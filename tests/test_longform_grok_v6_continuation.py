"""Synthetic continuation witnesses; no provider or production gate is used."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path.home() / ".codex/tools"
sys.path.insert(0, str(TOOLS))
from model_work_queue import test_grok_adapter as synthetic


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


w = load("test_p4_v6_continuation", ROOT / "evaluation-results/hbq-longform-dependency-pilot-v1/collector_longform_v6.py")


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(w.canonical(value))


@pytest.fixture
def prefix(tmp_path):
    source = tmp_path / "original"; source.mkdir()
    root = tmp_path / "frozen"; root.mkdir()
    rows = [{"endpoint": "grok", "endpoint_ordinal": i,
             "logical_sample_id": w.digest(str(i).encode())} for i in range(1, 233)]
    manifest = {"requests": rows, "artifacts": {}}; put(root / "manifest.json", manifest)
    (source / "frozen-manifest.json").write_bytes((root / "manifest.json").read_bytes())
    binding = {"manifest_sha256": w.MANIFEST_SHA, "route": {}, "payload_classification": "public_synthetic"}
    put(source / "job.json", binding); job_sha = w.digest((source / "job.json").read_bytes())
    first = w.c.sample_path(source, rows[0]); second = w.c.sample_path(source, rows[1])
    first.mkdir(); second.mkdir()
    accepted = {"state": "accepted", "native_thread_id": str(uuid.uuid4())}
    put(first / "terminal.json", accepted)
    negative = {"state": "definitely_not_contacted", "no_resend": True,
                "logical_sample_id": rows[1]["logical_sample_id"], "manifest_sha256": w.MANIFEST_SHA,
                "job_sha256": job_sha}
    native = {"state": "definitely_not_contacted", "result": None, "failure": {
        "category": "gate_error", "code": "nonvisual_prompt_too_large", "provider": "xai_grok_build",
        "account_class": "subscription", "status": None, "provider_error_type": None}}
    put(second / "terminal.json", negative); put(second / "native-result.json", native)
    pins = {"job": job_sha, "accepted_terminal": w.digest((first / "terminal.json").read_bytes()),
            "negative_terminal": w.digest((second / "terminal.json").read_bytes()),
            "negative_native": w.digest((second / "native-result.json").read_bytes())}
    def replay(sample, row, *args):
        return json.loads((sample / "terminal.json").read_bytes()), None
    return source, root, rows, manifest, binding, pins, replay


def test_positive_no_contact_only_and_ambiguous_refusal(prefix):
    source, _, rows, _, binding, pins, _ = prefix
    second = w.c.sample_path(source, rows[1])
    result = w.verify_negative(second, rows[1], binding, pins=pins)
    assert result["same_logical_slot"] and result["new_vote"] is False
    (second / "attempt-started.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="prohibits recovery"):
        w.verify_negative(second, rows[1], binding, pins=pins)
    (second / "attempt-started.json").unlink()
    native = json.loads((second / "native-result.json").read_bytes()); native["state"] = "ambiguous"
    put(second / "native-result.json", native)
    updated = {**pins, "negative_native": w.digest((second / "native-result.json").read_bytes())}
    with pytest.raises(ValueError, match="disposition conflicts"):
        w.verify_negative(second, rows[1], binding, pins=updated)


def test_source_prefix_never_selects_completed_or_newly_occupied_slot(prefix):
    source, root, rows, manifest, binding, pins, replay = prefix
    with patch.object(w.c, "job_binding", return_value=binding), patch.object(w.c, "replay", side_effect=replay):
        result = w.source_prefix(source, manifest, root, None, None, None, TOOLS, pins=pins)
        assert result[0]["disposition"] == "accepted_retained_original"
        assert result[1]["endpoint_ordinal"] == 2
        w.c.sample_path(source, rows[2]).mkdir()
        with pytest.raises(ValueError, match="untouched slot is occupied"):
            w.source_prefix(source, manifest, root, None, None, None, TOOLS, pins=pins)


def test_frozen_plan_keeps_entire_denominator_and_identical_suffix(prefix):
    source, root, rows, manifest, _, _, _ = prefix
    prefix_receipts = [{"native_thread_id": str(uuid.uuid4())}, {"endpoint_ordinal": 2}]
    with patch.object(w.c, "load_manifest", return_value=(manifest, root, None, None, None)), \
            patch.object(w, "source_prefix", return_value=prefix_receipts):
        plan, *_ = w.build_plan(root / "manifest.json", source, TOOLS)
    assert plan["requests"] == rows[1:]
    assert [r["endpoint_ordinal"] for r in plan["requests"]] == list(range(2, 233))
    assert plan["counts"] == {"full_endpoint_planned": 232, "full_matched_planned": 464,
        "accepted_original_retained": 1, "positive_no_contact_recovery": 1,
        "untouched": 230, "continuation_requests": 231}
    assert plan["execution_authority"] is False


def test_inventory_retains_missing_and_rejects_duplicate_native(prefix, tmp_path):
    _, root, rows, manifest, _, _, _ = prefix
    output = tmp_path / "new"; output.mkdir()
    identity = str(uuid.uuid4())
    plan = {"requests": rows[1:], "source_prefix": [{"native_thread_id": identity}]}
    sample = w.c.sample_path(output, rows[1]); sample.mkdir()
    with patch.object(w.c, "replay", return_value=({"state": "ambiguous"}, None)):
        pending, states = w.inventory(output, plan, manifest, {}, root, None, None, None)
    assert states == ["accepted_retained_original", "ambiguous"] and len(pending) == 230
    with patch.object(w.c, "replay", return_value=({"state": "accepted", "native_thread_id": identity}, None)):
        with pytest.raises(ValueError, match="Duplicate own native"):
            w.inventory(output, plan, manifest, {}, root, None, None, None)
    w.c.sample_path(output, rows[0]).mkdir()
    with patch.object(w.c, "replay", return_value=({"state": "semantic_rejected"}, None)):
        with pytest.raises(ValueError, match="never be recreated"):
            w.inventory(output, plan, manifest, {}, root, None, None, None)


def test_execution_interpreter_must_match_frozen_ast_profile(prefix):
    _, root, _, manifest, _, _, _ = prefix
    derived, _ = w.profile(TOOLS)
    route = {"nonvisual_transport_contract": derived.CONTRACT_NAME, "capabilities": [derived.CONTRACT_NAME],
             "nonvisual_max_turns": 1, "timeout_seconds": 900, "zero_charge": True,
             "command": ["C:/Python314/python.exe", str(w.V6_ROOT / "adapters/grok_exec.py"), "--tools-root", str(TOOLS)]}
    with pytest.raises(ValueError, match="interpreter must match"):
        w.job_binding({"python_runtime": w.python_runtime()}, "synthetic", manifest, root, route, TOOLS)


@pytest.fixture
def native_sample(tmp_path):
    fixture = synthetic.GrokAdapterTests(methodName="runTest"); fixture.setUp()
    derived, commitment = w.profile(TOOLS)
    fixture.broker = derived.load_broker().Broker(fixture.root, grok_host_gate_path=fixture.grok_host_gate)
    route = fixture.route(timeout_seconds=900)
    command = [sys.executable, str(w.V6_ROOT / "adapters/grok_exec.py"), "--tools-root", str(TOOLS)]
    route.update(command=command, command_identity=fixture.identity(command), nonvisual_transport_contract=derived.CONTRACT_NAME)
    route["capabilities"].append(derived.CONTRACT_NAME); fixture.write_route(route)
    root = tmp_path / "frozen"; root.mkdir(); output = tmp_path / "output"; output.mkdir()
    source = b"A synthetic full source with a complete ending."
    context = b'{"completion_status": "complete_work"}'
    prompt = source + b"\n" + context + b"\nSynthetic instructions only."
    schema = w.canonical({"$schema_version": 1, "type": "object"})
    files = {"source.txt": source, "context.json": context, "prompt.txt": prompt, "schema.json": schema}
    artifacts = {k: w.c.p.metadata(k, raw) for k, raw in files.items()}
    for name, raw in files.items(): (root / name).write_bytes(raw)
    row = {"endpoint": "grok", "endpoint_ordinal": 2, "logical_sample_id": w.digest(b"fixture logical slot"),
        "work_id": "synthetic", "artifact_id": "synthetic", "arm": "holistic", "contract": "whole_work_baseline",
        "context_arm": "raw_full", "prompt_path": "prompt.txt", "prompt_bytes": len(prompt), "prompt_sha256": w.digest(prompt),
        "schema_path": "schema.json", "schema_bytes": len(schema), "schema_sha256": w.digest(schema),
        "sources": [{**artifacts["source.txt"], "input_path": "source.txt", "id": "synthetic"}],
        "task_context": artifacts["context.json"], "target_original": artifacts["source.txt"]}
    manifest = {"artifacts": artifacts, "requests": [row]}
    binding = {"policy": w.POLICY, "manifest_sha256": w.MANIFEST_SHA, "route": route,
        "route_sha256": w.digest(w.canonical(route).rstrip(b"\n")), "runtime": {"model": "grok-4.7", "reasoning": "high"},
        "tools_root_local_only": str(TOOLS), "v6_execution_profile": commitment, "v6_entry_sha256s": w.V6_PINS,
        "source_prefix": [{"native_thread_id": str(uuid.uuid4())}]}
    put(output / "job.json", binding)
    class Validator:
        def semantic_validate(self, *args, **kwargs):
            return {"accepted": True, "abstention": False, "mock_only": True}
    validator = Validator()
    yield fixture, root, output, row, manifest, binding, validator
    fixture.tearDown()


def test_complete_native_v6_is_replayable_without_new_contact(native_sample):
    fixture, root, output, row, manifest, binding, validator = native_sample
    assert w.c.collect_one(row, manifest, binding, root, output, None, validator, None, broker=fixture.broker) == "accepted"
    sample = w.c.sample_path(output, row)
    terminal_before = (sample / "terminal.json").read_bytes()
    terminal, answer = w.c.replay(sample, row, manifest, binding, root, None, None, validator)
    assert terminal["state"] == "accepted" and answer == {"answer": "ok"}
    assert (sample / "terminal.json").read_bytes() == terminal_before
    terminal, _ = w.c.replay(sample, row, manifest, binding, root, None, None, validator)
    assert terminal["state"] == "accepted"


def test_full_parser_rejects_wrong_contract_version_and_own_start(native_sample):
    fixture, root, output, row, manifest, binding, validator = native_sample
    assert w.c.collect_one(row, manifest, binding, root, output, None, validator, None, broker=fixture.broker) == "accepted"
    sample = w.c.sample_path(output, row); raw = (sample / "native-result.json").read_bytes()
    prompt, schema, *_ = w.c.inputs(root, manifest, row)
    for change in ["version", "contract", "prompt"]:
        value = json.loads(raw)
        if change == "version": value["result"]["runtime"]["adapter_version"] = 5
        elif change == "contract": value["result"]["runtime"]["execution_contract"]["nonvisual_transport_contract"]["updates_bytes"] += 1
        else: value["result"]["runtime"]["execution_contract"]["staged_prompt_sha256"] = "0" * 64
        put(sample / "native-result.json", value)
        with pytest.raises(ValueError): w.strict_native_answer(sample, row, binding, prompt, schema, None)
    (sample / "native-result.json").write_bytes(raw)
    started = json.loads((sample / "attempt-started.json").read_bytes()); started["session_id"] = str(uuid.uuid4())
    put(sample / "attempt-started.json", started)
    with pytest.raises(ValueError, match="started/session"):
        w.strict_native_answer(sample, row, binding, prompt, schema, None)


def test_raw_full_source_snapshot_cannot_be_substituted(native_sample):
    _, root, _, row, manifest, _, _ = native_sample
    altered = copy.deepcopy(row); raw = b"A shorter substitute."
    (root / "substitute.txt").write_bytes(raw)
    meta = w.c.p.metadata("substitute.txt", raw); manifest["artifacts"]["substitute.txt"] = meta
    altered["sources"][0].update(meta, input_path="substitute.txt")
    with pytest.raises(ValueError): w.c.inputs(root, manifest, altered)


def test_stop_current_settles_semantic_missing_continues_native_failure_stops(tmp_path):
    output = tmp_path / "out"; output.mkdir()
    rows = [{"endpoint_ordinal": i, "contract": "synthetic"} for i in range(2, 6)]
    calls = []
    def contact(row, *args, **kwargs):
        calls.append(row["endpoint_ordinal"])
        return {2: "semantic_rejected", 3: "accepted", 4: "ambiguous"}[row["endpoint_ordinal"]]
    with patch.object(w.c, "grok_contact_allowed", return_value=False), patch.object(w.c, "collect_one", side_effect=contact):
        assert w.execute(output, rows, {}, {"route": {}}, tmp_path, None, None, None, object()) == 3
    assert calls == []
    with patch.object(w.c, "grok_contact_allowed", return_value=True), patch.object(w.c, "collect_one", side_effect=contact):
        assert w.execute(output, rows, {}, {"route": {}}, tmp_path, None, None, None, object()) == 3
    assert calls == [2, 3, 4]
    calls.clear()
    def settling(row, *args, **kwargs):
        calls.append(row["endpoint_ordinal"]); (output / "STOP").write_bytes(b"stop")
        return "accepted"
    with patch.object(w.c, "grok_contact_allowed", return_value=True), patch.object(w.c, "collect_one", side_effect=settling), patch.object(w.c.t, "note_stop"):
        assert w.execute(output, rows, {}, {"route": {}}, tmp_path, None, None, None, object()) == 3
        assert calls == [2]
        calls.clear()
        assert w.execute(output, rows, {}, {"route": {}}, tmp_path, None, None, None, object()) == 3
        assert calls == []
