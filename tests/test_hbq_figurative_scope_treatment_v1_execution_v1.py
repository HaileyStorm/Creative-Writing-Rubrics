from __future__ import annotations

import importlib.util
import gzip
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-scope-treatment-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("fstexec", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _verified(s, root: Path, slot: dict[str, object]) -> dict[str, object]:
    return {
        "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"],
        "arm": slot["arm"], "gate": s._gate_name(slot), "correct": True,
        "verdict": slot["oracle"]["expected_verdict"], "run_id": f"run-{slot['slot_id']}",
        "checkpoint_chain_head_sha256": "a" * 64, "session_id_sha256": (f"{int(slot['slot_id'].split('-')[1]):064x}"),
        "evidence": [{"reference": "artifact", "exact_quote": slot["artifact_text"][:40]}],
        "note": "revision note" if slot["oracle"]["source_case_id"] == "isolated-local-defect" else "grounded note",
        "accepted_provider_call_count": 1, "rejected_retry_count": 0, "batch_attempt_count": 1,
        "normalization_events": [],
    }


def _prepared_runtime(s, root: Path) -> list[dict[str, object]]:
    s.prepare(root)
    schedule = json.loads((root / "private-schedule.json").read_text(encoding="utf-8"))["slots"]
    for slot in schedule:
        target = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"prompt:{slot['artifact_id']}:{slot['arm']}", encoding="utf-8")
    resolved = s._runtime_schedule(root, schedule)
    s._write_summary(root / "runtime-schedule.json", s.canonical_json({"format_version": 1, "slots": resolved}))
    return resolved


