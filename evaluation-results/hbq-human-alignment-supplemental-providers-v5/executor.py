#!/usr/bin/env python3
"""Execute the v5 Nous batch-8 cells once each, with no in-place retry path."""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from hbqrs import runner as runner_module
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge

HERE = Path(__file__).resolve().parent


def _study() -> Any:
    spec = importlib.util.spec_from_file_location("hanna_supplemental_v5_study", HERE / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("v5 study helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


study = _study()


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(study.canonical(dict(value)))


def _cell_root(work: Path, cell_id: str) -> Path:
    return work / "cells" / cell_id


def _route_proof_record(cell: Mapping[str, Any], route_proof: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": study.STUDY_ID,
        "kind": "current_zero_new_spend_existing_credit_tool_free_route_proof",
        "cell_id": cell["cell_id"],
        "route": study.validate_route_proof(route_proof),
        "provider_calls_made": 0,
        "process_launches": 0,
    }


def _prepared_records(cell: Mapping[str, Any], route_proof: Mapping[str, Any], runtime: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    schema = runner_module._json_bytes(runner_module._response_schema())
    schedule = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "exact_v4_first_eight_question_schedule", "cell": dict(cell)}
    inputs = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "immutable_input_bindings", "inputs": cell["inputs"], "input_folder": cell["input_folder"]}
    disclosure = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "local_first_exact_outbound_disclosure",
        "cell_id": cell["cell_id"], "destination": "nous_tool_free_hardened_bridge",
        "provider": "nous", "model": study.MODEL, "reasoning": "max", "tools_enabled": False,
        "source_sha256": cell["inputs"]["source.md"]["sha256"], "prompt_sha256": cell["inputs"]["prompt.md"]["sha256"],
        "task_contract_sha256": cell["inputs"]["task-contract.json"]["sha256"], "question_ids": cell["question_ids"],
        "response_schema_sha256": study.sha_bytes(schema), "provider_calls_made": 0, "process_launches": 0,
    }
    authorization = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "authorized_remote_disclosure_acknowledgement",
        "cell_id": cell["cell_id"], "acknowledgement_sha256": study.ACKNOWLEDGEMENT_SHA256,
        "disclosure_sha256": study.sha_bytes(study.canonical(disclosure)),
    }
    proof = _route_proof_record(cell, route_proof)
    scope_override = study.scope_compatibility_override(cell)
    prepared = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "nous_v5_preparation", "cell_id": cell["cell_id"],
        "schedule_sha256": study.sha_bytes(study.canonical(schedule)), "inputs_sha256": study.sha_bytes(study.canonical(inputs)),
        "runtime_sha256": study.sha_bytes(study.canonical(dict(runtime))), "disclosure_sha256": study.sha_bytes(study.canonical(disclosure)),
        "authorization_sha256": study.sha_bytes(study.canonical(authorization)), "route_proof_sha256": study.sha_bytes(study.canonical(proof)),
        "response_schema_sha256": study.sha_bytes(schema), "scope_compatibility_override_sha256": study.sha_bytes(study.canonical(scope_override)), "provider_calls_made": 0, "process_launches": 0,
        "execution_status": "PREPARED_NO_CONTACT",
    }
    return {
        "prepared.json": prepared, "schedule.json": schedule, "inputs.json": inputs, "runtime.json": dict(runtime),
        "disclosure.json": disclosure, "authorization-acknowledgement.json": authorization, "zero-new-spend-route-proof.json": proof, "scope-compatibility-override.json": scope_override,
    }


def prepare(work_dir: Path, *, v4_work_dir: Path, route_proof: Mapping[str, Any], acknowledgement_sha256: str = study.ACKNOWLEDGEMENT_SHA256) -> dict[str, Any]:
    if acknowledgement_sha256 != study.ACKNOWLEDGEMENT_SHA256:
        raise ValueError("v5 requires the acknowledged remote-disclosure digest")
    v4_frozen, cells = study.load_v4_cells(v4_work_dir)
    route = study.validate_route_proof(route_proof)
    runtime = study.runtime_bindings()
    study.fresh_root(work_dir)
    root = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "v5_execution_freeze", "v4_frozen": study.fingerprint(v4_work_dir / "frozen-transport-contract.json"),
        "v4_runtime": v4_frozen.get("runtime"), "runtime": runtime, "route_proof_sha256": study.sha_bytes(study.canonical(route)),
        "cells": cells, "provider_calls_made": 0, "process_launches": 0,
        "policy": {"workers": 1, "batch_size": 8, "batch_attempts": 1, "timeout_seconds": 600, "maximum_completion_seconds_exclusive": 100, "tools_enabled": False},
    }
    study.immutable_json(work_dir / "frozen-v5.json", root)
    for cell in cells:
        cell_root = _cell_root(work_dir, str(cell["cell_id"]))
        cell_root.mkdir(parents=True, exist_ok=False)
        for name, value in _prepared_records(cell, route, runtime).items():
            study.immutable_json(cell_root / name, value)
    return root


