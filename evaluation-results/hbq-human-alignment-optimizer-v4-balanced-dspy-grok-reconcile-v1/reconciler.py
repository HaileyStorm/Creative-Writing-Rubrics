#!/usr/bin/env python3
"""Provider-free reconciliation of ten immutable terminal Grok descendant roots."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v1"
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "540d402683f5280e8e9c734756aa01e96e65964e077d724d38dfcb05db479b3d"
SOURCE_EXECUTOR_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2" / "executor.py"
SOURCE_EXECUTOR_SHA256 = "475f5d2fb02cdddcf5b14810d25ef63bd166c85f129dc64106b443f33895fbc4"
GROK_ADAPTER_SHA256 = "e12e8864094d96d9930602f42588238b94f506b4815f80f0215b7b5290b7b599"
PREPARATION_FILE_SHA256 = "dd6dc97e7474d169eef384cafa14ab71237a6b45ea572b8bb9829ca6f8bb3e56"
PREPARATION_SHA256 = "b65b42f839b61550036acd32b4fb151cc1a353fd76235ae9cc1739c3e93e8c60"
SOURCE_CONTROL_SHA256 = {"sample-01": "c014b6b98621e5d2038d40348059c449ab9b71fc520d2ef3d1108f9abb2d607d", "sample-02": "48eca4177647434146ed2c8ccd78a8bff317f6477923ddf2a9ff036948d8d31a", "sample-03": "b80814b5d39144ec913955da06b59ae86d8ba912d8a08d12409b78070e3e3115", "sample-04": "aaaba1f5753ebd028bce3fba1fdff6be215688f2c1d72cab59577138fb09095f", "sample-05": "4bb1211b1948500232369ab469d3fe4d13ed4b6587a77018946f9294f4740d31", "sample-06": "296a553bbf3827995ac005dd7c84c50f3645a302c6ddc1cfb5d125e67a43de0b", "sample-07": "9c254f11e600146b9e45a006313c9e3cc95788b121164881956b9172948b9e1e", "sample-08": "ca91bda3773d95b7637f103b1f2a6b8811d26b4c564bbba110ec412f0bb5a1ff", "sample-09": "dd91640a6aceb933b00df4000497d9378fe204ddcca870e98acc9dbe8dcd1150", "sample-10": "ae972aa053f5bfe209f477ef1525504ca89d9a9185b5bcbfdc515e696e8c51fb"}
SOURCE_FILES = frozenset({"dspy-input-preparation.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json", "launch-intent.json", "adapter-stdout.bin", "result.json"})
OUTPUT_FIELDS = frozenset({"descendant_instruction_base64", "descendant_profile_base64"})
ASCII_WHITESPACE = frozenset(b"\t\n\v\f\r ")
TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]
SYSTEM_PROMPT = "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."


def project_canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def adapter_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        return False
    return directory is None or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def stable_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not _plain(current):
            raise ValueError(f"reconcile v1 unsafe path: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("reconcile v1 source identity drifted")
        raw = handle.read(); after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("reconcile v1 source changed during read")
    return raw


def _reject_constant(value: str) -> None:
    raise ValueError(f"reconcile v1 nonfinite JSON value: {value}")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"reconcile v1 duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(raw: bytes, *, label: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"reconcile v1 invalid {label}") from error


def _canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    value = strict_json(raw, label=label)
    if not isinstance(value, dict) or project_canonical(value) != raw:
        raise ValueError(f"reconcile v1 {label} is not project canonical")
    return value


def _hex(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"reconcile v1 invalid {label}")
    return value


def _sample(number: int) -> str:
    if not 1 <= number <= 10:
        raise ValueError("reconcile v1 samples are 1 through 10")
    return f"sample-{number:02d}"


def _contract() -> dict[str, Any]:
    raw = stable_bytes(CONTRACT_PATH)
    if not CONTRACT_SHA256 or sha256(raw) != CONTRACT_SHA256:
        raise ValueError("reconcile v1 study contract drifted")
    if sha256(stable_bytes(SOURCE_EXECUTOR_PATH)) != SOURCE_EXECUTOR_SHA256:
        raise ValueError("reconcile v1 source executor drifted")
    value = _canonical_object(raw, label="study contract")
    expected = {"authority", "format_version", "kind", "source", "study_id"}
    if set(value) != expected or value.get("format_version") != 1 or value.get("kind") != "balanced_dspy_grok_v2_terminal_reconciliation" or value.get("study_id") != STUDY_ID or value.get("authority") != {"confirmation": {"cells": 0, "status": "unopened"}, "evaluation": False, "local_only": True, "optimizer_runtime": False} or value.get("source") != {"adapter_sha256": GROK_ADAPTER_SHA256, "executor_sha256": SOURCE_EXECUTOR_SHA256, "preparation_file_sha256": PREPARATION_FILE_SHA256, "study_id": SOURCE_STUDY_ID, "terminal_adapter_stdout_sha256": SOURCE_CONTROL_SHA256}:
        raise ValueError("reconcile v1 study contract semantics drifted")
    return value


def _safe_output_ancestry(path: Path) -> None:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True):
            raise ValueError(f"reconcile v1 output ancestry is unsafe: {current}")


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _b64(value: Any, *, label: str) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(value, str):
        raise ValueError(f"reconcile v1 {label} is not base64 text")
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(f"reconcile v1 {label} contains non-ASCII text") from error
    removed = [{"offset": index, "byte": f"0x{byte:02x}"} for index, byte in enumerate(raw) if byte in ASCII_WHITESPACE]
    stripped = bytes(byte for byte in raw if byte not in ASCII_WHITESPACE)
    try:
        decoded = base64.b64decode(stripped, validate=True)
    except ValueError as error:
        raise ValueError(f"reconcile v1 {label} is invalid base64") from error
    encoded = base64.b64encode(decoded)
    if encoded != stripped:
        raise ValueError(f"reconcile v1 {label} base64 does not roundtrip")
    return decoded, {"raw_encoded_sha256": sha256(raw), "removed_ascii_whitespace": removed, "stripped_encoded_sha256": sha256(stripped), "decoded_sha256": sha256(decoded), "canonical_base64": encoded.decode("ascii")}


def _prompt(preparation: Mapping[str, Any]) -> bytes:
    request = {"signature": "BalancedDescendantSignature", "inputs": dict(preparation["inputs"]), "output_fields": sorted(OUTPUT_FIELDS), "constraints": ["Return only the required JSON object.", "Create versioned descendants only.", "No tools, web, plans, memory, or subagents."]}
    return ("Development-only HANNA descendant generation.\n" + project_canonical(request).decode("utf-8")).encode("utf-8")


def _schema() -> bytes:
    return project_canonical({"$schema_version": 1, "type": "object", "additionalProperties": False, "required": sorted(OUTPUT_FIELDS), "properties": {field: {"type": "string", "minLength": 1} for field in sorted(OUTPUT_FIELDS)}})


def _preparation(raw: bytes) -> dict[str, Any]:
    if sha256(raw) != PREPARATION_FILE_SHA256:
        raise ValueError("reconcile v1 preparation hash drifted")
    value = _canonical_object(raw, label="preparation")
    expected = {"format_version", "study_id", "kind", "dspy_program", "inputs", "inputs_sha256", "training_result_sha256", "training_diagnostics_sha256", "dependencies", "provider_calls_made", "dispatch_authority", "runtime_authority", "confirmation", "preparation_sha256"}
    if set(value) != expected or value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1" or value.get("kind") != "dspy_predict_input_preparation" or value.get("dspy_program") != "Predict(BalancedDescendantSignature)@3.3.1" or value.get("preparation_sha256") != PREPARATION_SHA256 or value.get("provider_calls_made") != 0 or value.get("dispatch_authority") != "none_governed_executor_required" or value.get("runtime_authority") != "none" or value.get("confirmation") != {"status": "unopened", "cells": 0}:
        raise ValueError("reconcile v1 preparation semantics drifted")
    inputs = value.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {"parent_candidate_id", "parent_instruction_base64", "parent_profile_base64", "training_result_base64", "training_diagnostics_base64"} or value.get("inputs_sha256") != sha256(project_canonical(dict(inputs))) or not isinstance(inputs["parent_candidate_id"], str) or not inputs["parent_candidate_id"]:
        raise ValueError("reconcile v1 preparation inputs drifted")
    return value


def _source_snapshot(root: Path) -> tuple[dict[str, bytes], str]:
    if not root.is_dir() or not _plain(root, directory=True):
        raise ValueError("reconcile v1 source root is unsafe")
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != SOURCE_FILES or any(not _plain(entry, directory=False) for entry in entries.values()):
        raise ValueError("reconcile v1 source inventory is incomplete or unsafe")
    raw = {name: stable_bytes(entries[name]) for name in sorted(SOURCE_FILES)}
    commitment = {name: sha256(value) for name, value in raw.items()}
    return raw, sha256(project_canonical(commitment))


def _prepared_artifacts(raw: Mapping[str, bytes], sample: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes, bytes]:
    preparation_raw = raw["dspy-input-preparation.json"]
    preparation = _preparation(preparation_raw)
    prompt, schema = raw["prompt-request.bin"], raw["response-schema.json"]
    if prompt != _prompt(preparation) or schema != _schema():
        raise ValueError("reconcile v1 persisted prompt or schema drifted")
    disclosure = _canonical_object(raw["disclosure.json"], label="disclosure")
    acknowledgement = _canonical_object(raw["authorization-acknowledgement.json"], label="acknowledgement")
    proof = _canonical_object(raw["zero-charge-route-proof.json"], label="route proof")
    prepared = _canonical_object(raw["prepared.json"], label="prepared record")
    intent = _canonical_object(raw["launch-intent.json"], label="launch intent")
    route = disclosure.get("route_identity")
    evidence = proof.get("route_evidence")
    if not isinstance(route, Mapping) or dict(route) != {"name": "grok-build-grok-4.6", "provider": "xai_grok_build", "model": "grok-4.6", "adapter": "grok_exec", "destination": "xai_grok_build_subscription"} or not isinstance(evidence, Mapping):
        raise ValueError("reconcile v1 source route identity drifted")
    evidence = dict(evidence)
    if set(evidence) != {"cli_version_identity_sha256", "cost_evidence_hash", "grok_cli_version", "grok_command_identity_sha256", "registry_sha256", "route_name", "route_sha256", "subscription_receipt_hash"} or evidence.get("route_name") != route["name"] or any(not isinstance(value, str) or not value for value in evidence.values()) or any(not re.fullmatch(r"[0-9a-f]{64}", evidence[key]) for key in evidence if key not in {"grok_cli_version", "route_name"}):
        raise ValueError("reconcile v1 source route evidence drifted")
    expected_disclosure = {"format_version": 2, "study_id": SOURCE_STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "sample_id": sample, "route_identity": dict(route), "prompt": {"bytes": len(prompt), "sha256": sha256(prompt), "text": prompt.decode("utf-8")}, "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")}, "system_prompt_override": SYSTEM_PROMPT, "tool_free_argv": TOOL_FREE_ARGV, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    expected_acknowledgement = {"format_version": 2, "study_id": SOURCE_STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "sample_id": sample, "acknowledgement_sha256": acknowledgement.get("acknowledgement_sha256"), "disclosure_sha256": sha256(raw["disclosure.json"]), "destination": route["destination"]}
    expected_proof = {"format_version": 2, "study_id": SOURCE_STUDY_ID, "kind": "current_zero_charge_route_proof", "sample_id": sample, "route_evidence": evidence, "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    if disclosure != expected_disclosure or acknowledgement != expected_acknowledgement or not re.fullmatch(r"[0-9a-f]{64}", str(acknowledgement.get("acknowledgement_sha256"))) or proof != expected_proof:
        raise ValueError("reconcile v1 source disclosure, acknowledgement, or proof drifted")
    parent_instruction, _ = _b64(preparation["inputs"]["parent_instruction_base64"], label="parent instruction")
    parent_profile, _ = _b64(preparation["inputs"]["parent_profile_base64"], label="parent profile")
    expected_prepared = {"format_version": 2, "study_id": SOURCE_STUDY_ID, "kind": "balanced_dspy_grok_v2_preparation", "sample_id": sample, "preparation_file_sha256": sha256(preparation_raw), "preparation_sha256": preparation["preparation_sha256"], "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "capture_wrapper_sha256": "012144f9e3cb328131111bfc32bcab79ec5581c1020d0681ee883f02bfc58dc8", "parent_candidate_id": preparation["inputs"]["parent_candidate_id"], "parent_instruction_sha256": sha256(parent_instruction), "parent_profile_sha256": sha256(parent_profile), "route_evidence": evidence, "disclosure_sha256": sha256(raw["disclosure.json"]), "acknowledgement_sha256": sha256(raw["authorization-acknowledgement.json"]), "route_proof_sha256": sha256(raw["zero-charge-route-proof.json"]), "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    expected_intent = {"format_version": 2, "study_id": SOURCE_STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "prompt_sha256": sha256(prompt), "route_evidence": evidence, "native_contact_proven": False}
    if prepared != expected_prepared or intent != expected_intent:
        raise ValueError("reconcile v1 source prepared or launch binding drifted")
    terminal = _canonical_object(raw["result.json"], label="terminal result")
    expected_terminal = {"format_version": 2, "study_id": SOURCE_STUDY_ID, "kind": "reconcile_required_after_process_launch", "sample_id": sample, "adapter_stdout_sha256": None, "detail": "ValueError", "provider_calls_made": None, "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown"}
    if terminal != expected_terminal:
        raise ValueError("reconcile v1 source terminal state drifted")
    return preparation, evidence, parent_instruction, parent_profile, prompt


def _completed_control(raw: bytes, *, prompt: bytes, evidence: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    control = strict_json(raw, label="adapter stdout")
    if not isinstance(control, dict) or set(control) != {"control", "result"} or control.get("control") != {"version": 1, "state": "completed"}:
        raise ValueError("reconcile v1 adapter control is not completed")
    result = control.get("result")
    if not isinstance(result, dict) or set(result) != {"schema_version", "request_hash", "output", "output_hash", "runtime"} or result.get("schema_version") != 1 or result.get("request_hash") != sha256(adapter_canonical({"prompt": prompt.decode("utf-8")})):
        raise ValueError("reconcile v1 adapter request binding drifted")
    output = result.get("output")
    if not isinstance(output, dict) or set(output) != OUTPUT_FIELDS or any(not isinstance(output[field], str) or not output[field] for field in OUTPUT_FIELDS) or result.get("output_hash") != sha256(adapter_canonical(output)):
        raise ValueError("reconcile v1 adapter output binding drifted")
    runtime = result.get("runtime")
    required = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version", "session_id_hash", "request_id_hash", "envelope_hash", "command_identity", "command_identity_hash", "subscription_receipt_hash", "execution_policy", "usage_telemetry", "nonvisual_max_turns", "observed_turns"}
    if not isinstance(runtime, dict) or set(runtime) != required or runtime.get("adapter_version") != 1 or runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != "grok-4.6-build" or runtime.get("requested_reasoning_effort") != "high" or runtime.get("reasoning_attested") is not False or runtime.get("reasoning_attestation") != "not_reported_by_grok_build_cli" or runtime.get("identity_evidence") != "requested_only" or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1 or runtime.get("cli_version") != evidence["grok_cli_version"] or runtime.get("subscription_receipt_hash") != evidence["subscription_receipt_hash"]:
        raise ValueError("reconcile v1 adapter runtime semantics drifted")
    if not isinstance(runtime.get("command_identity"), dict) or sha256(project_canonical(runtime["command_identity"])) != evidence["grok_command_identity_sha256"] or any(not _hex(runtime.get(key), label=f"runtime {key}") for key in ("request_id_hash", "session_id_hash", "envelope_hash", "command_identity_hash")):
        raise ValueError("reconcile v1 adapter runtime identity drifted")
    telemetry = runtime.get("usage_telemetry")
    if not isinstance(telemetry, dict) or set(telemetry) - {"status", "total_cost_usd", "total_cost_usd_ticks", "model_cost_usd"} or telemetry.get("status") not in {"reported", "not_reported"} or (telemetry.get("status") == "not_reported" and set(telemetry) != {"status"}) or (telemetry.get("status") == "reported" and set(telemetry) == {"status"}):
        raise ValueError("reconcile v1 adapter telemetry drifted")
    for key in ("total_cost_usd", "model_cost_usd"):
        if key in telemetry and (not isinstance(telemetry[key], (int, float)) or isinstance(telemetry[key], bool) or not math.isfinite(telemetry[key]) or telemetry[key] < 0):
            raise ValueError("reconcile v1 adapter telemetry is invalid")
    if "total_cost_usd_ticks" in telemetry and (type(telemetry["total_cost_usd_ticks"]) is not int or telemetry["total_cost_usd_ticks"] < 0):
        raise ValueError("reconcile v1 adapter telemetry is invalid")
    return control, output, runtime


def _normalized_descendant(output: Mapping[str, Any], *, parent_instruction: bytes, parent_profile: bytes, parent_candidate_id: str) -> tuple[dict[str, str], dict[str, Any], dict[str, Any]]:
    instruction, instruction_audit = _b64(output["descendant_instruction_base64"], label="descendant instruction")
    profile_raw, profile_audit = _b64(output["descendant_profile_base64"], label="descendant profile")
    try:
        instruction_text = instruction.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("reconcile v1 descendant instruction is not UTF-8") from error
    if not instruction_text.strip() or "\x00" in instruction_text:
        raise ValueError("reconcile v1 descendant instruction is unsafe")
    profile = strict_json(profile_raw, label="descendant profile")
    if not isinstance(profile, dict) or not profile or not isinstance(profile.get("instruction_sha256"), str) or not isinstance(profile.get("immutable_cwr_commitments"), dict):
        raise ValueError("reconcile v1 descendant profile is invalid")
    parent_value = strict_json(parent_profile, label="parent profile")
    if not isinstance(parent_value, dict) or profile["immutable_cwr_commitments"] != parent_value.get("immutable_cwr_commitments"):
        raise ValueError("reconcile v1 immutable CWR commitments drifted")
    if "parent_candidate_id" in profile and profile["parent_candidate_id"] != parent_candidate_id:
        raise ValueError("reconcile v1 descendant parent candidate drifted")
    if instruction == parent_instruction:
        raise ValueError("reconcile v1 descendant instruction is parent-identical")
    repaired = dict(profile)
    repaired["instruction_sha256"] = sha256(instruction)
    profile_derived = project_canonical(repaired)
    if profile_derived == parent_profile:
        raise ValueError("reconcile v1 descendant profile is parent-identical")
    normalized = {"descendant_instruction_base64": base64.b64encode(instruction).decode("ascii"), "descendant_profile_base64": base64.b64encode(profile_derived).decode("ascii")}
    derivation = {"raw_output_sha256": sha256(adapter_canonical(dict(output))), "raw_profile_sha256": sha256(profile_raw), "raw_profile_instruction_sha256": profile["instruction_sha256"], "derived_profile_sha256": sha256(profile_derived), "derived_profile_base64": normalized["descendant_profile_base64"], "repaired_field": "instruction_sha256", "repaired_instruction_sha256": sha256(instruction), "factors": "opaque_model_supplied_not_v1_factor_conformance", "base64_audit": {"instruction": instruction_audit, "profile": profile_audit}}
    lineage = {"parent_candidate_id": parent_candidate_id, "parent_instruction_sha256": sha256(parent_instruction), "parent_profile_sha256": sha256(parent_profile), "descendant_instruction_sha256": sha256(instruction), "derived_descendant_profile_sha256": sha256(profile_derived)}
    return normalized, derivation, lineage


def _reconcile_sample(root: Path, sample: str) -> tuple[dict[str, Any], tuple[str, str, str, str, str]]:
    raw, inventory_sha256 = _source_snapshot(root)
    if sha256(raw["adapter-stdout.bin"]) != SOURCE_CONTROL_SHA256[sample]:
        raise ValueError("reconcile v1 source adapter control commitment drifted")
    preparation, evidence, parent_instruction, parent_profile, prompt = _prepared_artifacts(raw, sample)
    control, output, runtime = _completed_control(raw["adapter-stdout.bin"], prompt=prompt, evidence=evidence)
    normalized, derivation, lineage = _normalized_descendant(output, parent_instruction=parent_instruction, parent_profile=parent_profile, parent_candidate_id=preparation["inputs"]["parent_candidate_id"])
    row = {"sample_id": sample, "source_root": str(root), "source_inventory_sha256": inventory_sha256, "source_artifacts": {name: sha256(raw[name]) for name in sorted(raw)}, "source_terminal_kind": "reconcile_required_after_process_launch", "source_adapter_control_sha256": sha256(raw["adapter-stdout.bin"]), "source_control": control, "raw_output": dict(output), "raw_output_sha256": sha256(adapter_canonical(dict(output))), "runtime": runtime, "normalized_output": normalized, "derivation": derivation, "lineage": lineage, "source_native_contact_proven": True, "source_native_endpoint_contact_cardinality": "proven_exactly_one_from_completed_adapter_control", "reconciliation_provider_calls_made": 0, "reconciliation_process_launches": 0}
    return row, (sha256(prompt), sha256(raw["response-schema.json"]), sha256(raw["dspy-input-preparation.json"]), runtime["request_id_hash"], runtime["session_id_hash"])


def reconcile_all(*, source_root: Path, target_root: Path) -> dict[str, Any]:
    """Write one fresh local-only manifest; existing targets and all source mutations fail closed."""
    _contract()
    source, target = Path(source_root), Path(target_root)
    if target.exists():
        raise ValueError("reconcile v1 refuses an existing target root")
    if not source.is_dir() or not _plain(source, directory=True):
        raise ValueError("reconcile v1 source root is unsafe")
    source_entries = {entry.name: entry for entry in source.iterdir()}
    expected_samples = {_sample(number) for number in range(1, 11)}
    if set(source_entries) != expected_samples or any(not _plain(entry, directory=True) for entry in source_entries.values()):
        raise ValueError("reconcile v1 source does not contain exactly ten plain sample roots")
    rows: list[dict[str, Any]] = []
    prompt_hashes: set[str] = set(); schema_hashes: set[str] = set(); preparation_hashes: set[str] = set(); requests: set[str] = set(); sessions: set[str] = set(); descendants: set[str] = set(); snapshots: dict[str, str] = {}
    for number in range(1, 11):
        sample = _sample(number)
        row, identities = _reconcile_sample(source / sample, sample)
        prompt_hash, schema_hash, preparation_hash, request_id, session_id = identities
        descendant = sha256(project_canonical(row["normalized_output"]))
        if request_id in requests or session_id in sessions or descendant in descendants:
            raise ValueError("reconcile v1 duplicate request, session, or descendant identity")
        rows.append(row); prompt_hashes.add(prompt_hash); schema_hashes.add(schema_hash); preparation_hashes.add(preparation_hash); requests.add(request_id); sessions.add(session_id); descendants.add(descendant); snapshots[sample] = row["source_inventory_sha256"]
    if len(prompt_hashes) != 1 or len(schema_hashes) != 1 or len(preparation_hashes) != 1:
        raise ValueError("reconcile v1 source prompt, schema, or preparation differs across samples")
    for sample, before in snapshots.items():
        _raw, after = _source_snapshot(source / sample)
        if after != before:
            raise ValueError("reconcile v1 source changed during reconciliation")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_reconciled_all_ten_descendants", "source": {"study_id": SOURCE_STUDY_ID, "executor_sha256": SOURCE_EXECUTOR_SHA256, "adapter_sha256": GROK_ADAPTER_SHA256, "source_root": str(source), "preparation_file_sha256": next(iter(preparation_hashes)), "shared_prompt_sha256": next(iter(prompt_hashes)), "shared_response_schema_sha256": next(iter(schema_hashes)), "terminal_roots": 10, "completed_native_identities": 10, "source_process_launches": 10}, "samples": rows, "authority": {"confirmation": {"status": "unopened", "cells": 0}, "evaluation": False, "local_only": True, "optimizer_runtime": False}, "reconciliation_provider_calls_made": 0, "reconciliation_process_launches": 0}
    manifest["manifest_sha256"] = sha256(project_canonical(manifest))
    _safe_output_ancestry(target.parent)
    target.mkdir(parents=True, exist_ok=False)
    _write_new(target / "reconciliation-manifest.json", project_canonical(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    args = parser.parse_args(argv)
    reconcile_all(source_root=args.source_root, target_root=args.target_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
