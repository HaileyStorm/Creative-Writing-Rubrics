"""Geometry-independent, read-only reviewed-cohort ledger verification.

`cohort_ledger.py` remains immutable historical qualification evidence.  This
versioned core is its successor for explicitly supplied plan geometry.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

GENESIS_SETTLEMENT_SHA256 = "0" * 64
GENESIS_RENEWAL_SHA256 = "0" * 64
HISTORICAL_OPERATIONAL_REVISION = "49f662f1f03b636feed003b99c2f094ff19353ba"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_OPERATIONAL_FILES = (
    "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/cohort_ledger_core.py",
    "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_ledger.py",
    "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_admission.py",
    "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_execution.py",
)
_DERIVATION = "runner_normalized_verdicts_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _integer(value: Any, label: str) -> int:
    _require(type(value) is int, f"{label} must be an integer")
    return value


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        _require(isinstance(key, str) and key not in result, "JSON object has duplicate keys")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: set[str], label: str, *, version: int | None = None) -> None:
    _require(set(value) == expected, f"{label} schema differs")
    if version is not None:
        _require(_integer(value.get("schema_version"), f"{label} schema version") == version, f"{label} schema version differs")


def _utc(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and value.endswith(("Z", "+00:00")), f"{label} must use a zero offset")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} is not an ISO timestamp") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), f"{label} must use a zero offset")
    return parsed.astimezone(timezone.utc)


def _reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _tree(root: Path, label: str) -> tuple[dict[str, str], frozenset[str]]:
    try:
        info = root.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is missing") from error
    _require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and not _reparse(info), f"{label} must be a plain directory")
    files: dict[str, str] = {}
    directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            info = entry.stat(follow_symlinks=False)
            relative = Path(entry.path).relative_to(root).as_posix()
            _require(not stat.S_ISLNK(info.st_mode) and not _reparse(info), f"{label} contains a link or reparse point")
            if stat.S_ISDIR(info.st_mode):
                directories.add(relative); pending.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                files[relative] = digest(Path(entry.path).read_bytes())
            else:
                raise ValueError(f"{label} contains a non-regular entry")
    return files, frozenset(directories)


def _snapshot(execution_root: Path) -> tuple[dict[str, str], frozenset[str]]:
    root = Path(execution_root)
    for ancestor in Path(os.path.abspath(root)).parents:
        info = ancestor.lstat()
        _require(not stat.S_ISLNK(info.st_mode) and not _reparse(info), "Execution ancestry contains a link")
    files: dict[str, str] = {}
    directories: set[str] = set()
    try:
        root_info = root.lstat()
    except FileNotFoundError as error:
        raise ValueError("Execution root is missing") from error
    _require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode) and not _reparse(root_info), "Execution root must be a plain directory")
    for name in ("cohorts", "contacts"):
        child_files, child_directories = _tree(root / name, name)
        files.update({f"{name}/{path}": value for path, value in child_files.items()})
        directories.update({f"{name}/{path}" for path in child_directories})
    return files, frozenset(directories)


def _read(root: Path, relative: str, snapshot: Mapping[str, str]) -> bytes:
    _require(relative in snapshot, f"Ledger file is missing: {relative}")
    raw = (root / relative).read_bytes()
    _require(digest(raw) == snapshot[relative], f"Ledger file changed during read: {relative}")
    return raw


def _directories(files: set[str]) -> frozenset[str]:
    result: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while len(parent.parts) > 1:
            result.add(parent.as_posix()); parent = parent.parent
    return frozenset(result)


def _pending(paths: frozenset[str]) -> frozenset[str]:
    _require(isinstance(paths, frozenset) and all(type(item) is str for item in paths), "Pending paths differ")
    for item in paths:
        path = PurePosixPath(item)
        _require(path.parts and not path.is_absolute() and path.as_posix() == item and all(part not in (".", "..") for part in path.parts) and path.parts[0] in {"cohorts", "contacts"}, "Pending path escapes ledger")
    return paths


def _route_hash(route: Mapping[str, Any]) -> str:
    _require(isinstance(route, Mapping), "Route snapshot differs")
    return digest(canonical(dict(route)))


def _source_manifest(value: Any, label: str, *, require_current: bool) -> dict[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == {"revision", "files"}, f"{label} source manifest differs")
    revision, files = value["revision"], value["files"]
    _require(isinstance(revision, str) and _REVISION.fullmatch(revision) is not None
             and isinstance(files, Mapping) and set(files) == set(_OPERATIONAL_FILES)
             and all(_hash(item) for item in files.values()), f"{label} source manifest differs")
    repository = Path(__file__).resolve().parents[2]
    for relative in _OPERATIONAL_FILES:
        result = subprocess.run(("git", "-C", str(repository), "show", f"{revision}:{relative}"),
                                check=False, capture_output=True)
        _require(result.returncode == 0 and digest(result.stdout) == files[relative],
                 f"{label} source manifest Git evidence differs")
        if require_current:
            path = repository / relative
            _require(path.is_file() and digest(path.read_bytes()) == files[relative],
                     f"{label} current source differs")
    return {"revision": revision, "files": dict(files)}


def current_operational_source_manifest() -> dict[str, Any]:
    """Return the committed current operational source set after byte verification."""
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(("git", "-C", str(repository), "rev-parse", "HEAD"),
                            check=False, capture_output=True)
    _require(result.returncode == 0, "Current operational source revision differs")
    revision = result.stdout.decode("ascii", "strict").strip()
    value = {"revision": revision, "files": {}}
    for relative in _OPERATIONAL_FILES:
        shown = subprocess.run(("git", "-C", str(repository), "show", f"{revision}:{relative}"),
                               check=False, capture_output=True)
        _require(shown.returncode == 0, "Current operational source Git evidence differs")
        value["files"][relative] = digest(shown.stdout)
    return _source_manifest(value, "Current operational", require_current=True)


def _route_transition(old: Mapping[str, Any], new: Mapping[str, Any]) -> None:
    _require(set(old) == set(new) and "subscription_receipt_hash" in old and "cost_evidence" in old,
             "Renewal route keyset differs")
    _require(all(old[key] == new[key] for key in old if key not in {"subscription_receipt_hash", "cost_evidence"}),
             "Renewal route contract differs")
    old_cost, new_cost = old["cost_evidence"], new["cost_evidence"]
    _require(isinstance(old_cost, Mapping) and isinstance(new_cost, Mapping) and set(old_cost) == set(new_cost)
             and {"evidence_hash", "checked_at", "expires_at", "allowance_state", "kind", "version"} <= set(old_cost),
             "Renewal cost evidence keyset differs")
    _require(all(old_cost[key] == new_cost[key] for key in old_cost
                 if key not in {"evidence_hash", "checked_at", "expires_at"}),
             "Renewal cost evidence contract differs")


def _prefix_manifest(value: Any) -> dict[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == {"immutable_files", "derived_aggregate_prefixes"},
             "Renewal preserved-prefix manifest differs")
    immutable, aggregates = value["immutable_files"], value["derived_aggregate_prefixes"]
    _require(isinstance(immutable, Mapping) and isinstance(aggregates, Mapping)
             and set(immutable).isdisjoint(aggregates)
             and all(isinstance(path, str) and _hash(item) for path, item in immutable.items()),
             "Renewal immutable prefix differs")
    for path, item in aggregates.items():
        _require(isinstance(path, str) and isinstance(item, Mapping)
                 and set(item) == {"derivation", "sha256", "bytes", "verdict_count"}
                 and item.get("derivation") == _DERIVATION and _hash(item.get("sha256"))
                 and type(item.get("bytes")) is int and item["bytes"] >= 0
                 and type(item.get("verdict_count")) is int and item["verdict_count"] >= 0,
                 "Renewal aggregate prefix differs")
    return {"immutable_files": dict(immutable), "derived_aggregate_prefixes": dict(aggregates)}


def _run_files(root: Path) -> dict[str, str]:
    runs = root / "runs"
    if not runs.exists():
        return {}
    files, _ = _tree(runs, "runs")
    return {f"runs/{relative}": value for relative, value in files.items()}


def precontact_recovery_candidate(root: Path, *, cohort_number: int, ordinals: tuple[int, ...],
                                  initialization_sha256: str, previous_settlement_sha256: str,
                                  operational_renewal: Mapping[str, Any], prepared_sha256: str,
                                  review_sha256: str, route_sha256: str, reviewer_task: str,
                                  old_source_sha256: str, new_source_manifest: Mapping[str, Any],
                                  require_empty_cohort: bool = True,
                                  run_files: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Build a provider-free recovery candidate; reviewer timestamps are deliberately absent."""
    _require(type(cohort_number) is int and cohort_number > 1 and ordinals and _hash(initialization_sha256)
             and _hash(previous_settlement_sha256) and _hash(prepared_sha256) and _hash(review_sha256)
             and _hash(route_sha256) and _hash(old_source_sha256) and isinstance(reviewer_task, str) and reviewer_task,
             "Precontact recovery anchors differ")
    _require(isinstance(operational_renewal, Mapping) and _hash(operational_renewal.get("sha256"))
             and isinstance(operational_renewal.get("new_source"), Mapping),
             "Precontact recovery renewal differs")
    prepared_raw = _read(root, f"cohorts/{cohort_number:04d}/prepared.json", _snapshot(root)[0])
    review_raw = _read(root, f"cohorts/{cohort_number:04d}/review.json", _snapshot(root)[0])
    route_raw = _read(root, f"cohorts/{cohort_number:04d}/route.json", _snapshot(root)[0])
    prepared, review, route = _json(prepared_raw, "Prepared record"), _json(review_raw, "Review record"), _json(route_raw, "Route snapshot")
    _review(review_raw, prepared_sha256, reviewer_task)
    _require(digest(prepared_raw) == prepared_sha256 and digest(review_raw) == review_sha256
             and _route_hash(route) == route_sha256 and prepared.get("cohort_number") == cohort_number
             and prepared.get("previous_settlement_sha256") == previous_settlement_sha256
             and prepared.get("route_sha256") == route_sha256 and prepared.get("execution_source_sha256") == old_source_sha256
             and prepared.get("operational_renewal_sha256") == operational_renewal["sha256"]
             and review.get("reviewed_at", "").endswith("+00:00"),
             "Precontact recovery prepared evidence differs")
    if require_empty_cohort:
        _require(not any((root / "contacts" / f"request-{ordinal:04d}.json").exists() for ordinal in ordinals),
                 "Precontact recovery requires an empty cohort prefix")
    old_manifest = _source_manifest(operational_renewal["new_source"], "Precontact old operational", require_current=False)
    new_manifest = _source_manifest(new_source_manifest, "Precontact new operational", require_current=True)
    _require(old_manifest["files"][_OPERATIONAL_FILES[-1]] == old_source_sha256,
             "Precontact recovery old source differs")
    run_files = dict(_run_files(root) if run_files is None else run_files)
    _require(run_files, "Precontact recovery run prefix differs")
    _require(all(isinstance(path, str) and _hash(value) for path, value in run_files.items()),
             "Precontact recovery run prefix differs")
    return {"schema_version": 3, "reviewer_task": reviewer_task, "decision": "approved_precontact_recovery",
            "incident_type": "utc_review_encoding_mismatch", "prepared_sha256": prepared_sha256,
            "route_sha256": route_sha256, "prior_authorization_sha256": review_sha256,
            "previous_execution_source_sha256": old_source_sha256,
            "execution_source_sha256": new_manifest["files"][_OPERATIONAL_FILES[-1]],
            "completed_prefix": {"ordinals": [], "contacts": [], "run_files": run_files,
                                 "run_tree_sha256": digest(canonical(run_files))},
            "original_initialization_sha256": initialization_sha256,
            "previous_settlement_sha256": previous_settlement_sha256,
            "operational_renewal_sha256": operational_renewal["sha256"],
            "old_operational_source_manifest": old_manifest,
            "new_operational_source_manifest": new_manifest}


