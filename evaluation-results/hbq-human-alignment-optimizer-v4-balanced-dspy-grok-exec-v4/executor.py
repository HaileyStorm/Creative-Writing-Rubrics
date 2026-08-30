#!/usr/bin/env python3
"""Fresh-identity v4 successor for feedback-bound Grok generation."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v4"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "1446a1875eb13085f11e9ee428fc384bccf904cbcd1d96cf35a8fb2a5ff3a6d1"
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3" / "executor.py"
V3_SHA256 = "44279db49369029b97a4e2f1216caf99e876b0548910f157bdb3f60f7ea42d4a"
V3_CONTRACT_SHA256 = "b3f5d39e4d127d7ebd29ab9bbbd9c757f347349448b8c2b4d8c97510202888e2"
V2_SHA256 = "475f5d2fb02cdddcf5b14810d25ef63bd166c85f129dc64106b443f33895fbc4"
V2_CONTRACT_SHA256 = "48057e730c9c3d16cbcbb79c81b95da046e0adc0e25064961cf79628a008ffd6"
FORBIDDEN_WAVE_ID = "r4shrink-20260830a"
PUBLIC_STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1-public-result-v1"
PUBLIC_SUMMARY = "The Grok-selected descendant improved four-group Grok MAE from 1.0694444444444444 to 0.875, but reversed on two-group Sol validation from 1.3680555555555554 to 1.4277777777777778; endpoints are not pooled, general gain is not observed, Sol native contact cardinality is unproven, and confirmation remains unopened."
PUBLIC_AUTHORITY = {
    "feedback-producer-contract.json": "8022c4387718cd6491b7a6a83d6a64da7a42c85d7d640f18d42ee5d9eb70e4df",
    "feedback-producer-source.bin": "f64809efdb248ea87408e6cdb49e8d9727dc13614cbfa823cc3d4d90fbde4919",
    "feedback-selection-schema.json": "4e169f7d46fdcf62d73b73649f63c39d94cb191a09eb9ea6999a8f1a162fd48a",
    "feedback-result-schema.json": "b0f220be3bff0888fda12a87fc918d8d982eca1f4d0292638fae67c60629e2b1",
    "feedback-selection.json": "5b49688f85a530a7ab22cee382514bfd659eec4ef2d8bb68a9b223554aefb816",
    "feedback-result.json": "2ecaf697c8ff729e3545e7004113b0ac186428623d4116fa4e505df950bd1a25",
}
RUNTIME_KEYS = frozenset({
    "adapter_version", "requested_model", "reported_model", "requested_reasoning_effort",
    "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version",
    "session_id_hash", "request_id_hash", "envelope_hash", "command_identity",
    "command_identity_hash", "subscription_receipt_hash", "execution_policy",
    "usage_telemetry", "nonvisual_max_turns", "observed_turns",
})


def canonical(value: Any) -> bytes:
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


def _stable_bytes(path: Path) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if not _plain(current):
            raise ValueError(f"feedback Grok v4 unsafe pinned path: {current}")
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("feedback Grok v4 pinned file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("feedback Grok v4 pinned file changed during read")
    return raw


def _strict_json(raw: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"feedback Grok v4 {label} contains a duplicate key")
            value[key] = item
        return value

    def nonfinite(token: str) -> None:
        raise ValueError(f"feedback Grok v4 {label} contains non-finite number {token}")

    def reject_nonfinite(value: Any, path: str = "$") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"feedback Grok v4 {label} contains a non-finite value at {path}")
        if isinstance(value, dict):
            for key, item in value.items():
                reject_nonfinite(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                reject_nonfinite(item, f"{path}[{index}]")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"feedback Grok v4 {label} is invalid JSON") from error
    reject_nonfinite(value)
    return value


def _load_pinned(path: Path, expected: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if sha256(raw) != expected:
        raise ValueError(f"feedback Grok v4 pinned dependency drifted: {path.name}")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if _stable_bytes(path) != raw:
        raise ValueError(f"feedback Grok v4 loaded dependency drifted: {path.name}")
    return module


_v3_module = _load_pinned(V3_PATH, V3_SHA256, "_feedback_grok_v4_v3")
_v3_contract_base = _v3_module._contract
_v3_feedback_base = _v3_module._feedback
_v3_frozen_feedback_base = _v3_module._frozen_feedback
_v3_artifacts_base = _v3_module._artifacts
_v3_prepare_one_base = _v3_module.prepare_one


def _contract() -> dict[str, Any]:
    raw = _v3_module.stable_bytes(CONTRACT_PATH)
    if sha256(raw) != CONTRACT_SHA256:
        raise ValueError("feedback Grok v4 contract drifted")
    value = _strict_json(raw, "contract")
    if not isinstance(value, dict) or canonical(value) != raw or value.get("format_version") != 4 or value.get("study_id") != STUDY_ID:
        raise ValueError("feedback Grok v4 contract semantics drifted")
    predecessors = value.get("predecessors")
    if predecessors != {
        "transport": {"contract_sha256": V2_CONTRACT_SHA256, "executor_sha256": V2_SHA256, "study_id": "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2"},
        "wave": {"contract_sha256": V3_CONTRACT_SHA256, "executor_sha256": V3_SHA256, "study_id": "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3"},
    }:
        raise ValueError("feedback Grok v4 predecessor binding drifted")
    v2_path = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2"
    if sha256(_stable_bytes(V3_PATH)) != V3_SHA256 or sha256(_stable_bytes(V3_PATH.with_name("study-contract.json"))) != V3_CONTRACT_SHA256 or sha256(_stable_bytes(v2_path / "executor.py")) != V2_SHA256 or sha256(_stable_bytes(v2_path / "study-contract.json")) != V2_CONTRACT_SHA256:
        raise ValueError("feedback Grok v4 pinned predecessor bytes drifted")
    if value.get("authority") != {"confirmation": {"cells": 0, "status": "unopened"}, "evaluation": False, "runtime_selection": False, "sample_selection": False}:
        raise ValueError("feedback Grok v4 authority drifted")
    return value


def _enforce_feedback(feedback: Mapping[str, Any], authority: Mapping[str, bytes]) -> None:
    if feedback.get("study_id") != PUBLIC_STUDY_ID or feedback.get("public_result_summary") != PUBLIC_SUMMARY:
        raise ValueError("feedback Grok v4 public feedback identity drifted")
    wave_id = feedback.get("wave_id")
    if not isinstance(wave_id, str) or wave_id == FORBIDDEN_WAVE_ID or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", wave_id):
        raise ValueError("feedback Grok v4 requires a fresh replacement wave identity")
    if {name: sha256(raw) for name, raw in authority.items()} != PUBLIC_AUTHORITY:
        raise ValueError("feedback Grok v4 exact public feedback authority drifted")


def _feedback(path: Path, expected_sha256: str) -> tuple[bytes, dict[str, Any], dict[str, bytes]]:
    raw, feedback, authority = _v3_feedback_base(path, expected_sha256)
    _enforce_feedback(feedback, authority)
    return raw, feedback, authority


def _frozen_feedback(root: Path, expected_sha256: str) -> tuple[bytes, dict[str, Any], dict[str, bytes]]:
    raw, feedback, authority = _v3_frozen_feedback_base(root, expected_sha256)
    _enforce_feedback(feedback, authority)
    return raw, feedback, authority


def _artifacts(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    prepared, files = _v3_artifacts_base(*args, **kwargs)
    prepared = {**prepared, "kind": "feedback_bound_grok_v4_preparation", "package_version": 4, "canonicalization": {"adapter_commitment": "sorted_compact_utf8_no_lf", "provider_stdout": "strict_json_exact_raw_bytes", "project_profile": "sorted_compact_utf8_one_lf"}}
    files = {**files, "prepared.json": canonical(prepared)}
    return prepared, files


def _derived_descendant(value: Any, preparation: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != {"descendant_instruction_base64", "descendant_profile_base64"} or not all(isinstance(value[name], str) for name in value):
        raise ValueError("feedback Grok v4 descendant shape drifted")
    try:
        instruction = base64.b64decode(value["descendant_instruction_base64"].encode("ascii"), validate=True)
        profile = base64.b64decode(value["descendant_profile_base64"].encode("ascii"), validate=True)
        instruction_text = instruction.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("feedback Grok v4 descendant bytes are invalid") from error
    if not instruction_text.strip() or "\x00" in instruction_text:
        raise ValueError("feedback Grok v4 descendant instruction is invalid")
    profile_value = _strict_json(profile, "raw descendant profile")
    if not isinstance(profile_value, dict) or not profile_value:
        raise ValueError("feedback Grok v4 descendant profile is invalid")
    parent_instruction = _v3_module._v2()._decode(preparation["inputs"]["parent_instruction_base64"], label="parent instruction")
    parent_profile = _v3_module._v2()._decode(preparation["inputs"]["parent_profile_base64"], label="parent profile")
    if instruction == parent_instruction or profile == parent_profile:
        raise ValueError("feedback Grok v4 descendant is parent-identical")
    old_instruction_sha = profile_value.get("instruction_sha256")
    instruction_sha = sha256(instruction)
    derived_value = {**profile_value, "instruction_sha256": instruction_sha}
    derived_profile = canonical(derived_value)
    output = {
        "raw_descendant_instruction_base64": value["descendant_instruction_base64"],
        "raw_descendant_profile_base64": value["descendant_profile_base64"],
        "project_canonical_profile_base64": base64.b64encode(derived_profile).decode("ascii"),
        "raw_descendant_instruction_sha256": instruction_sha,
        "raw_descendant_profile_sha256": sha256(profile),
        "project_canonical_profile_sha256": sha256(derived_profile),
        "profile_derivation": {
            "kind": "versioned_project_canonical_profile_v1",
            "provider_output_unchanged": False,
            "source_profile_sha256": sha256(profile),
            "instruction_sha256_before": old_instruction_sha,
            "instruction_sha256_after": instruction_sha,
            "transformations": ["strict_json_parse", "instruction_sha256_repaired_to_exact_instruction", "sorted_compact_utf8_serialization", "one_trailing_lf"],
        },
    }
    lineage = {
        "parent_candidate_id": str(preparation["inputs"]["parent_candidate_id"]),
        "parent_instruction_sha256": sha256(parent_instruction),
        "parent_profile_sha256": sha256(parent_profile),
        "raw_descendant_instruction_sha256": instruction_sha,
        "raw_descendant_profile_sha256": sha256(profile),
        "project_canonical_profile_sha256": sha256(derived_profile),
    }
    return output, lineage


def _validate_completed_response(v2: ModuleType, control_raw: bytes, outcome_result: Any, preparation: Mapping[str, Any], prompt: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any], dict[str, Any], dict[str, str], Mapping[str, Any]]:
    control = _strict_json(control_raw, "adapter stdout")
    adapter_result = control.get("result") if isinstance(control, Mapping) else None
    if not isinstance(control, dict) or control.get("control") != {"version": 1, "state": "completed"} or adapter_result != outcome_result or not isinstance(adapter_result, Mapping) or set(adapter_result) != {"schema_version", "request_hash", "output", "output_hash", "runtime"} or adapter_result.get("schema_version") != 1:
        raise ValueError("feedback Grok v4 adapter control replay drifted")
    raw_output = adapter_result.get("output")
    if adapter_result.get("request_hash") != sha256(adapter_canonical({"prompt": prompt.decode("utf-8")})) or adapter_result.get("output_hash") != sha256(adapter_canonical(raw_output)):
        raise ValueError("feedback Grok v4 adapter canonical commitment drifted")
    output, lineage = _derived_descendant(raw_output, preparation)
    runtime = adapter_result.get("runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != RUNTIME_KEYS:
        raise ValueError("feedback Grok v4 adapter runtime keyset drifted")
    command_binding = {"adapter_version": 1, "grok_command": route.get("grok_command"), "model": route.get("model"), "reported_model": route.get("reported_model"), "reasoning_effort": route.get("reasoning_effort")}
    expected_command_hash = sha256(adapter_canonical(command_binding))
    if runtime.get("adapter_version") != 1 or runtime.get("requested_model") != route.get("model") or runtime.get("reported_model") != route.get("reported_model") or runtime.get("requested_reasoning_effort") != route.get("reasoning_effort") or runtime.get("reasoning_attested") is not False or runtime.get("reasoning_attestation") != "not_reported_by_grok_build_cli" or runtime.get("identity_evidence") != "requested_only" or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1 or runtime.get("cli_version") != evidence.get("grok_cli_version") or runtime.get("subscription_receipt_hash") != evidence.get("subscription_receipt_hash") or runtime.get("command_identity") != route.get("grok_command_identity") or sha256(canonical(runtime.get("command_identity"))) != evidence.get("grok_command_identity_sha256") or runtime.get("command_identity_hash") != expected_command_hash:
        raise ValueError("feedback Grok v4 native runtime binding drifted")
    request_id, session_id, envelope_hash = runtime.get("request_id_hash"), runtime.get("session_id_hash"), runtime.get("envelope_hash")
    if not all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in (request_id, session_id, envelope_hash)) or request_id == session_id:
        raise ValueError("feedback Grok v4 runtime identity is invalid")
    telemetry = runtime.get("usage_telemetry")
    if not isinstance(telemetry, Mapping) or telemetry.get("status") not in {"reported", "not_reported"}:
        raise ValueError("feedback Grok v4 usage telemetry schema drifted")
    if telemetry.get("status") == "not_reported":
        if set(telemetry) != {"status"}:
            raise ValueError("feedback Grok v4 usage telemetry schema drifted")
    else:
        if set(telemetry) != {"status", "total_cost_usd", "total_cost_usd_ticks", "model_cost_usd"}:
            raise ValueError("feedback Grok v4 usage telemetry schema drifted")
        for key in ("total_cost_usd", "model_cost_usd"):
            value = telemetry[key]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
                raise ValueError("feedback Grok v4 usage telemetry is non-finite or invalid")
        if type(telemetry["total_cost_usd_ticks"]) is not int or telemetry["total_cost_usd_ticks"] < 0:
            raise ValueError("feedback Grok v4 usage telemetry ticks are invalid")
    validated_runtime = {key: runtime[key] for key in sorted(RUNTIME_KEYS - {"envelope_hash"})}
    validated_runtime["evidence_scope"] = {
        "command_identity_hash": "independently_recomputed_adapter_sorted_compact_utf8_no_lf",
        "envelope_hash": "excluded_native_grok_cli_raw_stdout_not_persisted",
        "reasoning_attestation": "exact_adapter_attestation_not_native_reasoning_proof",
        "request_session_identity": "adapter_attested_hashes_format_checked_and_distinct",
        "usage_telemetry": "adapter_reported_exact_finite_schema",
    }
    return dict(control), adapter_result, output, lineage, validated_runtime


def _terminal(root: Path, sample: str, state: str, control_raw: bytes, detail: str | None, launches: int) -> dict[str, Any]:
    capture = root / "adapter-stdout.bin"
    if control_raw:
        if capture.exists():
            if _v3_module.stable_bytes(capture) != control_raw:
                raise ValueError("feedback Grok v4 terminal capture differs from adapter stdout")
        else:
            _v3_module._write_new(capture, control_raw)
    result = {"format_version": 4, "study_id": STUDY_ID, "kind": state, "sample_id": sample, "adapter_stdout_sha256": sha256(control_raw) if control_raw else None, "detail": detail, "provider_calls_made": 0 if state == "definitely_not_contacted" else None, "process_launches": launches, "native_contact_proven": False, "native_endpoint_contact_cardinality": "zero" if state == "definitely_not_contacted" else "unknown"}
    _v3_module._write_new(root / "result.json", canonical(result))
    return result


def _postwrite_reconcile(root: Path, sample: str, detail: str) -> dict[str, Any]:
    prior = _v3_module.stable_bytes(root / "result.json")
    marker = {"format_version": 4, "study_id": STUDY_ID, "kind": "postwrite_reconcile_required", "sample_id": sample, "detail": detail, "supersedes_success_result_sha256": sha256(prior), "provider_calls_made": None, "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown", "retry_policy": "fresh_output_root_required_no_in_place_retry"}
    _v3_module._write_new(root / _v3_module.POSTWRITE_RECONCILE, canonical(marker))
    return marker


def _receipt_and_result(sample: str, prepared_raw: bytes, intent_raw: bytes, control_raw: bytes, feedback_raw: bytes, prepared: Mapping[str, Any], adapter_result: Mapping[str, Any], output: Mapping[str, Any], lineage: Mapping[str, Any], runtime: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = {
        "format_version": 4,
        "study_id": STUDY_ID,
        "kind": "feedback_bound_grok_v4_native_receipt",
        "sample_id": sample,
        "prepared_sha256": sha256(prepared_raw),
        "launch_intent_sha256": sha256(intent_raw),
        "adapter_stdout_sha256": sha256(control_raw),
        "adapter_request_commitment_sha256": adapter_result["request_hash"],
        "adapter_output_commitment_sha256": adapter_result["output_hash"],
        "adapter_commitment_domain": "sorted_compact_utf8_no_lf",
        "feedback_sha256": sha256(feedback_raw),
        "prompt_sha256": prepared["prompt_sha256"],
        "response_schema_sha256": prepared["response_schema_sha256"],
        "route_evidence": prepared["route_evidence"],
        "provider_calls_made": 1,
        "process_launches": 1,
        "native_contact_proven": True,
        "native_endpoint_contact_cardinality": "proven_exactly_one",
        "runtime_evidence": dict(runtime),
        "lineage": dict(lineage),
        "descendant_output_sha256": sha256(canonical(output)),
    }
    result = {"format_version": 4, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v4_result", "sample_id": sample, "descendant": dict(output), "descendant_sha256": sha256(canonical(output)), "provider_calls_made": 1, "process_launches": 1, "authority": {"evaluation": "none", "selection": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}
    return receipt, result


def _require_single_replacement_sample(sample_id: str | int) -> None:
    if str(sample_id) != "1":
        raise ValueError("feedback Grok v4 permits only fresh replacement sample 1")


def prepare_one(*, output_root: Path, sample_id: str | int, dspy_input_preparation_path: Path, feedback_path: Path, feedback_sha256: str, queue_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    _require_single_replacement_sample(sample_id)
    return _v3_prepare_one_base(output_root=output_root, sample_id=sample_id, dspy_input_preparation_path=dspy_input_preparation_path, feedback_path=feedback_path, feedback_sha256=feedback_sha256, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)


def execute_one(*, output_root: Path, sample_id: str | int, dspy_input_preparation_path: Path, feedback_path: Path, feedback_sha256: str, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool) -> dict[str, Any]:
    _require_single_replacement_sample(sample_id)
    if allow_remote is not True:
        raise ValueError("feedback Grok v4 requires explicit allow_remote=True")
    _contract()
    v2 = _v3_module._v2()
    preparation_raw, preparation = v2._preparation(Path(dspy_input_preparation_path))
    feedback_raw, feedback, authority = _feedback(Path(feedback_path), feedback_sha256)
    sample = _v3_module._sample(feedback["wave_id"], sample_id)
    root = Path(output_root) / sample
    terminal_names = ("launch-intent.json", "adapter-stdout.bin", "execution-receipt.json", "result.json", _v3_module.ISOLATION_RECONCILE, _v3_module.POSTWRITE_RECONCILE)
    if any((root / name).exists() for name in terminal_names):
        raise ValueError("feedback Grok v4 forbids resend from a stranded root")
    persisted = _v3_module._canonical_object(_v3_module.stable_bytes(root / "prepared.json"), "prepared record")
    route, evidence = persisted.get("route"), persisted.get("route_evidence")
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
        raise ValueError("feedback Grok v4 prepared route binding is invalid")
    prepared, files = _artifacts(v2, sample, preparation_raw, preparation, feedback_raw, feedback, authority, route, evidence, authorization_acknowledgement_sha256)
    _v3_module._validate_root(root, files)
    _native, broker, fresh_route, fresh_evidence = v2._route(Path(queue_root))
    if dict(fresh_route) != dict(route) or dict(fresh_evidence) != dict(evidence):
        return _terminal(root, sample, "definitely_not_contacted", b"", "route_drift_before_launch", 0)
    intent = {"format_version": 4, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(canonical(prepared)), "prompt_sha256": prepared["prompt_sha256"], "route_evidence": evidence, "native_contact_proven": False}
    intent_raw = canonical(intent)
    _v3_module._write_new(root / "launch-intent.json", intent_raw)
    try:
        outcome, control_raw = v2._adapter_once(broker, fresh_route, {"prompt": _v3_module.stable_bytes(root / "prompt-request.bin").decode("utf-8")}, root / "adapter-stdout.bin")
    except BaseException as error:
        return _terminal(root, sample, "reconcile_required_after_process_launch", b"", type(error).__name__, 1)
    state, detail = getattr(outcome, "state", None), getattr(outcome, "detail", None)
    if state == "definitely_not_contacted":
        return _terminal(root, sample, state, control_raw, detail, 1)
    if state != "completed":
        return _terminal(root, sample, "reconcile_required_after_process_launch", control_raw, detail, 1)
    try:
        control, adapter_result, output, lineage, runtime = _validate_completed_response(v2, control_raw, getattr(outcome, "result", None), preparation, _v3_module.stable_bytes(root / "prompt-request.bin"), route, evidence)
        prepared_raw = canonical(prepared)
        receipt, result = _receipt_and_result(sample, prepared_raw, intent_raw, control_raw, feedback_raw, prepared, adapter_result, output, lineage, runtime)
        capture = root / "adapter-stdout.bin"
        if capture.exists():
            if _v3_module.stable_bytes(capture) != control_raw:
                raise ValueError("feedback Grok v4 adapter capture differs from exact stdout")
        else:
            _v3_module._write_new(capture, control_raw)
        _v3_module._write_new(root / "adapter-control-envelope.json", canonical(control))
        _v3_module._write_new(root / "runtime-identity.json", canonical(dict(runtime)))
        _v3_module._write_new(root / "execution-receipt.json", canonical(receipt))
        _v3_module._write_new(root / "result.json", canonical(result))
        return _admit_completed_root(root, sample)
    except BaseException as error:
        if (root / "result.json").exists():
            return _postwrite_reconcile(root, sample, type(error).__name__)
        return _terminal(root, sample, "reconcile_required_after_process_launch", control_raw, type(error).__name__, 1)


def _admit_completed_root(root: Path, sample: str) -> dict[str, Any]:
    v2 = _v3_module._v2()
    required = _v3_module.PREPARED | {"launch-intent.json", "adapter-stdout.bin", "adapter-control-envelope.json", "runtime-identity.json", "execution-receipt.json", "result.json"}
    if not root.is_dir() or not _v3_module._plain(root, directory=True) or {entry.name for entry in root.iterdir()} != required or any(not _v3_module._plain(entry, directory=False) for entry in root.iterdir()):
        raise ValueError("feedback Grok v4 completed root inventory is incomplete or unsafe")
    raw = {name: _v3_module.stable_bytes(root / name) for name in required}
    prepared = _v3_module._canonical_object(raw["prepared.json"], "prepared record")
    if prepared.get("sample_id") != sample or not isinstance(prepared.get("route"), Mapping) or not isinstance(prepared.get("route_evidence"), Mapping):
        raise ValueError("feedback Grok v4 prepared sample/route binding drifted")
    preparation_raw, preparation = v2._preparation(root / "dspy-input-preparation.json")
    feedback_raw, feedback, authority = _frozen_feedback(root, str(prepared.get("feedback_sha256")))
    if preparation_raw != raw["dspy-input-preparation.json"] or feedback_raw != raw["r4-feedback.json"]:
        raise ValueError("feedback Grok v4 persisted input bytes drifted")
    acknowledgement = _v3_module._canonical_object(raw["authorization-acknowledgement.json"], "acknowledgement").get("acknowledgement_sha256")
    expected_prepared, files = _artifacts(v2, sample, preparation_raw, preparation, feedback_raw, feedback, authority, prepared["route"], prepared["route_evidence"], acknowledgement)
    if prepared != expected_prepared or any(raw[name] != content for name, content in files.items()):
        raise ValueError("feedback Grok v4 prepared replay drifted")
    intent = _v3_module._canonical_object(raw["launch-intent.json"], "launch intent")
    expected_intent = {"format_version": 4, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "prompt_sha256": prepared["prompt_sha256"], "route_evidence": prepared["route_evidence"], "native_contact_proven": False}
    if intent != expected_intent:
        raise ValueError("feedback Grok v4 launch intent replay drifted")
    stored_control = _v3_module._canonical_object(raw["adapter-control-envelope.json"], "stored adapter control")
    control, adapter_result, output, lineage, runtime = _validate_completed_response(v2, raw["adapter-stdout.bin"], stored_control.get("result"), preparation, raw["prompt-request.bin"], prepared["route"], prepared["route_evidence"])
    if stored_control != control or _v3_module._canonical_object(raw["runtime-identity.json"], "runtime identity") != runtime:
        raise ValueError("feedback Grok v4 stored control/runtime drifted")
    expected_receipt, expected_result = _receipt_and_result(sample, raw["prepared.json"], raw["launch-intent.json"], raw["adapter-stdout.bin"], feedback_raw, prepared, adapter_result, output, lineage, runtime)
    if _v3_module._canonical_object(raw["execution-receipt.json"], "receipt") != expected_receipt or _v3_module._canonical_object(raw["result.json"], "result") != expected_result:
        raise ValueError("feedback Grok v4 receipt/result replay drifted")
    return {"sample_id": sample, "state": "native_descendant_received", "provider_calls_made": 1, "process_launches": 1, "descendant_sha256": expected_result["descendant_sha256"]}


_v3_module.STUDY_ID = STUDY_ID
_v3_module.HERE = HERE
_v3_module.CONTRACT_PATH = CONTRACT_PATH
_v3_module.CONTRACT_SHA256 = CONTRACT_SHA256
_v3_module.__file__ = str(Path(__file__).resolve())
_v3_module._contract = _contract
_v3_module._feedback = _feedback
_v3_module._frozen_feedback = _frozen_feedback
_v3_module._artifacts = _artifacts
_v3_module._validate_completed_response = _validate_completed_response
_v3_module._admit_completed_root = _admit_completed_root
_v3_module.execute_one = execute_one

_ChildTreeOwner = _v3_module._ChildTreeOwner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute-one", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sample-id")
    parser.add_argument("--dspy-input-preparation", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--feedback-sha256", required=True)
    parser.add_argument("--queue-root", type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    parser.add_argument("--isolation-gate", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.isolation_gate is not None:
        _v3_module._await_isolation_gate(args.isolation_gate)
    common = {"output_root": args.output_root, "dspy_input_preparation_path": args.dspy_input_preparation, "feedback_path": args.feedback, "feedback_sha256": args.feedback_sha256, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if not args.sample_id:
        parser.error("--sample-id is required")
    common["sample_id"] = args.sample_id
    if args.prepare_only:
        if args.allow_remote:
            parser.error("--prepare-only forbids --allow-remote")
        result = prepare_one(**common)
    else:
        if not args.allow_remote:
            parser.error("--execute-one requires --allow-remote")
        result = execute_one(**common, allow_remote=True)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
