"""V14 remaining-TRAIN Sol measurement over a frozen 88-cell expansion schedule."""
from __future__ import annotations

import base64
import importlib.util
import json
import math
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v14-dspy-train-expansion-sol-v1"
BASE = HERE / "sol.py"
BASE_SHA256 = "ac84ce7af8797b7e19feb79ec4026a4e68ae7f973e70e7e851cb70d9886c27b2"
BASE_COMMIT = "932ddbd"
EXPANSION = HERE / "expansion.py"
EXPANSION_SHA256 = "359fc5a9d4b60ab8c8b42f30c7c3598d7742fabf22962bc133db372716174e05"
EXPANSION_COMMIT = "8bd2f09"
EXPANSION_CONTRACT = HERE / "expansion-contract.json"
EXPANSION_CONTRACT_SHA256 = "065a21294586df4982b791b13cb4431799de16bf4e39a56f9ff9c8cf66789f00"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 10


def _base() -> ModuleType:
    raw = BASE.read_bytes()
    if __import__("hashlib").sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError("pinned V14 Sol composition drifted")
    import subprocess
    blob = subprocess.run(["git", "-C", str(HERE.parents[1]), "show", f"{BASE_COMMIT}:{BASE.relative_to(HERE.parents[1]).as_posix()}"], capture_output=True, check=False)
    if blob.returncode or blob.stdout != raw:
        raise ValueError("pinned V14 Sol commit drifted")
    spec = importlib.util.spec_from_file_location("_v14_expansion_base", BASE)
    if spec is None or spec.loader is None:
        raise ValueError("pinned V14 Sol composition cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(base: ModuleType) -> ModuleType:
    if re.fullmatch(r"[0-9a-f]{64}", EXPANSION_SHA256) is None or re.fullmatch(r"[0-9a-f]{7,64}", EXPANSION_COMMIT) is None:
        raise ValueError("V14 expansion source pin is unresolved; expansion Sol cannot run")
    return base._load(EXPANSION, EXPANSION_SHA256, EXPANSION_COMMIT, "_v14_expansion_source")


def validate_package() -> dict[str, Any]:
    base = _base()
    source = _source(base)
    contract = source.contract()
    geometry = {"candidates": 2, "grok_cells": 88, "groups": 22, "items": 44, "max_concurrency": 10, "sol_cells": 0}
    if (base.sha256(base.stable(EXPANSION_CONTRACT)) != EXPANSION_CONTRACT_SHA256
            or not isinstance(contract, Mapping) or source.STUDY_ID != "hbq-human-alignment-optimizer-v14-dspy-train-expansion-v1"
            or contract.get("geometry") != geometry
            or contract.get("authority", {}).get("endpoint_pooling") != "forbidden"
            or contract.get("authority", {}).get("confirmation") != "none"):
        raise ValueError("V14 expansion contract drifted")
    return dict(contract)


def _resolution(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Any]:
    base = _base()
    source = _source(base)
    paths = {
        "split_manifest": Path(split_manifest).resolve(), "hanna_csv": Path(hanna_csv).resolve(),
        "successor_contract": Path(successor_contract).resolve(), "recovered_descendant": Path(recovered_descendant).resolve(),
    }
    schedule = source.schedule(
        split_manifest=paths["split_manifest"], hanna_csv=paths["hanna_csv"],
        successor_contract=paths["successor_contract"], recovered_descendant=paths["recovered_descendant"],
    )
    expected_geometry = {"candidates": 2, "grok_cells": 88, "groups": 22, "items": 44, "max_concurrency": 10, "sol_cells": 0}
    commitment = dict(schedule) if isinstance(schedule, Mapping) else {}
    schedule_sha256 = commitment.pop("schedule_sha256", None)
    if (not isinstance(schedule, Mapping) or schedule.get("geometry") != expected_geometry or schedule.get("endpoint") != "grok_primary"
            or schedule.get("authority", {}).get("endpoint_pooling") != "forbidden" or schedule.get("authority", {}).get("confirmation") != "none"
            or schedule_sha256 != base.sha256(commitment)):
        raise ValueError("V14 expansion frozen schedule drifted")
    rows: list[dict[str, Any]] = []
    for source_row in schedule.get("cells", []):
        if not isinstance(source_row, Mapping):
            raise TypeError("V14 expansion schedule cell is invalid")
        try:
            payload = base64.b64decode(source_row["payload_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("V14 expansion schedule payload is invalid") from error
        target = source_row.get("target")
        if (source_row.get("candidate_id") not in {CHILD20, DESCENDANT} or not isinstance(source_row.get("cell_id"), str)
                or not isinstance(source_row.get("item_id"), str) or not isinstance(source_row.get("prompt_group_id"), str)
                or source_row.get("partition") != "train" or source_row.get("payload_sha256") != base.sha256(payload)
                or source_row.get("endpoint_payload_sha256s") != {"grok_primary": base.sha256(payload), "sol_later": base.sha256(payload)}
                or not isinstance(target, Mapping) or set(target) != set(DIMS)):
            raise ValueError("V14 expansion source-row binding drifted")
        numeric_target = {name: float(target[name]) for name in DIMS}
        if any(type(target[name]) not in {int, float} or isinstance(target[name], bool) or not math.isfinite(value) for name, value in numeric_target.items()):
            raise ValueError("V14 expansion target is invalid")
        rows.append({
            "cell_id": "v14-expansion-sol-" + base.sha256({"source_cell_id": source_row["cell_id"]})[:20],
            "source_cell_id": source_row["cell_id"], "candidate_id": source_row["candidate_id"], "item_id": source_row["item_id"],
            "story_id": source_row["item_id"], "prompt_group_id": source_row["prompt_group_id"], "partition": "train",
            "payload_base64": source_row["payload_base64"], "payload_sha256": base.sha256(payload),
            "payload_parity": "v14_expansion_grok_schedule_exact_payload_bytes", "target": numeric_target,
        })
    child_items = {row["item_id"] for row in rows if row["candidate_id"] == CHILD20}
    descendant_items = {row["item_id"] for row in rows if row["candidate_id"] == DESCENDANT}
    groups = {row["prompt_group_id"] for row in rows}
    if (len(rows) != 88 or len({row["cell_id"] for row in rows}) != 88 or len(child_items) != 44
            or child_items != descendant_items or len(groups) != 22):
        raise ValueError("V14 expansion matched Sol-88 geometry drifted")
    return {"base": base, "rows": tuple(sorted(rows, key=lambda row: row["cell_id"])), "schedule": schedule, "source_paths": paths, "bindings": {"expansion_study_commit": EXPANSION_COMMIT, "expansion_study_sha256": EXPANSION_SHA256, "expansion_schedule_sha256": schedule_sha256, "recovered_descendant_sha256": base.sha256(base.stable(paths["recovered_descendant"])), "hanna_csv_sha256": base.sha256(base.stable(paths["hanna_csv"]))}}


def _runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    base = resolution["base"]
    v9 = base._load(base.V9, base.V9_SHA256, base.V9_COMMIT, "_v14_expansion_sol_lifecycle")
    bindings = dict(resolution["bindings"])
    bindings.update({
        "result_analyzer_commit": "not_applicable_direct_frozen_schedule",
        "result_analyzer_sha256": bindings["expansion_schedule_sha256"],
        "result_analyzer_contract_sha256": bindings["expansion_schedule_sha256"],
        "grok_result_sha256": bindings["expansion_schedule_sha256"], "grok_result_internal_sha256": None,
        "grok_execution_commit": EXPANSION_COMMIT, "grok_executor_sha256": EXPANSION_SHA256,
        "grok_collector_sha256": bindings["expansion_schedule_sha256"], "hanna_csv_sha256": bindings["hanna_csv_sha256"],
        "parent_sol_reference": {"candidate_id": CHILD20, "comparison": "same_v14_expansion_train_frozen_schedule_matched_sol_only", "source": "v14_expansion_frozen_schedule"},
        "replay_input_commitments": {"expansion_schedule": bindings["expansion_schedule_sha256"], "recovered_descendant": bindings["recovered_descendant_sha256"]},
    })
    compatibility = dict(resolution); compatibility["bindings"] = bindings
    lifecycle = v9.desc16_lifecycle()
    lifecycle.STUDY_ID = v9.STUDY_ID; lifecycle.QUALIFIED_CHILDREN = (v9.CHILD,); lifecycle.PARENT_CANDIDATE_ID = v9.PARENT
    lifecycle.RESULT_FILE_SHA256 = v9.RESULT_FILE_SHA256; lifecycle.RESULT_INTERNAL_SHA256 = v9.RESULT_INTERNAL_SHA256
    runtime = lifecycle._configured_base(compatibility)
    lifecycle.STUDY_ID = STUDY_ID; lifecycle.QUALIFIED_CHILDREN = (CHILD20, DESCENDANT); lifecycle.PARENT_CANDIDATE_ID = CHILD20
    runtime.STUDY_ID = STUDY_ID; runtime.SOURCE_RESULT_FILE_SHA256 = bindings["expansion_schedule_sha256"]; runtime.RESULT_INTERNAL_SHA256 = None
    inherited = runtime._prepared

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"]); source = dict(value["source"])
        for key in ("frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256", "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256", "result_analyzer_contract_sha256"):
            source.pop(key, None)
        source.update({"expansion_study_sha256": EXPANSION_SHA256, "expansion_schedule_sha256": bindings["expansion_schedule_sha256"], "recovered_descendant_sha256": bindings["recovered_descendant_sha256"], "sol_role": "matched_train_measurement_on_v14_expansion_frozen_schedule", "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "generalization": "none"})
        value["source"] = source; files["prepared.json"] = runtime.canonical(value)
        return files

    runtime._prepared = prepared
    return lifecycle, runtime


def _source_roots(resolution: Mapping[str, Any]) -> tuple[Path, ...]:
    return tuple(path if path.is_dir() else path.parent for path in resolution["source_paths"].values())


def _prepare(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, broker_factory: Callable[[Path], Any] | None) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, HERE.parents[1], Path(queue_root), BASE, EXPANSION, *_source_roots(resolution))
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory)
    Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]; root.mkdir()
        payload = base64.b64decode(row["payload_base64"], validate=True)
        schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement).items():
            runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "state": "prepared_exact_88_matched_sol_train_cells", "cells": 88, "groups": 22, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY}


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path | None = None, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    validate_package(); base = _base()
    resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant) if recovered_descendant is not None else base.RECOVERED_DESCENDANT)
    return _prepare(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, broker_factory=broker_factory)


