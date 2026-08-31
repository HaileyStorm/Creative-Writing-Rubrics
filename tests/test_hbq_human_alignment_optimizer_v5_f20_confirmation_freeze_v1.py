"""Focused provider-free coverage for the compact confirmation freeze."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-confirmation-freeze-v1"
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
GROK = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec" / "result.json"
SOL = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1" / "result.json"


def module():
    spec = importlib.util.spec_from_file_location("confirmation_freeze", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def committed_sol(study, monkeypatch, sol_path: Path):
    original = study._git_blob
    raw = sol_path.read_bytes()

    def fake_blob(actual_commit: str, relative: str) -> bytes:
        if actual_commit == study.SOL_RESULT_COMMIT and relative == study.SOL_RESULT_RELATIVE:
            return raw
        return original(actual_commit, relative)

    monkeypatch.setattr(study, "_git_blob", fake_blob)


def build(study, monkeypatch, sol_path: Path = SOL):
    if sol_path != SOL:
        committed_sol(study, monkeypatch, sol_path)
    return study.build(
        normalized_root=NORMALIZED,
        materialization_root=MATERIALIZATION,
        frozen_successor_path=FROZEN,
        hanna_csv_path=CSV,
        grok_result_path=GROK,
        grok_result_commit=study.GROK_RESULT_COMMIT,
        sol_result_path=sol_path,
        sol_result_commit=study.SOL_RESULT_COMMIT,
    )


def test_exact_real_inputs_create_the_19_item_8_group_38_cell_endpoint_neutral_schedule(monkeypatch):
    study = module()
    value = build(study, monkeypatch)
    assert value["geometry"] == {"candidates": 2, "confirmation_groups": 8, "confirmation_items": 19, "endpoint_neutral_logical_cells": 38}
    assert {row["candidate_id"] for row in value["candidates"]} == {study.BASELINE, study.SELECTED}
    assert len(value["groups"]) == 8
    assert sum(row["items"] for row in value["groups"]) == 19
    assert {row["partition"] for row in value["cells"]} == {"confirmation"}
    assert not any("route" in row for row in value["cells"])
    assert len({row["cell_id"] for row in value["cells"]}) == len({row["payload_sha256"] for row in value["cells"]}) == 38
    assert value["authority"]["provider_calls_made"] == value["authority"]["process_launches"] == 0


def test_payloads_and_targets_are_reconstructed_and_bound_without_provider_surface(monkeypatch):
    study = module()
    source_before = FROZEN.read_bytes(), CSV.read_bytes()
    value = build(study, monkeypatch)
    assert source_before == (FROZEN.read_bytes(), CSV.read_bytes())
    for row in value["cells"]:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert study.sha256(payload) == row["payload_sha256"]
        decoded = json.loads(payload)
        assert decoded["study_id"] == study.STUDY_ID
        assert study.sha256(study.canonical(decoded["response_schema"])) == row["response_schema_sha256"]
        assert set(row["target"]) == set(study.DIMENSIONS)
    source = (PACKAGE / "study.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert "def execute" not in source and "allow_remote" not in source


def test_wrong_sol_commit_is_a_hard_stop_not_a_silent_provisional_freeze():
    study = module()
    with pytest.raises(ValueError, match="Sol result commit drifted"):
        study.build(
            normalized_root=NORMALIZED,
            materialization_root=MATERIALIZATION,
            frozen_successor_path=FROZEN,
            hanna_csv_path=CSV,
            grok_result_path=GROK,
            grok_result_commit=study.GROK_RESULT_COMMIT,
            sol_result_path=SOL,
            sol_result_commit="a" * 40,
        )


def test_selection_or_sol_support_tamper_is_rejected_before_schedule_construction(monkeypatch, tmp_path: Path):
    study = module()
    bad = json.loads(SOL.read_bytes())
    bad["comparison"]["baseline_to_descendant"]["absolute_delta"] = 0.01
    sol_path = tmp_path / "sol.json"
    sol_path.write_bytes(study.canonical(bad))
    with pytest.raises(ValueError, match="result commitment"):
        build(study, monkeypatch, sol_path)


def test_freeze_root_round_trips_and_rejects_payload_or_inventory_drift(monkeypatch, tmp_path: Path):
    study = module()
    root = tmp_path / "freeze"
    value = study.freeze(
        output_root=root,
        normalized_root=NORMALIZED,
        materialization_root=MATERIALIZATION,
        frozen_successor_path=FROZEN,
        hanna_csv_path=CSV,
        grok_result_path=GROK,
        grok_result_commit=study.GROK_RESULT_COMMIT,
        sol_result_path=SOL,
        sol_result_commit=study.SOL_RESULT_COMMIT,
    )
    assert study.validate_frozen_root(root) == value
    schedule = json.loads((root / "schedule.json").read_bytes())
    schedule["cells"][0]["payload_base64"] = schedule["cells"][1]["payload_base64"]
    (root / "schedule.json").write_bytes(study.canonical(schedule))
    with pytest.raises(ValueError, match="schedule commitment"):
        study.validate_frozen_root(root)
    (root / "schedule.json").write_bytes(study.canonical(value))
    (root / "extra.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        study.validate_frozen_root(root)
