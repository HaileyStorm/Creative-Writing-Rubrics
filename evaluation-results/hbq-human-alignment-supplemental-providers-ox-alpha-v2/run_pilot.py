#!/usr/bin/env python3
"""Serial, one-attempt Ox Alpha v2 executor. The runner owns all provider contact."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import CONTRACT, HERE, FROZEN_NAME, _assert_fresh_at, fingerprint, immutable_json, input_paths, load_frozen, sha


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "pilot-journal"
    if not root.exists():
        return []
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("[0-9][0-9][0-9][0-9]-*.json"))]
    if any(not isinstance(row, dict) or row.get("sequence") != number for number, row in enumerate(rows, 1)):
        raise ValueError("Ox v2 journal is malformed")
    return rows


def _append(work: Path, record: Mapping[str, Any]) -> None:
    rows = _records(work)
    if any(row.get("cell_id") == record.get("cell_id") for row in rows):
        raise ValueError("Ox v2 journal already records this cell")
    immutable_json(work / "pilot-journal" / f"{len(rows) + 1:04d}-{record['cell_id']}.json", {"sequence": len(rows) + 1, **record})


def _claim(work: Path) -> None:
    path = work / "pilot-execution-claim.json"
    value = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_ox_alpha_execution", "invocation": fingerprint(work / "pilot-invocation.json"), "pid": os.getpid()}
    rendered = json.dumps(value, sort_keys=True, indent=2) + "\n"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValueError("Ox v2 root already has an execution claim; no retry or resume is permitted") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(rendered); output.flush(); os.fsync(output.fileno())


def execute(work: Path, *, timeout: float = 600.0) -> None:
    if timeout != 600.0:
        raise ValueError("Frozen Ox v2 protocol requires timeout 600 seconds")
    frozen = load_frozen(work)
    if _records(work) or (work / "runs").exists():
        raise ValueError("Ox v2 has immutable evidence; retry, fallback, and resume are forbidden")
    invoked_at = datetime.now(timezone.utc).isoformat()
    _assert_fresh_at(frozen["zero_cost_proof"], invoked_at)
    invocation = {"format_version": 2, "study_id": CONTRACT["study_id"], "contract_sha256": sha(HERE / "study-contract.json"), "frozen_contract_sha256": sha(work / FROZEN_NAME), "provider": CONTRACT["provider"], "runtime": CONTRACT["runtime"], "remote_disclosure": CONTRACT["remote_disclosure"], "zero_cost": CONTRACT["zero_cost"], "zero_cost_fresh_at_invocation": invoked_at}
    immutable_json(work / "pilot-invocation.json", invocation)
    _claim(work)
    invocation_binding = fingerprint(work / "pilot-invocation.json")
    for cell in frozen["cells"]:
        artifact, prompt, task = input_paths(cell)
        output = work / "runs" / str(cell["cell_id"])
        try:
            run_judge(artifact_path=artifact, context_paths=[prompt], task_contract_path=task, bundle_id=CONTRACT["questions"]["bundle_id"], provider="nous", model=CONTRACT["provider"]["model"], reasoning="max", output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=cell["primary_question_ids"], batch_size=32, batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=cell["item_id"], strict_ai=False, allow_unattested_reasoning=True, resume=False)
            from analyze_pilot import verify_run
            verified = verify_run(work, frozen, cell)
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation_binding, "run": verified["run"], "proof": verified})
        except BaseException as exc:
            _append(work, {"cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "failed", "invocation": invocation_binding, "error": {"class": type(exc).__name__, "message": str(exc)[:4000]}})
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", required=True, type=Path); parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args(); execute(args.work_dir.resolve(), timeout=args.timeout)
