#!/usr/bin/env python3
"""Analyze only the completed Nous Pro successor condition."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path
from typing import Any

from run_study import CONTRACT, HERE, JOURNAL_NAME, _binding, _journal, preflight, schedule_events, sha, validate_flash_trigger


def _v3_analyzer():
    runner_path = HERE.parent / "supplemental-providers-v3" / "run_study.py"
    runner_spec = importlib.util.spec_from_file_location("pro_successor_v3_run_study", runner_path)
    if runner_spec is None or runner_spec.loader is None:
        raise ValueError("Supplemental-provider v3 runner is unavailable")
    runner = importlib.util.module_from_spec(runner_spec)
    runner_spec.loader.exec_module(runner)
    import sys
    sys.modules["run_study"] = runner
    analyzer_spec = importlib.util.spec_from_file_location("pro_successor_v3_analyzer", HERE.parent / "supplemental-providers-v3" / "analyze_study.py")
    if analyzer_spec is None or analyzer_spec.loader is None:
        raise ValueError("Supplemental-provider v3 analyzer is unavailable")
    analyzer = importlib.util.module_from_spec(analyzer_spec)
    analyzer_spec.loader.exec_module(analyzer)
    return analyzer


def _numeric(values: list[float]) -> dict[str, Any]:
    return {"values": values, "mean": statistics.fmean(values), "sample_standard_deviation": statistics.stdev(values), "range": max(values) - min(values)}


def _validate_journal(work: Path) -> None:
    path = work / "providers" / CONTRACT["provider"]["provider_id"] / JOURNAL_NAME
    plans, rows = schedule_events(), _journal(path)
    if len(rows) != len(plans) * 2 or rows[: len(plans)] != plans:
        raise ValueError("Nous Pro successor journal is incomplete or does not bind the frozen schedule")
    for expected, actual in zip(plans, rows[len(plans) :]):
        binding = _binding(work, expected["method_id"], expected["run_id"])
        required = {key: value for key, value in expected.items() if key != "event"}
        if actual.get("event") != "completed" or {key: actual.get(key) for key in required} != required or not binding.is_file() or actual.get("run_binding_sha256") != sha(binding):
            raise ValueError("Nous Pro successor completion journal does not bind its manifest")


def analyze(work: Path, flash_work: Path, output: Path) -> None:
    preflight(flash_work)
    validate_flash_trigger(flash_work)
    _validate_journal(work)
    if output.exists():
        raise ValueError("Refusing to merge into an existing output directory")
    inherited = _v3_analyzer()
    provider, methods = CONTRACT["provider"], CONTRACT["parity"]["methods"]
    by_method = {item["method_id"]: item for item in methods}
    values = {item["method_id"]: [] for item in methods}
    commitments = {item["method_id"]: [] for item in methods}
    receipts: list[str] = []
    rejected: list[str] = []
    for run in range(1, 6):
        value, observed, proof = inherited._hbq(work, provider, run)
        values["hbq"].append(value)
        commitments["hbq"].append(proof)
        receipts.extend(observed)
        for method_id in ("naplan", "cambridge", "oregon"):
            value, observed, proof = inherited._native(work, provider, by_method[method_id], run)
            values[method_id].append(value)
            commitments[method_id].append(proof)
            receipts.append(observed)
            rejected.extend(proof["rejected_receipts"])
    if len(receipts) != 45 or len(receipts) != len(set(receipts)) or len(rejected) != len(set(rejected)) or set(receipts) & set(rejected):
        raise ValueError("Nous Pro successor lacks unique accepted/rejected provider receipts")
    trigger = CONTRACT["flash_execution_trigger"]
    summary = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "provider": {key: provider[key] for key in ("provider_id", "provider", "model", "reasoning", "provisional_reasoning")},
        "flash_execution": {"classification": trigger["classification"], "journal_sha256": trigger["journal_sha256"], "completed_event_count": trigger["completed_event_count"], "semantic_rejection_count": len(trigger["semantic_rejections"]), "flash_score_result_used": False},
        "native_scale_rule": "Native results remain within their named scale; no cross-scale arithmetic.",
        "methods": {key: {"within_scale_repeatability": _numeric(values[key]), "run_commitments": commitments[key]} for key in values},
        "receipt_count": len(receipts),
        "receipt_commitment_sha256": hashlib.sha256(("\n".join(sorted(receipts)) + "\n").encode()).hexdigest(),
    }
    output.mkdir(parents=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    files = {path.name: {"bytes": path.stat().st_size, "sha256": sha(path)} for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps({"format_version": 1, "protocol_contract_sha256": sha(HERE / "study-contract.json"), "files": files}, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--flash-work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.work_dir.resolve(), args.flash_work_dir.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
