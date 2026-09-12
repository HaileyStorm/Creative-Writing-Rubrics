"""Provider-free V4 native admission with explicitly bound historical schema data."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SELF = Path(__file__).resolve()
NATIVE = ROOT / "native_admission.py"
NATIVE_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
LOGICAL_SCHEMA = "schema/hbq_judge_response.schema.json"
OLD_SCHEMA_SHA256 = "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854"
CURRENT_SCHEMA_SHA256 = "8896aabcd8f8a503f171d95d70117535da22ceff90400ff8698ee8b3f607edd8"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _native() -> ModuleType:
    raw = NATIVE.read_bytes()
    require(digest(raw) == NATIVE_SHA256, "frozen native admission source differs")
    spec = importlib.util.spec_from_file_location("_baseline_native_data_admission_frozen", NATIVE)
    require(spec is not None and spec.loader is not None, "frozen native admission cannot load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    require(NATIVE.read_bytes() == raw, "frozen native admission changed while loading")
    return module


def _bound_runtime_data(runtime: Any, snapshot_descriptor: dict[str, Any]) -> dict[str, Any]:
    """Bind the runtime's loaded schema to an independently supplied epoch descriptor."""
    require(isinstance(snapshot_descriptor, dict) and set(snapshot_descriptor) == {"epoch", "schema"}, "runtime data descriptor differs")
    epoch_descriptor = snapshot_descriptor["epoch"]
    schema_descriptor = snapshot_descriptor["schema"]
    require(isinstance(epoch_descriptor, dict) and set(epoch_descriptor) == {"path", "sha256"}, "runtime epoch descriptor differs")
    require(isinstance(schema_descriptor, dict) and set(schema_descriptor) == {"logical_path", "storage_path", "bytes", "sha256", "origin"}, "runtime schema descriptor differs")
    require(schema_descriptor["logical_path"] == LOGICAL_SCHEMA and schema_descriptor["sha256"] == OLD_SCHEMA_SHA256 and schema_descriptor["origin"] == "protocol_runtime_binding" and type(schema_descriptor["bytes"]) is int and schema_descriptor["bytes"] > 0, "runtime schema descriptor binding differs")
    provenance = getattr(runtime, "provenance", None)
    require(isinstance(provenance, dict) and provenance.get("evidence_class") == "constructor_verified_v4_runtime_with_explicit_historical_data_snapshot", "runtime provenance differs")
    require(provenance.get("provider_calls") == 0 and provenance.get("native_admission") is False and provenance.get("execution_authority") is False, "runtime authority differs")
    code, data = provenance.get("code"), provenance.get("data")
    require(isinstance(code, dict) and isinstance(data, dict), "runtime provenance shape differs")
    schema_pins = data.get("schema_pins")
    require(isinstance(schema_pins, list) and len(schema_pins) == 3 and schema_pins[0] == schema_descriptor, "runtime schema pin differs")
    current = data.get("current_canonical_schema")
    require(isinstance(current, dict) and current == {"path": str((REPOSITORY / LOGICAL_SCHEMA).resolve()), "sha256": CURRENT_SCHEMA_SHA256, "preserved": True}, "current canonical schema provenance differs")
    require(len((REPOSITORY / LOGICAL_SCHEMA).read_bytes()) > 0 and digest((REPOSITORY / LOGICAL_SCHEMA).read_bytes()) == CURRENT_SCHEMA_SHA256, "current canonical schema changed")
    storage = Path(schema_descriptor["storage_path"]).resolve()
    raw = storage.read_bytes()
    require(len(raw) == schema_descriptor["bytes"] and digest(raw) == schema_descriptor["sha256"], "historical schema storage differs")
    require(runtime.runner._response_schema() == json.loads(raw.decode("utf-8")), "runtime schema resolution differs")
    record = runtime.runner._read_text_record(REPOSITORY / LOGICAL_SCHEMA)
    require(isinstance(record, dict) and record.get("path") == str(storage) and record.get("bytes") == len(raw) and record.get("sha256") == OLD_SCHEMA_SHA256, "runtime schema record differs")
    epoch_path = Path(epoch_descriptor["path"]).resolve()
    epoch_raw = epoch_path.read_bytes()
    require(digest(epoch_raw) == epoch_descriptor["sha256"], "runtime epoch differs")
    epoch = json.loads(epoch_raw)
    require(isinstance(epoch, dict) and epoch.get("old_runtime_loader") == code.get("historical_v4_runtime_loader") and epoch.get("old_runtime_manifest", {}).get("sha256") == code.get("manifest_sha256"), "runtime epoch/code binding differs")
    return {"epoch": {"path": str(epoch_path), "sha256": digest(epoch_raw)}, "schema": schema_descriptor, "code": code, "data": {"snapshot_manifest": data.get("snapshot_manifest"), "current_canonical_schema": current}}


