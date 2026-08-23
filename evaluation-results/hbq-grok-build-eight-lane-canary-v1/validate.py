"""Validate the compact, public-synthetic eight-lane Grok canary packet."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    snapshot_path = ROOT / manifest["broker_evidence_snapshot"]["file"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == snapshot["schema_version"] == 1
    assert digest(snapshot_path) == manifest["broker_evidence_snapshot"]["sha256"]
    assert manifest["status"] == "completed_provisional_design_input"
    assert manifest["transport"]["host_max_concurrency"] == 8
    assert manifest["timing"]["broker_attempt_started_at"] == "2026-08-23T01:38:40+00:00"
    assert manifest["timing"]["result_envelope_launch_window"] == ["2026-08-23T01:38:40+00:00", "2026-08-23T01:38:41+00:00"]
    assert manifest["timing"]["completed_and_delivered"] == 8
    assert snapshot["evidence_class"] == "credential_safe_queue_route_gate_projection_v1"
    assert snapshot["queue"] == {"completed_count": 8, "delivered_count": 8, "reconcile_required_count": 0}
    gate = snapshot["route_and_gate"]
    assert gate["route"] == manifest["transport"]["route"]
    assert gate["route_hash"] == manifest["transport"]["route_hash"]
    assert gate["route_identity_hash"] == manifest["transport"]["route_identity_hash"]
    assert gate["contract"]["max_concurrency"] == manifest["transport"]["host_max_concurrency"] == 8
    assert gate["host_gate_state"] == "healthy" and gate["zero_charge_only"] is True
    assert len(manifest["results"]) == len(snapshot["items"]) == 8
    snapshot_items = {item["item_id"]: item for item in snapshot["items"]}
    assert len(snapshot_items) == 8
    started, finished = [], []
    for entry in manifest["results"]:
        path = ROOT / entry["file"]
        assert digest(path) == entry["sha256"]
        result = json.loads(path.read_bytes())
        broker_item = snapshot_items[entry["item_id"]]
        assert result["item_id"] == entry["item_id"]
        assert manifest["timing"]["result_envelope_launch_window"][0] <= result["started_at"] <= manifest["timing"]["result_envelope_launch_window"][1]
        assert result["finished_at"] == entry["finished_at"]
        assert broker_item["status"] == "completed"
        assert broker_item["delivery_status"] == "delivered"
        assert broker_item["attempt_count"] == 1
        assert broker_item["attempt"] == {"outcome": "completed", "started_at": manifest["timing"]["broker_attempt_started_at"], "finished_at": result["finished_at"]}
        resolution = result["resolution"]
        assert resolution["route_hash"] == gate["route_hash"]
        assert resolution["route_identity_hash"] == gate["route_identity_hash"]
        assert resolution["zero_charge_only"] is gate["zero_charge_only"]
        assert resolution["contact_cost_evidence_hash"] == gate["cost_evidence_hash"]
        assert resolution["contact_auth_receipt_hash"] == gate["auth_receipt_hash"]
        runtime = result["result"]["runtime"]
        assert result["route"] == {"adapter": "grok_exec", "model": "grok-4.6", "name": "grok-build-grok-4.6"}
        assert runtime["requested_model"] == manifest["transport"]["requested_model"]
        assert runtime["reported_model"] == manifest["transport"]["reported_model"]
        assert runtime["requested_reasoning_effort"] == manifest["transport"]["requested_reasoning_effort"]
        assert runtime["reasoning_attestation"] == manifest["transport"]["reasoning_attestation"]
        assert runtime["execution_policy"] == manifest["transport"]["execution_policy"]
        assert runtime["usage_telemetry"] == broker_item["usage_telemetry"]
        assert set(result["result"]["output"]) == {"summary", "findings", "risks", "recommendations"}
        started.append(result["started_at"])
        finished.append(result["finished_at"])
    assert min(started) == manifest["timing"]["result_envelope_launch_window"][0]
    assert max(started) == manifest["timing"]["result_envelope_launch_window"][1]
    assert min(finished) == manifest["timing"]["finished_at_range"][0]
    assert max(finished) == manifest["timing"]["finished_at_range"][1]
    print("eight-lane Grok canary packet valid")


if __name__ == "__main__":
    main()
