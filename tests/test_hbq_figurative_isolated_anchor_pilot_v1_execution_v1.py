from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as historical_runtime

ROOT = book_root() / "evaluation-results" / "hbq-figurative-isolated-anchor-pilot-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("figurative_anchor_pilot_execution", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return historical_runtime.install(module, source_commit="6ae9ee0db17dda61bb9adc00a60bcd8072969d5d")


@pytest.fixture
def external_private():
    root = Path(tempfile.mkdtemp(prefix="hbq-figurative-anchor-pilot-"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def fake_cwr(command, **_kwargs):
    if command[-1] == "--version":
        return SimpleNamespace(returncode=0, stdout="codex-cli test-version\n", stderr="")
    if command[-2:] == ["login", "status"]:
        return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
    if "render-judge" in command:
        output = Path(command[command.index("--output") + 1])
        task = json.loads(Path(command[command.index("--task-contract") + 1]).read_text(encoding="utf-8"))
        requirements = "\n".join(task["context"]["constraints"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"production prompt\n{requirements}\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    if "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text(
            json.dumps({"format_version": 5, "configuration": {"compiled_bundle_sha256": "f" * 64}}),
            encoding="utf-8",
        )
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_contract_schedule_and_ownership_are_exact():
    s = study()
    assert s.validate_package() == {
        "study_id": s.STUDY_ID,
        "slots": 18,
        "control_slots": 12,
        "target_slots": 6,
        "provider_calls": 0,
        "promotion": "none",
    }
    schedule = s.build_schedule()
    assert len(schedule) == 18
    assert all(slot["stage"] == "control" for slot in schedule[:12])
    assert all(slot["stage"] == "target" for slot in schedule[12:])
    assert {slot["leaf_id"] for slot in schedule[:12]} == set(s.CONTROLS)
    assert {slot["leaf_id"] for slot in schedule[12:]} == {s.TARGET}
    assert all(slot["treatment"] == "current_production_prompt" for slot in schedule[:12])
    assert all(slot["treatment"] == "manual_leaf_appendix_v1" for slot in schedule[12:])
    assert s.contract()["claims"]["ownership"] == "unchanged"
    assert s.contract()["claims"]["promotion"] == "none"


def test_manual_appendix_exists_only_in_target_task_contract():
    s = study()
    schedule = s.build_schedule()
    for slot in schedule:
        task = s._task_contract(slot)
        requirements = task["context"]["constraints"]
        assert task["binding_requirements"] == []
        if slot["stage"] == "target":
            assert requirements == [
                "Use only the supplied artifact.",
                s.STRICT_EVIDENCE_INSTRUCTION,
                s.TARGET_TREATMENT,
            ]
            assert "familiarity/defaultness" in requirements[2]
            assert "sheer figurative load" in requirements[2]
        else:
            assert requirements == ["Use only the supplied artifact.", s.STRICT_EVIDENCE_INSTRUCTION]


def test_target_negative_fixture_has_no_oracle_leaking_meta_language():
    s = study()
    negative = next(item for item in s._corpus() if item["case_id"] == "metaphor-clear-no")
    text = negative["text"].casefold()
    assert "without any change" not in text
    assert "without acknowledging" not in text
    assert "contradiction" not in text
    assert "zipper" in text and "welded wall" in text


def test_real_strict_evidence_validation_rejects_summary_only():
    s = study()
    slot = s.build_schedule()[0]
    with pytest.raises(ValueError, match="source-exact quote.*summary-only"):
        s._validate_strict_evidence(
            [{"reference": "synthetic", "summary": "The image is relevant."}],
            artifact_text=slot["artifact_text"],
            question_id=slot["leaf_id"],
            normalization_audit=[],
        )


def test_real_strict_evidence_validation_rejects_normalized_invalid_quote():
    s = study()
    slot = s.build_schedule()[0]
    audit = [{
        "question_id": slot["leaf_id"],
        "evidence_index": 1,
        "raw_sha256": "a" * 64,
        "from": "exact_quote",
        "to": "summary",
        "reason": "not_verbatim",
    }]
    with pytest.raises(ValueError, match="empty normalization audit"):
        s._validate_strict_evidence(
            [{"reference": "synthetic", "summary": "not a verbatim quote"}],
            artifact_text=slot["artifact_text"],
            question_id=slot["leaf_id"],
            normalization_audit=audit,
        )


def test_real_strict_evidence_validation_accepts_source_exact_quote():
    s = study()
    slot = s.build_schedule()[0]
    quote = "Mara listened for the boiler."
    result = s._validate_strict_evidence(
        [{"reference": "synthetic", "exact_quote": quote}],
        artifact_text=slot["artifact_text"],
        question_id=slot["leaf_id"],
        normalization_audit=[],
    )
    assert result["exact_quote_count"] == 1
    assert result["normalization_audit"] == "empty"


def test_provider_free_dry_run_binds_18_prompts_and_control_first_receipt(external_private):
    s = study()
    report = s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    assert report["provider_calls"] == 0
    assert report["rendered_prompts"] == 18
    assert report["control_slots"] == 12 and report["target_slots"] == 6
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    receipt = json.loads((root / "receipts" / "control-first-provider-free-dry-run.v1.json").read_text(encoding="utf-8"))
    assert receipt["provider_calls"] == 0
    assert receipt["stage_order"] == "all_controls_before_any_target"
    prompts = sorted((root / "rendered-prompts").glob("*.txt"))
    assert len(prompts) == 18
    control_text = "\n".join(path.read_text(encoding="utf-8") for path in prompts[:12])
    target_text = "\n".join(path.read_text(encoding="utf-8") for path in prompts[12:])
    assert s.TARGET_TREATMENT not in control_text
    assert target_text.count(s.TARGET_TREATMENT) == 6


def _record_for(slot, *, correct=True):
    verdict = slot["expected_verdict"] if correct else ("NO" if slot["expected_verdict"] == "YES" else "YES")
    return {
        "slot_id": slot["slot_id"],
        "verdict": verdict,
        "correct": correct,
        "session_id_sha256": slot["slot_id"].ljust(64, "0")[:64],
        "checkpoint_chain_head_sha256": slot["slot_id"].ljust(64, "1")[:64],
        "prompt_commitments": {},
    }


def test_execute_stops_after_12_controls_on_semantic_miss(external_private, monkeypatch):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    dispatched = []

    def dispatch(command, **kwargs):
        if "--allow-remote" in command:
            dispatched.append(command)
        return fake_cwr(command, **kwargs)

    calls = 0

    def verify(_root, slot):
        nonlocal calls
        calls += 1
        return _record_for(slot, correct=calls != 1)

    monkeypatch.setattr(s, "_verify_slot", verify)
    result = s.execute(
        external_private,
        allow_remote=True,
        acknowledged_zero_incremental_charge=True,
        runner_call=dispatch,
        auth_call=fake_cwr,
    )
    assert result["decision"] == "CONTROL_FIXTURE_OR_PROMPT_NO_GO"
    assert len(dispatched) == 12
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    assert json.loads((root / "control-gate.v1.json").read_text(encoding="utf-8"))["passed"] is False


def test_execute_dispatches_target_only_after_12_of_12_controls(external_private, monkeypatch):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    dispatched = []

    def dispatch(command, **kwargs):
        if "--allow-remote" in command:
            dispatched.append(command)
        return fake_cwr(command, **kwargs)

    monkeypatch.setattr(s, "_verify_slot", lambda _root, slot: _record_for(slot))
    result = s.execute(
        external_private,
        allow_remote=True,
        acknowledged_zero_incremental_charge=True,
        runner_call=dispatch,
        auth_call=fake_cwr,
    )
    assert result["executed_slots"] == 18
    assert result["control_gate"] == "12_of_12_passed_before_target"
    assert len(dispatched) == 18
    assert all(s.CONTROLS.__contains__(command[command.index("--question-id") + 1]) for command in dispatched[:12])
    assert all(command[command.index("--question-id") + 1] == s.TARGET for command in dispatched[12:])


def test_command_is_singleton_one_attempt_and_dual_gated(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    slot = s._validated_runtime_schedule(external_private)[0]
    command = s.command_for(slot, external_private)
    assert command[command.index("--batch-size") + 1] == "1"
    assert command[command.index("--batch-attempts") + 1] == "1"
    assert command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"
    assert "--resume" not in command and "--allow-remote" not in command
    assert s.command_for(slot, external_private, allow_remote=True)[-1] == "--allow-remote"
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(external_private, runner_call=fake_cwr, auth_call=fake_cwr)


def test_settlement_requires_execution_claim_and_does_not_trigger_dspy(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    result = s.settle(external_private)
    assert result["decision"] == "INCOMPLETE_NO_RETRY"
    assert result["dspy_eligible"] is False
    assert result["promotion"] == "none"
