from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-successor-v1"


def _module(name: str):
    previous = sys.modules.get("study")
    sys.modules.pop("study", None)
    sys.path.insert(0, str(PACKAGE))
    try:
        spec = importlib.util.spec_from_file_location(name, PACKAGE / f"{name}.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PACKAGE))
        sys.modules.pop("study", None)
        if previous is not None:
            sys.modules["study"] = previous


def _planned() -> list[dict[str, object]]:
    return [
        {
            "event": "planned",
            "sequence": sequence,
            "item_id": "hanna-52" if sequence == 178 else f"story-{sequence}",
            "arm_id": "hbq_short_story_batch32" if sequence == 178 else "compact_analytic",
            "repetition": 5 if sequence == 178 else 1,
            "position": 4 if sequence == 178 else 1,
        }
        for sequence in range(77, 331)
    ]


def _closed_journal(planned: list[dict[str, object]], completed: int = 101) -> str:
    rows = [*planned]
    for event in planned[:completed]:
        rows.append({**event, "event": "completed", "run_binding_sha256": "a" * 64})
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)


def test_fresh_schedule_keeps_only_unfinished_cells_and_replays_partial_from_scratch(tmp_path: Path) -> None:
    study = _module("study")
    root = tmp_path / "closed"
    root.mkdir()
    planned = _planned()
    (root / "successor-schedule-journal.jsonl").write_text(_closed_journal(planned), encoding="utf-8")
    schedule = study.fresh_schedule(root)
    assert len(schedule) == 153
    assert [event["sequence"] for event in schedule] == list(range(178, 331))
    assert schedule[0]["item_id"] == "hanna-52"
    assert schedule[0]["fresh_dispatch"] is True
    assert "run_binding_sha256" not in schedule[0]


