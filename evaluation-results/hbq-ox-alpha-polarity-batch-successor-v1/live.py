#!/usr/bin/env python3
"""Private, cap-one execution boundary for the frozen Ox polarity screen.

The study module intentionally remains offline.  This module is the only place
that may call the existing hardened Nous runner, and only after `prepare_work`
has sealed a private work root.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from hbqrs import runner as hbq_runner
from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, prompts_dir, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, run_judge
from hbqrs.weights import materialize_weight_profile

import study

HERE = Path(__file__).resolve().parent
FROZEN_NAME = "frozen-ox-alpha-polarity-batch-live-v1.json"
PROVIDER = {"provider": "nous", "model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "max_physical_http_attempts_per_logical_request": 1}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": _sha(path.read_bytes())}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def _immutable(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"Immutable evidence drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(rendered); out.flush(); os.fsync(out.fileno())
        Path(temp).replace(path)
    finally:
        Path(temp).unlink(missing_ok=True)


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load the frozen v9 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v9() -> Any:
    return _load_module(HERE.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v9" / "study.py", "ox_successor_live_v9")


def _v9_runner(v9: Any) -> Any:
    path = HERE.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v9" / "run_pilot.py"
    spec = importlib.util.spec_from_file_location("ox_successor_live_v9_runner", path)
    if spec is None or spec.loader is None:
        raise ValueError("Unable to load the frozen v9 executor")
    module = importlib.util.module_from_spec(spec); prior = sys.modules.get("study")
    sys.modules[spec.name] = module; sys.modules["study"] = v9
    try: spec.loader.exec_module(module)
    finally:
        if prior is None: sys.modules.pop("study", None)
        else: sys.modules["study"] = prior
    return module


def _replace_questions(value: Any, replacements: Mapping[str, str], seen: dict[str, list[str]]) -> None:
    if isinstance(value, dict):
        question_id = value.get("id")
        if value.get("type") == "question" and isinstance(question_id, str):
            if question_id in replacements:
                value["text"] = replacements[question_id]
            seen.setdefault(question_id, []).append(str(value.get("text")))
        for child in value.values():
            _replace_questions(child, replacements, seen)
    elif isinstance(value, list):
        for child in value:
            _replace_questions(child, replacements, seen)


def _projection(work: Path, polarity: str) -> Path:
    target = work / "projections" / f"{polarity}.registry.json"
    if target.exists():
        return target
    registry = json.loads(registry_path().read_text(encoding="utf-8"))
    replacements = (study._question_texts() if polarity == "positive" else study.reviewed_pairs())
    before = json.loads(registry_path().read_text(encoding="utf-8"))
    seen_before: dict[str, list[str]] = {}; seen_after: dict[str, list[str]] = {}
    _replace_questions(before, {}, seen_before); _replace_questions(registry, replacements, seen_after)
    if any(len(seen_before.get(question_id, ())) != 1 or len(seen_after.get(question_id, ())) != 1 for question_id in study.QUESTION_IDS):
        raise ValueError("Registry projection requires exactly one occurrence of every selected leaf")
    changed = {key for key in seen_before if seen_before[key] != seen_after.get(key)}
    if changed - set(study.QUESTION_IDS) or any(seen_after[question_id] != [replacements[question_id]] for question_id in study.QUESTION_IDS):
        raise ValueError("Registry projection did not make exactly the reviewed selected changes")
    _immutable(target, registry)
    return target


def _external_to_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(HERE.parent.parent.resolve())
        return False
    except ValueError:
        return True


def runtime_bindings() -> dict[str, Any]:
    from hbqrs import runner
    launcher = runner.NOUS_LAUNCHER_PATH
    return {
        "study": fingerprint(HERE / "study.py"),
        "live": fingerprint(Path(__file__)),
        "contract": fingerprint(HERE / "study-contract.json"),
        "runner": fingerprint(Path(runner.__file__)),
        "launcher": fingerprint(launcher),
        "bridge": fingerprint(launcher.parent / "nous_codex_bridge.py"),
        "bundles": fingerprint(bundles_path()),
    }


def _inputs(v9_frozen: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    units = v9_frozen.get("units")
    if not isinstance(units, list):
        raise ValueError("v9 frozen units are malformed")
    result: dict[str, dict[str, str]] = {}
    for unit in units:
        if not isinstance(unit, Mapping) or unit.get("item_id") not in study.STORIES:
            continue
        story_id = str(unit["item_id"])
        paths = unit.get("paths")
        if not isinstance(paths, Mapping):
            raise ValueError("v9 unit lacks private input paths")
        frozen_inputs = unit.get("inputs")
        if not isinstance(frozen_inputs, Mapping):
            raise ValueError("v9 unit lacks frozen input fingerprints")
        candidate = {key: str(paths[key]) for key in ("artifact", "prompt", "task_contract")}
        candidate["frozen_inputs"] = dict(frozen_inputs)
        if story_id in result and result[story_id] != candidate:
            raise ValueError("v9 has conflicting input paths for a frozen story")
        result[story_id] = candidate
    if set(result) != set(study.STORIES):
        raise ValueError("v9 does not provide all frozen story inputs")
    return result


def prepare_work(v9_root: Path, zero_cost_proof: Path, work: Path) -> dict[str, Any]:
    """Stage private projections and immutable no-charge execution bindings."""
    v9_root, zero_cost_proof, work = v9_root.resolve(), zero_cost_proof.resolve(), work.resolve()
    if work.exists() and any(work.iterdir()):
        raise ValueError("Live work root must be empty")
    if not _external_to_repo(work):
        raise ValueError("Live work must be external to the repository")
    helper = _v9()
    v9_frozen = helper.load_frozen(v9_root)
    zero = helper.parent_v8()._zero_cost_proof(zero_cost_proof)
    now = datetime.now(timezone.utc).isoformat()
    helper.parent_v8().assert_fresh_at(zero, now)
    inputs = _inputs(v9_frozen)
    work.mkdir(parents=True, exist_ok=True)
    projections = {polarity: fingerprint(_projection(work, polarity)) for polarity in ("positive", "negative_failure")}
    _immutable(work / "private-inputs.json", inputs)
    schedule = study.schedule()
    frozen = {
        "format_version": 1,
        "study_id": study.load_contract()["study_id"],
        "kind": "private_cap_one_execution_boundary",
        "contract": fingerprint(HERE / "study-contract.json"),
        "runtime": runtime_bindings(),
        "v9_root": str(v9_root),
        "v9_frozen": fingerprint(v9_root / helper.FROZEN_NAME),
        "zero_cost_proof": {**zero, "freshness_checked_at": now},
        "schedule": schedule,
        "schedule_sha256": _sha(_canonical(schedule)),
        "projections": projections,
        "private_inputs": fingerprint(work / "private-inputs.json"),
        "provider": PROVIDER,
        "disclosure": {"destination": "Nous hardened tool-free bridge -> authenticated Nous service", "first_screen_logical_calls": 30, "first_screen_max_physical_calls": 150, "confirmation_logical_calls": 30, "confirmation_max_physical_calls": 150, "paid_route": False},
    }
    _immutable(work / FROZEN_NAME, frozen)
    return frozen


def load_frozen(work: Path) -> dict[str, Any]:
    frozen = _read(work / FROZEN_NAME)
    required = {"format_version", "study_id", "kind", "contract", "runtime", "v9_root", "v9_frozen", "zero_cost_proof", "schedule", "schedule_sha256", "projections", "private_inputs", "provider", "disclosure"}
    if (set(frozen) != required or frozen.get("format_version") != 1 or frozen.get("study_id") != study.HERE.name
            or frozen.get("kind") != "private_cap_one_execution_boundary" or frozen.get("contract") != fingerprint(HERE / "study-contract.json")
            or frozen.get("runtime") != runtime_bindings() or frozen.get("schedule") != study.schedule()
            or frozen.get("schedule_sha256") != _sha(_canonical(study.schedule())) or frozen.get("provider") != PROVIDER
            or frozen.get("disclosure") != {"destination": "Nous hardened tool-free bridge -> authenticated Nous service", "first_screen_logical_calls": 30, "first_screen_max_physical_calls": 150, "confirmation_logical_calls": 30, "confirmation_max_physical_calls": 150, "paid_route": False}
            or not isinstance(frozen.get("v9_root"), str)):
        raise ValueError("Live frozen contract drifted")
    helper = _v9(); v9_root = Path(str(frozen["v9_root"]))
    if frozen.get("v9_frozen") != fingerprint(v9_root / helper.FROZEN_NAME):
        raise ValueError("Frozen v9 source drifted")
    helper.load_frozen(v9_root)
    if frozen.get("private_inputs") != fingerprint(work / "private-inputs.json"):
        raise ValueError("Private input binding drifted")
    for polarity in ("positive", "negative_failure"):
        if frozen["projections"].get(polarity) != fingerprint(work / "projections" / f"{polarity}.registry.json"):
            raise ValueError("Registry projection drifted")
    return frozen


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "attempt-records"
    if not root.exists():
        return []
    paths = sorted(root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))
    records = [_read(path) for path in paths]
    if len(paths) != len(list(root.iterdir())) or [row.get("sequence") for row in records] != list(range(1, len(records) + 1)):
        raise ValueError("Attempt journal is malformed")
    return records


def _append(work: Path, row: Mapping[str, Any]) -> None:
    records = _records(work)
    _immutable(work / "attempt-records" / f"{len(records)+1:06d}.json", {"sequence": len(records) + 1, **row})


def _histories(work: Path) -> dict[str, list[dict[str, Any]]]:
    pending: dict[tuple[str, int], dict[str, Any]] = {}
    histories: dict[str, list[dict[str, Any]]] = {}
    for row in _records(work):
        call_id, attempt = row.get("call_id"), row.get("attempt")
        if not isinstance(call_id, str) or not isinstance(attempt, int):
            raise ValueError("Attempt record identity is malformed")
        key = (call_id, attempt)
        if row.get("kind") == "intent":
            if key in pending: raise ValueError("Duplicate attempt intent")
            pending[key] = row
        elif row.get("kind") == "result":
            if key not in pending: raise ValueError("Result lacks immutable intent")
            intent = pending.pop(key)
            if row.get("binding") != intent.get("binding"):
                raise ValueError("Result does not bind its immutable request")
            result = row.get("result")
            if not isinstance(result, Mapping) or result.get("status") not in {"accepted", "eligible_524", "quarantined", "global_stop"}:
                raise ValueError("Result status is malformed")
            histories.setdefault(call_id, []).append(dict(result))
        else:
            raise ValueError("Unknown attempt record kind")
    if pending:
        raise ValueError("Interrupted intent has no result; no resend is safe")
    return histories


def _trailing_eligible_524(work: Path) -> int:
    count = 0
    for row in reversed(_records(work)):
        if row.get("kind") != "result":
            continue
        result = row.get("result")
        if not isinstance(result, Mapping) or result.get("status") != "eligible_524":
            break
        count += 1
    return count


def _binding(work: Path, row: Mapping[str, Any], *, effective_question_ids: Sequence[str] | None = None) -> dict[str, Any]:
    inputs = _read(work / "private-inputs.json")
    story = inputs.get(str(row.get("story_id")))
    if not isinstance(story, Mapping):
        raise ValueError("Scheduled story lacks private inputs")
    registry = work / "projections" / f"{row.get('polarity')}.registry.json"
    binding = {
        "call_id": row["call_id"], "story_id": row["story_id"], "condition_id": row["condition_id"],
        "polarity": row["polarity"], "frozen_question_ids": list(row.get("frozen_question_ids", row["question_ids"])), "question_ids": list(effective_question_ids or row["question_ids"]), "registry": fingerprint(registry),
        "artifact": fingerprint(Path(str(story["artifact"]))), "prompt": fingerprint(Path(str(story["prompt"]))),
        "task_contract": fingerprint(Path(str(story["task_contract"]))), "provider": PROVIDER,
    }
    expected = story.get("frozen_inputs")
    names = {"artifact": "source.md", "prompt": "prompt.md", "task_contract": "task-contract.json"}
    if not isinstance(expected, Mapping) or any(binding[key] != expected.get(name) for key, name in names.items()):
        raise ValueError("Current source input does not match the frozen v9 fingerprint")
    binding["static_sha256"] = _sha(_canonical(binding))
    return binding


def _v9_error_status(error: BaseException) -> str:
    text = str(error)
    is_524 = getattr(error, "http_status", None) == 524 or bool(re.search(r"\bHTTP\s*524\b", text, re.I))
    charge = getattr(error, "http_status", None) == 402 or bool(re.search(r"\b(?:HTTP\s*402|charge|payment)\b", text, re.I))
    return "global_stop" if charge else "candidate_524" if is_524 else "quarantined"


def _hash_binding(record: Mapping[str, Any]) -> dict[str, Any]:
    return {key: record[key] for key in ("bytes", "sha256")}


def _events(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Bridge evidence events are unreadable") from error


def _bridge() -> tuple[Any, Any, Any]:
    v9 = _v9(); executor = _v9_runner(v9); v8 = v9.parent_v8()
    return v9, executor, executor._bridge(v8)


def _verify_judge_request(bridge: Any, judge: Path, events: Sequence[Mapping[str, Any]], request_path: Path, http: Mapping[str, Any]) -> None:
    boundaries = [event.get("data") for event in events if event.get("event_type") == "judge_boundary"]
    if len(boundaries) != 1 or not isinstance(boundaries[0], Mapping):
        raise ValueError("Judge boundary is missing")
    try:
        messages, response_format, model, reasoning, cap = bridge.validate_judge_request(_read(request_path))
    except Exception as error:
        raise ValueError("Stored Judge request is invalid") from error
    normalized = {"schema": "codex-nous-tool-free-judge-request-v2", "messages": messages, "response_format": response_format, "model": model, "reasoning_effort": reasoning, "max_physical_http_attempts_per_logical_request": cap}
    payload = {"model": model, "reasoning_effort": reasoning, "messages": messages, "response_format": response_format}
    boundary = boundaries[0]
    if (model != PROVIDER["model"] or reasoning != PROVIDER["reasoning"] or cap != 1
            or boundary.get("request_schema") != normalized["schema"] or boundary.get("model_policy") != bridge.judge_model_policy(model)
            or boundary.get("transport_policy") != bridge.judge_transport_policy(1) or boundary.get("request_sha256") != bridge.sha256_bytes(bridge.canonical_bytes(normalized))
            or boundary.get("zero_tools") is not True or http.get("request_payload_sha256") != bridge.sha256_bytes(bridge.canonical_bytes(payload))):
        raise ValueError("Signed Judge boundary or payload drifts from the cap-one Ox route")
    manifest = _read(judge / "manifest.json")
    if manifest.get("bridge_sha256") != runtime_bindings()["bridge"]["sha256"] or manifest.get("requested_provider") != "nous" or manifest.get("requested_model") != PROVIDER["model"] or manifest.get("requested_reasoning_effort") != "max" or manifest.get("transport") != "nous-chat-completions-mcp":
        raise ValueError("Judge evidence manifest drifts from the frozen runtime")


def _eligible_524(attempt_dir: Path) -> dict[str, Any]:
    """v9-equivalent proof: one pinned outbound 524 and no completion artifact."""
    responses = attempt_dir / "responses"; rejected = sorted((responses / "rejected").rglob("attempt-0001.json")); evidence = sorted(path for path in responses.glob("*.nous.evidence") if path.is_dir())
    prompts = sorted(responses.glob("batch-[0-9][0-9][0-9][0-9].prompt.txt.gz")); requests = sorted(responses.glob("*.nous.request.json"))
    if len(rejected) != 1 or len(evidence) != 1 or len(prompts) != 1 or len(requests) != 1 or list(responses.glob("*.nous.result.json")) or list(responses.glob("batch-[0-9][0-9][0-9][0-9].json")) or any((attempt_dir / name).exists() for name in ("verdicts.jsonl", "score.json", "score.v2.json")):
        raise ValueError("Attempt is not a sealed no-result candidate")
    rejected_record = _read(rejected[0])
    if rejected_record.get("provider") is not None or rejected_record.get("validation_feedback") is not None or "HTTP 524" not in str(rejected_record.get("error", {}).get("message", "")):
        raise ValueError("Failure is not a raw 524")
    _, executor, bridge = _bridge(); proofs = sorted(evidence[0].rglob("serialization-proof.json"))
    if len(proofs) != 1: raise ValueError("524 lacks one serialization proof")
    v8 = _v9().parent_v8(); verifier = v8.v7_verifier()
    judge, prove = verifier._judge_leaf(evidence[0], proofs[0])
    for leaf in (judge, prove): bridge.validate_evidence(leaf)
    proof_status = bridge.serialization_proof_status(evidence[0], str(proofs[0]), expected_sha256=_sha(proofs[0].read_bytes()))
    if not getattr(proof_status, "valid", False): raise ValueError("Serialization proof is not canonical")
    judge_events, prove_events = _events(judge / "events.jsonl"), _events(prove / "events.jsonl")
    attempts = [event.get("data") for event in judge_events if event.get("event_type") == "http_attempt"]
    if len(attempts) != 1 or not isinstance(attempts[0], Mapping) or attempts[0].get("status") != 524 or any(event.get("event_type") == "http_attempt" for event in prove_events) or any(event.get("event_type") == "message" and isinstance(event.get("data"), Mapping) and event["data"].get("direction") == "inbound" for event in judge_events):
        raise ValueError("524 is not one outbound-only Judge attempt")
    _verify_judge_request(bridge, judge, judge_events, requests[0], attempts[0])
    receipt = _read(judge / "receipt.json"); logical_id, session_id = attempts[0].get("logical_request_id"), receipt.get("run_id")
    receipt_sha, proof_sha = receipt.get("receipt_sha256"), _sha(proofs[0].read_bytes())
    if receipt.get("status") != "failure" or any(not isinstance(value, str) or not value for value in (logical_id, session_id, receipt_sha, proof_sha)):
        raise ValueError("524 receipt or provider identities are malformed")
    return {"status": "eligible_524", "prompt": _hash_binding(fingerprint(prompts[0])), "request": _hash_binding(fingerprint(requests[0])), "failed_identities": {"logical_request_id": logical_id, "session_id": session_id, "receipt_sha256": receipt_sha, "serialization_proof_sha256": proof_sha}, "judge_receipt": fingerprint(judge / "receipt.json"), "prove_receipt": fingerprint(prove / "receipt.json"), "serialization_proof": fingerprint(proofs[0]), "quiescent_tree": executor._quiescent_tree(attempt_dir)}


def _effective_question_ids(row: Mapping[str, Any], inputs: Mapping[str, Any], registry: Path) -> list[str]:
    modules, bundle, _ = materialize_weight_profile(load_modules(registry), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    task = _read(Path(str(inputs["task_contract"]))); compiled = compile_bundle(modules, bundle, task_contract=task)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    selected = [item for item in questions if item["question"]["id"] in set(row["question_ids"])]
    effective = [str(item["question"]["id"]) for item in selected]
    frozen = set(row.get("frozen_question_ids", row["question_ids"]))
    if len(effective) != len(frozen) or set(effective) != frozen: raise ValueError("Projected registry cannot render exactly the frozen selected question set")
    return effective


def _expected_prompt(row: Mapping[str, Any], inputs: Mapping[str, Any], registry: Path) -> bytes:
    effective = _effective_question_ids(row, inputs, registry)
    if effective != list(row["question_ids"]): raise ValueError("Execution question order does not match compiled projection order")
    modules, bundle, _ = materialize_weight_profile(load_modules(registry), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    task = _read(Path(str(inputs["task_contract"]))); compiled = compile_bundle(modules, bundle, task_contract=task)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    selected = [item for item in questions if item["question"]["id"] in set(row["question_ids"])]
    binary = (prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8").strip()
    return hbq_runner._render_prompt(binary_prompt=binary, artifact={"name": Path(str(inputs["artifact"])).name, "text": Path(str(inputs["artifact"])).read_text(encoding="utf-8")}, contexts=[{"name": Path(str(inputs["prompt"])).name, "text": Path(str(inputs["prompt"])).read_text(encoding="utf-8")}], bundle_id="prose.short_story", artifact_id=str(row["story_id"]), questions=selected, provider="nous", model=PROVIDER["model"]).encode("utf-8")


def _accepted(attempt_dir: Path, row: Mapping[str, Any], binding: Mapping[str, Any], response: Mapping[str, Any], inputs: Mapping[str, Any], registry: Path) -> dict[str, Any]:
    responses = attempt_dir / "responses"; checkpoints = sorted(responses.glob("batch-[0-9][0-9][0-9][0-9].json"))
    verdict_path = attempt_dir / "verdicts.jsonl"
    if len(checkpoints) != 1 or list((responses / "rejected").rglob("*.json")) or not verdict_path.is_file():
        raise ValueError("Accepted attempt lacks one clean completed batch")
    checkpoint = _read(checkpoints[0]); prompt_path = checkpoints[0].with_suffix(".prompt.txt.gz")
    if (checkpoint.get("format_version") != 4 or checkpoint.get("batch") != 1 or checkpoint.get("previous_checkpoint_sha256") is not None
            or checkpoint.get("question_ids") != row["question_ids"] or checkpoint.get("retry_policy") != {"batch_attempts": 1}
            or checkpoint.get("accepted_attempt") != 1 or checkpoint.get("recovered_from_rejected") is not None
            or checkpoint.get("rejected_chain") != {"count": 0, "head_sha256": None}):
        raise ValueError("Accepted checkpoint is not the cap-one contract")
    prompt_bytes = gzip.decompress(prompt_path.read_bytes())
    if prompt_bytes != _expected_prompt(row, inputs, registry): raise ValueError("Accepted prompt does not reconstruct from frozen inputs and projection")
    try:
        replayed, count, previous = hbq_runner._load_checkpoints(attempt_dir, artifact_text=Path(str(inputs["artifact"])).read_text(encoding="utf-8"), context_texts=[Path(str(inputs["prompt"])).read_text(encoding="utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as error:
        raise ValueError("Accepted checkpoint/schema replay failed") from error
    verdicts = [json.loads(line) for line in verdict_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if count != 1 or previous != _sha(checkpoints[0].read_bytes()) or replayed != verdicts or len(verdicts) != len(row["question_ids"]) or {item.get("question_id") for item in verdicts} != set(row["question_ids"]):
        raise ValueError("Accepted response does not cover exactly the scheduled questions")
    configuration = _read(attempt_dir / "run.json").get("configuration")
    expected_policy = {"max_physical_attempts_per_logical_request": 1}
    if not isinstance(configuration, Mapping) or any(configuration.get(key) != value for key, value in {"provider": "nous", "model": PROVIDER["model"], "reasoning": "max", "batch_size": len(row["question_ids"]), "retry_policy": {"batch_attempts": 1}, "artifact_id": row["story_id"], "bundle_id": "prose.short_story", "question_ids": row["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True}.items()) or not isinstance(configuration.get("nous_transport_policy"), Mapping) or configuration["nous_transport_policy"].get("max_physical_attempts_per_logical_request") != 1:
        raise ValueError("Accepted run configuration drifts from the frozen cap-one request")
    provider = checkpoint.get("provider")
    if not isinstance(provider, Mapping): raise ValueError("Accepted checkpoint lacks a provider receipt")
    try: hbq_runner._validate_provider_artifacts(attempt_dir, checkpoint)
    except Exception as error: raise ValueError("Accepted provider artifacts are invalid") from error
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping): raise ValueError("Accepted provider artifact bindings are missing")
    request_ref, proof_ref = (artifacts.get(key, {}).get("path") if isinstance(artifacts.get(key), Mapping) else None for key in ("judge_request", "serialization_proof"))
    if not isinstance(request_ref, str) or not isinstance(proof_ref, str): raise ValueError("Accepted raw request or proof is unbound")
    request, proof = attempt_dir / request_ref, attempt_dir / proof_ref
    v9, _, bridge = _bridge(); v8 = v9.parent_v8(); evidence_root = attempt_dir / artifacts["evidence_tree"]["path"]; judge, prove = v8.v7_verifier()._judge_leaf(evidence_root, proof)
    for leaf in (judge, prove): bridge.validate_evidence(leaf)
    if not getattr(bridge.serialization_proof_status((attempt_dir / artifacts["evidence_tree"]["path"]), str(proof), expected_sha256=_sha(proof.read_bytes())), "valid", False): raise ValueError("Accepted serialization proof is invalid")
    judge_events = _events(judge / "events.jsonl"); http = [event.get("data") for event in judge_events if event.get("event_type") == "http_attempt"]
    prove_events = _events(prove / "events.jsonl")
    if len(http) != 1 or not isinstance(http[0], Mapping) or not 200 <= int(http[0].get("status", 0)) < 300 or any(event.get("event_type") == "http_attempt" for event in prove_events): raise ValueError("Accepted evidence is not exactly one 2xx Judge attempt")
    _verify_judge_request(bridge, judge, judge_events, request, http[0])
    request_value = _read(request); messages = request_value.get("messages")
    if not isinstance(messages, list) or len(messages) != 2 or messages[1].get("content") != prompt_bytes.decode("utf-8") or checkpoint.get("prompt_sha256") != _sha(prompt_bytes) or checkpoint.get("base_prompt_sha256") != _sha(prompt_bytes):
        raise ValueError("Accepted prompt/checkpoint/request replay drifted")
    receipt = _read(judge / "receipt.json"); session_id, logical_id = receipt.get("run_id"), http[0].get("logical_request_id")
    receipt_id = f"nous:{provider.get('evidence_sha256')}:{provider.get('serialization_proof_sha256')}"
    if receipt.get("status") != "success" or any(not isinstance(value, str) or not value for value in (session_id, logical_id, receipt_id)):
        raise ValueError("Accepted provider identities are malformed")
    normalized_ids: set[str] = set()
    for checkpoint in (attempt_dir / "responses").glob("batch-*.json"):
        value = _read(checkpoint)
        if isinstance(value.get("normalization_audit"), list):
            normalized_ids.update(str(item.get("question_id")) for item in value["normalization_audit"] if isinstance(item, Mapping))
    records = []
    for item in verdicts:
        records.append({"status": "accepted", "story_id": row["story_id"], "condition_id": row["condition_id"], "polarity": row["polarity"], "question_id": item["question_id"], "verdict": item["verdict"], "confidence": item["confidence"], "normalized_evidence": item["question_id"] in normalized_ids})
    return {"status": "accepted", "static_binding": binding["static_sha256"], "prompt": _hash_binding(fingerprint(prompt_path)), "request": _hash_binding(fingerprint(request)), "accepted_identities": {"receipt_id": receipt_id, "session_id": session_id, "logical_request_id": logical_id}, "run": fingerprint(attempt_dir / "run.json"), "checkpoint": fingerprint(checkpoints[0]), "verdicts": fingerprint(verdict_path), "records": records}


def _assert_identities(histories: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    accepted = {key: [] for key in ("receipt_id", "session_id", "logical_request_id")}; failed = {key: [] for key in ("session_id", "logical_request_id", "receipt_sha256", "serialization_proof_sha256")}
    for history in histories.values():
        for result in history:
            collection = accepted if result.get("status") == "accepted" else failed if result.get("status") == "eligible_524" else None
            identities = result.get("accepted_identities") if collection is accepted else result.get("failed_identities") if collection is failed else None
            if collection is None: continue
            if not isinstance(identities, Mapping): raise ValueError("Terminal provider result lacks typed identities")
            for key in collection:
                value = identities.get(key)
                if not isinstance(value, str) or not value: raise ValueError("Provider identity is malformed")
                collection[key].append(value)
    if any(len(values) != len(set(values)) for values in (*accepted.values(), *failed.values())):
        raise ValueError("Provider identity was reused")
    if set(accepted["session_id"]) & set(failed["session_id"]) or set(accepted["logical_request_id"]) & set(failed["logical_request_id"]):
        raise ValueError("Accepted provider identity collides with failed attempt")


def _pause(work: Path, reason: str, *, now: datetime) -> None:
    value: dict[str, Any] = {"study_id": study.HERE.name, "reason": reason, "at": now.isoformat()}
    if reason == "six-eligible-524":
        value["resume_after"] = (now + timedelta(minutes=study.AVAILABILITY["after_three_consecutive_minutes"])).isoformat()
    _immutable(work / "pauses" / f"{len(list((work / 'pauses').glob('*.json'))) + 1:04d}-{reason}.json", value)


def _globally_paused(work: Path, now: datetime) -> bool:
    pauses = sorted((work / "pauses").glob("*-six-eligible-524.json"))
    if not pauses:
        return False
    value = _read(pauses[-1])
    resume_after = value.get("resume_after")
    if not isinstance(resume_after, str):
        raise ValueError("Global 524 pause is malformed")
    return now < datetime.fromisoformat(resume_after)


def _assert_fresh_zero_cost(frozen: Mapping[str, Any]) -> None:
    proof = frozen.get("zero_cost_proof")
    if not isinstance(proof, Mapping) or not isinstance(proof.get("path"), str) or not isinstance(proof.get("freshness_checked_at"), str):
        raise ValueError("Live zero-cost proof is malformed")
    helper = _v9()
    live = helper.parent_v8()._zero_cost_proof(Path(str(proof["path"])))
    if proof != {**live, "freshness_checked_at": proof["freshness_checked_at"]}:
        raise ValueError("Live zero-cost proof drifted")
    helper.parent_v8().assert_fresh_at(proof, datetime.now(timezone.utc).isoformat())


def _orphan_intents(work: Path) -> bool:
    pending: set[tuple[str, int]] = set()
    for row in _records(work):
        key = (str(row.get("call_id")), int(row.get("attempt", 0)))
        if row.get("kind") == "intent": pending.add(key)
        elif row.get("kind") == "result": pending.discard(key)
    return bool(pending)


def _claim(work: Path) -> Path:
    path = work / "execution-claim.json"
    value = {"format_version": 1, "study_id": study.HERE.name, "kind": "O_EXCL_private_cap_one_execution", "pid": os.getpid(), "frozen": fingerprint(work / FROZEN_NAME)}
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"); out.flush(); os.fsync(out.fileno())
    except FileExistsError as error:
        raise ValueError("O_EXCL execution claim already exists; recovery is fail-closed") from error
    return path


def execute(work: Path, *, timeout: float = 600.0) -> int:
    """Run pending calls once. A paused/global-stop root never contacts Nous."""
    frozen = load_frozen(work)
    _assert_fresh_zero_cost(frozen)
    if any((work / "pauses").glob("*-global-stop.json")):
        raise ValueError("Global stop is immutable and blocks execution")
    histories = _histories(work)
    _assert_identities(histories)
    now = datetime.now(timezone.utc)
    if _globally_paused(work, now):
        return 0
    claim = _claim(work)
    sent = 0
    consecutive = _trailing_eligible_524(work)
    try:
      for scheduled in frozen["schedule"]:
        call_id = scheduled["call_id"]
        history = histories.get(call_id, [])
        if any(item["status"] in {"accepted", "quarantined", "global_stop"} for item in history):
            continue
        eligible = sum(item["status"] == "eligible_524" for item in history)
        if eligible >= study.AVAILABILITY["eligible_524_attempt_ceiling"]:
            continue
        if history:
            last = datetime.fromisoformat(str(history[-1]["at"]))
            cooldown = study.availability_policy(consecutive, eligible_524_for_unit=eligible)["minutes"]
            if cooldown is None or now < last + timedelta(minutes=int(cooldown)):
                continue
        inputs = _read(work / "private-inputs.json")[scheduled["story_id"]]
        registry = work / "projections" / f"{scheduled['polarity']}.registry.json"
        effective_ids = _effective_question_ids(scheduled, inputs, registry)
        execution_row = {**scheduled, "frozen_question_ids": list(scheduled["question_ids"]), "question_ids": effective_ids}
        binding = _binding(work, execution_row, effective_question_ids=effective_ids)
        if history and history[-1].get("static_binding") != binding["static_sha256"]:
            raise ValueError("Retry request or prompt binding drifted; no resend is safe")
        attempt = len(history) + 1
        attempt_dir = work / "runs" / call_id / f"attempt-{attempt:02d}"
        _append(work, {"kind": "intent", "call_id": call_id, "attempt": attempt, "at": now.isoformat(), "binding": binding})
        try:
            response = run_judge(artifact_path=inputs["artifact"], context_paths=[inputs["prompt"]], task_contract_path=inputs["task_contract"], bundle_id="prose.short_story", provider="nous", model="stealth/ox-alpha", reasoning="max", output_dir=attempt_dir, registry=registry, bundles=bundles_path(), question_ids=effective_ids, batch_size=len(effective_ids), batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=scheduled["story_id"], strict_ai=False, allow_unattested_reasoning=True, resume=False, max_physical_http_attempts_per_logical_request=1)
            result = _accepted(attempt_dir, execution_row, binding, response, inputs, registry)
            consecutive = 0
        except Exception as error:
            status = _v9_error_status(error)
            if status == "candidate_524":
                try: result = _eligible_524(attempt_dir); result["static_binding"] = binding["static_sha256"]; status = "eligible_524"
                except Exception as verification: result = {"status": "quarantined", "static_binding": binding["static_sha256"], "error": {"class": type(error).__name__, "message": str(error)[:800]}, "verification": {"class": type(verification).__name__, "message": str(verification)[:800]}}; status = "quarantined"
            else:
                result = {"status": status, "static_binding": binding["static_sha256"], "error": {"class": type(error).__name__, "message": str(error)[:800]}}
        if history and result.get("status") in {"accepted", "eligible_524"} and (result.get("prompt") != history[-1].get("prompt") or result.get("request") != history[-1].get("request")):
            result = {"status": "quarantined", "static_binding": binding["static_sha256"], "reason": "retry_request_or_prompt_hash_drift"}; consecutive = 0
        if result.get("status") == "eligible_524":
            consecutive += 1
        else:
            consecutive = 0
        if result.get("status") == "global_stop":
            _pause(work, "global-stop", now=datetime.now(timezone.utc))
        result["at"] = datetime.now(timezone.utc).isoformat()
        _append(work, {"kind": "result", "call_id": call_id, "attempt": attempt, "binding": binding, "result": result})
        _assert_identities(_histories(work))
        sent += 1
        if result["status"] == "global_stop":
            if not any((work / "pauses").glob("*-global-stop.json")):
                _pause(work, "global-stop", now=datetime.now(timezone.utc))
            break
        if consecutive >= study.AVAILABILITY["pause_after_consecutive_eligible_524"]:
            _pause(work, "six-eligible-524", now=datetime.now(timezone.utc))
            break
    finally:
        if not _orphan_intents(work): claim.unlink(missing_ok=True)
    return sent


def progress(work: Path) -> dict[str, Any]:
    """Return a non-final, versioned progress view; it never mutates evidence."""
    frozen = load_frozen(work)
    histories = _histories(work)
    _assert_identities(histories)
    final = {call_id: rows[-1] for call_id, rows in histories.items() if rows}
    rows = [record for item in final.values() if item["status"] == "accepted" for record in item.get("records", [])]
    analysis = study.analyze(rows + [{"status": item["status"]} for item in final.values() if item["status"] != "accepted"])
    return {"format_version": 1, "study_id": frozen["study_id"], "kind": "successor_progress_snapshot", "frozen": fingerprint(work / FROZEN_NAME), "attempt_count": len(_records(work)) // 2, "logical_calls_with_result": len(final), "scheduled_calls": len(frozen["schedule"]), "analysis": analysis, "terminal_status_counts": {status: sum(item["status"] == status for item in final.values()) for status in ("accepted", "eligible_524", "quarantined", "global_stop")}, "confirmation_available": study.confirmation_available(analysis), "production_recommendation": None}


def settle(work: Path) -> dict[str, Any]:
    """Seal only a completely terminal successor screen."""
    payload = progress(work)
    terminal = payload["terminal_status_counts"]
    histories = _histories(work)
    exhausted = sum(bool(history) and history[-1].get("status") == "eligible_524" and sum(result.get("status") == "eligible_524" for result in history) >= study.AVAILABILITY["eligible_524_attempt_ceiling"] for history in histories.values())
    stopped = bool(terminal["global_stop"])
    unresolved = payload["scheduled_calls"] - payload["logical_calls_with_result"]
    if (not stopped and (unresolved or terminal["eligible_524"] != exhausted)):
        raise ValueError("Cannot settle while calls are unresolved or retry-eligible")
    payload = {**payload, "kind": "successor_specific_settlement", "exhausted_eligible_524_calls": exhausted, "unsent_calls_after_global_stop": unresolved if stopped else 0, "status": "stopped" if stopped else "terminal", "confirmation_available": False if stopped or exhausted else payload["confirmation_available"]}
    _immutable(work / "settlement.json", payload)
    return payload
