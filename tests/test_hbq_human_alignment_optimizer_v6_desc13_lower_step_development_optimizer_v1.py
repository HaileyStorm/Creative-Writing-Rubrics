from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-development-optimizer-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc13_lower_step_development_optimizer", PACKAGE / "optimizer.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def projection(value):
    rows = []
    for candidate_index, candidate in enumerate(value.CANDIDATES):
        groups = {f"group-{index}": 0.1 * (candidate_index + 1) + index / 1000 for index in range(7)}
        rows.append({"candidate_id": candidate, "cells": 7, "equal_group_mae": sum(groups.values()) / 7, "group_mae": groups})
    return {"study_id": value.ANALYZER_ID, "kind": "descriptive_descendant13_lower_step_grok_development_equal_group_mae", "authority": {"selection": "grok_development_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}, "source_execution": {"candidate_manifest_sha256": "0487398345b28388fb6e35d879e5ea6f771f65802488e3fc33cf0426b530cecd", "development_schedule_sha256": "d" * 64, "executor_commit": "e" * 40, "executor_sha256": "f" * 64, "collector_sha256": "b" * 64}, "metrics": rows}


def inputs(tmp_path: Path):
    roots = {}
    for name in ("candidate_freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "output_root"):
        path = tmp_path / name; path.mkdir(); roots[name] = path
    for name in ("frozen_successor_path", "hanna_csv_path", "collector_path"):
        path = tmp_path / f"{name}.json"; path.write_bytes(b"{}\n"); roots[name] = path
    return roots


def test_only_pinned_analyzer_projection_can_feed_real_optuna_and_dspy(tmp_path, monkeypatch):
    value = module(); source = projection(value); paths = inputs(tmp_path)
    monkeypatch.setattr(value, "load_result_analyzer", lambda: SimpleNamespace(replay=lambda **kwargs: source))
    result = value.analyze(**paths)
    assert result["optimizer"]["completed_trials"] == 30
    assert result["optimizer"]["raw_mae_winner"] == value.PARENT
    assert result["optimizer"]["robustness"]["status"] == "unique_optimizer_winner"
    assert result["dspy_training_view"]["evidence_examples"] == 5
    assert result["dspy_training_view"]["lm_calls"] == result["dspy_training_view"]["predict_calls"] == 0
    assert result["authority"]["selection"] == "development_only_unique_optimizer_winner_pending_sol"
    with pytest.raises(TypeError):
        value.analyze(**paths, reference_path=tmp_path / "fabricated-references.json")


def test_projection_rejects_fabricated_route_or_aggregate_surfaces_before_ranking():
    value = module(); source = projection(value)
    with pytest.raises(ValueError, match="geometry|metric shape"):
        value._metrics({**source, "metrics": [{"candidate_id": value.PARENT, "equal_group_mae": 0.0}]})
    altered = deepcopy(source); altered["source_execution"]["candidate_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="commitments"):
        value._metrics(altered)
    mixed = deepcopy(source); mixed["metrics"][1]["group_mae"] = {f"foreign-{index}": 0.2 for index in range(7)}
    mixed["metrics"][1]["equal_group_mae"] = 0.2
    with pytest.raises(ValueError, match="mixed"):
        value._metrics(mixed)


def test_split_robustness_grid_is_not_recast_as_an_optimizer_selection():
    value = module()
    shapes = ((0.95, 0.20), (1.10, 0.20), (0.94, 0.01), (0.89, 0.20), (0.87, 0.40))
    metrics = []
    for candidate, (mean, excess) in zip(value.CANDIDATES, shapes, strict=True):
        groups = {"group-0": mean + excess, **{f"group-{group}": mean - excess / 6 for group in range(1, 7)}}
        metrics.append({"candidate_id": candidate, "equal_group_mae": sum(groups.values()) / 7, "group_mae": groups})
    result = value.run_optuna(metrics)
    assert result["robustness"]["status"] == "no_unique_optimizer_winner"
    assert "provisional_winner" not in result


def test_result_analyzer_executes_the_admitted_source_not_importer_bytecode():
    value = module()
    analyzer = value.load_result_analyzer()
    assert analyzer.STUDY_ID == value.ANALYZER_ID
    source = (PACKAGE / "optimizer.py").read_text(encoding="utf-8")
    assert "exec_module" not in source and "compile(source.raw" in source


def test_analyzer_rejection_for_fabricated_collector_non_xai_or_non_grok_propagates(tmp_path, monkeypatch):
    value = module(); paths = inputs(tmp_path)
    def reject(**_kwargs):
        raise ValueError("collector native request/response/settings/identity binding drifted")
    monkeypatch.setattr(value, "load_result_analyzer", lambda: SimpleNamespace(replay=reject))
    with pytest.raises(ValueError, match="identity binding"):
        value.analyze(**paths)


def test_cross_phase_swap_of_any_admitted_input_is_rejected(tmp_path, monkeypatch):
    value = module(); paths = inputs(tmp_path); source = projection(value)
    def swap(**_kwargs):
        paths["collector_path"].write_bytes(b'{"swapped":true}\n')
        return source
    monkeypatch.setattr(value, "load_result_analyzer", lambda: SimpleNamespace(replay=swap))
    with pytest.raises(ValueError, match="changed between analyzer"):
        value.analyze(**paths)


def test_contract_keeps_fresh96_confirmation_and_runtime_out_of_scope():
    contract = json.loads((PACKAGE / "study-contract.json").read_bytes())
    assert contract["authority"]["runtime"] == contract["authority"]["promotion"] == "none"
    assert "no Fresh96 data" in contract["prohibitions"]
    source = (PACKAGE / "optimizer.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "http" not in source


def test_claim_does_not_recast_a_robustness_tie_as_selection():
    value = module()
    claim = value.claim_for({"raw_mae_winner": "referent-resolution", "robustness": {"status": "no_unique_optimizer_winner"}})
    assert "no unique optimizer winner or selection" in claim


def test_write_result_is_write_once(tmp_path):
    value = module(); path = tmp_path / "result.json"; result = {"result": "fixture"}
    value.write_result(path, result)
    assert path.read_bytes() == value.canonical(result)
    with pytest.raises(ValueError, match="fresh"):
        value.write_result(path, result)