def test_duplicate_or_replayed_completed_cells_are_rejected(tmp_path: Path) -> None:
    study = _module("study")
    root = tmp_path / "closed"
    root.mkdir()
    planned = _planned()
    duplicated = [*planned]
    duplicated[1] = {**duplicated[1], "sequence": 77}
    (root / "successor-schedule-journal.jsonl").write_text(_closed_journal(duplicated), encoding="utf-8")
    with pytest.raises(ValueError, match="immutable 77-330 range"):
        study.schedule_from_closed(root)

    (root / "successor-schedule-journal.jsonl").write_text(_closed_journal(planned, completed=102), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed 254-cell plan plus 101 completions"):
        study.schedule_from_closed(root)


def test_prepare_is_contact_free_and_never_reuses_a_closed_or_partial_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_remainder")
    closed, source, work = tmp_path / "closed", tmp_path / "source", tmp_path / "fresh"
    closed.mkdir()
    source.mkdir()
    inherited = {"source": "exact"}
    (closed / "predecessor-binding.json").write_text(json.dumps(inherited), encoding="utf-8")
    schedule = [{"event": "planned", "fresh_dispatch": True, "sequence": 178, "item_id": "hanna-52", "arm_id": "hbq_short_story_batch32", "repetition": 5, "position": 4}]

    class Previous:
        def bind_predecessor(self, root):
            return inherited

        def _successor_plans(self, frozen):
            return [{"event": "planned", "sequence": 77}] * 101 + [{key: value for key, value in schedule[0].items() if key not in {"fresh_dispatch"}}]

    monkeypatch.setattr(runner, "bind_closed_successor", lambda root: {"closed": "exact"})
    monkeypatch.setattr(runner, "_previous_runner", lambda: Previous())
    monkeypatch.setattr(runner, "fresh_schedule", lambda root: schedule)
    monkeypatch.setattr(runner, "_runtime_commitment", lambda: {"runtime": "sealed"})
    monkeypatch.setattr(runner, "_outside_repo", lambda path: True)
    monkeypatch.setattr(runner, "read_json", lambda path: {"source": "exact"} if path.name == "predecessor-binding.json" else {"frozen": True})
    result = runner.prepare(closed, source, work)
    assert result["provider_calls"] == 0
    assert not (work / "runs").exists()
    assert json.loads((work / runner.JOURNAL).read_text(encoding="utf-8")) == schedule[0]
    (work / "runs").mkdir()
    with pytest.raises(ValueError, match="truly empty"):
        runner.prepare(closed, source, work)


def test_roots_must_be_disjoint_and_new_root_outside_repository(tmp_path: Path) -> None:
    runner = _module("run_remainder")
    closed, source = tmp_path / "closed", tmp_path / "source"
    closed.mkdir()
    source.mkdir()
    for output in (closed, closed / "child", source / "child", ROOT / ".remainder-private-output"):
        with pytest.raises(ValueError, match="pairwise disjoint|outside the repository|real external"):
            runner._roots(closed, source, output)


def _receipt(checked_at: datetime) -> dict[str, object]:
    return {
        "kind": "external_current_quota_evidence_v1",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "assertion": "quota_available",
        "observed_at": checked_at.isoformat(),
        "observation": {"surface": "native_codex_quota_surface", "reference": "native visible quota observation"},
    }


def _complete_binding(runner, root: str = "C:/executor") -> dict[str, object]:
    files = [{"path": "launch.py", "bytes": 1, "sha256": "a" * 64}]
    files.extend({"path": f"dependency-{index:02d}", "bytes": index + 2, "sha256": f"{index + 1:064x}"} for index in range(32))
    runtime = {"git": {"head": "b" * 40, "upstream": "b" * 40}, "files": files, "sha256": hashlib.sha256(runner.canonical(files)).hexdigest()}
    return {"format_version": 1, "executor_root": root, "launcher": files[0], "runtime": runtime, "sha256": hashlib.sha256(runner.canonical(runtime)).hexdigest()}


def test_external_quota_evidence_requires_post_retry_current_native_observation(tmp_path: Path) -> None:
    runner = _module("run_remainder")
    retry = datetime.fromisoformat(runner.RETRY_AFTER)
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(_receipt(retry - timedelta(seconds=1))), encoding="utf-8")
    with pytest.raises(ValueError, match="before the closed-run retry time"):
        runner.validate_external_quota_evidence(receipt, now=retry + timedelta(minutes=1))
    receipt.write_text(json.dumps(_receipt(retry + timedelta(minutes=1))), encoding="utf-8")
    assert runner.validate_external_quota_evidence(receipt, now=retry + timedelta(minutes=2))["assertion"] == "quota_available"
    with pytest.raises(ValueError, match="not current"):
        runner.validate_external_quota_evidence(receipt, now=retry + runner.MAX_PREFLIGHT_AGE + timedelta(minutes=2))
    receipt.write_text(json.dumps({**_receipt(retry + timedelta(minutes=1)), "observation": {"sha256": "a" * 64}}), encoding="utf-8")
    with pytest.raises(ValueError, match="non-hash native observation reference"):
        runner.validate_external_quota_evidence(receipt, now=retry + timedelta(minutes=2))


def test_authorization_is_short_lived_non_executable_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_remainder")
    work, receipt = tmp_path / "work", tmp_path / "receipt.json"
    work.mkdir()
    retry = datetime.fromisoformat(runner.RETRY_AFTER)
    current = retry + timedelta(minutes=1)
    receipt.write_text(json.dumps(_receipt(current)), encoding="utf-8")
    schedule, execution = [{"sequence": 178}], {"sealed": True}
    (work / runner.EXECUTION).write_text("{}\n", encoding="utf-8")
    (work / runner.JOURNAL).write_text(json.dumps(schedule[0]) + "\n", encoding="utf-8")
    binding = _complete_binding(runner)
    (work / runner.EXECUTOR_BINDING).write_text(json.dumps(binding) + "\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_verify_prepared", lambda *args, **kwargs: (schedule, execution))
    monkeypatch.setattr(runner, "validate_executor_binding", lambda *args: binding)
    result = runner.authorize(tmp_path / "closed", tmp_path / "source", work, receipt, now=current)
    authorization = json.loads((work / runner.AUTHORIZATION).read_text(encoding="utf-8"))
    assert result["authorized"] == "non_executable_handoff"
    assert authorization["authorized_at"] == current.isoformat()
    assert authorization["expires_at"] == (current + runner.AUTHORIZATION_TTL).isoformat()
    assert authorization["executable"] is False
    assert "launch-time" in authorization["launch_time_revalidation"]


