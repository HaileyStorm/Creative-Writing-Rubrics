from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v3-callback-prompt"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def module():
    return load(PACKAGE / "executor.py", "_desc13_lower_step_v3_callback_prompt")


def v1_support():
    return load(ROOT / "tests" / "test_hbq_human_alignment_optimizer_v6_desc13_lower_step_grok_exec_v1.py", "_desc13_lower_step_v3_v1_support")


def staged_runner(value, stage):
    events = {"entries": 0, "contacts": 0, "intent_seen": False}

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        events["entries"] += 1
        schema = json.loads(schema_path.read_bytes())
        assert schema["required"] == ["scores", "evidence", "coverage"]
        responses = output_dir / "responses"
        responses.mkdir()
        stage(responses, prompt)
        before_contact()
        events["intent_seen"] = (output_dir / "launch-intent.json").is_file()
        events["contacts"] += 1
        scores = {key: 3.0 for key in ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")}
        token = hashlib.sha256(prompt + str(output_dir).encode()).hexdigest()
        response = value.canonical({"requestId": "request-" + token, "sessionId": "session-" + token, "modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "structuredOutput": {"scores": scores, "evidence": {key: "fixture" for key in scores}, "coverage": {key: True for key in scores}}})
        (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}
        return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": "request-" + token, "session_id": "session-" + token, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": settings}

    return run, events


def exact_stage(responses: Path, prompt: bytes):
    (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)


def prepared(tmp_path: Path):
    value, support = module(), v1_support()
    args = support.common(tmp_path)
    result = value.prepare_all(**args)
    return value, args, result["prepared_cells"][0]


def test_contract_pins_committed_v2_and_callback_prompt_binding():
    value = module()
    assert value.contract() == value._expected_contract()
    assert value.contract()["pinned_v2"]["commit"] == value.V2_COMMIT
    assert value.contract()["callback_prompt"] == {"name": value.ATTEMPT_PROMPT, "source": "prompt-request.bin"}


def test_callback_accepts_only_exact_staged_prompt_then_writes_launch_intent(tmp_path: Path):
    value, args, cell = prepared(tmp_path)
    runner, events = staged_runner(value, exact_stage)
    result = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=runner)
    assert result["kind"] != "definitely_not_contacted"
    assert events == {"entries": 1, "contacts": 1, "intent_seen": True}


@pytest.mark.parametrize("stage", [
    lambda _responses, _prompt: None,
    lambda responses, prompt: (responses / "batch-0001.attempt-0002.prompt.txt").write_bytes(prompt),
    lambda responses, prompt: (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt + b" altered"),
    lambda responses, prompt: ((responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt), (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(b"{}")),
])
def test_callback_rejects_missing_misnamed_mutated_or_response_output_before_contact(tmp_path: Path, stage):
    value, args, cell = prepared(tmp_path)
    runner, events = staged_runner(value, stage)
    result = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=runner)
    assert result["kind"] == "definitely_not_contacted"
    assert events["entries"] == 1 and events["contacts"] == 0 and events["intent_seen"] is False
    assert not (args["output_root"] / cell / "launch-intent.json").exists()


def test_callback_rejects_reparsed_staged_prompt_before_contact(tmp_path: Path):
    def reparse(responses: Path, prompt: bytes):
        staged = responses / "staged-prompt.txt"
        staged.write_bytes(prompt)
        target = responses / "batch-0001.attempt-0001.prompt.txt"
        try:
            os.symlink(staged, target)
        except OSError:
            pytest.skip("symlink privilege is unavailable")

    value, args, cell = prepared(tmp_path)
    runner, events = staged_runner(value, reparse)
    result = value.execute_one(**args, cell_id=cell, allow_remote=True, runner=runner)
    assert result["kind"] == "definitely_not_contacted"
    assert events["entries"] == 1 and events["contacts"] == 0 and events["intent_seen"] is False


def test_runtime_has_no_dspy_or_optuna_dependency():
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
