#!/usr/bin/env python3
"""Execute the v5 Nous batch-8 cells once each, with no in-place retry path."""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import time
from collections.abc import Callable, Mapping
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


def _prepared_root(cell_root: Path, cell: Mapping[str, Any], *, allow_native_run: bool = False) -> dict[str, Any]:
    study.plain_entry(cell_root, directory=True)
    children = {child.name: child for child in cell_root.iterdir()}
    expected = set(study.PREPARED_FILES) | ({"native-run"} if allow_native_run else set())
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
    spec.loader.exec_module(bridge)
    candidates = [path for path in evidence_root.iterdir() if path.is_dir() and (path / "manifest.json").is_file() and (path / "receipt.json").is_file()]
    if len(candidates) != 1:
        raise ValueError("v5 sealed evidence does not have one native session")
    validated = bridge.validate_evidence(candidates[0])
    receipt = json.loads((candidates[0] / "receipt.json").read_text(encoding="utf-8"))
    session_id = receipt.get("run_id") if isinstance(validated, Mapping) and validated.get("valid") is True and isinstance(receipt, Mapping) else None
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("v5 sealed evidence lacks its native session identity")
    return session_id


def _completion_payload(cell_root: Path, native_root: Path, cell: Mapping[str, Any], started: float, sealed_evidence_validator: Callable[[Path], str]) -> dict[str, Any]:
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
    elapsed = time.monotonic() - started
    if not 0 < elapsed < 100:
        raise ValueError("v5 completion exceeded the frozen 100-second bound")
    result = {
        "format_version": 1, "study_id": study.STUDY_ID, "kind": "provisional_breadth_only_completion",
        "cell_id": cell["cell_id"], "elapsed_seconds": elapsed, "confirmed_process_launches": 1, "confirmed_provider_calls": 1,
        "native_contact_identity": {"provider": "nous", "model": study.MODEL, "reasoning": "max", "tools_enabled": False, "session_id": session_id},
        "checkpoint": study.fingerprint(native_root / "responses" / "batch-0001.json"), "provider": dict(provider),
        "launch_intent_sha256": study.sha(cell_root / "launch-intent.json"), "classification": "PROVISIONAL_BREADTH_ONLY",
    }
    return result


