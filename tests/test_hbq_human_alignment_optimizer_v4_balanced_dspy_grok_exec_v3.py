from __future__ import annotations

import base64
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3"
executor = load_module(PACKAGE / "executor.py", name="feedback_grok_v3")
ACK = "a" * 64


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _preparation() -> tuple[bytes, dict]:
    inputs = {"parent_candidate_id": "baseline", "parent_instruction_base64": _b64(b"baseline instruction"), "parent_profile_base64": _b64(b'{"dimension_first_overall_button":true}'), "training_result_base64": _b64(b"{}"), "training_diagnostics_base64": _b64(b"{}")}
    value = {"inputs": inputs, "preparation_sha256": "b" * 64}
    return executor.canonical(value), value


def _feedback(root: Path) -> tuple[bytes, dict]:
    study_id = "hbq-human-alignment-optimizer-v4-balanced-r4"; summary = "r4 two-phase public summary"
    contract = root / "producer-contract.json"; source = root / "producer.py"; selection_schema = root / "selection-schema.json"; result_schema = root / "result-schema.json"; selection = root / "selection.json"; result = root / "result.json"
    contract.write_bytes(executor.canonical({"study_id": study_id})); source.write_bytes(b"producer source"); selection_schema.write_bytes(executor.canonical({"type": "object"})); result_schema.write_bytes(executor.canonical({"type": "object"})); selection.write_bytes(executor.canonical({"study_id": study_id, "kind": "two_phase_selection"})); result.write_bytes(executor.canonical({"study_id": study_id, "kind": "two_phase_result", "public_result_summary": summary}))
    producer = {"study_contract_path": str(contract), "study_contract_sha256": executor.sha256(contract.read_bytes()), "producer_source_path": str(source), "producer_source_sha256": executor.sha256(source.read_bytes()), "selection_schema_path": str(selection_schema), "selection_schema_sha256": executor.sha256(selection_schema.read_bytes()), "result_schema_path": str(result_schema), "result_schema_sha256": executor.sha256(result_schema.read_bytes())}
    artifacts = {"selection_path": str(selection), "selection_sha256": executor.sha256(selection.read_bytes()), "result_path": str(result), "result_sha256": executor.sha256(result.read_bytes())}
    value = {"format_version": 1, "kind": "hanna_r4_two_phase_feedback", "study_id": study_id, "wave_id": "r4-feedback-wave", "seed": 17, "public_result_summary": summary, "producer": producer, "artifacts": artifacts}
    return executor.canonical(value), value


def _fake_v2(route_calls: list[str], adapter_calls: list[dict] | None = None) -> SimpleNamespace:
    preparation_raw, preparation = _preparation()
    route = {"name": "grok-build-grok-4.6", "provider": "xai_grok_build", "model": "grok-4.6", "adapter": "grok_exec", "destination": "xai_grok_build_subscription"}
    def decode(value: str, *, label: str) -> bytes: return base64.b64decode(value.encode("ascii"), validate=True)
    def get_route(_queue: Path):
        route_calls.append("route")
        return SimpleNamespace(), SimpleNamespace(), route, {"route_name": route["name"], "route_sha256": "3" * 64}
    def adapter_once(_broker, _route, request, _capture):
        if adapter_calls is not None: adapter_calls.append(dict(request))
        return SimpleNamespace(state="definitely_not_contacted", detail="fixture precontact", result=None), executor.canonical({"control": {"version": 1, "state": "definitely_not_contacted"}})
    return SimpleNamespace(_contract=lambda: None, _preparation=lambda _path: (preparation_raw, preparation), _schema=lambda: executor.canonical({"$schema_version": 1, "type": "object", "additionalProperties": False, "required": ["descendant_instruction_base64", "descendant_profile_base64"], "properties": {"descendant_instruction_base64": {"type": "string"}, "descendant_profile_base64": {"type": "string"}}}), _decode=decode, _route=get_route, _adapter_once=adapter_once)


