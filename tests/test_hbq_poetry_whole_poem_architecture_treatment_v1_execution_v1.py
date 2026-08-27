from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-whole-poem-architecture-treatment-v1-execution-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("whole_poem_architecture_execution", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STUDY = load_study()


ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived whole-poem execution mechanics require frozen 4ce1204 production bytes; current bindings have advanced."
)


def study():
    return STUDY


def receipt(slot):
    return {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "prompt_sha256": slot["prompt_sha256"], "fixture_sha256": slot["fixture_sha256"]}


def payload(slot, verdict="YES"):
    quote = next(line for line in slot["artifact_text"].splitlines() if line.strip())
    return {"verdicts": [{"question_id": "scope.poetry_poem.form", "verdict": verdict, "confidence": 0.75, "evidence": [{"kind": "exact_quote", "reference": slot["artifact_name"], "exact_quote": quote, "summary": None}], "note": "Public synthetic exact-quote check."}]}


def test_current_checkout_fails_closed_and_schedule_keeps_exact_geometry():
    s = study()
    with pytest.raises(ValueError, match="Pinned bound paths drifted from the exact Git parent"):
        s.validate_package()
    slots = s.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 42
    assert [slot["arm"] for slot in slots[:21]] == ["current_wording"] * 21
    assert [slot["arm"] for slot in slots[21:]] == ["candidate_architecture_wording"] * 21
    assert [(slot["case_id"], slot["repeat"]) for slot in slots[:21]] == [(slot["case_id"], slot["repeat"]) for slot in slots[21:]]
    assert all("expected" not in key for slot in slots for key in slot)
    assert s.contract()["execution"]["api_or_paid_fallback"] == "forbidden"
    assert s.contract()["predecessor"]["pinned_commit"] == "4ce1204d8dd97feff2c7bd88237e265fac742adb"
    with pytest.raises(ValueError, match="outside"):
        s._external_root(s.REPOSITORY / "forbidden-private-root")


@ARCHIVED_OLD_RUNTIME
def test_prepare_uses_external_root_and_keeps_expected_labels_out_of_prompts_and_manifest(tmp_path: Path):
    s = study()
    result = s.prepare(tmp_path)
    assert result["provider_calls"] == 0 and result["rendered_prompts"] == 42
    manifest = (tmp_path / "controller-manifest.json").read_text(encoding="utf-8")
    prompts = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "rendered-prompts").glob("*.txt"))
    assert "candidate_expected" not in manifest and "expected_verdict" not in manifest
    assert "candidate_expected" not in prompts and "expected_verdict" not in prompts
    assert len(json.loads((tmp_path / "sealed-candidate-ledger.v1.json").read_text(encoding="utf-8"))["rows"]) == 7
    with pytest.raises(ValueError, match="outside"):
        s.prepare(s.REPOSITORY / "forbidden-private-root")


@ARCHIVED_OLD_RUNTIME
def test_preclaim_rejects_any_prepared_prompt_or_input_drift(tmp_path: Path):
    s = study(); s.prepare(tmp_path)
    slot = s.build_schedule()[0]
    prompt = tmp_path / "rendered-prompts" / f"{slot['slot_id']}.txt"
    prompt.write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="rendered-prompts bytes drifted"):
        s.claim_slot(tmp_path, slot["slot_id"])


@ARCHIVED_OLD_RUNTIME
def test_one_attempt_and_control_technical_failure_stop_before_targets(tmp_path: Path):
    s = study(); s.prepare(tmp_path)
    first, target = s.build_schedule()[0], s.build_schedule()[21]
    assert s.claim_slot(tmp_path, first["slot_id"])["attempt"] == 1
    invalid = payload(first); invalid["verdicts"][0]["evidence"][0]["exact_quote"] = "not present"
    assert s.record_response(tmp_path, first["slot_id"], receipt(first), invalid)["state"] == "terminal_technical_failure"
    assert s.technical_status(tmp_path)["status"] == "TECHNICAL_INCOMPLETE"
    with pytest.raises(ValueError, match="Frozen sequence"):
        s.claim_slot(tmp_path, target["slot_id"])
    with pytest.raises(ValueError, match="retry/resume"):
        s.claim_slot(tmp_path, first["slot_id"])
    with pytest.raises(ValueError, match="all 42"):
        s.settle(tmp_path)


