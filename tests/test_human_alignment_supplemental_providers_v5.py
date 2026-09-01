from __future__ import annotations

import builtins
import gzip
import hashlib
import importlib.util
import json
import shutil
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


def fake_runner(calls: list[str], *, fail_after_callback: bool = False, sealed_failed_http: bool = False):
    def invoke(**kwargs):
        calls.append(str(kwargs["artifact_id"]))
        root = kwargs["output_dir"]; root.mkdir()
        schema = runner_module._json_bytes(runner_module._response_schema())
        config_sha = "c" * 64
        (root / "run.json").write_bytes(runner_module._json_bytes({"config_sha256": config_sha}))
        (root / "response.schema.json").write_bytes(schema)
        (root / "responses").mkdir()
        prompt = f"fixture exact prompt {kwargs['artifact_id']}\n"
        (root / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt.encode(), mtime=0))
        kwargs["before_provider_attempt"]({
            "run": {"run_id": f"run-{kwargs['artifact_id']}", "config_sha256": config_sha},
            "provider": {"provider": "nous", "model": study.MODEL, "reasoning": "max", "endpoint": None},
            "batch": {"number": 1, "question_ids": kwargs["question_ids"]}, "attempt": {"number": 1, "batch_attempts": 1},
            "prompt": {"text": prompt, "bytes": len(prompt.encode()), "sha256": hashlib.sha256(prompt.encode()).hexdigest(), "base_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()},
            "response_schema": {"text": schema.decode(), "bytes": len(schema), "sha256": hashlib.sha256(schema).hexdigest()},
        })
        if fail_after_callback:
            if sealed_failed_http:
                source = Path(kwargs["artifact_path"])
                context = Path(kwargs["context_paths"][0])
                run_id = f"run-{kwargs['artifact_id']}"
                configuration = {
                    "artifact_id": kwargs["artifact_id"], "provider": "nous", "model": study.MODEL, "reasoning": "max",
                    "question_ids": kwargs["question_ids"],
                    "artifact": {"sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
                    "contexts": [{"sha256": hashlib.sha256(context.read_bytes()).hexdigest()}],
                }
                (root / "run.json").write_bytes(runner_module._json_bytes({"config_sha256": config_sha, "run_id": run_id, "configuration": configuration}))
                request = root / "responses" / "batch-0001.attempt-0001.nous.request.json"
                request.write_text(json.dumps({"model": study.MODEL, "reasoning_effort": "max", "max_physical_http_attempts_per_logical_request": 1, "messages": [{"role": "system", "content": "fixture"}, {"role": "user", "content": prompt}]}), encoding="utf-8")
                evidence = root / "responses" / "batch-0001.attempt-0001.nous.evidence"
                proof = evidence / "proof"; judge = evidence / "judge"
                proof.mkdir(parents=True); judge.mkdir()
                (proof / "manifest.json").write_text(json.dumps({"mode": "serialization-proof", "run_id": "proof-session"}), encoding="utf-8")
                (proof / "receipt.json").write_text(json.dumps({"run_id": "proof-session", "status": "success"}), encoding="utf-8")
                (judge / "manifest.json").write_text(json.dumps({"mode": "judge", "requested_provider": "nous", "requested_model": study.MODEL, "requested_reasoning_effort": "max", "run_id": "failure-session"}), encoding="utf-8")
                (judge / "receipt.json").write_text(json.dumps({"run_id": "failure-session", "status": "failure"}), encoding="utf-8")
                events = [
                    {"event_type": "judge_boundary", "data": {"request_sha256": hashlib.sha256(json.dumps(json.loads(request.read_text(encoding="utf-8")), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(), "transport_policy": {"logical_requests_per_attempt": 1, "max_physical_attempts_per_logical_request": 1}}},
                    {"event_type": "http_attempt", "data": {"method": "POST", "status": 502, "logical_request_id": "failure-logical-request"}},
                ]
                (judge / "events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
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


def test_execute_stops_before_later_cells_after_first_terminal(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    results = executor.execute(work, allow_remote=True, runner=fake_runner(calls, fail_after_callback=True), sealed_evidence_validator=lambda _: "session-1")
    assert [result["state"] for result in results] == ["reconcile_required"]
    assert calls == ["item-1"]
    assert not (work / "cells" / "pilot-02" / "native-run").exists()


def test_direct_later_execute_requires_completed_predecessor(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    with pytest.raises(ValueError, match="predecessor"):
        executor.execute_one(work, cell_id="pilot-02", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-2")
    assert calls == [] and not (work / "cells" / "pilot-02" / "native-run").exists()


def test_postcontact_failure_is_terminal_reconcile_required(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls, fail_after_callback=True), sealed_evidence_validator=lambda _: "session-1")
    assert result["state"] == "reconcile_required" and calls == ["item-1"]
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")["state"] == "reconcile_required"


def test_unsealed_terminal_accounting_cannot_be_reminted(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls, fail_after_callback=True), sealed_evidence_validator=lambda _: "session-1")["state"] == "reconcile_required"
    terminal_path = work / "cells" / "pilot-01" / "terminal-reconcile-required.json"
    terminal = study.read_json(terminal_path)
    terminal["confirmed_process_launches"] = 1; terminal["confirmed_provider_calls"] = 1
    terminal_path.write_bytes(study.canonical(terminal))
    with pytest.raises(ValueError, match="unsupported without sealed failure evidence"):
        executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")
    assert calls == ["item-1"]


def test_one_sealed_failed_http_attempt_is_durably_accounted(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    result = executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls, fail_after_callback=True, sealed_failed_http=True), sealed_evidence_validator=lambda _: "failure-session")
    terminal = study.read_json(work / "cells" / "pilot-01" / "terminal-reconcile-required.json")
    assert result["state"] == "reconcile_required" and {key: result[key] for key in ("confirmed_process_launches", "confirmed_provider_calls")} == {"confirmed_process_launches": 1, "confirmed_provider_calls": 1}
    assert {key: terminal[key] for key in ("confirmed_process_launches", "confirmed_provider_calls")} == {"confirmed_process_launches": 1, "confirmed_provider_calls": 1}
    assert terminal["failure_contact_evidence"]["physical_http_attempt_count"] == 1 and terminal["failure_contact_evidence"]["recovered_request_count"] == 0
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "failure-session")["state"] == "reconcile_required"
    assert calls == ["item-1"]


def test_swapped_hmac_valid_failed_evidence_is_rejected_by_cell_bindings(monkeypatch, tmp_path: Path):
    work, cells = prepared(monkeypatch, tmp_path); calls: list[str] = []
    sealed = lambda _: "failure-session"
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls, fail_after_callback=True, sealed_failed_http=True), sealed_evidence_validator=sealed)["state"] == "reconcile_required"
    second = work / "cells" / "pilot-02" / "native-run"
    second_cell = cells[1]; second_folder = Path(second_cell["input_folder"])
    with pytest.raises(OSError, match="postcontact"):
        fake_runner([], fail_after_callback=True, sealed_failed_http=True)(artifact_path=second_folder / "source.md", context_paths=[second_folder / "prompt.md"], artifact_id=second_cell["item_id"], output_dir=second, question_ids=second_cell["question_ids"], before_provider_attempt=lambda _: None)
    first_evidence = work / "cells" / "pilot-01" / "native-run" / "responses" / "batch-0001.attempt-0001.nous.evidence"
    second_evidence = second / "responses" / "batch-0001.attempt-0001.nous.evidence"
    shutil.rmtree(first_evidence)
    shutil.copytree(second_evidence, first_evidence)
    with pytest.raises(ValueError, match="prompt or run binding|cell configuration|immutable inputs|outbound request binding"):
        executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=sealed)


@pytest.mark.skipif(not Path(r"C:\Users\Haile\Documents\cwr-supplemental-providers-v5-20260901-59a285b-r1").is_dir() or not Path(r"C:\Users\Haile\Documents\cwr-supplemental-providers-v5-20260901-6ff4e74-r2").is_dir(), reason="immutable external V5 roots are unavailable")
def test_actual_r1_r2_legacy_terminal_views_are_read_only():
    roots = ((Path(r"C:\Users\Haile\Documents\cwr-supplemental-providers-v5-20260901-59a285b-r1"), "pilot-01"), (Path(r"C:\Users\Haile\Documents\cwr-supplemental-providers-v5-20260901-6ff4e74-r2"), "pilot-02"))
    before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for root, _ in roots for path in root.rglob("*") if path.is_file()}
    for root, cell_id in roots:
        result = executor.execute_one(root, cell_id=cell_id, allow_remote=True)
        assert result["state"] == "reconcile_required" and result["terminal_accounting_view"]["kind"] == "derived_read_only_terminal_contact_accounting"
        assert result["confirmed_process_launches"] == result["confirmed_provider_calls"] == 1
    after = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for root, _ in roots for path in root.rglob("*") if path.is_file()}
    assert after == before


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


