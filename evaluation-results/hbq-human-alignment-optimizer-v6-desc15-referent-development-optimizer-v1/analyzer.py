"""Replay the 52-cell Grok development wave and freeze Sol-veto qualifiers."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc15-referent-development-optimizer-v1"
EXECUTOR_ID = "hbq-human-alignment-optimizer-v6-desc15-referent-grok-exec-v1"
EXECUTOR_ROOT = HERE.parent / EXECUTOR_ID
EXECUTOR_COMMIT = "eebf7409379952123f877d2e47031a95856498cc"
BASE_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v1"
BASE = HERE.parent / BASE_ID / "verify.py"
BASE_SHA256 = "cf6d0a6bb2526191b5897275ae903ca8569f61d733cb0bfe136a41856447b587"
EXECUTOR_HASHES = {
    "executor.py": "0220f63fe363502d2846b3300fb26fde2c09dd78ad621ea07bc99793bf6bd83f",
    "study-contract.json": "5c5596e8d648a7baf8280df33eb18a1e15352b1866b3c1cf36c488625cb94bb9",
    "README.md": "df4f072e5482cf11cea99e2a353b7940edf88d953e758e4af68f5dd2f3148467",
}
FREEZE_SCHEDULE_SHA256 = "d2935d770079a4bacee654ef36c165fc27bb6f700d48647cf1f867dee5c276b4"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
CHILDREN = (
    "broader-nextwave-19-construct_framing-referent-boundary",
    "broader-nextwave-20-missing_evidence_not_no-referent-evidence",
    "broader-nextwave-21-scope_materiality-referent-materiality",
)
CANDIDATES = (PARENT, *CHILDREN)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
WORST_GROUP_WEIGHTS = (0.0, 0.15, 0.30)
STABILITY_WEIGHTS = (0.0, 0.10)
SEED = 202609011
PUBLIC_FILES = {"README.md", "analyzer.py", "study-contract.json"}
AUTHORITY = {
    "confirmation": "unopened",
    "endpoint_pooling": "forbidden",
    "generalization": "none",
    "promotion": "none",
    "runtime": "none",
    "selection": "grok_development_qualification_only_pending_sol_veto",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _ancestry(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int, int | None], ...]:
    target = Path(os.path.abspath(path))
    values = []
    for index, current in enumerate((target, *target.parents)):
        info = os.lstat(current)
        expected = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed analyzer input")
        if stat.S_ISDIR(info.st_mode) != expected:
            raise ValueError("analyzer input type drifted")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_mtime_ns, None if expected else info.st_size))
    return tuple(values)


@dataclass(frozen=True)
class Admitted:
    path: Path
    directory: bool
    ancestry: tuple[tuple[str, int, int, int, int, int | None], ...]
    raw: bytes | None


def _admit(path: Path, *, directory: bool) -> Admitted:
    target = Path(os.path.abspath(path))
    before = _ancestry(target, directory=directory)
    if directory:
        return Admitted(target, True, before, None)
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    final = _ancestry(target, directory=False)
    identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != final or before[0][1:4] + (before[0][-1],) != identity or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("analyzer input changed during admission")
    return Admitted(target, False, before, raw)


def _verify(value: Admitted) -> None:
    if _ancestry(value.path, directory=value.directory) != value.ancestry:
        raise ValueError("admitted input changed between replay and optimization")
    if not value.directory and _admit(value.path, directory=False).raw != value.raw:
        raise ValueError("admitted input bytes changed between replay and optimization")


def _tree_commitment(root: Path) -> str:
    root = Path(os.path.abspath(root))
    _ancestry(root, directory=True)
    rows: list[dict[str, Any]] = []

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda path: path.name):
            info = os.lstat(child)
            relative = child.relative_to(root).as_posix()
            if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
                raise ValueError("nested analyzer evidence contains a reparse point")
            if stat.S_ISDIR(info.st_mode):
                rows.append({"kind": "directory", "path": relative})
                visit(child)
            elif stat.S_ISREG(info.st_mode):
                admitted = _admit(child, directory=False)
                rows.append({"kind": "file", "path": relative, "sha256": sha256(admitted.raw or b"")})
            else:
                raise ValueError("nested analyzer evidence has an unsupported artifact type")

    visit(root)
    return sha256(rows)


def _strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _load_exact(path: Path, name: str, expected_sha256: str) -> ModuleType:
    admitted = _admit(path, directory=False)
    if sha256(admitted.raw or b"") != expected_sha256:
        raise ValueError("pinned analyzer dependency drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    try:
        exec(compile(admitted.raw or b"", str(path), "exec"), module.__dict__)  # noqa: S102 -- exact admitted immutable bytes
    finally:
        sys.modules.pop(name, None)
    _verify(admitted)
    return module


def load_base() -> ModuleType:
    return _load_exact(BASE, "_desc15_optimizer_result_base", BASE_SHA256)


def load_executor() -> ModuleType:
    admitted = {name: _admit(EXECUTOR_ROOT / name, directory=False) for name in EXECUTOR_HASHES}
    for name, value in admitted.items():
        relative = (EXECUTOR_ROOT / name).relative_to(REPO).as_posix()
        blob = subprocess.run(["git", "-C", str(REPO), "show", f"{EXECUTOR_COMMIT}:{relative}"], capture_output=True, check=False)
        if blob.returncode or sha256(value.raw or b"") != EXECUTOR_HASHES[name] or blob.stdout != value.raw:
            raise ValueError("pinned 52-cell executor drifted or is not committed")
    module = _load_exact(EXECUTOR_ROOT / "executor.py", "_desc15_optimizer_executor", EXECUTOR_HASHES["executor.py"])
    for value in admitted.values():
        _verify(value)
    if module.STUDY_ID != EXECUTOR_ID:
        raise ValueError("52-cell executor identity drifted")
    return module


def _admit_inputs(**paths: Path) -> dict[str, Admitted]:
    directories = {"freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "output_root"}
    return {name: _admit(Path(path), directory=name in directories) for name, path in paths.items()}


def _development_targets(
    base: ModuleType,
    schedule: Mapping[str, Any],
    *,
    development_freeze_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
) -> dict[str, dict[str, float]]:
    paths = {
        "development_freeze_root": (Path(development_freeze_root), True),
        "normalized_root": (Path(normalized_root), True),
        "materialization_root": (Path(materialization_root), True),
        "frozen_successor_path": (Path(frozen_successor_path), False),
        "hanna_csv_path": (Path(hanna_csv_path), False),
    }
    before = {name: base._ancestry(path, directory=directory) for name, (path, directory) in paths.items()}
    freeze = base._load_freeze(REPO)
    persisted = freeze.validate_frozen_root(paths["development_freeze_root"][0])
    rebuilt = freeze.build(
        normalized_root=paths["normalized_root"][0],
        materialization_root=paths["materialization_root"][0],
        frozen_successor_path=paths["frozen_successor_path"][0],
        hanna_csv_path=paths["hanna_csv_path"][0],
    )
    if base.canonical(persisted) != base.canonical(rebuilt):
        raise ValueError("development evidence does not independently reconstruct")
    study, _harness, _frozen, split, _parents = freeze._v3()._material(
        frozen_successor_path=paths["frozen_successor_path"][0], hanna_csv_path=paths["hanna_csv_path"][0]
    )
    cells = schedule.get("cells")
    if not isinstance(cells, list):
        raise TypeError("52-cell schedule lacks cells")
    required_pairs = {(row.get("item_id"), row.get("prompt_group_id")) for row in cells if isinstance(row, Mapping)}
    development_pairs = {
        (row.get("item_id"), row.get("prompt_group_id"))
        for row in split.get("items", [])
        if isinstance(row, Mapping) and row.get("partition") == "development"
    }
    if len(required_pairs) != 13 or not required_pairs <= development_pairs:
        raise ValueError("52-cell items are not exactly admitted development items")
    targets = freeze._v3().v2_module()._human_targets(
        study=study,
        frozen_successor_path=paths["frozen_successor_path"][0],
        hanna_csv_path=paths["hanna_csv_path"][0],
    )
    required_items = {str(item) for item, _group in required_pairs}
    if not isinstance(targets, Mapping) or not required_items <= set(targets):
        raise ValueError("independent HANNA target reconstruction is incomplete")
    selected: dict[str, dict[str, float]] = {}
    for item in required_items:
        row = targets[item]
        if not isinstance(row, Mapping) or set(row) != set(DIMENSIONS):
            raise ValueError("independent HANNA target shape drifted")
        values = dict(row)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values.values()):
            raise ValueError("independent HANNA target is invalid")
        selected[item] = {name: float(values[name]) for name in DIMENSIONS}
    after = {name: base._ancestry(path, directory=directory) for name, (path, directory) in paths.items()}
    if before != after:
        raise ValueError("external HANNA input changed during target reconstruction")
    return selected


def _native_scores(raw: bytes, extractor: Any) -> tuple[dict[str, float], dict[str, bool]]:
    try:
        scores, coverage, _reported = extractor(raw, provider="xai", model="grok-4.6")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("native Grok response extraction drifted") from error
    if not isinstance(scores, Mapping) or set(scores) != set(DIMENSIONS) or not isinstance(coverage, Mapping) or set(coverage) != set(DIMENSIONS):
        raise ValueError("native Grok response shape drifted")
    score_values = {name: scores[name] for name in DIMENSIONS}
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in score_values.values()):
        raise ValueError("native Grok scores are invalid")
    if any(type(coverage[name]) is not bool for name in DIMENSIONS):
        raise ValueError("native Grok coverage is invalid")
    return ({name: float(score_values[name]) for name in DIMENSIONS}, {name: coverage[name] for name in DIMENSIONS})


def _project(
    schedule: Mapping[str, Any], collector: Mapping[str, Any], targets: Mapping[str, Mapping[str, float]], extractor: Any
) -> dict[str, Any]:
    geometry = {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0, "confirmation_cells": 0}
    cells = schedule.get("cells")
    if (
        schedule.get("study_id") != EXECUTOR_ID
        or schedule.get("kind") != "frozen_desc15_referent_grok_development_execution_schedule"
        or schedule.get("geometry") != geometry
        or schedule.get("frozen_schedule_sha256") != FREEZE_SCHEDULE_SHA256
        or not isinstance(cells, list)
        or len(cells) != 52
    ):
        raise ValueError("52-cell execution schedule geometry drifted")
    index = {row.get("cell_id"): row for row in cells if isinstance(row, Mapping)}
    candidates = {row.get("candidate_id") for row in cells if isinstance(row, Mapping)}
    item_pairs = {(row.get("item_id"), row.get("prompt_group_id")) for row in cells if isinstance(row, Mapping)}
    candidate_item_pairs = {(row.get("candidate_id"), row.get("item_id")) for row in cells if isinstance(row, Mapping)}
    if len(index) != 52 or candidates != set(CANDIDATES) or len(item_pairs) != 13 or len({group for _item, group in item_pairs}) != 7 or len(candidate_item_pairs) != 52:
        raise ValueError("52-cell candidate/item/group pairing drifted")
    expected_collector = {
        "format_version", "study_id", "kind", "schedule_sha256", "authorization_acknowledgement_sha256", "route", "route_evidence", "cells",
        "native_endpoint_contact_cardinality", "provider_calls_made", "process_launches",
    }
    supplied = collector.get("cells")
    if (
        set(collector) != expected_collector
        or collector.get("study_id") != EXECUTOR_ID
        or collector.get("kind") != "complete_52_desc15_referent_grok_receipts_cardinality_unproven"
        or collector.get("schedule_sha256") != schedule.get("schedule_sha256")
        or collector.get("native_endpoint_contact_cardinality") != "unproven"
        or collector.get("provider_calls_made") is not None
        or collector.get("process_launches") != 52
        or not isinstance(supplied, list)
        or len(supplied) != 52
    ):
        raise ValueError("52-cell collector or caller aggregate surface drifted")
    required_cell = {
        "cell_id", "payload_base64", "payload_sha256", "native_request_base64", "native_request_sha256", "native_response_base64",
        "native_response_sha256", "identity", "effective_settings", "effective_settings_sha256",
    }
    item_mae: dict[str, dict[str, list[tuple[str, float]]]] = {candidate: defaultdict(list) for candidate in CANDIDATES}
    coverage_false: dict[str, list[dict[str, str]]] = {candidate: [] for candidate in CANDIDATES}
    seen: set[str] = set()
    for entry in supplied:
        if not isinstance(entry, Mapping) or set(entry) != required_cell:
            raise ValueError("collector cell fields drifted")
        cell_id = entry.get("cell_id")
        row = index.get(cell_id)
        if not isinstance(cell_id, str) or cell_id in seen or not isinstance(row, Mapping):
            raise ValueError("duplicate or unknown collector cell")
        try:
            response = base64.b64decode(entry["native_response_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("collector native response bytes are invalid") from error
        if (
            entry.get("payload_base64") != row.get("payload_base64")
            or entry.get("payload_sha256") != row.get("payload_sha256")
            or entry.get("native_response_sha256") != sha256(response)
        ):
            raise ValueError("collector response or payload binding drifted")
        candidate = str(row["candidate_id"])
        item = str(row["item_id"])
        group = str(row["prompt_group_id"])
        target = targets.get(item)
        if not isinstance(target, Mapping) or set(target) != set(DIMENSIONS):
            raise ValueError("independent HANNA target binding drifted")
        scores, coverage = _native_scores(response, extractor)
        item_mae[candidate][group].append((item, sum(abs(scores[name] - float(target[name])) for name in DIMENSIONS) / len(DIMENSIONS)))
        coverage_false[candidate].extend({"dimension": name, "item_id": item, "prompt_group_id": group} for name in DIMENSIONS if not coverage[name])
        seen.add(cell_id)
    if seen != set(index):
        raise ValueError("partial 52-cell collector cannot be analyzed")
    expected_by_group: dict[str, set[str]] = defaultdict(set)
    for item, group in item_pairs:
        expected_by_group[str(group)].add(str(item))
    metrics = []
    for candidate in CANDIDATES:
        groups = item_mae[candidate]
        if set(groups) != set(expected_by_group):
            raise ValueError("partial candidate group cannot be imputed")
        group_mae: dict[str, float] = {}
        for group, expected_items in expected_by_group.items():
            rows = groups[group]
            if {item for item, _mae in rows} != expected_items or len(rows) != len(expected_items):
                raise ValueError("partial or duplicated group item cannot be imputed")
            group_mae[group] = sum(value for _item, value in rows) / len(rows)
        ordered = dict(sorted(group_mae.items()))
        metrics.append({
            "candidate_id": candidate,
            "cells": 13,
            "equal_group_mae": sum(ordered.values()) / 7,
            "group_mae": ordered,
            "coverage_false": sorted(coverage_false[candidate], key=lambda row: (row["item_id"], row["dimension"])),
        })
    metrics.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "desc15_referent_grok_development_equal_group_projection",
        "authority": AUTHORITY,
        "claim": "GROK_DEVELOPMENT_ONLY; thirteen item MAEs are averaged within seven frozen groups, then the groups are weighted equally; no Sol, confirmation, promotion, runtime, pooled-endpoint, or general claim follows",
        "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 52, "provider_calls_made": None},
        "metrics": metrics,
    }


def objective(metric: Mapping[str, Any], worst_weight: float, stability_weight: float) -> float:
    values = tuple(float(value) for value in metric["group_mae"].values())
    mean = float(metric["equal_group_mae"])
    return mean + worst_weight * (max(values) - mean) + stability_weight * sum(abs(value - mean) for value in values) / len(values)


def _validated_metrics(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    if projection.get("study_id") != STUDY_ID or projection.get("kind") != "desc15_referent_grok_development_equal_group_projection":
        raise ValueError("foreign result projection")
    if projection.get("authority") != AUTHORITY:
        raise ValueError("result projection authority drifted")
    source = projection.get("source_execution")
    if (
        not isinstance(source, Mapping)
        or set(source) != {"collector_sha256", "executor_sha256", "frozen_schedule_sha256", "schedule_sha256"}
        or source.get("executor_sha256") != EXECUTOR_HASHES["executor.py"]
        or source.get("frozen_schedule_sha256") != FREEZE_SCHEDULE_SHA256
    ):
        raise ValueError("result projection lacks exact execution commitments")
    rows = projection.get("metrics")
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("result projection candidate geometry drifted")
    output = []
    seen: set[str] = set()
    group_ids: set[str] | None = None
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae", "coverage_false"}:
            raise ValueError("result projection metric shape drifted")
        candidate = row.get("candidate_id")
        groups = row.get("group_mae")
        coverage = row.get("coverage_false")
        if candidate not in CANDIDATES or candidate in seen or row.get("cells") != 13 or not isinstance(groups, Mapping) or len(groups) != 7 or not isinstance(coverage, list):
            raise ValueError("result projection candidate or group identity drifted")
        current_groups = set(groups)
        if group_ids is None:
            group_ids = current_groups
        if current_groups != group_ids:
            raise ValueError("mixed development group geometry")
        values = list(groups.values())
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
            raise ValueError("result projection group MAE is invalid")
        mean = row.get("equal_group_mae")
        if isinstance(mean, bool) or not isinstance(mean, (int, float)) or not math.isclose(float(mean), sum(float(value) for value in values) / 7, rel_tol=0, abs_tol=1e-15):
            raise ValueError("result projection equal-group MAE does not recompute")
        for item in coverage:
            if not isinstance(item, Mapping) or set(item) != {"dimension", "item_id", "prompt_group_id"} or item.get("dimension") not in DIMENSIONS:
                raise ValueError("coverage-false provenance drifted")
        output.append({
            "candidate_id": str(candidate),
            "cells": 13,
            "equal_group_mae": float(mean),
            "group_mae": dict(sorted((str(key), float(value)) for key, value in groups.items())),
            "coverage_false": [dict(item) for item in coverage],
        })
        seen.add(str(candidate))
    if seen != set(CANDIDATES) or group_ids is None:
        raise ValueError("incomplete candidate projection")
    return sorted(output, key=lambda row: row["candidate_id"])


def run_optuna(metrics: list[Mapping[str, Any]]) -> dict[str, Any]:
    import optuna

    ids = [str(row["candidate_id"]) for row in metrics]
    by_id = {str(row["candidate_id"]): row for row in metrics}
    grid = {"candidate_id": ids, "worst_group_weight": list(WORST_GROUP_WEIGHTS), "stability_weight": list(STABILITY_WEIGHTS)}
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.GridSampler(grid, seed=SEED))

    def evaluate(trial: Any) -> float:
        candidate = trial.suggest_categorical("candidate_id", ids)
        worst = float(trial.suggest_categorical("worst_group_weight", list(WORST_GROUP_WEIGHTS)))
        stability = float(trial.suggest_categorical("stability_weight", list(STABILITY_WEIGHTS)))
        return objective(by_id[candidate], worst, stability)

    expected = len(ids) * len(WORST_GROUP_WEIGHTS) * len(STABILITY_WEIGHTS)
    study.optimize(evaluate, n_trials=expected)
    if len(study.trials) != expected or any(trial.state.name != "COMPLETE" for trial in study.trials):
        raise ValueError("Optuna GridSampler did not complete the frozen grid")
    records = sorted(
        (
            {
                "candidate_id": str(trial.params["candidate_id"]),
                "objective": float(trial.value),
                "stability_weight": float(trial.params["stability_weight"]),
                "worst_group_weight": float(trial.params["worst_group_weight"]),
            }
            for trial in study.trials
        ),
        key=lambda row: (row["worst_group_weight"], row["stability_weight"], row["candidate_id"]),
    )
    observed = {(row["candidate_id"], row["worst_group_weight"], row["stability_weight"]) for row in records}
    required = {(candidate, worst, stability) for candidate in ids for worst in WORST_GROUP_WEIGHTS for stability in STABILITY_WEIGHTS}
    if observed != required:
        raise ValueError("Optuna GridSampler trial geometry drifted")
    for row in records:
        recomputed = objective(by_id[row["candidate_id"]], row["worst_group_weight"], row["stability_weight"])
        if not math.isclose(row["objective"], recomputed, rel_tol=0, abs_tol=1e-15):
            raise ValueError("Optuna objective record does not independently recompute")
    settings = []
    for worst in WORST_GROUP_WEIGHTS:
        for stability in STABILITY_WEIGHTS:
            values = {
                row["candidate_id"]: row["objective"]
                for row in records
                if row["worst_group_weight"] == worst and row["stability_weight"] == stability
            }
            settings.append({"worst_group_weight": worst, "stability_weight": stability, "objective_by_candidate": dict(sorted(values.items()))})
    return {
        "library": f"optuna@{optuna.__version__}",
        "sampler": "GridSampler",
        "seed": SEED,
        "completed_trials": expected,
        "settings": settings,
        "trial_records_sha256": sha256(records),
    }


def qualify(metrics: list[Mapping[str, Any]], optimizer: Mapping[str, Any]) -> dict[str, Any]:
    by_id = {str(row["candidate_id"]): row for row in metrics}
    parent = by_id.get(PARENT)
    settings = optimizer.get("settings")
    if parent is None or not isinstance(settings, list) or len(settings) != 6:
        raise ValueError("qualification lacks parent or six robustness settings")
    expected_settings = {(worst, stability) for worst in WORST_GROUP_WEIGHTS for stability in STABILITY_WEIGHTS}
    validated_settings: dict[tuple[float, float], dict[str, float]] = {}
    for setting in settings:
        if not isinstance(setting, Mapping) or set(setting) != {"worst_group_weight", "stability_weight", "objective_by_candidate"}:
            raise ValueError("qualification robustness setting shape drifted")
        worst, stability, supplied = setting["worst_group_weight"], setting["stability_weight"], setting["objective_by_candidate"]
        if isinstance(worst, bool) or not isinstance(worst, (int, float)) or isinstance(stability, bool) or not isinstance(stability, (int, float)) or not isinstance(supplied, Mapping):
            raise TypeError("qualification robustness setting is invalid")
        key = (float(worst), float(stability))
        if key not in expected_settings or key in validated_settings or set(supplied) != set(CANDIDATES):
            raise ValueError("qualification robustness grid drifted")
        recomputed = {candidate: objective(by_id[candidate], *key) for candidate in CANDIDATES}
        if any(
            isinstance(supplied[candidate], bool)
            or not isinstance(supplied[candidate], (int, float))
            or not math.isfinite(supplied[candidate])
            or not math.isclose(float(supplied[candidate]), recomputed[candidate], rel_tol=0, abs_tol=1e-15)
            for candidate in CANDIDATES
        ):
            raise ValueError("qualification objective does not independently recompute")
        validated_settings[key] = recomputed
    if set(validated_settings) != expected_settings:
        raise ValueError("qualification robustness grid is incomplete")
    assessments = []
    qualifiers = []
    for candidate in CHILDREN:
        row = by_id[candidate]
        raw_strictly_better = row["equal_group_mae"] < parent["equal_group_mae"]
        no_worse_all_settings = all(values[candidate] <= values[PARENT] for values in validated_settings.values())
        qualifies = raw_strictly_better and no_worse_all_settings
        assessments.append({
            "candidate_id": candidate,
            "no_worse_than_parent_all_six_robustness_settings": no_worse_all_settings,
            "qualifies_for_sol_veto": qualifies,
            "raw_equal_group_mae": row["equal_group_mae"],
            "raw_equal_group_mae_strictly_below_parent": raw_strictly_better,
        })
        if qualifies:
            qualifiers.append(candidate)
    qualifiers.sort()
    return {
        "assessments": assessments,
        "frozen_before_sol": True,
        "parent_candidate_id": PARENT,
        "parent_equal_group_mae": parent["equal_group_mae"],
        "qualifiers": qualifiers,
        "rule": "raw equal-group MAE strictly below parent AND objective no worse than parent in every one of six frozen robustness settings",
        "sol_veto": {
            "calls_made": 0,
            "eligible_candidates": qualifiers,
            "role": "veto_only_no_sol_favored_substitution",
            "status": "not_required_no_qualifiers" if not qualifiers else "pending_for_frozen_qualifiers",
        },
        "development_decision": "retain_parent_zero_sol_calls" if not qualifiers else "freeze_qualifiers_pending_sol_veto",
    }


def build_dspy_evidence(metrics: list[Mapping[str, Any]], qualification: Mapping[str, Any]) -> dict[str, Any]:
    import dspy

    class ReplayedDesc15Evidence(dspy.Signature):
        candidate_id: str = dspy.InputField()
        group_mae_json: str = dspy.InputField()
        equal_group_mae: float = dspy.OutputField()

    examples = [
        dspy.Example(
            candidate_id=row["candidate_id"],
            group_mae_json=canonical(row["group_mae"]).decode("utf-8"),
            equal_group_mae=row["equal_group_mae"],
        ).with_inputs("candidate_id", "group_mae_json")
        for row in metrics
    ]
    return {
        "evidence_chain_sha256": sha256([example.toDict() for example in examples]),
        "evidence_examples": len(examples),
        "library": f"dspy@{dspy.__version__}",
        "lm_calls": 0,
        "predict_calls": 0,
        "proposal_generated": False,
        "qualifiers_frozen_before_sol": list(qualification["qualifiers"]),
        "signature": ReplayedDesc15Evidence.__name__,
    }


def replay_projection(
    *,
    freeze_root: Path,
    development_freeze_root: Path,
    normalized_root: Path,
    materialization_root: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
    output_root: Path,
    collector_path: Path,
) -> dict[str, Any]:
    sources = _admit_inputs(
        freeze_root=freeze_root,
        development_freeze_root=development_freeze_root,
        normalized_root=normalized_root,
        materialization_root=materialization_root,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
        output_root=output_root,
        collector_path=collector_path,
    )
    tree_before = {
        name: _tree_commitment(source.path)
        for name, source in sources.items()
        if source.directory
    }
    executor = load_executor()
    expected_schedule = executor.frozen_schedule(Path(freeze_root))
    schedule_admitted = _admit(Path(output_root) / "schedule.json", directory=False)
    schedule = _strict(schedule_admitted.raw or b"", "persisted 52-cell schedule")
    if canonical(expected_schedule) != schedule_admitted.raw:
        raise ValueError("persisted 52-cell schedule differs from immutable freeze")
    collector_admitted = sources["collector_path"]
    collector = _strict(collector_admitted.raw or b"", "52-cell collector")
    replayed = executor.replay_collector(output_root=Path(output_root), freeze_root=Path(freeze_root), collector_path=Path(collector_path))
    if (
        replayed.get("cells") != 52
        or replayed.get("equal_group_projection_ready") is not True
        or replayed.get("collector_sha256") != sha256(collector_admitted.raw or b"")
        or replayed.get("provider_calls_made") is not None
        or replayed.get("native_endpoint_contact_cardinality") != "unproven"
    ):
        raise ValueError("execution receipt replay is incomplete")
    base = load_base()
    targets = _development_targets(
        base,
        schedule,
        development_freeze_root=Path(development_freeze_root),
        normalized_root=Path(normalized_root),
        materialization_root=Path(materialization_root),
        frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path),
    )
    extractor = base._load_freeze(REPO)._v3().v2_module()._extract_native
    projection = _project(schedule, collector, targets, extractor)
    for source in sources.values():
        _verify(source)
    _verify(schedule_admitted)
    tree_after = {
        name: _tree_commitment(source.path)
        for name, source in sources.items()
        if source.directory
    }
    if tree_before != tree_after:
        raise ValueError("nested replay evidence changed during analysis")
    projection["source_execution"] = {
        "collector_sha256": sha256(collector_admitted.raw or b""),
        "executor_sha256": EXECUTOR_HASHES["executor.py"],
        "frozen_schedule_sha256": FREEZE_SCHEDULE_SHA256,
        "schedule_sha256": schedule["schedule_sha256"],
    }
    projection["projection_sha256"] = sha256(projection)
    return projection


def analyze(**paths: Path) -> dict[str, Any]:
    projection = replay_projection(**paths)
    metrics = _validated_metrics(projection)
    optimizer = run_optuna(metrics)
    qualification = qualify(metrics, optimizer)
    dspy_evidence = build_dspy_evidence(metrics, qualification)
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "desc15_referent_grok_development_optimizer_and_sol_veto_freeze",
        "source": {
            "collector_sha256": projection["source_execution"]["collector_sha256"],
            "executor_sha256": EXECUTOR_HASHES["executor.py"],
            "projection_sha256": projection["projection_sha256"],
        },
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_trials": 24, "sol_cells_executed": 0, "confirmation_cells": 0},
        "metrics": metrics,
        "optimizer": optimizer,
        "qualification": qualification,
        "dspy_evidence": dspy_evidence,
        "authority": {
            "confirmation": {"cells": 0, "status": "unopened"},
            "promotion": "none",
            "runtime": "none",
            "selection": qualification["development_decision"],
            "sol": "veto_only_pending" if qualification["qualifiers"] else "not_required_zero_calls",
        },
        "claim": "This development-only replay freezes only candidates satisfying the parent-relative raw-MAE and six-setting robustness rule. Sol may veto a frozen qualifier but cannot substitute a Sol-favored candidate. No confirmation, promotion, runtime, pooled-endpoint, or general claim follows.",
    }
    result["result_sha256"] = sha256(result)
    return result


def _contract() -> dict[str, Any]:
    return {
        "authority": {"confirmation": "unopened", "promotion": "none", "runtime": "none", "selection": "grok_development_qualification_only", "sol": "veto_only"},
        "format_version": 1,
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_grid_settings": 6},
        "kind": "provider_free_desc15_result_replay_and_development_optimizer",
        "pinned_executor": {"commit": EXECUTOR_COMMIT, "files": dict(sorted(EXECUTOR_HASHES.items())), "study_id": EXECUTOR_ID},
        "pinned_result_base": {"study_id": BASE_ID, "verify_sha256": BASE_SHA256},
        "qualification_rule": {
            "raw_equal_group_mae": "strictly_below_desc13_parent",
            "robustness": "no_worse_than_desc13_parent_in_all_six_settings",
            "sol": "freeze_qualifiers_before_sol_then_veto_only",
            "zero_qualifiers": "retain_desc13_parent_and_make_zero_sol_calls",
        },
        "runtime_dependencies": {"dspy": "development_only_zero_lm_calls", "optuna": "development_only_grid_sampler", "production": "none"},
        "study_id": STUDY_ID,
    }


def validate_package() -> dict[str, Any]:
    root = _admit(HERE, directory=True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("development optimizer package inventory drifted")
    contract = _strict(_admit(HERE / "study-contract.json", directory=False).raw or b"", "study contract")
    if contract != _contract():
        raise ValueError("development optimizer contract drifted")
    _verify(root)
    return contract


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("development optimizer result output must be fresh")
    parent_before = _ancestry(target.parent, directory=True)
    raw = canonical(dict(result))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(target, flags, 0o600)
    except OSError as error:
        raise ValueError("development optimizer result output must be a fresh plain file") from error
    with os.fdopen(descriptor, "wb") as handle:
        opened = os.fstat(handle.fileno())
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
        after = os.fstat(handle.fileno())
    persisted = _admit(target, directory=False)
    identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    final_identity = (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size)
    parent_after = _ancestry(target.parent, directory=True)
    same_parent = parent_before[0][:4] == parent_after[0][:4] and parent_before[1:] == parent_after[1:]
    persisted_identity = persisted.ancestry[0][1:4] + (persisted.ancestry[0][-1],)
    if not same_parent or identity[:3] != final_identity[:3] or final_identity != persisted_identity or final_identity[-1] != len(raw) or persisted.raw != raw:
        raise ValueError("development optimizer result changed or was redirected during write")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor-path", "hanna-csv-path", "output-root", "collector-path"
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv)
    validate_package()
    names = ("freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "output_root", "collector_path")
    result = analyze(**{name: getattr(args, name) for name in names})
    if args.result_output is not None:
        write_result(args.result_output, result)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
