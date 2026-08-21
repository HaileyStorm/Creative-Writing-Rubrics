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


def _load_runner_module(name: str):
    sys.modules["study"] = study
    module_spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    module_spec.loader.exec_module(module)
    return module


prepare_fresh = _load_runner_module("prepare_fresh")
run_fresh = _load_runner_module("run_fresh")

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


def test_matrix_rejects_duplicate_cells_and_extra_raw_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    wire(monkeypatch, tmp_path)
    duplicate = plan()
    duplicate["cells"][1]["run_dir"] = duplicate["cells"][0]["run_dir"]
    monkeypatch.setattr(study, "load_execution_contract", lambda *_: duplicate)
    with pytest.raises(ValueError, match="Duplicate"):
        study.verify_matrix(tmp_path, tmp_path, tmp_path)
    wire(monkeypatch, tmp_path)
    (tmp_path / "runs" / "extra").mkdir()
    with pytest.raises(ValueError, match="missing or extra"):
        study.verify_matrix(tmp_path, tmp_path, tmp_path)

def test_execution_plan_rejects_item_order_and_absolute_layout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    authority = {"fresh_complement": {"scheduled_item_ids": [f"i{i}" for i in range(88)]}}
    monkeypatch.setattr(study, "load_authority", lambda _: authority)
    base = {"registry": {"path":str(tmp_path / "x"),"bytes":0,"sha256":"0"*64}, "bundles": {"path":str(tmp_path / "x"),"bytes":0,"sha256":"0"*64}, "prompts": [], "response_schema": {"path":str(tmp_path / "x"),"bytes":0,"sha256":"0"*64}, "weight_profile":{}, "execution":{}, "provider":{}}
    bad = {"format_version":1,"study_id":study.CONTRACT["study_id"],"authority_contract_sha256":study.AUTHORITY_PIN["frozen_successor_sha256"],"origin":"fresh_full_successor","phase":"development","base_frozen":base,"cells":[]}
    (tmp_path / "fresh88-execution-contract.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="base contract keys|binding drifted|Prompt bindings|requires exactly 88"): study.load_execution_contract(tmp_path, tmp_path)


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


def _external(path: Path) -> dict[str, object]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _fresh88_inputs(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path / "inputs"
    ids = [f"fresh-{index:03d}" for index in range(1, 89)]
    rows = []
    for item_id in ids:
        directory = root / "development" / item_id
        directory.mkdir(parents=True)
        source, prompt, task = directory / "source.md", directory / "prompt.md", directory / "task-contract.json"
        source.write_text(f"The lantern for {item_id} flickered at dawn.", encoding="utf-8")
        prompt.write_text("Write a tense short story about a lantern.", encoding="utf-8")
        write_json(task, {
            "contract_version": 1, "contract_id": f"contract-{item_id}", "artifact_id": item_id,
            "context": {"artifact_kind": "short prose fiction", "declared_scope": "complete short story",
                        "completion_status": "complete", "background": [], "constraints": [], "audience": []},
            "preferences": [], "priorities": [],
            "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story respond to its originating prompt?",
                                "weight": 2.0, "source": {"kind": "driving_prompt", "reference": "fixture prompt",
                                "exact_excerpt": "Write a tense short story about a lantern."}, "applies_to": ["whole artifact"],
                                "rationale": "Fixture task relevance."}], "binding_requirements": [],
        })
        rows.append({"item_id": item_id, "external_input": {"source.md": _external(source), "prompt.md": _external(prompt),
                     "task-contract.json": _external(task)}})
    return root, {"fresh_complement": {"scheduled_item_ids": ids}, "selection": {"development": rows}}


def test_prepare_seals_authoritative_88_contract_and_receipt_before_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs, authority = _fresh88_inputs(tmp_path)
    work, artifacts = tmp_path / "work", tmp_path / "artifacts"
    monkeypatch.setattr(prepare_fresh, "load_authority", lambda _: authority)
    dry = prepare_fresh.prepare(tmp_path / "authority", inputs, work, artifacts, dry_run=True)
    assert dry["cells"] == 88 and not (work / "fresh88-execution-contract.json").exists()
    sealed = prepare_fresh.prepare(tmp_path / "authority", inputs, work, artifacts)
    assert sealed["cells"] == 88
    assert (work / "fresh88-execution-contract.json").is_file()
    assert (work / study.RECEIPT_NAME).is_file()
    assert not (artifacts / "runs").exists()
    artifacts.joinpath("runs", "existing").mkdir(parents=True)
    with pytest.raises(ValueError, match="empty work|before any raw run"):
        prepare_fresh.prepare(tmp_path / "authority", inputs, tmp_path / "later", artifacts)


