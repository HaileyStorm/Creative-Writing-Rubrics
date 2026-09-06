"""Read-only native record replay; never initializes or contacts a provider."""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import uuid


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
SHARED = Path.home() / ".codex/tools/model_work_queue"
PROTOCOL_SHA256 = "f6cf28247f8759a8a823bbdfb7f94e0af33a2661b9ffeb0ce17a1099662c7441"
SUPPLEMENTARY_PINS = {
    "src/hbqrs/paths.py": "dedadb6d9f8e3cf700c16012b29e1a590a2b1175c8ead0cf17c44aa6417b8266",
    "schema/hbq_weight_profile.schema.json": "06e87d35c9d1f2e2434f01dba87c4e0ffd978bd3c42815f85ac8dd21212566c5",
    "schema/hbq_verdict.schema.json": "2d176506edab164c71d42a73661bcd526e4331dbdce659dfae56168b708a4f19",
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _private_modules(root, names, captures):
    prefix = "_dryad_replay_" + uuid.uuid4().hex
    package = ModuleType(prefix)
    package.__path__ = []
    sys.modules[prefix] = package
    loaded = {}
    try:
        for name in names:
            if "." in name:
                parent = name.rsplit(".", 1)[0]
                full_parent = prefix + "." + parent
                if full_parent not in sys.modules:
                    container = ModuleType(full_parent)
                    container.__path__ = []
                    sys.modules[full_parent] = container
                    setattr(package, parent, container)
            path = root / (name.replace(".", "/") + ".py")
            module = ModuleType(prefix + "." + name)
            module.__file__ = str(path)
            module.__package__ = module.__name__.rpartition(".")[0]
            sys.modules[module.__name__] = module
            setattr(sys.modules[module.__package__], name.rsplit(".", 1)[-1], module)
            exec(compile(captures[path], str(path), "exec"), module.__dict__)
            loaded[name] = module
        return loaded
    finally:
        for name in list(sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name)


def load_runtime():
    raw = (ROOT / "protocol.json").read_bytes()
    require(digest(raw) == PROTOCOL_SHA256, "Analysis protocol drift")
    protocol = json.loads(raw)
    captures = {ROOT / "protocol.json": raw}
    for root, bindings in ((REPOSITORY, {**protocol["runtime_bindings"], **SUPPLEMENTARY_PINS}), (SHARED, protocol["shared_runtime_bindings"])):
        for relative, expected in bindings.items():
            path = root / relative
            value = path.read_bytes()
            require(digest(value) == expected, f"Runtime hash drift: {relative}")
            captures[path] = value
    def verify():
        require(all(path.read_bytes() == value for path, value in captures.items()), "Runtime changed during replay")
    hbq = _private_modules(REPOSITORY / "src/hbqrs", ("core", "paths", "weights", "runner", "grok_broker_transport"), captures)
    shared = _private_modules(SHARED, ("adapters.json_schema_subset", "image_canary", "grok_usage_evidence", "broker", "adapters.grok_exec"), captures)
    require(hbq["paths"].book_root().resolve() == REPOSITORY.resolve(), "HBQ book root differs from pinned source")
    core = hbq["core"]
    modules = core.load_modules(REPOSITORY / "registry/all_modules.json")
    bundle = core.resolve_bundle(core.load_bundles(REPOSITORY / "bundles/all_bundles.json"), "prose.short_story")
    compiled = core.compile_bundle(modules, bundle)
    order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(core.compiled_questions(compiled), key=lambda item: order[item["role"]])
    require(len(questions) == 178, "Full-HBQ question inventory drift")
    verify()
    return SimpleNamespace(core=core, runner=hbq["runner"], weights=hbq["weights"], broker=shared["broker"],
                           transport=hbq["grok_broker_transport"], transport_sha256=protocol["runtime_bindings"]["src/hbqrs/grok_broker_transport.py"],
                           adapter=shared["adapters.grok_exec"], modules=modules, bundle=bundle,
                           compiled=compiled, questions=questions, verify=verify)


def _read(run_root, relative, runtime):
    path = run_root / relative
    descriptor = runtime.runner._provider_artifact(run_root, path)
    raw = path.read_bytes()
    require(len(raw) == descriptor["bytes"] and digest(raw) == descriptor["sha256"], "Evidence changed during read")
    require(runtime.runner._provider_artifact(run_root, path) == descriptor, "Evidence changed after read")
    return raw


def _json(run_root, relative, runtime):
    return json.loads(_read(run_root, relative, runtime))


def _snapshot(root, runtime):
    return {path.relative_to(root).as_posix(): runtime.runner._provider_artifact(root, path)
            for path in sorted(root.rglob("*")) if path.is_file()}


def _native_result(runtime, result, raw_envelope, route, prompt, schema, session_hash):
    native = json.loads(raw_envelope)
    session = native["sessionId"]
    require(isinstance(session, str) and str(uuid.UUID(session)) == session and digest(session.encode()) == session_hash,
            "Native session differs from receipt")
    output, identity, usage = runtime.adapter._parse_grok_envelope(
        raw_envelope, model="grok-4.6", reported_model="grok-4.6-build", session_id=session,
        schema=schema, max_turns=1, exact_turns=True,
    )
    def read_envelope(self, descriptor):
        require(descriptor == result["native_envelope_artifact"], "Native descriptor differs")
        require(descriptor["sha256"] == digest(raw_envelope) and descriptor["byte_length"] == len(raw_envelope), "Native bytes differ")
        return raw_envelope
    def forbidden(*args, **kwargs):
        raise AssertionError("Native replay attempted broker state access")
    replay_class = type("ReadOnlyNativeReplay", (runtime.broker.Broker,), {
        "read_grok_native_envelope": read_envelope, "_connect_grok_host_gate": forbidden,
        "_connect": forbidden, "init": forbidden, "_run_grok_exec": forbidden,
    })
    replay = object.__new__(replay_class)
    execution_route = {**route, "output_schema": schema, "nonvisual_max_turns": 1}
    checked = replay._parse_grok_exec_envelope(
        canonical({"control": {"version": 1, "state": "completed"}, "result": result}),
        execution_route, {"prompt": prompt}, expected_session_id=session,
    )
    require(checked.state == "completed" and checked.result == result, "Broker native result replay rejected")
    require(output == result["output"] and usage == result["runtime"]["usage_telemetry"], "Native output/usage replay differs")
    require(all(identity[key] == result["runtime"][key] for key in identity), "Native identity replay differs")
    return identity


def _batch_count(batch_size, question_count):
    require(type(batch_size) is int and batch_size in (8, 32), "Unexpected qualification batch size")
    return (question_count + batch_size - 1) // batch_size


def _admit_replay(run_root, *, source, batch_size, approved_routes, expected_batches, runtime=None):
    """Replay a completed prefix against caller-frozen source/route snapshots."""
    runtime = runtime or load_runtime()
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
    require(all(config.get(key) == value for key, value in expected.items()), "Run configuration differs from qualification")
    require(set(config) == set(expected) | {"artifact", "weight_profile", "bundle_version", "prompts", "response_schema",
                                         "questions_sha256", "compiled_bundle_sha256", "grok_transport"}, "Run configuration shape differs")
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
    require(not list((root / "responses/rejected").rglob("*.json")), "Qualification cannot contain rejected attempts")
    verdicts, count, head = runner._load_checkpoints(root, artifact_text=text, context_texts=[], batch_attempts=1)
    accepted_count = min(len(expected_ids), expected_batches * batch_size)
    require(count == expected_batches and [v["question_id"] for v in verdicts] == expected_ids[:accepted_count], "Checkpoint prefix inventory differs")
    require(all(v["artifact_id"] == source["opaque_story_id"] and v["bundle_id"] == "prose.short_story"
                and v["judge_id"] == "grok:grok-4.6" and v["run_id"] == manifest["run_id"] for v in verdicts), "Verdict identity differs")
    runner._validate_or_reconstruct_attempt_lifecycle(root, config_sha256=manifest["config_sha256"], batch_attempts=1,
                                                    reconstruct=False, strict_v5=True, require_durable=True)
    require(_read(root, "verdicts.jsonl", runtime) == runner._verdicts_bytes(verdicts), "Verdict aggregate differs")
    schema = runner._response_schema()
    require(_read(root, "response.schema.json", runtime) == runner._json_bytes(schema), "Response schema differs")
    binary = (REPOSITORY / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_bytes().decode("utf-8-sig").strip()
    identities = []
    allowed_files = {"run.json", "response.schema.json", "verdicts.jsonl"}
    if full_pass:
        allowed_files.add("score.json")
    if full_pass and (root / "score.v2.json").is_file():
        allowed_files.add("score.v2.json")  # Not an input to qualification arithmetic.
    for number in range(1, count + 1):
        checkpoint = _json(root, f"responses/batch-{number:04d}.json", runtime)
        require(checkpoint["format_version"] == 5 and checkpoint["accepted_attempt"] == 1, "Checkpoint attempt policy differs")
        chunk = runtime.questions[(number - 1) * batch_size:number * batch_size]
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
            "result_sha256": canonical(outcome["result"]), "schema_sha256": runner._json_bytes(schema),
        }.items()), "Native receipt binding differs")
        route_hash = receipt["route_sha256"]
        require(route_hash in approved_routes and digest(canonical(approved_routes[route_hash])) == route_hash, "Native route snapshot missing or differs")
        route = approved_routes[route_hash]
        require(route["timeout_seconds"] == config["grok_transport"]["timeout"], "Native timeout differs")
        identity = _native_result(runtime, outcome["result"], envelope_raw, route, prompt, schema, receipt["session_id_hash"])
        context = runner._before_provider_attempt_context(
            destination=root, schema_path=root / "response.schema.json", run_id=manifest["run_id"],
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
            "schema_sha256": digest(runner._json_bytes(schema)), "result_sha256": digest(canonical(outcome["result"])),
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


def admit_prefix(run_root, *, source, batch_size, approved_routes, expected_batches, runtime=None):
    """Replay an exact nonempty prefix; score only when the pass is complete."""

    runtime = runtime or load_runtime()
    _batch_count(batch_size, len(runtime.questions))
    return _admit_replay(
        run_root,
        source=source,
        batch_size=batch_size,
        approved_routes=approved_routes,
        expected_batches=expected_batches,
        runtime=runtime,
    )


def admit_pass(run_root, *, source, batch_size, approved_routes, runtime=None):
    """Replay one full pass against caller-frozen source/route snapshots.

    This checks native-record consistency. The campaign layer must establish the
    source freeze, authorization lineage and unique identities across all passes;
    this function never authenticates an arbitrary caller's route dictionary.
    """

    runtime = runtime or load_runtime()
    expected_batches = _batch_count(batch_size, len(runtime.questions))
    return _admit_replay(
        run_root,
        source=source,
        batch_size=batch_size,
        approved_routes=approved_routes,
        expected_batches=expected_batches,
        runtime=runtime,
    )
