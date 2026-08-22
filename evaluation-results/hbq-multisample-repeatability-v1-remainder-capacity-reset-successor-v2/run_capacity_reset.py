#!/usr/bin/env python3
"""Create a capacity-reset handoff without contacting a model provider."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / "hbq-multisample-repeatability-v1-remainder-successor-v1"
CONTRACT_PATH = HERE / "study-contract.json"
CAPACITY_BINDING = "capacity-reset-binding.json"
CAPACITY_PREFLIGHT = "capacity-reset-preflight.json"
AUTHORIZATION = "capacity-reset-authorization.json"
MAX_PREFLIGHT_AGE = timedelta(minutes=10)
AUTHORIZATION_TTL = timedelta(minutes=10)
EXPECTED_CONTRACT = {
    "format_version": 1,
    "study_id": "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v2",
    "supersedes": {
        "study_id": "hbq-multisample-repeatability-v1-remainder-successor-v1",
        "study_contract_sha256": "339cbad16b6814f21629df2085062c03df17ee22cb7ad2bcde3ee48905a545ab",
        "scope": "capacity timing only",
    },
    "schedule": {"count": 153, "first_sequence": 178, "last_sequence": 330, "sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086"},
    "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "paid_api": False, "human_judgment": False},
    "capacity_gate": {"probe_kind": "external_current_capacity_evidence_v2", "max_age_seconds": 600, "launch_time_revalidation_required": True, "probe_authorizes_provider_contact": False},
    "runtime": {"source_files": ["run_capacity_reset.py"], "provider_dispatch": False, "executor_present": False},
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise ValueError(f"Immutable handoff artifact already exists: {path.name}")
    path.write_bytes(canonical(value) + b"\n")


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if value != EXPECTED_CONTRACT:
        raise ValueError("Capacity-reset contract semantics drifted")
    return value


def _file_commitment(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.parent != HERE:
        raise ValueError(f"Capacity-reset runtime file is invalid: {path}")
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _runtime_commitment() -> dict[str, Any]:
    files = [_file_commitment(HERE / name) for name in contract()["runtime"]["source_files"]]
    return {"files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def _previous() -> Any:
    previous_study = sys.modules.get("study")
    spec = importlib.util.spec_from_file_location("hbq_multisample_capacity_reset_previous", PREVIOUS / "run_remainder.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load immutable remainder handoff")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(PREVIOUS))
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(PREVIOUS))
        if previous_study is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous_study


def _expected_schedule(previous: Any, closed_root: Path, source_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sha(PREVIOUS / "study-contract.json") != contract()["supersedes"]["study_contract_sha256"]:
        raise ValueError("Immutable predecessor capacity contract drifted")
    if sha(PREVIOUS / "study-contract.json") != contract()["supersedes"]["study_contract_sha256"]:
        raise ValueError("Immutable predecessor capacity contract drifted")
    _, schedule, execution = previous._prepared_values(closed_root, source_root)
    frozen = contract()["schedule"]
    if len(schedule) != frozen["count"] or schedule[0]["sequence"] != frozen["first_sequence"] or schedule[-1]["sequence"] != frozen["last_sequence"]:
        raise ValueError("Capacity-reset schedule identity drifted")
    if hashlib.sha256(previous.canonical(schedule)).hexdigest() != frozen["sha256"]:
        raise ValueError("Capacity-reset schedule commitment drifted")
    return schedule, execution


def prepare(closed_root: Path, source_root: Path, work: Path) -> dict[str, Any]:
    previous = _previous()
    closed_root, source_root, work = previous._roots(closed_root, source_root, work)
    if work.exists() and any(work.iterdir()):
        raise ValueError("Capacity-reset output root must be truly empty")
    schedule, execution = _expected_schedule(previous, closed_root, source_root)
    work.mkdir(parents=True, exist_ok=True)
    previous.immutable_json(work / previous.BINDING, previous.bind_closed_successor(closed_root))
    previous.immutable_json(work / previous.EXECUTION, execution)
    previous._seal_schedule(work, schedule)
    binding = {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "contract": _file_commitment(CONTRACT_PATH),
        "provider": contract()["provider"],
        "runtime": _runtime_commitment(),
        "previous_contract_sha256": sha(PREVIOUS / "study-contract.json"),
        "previous_execution_sha256": sha(work / previous.EXECUTION),
        "schedule_journal_sha256": sha(work / previous.JOURNAL),
        "supersession": {
            "scope": "Replace only the predecessor's predicted retry timestamp with a fresh bounded capacity observation.",
            "preserves": "The 153-cell schedule, source selection, prompts, scoring, historical outputs, and failed attempts remain unchanged.",
            "capacity_gate": contract()["capacity_gate"],
        },
        "executor": "The immutable v1 executor-binding.json must be reconstructed before capacity authorization.",
        "provider_calls": 0,
    }
    immutable_json(work / CAPACITY_BINDING, binding)
    return {"provider_calls": 0, "cells": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"]}


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Capacity evidence {field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Capacity evidence {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Capacity evidence {field} must include a timezone")
    return parsed.astimezone(UTC)


def validate_capacity_evidence(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Check a current external observation without treating it as provider proof."""
    receipt = read_json(path)
    checked = _parse_time(receipt.get("observed_at"), "observed_at")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    provider = contract()["provider"]
    if receipt.get("kind") != contract()["capacity_gate"]["probe_kind"] or receipt.get("provider") != provider["provider"] or receipt.get("model") != provider["model"] or receipt.get("assertion") != "capacity_available":
        raise ValueError("Capacity evidence does not identify the required current Codex observation")
    if checked > current + timedelta(minutes=1) or current - checked > MAX_PREFLIGHT_AGE:
        raise ValueError("Capacity evidence is not current")
    observation = receipt.get("observation")
    if not isinstance(observation, Mapping) or observation.get("surface") != "native_codex_quota_surface" or not isinstance(observation.get("reference"), str) or not observation["reference"].strip():
        raise ValueError("Capacity evidence requires a nonempty native observation reference")
    return receipt


