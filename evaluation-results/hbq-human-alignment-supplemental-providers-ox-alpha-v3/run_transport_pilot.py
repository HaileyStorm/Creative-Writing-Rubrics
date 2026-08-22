#!/usr/bin/env python3
"""Execute the frozen Ox Alpha cap-1 transport pilot, serially and once."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import CONTRACT, FROZEN_NAME, assert_launch_freshness, fingerprint, immutable_json, input_paths, load_frozen, runtime_bindings, sha


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "pilot-journal"
    if not root.exists():
        return []
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json"))]
    if [row.get("sequence") for row in rows] != list(range(1, len(rows) + 1)) or len({row.get("cell_id") for row in rows}) != len(rows):
        raise ValueError("Ox v3 journal is malformed")
    return rows


def _append(work: Path, record: Mapping[str, Any]) -> None:
    rows = _records(work)
    if any(row.get("cell_id") == record.get("cell_id") for row in rows):
        raise ValueError("Ox v3 journal already records this cell")
    immutable_json(work / "pilot-journal" / f"{len(rows) + 1:04d}-{record['cell_id']}.json", {"sequence": len(rows) + 1, **record})


def _invocation(work: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    value = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "score_blind_cap1_transport_pilot", "contract": fingerprint(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract": fingerprint(work / FROZEN_NAME), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "execution": CONTRACT["execution"], "runtime": runtime_bindings(), "zero_cost_fresh_at_invocation": datetime.now(timezone.utc).isoformat(), "runner": fingerprint(Path(run_judge.__code__.co_filename)), "pilot_runner": fingerprint(Path(__file__)), "pilot_verifier": fingerprint(Path(__file__).resolve().parent / "verify_transport_pilot.py")}
    immutable_json(work / "pilot-invocation.json", value)
    return value


def _claim(work: Path) -> None:
    path = work / "pilot-execution-claim.json"
    value = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_cap1_transport_execution", "invocation": fingerprint(work / "pilot-invocation.json"), "pid": os.getpid()}
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Ox v3 root already has an execution claim; no retry or resume is permitted") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(rendered); output.flush(); os.fsync(output.fileno())


def _receipt_path(work: Path, cell_id: str) -> Path:
    return work / "pilot-receipts" / f"{cell_id}.json"


def _execute_one(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    artifact, prompt, task = input_paths(frozen, cell)
    output = work / "runs" / "pilot" / str(cell["cell_id"])
    run_judge(artifact_path=artifact, context_paths=[prompt], task_contract_path=task, bundle_id="prose.short_story", provider="nous", model=CONTRACT["provider"]["model"], reasoning="max", output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=cell["question_ids"], batch_size=16, batch_attempts=1, allow_remote=True, timeout=100, artifact_id=str(cell["item_id"]), strict_ai=False, allow_unattested_reasoning=True, resume=False, max_physical_http_attempts_per_logical_request=1)
    from verify_transport_pilot import verify_cell
    proof = verify_cell(work, frozen, cell)
    receipt = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "cap1_transport_completion", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_ids": cell["question_ids"], "run": proof["run"], "checkpoint": proof["checkpoint"], "logical_request_id": proof["logical_request_id"], "payload": proof["payload"], "raw_evidence": proof["raw_evidence"], "provider_receipt": proof["provider_receipt"]}
    immutable_json(_receipt_path(work, str(cell["cell_id"])), receipt)
    return receipt


def execute(work: Path) -> None:
    frozen = load_frozen(work)
    if _records(work) or (work / "runs").exists() or (work / "pilot-execution-claim.json").exists():
        raise ValueError("Ox v3 has immutable evidence; retry, fallback, and resume are forbidden")
    assert_launch_freshness(frozen)
    invocation = _invocation(work, frozen)
    _claim(work)
    invocation_binding = fingerprint(work / "pilot-invocation.json")
    for cell in frozen["cells"]:
        try:
            receipt = _execute_one(work, frozen, cell)
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation_binding, "receipt": fingerprint(_receipt_path(work, str(cell["cell_id"]))), "logical_request_id": receipt["logical_request_id"]})
        except BaseException as exc:
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "failed", "invocation": invocation_binding, "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    execute(parser.parse_args().work_dir.resolve())