def _pending_precontact_recovery(root: Path, snapshot: Mapping[str, str], *, cohort_number: int,
                                 ordinals: tuple[int, ...], initialization_sha256: str,
                                 previous_settlement_sha256: str, operational_renewal: Mapping[str, Any],
                                 reviewer_task: str) -> dict[str, Any] | None:
    relative = f"cohorts/{cohort_number:04d}/review-continuations/0001.json"
    if relative not in snapshot:
        return None
    raw = _read(root, relative, snapshot)
    value = _json(raw, "Precontact recovery")
    if value.get("schema_version") != 3:
        return None
    _require(set(value) == {"schema_version", "reviewer_task", "decision", "incident_type", "prepared_sha256",
                            "route_sha256", "prior_authorization_sha256", "previous_execution_source_sha256",
                            "execution_source_sha256", "completed_prefix", "original_initialization_sha256",
                            "previous_settlement_sha256", "operational_renewal_sha256",
                            "old_operational_source_manifest", "new_operational_source_manifest", "reviewed_at",
                            "expires_at"}, "Precontact recovery schema differs")
    candidate = {key: item for key, item in value.items() if key not in {"reviewed_at", "expires_at"}}
    prefix = value.get("completed_prefix")
    _require(isinstance(prefix, Mapping) and isinstance(prefix.get("run_files"), Mapping)
             and all(path in _run_files(root) for path in prefix["run_files"]),
             "Precontact recovery run prefix differs")
    expected = precontact_recovery_candidate(
        root, cohort_number=cohort_number, ordinals=ordinals, initialization_sha256=initialization_sha256,
        previous_settlement_sha256=previous_settlement_sha256, operational_renewal=operational_renewal,
        prepared_sha256=value["prepared_sha256"], review_sha256=value["prior_authorization_sha256"],
        route_sha256=value["route_sha256"], reviewer_task=reviewer_task,
        old_source_sha256=value["previous_execution_source_sha256"],
        new_source_manifest=value["new_operational_source_manifest"], require_empty_cohort=False,
        run_files=prefix["run_files"],
    )
    _require(candidate == expected, "Precontact recovery binding differs")
    start, end = _utc(value["reviewed_at"], "Precontact recovery review time"), _utc(value["expires_at"], "Precontact recovery expiry")
    _require(start < end <= start + timedelta(minutes=15), "Precontact recovery review window differs")
    return {"sha256": digest(raw), "value": value, "source_sha256": value["execution_source_sha256"],
            "reviewed_at": start, "expires_at": end}


