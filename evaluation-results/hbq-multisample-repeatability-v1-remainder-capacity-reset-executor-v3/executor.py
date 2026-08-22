#!/usr/bin/env python3
"""Append-only, one-cell executor for the capacity-reset multisample remainder."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
V2 = HERE.parent / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v2"
CONTRACT = HERE / "study-contract.json"
BINDING = "executor-binding.json"
SCHEDULE = "schedule.jsonl"
JOURNAL = "execution-journal.jsonl"
PROOFS = "capacity-proofs"
CLAIM = "active-epoch-claim.json"
V2_FILES = ("README.md", "run_capacity_reset.py", "study-contract.json")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT)
    expected = {
        "format_version": 1,
        "study_id": "hbq-multisample-repeatability-v1-remainder-capacity-reset-executor-v3",
        "base_v2_commit": "25783345f0bb18cf41cc641cd9aae90ab18ed25d",
        "schedule": {"count": 153, "first_sequence": 178, "last_sequence": 330, "sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086"},
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "paid_api": False, "human_judgment": False},
        "capacity": {"max_age_seconds": 600, "per_send_revalidation": True, "probe_authorizes_provider_contact": False},
        "execution": {"cells_per_epoch": 1, "resend_after_unresolved_attempt": False, "outcome_selection": False},
    }
    if value != expected:
        raise ValueError("V3 execution contract semantics drifted")
    return value


def _load_v2() -> Any:
    previous = sys.modules.get("study")
    spec = importlib.util.spec_from_file_location("multisample_capacity_reset_v2", V2 / "run_capacity_reset.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load pushed v2 handoff")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(V2))
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(V2))
        if previous is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous


def _commitment(path: Path, *, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file() or root not in resolved.parents:
        raise ValueError("Runtime file escapes its expected root")
    return {"path": resolved.relative_to(root).as_posix(), "bytes": resolved.stat().st_size, "sha256": sha(resolved)}


def _v2_projection() -> dict[str, Any]:
    c = contract()
    files = [_commitment(V2 / name, root=REPO) for name in V2_FILES]
    for item in files:
        expected = subprocess.check_output(["git", "rev-parse", f"{c['base_v2_commit']}:{item['path']}"], cwd=REPO, text=True, timeout=10).strip()
        current = subprocess.check_output(["git", "hash-object", item["path"]], cwd=REPO, text=True, timeout=10).strip()
        if expected != current:
            raise ValueError("Pushed v2 source projection drifted")
    return {"commit": c["base_v2_commit"], "files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def _v3_runtime() -> dict[str, Any]:
    files = [_commitment(CONTRACT, root=HERE), _commitment(HERE / "executor.py", root=HERE)]
    return {"files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def _outside_repo(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == REPO or REPO in resolved.parents:
        raise ValueError("Execution root must be external to the repository")
    return resolved


def _append(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        if os.write(descriptor, payload) != len(payload):
            raise OSError("Execution journal write was partial")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Journal has an uncertain partial tail")
    return [json.loads(line) for line in raw.splitlines()]


def _acquire_claim(work: Path, source: Path) -> Path:
    """Atomically reserve one epoch; an existing claim is never auto-cleared."""
    path = work / CLAIM
    claim = {
        "format_version": 1,
        "pid": os.getpid(),
        "claimed_at": datetime.now(UTC).isoformat(),
        "contract_sha256": sha(CONTRACT),
        "v3_runtime_sha256": _v3_runtime()["sha256"],
        "frozen_contract_sha256": sha(source / "frozen-run-contract.json"),
    }
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("Exclusive epoch claim exists; stop without duplicate dispatch") from exc
    try:
        payload = canonical(claim) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            raise OSError("Epoch claim write was partial")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def _base(v2: Any, closed: Path, source: Path, v2_work: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _, schedule, execution = v2._verify_prepared(closed, source, v2_work, allow_executor=True, allow_authorization=True)
    previous = v2._previous()
    validator = getattr(previous, "validate_executor_binding", None)
    if not callable(validator):
        raise ValueError("Pushed v2 predecessor executor-validator API drifted")
    validator(closed, source, v2_work)
    if hashlib.sha256(v2.canonical(schedule)).hexdigest() != contract()["schedule"]["sha256"]:
        raise ValueError("V2 schedule commitment drifted")
    return schedule, execution


def prepare(closed: Path, source: Path, v2_work: Path, work: Path) -> dict[str, Any]:
    v2, work = _load_v2(), _outside_repo(work)
    if work.exists() and any(work.iterdir()):
        raise ValueError("V3 execution root must be truly empty")
    schedule, execution = _base(v2, closed, source, v2_work)
    work.mkdir(parents=True, exist_ok=True)
    binding = {"format_version": 1, "study_id": contract()["study_id"], "contract": _commitment(CONTRACT, root=HERE), "provider": contract()["provider"], "v2_runtime": _v2_projection(), "v3_runtime": _v3_runtime(), "v2_work": {"binding_sha256": sha(v2_work / v2.CAPACITY_BINDING), "executor_binding_sha256": sha(v2_work / v2._previous().EXECUTOR_BINDING), "schedule_sha256": hashlib.sha256(v2.canonical(schedule)).hexdigest(), "lineage_execution_sha256": sha(v2_work / v2._previous().EXECUTION)}}
    (work / BINDING).write_bytes(canonical(binding) + b"\n")
    for row in schedule:
        _append(work / SCHEDULE, row)
    return {"provider_calls": 0, "cells": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"]}


def _verify(closed: Path, source: Path, v2_work: Path, work: Path) -> tuple[Any, Any, list[dict[str, Any]], dict[str, Any]]:
    v2, work = _load_v2(), _outside_repo(work)
    schedule, execution = _base(v2, closed, source, v2_work)
    binding = read_json(work / BINDING)
    previous = v2._previous()
    expected = {"format_version": 1, "study_id": contract()["study_id"], "contract": _commitment(CONTRACT, root=HERE), "provider": contract()["provider"], "v2_runtime": _v2_projection(), "v3_runtime": _v3_runtime(), "v2_work": {"binding_sha256": sha(v2_work / v2.CAPACITY_BINDING), "executor_binding_sha256": sha(v2_work / previous.EXECUTOR_BINDING), "schedule_sha256": hashlib.sha256(v2.canonical(schedule)).hexdigest(), "lineage_execution_sha256": sha(v2_work / previous.EXECUTION)}}
    if binding != expected or _rows(work / SCHEDULE) != schedule:
        raise ValueError("V3 prepared provenance drifted")
    return v2, previous, schedule, execution


def _completed(work: Path, schedule: list[dict[str, Any]], previous: Any) -> list[dict[str, Any]]:
    rows = _rows(work / JOURNAL)
    if len(rows) % 3:
        raise ValueError("Unresolved attempt intent; stop without resend")
    completed: list[dict[str, Any]] = []
    for index in range(0, len(rows), 3):
        proof, intent, result = rows[index:index + 3]
        event = schedule[len(completed)] if len(completed) < len(schedule) else None
        proof_sha = proof.get("capacity_proof_sha256")
        proof_path = work / PROOFS / f"{proof_sha}.json"
        if event is None or proof.get("event") != "capacity-checked" or not isinstance(proof_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", proof_sha) or not proof_path.is_file() or sha(proof_path) != proof_sha or intent != {"event": "attempt-intent", "sequence": event["sequence"], "capacity_proof_sha256": proof_sha} or result.get("event") != "completed" or result.get("sequence") != event["sequence"] or result.get("capacity_proof_sha256") != proof_sha or not isinstance(result.get("output_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", result["output_sha256"]):
            raise ValueError("Execution journal is not an append-only contiguous prefix")
        target = previous._binding_path(work, event)
        if not target.is_file() or sha(target) != result["output_sha256"]:
            raise ValueError("Completed cell output commitment drifted")
        completed.append(event)
    return completed


def execute_one(closed: Path, source: Path, v2_work: Path, work: Path, capacity_evidence: Path, *, timeout: float = 3600.0, allow_remote: bool = False, now: datetime | None = None) -> dict[str, Any]:
    v2, previous, schedule, execution = _verify(closed, source, v2_work, work)
    if not allow_remote:
        raise ValueError("This executor sends disclosed writing to Codex; pass --allow-remote only after review")
    receipt = v2.validate_capacity_evidence(capacity_evidence, now=now)
    claim = _acquire_claim(work, source)
    settled = False
    try:
        completed = _completed(work, schedule, previous)
        if len(completed) == len(schedule):
            settled = True
            return {"provider_calls": 0, "completed": len(completed), "remaining": 0}
        event = schedule[len(completed)]
        proof_bytes = canonical(receipt) + b"\n"
        proof_sha = hashlib.sha256(proof_bytes).hexdigest()
        proof_path = work / PROOFS / f"{proof_sha}.json"
        proof_path.parent.mkdir(exist_ok=True)
        if proof_path.exists() and proof_path.read_bytes() != proof_bytes:
            raise ValueError("Capacity proof hash collision or mutation")
        if not proof_path.exists():
            proof_path.write_bytes(proof_bytes)
        _append(work / JOURNAL, {"event": "capacity-checked", "sequence": event["sequence"], "capacity_proof_sha256": proof_sha, "observed_at": receipt["observed_at"]})
        _append(work / JOURNAL, {"event": "attempt-intent", "sequence": event["sequence"], "capacity_proof_sha256": proof_sha})
        frozen = previous.read_json(source / "frozen-run-contract.json")
        previous._revalidate_predecessor_event(source, frozen, event)
        previous._run_event(previous._v1_runner(), event, frozen, source, work, timeout)
        v2.validate_fresh_sessions(work / "runs", execution)
        target = previous._binding_path(work, event)
        _append(work / JOURNAL, {"event": "completed", "sequence": event["sequence"], "capacity_proof_sha256": proof_sha, "output_sha256": sha(target)})
        settled = True
        return {"provider_calls": 1, "completed": len(completed) + 1, "remaining": len(schedule) - len(completed) - 1, "sequence": event["sequence"]}
    finally:
        if settled:
            claim.unlink(missing_ok=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("closed", type=Path); parser.add_argument("source", type=Path); parser.add_argument("v2_work", type=Path); parser.add_argument("work", type=Path)
    parser.add_argument("--capacity-evidence", type=Path); parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--dry-run", action="store_true"); parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps(prepare(args.closed, args.source, args.v2_work, args.work), sort_keys=True)); return
    if args.capacity_evidence is None:
        parser.error("--capacity-evidence is required for a real one-cell epoch")
    print(json.dumps(execute_one(args.closed, args.source, args.v2_work, args.work, args.capacity_evidence, timeout=args.timeout, allow_remote=args.allow_remote), sort_keys=True))


if __name__ == "__main__":
    main()
