from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-other-lexical-overlap-ownership-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("l2_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_codex(command, **_kwargs):
    output = Path(command[command.index("--output-last-message") + 1])
    assert output.parent.is_dir()
    prompt = _kwargs["input"]
    question_id = next(line for line in prompt.splitlines() if '"question_id":' in line).split('"')[3]
    output.write_text(json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "summary", "reference": "supplied synthetic artifact", "exact_quote": None, "summary": "Grounded assessment of the supplied artifact."}], "note": "Synthetic test response."}]}), encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="completed", stderr="provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n")


def test_execution_binds_l2_predecessor_geometry_and_actual_image_slots():
    s = study()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "slots": 216, "provider_calls": 0, "predecessor": s.PREDECESSOR_COMMIT, "visual_image_slots": 72}
    schedule = s.build_schedule()
    assert len(schedule) == len({slot["slot_id"] for slot in schedule}) == len({slot["run_id"] for slot in schedule}) == 216
    assert len({slot["artifact_id"] for slot in schedule}) == 36
    assert len({(slot["case_id"], slot["artifact_id"]) for slot in schedule}) == 36
    visual = [slot for slot in schedule if slot["image_input"]]
    assert len(visual) == 72
    assert {slot["image_input"]["mime_type"] for slot in visual} == {"image/png"}
    assert all("expected_verdict" not in slot["prompt"] for slot in schedule)


def test_dry_run_freezes_each_png_copy_and_codex_image_command_without_contact(tmp_path: Path):
    s = study()
    report = s.dry_run(tmp_path)
    assert report["provider_calls"] == 0 and report["visual_image_slots"] == 72
    schedule = s.build_schedule()
    visual = next(slot for slot in schedule if slot["image_input"])
    command = s.command_for(visual, tmp_path)
    image_path = Path(command[command.index("--image") + 1])
    assert image_path.is_file() and image_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "--image" in command and "--output-schema" in command
    text_slot = next(slot for slot in schedule if not slot["image_input"])
    assert "--image" not in s.command_for(text_slot, tmp_path)
    manifest = json.loads((tmp_path / "study-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["slots"]) == 216 and "expected_verdict" not in json.dumps(manifest)


def test_execute_requires_dual_gate_and_quarantines_incomplete_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    s = study()
    s.dry_run(tmp_path)
    monkeypatch.setattr(s, "_validated_schedule", lambda _root: [s.build_schedule()[0]])
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(tmp_path, runner_call=_fake_codex)
    failing = lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout="", stderr="transport failed")
    with pytest.raises(RuntimeError, match="reconciliation"):
        s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=failing)
    with pytest.raises(ValueError, match="is ambiguous"):
        s.execute(tmp_path, resume=True, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_codex)


def test_definitively_invalid_response_retries_once_in_separate_attempt_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    s = study()
    s.dry_run(tmp_path)
    slot = s.build_schedule()[0]
    monkeypatch.setattr(s, "_validated_schedule", lambda _root: [slot])
    calls = []
    def invalid_then_valid(command, **kwargs):
        output = Path(command[command.index("--output-last-message") + 1])
        assert output.parent.is_dir()
        calls.append(output)
        if len(calls) == 1:
            output.write_text("{}", encoding="utf-8")
        else:
            _fake_codex(command, **kwargs)
        return SimpleNamespace(returncode=0, stdout="completed", stderr="provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n")
    assert s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=invalid_then_valid)["completed_slots"] == 1
    assert [path.parent.parent.name for path in calls] == ["attempt-01", "attempt-02"]
    assert json.loads(s._outcome_path(tmp_path, slot, 1).read_text(encoding="utf-8"))["state"] == "rejected"
    assert json.loads(s._outcome_path(tmp_path, slot, 2).read_text(encoding="utf-8"))["state"] == "accepted"
    accepted = s._accepted_slot(tmp_path, slot)
    assert accepted and accepted["accepted_provider_call_count"] == 1 and accepted["rejected_retry_count"] == 1 and accepted["batch_attempt_count"] == 2


def test_route_report_drift_is_quarantined_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    s = study()
    s.dry_run(tmp_path)
    slot = s.build_schedule()[0]
    monkeypatch.setattr(s, "_validated_schedule", lambda _root: [slot])
    calls = []
    def wrong_report(command, **kwargs):
        calls.append(command)
        _fake_codex(command, **kwargs)
        return SimpleNamespace(returncode=0, stdout="completed", stderr="provider: openai\nmodel: gpt-5.6-terra\nreasoning effort: high\n")
    with pytest.raises(ValueError, match="provider/model/reasoning"):
        s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=wrong_report)
    assert len(calls) == 1 and not s._outcome_path(tmp_path, slot, 1).exists()
    with pytest.raises(ValueError, match="is ambiguous"):
        s.execute(tmp_path, resume=True, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_codex)


def test_settlement_is_four_state_and_requires_unique_run_and_attachment_receipts(tmp_path: Path):
    s = study()
    s.dry_run(tmp_path)
    schedule = s.build_schedule()
    def record(_root, slot):
        return {"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": slot["expected_verdict"], "expected": slot["expected_verdict"], "correct": True, "run_id": slot["run_id"], "response_sha256": "a" * 64, "command_sha256": "b" * 64, "attachment_sha256": slot["image_input"]["sha256"] if slot["image_input"] else None, "evidence": [], "normalization_audit": [], "accepted_provider_call_count": 1, "rejected_retry_count": 0, "batch_attempt_count": 1}
    settled = s.settle(tmp_path, verifier=record)
    assert settled["decision"] == "PASS_NO_CHANGE" and settled["visual_attachment_slots"] == 72
    public = json.loads((tmp_path / "public-aggregate.json").read_text(encoding="utf-8"))
    assert public["scored_cells"]["total"] + public["not_applicable_diagnostic_cells"]["total"] == 72
