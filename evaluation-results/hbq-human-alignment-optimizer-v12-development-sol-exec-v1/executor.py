"""Exact matched Sol-26 development measurement from complete V12 Grok receipts."""
from __future__ import annotations

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
STUDY_ID = "hbq-human-alignment-optimizer-v12-development-sol-exec-v1"
CONTRACT_PATH = HERE / "study-contract.json"
SOURCE = REPO / "evaluation-results/hbq-human-alignment-optimizer-v12-development-panel-v1/study.py"
SOURCE_SHA256 = "a1100bc16528287571d1b7198729124a705990ab7561385d271df27a7e2b7851"
SOURCE_COMMIT = "10d4251"
V9 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1/executor.py"
V9_SHA256 = "578a488b8b85b67705e7db1d560134a1c24714ab201efba336ca3611979e72b7"
V9_COMMIT = "926f8f1"
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 10


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    path = Path(path)
    before = os.lstat(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe source artifact")
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, before.st_size)
    if identity != (opened.st_dev, opened.st_ino, opened.st_size) or identity != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable source read drifted")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def _load(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = stable(path)
    relative = path.relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if sha256(raw) != digest or blob.returncode or blob.stdout != raw:
        raise ValueError("pinned dependency drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned dependency cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def validate_package() -> dict[str, Any]:
    expected_files = {"README.md", "executor.py", "study-contract.json"}
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != expected_files:
        raise ValueError("package inventory drifted")
    value = strict(stable(CONTRACT_PATH), "study contract")
    expected = {
        "authority": {"confirmation": "none", "development_only": True, "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none", "sol": "matched_measurement_only_after_complete_grok_receipts"},
        "format_version": 1,
        "geometry": {"candidates": 2, "groups": 7, "items": 13, "max_concurrency": 10, "sol_cells": 26},
        "kind": "v12_development_paired_sol_execution",
        "prohibitions": ["no candidate edits or confirmation", "no fallback or resend", "no endpoint pooling or caller aggregate", "no source-root writes"],
        "source": {"v12_study_commit": SOURCE_COMMIT, "v12_study_sha256": SOURCE_SHA256},
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("study contract drifted")
    return value


def _expected_sha256(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected Grok result SHA-256 is invalid")
    return value


def _resolution(
    *,
    grok_root: Path,
    grok_acknowledgement: str,
    grok_result_path: Path,
    expected_grok_result_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
) -> dict[str, Any]:
    source = _load(SOURCE, SOURCE_SHA256, SOURCE_COMMIT, "_v12_sol_source")
    source_paths = {
        "grok_root": Path(grok_root).resolve(),
        "grok_result": Path(grok_result_path).resolve(),
        "split_manifest": Path(split_manifest).resolve(),
        "hanna_csv": Path(hanna_csv).resolve(),
        "successor_contract": Path(successor_contract).resolve(),
    }
    expected_result_sha256 = _expected_sha256(expected_grok_result_sha256)
    persisted_raw = stable(source_paths["grok_result"])
    persisted = strict(persisted_raw, "expected V12 Grok result")
    if sha256(persisted_raw) != expected_result_sha256:
        raise ValueError("expected V12 Grok result SHA-256 differs")
    replay = source.report(
        output_root=source_paths["grok_root"],
        authorization_acknowledgement_sha256=grok_acknowledgement,
        split_manifest=source_paths["split_manifest"],
        hanna_csv=source_paths["hanna_csv"],
        successor_contract=source_paths["successor_contract"],
    )
    if replay != persisted or replay.get("endpoint") != "grok_primary" or replay.get("native_endpoint_contact_cardinality") != "unproven":
        raise ValueError("complete V12 Grok receipt replay differs from supplied result")
    schedule = source.schedule(
        split_manifest=source_paths["split_manifest"],
        hanna_csv=source_paths["hanna_csv"],
        successor_contract=source_paths["successor_contract"],
    )
    if (schedule.get("endpoint") != "grok_primary" or schedule.get("geometry") != {"candidates": 2, "development_groups": 7, "development_items": 13, "grok_cells": 26, "sol_cells": 0}
            or schedule.get("authority", {}).get("confirmation_access") != "forbidden_in_this_study"):
        raise ValueError("V12 source schedule authority or geometry drifted")
    received = {cell.get("cell_id"): cell for cell in replay.get("cells", []) if isinstance(cell, Mapping)}
    rows: list[dict[str, Any]] = []
    for source_row in schedule.get("cells", []):
        payload = base64.b64decode(source_row.get("payload_base64", ""), validate=True)
        received_cell = received.get(source_row.get("cell_id"))
        if (not isinstance(received_cell, Mapping) or sha256(payload) != source_row.get("payload_sha256")
                or received_cell.get("candidate_id") != source_row.get("candidate_id")
                or received_cell.get("item_id") != source_row.get("item_id")
                or received_cell.get("prompt_group_id") != source_row.get("prompt_group_id")
                or received_cell.get("target") != source_row.get("target")
                or source_row.get("partition") != "development"):
            raise ValueError("V12 Grok/Sol source-row binding drifted")
        rows.append({
            "cell_id": "v12-development-sol-" + sha256({"source_cell_id": source_row["cell_id"]})[:20],
            "source_cell_id": source_row["cell_id"],
            "candidate_id": source_row["candidate_id"],
            "item_id": source_row["item_id"],
            "story_id": source_row["item_id"],
            "prompt_group_id": source_row["prompt_group_id"],
            "partition": "development",
            "payload_base64": source_row["payload_base64"],
            "payload_sha256": source_row["payload_sha256"],
            "payload_parity": "v12_grok_schedule_exact_payload_bytes",
            "target": {name: float(source_row["target"][name]) for name in DIMS},
        })
    paired_items = {row["item_id"] for row in rows if row["candidate_id"] == BASELINE}
    if (len(rows) != 26 or len({row["cell_id"] for row in rows}) != 26
            or {(row["candidate_id"], row["item_id"]) for row in rows} != {(candidate, item) for candidate in (BASELINE, CHILD20) for item in paired_items}
            or len(paired_items) != 13):
        raise ValueError("V12 matched Sol-26 geometry drifted")
    return {
        "rows": tuple(sorted(rows, key=lambda row: row["cell_id"])),
        "schedule": schedule,
        "grok_result": replay,
        "source_paths": source_paths,
        "bindings": {
            "v12_study_commit": SOURCE_COMMIT,
            "v12_study_sha256": SOURCE_SHA256,
            "v12_grok_result_sha256": expected_result_sha256,
            "v12_grok_replayed_report_sha256": sha256(replay),
            "v12_schedule_sha256": schedule["schedule_sha256"],
        },
    }


def _runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    v9 = _load(V9, V9_SHA256, V9_COMMIT, "_v12_sol_lifecycle")
    compatibility = dict(resolution)
    bindings = dict(resolution["bindings"])
    grok_result_sha256 = bindings["v12_grok_result_sha256"]
    bindings.update({
        "result_analyzer_commit": "explicit_expected_v12_grok_result_sha256",
        "result_analyzer_sha256": grok_result_sha256,
        "result_analyzer_contract_sha256": grok_result_sha256,
        "grok_result_sha256": grok_result_sha256,
        "grok_result_internal_sha256": None,
        "grok_execution_commit": SOURCE_COMMIT,
        "grok_executor_sha256": SOURCE_SHA256,
        "grok_collector_sha256": bindings["v12_grok_replayed_report_sha256"],
        "hanna_csv_sha256": resolution["schedule"]["source"]["hanna_csv_sha256"],
        "parent_sol_reference": {
            "candidate_id": BASELINE,
            "comparison": "same_v12_development_matched_sol_only",
            "source": "complete_v12_grok_receipts",
        },
        "replay_input_commitments": {"v12_schedule": bindings["v12_schedule_sha256"], "v12_grok_result": grok_result_sha256},
    })
    compatibility["bindings"] = bindings
    lifecycle = v9.desc16_lifecycle()
    lifecycle.STUDY_ID = v9.STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (v9.CHILD,)
    lifecycle.PARENT_CANDIDATE_ID = v9.PARENT
    lifecycle.RESULT_FILE_SHA256 = v9.RESULT_FILE_SHA256
    lifecycle.RESULT_INTERNAL_SHA256 = v9.RESULT_INTERNAL_SHA256
    runtime = lifecycle._configured_base(compatibility)
    lifecycle.STUDY_ID = STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (BASELINE, CHILD20)
    lifecycle.PARENT_CANDIDATE_ID = BASELINE
    runtime.STUDY_ID = STUDY_ID
    runtime.SOURCE_RESULT_FILE_SHA256 = grok_result_sha256
    runtime.RESULT_INTERNAL_SHA256 = None
    base_validate_answer = runtime._validate_answer

    def v12_answer(value: Mapping[str, Any]) -> dict[str, Any]:
        return base_validate_answer(value)

    runtime._validate_answer = v12_answer
    inherited = runtime._prepared

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"])
        source = dict(value["source"])
        for key in ("frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256", "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256", "result_analyzer_contract_sha256"):
            source.pop(key, None)
        source.update({
            "v12_grok_result_sha256": grok_result_sha256,
            "v12_study_sha256": SOURCE_SHA256,
            "v12_schedule_sha256": resolution["bindings"]["v12_schedule_sha256"],
            "sol_role": "matched_development_measurement_after_complete_grok_receipts",
            "endpoint_pooling": "forbidden",
            "selection": "none",
            "promotion": "none",
            "generalization": "none",
        })
        value["source"] = source
        files["prepared.json"] = runtime.canonical(value)
        return files

    runtime._prepared = prepared
    return lifecycle, runtime


def _prepare(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), SOURCE, *resolution["source_paths"].values())
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "state": "prepared_exact_26_matched_sol_development_cells", "cells": 26, "groups": 7, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY}


def prepare_all(*, grok_root: Path, grok_acknowledgement: str, grok_result_path: Path, expected_grok_result_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, grok_result_path=Path(grok_result_path), expected_grok_result_sha256=expected_grok_result_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    return _prepare(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=broker_factory)


def _execute(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    lifecycle, runtime = _runtime(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown V12 Sol cell")
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), SOURCE, *resolution["source_paths"].values())
    lifecycle._prepared_inventory(runtime, Path(output_root), tuple(rows.values()))
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_one(*, grok_root: Path, grok_acknowledgement: str, grok_result_path: Path, expected_grok_result_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, grok_result_path=Path(grok_result_path), expected_grok_result_sha256=expected_grok_result_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    return _execute(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=broker_factory, call_codex=call_codex)


def execute_wave(*, grok_root: Path, grok_acknowledgement: str, grok_result_path: Path, expected_grok_result_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, grok_result_path=Path(grok_result_path), expected_grok_result_sha256=expected_grok_result_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), SOURCE, *resolution["source_paths"].values())
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"])
    locks = lifecycle._locks(Path(output_root))
    try:
        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            return lifecycle._execute_prepared(base=runtime, row=row, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, resolution["rows"]))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def report(*, grok_root: Path, grok_acknowledgement: str, grok_result_path: Path, expected_grok_result_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, grok_result_path=Path(grok_result_path), expected_grok_result_sha256=expected_grok_result_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    lifecycle, runtime = _runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), resolution["rows"])
    v4 = lifecycle.sol_v4()
    route = evidence = None
    threads: set[str] = set()
    sessions: set[str] = set()
    cells: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {BASELINE: {}, CHILD20: {}}
    required_items: dict[str, set[str]] = {}
    for row in resolution["rows"]:
        if row["candidate_id"] == BASELINE:
            required_items.setdefault(row["prompt_group_id"], set()).add(row["item_id"])
    for row in resolution["rows"]:
        root = entries[row["cell_id"]]
        if "execution-receipt.json" not in {path.name for path in root.iterdir()}:
            raise ValueError("incomplete Sol terminal receipts cannot aggregate")
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, root, authorization_acknowledgement_sha256)
        identity, settings, answer = admitted["identity"], admitted["settings"], admitted["answer"]
        if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or not isinstance(answer, Mapping):
            raise TypeError("invalid admitted Sol receipt")
        thread, session = identity.get("thread_id"), identity.get("session_id")
        if (not isinstance(thread, str) or not thread or not isinstance(session, str) or not session
                or thread in threads or session in sessions):
            raise ValueError("duplicate or invalid Sol identity")
        threads.add(thread)
        sessions.add(session)
        cell_route, cell_evidence = admitted["route"], admitted["route_evidence"]
        if route is None:
            route, evidence = cell_route, cell_evidence
        elif cell_route != route or cell_evidence != evidence:
            raise ValueError("mixed Sol route or evidence")
        if (set(answer.get("scores", {})) != set(DIMS) or set(answer.get("coverage", {})) != set(DIMS)
                or any(type(answer["coverage"][name]) is not bool or type(answer["scores"][name]) not in {int, float} or not math.isfinite(float(answer["scores"][name])) for name in DIMS)):
            raise ValueError("Sol numeric score or coverage drifted")
        per_item_mae = sum(abs(float(answer["scores"][name]) - float(row["target"][name])) for name in DIMS) / len(DIMS)
        cell = {
            "cell_id": row["cell_id"],
            "source_cell_id": row["source_cell_id"],
            "candidate_id": row["candidate_id"],
            "item_id": row["item_id"],
            "prompt_group_id": row["prompt_group_id"],
            "partition": "development",
            "payload_sha256": row["payload_sha256"],
            "final_response_sha256": sha256(admitted["final"]),
            "receipt_sha256": sha256(admitted["receipt"]),
            "effective_settings_sha256": sha256(settings),
            "scores": {name: float(answer["scores"][name]) for name in DIMS},
            "coverage": dict(answer["coverage"]),
            "target": dict(row["target"]),
            "per_item_mae": per_item_mae,
        }
        candidate_groups = grouped.get(row["candidate_id"])
        if candidate_groups is None:
            raise ValueError("unexpected Sol candidate")
        candidate_groups.setdefault(row["prompt_group_id"], []).append(cell)
        cells.append(cell)
    if route is None or evidence is None or len(cells) != 26 or len(threads) != 26 or len(sessions) != 26:
        raise ValueError("incomplete Sol-26 report geometry")
    v4._frozen_route(route, evidence, runtime._load_v3(), require_unexpired=False)
    source = _load(SOURCE, SOURCE_SHA256, SOURCE_COMMIT, "_v12_sol_report_source")
    metrics: list[dict[str, Any]] = []
    correlations: dict[str, Any] = {}
    for candidate in (BASELINE, CHILD20):
        by_group = grouped[candidate]
        if set(by_group) != set(required_items):
            raise ValueError("incomplete V12 Sol development group coverage")
        for group, item_ids in required_items.items():
            if len(by_group[group]) != len(item_ids) or {row["item_id"] for row in by_group[group]} != item_ids:
                raise ValueError("ambiguous V12 Sol item grouping")
        group_mae = {
            group: sum(row["per_item_mae"] for row in by_group[group]) / len(by_group[group])
            for group in sorted(by_group)
        }
        candidate_cells = [row for row in cells if row["candidate_id"] == candidate]
        metrics.append({
            "candidate_id": candidate,
            "per_group_mean_item_mae": group_mae,
            "equal_group_mean_item_mae": sum(group_mae.values()) / len(group_mae),
            "item_count": 13,
            "group_count": 7,
        })
        correlations[candidate] = source._rank_records(candidate_cells, by_group)
    baseline, child = metrics
    primary_baseline = baseline["equal_group_mean_item_mae"]
    primary_child = child["equal_group_mean_item_mae"]
    authority = dict(validate_package()["authority"])
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "receipt_derived_26_cell_sol_development_report",
        "endpoint": "sol_later",
        "partition": "development",
        "authority": authority,
        "analysis_rule": source.contract()["analysis_rule"],
        "native_endpoint_contact_cardinality": "unproven",
        "v12_grok_result_sha256": resolution["bindings"]["v12_grok_result_sha256"],
        "v12_schedule_sha256": resolution["bindings"]["v12_schedule_sha256"],
        "cells": cells,
        "unique_thread_ids": len(threads),
        "unique_session_ids": len(sessions),
        "metrics": metrics,
        "rank_correlations": correlations,
        "comparison": {
            "baseline_candidate_id": BASELINE,
            "child_candidate_id": CHILD20,
            "child20_minus_baseline": primary_child - primary_baseline,
            "relative_reduction": (primary_baseline - primary_child) / primary_baseline if primary_baseline else None,
            "strict_primary_mae_improvement": primary_child < primary_baseline,
        },
        "interpretation": "development_measurement_only; no_selection_or_promotion; no_automatic_confirmation_or_grok_dispatch",
    }


if __name__ == "__main__":
    raise SystemExit("Use the callable API; Sol execution requires an explicit reviewed invocation.")
