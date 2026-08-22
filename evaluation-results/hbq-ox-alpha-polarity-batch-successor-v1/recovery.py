"""No-contact recovery overlay for sealed Ox successor evidence."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import gzip
import json
from pathlib import Path
from typing import Any

from hbqrs import runner as hbq_runner
from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, prompts_dir
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY
from hbqrs.weights import materialize_weight_profile

import live as v1

HERE = Path(__file__).resolve().parent
RECONCILIATION_NAME = "reconciliation-v1.json"
RETRY_SUCCESSOR_NAME = "retry-successor-frozen-v1.json"
PROMPT_RECONSTRUCTION_ERROR = "Accepted prompt does not reconstruct from frozen inputs and projection"


def _expected_prompt(row: Mapping[str, Any], inputs: Mapping[str, Any], registry: Path) -> bytes:
    effective = v1._effective_question_ids(row, inputs, registry)
    if effective != list(row["question_ids"]):
        raise ValueError("Execution question order does not match compiled projection order")
    modules, bundle, _ = materialize_weight_profile(load_modules(registry), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    task = v1._read(Path(str(inputs["task_contract"])))
    compiled = compile_bundle(modules, bundle, task_contract=task)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    selected = [item for item in questions if item["question"]["id"] in set(row["question_ids"])]
    binary = hbq_runner._read_text_record(prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md")["text"].strip()
    artifact = hbq_runner._read_text_record(Path(str(inputs["artifact"])))
    context = hbq_runner._read_text_record(Path(str(inputs["prompt"])))
    return hbq_runner._render_prompt(binary_prompt=binary, artifact=artifact, contexts=[context], bundle_id="prose.short_story", artifact_id=str(row["story_id"]), questions=selected, provider="nous", model=v1.PROVIDER["model"]).encode("utf-8")


def _accepted(attempt_dir: Path, row: Mapping[str, Any], binding: Mapping[str, Any], inputs: Mapping[str, Any], registry: Path) -> dict[str, Any]:
    responses = attempt_dir / "responses"
    checkpoints = sorted(responses.glob("batch-[0-9][0-9][0-9][0-9].json"))
    verdict_path = attempt_dir / "verdicts.jsonl"
    if len(checkpoints) != 1 or list((responses / "rejected").rglob("*.json")) or not verdict_path.is_file():
        raise ValueError("Accepted attempt lacks one clean completed batch")
    checkpoint = v1._read(checkpoints[0])
    prompt_path = checkpoints[0].with_suffix(".prompt.txt.gz")
    if (checkpoint.get("format_version") != 4 or checkpoint.get("batch") != 1 or checkpoint.get("previous_checkpoint_sha256") is not None
            or checkpoint.get("question_ids") != row["question_ids"] or checkpoint.get("retry_policy") != {"batch_attempts": 1}
            or checkpoint.get("accepted_attempt") != 1 or checkpoint.get("recovered_from_rejected") is not None
            or checkpoint.get("rejected_chain") != {"count": 0, "head_sha256": None}):
        raise ValueError("Accepted checkpoint is not the cap-one contract")
    prompt_bytes = gzip.decompress(prompt_path.read_bytes())
    if prompt_bytes != _expected_prompt(row, inputs, registry):
        raise ValueError(PROMPT_RECONSTRUCTION_ERROR)
    artifact = hbq_runner._read_text_record(Path(str(inputs["artifact"])))
    context = hbq_runner._read_text_record(Path(str(inputs["prompt"])))
    try:
        replayed, count, previous = hbq_runner._load_checkpoints(attempt_dir, artifact_text=artifact["text"], context_texts=[context["text"]], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as error:
        raise ValueError("Accepted checkpoint/schema replay failed") from error
    verdicts = [json.loads(line) for line in verdict_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if count != 1 or previous != v1._sha(checkpoints[0].read_bytes()) or replayed != verdicts or len(verdicts) != len(row["question_ids"]) or {item.get("question_id") for item in verdicts} != set(row["question_ids"]):
        raise ValueError("Accepted response does not cover exactly the scheduled questions")
    configuration = v1._read(attempt_dir / "run.json").get("configuration")
    if not isinstance(configuration, Mapping) or any(configuration.get(key) != value for key, value in {"provider": "nous", "model": v1.PROVIDER["model"], "reasoning": "max", "batch_size": len(row["question_ids"]), "retry_policy": {"batch_attempts": 1}, "artifact_id": row["story_id"], "bundle_id": "prose.short_story", "question_ids": row["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True}.items()) or not isinstance(configuration.get("nous_transport_policy"), Mapping) or configuration["nous_transport_policy"].get("max_physical_attempts_per_logical_request") != 1:
        raise ValueError("Accepted run configuration drifts from the frozen cap-one request")
    provider = checkpoint.get("provider")
    if not isinstance(provider, Mapping):
        raise ValueError("Accepted checkpoint lacks a provider receipt")
    try:
        hbq_runner._validate_provider_artifacts(attempt_dir, checkpoint)
    except Exception as error:
        raise ValueError("Accepted provider artifacts are invalid") from error
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("Accepted provider artifact bindings are missing")
    request_ref, proof_ref = (artifacts.get(key, {}).get("path") if isinstance(artifacts.get(key), Mapping) else None for key in ("judge_request", "serialization_proof"))
    if not isinstance(request_ref, str) or not isinstance(proof_ref, str):
        raise ValueError("Accepted raw request or proof is unbound")
    request, proof = attempt_dir / request_ref, attempt_dir / proof_ref
    v9, _, bridge = v1._bridge()
    v8 = v9.parent_v8()
    evidence_root = attempt_dir / artifacts["evidence_tree"]["path"]
    judge, prove = v8.v7_verifier()._judge_leaf(evidence_root, proof)
    for leaf in (judge, prove):
        bridge.validate_evidence(leaf)
    if not getattr(bridge.serialization_proof_status(evidence_root, str(proof), expected_sha256=v1._sha(proof.read_bytes())), "valid", False):
        raise ValueError("Accepted serialization proof is invalid")
    judge_events = v1._events(judge / "events.jsonl")
    http = [event.get("data") for event in judge_events if event.get("event_type") == "http_attempt"]
    prove_events = v1._events(prove / "events.jsonl")
    if len(http) != 1 or not isinstance(http[0], Mapping) or not 200 <= int(http[0].get("status", 0)) < 300 or any(event.get("event_type") == "http_attempt" for event in prove_events):
        raise ValueError("Accepted evidence is not exactly one 2xx Judge attempt")
    v1._verify_judge_request(bridge, judge, judge_events, request, http[0])
    request_value = v1._read(request)
    messages = request_value.get("messages")
    if not isinstance(messages, list) or len(messages) != 2 or messages[1].get("content") != prompt_bytes.decode("utf-8") or checkpoint.get("prompt_sha256") != v1._sha(prompt_bytes) or checkpoint.get("base_prompt_sha256") != v1._sha(prompt_bytes):
        raise ValueError("Accepted prompt/checkpoint/request replay drifted")
    receipt = v1._read(judge / "receipt.json")
    session_id, logical_id = receipt.get("run_id"), http[0].get("logical_request_id")
    receipt_id = f"nous:{provider.get('evidence_sha256')}:{provider.get('serialization_proof_sha256')}"
    if receipt.get("status") != "success" or any(not isinstance(value, str) or not value for value in (session_id, logical_id, receipt_id)):
        raise ValueError("Accepted provider identities are malformed")
    normalized_ids: set[str] = set()
    for checkpoint_path in (attempt_dir / "responses").glob("batch-*.json"):
        value = v1._read(checkpoint_path)
        if isinstance(value.get("normalization_audit"), list):
            normalized_ids.update(str(item.get("question_id")) for item in value["normalization_audit"] if isinstance(item, Mapping))
    records = [{"status": "accepted", "story_id": row["story_id"], "condition_id": row["condition_id"], "polarity": row["polarity"], "question_id": item["question_id"], "verdict": item["verdict"], "confidence": item["confidence"], "normalized_evidence": item["question_id"] in normalized_ids} for item in verdicts]
    return {"status": "accepted", "static_binding": binding["static_sha256"], "prompt": v1._hash_binding(v1.fingerprint(prompt_path)), "request": v1._hash_binding(v1.fingerprint(request)), "accepted_identities": {"receipt_id": receipt_id, "session_id": session_id, "logical_request_id": logical_id}, "run": v1.fingerprint(attempt_dir / "run.json"), "checkpoint": v1.fingerprint(checkpoints[0]), "verdicts": v1.fingerprint(verdict_path), "records": records}


def _source(work: Path) -> dict[str, Any]:
    frozen = v1._read(work / v1.FROZEN_NAME)
    runtime = frozen.get("runtime")
    if (frozen.get("study_id") != v1.study.HERE.name or frozen.get("schedule") != v1.study.schedule()
            or frozen.get("schedule_sha256") != v1._sha(v1._canonical(v1.study.schedule())) or frozen.get("provider") != v1.PROVIDER
            or not isinstance(runtime, Mapping) or runtime.get("live") != v1.fingerprint(v1.HERE / "live.py")
            or runtime.get("study") != v1.fingerprint(v1.HERE / "study.py")
            or runtime.get("runner") != v1.fingerprint(Path(hbq_runner.__file__)) or runtime.get("bundles") != v1.fingerprint(bundles_path())):
        raise ValueError("Recovery source does not bind the sealed v1 runtime and inputs")
    if frozen.get("private_inputs") != v1.fingerprint(work / "private-inputs.json"):
        raise ValueError("Recovery source private inputs drifted")
    for polarity in ("positive", "negative_failure"):
        if frozen.get("projections", {}).get(polarity) != v1.fingerprint(work / "projections" / f"{polarity}.registry.json"):
            raise ValueError("Recovery source projection drifted")
    return frozen


def _pairs(work: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pending: dict[tuple[str, int], dict[str, Any]] = {}
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in v1._records(work):
        key = (str(row.get("call_id")), int(row.get("attempt", 0)))
        if row.get("kind") == "intent":
            pending[key] = row
        elif row.get("kind") == "result":
            intent = pending.pop(key, None)
            if intent is None or row.get("binding") != intent.get("binding"):
                raise ValueError("Recovery journal pairing is malformed")
            pairs.append((intent, row))
        else:
            raise ValueError("Recovery journal kind is malformed")
    if pending:
        raise ValueError("Recovery source has interrupted intents")
    return pairs


def _counts(results: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {status: sum(item.get("status") == status for item in results) for status in ("accepted", "eligible_524", "quarantined", "global_stop")}


def _is_candidate(result: Mapping[str, Any]) -> bool:
    error = result.get("error")
    return result.get("status") == "quarantined" and isinstance(error, Mapping) and error.get("class") == "ValueError" and error.get("message") == PROMPT_RECONSTRUCTION_ERROR


def reconcile(work: Path) -> dict[str, Any]:
    """Record corrected verification without altering the sealed v1 journal."""
    frozen = _source(work)
    pairs = _pairs(work)
    source_frozen = v1.fingerprint(work / v1.FROZEN_NAME)
    source_journal = [v1.fingerprint(work / "attempt-records" / f"{index:06d}.json") for index in range(1, len(v1._records(work)) + 1)]
    destination = work / RECONCILIATION_NAME
    if destination.exists():
        existing = v1._read(destination)
        if existing.get("kind") != "prompt_reconstruction_recovery_overlay" or existing.get("source_frozen") != source_frozen or existing.get("source_journal") != source_journal:
            raise ValueError("Existing recovery overlay does not bind this sealed source")
        return existing
    inputs = v1._read(work / "private-inputs.json")
    schedule = {str(item["call_id"]): item for item in frozen["schedule"]}
    final = {str(intent["call_id"]): (intent, result) for intent, result in pairs}
    replacements: list[dict[str, Any]] = []
    effective: list[dict[str, Any]] = []
    for call_id, (intent, result_row) in final.items():
        source = result_row["result"]
        if not _is_candidate(source):
            effective.append(dict(source))
            continue
        binding = intent["binding"]
        source_row = schedule.get(call_id)
        if not isinstance(binding, Mapping) or source_row is None:
            raise ValueError("Recovery candidate lacks its frozen request")
        row = {**source_row, "question_ids": list(binding["question_ids"]), "frozen_question_ids": list(source_row["question_ids"])}
        accepted = _accepted(work / "runs" / call_id / f"attempt-{int(intent['attempt']):02d}", row, binding, inputs[str(row["story_id"])], work / "projections" / f"{row['polarity']}.registry.json")
        if accepted.get("static_binding") != binding.get("static_sha256"):
            raise ValueError("Recovery result does not bind its sealed request")
        source_path = work / "attempt-records" / f"{int(result_row['sequence']):06d}.json"
        replacements.append({"call_id": call_id, "attempt": int(intent["attempt"]), "source_result": v1.fingerprint(source_path), "result": accepted})
        effective.append(accepted)
    analysis_rows = [record for item in effective if item["status"] == "accepted" for record in item.get("records", [])]
    payload = {
        "format_version": 1,
        "study_id": frozen["study_id"],
        "kind": "prompt_reconstruction_recovery_overlay",
        "status": "partial_no_contact",
        "source_frozen": source_frozen,
        "source_journal": source_journal,
        "recovery_runtime": {"overlay": v1.fingerprint(Path(__file__)), "v1_live": v1.fingerprint(v1.HERE / "live.py"), "runner": v1.fingerprint(Path(hbq_runner.__file__)), "binary_prompt": v1.fingerprint(prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md")},
        "source_status_counts": _counts([result["result"] for _, result in final.values()]),
        "effective_status_counts": _counts(effective),
        "reconciled_results": replacements,
        "analysis": v1.study.analyze(analysis_rows + [{"status": item["status"]} for item in effective if item["status"] != "accepted"]),
        "confirmation_available": False,
        "production_recommendation": None,
    }
    v1._immutable(work / RECONCILIATION_NAME, payload)
    return payload


def prepare_retry_successor(source_work: Path, work: Path) -> dict[str, Any]:
    """Freeze, but do not execute, the twelve sealed outbound-524 retries."""
    source_work, work = source_work.resolve(), work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Retry successor work root must be new and empty")
    frozen = _source(source_work)
    reconciliation = reconcile(source_work)
    inputs = v1._read(source_work / "private-inputs.json")
    schedule = {str(item["call_id"]): item for item in frozen["schedule"]}
    requests: list[dict[str, Any]] = []
    for intent, result_row in _pairs(source_work):
        result = result_row["result"]
        if result.get("status") != "eligible_524":
            continue
        call_id = str(intent["call_id"])
        binding = intent["binding"]
        source_row = schedule.get(call_id)
        if not isinstance(binding, Mapping) or source_row is None:
            raise ValueError("Retry successor request lacks frozen provenance")
        row = {**source_row, "question_ids": list(binding["question_ids"]), "frozen_question_ids": list(source_row["question_ids"])}
        expected = _expected_prompt(row, inputs[str(row["story_id"])], source_work / "projections" / f"{row['polarity']}.registry.json")
        prompt = result.get("prompt")
        request = result.get("request")
        prompt_paths = list((source_work / "runs" / call_id / f"attempt-{int(intent['attempt']):02d}" / "responses").glob("batch-*.prompt.txt.gz"))
        if len(prompt_paths) != 1 or gzip.decompress(prompt_paths[0].read_bytes()) != expected or not isinstance(prompt, Mapping) or prompt != v1._hash_binding(v1.fingerprint(prompt_paths[0])) or not isinstance(request, Mapping):
            raise ValueError("Retry successor prompt or request binding drifted")
        source_path = source_work / "attempt-records" / f"{int(result_row['sequence']):06d}.json"
        requests.append({"call_id": call_id, "question_ids": list(binding["question_ids"]), "polarity": row["polarity"], "source_result": v1.fingerprint(source_path), "source_prompt": dict(prompt), "source_request": dict(request)})
    if len(requests) != 12:
        raise ValueError("Retry successor requires exactly the 12 sealed eligible-524 requests")
    payload = {
        "format_version": 1,
        "study_id": frozen["study_id"],
        "kind": "prepared_retry_successor_contract",
        "status": "prepared_no_provider_contact",
        "parent": {"frozen": v1.fingerprint(source_work / v1.FROZEN_NAME), "reconciliation": v1.fingerprint(source_work / RECONCILIATION_NAME)},
        "runtime": {"overlay": v1.fingerprint(Path(__file__)), "v1_live": v1.fingerprint(v1.HERE / "live.py"), "runner": v1.fingerprint(Path(hbq_runner.__file__))},
        "provider": v1.PROVIDER,
        "retry_requests": requests,
        "logical_calls": len(requests),
        "maximum_physical_calls": len(requests) * v1.study.AVAILABILITY["eligible_524_attempt_ceiling"],
        "limits": ["Preparation makes no provider call.", "This contract is not an executor.", "Each later send must preserve the carried-forward prompt and request bindings."],
    }
    v1._immutable(work / RETRY_SUCCESSOR_NAME, payload)
    return payload
