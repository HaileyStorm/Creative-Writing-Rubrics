from __future__ import annotations

import base64
import builtins
import json
import shutil
from pathlib import Path

import pytest
from _scoped_module_loader import load_module

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-shrinkage-eval-v1"
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-reconcile-v1-52dc2157-e0b5c104\reconciliation-manifest.json")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
analyze = load_module(PACKAGE / "analyze.py", name="hanna_shrinkage_analyze")
study = analyze._study()
development_optuna = load_module(PACKAGE / "development_optuna.py", name="hanna_shrinkage_optuna")


@pytest.fixture(scope="module")
def validated_schedule():
    return study.prepare_grok_schedule(reconciliation_manifest_path=RECONCILIATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def _metrics(validated, winner_values=(0.80, 0.85, 0.90)) -> list[dict]:
    schedule = validated.value; winner = schedule["candidates"][1]["candidate_id"]
    group_index = {row["prompt_group_id"]: index for index, row in enumerate(schedule["groups"])}; rows = []
    for cell in schedule["cells"]:
        if cell["candidate_id"] == study.BASELINE_ID: value = 1.0
        elif cell["candidate_id"] == winner: value = winner_values[group_index[cell["prompt_group_id"]]]
        else: value = 1.30
        rows.append({"cell_id": cell["cell_id"], "candidate_id": cell["candidate_id"], "prompt_group_id": cell["prompt_group_id"], "mean_absolute_error": value})
    return rows


def test_real_r4_feedback_reconciliation_admission_and_exact_geometry(validated_schedule):
    schedule = validated_schedule.value
    assert schedule["geometry"] == {"candidates": 11, "groups": 3, "grok_cells": 33, "sol_cells": 0}
    assert [(row["prompt_group_id"], row["item_id"]) for row in schedule["groups"]] == list(study.UNUSED_DEVELOPMENT_GROUPS)
    assert schedule["feedback"]["claim"] == "no_independently_observed_heldout_gain"
    assert schedule["reconciliation_manifest_file_sha256"] == "26b91ea23f04b55909db775b75c1bf7ae2d4819d2acc8346244548296e229bf3"
    descendants = schedule["candidates"][1:]
    assert len({row["declared_mechanism"] for row in descendants}) == 10
    assert all(row["semantic_single_mechanism_verified"] is False for row in descendants)
    assert schedule["confirmation"] == {"status": "unopened", "cells": 0}


def test_objective_grid_folds_boundary_and_zero_sol_stop(validated_schedule):
    frozen = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=_metrics(validated_schedule))
    winner = validated_schedule.value["candidates"][1]["candidate_id"]
    assert frozen.decision["selected_candidate_id"] == winner and frozen.decision["gate"]["same_candidate_fold_wins"] == 3
    scores = {row["candidate_id"]: row["j"] for row in frozen.decision["scores"]}
    replay = development_optuna.grid_replay(scores)
    assert len(replay) == 11 and min(replay, key=lambda row: (row["value"], row["candidate_id"]))["candidate_id"] == winner
    boundary = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=_metrics(validated_schedule, (0.60, 0.60, 1.10)))
    assert boundary.decision["action"] == "advance_to_sol" and boundary.decision["gate"]["maximum_group_worsening"] == pytest.approx(0.10)
    stopped = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=_metrics(validated_schedule, (0.60, 0.60, 1.15)))
    sol = analyze.build_sol_schedule(frozen=stopped)
    assert stopped.decision["action"] == "baseline_stop" and sol.value["cells"] == []
    assert analyze.validate_sol(frozen=stopped, sol_schedule=sol, projected_group_metrics=[])["action"] == "baseline_stop"


