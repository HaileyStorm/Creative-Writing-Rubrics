from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-poetry-whole-poem-architecture-treatment-v1-public-result-v1"


def load_verifier():
    spec = importlib.util.spec_from_file_location("whole_poem_public_result", PACKAGE / "verify_output.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_public_aggregate_is_complete_negative_and_nonpromoting() -> None:
    value = load_verifier().verify()
    assert value["protocol_geometry"] == {"candidate_calls": 21, "current_calls": 21, "planned_calls": 42, "valid_terminals": 42}
    assert value["candidate_outcome"] == {"correct": 13, "total": 21}
    assert value["decision"] == "NO_GO_CANDIDATE"
    assert value["promotion"] == "none"
    assert value["stable_3_of_3_arm_gap_case_ids"] == ["line_excerpt", "missing_poem_coverage", "single_unit_poem"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("decision", "GO_TO_BROADER_VALIDATION"), ("slot_id", "not-public")],
)
def test_public_aggregate_fails_closed_on_decision_or_restricted_field(tmp_path, field, value) -> None:
    verifier = load_verifier()
    payload = json.loads((PACKAGE / "aggregate.v1.json").read_text(encoding="utf-8"))
    payload[field] = value
    replacement = tmp_path / "aggregate.v1.json"
    replacement.write_text(json.dumps(payload), encoding="utf-8")
    original = verifier.AGGREGATE
    verifier.AGGREGATE = replacement
    try:
        with pytest.raises(ValueError):
            verifier.verify()
    finally:
        verifier.AGGREGATE = original
