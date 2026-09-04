"""Exact V11 TRAIN Sol-8 measurement, gated by independently replayed Grok receipts."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v11-train-sol-exec-v1"
SOURCE = REPO / "evaluation-results/hbq-human-alignment-optimizer-v11-child20-train-screen-v1/study.py"
SOURCE_SHA256 = "af2d326934f51ddb83b6449a760295f46921c87189c653558de37930af018f11"
SOURCE_COMMIT = "dc7b59a"
GROK_RESULT = REPO / "evaluation-results/hbq-human-alignment-optimizer-v11-train-grok-result-v1/result.json"
GROK_RESULT_SHA256 = "6366de64754c365c4d91a9117d8c174f771ad50062ef342f11996cddfa78c58e"
GROK_RESULT_COMMIT = "0759e7c"
V9 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1/executor.py"
V9_SHA256 = "578a488b8b85b67705e7db1d560134a1c24714ab201efba336ca3611979e72b7"
V9_COMMIT = "926f8f1"
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 8


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    path = Path(path)
    before = os.lstat(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe source artifact")
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
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
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def validate_package() -> dict[str, Any]:
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != {"README.md", "executor.py", "study-contract.json"}:
        raise ValueError("package inventory drifted")
    value = strict(stable(HERE / "study-contract.json"), "study contract")
    expected = {"authority": {"confirmation": "none", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none", "sol": "matched_measurement_only_after_grok_gate"}, "format_version": 1, "geometry": {"candidates": 2, "groups": 4, "items": 4, "max_concurrency": 8, "sol_cells": 8}, "kind": "v11_train_paired_sol_execution", "prohibitions": ["no candidate edits or confirmation", "no fallback or resend", "no endpoint pooling or caller aggregate", "no source-root writes"], "study_id": STUDY_ID}
    if value != expected:
        raise ValueError("study contract drifted")
    return value


def _resolution(*, grok_root: Path, grok_acknowledgement: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    source = _load(SOURCE, SOURCE_SHA256, SOURCE_COMMIT, "_v11_sol_source")
    source_paths = {"grok_root": Path(grok_root).resolve(), "split_manifest": Path(split_manifest).resolve(), "hanna_csv": Path(hanna_csv).resolve(), "successor_contract": Path(successor_contract).resolve()}
    result_raw = stable(GROK_RESULT)
    result_blob = subprocess.run(["git", "-C", str(REPO), "show", f"{GROK_RESULT_COMMIT}:{GROK_RESULT.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    persisted = strict(result_raw, "committed Grok result")
    if sha256(result_raw) != GROK_RESULT_SHA256 or result_blob.returncode or result_blob.stdout != result_raw:
        raise ValueError("committed Grok result drifted")
    replay = source.report(output_root=source_paths["grok_root"], authorization_acknowledgement_sha256=grok_acknowledgement, split_manifest=source_paths["split_manifest"], hanna_csv=source_paths["hanna_csv"], successor_contract=source_paths["successor_contract"])
    if replay != persisted or replay.get("endpoint") != "grok_primary" or replay.get("partition") != "train":
        raise ValueError("Grok receipt replay differs from committed V11 result")
    gate = replay.get("later_matched_sol8_gate", {})
    if gate.get("sole_gate") != "strict_child20_mean_mae_improvement" or gate.get("satisfied") is not True:
        raise ValueError("Grok result does not open matched Sol-8 measurement")
    schedule = source.schedule(split_manifest=source_paths["split_manifest"], hanna_csv=source_paths["hanna_csv"], successor_contract=source_paths["successor_contract"])
    received = {cell["cell_id"]: cell for cell in replay.get("cells", []) if isinstance(cell, Mapping)}
    rows = []
    for source_row in schedule.get("cells", []):
        payload = base64.b64decode(source_row.get("payload_base64", ""), validate=True)
        received_cell = received.get(source_row.get("cell_id"))
        if (not isinstance(received_cell, Mapping) or sha256(payload) != source_row.get("payload_sha256")
                or received_cell.get("candidate_id") != source_row.get("candidate_id")
                or received_cell.get("item_id", source_row.get("item_id")) != source_row.get("item_id")
                or received_cell.get("prompt_group_id") != source_row.get("prompt_group_id")
                or received_cell.get("target") != source_row.get("target") or source_row.get("partition") != "train"):
            raise ValueError("V11 Grok/Sol source-row binding drifted")
        rows.append({"cell_id": "v11-train-sol-" + sha256({"source_cell_id": source_row["cell_id"]})[:20], "source_cell_id": source_row["cell_id"], "candidate_id": source_row["candidate_id"], "item_id": source_row["item_id"], "story_id": source_row["item_id"], "prompt_group_id": source_row["prompt_group_id"], "partition": "train", "payload_base64": source_row["payload_base64"], "payload_sha256": source_row["payload_sha256"], "payload_parity": "v11_grok_schedule_exact_payload_bytes", "target": {name: float(source_row["target"][name]) for name in DIMS}})
    if len(rows) != 8 or len({row["cell_id"] for row in rows}) != 8 or {(row["candidate_id"], row["item_id"]) for row in rows} != {(candidate, row["item_id"]) for candidate in (BASELINE, CHILD20) for row in rows if row["candidate_id"] == BASELINE}:
        raise ValueError("V11 matched Sol-8 geometry drifted")
    return {"rows": tuple(sorted(rows, key=lambda row: row["cell_id"])), "schedule": schedule, "grok_result": replay, "source_paths": source_paths, "bindings": {"v11_study_commit": SOURCE_COMMIT, "v11_study_sha256": SOURCE_SHA256, "v11_grok_result_commit": GROK_RESULT_COMMIT, "v11_grok_result_sha256": GROK_RESULT_SHA256, "grok_replayed_report_sha256": sha256(replay), "parent_sol_reference": {"candidate_id": BASELINE, "comparison": "same_v11_train_matched_sol_only", "source": "v11_grok_receipts"}}}


def _runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    v9 = _load(V9, V9_SHA256, V9_COMMIT, "_v11_sol_lifecycle")
    compatibility = dict(resolution)
    bindings = dict(resolution["bindings"])
    bindings.update({"result_analyzer_commit": GROK_RESULT_COMMIT, "result_analyzer_sha256": GROK_RESULT_SHA256, "result_analyzer_contract_sha256": GROK_RESULT_SHA256, "grok_result_sha256": GROK_RESULT_SHA256, "grok_result_internal_sha256": None, "grok_execution_commit": SOURCE_COMMIT, "grok_executor_sha256": SOURCE_SHA256, "grok_collector_sha256": resolution["bindings"]["grok_replayed_report_sha256"], "hanna_csv_sha256": resolution["schedule"]["source"]["hanna_csv_sha256"], "replay_input_commitments": {"v11_schedule": resolution["schedule"]["schedule_sha256"], "v11_grok_result": GROK_RESULT_SHA256}})
    compatibility["bindings"] = bindings
    lifecycle, runtime = v9._configured_lifecycle(compatibility)
    lifecycle.STUDY_ID = STUDY_ID; lifecycle.QUALIFIED_CHILDREN = (BASELINE, CHILD20); lifecycle.PARENT_CANDIDATE_ID = BASELINE
    runtime.STUDY_ID = STUDY_ID; runtime.SOURCE_RESULT_FILE_SHA256 = GROK_RESULT_SHA256; runtime.RESULT_INTERNAL_SHA256 = None
    inherited = runtime._prepared

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"])
        source = dict(value["source"])
        for key in ("frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256", "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256", "result_analyzer_contract_sha256"):
            source.pop(key, None)
        source.update({"v11_grok_result_sha256": GROK_RESULT_SHA256, "v11_study_sha256": SOURCE_SHA256, "sol_role": "matched_measurement_only_after_grok_gate", "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "generalization": "none"})
        value["source"] = source; files["prepared.json"] = runtime.canonical(value)
        return files

    runtime._prepared = prepared
    return lifecycle, runtime


def _prepare(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), GROK_RESULT, SOURCE, *resolution["source_paths"].values())
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "state": "prepared_exact_8_matched_sol_train_cells", "cells": 8, "groups": 4, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY}


def prepare_all(*, grok_root: Path, grok_acknowledgement: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    return _prepare(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=broker_factory)


def _execute(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    lifecycle, runtime = _runtime(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown V11 Sol cell")
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), GROK_RESULT, SOURCE, *resolution["source_paths"].values())
    lifecycle._prepared_inventory(runtime, Path(output_root), tuple(rows.values()))
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_one(*, grok_root: Path, grok_acknowledgement: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    return _execute(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=broker_factory, call_codex=call_codex)


def execute_wave(*, grok_root: Path, grok_acknowledgement: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), GROK_RESULT, SOURCE, *resolution["source_paths"].values())
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


def report(*, grok_root: Path, grok_acknowledgement: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, output_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(grok_root=Path(grok_root), grok_acknowledgement=grok_acknowledgement, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    lifecycle, runtime = _runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), resolution["rows"])
    v4 = lifecycle.sol_v4()
    route = evidence = None
    threads: set[str] = set()
    sessions: set[str] = set()
    cells = []
    group_errors: dict[str, dict[str, float]] = {BASELINE: {}, CHILD20: {}}
    for row in resolution["rows"]:
        root = entries[row["cell_id"]]
        if "execution-receipt.json" not in {path.name for path in root.iterdir()}:
            raise ValueError("incomplete Sol terminal receipts cannot aggregate")
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, root, authorization_acknowledgement_sha256)
        identity, settings, answer = admitted["identity"], admitted["settings"], admitted["answer"]
        if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or not isinstance(answer, Mapping):
            raise TypeError("invalid admitted Sol receipt")
        thread, session = identity.get("thread_id"), identity.get("session_id")
        if not isinstance(thread, str) or not thread or not isinstance(session, str) or not session or thread in threads or session in sessions:
            raise ValueError("duplicate or invalid Sol identity")
        threads.add(thread); sessions.add(session)
        cell_route, cell_evidence = admitted["route"], admitted["route_evidence"]
        if route is None:
            route, evidence = cell_route, cell_evidence
        elif cell_route != route or cell_evidence != evidence:
            raise ValueError("mixed Sol route or evidence")
        if any(type(answer["coverage"][name]) is not bool or type(answer["scores"][name]) not in {int, float} or not math.isfinite(float(answer["scores"][name])) for name in DIMS):
            raise ValueError("Sol numeric score or coverage drifted")
        mae = sum(abs(float(answer["scores"][name]) - row["target"][name]) for name in DIMS) / len(DIMS)
        groups = group_errors[row["candidate_id"]]
        if row["prompt_group_id"] in groups:
            raise ValueError("ambiguous Sol group pairing")
        groups[row["prompt_group_id"]] = mae
        cells.append({"cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "payload_sha256": row["payload_sha256"], "final_response_sha256": sha256(admitted["final"]), "receipt_sha256": sha256(admitted["receipt"]), "effective_settings_sha256": sha256(settings), "scores": {name: float(answer["scores"][name]) for name in DIMS}, "coverage": dict(answer["coverage"]), "target": dict(row["target"]), "mae": mae})
    required_groups = {entry["prompt_group_id"] for entry in resolution["schedule"]["groups"]}
    if route is None or evidence is None or len(cells) != 8 or len(threads) != 8 or len(sessions) != 8 or any(set(groups) != required_groups for groups in group_errors.values()):
        raise ValueError("incomplete Sol-8 report geometry")
    v4._frozen_route(route, evidence, runtime._load_v3(), require_unexpired=False)
    metrics = []
    for candidate in (BASELINE, CHILD20):
        group_mae = dict(sorted(group_errors[candidate].items()))
        metrics.append({"candidate_id": candidate, "equal_group_mae": sum(group_mae.values()) / 4, "group_mae": group_mae})
    baseline, child = metrics
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_8_cell_sol_train_report", "endpoint": "sol_later", "partition": "train", "native_endpoint_contact_cardinality": "unproven", "grok_gate_result_sha256": GROK_RESULT_SHA256, "cells": cells, "unique_thread_ids": len(threads), "unique_session_ids": len(sessions), "metrics": metrics, "comparison": {"baseline_candidate_id": BASELINE, "child_candidate_id": CHILD20, "child20_minus_baseline": child["equal_group_mae"] - baseline["equal_group_mae"], "relative_reduction": (baseline["equal_group_mae"] - child["equal_group_mae"]) / baseline["equal_group_mae"] if baseline["equal_group_mae"] else None}, "authority": {"confirmation": "none", "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"}}


if __name__ == "__main__":
    raise SystemExit("Use the callable API; Sol execution requires an explicit reviewed invocation.")
