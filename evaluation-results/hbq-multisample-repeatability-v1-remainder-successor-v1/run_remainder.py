#!/usr/bin/env python3
"""Prepare a new root for the quota-stopped multisample remainder.

This program intentionally has no provider dispatch path.  Its output is the
immutable, source-bound handoff an exact frozen executor must consume after a
fresh quota preflight.  That separation prevents either accidental contact or
an in-place retry of the partial predecessor root.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from study import BINDING, CONTRACT_PATH, EXECUTION, HERE, JOURNAL, RETRY_AFTER, bind_closed_successor, canonical, contract, fresh_schedule, immutable_json, parse_json_object, read_json, sha


PREVIOUS = HERE.parent / "hbq-multisample-repeatability-v1-successor-v1"
PREFLIGHT = "quota-preflight.json"
AUTHORIZATION = "launch-authorization.json"
EXECUTOR_BINDING = "executor-binding.json"
MAX_PREFLIGHT_AGE = timedelta(minutes=10)
AUTHORIZATION_TTL = timedelta(minutes=10)


def _load_previous(name: str, filename: str) -> Any:
    previous_study = sys.modules.get("study")
    spec = importlib.util.spec_from_file_location(name, PREVIOUS / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load predecessor helper: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        if filename != "study.py":
            study_spec = importlib.util.spec_from_file_location("study", PREVIOUS / "study.py")
            if study_spec is None or study_spec.loader is None:
                raise RuntimeError("Cannot load predecessor study helper")
            old_study = importlib.util.module_from_spec(study_spec)
            sys.modules["study"] = old_study
            study_spec.loader.exec_module(old_study)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_study is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous_study


def _previous_runner() -> Any:
    return _load_previous("hbq_multisample_remainder_previous_runner", "run_successor.py")


def _outside_repo(path: Path) -> bool:
    repository = HERE.parents[1].resolve()
    resolved = path.resolve()
    return resolved != repository and repository not in resolved.parents


def _is_reparse(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except AttributeError:
        return path.is_symlink()
    return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def _plain_path(path: Path, *, allow_missing_leaf: bool = False) -> Path:
    absolute = path.absolute()
    probe = absolute if absolute.exists() else absolute.parent
    if not allow_missing_leaf and not absolute.exists():
        raise ValueError(f"Required root is missing: {absolute}")
    while True:
        if _is_reparse(probe):
            raise ValueError(f"Root path contains a symlink/reparse point: {probe}")
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    return absolute.resolve()


def _roots(closed_root: Path, source_root: Path, work: Path) -> tuple[Path, Path, Path]:
    closed = _plain_path(closed_root)
    source = _plain_path(source_root)
    output = _plain_path(work, allow_missing_leaf=True)
    for root, name in ((closed, "closed successor"), (source, "source")):
        if not root.is_dir() or _is_reparse(root) or not _outside_repo(root):
            raise ValueError(f"{name.title()} root must be a real external directory")
    if not _outside_repo(output):
        raise ValueError("Fresh remainder root must remain outside the repository")
    if any(left == right or left in right.parents or right in left.parents for left, right in ((closed, source), (closed, output), (source, output))):
        raise ValueError("Closed, source, and fresh remainder roots must be pairwise disjoint")
    if output.exists() and (not output.is_dir() or _is_reparse(output)):
        raise ValueError("Fresh remainder root must be a real directory when it exists")
    return closed, source, output


def _file_commitment(path: Path, *, root: Path | None = None) -> dict[str, Any]:
    original = _plain_path(path)
    if _is_reparse(path.absolute()):
        raise ValueError("Runtime commitment original path is a symlink/reparse point")
    if not original.is_file():
        raise ValueError(f"Required runtime file is missing: {original}")
    if root is not None and root != original and root not in original.parents:
        raise ValueError("Required runtime file escapes the executor root")
    relative = original.relative_to(root).as_posix() if root is not None else original.as_posix()
    return {"path": relative, "bytes": original.stat().st_size, "sha256": sha(original)}


def _runtime_commitment() -> dict[str, Any]:
    paths = [CONTRACT_PATH, HERE / "study.py", HERE / "run_remainder.py", PREVIOUS / "study.py", PREVIOUS / "run_successor.py"]
    files = [_file_commitment(path) for path in paths]
    return {"files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def _executor_dependencies(root: Path, frozen: Mapping[str, Any], launcher: Path) -> list[Path]:
    arms = frozen.get("contract", {}).get("arms") if isinstance(frozen.get("contract"), Mapping) else None
    if not isinstance(arms, list):
        raise ValueError("Source frozen contract lacks arms")
    native_pairs: list[Path] = []
    for arm in arms:
        if not isinstance(arm, Mapping) or arm.get("kind") != "native":
            continue
        prompt, schema = arm.get("prompt"), arm.get("schema")
        if not isinstance(prompt, str) or not isinstance(schema, str):
            raise ValueError("Native arm lacks its exact prompt/schema pair")
        native_pairs.extend([(root / "evaluation-results" / "hbq-multisample-repeatability-v1" / prompt).absolute(), (root / "evaluation-results" / "hbq-multisample-repeatability-v1" / schema).absolute()])
    if len(native_pairs) != 10 or len({path.resolve() for path in native_pairs}) != 10:
        raise ValueError("Executor must bind all five distinct native-arm prompt/schema pairs")
    return [
        launcher,
        root / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-successor-v1" / "study.py",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-successor-v1" / "run_remainder.py",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-successor-v1" / "study-contract.json",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1" / "study.py",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1" / "run_study.py",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1" / "study-contract.json",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "study.py",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "run_successor.py",
        root / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "study-contract.json",
        root / "src" / "hbqrs" / "__init__.py",
        root / "src" / "hbqrs" / "runner.py",
        root / "src" / "hbqrs" / "longform_runner.py",
        root / "src" / "hbqrs" / "core.py",
        root / "src" / "hbqrs" / "paths.py",
        root / "registry" / "all_modules.json",
        root / "bundles" / "all_bundles.json",
        root / "prompts" / "judge" / "JUDGE_PREFIX.md",
        root / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md",
        root / "schema" / "hbq_judge_response.schema.json",
        root / "schema" / "hbq_verdict.schema.json",
        root / "schema" / "hbq_task_contract.schema.json",
        root / "schema" / "hbq_diagnostic_report.schema.json",
        *native_pairs,
    ]


def _clean_executor_projection(root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=10).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=root, text=True, timeout=10).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Executor root lacks an exact clean source projection") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != upstream or dirty:
        raise ValueError("Executor root must be clean and exactly pushed to its upstream")
    for file in files:
        try:
            subprocess.check_output(["git", "ls-files", "--error-unmatch", "--", file["path"]], cwd=root, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("Executor dependency is not tracked by the exact source projection") from exc
    return {"git": {"head": head, "upstream": upstream}, "files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def bind_executor(executor_root: Path, launcher: Path, closed_root: Path, source_root: Path, work: Path) -> dict[str, Any]:
    """Commit a separately reviewed executor and every HBQ input it can dispatch."""
    closed, source, output = _roots(closed_root, source_root, work)
    root = _plain_path(executor_root)
    launch = _plain_path(launcher)
    if not root.is_dir() or not _outside_repo(root) or root not in launch.parents:
        raise ValueError("Executor and launcher must be external and the launcher must be inside its root")
    if any(left == root or left in root.parents or root in left.parents for left in (closed, source, output)):
        raise ValueError("Executor root must be pairwise disjoint from closed, source, and fresh roots")
    previous = _previous_runner()
    _, frozen = _source_binding(source, previous)
    required = _executor_dependencies(root, frozen, launch)
    files = [_file_commitment(path, root=root) for path in required]
    if len({file["path"] for file in files}) != len(files):
        raise ValueError("Executor dependency projection contains duplicate paths")
    projection = _clean_executor_projection(root, files)
    return {"format_version": 1, "executor_root": root.as_posix(), "launcher": _file_commitment(launch, root=root), "runtime": projection, "sha256": hashlib.sha256(canonical(projection)).hexdigest()}


def validate_executor_binding(closed_root: Path, source_root: Path, work: Path) -> dict[str, Any]:
    """Reconstruct the stored executor binding before it can influence a handoff."""
    binding_path = work / EXECUTOR_BINDING
    binding = read_json(binding_path)
    if set(binding) != {"format_version", "executor_root", "launcher", "runtime", "sha256"} or binding.get("format_version") != 1:
        raise ValueError("Persisted executor binding has unexpected top-level keys")
    root_value, launcher_value, runtime = binding.get("executor_root"), binding.get("launcher"), binding.get("runtime")
    if not isinstance(root_value, str) or not isinstance(launcher_value, Mapping) or not isinstance(runtime, Mapping):
        raise ValueError("Persisted executor binding has invalid root, launcher, or runtime")
    if set(launcher_value) != {"path", "bytes", "sha256"} or not isinstance(launcher_value.get("path"), str):
        raise ValueError("Persisted executor binding launcher is malformed")
    if set(runtime) != {"git", "files", "sha256"} or not isinstance(runtime.get("git"), Mapping) or not isinstance(runtime.get("files"), list):
        raise ValueError("Persisted executor binding runtime is malformed")
    if set(runtime["git"]) != {"head", "upstream"} or not all(isinstance(runtime["git"].get(key), str) and re.fullmatch(r"[0-9a-f]{40}", runtime["git"][key]) for key in ("head", "upstream")):
        raise ValueError("Persisted executor binding Git projection is malformed")
    files = runtime["files"]
    if len(files) != 33 or any(not isinstance(file, Mapping) or set(file) != {"path", "bytes", "sha256"} or not isinstance(file.get("path"), str) or not isinstance(file.get("bytes"), int) or not isinstance(file.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", file["sha256"]) for file in files):
        raise ValueError("Persisted executor binding does not contain the exact 33-file projection")
    if len({file["path"] for file in files}) != 33 or launcher_value not in files:
        raise ValueError("Persisted executor binding launcher is not a unique member of its runtime projection")
    if runtime.get("sha256") != hashlib.sha256(canonical(files)).hexdigest() or binding.get("sha256") != hashlib.sha256(canonical(runtime)).hexdigest():
        raise ValueError("Persisted executor binding internal hashes drifted")
    root = Path(root_value)
    launcher = root / str(launcher_value["path"])
    reconstructed = bind_executor(root, launcher, closed_root, source_root, work)
    if reconstructed != binding:
        raise ValueError("Persisted executor binding does not match its reconstructed exact projection")
    return binding


def _source_binding(source_root: Path, previous: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = previous.bind_predecessor(source_root)
    frozen = read_json(source_root / "frozen-run-contract.json")
    return binding, frozen


def _session_ids(value: Any) -> list[str]:
    values: list[str] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            session = current.get("session_id")
            if isinstance(session, str):
                values.append(session)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return values


def _lineage_sessions(root: Path) -> dict[str, Any]:
    """Commit session identifiers without copying them into the new handoff."""
    values: list[str] = []
    for path in sorted(root.rglob("*.json")):
        values.extend(_session_ids(read_json(path)))
    for path in sorted(root.rglob("*.jsonl")):
        raw = path.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise ValueError("Lineage JSONL has an uncertain partial tail")
        for line in raw.splitlines():
            values.extend(_session_ids(parse_json_object(line.decode("utf-8"), str(path))))
    unique = sorted(set(values))
    digest_items = [hashlib.sha256(item.encode("utf-8")).hexdigest() for item in unique]
    return {"occurrence_count": len(values), "unique_count": len(unique), "ids_sha256": digest_items, "set_sha256": hashlib.sha256(canonical(digest_items)).hexdigest()}


def validate_fresh_sessions(run_root: Path, execution: Mapping[str, Any]) -> dict[str, Any]:
    lineage = execution.get("lineage_sessions")
    if not isinstance(lineage, Mapping) or not isinstance(lineage.get("source"), Mapping) or not isinstance(lineage.get("closed"), Mapping):
        raise ValueError("Execution contract lacks source and closed session commitments")
    observed = _lineage_sessions(run_root)
    if observed["unique_count"] < 1:
        raise ValueError("Fresh executor output lacks session evidence")
    historical = set(lineage["source"].get("ids_sha256", [])) | set(lineage["closed"].get("ids_sha256", []))
    if historical.intersection(observed["ids_sha256"]):
        raise ValueError("Fresh executor session collides with source or closed lineage")
    return observed


def _append(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError("Remainder journal write was partial")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_output_journal(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError("Remainder journal has an uncertain partial tail")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        rows.append(parse_json_object(line.decode("utf-8"), "remainder journal row"))
    return rows


def _seal_schedule(work: Path, schedule: list[Mapping[str, Any]]) -> None:
    journal = work / JOURNAL
    existing = _read_output_journal(journal)
    if existing:
        if existing != schedule:
            raise ValueError("Fresh remainder journal is not the sealed plan")
        return
    for event in schedule:
        _append(journal, event)


def _prepared_values(closed_root: Path, source_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    closed = bind_closed_successor(closed_root)
    previous = _previous_runner()
    source_binding, frozen = _source_binding(source_root, previous)
    inherited = read_json(closed_root / "predecessor-binding.json")
    if source_binding != inherited:
        raise ValueError("Source root does not exactly match the closed successor's immutable predecessor binding")
    closed_plan = previous._successor_plans(frozen)
    schedule = fresh_schedule(closed_root)
    if [{key: value for key, value in event.items() if key not in {"event", "fresh_dispatch"}} for event in schedule] != [{key: value for key, value in event.items() if key != "event"} for event in closed_plan[101:]]:
        raise ValueError("Fresh-only remainder is not the sealed uncompleted schedule")
    execution = {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "closed_successor_binding_sha256": hashlib.sha256(canonical(closed)).hexdigest(),
        "source_binding_sha256": hashlib.sha256(canonical(source_binding)).hexdigest(),
        "schedule_sha256": hashlib.sha256(canonical(schedule)).hexdigest(),
        "runtime": _runtime_commitment(),
        "lineage_sessions": {"source": _lineage_sessions(source_root), "closed": _lineage_sessions(closed_root)},
        "provider_contact": {
            "permitted_only_after": RETRY_AFTER,
            "requires": "a current external quota observation plus launch-time revalidation by a separately reviewed bound executor",
            "provider_calls_during_prepare": 0,
        },
        "executor": {
            "status": "unbound_non_executable_handoff",
            "before_dispatch": "A separately reviewed executor must bind its launcher, hbqrs runner, prompts, schemas, registry, bundles, and runtime with bind_executor().",
        },
        "output_session_contract": {
            "root_must_be_fresh": True,
            "no_output_or_session_may_be_reused_from_closed_root": True,
            "fresh_session_ids_must_be_unique_against_source_and_closed_lineage": True,
            "each_completed_cell_must_bind_its_output_sha256_in_the_new_journal": True,
        },
    }
    return closed, schedule, execution


def prepare(closed_root: Path, source_root: Path, work: Path) -> dict[str, Any]:
    closed_root, source_root, work = _roots(closed_root, source_root, work)
    if work.exists() and any(work.iterdir()):
        raise ValueError("Fresh remainder root must be truly empty; do not resume in place")
    closed, schedule, execution = _prepared_values(closed_root, source_root)
    immutable_json(work / BINDING, closed)
    immutable_json(work / EXECUTION, execution)
    _seal_schedule(work, schedule)
    return {"provider_calls": 0, "cells": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"], "execution": execution}


def _parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Quota preflight {field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Quota preflight {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Quota preflight {field} must include a timezone")
    return parsed.astimezone(UTC)


def validate_external_quota_evidence(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Validate only the shape/freshness of external evidence, never provider access.

    A local JSON file cannot prove quota availability.  This validation therefore
    creates a non-executable handoff; the future reviewed executor must make and
    bind its own native launch-time observation.
    """
    receipt = read_json(path)
    checked = _parse_time(receipt.get("observed_at"), "observed_at")
    retry_after = _parse_time(RETRY_AFTER, "retry_after")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if receipt.get("kind") != "external_current_quota_evidence_v1" or receipt.get("provider") != "codex" or receipt.get("model") != "gpt-5.6-sol" or receipt.get("assertion") != "quota_available":
        raise ValueError("External quota evidence does not identify the required Codex GPT-5.6 Sol observation")
    if checked < retry_after or current < retry_after:
        raise ValueError("External quota evidence is before the closed-run retry time")
    if checked > current + timedelta(minutes=1) or current - checked > MAX_PREFLIGHT_AGE:
        raise ValueError("External quota evidence is not current")
    observation = receipt.get("observation")
    if not isinstance(observation, Mapping) or observation.get("surface") != "native_codex_quota_surface" or not isinstance(observation.get("reference"), str) or not observation["reference"].strip():
        raise ValueError("External quota evidence requires a non-hash native observation reference")
    return receipt


