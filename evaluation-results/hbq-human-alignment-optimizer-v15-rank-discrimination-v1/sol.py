"""Separate Sol measurement over V15's frozen rank-discrimination schedule."""
from __future__ import annotations

import base64
import importlib.util
import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v15-rank-discrimination-sol-v1"
BASE = REPO / "evaluation-results/hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1/sol.py"
BASE_SHA256 = "ac84ce7af8797b7e19feb79ec4026a4e68ae7f973e70e7e851cb70d9886c27b2"
BASE_COMMIT = "932ddbd"
SOURCE = HERE / "study.py"
SOURCE_SHA256 = "4afeaff679efaf37e702c08841eb30a3317693e677ecfc3ded4dbb4ae4710caf"
SOURCE_COMMIT = "3b28c30"
SOURCE_CONTRACT = HERE / "experiment-contract.json"
SOURCE_CONTRACT_SHA256 = "de0fed9eefa6791e7d063a3f8bde759ab723000a436702c48c1e6ad3e4a0a24b"
CONTRACT = HERE / "sol-contract.json"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
DIRECT, THRESHOLDS = "direct_integer", "ordinal_thresholds"
MAX_CONCURRENCY = 10


def _base() -> ModuleType:
    raw = BASE.read_bytes()
    if __import__("hashlib").sha256(raw).hexdigest() != BASE_SHA256:
        raise ValueError("pinned V14 Sol lifecycle drifted")
    blob = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE_COMMIT}:{BASE.relative_to(REPO).as_posix()}"],
        capture_output=True,
        check=False,
    )
    if blob.returncode or blob.stdout != raw:
        raise ValueError("pinned V14 Sol lifecycle commit drifted")
    spec = importlib.util.spec_from_file_location("_v15_sol_base", BASE)
    if spec is None or spec.loader is None:
        raise ValueError("pinned V14 Sol lifecycle cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source(base: ModuleType) -> ModuleType:
    if re.fullmatch(r"[0-9a-f]{64}", SOURCE_SHA256) is None or re.fullmatch(r"[0-9a-f]{7,64}", SOURCE_COMMIT) is None:
        raise ValueError("V15 Grok study pin is unresolved; Sol composition cannot run")
    return base._load(SOURCE, SOURCE_SHA256, SOURCE_COMMIT, "_v15_rank_source")


def contract() -> dict[str, Any]:
    base = _base()
    value = base.strict(base.stable(CONTRACT), "V15 Sol contract")
    expected = {
        "authority": {"confirmation": "none", "development_train_only": True, "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none", "sol": "separate_later_validation_only"},
        "format_version": 1,
        "geometry": {"conditions": 2, "grok_cells": 96, "groups": 24, "items": 48, "max_concurrency": 10, "sol_cells": 96},
        "kind": "matched_hanna_rank_discrimination_train_sol_measurement",
        "source": {"grok_experiment_contract_sha256": SOURCE_CONTRACT_SHA256, "grok_study_commit": SOURCE_COMMIT, "grok_study_sha256": SOURCE_SHA256},
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("V15 Sol contract drifted")
    return value


def validate_package() -> dict[str, Any]:
    base = _base()
    source = _source(base)
    expected_geometry = {"conditions": 2, "grok_cells": 96, "groups": 24, "items": 48, "max_concurrency": 10, "sol_cells": 0}
    if (
        base.sha256(base.stable(SOURCE_CONTRACT)) != SOURCE_CONTRACT_SHA256
        or source.STUDY_ID != "hbq-human-alignment-optimizer-v15-rank-discrimination-v1"
        or source.contract().get("geometry") != expected_geometry
        or source.contract().get("authority", {}).get("endpoint_pooling") != "forbidden"
        or source.contract().get("authority", {}).get("confirmation") != "none"
    ):
        raise ValueError("V15 Grok study contract drifted")
    return contract()


def _resolution(*, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    base = _base()
    source = _source(base)
    paths = {
        "split_manifest": Path(split_manifest).resolve(),
        "hanna_csv": Path(hanna_csv).resolve(),
        "successor_contract": Path(successor_contract).resolve(),
    }
    schedule = source.schedule(**paths)
    expected_geometry = {"conditions": 2, "grok_cells": 96, "groups": 24, "items": 48, "max_concurrency": 10, "sol_cells": 0}
    commitment = dict(schedule) if isinstance(schedule, Mapping) else {}
    schedule_sha256 = commitment.pop("schedule_sha256", None)
    if (
        not isinstance(schedule, Mapping)
        or schedule.get("geometry") != expected_geometry
        or schedule.get("endpoint") != "grok_primary"
        or schedule.get("authority", {}).get("endpoint_pooling") != "forbidden"
        or schedule.get("authority", {}).get("confirmation") != "none"
        or schedule_sha256 != base.sha256(commitment)
    ):
        raise ValueError("V15 frozen Grok schedule drifted")
    rows: list[dict[str, Any]] = []
    for source_row in schedule.get("cells", []):
        if not isinstance(source_row, Mapping):
            raise TypeError("V15 schedule cell is invalid")
        try:
            payload = base64.b64decode(source_row["payload_base64"], validate=True)
            body = json.loads(payload.decode("utf-8"))
        except (KeyError, TypeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("V15 schedule payload is invalid") from error
        target = source_row.get("target")
        if (
            source_row.get("condition") not in {DIRECT, THRESHOLDS}
            or not isinstance(source_row.get("cell_id"), str)
            or not isinstance(source_row.get("item_id"), str)
            or not isinstance(source_row.get("prompt_group_id"), str)
            or source_row.get("partition") != "train"
            or source_row.get("payload_sha256") != base.sha256(payload)
            or source_row.get("endpoint_payload_sha256s") != {"grok_primary": base.sha256(payload), "sol_later": base.sha256(payload)}
            or not isinstance(target, Mapping)
            or set(target) != set(DIMS)
            or not isinstance(body, Mapping)
            or set(body.get("writing", {})) != {"prompt", "story"}
            or "target" in body
            or "target" in body.get("writing", {})
        ):
            raise ValueError("V15 source-row binding drifted")
        numeric_target = {name: float(target[name]) for name in DIMS}
        if any(
            type(target[name]) not in {int, float}
            or isinstance(target[name], bool)
            or not math.isfinite(value)
            for name, value in numeric_target.items()
        ):
            raise ValueError("V15 target is invalid")
        rows.append(
            {
                "cell_id": "v15-sol-" + base.sha256({"source_cell_id": source_row["cell_id"]})[:20],
                "source_cell_id": source_row["cell_id"],
                "condition": source_row["condition"],
                "candidate_id": source_row["condition"],
                "item_id": source_row["item_id"],
                "story_id": source_row["item_id"],
                "prompt_group_id": source_row["prompt_group_id"],
                "partition": "train",
                "payload_base64": source_row["payload_base64"],
                "payload_sha256": base.sha256(payload),
                "payload_parity": "v15_grok_schedule_exact_payload_bytes",
                "target": numeric_target,
            }
        )
    groups = {row["prompt_group_id"] for row in rows}
    direct = {row["item_id"] for row in rows if row["condition"] == DIRECT}
    thresholds = {row["item_id"] for row in rows if row["condition"] == THRESHOLDS}
    if (
        len(rows) != 96
        or len({row["cell_id"] for row in rows}) != 96
        or len(groups) != 24
        or len(direct) != 48
        or direct != thresholds
        or sum(row["condition"] == DIRECT for row in rows) != 48
        or sum(row["condition"] == THRESHOLDS for row in rows) != 48
    ):
        raise ValueError("V15 matched Sol-96 geometry drifted")
    return {
        "base": base,
        "rows": tuple(sorted(rows, key=lambda row: row["cell_id"])),
        "schedule": schedule,
        "source_paths": paths,
        "bindings": {
            "grok_study_commit": SOURCE_COMMIT,
            "grok_study_sha256": SOURCE_SHA256,
            "grok_schedule_sha256": schedule_sha256,
            "grok_experiment_contract_sha256": SOURCE_CONTRACT_SHA256,
            "hanna_csv_sha256": base.sha256(base.stable(paths["hanna_csv"])),
        },
    }


def _source_roots(resolution: Mapping[str, Any]) -> tuple[Path, ...]:
    return tuple(path if path.is_dir() else path.parent for path in resolution["source_paths"].values())


def _runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    base = resolution["base"]
    source = _source(base)
    v9 = base._load(base.V9, base.V9_SHA256, base.V9_COMMIT, "_v15_sol_lifecycle")
    bindings = dict(resolution["bindings"])
    bindings.update(
        {
            "result_analyzer_commit": "not_applicable_direct_frozen_schedule",
            "result_analyzer_sha256": bindings["grok_schedule_sha256"],
            "result_analyzer_contract_sha256": bindings["grok_schedule_sha256"],
            "grok_result_sha256": bindings["grok_schedule_sha256"],
            "grok_result_internal_sha256": None,
            "grok_execution_commit": SOURCE_COMMIT,
            "grok_executor_sha256": SOURCE_SHA256,
            "grok_collector_sha256": bindings["grok_schedule_sha256"],
            "parent_sol_reference": {
                "candidate_id": DIRECT,
                "comparison": "same_v15_rank_discrimination_train_frozen_schedule_matched_sol_only",
                "source": "v15_frozen_schedule",
            },
            "replay_input_commitments": {"v15_schedule": bindings["grok_schedule_sha256"]},
        }
    )
    compatibility = dict(resolution)
    compatibility["bindings"] = bindings
    lifecycle = v9.desc16_lifecycle()
    lifecycle.STUDY_ID = v9.STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (v9.CHILD,)
    lifecycle.PARENT_CANDIDATE_ID = v9.PARENT
    lifecycle.RESULT_FILE_SHA256 = v9.RESULT_FILE_SHA256
    lifecycle.RESULT_INTERNAL_SHA256 = v9.RESULT_INTERNAL_SHA256
    runtime = lifecycle._configured_base(compatibility)
    lifecycle.STUDY_ID = STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (DIRECT, THRESHOLDS)
    lifecycle.PARENT_CANDIDATE_ID = DIRECT
    runtime.STUDY_ID = STUDY_ID
    runtime.SOURCE_RESULT_FILE_SHA256 = bindings["grok_schedule_sha256"]
    runtime.RESULT_INTERNAL_SHA256 = None

    def v15_answer(value: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise TypeError("V15 Sol final response is not an object")
        for condition in (DIRECT, THRESHOLDS):
            try:
                source._validate_answer(condition, value)
            except (TypeError, ValueError):
                continue
            return dict(value)
        raise ValueError("V15 Sol final response does not match either frozen response schema")

    runtime._validate_answer = v15_answer
    inherited = runtime._prepared

    def prepared(
        row: Mapping[str, Any],
        payload: bytes,
        schema: bytes,
        target: Mapping[str, float],
        route: Mapping[str, Any],
        evidence: Mapping[str, Any],
        acknowledgement: str,
    ) -> dict[str, bytes]:
        files = inherited(row, payload, schema, target, route, evidence, acknowledgement)
        value = json.loads(files["prepared.json"])
        source = dict(value["source"])
        for key in (
            "frozen_grok_qualifiers",
            "parent_sol_reference",
            "sol_role",
            "independently_replayed_grok_result_sha256",
            "independently_replayed_grok_result_internal_sha256",
            "result_analyzer_commit",
            "result_analyzer_sha256",
            "result_analyzer_contract_sha256",
        ):
            source.pop(key, None)
        source.update(
            {
                "grok_study_sha256": SOURCE_SHA256,
                "grok_schedule_sha256": bindings["grok_schedule_sha256"],
                "grok_experiment_contract_sha256": SOURCE_CONTRACT_SHA256,
                "sol_role": "matched_train_measurement_on_v15_rank_discrimination_frozen_schedule",
                "endpoint_pooling": "forbidden",
                "selection": "none",
                "promotion": "none",
                "generalization": "none",
            }
        )
        value["source"] = source
        files["prepared.json"] = runtime.canonical(value)
        return files

    runtime._prepared = prepared
    return lifecycle, runtime


def _prepare(
    *,
    resolution: Mapping[str, Any],
    output_root: Path,
    queue_root: Path,
    acknowledgement: str,
    broker_factory: Callable[[Path], Any] | None,
) -> dict[str, Any]:
    if Path(output_root).exists():
        raise ValueError("fresh output root required")
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), BASE, SOURCE, CONTRACT, *_source_roots(resolution))
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
        "study_id": STUDY_ID,
        "state": "prepared_exact_96_matched_sol_train_cells",
        "cells": 96,
        "groups": 24,
        "provider_calls_made": 0,
        "process_launches": 0,
        "max_concurrency": MAX_CONCURRENCY,
    }


def prepare_all(
    *,
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    broker_factory: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract)
    )
    return _prepare(
        resolution=resolution,
        output_root=Path(output_root),
        queue_root=Path(queue_root),
        acknowledgement=authorization_acknowledgement_sha256,
        broker_factory=broker_factory,
    )


def _execute(
    *,
    resolution: Mapping[str, Any],
    output_root: Path,
    queue_root: Path,
    acknowledgement: str,
    cell_id: str,
    broker_factory: Callable[[Path], Any] | None,
    call_codex: Callable[..., Any] | None,
) -> dict[str, Any]:
    lifecycle, runtime = _runtime(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows:
        raise ValueError("unknown V15 Sol cell")
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), BASE, SOURCE, CONTRACT, *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), tuple(rows.values()))
    locks = lifecycle._locks(Path(output_root))
    try:
        return lifecycle._execute_prepared(
            base=runtime,
            row=rows[cell_id],
            output_root=Path(output_root),
            queue_root=Path(queue_root),
            authorization_acknowledgement_sha256=acknowledgement,
            allow_remote=True,
            locks=locks,
            broker_factory=broker_factory,
            call_codex=call_codex,
        )
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def execute_one(
    *,
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    cell_id: str,
    allow_remote: bool,
    broker_factory: Callable[[Path], Any] | None = None,
    call_codex: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract)
    )
    return _execute(
        resolution=resolution,
        output_root=Path(output_root),
        queue_root=Path(queue_root),
        acknowledgement=authorization_acknowledgement_sha256,
        cell_id=cell_id,
        broker_factory=broker_factory,
        call_codex=call_codex,
    )


