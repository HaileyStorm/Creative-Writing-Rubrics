"""Read-only admission for the complete fixed-batch baseline evidence."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import stat
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
PLAN_SOURCE = ROOT / "baseline_measurement_plan.py"
LEDGER_SOURCE = ROOT / "baseline_measurement_ledger.py"
RUNTIME_SOURCE = ROOT / "baseline_native_runtime.py"
NATIVE_SOURCE = ROOT / "native_admission.py"
TERMINAL_IDENTITIES = ROOT / "terminal-identities-v2.json"
SOURCE_PINS = {
    PLAN_SOURCE: "33193aa1a394c04c14b4f9ab81871116dbac11f933f22a9e45f252b2d279fdc8",
    LEDGER_SOURCE: "a7c850d97f6bbac10ba95162e4557570c79e4b9ca9add2abfb3421b10da5b144",
    RUNTIME_SOURCE: "5130bc037e0700f8d498c40ca790aaf248e986189818ae059934ee6488bbfbcd",
    NATIVE_SOURCE: "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec",
    TERMINAL_IDENTITIES: "82cc80c2692fc0c0f47024d4db04cdbf5dd1c34c2d5deea40916a0e8ea45ca63",
}
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _plain(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError as error:
            raise ValueError("Path is missing") from error
        _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                 "Path contains a link or reparse point")
    if directory is True:
        _require(absolute.is_dir(), "Expected a directory")
    if directory is False:
        _require(absolute.is_file(), "Expected a file")
    return absolute


def _relative(root: Path, relative: Any, label: str, *, directory: bool | None = None) -> Path:
    _require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), f"{label} path differs")
    value = Path(relative)
    _require("." not in value.parts and ".." not in value.parts, f"{label} path escapes its root")
    target = _plain(root / value, directory=directory)
    _require(target.is_relative_to(root), f"{label} path escapes its root")
    return target


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


def _load_module(path: Path, raw: bytes, prefix: str) -> ModuleType:
    name = prefix + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(path), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local source.
        return module
    finally:
        sys.modules.pop(name, None)


def _sources() -> tuple[dict[Path, bytes], tuple[ModuleType, ModuleType, ModuleType, ModuleType], bytes]:
    captured = {_plain(path, directory=False): path.read_bytes() for path in SOURCE_PINS}
    _require(all(_digest(captured[path]) == expected for path, expected in SOURCE_PINS.items()),
             "Baseline admission source pin differs")
    modules = (
        _load_module(PLAN_SOURCE, captured[PLAN_SOURCE], "_dryad_baseline_plan_"),
        _load_module(LEDGER_SOURCE, captured[LEDGER_SOURCE], "_dryad_baseline_ledger_"),
        _load_module(RUNTIME_SOURCE, captured[RUNTIME_SOURCE], "_dryad_baseline_runtime_"),
        _load_module(NATIVE_SOURCE, captured[NATIVE_SOURCE], "_dryad_baseline_native_"),
    )
    own = _plain(Path(__file__), directory=False)
    captured[own] = own.read_bytes()
    _unchanged(captured)
    return captured, modules, captured[TERMINAL_IDENTITIES]


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    _require(all(_plain(path, directory=False).read_bytes() == raw for path, raw in captured.items()),
             "Baseline admission source changed during admission")


def _tree(root: Path, label: str) -> tuple[dict[str, str], frozenset[str]]:
    root = _plain(root, directory=True)
    files: dict[str, str] = {}
    directories: set[str] = set()
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in sorted(os.scandir(directory), key=lambda item: item.name):
            info = entry.stat(follow_symlinks=False)
            relative = Path(entry.path).relative_to(root).as_posix()
            _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                     f"{label} contains a link or reparse point")
            if stat.S_ISDIR(info.st_mode):
                directories.add(relative)
                pending.append(Path(entry.path))
            elif stat.S_ISREG(info.st_mode):
                files[relative] = _digest(Path(entry.path).read_bytes())
            else:
                raise ValueError(f"{label} contains a non-regular entry")
    return files, frozenset(directories)


def _plan(plan_module: ModuleType, public_inputs_path: Path, plan_root: Path,
          expected_plan_sha256: str) -> tuple[dict[str, Any], bytes, dict[str, str]]:
    verified = plan_module.verify(public_inputs_path, plan_root)
    _require(isinstance(verified, dict) and verified.get("plan.json") == expected_plan_sha256,
             "Baseline plan anchor differs")
    raw = _relative(plan_root, "plan.json", "Baseline plan", directory=False).read_bytes()
    _require(_digest(raw) == expected_plan_sha256, "Baseline plan changed during verification")
    return _json(raw, "Baseline plan"), raw, verified


def _question_ids(runtime: Any) -> list[str]:
    questions = getattr(runtime, "questions", None)
    _require(isinstance(questions, list) and len(questions) == 178, "Baseline runtime question inventory differs")
    result = [item.get("question", {}).get("id") if isinstance(item, Mapping) else None for item in questions]
    _require(all(isinstance(item, str) and item for item in result) and len(set(result)) == 178,
             "Baseline runtime question identity differs")
    return result


def _rows(plan: Mapping[str, Any], plan_root: Path, execution_root: Path,
          runtime_question_ids: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    passes, requests = plan.get("passes"), plan.get("requests")
    _require(isinstance(passes, list) and isinstance(requests, list) and len(passes) == 236 and len(requests) == 5428,
             "Baseline plan geometry differs")
    pass_by_id: dict[str, dict[str, Any]] = {}
    for item in passes:
        _require(isinstance(item, dict) and set(item) >= {"pass_id", "logical_sample_id", "opaque_story_id", "input_path", "run_path", "source_sha256", "source_bytes", "batch_size", "batches"},
                 "Baseline pass schema differs")
        pass_id = item["pass_id"]
        _require(isinstance(pass_id, str) and pass_id and pass_id not in pass_by_id
                 and isinstance(item["logical_sample_id"], str) and item["logical_sample_id"]
                 and isinstance(item["opaque_story_id"], str) and item["opaque_story_id"]
                 and _HASH.fullmatch(item["source_sha256"]) is not None
                 and type(item["source_bytes"]) is int and item["source_bytes"] >= 0
                 and item["batch_size"] == 8 and item["batches"] == 23,
                 "Baseline pass binding differs")
        _relative(plan_root, item["input_path"], "Baseline input", directory=False)
        _relative(execution_root, item["run_path"], "Baseline execution run", directory=True)
        pass_by_id[pass_id] = item
    _require(len(pass_by_id) == 236, "Baseline pass cardinality differs")
    by_pass = {pass_id: [] for pass_id in pass_by_id}
    ordered: list[dict[str, Any]] = []
    for ordinal, item in enumerate(requests, start=1):
        _require(isinstance(item, dict) and set(item) >= {"ordinal", "pass_id", "logical_sample_id", "batch_number", "question_ids", "prompt_path", "prompt_sha256", "prompt_bytes", "schema_path", "schema_sha256", "schema_bytes", "endpoint_user_payloads"},
                 "Baseline request schema differs")
        _require(item["ordinal"] == ordinal and item["pass_id"] in pass_by_id and type(item["batch_number"]) is int,
                 "Baseline request identity differs")
        passed = pass_by_id[item["pass_id"]]
        _require(item["logical_sample_id"] == passed["logical_sample_id"]
                 and isinstance(item["question_ids"], list) and 1 <= len(item["question_ids"]) <= 8
                 and all(isinstance(value, str) and value for value in item["question_ids"])
                 and _HASH.fullmatch(item["prompt_sha256"]) is not None
                 and _HASH.fullmatch(item["schema_sha256"]) is not None
                 and type(item["prompt_bytes"]) is int and item["prompt_bytes"] >= 0
                 and type(item["schema_bytes"]) is int and item["schema_bytes"] >= 0,
                 "Baseline request binding differs")
        prompt = _relative(plan_root, item["prompt_path"], "Baseline prompt", directory=False).read_bytes()
        schema = _relative(plan_root, item["schema_path"], "Baseline schema", directory=False).read_bytes()
        _require(_digest(prompt) == item["prompt_sha256"] and len(prompt) == item["prompt_bytes"]
                 and _digest(schema) == item["schema_sha256"] and len(schema) == item["schema_bytes"],
                 "Baseline prompt or schema artifact differs")
        payloads = item["endpoint_user_payloads"]
        _require(isinstance(payloads, Mapping) and payloads == {
            "grok": {"sha256": item["prompt_sha256"], "bytes": item["prompt_bytes"]},
            "sol": {"sha256": item["prompt_sha256"], "bytes": item["prompt_bytes"]},
        }, "Baseline endpoint payload binding differs")
        by_pass[item["pass_id"]].append(item)
        ordered.append(item)
    _require(len(ordered) == 5428, "Baseline request cardinality differs")
    for pass_id, planned in by_pass.items():
        _require([item["batch_number"] for item in planned] == list(range(1, 24))
                 and [question for item in planned for question in item["question_ids"]] == runtime_question_ids,
                 "Baseline batch or runtime question binding differs")
    return pass_by_id, by_pass, ordered


def _source(pass_record: Mapping[str, Any], plan_root: Path) -> dict[str, Any]:
    path = _relative(plan_root, pass_record["input_path"], "Baseline input", directory=False)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Baseline input is not UTF-8") from error
    _require(text.encode("utf-8") == raw and _digest(raw) == pass_record["source_sha256"]
             and len(raw) == pass_record["source_bytes"], "Baseline source artifact differs")
    return {
        "opaque_story_id": pass_record["logical_sample_id"],
        "story_text": text,
        "artifact_path": str(path),
        "source_opaque_story_id": pass_record["opaque_story_id"],
    }


def _checkpoint_hash(run_root: Path, batch_number: int) -> str:
    return _digest(_relative(run_root, f"responses/batch-{batch_number:04d}.json", "Baseline checkpoint", directory=False).read_bytes())


def _receipt_route_hash(run_root: Path, batch_number: int) -> str:
    receipt = _json(_relative(run_root, f"responses/grok-broker/batch-{batch_number:04d}-attempt-0001/receipt.json", "Baseline receipt", directory=False).read_bytes(), "Baseline receipt")
    route_hash = receipt.get("route_sha256")
    _require(isinstance(route_hash, str) and _HASH.fullmatch(route_hash) is not None, "Baseline receipt route differs")
    return route_hash


def _run_artifact_hash(run_root: Path, batch_number: int, relative: str, label: str) -> str:
    raw = _relative(run_root, relative.format(batch_number=batch_number), label, directory=False).read_bytes()
    if label == "Baseline replay prompt":
        try:
            raw = gzip.decompress(raw)
        except OSError as error:
            raise ValueError("Baseline replay prompt is not gzip") from error
    return _digest(raw)


def _trusted_identities(raw: bytes) -> tuple[frozenset[str], frozenset[str]]:
    value = _json(raw, "Terminal identities")
    unresolved = value.get("unresolved_contact")
    _require(value.get("schema_version") == 2
             and value.get("evidence_class") == "preserved_predecessor_native_identity_exclusion"
             and value.get("completed_identity_records") == 33
             and value.get("native_admission") is False
             and value.get("execution_authority") is False
             and value.get("empirical_batch_cap") is None
             and isinstance(value.get("records"), list) and len(value["records"]) == 33
             and unresolved == {
                 "automatic_resend_permitted": False,
                 "campaign": "qualification-v2",
                 "native_identity_claimed": False,
                 "ordinal": 28,
                 "state": "ambiguous_terminal_no_trusted_native_identity",
                 "terminal_proof_sha256": "b35a84feebcdd948bf2a827b67421f9142efa7698650a439a13e9d6ce59e22ba",
             }, "Terminal identity exclusion differs")
    request_ids: set[str] = set()
    session_ids: set[str] = set()
    for record in value["records"]:
        _require(isinstance(record, Mapping) and set(record) == {
            "campaign", "ordinal", "receipt_path", "receipt_sha256", "request_id_hash", "session_id_hash",
        } and isinstance(record["campaign"], str) and record["campaign"].startswith("qualification-v")
                 and type(record["ordinal"]) is int and record["ordinal"] > 0
                 and isinstance(record["receipt_path"], str) and record["receipt_path"]
                 and all(isinstance(record[field], str) and _HASH.fullmatch(record[field]) is not None
                         for field in ("receipt_sha256", "request_id_hash", "session_id_hash"))
                 and record["request_id_hash"] not in request_ids and record["session_id_hash"] not in session_ids,
                 "Terminal identity record differs")
        _require(not (record["campaign"] == unresolved["campaign"] and record["ordinal"] == unresolved["ordinal"]),
                 "Quarantined terminal contact has a trusted identity")
        request_ids.add(record["request_id_hash"])
        session_ids.add(record["session_id_hash"])
    _require(len(request_ids) == len(session_ids) == 33, "Terminal identity cardinality differs")
    return frozenset(request_ids), frozenset(session_ids)


def _execution_inventory(execution_root: Path, pass_by_id: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, str], frozenset[str]]:
    files, directories = _tree(execution_root, "Baseline execution")
    prefixes = ("cohorts/", "contacts/", *(record["run_path"] + "/" for record in pass_by_id.values()))
    _require(all(relative == "initialization.json" or relative.startswith(prefixes) for relative in files), "Baseline execution contains unexpected evidence")
    expected_directories = {
        parent.as_posix()
        for relative in files
        for parent in Path(relative).parents
        if parent != Path(".")
    }
    _require(directories == expected_directories, "Baseline execution contains orphan directories")
    return files, directories


def _ledger(ledger_module: ModuleType, execution_root: Path, public_inputs_raw: bytes, plan_raw: bytes,
            expected_plan_sha256: str, expected_final_settlement_sha256: str, expected_route_sha256: str,
            expected_execution_source_sha256: str, expected_reviewer_task: str) -> dict[str, Any]:
    result = ledger_module.verify_ledger(
        execution_root,
        public_inputs_raw,
        plan_raw,
        expected_plan_sha256,
        expected_final_settlement_sha256,
        expected_route_sha256=expected_route_sha256,
        expected_execution_source_sha256=expected_execution_source_sha256,
        expected_reviewer_task=expected_reviewer_task,
    )
    if set(result) == {"evidence_class", "native_admission", "execution_authority", "contacts", "routes", "authorizations", "head"}:
        plan = _json(plan_raw, "Baseline plan")
        groups = ledger_module.cohort_groups(plan)
        result = {**result, "epochs": {
            number: {"route_sha256": expected_route_sha256, "execution_source_sha256": expected_execution_source_sha256,
                     "operational_renewal_sha256": None}
            for number, _ in enumerate(groups, start=1)}, "renewals": []}
    if isinstance(result.get("contacts"), Mapping) and any("cohort_number" not in item for item in result["contacts"].values()):
        plan = _json(plan_raw, "Baseline plan")
        ordinal_cohorts = {ordinal: number for number, group in enumerate(ledger_module.cohort_groups(plan), start=1)
                           for ordinal in group}
        result = {**result, "contacts": {
            ordinal: {**item, "cohort_number": ordinal_cohorts[ordinal]}
            for ordinal, item in result["contacts"].items()}}
    _require(isinstance(result, dict) and set(result) == {
        "evidence_class", "native_admission", "execution_authority", "contacts", "routes", "authorizations", "epochs", "renewals", "head",
    } and result["evidence_class"] == "provider_free_baseline_ledger_consistency"
             and result["native_admission"] is False and result["execution_authority"] is False,
             "Baseline ledger return shape differs")
    contacts, routes, authorizations, epochs, head = result["contacts"], result["routes"], result["authorizations"], result["epochs"], result["head"]
    _require(isinstance(contacts, Mapping) and set(contacts) == set(range(1, 5429))
             and isinstance(routes, Mapping) and expected_route_sha256 in routes and all(isinstance(value, Mapping) for value in routes.values())
             and isinstance(authorizations, Mapping) and authorizations
             and isinstance(epochs, Mapping) and set(epochs) == set(range(1, 544))
             and head == {"cohort_number": 543, "settlement_sha256": expected_final_settlement_sha256},
             "Baseline ledger authority differs")
    return result


def admit_baseline(
    public_inputs_path: Path,
    plan_root: Path,
    execution_root: Path,
    runtime_manifest_path: Path,
    *,
    expected_plan_sha256: str,
    expected_final_settlement_sha256: str,
    expected_execution_source_sha256: str,
    expected_route_sha256: str,
    expected_runtime_manifest_sha256: str,
    expected_admission_sha256: str,
    expected_reviewer_task: str,
    expected_initialization_sha256: str,
) -> dict[str, Any]:
    """Replay all 236 fixed baseline passes without contacting a provider."""
    required_hashes = (
        expected_plan_sha256,
        expected_final_settlement_sha256,
        expected_execution_source_sha256,
        expected_route_sha256,
        expected_runtime_manifest_sha256,
        expected_admission_sha256,
        expected_initialization_sha256,
    )
    _require(all(isinstance(value, str) and _HASH.fullmatch(value) is not None for value in required_hashes)
             and expected_plan_sha256 == PLAN_SHA256
             and isinstance(expected_reviewer_task, str) and expected_reviewer_task,
             "Trusted baseline admission anchors are required")
    own_path = _plain(Path(__file__), directory=False)
    own_raw = own_path.read_bytes()
    _require(_digest(own_raw) == expected_admission_sha256, "Reviewed baseline admission source differs")
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root = _plain(plan_root, directory=True)
    execution_root = _plain(execution_root, directory=True)
    runtime_manifest_path = _plain(runtime_manifest_path, directory=False)
    _require(_digest(runtime_manifest_path.read_bytes()) == expected_runtime_manifest_sha256,
             "Runtime manifest anchor differs")
    _require(not plan_root.is_relative_to(execution_root) and not execution_root.is_relative_to(plan_root),
             "Baseline plan and execution roots must be separate")
    public_inputs_raw = public_inputs_path.read_bytes()
    captured, (plan_module, ledger_module, runtime_module, native_module), terminal_raw = _sources()
    _require(captured.get(own_path) == own_raw, "Baseline admission source changed during loading")
    plan, plan_raw, plan_artifacts = _plan(plan_module, public_inputs_path, plan_root, expected_plan_sha256)
    _require(isinstance(plan_artifacts, dict) and all(isinstance(path, str) and isinstance(value, str)
             and _HASH.fullmatch(value) is not None for path, value in plan_artifacts.items()),
             "Baseline plan verification result differs")
    initialization_raw = _relative(execution_root, "initialization.json", "Baseline initialization", directory=False).read_bytes()
    _require(_digest(initialization_raw) == expected_initialization_sha256, "Baseline initialization anchor differs")
    initialization = _json(initialization_raw, "Baseline initialization")
    initialization_fields = {"schema_version", "evidence_class", "plan_sha256", "plan_inventory_sha256", "plan_files",
                             "runtime_manifest_sha256", "route_sha256", "execution_source_sha256", "public_inputs_sha256"}
    _require(set(initialization) in (initialization_fields, initialization_fields | {"route_snapshot_sha256"})
             and ("route_snapshot_sha256" not in initialization or isinstance(initialization["route_snapshot_sha256"], str)
                  and _HASH.fullmatch(initialization["route_snapshot_sha256"]) is not None)
             and type(initialization.get("schema_version")) is int and initialization["schema_version"] == 1
             and initialization.get("evidence_class") == "provider_free_baseline_initialization"
             and initialization.get("plan_sha256") == expected_plan_sha256
             and initialization.get("plan_inventory_sha256") == _digest(_canonical(plan_artifacts))
             and type(initialization.get("plan_files")) is int and initialization["plan_files"] == len(plan_artifacts) == 11094
             and initialization.get("runtime_manifest_sha256") == expected_runtime_manifest_sha256
             and initialization.get("route_sha256") == expected_route_sha256
             and initialization.get("execution_source_sha256") == expected_execution_source_sha256
             and initialization.get("public_inputs_sha256") == _digest(public_inputs_raw),
             "Baseline initialization bindings differ")
    runtime = runtime_module.load_runtime(runtime_manifest_path, expected_manifest_sha256=expected_runtime_manifest_sha256)
    _require(callable(getattr(runtime, "verify", None)), "Baseline runtime verification differs")
    runtime.verify()
    runtime_question_ids = _question_ids(runtime)
    pass_by_id, by_pass, _ = _rows(plan, plan_root, execution_root, runtime_question_ids)
    trusted_request_ids, trusted_session_ids = _trusted_identities(terminal_raw)
    ledger = _ledger(
        ledger_module,
        execution_root,
        public_inputs_raw,
        plan_raw,
        expected_plan_sha256,
        expected_final_settlement_sha256,
        expected_route_sha256,
        expected_execution_source_sha256,
        expected_reviewer_task,
    )
    execution_before = _execution_inventory(execution_root, pass_by_id)
    _require(execution_before[0].get("initialization.json") == _digest(initialization_raw),
             "Baseline initialization changed before native replay")
    contacts = ledger["contacts"]
    routes = ledger["routes"]
    request_ids: set[str] = set()
    session_ids: set[str] = set()
    grok_rows: list[dict[str, Any]] = []
    for pass_record in plan["passes"]:
        source = _source(pass_record, plan_root)
        _require(source["opaque_story_id"] == pass_record["logical_sample_id"]
                 and source["source_opaque_story_id"] == pass_record["opaque_story_id"],
                 "Baseline logical/native source identity differs")
        run_root = _relative(execution_root, pass_record["run_path"], "Baseline execution run", directory=True)
        admitted = native_module.admit_pass(
            run_root,
            source=source,
            batch_size=8,
            approved_routes=routes,
            runtime=runtime,
        )
        _require(isinstance(admitted, Mapping) and set(admitted) >= {
            "verdicts", "score", "coverage", "native_identities", "run_manifest_sha256", "checkpoint_head_sha256", "evidence_class",
        } and admitted["evidence_class"] == "native_record_replay_only"
                 and isinstance(admitted["verdicts"], list) and len(admitted["verdicts"]) == 178
                 and isinstance(admitted["native_identities"], list) and len(admitted["native_identities"]) == 23,
                 "Baseline native replay result differs")
        planned = by_pass[pass_record["pass_id"]]
        _require(len(planned) == 23, "Baseline pass request count differs")
        for request, identity in zip(planned, admitted["native_identities"], strict=True):
            _require(isinstance(identity, Mapping), "Baseline native identity differs")
            ordinal = request["ordinal"]
            contact = contacts[ordinal]
            _require(isinstance(contact, Mapping)
                     and contact.get("pass_id") == pass_record["pass_id"]
                     and contact.get("logical_sample_id") == pass_record["logical_sample_id"]
                     and contact.get("source_sha256") == pass_record["source_sha256"]
                     and contact.get("prompt_sha256") == request["prompt_sha256"]
                     and contact.get("schema_sha256") == request["schema_sha256"]
                     and isinstance(contact.get("cohort_number"), int)
                     and contact["cohort_number"] in ledger["epochs"]
                     and contact.get("execution_source_sha256") == ledger["epochs"][contact["cohort_number"]]["execution_source_sha256"],
                     "Baseline ledger source, prompt, schema, or executor binding differs")
            _require(_checkpoint_hash(run_root, request["batch_number"]) == contact.get("checkpoint_sha256")
                     and _run_artifact_hash(run_root, request["batch_number"], "responses/batch-{batch_number:04d}.prompt.txt.gz", "Baseline replay prompt") == request["prompt_sha256"]
                     and _run_artifact_hash(run_root, request["batch_number"], "responses/schemas/batch-{batch_number:04d}.json", "Baseline replay schema") == request["schema_sha256"],
                     "Baseline native checkpoint, prompt, or schema binding differs")
            route_hash = _receipt_route_hash(run_root, request["batch_number"])
            _require(route_hash == contact.get("route_sha256") and route_hash in routes
                     and route_hash == ledger["epochs"][contact["cohort_number"]]["route_sha256"],
                     "Baseline route binding differs")
            request_id = identity.get("request_id_hash")
            session_id = identity.get("session_id_hash")
            _require(isinstance(request_id, str) and isinstance(session_id, str)
                     and _HASH.fullmatch(request_id) is not None and _HASH.fullmatch(session_id) is not None
                     and request_id == contact.get("request_id_hash") and session_id == contact.get("session_id_hash")
                     and request_id not in request_ids and session_id not in session_ids
                     and request_id not in trusted_request_ids and session_id not in trusted_session_ids,
                     "Baseline native identity binding or exclusion differs")
            request_ids.add(request_id)
            session_ids.add(session_id)
        grok_rows.append({
            "endpoint": "grok",
            "logical_sample_id": pass_record["logical_sample_id"],
            "native_artifact_id": source["opaque_story_id"],
            "opaque_story_id": source["source_opaque_story_id"],
            "source_path": source["artifact_path"],
            "source_sha256": pass_record["source_sha256"],
            "verdicts": admitted["verdicts"],
            "score": admitted["score"],
            "coverage": admitted["coverage"],
            "run_manifest_sha256": admitted["run_manifest_sha256"],
            "checkpoint_head_sha256": admitted["checkpoint_head_sha256"],
        })
    _require(len(grok_rows) == 236 and len(request_ids) == len(session_ids) == 5428
             and request_ids.isdisjoint(session_ids)
             and request_ids.isdisjoint(trusted_request_ids | trusted_session_ids)
             and session_ids.isdisjoint(trusted_request_ids | trusted_session_ids),
             "Baseline native identity cardinality or predecessor exclusion differs")
    runtime.verify()
    _require(public_inputs_path.read_bytes() == public_inputs_raw, "Public inputs changed during baseline admission")
    _require(_tree(plan_root, "Baseline plan") == ({path: value for path, value in plan_artifacts.items()},
             frozenset(parent.as_posix() for path in plan_artifacts for parent in Path(path).parents if parent != Path("."))),
             "Baseline plan artifact inventory changed during admission")
    _require(_ledger(
        ledger_module,
        execution_root,
        public_inputs_raw,
        plan_raw,
        expected_plan_sha256,
        expected_final_settlement_sha256,
        expected_route_sha256,
        expected_execution_source_sha256,
        expected_reviewer_task,
    ) == ledger, "Baseline ledger changed during admission")
    _require(_execution_inventory(execution_root, pass_by_id) == execution_before,
             "Baseline execution evidence changed during admission")
    _unchanged(captured)
    return {
        "schema_version": 2,
        "evidence_class": "complete_native_baseline_measurement_admission",
        "execution_authority": False,
        "provider_calls": 0,
        "empirical_batch_cap": None,
        "admission_sha256": expected_admission_sha256,
        "plan_sha256": expected_plan_sha256,
        "initialization_sha256": expected_initialization_sha256,
        "runtime_manifest_sha256": expected_runtime_manifest_sha256,
        "original_initialization": {
            "execution_source_sha256": expected_execution_source_sha256,
            "route_sha256": expected_route_sha256,
        },
        "cohort_epochs": ledger["epochs"],
        "reviewer_task": expected_reviewer_task,
        "admitted_passes": 236,
        "logical_requests": 5428,
        "endpoint_grok_rows": grok_rows,
        "immutable_provenance": {
            "dependency_source_sha256": {path.name: expected for path, expected in SOURCE_PINS.items()},
            "terminal_identities_sha256": SOURCE_PINS[TERMINAL_IDENTITIES],
            "ledger_head": ledger["head"],
            "trusted_predecessor_native_identities": 33,
            "quarantined_predecessor_contact": {"campaign": "qualification-v2", "ordinal": 28},
        },
    }
