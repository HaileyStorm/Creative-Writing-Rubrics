#!/usr/bin/env python3
"""Offline receipt journal for Linux-portable Flash-Next preparation.

The CLI has no network, acceptance, provenance, or dispatch path. Owner
assertions are preserved only as non-authoritative local records.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit, urlunsplit


FORMAT_VERSION = 2
PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
REQUEST_ID_PREFIX = "flash-next-"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def relative_posix_path(value: str, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError(f"{label} must be a nonempty POSIX-relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} must be a contained POSIX-relative path")
    return path


def _is_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def assert_no_reparse(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if _is_reparse(cursor):
            raise ValueError(f"{label} crosses a symlink or reparse point")
    return absolute


def _identity(path: Path) -> tuple[int, int, int, int]:
    metadata = os.stat(path, follow_symlinks=False)
    return (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)


def _directory_identity(path: Path) -> tuple[int, int]:
    metadata = os.stat(path, follow_symlinks=False)
    return (metadata.st_dev, metadata.st_ino)


def _linux_directory_handle(parent: Path) -> int | None:
    if os.name != "posix":
        return None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(parent, flags)


def safe_file(path: Path, label: str) -> bytes:
    absolute = assert_no_reparse(path, label)
    if not absolute.is_file():
        raise ValueError(f"{label} is not a regular file")
    before = _identity(absolute)
    value = absolute.read_bytes()
    after = _identity(absolute)
    assert_no_reparse(absolute, label)
    if before != after:
        raise ValueError(f"{label} changed while being read")
    return value


def read_json_bytes(value: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{label} must be a JSON object")
    return decoded


def _canonical_https_url(value: Any) -> str:
    if not isinstance(value, str) or not value or any(ord(character) <= 0x20 or ord(character) == 0x7f for character in value) or any(ord(character) <= 0x20 or ord(character) == 0x7f for character in unquote(value)):
        raise ValueError("Route endpoint has control or whitespace")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("Route endpoint has an invalid port") from error
    host = parsed.hostname
    if parsed.scheme != "https" or not host or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query:
        raise ValueError("Route endpoint must be a credential-free canonical HTTPS URL")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Route endpoint port is outside the DNS/TCP range")
    if len(host) > 253 or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for character in host) or host.startswith(".") or host.endswith(".") or ".." in host:
        raise ValueError("Route endpoint host is not canonical")
    if any(not 1 <= len(label) <= 63 or not label[0].isalnum() or not label[-1].isalnum() or any(not (character.isalnum() or character == "-") for character in label) for label in host.split(".")):
        raise ValueError("Route endpoint host has an invalid DNS label")
    netloc = host if port in {None, 443} else f"{host}:{port}"
    canonical_url = urlunsplit(("https", netloc, parsed.path or "/", "", ""))
    if value != canonical_url:
        raise ValueError("Route endpoint is not in canonical HTTPS form")
    return canonical_url


def parse_route(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"format_version", "endpoint", "model", "transport", "provider_identity"}
    if set(value) != required or value.get("format_version") != 1:
        raise ValueError("Route identity has an invalid shape")
    route = dict(value)
    route["endpoint"] = _canonical_https_url(route["endpoint"])
    for key in ("model", "transport", "provider_identity"):
        if not isinstance(route[key], str) or not route[key] or route[key] != route[key].strip() or any(ord(character) <= 0x20 for character in route[key]):
            raise ValueError("Route identity contains an invalid field")
    return route


def _load_study() -> Any:
    spec = importlib.util.spec_from_file_location("flash_next_adapter_study", PACKAGE / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Frozen study module is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.validate()
    return module


def _asset_identity(value: bytes, label: str) -> dict[str, Any]:
    if not value:
        raise ValueError(f"{label} is empty")
    return {"bytes": len(value), "sha256": sha256_bytes(value)}


def _freeze_binding(study: Any, logical_cell: Mapping[str, Any], request_bytes: bytes, prompt_bytes: bytes, schema_bytes: bytes, sampler_bytes: bytes) -> dict[str, Any]:
    if set(logical_cell) != {"condition_id", "request"} or not isinstance(logical_cell.get("condition_id"), str) or not isinstance(logical_cell.get("request"), dict):
        raise ValueError("Logical cell has an invalid shape")
    contract = study.contract()
    rows = study._read_method_inputs()
    matches = [row for row in rows if row["request"] == logical_cell["request"]]
    if len(matches) != 1:
        raise ValueError("Logical cell must bind exactly one frozen schedule row")
    row = matches[0]
    if logical_cell["condition_id"] not in row["condition_labels"]:
        raise ValueError("Logical cell condition is absent from the frozen row")
    payload = read_json_bytes(request_bytes, "outbound request")
    required = {"format_version", "study_id", "condition_id", "request", "source_artifact", "question_ids", "prompt_sha256", "schema_sha256", "sampler_sha256"}
    if set(payload) != required or payload.get("format_version") != 1:
        raise ValueError("Outbound request must use the frozen wire shape")
    if payload["study_id"] != contract["study_id"] or payload["condition_id"] != logical_cell["condition_id"] or payload["request"] != row["request"] or payload["source_artifact"] != row["source_artifact"] or payload["question_ids"] != row["question_ids"]:
        raise ValueError("Outbound request is not bound to its frozen schedule row")
    assets = {"prompt": _asset_identity(prompt_bytes, "prompt"), "schema": _asset_identity(schema_bytes, "schema"), "sampler": _asset_identity(sampler_bytes, "sampler")}
    if {key: payload[f"{key}_sha256"] for key in assets} != {key: asset["sha256"] for key, asset in assets.items()}:
        raise ValueError("Outbound request does not bind frozen prompt/schema/sampler bytes")
    all_ids: list[str] = []
    for candidate in rows:
        if candidate["request"]["method_id"] == "hbq" and candidate["request"]["repetition"] == 1:
            all_ids.extend(candidate["question_ids"])
    if len(all_ids) != 178 or len(set(all_ids)) != 178:
        raise ValueError("Frozen 178-question identity is unavailable")
    return {
        "study_id": contract["study_id"],
        "condition_id": logical_cell["condition_id"],
        "source_artifact": row["source_artifact"],
        "method_input_manifest": contract["method_input_manifest"]["artifact"],
        "schedule_row": row,
        "schedule_row_sha256": digest(row),
        "canonical_178_question_ids_sha256": digest(all_ids),
        "assets": assets,
    }


def _validate_owner_assertions(route_bytes: bytes, disclosure_bytes: bytes, acknowledgement_bytes: bytes, zero_charge_bytes: bytes, request_bytes: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Validate consistency only; these are owner assertions, never acceptance."""
    route = parse_route(read_json_bytes(route_bytes, "owner route assertion"))
    required = {"format_version", "destination", "route_sha256", "outbound_request", "local_first"}
    disclosure = read_json_bytes(disclosure_bytes, "owner disclosure assertion")
    if set(disclosure) != required or disclosure.get("format_version") != 1 or disclosure.get("local_first") is not True:
        raise ValueError("Owner disclosure assertion has an invalid shape")
    if disclosure.get("destination") != {key: route[key] for key in ("endpoint", "model", "transport", "provider_identity")} or disclosure.get("route_sha256") != digest(route) or disclosure.get("outbound_request") != _asset_identity(request_bytes, "outbound request"):
        raise ValueError("Owner disclosure assertion is not bound to the exact route and request")
    acknowledgement = read_json_bytes(acknowledgement_bytes, "owner acknowledgement assertion")
    if set(acknowledgement) != {"format_version", "acknowledged_by", "acknowledgement", "disclosure_sha256"} or acknowledgement.get("format_version") != 1 or acknowledgement.get("disclosure_sha256") != digest(disclosure) or not all(isinstance(acknowledgement.get(key), str) and acknowledgement[key].strip() for key in ("acknowledged_by", "acknowledgement")):
        raise ValueError("Owner acknowledgement assertion is not bound to the disclosure")
    zero_charge = read_json_bytes(zero_charge_bytes, "owner zero-charge assertion")
    if set(zero_charge) != {"format_version", "status", "route_sha256", "issued_by", "receipt"} or zero_charge.get("format_version") != 1 or zero_charge.get("status") != "asserted_zero_charge_route" or zero_charge.get("route_sha256") != digest(route) or not all(isinstance(zero_charge.get(key), str) and zero_charge[key].strip() for key in ("issued_by", "receipt")):
        raise ValueError("Owner zero-charge assertion is not bound to the route")
    receipts = {"route": route_bytes, "disclosure": disclosure_bytes, "acknowledgement": acknowledgement_bytes, "zero_charge": zero_charge_bytes}
    return route, receipts