def _verify_prepared(closed_root: Path, source_root: Path, work: Path, *, allow_executor: bool = False, allow_authorization: bool = False) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    previous = _previous()
    closed_root, source_root, work = previous._roots(closed_root, source_root, work)
    schedule, execution = _expected_schedule(previous, closed_root, source_root)
    binding = read_json(work / CAPACITY_BINDING)
    if set(binding) != {"format_version", "study_id", "contract", "provider", "runtime", "previous_contract_sha256", "previous_execution_sha256", "schedule_journal_sha256", "supersession", "executor", "provider_calls"} or binding.get("format_version") != 1 or binding.get("study_id") != contract()["study_id"] or binding.get("contract") != _file_commitment(CONTRACT_PATH) or binding.get("provider") != contract()["provider"] or binding.get("runtime") != _runtime_commitment() or binding.get("previous_contract_sha256") != contract()["supersedes"]["study_contract_sha256"] or binding.get("previous_execution_sha256") != sha(work / previous.EXECUTION) or binding.get("schedule_journal_sha256") != sha(work / previous.JOURNAL) or not isinstance(binding.get("supersession"), Mapping) or binding["supersession"].get("capacity_gate") != contract()["capacity_gate"] or binding.get("provider_calls") != 0:
        raise ValueError("Capacity-reset binding drifted")
    if previous.read_json(work / previous.BINDING) != previous.bind_closed_successor(closed_root) or previous.read_json(work / previous.EXECUTION) != execution or previous._read_output_journal(work / previous.JOURNAL) != schedule:
        raise ValueError("Immutable 153-cell predecessor handoff drifted")
    permitted = {previous.BINDING, previous.EXECUTION, previous.JOURNAL, CAPACITY_BINDING}
    if allow_executor:
        permitted.add(previous.EXECUTOR_BINDING)
    if allow_authorization:
        permitted.update({CAPACITY_PREFLIGHT, AUTHORIZATION})
    unexpected = {item.name for item in work.iterdir()} - permitted
    if unexpected:
        raise ValueError("Capacity-reset handoff contains arbitrary preexisting files")
    return previous, schedule, execution


def seal_executor_binding(executor_root: Path, launcher: Path, closed_root: Path, source_root: Path, work: Path) -> dict[str, Any]:
    """Persist the unchanged v1 33-file core after v2 has bound the schedule."""
    previous, _, _ = _verify_prepared(closed_root, source_root, work)
    binding = previous.bind_executor(executor_root, launcher, closed_root, source_root, work)
    previous.immutable_json(work / previous.EXECUTOR_BINDING, binding)
    return previous.validate_executor_binding(closed_root, source_root, work)


