"""Read-only verification for reviewed Dryad qualification cohorts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


GENESIS_SETTLEMENT_SHA256 = "0" * 64
REVIEWER_TASK = "019ff75c-e610-7581-bacc-33ee869d521a"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PASS_FIELDS = {"pass_id", "batch_size", "source_sha256"}
_REQUEST_FIELDS = {"ordinal", "pass_id", "prompt_sha256", "schema_sha256"}
_CONTINUATION_FIELDS = {"schema_version", "reviewer_task", "decision", "prepared_sha256", "route_sha256", "prior_authorization_sha256", "previous_execution_source_sha256", "execution_source_sha256", "completed_prefix", "reviewed_at", "expires_at"}


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


def _continuation_records(root: Path, prefix: str, snapshot: Mapping[str, str], prepared_sha256: str, route_sha256: str, initial_authorization_sha256: str, initial_execution_source_sha256: str) -> list[dict[str, Any]]:
    """Read the append-only reviewer-authored authorization chain for one cohort."""
    pattern = re.compile(re.escape(prefix) + r"/review-continuations/(\d{4})\.json\Z")
    numbered = []
    for relative in snapshot:
        match = pattern.fullmatch(relative)
        if match:
            numbered.append((int(match.group(1)), relative))
    _require([number for number, _ in sorted(numbered)] == list(range(1, len(numbered) + 1)), "Continuation inventory differs")
    prior_hash, prior_source = initial_authorization_sha256, initial_execution_source_sha256
    records: list[dict[str, Any]] = []
    for _, relative in sorted(numbered):
        raw = _read_ledger_file(root, relative, snapshot)
        value = _json_object(raw, "Continuation record")
        _assert_keys(value, _CONTINUATION_FIELDS, "Continuation record")
        _require(_integer(value["schema_version"], "Continuation schema version") == 1, "Continuation schema version differs")
        _require(value["reviewer_task"] == REVIEWER_TASK and value["decision"] == "approved_continuation", "Continuation approval differs")
        _require(value["prepared_sha256"] == prepared_sha256 and value["route_sha256"] == route_sha256, "Continuation cohort binding differs")
        _require(value["prior_authorization_sha256"] == prior_hash and value["previous_execution_source_sha256"] == prior_source and _is_hash(value["execution_source_sha256"]), "Continuation source chain differs")
        _review_window({"schema_version": 1, "reviewer_task": value["reviewer_task"], "decision": "approved_cohort", "prepared_sha256": value["prepared_sha256"], "reviewed_at": value["reviewed_at"], "expires_at": value["expires_at"]}, prepared_sha256, REVIEWER_TASK)
        prefix_value = value["completed_prefix"]
        _assert_keys(prefix_value, {"ordinals", "contacts", "run_files", "run_tree_sha256"}, "Continuation prefix") if isinstance(prefix_value, Mapping) else _require(False, "Continuation prefix differs")
        _require(isinstance(prefix_value["ordinals"], list) and prefix_value["ordinals"] and all(type(item) is int for item in prefix_value["ordinals"]) and prefix_value["ordinals"] == list(range(prefix_value["ordinals"][0], prefix_value["ordinals"][0] + len(prefix_value["ordinals"]))), "Continuation prefix ordinals differ")
        _require(isinstance(prefix_value["contacts"], list) and len(prefix_value["contacts"]) == len(prefix_value["ordinals"]) and isinstance(prefix_value["run_files"], dict) and prefix_value["run_files"] and all(isinstance(path, str) and _is_hash(digest) for path, digest in prefix_value["run_files"].items()) and _is_hash(prefix_value["run_tree_sha256"]) and _digest(_canonical(prefix_value["run_files"])) == prefix_value["run_tree_sha256"], "Continuation prefix differs")
        for ordinal, contact in zip(prefix_value["ordinals"], prefix_value["contacts"], strict=True):
            _require(isinstance(contact, Mapping), "Continuation prefix contact differs")
            _assert_keys(contact, {"ordinal", "contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash"}, "Continuation prefix contact")
            _require(_integer(contact["ordinal"], "Continuation prefix ordinal") == ordinal and all(_is_hash(contact[field]) for field in ("contact_sha256", "checkpoint_sha256", "request_id_hash", "session_id_hash")), "Continuation prefix contact differs")
        prior_hash, prior_source = _digest(raw), value["execution_source_sha256"]
        records.append({"sha256": prior_hash, "source_sha256": prior_source, "value": value, "raw": raw})
    return records


def continuation_chain(execution_root: Path, cohort_number: int, prepared_raw: bytes, route: Mapping[str, Any], review_raw: bytes) -> list[dict[str, Any]]:
    """Return a verified continuation chain for a prepared cohort without accepting it as an approval."""
    root = Path(execution_root)
    files, _ = _ledger_snapshot(root)
    prepared = _json_object(prepared_raw, "Prepared record")
    _require(_is_hash(prepared.get("execution_source_sha256")), "Prepared execution source differs")
    return _continuation_records(root, f"cohorts/{cohort_number:04d}", files, _digest(prepared_raw), _digest(_canonical(dict(route))), _digest(review_raw), prepared["execution_source_sha256"])


def _pending_paths(value: frozenset[str]) -> frozenset[str]:
    _require(isinstance(value, frozenset) and all(type(item) is str for item in value), "Pending paths differ")
    for item in value:
        path = PurePosixPath(item)
        _require(path.parts and not path.is_absolute() and path.as_posix() == item, "Pending path differs")
        _require(all(part not in (".", "..") for part in path.parts) and path.parts[0] in {"cohorts", "contacts"}, "Pending path escapes ledger")
    return value


def _ledger_directories(files: set[str]) -> frozenset[str]:
    directories: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while len(parent.parts) > 1:
            directories.add(parent.as_posix())
            parent = parent.parent
    return frozenset(directories)


def _verify_prefix(
    execution_root: Path,
    plan_raw: bytes,
    expected_plan_sha256: str,
    expected_settlement_sha256: str,
    through_cohort: int,
    allowed_pending_paths: frozenset[str],
) -> dict[str, Any]:
    _require(_is_hash(expected_plan_sha256) and _is_hash(expected_settlement_sha256), "Expected ledger hashes differ")
    _require(type(through_cohort) is int and 0 <= through_cohort <= 27, "Prefix cohort differs")
    pending_paths = _pending_paths(allowed_pending_paths)
    _require(isinstance(plan_raw, bytes) and _digest(plan_raw) == expected_plan_sha256, "Exact plan hash differs")
    plan = _json_object(plan_raw, "Plan")
    groups = cohort_groups(plan)
    requests, passes = _plan_rows(plan)
    root = Path(execution_root)
    before_files, before_directories = _ledger_snapshot(root)
    expected_files: set[str] = set()
    for number in range(1, through_cohort + 1):
        prefix = f"cohorts/{number:04d}"
        expected_files.update(f"{prefix}/{name}" for name in ("prepared.json", "review.json", "route.json", "settlement.json"))
    expected_files.update(f"contacts/request-{ordinal:04d}.json" for group in groups[:through_cohort] for ordinal in group)
    continuation_pattern = re.compile(r"cohorts/(\d{4})/review-continuations/(\d{4})\.json\Z")
    continuation_files: dict[int, list[tuple[int, str]]] = {}
    for relative in before_files:
        match = continuation_pattern.fullmatch(relative)
        if match:
            cohort_number, number = (int(value) for value in match.groups())
            _require(1 <= cohort_number <= 27 and (cohort_number <= through_cohort or relative in pending_paths), "Continuation inventory differs")
            if cohort_number <= through_cohort:
                continuation_files.setdefault(cohort_number, []).append((number, relative))
                expected_files.add(relative)
    for values in continuation_files.values():
        _require([number for number, _ in sorted(values)] == list(range(1, len(values) + 1)), "Continuation inventory differs")
    _require(expected_files.isdisjoint(pending_paths), "Pending paths overlap settled ledger")
    expected_inventory = expected_files | set(pending_paths)
    _require(set(before_files) == expected_inventory and before_directories == _ledger_directories(expected_inventory), "Ledger inventory differs")

    routes: dict[str, dict[str, Any]] = {}
    contacts: dict[int, dict[str, Any]] = {}
    native_request_ids: set[str] = set()
    native_session_ids: set[str] = set()
    all_authorizations: list[dict[str, str]] = []
    previous_settlement = GENESIS_SETTLEMENT_SHA256
    previous_settled_at = None
    previous_execution_source: str | None = None

    for cohort_number, ordinals in enumerate(groups[:through_cohort], start=1):
        prefix = f"cohorts/{cohort_number:04d}"
        prepared_raw = _read_ledger_file(root, f"{prefix}/prepared.json", before_files)
        review_raw = _read_ledger_file(root, f"{prefix}/review.json", before_files)
        route_raw = _read_ledger_file(root, f"{prefix}/route.json", before_files)
        settlement_raw = _read_ledger_file(root, f"{prefix}/settlement.json", before_files)
        prepared, review = _json_object(prepared_raw, "Prepared record"), _json_object(review_raw, "Review record")
        route, settlement = _json_object(route_raw, "Route snapshot"), _json_object(settlement_raw, "Settlement record")
        prepared_sha256, review_sha256 = _digest(prepared_raw), _digest(review_raw)
        route_sha256 = _digest(_canonical(route))
        _assert_schema(prepared, {"schema_version", "cohort_number", "plan_sha256", "previous_settlement_sha256", "request_ordinals", "route_sha256", "execution_source_sha256"}, "Prepared record")
        _require(_is_hash(prepared["execution_source_sha256"]), "Prepared execution source differs")
        _require(previous_execution_source is None or prepared["execution_source_sha256"] == previous_execution_source, "Prepared executor transition differs")
        _require(_integer(prepared["cohort_number"], "Prepared cohort number") == cohort_number, "Prepared cohort number differs")
        _require(prepared["plan_sha256"] == expected_plan_sha256 and prepared["previous_settlement_sha256"] == previous_settlement, "Prepared chain binding differs")
        _require(isinstance(prepared["request_ordinals"], list) and all(type(value) is int for value in prepared["request_ordinals"]), "Prepared request ordinals differ")
        _require(tuple(prepared["request_ordinals"]) == ordinals and prepared["route_sha256"] == route_sha256, "Prepared cohort binding differs")
        reviewed_at, expires_at = _review_window(review, prepared_sha256, REVIEWER_TASK)
        _require(previous_settled_at is None or reviewed_at >= previous_settled_at, "Review precedes previous settlement")
        _require(route_sha256 not in routes or routes[route_sha256] == route, "Route hash collision differs")
        routes[route_sha256] = route
        continuations = _continuation_records(root, prefix, before_files, prepared_sha256, route_sha256, review_sha256, prepared["execution_source_sha256"])
        authorizations = [{"sha256": review_sha256, "source_sha256": prepared["execution_source_sha256"]}, *[{"sha256": item["sha256"], "source_sha256": item["source_sha256"]} for item in continuations]]
        all_authorizations.extend(authorizations)

        settlement_version = _integer(settlement.get("schema_version"), "Settlement schema version")
        expected_settlement_fields = {"schema_version", "cohort_number", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256", "previous_settlement_sha256", "settled_at", "contacts"}
        if settlement_version == 1:
            _assert_keys(settlement, expected_settlement_fields, "Settlement record")
            _require(not continuations, "Legacy settlement cannot retain continuations")
        elif settlement_version == 2:
            _assert_keys(settlement, expected_settlement_fields | {"authorization_chain"}, "Settlement record")
            chain = settlement["authorization_chain"]
            _require(isinstance(chain, list) and len(chain) == len(authorizations), "Settlement authorization chain differs")
            for expected, observed in zip(authorizations, chain, strict=True):
                _require(isinstance(observed, Mapping), "Settlement authorization differs")
                _assert_keys(observed, {"authorization_sha256", "execution_source_sha256", "ordinals"}, "Settlement authorization")
                _require(observed["authorization_sha256"] == expected["sha256"] and observed["execution_source_sha256"] == expected["source_sha256"] and isinstance(observed["ordinals"], list) and observed["ordinals"] and all(type(item) is int for item in observed["ordinals"]), "Settlement authorization differs")
        else:
            raise ValueError("Settlement schema version differs")
        settled_at = _parse_utc(settlement["settled_at"], "Settlement time")
        _require(_integer(settlement["cohort_number"], "Settlement cohort number") == cohort_number, "Settlement cohort number differs")
        _require(settlement["plan_sha256"] == expected_plan_sha256 and settlement["prepared_sha256"] == prepared_sha256 and settlement["review_sha256"] == review_sha256, "Settlement review binding differs")
        _require(settlement["route_sha256"] == route_sha256 and settlement["previous_settlement_sha256"] == previous_settlement, "Settlement chain binding differs")
        settlement_contacts = settlement["contacts"]
        _require(isinstance(settlement_contacts, list) and len(settlement_contacts) == len(ordinals), "Settlement contacts differ")
        _require([entry.get("ordinal") if isinstance(entry, dict) else None for entry in settlement_contacts] == list(ordinals), "Settlement contact order differs")
        authorization_by_hash = {item["sha256"]: item["source_sha256"] for item in authorizations}
        authorization_windows = {review_sha256: (reviewed_at, expires_at)}
        for continuation in continuations:
            value = continuation["value"]
            window = _review_window({"schema_version": 1, "reviewer_task": value["reviewer_task"], "decision": "approved_cohort", "prepared_sha256": prepared_sha256, "reviewed_at": value["reviewed_at"], "expires_at": value["expires_at"]}, prepared_sha256, REVIEWER_TASK)
            _require(window[0] >= next(reversed(authorization_windows.values()))[0], "Continuation review order differs")
            authorization_windows[continuation["sha256"]] = window
        used_authorizations: dict[str, list[int]] = {item["sha256"]: [] for item in authorizations}
        contact_times: dict[int, datetime] = {}
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
            _require(contact["plan_sha256"] == expected_plan_sha256 and contact["prepared_sha256"] == prepared_sha256 and contact["route_sha256"] == route_sha256, "Contact authorization binding differs")
            if settlement_version == 1:
                _require(contact["review_sha256"] == review_sha256, "Contact authorization binding differs")
            else:
                _require(contact["review_sha256"] in authorization_by_hash, "Contact authorization binding differs")
                used_authorizations[contact["review_sha256"]].append(ordinal)
            _require(contact["prompt_sha256"] == request["prompt_sha256"] and contact["schema_sha256"] == request["schema_sha256"], "Contact plan binding differs")
            admitted_at = _parse_utc(contact["admitted_at"], "Contact admission time")
            contact_window = authorization_windows[contact["review_sha256"]]
            _require(contact_window[0] <= admitted_at <= contact_window[1], "Contact is outside the review window")
            _require(admitted_at <= settled_at, "Settlement precedes contact admission")
            contact_times[ordinal] = admitted_at
            contacts[ordinal] = {
                "cohort_number": cohort_number,
                "execution_source_sha256": authorization_by_hash.get(contact["review_sha256"], prepared["execution_source_sha256"]),
                "authorization_sha256": contact["review_sha256"],
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
        if settlement_version == 2:
            ordered = [ordinal for item in authorizations for ordinal in used_authorizations[item["sha256"]]]
            _require(ordered == list(ordinals) and all(used_authorizations[item["sha256"]] for item in authorizations), "Settlement authorization order differs")
            for authorization in settlement["authorization_chain"]:
                _require(authorization["ordinals"] == used_authorizations[authorization["authorization_sha256"]], "Settlement authorization ordinals differ")
            completed = 0
            for index, continuation in enumerate(continuations):
                completed += len(used_authorizations[authorizations[index]["sha256"]])
                prefix_value = continuation["value"]["completed_prefix"]
                prefix_ordinals = prefix_value["ordinals"]
                _require(prefix_ordinals == list(ordinals[:completed]) and 0 < completed < len(ordinals), "Continuation prefix ordinals differ")
                _require(authorization_windows[continuation["sha256"]][0] >= max(contact_times[ordinal] for ordinal in prefix_ordinals), "Continuation review precedes completed prefix")
                for expected_contact, actual in zip(settlement_contacts[:len(prefix_ordinals)], prefix_value["contacts"], strict=True):
                    _require(actual == expected_contact, "Continuation prefix contact differs")
        previous_settlement = _digest(settlement_raw)
        previous_settled_at = settled_at
        previous_execution_source = authorizations[-1]["source_sha256"]

    expected_contacts = sum(len(group) for group in groups[:through_cohort])
    _require(len(contacts) == len(native_request_ids) == len(native_session_ids) == expected_contacts, "Ledger contact cardinality differs")
    _require(previous_settlement == expected_settlement_sha256, "Ledger closing settlement differs")
    after_files, after_directories = _ledger_snapshot(root)
    _require(before_files == after_files and before_directories == after_directories, "Ledger changed during verification")
    return {
        "routes": routes,
        "contacts": contacts,
        "head": {"cohort_number": through_cohort, "settlement_sha256": previous_settlement},
        "authorization_chain": all_authorizations,
    }


def verify_prefix(
    execution_root: Path,
    plan_raw: bytes,
    expected_plan_sha256: str,
    expected_settlement_sha256: str,
    through_cohort: int,
    allowed_pending_paths: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Verify a contiguous settled ledger prefix without contacting a provider."""
    return _verify_prefix(execution_root, plan_raw, expected_plan_sha256, expected_settlement_sha256, through_cohort, allowed_pending_paths)


def verify_ledger(
    execution_root: Path,
    plan_raw: bytes,
    expected_plan_sha256: str,
    expected_final_settlement_sha256: str,
) -> dict[str, Any]:
    """Verify the complete closed ledger without contacting a provider."""
    return _verify_prefix(execution_root, plan_raw, expected_plan_sha256, expected_final_settlement_sha256, 27, frozenset())