def _safe_root(root: Path) -> Path:
    value = assert_no_reparse(root, "run root")
    value.mkdir(parents=True, exist_ok=True)
    assert_no_reparse(value, "run root")
    return value


def run_relative(root: Path, relative: str, label: str) -> Path:
    path = relative_posix_path(relative, label)
    candidate = root.joinpath(*path.parts)
    assert_no_reparse(root, "run root")
    assert_no_reparse(candidate.parent, label)
    return candidate


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = assert_no_reparse(path.parent, "receipt parent")
    before = _directory_identity(parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        assert_no_reparse(parent, "receipt parent")
        if _directory_identity(parent) != before:
            raise ValueError("Receipt parent changed during publication")
        directory_handle = _linux_directory_handle(parent)
        try:
            if directory_handle is None:
                os.replace(temporary, path)
            else:
                os.replace(temporary.name, path.name, src_dir_fd=directory_handle, dst_dir_fd=directory_handle)
                os.fsync(directory_handle)
        finally:
            if directory_handle is not None:
                os.close(directory_handle)
        assert_no_reparse(path, "published receipt")
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_exclusive(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parent = assert_no_reparse(path.parent, "receipt parent")
    before = _directory_identity(parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        assert_no_reparse(parent, "receipt parent")
        if _directory_identity(parent) != before:
            raise ValueError("Receipt parent changed during publication")
        directory_handle = _linux_directory_handle(parent)
        try:
            if directory_handle is None:
                os.link(temporary, path)
            else:
                os.link(temporary.name, path.name, src_dir_fd=directory_handle, dst_dir_fd=directory_handle, follow_symlinks=False)
                os.fsync(directory_handle)
        finally:
            if directory_handle is not None:
                os.close(directory_handle)
        assert_no_reparse(path, "published immutable receipt")
    except BaseException:
        try:
            if temporary.exists():
                temporary.unlink()
        except OSError:
            pass
        raise
    finally:
        if temporary.exists():
            temporary.unlink()


def _request_id(binding: Mapping[str, Any]) -> str:
    return REQUEST_ID_PREFIX + digest({"study_id": binding["study_id"], "condition_id": binding["condition_id"], "schedule_row_sha256": binding["schedule_row_sha256"]})[:32]


def _paths(root: Path, request_id: str) -> dict[str, Path]:
    if not isinstance(request_id, str) or not request_id.startswith(REQUEST_ID_PREFIX) or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in request_id):
        raise ValueError("Request ID has an invalid Linux-safe shape")
    return {
        "request": run_relative(root, f"requests/{request_id}.request.json", "request receipt path"),
        "intent": run_relative(root, f"intents/{request_id}.intent.json", "intent receipt path"),
        "response": run_relative(root, f"responses/{request_id}.response.bin", "response receipt path"),
        "response_receipt": run_relative(root, f"responses/{request_id}.receipt.json", "response metadata path"),
        "journal_head": run_relative(root, "journal/head.json", "journal head path"),
        "journal_lock": run_relative(root, "journal/lock", "journal lock path"),
    }


class _JournalLock:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> None:
        try:
            _atomic_exclusive(self.path, b"locked\n")
        except FileExistsError as error:
            raise ValueError("Append-only journal is busy") from error

    def __exit__(self, *_: object) -> None:
        self.path.unlink()


def _root_binding(root: Path, binding_file: Path, study: Any) -> dict[str, Any]:
    value = read_json_bytes(safe_file(binding_file, "canonical-root binding"), "canonical-root binding")
    contract = study.contract()
    expected_root = hashlib.sha256(str(root).replace("\\", "/").encode("utf-8")).hexdigest()
    required = {"format_version", "study_id", "contract_sha256", "canonical_root_id", "root_path_sha256"}
    if set(value) != required or value.get("format_version") != 1 or value.get("study_id") != contract["study_id"] or value.get("contract_sha256") != contract["semantic_contract_sha256"] or value.get("canonical_root_id") != contract["canonical_root"]["identity"] or value.get("root_path_sha256") != expected_root:
        raise ValueError("Canonical-root binding is not exact for this external root")
    return value


def _journal_state(root: Path, study_id: str, root_id: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    head_path = run_relative(root, "journal/head.json", "journal head path")
    if not head_path.exists():
        return [], {"format_version": FORMAT_VERSION, "study_id": study_id, "canonical_root_id": root_id, "sequence": 0, "entry_sha256": None}
    head = read_json_bytes(safe_file(head_path, "journal head"), "journal head")
    if set(head) != {"format_version", "study_id", "canonical_root_id", "sequence", "entry_sha256"} or head.get("format_version") != FORMAT_VERSION or head.get("study_id") != study_id or head.get("canonical_root_id") != root_id or not isinstance(head.get("sequence"), int) or head["sequence"] < 1 or not isinstance(head.get("entry_sha256"), str):
        raise ValueError("Append-only journal head drifted")
    entries: list[dict[str, Any]] = []
    previous: str | None = None
    for sequence in range(1, head["sequence"] + 1):
        path = run_relative(root, f"journal/entries/{sequence:08d}.json", "journal entry path")
        entry_bytes = safe_file(path, "journal entry")
        entry = read_json_bytes(entry_bytes, "journal entry")
        if set(entry) != {"format_version", "sequence", "previous_entry_sha256", "study_id", "canonical_root_id", "cell_key", "request_sha256", "request_id", "intent_sha256"} or entry.get("format_version") != FORMAT_VERSION or entry.get("sequence") != sequence or entry.get("previous_entry_sha256") != previous or entry.get("study_id") != study_id or entry.get("canonical_root_id") != root_id:
            raise ValueError("Append-only journal chain drifted")
        previous = sha256_bytes(entry_bytes)
        entries.append(entry)
    if head["entry_sha256"] != previous:
        raise ValueError("Append-only journal head does not bind its final entry")
    return entries, head


def _persist_receipts(root: Path, request_id: str, receipts: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, content in receipts.items():
        path = run_relative(root, f"preflight/{request_id}.{name}.json", f"{name} receipt path")
        _atomic_exclusive(path, content)
        result[name] = {"relative_path": f"preflight/{request_id}.{name}.json", **_asset_identity(content, name), "object_sha256": digest(read_json_bytes(content, name))}
    return result


def _persist_assets(root: Path, request_id: str, assets: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, content in assets.items():
        path = run_relative(root, f"inputs/{request_id}.{name}.bin", f"{name} input path")
        _atomic_exclusive(path, content)
        result[name] = {"relative_path": f"inputs/{request_id}.{name}.bin", **_asset_identity(content, name)}
    return result


def prepare(
    root: Path,
    canonical_root_file: Path,
    logical_cell: Mapping[str, Any],
    request_file: Path,
    prompt_file: Path,
    schema_file: Path,
    sampler_file: Path,
    route_file: Path,
    disclosure_file: Path,
    acknowledgement_file: Path,
    zero_charge_file: Path,
) -> dict[str, Any]:
    """Prepare an offline-only immutable intent from non-authoritative owner assertions."""
    root = _safe_root(root)
    study = _load_study()
    root_binding_bytes = safe_file(canonical_root_file, "canonical-root binding")
    root_binding = _root_binding(root, canonical_root_file, study)
    request_bytes = safe_file(request_file, "outbound request")
    prompt_bytes = safe_file(prompt_file, "prompt")
    schema_bytes = safe_file(schema_file, "schema")
    sampler_bytes = safe_file(sampler_file, "sampler")
    binding = _freeze_binding(study, logical_cell, request_bytes, prompt_bytes, schema_bytes, sampler_bytes)
    route_bytes = safe_file(route_file, "owner route assertion")
    disclosure_bytes = safe_file(disclosure_file, "owner disclosure assertion")
    acknowledgement_bytes = safe_file(acknowledgement_file, "owner acknowledgement assertion")
    zero_charge_bytes = safe_file(zero_charge_file, "owner zero-charge assertion")
    route, receipts = _validate_owner_assertions(route_bytes, disclosure_bytes, acknowledgement_bytes, zero_charge_bytes, request_bytes)
    request_id = _request_id(binding)
    paths = _paths(root, request_id)
    request = {"relative_path": f"requests/{request_id}.request.json", **_asset_identity(request_bytes, "outbound request")}
    intent = {
        "format_version": FORMAT_VERSION,
        "request_id": request_id,
        "request": request,
        "study_binding": binding,
        "route": route,
        "route_sha256": digest(route),
        "canonical_root": {"identity": root_binding["canonical_root_id"], "binding_sha256": sha256_bytes(root_binding_bytes)},
        "owner_assertions": {},
        "input_assets": {},
        "dispatch": {"enabled": False, "reason": "native_linux_runner_required"},
        "pairable": False,
        "linux_runtime_evidence": "absent_nonpairable",
    }
    cell_key = digest({"study_id": binding["study_id"], "condition_id": binding["condition_id"], "schedule_row_sha256": binding["schedule_row_sha256"]})
    with _JournalLock(paths["journal_lock"]):
        entries, head = _journal_state(root, binding["study_id"], root_binding["canonical_root_id"])
        existing = [entry for entry in entries if entry["cell_key"] == cell_key]
        if existing:
            if len(existing) != 1 or existing[0]["request_sha256"] != request["sha256"] or existing[0]["request_id"] != request_id or not paths["intent"].is_file() or safe_file(paths["request"], "persisted request") != request_bytes:
                raise ValueError("Frozen logical cell is already bound; no remint or resend is allowed")
            existing_intent = read_json_bytes(safe_file(paths["intent"], "existing intent"), "existing intent")
            _validate_full_intent(root, existing_intent, paths)
            if existing_intent.get("request") != request or existing_intent.get("study_binding") != binding or existing_intent.get("canonical_root") != intent["canonical_root"]:
                raise ValueError("Existing intent does not match the append-only journal")
            return {"state": "resumed", "intent": existing_intent}
        if any(entry["request_sha256"] == request["sha256"] for entry in entries):
            raise ValueError("Request digest is globally bound; no duplicate work is allowed")
        if paths["request"].exists() or paths["intent"].exists():
            raise ValueError("Partial immutable state refuses resume")
        _atomic_exclusive(paths["request"], request_bytes)
        owner_assertions = dict(receipts)
        owner_assertions["canonical_root"] = root_binding_bytes
        intent["owner_assertions"] = _persist_receipts(root, request_id, owner_assertions)
        intent["input_assets"] = _persist_assets(root, request_id, {"prompt": prompt_bytes, "schema": schema_bytes, "sampler": sampler_bytes})
        _atomic_exclusive(paths["intent"], canonical(intent))
        entry = {"format_version": FORMAT_VERSION, "sequence": head["sequence"] + 1, "previous_entry_sha256": head["entry_sha256"], "study_id": binding["study_id"], "canonical_root_id": root_binding["canonical_root_id"], "cell_key": cell_key, "request_sha256": request["sha256"], "request_id": request_id, "intent_sha256": sha256_bytes(canonical(intent))}
        entry_path = run_relative(root, f"journal/entries/{entry['sequence']:08d}.json", "journal entry path")
        _atomic_exclusive(entry_path, canonical(entry))
        _atomic_replace(paths["journal_head"], canonical({"format_version": FORMAT_VERSION, "study_id": binding["study_id"], "canonical_root_id": root_binding["canonical_root_id"], "sequence": entry["sequence"], "entry_sha256": sha256_bytes(canonical(entry))}))
    return {"state": "prepared", "intent": intent}


def _load_journal_intent(root: Path, canonical_root_file: Path, logical_cell: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Path]]:
    study = _load_study()
    rows = [row for row in study._read_method_inputs() if row["request"] == logical_cell.get("request")]
    if set(logical_cell) != {"condition_id", "request"} or len(rows) != 1 or logical_cell.get("condition_id") not in rows[0]["condition_labels"]:
        raise ValueError("Logical cell is not frozen")
    row = rows[0]
    root_binding = _root_binding(root, canonical_root_file, study)
    cell_key = digest({"study_id": study.contract()["study_id"], "condition_id": logical_cell["condition_id"], "schedule_row_sha256": digest(row)})
    request_id = REQUEST_ID_PREFIX + digest({"study_id": study.contract()["study_id"], "condition_id": logical_cell["condition_id"], "schedule_row_sha256": digest(row)})[:32]
    paths = _paths(root, request_id)
    entries, _ = _journal_state(root, study.contract()["study_id"], root_binding["canonical_root_id"])
    matches = [entry for entry in entries if entry["cell_key"] == cell_key and entry["request_id"] == request_id]
    if len(matches) != 1:
        raise ValueError("Append-only journal cannot resolve exactly one immutable logical cell")
    intent = read_json_bytes(safe_file(paths["intent"], "journal intent"), "journal intent")
    if matches[0]["intent_sha256"] != sha256_bytes(canonical(intent)):
        raise ValueError("Append-only journal intent binding drifted")
    binding_bytes = safe_file(canonical_root_file, "canonical-root binding")
    if intent.get("canonical_root") != {"identity": root_binding["canonical_root_id"], "binding_sha256": sha256_bytes(binding_bytes)}:
        raise ValueError("Immutable intent belongs to a different canonical root")
    return intent, paths


def _validate_full_intent(root: Path, intent: Mapping[str, Any], paths: Mapping[str, Path]) -> None:
    required = {"format_version", "request_id", "request", "study_binding", "route", "route_sha256", "canonical_root", "owner_assertions", "input_assets", "dispatch", "pairable", "linux_runtime_evidence"}
    if set(intent) != required or intent.get("format_version") != FORMAT_VERSION or paths["intent"].name != f"{intent.get('request_id')}.intent.json":
        raise ValueError("Immutable intent has an invalid shape")
    if intent.get("dispatch") != {"enabled": False, "reason": "native_linux_runner_required"} or intent.get("pairable") is not False or intent.get("linux_runtime_evidence") != "absent_nonpairable":
        raise ValueError("Immutable intent overstated executable state")
    route = parse_route(intent.get("route", {}))
    if intent.get("route_sha256") != digest(route):
        raise ValueError("Immutable intent route binding drifted")
    request = intent.get("request")
    if not isinstance(request, dict) or set(request) != {"relative_path", "bytes", "sha256"}:
        raise ValueError("Immutable intent request receipt drifted")
    request_path = run_relative(root, request["relative_path"], "persisted request path")
    request_bytes = safe_file(request_path, "persisted request")
    if request != {"relative_path": request["relative_path"], **_asset_identity(request_bytes, "persisted request")}:
        raise ValueError("Immutable request bytes drifted")
    binding = intent.get("study_binding")
    if not isinstance(binding, dict) or not isinstance(binding.get("assets"), dict):
        raise ValueError("Immutable intent study binding drifted")
    payload = read_json_bytes(request_bytes, "persisted request")
    study = _load_study()
    rows = [row for row in study._read_method_inputs() if row == binding.get("schedule_row")]
    contract = study.contract()
    all_ids = [question for candidate in study._read_method_inputs() if candidate["request"]["method_id"] == "hbq" and candidate["request"]["repetition"] == 1 for question in candidate["question_ids"]]
    expected_binding = {
        "study_id": contract["study_id"],
        "condition_id": binding.get("condition_id"),
        "source_artifact": rows[0]["source_artifact"] if len(rows) == 1 else None,
        "method_input_manifest": contract["method_input_manifest"]["artifact"],
        "schedule_row": rows[0] if len(rows) == 1 else None,
        "schedule_row_sha256": digest(rows[0]) if len(rows) == 1 else None,
        "canonical_178_question_ids_sha256": digest(all_ids),
    }
    if len(rows) != 1 or expected_binding["condition_id"] not in rows[0]["condition_labels"] or any(binding.get(key) != value for key, value in expected_binding.items()):
        raise ValueError("Immutable intent is not bound to exactly one frozen schedule row")
    if payload.get("study_id") != binding["study_id"] or payload.get("condition_id") != binding["condition_id"] or payload.get("request") != rows[0]["request"] or payload.get("source_artifact") != rows[0]["source_artifact"] or payload.get("question_ids") != rows[0]["question_ids"]:
        raise ValueError("Immutable request no longer matches its frozen schedule binding")
    for key in ("prompt", "schema", "sampler"):
        asset = binding["assets"].get(key)
        if not isinstance(asset, dict) or set(asset) != {"bytes", "sha256"} or payload.get(f"{key}_sha256") != asset["sha256"]:
            raise ValueError("Immutable intent asset identity drifted")
    receipts = intent.get("owner_assertions")
    if not isinstance(receipts, dict) or set(receipts) != {"route", "disclosure", "acknowledgement", "zero_charge", "canonical_root"}:
        raise ValueError("Immutable intent lacks exact owner assertions")
    for name, receipt in receipts.items():
        if not isinstance(receipt, dict) or set(receipt) != {"relative_path", "bytes", "sha256", "object_sha256"}:
            raise ValueError("Immutable owner assertion shape drifted")
        content = safe_file(run_relative(root, receipt["relative_path"], f"{name} owner assertion"), f"{name} owner assertion")
        if receipt != {"relative_path": receipt["relative_path"], **_asset_identity(content, name), "object_sha256": digest(read_json_bytes(content, name))}:
            raise ValueError("Immutable owner assertion bytes drifted")
    route_content = safe_file(run_relative(root, receipts["route"]["relative_path"], "route owner assertion"), "route owner assertion")
    route_receipt = read_json_bytes(route_content, "route owner assertion")
    if parse_route(route_receipt) != route:
        raise ValueError("Immutable route receipt drifted")
    disclosure_content = safe_file(run_relative(root, receipts["disclosure"]["relative_path"], "disclosure owner assertion"), "disclosure owner assertion")
    acknowledgement_content = safe_file(run_relative(root, receipts["acknowledgement"]["relative_path"], "acknowledgement owner assertion"), "acknowledgement owner assertion")
    zero_charge_content = safe_file(run_relative(root, receipts["zero_charge"]["relative_path"], "zero-charge owner assertion"), "zero-charge owner assertion")
    disclosure = read_json_bytes(disclosure_content, "disclosure owner assertion")
    acknowledgement = read_json_bytes(acknowledgement_content, "acknowledgement owner assertion")
    zero_charge = read_json_bytes(zero_charge_content, "zero-charge owner assertion")
    if disclosure.get("route_sha256") != digest(route) or disclosure.get("outbound_request") != _asset_identity(request_bytes, "persisted request") or acknowledgement.get("disclosure_sha256") != digest(disclosure) or zero_charge.get("route_sha256") != digest(route):
        raise ValueError("Immutable preflight relationship binding drifted")
    inputs = intent.get("input_assets")
    if not isinstance(inputs, dict) or set(inputs) != {"prompt", "schema", "sampler"}:
        raise ValueError("Immutable input-byte receipts drifted")
    for key, receipt in inputs.items():
        if not isinstance(receipt, dict) or set(receipt) != {"relative_path", "bytes", "sha256"}:
            raise ValueError("Immutable input receipt shape drifted")
        content = safe_file(run_relative(root, receipt["relative_path"], f"{key} input"), f"{key} input")
        if receipt != {"relative_path": receipt["relative_path"], **_asset_identity(content, key)} or binding["assets"][key] != _asset_identity(content, key):
            raise ValueError("Immutable prompt/schema/sampler bytes drifted")


def record_response(root: Path, canonical_root_file: Path, logical_cell: Mapping[str, Any], response_file: Path) -> dict[str, Any]:
    """Record raw bytes only; this offline package never labels a response native."""
    root = _safe_root(root)
    intent, paths = _load_journal_intent(root, canonical_root_file, logical_cell)
    _validate_full_intent(root, intent, paths)
    response_bytes = safe_file(response_file, "response")
    response = {"relative_path": f"responses/{intent['request_id']}.response.bin", **_asset_identity(response_bytes, "response")}
    provenance = {"classification": "untrusted_raw", "reason": "offline_package_has_no_native_provenance_authority", "receipt": None}
    receipt = {"format_version": FORMAT_VERSION, "request_id": intent["request_id"], "intent_sha256": sha256_bytes(canonical(intent)), "request_sha256": intent["request"]["sha256"], "route_sha256": intent["route_sha256"], "response": response, "provenance": provenance, "pairable": False, "linux_runtime_evidence": "absent_nonpairable"}
    if paths["response_receipt"].exists() or paths["response"].exists():
        if not (paths["response_receipt"].is_file() and paths["response"].is_file()):
            raise ValueError("Partial response state refuses resume")
        if read_json_bytes(safe_file(paths["response_receipt"], "existing response receipt"), "existing response receipt") != receipt or safe_file(paths["response"], "persisted response") != response_bytes:
            raise ValueError("Response receipt is already bound")
        return {"state": "resumed", "receipt": receipt}
    _atomic_exclusive(paths["response"], response_bytes)
    _atomic_exclusive(paths["response_receipt"], canonical(receipt))
    return {"state": "recorded_untrusted_nonpairable", "receipt": receipt}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("dispatch", help="always disabled; no transport is implemented")
    commands.add_parser("prepare", help="offline preparation is application-only; unavailable from CLI")
    commands.add_parser("record-response", help="requires application-supplied logical-cell input; unavailable from CLI")
    args = parser.parse_args()
    parser.error(f"{args.command} is unavailable from the CLI: this package is offline-only and dispatch is disabled")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
