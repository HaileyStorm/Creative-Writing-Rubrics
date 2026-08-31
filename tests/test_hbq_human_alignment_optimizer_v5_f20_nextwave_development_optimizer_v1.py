from __future__ import annotations

import importlib.util
import itertools
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-development-optimizer-v1"
SCORER = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1" / "executor.py"
COLLECTOR = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-score-6cfd64e-20260831a-collector.json")
SCORE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-score-6cfd64e-20260831a")
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")


def module():
    spec = importlib.util.spec_from_file_location("_hanna_nextwave_development_optimizer_test", PACKAGE / "analyzer.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_frozen_empirical_replay_runs_real_optuna_and_dspy_without_lm():
    value = module()
    result = value.analyze(
        collector_path=COLLECTOR,
        score_root=SCORE_ROOT,
        normalized_root=NORMALIZED,
        materialization_root=MATERIALIZATION,
        frozen_successor_path=FROZEN,
        hanna_csv_path=CSV,
    )
    frozen = json.loads((PACKAGE / "result.json").read_bytes())
    assert result == frozen
    assert value.validate_result_bytes((PACKAGE / "result.json").read_bytes(), result) == result
    contract, contract_sha = value.load_contract()
    assert contract == value.expected_contract()
    assert result["source"]["study_contract_file_sha256"] == contract_sha
    assert result["source"]["frozen_successor_sha256"] == value.EXPECTED["frozen_successor_sha256"]
    assert result["source"]["hanna_csv_sha256"] == value.EXPECTED["hanna_csv_sha256"]
    assert result["source"]["admitted_source_snapshot_sha256"] == value.EXPECTED["admitted_source_snapshot_sha256"]
    assert result["optimizer"]["optimizer"] == "optuna.GridSampler@4.9.0"
    assert result["optimizer"]["completed_trials"] == 198
    assert result["optimizer"]["verified_unique_grid_tuples"] == 198
    assert result["optimizer"]["candidate08_wins"] == result["optimizer"]["setting_count"] == 18
    assert result["dspy_training_view"]["library"] == "dspy@3.3.1"
    assert result["dspy_training_view"]["evidence_examples"] == 11
    assert result["dspy_training_view"]["lm_calls"] == result["dspy_training_view"]["predict_calls"] == 0
    assert result["authority"]["confirmation"] == {"status": "unopened", "cells": 0}


def test_candidate08_preference_is_contextualized_and_runtime_stays_clean():
    value = module()
    result = json.loads((PACKAGE / "result.json").read_bytes())
    assert result["finding"]["candidate08_remains_preferred_across_low_penalty_grid"] is True
    assert result["optimizer"]["outside_grid_sensitivity"]["winner"] == "normalized-nextwave-04-untouched-calibration"
    assert result["optimizer"]["outside_grid_sensitivity"]["candidate08_rank"] > 1
    assert result["finding"]["relative_mae_reduction"] == 0.19
    assert result["next_geometry"]["immediate_sol_checkpoint"]["sol_cells"] == 6
    assert result["next_geometry"]["broader_grok_iteration_after_checkpoint"]["grok_cells"] == 35
    scorer_text = SCORER.read_text(encoding="utf-8").lower()
    assert "import optuna" not in scorer_text and "import dspy" not in scorer_text
    contract = json.loads((PACKAGE / "study-contract.json").read_bytes())
    assert contract["authority"]["runtime"] == "none"
    assert contract["development"]["dspy"]["lm_calls"] == 0


def test_regularized_objective_recomputes_without_caller_aggregate_authority():
    value = module()
    result = json.loads((PACKAGE / "result.json").read_bytes())
    diagnostics = result["optimizer"]["candidate_diagnostics"]
    candidate = diagnostics["normalized-nextwave-08-conservative-hybrid"]
    assert value.regularized_score(candidate, worst_weight=0.25, loo_weight=0.25, next_step_fraction=0.10) < min(
        value.regularized_score(other, worst_weight=0.25, loo_weight=0.25, next_step_fraction=0.10)
        for candidate_id, other in diagnostics.items()
        if candidate_id != "normalized-nextwave-08-conservative-hybrid"
    )


def _trial_records(value, diagnostics):
    records = []
    for number, (candidate_id, worst, loo, step) in enumerate(
        itertools.product(sorted(diagnostics), value.WORST_WEIGHTS, value.LOO_WEIGHTS, value.NEXT_STEP_FRACTIONS)
    ):
        records.append(
            {
                "number": number,
                "params": {
                    "candidate_id": candidate_id,
                    "worst_group_weight": worst,
                    "loo_weight": loo,
                    "next_step_fraction": step,
                },
                "value": value.regularized_score(
                    diagnostics[candidate_id], worst_weight=worst, loo_weight=loo, next_step_fraction=step
                ),
            }
        )
    return records


def test_optuna_grid_rejects_duplicates_fabricated_params_and_values():
    value = module()
    diagnostics = json.loads((PACKAGE / "result.json").read_bytes())["optimizer"]["candidate_diagnostics"]
    records = _trial_records(value, diagnostics)
    verified, settings = value.verify_optuna_trial_records(records, diagnostics)
    assert len(verified) == 198 and len(settings) == 18
    duplicate = [dict(record) for record in records]
    duplicate[-1] = duplicate[0]
    with pytest.raises(ValueError, match="missing, duplicated, or fabricated"):
        value.verify_optuna_trial_records(duplicate, diagnostics)
    fabricated = [dict(record) for record in records]
    fabricated[0] = {**fabricated[0], "params": {**fabricated[0]["params"], "worst_group_weight": 0.2}}
    with pytest.raises(ValueError, match="missing, duplicated, or fabricated"):
        value.verify_optuna_trial_records(fabricated, diagnostics)
    wrong_value = [dict(record) for record in records]
    wrong_value[0] = {**wrong_value[0], "value": wrong_value[0]["value"] + 0.01}
    with pytest.raises(ValueError, match="does not independently recompute"):
        value.verify_optuna_trial_records(wrong_value, diagnostics)


def _snapshot(value, root):
    directory, members = value._admit_directory(root)
    files = {value._absolute(path): value._admit_file(path) for path in members}
    return value.SourceSnapshot(files, {directory.path: directory})


def test_admitted_snapshot_rejects_between_phase_bytes_and_identity_replacement(tmp_path):
    value = module()
    root = tmp_path / "source"
    root.mkdir()
    source = root / "candidate.json"
    source.write_bytes(b'{"value":1}')
    snapshot = _snapshot(value, root)
    assert snapshot.bytes(source) == b'{"value":1}'
    source.write_bytes(b'{"value":2}')
    with pytest.raises(ValueError, match="identity changed|identity or bytes changed"):
        snapshot.verify_unchanged()

    source.write_bytes(b'{"value":1}')
    snapshot = _snapshot(value, root)
    replacement = root / "replacement.json"
    replacement.write_bytes(b'{"value":1}')
    os.replace(replacement, source)
    with pytest.raises(ValueError, match="identity changed|identity or bytes changed"):
        snapshot.verify_unchanged()


def test_full_ancestry_reparse_is_rejected(tmp_path, monkeypatch):
    value = module()
    root = tmp_path / "source"
    root.mkdir()
    source = root / "candidate.json"
    source.write_bytes(b'{}')
    original = getattr(value.os.path, "isjunction", lambda _path: False)
    monkeypatch.setattr(value.os.path, "isjunction", lambda path: value._absolute(Path(path)) == value._absolute(root) or original(path))
    with pytest.raises(ValueError, match="reparse point"):
        value._admit_file(source)


def test_result_and_contract_reject_reformat_duplicate_fabrication_and_private_path():
    value = module()
    raw = (PACKAGE / "result.json").read_bytes()
    expected = json.loads(raw)
    assert value.validate_result_bytes(raw, expected) == expected
    with pytest.raises(ValueError, match="exact canonical"):
        value.validate_result_bytes(json.dumps(expected, indent=2).encode(), expected)
    duplicate = raw.replace(b'{"authority":', b'{"format_version":1,"format_version":1,"authority":', 1)
    with pytest.raises(ValueError, match="duplicate key"):
        value.validate_result_bytes(duplicate, expected)
    fabricated = json.loads(raw)
    fabricated["finding"]["relative_mae_reduction"] = 0.20
    with pytest.raises(ValueError, match="differs from recomputed"):
        value.validate_result_bytes(value.canonical(fabricated) + b"\n", expected)
    leaked = json.loads(raw)
    leaked["claim"] = r"C:\Users\Haile\private"
    with pytest.raises(ValueError, match="private path"):
        value.validate_result_bytes(value.canonical(leaked) + b"\n", expected)

    contract, _digest = value.load_contract()
    contract_raw = (PACKAGE / "study-contract.json").read_bytes()
    assert contract_raw == value.canonical(contract) + b"\n"
    with pytest.raises(ValueError, match="duplicate key"):
        value.parse_no_duplicates(contract_raw.replace(b'{"authority":', b'{"format_version":1,"format_version":1,"authority":', 1), "study contract")