def test_response_receipt_schema_grounding_and_singleton_validation():
    s = study()
    slot = s.build_schedule()[0]
    assert s._validate_response(slot, receipt(slot), payload(slot))["question_id"] == "scope.poetry_poem.form"
    bad = receipt(slot); bad["reasoning"] = "medium"
    with pytest.raises(ValueError, match="receipt drifted"):
        s._validate_response(slot, bad, payload(slot))
    grounded = payload(slot); grounded["verdicts"][0]["evidence"][0]["exact_quote"] = "not present"
    with pytest.raises(ValueError, match="fixture-grounded"):
        s._validate_response(slot, receipt(slot), grounded)


@ARCHIVED_OLD_RUNTIME
def test_candidate_semantic_miss_is_recorded_without_stopping_later_targets(tmp_path: Path):
    s = study(); s.prepare(tmp_path)
    slots = s.build_schedule()
    for slot in slots[:21]:
        s.claim_slot(tmp_path, slot["slot_id"])
        assert s.record_response(tmp_path, slot["slot_id"], receipt(slot), payload(slot))["state"] == "terminal_valid"
    missed, next_target = slots[21:23]
    s.claim_slot(tmp_path, missed["slot_id"])
    assert s.record_response(tmp_path, missed["slot_id"], receipt(missed), payload(missed, "NO"))["state"] == "terminal_valid"
    assert s.claim_slot(tmp_path, next_target["slot_id"])["slot_id"] == next_target["slot_id"]


@ARCHIVED_OLD_RUNTIME
def test_full_42_settlement_revalidates_every_terminal_and_rejects_tampering(tmp_path: Path):
    s = study(); s.prepare(tmp_path)
    expected = {row["case_id"]: row["expected_verdict"] for row in s._candidate_ledger()["rows"]}
    slots = s.build_schedule()
    for slot in slots:
        verdict = expected[slot["case_id"]]
        if slot["arm"] == "current_wording" and slot["case_id"] == "interchangeable_architecture":
            verdict = "YES"
        response = payload(slot, verdict)
        terminal = {"format_version": 1, "study_id": s.STUDY_ID, "slot_id": slot["slot_id"], "attempt": 1, "state": "terminal_valid", "response_sha256": s.sha256_bytes(s.canonical_json(response)), "receipt": receipt(slot), "payload": response, "verdict": response["verdicts"][0]}
        s._write_immutable(tmp_path / "terminals" / f"{slot['slot_id']}.json", s.canonical_json(terminal))
    settlement = s.settle(tmp_path)
    assert settlement["decision"] == "GO_TO_BROADER_VALIDATION"
    assert settlement["candidate_correct"] == settlement["candidate_total"] == 21
    terminal_path = tmp_path / "terminals" / f"{slots[0]['slot_id']}.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["payload"]["verdicts"][0]["verdict"] = "NO"
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="response hash drifted"):
        s.technical_status(tmp_path)
    with pytest.raises(ValueError, match="response hash drifted"):
        s.settle(tmp_path)


def test_semantic_decision_contract_has_no_current_label_scoring():
    s = study()
    cases = [case["case_id"] for case in s.predecessor().load_corpus()["cases"]]
    correct = {case: [True, True, True] for case in cases}
    candidate = {case: ["YES", "YES", "YES"] for case in cases}
    controls = {case: ["YES", "YES", "YES"] for case in cases}
    assert s.classify(correct, controls, candidate) == ("NO_GO_NO_CLEAR_DISCRIMINATION", [])
    controls[cases[0]] = ["NO", "NO", "NO"]
    assert s.classify(correct, controls, candidate) == ("GO_TO_BROADER_VALIDATION", [cases[0]])
    correct[cases[-1]] = [True, False, True]
    assert s.classify(correct, controls, candidate)[0] == "NO_GO_CANDIDATE"


def test_cli_and_source_have_no_provider_execution_surface():
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "--execute" not in text
        assert "import requests" not in text and "from requests" not in text