def _metadata(config: dict[str, Any], *, schema_descriptor: dict[str, Any]) -> None:
    schema = config["response_schema"]
    expected_schema = {"name": Path(LOGICAL_SCHEMA).name, "path": str((REPOSITORY / LOGICAL_SCHEMA).resolve()), "sha256": schema_descriptor["sha256"], "bytes": schema_descriptor["bytes"]}
    require(canonical([schema]) == canonical([expected_schema]), "Judge instruction/schema metadata differs")
    relative = "prompts/judge/BINARY_EVALUATION_PROMPT.md"
    raw = (REPOSITORY / relative).read_bytes()
    expected_prompt = {"name": Path(relative).name, "path": str((REPOSITORY / relative).resolve()), "sha256": digest(raw), "bytes": len(raw)}
    require(canonical(config["prompts"]) == canonical([expected_prompt]), "Judge instruction/schema metadata differs")


def _admit_replay_with_runtime_data(
    run_root: str | Path, *, source: dict[str, Any], batch_size: int, approved_routes: dict[str, dict[str, Any]],
    expected_batches: int, runtime: Any, runtime_data: dict[str, Any], frozen: ModuleType,
) -> dict[str, Any]:
    runtime.verify()
    bound = _bound_runtime_data(runtime, runtime_data)
    root = Path(run_root).resolve()
    before = frozen._snapshot(root, runtime)
    runner, core = runtime.runner, runtime.core
    full_batches = frozen._batch_count(batch_size, len(runtime.questions))
    require(type(expected_batches) is int and not isinstance(expected_batches, bool) and 1 <= expected_batches <= full_batches, "Expected checkpoint prefix differs")
    full_pass = expected_batches == full_batches
    manifest = frozen._json(root, "run.json", runtime)
    require(manifest.get("format_version") == 5, "Qualification requires current terminal lifecycle")
    config = manifest["configuration"]
    expected_ids = [item["question"]["id"] for item in runtime.questions]
    response_schema_mode = getattr(runtime, "response_schema_mode", None)
    require(response_schema_mode in {None, "batch_question_ids_v1"}, "Unsupported response schema mode")
    batch_schema_records, batch_schema_raw = [], {}
    if response_schema_mode is not None:
        batch_schema_records, batch_schema_raw = runner._batch_schema_plan(expected_ids, batch_size)
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
    if response_schema_mode is not None:
        expected["response_schema_mode"] = response_schema_mode
        expected["batch_response_schemas"] = batch_schema_records
    require(all(config.get(key) == value for key, value in expected.items()), "Run configuration differs from qualification")
    require(set(config) == set(expected) | {"artifact", "weight_profile", "bundle_version", "prompts", "response_schema", "questions_sha256", "compiled_bundle_sha256", "grok_transport"}, "Run configuration shape differs")
    if response_schema_mode is None:
        require("response_schema_initialization" not in manifest, "Generic schema run has batch initialization state")
    else:
        require(manifest.get("response_schema_initialization") == "complete", "Batch response-schema initialization is incomplete")
    require(config["bundle_version"] == runtime.bundle.get("version"), "Bundle version differs")
    require(manifest["config_sha256"] == digest(runner._json_bytes(config)), "Run configuration hash differs")
    text = source["story_text"]
    artifact_path = Path(source["artifact_path"]).resolve()
    expected_artifact = {"path": str(artifact_path), "name": artifact_path.name, "sha256": digest(text.encode()), "bytes": len(text.encode())}
    require(canonical(config["artifact"]) == canonical(expected_artifact), "Story source binding differs")
    require(config["compiled_bundle_sha256"] == digest(runner._json_bytes(runtime.compiled)), "Compiled rubric differs")
    require(config["questions_sha256"] == digest(runner._json_bytes(runner._question_payload(runtime.questions))), "Question payload differs")
    _, _, weight_audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, None)
    require(config["weight_profile"] == weight_audit, "Qualification scoring weights differ")
    transport = config["grok_transport"]
    require(set(transport) == {"protocol", "declared_sha256", "identity_evidence", "timeout"} and transport["protocol"] == "injected_grok_attempt_v1" and transport["identity_evidence"] == "caller_declared_unverified" and transport["declared_sha256"] == runtime.transport_sha256 and type(transport["timeout"]) in (int, float) and math.isfinite(transport["timeout"]) and transport["timeout"] > 0, "Transport contract differs")
    _metadata(config, schema_descriptor=bound["schema"])
    require(not list((root / "responses/rejected").rglob("*.json")), "Qualification cannot contain rejected attempts")
    verdicts, count, head = runner._load_checkpoints(root, artifact_text=text, context_texts=[], batch_attempts=1)
    accepted_count = min(len(expected_ids), expected_batches * batch_size)
    require(count == expected_batches and [v["question_id"] for v in verdicts] == expected_ids[:accepted_count], "Checkpoint prefix inventory differs")
    require(all(v["artifact_id"] == source["opaque_story_id"] and v["bundle_id"] == "prose.short_story" and v["judge_id"] == "grok:grok-4.6" and v["run_id"] == manifest["run_id"] for v in verdicts), "Verdict identity differs")
    runner._validate_or_reconstruct_attempt_lifecycle(root, config_sha256=manifest["config_sha256"], batch_attempts=1, reconstruct=False, strict_v5=True, require_durable=True)
    require(frozen._read(root, "verdicts.jsonl", runtime) == runner._verdicts_bytes(verdicts), "Verdict aggregate differs")
    schema = runner._response_schema()
    require(frozen._read(root, "response.schema.json", runtime) == runner._json_bytes(schema), "Response schema differs")
    identities: list[dict[str, Any]] = []
    allowed_files = {"run.json", "response.schema.json", "verdicts.jsonl"}
    if response_schema_mode is not None:
        for number, record in enumerate(batch_schema_records, start=1):
            require(frozen._read(root, record["path"], runtime) == batch_schema_raw[number], "Batch response schema differs")
            allowed_files.add(record["path"])
    if full_pass:
        allowed_files.add("score.json")
    if full_pass and (root / "score.v2.json").is_file():
        allowed_files.add("score.v2.json")
    for number in range(1, count + 1):
        _admit_batch(root=root, number=number, runtime=runtime, frozen=frozen, config=config, manifest=manifest, text=text,
                     schema=schema, batch_schema_records=batch_schema_records, verdicts=verdicts, approved_routes=approved_routes,
                     identities=identities, allowed_files=allowed_files)
    _admit_pause_prompt(root=root, expected_batches=expected_batches, full_pass=full_pass, runtime=runtime, frozen=frozen, config=config, text=text, allowed_files=allowed_files)
    require(set(before) == allowed_files, "Run contains missing or orphan evidence files")
    allowed_dirs = {parent.as_posix() for name in allowed_files for parent in Path(name).parents if parent != Path(".")}
    require({path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()} <= allowed_dirs, "Run contains orphan evidence directories")
    require(len({i["request_id_hash"] for i in identities}) == count and len({i["session_id_hash"] for i in identities}) == count, "Duplicate native request/session identity")
    observed = coverage = None
    if full_pass:
        score = core.score_bundle(runtime.modules, runtime.bundle, verdicts, artifact_id=source["opaque_story_id"], task_contract=None)
        score["weight_profile"] = weight_audit
        require(frozen._read(root, "score.json", runtime) == runner._json_bytes(score), "Canonical score replay differs")
        observed, coverage = score["final_score"]["observed"], score["coverage"]
        require(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100 and coverage >= 0.88, "Unqualified score or coverage")
    runtime.verify()
    require(frozen._snapshot(root, runtime) == before, "Run evidence changed during replay")
    result = {"verdicts": [{"question_id": v["question_id"], "verdict": v["verdict"]} for v in verdicts], "score": observed, "coverage": coverage,
              "native_identities": identities, "run_manifest_sha256": digest(frozen._read(root, "run.json", runtime)), "checkpoint_head_sha256": head,
              "evidence_class": "native_record_replay_with_explicit_historical_schema_data",
              "runtime_data_provenance": {"adapter": {"path": str(SELF), "sha256": digest(SELF.read_bytes())}, "frozen_native_admission": {"path": str(NATIVE), "sha256": NATIVE_SHA256}, **bound}}
    if not full_pass:
        result["accepted_count"] = len(verdicts)
    return result


