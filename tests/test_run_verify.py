from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from hbqrs import core, runner, scoring_v2
from hbqrs import run_verify
from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir
from hbqrs.run_verify import verify_binary_run
from hbqrs.weights import materialize_weight_profile


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(runner._json_bytes(value))


def _binding(path: Path) -> dict[str, Any]:
    path = path.resolve()
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    inputs = tmp_path / "inputs"
    artifact, context, task_path = inputs / "source.md", inputs / "prompt.md", inputs / "task.json"
    inputs.mkdir(parents=True)
    artifact.write_text("The lantern flickered at dawn.", encoding="utf-8")
    context.write_text("Write a tense short story about a lantern.", encoding="utf-8")
    task = {"contract_version": 1, "contract_id": "fixture", "artifact_id": "fixture-story", "context": {"artifact_kind": "short prose fiction", "declared_scope": "complete short story", "completion_status": "complete", "background": [], "constraints": [], "audience": []}, "preferences": [], "priorities": [], "weighted_goals": [{"goal_id": "prompt_response", "atomic_question": "Does the story respond to its originating prompt?", "weight": 2.0, "source": {"kind": "driving_prompt", "reference": "fixture prompt", "exact_excerpt": "Write a tense short story about a lantern."}, "applies_to": ["whole artifact"], "rationale": "Fixture task relevance."}], "binding_requirements": []}
    _write(task_path, task)
    binary_prompt = prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"
    response_schema = schema_dir() / "hbq_judge_response.schema.json"
    frozen = {"artifact": _binding(artifact), "contexts": [_binding(context)], "task_contract": _binding(task_path), "registry": _binding(registry_path()), "bundles": _binding(bundles_path()), "prompts": [_binding(binary_prompt)], "response_schema": _binding(response_schema), "score_v1_schema": _binding(schema_dir() / "hbq_score_report.schema.json"), "score_v2_schema": _binding(schema_dir() / "hbq_score_report.v2.schema.json"), "weight_profile": None, "execution": {"artifact_id": "fixture-story", "bundle_id": "prose.short_story", "batch_size": 32, "batch_attempts": 3, "strict_ai": False, "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "codex_bin": "codex"}, "provider": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}}
    modules = core.load_modules(registry_path())
    bundle = core.resolve_bundle(core.load_bundles(bundles_path()), "prose.short_story")
    modules, bundle, weight = materialize_weight_profile(modules, bundle, None)
    compiled = core.compile_bundle(modules, bundle, task_contract=task)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order.get(str(item.get("role")), 99))
    artifact_record = runner._read_text_record(artifact)
    context_record = runner._read_text_record(context)
    task_record = runner._manifest_inputs([runner._read_text_record(task_path)])[0]
    task_record["contract_id"] = "fixture"
    prompt_records = [runner._read_text_record(binary_prompt)]
    binary = "\n\n".join(str(item["text"]).strip() for item in prompt_records)
    configuration = {"artifact": runner._manifest_inputs([artifact_record])[0], "contexts": runner._manifest_inputs([context_record]), "task_contract": task_record, "weight_profile": weight, "bundle_id": "prose.short_story", "bundle_version": bundle["version"], "question_ids": [str(item["question"]["id"]) for item in questions], "provider": "codex", "model": "gpt-5.6-sol", "endpoint": None, "api_key_env": None, "temperature": None, "allow_model_mismatch": None, "reasoning": "high", "codex_bin": "codex", "batch_size": 32, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "artifact_id": "fixture-story", "judge_id": "codex:gpt-5.6-sol", "strict_ai": False, "prompts": runner._manifest_inputs(prompt_records), "response_schema": runner._manifest_inputs([runner._read_text_record(response_schema)])[0], "questions_sha256": hashlib.sha256(runner._json_bytes(runner._question_payload(questions))).hexdigest(), "compiled_bundle_sha256": hashlib.sha256(runner._json_bytes(compiled)).hexdigest()}
    run = tmp_path / "run"
    _write(run / "run.json", {"format_version": 3, "run_id": "fixture-run", "config_sha256": hashlib.sha256(runner._json_bytes(configuration)).hexdigest(), "configuration": configuration})
    completed: list[dict[str, Any]] = []
    previous = None
    for batch, start in enumerate(range(0, len(questions), 32), start=1):
        selected = questions[start:start + 32]
        ids = [str(item["question"]["id"]) for item in selected]
        payload = {"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8, "evidence": [{"kind": "exact_quote", "reference": "story", "exact_quote": "lantern", "summary": None}], "note": "grounded"} for question_id in ids]}
        raw = json.dumps(payload, ensure_ascii=False)
        audit: list[dict[str, Any]] = []
        normalized = runner._normalize_batch(payload, expected_ids=ids, artifact_id="fixture-story", bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id="fixture-run", artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[context.read_text(encoding="utf-8")], normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
        prompt = runner._render_prompt(binary_prompt=binary, artifact={"name": artifact.name, "text": artifact.read_text(encoding="utf-8")}, contexts=[{"name": context.name, "text": context.read_text(encoding="utf-8")}], bundle_id="prose.short_story", artifact_id="fixture-story", questions=selected)
        prompt_bytes = prompt.encode("utf-8")
        response = run / "responses" / f"batch-{batch:04d}.accepted-0001.message.txt"
        response.parent.mkdir(parents=True, exist_ok=True)
        response.write_text(raw, encoding="utf-8")
        provider_artifact = run / "responses" / f"batch-{batch:04d}.provider.txt"
        provider_artifact.write_text("provider receipt", encoding="utf-8")
        completed.extend(normalized)
        record = {"format_version": 4, "batch": batch, "retry_policy": {"batch_attempts": 3}, "accepted_attempt": 1, "question_ids": ids, "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(), "base_prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(), "effective_prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(), "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "validation_feedback": None, "normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": audit, "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(), "response_artifact": {"path": response.relative_to(run).as_posix(), "bytes": response.stat().st_size, "sha256": hashlib.sha256(response.read_bytes()).hexdigest()}, "rejected_chain": {"count": 0, "head_sha256": None}, "previous_checkpoint_sha256": previous, "verdicts_sha256": hashlib.sha256(runner._verdicts_bytes(completed)).hexdigest(), "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"session-{batch}"}, "provider_artifacts": {"metadata": {"path": provider_artifact.relative_to(run).as_posix(), "bytes": provider_artifact.stat().st_size, "sha256": hashlib.sha256(provider_artifact.read_bytes()).hexdigest()}}}, "normalized_verdicts": normalized}
        checkpoint = run / "responses" / f"batch-{batch:04d}.json"
        _write(checkpoint, record)
        checkpoint.with_suffix(".prompt.txt.gz").write_bytes(gzip.compress(prompt_bytes, mtime=0))
        previous = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (run / "verdicts.jsonl").write_bytes(runner._verdicts_bytes(completed))
    parent = core.score_bundle(modules, bundle, completed, artifact_id="fixture-story", task_contract=task)
    parent["weight_profile"] = weight
    _write(run / "score.json", parent)
    descendant = scoring_v2.score_bundle(modules, bundle, completed, artifact_id="fixture-story", task_contract=task)
    descendant["weight_profile"] = weight
    descendant["parent_score_sha256"] = hashlib.sha256((run / "score.json").read_bytes()).hexdigest()
    _write(run / "score.v2.json", descendant)
    return run, frozen


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
