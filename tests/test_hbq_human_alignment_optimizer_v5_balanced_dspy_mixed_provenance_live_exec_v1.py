from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1"
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
ACK = "a" * 64


def _module():
    spec = importlib.util.spec_from_file_location("_v5_live_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def _route(_root: Path):
    return ({"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "grok_command": ["fixture"], "allowed_payload_classes": ["public_synthetic"], "timeout_seconds": 120}, {"fixture": "route"})


def _runner(**kwargs):
    prompt, output_dir, route = kwargs["prompt"], kwargs["output_dir"], kwargs["route"]
    kwargs["before_contact"](); token = hashlib.sha256(prompt + str(output_dir).encode()).hexdigest(); responses = output_dir / "responses"; responses.mkdir()
    (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"); scores = {key: 3.0 for key in dimensions}
    envelope = {"modelUsage": {"grok-4.6-build": {}}, "requestId": "request-" + token, "sessionId": "session-" + token, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": {"scores": scores, "evidence": {key: "fixture" for key in dimensions}, "coverage": {key: True for key in dimensions}}}
    raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(); (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(raw)
    identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 120.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False}
    return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": raw, "identity": identity, "effective_settings": settings}


def _prepared(tmp_path: Path):
    module = _module(); common = {"output_root": tmp_path / "roots", "materialization_root": MATERIALIZATION, "frozen_successor_path": FROZEN, "hanna_csv_path": CSV, "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": _route}
    prepared = module.prepare_all(**common); study, token, schedule = module._schedule(materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV); rows, aliases, manifest = module._dedupe(study, schedule); module._schedule = lambda **_kwargs: (study, token, schedule)
    return module, common, prepared, rows, aliases, manifest


def test_prepare_is_30_unique_payload_roots_with_three_aliases(tmp_path: Path):
    module, common, prepared, rows, aliases, manifest = _prepared(tmp_path)
    assert prepared["unique_payload_cells"] == len(rows) == 30 and prepared["effective_candidates"] == 10 and len(aliases) == 3
    assert {path.name for path in common["output_root"].iterdir()} == {"alias-manifest.json", *(row["cell_id"] for row in rows)}
    for alias in aliases:
        assert not (common["output_root"] / alias).exists()
        with pytest.raises(ValueError, match="alias cell"):
            module.execute_one(**common, cell_id=alias, allow_remote=True, runner=_runner)
    assert module._alias_manifest(common["output_root"], manifest)["manifest_sha256"] == manifest["manifest_sha256"]


def test_one_shot_binds_real_runner_artifacts_and_rejects_forged_settings(tmp_path: Path):
    module, common, _prepared_value, rows, _aliases, _manifest = _prepared(tmp_path); cell = rows[0]["cell_id"]
    returned = module.execute_one(**common, cell_id=cell, allow_remote=True, runner=_runner)
    assert returned == {"cell_id": cell, "state": "local_cli_lifecycle_received", "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    root = common["output_root"] / cell
    assert (root / "responses" / "batch-0001.attempt-0001.prompt.txt").read_bytes() == (root / "prompt-request.bin").read_bytes()
    with pytest.raises(ValueError):
        module.execute_one(**common, cell_id=cell, allow_remote=True, runner=_runner)
    def forged(**kwargs):
        result = _runner(**kwargs); result["effective_settings"]["tools_enabled"] = True; return result
    terminal = module.execute_one(**common, cell_id=rows[1]["cell_id"], allow_remote=True, runner=forged)
    assert terminal["kind"] == "reconcile_required_after_process_launch"


def test_unexpected_postwrite_response_artifact_forces_idempotent_reconcile_block(tmp_path: Path):
    module, common, _prepared_value, rows, _aliases, _manifest = _prepared(tmp_path); cell = rows[0]["cell_id"]
    def unexpected(**kwargs):
        value = _runner(**kwargs)
        (kwargs["output_dir"] / "responses" / "unexpected.bin").write_bytes(b"unexpected")
        return value
    result = module.execute_one(**common, cell_id=cell, allow_remote=True, runner=unexpected)
    root = common["output_root"] / cell; marker = root / module.POSTWRITE_RECONCILE
    assert result["kind"] == "postwrite_reconcile_required" and marker.exists()
    before = marker.read_bytes()
    with pytest.raises(ValueError):
        module.execute_one(**common, cell_id=cell, allow_remote=True, runner=unexpected)
    assert marker.read_bytes() == before
    study, _token, schedule = module._schedule(materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    row = next(row for row in schedule["cells"] if row["cell_id"] == cell); payload, prompt, schema = module._payload(study, row)
    prepared = module._strict_json((root / "prepared.json").read_bytes(), "prepared")
    with pytest.raises(ValueError, match="postwrite reconciliation blocks"):
        module._admit_completed(root=root, row=row, schedule=schedule, payload=payload, prompt=prompt, schema=schema, route=prepared["route"], evidence=prepared["route_evidence"], acknowledgement=ACK)


def test_30_receipt_descriptive_roundtrip_has_strict_v5_negative_gate(tmp_path: Path):
    module, common, _prepared_value, rows, _aliases, _manifest = _prepared(tmp_path)
    for row in rows:
        assert module.execute_one(**common, cell_id=row["cell_id"], allow_remote=True, runner=_runner)["native_endpoint_contact_cardinality"] == "unproven"
    collector = tmp_path / "collector.json"
    assert module.finalize_collector(output_root=common["output_root"], collector_output=collector, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV, authorization_acknowledgement_sha256=ACK)["unique_payload_cells"] == 30
    descriptive = module.descriptive_project(collector_path=collector, materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    assert len(descriptive["metrics"]) == 10 and descriptive["authority"]["selection"] == "none"
    analyzer = module._analyze(); token = analyzer._study().prepare_grok_schedule(materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    with pytest.raises(ValueError): analyzer.project_native(validated_schedule=token, route_name="grok_primary", native_evidence_path=collector)


def test_collector_rejects_partial_swap_or_settings_tamper_and_runtime_has_no_optimizer(tmp_path: Path):
    module, common, _prepared_value, rows, _aliases, _manifest = _prepared(tmp_path)
    for row in rows: module.execute_one(**common, cell_id=row["cell_id"], allow_remote=True, runner=_runner)
    first, second = (common["output_root"] / rows[0]["cell_id"], common["output_root"] / rows[1]["cell_id"])
    original = (first / "native-response.bin").read_bytes(); (first / "native-response.bin").write_bytes((second / "native-response.bin").read_bytes())
    with pytest.raises(ValueError): module.finalize_collector(output_root=common["output_root"], collector_output=tmp_path / "swapped.json", materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV, authorization_acknowledgement_sha256=ACK)
    (first / "native-response.bin").write_bytes(original); (second / "effective-settings.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError): module.finalize_collector(output_root=common["output_root"], collector_output=tmp_path / "settings.json", materialization_root=MATERIALIZATION, frozen_successor_path=FROZEN, hanna_csv_path=CSV, authorization_acknowledgement_sha256=ACK)
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower(); assert "import dspy" not in source and "import optuna" not in source
