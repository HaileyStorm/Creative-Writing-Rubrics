from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v4"
PUBLIC = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1-public-result-v1"
LIVE_V3_STDOUT_FIXTURE = PACKAGE / "fixtures" / "v3-sample-01-adapter-stdout.base64"
LIVE_V3_ROOT = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-v3-a1f9467-r4shrink-20260830a\r4shrink-20260830a-sample-01")
executor = load_module(PACKAGE / "executor.py", name="feedback_grok_v4")
ACK = "a" * 64


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _preparation() -> tuple[bytes, dict]:
    inputs = {
        "parent_candidate_id": "baseline",
        "parent_instruction_base64": _b64(b"baseline instruction"),
        "parent_profile_base64": _b64(executor.canonical({"parent": True})),
        "training_result_base64": _b64(b"{}"),
        "training_diagnostics_base64": _b64(b"{}"),
    }
    value = {"inputs": inputs, "preparation_sha256": "b" * 64}
    return executor.canonical(value), value


def _feedback(tmp_path: Path, *, wave_id: str = "r4shrink-replacement-v4-test") -> tuple[Path, bytes]:
    producer = {
        "study_contract_path": str(PUBLIC / "study-contract.json"),
        "study_contract_sha256": executor.PUBLIC_AUTHORITY["feedback-producer-contract.json"],
        "producer_source_path": str(PUBLIC / "materialize.py"),
        "producer_source_sha256": executor.PUBLIC_AUTHORITY["feedback-producer-source.bin"],
        "selection_schema_path": str(PUBLIC / "selection-schema.json"),
        "selection_schema_sha256": executor.PUBLIC_AUTHORITY["feedback-selection-schema.json"],
        "result_schema_path": str(PUBLIC / "result-schema.json"),
        "result_schema_sha256": executor.PUBLIC_AUTHORITY["feedback-result-schema.json"],
    }
    artifacts = {
        "selection_path": str(PUBLIC / "feedback-selection.json"),
        "selection_sha256": executor.PUBLIC_AUTHORITY["feedback-selection.json"],
        "result_path": str(PUBLIC / "feedback-result.json"),
        "result_sha256": executor.PUBLIC_AUTHORITY["feedback-result.json"],
    }
    value = {
        "format_version": 1,
        "kind": "hanna_r4_two_phase_feedback",
        "study_id": executor.PUBLIC_STUDY_ID,
        "wave_id": wave_id,
        "seed": 202608302,
        "public_result_summary": executor.PUBLIC_SUMMARY,
        "producer": producer,
        "artifacts": artifacts,
    }
    raw = executor.canonical(value)
    path = tmp_path / f"{wave_id}.json"
    path.write_bytes(raw)
    return path, raw


def _route() -> tuple[dict, dict]:
    identity: dict = {}
    route = {
        "name": "grok-build-grok-4.6",
        "provider": "xai_grok_build",
        "model": "grok-4.6",
        "reported_model": "grok-4.6-build",
        "reasoning_effort": "high",
        "adapter": "grok_exec",
        "destination": "xai_grok_build_subscription",
        "grok_command": ["grok.exe"],
        "grok_command_identity": identity,
    }
    evidence = {
        "route_name": route["name"],
        "route_sha256": "3" * 64,
        "grok_cli_version": "fixture",
        "subscription_receipt_hash": "4" * 64,
        "grok_command_identity_sha256": executor.sha256(executor.canonical(identity)),
    }
    return route, evidence


