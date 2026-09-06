"""Genuine, offline v4 binary-run fixture construction for verifier consumers."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

from hbqrs import core, runner, scoring_v2
from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir
from hbqrs.weights import materialize_weight_profile


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(runner._json_bytes(value))


def binding(path: Path) -> dict[str, Any]:
    path = path.resolve()
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def build_fixture(
    root: Path,
    *,
    artifact_id: str = "fixture-story",
    provider_session_prefix: str = "session",
    run_dir: Path | None = None,
    artifact_text: str = "The lantern flickered at dawn.",
    context_text: str = "Write a tense short story about a lantern.",
    input_paths: tuple[Path, Path, Path] | None = None,
    prompt_rendering_version: int = runner.PROMPT_RENDERING_VERSION,
    task_contract_enabled: bool = True,
    response_schema_mode: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Materialize a complete run from source inputs; never edits an existing run."""

    run = (run_dir or root / "run").resolve()
    if run.exists():
        raise ValueError(f"Fixture run path already exists: {run}")
    if input_paths is None:
        inputs = root / f"inputs-{artifact_id}"
        if inputs.exists():
            raise ValueError(f"Fixture input path already exists: {inputs}")
        artifact, context, task_path = inputs / "source.md", inputs / "prompt.md", inputs / "task.json"
        inputs.mkdir(parents=True)
        artifact.write_text(artifact_text, encoding="utf-8")
        context.write_text(context_text, encoding="utf-8")
        task = {
            "contract_version": 1,
            "contract_id": f"fixture-{artifact_id}",
            "artifact_id": artifact_id,
            "context": {
                "artifact_kind": "short prose fiction", "declared_scope": "complete short story",
                "completion_status": "complete", "background": [], "constraints": [], "audience": [],
            },
            "preferences": [], "priorities": [],
            "weighted_goals": [{
                "goal_id": "prompt_response", "atomic_question": "Does the story respond to its originating prompt?",
                "weight": 2.0,
                "source": {"kind": "driving_prompt", "reference": "fixture prompt", "exact_excerpt": context_text},
                "applies_to": ["whole artifact"], "rationale": "Fixture task relevance.",
            }],
            "binding_requirements": [],
        }
        write_json(task_path, task)
    else:
        artifact, context, task_path = (path.resolve() for path in input_paths)
        if not all(path.is_file() for path in (artifact, context, task_path)):
            raise ValueError("Fixture source inputs must exist")
        artifact_text = artifact.read_text(encoding="utf-8")
        context_text = context.read_text(encoding="utf-8")
        task = json.loads(task_path.read_text(encoding="utf-8"))
        if not isinstance(task, dict) or task.get("artifact_id") != artifact_id:
            raise ValueError("Fixture task input must bind the artifact identity")
    task_for_scoring = task if task_contract_enabled else None
    scope_override = task_path.with_name("scope-compatibility.json")
    override = {
        "format_version": 1,
        "artifact_id": artifact_id,
        "bundle_id": "prose.short_story",
        "task_contract_sha256": hashlib.sha256(task_path.read_bytes()).hexdigest(),
        "contract_id": task["contract_id"],
        "artifact_kind": task["context"]["artifact_kind"],
        "declared_scope": task["context"]["declared_scope"],
        "compatibility_mode": "reviewed_override",
        "decision_id": "fixture-reviewed-compatibility",
        "reviewer": "fixture",
        "reason": "Fixture binds an explicit reviewed compatibility decision.",
    }
    if task_contract_enabled:
        write_json(scope_override, override)
    binary_prompt = prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"
    response_schema = schema_dir() / "hbq_judge_response.schema.json"
    frozen = {
        "artifact": binding(artifact), "contexts": [binding(context)],
        "task_contract": binding(task_path) if task_contract_enabled else None,
        "scope_compatibility_override": binding(scope_override) if task_contract_enabled else None,
        "registry": binding(registry_path()), "bundles": binding(bundles_path()), "prompts": [binding(binary_prompt)],
        "response_schema": binding(response_schema), "score_v1_schema": binding(schema_dir() / "hbq_score_report.schema.json"),
        "score_v2_schema": binding(schema_dir() / "hbq_score_report.v2.schema.json"), "weight_profile": None,
        "execution": {"artifact_id": artifact_id, "bundle_id": "prose.short_story", "batch_size": 32,
                      "batch_attempts": 3, "strict_ai": False, "provider": "codex", "model": "gpt-5.6-sol",
                      "reasoning": "high", "codex_bin": "codex"},
        "provider": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"},
    }
    modules = core.load_modules(registry_path())
    bundle = core.resolve_bundle(core.load_bundles(bundles_path()), "prose.short_story")
    modules, bundle, weight = materialize_weight_profile(modules, bundle, None)
    compiled = core.compile_bundle(modules, bundle, task_contract=task_for_scoring)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order.get(str(item.get("role")), 99))
    if response_schema_mode is not None:
        if response_schema_mode != "batch_question_ids_v1" or prompt_rendering_version != runner.PROMPT_RENDERING_VERSION:
            raise ValueError("Unsupported opt-in verifier fixture configuration")
        frozen["execution"]["response_schema_mode"] = response_schema_mode
        calls = 0

        def fake_codex(*, response_schema: Path, **_kwargs: Any) -> tuple[str, dict[str, Any]]:
            nonlocal calls
            calls += 1
            schema = json.loads(response_schema.read_text(encoding="utf-8"))
            ids = schema["properties"]["verdicts"]["items"]["properties"]["question_id"]["enum"]
            content = json.dumps({"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8,
                "evidence": [{"kind": "exact_quote", "reference": "story", "exact_quote": "lantern", "summary": None}],
                "note": "grounded"} for question_id in ids]}, ensure_ascii=False)
            return content, {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"{provider_session_prefix}-{calls}"}}

        with patch.object(runner, "_call_codex", fake_codex):
            runner.run_judge(
                artifact_path=artifact,
                context_paths=(context,),
                task_contract_path=task_path if task_contract_enabled else None,
                scope_compatibility_override_path=scope_override if task_contract_enabled else None,
                bundle_id="prose.short_story",
                provider="codex",
                model="gpt-5.6-sol",
                output_dir=run,
                registry=registry_path(),
                bundles=bundles_path(),
                question_ids=[str(item["question"]["id"]) for item in questions],
                batch_size=32,
                batch_attempts=3,
                reasoning="high",
                allow_remote=True,
                artifact_id=artifact_id,
                response_schema_mode=response_schema_mode,
            )
        if calls != (len(questions) + 31) // 32:
            raise AssertionError("Opt-in fixture did not execute every frozen batch")
        completed = core.load_verdicts(run / "verdicts.jsonl")
        descendant = scoring_v2.score_bundle(modules, bundle, completed, artifact_id=artifact_id, task_contract=task_for_scoring)
        descendant["weight_profile"] = weight
        descendant["parent_score_sha256"] = hashlib.sha256((run / "score.json").read_bytes()).hexdigest()
        write_json(run / "score.v2.json", descendant)
        return run, frozen
    artifact_record, context_record = runner._read_text_record(artifact), runner._read_text_record(context)
    task_record = None
    task_context = None
    scope_compatibility = None
    if task_contract_enabled:
        task_record = runner._manifest_inputs([runner._read_text_record(task_path)])[0]
        task_record["contract_id"] = task["contract_id"]
        task_context = runner._task_contract_judge_context(task)
        scope_compatibility = runner._scope_compatibility_override(
            scope_override,
            artifact_id=artifact_id,
            bundle_id="prose.short_story",
            task_contract=task,
            task_contract_record=task_record,
        )
    prompt_records = [runner._read_text_record(binary_prompt)]
    binary = "\n\n".join(str(item["text"]).strip() for item in prompt_records)
    configuration = {
        "artifact": runner._manifest_inputs([artifact_record])[0], "contexts": runner._manifest_inputs([context_record]),
        "task_contract": task_record,
        "weight_profile": weight, "bundle_id": "prose.short_story",
        "bundle_version": bundle["version"], "question_ids": [str(item["question"]["id"]) for item in questions],
        "provider": "codex", "model": "gpt-5.6-sol", "endpoint": None, "api_key_env": None, "temperature": None,
        "allow_model_mismatch": None, "reasoning": "high", "codex_bin": "codex", "batch_size": 32,
        "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY,
        "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "artifact_id": artifact_id,
        "judge_id": "codex:gpt-5.6-sol", "strict_ai": False,
        "prompts": runner._manifest_inputs(prompt_records),
        "response_schema": runner._manifest_inputs([runner._read_text_record(response_schema)])[0],
        "questions_sha256": hashlib.sha256(runner._json_bytes(runner._question_payload(questions))).hexdigest(),
        "compiled_bundle_sha256": hashlib.sha256(runner._json_bytes(compiled)).hexdigest(),
    }
    if prompt_rendering_version == runner.PROMPT_RENDERING_VERSION:
        configuration.update({
            "task_contract_judge_context": runner._task_contract_judge_context_record(task_context),
            "scope_compatibility": scope_compatibility,
            "prompt_rendering_version": runner.PROMPT_RENDERING_VERSION,
        })
    elif prompt_rendering_version != runner.LEGACY_PROMPT_RENDERING_VERSION:
        raise ValueError("Unsupported fixture prompt rendering version")
    write_json(run / "run.json", {"format_version": 4 if prompt_rendering_version == runner.PROMPT_RENDERING_VERSION else 3, "run_id": f"fixture-{artifact_id}",
                                    "config_sha256": hashlib.sha256(runner._json_bytes(configuration)).hexdigest(),
                                    "configuration": configuration})
    completed: list[dict[str, Any]] = []
    previous = None
    for batch, start in enumerate(range(0, len(questions), 32), start=1):
        selected = questions[start:start + 32]
        ids = [str(item["question"]["id"]) for item in selected]
        payload = {"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 0.8,
                   "evidence": [{"kind": "exact_quote", "reference": "story", "exact_quote": "lantern", "summary": None}],
                   "note": "grounded"} for question_id in ids]}
        raw = json.dumps(payload, ensure_ascii=False)
        audit: list[dict[str, Any]] = []
        normalized = runner._normalize_batch(payload, expected_ids=ids, artifact_id=artifact_id, bundle_id="prose.short_story",
            judge_id="codex:gpt-5.6-sol", run_id=f"fixture-{artifact_id}", artifact_text=artifact_text,
            context_texts=[context_text], normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
        prompt = runner._render_prompt(binary_prompt=binary, artifact={"name": artifact.name, "text": artifact_text},
            contexts=[{"name": context.name, "text": context_text}], bundle_id="prose.short_story", artifact_id=artifact_id, questions=selected,
            task_contract_context=(task_context if prompt_rendering_version == runner.PROMPT_RENDERING_VERSION else None),
            prompt_rendering_version=prompt_rendering_version)
        prompt_bytes = prompt.encode("utf-8")
        response = run / "responses" / f"batch-{batch:04d}.accepted-0001.message.txt"
        response.parent.mkdir(parents=True, exist_ok=True); response.write_text(raw, encoding="utf-8")
        provider_artifact = run / "responses" / f"batch-{batch:04d}.provider.txt"; provider_artifact.write_text("provider receipt", encoding="utf-8")
        completed.extend(normalized)
        record = {"format_version": 4, "batch": batch, "retry_policy": {"batch_attempts": 3}, "accepted_attempt": 1,
            "question_ids": ids, "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "base_prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(), "effective_prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
            "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "validation_feedback": None,
            "normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": audit,
            "response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "response_artifact": {"path": response.relative_to(run).as_posix(), "bytes": response.stat().st_size, "sha256": hashlib.sha256(response.read_bytes()).hexdigest()},
            "rejected_chain": {"count": 0, "head_sha256": None}, "previous_checkpoint_sha256": previous,
            "verdicts_sha256": hashlib.sha256(runner._verdicts_bytes(completed)).hexdigest(),
            "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"{provider_session_prefix}-{batch}"},
                         "provider_artifacts": {"metadata": {"path": provider_artifact.relative_to(run).as_posix(), "bytes": provider_artifact.stat().st_size, "sha256": hashlib.sha256(provider_artifact.read_bytes()).hexdigest()}}},
            "normalized_verdicts": normalized}
        checkpoint = run / "responses" / f"batch-{batch:04d}.json"; write_json(checkpoint, record)
        checkpoint.with_suffix(".prompt.txt.gz").write_bytes(gzip.compress(prompt_bytes, mtime=0))
        previous = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (run / "verdicts.jsonl").write_bytes(runner._verdicts_bytes(completed))
    parent = core.score_bundle(modules, bundle, completed, artifact_id=artifact_id, task_contract=task_for_scoring); parent["weight_profile"] = weight
    write_json(run / "score.json", parent)
    descendant = scoring_v2.score_bundle(modules, bundle, completed, artifact_id=artifact_id, task_contract=task_for_scoring)
    descendant["weight_profile"] = weight; descendant["parent_score_sha256"] = hashlib.sha256((run / "score.json").read_bytes()).hexdigest()
    write_json(run / "score.v2.json", descendant)
    return run, frozen
