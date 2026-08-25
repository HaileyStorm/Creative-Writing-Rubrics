"""Provider-free verifier for a settled figurative isolated-anchor pilot."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
FROZEN_MANIFEST_SHA256 = "001a8974c6c6ae010f7d0bd7f93fef957868644665eca4d54de6f32dd481ccf9"
CLAIM_SHA256 = "02141f3c8a9ba5ddd6135110f0e0dfa9c0f4d92791870d16cf6fbf0514d99442"
SETTLEMENT_SHA256 = "0e2802d0b2cc95cd4cb52d824478091a577fb3ad43fb6cb140d29f10ac683460"
PUBLIC_AGGREGATE_SHA256 = "08ee680929cb8256339c1f5af7e43820581b8b53d3367c6d94414a512f020099"
TERMINAL_SHA256 = "f4177a1090765551c3385b1b8649c939263f905df60a89c15e0f7f17e481ce77"
CONTROL_GATE_SHA256 = "7df361821743005bf2a27aa71c4ba7dd8ce951c4c1f0639275dd466858777e24"


def _load_study():
    spec = importlib.util.spec_from_file_location("figurative_anchor_settled_source", ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Settled source executor cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


study = _load_study()


def _require_hash(path: Path, expected: str, label: str) -> None:
    if study.sha256_file(path) != expected:
        raise ValueError(f"{label} hash drifted")


def _expected_public(settlement: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "study_id": study.STUDY_ID,
        "decision": settlement["decision"],
        "completed_slots": settlement["completed_slots"],
        "planned_slots": study.SLOTS,
        "controls": settlement["controls"],
        "target": settlement["target"],
        "dspy_eligible": settlement["dspy_eligible"],
        "target_treatment": "experimental_not_promoted",
        "promotion": "none",
    }


def _expected_settlement(
    schedule: list[dict[str, Any]],
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    controls = [slot for slot in schedule if slot["stage"] == "control"]
    targets = [slot for slot in schedule if slot["stage"] == "target"]
    control_records = records[: study.CONTROL_SLOTS]
    target_records = records[study.CONTROL_SLOTS :]
    controls_summary = {
        leaf: {
            "correct": sum(
                bool(record["correct"])
                for record, slot in zip(control_records, controls, strict=True)
                if slot["leaf_id"] == leaf
            ),
            "total": 6,
            "passed": all(
                bool(record["correct"])
                for record, slot in zip(control_records, controls, strict=True)
                if slot["leaf_id"] == leaf
            ),
        }
        for leaf in study.CONTROLS
    }
    cells: dict[str, list[bool]] = defaultdict(list)
    cell_labels: dict[str, str] = {}
    for record, slot in zip(target_records, targets, strict=True):
        artifact_id = str(slot["artifact_id"])
        cells[artifact_id].append(bool(record["correct"]))
        cell_labels[artifact_id] = str(slot["case_id"])
    if len(cells) != 2 or any(len(items) != 3 for items in cells.values()):
        raise ValueError("Settled target cell geometry drifted")
    named_cells = {
        cell_labels[artifact]: {"correct": sum(values), "total": len(values)}
        for artifact, values in cells.items()
    }
    target_correct = sum(item["correct"] for item in named_cells.values())
    mixed_cells = sum(1 for item in named_cells.values() if 0 < item["correct"] < item["total"])
    stable_miss_cells = sum(1 for item in named_cells.values() if item["correct"] == 0)
    if target_correct == study.TARGET_SLOTS:
        decision, dspy = "MANUAL_TARGET_ANCHOR_PILOT_PASS", False
    elif mixed_cells:
        decision, dspy = "MANUAL_TARGET_UNSTABLE_NO_GO_DSPY_ELIGIBLE", True
    else:
        decision, dspy = "MANUAL_TARGET_STABLE_MISS_NO_GO_DSPY_ELIGIBLE", True
    settlement = {
        "format_version": 1,
        "study_id": study.STUDY_ID,
        "decision": decision,
        "completed_slots": study.SLOTS,
        "planned_slots": study.SLOTS,
        "controls": controls_summary,
        "target": {
            "executed": True,
            "correct": target_correct,
            "total": study.TARGET_SLOTS,
            "mixed_cells": mixed_cells,
            "stable_miss_cells": stable_miss_cells,
        },
        "dspy_eligible": dspy,
        "dspy_trigger": "controls_12_of_12_and_valid_target_below_6_of_6" if dspy else None,
        "baseline_comparison": "none",
        "promotion": "none",
    }
    return settlement, named_cells


def verify_settled(private_root: str | Path) -> dict[str, Any]:
    root = study._root(private_root)
    schedule = study.build_schedule(validate=False)
    manifest_path = root / "study-manifest.v1.json"
    _require_hash(manifest_path, FROZEN_MANIFEST_SHA256, "Frozen study manifest")
    manifest = study._load_json(manifest_path)
    if (
        manifest.get("study_id") != study.STUDY_ID
        or manifest.get("planned_slots") != study.SLOTS
        or manifest.get("slots") != [study._public_slot(slot) for slot in schedule]
    ):
        raise ValueError("Frozen study manifest identity or schedule drifted")
    authentication = study._load_json(root / "receipts" / "subscription-authentication.v1.json")
    expected_runtime = study._base._runtime_schedule(root, schedule)
    aggregate = study.sha256_bytes(
        study.canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected_runtime})
    )
    stored_runtime = study._load_json(root / "runtime-schedule.v1.json")
    if stored_runtime != {
        "format_version": 1,
        "study_id": study.STUDY_ID,
        "provider_calls": 0,
        "slots": expected_runtime,
        "rendered_prompt_aggregate_sha256": aggregate,
    }:
        raise ValueError("Frozen runtime schedule drifted")
    disclosure = study._base._disclosure(expected_runtime, root, authentication)
    if study._load_json(root / "receipts" / "preexecution-disclosure.v1.json") != disclosure:
        raise ValueError("Preexecution disclosure drifted")
    claim_path = root / "execution-claim.v1.json"
    _require_hash(claim_path, CLAIM_SHA256, "Execution claim")
    if study._load_json(claim_path) != study._base._execution_claim_payload(root):
        raise ValueError("Execution claim no longer binds the frozen inputs")
    if study._load_json(root / "receipts" / "zero-charge-acknowledgement.v1.json") != study._zero_charge_receipt(authentication):
        raise ValueError("Zero-charge acknowledgement drifted")
    records = [study._verify_slot(root, slot) for slot in expected_runtime]
    if len({record["slot_id"] for record in records}) != study.SLOTS:
        raise ValueError("Accepted slot identity drifted")
    if len({record["session_id_sha256"] for record in records}) != study.SLOTS:
        raise ValueError("Provider session identity is not unique per accepted slot")
    if len({record["checkpoint_chain_head_sha256"] for record in records}) != study.SLOTS:
        raise ValueError("Checkpoint-chain identity is not unique per accepted slot")
    control_records = records[: study.CONTROL_SLOTS]
    gate_path = root / "control-gate.v1.json"
    _require_hash(gate_path, CONTROL_GATE_SHA256, "Control gate")
    if study._load_json(gate_path) != study._control_gate_payload(control_records):
        raise ValueError("Control gate does not bind the revalidated controls")
    expected_settlement, named_cells = _expected_settlement(expected_runtime, records)
    settlement_path = root / "anchor-pilot-settlement.v1.json"
    _require_hash(settlement_path, SETTLEMENT_SHA256, "Settlement")
    if study._load_json(settlement_path) != expected_settlement:
        raise ValueError("Settlement does not match the revalidated accepted slots")
    aggregate_path = root / "public-aggregate.v1.json"
    _require_hash(aggregate_path, PUBLIC_AGGREGATE_SHA256, "Public aggregate")
    if study._load_json(aggregate_path) != _expected_public(expected_settlement):
        raise ValueError("Public aggregate does not match the settlement")
    terminal_path = root / "terminal-sidecar.v5.json"
    _require_hash(terminal_path, TERMINAL_SHA256, "Terminal sidecar")
    terminal = study._load_json(terminal_path)
    if terminal != {
        "format": "terminal_sidecar_v1",
        "format_version": 5,
        "study_id": study.STUDY_ID,
        "decision": expected_settlement["decision"],
        "completed_slots": study.SLOTS,
        "planned_slots": study.SLOTS,
        "settlement_sha256": SETTLEMENT_SHA256,
        "promotion": "none",
    }:
        raise ValueError("Terminal sidecar does not bind the settlement")
    return {
        "study_id": study.STUDY_ID,
        "state": "verified_settled_provider_free",
        "provider_calls": 0,
        "completed_slots": study.SLOTS,
        "controls_correct": study.CONTROL_SLOTS,
        "target_correct": expected_settlement["target"]["correct"],
        "target_cells": named_cells,
        "decision": expected_settlement["decision"],
        "claim_sha256": CLAIM_SHA256,
        "settlement_sha256": SETTLEMENT_SHA256,
        "public_aggregate_sha256": PUBLIC_AGGREGATE_SHA256,
        "promotion": "none",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify_settled(args.private_root), sort_keys=True))


if __name__ == "__main__":
    main()