def _verify_prepared(closed_root: Path, source_root: Path, work: Path, *, allow_executor_binding: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    closed_root, source_root, work = _roots(closed_root, source_root, work)
    if not work.is_dir() or (work / "runs").exists() or (work / PREFLIGHT).exists() or (work / AUTHORIZATION).exists():
        raise ValueError("Fresh root is not an untouched prepared handoff")
    expected_closed, expected_schedule, expected_execution = _prepared_values(closed_root, source_root)
    if read_json(work / BINDING) != expected_closed or read_json(work / EXECUTION) != expected_execution or _read_output_journal(work / JOURNAL) != expected_schedule:
        raise ValueError("Prepared handoff commitments drifted")
    permitted = {BINDING, EXECUTION, JOURNAL}
    if allow_executor_binding:
        permitted.add(EXECUTOR_BINDING)
    unexpected = {item.name for item in work.iterdir()} - permitted
    if unexpected:
        raise ValueError("Prepared handoff contains arbitrary preexisting files")
    return expected_schedule, expected_execution


def seal_executor_binding(executor_root: Path, launcher: Path, closed_root: Path, source_root: Path, work: Path) -> dict[str, Any]:
    _verify_prepared(closed_root, source_root, work)
    binding = bind_executor(executor_root, launcher, closed_root, source_root, work)
    immutable_json(work / EXECUTOR_BINDING, binding)
    return validate_executor_binding(closed_root, source_root, work)


def authorize(closed_root: Path, source_root: Path, work: Path, quota_preflight: Path, *, now: datetime | None = None) -> dict[str, Any]:
    schedule, execution = _verify_prepared(closed_root, source_root, work, allow_executor_binding=True)
    binding_path = work / EXECUTOR_BINDING
    if not binding_path.is_file():
        raise ValueError("Authorization requires a persisted separately reviewed executor binding")
    binding = validate_executor_binding(closed_root, source_root, work)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    receipt = validate_external_quota_evidence(quota_preflight, now=current)
    immutable_json(work / PREFLIGHT, receipt)
    authorization = {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "authorized_at": current.isoformat(),
        "expires_at": (current + AUTHORIZATION_TTL).isoformat(),
        "external_quota_evidence_sha256": sha(work / PREFLIGHT),
        "execution_contract_sha256": sha(work / EXECUTION),
        "schedule_journal_sha256": sha(work / JOURNAL),
        "executor_binding_sha256": sha(binding_path),
        "executable": False,
        "launch_time_revalidation": "Required at launch-time. A separately reviewed bound executor must independently obtain and bind a fresh native quota observation; this handoff is not provider authorization.",
        "dispatch": "Use only a separately reviewed bound executor; this preparer never calls a provider.",
    }
    immutable_json(work / AUTHORIZATION, authorization)
    return {"provider_calls": 0, "cells": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"], "execution": execution, "authorized": "non_executable_handoff"}


def validate_launch_handoff(closed_root: Path, source_root: Path, work: Path, *, now: datetime | None = None) -> dict[str, Any]:
    root = _plain_path(work)
    authorization = read_json(root / AUTHORIZATION)
    authorized = _parse_time(authorization.get("authorized_at"), "authorized_at")
    expires = _parse_time(authorization.get("expires_at"), "expires_at")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if expires - authorized != AUTHORIZATION_TTL or current < authorized:
        raise ValueError("Launch handoff authorization window is invalid")
    if current > expires:
        raise ValueError("Launch handoff authorization has expired; obtain current external quota evidence again")
    validate_executor_binding(closed_root, source_root, root)
    if authorization.get("executor_binding_sha256") != sha(root / EXECUTOR_BINDING):
        raise ValueError("Launch handoff executor binding drifted")
    if authorization.get("execution_contract_sha256") != sha(root / EXECUTION) or authorization.get("schedule_journal_sha256") != sha(root / JOURNAL):
        raise ValueError("Launch handoff execution commitments drifted")
    if authorization.get("external_quota_evidence_sha256") != sha(root / PREFLIGHT):
        raise ValueError("Launch handoff external quota evidence drifted")
    if authorization.get("executable") is not False:
        raise ValueError("Launch handoff must remain non-executable until the reviewed executor revalidates quota")
    return authorization


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("closed_root", type=Path)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("work", type=Path)
    parser.add_argument("--external-quota-evidence", type=Path)
    parser.add_argument("--authorize", action="store_true")
    parser.add_argument("--bind-executor-root", type=Path)
    parser.add_argument("--executor-launcher", type=Path)
    args = parser.parse_args()
    if args.bind_executor_root is not None or args.executor_launcher is not None:
        if args.authorize or args.external_quota_evidence is not None or args.bind_executor_root is None or args.executor_launcher is None:
            parser.error("executor binding requires both --bind-executor-root and --executor-launcher alone")
        result = seal_executor_binding(args.bind_executor_root, args.executor_launcher, args.closed_root, args.source_root, args.work)
    elif args.authorize:
        if args.external_quota_evidence is None:
            parser.error("--authorize requires --external-quota-evidence")
        result = authorize(args.closed_root, args.source_root, args.work, args.external_quota_evidence)
    elif args.external_quota_evidence is not None:
        parser.error("--external-quota-evidence requires --authorize")
    else:
        result = prepare(args.closed_root, args.source_root, args.work)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
