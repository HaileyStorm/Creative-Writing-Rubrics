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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any

GENESIS_SETTLEMENT_SHA256 = "0" * 64
_HASH = re.compile(r"[0-9a-f]{64}\Z")


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
            _require(isinstance(pass_id, str) and isinstance(value, Mapping) and value.get("pass_id") == pass_id and _hash(value.get("source_sha256")) and isinstance(value.get("logical_sample_id"), str) and value["logical_sample_id"], "Ledger pass binding differs")


def _review(raw: bytes, prepared_sha256: str, reviewer_task: str) -> tuple[dict[str, Any], datetime, datetime]:
    value = _json(raw, "Review record")
    _keys(value, {"schema_version", "reviewer_task", "decision", "prepared_sha256", "reviewed_at", "expires_at"}, "Review record", version=1)
    _require(value["reviewer_task"] == reviewer_task and value["decision"] == "approved_cohort" and value["prepared_sha256"] == prepared_sha256, "Review approval differs")
    start, end = _utc(value["reviewed_at"], "Review time"), _utc(value["expires_at"], "Review expiry")
    _require(start < end <= start + timedelta(minutes=15), "Review window differs")
    return value, start, end


def _continuations(root: Path, prefix: str, snapshot: Mapping[str, str], prepared_sha256: str, route_sha256: str, review_sha256: str, source_sha256: str, reviewer_task: str) -> list[dict[str, Any]]:
    pattern = re.compile(re.escape(prefix) + r"/review-continuations/(\d{4})\.json\Z")
    found = sorted((int(match.group(1)), relative) for relative in snapshot if (match := pattern.fullmatch(relative)))
    _require([number for number, _ in found] == list(range(1, len(found) + 1)), "Continuation inventory differs")
    prior_hash, prior_source = review_sha256, source_sha256
    result: list[dict[str, Any]] = []
    for _, relative in found:
        raw = _read(root, relative, snapshot); value = _json(raw, "Continuation record")
        fields = {"schema_version", "reviewer_task", "decision", "prepared_sha256", "route_sha256", "prior_authorization_sha256", "previous_execution_source_sha256", "execution_source_sha256", "completed_prefix", "reviewed_at", "expires_at"}
        _keys(value, fields, "Continuation record", version=1)
        _require(value["reviewer_task"] == reviewer_task and value["decision"] == "approved_continuation" and value["prepared_sha256"] == prepared_sha256 and value["route_sha256"] == route_sha256 and value["prior_authorization_sha256"] == prior_hash and value["previous_execution_source_sha256"] == prior_source and _hash(value["execution_source_sha256"]), "Continuation binding differs")
        _, start, end = _review(canonical({"schema_version": 1, "reviewer_task": value["reviewer_task"], "decision": "approved_cohort", "prepared_sha256": value["prepared_sha256"], "reviewed_at": value["reviewed_at"], "expires_at": value["expires_at"]}), prepared_sha256, reviewer_task)
        prefix_value = value["completed_prefix"]
        _require(isinstance(prefix_value, Mapping) and set(prefix_value) == {"ordinals", "contacts", "run_files", "run_tree_sha256"} and isinstance(prefix_value["ordinals"], list) and prefix_value["ordinals"] and all(type(item) is int for item in prefix_value["ordinals"]) and prefix_value["ordinals"] == list(range(prefix_value["ordinals"][0], prefix_value["ordinals"][0] + len(prefix_value["ordinals"]))) and isinstance(prefix_value["contacts"], list) and len(prefix_value["contacts"]) == len(prefix_value["ordinals"]) and isinstance(prefix_value["run_files"], dict) and prefix_value["run_files"] and all(isinstance(path, str) and _hash(value) for path, value in prefix_value["run_files"].items()) and _hash(prefix_value["run_tree_sha256"]) and digest(canonical(prefix_value["run_files"])) == prefix_value["run_tree_sha256"], "Continuation prefix differs")
        for ordinal, contact in zip(prefix_value["ordinals"], prefix_value["contacts"], strict=True):
            _require(isinstance(contact, Mapping) and set(contact) == {"ordinal", "contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash"} and contact.get("ordinal") == ordinal and all(_hash(contact.get(field)) for field in ("contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash")), "Continuation prefix contact differs")
        prior_hash, prior_source = digest(raw), value["execution_source_sha256"]
        result.append({"sha256": prior_hash, "source_sha256": prior_source, "value": value, "start": start, "end": end})
    return result


