"""Owner-gated interpretation of the single frozen Sol ordinal-221 incident.

Candidate verification replays locally but returns no study data or authority.
The strict predecessor remains immutable for historical replay and ordinary passes.
"""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STRICT_PATH = ROOT / "sol_pass_admission.py"
STRICT_SHA256 = "cd8364c18cbd8a07bc18a9b4d3d0bc1102518cfbed465b9c4f4586245b8eb65d"
EXECUTOR_PATH = ROOT.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/executor.py"
EXECUTOR_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
SHARED_PARSER_PATH = Path.home() / ".codex/tools/model_work_queue/adapters/codex_exec.py"
SHARED_PARSER_SHA256 = "89b906fe488c663d23cc1f5d0d8d3b5d0bf105fbdae96a848598bc2a1f6e3cee"
PROPOSAL_SHA256 = "fece81ca25260c830fbe62d21a1ba30543e316905a70a773276090ca02b38507"
INCIDENT_SHA256 = "43209a6cbf35bb1297ce25431e6fddea19df0cf1e1b5c3eaf0da9f13e72cbbe5"
RECOVERY_CLASS = "recovered_transport_exact_ordinal_221_v1"
ALLOWLIST = {
    "ordinal": 221, "batch": 14, "pass_number": 10,
    "events_sha256": "b2a2ec194c4cd755797256feeb50a48179c12e1a755ea712cdab2c10e1166918",
    "events_bytes": 5108,
    "error_message_sha256": "61cbbf0ae9181725d0cf3779e1e940b5e4bf65475d3c2cc3a59c1964ad8f7723",
    "error_message_bytes": 39,
    "stderr_sha256": "3784f263cc1e32cd8d0b69408e73b54c7c678fcfc1044a1254b0b2fc0d808a32",
    "stderr_bytes": 143,
    "final_message_sha256": "5a2b46c215eab6dc42a8e7b5ce822baf7706cbf176985fff359f4f7b3e344a63",
    "checkpoint_sha256": "5edfae703298a2665e861390953db726e45108726cd7b9bd1021ef0ba3d1fffa",
    "attempt_start_sha256": "c77260797d6543d45218d1e582df2fa3dd5c4d89529c603cc2bd55d50a716cf8",
    "attempt_settled_sha256": "3b8ea5924af4bccefe2a82b2ddf0bd72c30611a5128f2b69b9eedcbf1029b6d7",
    "accepted_attempt": 1,
    "external_launch_evidence": "accepted_checkpoint_and_pinned_single_launch_runtime",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _load_strict() -> Any:
    raw = STRICT_PATH.read_bytes()
    _require(_sha(raw) == STRICT_SHA256, "Frozen strict admission source differs")
    spec = importlib.util.spec_from_file_location("_sol_recovery_strict", STRICT_PATH)
    _require(spec is not None and spec.loader is not None, "Strict admission cannot load")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(STRICT_PATH), "exec"), module.__dict__)  # noqa: S102 - execute only hash-pinned predecessor bytes
    return module


_base = _load_strict()
PLAN_SHA256 = _base.PLAN_SHA256
_canonical = _base._canonical
_hex = _base._hex
_time = _base._time
_relative = _base._relative
_source_bindings = _base._source_bindings
_route = _base._route


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON key in recovery evidence")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed or has duplicate keys") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _verify_sources() -> dict[str, str]:
    for path, expected in ((STRICT_PATH, STRICT_SHA256), (EXECUTOR_PATH, EXECUTOR_SHA256),
                           (SHARED_PARSER_PATH, SHARED_PARSER_SHA256)):
        _require(_sha(path.read_bytes()) == expected, "Recovery source binding differs")
    return {"interpreter_sha256": _sha(Path(__file__).read_bytes()),
            "strict_admission_sha256": STRICT_SHA256, "executor_sha256": EXECUTOR_SHA256,
            "shared_parser_sha256": SHARED_PARSER_SHA256}


