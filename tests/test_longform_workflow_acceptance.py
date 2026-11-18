"""One provider-disabled public long-form workflow composition witness."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess

import pytest

from hbqrs import longform, longform_runner, runner
from hbqrs.paths import prompts_dir, schema_dir
from hbqrs.runner_v2 import persist_v2_descendant
from hbqrs.verified_longform_context import verify_longform_contexts
from _run_verify_fixture import binding, write_json
from test_longform import TEXT, _contract, _map, _route
from test_longform_runner import _catalog, _questions


def test_generated_workflow_preserves_scoped_goals_absence_and_multiline_quotes(tmp_path, monkeypatch):
    registry, bundles = _catalog(tmp_path)
    artifact = tmp_path / "story.txt"
    artifact.write_bytes(TEXT.encode("utf-8"))
    artifact_id = "synthetic-story"
    segmentation = longform.segment_longform(TEXT, artifact_id=artifact_id)
    first_unit = next(unit["unit_id"] for unit in segmentation["units"] if unit["local_evaluation"]["eligible"])
    contract = _contract(binding=False)
    contract["preferences"] = []
    contract["weighted_goals"][0]["goal_id"] = "goal.work_clarity"
    contract["weighted_goals"].append({
        "goal_id": "goal.local_tension", "atomic_question": "Does this chapter sustain quiet tension?",
        "weight": 1.0, "source": {"kind": "driving_prompt", "reference": "driving-prompt:local",
        "exact_excerpt": "Sustain quiet tension in the first chapter."}, "applies_to": [first_unit],
        "rationale": "This local goal is scoped to the first selected unit.",
    })
    contract["binding_requirements"] = [{
        "requirement_id": "requirement.no_dragons", "atomic_question": "Is the work free of dragons?",
        "objective": True, "non_negotiable": True,
        "source": {"kind": "explicit_user_requirement", "reference": "driving-prompt:absence",
                   "exact_excerpt": "Do not include dragons."},
        "applies_to": ["work"], "verification": {"method": "absence", "expected": "dragons"},
    }]
    contract_path = tmp_path / "contract.json"
    write_json(contract_path, contract)
    automatic_contract = deepcopy(contract)
    automatic_contract["binding_requirements"] = []
    route = _route(segmentation, contract=automatic_contract)
    calls = []

    def forbidden(*args, **kwargs):
        pytest.fail("Unexpected provider, network or process boundary")

    def fake_structured(**kwargs):
        stage = kwargs["prompt"].split("HBQ-RS STRUCTURED PASS: ", 1)[1].split("\n", 1)[0]
        value = {"route": route, "map": _map(segmentation), "synthesis": {"findings": [], "warnings": []}}[stage]
        return json.dumps(value), {"reported": {
            "provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high",
            "session_id": f"invented-structured-{stage}",
        }}

    def fake_binary(**kwargs):
        prompt = kwargs["prompt"]
        ids = [row["question_id"] for row in _questions(prompt)]
        text = prompt.split("\n## Artifact: ", 1)[1].split("\n", 1)[1].split("\n## Questions\n", 1)[0]
        # Preserve original CRLF/LF exactly; newline normalization breaks grounding.
        quote = "".join(text.lstrip("\r\n").splitlines(keepends=True)[:2]).rstrip("\r\n")
        assert quote and quote in text
        scope = Path(kwargs["output_dir"]).name
        if scope == "global":
            assert "\n" in quote
        calls.append((scope, ids))
        response = {"verdicts": [{
            "question_id": question_id, "verdict": "YES", "confidence": 0.8,
            "evidence": [{"kind": "exact_quote", "reference": "invented artifact lines1-2",
                          "exact_quote": quote, "summary": None}], "note": "Invented fixture verdict.",
        } for question_id in ids]}
        return json.dumps(response), {"reported": {
            "provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high",
            "session_id": f"invented-binary-{len(calls)}",
        }}

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for module in (runner, longform_runner):
        for name in ("_call_openai", "_call_openai_structured", "_call_grok", "_call_nous"):
            if hasattr(module, name):
                monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(runner, "_call_codex", fake_binary)
    monkeypatch.setattr(longform_runner, "_call_codex", fake_structured)
    run = tmp_path / "workflow"
    summary = longform_runner.run_longform_judge(
        artifact_path=artifact, brief_paths=[], output_dir=run, provider="codex", model="gpt-5.6-sol",
        registry=registry, bundles=bundles, artifact_kind="prose_fiction", bundle_id="prose.synthetic",
        artifact_id=artifact_id, task_contract_path=contract_path,
        driving_prompt="Keep the prose clear. Sustain quiet tension in the first chapter. Do not include dragons.",
        batch_size=32, binary_workers=1, batch_attempts=1, allow_remote=True, judge_reasoning="high",
    )
    assert summary["status"] == "VALID"
    generated = run / ".private/generated-inputs"
    task_path = generated / "contracts/work.json"
    work_task = json.loads(task_path.read_bytes())
    assert [goal["goal_id"] for goal in work_task["weighted_goals"]] == ["goal.work_clarity"]
    assert work_task["binding_requirements"][0]["verification"]["method"] == "structural_constraint"
    for unit in segmentation["units"]:
        if not unit["local_evaluation"]["eligible"]:
            continue
        local_task = json.loads((generated / "contracts" / f"{unit['unit_id']}.json").read_bytes())
        expected = ["goal.local_tension"] if unit["unit_id"] == first_unit else []
        assert [goal["goal_id"] for goal in local_task["weighted_goals"]] == expected
        assert not local_task["binding_requirements"]
    expected_goals = {"global": "goal.work_clarity", first_unit: "goal.local_tension"}
    expected_scopes = {"global"} | {
        unit["unit_id"] for unit in segmentation["units"] if unit["local_evaluation"]["eligible"]
    }
    # This tiny catalog fits one batch per scope. No omitted or duplicated scope
    # may hide behind assertions over only the callbacks that happened.
    assert {scope for scope, _ in calls} == expected_scopes
    assert len(calls) == len(expected_scopes)
    for scope, ids in calls:
        expected = expected_goals.get(scope)
        goal_ids = [question_id for question_id in ids if ".goal." in question_id]
        assert goal_ids == ([f"task.contract.contract.synthetic.{expected}"] if expected else [])
    global_run = run / ".private/evaluations/global"
    manifest = json.loads((global_run / "run.json").read_bytes())
    contexts = [run / ".private/inputs/driving-prompt.txt", run / ".private/passes/map/result.json",
                generated / "contracts/work.judge-context.json", generated / "completion-contexts/work.json"]
    frozen = {
        "artifact": binding(generated / "whole-work-units.txt"), "contexts": [binding(p) for p in contexts],
        "task_contract": binding(task_path), "longform_scope_compatibility_proof": manifest["configuration"]["scope_compatibility"],
        "registry": binding(registry), "bundles": binding(bundles),
        "prompts": [binding(prompts_dir() / "judge/BINARY_EVALUATION_PROMPT.md")],
        "response_schema": binding(schema_dir() / "hbq_judge_response.schema.json"),
        "score_v1_schema": binding(schema_dir() / "hbq_score_report.schema.json"),
        "score_v2_schema": binding(schema_dir() / "hbq_score_report.v2.schema.json"), "weight_profile": None,
        "execution": {"artifact_id": artifact_id, "bundle_id": "prose.synthetic", "batch_size": 32,
                      "batch_attempts": 1, "strict_ai": False, "provider": "codex", "model": "gpt-5.6-sol",
                      "reasoning": "high", "codex_bin": "codex", "response_json_policy": runner.RESPONSE_JSON_FINITE_POLICY},
        "provider": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"},
    }
    persist_v2_descendant(output_dir=global_run, registry=registry, bundles=bundles,
                          weight_profile=None, task_contract_path=task_path)
    verified = verify_longform_contexts(global_run, frozen)
    assert verified["task_context_sha256"] == frozen["contexts"][2]["sha256"]
    judge_context = json.loads(contexts[2].read_bytes())
    assert "absence" in json.dumps(judge_context)
    verdicts = [json.loads(line) for line in (global_run / "verdicts.jsonl").read_bytes().splitlines()]
    assert any("\n" in item["exact_quote"] for row in verdicts for item in row["evidence"] if item.get("exact_quote"))
    assert verified["provider_identity_authenticated"] is False
    assert verified["map_truth_established"] is False