def _completed_v2(*, wrong_model: bool = False, same_identity: bool = False, mutate: object = None) -> SimpleNamespace:
    preparation_raw, preparation = _preparation(); identity: dict = {}; route = {"name": "grok-build-grok-4.6", "provider": "xai_grok_build", "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "adapter": "grok_exec", "destination": "xai_grok_build_subscription", "grok_command_identity": identity}; evidence = {"route_name": route["name"], "route_sha256": "3" * 64, "grok_cli_version": "fixture", "subscription_receipt_hash": "4" * 64, "grok_command_identity_sha256": executor.sha256(executor.canonical(identity))}; output = {"descendant_instruction_base64": _b64(b"new instruction"), "descendant_profile_base64": _b64(b'{"new":true}')}; lineage = {"parent_candidate_id": "baseline", "parent_instruction_sha256": "5" * 64, "parent_profile_sha256": "6" * 64, "descendant_instruction_sha256": "7" * 64, "descendant_profile_sha256": "8" * 64}
    def get_route(_queue: Path): return SimpleNamespace(), SimpleNamespace(), route, evidence
    def adapter_once(_broker, _route, request, _capture):
        request_id = "9" * 64; session_id = request_id if same_identity else "a" * 64
        runtime = {"adapter_version": 1, "requested_model": "wrong" if wrong_model else route["model"], "reported_model": route["reported_model"], "requested_reasoning_effort": route["reasoning_effort"], "reasoning_attested": False, "identity_evidence": "requested_only", "execution_policy": "bounded_nonvisual_read_only", "nonvisual_max_turns": 1, "observed_turns": 1, "cli_version": evidence["grok_cli_version"], "subscription_receipt_hash": evidence["subscription_receipt_hash"], "command_identity": identity, "request_id_hash": request_id, "session_id_hash": session_id}
        result = {"schema_version": 1, "request_hash": executor.sha256(executor.canonical({"prompt": request["prompt"]})), "output": output, "output_hash": executor.sha256(executor.canonical(output)), "runtime": runtime}; control = {"control": {"version": 1, "state": "completed"}, "result": result}
        if callable(mutate): mutate()
        return SimpleNamespace(state="completed", detail=None, result=result), executor.canonical(control)
    return SimpleNamespace(_contract=lambda: None, _preparation=lambda _path: (preparation_raw, preparation), _schema=lambda: executor.canonical({"$schema_version": 1, "type": "object", "additionalProperties": False, "required": ["descendant_instruction_base64", "descendant_profile_base64"], "properties": {}}), _decode=lambda value, **_kwargs: base64.b64decode(value.encode("ascii"), validate=True), _route=get_route, _adapter_once=adapter_once, _descendant=lambda _output, _preparation: (output, lineage))


def test_prepare_ten_feedback_bound_wave_is_provider_free_and_byte_identical(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); route_calls: list[str] = []; monkeypatch.setattr(executor, "_v2", lambda: _fake_v2(route_calls))
    rows = [executor.prepare_one(output_root=tmp_path / "roots", sample_id=index, dspy_input_preparation_path=tmp_path / "prep.json", feedback_path=feedback, feedback_sha256=executor.sha256(feedback_raw), queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK) for index in range(1, 11)]
    assert [row["provider_calls_made"] for row in rows] == [0] * 10 and len({row["sample_id"] for row in rows}) == 10 and route_calls == ["route"] * 10
    roots = [tmp_path / "roots" / row["sample_id"] for row in rows]
    assert len({(root / "prompt-request.bin").read_bytes() for root in roots}) == 1
    prepared = json.loads((roots[0] / "prepared.json").read_bytes())
    assert prepared["feedback_sha256"] == executor.sha256(feedback_raw) and prepared["confirmation"] == {"status": "unopened", "cells": 0} and prepared["selection_authority"] == prepared["runtime_authority"] == "none"


def test_prepare_rejects_feedback_hash_before_route_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); calls: list[str] = []; monkeypatch.setattr(executor, "_v2", lambda: _fake_v2(calls))
    with pytest.raises(ValueError, match="feedback file hash"):
        executor.prepare_one(output_root=tmp_path / "roots", sample_id=1, dspy_input_preparation_path=tmp_path / "prep.json", feedback_path=feedback, feedback_sha256="f" * 64, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK)
    assert not calls and not (tmp_path / "roots").exists()


def test_prepare_rejects_mutated_pinned_producer_source_before_route_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); Path(feedback_value["producer"]["producer_source_path"]).write_bytes(b"mutated")
    calls: list[str] = []; monkeypatch.setattr(executor, "_v2", lambda: _fake_v2(calls))
    with pytest.raises(ValueError, match="producer source hash"):
        executor.prepare_one(output_root=tmp_path / "roots", sample_id=1, dspy_input_preparation_path=tmp_path / "prep.json", feedback_path=feedback, feedback_sha256=executor.sha256(feedback_raw), queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK)
    assert not calls


