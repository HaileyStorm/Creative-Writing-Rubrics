#!/usr/bin/env python3
"""Settle the V6 pre-contact stop and execute the untouched 182-330 suffix.

The v4 and v5 roots are evidence, not resumable workspaces.  This successor
therefore validates them without writing to either root, creates a fresh
external work root, and settles one logical sequence at a time in ascending
order.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping


def _lexical_package_file() -> Path:
    path = Path(__file__).absolute()
    probe = path
    while True:
        try:
            metadata = probe.lstat()
        except FileNotFoundError as exc:
            raise ValueError(f"V7 package path is missing: {probe}") from exc
        if stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400):
            raise ValueError(f"V7 package path contains a symlink/reparse point: {probe}")
        if probe.parent == probe:
            break
        probe = probe.parent
    return path


HERE = _lexical_package_file().parent
REPO = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
REMAINDER_STUDY = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-successor-v1" / "study.py"
SUCCESSOR_STUDY = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "study.py"
SUCCESSOR_RUNNER = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v2" / "run_successor.py"
PREDECESSOR_RUNNER = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "run_successor.py"
SOURCE_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
CLOSED_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff")
V6_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v6-live-unique")

BINDING = "v7-binding.json"
ADMISSION = "admitted-v6-prefix.json"
FORENSIC_SETTLEMENT = "forensic-sequence-181-settlement.json"
COHORT_POLICY = "cohort-compatibility-policy.json"
OVERRIDES = "scope-compatibility-overrides"
SCHEDULE = "schedule.jsonl"
JOURNAL = "execution-journal.jsonl"
CLAIM = "active-epoch-claim.json"
PROOFS = "capacity-proofs"
MAX_WORKERS = 1
MAX_PREFLIGHT_AGE = timedelta(seconds=600)
DISCLOSURE = "preflight-disclosure.json"
DISCLOSURE_ACK = "disclosure-acknowledgement.json"
RETRY_DISCLOSURES = "retry-disclosures"
RETRY_ACKS = "retry-disclosure-acknowledgements"
UNRESOLVED_RECOVERY = "unresolved-attempt-recovery.json"
V1_ROOT = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1"
REGISTRY = REPO / "registry" / "all_modules.json"
BUNDLES = REPO / "bundles" / "all_bundles.json"
REMAINDER_COMMIT = "843be2f6e1bc62cf09f04b44b3ce5bf17818114d"
REMAINDER_STUDY_GIT_BLOB_OID_SHA1 = "e60dde59e0c8d3a52bea42bc09b69b79a3e0d047"

V6_RUNTIME_HEAD = "742e767c209a466dbafb5d33a2a179e1f85f9627"
EXPECTED_V6_BINDING = "04a7385c9c5a32e718fbc6ec6bc64681fb365edd7fec76a456f0c25c978f63fa"
EXPECTED_V6_SCHEDULE = "fb50b070e1227974f40727f392d2cb4a15c3ec3cdadd0f7804c045f4084f5dad"
EXPECTED_V6_JOURNAL = "cb9215cb97f6b4317352e2f6d957007c96a22c9a7307ab535d11f99d9ec9e1c5"
EXPECTED_V6_CLAIM = "ae7b8ce9993388a706b7719761c24ae099780951c4b3b47503534a3af02d025d"
EXPECTED_V6_DISCLOSURE = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
EXPECTED_V6_ACK = "663acdd1aac5d41dcd9ab76bf482f4bbd5bdc1e11b0abdfb2d7acba630815b93"
EXPECTED_V6_CAPTURED_COMMAND_SHA256 = "5c6fa84e42045ca948c72f5d40a0bf19e42df9ab83ae3f00cc26bb7c4073e4b9"
EXPECTED_COHORT_POLICY = "399e1ae6f7feccbb4772aa92cd125de9e273c115d6d31586a956ed918c09234b"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(_plain_path(path).read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    path = _plain_path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON object: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    path = _plain_path(path, allow_missing_leaf=True)
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError(f"Immutable v6 artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise ValueError(f"Uncertain partial v6 artifact exists: {temporary.name}")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    if (
        value.get("format_version") != 1
        or value.get("study_id") != "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v7"
        or value.get("supersedes", {}).get("v6_runtime_commit") != V6_RUNTIME_HEAD
        or value.get("schedule", {}).get("sha256") != "7866694887a6abcfb78fea4dd220e7ce3c5bb7ebbd85bc529ef18f06fddf89e8"
        or value.get("schedule", {}).get("count") != 150
        or value.get("schedule", {}).get("first_sequence") != 181
        or value.get("schedule", {}).get("last_sequence") != 330
        or value.get("admitted_prefix", {}).get("v6_journal_sha256") != EXPECTED_V6_JOURNAL
        or value.get("cohort_compatibility_policy") != {"path": COHORT_POLICY, "sha256": EXPECTED_COHORT_POLICY}
    ):
        raise ValueError("V6 study contract drifted")
    return value


def _is_reparse(path: Path) -> bool:
    try:
        return bool(path.lstat().st_file_attributes & 0x400)
    except FileNotFoundError:
        return False
    except AttributeError:
        return path.is_symlink()


def _plain_path(path: Path, *, allow_missing_leaf: bool = False) -> Path:
    absolute = path.absolute()
    probe = absolute if absolute.exists() else absolute.parent
    if not allow_missing_leaf and not absolute.exists():
        raise ValueError(f"Required path is missing: {absolute}")
    while True:
        if _is_reparse(probe):
            raise ValueError(f"Root path contains a symlink/reparse point: {probe}")
        parent = probe.parent
        if parent == probe:
            break
        probe = parent
    return absolute


def _external(path: Path, *, allow_missing_leaf: bool = False) -> Path:
    resolved = _plain_path(path, allow_missing_leaf=allow_missing_leaf)
    repo = _plain_path(REPO)
    if resolved == repo or repo in resolved.parents:
        raise ValueError("Multisample evidence/work roots must remain outside the CWR repository")
    return resolved


def _work_path(work: Path, *parts: str, allow_missing_leaf: bool = True) -> Path:
    """Return an in-root path only after rejecting every redirecting ancestor."""
    root = _external(work)
    if not root.is_dir():
        raise ValueError("Prepared v6 work root is missing or not a directory")
    candidate = _plain_path(root.joinpath(*parts), allow_missing_leaf=allow_missing_leaf)
    if candidate != root and root not in candidate.parents:
        raise ValueError("V6 work artifact escapes its prepared root")
    return candidate


def _roots(source: Path, closed: Path, v6: Path, work: Path) -> tuple[Path, Path, Path, Path]:
    source_r, closed_r, v6_r = (_external(source), _external(closed), _external(v6))
    work_r = _external(work, allow_missing_leaf=True)
    if not source_r.is_dir() or not closed_r.is_dir() or not v6_r.is_dir():
        raise ValueError("Source, closed, and V6 roots have the wrong type")
    roots = (source_r, closed_r, v6_r, work_r)
    for left_index, left in enumerate(roots):
        for right in roots[left_index + 1:]:
            # A missing work root is still its literal intended leaf after its
            # existing ancestry has been reparse-checked; sibling roots share
            # a parent safely, while containment remains unsafe.
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("Source, closed, evidence, and fresh work roots must be disjoint")
    if work_r.exists() and not work_r.is_dir():
        raise ValueError("Fresh v6 work root must be a directory")
    for root, label in ((source_r, "Source root"), (closed_r, "Closed root"), (v6_r, "V6 evidence root")):
        _assert_plain_tree(root, label)
    return roots


def _manifest(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if _is_reparse(path):
            raise ValueError(f"Evidence root contains a reparse/symlink entry: {path}")
        if path.is_file():
            rows.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)})
    return sorted(rows, key=lambda row: row["path"])


def _assert_plain_tree(root: Path, label: str) -> None:
    root = _plain_path(root)
    if not root.is_dir():
        raise ValueError(f"{label} is missing or not a directory")
    for path in [root, *root.rglob("*")]:
        if _is_reparse(path):
            raise ValueError(f"{label} contains a symlink/reparse entry: {path}")


def _manifest_sha(rows: list[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical(rows)).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    path = _plain_path(path)
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ValueError(f"JSONL has an uncertain partial tail: {path.name}")
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSONL: {path.name}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL record is not an object: {path.name}")
        rows.append(value)
    return rows


def _session_ids(value: Any) -> list[str]:
    found: list[str] = []
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, Mapping):
            if isinstance(item.get("session_id"), str):
                found.append(item["session_id"])
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


def _pid_is_dead(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    except OSError as exc:
        if getattr(exc, "winerror", None) == 87:
            return True
        raise
    return False


def admit_v6_prefix(v6_root: Path = V6_DEFAULT) -> dict[str, Any]:
    """Validate V6 without recovery, mutation, or inference from absence alone."""
    v6 = _external(v6_root)
    if not v6.is_dir():
        raise ValueError("V6 immutable evidence root is missing")
    expected = contract()["admitted_prefix"]
    files = {
        "binding": v6 / "v6-binding.json",
        "schedule": v6 / SCHEDULE,
        "journal": v6 / JOURNAL,
        "claim": v6 / CLAIM,
        "disclosure": v6 / DISCLOSURE,
        "acknowledgement": v6 / DISCLOSURE_ACK,
    }
    required_hashes = {
        "binding": EXPECTED_V6_BINDING, "schedule": EXPECTED_V6_SCHEDULE,
        "journal": EXPECTED_V6_JOURNAL, "claim": EXPECTED_V6_CLAIM,
        "disclosure": EXPECTED_V6_DISCLOSURE, "acknowledgement": EXPECTED_V6_ACK,
    }
    if any(not path.is_file() or sha(path) != required_hashes[name] for name, path in files.items()):
        raise ValueError("V6 immutable binding, schedule, journal, claim, disclosure, or acknowledgement drifted")
    binding = read_json(files["binding"])
    if binding.get("study_id") != "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v6" or binding.get("runtime", {}).get("git") != {"head": V6_RUNTIME_HEAD, "upstream": V6_RUNTIME_HEAD}:
        raise ValueError("V6 runtime identity drifted")
    schedule = _jsonl(files["schedule"])
    if [row.get("sequence") for row in schedule] != list(range(179, 331)):
        raise ValueError("V6 schedule order drifted")
    v6_event_181 = schedule[2]
    expected_v6_event_181 = {"sequence": 181, "item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    if {key: v6_event_181.get(key) for key in expected_v6_event_181} != expected_v6_event_181:
        raise ValueError("V6 schedule does not identify the sealed sequence-181 cell")
    rows = _jsonl(files["journal"])
    expected_events = ["admitted-prefix", "attempt-intent", "provider-contacts", "completed", "attempt-intent", "provider-contacts", "completed", "attempt-intent"]
    if [row.get("event") for row in rows] != expected_events or [row.get("sequence") for row in rows[1:]] != [179, 179, 179, 180, 180, 180, 181]:
        raise ValueError("V6 journal is not the sealed 179/180 completion plus 181 intent")
    for sequence, output_sha in ((179, "f9f9de8d5d2a7d7cda0be14e2c45a20862a843318fadcaef7d5983161abfa1b1"), (180, "6dea9b78d536f4ba9e3a6920642e7c325c7d806dba6ac0ec1db220168bb8a3e5")):
        event = schedule[sequence - 179]
        target = _output_path(v6, event)
        if not target.is_file() or sha(target) != output_sha or _recorded_provider_contacts(v6, event) != 1:
            raise ValueError(f"V6 sequence-{sequence} output or contact evidence drifted")
    claim = read_json(files["claim"])
    if claim != {"arm_id": "hbq_short_story_batch32", "binding_sha256": EXPECTED_V6_BINDING, "claimed_at": "2026-08-27T21:16:09.994774+00:00", "format_version": 1, "item_id": "hanna-523", "pid": 17716, "sequence": 181, "source_frozen_contract_sha256": "5fb06e5a4775ecfe1cee10132e52100733c7e765e8eae9865374bb23f1addddd", "study_id": "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v6"} or any(claim.get(key) != v6_event_181[key] for key in ("sequence", "item_id", "arm_id")) or not _pid_is_dead(17716):
        raise ValueError("V6 sequence-181 claim is not the exact dead claim")
    settlement = read_json(HERE / FORENSIC_SETTLEMENT)
    projection = settlement.get("task_history_projection")
    settled = settlement.get("settled_sequence")
    expected_v6_evidence = {"binding_sha256": EXPECTED_V6_BINDING, "schedule_sha256": EXPECTED_V6_SCHEDULE, "journal_sha256": EXPECTED_V6_JOURNAL, "claim_sha256": EXPECTED_V6_CLAIM, "disclosure_sha256": EXPECTED_V6_DISCLOSURE, "acknowledgement_sha256": EXPECTED_V6_ACK}
    expected_locator = {"thread_id": "01a04440-c441-7701-8bb7-7e4d5e4ac110", "turn_id": "01a0450f-be14-7840-abe5-bed599403d4b", "command_item_id": "exec-0df77963-2a4e-4acb-a2a6-1a9328200f57", "exit_code": 1, "traceback_tail": ["HBQError: Task-contract bundle compatibility is unproven; supply a reviewed scope compatibility override or use the validated long-form workflow", "src/hbqrs/runner.py:1677 in _scope_compatibility"], "ordering": ["_scope_compatibility", "before_provider_attempt", "_call_codex"]}
    if (
        settlement.get("kind") != "v6_sequence_181_precontact_settlement"
        or settlement.get("not_provider_attestation") is not True
        or settlement.get("v6_evidence") != expected_v6_evidence
        or not isinstance(projection, Mapping)
        or any(projection.get(key) != item for key, item in expected_locator.items())
        or projection.get("captured_command_sha256") != EXPECTED_V6_CAPTURED_COMMAND_SHA256
        or not isinstance(projection.get("captured_command"), str)
        or hashlib.sha256(projection["captured_command"].encode("utf-8")).hexdigest() != EXPECTED_V6_CAPTURED_COMMAND_SHA256
        or not isinstance(settled, Mapping) or {key: settled.get(key) for key in expected_v6_event_181} != expected_v6_event_181 or settled.get("provider_contacts") != 0 or settled.get("claim_pid") != claim["pid"]
    ):
        raise ValueError("V7 forensic trace settlement is missing, forged, or insufficient")
    if (v6 / "runs" / "hanna-523").exists() or any(row.get("event") in {"provider-contacts", "completed"} and row.get("sequence") == 181 for row in rows):
        raise ValueError("V6 sequence-181 does not remain a trace-proven pre-contact stop")
    return {"sequence": 180, "v6_root": str(v6), "completed_sequences": [179, 180], "settled_precontact_sequence": 181, "v6_binding_sha256": EXPECTED_V6_BINDING, "v6_journal_sha256": EXPECTED_V6_JOURNAL, "forensic_settlement_sha256": sha(HERE / FORENSIC_SETTLEMENT), "admission_contract": expected}


def _load_module(path: Path, name: str, *, study_path: Path | None = None) -> Any:
    path = _plain_path(path)
    if study_path is not None:
        study_path = _plain_path(study_path)
    previous = sys.modules.get("study")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load pinned study component: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        if study_path is not None:
            study_spec = importlib.util.spec_from_file_location("study", study_path)
            if study_spec is None or study_spec.loader is None:
                raise RuntimeError(f"Cannot load pinned study dependency: {study_path}")
            study_module = importlib.util.module_from_spec(study_spec)
            sys.modules["study"] = study_module
            study_spec.loader.exec_module(study_module)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous
        sys.modules.pop(name, None)


def _load_remainder_study() -> Any:
    return _load_module(REMAINDER_STUDY, "v6_remainder_study")


def _load_successor_study() -> Any:
    return _load_module(SUCCESSOR_STUDY, "v6_successor_study")


def _load_successor_runner() -> Any:
    return _load_module(SUCCESSOR_RUNNER, "v7_dispatch_helper")


def _load_predecessor_runner() -> Any:
    return _load_module(PREDECESSOR_RUNNER, "v7_predecessor_runner", study_path=SUCCESSOR_STUDY)


def _load_hbq_runner() -> Any:
    return importlib.import_module("hbqrs.runner")


def _git_sha1_object_format() -> None:
    try:
        object_format = subprocess.check_output(["git", "rev-parse", "--show-object-format"], cwd=REPO, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("CWR Git object format is unavailable") from exc
    if object_format != "sha1":
        raise ValueError(f"Pinned Git SHA-1 object bindings require sha1 repository format, got {object_format!r}")


def _git_blob_sha1(commit: str, relative: str) -> str:
    _git_sha1_object_format()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Pinned Git commit is not a SHA-1 object ID")
    try:
        oid = subprocess.check_output(["git", "rev-parse", f"{commit}:{relative}"], cwd=REPO, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"Pinned Git source is unavailable: {relative}") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", oid):
        raise ValueError(f"Pinned Git blob is not a SHA-1 object ID: {relative}")
    return oid


def _pinned_successor_source() -> dict[str, Any]:
    commit = contract()["lineage"]["closed_successor_commit"]
    files = []
    for path in (SUCCESSOR_STUDY, SUCCESSOR_RUNNER):
        relative = path.relative_to(REPO).as_posix()
        _git_sha1_object_format()
        current = subprocess.check_output(["git", "hash-object", relative], cwd=REPO, text=True, timeout=10).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", current):
            raise ValueError(f"Current Git blob is not a SHA-1 object ID: {relative}")
        if path == SUCCESSOR_STUDY and current != _git_blob_sha1(commit, relative):
            raise ValueError("Closed successor source projection drifted")
        files.append({"path": relative, "bytes": path.stat().st_size, "git_blob_oid_sha1": current})
    return {"commit": commit, "files": files, "files_sha256": hashlib.sha256(canonical(files)).hexdigest()}


def _pinned_remainder_source() -> dict[str, Any]:
    commit = contract()["lineage"]["remainder_study_commit"]
    relative = REMAINDER_STUDY.relative_to(REPO).as_posix()
    _git_sha1_object_format()
    current = subprocess.check_output(["git", "hash-object", relative], cwd=REPO, text=True, timeout=10).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", current) or current != _git_blob_sha1(commit, relative) or current != REMAINDER_STUDY_GIT_BLOB_OID_SHA1:
        raise ValueError("Remainder study source projection drifted")
    return {"commit": commit, "path": relative, "bytes": REMAINDER_STUDY.stat().st_size, "git_blob_oid_sha1": current}


def _runtime_file(path: Path, *, require_tracked: bool = True) -> dict[str, Any]:
    resolved = _plain_path(path)
    repo = _plain_path(REPO)
    if not resolved.is_file() or resolved == repo or repo not in resolved.parents or _is_reparse(resolved):
        raise ValueError(f"Executed dependency is unavailable or escapes CWR: {path}")
    relative = resolved.relative_to(repo).as_posix()
    if require_tracked:
        try:
            subprocess.check_output(["git", "ls-files", "--error-unmatch", "--", relative], cwd=REPO, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"Executed dependency is not tracked: {relative}") from exc
    return {"path": relative, "bytes": resolved.stat().st_size, "sha256": sha(resolved)}


def _executed_dependencies(frozen: Mapping[str, Any]) -> list[Path]:
    paths = [
        REMAINDER_STUDY,
        SUCCESSOR_STUDY,
        SUCCESSOR_RUNNER,
        PREDECESSOR_RUNNER,
        V1_ROOT / "study.py",
        V1_ROOT / "run_study.py",
        V1_ROOT / "study-contract.json",
        REPO / "src" / "hbqrs" / "__init__.py",
        REPO / "src" / "hbqrs" / "core.py",
        REPO / "src" / "hbqrs" / "paths.py",
        REPO / "src" / "hbqrs" / "runner.py",
        REPO / "src" / "hbqrs" / "longform_runner.py",
        REPO / "src" / "hbqrs" / "longform.py",
        REPO / "src" / "hbqrs" / "weights.py",
        REGISTRY,
        BUNDLES,
        REPO / "prompts" / "judge" / "JUDGE_PREFIX.md",
        REPO / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md",
        REPO / "schema" / "hbq_judge_response.schema.json",
        REPO / "schema" / "hbq_verdict.schema.json",
        REPO / "schema" / "hbq_task_contract.schema.json",
        REPO / "schema" / "hbq_diagnostic_report.schema.json",
    ]
    arms = frozen.get("contract", {}).get("arms") if isinstance(frozen.get("contract"), Mapping) else None
    if not isinstance(arms, list):
        raise ValueError("Source frozen contract has no arms")
    for arm in arms:
        if isinstance(arm, Mapping) and arm.get("kind") == "native":
            prompt, schema = arm.get("prompt"), arm.get("schema")
            if not isinstance(prompt, str) or not isinstance(schema, str):
                raise ValueError("Native arm lacks its prompt/schema dependency")
            paths.extend([V1_ROOT / prompt, V1_ROOT / schema])
    unique: dict[str, Path] = {}
    for path in paths:
        unique[_plain_path(path).relative_to(_plain_path(REPO)).as_posix()] = path
    return [unique[key] for key in sorted(unique)]


def _runtime_projection(frozen: Mapping[str, Any]) -> dict[str, Any]:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, timeout=10).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=REPO, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Current CWR Git runtime is unavailable") from exc
    files = [_runtime_file(path, require_tracked=False) for path in [CONTRACT_PATH, HERE / COHORT_POLICY, HERE / "executor.py"]]
    files.extend(_runtime_file(path, require_tracked=False) for path in _executed_dependencies(frozen))
    if len({item["path"] for item in files}) != len(files):
        raise ValueError("Executed dependency projection contains duplicates")
    return {"git": {"head": head, "upstream": upstream}, "files": files, "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def _require_clean_pushed() -> None:
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, timeout=10).strip()
        upstream = subprocess.check_output(["git", "rev-parse", "@{u}"], cwd=REPO, text=True, timeout=10).strip()
        dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=REPO, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("A clean pushed CWR runtime is required for remote dispatch") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != upstream or dirty:
        raise ValueError("Remote dispatch requires a clean checkout exactly at its upstream")


def _fresh_schedule(closed_root: Path) -> list[dict[str, Any]]:
    remainder = _load_remainder_study()
    closed = remainder.bind_closed_successor(closed_root)
    if closed["remaining"] != {"count": 153, "first_sequence": 178, "last_sequence": 330}:
        raise ValueError("Closed successor remaining schedule drifted")
    full = remainder.fresh_schedule(closed_root)
    c = contract()["schedule"]
    if len(full) != 153 or [row.get("sequence") for row in full] != list(range(178, 331)) or hashlib.sha256(canonical(full)).hexdigest() != c["source_full_schedule_sha256"]:
        raise ValueError("Full capacity-reset schedule commitment drifted")
    schedule = full[3:]
    if len(schedule) != c["count"] or [row.get("sequence") for row in schedule] != list(range(c["first_sequence"], c["last_sequence"] + 1)) or hashlib.sha256(canonical(schedule)).hexdigest() != c["sha256"]:
        raise ValueError("V7 fresh schedule commitment drifted")
    return schedule


def _external_file_record(path: Path, root: Path, role: str) -> dict[str, Any]:
    resolved = _plain_path(path)
    root = _plain_path(root)
    if not resolved.is_file() or root not in resolved.parents:
        raise ValueError(f"Disclosure dependency is unavailable: {path}")
    return {"role": role, "identifier": resolved.relative_to(root).as_posix(), "bytes": resolved.stat().st_size, "sha256": sha(resolved)}


def _repo_file_record(path: Path, role: str) -> dict[str, Any]:
    record = _runtime_file(path)
    return {"role": role, "identifier": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}


def _outbound_text_record(path: Path, root: Path, role: str) -> dict[str, Any]:
    record = _external_file_record(path, root, role)
    try:
        text = _plain_path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Outbound text is not UTF-8: {path}") from exc
    return {**record, "utf8": text}


def _provider_payload(batch: int, prompt: bytes, response_schema: bytes, question_ids: list[str] | None = None) -> dict[str, Any]:
    try:
        request = {"prompt_utf8": prompt.decode("utf-8"), "response_schema_utf8": response_schema.decode("utf-8")}
    except UnicodeDecodeError as exc:
        raise ValueError("Rendered provider payload is not UTF-8") from exc
    payload: dict[str, Any] = {"batch": batch, "request": request}
    if question_ids is not None:
        payload["question_ids"] = question_ids
    return {**payload, "payload_sha256": hashlib.sha256(canonical(payload)).hexdigest()}


def _arm(frozen: Mapping[str, Any], event: Mapping[str, Any]) -> Mapping[str, Any]:
    arms = frozen.get("contract", {}).get("arms") if isinstance(frozen.get("contract"), Mapping) else None
    if not isinstance(arms, list):
        raise ValueError("Frozen contract has no arm definitions")
    matches = [item for item in arms if isinstance(item, Mapping) and item.get("arm_id") == event.get("arm_id")]
    if len(matches) != 1:
        raise ValueError(f"Frozen contract arm is unavailable: {event.get('arm_id')}")
    return matches[0]


def _event_disclosure(source: Path, event: Mapping[str, Any], frozen: Mapping[str, Any]) -> dict[str, Any]:
    folder = source / "inputs" / str(event["item_id"])
    source_file = folder / "source.md"
    prompt_file = folder / "prompt.md"
    task_contract = folder / "task-contract.json"
    outbound_artifacts = [
        _outbound_text_record(source_file, source, "artifact"),
        _outbound_text_record(prompt_file, source, "originating_prompt"),
    ]
    arm = _arm(frozen, event)
    rubric: list[dict[str, Any]] = []
    provider_payloads: list[dict[str, Any]]
    if arm.get("kind") == "native":
        prompt_name, schema_name = arm.get("prompt"), arm.get("schema")
        if not isinstance(prompt_name, str) or not isinstance(schema_name, str):
            raise ValueError("Native arm disclosure dependencies are malformed")
        rubric_file = V1_ROOT / prompt_name
        schema_file = V1_ROOT / schema_name
        rubric.append(_repo_file_record(rubric_file, "rubric"))
        successor_runner = _load_predecessor_runner()
        rendered = successor_runner._artifact_prompt(
            rubric_file.read_text(encoding="utf-8"),
            source_file.read_text(encoding="utf-8"),
            prompt_file.read_text(encoding="utf-8"),
        ).encode("utf-8")
        provider_schema = successor_runner._structured_json_bytes(
            successor_runner._provider_response_schema(read_json(schema_file))
        )
        provider_payloads = [_provider_payload(1, rendered, provider_schema, [])]
    else:
        outbound_artifacts.append(_outbound_text_record(task_contract, source, "task_contract"))
        runner = _load_hbq_runner()
        artifact = runner._read_text_record(source_file)
        contexts = [runner._read_text_record(prompt_file)]
        task_value = runner.load_data(task_contract)
        if not isinstance(task_value, Mapping):
            raise ValueError("HBQ task contract is not an object")
        modules = runner.load_modules(REGISTRY)
        bundle = runner.resolve_bundle(runner.load_bundles(BUNDLES), str(arm.get("bundle_id")))
        modules, bundle, _ = runner.materialize_weight_profile(modules, bundle, None)
        compiled = runner.compile_bundle(modules, bundle, task_contract=task_value)
        role_order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
        questions = sorted(
            runner.compiled_questions(compiled),
            key=lambda item: role_order.get(str(item.get("role")), 99),
        )
        prompt_records = [
            runner._read_text_record(runner.prompts_dir() / "judge" / "JUDGE_PREFIX.md"),
            runner._read_text_record(runner.prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"),
        ]
        binary_prompt = "\n\n".join(str(item["text"]).strip() for item in prompt_records)
        batch_size = arm.get("batch_size")
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError("HBQ arm batch size is malformed")
        provider_payloads = []
        for batch_number, start in enumerate(range(0, len(questions), batch_size), start=1):
            rendered = runner._render_prompt(
                binary_prompt=binary_prompt,
                artifact=artifact,
                contexts=contexts,
                bundle_id=str(arm["bundle_id"]),
                artifact_id=str(event["item_id"]),
                questions=questions[start : start + batch_size],
                task_contract_context=runner._task_contract_judge_context(task_value),
                provider="codex",
                model=str(frozen["contract"]["provider"]["model"]),
            ).encode("utf-8")
            provider_payloads.append(
                _provider_payload(
                    batch_number,
                    rendered,
                    runner._json_bytes(runner._response_schema()),
                    [str(item["question"]["id"]) for item in questions[start : start + batch_size]],
                )
            )
        rubric.extend([_repo_file_record(REGISTRY, "rubric_registry"), _repo_file_record(BUNDLES, "rubric_bundle")])
        rubric.extend(
            {
                "role": "judge_instruction",
                "identifier": str(record["path"]),
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
            for record in prompt_records
        )
    return {
        "sequence": event["sequence"],
        "item_id": event["item_id"],
        "arm_id": event["arm_id"],
        "repetition": event["repetition"],
        "source_path_identifier": source_file.relative_to(source).as_posix(),
        "outbound_artifacts": outbound_artifacts,
        "payload": {
            "provider_payloads": provider_payloads,
            "rubric": rubric,
        },
    }


def _cohort_policy() -> dict[str, Any]:
    path = _plain_path(HERE / COHORT_POLICY)
    policy = read_json(path)
    geometry = policy.get("shared_geometry")
    decision = policy.get("decision")
    entries = policy.get("entries")
    if (
        sha(path) != EXPECTED_COHORT_POLICY
        or policy.get("study_id") != contract()["study_id"]
        or policy.get("kind") != "engineering_reviewed_hanna_cohort_scope_compatibility_policy"
        or not isinstance(geometry, Mapping)
        or geometry != {"bundle_id": "prose.short_story", "contract_id": "hanna", "artifact_kind": "short prose fiction", "declared_scope": "complete short story", "compatibility_mode": "reviewed_override"}
        or not isinstance(decision, Mapping)
        or decision.get("reviewer") != "Codex continuity owner task 01a04440-c441-7701-8bb7-7e4d5e4ac110"
        or decision.get("reviewer_role") != "engineering agent, not human/user"
        or not isinstance(entries, list) or len(entries) != 11
    ):
        raise ValueError("V7 engineering-reviewed cohort compatibility policy drifted")
    ids = [entry.get("artifact_id") for entry in entries if isinstance(entry, Mapping)]
    if len(ids) != 11 or len(set(ids)) != 11 or any(not isinstance(entry.get("task_contract_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", entry["task_contract_sha256"]) for entry in entries if isinstance(entry, Mapping)):
        raise ValueError("V7 cohort policy entries are malformed")
    return policy


def _scope_override_value(source: Path, event: Mapping[str, Any], frozen: Mapping[str, Any]) -> dict[str, Any] | None:
    arm = _arm(frozen, event)
    if arm.get("kind") == "native":
        return None
    task_contract = read_json(source / "inputs" / str(event["item_id"]) / "task-contract.json")
    policy = _cohort_policy()
    geometry = policy["shared_geometry"]
    entries = {entry["artifact_id"]: entry for entry in policy["entries"]}
    entry = entries.get(str(event["item_id"]))
    if not isinstance(entry, Mapping) or sha(source / "inputs" / str(event["item_id"]) / "task-contract.json") != entry.get("task_contract_sha256"):
        raise ValueError("V7 cohort policy does not bind this exact task-contract artifact")
    if str(arm.get("bundle_id")) != geometry["bundle_id"] or task_contract.get("contract_id") != geometry["contract_id"] or task_contract.get("context", {}).get("artifact_kind") != geometry["artifact_kind"] or task_contract.get("context", {}).get("declared_scope") != geometry["declared_scope"]:
        raise ValueError("V7 cohort policy geometry does not bind this direct HBQ event")
    return {
        "format_version": 1,
        "artifact_id": str(event["item_id"]),
        "bundle_id": str(arm["bundle_id"]),
        "task_contract_sha256": entry["task_contract_sha256"],
        "contract_id": geometry["contract_id"],
        "artifact_kind": geometry["artifact_kind"],
        "declared_scope": geometry["declared_scope"],
        "compatibility_mode": geometry["compatibility_mode"],
        "decision_id": policy["decision"]["decision_id"],
        "reviewer": policy["decision"]["reviewer"],
        "reason": policy["decision"]["reason"],
    }


def _scope_override_name(event: Mapping[str, Any]) -> str:
    return f"{event['item_id']}--{event['arm_id']}.json"


def _materialize_scope_overrides(work: Path, source: Path, schedule: list[dict[str, Any]], frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in schedule:
        value = _scope_override_value(source, event, frozen)
        if value is None:
            continue
        path = _work_path(work, OVERRIDES, _scope_override_name(event))
        _write_immutable(path, value)
        records.append({"artifact_id": event["item_id"], "arm_id": event["arm_id"], "path": f"{OVERRIDES}/{path.name}", "sha256": sha(path), "schema": value})
    unique = {(record["artifact_id"], record["arm_id"]): record for record in records}
    return [unique[key] for key in sorted(unique)]


def _scope_override_records(source: Path, schedule: list[dict[str, Any]], frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: dict[tuple[str, str], dict[str, Any]] = {}
    for event in schedule:
        value = _scope_override_value(source, event, frozen)
        if value is None:
            continue
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        records[(str(event["item_id"]), str(event["arm_id"]))] = {"artifact_id": event["item_id"], "arm_id": event["arm_id"], "path": f"{OVERRIDES}/{_scope_override_name(event)}", "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(), "schema": value}
    return [records[key] for key in sorted(records)]


def _validate_scope_overrides(work: Path, source: Path, schedule: list[dict[str, Any]], frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = _scope_override_records(source, schedule, frozen)
    for record in records:
        path = _work_path(work, *str(record["path"]).split("/"), allow_missing_leaf=False)
        if read_json(path) != record["schema"] or sha(path) != record["sha256"]:
            raise ValueError("V7 scope compatibility override drifted")
    return records


def _preflight_disclosure(source: Path, schedule: list[dict[str, Any]], frozen: Mapping[str, Any]) -> dict[str, Any]:
    provider = contract()["provider"]
    rendered: dict[tuple[str, str], dict[str, Any]] = {}
    cells = []
    for event in schedule:
        key = (str(event["item_id"]), str(event["arm_id"]))
        template = rendered.get(key)
        if template is None:
            template = _event_disclosure(source, event, frozen)
            rendered[key] = template
        cells.append(
            {
                **template,
                "sequence": event["sequence"],
                "item_id": event["item_id"],
                "arm_id": event["arm_id"],
                "repetition": event["repetition"],
            }
        )
    return {
        "format_version": 2,
        "study_id": contract()["study_id"],
        "destination": "codex",
        "profile": dict(provider),
        "schedule": {"count": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"]},
        "cohort_compatibility_policy": {"path": COHORT_POLICY, "sha256": sha(HERE / COHORT_POLICY)},
        "scope_compatibility_overrides": _scope_override_records(source, schedule, frozen),
        "cells": cells,
    }


def make_disclosure_ack(disclosure_path: Path) -> dict[str, Any]:
    """Return the exact owner acknowledgement for a reviewed disclosure."""
    return {"format_version": 1, "study_id": contract()["study_id"], "disclosure_sha256": sha(disclosure_path), "acknowledged": True}


def _is_nonplaceholder(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.strip().casefold()
    return normalized not in {"ack", "acknowledged", "placeholder", "replace-me", "todo", "tbd", "unknown", "none", "n/a"} and not re.fullmatch(r"[0x-]+", normalized)


def make_retry_disclosure_ack(disclosure_path: Path, *, acknowledgement_id: str, acknowledged_at: str) -> dict[str, Any]:
    """Create the exact acknowledgement shape for one immutable retry disclosure."""

    if not _is_nonplaceholder(acknowledgement_id) or not _is_nonplaceholder(acknowledged_at):
        raise ValueError("Retry acknowledgement requires non-placeholder acknowledgement_id and acknowledged_at")
    _validate_time(acknowledged_at)
    return {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "retry_disclosure_sha256": sha(disclosure_path),
        "acknowledged": True,
        "acknowledgement_id": acknowledgement_id,
        "acknowledged_at": acknowledged_at,
    }






def _validate_disclosure_ack(work: Path, ack_path: Path | None) -> dict[str, Any]:
    if ack_path is None:
        raise ValueError("Exact disclosure acknowledgement is required before remote dispatch")
    ack = read_json(ack_path)
    expected = make_disclosure_ack(work / DISCLOSURE)
    if ack != expected:
        raise ValueError("Disclosure acknowledgement does not match the exact preflight artifact")
    return ack


def _retry_ack_path(work: Path, disclosure_sha256: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", disclosure_sha256):
        raise ValueError("Retry disclosure hash is malformed")
    return _work_path(work, RETRY_ACKS, f"{disclosure_sha256}.json")


def _validate_retry_ack(work: Path, disclosure_sha256: str, ack_path: Path | None) -> dict[str, Any]:
    if ack_path is None:
        raise ValueError("Exact retry disclosure acknowledgement is required before the changed retry payload")
    expected_path = _retry_ack_path(work, disclosure_sha256)
    if _external(ack_path) != expected_path:
        raise ValueError("Retry acknowledgement must be the immutable work-root acknowledgement artifact")
    ack = read_json(expected_path)
    expected = make_retry_disclosure_ack(
        _work_path(work, RETRY_DISCLOSURES, f"{disclosure_sha256}.json", allow_missing_leaf=False),
        acknowledgement_id=ack.get("acknowledgement_id"),
        acknowledged_at=ack.get("acknowledged_at"),
    )
    if ack != expected:
        raise ValueError("Retry acknowledgement does not exactly bind the immutable changed-payload disclosure")
    return ack


def _validate_disclosed_payload(work: Path, source: Path, event: Mapping[str, Any], frozen: Mapping[str, Any]) -> None:
    disclosure = read_json(_work_path(work, DISCLOSURE, allow_missing_leaf=False))
    matches = [
        cell
        for cell in disclosure.get("cells", [])
        if isinstance(cell, Mapping)
        and cell.get("sequence") == event.get("sequence")
        and cell.get("item_id") == event.get("item_id")
        and cell.get("arm_id") == event.get("arm_id")
        and cell.get("repetition") == event.get("repetition")
    ]
    if len(matches) != 1 or matches[0] != _event_disclosure(source, event, frozen):
        raise ValueError("Exact disclosed provider payload drifted before dispatch")


def _validate_base_attempt_context(work: Path, event: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    """The hook must prove its first provider boundary is exactly preflight-acknowledged."""

    disclosure = read_json(_work_path(work, DISCLOSURE, allow_missing_leaf=False))
    cells = [cell for cell in disclosure.get("cells", []) if isinstance(cell, Mapping) and all(cell.get(key) == event.get(key) for key in ("sequence", "item_id", "arm_id", "repetition"))]
    if len(cells) != 1:
        raise ValueError("Base provider-attempt context has no unique preflight disclosure cell")
    provider = context.get("provider")
    batch = context.get("batch")
    attempt = context.get("attempt")
    prompt = context.get("prompt")
    schema = context.get("response_schema")
    if not all(isinstance(value, Mapping) for value in (provider, batch, attempt, prompt, schema)) or attempt.get("number") != 1:
        raise ValueError("Base provider-attempt hook context is malformed")
    payloads = cells[0].get("payload", {}).get("provider_payloads") if isinstance(cells[0].get("payload"), Mapping) else None
    selected = [payload for payload in payloads or [] if isinstance(payload, Mapping) and payload.get("batch") == batch.get("number")]
    if len(selected) != 1:
        raise ValueError("Base provider-attempt batch is not preflight-disclosed")
    request = selected[0].get("request")
    if (
        not isinstance(request, Mapping)
        or provider.get("provider") != contract()["provider"]["provider"]
        or provider.get("model") != contract()["provider"]["model"]
        or provider.get("reasoning") != contract()["provider"]["reasoning"]
        or prompt.get("encoding") != "utf-8"
        or schema.get("encoding") != "utf-8"
        or prompt.get("text") != request.get("prompt_utf8")
        or schema.get("text") != request.get("response_schema_utf8")
        or prompt.get("bytes") != len(str(request.get("prompt_utf8", "")).encode("utf-8"))
        or schema.get("bytes") != len(str(request.get("response_schema_utf8", "")).encode("utf-8"))
        or prompt.get("sha256") != hashlib.sha256(str(request.get("prompt_utf8", "")).encode("utf-8")).hexdigest()
        or schema.get("sha256") != hashlib.sha256(str(request.get("response_schema_utf8", "")).encode("utf-8")).hexdigest()
        or batch.get("question_ids") != selected[0].get("question_ids")
    ):
        raise ValueError("Base provider-attempt context does not exactly match acknowledged payload bytes")


def _retry_disclosure(
    *,
    event: Mapping[str, Any],
    prior_intent: Mapping[str, Any],
    context: Mapping[str, Any],
    preflight_disclosure_sha256: str,
    binding_sha256: str,
) -> dict[str, Any]:
    """Freeze the hook's complete changed request before its provider boundary."""

    required_context = {
        "format_version",
        "run",
        "provider",
        "batch",
        "attempt",
        "prompt",
        "response_schema",
        "validation_feedback_policy",
        "validation_feedback",
        "rejected_chain",
        "output_dir",
    }
    if set(context) != required_context or context.get("format_version") != 1:
        raise ValueError("Retry hook context is malformed")
    provider = context.get("provider")
    attempt = context.get("attempt")
    batch = context.get("batch")
    prompt = context.get("prompt")
    schema = context.get("response_schema")
    rejected = context.get("rejected_chain")
    if (
        not isinstance(provider, Mapping)
        or provider.get("provider") != contract()["provider"]["provider"]
        or provider.get("model") != contract()["provider"]["model"]
        or provider.get("reasoning") != contract()["provider"]["reasoning"]
        or not isinstance(attempt, Mapping)
        or not isinstance(attempt.get("number"), int)
        or attempt["number"] < 2
        or not isinstance(batch, Mapping)
        or not isinstance(batch.get("number"), int)
        or not isinstance(batch.get("question_ids"), list)
        or not isinstance(prompt, Mapping)
        or not isinstance(schema, Mapping)
        or not isinstance(rejected, Mapping)
        or rejected.get("count") != attempt["number"] - 1
        or not re.fullmatch(r"[0-9a-f]{64}", str(rejected.get("head_sha256")))
    ):
        raise ValueError("Retry hook context does not bind the changed request")
    for payload in (prompt, schema):
        text = payload.get("text")
        if (
            payload.get("encoding") != "utf-8"
            or not isinstance(text, str)
            or payload.get("bytes") != len(text.encode("utf-8"))
            or payload.get("sha256") != hashlib.sha256(text.encode("utf-8")).hexdigest()
        ):
            raise ValueError("Retry hook context payload bytes are malformed")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(prompt.get("base_prompt_sha256")))
        or prompt["sha256"] == prompt["base_prompt_sha256"]
    ):
        raise ValueError("Retry hook did not supply materially changed retry prompt bytes")
    if not isinstance(context.get("validation_feedback"), Mapping):
        raise ValueError("Retry hook context lacks the rejection-derived validation feedback")
    if not re.fullmatch(r"[0-9a-f]{64}", str(prior_intent.get("capacity_proof_sha256"))):
        raise ValueError("Retry disclosure lacks its prior intent capacity commitment")
    return {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "event": {
            "sequence": event["sequence"],
            "item_id": event["item_id"],
            "arm_id": event["arm_id"],
            "repetition": event["repetition"],
        },
        "prior_intent": {
            "capacity_proof_sha256": prior_intent["capacity_proof_sha256"],
            "observed_at": prior_intent["observed_at"],
        },
        "preflight_disclosure_sha256": preflight_disclosure_sha256,
        "binding_sha256": binding_sha256,
        "provider_attempt_context": dict(context),
        "provider_attempt_context_sha256": hashlib.sha256(canonical(context)).hexdigest(),
    }