def test_prepare_rejects_authoritative_input_hash_drift_and_receipt_after_runs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs, authority = _fresh88_inputs(tmp_path)
    monkeypatch.setattr(prepare_fresh, "load_authority", lambda _: authority)
    (inputs / "development" / "fresh-001" / "source.md").write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="input drifted"):
        prepare_fresh.prepare(tmp_path / "authority", inputs, tmp_path / "work", tmp_path / "artifacts")
    work, artifacts = tmp_path / "receipt-work", tmp_path / "receipt-artifacts"
    work.mkdir(); (work / "fresh88-execution-contract.json").write_text("{}", encoding="utf-8")
    artifacts.joinpath("runs", "already").mkdir(parents=True)
    with pytest.raises(ValueError, match="before raw runs"):
        study.freeze_execution_contract(work, artifacts)


def test_execution_contract_recomputes_exact_canonical_bindings_and_runtime_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs, authority = _fresh88_inputs(tmp_path)
    work, artifacts = tmp_path / "work", tmp_path / "artifacts"
    monkeypatch.setattr(prepare_fresh, "load_authority", lambda _: authority)
    prepare_fresh.prepare(tmp_path / "authority", inputs, work, artifacts)
    monkeypatch.setattr(study, "load_authority", lambda _: authority)
    contract = work / "fresh88-execution-contract.json"
    original = json.loads(contract.read_text(encoding="utf-8"))
    assert set(original["base_frozen"]) == {"registry", "bundles", "prompts", "response_schema", "score_v1_schema", "score_v2_schema", "verdict_schema", "task_contract_schema", "weight_profile", "execution", "provider", "runtime_manifest"}
    alternate = tmp_path / "same-registry.json"
    alternate.write_bytes(Path(original["base_frozen"]["registry"]["path"]).read_bytes())
    changed = json.loads(json.dumps(original)); changed["base_frozen"]["registry"]["path"] = str(alternate.resolve())
    write_json(contract, changed)
    with pytest.raises(ValueError, match="Canonical registry"):
        study.load_execution_contract(work, tmp_path / "authority")
    changed = json.loads(json.dumps(original)); one_path, one_binding = next(iter(changed["base_frozen"]["runtime_manifest"]["files"].items()))
    changed["base_frozen"]["runtime_manifest"]["files"] = {one_path: one_binding}
    changed["base_frozen"]["runtime_manifest"]["sha256"] = hashlib.sha256(study.canonical(changed["base_frozen"]["runtime_manifest"]["files"])).hexdigest()
    write_json(contract, changed)
    with pytest.raises(ValueError, match="Runtime source manifest"):
        study.load_execution_contract(work, tmp_path / "authority")
    changed = json.loads(json.dumps(original)); changed["base_frozen"].pop("verdict_schema")
    write_json(contract, changed)
    with pytest.raises(ValueError, match="base contract keys"):
        study.load_execution_contract(work, tmp_path / "authority")
    changed = json.loads(json.dumps(original)); changed["base_frozen"]["extra"] = None
    write_json(contract, changed)
    with pytest.raises(ValueError, match="base contract keys"):
        study.load_execution_contract(work, tmp_path / "authority")