def _renewals(root: Path, snapshot: Mapping[str, str], geometry: LedgerGeometry, *,
              initialization_sha256: str, through_cohort: int) -> list[dict[str, Any]]:
    pattern = re.compile(r"cohorts/(\d{4})/operational-renewals/0001\.json\Z")
    found = sorted((int(match.group(1)), relative) for relative in snapshot if (match := pattern.fullmatch(relative)))
    _require(all(1 <= number <= through_cohort for number, _ in found) and len({number for number, _ in found}) == len(found),
             "Operational renewal inventory differs")
    prior_hash = GENESIS_RENEWAL_SHA256
    prior_route_sha256: str | None = None
    prior_manifest: dict[str, Any] | None = None
    result: list[dict[str, Any]] = []
    for number, relative in found:
        raw = _read(root, relative, snapshot); value = _json(raw, "Operational renewal")
        fields = {"schema_version", "evidence_class", "reviewer_task", "decision", "original_initialization_sha256",
                  "previous_renewal_sha256", "settled_cohort_number", "settled_head_settlement_sha256",
                  "preserved_prefix", "next_cohort_number", "remaining_ordinals", "old_route", "old_route_sha256",
                  "new_route", "new_route_sha256", "old_receipt_sha256", "new_receipt_sha256",
                  "old_operational_source_manifest", "new_operational_source_manifest", "reviewed_at"}
        _keys(value, fields, "Operational renewal", version=1)
        _require(value["evidence_class"] == "independently_reviewed_operational_renewal"
                 and isinstance(value["reviewer_task"], str) and value["reviewer_task"]
                 and value["decision"] == "approved_operational_renewal"
                 and value["original_initialization_sha256"] == initialization_sha256
                 and value["previous_renewal_sha256"] == prior_hash
                 and value["settled_cohort_number"] == number and number < len(geometry.groups)
                 and value["next_cohort_number"] == number + 1
                 and _hash(value["settled_head_settlement_sha256"])
                 and isinstance(value["remaining_ordinals"], list)
                 and value["remaining_ordinals"] == [ordinal for group in geometry.groups[number:] for ordinal in group]
                 and value["remaining_ordinals"],
                 "Operational renewal binding differs")
        old_route, new_route = value["old_route"], value["new_route"]
        _require(isinstance(old_route, Mapping) and isinstance(new_route, Mapping)
                 and value["old_route_sha256"] == _route_hash(old_route)
                 and value["new_route_sha256"] == _route_hash(new_route)
                 and value["old_receipt_sha256"] == old_route.get("subscription_receipt_hash")
                 and value["new_receipt_sha256"] == new_route.get("subscription_receipt_hash")
                 and _hash(value["old_receipt_sha256"]) and _hash(value["new_receipt_sha256"]),
                 "Operational renewal route binding differs")
        _route_transition(old_route, new_route)
        old_manifest = _source_manifest(value["old_operational_source_manifest"], "Old operational", require_current=False)
        new_manifest = _source_manifest(value["new_operational_source_manifest"], "New operational", require_current=False)
        if prior_manifest is None:
            _require(old_manifest["revision"] == HISTORICAL_OPERATIONAL_REVISION, "Initial operational source revision differs")
        else:
            _require(value["old_route_sha256"] == prior_route_sha256, "Operational renewal chain differs")
            if old_manifest != prior_manifest:
                recovery_path = f"cohorts/{number:04d}/review-continuations/0001.json"
                recovery = _json(_read(root, recovery_path, snapshot), "Precontact recovery")
                _require(recovery.get("schema_version") == 3
                         and recovery.get("decision") == "approved_precontact_recovery"
                         and recovery.get("route_sha256") == prior_route_sha256
                         and _source_manifest(recovery.get("old_operational_source_manifest"), "Recovery old operational", require_current=False) == prior_manifest
                         and _source_manifest(recovery.get("new_operational_source_manifest"), "Recovery new operational", require_current=False) == old_manifest,
                         "Operational renewal recovery chain differs")
        _require(old_route["subscription_receipt_hash"] == value["old_receipt_sha256"]
                 and new_route["subscription_receipt_hash"] == value["new_receipt_sha256"]
                 and _utc(value["reviewed_at"], "Operational renewal review time") is not None,
                 "Operational renewal evidence differs")
        manifest = _prefix_manifest(value["preserved_prefix"])
        prior_hash = digest(raw)
        prior_route_sha256, prior_manifest = value["new_route_sha256"], new_manifest
        result.append({"sha256": prior_hash, "value": value, "cohort_number": number,
                       "old_source": old_manifest, "new_source": new_manifest,
                       "manifest": manifest})
    return result


