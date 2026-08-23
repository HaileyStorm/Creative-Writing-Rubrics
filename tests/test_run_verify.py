from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hbqrs import core, runner
from hbqrs.longform import resolve_local_bundle_plan, segment_longform
from hbqrs.paths import bundles_path, registry_path
from hbqrs.run_verify import verify_binary_run
from _run_verify_fixture import build_fixture as _fixture, write_json as _write


def _rewrite_configuration(run: Path, mutate) -> None:
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    mutate(manifest["configuration"])
    manifest["config_sha256"] = hashlib.sha256(runner._json_bytes(manifest["configuration"])).hexdigest()
    _write(run / "run.json", manifest)


def _rewrite_checkpoint(run: Path, batch: int, mutate) -> None:
    path = run / "responses" / f"batch-{batch:04d}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    _write(path, value)


def _rewrite_score(run: Path, name: str = "score.json") -> None:
    path = run / name
    value = json.loads(path.read_text(encoding="utf-8"))
    value["status"] = "forged"
    _write(path, value)


def _add_rejected_retry(run: Path) -> None:
    checkpoint = run / "responses" / "batch-0001.json"
    record = json.loads(checkpoint.read_text(encoding="utf-8"))
    base_prompt = gzip.decompress(checkpoint.with_suffix(".prompt.txt.gz").read_bytes()).decode("utf-8")
    base_hash = hashlib.sha256(base_prompt.encode("utf-8")).hexdigest()
    rejected_path = run / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    rejection = {"format_version": 4, "batch": 1, "attempt": 1, "sequence": 1, "previous_rejected_sha256": None, "stage": "model_output", "retry_policy": {"batch_attempts": 3}, "prompt_sha256": base_hash, "base_prompt_sha256": base_hash, "effective_prompt_sha256": base_hash, "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "validation_feedback": None, "raw_content": {"encoding": "utf-8", "text": "{}", "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}, "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "retry-session-1"}}, "error": {"class": "HBQError", "message": "fixture rejection"}}
    _write(rejected_path, rejection)
    effective, feedback = runner._feedback_for_rejection(base_prompt=base_prompt, base_prompt_sha256=base_hash, previous_rejection=(rejected_path, rejection))
    record["accepted_attempt"] = 2
    record["rejected_chain"] = {"count": 1, "head_sha256": hashlib.sha256(rejected_path.read_bytes()).hexdigest()}
    record["validation_feedback"] = feedback
    record["effective_prompt_sha256"] = hashlib.sha256(effective.encode("utf-8")).hexdigest()
    _write(checkpoint, record)
    previous = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    for batch in range(2, 7):
        path = run / "responses" / f"batch-{batch:04d}.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["previous_checkpoint_sha256"] = previous
        _write(path, value)
        previous = hashlib.sha256(path.read_bytes()).hexdigest()


def _rechain_from(run: Path, batch: int) -> None:
    previous = hashlib.sha256((run / "responses" / f"batch-{batch:04d}.json").read_bytes()).hexdigest()
    for number in range(batch + 1, 7):
        path = run / "responses" / f"batch-{number:04d}.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["previous_checkpoint_sha256"] = previous
        _write(path, value)
        previous = hashlib.sha256(path.read_bytes()).hexdigest()


def _refresh_rejected_retry_binding(run: Path, rejected: Path, rejection: dict[str, Any]) -> None:
    checkpoint = run / "responses" / "batch-0001.json"
    record = json.loads(checkpoint.read_text(encoding="utf-8"))
    record["rejected_chain"]["head_sha256"] = hashlib.sha256(rejected.read_bytes()).hexdigest()
    base_prompt = gzip.decompress(checkpoint.with_suffix(".prompt.txt.gz").read_bytes()).decode("utf-8")
    effective, feedback = runner._feedback_for_rejection(base_prompt=base_prompt, base_prompt_sha256=hashlib.sha256(base_prompt.encode("utf-8")).hexdigest(), previous_rejection=(rejected, rejection))
    record["validation_feedback"] = feedback
    record["effective_prompt_sha256"] = hashlib.sha256(effective.encode("utf-8")).hexdigest()
    _write(checkpoint, record)
    _rechain_from(run, 1)


