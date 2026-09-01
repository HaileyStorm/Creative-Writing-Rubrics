#!/usr/bin/env python3
"""Contingent, veto-only Sol validation for the Desc18 public/open replay."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1"
FREEZE_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1"
FREEZE = HERE.parent / FREEZE_ID / "study.py"
FREEZE_COMMIT = "83d7be718c99c1135302ccb4f8d339a4c68f292f"
FREEZE_SHA256 = "99387d9626ae13f20ef58f0a7f6624ebe850d8477ba17934c4f35735ca9eda16"
FREEZE_SCHEDULE_SHA256 = "1e45510b99e328388ea663ef42523d202322011959ad7f0e62629c3ec8075dfa"
GROK_EXECUTOR_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-grok-exec-v1"
GROK_EXECUTOR = HERE.parent / GROK_EXECUTOR_ID / "executor.py"
GROK_EXECUTOR_COMMIT = "4d3b2ef20f5fad4ea0974e888f37550d4b8480f2"
GROK_EXECUTOR_SHA256 = "d719d484fabc12110fe36f61c379edf8d15aa701f97f025d1ff2ac24f1d2f4a4"
OPTIMIZER_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-development-optimizer-v1"
OPTIMIZER = HERE.parent / OPTIMIZER_ID / "analyzer.py"
OPTIMIZER_CONTRACT = OPTIMIZER.parent / "study-contract.json"
OPTIMIZER_COMMIT = "4fe1329b05deb0030c80b5d0f1904d807cf6674e"
OPTIMIZER_SHA256 = "d70579f5bd5688f4a1e402bc53fc1c7e82501cf44814bda52ad36e34a6340176"
OPTIMIZER_CONTRACT_SHA256 = "599fc4e981604ffa139e68c0dcb479dd07598e1b6de12159530360028fcc7d10"
DESC16_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-exec-v1"
DESC16 = HERE.parent / DESC16_ID / "executor.py"
DESC16_COMMIT = "9f48ed828e49c640434008979606ccc838cef8da"
DESC16_SHA256 = "fd17b8b2079fe44eddea7aaa611ec6be649503af61ada62cc6f888bee548497c"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 10
RESULT_FILE_SHA256 = "da6f567763f4b4f0bece074a47bcf34a247e2c337dbaaee09f3ee9f69cd5aaa9"
RESULT_INTERNAL_SHA256 = "a399ca0f626cc62eccd352b256385d8892c5799455494b76ca5d539c1e3072a6"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    path = Path(path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not canonical JSON") from error
    if canonical(value) != raw or not isinstance(value, dict):
        raise ValueError(f"{label} is not canonical object JSON")
    return value


def _blob(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"pinned Git blob is unavailable: {relative}")
    return result.stdout


def _load(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest or _blob(commit, path) != raw:
        raise ValueError("pinned dependency drifted or is not committed")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned dependency cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def freeze_module() -> ModuleType:
    return _load(FREEZE, FREEZE_SHA256, FREEZE_COMMIT, "_desc18_sol_freeze")


def optimizer_module() -> ModuleType:
    module = _load(OPTIMIZER, OPTIMIZER_SHA256, OPTIMIZER_COMMIT, "_desc18_sol_optimizer")
    contract = stable(OPTIMIZER_CONTRACT)
    if sha256(contract) != OPTIMIZER_CONTRACT_SHA256 or _blob(OPTIMIZER_COMMIT, OPTIMIZER_CONTRACT) != contract:
        raise ValueError("pinned Desc18 optimizer contract drifted")
    module.validate_package()
    return module


def desc16_lifecycle() -> ModuleType:
    return _load(DESC16, DESC16_SHA256, DESC16_COMMIT, "_desc18_sol_lifecycle")


def _schedule(freeze_root: Path) -> dict[str, Any]:
    module = freeze_module()
    schedule = module.validate_frozen_root(Path(freeze_root))
    if schedule != module.materialize() or schedule.get("schedule_sha256") != FREEZE_SCHEDULE_SHA256:
        raise ValueError("frozen Desc18 schedule drifted")
    if schedule.get("geometry") != {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}:
        raise ValueError("Desc18 geometry drifted")
    return schedule


def _replay_optimizer(*, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    raw = stable(Path(grok_result_path))
    if sha256(raw) != RESULT_FILE_SHA256:
        raise ValueError("wrong immutable Desc18 optimizer result file")
    persisted = strict(raw, "Desc18 optimizer result")
    replayed = optimizer_module().analyze(output_root=Path(grok_execution_root), freeze_root=Path(freeze_root), collector_path=Path(grok_collector_path))
    if persisted != replayed or replayed.get("result_sha256") != RESULT_INTERNAL_SHA256:
        raise ValueError("Desc18 optimizer result differs from independent replay")
    qualification = replayed.get("qualification")
    if not isinstance(qualification, Mapping) or qualification.get("frozen_before_sol") is not True or qualification.get("parent_candidate_id") != PARENT:
        raise ValueError("Desc18 optimizer qualification drifted")
    qualifiers = qualification.get("qualifiers")
    if qualifiers not in ([], [CHILD]):
        raise ValueError("Desc18 optimizer qualifier surface drifted")
    return replayed


def _rows(schedule: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 64:
        raise ValueError("Desc18 schedule cell inventory drifted")
    rows: list[dict[str, Any]] = []
    for source in cells:
        if not isinstance(source, Mapping) or source.get("candidate_id") not in {PARENT, CHILD}:
            raise ValueError("Desc18 schedule candidate drifted")
        payload = base64.b64decode(source.get("payload_base64", ""), validate=True)
        if (sha256(payload) != source.get("payload_sha256")
                or source.get("endpoint_payload_sha256s") != {"grok_primary": source["payload_sha256"], "sol_veto_if_qualified": source["payload_sha256"]}
                or source.get("partition") != "open_validation_development"):
            raise ValueError("Desc18 exact Sol payload binding drifted")
        target = source.get("target")
        if not isinstance(target, Mapping) or set(target) != set(DIMENSIONS):
            raise ValueError("Desc18 target binding drifted")
        rows.append({
            "cell_id": "desc18-sol-veto-" + sha256({"source_cell_id": source["cell_id"]})[:16],
            "source_cell_id": source["cell_id"], "candidate_id": source["candidate_id"],
            "prompt_group_id": source["prompt_group_id"], "item_id": source["item_id"], "story_id": source["item_id"],
            "payload_base64": source["payload_base64"], "payload_sha256": source["payload_sha256"],
            "payload_parity": "frozen_desc18_schedule_exact_payload_bytes",
            "target": {name: float(target[name]) for name in DIMENSIONS},
        })
    pairs = {(row["candidate_id"], row["item_id"]) for row in rows}
    if len(rows) != 64 or len({row["cell_id"] for row in rows}) != 64 or pairs != {(candidate, row["item_id"]) for candidate in (PARENT, CHILD) for row in rows if row["candidate_id"] == PARENT}:
        raise ValueError("Desc18 matched Sol geometry drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _resolution(*, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    schedule = _schedule(Path(freeze_root))
    result = _replay_optimizer(
        grok_execution_root=Path(grok_execution_root), freeze_root=Path(freeze_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path),
    )
    qualification = result["qualification"]
    if qualification["qualifiers"] == []:
        return {"status": "not_qualified_zero_sol_calls", "schedule": schedule, "result": result}
    rows = _rows(schedule)
    return {
        "status": "qualified", "rows": rows, "schedule": schedule, "result": result,
        "qualification": qualification,
        "bindings": {
            "result_analyzer_commit": OPTIMIZER_COMMIT,
            "result_analyzer_sha256": OPTIMIZER_SHA256,
            "result_analyzer_contract_sha256": OPTIMIZER_CONTRACT_SHA256,
            "grok_result_sha256": RESULT_FILE_SHA256,
            "grok_result_internal_sha256": RESULT_INTERNAL_SHA256,
            "grok_execution_commit": GROK_EXECUTOR_COMMIT,
            "grok_executor_sha256": GROK_EXECUTOR_SHA256,
            "grok_collector_sha256": sha256(stable(Path(grok_collector_path))),
            "hanna_csv_sha256": FREEZE_SCHEDULE_SHA256,
            "replay_input_commitments": {
                "freeze_root": sha256(canonical(_schedule(Path(freeze_root)))),
                "grok_execution_root": str(Path(grok_execution_root).resolve()),
                "grok_collector": sha256(stable(Path(grok_collector_path))),
                "grok_result": sha256(stable(Path(grok_result_path))),
            },
            "parent_sol_reference": {
                "candidate_id": PARENT,
                "comparison": "same_wave_matched_open_validation_sol_veto",
                "source": "desc18_frozen_schedule",
            },
        },
        "parent_sol_reference": {"candidate_id": PARENT, "comparison": "same_wave_matched_open_validation_sol_veto", "source": "desc18_frozen_schedule"},
    }


def validate_response_quality(value: Mapping[str, Any]) -> dict[str, Any]:
    """Reject structurally valid but unusable score evidence before admission."""
    if set(value) != {"scores", "evidence", "coverage"}:
        raise ValueError("Sol response schema drifted")
    scores, evidence, coverage = value["scores"], value["evidence"], value["coverage"]
    if not isinstance(scores, Mapping) or not isinstance(evidence, Mapping) or not isinstance(coverage, Mapping) or set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS):
        raise ValueError("Sol response dimensions drifted")
    for dimension in DIMENSIONS:
        score = scores[dimension]
        text = evidence[dimension]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= float(score) <= 5:
            raise ValueError("Sol response score type/range drifted")
        if type(coverage[dimension]) is not bool or not isinstance(text, str):
            raise ValueError("Sol response evidence/coverage type drifted")
        normalized = " ".join(text.split()).casefold()
        if (not normalized or normalized in {"x", "n/a", "na", "none", "missing", "redacted", "[placeholder]", "placeholder"}
                or len(normalized) < 3
                or "placeholder" in normalized
                or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b", normalized)
                or re.search(r"\bworkspace (?:search|lookup)\b", normalized)
                or normalized.startswith(("file:", "source:", "http:", "https:", "\\\\", "/", "./", "../", "see attached", "see workspace", "workspace:", "path:"))):
            raise ValueError("Sol response evidence is placeholder or pointer-like")
    if all(float(scores[dimension]) == 0.0 for dimension in DIMENSIONS):
        raise ValueError("Sol response has an all-zero score vector")
    return dict(value)


def _configured_lifecycle(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    lifecycle = desc16_lifecycle()
    lifecycle.STUDY_ID = STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (CHILD,)
    lifecycle.PARENT_CANDIDATE_ID = PARENT
    lifecycle.RESULT_FILE_SHA256 = RESULT_FILE_SHA256
    lifecycle.RESULT_INTERNAL_SHA256 = RESULT_INTERNAL_SHA256
    runtime = lifecycle._configured_base(resolution)
    original = runtime._validate_answer

    def strict_answer(value: Mapping[str, Any]) -> dict[str, Any]:
        return validate_response_quality(original(value))

    runtime._validate_answer = strict_answer
    return lifecycle, runtime


def validate_package() -> dict[str, Any]:
    expected_files = {"README.md", "executor.py", "study-contract.json"}
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != expected_files:
        raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    expected = {
        "authority": {"confirmation": "unopened", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_qualification_frozen", "sol": "veto_only"},
        "format_version": 1,
        "geometry": {"max_concurrency": 10, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells_if_child20_qualifies": 64},
        "kind": "contingent_desc18_exact_schedule_payload_sol_veto",
        "frozen_optimizer_result": {"file_sha256": RESULT_FILE_SHA256, "internal_sha256": RESULT_INTERNAL_SHA256},
        "pinned_dependencies": {
            "desc16_sol_lifecycle": {"commit": DESC16_COMMIT, "executor_sha256": DESC16_SHA256},
            "desc18_freeze": {"commit": FREEZE_COMMIT, "schedule_sha256": FREEZE_SCHEDULE_SHA256},
            "desc18_grok_executor": {"commit": GROK_EXECUTOR_COMMIT, "executor_sha256": GROK_EXECUTOR_SHA256},
            "desc18_optimizer": {"analyzer_sha256": OPTIMIZER_SHA256, "commit": OPTIMIZER_COMMIT, "study_contract_sha256": OPTIMIZER_CONTRACT_SHA256},
        },
        "prohibitions": ["reconciliation and optimizer replay before route/root", "no fallback or resend", "no confirmation, reserve, promotion, runtime, endpoint pooling, or Sol-favored substitution"],
        "study_id": STUDY_ID,
    }
    if contract != expected:
        raise ValueError("study contract drifted")
    return contract


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_execution_root=grok_execution_root, freeze_root=freeze_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    if resolution["status"] != "qualified":
        return {"study_id": STUDY_ID, "state": "not_qualified_zero_sol_calls", "provider_calls_made": 0, "process_launches": 0, "output_root_created": False}
    output_root = Path(output_root)
    if output_root.exists():
        raise ValueError("fresh output root required")
    lifecycle, runtime = _configured_lifecycle(resolution)
    lifecycle._disjoint(output_root, HERE, REPO, Path(queue_root), Path(grok_execution_root), Path(freeze_root), Path(grok_collector_path), Path(grok_result_path))
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    output_root.mkdir(parents=True)
    for row in resolution["rows"]:
        root = output_root / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256).items():
            runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "state": "prepared_exact_64_matched_sol_veto_cells", "cells": 64, "groups": 16, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY}


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(grok_execution_root=grok_execution_root, freeze_root=freeze_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    if resolution["status"] != "qualified":
        return {"study_id": STUDY_ID, "state": "not_qualified_zero_sol_calls", "provider_calls_made": 0, "process_launches": 0}
    lifecycle, runtime = _configured_lifecycle(resolution)
    if cell_id not in {row["cell_id"] for row in resolution["rows"]}:
        raise ValueError("unknown Desc18 Sol veto cell")
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), Path(grok_execution_root), Path(freeze_root), Path(grok_collector_path), Path(grok_result_path))
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"])
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=next(row for row in resolution["rows"] if row["cell_id"] == cell_id), output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(grok_execution_root=grok_execution_root, freeze_root=freeze_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    if resolution["status"] != "qualified":
        return []
    lifecycle, runtime = _configured_lifecycle(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), Path(grok_execution_root), Path(freeze_root), Path(grok_collector_path), Path(grok_result_path))
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"])
    locks = lifecycle._locks(Path(output_root))

    def run(row: Mapping[str, Any]) -> dict[str, Any]:
        return lifecycle._execute_prepared(base=runtime, row=row, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)

    try:
        pending = tuple(row for row in resolution["rows"] if not lifecycle._terminal_state(runtime, Path(output_root) / row["cell_id"], row))
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, pending))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def _collector_output_disjoint(lifecycle: ModuleType, *, collector_output: Path, output_root: Path, queue_root: Path, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> None:
    lifecycle._disjoint(Path(collector_output), HERE, REPO, Path(output_root), Path(queue_root), Path(grok_execution_root), Path(freeze_root), Path(grok_collector_path), Path(grok_result_path))


def _validate_collector_shape(collector: Mapping[str, Any], acknowledgement: str) -> list[Mapping[str, Any]]:
    expected = {"format_version", "study_id", "kind", "authorization_acknowledgement_sha256", "optimizer_result_file_sha256", "optimizer_result_internal_sha256", "parent_candidate_id", "qualified_children", "route", "route_evidence", "cells", "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches"}
    if (set(collector) != expected or collector.get("format_version") != 1 or collector.get("study_id") != STUDY_ID or collector.get("kind") != "complete_desc18_matched_sol_veto_receipts_cardinality_unproven" or collector.get("authorization_acknowledgement_sha256") != acknowledgement or collector.get("optimizer_result_file_sha256") != RESULT_FILE_SHA256 or collector.get("optimizer_result_internal_sha256") != RESULT_INTERNAL_SHA256 or collector.get("parent_candidate_id") != PARENT or collector.get("qualified_children") != [CHILD] or collector.get("native_endpoint_contact_cardinality") != "unproven" or collector.get("provider_calls_made") is not None or collector.get("process_launches") != 64 or not isinstance(collector.get("cells"), list) or len(collector["cells"]) != 64):
        raise ValueError("Desc18 Sol collector drifted")
    return collector["cells"]


def _validate_collector_cell_shape(supplied: Mapping[str, Any]) -> None:
    expected = {"cell_id", "source_cell_id", "candidate_id", "payload_base64", "payload_sha256", "final_response_base64", "final_response_sha256", "receipt_sha256", "identity", "effective_settings", "effective_settings_sha256", "human_score_projection"}
    if set(supplied) != expected:
        raise ValueError("collector cell fields drifted")


def finalize_collector(*, output_root: Path, queue_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_execution_root=grok_execution_root, freeze_root=freeze_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    if resolution["status"] != "qualified":
        raise ValueError("no Sol collector exists without a frozen qualifier")
    if Path(collector_output).exists():
        raise ValueError("collector output must be fresh")
    lifecycle, runtime = _configured_lifecycle(resolution)
    _collector_output_disjoint(lifecycle, collector_output=Path(collector_output), output_root=Path(output_root), queue_root=Path(queue_root), grok_execution_root=Path(grok_execution_root), freeze_root=Path(freeze_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path))
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"], completed=True)
    v4 = lifecycle.sol_v4()
    cells, identities, route, route_evidence = [], set(), None, None
    for row in resolution["rows"]:
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, Path(output_root) / row["cell_id"], authorization_acknowledgement_sha256)
        if admitted["identity_key"] in identities:
            raise ValueError("duplicate Sol lifecycle identity")
        identities.add(admitted["identity_key"])
        if route is None:
            route, route_evidence = admitted["route"], admitted["route_evidence"]
        if admitted["route"] != route or admitted["route_evidence"] != route_evidence:
            raise ValueError("Sol route/evidence differs across cells")
        cells.append({"cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "payload_base64": base64.b64encode(admitted["payload"]).decode("ascii"), "payload_sha256": sha256(admitted["payload"]), "final_response_base64": base64.b64encode(admitted["final"]).decode("ascii"), "final_response_sha256": sha256(admitted["final"]), "receipt_sha256": sha256(admitted["receipt"]), "identity": admitted["identity"], "effective_settings": admitted["settings"], "effective_settings_sha256": sha256(admitted["settings"]), "human_score_projection": admitted["answer"]})
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_desc18_matched_sol_veto_receipts_cardinality_unproven", "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "optimizer_result_file_sha256": RESULT_FILE_SHA256, "optimizer_result_internal_sha256": RESULT_INTERNAL_SHA256, "parent_candidate_id": PARENT, "qualified_children": [CHILD], "route": route, "route_evidence": route_evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}
    runtime._write_new(Path(collector_output), canonical(value))
    return {"study_id": STUDY_ID, "collector_sha256": sha256(value), "cells": 64, "provider_calls_made": None, "process_launches": 64, "native_endpoint_contact_cardinality": "unproven"}


def replay_collector(*, output_root: Path, collector_path: Path, authorization_acknowledgement_sha256: str, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_execution_root=grok_execution_root, freeze_root=freeze_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    if resolution["status"] != "qualified":
        raise ValueError("no Sol collector exists without a frozen qualifier")
    lifecycle, runtime = _configured_lifecycle(resolution)
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"], completed=True)
    collector = strict(stable(Path(collector_path)), "Desc18 Sol collector")
    supplied_cells = _validate_collector_shape(collector, authorization_acknowledgement_sha256)
    v4, index, identities = lifecycle.sol_v4(), {row["cell_id"]: row for row in resolution["rows"]}, set()
    for supplied in supplied_cells:
        if not isinstance(supplied, Mapping):
            raise TypeError("collector cell drifted")
        _validate_collector_cell_shape(supplied)
        if supplied.get("cell_id") not in index:
            raise ValueError("collector cell drifted")
        row = index.pop(supplied["cell_id"])
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, Path(output_root) / row["cell_id"], authorization_acknowledgement_sha256)
        payload, final = base64.b64decode(supplied.get("payload_base64", ""), validate=True), base64.b64decode(supplied.get("final_response_base64", ""), validate=True)
        if (admitted["identity_key"] in identities or supplied.get("source_cell_id") != row["source_cell_id"] or supplied.get("candidate_id") != row["candidate_id"] or payload != admitted["payload"] or final != admitted["final"] or supplied.get("payload_sha256") != sha256(payload) or supplied.get("final_response_sha256") != sha256(final) or supplied.get("receipt_sha256") != sha256(admitted["receipt"]) or supplied.get("identity") != admitted["identity"] or supplied.get("effective_settings") != admitted["settings"] or supplied.get("effective_settings_sha256") != sha256(admitted["settings"]) or supplied.get("human_score_projection") != admitted["answer"] or admitted["route"] != collector["route"] or admitted["route_evidence"] != collector["route_evidence"]):
            raise ValueError("collector differs from persisted Sol receipt")
        identities.add(admitted["identity_key"])
    if index:
        raise ValueError("partial Desc18 Sol collector")
    return {"study_id": STUDY_ID, "collector_sha256": sha256(collector), "cells": 64, "provider_calls_made": None, "process_launches": 64, "native_endpoint_contact_cardinality": "unproven", "sol_role": "veto_only_no_outside_candidate_substitution", "confirmation_cells": 0}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute-one", action="store_true")
    modes.add_argument("--execute-wave", action="store_true")
    modes.add_argument("--finalize-collector", action="store_true")
    modes.add_argument("--replay-collector", action="store_true")
    for name in ("output-root", "queue-root", "grok-execution-root", "freeze-root", "grok-collector", "grok-result"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256")
    parser.add_argument("--cell-id")
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "queue_root": args.queue_root, "grok_execution_root": args.grok_execution_root, "freeze_root": args.freeze_root, "grok_collector_path": args.grok_collector, "grok_result_path": args.grok_result, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare:
        if args.allow_remote or not args.authorization_acknowledgement_sha256:
            parser.error("prepare requires acknowledgement and forbids remote execution")
        value = prepare_all(**common)
    elif args.execute_one:
        if not args.allow_remote or not args.cell_id or not args.authorization_acknowledgement_sha256:
            parser.error("execute-one requires acknowledgement, a cell, and explicit remote authorization")
        value = execute_one(**common, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote or not args.authorization_acknowledgement_sha256:
            parser.error("execute-wave requires acknowledgement and explicit remote authorization")
        value = execute_wave(**common, allow_remote=True)
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256:
            parser.error("finalize-collector requires acknowledgement/output and forbids remote execution")
        value = finalize_collector(**common, collector_output=args.collector_output)
    else:
        if args.allow_remote or not args.collector_path or not args.authorization_acknowledgement_sha256:
            parser.error("replay-collector requires acknowledgement/collector and forbids remote execution")
        value = replay_collector(**{key: item for key, item in common.items() if key != "queue_root"}, collector_path=args.collector_path)
    print(canonical(value).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
