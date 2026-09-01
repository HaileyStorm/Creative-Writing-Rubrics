#!/usr/bin/env python3
"""Provider-free Flash-Next fixture contract; native execution is deliberately disabled."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parent
REPOSITORY = PACKAGE.parents[1]
CONTRACT_PATH = PACKAGE / "study-contract.json"
FIXTURE_ENVELOPE = "flash-next-fixture-envelope-v1"
PREPARE_NAME = "prepare.json"
ENVELOPE_SCHEMA = {
    "identity_required_keys": [
        "model",
        "provider",
        "request_id",
        "runtime",
        "session_id",
    ],
    "required_keys": [
        "fixture_only",
        "format_version",
        "identity",
        "output",
        "request_sha256",
        "schema",
    ],
    "schema": FIXTURE_ENVELOPE,
}
PREDECESSOR_PATHS = {
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/adapter.py",
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/study-contract.json",
    "evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/preflight.py",
    "evaluation-results/hbq-supplemental-providers-flash-next-linux-portability-v1/study-contract.json",
}
EVIDENCE_LIMITS = [
    "Fixture subprocess output is not native Linux, provider, model, or endpoint evidence.",
    "Promotion, pairing, and native endpoint contact cardinality remain NO-GO.",
    "A future external Linux run must create a new root and bind native executable, runtime, model, request, session, raw response, and receipt evidence.",
]
FUTURE_LINUX_NATIVE_INVOCATION = {
    "command": [
        "<python3>",
        "<executor.py>",
        "native-run",
        "--prepared-root",
        "<new-external-linux-root>",
        "--cell-id",
        "<frozen-cell-id>",
        "--runner",
        "<verified-native-runner>",
    ],
    "current_implementation": "disabled; metadata-only",
    "required_before_use": [
        "fresh local-first disclosure naming the remote destination and exact outbound payload",
        "fresh no-liability route evidence",
        "native executable and runtime hashes",
        "provider/model/request/session identity",
        "immutable raw response and receipt bindings",
    ],
}


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_sha256(value: Any) -> str:
    return sha256(canonical(value))


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _assert_plain_path(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if _is_reparse(cursor):
            raise ValueError(f"{label} crosses a symlink or reparse point")
    return absolute


def _safe_bytes(path: Path, label: str) -> bytes:
    absolute = _assert_plain_path(path, label)
    if not absolute.is_file():
        raise ValueError(f"{label} is not a regular file")
    before = os.stat(absolute, follow_symlinks=False)
    value = absolute.read_bytes()
    after = os.stat(absolute, follow_symlinks=False)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise ValueError(f"{label} changed while being read")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = item
    return result


def _json_bytes(
    value: bytes, label: str, *, canonical_required: bool = False
) -> dict[str, Any]:
    try:
        result = json.loads(value.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(result, dict):
        raise TypeError(f"{label} must be a JSON object")
    if canonical_required and canonical(result) != value:
        raise ValueError(f"{label} is not canonical JSON")
    return result


def _read_json(
    path: Path, label: str, *, canonical_required: bool = False
) -> dict[str, Any]:
    return _json_bytes(
        _safe_bytes(path, label), label, canonical_required=canonical_required
    )


def _write_exclusive(path: Path, content: bytes) -> None:
    _assert_plain_path(path.parent, "publication parent")
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError(f"Immutable artifact already exists: {path.name}") from None
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        raise


def _decode_asset(record: Any, label: str) -> bytes:
    if (
        not isinstance(record, dict)
        or set(record) != {"base64", "bytes", "sha256"}
        or not isinstance(record.get("bytes"), int)
        or record["bytes"] < 1
        or not _is_sha256(record.get("sha256"))
    ):
        raise ValueError(f"{label} binding shape drifted")
    try:
        value = base64.b64decode(record["base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} base64 drifted") from error
    if not value or len(value) != record["bytes"] or sha256(value) != record["sha256"]:
        raise ValueError(f"{label} bytes drifted")
    return value


def _validate_predecessors(records: Any) -> None:
    if not isinstance(records, list) or len(records) != len(PREDECESSOR_PATHS):
        raise ValueError("Predecessor bindings drifted")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"path", "bytes", "sha256"}:
            raise ValueError("Predecessor binding shape drifted")
        path = record["path"]
        if (
            not isinstance(path, str)
            or not path
            or path.startswith("/")
            or "\\" in path
            or ".." in Path(path).parts
            or path in seen
        ):
            raise ValueError("Predecessor path drifted")
        seen.add(path)
        if (
            not isinstance(record["bytes"], int)
            or record["bytes"] < 1
            or not _is_sha256(record["sha256"])
        ):
            raise ValueError("Predecessor binding drifted")
        candidate = REPOSITORY.joinpath(*Path(path).parts)
        actual = _safe_bytes(candidate, "predecessor asset")
        if len(actual) != record["bytes"] or sha256(actual) != record["sha256"]:
            raise ValueError(f"Predecessor asset binding drifted: {path}")
    if seen != PREDECESSOR_PATHS:
        raise ValueError("Predecessor path set drifted")


def contract() -> dict[str, Any]:
    value = _read_json(CONTRACT_PATH, "study contract")
    unsigned = dict(value)
    contract_digest = unsigned.pop("semantic_contract_sha256", None)
    required = {
        "adapter_request_manifest_only",
        "cells",
        "evidence_limits",
        "execution_policy",
        "fixture_envelope_schema",
        "format_version",
        "future_linux_native_invocation",
        "predecessor_assets",
        "semantic_contract_sha256",
        "status",
        "study_id",
    }
    if set(value) != required or contract_digest != object_sha256(unsigned):
        raise ValueError("Study contract semantic digest drifted")
    if (
        value["format_version"] != 1
        or value["study_id"]
        != "hbq-supplemental-providers-flash-next-execution-contract-v1"
        or value["status"] != "fixture_contract_only_no_go"
    ):
        raise ValueError("Study contract identity drifted")
    if (
        value["adapter_request_manifest_only"] is not True
        or value["fixture_envelope_schema"] != ENVELOPE_SCHEMA
    ):
        raise ValueError(
            "Fixture envelope or adapter-request manifest contract drifted"
        )
    policy = value["execution_policy"]
    if policy != {
        "fixture_process_limit_per_cell": 1,
        "fixture_subprocess_only": True,
        "native_dispatch_enabled": False,
        "provider_calls_made": 0,
        "remote_fallback_allowed": False,
        "resend_allowed": False,
    }:
        raise ValueError("Execution policy drifted")
    if (
        value["evidence_limits"] != EVIDENCE_LIMITS
        or value["future_linux_native_invocation"] != FUTURE_LINUX_NATIVE_INVOCATION
    ):
        raise ValueError("Evidence limits or future Linux invocation drifted")
    _validate_predecessors(value["predecessor_assets"])
    return value


def _cells() -> list[dict[str, Any]]:
    value = contract()
    cells = value["cells"]
    if not isinstance(cells, list) or len(cells) != 2:
        raise ValueError("Representative cell geometry drifted")
    expected = {
        "flash-next-generation-representative-v1": "generation",
        "flash-next-judging-representative-v1": "judging",
    }
    observed: set[str] = set()
    for cell in cells:
        if not isinstance(cell, dict) or set(cell) != {
            "assets",
            "cell_id",
            "operation",
            "outbound_payload_base64",
            "outbound_payload_sha256",
        }:
            raise ValueError("Representative cell shape drifted")
        cell_id, operation = cell["cell_id"], cell["operation"]
        if expected.get(cell_id) != operation or cell_id in observed:
            raise ValueError("Representative cell identity drifted")
        observed.add(cell_id)
        assets = cell["assets"]
        if not isinstance(assets, dict) or set(assets) != {
            "context",
            "prompt",
            "schema",
            "sampler",
        }:
            raise ValueError("Frozen assets drifted")
        bytes_by_name = {
            name: _decode_asset(record, f"{cell_id} {name}")
            for name, record in assets.items()
        }
        try:
            payload = base64.b64decode(cell["outbound_payload_base64"], validate=True)
        except (TypeError, ValueError) as error:
            raise ValueError("Outbound payload base64 drifted") from error
        if (
            not _is_sha256(cell["outbound_payload_sha256"])
            or sha256(payload) != cell["outbound_payload_sha256"]
        ):
            raise ValueError("Outbound payload bytes drifted")
        request = _json_bytes(payload, "outbound payload", canonical_required=True)
        required = {
            "format_version",
            "study_id",
            "cell_id",
            "operation",
            "source_class",
            "context_sha256",
            "prompt_sha256",
            "schema_sha256",
            "sampler_sha256",
            "requested_model",
            "response_envelope_schema",
        }
        if (
            set(request) != required
            or request["format_version"] != 1
            or request["study_id"] != value["study_id"]
            or request["cell_id"] != cell_id
            or request["operation"] != operation
            or request["source_class"] != "public_synthetic_immutable"
            or request["requested_model"] != "flash-next"
            or request["response_envelope_schema"] != FIXTURE_ENVELOPE
        ):
            raise ValueError("Outbound payload identity drifted")
        if {name: request[f"{name}_sha256"] for name in bytes_by_name} != {
            name: sha256(content) for name, content in bytes_by_name.items()
        }:
            raise ValueError("Outbound payload asset binding drifted")
    if observed != set(expected):
        raise ValueError("Representative cell set drifted")
    return cells


def _root(root: Path) -> Path:
    result = _assert_plain_path(root, "prepared root")
    if not result.is_dir():
        raise ValueError("Prepared root is unavailable")
    return result


def _cell(root: Path, cell_id: str) -> Path:
    if (
        not isinstance(cell_id, str)
        or "/" in cell_id
        or "\\" in cell_id
        or cell_id in {"", ".", ".."}
    ):
        raise ValueError("Cell id is unsafe")
    return root / cell_id


def _intent_for(cell: dict[str, Any], contract_value: dict[str, Any]) -> dict[str, Any]:
    assets = {
        name: {
            "bytes": len(_decode_asset(record, f"{cell['cell_id']} {name}")),
            "sha256": record["sha256"],
        }
        for name, record in cell["assets"].items()
    }
    payload = base64.b64decode(cell["outbound_payload_base64"], validate=True)
    return {
        "cell_id": cell["cell_id"],
        "contract_sha256": contract_value["semantic_contract_sha256"],
        "fixture_only": True,
        "format_version": 1,
        "identity_policy": {
            "native_endpoint_contact_cardinality": "unproven_fixture_only",
            "provider": "fixture-only",
            "requested_model": "flash-next",
            "runtime": "local-fixture-subprocess",
            "session": "deterministic-fixture-session",
        },
        "local_first_disclosure": {
            "outbound_payload": {"bytes": len(payload), "sha256": sha256(payload)},
            "remote_dispatch_enabled": False,
            "remote_destination": "not-disclosed-not-executable",
        },
        "operation": cell["operation"],
        "outbound_payload_sha256": cell["outbound_payload_sha256"],
        "prepared_assets": assets,
        "process_policy": {"fallback": "disabled", "limit": 1, "resend": "disabled"},
        "state": "prepared_fixture_only",
    }


def prepare(output_root: Path) -> dict[str, Any]:
    contract_value = contract()
    cells = _cells()
    root = Path(os.path.abspath(output_root))
    if root.exists() or os.path.lexists(root):
        raise ValueError(
            "Prepared root must be a new path and refuses overwrite or resume"
        )
    _assert_plain_path(root.parent, "prepared-root parent")
    root.mkdir(mode=0o700)
    _assert_plain_path(root, "prepared root")
    _write_exclusive(
        root / PREPARE_NAME,
        canonical(
            {
                "cell_ids": [cell["cell_id"] for cell in cells],
                "contract_sha256": contract_value["semantic_contract_sha256"],
                "format_version": 1,
                "state": "prepared_fixture_only",
            }
        ),
    )
    for cell in cells:
        directory = _cell(root, cell["cell_id"])
        directory.mkdir(mode=0o700)
        _write_exclusive(
            directory / "outbound-payload.json",
            base64.b64decode(cell["outbound_payload_base64"], validate=True),
        )
        _write_exclusive(
            directory / "intent.json", canonical(_intent_for(cell, contract_value))
        )
    validate_prepared(root)
    return {
        "cells": len(cells),
        "fixture_process_launches": 0,
        "native_endpoint_contact_cardinality": "unproven_fixture_only",
        "provider_calls_made": 0,
        "state": "prepared_fixture_only",
    }


def _cell_by_id(cell_id: str) -> dict[str, Any]:
    matches = [cell for cell in _cells() if cell["cell_id"] == cell_id]
    if len(matches) != 1:
        raise ValueError("Unknown representative cell")
    return matches[0]


def _expected_prepared_names() -> set[str]:
    return {PREPARE_NAME, *[cell["cell_id"] for cell in _cells()]}


def _validate_intent(root: Path, cell: dict[str, Any]) -> dict[str, Any]:
    directory = _cell(root, cell["cell_id"])
    if not directory.is_dir() or _is_reparse(directory):
        raise ValueError("Prepared cell directory drifted")
    actual_names = {path.name for path in directory.iterdir()}
    allowed = {
        "intent.json",
        "outbound-payload.json",
        "launch-intent.json",
        "fixture-process-result.json",
        "raw-response.json",
        "raw-stderr.txt",
        "receipt.json",
    }
    if (
        not actual_names <= allowed
        or not {"intent.json", "outbound-payload.json"} <= actual_names
    ):
        raise ValueError("Prepared cell inventory drifted")
    intent = _read_json(
        directory / "intent.json", "prepared intent", canonical_required=True
    )
    expected = _intent_for(cell, contract())
    if intent != expected:
        raise ValueError("Prepared intent binding drifted")
    payload = _safe_bytes(directory / "outbound-payload.json", "outbound payload")
    if payload != base64.b64decode(cell["outbound_payload_base64"], validate=True):
        raise ValueError("Prepared outbound payload drifted")
    return intent


def validate_prepared(output_root: Path) -> dict[str, Any]:
    root = _root(output_root)
    if {path.name for path in root.iterdir()} != _expected_prepared_names():
        raise ValueError("Prepared root inventory drifted")
    value = contract()
    header = _read_json(root / PREPARE_NAME, "prepare record", canonical_required=True)
    cells = _cells()
    if header != {
        "cell_ids": [cell["cell_id"] for cell in cells],
        "contract_sha256": value["semantic_contract_sha256"],
        "format_version": 1,
        "state": "prepared_fixture_only",
    }:
        raise ValueError("Prepare record binding drifted")
    for cell in cells:
        _validate_intent(root, cell)
    return {"cells": len(cells), "state": "prepared_fixture_only"}


def _fixture_output(operation: str) -> dict[str, Any]:
    if operation == "generation":
        return {
            "text": "fixture-only Flash-Next generation output; not native model evidence."
        }
    if operation == "judging":
        return {
            "evidence": "fixture-only judging evidence; not native model evidence.",
            "score": 3.0,
        }
    raise ValueError("Fixture operation is unsupported")


def _expected_identity(intent: dict[str, Any]) -> dict[str, str]:
    token = sha256(
        canonical(
            {
                "cell_id": intent["cell_id"],
                "outbound_payload_sha256": intent["outbound_payload_sha256"],
            }
        )
    )
    return {
        "model": "flash-next-fixture",
        "provider": "fixture-only",
        "request_id": "fixture-request-" + token,
        "runtime": "local-fixture-subprocess",
        "session_id": "fixture-session-" + token,
    }


def fixture_response(intent_path: Path) -> bytes:
    intent = _read_json(intent_path, "fixture intent", canonical_required=True)
    expected_keys = {
        "cell_id",
        "contract_sha256",
        "fixture_only",
        "format_version",
        "identity_policy",
        "local_first_disclosure",
        "operation",
        "outbound_payload_sha256",
        "prepared_assets",
        "process_policy",
        "state",
    }
    if (
        set(intent) != expected_keys
        or intent["fixture_only"] is not True
        or intent["state"] != "prepared_fixture_only"
        or intent["process_policy"]
        != {"fallback": "disabled", "limit": 1, "resend": "disabled"}
    ):
        raise ValueError("Fixture intent is not executable")
    return canonical(
        {
            "fixture_only": True,
            "format_version": 1,
            "identity": _expected_identity(intent),
            "output": _fixture_output(intent["operation"]),
            "request_sha256": intent["outbound_payload_sha256"],
            "schema": FIXTURE_ENVELOPE,
        }
    )


def _validate_envelope(intent: dict[str, Any], raw: bytes) -> dict[str, Any]:
    envelope = _json_bytes(raw, "fixture response", canonical_required=True)
    if (
        set(envelope)
        != {
            "fixture_only",
            "format_version",
            "identity",
            "output",
            "request_sha256",
            "schema",
        }
        or envelope["fixture_only"] is not True
        or envelope["format_version"] != 1
        or envelope["schema"] != FIXTURE_ENVELOPE
        or envelope["request_sha256"] != intent["outbound_payload_sha256"]
    ):
        raise ValueError("Fixture response envelope drifted")
    if envelope["identity"] != _expected_identity(intent):
        raise ValueError("Fixture identity is duplicate, misassociated, or malformed")
    expected_output = _fixture_output(intent["operation"])
    if envelope["output"] != expected_output:
        raise ValueError("Fixture response schema or output drifted")
    return envelope


def _file_identity(path: Path, label: str) -> dict[str, Any]:
    value = _safe_bytes(path, label)
    return {
        "bytes": len(value),
        "path": str(Path(path).resolve()),
        "sha256": sha256(value),
    }


def _fixture_runtime() -> dict[str, Any]:
    return {
        "executor": _file_identity(Path(__file__).resolve(), "fixture executor"),
        "python": {
            **_file_identity(
                Path(sys.executable).resolve(), "fixture Python executable"
            ),
            "version": sys.version,
        },
    }


def _launch_intent(intent: dict[str, Any], intent_path: Path) -> dict[str, Any]:
    command = [
        str(Path(sys.executable).resolve()),
        str(Path(__file__).resolve()),
        "fixture-response",
        "--intent",
        str(intent_path.resolve()),
    ]
    return {
        "cell_id": intent["cell_id"],
        "command": command,
        "command_sha256": sha256(canonical(command)),
        "fixture_only": True,
        "fixture_runtime": _fixture_runtime(),
        "format_version": 1,
        "intent_sha256": object_sha256(intent),
        "process_ordinal": 1,
        "resend": "disabled",
        "state": "fixture_process_launched",
    }


def _process_result(completed: Any) -> tuple[dict[str, Any], bytes, bytes]:
    stdout, stderr = bytes(completed.stdout), bytes(completed.stderr)
    result = {
        "exit_code": completed.returncode,
        "format_version": 1,
        "stderr": {"bytes": len(stderr), "sha256": sha256(stderr)},
        "stdout": {"bytes": len(stdout), "sha256": sha256(stdout)},
    }
    if not isinstance(completed.returncode, int):
        raise TypeError("Fixture process return code is malformed")
    return result, stdout, stderr


def _recorded_receipt(
    intent: dict[str, Any],
    launch: dict[str, Any],
    envelope: dict[str, Any],
    raw: bytes,
    process_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "cell_id": intent["cell_id"],
        "fixture_process_launches": 1,
        "fixture_process_result_sha256": object_sha256(process_result),
        "fixture_runtime": launch["fixture_runtime"],
        "format_version": 1,
        "identity": envelope["identity"],
        "intent_sha256": object_sha256(intent),
        "launch_intent_sha256": object_sha256(launch),
        "native_endpoint_contact_cardinality": "unproven_fixture_only",
        "provider_calls_made": 0,
        "raw_response_sha256": sha256(raw),
        "state": "recorded_fixture_only_non_native",
    }


def execute_fixture(output_root: Path, cell_id: str) -> dict[str, Any]:
    root = _root(output_root)
    validate_prepared(root)
    cell = _cell_by_id(cell_id)
    intent = _validate_intent(root, cell)
    directory = _cell(root, cell_id)
    terminal_artifacts = [
        directory / name
        for name in (
            "launch-intent.json",
            "fixture-process-result.json",
            "raw-response.json",
            "raw-stderr.txt",
            "receipt.json",
        )
    ]
    if any(path.exists() for path in terminal_artifacts):
        try:
            _validate_recorded_cell(root, cell)
        except ValueError:
            return {
                "cell_id": cell_id,
                "fixture_process_launches": 1,
                "state": "reconcile_required_after_fixture_process_launch",
            }
        return {
            "cell_id": cell_id,
            "fixture_process_launches": 1,
            "state": "terminal_recorded_no_resend",
        }
    launch = _launch_intent(intent, directory / "intent.json")
    _write_exclusive(directory / "launch-intent.json", canonical(launch))
    command = launch["command"]
    completed = subprocess.run(command, capture_output=True, check=False)
    process_result, raw, stderr = _process_result(completed)
    _write_exclusive(
        directory / "fixture-process-result.json", canonical(process_result)
    )
    _write_exclusive(directory / "raw-stderr.txt", stderr)
    if process_result["exit_code"] != 0:
        return {
            "cell_id": cell_id,
            "fixture_process_launches": 1,
            "state": "reconcile_required_after_fixture_process_launch",
        }
    envelope = _validate_envelope(intent, raw)
    _write_exclusive(directory / "raw-response.json", raw)
    receipt = _recorded_receipt(intent, launch, envelope, raw, process_result)
    _write_exclusive(directory / "receipt.json", canonical(receipt))
    return receipt


def _validate_recorded_cell(root: Path, cell: dict[str, Any]) -> dict[str, Any]:
    directory = _cell(root, cell["cell_id"])
    expected_names = {
        "intent.json",
        "outbound-payload.json",
        "launch-intent.json",
        "fixture-process-result.json",
        "raw-response.json",
        "raw-stderr.txt",
        "receipt.json",
    }
    if {path.name for path in directory.iterdir()} != expected_names:
        raise ValueError(
            "Fixture process state is ambiguous and requires reconciliation"
        )
    intent = _validate_intent(root, cell)
    launch = _read_json(
        directory / "launch-intent.json", "launch intent", canonical_required=True
    )
    if launch != _launch_intent(intent, directory / "intent.json"):
        raise ValueError("Launch intent binding drifted")
    process_result = _read_json(
        directory / "fixture-process-result.json",
        "fixture process result",
        canonical_required=True,
    )
    expected_result_keys = {"exit_code", "format_version", "stderr", "stdout"}
    if (
        set(process_result) != expected_result_keys
        or process_result["format_version"] != 1
        or process_result["exit_code"] != 0
    ):
        raise ValueError("Fixture process result drifted")
    raw = _safe_bytes(directory / "raw-response.json", "raw response")
    stderr = _safe_bytes(directory / "raw-stderr.txt", "raw stderr")
    if process_result["stdout"] != {
        "bytes": len(raw),
        "sha256": sha256(raw),
    } or process_result["stderr"] != {"bytes": len(stderr), "sha256": sha256(stderr)}:
        raise ValueError("Fixture process stream binding drifted")
    envelope = _validate_envelope(intent, raw)
    receipt = _read_json(
        directory / "receipt.json", "fixture receipt", canonical_required=True
    )
    expected_receipt = _recorded_receipt(intent, launch, envelope, raw, process_result)
    if receipt != expected_receipt:
        raise ValueError("Fixture receipt binding drifted")
    return receipt


def replay(output_root: Path) -> dict[str, Any]:
    root = _root(output_root)
    validate_prepared(root)
    identities: set[tuple[str, str]] = set()
    completed = 0
    for cell in _cells():
        directory = _cell(root, cell["cell_id"])
        terminal_names = (
            "launch-intent.json",
            "fixture-process-result.json",
            "raw-response.json",
            "raw-stderr.txt",
            "receipt.json",
        )
        if not any((directory / name).exists() for name in terminal_names):
            continue
        receipt = _validate_recorded_cell(root, cell)
        identity = (
            receipt["identity"]["request_id"],
            receipt["identity"]["session_id"],
        )
        if identity in identities:
            raise ValueError("Fixture identity is duplicated across cells")
        identities.add(identity)
        completed += 1
    return {
        "cells": len(_cells()),
        "completed_cells": completed,
        "fixture_process_launches": completed,
        "native_endpoint_contact_cardinality": "unproven_fixture_only",
        "provider_calls_made": 0,
        "state": "fixture_only_non_native_no_go",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("plan", "prepare", "fixture-response", "native-run", "replay"),
    )
    parser.add_argument("root", nargs="?", type=Path)
    parser.add_argument("--intent", type=Path)
    parser.add_argument("--cell-id")
    parser.add_argument("--runner")
    args = parser.parse_args()
    if args.command == "plan":
        if args.root is not None or args.intent is not None:
            parser.error("plan accepts no paths")
        value = contract()
        result: Any = {
            "future_linux_native_invocation": value["future_linux_native_invocation"],
            "state": "fixture_contract_only_no_go",
        }
    elif args.command == "prepare":
        if args.root is None:
            parser.error("prepare requires a new output root")
        result = prepare(args.root)
    elif args.command == "fixture-response":
        if args.intent is None or args.root is not None:
            parser.error("fixture-response requires only --intent")
        sys.stdout.buffer.write(fixture_response(args.intent))
        return 0
    elif args.command == "replay":
        if args.root is None:
            parser.error("replay requires a prepared root")
        result = replay(args.root)
    else:
        parser.error(
            "native-run is deliberately disabled: future Linux metadata only; no provider or native dispatch path exists"
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
