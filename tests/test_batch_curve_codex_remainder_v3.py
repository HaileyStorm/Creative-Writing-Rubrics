from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "batch-curve-codex-remainder-v3"


def _module():
    spec = importlib.util.spec_from_file_location("batch_curve_codex_remainder_v3", ROOT / "batch_recovery.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def _run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    if argv[:2] == ["git", "rev-parse"]: return subprocess.CompletedProcess(argv, 0, "a" * 40 + "\n", "")
    if argv[:2] == ["git", "status"]: return subprocess.CompletedProcess(argv, 0, "", "")
    if argv[:2] == ["git", "ls-files"]: return subprocess.CompletedProcess(argv, 0, argv[-1] + "\n", "")
    if argv[-1] == "--version": return subprocess.CompletedProcess(argv, 0, "codex test\n", "")
    raise AssertionError(argv)


def _canonical_bytes(module, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_bound", lambda binding: (module.HERE / binding["path"]).resolve())
    monkeypatch.setattr(module, "BASE_PLAN", lambda: list(module.V2.REMAINDER.schedule()))


def test_exact_v2_root_freeze_and_invalid_schema_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch)
    predecessor = module._predecessor()
    assert predecessor["attempt"] == {"logical_attempt": 1, "epoch": 1, "refresh": 1, "status": "failed_invalid_json_schema", "scored_provider_calls": 0}
    assert module._read(module._bound(predecessor["old_schema"]))["properties"]["ready"] == {"const": True}
    original = module._tree
    monkeypatch.setattr(module, "_tree", lambda root: [] if root == module.V2_PUBLIC else original(root))
    with pytest.raises(ValueError, match="tree drifted"):
        module._predecessor()


def test_valid_v3_schema_and_47_sealed_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch)
    assert module._read(module._preflight_schema()) == {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "required": ["ready"], "properties": {"ready": {"type": "boolean", "const": True}}}
    rows = module.plan()
    assert len(rows) == 47 and not any(row["parent_cell"] == 36 and row["batch"] <= 31 for row in rows)


def test_inherited_preflight_starts_successor_at_attempt_two_without_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch); attempts: list[int] = []
    with tempfile.TemporaryDirectory(prefix="cwr-batch-v3-", dir=str(ROOT.parents[3])) as outer:
        work, private = Path(outer) / "work", Path(outer) / "private"
        receipt = module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(Path(outer) / "codex.exe"))
        assert receipt["inherited_preflight_provider_calls"] == 1 and receipt["inherited_scored_provider_calls"] == 0
        def ready(**kwargs: object):
            attempts.append(kwargs["attempt_number"])
            assert json.loads(Path(kwargs["response_schema"]).read_text(encoding="utf-8"))["properties"]["ready"] == {"type": "boolean", "const": True}
            return "{\"ready\":true}", {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "native-capacity"}}
        first = module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(Path(outer) / "codex.exe"), now=datetime.fromisoformat("2026-08-22T03:00:00-06:00"), invoke=ready)
        second = module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(Path(outer) / "codex.exe"), now=datetime.fromisoformat("2026-08-22T03:01:00-06:00"), invoke=ready)
        assert first["logical_attempt"] == 2 and second["logical_attempt"] == 3 and attempts == [2, 3]
        assert sorted((work / "preflights" / "epoch-0001").glob("refresh-*.json"))[-1].name == "refresh-0002.json"


def test_clean_pushed_gate_rejects_dirty_source() -> None:
    module = _module()
    with pytest.raises(ValueError, match="clean committed pushed"):
        module._git_state(lambda argv, **_kwargs: subprocess.CompletedProcess(argv, 0, "dirty\n" if argv[:2] == ["git", "status"] else "a" * 40 + "\n", ""))


def test_v3_scored_artifacts_keep_v3_protocol_and_run_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch)
    row = {"sequence": 1, "parent_cell": 36, "batch": 32, "size": 1, "question_ids": ["q1"], "question_count": 1}
    monkeypatch.setattr(module.V2, "_items_for", lambda _row: [{"question": {"id": "q1"}}])
    monkeypatch.setattr(module.V2, "_prompt", lambda _items: "v3 prompt")
    monkeypatch.setattr(module.V2, "_stack", lambda _name: ROOT / "capacity-preflight.schema.json")
    run_ids: list[str] = []
    def normalize(*_args: object, **kwargs: object):
        run_ids.append(kwargs["run_id"])
        return [{"question_id": "q1", "run_id": kwargs["run_id"]}]
    monkeypatch.setattr(module.shared, "_normalize_batch", normalize)
    monkeypatch.setattr(module.shared, "_write_verdicts", lambda path, verdicts: path.write_text(json.dumps(verdicts), encoding="utf-8"))
    monkeypatch.setattr(module.V2, "load_modules", lambda _path: [])
    monkeypatch.setattr(module.V2, "load_bundles", lambda _path: [{"bundle_id": "prose.short_story"}])
    monkeypatch.setattr(module.V2.core, "score_bundle", lambda *_args, **_kwargs: {"score": 1})
    monkeypatch.setattr(module.V2.scoring_v2, "score_bundle", lambda *_args, **_kwargs: {"score": 1})
    module._delegate()
    prepared = module._prepare_unit(tmp_path, row)
    result = module._run_unit(tmp_path, row, "fake", prepared=prepared, invoke=lambda **_kwargs: ("{}", {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "v3-session"}}))
    destination = module.V2._unit_path(tmp_path, row)
    assert module._read(destination / "run.json")["protocol"] == "batch-curve-codex-remainder-v3-cap1"
    assert module._read(destination / "responses" / "attempt-outcome.json")["normalized_verdicts"][0]["run_id"] == "batch-curve-codex-remainder-v3"
    assert run_ids == ["batch-curve-codex-remainder-v3", "batch-curve-codex-remainder-v3"] and result["verdict_count"] == 1


