#!/usr/bin/env python3
"""Admit the recovered 178 cell and execute the untouched 179-330 suffix.

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
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
REMAINDER_STUDY = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-successor-v1" / "study.py"
SUCCESSOR_STUDY = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "study.py"
SUCCESSOR_RUNNER = REPO / "evaluation-results" / "hbq-multisample-repeatability-v1-successor-v1" / "run_successor.py"
SOURCE_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
CLOSED_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff")
V4_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v4-live-1c587bc-20260822")
V5_DEFAULT = Path(r"C:\Users\Haile\Documents\cwr-multisample-v5-owner-validated-settlement-20260822\offline-recovered-completion.json")

BINDING = "v6-binding.json"
ADMISSION = "admitted-sequence-178.json"
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

EXPECTED_V4_FILES = 33
EXPECTED_V4_TREE = "b084bc32f1df05b279a3816f188d98e1e7f95da0e4453a46d5e2b7fa81af6009"
EXPECTED_V4_JOURNAL = "e1c3b88b94193906591a6566668688eb67b2592d19f8f7fe832dbc9941e0096a"
EXPECTED_V4_CLAIM = "b649cb066a46e4be45a358f4b6f082c4ba588e6c05d99f2fe46a0720ac58a445"
EXPECTED_V4_RUN = "42b223e0ef9ae6d258c68b35ae1a08f1ecce1d073b64b7f19b77b95e3b584f70"
EXPECTED_V4_VERDICTS = "28d3cbbb616be02f4d2cab063f9ef56ca9be8d4689025cb1ef998274aeac091a"
EXPECTED_V4_SESSIONS = "ebde6b1ccd743548bb2ce7c03b04971aabbc13c451c29e153f2132f369a704f5"
EXPECTED_V5_RECORD = "b784bd4baa1cf209ae941de989fe19697de51d22fb8602499b747e13399216ff"


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
    expected = {
        "format_version": 1,
        "study_id": "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v6",
        "supersedes": {
            "failed_live_root": "cwr-multisample-capacity-reset-v4-live-1c587bc-20260822",
            "offline_admission_root": "cwr-multisample-v5-owner-validated-settlement-20260822",
            "v4_package_commit": "1c587bc311e0f303e809d842ec1035e5e81eb60b",
            "v5_package_commit": "9a911138c84928dc457c7279eae7fca174091c1e",
            "reason": "admit the independently validated sequence-178 output and continue only the untouched 179-330 suffix",
        },
        "admitted_prefix": {
            "sequence": 178,
            "v4_tree_sha256": EXPECTED_V4_TREE,
            "v4_journal_sha256": EXPECTED_V4_JOURNAL,
            "v4_claim_sha256": EXPECTED_V4_CLAIM,
            "v4_run_sha256": EXPECTED_V4_RUN,
            "v4_verdicts_sha256": EXPECTED_V4_VERDICTS,
            "v4_session_sha256": EXPECTED_V4_SESSIONS,
            "v5_record_sha256": EXPECTED_V5_RECORD,
            "v5_completion_sha256": EXPECTED_V4_RUN,
        },
        "schedule": {
            "count": 152,
            "first_sequence": 179,
            "last_sequence": 330,
            "source_full_schedule_sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086",
            "sha256": "6f22cdcd4501e1de4c90ec9c756c2006a7dcef9e9ee8c446ce8b985f2bb3ec4b",
        },
        "evaluation_population": {
            "generated_stories": 10,
            "human_story": 1,
            "primary": {"stories": 10, "cells": 300},
            "secondary": {"stories": 1, "cells": 30},
            "total_cells": 330,
        },
        "accounting": {
            "suffix_logical_cells": 152,
            "suffix_minimum_physical_provider_contacts": 277,
            "suffix_retry_ceiling": 831,
            "accepted_count_basis": "validated output files in the contiguous journal prefix",
        },
        "lineage": {
            "closed_successor_commit": "9422efffdca1e5e7f82d4bf77588a726af75b4cd",
            "closed_successor_study_git_blob_oid_sha1": "d2cafd72b6c5e96582064e8aa877b42a9e04ebd2",
            "closed_successor_runner_git_blob_oid_sha1": "98a276a64b17dd1d20cd3fe3cc4aa5176040144d",
            "closed_successor_runner_retry_hook_git_blob_oid_sha1": "dbcacd3f0b02a8d1db7683dfade213fdd0f17243",
            "remainder_study_commit": REMAINDER_COMMIT,
            "remainder_study_git_blob_oid_sha1": REMAINDER_STUDY_GIT_BLOB_OID_SHA1,
            "capacity_reset_v3_commit": "90f5769b8119d9011ed6435742ad23c208eb69e4",
            "capacity_reset_v4_commit": "1c587bc311e0f303e809d842ec1035e5e81eb60b",
            "settler_v5_commit": "9a911138c84928dc457c7279eae7fca174091c1e",
        },
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "paid_api": False, "human_judgment": False},
        "capacity_gate": {"probe_kind": "external_current_capacity_evidence_v2", "max_age_seconds": 600, "launch_time_revalidation_required": True, "probe_authorizes_provider_contact": False, "attestation": "local_host_observation_only", "does_not_attest": ["provider_acceptance", "future_capacity"]},
        "execution": {"max_workers": 1, "worker_unit": "one logical sequence per isolated output root and epoch", "journal_commit_order": "ascending sequence only", "unresolved_attempt_policy": "stop without resend; preserve bounded unresolved-contact accounting and require explicit offline operator settlement", "changed_retry_policy": "terminal rejected evidence pauses before any changed retry payload; exact immutable retry disclosure, non-placeholder acknowledgement, and fresh later capacity evidence are required before retry intent", "paused_claim_recovery_policy": "never automatically remove an existing claim; any crash-left or concurrent claim requires explicit offline operator settlement before a distinct successor may proceed", "outcome_selection": False, "prepare_provider_calls": 0},
    }
    if value != expected:
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


def _roots(source: Path, closed: Path, v4: Path, v5: Path, work: Path) -> tuple[Path, Path, Path, Path, Path]:
    source_r, closed_r, v4_r = (_external(source), _external(closed), _external(v4))
    v5_r = _external(v5)
    work_r = _external(work, allow_missing_leaf=True)
    if not source_r.is_dir() or not closed_r.is_dir() or not v4_r.is_dir() or not v5_r.is_file():
        raise ValueError("Source, closed, v4, and v5 roots have the wrong type")
    roots = (source_r, closed_r, v4_r, v5_r, work_r)
    for left_index, left in enumerate(roots):
        for right in roots[left_index + 1:]:
            # A missing work root is still its literal intended leaf after its
            # existing ancestry has been reparse-checked; sibling roots share
            # a parent safely, while containment remains unsafe.
            if left == right or left in right.parents or right in left.parents:
                raise ValueError("Source, closed, evidence, and fresh work roots must be disjoint")
    if work_r.exists() and not work_r.is_dir():
        raise ValueError("Fresh v6 work root must be a directory")
    for root, label in ((source_r, "Source root"), (closed_r, "Closed root"), (v4_r, "V4 evidence root")):
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


def admit_sequence_178(v4_root: Path = V4_DEFAULT, v5_settlement: Path = V5_DEFAULT) -> dict[str, Any]:
    """Validate the immutable v4 output and v5 offline recovery sidecar."""
    v4 = _external(v4_root)
    v5 = _external(v5_settlement)
    if not v4.is_dir() or not v5.is_file():
        raise ValueError("Sequence-178 admission inputs are missing")
    sidecar = read_json(v5)
    if sha(v5) != EXPECTED_V5_RECORD or sidecar.get("format_version") != 1 or sidecar.get("kind") != "offline_recovered_completion_v5" or sidecar.get("sequence") != 178 or sidecar.get("provider_calls") != 0 or sidecar.get("completion_sha256") != EXPECTED_V4_RUN or sidecar.get("reason") != "post-run session-validator AttributeError; six batches and 179 verdicts already accepted":
        raise ValueError("V5 sequence-178 recovery sidecar drifted")
    failed = sidecar.get("failed_v4")
    if not isinstance(failed, Mapping) or failed.get("root") != str(v4):
        raise ValueError("V5 sidecar is not bound to this exact v4 root")

    rows = _manifest(v4)
    if len(rows) != EXPECTED_V4_FILES or _manifest_sha(rows) != EXPECTED_V4_TREE or list(failed.get("files", [])) != rows:
        raise ValueError("V4 immutable evidence manifest drifted")
    journal = v4 / "execution-journal.jsonl"
    claim = v4 / "active-epoch-claim.json"
    if sha(journal) != EXPECTED_V4_JOURNAL or sha(claim) != EXPECTED_V4_CLAIM:
        raise ValueError("V4 journal or active claim drifted")
    journal_rows = _jsonl(journal)
    if len(journal_rows) != 2 or [row.get("event") for row in journal_rows] != ["capacity-checked", "attempt-intent"] or journal_rows[0].get("sequence") != 178 or journal_rows[1].get("sequence") != 178:
        raise ValueError("V4 is not the sealed unfinished sequence-178 root")

    output = v4 / "runs" / "hanna-52" / "hbq_short_story_batch32" / "run-05"
    run = output / "run.json"
    verdicts = output / "verdicts.jsonl"
    batches = sorted((output / "responses").glob("batch-????.json"))
    if sha(run) != EXPECTED_V4_RUN or sha(verdicts) != EXPECTED_V4_VERDICTS or len(batches) != 6:
        raise ValueError("V4 sequence-178 accepted output commitments drifted")
    run_value = read_json(run)
    questions = run_value.get("configuration", {}).get("question_ids")
    verdict_rows = _jsonl(verdicts)
    if not isinstance(questions, list) or len(questions) != 179 or len(verdict_rows) != 179 or [row.get("question_id") for row in verdict_rows] != questions or any(row.get("judge_id") != "codex:gpt-5.6-sol" or row.get("run_id") != run_value.get("run_id") for row in verdict_rows):
        raise ValueError("V4 sequence-178 verdict ordering or judge binding drifted")
    sessions: list[str] = []
    for batch in batches:
        found = _session_ids(read_json(batch))
        if len(found) != 1:
            raise ValueError("V4 batch session evidence is missing or ambiguous")
        sessions.append(found[0])
    if len(set(sessions)) != 6:
        raise ValueError("V4 sequence-178 batch sessions are not unique")
    session_hash = hashlib.sha256(canonical(sorted(hashlib.sha256(item.encode("utf-8")).hexdigest() for item in sessions))).hexdigest()
    if session_hash != EXPECTED_V4_SESSIONS:
        raise ValueError("V4 sequence-178 session commitment drifted")
    if failed.get("root") != str(v4) or failed.get("tree_sha256") != EXPECTED_V4_TREE or failed.get("journal_sha256") != EXPECTED_V4_JOURNAL or failed.get("claim_sha256") != EXPECTED_V4_CLAIM or failed.get("run_sha256") != EXPECTED_V4_RUN or failed.get("verdicts_sha256") != EXPECTED_V4_VERDICTS or failed.get("session_sha256") != EXPECTED_V4_SESSIONS or failed.get("batch_count") != 6 or failed.get("verdict_count") != 179 or list(failed.get("files", [])) != rows:
        raise ValueError("V5 sidecar does not exactly settle the validated v4 evidence")
    return {
        "sequence": 178,
        "v4_root": str(v4),
        "v4_tree_sha256": EXPECTED_V4_TREE,
        "v4_journal_sha256": EXPECTED_V4_JOURNAL,
        "v4_claim_sha256": EXPECTED_V4_CLAIM,
        "v4_run_sha256": EXPECTED_V4_RUN,
        "v4_verdicts_sha256": EXPECTED_V4_VERDICTS,
        "v4_session_sha256": EXPECTED_V4_SESSIONS,
        "v5_settlement": str(v5),
        "v5_record_sha256": EXPECTED_V5_RECORD,
        "v5_completion_sha256": EXPECTED_V4_RUN,
    }


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
    return _load_module(SUCCESSOR_RUNNER, "v6_successor_runner", study_path=SUCCESSOR_STUDY)


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
        expected = (
            contract()["lineage"]["closed_successor_runner_retry_hook_git_blob_oid_sha1"]
            if path == SUCCESSOR_RUNNER
            else _git_blob_sha1(commit, relative)
        )
        if not re.fullmatch(r"[0-9a-f]{40}", current):
            raise ValueError(f"Current Git blob is not a SHA-1 object ID: {relative}")
        if current != expected:
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
    files = [_runtime_file(path, require_tracked=False) for path in [CONTRACT_PATH, HERE / "executor.py"]]
    files.extend(_runtime_file(path) for path in _executed_dependencies(frozen))
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
    schedule = full[1:]
    if len(schedule) != c["count"] or [row.get("sequence") for row in schedule] != list(range(c["first_sequence"], c["last_sequence"] + 1)) or hashlib.sha256(canonical(schedule)).hexdigest() != c["sha256"]:
        raise ValueError("V6 fresh schedule commitment drifted")
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
        successor_runner = _load_successor_runner()
        rendered = successor_runner._artifact_prompt(
            rubric_file.read_text(encoding="utf-8"),
            source_file.read_text(encoding="utf-8"),
            prompt_file.read_text(encoding="utf-8"),
        ).encode("utf-8")
        provider_schema = successor_runner._structured_json_bytes(
            successor_runner._provider_response_schema(read_json(schema_file))
        )
        provider_payloads = [_provider_payload(1, rendered, provider_schema)]
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


def _prepared_binding(source: Path, closed: Path, v4: Path, v5: Path, work: Path, admission: Mapping[str, Any], schedule: list[dict[str, Any]], disclosure_sha256: str, frozen: Mapping[str, Any]) -> dict[str, Any]:
    c = contract()
    return {
        "format_version": 1,
        "study_id": c["study_id"],
        "roots": {"source": str(source), "closed": str(closed), "v4": str(v4), "v5_settlement": str(v5)},
        "admitted_prefix": dict(admission),
        "schedule": {"count": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"], "sha256": hashlib.sha256(canonical(schedule)).hexdigest()},
        "disclosure_sha256": disclosure_sha256,
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
        "admitted_sequence": 178,
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
    _assert_plain_tree(work, "V6 work root")


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
    messages = sorted((output / "responses").glob("batch-0001.attempt-[0-9][0-9][0-9][0-9].message.json"))
    if not 1 <= len(messages) <= 3:
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
        observed = len(sorted((output / "responses").glob("batch-0001.attempt-[0-9][0-9][0-9][0-9].message.json")))
        if observed > 3:
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
    return {
        "logical_cells": len(schedule),
        "accepted_cells": len(accepted),
        "accepted_count_basis": "validated output files in the contiguous journal prefix",
        "minimum_physical_provider_contacts": _minimum_contacts(schedule),
        "retry_ceiling": _minimum_contacts(schedule) * 3,
        "accepted_minimum_physical_provider_contacts": _minimum_contacts(accepted),
        "accepted_retry_ceiling": _minimum_contacts(accepted) * 3,
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
    active: dict[int, dict[str, Any]] = {}
    contacts: set[int] = set()
    paused: dict[int, dict[str, Any]] = {}
    expected_index = 0
    for row in rows[1:]:
        kind, sequence = row.get("event"), row.get("sequence")
        if kind == "attempt-intent":
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


def prepare(source_root: Path, closed_root: Path, v4_root: Path, v5_settlement: Path, work_root: Path) -> dict[str, Any]:
    source, closed, v4, v5, work = _roots(source_root, closed_root, v4_root, v5_settlement, work_root)
    if work.exists() and any(work.iterdir()):
        raise ValueError("Fresh v6 root must be empty; use dry-run validation to reload it")
    admission = admit_sequence_178(v4, v5)
    schedule = _fresh_schedule(closed)
    _source_and_closed(source, closed)
    frozen = read_json(source / "frozen-run-contract.json")
    work.mkdir(parents=True, exist_ok=True)
    disclosure = _preflight_disclosure(source, schedule, frozen)
    _write_immutable(work / DISCLOSURE, disclosure)
    binding = _prepared_binding(source, closed, v4, v5, work, admission, schedule, sha(work / DISCLOSURE), frozen)
    _write_immutable(work / BINDING, binding)
    _write_immutable(work / ADMISSION, admission)
    for row in schedule:
        _append(work / SCHEDULE, row)
    _append(work / JOURNAL, {"event": "admitted-prefix", **admission})
    return {"provider_calls": 0, "admitted_sequence": 178, "cells": len(schedule), "first_sequence": schedule[0]["sequence"], "last_sequence": schedule[-1]["sequence"], "work_root": str(work), "disclosure_path": str(work / DISCLOSURE), "disclosure_sha256": sha(work / DISCLOSURE), "destination": "codex", "profile": contract()["provider"], "accounting": _accounting(schedule, [])}


def _verify_prepared(source_root: Path, closed_root: Path, v4_root: Path, v5_settlement: Path, work_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    source, closed, v4, v5, work = _roots(source_root, closed_root, v4_root, v5_settlement, work_root)
    if not work.is_dir():
        raise ValueError("Prepared v6 root is missing")
    _assert_plain_work_tree(work)
    admission = admit_sequence_178(v4, v5)
    schedule = _fresh_schedule(closed)
    frozen = read_json(source / "frozen-run-contract.json")
    expected_disclosure = _preflight_disclosure(source, schedule, frozen)
    if read_json(work / DISCLOSURE) != expected_disclosure:
        raise ValueError("V6 preflight disclosure drifted")
    expected = _prepared_binding(source, closed, v4, v5, work, admission, schedule, sha(work / DISCLOSURE), frozen)
    if read_json(work / BINDING) != expected or read_json(work / ADMISSION) != admission or _jsonl(work / SCHEDULE) != schedule:
        raise ValueError("V6 prepared provenance drifted")
    if _read_journal(work)[:1] != [{"event": "admitted-prefix", **admission}]:
        raise ValueError("V6 admission journal drifted")
    allowed = {BINDING, ADMISSION, DISCLOSURE, DISCLOSURE_ACK, RETRY_DISCLOSURES, RETRY_ACKS, UNRESOLVED_RECOVERY, SCHEDULE, JOURNAL, CLAIM, PROOFS, "runs"}
    unexpected = {path.name for path in work.iterdir()} - allowed
    if unexpected:
        raise ValueError(f"V6 work root contains unexpected entries: {sorted(unexpected)}")
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
    return runner._run_event(
        runner._v1_runner(),
        event,
        frozen,
        source,
        work,
        timeout,
        before_provider_attempt=before_provider_attempt,
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
    runner._revalidate_predecessor_event(source, frozen, event)
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
        runner._revalidate_predecessor_event(source, frozen, event)
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

        output = _dispatch_event(runner, event, frozen, source, work, timeout, before_provider_attempt)
        runner._validate_global_sessions(source, work, [*accepted, event])
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


def execute(source_root: Path, closed_root: Path, v4_root: Path, v5_settlement: Path, work_root: Path, capacity_evidence: Path | None = None, *, timeout: float = 3600.0, allow_remote: bool = False, dry_run: bool = False, disclosure_ack: Path | None = None, retry_disclosure_ack: Path | None = None) -> dict[str, Any]:
    work = _external(work_root, allow_missing_leaf=True)
    if not work.exists():
        prepare(source_root, closed_root, v4_root, v5_settlement, work)
    if dry_run and not any(work.iterdir()):
        prepare(source_root, closed_root, v4_root, v5_settlement, work)
    binding, schedule, admission = _verify_prepared(source_root, closed_root, v4_root, v5_settlement, work)
    accepted = _accepted(work, schedule, admission)
    remaining = schedule[len(accepted):]
    if dry_run:
        accounting = _accounting(schedule, accepted)
        return {"provider_calls": 0, "admitted_sequence": 178, "completed": len(accepted), "cells": len(remaining), "first_sequence": remaining[0]["sequence"] if remaining else None, "last_sequence": remaining[-1]["sequence"] if remaining else None, "prepared": True, "disclosure_path": str(work / DISCLOSURE), "disclosure_sha256": sha(work / DISCLOSURE), "destination": "codex", "profile": contract()["provider"], "accounting": accounting}
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
                    "admitted_sequence": 178,
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
        "admitted_sequence": 178,
        "completed": len(accepted),
        "remaining": 0,
        "max_workers": 1,
        "accounting": accounting,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=SOURCE_DEFAULT)
    parser.add_argument("--closed-root", type=Path, default=CLOSED_DEFAULT)
    parser.add_argument("--v4-root", type=Path, default=V4_DEFAULT)
    parser.add_argument("--v5-settlement", type=Path, default=V5_DEFAULT)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--capacity-evidence", type=Path)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--disclosure-ack", type=Path, help="Exact owner acknowledgement for preflight-disclosure.json")
    parser.add_argument("--retry-disclosure-ack", type=Path, help="Exact owner acknowledgement for a paused changed-payload retry disclosure")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preview-disclosure", action="store_true", help="Prepare/reload and print the exact private outbound-payload disclosure")
    args = parser.parse_args()
    result = execute(args.source_root, args.closed_root, args.v4_root, args.v5_settlement, args.work_root, args.capacity_evidence, timeout=args.timeout, allow_remote=args.allow_remote, dry_run=args.dry_run or args.preview_disclosure, disclosure_ack=args.disclosure_ack, retry_disclosure_ack=args.retry_disclosure_ack)
    if args.preview_disclosure:
        result["disclosure_preview"] = read_json(_plain_path(Path(args.work_root)) / DISCLOSURE)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
