"""Regression checks for QPC24's exact-head provider-free freeze."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-qpc24-exact-head-successor-v1"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _study():
    return _module("hbq_qpc24_exact_head_successor_v1", PACKAGE / "study.py")


def _verifier():
    return _module("hbq_qpc24_exact_head_successor_verifier_v1", PACKAGE / "verify_output.py")


def _controller(study, path: Path) -> Path:
    roles = []
    for role in study.ROLE_ORDER:
        text = f"Public synthetic complete work for {role}. It has an opening, development, and ending."
        source = path.parent / f"{role}.txt"
        source.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        roles.append({"role": role, "source_path": str(source), "source_sha256": digest, "qpc1_blind_id": f"synthetic-{role}", "qpc1_artifact_commitment_sha256": digest})
    payload = {"format_version": 1, "study_id": study.STUDY_ID, "source_head": study.HEAD, "bundle_id": study.BUNDLE_ID, "repetitions_per_role": 5, "provider_calls_made": 0, "whole_work_scope": study.contract()["whole_work_scope"], "roles": roles}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_provider_free_validation_reconstructs_full_qpc24_geometry(tmp_path: Path) -> None:
    study = _study()
    result = study.validate(_controller(study, tmp_path / "controller.json"))
    assert result["provider_calls"] == 0
    assert result["logical_work_evaluations"] == 15
    assert result["planned_provider_calls"] == 150
    assert result["verdict_positions"] == 3315


def test_every_logical_work_covers_all_eligible_questions_in_nine_full_batches_and_one_remainder(tmp_path: Path) -> None:
    study = _study()
    slots = study.schedule(study.controller(_controller(study, tmp_path / "controller.json")))
    assert len(slots) == 150
    for role in study.ROLE_ORDER:
        for repetition in range(1, 6):
            work = [slot for slot in slots if slot["role"] == role and slot["repetition"] == repetition]
            assert [len(slot["question_rows"]) for slot in work] == [24] * 9 + [5]
            ids = [row["question"]["id"] for slot in work for row in slot["question_rows"]]
            assert len(ids) == len(set(ids)) == 221
            assert set(study.REQUIRED_LEAVES).issubset(ids)


def test_native_renderer_exposes_true_whole_work_scope_and_never_receives_a_private_oracle(tmp_path: Path) -> None:
    study = _study()
    slot = study.schedule(study.controller(_controller(study, tmp_path / "controller.json")))[0]
    prompt = study.render_slot(slot)
    task = json.dumps(study.task_contract(slot), sort_keys=True)
    assert prompt.count('"question_id"') == 24
    assert "WHOLE_WORK: complete supplied work" in prompt
    assert '"completion_status": "complete"' in prompt
    assert "expected_state" not in task and "oracle" not in task


def test_public_projection_is_aggregate_only_and_keeps_qpc1_roles(tmp_path: Path) -> None:
    verifier = _verifier()
    assert verifier.check(PACKAGE) == []
    candidate = tmp_path / "qpc24"
    shutil.copytree(PACKAGE, candidate)
    aggregate = candidate / "qpc24-public-aggregate-plan.v1.json"
    aggregate.write_text(aggregate.read_text(encoding="utf-8").replace("Aggregate-only projection", "Aggregate-only projection with Chapter One"), encoding="utf-8")
    failures = verifier.check(candidate)
    assert "aggregate shape or commitments drifted" in failures
    assert "forbidden aggregate-only content: private prose" in failures


def test_exact_head_runtime_and_controller_commitment_are_fail_stops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    with pytest.raises(ValueError, match="source commitment drift"):
        broken = _controller(study, tmp_path / "broken.json")
        data = json.loads(broken.read_text(encoding="utf-8")); data["roles"][0]["source_sha256"] = "0" * 64
        broken.write_text(json.dumps(data), encoding="utf-8")
        study.controller(broken)
    monkeypatch.setattr(study, "HEAD", "0" * 40)
    with pytest.raises(ValueError, match="source HEAD"):
        study.verify_exact_head_and_bindings()
