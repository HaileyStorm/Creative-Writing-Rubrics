"""Exact request-70 study descendant and mixed replay; never sends a request.

The native replay checks below preserve the frozen native-admission contract.
Its historical file cannot be refactored: existing evidence pins those bytes.
Only the independently anchored first checkpoint is study-accepted; it does not
claim that the original provider or runtime accepted the failed attempt.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
NATIVE_SHA256 = "22ccfe3299bab0e04045a7ec01ab4799929818a3a84aecc8549bb6cb3032a1ec"
READER_SHA256 = "336807c3cfeb59d318c994305bae87501912065a4f4c7094c0c9be1c3a5a9904"
MANIFEST = "recovered-study.json"
RECOVERED_ORDINAL = 70
STORY_ID = "dryad-01e20a68db7fe9ad1d3a7749"
TARGET_PASS_ID = "baseline8-v1/train/0004/" + STORY_ID
LOGICAL_SAMPLE_ID = "baseline8-v1-train-0004-" + STORY_ID
SUMMARY_FIELDS = {"ordinal", "evidence_kind", "contact_sha256", "adoption_sha256", "derivative_sha256", "study_accepted_at"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _module(name):
    path = ROOT / (name + ".py")
    raw = path.read_bytes()
    if name == "native_admission":
        require(digest(raw) == NATIVE_SHA256, "Frozen native admission source differs")
    elif name == "grok70_schema_recovery":
        require(digest(raw) == READER_SHA256, "Recovery reader source differs")
    module = ModuleType("_dryad_recovered_" + name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - local source bindings checked before execution.
    require(path.read_bytes() == raw, "Recovery dependency changed during load")
    return module


def _inventory(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Recovery run root differs")
    paths = sorted(root.rglob("*"))
    require(not any(path.is_symlink() for path in paths), "Recovery run contains a link")
    return {path.relative_to(root).as_posix(): digest(path.read_bytes()) for path in paths if path.is_file()}


def _read_bound(path, expected, label):
    raw = Path(path).read_bytes()
    require(digest(raw) == expected, f"{label} hash differs")
    return raw


def _recovery(reader_inputs):
    reader = _module("grok70_schema_recovery")
    args = {key: Path(value) if key != "expected_adoption_sha256" else value
            for key, value in reader_inputs.items()}
    return reader.recover_judgment(**args)


def _amendment(path, expected, *, original_inventory, recovery, contact_sha256, require_current):
    value = json.loads(_read_bound(path, expected, "Study amendment"))
    require(set(value) == {"schema_version", "decision", "reviewer_task", "original_run_tree_sha256",
                           "materializer_sha256", "recovery_operational_source_manifest", "study_recovery_summary"}
            and value["schema_version"] == 1
            and value["decision"] == "approved_study_recovery_materialization"
            and isinstance(value["reviewer_task"], str) and value["reviewer_task"], "Study amendment schema differs")
    require(value["original_run_tree_sha256"] == digest(canonical(original_inventory))
            and value["materializer_sha256"] == digest(Path(__file__).read_bytes()), "Study amendment source binding differs")
    summary = value["study_recovery_summary"]
    provenance = recovery["study_recovered_quote_repair"]
    require(isinstance(summary, dict) and set(summary) == SUMMARY_FIELDS
            and summary["ordinal"] == RECOVERED_ORDINAL and summary["evidence_kind"] == "study_recovered"
            and summary["contact_sha256"] == contact_sha256
            and summary["adoption_sha256"] == provenance["adoption_sha256"]
            and summary["derivative_sha256"] == provenance["derivative_sha256"], "Study amendment recovery binding differs")
    accepted_at = datetime.fromisoformat(summary["study_accepted_at"].replace("Z", "+00:00"))
    require(accepted_at.tzinfo is not None and accepted_at.utcoffset().total_seconds() == 0,
            "Study acceptance time must be UTC")
    require(accepted_at >= datetime.fromisoformat(provenance["owner_adopted_at"].replace("Z", "+00:00")),
            "Study acceptance precedes owner adoption")
    ledger = _module("baseline_measurement_ledger")
    source_manifest = value["recovery_operational_source_manifest"]
    if require_current:
        require(ledger.current_operational_source_manifest() == source_manifest, "Study amendment current source manifest differs")
    else:
        core, _ = ledger._core()
        core._source_manifest(source_manifest, "Study recovery", require_current=False)
    return {"adoption_sha256": summary["adoption_sha256"], "amendment_sha256": expected,
            "summary": {**summary, "amendment_sha256": expected},
            "recovery_operational_source_manifest": source_manifest}


def _write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def _run_identity(run, source, runner):
    config = run["configuration"]
    require(run.get("format_version") == 5 and config.get("batch_size") == 8
            and config.get("artifact_id") == source["opaque_story_id"] == LOGICAL_SAMPLE_ID
            and source.get("source_opaque_story_id") == STORY_ID
            and config.get("retry_policy") == {"batch_attempts": 1}
            and config.get("attempt_lifecycle_policy") == runner.ATTEMPT_LIFECYCLE_POLICY
            and config.get("provider") == "grok" and config.get("model") == "grok-4.6",
            "Study descendant run identity differs")
    return config


def materialize_recovered_run(
    original_run_root, descendant_run_root, *, proposal_root, adoption_path, expected_adoption_sha256,
    review_path, source_path, updates_path, terminal_outcome_path, amendment_path, expected_amendment_sha256,
    contact_path, expected_contact_sha256, source, runtime,
):
    """Create one explicitly study-accepted descendant, or verify its prior seed."""
    original, descendant = Path(original_run_root).resolve(), Path(descendant_run_root).resolve()
    require(original != descendant and not descendant.is_relative_to(original)
            and not original.is_relative_to(descendant), "Study descendant must be outside original run")
    runtime.verify()
    original_inventory = _inventory(original)
    require(not list((original / "responses").glob("batch-????.json")), "Exact-70 original already has an accepted checkpoint")
    contact = json.loads(_read_bound(contact_path, expected_contact_sha256, "Original contact"))
    require(contact.get("ordinal") == RECOVERED_ORDINAL and contact.get("cohort_number") == 7,
            "Study recovery requires original request 70")
    reader_inputs = {"proposal_root": str(Path(proposal_root).resolve()), "adoption_path": str(Path(adoption_path).resolve()),
                     "expected_adoption_sha256": expected_adoption_sha256, "review_path": str(Path(review_path).resolve()),
                     "source_path": str(Path(source_path).resolve()), "updates_path": str(Path(updates_path).resolve()),
                     "terminal_outcome_path": str(Path(terminal_outcome_path).resolve())}
    recovery = _recovery(reader_inputs)
    binding = _amendment(amendment_path, expected_amendment_sha256, original_inventory=original_inventory,
                         recovery=recovery, contact_sha256=expected_contact_sha256, require_current=not descendant.exists())
    if descendant.exists():
        require((descendant / MANIFEST).is_file(), "Existing descendant has no completed study manifest")
        manifest_sha256 = digest((descendant / MANIFEST).read_bytes())
        manifest, checked = _verify_recovered(
            descendant, expected_recovered_manifest_sha256=manifest_sha256,
            expected_adoption_sha256=expected_adoption_sha256, expected_amendment_sha256=expected_amendment_sha256,
            source=source, runtime=runtime)
        require(manifest["original_run_root"] == str(original) and manifest["reader_inputs"] == reader_inputs
                and checked == binding, "Existing study descendant binding differs")
        return {"manifest_sha256": manifest_sha256, "checkpoint_head_sha256": manifest["seed_files"]["responses/batch-0001.json"],
                "expected_study_recovery": binding}
    runner = runtime.runner
    run_raw = (original / "run.json").read_bytes()
    run = json.loads(run_raw)
    config = _run_identity(run, source, runner)
    provenance = recovery["study_recovered_quote_repair"]
    require(provenance["source_sha256"] == digest(source["story_text"].encode("utf-8"))
            and config["artifact"]["sha256"] == provenance["source_sha256"], "Study descendant source differs")
    expected_ids = config["question_ids"][:8]
    require(len(expected_ids) == 8 and [v["question_id"] for v in recovery["judgment"]["verdicts"]] == expected_ids,
            "Study recovery question order differs")
    prompt_relative = "responses/batch-0001.prompt.txt.gz"
    start_relative = "responses/attempt-lifecycle/batch-0001/attempt-0001.start.json"
    failed_settled = "responses/attempt-lifecycle/batch-0001/attempt-0001.settled.json"
    failed_outcome = "responses/grok-broker/batch-0001-attempt-0001/outcome.json"
    require(all(relative in original_inventory for relative in (prompt_relative, start_relative, failed_settled, failed_outcome)),
            "Original failed attempt evidence is incomplete")
    require(original_inventory[failed_outcome] == provenance["terminal_outcome_sha256"]
            and original_inventory.get("responses/schemas/batch-0001.json") == provenance["response_schema_sha256"],
            "Recovered original outcome or schema differs")
    copied = ["run.json", "response.schema.json", prompt_relative, start_relative,
              *[item["path"] for item in config.get("batch_response_schemas", [])]]
    descendant.mkdir(parents=True)
    for relative in copied:
        _write_new(descendant / relative, (original / relative).read_bytes())
    prompt = gzip.decompress((descendant / prompt_relative).read_bytes())
    response_raw = _read_bound(Path(proposal_root) / "derivative-agent-message.json",
                               provenance["derivative_sha256"], "Adopted derivative")
    require(json.loads(response_raw) == recovery["judgment"], "Adopted derivative judgment differs")
    audit = []
    normalized = runner._normalize_batch(recovery["judgment"], expected_ids=expected_ids,
        artifact_id=source["opaque_story_id"], bundle_id=config["bundle_id"], judge_id=config["judge_id"],
        run_id=run["run_id"], artifact_text=source["story_text"], context_texts=[],
        normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
    response_relative = "responses/batch-0001.accepted-0001.message.txt"
    _write_new(descendant / response_relative, response_raw)
    checkpoint = {"format_version": 5, "batch": 1, "retry_policy": {"batch_attempts": 1}, "accepted_attempt": 1,
        "question_ids": expected_ids, "prompt_sha256": digest(prompt), "base_prompt_sha256": digest(prompt),
        "effective_prompt_sha256": digest(prompt), "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY,
        "validation_feedback": None, "normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY,
        "normalization_audit": audit, "response_sha256": digest(response_raw),
        "response_artifact": runner._provider_artifact(descendant, descendant / response_relative),
        "rejected_chain": runner._rejected_chain_binding(descendant, batch_number=1, base_prompt=prompt.decode("utf-8"),
            batch_attempts=1, normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY),
        "previous_checkpoint_sha256": None,
        "verdicts_sha256": digest(runner._verdicts_bytes(normalized)),
        "provider": {"study_recovered_quote_repair": provenance}, "normalized_verdicts": normalized}
    checkpoint_path = descendant / "responses/batch-0001.json"
    _write_new(checkpoint_path, runner._json_bytes(checkpoint))
    runner._settle_attempt(output_dir=descendant, batch_number=1, attempt_number=1,
        outcome="accepted", evidence_kind="accepted_checkpoint", evidence_path=checkpoint_path)
    _write_new(descendant / "verdicts.jsonl", runner._verdicts_bytes(normalized))
    seed_files = _inventory(descendant)
    manifest = {"schema_version": 1, "evidence_class": "study_recovered_quote_repair_descendant",
        "logical_request_ordinal": RECOVERED_ORDINAL, "original_run_root": str(original),
        "descendant_run_root": str(descendant), "original_files": original_inventory,
        "original_failed_settlement_sha256": original_inventory[failed_settled],
        "original_failed_outcome_sha256": original_inventory[failed_outcome],
        "reader_inputs": reader_inputs, "recovery": recovery,
        "amendment_path": str(Path(amendment_path).resolve()), "amendment_sha256": expected_amendment_sha256,
        "contact_path": str(Path(contact_path).resolve()), "contact_sha256": expected_contact_sha256,
        "materializer_sha256": digest(Path(__file__).read_bytes()), "native_admission_sha256": NATIVE_SHA256,
        "copied_historical_files": copied, "seed_files": seed_files,
        "aggregate_prefix_bytes": len((descendant / "verdicts.jsonl").read_bytes()),
        "generated_acceptance": "study_accepted_under_independent_amendment_not_original_provider_or_runtime_acceptance",
        "native_identity_claimed": False, "provider_calls": 0, "resend_authority": False}
    _write_new(descendant / MANIFEST, canonical(manifest))
    manifest_sha256 = digest((descendant / MANIFEST).read_bytes())
    _verify_recovered(descendant, expected_recovered_manifest_sha256=manifest_sha256,
        expected_adoption_sha256=expected_adoption_sha256, expected_amendment_sha256=expected_amendment_sha256,
        source=source, runtime=runtime)
    return {"manifest_sha256": manifest_sha256, "checkpoint_head_sha256": digest(checkpoint_path.read_bytes()),
            "expected_study_recovery": binding}


def _verify_recovered(root, *, expected_recovered_manifest_sha256, expected_adoption_sha256,
                      expected_amendment_sha256, source, runtime):
    root = Path(root).resolve()
    manifest = json.loads(_read_bound(root / MANIFEST, expected_recovered_manifest_sha256, "Recovered study manifest"))
    require(manifest.get("schema_version") == 1
            and manifest.get("evidence_class") == "study_recovered_quote_repair_descendant"
            and manifest.get("logical_request_ordinal") == RECOVERED_ORDINAL
            and manifest.get("descendant_run_root") == str(root)
            and manifest.get("materializer_sha256") == digest(Path(__file__).read_bytes())
            and manifest.get("native_admission_sha256") == NATIVE_SHA256
            and manifest.get("native_identity_claimed") is False and manifest.get("provider_calls") == 0
            and manifest.get("resend_authority") is False, "Recovered study manifest scope differs")
    original = Path(manifest["original_run_root"]).resolve()
    require(original != root and not root.is_relative_to(original) and not original.is_relative_to(root),
            "Recovered study roots overlap")
    require(_inventory(original) == manifest["original_files"], "Original failed run changed")
    require(manifest["reader_inputs"]["expected_adoption_sha256"] == expected_adoption_sha256
            and manifest["amendment_sha256"] == expected_amendment_sha256, "Recovery external anchors differ")
    recovery = _recovery(manifest["reader_inputs"])
    require(recovery == manifest["recovery"], "Recovered judgment or provenance changed")
    contact = json.loads(_read_bound(manifest["contact_path"], manifest["contact_sha256"], "Original contact"))
    require(contact.get("ordinal") == RECOVERED_ORDINAL and contact.get("cohort_number") == 7,
            "Recovered contact is not request 70")
    binding = _amendment(manifest["amendment_path"], expected_amendment_sha256,
        original_inventory=manifest["original_files"], recovery=recovery,
        contact_sha256=manifest["contact_sha256"], require_current=False)
    require(source["opaque_story_id"] == LOGICAL_SAMPLE_ID and source.get("source_opaque_story_id") == STORY_ID
            and digest(source["story_text"].encode("utf-8")) == recovery["study_recovered_quote_repair"]["source_sha256"],
            "Recovered study source differs")
    for relative, expected in manifest["seed_files"].items():
        path = root / relative
        require(path.resolve().is_relative_to(root), "Recovered seed path escapes descendant")
        raw = path.read_bytes()
        if relative == "verdicts.jsonl":
            raw = raw[:manifest["aggregate_prefix_bytes"]]
        require(digest(raw) == expected, "Recovered seed file changed")
    require(all(manifest["seed_files"][relative] == manifest["original_files"][relative]
                for relative in manifest["copied_historical_files"]), "Historical copied seed differs")
    checkpoint = json.loads((root / "responses/batch-0001.json").read_bytes())
    require(checkpoint["provider"] == {"study_recovered_quote_repair": recovery["study_recovered_quote_repair"]}
            and checkpoint["response_sha256"] == recovery["study_recovered_quote_repair"]["derivative_sha256"],
            "Recovered checkpoint claims different evidence")
    runtime.verify()
    runner = runtime.runner
    verdicts, count, _ = runner._load_checkpoints(root, artifact_text=source["story_text"], context_texts=[], batch_attempts=1)
    require(count >= 1 and len(verdicts) >= 8, "Recovered checkpoint cannot resume")
    run = json.loads((root / "run.json").read_bytes())
    _run_identity(run, source, runner)
    runner._validate_or_reconstruct_attempt_lifecycle(root, config_sha256=run["config_sha256"],
        batch_attempts=1, reconstruct=False, strict_v5=True)
    require(_inventory(original) == manifest["original_files"], "Original failed run changed during replay")
    runtime.verify()
    return manifest, binding


def load_recovered_study(run_root, *, expected_recovered_manifest_sha256, expected_adoption_sha256,
                         expected_amendment_sha256, source, runtime):
    """Validate the externally anchored recovery before a ledger or route lookup."""
    manifest, binding = _verify_recovered(run_root,
        expected_recovered_manifest_sha256=expected_recovered_manifest_sha256,
        expected_adoption_sha256=expected_adoption_sha256, expected_amendment_sha256=expected_amendment_sha256,
        source=source, runtime=runtime)
    return {"expected_study_recovery": binding, "original_run_root": manifest["original_run_root"],
            "descendant_run_root": manifest["descendant_run_root"], "target_pass_id": TARGET_PASS_ID,
            "manifest_sha256": expected_recovered_manifest_sha256,
            "checkpoint_head_sha256": manifest["seed_files"]["responses/batch-0001.json"]}


_native = _module("native_admission")
_snapshot = _native._snapshot
_read = _native._read
_json = _native._json
_native_result = _native._native_result
_batch_count = _native._batch_count
load_runtime = _native.load_runtime


def _admit_replay(run_root, *, source, batch_size, approved_routes, expected_batches, runtime=None, recovery_context):
    """Frozen native replay with one separately validated study checkpoint."""
    recovered_manifest, recovered_binding, recovered_manifest_sha256 = recovery_context
    require(batch_size == 8, "Exact-70 mixed replay requires batches of eight")
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
    allowed_files = {"run.json", "response.schema.json", "verdicts.jsonl", MANIFEST}
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
        if number == 1:
            require(checkpoint["provider"] == {"study_recovered_quote_repair": recovered_manifest["recovery"]["study_recovered_quote_repair"]},
                    "Recovered checkpoint evidence differs")
            allowed_files.update({
                "responses/batch-0001.json", "responses/batch-0001.prompt.txt.gz",
                "responses/batch-0001.accepted-0001.message.txt",
                "responses/attempt-lifecycle/batch-0001/attempt-0001.start.json",
                "responses/attempt-lifecycle/batch-0001/attempt-0001.settled.json",
            })
            continue
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
    require(set(before) == allowed_files, "Run contains missing or orphan evidence files")
    allowed_dirs = {parent.as_posix() for name in allowed_files for parent in Path(name).parents if parent != Path(".")}
    require({path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()} <= allowed_dirs,
            "Run contains orphan evidence directories")
    require(len({i["request_id_hash"] for i in identities}) == count - 1 and len({i["session_id_hash"] for i in identities}) == count - 1,
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
              "evidence_class": "mixed_native_and_study_recovered_record_replay",
              "study_recovered": [recovered_binding["summary"]], "study_recovered_ordinals": [RECOVERED_ORDINAL],
              "native_record_count": len(identities), "study_recovered_record_count": 1,
              "recovered_manifest_sha256": recovered_manifest_sha256, "expected_study_recovery": recovered_binding}
    if not full_pass:
        result["accepted_count"] = len(verdicts)
    return result


def admit_prefix(run_root, *, source, batch_size, approved_routes, expected_batches,
                 expected_recovered_manifest_sha256, expected_adoption_sha256, expected_amendment_sha256,
                 runtime=None):
    """Replay the study first checkpoint and strictly native subsequent batches."""
    runtime = runtime or load_runtime()
    manifest, binding = _verify_recovered(run_root,
        expected_recovered_manifest_sha256=expected_recovered_manifest_sha256,
        expected_adoption_sha256=expected_adoption_sha256, expected_amendment_sha256=expected_amendment_sha256,
        source=source, runtime=runtime)
    result = _admit_replay(run_root, source=source, batch_size=batch_size, approved_routes=approved_routes,
        expected_batches=expected_batches, runtime=runtime,
        recovery_context=(manifest, binding, expected_recovered_manifest_sha256))
    require(_inventory(manifest["original_run_root"]) == manifest["original_files"], "Original failed run changed during mixed replay")
    return result


def admit_pass(run_root, *, source, batch_size, approved_routes, expected_recovered_manifest_sha256,
               expected_adoption_sha256, expected_amendment_sha256, runtime=None):
    """Use canonical full-pass scoring with exactly one non-native study record."""
    runtime = runtime or load_runtime()
    return admit_prefix(run_root, source=source, batch_size=batch_size, approved_routes=approved_routes,
        expected_batches=_batch_count(batch_size, len(runtime.questions)),
        expected_recovered_manifest_sha256=expected_recovered_manifest_sha256,
        expected_adoption_sha256=expected_adoption_sha256, expected_amendment_sha256=expected_amendment_sha256,
        runtime=runtime)
