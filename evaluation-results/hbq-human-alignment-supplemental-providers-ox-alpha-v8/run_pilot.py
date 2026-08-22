#!/usr/bin/env python3
"""Serial, cap-1 Ox Alpha v8 executor. This is the only provider-contact path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import CONTRACT, FROZEN_NAME, assert_fresh_at, fingerprint, immutable_json, input_paths, load_frozen, runtime_bindings

QUIESCENCE_SECONDS = 2.0


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "pilot-journal"
    if not root.exists():
        return []
    paths = sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json"))
    if len(paths) != len(list(root.iterdir())):
        raise ValueError("Ox v8 journal is malformed")
    records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if [record.get("sequence") for record in records] != list(range(1, len(records) + 1)):
        raise ValueError("Ox v8 journal sequence is malformed")
    return records


def _append(work: Path, record: Mapping[str, Any]) -> None:
    rows = _records(work)
    if any(row.get("cell_id") == record.get("cell_id") for row in rows):
        raise ValueError("Ox v8 journal already records this cell")
    immutable_json(work / "pilot-journal" / f"{len(rows) + 1:04d}-{record['cell_id']}.json", {"sequence": len(rows) + 1, **record})


def _claim(work: Path) -> None:
    path = work / "pilot-execution-claim.json"
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_cap1_full_scoring_execution", "invocation": fingerprint(work / "pilot-invocation.json"), "pid": os.getpid()}
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Ox v8 root already has an execution claim; retry or resume is forbidden") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(rendered)
        output.flush()
        os.fsync(output.fileno())


def _tree(root: Path) -> dict[str, Any]:
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"files": len(entries), "sha256": hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()}


def _quiescent(work: Path) -> dict[str, Any]:
    """Any non-success is uncertain unless the launcher-returned tree is stable."""
    first = _tree(work / "runs") if (work / "runs").is_dir() else {"files": 0, "sha256": hashlib.sha256(b"[]").hexdigest()}
    time.sleep(QUIESCENCE_SECONDS)
    second = _tree(work / "runs") if (work / "runs").is_dir() else {"files": 0, "sha256": hashlib.sha256(b"[]").hexdigest()}
    if first != second:
        raise ValueError("Ox v8 launcher-returned provider evidence is not quiescent")
    return {"runs_tree": first, "state": "launcher_returned_and_runs_tree_stable"}


def _invocation(work: Path, frozen: Mapping[str, Any]) -> None:
    value = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "kind": "outcome_blind_serial_cap1_full_scoring",
        "contract": fingerprint(Path(__file__).resolve().parent / "study-contract.json"),
        "frozen_contract": fingerprint(work / FROZEN_NAME),
        "provider": CONTRACT["provider"],
        "runtime": CONTRACT["runtime"],
        "remote_disclosure": CONTRACT["remote_disclosure"],
        "zero_cost": CONTRACT["zero_cost"],
        "runtime_bindings": runtime_bindings(),
        "runner": fingerprint(Path(run_judge.__code__.co_filename)),
        "executor": fingerprint(Path(__file__)),
        "verifier": fingerprint(Path(__file__).resolve().parent / "analyze_pilot.py"),
        "zero_cost_fresh_at_invocation": datetime.now(timezone.utc).isoformat(),
    }
    assert_fresh_at(frozen["zero_cost_proof"], value["zero_cost_fresh_at_invocation"])
    immutable_json(work / "pilot-invocation.json", value)


def _receipt(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any], proof: Mapping[str, Any]) -> Path:
    path = work / "pilot-receipts" / f"{cell['cell_id']}.json"
    immutable_json(path, {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "kind": "cap1_full_scoring_completion",
        "cell_id": cell["cell_id"],
        "item_id": cell["item_id"],
        "question_count": len(cell["primary_question_ids"]),
        "v7_transport_tree": frozen["v7_transport_success"]["tree"],
        "excluded_v7_global_ids": frozen["v7_transport_success"]["global_ids"],
        "proof": proof,
    })
    return path


def execute(work: Path, *, timeout: float = 240.0) -> None:
    if timeout != 240.0:
        raise ValueError("Frozen Ox v8 protocol requires a 240-second launcher timeout")
    frozen = load_frozen(work)
    if _records(work) or any((work / name).exists() for name in ("runs", "pilot-execution-claim.json", "pilot-receipts", "pilot-uncertain.json")):
        raise ValueError("Ox v8 has immutable evidence; retry, fallback, and resume are forbidden")
    _invocation(work, frozen)
    _claim(work)
    invocation = fingerprint(work / "pilot-invocation.json")
    for cell in frozen["cells"]:
        try:
            artifact, prompt, task = input_paths(cell)
            run_judge(
                artifact_path=artifact, context_paths=[prompt], task_contract_path=task,
                bundle_id=CONTRACT["questions"]["bundle_id"], provider="nous", model=CONTRACT["provider"]["model"], reasoning="max",
                output_dir=work / "runs" / str(cell["cell_id"]), registry=registry_path(), bundles=bundles_path(),
                question_ids=cell["primary_question_ids"], batch_size=4, batch_attempts=1, allow_remote=True,
                timeout=timeout, artifact_id=str(cell["item_id"]), strict_ai=False, allow_unattested_reasoning=True,
                resume=False, max_physical_http_attempts_per_logical_request=1,
            )
            from analyze_pilot import verify_run
            proof = verify_run(work, frozen, cell)
            receipt = _receipt(work, frozen, cell, proof)
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation, "receipt": fingerprint(receipt), "proof": proof})
        except BaseException as exc:
            try:
                quiescence = _quiescent(work)
            except BaseException as quiescence_error:
                quiescence = {"state": "unproven", "error": {"class": type(quiescence_error).__name__, "message": str(quiescence_error)[:4000]}}
            immutable_json(work / "pilot-uncertain.json", {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "blocked_uncertain_full_scoring_outcome", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "invocation": invocation, "quiescence": quiescence, "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "failed_uncertain", "invocation": invocation, "uncertain": fingerprint(work / "pilot-uncertain.json")})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=240.0)
    args = parser.parse_args()
    execute(args.work_dir.resolve(), timeout=args.timeout)
