"""Validate a retained final Sol message when the launcher exit is unknown."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _artifact(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise ValueError(f"{label} is absent") from error


def _expected_command(frozen_runtime: Any, executable: str, native: Path, batch: int, schema: Path) -> list[str]:
    base = frozen_runtime._base()
    command = list(base._expected_codex_command(executable, native))
    _require("--output-schema" in command and "--output-last-message" in command, "frozen Sol command differs")
    command[command.index("--output-schema") + 1] = str(schema)
    command[command.index("--output-last-message") + 1] = str(native / "responses" / f"batch-{batch:04d}.attempt-0001.message.json")
    command[-1:-1] = ["--disable", "code_mode"]
    return command


def validate_completed_unknown_exit(*, slot: Path, request: Mapping[str, Any], frozen_runtime: Any,
                                    route: Mapping[str, Any], source: Mapping[str, Any] | None = None,
                                    expected_record: Mapping[str, Any] | None = None) -> tuple[str, str, dict[str, Any]]:
    """Return retained content and provenance without converting an unknown exit into success."""
    slot = Path(slot).resolve()
    ordinal, batch = request.get("ordinal"), request.get("batch_number")
    _require(type(ordinal) is int and type(batch) is int and ordinal >= 1 and batch >= 1, "unknown-exit request differs")
    native = slot / "native-output"
    prompt, schema_raw = _artifact(native / "payload" / "prompt.txt", "unknown-exit prompt"), _artifact(native / "payload" / "schema.json", "unknown-exit schema")
    _require(_sha(prompt) == request.get("prompt_sha256") and _sha(schema_raw) == request.get("schema_sha256"),
             "unknown-exit request payload differs")
    if source is not None:
        _require(source.get("prompt_sha256") == _sha(prompt) and source.get("schema_sha256") == _sha(schema_raw),
                 "unknown-exit source payload differs")
    message_path = native / "responses" / f"batch-{batch:04d}.attempt-0001.message.json"
    events_path = native / "responses" / f"batch-{batch:04d}.attempt-0001.events.jsonl"
    stderr_path = native / "responses" / f"batch-{batch:04d}.attempt-0001.stderr.bin"
    message, events, stderr = (_artifact(message_path, "unknown-exit final message"), _artifact(events_path, "unknown-exit events"), _artifact(stderr_path, "unknown-exit stderr"))
    receipt = _json(slot / "process-completion" / "native-output.json", "unknown-exit process receipt")
    final = receipt.get("final_message")
    _require(receipt.get("format_version") == 1 and receipt.get("state") == "exception" and receipt.get("exit_code") is None
             and isinstance(final, Mapping) and final.get("exists") is True and final.get("bytes") == len(message)
             and final.get("sha256") == _sha(message) and receipt.get("stdout") == {"bytes": len(events), "sha256": _sha(events)}
             and receipt.get("stderr") == {"bytes": len(stderr), "sha256": _sha(stderr)},
             "unknown-exit receipt is not a retained completed message")
    try:
        content = message.decode("utf-8")
        response = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        schema = json.loads(schema_raw.decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        Draft202012Validator(schema).validate(response)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError) as error:
        raise ValueError("unknown-exit final response schema differs") from error
    ids = request.get("question_ids")
    verdicts = response.get("verdicts") if isinstance(response, Mapping) else None
    _require(isinstance(ids, list) and all(isinstance(item, str) for item in ids) and isinstance(verdicts, list)
             and all(isinstance(item, Mapping) for item in verdicts)
             and [item.get("question_id") for item in verdicts] == ids and len(ids) == len(set(ids)),
             "unknown-exit verdict identities differ")
    labels, _warning = frozen_runtime._labels(stderr)
    base = frozen_runtime._base()
    try:
        event_rows = [json.loads(line) for line in events.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("unknown-exit lifecycle differs") from error
    _require(len(event_rows) == 4 and [item.get("type") for item in event_rows] == ["thread.started", "turn.started", "item.completed", "turn.completed"]
             and isinstance(event_rows[2].get("item"), Mapping) and event_rows[2]["item"].get("type") == "agent_message"
             and event_rows[2]["item"].get("text") == content, "unknown-exit lifecycle is not one completed tool-free turn")
    projection = base._codex_event_projection(events, base._load_parse_codex_events())
    thread_id = projection.get("thread_id")
    _require(isinstance(thread_id, str) and thread_id and projection.get("completed_agent_message_text", "").encode("utf-8") == message
             and labels.get("session_id") in (None, thread_id), "unknown-exit lifecycle differs")
    executable = route.get("codex_command", [None])[0] if isinstance(route.get("codex_command"), list) else None
    _require(isinstance(executable, str) and executable, "unknown-exit route differs")
    command = _expected_command(frozen_runtime, executable, native, batch, native / "payload" / "schema.json")
    record = {
        "command": command,
        "reported": labels,
        "provider_artifacts": {
            "codex_events": {"path": events_path.relative_to(native).as_posix(), "bytes": len(events), "sha256": _sha(events)},
            "codex_stderr": {"path": stderr_path.relative_to(native).as_posix(), "bytes": len(stderr), "sha256": _sha(stderr)},
        },
        "completion": receipt,
        "completion_class": "completed_with_unknown_exit",
        "native_thread_id": thread_id,
        "process_success_proven": False,
        "provider_attested": False,
        "native_expected_command_sha256": _sha(_canonical(command)),
    }
    if expected_record is not None:
        _require(expected_record.get("ordinal") == ordinal and expected_record.get("thread_id") == thread_id
                 and expected_record.get("process_returncode") is None and expected_record.get("process_success_proven") is False
                 and expected_record.get("source_class") == "unchanged_completed_message_unknown_process_exit"
                 and expected_record.get("derived_response_sha256") == _sha(message), "unknown-exit reconciliation record differs")
        files = expected_record.get("native_files")
        _require(isinstance(files, Mapping), "unknown-exit reconciliation files differ")
        expected_files = {"message": message_path, "events": events_path, "stderr": stderr_path,
                          "completion_receipt": slot / "process-completion" / "native-output.json"}
        for name, path in expected_files.items():
            item = files.get(name)
            _require(isinstance(item, Mapping) and Path(item.get("path", "")).resolve() == path.resolve()
                     and item.get("bytes") == len(path.read_bytes()) and item.get("sha256") == _sha(path.read_bytes()),
                     "unknown-exit reconciliation files differ")
    return content, thread_id, record