def _verify_renewal_prefix(root: Path, renewal: Mapping[str, Any]) -> None:
    raw_files, _ = _tree(root, "Execution evidence")
    manifest = renewal["manifest"]
    immutable, aggregates = manifest["immutable_files"], manifest["derived_aggregate_prefixes"]
    _require(set(immutable).isdisjoint(aggregates)
             and all(raw_files.get(path) == sha256 for path, sha256 in immutable.items()),
             "Renewal preserved immutable prefix differs")
    for path, value in aggregates.items():
        raw = (root / path).read_bytes()
        _require(path in raw_files and len(raw) >= value["bytes"]
                 and digest(raw[:value["bytes"]]) == value["sha256"],
                 "Renewal preserved aggregate prefix differs")


@dataclass(frozen=True)
class LedgerGeometry:
    plan_sha256: str
    requests: Mapping[int, Mapping[str, Any]]
    passes: Mapping[str, Mapping[str, Any]]
    groups: tuple[tuple[int, ...], ...]

    def validate(self) -> None:
        _require(_hash(self.plan_sha256) and self.groups and tuple(ordinal for group in self.groups for ordinal in group) == tuple(range(1, len(self.requests) + 1)), "Ledger geometry differs")
        _require(set(self.requests) == set(range(1, len(self.requests) + 1)) and all(group and len(group) <= 10 for group in self.groups), "Ledger request geometry differs")
        for ordinal, request in self.requests.items():
            _require(isinstance(request, Mapping) and request.get("ordinal") == ordinal and isinstance(request.get("pass_id"), str) and request["pass_id"] in self.passes and _hash(request.get("prompt_sha256")) and _hash(request.get("schema_sha256")), "Ledger request binding differs")
        for pass_id, value in self.passes.items():
            _require(isinstance(pass_id, str) and isinstance(value, Mapping) and value.get("pass_id") == pass_id
                     and _hash(value.get("source_sha256")) and isinstance(value.get("logical_sample_id"), str)
                     and value["logical_sample_id"], "Ledger pass binding differs")


def _review(raw: bytes, prepared_sha256: str, reviewer_task: str) -> tuple[dict[str, Any], datetime, datetime]:
    value = _json(raw, "Review record")
    _keys(value, {"schema_version", "reviewer_task", "decision", "prepared_sha256", "reviewed_at", "expires_at"}, "Review record", version=1)
    _require(value["reviewer_task"] == reviewer_task and value["decision"] == "approved_cohort" and value["prepared_sha256"] == prepared_sha256, "Review approval differs")
    start, end = _utc(value["reviewed_at"], "Review time"), _utc(value["expires_at"], "Review expiry")
    _require(start < end <= start + timedelta(minutes=15), "Review window differs")
    return value, start, end


