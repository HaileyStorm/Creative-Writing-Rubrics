from __future__ import annotations

import importlib.util
import gzip
import hashlib
import json
import sys
from pathlib import Path

import pytest

from hbqrs import core, runner

from _run_verify_fixture import build_fixture, write_json

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-human-alignment-v3-successor-v1"
spec = importlib.util.spec_from_file_location("fresh88_study", ROOT / "study.py")
assert spec and spec.loader
study = importlib.util.module_from_spec(spec); sys.modules["fresh88_study"] = study; spec.loader.exec_module(study)

def plan() -> dict:
    return {"base_frozen": {}, "cells": [{"item_id":f"item-{i}","origin":"fresh_full_successor","ordinal":i + 1,"run_dir":f"runs/{i}","artifact":{},"contexts":[],"task_contract":{}} for i in range(88)]}

def result(i: int, session: str | None = None) -> dict:
    return {"run_sha256": f"{i:064x}", "sessions": [{"session_id_sha256": session or f"{i + 1000:064x}"}], "commitments": {"verdicts":"0" * 64}}

def wire(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, duplicate: bool = False) -> None:
    monkeypatch.setattr(study, "load_execution_contract", lambda *_: plan())
    def verify(cell, base, root):
        index = int(Path(cell["run_dir"]).name); return {"run_dir": cell["run_dir"], "result": result(index, "a" * 64 if duplicate else None), "metrics": {"score": .5, "confidence": .8, "calibration": {"status":"UNAVAILABLE"}}}
    monkeypatch.setattr(study, "_verify_cell", verify)
    (tmp_path / "fresh88-execution-contract.json").write_text("{}", encoding="utf-8")
    if not (tmp_path / study.RECEIPT_NAME).exists(): study.freeze_execution_contract(tmp_path, tmp_path)
    for i in range(88):
        directory = tmp_path / "runs" / str(i); directory.mkdir(parents=True, exist_ok=True); (directory / "score.v2.json").write_text(json.dumps({"score": 0.5}), encoding="utf-8")

def test_contract_disables_verified54_and_pins_rejected_fresh88():
    assert study.CONTRACT["verified54"]["status"] == "DISABLED"
    assert study.CONTRACT["fresh88_authority"] == study.AUTHORITY_PIN

def test_exact_88_matrix_is_raw_verifier_derived_and_atomic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    wire(monkeypatch, tmp_path); matrix = study.verify_matrix(tmp_path, tmp_path, tmp_path)
    assert len(matrix["records"]) == matrix["session_count"] == 88
    assert matrix["matrix_sha256"] and study.read_json(tmp_path / study.MATRIX_NAME) == matrix
    assert study.diagnostics(matrix)["calibration"]["status"] == "UNAVAILABLE"

def test_session_reuse_and_reseal_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    wire(monkeypatch, tmp_path, duplicate=True)
    with pytest.raises(ValueError, match="unique"): study.verify_matrix(tmp_path, tmp_path, tmp_path)
    wire(monkeypatch, tmp_path); matrix = study.verify_matrix(tmp_path, tmp_path, tmp_path)
    matrix["session_count"] = 1
    (tmp_path / study.MATRIX_NAME).write_text(json.dumps(matrix), encoding="utf-8")
    with pytest.raises(ValueError, match="Immutable artifact"): study.verify_matrix(tmp_path, tmp_path, tmp_path)

