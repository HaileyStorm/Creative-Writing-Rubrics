"""Provider-free recovered-prefix admission with explicit historical schema data."""

from __future__ import annotations

import hashlib
import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SELF = Path(__file__).resolve()
RECOVERED = ROOT / "baseline_recovered_study.py"
RECOVERED_SHA256 = "573fbd9b05659aff80c7db4dfae9cf7c7c549b7e28d99260c50a98aa458bb8b3"
SHARED = ROOT / "baseline_native_data_admission.py"
SHARED_SHA256 = "719dd0af186f38bdeff2ee08cf9b90275003c28cd08b1c7abd246882f585b366"


def _load(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError(f"{path.name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{path.name} cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    if path.read_bytes() != raw:
        raise ValueError(f"{path.name} changed while loading")
    return module


def _recovered() -> ModuleType:
    return _load(RECOVERED, RECOVERED_SHA256, "_baseline_recovered_data_admission_frozen")


def _shared() -> ModuleType:
    return _load(SHARED, SHARED_SHA256, "_baseline_recovered_data_admission_shared")


def _qualification(
    *, root: Path, source: dict[str, Any], batch_size: int, expected_batches: int, runtime: Any,
    frozen: ModuleType, shared: ModuleType, bound: dict[str, Any], recovered_manifest: dict[str, Any],
    recovered_binding: dict[str, Any], recovered_manifest_sha256: str, approved_routes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    runner, core = runtime.runner, runtime.core
    before = frozen._snapshot(root, runtime)
    full_batches = frozen._batch_count(batch_size, len(runtime.questions))
    shared.require(batch_size == 8, "Exact-70 mixed replay requires batches of eight")
    shared.require(type(expected_batches) is int and not isinstance(expected_batches, bool) and 1 <= expected_batches <= full_batches, "Expected checkpoint prefix differs")
    full_pass = expected_batches == full_batches
    manifest = frozen._json(root, "run.json", runtime)
    shared.require(manifest.get("format_version") == 5, "Qualification requires current terminal lifecycle")
    config = manifest["configuration"]
    expected_ids = [item["question"]["id"] for item in runtime.questions]
    response_schema_mode = getattr(runtime, "response_schema_mode", None)
    shared.require(response_schema_mode in {None, "batch_question_ids_v1"}, "Unsupported response schema mode")
    batch_schema_records, batch_schema_raw = (runner._batch_schema_plan(expected_ids, batch_size) if response_schema_mode else ([], {}))
    expected = {
        "provider": "grok", "model": "grok-4.6", "reasoning": "high", "bundle_id": "prose.short_story",
        "artifact_id": source["opaque_story_id"], "judge_id": "grok:grok-4.6", "batch_size": batch_size,
        "question_ids": expected_ids, "retry_policy": {"batch_attempts": 1}, "attempt_lifecycle_policy": "terminal_sidecar_v1",
        "allow_unattested_reasoning": True, "strict_ai": False, "task_contract": None, "task_contract_judge_context": None,
        "scope_compatibility": None, "contexts": [], "endpoint": None, "api_key_env": None, "temperature": None,
        "allow_model_mismatch": None, "codex_bin": None, "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY,
        "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "prompt_rendering_version": runner.PROMPT_RENDERING_VERSION,
    }
    if response_schema_mode:
        expected.update(response_schema_mode=response_schema_mode, batch_response_schemas=batch_schema_records)
    shared.require(all(config.get(key) == value for key, value in expected.items()), "Run configuration differs from qualification")
    shared.require(set(config) == set(expected) | {"artifact", "weight_profile", "bundle_version", "prompts", "response_schema", "questions_sha256", "compiled_bundle_sha256", "grok_transport"}, "Run configuration shape differs")
    shared.require(manifest.get("response_schema_initialization") == "complete" if response_schema_mode else "response_schema_initialization" not in manifest, "Batch response-schema initialization is incomplete")
    shared.require(config["bundle_version"] == runtime.bundle.get("version") and manifest["config_sha256"] == shared.digest(runner._json_bytes(config)), "Run configuration binding differs")
    text = source["story_text"]
    artifact_path = Path(source["artifact_path"]).resolve()
    artifact = {"path": str(artifact_path), "name": artifact_path.name, "sha256": shared.digest(text.encode()), "bytes": len(text.encode())}
    shared.require(shared.canonical(config["artifact"]) == shared.canonical(artifact), "Story source binding differs")
    shared.require(config["compiled_bundle_sha256"] == shared.digest(runner._json_bytes(runtime.compiled)) and config["questions_sha256"] == shared.digest(runner._json_bytes(runner._question_payload(runtime.questions))), "Rubric or question binding differs")
    _, _, weight_audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, None)
    shared.require(config["weight_profile"] == weight_audit, "Qualification scoring weights differ")
    transport = config["grok_transport"]
    shared.require(set(transport) == {"protocol", "declared_sha256", "identity_evidence", "timeout"} and transport["protocol"] == "injected_grok_attempt_v1" and transport["identity_evidence"] == "caller_declared_unverified" and transport["declared_sha256"] == runtime.transport_sha256 and type(transport["timeout"]) in (int, float) and math.isfinite(transport["timeout"]) and transport["timeout"] > 0, "Transport contract differs")
    shared._metadata(config, schema_descriptor=bound["schema"])
    shared.require(not list((root / "responses/rejected").rglob("*.json")), "Qualification cannot contain rejected attempts")
    verdicts, count, head = runner._load_checkpoints(root, artifact_text=text, context_texts=[], batch_attempts=1)
    shared.require(count == expected_batches and [v["question_id"] for v in verdicts] == expected_ids[:min(len(expected_ids), expected_batches * batch_size)], "Checkpoint prefix inventory differs")
    shared.require(all(v["artifact_id"] == source["opaque_story_id"] and v["bundle_id"] == "prose.short_story" and v["judge_id"] == "grok:grok-4.6" and v["run_id"] == manifest["run_id"] for v in verdicts), "Verdict identity differs")
    runner._validate_or_reconstruct_attempt_lifecycle(root, config_sha256=manifest["config_sha256"], batch_attempts=1, reconstruct=False, strict_v5=True, require_durable=True)
    shared.require(frozen._read(root, "verdicts.jsonl", runtime) == runner._verdicts_bytes(verdicts), "Verdict aggregate differs")
    schema = runner._response_schema()
    shared.require(frozen._read(root, "response.schema.json", runtime) == runner._json_bytes(schema), "Response schema differs")
    identities: list[dict[str, Any]] = []
    allowed_files = {"run.json", "response.schema.json", "verdicts.jsonl", frozen.MANIFEST}
    for number, record in enumerate(batch_schema_records, start=1):
        shared.require(frozen._read(root, record["path"], runtime) == batch_schema_raw[number], "Batch response schema differs")
        allowed_files.add(record["path"])
    if full_pass:
        allowed_files.add("score.json")
        if (root / "score.v2.json").is_file():
            allowed_files.add("score.v2.json")
    for number in range(1, count + 1):
        if number == 1:
            checkpoint = frozen._json(root, "responses/batch-0001.json", runtime)
            shared.require(checkpoint["format_version"] == 5 and checkpoint["accepted_attempt"] == 1 and checkpoint["provider"] == {"study_recovered_quote_repair": recovered_manifest["recovery"]["study_recovered_quote_repair"]}, "Recovered checkpoint evidence differs")
            allowed_files.update({"responses/batch-0001.json", "responses/batch-0001.prompt.txt.gz", "responses/batch-0001.accepted-0001.message.txt", "responses/attempt-lifecycle/batch-0001/attempt-0001.start.json", "responses/attempt-lifecycle/batch-0001/attempt-0001.settled.json"})
            continue
        shared._admit_batch(root=root, number=number, runtime=runtime, frozen=frozen, config=config, manifest=manifest, text=text, schema=schema, batch_schema_records=batch_schema_records, verdicts=verdicts, approved_routes=approved_routes, identities=identities, allowed_files=allowed_files)
    shared._admit_pause_prompt(root=root, expected_batches=expected_batches, full_pass=full_pass, runtime=runtime, frozen=frozen, config=config, text=text, allowed_files=allowed_files)
    shared.require(set(before) == allowed_files, "Run contains missing or orphan evidence files")
    allowed_dirs = {parent.as_posix() for name in allowed_files for parent in Path(name).parents if parent != Path(".")}
    shared.require({path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()} <= allowed_dirs, "Run contains orphan evidence directories")
    shared.require(len({item["request_id_hash"] for item in identities}) == count - 1 and len({item["session_id_hash"] for item in identities}) == count - 1, "Duplicate native request/session identity")
    observed = coverage = None
    if full_pass:
        score = core.score_bundle(runtime.modules, runtime.bundle, verdicts, artifact_id=source["opaque_story_id"], task_contract=None)
        score["weight_profile"] = weight_audit
        shared.require(frozen._read(root, "score.json", runtime) == runner._json_bytes(score), "Canonical score replay differs")
        observed, coverage = score["final_score"]["observed"], score["coverage"]
        shared.require(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100 and coverage >= 0.88, "Unqualified score or coverage")
    runtime.verify()
    shared.require(frozen._snapshot(root, runtime) == before, "Run evidence changed during replay")
    return {"verdicts": [{"question_id": value["question_id"], "verdict": value["verdict"]} for value in verdicts], "score": observed, "coverage": coverage, "native_identities": identities, "run_manifest_sha256": shared.digest(frozen._read(root, "run.json", runtime)), "checkpoint_head_sha256": head, "evidence_class": "mixed_native_and_study_recovered_record_replay", "study_recovered": [recovered_binding["summary"]], "study_recovered_ordinals": [frozen.RECOVERED_ORDINAL], "native_record_count": len(identities), "study_recovered_record_count": 1, "recovered_manifest_sha256": recovered_manifest_sha256, "expected_study_recovery": recovered_binding, "runtime_data_provenance": {"adapter": {"path": str(SELF), "sha256": shared.digest(SELF.read_bytes())}, "frozen_recovered_study": {"path": str(RECOVERED), "sha256": RECOVERED_SHA256}, "shared_native_data_admission": {"path": str(SHARED), "sha256": SHARED_SHA256}, **bound}, **({"accepted_count": len(verdicts)} if not full_pass else {})}


def admit_prefix_with_runtime_data(run_root: str | Path, *, source: dict[str, Any], batch_size: int, approved_routes: dict[str, dict[str, Any]], expected_batches: int, expected_recovered_manifest_sha256: str, expected_adoption_sha256: str, expected_amendment_sha256: str, runtime: Any, snapshot_descriptor: dict[str, Any]) -> dict[str, Any]:
    """Replay an explicit recovered prefix without provider contact or source mutation."""
    frozen, shared = _recovered(), _shared()
    runtime.verify()
    bound = shared._bound_runtime_data(runtime, snapshot_descriptor)
    manifest, binding = frozen._verify_recovered(run_root, expected_recovered_manifest_sha256=expected_recovered_manifest_sha256, expected_adoption_sha256=expected_adoption_sha256, expected_amendment_sha256=expected_amendment_sha256, source=source, runtime=runtime)
    result = _qualification(root=Path(run_root).resolve(), source=source, batch_size=batch_size, expected_batches=expected_batches, runtime=runtime, frozen=frozen, shared=shared, bound=bound, recovered_manifest=manifest, recovered_binding=binding, recovered_manifest_sha256=expected_recovered_manifest_sha256, approved_routes=approved_routes)
    shared.require(frozen._inventory(manifest["original_run_root"]) == manifest["original_files"], "Original failed run changed during mixed replay")
    return result