def _execute(*, resolution: Mapping[str, Any], output_root: Path, queue_root: Path, acknowledgement: str, cell_id: str, broker_factory: Callable[[Path], Any] | None, call_codex: Callable[..., Any] | None) -> dict[str, Any]:
    lifecycle, runtime = _runtime(resolution); rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown V14 expansion Sol cell")
    lifecycle._disjoint(Path(output_root), HERE, HERE.parents[1], Path(queue_root), BASE, EXPANSION, *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), tuple(rows.values())); locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(base=runtime, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=acknowledgement, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()): locks.rmdir()


def execute_one(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, cell_id: str, allow_remote: bool, recovered_descendant: Path | None = None, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("execution requires explicit allow_remote=True")
    base = _base(); resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant) if recovered_descendant is not None else base.RECOVERED_DESCENDANT)
    return _execute(resolution=resolution, output_root=Path(output_root), queue_root=Path(queue_root), acknowledgement=authorization_acknowledgement_sha256, cell_id=cell_id, broker_factory=broker_factory, call_codex=call_codex)


def execute_wave(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, allow_remote: bool, recovered_descendant: Path | None = None, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True: raise ValueError("execution requires explicit allow_remote=True")
    base = _base(); resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant) if recovered_descendant is not None else base.RECOVERED_DESCENDANT)
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, HERE.parents[1], Path(queue_root), BASE, EXPANSION, *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"]); locks = lifecycle._locks(Path(output_root))
    try:
        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            return lifecycle._execute_prepared(base=runtime, row=row, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, resolution["rows"]))
    finally:
        if locks.exists() and not any(locks.iterdir()): locks.rmdir()