def test_verifies_a_genuine_complete_v4_run_and_returns_raw_commitments(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    result = verify_binary_run(run, frozen)
    assert result["verdict_count"] == 179 and result["checkpoint_count"] == 6 and len(result["sessions"]) == 6
    assert result["checkpoint_chain_head_sha256"] == hashlib.sha256((run / "responses" / "batch-0006.json").read_bytes()).hexdigest()
    assert len(result["commitments"]["prompts"]) == len(result["commitments"]["accepted_response_artifacts"]) == 6
    assert result["commitments"]["rejected_attempts"] == []


def test_replays_a_genuine_v2_longform_scope_proof(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    artifact = inputs / "source.md"
    context = inputs / "prompt.md"
    task_path = inputs / "task.json"
    artifact.write_text("The lantern flickered at dawn.", encoding="utf-8")
    context.write_text("Write a tense short story about a lantern.", encoding="utf-8")
    task = {
        "contract_version": 1, "contract_id": "longform-proof", "artifact_id": "fixture-story",
        "context": {"artifact_kind": "prose_fiction", "declared_scope": "story", "completion_status": "complete", "background": [], "constraints": [], "audience": []},
        "preferences": [], "priorities": [],
        "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story respond to its originating prompt?", "weight": 2.0, "source": {"kind": "driving_prompt", "reference": "fixture prompt", "exact_excerpt": context.read_text(encoding="utf-8")}, "applies_to": ["work"], "rationale": "Fixture task relevance."}],
        "binding_requirements": [],
    }
    _write(task_path, task)
    plan_root = tmp_path / "longform"
    persisted_source = plan_root / ".private" / "inputs" / "artifact.txt"
    persisted_source.parent.mkdir(parents=True)
    persisted_source.write_bytes(artifact.read_bytes())
    persisted_context = persisted_source.with_name("prompt.md")
    persisted_context.write_bytes(context.read_bytes())
    segmentation = segment_longform(artifact.read_text(encoding="utf-8"), artifact_id="fixture-story")
    redacted = runner._redacted_segmentation(segmentation)
    modules, bundles = core.load_modules(registry_path()), core.load_bundles(bundles_path())
    bundle = core.resolve_bundle(bundles, "prose.short_story")
    route = {
        "route_version": 1,
        "artifact_profile": {"artifact_kind": "prose_fiction", "declared_scope": "story", "completion_status": "complete", "unit_count": segmentation["unit_count"], "source_sha256": segmentation["source_sha256"]},
        "selected_bundle_id": "prose.short_story", "selected_module_ids": bundle["module_ids"],
        "selection_reasons": [{"catalog_id": "prose.short_story", "reason": "Fixture route."}],
        "sampling_plan": {"coverage_mode": "complete", "unit_ids": [unit["unit_id"] for unit in segmentation["units"]], "strata": [{"name": "complete", "unit_ids": [unit["unit_id"] for unit in segmentation["units"]]}], "global_map_required": True, "rationale": "Fixture coverage."},
        "task_contract": task,
    }
    plan = {
        "format_version": 2, "status": "PLANNED", "execution_mode": "route_only", "artifact_id": "fixture-story", "route": route,
        "local_bundle_plan": resolve_local_bundle_plan(bundles=bundles, global_bundle_id="prose.short_story", artifact_kind="prose_fiction", segmentation=segmentation),
        "segmentation": redacted,
        "source_artifact": {"path": ".private/inputs/artifact.txt", "bytes": persisted_source.stat().st_size, "sha256": hashlib.sha256(persisted_source.read_bytes()).hexdigest()},
        "context_artifacts": [{"path": ".private/inputs/prompt.md", "bytes": persisted_context.stat().st_size, "sha256": hashlib.sha256(persisted_context.read_bytes()).hexdigest()}],
        "route_validation": {"local_sample_limit": None, "binding_contract_approved": False, "explicit_local_bundle_id": None},
        "transform_policy": {"format_version": 1, "policy_id": runner.LONGFORM_RUNTIME_CONTRACT_POLICY},
        "next_step": "Fixture plan.",
    }
    plan_path = plan_root / "plan.json"
    _write(plan_path, plan)
    run, frozen = _fixture(tmp_path, input_paths=(persisted_source, persisted_context, task_path))
    task_record = runner._manifest_inputs([runner._read_text_record(task_path)])[0]
    task_record["contract_id"] = task["contract_id"]
    proof = runner._longform_scope_compatibility_proof(
        artifact_path=persisted_source,
        artifact_id="fixture-story", bundle_id="prose.short_story", task_contract=task,
        task_contract_record=task_record, route_plan_path=plan_path,
        registry_path=registry_path(), bundles_path=bundles_path(), context_paths=(persisted_context,),
    )
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    manifest["configuration"]["scope_compatibility"] = proof
    manifest["config_sha256"] = hashlib.sha256(runner._json_bytes(manifest["configuration"])).hexdigest()
    _write(run / "run.json", manifest)
    frozen.pop("scope_compatibility_override")
    frozen["longform_scope_compatibility_proof"] = proof
    assert verify_binary_run(run, frozen)["verdict_count"] == 179
    forged_proof = dict(proof)
    forged_proof["generated_contexts"] = [{"role": "longform_map", "sha256": "0" * 64}]
    frozen["longform_scope_compatibility_proof"] = forged_proof
    _rewrite_configuration(run, lambda value: value.update({"scope_compatibility": forged_proof}))
    with pytest.raises(core.HBQError, match="does not bind"):
        verify_binary_run(run, frozen)
    with pytest.raises(core.HBQError, match="exact planned binary contexts"):
        runner._longform_scope_compatibility_proof(
            artifact_path=persisted_source,
            artifact_id="fixture-story", bundle_id="prose.short_story", task_contract=task,
            task_contract_record=task_record, route_plan_path=plan_path,
            registry_path=registry_path(), bundles_path=bundles_path(), context_paths=(),
        )
    extra = inputs / "extra.md"
    extra.write_text("extra", encoding="utf-8")
    with pytest.raises(core.HBQError, match="exact generated binary contexts"):
        runner._longform_scope_compatibility_proof(
            artifact_path=persisted_source,
            artifact_id="fixture-story", bundle_id="prose.short_story", task_contract=task,
            task_contract_record=task_record, route_plan_path=plan_path,
            registry_path=registry_path(), bundles_path=bundles_path(), context_paths=(persisted_context, extra),
        )
    persisted_context.write_text("drifted", encoding="utf-8")
    with pytest.raises(core.HBQError, match="persisted context commitment drifted"):
        runner._longform_scope_compatibility_proof(
            artifact_path=persisted_source,
            artifact_id="fixture-story", bundle_id="prose.short_story", task_contract=task,
            task_contract_record=task_record, route_plan_path=plan_path,
            registry_path=registry_path(), bundles_path=bundles_path(), context_paths=(persisted_context,),
        )