def test_execution_plan_rejects_item_order_and_absolute_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    authority = {"fresh_complement": {"scheduled_item_ids": [f"i{i}" for i in range(88)]}}
    monkeypatch.setattr(study, "load_authority", lambda _: authority)
    base = {"registry": {"path":str(tmp_path / "x"),"bytes":0,"sha256":"0"*64}, "bundles": {"path":str(tmp_path / "x"),"bytes":0,"sha256":"0"*64}, "prompts": [], "response_schema": {"path":str(tmp_path / "x"),"bytes":0,"sha256":"0"*64}, "weight_profile":{}, "execution":{}, "provider":{}}
    bad = {"format_version":1,"study_id":study.CONTRACT["study_id"],"authority_contract_sha256":study.AUTHORITY_PIN["frozen_successor_sha256"],"origin":"fresh_full_successor","phase":"development","base_frozen":base,"cells":[]}
    (tmp_path / "fresh88-execution-contract.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="binding drifted|Prompt bindings|requires exactly 88"): study.load_execution_contract(tmp_path, tmp_path)


def _cell(item_id: str, run_dir: Path, frozen: dict) -> tuple[dict, dict]:
    base = dict(frozen)
    execution = dict(base["execution"])
    execution["artifact_id"] = "template-artifact"
    base["execution"] = execution
    return ({"item_id": item_id, "run_dir": f"runs/{run_dir.name}", "artifact": frozen["artifact"],
             "contexts": frozen["contexts"], "task_contract": frozen["task_contract"]}, base)


def _rechain(run: Path, first: int) -> None:
    previous = hashlib.sha256((run / "responses" / f"batch-{first:04d}.json").read_bytes()).hexdigest()
    for batch in range(first + 1, 7):
        path = run / "responses" / f"batch-{batch:04d}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["previous_checkpoint_sha256"] = previous
        write_json(path, record)
        previous = hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_genuine_v4_runs_verify_through_successor_cells(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    first, first_frozen = build_fixture(tmp_path / "first", artifact_id="fresh-1", provider_session_prefix="fresh-one", run_dir=artifact_root / "runs" / "one")
    second, second_frozen = build_fixture(tmp_path / "second", artifact_id="fresh-2", provider_session_prefix="fresh-two", run_dir=artifact_root / "runs" / "two")
    first_cell, first_base = _cell("fresh-1", first, first_frozen)
    second_cell, second_base = _cell("fresh-2", second, second_frozen)
    first_verified = study._verify_cell(first_cell, first_base, artifact_root)
    second_verified = study._verify_cell(second_cell, second_base, artifact_root)
    first_sessions = {entry["session_id_sha256"] for entry in first_verified["result"]["sessions"]}
    second_sessions = {entry["session_id_sha256"] for entry in second_verified["result"]["sessions"]}
    assert first_sessions.isdisjoint(second_sessions)
    assert first_verified["result"]["commitments"]["verdicts"]["path"] == "verdicts.jsonl"
    assert first_verified["metrics"]["calibration"]["status"] == "UNAVAILABLE"
    assert second_verified["result"]["verdict_count"] == 179


@pytest.mark.parametrize("tamper", ["response", "prompt", "input", "item", "session", "score"])
def test_successor_cell_rejects_raw_artifact_tampering(tmp_path: Path, tamper: str) -> None:
    artifact_root = tmp_path / "artifacts"
    run, frozen = build_fixture(tmp_path / "fixture", artifact_id="fresh-tamper", provider_session_prefix="fresh", run_dir=artifact_root / "runs" / "tamper")
    cell, base = _cell("fresh-tamper", run, frozen)
    if tamper == "response":
        (run / "responses" / "batch-0001.accepted-0001.message.txt").write_text("{}", encoding="utf-8")
    elif tamper == "prompt":
        (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"forged", mtime=0))
    elif tamper == "input":
        Path(cell["artifact"]["path"]).write_text("forged source", encoding="utf-8")
    elif tamper == "item":
        cell["item_id"] = "forged-item"
    elif tamper == "session":
        path = run / "responses" / "batch-0001.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["provider"]["reported"]["session_id"] = " "
        write_json(path, record)
        _rechain(run, 1)
    else:
        path = run / "score.json"
        score = json.loads(path.read_text(encoding="utf-8"))
        score["status"] = "forged"
        write_json(path, score)
    with pytest.raises((core.HBQError, ValueError)):
        study._verify_cell(cell, base, artifact_root)


def test_canonical_run_path_receipt_and_phase_requirements(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert study._under(tmp_path, "runs/cell").as_posix().endswith("/runs/cell")
    with pytest.raises(ValueError, match="canonical"):
        study._under(tmp_path, "cells/cell")
    with pytest.raises(ValueError, match="canonical"):
        study._under(tmp_path, "runs/a/b")
    (tmp_path / "fresh88-execution-contract.json").write_text("{}", encoding="utf-8")
    receipt = study.freeze_execution_contract(tmp_path, tmp_path)
    assert receipt["purpose"] == "pre_execution_raw_verifier_binding"
    matrix = {"matrix_sha256": "a" * 64, "execution_receipt_sha256": "b" * 64, "records": []}
    monkeypatch.setattr(study, "verify_matrix", lambda *_: matrix)
    (tmp_path / "semantic-development-gate.json").write_text(json.dumps({"study_id": study.CONTRACT["study_id"], "phase": "semantic_development_gate", "development_mode": "fresh_88", "matrix_sha256": "a" * 64, "diagnostics": {}, "next_phase": "repeatability"}), encoding="utf-8")
    with pytest.raises(ValueError): study.permit_phase(tmp_path, "development", tmp_path, tmp_path)
    with pytest.raises(ValueError, match="Distinct raw-run"):
        study.permit_phase(tmp_path, "repeatability", tmp_path, tmp_path)
    with pytest.raises(ValueError, match="Distinct raw-run"):
        study.permit_phase(tmp_path, "confirmatory", tmp_path, tmp_path)