def _admit_batch(*, root: Path, number: int, runtime: Any, frozen: ModuleType, config: dict[str, Any], manifest: dict[str, Any], text: str, schema: dict[str, Any], batch_schema_records: list[dict[str, Any]], verdicts: list[dict[str, Any]], approved_routes: dict[str, dict[str, Any]], identities: list[dict[str, Any]], allowed_files: set[str]) -> None:
    runner = runtime.runner
    checkpoint = frozen._json(root, f"responses/batch-{number:04d}.json", runtime)
    require(checkpoint["format_version"] == 5 and checkpoint["accepted_attempt"] == 1, "Checkpoint attempt policy differs")
    batch_size = config["batch_size"]
    chunk = runtime.questions[(number - 1) * batch_size:number * batch_size]
    active_schema = runner._batch_response_schema([q["question"]["id"] for q in chunk]) if batch_schema_records else schema
    active_schema_raw = runner._json_bytes(active_schema)
    active_schema_path = root / batch_schema_records[number - 1]["path"] if batch_schema_records else root / "response.schema.json"
    binary = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes().decode("utf-8-sig").strip()
    prompt = runner._render_prompt(binary_prompt=binary, artifact={"name": config["artifact"]["name"], "text": text}, contexts=[], bundle_id="prose.short_story", artifact_id=config["artifact_id"], questions=chunk, provider="grok", model="grok-4.6")
    prompt_bytes = gzip.decompress(frozen._read(root, f"responses/batch-{number:04d}.prompt.txt.gz", runtime))
    require(prompt_bytes == prompt.encode("utf-8"), "Reconstructed prompt differs")
    prefix = f"responses/grok-broker/batch-{number:04d}-attempt-0001"
    receipt_raw = frozen._read(root, prefix + "/receipt.json", runtime)
    receipt = json.loads(receipt_raw)
    request_raw = frozen._read(root, prefix + "/request.json", runtime)
    context_raw = frozen._read(root, prefix + "/context-bindings.json", runtime)
    outcome_raw = frozen._read(root, prefix + "/outcome.json", runtime)
    envelope_raw = frozen._read(root, prefix + "/native-envelope.json", runtime)
    require(request_raw == canonical({"prompt": prompt}), "Native request differs")
    outcome = json.loads(outcome_raw)
    require(set(outcome) == {"state", "result", "failure"} and outcome["state"] == "completed" and outcome["failure"] is None, "Native outcome not completed")
    require(all(receipt[key] == digest(value) for key, value in {"request_sha256": request_raw, "context_sha256": context_raw, "outcome_sha256": outcome_raw, "envelope_sha256": envelope_raw, "result_sha256": canonical(outcome["result"]), "schema_sha256": active_schema_raw}.items()), "Native receipt binding differs")
    route_hash = receipt["route_sha256"]
    require(route_hash in approved_routes and digest(canonical(approved_routes[route_hash])) == route_hash, "Native route snapshot missing or differs")
    route = approved_routes[route_hash]
    require(route["timeout_seconds"] == config["grok_transport"]["timeout"], "Native timeout differs")
    identity = frozen._native_result(runtime, outcome["result"], envelope_raw, route, prompt, active_schema, receipt["session_id_hash"])
    context = runner._before_provider_attempt_context(destination=root, schema_path=active_schema_path, run_id=manifest["run_id"], config_sha256=manifest["config_sha256"], provider="grok", model="grok-4.6", reasoning="high", endpoint=None, batch_number=number, question_ids=[q["question"]["id"] for q in chunk], attempt_number=1, batch_attempts=1, base_prompt_sha256=digest(prompt_bytes), effective_prompt=prompt, feedback_policy=runner.VALIDATION_FEEDBACK_POLICY, feedback=None, rejected_chain={})
    context["transport"] = {**config["grok_transport"], "allow_unattested_reasoning": True}
    *_, bindings = runtime.transport._context_bindings(context, route)
    require(context_raw == canonical(bindings), "Native context semantic reconstruction differs")
    expected_receipt = {"schema_version": 1, "source_sha256": runtime.transport_sha256, "route_sha256": route_hash, "request_sha256": digest(request_raw), "context_sha256": digest(context_raw), "schema_sha256": digest(active_schema_raw), "result_sha256": digest(canonical(outcome["result"])), "outcome_sha256": digest(outcome_raw), "envelope_sha256": digest(envelope_raw), "session_id_hash": identity["session_id_hash"], "request_id_hash": identity["request_id_hash"]}
    require(receipt_raw == canonical(expected_receipt), "Native receipt semantic reconstruction differs")
    metadata = checkpoint["provider"]
    require(metadata["evidence_sha256"] == digest(frozen._read(root, prefix + "/receipt.json", runtime)) and metadata["request_id_sha256"] == identity["request_id_hash"] and metadata["session_id_sha256"] == identity["session_id_hash"], "Checkpoint native identity differs")
    identities.append(identity)
    allowed_files.update({f"responses/batch-{number:04d}.json", f"responses/batch-{number:04d}.prompt.txt.gz", f"responses/batch-{number:04d}.accepted-0001.message.txt", f"responses/attempt-lifecycle/batch-{number:04d}/attempt-0001.start.json", f"responses/attempt-lifecycle/batch-{number:04d}/attempt-0001.settled.json", *(prefix + "/" + name for name in ("request.json", "context-bindings.json", "outcome.json", "native-envelope.json", "receipt.json"))})


