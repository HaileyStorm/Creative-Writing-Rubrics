"""Offline verifier for completed binary HBQ runs bound to frozen inputs."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from . import core, runner, scoring_v2
from .runner_v2 import _canonical_projection
from .weights import materialize_weight_profile


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise core.HBQError(f"Invalid verifier JSON: {path}") from exc
    if not isinstance(value, dict):
        raise core.HBQError(f"Verifier JSON must be an object: {path}")
    return value


def _bound_file(value: Any, *, label: str) -> Path:
    if not isinstance(value, Mapping):
        raise core.HBQError(f"Frozen {label} binding is missing")
    path, size, digest = value.get("path"), value.get("bytes"), value.get("sha256")
    if not isinstance(path, str) or not isinstance(size, int) or isinstance(size, bool) or not isinstance(digest, str):
        raise core.HBQError(f"Frozen {label} binding is malformed")
    resolved = Path(path).resolve()
    if not resolved.is_file() or resolved.stat().st_size != size or _sha256(resolved) != digest:
        raise core.HBQError(f"Frozen {label} bytes drifted")
    return resolved


def _schema_errors(report: Mapping[str, Any], schema_path: Path) -> None:
    errors = list(Draft202012Validator(_json(schema_path)).iter_errors(report))
    if errors:
        raise core.HBQError(f"Score report violates {schema_path.name}: {errors[0].message}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest_record(path: Path) -> dict[str, Any]:
    return runner._manifest_inputs([runner._read_text_record(path)])[0]


def _execution(frozen: Mapping[str, Any]) -> dict[str, Any]:
    value = frozen.get("execution")
    required = {"artifact_id", "bundle_id", "batch_size", "batch_attempts", "strict_ai", "provider", "model", "reasoning", "codex_bin"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise core.HBQError("Frozen execution contract is malformed")
    if not isinstance(value["artifact_id"], str) or not value["artifact_id"] or not isinstance(value["bundle_id"], str) or not value["bundle_id"]:
        raise core.HBQError("Frozen execution identity is malformed")
    if not isinstance(value["batch_size"], int) or isinstance(value["batch_size"], bool) or value["batch_size"] < 1:
        raise core.HBQError("Frozen batch size is malformed")
    if not isinstance(value["batch_attempts"], int) or isinstance(value["batch_attempts"], bool) or value["batch_attempts"] < 1:
        raise core.HBQError("Frozen retry policy is malformed")
    if not isinstance(value["strict_ai"], bool) or value["provider"] != "codex" or not all(isinstance(value[key], str) and value[key] for key in ("model", "reasoning", "codex_bin")):
        raise core.HBQError("Frozen provider execution contract is malformed")
    return dict(value)


def _bound_files(value: Any, *, label: str) -> list[Path]:
    if not isinstance(value, list) or not value:
        raise core.HBQError(f"Frozen {label} bindings are missing")
    return [_bound_file(item, label=label) for item in value]


def _configuration(
    *,
    execution: Mapping[str, Any],
    artifact: Path,
    contexts: Sequence[Path],
    task_contract: Path | None,
    prompts: Sequence[Path],
    response_schema: Path,
    modules: Sequence[dict[str, Any]],
    bundle: Mapping[str, Any],
    weight_audit: Mapping[str, Any],
    questions: Sequence[Mapping[str, Any]],
    compiled: Mapping[str, Any],
    prompt_rendering_version: int,
    scope_compatibility: Mapping[str, Any] | None,
) -> dict[str, Any]:
    task_record = _manifest_record(task_contract) if task_contract is not None else None
    if task_record is not None:
        task = core.load_data(task_contract)
        if not isinstance(task, Mapping) or task.get("artifact_id") != execution["artifact_id"]:
            raise core.HBQError("Frozen task contract does not bind the artifact identity")
        task_record["contract_id"] = task.get("contract_id")
    prompt_records = [runner._read_text_record(path) for path in prompts]
    expected_prompt_names = ["JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"] if execution["strict_ai"] else ["BINARY_EVALUATION_PROMPT.md"]
    if [path.name for path in prompts] != expected_prompt_names:
        raise core.HBQError("Frozen prompt bindings do not match the strict execution contract")
    binary_prompt = "\n\n".join(str(item["text"]).strip() for item in prompt_records)
    task_context = (
        runner._task_contract_judge_context(task)
        if task is not None and prompt_rendering_version == runner.PROMPT_RENDERING_VERSION
        else None
    )
    configuration = {
        "artifact": _manifest_record(artifact),
        "contexts": [_manifest_record(path) for path in contexts],
        "task_contract": task_record,
        "weight_profile": dict(weight_audit),
        "bundle_id": execution["bundle_id"],
        "bundle_version": bundle.get("version"),
        "question_ids": [str(item["question"]["id"]) for item in questions],
        "provider": "codex",
        "model": execution["model"],
        "endpoint": None,
        "api_key_env": None,
        "temperature": None,
        "allow_model_mismatch": None,
        "reasoning": execution["reasoning"],
        "codex_bin": execution["codex_bin"],
        "batch_size": execution["batch_size"],
        "retry_policy": {"batch_attempts": execution["batch_attempts"]},
        "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY,
        "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY,
        "artifact_id": execution["artifact_id"],
        "judge_id": f"codex:{execution['model']}",
        "strict_ai": execution["strict_ai"],
        "prompts": runner._manifest_inputs(prompt_records),
        "response_schema": _manifest_record(response_schema),
        "questions_sha256": hashlib.sha256(runner._json_bytes(runner._question_payload(questions))).hexdigest(),
        "compiled_bundle_sha256": hashlib.sha256(runner._json_bytes(compiled)).hexdigest(),
        "_binary_prompt": binary_prompt,
    }
    if prompt_rendering_version == runner.PROMPT_RENDERING_VERSION:
        configuration.update(
            {
                "task_contract_judge_context": runner._task_contract_judge_context_record(task_context),
                "scope_compatibility": (
                    dict(scope_compatibility) if scope_compatibility is not None else None
                ),
                "prompt_rendering_version": prompt_rendering_version,
            }
        )
    return configuration


def _scope_compatibility(
    frozen: Mapping[str, Any],
    *,
    task: Mapping[str, Any] | None,
    task_contract_path: Path | None,
    artifact_id: str,
    bundle_id: str,
    registry_path: Path,
    bundles_path: Path,
    artifact_path: Path,
    context_paths: Sequence[Path],
) -> dict[str, Any] | None:
    if task is None:
        if frozen.get("scope_compatibility_override") is not None:
            raise core.HBQError("Frozen scope compatibility override requires a task contract")
        return None
    if task_contract_path is None:
        raise core.HBQError("Frozen task contract path is missing")
    longform_proof = frozen.get("longform_scope_compatibility_proof")
    if longform_proof is not None:
        if frozen.get("scope_compatibility_override") is not None:
            raise core.HBQError("Frozen scope compatibility evidence is ambiguous")
        if not isinstance(longform_proof, Mapping):
            raise core.HBQError("Frozen long-form scope compatibility proof is malformed")
        contract_record = _manifest_record(task_contract_path)
        contract_record["contract_id"] = task.get("contract_id")
        return runner._scope_compatibility(
            task_contract=task,
            task_contract_record=contract_record,
            artifact_id=artifact_id,
            bundle_id=bundle_id,
            scope_compatibility_override_path=None,
            longform_scope_compatibility_proof=longform_proof,
            artifact_path=artifact_path,
            registry_path=registry_path,
            bundles_path=bundles_path,
            context_paths=context_paths,
        )
    override_path = _bound_file(
        frozen.get("scope_compatibility_override"), label="scope compatibility override"
    )
    contract_record = _manifest_record(task_contract_path)
    contract_record["contract_id"] = task.get("contract_id")
    return runner._scope_compatibility_override(
        override_path,
        artifact_id=artifact_id,
        bundle_id=bundle_id,
        task_contract=task,
        task_contract_record=contract_record,
    )


def _require_v4_artifacts(run_dir: Path) -> None:
    checkpoints = sorted((run_dir / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
    if not checkpoints:
        raise core.HBQError("Run has no accepted v4 checkpoints")
    for path in [*checkpoints, *(run_dir / "responses" / "rejected").glob("batch-*/attempt-*.json")]:
        if _json(path).get("format_version") != 4:
            raise core.HBQError(f"Fresh verifier rejects non-v4 checkpoint: {path.name}")


def _relative_commitment(run_dir: Path, path: Path) -> dict[str, Any]:
    try:
        relative = path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError as exc:
        raise core.HBQError("Verifier artifact path escapes the run") from exc
    return {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _provider_commitments(run_dir: Path, record: Mapping[str, Any]) -> list[dict[str, Any]]:
    runner._validate_provider_artifacts(run_dir, record)
    provider = record.get("provider")
    artifacts = provider.get("provider_artifacts") if isinstance(provider, Mapping) else None
    if artifacts is None:
        return []
    result: list[dict[str, Any]] = []
    for name, item in sorted(artifacts.items()):
        if not isinstance(item, Mapping):
            raise core.HBQError("Provider artifact commitment is malformed")
        result.append({"name": name, "artifact": dict(item)})
    return result


def _provider_sessions(run_dir: Path, *, expected: Mapping[str, str], checkpoint_paths: Sequence[Path]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sessions: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    provider_artifacts: list[dict[str, Any]] = []
    for batch, checkpoint in enumerate(checkpoint_paths, start=1):
        record = _json(checkpoint)
        provider = record.get("provider")
        reported = provider.get("reported") if isinstance(provider, Mapping) else None
        if not isinstance(reported, Mapping) or any(reported.get(key) != value for key, value in expected.items()):
            raise core.HBQError(f"Checkpoint provider identity drifted: {checkpoint.name}")
        session = reported.get("session_id")
        if not isinstance(session, str) or not session.strip():
            raise core.HBQError(f"Checkpoint lacks a provider session: {checkpoint.name}")
        sessions.append({"batch": batch, "kind": "accepted", "session_id_sha256": hashlib.sha256(session.encode("utf-8")).hexdigest()})
        provider_artifacts.extend({"batch": batch, "kind": "accepted", **item} for item in _provider_commitments(run_dir, record))
        for path, rejected_record in runner._rejected_records(run_dir, batch):
            rejected.append(_relative_commitment(run_dir, path))
            provider_artifacts.extend({"batch": batch, "kind": "rejected", **item} for item in _provider_commitments(run_dir, rejected_record))
            rejected_provider = rejected_record.get("provider")
            rejected_reported = rejected_provider.get("reported") if isinstance(rejected_provider, Mapping) else None
            if not isinstance(rejected_reported, Mapping) or any(rejected_reported.get(key) != value for key, value in expected.items()):
                raise core.HBQError(f"Rejected provider identity drifted: {path.name}")
            session = rejected_reported.get("session_id")
            if not isinstance(session, str) or not session.strip():
                raise core.HBQError(f"Rejected provider session is malformed: {path.name}")
            sessions.append({"batch": batch, "kind": "rejected", "session_id_sha256": hashlib.sha256(session.encode("utf-8")).hexdigest()})
    hashes = [item["session_id_sha256"] for item in sessions]
    if len(hashes) != len(set(hashes)):
        raise core.HBQError("Run reuses provider sessions across accepted or rejected attempts")
    return sessions, rejected, provider_artifacts


def verify_binary_run(run_dir: str | Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Verify a run directory exclusively from frozen inputs and raw artifacts."""

    directory = Path(run_dir).resolve()
    manifest = _json(directory / "run.json")
    manifest_format_version = manifest.get("format_version")
    if manifest_format_version not in {3, 4}:
        raise core.HBQError("Fresh verifier requires a v3 or v4 run manifest")
    execution = _execution(frozen)
    artifact = _bound_file(frozen.get("artifact"), label="artifact")
    registry = _bound_file(frozen.get("registry"), label="registry")
    bundles = _bound_file(frozen.get("bundles"), label="bundles")
    context_paths = _bound_files(frozen.get("contexts"), label="context")
    task_contract = frozen.get("task_contract")
    task_contract_path = _bound_file(task_contract, label="task contract") if task_contract is not None else None
    prompt_paths = _bound_files(frozen.get("prompts"), label="prompt")
    response_schema = _bound_file(frozen.get("response_schema"), label="response schema")
    expected_provider = frozen.get("provider")
    if not isinstance(expected_provider, Mapping) or set(expected_provider) != {"provider", "model", "reasoning_effort"} or not all(isinstance(value, str) and value for value in expected_provider.values()):
        raise core.HBQError("Frozen provider expectation is malformed")
    if dict(expected_provider) != {"provider": "openai", "model": execution["model"], "reasoning_effort": execution["reasoning"]}:
        raise core.HBQError("Frozen provider expectation diverges from the Codex execution contract")
    modules = core.load_modules(registry)
    bundle = core.resolve_bundle(core.load_bundles(bundles), execution["bundle_id"])
    frozen_weight_profile = frozen.get("weight_profile")
    materialized_modules, materialized_bundle, weight_audit = materialize_weight_profile(
        modules, bundle, frozen_weight_profile
    )
    task = core.load_data(task_contract_path) if task_contract_path is not None else None
    if task is not None and not isinstance(task, Mapping):
        raise core.HBQError("Frozen task contract must be an object")
    if task is not None:
        errors = sorted(
            Draft202012Validator(core.load_data(runner.schema_dir() / "hbq_task_contract.schema.json")).iter_errors(task),
            key=lambda error: list(error.path),
        )
        if errors:
            raise core.HBQError(f"Frozen task contract violates its strict schema: {errors[0].message}")
    compiled = core.compile_bundle(materialized_modules, materialized_bundle, task_contract=task)
    role_order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: role_order.get(str(item.get("role")), 99))
    prompt_rendering_version = (
        runner.PROMPT_RENDERING_VERSION
        if manifest_format_version == 4
        else runner.LEGACY_PROMPT_RENDERING_VERSION
    )
    scope_compatibility = (
        _scope_compatibility(
            frozen,
            task=task,
            task_contract_path=task_contract_path,
            artifact_id=execution["artifact_id"],
            bundle_id=execution["bundle_id"],
            registry_path=registry,
            bundles_path=bundles,
            artifact_path=artifact,
            context_paths=context_paths,
        )
        if manifest_format_version == 4
        else None
    )
    if scope_compatibility is not None and scope_compatibility.get("mode") == "longform_prevalidated_route":
        contract_questions = compiled.get("task_contract")
        actual_dynamic_ids = (
            [*contract_questions.get("weighted_goal_ids", []), *contract_questions.get("binding_requirement_ids", [])]
            if isinstance(contract_questions, Mapping)
            else []
        )
        if actual_dynamic_ids != scope_compatibility.get("selected_dynamic_question_ids"):
            raise core.HBQError("Long-form scope proof does not bind the exact selected dynamic task questions")
    expected_configuration = _configuration(execution=execution, artifact=artifact, contexts=context_paths, task_contract=task_contract_path, prompts=prompt_paths, response_schema=response_schema, modules=materialized_modules, bundle=materialized_bundle, weight_audit=weight_audit, questions=questions, compiled=compiled, prompt_rendering_version=prompt_rendering_version, scope_compatibility=scope_compatibility)
    binary_prompt = expected_configuration.pop("_binary_prompt")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping) or manifest.get("config_sha256") != hashlib.sha256(runner._json_bytes(configuration)).hexdigest():
        raise core.HBQError("Run manifest configuration binding is invalid")
    if dict(configuration) != expected_configuration:
        raise core.HBQError("Run configuration does not independently match its frozen inputs")
    if configuration.get("question_ids") != [str(item["question"]["id"]) for item in questions]:
        raise core.HBQError("Run does not contain the complete nondiagnostic question set")
    if (directory / "diagnostic.json").exists():
        raise core.HBQError("Completed full run must not contain a diagnostic subset report")
    _require_v4_artifacts(directory)
    checkpoint_paths = sorted((directory / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
    expected_count = (len(questions) + execution["batch_size"] - 1) // execution["batch_size"]
    if len(checkpoint_paths) != expected_count:
        raise core.HBQError("Run checkpoint count does not match the complete frozen question set")
    prompt_commitments: list[dict[str, Any]] = []
    for batch, checkpoint in enumerate(checkpoint_paths, start=1):
        record = _json(checkpoint)
        start = (batch - 1) * execution["batch_size"]
        batch_questions = questions[start:start + execution["batch_size"]]
        expected_ids = [str(item["question"]["id"]) for item in batch_questions]
        prompt_path = checkpoint.with_suffix(".prompt.txt.gz")
        try:
            prompt = gzip.decompress(prompt_path.read_bytes()).decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise core.HBQError(f"Cannot read exact frozen batch prompt: {prompt_path.name}") from exc
        expected_prompt = runner._render_prompt(binary_prompt=binary_prompt, artifact={"name": artifact.name, "text": artifact.read_text(encoding="utf-8")}, contexts=[{"name": path.name, "text": path.read_text(encoding="utf-8")} for path in context_paths], bundle_id=execution["bundle_id"], artifact_id=execution["artifact_id"], questions=batch_questions, task_contract_context=(runner._task_contract_judge_context(task) if task is not None and prompt_rendering_version == runner.PROMPT_RENDERING_VERSION else None), prompt_rendering_version=prompt_rendering_version)
        if record.get("batch") != batch or record.get("question_ids") != expected_ids or prompt != expected_prompt:
            raise core.HBQError("Checkpoint does not bind the exact frozen batch slice and prompt bytes")
        prompt_commitments.append(_relative_commitment(directory, prompt_path))
    verdicts, checkpoint_count, chain_head = runner._load_checkpoints(directory, artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[path.read_text(encoding="utf-8") for path in context_paths], batch_attempts=execution["batch_attempts"], normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
    persisted = core.load_verdicts(directory / "verdicts.jsonl")
    if verdicts != persisted:
        raise core.HBQError("Checkpoint verdicts do not match verdicts.jsonl")
    parent = core.score_bundle(materialized_modules, materialized_bundle, persisted, artifact_id=execution["artifact_id"], task_contract=task)
    parent["weight_profile"] = weight_audit
    score_path = directory / "score.json"
    if _json(score_path) != parent:
        raise core.HBQError("score.json does not match deterministic v1 recomputation")
    _schema_errors(parent, _bound_file(frozen.get("score_v1_schema"), label="v1 score schema"))
    descendant_path = directory / "score.v2.json"
    descendant = _json(descendant_path)
    expected_v2 = scoring_v2.score_bundle(materialized_modules, materialized_bundle, persisted, artifact_id=execution["artifact_id"], task_contract=task)
    expected_v2["weight_profile"] = weight_audit
    expected_v2["parent_score_sha256"] = _sha256(score_path)
    if descendant != expected_v2 or _canonical_projection(descendant) != _canonical_projection(parent):
        raise core.HBQError("score.v2.json has invalid parent hash or canonical parity")
    _schema_errors(descendant, _bound_file(frozen.get("score_v2_schema"), label="v2 score schema"))
    sessions, rejected, provider_artifacts = _provider_sessions(directory, expected=dict(expected_provider), checkpoint_paths=checkpoint_paths)
    accepted_artifacts = []
    for checkpoint in checkpoint_paths:
        record = _json(checkpoint)
        response = record.get("response_artifact")
        if not isinstance(response, Mapping) or not isinstance(response.get("path"), str):
            raise core.HBQError("Accepted response artifact commitment is malformed")
        accepted_artifacts.append(_relative_commitment(directory, directory / response["path"]))
    commitments = {"verdicts": _relative_commitment(directory, directory / "verdicts.jsonl"), "prompts": prompt_commitments, "accepted_response_artifacts": accepted_artifacts, "rejected_attempts": rejected, "provider_artifacts": provider_artifacts}
    return {
        "run_sha256": _sha256(directory / "run.json"),
        "score_sha256": _sha256(score_path),
        "score_v2_sha256": _sha256(descendant_path),
        "verdict_count": len(persisted),
        "checkpoint_count": checkpoint_count,
        "rejected_attempt_count": len(rejected),
        "sessions": sessions,
        "session_list_commitment_sha256": hashlib.sha256(_canonical(sessions)).hexdigest(),
        "checkpoint_chain_head_sha256": chain_head,
        "commitments": commitments,
        "calibration": {"status": "UNAVAILABLE"},
    }
