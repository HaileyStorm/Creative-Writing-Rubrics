"""Provider-free, TRAIN-only original-HBQ mapped-score calibration diagnostic."""
from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CONTRACT_PATH = HERE / "development-calibration-contract.json"
STUDY_ID = "hbq-human-alignment-v3-fresh88-development-calibration-v1"
ITEMS_SHA256 = "e464ecd5748164ab96a7ba88ae03e0a777edd945ab5fbaee42c38d5ccaae4ec5"
SPLIT_SHA256 = "6ffa942b595449f4118c2cd51f3a36716126612a7c10f4765953c17eb1efdbc2"
MAPPING_SETS_SHA256 = "33de035935dc1304cf782d596038354f65efb00b019babe0cf61aa9474d142c5"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
SEED, TRIALS, OPTUNA_VERSION = 20260904, 64, "4.9.0"
_JSON_STRING = re.compile(rb'"(?P<key>item_id|story_sha256|prompt_sha256)"\s*:\s*"(?P<value>(?:[^"\\\\]|\\\\.)*)"')


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _strict(raw: bytes, label: str, *, canonical_required: bool = True) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or (canonical_required and canonical(value) != raw):
        raise ValueError(f"invalid {label}")
    return value


def contract() -> dict[str, Any]:
    value = _strict(CONTRACT_PATH.read_bytes(), "development calibration contract")
    if (set(value) != {"analysis_rule", "authority", "format_version", "geometry", "kind", "optimizer", "source", "study_id"}
            or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID
            or value.get("kind") != "provider_free_full_hbq_train_leave_one_group_out_calibration_diagnostic"
            or value.get("geometry") != {"dimensions": 6, "fitting_groups_per_fold": 23, "train_groups": 24, "train_items": 48}
            or value.get("authority") != {"confirmation_access": "forbidden_in_this_study", "confirmation_cells": 0, "development_train_only": True, "promotion": "none", "runtime": "none", "selection": "none"}
            or value.get("analysis_rule") != {"coverage": "preserve_finite_mapped_scores_even_when_partial_coverage; missing_mapped_dimension_uses_fixed_three_and_is_excluded_only_from_that_dimension_fit", "fitting": "TRAIN_48_only; leave_one_of_24_prompt_groups_out; heldout_targets_excluded_from_every_fit", "primary": "absolute_error_per_item_then_mean_within_prompt_group_then_equal_mean_across_24_train_groups", "rank": "pooled_average_tie_spearman_is_descriptive_only"}
            or value.get("source") != {"items_sha256": ITEMS_SHA256, "mapping_sets_sha256": MAPPING_SETS_SHA256, "split_manifest_sha256": SPLIT_SHA256}
            or value.get("optimizer") != {"affine": {"bounds": {"intercept": [-2.0, 4.0], "slope": [0.0, 8.0]}, "clip": [1.0, 5.0], "penalty": 0.01, "seed": SEED, "single_worker": True, "trials_per_fold": TRIALS, "type": "optuna.TPESampler", "version": OPTUNA_VERSION}, "ridge": {"alpha": 1.0, "baseline": "1_plus_4p", "feature": "p_minus_half; missing_input_imputed_zero", "fit": "weighted_by_inverse_usable_group_item_count; residual_correction; intercept_unpenalized"}}):
        raise ValueError("development calibration contract drifted")
    return value


def _finite(value: Any) -> float | None:
    return float(value) if type(value) in {int, float} and math.isfinite(float(value)) else None


def _mean(values: Sequence[float]) -> float:
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("finite nonempty values required")
    return sum(values) / len(values)


