"""Prepare or dispatch one frozen HANNA development cell under deployment trust gates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

import jsonschema
from jsonschema import Draft202012Validator
from execution_freeze import ROUTES, provider_ready_payload, validate_execution_freeze
from study import (
    CONTRACT,
    _is_hash,
    _read_bytes_checked,
    _exact,
    atomic_output_directory,
    canonical,
    checked_output_path,
    checked_path,
    read_json,
    require_disjoint_paths,
    sha256,
)


HERE = Path(os.path.abspath(__file__)).parent
REPOSITORY = HERE.parents[1]
STUDY_ID = CONTRACT["study_id"]
ADAPTER_PATH = REPOSITORY / "src" / "hbqrs" / "runner.py"
CORE_PATH = REPOSITORY / "src" / "hbqrs" / "core.py"
EXECUTOR_PATH = HERE / "executor.py"
FREEZE_PATH = HERE / "execution_freeze.py"
PERSISTED_FILES = ("disclosure.json", "prepared-cell.json", "acknowledgement.json", "zero-charge-route-receipt.json")
SYSTEM_INSTRUCTION = "Return only JSON valid under the supplied response_schema; no tools or side effects."
TrustedGateVerifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _digest(path: Path, *, label: str) -> str:
    try:
        return hashlib.sha256(_read_bytes_checked(checked_path(path, must_exist=True))).hexdigest()
    except ValueError as error:
        raise ValueError(f"HANNA {label} cannot be read") from error


def _stable_identity(path: Path, *, label: str) -> dict[str, Any]:
    candidate = checked_path(path, must_exist=True)
    try:
        metadata = os.stat(candidate, follow_symlinks=False)
    except OSError as error:
        raise ValueError(f"HANNA {label} identity cannot be read") from error
    identity = {"path": str(candidate), "device": metadata.st_dev, "inode": metadata.st_ino, "size": metadata.st_size, "is_file": candidate.is_file()}
    if identity["is_file"]:
        payload = _read_bytes_checked(candidate)
        identity["sha256"] = hashlib.sha256(payload).hexdigest()
        identity["bytes"] = len(payload)
    return identity


def _assert_stable_identity(snapshot: Mapping[str, Mapping[str, Any]]) -> None:
    for label, expected in snapshot.items():
        observed = _stable_identity(Path(expected["path"]), label=label)
        if observed != dict(expected):
            raise ValueError(f"HANNA {label} changed after final pre-contact snapshot")


def _allowed_inventory_digest(root: Path) -> str:
    root = checked_path(root, must_exist=True)
    entries = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        checked_path(child, must_exist=True)
        if child.name == "responses":
            entries.append({"name": child.name, "kind": "runner_mutable_evidence_directory"})
        elif child.is_file():
            raw = _read_bytes_checked(child)
            entries.append({"name": child.name, "kind": "file", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
        elif child.is_dir():
            entries.append({"name": child.name, "kind": "directory", "children": sorted(grandchild.name for grandchild in child.iterdir())})
        else:
            raise ValueError("HANNA prepared root child is not an allowed file or directory")
    return hashlib.sha256(canonical(entries)).hexdigest()


def _acquire_cell_lock(output: Path, *, cell_id: str) -> Path:
    lock = checked_path(output / ".cell-lock")
    try:
        os.mkdir(lock)
    except FileExistsError as error:
        raise ValueError("HANNA cell lock is unavailable; refusing concurrent contact or recovery") from error
    except OSError as error:
        raise ValueError("HANNA cell lock cannot be acquired") from error
    _write_immutable(lock / "claim.json", canonical({"format_version": 1, "study_id": STUDY_ID, "cell_id": cell_id, "kind": "exclusive_cell_contact_lock"}), label="cell lock claim")
    return lock


def _release_cell_lock(lock: Path) -> None:
    checked_path(lock, must_exist=True)
    children = list(lock.iterdir())
    if [child.name for child in children] != ["claim.json"]:
        raise ValueError("HANNA cell lock topology drifted")
    checked_path(children[0], must_exist=True)
    children[0].unlink()
    lock.rmdir()


def _reserve_result_slot(output: Path, *, intent: Mapping[str, Any]) -> Path:
    result_root = checked_path(output / "result")
    if result_root.exists():
        raise ValueError("HANNA result namespace already exists before contact")
    claim = {"format_version": 1, "study_id": STUDY_ID, "kind": "claim_owned_result_slot", "intent_sha256": sha256(intent), "slot": "result"}
    atomic_output_directory(result_root, {"claim.json": canonical(claim).decode("utf-8")})
    return result_root


def _canonical_json(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    payload = _read_bytes_checked(checked_path(path, must_exist=True))
    try:
        value = json.loads(payload.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"HANNA {label} is not canonical JSON") from error
    if not isinstance(value, dict) or canonical(value) != payload:
        raise ValueError(f"HANNA {label} is not canonical JSON")
    return value, payload


def adapter_commitments() -> list[dict[str, Any]]:
    """Pin the reviewed adapter sources a future trusted dispatcher must use."""
    names = (("executor", EXECUTOR_PATH), ("execution_freeze", FREEZE_PATH), ("hbqrs_runner", ADAPTER_PATH), ("hbqrs_core", CORE_PATH))
    result = []
    for name, path in names:
        source = _read_bytes_checked(checked_path(path, must_exist=True))
        if name == "hbqrs_runner" and b"def _call_openai(" not in source:
            raise ValueError("HANNA reviewed OpenAI adapter is unavailable")
        if name == "hbqrs_runner" and b"def _call_grok(" not in source:
            raise ValueError("HANNA reviewed Grok adapter is unavailable")
        result.append({"name": name, "path": path.relative_to(REPOSITORY).as_posix(), "bytes": len(source), "sha256": hashlib.sha256(source).hexdigest()})
    parser_path = Path(jsonschema.__file__ or "")
    parser_source = _read_bytes_checked(checked_path(parser_path, must_exist=True))
    runtime = {"implementation": sys.implementation.name, "version": list(sys.version_info[:3]), "cache_tag": sys.implementation.cache_tag}
    result.append({"name": "jsonschema_parser", "path": "environment/jsonschema/__init__.py", "bytes": len(parser_source), "sha256": hashlib.sha256(parser_source).hexdigest()})
    result.append({"name": "python_runtime", "path": "runtime-identity.json", "bytes": len(canonical(runtime)), "sha256": hashlib.sha256(canonical(runtime)).hexdigest()})
    return result


def _cell(freeze: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("HANNA execution cell ID is invalid")
    matches = [dict(row) for row in freeze["schedule"] if row["cell_id"] == cell_id]
    if len(matches) != 1:
        raise ValueError("HANNA execution cell is unknown")
    cell = matches[0]
    if cell["partition"] not in {"train", "development"}:
        raise ValueError("HANNA confirmation is structurally unreachable")
    return cell


def _route(cell: Mapping[str, Any]) -> dict[str, Any]:
    model = cell.get("model")
    if model not in ROUTES:
        raise ValueError("HANNA cell route is unknown")
    route = ROUTES[model]
    if cell.get("provider") != route["provider"] or route["paid_api"] is not False:
        raise ValueError("HANNA cell route drifted")
    return dict(route)


def _trusted_gate(*, verifier: TrustedGateVerifier, gate_kind: str, path: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    raw = _read_bytes_checked(checked_path(path, must_exist=True))
    try:
        verdict = dict(verifier({"format_version": 1, "study_id": STUDY_ID, "gate_kind": gate_kind, "gate_bytes": raw, "gate_sha256": hashlib.sha256(raw).hexdigest(), "expected": dict(expected)}))
    except (TypeError, ValueError) as error:
        raise ValueError("HANNA trusted deployment verifier rejected gate") from error
    _exact(verdict, {"format_version", "study_id", "gate_kind", "gate_sha256", "gate_bytes", "trusted_verifier_id", "trusted_root_id", "verified"}, "trusted deployment verdict")
    if verdict["format_version"] != 1 or verdict["study_id"] != STUDY_ID or verdict["gate_kind"] != gate_kind or verdict["gate_sha256"] != hashlib.sha256(raw).hexdigest() or verdict["gate_bytes"] != len(raw) or verdict["verified"] is not True or not all(isinstance(verdict[key], str) and verdict[key].strip() for key in ("trusted_verifier_id", "trusted_root_id")):
        raise ValueError("HANNA trusted deployment verifier verdict is invalid")
    return verdict


def _external_acknowledgement(path: Path, *, cell: Mapping[str, Any], disclosure_sha256: str, verifier: TrustedGateVerifier) -> dict[str, Any]:
    value, payload = _canonical_json(path, label="external acknowledgement")
    required = {"format_version", "study_id", "kind", "cell_id", "disclosure_sha256", "acknowledged", "attestor"}
    _exact(value, required, "external acknowledgement")
    if value != {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "local_first_remote_execution",
        "cell_id": cell["cell_id"],
        "disclosure_sha256": disclosure_sha256,
        "acknowledged": True,
        "attestor": value["attestor"],
    } or not isinstance(value["attestor"], str) or not value["attestor"].strip():
        raise ValueError("HANNA external acknowledgement is invalid")
    gate = _trusted_gate(verifier=verifier, gate_kind="acknowledgement", path=path, expected=value)
    return {"path": "acknowledgement.json", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "attestor": value["attestor"], "trusted_gate": gate}


def _zero_charge_receipt(path: Path, *, cell: Mapping[str, Any], route: Mapping[str, Any], disclosure_sha256: str, verifier: TrustedGateVerifier) -> dict[str, Any]:
    value, payload = _canonical_json(path, label="trusted zero-charge route receipt")
    required = {"format_version", "study_id", "kind", "cell_id", "disclosure_sha256", "provider", "model", "transport_identity", "reasoning_effort", "paid_api", "no_financial_liability", "issuer"}
    _exact(value, required, "trusted zero-charge route receipt")
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "trusted_zero_charge_route_receipt",
        "cell_id": cell["cell_id"],
        "disclosure_sha256": disclosure_sha256,
        "provider": route["provider"],
        "model": route["model"],
        "transport_identity": route["transport_identity"],
        "reasoning_effort": route["reasoning_effort"],
        "paid_api": False,
        "no_financial_liability": True,
        "issuer": value["issuer"],
    }
    if value != expected or not isinstance(value["issuer"], str) or not value["issuer"].strip():
        raise ValueError("HANNA trusted zero-charge route receipt is invalid")
    gate = _trusted_gate(verifier=verifier, gate_kind="zero_charge_route_receipt", path=path, expected=value)
    return {"path": "zero-charge-route-receipt.json", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "issuer": value["issuer"], "trusted_gate": gate}


def _outbound_wrapper(*, route: Mapping[str, Any], endpoint: str | None, grok_bin: Path | None) -> dict[str, Any]:
    if route["provider"] == "openai":
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError("HANNA OpenAI-compatible endpoint is required before preparation")
        return {"transport": route["transport_identity"], "endpoint": endpoint, "api_key_env": "OPENAI_API_KEY", "system_instruction": SYSTEM_INSTRUCTION, "message_order": ["system:fixed_instruction", "user:exact_provider_ready_task"]}
    if route["provider"] == "xai":
        if grok_bin is None:
            raise ValueError("HANNA Grok executable is required before preparation")
        binary = _read_bytes_checked(checked_path(grok_bin, must_exist=True))
        return {"transport": route["transport_identity"], "executable": {"bytes": len(binary), "sha256": hashlib.sha256(binary).hexdigest()}, "system_instruction": SYSTEM_INSTRUCTION, "flags": ["--model", route["model"], "--reasoning-effort", route["reasoning_effort"], "--output-format", "json", "--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim", "--system-prompt-override", SYSTEM_INSTRUCTION], "runner_parser_policy": {"allow_unattested_reasoning": True, "attestation_absent_result_class": "development_provisional_nonselector_not_promotable"}, "dynamic_values": ["fresh_session_id", "prepared_cell_output_dir", "frozen_schema_path", "exact_provider_ready_task"]}
    raise ValueError("HANNA route provider is unsupported")


def _disclosure(*, freeze: Mapping[str, Any], cell: Mapping[str, Any], route: Mapping[str, Any], payload: bytes, endpoint: str | None, grok_bin: Path | None) -> dict[str, Any]:
    try:
        request = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA provider-ready task is not JSON") from error
    response_schema = request.get("response_schema")
    if not isinstance(response_schema, Mapping):
        raise ValueError("HANNA provider-ready task lacks its schema")
    components = {
        "prompt": request.get("prompt"),
        "writing": request.get("writing"),
        "instruction": request.get("instruction"),
        "profile": request.get("profile"),
        "response_schema": response_schema,
    }
    if not isinstance(components["prompt"], str) or not isinstance(components["writing"], str) or not isinstance(components["instruction"], str) or not isinstance(components["profile"], Mapping):
        raise ValueError("HANNA provider-ready task components drifted")
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "pre_contact_local_first_disclosure",
        "dispatch_authorized": False,
        "execution_freeze_sha256": sha256(freeze),
        "cell": {key: cell[key] for key in ("cell_id", "item_id", "prompt_group_id", "partition", "candidate_id", "provider", "model", "task_payload_sha256", "prompt_sha256", "story_sha256", "candidate_instruction_sha256", "candidate_profile_sha256", "response_schema_sha256")},
        "remote_destination": route,
        "outbound_wrapper": _outbound_wrapper(route=route, endpoint=endpoint, grok_bin=grok_bin),
        "artifacts_leaving_machine": {
            "provider_ready_task": {"encoding": "utf-8", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "text": payload.decode("utf-8")},
            "prompt": {"encoding": "utf-8", "bytes": len(components["prompt"].encode("utf-8")), "sha256": hashlib.sha256(components["prompt"].encode("utf-8")).hexdigest(), "text": components["prompt"]},
            "writing": {"encoding": "utf-8", "bytes": len(components["writing"].encode("utf-8")), "sha256": hashlib.sha256(components["writing"].encode("utf-8")).hexdigest(), "text": components["writing"]},
            "candidate_instruction": {"encoding": "utf-8", "bytes": len(components["instruction"].encode("utf-8")), "sha256": hashlib.sha256(components["instruction"].encode("utf-8")).hexdigest(), "text": components["instruction"]},
            "candidate_profile": {"encoding": "utf-8", "bytes": len(canonical(components["profile"])), "sha256": hashlib.sha256(canonical(components["profile"])).hexdigest(), "json": components["profile"]},
            "response_schema": {"encoding": "utf-8", "bytes": len(canonical(response_schema)), "sha256": hashlib.sha256(canonical(response_schema)).hexdigest(), "json": response_schema},
        },
        "confirmation": "structurally_unreachable",
        "fairness": {"identical_candidate_task_schema_bytes_across_routes": True, "shared_system_instruction": SYSTEM_INSTRUCTION, "route_wrapper_difference": "transport endpoint/executable and their native invocation envelope remain separate, pinned, and never pooled"},
        "native_evidence_policy": "A future trusted dispatcher must persist immutable provider-native request, response, and session artifacts; this local pre-contact projection is non-promotable.",
    }


def _prepared_manifest(*, freeze: Mapping[str, Any], cell: Mapping[str, Any], route: Mapping[str, Any], disclosure: Mapping[str, Any], acknowledgement: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "prepared_hanna_development_cell",
        "state": "prepared_not_dispatched",
        "dispatch_authorized": False,
        "execution_freeze_sha256": sha256(freeze),
        "cell_id": cell["cell_id"],
        "partition": cell["partition"],
        "route": route,
        "disclosure_sha256": sha256(disclosure),
        "external_acknowledgement": dict(acknowledgement),
        "trusted_zero_charge_route_receipt": dict(receipt),
        "adapter_commitments": adapter_commitments(),
        "native_provider_evidence": {"status": "absent_pre_contact", "acceptance": "only provider-native artifacts may support a future derived receipt; locally minted projections are non-promotable"},
        "confirmation": "structurally_unreachable",
    }


def preview_cell_disclosure(*, freeze_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, endpoint: str | None = None, grok_bin: Path | None = None) -> dict[str, Any]:
    """Build one exact local-first disclosure without touching any attempt root or provider."""
    require_disjoint_paths(freeze_path, frozen_successor_path, hanna_csv_path, *( [grok_bin] if grok_bin is not None else []))
    freeze = read_json(freeze_path)
    validate_execution_freeze(freeze, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    cell = _cell(freeze, cell_id)
    route = _route(cell)
    payload = provider_ready_payload(freeze=freeze, cell_id=cell_id, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    return _disclosure(freeze=freeze, cell=cell, route=route, payload=payload, endpoint=endpoint, grok_bin=grok_bin)


def _existing_prepared(path: Path, *, freeze: Mapping[str, Any], cell: Mapping[str, Any], route: Mapping[str, Any], acknowledgement: Mapping[str, Any], receipt: Mapping[str, Any], disclosure: Mapping[str, Any]) -> dict[str, Any]:
    root = checked_path(path, must_exist=True)
    if not root.is_dir():
        raise ValueError("HANNA prepared cell root is invalid")
    for child in root.rglob("*"):
        checked_path(child, must_exist=True)
    _validate_root_inventory(root)
    names = sorted(child.name for child in root.iterdir())
    permitted = set(PERSISTED_FILES) | {"intent.json", "result", "response-schema.json", "responses", ".cell-lock"}
    if not set(names).issubset(permitted) or not set(PERSISTED_FILES).issubset(names):
        raise ValueError("HANNA existing prepared cell is orphaned or incomplete; refusing recovery or resend")
    persisted_disclosure, disclosure_bytes = _canonical_json(root / "disclosure.json", label="persisted disclosure")
    prepared, prepared_bytes = _canonical_json(root / "prepared-cell.json", label="persisted prepared cell")
    expected = _prepared_manifest(freeze=freeze, cell=cell, route=route, disclosure=disclosure, acknowledgement=acknowledgement, receipt=receipt)
    if persisted_disclosure != disclosure or prepared != expected or prepared["disclosure_sha256"] != hashlib.sha256(disclosure_bytes).hexdigest():
        raise ValueError("HANNA existing prepared cell cannot be recomputed; refusing recovery or resend")
    for name, commitment in (("acknowledgement.json", acknowledgement), ("zero-charge-route-receipt.json", receipt)):
        raw = _read_bytes_checked(root / name)
        if len(raw) != commitment["bytes"] or hashlib.sha256(raw).hexdigest() != commitment["sha256"]:
            raise ValueError("HANNA persisted external gate binding drifted")
    if hashlib.sha256(disclosure_bytes).hexdigest() != expected["disclosure_sha256"] or not prepared_bytes:
        raise ValueError("HANNA existing prepared cell is invalid")
    return prepared


def _write_immutable(path: Path, payload: bytes, *, label: str) -> None:
    path = checked_path(path)
    if path.exists():
        raise ValueError(f"HANNA immutable {label} already exists")
    checked_path(path.parent, must_exist=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        raise ValueError(f"HANNA cannot create immutable {label}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        raise
    checked_path(path, must_exist=True)


def _load_prepared_for_dispatch(output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = checked_path(output, must_exist=True)
    if not root.is_dir():
        raise ValueError("HANNA prepared cell root is invalid")
    _validate_root_inventory(root)
    prepared, _ = _canonical_json(root / "prepared-cell.json", label="prepared cell")
    disclosure, _ = _canonical_json(root / "disclosure.json", label="persisted disclosure")
    if prepared.get("state") != "prepared_not_dispatched" or prepared.get("dispatch_authorized") is not False:
        raise ValueError("HANNA prepared cell state is invalid")
    if prepared.get("disclosure_sha256") != sha256(disclosure):
        raise ValueError("HANNA prepared cell disclosure binding drifted")
    if prepared.get("adapter_commitments") != adapter_commitments():
        raise ValueError("HANNA prepared adapter binding drifted")
    for name in PERSISTED_FILES:
        checked_path(root / name, must_exist=True)
    return prepared, disclosure


def _validate_root_inventory(root: Path) -> None:
    root = checked_path(root, must_exist=True)
    names = {child.name for child in root.iterdir()}
    allowed = set(PERSISTED_FILES) | {"intent.json", "result", "responses", "response-schema.json", ".cell-lock"}
    if not set(PERSISTED_FILES).issubset(names) or not names.issubset(allowed):
        raise ValueError("HANNA prepared root has an unknown or missing immutable entry")
    for child in root.iterdir():
        checked_path(child, must_exist=True)
    intent = "intent.json" in names
    result = "result" in names
    lock = ".cell-lock" in names
    evidence = names - set(PERSISTED_FILES) - {"intent.json", "result", "responses", "response-schema.json", ".cell-lock"}
    if not intent and (result or evidence or lock):
        raise ValueError("HANNA prepared root has orphan provider evidence before intent")
    if intent and not result:
        raise ValueError("HANNA prior contact intent is unresolved; refusing resend")
    if result and not intent:
        raise ValueError("HANNA result without intent is an orphan; refusing recovery or resend")
    if lock:
        raise ValueError("HANNA cell lock is held or stale; refusing recovery or resend")
    if result:
        result_root = checked_path(root / "result", must_exist=True)
        if not result_root.is_dir() or not (result_root / "claim.json").is_file():
            raise ValueError("HANNA result namespace is not claim-owned")


def _intent(*, prepared: Mapping[str, Any], disclosure: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_contact_intent",
        "cell_id": prepared["cell_id"],
        "state": "contact_started_no_resend",
        "dispatch_authorized": True,
        "prepared_cell_sha256": sha256(prepared),
        "disclosure_sha256": sha256(disclosure),
        "route": prepared["route"],
        "adapter_commitments": prepared["adapter_commitments"],
        "provider_calls_made_before_intent": 0,
    }


def _runner():
    source_root = str(REPOSITORY / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    try:
        from hbqrs import runner
    except ImportError as error:
        raise ValueError("HANNA reviewed runner adapter cannot be imported") from error
    if _digest(ADAPTER_PATH, label="runner adapter") != next(item["sha256"] for item in adapter_commitments() if item["name"] == "hbqrs_runner"):
        raise ValueError("HANNA runner adapter commitment drifted")
    return runner


def _dispatch_via_runner(*, route: Mapping[str, Any], payload: bytes, output: Path, wrapper: Mapping[str, Any], grok_bin: Path | None, timeout: float, before_provider_attempt: Callable[[], None]) -> tuple[str, dict[str, Any]]:
    """Use the reviewed HBQ-RS adapters; this is the only remote-call surface."""
    runner = _runner()
    prompt = payload.decode("utf-8")
    if route["provider"] == "openai":
        endpoint = wrapper.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            raise ValueError("HANNA prepared OpenAI-compatible endpoint is invalid")
        return runner._call_openai(
            endpoint=endpoint,
            api_key_env="OPENAI_API_KEY",
            model=route["model"],
            system_prompt=SYSTEM_INSTRUCTION,
            user_prompt=prompt,
            temperature=None,
            allow_model_mismatch=False,
            timeout=timeout,
            before_provider_attempt=before_provider_attempt,
        )
    if route["provider"] == "xai":
        if grok_bin is None:
            raise ValueError("HANNA prepared Grok executable is unavailable")
        binary = _read_bytes_checked(checked_path(grok_bin, must_exist=True))
        if wrapper.get("executable") != {"bytes": len(binary), "sha256": hashlib.sha256(binary).hexdigest()}:
            raise ValueError("HANNA Grok executable substitution was rejected")
        schema_path = output / "response-schema.json"
        schema = json.loads(prompt)["response_schema"]
        if schema_path.exists():
            if _read_bytes_checked(schema_path) != canonical(schema):
                raise ValueError("HANNA precontact response schema binding drifted")
        else:
            _write_immutable(schema_path, canonical(schema), label="response schema")
        return runner._call_grok(
            executable=str(grok_bin),
            model=route["model"],
            reasoning=route["reasoning_effort"],
            prompt=prompt,
            output_dir=output,
            response_schema=schema_path,
            batch_number=1,
            timeout=timeout,
            attempt_number=1,
            allow_unattested_reasoning=True,
            system_prompt_override=SYSTEM_INSTRUCTION,
            before_provider_attempt=before_provider_attempt,
        )
    raise ValueError("HANNA route provider is unsupported")


def _validate_model_response(content: str, *, disclosure: Mapping[str, Any]) -> dict[str, Any]:
    try:
        response = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("HANNA provider response is not JSON") from error
    schema = disclosure["artifacts_leaving_machine"]["response_schema"]["json"]
    errors = sorted(Draft202012Validator(schema).iter_errors(response), key=lambda error: list(error.path))
    if errors:
        raise ValueError(f"HANNA provider response does not match frozen schema: {errors[0].message}")
    return response


def dispatch_prepared_cell(*, freeze_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, cell_id: str, allow_remote: bool, trusted_gate_verifier: TrustedGateVerifier, endpoint: str | None = None, grok_bin: Path | None = None, timeout: float = 600.0) -> dict[str, Any]:
    """Dispatch exactly one prepared train/development cell; no resend follows any written intent."""
    if allow_remote is not True:
        raise ValueError("HANNA dispatch requires explicit --allow-remote")
    output = checked_output_path(output_root / cell_id)
    prepared, disclosure = _load_prepared_for_dispatch(output)
    require_disjoint_paths(freeze_path, frozen_successor_path, hanna_csv_path, output)
    freeze = read_json(freeze_path)
    validate_execution_freeze(freeze, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    cell = _cell(freeze, cell_id)
    route = _route(cell)
    payload_bytes = provider_ready_payload(freeze=freeze, cell_id=cell_id, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    expected_disclosure = _disclosure(freeze=freeze, cell=cell, route=route, payload=payload_bytes, endpoint=endpoint, grok_bin=grok_bin)
    if prepared["cell_id"] != cell_id or prepared["partition"] not in {"train", "development"}:
        raise ValueError("HANNA confirmation is structurally unreachable")
    if prepared.get("execution_freeze_sha256") != sha256(freeze) or disclosure != expected_disclosure:
        raise ValueError("HANNA prepared freeze, request, or route wrapper drifted")
    acknowledgement = _external_acknowledgement(output / "acknowledgement.json", cell=cell, disclosure_sha256=sha256(disclosure), verifier=trusted_gate_verifier)
    receipt = _zero_charge_receipt(output / "zero-charge-route-receipt.json", cell=cell, route=route, disclosure_sha256=sha256(disclosure), verifier=trusted_gate_verifier)
    expected_prepared = _prepared_manifest(freeze=freeze, cell=cell, route=route, disclosure=disclosure, acknowledgement=acknowledgement, receipt=receipt)
    if prepared != expected_prepared:
        raise ValueError("HANNA prepared cell gate or provenance binding drifted")
    intent_path = output / "intent.json"
    if intent_path.exists():
        result_root = output / "result"
        if not result_root.is_dir() or not (result_root / "attempt-result.json").exists():
            raise ValueError("HANNA prior contact intent is unresolved; refusing resend")
        claim, _ = _canonical_json(result_root / "claim.json", label="result claim")
        if claim != {"format_version": 1, "study_id": STUDY_ID, "kind": "claim_owned_result_slot", "intent_sha256": _digest(intent_path, label="contact intent"), "slot": "result"}:
            raise ValueError("HANNA result claim does not bind the contact intent")
        result, _ = _canonical_json(result_root / "attempt-result.json", label="attempt result")
        if result.get("intent_sha256") != _digest(intent_path, label="contact intent") or result.get("study_id") != STUDY_ID:
            raise ValueError("HANNA settled attempt intent binding drifted")
        if result.get("state") == "provider_returned_unpromotable":
            _exact(result, {"format_version", "study_id", "kind", "state", "intent_sha256", "provider_native_message_sha256", "model_content_sha256", "response_sha256", "route_evidence", "receipt"}, "settled attempt result")
            for name, field in (("provider-native-message.json", "provider_native_message_sha256"), ("model-content.txt", "model_content_sha256")):
                if _digest(result_root / name, label=name) != result[field]:
                    raise ValueError("HANNA settled native evidence binding drifted")
        elif result.get("state") == "contact_outcome_unresolved_no_resend":
            _exact(result, {"format_version", "study_id", "kind", "state", "intent_sha256", "error_type", "provider_failure_sha256", "provider_failure_content", "receipt"}, "unresolved attempt result")
            if _digest(result_root / "provider-failure.json", label="provider failure") != result["provider_failure_sha256"]:
                raise ValueError("HANNA unresolved native failure binding drifted")
            failure, _ = _canonical_json(result_root / "provider-failure.json", label="provider failure")
            if failure.get("content") != result["provider_failure_content"]:
                raise ValueError("HANNA unresolved failure-content binding drifted")
            content_binding = result["provider_failure_content"]
            if content_binding is not None:
                _exact(content_binding, {"path", "bytes", "sha256"}, "provider failure content")
                if content_binding["path"] != "provider-failure-content.txt" or _digest(result_root / content_binding["path"], label="provider failure content") != content_binding["sha256"] or len(_read_bytes_checked(result_root / content_binding["path"])) != content_binding["bytes"]:
                    raise ValueError("HANNA unresolved provider failure content was tampered")
        else:
            raise ValueError("HANNA attempt result state is invalid")
        return {"cell_id": cell_id, "state": result.get("state"), "provider_calls_made": 0, "resumed": True}
    lock = _acquire_cell_lock(output, cell_id=cell_id)
    intent = _intent(prepared=prepared, disclosure=disclosure)
    _write_immutable(intent_path, canonical(intent), label="contact intent")
    result_root = _reserve_result_slot(output, intent=intent)
    responses = checked_path(output / "responses")
    responses.mkdir(exist_ok=False)
    checked_path(responses, must_exist=True)
    payload = disclosure["artifacts_leaving_machine"]["provider_ready_task"]
    if not isinstance(payload, Mapping) or not isinstance(payload.get("text"), str):
        raise ValueError("HANNA prepared task payload is invalid")
    text = payload["text"]
    payload_bytes = text.encode("utf-8")
    if len(payload_bytes) != payload["bytes"] or hashlib.sha256(payload_bytes).hexdigest() != payload["sha256"]:
        raise ValueError("HANNA prepared task payload binding drifted")
    final_snapshot_paths = {
        "freeze": freeze_path,
        "frozen successor": frozen_successor_path,
        "HANNA CSV": hanna_csv_path,
        "prepared root": output,
        "prepared manifest": output / "prepared-cell.json",
        "disclosure": output / "disclosure.json",
        "acknowledgement": output / "acknowledgement.json",
        "zero-charge receipt": output / "zero-charge-route-receipt.json",
        "contact intent": intent_path,
        "result namespace": result_root,
        "result claim": result_root / "claim.json",
        "cell lock": lock,
        "executor": EXECUTOR_PATH,
        "execution freeze module": FREEZE_PATH,
        "runner adapter": ADAPTER_PATH,
        "HBQ core": CORE_PATH,
    }
    if prepared["route"]["provider"] == "xai":
        if grok_bin is None:
            raise ValueError("HANNA prepared Grok executable is unavailable")
        final_snapshot_paths["Grok executable"] = grok_bin
        schema = disclosure["artifacts_leaving_machine"]["response_schema"]["json"]
        _write_immutable(output / "response-schema.json", canonical(schema), label="response schema")
        final_snapshot_paths["response schema"] = output / "response-schema.json"
    final_snapshot = {label: _stable_identity(path, label=label) for label, path in final_snapshot_paths.items()}
    _assert_stable_identity(final_snapshot)
    inventory_digest = _allowed_inventory_digest(output)

    def before_provider_attempt() -> None:
        _assert_stable_identity(final_snapshot)
        if _allowed_inventory_digest(output) != inventory_digest:
            raise ValueError("HANNA allowed-child inventory changed before physical provider contact")

    try:
        content, native_message = _dispatch_via_runner(route=prepared["route"], payload=payload_bytes, output=output, wrapper=disclosure["outbound_wrapper"], grok_bin=grok_bin, timeout=timeout, before_provider_attempt=before_provider_attempt)
        response = _validate_model_response(content, disclosure=disclosure)
        _write_immutable(result_root / "provider-native-message.json", canonical(native_message), label="provider-native message")
        _write_immutable(result_root / "model-content.txt", content.encode("utf-8"), label="model content")
        result = {
            "format_version": 1,
            "study_id": STUDY_ID,
            "kind": "unpromotable_provider_return",
            "state": "provider_returned_unpromotable",
            "intent_sha256": _digest(intent_path, label="contact intent"),
            "provider_native_message_sha256": _digest(result_root / "provider-native-message.json", label="provider-native message"),
            "model_content_sha256": _digest(result_root / "model-content.txt", label="model content"),
            "response_sha256": hashlib.sha256(canonical(response)).hexdigest(),
            "route_evidence": {"evidence_class": prepared["route"]["evidence_class"], "reasoning_attested": native_message.get("reasoning_attested") if prepared["route"]["provider"] == "xai" else None, "reasoning_attestation": native_message.get("reasoning_attestation") if prepared["route"]["provider"] == "xai" else "not_applicable"},
            "receipt": "absent: this executor cannot derive a promotable receipt without exact raw-wire/session artifact recomputation",
        }
    except BaseException as error:
        provider_record = getattr(error, "provider_record", None)
        content = getattr(error, "content", None)
        content_binding = None
        if isinstance(content, str):
            content_bytes = content.encode("utf-8")
            content_binding = {"path": "provider-failure-content.txt", "bytes": len(content_bytes), "sha256": hashlib.sha256(content_bytes).hexdigest()}
            _write_immutable(result_root / "provider-failure-content.txt", content.encode("utf-8"), label="provider failure content")
        failure = {"format_version": 1, "study_id": STUDY_ID, "exception_type": type(error).__name__, "message": str(error), "retryable": getattr(error, "retryable", None), "attempt_outcome": getattr(error, "attempt_outcome", None), "provider_record": dict(provider_record) if isinstance(provider_record, Mapping) else None, "content": content_binding}
        _write_immutable(result_root / "provider-failure.json", canonical(failure), label="provider failure")
        result = {
            "format_version": 1,
            "study_id": STUDY_ID,
            "kind": "unpromotable_provider_attempt",
            "state": "contact_outcome_unresolved_no_resend",
            "intent_sha256": _digest(intent_path, label="contact intent"),
            "error_type": type(error).__name__,
            "provider_failure_sha256": _digest(result_root / "provider-failure.json", label="provider failure"),
            "provider_failure_content": content_binding,
            "receipt": "absent: preserve intent and resolve manually; retry is prohibited",
        }
        _write_immutable(result_root / "attempt-result.json", canonical(result), label="attempt result")
        _release_cell_lock(lock)
        raise
    _write_immutable(result_root / "attempt-result.json", canonical(result), label="attempt result")
    _release_cell_lock(lock)
    return {"cell_id": cell_id, "state": result["state"], "provider_calls_made": 1, "resumed": False}


def prepare_cell(*, freeze_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, cell_id: str, output_root: Path, acknowledgement_path: Path, zero_charge_route_receipt_path: Path, trusted_gate_verifier: TrustedGateVerifier, endpoint: str | None = None, grok_bin: Path | None = None) -> dict[str, Any]:
    """Create or exactly recover one pre-contact development-cell directory; never call a provider."""
    require_disjoint_paths(freeze_path, frozen_successor_path, hanna_csv_path, output_root, acknowledgement_path, zero_charge_route_receipt_path)
    freeze = read_json(freeze_path)
    validate_execution_freeze(freeze, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    cell = _cell(freeze, cell_id)
    route = _route(cell)
    payload = provider_ready_payload(freeze=freeze, cell_id=cell_id, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    if hashlib.sha256(payload).hexdigest() != cell["task_payload_sha256"]:
        raise ValueError("HANNA provider-ready payload drifted")
    disclosure = _disclosure(freeze=freeze, cell=cell, route=route, payload=payload, endpoint=endpoint, grok_bin=grok_bin)
    acknowledgement = _external_acknowledgement(acknowledgement_path, cell=cell, disclosure_sha256=sha256(disclosure), verifier=trusted_gate_verifier)
    receipt = _zero_charge_receipt(zero_charge_route_receipt_path, cell=cell, route=route, disclosure_sha256=sha256(disclosure), verifier=trusted_gate_verifier)
    output = checked_output_path(output_root / cell_id)
    if output.exists():
        return _existing_prepared(output, freeze=freeze, cell=cell, route=route, acknowledgement=acknowledgement, receipt=receipt, disclosure=disclosure)
    prepared = _prepared_manifest(freeze=freeze, cell=cell, route=route, disclosure=disclosure, acknowledgement=acknowledgement, receipt=receipt)
    acknowledgement_bytes = _read_bytes_checked(acknowledgement_path)
    receipt_bytes = _read_bytes_checked(zero_charge_route_receipt_path)
    atomic_output_directory(output, {
        "disclosure.json": canonical(disclosure).decode("utf-8"),
        "prepared-cell.json": canonical(prepared).decode("utf-8"),
        "acknowledgement.json": acknowledgement_bytes.decode("utf-8"),
        "zero-charge-route-receipt.json": receipt_bytes.decode("utf-8"),
    })
    return prepared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-freeze", required=True, type=Path)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--acknowledgement", required=True, type=Path)
    parser.add_argument("--zero-charge-route-receipt", required=True, type=Path)
    parser.add_argument("--dispatch", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--endpoint")
    parser.add_argument("--grok-bin", default="grok")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()
    parser.error("CLI cannot supply a trusted deployment gate verifier; inject prepare_cell/dispatch_prepared_cell from an approved local deployment integration")


if __name__ == "__main__":
    raise SystemExit(main())
