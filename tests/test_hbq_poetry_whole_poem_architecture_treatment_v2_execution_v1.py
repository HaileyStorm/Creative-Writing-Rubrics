from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-whole-poem-architecture-treatment-v2-execution-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("whole_poem_architecture_v2_execution", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STUDY = load_study()


ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived whole-poem execution mechanics require frozen 4ce1204 production bytes; current bindings have advanced."
)


def receipt(slot):
    return {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "prompt_sha256": slot["prompt_sha256"], "fixture_sha256": slot["fixture_sha256"]}


def payload(slot, verdict="YES"):
    quote = next(line for line in slot["artifact_text"].splitlines() if line.strip())
    return {"verdicts": [{"question_id": "scope.poetry_poem.form", "verdict": verdict, "confidence": 0.75, "evidence": [{"kind": "exact_quote", "reference": slot["artifact_name"], "exact_quote": quote, "summary": None}], "note": "Public synthetic exact-quote check."}]}


def test_current_checkout_fails_closed_and_schedule_keeps_exact_geometry() -> None:
    s = STUDY
    with pytest.raises(ValueError, match="Pinned bound paths drifted from the exact Git parent"):
        s.validate_package()
    slots = s.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 42
    assert [slot["arm"] for slot in slots[:21]] == ["current_wording"] * 21
    assert [slot["arm"] for slot in slots[21:]] == ["candidate_architecture_wording"] * 21
    assert [(slot["case_id"], slot["repeat"]) for slot in slots[:21]] == [(slot["case_id"], slot["repeat"]) for slot in slots[21:]]
    assert all("expected" not in key for slot in slots for key in slot)
    assert s.contract()["execution"] == {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "zero_paid_only": True, "api_or_paid_fallback": "forbidden", "provider_calls_authorized_by_this_freeze": False, "one_physical_attempt_per_slot": True, "retry": "forbidden", "replacement": "forbidden", "resampling": "forbidden", "extension": "forbidden", "resume": "forbidden"}
    with pytest.raises(ValueError, match="outside"):
        s._external_root(s.REPOSITORY / "forbidden-private-root")


@ARCHIVED_OLD_RUNTIME
def test_prepare_is_external_and_keeps_labels_out_of_prompts_and_manifest(tmp_path: Path) -> None:
    s = STUDY
    with tempfile.TemporaryDirectory(prefix="hbq-architecture-v2-") as directory:
        private_root = Path(directory)
        result = s.prepare(private_root)
        assert result["provider_calls"] == 0 and result["rendered_prompts"] == 42
        manifest = (private_root / "controller-manifest.json").read_text(encoding="utf-8")
        prompts = "\n".join(path.read_text(encoding="utf-8") for path in (private_root / "rendered-prompts").glob("*.txt"))
        assert "candidate_expected" not in manifest and "expected_verdict" not in manifest
        assert "candidate_expected" not in prompts and "expected_verdict" not in prompts
        assert len(json.loads((private_root / "sealed-candidate-ledger.v1.json").read_text(encoding="utf-8"))["rows"]) == 7
    with pytest.raises(ValueError, match="outside"):
        s.prepare(s.REPOSITORY / "forbidden-private-root")


@ARCHIVED_OLD_RUNTIME
def test_one_attempt_and_control_failure_stop_before_targets(tmp_path: Path) -> None:
    s = STUDY; s.prepare(tmp_path)
    first, target = s.build_schedule()[0], s.build_schedule()[21]
    assert s.claim_slot(tmp_path, first["slot_id"])["attempt"] == 1
    invalid = payload(first); invalid["verdicts"][0]["evidence"][0]["exact_quote"] = "not present"
    assert s.record_response(tmp_path, first["slot_id"], receipt(first), invalid)["state"] == "terminal_technical_failure"
    assert s.technical_status(tmp_path)["status"] == "TECHNICAL_INCOMPLETE"
    with pytest.raises(ValueError, match="Frozen sequence"):
        s.claim_slot(tmp_path, target["slot_id"])
    with pytest.raises(ValueError, match="retry/resume"):
        s.claim_slot(tmp_path, first["slot_id"])


@ARCHIVED_OLD_RUNTIME
def test_full_settlement_revalidates_all_terminals_and_never_promotes(tmp_path: Path) -> None:
    s = STUDY; s.prepare(tmp_path)
    expected = {row["case_id"]: row["expected_verdict"] for row in s._candidate_ledger()["rows"]}
    slots = s.build_schedule()
    for slot in slots:
        verdict = expected[slot["case_id"]]
        response = payload(slot, verdict)
        terminal = {"format_version": 1, "study_id": s.STUDY_ID, "slot_id": slot["slot_id"], "attempt": 1, "state": "terminal_valid", "response_sha256": s.sha256_bytes(s.canonical_json(response)), "receipt": receipt(slot), "payload": response, "verdict": response["verdicts"][0]}
        s._write_immutable(tmp_path / "terminals" / f"{slot['slot_id']}.json", s.canonical_json(terminal))
    settlement = s.settle(tmp_path)
    assert settlement["decision"] == "NO_GO_NO_CLEAR_DISCRIMINATION"
    assert settlement["candidate_correct"] == settlement["candidate_total"] == 21
    assert settlement["promotion"] == "none"
    terminal_path = tmp_path / "terminals" / f"{slots[0]['slot_id']}.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8")); terminal["payload"]["verdicts"][0]["verdict"] = "NO"
    terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="response hash drifted"):
        s.settle(tmp_path)


def test_cli_and_source_have_no_provider_execution_surface() -> None:
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "--execute" not in text
        assert "import requests" not in text and "from requests" not in text