def execute_wave(
    *,
    output_root: Path,
    queue_root: Path,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
    allow_remote: bool,
    broker_factory: Callable[[Path], Any] | None = None,
    call_codex: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True:
        raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract)
    )
    lifecycle, runtime = _runtime(resolution)
    lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), BASE, SOURCE, CONTRACT, *_source_roots(resolution))
    lifecycle._prepared_inventory(runtime, Path(output_root), resolution["rows"])
    locks = lifecycle._locks(Path(output_root))
    try:
        def run(row: Mapping[str, Any]) -> dict[str, Any]:
            return lifecycle._execute_prepared(
                base=runtime,
                row=row,
                output_root=Path(output_root),
                queue_root=Path(queue_root),
                authorization_acknowledgement_sha256=authorization_acknowledgement_sha256,
                allow_remote=True,
                locks=locks,
                broker_factory=broker_factory,
                call_codex=call_codex,
            )

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            return list(pool.map(run, resolution["rows"]))
    finally:
        if locks.exists() and not any(locks.iterdir()):
            locks.rmdir()


def report(
    *,
    output_root: Path,
    authorization_acknowledgement_sha256: str,
    split_manifest: Path,
    hanna_csv: Path,
    successor_contract: Path,
) -> dict[str, Any]:
    validate_package()
    resolution = _resolution(
        split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract)
    )
    base = resolution["base"]
    source = _source(base)
    lifecycle, runtime = _runtime(resolution)
    entries = lifecycle._output_inventory(Path(output_root), resolution["rows"])
    v4 = lifecycle.sol_v4()
    route = evidence = None
    threads: set[str] = set()
    sessions: set[str] = set()
    cells: list[dict[str, Any]] = []
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {
        DIRECT: defaultdict(list),
        THRESHOLDS: defaultdict(list),
    }
    for row in resolution["rows"]:
        root = entries[row["cell_id"]]
        if "execution-receipt.json" not in {path.name for path in root.iterdir()}:
            raise ValueError("incomplete Sol terminal receipts cannot aggregate")
        admitted = lifecycle._admit_completed_cell(runtime, v4, row, root, authorization_acknowledgement_sha256)
        identity, settings, answer = admitted["identity"], admitted["settings"], admitted["answer"]
        if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or not isinstance(answer, Mapping):
            raise TypeError("invalid admitted Sol receipt")
        thread, session = identity.get("thread_id"), identity.get("session_id")
        if (
            not isinstance(thread, str)
            or not thread
            or not isinstance(session, str)
            or not session
            or thread in threads
            or session in sessions
        ):
            raise ValueError("duplicate or invalid Sol identity")
        threads.add(thread)
        sessions.add(session)
        cell_route, cell_evidence = admitted["route"], admitted["route_evidence"]
        if route is None:
            route, evidence = cell_route, cell_evidence
        elif cell_route != route or cell_evidence != evidence:
            raise ValueError("mixed Sol route or evidence")
        scores, coverage, raw_form = source._validate_answer(row["condition"], answer)
        if any(not math.isfinite(float(scores[name])) or type(coverage[name]) is not bool for name in DIMS):
            raise ValueError("Sol numeric score or coverage drifted")
        cell = {
            "cell_id": row["cell_id"],
            "source_cell_id": row["source_cell_id"],
            "condition": row["condition"],
            "item_id": row["item_id"],
            "prompt_group_id": row["prompt_group_id"],
            "partition": "train",
            "payload_sha256": row["payload_sha256"],
            "final_response_sha256": base.sha256(admitted["final"]),
            "receipt_sha256": base.sha256(admitted["receipt"]),
            "effective_settings_sha256": base.sha256(settings),
            "scores": scores,
            "coverage": coverage,
            "target": dict(row["target"]),
            **raw_form,
        }
        cell["per_item_mae"] = source._mean(
            [abs(float(scores[name]) - float(row["target"][name])) for name in DIMS]
        )
        cells.append(cell)
        grouped[row["condition"]][row["prompt_group_id"]].append(cell)
    if route is None or evidence is None or len(cells) != 96 or len(threads) != 96 or len(sessions) != 96:
        raise ValueError("incomplete Sol-96 report geometry")
    v4._frozen_route(route, evidence, runtime._load_v3(), require_unexpired=False)
    groups = sorted({row["prompt_group_id"] for row in resolution["rows"]})
    expected_items = {
        condition: {
            group: {
                row["item_id"]
                for row in resolution["rows"]
                if row["condition"] == condition and row["prompt_group_id"] == group
            }
            for group in groups
        }
        for condition in (DIRECT, THRESHOLDS)
    }
    if expected_items[DIRECT] != expected_items[THRESHOLDS] or any(
        not item_ids for item_ids in expected_items[DIRECT].values()
    ):
        raise ValueError("V15 schedule does not preserve matched per-group item identities")
    metrics: dict[str, Any] = {}
    rank_metrics: dict[str, Any] = {}
    occupancy: dict[str, Any] = {}
    coverage_counts: dict[str, Any] = {}
    for condition in (DIRECT, THRESHOLDS):
        by_group = grouped[condition]
        if set(by_group) != set(groups) or any(
            {cell["item_id"] for cell in by_group[group]} != expected_items[condition][group]
            or len(by_group[group]) != len(expected_items[condition][group])
            for group in groups
        ):
            raise ValueError("V15 Sol condition does not retain the scheduled per-group items")
        rows = [cell for group in groups for cell in by_group[group]]
        group_mae = {group: source._mean([cell["per_item_mae"] for cell in by_group[group]]) for group in groups}
        fixed = {
            group: source._mean(
                [
                    source._mean([abs(3.0 - float(cell["target"][name])) for name in DIMS])
                    for cell in by_group[group]
                ]
            )
            for group in groups
        }
        metrics[condition] = {
            "per_group_mean_item_mae": group_mae,
            "equal_group_mean_item_mae": source._mean(list(group_mae.values())),
            "fixed_three_equal_group_mae": source._mean(list(fixed.values())),
            "item_count": 48,
            "group_count": 24,
            "pair_accuracy": source._pair_accuracy(rows),
        }
        rank_metrics[condition] = source._rank_metrics(rows, by_group)
        occupancy[condition] = {
            dimension: dict(sorted(Counter(int(cell["scores"][dimension]) for cell in rows).items()))
            for dimension in DIMS
        }
        coverage_counts[condition] = {
            dimension: {
                "true": sum(cell["coverage"][dimension] for cell in rows),
                "false": sum(not cell["coverage"][dimension] for cell in rows),
            }
            for dimension in DIMS
        }
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": contract()["kind"],
        "status": "complete_matched_96_cells",
        "endpoint": "sol_later",
        "grok_schedule_sha256": resolution["bindings"]["grok_schedule_sha256"],
        "cells": cells,
        "metrics": metrics,
        "rank_metrics": rank_metrics,
        "score_occupancy": occupancy,
        "coverage_counts": coverage_counts,
        "unique_thread_ids": len(threads),
        "unique_session_ids": len(sessions),
        "native_endpoint_contact_cardinality": "unproven",
        "authority": contract()["authority"],
        "interpretation": "TRAIN_only_separate_sol_measurement; no_selection_promotion_confirmation_or_endpoint_pooling",
    }


if __name__ == "__main__":
    raise SystemExit("Use the callable API; Sol execution requires an explicit reviewed invocation.")
