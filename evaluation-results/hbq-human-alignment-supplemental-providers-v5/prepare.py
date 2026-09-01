#!/usr/bin/env python3
"""Prepare one fresh v5 execution root without contacting Nous."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _executor():
    spec = importlib.util.spec_from_file_location("hanna_supplemental_v5_executor_prepare", HERE / "executor.py")
    if spec is None or spec.loader is None:
        raise ValueError("v5 executor is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v4-work-dir", type=Path, required=True)
    parser.add_argument("--route-proof", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    arguments = parser.parse_args()
    proof = json.loads(arguments.route_proof.read_text(encoding="utf-8"))
    if not isinstance(proof, dict):
        raise TypeError("route proof must be a JSON object")
    value = _executor().prepare(arguments.work_dir.resolve(), v4_work_dir=arguments.v4_work_dir.resolve(), route_proof=proof)
    print(json.dumps({"study_id": value["study_id"], "provider_calls_made": 0, "process_launches": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