def test_private_only_terminal_preflight_settles_then_advances_without_resend(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch); attempts: list[int] = []
    with tempfile.TemporaryDirectory(prefix="cwr-batch-v3-", dir=str(ROOT.parents[3])) as outer:
        root = Path(outer); work, private = root / "work", root / "private"
        module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"))
        def failed(**kwargs: object):
            attempts.append(kwargs["attempt_number"])
            raise module.shared._ProviderAttemptFailure("failed", retryable=False, content="", provider_record=None)
        with pytest.raises(ValueError, match="capacity preflight failed"):
            module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"), now=datetime.fromisoformat("2026-08-22T03:00:00-06:00"), invoke=failed)
        first = work / "preflights" / "epoch-0001" / "refresh-0001.json"; first.unlink()
        def ready(**kwargs: object):
            attempts.append(kwargs["attempt_number"])
            return "{\"ready\":true}", {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "v3-session"}}
        recovered = module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"), now=datetime.fromisoformat("2026-08-22T03:01:00-06:00"), invoke=ready)
        assert attempts == [2, 3] and recovered["logical_attempt"] == 3 and module._read(first)["status"] == "failed"


def test_incomplete_private_only_preflight_fails_closed_before_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch); calls: list[object] = []
    with tempfile.TemporaryDirectory(prefix="cwr-batch-v3-", dir=str(ROOT.parents[3])) as outer:
        root = Path(outer); work, private = root / "work", root / "private"
        module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"))
        (private / "preflights" / "epoch-0001" / "refresh-0001.json").mkdir(parents=True)
        with pytest.raises(ValueError, match="cannot be adjudicated"):
            module.native_preflight(work, private, epoch=1, subprocess_run=_run, executable_resolver=lambda _: str(root / "codex.exe"), now=datetime.fromisoformat("2026-08-22T03:00:00-06:00"), invoke=lambda **_kwargs: calls.append(True))
        assert calls == []


def test_execute_replays_completed_v3_prefix_with_v3_verifier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _module(); _canonical_bytes(module, monkeypatch)
    rows = [
        {"sequence": 1, "parent_cell": 36, "batch": 32, "size": 1, "question_ids": ["q1"], "question_count": 1},
        {"sequence": 2, "parent_cell": 36, "batch": 33, "size": 1, "question_ids": ["q2"], "question_count": 1},
    ]
    monkeypatch.setattr(module, "plan", lambda: rows)
    monkeypatch.setattr(module, "_receipt", lambda private, *_args: {"runtime": {"executable": "fake"}})
    monkeypatch.setattr(module, "_prepare_unit", lambda private, row: {"destination": private / "runs" / module.V2._unit_name(row)})
    monkeypatch.setattr(module.V2, "_historical_session_hashes", lambda: set())
    monkeypatch.setattr(module.V2, "_active_preflight", lambda *_args, **_kwargs: {"active": True})
    verified: list[int] = []
    def v3_verifier(_private: Path, row: dict, _executable: str) -> dict:
        verified.append(row["sequence"])
        return {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "verdict_count": row["question_count"], "sessions": [{"session_id_sha256": f"{row['sequence']:064x}"}]}
    monkeypatch.setattr(module, "_verify_unit", v3_verifier)
    def unit_runner(private: Path, row: dict, _executable: str) -> dict:
        destination = private / "runs" / module.V2._unit_name(row); destination.mkdir(parents=True); (destination / "raw.txt").write_text(str(row["sequence"]), encoding="utf-8")
        return {"run_sha256": "a" * 64, "score_sha256": "b" * 64, "score_v2_sha256": "c" * 64, "verdict_count": row["question_count"], "sessions": [{"session_id_sha256": f"{row['sequence']:064x}"}]}
    with tempfile.TemporaryDirectory(prefix="cwr-batch-v3-", dir=str(ROOT.parents[3])) as outer:
        work, private = Path(outer) / "work", Path(outer) / "private"; module.prepare(work, private, subprocess_run=_run, executable_resolver=lambda _: str(Path(outer) / "codex.exe"))
        first = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(Path(outer) / "codex.exe"), unit_runner=unit_runner, max_scored_units=1)
        second = module.execute(work, private, subprocess_run=_run, executable_resolver=lambda _: str(Path(outer) / "codex.exe"), unit_runner=unit_runner, max_scored_units=1)
        assert first["completed_units"] == 1 and second["completed_units"] == 2 and verified == [1]
