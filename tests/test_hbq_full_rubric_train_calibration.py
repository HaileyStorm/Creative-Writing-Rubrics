from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-v3-fresh88-analysis-v1" / "development_calibration.py"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module() -> Any:
    spec = importlib.util.spec_from_file_location("full_hbq_train_calibration", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def group_id(index: int) -> str:
    return "prompt-" + hashlib.sha256(f"prompt-{index:02d}".encode()).hexdigest()[:16]


def inputs(root: Path, *, heldout_target_delta: float = 0.0) -> tuple[Path, Path]:
    split_rows: list[dict[str, str]] = []
    primary_rows: list[dict[str, Any]] = []
    for index in range(48):
        group, score = group_id(index // 2), ((index * 3) % 5) / 4.0
        story = hashlib.sha256(f"story-{index:02d}".encode()).hexdigest()
        prompt = hashlib.sha256(f"prompt-{index // 2:02d}".encode()).hexdigest()
        primary_item_id = f"primary-{index:02d}"
        split_item_id = f"item-{hashlib.sha256(primary_item_id.encode()).hexdigest()[:16]}"
        split_rows.append({"item_id": split_item_id, "partition": "train", "prompt_group_id": group})
        mapping = {}
        targets = {}
        for offset, dimension in enumerate(DIMS):
            value = None if (dimension, index) in {("Coherence", 0), ("Complexity", 1)} else (score + offset / 8.0) % 1.0
            mapping[dimension] = {"score": value, "coverage": 0.5 if (index + offset) % 4 == 0 else 1.0, "unresolved": 0, "not_applicable": 0, "question_count": 5}
            targets[dimension] = 1.0 if value is None else 1.0 + 4.0 * value
            if group == group_id(0):
                targets[dimension] = min(5.0, max(1.0, targets[dimension] + heldout_target_delta))
        primary_rows.append({"item_id": primary_item_id, "story_sha256": story, "prompt_sha256": prompt, "prompt_group_id": group, "hbq_mapping": mapping, "human_means": targets})
    split_path, items_path = root / "split.json", root / "items.jsonl"
    split_path.write_bytes(canonical({"items": split_rows}))
    items_path.write_bytes(b"".join(canonical(row) for row in primary_rows))
    return items_path, split_path


def rebind(value: Any, monkeypatch: pytest.MonkeyPatch, items_path: Path, split_path: Path) -> None:
    monkeypatch.setattr(value, "ITEMS_SHA256", value.sha256(items_path.read_bytes()))
    monkeypatch.setattr(value, "SPLIT_SHA256", value.sha256(split_path.read_bytes()))
    monkeypatch.setattr(value, "contract", lambda: {"kind": "test", "authority": {"promotion": "none"}, "analysis_rule": {"development_train_only": True}, "optimizer": {"affine": {"trials_per_fold": 64}}, "geometry": {"dimensions": 6, "fitting_groups_per_fold": 23, "train_groups": 24, "train_items": 48}})


def baseline_affine(training: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
    assert len({row["prompt_group_id"] for row in training}) == 23
    return {"seed": seed, "parameters": {dimension: {"slope": 4.0, "intercept": 1.0} for dimension in DIMS}}


def flatten(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["item_id"]: row for fold in result["folds"] for row in fold["oof_predictions"]}


def test_source_pair_crosswalk_requires_hash_pins_and_exact_group_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, folder = module(), tmp_path / "base"
    folder.mkdir()
    items_path, split_path = inputs(folder)
    rebind(value, monkeypatch, items_path, split_path)
    rows = value.source_items(items_path=items_path, split_manifest=split_path)
    assert len(rows) == 48
    assert {row["item_id"] for row in rows}.isdisjoint({f"item-{hashlib.sha256(f'primary-{index:02d}'.encode()).hexdigest()[:16]}" for index in range(48)})
    assert {row["prompt_group_id"] for row in rows} == {group_id(index) for index in range(24)}

    changed = [json.loads(line) for line in items_path.read_text().splitlines()]
    changed[0]["prompt_group_id"] = "wrong-group"
    items_path.write_bytes(b"".join(canonical(row) for row in changed))
    rebind(value, monkeypatch, items_path, split_path)
    with pytest.raises(ValueError, match="identity drifted"):
        value.source_items(items_path=items_path, split_manifest=split_path)

    duplicate_folder = tmp_path / "duplicate"
    duplicate_folder.mkdir()
    items_path, split_path = inputs(duplicate_folder)
    items_path.write_bytes(items_path.read_bytes() + items_path.read_bytes().splitlines()[1] + b"\n")
    rebind(value, monkeypatch, items_path, split_path)
    with pytest.raises(ValueError, match="duplicate TRAIN item"):
        value.source_items(items_path=items_path, split_manifest=split_path)


def test_source_rejects_hash_and_partition_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, folder = module(), tmp_path / "base"
    folder.mkdir()
    items_path, split_path = inputs(folder)
    rebind(value, monkeypatch, items_path, split_path)
    items_path.write_bytes(items_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="items input pin drifted"):
        value.source_items(items_path=items_path, split_manifest=split_path)

    partition_folder = tmp_path / "partition"
    partition_folder.mkdir()
    items_path, split_path = inputs(partition_folder)
    split = json.loads(split_path.read_text())
    split["items"].pop()
    split_path.write_bytes(canonical(split))
    rebind(value, monkeypatch, items_path, split_path)
    with pytest.raises(ValueError, match="split geometry drifted"):
        value.source_items(items_path=items_path, split_manifest=split_path)


def test_run_uses_fixed_three_scaling_partial_coverage_and_loo_groups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, folder = module(), tmp_path / "inputs"
    folder.mkdir()
    items_path, split_path = inputs(folder)
    rebind(value, monkeypatch, items_path, split_path)
    seen: list[set[str]] = []

    def affine(training: list[dict[str, Any]], *, seed: int) -> dict[str, Any]:
        seen.append({row["prompt_group_id"] for row in training})
        return baseline_affine(training, seed=seed)

    monkeypatch.setattr(value, "fit_affine", affine)
    result = value.run(items_path=items_path, split_manifest=split_path, output_root=tmp_path / "output")
    assert len(result["folds"]) == len(seen) == 24
    assert all(len(groups) == 23 for groups in seen)
    assert all(fold["heldout_prompt_group_id"] not in fold["fit_prompt_group_ids"] for fold in result["folds"])
    assert (tmp_path / "output" / "result.json").read_bytes() == value.canonical(result)
    rows = flatten(result)
    assert len(rows) == 48
    for row in rows.values():
        for dimension in DIMS:
            score, prediction = row["scores"][dimension], row["predictions"]["diagnostic_1_plus_4p"][dimension]
            assert prediction == (3.0 if score is None else 1.0 + 4.0 * score)
            if score is None:
                assert {row["predictions"][arm][dimension] for arm in result["arms"]} == {3.0}
    assert result["coverage_and_missing_counts"]["Relevance"]["partial_coverage"] > 0
    assert result["coverage_and_missing_counts"]["Coherence"]["missing_mapped_score"] == 1
    assert result["arms"]["diagnostic_1_plus_4p"]["equal_group_mean_item_mae"] == pytest.approx(1.0 / 72.0)


def test_held_group_targets_cannot_change_its_oof_predictions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = module()
    first_folder, changed_folder = tmp_path / "first", tmp_path / "changed"
    first_folder.mkdir(); changed_folder.mkdir()
    items_path, split_path = inputs(first_folder)
    rebind(value, monkeypatch, items_path, split_path)
    monkeypatch.setattr(value, "fit_affine", baseline_affine)
    first = value.run(items_path=items_path, split_manifest=split_path, output_root=tmp_path / "first-output")
    changed_items, changed_split = inputs(changed_folder, heldout_target_delta=2.0)
    rebind(value, monkeypatch, changed_items, changed_split)
    second = value.run(items_path=changed_items, split_manifest=changed_split, output_root=tmp_path / "changed-output")
    first_rows, second_rows = flatten(first), flatten(second)
    held = {item_id for item_id, row in first_rows.items() if row["prompt_group_id"] == group_id(0)}
    assert held
    assert {item_id: first_rows[item_id]["predictions"] for item_id in held} == {item_id: second_rows[item_id]["predictions"] for item_id in held}


def test_equal_group_mae_weights_prompt_groups_equally() -> None:
    value = module()
    cells = [{"item_id": "small", "prompt_group_id": "small", "scores": {dimension: 0.5 for dimension in DIMS}, "target": {dimension: 1.0 for dimension in DIMS}}]
    cells.extend({"item_id": f"large-{index}", "prompt_group_id": "large", "scores": {dimension: 0.5 for dimension in DIMS}, "target": {dimension: 1.0 for dimension in DIMS}} for index in range(9))
    predictions = {"small": {dimension: 3.0 for dimension in DIMS}}
    predictions.update({f"large-{index}": {dimension: 1.0 for dimension in DIMS} for index in range(9)})
    metrics = value.equal_group_mae(cells, predictions)
    assert metrics["per_group_mean_item_mae"] == {"large": 0.0, "small": 2.0}
    assert metrics["equal_group_mean_item_mae"] == pytest.approx(1.0)


def test_fit_affine_uses_deterministic_frozen_tpe_bounds(monkeypatch: pytest.MonkeyPatch) -> None:
    value = module()
    cells = [{"item_id": f"item-{index}", "prompt_group_id": f"group-{index:02d}", "scores": {dimension: 0.5 for dimension in DIMS}, "target": {dimension: 3.0 for dimension in DIMS}} for index in range(23)]
    calls: dict[str, Any] = {}

    class Trial:
        def __init__(self) -> None:
            self.params: dict[str, float] = {}

        def suggest_float(self, name: str, low: float, high: float) -> float:
            calls.setdefault("bounds", []).append((name, low, high))
            value = (low + high) / 2.0
            self.params[name] = value
            return value

    class Study:
        def __init__(self) -> None:
            self.trials: list[object] = []
            self.best_trial = Trial()

        def optimize(self, objective: Any, *, n_trials: int, n_jobs: int, catch: tuple[()]) -> None:
            calls.update({"trials": n_trials, "jobs": n_jobs})
            self.best_trial = Trial()
            objective(self.best_trial)
            self.trials = [object()] * n_trials
            self.best_trial.number = 0

    def create_study(*, direction: str, sampler: Any) -> Study:
        calls.update({"direction": direction, "seed": sampler.seed})
        return Study()

    class Sampler:
        def __init__(self, *, seed: int):
            self.seed = seed

    fake = SimpleNamespace(__version__=value.OPTUNA_VERSION, create_study=create_study, samplers=SimpleNamespace(TPESampler=Sampler))
    monkeypatch.setitem(sys.modules, "optuna", fake)
    fit = value.fit_affine(cells, seed=123)
    assert calls["direction"] == "minimize" and calls["seed"] == 123
    assert calls["trials"] == 64 and calls["jobs"] == 1
    assert {bounds[1:] for bounds in calls["bounds"]} == {(0.0, 8.0), (-2.0, 4.0)}
    assert all(0.0 <= row["slope"] <= 8.0 and -2.0 <= row["intercept"] <= 4.0 for row in fit["parameters"].values())


def test_ridge_is_deterministic_and_uses_per_dimension_usable_group_weights() -> None:
    value = module()
    cells = []
    for group in range(23):
        for row in range(2):
            scores = {dimension: 0.25 + ((group + row + offset) % 3) / 4.0 for offset, dimension in enumerate(DIMS)}
            if group == 0 and row == 1:
                scores["Coherence"] = None
            cells.append({"item_id": f"{group}-{row}", "prompt_group_id": f"group-{group:02d}", "scores": scores, "target": {dimension: min(5.0, 1.2 + 3.5 * (score if score is not None else 0.5)) for dimension, score in scores.items()}})
    first, second = value.fit_ridge(cells), value.fit_ridge(cells)
    without_missing_row = [cell for cell in cells if cell["item_id"] != "0-1"]
    reference = value.fit_ridge(without_missing_row)
    assert first == second
    assert first["alpha"] == 1.0 and first["group_weighting"] == "inverse_usable_group_item_count"
    assert first["coefficients"]["Coherence"]["fitted_items"] == 45
    coherence, reference_coherence = first["coefficients"]["Coherence"], reference["coefficients"]["Coherence"]
    assert coherence["intercept"] == pytest.approx(reference_coherence["intercept"])
    assert coherence["deltas"] == pytest.approx(reference_coherence["deltas"])
    assert all(math.isfinite(number) for coefficient in first["coefficients"].values() for number in [coefficient["intercept"], *coefficient["deltas"].values()])


def test_run_rejects_nonfresh_and_input_overlapping_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, folder = module(), tmp_path / "inputs"
    folder.mkdir()
    items_path, split_path = inputs(folder)
    rebind(value, monkeypatch, items_path, split_path)
    monkeypatch.setattr(value, "fit_affine", baseline_affine)
    output = tmp_path / "output"
    value.run(items_path=items_path, split_manifest=split_path, output_root=output)
    with pytest.raises(ValueError, match="fresh"):
        value.run(items_path=items_path, split_manifest=split_path, output_root=output)
    with pytest.raises(ValueError, match="overlaps immutable input"):
        value.run(items_path=items_path, split_manifest=split_path, output_root=folder / "nested-output")