def test_verifies_historical_v3_prompt_bytes_without_reinterpreting_them(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path, prompt_rendering_version=runner.LEGACY_PROMPT_RENDERING_VERSION)
    result = verify_binary_run(run, frozen)
    assert result["verdict_count"] == 179


def test_rejects_a_schema_invalid_frozen_task_contract_before_replay(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    task_path = Path(frozen["task_contract"]["path"])
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["context"]["unexpected"] = True
    _write(task_path, task)
    frozen["task_contract"]["bytes"] = task_path.stat().st_size
    frozen["task_contract"]["sha256"] = hashlib.sha256(task_path.read_bytes()).hexdigest()
    with pytest.raises(core.HBQError, match="strict schema"):
        verify_binary_run(run, frozen)


def test_replays_and_commits_a_genuine_rejected_retry_chain(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    _add_rejected_retry(run)
    result = verify_binary_run(run, frozen)
    assert result["rejected_attempt_count"] == len(result["commitments"]["rejected_attempts"]) == 1
    assert result["commitments"]["rejected_attempts"][0]["path"] == "responses/rejected/batch-0001/attempt-0001.json"
    assert len(result["sessions"]) == 7


@pytest.mark.parametrize("mutate", [
    lambda run, frozen: _rewrite_configuration(run, lambda value: value.update({"model": "forged"})),
    lambda run, frozen: _rewrite_configuration(run, lambda value: value.update({"reasoning": "low"})),
    lambda run, frozen: _rewrite_configuration(run, lambda value: value["task_contract_judge_context"].update({"sha256": "0" * 64})),
    lambda run, frozen: _rewrite_configuration(run, lambda value: value["scope_compatibility"].update({"decision_id": "forged"})),
    lambda run, frozen: _rewrite_configuration(run, lambda value: value["weight_profile"].update({"identity": False})),
    lambda run, frozen: (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"forged", mtime=0)),
    lambda run, frozen: (run / "responses" / "batch-0006.json").unlink(),
    lambda run, frozen: _rewrite_checkpoint(run, 1, lambda value: value.update({"format_version": 3})),
    lambda run, frozen: _rewrite_checkpoint(run, 2, lambda value: value.update({"previous_checkpoint_sha256": None})),
    lambda run, frozen: _rewrite_checkpoint(run, 1, lambda value: value.update({"accepted_attempt": 2})),
    lambda run, frozen: _rewrite_checkpoint(run, 1, lambda value: value["provider"]["reported"].update({"reasoning_effort": "low"})),
    lambda run, frozen: _rewrite_score(run),
    lambda run, frozen: _rewrite_score(run, "score.v2.json"),
    lambda run, frozen: (run / "responses" / "batch-0001.provider.txt").write_text("forged", encoding="utf-8"),
])
def test_rejects_manifest_prompt_checkpoint_provider_weight_and_score_tampering(tmp_path: Path, mutate) -> None:
    run, frozen = _fixture(tmp_path)
    mutate(run, frozen)
    with pytest.raises(core.HBQError):
        verify_binary_run(run, frozen)


def test_rejects_same_byte_wrong_bound_path_and_source_schema_drift(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    duplicate = tmp_path / "same-bytes.md"
    duplicate.write_bytes(Path(frozen["artifact"]["path"]).read_bytes())
    _rewrite_configuration(run, lambda value: value["artifact"].update({"path": str(duplicate.resolve()), "name": duplicate.name}))
    with pytest.raises(core.HBQError, match="independently"):
        verify_binary_run(run, frozen)
    run, frozen = _fixture(tmp_path / "source")
    Path(frozen["artifact"]["path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(core.HBQError, match="artifact bytes drifted"):
        verify_binary_run(run, frozen)
    run, frozen = _fixture(tmp_path / "schema")
    frozen["response_schema"]["sha256"] = "0" * 64
    with pytest.raises(core.HBQError, match="response schema bytes drifted"):
        verify_binary_run(run, frozen)
    run, frozen = _fixture(tmp_path / "context")
    Path(frozen["contexts"][0]["path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(core.HBQError, match="context bytes drifted"):
        verify_binary_run(run, frozen)


def test_rejects_reused_provider_sessions_after_a_valid_checkpoint_rechain(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    _rewrite_checkpoint(run, 2, lambda value: value["provider"]["reported"].update({"session_id": "session-1"}))
    _rechain_from(run, 2)
    with pytest.raises(core.HBQError, match="reuses provider sessions"):
        verify_binary_run(run, frozen)


def test_rejects_whitespace_only_accepted_provider_session_after_rechain(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    _rewrite_checkpoint(run, 2, lambda value: value["provider"]["reported"].update({"session_id": " \t "}))
    _rechain_from(run, 2)
    with pytest.raises(core.HBQError, match="lacks a provider session"):
        verify_binary_run(run, frozen)


def test_rejects_frozen_provider_divergence_before_checkpoint_replay(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    frozen["provider"] = {"provider": "openai", "model": "forged", "reasoning_effort": "high"}
    with pytest.raises(core.HBQError, match="diverges from the Codex execution contract"):
        verify_binary_run(run, frozen)


def test_rejects_model_output_rejection_without_an_attested_provider_session(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    _add_rejected_retry(run)
    rejected = run / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    value = json.loads(rejected.read_text(encoding="utf-8"))
    value["provider"] = None
    _write(rejected, value)
    _refresh_rejected_retry_binding(run, rejected, value)
    with pytest.raises(core.HBQError, match="Rejected provider identity drifted"):
        verify_binary_run(run, frozen)


def test_rejects_whitespace_only_rejected_provider_session_after_rebinding(tmp_path: Path) -> None:
    run, frozen = _fixture(tmp_path)
    _add_rejected_retry(run)
    rejected = run / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    value = json.loads(rejected.read_text(encoding="utf-8"))
    value["provider"]["reported"]["session_id"] = " \n "
    _write(rejected, value)
    _refresh_rejected_retry_binding(run, rejected, value)
    with pytest.raises(core.HBQError, match="Rejected provider session is malformed"):
        verify_binary_run(run, frozen)