def _load_frozen(work: Path) -> dict[str, Any]:
    frozen = study.read_json(work / "frozen-v5.json")
    if frozen.get("study_id") != study.STUDY_ID or frozen.get("provider_calls_made") != 0 or frozen.get("process_launches") != 0:
        raise ValueError("v5 root is not a provider-free preparation")
    if frozen.get("runtime") != study.runtime_bindings():
        raise ValueError("v5 runtime changed; prepare a fresh root")
    cells = frozen.get("cells")
    if not isinstance(cells, list) or len(cells) != 3:
        raise ValueError("v5 root lacks its exact three-cell schedule")
    return frozen


def _prepared_root(cell_root: Path, cell: Mapping[str, Any], *, allow_native_run: bool = False, allowed_extra: frozenset[str] = frozenset()) -> dict[str, Any]:
    study.plain_entry(cell_root, directory=True)
    children = {child.name: child for child in cell_root.iterdir()}
    expected = set(study.PREPARED_FILES) | ({"native-run"} if allow_native_run else set()) | set(allowed_extra)
    if set(children) != expected:
        raise ValueError("v5 prepared root has missing, extra, or unsafe artifacts")
    for name, path in children.items():
        study.plain_entry(path, directory=name == "native-run")
    records = {name: study.read_json(cell_root / name) for name in study.PREPARED_FILES}
    _prepared, schedule, inputs, runtime, disclosure, authorization, proof, scope_override = (records[name] for name in ("prepared.json", "schedule.json", "inputs.json", "runtime.json", "disclosure.json", "authorization-acknowledgement.json", "zero-new-spend-route-proof.json", "scope-compatibility-override.json"))
    if runtime != study.runtime_bindings() or schedule.get("cell") != dict(cell) or inputs.get("inputs") != cell.get("inputs"):
        raise ValueError("v5 prepared schedule, inputs, or runtime drifted")
    if authorization.get("acknowledgement_sha256") != study.ACKNOWLEDGEMENT_SHA256 or authorization.get("disclosure_sha256") != study.sha_bytes(study.canonical(disclosure)):
        raise ValueError("v5 acknowledgement drifted")
    if proof.get("route") != study.validate_route_proof(proof.get("route", {})) or disclosure.get("question_ids") != cell.get("question_ids"):
        raise ValueError("v5 disclosure or route proof drifted")
    if scope_override != study.scope_compatibility_override(cell):
        raise ValueError("v5 reviewed scope compatibility override drifted")
    expected = _prepared_records(cell, proof["route"], runtime)
    if any(records[name] != expected[name] for name in study.PREPARED_FILES):
        raise ValueError("v5 prepared commitment drifted")
    folder = Path(str(cell["input_folder"]))
    actual = {name: study.fingerprint(folder / name) for name in ("source.md", "prompt.md", "task-contract.json")}
    if actual != cell.get("inputs"):
        raise ValueError("v5 source input bytes drifted")
    return records


def _native_precontact_dir(native_root: Path) -> tuple[bytes, bytes]:
    study.plain_entry(native_root, directory=True)
    children = {child.name: child for child in native_root.iterdir()}
    if set(children) != {"run.json", "response.schema.json", "responses"}:
        raise ValueError("v5 runner precontact inventory drifted")
    for name, path in children.items():
        study.plain_entry(path, directory=name == "responses")
    responses = native_root / "responses"
    if {path.name for path in responses.iterdir()} != {"batch-0001.prompt.txt.gz"}:
        raise ValueError("v5 runner precontact responses inventory drifted")
    prompt_path = responses / "batch-0001.prompt.txt.gz"
    study.plain_entry(prompt_path)
    try:
        prompt_bytes = gzip.decompress(prompt_path.read_bytes())
    except (OSError, EOFError) as error:
        raise ValueError("v5 runner precontact prompt checkpoint is unreadable") from error
    return prompt_bytes, study.stable_bytes(native_root / "response.schema.json")


def _validate_callback_context(context: Mapping[str, Any], native_root: Path, cell: Mapping[str, Any], prepared: Mapping[str, Any], checkpoint_prompt: bytes, schema_bytes: bytes) -> dict[str, Any]:
    provider = context.get("provider", {})
    batch = context.get("batch", {})
    attempt = context.get("attempt", {})
    prompt = context.get("prompt", {})
    schema = context.get("response_schema", {})
    if provider != {"provider": "nous", "model": study.MODEL, "reasoning": "max", "endpoint": None} or batch != {"number": 1, "question_ids": cell["question_ids"]} or attempt != {"number": 1, "batch_attempts": 1}:
        raise ValueError("v5 runner callback settings drifted")
    if not isinstance(prompt.get("text"), str) or prompt.get("text", "").encode("utf-8") != checkpoint_prompt or prompt.get("sha256") != study.sha_bytes(checkpoint_prompt):
        raise ValueError("v5 runner callback prompt is malformed")
    if schema.get("sha256") != prepared["response_schema_sha256"] or schema.get("text", "").encode("utf-8") != schema_bytes or schema_bytes != runner_module._json_bytes(runner_module._response_schema()):
        raise ValueError("v5 runner callback schema drifted")
    run = study.read_json(native_root / "run.json", canonical_required=False)
    if run.get("config_sha256") != context.get("run", {}).get("config_sha256"):
        raise ValueError("v5 runner manifest is not bound to callback")
    return {"prompt": {key: prompt[key] for key in ("bytes", "sha256", "base_prompt_sha256")}, "response_schema": {key: schema[key] for key in ("bytes", "sha256")}, "run": dict(context["run"])}


