#!/usr/bin/env python3
"""Execute the frozen Ox Alpha v4 probe once, serially, with a cap of one."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import CONTRACT, FROZEN_NAME, assert_launch_freshness, canonical, fingerprint, immutable_json, input_paths, load_frozen, read_json, runtime_bindings


TERMINAL_STABILITY_SECONDS = 2.0


def _records(work: Path) -> list[Path]:
    root = work / "pilot-journal"
    if not root.exists():
        return []
    records = sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json"))
    if len(records) != len(list(root.iterdir())):
        raise ValueError("Ox v4 journal is malformed")
    return records


def _append(work: Path, record: Mapping[str, Any]) -> None:
    records = _records(work)
    sequence = len(records) + 1
    cell_id = record.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("Ox v4 journal cell is malformed")
    path = work / "pilot-journal" / f"{sequence:04d}-{cell_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps({"sequence": sequence, **record}, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Ox v4 journal record already exists") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(rendered)
        output.flush()
        os.fsync(output.fileno())


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
        raise ValueError("Ox v4 root already has an execution claim; retry or resume is forbidden") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write(rendered)
        output.flush()
        os.fsync(output.fileno())


def _receipt_path(work: Path, cell_id: str) -> Path:
    return work / "pilot-receipts" / f"{cell_id}.json"


def _tree(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError("Ox v4 bridge evidence root is unavailable")
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _terminal_failure_seal(work: Path, cell: Mapping[str, Any]) -> dict[str, Any]:
    evidence = work / "runs" / "pilot" / str(cell["cell_id"]) / "responses" / "batch-0001.attempt-0001.nous.evidence"
    initial = _tree(evidence)
    receipts = sorted(evidence.rglob("receipt.json"))
    failure = next((path for path in receipts if read_json(path).get("status") == "failure"), None)
    receipt = read_json(failure) if failure is not None else None
    if failure is None or not isinstance(receipt, Mapping) or any(not isinstance(receipt.get(key), str) or not receipt[key] for key in ("sealed_at", "terminal_chain_sha256", "events_sha256")):
        raise ValueError("Ox v4 bridge has not sealed a terminal failure")
    events = failure.parent / "events.jsonl"
    if not events.is_file():
        raise ValueError("Ox v4 terminal failure lacks an event chain")
    records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [record.get("data") for record in records if isinstance(record, Mapping) and record.get("event_type") == "http_attempt"]
    status = attempts[0].get("status") if len(attempts) == 1 and isinstance(attempts[0], Mapping) else None
    if len(attempts) != 1 or isinstance(status, bool) or not isinstance(status, int) or 200 <= status < 300:
        raise ValueError("Ox v4 terminal failure does not bind one failed physical attempt")
    time.sleep(TERMINAL_STABILITY_SECONDS)
    if _tree(evidence) != initial or not failure.is_file() or read_json(failure) != receipt:
        raise ValueError("Ox v4 bridge terminal evidence is not stable after launcher return")
    return {"evidence_tree": initial, "failure_receipt": fingerprint(failure), "events": fingerprint(events), "quiescence": "launcher_returned_and_terminal_tree_stable"}


def _uncertain(work: Path, cell: Mapping[str, Any], invocation: Mapping[str, Any], error: BaseException, reason: str) -> None:
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "blocked_uncertain_transport_outcome", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "invocation": invocation, "reason": reason, "error": {"class": type(error).__name__, "message": str(error)[:4000]}}
    immutable_json(work / "pilot-uncertain.json", value)


def _execute_one(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    artifact, prompt, task = input_paths(frozen, cell)
    output = work / "runs" / "pilot" / str(cell["cell_id"])
    run_judge(artifact_path=artifact, context_paths=[prompt], task_contract_path=task, bundle_id="prose.short_story", provider="nous", model=CONTRACT["provider"]["model"], reasoning="max", output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=cell["question_ids"], batch_size=8, batch_attempts=1, allow_remote=True, timeout=240, artifact_id=str(cell["item_id"]), strict_ai=False, allow_unattested_reasoning=True, resume=False, max_physical_http_attempts_per_logical_request=1)
    from verify_transport_pilot import verify_cell
    proof = verify_cell(work, frozen, cell)
    receipt = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "cap1_transport_completion", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_ids": cell["question_ids"], "run": proof["run"], "checkpoint": proof["checkpoint"], "logical_request_id": proof["logical_request_id"], "payload": proof["payload"], "raw_evidence": proof["raw_evidence"], "provider_receipt": proof["provider_receipt"]}
    immutable_json(_receipt_path(work, str(cell["cell_id"])), receipt)
    return receipt


def execute(work: Path) -> None:
    frozen = load_frozen(work)
    if _records(work) or (work / "runs").exists() or (work / "pilot-execution-claim.json").exists() or (work / "pilot-receipts").exists() or (work / "pilot-uncertain.json").exists():
        raise ValueError("Ox v4 has immutable evidence; retry, fallback, and resume are forbidden")
    assert_launch_freshness(frozen)
    _invocation(work, frozen)
    _claim(work)
    invocation = fingerprint(work / "pilot-invocation.json")
    for cell in frozen["cells"]:
        try:
            receipt = _execute_one(work, frozen, cell)
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation, "receipt": fingerprint(_receipt_path(work, str(cell["cell_id"]))), "logical_request_id": receipt["logical_request_id"]})
        except BaseException as exc:
            if "launcher timed out" in str(exc).lower():
                _uncertain(work, cell, invocation, exc, "outer_timeout_before_terminal_bridge_quiescence")
                raise
            try:
                terminal = _terminal_failure_seal(work, cell)
            except BaseException as seal_error:
                _uncertain(work, cell, invocation, exc, f"terminal_bridge_quiescence_unproven:{type(seal_error).__name__}")
                raise ValueError("Ox v4 root is uncertain and blocked; terminal bridge quiescence was not proved") from exc
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "failed", "invocation": invocation, "terminal_failure": terminal, "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    execute(parser.parse_args().work_dir.resolve())
