"""Read-only composition of the frozen Dryad qualification evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
PLAN_SOURCE = ROOT / "campaign_plan.py"
LEDGER_SOURCE = ROOT / "cohort_ledger.py"
NATIVE_SOURCE = ROOT / "native_admission.py"
MATH_SOURCE = ROOT / "qualification_math.py"
SOURCE_PINS = {
    PLAN_SOURCE: "21d25bf51017665d0893efe8eed152fc337688115e303304a09824419bd5e622",
    LEDGER_SOURCE: "ec70e52eb99abdf21342a949a5a77f1a19f542ee585e198b5f8eb147e2594a3d",
    NATIVE_SOURCE: "e061d768449adfaab96b15c62a8ebe213d6de10e9ec6d7755e52d911a57b71ac",
    MATH_SOURCE: "25c57a64ce18d938c900ef3de47cdc04282ce2b6aff92f897f8ad012b25098d0",
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _plain(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Path contains a link or reparse point")
    resolved = absolute.resolve()
    if directory is True:
        _require(resolved.is_dir(), "Expected a directory")
    if directory is False:
        _require(resolved.is_file(), "Expected a file")
    return resolved


def _relative(root: Path, relative: Any, label: str, *, directory: bool | None = None) -> Path:
    _require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), f"{label} path differs")
    value = Path(relative)
    _require(".." not in value.parts and "." not in value.parts, f"{label} path escapes its root")
    target = _plain(root / value, directory=directory)
    _require(target.is_relative_to(root), f"{label} path escapes its root")
    return target


def _load_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            _require(isinstance(key, str) and key not in value, f"{label} has duplicate keys")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _load_module(path: Path, raw: bytes) -> ModuleType:
    name = "_dryad_campaign_admission_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
        return module
    finally:
        sys.modules.pop(name, None)


def _sources() -> tuple[dict[Path, bytes], tuple[ModuleType, ModuleType, ModuleType, ModuleType]]:
    captured = {_plain(path, directory=False): path.read_bytes() for path in SOURCE_PINS}
    _require(all(_digest(captured[path]) == expected for path, expected in SOURCE_PINS.items()), "Campaign source pin differs")
    modules = tuple(_load_module(path, raw) for path, raw in captured.items())
    captured[Path(__file__).resolve()] = Path(__file__).read_bytes()
    _unchanged(captured)
    return captured, modules  # type: ignore[return-value]


def _unchanged(captured: Mapping[Path, bytes]) -> None:
    _require(all(path.read_bytes() == raw for path, raw in captured.items()), "Campaign source changed during admission")


def _plan(plan_root: Path, expected_plan_sha256: str, plan_module: ModuleType, public_inputs_path: Path) -> tuple[dict[str, Any], bytes]:
    verified = plan_module.verify(public_inputs_path, plan_root)
    _require(isinstance(verified, dict) and verified.get("plan.json") == expected_plan_sha256, "Plan anchor differs")
    raw = _relative(plan_root, "plan.json", "Plan", directory=False).read_bytes()
    _require(_digest(raw) == expected_plan_sha256, "Plan changed during verification")
    plan = _load_json(raw, "Plan")
    _require(isinstance(plan.get("passes"), list) and isinstance(plan.get("requests"), list), "Plan pass/request arrays are missing")
    _require(len(plan["passes"]) == 18 and len(plan["requests"]) == 261, "Plan geometry differs")
    return plan, raw


def _rows(plan: Mapping[str, Any], plan_root: Path, execution_root: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    passes = plan["passes"]
    requests = plan["requests"]
    pass_by_id: dict[str, dict[str, Any]] = {}
    for item in passes:
        _require(isinstance(item, dict) and set(item) >= {"pass_id", "opaque_story_id", "batch_size", "repetition", "input_path", "run_path", "source_sha256"}, "Plan pass schema differs")
        pass_id = item["pass_id"]
        _require(isinstance(pass_id, str) and pass_id and pass_id not in pass_by_id, "Plan pass identity differs")
        _require(type(item["batch_size"]) is int and item["batch_size"] in (8, 32) and type(item["repetition"]) is int and item["repetition"] in (1, 2, 3), "Plan pass schedule differs")
        _require(isinstance(item["opaque_story_id"], str) and _HASH.fullmatch(item["source_sha256"]) is not None, "Plan source binding differs")
        _relative(plan_root, item["input_path"], "Plan input", directory=False)
        _relative(execution_root, item["run_path"], "Execution run", directory=True)
        pass_by_id[pass_id] = item
    _require(len(pass_by_id) == 18, "Plan pass cardinality differs")
    by_pass = {pass_id: [] for pass_id in pass_by_id}
    ordered: list[dict[str, Any]] = []
    for ordinal, item in enumerate(requests, start=1):
        _require(isinstance(item, dict) and set(item) >= {"ordinal", "pass_id", "batch_number", "question_ids", "prompt_path", "prompt_sha256", "prompt_bytes", "schema_sha256", "schema_bytes"}, "Plan request schema differs")
        _require(item["ordinal"] == ordinal and item["pass_id"] in pass_by_id and type(item["batch_number"]) is int, "Plan request identity differs")
        _require(isinstance(item["question_ids"], list) and item["question_ids"] and all(isinstance(value, str) for value in item["question_ids"]), "Plan request questions differ")
        _require(_HASH.fullmatch(item["prompt_sha256"]) is not None and _HASH.fullmatch(item["schema_sha256"]) is not None, "Plan request hash differs")
        prompt = _relative(plan_root, item["prompt_path"], "Plan prompt", directory=False).read_bytes()
        _require(_digest(prompt) == item["prompt_sha256"] and len(prompt) == item["prompt_bytes"], "Plan prompt artifact differs")
        by_pass[item["pass_id"]].append(item)
        ordered.append(item)
    _require(len(ordered) == 261, "Plan request cardinality differs")
    for pass_id, planned in by_pass.items():
        _require([item["batch_number"] for item in planned] == list(range(1, len(planned) + 1)), "Plan batch ordering differs")
        expected = (178 + pass_by_id[pass_id]["batch_size"] - 1) // pass_by_id[pass_id]["batch_size"]
        _require(len(planned) == expected, "Plan batch cardinality differs")
    return ordered, by_pass, pass_by_id


def _source(pass_record: Mapping[str, Any], plan_root: Path) -> dict[str, Any]:
    path = _relative(plan_root, pass_record["input_path"], "Plan input", directory=False)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Plan source is not UTF-8") from error
    _require(text.encode("utf-8") == raw and _digest(raw) == pass_record["source_sha256"], "Plan source artifact differs")
    return {"opaque_story_id": pass_record["opaque_story_id"], "story_text": text, "artifact_path": str(path)}


def _checkpoint_hash(run_root: Path, batch_number: int) -> str:
    path = _relative(run_root, f"responses/batch-{batch_number:04d}.json", "Checkpoint", directory=False)
    return _digest(path.read_bytes())


def _receipt_route_hash(run_root: Path, batch_number: int) -> str:
    path = _relative(run_root, f"responses/grok-broker/batch-{batch_number:04d}-attempt-0001/receipt.json", "Native receipt", directory=False)
    route_hash = _load_json(path.read_bytes(), "Native receipt").get("route_sha256")
    _require(_HASH.fullmatch(route_hash) is not None, "Native receipt route differs")
    return route_hash


def admit_campaign(
    public_inputs_path: Path,
    plan_root: Path,
    execution_root: Path,
    *,
    expected_plan_sha256: str,
    expected_final_settlement_sha256: str,
    expected_admission_sha256: str,
    expected_execution_sha256: str,
) -> dict[str, Any]:
    """Replay the complete approved campaign and return its bounded cap decision."""
    _require(_HASH.fullmatch(expected_plan_sha256) is not None and _HASH.fullmatch(expected_final_settlement_sha256) is not None, "Trusted external anchors are required")
    own_path = _plain(Path(__file__), directory=False)
    own_raw = own_path.read_bytes()
    _require(isinstance(expected_admission_sha256, str) and _digest(own_raw) == expected_admission_sha256, "Reviewed admission source differs")
    public_inputs_path = _plain(public_inputs_path, directory=False)
    plan_root, execution_root = _plain(plan_root, directory=True), _plain(execution_root, directory=True)
    _require(not plan_root.is_relative_to(execution_root) and not execution_root.is_relative_to(plan_root), "Plan and execution roots must be separate")
    captured, (plan_module, ledger_module, native_module, math_module) = _sources()
    _require(captured.get(own_path) == own_raw, "Admission source changed during loading")
    plan, plan_raw = _plan(plan_root, expected_plan_sha256, plan_module, public_inputs_path)
    _, by_pass, _ = _rows(plan, plan_root, execution_root)
    ledger = ledger_module.verify_ledger(execution_root, plan_raw, expected_plan_sha256, expected_final_settlement_sha256)
    _require(isinstance(ledger, dict) and set(ledger) == {"routes", "contacts", "head"}, "Ledger return shape differs")
    routes, contacts = ledger["routes"], ledger["contacts"]
    _require(isinstance(routes, dict) and isinstance(contacts, dict) and set(contacts) == set(range(1, 262)), "Ledger cardinality differs")
    _require(isinstance(expected_execution_sha256, str) and _HASH.fullmatch(expected_execution_sha256) is not None
             and {contact.get("execution_source_sha256") for contact in contacts.values()} == {expected_execution_sha256},
             "Campaign execution source differs")
    execution_before = ledger_module._regular_tree(execution_root, "Campaign execution")
    allowed_prefixes = ("cohorts/", "contacts/", *(row["run_path"] + "/" for row in plan["passes"]))
    _require(all(path.startswith(allowed_prefixes) for path in execution_before[0]), "Unexpected campaign evidence")
    expected_directories = {parent.as_posix() for relative in execution_before[0]
                            for parent in Path(relative).parents if parent != Path(".")}
    _require(set(execution_before[1]) == expected_directories, "Unexpected campaign directory")
    runtime = native_module.load_runtime()
    runtime.verify()
    result_rows: list[dict[str, Any]] = []
    request_ids: set[str] = set()
    session_ids: set[str] = set()
    for pass_record in plan["passes"]:
        source = _source(pass_record, plan_root)
        run_root = _relative(execution_root, pass_record["run_path"], "Execution run", directory=True)
        admitted = native_module.admit_pass(run_root, source=source, batch_size=pass_record["batch_size"], approved_routes=routes, runtime=runtime)
        _require(isinstance(admitted, dict) and set(admitted) >= {"verdicts", "score", "coverage", "native_identities", "checkpoint_head_sha256"}, "Native admission return differs")
        planned = by_pass[pass_record["pass_id"]]
        identities = admitted["native_identities"]
        _require(isinstance(identities, list) and len(identities) == len(planned), "Native batch identity count differs")
        for request, identity in zip(planned, identities, strict=True):
            _require(isinstance(identity, dict), "Native identity differs")
            contact = contacts[request["ordinal"]]
            _require(contact.get("source_sha256") == pass_record["source_sha256"], "Ledger source binding differs")
            checkpoint = _checkpoint_hash(run_root, request["batch_number"])
            _require(checkpoint == contact["checkpoint_sha256"], "Ledger checkpoint binding differs")
            _require(identity.get("request_id_hash") == contact["request_id_hash"] and identity.get("session_id_hash") == contact["session_id_hash"], "Ledger native identity binding differs")
            route_hash = _receipt_route_hash(run_root, request["batch_number"])
            _require(route_hash == contact.get("route_sha256") and route_hash in routes, "Ledger route binding differs")
            _require(identity["request_id_hash"] not in request_ids and identity["session_id_hash"] not in session_ids, "Campaign native identity is duplicated")
            request_ids.add(identity["request_id_hash"])
            session_ids.add(identity["session_id_hash"])
        result_rows.append({"opaque_story_id": pass_record["opaque_story_id"], "batch_size": pass_record["batch_size"], "repetition": pass_record["repetition"], "verdicts": admitted["verdicts"], "score": admitted["score"], "coverage": admitted["coverage"]})
    _require(len(result_rows) == 18 and len(request_ids) == len(session_ids) == 261, "Campaign admission is incomplete")
    runtime.verify()
    question_ids = plan.get("runtime", {}).get("question_ids") if isinstance(plan.get("runtime"), dict) else None
    _require(isinstance(question_ids, list) and len(question_ids) == 178, "Plan canonical question IDs differ")
    comparability = math_module.evaluate_comparability(result_rows, question_ids)
    _require(isinstance(comparability, dict) and type(comparability.get("overall_candidate_comparable")) is bool, "Comparability result differs")
    final_plan = plan_module.verify(public_inputs_path, plan_root)
    _require(isinstance(final_plan, dict) and final_plan.get("plan.json") == expected_plan_sha256, "Plan changed during admission")
    _require(ledger_module.verify_ledger(execution_root, plan_raw, expected_plan_sha256, expected_final_settlement_sha256) == ledger, "Ledger changed during admission")
    _require(ledger_module._regular_tree(execution_root, "Campaign execution") == execution_before, "Campaign evidence changed during admission")
    _unchanged(captured)
    cap = 32 if comparability["overall_candidate_comparable"] else 8
    return {"evidence_class": "complete_native_campaign_admission", "execution_authority": False, "provider_calls": 0,
            "admission_sha256": expected_admission_sha256,
            "execution_source_sha256": expected_execution_sha256,
            "dependency_source_sha256": {path.name: expected for path, expected in SOURCE_PINS.items()},
            "plan_sha256": expected_plan_sha256, "ledger_head": ledger["head"], "admitted_passes": len(result_rows),
            "logical_requests": len(request_ids), "comparability": comparability, "cap": cap}
