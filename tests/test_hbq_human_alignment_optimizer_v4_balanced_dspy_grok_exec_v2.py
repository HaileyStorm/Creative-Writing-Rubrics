from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2"
executor = load_module(PACKAGE / "executor.py", name="hanna_v4_balanced_dspy_grok_exec_v2")
AUTH = "a" * 64


def _fixture_preparation(path: Path) -> tuple[Path, str, str]:
    inputs = {"parent_candidate_id": "candidate-4", "parent_instruction_base64": base64.b64encode(b"parent instruction").decode(), "parent_profile_base64": base64.b64encode(executor.canonical({"parent": True})).decode(), "training_result_base64": base64.b64encode(executor.canonical({"result": "fixed"})).decode(), "training_diagnostics_base64": base64.b64encode(executor.canonical({"diagnostics": "fixed"})).decode()}
    value = {"format_version": 1, "study_id": "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1", "kind": "dspy_predict_input_preparation", "dspy_program": "Predict(BalancedDescendantSignature)@3.3.1", "inputs": inputs, "inputs_sha256": executor.sha256(executor.canonical(inputs)), "training_result_sha256": "b" * 64, "training_diagnostics_sha256": "c" * 64, "dependencies": {"fixture": "only"}, "provider_calls_made": 0, "dispatch_authority": "none_governed_executor_required", "runtime_authority": "none", "confirmation": {"status": "unopened", "cells": 0}}
    value["preparation_sha256"] = executor.sha256(executor.canonical(value)); raw = executor.canonical(value); path.write_bytes(raw)
    return path, executor.sha256(raw), value["preparation_sha256"]


def _route(*_args):
    route = {"name": "grok-build-grok-4.6", "provider": "xai_grok_build", "model": "grok-4.6", "adapter": "grok_exec", "destination": "xai_grok_build_subscription", "nonvisual_max_turns": 1}
    return None, object(), route, {"route_name": route["name"], "route_sha256": "d" * 64, "registry_sha256": "e" * 64, "cost_evidence_hash": "f" * 64, "subscription_receipt_hash": "a" * 64, "grok_command_identity_sha256": executor.sha256(executor.canonical({"version": 1, "artifacts": []})), "cli_version_identity_sha256": "b" * 64, "grok_cli_version": "grok 1.0.13"}


def _patch_fixture(monkeypatch, path: Path, raw_hash: str, preparation_hash: str):
    monkeypatch.setattr(executor, "_contract", lambda: {})
    monkeypatch.setattr(executor, "_optimizer", lambda: SimpleNamespace(contract=lambda: None, _output_dependencies=lambda: {"fixture": "only"}))
    monkeypatch.setattr(executor, "_route", _route)
    monkeypatch.setattr(executor, "PREPARATION_FILE_SHA256", raw_hash)
    monkeypatch.setattr(executor, "PREPARATION_SHA256", preparation_hash)


