from __future__ import annotations

import builtins
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs import runner as runner_module

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v5"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


executor = load("supplemental_hanna_v5_executor")
study = executor.study


def route() -> dict:
    return {
        "provider": "nous", "model": study.MODEL, "reasoning": "max", "tools_enabled": False,
        "zero_new_spend_existing_credit_only": True, "paid_fallback_forbidden": True, "armed": True,
        "checked_at": "2026-09-01T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z",
    }


def fixture_cells(tmp_path: Path, *, question_ids: list[str] | None = None) -> list[dict]:
    cells = []
    for index in range(1, 4):
        folder = tmp_path / "inputs" / f"item-{index}"
        folder.mkdir(parents=True)
        task = json.dumps({"contract_version": 1, "contract_id": f"contract-{index}", "artifact_id": f"item-{index}", "context": {"artifact_kind": "short_story", "declared_scope": "whole short story", "completion_status": "complete", "background": [], "constraints": [], "audience": []}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []})
        for name, content in (("source.md", f"source {index}"), ("prompt.md", f"prompt {index}"), ("task-contract.json", task)):
            (folder / name).write_text(content, encoding="utf-8")
        inputs = {name: study.fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
        cells.append({
            "cell_id": f"pilot-{index:02d}", "historical_cell_id": f"historical-{index:02d}", "item_id": f"item-{index}",
            "selection": {"item_id": f"item-{index}"}, "inputs": inputs, "input_folder": str(folder),
            "question_ids": question_ids or [f"q-{index}-{number}" for number in range(1, 9)],
            "historical_question_ids_sha256": "a" * 64,
        })
    return cells


def prepared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, question_ids: list[str] | None = None) -> tuple[Path, list[dict]]:
    cells = fixture_cells(tmp_path, question_ids=question_ids)
    runtime = {"runner": {"sha256": "r"}, "launcher": {"sha256": "l"}, "bridge": {"sha256": "b"}}
    monkeypatch.setattr(study, "load_v4_cells", lambda _: ({"runtime": {"historical": True}}, cells))
    monkeypatch.setattr(study, "runtime_bindings", lambda: runtime)
    v4 = tmp_path / "v4"; v4.mkdir()
    (v4 / "frozen-transport-contract.json").write_bytes(runner_module._json_bytes({"fixture": True}))
    work = tmp_path / "work"
    executor.prepare(work, v4_work_dir=tmp_path / "v4", route_proof=route())
    return work, cells


def fake_runner(calls: list[str], *, fail_after_callback: bool = False):
    def invoke(**kwargs):
        calls.append(str(kwargs["artifact_id"]))
        root = kwargs["output_dir"]; root.mkdir()
        schema = runner_module._json_bytes(runner_module._response_schema())
        config_sha = "c" * 64
        (root / "run.json").write_bytes(runner_module._json_bytes({"config_sha256": config_sha}))
        (root / "response.schema.json").write_bytes(schema)
        (root / "responses").mkdir()
        prompt = "fixture exact prompt\n"
        (root / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt.encode(), mtime=0))
        kwargs["before_provider_attempt"]({
            "run": {"run_id": f"run-{kwargs['artifact_id']}", "config_sha256": config_sha},
            "provider": {"provider": "nous", "model": study.MODEL, "reasoning": "max", "endpoint": None},
            "batch": {"number": 1, "question_ids": kwargs["question_ids"]}, "attempt": {"number": 1, "batch_attempts": 1},
            "prompt": {"text": prompt, "bytes": len(prompt.encode()), "sha256": hashlib.sha256(prompt.encode()).hexdigest(), "base_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
            "response_schema": {"text": schema.decode(), "bytes": len(schema), "sha256": hashlib.sha256(schema).hexdigest()},
        })
        if fail_after_callback:
            raise OSError("fixture postcontact failure")
        request = root / "responses" / "judge-request.json"; request.write_bytes(b"request")
        result = root / "responses" / "judge-result.json"; result.write_bytes(b"result")
        proof = root / "responses" / "serialization-proof.json"; proof.write_bytes(b"proof")
        evidence = root / "responses" / "evidence"; evidence.mkdir(); (evidence / "sealed.bin").write_bytes(b"sealed")
        provider = {
            "requested": {"model": study.MODEL, "reasoning_effort": "max"},
            "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0,
            "tool_free": True, "provider_artifacts": {
                "judge_request": runner_module._provider_artifact(root, request),
                "judge_result": runner_module._provider_artifact(root, result),
                "serialization_proof": runner_module._provider_artifact(root, proof),
                "evidence_tree": runner_module._provider_tree_digest(root, evidence),
            },
        }
        (root / "responses" / "batch-0001.json").write_bytes(runner_module._json_bytes({"provider": provider}))
        return {"status": "DIAGNOSTIC_SUBSET"}
    return invoke


def test_prepare_uses_exact_first_eight_v4_question_ids_and_no_contact(monkeypatch, tmp_path: Path):
    work, cells = prepared(monkeypatch, tmp_path)
    frozen = study.read_json(work / "frozen-v5.json")
    assert frozen["provider_calls_made"] == 0 and frozen["process_launches"] == 0
    assert [cell["question_ids"] for cell in frozen["cells"]] == [cell["question_ids"] for cell in cells]
    for cell in cells:
        root = work / "cells" / cell["cell_id"]
        assert {path.name for path in root.iterdir()} == set(study.PREPARED_FILES)
        disclosure = study.read_json(root / "disclosure.json")
        assert disclosure["question_ids"] == cell["question_ids"] and disclosure["tools_enabled"] is False


def test_prepare_rejects_existing_orphan_without_adoption(monkeypatch, tmp_path: Path):
    work = tmp_path / "work"; work.mkdir()
    cells = fixture_cells(tmp_path)
    monkeypatch.setattr(study, "load_v4_cells", lambda _: ({}, cells))
    monkeypatch.setattr(study, "runtime_bindings", lambda: {"runner": {}, "launcher": {}, "bridge": {}})
    with pytest.raises(ValueError, match="fresh nonexistent"):
        executor.prepare(work, v4_work_dir=tmp_path / "v4", route_proof=route())


def test_callback_order_binds_exact_runner_prompt_gzip(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")
    assert result["state"] == "completed_provisional_breadth_only" and result["confirmed_provider_calls"] == 1 and calls == ["item-1"]
    root = work / "cells" / "pilot-01"
    assert (root / "launch-intent.json").is_file() and (root / "completion-receipt.json").is_file()


def test_real_runner_reaches_actual_precontact_boundary_before_native_call(monkeypatch, tmp_path: Path):
    modules = runner_module.load_modules(executor.registry_path())
    bundle = runner_module.resolve_bundle(runner_module.load_bundles(executor.bundles_path()), "prose.short_story")
    question_ids = [item["question"]["id"] for item in runner_module.compiled_questions(runner_module.compile_bundle(modules, bundle, task_contract=None))[:8]]
    work, _ = prepared(monkeypatch, tmp_path, question_ids=question_ids); native_calls: list[bool] = []
    def forbidden_native(**kwargs):
        native_calls.append(True)
        raise runner_module.HBQError("fixture stops before native Nous contact")
    monkeypatch.setattr(runner_module, "_call_nous", forbidden_native)
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, sealed_evidence_validator=lambda _: "unused")
    native = work / "cells" / "pilot-01" / "native-run"
    assert result["state"] == "reconcile_required" and result["confirmed_provider_calls"] == 0 and result["confirmed_process_launches"] == 0 and native_calls == [True]
    assert {path.name for path in native.iterdir()} >= {"run.json", "response.schema.json", "responses"}
    assert (native / "responses" / "batch-0001.prompt.txt.gz").is_file()


def test_one_contact_then_second_call_is_idle(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []; runner = fake_runner(calls)
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=runner, sealed_evidence_validator=lambda _: "session-1")["confirmed_provider_calls"] == 1
    again = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=runner, sealed_evidence_validator=lambda _: "session-1")
    assert {key: again[key] for key in ("cell_id", "state", "confirmed_provider_calls", "confirmed_process_launches")} == {"cell_id": "pilot-01", "state": "terminal_no_resend", "confirmed_provider_calls": 0, "confirmed_process_launches": 0}
    assert calls == ["item-1"]