def test_run_dry_run_uses_sealed_plan_without_provider_calls(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs, authority = _fresh88_inputs(tmp_path)
    work, artifacts = tmp_path / "work", tmp_path / "artifacts"
    monkeypatch.setattr(prepare_fresh, "load_authority", lambda _: authority)
    prepare_fresh.prepare(tmp_path / "authority", inputs, work, artifacts)
    monkeypatch.setattr(study, "load_authority", lambda _: authority)
    calls: list[dict] = []
    monkeypatch.setattr(run_fresh, "run_judge", lambda **kwargs: calls.append(kwargs))
    assert run_fresh.run(tmp_path / "authority", work, artifacts, dry_run=True) == {"cells": 88, "provider_calls": 0}
    assert calls == []


def test_run_invokes_exact_sol_contract_resumes_and_gates_after_provider_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inputs, authority = _fresh88_inputs(tmp_path)
    work, artifacts = tmp_path / "work", tmp_path / "artifacts"
    monkeypatch.setattr(prepare_fresh, "load_authority", lambda _: authority)
    prepare_fresh.prepare(tmp_path / "authority", inputs, work, artifacts)
    monkeypatch.setattr(study, "load_authority", lambda _: authority)
    calls: list[dict] = []

    def provider_boundary(**kwargs):
        calls.append(kwargs)
        ordinal = len(calls)
        if ordinal <= 2:
            build_fixture(tmp_path / f"genuine-{ordinal}", artifact_id=kwargs["artifact_id"],
                          provider_session_prefix=f"provider-{ordinal}", run_dir=Path(kwargs["output_dir"]),
                          input_paths=(Path(kwargs["artifact_path"]), Path(kwargs["context_paths"][0]), Path(kwargs["task_contract_path"])))
        else:
            Path(kwargs["output_dir"]).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(run_fresh, "run_judge", provider_boundary)
    def verify_first_two(work_path: Path, authority_path: Path, artifact_path: Path) -> dict:
        plan = study.load_execution_contract(work_path, authority_path)
        verified = study.verify_cells(plan["cells"][:2], plan["base_frozen"], artifact_path)
        assert len(verified["records"]) == 2 and verified["session_count"] == 12
        return {"matrix_sha256": "m" * 64}
    monkeypatch.setattr(run_fresh, "verify_matrix", verify_first_two)
    monkeypatch.setattr(run_fresh, "create_development_gate", lambda *_: {"phase": "semantic_development_gate"})
    result = run_fresh.run(tmp_path / "authority", work, artifacts)
    assert result == {"matrix": "m" * 64, "gate": {"phase": "semantic_development_gate"}}
    assert len(calls) == 88
    first, second = calls[:2]
    assert first["output_dir"] == artifacts / "runs" / "fresh-001" and first["resume"] is False
    assert second["output_dir"] == artifacts / "runs" / "fresh-002" and second["resume"] is False
    for call in calls:
        assert call["provider"] == "codex" and call["model"] == "gpt-5.6-sol" and call["reasoning"] == "high"
        assert call["strict_ai"] is False and call["allow_remote"] is True and call["judge_id"] == "codex:gpt-5.6-sol"
        assert Path(call["output_dir"]).parent == artifacts / "runs"
    result = run_fresh.run(tmp_path / "authority", work, artifacts)
    assert len(calls) == 176 and all(call["resume"] is True for call in calls[88:])
    assert result["matrix"] == "m" * 64


def test_run_refuses_runtime_pin_drift_and_never_gates_after_provider_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bad = plan()
    bad["base_frozen"] = {"execution": {"model": "wrong", "provider": "other", "reasoning": "low"}}
    monkeypatch.setattr(run_fresh, "load_execution_contract", lambda *_: bad)
    monkeypatch.setattr(run_fresh, "run_judge", lambda **_: pytest.fail("provider must not run with a wrong route"))
    with pytest.raises(ValueError, match="runtime pin"):
        run_fresh.run(tmp_path, tmp_path, tmp_path)
    inputs, authority = _fresh88_inputs(tmp_path / "failure")
    work, artifacts = tmp_path / "failure-work", tmp_path / "failure-artifacts"
    monkeypatch.setattr(prepare_fresh, "load_authority", lambda _: authority)
    prepare_fresh.prepare(tmp_path / "authority", inputs, work, artifacts)
    monkeypatch.setattr(study, "load_authority", lambda _: authority)
    monkeypatch.setattr(run_fresh, "load_execution_contract", study.load_execution_contract)
    monkeypatch.setattr(run_fresh, "run_judge", lambda **_: (_ for _ in ()).throw(RuntimeError("provider failed")))
    monkeypatch.setattr(run_fresh, "verify_matrix", lambda *_: pytest.fail("incomplete run must not verify"))
    monkeypatch.setattr(run_fresh, "create_development_gate", lambda *_: pytest.fail("provider failure must not gate"))
    with pytest.raises(RuntimeError, match="provider failed"):
        run_fresh.run(tmp_path / "authority", work, artifacts)