def _validate_terminal_rejected_chain(work: Path, event: Mapping[str, Any], context: Mapping[str, Any]) -> None:
    """Only a persisted model-output rejection authorizes the known-safe pause."""

    batch = context["batch"]
    rejected_chain = context["rejected_chain"]
    output = _output_path(work, event).parent
    if context.get("validation_feedback_policy") == "native_semantic_rejection_v1":
        records = rejected_chain.get("records") if isinstance(rejected_chain, Mapping) else None
        if not isinstance(records, list) or rejected_chain.get("count") != len(records) or not records:
            raise ValueError("Native retry hook rejected-chain evidence is incomplete")
        for record in records:
            if not isinstance(record, Mapping) or not isinstance(record.get("path"), str) or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256"))):
                raise ValueError("Native retry hook rejected-chain record is malformed")
            path = output / "attempts" / record["path"]
            value = read_json(path)
            if sha(path) != record["sha256"] or not isinstance(value.get("reason"), str) or not isinstance(value.get("response"), Mapping):
                raise ValueError("Native retry hook rejected checkpoint drifted")
        feedback = context.get("validation_feedback")
        expected_feedback = {"format_version": 1, "kind": "native_semantic_rejection", "rejected_checkpoint_sha256": records[-1]["sha256"], "reason": records[-1]["reason"]}
        expected_feedback["sha256"] = hashlib.sha256(canonical(expected_feedback)).hexdigest()
        if feedback != expected_feedback or rejected_chain.get("head_sha256") != records[-1]["sha256"]:
            raise ValueError("Native retry hook feedback is not bound to its rejected checkpoint")
        return
    root = output / "responses" / "rejected" / f"batch-{batch['number']:04d}"
    paths = sorted(root.glob("attempt-[0-9][0-9][0-9][0-9].json")) if root.is_dir() else []
    if len(paths) != rejected_chain["count"] or [path.name for path in paths] != [f"attempt-{index:04d}.json" for index in range(1, len(paths) + 1)]:
        raise ValueError("Retry hook rejected-chain evidence is incomplete")
    for path in paths:
        record = read_json(path)
        raw_content = record.get("raw_content")
        raw_text = raw_content.get("text") if isinstance(raw_content, Mapping) else None
        if (
            record.get("stage") != "model_output"
            or not isinstance(raw_text, str)
            or raw_content.get("encoding") != "utf-8"
            or raw_content.get("bytes") != len(raw_text.encode("utf-8"))
            or raw_content.get("sha256") != hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        ):
            raise ValueError("Retry hook requires terminal model-output rejection evidence, not an ambiguous provider failure")
    if not paths or sha(paths[-1]) != rejected_chain["head_sha256"]:
        raise ValueError("Retry hook rejected-chain commitment drifted")


