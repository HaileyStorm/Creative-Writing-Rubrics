"""Matched V14 Sol measurement over the frozen child20/DSPy TRAIN schedule only."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v14-dspy-train-pilot-sol-v1"
SOURCE = HERE / "study.py"
CONTRACT_PATH = HERE / "study-contract.json"
SOURCE_SHA256 = "4446c2b3e1472039b2aa0c607cfe84656aa5504d3fe37ae428945a1f7b62fc3f"
SOURCE_COMMIT = "f28db1b"
CONTRACT_SHA256 = "d92013a659f494547053d2737459a7715247894b113f60669b2fdf761ff2e8b3"
V9 = REPO / "evaluation-results/hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1/executor.py"
V9_SHA256 = "578a488b8b85b67705e7db1d560134a1c24714ab201efba336ca3611979e72b7"
V9_COMMIT = "926f8f1"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
RECOVERED_DESCENDANT = Path(r"C:\Users\Haile\Documents\cwr-hanna-dspy-proposal-recovery-cbe403dd-20260904-r1\recovered-descendant.json")
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 8


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    value = Path(path)
    before = os.lstat(value)
    if value.is_symlink() or not value.is_file():
        raise ValueError("unsafe source artifact")
    with value.open("rb") as handle:
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


def _pin(value: str, label: str) -> str:
    if re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} is unresolved; V14 Sol cannot run before source freeze")
    return value


def _load(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    pinned = _pin(digest, "source SHA-256")
    if not re.fullmatch(r"[0-9a-f]{7,64}", commit):
        raise ValueError("source commit is unresolved; V14 Sol cannot run before source freeze")
    raw = stable(path)
    relative = path.relative_to(REPO).as_posix()
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if sha256(raw) != pinned or blob.returncode or blob.stdout != raw:
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
    source = _load(SOURCE, SOURCE_SHA256, SOURCE_COMMIT, "_v14_sol_source_contract")
    contract = source.contract()
    expected_geometry = {"candidates": 2, "grok_cells": 8, "groups": 4, "items": 4, "max_concurrency": 10, "sol_cells": 0}
    if (sha256(stable(CONTRACT_PATH)) != CONTRACT_SHA256 or not isinstance(contract, Mapping)
            or contract.get("study_id") != "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
            or contract.get("geometry") != expected_geometry or contract.get("authority", {}).get("endpoint_pooling") != "forbidden"
            or contract.get("authority", {}).get("confirmation") != "none"):
        raise ValueError("V14 source contract drifted")
    return dict(contract)


def _resolution(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Any]:
    source = _load(SOURCE, SOURCE_SHA256, SOURCE_COMMIT, "_v14_sol_source")
    source_paths = {
        "split_manifest": Path(split_manifest).resolve(),
        "hanna_csv": Path(hanna_csv).resolve(),
        "successor_contract": Path(successor_contract).resolve(),
        "recovered_descendant": Path(recovered_descendant).resolve(),
    }
    schedule = source.schedule(
        split_manifest=source_paths["split_manifest"], hanna_csv=source_paths["hanna_csv"],
        successor_contract=source_paths["successor_contract"], recovered_descendant=source_paths["recovered_descendant"],
    )
    expected_geometry = {"candidates": 2, "grok_cells": 8, "groups": 4, "items": 4, "max_concurrency": 10, "sol_cells": 0}
    schedule_commitment = dict(schedule) if isinstance(schedule, Mapping) else {}
    schedule_sha256 = schedule_commitment.pop("schedule_sha256", None)
    if (not isinstance(schedule, Mapping) or schedule.get("study_id") != "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
            or schedule.get("endpoint") != "grok_primary" or schedule.get("geometry") != expected_geometry
            or schedule.get("authority", {}).get("endpoint_pooling") != "forbidden"
            or schedule.get("authority", {}).get("confirmation") != "none" or schedule_sha256 != sha256(schedule_commitment)):
        raise ValueError("V14 frozen schedule authority or geometry drifted")
    rows: list[dict[str, Any]] = []
    seen_payloads: dict[tuple[str, str], bytes] = {}
    for source_row in schedule.get("cells", []):
        if not isinstance(source_row, Mapping):
            raise TypeError("V14 schedule cell is invalid")
        try:
            payload = base64.b64decode(source_row["payload_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("V14 schedule payload is invalid") from error
        candidate_id = source_row.get("candidate_id")
        item_id = source_row.get("item_id")
        target = source_row.get("target")
        if (candidate_id not in {CHILD20, DESCENDANT} or not isinstance(source_row.get("cell_id"), str)
                or not source_row.get("cell_id") or not isinstance(item_id, str) or not item_id
                or not isinstance(source_row.get("prompt_group_id"), str) or not source_row.get("prompt_group_id")
                or source_row.get("partition") != "train" or source_row.get("payload_sha256") != sha256(payload)
                or source_row.get("endpoint_payload_sha256s") != {"grok_primary": sha256(payload), "sol_later": sha256(payload)}
                or not isinstance(target, Mapping) or set(target) != set(DIMS)):
            raise ValueError("V14 frozen schedule row binding drifted")
        numeric_target = {name: float(target[name]) for name in DIMS}
        if any(type(target[name]) not in {int, float} or isinstance(target[name], bool) or not math.isfinite(value) for name, value in numeric_target.items()):
            raise ValueError("V14 target is not finite")
        key = (str(candidate_id), item_id)
        if key in seen_payloads:
            raise ValueError("duplicate V14 candidate/item schedule row")
        seen_payloads[key] = payload
        rows.append({
            "cell_id": "v14-train-sol-" + sha256({"source_cell_id": source_row.get("cell_id")})[:20],
            "source_cell_id": source_row.get("cell_id"), "candidate_id": candidate_id, "item_id": item_id,
            "story_id": item_id, "prompt_group_id": source_row.get("prompt_group_id"), "partition": "train",
            "payload_base64": source_row["payload_base64"], "payload_sha256": sha256(payload),
            "payload_parity": "v14_grok_schedule_exact_payload_bytes", "target": numeric_target,
        })
    child_items = {row["item_id"] for row in rows if row["candidate_id"] == CHILD20}
    descendant_items = {row["item_id"] for row in rows if row["candidate_id"] == DESCENDANT}
    groups = {row["prompt_group_id"] for row in rows}
    if (len(rows) != 8 or len({row["cell_id"] for row in rows}) != 8 or len(child_items) != 4
            or child_items != descendant_items or len(groups) != 4 or any(not isinstance(group, str) or not group for group in groups)):
        raise ValueError("V14 matched Sol-8 geometry drifted")
    return {
        "rows": tuple(sorted(rows, key=lambda row: row["cell_id"])), "schedule": schedule, "source_paths": source_paths,
        "bindings": {"v14_study_commit": SOURCE_COMMIT, "v14_study_sha256": SOURCE_SHA256, "v14_schedule_sha256": schedule_sha256, "recovered_descendant_sha256": sha256(stable(source_paths["recovered_descendant"])), "hanna_csv_sha256": sha256(stable(source_paths["hanna_csv"]))},
    }


def _runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    v9 = _load(V9, V9_SHA256, V9_COMMIT, "_v14_sol_lifecycle")
    compatibility = dict(resolution)
    bindings = dict(resolution["bindings"])
    bindings.update({
        "result_analyzer_commit": "not_applicable_direct_frozen_schedule",
        "result_analyzer_sha256": bindings["v14_schedule_sha256"],
        "result_analyzer_contract_sha256": bindings["v14_schedule_sha256"],
        "grok_result_sha256": bindings["v14_schedule_sha256"],
        "grok_result_internal_sha256": None,
        "grok_execution_commit": SOURCE_COMMIT,
        "grok_executor_sha256": SOURCE_SHA256,
        "grok_collector_sha256": bindings["v14_schedule_sha256"],
        "hanna_csv_sha256": bindings["hanna_csv_sha256"],
        "parent_sol_reference": {
            "candidate_id": CHILD20,
            "comparison": "same_v14_train_frozen_schedule_matched_sol_only",
            "source": "v14_frozen_schedule",
        },
        "replay_input_commitments": {"v14_schedule": bindings["v14_schedule_sha256"], "recovered_descendant": bindings["recovered_descendant_sha256"]},
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
    lifecycle.QUALIFIED_CHILDREN = (CHILD20, DESCENDANT)
    lifecycle.PARENT_CANDIDATE_ID = CHILD20
    runtime.STUDY_ID = STUDY_ID
    runtime.SOURCE_RESULT_FILE_SHA256 = bindings["v14_schedule_sha256"]
    runtime.RESULT_INTERNAL_SHA256 = None
    inherited = runtime._prepared

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"])
        source = dict(value["source"])
        for key in (
            "frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256",
            "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256",
            "result_analyzer_contract_sha256",
        ):
            source.pop(key, None)
        source.update({
            "v14_study_sha256": SOURCE_SHA256,
            "v14_schedule_sha256": resolution["bindings"]["v14_schedule_sha256"],
            "recovered_descendant_sha256": resolution["bindings"]["recovered_descendant_sha256"],
            "sol_role": "matched_train_measurement_on_v14_frozen_schedule",
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


def _source_roots(resolution: Mapping[str, Any]) -> tuple[Path, ...]:
    return tuple(path if path.is_dir() else path.parent for path in resolution["source_paths"].values())


def _prepare(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), SOURCE, *_source_roots(resolution))
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]
        root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            runtime._write_new(root / name, raw)
    return {
        "study_id": STUDY_ID, "state": "prepared_exact_8_matched_sol_train_cells", "cells": 8, "groups": 4,
        "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY,
    }


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path = RECOVERED_DESCENDANT, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
    return _prepare(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=broker_factory)


def _execute(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    lifecycle, runtime = _runtime(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown V14 Sol cell")
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), SOURCE, *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), tuple(rows.values()))
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, cell_id: str, allow_remote: bool, recovered_descendant: Path = RECOVERED_DESCENDANT, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
    return _execute(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=broker_factory, call_codex=call_codex)


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, recovered_descendant: Path = RECOVERED_DESCENDANT, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), SOURCE, *_source_roots(resolution))
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


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path = RECOVERED_DESCENDANT) -> dict[str, Any]:
    """Produce Sol-only receipt metrics; this never combines Grok measurements."""
    validate_package()
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant))
    lifecycle, runtime = _runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), resolution["rows"])
    v4 = lifecycle.sol_v4()
    route = evidence = None
    threads: set[str] = set()
    sessions: set[str] = set()
    cells: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {CHILD20: {}, DESCENDANT: {}}
    required_items: dict[str, set[str]] = {}
    for row in resolution["rows"]:
        if row["candidate_id"] == CHILD20:
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
            "cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"],
            "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train",
            "payload_sha256": row["payload_sha256"], "final_response_sha256": sha256(admitted["final"]),
            "receipt_sha256": sha256(admitted["receipt"]), "effective_settings_sha256": sha256(settings),
            "scores": {name: float(answer["scores"][name]) for name in DIMS}, "coverage": dict(answer["coverage"]),
            "target": dict(row["target"]), "per_item_mae": per_item_mae,
        }
        grouped[row["candidate_id"]].setdefault(row["prompt_group_id"], []).append(cell)
        cells.append(cell)
    if route is None or evidence is None or len(cells) != 8 or len(threads) != 8 or len(sessions) != 8:
        raise ValueError("incomplete Sol-8 report geometry")
    v4._frozen_route(route, evidence, runtime._load_v3(), require_unexpired=False)
    metrics: list[dict[str, Any]] = []
    for candidate in (CHILD20, DESCENDANT):
        by_group = grouped[candidate]
        if set(by_group) != set(required_items):
            raise ValueError("incomplete V14 Sol TRAIN group coverage")
        for group, item_ids in required_items.items():
            if len(by_group[group]) != len(item_ids) or {cell["item_id"] for cell in by_group[group]} != item_ids:
                raise ValueError("ambiguous V14 Sol item grouping")
        group_mae = {group: sum(cell["per_item_mae"] for cell in by_group[group]) / len(by_group[group]) for group in sorted(by_group)}
        metrics.append({"candidate_id": candidate, "per_group_mean_item_mae": group_mae, "equal_group_mean_item_mae": sum(group_mae.values()) / len(group_mae), "item_count": 4, "group_count": 4})
    child, descendant = metrics
    child_mae, descendant_mae = child["equal_group_mean_item_mae"], descendant["equal_group_mean_item_mae"]
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_8_cell_sol_train_pilot_report",
        "endpoint": "sol_later", "partition": "train", "native_endpoint_contact_cardinality": "unproven",
        "v14_schedule_sha256": resolution["bindings"]["v14_schedule_sha256"],
        "recovered_descendant_sha256": resolution["bindings"]["recovered_descendant_sha256"],
        "cells": cells, "unique_thread_ids": len(threads), "unique_session_ids": len(sessions), "metrics": metrics,
        "comparison": {"child20_candidate_id": CHILD20, "descendant_candidate_id": DESCENDANT, "descendant_minus_child20": descendant_mae - child_mae, "relative_reduction": (child_mae - descendant_mae) / child_mae if child_mae else None, "strict_primary_mae_improvement": descendant_mae < child_mae},
        "authority": {"confirmation": "none", "development_in_sample_only": True, "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"},
        "interpretation": "separate_sol_measurement_only; no_selection_or_promotion; no_automatic_dispatch_or_confirmation",
    }


if __name__ == "__main__":
    raise SystemExit("Use the callable API; Sol execution requires an explicit reviewed invocation.")
