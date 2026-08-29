#!/usr/bin/env python3
"""Provider-free native-subscription executor for the frozen HANNA v4 dev gate."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence


HERE = Path(__file__).resolve().parent
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v3" / "study.py"
V3_EXECUTOR_PATH = HERE.parent / "hbq-human-alignment-optimizer-v3-executor-v1" / "executor.py"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "aac0c8952894a2501bd364fcf7fff392399633de8f310be1b97108061e78bbe9"
STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-v1"
GROK_ROUTE = {
    "route_name": "grok-build-grok-4.6",
    "provider": "xai_grok_build",
    "destination": "xai_grok_build_subscription",
    "account_class": "subscription",
    "requested_model": "grok-4.6",
    "requested_reasoning_effort": "high",
    "effective_model": "grok-4.6-build",
    "provider_reported_model": "grok-4.6-build",
    "identity_evidence": "requested_and_cli_envelope_reported_model_reasoning_unattested",
    "transport_identity": "grok_build_saved_session_subscription_tool_free_v1",
    "tool_policy": "tool_free_no_web_no_plan_no_subagents",
}
SOL_ROUTE = {
    "route_name": "codex-chatgpt-gpt-5.6-sol",
    "provider": "openai_codex",
    "destination": "openai_codex_chatgpt_subscription",
    "account_class": "subscription",
    "requested_model": "gpt-5.6-sol",
    "requested_reasoning_effort": "high",
    "effective_model": "gpt-5.6-sol",
    "provider_reported_model": None,
    "identity_evidence": "requested_and_local_effective_settings_only_not_provider_attested",
    "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v1",
    "tool_policy": "tool_free_no_web_no_plan_no_subagents",
}
ROUTES = {"grok_primary": GROK_ROUTE, "sol_validation": SOL_ROUTE}
PROMPT_FIELDS = (
    "task_payload_sha256", "candidate_instruction_sha256", "candidate_profile_sha256",
    "response_schema_sha256", "prompt_sha256", "story_sha256",
)
BASE_FILES = frozenset({
    "outbound-payload.json", "disclosure.json", "acknowledgement.json",
    "zero-charge-route-proof.json", "prepared.json",
})
CONTACT_STATES = {
    "prepared": frozenset(),
    "intent_unsettled": frozenset({"intent.json"}),
    "reconcile_required": frozenset({"intent.json", "result.json"}),
    "native_returned_unprojected": frozenset({
        "intent.json", "native-request.bin", "native-response.bin", "effective-settings.json", "result.json",
    }),
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest(value: Any) -> str:
    return digest_bytes(canonical(value))


def _absolute_no_resolve(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _ancestry(path: Path, *, include_leaf: bool) -> list[Path]:
    absolute = _absolute_no_resolve(path)
    anchor = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    limit = len(parts) if include_leaf else max(0, len(parts) - 1)
    result: list[Path] = []
    current = anchor
    for part in parts[:limit]:
        current = current / part
        result.append(current)
    return result


def _reject_reparse_stat(path: Path, value: os.stat_result) -> None:
    attributes = getattr(value, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if stat.S_ISLNK(value.st_mode) or attributes & reparse:
        raise ValueError(f"HANNA v4 reparse point is forbidden: {path}")


def _assert_no_reparse_ancestry(path: Path, *, include_leaf: bool) -> None:
    for candidate in _ancestry(path, include_leaf=include_leaf):
        try:
            info = os.lstat(candidate)
        except OSError as error:
            raise ValueError(f"HANNA v4 path ancestry is unavailable: {candidate}") from error
        _reject_reparse_stat(candidate, info)


def _win_open_checked(path: Path, *, directory: bool) -> tuple[Any, Callable[[], None]]:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel32.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    get_info = kernel32.GetFileInformationByHandle
    get_info.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    get_info.restype = wintypes.BOOL
    get_final = kernel32.GetFinalPathNameByHandleW
    get_final.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    get_final.restype = wintypes.DWORD
    close = kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL

    class HandleInfo(ctypes.Structure):
        _fields_ = [
            ("attributes", wintypes.DWORD), ("created_low", wintypes.DWORD), ("created_high", wintypes.DWORD),
            ("accessed_low", wintypes.DWORD), ("accessed_high", wintypes.DWORD),
            ("written_low", wintypes.DWORD), ("written_high", wintypes.DWORD),
            ("volume_serial", wintypes.DWORD), ("size_high", wintypes.DWORD), ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD), ("index_high", wintypes.DWORD), ("index_low", wintypes.DWORD),
        ]

    generic_read = 0x80000000
    share_read, share_write = 0x1, 0x2
    open_existing = 3
    open_reparse = 0x00200000
    backup_semantics = 0x02000000
    flags = open_reparse | (backup_semantics if directory else 0x80)
    handle = create(str(_absolute_no_resolve(path)), 0 if directory else generic_read,
                    share_read | (share_write if directory else 0), None, open_existing, flags, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), f"cannot stably open {path}")
    try:
        info = HandleInfo()
        if not get_info(handle, ctypes.byref(info)):
            raise OSError(ctypes.get_last_error(), f"cannot inspect {path}")
        if info.attributes & 0x400:
            raise ValueError(f"HANNA v4 reparse point is forbidden: {path}")
        buffer = ctypes.create_unicode_buffer(32768)
        length = get_final(handle, buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            raise OSError(ctypes.get_last_error(), f"cannot resolve stable handle {path}")
        final = buffer.value
        if final.startswith("\\\\?\\"):
            final = final[4:]
        if os.path.normcase(os.path.abspath(final)) != os.path.normcase(os.path.abspath(path)):
            raise ValueError(f"HANNA v4 stable handle path drifted: {path}")
    except BaseException:
        close(handle)
        raise
    return handle, lambda: close(handle)


def _stable_read_bytes(path: Path) -> bytes:
    path = _absolute_no_resolve(path)
    _assert_no_reparse_ancestry(path, include_leaf=True)
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        releases: list[Callable[[], None]] = []
        try:
            for parent in _ancestry(path, include_leaf=False):
                _handle, release = _win_open_checked(parent, directory=True)
                releases.append(release)
            handle, release = _win_open_checked(path, directory=False)
            releases.append(release)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_size = kernel32.GetFileSizeEx
            get_size.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong)]
            get_size.restype = wintypes.BOOL
            read_file = kernel32.ReadFile
            read_file.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                  ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
            read_file.restype = wintypes.BOOL
            size = ctypes.c_longlong()
            if not get_size(handle, ctypes.byref(size)) or size.value < 0:
                raise OSError(ctypes.get_last_error(), f"cannot size {path}")
            chunks: list[bytes] = []
            remaining = size.value
            while remaining:
                length = min(remaining, 1024 * 1024)
                buffer = ctypes.create_string_buffer(length)
                read = wintypes.DWORD()
                if not read_file(handle, buffer, length, ctypes.byref(read), None) or read.value <= 0:
                    raise OSError(ctypes.get_last_error(), f"cannot stably read {path}")
                chunks.append(buffer.raw[:read.value])
                remaining -= read.value
            return b"".join(chunks)
        finally:
            for release in reversed(releases):
                release()
    before = os.lstat(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"HANNA v4 stable file identity drifted: {path}")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def contract() -> dict[str, Any]:
    try:
        raw = _stable_read_bytes(CONTRACT_PATH)
        if digest_bytes(raw) != CONTRACT_SHA256:
            raise ValueError("HANNA v4 study contract bytes drifted")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA v4 study contract is invalid") from error
    if (not isinstance(value, dict) or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID
            or value.get("kind") != "provider_free_native_subscription_development_executor"):
        raise ValueError("HANNA v4 study contract identity drifted")
    routes = value.get("routes", {})
    if (routes.get("grok_primary") != {
        "provider": GROK_ROUTE["provider"], "destination": GROK_ROUTE["destination"],
        "requested_model": GROK_ROUTE["requested_model"], "effective_model": GROK_ROUTE["effective_model"],
        "provider_reported_model": GROK_ROUTE["provider_reported_model"], "reasoning_attested": False,
        "tool_policy": GROK_ROUTE["tool_policy"],
    } or routes.get("sol_validation") != {
        "provider": SOL_ROUTE["provider"], "destination": SOL_ROUTE["destination"],
        "requested_model": SOL_ROUTE["requested_model"], "effective_model": SOL_ROUTE["effective_model"],
        "provider_reported_model": None, "identity_evidence": SOL_ROUTE["identity_evidence"],
        "tool_policy": SOL_ROUTE["tool_policy"],
    }):
        raise ValueError("HANNA v4 route identity contract drifted")
    if (value.get("geometry") != {
        "mandatory_development": {"grok": 65, "sol": 35, "total": 100},
        "optional_training_pool": {"grok": 240, "sol": 120, "total": 360},
        "confirmation_cells": 0,
    } or value.get("confirmation") != {"status": "unopened", "scheduled_cells": 0}):
        raise ValueError("HANNA v4 geometry or confirmation contract drifted")
    execution = value.get("execution", {})
    if execution != {
        "payload": "exact_unchanged_task_instruction_profile_schema_prompt_story_bytes",
        "contact_rule": "exclusive_intent_before_contact_one_native_call_max",
        "ambiguous_rule": "reconcile_required_no_auto_resend",
        "zero_charge_only": True, "paid_fallback_forbidden": True, "api_fallback_forbidden": True,
        "live_runner": "absent_private_seam",
    }:
        raise ValueError("HANNA v4 zero-charge contract drifted")
    if value.get("optimizer") != {
        "training_pool": "optional_development_only", "dspy_runtime_dependency": False,
        "optuna_runtime_dependency": False, "selection_authority": "none",
    }:
        raise ValueError("HANNA v4 optimizer boundary drifted")
    if value.get("result_authority") != "development_evidence_only_pending_independent_adapter_receipt_and_native_request_review":
        raise ValueError("HANNA v4 result authority drifted")
    return value


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"HANNA v4 predecessor {path.name} is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_v3() -> ModuleType:
    module = _load_module(V3_PATH, "_hanna_v4_parent_v3")
    module.contract()
    return module


def _load_v3_executor() -> ModuleType:
    return _load_module(V3_EXECUTOR_PATH, "_hanna_v4_parent_executor")


def _write_new(path: Path, payload: bytes) -> None:
    _assert_no_reparse_ancestry(Path(path).parent, include_leaf=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError(f"HANNA v4 refuses to overwrite {path.name}") from error


def _read_canonical(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = _stable_read_bytes(path)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA v4 {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA v4 {label} is noncanonical")
    return value


def _inventory(root: Path) -> tuple[frozenset[str], str]:
    _assert_no_reparse_ancestry(root, include_leaf=True)
    try:
        entries = list(os.scandir(root))
    except OSError as error:
        raise ValueError("HANNA v4 prepared root inventory is unavailable") from error
    names: set[str] = set()
    for entry in entries:
        try:
            info = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError("HANNA v4 prepared root inventory is unstable") from error
        _reject_reparse_stat(Path(entry.path), info)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("HANNA v4 prepared root contains a non-regular artifact")
        names.add(entry.name)
    frozen = frozenset(names)
    if not BASE_FILES <= frozen:
        raise ValueError("HANNA v4 prepared root is missing a base artifact")
    contact = frozen - BASE_FILES
    states = [name for name, expected in CONTACT_STATES.items() if contact == expected]
    if len(states) != 1:
        raise ValueError("HANNA v4 prepared root contains orphan or partial contact artifacts")
    return frozen, states[0]


def _expected_intent(row: Mapping[str, Any], prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "intent_before_native_subscription_contact",
        "cell_id": row["cell_id"],
        "prepared_sha256": digest(prepared),
        "provider_calls_made_before_intent": 0,
    }


def _validate_persisted_result(root: Path, *, row: Mapping[str, Any], prepared: Mapping[str, Any],
                               inventory_state: str) -> dict[str, Any]:
    if inventory_state not in {"reconcile_required", "native_returned_unprojected"}:
        raise ValueError("HANNA v4 persisted result state is unavailable")
    intent = _read_canonical(root / "intent.json", label="contact intent")
    expected_intent = _expected_intent(row, prepared)
    if intent != expected_intent:
        raise ValueError("HANNA v4 persisted intent binding drifted")
    result = _read_canonical(root / "result.json", label="native result")
    common = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "native_subscription_cell_result",
        "state": inventory_state,
        "cell_id": row["cell_id"],
        "intent_sha256": digest(expected_intent),
        "provider_calls_made": 1,
    }
    if inventory_state == "reconcile_required":
        if set(result) != {*common, "error_type"} or any(result.get(key) != value for key, value in common.items()):
            raise ValueError("HANNA v4 malformed reconciliation result")
        if not isinstance(result.get("error_type"), str) or not result["error_type"]:
            raise ValueError("HANNA v4 malformed reconciliation result")
        return result
    required = {
        *common, "native_request_sha256", "native_response_sha256", "effective_settings_sha256",
        "identity", "identity_sha256",
    }
    if set(result) != required or any(result.get(key) != value for key, value in common.items()):
        raise ValueError("HANNA v4 malformed settled result")
    request = _stable_read_bytes(root / "native-request.bin")
    response = _stable_read_bytes(root / "native-response.bin")
    settings_value = _read_canonical(root / "effective-settings.json", label="effective settings")
    identity_value = _validate_identity(result.get("identity"), row)
    if (digest_bytes(request) != result.get("native_request_sha256")
            or digest_bytes(response) != result.get("native_response_sha256")
            or digest(settings_value) != result.get("effective_settings_sha256")
            or digest(identity_value) != result.get("identity_sha256")):
        raise ValueError("HANNA v4 malformed settled result bindings")
    _validate_effective_settings(settings_value, row)
    return result


def _successor_row(parent: Mapping[str, Any], *, route_name: str, ordinal: int) -> dict[str, Any]:
    route = ROUTES[route_name]
    key = {"study_id": STUDY_ID, "route_name": route_name, "parent_cell_id": parent["cell_id"]}
    return {
        "ordinal": ordinal,
        "cell_id": "v4-cell-" + digest(key)[:16],
        "parent_cell_id": parent["cell_id"],
        "item_id": parent["item_id"],
        "candidate_id": parent["candidate_id"],
        "partition": parent["partition"],
        "prompt_group_id": parent["prompt_group_id"],
        "route_name": route_name,
        "route": dict(route),
        **{field: parent[field] for field in PROMPT_FIELDS},
    }


def derive_schedule(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    contract()
    v3 = _load_v3()
    parent = v3.derive_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    grok_dev = [row for row in parent["grok_primary"] if row["partition"] == "development"]
    sol_dev = [row for row in parent["sol_validation"] if row["partition"] == "development"]
    grok_train = [row for row in parent["grok_primary"] if row["partition"] == "train"]
    sol_train = [row for row in parent["sol_validation"] if row["partition"] == "train"]
    mandatory = [
        *[_successor_row(row, route_name="grok_primary", ordinal=index + 1) for index, row in enumerate(grok_dev)],
        *[_successor_row(row, route_name="sol_validation", ordinal=index + 1) for index, row in enumerate(sol_dev)],
    ]
    training = [
        *[_successor_row(row, route_name="grok_primary", ordinal=index + 1) for index, row in enumerate(grok_train)],
        *[_successor_row(row, route_name="sol_validation", ordinal=index + 1) for index, row in enumerate(sol_train)],
    ]
    if len(mandatory) != 100 or sum(row["route_name"] == "grok_primary" for row in mandatory) != 65:
        raise ValueError("HANNA v4 mandatory development geometry drifted")
    if len(training) != 360 or any(row["partition"] != "train" for row in training):
        raise ValueError("HANNA v4 optional training-pool geometry drifted")
    if len({row["cell_id"] for row in [*mandatory, *training]}) != 460:
        raise ValueError("HANNA v4 schedule cell identities are duplicated")
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_native_subscription_development_schedule",
        "parent_v3_schedule_sha256": parent["schedule_sha256"],
        "candidate_ids": parent["candidate_ids"],
        "mandatory_development": mandatory,
        "optional_training_pool": {
            "status": "retained_development_only_not_runtime_dispatchable",
            "dspy_runtime_dependency": False,
            "optuna_runtime_dependency": False,
            "cells": training,
        },
        "geometry": {
            "mandatory_development": {"grok": 65, "sol": 35, "total": 100},
            "optional_training_pool": {"grok": 240, "sol": 120, "total": 360},
        },
        "confirmation": {"status": "unopened", "scheduled_cells": 0},
    }
    result["schedule_sha256"] = digest({
        "parent_v3_schedule_sha256": result["parent_v3_schedule_sha256"],
        "mandatory_development": mandatory,
        "optional_training_pool": training,
        "confirmation": result["confirmation"],
    })
    return result


def _cell(schedule: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    rows = [row for row in schedule["mandatory_development"] if row["cell_id"] == cell_id]
    if len(rows) != 1:
        raise ValueError("HANNA v4 accepts only mandatory development cells; training is optional and confirmation is unopened")
    return dict(rows[0])


def _payload(v3: ModuleType, row: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> bytes:
    predecessor = _load_v3_executor()
    parent_row = dict(row)
    parent_row["cell_id"] = row["parent_cell_id"]
    raw = predecessor._payload(
        v3, parent_row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    parsed = json.loads(raw.decode("utf-8"))
    components = parsed.get("components")
    if not isinstance(components, dict) or tuple(components) != (
        "candidate_instruction", "candidate_profile", "prompt", "response_schema", "story", "task_payload"
    ):
        raise ValueError("HANNA v4 predecessor payload components drifted")
    actual = {
        "task_payload_sha256": digest_bytes(components["task_payload"].encode("utf-8")),
        "candidate_instruction_sha256": digest_bytes(components["candidate_instruction"].encode("utf-8")),
        "candidate_profile_sha256": digest_bytes(components["candidate_profile"].encode("utf-8")),
        "response_schema_sha256": digest_bytes(components["response_schema"].encode("utf-8")),
        "prompt_sha256": digest_bytes(components["prompt"].encode("utf-8")),
        "story_sha256": digest_bytes(components["story"].encode("utf-8")),
    }
    if any(actual[field] != row[field] for field in PROMPT_FIELDS):
        raise ValueError("HANNA v4 exact prompt component binding drifted")
    return canonical({"format_version": 1, "study_id": STUDY_ID, "components": components})


def _load_pinned_gate_verifier() -> Callable[[dict[str, Any]], Any]:
    """Private production seam; the provider-free package binds no live authority."""
    raise ValueError("HANNA v4 has no enabled trusted gate verifier")


def _load_pinned_runner() -> Callable[[Mapping[str, Any], bytes, Callable[[], None]], Mapping[str, Any]]:
    """Private production seam; tests may replace only this loader."""
    raise ValueError("HANNA v4 has no enabled native subscription runner")


def _load_pinned_native_request_verifier() -> Callable[[dict[str, Any]], Any]:
    """Private production seam proving the native request carried frozen bytes."""
    raise ValueError("HANNA v4 has no enabled native-request verifier")


def _gate(path: Path, *, kind: str, row: Mapping[str, Any], disclosure_sha256: str) -> dict[str, Any]:
    value = _read_canonical(path, label=kind)
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": kind,
        "cell_id": row["cell_id"],
        "disclosure_sha256": disclosure_sha256,
    }
    if any(value.get(key) != candidate for key, candidate in expected.items()) or value.get("acknowledged") is not True:
        raise ValueError(f"HANNA v4 {kind} gate is invalid")
    if kind == "zero_charge_route_proof":
        route = row["route"]
        required = {
            "route_descriptor_sha256": digest(route),
            "account_class": "subscription",
            "zero_charge_only": True,
            "paid_fallback_forbidden": True,
            "api_fallback_forbidden": True,
        }
        if any(value.get(key) != candidate for key, candidate in required.items()):
            raise ValueError("HANNA v4 zero-charge route proof is invalid")
    outcome = _load_pinned_gate_verifier()({"gate_kind": kind, "gate": value, "cell": dict(row)})
    if outcome is not True and outcome != {"accepted": True}:
        raise ValueError(f"HANNA v4 {kind} gate is not trusted")
    return value


def _disclosure(*, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "pre_contact_local_first_disclosure",
        "cell_id": row["cell_id"],
        "schedule_sha256": schedule["schedule_sha256"],
        "route": row["route"],
        "artifacts_leaving_machine": {
            "outbound_payload": {"bytes": len(payload), "sha256": digest_bytes(payload), "text": payload.decode("utf-8")}
        },
        "tool_policy": "tool_free_no_web_no_plan_no_subagents",
        "provider_calls_made": 0,
    }


def _prepared(*, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes,
              disclosure: Mapping[str, Any], acknowledgement: Mapping[str, Any], proof: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "prepared_native_subscription_cell",
        "cell": dict(row),
        "schedule_sha256": schedule["schedule_sha256"],
        "outbound_payload_sha256": digest_bytes(payload),
        "disclosure_sha256": digest(disclosure),
        "acknowledgement_sha256": digest(acknowledgement),
        "route_proof_sha256": digest(proof),
        "provider_calls_made": 0,
    }


def _verify_root(*, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path,
                 cell_id: str, allow_contact_files: bool) -> tuple[dict[str, Any], dict[str, Any], bytes, str]:
    schedule = derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    row = _cell(schedule, cell_id)
    root = Path(output_root) / cell_id
    inventory_before, inventory_state = _inventory(root)
    if not allow_contact_files and inventory_state != "prepared":
        raise ValueError("HANNA v4 prepared root already contains contact artifacts")
    payload = _payload(_load_v3(), row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    disclosure = _disclosure(row=row, schedule=schedule, payload=payload)
    acknowledgement = _gate(root / "acknowledgement.json", kind="acknowledgement", row=row, disclosure_sha256=digest(disclosure))
    proof = _gate(root / "zero-charge-route-proof.json", kind="zero_charge_route_proof", row=row, disclosure_sha256=digest(disclosure))
    prepared = _prepared(row=row, schedule=schedule, payload=payload, disclosure=disclosure, acknowledgement=acknowledgement, proof=proof)
    if (_stable_read_bytes(root / "outbound-payload.json") != payload
            or _read_canonical(root / "disclosure.json", label="disclosure") != disclosure
            or _read_canonical(root / "prepared.json", label="prepared manifest") != prepared):
        raise ValueError("HANNA v4 prepared root binding drifted")
    inventory_after, state_after = _inventory(root)
    if inventory_after != inventory_before or state_after != inventory_state:
        raise ValueError("HANNA v4 prepared root inventory changed during verification")
    return row, prepared, payload, inventory_state


def prepare_cell(*, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, output_root: Path,
                 acknowledgement_path: Path, route_proof_path: Path) -> dict[str, Any]:
    schedule = derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    row = _cell(schedule, cell_id)
    payload = _payload(_load_v3(), row, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    root = Path(output_root) / cell_id
    if root.exists():
        _verify_root(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), cell_id=cell_id, allow_contact_files=False)
        return {"cell_id": cell_id, "prepared": True, "resumed": True, "provider_calls_made": 0}
    disclosure = _disclosure(row=row, schedule=schedule, payload=payload)
    acknowledgement = _gate(Path(acknowledgement_path), kind="acknowledgement", row=row, disclosure_sha256=digest(disclosure))
    proof = _gate(Path(route_proof_path), kind="zero_charge_route_proof", row=row, disclosure_sha256=digest(disclosure))
    root.mkdir(parents=True, exist_ok=False)
    _write_new(root / "outbound-payload.json", payload)
    _write_new(root / "disclosure.json", canonical(disclosure))
    _write_new(root / "acknowledgement.json", canonical(acknowledgement))
    _write_new(root / "zero-charge-route-proof.json", canonical(proof))
    _write_new(root / "prepared.json", canonical(_prepared(
        row=row, schedule=schedule, payload=payload, disclosure=disclosure, acknowledgement=acknowledgement, proof=proof
    )))
    return {"cell_id": cell_id, "prepared": True, "resumed": False, "provider_calls_made": 0}


def _validate_effective_settings(value: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    route = row["route"]
    expected = {
        "route_name": route["route_name"],
        "effective_model": route["effective_model"],
        "requested_reasoning_effort": route["requested_reasoning_effort"],
        "tools_enabled": False,
        "web_search_enabled": False,
        "subagents_enabled": False,
        "output_schema_sha256": row["response_schema_sha256"],
        "provider_attested": False,
        "source": "grok_cli_invocation_and_envelope_v1" if row["route_name"] == "grok_primary" else "codex_cli_local_events_and_invocation_v1",
    }
    if not isinstance(value, Mapping) or dict(value) != expected:
        raise ValueError("HANNA v4 local effective settings drifted")
    return dict(value)


def _validate_identity(value: Any, row: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "provider", "route_name", "requested_model", "requested_reasoning_effort", "effective_model",
        "provider_reported_model", "identity_evidence", "reasoning_attested", "transport_identity",
        "contact_id", "session_id",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("HANNA v4 native identity fields drifted")
    route = row["route"]
    expected = {
        "provider": route["provider"],
        "route_name": route["route_name"],
        "requested_model": route["requested_model"],
        "requested_reasoning_effort": route["requested_reasoning_effort"],
        "effective_model": route["effective_model"],
        "provider_reported_model": route["provider_reported_model"],
        "identity_evidence": route["identity_evidence"],
        "reasoning_attested": False,
        "transport_identity": route["transport_identity"],
    }
    if any(value.get(key) != candidate for key, candidate in expected.items()):
        raise ValueError("HANNA v4 native route identity drifted or was relabelled")
    if any(not isinstance(value.get(key), str) or not value[key] for key in ("contact_id", "session_id")):
        raise ValueError("HANNA v4 native contact identity is incomplete")
    return dict(value)


def dispatch_prepared_cell(*, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path,
                           cell_id: str, allow_remote: bool) -> dict[str, Any]:
    """Make at most one contact; every post-intent uncertainty requires reconciliation."""
    if allow_remote is not True:
        return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
    root = Path(output_root) / cell_id
    row, prepared, payload, inventory_state = _verify_root(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
        output_root=Path(output_root), cell_id=cell_id, allow_contact_files=True,
    )
    if inventory_state in {"reconcile_required", "native_returned_unprojected"}:
        prior = _validate_persisted_result(root, row=row, prepared=prepared, inventory_state=inventory_state)
        return {"cell_id": cell_id, "state": prior["state"], "provider_calls_made": 0, "resumed": True}
    if inventory_state == "intent_unsettled":
        raise ValueError("HANNA v4 prior contact intent is unresolved; explicit reconciliation is required")
    if inventory_state != "prepared":
        raise ValueError("HANNA v4 contact state is invalid before fresh intent")
    intent = _expected_intent(row, prepared)
    try:
        runner = _load_pinned_runner()
    except BaseException:
        return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
    contacted = False

    def before_contact() -> None:
        nonlocal contacted
        if contacted:
            raise ValueError("HANNA v4 runner signalled contact twice")
        _write_new(root / "intent.json", canonical(intent))
        contacted = True

    try:
        native = runner(row, payload, before_contact)
        if not contacted:
            return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
        if not isinstance(native, Mapping):
            raise ValueError("HANNA v4 native runner result is invalid")
        request = native.get("request_bytes")
        response = native.get("response_bytes")
        if not isinstance(request, bytes) or not isinstance(response, bytes):
            raise ValueError("HANNA v4 runner must return raw request and response bytes")
        identity = _validate_identity(native.get("identity"), row)
        settings = _validate_effective_settings(native.get("effective_settings"), row)
        _write_new(root / "native-request.bin", request)
        _write_new(root / "native-response.bin", response)
        _write_new(root / "effective-settings.json", canonical(settings))
        result = {
            "format_version": 1,
            "study_id": STUDY_ID,
            "kind": "native_subscription_cell_result",
            "state": "native_returned_unprojected",
            "cell_id": cell_id,
            "intent_sha256": digest(intent),
            "native_request_sha256": digest_bytes(request),
            "native_response_sha256": digest_bytes(response),
            "effective_settings_sha256": digest(settings),
            "identity": identity,
            "identity_sha256": digest(identity),
            "provider_calls_made": 1,
        }
    except BaseException as error:
        if not contacted:
            return {"cell_id": cell_id, "state": "pending_precontact", "provider_calls_made": 0}
        result = {
            "format_version": 1,
            "study_id": STUDY_ID,
            "kind": "native_subscription_cell_result",
            "state": "reconcile_required",
            "cell_id": cell_id,
            "intent_sha256": digest(intent),
            "error_type": type(error).__name__,
            "provider_calls_made": 1,
        }
    _write_new(root / "result.json", canonical(result))
    return {"cell_id": cell_id, "state": result["state"], "provider_calls_made": 1, "resumed": False}


def _extract_native(response: bytes, *, row: Mapping[str, Any], identity: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, bool]]:
    v2 = _load_v3().v2_module()
    if row["route_name"] == "grok_primary":
        scores, coverage, reported = v2._extract_native(response, provider="xai", model="grok-4.6")
        if (reported.get("reported_model") != identity["provider_reported_model"]
                or reported.get("native_request_id_sha256") != digest_bytes(identity["contact_id"].encode("utf-8"))
                or reported.get("native_session_id_sha256") != digest_bytes(identity["session_id"].encode("utf-8"))):
            raise ValueError("HANNA v4 Grok envelope/contact/session identity is misassociated")
        return scores, coverage
    try:
        value = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA v4 Codex final response is not strict JSON") from error
    if not isinstance(value, dict):
        raise ValueError("HANNA v4 Codex final response must be one JSON object")
    scores = v2._validate_scores(value)
    coverage = {dimension: bool(value["coverage"][dimension]) for dimension in v2.DIMENSIONS}
    if identity["provider_reported_model"] is not None or identity["identity_evidence"] != SOL_ROUTE["identity_evidence"]:
        raise ValueError("HANNA v4 Codex identity was falsely provider-attested")
    return scores, coverage


def _verify_native_request_receipt(*, row: Mapping[str, Any], identity: Mapping[str, Any],
                                   event: dict[str, Any]) -> None:
    outcome = _load_pinned_native_request_verifier()(event)
    if row["route_name"] == "sol_validation":
        expected = {
            "accepted": True,
            "attested_contact_id": identity["contact_id"],
            "attested_session_id": identity["session_id"],
            "attestation_scope": "local_codex_contact_and_session_binding_not_provider_model_attestation",
        }
        if outcome != expected:
            raise ValueError("HANNA v4 Sol local contact/session receipt is not independently attested")
        return
    if outcome is not True and outcome != {"accepted": True}:
        raise ValueError("HANNA v4 native request is not bound to frozen outbound payload")


def _targets(*, v3: ModuleType, schedule: Mapping[str, Any], frozen_successor_path: Path,
             hanna_csv_path: Path) -> dict[str, dict[str, float]]:
    predecessor = _load_v3_executor()
    parent = v3.derive_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    by_id = {row["cell_id"]: row for row in [*parent["grok_primary"], *parent["sol_validation"]]}
    parent_rows = [by_id[row["parent_cell_id"]] for row in schedule["mandatory_development"]]
    return predecessor._scheduled_targets(
        v3=v3, rows=parent_rows, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )


def project_mandatory_cells(*, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path) -> dict[str, Any]:
    """Project all 100 persisted development cells; no caller metrics are accepted."""
    v3 = _load_v3()
    schedule = derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    targets = _targets(
        v3=v3, schedule=schedule, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    observations: list[dict[str, Any]] = []
    contacts: set[tuple[str, str, str]] = set()
    for row in schedule["mandatory_development"]:
        root = Path(output_root) / row["cell_id"]
        checked, prepared, payload, inventory_state = _verify_root(
            frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
            output_root=Path(output_root), cell_id=row["cell_id"], allow_contact_files=True,
        )
        if checked != row:
            raise ValueError("HANNA v4 projected schedule row drifted")
        if inventory_state != "native_returned_unprojected":
            raise ValueError("HANNA v4 projection requires every mandatory settled native cell")
        result = _validate_persisted_result(root, row=row, prepared=prepared, inventory_state=inventory_state)
        request = _stable_read_bytes(root / "native-request.bin")
        response = _stable_read_bytes(root / "native-response.bin")
        settings = _read_canonical(root / "effective-settings.json", label="effective settings")
        if (digest_bytes(request) != result["native_request_sha256"] or digest_bytes(response) != result["native_response_sha256"]
                or digest(settings) != result["effective_settings_sha256"]):
            raise ValueError("HANNA v4 persisted native bytes drifted")
        _validate_effective_settings(settings, row)
        identity = _validate_identity(result.get("identity"), row)
        if digest(identity) != result["identity_sha256"]:
            raise ValueError("HANNA v4 native identity binding drifted")
        _verify_native_request_receipt(row=row, identity=identity, event={
            "cell": dict(row), "prepared": prepared, "outbound_payload": payload,
            "native_request_bytes": request, "effective_settings": settings, "identity": identity,
        })
        contact = (identity["provider"], identity["contact_id"], identity["session_id"])
        if contact in contacts:
            raise ValueError("HANNA v4 native contact identity is duplicated")
        contacts.add(contact)
        scores, coverage = _extract_native(response, row=row, identity=identity)
        observations.append({**row, "scores": scores, "coverage": coverage})

    v2 = v3.v2_module()
    def metrics(route_name: str, expected_items: int) -> list[dict[str, Any]]:
        result = []
        for candidate in schedule["candidate_ids"]:
            subset = [row for row in observations if row["route_name"] == route_name and row["candidate_id"] == candidate]
            result.append({
                "candidate_id": candidate,
                "candidate_sha256": next(item["candidate_sha256"] for item in v3.candidate_pack() if item["candidate_id"] == candidate),
                "development": v2._candidate_endpoint(subset, targets, expected_items=expected_items, expected_groups=7),
            })
        return result

    parent_schedule = v3.derive_schedule(
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)
    )
    grok = metrics("grok_primary", 13)
    frozen = v3.freeze_grok_selection(grok, schedule=parent_schedule)
    sol = metrics("sol_validation", 7)
    validation = v3.validate_sol_generalization(frozen, grok, sol, schedule=parent_schedule)
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "persisted_native_subscription_development_projection",
        "completed_cells": 100,
        "grok_selection": frozen,
        "sol_validation": validation,
        "optional_training_pool": {"status": "unopened_not_required_for_projection", "scheduled_cells": 0},
        "confirmation": {"status": "unopened", "scheduled_cells": 0},
        "empirical_authority": "development_evidence_only_pending_independent_adapter_receipt_and_native_request_review",
    }
