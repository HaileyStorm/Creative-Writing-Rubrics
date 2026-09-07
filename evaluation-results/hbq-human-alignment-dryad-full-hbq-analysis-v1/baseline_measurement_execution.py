"""Governed, reviewed collection of the fixed batch-eight Dryad baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
EXECUTION_SOURCE_RELATIVE = Path(__file__).relative_to(REPOSITORY).as_posix()
PLAN_SOURCE = ROOT / "baseline_measurement_plan.py"
LEDGER_SOURCE = ROOT / "baseline_measurement_ledger.py"
RUNTIME_SOURCE = ROOT / "baseline_native_runtime.py"
NATIVE_SOURCE = ROOT / "native_admission.py"
ADMISSION_SOURCE = ROOT / "baseline_measurement_admission.py"
TERMINAL_IDENTITIES = ROOT / "terminal-identities-v2.json"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
SOURCE_PINS = {
    PLAN_SOURCE: "33193aa1a394c04c14b4f9ab81871116dbac11f933f22a9e45f252b2d279fdc8",
    LEDGER_SOURCE: "67f3df2b48708e7eec2f9362d4441b6c7a7cddbf978d8edb10a7f4fbadb4b4c1",
    RUNTIME_SOURCE: "5130bc037e0700f8d498c40ca790aaf248e986189818ae059934ee6488bbfbcd",
    NATIVE_SOURCE: "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec",
    ADMISSION_SOURCE: "062a7b3f4e5783a62d3c269ecb01884bc089d3671fec28f5cb52489acda612e2",
    TERMINAL_IDENTITIES: "82cc80c2692fc0c0f47024d4db04cdbf5dd1c34c2d5deea40916a0e8ea45ca63",
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
REVIEWER_TASK = "baseline-human-review"
GENESIS_SETTLEMENT_SHA256 = "0" * 64


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _plain(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                 "Path contains a link or reparse point")
    if directory is True:
        _require(absolute.is_dir(), "Expected directory")
    if directory is False:
        _require(absolute.is_file(), "Expected file")
    return absolute


def _relative(root: Path, name: str, *, directory: bool | None = None) -> Path:
    candidate = Path(name)
    _require(isinstance(name, str) and name and not candidate.is_absolute()
             and all(part not in {".", ".."} for part in candidate.parts), "Relative path differs")
    result = _plain(root / candidate, directory=directory)
    _require(result.is_relative_to(root), "Relative path escapes its root")
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _require(isinstance(key, str) and key not in result, f"{label} has duplicate keys")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _load(path: Path, raw: bytes, prefix: str) -> ModuleType:
    name = prefix + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local source.
        return module
    finally:
        sys.modules.pop(name, None)


def _sources() -> tuple[dict[Path, bytes], tuple[ModuleType, ModuleType, ModuleType, ModuleType, ModuleType]]:
    captured = {_plain(path, directory=False): path.read_bytes() for path in SOURCE_PINS}
    _require(all(_hash(captured[path]) == expected for path, expected in SOURCE_PINS.items()),
             "Baseline execution dependency source pin differs")
    own = _plain(Path(__file__), directory=False)
    captured[own] = own.read_bytes()
    modules = (
        _load(PLAN_SOURCE, captured[PLAN_SOURCE], "_dryad_baseline_plan_"),
        _load(LEDGER_SOURCE, captured[LEDGER_SOURCE], "_dryad_baseline_ledger_"),
        _load(RUNTIME_SOURCE, captured[RUNTIME_SOURCE], "_dryad_baseline_runtime_"),
        _load(NATIVE_SOURCE, captured[NATIVE_SOURCE], "_dryad_baseline_native_"),
        _load(ADMISSION_SOURCE, captured[ADMISSION_SOURCE], "_dryad_baseline_admission_"),
    )
    return captured, modules


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    _require(all(_plain(path, directory=False).read_bytes() == raw for path, raw in captured.items()),
             "Baseline execution source changed")


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _lock(root: Path) -> tuple[Path, bytes]:
    token = uuid.uuid4().hex.encode("ascii")
    path = root / ".launch.lock"
    _write_new(path, token)
    return path, token


def _route_hash(route: Mapping[str, Any]) -> str:
    _require(isinstance(route, Mapping), "Route snapshot differs")
    return _hash(_canonical(dict(route)))


def _time(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and value.endswith(("Z", "+00:00")), f"{label} differs")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _plan(plan_root: Path, expected_plan_sha256: str) -> tuple[dict[str, Any], bytes]:
    _require(expected_plan_sha256 == PLAN_SHA256, "Published baseline plan anchor differs")
    raw = _relative(plan_root, "plan.json", directory=False).read_bytes()
    _require(_hash(raw) == expected_plan_sha256, "Baseline plan anchor differs")
    plan = _json(raw, "Baseline plan")
    _require(plan.get("dispatch_batch_size") == 8 and plan.get("empirical_batch_cap") is None
             and isinstance(plan.get("passes"), list) and len(plan["passes"]) == 236
             and isinstance(plan.get("requests"), list) and len(plan["requests"]) == 5428, "Baseline plan geometry differs")
    return plan, raw


def _groups(ledger: ModuleType, plan: Mapping[str, Any], number: int) -> tuple[int, ...]:
    groups = ledger.cohort_groups(plan)
    _require(type(number) is int and 1 <= number <= len(groups), "Baseline cohort number differs")
    group = groups[number - 1]
    _require(group and tuple(group) == tuple(range(group[0], group[0] + len(group)))
             and tuple(ordinal for item in groups for ordinal in item) == tuple(range(1, len(plan["requests"]) + 1)),
             "Baseline cohort group differs")
    return tuple(group)


def _rows(plan: Mapping[str, Any], plan_root: Path, ordinals: tuple[int, ...]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]]]:
    passes = plan["passes"]
    requests = plan["requests"]
    pass_by_id = {row.get("pass_id"): row for row in passes if isinstance(row, dict) and isinstance(row.get("pass_id"), str)}
    _require(len(pass_by_id) == 236, "Baseline pass inventory differs")
    request_by_ordinal = {row.get("ordinal"): row for row in requests if isinstance(row, dict) and type(row.get("ordinal")) is int}
    _require(set(request_by_ordinal) == set(range(1, 5429)), "Baseline request inventory differs")
    selected = {ordinal: request_by_ordinal[ordinal] for ordinal in ordinals}
    for request in selected.values():
        passed = pass_by_id.get(request.get("pass_id"))
        _require(isinstance(passed, dict) and request.get("logical_sample_id") == passed.get("logical_sample_id")
                 and type(request.get("batch_number")) is int and 1 <= request["batch_number"] <= 23
                 and isinstance(request.get("question_ids"), list) and 1 <= len(request["question_ids"]) <= 8
                 and all(isinstance(value, str) and value for value in request["question_ids"]), "Baseline request binding differs")
        for path_name, hash_name, bytes_name in (("prompt_path", "prompt_sha256", "prompt_bytes"),
                                                  ("schema_path", "schema_sha256", "schema_bytes")):
            raw = _relative(plan_root, request.get(path_name), directory=False).read_bytes()
            _require(_hash(raw) == request.get(hash_name) and len(raw) == request.get(bytes_name),
                     "Baseline planned payload differs")
        payloads = request.get("endpoint_user_payloads")
        _require(payloads == {"grok": {"sha256": request["prompt_sha256"], "bytes": request["prompt_bytes"]},
                              "sol": {"sha256": request["prompt_sha256"], "bytes": request["prompt_bytes"]}},
                 "Baseline endpoint payload binding differs")
    return pass_by_id, selected


def _source(record: Mapping[str, Any], plan_root: Path) -> tuple[Path, bytes]:
    path = _relative(plan_root, record.get("input_path"), directory=False)
    raw = path.read_bytes()
    _require(_hash(raw) == record.get("source_sha256") and len(raw) == record.get("source_bytes"),
             "Baseline source payload differs")
    raw.decode("utf-8")
    return path, raw


def _initialization(execution_root: Path, expected_sha256: str) -> tuple[dict[str, Any], bytes]:
    raw = _relative(execution_root, "initialization.json", directory=False).read_bytes()
    _require(_HASH.fullmatch(expected_sha256) is not None and _hash(raw) == expected_sha256,
             "Initialization anchor differs")
    value = _json(raw, "Initialization")
    required = {"schema_version", "evidence_class", "plan_sha256", "plan_inventory_sha256", "plan_files",
                "runtime_manifest_sha256", "route_sha256", "execution_source_sha256", "public_inputs_sha256"}
    _require((set(value) == required or set(value) == required | {"route_snapshot_sha256"})
             and value.get("schema_version") == 1
             and value.get("evidence_class") == "provider_free_baseline_initialization"
             and value.get("plan_sha256") == PLAN_SHA256 and value.get("plan_files") == 11094
             and all(isinstance(value.get(key), str) and _HASH.fullmatch(value[key]) is not None
                     for key in value if key.endswith("sha256"))
             , "Initialization record differs")
    return value, raw


def initialize(public_inputs_path: Path, plan_root: Path, execution_root: Path, runtime_manifest_path: Path,
               route_path: Path, *, expected_plan_sha256: str, expected_runtime_manifest_sha256: str,
               expected_route_sha256: str) -> dict[str, str]:
    """Create the exclusive provider-free binding after one complete plan verification."""
    _require(expected_plan_sha256 == PLAN_SHA256 and _HASH.fullmatch(expected_runtime_manifest_sha256) is not None
             and _HASH.fullmatch(expected_route_sha256) is not None, "Initialization anchors differ")
    captured, (planner, _, runtime_loader, _, _) = _sources()
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    execution_root = _plain(execution_root, directory=True)
    runtime_manifest_path = _plain(runtime_manifest_path, directory=False)
    route_path = _plain(route_path, directory=False)
    _require(not plan_root.is_relative_to(execution_root) and not execution_root.is_relative_to(plan_root),
             "Baseline plan and execution roots must differ")
    route_raw = route_path.read_bytes()
    route = _json(route_raw, "External route snapshot")
    _require(_route_hash(route) == expected_route_sha256, "External route snapshot anchor differs")
    public_raw = public_inputs_path.read_bytes()
    verified = planner.verify(public_inputs_path, plan_root)
    _require(isinstance(verified, dict) and verified.get("plan.json") == expected_plan_sha256 and len(verified) == 11094,
             "Complete baseline plan verification differs")
    plan, plan_raw = _plan(plan_root, expected_plan_sha256)
    _require(plan.get("public_inputs_sha256") == _hash(public_raw), "Baseline public inputs binding differs")
    runtime = runtime_loader.load_runtime(runtime_manifest_path, expected_manifest_sha256=expected_runtime_manifest_sha256)
    runtime.verify()
    own = _plain(Path(__file__), directory=False)
    record = {
        "schema_version": 1,
        "evidence_class": "provider_free_baseline_initialization",
        "plan_sha256": expected_plan_sha256,
        "plan_inventory_sha256": _hash(_canonical(verified)),
        "plan_files": 11094,
        "runtime_manifest_sha256": expected_runtime_manifest_sha256,
        "route_sha256": _route_hash(route),
        "route_snapshot_sha256": _hash(route_raw),
        "execution_source_sha256": _hash(captured[own]),
        "public_inputs_sha256": _hash(public_raw),
    }
    lock, token = _lock(execution_root)
    try:
        _require(not any(path != lock for path in execution_root.iterdir()),
                 "Initialization requires an empty execution root")
        _write_new(execution_root / "initialization.json", _canonical(record))
        (execution_root / "cohorts").mkdir()
        (execution_root / "contacts").mkdir()
        _unchanged(captured)
        runtime.verify()
        _require(public_inputs_path.read_bytes() == public_raw and _relative(plan_root, "plan.json", directory=False).read_bytes() == plan_raw,
                 "Baseline initialization input changed")
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
    return {"initialization_sha256": _hash((execution_root / "initialization.json").read_bytes()),
            "plan_inventory_sha256": record["plan_inventory_sha256"], "route_sha256": record["route_sha256"]}


def _epoch(initialization: Mapping[str, Any], prior: Mapping[str, Any],
           expected_operational_renewal_sha256: str | None = None, *,
           apply_precontact_recovery: bool = True) -> dict[str, Any]:
    renewals = prior.get("renewals", [])
    _require(isinstance(renewals, list), "Operational renewal inventory differs")
    if not renewals:
        _require(expected_operational_renewal_sha256 is None, "Unexpected operational renewal anchor")
        return {"route": None, "route_sha256": initialization["route_sha256"],
                "execution_source_sha256": initialization["execution_source_sha256"],
                "operational_renewal_sha256": None}
    latest = renewals[-1]
    _require(isinstance(latest, Mapping) and isinstance(latest.get("sha256"), str)
             and _HASH.fullmatch(latest["sha256"]) is not None
             and expected_operational_renewal_sha256 == latest["sha256"]
             and isinstance(latest.get("value"), Mapping) and isinstance(latest["value"].get("new_route"), Mapping)
             and isinstance(latest.get("new_source"), Mapping) and isinstance(latest["new_source"].get("files"), Mapping),
             "Latest operational renewal differs")
    source_sha256 = latest["new_source"]["files"][EXECUTION_SOURCE_RELATIVE]
    epochs, head = prior.get("epochs"), prior.get("head")
    if (isinstance(epochs, Mapping) and isinstance(head, Mapping) and type(head.get("cohort_number")) is int
            and isinstance(epochs.get(head["cohort_number"]), Mapping)
            and latest.get("cohort_number") != head["cohort_number"]):
        resolved = epochs[head["cohort_number"]].get("execution_source_sha256")
        _require(isinstance(resolved, str) and _HASH.fullmatch(resolved) is not None,
                 "Resolved operational epoch differs")
        source_sha256 = resolved
    recovery = prior.get("precontact_recovery") if apply_precontact_recovery else None
    if recovery is not None:
        _require(isinstance(recovery, Mapping) and isinstance(recovery.get("sha256"), str)
                 and _HASH.fullmatch(recovery["sha256"]) is not None
                 and isinstance(recovery.get("source_sha256"), str)
                 and _HASH.fullmatch(recovery["source_sha256"]) is not None,
                 "Precontact recovery differs")
        source_sha256 = recovery["source_sha256"]
    return {"route": dict(latest["value"]["new_route"]), "route_sha256": latest["value"]["new_route_sha256"],
            "execution_source_sha256": source_sha256, "operational_renewal_sha256": latest["sha256"],
            "precontact_recovery_sha256": recovery["sha256"] if recovery is not None else None}


def _prepared(execution_root: Path, number: int, expected_sha256: str, initialization: Mapping[str, Any],
              ordinals: tuple[int, ...], previous_settlement_sha256: str, route: Mapping[str, Any],
              epoch: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    raw = _relative(execution_root, f"cohorts/{number:04d}/prepared.json", directory=False).read_bytes()
    _require(_hash(raw) == expected_sha256, "Prepared cohort anchor differs")
    value = _json(raw, "Prepared cohort")
    required = {"schema_version", "cohort_number", "plan_sha256", "previous_settlement_sha256",
                "request_ordinals", "route_sha256", "execution_source_sha256"}
    version = value.get("schema_version")
    if epoch["operational_renewal_sha256"] is None:
        _require(set(value) == required and version == 1, "Prepared cohort differs")
    else:
        _require(set(value) == required | {"operational_renewal_sha256"} and version == 2
                 and value.get("operational_renewal_sha256") == epoch["operational_renewal_sha256"],
                 "Prepared cohort operational renewal differs")
    _require(value.get("cohort_number") == number and value.get("plan_sha256") == initialization["plan_sha256"]
             and value.get("previous_settlement_sha256") == previous_settlement_sha256
             and value.get("request_ordinals") == list(ordinals) and value.get("route_sha256") == _route_hash(route) == epoch["route_sha256"]
             and value.get("execution_source_sha256") == epoch["execution_source_sha256"], "Prepared cohort differs")
    return value, raw


def prepare_cohort(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int,
                   route: Mapping[str, Any], *, expected_plan_sha256: str, expected_initialization_sha256: str,
                   expected_previous_settlement_sha256: str,
                   expected_operational_renewal_sha256: str | None = None) -> dict[str, str]:
    """Provider-free creation of one exact reviewed-cohort preparation record."""
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_HASH.fullmatch(value) is not None for value in
             (expected_initialization_sha256, expected_previous_settlement_sha256)), "Preparation anchors differ")
    captured, (_, ledger, runtime_loader, native, _) = _sources()
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    execution_root = _plain(execution_root, directory=True)
    initialization, initialization_raw = _initialization(execution_root, expected_initialization_sha256)
    _require(_hash(public_inputs_path.read_bytes()) == initialization["public_inputs_sha256"],
             "Initialization public inputs binding differs")
    own = _plain(Path(__file__), directory=False)
    runtime = runtime_loader.load_runtime(ROOT / "baseline-runtime-v1.json",
                                          expected_manifest_sha256=initialization["runtime_manifest_sha256"])
    runtime.verify()
    plan, plan_raw = _plan(plan_root, expected_plan_sha256)
    all_requests = {row["ordinal"]: row for row in plan["requests"]
                    if isinstance(row, Mapping) and type(row.get("ordinal")) is int}
    all_passes = {row["pass_id"]: row for row in plan["passes"]
                  if isinstance(row, Mapping) and isinstance(row.get("pass_id"), str)}
    _require(set(all_requests) == set(range(1, len(plan["requests"]) + 1)) and len(all_passes) == len(plan["passes"]),
             "Full baseline plan inventory differs")
    ordinals = _groups(ledger, plan, cohort_number)
    passes, requests = _rows(plan, plan_root, ordinals)
    _frozen_payloads(plan_root, requests, passes, ordinals)
    route = dict(route)
    lock, token = _lock(execution_root)
    try:
        prefix = execution_root / "cohorts" / f"{cohort_number:04d}"
        _require(not prefix.exists(), "Prepared cohort already exists")
        prior = ledger.verify_prefix(execution_root, public_inputs_path.read_bytes(), plan_raw, expected_plan_sha256,
                                     expected_previous_settlement_sha256, cohort_number - 1,
                                     expected_route_sha256=initialization["route_sha256"],
                                     expected_execution_source_sha256=initialization["execution_source_sha256"],
                                     expected_reviewer_task=REVIEWER_TASK)
        _require(prior["head"]["settlement_sha256"] == expected_previous_settlement_sha256,
                 "Previous baseline settlement differs")
        renewals = prior.get("renewals", [])
        if renewals and renewals[-1]["cohort_number"] == cohort_number - 1:
            _verify_new_renewal_boundary(execution_root, plan_root, prior, renewals[-1], all_passes, all_requests,
                                         runtime, native)
        epoch = _epoch(initialization, prior, expected_operational_renewal_sha256)
        _require(_hash(captured[own]) == epoch["execution_source_sha256"]
                 and _route_hash(route) == epoch["route_sha256"]
                 and (epoch["route"] is None or _canonical(route) == _canonical(epoch["route"])),
                 "Resolved operational epoch differs")
        prepared = {"schema_version": 1 if epoch["operational_renewal_sha256"] is None else 2,
                    "cohort_number": cohort_number, "plan_sha256": expected_plan_sha256,
                    "previous_settlement_sha256": expected_previous_settlement_sha256, "request_ordinals": list(ordinals),
                    "route_sha256": epoch["route_sha256"],
                    "execution_source_sha256": epoch["execution_source_sha256"]}
        if epoch["operational_renewal_sha256"] is not None:
            prepared["operational_renewal_sha256"] = epoch["operational_renewal_sha256"]
        _write_new(prefix / "prepared.json", _canonical(prepared))
        _write_new(prefix / "route.json", _canonical(route))
        _unchanged(captured)
        runtime.verify()
        _require(_relative(execution_root, "initialization.json", directory=False).read_bytes() == initialization_raw,
                 "Initialization changed during preparation")
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
    return {"prepared_sha256": _hash((execution_root / "cohorts" / f"{cohort_number:04d}" / "prepared.json").read_bytes()),
            "route_sha256": _route_hash(route)}


def prepare_precontact_recovery(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int, *,
                                expected_plan_sha256: str, expected_initialization_sha256: str,
                                expected_previous_settlement_sha256: str, expected_prepared_sha256: str,
                                expected_review_sha256: str, expected_source_sha256: str,
                                expected_operational_renewal_sha256: str) -> dict[str, Any]:
    """Produce an unapproved, provider-free source-recovery candidate for independent review."""
    anchors = (expected_initialization_sha256, expected_previous_settlement_sha256, expected_prepared_sha256,
               expected_review_sha256, expected_source_sha256, expected_operational_renewal_sha256)
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_HASH.fullmatch(value) is not None for value in anchors),
             "Precontact recovery anchors differ")
    captured, (_, ledger, _, _, _) = _sources()
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    root = _plain(execution_root, directory=True)
    initialization, initialization_raw = _initialization(root, expected_initialization_sha256)
    _require(_hash(public_inputs_path.read_bytes()) == initialization["public_inputs_sha256"],
             "Initialization precontact recovery binding differs")
    plan, plan_raw = _plan(plan_root, expected_plan_sha256)
    _groups(ledger, plan, cohort_number)
    route = _json(_relative(root, f"cohorts/{cohort_number:04d}/route.json", directory=False).read_bytes(), "Cohort route")
    lock, token = _lock(root)
    before = _execution_snapshot(root)
    try:
        result = ledger.prepare_precontact_recovery_candidate(
            root, public_inputs_path.read_bytes(), plan_raw, expected_plan_sha256=expected_plan_sha256,
            expected_initialization_sha256=expected_initialization_sha256,
            expected_previous_settlement_sha256=expected_previous_settlement_sha256, cohort_number=cohort_number,
            expected_prepared_sha256=expected_prepared_sha256, expected_review_sha256=expected_review_sha256,
            expected_operational_renewal_sha256=expected_operational_renewal_sha256,
            expected_route_sha256=_route_hash(route),
            expected_execution_source_sha256=expected_source_sha256, expected_reviewer_task=REVIEWER_TASK)
        _require(lock.is_file() and lock.read_bytes() == token and _execution_snapshot(root) == before,
                 "Precontact recovery preparation changed execution evidence")
        _unchanged(captured)
        _require(_relative(root, "initialization.json", directory=False).read_bytes() == initialization_raw,
                 "Initialization changed during precontact recovery preparation")
        return result
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()


def _continuations(execution_root: Path, number: int, prepared_sha256: str, review_sha256: str,
                   route_sha256: str, source_sha256: str) -> list[dict[str, Any]]:
    root = execution_root / "cohorts" / f"{number:04d}" / "review-continuations"
    if not root.exists():
        return []
    root = _plain(root, directory=True)
    files = sorted(root.glob("*.json"))
    _require([path.name for path in files] == [f"{index:04d}.json" for index in range(1, len(files) + 1)],
             "Continuation inventory differs")
    prior_authorization, prior_source = review_sha256, source_sha256
    result: list[dict[str, Any]] = []
    for path in files:
        raw = _plain(path, directory=False).read_bytes()
        value = _json(raw, "Continuation")
        required = {"schema_version", "reviewer_task", "decision", "prepared_sha256", "route_sha256",
                    "prior_authorization_sha256", "previous_execution_source_sha256", "execution_source_sha256",
                    "completed_prefix", "reviewed_at", "expires_at"}
        version = value.get("schema_version")
        _require(set(value) >= required and type(version) is int and version in {1, 2, 3}
                 and value.get("reviewer_task") == REVIEWER_TASK
                 and value.get("prepared_sha256") == prepared_sha256 and value.get("route_sha256") == route_sha256
                 and value.get("prior_authorization_sha256") == prior_authorization
                 and value.get("previous_execution_source_sha256") == prior_source
                 and (value.get("decision") == "approved_continuation" if version in {1, 2}
                      else not result and value.get("decision") == "approved_precontact_recovery"
                      and value.get("incident_type") == "utc_review_encoding_mismatch"), "Continuation binding differs")
        if version in {1, 2}:
            _require(set(value) == required and value.get("execution_source_sha256") == prior_source,
                     "Continuation binding differs")
        else:
            recovery = {"incident_type", "original_initialization_sha256", "previous_settlement_sha256",
                        "operational_renewal_sha256", "old_operational_source_manifest", "new_operational_source_manifest"}
            _require(set(value) == required | recovery and value.get("execution_source_sha256") != prior_source,
                     "Continuation binding differs")
        reviewed_at, expires_at = _time(value.get("reviewed_at"), "Continuation review time"), _time(value.get("expires_at"), "Continuation expiry")
        _require(reviewed_at < expires_at <= reviewed_at + timedelta(hours=2), "Continuation review window differs")
        prefix = value.get("completed_prefix")
        _require(isinstance(prefix, Mapping) and set(prefix) == {"ordinals", "contacts", "run_files", "run_tree_sha256"}
                 and isinstance(prefix["ordinals"], list) and (version in {2, 3} or prefix["ordinals"])
                 and isinstance(prefix["contacts"], list) and len(prefix["contacts"]) == len(prefix["ordinals"])
                 and isinstance(prefix["run_files"], Mapping)
                 and _hash(_canonical(prefix["run_files"])) == prefix["run_tree_sha256"]
                 and (version != 3 or not prefix["ordinals"] and not prefix["contacts"]), "Continuation prefix differs")
        prior_authorization, prior_source = _hash(raw), value["execution_source_sha256"]
        result.append({"sha256": prior_authorization, "value": value, "reviewed_at": reviewed_at,
                       "expires_at": expires_at, "start": reviewed_at, "end": expires_at,
                       "source_sha256": prior_source, "version": version})
    return result


def _cohort_state(public_inputs_raw: bytes, plan_raw: bytes, execution_root: Path, initialization: Mapping[str, Any],
                  ledger: ModuleType, number: int, ordinals: tuple[int, ...], expected_previous_settlement_sha256: str,
                  expected_prepared_sha256: str, expected_review_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    route_raw = _relative(execution_root, f"cohorts/{number:04d}/route.json", directory=False).read_bytes()
    route = _json(route_raw, "Cohort route")
    files = {f"cohorts/{number:04d}/prepared.json", f"cohorts/{number:04d}/route.json", f"cohorts/{number:04d}/review.json"}
    contacts = execution_root / "contacts"
    if contacts.exists():
        files.update(f"contacts/{path.name}" for path in contacts.glob("request-*.json")
                     if (match := re.fullmatch(r"request-(\d{4})\.json", path.name)) and int(match.group(1)) in ordinals)
    continuation_root = execution_root / "cohorts" / f"{number:04d}" / "review-continuations"
    if continuation_root.exists():
        files.update(f"cohorts/{number:04d}/review-continuations/{path.name}" for path in continuation_root.glob("*.json"))
    prior = ledger.verify_prefix(execution_root, public_inputs_raw, plan_raw, initialization["plan_sha256"],
                                 expected_previous_settlement_sha256, number - 1,
                                 expected_route_sha256=initialization["route_sha256"],
                                 expected_execution_source_sha256=initialization["execution_source_sha256"],
                                 expected_reviewer_task=REVIEWER_TASK, allowed_pending_paths=frozenset(files))
    prepared_candidate = _json(_relative(execution_root, f"cohorts/{number:04d}/prepared.json", directory=False).read_bytes(),
                               "Prepared cohort")
    prepared_epoch = _epoch(initialization, prior, prepared_candidate.get("operational_renewal_sha256"),
                            apply_precontact_recovery=False)
    epoch = _epoch(initialization, prior, prepared_candidate.get("operational_renewal_sha256"))
    _require(_route_hash(route) == prepared_epoch["route_sha256"]
             and (prepared_epoch["route"] is None or _canonical(route) == _canonical(prepared_epoch["route"])),
             "Cohort route binding differs")
    prepared, _prepared_raw = _prepared(execution_root, number, expected_prepared_sha256, initialization, ordinals,
                                         expected_previous_settlement_sha256, route, prepared_epoch)
    review_raw = _relative(execution_root, f"cohorts/{number:04d}/review.json", directory=False).read_bytes()
    _require(_hash(review_raw) == expected_review_sha256, "Review anchor differs")
    review = _json(review_raw, "Review")
    _require(set(review) == {"schema_version", "reviewer_task", "decision", "prepared_sha256", "reviewed_at", "expires_at"}
             and review.get("schema_version") == 1 and review.get("reviewer_task") == REVIEWER_TASK
             and review.get("decision") == "approved_cohort" and review.get("prepared_sha256") == expected_prepared_sha256,
             "Cohort review differs")
    review_start, review_end = _time(review.get("reviewed_at"), "Review time"), _time(review.get("expires_at"), "Review expiry")
    _require(review_start < review_end <= review_start + timedelta(hours=2), "Review window differs")
    if expected_previous_settlement_sha256 != "0" * 64:
        previous_raw = _relative(execution_root, f"cohorts/{number - 1:04d}/settlement.json", directory=False).read_bytes()
        _require(_hash(previous_raw) == expected_previous_settlement_sha256, "Previous baseline settlement differs")
        previous = _json(previous_raw, "Previous settlement")
        _require(review_start >= _time(previous.get("settled_at"), "Previous settlement time"),
                 "Review precedes previous settlement")
    continuations = _continuations(execution_root, number, expected_prepared_sha256, expected_review_sha256,
                                   prepared_epoch["route_sha256"], prepared_epoch["execution_source_sha256"])
    review["_window"] = (review_start, review_end)
    return prepared, route, review, continuations, prior, epoch


def _contact_prefix(execution_root: Path, ordinals: tuple[int, ...]) -> list[int]:
    contacts = execution_root / "contacts"
    paths = sorted(contacts.glob("request-*.json")) if contacts.exists() else []
    values: list[int] = []
    for path in paths:
        match = re.fullmatch(r"request-(\d{4})\.json", path.name)
        _require(match is not None, "Contact inventory differs")
        ordinal = int(match.group(1))
        _require(ordinal < ordinals[0] or ordinal in ordinals, "Contact lies outside cohort prefix")
        if ordinal in ordinals:
            values.append(ordinal)
    _require(values == list(ordinals[:len(values)]), "Contact prefix differs")
    return values


def _validate_approval_chronology(execution_root: Path, ordinals: tuple[int, ...], review_sha256: str, review: Mapping[str, Any],
                                  continuations: list[dict[str, Any]], *,
                                  replayed_contacts: list[dict[str, Any]] | None = None) -> None:
    """Require the pending approval chain to remain settlement-valid before another contact."""
    review_start, review_end = review["_window"]
    authorizations = [{"sha256": review_sha256, "reviewed_at": review_start,
                       "expires_at": review_end, "ordinals": []}]
    prior_reviewed_at = review_start
    for continuation in continuations:
        _require(continuation["reviewed_at"] >= prior_reviewed_at, "Continuation review order differs")
        authorizations.append({"sha256": continuation["sha256"], "reviewed_at": continuation["reviewed_at"],
                               "expires_at": continuation["expires_at"], "ordinals": []})
        prior_reviewed_at = continuation["reviewed_at"]
    by_authorization = {item["sha256"]: item for item in authorizations}
    completed = _contact_prefix(execution_root, ordinals)
    admitted_at: dict[int, datetime] = {}
    for ordinal in completed:
        contact = _json(_relative(execution_root, f"contacts/request-{ordinal:04d}.json", directory=False).read_bytes(),
                        "Contact")
        authorization = contact.get("review_sha256")
        _require(authorization in by_authorization, "Contact authorization differs")
        when = _time(contact.get("admitted_at"), "Contact admission")
        window = by_authorization[authorization]
        _require(window["reviewed_at"] <= when <= window["expires_at"], "Contact lies outside authorization")
        window["ordinals"].append(ordinal)
        admitted_at[ordinal] = when
    _require([ordinal for item in authorizations for ordinal in item["ordinals"]] == completed,
             "Settlement authorization order differs")
    completed_before = 0
    for index, continuation in enumerate(continuations):
        completed_before += len(authorizations[index]["ordinals"])
        prefix = continuation["value"]["completed_prefix"]
        prefix_ordinals = prefix["ordinals"]
        _require(prefix_ordinals == list(ordinals[:completed_before]) and completed_before < len(ordinals),
                  "Continuation prefix ordinals differ")
        if completed_before:
            _require(continuation["reviewed_at"] >= max(admitted_at[ordinal] for ordinal in prefix_ordinals),
                     "Continuation review precedes completed prefix")
        if not authorizations[index]["ordinals"]:
            _require(continuation["reviewed_at"] >= authorizations[index]["expires_at"],
                     "Unused authorization renewal differs")
        if replayed_contacts is not None:
            _require(prefix["contacts"] == replayed_contacts[:completed_before], "Continuation prefix contact differs")


def _frozen_payloads(plan_root: Path, requests: Mapping[int, Mapping[str, Any]], passes: Mapping[str, Mapping[str, Any]],
                     ordinals: tuple[int, ...]) -> dict[Path, bytes]:
    result: dict[Path, bytes] = {}
    for ordinal in ordinals:
        request = requests[ordinal]
        passed = passes[request["pass_id"]]
        for relative, expected_hash, expected_bytes in (
            (request["prompt_path"], request["prompt_sha256"], request["prompt_bytes"]),
            (request["schema_path"], request["schema_sha256"], request["schema_bytes"]),
            (passed["input_path"], passed["source_sha256"], passed["source_bytes"]),
        ):
            path = _relative(plan_root, relative, directory=False)
            raw = path.read_bytes()
            _require(_hash(raw) == expected_hash and len(raw) == expected_bytes, "Frozen payload commitment differs")
            result[path] = raw
    return result


def _trusted_identities(admission: ModuleType, captured: Mapping[Path, bytes]) -> tuple[frozenset[str], frozenset[str]]:
    value = admission._trusted_identities(captured[TERMINAL_IDENTITIES])
    _require(isinstance(value, tuple) and len(value) == 2 and all(isinstance(item, frozenset) and len(item) == 33 for item in value),
             "Trusted predecessor identities differ")
    return value


def _execution_snapshot(root: Path) -> tuple[dict[str, str], frozenset[str]]:
    files: dict[str, str] = {}
    directories: set[str] = set()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == ".launch.lock":
            continue
        if path.is_dir():
            directories.add(relative)
        elif path.is_file():
            files[relative] = _hash(path.read_bytes())
        else:
            raise ValueError("Execution snapshot contains a non-regular entry")
    return files, frozenset(directories)


def _run_files(execution_root: Path) -> dict[str, str]:
    return {path.relative_to(execution_root).as_posix(): _hash(path.read_bytes())
            for path in sorted((execution_root / "runs").rglob("*")) if path.is_file()} if (execution_root / "runs").is_dir() else {}


def _validate_latest_continuation_evidence(continuations: list[dict[str, Any]], completed: list[int],
                                           contacts: list[dict[str, Any]], files: Mapping[str, str],
                                           aggregates: Mapping[str, bytes],
                                           prefix_aggregates: Mapping[str, bytes]) -> None:
    if not continuations:
        return
    prefix = continuations[-1]["value"]["completed_prefix"]
    prefix_ordinals = prefix["ordinals"]
    prefix_length = len(prefix_ordinals)
    _require(prefix_ordinals == completed[:prefix_length] and prefix["contacts"] == contacts[:prefix_length]
             and prefix["run_tree_sha256"] == _hash(_canonical(prefix["run_files"])),
             "Continuation completed evidence differs")
    _require(set(prefix["run_files"]).issubset(files), "Continuation completed evidence differs")
    for path, previous_hash in prefix["run_files"].items():
        if files.get(path) == previous_hash:
            continue
        old, current = prefix_aggregates.get(path), aggregates.get(path)
        _require(old is not None and current is not None and _hash(old) == previous_hash and current.startswith(old)
                 and files.get(path) == _hash(current), "Continuation completed evidence differs")
    if prefix_length == len(completed):
        _require(prefix["run_files"] == files, "Continuation completed evidence differs")


def _normalized_verdicts(run_root: Path, source_raw: bytes, runtime: Any, admitted: Mapping[str, Any]) -> list[dict[str, Any]]:
    verdicts, count, head = runtime.runner._load_checkpoints(
        run_root, artifact_text=source_raw.decode("utf-8"), context_texts=[], batch_attempts=1)
    projected = [{"question_id": verdict["question_id"], "verdict": verdict["verdict"]} for verdict in verdicts]
    _require(projected == admitted["verdicts"] and count == len(admitted["native_identities"])
             and head == admitted["checkpoint_head_sha256"]
             and ("accepted_count" not in admitted or admitted["accepted_count"] == len(verdicts)),
             "Native normalized verdict binding differs")
    return verdicts


def _replay_completed_prefix(execution_root: Path, plan_root: Path, ordinals: list[int],
                             passes: Mapping[str, Mapping[str, Any]], requests: Mapping[int, Mapping[str, Any]],
                             all_requests: Mapping[int, Mapping[str, Any]],
                             runtime: Any, native: ModuleType, admission: ModuleType,
                             captured: Mapping[Path, bytes], prior: Mapping[str, Any], route: Mapping[str, Any],
                             route_sha256: str) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, bytes]]:
    trusted_requests, trusted_sessions = _trusted_identities(admission, captured)
    seen_requests, seen_sessions = set(trusted_requests), set(trusted_sessions)
    for contact in prior["contacts"].values():
        seen_requests.add(contact["request_id_hash"])
        seen_sessions.add(contact["session_id_hash"])
    replayed: dict[str, Any] = {}
    aggregates: dict[str, bytes] = {}
    contacts: list[dict[str, Any]] = []
    for ordinal in ordinals:
        request, record = requests[ordinal], passes[requests[ordinal]["pass_id"]]
        admitted = replayed.get(record["pass_id"])
        if admitted is None:
            endpoint = max(item for item in ordinals if requests[item]["pass_id"] == record["pass_id"])
            source_path, source_raw = _source(record, plan_root)
            response_root = _relative(execution_root, record["run_path"], directory=True) / "responses"
            actual_batches = len(list(response_root.glob("batch-*.json")))
            _require(actual_batches >= requests[endpoint]["batch_number"], "Native checkpoint prefix differs")
            admitted = native.admit_prefix(
                _relative(execution_root, record["run_path"], directory=True),
                source={"opaque_story_id": record["logical_sample_id"], "story_text": source_raw.decode("utf-8"),
                        "artifact_path": str(source_path), "source_opaque_story_id": record["opaque_story_id"]},
                batch_size=8, expected_batches=actual_batches,
                approved_routes={**prior["routes"], route_sha256: route}, runtime=runtime)
            replayed[record["pass_id"]] = admitted
            aggregate_path = f"{record['run_path']}/verdicts.jsonl"
            normalized = _normalized_verdicts(
                _relative(execution_root, record["run_path"], directory=True), source_raw, runtime, admitted)
            complete = runtime.runner._verdicts_bytes(normalized)
            _require(_relative(execution_root, aggregate_path, directory=False).read_bytes() == complete,
                     "Native verdict aggregate differs")
            prefix_size = sum(len(item["question_ids"]) for item in all_requests.values()
                              if item["pass_id"] == record["pass_id"]
                              and item["batch_number"] <= requests[endpoint]["batch_number"])
            aggregates[aggregate_path] = runtime.runner._verdicts_bytes(normalized[:prefix_size])
        identity = admitted["native_identities"][request["batch_number"] - 1]
        _require(identity["request_id_hash"] not in seen_requests and identity["session_id_hash"] not in seen_sessions,
                 "Native identity collides with trusted or settled evidence")
        seen_requests.add(identity["request_id_hash"])
        seen_sessions.add(identity["session_id_hash"])
        contact_raw = _relative(execution_root, f"contacts/request-{ordinal:04d}.json", directory=False).read_bytes()
        checkpoint = _relative(execution_root / record["run_path"], f"responses/batch-{request['batch_number']:04d}.json", directory=False).read_bytes()
        contacts.append({"ordinal": ordinal, "contact_sha256": _hash(contact_raw), "checkpoint_sha256": _hash(checkpoint),
                         "request_id_hash": identity["request_id_hash"], "session_id_hash": identity["session_id_hash"]})
    return contacts, _run_files(execution_root), aggregates


def _reconstruct_aggregate_prefixes(execution_root: Path, plan_root: Path, ordinals: list[int],
                                    passes: Mapping[str, Mapping[str, Any]], requests: Mapping[int, Mapping[str, Any]],
                                    runtime: Any, native: ModuleType, routes: Mapping[str, Mapping[str, Any]]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    selected = {ordinal: requests[ordinal] for ordinal in ordinals}
    for pass_id in dict.fromkeys(request["pass_id"] for request in selected.values()):
        record = passes[pass_id]
        endpoint = max(request["batch_number"] for request in selected.values() if request["pass_id"] == pass_id)
        source_path, source_raw = _source(record, plan_root)
        response_root = _relative(execution_root, record["run_path"], directory=True) / "responses"
        actual_batches = len(list(response_root.glob("batch-*.json")))
        _require(actual_batches >= endpoint, "Native checkpoint prefix differs")
        admitted = native.admit_prefix(
            _relative(execution_root, record["run_path"], directory=True),
            source={"opaque_story_id": record["logical_sample_id"], "story_text": source_raw.decode("utf-8"),
                    "artifact_path": str(source_path), "source_opaque_story_id": record["opaque_story_id"]},
            batch_size=8, expected_batches=actual_batches, approved_routes=routes, runtime=runtime)
        aggregate_path = f"{record['run_path']}/verdicts.jsonl"
        normalized = _normalized_verdicts(
            _relative(execution_root, record["run_path"], directory=True), source_raw, runtime, admitted)
        complete = runtime.runner._verdicts_bytes(normalized)
        _require(_relative(execution_root, aggregate_path, directory=False).read_bytes() == complete,
                 "Native verdict aggregate differs")
        prefix_size = sum(len(request["question_ids"]) for request in requests.values()
                          if request["pass_id"] == pass_id and request["batch_number"] <= endpoint)
        result[aggregate_path] = runtime.runner._verdicts_bytes(normalized[:prefix_size])
    return result


def _verify_new_renewal_boundary(execution_root: Path, plan_root: Path, prior: Mapping[str, Any],
                                 renewal: Mapping[str, Any], passes: Mapping[str, Mapping[str, Any]],
                                 requests: Mapping[int, Mapping[str, Any]], runtime: Any, native: ModuleType) -> None:
    files, _ = _execution_snapshot(execution_root)
    record_path = f"cohorts/{renewal['cohort_number']:04d}/operational-renewals/0001.json"
    _require(record_path in files, "Operational renewal record is missing")
    files.pop(record_path)
    manifest = renewal["manifest"]
    immutable, aggregates = manifest["immutable_files"], manifest["derived_aggregate_prefixes"]
    _require(set(files) == set(immutable) | set(aggregates) and set(immutable).isdisjoint(aggregates)
             and all(files[path] == sha256 for path, sha256 in immutable.items()),
             "Operational renewal immutable prefix differs")
    reconstructed = _reconstruct_aggregate_prefixes(
        execution_root, plan_root, sorted(prior["contacts"]), passes, requests, runtime, native, prior["routes"])
    _require(set(aggregates) == set(reconstructed), "Operational renewal aggregate prefix differs")
    for path, value in aggregates.items():
        aggregate = reconstructed[path]
        _require(files[path] == _hash(aggregate) == value["sha256"] and len(aggregate) == value["bytes"]
                 and aggregate.count(b"\n") == value["verdict_count"], "Operational renewal aggregate prefix differs")


def _prepare_continuation_unlocked(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int, *,
                         expected_plan_sha256: str, expected_initialization_sha256: str,
                         expected_previous_settlement_sha256: str, expected_prepared_sha256: str,
                         expected_review_sha256: str, expected_source_sha256: str,
                         expected_operational_renewal_sha256: str | None = None,
                         expected_precontact_recovery_sha256: str | None = None) -> dict[str, Any]:
    """Build a provider-free candidate for an independent continuation review."""
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_HASH.fullmatch(value) is not None for value in
             (expected_initialization_sha256, expected_previous_settlement_sha256, expected_prepared_sha256,
              expected_review_sha256, expected_source_sha256)), "Continuation anchors differ")
    _require(expected_operational_renewal_sha256 is None or _HASH.fullmatch(expected_operational_renewal_sha256) is not None,
             "Continuation operational renewal anchor differs")
    _require(expected_precontact_recovery_sha256 is None or _HASH.fullmatch(expected_precontact_recovery_sha256) is not None,
             "Continuation precontact recovery anchor differs")
    captured, (_, ledger, runtime_loader, native, admission) = _sources()
    own = _plain(Path(__file__), directory=False)
    _require(_hash(captured[own]) == expected_source_sha256, "Reviewed execution source differs")
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    execution_root = _plain(execution_root, directory=True)
    initialization, initialization_raw = _initialization(execution_root, expected_initialization_sha256)
    _require(_hash(public_inputs_path.read_bytes()) == initialization["public_inputs_sha256"],
             "Initialization continuation binding differs")
    plan, plan_raw = _plan(plan_root, expected_plan_sha256)
    all_requests = {row["ordinal"]: row for row in plan["requests"]
                    if isinstance(row, Mapping) and type(row.get("ordinal")) is int}
    _require(set(all_requests) == set(range(1, len(plan["requests"]) + 1)), "Full baseline request inventory differs")
    all_passes = {row["pass_id"]: row for row in plan["passes"]
                  if isinstance(row, Mapping) and isinstance(row.get("pass_id"), str)}
    _require(len(all_passes) == len(plan["passes"]), "Full baseline pass inventory differs")
    ordinals = _groups(ledger, plan, cohort_number)
    prepared, route, _review, continuations, prior, epoch = _cohort_state(
        public_inputs_path.read_bytes(), plan_raw, execution_root, initialization, ledger, cohort_number, ordinals,
        expected_previous_settlement_sha256, expected_prepared_sha256, expected_review_sha256,
    )
    _require(epoch["execution_source_sha256"] == expected_source_sha256
             and prepared.get("operational_renewal_sha256") == expected_operational_renewal_sha256
             and epoch.get("precontact_recovery_sha256") == expected_precontact_recovery_sha256,
             "Prepared operational epoch differs")
    completed = _contact_prefix(execution_root, ordinals)
    _validate_approval_chronology(execution_root, ordinals, expected_review_sha256, _review, continuations)
    _require(len(completed) < len(ordinals), "Continuation requires an incomplete cohort")
    runtime = runtime_loader.load_runtime(
        ROOT / "baseline-runtime-v1.json", expected_manifest_sha256=initialization["runtime_manifest_sha256"])
    runtime.verify()
    passes, requests = _rows(plan, plan_root, ordinals)
    _frozen_payloads(plan_root, requests, passes, ordinals)
    contacts, files, aggregates = _replay_completed_prefix(execution_root, plan_root, completed, passes, requests, all_requests, runtime, native,
                                                            admission, captured, prior, route, prepared["route_sha256"])
    prefix_aggregates: dict[str, bytes] = {}
    if continuations:
        prefix_ordinals = sorted({*prior["contacts"], *continuations[-1]["value"]["completed_prefix"]["ordinals"]})
        prefix_aggregates = _reconstruct_aggregate_prefixes(
            execution_root, plan_root, prefix_ordinals, all_passes, all_requests, runtime, native,
            {**prior["routes"], prepared["route_sha256"]: route})
    _validate_latest_continuation_evidence(continuations, completed, contacts, files, aggregates, prefix_aggregates)
    prior_authorization = continuations[-1]["sha256"] if continuations else expected_review_sha256
    candidate = {"schema_version": 2, "reviewer_task": REVIEWER_TASK, "decision": "approved_continuation",
                 "prepared_sha256": expected_prepared_sha256, "route_sha256": prepared["route_sha256"],
                 "prior_authorization_sha256": prior_authorization,
                 "previous_execution_source_sha256": expected_source_sha256,
                 "execution_source_sha256": expected_source_sha256,
                 "completed_prefix": {"ordinals": completed, "contacts": contacts, "run_files": files,
                                      "run_tree_sha256": _hash(_canonical(files))}}
    runtime.verify()
    _unchanged(captured)
    _require(_relative(execution_root, "initialization.json", directory=False).read_bytes() == initialization_raw,
             "Initialization changed during continuation preparation")
    return candidate


def prepare_continuation(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int, *,
                         expected_plan_sha256: str, expected_initialization_sha256: str,
                         expected_previous_settlement_sha256: str, expected_prepared_sha256: str,
                         expected_review_sha256: str, expected_source_sha256: str,
                         expected_operational_renewal_sha256: str | None = None,
                         expected_precontact_recovery_sha256: str | None = None) -> dict[str, Any]:
    root = _plain(execution_root, directory=True)
    lock, token = _lock(root)
    before = _execution_snapshot(root)
    try:
        result = _prepare_continuation_unlocked(
            public_inputs_path, plan_root, root, cohort_number, expected_plan_sha256=expected_plan_sha256,
            expected_initialization_sha256=expected_initialization_sha256,
            expected_previous_settlement_sha256=expected_previous_settlement_sha256,
            expected_prepared_sha256=expected_prepared_sha256, expected_review_sha256=expected_review_sha256,
            expected_source_sha256=expected_source_sha256,
            expected_operational_renewal_sha256=expected_operational_renewal_sha256,
            expected_precontact_recovery_sha256=expected_precontact_recovery_sha256)
        _require(_execution_snapshot(root) == before, "Execution evidence changed during continuation preparation")
        _require(lock.is_file() and lock.read_bytes() == token, "Continuation lock ownership changed")
        return result
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()


def _fresh_route(broker: Any, route: Mapping[str, Any]) -> None:
    live = broker._grok_native_route(route["name"])
    _require(isinstance(live, Mapping) and _canonical(dict(live)) == _canonical(dict(route)),
             "Broker route is no longer exact")


def _settle_completed_cohort(execution_root: Path, plan_root: Path, public_inputs_raw: bytes, plan_raw: bytes,
                             cohort_number: int, ordinals: tuple[int, ...], initialization: Mapping[str, Any],
                             expected_plan_sha256: str, expected_previous_settlement_sha256: str,
                             expected_prepared_sha256: str, expected_review_sha256: str,
                             expected_source_sha256: str, route: Mapping[str, Any], route_sha256: str, review: Mapping[str, Any],
                             continuations: list[dict[str, Any]], prior: Mapping[str, Any], passes: Mapping[str, Mapping[str, Any]],
                             requests: Mapping[int, Mapping[str, Any]], runtime: Any, native: ModuleType,
                             admission: ModuleType, captured: Mapping[Path, bytes], ledger: ModuleType,
                             provider_calls: int, lock_owned: Any) -> dict[str, Any]:
    """Replay a fully contacted cohort and settle it without another provider contact."""
    lock_owned()
    all_requests = {row["ordinal"]: row for row in _json(plan_raw, "Baseline plan")["requests"]
                    if isinstance(row, Mapping) and type(row.get("ordinal")) is int}
    _require(set(all_requests) == set(range(1, len(all_requests) + 1)), "Full baseline request inventory differs")
    contacts, _, _ = _replay_completed_prefix(execution_root, plan_root, list(ordinals), passes, requests, all_requests, runtime, native,
                                               admission, captured, prior, route, route_sha256)
    original_source_sha256 = continuations[0]["value"]["previous_execution_source_sha256"] if continuations else expected_source_sha256
    authorizations = [{"authorization_sha256": expected_review_sha256, "execution_source_sha256": original_source_sha256, "ordinals": []},
                      *[{"authorization_sha256": item["sha256"], "execution_source_sha256": item["source_sha256"], "ordinals": []}
                         for item in continuations]]
    by_authorization = {item["authorization_sha256"]: item for item in authorizations}
    for summary in contacts:
        contact = _json(_relative(execution_root, f"contacts/request-{summary['ordinal']:04d}.json", directory=False).read_bytes(), "Contact")
        authorization = contact.get("review_sha256")
        _require(authorization in by_authorization, "Completed contact authorization differs")
        by_authorization[authorization]["ordinals"].append(summary["ordinal"])
    settlement = {"schema_version": 3, "cohort_number": cohort_number, "plan_sha256": expected_plan_sha256,
                   "prepared_sha256": expected_prepared_sha256, "review_sha256": expected_review_sha256,
                   "route_sha256": route_sha256,
                   "previous_settlement_sha256": expected_previous_settlement_sha256,
                   "settled_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                   "contacts": contacts, "authorization_chain": authorizations}
    contact_records = {ordinal: _relative(execution_root, f"contacts/request-{ordinal:04d}.json", directory=False).read_bytes()
                       for ordinal in ordinals}
    ledger.validate_candidate_cohort(
        public_inputs_raw, plan_raw, expected_plan_sha256, cohort_number=cohort_number, ordinals=ordinals,
        prepared_sha256=expected_prepared_sha256, review_sha256=expected_review_sha256,
        route_sha256=route_sha256, previous_settlement_sha256=expected_previous_settlement_sha256,
        review_start=review["_window"][0], review_end=review["_window"][1], continuations=continuations,
        settlement=settlement, contact_records=contact_records,
        expected_execution_source_sha256=original_source_sha256,
    )
    lock_owned()
    _write_new(execution_root / "cohorts" / f"{cohort_number:04d}" / "settlement.json", _canonical(settlement))
    settlement_sha256 = _hash((execution_root / "cohorts" / f"{cohort_number:04d}" / "settlement.json").read_bytes())
    ledger.verify_prefix(execution_root, public_inputs_raw, plan_raw, expected_plan_sha256, settlement_sha256, cohort_number,
                         expected_route_sha256=initialization["route_sha256"],
                         expected_execution_source_sha256=initialization["execution_source_sha256"], expected_reviewer_task=REVIEWER_TASK)
    runtime.verify()
    _unchanged(captured)
    lock_owned()
    return {"cohort_number": cohort_number, "status": "settled", "settlement_sha256": settlement_sha256,
            "provider_calls": provider_calls, "execution_source_sha256": expected_source_sha256}


def run_cohort(public_inputs_path: Path, plan_root: Path, execution_root: Path, cohort_number: int, queue_root: Path,
               broker_factory: Any | None = None, *, expected_plan_sha256: str, expected_initialization_sha256: str,
               expected_previous_settlement_sha256: str, expected_prepared_sha256: str,
               expected_review_sha256: str, expected_source_sha256: str,
               expected_continuation_sha256: str | None = None,
               expected_operational_renewal_sha256: str | None = None,
               expected_precontact_recovery_sha256: str | None = None) -> dict[str, Any]:
    """Contact Grok only under an externally reviewed, still-live cohort authorization."""
    anchors = (expected_initialization_sha256, expected_previous_settlement_sha256, expected_prepared_sha256,
               expected_review_sha256, expected_source_sha256)
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_HASH.fullmatch(value) is not None for value in anchors)
             and (expected_continuation_sha256 is None or _HASH.fullmatch(expected_continuation_sha256) is not None)
             and (expected_operational_renewal_sha256 is None or _HASH.fullmatch(expected_operational_renewal_sha256) is not None)
             and (expected_precontact_recovery_sha256 is None or _HASH.fullmatch(expected_precontact_recovery_sha256) is not None),
             "Execution anchors differ")
    captured, (_, ledger, runtime_loader, native, admission) = _sources()
    own = _plain(Path(__file__), directory=False)
    _require(_hash(captured[own]) == expected_source_sha256, "Reviewed execution source differs")
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    execution_root = _plain(execution_root, directory=True)
    queue_root = _plain(queue_root, directory=True)
    _require(all(not queue_root.is_relative_to(protected) and not protected.is_relative_to(queue_root)
                 for protected in (public_inputs_path.parent, plan_root, execution_root, REPOSITORY)),
             "Queue root overlaps baseline evidence")
    lock, token = _lock(execution_root)
    try:
        def lock_owned() -> None:
            _require(lock.is_file() and lock.read_bytes() == token, "Execution lock ownership changed")

        initialization, initialization_raw = _initialization(execution_root, expected_initialization_sha256)
        _require(_hash(public_inputs_path.read_bytes()) == initialization["public_inputs_sha256"],
                 "Initialization execution binding differs")
        plan, plan_raw = _plan(plan_root, expected_plan_sha256)
        ordinals = _groups(ledger, plan, cohort_number)
        _prepared, route, review, continuations, prior, epoch = _cohort_state(
            public_inputs_path.read_bytes(), plan_raw, execution_root, initialization, ledger, cohort_number, ordinals,
            expected_previous_settlement_sha256, expected_prepared_sha256, expected_review_sha256,
        )
        _require(epoch["execution_source_sha256"] == expected_source_sha256
                 and _prepared.get("operational_renewal_sha256") == expected_operational_renewal_sha256
                 and epoch.get("precontact_recovery_sha256") == expected_precontact_recovery_sha256,
                 "Prepared operational epoch differs")
        completed = _contact_prefix(execution_root, ordinals)
        _validate_approval_chronology(execution_root, ordinals, expected_review_sha256, review, continuations)
        if completed and len(completed) < len(ordinals) and expected_continuation_sha256 is None:
            lock_owned()
            return {"cohort_number": cohort_number, "completed_ordinals": completed,
                    "status": "paused_for_continuation_review", "provider_calls": 0}
        if completed and len(completed) < len(ordinals):
            _require(continuations and continuations[-1]["sha256"] == expected_continuation_sha256,
                     "Continuation authorization differs")
            authorization_sha256 = expected_continuation_sha256
            authorization_window = (continuations[-1]["reviewed_at"], continuations[-1]["expires_at"])
        elif completed:
            if continuations:
                _require(continuations[-1]["sha256"] == expected_continuation_sha256,
                         "Completed cohort continuation anchor differs")
                authorization_sha256 = expected_continuation_sha256
                authorization_window = (continuations[-1]["reviewed_at"], continuations[-1]["expires_at"])
            else:
                _require(expected_continuation_sha256 is None, "Completed cohort continuation anchor differs")
                authorization_sha256 = expected_review_sha256
                authorization_window = review["_window"]
        else:
            if continuations:
                required_anchor = (expected_precontact_recovery_sha256 if continuations[-1]["version"] == 3
                                   else expected_continuation_sha256)
                _require(continuations[-1]["sha256"] == required_anchor,
                         "Continuation authorization differs")
                authorization_sha256 = required_anchor
                authorization_window = (continuations[-1]["reviewed_at"], continuations[-1]["expires_at"])
            else:
                _require(expected_continuation_sha256 is None, "Unexpected continuation authorization")
                authorization_sha256 = expected_review_sha256
                authorization_window = review["_window"]
        if len(completed) < len(ordinals) and not authorization_window[0] <= datetime.now(timezone.utc) <= authorization_window[1]:
            lock_owned()
            return {"cohort_number": cohort_number, "completed_ordinals": completed,
                    "status": "paused_for_review_expiry", "provider_calls": 0}
        runtime = runtime_loader.load_runtime(ROOT / "baseline-runtime-v1.json",
                                              expected_manifest_sha256=initialization["runtime_manifest_sha256"])
        runtime.verify()
        passes, requests = _rows(plan, plan_root, ordinals)
        all_requests = {row["ordinal"]: row for row in plan["requests"]
                        if isinstance(row, Mapping) and type(row.get("ordinal")) is int}
        _require(set(all_requests) == set(range(1, 5429)), "Full baseline request inventory differs")
        all_passes = {row["pass_id"]: row for row in plan["passes"]
                      if isinstance(row, Mapping) and isinstance(row.get("pass_id"), str)}
        _require(len(all_passes) == len(plan["passes"]), "Full baseline pass inventory differs")
        payloads = _frozen_payloads(plan_root, requests, passes, ordinals)
        replayed_contacts, replayed_files, replayed_aggregates = _replay_completed_prefix(
            execution_root, plan_root, completed, passes, requests, all_requests, runtime, native, admission, captured, prior,
            route, _prepared["route_sha256"])
        _validate_approval_chronology(execution_root, ordinals, expected_review_sha256, review, continuations,
                                      replayed_contacts=replayed_contacts)
        if len(completed) == len(ordinals):
            return _settle_completed_cohort(
                execution_root, plan_root, public_inputs_path.read_bytes(), plan_raw, cohort_number, ordinals, initialization,
                expected_plan_sha256, expected_previous_settlement_sha256, expected_prepared_sha256, expected_review_sha256,
                expected_source_sha256, route, _prepared["route_sha256"], review, continuations, prior, passes, requests, runtime, native, admission,
                captured, ledger, 0, lock_owned)
        prefix_aggregates: dict[str, bytes] = {}
        if continuations:
            prefix_ordinals = sorted({*prior["contacts"], *continuations[-1]["value"]["completed_prefix"]["ordinals"]})
            prefix_aggregates = _reconstruct_aggregate_prefixes(
                execution_root, plan_root, prefix_ordinals, all_passes, all_requests, runtime, native,
                {**prior["routes"], _prepared["route_sha256"]: route})
        _validate_latest_continuation_evidence(continuations, completed, replayed_contacts, replayed_files,
                                               replayed_aggregates, prefix_aggregates)
        factory = broker_factory or (lambda root, cls: cls(root))
        _require(callable(factory), "Broker factory differs")
        broker = factory(queue_root, runtime.broker.Broker)
        _require(type(broker) is runtime.broker.Broker and _plain(broker.root, directory=True) == queue_root,
                 "Broker runtime class or queue root differs")
        _fresh_route(broker, route)
        current = set(ordinals[len(completed):])
        immutable_contacts = {ordinal: _relative(execution_root, f"contacts/request-{ordinal:04d}.json", directory=False).read_bytes()
                              for ordinal in completed}
        phase = {"value": "before_contact"}

        def pending_paths() -> frozenset[str]:
            paths = {f"cohorts/{cohort_number:04d}/prepared.json", f"cohorts/{cohort_number:04d}/route.json",
                     f"cohorts/{cohort_number:04d}/review.json"}
            paths.update(f"contacts/request-{ordinal:04d}.json" for ordinal in ordinals
                         if (execution_root / "contacts" / f"request-{ordinal:04d}.json").is_file())
            continuation_root = execution_root / "cohorts" / f"{cohort_number:04d}" / "review-continuations"
            if continuation_root.is_dir():
                paths.update(f"cohorts/{cohort_number:04d}/review-continuations/{path.name}" for path in continuation_root.glob("*.json"))
            return frozenset(paths)

        def frozen_unchanged() -> None:
            lock_owned()
            _require(all(_plain(path, directory=False).read_bytes() == raw for path, raw in payloads.items()),
                     "Frozen baseline payload changed")
            _require(_relative(execution_root, "initialization.json", directory=False).read_bytes() == initialization_raw,
                     "Initialization changed during execution")
            _require(all(_relative(execution_root, f"contacts/request-{ordinal:04d}.json", directory=False).read_bytes() == raw
                         for ordinal, raw in immutable_contacts.items()), "Existing contact changed during execution")
            _require(ledger.verify_prefix(execution_root, public_inputs_path.read_bytes(), plan_raw, expected_plan_sha256,
                                          expected_previous_settlement_sha256, cohort_number - 1,
                                          expected_route_sha256=initialization["route_sha256"],
                                          expected_execution_source_sha256=initialization["execution_source_sha256"],
                                          expected_reviewer_task=REVIEWER_TASK, allowed_pending_paths=pending_paths()) == prior,
                     "Settled ledger prefix changed")
            runtime.verify()
            _fresh_route(broker, route)
            _unchanged(captured)

        def check(context: Mapping[str, Any], *, inner: bool = False) -> None:
            batch = context.get("batch")
            _require(isinstance(batch, Mapping) and type(batch.get("number")) is int, "Runner batch context differs")
            output = Path(context.get("output_dir", "")).resolve()
            pass_id = next((key for key, value in passes.items()
                            if (execution_root / value["run_path"]).resolve() == output), None)
            _require(pass_id is not None, "Runner output path differs")
            planned = next((value for value in all_requests.values()
                            if value.get("pass_id") == pass_id and value.get("batch_number") == batch["number"]), None)
            _require(isinstance(planned, Mapping), "Runner request binding differs")
            if planned["ordinal"] not in current:
                if not inner:
                    raise runtime.runner.RetryDisclosurePause("reviewed cohort boundary")
                raise ValueError("Broker-inner request lies outside reviewed cohort")
            request = requests.get(planned["ordinal"])
            _require(request is planned, "Selected runner request differs")
            prompt = _relative(plan_root, request["prompt_path"], directory=False).read_bytes()
            schema = _relative(plan_root, request["schema_path"], directory=False).read_bytes()
            prompt_record, schema_record = context.get("prompt"), context.get("response_schema")
            _require(isinstance(prompt_record, Mapping) and isinstance(schema_record, Mapping)
                     and prompt_record.get("text", "").encode("utf-8") == prompt
                     and prompt_record.get("sha256") == request["prompt_sha256"] and prompt_record.get("bytes") == request["prompt_bytes"]
                     and isinstance(schema_record.get("text"), str) and schema_record["text"].encode("utf-8") == schema
                     and schema_record.get("sha256") == request["schema_sha256"] and schema_record.get("bytes") == request["schema_bytes"]
                     and batch.get("question_ids") == request["question_ids"]
                     and context.get("attempt", {}).get("number") == 1, "Exact planned payload binding differs")
            frozen_unchanged()
            now = datetime.now(timezone.utc)
            _require(authorization_window[0] <= now <= authorization_window[1], "Review window expired")
            if authorization_window[1] - now < timedelta(seconds=route["timeout_seconds"]):
                if inner:
                    raise ValueError("Review window is too short for another contact")
                raise runtime.runner.RetryDisclosurePause("review window is too short for another contact")
            if inner:
                contact = {"schema_version": 1, "cohort_number": cohort_number, "ordinal": request["ordinal"],
                           "plan_sha256": expected_plan_sha256, "prepared_sha256": expected_prepared_sha256,
                           "review_sha256": authorization_sha256, "route_sha256": _prepared["route_sha256"],
                           "prompt_sha256": request["prompt_sha256"], "schema_sha256": request["schema_sha256"],
                           "admitted_at": now.isoformat().replace("+00:00", "Z")}
                _write_new(execution_root / "contacts" / f"request-{request['ordinal']:04d}.json", _canonical(contact))
                phase["value"] = "inner_admitted"

        def runtime_guard() -> None:
            frozen_unchanged()
            if phase["value"] != "in_flight":
                _require(authorization_window[0] <= datetime.now(timezone.utc) <= authorization_window[1],
                         "Review window expired")
            if phase["value"] == "inner_admitted":
                phase["value"] = "in_flight"

        transport = runtime.transport.bind_grok_broker_transport(
            broker=broker, route=route, before_contact=lambda context: check(context, inner=True), runtime_check=runtime_guard)
        for pass_id in dict.fromkeys(requests[ordinal]["pass_id"] for ordinal in ordinals):
            record = passes[pass_id]
            source_path, _ = _source(record, plan_root)
            destination = execution_root / record["run_path"]
            try:
                runtime.runner.run_judge(
                    artifact_path=source_path, bundle_id="prose.short_story", provider="grok", model="grok-4.6",
                    output_dir=destination, registry=REPOSITORY / "registry/all_modules.json",
                    bundles=REPOSITORY / "bundles/all_bundles.json", question_ids=plan["runtime"]["question_ids"],
                    batch_size=8, batch_attempts=1, reasoning="high", allow_remote=True, resume=destination.exists(),
                    timeout=route["timeout_seconds"], artifact_id=record["logical_sample_id"], judge_id="grok:grok-4.6",
                    allow_unattested_reasoning=True, attempt_lifecycle_policy="terminal_sidecar_v1",
                    before_provider_attempt=check, grok_transport=transport, grok_transport_sha256=runtime.transport_sha256,
                    response_schema_mode="batch_question_ids_v1",
                )
            except runtime.runner.RetryDisclosurePause:
                pass
        completed_after = _contact_prefix(execution_root, ordinals)
        if len(completed_after) < len(ordinals):
            lock_owned()
            return {"cohort_number": cohort_number, "completed_ordinals": completed_after,
                    "status": "paused_for_continuation_review", "provider_calls": len(completed_after) - len(completed)}
        frozen_unchanged()
        return _settle_completed_cohort(
            execution_root, plan_root, public_inputs_path.read_bytes(), plan_raw, cohort_number, ordinals, initialization,
            expected_plan_sha256, expected_previous_settlement_sha256, expected_prepared_sha256, expected_review_sha256,
            expected_source_sha256, route, _prepared["route_sha256"], review, continuations, prior, passes, requests, runtime, native, admission,
            captured, ledger, len(current), lock_owned)
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()


def finalize(public_inputs_path: Path, plan_root: Path, execution_root: Path, runtime_manifest_path: Path, *,
             expected_plan_sha256: str, expected_initialization_sha256: str,
             expected_final_settlement_sha256: str, expected_execution_source_sha256: str,
             expected_runtime_manifest_sha256: str, expected_admission_sha256: str) -> dict[str, Any]:
    """Read-only final native admission after the 543rd cohort has released its lock."""
    anchors = (expected_initialization_sha256, expected_final_settlement_sha256, expected_execution_source_sha256,
               expected_runtime_manifest_sha256, expected_admission_sha256)
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_HASH.fullmatch(value) is not None for value in anchors),
             "Final admission anchors differ")
    captured, (planner, ledger, _, _, admission) = _sources()
    own = _plain(Path(__file__), directory=False)
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    execution_root = _plain(execution_root, directory=True)
    runtime_manifest_path = _plain(runtime_manifest_path, directory=False)
    _require(not (execution_root / ".launch.lock").exists(), "Final admission requires a released execution lock")
    initialization, _ = _initialization(execution_root, expected_initialization_sha256)
    _require(initialization["execution_source_sha256"] == expected_execution_source_sha256
             and initialization["runtime_manifest_sha256"] == expected_runtime_manifest_sha256
             and _hash(public_inputs_path.read_bytes()) == initialization["public_inputs_sha256"],
             "Final initialization binding differs")
    verified = planner.verify(public_inputs_path, plan_root)
    _require(isinstance(verified, dict) and len(verified) == initialization["plan_files"] == 11094
             and verified.get("plan.json") == expected_plan_sha256
             and _hash(_canonical(verified)) == initialization["plan_inventory_sha256"],
             "Final full plan inventory differs")
    _plan_value, plan_raw = _plan(plan_root, expected_plan_sha256)
    ledger_result = ledger.verify_ledger(execution_root, public_inputs_path.read_bytes(), plan_raw, expected_plan_sha256,
                                         expected_final_settlement_sha256, expected_route_sha256=initialization["route_sha256"],
                                         expected_execution_source_sha256=expected_execution_source_sha256,
                                         expected_reviewer_task=REVIEWER_TASK)
    final_source = ledger_result.get("epochs", {}).get(543, {}).get("execution_source_sha256", expected_execution_source_sha256) if isinstance(ledger_result, Mapping) else None
    _require(_hash(captured[own]) == final_source,
             "Final reviewed execution source differs")
    result = admission.admit_baseline(
        public_inputs_path, plan_root, execution_root, runtime_manifest_path,
        expected_plan_sha256=expected_plan_sha256,
        expected_initialization_sha256=expected_initialization_sha256,
        expected_final_settlement_sha256=expected_final_settlement_sha256,
        expected_execution_source_sha256=expected_execution_source_sha256,
        expected_route_sha256=initialization["route_sha256"],
        expected_runtime_manifest_sha256=expected_runtime_manifest_sha256,
        expected_admission_sha256=expected_admission_sha256,
        expected_reviewer_task=REVIEWER_TASK,
    )
    _require(isinstance(result, Mapping) and result.get("evidence_class") == "complete_native_baseline_measurement_admission"
             and result.get("admitted_passes") == 236 and result.get("logical_requests") == 5428,
             "Final native admission result differs")
    _unchanged(captured)
    return dict(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Governed fixed-baseline Dryad cohort collection.")
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("initialize", "prepare", "prepare-precontact-recovery", "prepare-continuation", "run", "finalize"):
        command = commands.add_parser(name)
        command.add_argument("--public-inputs", type=Path, required=True)
        command.add_argument("--plan-root", type=Path, required=True)
        command.add_argument("--execution-root", type=Path, required=True)
        command.add_argument("--plan-sha256", required=True)
        command.add_argument("--initialization-sha256")
        if name == "initialize":
            command.add_argument("--runtime-manifest", type=Path, required=True)
            command.add_argument("--runtime-manifest-sha256", required=True)
            command.add_argument("--route-json", type=Path, required=True)
            command.add_argument("--route-json-sha256", required=True)
        elif name == "finalize":
            command.add_argument("--runtime-manifest", type=Path, required=True)
            command.add_argument("--runtime-manifest-sha256", required=True)
            command.add_argument("--final-settlement-sha256", required=True)
            command.add_argument("--source-sha256", required=True)
            command.add_argument("--admission-sha256", required=True)
        else:
            command.add_argument("--cohort", type=int, required=True)
            command.add_argument("--previous-settlement-sha256", required=True)
            if name == "prepare":
                command.add_argument("--route-json", type=Path, required=True)
                command.add_argument("--operational-renewal-sha256")
            else:
                command.add_argument("--prepared-sha256", required=True)
                command.add_argument("--review-sha256", required=True)
                command.add_argument("--source-sha256", required=True)
                if name in {"prepare-precontact-recovery", "prepare-continuation"}:
                    command.add_argument("--operational-renewal-sha256", required=name == "prepare-precontact-recovery")
                if name == "run":
                    command.add_argument("--queue-root", type=Path, required=True)
                    command.add_argument("--continuation-sha256")
                    command.add_argument("--operational-renewal-sha256")
                if name in {"prepare-continuation", "run"}:
                    command.add_argument("--precontact-recovery-sha256")
    args = parser.parse_args()
    if args.action == "initialize":
        result = initialize(args.public_inputs, args.plan_root, args.execution_root, args.runtime_manifest, args.route_json,
                            expected_plan_sha256=args.plan_sha256,
                            expected_runtime_manifest_sha256=args.runtime_manifest_sha256,
                            expected_route_sha256=args.route_json_sha256)
    elif args.action == "prepare":
        result = prepare_cohort(args.public_inputs, args.plan_root, args.execution_root, args.cohort,
                                _json(_plain(args.route_json, directory=False).read_bytes(), "Route"),
                                expected_plan_sha256=args.plan_sha256,
                                expected_initialization_sha256=args.initialization_sha256,
                                expected_previous_settlement_sha256=args.previous_settlement_sha256,
                                expected_operational_renewal_sha256=args.operational_renewal_sha256)
    elif args.action == "prepare-precontact-recovery":
        result = prepare_precontact_recovery(
            args.public_inputs, args.plan_root, args.execution_root, args.cohort,
            expected_plan_sha256=args.plan_sha256, expected_initialization_sha256=args.initialization_sha256,
            expected_previous_settlement_sha256=args.previous_settlement_sha256,
            expected_prepared_sha256=args.prepared_sha256, expected_review_sha256=args.review_sha256,
            expected_source_sha256=args.source_sha256,
            expected_operational_renewal_sha256=args.operational_renewal_sha256)
    elif args.action == "prepare-continuation":
        result = prepare_continuation(args.public_inputs, args.plan_root, args.execution_root, args.cohort,
                                      expected_plan_sha256=args.plan_sha256,
                                      expected_initialization_sha256=args.initialization_sha256,
                                      expected_previous_settlement_sha256=args.previous_settlement_sha256,
                                      expected_prepared_sha256=args.prepared_sha256, expected_review_sha256=args.review_sha256,
                                      expected_source_sha256=args.source_sha256,
                                      expected_operational_renewal_sha256=args.operational_renewal_sha256,
                                      expected_precontact_recovery_sha256=args.precontact_recovery_sha256)
    elif args.action == "run":
        result = run_cohort(args.public_inputs, args.plan_root, args.execution_root, args.cohort, args.queue_root,
                            expected_plan_sha256=args.plan_sha256, expected_initialization_sha256=args.initialization_sha256,
                            expected_previous_settlement_sha256=args.previous_settlement_sha256,
                            expected_prepared_sha256=args.prepared_sha256, expected_review_sha256=args.review_sha256,
                            expected_source_sha256=args.source_sha256,
                            expected_continuation_sha256=args.continuation_sha256,
                            expected_operational_renewal_sha256=args.operational_renewal_sha256,
                            expected_precontact_recovery_sha256=args.precontact_recovery_sha256)
    else:
        result = finalize(args.public_inputs, args.plan_root, args.execution_root, args.runtime_manifest,
                          expected_plan_sha256=args.plan_sha256, expected_initialization_sha256=args.initialization_sha256,
                          expected_final_settlement_sha256=args.final_settlement_sha256,
                          expected_execution_source_sha256=args.source_sha256,
                          expected_runtime_manifest_sha256=args.runtime_manifest_sha256,
                          expected_admission_sha256=args.admission_sha256)
    print(_canonical(result).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
