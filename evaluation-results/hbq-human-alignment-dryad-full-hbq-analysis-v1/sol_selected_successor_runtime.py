"""Prospective Sol launcher that preserves process completion evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
BASE = ROOT.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
BASE_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
RUNNER = REPOSITORY / "src" / "hbqrs" / "runner.py"
RUNNER_SHA256 = "3af6dd86088fddb91c2979ed6ddef00efb3da767e959972f8ee1ee0c1ab034f6"
CAPTURE = REPOSITORY / "src" / "hbqrs" / "sol_process_capture.py"
CAPTURE_SHA256 = "d93a24580b1b492ea116514ba768bb7f7dc5a8e386c925720b434ce94c4d9cb7"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _verify() -> None:
    for path, expected in ((BASE, BASE_SHA256), (RUNNER, RUNNER_SHA256), (CAPTURE, CAPTURE_SHA256)):
        _require(_sha(path.read_bytes()) == expected, "selected Sol runtime source differs")


def _load(path: Path, expected: str, name: str) -> Any:
    raw = path.read_bytes()
    _require(_sha(raw) == expected, f"{name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"{name} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{name} changed during load")
    return module


def _base() -> Any:
    _verify()
    name = f"_dryad_selected_sol_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, BASE)
    _require(spec is not None and spec.loader is not None, "selected Sol lifecycle cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    module.RUNNER_SHA256 = RUNNER_SHA256
    return module


def _labels(raw: bytes) -> tuple[dict[str, str | None], bool]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("selected Sol stderr is not valid UTF-8") from error
    labels = {"model": "model", "provider": "provider", "reasoning effort": "reasoning_effort", "session id": "session_id"}
    values: dict[str, str | None] = {value: None for value in labels.values()}
    warning = False
    for line in text.splitlines():
        if line.strip() == "user":
            break
        if "ERROR:" in line.upper():
            warning = True
        if ":" not in line:
            continue
        label, value = line.split(":", 1)
        key = labels.get(label.strip().lower())
        if key is None:
            continue
        value = value.strip()
        _require(value and values[key] is None, "selected Sol stderr identity label is malformed")
        values[key] = value
    expected = {"model": "gpt-5.6-sol", "provider": "openai", "reasoning_effort": "high"}
    for key, expected_value in expected.items():
        _require(values[key] in (None, expected_value), "selected Sol stderr identity label conflicts with the request")
    return values, warning


def _receipt(path: Path, message: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("selected Sol process completion receipt is malformed") from error
    final = value.get("final_message") if isinstance(value, Mapping) else None
    _require(isinstance(value, Mapping) and value.get("format_version") == 1 and value.get("state") == "completed"
             and value.get("exit_code") == 0 and isinstance(final, Mapping) and final.get("exists") is True
             and final.get("bytes") == len(message.read_bytes()) and final.get("sha256") == _sha(message.read_bytes()),
             "selected Sol process completion is not a proven zero exit")
    return dict(value)


def _record(module: Any, command: list[str], root: Path, batch: int, receipt: Mapping[str, Any], *, warning: bool) -> tuple[str, dict[str, Any]]:
    message = root / "responses" / f"batch-{batch:04d}.attempt-0001.message.json"
    events = root / "responses" / f"batch-{batch:04d}.attempt-0001.events.jsonl"
    stderr = root / "responses" / f"batch-{batch:04d}.attempt-0001.stderr.bin"
    final = message.read_bytes()
    labels, has_warning = _labels(stderr.read_bytes())
    _require(has_warning is warning, "selected Sol stderr warning classification differs")
    projection = module._codex_event_projection(events.read_bytes(), module._load_parse_codex_events())
    _require(projection.get("completed_agent_message_text", "").encode("utf-8") == final,
             "selected Sol final message does not match the tool-free lifecycle")
    thread_id = projection.get("thread_id")
    _require(isinstance(thread_id, str) and thread_id
             and labels["session_id"] in (None, thread_id), "selected Sol lifecycle identity differs")
    try:
        content = final.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("selected Sol final message is not valid UTF-8") from error
    return content, {
        "command": command,
        "reported": labels,
        "provider_artifacts": {
            "codex_events": {"path": events.relative_to(root).as_posix(), "bytes": len(events.read_bytes()), "sha256": _sha(events.read_bytes())},
            "codex_stderr": {"path": stderr.relative_to(root).as_posix(), "bytes": len(stderr.read_bytes()), "sha256": _sha(stderr.read_bytes())},
        },
        "completion": dict(receipt),
        "completion_class": "completed_with_wrapper_warning" if warning else "completed",
        "native_thread_id": thread_id,
    }


def replay_completion(*, output_dir: Path, batch_number: int, record: Mapping[str, Any]) -> str:
    """Reparse retained lifecycle evidence without launching another child process."""
    _verify()
    root = Path(output_dir).resolve(); batch = int(batch_number)
    message = root / "responses" / f"batch-{batch:04d}.attempt-0001.message.json"
    events = root / "responses" / f"batch-{batch:04d}.attempt-0001.events.jsonl"
    stderr = root / "responses" / f"batch-{batch:04d}.attempt-0001.stderr.bin"
    final = message.read_bytes(); event_bytes = events.read_bytes(); stderr_bytes = stderr.read_bytes()
    labels, warning = _labels(stderr_bytes)
    module = _base()
    projection = module._codex_event_projection(event_bytes, module._load_parse_codex_events())
    thread_id = projection.get("thread_id")
    _require(isinstance(thread_id, str) and thread_id and projection.get("completed_agent_message_text", "").encode("utf-8") == final
             and labels["session_id"] in (None, thread_id)
             and record.get("reported") == labels and record.get("native_thread_id") == thread_id
             and record.get("completion_class") == ("completed_with_wrapper_warning" if warning else "completed"),
             "selected Sol retained lifecycle identity differs")
    _verify()
    return thread_id


def call_codex(**kwargs: Any) -> tuple[str, dict[str, Any]]:
    """Launch once and retain completion metadata before V3 parses diagnostics."""
    values = dict(kwargs)
    receipt_root = Path(values.pop("receipt_root")).resolve()
    _require(values.get("attempt_number", 1) == 1, "selected Sol permits one cumulative attempt")
    gate = values.get("before_provider_attempt")
    _require(callable(gate), "selected Sol requires a precontact gate")
    root = Path(values["output_dir"]).resolve()
    batch = values.get("batch_number")
    _require(type(batch) is int and batch >= 1, "selected Sol batch number differs")
    schema = Path(values["response_schema"]).resolve()
    schema.relative_to(root)
    module = _base()
    original_command = module._expected_codex_command

    def command(executable: str, output_root: Path) -> list[str]:
        value = original_command(executable, output_root)
        value[value.index("--output-schema") + 1] = str(schema)
        value[value.index("--output-last-message") + 1] = str(root / "responses" / f"batch-{batch:04d}.attempt-0001.message.json")
        value[-1:-1] = ["--disable", "code_mode"]
        return value

    def stderr_artifact(output_root: Path, raw: bytes) -> dict[str, Any]:
        path = output_root / "responses" / f"batch-{batch:04d}.attempt-0001.stderr.bin"
        with path.open("xb") as output:
            output.write(raw)
        return {"path": path.relative_to(output_root).as_posix(), "bytes": len(raw), "sha256": _sha(raw)}

    def before_contact() -> None:
        _verify()
        gate()

    module._expected_codex_command = command
    module._stderr_artifact = stderr_artifact
    module.subprocess = _load(CAPTURE, CAPTURE_SHA256, "selected Sol capture").facade(
        module.subprocess, receipt_root=receipt_root)
    invoke = module._load_call_codex()
    message = root / "responses" / f"batch-{batch:04d}.attempt-0001.message.json"
    events = root / "responses" / f"batch-{batch:04d}.attempt-0001.events.jsonl"
    stderr = root / "responses" / f"batch-{batch:04d}.attempt-0001.stderr.bin"
    receipt_path = receipt_root / f"{root.name}.json"
    _require(not any(path.exists() for path in (receipt_path, message, events, stderr)),
             "selected Sol attempt artifacts already exist")
    try:
        content, record = invoke(**{**values, "capture_jsonl_events": True, "before_provider_attempt": before_contact})
    except ValueError:
        receipt = _receipt(receipt_path, message)
        result = _record(module, command(values["executable"], root), root, batch, receipt, warning=True)
        _verify()
        return result
    receipt = _receipt(receipt_path, message)
    captured_content, record = _record(module, command(values["executable"], root), root, batch, receipt, warning=False)
    _require(captured_content == content, "selected Sol returned content differs from its final message")
    _verify()
    return content, record