def test_execute_uses_pinned_transport_once_and_strands_precontact_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); routes: list[str] = []; calls: list[dict] = []; monkeypatch.setattr(executor, "_v2", lambda: _fake_v2(routes, calls))
    common = {"output_root": tmp_path / "roots", "sample_id": 1, "dspy_input_preparation_path": tmp_path / "prep.json", "feedback_path": feedback, "feedback_sha256": executor.sha256(feedback_raw), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}
    executor.prepare_one(**common)
    result = executor.execute_one(**common, allow_remote=True)
    assert result["kind"] == "definitely_not_contacted" and result["provider_calls_made"] == 0 and len(calls) == 1
    root = next((tmp_path / "roots").iterdir())
    assert (root / "launch-intent.json").is_file() and (root / "adapter-stdout.bin").is_file()
    with pytest.raises(ValueError, match="forbids resend"):
        executor.execute_one(**common, allow_remote=True)


def test_execute_route_drift_is_definite_precontact_without_adapter_call(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); routes: list[str] = []; calls: list[dict] = []; v2 = _fake_v2(routes, calls); original = v2._route
    def drifting(queue: Path):
        native, broker, route, evidence = original(queue)
        if len(routes) > 1: route = {**route, "destination": "drifted"}
        return native, broker, route, evidence
    v2._route = drifting; monkeypatch.setattr(executor, "_v2", lambda: v2)
    common = {"output_root": tmp_path / "roots", "sample_id": 1, "dspy_input_preparation_path": tmp_path / "prep.json", "feedback_path": feedback, "feedback_sha256": executor.sha256(feedback_raw), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}
    executor.prepare_one(**common); result = executor.execute_one(**common, allow_remote=True)
    assert result["kind"] == "definitely_not_contacted" and result["process_launches"] == result["provider_calls_made"] == 0 and not calls


@pytest.mark.parametrize(("wrong_model", "same_identity"), [(True, False), (False, True)])
def test_completed_identity_failures_are_reconcile_only_and_never_persist_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, wrong_model: bool, same_identity: bool):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); monkeypatch.setattr(executor, "_v2", lambda: _completed_v2(wrong_model=wrong_model, same_identity=same_identity))
    common = {"output_root": tmp_path / "roots", "sample_id": 1, "dspy_input_preparation_path": tmp_path / "prep.json", "feedback_path": feedback, "feedback_sha256": executor.sha256(feedback_raw), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}
    executor.prepare_one(**common); result = executor.execute_one(**common, allow_remote=True); root = next((tmp_path / "roots").iterdir())
    assert result["kind"] == "reconcile_required_after_process_launch" and not (root / "execution-receipt.json").exists() and not (root / "adapter-control-envelope.json").exists()
    assert json.loads((root / "result.json").read_bytes())["kind"] == "reconcile_required_after_process_launch"
    with pytest.raises(ValueError, match="forbids resend"):
        executor.execute_one(**common, allow_remote=True)


def test_completed_contact_can_mutate_external_feedback_only_after_immutable_prepare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw)
    def mutate() -> None:
        Path(feedback_value["producer"]["producer_source_path"]).write_bytes(b"changed source")
        Path(feedback_value["artifacts"]["selection_path"]).write_bytes(executor.canonical({"changed": True}))
        Path(feedback_value["artifacts"]["result_path"]).write_bytes(executor.canonical({"changed": True}))
    monkeypatch.setattr(executor, "_v2", lambda: _completed_v2(mutate=mutate))
    common = {"output_root": tmp_path / "roots", "sample_id": 1, "dspy_input_preparation_path": tmp_path / "prep.json", "feedback_path": feedback, "feedback_sha256": executor.sha256(feedback_raw), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}
    executor.prepare_one(**common); result = executor.execute_one(**common, allow_remote=True); root = next((tmp_path / "roots").iterdir())
    assert result["state"] == "native_descendant_received" and (root / "execution-receipt.json").is_file() and not (root / executor.POSTWRITE_RECONCILE).exists()