def _retry_disclosure_path(work: Path, disclosure_sha256: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", disclosure_sha256):
        raise ValueError("Retry disclosure hash is malformed")
    return _work_path(work, RETRY_DISCLOSURES, f"{disclosure_sha256}.json")


def _write_retry_disclosure(work: Path, disclosure: Mapping[str, Any]) -> tuple[Path, str]:
    digest = hashlib.sha256((json.dumps(disclosure, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")).hexdigest()
    path = _retry_disclosure_path(work, digest)
    _write_immutable(path, disclosure)
    if sha(path) != digest:
        raise ValueError("Retry disclosure immutability commitment drifted")
    return path, digest


def _source_and_closed(source: Path, closed: Path) -> dict[str, Any]:
    successor = _load_successor_study()
    source_binding = successor.bind_predecessor(source)
    closed_binding = read_json(closed / "predecessor-binding.json")
    if source_binding != closed_binding:
        raise ValueError("Source and closed successor predecessor bindings differ")
    return {"source_binding_sha256": hashlib.sha256(canonical(source_binding)).hexdigest(), "closed_binding_sha256": hashlib.sha256(canonical(closed_binding)).hexdigest(), "source_frozen_contract_sha256": sha(source / "frozen-run-contract.json")}


def _prepared_binding(source: Path, closed: Path, v6: Path, work: Path, admission: Mapping[str, Any], schedule: list[dict[str, Any]], disclosure_sha256: str, frozen: Mapping[str, Any]) -> dict[str, Any]:
    c = contract()
    return {
        "format_version": 1,
        "study_id": c["study_id"],
        "roots": {"source": str(source), "closed": str(closed), "v6": str(v6)},
        "admitted_prefix": dict(admission),
        "schedule": {"count": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"], "sha256": hashlib.sha256(canonical(schedule)).hexdigest()},
        "disclosure_sha256": disclosure_sha256,
        "scope_compatibility_overrides": _scope_override_records(source, schedule, frozen),
        "lineage": {"closed_successor": _pinned_successor_source(), "remainder_study": _pinned_remainder_source(), "source_closed": _source_and_closed(source, closed)},
        "runtime": _runtime_projection(frozen),
        "execution": c["execution"],
        "provider": c["provider"],
    }


def _append(path: Path, value: Mapping[str, Any]) -> None:
    path = _plain_path(path, allow_missing_leaf=True)
    payload = canonical(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written < 1:
                raise OSError("v6 journal write was partial")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _claim(work: Path, source: Path, event: Mapping[str, Any]) -> Path:
    path = _work_path(work, CLAIM)
    value = {"format_version": 1, "study_id": contract()["study_id"], "sequence": event["sequence"], "item_id": event["item_id"], "arm_id": event["arm_id"], "pid": os.getpid(), "claimed_at": datetime.now(UTC).isoformat(), "binding_sha256": sha(work / BINDING), "source_frozen_contract_sha256": sha(source / "frozen-run-contract.json")}
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("Exclusive v6 claim exists; stop without duplicate dispatch") from exc
    try:
        payload = canonical(value) + b"\n"
        if os.write(descriptor, payload) != len(payload):
            raise OSError("v6 claim write was partial")
        os.fsync(descriptor)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)
    return path


def _capacity_projection(receipt: Mapping[str, Any]) -> dict[str, Any]:
    observation = receipt.get("observation")
    if not isinstance(observation, Mapping):
        raise ValueError("Capacity evidence observation is malformed")
    return {
        "kind": receipt["kind"],
        "provider": receipt["provider"],
        "model": receipt["model"],
        "assertion": receipt["assertion"],
        "attestation": receipt["attestation"],
        "observed_at": receipt["observed_at"],
        "observation": {"surface": observation["surface"], "reference": observation["reference"]},
    }


def _proof(work: Path, sequence: int, receipt: Mapping[str, Any]) -> tuple[Path, str]:
    payload = canonical({"sequence": sequence, "capacity": _capacity_projection(receipt)}) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    proofs = _work_path(work, PROOFS)
    path = _work_path(work, PROOFS, f"{digest}.json")
    proofs.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise ValueError("Capacity proof hash collision or mutation")
    if not path.exists():
        temporary = path.with_name(path.name + ".tmp")
        if temporary.exists():
            raise ValueError("Uncertain partial capacity proof exists")
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    return path, digest


def _read_journal(work: Path) -> list[dict[str, Any]]:
    path = _work_path(work, JOURNAL)
    if not path.exists():
        return []
    return _jsonl(path)


def _current_retry_pause(work: Path, event: Mapping[str, Any]) -> dict[str, Any] | None:
    rows = _read_journal(work)
    if rows and rows[-1].get("event") == "retry-disclosure-pause" and rows[-1].get("sequence") == event.get("sequence"):
        return rows[-1]
    return None


def _retry_pause_result(work: Path, schedule: list[dict[str, Any]], accepted: list[dict[str, Any]], remaining: list[dict[str, Any]], pause: Mapping[str, Any]) -> dict[str, Any]:
    disclosure_sha256 = str(pause["retry_disclosure_sha256"])
    return {
        "provider_contacts_recorded": _journaled_provider_contacts(work, schedule),
        "admitted_sequence": 180,
        "completed": len(accepted),
        "remaining": len(remaining),
        "next_sequence": remaining[0]["sequence"],
        "paused": "retry_disclosure_required_before_changed_payload",
        "retry_disclosure_path": str(_retry_disclosure_path(work, disclosure_sha256)),
        "retry_disclosure_sha256": disclosure_sha256,
        "required_next_step": "review the immutable changed-payload retry disclosure, persist its exact non-placeholder acknowledgement, and rerun with a fresh later local-host capacity observation",
        "max_workers": 1,
        "accounting": _accounting(schedule, accepted),
    }


def _assert_plain_work_tree(work: Path) -> None:
    _assert_plain_tree(work, "V7 work root")


def _output_path(work: Path, event: Mapping[str, Any]) -> Path:
    suffix = "run.json" if event["arm_id"] == "hbq_short_story_batch32" else "pass.json"
    return _work_path(
        work,
        "runs",
        str(event["item_id"]),
        str(event["arm_id"]),
        f"run-{event['repetition']:02d}",
        suffix,
    )


def _minimum_contacts(events: list[Mapping[str, Any]]) -> int:
    return sum(6 if event.get("arm_id") == "hbq_short_story_batch32" else 1 for event in events)


def _native_message_evidence(output: Path, *, allow_missing: bool) -> list[tuple[int, Path]]:
    """Return exact native physical-message evidence keyed by logical attempt."""
    if not output.exists():
        if allow_missing:
            return []
        raise ValueError("Settled native output is missing")
    _assert_plain_tree(output, "Native output")
    message_name = re.compile(r"batch-0001\.attempt-0001\.message\.json")
    base = output / "responses"
    roots: list[tuple[int, Path]] = [(1, base)]
    retry_root = output / "retry-attempts"
    if retry_root.exists():
        if not retry_root.is_dir():
            raise ValueError("Native retry evidence root is not a directory")
        names = sorted(path.name for path in retry_root.iterdir())
        if not names or any(not re.fullmatch(r"attempt-000[12]", name) for name in names):
            raise ValueError("Native retry evidence has an unexpected attempt root")
        retry_one = retry_root / "attempt-0001"
        retry_two = retry_root / "attempt-0002"
        if retry_one.exists() and not retry_one.is_dir():
            raise ValueError("Native base retry archive is not a directory")
        if retry_one.is_dir() and (retry_one / "responses").exists():
            raise ValueError("Native base retry archive must not duplicate canonical attempt-one response evidence")
        if retry_two.exists():
            if not retry_two.is_dir() or not retry_one.is_dir():
                raise ValueError("Native retry attempt two lacks its required base archive")
            roots.append((2, retry_two / "responses"))
    evidence: list[tuple[int, Path]] = []
    for ordinal, root in roots:
        if not root.exists():
            continue
        if not root.is_dir():
            raise ValueError("Native response evidence root is not a directory")
        entries = sorted(root.iterdir(), key=lambda path: path.name)
        if len(entries) != 1 or not entries[0].is_file() or not message_name.fullmatch(entries[0].name):
            raise ValueError("Native response evidence does not have one exact message for its logical attempt")
        if not isinstance(read_json(entries[0]), Mapping):
            raise ValueError("Native provider message evidence is not a JSON object")
        evidence.append((ordinal, entries[0]))
    ordinals = [ordinal for ordinal, _path in evidence]
    if ordinals and ordinals != list(range(1, len(ordinals) + 1)):
        raise ValueError("Native logical provider attempts contain a gap or duplicate")
    if len({str(path.absolute()) for _ordinal, path in evidence}) != len(evidence):
        raise ValueError("Native provider message evidence is duplicated across attempt roots")
    if len({sha(path) for _ordinal, path in evidence}) != len(evidence):
        raise ValueError("Native provider message content is duplicated across logical attempts")
    return evidence


def _recorded_provider_contacts(work: Path, event: Mapping[str, Any]) -> int:
    """Count the provider attempts persisted by the production runner for one settled cell."""
    output = _plain_path(_output_path(work, event).parent)
    if event["arm_id"] == "hbq_short_story_batch32":
        responses = sorted((output / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
        if len(responses) != 6:
            raise ValueError("Settled HBQ output does not have its six batch response records")
        attempts = []
        for path in responses:
            value = read_json(path)
            count = value.get("accepted_attempt")
            if not isinstance(count, int) or not 1 <= count <= 3:
                raise ValueError("Settled HBQ batch does not record its accepted provider attempt")
            attempts.append(count)
        return sum(attempts)
    messages = _native_message_evidence(output, allow_missing=False)
    if not 1 <= len(messages) <= 2:
        raise ValueError("Settled native output has an invalid number of Codex attempt messages")
    return len(messages)


def _rejected_attempt_paths(output: Path) -> list[Path]:
    root = output / "responses" / "rejected"
    if not root.is_dir():
        return []
    paths = sorted(root.glob("batch-[0-9][0-9][0-9][0-9]/attempt-[0-9][0-9][0-9][0-9].json"))
    flat = sorted(root.glob("batch-[0-9][0-9][0-9][0-9].attempt-[0-9][0-9][0-9][0-9].json"))
    if flat:
        raise ValueError("V6 rejected attempt evidence must use nested batch/attempt paths")
    return paths


def _unresolved_contact_bounds(work: Path, event: Mapping[str, Any]) -> dict[str, int]:
    output = _output_path(work, event).parent
    rejected_confirmed = 0
    rejected_uncertain = 0
    accepted_batches: set[int] = set()
    if output.exists() and event["arm_id"] == "hbq_short_story_batch32":
        for response in sorted((output / "responses").glob("batch-[0-9][0-9][0-9][0-9].json")):
            match = re.fullmatch(r"batch-([0-9]{4})\.json", response.name)
            if match is None:
                raise ValueError("Unresolved HBQ accepted response path is malformed")
            value = read_json(response)
            count = value.get("accepted_attempt")
            if not isinstance(count, int) or not 1 <= count <= 3:
                raise ValueError("Unresolved HBQ accepted response has invalid provider-contact evidence")
            accepted_batches.add(int(match.group(1)))
    for path in _rejected_attempt_paths(output):
        batch_match = re.fullmatch(r"batch-([0-9]{4})/attempt-[0-9]{4}\.json", path.relative_to(output / "responses" / "rejected").as_posix())
        if batch_match is None:
            raise ValueError("Unresolved rejected attempt path is malformed")
        if int(batch_match.group(1)) in accepted_batches:
            continue
        record = read_json(path)
        if record.get("stage") == "manual_reconcile":
            continue
        raw_content = record.get("raw_content")
        if isinstance(raw_content, Mapping) and isinstance(raw_content.get("text"), str):
            rejected_confirmed += 1
        else:
            rejected_uncertain += 1
    if not output.exists():
        observed = 0
    elif event["arm_id"] == "hbq_short_story_batch32":
        observed = 0
        for path in sorted((output / "responses").glob("batch-[0-9][0-9][0-9][0-9].json")):
            value = read_json(path)
            count = value.get("accepted_attempt")
            if not isinstance(count, int) or not 1 <= count <= 3:
                raise ValueError("Unresolved HBQ output has invalid persisted provider-contact evidence")
            observed += count
    else:
        observed = len(_native_message_evidence(output, allow_missing=True))
        if observed > 2:
            raise ValueError("Unresolved native output exceeds the retry ceiling")
    maximum = _minimum_contacts([event]) * 3
    if observed + rejected_confirmed + rejected_uncertain > maximum:
        raise ValueError("Unresolved output exceeds the retry ceiling")
    return {
        "observed_contact_lower_bound": observed + rejected_confirmed,
        "uncertain_contact_evidence_count": rejected_uncertain,
        "contact_upper_bound": maximum,
    }


def _require_no_orphan_output_cells(work: Path, pending: list[Mapping[str, Any]], *, allow_sequence: int | None = None) -> None:
    for candidate in pending:
        if allow_sequence is not None and candidate["sequence"] == allow_sequence:
            continue
        if _output_path(work, candidate).parent.exists():
            raise ValueError("A future or unjournaled V6 cell already has an output tree; no orphan output adoption or resume is allowed")


def _require_paused_cell_resumable(work: Path, event: Mapping[str, Any]) -> None:
    """A pause may retain runner checkpoints, never an unjournaled completed cell."""

    output = _output_path(work, event).parent
    target = _output_path(work, event)
    if event["arm_id"] != "hbq_short_story_batch32":
        if target.exists():
            raise ValueError("Paused V6 cell has an orphan completed target; no successor resume or adoption is allowed")
        attempts = output / "attempts"
        rejected = sorted(attempts.glob("rejected-*.json")) if attempts.is_dir() else []
        if not rejected or not all(isinstance(read_json(path).get("reason"), str) and isinstance(read_json(path).get("response"), Mapping) for path in rejected):
            raise ValueError("Paused native V7 retry lacks durable rejected-checkpoint evidence")
        return
    for completed_artifact in ("score.json", "diagnostic.json"):
        if (output / completed_artifact).exists():
            raise ValueError("Paused V6 HBQ cell has completed output evidence; no successor resume or adoption is allowed")
    if target.exists():
        manifest = read_json(target)
        if not isinstance(manifest.get("configuration"), Mapping) or not isinstance(manifest.get("config_sha256"), str) or not isinstance(manifest.get("run_id"), str):
            raise ValueError("Paused V6 HBQ cell has an orphan run.json rather than a resumable runner manifest")
    disclosure = read_json(_work_path(work, DISCLOSURE, allow_missing_leaf=False))
    cells = [cell for cell in disclosure.get("cells", []) if isinstance(cell, Mapping) and all(cell.get(key) == event.get(key) for key in ("sequence", "item_id", "arm_id", "repetition"))]
    if len(cells) != 1:
        raise ValueError("Paused V6 HBQ cell has no unique preflight disclosure")
    payloads = cells[0].get("payload", {}).get("provider_payloads") if isinstance(cells[0].get("payload"), Mapping) else None
    if not isinstance(payloads, list) or not payloads:
        raise ValueError("Paused V6 HBQ disclosure has no batch plan")
    complete = True
    for payload in payloads:
        if not isinstance(payload, Mapping) or not isinstance(payload.get("batch"), int) or not isinstance(payload.get("question_ids"), list):
            raise ValueError("Paused V6 HBQ disclosure batch plan is malformed")
        checkpoint = output / "responses" / f"batch-{payload['batch']:04d}.json"
        if not checkpoint.is_file():
            complete = False
            break
        record = read_json(checkpoint)
        expected_ids = payload["question_ids"]
        verdicts = record.get("normalized_verdicts")
        if (
            not isinstance(record.get("accepted_attempt"), int)
            or not 1 <= record["accepted_attempt"] <= 3
            or record.get("question_ids") != expected_ids
            or not isinstance(verdicts, list)
            or [item.get("question_id") if isinstance(item, Mapping) else None for item in verdicts] != expected_ids
        ):
            complete = False
            break
    if complete:
        raise ValueError("Paused V6 HBQ cell already has all accepted batch checkpoints; no orphan completion adoption is allowed")


def _journaled_provider_contacts(work: Path, schedule: list[dict[str, Any]]) -> int:
    by_sequence = {int(event["sequence"]): event for event in schedule}
    total = 0
    for row in _read_journal(work):
        if row.get("event") != "provider-contacts":
            continue
        event = by_sequence.get(row.get("sequence"))
        if event is None or _recorded_provider_contacts(work, event) != row.get("recorded_provider_contacts"):
            raise ValueError("V6 journaled provider contacts do not exactly match persisted attempt evidence")
        total += int(row["recorded_provider_contacts"])
    return total


def _accounting(schedule: list[dict[str, Any]], accepted: list[dict[str, Any]]) -> dict[str, Any]:
    provider_eligible = [event for event in schedule if event.get("sequence") != 181]
    accepted_provider_eligible = [event for event in accepted if event.get("sequence") != 181]
    return {
        "logical_cells": len(schedule),
        "accepted_cells": len(accepted),
        "accepted_count_basis": "validated output files plus the immutable trace-proven sequence-181 zero-contact settlement",
        "minimum_physical_provider_contacts": _minimum_contacts(provider_eligible),
        "retry_ceiling": _minimum_contacts(provider_eligible) * 3,
        "accepted_minimum_physical_provider_contacts": _minimum_contacts(accepted_provider_eligible),
        "accepted_retry_ceiling": _minimum_contacts(accepted_provider_eligible) * 3,
        "recorded_provider_contacts": "persisted per settled cell in execution-journal.jsonl",
    }


def _materialize_unresolved_recovery(work: Path, schedule: list[dict[str, Any]], rows: list[dict[str, Any]]) -> Path | None:
    by_sequence = {int(event["sequence"]): event for event in schedule}
    active: dict[int, dict[str, Any]] = {}
    for row in rows:
        sequence = row.get("sequence")
        if not isinstance(sequence, int) or sequence not in by_sequence:
            continue
        if row.get("event") == "attempt-intent":
            active[sequence] = {
                "kind": "attempt-intent",
                "capacity_proof_sha256": row["capacity_proof_sha256"],
                "observed_at": row["observed_at"],
            }
        elif row.get("event") == "retry-intent":
            disclosure_sha256 = row["retry_disclosure_sha256"]
            ack_path = _retry_ack_path(work, disclosure_sha256)
            if sha(ack_path) != row["retry_ack_sha256"]:
                raise ValueError("Unresolved retry intent acknowledgement commitment drifted")
            _validate_retry_ack(work, disclosure_sha256, ack_path)
            active[sequence] = {
                "kind": "retry-intent",
                "capacity_proof_sha256": row["retry_capacity_proof_sha256"],
                "observed_at": row["observed_at"],
                "retry_authorization": {
                    "prior_capacity_proof_sha256": row["prior_capacity_proof_sha256"],
                    "retry_disclosure_sha256": disclosure_sha256,
                    "retry_ack_sha256": row["retry_ack_sha256"],
                },
            }
        elif row.get("event") == "completed":
            active.pop(sequence, None)
    if not active:
        return None
    entries = []
    for sequence, intent in sorted(active.items()):
        event = by_sequence[sequence]
        proof = _capacity_proof(work, str(intent["capacity_proof_sha256"]))
        if proof.get("sequence") != sequence or proof["capacity"].get("observed_at") != intent["observed_at"]:
            raise ValueError("Unresolved active intent capacity proof drifted")
        entries.append(
            {
                "sequence": event["sequence"],
                "item_id": event["item_id"],
                "arm_id": event["arm_id"],
                "repetition": event["repetition"],
                "active_intent_kind": intent["kind"],
                "active_capacity_proof_sha256": intent["capacity_proof_sha256"],
                "active_capacity_observed_at": intent["observed_at"],
                **({"retry_authorization": intent["retry_authorization"]} if "retry_authorization" in intent else {}),
                "output_root": str(_output_path(work, event).parent),
                **_unresolved_contact_bounds(work, event),
            }
        )
    if not entries:
        return None
    recovery = {
        "format_version": 1,
        "study_id": contract()["study_id"],
        "status": "operator_settlement_required_no_resend",
        "attempts": entries,
        "operator_settlement": {
            "allowed": ["preserve_as_unresolved_nonvoting_evidence", "create_a_distinct_successor_after_offline_adjudication"],
            "forbidden": ["blind_resend", "adopt_or_replace_output_without_a_new_immutable_settlement"],
        },
    }
    path = _work_path(work, UNRESOLVED_RECOVERY)
    _write_immutable(path, recovery)
    return path


def _capacity_proof(work: Path, digest: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Capacity proof commitment is malformed")
    path = _work_path(work, PROOFS, f"{digest}.json", allow_missing_leaf=False)
    if sha(path) != digest:
        raise ValueError("V6 capacity proof commitment drifted")
    value = read_json(path)
    if set(value) != {"sequence", "capacity"} or not isinstance(value.get("capacity"), Mapping):
        raise ValueError("V6 capacity proof payload is malformed")
    _validate_time(value["capacity"].get("observed_at"))
    return value


def _retry_pause_record(work: Path, row: Mapping[str, Any], prior_intent: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    expected_keys = {
        "event",
        "sequence",
        "prior_capacity_proof_sha256",
        "retry_disclosure_sha256",
        "retry_context_sha256",
        "batch_number",
        "attempt_number",
        "rejected_chain_sha256",
    }
    if (
        set(row) != expected_keys
        or row.get("event") != "retry-disclosure-pause"
        or row.get("sequence") != event["sequence"]
        or row.get("prior_capacity_proof_sha256") != prior_intent["capacity_proof_sha256"]
        or not isinstance(row.get("batch_number"), int)
        or not isinstance(row.get("attempt_number"), int)
        or row["attempt_number"] < 2
        or not all(re.fullmatch(r"[0-9a-f]{64}", str(row.get(key))) for key in ("retry_disclosure_sha256", "retry_context_sha256", "rejected_chain_sha256"))
    ):
        raise ValueError("V6 retry-disclosure pause is malformed")
    disclosure_path = _retry_disclosure_path(work, str(row["retry_disclosure_sha256"]))
    disclosure = read_json(disclosure_path)
    if sha(disclosure_path) != row["retry_disclosure_sha256"] or disclosure.get("study_id") != contract()["study_id"]:
        raise ValueError("V6 retry disclosure commitment drifted")
    context = disclosure.get("provider_attempt_context")
    if (
        not isinstance(context, Mapping)
        or hashlib.sha256(canonical(context)).hexdigest() != row["retry_context_sha256"]
        or disclosure.get("provider_attempt_context_sha256") != row["retry_context_sha256"]
        or disclosure.get("event") != {"sequence": event["sequence"], "item_id": event["item_id"], "arm_id": event["arm_id"], "repetition": event["repetition"]}
        or disclosure.get("prior_intent") != {"capacity_proof_sha256": prior_intent["capacity_proof_sha256"], "observed_at": prior_intent["observed_at"]}
        or disclosure.get("preflight_disclosure_sha256") != sha(_work_path(work, DISCLOSURE, allow_missing_leaf=False))
        or disclosure.get("binding_sha256") != sha(_work_path(work, BINDING, allow_missing_leaf=False))
        or context.get("batch", {}).get("number") != row["batch_number"]
        or context.get("attempt", {}).get("number") != row["attempt_number"]
        or hashlib.sha256(canonical(context.get("rejected_chain"))).hexdigest() != row["rejected_chain_sha256"]
    ):
        raise ValueError("V6 retry-disclosure pause does not bind the changed provider payload")
    expected_disclosure = _retry_disclosure(
        event=event,
        prior_intent=prior_intent,
        context=context,
        preflight_disclosure_sha256=sha(_work_path(work, DISCLOSURE, allow_missing_leaf=False)),
        binding_sha256=sha(_work_path(work, BINDING, allow_missing_leaf=False)),
    )
    if disclosure != expected_disclosure:
        raise ValueError("V6 retry disclosure is not an exact immutable hook-context projection")
    return dict(row)


def _accepted(work: Path, schedule: list[dict[str, Any]], admission: Mapping[str, Any]) -> list[dict[str, Any]]:
    _assert_plain_work_tree(work)
    rows = _read_journal(work)
    expected_prefix = {"event": "admitted-prefix", **dict(admission)}
    if not rows or rows[0] != expected_prefix:
        raise ValueError("V6 admission journal is missing or drifted")
    if len(rows) < 2 or rows[1] != {"event": "forensic-precontact", "sequence": 181, "settlement_sha256": sha(HERE / FORENSIC_SETTLEMENT)}:
        raise ValueError("V7 forensic settlement must precede every V7 intent")
    active: dict[int, dict[str, Any]] = {}
    contacts: set[int] = set()
    paused: dict[int, dict[str, Any]] = {}
    expected_index = 0
    for row in rows[1:]:
        kind, sequence = row.get("event"), row.get("sequence")
        if kind == "forensic-precontact":
            if (
                expected_index != 0
                or sequence != 181
                or set(row) != {"event", "sequence", "settlement_sha256"}
                or row.get("settlement_sha256") != sha(HERE / FORENSIC_SETTLEMENT)
                or read_json(HERE / FORENSIC_SETTLEMENT).get("settled_sequence", {}).get("provider_contacts") != 0
            ):
                raise ValueError("V7 forensic pre-contact settlement is malformed")
            expected_index += 1
        elif kind == "attempt-intent":
            if (
                active
                or expected_index >= len(schedule)
                or sequence != schedule[expected_index]["sequence"]
                or set(row) != {"event", "sequence", "capacity_proof_sha256", "observed_at"}
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("capacity_proof_sha256")))
            ):
                raise ValueError("V6 attempt-intent journal is not an ordered prefix")
            proof = _capacity_proof(work, str(row["capacity_proof_sha256"]))
            if proof.get("sequence") != sequence or row.get("observed_at") != proof["capacity"].get("observed_at"):
                raise ValueError("V6 attempt intent does not match its capacity proof")
            active[sequence] = dict(row)
        elif kind == "retry-disclosure-pause":
            if (
                expected_index >= len(schedule)
                or sequence != schedule[expected_index]["sequence"]
                or sequence not in active
                or sequence in paused
                or sequence in contacts
            ):
                raise ValueError("V6 retry-disclosure pause is not the next unsettled cell")
            paused[sequence] = _retry_pause_record(work, row, active[sequence], schedule[expected_index])
        elif kind == "retry-intent":
            pause = paused.get(sequence)
            expected_keys = {"event", "sequence", "prior_capacity_proof_sha256", "retry_capacity_proof_sha256", "retry_disclosure_sha256", "retry_ack_sha256", "observed_at"}
            if (
                pause is None
                or set(row) != expected_keys
                or row.get("prior_capacity_proof_sha256") != active.get(sequence, {}).get("capacity_proof_sha256")
                or row.get("retry_disclosure_sha256") != pause["retry_disclosure_sha256"]
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("retry_capacity_proof_sha256")))
                or row["retry_capacity_proof_sha256"] == row["prior_capacity_proof_sha256"]
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("retry_ack_sha256")))
            ):
                raise ValueError("V6 retry intent is not bound to its paused changed payload")
            retry_proof = _capacity_proof(work, str(row["retry_capacity_proof_sha256"]))
            prior_proof = _capacity_proof(work, str(row["prior_capacity_proof_sha256"]))
            if row.get("observed_at") != retry_proof["capacity"]["observed_at"] or _validate_time(retry_proof["capacity"]["observed_at"]) <= _validate_time(prior_proof["capacity"]["observed_at"]):
                raise ValueError("V6 retry intent lacks fresh capacity evidence")
            ack_path = _retry_ack_path(work, str(row["retry_disclosure_sha256"]))
            if sha(ack_path) != row["retry_ack_sha256"]:
                raise ValueError("V6 retry acknowledgement commitment drifted")
            _validate_retry_ack(work, str(row["retry_disclosure_sha256"]), ack_path)
            active[sequence] = {"capacity_proof_sha256": row["retry_capacity_proof_sha256"], "observed_at": row["observed_at"]}
            paused.pop(sequence)
        elif kind == "provider-contacts":
            if (
                expected_index >= len(schedule)
                or sequence != schedule[expected_index]["sequence"]
                or sequence not in active
                or paused
                or sequence in contacts
                or set(row) != {"event", "sequence", "capacity_proof_sha256", "recorded_provider_contacts"}
                or row.get("capacity_proof_sha256") != active[sequence]["capacity_proof_sha256"]
                or not isinstance(row.get("recorded_provider_contacts"), int)
                or row["recorded_provider_contacts"] < 1
            ):
                raise ValueError("V6 provider-contact journal is not an ordered settled attempt")
            target = _output_path(work, schedule[expected_index])
            if not target.is_file() or _recorded_provider_contacts(work, schedule[expected_index]) != row["recorded_provider_contacts"]:
                raise ValueError("V6 provider-contact evidence does not match the persisted runner artifacts")
            contacts.add(sequence)
        elif kind == "completed":
            if (
                expected_index >= len(schedule)
                or sequence != schedule[expected_index]["sequence"]
                or sequence not in active
                or sequence not in contacts
                or set(row) != {"event", "sequence", "capacity_proof_sha256", "output_sha256"}
                or row.get("capacity_proof_sha256") != active[sequence]["capacity_proof_sha256"]
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("output_sha256")))
            ):
                raise ValueError("V6 completion journal is not an ascending contiguous prefix")
            target = _output_path(work, schedule[expected_index])
            if not target.is_file() or sha(target) != row["output_sha256"]:
                raise ValueError("V6 completed output commitment drifted")
            active.pop(sequence)
            contacts.remove(sequence)
            expected_index += 1
        else:
            raise ValueError("V6 journal contains an unknown event")
    if active and paused and len(active) == len(paused) == 1 and not contacts:
        return schedule[:expected_index]
    if active or contacts:
        recovery = _materialize_unresolved_recovery(work, schedule, rows)
        suffix = f"; operator settlement is required at {recovery}" if recovery is not None else ""
        raise ValueError(f"V6 has an unresolved attempt intent; stop without resend{suffix}")
    return schedule[:expected_index]


def _validate_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Capacity evidence observed_at is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Capacity evidence observed_at is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("Capacity evidence observed_at requires a timezone")
    return parsed.astimezone(UTC)


def validate_capacity_evidence(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    receipt = read_json(path)
    checked = _validate_time(receipt.get("observed_at"))
    current = (now or datetime.now(UTC)).astimezone(UTC)
    c = contract()
    if receipt.get("kind") != c["capacity_gate"]["probe_kind"] or receipt.get("provider") != c["provider"]["provider"] or receipt.get("model") != c["provider"]["model"] or receipt.get("assertion") != "capacity_available" or receipt.get("attestation") != c["capacity_gate"]["attestation"]:
        raise ValueError("Capacity evidence does not identify the required current Codex observation")
    if checked > current + timedelta(minutes=1) or current - checked > MAX_PREFLIGHT_AGE:
        raise ValueError("Capacity evidence is not current")
    observation = receipt.get("observation")
    if not isinstance(observation, Mapping) or observation.get("surface") != "native_codex_quota_surface" or not isinstance(observation.get("reference"), str) or not observation["reference"].strip():
        raise ValueError("Capacity evidence requires a nonempty native observation reference")
    return receipt


def prepare(source_root: Path, closed_root: Path, v6_root: Path, work_root: Path) -> dict[str, Any]:
    source, closed, v6, work = _roots(source_root, closed_root, v6_root, work_root)
    if work.exists() and any(work.iterdir()):
        raise ValueError("Fresh V7 root must be empty; use dry-run validation to reload it")
    admission = admit_v6_prefix(v6)
    schedule = _fresh_schedule(closed)
    _source_and_closed(source, closed)
    frozen = read_json(source / "frozen-run-contract.json")
    work.mkdir(parents=True, exist_ok=True)
    _materialize_scope_overrides(work, source, schedule, frozen)
    disclosure = _preflight_disclosure(source, schedule, frozen)
    _write_immutable(work / DISCLOSURE, disclosure)
    binding = _prepared_binding(source, closed, v6, work, admission, schedule, sha(work / DISCLOSURE), frozen)
    _write_immutable(work / BINDING, binding)
    _write_immutable(work / ADMISSION, admission)
    for row in schedule:
        _append(work / SCHEDULE, row)
    _append(work / JOURNAL, {"event": "admitted-prefix", **admission})
    _append(work / JOURNAL, {"event": "forensic-precontact", "sequence": 181, "settlement_sha256": sha(HERE / FORENSIC_SETTLEMENT)})
    return {"provider_calls": 0, "admitted_sequence": 180, "settled_precontact_sequence": 181, "cells": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"], "work_root": str(work), "disclosure_path": str(work / DISCLOSURE), "disclosure_sha256": sha(work / DISCLOSURE), "destination": "codex", "profile": contract()["provider"], "accounting": _accounting(schedule, [])}


def _verify_prepared(source_root: Path, closed_root: Path, v6_root: Path, work_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    source, closed, v6, work = _roots(source_root, closed_root, v6_root, work_root)
    if not work.is_dir():
        raise ValueError("Prepared V7 root is missing")
    _assert_plain_work_tree(work)
    admission = admit_v6_prefix(v6)
    schedule = _fresh_schedule(closed)
    frozen = read_json(source / "frozen-run-contract.json")
    _validate_scope_overrides(work, source, schedule, frozen)
    expected_disclosure = _preflight_disclosure(source, schedule, frozen)
    if read_json(work / DISCLOSURE) != expected_disclosure:
        raise ValueError("V7 preflight disclosure drifted")
    expected = _prepared_binding(source, closed, v6, work, admission, schedule, sha(work / DISCLOSURE), frozen)
    if read_json(work / BINDING) != expected or read_json(work / ADMISSION) != admission or _jsonl(work / SCHEDULE) != schedule:
        raise ValueError("V7 prepared provenance drifted")
    if _read_journal(work)[:2] != [{"event": "admitted-prefix", **admission}, {"event": "forensic-precontact", "sequence": 181, "settlement_sha256": sha(HERE / FORENSIC_SETTLEMENT)}]:
        raise ValueError("V7 admission journal drifted")
    allowed = {BINDING, ADMISSION, DISCLOSURE, DISCLOSURE_ACK, RETRY_DISCLOSURES, RETRY_ACKS, UNRESOLVED_RECOVERY, SCHEDULE, JOURNAL, CLAIM, PROOFS, OVERRIDES, "runs"}
    unexpected = {path.name for path in work.iterdir()} - allowed
    if unexpected:
        raise ValueError(f"V7 work root contains unexpected entries: {sorted(unexpected)}")
    return expected, schedule, admission


def _dispatch_event(
    runner: Any,
    event: Mapping[str, Any],
    frozen: Mapping[str, Any],
    source: Path,
    work: Path,
    timeout: float,
    before_provider_attempt: Callable[[Mapping[str, Any]], None] | None = None,
) -> Path:
    _output_path(work, event)
    disclosure = read_json(_work_path(work, DISCLOSURE, allow_missing_leaf=False))
    cells = disclosure.get("cells")
    if not isinstance(cells, list) or disclosure.get("profile") != contract()["provider"]:
        raise ValueError("V7 dispatch disclosure is malformed")
    matches = [cell for cell in cells if isinstance(cell, Mapping) and all(cell.get(key) == event.get(key) for key in ("sequence", "item_id", "arm_id", "repetition"))]
    if len(matches) != 1:
        raise ValueError("V7 dispatch event is not uniquely bound to its full disclosure cell")
    override_path: Path | None = None
    if _scope_override_value(source, event, frozen) is not None:
        override_path = _work_path(work, OVERRIDES, _scope_override_name(event), allow_missing_leaf=False)
        if read_json(override_path) != _scope_override_value(source, event, frozen):
            raise ValueError("V7 scope compatibility override changed before dispatch")

    def provider_boundary_check(context: Mapping[str, Any], commitments: Mapping[str, Any]) -> None:
        provider_identity = {key: contract()["provider"][key] for key in ("provider", "model", "reasoning")}
        if (
            commitments.get("provider") != provider_identity
            or commitments.get("disclosure_profile") != contract()["provider"]
            or commitments.get("disclosed_cell_sha256") != hashlib.sha256(canonical(matches[0])).hexdigest()
            or commitments.get("disclosure_profile_sha256") != hashlib.sha256(canonical(disclosure["profile"])).hexdigest()
            or commitments.get("helper") != runner.runtime_identity()
        ):
            raise ValueError("Provider-boundary commitments no longer match the acknowledged V7 disclosure")
        if override_path is None:
            if commitments.get("dependencies") is not None:
                raise ValueError("Native provider boundary unexpectedly carries HBQ dependencies")
            return
        dependencies = commitments.get("dependencies")
        task_contract = source / "inputs" / str(event["item_id"]) / "task-contract.json"
        expected_override = next((record for record in disclosure.get("scope_compatibility_overrides", []) if record.get("artifact_id") == event["item_id"] and record.get("arm_id") == event["arm_id"]), None)
        expected_task = next((record for record in matches[0].get("outbound_artifacts", []) if record.get("role") == "task_contract"), None)
        if (
            not isinstance(dependencies, Mapping) or not isinstance(expected_override, Mapping) or not isinstance(expected_task, Mapping)
            or dependencies.get("scope_compatibility_override") != {"path": str(override_path.absolute()), "bytes": override_path.stat().st_size, "sha256": sha(override_path)}
            or dependencies.get("task_contract") != {"path": str(task_contract.absolute()), "bytes": task_contract.stat().st_size, "sha256": sha(task_contract)}
            or expected_override.get("sha256") != sha(override_path)
            or expected_task.get("sha256") != sha(task_contract)
        ):
            raise ValueError("Provider-boundary override or task-contract bytes drifted from the acknowledged V7 disclosure")

    return runner.dispatch_event(
        event=event,
        frozen=frozen,
        predecessor_root=source,
        work=work,
        timeout=timeout,
        disclosed_cell=matches[0],
        disclosure_profile=disclosure["profile"],
        scope_compatibility_override_path=override_path,
        predecessor_runner=_load_predecessor_runner(),
        before_provider_attempt=before_provider_attempt,
        provider_boundary_check=provider_boundary_check,
    )


def _settle_one(
    runner: Any,
    frozen: Mapping[str, Any],
    source: Path,
    work: Path,
    schedule: list[dict[str, Any]],
    admission: Mapping[str, Any],
    accepted: list[dict[str, Any]],
    event: dict[str, Any],
    evidence: Path,
    disclosure_ack: Path,
    timeout: float,
    expected_runtime: Mapping[str, Any] | None = None,
    retry_disclosure_ack: Path | None = None,
) -> list[dict[str, Any]]:
    # All failure points before the intent are local/pre-dispatch and leave no
    # claim behind. Once the intent is durable, the provider outcome is treated
    # as ambiguous until the output and completion row are both settled.
    receipt = validate_capacity_evidence(evidence)
    _validate_disclosure_ack(work, disclosure_ack)
    predecessor_runner = _load_predecessor_runner()
    predecessor_runner._revalidate_predecessor_event(source, frozen, event)
    if expected_runtime is not None and _runtime_projection(frozen) != expected_runtime:
        raise ValueError("Executed runtime projection drifted before dispatch")
    rows = _read_journal(work)
    prior_pause = rows[-1] if rows and rows[-1].get("event") == "retry-disclosure-pause" and rows[-1].get("sequence") == event["sequence"] else None
    prior_intent = next(
        (
            {"capacity_proof_sha256": row["retry_capacity_proof_sha256"], "observed_at": row["observed_at"]}
            if row.get("event") == "retry-intent"
            else row
            for row in reversed(rows)
            if row.get("sequence") == event["sequence"] and row.get("event") in {"attempt-intent", "retry-intent"}
        ),
        None,
    )
    if prior_pause is None:
        _require_no_orphan_output_cells(work, schedule[len(accepted):])
    else:
        _require_no_orphan_output_cells(work, schedule[len(accepted):], allow_sequence=int(event["sequence"]))
        _require_paused_cell_resumable(work, event)
    claim = _claim(work, source, event)
    dispatch_authorized = False
    initial_intent_durable = False
    known_safe_pause = False
    settled = False
    try:
        predecessor_runner._revalidate_predecessor_event(source, frozen, event)
        if expected_runtime is not None and _runtime_projection(frozen) != expected_runtime:
            raise ValueError("Executed runtime projection drifted before intent")
        receipt = validate_capacity_evidence(evidence)
        _validate_disclosure_ack(work, disclosure_ack)
        _validate_disclosed_payload(work, source, event, frozen)
        if prior_pause is None:
            _, proof_digest = _proof(work, int(event["sequence"]), receipt)
            initial_intent = {"event": "attempt-intent", "sequence": event["sequence"], "capacity_proof_sha256": proof_digest, "observed_at": receipt["observed_at"]}
            _append(work / JOURNAL, initial_intent)
            initial_intent_durable = True
            current_intent = initial_intent
        else:
            current_intent = prior_intent
            proof_digest = str(current_intent["capacity_proof_sha256"])

        current_pause = prior_pause

        def before_provider_attempt(context: Mapping[str, Any]) -> None:
            nonlocal dispatch_authorized, known_safe_pause, proof_digest, current_intent, current_pause
            attempt = context.get("attempt")
            if not isinstance(attempt, Mapping) or not isinstance(attempt.get("number"), int):
                raise ValueError("Runner omitted the provider attempt number")
            if attempt["number"] == 1:
                if current_pause is not None:
                    raise ValueError("Paused V6 retry unexpectedly changed back to attempt one")
                _validate_base_attempt_context(work, event, context)
                dispatch_authorized = True
                return
            _validate_terminal_rejected_chain(work, event, context)
            disclosure = _retry_disclosure(
                event=event,
                prior_intent=current_intent,
                context=context,
                preflight_disclosure_sha256=sha(_work_path(work, DISCLOSURE, allow_missing_leaf=False)),
                binding_sha256=sha(_work_path(work, BINDING, allow_missing_leaf=False)),
            )
            disclosure_path, disclosure_digest = _write_retry_disclosure(work, disclosure)
            if current_pause is None:
                pause = {
                    "event": "retry-disclosure-pause",
                    "sequence": event["sequence"],
                    "prior_capacity_proof_sha256": current_intent["capacity_proof_sha256"],
                    "retry_disclosure_sha256": disclosure_digest,
                    "retry_context_sha256": disclosure["provider_attempt_context_sha256"],
                    "batch_number": context["batch"]["number"],
                    "attempt_number": context["attempt"]["number"],
                    "rejected_chain_sha256": hashlib.sha256(canonical(context["rejected_chain"])).hexdigest(),
                }
                _append(work / JOURNAL, pause)
                known_safe_pause = True
                raise _load_hbq_runner().RetryDisclosurePause("Retry disclosure acknowledgement and fresh capacity evidence are required before another provider attempt")
            if disclosure_digest != current_pause.get("retry_disclosure_sha256"):
                raise ValueError("Retry payload changed after the immutable retry disclosure pause")
            ack = _validate_retry_ack(work, disclosure_digest, retry_disclosure_ack)
            retry_receipt = validate_capacity_evidence(evidence)
            _, retry_proof_digest = _proof(work, int(event["sequence"]), retry_receipt)
            previous_proof = _capacity_proof(work, str(current_intent["capacity_proof_sha256"]))
            if (
                retry_proof_digest == current_intent["capacity_proof_sha256"]
                or _validate_time(retry_receipt["observed_at"]) <= _validate_time(previous_proof["capacity"]["observed_at"])
            ):
                raise ValueError("Retry requires a fresh capacity observation after the prior attempt")
            retry_intent = {
                "event": "retry-intent",
                "sequence": event["sequence"],
                "prior_capacity_proof_sha256": current_intent["capacity_proof_sha256"],
                "retry_capacity_proof_sha256": retry_proof_digest,
                "retry_disclosure_sha256": disclosure_digest,
                "retry_ack_sha256": sha(_retry_ack_path(work, disclosure_digest)),
                "observed_at": retry_receipt["observed_at"],
            }
            _append(work / JOURNAL, retry_intent)
            proof_digest = retry_proof_digest
            current_intent = {"capacity_proof_sha256": retry_proof_digest, "observed_at": retry_receipt["observed_at"]}
            current_pause = None
            dispatch_authorized = True

        try:
            output = _dispatch_event(runner, event, frozen, source, work, timeout, before_provider_attempt)
        except runner.NativeRetryDisclosurePause as exc:
            before_provider_attempt(exc.context)
            raise AssertionError("V7 native retry pause must be converted by the pre-contact hook")
        predecessor_runner._validate_global_sessions(source, work, [*accepted, event])
        target = _output_path(work, event)
        if _plain_path(output) != target or not target.is_file():
            raise ValueError("Worker output path did not match the planned isolated cell")
        _append(
            work / JOURNAL,
            {
                "event": "provider-contacts",
                "sequence": event["sequence"],
                "capacity_proof_sha256": proof_digest,
                "recorded_provider_contacts": _recorded_provider_contacts(work, event),
            },
        )
        _append(work / JOURNAL, {"event": "completed", "sequence": event["sequence"], "capacity_proof_sha256": proof_digest, "output_sha256": sha(target)})
        settled_accepted = _accepted(work, schedule, admission)
        if not settled_accepted or settled_accepted[-1]["sequence"] != event["sequence"]:
            raise ValueError("Completed cell did not settle the next contiguous prefix")
        settled = True
        return settled_accepted
    finally:
        # A hook-created retry pause is known to precede attempt-start/contact;
        # all other durable intents remain fail-closed and operator-visible.
        if settled or known_safe_pause or (prior_pause is not None and not dispatch_authorized) or (not initial_intent_durable and not dispatch_authorized):
            claim.unlink(missing_ok=True)


def execute(source_root: Path, closed_root: Path, v6_root: Path, work_root: Path, capacity_evidence: Path | None = None, *, timeout: float = 3600.0, allow_remote: bool = False, dry_run: bool = False, disclosure_ack: Path | None = None, retry_disclosure_ack: Path | None = None) -> dict[str, Any]:
    work = _external(work_root, allow_missing_leaf=True)
    if not work.exists():
        prepare(source_root, closed_root, v6_root, work)
    if dry_run and not any(work.iterdir()):
        prepare(source_root, closed_root, v6_root, work)
    binding, schedule, admission = _verify_prepared(source_root, closed_root, v6_root, work)
    accepted = _accepted(work, schedule, admission)
    remaining = schedule[len(accepted):]
    if dry_run:
        accounting = _accounting(schedule, accepted)
        return {"provider_calls": 0, "admitted_sequence": 180, "settled_precontact_sequence": 181, "completed": len(accepted), "cells": len(remaining), "first_sequence": remaining[0]["sequence"] if remaining else None, "last_sequence": remaining[-1]["sequence"] if remaining else None, "prepared": True, "disclosure_path": str(work / DISCLOSURE), "disclosure_sha256": sha(work / DISCLOSURE), "destination": "codex", "profile": contract()["provider"], "accounting": accounting}
    if not allow_remote:
        raise ValueError("This successor sends disclosed predecessor prose and prompts to Codex; pass --allow-remote after review")
    if capacity_evidence is None:
        raise ValueError("A fresh capacity evidence path is required before dispatch")
    evidence = _external(capacity_evidence)
    if disclosure_ack is None:
        raise ValueError("An exact disclosure acknowledgement is required before --allow-remote")
    ack = _external(disclosure_ack)
    if ack != _work_path(work, DISCLOSURE_ACK, allow_missing_leaf=False):
        raise ValueError("Disclosure acknowledgement must be the immutable work-root acknowledgement artifact")
    retry_ack = _external(retry_disclosure_ack) if retry_disclosure_ack is not None else None
    pause = _current_retry_pause(work, remaining[0]) if remaining else None
    if pause is not None:
        retry_disclosure_sha256 = str(pause["retry_disclosure_sha256"])
        try:
            _validate_retry_ack(work, retry_disclosure_sha256, retry_ack)
            validate_capacity_evidence(evidence)
        except ValueError:
            return _retry_pause_result(work, schedule, accepted, remaining, pause)
    # The receipt and acknowledgement are checked before the clean-runtime
    # gate, so stale/pre-dispatch failures create neither claim nor intent.
    validate_capacity_evidence(evidence)
    _validate_disclosure_ack(work, ack)
    _require_clean_pushed()
    runner = _load_successor_runner()
    source = _plain_path(Path(source_root))
    frozen = read_json(source / "frozen-run-contract.json")
    if _runtime_projection(frozen) != binding["runtime"]:
        raise ValueError("Executed runtime projection drifted after preparation")
    while remaining:
        try:
            accepted = _settle_one(runner, frozen, source, work, schedule, admission, accepted, remaining[0], evidence, ack, timeout, binding["runtime"], retry_ack)
        except _load_hbq_runner().RetryDisclosurePause:
            pause = _read_journal(work)[-1]
            if pause.get("event") != "retry-disclosure-pause" or pause.get("sequence") != remaining[0]["sequence"]:
                raise ValueError("Runner reported a retry pause without the required durable V6 pause evidence")
            return _retry_pause_result(work, schedule, accepted, remaining, pause)
        except ValueError as exc:
            if accepted and _current_retry_pause(work, remaining[0]) is None and "Capacity evidence is not current" in str(exc):
                return {
                    "provider_contacts_recorded": _journaled_provider_contacts(work, schedule),
                    "admitted_sequence": 180,
                    "completed": len(accepted),
                    "remaining": len(remaining),
                    "next_sequence": remaining[0]["sequence"],
                    "paused": "capacity_receipt_expired_after_clean_checkpoint",
                    "required_next_step": "rerun with a fresh local-host capacity observation; the next sequence remains unclaimed and must not be resent",
                    "max_workers": 1,
                    "accounting": _accounting(schedule, accepted),
                }
            raise
        remaining = schedule[len(accepted):]
    accounting = _accounting(schedule, accepted)
    return {
        "provider_contacts_recorded": _journaled_provider_contacts(work, schedule),
        "admitted_sequence": 180,
        "completed": len(accepted),
        "remaining": 0,
        "max_workers": 1,
        "accounting": accounting,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--closed-root", type=Path, default=CLOSED_DEFAULT)
    parser.add_argument("--v6-root", type=Path, default=V6_DEFAULT)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--capacity-evidence", type=Path)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--disclosure-ack", type=Path, help="Exact owner acknowledgement for preflight-disclosure.json")
    parser.add_argument("--retry-disclosure-ack", type=Path, help="Exact owner acknowledgement for a paused changed-payload retry disclosure")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preview-disclosure", action="store_true", help="Prepare/reload and print the exact private outbound-payload disclosure")
    args = parser.parse_args()
    result = execute(args.source_root, args.closed_root, args.v6_root, args.work_root, args.capacity_evidence, timeout=args.timeout, allow_remote=args.allow_remote, dry_run=args.dry_run or args.preview_disclosure, disclosure_ack=args.disclosure_ack, retry_disclosure_ack=args.retry_disclosure_ack)
    if args.preview_disclosure:
        result["disclosure_preview"] = read_json(_plain_path(Path(args.work_root)) / DISCLOSURE)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