def _sealed_session_id(evidence_root: Path) -> str:
    bridge_path = Path.home() / ".codex" / "tools" / "nous_codex_bridge.py"
    spec = importlib.util.spec_from_file_location("hanna_supplemental_v5_bridge_validator", bridge_path)
    if spec is None or spec.loader is None:
        raise ValueError("v5 canonical bridge validator is unavailable")
    bridge = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = bridge
    try:
        spec.loader.exec_module(bridge)
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
    candidates = [path for path in evidence_root.iterdir() if path.is_dir() and (path / "manifest.json").is_file() and (path / "receipt.json").is_file()]
    records: list[tuple[Path, Mapping[str, Any], Mapping[str, Any]]] = []
    for candidate in candidates:
        validated = bridge.validate_evidence(candidate)
        manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        receipt = json.loads((candidate / "receipt.json").read_text(encoding="utf-8"))
        if not isinstance(validated, Mapping) or validated.get("valid") is not True or not isinstance(manifest, Mapping) or not isinstance(receipt, Mapping):
            raise ValueError("v5 sealed evidence is malformed")
        records.append((candidate, manifest, receipt))
    judges = [(manifest, receipt) for _, manifest, receipt in records if manifest.get("mode") == "judge"]
    proofs = [(manifest, receipt) for _, manifest, receipt in records if manifest.get("mode") == "serialization-proof"]
    if len(judges) != 1 or len(proofs) != 1 or len(records) != 2:
        raise ValueError("v5 sealed evidence does not have one judge and one serialization session")
    manifest, receipt = judges[0]
    session_id = receipt.get("run_id") if manifest.get("run_id") == receipt.get("run_id") else None
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("v5 sealed evidence lacks its native session identity")
    return session_id


def _sealed_elapsed_seconds(evidence_root: Path) -> float:
    """Derive elapsed wall time from the two sealed bridge session timestamps."""
    stamps: list[datetime] = []
    for candidate in evidence_root.iterdir():
        if not candidate.is_dir() or not (candidate / "manifest.json").is_file() or not (candidate / "receipt.json").is_file():
            continue
        manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
        receipt = json.loads((candidate / "receipt.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, Mapping) or not isinstance(receipt, Mapping):
            raise TypeError("v5 sealed evidence timestamps are malformed")
        for value in (manifest.get("created_at"), receipt.get("sealed_at")):
            if not isinstance(value, str):
                raise TypeError("v5 sealed evidence lacks a timestamp")
            stamps.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
    if len(stamps) != 4:
        raise ValueError("v5 sealed evidence does not have the required timestamp geometry")
    elapsed = (max(stamps) - min(stamps)).total_seconds()
    if not 0 < elapsed < 100:
        raise ValueError("v5 sealed evidence exceeds the frozen 100-second bound")
    return elapsed


def _completion_payload(cell_root: Path, native_root: Path, cell: Mapping[str, Any], started: float | None, sealed_evidence_validator: Callable[[Path], str], *, elapsed_seconds: float | None = None) -> dict[str, Any]:
    checkpoint = study.read_json(native_root / "responses" / "batch-0001.json", canonical_required=False)
    provider = checkpoint.get("provider")
    if not isinstance(provider, Mapping) or provider.get("requested") != {"model": study.MODEL, "reasoning_effort": "max"} or provider.get("logical_provider_request_count") != 1 or provider.get("physical_http_attempt_count") != 1 or provider.get("recovered_request_count") != 0 or provider.get("tool_free") is not True:
        raise ValueError("v5 native Nous receipt does not prove exactly one tool-free HTTP attempt")
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping):
        raise TypeError("v5 native Nous receipt lacks sealed artifacts")
    required = {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}
    if set(artifacts) != required:
        raise ValueError("v5 native Nous artifact envelope is incomplete")
    for name, record in artifacts.items():
        if not isinstance(record, Mapping) or not isinstance(record.get("sha256"), str):
            raise TypeError(f"v5 native {name} envelope is malformed")
    try:
        runner_module._validate_provider_artifacts(native_root, checkpoint)
        evidence_path = native_root / str(artifacts["evidence_tree"]["path"])
        evidence_path.resolve().relative_to(native_root.resolve())
    except Exception as error:
        raise ValueError("v5 native artifact envelope is not replayable") from error
    session_id = sealed_evidence_validator(evidence_path)
    elapsed = elapsed_seconds if elapsed_seconds is not None else (time.monotonic() - started if started is not None else None)
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not 0 < elapsed < 100:
        raise ValueError("v5 completion exceeded the frozen 100-second bound")
    result = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "provisional_breadth_only_completion",
        "cell_id": cell["cell_id"], "elapsed_seconds": elapsed, "confirmed_process_launches": 1, "confirmed_provider_calls": 1,
        "native_contact_identity": {"provider": "nous", "model": study.MODEL, "reasoning": "max", "tools_enabled": False, "session_id": session_id},
        "checkpoint": study.fingerprint(native_root / "responses" / "batch-0001.json"), "provider": dict(provider),
        "launch_intent_sha256": study.sha(cell_root / "launch-intent.json"), "classification": "PROVISIONAL_BREADTH_ONLY",
    }
    return result