def test_postwrite_admission_failure_gets_terminal_marker_without_overwrite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); monkeypatch.setattr(executor, "_v2", lambda: _completed_v2())
    common = {"output_root": tmp_path / "roots", "sample_id": 1, "dspy_input_preparation_path": tmp_path / "prep.json", "feedback_path": feedback, "feedback_sha256": executor.sha256(feedback_raw), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK}
    executor.prepare_one(**common); monkeypatch.setattr(executor, "_admit_completed_root", lambda *_args: (_ for _ in ()).throw(ValueError("injected")))
    result = executor.execute_one(**common, allow_remote=True); root = next((tmp_path / "roots").iterdir())
    assert result["kind"] == "postwrite_reconcile_required" and (root / executor.POSTWRITE_RECONCILE).is_file() and (root / "result.json").is_file()
    with pytest.raises(ValueError, match="forbids resend"):
        executor.execute_one(**common, allow_remote=True)


def test_wave_uses_ten_isolated_gated_children(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); active = 0; maximum = 0; owned: set[int] = set()
    class Owner:
        def __init__(self, child): owned.add(id(child))
        async def stop(self): pass
        def close(self): pass
    class Process:
        returncode = 0
        def __init__(self, sample: str, gate: Path): self.sample, self.gate = sample, gate
        async def communicate(self):
            nonlocal active
            assert id(self) in owned and self.gate.read_bytes() == b"feedback-grok-v3-isolation-gate\n"
            await asyncio.sleep(0.01); active -= 1
            return executor.canonical({"sample_id": self.sample, "state": "native_descendant_received", "provider_calls_made": 1, "process_launches": 1, "descendant_sha256": "f" * 64}), b""
    async def spawn(*argv, **_kwargs):
        nonlocal active, maximum
        sample = argv[argv.index("--sample-id") + 1]; feedback_value = json.loads(feedback_raw); logical = executor._sample(feedback_value["wave_id"], sample); gate = Path(argv[argv.index("--isolation-gate") + 1]); active += 1; maximum = max(maximum, active); return Process(logical, gate)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn); monkeypatch.setattr(executor, "_ChildTreeOwner", Owner)
    rows = asyncio.run(executor.execute_wave(output_root=tmp_path / "roots", sample_ids=list(range(1, 11)), dspy_input_preparation_path=tmp_path / "prep.json", feedback_path=feedback, feedback_sha256=executor.sha256(feedback_raw), queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True))
    assert len(rows) == 10 and maximum == 10 and all(row["state"] == "isolated_child_reconcile_required" for row in rows) and not (tmp_path / "roots" / ".isolated-gates").exists()


def test_wave_timeout_and_owner_failure_stop_children(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    feedback_raw, _feedback_value = _feedback(tmp_path); feedback = tmp_path / "feedback.json"; feedback.write_bytes(feedback_raw); stopped: list[str] = []
    class Process:
        returncode = None
        async def communicate(self): await asyncio.Event().wait(); return b"", b""
        async def wait(self): return self.returncode
        def terminate(self): self.returncode = 1; stopped.append("terminate")
        def kill(self): self.returncode = 1; stopped.append("kill")
    class Owner:
        def __init__(self, _child): pass
        async def stop(self): stopped.append("stop")
        def close(self): pass
    async def spawn(*_argv, **_kwargs): return Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn); monkeypatch.setattr(executor, "_ChildTreeOwner", Owner); monkeypatch.setattr(executor, "ISOLATED_CHILD_TIMEOUT_SECONDS", 0.01)
    common = {"output_root": tmp_path / "roots", "sample_ids": list(range(1, 11)), "dspy_input_preparation_path": tmp_path / "prep.json", "feedback_path": feedback, "feedback_sha256": executor.sha256(feedback_raw), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "allow_remote": True}
    rows = asyncio.run(executor.execute_wave(**common))
    assert len(rows) == 10 and stopped == ["stop"] * 10
    stopped.clear()
    class BrokenOwner:
        def __init__(self, _child): raise OSError("fixture ownership failure")
    monkeypatch.setattr(executor, "_ChildTreeOwner", BrokenOwner)
    rows = asyncio.run(executor.execute_wave(**{**common, "output_root": tmp_path / "roots2"}))
    assert len(rows) == 10 and stopped == ["terminate"] * 10


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object semantics")
def test_windows_child_owner_terminates_actual_process() -> None:
    async def exercise() -> None:
        child = await asyncio.create_subprocess_exec(__import__("sys").executable, "-c", "import time; time.sleep(30)", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0))
        owner = executor._ChildTreeOwner(child); await owner.stop(); owner.close()
        assert child.returncode is not None
    asyncio.run(exercise())
