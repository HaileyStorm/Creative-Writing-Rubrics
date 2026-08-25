from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-free-verse-necessity-scope-ablation-v1-public-result-v1"


def load_verifier():
    spec = importlib.util.spec_from_file_location("necessity_scope_public_result", PACKAGE / "verify_output.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_aggregate_result_is_private_safe_and_negative_nonpromotion() -> None:
    value = load_verifier().verify()
    assert value["accepted_provider_calls"] == value["planned_provider_calls"] == 36
    assert value["classification"] == "VALID_EXECUTION_NEGATIVE_DISCRIMINATION_NO_PROMOTION"
    assert value["necessity_arm"]["call_level_expected_matches"] == 18
    assert value["paired_arms"]["calls_with_same_verdict"] == 16


@pytest.mark.parametrize("field,value", [("accepted_provider_calls", 35), ("question_id", "private"), ("opaque_private_receipt_and_settlement_commitment_sha256", "0" * 64)])
def test_aggregate_result_fails_closed_on_count_or_private_detail(tmp_path, field, value) -> None:
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
