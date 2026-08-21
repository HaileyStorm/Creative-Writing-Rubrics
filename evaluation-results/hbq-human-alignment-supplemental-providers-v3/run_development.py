#!/usr/bin/env python3
"""Run the explicitly enabled, one-attempt batch-8 development condition."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from enable_development import enable
from study import CONTRACT, _v2_parent_inputs, fingerprint, immutable_json, load_frozen, runtime_bindings, sha


def _invocation(work: Path, enablement: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "batch_8_development", "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"), "enablement": fingerprint(work / "development-enablement.json"), "provider": CONTRACT["provider"], "batch_size": 8, "batch_attempts": 1, "workers": 1, "timeout_seconds": 600.0, "runtime": runtime_bindings(), "runner": fingerprint(Path(run_judge.__code__.co_filename)), "study": fingerprint(Path(__file__).resolve().parent / "study.py"), "development_enabler": fingerprint(Path(__file__).resolve().parent / "enable_development.py"), "development_runner": fingerprint(Path(__file__)), "comparison_status": enablement["development"]["comparison_status"]}


def _claim(work: Path) -> None:
    path = work / "development-execution-claim.json"
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_batch_8_development_execution", "invocation": fingerprint(work / "development-invocation.json"), "pid": os.getpid()}
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try: descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc: raise ValueError("Development root already has an exclusive execution claim; do not race or retry v3") from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as output: output.write(rendered); output.flush(); os.fsync(output.fileno())


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "development-journal"
    if not root.exists(): return []
    records = []
    for number, path in enumerate(sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json")), 1):
        value = json.loads(path.read_text(encoding="utf-8"))
        if path.name != f"{number:04d}-{value.get('item_id')}.json": raise ValueError("Development journal path/sequence is malformed")
        records.append(value)
    if [item.get("sequence") for item in records] != list(range(1, len(records) + 1)) or len({item.get("item_id") for item in records}) != len(records): raise ValueError("Development journal is not append-only")
    return records


def _append(work: Path, value: Mapping[str, Any]) -> None:
    lock = work / "development-journal.lock"; lock.parent.mkdir(parents=True, exist_ok=True)
    try: descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc: raise ValueError("Development journal is locked; do not race v3") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output: output.write("locked\n"); output.flush(); os.fsync(output.fileno())
        records = _records(work)
        if any(item.get("item_id") == value.get("item_id") for item in records): raise ValueError("Development journal already has this item")
        record = {"sequence": len(records) + 1, **value}; immutable_json(work / "development-journal" / f"{record['sequence']:04d}-{record['item_id']}.json", record)
    finally: lock.unlink(missing_ok=True)


def execute(work: Path, *, timeout: float = 600) -> None:
    if timeout != 600: raise ValueError("Frozen v3 development requires timeout 600 seconds")
    frozen = load_frozen(work); enablement = enable(work); immutable_json(work / "development-invocation.json", _invocation(work, enablement))
    if _records(work): raise ValueError("Development has immutable partial/completed evidence; do not retry v3")
    _claim(work)
    parent, parent_frozen = _v2_parent_inputs(Path(frozen["failed_v2"]["work_dir"]))
    for row in parent.phase_rows(parent_frozen, "development"):
        item_id = str(row["item_id"]); folder, _ = parent.primary_input(parent_frozen, "development", item_id); output = work / "runs" / "development" / item_id / "run-01"
        try:
            run_judge(artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"], task_contract_path=folder / "task-contract.json", bundle_id="prose.short_story", provider="nous", model=CONTRACT["provider"]["model"], reasoning="max", output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=parent_frozen["selection"]["question_ids"], batch_size=8, batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=item_id, strict_ai=False, allow_unattested_reasoning=True)
            _append(work, {"item_id": item_id, "status": "completed", "run": fingerprint(output / "run.json")})
        except BaseException as exc:
            _append(work, {"item_id": item_id, "status": "failed", "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True); parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(); execute(args.work_dir.resolve(), timeout=args.timeout)