def _replace_completion_with_terminal(work: Path, cell_id: str) -> None:
    root = work / "cells" / cell_id
    (root / "completion-receipt.json").unlink()
    study.immutable_json(root / "terminal-reconcile-required.json", {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "postlaunch_terminal_reconcile_required",
        "cell_id": cell_id, "contact_state": "ambiguous_after_intent", "confirmed_process_launches": 0,
        "confirmed_provider_calls": 0, "error": {"class": "Fixture", "message": "post-intent"},
        "retry_policy": "no_resend_fresh_successor_only",
    })


def _synthetic_terminal_cell(work: Path, calls: list[str], cell_id: str, *, predecessor_snapshot: dict | None = None) -> Path:
    root = work / "cells" / cell_id
    cell = study.read_json(root / "schedule.json")["cell"]
    fake_runner(calls)(artifact_id=cell["item_id"], output_dir=root / "native-run", question_ids=cell["question_ids"], before_provider_attempt=lambda _: None)
    intent = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "single_native_nous_launch_intent", "cell_id": cell_id,
        "prepared_sha256": study.sha(root / "prepared.json"), "route_proof_sha256": study.sha(root / "zero-new-spend-route-proof.json"),
        "callback": {}, "contact_state": "pre_native_intent", "confirmed_process_launches": 0, "confirmed_provider_calls": 0,
        "intended_maximum_process_launches": 1, "intended_maximum_provider_calls": 1,
    }
    if predecessor_snapshot is not None:
        intent["predecessor_snapshot"] = predecessor_snapshot
    study.immutable_json(root / "launch-intent.json", intent)
    study.immutable_json(root / "terminal-reconcile-required.json", {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "postlaunch_terminal_reconcile_required", "cell_id": cell_id,
        "contact_state": "ambiguous_after_intent", "confirmed_process_launches": 0, "confirmed_provider_calls": 0,
        "error": {"class": "Fixture", "message": "out-of-order"}, "retry_policy": "no_resend_fresh_successor_only",
    })
    return root


