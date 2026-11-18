"""Fresh offline full-judging runs distinguish byte binding from context validity."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hbqrs import core, longform, longform_runner, runner, scoring_v2
from hbqrs.paths import prompts_dir, schema_dir
from hbqrs.run_verify import verify_binary_run
from hbqrs.verified_longform_context import verify_longform_contexts
from hbqrs.weights import materialize_weight_profile
from _run_verify_fixture import binding, write_json
from test_longform import TEXT, _contract, _map, _route
from test_longform_runner import _catalog


def _full_judging_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, alteration: str | None = None
) -> tuple[Path, dict[str, Any]]:
    """Generate every run input locally, including self-consistent bad contexts.

    Alterations precede all proof, prompt, checkpoint and score commitments: these
    are not simple file-tampering cases that the binary verifier already catches.
    """
    registry, bundles = _catalog(tmp_path)
    plan_root = tmp_path / "longform"
    source = plan_root / ".private" / "inputs" / "artifact.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(TEXT.encode("utf-8"))
    prompt = source.with_name("prompt.md")
    prompt.write_bytes(b"Keep the prose clear; prefer quiet tension.\n")
    artifact_id = "synthetic-story"
    segmentation = longform.segment_longform(TEXT, artifact_id=artifact_id)
    contract = _contract(binding=False)
    route = _route(segmentation, contract=contract)
    plan = {
        "format_version": 2,
        "status": "PLANNED",
        "execution_mode": "full_judging",
        "artifact_id": artifact_id,
        "route": route,
        "local_bundle_plan": longform.resolve_local_bundle_plan(
            bundles=core.load_bundles(bundles), global_bundle_id=route["selected_bundle_id"],
            artifact_kind="prose_fiction", segmentation=segmentation,
        ),
        "segmentation": runner._redacted_segmentation(segmentation),
        "source_artifact": {**binding(source), "path": ".private/inputs/artifact.txt"},
        "context_artifacts": [{**binding(prompt), "path": ".private/inputs/prompt.md"}],
        "route_validation": {
            "local_sample_limit": None, "binding_contract_approved": False,
            "explicit_local_bundle_id": None,
        },
        "transform_policy": {"format_version": 1, "policy_id": runner.LONGFORM_RUNTIME_CONTRACT_POLICY},
        "next_step": "Synthetic offline full-judging fixture.",
    }
    plan_path = plan_root / "plan.json"
    write_json(plan_path, plan)
    generated = plan_root / ".private" / "generated-inputs"
    generated.mkdir(parents=True)
    artifact = generated / "whole-work-units.txt"
    artifact.write_bytes(longform_runner._organized_source(segmentation).encode("utf-8"))
    task = runner._longform_runtime_contract(
        contract, scope_id="work", artifact_id=artifact_id, execution_scope="work"
    )
    task_path = generated / "contracts" / "work.json"
    write_json(task_path, task)
    context_contract = runner._longform_runtime_contract(
        contract, scope_id="work", artifact_id=artifact_id,
        execution_scope="work", normalize_absence=False,
    )
    task_context = longform_runner._contract_judge_context(context_contract)
    map_value = _map(segmentation)
    if alteration == "wrong_map_source":
        map_value["source_sha256"] = "0" * 64
    elif alteration == "altered_task_context":
        task_context["task_contract_questions"][0]["source_reference"] = "invented-other-source"
    elif alteration is not None:
        raise ValueError(alteration)
    map_path = plan_root / ".private" / "passes" / "map" / "result.json"
    task_context_path = generated / "contracts" / "work.judge-context.json"
    completion_path = generated / "completion-contexts" / "work.json"
    write_json(map_path, map_value)
    write_json(task_context_path, task_context)
    write_json(completion_path, longform_runner._completion_judge_context(
        "work_in_progress", scope_kind="global", scope_id="work"
    ))
    contexts = [prompt, map_path, task_context_path, completion_path]
    task_record = runner._manifest_inputs([runner._read_text_record(task_path)])[0]
    task_record["contract_id"] = task["contract_id"]
    proof = runner._longform_scope_compatibility_proof(
        artifact_path=artifact, artifact_id=artifact_id, bundle_id=route["selected_bundle_id"],
        task_contract=task, task_contract_record=task_record, route_plan_path=plan_path,
        registry_path=registry, bundles_path=bundles, context_paths=contexts,
    )
    modules = core.load_modules(registry)
    bundle = core.resolve_bundle(core.load_bundles(bundles), route["selected_bundle_id"])
    modules, bundle, weight = materialize_weight_profile(modules, bundle, None)
    compiled = core.compile_bundle(modules, bundle, task_contract=task)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda row: order.get(str(row.get("role")), 99))
    calls = []

    def fail_provider(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Unexpected provider boundary in an offline fixture")

    def fake_codex(*, response_schema: Path, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        schema = json.loads(Path(response_schema).read_bytes())
        ids = schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"]
        calls.append(ids)
        response = {"verdicts": [{
            "question_id": question_id, "verdict": "YES", "confidence": 0.8,
            "evidence": [{"kind": "summary", "reference": "synthetic fixture",
                          "exact_quote": None, "summary": "Invented fixture evidence."}],
            "note": "Invented fixture verdict.",
        } for question_id in ids]}
        # Compatibility metadata is invented; no model or native session runs.
        return json.dumps(response), {"reported": {
            "provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high",
            "session_id": f"invented-offline-session-{len(calls)}",
        }}

    for name in ("_call_openai", "_call_grok", "_call_nous"):
        monkeypatch.setattr(runner, name, fail_provider)
    monkeypatch.setattr(runner, "_call_codex", fake_codex)
    run = tmp_path / "binary-run"
    runner.run_judge(
        artifact_path=artifact, context_paths=contexts, task_contract_path=task_path,
        longform_scope_compatibility_proof=proof, bundle_id=bundle["bundle_id"],
        provider="codex", model="gpt-5.6-sol", output_dir=run, registry=registry, bundles=bundles,
        question_ids=[str(row["question"]["id"]) for row in questions],
        batch_size=32, batch_attempts=3, reasoning="high", allow_remote=True,
        artifact_id=artifact_id, response_schema_mode="batch_question_ids_v1",
        response_json_policy=runner.RESPONSE_JSON_FINITE_POLICY,
    )
    assert len(calls) == (len(questions) + 31) // 32
    descendant = scoring_v2.score_bundle(
        modules, bundle, core.load_verdicts(run / "verdicts.jsonl"),
        artifact_id=artifact_id, task_contract=task,
    )
    descendant["weight_profile"] = weight
    descendant["parent_score_sha256"] = binding(run / "score.json")["sha256"]
    write_json(run / "score.v2.json", descendant)
    frozen = {
        "artifact": binding(artifact), "contexts": [binding(path) for path in contexts],
        "task_contract": binding(task_path), "longform_scope_compatibility_proof": proof,
        "registry": binding(registry), "bundles": binding(bundles),
        "prompts": [binding(prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md")],
        "response_schema": binding(schema_dir() / "hbq_judge_response.schema.json"),
        "score_v1_schema": binding(schema_dir() / "hbq_score_report.schema.json"),
        "score_v2_schema": binding(schema_dir() / "hbq_score_report.v2.schema.json"),
        "weight_profile": None,
        "execution": {
            "artifact_id": artifact_id, "bundle_id": bundle["bundle_id"], "batch_size": 32,
            "batch_attempts": 3, "strict_ai": False, "provider": "codex", "model": "gpt-5.6-sol",
            "reasoning": "high", "codex_bin": "codex", "response_schema_mode": "batch_question_ids_v1",
            "response_json_policy": runner.RESPONSE_JSON_FINITE_POLICY,
        },
        "provider": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"},
    }
    return run, frozen


def test_verifies_fresh_binary_run_and_reconstructed_whole_work_contexts(tmp_path, monkeypatch):
    run, frozen = _full_judging_fixture(tmp_path, monkeypatch)
    binary = verify_binary_run(run, frozen)
    result = verify_longform_contexts(run, frozen)
    assert result["run_sha256"] == binary["run_sha256"]
    assert result["score_v2_sha256"] == binary["score_v2_sha256"]
    assert result["scope_proof"] == frozen["longform_scope_compatibility_proof"]
    source = tmp_path / "longform" / ".private" / "inputs" / "artifact.txt"
    assert result["source_sha256"] == binding(source)["sha256"]
    for name, context in zip(
        ("map_sha256", "task_context_sha256", "completion_context_sha256"), frozen["contexts"][-3:]
    ):
        assert result[name] == context["sha256"]
    for limitation in (
        "provider_identity_authenticated", "map_truth_established",
        "structured_pass_provenance_verified", "atomic_snapshot_established",
    ):
        assert result[limitation] is False


@pytest.mark.parametrize(("alteration", "message"), [
    ("wrong_map_source", "Long-form map source_sha256 does not match"),
    ("altered_task_context", "Deterministic context reconstruction differs"),
])
def test_rejects_self_consistent_contexts_that_binary_verification_accepts(
    tmp_path, monkeypatch, alteration, message
):
    run, frozen = _full_judging_fixture(tmp_path, monkeypatch, alteration=alteration)
    assert verify_binary_run(run, frozen)["verdict_count"] > 0
    with pytest.raises(core.HBQError, match=message):
        verify_longform_contexts(run, frozen)
