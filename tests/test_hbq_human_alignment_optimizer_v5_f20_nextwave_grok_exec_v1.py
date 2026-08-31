from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import shutil
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-exec-v1"
SOURCE = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-live-856451a-20260830a")
ACK = "a" * 64


def _module():
    spec = importlib.util.spec_from_file_location("_f20_nextwave_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def _route(_queue: Path):
    return ({"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "grok_command": ["fixture"], "allowed_payload_classes": ["public_repo"], "timeout_seconds": 5.0}, {"route": "fixture"})


def _runner(**kwargs):
    prompt, output_dir, route = kwargs["prompt"], kwargs["output_dir"], kwargs["route"]
    responses = output_dir / "responses"; responses.mkdir(); (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
    kwargs["before_contact"](); token = hashlib.sha256(prompt + str(output_dir).encode()).hexdigest()
    instruction = "Versioned descendant " + token[:12]
    profile = json.loads((output_dir / "parent-profile.json").read_bytes()); profile["instruction_sha256"] = hashlib.sha256(instruction.encode()).hexdigest()
    descendant = {"instruction": instruction, "profile": profile, "change_summary": "fixture descendant"}
    content = json.dumps(descendant, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    envelope = {"requestId": "request-" + token, "sessionId": "session-" + token, "modelUsage": {"grok-4.6-build": {}}, "structuredOutput": descendant}
    raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(); (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(raw)
    identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Generate an isolated structured descendant. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 5.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False}
    request = json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"native_request_bytes": request, "native_response_bytes": raw, "content": content, "identity": identity, "effective_settings": settings}


def _prepared(module, tmp_path: Path):
    common = {"output_root": tmp_path / "roots", "source_root": SOURCE, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": _route}
    return common, module.prepare_all(**common)


def test_prepare_pins_f20_and_freezes_ten_distinct_tool_free_prompts(tmp_path: Path):
    module = _module(); common, result = _prepared(module, tmp_path)
    assert result["provider_calls_made"] == result["process_launches"] == 0 and len(result["prepared_cells"]) == 10
    catalog = json.loads((common["output_root"] / "catalog.json").read_bytes())
    assert catalog["public_result_commit"] == module.PUBLIC_RESULT_COMMIT and len(catalog["cells"]) == 10
    assert len({row["brief_sha256"] for row in catalog["cells"]}) == len({row["prompt_sha256"] for row in catalog["cells"]}) == 10
    for row in catalog["cells"]:
        root = common["output_root"] / row["cell_id"]
        assert set(path.name for path in root.iterdir()) == module.PREPARED
        prepared = json.loads((root / "prepared.json").read_bytes())
        assert prepared["source"]["public_result_sha256"] == module.PUBLIC_RESULT_SHA256
        parent = prepared["source"]["parent"]
        assert hashlib.sha256((root / "parent-outbound-payload.json").read_bytes()).hexdigest() == parent["outbound_payload_sha256"]
    with pytest.raises(ValueError): module.prepare_all(**common)


def test_real_runner_order_one_shot_and_parent_identical_rejection(tmp_path: Path):
    module = _module(); common, result = _prepared(module, tmp_path); cell = result["prepared_cells"][0]
    received = module.execute_one(**common, cell_id=cell, allow_remote=True, runner=_runner)
    assert received["state"] == "provisional_candidate_received" and received["native_endpoint_contact_cardinality"] == "unproven"
    root = common["output_root"] / cell
    assert (root / "responses" / "batch-0001.attempt-0001.prompt.txt").read_bytes() == (root / "prompt-request.bin").read_bytes()
    with pytest.raises(ValueError, match="no resend"): module.execute_one(**common, cell_id=cell, allow_remote=True, runner=_runner)
    def identical(**kwargs):
        value = _runner(**kwargs); parent_instruction = (kwargs["output_dir"] / "parent-instruction.bin").read_text(); parent_profile = json.loads((kwargs["output_dir"] / "parent-profile.json").read_bytes())
        content = {"instruction": parent_instruction, "profile": parent_profile, "change_summary": "same"}; value["content"] = json.dumps(content, sort_keys=True, separators=(",", ":")).encode(); return value
    rejected = module.execute_one(**common, cell_id=result["prepared_cells"][1], allow_remote=True, runner=identical)
    assert rejected["kind"] == "reconcile_required_after_process_launch"
    def envelope_mismatch(**kwargs):
        value = _runner(**kwargs); envelope = json.loads(value["native_response_bytes"]); envelope["structuredOutput"]["change_summary"] = "different"; value["native_response_bytes"] = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(); return value
    mismatch = module.execute_one(**common, cell_id=result["prepared_cells"][2], allow_remote=True, runner=envelope_mismatch)
    assert mismatch["kind"] == "reconcile_required_after_process_launch"
    def minimal_profile(**kwargs):
        value = _runner(**kwargs); descendant = json.loads(value["content"]); descendant["profile"] = {"format_version": 1}; value["content"] = json.dumps(descendant, sort_keys=True, separators=(",", ":")).encode(); envelope = json.loads(value["native_response_bytes"]); envelope["structuredOutput"] = descendant; value["native_response_bytes"] = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(); return value
    malformed = module.execute_one(**common, cell_id=result["prepared_cells"][3], allow_remote=True, runner=minimal_profile)
    assert malformed["kind"] == "reconcile_required_after_process_launch"
    def changed_profile(field, value):
        def runner(**kwargs):
            result = _runner(**kwargs); descendant = json.loads(result["content"]); descendant["profile"][field] = value
            result["content"] = json.dumps(descendant, sort_keys=True, separators=(",", ":")).encode(); envelope = json.loads(result["native_response_bytes"]); envelope["structuredOutput"] = descendant; result["native_response_bytes"] = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(); return result
        return runner
    assert module.execute_one(**common, cell_id=result["prepared_cells"][4], allow_remote=True, runner=changed_profile("demonstrations", 1))["kind"] == "reconcile_required_after_process_launch"
    assert module.execute_one(**common, cell_id=result["prepared_cells"][5], allow_remote=True, runner=changed_profile("fixed_mapping", "different mapping"))["kind"] == "reconcile_required_after_process_launch"
    assert module.execute_one(**common, cell_id=result["prepared_cells"][6], allow_remote=True, runner=changed_profile("immutable_cwr_commitments", {"mapping_sets_sha256": "0" * 64}))["kind"] == "reconcile_required_after_process_launch"


def test_ten_lane_wave_and_tamper_reparse_partial_reject(tmp_path: Path):
    module = _module(); common, _result = _prepared(module, tmp_path); active = maximum = 0
    def concurrent(**kwargs):
        nonlocal active, maximum
        active += 1; maximum = max(maximum, active)
        try:
            time.sleep(0.02); return _runner(**kwargs)
        finally: active -= 1
    rows = asyncio.run(module.execute_wave(**common, allow_remote=True, runner=concurrent))
    assert len(rows) == 10 and 1 <= maximum <= 10 and all(row["state"] == "provisional_candidate_received" for row in rows)
    assert module.reconcile_all(output_root=common["output_root"], source_root=SOURCE, queue_root=common["queue_root"], authorization_acknowledgement_sha256=ACK)["cells"] == 10
    coherent = common["output_root"] / rows[2]["cell_id"]; new_prompt = b'{"coherently":"rewritten"}\n'; (coherent / "responses" / "batch-0001.attempt-0001.prompt.txt").write_bytes(new_prompt)
    request = json.dumps({"prompt": new_prompt.decode()}, sort_keys=True, separators=(",", ":")).encode(); (coherent / "native-request.bin").write_bytes(request)
    settings = json.loads((coherent / "effective-settings.json").read_bytes()); settings["runner_prompt_artifact_sha256"] = hashlib.sha256(new_prompt).hexdigest(); (coherent / "effective-settings.json").write_bytes(module.canonical(settings))
    row = next(row for row in module._catalog(SOURCE)[0] if row["cell_id"] == coherent.name); prepared = json.loads((coherent / "prepared.json").read_bytes()); frozen = (coherent / "prompt-request.bin").read_bytes(); intent = {"format_version": 1, "study_id": module.STUDY_ID, "kind": "intent_before_grok_candidate_generation", "cell_id": coherent.name, "prepared_sha256": module.sha256(prepared), "prompt_sha256": module.sha256(frozen), "native_contact_proven": False}; content = (coherent / "descendant-result.json").read_bytes(); descendant = json.loads(content); response = (coherent / "native-response.bin").read_bytes(); identity = json.loads((coherent / "runtime-identity.json").read_bytes())
    receipt, final = module._completed_records(row, prepared, intent, new_prompt, request, response, content, descendant, identity, settings); (coherent / "execution-receipt.json").write_bytes(module.canonical(receipt)); (coherent / "result.json").write_bytes(module.canonical(final))
    with pytest.raises(ValueError, match="runner prompt"): module.reconcile_all(output_root=common["output_root"], source_root=SOURCE, queue_root=common["queue_root"], authorization_acknowledgement_sha256=ACK)
    (coherent / "responses" / "batch-0001.attempt-0001.prompt.txt").write_bytes(frozen)
    (coherent / "native-request.bin").write_bytes(json.dumps({"prompt": frozen.decode()}, sort_keys=True, separators=(",", ":")).encode())
    settings["runner_prompt_artifact_sha256"] = hashlib.sha256(frozen).hexdigest(); (coherent / "effective-settings.json").write_bytes(module.canonical(settings)); receipt, final = module._completed_records(row, prepared, intent, frozen, (coherent / "native-request.bin").read_bytes(), response, content, descendant, identity, settings); (coherent / "execution-receipt.json").write_bytes(module.canonical(receipt)); (coherent / "result.json").write_bytes(module.canonical(final))
    first, second = (common["output_root"] / rows[0]["cell_id"], common["output_root"] / rows[1]["cell_id"])
    original = (first / "runtime-identity.json").read_bytes(); (first / "runtime-identity.json").write_bytes((second / "runtime-identity.json").read_bytes())
    with pytest.raises(ValueError, match="misassociated|duplicate|receipt"): module.reconcile_all(output_root=common["output_root"], source_root=SOURCE, queue_root=common["queue_root"], authorization_acknowledgement_sha256=ACK)
    (first / "runtime-identity.json").write_bytes(original)
    module2 = _module(); common2, result2 = _prepared(module2, tmp_path / "tamper"); root = common2["output_root"] / result2["prepared_cells"][0]
    (root / "prompt-request.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError): module2.execute_one(**common2, cell_id=result2["prepared_cells"][0], allow_remote=True, runner=_runner)
    assert not (root / "launch-intent.json").exists()
    root2 = common2["output_root"] / result2["prepared_cells"][1]; (root2 / "orphan.bin").write_bytes(b"x")
    with pytest.raises(ValueError): module2.execute_one(**common2, cell_id=result2["prepared_cells"][1], allow_remote=True, runner=_runner)
    assert not (root2 / "launch-intent.json").exists()


def test_source_payload_disjoint_root_and_closed_world_rejections(tmp_path: Path):
    module = _module(); partial_source = tmp_path / "source"
    partial_source.mkdir()
    for cell in (module.BASELINE_CELL, module.BEST_CELL):
        target = partial_source / cell; target.mkdir()
        for name in ("prepared.json", "outbound-payload.json"): shutil.copy2(SOURCE / cell / name, target / name)
    route = _route
    with pytest.raises(ValueError, match="disjoint"):
        module.prepare_all(output_root=tmp_path / "queue" / "roots", source_root=partial_source, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, route_provider=route)
    (partial_source / module.BASELINE_CELL / "outbound-payload.json").write_bytes((partial_source / module.BASELINE_CELL / "outbound-payload.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="payload"): module.prepare_all(output_root=tmp_path / "roots", source_root=partial_source, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, route_provider=route)
    module2 = _module(); common, _result = _prepared(module2, tmp_path / "closed")
    (common["output_root"] / "unexpected-top-level.bin").write_bytes(b"x")
    with pytest.raises(ValueError, match="top-level"): module2.execute_one(**common, cell_id="nextwave-01-baseline-local-evidence", allow_remote=True, runner=_runner)


def test_no_runtime_optimizer_dependency():
    text = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in text and "import optuna" not in text
