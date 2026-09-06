"""Read-only reviewed-cohort verification for one fixed-source baseline run.

This baseline accepts one externally pinned execution source throughout.  It
does not implement historical source-transition admission or native lifecycle.
"""

from __future__ import annotations

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
CONTRACT = ROOT / "baseline-measurement-v1.json"
PREPARATION = ROOT / "baseline-preparation-v1.json"
CORE = ROOT / "cohort_ledger_core.py"
PLAN_SOURCE_SHA256 = "33193aa1a394c04c14b4f9ab81871116dbac11f933f22a9e45f252b2d279fdc8"
CONTRACT_SHA256 = "6ae404e31ecafbeac0ef69814127c5222ac8da5fd24c2700f185ca2f8af5cf37"
CORE_SHA256 = "f2dbf57010c324e5b523a23864845d22665af20645a09819c695198c4a11fd6c"
PREPARATION_SHA256 = "64d8deb56082ecc9ca899b264cab6a3b50f91333a8ada5bc0bb9573bfbf1924a"
PUBLIC_INPUTS_SHA256 = "6254f58d3366667c9578e2661a1ca0d105a603a0f8affe2d925a767957937c42"
PLAN_SHA256 = "edeadb93c485ba227153329b5ae420de1c9d08d95e920bac0635d197fd3dbd7f"
GENERATOR_COMMIT = "d8e6cf69a4f05b854859a0f14496066e5c898dd6"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"baseline8-v1-(?:train|dev)-\d{4}-dryad-[0-9a-f]{24}\Z")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            require(key not in value, f"{label} has duplicate keys")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    require(isinstance(value, dict), f"{label} must be an object")
    return value


