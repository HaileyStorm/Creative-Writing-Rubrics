#!/usr/bin/env python3
"""Execute the immutable batch-8 pilot: sequential, one request per cell."""
from __future__ import annotations

import argparse
import gzip
import json
import os
import time
from pathlib import Path
from typing import Any, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import CONTRACT, fingerprint, immutable_json, input_folder, load_frozen, read_json, runtime_bindings, sha


def _journal_records(work: Path) -> list[dict[str, Any]]:
    root = work / "pilot-journal"
    if not root.exists():
        return []
    paths = sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json")); records = []
    for number, path in enumerate(paths, 1):
        try: value = read_json(path)
        except (OSError, ValueError) as exc: raise ValueError("Pilot journal is malformed") from exc
        if path.name != f"{number:04d}-{value.get('cell_id')}.json": raise ValueError("Pilot journal path/sequence is malformed")
        records.append(value)
    if [item.get("sequence") for item in records] != list(range(1, len(records) + 1)) or len({item.get("cell_id") for item in records}) != len(records):
        raise ValueError("Pilot journal is not append-only")
    return records


def _append_journal(work: Path, value: Mapping[str, Any]) -> None:
    lock = work / "pilot-journal.lock"; lock.parent.mkdir(parents=True, exist_ok=True)
    try: descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc: raise ValueError("Pilot journal is locked; do not race v3") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output: output.write("locked\n"); output.flush(); os.fsync(output.fileno())
        records = _journal_records(work)
        if any(record.get("cell_id") == value.get("cell_id") for record in records): raise ValueError("Pilot journal already has this cell")
        record = {"sequence": len(records) + 1, **value}
        immutable_json(work / "pilot-journal" / f"{record['sequence']:04d}-{record['cell_id']}.json", record)
    finally: lock.unlink(missing_ok=True)


def _claim(work: Path) -> dict[str, Any]:
    path = work / "pilot-execution-claim.json"
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_score_blind_pilot_execution", "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"), "pid": os.getpid(), "runtime": runtime_bindings()}
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try: descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc: raise ValueError("Pilot work root already has an exclusive execution claim; v3 is permanently closed") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as output: output.write(rendered); output.flush(); os.fsync(output.fileno())
    return value


def _invocation(work: Path, frozen: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "score_blind_transport_pilot", "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"), "workers": 1, "timeout_seconds": float(timeout), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "runner": fingerprint(Path(run_judge.__code__.co_filename)), "study": fingerprint(Path(__file__).resolve().parent / "study.py"), "pilot_runner": fingerprint(Path(__file__)), "pilot_verifier": fingerprint(Path(__file__).resolve().parent / "verify_transport_pilot.py")}
    if not (work / "pilot-invocation.json").exists() and ((work / "pilot-journal").exists() or (work / "runs" / "pilot").exists()):
        raise ValueError("Refusing pilot invocation backfill after output exists")
    immutable_json(work / "pilot-invocation.json", value)
    return value


def _receipt_path(work: Path, cell_id: str) -> Path: return work / "pilot-receipts" / f"{cell_id}.json"


def _receipt(work: Path, cell: Mapping[str, Any], elapsed: float) -> dict[str, Any]:
    from verify_transport_pilot import _raw_transport
    run = work / "runs" / "pilot" / str(cell["cell_id"]); checkpoint_path = run / "responses" / "batch-0001.json"
    checkpoint = read_json(checkpoint_path); provider = checkpoint.get("provider")
    if not isinstance(provider, Mapping): raise ValueError("Pilot checkpoint lacks a Nous provider receipt")
    raw = _raw_transport(run, checkpoint, gzip.decompress(checkpoint_path.with_suffix(".prompt.txt.gz").read_bytes()))
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "score_blind_transport_completion", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_ids": cell["question_ids"], "elapsed_seconds": elapsed, "run": fingerprint(run / "run.json"), "checkpoint": fingerprint(checkpoint_path), "provider": provider, "session": {"mode": "stateless"}, "raw_transport": raw}
    immutable_json(_receipt_path(work, str(cell["cell_id"])), value)
    return value


def _execute_one(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    folder = input_folder(frozen, cell); output = work / "runs" / "pilot" / str(cell["cell_id"]); started = time.monotonic()
    run_judge(artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"], task_contract_path=folder / "task-contract.json", bundle_id="prose.short_story", provider="nous", model=CONTRACT["provider"]["model"], reasoning="max", output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=cell["question_ids"], batch_size=8, batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=str(cell["item_id"]), strict_ai=False, allow_unattested_reasoning=True)
    receipt = _receipt(work, cell, time.monotonic() - started)
    _append_journal(work, {"cell_id": cell["cell_id"], "status": "completed", "receipt": fingerprint(_receipt_path(work, str(cell["cell_id"])))})
    return receipt


def execute(work: Path, *, timeout: float = 600) -> None:
    if timeout != CONTRACT["transport_pilot"]["timeout_seconds"]: raise ValueError("The frozen v3 transport pilot requires timeout 600 seconds")
    frozen = load_frozen(work); records = _journal_records(work)
    if records:
        if len(records) == 3 and all(item.get("status") == "completed" for item in records):
            from verify_transport_pilot import verify_pilot; verify_pilot(work); return
        raise ValueError("v3 has immutable partial/failure evidence; no further automatic successor is authorized")
    _claim(work); _invocation(work, frozen, timeout)
    for cell in frozen["cells"]:
        try: _execute_one(work, frozen, cell, timeout)
        except BaseException as exc:
            _append_journal(work, {"cell_id": cell["cell_id"], "status": "failed", "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True); parser.add_argument("--timeout", type=float, default=600)
    arguments = parser.parse_args(); execute(arguments.work_dir.resolve(), timeout=arguments.timeout)
