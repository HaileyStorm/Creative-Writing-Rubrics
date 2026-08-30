"""Token-bound shrinkage decisions over projected per-group MAE."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, pstdev
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_PATH = HERE / "study.py"
_STUDY: Any | None = None
_FROZEN_TOKEN = object()
_SOL_TOKEN = object()


def _study() -> Any:
    global _STUDY
    if _STUDY is not None: return _STUDY
    spec = importlib.util.spec_from_file_location("_hanna_shrinkage_study", STUDY_PATH)
    if spec is None or spec.loader is None: raise ValueError("HANNA shrinkage cannot load study")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module); _STUDY = module
    return module


def objective(deltas: Sequence[float], edit_mass: float) -> float:
    values = [float(value) for value in deltas]
    if not values or any(not math.isfinite(value) for value in values) or not math.isfinite(float(edit_mass)) or not 0.0 <= float(edit_mass) <= 1.0:
        raise ValueError("HANNA shrinkage objective inputs are invalid")
    return 0.5 * fmean(values) + 0.25 * pstdev(values) + 0.02 * float(edit_mass)


def _matrix(schedule: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], *, route: str, expected: int) -> dict[str, dict[str, float]]:
    cells = [row for row in schedule["cells"] if row["route_name"] == route]
    if len(cells) != expected or not isinstance(rows, Sequence) or len(rows) != expected: raise ValueError("HANNA shrinkage metric geometry drifted")
    index = {row["cell_id"]: row for row in cells}; result: dict[str, dict[str, float]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"cell_id", "candidate_id", "prompt_group_id", "mean_absolute_error"}: raise ValueError("HANNA shrinkage metric shape drifted")
        cell, value = index.get(row["cell_id"]), row["mean_absolute_error"]
        if cell is None or row["candidate_id"] != cell["candidate_id"] or row["prompt_group_id"] != cell["prompt_group_id"] or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or not 0 <= float(value) <= 4:
            raise ValueError("HANNA shrinkage metric binding/value drifted")
        if row["prompt_group_id"] in result.setdefault(row["candidate_id"], {}): raise ValueError("HANNA shrinkage duplicate group metric")
        result[row["candidate_id"]][row["prompt_group_id"]] = float(value)
    if set(index) != {row["cell_id"] for row in rows} or any(len(values) != expected // len(result) for values in result.values()): raise ValueError("HANNA shrinkage metrics are partial or duplicated")
    return result


def _decision(validated_schedule: Any, projected_group_metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    study = _study(); schedule, candidates = study._validated_schedule(validated_schedule)
    matrix = _matrix(schedule, projected_group_metrics, route="grok_primary", expected=33)
    groups = [row["prompt_group_id"] for row in schedule["groups"]]; baseline = matrix[study.BASELINE_ID]
    edit_mass = {row["candidate_id"]: 0.0 if row["candidate_id"] == study.BASELINE_ID else study._edit_mass(candidates[0], row) for row in candidates}
    scores: dict[str, dict[str, Any]] = {study.BASELINE_ID: {"deltas": [0.0] * 3, "j": 0.0, "edit_mass": 0.0}}
    for candidate_id in sorted(set(matrix) - {study.BASELINE_ID}):
        deltas = [matrix[candidate_id][group] - baseline[group] for group in groups]
        scores[candidate_id] = {"deltas": deltas, "j": objective(deltas, edit_mass[candidate_id]), "edit_mass": edit_mass[candidate_id]}
    overall = min(scores, key=lambda candidate: (scores[candidate]["j"], candidate)); fold_winners = []
    for held_out in range(3):
        def fold_score(candidate: str, held_out_index: int = held_out) -> float:
            if candidate == study.BASELINE_ID: return 0.0
            return objective([value for index, value in enumerate(scores[candidate]["deltas"]) if index != held_out_index], scores[candidate]["edit_mass"])
        winner = min(scores, key=lambda candidate: (fold_score(candidate), candidate))
        fold_winners.append({"held_out_prompt_group_id": groups[held_out], "winner_candidate_id": winner, "j": fold_score(winner)})
    candidate = scores[overall]; fold_wins = sum(row["winner_candidate_id"] == overall for row in fold_winners)
    improved = sum(value < 0 for value in candidate["deltas"]); worst = max(candidate["deltas"])
    advances = overall != study.BASELINE_ID and candidate["j"] < 0 and fold_wins >= 2 and improved >= 2 and worst <= 0.10 + 1e-12
    result = {"format_version": 2, "study_id": study.STUDY_ID, "kind": "three_group_shrinkage_grok_decision", "grok_schedule_sha256": schedule["schedule_sha256"], "selected_candidate_id": overall if advances else study.BASELINE_ID, "provisional_candidate_id": overall, "action": "advance_to_sol" if advances else "baseline_stop", "scores": [{"candidate_id": candidate_id, **scores[candidate_id]} for candidate_id in sorted(scores)], "leave_one_group_out": fold_winners, "gate": {"j_strictly_negative": candidate["j"] < 0, "same_candidate_fold_wins": fold_wins, "raw_groups_improved": improved, "maximum_group_worsening": worst, "maximum_allowed_group_worsening": 0.10, "passed": advances}, "optuna_role": "development_only_grid_reproduction_no_selection_authority", "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "claim": "NO-GO until independently replayed native evidence"}
    result["decision_sha256"] = study.sha256(result)
    return result


@dataclass(frozen=True)
class FrozenGrokDecision:
    decision: Mapping[str, Any]
    _decision_bytes: bytes
    _metrics_bytes: bytes
    _schedule: Any
    _token: object


def select_grok(*, validated_schedule: Any, projected_group_metrics: Sequence[Mapping[str, Any]]) -> FrozenGrokDecision:
    study = _study(); decision = _decision(validated_schedule, projected_group_metrics)
    decision_raw = study.canonical(decision); metrics_raw = study.canonical(list(projected_group_metrics))
    return FrozenGrokDecision(json.loads(decision_raw), decision_raw, metrics_raw, validated_schedule, _FROZEN_TOKEN)


def _validated_frozen(value: Any) -> tuple[Any, dict[str, Any], list[Mapping[str, Any]]]:
    study = _study()
    if not isinstance(value, FrozenGrokDecision) or value._token is not _FROZEN_TOKEN or study.canonical(dict(value.decision)) != value._decision_bytes:
        raise ValueError("HANNA shrinkage Sol stage requires analyzer-minted frozen Grok decision")
    metrics = json.loads(value._metrics_bytes); recomputed = _decision(value._schedule, metrics)
    if study.canonical(recomputed) != value._decision_bytes: raise ValueError("HANNA shrinkage frozen Grok decision or evidence drifted")
    return value._schedule, recomputed, metrics


@dataclass(frozen=True)
class ValidatedSolSchedule:
    value: Mapping[str, Any]
    _bytes: bytes
    _frozen: FrozenGrokDecision
    _token: object


def _sol_value(frozen: FrozenGrokDecision) -> dict[str, Any]:
    study = _study(); validated_schedule, decision, _metrics = _validated_frozen(frozen); schedule, _candidates = study._validated_schedule(validated_schedule)
    if decision["action"] != "advance_to_sol":
        return {"format_version": 2, "study_id": study.STUDY_ID, "kind": "baseline_stop_no_sol_schedule", "grok_decision_sha256": study.sha256(frozen._decision_bytes), "cells": [], "geometry": {"candidates": 0, "groups": 0, "sol_cells": 0}, "confirmation": {"status": "unopened", "cells": 0}}
    winner = decision["selected_candidate_id"]; candidate_index = {row["candidate_id"]: row for row in schedule["candidates"]}
    if winner not in candidate_index or winner == study.BASELINE_ID: raise ValueError("HANNA shrinkage frozen winner is invalid")
    grok_index = {(row["item_id"], row["candidate_id"]): row for row in schedule["cells"]}; cells = []
    for group in schedule["groups"][:2]:
        for candidate_id in (study.BASELINE_ID, winner):
            source = grok_index[(group["item_id"], candidate_id)]; candidate = candidate_index[candidate_id]; payload = study.payload_bytes(source)
            key = {"study_id": study.STUDY_ID, "route_name": "sol_validation", "item_id": group["item_id"], "candidate_id": candidate_id}
            cells.append({"ordinal": len(cells) + 1, "cell_id": "shrinkage-cell-" + study.sha256(key)[:16], "route_name": "sol_validation", **group, "candidate_id": candidate_id, "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "payload_base64": source["payload_base64"], "payload_sha256": study.sha256(payload)})
    result = {"format_version": 2, "study_id": study.STUDY_ID, "kind": "frozen_winner_two_group_sol_schedule", "grok_decision_sha256": study.sha256(frozen._decision_bytes), "selected_candidate_id": winner, "candidate_order": [study.BASELINE_ID, winner], "groups": schedule["groups"][:2], "cells": cells, "geometry": {"candidates": 2, "groups": 2, "sol_cells": 4}, "confirmation": {"status": "unopened", "cells": 0}, "provider_calls_made": 0, "process_launches": 0, "runtime_authority": "none"}
    result["schedule_sha256"] = study.sha256(result)
    return result


def build_sol_schedule(*, frozen: FrozenGrokDecision) -> ValidatedSolSchedule:
    study = _study(); value = _sol_value(frozen); raw = study.canonical(value)
    return ValidatedSolSchedule(json.loads(raw), raw, frozen, _SOL_TOKEN)


def _validated_sol_schedule(value: Any, frozen: FrozenGrokDecision) -> dict[str, Any]:
    study = _study(); _validated_frozen(frozen)
    if (not isinstance(value, ValidatedSolSchedule) or value._token is not _SOL_TOKEN or value._frozen is not frozen
            or study.canonical(dict(value.value)) != value._bytes or study.canonical(_sol_value(frozen)) != value._bytes):
        raise ValueError("HANNA shrinkage Sol schedule token/bytes/frozen binding drifted")
    return json.loads(value._bytes)


def validate_sol(*, frozen: FrozenGrokDecision, sol_schedule: ValidatedSolSchedule, projected_group_metrics: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    study = _study(); decision = _validated_frozen(frozen)[1]; schedule = _validated_sol_schedule(sol_schedule, frozen)
    if decision["action"] != "advance_to_sol":
        if schedule["cells"] or projected_group_metrics: raise ValueError("HANNA shrinkage baseline stop requires zero Sol cells")
        return {"passed": False, "action": "baseline_stop", "selected_candidate_id": study.BASELINE_ID, "confirmation": {"status": "unopened", "cells": 0}, "claim": "NO-GO"}
    matrix = _matrix(schedule, projected_group_metrics, route="sol_validation", expected=4); winner = decision["selected_candidate_id"]
    groups = [row["prompt_group_id"] for row in schedule["groups"]]; deltas = [matrix[winner][group] - matrix[study.BASELINE_ID][group] for group in groups]
    passed = fmean(deltas) <= 1e-12 and max(deltas) <= 0.10 + 1e-12
    return {"format_version": 2, "study_id": study.STUDY_ID, "kind": "two_group_sol_nonreversal_decision", "selected_candidate_id": winner, "aggregate_delta": fmean(deltas), "group_deltas": deltas, "passed": passed, "action": "retain_candidate" if passed else "baseline_stop", "sol_cannot_substitute": True, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "claim": "NO-GO until independently replayed native evidence"}