def test_sol_stage_is_exact_four_cells_with_unchanged_bytes(validated_schedule):
    frozen = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=_metrics(validated_schedule))
    sol = analyze.build_sol_schedule(frozen=frozen); schedule = validated_schedule.value
    assert sol.value["geometry"] == {"candidates": 2, "groups": 2, "sol_cells": 4}
    assert sol.value["candidate_order"] == [study.BASELINE_ID, frozen.decision["selected_candidate_id"]]
    grok = {(row["item_id"], row["candidate_id"]): row for row in schedule["cells"]}
    assert all(study.payload_bytes(row) == study.payload_bytes(grok[(row["item_id"], row["candidate_id"])]) for row in sol.value["cells"])
    values = {study.BASELINE_ID: (1.0, 1.0), frozen.decision["selected_candidate_id"]: (0.95, 1.0)}
    group_index = {row["prompt_group_id"]: index for index, row in enumerate(sol.value["groups"])}
    metrics = [{"cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "prompt_group_id": row["prompt_group_id"], "mean_absolute_error": values[row["candidate_id"]][group_index[row["prompt_group_id"]]]} for row in sol.value["cells"]]
    result = analyze.validate_sol(frozen=frozen, sol_schedule=sol, projected_group_metrics=metrics)
    assert result["passed"] is True and result["sol_cannot_substitute"] is True


def test_arbitrary_decision_mint_and_sol_token_substitution_are_rejected(validated_schedule):
    metrics = _metrics(validated_schedule); genuine = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=metrics)
    decision = json.loads(genuine._decision_bytes); decision["selected_candidate_id"] = study.BASELINE_ID; decision["action"] = "baseline_stop"
    body = {key: value for key, value in decision.items() if key != "decision_sha256"}; decision["decision_sha256"] = study.sha256(body)
    forged = analyze.FrozenGrokDecision(decision, study.canonical(decision), genuine._metrics_bytes, genuine._schedule, analyze._FROZEN_TOKEN)
    with pytest.raises(ValueError, match="decision or evidence drifted"): analyze.build_sol_schedule(frozen=forged)
    sol = analyze.build_sol_schedule(frozen=genuine)
    other = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=_metrics(validated_schedule, (0.70, 0.75, 0.80)))
    substituted = analyze.ValidatedSolSchedule(sol.value, sol._bytes, other, analyze._SOL_TOKEN)
    with pytest.raises(ValueError, match="token/bytes/frozen binding"): analyze.validate_sol(frozen=genuine, sol_schedule=substituted, projected_group_metrics=[])


def test_caller_rehashed_edit_mass_cannot_flip_winner(validated_schedule):
    forged_value = json.loads(study.canonical(validated_schedule.value))
    forged_value["candidates"][1]["edit_mass"] = 1.0
    body = {key: value for key, value in forged_value.items() if key != "schedule_sha256"}; forged_value["schedule_sha256"] = study.sha256(body)
    raw = study.canonical(forged_value)
    forged = study.ValidatedSchedule(forged_value, raw, validated_schedule._candidate_bytes, validated_schedule._inputs, study._SCHEDULE_TOKEN)
    with pytest.raises(ValueError, match="full schedule/candidate/cell replay drifted"):
        analyze.select_grok(validated_schedule=forged, projected_group_metrics=_metrics(validated_schedule))
    genuine = analyze.select_grok(validated_schedule=validated_schedule, projected_group_metrics=_metrics(validated_schedule))
    score = next(row for row in genuine.decision["scores"] if row["candidate_id"] == validated_schedule.value["candidates"][1]["candidate_id"])
    assert score["edit_mass"] == pytest.approx(study._validated_schedule(validated_schedule)[0]["candidates"][1]["edit_mass"])


@pytest.mark.parametrize("mutation", ["payload", "cell", "group", "geometry"])
def test_real_token_rejects_rehashed_full_schedule_forgery(validated_schedule, mutation: str):
    forged_value = json.loads(study.canonical(validated_schedule.value))
    if mutation == "payload":
        raw = b"forged-payload"
        forged_value["cells"][0]["payload_base64"] = base64.b64encode(raw).decode("ascii")
        forged_value["cells"][0]["payload_sha256"] = study.sha256(raw)
    elif mutation == "cell":
        forged_value["cells"][0]["cell_id"] = "shrinkage-cell-0000000000000000"
    elif mutation == "group":
        forged_value["groups"][0]["item_id"] = "item-forged"
    else:
        forged_value["geometry"]["grok_cells"] = 32
    body = {key: value for key, value in forged_value.items() if key != "schedule_sha256"}
    forged_value["schedule_sha256"] = study.sha256(body)
    raw = study.canonical(forged_value)
    forged = study.ValidatedSchedule(forged_value, raw, validated_schedule._candidate_bytes, validated_schedule._inputs, study._SCHEDULE_TOKEN)
    with pytest.raises(ValueError, match="full schedule/candidate/cell replay drifted"):
        study._validated_schedule(forged)


def test_fake_feedback_hashes_are_rejected_before_candidate_replay(tmp_path: Path):
    for name in study.PUBLIC_ARTIFACT_SHA256: shutil.copy2(study.PUBLIC_RESULT_ROOT / name, tmp_path / name)
    value = json.loads((tmp_path / "public-result.json").read_bytes()); value["artifacts"]["grok_selection"]["sha256"] = "0" * 64
    (tmp_path / "public-result.json").write_bytes(study.canonical(value))
    with pytest.raises(ValueError, match="feedback public-result.json hash"): study._feedback(tmp_path)


def test_runtime_modules_do_not_import_dspy_or_optuna(monkeypatch: pytest.MonkeyPatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}: raise AssertionError("development optimizer imported at runtime")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    load_module(PACKAGE / "study.py", name="hanna_shrinkage_runtime_study")
    load_module(PACKAGE / "analyze.py", name="hanna_shrinkage_runtime_analyze")
