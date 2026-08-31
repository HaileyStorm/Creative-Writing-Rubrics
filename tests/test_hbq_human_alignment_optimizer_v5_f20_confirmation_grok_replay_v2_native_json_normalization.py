from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-confirmation-grok-replay-v2-native-json-normalization"


def module():
    spec = importlib.util.spec_from_file_location("_confirmation_replay_v2_test", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def response(*, request_id="request", session_id="session", text=None):
    output = {"scores": {dimension: 3 for dimension in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}, "evidence": {dimension: "evidence" for dimension in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}, "coverage": {dimension: True for dimension in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}}
    value = {"requestId": request_id, "sessionId": session_id, "stopReason": "end_turn", "structuredOutput": output, "text": text or json.dumps(output, indent=2), "modelUsage": {}, "num_turns": 1, "thought": "", "total_cost_usd": 0, "total_cost_usd_ticks": 0, "usage": {}}
    return json.dumps(value, indent=2).encode()


def test_accepts_whitespace_and_order_variance_but_binds_raw_hash():
    value = module()
    raw = response()
    result = value._response(raw, {"request_id": "request", "session_id": "session"})
    assert result["scores"]["Relevance"] == 3.0
    assert result["raw_sha256"] == value.sha256(raw)


def test_rejects_semantic_identity_text_and_schema_tampering():
    value = module()
    identity = {"request_id": "request", "session_id": "session"}
    with pytest.raises(ValueError, match="identity"):
        value._response(response(request_id="other"), identity)
    with pytest.raises(ValueError, match="text/schema"):
        value._response(response(text='{"scores":{}}'), identity)
    malformed = response().replace(b'"end_turn"', b'"other"')
    with pytest.raises(ValueError, match="terminal state"):
        value._response(malformed, identity)
    outer = json.loads(response())
    outer["unexpected"] = "semantic drift"
    with pytest.raises(ValueError, match="identity or terminal state"):
        value._response(json.dumps(outer, indent=2).encode(), identity)


def test_contract_pins_the_complete_v1_collector_and_preserves_measurement_boundary():
    value = module()
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["pins"]["collector_sha256"] == value.COLLECTOR_SHA256
    assert contract["authority"] == {"confirmation": "measurement_only", "promotion": "none", "runtime": "none", "selection": "none", "sol": "out_of_scope"}


def test_real_pinned_replay_matches_checked_result_when_inputs_are_supplied():
    root = os.environ.get("CWR_CONFIRMATION_GROK_ROOT")
    collector = os.environ.get("CWR_CONFIRMATION_GROK_COLLECTOR")
    if not root or not collector:
        pytest.skip("real immutable confirmation evidence was not supplied")
    value = module()
    assert value.canonical(value.replay(output_root=Path(root), collector_path=Path(collector))) == (PACKAGE / "result.json").read_bytes()