def _completed_session(cell_root: Path, native_root: Path, cell: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> str:
    receipt = study.read_json(cell_root / "completion-receipt.json")
    if receipt.get("study_id") != study.STUDY_ID or receipt.get("kind") != "provisional_breadth_only_completion" or receipt.get("cell_id") != cell["cell_id"] or receipt.get("confirmed_provider_calls") != 1 or receipt.get("confirmed_process_launches") != 1:
        raise ValueError("v5 completed receipt is malformed")
    checkpoint = study.read_json(native_root / "responses" / "batch-0001.json", canonical_required=False)
    provider = checkpoint.get("provider")
    artifacts = provider.get("provider_artifacts") if isinstance(provider, Mapping) else None
    if not isinstance(artifacts, Mapping):
        raise TypeError("v5 completed receipt lacks native provider artifacts")
    runner_module._validate_provider_artifacts(native_root, checkpoint)
    evidence_path = native_root / str(artifacts.get("evidence_tree", {}).get("path", ""))
    session_id = sealed_evidence_validator(evidence_path)
    if receipt.get("native_contact_identity", {}).get("session_id") != session_id:
        raise ValueError("v5 completed receipt session binding drifted")
    return session_id


def _terminal_state(cell_root: Path, native_root: Path, cell: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> tuple[str, str | None]:
    completion = cell_root / "completion-receipt.json"
    reconcile = cell_root / "terminal-reconcile-required.json"
    intent = cell_root / "launch-intent.json"
    present = [path for path in (completion, reconcile, intent) if path.exists()]
    if not present:
        return "new", None
    if not intent.exists():
        raise ValueError("v5 terminal state lacks its launch intent")
    intent_record = study.read_json(intent)
    if intent_record.get("study_id") != study.STUDY_ID or intent_record.get("cell_id") != cell["cell_id"] or intent_record.get("contact_state") != "pre_native_intent" or intent_record.get("confirmed_process_launches") != 0 or intent_record.get("confirmed_provider_calls") != 0 or intent_record.get("intended_maximum_process_launches") != 1 or intent_record.get("intended_maximum_provider_calls") != 1:
        raise ValueError("v5 launch intent is malformed")
    if completion.exists() and not reconcile.exists() and intent.exists():
        return "completed", _completed_session(cell_root, native_root, cell, sealed_evidence_validator)
    if reconcile.exists() and not completion.exists() and intent.exists():
        record = study.read_json(reconcile)
        if record.get("study_id") != study.STUDY_ID or record.get("cell_id") != cell["cell_id"] or record.get("contact_state") != "ambiguous_after_intent" or record.get("confirmed_provider_calls") not in {0, 1} or record.get("confirmed_process_launches") not in {0, 1}:
            raise ValueError("v5 reconcile terminal record is malformed")
        return "reconcile_required", None
    raise ValueError("v5 launch state is incomplete or contradictory")


def _existing_sessions(work_dir: Path, frozen: Mapping[str, Any], sealed_evidence_validator: Callable[[Path], str]) -> set[str]:
    sessions: set[str] = set()
    for cell in frozen["cells"]:
        cell_root = _cell_root(work_dir, str(cell["cell_id"]))
        state, session = _terminal_state(cell_root, cell_root / "native-run", cell, sealed_evidence_validator)
        if state == "completed":
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
    terminal, session = _terminal_state(cell_root, cell_root / "native-run", cell, sealed_evidence_validator)
    if terminal != "new":
        return {"cell_id": cell_id, "state": "terminal_no_resend" if terminal == "completed" else terminal, "confirmed_provider_calls": 0, "confirmed_process_launches": 0, "session_id": session}
    records = _prepared_root(cell_root, cell)
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
        checkpoint_prompt, schema_bytes = _native_precontact_dir(native_root)
        binding = _validate_callback_context(context, native_root, cell, records["prepared.json"], checkpoint_prompt, schema_bytes)
        _write_new(cell_root / "launch-intent.json", {"format_version": 1, "study_id": study.STUDY_ID, "kind": "single_native_nous_launch_intent", "cell_id": cell_id, "prepared_sha256": study.sha(cell_root / "prepared.json"), "route_proof_sha256": study.sha(cell_root / "zero-new-spend-route-proof.json"), "callback": binding, "contact_state": "pre_native_intent", "confirmed_process_launches": 0, "confirmed_provider_calls": 0, "intended_maximum_process_launches": 1, "intended_maximum_provider_calls": 1})
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
            try:
                settled = _completion_payload(cell_root, native_root, cell, started, sealed_evidence_validator)
                confirmed = {key: settled[key] for key in confirmed}
            except Exception as evidence_error:  # noqa: BLE001 - any validator failure is terminal after intent.
                validation_error = {"class": type(evidence_error).__name__, "message": str(evidence_error)[:1000]}
            terminal = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "postlaunch_terminal_reconcile_required", "cell_id": cell_id, "contact_state": "ambiguous_after_intent", **confirmed, "error": {"class": type(error).__name__, "message": str(error)[:1000]}, "retry_policy": "no_resend_fresh_successor_only"}
            if validation_error is not None:
                terminal["evidence_validation_error"] = validation_error
            _write_new(cell_root / "terminal-reconcile-required.json", terminal)
            return {"cell_id": cell_id, "state": "reconcile_required", **confirmed}
        raise
    return {"cell_id": cell_id, "state": "completed_provisional_breadth_only", "confirmed_provider_calls": 1, "confirmed_process_launches": 1, "receipt": receipt}


def execute(work_dir: Path, *, allow_remote: bool, timeout: float = 600, runner: Callable[..., Any] = run_judge, sealed_evidence_validator: Callable[[Path], str] = _sealed_session_id) -> list[dict[str, Any]]:
    frozen = _load_frozen(work_dir)
    results = [execute_one(work_dir, cell_id=str(cell["cell_id"]), allow_remote=allow_remote, timeout=timeout, runner=runner, sealed_evidence_validator=sealed_evidence_validator) for cell in frozen["cells"]]
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