def _continuations(root: Path, prefix: str, snapshot: Mapping[str, str], prepared_sha256: str, route_sha256: str,
                   review_sha256: str, source_sha256: str, reviewer_task: str, *,
                   initialization_sha256: str, previous_settlement_sha256: str,
                   operational_renewal_sha256: str | None,
                   operational_source_manifest: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    pattern = re.compile(re.escape(prefix) + r"/review-continuations/(\d{4})\.json\Z")
    found = sorted((int(match.group(1)), relative) for relative in snapshot if (match := pattern.fullmatch(relative)))
    _require([number for number, _ in found] == list(range(1, len(found) + 1)), "Continuation inventory differs")
    prior_hash, prior_source = review_sha256, source_sha256
    result: list[dict[str, Any]] = []
    for _, relative in found:
        raw = _read(root, relative, snapshot); value = _json(raw, "Continuation record")
        fields = {"schema_version", "reviewer_task", "decision", "prepared_sha256", "route_sha256", "prior_authorization_sha256", "previous_execution_source_sha256", "execution_source_sha256", "completed_prefix", "reviewed_at", "expires_at"}
        version = _integer(value.get("schema_version"), "Continuation schema version")
        _require(version in {1, 2, 3}, "Continuation schema version differs")
        if version == 3:
            recovery_fields = fields | {"incident_type", "original_initialization_sha256", "previous_settlement_sha256",
                                        "operational_renewal_sha256", "old_operational_source_manifest",
                                        "new_operational_source_manifest"}
            _keys(value, recovery_fields, "Precontact recovery", version=3)
            _require(not result and operational_renewal_sha256 is not None and isinstance(operational_source_manifest, Mapping)
                     and value["reviewer_task"] == reviewer_task and value["decision"] == "approved_precontact_recovery"
                     and value["incident_type"] == "utc_review_encoding_mismatch"
                     and value["prepared_sha256"] == prepared_sha256 and value["route_sha256"] == route_sha256
                     and value["prior_authorization_sha256"] == prior_hash and value["previous_execution_source_sha256"] == prior_source
                     and value["original_initialization_sha256"] == initialization_sha256
                     and value["previous_settlement_sha256"] == previous_settlement_sha256
                     and value["operational_renewal_sha256"] == operational_renewal_sha256,
                     "Precontact recovery binding differs")
            old_manifest = _source_manifest(value["old_operational_source_manifest"], "Precontact old operational", require_current=False)
            new_manifest = _source_manifest(value["new_operational_source_manifest"], "Precontact new operational", require_current=False)
            _require(old_manifest == dict(operational_source_manifest)
                     and old_manifest["files"][_OPERATIONAL_FILES[-1]] == prior_source
                     and new_manifest["files"][_OPERATIONAL_FILES[-1]] == value["execution_source_sha256"],
                     "Precontact recovery source manifest differs")
        else:
            _keys(value, fields, "Continuation record", version=version)
            _require(value["reviewer_task"] == reviewer_task and value["decision"] == "approved_continuation"
                     and value["prepared_sha256"] == prepared_sha256 and value["route_sha256"] == route_sha256
                     and value["prior_authorization_sha256"] == prior_hash and value["previous_execution_source_sha256"] == prior_source
                     and value["execution_source_sha256"] == prior_source, "Continuation binding differs")
        _require(_hash(value["execution_source_sha256"]), "Continuation binding differs")
        _, start, end = _review(canonical({"schema_version": 1, "reviewer_task": value["reviewer_task"], "decision": "approved_cohort", "prepared_sha256": value["prepared_sha256"], "reviewed_at": value["reviewed_at"], "expires_at": value["expires_at"]}), prepared_sha256, reviewer_task)
        prefix_value = value["completed_prefix"]
        _require(isinstance(prefix_value, Mapping) and set(prefix_value) == {"ordinals", "contacts", "run_files", "run_tree_sha256"} and isinstance(prefix_value["ordinals"], list) and (version in {2, 3} or prefix_value["ordinals"]) and all(type(item) is int for item in prefix_value["ordinals"]) and (not prefix_value["ordinals"] or prefix_value["ordinals"] == list(range(prefix_value["ordinals"][0], prefix_value["ordinals"][0] + len(prefix_value["ordinals"])))) and isinstance(prefix_value["contacts"], list) and len(prefix_value["contacts"]) == len(prefix_value["ordinals"]) and isinstance(prefix_value["run_files"], dict) and (version == 2 or prefix_value["run_files"]) and all(isinstance(path, str) and _hash(value) for path, value in prefix_value["run_files"].items()) and _hash(prefix_value["run_tree_sha256"]) and digest(canonical(prefix_value["run_files"])) == prefix_value["run_tree_sha256"] and (version != 3 or not prefix_value["ordinals"] and not prefix_value["contacts"]), "Continuation prefix differs")
        for ordinal, contact in zip(prefix_value["ordinals"], prefix_value["contacts"], strict=True):
            _require(isinstance(contact, Mapping) and set(contact) == {"ordinal", "contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash"} and contact.get("ordinal") == ordinal and all(_hash(contact.get(field)) for field in ("contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash")), "Continuation prefix contact differs")
        prior_hash, prior_source = digest(raw), value["execution_source_sha256"]
        result.append({"sha256": prior_hash, "source_sha256": prior_source, "value": value, "start": start, "end": end, "version": version})
    return result


def validate_candidate_cohort(geometry: LedgerGeometry, *, cohort_number: int, ordinals: tuple[int, ...],
                              prepared_sha256: str, review_sha256: str, route_sha256: str,
                              previous_settlement_sha256: str, review_start: datetime, review_end: datetime,
                              continuations: list[dict[str, Any]], settlement: Mapping[str, Any],
                              contact_records: Mapping[int, bytes], expected_execution_source_sha256: str,
                              request_ids: set[str] | None = None, session_ids: set[str] | None = None) -> tuple[dict[int, dict[str, Any]], dict[str, tuple[str, datetime, datetime]]]:
    """Validate one complete candidate before its immutable settlement is written."""
    fields = {"schema_version", "cohort_number", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "previous_settlement_sha256", "settled_at", "contacts"}
    version = _integer(settlement.get("schema_version"), "Settlement schema version")
    if version == 1:
        _keys(settlement, fields, "Settlement record", version=1)
        _require(not continuations, "Legacy settlement cannot retain continuations")
    elif version == 2:
        _keys(settlement, fields | {"authorization_chain"}, "Settlement record", version=2)
        _require(all(item["version"] == 1 for item in continuations), "Settlement continuation schema differs")
    elif version == 3:
        _keys(settlement, fields | {"authorization_chain"}, "Settlement record", version=3)
        _require(all(item["version"] in {2, 3} for item in continuations), "Settlement continuation schema differs")
    else:
        raise ValueError("Settlement schema version differs")
    settled_at = _utc(settlement["settled_at"], "Settlement time")
    _require(settlement["cohort_number"] == cohort_number and settlement["plan_sha256"] == geometry.plan_sha256 and settlement["prepared_sha256"] == prepared_sha256 and settlement["review_sha256"] == review_sha256 and settlement["route_sha256"] == route_sha256 and settlement["previous_settlement_sha256"] == previous_settlement_sha256 and isinstance(settlement["contacts"], list) and [item.get("ordinal") if isinstance(item, dict) else None for item in settlement["contacts"]] == list(ordinals), "Settlement binding differs")
    _require(review_start < review_end <= review_start + timedelta(minutes=15), "Review window differs")
    prior_reviewed_at = review_start
    for item in continuations:
        _require(isinstance(item, Mapping) and _hash(item.get("sha256")) and _hash(item.get("source_sha256"))
                 and item.get("version") in {1, 2, 3} and isinstance(item.get("start"), datetime)
                 and isinstance(item.get("end"), datetime) and item["start"] < item["end"] <= item["start"] + timedelta(minutes=15)
                 and item["start"] >= prior_reviewed_at, "Continuation review order differs")
        prior_reviewed_at = item["start"]
    authorization = [(review_sha256, expected_execution_source_sha256, review_start, review_end), *[(item["sha256"], item["source_sha256"], item["start"], item["end"]) for item in continuations]]
    authorization_by_hash = {key: (source, start, end) for key, source, start, end in authorization}
    _require(len(authorization_by_hash) == len(authorization), "Authorization chain differs")
    used: dict[str, list[int]] = {key: [] for key in authorization_by_hash}
    local_request_ids: set[str] = set()
    local_session_ids: set[str] = set()
    contacts: dict[int, dict[str, Any]] = {}
    contact_times: dict[int, datetime] = {}
    for ordinal, summary in zip(ordinals, settlement["contacts"], strict=True):
        _keys(summary, {"ordinal", "contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash"}, "Settlement contact")
        _require(all(_hash(summary[field]) for field in ("contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash")) and summary["request_id_hash"] not in local_request_ids and summary["session_id_hash"] not in local_session_ids and (request_ids is None or summary["request_id_hash"] not in request_ids) and (session_ids is None or summary["session_id_hash"] not in session_ids), "Native identity is duplicated")
        raw = contact_records.get(ordinal)
        _require(isinstance(raw, bytes), "Contact record is missing")
        contact = _json(raw, "Contact record")
        _keys(contact, {"schema_version", "cohort_number", "ordinal", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "prompt_sha256", "schema_sha256", "admitted_at"}, "Contact record", version=1)
        request = geometry.requests[ordinal]
        passed = geometry.passes[request["pass_id"]]
        _require(digest(raw) == summary["contact_sha256"] and contact["cohort_number"] == cohort_number and contact["ordinal"] == ordinal and contact["plan_sha256"] == geometry.plan_sha256 and contact["prepared_sha256"] == prepared_sha256 and contact["route_sha256"] == route_sha256 and contact["review_sha256"] in authorization_by_hash and contact["prompt_sha256"] == request["prompt_sha256"] and contact["schema_sha256"] == request["schema_sha256"], "Contact binding differs")
        admitted_at = _utc(contact["admitted_at"], "Contact admission time")
        source, start, end = authorization_by_hash[contact["review_sha256"]]
        _require(start <= admitted_at <= end and admitted_at <= settled_at, "Contact is outside its authorization window")
        local_request_ids.add(summary["request_id_hash"])
        local_session_ids.add(summary["session_id_hash"])
        used[contact["review_sha256"]].append(ordinal)
        contact_times[ordinal] = admitted_at
        contacts[ordinal] = {"ordinal": ordinal, "pass_id": request["pass_id"], "logical_sample_id": passed["logical_sample_id"], "source_sha256": passed["source_sha256"], "prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"], "route_sha256": route_sha256, "execution_source_sha256": source, "authorization_sha256": contact["review_sha256"], **summary}
    if version in {2, 3}:
        chain = settlement["authorization_chain"]
        _require(isinstance(chain, list) and len(chain) == len(authorization) and [ordinal for key, _, _, _ in authorization for ordinal in used[key]] == list(ordinals), "Settlement authorization order differs")
        for (expected_sha, source, _, _), record in zip(authorization, chain, strict=True):
            _require(isinstance(record, Mapping) and set(record) == {"authorization_sha256", "execution_source_sha256", "ordinals"} and record.get("authorization_sha256") == expected_sha and record.get("execution_source_sha256") == source and record.get("ordinals") == used[expected_sha], "Settlement authorization differs")
        if version == 2:
            _require(all(used[key] for key, _, _, _ in authorization), "Settlement authorization order differs")
        else:
            for index, (key, _, _, expires_at) in enumerate(authorization[:-1]):
                if not used[key]:
                    _require(authorization[index + 1][2] >= expires_at, "Unused authorization renewal differs")
        completed = 0
        for index, continuation in enumerate(continuations):
            completed += len(used[authorization[index][0]])
            prefix = continuation["value"]["completed_prefix"]
            _require(prefix["ordinals"] == list(ordinals[:completed]) and completed < len(ordinals) and prefix["contacts"] == settlement["contacts"][:completed], "Continuation prefix differs")
            if completed:
                _require(continuation["start"] >= max(contact_times[item] for item in prefix["ordinals"]), "Continuation review precedes completed prefix")
    if request_ids is not None:
        request_ids.update(local_request_ids)
    if session_ids is not None:
        session_ids.update(local_session_ids)
    return contacts, authorization_by_hash