def test_reconcile_existing_replays_complete_native_artifacts_without_runner(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")["state"] == "completed_provisional_breadth_only"
    _replace_completion_with_terminal(work, "pilot-01")
    results = executor.reconcile_existing(work, sealed_evidence_validator=lambda _: "session-1", elapsed_reader=lambda _: 1.0)
    root = work / "cells" / "pilot-01"
    assert results[0] == {"cell_id": "pilot-01", "state": "reconciled_completion_provisional_breadth_only", "session_id": "session-1"}
    assert (root / "terminal-reconcile-required.json").is_file() and (root / "reconciled-completion.json").is_file()
    assert calls == ["item-1"]


def test_reconciled_predecessor_permits_later_fresh_launch(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda root: root.parent.parent.parent.name)["state"] == "completed_provisional_breadth_only"
    _replace_completion_with_terminal(work, "pilot-01")
    assert executor.reconcile_existing(work, sealed_evidence_validator=lambda root: root.parent.parent.parent.name, elapsed_reader=lambda _: 1.0)[0]["state"] == "reconciled_completion_provisional_breadth_only"
    result = executor.execute_one(work, cell_id="pilot-02", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda root: root.parent.parent.parent.name)
    assert result["state"] == "completed_provisional_breadth_only" and calls == ["item-1", "item-2"]
    intent = study.read_json(work / "cells" / "pilot-02" / "launch-intent.json")
    assert intent["predecessor_snapshot"]["predecessors"][0]["state"] == "reconciled"


def test_reconcile_existing_preserves_later_historical_policy_violation(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")["state"] == "completed_provisional_breadth_only"
    _replace_completion_with_terminal(work, "pilot-01")
    second = _synthetic_terminal_cell(work, calls, "pilot-02")
    first = work / "cells" / "pilot-01"
    results = executor.reconcile_existing(work, sealed_evidence_validator=lambda root: root.parent.parent.parent.name, elapsed_reader=lambda _: 1.0)
    assert results[0]["state"] == "reconciled_completion_provisional_breadth_only"
    assert results[1] == {"cell_id": "pilot-02", "state": "historical_policy_violation_not_promoted"}
    assert (first / "reconciled-completion.json").is_file() and not (second / "reconciled-completion.json").exists()


def test_reconcile_existing_marks_later_terminal_historical_when_predecessor_never_started(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    second = _synthetic_terminal_cell(work, calls, "pilot-02")
    results = executor.reconcile_existing(work, sealed_evidence_validator=lambda _: "session-2", elapsed_reader=lambda _: 1.0)
    assert results[:2] == [{"cell_id": "pilot-01", "state": "unstarted"}, {"cell_id": "pilot-02", "state": "historical_policy_violation_not_promoted"}]
    assert not (second / "reconciled-completion.json").exists()


def test_reconcile_existing_rejects_forged_predecessor_receipt_hash(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")["state"] == "completed_provisional_breadth_only"
    receipt = study.fingerprint(work / "cells" / "pilot-01" / "completion-receipt.json")
    receipt["sha256"] = "f" * 64
    second = _synthetic_terminal_cell(work, calls, "pilot-02", predecessor_snapshot={"predecessors": [{"cell_id": "pilot-01", "state": "completed", "completion_receipt": receipt}]})
    results = executor.reconcile_existing(work, sealed_evidence_validator=lambda _: "session-1", elapsed_reader=lambda _: 1.0)
    assert results[1] == {"cell_id": "pilot-02", "state": "historical_policy_violation_not_promoted"}
    assert not (second / "reconciled-completion.json").exists()


def test_reconcile_existing_rejects_absent_predecessor_receipt(monkeypatch, tmp_path: Path):
    work, _ = prepared(monkeypatch, tmp_path); calls: list[str] = []
    assert executor.execute_one(work, cell_id="pilot-01", allow_remote=True, runner=fake_runner(calls), sealed_evidence_validator=lambda _: "session-1")["state"] == "completed_provisional_breadth_only"
    receipt = study.fingerprint(work / "cells" / "pilot-01" / "completion-receipt.json")
    _replace_completion_with_terminal(work, "pilot-01")
    second = _synthetic_terminal_cell(work, calls, "pilot-02", predecessor_snapshot={"predecessors": [{"cell_id": "pilot-01", "state": "completed", "completion_receipt": receipt}]})
    results = executor.reconcile_existing(work, sealed_evidence_validator=lambda _: "session-1", elapsed_reader=lambda _: 1.0)
    assert results[0]["state"] == "reconciled_completion_provisional_breadth_only"
    assert results[1] == {"cell_id": "pilot-02", "state": "historical_policy_violation_not_promoted"}
    assert not (second / "reconciled-completion.json").exists()


def test_dynamic_bridge_import_registers_dataclass_module(monkeypatch, tmp_path: Path):
    bridge = tmp_path / "bridge.py"
    bridge.write_text("from dataclasses import dataclass\n@dataclass\nclass Record:\n    value: str\ndef validate_evidence(path):\n    return {'valid': Record('ok').value == 'ok'}\n", encoding="utf-8")
    original = importlib.util.spec_from_file_location
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda name, _: original(name, bridge))
    evidence = tmp_path / "evidence"
    for name, mode in (("proof", "serialization-proof"), ("judge", "judge")):
        child = evidence / name; child.mkdir(parents=True)
        (child / "manifest.json").write_text(json.dumps({"mode": mode, "run_id": "native-session"}), encoding="utf-8")
        (child / "receipt.json").write_text(json.dumps({"run_id": "native-session"}), encoding="utf-8")
    assert executor._sealed_session_id(evidence) == "native-session"


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