def _clip(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("finite prediction required")
    return min(5.0, max(1.0, value))


def average_tie_spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2 or any(not math.isfinite(value) for value in (*left, *right)):
        raise ValueError("finite paired rank values required")

    def ranks(values: Sequence[float]) -> list[float]:
        ordered, result, start = sorted(enumerate(values), key=lambda pair: pair[1]), [0.0] * len(values), 0
        while start < len(ordered):
            end = start + 1
            while end < len(ordered) and ordered[end][1] == ordered[start][1]:
                end += 1
            for index, _value in ordered[start:end]:
                result[index] = (start + 1 + end) / 2.0
            start = end
        return result

    x, y = ranks(left), ranks(right)
    centered_x, centered_y = [value - _mean(x) for value in x], [value - _mean(y) for value in y]
    denominator = math.sqrt(sum(value * value for value in centered_x) * sum(value * value for value in centered_y))
    return None if denominator == 0.0 else sum(a * b for a, b in zip(centered_x, centered_y, strict=True)) / denominator


def _train_partition(split_raw: bytes) -> list[dict[str, str]]:
    split = _strict(split_raw, "split manifest", canonical_required=False)
    rows = split.get("items")
    if not isinstance(rows, list):
        raise TypeError("split manifest item projection is invalid")
    train = [dict(row) for row in rows if isinstance(row, Mapping) and row.get("partition") == "train"]
    keys = [(row.get("prompt_group_id"), row.get("item_id")) for row in train]
    if (len(train) != 48 or len(set(keys)) != 48 or len({row.get("prompt_group_id") for row in train}) != 24
            or any(any(not isinstance(row.get(key), str) for key in ("prompt_group_id", "item_id")) for row in train)):
        raise ValueError("frozen TRAIN split geometry drifted")
    return sorted(({key: str(row[key]) for key in ("prompt_group_id", "item_id")} for row in train), key=lambda row: (row["prompt_group_id"], row["item_id"]))


def _line_identity(raw: bytes) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _JSON_STRING.finditer(raw):
        key = match.group("key").decode("ascii")
        if key in values:
            raise ValueError("items JSONL identity is duplicated")
        try:
            value = json.loads(b'"' + match.group("value") + b'"')
        except json.JSONDecodeError as error:
            raise ValueError("items JSONL identity is invalid") from error
        if not isinstance(value, str):
            raise TypeError("items JSONL identity is invalid")
        values[key] = value
    if set(values) != {"item_id", "story_sha256", "prompt_sha256"}:
        raise ValueError("items JSONL row lacks an exact identity")
    return values


def _source_row(raw: bytes, *, identity: Mapping[str, str], prompt_group_id: str) -> dict[str, Any]:
    row = _strict(raw, "TRAIN items JSONL row", canonical_required=False)
    if any(row.get(key) != value for key, value in identity.items()) or row.get("prompt_group_id") != prompt_group_id:
        raise ValueError("TRAIN item identity drifted")
    if any(not re.fullmatch(r"[0-9a-f]{64}", identity[key]) for key in ("story_sha256", "prompt_sha256")) or prompt_group_id != "prompt-" + identity["prompt_sha256"][:16]:
        raise ValueError("TRAIN item source binding drifted")
    mapped, human = row.get("hbq_mapping"), row.get("human_means")
    if not isinstance(mapped, Mapping) or set(mapped) != set(DIMS) or not isinstance(human, Mapping) or set(human) != set(DIMS):
        raise ValueError("TRAIN full-HBQ mapping schema drifted")
    score: dict[str, float | None] = {}; coverage: dict[str, Any] = {}; target: dict[str, float] = {}
    for dimension in DIMS:
        mapping, human_value = mapped[dimension], _finite(human[dimension])
        if (not isinstance(mapping, Mapping) or set(mapping) != {"score", "coverage", "unresolved", "not_applicable", "question_count"}
                or human_value is None or not 1.0 <= human_value <= 5.0):
            raise ValueError("TRAIN mapped target schema drifted")
        coverage_value = _finite(mapping.get("coverage"))
        if coverage_value is None or not 0.0 <= coverage_value <= 1.0:
            raise ValueError("TRAIN mapped coverage schema drifted")
        score_value = _finite(mapping.get("score"))
        if score_value is not None and not 0.0 <= score_value <= 1.0:
            raise ValueError("TRAIN mapped score schema drifted")
        score[dimension], coverage[dimension], target[dimension] = score_value, coverage_value, human_value
    return {"item_id": identity["item_id"], "prompt_group_id": prompt_group_id, "scores": score, "coverage": coverage, "target": target,
            "source_binding_sha256": sha256({"item_id": identity["item_id"], "prompt_group_id": prompt_group_id, "story_sha256": identity["story_sha256"], "prompt_sha256": identity["prompt_sha256"]})}


def source_items(*, items_path: Path, split_manifest: Path) -> list[dict[str, Any]]:
    split_raw = Path(split_manifest).read_bytes()
    if sha256(split_raw) != SPLIT_SHA256:
        raise ValueError("frozen split manifest pin drifted")
    train = _train_partition(split_raw)
    by_split_id = {row["item_id"]: row["prompt_group_id"] for row in train}
    selected: dict[str, dict[str, Any]] = {}
    items_raw = Path(items_path).read_bytes()
    if sha256(items_raw) != ITEMS_SHA256:
        raise ValueError("frozen items input pin drifted")
    for raw in items_raw.splitlines():
        if not raw:
            raise ValueError("items JSONL contains a blank row")
        identity = _line_identity(raw)
        split_id = "item-" + hashlib.sha256(identity["item_id"].encode("utf-8")).hexdigest()[:16]
        group = by_split_id.get(split_id)
        if group is not None:
            item_id = identity["item_id"]
            if item_id in selected:
                raise ValueError("duplicate TRAIN item")
            selected[item_id] = _source_row(raw, identity=identity, prompt_group_id=group)
    if len(selected) != len(by_split_id):
        raise ValueError("TRAIN items are not the exact frozen split")
    return sorted(selected.values(), key=lambda row: (row["prompt_group_id"], row["item_id"]))


def _baseline(scores: Mapping[str, float | None]) -> dict[str, float]:
    return {dimension: 3.0 if scores[dimension] is None else _clip(1.0 + 4.0 * float(scores[dimension])) for dimension in DIMS}


def _constant_three(_scores: Mapping[str, float | None]) -> dict[str, float]:
    return {dimension: 3.0 for dimension in DIMS}


def _usable_dimension_equal_group_mae(cells: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    expected = {str(cell["item_id"]) for cell in cells}
    if set(predictions) != expected:
        raise ValueError("prediction inventory drifted")
    per_dimension: dict[str, dict[str, float]] = {}
    for cell in cells:
        item_id, group, target, predicted, scores = str(cell["item_id"]), cell.get("prompt_group_id"), cell.get("target"), predictions[str(cell["item_id"])], cell.get("scores")
        if not isinstance(group, str) or not isinstance(target, Mapping) or not isinstance(predicted, Mapping):
            raise TypeError("calibration metric schema drifted")
        if not isinstance(scores, Mapping):
            raise TypeError("calibration score schema drifted")
        for dimension in DIMS:
            if scores.get(dimension) is None:
                continue
            value, reference = _finite(predicted.get(dimension)), _finite(target.get(dimension))
            if value is None or reference is None:
                raise ValueError(f"non-finite prediction or target for {item_id}")
            per_dimension.setdefault(dimension, {}).setdefault(group, []).append(abs(value - reference))
    for dimension in DIMS:
        grouped = per_dimension.get(dimension, {})
        if not grouped:
            raise ValueError(f"no usable mapped score for {dimension}")
        per_dimension[dimension] = {group: _mean(values) for group, values in sorted(grouped.items())}
    dimension_means = {dimension: _mean(list(per_dimension[dimension].values())) for dimension in DIMS}
    return {"per_dimension_per_group_mean_item_mae": per_dimension, "per_dimension_equal_group_mean_item_mae": dimension_means,
            "equal_group_mean_item_mae": _mean(list(dimension_means.values())), "item_count": len(cells),
            "group_count": {dimension: len(per_dimension[dimension]) for dimension in DIMS}}


def equal_group_mae(cells: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    expected = {str(cell["item_id"]) for cell in cells}
    if set(predictions) != expected:
        raise ValueError("prediction inventory drifted")
    grouped: dict[str, list[float]] = defaultdict(list)
    for cell in cells:
        item_id, group, target, predicted = str(cell["item_id"]), cell.get("prompt_group_id"), cell.get("target"), predictions[str(cell["item_id"])]
        if not isinstance(group, str) or not isinstance(target, Mapping) or not isinstance(predicted, Mapping):
            raise TypeError("calibration metric schema drifted")
        errors = []
        for dimension in DIMS:
            value, reference = _finite(predicted.get(dimension)), _finite(target.get(dimension))
            if value is None or reference is None:
                raise ValueError(f"non-finite prediction or target for {item_id}")
            errors.append(abs(value - reference))
        grouped[group].append(_mean(errors))
    per_group = {group: _mean(errors) for group, errors in sorted(grouped.items())}
    return {"per_group_mean_item_mae": per_group, "equal_group_mean_item_mae": _mean(list(per_group.values())), "item_count": len(cells), "group_count": len(per_group)}


def _parameter_penalty(parameters: Mapping[str, Mapping[str, float]]) -> float:
    return _mean([((parameters[dimension]["slope"] - 4.0) / 4.0) ** 2 + ((parameters[dimension]["intercept"] - 1.0) / 2.0) ** 2 for dimension in DIMS])


def _affine_predictions(cells: Sequence[Mapping[str, Any]], parameters: Mapping[str, Mapping[str, float]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for cell in cells:
        scores = cell["scores"]
        result[str(cell["item_id"])] = {
            dimension: 3.0 if scores[dimension] is None else _clip(parameters[dimension]["slope"] * float(scores[dimension]) + parameters[dimension]["intercept"])
            for dimension in DIMS
        }
    return result


def fit_affine(training_cells: Sequence[Mapping[str, Any]], *, seed: int) -> dict[str, Any]:
    if len({cell.get("prompt_group_id") for cell in training_cells}) != 23:
        raise ValueError("each affine fold requires exactly 23 TRAIN groups")
    try:
        import optuna  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("Optuna is required for this development-only diagnostic") from error
    if optuna.__version__ != OPTUNA_VERSION:
        raise ValueError("frozen Optuna version drifted")
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))

    def objective(trial: Any) -> float:
        parameters = {
            dimension: {"slope": trial.suggest_float(f"{dimension}_slope", 0.0, 8.0), "intercept": trial.suggest_float(f"{dimension}_intercept", -2.0, 4.0)}
            for dimension in DIMS
        }
        predictions = _affine_predictions(training_cells, parameters)
        return float(_usable_dimension_equal_group_mae(training_cells, predictions)["equal_group_mean_item_mae"]) + 0.01 * _parameter_penalty(parameters)

    study.optimize(objective, n_trials=TRIALS, n_jobs=1, catch=())
    if len(study.trials) != TRIALS or study.best_trial.number < 0:
        raise ValueError("frozen Optuna trial count drifted")
    parameters = {
        dimension: {"slope": float(study.best_trial.params[f"{dimension}_slope"]), "intercept": float(study.best_trial.params[f"{dimension}_intercept"])}
        for dimension in DIMS
    }
    return {"seed": seed, "trials": TRIALS, "optuna_version": OPTUNA_VERSION, "parameters": parameters,
            "training_usable_dimension_metric": _usable_dimension_equal_group_mae(training_cells, _affine_predictions(training_cells, parameters)), "objective_penalty": _parameter_penalty(parameters)}


def _ridge_features(scores: Mapping[str, float | None]) -> list[float]:
    return [0.0 if scores[dimension] is None else float(scores[dimension]) - 0.5 for dimension in DIMS]


def fit_ridge(training_cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len({cell.get("prompt_group_id") for cell in training_cells}) != 23:
        raise ValueError("each ridge fold requires exactly 23 TRAIN groups")
    try:
        import numpy as np  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("NumPy is required for this development-only diagnostic") from error
    coefficients: dict[str, dict[str, Any]] = {}
    for dimension in DIMS:
        usable = [cell for cell in training_cells if cell["scores"][dimension] is not None]
        if not usable:
            coefficients[dimension] = {"intercept": 0.0, "deltas": {feature: 0.0 for feature in DIMS}, "fitted_items": 0}
            continue
        group_counts: dict[str, int] = defaultdict(int)
        for cell in usable:
            group_counts[str(cell["prompt_group_id"])] += 1
        x = np.array([[1.0, *_ridge_features(cell["scores"])] for cell in usable], dtype=float)
        weights = np.array([1.0 / group_counts[str(cell["prompt_group_id"])] for cell in usable], dtype=float)
        residual = np.array([float(cell["target"][dimension]) - (1.0 + 4.0 * float(cell["scores"][dimension])) for cell in usable], dtype=float)
        penalty = np.diag([0.0, *([1.0] * len(DIMS))])
        beta = np.linalg.solve(x.T @ (weights[:, None] * x) + penalty, x.T @ (weights * residual))
        if not np.isfinite(beta).all():
            raise ValueError("ridge fit is non-finite")
        coefficients[dimension] = {"intercept": float(beta[0]), "deltas": {feature: float(beta[index + 1]) for index, feature in enumerate(DIMS)}, "fitted_items": len(usable)}
    return {"alpha": 1.0, "feature_imputation": "missing_p_minus_half_is_zero", "group_weighting": "inverse_usable_group_item_count", "coefficients": coefficients}


def _ridge_predictions(cells: Sequence[Mapping[str, Any]], fit: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    coefficients = fit.get("coefficients")
    if not isinstance(coefficients, Mapping) or set(coefficients) != set(DIMS):
        raise ValueError("ridge fit schema drifted")
    predicted: dict[str, dict[str, float]] = {}
    for cell in cells:
        features = _ridge_features(cell["scores"]); result: dict[str, float] = {}
        for dimension in DIMS:
            values = coefficients[dimension]
            if not isinstance(values, Mapping) or not isinstance(values.get("deltas"), Mapping):
                raise TypeError("ridge coefficient schema drifted")
            result[dimension] = 3.0 if cell["scores"][dimension] is None else _clip(
                1.0 + 4.0 * float(cell["scores"][dimension]) + float(values["intercept"])
                + sum(float(values["deltas"][feature]) * features[index] for index, feature in enumerate(DIMS))
            )
        predicted[str(cell["item_id"])] = result
    return predicted


def _bias_and_rank(cells: Sequence[Mapping[str, Any]], predictions: Mapping[str, Mapping[str, float]]) -> dict[str, Any]:
    return {
        "mean_signed_error": {
            dimension: _mean([float(predictions[str(cell["item_id"])][dimension]) - float(cell["target"][dimension]) for cell in cells])
            for dimension in DIMS
        },
        "actual_pooled_average_tie_spearman": {
            dimension: average_tie_spearman(
                [float(predictions[str(cell["item_id"])][dimension]) for cell in cells],
                [float(cell["target"][dimension]) for cell in cells],
            )
            for dimension in DIMS
        },
    }


def _coverage_and_missing_counts(cells: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        dimension: {
            "finite_mapped_score": sum(cell["scores"][dimension] is not None for cell in cells),
            "missing_mapped_score": sum(cell["scores"][dimension] is None for cell in cells),
            "partial_coverage": sum(float(cell["coverage"][dimension]) < 1.0 for cell in cells),
        }
        for dimension in DIMS
    }


def _fresh_output(output_root: Path, *, inputs: Sequence[Path]) -> Path:
    output = Path(output_root).resolve(strict=False)
    if output.exists() or not output.parent.is_dir():
        raise ValueError("development calibration output root must be fresh with an existing parent")
    for source in (*inputs, HERE, REPO):
        protected = Path(source).resolve(strict=True).parent if Path(source).is_file() else Path(source).resolve(strict=True)
        if output == protected or output.is_relative_to(protected) or protected.is_relative_to(output):
            raise ValueError("development calibration output overlaps immutable input")
    return output


def _write_result(output: Path, result: Mapping[str, Any]) -> None:
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        (staging / "result.json").write_bytes(canonical(result))
        staging.replace(output)
    except BaseException:
        for path in staging.glob("*"):
            path.unlink()
        staging.rmdir()
        raise


def run(*, items_path: Path, split_manifest: Path, output_root: Path) -> dict[str, Any]:
    output = _fresh_output(Path(output_root), inputs=(Path(items_path), Path(split_manifest), CONTRACT_PATH))
    frozen = contract()
    cells = source_items(items_path=Path(items_path), split_manifest=Path(split_manifest))
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cell in cells:
        by_group[str(cell["prompt_group_id"])].append(cell)
    groups = sorted(by_group)
    if len(cells) != 48 or len(groups) != 24 or any(not rows for rows in by_group.values()):
        raise ValueError("TRAIN source geometry drifted")

    all_predictions = {"constant_three": {}, "diagnostic_1_plus_4p": {}, "positive_affine": {}, "ridge_residual": {}}
    folds: list[dict[str, Any]] = []
    for fold_index, heldout_group in enumerate(groups):
        training = [cell for group in groups if group != heldout_group for cell in by_group[group]]
        heldout = by_group[heldout_group]
        affine, ridge = fit_affine(training, seed=SEED + fold_index), fit_ridge(training)
        fold_predictions = {
            "constant_three": {str(cell["item_id"]): _constant_three(cell["scores"]) for cell in heldout},
            "diagnostic_1_plus_4p": {str(cell["item_id"]): _baseline(cell["scores"]) for cell in heldout},
            "positive_affine": _affine_predictions(heldout, affine["parameters"]),
            "ridge_residual": _ridge_predictions(heldout, ridge),
        }
        for name, predicted in fold_predictions.items():
            all_predictions[name].update(predicted)
        folds.append({
            "fold_index": fold_index,
            "heldout_prompt_group_id": heldout_group,
            "fit_prompt_group_ids": [group for group in groups if group != heldout_group],
            "fits": {"positive_affine": affine, "ridge_residual": ridge},
            "oof_predictions": [
                {"item_id": cell["item_id"], "prompt_group_id": cell["prompt_group_id"], "source_binding_sha256": cell["source_binding_sha256"], "scores": cell["scores"], "coverage": cell["coverage"], "target": cell["target"],
                 "predictions": {name: predicted[str(cell["item_id"])] for name, predicted in fold_predictions.items()}}
                for cell in heldout
            ],
        })
    expected = {str(cell["item_id"]) for cell in cells}
    if len(folds) != 24 or any(set(predicted) != expected for predicted in all_predictions.values()):
        raise ValueError("out-of-fold prediction inventory drifted")
    arms = {
        name: {**equal_group_mae(cells, predicted), **_bias_and_rank(cells, predicted)}
        for name, predicted in all_predictions.items()
    }
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": frozen["kind"],
        "authority": frozen["authority"],
        "analysis_rule": frozen["analysis_rule"],
        "input": {
            "items_sha256": ITEMS_SHA256,
            "split_manifest_sha256": SPLIT_SHA256,
            "mapping_sets_sha256": MAPPING_SETS_SHA256,
            "contract_sha256": sha256(CONTRACT_PATH.read_bytes()),
            "source_sha256": sha256(Path(__file__).read_bytes()),
        },
        "config": frozen["optimizer"],
        "geometry": frozen["geometry"],
        "coverage_and_missing_counts": _coverage_and_missing_counts(cells),
        "folds": folds,
        "arms": arms,
        "interpretation": "original_HBQ_mapped_score_calibration_diagnostic_only; no_rubric_weight_or_runtime_change_or_selection_or_promotion_or_confirmation_access",
    }
    _write_result(output, result)
    return result
