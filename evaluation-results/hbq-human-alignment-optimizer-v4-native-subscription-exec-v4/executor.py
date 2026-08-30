#!/usr/bin/env python3
"""Tool-free Sol execution for the two immutable replacement descendants."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
SCHEDULE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-sol-replacement-schedule-v1" / "schedule.py"
SCHEDULE_SHA256 = "e098739372c1b88cb84766e483c395ab3a7542c0ea45287d38b17187d1645d62"
SCHEDULE_CONTRACT_PATH = SCHEDULE_PATH.with_name("study-contract.json")
SCHEDULE_CONTRACT_SHA256 = "7162f41f00b3e23536270ed93da54315f33170673741a8805390738830a89df1"
EXEC_V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
EXEC_V3_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
EXEC_V3_CONTRACT_PATH = EXEC_V3_PATH.with_name("study-contract.json")
EXEC_V3_CONTRACT_SHA256 = "d92970c60a538a229c8f5470d53e8fd3dd4d163aff25b0110b6453f6caf080f5"
STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-exec-v4"
PREPARED_FILES = frozenset({"matched-grok-task.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
PRECONTACT_FAILURE = "precontact-failure.json"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _load_module(path: Path, expected: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    if _sha(raw) != expected:
        raise ValueError("HANNA Sol exec-v4 pinned predecessor bytes drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if _sha(path.read_bytes()) != expected:
        raise ValueError("HANNA Sol exec-v4 predecessor changed during load")
    return module


def _schedule() -> ModuleType:
    if _sha(SCHEDULE_CONTRACT_PATH.read_bytes()) != SCHEDULE_CONTRACT_SHA256:
        raise ValueError("HANNA Sol exec-v4 replacement contract drifted")
    return _load_module(SCHEDULE_PATH, SCHEDULE_SHA256, "_hanna_sol_replacement_schedule_v1")


def _v3() -> ModuleType:
    if _sha(EXEC_V3_CONTRACT_PATH.read_bytes()) != EXEC_V3_CONTRACT_SHA256:
        raise ValueError("HANNA Sol exec-v4 v3 contract drifted")
    return _load_module(EXEC_V3_PATH, EXEC_V3_SHA256, "_hanna_sol_exec_v3")


def _row(cell_id: str) -> dict[str, Any]:
    rows = _schedule().derive_replacements()
    selected = [row for row in rows if row["cell_id"] == cell_id]
    if len(selected) != 1:
        raise ValueError("HANNA Sol exec-v4 accepts only the two replacement cell IDs")
    return selected[0]


def _write_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _plain_entry(path: Path, *, directory: bool = False) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"HANNA Sol exec-v4 prepared root is reparsed: {path}")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError(f"HANNA Sol exec-v4 prepared root entry type drifted: {path}")


def _stable_bytes(path: Path) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        _plain_entry(current, directory=current != path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"HANNA Sol exec-v4 prepared file changed during read: {path}")
    return raw


def _read_json(path: Path, label: str, *, canonical_required: bool = True) -> dict[str, Any]:
    try:
        raw = _stable_bytes(path)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA Sol exec-v4 {label} is unreadable") from error
    if not isinstance(value, dict) or (canonical_required and _canonical(value) != raw):
        raise ValueError(f"HANNA Sol exec-v4 {label} is not canonical")
    return value


def _route_identity() -> dict[str, Any]:
    return {"route_name": "codex-chatgpt-gpt-5.6-sol", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "requested_model": "gpt-5.6-sol", "effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "tool_policy": "tool_free_no_web_no_plan_no_subagents"}


def _validated_prepared(root: Path, row: Mapping[str, Any], authorization_acknowledgement_sha256: str, *, allow_empty_responses: bool = False) -> dict[str, Any]:
    _plain_entry(root, directory=True)
    children = {child.name: child for child in root.iterdir()}
    expected = set(PREPARED_FILES) | ({"responses"} if allow_empty_responses else set())
    if set(children) != expected:
        raise ValueError("HANNA Sol exec-v4 prepared root inventory contains missing, extra, or unsafe artifacts")
    for name, path in children.items():
        _plain_entry(path, directory=name == "responses")
    if allow_empty_responses and any((root / "responses").iterdir()):
        raise ValueError("HANNA Sol exec-v4 callback-time responses residue is not empty")
    prepared = _read_json(root / "prepared.json", "preparation")
    if (prepared.get("format_version") != 1 or prepared.get("study_id") != STUDY_ID or prepared.get("kind") != "replacement_sol_preparation"
            or prepared.get("cell_id") != row["cell_id"] or prepared.get("schedule_sha256") != SCHEDULE_SHA256
            or prepared.get("v3_executor_sha256") != EXEC_V3_SHA256 or prepared.get("route_status") != "SOL_REPLACEMENT_PREPARED_NO_CONTACT"
            or prepared.get("replacement_row") != dict(row) or prepared.get("provider_calls_made") != 0 or prepared.get("process_launches") != 0):
        raise ValueError("HANNA Sol exec-v4 preparation binding drifted")
    disclosure = _read_json(root / "disclosure.json", "disclosure")
    authorization = _read_json(root / "authorization-acknowledgement.json", "authorization")
    proof = _read_json(root / "zero-charge-route-proof.json", "route proof")
    if (disclosure.get("format_version") != 1 or disclosure.get("study_id") != STUDY_ID or disclosure.get("kind") != "local_first_exact_outbound_disclosure"
            or disclosure.get("cell_id") != row["cell_id"] or disclosure.get("replacement_for_terminal_cell_id") != row["replacement_for_terminal_cell_id"]
            or disclosure.get("matched_grok_cell_id") != row["matched_grok_cell_id"] or disclosure.get("provider_calls_made") != 0
            or disclosure.get("destination") != "openai_codex_chatgpt_subscription" or disclosure.get("route_identity") != _route_identity()
            or disclosure.get("process_launches") != 0 or any(disclosure.get(key) is not False for key in ("tools_enabled", "web_search_enabled", "subagents_enabled"))
            or disclosure.get("task_payload_sha256") != prepared.get("request_sha256") or disclosure.get("response_schema_sha256") != prepared.get("response_schema_sha256")
            or prepared.get("disclosure_sha256") != _sha(_canonical(disclosure))):
        raise ValueError("HANNA Sol exec-v4 disclosure binding drifted")
    if (authorization.get("format_version") != 1 or authorization.get("study_id") != STUDY_ID or authorization.get("kind") != "caller_authorization_acknowledgement_reference"
            or authorization.get("cell_id") != row["cell_id"] or authorization.get("destination") != "openai_codex_chatgpt_subscription" or authorization.get("acknowledgement_sha256") != authorization_acknowledgement_sha256
            or authorization.get("disclosure_sha256") != _sha(_canonical(disclosure)) or prepared.get("authorization_sha256") != _sha(_canonical(authorization))):
        raise ValueError("HANNA Sol exec-v4 authorization drifted")
    if (proof.get("format_version") != 1 or proof.get("study_id") != STUDY_ID or proof.get("kind") != "route_proof" or proof.get("cell_id") != row["cell_id"]
            or proof.get("status") != "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE" or proof.get("zero_charge_only") is not True
            or proof.get("paid_fallback_forbidden") is not True or proof.get("provider_calls_made") != 0 or proof.get("process_launches") != 0
            or proof.get("route_evidence") != prepared.get("route_evidence") or prepared.get("route_proof_sha256") != _sha(_canonical(proof))):
        raise ValueError("HANNA Sol exec-v4 route proof binding drifted")
    schedule = _schedule()
    destination = Path(str(row["grok_destination_root"]))
    source_task = schedule.stable_bytes(destination / "native-request.bin")
    payload = schedule._json(destination / "outbound-payload.json", "matched Grok payload", canonical_required=False)
    components = payload.get("components")
    if not isinstance(components, dict) or not isinstance(components.get("response_schema"), str):
        raise ValueError("HANNA Sol exec-v4 matched Grok schema is absent")
    source_schema = components["response_schema"].encode("utf-8")
    task, schema = _stable_bytes(root / "matched-grok-task.bin"), _stable_bytes(root / "response-schema.json")
    if (task != source_task or schema != source_schema or _sha(task) != row["task_payload_sha256"]
            or _sha(schema) != row["response_schema_sha256"] or prepared.get("request_sha256") != _sha(task)
            or prepared.get("response_schema_sha256") != _sha(schema)):
        raise ValueError("HANNA Sol exec-v4 prepared task/schema binding drifted")
    return prepared, task, schema


def _record_definite_precontact_residue(root: Path, prepared: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    children = {child.name: child for child in root.iterdir()}
    if set(children) != set(PREPARED_FILES) | {"responses"}:
        raise ValueError("HANNA Sol exec-v4 precontact residue inventory is not safely recoverable")
    for name, path in children.items():
        _plain_entry(path, directory=name == "responses")
    responses = root / "responses"
    if any(responses.iterdir()) or any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json", PRECONTACT_FAILURE)):
        raise ValueError("HANNA Sol exec-v4 precontact residue is not a provably empty zero-launch runner directory")
    failure = {"format_version": 1, "study_id": STUDY_ID, "kind": "definite_precontact_runner_residue", "cell_id": cell_id,
               "prepared_sha256": _sha(_canonical(prepared)), "provider_calls_made": 0, "process_launches": 0,
               "owned_empty_residue_directory": "responses", "retry_policy": "fresh_output_root_required_no_in_place_retry"}
    _write_new(root / PRECONTACT_FAILURE, _canonical(failure))
    return failure


def _artifact(root: Path, value: Any, label: str) -> bytes:
    if not isinstance(value, Mapping) or not isinstance(value.get("path"), str) or not isinstance(value.get("bytes"), int) or not isinstance(value.get("sha256"), str):
        raise ValueError(f"HANNA Sol exec-v4 {label} artifact reference is malformed")
    relative = Path(value["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"HANNA Sol exec-v4 {label} artifact path is unsafe")
    raw = _stable_bytes(root / relative)
    if len(raw) != value["bytes"] or _sha(raw) != value["sha256"]:
        raise ValueError(f"HANNA Sol exec-v4 {label} artifact bytes drifted")
    return raw


def _finalize_v4(*, v3: ModuleType, root: Path, row: Mapping[str, Any], prepared: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], content: str, record: Mapping[str, Any]) -> dict[str, Any]:
    artifacts = record.get("provider_artifacts")
    if not isinstance(artifacts, Mapping) or list(record.get("command", [])) != v3._expected_codex_command(route["codex_command"][0], root):
        raise ValueError("HANNA Sol exec-v4 Codex command/artifact binding drifted")
    events = _artifact(root, artifacts.get("codex_events"), "Codex events")
    stderr = _artifact(root, artifacts.get("codex_stderr"), "Codex stderr")
    labels = v3._strict_stderr_labels(stderr)
    projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
    final = _stable_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
    if content.encode("utf-8") != final or projection["completed_agent_message_text"].encode("utf-8") != final:
        raise ValueError("HANNA Sol exec-v4 final response association drifted")
    try:
        final_value = json.loads(final.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA Sol exec-v4 final response is not strict JSON") from error
    if not isinstance(final_value, dict):
        raise ValueError("HANNA Sol exec-v4 final response must be an object")
    thread_id = projection.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id or not isinstance(projection.get("usage"), dict):
        raise ValueError("HANNA Sol exec-v4 lifecycle projection is incomplete")
    if labels["session_id"] is not None and labels["session_id"] != thread_id:
        raise ValueError("HANNA Sol exec-v4 stderr/session association drifted")
    effective = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "stderr_label_evidence": labels, "provider_attested": False, "codex_cli_version": route["codex_cli_version"], "codex_command_identity": route["codex_command_identity"], "codex_adapter_sha256": v3.CODEX_ADAPTER_SHA256, "capture_jsonl_events": True, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "event_projection": projection}
    identity = {"provider": "openai_codex", "route_name": v3.SOL_ROUTE_NAME, "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested", "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v4", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}", "session_id": f"local-codex-thread-session:{labels['session_id'] or thread_id}"}
    receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "codex_local_lifecycle_receipt", "cell_id": row["cell_id"], "replacement_for_terminal_cell_id": row["replacement_for_terminal_cell_id"], "original_item_id": row["original_item_id"], "replacement_item_id": row["item_id"], "matched_grok_cell_id": row["matched_grok_cell_id"], "native_contact_proven": False, "process_launches": 1, "local_codex_thread_lifecycle_proven": True, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": _sha(_stable_bytes(root / "matched-grok-task.bin")), "response_schema_sha256": _sha(_stable_bytes(root / "response-schema.json")), "raw_events_sha256": _sha(events), "raw_stderr_sha256": _sha(stderr), "final_response_sha256": _sha(final), "route_evidence": evidence, "effective_settings_sha256": _sha(_canonical(effective)), "launch_intent_sha256": _sha(_stable_bytes(root / "launch-intent.json")), "identity": identity, "usage": projection["usage"]}
    _write_new(root / "raw-codex-events.bin", events); _write_new(root / "raw-codex-final-response.bin", final); _write_new(root / "codex-record.json", _canonical(dict(record))); _write_new(root / "effective-settings.json", _canonical(effective)); _write_new(root / "execution-receipt.json", _canonical(receipt))
    return {"cell_id": row["cell_id"], "state": "local_codex_lifecycle_received_native_contact_unproven", "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "identity": identity}


def prepare_only(*, output_root: Path, cell_id: str, queue_root: Path, authorization_acknowledgement_sha256: str,
                 broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_acknowledgement_sha256):
        raise ValueError("HANNA Sol exec-v4 authorization acknowledgement must be lowercase SHA-256")
    row, v3 = _row(cell_id), _v3()
    route, evidence = v3.validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
    task = Path(row["grok_destination_root"]) / "native-request.bin"
    payload = _read_json(Path(row["grok_destination_root"]) / "outbound-payload.json", "matched Grok payload", canonical_required=False)
    components = payload["components"]
    task_raw, schema_raw = task.read_bytes(), components["response_schema"].encode("utf-8")
    if _sha(task_raw) != row["task_payload_sha256"] or _sha(schema_raw) != row["response_schema_sha256"]:
        raise ValueError("HANNA Sol exec-v4 matched Grok prompt/schema drifted")
    root = Path(output_root) / cell_id
    root.mkdir(parents=True, exist_ok=False)
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": cell_id,
                  "replacement_for_terminal_cell_id": row["replacement_for_terminal_cell_id"], "matched_grok_cell_id": row["matched_grok_cell_id"],
                  "route_identity": _route_identity(), "destination": route["destination"], "task_payload_sha256": _sha(task_raw),
                  "response_schema_sha256": _sha(schema_raw), "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False,
                  "provider_calls_made": 0, "process_launches": 0}
    authorization = {"format_version": 1, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "cell_id": cell_id,
                     "acknowledgement_sha256": authorization_acknowledgement_sha256, "disclosure_sha256": _sha(_canonical(disclosure)), "destination": route["destination"]}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "route_proof", "cell_id": cell_id,
             "status": "CURRENT_BROKER_VALIDATED_ZERO_CHARGE_SUBSCRIPTION_ROUTE", "route_evidence": evidence,
             "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "replacement_sol_preparation", "cell_id": cell_id,
                "route_status": "SOL_REPLACEMENT_PREPARED_NO_CONTACT", "replacement_row": row,
                "schedule_sha256": SCHEDULE_SHA256, "v3_executor_sha256": EXEC_V3_SHA256, "route_evidence": evidence,
                "request_sha256": _sha(task_raw), "response_schema_sha256": _sha(schema_raw), "provider_calls_made": 0, "process_launches": 0,
                "disclosure_sha256": _sha(_canonical(disclosure)), "authorization_sha256": _sha(_canonical(authorization)), "route_proof_sha256": _sha(_canonical(proof)),
                "executable": route["codex_command"][0], "requested": {"model": "gpt-5.6-sol", "reasoning_effort": "high"}, "capture_jsonl_events": True}
    _write_new(root / "matched-grok-task.bin", task_raw)
    _write_new(root / "response-schema.json", schema_raw)
    _write_new(root / "disclosure.json", _canonical(disclosure))
    _write_new(root / "authorization-acknowledgement.json", _canonical(authorization))
    _write_new(root / "zero-charge-route-proof.json", _canonical(proof))
    _write_new(root / "prepared.json", _canonical(prepared))
    return {"cell_id": cell_id, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0}


def execute_sol(*, output_root: Path, cell_id: str, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool,
                broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., tuple[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("HANNA Sol exec-v4 requires explicit allow_remote=True")
    row, v3, root = _row(cell_id), _v3(), Path(output_root) / cell_id
    if (root / PRECONTACT_FAILURE).exists():
        raise ValueError("HANNA Sol exec-v4 precontact root is preserved; retry requires a fresh output root")
    if any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json")):
        raise ValueError("HANNA Sol exec-v4 refuses to resend a replacement after any launch state")
    prepared, task_bytes, schema_bytes = _validated_prepared(root, row, authorization_acknowledgement_sha256)
    route, evidence = v3.validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
    if (evidence != prepared.get("route_evidence") or prepared.get("executable") != route["codex_command"][0]
            or prepared.get("requested") != {"model": "gpt-5.6-sol", "reasoning_effort": "high"}
            or prepared.get("capture_jsonl_events") is not True):
        raise ValueError("HANNA Sol exec-v4 live route evidence is stale")
    launches = 0
    def before_provider_attempt() -> None:
        nonlocal launches
        if launches:
            raise ValueError("HANNA Sol exec-v4 provider launch callback repeated")
        fresh_route, fresh_evidence = v3.validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
        if fresh_route != route or fresh_evidence != evidence:
            raise ValueError("HANNA Sol exec-v4 route drifted adjacent to launch")
        fresh_prepared, fresh_task, fresh_schema = _validated_prepared(root, row, authorization_acknowledgement_sha256, allow_empty_responses=True)
        if fresh_prepared != prepared or fresh_task != task_bytes or fresh_schema != schema_bytes:
            raise ValueError("HANNA Sol exec-v4 prepared bytes drifted adjacent to launch")
        intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": cell_id, "prepared_sha256": _sha(_canonical(prepared)), "native_contact_proven": False}
        _write_new(root / "launch-intent.json", _canonical(intent))
        if _read_json(root / "launch-intent.json", "launch intent") != intent:
            raise ValueError("HANNA Sol exec-v4 launch intent binding drifted")
        launches += 1
    invoke = call_codex or v3._load_call_codex()
    try:
        content, record = invoke(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high", prompt=task_bytes.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json", batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, before_provider_attempt=before_provider_attempt, capture_jsonl_events=True)
    except BaseException as error:
        if launches:
            result = {"format_version": 1, "study_id": STUDY_ID, "kind": "native_exec_result", "cell_id": cell_id, "state": "reconcile_required_after_process_launch", "process_launches": 1, "native_contact_proven": False, "error_type": type(error).__name__}
            _write_new(root / "result.json", _canonical(result))
            return result
        failure = _record_definite_precontact_residue(root, prepared, cell_id)
        return {"cell_id": cell_id, "state": "pending_precontact_fresh_root_required", "process_launches": 0, "native_contact_proven": False, "precontact_failure_sha256": _sha(_canonical(failure))}
    if launches != 1 or not isinstance(content, str):
        return {"cell_id": cell_id, "state": "reconcile_required_after_process_launch", "process_launches": launches, "native_contact_proven": False}
    try:
        lifecycle = _finalize_v4(v3=v3, root=root, row=row, prepared=prepared, route=route, evidence=evidence, content=content, record=record)
    except BaseException as error:
        result = {"format_version": 1, "study_id": STUDY_ID, "kind": "native_exec_result", "cell_id": cell_id, "state": "reconcile_required_after_process_launch", "process_launches": 1, "native_contact_proven": False, "error_type": type(error).__name__}
        _write_new(root / "result.json", _canonical(result)); return result
    return {key: lifecycle[key] for key in ("cell_id", "state", "process_launches", "native_contact_proven", "native_endpoint_contact_cardinality")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare-only", action="store_true"); mode.add_argument("--execute-one-sol", action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--output-root", required=True, type=Path); parser.add_argument("--cell-id", required=True); parser.add_argument("--queue-root", required=True, type=Path); parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    args = parser.parse_args(argv); common = {"output_root": args.output_root, "cell_id": args.cell_id, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare_only:
        if args.allow_remote: parser.error("--prepare-only forbids --allow-remote")
        result = prepare_only(**common)
    else:
        if not args.allow_remote: parser.error("execution requires --allow-remote")
        result = execute_sol(**common, allow_remote=True)
    print(_canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__":
    raise SystemExit(main())