def authorize(closed_root: Path, source_root: Path, work: Path, capacity_evidence: Path, *, now: datetime | None = None) -> dict[str, Any]:
    previous, schedule, _ = _verify_prepared(closed_root, source_root, work, allow_executor=True)
    if not (work / previous.EXECUTOR_BINDING).is_file():
        raise ValueError("Capacity authorization requires the immutable reviewed 33-file executor binding")
    executor = previous.validate_executor_binding(closed_root, source_root, work)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    receipt = validate_capacity_evidence(capacity_evidence, now=current)
    immutable_json(work / CAPACITY_PREFLIGHT, receipt)
    authorization = {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "authorized_at": current.isoformat(),
        "expires_at": (current + AUTHORIZATION_TTL).isoformat(),
        "capacity_evidence_sha256": sha(work / CAPACITY_PREFLIGHT),
        "capacity_reset_binding_sha256": sha(work / CAPACITY_BINDING),
        "contract_sha256": sha(CONTRACT_PATH),
        "runtime_sha256": _runtime_commitment()["sha256"],
        "provider": contract()["provider"],
        "schedule_journal_sha256": sha(work / previous.JOURNAL),
        "executor_binding_sha256": sha(work / previous.EXECUTOR_BINDING),
        "executable": False,
        "provider_calls": 0,
        "launch_time_revalidation": "A separately reviewed executor must independently revalidate current native Codex capacity, append only the next contiguous completion, and stop on an unresolved attempt.",
    }
    immutable_json(work / AUTHORIZATION, authorization)
    return {"provider_calls": 0, "cells": len(schedule), "executor_runtime_files": len(executor["runtime"]["files"]), "authorized": "non_executable_capacity_reset_handoff"}


def validate_launch_handoff(closed_root: Path, source_root: Path, work: Path, *, now: datetime | None = None) -> dict[str, Any]:
    previous, _, _ = _verify_prepared(closed_root, source_root, work, allow_executor=True, allow_authorization=True)
    authorization = read_json(work / AUTHORIZATION)
    authorized = _parse_time(authorization.get("authorized_at"), "authorized_at")
    expires = _parse_time(authorization.get("expires_at"), "expires_at")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if expires - authorized != AUTHORIZATION_TTL or current < authorized or current > expires:
        raise ValueError("Capacity-reset authorization window is invalid or expired")
    if authorization.get("study_id") != contract()["study_id"] or authorization.get("contract_sha256") != sha(CONTRACT_PATH) or authorization.get("runtime_sha256") != _runtime_commitment()["sha256"] or authorization.get("provider") != contract()["provider"] or authorization.get("capacity_evidence_sha256") != sha(work / CAPACITY_PREFLIGHT) or authorization.get("capacity_reset_binding_sha256") != sha(work / CAPACITY_BINDING) or authorization.get("schedule_journal_sha256") != sha(work / previous.JOURNAL) or authorization.get("executor_binding_sha256") != sha(work / previous.EXECUTOR_BINDING) or authorization.get("executable") is not False or authorization.get("provider_calls") != 0:
        raise ValueError("Capacity-reset authorization commitments drifted")
    previous.validate_executor_binding(closed_root, source_root, work)
    validate_capacity_evidence(work / CAPACITY_PREFLIGHT, now=current)
    return authorization


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("closed_root", type=Path)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--capacity-evidence", type=Path)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--bind-executor-root", type=Path)
    parser.add_argument("--executor-launcher", type=Path)
    args = parser.parse_args()
    if args.bind_executor_root is not None or args.executor_launcher is not None:
        if args.authorize or args.capacity_evidence is not None or args.bind_executor_root is None or args.executor_launcher is None:
            parser.error("executor binding requires both --bind-executor-root and --executor-launcher alone")
        result = seal_executor_binding(args.bind_executor_root, args.executor_launcher, args.closed_root, args.source_root, args.work)
    elif args.authorize:
        if args.capacity_evidence is None:
            parser.error("--authorize requires --capacity-evidence")
        result = authorize(args.closed_root, args.source_root, args.work, args.capacity_evidence)
    elif args.capacity_evidence is not None:
        parser.error("--capacity-evidence requires --authorize")
    else:
        result = prepare(args.closed_root, args.source_root, args.work)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