def verify_prefix(execution_root: Path, geometry: LedgerGeometry, expected_settlement_sha256: str, through_cohort: int, *, expected_route_sha256: str, expected_execution_source_sha256: str, reviewer_task: str, allowed_pending_paths: frozenset[str] = frozenset()) -> dict[str, Any]:
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
    _require(expected_files.isdisjoint(pending) and set(files) == expected_files | set(pending) and directories == _directories(expected_files | set(pending)), "Ledger inventory differs")
    previous_settlement, previous_source, previous_settled = GENESIS_SETTLEMENT_SHA256, None, None
    contacts: dict[int, dict[str, Any]] = {}; request_ids: set[str] = set(); session_ids: set[str] = set(); routes: dict[str, dict[str, Any]] = {}
    authorizations: dict[str, dict[str, Any]] = {}
    for number, ordinals in enumerate(geometry.groups[:through_cohort], start=1):
        prefix = f"cohorts/{number:04d}"; prepared_raw = _read(root, f"{prefix}/prepared.json", files); review_raw = _read(root, f"{prefix}/review.json", files); route_raw = _read(root, f"{prefix}/route.json", files); settlement_raw = _read(root, f"{prefix}/settlement.json", files)
        prepared, route, settlement = _json(prepared_raw, "Prepared record"), _json(route_raw, "Route snapshot"), _json(settlement_raw, "Settlement record")
        prepared_sha, review_sha, route_sha = digest(prepared_raw), digest(review_raw), digest(canonical(route))
        _keys(prepared, {"schema_version", "cohort_number", "plan_sha256", "previous_settlement_sha256", "request_ordinals", "route_sha256", "execution_source_sha256"}, "Prepared record", version=1)
        _require(prepared["cohort_number"] == number and prepared["plan_sha256"] == geometry.plan_sha256 and prepared["previous_settlement_sha256"] == previous_settlement and tuple(prepared["request_ordinals"]) == ordinals and prepared["route_sha256"] == route_sha == expected_route_sha256 and prepared["execution_source_sha256"] == expected_execution_source_sha256 and (previous_source is None or previous_source == expected_execution_source_sha256), "Prepared binding differs")
        _, reviewed_at, expires_at = _review(review_raw, prepared_sha, reviewer_task); _require(previous_settled is None or reviewed_at >= previous_settled, "Review precedes previous settlement")
        _require(route_sha not in routes or routes[route_sha] == route, "Route hash collision differs"); routes[route_sha] = route
        continuations = _continuations(root, prefix, files, prepared_sha, route_sha, review_sha, expected_execution_source_sha256, reviewer_task)
        _require(all(item["source_sha256"] == expected_execution_source_sha256 for item in continuations), "Continuation execution source differs")
        authorization = {review_sha: (expected_execution_source_sha256, reviewed_at, expires_at), **{item["sha256"]: (item["source_sha256"], item["start"], item["end"]) for item in continuations}}
        for authorization_sha, (source_sha, start, end) in authorization.items():
            _require(authorization_sha not in authorizations, "Authorization reused across cohorts")
            authorizations[authorization_sha] = {"execution_source_sha256": source_sha, "reviewed_at": start.isoformat(), "expires_at": end.isoformat(), "cohort_number": number}
        fields = {"schema_version", "cohort_number", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "previous_settlement_sha256", "settled_at", "contacts"}
        version = _integer(settlement.get("schema_version"), "Settlement schema version")
        if version == 1:
            _keys(settlement, fields, "Settlement record", version=1); _require(not continuations, "Legacy settlement cannot retain continuations")
        elif version == 2:
            _keys(settlement, fields | {"authorization_chain"}, "Settlement record", version=2)
            chain = settlement["authorization_chain"]
            _require(isinstance(chain, list) and len(chain) == len(authorization), "Settlement authorization chain differs")
        else:
            raise ValueError("Settlement schema version differs")
        settled_at = _utc(settlement["settled_at"], "Settlement time")
        _require(settlement["cohort_number"] == number and settlement["plan_sha256"] == geometry.plan_sha256 and settlement["prepared_sha256"] == prepared_sha and settlement["review_sha256"] == review_sha and settlement["route_sha256"] == route_sha and settlement["previous_settlement_sha256"] == previous_settlement and isinstance(settlement["contacts"], list) and [item.get("ordinal") if isinstance(item, dict) else None for item in settlement["contacts"]] == list(ordinals), "Settlement binding differs")
        used: dict[str, list[int]] = {key: [] for key in authorization}
        contact_times: dict[int, datetime] = {}
        for ordinal, summary in zip(ordinals, settlement["contacts"], strict=True):
            _keys(summary, {"ordinal", "contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash"}, "Settlement contact")
            _require(all(_hash(summary[field]) for field in ("contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash")) and summary["request_id_hash"] not in request_ids and summary["session_id_hash"] not in session_ids, "Native identity is duplicated")
            request_ids.add(summary["request_id_hash"]); session_ids.add(summary["session_id_hash"])
            raw = _read(root, f"contacts/request-{ordinal:04d}.json", files); contact = _json(raw, "Contact record")
            fields = {"schema_version", "cohort_number", "ordinal", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "prompt_sha256", "schema_sha256", "admitted_at"}
            _keys(contact, fields, "Contact record", version=1); request = geometry.requests[ordinal]; passed = geometry.passes[request["pass_id"]]
            _require(digest(raw) == summary["contact_sha256"] and contact["cohort_number"] == number and contact["ordinal"] == ordinal and contact["plan_sha256"] == geometry.plan_sha256 and contact["prepared_sha256"] == prepared_sha and contact["route_sha256"] == route_sha and contact["review_sha256"] in authorization and contact["prompt_sha256"] == request["prompt_sha256"] and contact["schema_sha256"] == request["schema_sha256"], "Contact binding differs")
            admitted_at = _utc(contact["admitted_at"], "Contact admission time"); source, start, end = authorization[contact["review_sha256"]]
            _require(start <= admitted_at <= end and admitted_at <= settled_at, "Contact is outside its authorization window")
            used[contact["review_sha256"]].append(ordinal); contact_times[ordinal] = admitted_at
            contacts[ordinal] = {"ordinal": ordinal, "pass_id": request["pass_id"], "logical_sample_id": passed["logical_sample_id"], "source_sha256": passed["source_sha256"], "prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"], "route_sha256": route_sha, "execution_source_sha256": source, "authorization_sha256": contact["review_sha256"], **summary}
        if version == 2:
            ordered = [ordinal for authorization_sha in authorization for ordinal in used[authorization_sha]]
            _require(ordered == list(ordinals) and all(used[authorization_sha] for authorization_sha in authorization), "Settlement authorization order differs")
            for expected_sha, record in zip(authorization, settlement["authorization_chain"], strict=True):
                _require(isinstance(record, Mapping) and set(record) == {"authorization_sha256", "execution_source_sha256", "ordinals"} and record.get("authorization_sha256") == expected_sha and record.get("execution_source_sha256") == expected_execution_source_sha256 and record.get("ordinals") == used[expected_sha], "Settlement authorization differs")
            completed = 0
            for index, continuation in enumerate(continuations):
                completed += len(used[list(authorization)[index]])
                prefix_value = continuation["value"]["completed_prefix"]
                prefix_ordinals = prefix_value["ordinals"]
                _require(prefix_ordinals == list(ordinals[:completed]) and 0 < completed < len(ordinals) and continuation["start"] >= max(contact_times[item] for item in prefix_ordinals), "Continuation prefix differs")
                _require(prefix_value["contacts"] == settlement["contacts"][:len(prefix_ordinals)], "Continuation prefix contact differs")
        previous_settlement, previous_source, previous_settled = digest(settlement_raw), expected_execution_source_sha256, settled_at
    _require(previous_settlement == expected_settlement_sha256 and len(contacts) == sum(map(len, geometry.groups[:through_cohort])) and len(request_ids) == len(session_ids) == len(contacts), "Ledger closing settlement differs")
    after_files, after_directories = _snapshot(root); _require(files == after_files and directories == after_directories, "Ledger changed during verification")
    return {"evidence_class": "provider_free_baseline_ledger_consistency", "native_admission": False, "execution_authority": False, "contacts": contacts, "routes": routes, "authorizations": authorizations, "head": {"cohort_number": through_cohort, "settlement_sha256": previous_settlement}}
