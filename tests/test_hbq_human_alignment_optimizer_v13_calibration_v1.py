from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v13-train-expansion-v1"
CALIBRATION = PACKAGE / "calibration.py"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def load():
    spec = importlib.util.spec_from_file_location("v13_calibration_test", CALIBRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def child_cells() -> list[dict[str, object]]:
    sizes = [1] * 12 + [2] * 3 + [3] * 3 + [4] * 3 + [5]
    cells: list[dict[str, object]] = []
    ordinal = 0
    for group_index, size in enumerate(sizes):
        for item_index in range(size):
            ordinal += 1
            target = {dimension: float((ordinal + offset) % 6) for offset, dimension in enumerate(DIMS)}
            scores = {dimension: max(0.0, min(5.0, target[dimension] + ((ordinal % 3) - 1) * 0.4)) for dimension in DIMS}
            cells.append(
                {
                    "cell_id": f"child-{ordinal:02d}",
                    "candidate_id": "broader-nextwave-20-missing_evidence_not_no-referent-evidence",
                    "item_id": f"item-{ordinal:02d}",
                    "prompt_group_id": f"group-{group_index:02d}",
                    "partition": "train",
                    "scores": scores,
                    "target": target,
                    "coverage": {dimension: ordinal % 2 == 0 for dimension in DIMS},
                }
            )
    assert len(cells) == 44
    return cells


def report(cells: list[dict[str, object]]) -> dict[str, object]:
    return {"study_id": "hbq-human-alignment-optimizer-v13-train-expansion-v1", "cells": cells}


def arguments(tmp_path: Path) -> dict[str, Path | str]:
    inputs = tmp_path / "inputs"
    inputs.mkdir(exist_ok=True)
    for name in ("split.json", "hanna.csv", "successor.json"):
        (inputs / name).write_text("{}", encoding="utf-8")
    source_root = tmp_path / "v13-receipts"
    source_root.mkdir(exist_ok=True)
    return {
        "v13_output_root": source_root,
        "authorization_acknowledgement_sha256": "a" * 64,
        "split_manifest": inputs / "split.json",
        "hanna_csv": inputs / "hanna.csv",
        "successor_contract": inputs / "successor.json",
    }


def install_fast_fit(monkeypatch: pytest.MonkeyPatch, calibration):
    def fit(training_cells, *, seed: int):
        slope = 0.1 + (seed % 5) * 0.2
        parameters = {dimension: {"slope": slope, "intercept": 0.0} for dimension in calibration.DIMS}
        predictions = {str(cell["cell_id"]): calibration.predict(cell["scores"], parameters) for cell in training_cells}
        return {
            "seed": seed,
            "trials": calibration.TRIALS,
            "optuna_version": calibration.OPTUNA_VERSION,
            "parameters": parameters,
            "training": calibration.equal_group_mae(training_cells, predictions),
        }

    monkeypatch.setattr(calibration, "_fit_fold", fit)


def run(monkeypatch: pytest.MonkeyPatch, calibration, tmp_path: Path, cells: list[dict[str, object]], name: str):
    monkeypatch.setattr(calibration, "_load_v13", lambda: SimpleNamespace(report=lambda **_kwargs: report(cells)))
    install_fast_fit(monkeypatch, calibration)
    return calibration.run(**arguments(tmp_path), output_root=tmp_path / name)


def test_pinned_v13_input_and_complete_seeded_loo_geometry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calibration = load()
    assert hashlib.sha256(calibration.V13.read_bytes()).hexdigest() == calibration.V13_SHA256
    contract = calibration.contract()
    assert contract["geometry"] == {"child20_cells": 44, "dimensions": 6, "fitting_groups_per_fold": 21, "heldout_groups": 22, "items": 44, "prompt_groups": 22}
    assert contract["optimizer"]["trials_per_fold"] == 64
    assert contract["optimizer"]["version"] == calibration.OPTUNA_VERSION == "4.9.0"

    cells = child_cells()
    first = run(monkeypatch, calibration, tmp_path, cells, "first")
    second = run(monkeypatch, calibration, tmp_path, cells, "second")

    assert first == second
    assert first["input_report_sha256"] == calibration.sha256(report(cells))
    assert len(first["folds"]) == 22
    heldout = [fold["heldout_prompt_group_id"] for fold in first["folds"]]
    assert len(set(heldout)) == 22
    predicted_ids = [row["cell_id"] for fold in first["folds"] for row in fold["heldout_predictions"]]
    assert len(predicted_ids) == len(set(predicted_ids)) == 44
    assert {row["cell_id"] for row in cells} == set(predicted_ids)
    for fold in first["folds"]:
        assert fold["heldout_prompt_group_id"] not in fold["fit_prompt_group_ids"]
        assert len(fold["fit_prompt_group_ids"]) == 21
        assert all(0.1 <= values["slope"] <= 2.0 and -2.0 <= values["intercept"] <= 2.0 for values in fold["parameters"].values())

    predictions = {
        row["cell_id"]: row["scores"]
        for fold in first["folds"]
        for row in fold["heldout_predictions"]
    }
    recomputed = {
        dimension: calibration.average_tie_spearman(
            [predictions[str(cell["cell_id"])][dimension] for cell in cells],
            [cell["target"][dimension] for cell in cells],
        )
        for dimension in calibration.DIMS
    }
    assert first["out_of_fold_calibrated_child20"]["pooled_average_tie_spearman"] == recomputed


def test_heldout_target_cannot_change_its_fold_fit_and_group_metric_is_equal_weighted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calibration = load()
    baseline_cells = child_cells()
    baseline = run(monkeypatch, calibration, tmp_path, baseline_cells, "baseline")

    changed_cells = json.loads(json.dumps(baseline_cells))
    heldout_group = "group-00"
    for cell in changed_cells:
        if cell["prompt_group_id"] == heldout_group:
            for dimension in DIMS:
                cell["target"][dimension] = 5.0
    perturbed = run(monkeypatch, calibration, tmp_path, changed_cells, "perturbed")
    before = next(fold for fold in baseline["folds"] if fold["heldout_prompt_group_id"] == heldout_group)
    after = next(fold for fold in perturbed["folds"] if fold["heldout_prompt_group_id"] == heldout_group)
    assert after["parameters"] == before["parameters"]
    assert after["training_equal_group_mean_item_mae"] == before["training_equal_group_mean_item_mae"]

    def cell(cell_id: str, group: str, score: float, target: float) -> dict[str, object]:
        return {"cell_id": cell_id, "prompt_group_id": group, "target": {dimension: target for dimension in DIMS}}

    unequal = [cell("a", "one", 0.0, 0.0), *[cell(f"b-{index}", "three", 0.0, 1.0) for index in range(3)]]
    predictions = {row["cell_id"]: {dimension: 0.0 for dimension in DIMS} for row in unequal}
    metric = calibration.equal_group_mae(unequal, predictions)
    assert metric["per_group_mean_item_mae"] == {"one": 0.0, "three": 1.0}
    assert metric["equal_group_mean_item_mae"] == 0.5
    assert metric["equal_group_mean_item_mae"] != 0.75


def test_output_gates_reject_before_loading_or_fitting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calibration = load()
    args = arguments(tmp_path)
    existing_empty = tmp_path / "existing-empty"
    existing_empty.mkdir()
    destinations = [
        Path(args["v13_output_root"]).parent,
        calibration.REPO / "calibration-output-must-not-be-created",
        existing_empty,
    ]
    monkeypatch.setattr(calibration, "_load_v13", lambda: (_ for _ in ()).throw(AssertionError("source load after output gate")))
    monkeypatch.setattr(calibration, "_fit_fold", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fit after output gate")))
    for destination in destinations:
        with pytest.raises(ValueError, match="output"):
            calibration.run(**args, output_root=destination)
    assert not (calibration.REPO / "calibration-output-must-not-be-created").exists()