def _hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _plain_source(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        info = candidate.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Ledger source path contains a link or reparse point")
        require(stat.S_ISREG(info.st_mode) if candidate == absolute else stat.S_ISDIR(info.st_mode),
                "Ledger source path is not a plain file with directory ancestry")
    return absolute


def _source(path: Path, expected: str, label: str) -> bytes:
    plain = _plain_source(path)
    raw = plain.read_bytes()
    require(digest(raw) == expected, f"{label} source pin differs")
    _plain_source(plain)
    return raw


def _core() -> tuple[ModuleType, bytes]:
    raw = _source(CORE, CORE_SHA256, "Ledger core")
    name = "_dryad_baseline_ledger_" + uuid.uuid4().hex
    module = ModuleType(name)
    module.__file__, module.__package__ = str(CORE), ""
    sys.modules[name] = module
    try:
        exec(compile(raw, str(CORE), "exec"), module.__dict__)  # noqa: S102 - execute only exact hash-pinned local source.
        return module, raw
    finally:
        sys.modules.pop(name, None)


def _input_sources(raw: bytes) -> dict[str, str]:
    require(digest(raw) == PUBLIC_INPUTS_SHA256, "Public inputs hash differs")
    value = _json(raw, "Public inputs")
    require(set(value) == {"TRAIN", "DEV"} and isinstance(value["TRAIN"], list) and isinstance(value["DEV"], list) and len(value["TRAIN"]) == 176 and len(value["DEV"]) == 60, "Public input geometry differs")
    result: dict[str, str] = {}
    for rows in (value["TRAIN"], value["DEV"]):
        for row in rows:
            require(isinstance(row, dict) and set(row) == {"opaque_story_id", "story_text"} and isinstance(row["opaque_story_id"], str) and isinstance(row["story_text"], str) and row["opaque_story_id"] not in result, "Public input identity differs")
            result[row["opaque_story_id"]] = digest(row["story_text"].encode("utf-8"))
    require(len(result) == 236, "Public input count differs")
    return result


def _geometry(public_inputs_raw: bytes, plan_raw: bytes, expected_plan_sha256: str, core: ModuleType) -> Any:
    require(expected_plan_sha256 == PLAN_SHA256 and digest(plan_raw) == PLAN_SHA256, "Published baseline plan hash differs")
    planner_raw, contract_raw, preparation_raw = _source(PLAN_SOURCE, PLAN_SOURCE_SHA256, "Baseline planner"), _source(CONTRACT, CONTRACT_SHA256, "Baseline contract"), _source(PREPARATION, PREPARATION_SHA256, "Baseline preparation")
    contract = _json(contract_raw, "Baseline contract")
    preparation = _json(preparation_raw, "Baseline preparation")
    require(preparation.get("evidence_class") == "provider_free_fixed_baseline_preparation" and preparation.get("generator_commit") == GENERATOR_COMMIT and preparation.get("contract_sha256") == CONTRACT_SHA256 and preparation.get("plan_sha256") == PLAN_SHA256 and preparation.get("public_inputs_sha256") == PUBLIC_INPUTS_SHA256 and preparation.get("files") == 11094 and preparation.get("train_stories") == 176 and preparation.get("dev_stories") == 60 and preparation.get("questions_per_story") == 178 and preparation.get("complete_passes_per_endpoint") == 236 and preparation.get("logical_requests_per_endpoint") == 5428 and preparation.get("dispatch_batch_size") == 8 and preparation.get("empirical_batch_cap") is None and preparation.get("byte_exact_regeneration") is True and preparation.get("provider_calls") == 0 and preparation.get("native_admission") is False and preparation.get("execution_authority") is False, "Baseline preparation binding differs")
    require(contract.get("execution", {}).get("dispatch_batch_size") == 8 and contract.get("execution", {}).get("empirical_batch_cap") is None, "Baseline contract geometry differs")
    sources = _input_sources(public_inputs_raw)
    plan = _json(plan_raw, "Baseline plan")
    generator = plan.get("generator")
    planner_relative = PLAN_SOURCE.relative_to(ROOT.parents[1]).as_posix()
    require(plan.get("evidence_class") == "provider_free_fixed_baseline_measurement_plan" and plan.get("execution_authority") is False and plan.get("native_admission") is False and plan.get("public_inputs_sha256") == PUBLIC_INPUTS_SHA256 and plan.get("baseline_contract") == {"path": CONTRACT.relative_to(ROOT.parents[1]).as_posix(), "sha256": CONTRACT_SHA256} and plan.get("dispatch_batch_size") == 8 and plan.get("empirical_batch_cap") is None and isinstance(generator, Mapping) and generator.get("git_commit") == GENERATOR_COMMIT and isinstance(generator.get("files"), Mapping) and generator["files"].get(planner_relative) == PLAN_SOURCE_SHA256, "Baseline plan contract differs")
    counts = plan.get("counts")
    require(counts == {"train_stories": 176, "dev_stories": 60, "stories": 236, "questions_per_story": 178, "logical_requests": 5428, "complete_passes_per_endpoint": 236, "logical_requests_per_endpoint": 5428}, "Baseline plan geometry differs")
    passes, requests = plan.get("passes"), plan.get("requests")
    require(isinstance(passes, list) and isinstance(requests, list) and len(passes) == 236 and len(requests) == 5428, "Baseline plan arrays differ")
    pass_by_id: dict[str, dict[str, Any]] = {}
    for item in passes:
        require(isinstance(item, dict) and isinstance(item.get("pass_id"), str) and isinstance(item.get("logical_sample_id"), str) and _ID.fullmatch(item["logical_sample_id"]) and item["pass_id"].startswith("baseline8-v1/") and item.get("batch_size") == 8 and item.get("batches") == 23 and isinstance(item.get("opaque_story_id"), str) and item["opaque_story_id"] in sources and item.get("source_sha256") == sources[item["opaque_story_id"]] and item["pass_id"] not in pass_by_id, "Baseline pass binding differs")
        pass_by_id[item["pass_id"]] = item
    request_by_ordinal: dict[int, dict[str, Any]] = {}
    for item in requests:
        ordinal = item.get("ordinal") if isinstance(item, dict) else None
        require(type(ordinal) is int and ordinal not in request_by_ordinal and item.get("pass_id") in pass_by_id and item.get("logical_sample_id") == pass_by_id[item["pass_id"]]["logical_sample_id"] and isinstance(item.get("question_ids"), list) and 1 <= len(item["question_ids"]) <= 8 and _hash(item.get("prompt_sha256")) and _hash(item.get("schema_sha256")), "Baseline request binding differs")
        request_by_ordinal[ordinal] = item
    require(set(request_by_ordinal) == set(range(1, 5429)), "Baseline request ordinals differ")
    groups = tuple(tuple(range(start, min(start + 10, 5429))) for start in range(1, 5429, 10))
    require(len(groups) == 543 and [len(group) for group in groups] == [10] * 542 + [8], "Baseline cohort geometry differs")
    require(_source(PLAN_SOURCE, PLAN_SOURCE_SHA256, "Baseline planner") == planner_raw and _source(CONTRACT, CONTRACT_SHA256, "Baseline contract") == contract_raw and _source(PREPARATION, PREPARATION_SHA256, "Baseline preparation") == preparation_raw, "Baseline source changed during geometry validation")
    return core.LedgerGeometry(expected_plan_sha256, request_by_ordinal, pass_by_id, groups)


def cohort_groups(plan: Mapping[str, Any]) -> list[tuple[int, ...]]:
    """Return the fixed 543 reviewed cohorts after validating plan geometry."""
    require(isinstance(plan, Mapping) and isinstance(plan.get("requests"), list) and len(plan["requests"]) == 5428, "Baseline plan geometry differs")
    return [tuple(range(start, min(start + 10, 5429))) for start in range(1, 5429, 10)]


def verify_prefix(execution_root: Path, public_inputs_raw: bytes, plan_raw: bytes, expected_plan_sha256: str, expected_settlement_sha256: str, through_cohort: int, *, expected_route_sha256: str, expected_execution_source_sha256: str, expected_reviewer_task: str, allowed_pending_paths: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Verify a provider-free contiguous baseline ledger prefix."""
    core, core_raw = _core()
    geometry = _geometry(public_inputs_raw, plan_raw, expected_plan_sha256, core)
    result = core.verify_prefix(execution_root, geometry, expected_settlement_sha256, through_cohort, expected_route_sha256=expected_route_sha256, expected_execution_source_sha256=expected_execution_source_sha256, reviewer_task=expected_reviewer_task, allowed_pending_paths=allowed_pending_paths)
    require(_source(CORE, CORE_SHA256, "Ledger core") == core_raw, "Baseline ledger source changed during verification")
    for path, expected in ((PLAN_SOURCE, PLAN_SOURCE_SHA256), (CONTRACT, CONTRACT_SHA256), (PREPARATION, PREPARATION_SHA256)):
        _source(path, expected, "Baseline dependency")
    return result


def verify_ledger(execution_root: Path, public_inputs_raw: bytes, plan_raw: bytes, expected_plan_sha256: str, expected_final_settlement_sha256: str, *, expected_route_sha256: str, expected_execution_source_sha256: str, expected_reviewer_task: str) -> dict[str, Any]:
    """Verify all 543 settled cohorts with no pending files or provider contact."""
    return verify_prefix(execution_root, public_inputs_raw, plan_raw, expected_plan_sha256, expected_final_settlement_sha256, 543, expected_route_sha256=expected_route_sha256, expected_execution_source_sha256=expected_execution_source_sha256, expected_reviewer_task=expected_reviewer_task)
