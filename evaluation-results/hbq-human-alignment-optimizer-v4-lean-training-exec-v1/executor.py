#!/usr/bin/env python3
"""Training-row-local preparation and one-launch guard for the frozen HANNA lean pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-lean-training-exec-v1"
LEAN_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-development-v1" / "optimizer.py"
NATIVE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
EXEC_V1_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
EXEC_V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
VERIFIER_CONTRACT_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-training-verifier-v1" / "study-contract.json"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "b608ae2313bca80289f7edc629ea3656f0394f7c76ec559adb35c73ecef7c27b"
LEAN_SHA256 = "cbbf3b51a875ff4c0c1b72379e089cbd8f0a76cb2a0da5da74f31a13b4de377f"
NATIVE_SHA256 = "6d93f69216d62bd0847aa6b338b6e2360587c82608669f78fbad245a34ba1c49"
EXEC_V1_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
EXEC_V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
VERIFIER_CONTRACT_SHA256 = "20ea7d2e7a9bc59ca01227f34fd9c441b6ccb902c2d02aa41256df69f1bae27b"
GROK_SYSTEM_PROMPT = "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."
GROK_TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]
PREPARED_FILES = frozenset({"outbound-payload.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError(f"HANNA lean training path is reparsed: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError(f"HANNA lean training file identity drifted: {absolute}")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError(f"HANNA lean training file changed during read: {absolute}")
    return raw


def _load_module(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if sha256(raw) != expected_sha256:
        raise ValueError(f"HANNA lean training pinned dependency drifted: {path.name}")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if _stable_bytes(path) != raw:
        raise ValueError(f"HANNA lean training module changed during load: {path.name}")
    return module


def contract() -> dict[str, Any]:
    raw = _stable_bytes(CONTRACT_PATH)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA lean training contract is invalid") from error
    if sha256(raw) != CONTRACT_SHA256 or value.get("study_id") != STUDY_ID:
        raise ValueError("HANNA lean training contract identity drifted")
    return value


def _verifier_contract() -> None:
    raw = _stable_bytes(VERIFIER_CONTRACT_PATH)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA lean training verifier contract is invalid") from error
    if (sha256(raw) != VERIFIER_CONTRACT_SHA256
            or value.get("study_id") != "hbq-human-alignment-optimizer-v4-lean-training-verifier-v1"
            or value.get("kind") != "provider_free_complete_training_receipt_replay"):
        raise ValueError("HANNA lean training verifier contract identity drifted")


def _load_lean() -> ModuleType:
    return _load_module(LEAN_PATH, LEAN_SHA256, "_hanna_lean_training")


def _load_native() -> ModuleType:
    return _load_module(NATIVE_PATH, NATIVE_SHA256, "_hanna_lean_training_native")


def _load_exec(route_name: str) -> ModuleType:
    if route_name == "grok_primary":
        return _load_module(EXEC_V1_PATH, EXEC_V1_SHA256, "_hanna_lean_training_exec_v1")
    if route_name == "sol_validation":
        return _load_module(EXEC_V3_PATH, EXEC_V3_SHA256, "_hanna_lean_training_exec_v3")
    raise ValueError("HANNA lean training route is unsupported")


def _training_rows(schedule: Mapping[str, Any]) -> list[dict[str, Any]]:
    try:
        rows = [*schedule["partitions"]["training"]["grok"], *schedule["partitions"]["training"]["sol_sprinkled"]]
    except (KeyError, TypeError) as error:
        raise ValueError("HANNA lean training schedule is malformed") from error
    if len(rows) != 35 or sum(row.get("route_name") == "grok_primary" for row in rows) != 25 or sum(row.get("route_name") == "sol_validation" for row in rows) != 10:
        raise ValueError("HANNA lean training geometry drifted")
    return [dict(row) for row in rows]


def training_schedule(*, frozen_successor_path: Path, hanna_csv_path: Path,
                      schedule_loader: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    contract()
    schedule = dict((schedule_loader or _load_lean().freeze_lean_schedule)(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)))
    _training_rows(schedule)
    return schedule


def training_row(schedule: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    matches = [row for row in _training_rows(schedule) if row["cell_id"] == cell_id]
    if len(matches) != 1:
        raise ValueError("HANNA lean training accepts only a frozen training cell")
    return matches[0]


def _payload(native: ModuleType, row: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[bytes, bytes, bytes]:
    payload = native._payload(native._load_v3(), row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    value = json.loads(payload.decode("utf-8"))
    components = value.get("components") if isinstance(value, dict) else None
    if native.canonical(value) != payload or not isinstance(components, dict):
        raise ValueError("HANNA lean training outbound payload is invalid")
    task, schema = components.get("task_payload"), components.get("response_schema")
    if not isinstance(task, str) or not isinstance(schema, str):
        raise ValueError("HANNA lean training task/schema are absent")
    task_bytes, schema_bytes = task.encode("utf-8"), schema.encode("utf-8")
    if sha256(task_bytes) != row["task_payload_sha256"] or sha256(schema_bytes) != row["response_schema_sha256"]:
        raise ValueError("HANNA lean training exact prompt/schema binding drifted")
    return payload, task_bytes, schema_bytes


def _write_new(native: ModuleType, path: Path, value: bytes) -> None:
    native._write_new(path, value)


def _route(exec_module: ModuleType, row: Mapping[str, Any], queue_root: Path, broker_factory: Callable[[Path], Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    return (exec_module.validate_live_grok_route(Path(queue_root), broker_factory=broker_factory)
            if row["route_name"] == "grok_primary" else exec_module.validate_live_sol_route(Path(queue_root), broker_factory=broker_factory))


def _prepared_root(native: ModuleType, root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes,
                   task: bytes, schema: bytes, route_evidence: Mapping[str, Any], authorization_sha256: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_sha256):
        raise ValueError("HANNA lean training authorization acknowledgement must be lowercase SHA-256")
    grok = row["route_name"] == "grok_primary"
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure",
                  "cell_id": row["cell_id"], "route_identity": row["route"], "destination": row["route"]["destination"],
                  "task_payload": {"bytes": len(task), "sha256": sha256(task), "text": task.decode("utf-8")},
                  "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")},
                  "system_prompt_override": GROK_SYSTEM_PROMPT if grok else None,
                  "tool_free_argv": GROK_TOOL_FREE_ARGV if grok else None, "tools_enabled": False,
                  "web_search_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    authorization = {"format_version": 1, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference",
                     "cell_id": row["cell_id"], "acknowledgement_sha256": authorization_sha256,
                     "disclosure_sha256": sha256(canonical(disclosure)), "route_identity": row["route"], "destination": row["route"]["destination"]}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "route_proof", "cell_id": row["cell_id"],
             "status": "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE", "route_identity": row["route"],
             "destination": row["route"]["destination"], "route_evidence": dict(route_evidence), "zero_charge_only": True,
             "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_preparation", "cell": dict(row),
                "schedule_sha256": schedule["schedule_sha256"], "outbound_payload_sha256": sha256(payload),
                "request_sha256": sha256(task), "response_schema_sha256": sha256(schema), "route_evidence": dict(route_evidence),
                "disclosure_sha256": sha256(canonical(disclosure)), "authorization_sha256": sha256(canonical(authorization)),
                "route_proof_sha256": sha256(canonical(proof)), "route_status": "GROK_PREPARED_NO_CONTACT" if grok else "SOL_PREPARED_NO_CONTACT",
                "provider_calls_made": 0, "process_launches": 0, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False}
    root.mkdir(parents=True, exist_ok=False)
    for name, raw in {"outbound-payload.json": payload, "prompt-request.bin": task, "response-schema.json": schema,
                      "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(authorization),
                      "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}.items():
        _write_new(native, root / name, raw)
    return prepared


def _expected_prepared_artifacts(row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, task: bytes,
                                 schema: bytes, route_evidence: Mapping[str, Any], authorization_sha256: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_sha256):
        raise ValueError("HANNA lean training authorization acknowledgement must be lowercase SHA-256")
    grok = row["route_name"] == "grok_primary"
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": row["cell_id"], "route_identity": row["route"], "destination": row["route"]["destination"], "task_payload": {"bytes": len(task), "sha256": sha256(task), "text": task.decode("utf-8")}, "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")}, "system_prompt_override": GROK_SYSTEM_PROMPT if grok else None, "tool_free_argv": GROK_TOOL_FREE_ARGV if grok else None, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    authorization = {"format_version": 1, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": authorization_sha256, "disclosure_sha256": sha256(canonical(disclosure)), "route_identity": row["route"], "destination": row["route"]["destination"]}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "route_proof", "cell_id": row["cell_id"], "status": "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE", "route_identity": row["route"], "destination": row["route"]["destination"], "route_evidence": dict(route_evidence), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_preparation", "cell": dict(row), "schedule_sha256": schedule["schedule_sha256"], "outbound_payload_sha256": sha256(payload), "request_sha256": sha256(task), "response_schema_sha256": sha256(schema), "route_evidence": dict(route_evidence), "disclosure_sha256": sha256(canonical(disclosure)), "authorization_sha256": sha256(canonical(authorization)), "route_proof_sha256": sha256(canonical(proof)), "route_status": "GROK_PREPARED_NO_CONTACT" if grok else "SOL_PREPARED_NO_CONTACT", "provider_calls_made": 0, "process_launches": 0, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False}
    return prepared, {"outbound-payload.json": payload, "prompt-request.bin": task, "response-schema.json": schema, "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(authorization), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def prepare_one(*, output_root: Path, cell_id: str, queue_root: Path, frozen_successor_path: Path, hanna_csv_path: Path,
                authorization_acknowledgement_sha256: str, schedule_loader: Callable[..., Mapping[str, Any]] | None = None,
                broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    schedule = training_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), schedule_loader=schedule_loader)
    row, native = training_row(schedule, cell_id), _load_native()
    payload, task, schema = _payload(native, row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    _route_value, evidence = _route(_load_exec(row["route_name"]), row, Path(queue_root), broker_factory)
    root = Path(output_root) / cell_id
    if root.exists():
        raise ValueError("HANNA lean training refuses a pre-existing preparation root")
    prepared = _prepared_root(native, root, row, schedule, payload, task, schema, evidence, authorization_acknowledgement_sha256)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_prepared_cell", "cell_id": cell_id,
            "route_name": row["route_name"], "schedule_sha256": schedule["schedule_sha256"], "provider_calls_made": 0, "prepared": prepared}


def execute_one(*, output_root: Path, cell_id: str, queue_root: Path, frozen_successor_path: Path, hanna_csv_path: Path,
                authorization_acknowledgement_sha256: str, allow_remote: bool,
                broker_factory: Callable[[Path], Any] | None = None, call_grok: Callable[..., Any] | None = None,
                call_codex: Callable[..., Any] | None = None, schedule_loader: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("HANNA lean training requires explicit allow_remote=True")
    schedule = training_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), schedule_loader=schedule_loader)
    row, native, root = training_row(schedule, cell_id), _load_native(), Path(output_root) / cell_id
    if any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json")):
        raise ValueError("HANNA lean training refuses resend after launch state")
    if not root.is_dir() or {path.name for path in root.iterdir()} != PREPARED_FILES:
        raise ValueError("HANNA lean training requires one pristine prepared root")
    payload, task, schema = _payload(native, row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    execution = _load_exec(row["route_name"])
    route, evidence = _route(execution, row, Path(queue_root), broker_factory)
    prepared, expected_artifacts = _expected_prepared_artifacts(row, schedule, payload, task, schema, evidence, authorization_acknowledgement_sha256)
    for name, expected in expected_artifacts.items():
        if _stable_bytes(root / name) != expected:
            raise ValueError(f"HANNA lean training persisted prepared artifact drifted: {name}")
    collector_sha = sha256(_stable_bytes(Path(__file__)))
    intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_contact_intent", "cell_id": cell_id,
              "prepared_sha256": sha256(canonical(prepared)), "request_sha256": sha256(task), "response_schema_sha256": sha256(schema),
              "outbound_payload_sha256": sha256(payload), "collector_executor_sha256": collector_sha, "native_contact_proven": False}
    launches = 0
    def before() -> None:
        nonlocal launches
        if launches:
            raise ValueError("HANNA lean training launch callback repeated")
        fresh_route, fresh_evidence = _route(execution, row, Path(queue_root), broker_factory)
        if fresh_route != route or fresh_evidence != evidence:
            raise ValueError("HANNA lean training route changed adjacent to launch")
        _write_new(native, root / "launch-intent.json", canonical(intent)); launches = 1
    def reconcile(error: BaseException) -> dict[str, Any]:
        result = {"format_version": 1, "study_id": STUDY_ID, "kind": "reconcile_required_after_process_launch", "cell_id": cell_id, "error_type": type(error).__name__, "provider_calls_made": 1, "process_launches": 1}
        if not (root / "result.json").exists():
            _write_new(native, root / "result.json", canonical(result))
        return result
    try:
        if row["route_name"] == "grok_primary":
            content, record = (call_grok or execution._load_call_grok())(executable=route["grok_command"][0], model="grok-4.6", reasoning="high", prompt=task.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json", batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, allow_unattested_reasoning=True, system_prompt_override=GROK_SYSTEM_PROMPT, before_provider_attempt=before)
            artifact = record.get("provider_artifacts", {}).get("grok_envelope", {})
            response = _stable_bytes(root / str(artifact.get("path", "")))
            request_id, session_id = execution._envelope_identity(response, record)
            identity = {"provider": "xai_grok_build", "route_name": route["name"], "requested_model": "grok-4.6", "requested_reasoning_effort": "high", "effective_model": "grok-4.6-build", "provider_reported_model": "grok-4.6-build", "identity_evidence": "requested_and_cli_envelope_reported_model_reasoning_unattested", "reasoning_attested": False, "transport_identity": "grok_build_saved_session_subscription_tool_free_v1", "contact_id": request_id, "session_id": session_id}
            effective = {"requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "reasoning_attested": False, "grok_cli_version": route["grok_cli_version"], "grok_command_identity": route["grok_command_identity"], "tool_free_argv": GROK_TOOL_FREE_ARGV, "system_prompt_override": GROK_SYSTEM_PROMPT}
            native_contact, cardinality = True, "proven_exactly_one"
        else:
            content, record = (call_codex or execution._load_call_codex())(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high", prompt=task.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json", batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, capture_jsonl_events=True, before_provider_attempt=before)
            response = _stable_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
            events = _stable_bytes(root / "responses" / "batch-0001.attempt-0001.events.jsonl")
            if not isinstance(content, str) or content.encode("utf-8") != response:
                raise ValueError("HANNA lean training Sol final-response association drifted")
            projection = execution._codex_event_projection(events, execution._load_parse_codex_events())
            thread = projection.get("thread_id")
            if not isinstance(thread, str) or not thread:
                raise ValueError("HANNA lean training Sol lifecycle lacks its thread identity")
            identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested", "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread}", "session_id": f"local-codex-thread-session:{thread}"}
            effective = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "provider_attested": False, "codex_cli_version": route["codex_cli_version"], "codex_command_identity": route["codex_command_identity"], "capture_jsonl_events": True, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "event_projection": projection}
            native_contact, cardinality = False, "unproven"
    except BaseException as error:
        if launches == 0:
            return {"cell_id": cell_id, "state": "pending_precontact", "process_launches": 0, "native_contact_proven": False}
        return reconcile(error)
    try:
        if launches != 1:
            raise ValueError("HANNA lean training runner returned without exactly one launch")
        if native_contact:
            expected_path = "responses/batch-0001.attempt-0001.grok.envelope.json"
            artifact = record.get("provider_artifacts", {}).get("grok_envelope")
            expected_artifact = {"path": expected_path, "bytes": len(response), "sha256": sha256(response)}
            if (not isinstance(record, Mapping) or record.get("provider_artifacts") != {"grok_envelope": expected_artifact}
                    or record.get("cli_version") != route["grok_cli_version"]
                    or record.get("requested") != {"model": "grok-4.6", "reasoning_effort": "high"}
                    or record.get("reported") != {"provider": "grok", "model": "grok-4.6-build"}
                    or record.get("reasoning_attested") is not False
                    or artifact != expected_artifact
                    or _stable_bytes(root / expected_path) != response):
                raise ValueError("HANNA lean training Grok artifact/record association drifted")
            _write_new(native, root / "raw-grok-envelope.bin", response)
            _write_new(native, root / "grok-record.json", canonical(dict(record)))
        else:
            artifacts = record.get("provider_artifacts") if isinstance(record, Mapping) else None
            stderr = _stable_bytes(root / "raw-codex-stderr.bin")
            expected_artifacts = {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha256(stderr)}}
            if artifacts != expected_artifacts or _stable_bytes(root / "responses/batch-0001.attempt-0001.events.jsonl") != events:
                raise ValueError("HANNA lean training Sol artifact/record association drifted")
            _write_new(native, root / "raw-codex-events.bin", events)
            _write_new(native, root / "raw-codex-final-response.bin", response)
            _write_new(native, root / "codex-record.json", canonical(dict(record)))
        _write_new(native, root / "effective-settings.json", canonical(effective))
        result = {"format_version": 1, "study_id": STUDY_ID, "kind": "training_collector_result", "cell_id": cell_id, "identity": identity, "identity_sha256": sha256(canonical(identity)), "native_response_sha256": sha256(response), "effective_settings_sha256": sha256(canonical(effective)), "provider_calls_made": 1, "process_launches": 1}
        receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "lean_training_grok_native_receipt" if native_contact else "lean_training_sol_local_lifecycle_receipt", "cell": row, "schedule_sha256": schedule["schedule_sha256"], "outbound_payload_sha256": sha256(payload), "request_sha256": sha256(task), "response_schema_sha256": sha256(schema), "prepared_sha256": sha256(canonical(prepared)), "launch_intent_sha256": sha256(canonical(intent)), "route_evidence": evidence, "provider_calls_made": 1, "process_launches": 1, "identity": identity, "collector_executor_sha256": collector_sha, "native_response_sha256": sha256(response), "result_sha256": sha256(canonical(result)), "native_contact_proven": native_contact, "native_endpoint_contact_cardinality": cardinality}
        _write_new(native, root / "execution-receipt.json", canonical(receipt))
        _write_new(native, root / "result.json", canonical(result))
        return {"cell_id": cell_id, "state": "native_envelope_received" if native_contact else "local_codex_lifecycle_received_native_contact_unproven", "process_launches": 1, "native_contact_proven": native_contact, "identity": identity}
    except BaseException as error:
        return reconcile(error)


def emit_collector_receipts(*, output_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, references: list[Mapping[str, Any]],
                            schedule_loader: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    _verifier_contract()
    schedule = training_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), schedule_loader=schedule_loader)
    rows = _training_rows(schedule)
    if len(references) != len(rows) or [item.get("cell_id") for item in references] != [row["cell_id"] for row in rows]:
        raise ValueError("HANNA lean training receipt geometry or order drifted")
    if any(not isinstance(item, Mapping) or set(item) != {"cell_id", "execution_root"} for item in references):
        raise ValueError("HANNA lean training receipt reference shape is invalid")
    manifest = {"format_version": 1, "study_id": "hbq-human-alignment-optimizer-v4-lean-training-verifier-v1", "kind": "lean_training_collector_receipts", "collector_executor_sha256": sha256(_stable_bytes(Path(__file__))), "collector_contract_sha256": CONTRACT_SHA256, "optimizer_sha256": LEAN_SHA256, "native_executor_sha256": NATIVE_SHA256, "schedule_sha256": schedule["schedule_sha256"], "stage": "training", "cells": [dict(item) for item in references]}
    output_path = Path(output_path)
    if output_path.exists():
        raise ValueError("HANNA lean training refuses an existing receipt manifest")
    with output_path.open("xb") as handle:
        handle.write(canonical(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare-only", action="store_true"); mode.add_argument("--execute-one", action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--cell-id", required=True); parser.add_argument("--queue-root", type=Path, required=True); parser.add_argument("--frozen-successor", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "cell_id": args.cell_id, "queue_root": args.queue_root, "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare_only:
        if args.allow_remote: parser.error("--prepare-only forbids --allow-remote")
        result = prepare_one(**common)
    else:
        if not args.allow_remote: parser.error("--execute-one requires --allow-remote")
        result = execute_one(**common, allow_remote=True)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__":
    raise SystemExit(main())