def _fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        target = Path(command[command.index("-o") + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("rendered:" + command[command.index("--artifact-id") + 1] + (":treatment" if "--task-contract" in command else ":baseline"), encoding="utf-8")
    else:
        run = Path(command[command.index("--output-dir") + 1])
        run.mkdir(parents=True, exist_ok=True)
        (run / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_frozen_execution_schedule_uses_the_published_corpus_without_copying_it() -> None:
    s = study()
    report = s.validate_package()
    schedule = s.build_schedule()
    assert report["planned_requests"] == len(schedule) == 168
    assert {slot["arm"] for slot in schedule} == {"baseline", "scope_rendering_only"}
    assert {slot["leaf_id"] for slot in schedule} == s.LEAVES
    assert all(slot["artifact_file"].startswith("asset-") for slot in schedule)
    assert all(slot["logical_sample_id"].startswith("sample:") for slot in schedule)
    assert not (ROOT / "public-synthetic-prompt-scope-corpus.json").exists()


def test_prepare_keeps_provider_inputs_opaque_and_binds_only_treatment_to_v4_context(tmp_path: Path) -> None:
    s = study()
    result = s.prepare(tmp_path)
    schedule = json.loads((tmp_path / "private-schedule.json").read_text(encoding="utf-8"))["slots"]
    baseline = next(slot for slot in schedule if slot["arm"] == "baseline")
    treatment = next(slot for slot in schedule if slot["arm"] == "scope_rendering_only")
    baseline_command = s.command_for(baseline, tmp_path)
    treatment_command = s.command_for(treatment, tmp_path)
    assert result["planned_requests"] == 168
    assert "--task-contract" not in baseline_command
    assert treatment_command.count("--task-contract") == 1
    assert treatment_command[0:3] == [sys.executable, "-m", "hbqrs"]
    assert treatment_command[treatment_command.index("--batch-size") + 1] == "1"
    assert treatment_command[treatment_command.index("--question-id") + 1] == treatment["leaf_id"]
    provider_input = (tmp_path / "inputs" / treatment["artifact_file"]).read_text(encoding="utf-8")
    contract = (tmp_path / "contracts" / "contract-001.json").read_text(encoding="utf-8")
    for forbidden in ("isolated-local-defect", "scope_rendering_only", "expected_verdict", "controller_scope", "oracle"):
        assert forbidden not in provider_input
        assert forbidden not in contract
    assert treatment["task_contract"]["preferences"] == []
    assert treatment["task_contract"]["weighted_goals"] == []


def test_settlement_decisions_are_practical_and_do_not_require_extra_receipts(tmp_path: Path) -> None:
    s = study()
    _prepared_runtime(s, tmp_path)
    no_effect = s.settle(tmp_path, verifier=lambda root, slot: _verified(s, root, slot))
    assert no_effect["decision"] == "NO_EFFECT"
    assert no_effect["completed_slots"] == 168
    expected = {"stockness": 36, "proportion_material_load": 36, "fatigue": 12, "isolated_yes_revision_note": 3, "recurring_no": 3, "excerpt_cannot_assess": 3, "schema_evidence_provenance": 84}
    assert {name: value["denominator"] for name, value in no_effect["gates"]["baseline"].items() if name in expected} == expected
    assert {name: value["denominator"] for name, value in no_effect["gates"]["scope_rendering_only"].items() if name in expected} == expected
    corrupted = dict(no_effect["published_v1_analysis"])
    corrupted["gates"] = dict(corrupted["gates"])
    corrupted["gates"]["schema_evidence_provenance"] = {"passed": False, "correct": 167, "denominator": 168}
    assert s._decision_from_v1_gates(no_effect["gates"], corrupted) == "NO_GO"
    malformed = dict(no_effect["published_v1_analysis"])
    malformed["gates"] = {"schema_evidence_provenance": {"passed": True, "correct": 168, "denominator": 168}}
    with pytest.raises(ValueError, match="analyzer"):
        s._decision_from_v1_gates(no_effect["gates"], malformed)

    other = tmp_path.parent / "treatment-improves"
    _prepared_runtime(s, other)

    def treatment_improves(root: Path, slot: dict[str, object]) -> dict[str, object]:
        row = _verified(s, root, slot)
        if slot["arm"] == "baseline" and s._gate_name(slot) == "isolated_yes_revision_note":
            row["correct"] = False
            row["verdict"] = "NO"
        return row

    assert s.settle(other, verifier=treatment_improves)["decision"] == "GO_TREATMENT"

    incomplete = tmp_path.parent / "incomplete"
    _prepared_runtime(s, incomplete)

    def missing_one(root: Path, slot: dict[str, object]) -> dict[str, object]:
        if slot["slot_id"] == "slot-001":
            raise ValueError("missing CWR manifest")
        return _verified(s, root, slot)

    report = s.settle(incomplete, verifier=missing_one)
    assert report["decision"] == "INCOMPLETE"
    assert report["completed_slots"] == 167
    assert s.settle(incomplete, verifier=lambda root, slot: _verified(s, root, slot))["decision"] == "NO_EFFECT"


def test_private_root_must_not_be_the_checkout_and_dry_run_has_no_provider_calls(tmp_path: Path) -> None:
    s = study()
    with pytest.raises(ValueError, match="outside"):
        s.prepare(s.REPO_ROOT)
    report = s.dry_run(tmp_path, runner_call=_fake_cwr)
    assert report["mode"] == "dry_run"
    assert report["provider_calls"] == 0
    assert report["first_command"][0:4] == [sys.executable, "-m", "hbqrs", "judge"]
    assert len(report["rendered_prompt_sha256s"]) == 168


def test_duplicate_provider_sessions_invalidate_a_public_aggregate_and_execution_needs_ack(tmp_path: Path) -> None:
    s = study()
    _prepared_runtime(s, tmp_path)

    def duplicate_session(root: Path, slot: dict[str, object]) -> dict[str, object]:
        row = _verified(s, root, slot)
        row["session_id_sha256"] = "b" * 64
        return row

    report = s.settle(tmp_path, verifier=duplicate_session)
    assert report["decision"] == "INCOMPLETE"
    assert json.loads((tmp_path / "public-aggregate.json").read_text(encoding="utf-8"))["publicable"] is False
    with pytest.raises(ValueError, match="acknowledgement"):
        s.execute(tmp_path)


def test_checkpoint_prompt_and_harness_bindings_fail_closed_on_tampering(tmp_path: Path) -> None:
    s = study()
    run = tmp_path / "run"
    prompt = tmp_path / "rendered.txt"
    prompt.write_text("exact frozen prompt", encoding="utf-8")
    (run / "responses").mkdir(parents=True)
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt.read_bytes(), mtime=0))
    s._verify_checkpoint_prompt(run, prompt)
    prompt.write_text("changed after checkpoint", encoding="utf-8")
    with pytest.raises(ValueError, match="does not equal"):
        s._verify_checkpoint_prompt(run, prompt)

    root = tmp_path / "external"
    _prepared_runtime(s, root)
    manifest = json.loads((root / "study-manifest.json").read_text(encoding="utf-8"))
    manifest["runtime_bindings"]["successor_files"]["study.py"] = "0" * 64
    (root / "study-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="runtime"):
        s._validate_runtime_bindings(root)
