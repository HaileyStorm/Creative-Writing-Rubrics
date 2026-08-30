#!/usr/bin/env python3
"""Pinned HANNA Sol successor that treats absent stderr labels as unknown evidence."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
EXEC_V2_DIR = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v2"
EXEC_V2_PATH = EXEC_V2_DIR / "executor.py"
EXEC_V2_CONTRACT_PATH = EXEC_V2_DIR / "study-contract.json"
EXEC_V2_SHA256 = "2c4629aa22c24f5c9093fd69fb45942ddd2e84bc057a6d01ff01275fa166a92b"
EXEC_V2_CONTRACT_SHA256 = "238a5e26ccbb370b473ee8d48eaebd110dc8bdfe8a208bd18112e91877dfb83d"


def _bootstrap_sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bootstrap_stable_file_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise ValueError(f"HANNA native exec-v3 pinned path is reparsed: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError(f"HANNA native exec-v3 pinned file identity drifted: {absolute}")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError(f"HANNA native exec-v3 pinned file changed during read: {absolute}")
    return raw


def _bootstrap_successor_source() -> bytes:
    raw = _bootstrap_stable_file_bytes(EXEC_V2_PATH)
    contract_raw = _bootstrap_stable_file_bytes(EXEC_V2_CONTRACT_PATH)
    if _bootstrap_sha(raw) != EXEC_V2_SHA256 or _bootstrap_sha(contract_raw) != EXEC_V2_CONTRACT_SHA256:
        raise ValueError("HANNA native exec-v3 predecessor bytes drifted")
    source = raw.decode("utf-8")
    patches = (
        ('STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-exec-v2"',
         'STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3"'),
        ('"transport_identity": "codex_chatgpt_subscription_exec_tool_free_v2"',
         '"transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3"'),
    )
    for old, new in patches:
        if source.count(old) != 1 or new in source:
            raise ValueError("HANNA native exec-v3 exact source patch precondition drifted")
        source = source.replace(old, new, 1)
    if _bootstrap_sha(_bootstrap_stable_file_bytes(EXEC_V2_PATH)) != EXEC_V2_SHA256:
        raise ValueError("HANNA native exec-v3 predecessor changed during exact-byte load")
    return source.encode("utf-8")


_v3_outer_module_name = __name__
__name__ = "_hanna_v4_native_subscription_exec_v3_runtime"
exec(compile(_bootstrap_successor_source(), str(Path(__file__).resolve()), "exec"), globals())
__name__ = _v3_outer_module_name
_V2_VALIDATE_COMPLETED_INVENTORY = _validate_completed_inventory
_V2_VERIFY_PREDECESSOR_RECEIPT = verify_predecessor_receipt

# The inherited v2 executor pins v1; v3 separately proves that its entire localized base is v2.
EXEC_V2_DIR = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v2"
EXEC_V2_PATH = EXEC_V2_DIR / "executor.py"
EXEC_V2_CONTRACT_PATH = EXEC_V2_DIR / "study-contract.json"
EXEC_V2_SHA256 = "2c4629aa22c24f5c9093fd69fb45942ddd2e84bc057a6d01ff01275fa166a92b"
EXEC_V2_CONTRACT_SHA256 = "238a5e26ccbb370b473ee8d48eaebd110dc8bdfe8a208bd18112e91877dfb83d"


def _stderr_artifact(root: Path, raw: bytes) -> dict[str, Any]:
    path = root / "raw-codex-stderr.bin"
    if path.exists():
        raise ValueError("HANNA native exec-v3 stderr artifact path already exists")
    _write_new(_load_predecessor(), path, raw)
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": _sha(raw)}


def _strict_stderr_labels(raw: bytes) -> dict[str, str | None]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("HANNA native exec-v3 Codex stderr is not valid UTF-8") from error
    labels = {"model": "model", "provider": "provider", "reasoning effort": "reasoning_effort", "session id": "session_id"}
    values: dict[str, str | None] = {value: None for value in labels.values()}
    for line in text.splitlines():
        if line.strip() == "user":
            break
        if "ERROR:" in line.upper():
            raise ValueError("HANNA native exec-v3 Codex stderr contains an error marker")
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        key = labels.get(label.strip().lower())
        if key is None:
            continue
        value = value.strip()
        if not value or values[key] is not None:
            raise ValueError("HANNA native exec-v3 Codex stderr has a malformed or duplicate identity label")
        values[key] = value
    expected = {"model": "gpt-5.6-sol", "provider": "openai", "reasoning_effort": "high"}
    for key, expected_value in expected.items():
        if values[key] is not None and values[key] != expected_value:
            raise ValueError("HANNA native exec-v3 Codex stderr identity label conflicts with the request")
    return values


def _load_call_codex() -> Callable[..., tuple[str, dict[str, Any]]]:
    """Return the v3-only launcher; it preserves raw stderr without treating absence as attestation."""
    raw = _stable_file_bytes(RUNNER_PATH)
    if _sha(raw) != RUNNER_SHA256:
        raise ValueError("HANNA native exec-v3 pinned runner bytes drifted")
    source_root = str(REPOSITORY / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        importlib.import_module("hbqrs")
        module = ModuleType("hbqrs._hanna_native_exec_v3_pinned_runner")
        module.__file__ = str(RUNNER_PATH)
        module.__package__ = "hbqrs"
        exec(compile(raw, str(RUNNER_PATH), "exec"), module.__dict__)
    finally:
        if inserted:
            sys.path.remove(source_root)
    if _sha(_stable_file_bytes(RUNNER_PATH)) != RUNNER_SHA256:
        raise ValueError("HANNA native exec-v3 runner changed during exact-byte load")

    def invoke(*, executable: str, model: str, reasoning: str, prompt: str, output_dir: Path,
               response_schema: Path, batch_number: int, timeout: float, attempt_number: int = 1,
               before_provider_attempt: Callable[[], None] | None = None,
               capture_jsonl_events: bool = False) -> tuple[str, dict[str, Any]]:
        if not capture_jsonl_events or model != "gpt-5.6-sol" or reasoning != "high":
            raise ValueError("HANNA native exec-v3 requires the pinned Sol JSONL lifecycle")
        expected = _expected_codex_command(executable, output_dir)
        command = [*expected[:-1], "-"]
        message = output_dir / "responses" / f"batch-{batch_number:04d}.attempt-{attempt_number:04d}.message.json"
        events = output_dir / "responses" / f"batch-{batch_number:04d}.attempt-{attempt_number:04d}.events.jsonl"
        if message.exists() or events.exists() or (output_dir / "raw-codex-stderr.bin").exists():
            raise ValueError("HANNA native exec-v3 attempt artifact path already exists")
        message.parent.mkdir(parents=True, exist_ok=True)
        if before_provider_attempt is not None:
            before_provider_attempt()
        try:
            completed = subprocess.run(command, input=prompt.encode("utf-8"), capture_output=True,
                                       timeout=timeout, check=False, env=module._codex_environment())
        except (OSError, subprocess.TimeoutExpired) as error:
            partial_stdout = getattr(error, "stdout", None)
            partial_stderr = getattr(error, "stderr", None)
            stdout = partial_stdout if isinstance(partial_stdout, bytes) else (partial_stdout or "").encode("utf-8")
            stderr = partial_stderr if isinstance(partial_stderr, bytes) else (partial_stderr or "").encode("utf-8")
            _write_new(_load_predecessor(), events, stdout)
            _stderr_artifact(output_dir, stderr)
            raise ValueError("HANNA native exec-v3 Codex process failed after launch") from error
        stdout = completed.stdout if isinstance(completed.stdout, bytes) else (completed.stdout or "").encode("utf-8")
        stderr = completed.stderr if isinstance(completed.stderr, bytes) else (completed.stderr or "").encode("utf-8")
        _write_new(_load_predecessor(), events, stdout)
        stderr_artifact = _stderr_artifact(output_dir, stderr)
        labels = _strict_stderr_labels(stderr)
        if completed.returncode != 0:
            raise ValueError("HANNA native exec-v3 Codex process returned nonzero after launch")
        if not message.is_file():
            raise ValueError("HANNA native exec-v3 Codex omitted its final response")
        content = _stable_file_bytes(message).decode("utf-8")
        return content, {
            "command": expected,
            "reported": labels,
            "provider_artifacts": {
                "codex_events": {"path": events.relative_to(output_dir).as_posix(), "bytes": len(stdout), "sha256": _sha(stdout)},
                "codex_stderr": stderr_artifact,
            },
        }
    return invoke


def _finalize_sol(*, predecessor: ModuleType, root: Path, cell_id: str, task: bytes, schema: bytes,
                  route: Mapping[str, Any], evidence: Mapping[str, Any], launches: int,
                  content: str, record: Mapping[str, Any], parse_events: Callable[[bytes], dict[str, Any]],
                  prepared_sha256: str) -> dict[str, Any]:
    stderr = _artifact_bytes(predecessor, root, record.get("provider_artifacts", {}).get("codex_stderr"), "Codex stderr")
    reported = _strict_stderr_labels(stderr)
    events = _artifact_bytes(predecessor, root, record.get("provider_artifacts", {}).get("codex_events"), "Codex JSONL events")
    if launches != 1 or not isinstance(content, str) or list(record.get("command", [])) != _expected_codex_command(route["codex_command"][0], root):
        raise ValueError("HANNA native exec-v3 Codex runner did not bind exactly one tool-free process launch")
    projection = _codex_event_projection(events, parse_events)
    thread_id, usage = projection.get("thread_id"), projection.get("usage")
    if not isinstance(thread_id, str) or not thread_id or not isinstance(usage, dict):
        raise ValueError("HANNA native exec-v3 Codex event projection is incomplete")
    if reported["session_id"] is not None and reported["session_id"] != thread_id:
        raise ValueError("HANNA native exec-v3 Codex thread/session identity is misassociated")
    final_response = predecessor._stable_read_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
    if content.encode("utf-8") != final_response or projection["completed_agent_message_text"].encode("utf-8") != final_response:
        raise ValueError("HANNA native exec-v3 Codex final response bytes drifted")
    try:
        final_value = json.loads(final_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA native exec-v3 Codex final response is not strict JSON") from error
    if not isinstance(final_value, dict):
        raise ValueError("HANNA native exec-v3 Codex final response must be one JSON object")
    effective = {
        "requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high",
        "stderr_label_evidence": reported, "provider_attested": False,
        "codex_cli_version": route["codex_cli_version"], "codex_command_identity": route["codex_command_identity"],
        "codex_adapter_sha256": CODEX_ADAPTER_SHA256, "capture_jsonl_events": True,
        "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "event_projection": projection,
    }
    identity = {
        "provider": "openai_codex", "route_name": SOL_ROUTE_NAME, "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None,
        "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested",
        "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
        "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}",
        "session_id": f"local-codex-thread-session:{reported['session_id'] or thread_id}",
    }
    receipt = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "codex_local_lifecycle_receipt", "cell_id": cell_id,
        "native_contact_proven": False, "process_launches": 1, "local_codex_thread_lifecycle_proven": True,
        "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven",
        "request_sha256": _sha(task), "response_schema_sha256": _sha(schema), "raw_events_sha256": _sha(events),
        "raw_stderr_sha256": _sha(stderr), "final_response_sha256": _sha(final_response), "route_evidence": evidence,
        "effective_settings_sha256": _sha(_canonical(effective)),
        "launch_intent_sha256": _launch_intent_sha256(predecessor, root, cell_id=cell_id, prepared_sha256=prepared_sha256),
        "identity": identity, "usage": usage,
    }
    _write_new(predecessor, root / "raw-codex-events.bin", events)
    _write_new(predecessor, root / "raw-codex-final-response.bin", final_response)
    _write_new(predecessor, root / "codex-record.json", _canonical(dict(record)))
    _write_new(predecessor, root / "effective-settings.json", _canonical(effective))
    _write_new(predecessor, root / "execution-receipt.json", _canonical(receipt))
    return {"cell_id": cell_id, "state": "local_codex_lifecycle_received_native_contact_unproven", "process_launches": 1,
            "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven", "request_bytes": task,
            "raw_response_bytes": final_response, "raw_events_bytes": events, "raw_stderr_bytes": stderr,
            "effective_settings": effective, "identity": identity}


def _validate_completed_inventory(root: Path, *, is_sol: bool) -> None:
    if not is_sol:
        _V2_VALIDATE_COMPLETED_INVENTORY(root, is_sol=False)
        return
    expected_root = set(PREPARED_FILES) | {
        "raw-codex-events.bin", "raw-codex-final-response.bin", "raw-codex-stderr.bin", "codex-record.json",
        "launch-intent.json", "effective-settings.json", "execution-receipt.json", "responses",
    }
    children = {child.name: child for child in root.iterdir()}
    if set(children) != expected_root:
        raise ValueError("HANNA native exec-v3 completed Sol root inventory contains missing or extra artifacts")
    if any(not _plain_entry(child, directory=name == "responses") for name, child in children.items()):
        raise ValueError("HANNA native exec-v3 completed Sol root inventory contains unsafe entries")
    responses = children["responses"]
    expected_responses = {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"}
    response_children = {child.name: child for child in responses.iterdir()}
    if set(response_children) != expected_responses or any(not _plain_entry(child, directory=False) for child in response_children.values()):
        raise ValueError("HANNA native exec-v3 completed Sol response inventory contains missing, extra, or unsafe artifacts")


def verify_predecessor_receipt(event: Mapping[str, Any], *, execution_root: Path, queue_root: Path,
                               frozen_successor_path: Path, hanna_csv_path: Path,
                               broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    """Verify v3's local lifecycle bytes without promoting them to endpoint evidence."""
    cell, identity = event.get("cell"), event.get("identity")
    if not isinstance(cell, Mapping) or cell.get("route_name") != "sol_validation" or not isinstance(identity, Mapping):
        raise ValueError("HANNA native exec-v3 receipt verifier requires one Sol predecessor cell")
    predecessor = _load_predecessor()
    root = Path(execution_root) / str(cell["cell_id"])
    prepared, parent_payload, task, schema, fresh_row = _read_prepared(
        predecessor, root, cell_id=str(cell["cell_id"]), frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path), require_pristine=False,
    )
    if dict(cell) != fresh_row or prepared.get("route_status") != "SOL_PREPARED_NO_CONTACT":
        raise ValueError("HANNA native exec-v3 caller cell or Sol preparation drifted")
    _validate_completed_inventory(root, is_sol=True)
    receipt = predecessor._read_canonical(root / "execution-receipt.json", label="Codex execution receipt")
    record = predecessor._read_canonical(root / "codex-record.json", label="Codex provider record")
    effective = predecessor._read_canonical(root / "effective-settings.json", label="Codex effective settings")
    route, evidence = validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
    if evidence != prepared.get("route_evidence") or evidence != receipt.get("route_evidence"):
        raise ValueError("HANNA native exec-v3 receipt route evidence is stale")
    launch_intent_sha256 = _launch_intent_sha256(predecessor, root, cell_id=str(cell["cell_id"]), prepared_sha256=_sha(_canonical(prepared)))
    events = _artifact_bytes(predecessor, root, record.get("provider_artifacts", {}).get("codex_events"), "Codex JSONL events")
    stderr = _artifact_bytes(predecessor, root, record.get("provider_artifacts", {}).get("codex_stderr"), "Codex stderr")
    labels = _strict_stderr_labels(stderr)
    projection = _codex_event_projection(events, _load_parse_codex_events())
    final_response = predecessor._stable_read_bytes(root / "raw-codex-final-response.bin")
    response_copy = predecessor._stable_read_bytes(root / "responses" / "batch-0001.attempt-0001.message.json")
    raw_events_copy = predecessor._stable_read_bytes(root / "raw-codex-events.bin")
    if (receipt.get("study_id") != STUDY_ID or receipt.get("kind") != "codex_local_lifecycle_receipt"
            or receipt.get("cell_id") != cell["cell_id"] or receipt.get("native_contact_proven") is not False
            or receipt.get("process_launches") != 1 or receipt.get("local_codex_thread_lifecycle_proven") is not True
            or receipt.get("native_endpoint_contact_cardinality") != "unproven" or receipt.get("internal_retry_cardinality") != "unproven"
            or receipt.get("request_sha256") != _sha(task) or receipt.get("response_schema_sha256") != _sha(schema)
            or receipt.get("launch_intent_sha256") != launch_intent_sha256 or receipt.get("raw_events_sha256") != _sha(events)
            or receipt.get("raw_stderr_sha256") != _sha(stderr) or receipt.get("final_response_sha256") != _sha(final_response)
            or receipt.get("effective_settings_sha256") != _sha(_canonical(effective)) or receipt.get("usage") != projection.get("usage")):
        raise ValueError("HANNA native exec-v3 receipt bindings drifted")
    if raw_events_copy != events or final_response != response_copy or projection["completed_agent_message_text"].encode("utf-8") != final_response:
        raise ValueError("HANNA native exec-v3 raw lifecycle byte copies drifted")
    expected_effective = {
        "requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high",
        "stderr_label_evidence": labels, "provider_attested": False,
        "codex_cli_version": route["codex_cli_version"], "codex_command_identity": route["codex_command_identity"],
        "codex_adapter_sha256": CODEX_ADAPTER_SHA256, "capture_jsonl_events": True,
        "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False,
        "event_projection": projection,
    }
    if (record.get("reported") != labels or record.get("command") != _expected_codex_command(route["codex_command"][0], root)
            or dict(effective) != expected_effective):
        raise ValueError("HANNA native exec-v3 local command or stderr projection drifted")
    thread_id = projection.get("thread_id")
    expected_identity = {
        "provider": "openai_codex", "route_name": SOL_ROUTE_NAME, "requested_model": "gpt-5.6-sol",
        "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None,
        "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested",
        "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
        "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}",
        "session_id": f"local-codex-thread-session:{labels['session_id'] or thread_id}",
    }
    if (not isinstance(thread_id, str) or receipt.get("identity") != expected_identity
            or dict(identity) != expected_identity):
        raise ValueError("HANNA native exec-v3 identity/contact ceiling drifted")
    native_request, outbound = event.get("native_request_bytes"), event.get("outbound_payload")
    try:
        outbound_value = json.loads(outbound.decode("utf-8")) if isinstance(outbound, bytes) else None
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA native exec-v3 predecessor outbound payload is invalid") from error
    if (not isinstance(native_request, bytes) or native_request != task or not isinstance(outbound_value, dict)
            or predecessor.canonical(outbound_value) != parent_payload
            or outbound_value.get("components", {}).get("task_payload", "").encode("utf-8") != task
            or outbound_value.get("components", {}).get("response_schema", "").encode("utf-8") != schema):
        raise ValueError("HANNA native exec-v3 predecessor request/payload association drifted")
    predecessor._validate_effective_settings(event.get("effective_settings"), cell)
    return {"accepted": False, "local_lifecycle_verified": True, "native_endpoint_contact_cardinality": "unproven",
            "reason": "local_codex_thread_events_do_not_attest_native_endpoint_contact_cardinality"}


if _v3_outer_module_name == "__main__":
    raise SystemExit(main())