def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(tmp_path: Path) -> None:
    study = _module("study")
    for text in ('{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}'):
        with pytest.raises(ValueError, match="Invalid strict JSON"):
            study.parse_json_object(text, "fixture")
    path = tmp_path / "bad.json"
    path.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid strict JSON"):
        study.read_json(path)


def test_executor_binding_requires_all_hbq_inputs_and_plain_external_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_remainder")
    root = tmp_path / "executor"
    closed, source, work = tmp_path / "closed", tmp_path / "source", tmp_path / "work"
    closed.mkdir()
    source.mkdir()
    root.mkdir()
    launcher = root / "launch.py"
    launcher.write_text("pass\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_outside_repo", lambda path: True)
    frozen = {"contract": {"arms": [{"kind": "native", "prompt": f"../arms/prompt-{index}.md", "schema": f"../arms/schema-{index}.json"} for index in range(5)]}}
    monkeypatch.setattr(runner, "_previous_runner", lambda: object())
    monkeypatch.setattr(runner, "_source_binding", lambda source, previous: ({}, frozen))
    monkeypatch.setattr(runner, "_clean_executor_projection", lambda root, files: {"git": {"head": "a" * 40, "upstream": "a" * 40}, "files": files, "sha256": "b" * 64})
    for relative in ("src/hbqrs/runner.py", "src/hbqrs/longform_runner.py", "src/hbqrs/core.py", "src/hbqrs/paths.py", "registry/all_modules.json", "bundles/all_bundles.json", "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md", "schema/hbq_judge_response.schema.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Required root is missing"):
        runner.bind_executor(root, launcher, closed, source, work)
    dependencies = runner._executor_dependencies(root, frozen, launcher)
    assert len(dependencies) == 33
    for path in dependencies:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    binding = runner.bind_executor(root, launcher, closed, source, work)
    assert binding["launcher"]["sha256"]
    assert len(binding["runtime"]["files"]) == 33
    original_is_reparse = runner._is_reparse
    monkeypatch.setattr(runner, "_is_reparse", lambda path: path.name == "runner.py" or original_is_reparse(path))
    with pytest.raises(ValueError, match="reparse"):
        runner._file_commitment(root / "src" / "hbqrs" / "runner.py", root=root)
    monkeypatch.setattr(runner, "_is_reparse", original_is_reparse)
    closed_launcher = closed / "launch.py"
    closed_launcher.write_text("pass\n", encoding="utf-8")
    with pytest.raises(ValueError, match="pairwise disjoint"):
        runner.bind_executor(closed, closed_launcher, closed, source, work)


def test_executor_projection_requires_clean_exact_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = _module("run_remainder")
    root = tmp_path / "executor"
    root.mkdir()

    def git(command, **kwargs):
        if command[1:3] in (["rev-parse", "HEAD"], ["rev-parse", "@{u}"]):
            return "a" * 40 + "\n"
        if command[1:3] == ["status", "--porcelain"]:
            return " M src/hbqrs/runner.py\n"
        raise AssertionError(command)

    monkeypatch.setattr(runner.subprocess, "check_output", git)
    with pytest.raises(ValueError, match="clean and exactly pushed"):
        runner._clean_executor_projection(root, [{"path": "src/hbqrs/runner.py", "bytes": 1, "sha256": "a" * 64}])


def test_executor_binding_is_persisted_before_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_remainder")
    work = tmp_path / "work"
    work.mkdir()
    sealed = _complete_binding(runner)
    monkeypatch.setattr(runner, "_verify_prepared", lambda *args, **kwargs: ([], {}))
    monkeypatch.setattr(runner, "bind_executor", lambda *args: sealed)
    monkeypatch.setattr(runner, "validate_executor_binding", lambda *args: sealed)
    assert runner.seal_executor_binding(tmp_path / "executor", tmp_path / "launcher", tmp_path / "closed", tmp_path / "source", work) == sealed
    assert json.loads((work / runner.EXECUTOR_BINDING).read_text(encoding="utf-8")) == sealed