def _incident(path: Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    _require(_sha(raw) == INCIDENT_SHA256, "Recovery incident differs")
    return _json(raw, "Recovery incident")


def _parse_exact_events(raw: bytes) -> dict[str, Any]:
    _require(type(raw) is bytes and len(raw) == ALLOWLIST["events_bytes"]
             and _sha(raw) == ALLOWLIST["events_sha256"], "Exact recovery event bytes differ")
    lines = raw.splitlines()
    _require(len(lines) == 5 and all(line.strip() for line in lines), "Exact recovery event count differs")
    events = [_json(line, "Recovery event") for line in lines]
    grammar = (("thread.started", {"type", "thread_id"}), ("turn.started", {"type"}),
               ("error", {"type", "message"}), ("item.completed", {"type", "item"}),
               ("turn.completed", {"type", "usage"}))
    for event, (kind, keys) in zip(events, grammar, strict=True):
        _require(set(event) == keys and event.get("type") == kind, "Exact recovery event grammar differs")
    thread, message, item, usage = events[0]["thread_id"], events[2]["message"], events[3]["item"], events[4]["usage"]
    _require(isinstance(thread, str) and bool(thread), "Recovery thread differs")
    _require(isinstance(message, str), "Recovery error message type differs")
    encoded = message.encode("utf-8")
    _require(len(encoded) == ALLOWLIST["error_message_bytes"] and _sha(encoded) == ALLOWLIST["error_message_sha256"],
             "Recovery error message differs")
    _require(isinstance(item, dict) and set(item) == {"id", "type", "text"}
             and isinstance(item["id"], str) and bool(item["id"]) and item["type"] == "agent_message"
             and isinstance(item["text"], str), "Recovery completed item differs")
    _require(_sha(item["text"].encode("utf-8")) == ALLOWLIST["final_message_sha256"], "Recovery output differs")
    usage_keys = {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens"}
    _require(isinstance(usage, dict) and set(usage) == usage_keys
             and all(type(value) is int and value >= 0 for value in usage.values()), "Recovery usage differs")
    return {"schema_version": 1, "thread_id": thread, "usage": usage}


def verify_adoption(adoption_path: Path, *, expected_adoption_sha256: str, incident_path: Path) -> dict[str, Any]:
    """Validate an externally supplied owner decision; never create one."""
    _require(_hex(expected_adoption_sha256), "Trusted recovery adoption hash differs")
    raw = Path(adoption_path).read_bytes()
    _require(_sha(raw) == expected_adoption_sha256, "Recovery adoption bytes differ")
    value = _json(raw, "Recovery adoption")
    sources = _verify_sources()
    _incident(incident_path)
    keys = {"schema_version", "decision", "owner_decision", "proposal_sha256", "incident_sha256",
            "allowlist", "independent_review", "tests", "candidate_verification_sha256", *sources}
    _require(set(value) == keys and type(value["schema_version"]) is int and value["schema_version"] == 1
             and value["decision"] == "adopt_" + RECOVERY_CLASS
             and value["proposal_sha256"] == PROPOSAL_SHA256 and value["incident_sha256"] == INCIDENT_SHA256
             and _hex(value["candidate_verification_sha256"])
             and _canonical(value["allowlist"]) == _canonical(ALLOWLIST)
             and all(value[key] == expected for key, expected in sources.items()), "Recovery adoption commitments differ")
    owner = value["owner_decision"]
    _require(isinstance(owner, dict) and set(owner) == {"explicit", "recorded_at", "reference"}
             and owner["explicit"] is True and isinstance(owner["reference"], str) and bool(owner["reference"].strip()),
             "Explicit owner adoption is missing")
    _time(owner["recorded_at"], "Owner adoption time")
    tests, review = value["tests"], value["independent_review"]
    _require(isinstance(tests, dict) and set(tests) == {"test_source_sha256", "result", "command", "passed"}
             and _hex(tests["test_source_sha256"]) and tests["result"] == "passed"
             and type(tests["passed"]) is int and tests["passed"] > 0
             and isinstance(tests["command"], str) and bool(tests["command"].strip()), "Recovery test evidence differs")
    _require(isinstance(review, dict) and set(review) == {"decision", "reference", "interpreter_sha256", "test_source_sha256"}
             and review["decision"] == "approved" and isinstance(review["reference"], str) and bool(review["reference"].strip())
             and review["interpreter_sha256"] == sources["interpreter_sha256"]
             and review["test_source_sha256"] == tests["test_source_sha256"], "Independent recovery review differs")
    test_path = ROOT.parents[1] / "tests/test_dryad_sol_recovered_transport_admission.py"
    _require(_sha(test_path.read_bytes()) == tests["test_source_sha256"], "Recovery test source differs")
    return {"schema_version": 1, "evidence_class": RECOVERY_CLASS, "adoption_sha256": expected_adoption_sha256,
            "proposal_sha256": PROPOSAL_SHA256, "incident_sha256": INCIDENT_SHA256, **sources,
            "allowlist": dict(ALLOWLIST), "candidate_verification_sha256": value["candidate_verification_sha256"],
            "execution_authority": False, "provider_calls": 0,
            "internal_retry_cardinality": "unproven", "native_endpoint_contact_cardinality": "unproven",
            "identity_evidence": "requested_only", "provider_attested": False,
            "observed_external_launch_count": None, "observed_process_exit_code": None,
            "independent_process_exit_receipt": False}


def _target_pass(plan_root: Path, pass_id: str) -> bool:
    raw = _relative(Path(plan_root), "plan.json").read_bytes()
    _require(_sha(raw) == PLAN_SHA256, "Frozen recovery plan differs")
    plan = _json(raw, "Recovery plan")
    passes = plan.get("passes")
    _require(isinstance(passes, list) and len(passes) == 236, "Recovery plan geometry differs")
    return passes[ALLOWLIST["pass_number"] - 1].get("pass_id") == pass_id


def _candidate_report(result: Mapping[str, Any], run_root: Path, pass_id: str,
                      sources: Mapping[str, str]) -> dict[str, Any]:
    count = len(result["local_thread_ids"])
    root = Path(run_root)
    return {
        "schema_version": 1, "evidence_class": "sol_recovered_transport_candidate_verification_v1",
        "execution_authority": False, "study_admission": False, "provider_calls": 0,
        "proposal_sha256": PROPOSAL_SHA256, "incident_sha256": INCIDENT_SHA256, **sources,
        "plan_sha256": PLAN_SHA256, "pass_id": pass_id, "replayed_batches": count,
        "replayed_verdict_count": len(result["verdicts"]), "recovered_ordinals": [ALLOWLIST["ordinal"]],
        "allowlist": dict(ALLOWLIST), "checkpoint_head_sha256": result["checkpoint_head_sha256"],
        "run_manifest_sha256": _sha(_relative(root, "run.json").read_bytes()),
        "score_artifact_sha256": _sha(_relative(root, "score.json").read_bytes()) if count == 23 else None,
        "thread_ids_sha256": _sha(_canonical(result["local_thread_ids"])),
        "parity": {"plan_source_route_review_checkpoint_schema_output": True,
                   "ordinary_streams_strict": True, "score": count == 23, "exact_error_allowlist": True},
        "identity_evidence": "requested_only", "provider_attested": False,
        "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven",
        "launch_evidence": "accepted_checkpoint_and_pinned_single_launch_runtime",
        "process_exit_evidence": "accepted_checkpoint_and_pinned_runtime_nonzero_rejection",
        "observed_external_launch_count": None, "observed_process_exit_code": None,
        "independent_process_exit_receipt": False, "new_caller_retry_or_resend": False,
    }


def verify_candidate(run_root: Path, plan_root: Path, pass_id: str, *, expected_plan_sha256: str,
                     expected_source_bindings: Mapping[str, str], expected_reviews: set[str],
                     incident_path: Path, proposal_path: Path, expected_batches: int | None = None) -> dict[str, Any]:
    """Provider-free replay with only commitments, counts and parity in its output."""
    sources = _verify_sources()
    _incident(incident_path)
    _require(_sha(Path(proposal_path).read_bytes()) == PROPOSAL_SHA256, "Recovery proposal differs")
    result = _replay_target_pass(run_root, plan_root, pass_id, expected_plan_sha256=expected_plan_sha256,
                                 expected_source_bindings=expected_source_bindings,
                                 expected_reviews=expected_reviews, expected_batches=expected_batches)
    return _candidate_report(result, run_root, pass_id, sources)


def admit_campaign(plan_root: Path, execution_root: Path, *, expected_plan_sha256: str, expected_source_bindings: Mapping[str, str], expected_reviews: set[str], adoption_path: Path, expected_adoption_sha256: str, incident_path: Path) -> dict[str, Any]:
    """Compose only complete admitted passes; partial results have no campaign meaning."""
    adoption = verify_adoption(adoption_path, expected_adoption_sha256=expected_adoption_sha256, incident_path=incident_path)
    recoveries: list[dict[str, Any]] = []
    plan_raw = _relative(Path(plan_root), "plan.json").read_bytes()
    _require(expected_plan_sha256 == PLAN_SHA256 and _sha(plan_raw) == expected_plan_sha256, "Frozen campaign plan differs")
    plan = _json(plan_raw, "Plan")
    passes, requests = plan.get("passes"), plan.get("requests")
    _require(isinstance(passes, list) and len(passes) == 236 and isinstance(requests, list) and len(requests) == 5428, "Campaign plan geometry differs")
    _require([item.get("partition") if isinstance(item, Mapping) else None for item in passes] == ["TRAIN"] * 176 + ["DEV"] * 60, "Campaign frozen source order differs")
    threads: set[str] = set(); rows: list[dict[str, Any]] = []
    for record in passes:
        _require(isinstance(record, Mapping) and isinstance(record.get("pass_id"), str) and isinstance(record.get("run_path"), str), "Campaign pass differs")
        admitted = _admit_with_adoption(Path(execution_root) / record["run_path"], Path(plan_root), record["pass_id"], expected_plan_sha256=expected_plan_sha256, expected_source_bindings=expected_source_bindings, expected_reviews=expected_reviews, adoption=adoption)
        if "transport_recovery" in admitted:
            recoveries.append(admitted["transport_recovery"])
        local = admitted.get("local_thread_ids")
        _require(isinstance(local, list) and len(local) == len(set(local)) == 23 and all(isinstance(value, str) and value and value not in threads for value in local) and isinstance(admitted.get("verdicts"), list) and len(admitted["verdicts"]) == 178 and type(admitted.get("score")) in (int, float) and type(admitted.get("coverage")) in (int, float), "Campaign pass is incomplete or duplicates a local thread")
        threads.update(local)
        rows.append({key: record[key] for key in ("pass_id", "logical_sample_id", "opaque_story_id", "partition")} | {key: admitted[key] for key in ("verdicts", "score", "coverage")})
    _require(len(rows) == 236 and len(threads) == 5428, "Campaign local thread cardinality differs")
    _require(len(recoveries) == 1, "Campaign recovery must identify exactly one ordinal")
    return {"transport_recovery": recoveries[0], "evidence_class": "complete_sol_local_lifecycle_campaign_admission", "execution_authority": False, "provider_calls": 0, "admitted_passes": 236, "logical_requests": 5428, "endpoint_sol_rows": rows, "identity_ceiling": {"identity_evidence": "requested_only", "native_endpoint_contact_cardinality": "unproven", "provider_attested": False}}


def _admit_with_adoption(run_root: Path, plan_root: Path, pass_id: str, *, expected_plan_sha256: str,
                          expected_source_bindings: Mapping[str, str], expected_reviews: set[str],
                          adoption: Mapping[str, Any], expected_batches: int | None = None) -> dict[str, Any]:
    kwargs = {"expected_plan_sha256": expected_plan_sha256, "expected_source_bindings": expected_source_bindings,
              "expected_reviews": expected_reviews, "expected_batches": expected_batches}
    if not _target_pass(plan_root, pass_id):
        return _base.admit_pass(run_root, plan_root, pass_id, **kwargs)
    result = _replay_target_pass(run_root, plan_root, pass_id, **kwargs)
    report = _candidate_report(result, run_root, pass_id, _verify_sources())
    _require(_sha(_canonical(report)) == adoption["candidate_verification_sha256"], "Adopted recovery candidate differs")
    return {**result, "transport_recovery": dict(adoption)}


def admit_pass(run_root: Path, plan_root: Path, pass_id: str, *, expected_plan_sha256: str,
               expected_source_bindings: Mapping[str, str], expected_reviews: set[str],
               adoption_path: Path, expected_adoption_sha256: str, incident_path: Path,
               expected_batches: int | None = None) -> dict[str, Any]:
    adoption = verify_adoption(adoption_path, expected_adoption_sha256=expected_adoption_sha256, incident_path=incident_path)
    return _admit_with_adoption(run_root, plan_root, pass_id, expected_plan_sha256=expected_plan_sha256,
                                expected_source_bindings=expected_source_bindings, expected_reviews=expected_reviews,
                                adoption=adoption, expected_batches=expected_batches)


def _target_evidence(root: Path, request: Mapping[str, Any], checkpoint: Mapping[str, Any],
                     manifest: Mapping[str, Any], stderr: bytes, final: bytes, v3: Any) -> None:
    _require(type(request.get("ordinal")) is int and request["ordinal"] == ALLOWLIST["ordinal"]
             and type(request.get("batch_number")) is int and request["batch_number"] == ALLOWLIST["batch"],
             "Recovery ordinal or batch differs")
    number = ALLOWLIST["batch"]
    checkpoint_path = _relative(root, f"responses/batch-{number:04d}.json")
    _require(_sha(checkpoint_path.read_bytes()) == ALLOWLIST["checkpoint_sha256"], "Recovery checkpoint differs")
    _require(type(checkpoint.get("accepted_attempt")) is int and checkpoint["accepted_attempt"] == 1,
             "Recovery accepted attempt differs")
    _require(len(stderr) == ALLOWLIST["stderr_bytes"] and _sha(stderr) == ALLOWLIST["stderr_sha256"],
             "Recovery stderr differs")
    labels = v3._strict_stderr_labels(stderr)
    _require(labels == {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}
             and checkpoint["provider"].get("reported") == labels, "Recovery identity labels differ")
    _require(_sha(final) == ALLOWLIST["final_message_sha256"], "Recovery final message differs")
    expected_files = {f"batch-{number:04d}.attempt-0001.{suffix}" for suffix in ("events.jsonl", "message.json", "stderr.bin")}
    _require({path.name for path in (root / "responses").glob(f"batch-{number:04d}.attempt-*")} == expected_files,
             "Recovery has extra or missing attempt artifacts")
    lifecycle = root / f"responses/attempt-lifecycle/batch-{number:04d}"
    _require(lifecycle.is_dir() and {path.name for path in lifecycle.iterdir()}
             == {"attempt-0001.start.json", "attempt-0001.settled.json"}, "Recovery attempt lifecycle inventory differs")
    start_raw = _relative(lifecycle, "attempt-0001.start.json").read_bytes()
    _require(_sha(start_raw) == ALLOWLIST["attempt_start_sha256"], "Recovery attempt start bytes differ")
    start = _json(start_raw, "Recovery attempt start")
    expected_start = {"format_version": 1, "policy": "terminal_sidecar_v1", "state": "started",
                      "config_sha256": manifest.get("config_sha256"), "batch": number, "attempt": 1,
                      "base_prompt_sha256": request["prompt_sha256"], "effective_prompt_sha256": request["prompt_sha256"],
                      "retry_policy": {"batch_attempts": 1}}
    _require(_hex(manifest.get("config_sha256")) and _canonical(start) == _canonical(expected_start),
             "Recovery attempt start differs")
    settled_raw = _relative(lifecycle, "attempt-0001.settled.json").read_bytes()
    _require(_sha(settled_raw) == ALLOWLIST["attempt_settled_sha256"], "Recovery settlement bytes differ")
    settled = _json(settled_raw, "Recovery settlement")
    expected_settled = {"format_version": 1, "policy": "terminal_sidecar_v1", "state": "settled",
                        "start_sha256": _sha(start_raw), "batch": number, "attempt": 1, "outcome": "accepted",
                        "evidence": {"kind": "accepted_checkpoint", "path": f"responses/batch-{number:04d}.json",
                                     "sha256": ALLOWLIST["checkpoint_sha256"]}}
    _require(_canonical(settled) == _canonical(expected_settled), "Recovery accepted settlement differs")


def _replay_target_pass(run_root: Path, plan_root: Path, pass_id: str, *, expected_plan_sha256: str, expected_source_bindings: Mapping[str, str], expected_reviews: set[str], expected_batches: int | None = None) -> dict[str, Any]:
    """Derivative of the pinned strict body; only target parser selection differs."""
    _require(_target_pass(plan_root, pass_id), "Recovery target pass differs")
    _require(expected_plan_sha256 == PLAN_SHA256 and all(_hex(value) for value in expected_reviews), "Trusted Sol admission anchors differ")
    runtime, v3, _ = _source_bindings(expected_source_bindings)
    plan_raw = _relative(Path(plan_root), "plan.json").read_bytes()
    _require(_sha(plan_raw) == expected_plan_sha256, "Frozen plan differs")
    plan = _json(plan_raw, "Plan")
    passes, requests = plan.get("passes"), plan.get("requests")
    _require(isinstance(passes, list) and isinstance(requests, list) and len(passes) == 236 and len(requests) == 5428, "Plan geometry differs")
    record = next((item for item in passes if isinstance(item, dict) and item.get("pass_id") == pass_id), None)
    _require(record is not None and record.get("batch_size") == 8 and record.get("batches") == 23, "Planned Sol pass differs")
    planned = [item for item in requests if isinstance(item, dict) and item.get("pass_id") == pass_id]
    ids = plan.get("runtime", {}).get("question_ids") if isinstance(plan.get("runtime"), dict) else None
    _require(len(planned) == 23 and isinstance(ids, list) and len(ids) == len(set(ids)) == 178 and [item.get("batch_number") for item in planned] == list(range(1, 24)) and [question for item in planned for question in item.get("question_ids", [])] == ids, "Planned Sol batches differ")
    root = Path(run_root).resolve(); _require(root.is_dir(), "Sol run root differs")
    execution = root
    for _ in Path(record["run_path"]).parts: execution = execution.parent
    _require((execution / record["run_path"]).resolve() == root, "Sol execution root differs")
    source = _relative(Path(plan_root), record["input_path"]).read_bytes()
    _require(_sha(source) == record.get("source_sha256") and len(source) == record.get("source_bytes"), "Sol source differs")
    text = source.decode("utf-8")
    manifest = _json(_relative(root, "run.json").read_bytes(), "Sol run")
    config = manifest.get("configuration")
    _, _, weight_audit = runtime.weights.materialize_weight_profile(runtime.modules, runtime.bundle, None)
    _require(isinstance(config, Mapping) and config.get("provider") == "codex" and config.get("model") == "gpt-5.6-sol" and config.get("reasoning") == "high" and config.get("artifact_id") == record.get("logical_sample_id") and config.get("question_ids") == ids and config.get("batch_size") == 8 and config.get("retry_policy") == {"batch_attempts": 1} and config.get("attempt_lifecycle_policy") == "terminal_sidecar_v1" and config.get("weight_profile") == weight_audit, "Sol run configuration differs")
    count = 23 if expected_batches is None else expected_batches
    _require(type(count) is int and 1 <= count <= 23, "Sol expected batch prefix differs")
    verdicts, checkpoint_count, head = runtime.runner._load_checkpoints(root, artifact_text=text, context_texts=[], batch_attempts=1)
    _require(checkpoint_count == count and len(verdicts) == sum(len(item["question_ids"]) for item in planned[:count]), "Sol checkpoint prefix differs")
    threads: list[str] = []
    recovered = 0
    for request in planned[:count]:
        number = request["batch_number"]
        checkpoint = _json(_relative(root, f"responses/batch-{number:04d}.json").read_bytes(), "Sol checkpoint")
        _require(checkpoint.get("accepted_attempt") == 1 and checkpoint.get("question_ids") == request["question_ids"], "Sol checkpoint request differs")
        prompt, schema = _relative(Path(plan_root), request["prompt_path"]).read_bytes(), _relative(Path(plan_root), request["schema_path"]).read_bytes()
        _require(gzip.decompress(_relative(root, f"responses/batch-{number:04d}.prompt.txt.gz").read_bytes()) == prompt and _sha(prompt) == request["prompt_sha256"] and len(prompt) == request["prompt_bytes"] and _relative(root, f"responses/schemas/batch-{number:04d}.json").read_bytes() == schema and _sha(schema) == request["schema_sha256"] and len(schema) == request["schema_bytes"], "Sol retained prompt or schema differs")
        provider = checkpoint.get("provider"); metadata = provider.get("dryad_sol") if isinstance(provider, Mapping) else None
        _require(isinstance(metadata, Mapping) and metadata.get("ordinal") == request["ordinal"] and metadata.get("source_bindings") == dict(expected_source_bindings), "Sol provider binding differs")
        authorized = _time(metadata.get("authorized_at"), "Sol authorization")
        _route(metadata, authorized)
        cohort = metadata.get("cohort_number"); start = ((request["ordinal"] - 1) // 10) * 10 + 1
        _require(type(cohort) is int and cohort == (request["ordinal"] - 1) // 10 + 1 and metadata["review_sha256"] in expected_reviews, "Sol cohort binding differs")
        review_raw = _relative(execution, f"cohorts/{cohort:04d}/reviews/{metadata['review_sha256']}.json").read_bytes(); review = _json(review_raw, "Sol review")
        _require(_sha(review_raw) == metadata["review_sha256"] and set(review) == {"schema_version", "decision", "plan_sha256", "cohort_number", "ordinals", "source_bindings", "route_sha256", "reviewed_at", "expires_at", "reviewer_task"} and review.get("schema_version") == 1 and review.get("decision") == "approved_sol_cohort" and review.get("plan_sha256") == PLAN_SHA256 and review.get("cohort_number") == cohort and review.get("ordinals") == list(range(start, min(start + 10, 5429))) and review.get("source_bindings") == dict(expected_source_bindings) and review.get("route_sha256") == metadata["route_sha256"] and isinstance(review.get("reviewer_task"), str) and review["reviewer_task"], "Sol review differs")
        reviewed, expires = _time(review["reviewed_at"], "Sol review"), _time(review["expires_at"], "Sol review")
        _require(reviewed <= authorized <= expires <= reviewed + timedelta(hours=2), "Sol review window differs")
        artifacts = provider.get("provider_artifacts") if isinstance(provider, Mapping) else None
        _require(isinstance(artifacts, Mapping) and set(artifacts) == {"codex_events", "codex_stderr"}, "Sol provider artifacts differ")
        command = list(v3._expected_codex_command(config.get("codex_bin", "codex"), root))
        command[command.index("--output-schema") + 1] = str(root / f"responses/schemas/batch-{number:04d}.json")
        command[command.index("--output-last-message") + 1] = str(root / f"responses/batch-{number:04d}.attempt-0001.message.json")
        command[-1:-1] = ["--disable", "code_mode"]
        _require(config.get("codex_bin") == metadata["route_snapshot"]["codex_command"][0] == provider.get("command", [None])[0] and provider.get("command") == command, "Sol native command differs")
        for descriptor in artifacts.values():
            path = _relative(root, descriptor.get("path")); _require(runtime.runner._provider_artifact(root, path) == dict(descriptor), "Sol provider artifact hash differs")
        stderr = _relative(root, artifacts["codex_stderr"]["path"]).read_bytes(); v3._strict_stderr_labels(stderr)
        events = _relative(root, artifacts["codex_events"]["path"]).read_bytes()
        final = _relative(root, checkpoint["response_artifact"]["path"]).read_bytes()
        parser = v3._load_parse_codex_events()
        if request["ordinal"] == ALLOWLIST["ordinal"]:
            _target_evidence(root, request, checkpoint, manifest, stderr, final, v3)
            parser = _parse_exact_events
            recovered += 1
        projection = v3._codex_event_projection(events, parser)
        _require(projection.get("completed_agent_message_text", "").encode("utf-8") == final and isinstance(projection.get("thread_id"), str) and projection["thread_id"] and isinstance(projection.get("usage"), dict), "Sol native event projection differs")
        threads.append(projection["thread_id"])
    _require(recovered == 1, "Recovery prefix must contain exactly ordinal 221")
    _require(len(threads) == len(set(threads)), "Duplicate local Sol thread identity")
    result: dict[str, Any] = {"verdicts": [{"question_id": item["question_id"], "verdict": item["verdict"]} for item in verdicts], "checkpoint_head_sha256": head, "local_thread_ids": threads, "requested_identity": {"model": "gpt-5.6-sol", "reasoning": "high", "identity_evidence": "requested_only", "native_endpoint_contact_cardinality": "unproven"}, "score": None, "coverage": None}
    if count == 23:
        score = runtime.core.score_bundle(runtime.modules, runtime.bundle, verdicts, artifact_id=record["logical_sample_id"], task_contract=None)
        score["weight_profile"] = weight_audit
        _require(_relative(root, "score.json").read_bytes() == runtime.runner._json_bytes(score), "Sol score replay differs")
        observed, coverage = score["final_score"]["observed"], score["coverage"]
        _require(type(observed) in (int, float) and math.isfinite(observed) and 0 <= observed <= 100 and type(coverage) in (int, float) and math.isfinite(coverage) and coverage >= .88, "Sol score or coverage differs")
        result.update(score=observed, coverage=coverage)
    return result
