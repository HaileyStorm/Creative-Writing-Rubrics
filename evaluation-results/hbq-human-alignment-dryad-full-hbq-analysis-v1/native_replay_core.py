"""Versioned native replay with an opt-in authenticated terminal-residue policy.

The original native_admission.py stays unchanged for frozen campaign provenance.
The replay body retains its checks; only validated terminal inventory is extended.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import stat
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
NATIVE = ROOT / "native_admission.py"
NATIVE_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
TERMINAL = ROOT / "terminal_residue.py"
TERMINAL_SHA256 = "d525e6eebdd5d6864057c71dd1c6141f3423cfde78459a2f4b8e18fb00789f94"


def _source(path: Path, expected: str) -> bytes:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        info = candidate.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Replay source contains a link or reparse point")
        if not (stat.S_ISREG(info.st_mode) if candidate == absolute else stat.S_ISDIR(info.st_mode)):
            raise ValueError("Replay source is not plain")
    raw = absolute.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("Replay source pin differs")
    return raw


def _load(path: Path, expected: str) -> tuple[ModuleType, bytes]:
    raw = _source(path, expected)
    module = ModuleType("_dryad_pinned_" + path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact hash-pinned local definitions.
    if _source(path, expected) != raw:
        raise ValueError("Replay source changed while loading")
    return module, raw


def admit_prefix(run_root: Path, *, source: dict[str, Any], batch_size: int, approved_routes: dict[str, Any], expected_batches: int, runtime: Any, terminal_residue: bool = False) -> dict[str, Any]:
    """Replay completed native batches; True validates this exact terminal residue."""
    if runtime is None or not callable(getattr(runtime, "verify", None)) or type(terminal_residue) is not bool:
        raise ValueError("Explicit pinned runtime and residue mode are required")
    native, native_raw = _load(NATIVE, NATIVE_SHA256)
    proof = None
    terminal_raw = None
    if terminal_residue:
        if expected_batches != 4 or batch_size != 8:
            raise ValueError("Terminal residue requires the four-batch size-8 prefix")
        validator, terminal_raw = _load(TERMINAL, TERMINAL_SHA256)
        proof = validator.validate_terminal_residue(Path(run_root), source=source, approved_routes=approved_routes, runtime=runtime)
        expected = {"admitted_batches": 4, "terminal_batch": 5, "ordinal": 28, "native_identity_claimed": False}
        if any(proof.get(key) != value for key, value in expected.items()) or set(proof["residue_files"]) != set(validator.RESIDUE):
            raise ValueError("Terminal residue proof differs")
    result = _replay(run_root, source=source, batch_size=batch_size, approved_routes=approved_routes, expected_batches=expected_batches, runtime=runtime, native=native, terminal_proof=proof)
    if _source(NATIVE, NATIVE_SHA256) != native_raw:
        raise ValueError("Native source changed during replay")
    if proof is not None:
        if _source(TERMINAL, TERMINAL_SHA256) != terminal_raw:
            raise ValueError("Terminal source changed during replay")
        if validator.validate_terminal_residue(Path(run_root), source=source, approved_routes=approved_routes, runtime=runtime) != proof:
            raise ValueError("Terminal residue changed during replay")
        result.update(evidence_class="typed_terminal_residue_native_prefix_replay", terminal_residue=proof)
    return result


def admit_pass(run_root: Path, *, source: dict[str, Any], batch_size: int, approved_routes: dict[str, Any], runtime: Any) -> dict[str, Any]:
    """Replay one complete pass without permitting terminal residue."""
    native, _ = _load(NATIVE, NATIVE_SHA256)
    return admit_prefix(run_root, source=source, batch_size=batch_size, approved_routes=approved_routes, expected_batches=native._batch_count(batch_size, len(runtime.questions)), runtime=runtime)


def _replay(run_root, *, source, batch_size, approved_routes, expected_batches, runtime, native, terminal_proof=None):
    """Replay a completed prefix against caller-frozen source/route snapshots."""
    require, digest, canonical = native.require, native.digest, native.canonical
    _snapshot, _json, _read = native._snapshot, native._json, native._read
    _native_result, _batch_count = native._native_result, native._batch_count
    runtime.verify()
    root = Path(run_root).resolve()
    before = _snapshot(root, runtime)
    runner, core = runtime.runner, runtime.core
    full_batches = _batch_count(batch_size, len(runtime.questions))
    require(type(expected_batches) is int and not isinstance(expected_batches, bool)
            and 1 <= expected_batches <= full_batches, "Expected checkpoint prefix differs")
    full_pass = expected_batches == full_batches
    manifest = _json(root, "run.json", runtime)
    require(manifest.get("format_version") == 5, "Qualification requires current terminal lifecycle")
    config = manifest["configuration"]
    expected_ids = [item["question"]["id"] for item in runtime.questions]
    response_schema_mode = getattr(runtime, "response_schema_mode", None)
    require(response_schema_mode in {None, "batch_question_ids_v1"}, "Unsupported response schema mode")
    batch_schema_records, batch_schema_raw = [], {}
    if response_schema_mode is not None:
        batch_schema_records, batch_schema_raw = runner._batch_schema_plan(expected_ids, batch_size)
    expected = {
        "provider": "grok", "model": "grok-4.6", "reasoning": "high",
        "bundle_id": "prose.short_story", "artifact_id": source["opaque_story_id"],
        "judge_id": "grok:grok-4.6", "batch_size": batch_size,
        "question_ids": expected_ids, "retry_policy": {"batch_attempts": 1},
        "attempt_lifecycle_policy": "terminal_sidecar_v1", "allow_unattested_reasoning": True,
        "strict_ai": False, "task_contract": None, "task_contract_judge_context": None,
        "scope_compatibility": None, "contexts": [],
        "endpoint": None, "api_key_env": None, "temperature": None,
        "allow_model_mismatch": None, "codex_bin": None,
        "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY,
        "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY,
        "prompt_rendering_version": runner.PROMPT_RENDERING_VERSION,
    }
    if response_schema_mode is not None:
        expected["response_schema_mode"] = response_schema_mode
        expected["batch_response_schemas"] = batch_schema_records
    require(all(config.get(key) == value for key, value in expected.items()), "Run configuration differs from qualification")
    require(set(config) == set(expected) | {"artifact", "weight_profile", "bundle_version", "prompts", "response_schema",
                                         "questions_sha256", "compiled_bundle_sha256", "grok_transport"}, "Run configuration shape differs")
    if response_schema_mode is None:
        require("response_schema_initialization" not in manifest, "Generic schema run has batch initialization state")
    else:
        require(manifest.get("response_schema_initialization") == "complete", "Batch response-schema initialization is incomplete")
    require(config["bundle_version"] == runtime.bundle.get("version"), "Bundle version differs")
    require(manifest["config_sha256"] == digest(runner._json_bytes(config)), "Run configuration hash differs")
    text = source["story_text"]
    artifact_path = Path(source["artifact_path"]).resolve()
    expected_artifact = {"path": str(artifact_path), "name": artifact_path.name,
                         "sha256": digest(text.encode()), "bytes": len(text.encode())}
    require(canonical(config["artifact"]) == canonical(expected_artifact), "Story source binding differs")
    require(config["compiled_bundle_sha256"] == digest(runner._json_bytes(runtime.compiled)), "Compiled rubric differs")
    require(config["questions_sha256"] == digest(runner._json_bytes(runner._question_payload(runtime.questions))), "Question payload differs")
    _, _, weight_audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, None)
    require(config["weight_profile"] == weight_audit, "Qualification scoring weights differ")
    transport = config["grok_transport"]
    require(set(transport) == {"protocol", "declared_sha256", "identity_evidence", "timeout"}
            and transport["protocol"] == "injected_grok_attempt_v1"
            and transport["identity_evidence"] == "caller_declared_unverified"
            and transport["declared_sha256"] == runtime.transport_sha256
            and type(transport["timeout"]) in (int, float) and math.isfinite(transport["timeout"]) and transport["timeout"] > 0,
            "Transport contract differs")
    for field, relative in (("response_schema", "schema/hbq_judge_response.schema.json"), ("prompts", "prompts/judge/BINARY_EVALUATION_PROMPT.md")):
        raw = (REPOSITORY / relative).read_bytes()
        records = config[field] if field == "prompts" else [config[field]]
        expected_record = {"name": Path(relative).name, "path": str((REPOSITORY / relative).resolve()), "sha256": digest(raw), "bytes": len(raw)}
        require(canonical(records) == canonical([expected_record]), "Judge instruction/schema metadata differs")
    rejected_files = {path.relative_to(root).as_posix() for path in (root / "responses/rejected").rglob("*.json")}
    allowed_rejected = {path for path in terminal_proof["residue_files"] if path.startswith("responses/rejected/")} if terminal_proof else set()
    require(rejected_files == allowed_rejected, "Qualification cannot contain unadmitted rejected attempts")
    verdicts, count, head = runner._load_checkpoints(root, artifact_text=text, context_texts=[], batch_attempts=1)
    accepted_count = min(len(expected_ids), expected_batches * batch_size)
    require(count == expected_batches and [v["question_id"] for v in verdicts] == expected_ids[:accepted_count], "Checkpoint prefix inventory differs")
    require(all(v["artifact_id"] == source["opaque_story_id"] and v["bundle_id"] == "prose.short_story"
                and v["judge_id"] == "grok:grok-4.6" and v["run_id"] == manifest["run_id"] for v in verdicts), "Verdict identity differs")
    runner._validate_or_reconstruct_attempt_lifecycle(root, config_sha256=manifest["config_sha256"], batch_attempts=1,
                                                    reconstruct=False, strict_v5=True, require_durable=terminal_proof is None)
    require(_read(root, "verdicts.jsonl", runtime) == runner._verdicts_bytes(verdicts), "Verdict aggregate differs")
    schema = runner._response_schema()
    require(_read(root, "response.schema.json", runtime) == runner._json_bytes(schema), "Response schema differs")
    binary = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes().decode("utf-8-sig").strip()
    identities = []
    allowed_files = {"run.json", "response.schema.json", "verdicts.jsonl"}
    if response_schema_mode is not None:
        for number, record in enumerate(batch_schema_records, start=1):
            require(_read(root, record["path"], runtime) == batch_schema_raw[number], "Batch response schema differs")
            allowed_files.add(record["path"])
    if full_pass:
        allowed_files.add("score.json")
    if full_pass and (root / "score.v2.json").is_file():
        allowed_files.add("score.v2.json")  # Not an input to qualification arithmetic.
    for number in range(1, count + 1):
        checkpoint = _json(root, f"responses/batch-{number:04d}.json", runtime)
        require(checkpoint["format_version"] == 5 and checkpoint["accepted_attempt"] == 1, "Checkpoint attempt policy differs")
        chunk = runtime.questions[(number - 1) * batch_size:number * batch_size]
        active_schema = runner._batch_response_schema([q["question"]["id"] for q in chunk]) if response_schema_mode is not None else schema
        active_schema_raw = runner._json_bytes(active_schema)
        active_schema_path = root / batch_schema_records[number - 1]["path"] if response_schema_mode is not None else root / "response.schema.json"
        prompt = runner._render_prompt(binary_prompt=binary, artifact={"name": config["artifact"]["name"], "text": text},
                                       contexts=[], bundle_id="prose.short_story", artifact_id=source["opaque_story_id"],
                                       questions=chunk, provider="grok", model="grok-4.6")
        prompt_bytes = gzip.decompress(_read(root, f"responses/batch-{number:04d}.prompt.txt.gz", runtime))
        require(prompt_bytes == prompt.encode("utf-8"), "Reconstructed prompt differs")
        prefix = f"responses/grok-broker/batch-{number:04d}-attempt-0001"
        receipt_raw = _read(root, prefix + "/receipt.json", runtime)
        receipt = json.loads(receipt_raw)
        request_raw = _read(root, prefix + "/request.json", runtime)
        context_raw = _read(root, prefix + "/context-bindings.json", runtime)
        outcome_raw = _read(root, prefix + "/outcome.json", runtime)
        envelope_raw = _read(root, prefix + "/native-envelope.json", runtime)
        require(request_raw == canonical({"prompt": prompt}), "Native request differs")
        outcome = json.loads(outcome_raw)
        require(set(outcome) == {"state", "result", "failure"} and outcome["state"] == "completed" and outcome["failure"] is None, "Native outcome not completed")
        require(all(receipt[key] == digest(value) for key, value in {
            "request_sha256": request_raw, "context_sha256": context_raw,
            "outcome_sha256": outcome_raw, "envelope_sha256": envelope_raw,
            "result_sha256": canonical(outcome["result"]), "schema_sha256": active_schema_raw,
        }.items()), "Native receipt binding differs")
        route_hash = receipt["route_sha256"]
        require(route_hash in approved_routes and digest(canonical(approved_routes[route_hash])) == route_hash, "Native route snapshot missing or differs")
        route = approved_routes[route_hash]
        require(route["timeout_seconds"] == config["grok_transport"]["timeout"], "Native timeout differs")
        identity = _native_result(runtime, outcome["result"], envelope_raw, route, prompt, active_schema, receipt["session_id_hash"])
        context = runner._before_provider_attempt_context(
            destination=root, schema_path=active_schema_path, run_id=manifest["run_id"],
            config_sha256=manifest["config_sha256"], provider="grok", model="grok-4.6", reasoning="high", endpoint=None,
            batch_number=number, question_ids=[q["question"]["id"] for q in chunk], attempt_number=1, batch_attempts=1,
            base_prompt_sha256=digest(prompt_bytes), effective_prompt=prompt,
            feedback_policy=runner.VALIDATION_FEEDBACK_POLICY, feedback=None, rejected_chain={},
        )
        context["transport"] = {**config["grok_transport"], "allow_unattested_reasoning": True}
        *_, bindings = runtime.transport._context_bindings(context, route)
        require(context_raw == canonical(bindings), "Native context semantic reconstruction differs")
        expected_receipt = {
            "schema_version": 1, "source_sha256": runtime.transport_sha256, "route_sha256": route_hash,
            "request_sha256": digest(request_raw), "context_sha256": digest(context_raw),
            "schema_sha256": digest(active_schema_raw), "result_sha256": digest(canonical(outcome["result"])),
            "outcome_sha256": digest(outcome_raw), "envelope_sha256": digest(envelope_raw),
            "session_id_hash": identity["session_id_hash"], "request_id_hash": identity["request_id_hash"],
        }
        require(receipt_raw == canonical(expected_receipt), "Native receipt semantic reconstruction differs")
        metadata = checkpoint["provider"]
        require(metadata["evidence_sha256"] == digest(_read(root, prefix + "/receipt.json", runtime))
                and metadata["request_id_sha256"] == identity["request_id_hash"]
                and metadata["session_id_sha256"] == identity["session_id_hash"], "Checkpoint native identity differs")
        identities.append(identity)
        allowed_files.update({
            f"responses/batch-{number:04d}.json", f"responses/batch-{number:04d}.prompt.txt.gz",
            f"responses/batch-{number:04d}.accepted-0001.message.txt",
            f"responses/attempt-lifecycle/batch-{number:04d}/attempt-0001.start.json",
            f"responses/attempt-lifecycle/batch-{number:04d}/attempt-0001.settled.json",
            *(prefix + "/" + name for name in ("request.json", "context-bindings.json", "outcome.json", "native-envelope.json", "receipt.json")),
        })
    if not full_pass:
        next_number = expected_batches + 1
        next_prompt_path = root / "responses" / f"batch-{next_number:04d}.prompt.txt.gz"
        if next_prompt_path.is_file():
            next_chunk = runtime.questions[expected_batches * batch_size:(expected_batches + 1) * batch_size]
            next_prompt = runner._render_prompt(
                binary_prompt=binary,
                artifact={"name": config["artifact"]["name"], "text": text},
                contexts=[], bundle_id="prose.short_story", artifact_id=source["opaque_story_id"],
                questions=next_chunk, provider="grok", model="grok-4.6",
            )
            prompt_bytes = gzip.decompress(_read(root, next_prompt_path.relative_to(root).as_posix(), runtime))
            require(prompt_bytes == next_prompt.encode("utf-8"), "Next prompt checkpoint differs")
            allowed_files.add(next_prompt_path.relative_to(root).as_posix())
    if terminal_proof is not None:
        require(not full_pass and expected_batches == 4 and count == 4 and len(identities) == 4, "Terminal prefix geometry differs")
        for relative, expected in terminal_proof["residue_files"].items():
            require(digest(_read(root, relative, runtime)) == expected, "Terminal residue changed during replay")
        allowed_files.update(terminal_proof["residue_files"])
    require(set(before) == allowed_files, "Run contains missing or orphan evidence files")
    allowed_dirs = {parent.as_posix() for name in allowed_files for parent in Path(name).parents if parent != Path(".")}
    require({path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()} <= allowed_dirs,
            "Run contains orphan evidence directories")
    require(len({i["request_id_hash"] for i in identities}) == count and len({i["session_id_hash"] for i in identities}) == count,
            "Duplicate native request/session identity")
    observed = coverage = None
    if full_pass:
        score = core.score_bundle(runtime.modules, runtime.bundle, verdicts, artifact_id=source["opaque_story_id"], task_contract=None)
        score["weight_profile"] = weight_audit
        require(_read(root, "score.json", runtime) == runner._json_bytes(score), "Canonical score replay differs")
        observed, coverage = score["final_score"]["observed"], score["coverage"]
        require(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100 and coverage >= 0.88,
                "Unqualified score or coverage")
    runtime.verify()
    require(_snapshot(root, runtime) == before, "Run evidence changed during replay")
    result = {"verdicts": [{"question_id": v["question_id"], "verdict": v["verdict"]} for v in verdicts],
              "score": observed, "coverage": coverage, "native_identities": identities,
              "run_manifest_sha256": digest(_read(root, "run.json", runtime)), "checkpoint_head_sha256": head,
              "evidence_class": "native_record_replay_only"}
    if not full_pass:
        result["accepted_count"] = len(verdicts)
    return result
