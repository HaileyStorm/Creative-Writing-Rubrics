#!/usr/bin/env python3
"""Verify batch-8 raw transport evidence without reading scores or HANNA labels."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, _json_bytes, _load_checkpoints
from study import CONTRACT, _parent_v2, fingerprint, input_folder, load_frozen, read_json, runtime_bindings, sha


def _timely(value: Any) -> bool: return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < CONTRACT["transport_pilot"]["maximum_completion_seconds_exclusive"]


def _v2_raw_verifier() -> Any:
    """Load the pinned v2 verifier without retaining its historical bare import alias."""
    parent = _parent_v2()
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("hanna_supplemental_v3_raw_v2", parent.HERE / "verify_transport_pilot.py")
    if spec is None or spec.loader is None: raise ValueError("v2 raw verifier is unavailable")
    module = importlib.util.module_from_spec(spec); previous = sys.modules.get("study"); sys.modules[spec.name] = module; sys.modules["study"] = parent
    try: spec.loader.exec_module(module)
    finally:
        if previous is None: sys.modules.pop("study", None)
        else: sys.modules["study"] = previous
    return module


def _expected_prompt(folder: Path, cell: Mapping[str, Any]) -> bytes:
    return _v2_raw_verifier()._expected_prompt(folder, cell)


def _raw_transport(run: Path, checkpoint: Mapping[str, Any], prompt: bytes) -> dict[str, Any]:
    """Use the hash-pinned v2 raw-evidence verifier; provider/prompt semantics are identical."""
    module = _v2_raw_verifier()
    return module._raw_transport(run, checkpoint, prompt)


def _invocation(work: Path) -> dict[str, Any]:
    from run_transport_pilot import _invocation
    frozen = load_frozen(work); record = read_json(work / "pilot-invocation.json")
    try: expected = _invocation(work, frozen, 600)
    except ValueError as exc: raise ValueError("Pilot invocation record does not bind v3") from exc
    if record != expected: raise ValueError("Pilot invocation record does not bind v3")
    return record


def _claim(work: Path) -> dict[str, Any]:
    path = work / "pilot-execution-claim.json"
    if not path.is_file(): raise ValueError("Pilot exclusive execution claim is missing")
    record = read_json(path); expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_score_blind_pilot_execution", "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"), "runtime": runtime_bindings()}
    if any(record.get(key) != value for key, value in expected.items()) or set(record) != {*expected, "pid"} or isinstance(record.get("pid"), bool) or not isinstance(record.get("pid"), int) or record["pid"] < 1: raise ValueError("Pilot exclusive execution claim is forged or unbound")
    return record


def _verify_cell(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    receipt_path = work / "pilot-receipts" / f"{cell['cell_id']}.json"; receipt = read_json(receipt_path); run = work / "runs" / "pilot" / str(cell["cell_id"])
    manifest = read_json(run / "run.json"); configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(configuration)).hexdigest(): raise ValueError("Pilot run manifest is malformed")
    folder = input_folder(frozen, cell); inputs = cell["inputs"]
    compact = lambda value: {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None
    expected = {"provider": "nous", "model": CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 8, "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "bundle_id": "prose.short_story", "question_ids": cell["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True}
    if any(configuration.get(key) != value for key, value in expected.items()) or compact(configuration.get("artifact")) != inputs["source.md"] or [compact(item) for item in configuration.get("contexts", [])] != [inputs["prompt.md"]] or compact(configuration.get("task_contract")) != inputs["task-contract.json"]: raise ValueError("Pilot run does not bind its frozen batch-8 settings")
    checkpoints = sorted((run / "responses").glob("batch-*.json"))
    if [path.name for path in checkpoints] != ["batch-0001.json"]: raise ValueError("Pilot cell does not have exactly one completed provider batch")
    checkpoint = read_json(checkpoints[0]); prompt = gzip.decompress(checkpoints[0].with_suffix(".prompt.txt.gz").read_bytes())
    if checkpoint.get("format_version") != 4 or checkpoint.get("batch") != 1 or checkpoint.get("question_ids") != cell["question_ids"] or checkpoint.get("retry_policy") != {"batch_attempts": 1} or checkpoint.get("base_prompt_sha256") != hashlib.sha256(prompt).hexdigest() or checkpoint.get("prompt_sha256") != hashlib.sha256(prompt).hexdigest(): raise ValueError("Pilot checkpoint is malformed")
    if prompt != _expected_prompt(folder, cell):
        raise ValueError("Pilot checkpoint prompt does not reconstruct from frozen inputs/questions")
    raw = _raw_transport(run, checkpoint, prompt)
    try: _load_checkpoints(run, artifact_text=(folder / "source.md").read_text(encoding="utf-8"), context_texts=[(folder / "prompt.md").read_text(encoding="utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc: raise ValueError("Pilot completion is not schema-valid/replayable") from exc
    expected_receipt = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "score_blind_transport_completion", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_ids": cell["question_ids"], "elapsed_seconds": receipt.get("elapsed_seconds"), "run": fingerprint(run / "run.json"), "checkpoint": fingerprint(checkpoints[0]), "provider": checkpoint["provider"], "session": {"mode": "stateless"}, "raw_transport": raw}
    if not _timely(receipt.get("elapsed_seconds")) or receipt != expected_receipt: raise ValueError("Pilot receipt has invalid duration or bindings")
    return receipt


def verify_pilot(work: Path) -> dict[str, Any]:
    frozen = load_frozen(work); _invocation(work); _claim(work)
    paths = sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json")); records = [read_json(path) for path in paths]
    if len(records) != 3 or [record.get("sequence") for record in records] != [1, 2, 3] or any(record.get("status") != "completed" for record in records): raise ValueError("Pilot did not produce exactly three completed cells; v3 is closed")
    receipts = [_verify_cell(work, frozen, cell) for cell in frozen["cells"]]; ids = [str(item["raw_transport"]["evidence"]["run_id"]) for item in receipts]
    if len(set(ids)) != 3: raise ValueError("Pilot completion evidence was reused across cells")
    expected = [{"sequence": number, "cell_id": receipt["cell_id"], "status": "completed", "receipt": fingerprint(work / "pilot-receipts" / f"{receipt['cell_id']}.json")} for number, receipt in enumerate(receipts, 1)]
    if records != expected or [path.name for path in paths] != [f"{number:04d}-{receipt['cell_id']}.json" for number, receipt in enumerate(receipts, 1)]: raise ValueError("Pilot journal does not bind its receipts")
    return {"status": "PASS", "cells": 3, "comparison_status": CONTRACT["development"]["comparison_status"], "claim": fingerprint(work / "pilot-execution-claim.json"), "verifier": fingerprint(Path(__file__))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True)
    print(json.dumps(verify_pilot(parser.parse_args().work_dir.resolve()), sort_keys=True))
