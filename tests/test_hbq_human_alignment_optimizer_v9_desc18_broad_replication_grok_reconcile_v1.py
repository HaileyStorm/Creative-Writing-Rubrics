from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-reconcile-v1"
LIVE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a")
FREEZE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-desc18-open-freeze-83d7be7-20260901a")


def module():
    spec = importlib.util.spec_from_file_location("_desc18_reconcile_test", PACKAGE / "reconcile.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def route():
    return {"model": "grok-4.6", "reported_model": "grok-4.6-build"}


def response(*, request_id: str = "request", session_id: str = "session", text: str | None = None) -> bytes:
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    output = {"scores": {name: 3 for name in dimensions}, "evidence": {name: "specific textual evidence" for name in dimensions}, "coverage": {name: True for name in dimensions}}
    envelope = {"requestId": request_id, "sessionId": session_id, "stopReason": "end_turn", "structuredOutput": output, "text": text or json.dumps(output, indent=2), "modelUsage": {"grok-4.6-build": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.01}}, "num_turns": 1, "thought": "Direct evaluation reasoning.", "total_cost_usd": 0.01, "total_cost_usd_ticks": 100000000, "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 2, "total_tokens": 15}}
    return json.dumps(envelope, indent=2).encode("utf-8")


def test_native_json_normalization_accepts_formatting_only_and_binds_raw_hash():
    value = module()
    raw = response()
    parsed, identity = value._response(raw, route())
    assert parsed["structuredOutput"]["scores"]["Relevance"] == 3
    assert identity["request_id"] == "request"
    assert value.sha256(raw) != value.sha256(value.canonical(parsed))


def test_native_response_rejects_duplicates_identity_text_schema_and_quality_drift():
    value = module()
    with pytest.raises(ValueError, match="text/schema"):
        value._response(response(text='{"scores":{}}'), route())
    raw = response().replace(b'"requestId": "request"', b'"requestId": "request", "requestId": "request"')
    with pytest.raises(ValueError, match="invalid native response"):
        value._response(raw, route())
    envelope = json.loads(response())
    envelope["structuredOutput"]["evidence"]["Relevance"] = "placeholder"
    envelope["text"] = json.dumps(envelope["structuredOutput"])
    with pytest.raises(ValueError, match="evidence"):
        value._response(json.dumps(envelope).encode(), route())


def test_native_response_rejects_all_zero_placeholder_and_telemetry_drift():
    value = module()
    envelope = json.loads(response())
    envelope["structuredOutput"]["scores"] = {name: 0 for name in envelope["structuredOutput"]["scores"]}
    envelope["text"] = json.dumps(envelope["structuredOutput"])
    with pytest.raises(ValueError, match="all-zero"):
        value._response(json.dumps(envelope).encode(), route())
    envelope = json.loads(response())
    envelope["structuredOutput"]["evidence"]["Relevance"] = "Searching the workspace"
    envelope["text"] = json.dumps(envelope["structuredOutput"])
    with pytest.raises(ValueError, match="evidence"):
        value._response(json.dumps(envelope).encode(), route())
    for field, replacement, match in (("num_turns", 2, "terminal"), ("thought", "placeholder", "thought"), ("total_cost_usd_ticks", -1, "cost")):
        envelope = json.loads(response()); envelope[field] = replacement
        with pytest.raises(ValueError, match=match):
            value._response(json.dumps(envelope).encode(), route())
    envelope = json.loads(response()); envelope["modelUsage"] = {"wrong-model": envelope["modelUsage"]["grok-4.6-build"]}
    with pytest.raises(ValueError, match="model usage"):
        value._response(json.dumps(envelope).encode(), route())
    envelope = json.loads(response()); envelope["modelUsage"]["grok-4.6-build"]["modelCalls"] = 2
    with pytest.raises(ValueError, match="model call"):
        value._response(json.dumps(envelope).encode(), route())
    envelope = json.loads(response()); envelope["usage"]["input_tokens"] = -1
    with pytest.raises(ValueError, match="usage"):
        value._response(json.dumps(envelope).encode(), route())


def test_contract_pins_source_freeze_and_zero_call_boundary():
    value = module()
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["pins"]["source_commit"] == value.SOURCE_COMMIT
    assert contract["pins"]["freeze_commit"] == value.FREEZE_COMMIT
    assert contract["geometry"] == {"historical_process_launches": 64, "provider_calls_during_reconciliation": 0, "reconciled_cells": 64}
    assert contract["native_endpoint_contact_cardinality"] == "unproven"
    assert contract["output_kind"].startswith("reconciled_")


@pytest.mark.skipif(not (LIVE_ROOT.is_dir() and FREEZE_ROOT.is_dir()), reason="immutable desc18 evidence is not present")
def test_real_immutable_root_reconciles_and_replays_without_source_mutation(tmp_path: Path):
    value = module()
    before = {path.relative_to(LIVE_ROOT).as_posix(): value.sha256(value.stable(path)) for path in LIVE_ROOT.rglob("*") if path.is_file()}
    collector = tmp_path / "desc18-reconciled.collector.json"
    result = value.write_collector(output_root=LIVE_ROOT, freeze_root=FREEZE_ROOT, collector_output=collector)
    assert result["cells"] == 64
    assert result["provider_calls_made"] == 0
    assert result["process_launches"] == 0
    assert result["historical_process_launches"] == 64
    assert result["native_endpoint_contact_cardinality"] == "unproven"
    stored = json.loads(collector.read_bytes())
    assert stored["study_id"] == value.STUDY_ID
    assert stored["kind"].startswith("reconciled_")
    assert stored["source_lineage"]["source_study_id"] == value.SOURCE_STUDY_ID
    assert value.replay_collector(output_root=LIVE_ROOT, freeze_root=FREEZE_ROOT, collector_path=collector) == result
    forged = dict(stored)
    forged["route"] = {**stored["route"], "reported_model": "forged"}
    forged_path = tmp_path / "forged-route.json"
    forged_path.write_bytes(value.canonical(forged))
    with pytest.raises(ValueError, match="differs"):
        value.replay_collector(output_root=LIVE_ROOT, freeze_root=FREEZE_ROOT, collector_path=forged_path)
    swapped = json.loads(collector.read_bytes())
    swapped["cells"][0]["identity"], swapped["cells"][1]["identity"] = swapped["cells"][1]["identity"], swapped["cells"][0]["identity"]
    swapped_path = tmp_path / "swapped-identity.json"
    swapped_path.write_bytes(value.canonical(swapped))
    with pytest.raises(ValueError, match="differs"):
        value.replay_collector(output_root=LIVE_ROOT, freeze_root=FREEZE_ROOT, collector_path=swapped_path)
    after = {path.relative_to(LIVE_ROOT).as_posix(): value.sha256(value.stable(path)) for path in LIVE_ROOT.rglob("*") if path.is_file()}
    assert after == before


def test_write_rejects_existing_output_before_reconciliation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    output = tmp_path / "exists.json"
    output.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(value, "reconcile", lambda **_kwargs: pytest.fail("must not reconcile"))
    with pytest.raises(ValueError, match="fresh"):
        value.write_collector(output_root=tmp_path / value.SOURCE_ROOT_NAME, freeze_root=tmp_path / "freeze", collector_output=output)


def test_inventory_rejects_extra_and_wrong_types(tmp_path: Path):
    value = module()
    root = tmp_path / "inventory"
    root.mkdir()
    (root / "expected").write_text("x", encoding="utf-8")
    value._inventory(root, {"expected"})
    (root / "extra").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        value._inventory(root, {"expected"})
    (root / "extra").unlink()
    (root / "expected").unlink()
    (root / "expected").mkdir()
    with pytest.raises(ValueError, match="type"):
        value._inventory(root, {"expected"})
