"""Provider-free, leave-one-group-out affine calibration diagnostic for V13."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v13-train-expansion-calibration-v1"
CONTRACT_PATH = HERE / "calibration-contract.json"
CONTRACT_SHA256 = "c9b6aeefc2e66fbe8cb331f43f655d1f3ae5d88b3a3507084bd58441f250ae77"
V13 = HERE / "study.py"
V13_SHA256 = "f2b5a4c178cf2a7919b5dfd8c5ddde7bf5c1e0e9aa81a2f2f4d0bdd9b97c8261"
V13_CONTRACT_SHA256 = "f4868f88e001d07a02c5cf35b12b923c9fa8c53a0ce6010151b1142ad87495a9"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
SLOPE_MIN, SLOPE_MAX = 0.1, 2.0
INTERCEPT_MIN, INTERCEPT_MAX = -2.0, 2.0
CLIP_MIN, CLIP_MAX = 0.0, 5.0
SEED, TRIALS, OPTUNA_VERSION = 20260904, 64, "4.9.0"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _strict(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"invalid {label}")
    return value


def contract() -> dict[str, Any]:
    raw = CONTRACT_PATH.read_bytes()
    if sha256(raw) != CONTRACT_SHA256:
        raise ValueError("calibration contract drifted")
    value = _strict(raw, "calibration contract")
    if value.get("study_id") != STUDY_ID or value.get("optimizer", {}).get("trials_per_fold") != TRIALS or value["optimizer"].get("version") != OPTUNA_VERSION:
        raise ValueError("calibration contract schema drifted")
    return value


def _load_v13() -> ModuleType:
    raw = V13.read_bytes()
    if sha256(raw) != V13_SHA256:
        raise ValueError("pinned V13 source drifted")
    spec = importlib.util.spec_from_file_location("_v13_calibration_source", V13)
    if spec is None or spec.loader is None:
        raise ValueError("pinned V13 source cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if V13.read_bytes() != raw or module.sha256(module.CONTRACT_PATH.read_bytes()) != V13_CONTRACT_SHA256:
        raise ValueError("pinned V13 dependency drifted during load")
    return module


def clip(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("finite calibration value required")
    return min(CLIP_MAX, max(CLIP_MIN, value))


def _mean(values: Sequence[float]) -> float:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("finite nonempty values required")
    return sum(values) / len(values)


def average_tie_spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2 or not all(math.isfinite(value) for value in (*left, *right)):
        raise ValueError("finite paired rank values required")

    def ranks(values: Sequence[float]) -> list[float]:
        ordered = sorted(enumerate(values), key=lambda pair: pair[1])
        result = [0.0] * len(values); start = 0
        while start < len(ordered):
            end = start + 1
            while end < len(ordered) and ordered[end][1] == ordered[start][1]:
                end += 1
            rank = (start + 1 + end) / 2.0
            for index, _value in ordered[start:end]:
                result[index] = rank
            start = end
        return result

    x, y = ranks(left), ranks(right)
    centered_x = [value - _mean(x) for value in x]
    centered_y = [value - _mean(y) for value in y]
    denominator = math.sqrt(sum(value * value for value in centered_x) * sum(value * value for value in centered_y))
    return None if denominator == 0.0 else sum(a * b for a, b in zip(centered_x, centered_y, strict=True)) / denominator


def _validate_child20_cells(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells = report.get("cells")
    if not isinstance(cells, list) or report.get("study_id") != "hbq-human-alignment-optimizer-v13-train-expansion-v1":
        raise ValueError("V13 report identity drifted")
    child = [dict(cell) for cell in cells if isinstance(cell, Mapping) and cell.get("candidate_id") == CHILD20]
    if len(child) != 44 or len({cell.get("cell_id") for cell in child}) != 44 or len({cell.get("prompt_group_id") for cell in child}) != 22:
        raise ValueError("V13 child20 geometry drifted")
    for cell in child:
        if cell.get("partition") != "train" or not isinstance(cell.get("coverage"), Mapping):
            raise ValueError("V13 child20 partition or coverage drifted")
        for dimension in DIMS:
            score, target, covered = cell.get("scores", {}).get(dimension), cell.get("target", {}).get(dimension), cell["coverage"].get(dimension)
            if not isinstance(covered, bool) or not isinstance(score, (int, float)) or not isinstance(target, (int, float)) or not math.isfinite(float(score)) or not math.isfinite(float(target)):
                raise ValueError("V13 child20 finite score projection drifted")
    return sorted(child, key=lambda cell: str(cell["cell_id"]))


def _parameters(value: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    if set(value) != set(DIMS):
        raise ValueError("calibration dimensions drifted")
    result: dict[str, dict[str, float]] = {}
    for dimension in DIMS:
        row = value[dimension]
        if not isinstance(row, Mapping):
            raise TypeError("calibration parameter shape drifted")
        slope, intercept = row.get("slope"), row.get("intercept")
        if not isinstance(slope, (int, float)) or not isinstance(intercept, (int, float)) or not math.isfinite(float(slope)) or not math.isfinite(float(intercept)) or not SLOPE_MIN <= float(slope) <= SLOPE_MAX or not INTERCEPT_MIN <= float(intercept) <= INTERCEPT_MAX:
            raise ValueError("calibration parameter bounds drifted")
        result[dimension] = {"slope": float(slope), "intercept": float(intercept)}
    return result


def predict(scores: Mapping[str, Any], parameters: Mapping[str, Any]) -> dict[str, float]:
    checked = _parameters(parameters)
    result: dict[str, float] = {}
    for dimension in DIMS:
        score = scores.get(dimension)
        if not isinstance(score, (int, float)) or not math.isfinite(float(score)):
            raise ValueError("finite score required for calibration")
        result[dimension] = clip(checked[dimension]["slope"] * float(score) + checked[dimension]["intercept"])
    return result


def equal_group_mae(cells: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[float]] = defaultdict(list)
    expected = {str(cell.get("cell_id")) for cell in cells}
    if set(predictions) != expected:
        raise ValueError("prediction inventory drifted")
    for cell in cells:
        cell_id, group = str(cell["cell_id"]), cell.get("prompt_group_id")
        target, scores = cell.get("target"), predictions[cell_id]
        if not isinstance(group, str) or not isinstance(target, Mapping) or not isinstance(scores, Mapping):
            raise TypeError("calibration metric shape drifted")
        grouped[group].append(_mean([abs(float(scores[dimension]) - float(target[dimension])) for dimension in DIMS]))
    per_group = {group: _mean(values) for group, values in sorted(grouped.items())}
    return {"per_group_mean_item_mae": per_group, "equal_group_mean_item_mae": _mean(list(per_group.values())), "item_count": len(cells), "group_count": len(per_group)}


def _fit_fold(training_cells: Sequence[Mapping[str, Any]], *, seed: int) -> dict[str, Any]:
    if len({cell.get("prompt_group_id") for cell in training_cells}) != 21:
        raise ValueError("each calibration fold requires exactly 21 fitting groups")
    try:
        import optuna  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("Optuna is required for this frozen calibration diagnostic") from error
    if optuna.__version__ != OPTUNA_VERSION:
        raise ValueError("frozen Optuna version drifted")
    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)

    def objective(trial: Any) -> float:
        parameters = {
            dimension: {
                "slope": trial.suggest_float(f"{dimension}_slope", SLOPE_MIN, SLOPE_MAX),
                "intercept": trial.suggest_float(f"{dimension}_intercept", INTERCEPT_MIN, INTERCEPT_MAX),
            }
            for dimension in DIMS
        }
        predictions = {str(cell["cell_id"]): predict(cell["scores"], parameters) for cell in training_cells}
        return float(equal_group_mae(training_cells, predictions)["equal_group_mean_item_mae"])

    study.optimize(objective, n_trials=TRIALS, n_jobs=1, catch=())
    if len(study.trials) != TRIALS or study.best_trial.number < 0:
        raise ValueError("frozen Optuna trial count drifted")
    parameters = _parameters({dimension: {"slope": study.best_trial.params[f"{dimension}_slope"], "intercept": study.best_trial.params[f"{dimension}_intercept"]} for dimension in DIMS})
    predictions = {str(cell["cell_id"]): predict(cell["scores"], parameters) for cell in training_cells}
    return {"seed": seed, "trials": TRIALS, "optuna_version": OPTUNA_VERSION, "parameters": parameters, "training": equal_group_mae(training_cells, predictions)}


def _rank_metrics(cells: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]) -> dict[str, float | None]:
    return {
        dimension: average_tie_spearman(
            [float(predictions[str(cell["cell_id"])][dimension]) for cell in cells],
            [float(cell["target"][dimension]) for cell in cells],
        )
        for dimension in DIMS
    }


def _disjoint_fresh_output(output_root: Path, *, source_files: Sequence[Path], source_roots: Sequence[Path]) -> Path:
    output = Path(output_root).resolve(strict=False)
    if output.exists():
        raise ValueError("calibration output root must be fresh")
    if not output.parent.is_dir():
        raise ValueError("calibration output parent is absent")
    protected = [Path(path).resolve(strict=True).parent for path in source_files]
    protected.extend(Path(path).resolve(strict=True) for path in source_roots)
    for source in protected:
        if output == source or output.is_relative_to(source) or source.is_relative_to(output):
            raise ValueError("calibration output overlaps immutable V13 input")
    return output


def _write_result(output_root: Path, value: Mapping[str, Any]) -> None:
    output_root.mkdir()
    destination = output_root / "calibration.json"
    temporary = output_root / ".calibration.json.tmp"
    temporary.write_bytes(canonical(value))
    temporary.replace(destination)


def run(*, v13_output_root: Path, output_root: Path, authorization_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path) -> dict[str, Any]:
    frozen = contract()
    source_root = Path(v13_output_root)
    output = _disjoint_fresh_output(
        Path(output_root),
        source_files=(V13, CONTRACT_PATH, Path(split_manifest), Path(hanna_csv), Path(successor_contract)),
        source_roots=(source_root, REPO),
    )
    v13 = _load_v13()
    report = v13.report(output_root=source_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract))
    child = _validate_child20_cells(report)
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in child:
        by_group[str(cell["prompt_group_id"])].append(cell)
    groups = sorted(by_group)
    if len(groups) != 22 or any(not rows for rows in by_group.values()):
        raise ValueError("V13 child20 group inventory drifted")

    uncalibrated = {str(cell["cell_id"]): {dimension: float(cell["scores"][dimension]) for dimension in DIMS} for cell in child}
    constant_three = {str(cell["cell_id"]): {dimension: 3.0 for dimension in DIMS} for cell in child}
    heldout_predictions: dict[str, dict[str, float]] = {}
    folds: list[dict[str, Any]] = []
    for fold_index, heldout_group in enumerate(groups):
        training = [cell for group in groups if group != heldout_group for cell in by_group[group]]
        heldout = by_group[heldout_group]
        fitted = _fit_fold(training, seed=SEED + fold_index)
        parameters = _parameters(fitted.get("parameters", {}))
        training_metric = fitted.get("training")
        if not isinstance(training_metric, Mapping) or fitted.get("seed") != SEED + fold_index or fitted.get("trials") != TRIALS:
            raise ValueError("frozen fold optimizer metadata drifted")
        predicted = {str(cell["cell_id"]): predict(cell["scores"], parameters) for cell in heldout}
        heldout_predictions.update(predicted)
        folds.append({"fold_index": fold_index, "heldout_prompt_group_id": heldout_group, "fit_prompt_group_ids": [group for group in groups if group != heldout_group], "parameters": parameters, "training_equal_group_mean_item_mae": float(training_metric["equal_group_mean_item_mae"]), "heldout_predictions": [{"cell_id": cell["cell_id"], "scores": predicted[str(cell["cell_id"])]} for cell in heldout]})
    if set(heldout_predictions) != {str(cell["cell_id"]) for cell in child} or len(folds) != 22:
        raise ValueError("out-of-fold prediction inventory drifted")
    calibrated = equal_group_mae(child, heldout_predictions)
    input_data = {"report_study_id": report["study_id"], "report_cells": report["cells"], "child20_cell_ids": [cell["cell_id"] for cell in child]}
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": frozen["kind"],
        "authority": frozen["authority"],
        "analysis_rule": frozen["analysis_rule"],
        "contract_sha256": CONTRACT_SHA256,
        "optuna_version": OPTUNA_VERSION,
        "input_data_sha256": sha256(input_data),
        "input_report_sha256": sha256(report),
        "geometry": frozen["geometry"],
        "folds": folds,
        "comparators": {
            "uncalibrated_child20": {**equal_group_mae(child, uncalibrated), "pooled_average_tie_spearman": _rank_metrics(child, uncalibrated)},
            "fixed_three": {**equal_group_mae(child, constant_three), "pooled_average_tie_spearman": _rank_metrics(child, constant_three)},
        },
        "out_of_fold_calibrated_child20": {**calibrated, "pooled_average_tie_spearman": _rank_metrics(child, heldout_predictions)},
        "interpretation": "provider_free_development_train_calibration_diagnostic_only; no_candidate_export_or_runtime_or_promotion_or_confirmation_authority",
    }
    _write_result(output, result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v13-output-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--acknowledgement-sha256", required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--hanna-csv", type=Path, required=True)
    parser.add_argument("--successor-contract", type=Path, required=True)
    args = parser.parse_args(argv)
    print(canonical(run(v13_output_root=args.v13_output_root, output_root=args.output_root, authorization_acknowledgement_sha256=args.acknowledgement_sha256, split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract)).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