def test_executor_binding_is_reconstructed_and_forgery_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_remainder")
    work = tmp_path / "work"
    work.mkdir()
    binding = _complete_binding(runner)
    (work / runner.EXECUTOR_BINDING).write_text(json.dumps(binding) + "\n", encoding="utf-8")
    monkeypatch.setattr(runner, "bind_executor", lambda *args: binding)
    assert runner.validate_executor_binding(tmp_path / "closed", tmp_path / "source", work) == binding
    forged = _complete_binding(runner)
    forged["runtime"]["files"][1]["sha256"] = "f" * 64
    forged["runtime"]["sha256"] = hashlib.sha256(runner.canonical(forged["runtime"]["files"])).hexdigest()
    forged["sha256"] = hashlib.sha256(runner.canonical(forged["runtime"])).hexdigest()
    (work / runner.EXECUTOR_BINDING).write_text(json.dumps(forged) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match its reconstructed"):
        runner.validate_executor_binding(tmp_path / "closed", tmp_path / "source", work)


def test_launch_handoff_enforces_expiry_and_transitive_executor_binding(tmp_path: Path) -> None:
    runner = _module("run_remainder")
    work = tmp_path / "work"
    work.mkdir()
    retry = datetime.fromisoformat(runner.RETRY_AFTER)
    binding = work / runner.EXECUTOR_BINDING
    complete_binding = _complete_binding(runner)
    binding.write_text(json.dumps(complete_binding) + "\n", encoding="utf-8")
    (work / runner.EXECUTION).write_text("{}\n", encoding="utf-8")
    (work / runner.JOURNAL).write_text("{}\n", encoding="utf-8")
    (work / runner.PREFLIGHT).write_text("{}\n", encoding="utf-8")
    authorization = {
        "authorized_at": retry.isoformat(),
        "expires_at": (retry + runner.AUTHORIZATION_TTL).isoformat(),
        "executor_binding_sha256": runner.sha(binding),
        "execution_contract_sha256": runner.sha(work / runner.EXECUTION),
        "schedule_journal_sha256": runner.sha(work / runner.JOURNAL),
        "external_quota_evidence_sha256": runner.sha(work / runner.PREFLIGHT),
        "executable": False,
    }
    (work / runner.AUTHORIZATION).write_text(json.dumps(authorization) + "\n", encoding="utf-8")
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(runner, "validate_executor_binding", lambda *args: complete_binding)
    assert runner.validate_launch_handoff(tmp_path / "closed", tmp_path / "source", work, now=retry + timedelta(minutes=1))["executable"] is False
    with pytest.raises(ValueError, match="has expired"):
        runner.validate_launch_handoff(tmp_path / "closed", tmp_path / "source", work, now=retry + runner.AUTHORIZATION_TTL + timedelta(minutes=1))
    forged = _complete_binding(runner)
    forged["sha256"] = "c" * 64
    binding.write_text(json.dumps(forged) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="binding drifted"):
        runner.validate_launch_handoff(tmp_path / "closed", tmp_path / "source", work, now=retry + timedelta(minutes=1))
    monkeypatch.undo()


def test_fresh_sessions_are_checked_against_both_lineages(tmp_path: Path) -> None:
    runner = _module("run_remainder")
    runs = tmp_path / "runs"
    runs.mkdir()
    (runs / "response.json").write_text(json.dumps({"session_id": "new-session"}), encoding="utf-8")
    fresh_hash = __import__("hashlib").sha256(b"new-session").hexdigest()
    execution = {"lineage_sessions": {"source": {"ids_sha256": []}, "closed": {"ids_sha256": []}}}
    assert runner.validate_fresh_sessions(runs, execution)["ids_sha256"] == [fresh_hash]
    execution["lineage_sessions"]["closed"]["ids_sha256"] = [fresh_hash]
    with pytest.raises(ValueError, match="collides with source or closed"):
        runner.validate_fresh_sessions(runs, execution)


def test_real_closed_root_is_exact_when_present() -> None:
    study = _module("study")
    closed = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff")
    if not closed.is_dir():
        pytest.skip("closed external successor root is host-local evidence")
    binding = study.bind_closed_successor(closed)
    assert binding["completed"] == {"count": 101, "first_sequence": 77, "last_sequence": 177}
    assert binding["partial"]["accepted_batches"] == [1, 2]
    assert binding["partial"]["rejected_batch"] == 3
    assert binding["remaining"] == {"count": 153, "first_sequence": 178, "last_sequence": 330}
