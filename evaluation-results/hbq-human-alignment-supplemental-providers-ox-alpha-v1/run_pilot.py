#!/usr/bin/env python3
"""Launch the one-attempt, serial Ox Alpha pilot through the canonical Nous bridge."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as runner_module
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge

from study import CONTRACT, HERE, _assert_fresh_at, fingerprint, immutable_json, input_folder, load_frozen, runtime_bindings, sha, strict_json


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "pilot-journal"
    if not root.exists():
        return []
    records: list[dict[str, Any]] = []
    for sequence, path in enumerate(sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json")), 1):
        record = strict_json(path.read_text(encoding="utf-8"), label=str(path))
        if not isinstance(record, dict) or record.get("sequence") != sequence or path.name != f"{sequence:04d}-{record.get('cell_id')}.json":
            raise ValueError("Pilot journal is malformed")
        records.append(record)
    if len({record.get("cell_id") for record in records}) != len(records):
        raise ValueError("Pilot journal reuses a cell")
    return records


def _append(work: Path, value: Mapping[str, Any]) -> None:
    lock = work / "pilot-journal.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Pilot journal is locked; do not race the serial Ox Alpha pilot") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write("locked\n")
            output.flush()
            os.fsync(output.fileno())
        records = _records(work)
        if any(record.get("cell_id") == value.get("cell_id") for record in records):
            raise ValueError("Pilot journal already records this cell")
        record = {"sequence": len(records) + 1, **value}
        immutable_json(work / "pilot-journal" / f"{record['sequence']:04d}-{record['cell_id']}.json", record)
    finally:
        lock.unlink(missing_ok=True)


def _claim(work: Path) -> None:
    path = work / "pilot-execution-claim.json"
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_ox_alpha_execution", "invocation": fingerprint(work / "pilot-invocation.json"), "pid": os.getpid()}
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Pilot root already has an exclusive execution claim; do not retry or resume") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(rendered)
        output.flush()
        os.fsync(output.fileno())


def _invocation(work: Path, frozen: Mapping[str, Any], timeout: float, zero_cost_fresh_at_invocation: str) -> dict[str, Any]:
    return {
        "format_version": 1, "study_id": CONTRACT["study_id"], "contract_sha256": sha(HERE / "study-contract.json"),
        "frozen_contract_sha256": sha(work / "frozen-ox-alpha-contract.json"), "provider": CONTRACT["provider"],
        "workers": 1, "timeout_seconds": timeout, "runtime": runtime_bindings(),
        "pilot_runner": fingerprint(Path(__file__)), "runner": fingerprint(Path(run_judge.__code__.co_filename)),
        "maximum_logical_requests": CONTRACT["runtime"]["maximum_logical_requests"],
        "maximum_physical_http_attempts": CONTRACT["runtime"]["maximum_physical_http_attempts"],
        "remote_disclosure": CONTRACT["remote_disclosure"], "zero_cost": CONTRACT["zero_cost"],
        "zero_cost_fresh_at_invocation": zero_cost_fresh_at_invocation,
    }


def _verify_cell(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    from analyze_pilot import verify_run
    return verify_run(work, frozen, cell)


def execute(work: Path, *, timeout: float = 600.0) -> None:
    if timeout != 600.0:
        raise ValueError("Frozen Ox Alpha pilot requires timeout 600 seconds")
    frozen = load_frozen(work)
    if _records(work) or (work / "runs").exists():
        raise ValueError("Pilot already has immutable evidence; no retry, fallback, or resume is permitted")
    proof = frozen.get("zero_cost_proof")
    if not isinstance(proof, Mapping):
        raise ValueError("Frozen Ox Alpha pilot lacks its sealed zero-cost proof")
    fresh_at = datetime.now(timezone.utc).isoformat()
    _assert_fresh_at(proof, fresh_at)
    immutable_json(work / "pilot-invocation.json", _invocation(work, frozen, timeout, fresh_at))
    _claim(work)
    for cell in frozen["cells"]:
        folder = input_folder(frozen, cell)
        output = work / "runs" / cell["cell_id"]
        try:
            run_judge(
                artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"], task_contract_path=folder / "task-contract.json",
                bundle_id=CONTRACT["runtime"]["bundle_id"], provider="nous", model=CONTRACT["provider"]["model"],
                reasoning="max", output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=cell["question_ids"],
                batch_size=32, batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=cell["item_id"],
                strict_ai=False, allow_unattested_reasoning=True, resume=False,
            )
            proof = _verify_cell(work, frozen, cell)
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "run": fingerprint(output / "run.json"), "proof": proof})
        except BaseException as exc:
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "failed", "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--timeout", default=600.0, type=float)
    args = parser.parse_args()
    execute(args.work_dir.resolve(), timeout=args.timeout)