def _completed(counter: list[int]):
    def invoke(_broker, _route_value, _request, _capture_path):
        counter[0] += 1; number = counter[0]
        output = {"descendant_instruction_base64": base64.b64encode(f"instruction {number}".encode()).decode(), "descendant_profile_base64": base64.b64encode(executor.canonical({"sample": number})).decode()}
        runtime = {"adapter_version": 1, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli", "identity_evidence": "requested_only", "cli_version": "grok 1.0.13", "session_id_hash": f"{number + 100:064x}", "request_id_hash": f"{number:064x}", "envelope_hash": f"{number + 200:064x}", "command_identity": {"version": 1, "artifacts": []}, "command_identity_hash": f"{number + 300:064x}", "subscription_receipt_hash": "a" * 64, "execution_policy": "bounded_nonvisual_read_only", "usage_telemetry": {"status": "not_reported"}, "nonvisual_max_turns": 1, "observed_turns": 1}
        result = {"schema_version": 1, "request_hash": executor.sha256(executor.canonical(_request)), "output": output, "output_hash": executor.sha256(executor.canonical(output)), "runtime": runtime}
        control = {"control": {"version": 1, "state": "completed"}, "result": result}
        return SimpleNamespace(state="completed", detail=None, result=result), json.dumps(control, sort_keys=True, separators=(",", ":")).encode()
    return invoke


def test_contract_is_exactly_hash_pinned(tmp_path: Path, monkeypatch):
    executor._contract()
    mutated = tmp_path / "contract.json"; mutated.write_bytes(executor.canonical({"study_id": executor.STUDY_ID}))
    monkeypatch.setattr(executor, "CONTRACT_PATH", mutated)
    with pytest.raises(ValueError, match="contract drifted"):
        executor._contract()


def test_all_ten_have_identical_prepared_bytes_and_freeze_only_after_distinct_native_records(monkeypatch, tmp_path: Path):
    preparation, raw_hash, prep_hash = _fixture_preparation(tmp_path / "dspy-descendant-input-preparation.json"); _patch_fixture(monkeypatch, preparation, raw_hash, prep_hash)
    counter = [0]; monkeypatch.setattr(executor, "_adapter_once", _completed(counter)); common = {"output_root": tmp_path / "out", "dspy_input_preparation_path": preparation, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": AUTH}
    for sample in range(1, 11):
        assert executor.prepare_one(sample_id=sample, **common)["provider_calls_made"] == 0
        assert executor.execute_one(sample_id=sample, allow_remote=True, **common)["state"] == "native_descendant_received"
    prompts = {(common["output_root"] / f"sample-{sample:02d}" / "prompt-request.bin").read_bytes() for sample in range(1, 11)}
    schemas = {(common["output_root"] / f"sample-{sample:02d}" / "response-schema.json").read_bytes() for sample in range(1, 11)}
    inputs = {(common["output_root"] / f"sample-{sample:02d}" / "dspy-input-preparation.json").read_bytes() for sample in range(1, 11)}
    assert len(prompts) == len(schemas) == len(inputs) == 1
    manifest = executor.freeze_all_ten(output_root=common["output_root"], manifest_path=tmp_path / "frozen.json")
    assert len(manifest["samples"]) == 10 and manifest["freeze_provider_calls_made"] == 0 and manifest["source_provider_calls_made"] == 10
    assert manifest["confirmation"] == {"status": "unopened", "cells": 0}
    sample_one = common["output_root"] / "sample-01"
    for name, replacement in (("prompt-request.bin", b"tampered"), ("response-schema.json", b"{}\n"), ("adapter-stdout.bin", b"{}")):
        target = sample_one / name; original = target.read_bytes(); target.write_bytes(replacement)
        with pytest.raises(ValueError): executor.freeze_all_ten(output_root=common["output_root"], manifest_path=tmp_path / f"tampered-{name}.json")
        target.write_bytes(original)
    receipt = sample_one / "execution-receipt.json"; original = receipt.read_bytes(); receipt.write_bytes((common["output_root"] / "sample-02" / "execution-receipt.json").read_bytes())
    with pytest.raises(ValueError): executor.freeze_all_ten(output_root=common["output_root"], manifest_path=tmp_path / "swapped-receipt.json")
    receipt.write_bytes(original)


def test_freeze_rejects_duplicate_adapter_identity_and_parent_identical_descendant(monkeypatch, tmp_path: Path):
    preparation, raw_hash, prep_hash = _fixture_preparation(tmp_path / "dspy-descendant-input-preparation.json"); _patch_fixture(monkeypatch, preparation, raw_hash, prep_hash)
    counter = [0]; monkeypatch.setattr(executor, "_adapter_once", _completed(counter)); common = {"output_root": tmp_path / "out", "dspy_input_preparation_path": preparation, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": AUTH}
    for sample in range(1, 11): executor.prepare_one(sample_id=sample, **common); executor.execute_one(sample_id=sample, allow_remote=True, **common)
    sample_two = common["output_root"] / "sample-02"; control = json.loads((sample_two / "adapter-stdout.bin").read_text()); control["result"]["runtime"]["request_id_hash"] = f"{1:064x}"; raw_control = json.dumps(control, sort_keys=True, separators=(",", ":")).encode(); (sample_two / "adapter-stdout.bin").write_bytes(raw_control); (sample_two / "adapter-control-envelope.json").write_bytes(executor.canonical(control)); (sample_two / "runtime-identity.json").write_bytes(executor.canonical(control["result"]["runtime"])); receipt = json.loads((sample_two / "execution-receipt.json").read_text()); receipt["runtime"] = control["result"]["runtime"]; receipt["adapter_stdout_sha256"] = executor.sha256(raw_control); (sample_two / "execution-receipt.json").write_bytes(executor.canonical(receipt))
    with pytest.raises(ValueError, match="identity is duplicated"):
        executor.freeze_all_ten(output_root=common["output_root"], manifest_path=tmp_path / "duplicate.json")
    parent, parent_raw_hash, parent_prep_hash = _fixture_preparation(tmp_path / "parent.json")
    _patch_fixture(monkeypatch, parent, parent_raw_hash, parent_prep_hash)
    def identical(_broker, _route_value, _request, _capture_path):
        content = {"descendant_instruction_base64": base64.b64encode(b"parent instruction").decode(), "descendant_profile_base64": base64.b64encode(executor.canonical({"parent": True})).decode()}; runtime = {"adapter_version": 1, "request_id_hash": "1" * 64, "session_id_hash": "2" * 64}; result = {"schema_version": 1, "output": content, "output_hash": executor.sha256(executor.canonical(content)), "runtime": runtime}; return SimpleNamespace(state="completed", detail=None, result=result), json.dumps({"control": {"version": 1, "state": "completed"}, "result": result}, sort_keys=True, separators=(",", ":")).encode()
    monkeypatch.setattr(executor, "_adapter_once", identical); single = {**common, "output_root": tmp_path / "single", "dspy_input_preparation_path": parent}
    executor.prepare_one(sample_id=1, **single)
    assert executor.execute_one(sample_id=1, allow_remote=True, **single)["kind"] == "reconcile_required_after_process_launch"


def test_definite_precontact_control_is_persisted_zero_contact_and_root_is_stranded(monkeypatch, tmp_path: Path):
    preparation, raw_hash, prep_hash = _fixture_preparation(tmp_path / "dspy-descendant-input-preparation.json"); _patch_fixture(monkeypatch, preparation, raw_hash, prep_hash)
    def no_contact(_broker, _route_value, _request, _capture_path):
        control = {"control": {"version": 1, "state": "definitely_not_contacted", "detail": "fixture unavailable"}}
        return SimpleNamespace(state="definitely_not_contacted", detail="fixture unavailable", result=None), json.dumps(control, sort_keys=True, separators=(",", ":")).encode()
    monkeypatch.setattr(executor, "_adapter_once", no_contact); common = {"output_root": tmp_path / "out", "dspy_input_preparation_path": preparation, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": AUTH}
    executor.prepare_one(sample_id=1, **common); result = executor.execute_one(sample_id=1, allow_remote=True, **common)
    assert result["native_endpoint_contact_cardinality"] == "zero" and result["provider_calls_made"] == 0
    assert (common["output_root"] / "sample-01" / "adapter-stdout.bin").read_bytes()
    with pytest.raises(ValueError, match="forbids resend"):
        executor.execute_one(sample_id=1, allow_remote=True, **common)


def test_adapter_command_uses_broker_protocol_and_invalid_descendant_bytes_are_rejected(tmp_path: Path):
    route = {"command": ["python", str(executor.GROK_ADAPTER_PATH)], "grok_command": ["grok"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "grok_command_identity": {"version": 1, "artifacts": []}, "cli_version_command": ["grok", "--version"], "cli_version_identity": {"version": 1, "artifacts": []}, "grok_cli_version": "grok 1.0.13", "subscription_receipt_hash": "f" * 64, "timeout_seconds": 30, "nonvisual_max_turns": 1}
    broker = SimpleNamespace(root=tmp_path, _load_json_artifact=lambda _: {"schema_version": 1})
    command = executor._adapter_command(broker, route, json.loads(executor._schema()))["command"]
    assert command[:2] == route["command"] and command[command.index("--nonvisual-max-turns") + 1] == "1"
    route["nonvisual_max_turns"] = 4
    with pytest.raises(ValueError, match="turn bound drifted"):
        executor._adapter_command(broker, route, json.loads(executor._schema()))
    preparation, _, _ = _fixture_preparation(tmp_path / "dspy.json")
    value = json.loads(preparation.read_text())
    malformed = {"descendant_instruction_base64": base64.b64encode(b"ok").decode(), "descendant_profile_base64": base64.b64encode(b"\xff").decode()}
    with pytest.raises(ValueError, match="descendant bytes are invalid"):
        executor._descendant(malformed, value)


def test_adapter_once_reads_wrapper_capture_for_nonzero_timeout_and_malformed_controls(tmp_path: Path):
    route = {"command": ["python", str(executor.GROK_ADAPTER_PATH)], "grok_command": ["grok"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "grok_command_identity": {"version": 1, "artifacts": []}, "cli_version_command": ["grok", "--version"], "cli_version_identity": {"version": 1, "artifacts": []}, "grok_cli_version": "grok 1.0.13", "subscription_receipt_hash": "f" * 64, "timeout_seconds": 30, "nonvisual_max_turns": 1}
    class Broker:
        root = tmp_path
        _load_json_artifact = staticmethod(lambda _: {"schema_version": 1})
        def _run_subprocess(self, wrapper_route, _request, parser):
            capture = Path(wrapper_route["command"][wrapper_route["command"].index("--capture-path") + 1])
            capture.write_bytes(b"wrapper-captured")
            return SimpleNamespace(state="ambiguous", detail="fixture terminal", result=None)
    broker = Broker()
    outcome, raw = executor._adapter_once(broker, route, {"prompt": "fixture"}, tmp_path / "capture.bin")
    assert outcome.state == "ambiguous" and raw == b"wrapper-captured"


def test_broker_job_timeout_kills_capture_wrapper_child_without_orphan(tmp_path: Path):
    broker = executor._native()._load_broker_class()(tmp_path)
    started, survived, capture = tmp_path / "started", tmp_path / "survived", tmp_path / "capture.bin"
    child = f"from pathlib import Path; import time; Path(r'{started}').write_text('started'); time.sleep(5.0); Path(r'{survived}').write_text('survived')"
    route = {"adapter": "grok_exec", "command": [sys.executable, str(executor.CAPTURE_WRAPPER_PATH), "--capture-path", str(capture), "--", sys.executable, "-c", child], "timeout_seconds": 3.0}
    outcome = broker._run_subprocess(route, {"prompt": "fixture"}, lambda _: SimpleNamespace(state="completed", detail=None, result={}))
    assert outcome.state == "ambiguous"
    deadline = time.monotonic() + 0.7
    while not started.exists() and time.monotonic() < deadline: time.sleep(0.02)
    assert started.exists()
    time.sleep(1.0)
    assert not survived.exists()


def test_capture_wrapper_passes_inherited_stdin_bytes_exactly(tmp_path: Path):
    capture = tmp_path / "stdin.bin"
    payload = b"governed-request\\x00with-binary\\n"
    completed = subprocess.run([sys.executable, str(executor.CAPTURE_WRAPPER_PATH), "--capture-path", str(capture), "--", sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"], input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    assert completed.returncode == 0
    assert completed.stdout == payload
    assert capture.read_bytes() == payload


def test_broker_forced_early_timeout_never_leaves_wrapper_child(tmp_path: Path):
    broker = executor._native()._load_broker_class()(tmp_path)
    for index in range(3):
        survived, capture = tmp_path / f"survived-{index}", tmp_path / f"capture-{index}.bin"
        child = f"from pathlib import Path; import time; time.sleep(0.7); Path(r'{survived}').write_text('survived')"
        route = {"adapter": "grok_exec", "command": [sys.executable, str(executor.CAPTURE_WRAPPER_PATH), "--capture-path", str(capture), "--", sys.executable, "-c", child], "timeout_seconds": 0.03}
        outcome = broker._run_subprocess(route, {"prompt": "fixture"}, lambda _: SimpleNamespace(state="completed", detail=None, result={}))
        assert outcome.state == "ambiguous"
        time.sleep(0.9)
        assert not survived.exists()


def test_capture_wrapper_tees_success_nonzero_and_malformed_stdout_exactly(tmp_path: Path):
    def invoke(name: str, code: str) -> tuple[int, bytes, bytes]:
        capture = tmp_path / f"{name}.bin"
        completed = subprocess.run([sys.executable, str(executor.CAPTURE_WRAPPER_PATH), "--capture-path", str(capture), "--", sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        return completed.returncode, completed.stdout, capture.read_bytes()
    assert invoke("success", "import sys; sys.stdout.buffer.write(b'success')") == (0, b"success", b"success")
    assert invoke("nonzero", "import sys; sys.stdout.buffer.write(b'nonzero'); raise SystemExit(9)") == (9, b"nonzero", b"nonzero")
    assert invoke("malformed", "import sys; sys.stdout.buffer.write(b'not-json')") == (0, b"not-json", b"not-json")
