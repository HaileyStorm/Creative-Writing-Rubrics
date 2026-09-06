"""Read-only verification for reviewed Dryad qualification cohorts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


GENESIS_SETTLEMENT_SHA256 = "0" * 64
REVIEWER_TASK = "019ff75c-e610-7581-bacc-33ee869d521a"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PASS_FIELDS = {"pass_id", "batch_size", "source_sha256"}
_REQUEST_FIELDS = {"ordinal", "pass_id", "prompt_sha256", "schema_sha256"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _integer(value: Any, label: str) -> int:
    _require(type(value) is int, f"{label} must be an integer")
    return value


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(isinstance(key, str) and key not in result, "JSON object has duplicate keys")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"JSON constant is not permitted: {value}")


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object_pairs, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _assert_schema(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    _require(set(value) == expected, f"{label} schema differs")
    _require(_integer(value.get("schema_version"), f"{label} schema version") == 1, f"{label} schema version differs")


def _assert_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    _require(set(value) == expected, f"{label} schema differs")


def _parse_utc(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and (value.endswith("Z") or value.endswith("+00:00")), f"{label} must use a zero offset")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} is not an ISO timestamp") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), f"{label} must use a zero offset")
    return parsed.astimezone(timezone.utc)


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _regular_tree(root: Path, label: str) -> tuple[dict[str, str], frozenset[str]]:
    try:
        root_info = root.lstat()
    except FileNotFoundError as error:
        raise ValueError(f"{label} is missing") from error
    _require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode) and not _is_reparse(root_info), f"{label} must be a plain directory")
    files: dict[str, str] = {}
    directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            info = entry.stat(follow_symlinks=False)
            relative = Path(entry.path).relative_to(root).as_posix()
            _require(not stat.S_ISLNK(info.st_mode) and not _is_reparse(info), f"{label} contains a link or reparse point")
            if stat.S_ISDIR(info.st_mode):
                directories.add(relative)
                pending.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                files[relative] = _digest(Path(entry.path).read_bytes())
            else:
                raise ValueError(f"{label} contains a non-regular entry")
    return files, frozenset(directories)


def _ledger_snapshot(execution_root: Path) -> tuple[dict[str, str], frozenset[str]]:
    root = Path(execution_root)
    for ancestor in Path(os.path.abspath(root)).parents:
        info = ancestor.lstat()
        _require(not stat.S_ISLNK(info.st_mode) and not _is_reparse(info), "Execution ancestry contains a link")
    try:
        root_info = root.lstat()
    except FileNotFoundError as error:
        raise ValueError("Execution root is missing") from error
    _require(stat.S_ISDIR(root_info.st_mode) and not stat.S_ISLNK(root_info.st_mode) and not _is_reparse(root_info), "Execution root must be a plain directory")
    files: dict[str, str] = {}
    directories: set[str] = set()
    for name in ("cohorts", "contacts"):
        child_files, child_directories = _regular_tree(root / name, name)
        files.update({f"{name}/{relative}": digest for relative, digest in child_files.items()})
        directories.update({f"{name}/{relative}" for relative in child_directories})
    return files, frozenset(directories)


def _read_ledger_file(root: Path, relative: str, snapshot: Mapping[str, str]) -> bytes:
    _require(relative in snapshot, f"Ledger file is missing: {relative}")
    raw = (root / relative).read_bytes()
    _require(_digest(raw) == snapshot[relative], f"Ledger file changed during read: {relative}")
    return raw


def _plan_rows(plan: Mapping[str, Any]) -> tuple[dict[int, dict[str, Any]], dict[str, dict[str, Any]]]:
    _require(isinstance(plan, Mapping), "Plan must be an object")
    requests, passes = plan.get("requests"), plan.get("passes")
    _require(isinstance(requests, list) and isinstance(passes, list), "Plan request/pass arrays are missing")
    _require(len(requests) == 261 and len(passes) == 18, "Qualification plan geometry differs")
    pass_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(passes, start=1):
        _require(isinstance(item, dict) and _PASS_FIELDS <= set(item), f"Plan pass {index} is malformed")
        pass_id, batch_size, source_sha256 = item["pass_id"], item["batch_size"], item["source_sha256"]
        _require(isinstance(pass_id, str) and pass_id and pass_id not in pass_by_id, "Plan pass identities differ")
        _require(type(batch_size) is int and batch_size in (8, 32), "Plan batch size differs")
        _require(_is_hash(source_sha256), "Plan source hash differs")
        pass_by_id[pass_id] = item
    _require(len(pass_by_id) == 18, "Plan must contain 18 unique pass IDs")
    request_by_ordinal: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(requests, start=1):
        _require(isinstance(item, dict) and _REQUEST_FIELDS <= set(item), f"Plan request {index} is malformed")
        ordinal = _integer(item["ordinal"], "Plan request ordinal")
        _require(ordinal not in request_by_ordinal and item["pass_id"] in pass_by_id, "Plan request identity differs")
        _require(isinstance(item["pass_id"], str) and _is_hash(item["prompt_sha256"]) and _is_hash(item["schema_sha256"]), "Plan request binding differs")
        request_by_ordinal[ordinal] = item
    _require(set(request_by_ordinal) == set(range(1, 262)), "Plan request ordinals must be contiguous 1..261")
    return request_by_ordinal, pass_by_id


def cohort_groups(plan: Mapping[str, Any]) -> list[tuple[int, ...]]:
    """Return the exact reviewed-cohort partition for the pinned qualification plan."""
    requests, passes = _plan_rows(plan)
    groups: list[tuple[int, ...]] = []
    current: list[int] = []
    current_size: int | None = None
    for ordinal in range(1, 262):
        batch_size = passes[requests[ordinal]["pass_id"]]["batch_size"]
        if current and (len(current) == 10 or batch_size != current_size):
            groups.append(tuple(current))
            current = []
        current.append(ordinal)
        current_size = batch_size
    if current:
        groups.append(tuple(current))
    _require(len(groups) == 27 and [len(group) for group in groups] == [10] * 20 + [7] + [10] * 5 + [4], "Qualification cohort partition differs")
    _require(tuple(ordinal for group in groups for ordinal in group) == tuple(range(1, 262)), "Qualification cohorts are not contiguous")
    return groups


def _review_window(review: Mapping[str, Any], prepared_sha256: str, reviewer_task: str) -> tuple[datetime, datetime]:
    _assert_schema(review, {"schema_version", "reviewer_task", "decision", "prepared_sha256", "reviewed_at", "expires_at"}, "Review")
    _require(review["reviewer_task"] == reviewer_task and review["decision"] == "approved_cohort", "Review approval differs")
    _require(review["prepared_sha256"] == prepared_sha256, "Review prepared binding differs")
    reviewed_at, expires_at = _parse_utc(review["reviewed_at"], "Review time"), _parse_utc(review["expires_at"], "Review expiry")
    _require(reviewed_at < expires_at <= reviewed_at + timedelta(minutes=15), "Review window differs")
    return reviewed_at, expires_at


def verify_ledger(
    execution_root: Path,
    plan_raw: bytes,
    expected_plan_sha256: str,
    expected_final_settlement_sha256: str,
) -> dict[str, Any]:
    """Verify all review, routing, and contact bindings without contacting a provider."""
    _require(_is_hash(expected_plan_sha256) and _is_hash(expected_final_settlement_sha256), "Expected ledger hashes differ")
    _require(isinstance(plan_raw, bytes) and _digest(plan_raw) == expected_plan_sha256, "Exact plan hash differs")
    plan = _json_object(plan_raw, "Plan")
    groups = cohort_groups(plan)
    requests, passes = _plan_rows(plan)
    root = Path(execution_root)
    before_files, before_directories = _ledger_snapshot(root)
    expected_files: set[str] = set()
    expected_directories = {f"cohorts/{number:04d}" for number in range(1, len(groups) + 1)}
    for number in range(1, len(groups) + 1):
        prefix = f"cohorts/{number:04d}"
        expected_files.update(f"{prefix}/{name}" for name in ("prepared.json", "review.json", "route.json", "settlement.json"))
    expected_files.update(f"contacts/request-{ordinal:04d}.json" for ordinal in range(1, 262))
    _require(set(before_files) == expected_files and before_directories == expected_directories, "Ledger inventory differs")

    routes: dict[str, dict[str, Any]] = {}
    contacts: dict[int, dict[str, Any]] = {}
    native_request_ids: set[str] = set()
    native_session_ids: set[str] = set()
    previous_settlement = GENESIS_SETTLEMENT_SHA256
    previous_settled_at = None

    for cohort_number, ordinals in enumerate(groups, start=1):
        prefix = f"cohorts/{cohort_number:04d}"
        prepared_raw = _read_ledger_file(root, f"{prefix}/prepared.json", before_files)
        review_raw = _read_ledger_file(root, f"{prefix}/review.json", before_files)
        route_raw = _read_ledger_file(root, f"{prefix}/route.json", before_files)
        settlement_raw = _read_ledger_file(root, f"{prefix}/settlement.json", before_files)
        prepared, review = _json_object(prepared_raw, "Prepared record"), _json_object(review_raw, "Review record")
        route, settlement = _json_object(route_raw, "Route snapshot"), _json_object(settlement_raw, "Settlement record")
        prepared_sha256, review_sha256 = _digest(prepared_raw), _digest(review_raw)
        route_sha256 = _digest(_canonical(route))
        _assert_schema(prepared, {"schema_version", "cohort_number", "plan_sha256", "previous_settlement_sha256", "request_ordinals", "route_sha256"}, "Prepared record")
        _require(_integer(prepared["cohort_number"], "Prepared cohort number") == cohort_number, "Prepared cohort number differs")
        _require(prepared["plan_sha256"] == expected_plan_sha256 and prepared["previous_settlement_sha256"] == previous_settlement, "Prepared chain binding differs")
        _require(isinstance(prepared["request_ordinals"], list) and all(type(value) is int for value in prepared["request_ordinals"]), "Prepared request ordinals differ")
        _require(tuple(prepared["request_ordinals"]) == ordinals and prepared["route_sha256"] == route_sha256, "Prepared cohort binding differs")
        reviewed_at, expires_at = _review_window(review, prepared_sha256, REVIEWER_TASK)
        _require(previous_settled_at is None or reviewed_at >= previous_settled_at, "Review precedes previous settlement")
        _require(route_sha256 not in routes or routes[route_sha256] == route, "Route hash collision differs")
        routes[route_sha256] = route

        _assert_schema(settlement, {"schema_version", "cohort_number", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "previous_settlement_sha256", "settled_at", "contacts"}, "Settlement record")
        settled_at = _parse_utc(settlement["settled_at"], "Settlement time")
        _require(_integer(settlement["cohort_number"], "Settlement cohort number") == cohort_number, "Settlement cohort number differs")
        _require(settlement["plan_sha256"] == expected_plan_sha256 and settlement["prepared_sha256"] == prepared_sha256 and settlement["review_sha256"] == review_sha256, "Settlement review binding differs")
        _require(settlement["route_sha256"] == route_sha256 and settlement["previous_settlement_sha256"] == previous_settlement, "Settlement chain binding differs")
        settlement_contacts = settlement["contacts"]
        _require(isinstance(settlement_contacts, list) and len(settlement_contacts) == len(ordinals), "Settlement contacts differ")
        _require([entry.get("ordinal") if isinstance(entry, dict) else None for entry in settlement_contacts] == list(ordinals), "Settlement contact order differs")
        for ordinal, settlement_contact in zip(ordinals, settlement_contacts, strict=True):
            _require(isinstance(settlement_contact, dict), "Settlement contact is malformed")
            _assert_keys(settlement_contact, {"ordinal", "contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash"}, "Settlement contact")
            _require(_integer(settlement_contact["ordinal"], "Settlement contact ordinal") == ordinal, "Settlement contact ordinal differs")
            _require(all(_is_hash(settlement_contact[field]) for field in ("contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash")), "Settlement contact hash differs")
            _require(settlement_contact["request_id_hash"] not in native_request_ids and settlement_contact["session_id_hash"] not in native_session_ids, "Native identity is duplicated")
            native_request_ids.add(settlement_contact["request_id_hash"])
            native_session_ids.add(settlement_contact["session_id_hash"])
            contact_raw = _read_ledger_file(root, f"contacts/request-{ordinal:04d}.json", before_files)
            contact = _json_object(contact_raw, "Contact record")
            _assert_schema(contact, {"schema_version", "cohort_number", "ordinal", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "prompt_sha256", "schema_sha256", "admitted_at"}, "Contact record")
            _require(_digest(contact_raw) == settlement_contact["contact_sha256"], "Settlement contact hash differs")
            request, pass_record = requests[ordinal], passes[requests[ordinal]["pass_id"]]
            _require(_integer(contact["cohort_number"], "Contact cohort number") == cohort_number and _integer(contact["ordinal"], "Contact ordinal") == ordinal, "Contact identity differs")
            _require(contact["plan_sha256"] == expected_plan_sha256 and contact["prepared_sha256"] == prepared_sha256 and contact["review_sha256"] == review_sha256 and contact["route_sha256"] == route_sha256, "Contact authorization binding differs")
            _require(contact["prompt_sha256"] == request["prompt_sha256"] and contact["schema_sha256"] == request["schema_sha256"], "Contact plan binding differs")
            admitted_at = _parse_utc(contact["admitted_at"], "Contact admission time")
            _require(reviewed_at <= admitted_at <= expires_at, "Contact is outside the review window")
            _require(admitted_at <= settled_at, "Settlement precedes contact admission")
            contacts[ordinal] = {
                "cohort_number": cohort_number,
                "ordinal": ordinal,
                "pass_id": request["pass_id"],
                "source_sha256": pass_record["source_sha256"],
                "prompt_sha256": request["prompt_sha256"],
                "schema_sha256": request["schema_sha256"],
                "route_sha256": route_sha256,
                "contact_sha256": settlement_contact["contact_sha256"],
                "checkpoint_sha256": settlement_contact["checkpoint_sha256"],
                "request_id_hash": settlement_contact["request_id_hash"],
                "session_id_hash": settlement_contact["session_id_hash"],
            }
        previous_settlement = _digest(settlement_raw)
        previous_settled_at = settled_at

    _require(len(contacts) == len(native_request_ids) == len(native_session_ids) == 261, "Ledger contact cardinality differs")
    _require(previous_settlement == expected_final_settlement_sha256, "Ledger closing settlement differs")
    after_files, after_directories = _ledger_snapshot(root)
    _require(before_files == after_files and before_directories == after_directories, "Ledger changed during verification")
    return {
        "routes": routes,
        "contacts": contacts,
        "head": {"cohort_number": len(groups), "settlement_sha256": previous_settlement},
    }