def verify_prefix(execution_root: Path, geometry: LedgerGeometry, expected_settlement_sha256: str, through_cohort: int, *, expected_route_sha256: str, expected_execution_source_sha256: str, reviewer_task: str, allowed_pending_paths: frozenset[str] = frozenset(), pending_precontact_recovery: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Verify a closed contiguous prefix; this function never contacts a provider."""
    geometry.validate()
    _require(all(_hash(value) for value in (expected_settlement_sha256, expected_route_sha256, expected_execution_source_sha256)) and isinstance(reviewer_task, str) and reviewer_task, "Expected ledger anchors differ")
    _require(type(through_cohort) is int and 0 <= through_cohort <= len(geometry.groups), "Prefix cohort differs")
    pending = _pending(allowed_pending_paths); root = Path(execution_root); files, directories = _snapshot(root)
    expected_files: set[str] = set()
    for number in range(1, through_cohort + 1):
        prefix = f"cohorts/{number:04d}"; expected_files.update(f"{prefix}/{name}" for name in ("prepared.json", "review.json", "route.json", "settlement.json"))
    expected_files.update(f"contacts/request-{ordinal:04d}.json" for group in geometry.groups[:through_cohort] for ordinal in group)
    continuation_pattern = re.compile(r"cohorts/(\d{4})/review-continuations/(\d{4})\.json\Z")
    for relative in files:
        if match := continuation_pattern.fullmatch(relative):
            number = int(match.group(1)); _require(1 <= number <= len(geometry.groups) and (number <= through_cohort or relative in pending), "Continuation inventory differs")
            if number <= through_cohort: expected_files.add(relative)
    renewal_pattern = re.compile(r"cohorts/(\d{4})/operational-renewals/0001\.json\Z")
    renewal_paths = [relative for relative in files if renewal_pattern.fullmatch(relative)]
    if renewal_paths:
        initialization_raw = (root / "initialization.json").read_bytes()
        initialization_sha256 = digest(initialization_raw)
        renewals = _renewals(root, files, geometry, initialization_sha256=initialization_sha256,
                             through_cohort=through_cohort)
    else:
        renewals = []
        initialization_sha256 = digest((root / "initialization.json").read_bytes()) if (root / "initialization.json").is_file() else ""
    for relative in files:
        if match := renewal_pattern.fullmatch(relative):
            number = int(match.group(1)); _require(number <= through_cohort, "Operational renewal inventory differs")
            expected_files.add(relative)
    _require(expected_files.isdisjoint(pending) and set(files) == expected_files | set(pending) and directories == _directories(expected_files | set(pending)), "Ledger inventory differs")
    if renewals:
        initialization = _json(initialization_raw, "Initialization")
        _require(initialization.get("route_sha256") == expected_route_sha256
                 and initialization.get("execution_source_sha256") == expected_execution_source_sha256
                 and all(item["value"]["original_initialization_sha256"] == initialization_sha256 for item in renewals),
                 "Operational renewal initialization differs")
    renewals_by_cohort = {item["cohort_number"]: item for item in renewals}
    pending_recovery: dict[str, Any] | None = None
    if renewals and through_cohort < len(geometry.groups):
        next_cohort = through_cohort + 1
        recovery_path = f"cohorts/{next_cohort:04d}/review-continuations/0001.json"
        if recovery_path in files:
            _require(recovery_path in pending, "Precontact recovery inventory differs")
            pending_recovery = _pending_precontact_recovery(
                root, files, cohort_number=next_cohort, ordinals=geometry.groups[next_cohort - 1],
                initialization_sha256=initialization_sha256, previous_settlement_sha256=expected_settlement_sha256,
                operational_renewal=renewals[-1], reviewer_task=reviewer_task,
            )
        if pending_precontact_recovery is not None:
            _require(recovery_path not in files, "Precontact recovery already exists")
            candidate = precontact_recovery_candidate(
                root, cohort_number=next_cohort, ordinals=geometry.groups[next_cohort - 1],
                initialization_sha256=initialization_sha256, previous_settlement_sha256=expected_settlement_sha256,
                operational_renewal=renewals[-1], prepared_sha256=pending_precontact_recovery.get("prepared_sha256"),
                review_sha256=pending_precontact_recovery.get("prior_authorization_sha256"),
                route_sha256=pending_precontact_recovery.get("route_sha256"),
                reviewer_task=reviewer_task, old_source_sha256=pending_precontact_recovery.get("previous_execution_source_sha256"),
                new_source_manifest=pending_precontact_recovery.get("new_operational_source_manifest"),
            )
            _require(dict(pending_precontact_recovery) == candidate, "Precontact recovery candidate differs")
            pending_recovery = {"value": candidate, "source_sha256": candidate["execution_source_sha256"]}
    _require(pending_precontact_recovery is None or pending_recovery is not None, "Precontact recovery candidate differs")
    previous_settlement, previous_settled = GENESIS_SETTLEMENT_SHA256, None
    current_route_sha256, current_source_sha256 = expected_route_sha256, expected_execution_source_sha256
    current_renewal_sha256: str | None = None
    current_operational_manifest: Mapping[str, Any] | None = None
    current_source_manifest: Mapping[str, Any] | None = None
    contacts: dict[int, dict[str, Any]] = {}; request_ids: set[str] = set(); session_ids: set[str] = set(); routes: dict[str, dict[str, Any]] = {}
    authorizations: dict[str, dict[str, Any]] = {}
    epochs: dict[int, dict[str, Any]] = {}
    for number, ordinals in enumerate(geometry.groups[:through_cohort], start=1):
        prefix = f"cohorts/{number:04d}"; prepared_raw = _read(root, f"{prefix}/prepared.json", files); review_raw = _read(root, f"{prefix}/review.json", files); route_raw = _read(root, f"{prefix}/route.json", files); settlement_raw = _read(root, f"{prefix}/settlement.json", files)
        prepared, route, settlement = _json(prepared_raw, "Prepared record"), _json(route_raw, "Route snapshot"), _json(settlement_raw, "Settlement record")
        prepared_sha, review_sha, route_sha = digest(prepared_raw), digest(review_raw), digest(canonical(route))
        prepared_fields = {"schema_version", "cohort_number", "plan_sha256", "previous_settlement_sha256", "request_ordinals", "route_sha256", "execution_source_sha256"}
        version = _integer(prepared.get("schema_version"), "Prepared schema version")
        if version == 1:
            _keys(prepared, prepared_fields, "Prepared record", version=1)
            _require(current_renewal_sha256 is None, "Renewal-bound cohort requires preparation schema 2")
        elif version == 2:
            _keys(prepared, prepared_fields | {"operational_renewal_sha256"}, "Prepared record", version=2)
            _require(current_renewal_sha256 is not None and prepared["operational_renewal_sha256"] == current_renewal_sha256,
                     "Prepared operational renewal differs")
        else:
            raise ValueError("Prepared schema version differs")
        _require(prepared["cohort_number"] == number and prepared["plan_sha256"] == geometry.plan_sha256
                 and prepared["previous_settlement_sha256"] == previous_settlement
                 and tuple(prepared["request_ordinals"]) == ordinals and prepared["route_sha256"] == route_sha == current_route_sha256
                 and prepared["execution_source_sha256"] == current_source_sha256,
                 "Prepared binding differs")
        _, reviewed_at, expires_at = _review(review_raw, prepared_sha, reviewer_task); _require(previous_settled is None or reviewed_at >= previous_settled, "Review precedes previous settlement")
        _require(route_sha not in routes or routes[route_sha] == route, "Route hash collision differs"); routes[route_sha] = route
        continuations = _continuations(
            root, prefix, files, prepared_sha, route_sha, review_sha, current_source_sha256, reviewer_task,
            initialization_sha256=initialization_sha256,
            previous_settlement_sha256=previous_settlement, operational_renewal_sha256=current_renewal_sha256,
            operational_source_manifest=current_operational_manifest,
        )
        contact_records = {ordinal: _read(root, f"contacts/request-{ordinal:04d}.json", files) for ordinal in ordinals}
        cohort_contacts, authorization = validate_candidate_cohort(
            geometry, cohort_number=number, ordinals=ordinals, prepared_sha256=prepared_sha,
            review_sha256=review_sha, route_sha256=route_sha, previous_settlement_sha256=previous_settlement,
            review_start=reviewed_at, review_end=expires_at, continuations=continuations, settlement=settlement,
            contact_records=contact_records, expected_execution_source_sha256=current_source_sha256,
            request_ids=request_ids, session_ids=session_ids,
        )
        for authorization_sha, (source_sha, start, end) in authorization.items():
            _require(authorization_sha not in authorizations, "Authorization reused across cohorts")
            authorizations[authorization_sha] = {"execution_source_sha256": source_sha, "reviewed_at": start.isoformat(), "expires_at": end.isoformat(), "cohort_number": number}
        contacts.update(cohort_contacts)
        effective_source_sha256 = continuations[-1]["source_sha256"] if continuations else current_source_sha256
        recovery_continuation = next((item for item in continuations if item["version"] == 3), None)
        if recovery_continuation is not None:
            current_source_manifest = _source_manifest(
                recovery_continuation["value"]["new_operational_source_manifest"], "Precontact new operational", require_current=False)
        epochs[number] = {"route_sha256": current_route_sha256, "execution_source_sha256": effective_source_sha256,
                          "operational_renewal_sha256": current_renewal_sha256}
        settled_at = _utc(settlement["settled_at"], "Settlement time")
        if renewal := renewals_by_cohort.get(number):
            value = renewal["value"]
            _require(value["settled_head_settlement_sha256"] == digest(settlement_raw)
                     and value["old_route_sha256"] == current_route_sha256
                     and value["old_operational_source_manifest"]["files"][_OPERATIONAL_FILES[-1]] == effective_source_sha256
                     and _utc(value["reviewed_at"], "Operational renewal review time") >= settled_at,
                     "Operational renewal boundary differs")
            _verify_renewal_prefix(root, renewal)
            current_route_sha256 = value["new_route_sha256"]
            current_source_sha256 = renewal["new_source"]["files"][_OPERATIONAL_FILES[-1]]
            current_renewal_sha256 = renewal["sha256"]
            current_operational_manifest = renewal["new_source"]
            current_source_manifest = renewal["new_source"]
        else:
            current_source_sha256 = effective_source_sha256
        previous_settlement, previous_settled = digest(settlement_raw), settled_at
    _require(previous_settlement == expected_settlement_sha256 and len(contacts) == sum(map(len, geometry.groups[:through_cohort])) and len(request_ids) == len(session_ids) == len(contacts), "Ledger closing settlement differs")
    if renewals and pending_recovery is None:
        _source_manifest(current_source_manifest or renewals[-1]["value"]["new_operational_source_manifest"],
                         "Latest operational", require_current=True)
    after_files, after_directories = _snapshot(root); _require(files == after_files and directories == after_directories, "Ledger changed during verification")
    result = {"evidence_class": "provider_free_baseline_ledger_consistency", "native_admission": False,
              "execution_authority": False, "contacts": contacts, "routes": routes,
              "authorizations": authorizations, "head": {"cohort_number": through_cohort,
              "settlement_sha256": previous_settlement}}
    if renewals:
        result.update({"epochs": epochs, "renewals": renewals})
    if pending_recovery is not None:
        result["precontact_recovery"] = pending_recovery
    return result