def _admit_pause_prompt(*, root: Path, expected_batches: int, full_pass: bool, runtime: Any, frozen: ModuleType, config: dict[str, Any], text: str, allowed_files: set[str]) -> None:
    if full_pass:
        return
    next_prompt_path = root / "responses" / f"batch-{expected_batches + 1:04d}.prompt.txt.gz"
    if not next_prompt_path.is_file():
        return
    runner = runtime.runner
    batch_size = config["batch_size"]
    next_chunk = runtime.questions[expected_batches * batch_size:(expected_batches + 1) * batch_size]
    binary = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes().decode("utf-8-sig").strip()
    next_prompt = runner._render_prompt(binary_prompt=binary, artifact={"name": config["artifact"]["name"], "text": text}, contexts=[], bundle_id="prose.short_story", artifact_id=config["artifact_id"], questions=next_chunk, provider="grok", model="grok-4.6")
    prompt_bytes = gzip.decompress(frozen._read(root, next_prompt_path.relative_to(root).as_posix(), runtime))
    require(prompt_bytes == next_prompt.encode("utf-8"), "Next prompt checkpoint differs")
    allowed_files.add(next_prompt_path.relative_to(root).as_posix())


def admit_prefix_with_runtime_data(run_root: str | Path, *, source: dict[str, Any], batch_size: int, approved_routes: dict[str, dict[str, Any]], expected_batches: int, runtime: Any, snapshot_descriptor: dict[str, Any]) -> dict[str, Any]:
    """Replay an exact nonempty prefix using a caller-supplied, verified V4 runtime."""
    frozen = _native()
    return _admit_replay_with_runtime_data(run_root, source=source, batch_size=batch_size, approved_routes=approved_routes, expected_batches=expected_batches, runtime=runtime, runtime_data=snapshot_descriptor, frozen=frozen)


def admit_pass_with_runtime_data(run_root: str | Path, *, source: dict[str, Any], batch_size: int, approved_routes: dict[str, dict[str, Any]], runtime: Any, snapshot_descriptor: dict[str, Any]) -> dict[str, Any]:
    """Replay one full pass with explicit runtime-data provenance."""
    frozen = _native()
    return _admit_replay_with_runtime_data(run_root, source=source, batch_size=batch_size, approved_routes=approved_routes, expected_batches=frozen._batch_count(batch_size, len(runtime.questions)), runtime=runtime, runtime_data=snapshot_descriptor, frozen=frozen)
