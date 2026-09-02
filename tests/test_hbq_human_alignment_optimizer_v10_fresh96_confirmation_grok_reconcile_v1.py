from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1"
LIVE = Path(r"C:\Users\Haile\Documents\cwr-hanna-v10-fresh96-confirmation-grok-1c10bae-20260901-r1")
FREEZE = Path(r"C:\Users\Haile\Documents\cwr-hanna-v10-fresh96-confirmation-freeze-1c10bae-20260901-r1")


def module():
    spec = importlib.util.spec_from_file_location("v10_reconcile", PACKAGE / "reconcile.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def test_contract_pins_measurement_only_and_zero_call_boundary():
    value = module()
    assert value.contract()["geometry"] == {"historical_process_launches": 64, "provider_calls_during_reconciliation": 0, "reconciled_cells": 64}
    assert value.contract()["authority"]["confirmation"] == "measurement_only"


def test_readme_is_aggregate_only_and_does_not_claim_promotion():
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "64 cells" in readme and "zero provider calls" in readme and "measurement-only" in readme
    assert "C:\\Users\\" not in readme and "request_id" not in readme and "session_id" not in readme
    assert "no Sol result, selection, promotion, runtime, or endpoint-pooling" in readme


@pytest.mark.skipif(not (LIVE.is_dir() and FREEZE.is_dir()), reason="immutable V10 r1 evidence is absent")
def test_real_r1_reconciles_read_only_and_preserves_raw_receipts():
    value = module(); helper = value.helper()
    before = {path.relative_to(LIVE).as_posix(): helper.sha256(helper.stable(path)) for path in LIVE.rglob("*") if path.is_file()}
    result = value.reconcile(output_root=LIVE, freeze_root=FREEZE)
    assert result["kind"] == "reconciled_64_fresh96_future_confirmation_grok_receipts_cardinality_unproven"
    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert result["historical_process_launches"] == 64
    assert len(result["cells"]) == len({row["identity"]["request_id"] for row in result["cells"]}) == 64
    assert all(row["effective_settings"]["tools_enabled"] is False for row in result["cells"])
    assert all(helper.sha256(__import__("base64").b64decode(row["native_response_base64"])) == row["native_response_sha256"] for row in result["cells"])
    after = {path.relative_to(LIVE).as_posix(): helper.sha256(helper.stable(path)) for path in LIVE.rglob("*") if path.is_file()}
    assert after == before


@pytest.mark.skipif(not LIVE.is_dir(), reason="immutable V10 r1 evidence is absent")
def test_narrow_evidence_rejection_keeps_legitimate_placeholder_words_but_rejects_exact_placeholder():
    value = module(); helper = value.helper(); root = None
    for candidate in LIVE.iterdir():
        if candidate.is_dir() and candidate.name != ".claims":
            raw = (candidate / "responses" / "batch-0001.attempt-0001.grok.envelope.json").read_bytes()
            envelope = json.loads(raw)
            if any("placeholder" in text.casefold() and text.casefold().strip() != "placeholder" for text in envelope["structuredOutput"]["evidence"].values()):
                root = candidate; break
    assert root is not None
    route = json.loads((root / "prepared.json").read_text(encoding="utf-8"))["route"]
    raw = (root / "responses" / "batch-0001.attempt-0001.grok.envelope.json").read_bytes()
    envelope, _identity = value._response(helper, raw, route)
    envelope["structuredOutput"]["evidence"]["Relevance"] = "placeholder"
    envelope["text"] = json.dumps(envelope["structuredOutput"])
    with pytest.raises(ValueError, match="evidence"):
        value._response(helper, json.dumps(envelope).encode(), route)


@pytest.mark.skipif(not LIVE.is_dir(), reason="immutable V10 r1 evidence is absent")
def test_native_response_rejects_duplicate_schema_telemetry_and_workspace_search_drift():
    value = module(); helper = value.helper(); root = next(path for path in LIVE.iterdir() if path.is_dir() and path.name != ".claims")
    route = json.loads((root / "prepared.json").read_text(encoding="utf-8"))["route"]
    raw = (root / "responses" / "batch-0001.attempt-0001.grok.envelope.json").read_bytes()
    with pytest.raises(ValueError, match="invalid native response"):
        value._response(helper, raw.replace(b'"requestId"', b'"requestId","requestId"', 1), route)
    envelope = json.loads(raw); envelope["usage"]["input_tokens"] = -1
    with pytest.raises(ValueError, match="usage"):
        value._response(helper, json.dumps(envelope).encode(), route)
    envelope = json.loads(raw); envelope["structuredOutput"]["evidence"]["Relevance"] = "Searching the workspace"
    envelope["text"] = json.dumps(envelope["structuredOutput"])
    with pytest.raises(ValueError, match="evidence"):
        value._response(helper, json.dumps(envelope).encode(), route)


def test_existing_collector_is_rejected_before_reconciliation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module(); output = tmp_path / "occupied.json"; output.write_text("occupied", encoding="utf-8")
    monkeypatch.setattr(value, "reconcile", lambda **_kwargs: pytest.fail("must not reconcile"))
    with pytest.raises(ValueError, match="fresh"):
        value.write_collector(output_root=tmp_path / value.SOURCE_ROOT_NAME, freeze_root=tmp_path / "freeze", collector_output=output)


@pytest.mark.skipif(not (LIVE.is_dir() and FREEZE.is_dir()), reason="immutable V10 r1 evidence is absent")
def test_write_collector_uses_fresh_external_path_and_replays(tmp_path: Path):
    value = module(); collector = tmp_path / "v10-r1.collector.json"
    result = value.write_collector(output_root=LIVE, freeze_root=FREEZE, collector_output=collector)
    assert collector.is_file() and result["cells"] == 64
    assert value.replay_collector(output_root=LIVE, freeze_root=FREEZE, collector_path=collector) == result