def _failed_contact_evidence(cell_root: Path, native_root: Path, cell: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> dict[str, Any] | None:
    responses = native_root / "responses"
    if not responses.is_dir():
        return None
    evidence_roots = sorted(path for path in responses.glob("batch-0001.attempt-0001.nous.evidence") if path.is_dir())
    if not evidence_roots:
        return None
    if len(evidence_roots) != 1:
        raise ValueError("v5 failure evidence has an ambiguous native attempt root")
    evidence_root = evidence_roots[0]
    study.plain_entry(evidence_root, directory=True)
    session_id = sealed_evidence_validator(evidence_root)
    judges: list[Path] = []
    for candidate in evidence_root.iterdir():
        if not candidate.is_dir() or not (candidate / "manifest.json").is_file() or not (candidate / "receipt.json").is_file():
            continue
        manifest = json.loads(study.stable_bytes(candidate / "manifest.json").decode("utf-8"))
        if isinstance(manifest, Mapping) and manifest.get("mode") == "judge":
            judges.append(candidate)
    if len(judges) != 1:
        raise ValueError("v5 failure evidence lacks one sealed judge session")
    judge = judges[0]
    manifest = json.loads(study.stable_bytes(judge / "manifest.json").decode("utf-8"))
    receipt = json.loads(study.stable_bytes(judge / "receipt.json").decode("utf-8"))
    if not isinstance(manifest, Mapping) or not isinstance(receipt, Mapping) or manifest.get("requested_provider") != "nous" or manifest.get("requested_model") != study.MODEL or manifest.get("requested_reasoning_effort") != "max" or receipt.get("run_id") != session_id or receipt.get("status") != "failure":
        raise ValueError("v5 failure evidence judge identity drifted")
    events_path = judge / "events.jsonl"
    events = [json.loads(line) for line in study.stable_bytes(events_path).decode("utf-8").splitlines()]
    attempts = [event.get("data") for event in events if isinstance(event, Mapping) and event.get("event_type") == "http_attempt"]
    boundaries = [event.get("data") for event in events if isinstance(event, Mapping) and event.get("event_type") == "judge_boundary"]
    if len(attempts) != 1 or len(boundaries) != 1 or not isinstance(attempts[0], Mapping) or not isinstance(boundaries[0], Mapping):
        raise ValueError("v5 failure evidence does not prove exactly one judge HTTP attempt")
    attempt = attempts[0]
    transport = boundaries[0].get("transport_policy")
    if attempt.get("method") != "POST" or not isinstance(attempt.get("status"), int) or 200 <= attempt["status"] < 300 or not isinstance(attempt.get("logical_request_id"), str) or not isinstance(transport, Mapping) or transport.get("logical_requests_per_attempt") != 1 or transport.get("max_physical_attempts_per_logical_request") != 1:
        raise ValueError("v5 failure evidence contact accounting drifted")
    intent = study.read_json(cell_root / "launch-intent.json")
    callback = intent.get("callback")
    run = study.read_json(native_root / "run.json", canonical_required=False)
    request_path = responses / "batch-0001.attempt-0001.nous.request.json"
    request = json.loads(study.stable_bytes(request_path).decode("utf-8"))
    prompt_path = responses / "batch-0001.prompt.txt.gz"
    try:
        prompt_bytes = gzip.decompress(study.stable_bytes(prompt_path))
    except (OSError, EOFError) as error:
        raise ValueError("v5 failure evidence prompt is unreadable") from error
    if not isinstance(callback, Mapping) or not isinstance(run, Mapping) or not isinstance(request, Mapping):
        raise TypeError("v5 failure evidence lacks request bindings")
    callback_prompt = callback.get("prompt")
    callback_run = callback.get("run")
    configuration = run.get("configuration")
    messages = request.get("messages")
    user_message = messages[1] if isinstance(messages, list) and len(messages) == 2 else None
    if not isinstance(callback_prompt, Mapping) or not isinstance(callback_run, Mapping) or not isinstance(configuration, Mapping) or not isinstance(user_message, Mapping) or user_message.get("role") != "user" or not isinstance(user_message.get("content"), str):
        raise TypeError("v5 failure evidence request geometry is malformed")
    prompt_sha = study.sha_bytes(prompt_bytes)
    if callback_prompt.get("sha256") != prompt_sha or callback_prompt.get("bytes") != len(prompt_bytes) or user_message["content"].encode("utf-8") != prompt_bytes or run.get("config_sha256") != callback_run.get("config_sha256") or run.get("run_id") != callback_run.get("run_id"):
        raise ValueError("v5 failure evidence prompt or run binding drifted")
    if configuration.get("artifact_id") != cell.get("item_id") or configuration.get("provider") != "nous" or configuration.get("model") != study.MODEL or configuration.get("reasoning") != "max" or configuration.get("question_ids") != cell.get("question_ids"):
        raise ValueError("v5 failure evidence cell configuration drifted")
    artifact = configuration.get("artifact")
    contexts = configuration.get("contexts")
    if not isinstance(artifact, Mapping) or artifact.get("sha256") != cell["inputs"]["source.md"]["sha256"] or not isinstance(contexts, list) or len(contexts) != 1 or not isinstance(contexts[0], Mapping) or contexts[0].get("sha256") != cell["inputs"]["prompt.md"]["sha256"]:
        raise ValueError("v5 failure evidence immutable inputs drifted")
    boundary = boundaries[0]
    request_sha = study.sha_bytes(json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    if boundary.get("request_sha256") != request_sha or request.get("model") != study.MODEL or request.get("reasoning_effort") != "max" or request.get("max_physical_http_attempts_per_logical_request") != 1:
        raise ValueError("v5 failure evidence outbound request binding drifted")
    return {
        "confirmed_process_launches": 1,
        "confirmed_provider_calls": 1,
        "failure_contact_evidence": {
            "judge_session_id": session_id,
            "judge_events": study.fingerprint(events_path),
            "physical_http_attempt_count": 1,
            "recovered_request_count": 0,
        },
    }


def _receipt_session(cell_root: Path, native_root: Path, cell: Mapping[str, Any], receipt_name: str, sealed_evidence_validator: Callable[[Path], str]) -> str:
    receipt = study.read_json(cell_root / receipt_name)
    elapsed = receipt.get("elapsed_seconds")
    expected = _completion_payload(cell_root, native_root, cell, None, sealed_evidence_validator, elapsed_seconds=elapsed)
    if receipt_name == "completion-receipt.json":
        if receipt != expected:
            raise ValueError("v5 completed receipt is malformed or drifted")
    else:
        terminal = cell_root / "terminal-reconcile-required.json"
        expected["kind"] = "reconciled_provisional_breadth_only_completion"
        expected["reconciliation"] = {
            "kind": "post_intent_read_only_replay",
            "terminal_reconcile_required": study.fingerprint(terminal),
        }
        if receipt != expected:
            raise ValueError("v5 reconciled completion is malformed or drifted")
    session = expected["native_contact_identity"]["session_id"]
    if not isinstance(session, str):
        raise TypeError("v5 completed receipt lacks a session identity")
    return session


def _predecessors(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    cells = frozen.get("cells")
    if not isinstance(cells, list):
        raise TypeError("v5 frozen schedule is malformed")
    for index, candidate in enumerate(cells):
        if candidate.get("cell_id") == cell.get("cell_id"):
            return cells[:index]
    raise ValueError("v5 cell is outside the frozen schedule")


def _snapshot_is_ordered(work_dir: Path, snapshot: Any, frozen: Mapping[str, Any], cell: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> bool:
    predecessors = _predecessors(frozen, cell)
    if snapshot is None:
        return not predecessors
    if not isinstance(snapshot, Mapping) or set(snapshot) != {"predecessors"}:
        return False
    records = snapshot.get("predecessors")
    if not isinstance(records, list) or len(records) != len(predecessors):
        return False
    for record, predecessor in zip(records, predecessors, strict=True):
        receipt = record.get("completion_receipt") if isinstance(record, Mapping) else None
        if not isinstance(receipt, Mapping) or set(record) != {"cell_id", "state", "completion_receipt"}:
            return False
        if record.get("cell_id") != predecessor.get("cell_id") or record.get("state") not in {"completed", "reconciled"}:
            return False
        expected_receipt = "completion-receipt.json" if record["state"] == "completed" else "reconciled-completion.json"
        if receipt.get("name") != expected_receipt or not isinstance(receipt.get("bytes"), int) or not isinstance(receipt.get("sha256"), str) or len(receipt["sha256"]) != 64:
            return False
        predecessor_root = _cell_root(work_dir, str(predecessor["cell_id"]))
        try:
            if study.fingerprint(predecessor_root / expected_receipt) != dict(receipt):
                return False
            state, _session = _terminal_state(predecessor_root, predecessor_root / "native-run", predecessor, work_dir, frozen, sealed_evidence_validator)
        except (OSError, TypeError, ValueError):
            return False
        if state != record["state"]:
            return False
    return True


def _predecessor_snapshot(work_dir: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for predecessor in _predecessors(frozen, cell):
        predecessor_root = _cell_root(work_dir, str(predecessor["cell_id"]))
        state, _session = _terminal_state(predecessor_root, predecessor_root / "native-run", predecessor, work_dir, frozen, sealed_evidence_validator)
        if state not in {"completed", "reconciled"}:
            raise ValueError("v5 later-cell launch requires every predecessor to be durably completed")
        receipt_name = "completion-receipt.json" if state == "completed" else "reconciled-completion.json"
        records.append({"cell_id": predecessor["cell_id"], "state": state, "completion_receipt": study.fingerprint(predecessor_root / receipt_name)})
    return {"predecessors": records}


def _terminal_accounting_view(cell_root: Path, native_root: Path, cell: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> dict[str, Any]:
    terminal_path = cell_root / "terminal-reconcile-required.json"
    record = study.read_json(terminal_path)
    failed = _failed_contact_evidence(cell_root, native_root, cell, sealed_evidence_validator)
    if failed is None:
        if record.get("confirmed_process_launches") != 0 or record.get("confirmed_provider_calls") != 0 or "failure_contact_evidence" in record:
            raise ValueError("v5 reconcile terminal contact accounting is unsupported without sealed failure evidence")
        return {
            "kind": "persisted_terminal_contact_accounting",
            "source_terminal": study.fingerprint(terminal_path),
            "confirmed_process_launches": record["confirmed_process_launches"],
            "confirmed_provider_calls": record["confirmed_provider_calls"],
        }
    expected = {key: failed[key] for key in ("confirmed_process_launches", "confirmed_provider_calls", "failure_contact_evidence")}
    observed = {key: record.get(key) for key in expected}
    if observed == expected:
        return {"kind": "persisted_terminal_contact_accounting", "source_terminal": study.fingerprint(terminal_path), **expected}
    if observed == {"confirmed_process_launches": 0, "confirmed_provider_calls": 0, "failure_contact_evidence": None}:
        return {"kind": "derived_read_only_terminal_contact_accounting", "source_terminal": study.fingerprint(terminal_path), **expected}
    raise ValueError("v5 reconcile terminal contact accounting drifted")


def _terminal_state(cell_root: Path, native_root: Path, cell: Mapping[str, Any], work_dir: Path, frozen: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> tuple[str, str | None]:
    completion = cell_root / "completion-receipt.json"
    reconcile = cell_root / "terminal-reconcile-required.json"
    reconciled = cell_root / "reconciled-completion.json"
    intent = cell_root / "launch-intent.json"
    present = [path for path in (completion, reconcile, reconciled, intent) if path.exists()]
    if not present:
        return "new", None
    if not intent.exists():
        raise ValueError("v5 terminal state lacks its launch intent")
    intent_record = study.read_json(intent)
    if intent_record.get("study_id") != study.STUDY_ID or intent_record.get("cell_id") != cell["cell_id"] or intent_record.get("contact_state") != "pre_native_intent" or intent_record.get("confirmed_process_launches") != 0 or intent_record.get("confirmed_provider_calls") != 0 or intent_record.get("intended_maximum_process_launches") != 1 or intent_record.get("intended_maximum_provider_calls") != 1:
        raise ValueError("v5 launch intent is malformed")
    if not _snapshot_is_ordered(work_dir, intent_record.get("predecessor_snapshot"), frozen, cell, sealed_evidence_validator):
        return "historical_policy_violation", None
    if completion.exists() and not reconcile.exists() and intent.exists():
        return "completed", _receipt_session(cell_root, native_root, cell, "completion-receipt.json", sealed_evidence_validator)
    if reconcile.exists() and reconciled.exists() and not completion.exists() and intent.exists():
        return "reconciled", _receipt_session(cell_root, native_root, cell, "reconciled-completion.json", sealed_evidence_validator)
    if reconcile.exists() and not completion.exists() and not reconciled.exists() and intent.exists():
        record = study.read_json(reconcile)
        if record.get("study_id") != study.STUDY_ID or record.get("cell_id") != cell["cell_id"] or record.get("contact_state") != "ambiguous_after_intent" or record.get("confirmed_provider_calls") not in {0, 1} or record.get("confirmed_process_launches") not in {0, 1}:
            raise ValueError("v5 reconcile terminal record is malformed")
        _terminal_accounting_view(cell_root, native_root, cell, sealed_evidence_validator)
        return "reconcile_required", None
    raise ValueError("v5 launch state is incomplete or contradictory")


def _existing_sessions(work_dir: Path, frozen: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> set[str]:
    sessions: set[str] = set()
    for cell in frozen["cells"]:
        cell_root = _cell_root(work_dir, str(cell["cell_id"]))
        state, session = _terminal_state(cell_root, cell_root / "native-run", cell, work_dir, frozen, sealed_evidence_validator)
        if state in {"completed", "reconciled"}:
            if session in sessions:
                raise ValueError("v5 completed cells reused a native Nous session")
            sessions.add(str(session))
    return sessions


def execute_one(work_dir: Path, *, cell_id: str, allow_remote: bool, runner: Callable[..., Any] = run_judge, timeout: float = 600, sealed_evidence_validator: Callable[[Path], str] = _sealed_session_id) -> dict[str, Any]:
    if allow_remote is not True or timeout != 600:
        raise ValueError("v5 execution requires explicit allow_remote and frozen 600-second timeout")
    frozen = _load_frozen(work_dir)
    cell = next((candidate for candidate in frozen["cells"] if candidate.get("cell_id") == cell_id), None)
    if not isinstance(cell, Mapping):
        raise TypeError("v5 cell is outside the frozen schedule")
    cell_root = _cell_root(work_dir, cell_id)
    existing_sessions = _existing_sessions(work_dir, frozen, sealed_evidence_validator)
    terminal, session = _terminal_state(cell_root, cell_root / "native-run", cell, work_dir, frozen, sealed_evidence_validator)
    if terminal != "new":
        result = {"cell_id": cell_id, "state": "terminal_no_resend" if terminal == "completed" else terminal, "confirmed_provider_calls": 0, "confirmed_process_launches": 0, "session_id": session}
        if terminal == "reconcile_required":
            view = _terminal_accounting_view(cell_root, cell_root / "native-run", cell, sealed_evidence_validator)
            result.update({key: view[key] for key in ("confirmed_provider_calls", "confirmed_process_launches")})
            result["terminal_accounting_view"] = view
        return result
    records = _prepared_root(cell_root, cell)
    _predecessor_snapshot(work_dir, frozen, cell, sealed_evidence_validator)
    native_root = cell_root / "native-run"
    if native_root.exists():
        raise ValueError("v5 refuses a pre-existing native run directory")
    launched = False
    started = time.monotonic()

    def before_provider_attempt(context: Mapping[str, Any]) -> None:
        nonlocal launched, records
        if launched:
            raise ValueError("v5 callback attempted a second provider launch")
        records = _prepared_root(cell_root, cell, allow_native_run=True)
        predecessor_snapshot = _predecessor_snapshot(work_dir, frozen, cell, sealed_evidence_validator)
        checkpoint_prompt, schema_bytes = _native_precontact_dir(native_root)
        binding = _validate_callback_context(context, native_root, cell, records["prepared.json"], checkpoint_prompt, schema_bytes)
        _write_new(cell_root / "launch-intent.json", {"format_version": 1, "study_id": study.STUDY_ID, "kind": "single_native_nous_launch_intent", "cell_id": cell_id, "prepared_sha256": study.sha(cell_root / "prepared.json"), "route_proof_sha256": study.sha(cell_root / "zero-new-spend-route-proof.json"), "callback": binding, "predecessor_snapshot": predecessor_snapshot, "contact_state": "pre_native_intent", "confirmed_process_launches": 0, "confirmed_provider_calls": 0, "intended_maximum_process_launches": 1, "intended_maximum_provider_calls": 1})
        launched = True

    folder = Path(str(cell["input_folder"]))
    try:
        runner(artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"], task_contract_path=folder / "task-contract.json", scope_compatibility_override_path=cell_root / "scope-compatibility-override.json", bundle_id="prose.short_story", provider="nous", model=study.MODEL, reasoning="max", output_dir=native_root, registry=registry_path(), bundles=bundles_path(), question_ids=cell["question_ids"], batch_size=8, batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=str(cell["item_id"]), strict_ai=False, allow_unattested_reasoning=True, max_physical_http_attempts_per_logical_request=1, before_provider_attempt=before_provider_attempt)
        if not launched:
            raise ValueError("v5 runner returned without provider callback")
        receipt = _completion_payload(cell_root, native_root, cell, started, sealed_evidence_validator)
        if receipt["native_contact_identity"]["session_id"] in existing_sessions:
            raise ValueError("v5 new cell reused a native Nous session")
        _write_new(cell_root / "completion-receipt.json", receipt)
    except BaseException as error:
        if launched:
            confirmed = {"confirmed_process_launches": 0, "confirmed_provider_calls": 0}
            validation_error: dict[str, str] | None = None
            failure_evidence: dict[str, Any] | None = None
            try:
                settled = _completion_payload(cell_root, native_root, cell, started, sealed_evidence_validator)
                confirmed = {key: settled[key] for key in confirmed}
            except Exception as evidence_error:  # noqa: BLE001 - any validator failure is terminal after intent.
                try:
                    failed = _failed_contact_evidence(cell_root, native_root, cell, sealed_evidence_validator)
                except Exception as failure_error:  # noqa: BLE001 - an unsealed failure cannot prove contact.
                    validation_error = {"class": type(failure_error).__name__, "message": str(failure_error)[:1000]}
                else:
                    if failed is None:
                        validation_error = {"class": type(evidence_error).__name__, "message": str(evidence_error)[:1000]}
                    else:
                        confirmed = {key: failed[key] for key in confirmed}
                        failure_evidence = failed["failure_contact_evidence"]
            terminal = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "postlaunch_terminal_reconcile_required", "cell_id": cell_id, "contact_state": "ambiguous_after_intent", **confirmed, "error": {"class": type(error).__name__, "message": str(error)[:1000]}, "retry_policy": "no_resend_fresh_successor_only"}
            if failure_evidence is not None:
                terminal["failure_contact_evidence"] = failure_evidence
            if validation_error is not None:
                terminal["evidence_validation_error"] = validation_error
            _write_new(cell_root / "terminal-reconcile-required.json", terminal)
            return {"cell_id": cell_id, "state": "reconcile_required", **confirmed}
        raise
    return {"cell_id": cell_id, "state": "completed_provisional_breadth_only", "confirmed_provider_calls": 1, "confirmed_process_launches": 1, "receipt": receipt}


def reconcile_existing(work_dir: Path, *, sealed_evidence_validator: Callable[[Path], str] = _sealed_session_id, elapsed_reader: Callable[[Path], float] = _sealed_elapsed_seconds) -> list[dict[str, Any]]:
    """Replay native artifacts only; it never invokes a provider or runner."""
    frozen = _load_frozen(work_dir)
    sessions = _existing_sessions(work_dir, frozen, sealed_evidence_validator)
    results: list[dict[str, Any]] = []
    blocked_by: str | None = None
    for cell in frozen["cells"]:
        cell_id = str(cell["cell_id"])
        cell_root = _cell_root(work_dir, cell_id)
        native_root = cell_root / "native-run"
        state, session = _terminal_state(cell_root, native_root, cell, work_dir, frozen, sealed_evidence_validator)
        if state in {"completed", "reconciled"}:
            if session in sessions:
                results.append({"cell_id": cell_id, "state": state, "session_id": session})
                continue
            raise ValueError("v5 persisted completion session inventory drifted")
        if state == "new":
            results.append({"cell_id": cell_id, "state": "unstarted"})
            continue
        if state == "historical_policy_violation":
            results.append({"cell_id": cell_id, "state": "historical_policy_violation_not_promoted"})
            continue
        if blocked_by is not None:
            results.append({"cell_id": cell_id, "state": "historical_policy_violation_not_promoted", "blocked_by": blocked_by})
            continue
        try:
            _prepared_root(cell_root, cell, allow_native_run=True, allowed_extra=frozenset({"launch-intent.json", "terminal-reconcile-required.json"}))
            checkpoint = study.read_json(native_root / "responses" / "batch-0001.json", canonical_required=False)
            provider = checkpoint.get("provider")
            artifacts = provider.get("provider_artifacts") if isinstance(provider, Mapping) else None
            if not isinstance(artifacts, Mapping):
                raise TypeError("v5 terminal native result lacks provider artifacts")
            evidence_root = native_root / str(artifacts.get("evidence_tree", {}).get("path", ""))
            receipt = _completion_payload(cell_root, native_root, cell, None, sealed_evidence_validator, elapsed_seconds=elapsed_reader(evidence_root))
            session = receipt["native_contact_identity"]["session_id"]
            if session in sessions:
                raise ValueError("v5 reconciled completion reused a native Nous session")
            receipt["kind"] = "reconciled_provisional_breadth_only_completion"
            receipt["reconciliation"] = {
                "kind": "post_intent_read_only_replay",
                "terminal_reconcile_required": study.fingerprint(cell_root / "terminal-reconcile-required.json"),
            }
            _write_new(cell_root / "reconciled-completion.json", receipt)
            sessions.add(session)
            results.append({"cell_id": cell_id, "state": "reconciled_completion_provisional_breadth_only", "session_id": session})
        except Exception as error:  # noqa: BLE001 - a terminal root remains terminal until a complete replay validates.
            blocked_by = cell_id
            results.append({"cell_id": cell_id, "state": "reconcile_required", "error": {"class": type(error).__name__, "message": str(error)[:1000]}})
    return results


def execute(work_dir: Path, *, allow_remote: bool, timeout: float = 600, runner: Callable[..., Any] = run_judge, sealed_evidence_validator: Callable[[Path], str] = _sealed_session_id) -> list[dict[str, Any]]:
    frozen = _load_frozen(work_dir)
    results: list[dict[str, Any]] = []
    for cell in frozen["cells"]:
        result = execute_one(work_dir, cell_id=str(cell["cell_id"]), allow_remote=allow_remote, timeout=timeout, runner=runner, sealed_evidence_validator=sealed_evidence_validator)
        results.append(result)
        if result.get("state") != "completed_provisional_breadth_only":
            break
    sessions = [result["receipt"]["native_contact_identity"]["session_id"] for result in results if result.get("state") == "completed_provisional_breadth_only"]
    if len(sessions) != len(set(sessions)):
        raise ValueError("v5 cells reused a native Nous session")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--timeout", type=float, default=600)
    arguments = parser.parse_args()
    print(json.dumps(execute(arguments.work_dir.resolve(), allow_remote=arguments.allow_remote, timeout=arguments.timeout), sort_keys=True))
