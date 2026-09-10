"""Provider-free composition of the immutable Dryad prefix and v5 suffix."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
FIRST_SUFFIX_ORDINAL = 81
LAST_ORDINAL = 5428
PASS_COUNT = 236
QUESTION_COUNT = 178
LOGICAL_REQUEST_COUNT = 5428
RECOVERED_ORDINAL = 70
PREFIX_NATIVE_COUNT = 79
HISTORICAL_EXCLUSION_COUNT = 33
SELECTED_PASS_COUNT = 100
SELECTED_LOGICAL_REQUEST_COUNT = 2300
SELECTED_NATIVE_REQUEST_COUNT = 2299
SELECTED_REMAINING_REQUEST_COUNT = 2220
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _digest(value: Any, label: str) -> str:
    _require(isinstance(value, str) and _HASH.fullmatch(value) is not None, f"{label} must be a lowercase SHA-256")
    return value


def _plain(path: Path | str, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        _require(
            not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
            "Composite path contains a link or reparse point",
        )
    if directory is True:
        _require(absolute.is_dir(), "Composite expected directory")
    if directory is False:
        _require(absolute.is_file(), "Composite expected file")
    return absolute


def _relative(root: Path, value: Any) -> Path:
    _require(isinstance(value, str) and value, "Composite relative path differs")
    relative = Path(value)
    _require(not relative.is_absolute() and all(part not in {"", ".", ".."} for part in relative.parts), "Composite relative path differs")
    path = _plain(root / relative, directory=False)
    _require(path.is_relative_to(root), "Composite path escapes its root")
    return path


def _json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(isinstance(key, str) and key not in result, f"{label} has duplicate keys")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error


def _read(path: Path | str, expected: str, label: str) -> bytes:
    checked = _plain(path, directory=False)
    raw = checked.read_bytes()
    _require(_sha(raw) == _digest(expected, label + " hash") and checked.read_bytes() == raw, f"{label} drifted")
    return raw


def _load_module(path: Path, expected: str, label: str) -> ModuleType:
    raw = _read(path, expected, label)
    name = "_dryad_composite_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - caller supplied hash-pinned source only.
    finally:
        sys.modules.pop(name, None)
    _require(path.read_bytes() == raw, f"{label} changed while loading")
    return module


def _descriptor(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == {"path", "sha256"}, f"{label} descriptor differs")
    path = _plain(value.get("path"), directory=False)
    expected = _digest(value.get("sha256"), label)
    raw = _read(path, expected, label)
    return {"path": str(path), "sha256": expected, "bytes": len(raw)}


def _descriptor_with_bytes(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping) and set(value) == {"path", "sha256", "bytes"}, f"{label} descriptor differs")
    path = _plain(value.get("path"), directory=False)
    expected = _digest(value.get("sha256"), label)
    raw = _read(path, expected, label)
    _require(type(value.get("bytes")) is int and value["bytes"] == len(raw), f"{label} bytes differ")
    return {"path": str(path), "sha256": expected, "bytes": len(raw)}


def _plan(plan_root: Path, expected: str) -> tuple[dict[str, Any], bytes, list[dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    raw = _read(plan_root / "plan.json", expected, "Frozen plan")
    plan = _json(raw, "Frozen plan")
    _require(isinstance(plan, dict) and isinstance(plan.get("passes"), list) and len(plan["passes"]) == PASS_COUNT
             and isinstance(plan.get("requests"), list) and len(plan["requests"]) == LOGICAL_REQUEST_COUNT,
             "Frozen plan geometry differs")
    passes = [dict(item) for item in plan["passes"] if isinstance(item, Mapping)]
    indexed = {item.get("pass_id"): item for item in passes if isinstance(item.get("pass_id"), str)}
    _require(len(passes) == PASS_COUNT and len(indexed) == PASS_COUNT, "Frozen pass inventory differs")
    requests = {item.get("ordinal"): item for item in plan["requests"] if isinstance(item, Mapping) and type(item.get("ordinal")) is int}
    _require(set(requests) == set(range(1, LAST_ORDINAL + 1)), "Frozen request inventory differs")
    runtime = plan.get("runtime")
    question_ids = runtime.get("question_ids") if isinstance(runtime, Mapping) else None
    _require(isinstance(question_ids, list) and len(question_ids) == QUESTION_COUNT
             and all(isinstance(item, str) and item for item in question_ids) and len(set(question_ids)) == QUESTION_COUNT,
             "Frozen criterion inventory differs")
    for index, record in enumerate(passes, start=1):
        grouped = [item for item in requests.values() if item.get("pass_id") == record["pass_id"]]
        grouped.sort(key=lambda item: item["batch_number"])
        _require(len(grouped) == 23 and [item.get("batch_number") for item in grouped] == list(range(1, 24))
                 and [item.get("ordinal") for item in grouped] == list(range((index - 1) * 23 + 1, index * 23 + 1)),
                 "Frozen pass/request geometry differs")
    return plan, raw, passes, indexed, list(question_ids)


def _source(plan_root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    path = _relative(plan_root, record.get("input_path"))
    raw = path.read_bytes()
    _require(_sha(raw) == record.get("source_sha256") and len(raw) == record.get("source_bytes"), "Frozen source differs")
    return {"path": str(path), "sha256": _sha(raw), "bytes": len(raw)}


def _identity_exclusions(descriptor: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    raw = _read(descriptor["path"], descriptor["sha256"], "Historical identity exclusion")
    value = _json(raw, "Historical identity exclusion")
    _require(
        isinstance(value, Mapping) and value.get("schema_version") == 2
        and value.get("evidence_class") == "preserved_predecessor_native_identity_exclusion"
        and value.get("completed_identity_records") == HISTORICAL_EXCLUSION_COUNT
        and isinstance(value.get("records"), list) and len(value["records"]) == HISTORICAL_EXCLUSION_COUNT,
        "Historical identity exclusion schema differs",
    )
    requests: set[str] = set()
    sessions: set[str] = set()
    for record in value["records"]:
        _require(
            isinstance(record, Mapping) and isinstance(record.get("request_id_hash"), str)
            and isinstance(record.get("session_id_hash"), str) and _HASH.fullmatch(record["request_id_hash"])
            and _HASH.fullmatch(record["session_id_hash"]) and record["request_id_hash"] not in requests
            and record["session_id_hash"] not in sessions,
            "Historical identity exclusion record differs",
        )
        requests.add(record["request_id_hash"])
        sessions.add(record["session_id_hash"])
    _require(len(requests) == len(sessions) == HISTORICAL_EXCLUSION_COUNT, "Historical identity exclusion cardinality differs")
    return requests, sessions


def _predecessor(path: Path | str, expected: str) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _read(path, expected, "Composite predecessor")
    value = _json(raw, "Composite predecessor")
    required = {
        "schema_version", "initialization", "ledger_head", "recovery_manifest", "identity_exclusion",
    }
    _require(isinstance(value, Mapping) and set(value) == required and value.get("schema_version") == 1, "Composite predecessor schema differs")
    predecessor = {name: _descriptor(value[name], "Predecessor " + name) for name in required - {"schema_version"}}
    return dict(value), predecessor


def _qualified(result: Mapping[str, Any], question_ids: Sequence[str], *, expected_native: int,
               evidence_class: str) -> tuple[list[dict[str, Any]], list[dict[str, str]], float | int, float | int]:
    verdicts = result.get("verdicts")
    identities = result.get("native_identities")
    _require(
        set(result) == {
            "verdicts", "score", "coverage", "native_identities", "run_manifest_sha256", "checkpoint_head_sha256",
            "evidence_class",
        }
        and result.get("evidence_class") == evidence_class and isinstance(verdicts, list) and len(verdicts) == QUESTION_COUNT
        and isinstance(identities, list) and len(identities) == expected_native,
        "Per-pass replay result differs",
    )
    _require(
        isinstance(result.get("run_manifest_sha256"), str) and _HASH.fullmatch(result["run_manifest_sha256"])
        and isinstance(result.get("checkpoint_head_sha256"), str) and _HASH.fullmatch(result["checkpoint_head_sha256"]),
        "Per-pass native replay commitments differ",
    )
    normalized = [dict(item) for item in verdicts if isinstance(item, Mapping)]
    _require(len(normalized) == QUESTION_COUNT and [item.get("question_id") for item in normalized] == list(question_ids),
             "Per-pass criterion order differs")
    native = [dict(item) for item in identities if isinstance(item, Mapping)]
    _require(len(native) == expected_native and all(isinstance(item.get("request_id_hash"), str)
             and isinstance(item.get("session_id_hash"), str) and _HASH.fullmatch(item["request_id_hash"])
             and _HASH.fullmatch(item["session_id_hash"]) and type(item.get("observed_turns")) is int
             and item["observed_turns"] >= 1 for item in native), "Per-pass identity differs")
    score, coverage = result.get("score"), result.get("coverage")
    _require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100
             and type(coverage) in (int, float) and math.isfinite(coverage) and coverage >= 0.88
             and result.get("provisional") is not True and result.get("fail_contract") is not True,
             "Per-pass score is not qualified")
    return normalized, native, score, coverage


def _identity_projection(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [{"request_id_hash": item["request_id_hash"], "session_id_hash": item["session_id_hash"]} for item in values]


def _suffix_result(result: Mapping[str, Any], question_ids: Sequence[str], *, pass_id: str,
                   mixed: bool) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]], float | int, float | int]:
    evidence = "mixed_v4_native_recovered70_and_v5_native_replay" if mixed else "v5_native_full_pass_replay"
    expected_new = 12 if mixed else 23
    verdicts = result.get("verdicts")
    identities = result.get("native_identities")
    _require(
        result.get("pass_id") == pass_id and result.get("evidence_class") == evidence and result.get("provider_calls_made") == 0
        and result.get("old_prefix_native_records") == PREFIX_NATIVE_COUNT and result.get("new_v5_native_records") == expected_new
        and (not mixed or (result.get("old_v4_native_records") == 10 and result.get("old_recovered70_records") == 1))
        and (mixed or (result.get("old_v4_native_records") == 0 and result.get("old_recovered70_records") == 0))
        and isinstance(verdicts, list) and len(verdicts) == QUESTION_COUNT and isinstance(identities, list)
        and len(identities) == PREFIX_NATIVE_COUNT + expected_new,
        "Suffix replay result differs",
    )
    normalized = [dict(item) for item in verdicts if isinstance(item, Mapping)]
    _require(len(normalized) == QUESTION_COUNT and [item.get("question_id") for item in normalized] == list(question_ids),
             "Suffix criterion order differs")
    values = [dict(item) for item in identities if isinstance(item, Mapping)]
    _require(len(values) == len(identities) and all(isinstance(item.get("request_id_hash"), str)
             and isinstance(item.get("session_id_hash"), str) and _HASH.fullmatch(item["request_id_hash"])
             and _HASH.fullmatch(item["session_id_hash"]) for item in values), "Suffix identity differs")
    score, coverage = result.get("score"), result.get("coverage")
    _require(type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100
             and type(coverage) in (int, float) and math.isfinite(coverage) and coverage >= 0.88
             and result.get("provisional") is not True and result.get("fail_contract") is not True,
             "Suffix score is not qualified")
    return normalized, values[:PREFIX_NATIVE_COUNT], values[PREFIX_NATIVE_COUNT:], score, coverage


def _identity_sets(values: Sequence[Mapping[str, str]], historical_requests: set[str], historical_sessions: set[str]) -> None:
    requests = [item["request_id_hash"] for item in values]
    sessions = [item["session_id_hash"] for item in values]
    request_set, session_set = set(requests), set(sessions)
    _require(
        len(requests) == len(request_set) and len(sessions) == len(session_set)
        and not (request_set & session_set)
        and not (request_set & historical_requests) and not (request_set & historical_sessions)
        and not (session_set & historical_requests) and not (session_set & historical_sessions),
        "Composite native identity collision or historical exclusion differs",
    )


def _measurement_source(plan_root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    source = _source(plan_root, record)
    raw = Path(source["path"]).read_bytes()
    return {
        "opaque_story_id": record["logical_sample_id"], "source_opaque_story_id": record["opaque_story_id"],
        "story_text": raw.decode("utf-8"), "artifact_path": source["path"],
    }


def _old_inventory_descriptor(context: Any, descriptor: Mapping[str, Any], label: str, expected_relative: str) -> bytes:
    root = _plain(context.old_root, directory=True)
    path = _plain(descriptor["path"], directory=False)
    _require(path.is_relative_to(root), f"{label} is outside the actual old execution root")
    inventory = context.epoch.get("old_execution_inventory")
    relative = path.relative_to(root).as_posix()
    _require(relative == expected_relative and isinstance(inventory, Mapping) and inventory.get(relative) == descriptor["sha256"],
             f"{label} differs from the frozen old execution inventory")
    return _read(path, descriptor["sha256"], label)


def _predecessor_bindings(
    context: Any, predecessor: Mapping[str, Any], *, expected_plan_sha256: str, expected_public_inputs_sha256: str,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    initialization_raw = _old_inventory_descriptor(
        context, predecessor["initialization"], "Predecessor initialization", "initialization.json",
    )
    initialization = _json(initialization_raw, "Predecessor initialization")
    fields = {
        "schema_version", "evidence_class", "plan_sha256", "plan_inventory_sha256", "plan_files",
        "runtime_manifest_sha256", "route_sha256", "execution_source_sha256", "public_inputs_sha256",
    }
    _require(
        isinstance(initialization, Mapping) and set(initialization) in (fields, fields | {"route_snapshot_sha256"})
        and type(initialization.get("schema_version")) is int and initialization["schema_version"] == 1
        and initialization.get("evidence_class") == "provider_free_baseline_initialization"
        and initialization.get("plan_sha256") == expected_plan_sha256
        and isinstance(initialization.get("plan_inventory_sha256"), str) and _HASH.fullmatch(initialization["plan_inventory_sha256"])
        and initialization.get("plan_files") == 11094
        and initialization.get("runtime_manifest_sha256") == context.epoch["old_runtime_manifest"]["sha256"]
        and isinstance(initialization.get("route_sha256"), str) and _HASH.fullmatch(initialization["route_sha256"])
        and isinstance(initialization.get("execution_source_sha256"), str) and _HASH.fullmatch(initialization["execution_source_sha256"])
        and initialization.get("public_inputs_sha256") == expected_public_inputs_sha256,
        "Actual predecessor initialization bindings differ",
    )
    if "route_snapshot_sha256" in initialization:
        _require(isinstance(initialization["route_snapshot_sha256"], str) and _HASH.fullmatch(initialization["route_snapshot_sha256"]),
                 "Actual predecessor route snapshot differs")
    settlement_raw = _old_inventory_descriptor(
        context, predecessor["ledger_head"], "Predecessor cohort settlement", "cohorts/0008/settlement.json",
    )
    settlement = _json(settlement_raw, "Predecessor cohort settlement")
    settlement_fields = {
        "schema_version", "cohort_number", "plan_sha256", "prepared_sha256", "review_sha256", "route_sha256",
        "previous_settlement_sha256", "settled_at", "contacts", "authorization_chain",
    }
    _require(
        isinstance(settlement, Mapping) and set(settlement) == settlement_fields
        and settlement.get("schema_version") == 3 and settlement.get("cohort_number") == 8
        and settlement.get("plan_sha256") == expected_plan_sha256
        and all(isinstance(settlement.get(name), str) and _HASH.fullmatch(settlement[name])
                for name in ("prepared_sha256", "review_sha256", "route_sha256", "previous_settlement_sha256"))
        and isinstance(settlement.get("settled_at"), str) and isinstance(settlement.get("contacts"), list)
        and isinstance(settlement.get("authorization_chain"), list),
        "Actual predecessor cohort settlement differs",
    )
    ledger_head = {"cohort_number": 8, "settlement_sha256": predecessor["ledger_head"]["sha256"]}
    anchors = context.prefix_anchors
    _require(
        isinstance(anchors, Mapping)
        and (anchors.get("initialization_sha256") is None or anchors["initialization_sha256"] == predecessor["initialization"]["sha256"])
        and (anchors.get("final_settlement_sha256") is None or anchors["final_settlement_sha256"] == ledger_head["settlement_sha256"]),
        "Actual prefix settlement anchors differ",
    )
    original = {
        "execution_source_sha256": initialization["execution_source_sha256"],
        "route_sha256": initialization["route_sha256"],
    }
    return dict(initialization), original, dict(ledger_head)


def _actual_replay_context(
    *, suffix_root: Path, plan_root: Path, expected_epoch_sha256: str, expected_suffix_source_sha256: str,
    predecessor: Mapping[str, Any],
) -> Any:
    epoch_raw = _read(suffix_root / "suffix-epoch.json", expected_epoch_sha256, "Suffix epoch")
    epoch_value = _json(epoch_raw, "Suffix epoch")
    _require(isinstance(epoch_value, Mapping) and isinstance(epoch_value.get("executor_source"), Mapping), "Suffix epoch source binding differs")
    executor = epoch_value["executor_source"]
    _require(executor.get("sha256") == expected_suffix_source_sha256, "Suffix source anchor differs")
    suffix = _load_module(_plain(executor.get("path"), directory=False), expected_suffix_source_sha256, "Suffix executor")
    epoch, _ = suffix._load_epoch(suffix_root, expected_epoch_sha256)
    resolved_plan, old_root, prefix_root, _requests = suffix._epoch_integrity(suffix_root, epoch)
    _require(resolved_plan == plan_root, "Suffix epoch plan root differs")
    prefix_raw = _read(epoch["old_prefix_manifest"]["path"], epoch["old_prefix_manifest"]["sha256"], "Old prefix manifest")
    prefix = _json(prefix_raw, "Old prefix manifest")
    _require(
        isinstance(prefix, Mapping) and isinstance(prefix.get("anchors"), Mapping)
        and prefix["anchors"].get("grok51_manifest_sha256") == predecessor["recovery_manifest"]["sha256"]
        and isinstance(prefix.get("per_pass"), list) and len(prefix["per_pass"]) == 4,
        "Old prefix provenance differs",
    )
    records = prefix["per_pass"]
    _require(all(isinstance(item, Mapping) for item in records), "Old prefix pass provenance differs")
    old_passes: list[dict[str, str]] = []
    for item in records[:3]:
        _require(
            isinstance(item.get("pass_id"), str) and isinstance(item.get("run_root"), str)
            and item.get("checkpoint_count") == 23 and item.get("native_records") == 23
            and item.get("study_recovered_records") == 0,
            "Old complete pass provenance differs",
        )
        old_passes.append({"pass_id": item["pass_id"], "run_root": str(_plain(item["run_root"], directory=True))})
    old_runtime = suffix._old_runtime_from_epoch(epoch)
    recovered = suffix._load_module(
        _plain(epoch["recovered_study_source"]["path"], directory=False), epoch["recovered_study_source"]["sha256"], "Recovered study",
    )
    native = recovered._module("native_admission")
    return SimpleNamespace(
        suffix=suffix, epoch=epoch, old_root=old_root, prefix_root=prefix_root, old_passes=old_passes,
        old_runtime=old_runtime, native=native, prefix_manifest={"path": epoch["old_prefix_manifest"]["path"], "sha256": epoch["old_prefix_manifest"]["sha256"]},
        prefix_anchors=dict(prefix["anchors"]),
    )


def _actual_old_admit(context: Any, *, plan_root: Path, pass_record: Mapping[str, Any], run_root: Path,
                      approved_v4_routes: Mapping[str, Any]) -> Mapping[str, Any]:
    return context.native.admit_pass(
        run_root, source=_measurement_source(plan_root, pass_record), batch_size=8,
        approved_routes=dict(approved_v4_routes), runtime=context.old_runtime,
    )


def _actual_suffix_admit(context: Any, *, suffix_root: Path, expected_epoch_sha256: str, pass_id: str,
                         approved_v4_routes: Mapping[str, Any], approved_v5_routes: Mapping[str, Any]) -> Mapping[str, Any]:
    return context.suffix.admit_pass(
        suffix_root=suffix_root, expected_epoch_sha256=expected_epoch_sha256, pass_id=pass_id,
        approved_v4_routes=dict(approved_v4_routes), approved_v5_routes=dict(approved_v5_routes),
    )


def _terminal_commitments(
    context: Any, *, suffix_root: Path, expected_epoch_sha256: str, ordinals: Sequence[int],
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    reviews: dict[str, dict[str, Any]] = {}
    for ordinal in ordinals:
        start_path = context.suffix._attempt_path(suffix_root, ordinal, "attempt-start.json")
        terminal_path = context.suffix._attempt_path(suffix_root, ordinal, "terminal.json")
        start_raw = start_path.read_bytes()
        terminal_raw = terminal_path.read_bytes()
        start, terminal = _json(start_raw, "Suffix attempt start"), _json(terminal_raw, "Suffix terminal")
        _require(
            isinstance(start, Mapping) and isinstance(terminal, Mapping) and start.get("ordinal") == ordinal
            and terminal.get("ordinal") == ordinal and start.get("epoch_sha256") == expected_epoch_sha256
            and terminal.get("epoch_sha256") == expected_epoch_sha256 and terminal.get("status") == "completed"
            and terminal.get("attempt_start_sha256") == _sha(start_raw),
            "Ordered suffix terminal provenance differs",
        )
        review = start.get("review")
        _require(isinstance(review, Mapping) and set(review) == {"path", "sha256"}, "Suffix terminal review binding differs")
        descriptor = _descriptor(review, "Suffix terminal review")
        reviews[descriptor["sha256"]] = descriptor
        entries.append({"ordinal": ordinal, "attempt_start_sha256": _sha(start_raw), "terminal_sha256": _sha(terminal_raw),
                        "review_sha256": descriptor["sha256"]})
    return entries, _sha(_canonical(entries)), [reviews[key] for key in sorted(reviews)]


def admit_composite_baseline(
    *,
    plan_root: Path | str,
    public_inputs_path: Path | str,
    predecessor_path: Path | str,
    suffix_root: Path | str,
    expected_plan_sha256: str,
    expected_public_inputs_sha256: str,
    expected_predecessor_sha256: str,
    expected_suffix_epoch_sha256: str,
    expected_suffix_source_sha256: str,
    expected_selected_schedule_sha256: str,
    expected_selected_schedule_source_sha256: str,
    expected_composer_sha256: str,
    approved_v4_routes: Mapping[str, Any],
    approved_v5_routes: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose the actual pinned native prefix and suffix replays without dispatching work."""
    own = _plain(Path(__file__), directory=False)
    _require(_sha(own.read_bytes()) == _digest(expected_composer_sha256, "Composer source"), "Composer source differs")
    plan_root = _plain(plan_root, directory=True)
    suffix_root = _plain(suffix_root, directory=True)
    _require(not suffix_root.is_relative_to(plan_root) and not plan_root.is_relative_to(suffix_root), "Composite plan and suffix roots overlap")
    _public_raw = _read(public_inputs_path, expected_public_inputs_sha256, "Public inputs")
    _require(isinstance(_json(_public_raw, "Public inputs"), Mapping), "Public inputs schema differs")
    _plan_value, _plan_raw, passes, _pass_by_id, question_ids = _plan(plan_root, expected_plan_sha256)
    _predecessor_raw, predecessor = _predecessor(predecessor_path, expected_predecessor_sha256)
    expected_suffix_epoch_sha256 = _digest(expected_suffix_epoch_sha256, "Suffix epoch")
    expected_suffix_source_sha256 = _digest(expected_suffix_source_sha256, "Suffix source")
    expected_selected_schedule_sha256 = _digest(expected_selected_schedule_sha256, "Selected schedule")
    expected_selected_schedule_source_sha256 = _digest(
        expected_selected_schedule_source_sha256, "Selected schedule source",
    )
    context = _actual_replay_context(
        suffix_root=suffix_root, plan_root=plan_root, expected_epoch_sha256=expected_suffix_epoch_sha256,
        expected_suffix_source_sha256=expected_suffix_source_sha256, predecessor=predecessor,
    )
    epoch = context.epoch
    _require(
        epoch["executor_source"]["sha256"] == expected_suffix_source_sha256
        and epoch["plan_sha256"] == expected_plan_sha256
        and context.prefix_manifest["sha256"] == epoch["old_prefix_manifest"]["sha256"],
        "Actual suffix replay provenance differs",
    )
    schedule_descriptor = _descriptor_with_bytes(epoch.get("selected_schedule"), "Selected schedule")
    schedule_source_descriptor = _descriptor(epoch.get("selected_schedule_source"), "Selected schedule source")
    _require(
        schedule_descriptor["sha256"] == expected_selected_schedule_sha256
        and schedule_source_descriptor["sha256"] == expected_selected_schedule_source_sha256,
        "Selected schedule epoch binding differs",
    )
    schedule_module = _load_module(
        Path(schedule_source_descriptor["path"]), expected_selected_schedule_source_sha256, "Selected schedule source",
    )
    verified_selection = schedule_module.verify_selected_schedule(
        descriptor=_json(_read(Path(schedule_descriptor["path"]), expected_selected_schedule_sha256, "Selected schedule"), "Selected schedule"),
        plan_root=plan_root,
        expected_plan_sha256=expected_plan_sha256,
    )
    selected_pass_ids = [*verified_selection["selected_train_ids"], *verified_selection["selected_dev_ids"]]
    selected_records = [_pass_by_id.get(pass_id) for pass_id in selected_pass_ids]
    selected_request_ordinals = verified_selection["selected_request_ordinals"]
    remaining_ordinals = verified_selection["grok_remaining_request_ordinals"]
    _require(
        len(selected_records) == SELECTED_PASS_COUNT and all(isinstance(item, Mapping) for item in selected_records)
        and len(set(selected_pass_ids)) == SELECTED_PASS_COUNT
        and verified_selection["question_ids"] == question_ids
        and epoch.get("selected_request_ordinals") == selected_request_ordinals
        and epoch.get("remaining_request_ordinals") == remaining_ordinals
        and len(selected_request_ordinals) == SELECTED_LOGICAL_REQUEST_COUNT
        and len(remaining_ordinals) == SELECTED_REMAINING_REQUEST_COUNT
        and remaining_ordinals[0] == FIRST_SUFFIX_ORDINAL
        and selected_request_ordinals[:PREFIX_NATIVE_COUNT + 1] == list(range(1, PREFIX_NATIVE_COUNT + 2)),
        "Selected baseline inventory differs",
    )
    selected_records = [dict(item) for item in selected_records]
    initialization, original_initialization, ledger_head = _predecessor_bindings(
        context, predecessor, expected_plan_sha256=expected_plan_sha256,
        expected_public_inputs_sha256=expected_public_inputs_sha256,
    )
    historical_requests, historical_sessions = _identity_exclusions(predecessor["identity_exclusion"])
    old_specs = context.old_passes
    _require([item["pass_id"] for item in old_specs] == [item["pass_id"] for item in passes[:3]], "Old pass order differs")
    _require([item["pass_id"] for item in old_specs] == [item["pass_id"] for item in selected_records[:3]], "Selected old pass order differs")
    endpoint_rows: list[dict[str, Any]] = []
    commitments: list[dict[str, Any]] = []
    first_three_native: list[dict[str, str]] = []
    for index, spec in enumerate(old_specs):
        record = passes[index]
        replay = _actual_old_admit(
            context, plan_root=plan_root, pass_record=dict(record), run_root=Path(spec["run_root"]),
            approved_v4_routes=approved_v4_routes,
        )
        verdicts, identities, score, coverage = _qualified(
            replay, question_ids, expected_native=23, evidence_class="native_record_replay_only",
        )
        first_three_native.extend(_identity_projection(identities))
        endpoint_rows.append({"pass_id": record["pass_id"], "opaque_story_id": record["opaque_story_id"], "verdicts": verdicts,
                              "score": score, "coverage": coverage, "provenance": "v4_native"})
        commitments.append({"pass_id": record["pass_id"], "source": _source(plan_root, record), "replay_sha256": _sha(_canonical(replay)),
                            "native_records": 23, "recovered_records": 0, "provenance": "v4_native"})
    prefix_context: list[dict[str, str]] | None = None
    new_native: list[dict[str, str]] = []
    recovered_count = 0
    for index, record in enumerate(selected_records[3:], start=4):
        mixed = index == 4
        replay = _actual_suffix_admit(
            context, suffix_root=suffix_root, expected_epoch_sha256=expected_suffix_epoch_sha256, pass_id=record["pass_id"],
            approved_v4_routes=approved_v4_routes, approved_v5_routes=approved_v5_routes,
        )
        verdicts, repeated, fresh, score, coverage = _suffix_result(replay, question_ids, pass_id=record["pass_id"], mixed=mixed)
        if prefix_context is None:
            _require(repeated[:69] == first_three_native, "Suffix repeated old-prefix identities differ")
            prefix_context = repeated
            recovered_count = 1
        else:
            _require(repeated == prefix_context, "Suffix repeated old-prefix identities differ")
        new_native.extend(fresh)
        endpoint_rows.append({"pass_id": record["pass_id"], "opaque_story_id": record["opaque_story_id"], "verdicts": verdicts,
                              "score": score, "coverage": coverage, "provenance": "mixed_v4_recovered70_v5" if mixed else "v5_native"})
        commitments.append({"pass_id": record["pass_id"], "source": _source(plan_root, record), "replay_sha256": _sha(_canonical(replay)),
                            "native_records": len(fresh), "recovered_records": 1 if mixed else 0,
                            "provenance": "mixed_v4_recovered70_v5" if mixed else "v5_native"})
    _require(prefix_context is not None and len(prefix_context) == PREFIX_NATIVE_COUNT and len(first_three_native) == 69
             and len(endpoint_rows) == SELECTED_PASS_COUNT and len(commitments) == SELECTED_PASS_COUNT,
             "Composite pass replay inventory differs")
    all_native = prefix_context + new_native
    _require(len(new_native) == SELECTED_NATIVE_REQUEST_COUNT - PREFIX_NATIVE_COUNT and len(all_native) == SELECTED_NATIVE_REQUEST_COUNT
             and recovered_count == 1, "Composite native/recovered cardinality differs")
    _identity_sets(all_native, historical_requests, historical_sessions)
    terminals, terminal_commitment, reviews = _terminal_commitments(
        context, suffix_root=suffix_root, expected_epoch_sha256=expected_suffix_epoch_sha256, ordinals=remaining_ordinals,
    )
    _require(
        len(terminals) == SELECTED_REMAINING_REQUEST_COUNT
        and [item.get("ordinal") for item in terminals] == remaining_ordinals
        and isinstance(reviews, list) and reviews
        and all(isinstance(item, Mapping) and _HASH.fullmatch(item.get("sha256", "")) for item in reviews)
        and [row["pass_id"] for row in endpoint_rows] == [record["pass_id"] for record in selected_records]
        and [row["opaque_story_id"] for row in endpoint_rows] == [record["opaque_story_id"] for record in selected_records]
        and len({row["opaque_story_id"] for row in endpoint_rows}) == SELECTED_PASS_COUNT
        and all([item["question_id"] for item in row["verdicts"]] == question_ids for row in endpoint_rows),
        "Composite endpoint rows differ",
    )
    record = {
        "schema_version": 2,
        "evidence_class": "composite_v4_recovered70_v5_selected_baseline_admission",
        "composer_source_sha256": expected_composer_sha256,
        "plan_sha256": expected_plan_sha256,
        "public_inputs_sha256": expected_public_inputs_sha256,
        "counts": {"passes": SELECTED_PASS_COUNT, "logical": SELECTED_LOGICAL_REQUEST_COUNT,
                   "native": SELECTED_NATIVE_REQUEST_COUNT, "recovered": 1},
        "recovered_ordinals": [RECOVERED_ORDINAL],
        "selection": {
            "schedule": schedule_descriptor,
            "source": schedule_source_descriptor,
            "train_pass_ids": verified_selection["selected_train_ids"],
            "dev_pass_ids": verified_selection["selected_dev_ids"],
            "request_ordinals": selected_request_ordinals,
        },
        "predecessor": {
            "initialization_sha256": predecessor["initialization"]["sha256"], "initialization": predecessor["initialization"],
            "initialization_record": initialization,
            "original_initialization": original_initialization, "ledger_head": ledger_head,
            "ledger_head_record": predecessor["ledger_head"],
            "covered_ordinals": [1, 80], "prefix_manifest": context.prefix_manifest,
            "recovery_manifest": predecessor["recovery_manifest"],
            "recovered_study_manifest": epoch["recovered_study_manifest"],
            "adoption_sha256": epoch["recovery_adoption_sha256"], "amendment_sha256": epoch["recovery_amendment_sha256"],
        },
        "suffix": {
            "epoch_sha256": expected_suffix_epoch_sha256, "source_sha256": epoch["executor_source"]["sha256"],
            "runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"],
            "runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"],
            "covered_ordinals": remaining_ordinals,
            "ordered_terminal_commitment_sha256": terminal_commitment,
            "ordered_terminals": terminals, "review_bindings": reviews,
        },
        "identity_exclusion_sha256": predecessor["identity_exclusion"]["sha256"],
        "per_pass_replay_commitments": commitments,
        "endpoint_grok_rows": endpoint_rows,
        "provider_calls_made": 0,
        "execution_authority": False,
        "promotion_authority": False,
        "confirmation_authority": False,
    }
    return {"composite_admission": record, "composite_admission_sha256": _sha(_canonical(record)),
            "provider_calls_made": 0, "execution_authority": False}
