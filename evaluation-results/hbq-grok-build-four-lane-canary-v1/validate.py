"""Validate the compact, public-synthetic four-lane Grok canary packet."""
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
    assert manifest["schema_version"] == 1
    assert digest(snapshot_path) == manifest["broker_evidence_snapshot"]["sha256"]
    assert manifest["status"] == "completed_provisional_design_input"
    assert manifest["transport"]["host_max_concurrency"] == 4
    assert manifest["timing"]["shared_started_at"] == "2026-08-23T00:14:33+00:00"
    assert manifest["timing"]["completed_and_delivered"] == 4
    assert len(manifest["results"]) == 4
    assert snapshot["schema_version"] == 1
    assert snapshot["evidence_class"] == "credential_safe_queue_route_gate_projection_v1"
    assert snapshot["queue"] == {
        "completed_count": 4,
        "delivered_count": 4,
        "reconcile_required_count": 0,
    }
    route_and_gate = snapshot["route_and_gate"]
    assert route_and_gate["route"] == manifest["transport"]["route"]
    assert route_and_gate["route_hash"] == manifest["transport"]["route_hash"]
    assert route_and_gate["route_identity_hash"] == manifest["transport"]["route_identity_hash"]
    assert route_and_gate["contract"]["max_concurrency"] == manifest["transport"]["host_max_concurrency"] == 4
    assert route_and_gate["host_gate_state"] == "healthy"
    assert route_and_gate["zero_charge_only"] is True
    assert len(snapshot["items"]) == 4
    snapshot_items = {entry["item_id"]: entry for entry in snapshot["items"]}
    assert len(snapshot_items) == 4
    finished = []
    for entry in manifest["results"]:
        path = ROOT / entry["file"]
        assert digest(path) == entry["sha256"]
        result = json.loads(path.read_text(encoding="utf-8"))
        broker_item = snapshot_items[entry["item_id"]]
        assert result["item_id"] == entry["item_id"]
        assert result["started_at"] == manifest["timing"]["shared_started_at"]
        assert result["finished_at"] == entry["finished_at"]
        assert broker_item["status"] == "completed"
        assert broker_item["delivery_status"] == "delivered"
        assert broker_item["attempt_count"] == 1
        assert broker_item["attempt"] == {
            "outcome": "completed",
            "started_at": result["started_at"],
            "finished_at": result["finished_at"],
        }
        resolution = result["resolution"]
        assert resolution["route_hash"] == route_and_gate["route_hash"]
        assert resolution["route_identity_hash"] == route_and_gate["route_identity_hash"]
        assert resolution["zero_charge_only"] is route_and_gate["zero_charge_only"]
        assert resolution["contact_cost_evidence_hash"] == route_and_gate["cost_evidence_hash"]
        assert resolution["contact_auth_receipt_hash"] == route_and_gate["auth_receipt_hash"]
        runtime = result["result"]["runtime"]
        assert result["route"] == {"adapter": "grok_exec", "model": "grok-4.6", "name": "grok-build-grok-4.6"}
        assert runtime["reported_model"] == manifest["transport"]["reported_model"]
        assert runtime["requested_model"] == manifest["transport"]["requested_model"]
        assert runtime["requested_reasoning_effort"] == manifest["transport"]["requested_reasoning_effort"]
        assert runtime["reasoning_attestation"] == manifest["transport"]["reasoning_attestation"]
        assert runtime["execution_policy"] == manifest["transport"]["execution_policy"]
        assert runtime["usage_telemetry"] == broker_item["usage_telemetry"]
        assert set(result["result"]["output"]) == {"summary", "findings", "risks", "recommendations"}
        finished.append(result["finished_at"])
    assert min(finished) == manifest["timing"]["finished_at_range"][0]
    assert max(finished) == manifest["timing"]["finished_at_range"][1]
    print("four-lane Grok canary packet valid")


if __name__ == "__main__":
    main()