def test_three_cells_run_sequentially_with_distinct_native_sessions(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    results = executor.execute(work, allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda root: root.parent.parent.parent.name)
    assert calls == ["item-1", "item-2", "item-3"]
    assert [result["receipt"]["native_contact_identity"]["session_id"] for result in results] == ["pilot-01", "pilot-02", "pilot-03"]


def test_postcontact_failure_is_terminal_reconcile_required(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls, fail_after_callback=True), sealed_evidence_validator=lambda _: "session-1")
    assert result["state"] == "reconcile_required" and calls == ["item-1"]
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")["state"] == "reconcile_required"


def test_sealed_evidence_validation_failure_after_intent_is_terminal(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path)
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner([]), sealed_evidence_validator=lambda _: (_ for _ in ()).throw(ValueError("fixture invalid HMAC")))
    assert result["state"] == "reconcile_required"
    terminal = study.read_json(work / "cells" / "pilot-01" / "terminal-reconcile-required.json")
    assert terminal["confirmed_provider_calls"] == 0 and terminal["confirmed_process_launches"] == 0


def test_duplicate_prior_session_is_revalidated_and_terminal(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []; verified: list[str] = []
    def session(_: Path) -> str:
        verified.append("checked")
        return "same-native-session"
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=session)["state"] == "completed_provisional_breadth_only"
    result = executor.execute_one(work, cell_id="pilot-02", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=session)
    assert result["state"] == "reconcile_required" and verified
    assert (work / "cells" / "pilot-02" / "terminal-reconcile-required.json").is_file()


def test_tampered_prepared_or_native_envelope_is_rejected(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path)
    root = work / "cells" / "pilot-01"
    (root / "disclosure.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not canonical|prepared commitment|acknowledgement"):
        executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner([]), sealed_evidence_validator=lambda _: "session-1")
    work, _ = prepared(monkeypatch, tmp_path / "second")
    def malformed(**kwargs):
        fake_runner([])(**kwargs)
        checkpoint = kwargs["output_dir"] / "responses" / "batch-0001.json"
        value = json.loads(checkpoint.read_text(encoding="utf-8")); value["provider"]["provider_artifacts"].pop("evidence_tree")
        checkpoint.write_bytes(runner_module._json_bytes(value))
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=malformed, sealed_evidence_validator=lambda _: "session-1")
    assert result["state"] == "reconcile_required"
    assert (work / "cells" / "pilot-01" / "terminal-reconcile-required.json").is_file()


def test_runtime_has_no_optimizer_import(monkeypatch):
    attempted: list[str] = []; original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}:
            attempted.append(name); raise AssertionError(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    loaded = load("supplemental_hanna_v5_import_guard")
    assert loaded.study.STUDY_ID.endswith("-v5") and attempted == []