def report(*, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path | None = None) -> dict[str, Any]:
    base = _base(); resolution = _resolution(split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant) if recovered_descendant is not None else base.RECOVERED_DESCENDANT)
    lifecycle, runtime = _runtime(resolution); entries = lifecycle._output_inventory(Path(output_root), resolution["rows"]); v4 = lifecycle.sol_v4()
    route = evidence = None; threads: set[str] = set(); sessions: set[str] = set(); cells: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {CHILD20: {}, DESCENDANT: {}}; required_items: dict[str, set[str]] = {}
    for row in resolution["rows"]:
        if row["candidate_id"] == CHILD20: required_items.setdefault(row["prompt_group_id"], set()).add(row["item_id"])
    for row in resolution["rows"]:
        root = entries[row["cell_id"]]
        if "execution-receipt.json" not in {path.name for path in root.iterdir()}: raise ValueError("incomplete Sol terminal receipts cannot aggregate")
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, root, authorization_acknowledgement_sha256)
        identity, settings, answer = admitted["identity"], admitted["settings"], admitted["answer"]
        if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or not isinstance(answer, Mapping): raise TypeError("invalid admitted Sol receipt")
        thread, session = identity.get("thread_id"), identity.get("session_id")
        if not isinstance(thread, str) or not thread or not isinstance(session, str) or not session or thread in threads or session in sessions: raise ValueError("duplicate or invalid Sol identity")
        threads.add(thread); sessions.add(session); cell_route, cell_evidence = admitted["route"], admitted["route_evidence"]
        if route is None: route, evidence = cell_route, cell_evidence
        elif cell_route != route or cell_evidence != evidence: raise ValueError("mixed Sol route or evidence")
        if set(answer.get("scores", {})) != set(DIMS) or set(answer.get("coverage", {})) != set(DIMS) or any(type(answer["coverage"][name]) is not bool or type(answer["scores"][name]) not in {int, float} or not math.isfinite(float(answer["scores"][name])) for name in DIMS): raise ValueError("Sol numeric score or coverage drifted")
        per_item_mae = sum(abs(float(answer["scores"][name]) - float(row["target"][name])) for name in DIMS) / len(DIMS)
        cell = {"cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "partition": "train", "payload_sha256": row["payload_sha256"], "final_response_sha256": base.sha256(admitted["final"]), "receipt_sha256": base.sha256(admitted["receipt"]), "effective_settings_sha256": base.sha256(settings), "scores": {name: float(answer["scores"][name]) for name in DIMS}, "coverage": dict(answer["coverage"]), "target": dict(row["target"]), "per_item_mae": per_item_mae}
        grouped[row["candidate_id"]].setdefault(row["prompt_group_id"], []).append(cell); cells.append(cell)
    if route is None or evidence is None or len(cells) != 88 or len(threads) != 88 or len(sessions) != 88: raise ValueError("incomplete Sol-88 report geometry")
    v4._frozen_route(route, evidence, runtime._load_v3(), require_unexpired=False)
    metrics: list[dict[str, Any]] = []
    for candidate in (CHILD20, DESCENDANT):
        by_group = grouped[candidate]
        if set(by_group) != set(required_items): raise ValueError("incomplete V14 expansion Sol TRAIN group coverage")
        for group, item_ids in required_items.items():
            if len(by_group[group]) != len(item_ids) or {cell["item_id"] for cell in by_group[group]} != item_ids: raise ValueError("ambiguous V14 expansion Sol item grouping")
        group_mae = {group: sum(cell["per_item_mae"] for cell in by_group[group]) / len(by_group[group]) for group in sorted(by_group)}
        metrics.append({"candidate_id": candidate, "per_group_mean_item_mae": group_mae, "equal_group_mean_item_mae": sum(group_mae.values()) / len(group_mae), "item_count": 44, "group_count": 22})
    child, descendant = metrics; child_mae, descendant_mae = child["equal_group_mean_item_mae"], descendant["equal_group_mean_item_mae"]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_88_cell_sol_train_expansion_report", "endpoint": "sol_later", "partition": "train", "native_endpoint_contact_cardinality": "unproven", "expansion_schedule_sha256": resolution["bindings"]["expansion_schedule_sha256"], "recovered_descendant_sha256": resolution["bindings"]["recovered_descendant_sha256"], "cells": cells, "unique_thread_ids": len(threads), "unique_session_ids": len(sessions), "metrics": metrics, "comparison": {"child20_candidate_id": CHILD20, "descendant_candidate_id": DESCENDANT, "descendant_minus_child20": descendant_mae - child_mae, "relative_reduction": (child_mae - descendant_mae) / child_mae if child_mae else None, "strict_primary_mae_improvement": descendant_mae < child_mae}, "authority": {"confirmation": "none", "development_in_sample_only": True, "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"}, "interpretation": "separate_sol_measurement_only; no_selection_or_promotion; no_automatic_dispatch_or_confirmation"}


if __name__ == "__main__":
    raise SystemExit("Use the callable API; Sol execution requires an explicit reviewed invocation.")