def _native_control(prompt: str, *, request_hash: str | None = None, output_hash: str | None = None) -> tuple[dict, bytes]:
    instruction = b"Assess all six dimensions from local textual evidence."
    profile = executor.adapter_canonical({"instruction_sha256": "", "version": "replacement-v4"})
    output = {"descendant_instruction_base64": _b64(instruction), "descendant_profile_base64": _b64(profile)}
    route, evidence = _route()
    runtime = {
        "adapter_version": 1,
        "requested_model": route["model"],
        "reported_model": route["reported_model"],
        "requested_reasoning_effort": route["reasoning_effort"],
        "reasoning_attested": False,
        "reasoning_attestation": "not_reported_by_grok_build_cli",
        "identity_evidence": "requested_only",
        "execution_policy": "bounded_nonvisual_read_only",
        "nonvisual_max_turns": 1,
        "observed_turns": 1,
        "cli_version": evidence["grok_cli_version"],
        "subscription_receipt_hash": evidence["subscription_receipt_hash"],
        "command_identity": route["grok_command_identity"],
        "command_identity_hash": executor.sha256(executor.adapter_canonical({"adapter_version": 1, "grok_command": route["grok_command"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"]})),
        "envelope_hash": "7" * 64,
        "request_id_hash": "9" * 64,
        "session_id_hash": "8" * 64,
        "usage_telemetry": {"status": "reported", "total_cost_usd": 0.01, "total_cost_usd_ticks": 100000000, "model_cost_usd": 0.01},
    }
    result = {
        "schema_version": 1,
        "request_hash": request_hash or executor.sha256(executor.adapter_canonical({"prompt": prompt})),
        "output": output,
        "output_hash": output_hash or executor.sha256(executor.adapter_canonical(output)),
        "runtime": runtime,
    }
    control = {"control": {"state": "completed", "version": 1}, "result": result}
    return result, (json.dumps(control, ensure_ascii=False, sort_keys=True) + "\r\n").encode("utf-8")


def _fake_v2(*, drift_after_prepare: bool = False, completed: bool = False, adapter_calls: list[dict] | None = None) -> SimpleNamespace:
    preparation_raw, preparation = _preparation()
    route, evidence = _route()
    route_calls = 0

    def get_route(_queue: Path):
        nonlocal route_calls
        route_calls += 1
        current = {**route, "destination": "drifted"} if drift_after_prepare and route_calls > 1 else dict(route)
        return SimpleNamespace(), SimpleNamespace(), current, dict(evidence)

    def adapter_once(_broker, _route, request, _capture):
        if adapter_calls is not None:
            adapter_calls.append(dict(request))
        if not completed:
            raw = executor.canonical({"control": {"version": 1, "state": "definitely_not_contacted"}})
            return SimpleNamespace(state="definitely_not_contacted", detail="fixture precontact", result=None), raw
        result, raw = _native_control(request["prompt"])
        return SimpleNamespace(state="completed", detail=None, result=result), raw

    return SimpleNamespace(
        _contract=lambda: None,
        _preparation=lambda _path: (preparation_raw, preparation),
        _schema=lambda: executor.canonical({"$schema_version": 1, "type": "object"}),
        _decode=lambda value, **_kwargs: base64.b64decode(value.encode("ascii"), validate=True),
        _route=get_route,
        _adapter_once=adapter_once,
    )


def _common(tmp_path: Path, feedback: Path, feedback_raw: bytes) -> dict:
    return {
        "output_root": tmp_path / "roots",
        "sample_id": 1,
        "dspy_input_preparation_path": tmp_path / "prep.json",
        "feedback_path": feedback,
        "feedback_sha256": executor.sha256(feedback_raw),
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
    }


def test_actual_immutable_v3_stdout_presentation_replays_in_adapter_domain() -> None:
    raw = base64.b64decode(LIVE_V3_STDOUT_FIXTURE.read_bytes(), validate=False)
    assert executor.sha256(raw) == "42c8b676f499ec90e9833b92ef32cd341f5479635d42df111531d58fa15f6f90"
    assert raw.endswith(b"\r\n") and raw.startswith(b'{"control": {')
    control = executor._strict_json(raw, "actual v3 fixture")
    assert set(control["result"]["runtime"]) == executor.RUNTIME_KEYS
    if not LIVE_V3_ROOT.is_dir():
        pytest.skip("raw presentation is portable; full immutable preparation fixture is host-local")
    v2 = executor._v3_module._v2()
    _preparation_raw, preparation = v2._preparation(LIVE_V3_ROOT / "dspy-input-preparation.json")
    prepared = json.loads((LIVE_V3_ROOT / "prepared.json").read_bytes())
    _control, _result, output, lineage, runtime = executor._validate_completed_response(v2, raw, control["result"], preparation, (LIVE_V3_ROOT / "prompt-request.bin").read_bytes(), prepared["route"], prepared["route_evidence"])
    raw_instruction = base64.b64decode(output["raw_descendant_instruction_base64"])
    raw_profile = base64.b64decode(output["raw_descendant_profile_base64"])
    derived = base64.b64decode(output["project_canonical_profile_base64"])
    assert output["raw_descendant_instruction_sha256"] == executor.sha256(raw_instruction)
    assert output["raw_descendant_profile_sha256"] == executor.sha256(raw_profile)
    assert derived.endswith(b"\n") and not derived.endswith(b"\n\n")
    assert json.loads(derived)["instruction_sha256"] == executor.sha256(raw_instruction)
    assert output["profile_derivation"]["provider_output_unchanged"] is False
    assert lineage["project_canonical_profile_sha256"] == executor.sha256(derived)
    assert "envelope_hash" not in runtime
    assert runtime["evidence_scope"]["envelope_hash"] == "excluded_native_grok_cli_raw_stdout_not_persisted"
    assert runtime["reasoning_attestation"] == "not_reported_by_grok_build_cli"
    assert runtime["command_identity_hash"] == "42e75c8382b22e8dbb6061c32a39435943fed12547995a5305bdcf4d73583889"
    assert runtime["usage_telemetry"] == {"model_cost_usd": 0.01386282, "status": "reported", "total_cost_usd": 0.01386282, "total_cost_usd_ticks": 138628200}


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}\r\n', b'{"a":NaN}\r\n', b'{"a":Infinity}\r\n', b'{"a":1e309}\r\n', b'{"a":[{"b":-1e309}]}\r\n', b'{"a":'])
def test_strict_json_rejects_duplicates_nonfinite_and_malformed(raw: bytes) -> None:
    with pytest.raises(ValueError):
        executor._strict_json(raw, "fixture")


def test_project_and_adapter_canonicalization_reject_nonfinite_values() -> None:
    for serializer in (executor.canonical, executor.adapter_canonical):
        with pytest.raises(ValueError):
            serializer({"outer": [{"value": float("inf")} ]})


@pytest.mark.parametrize("which", ["request", "output"])
def test_wrong_adapter_domain_hashes_are_rejected(which: str) -> None:
    _raw, preparation = _preparation()
    prompt = b"prompt"
    result, control_raw = _native_control(prompt.decode(), request_hash="f" * 64 if which == "request" else None, output_hash="e" * 64 if which == "output" else None)
    route, evidence = _route()
    with pytest.raises(ValueError, match="adapter canonical commitment"):
        executor._validate_completed_response(SimpleNamespace(), control_raw, result, preparation, prompt, route, evidence)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("runtime_extra", "runtime keyset"),
        ("runtime_missing", "runtime keyset"),
        ("command_identity_hash", "native runtime binding"),
        ("envelope_hash", "runtime identity"),
        ("reasoning_attestation", "native runtime binding"),
        ("telemetry_extra", "usage telemetry schema"),
        ("telemetry_nonfinite", "usage telemetry is non-finite"),
        ("telemetry_ticks", "usage telemetry ticks"),
    ],
)
def test_runtime_evidence_mutations_fail_closed(mutation: str, message: str) -> None:
    _raw, preparation = _preparation()
    prompt = b"prompt"
    _result, control_raw = _native_control(prompt.decode())
    control = json.loads(control_raw)
    runtime = control["result"]["runtime"]
    if mutation == "runtime_extra":
        runtime["unexpected"] = True
    elif mutation == "runtime_missing":
        runtime.pop("reasoning_attestation")
    elif mutation == "command_identity_hash":
        runtime["command_identity_hash"] = "f" * 64
    elif mutation == "envelope_hash":
        runtime["envelope_hash"] = "not-a-hash"
    elif mutation == "reasoning_attestation":
        runtime["reasoning_attestation"] = "reported"
    elif mutation == "telemetry_extra":
        runtime["usage_telemetry"]["unreviewed"] = 1
    elif mutation == "telemetry_nonfinite":
        runtime["usage_telemetry"]["total_cost_usd"] = -1.0
    else:
        runtime["usage_telemetry"]["total_cost_usd_ticks"] = 1.5
    mutated = (json.dumps(control, ensure_ascii=False, sort_keys=True) + "\r\n").encode("utf-8")
    route, evidence = _route()
    with pytest.raises(ValueError, match=message):
        executor._validate_completed_response(SimpleNamespace(), mutated, control["result"], preparation, prompt, route, evidence)


def test_prepare_requires_fresh_identity_and_exact_public_authority(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = _fake_v2()
    monkeypatch.setattr(executor._v3_module, "_v2", lambda: fake)
    feedback, raw = _feedback(tmp_path)
    row = executor.prepare_one(**_common(tmp_path, feedback, raw))
    assert row["sample_id"] == "r4shrink-replacement-v4-test-sample-01"
    assert row["sample_id"] != "r4shrink-20260830a-sample-06"
    prepared = json.loads((tmp_path / "roots" / row["sample_id"] / "prepared.json").read_bytes())
    assert prepared["kind"] == "feedback_bound_grok_v4_preparation" and prepared["package_version"] == 4
    old_feedback, old_raw = _feedback(tmp_path, wave_id=executor.FORBIDDEN_WAVE_ID)
    with pytest.raises(ValueError, match="fresh replacement wave"):
        executor.prepare_one(**{**_common(tmp_path / "old", old_feedback, old_raw), "output_root": tmp_path / "old-roots"})


def test_v4_surface_can_launch_only_fresh_sample_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert not hasattr(executor, "execute_wave")
    assert "--execute-wave" not in (PACKAGE / "README.md").read_text(encoding="utf-8")
    contract = json.loads((PACKAGE / "study-contract.json").read_bytes())
    assert contract["execution"]["replacement_scope"] == "one_fresh_sample_prepare_then_execute_one"
    assert contract["execution"]["sample_id"] == "1_only" and "isolated_wave" not in contract["execution"]
    feedback, raw = _feedback(tmp_path)
    common = {**_common(tmp_path, feedback, raw), "sample_id": 2}
    monkeypatch.setattr(executor._v3_module, "_v2", lambda: _fake_v2(completed=True))
    with pytest.raises(ValueError, match="only fresh replacement sample 1"):
        executor.prepare_one(**common)
    with pytest.raises(ValueError, match="only fresh replacement sample 1"):
        executor.execute_one(**common, allow_remote=True)
    assert not (tmp_path / "roots").exists()
    calls: list[dict] = []
    monkeypatch.setattr(executor, "execute_one", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(SystemExit):
        executor.main(["--execute-wave"])
    assert not calls


def test_completed_spaced_crlf_stdout_preserves_raw_and_records_derived_profile(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []
    fake = _fake_v2(completed=True, adapter_calls=calls)
    monkeypatch.setattr(executor._v3_module, "_v2", lambda: fake)
    feedback, raw = _feedback(tmp_path)
    common = _common(tmp_path, feedback, raw)
    executor.prepare_one(**common)
    row = executor.execute_one(**common, allow_remote=True)
    root = tmp_path / "roots" / row["sample_id"]
    captured = (root / "adapter-stdout.bin").read_bytes()
    assert captured.endswith(b"\r\n") and len(calls) == 1
    receipt = json.loads((root / "execution-receipt.json").read_bytes())
    result = json.loads((root / "result.json").read_bytes())
    assert receipt["adapter_stdout_sha256"] == executor.sha256(captured)
    assert "runtime" not in receipt and "runtime_evidence" in receipt
    assert "envelope_hash" not in receipt["runtime_evidence"]
    assert receipt["runtime_evidence"]["evidence_scope"]["envelope_hash"] == "excluded_native_grok_cli_raw_stdout_not_persisted"
    descendant = result["descendant"]
    assert descendant["profile_derivation"]["provider_output_unchanged"] is False
    assert base64.b64decode(descendant["project_canonical_profile_base64"]).endswith(b"\n")
    with pytest.raises(ValueError, match="forbids resend"):
        executor.execute_one(**common, allow_remote=True)


def test_route_drift_is_zero_contact_terminal_and_never_resends(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict] = []
    fake = _fake_v2(drift_after_prepare=True, completed=True, adapter_calls=calls)
    monkeypatch.setattr(executor._v3_module, "_v2", lambda: fake)
    feedback, raw = _feedback(tmp_path)
    common = _common(tmp_path, feedback, raw)
    executor.prepare_one(**common)
    result = executor.execute_one(**common, allow_remote=True)
    assert result["kind"] == "definitely_not_contacted" and result["provider_calls_made"] == 0 and not calls
    with pytest.raises(ValueError, match="forbids resend"):
        executor.execute_one(**common, allow_remote=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object semantics")
def test_windows_child_owner_terminates_actual_process() -> None:
    async def exercise() -> None:
        child = await asyncio.create_subprocess_exec(__import__("sys").executable, "-c", "import time; time.sleep(30)", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, creationflags=getattr(__import__("subprocess"), "CREATE_NEW_PROCESS_GROUP", 0))
        owner = executor._ChildTreeOwner(child)
        await owner.stop()
        owner.close()
        assert child.returncode is not None
    asyncio.run(exercise())
