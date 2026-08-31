from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-exec-v1"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def module():
    spec = importlib.util.spec_from_file_location("_desc13_nextwave_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def route_provider(counter: dict[str, int] | None = None):
    route = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "grok_command": ["fake-grok"], "allowed_payload_classes": ["public_repo"], "timeout_seconds": 60}
    evidence = {"kind": "fake-current-zero-charge-proof"}
    lock = threading.Lock()
    def provider(_queue: Path):
        if counter is not None:
            with lock:
                counter["active"] = counter.get("active", 0) + 1
                counter["max_active"] = max(counter.get("max_active", 0), counter["active"])
            time.sleep(0.003)
            with lock:
                counter["active"] -= 1; counter["calls"] = counter.get("calls", 0) + 1
        return route, evidence
    return provider


def runner(value, *, duplicate: bool = False, fail_after_contact: bool = False):
    calls = {"count": 0, "schema_ok": 0}
    parent = value._parent(value.DEFAULT_PARENT_PROFILE)
    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        calls["count"] += 1; ordinal = 1 if duplicate else calls["count"]
        assert schema_path.read_bytes() == value.canonical(value._generator_schema_value())
        calls["schema_ok"] += 1
        before_contact()
        if fail_after_contact: raise RuntimeError("postlaunch")
        profile = json.loads(parent["profile"].decode("utf-8"))
        instruction = parent["instruction"].decode("utf-8") + f"\nNextwave local evidence calibration {ordinal}."
        profile["factors"]["missing_evidence_not_no"] += f"\nNextwave conservative evidence calibration {ordinal}."
        profile["instruction_sha256"] = value.sha256(instruction.encode("utf-8"))
        content = value.canonical({"instruction": instruction, "profile": profile, "change_summary": f"conservative local change {ordinal}"})
        response = value.canonical({"requestId": f"request-{ordinal}", "sessionId": f"session-{ordinal}", "structuredOutput": json.loads(content)})
        responses = output_dir / "responses"; responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
        (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": value.TOOL_FREE_ARGV, "system_prompt_override": value.SYSTEM_PROMPT, "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}
        return {"native_request_bytes": value.canonical({"prompt": prompt.decode("utf-8")}).rstrip(b"\n"), "native_response_bytes": response, "content": content, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": f"request-{ordinal}", "session_id": f"session-{ordinal}", "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": settings}
    return run, calls


def prepared(value, tmp_path: Path):
    output = tmp_path / "output"; value.prepare_all(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, route_provider=route_provider())
    return output


def test_parent_bytes_catalog_and_prepare_are_exact_and_provider_free(tmp_path: Path):
    value = module(); parent = value._parent(value.DEFAULT_PARENT_PROFILE); output = prepared(value, tmp_path)
    assert parent["provenance"]["candidate_id"] == value.PARENT_CANDIDATE_ID
    assert parent["provenance"]["outbound_payload_sha256"] == "e48306dd4e4037a2cb2fa3553ec9287c18f496837b818ab097b59fc382a8f9e1"
    assert value.sha256((output / "descendant13-nextwave-01-scale-adjacency" / "parent-outbound-payload.json").read_bytes()) == parent["provenance"]["outbound_payload_sha256"]
    catalog = json.loads((output / "catalog.json").read_text(encoding="utf-8"))
    assert len(catalog["cells"]) == 10
    assert len({cell["brief_sha256"] for cell in catalog["cells"]}) == 10
    assert not ({cell["semantic_label"] for cell in catalog["cells"]} & value.KNOWN_TESTED_MECHANISMS)
    assert len({(cell["target_dimension"], cell["mechanism_family"]) for cell in catalog["cells"]}) == 10
    assert json.loads((output / catalog["cells"][0]["cell_id"] / "response-schema.json").read_text(encoding="utf-8"))["required"] == ["instruction", "profile", "change_summary"]
    assert {cell["parent"]["candidate_id"] for cell in [json.loads((output / row["cell_id"] / "prepared.json").read_text(encoding="utf-8")) for row in catalog["cells"]]} == {value.PARENT_CANDIDATE_ID}
    assert "dspy" not in (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "optuna" not in (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()


def test_wave_is_capped_serializes_route_loading_and_reconciles_without_provider(tmp_path: Path):
    value = module(); output = prepared(value, tmp_path); counter = {}
    fake, calls = runner(value)
    results = asyncio.run(value.execute_wave(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(counter), runner=fake))
    assert len(results) == 10 and calls["count"] == 10
    assert calls["schema_ok"] == 10
    assert counter["max_active"] == 1
    summary = value.reconcile_all(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK)
    assert summary["cells"] == 10 and summary["provider_calls_made"] == 0


def test_postlaunch_failure_is_terminal_and_cannot_be_resent(tmp_path: Path):
    value = module(); output = prepared(value, tmp_path); fake, calls = runner(value, fail_after_contact=True)
    cell = "descendant13-nextwave-01-scale-adjacency"
    result = value.execute_one(output_root=output, cell_id=cell, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake)
    assert result["kind"] == "reconcile_required_after_process_launch" and calls["count"] == 1
    with pytest.raises(ValueError, match="no resend"):
        value.execute_one(output_root=output, cell_id=cell, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake)


def test_duplicate_output_and_prepared_tamper_are_rejected(tmp_path: Path):
    value = module(); output = prepared(value, tmp_path); fake, _calls = runner(value, duplicate=True)
    first = "descendant13-nextwave-01-scale-adjacency"; second = "descendant13-nextwave-02-speaker-attribution"
    assert value.execute_one(output_root=output, cell_id=first, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake)["kind"] == "provisional_grok_candidate_generation_received"
    assert value.execute_one(output_root=output, cell_id=second, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake)["kind"] == "reconcile_required_after_process_launch"
    tampered = tmp_path / "tampered"; value.prepare_all(output_root=tampered, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, route_provider=route_provider())
    path = tampered / first / "parent-profile.json"; path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="prepared bytes drifted"):
        value.execute_one(output_root=tampered, cell_id=first, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake)


def test_parent_path_and_cli_surface_are_bound(tmp_path: Path):
    value = module(); output = tmp_path / "out"
    with pytest.raises(ValueError, match="published parent profile drifted"):
        value.prepare_all(output_root=output, queue_root=tmp_path / "queue", parent_profile=tmp_path / "fake.json", authorization_acknowledgement_sha256=ACK, route_provider=route_provider())
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8")
    assert '"--parent-profile"' in source


def test_reconcile_rejects_terminal_native_and_responses_lifecycle_tampering(tmp_path: Path):
    value = module(); output = prepared(value, tmp_path); fake, _calls = runner(value)
    asyncio.run(value.execute_wave(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake))
    cell = output / "descendant13-nextwave-01-scale-adjacency"
    native = cell / "native-response.bin"; native.write_bytes(b"{}")
    with pytest.raises(ValueError, match="native response"):
        value.reconcile_all(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK)
    native.write_bytes((cell / "responses" / "batch-0001.attempt-0001.grok.envelope.json").read_bytes())
    (cell / "responses" / "batch-0001.attempt-0001.prompt.txt").unlink()
    with pytest.raises(ValueError, match="runner response lifecycle drifted"):
        value.reconcile_all(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK)


def test_reconcile_rejects_effective_settings_tamper(tmp_path: Path):
    value = module(); output = prepared(value, tmp_path); fake, _calls = runner(value)
    asyncio.run(value.execute_wave(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, route_provider=route_provider(), runner=fake))
    path = output / "descendant13-nextwave-01-scale-adjacency" / "effective-settings.json"
    settings = json.loads(path.read_text(encoding="utf-8")); settings["web_search_enabled"] = True; path.write_bytes(value.canonical(settings))
    with pytest.raises(ValueError, match="effective settings drifted"):
        value.reconcile_all(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK)


def test_output_root_inside_repo_is_rejected_before_prepare(tmp_path: Path):
    value = module()
    with pytest.raises(ValueError, match="disjoint"):
        value.prepare_all(output_root=ROOT / "unsafe-output", queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, route_provider=route_provider())
