#!/usr/bin/env python3
"""Feedback-bound, development-only Grok descendant wave."""
from __future__ import annotations

import argparse
import asyncio
import ctypes
import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3"
CONTRACT_PATH = HERE / "study-contract.json"
CONTRACT_SHA256 = "b3f5d39e4d127d7ebd29ab9bbbd9c757f347349448b8c2b4d8c97510202888e2"
V2_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2" / "executor.py"
V2_SHA256 = "475f5d2fb02cdddcf5b14810d25ef63bd166c85f129dc64106b443f33895fbc4"
V2_CONTRACT_SHA256 = "48057e730c9c3d16cbcbb79c81b95da046e0adc0e25064961cf79628a008ffd6"
PREPARED = frozenset({"dspy-input-preparation.json", "r4-feedback.json", "feedback-producer-contract.json", "feedback-producer-source.bin", "feedback-selection-schema.json", "feedback-result-schema.json", "feedback-selection.json", "feedback-result.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
ISOLATION_RECONCILE = "isolated-child-reconcile.json"
POSTWRITE_RECONCILE = "postwrite-reconcile.json"
ISOLATED_CHILD_TIMEOUT_SECONDS = 960


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        return False
    return directory is None or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def stable_bytes(path: Path) -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if not _plain(current): raise ValueError(f"feedback Grok v3 unsafe path: {current}")
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size): raise ValueError("feedback Grok v3 file identity drifted")
        raw = handle.read(); after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size): raise ValueError("feedback Grok v3 file changed during read")
    return raw


def _load(path: Path, expected: str, name: str) -> ModuleType:
    raw = stable_bytes(path)
    if sha256(raw) != expected: raise ValueError(f"feedback Grok v3 pinned dependency drifted: {path.name}")
    module = ModuleType(name); module.__file__ = str(path); exec(compile(raw, str(path), "exec"), module.__dict__)
    if stable_bytes(path) != raw: raise ValueError(f"feedback Grok v3 loaded dependency drifted: {path.name}")
    return module


def _v2() -> ModuleType:
    return _load(V2_PATH, V2_SHA256, "_feedback_grok_v3_v2")


def _contract() -> dict[str, Any]:
    raw = stable_bytes(CONTRACT_PATH)
    if sha256(raw) != CONTRACT_SHA256: raise ValueError("feedback Grok v3 contract drifted")
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("feedback Grok v3 contract is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw or value.get("study_id") != STUDY_ID or value.get("format_version") != 3 or value.get("predecessor") != {"contract_sha256": V2_CONTRACT_SHA256, "executor_sha256": V2_SHA256, "study_id": "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2"} or value.get("authority") != {"confirmation": {"cells": 0, "status": "unopened"}, "evaluation": False, "runtime_selection": False, "sample_selection": False}:
        raise ValueError("feedback Grok v3 contract semantics drifted")
    return value


def _feedback(path: Path, expected_sha256: str) -> tuple[bytes, dict[str, Any], dict[str, bytes]]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256): raise ValueError("feedback Grok v3 feedback hash must be lowercase SHA-256")
    raw = stable_bytes(path)
    if sha256(raw) != expected_sha256: raise ValueError("feedback Grok v3 feedback file hash drifted")
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("feedback Grok v3 feedback is invalid") from error
    required = {"format_version", "kind", "study_id", "wave_id", "seed", "public_result_summary", "producer", "artifacts"}
    if not isinstance(value, dict) or canonical(value) != raw or set(value) != required or value.get("format_version") != 1 or value.get("kind") != "hanna_r4_two_phase_feedback" or not isinstance(value.get("study_id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", str(value.get("wave_id"))) or type(value.get("seed")) is not int or value["seed"] < 0 or not isinstance(value.get("public_result_summary"), str) or not value["public_result_summary"].strip():
        raise ValueError("feedback Grok v3 feedback semantics drifted")
    producer, artifacts = value.get("producer"), value.get("artifacts")
    producer_keys = {"study_contract_path", "study_contract_sha256", "producer_source_path", "producer_source_sha256", "selection_schema_path", "selection_schema_sha256", "result_schema_path", "result_schema_sha256"}
    artifact_keys = {"selection_path", "selection_sha256", "result_path", "result_sha256"}
    if not isinstance(producer, Mapping) or set(producer) != producer_keys or not isinstance(artifacts, Mapping) or set(artifacts) != artifact_keys:
        raise ValueError("feedback Grok v3 feedback provenance shape drifted")
    for name in producer_keys | artifact_keys:
        if name.endswith("_sha256") and (not isinstance((producer | artifacts).get(name), str) or not re.fullmatch(r"[0-9a-f]{64}", (producer | artifacts)[name])): raise ValueError("feedback Grok v3 feedback provenance hash is invalid")
    authority: dict[str, bytes] = {}
    def checked_json(reference: str, digest: str, label: str, target: str) -> dict[str, Any]:
        if not isinstance(reference, str) or not Path(reference).is_absolute(): raise ValueError(f"feedback Grok v3 {label} path must be absolute")
        try: candidate_raw = stable_bytes(Path(reference)); candidate = json.loads(candidate_raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"feedback Grok v3 {label} artifact is invalid") from error
        if sha256(candidate_raw) != digest or not isinstance(candidate, dict) or canonical(candidate) != candidate_raw: raise ValueError(f"feedback Grok v3 {label} artifact hash or canonical bytes drifted")
        authority[target] = candidate_raw
        return candidate
    contract = checked_json(producer["study_contract_path"], producer["study_contract_sha256"], "producer contract", "feedback-producer-contract.json")
    if contract.get("study_id") != value["study_id"]: raise ValueError("feedback Grok v3 producer study identity drifted")
    if not isinstance(producer["producer_source_path"], str) or not Path(producer["producer_source_path"]).is_absolute(): raise ValueError("feedback Grok v3 producer source hash drifted")
    source_raw = stable_bytes(Path(producer["producer_source_path"]))
    if sha256(source_raw) != producer["producer_source_sha256"]: raise ValueError("feedback Grok v3 producer source hash drifted")
    authority["feedback-producer-source.bin"] = source_raw
    checked_json(producer["selection_schema_path"], producer["selection_schema_sha256"], "selection schema", "feedback-selection-schema.json"); checked_json(producer["result_schema_path"], producer["result_schema_sha256"], "result schema", "feedback-result-schema.json")
    selection = checked_json(artifacts["selection_path"], artifacts["selection_sha256"], "selection", "feedback-selection.json")
    result = checked_json(artifacts["result_path"], artifacts["result_sha256"], "result", "feedback-result.json")
    if selection.get("study_id") != value["study_id"] or result.get("study_id") != value["study_id"] or result.get("public_result_summary") != value["public_result_summary"]:
        raise ValueError("feedback Grok v3 r4 result/selection binding drifted")
    value = {**value, "r4_result_sha256": artifacts["result_sha256"], "r4_selection_sha256": artifacts["selection_sha256"]}
    return raw, value, authority


def _frozen_feedback(root: Path, expected_sha256: str) -> tuple[bytes, dict[str, Any], dict[str, bytes]]:
    raw = stable_bytes(root / "r4-feedback.json")
    if sha256(raw) != expected_sha256: raise ValueError("feedback Grok v3 frozen feedback hash drifted")
    value = _canonical_object(raw, "frozen feedback")
    required = {"format_version", "kind", "study_id", "wave_id", "seed", "public_result_summary", "producer", "artifacts"}
    producer, artifacts = value.get("producer"), value.get("artifacts")
    if set(value) != required or value.get("format_version") != 1 or value.get("kind") != "hanna_r4_two_phase_feedback" or not isinstance(value.get("study_id"), str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", str(value.get("wave_id"))) or type(value.get("seed")) is not int or value["seed"] < 0 or not isinstance(value.get("public_result_summary"), str) or not value["public_result_summary"].strip() or not isinstance(producer, Mapping) or not isinstance(artifacts, Mapping):
        raise ValueError("feedback Grok v3 frozen feedback semantics drifted")
    names = {"feedback-producer-contract.json": producer.get("study_contract_sha256"), "feedback-producer-source.bin": producer.get("producer_source_sha256"), "feedback-selection-schema.json": producer.get("selection_schema_sha256"), "feedback-result-schema.json": producer.get("result_schema_sha256"), "feedback-selection.json": artifacts.get("selection_sha256"), "feedback-result.json": artifacts.get("result_sha256")}
    authority = {name: stable_bytes(root / name) for name in names}
    if any(not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or sha256(authority[name]) != digest for name, digest in names.items()): raise ValueError("feedback Grok v3 frozen authority hash drifted")
    contract = _canonical_object(authority["feedback-producer-contract.json"], "frozen producer contract"); selection = _canonical_object(authority["feedback-selection.json"], "frozen selection"); result = _canonical_object(authority["feedback-result.json"], "frozen result")
    _canonical_object(authority["feedback-selection-schema.json"], "frozen selection schema"); _canonical_object(authority["feedback-result-schema.json"], "frozen result schema")
    if contract.get("study_id") != value["study_id"] or selection.get("study_id") != value["study_id"] or result.get("study_id") != value["study_id"] or result.get("public_result_summary") != value["public_result_summary"]:
        raise ValueError("feedback Grok v3 frozen result/selection binding drifted")
    return raw, {**value, "r4_result_sha256": artifacts["result_sha256"], "r4_selection_sha256": artifacts["selection_sha256"]}, authority


def _sample(wave_id: str, sample_id: str | int) -> str:
    try: number = int(sample_id)
    except (TypeError, ValueError) as error: raise ValueError("feedback Grok v3 sample id must be 1 through 10") from error
    if str(sample_id) != str(number) or not 1 <= number <= 10: raise ValueError("feedback Grok v3 sample id must be 1 through 10")
    return f"{wave_id}-sample-{number:02d}"


def _prompt(preparation: Mapping[str, Any], feedback: Mapping[str, Any]) -> bytes:
    request = {"signature": "FeedbackBoundBalancedDescendantSignature", "inputs": dict(preparation["inputs"]), "feedback": dict(feedback), "output_fields": ["descendant_instruction_base64", "descendant_profile_base64"], "constraints": ["Return only the required JSON object.", "Create versioned descendants only.", "No tools, web, plans, memory, or subagents."]}
    return ("Development-only HANNA feedback-informed descendant generation.\n" + canonical(request).decode("utf-8")).encode("utf-8")


def _safe_output_ancestry(path: Path) -> None:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True): raise ValueError(f"feedback Grok v3 output ancestry is unsafe: {current}")


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _await_isolation_gate(path: Path) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if path.exists():
            absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
            for part in absolute.parts[1:]:
                current /= part
                if not _plain(current, directory=current != absolute): raise ValueError("feedback Grok v3 isolation gate is unsafe")
            if stable_bytes(absolute) == b"feedback-grok-v3-isolation-gate\n": return
            raise ValueError("feedback Grok v3 isolation gate bytes drifted")
        time.sleep(0.01)
    raise ValueError("feedback Grok v3 isolation gate timed out")


class _ChildTreeOwner:
    def __init__(self, child: asyncio.subprocess.Process):
        self.child = child; self.handle: Any | None = None
        if os.name != "nt": return
        transport = getattr(child, "_transport", None); proc = transport.get_extra_info("subprocess") if transport is not None else None; process_handle = getattr(proc, "_handle", None)
        if process_handle is None: raise ValueError("feedback Grok v3 child lacks Windows process handle")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True); kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p); kernel32.CreateJobObjectW.restype = ctypes.c_void_p; kernel32.SetInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32); kernel32.SetInformationJobObject.restype = ctypes.c_int; kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p); kernel32.AssignProcessToJobObject.restype = ctypes.c_int; kernel32.CloseHandle.argtypes = (ctypes.c_void_p,); kernel32.CloseHandle.restype = ctypes.c_int
        job = kernel32.CreateJobObjectW(None, None)
        if not job: raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        class Basic(ctypes.Structure): _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", ctypes.c_uint32), ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", ctypes.c_uint32), ("Affinity", ctypes.c_size_t), ("PriorityClass", ctypes.c_uint32), ("SchedulingClass", ctypes.c_uint32)]
        class Io(ctypes.Structure): _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure): _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Io), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        info = Extended(); info.BasicLimitInformation.LimitFlags = 0x00002000
        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel32.AssignProcessToJobObject(job, ctypes.c_void_p(process_handle)):
            error = ctypes.get_last_error(); kernel32.CloseHandle(job); raise OSError(error, "Windows Job ownership")
        self.handle = job

    async def stop(self) -> None:
        if os.name == "nt":
            if self.child.returncode is None: self.child.terminate()
            try: await asyncio.wait_for(self.child.wait(), timeout=5)
            except asyncio.TimeoutError: self.child.kill(); await self.child.wait()
            return
        try: os.killpg(self.child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: await asyncio.wait_for(self.child.wait(), timeout=5)
        except asyncio.TimeoutError: pass
        try: os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        await self.child.wait()

    def close(self) -> None:
        if self.handle is not None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True); kernel32.CloseHandle.argtypes = (ctypes.c_void_p,); kernel32.CloseHandle.restype = ctypes.c_int; kernel32.CloseHandle(self.handle); self.handle = None


async def _stop_unowned_child(child: asyncio.subprocess.Process) -> None:
    if os.name == "nt":
        if child.returncode is None: child.terminate()
        try: await asyncio.wait_for(child.wait(), timeout=5)
        except asyncio.TimeoutError: child.kill(); await child.wait()
        return
    try: os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    try: await asyncio.wait_for(child.wait(), timeout=5)
    except asyncio.TimeoutError: pass
    try: os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError: pass
    await child.wait()


def _artifacts(v2: ModuleType, sample: str, preparation_raw: bytes, preparation: Mapping[str, Any], feedback_raw: bytes, feedback: Mapping[str, Any], authority: Mapping[str, bytes], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement): raise ValueError("feedback Grok v3 acknowledgement must be lowercase SHA-256")
    prompt, schema = _prompt(preparation, feedback), v2._schema(); parent_instruction = v2._decode(preparation["inputs"]["parent_instruction_base64"], label="parent instruction"); parent_profile = v2._decode(preparation["inputs"]["parent_profile_base64"], label="parent profile")
    route_identity = {name: route[name] for name in ("name", "provider", "model", "adapter", "destination")}
    disclosure = {"format_version": 3, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "sample_id": sample, "route_identity": route_identity, "prompt": {"bytes": len(prompt), "sha256": sha256(prompt), "text": prompt.decode("utf-8")}, "response_schema_sha256": sha256(schema), "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    ack = {"format_version": 3, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "sample_id": sample, "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha256(canonical(disclosure)), "destination": route["destination"]}
    proof = {"format_version": 3, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "sample_id": sample, "route_evidence": dict(evidence), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    if set(authority) != PREPARED - {"dspy-input-preparation.json", "r4-feedback.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"} or any(not isinstance(raw, bytes) for raw in authority.values()): raise ValueError("feedback Grok v3 feedback authority inventory is invalid")
    prepared = {"format_version": 3, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v3_preparation", "sample_id": sample, "wave_id": feedback["wave_id"], "seed": feedback["seed"], "feedback_sha256": sha256(feedback_raw), "feedback_authority_sha256": {name: sha256(raw) for name, raw in sorted(authority.items())}, "r4_result_sha256": feedback["r4_result_sha256"], "r4_selection_sha256": feedback["r4_selection_sha256"], "public_result_summary": feedback["public_result_summary"], "preparation_file_sha256": sha256(preparation_raw), "preparation_sha256": preparation["preparation_sha256"], "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "parent_candidate_id": preparation["inputs"]["parent_candidate_id"], "parent_instruction_sha256": sha256(parent_instruction), "parent_profile_sha256": sha256(parent_profile), "route": dict(route), "route_evidence": dict(evidence), "disclosure_sha256": sha256(canonical(disclosure)), "acknowledgement_sha256": sha256(canonical(ack)), "route_proof_sha256": sha256(canonical(proof)), "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "selection_authority": "none"}
    return prepared, {"dspy-input-preparation.json": preparation_raw, "r4-feedback.json": feedback_raw, **dict(authority), "prompt-request.bin": prompt, "response-schema.json": schema, "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(ack), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def _validate_root(root: Path, files: Mapping[str, bytes]) -> None:
    if not root.is_dir() or not _plain(root, directory=True): raise ValueError("feedback Grok v3 prepared root is unsafe")
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != set(files) or any(not _plain(entry, directory=False) for entry in entries.values()): raise ValueError("feedback Grok v3 prepared inventory drifted")
    if any(stable_bytes(root / name) != raw for name, raw in files.items()): raise ValueError("feedback Grok v3 prepared artifact drifted")


def _canonical_object(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"feedback Grok v3 {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw: raise ValueError(f"feedback Grok v3 {label} is not canonical")
    return value


def prepare_one(*, output_root: Path, sample_id: str | int, dspy_input_preparation_path: Path, feedback_path: Path, feedback_sha256: str, queue_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    _contract(); v2 = _v2(); v2._contract(); preparation_raw, preparation = v2._preparation(Path(dspy_input_preparation_path)); feedback_raw, feedback, authority = _feedback(Path(feedback_path), feedback_sha256); sample = _sample(feedback["wave_id"], sample_id)
    _native, _broker, route, evidence = v2._route(Path(queue_root)); prepared, files = _artifacts(v2, sample, preparation_raw, preparation, feedback_raw, feedback, authority, route, evidence, authorization_acknowledgement_sha256); root = Path(output_root) / sample
    if root.exists(): raise ValueError("feedback Grok v3 refuses an existing sample root")
    _safe_output_ancestry(root.parent); root.mkdir(parents=True, exist_ok=False)
    for name, raw in files.items(): _write_new(root / name, raw)
    return {"format_version": 3, "study_id": STUDY_ID, "sample_id": sample, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "prepared_sha256": sha256(canonical(prepared))}


def execute_one(*, output_root: Path, sample_id: str | int, dspy_input_preparation_path: Path, feedback_path: Path, feedback_sha256: str, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("feedback Grok v3 requires explicit allow_remote=True")
    _contract(); v2 = _v2(); preparation_raw, preparation = v2._preparation(Path(dspy_input_preparation_path)); feedback_raw, feedback, authority = _feedback(Path(feedback_path), feedback_sha256); sample = _sample(feedback["wave_id"], sample_id); root = Path(output_root) / sample
    if any((root / name).exists() for name in ("launch-intent.json", "adapter-stdout.bin", "execution-receipt.json", "result.json", ISOLATION_RECONCILE, POSTWRITE_RECONCILE)): raise ValueError("feedback Grok v3 forbids resend from a stranded root")
    persisted_prepared = _canonical_object(stable_bytes(root / "prepared.json"), "prepared record")
    route, evidence = persisted_prepared.get("route"), persisted_prepared.get("route_evidence")
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping): raise ValueError("feedback Grok v3 prepared route binding is invalid")
    prepared, files = _artifacts(v2, sample, preparation_raw, preparation, feedback_raw, feedback, authority, route, evidence, authorization_acknowledgement_sha256); _validate_root(root, files)
    _native, broker, fresh_route, fresh_evidence = v2._route(Path(queue_root))
    if dict(fresh_route) != dict(route) or dict(fresh_evidence) != dict(evidence): return _terminal(root, sample, "definitely_not_contacted", b"", "route_drift_before_launch", 0)
    intent = {"format_version": 3, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(canonical(prepared)), "prompt_sha256": prepared["prompt_sha256"], "route_evidence": evidence, "native_contact_proven": False}; _write_new(root / "launch-intent.json", canonical(intent))
    try: outcome, control_raw = v2._adapter_once(broker, fresh_route, {"prompt": stable_bytes(root / "prompt-request.bin").decode("utf-8")}, root / "adapter-stdout.bin")
    except BaseException as error: return _terminal(root, sample, "reconcile_required_after_process_launch", b"", type(error).__name__, 1)
    state, detail = getattr(outcome, "state", None), getattr(outcome, "detail", None)
    if state == "definitely_not_contacted": return _terminal(root, sample, state, control_raw, detail, 1)
    if state != "completed": return _terminal(root, sample, "reconcile_required_after_process_launch", control_raw, detail, 1)
    try:
        control, _adapter_result, output, lineage, runtime = _validate_completed_response(v2, control_raw, getattr(outcome, "result", None), preparation, stable_bytes(root / "prompt-request.bin"), route, evidence)
        receipt = {"format_version": 3, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v3_native_receipt", "sample_id": sample, "prepared_sha256": sha256(canonical(prepared)), "launch_intent_sha256": sha256(canonical(intent)), "adapter_stdout_sha256": sha256(control_raw), "feedback_sha256": sha256(feedback_raw), "prompt_sha256": prepared["prompt_sha256"], "response_schema_sha256": prepared["response_schema_sha256"], "route_evidence": evidence, "provider_calls_made": 1, "process_launches": 1, "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "runtime": dict(runtime), "lineage": lineage, "descendant_output_sha256": sha256(canonical(output))}
        final = {"format_version": 3, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v3_result", "sample_id": sample, "descendant": output, "descendant_sha256": sha256(canonical(output)), "provider_calls_made": 1, "process_launches": 1}
        capture = root / "adapter-stdout.bin"
        if capture.exists():
            if stable_bytes(capture) != control_raw: raise ValueError("feedback Grok v3 adapter capture differs from control stdout")
        else: _write_new(capture, control_raw)
        _write_new(root / "adapter-control-envelope.json", canonical(control)); _write_new(root / "runtime-identity.json", canonical(dict(runtime))); _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical(final))
        return _admit_completed_root(root, sample)
    except BaseException as error:
        if (root / "result.json").exists(): return _postwrite_reconcile(root, sample, type(error).__name__)
        return _terminal(root, sample, "reconcile_required_after_process_launch", control_raw, type(error).__name__, 1)


def _terminal(root: Path, sample: str, state: str, control_raw: bytes, detail: str | None, launches: int) -> dict[str, Any]:
    capture = root / "adapter-stdout.bin"
    if control_raw:
        if capture.exists():
            if stable_bytes(capture) != control_raw: raise ValueError("feedback Grok v3 terminal capture differs from adapter stdout")
        else: _write_new(capture, control_raw)
    result = {"format_version": 3, "study_id": STUDY_ID, "kind": state, "sample_id": sample, "adapter_stdout_sha256": sha256(control_raw) if control_raw else None, "detail": detail, "provider_calls_made": 0 if state == "definitely_not_contacted" else None, "process_launches": launches, "native_contact_proven": False, "native_endpoint_contact_cardinality": "zero" if state == "definitely_not_contacted" else "unknown"}
    _write_new(root / "result.json", canonical(result)); return result


def _postwrite_reconcile(root: Path, sample: str, detail: str) -> dict[str, Any]:
    prior = stable_bytes(root / "result.json")
    marker = {"format_version": 3, "study_id": STUDY_ID, "kind": "postwrite_reconcile_required", "sample_id": sample, "detail": detail, "supersedes_success_result_sha256": sha256(prior), "provider_calls_made": None, "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown", "retry_policy": "fresh_output_root_required_no_in_place_retry"}
    _write_new(root / POSTWRITE_RECONCILE, canonical(marker)); return marker


def _validate_completed_response(v2: ModuleType, control_raw: bytes, outcome_result: Any, preparation: Mapping[str, Any], prompt: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any], dict[str, str], dict[str, str], Mapping[str, Any]]:
    control = _canonical_object(control_raw, "adapter stdout"); adapter_result = control.get("result")
    if control.get("control") != {"version": 1, "state": "completed"} or adapter_result != outcome_result or not isinstance(adapter_result, Mapping) or set(adapter_result) != {"schema_version", "request_hash", "output", "output_hash", "runtime"} or adapter_result.get("schema_version") != 1:
        raise ValueError("feedback Grok v3 adapter control replay drifted")
    output, lineage = v2._descendant(adapter_result.get("output"), preparation); runtime = adapter_result.get("runtime")
    required_runtime = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "identity_evidence", "execution_policy", "nonvisual_max_turns", "observed_turns", "cli_version", "subscription_receipt_hash", "command_identity", "request_id_hash", "session_id_hash"}
    if not isinstance(runtime, Mapping) or not required_runtime <= set(runtime) or runtime.get("adapter_version") != 1 or runtime.get("requested_model") != route.get("model") or runtime.get("reported_model") != route.get("reported_model") or runtime.get("requested_reasoning_effort") != route.get("reasoning_effort") or runtime.get("reasoning_attested") is not False or runtime.get("identity_evidence") != "requested_only" or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1 or runtime.get("cli_version") != evidence.get("grok_cli_version") or runtime.get("subscription_receipt_hash") != evidence.get("subscription_receipt_hash") or runtime.get("command_identity") != route.get("grok_command_identity") or sha256(canonical(runtime.get("command_identity"))) != evidence.get("grok_command_identity_sha256") or adapter_result.get("request_hash") != sha256(canonical({"prompt": prompt.decode("utf-8")})) or adapter_result.get("output_hash") != sha256(canonical(output)):
        raise ValueError("feedback Grok v3 native runtime/response binding drifted")
    request_id, session_id = runtime.get("request_id_hash"), runtime.get("session_id_hash")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (request_id, session_id)) or request_id == session_id:
        raise ValueError("feedback Grok v3 runtime identity is invalid")
    return control, adapter_result, output, lineage, runtime


def _admit_completed_root(root: Path, sample: str) -> dict[str, Any]:
    v2 = _v2(); required = PREPARED | {"launch-intent.json", "adapter-stdout.bin", "adapter-control-envelope.json", "runtime-identity.json", "execution-receipt.json", "result.json"}
    if not root.is_dir() or not _plain(root, directory=True) or {entry.name for entry in root.iterdir()} != required or any(not _plain(entry, directory=False) for entry in root.iterdir()): raise ValueError("feedback Grok v3 completed root inventory is incomplete or unsafe")
    raw = {name: stable_bytes(root / name) for name in required}; prepared = _canonical_object(raw["prepared.json"], "prepared record")
    if prepared.get("sample_id") != sample or not isinstance(prepared.get("route"), Mapping) or not isinstance(prepared.get("route_evidence"), Mapping): raise ValueError("feedback Grok v3 prepared sample/route binding drifted")
    preparation_raw, preparation = v2._preparation(root / "dspy-input-preparation.json"); feedback_raw, feedback, authority = _frozen_feedback(root, str(prepared.get("feedback_sha256")))
    if preparation_raw != raw["dspy-input-preparation.json"] or feedback_raw != raw["r4-feedback.json"]: raise ValueError("feedback Grok v3 persisted input bytes drifted")
    ack = _canonical_object(raw["authorization-acknowledgement.json"], "acknowledgement"); acknowledgement = ack.get("acknowledgement_sha256")
    expected_prepared, files = _artifacts(v2, sample, preparation_raw, preparation, feedback_raw, feedback, authority, prepared["route"], prepared["route_evidence"], acknowledgement)
    if prepared != expected_prepared or any(raw[name] != content for name, content in files.items()): raise ValueError("feedback Grok v3 prepared replay drifted")
    intent = _canonical_object(raw["launch-intent.json"], "launch intent")
    expected_intent = {"format_version": 3, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "prompt_sha256": prepared["prompt_sha256"], "route_evidence": prepared["route_evidence"], "native_contact_proven": False}
    if intent != expected_intent: raise ValueError("feedback Grok v3 launch intent replay drifted")
    control, adapter_result, output, lineage, runtime = _validate_completed_response(v2, raw["adapter-stdout.bin"], _canonical_object(raw["adapter-control-envelope.json"], "stored adapter control").get("result"), preparation, raw["prompt-request.bin"], prepared["route"], prepared["route_evidence"])
    stored_control = _canonical_object(raw["adapter-control-envelope.json"], "stored adapter control")
    if stored_control != control: raise ValueError("feedback Grok v3 stored adapter control drifted")
    evidence, route = prepared["route_evidence"], prepared["route"]
    request_id, session_id = runtime.get("request_id_hash"), runtime.get("session_id_hash")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (request_id, session_id)) or request_id == session_id or _canonical_object(raw["runtime-identity.json"], "runtime identity") != runtime: raise ValueError("feedback Grok v3 runtime identity is invalid")
    receipt = _canonical_object(raw["execution-receipt.json"], "receipt"); result = _canonical_object(raw["result.json"], "result")
    expected_receipt = {"format_version": 3, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v3_native_receipt", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "launch_intent_sha256": sha256(raw["launch-intent.json"]), "adapter_stdout_sha256": sha256(raw["adapter-stdout.bin"]), "feedback_sha256": sha256(feedback_raw), "prompt_sha256": prepared["prompt_sha256"], "response_schema_sha256": prepared["response_schema_sha256"], "route_evidence": evidence, "provider_calls_made": 1, "process_launches": 1, "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "runtime": dict(runtime), "lineage": lineage, "descendant_output_sha256": sha256(canonical(output))}
    expected_result = {"format_version": 3, "study_id": STUDY_ID, "kind": "feedback_bound_grok_v3_result", "sample_id": sample, "descendant": output, "descendant_sha256": sha256(canonical(output)), "provider_calls_made": 1, "process_launches": 1}
    if receipt != expected_receipt or result != expected_result: raise ValueError("feedback Grok v3 receipt/result replay drifted")
    return {"sample_id": sample, "state": "native_descendant_received", "provider_calls_made": 1, "process_launches": 1, "descendant_sha256": expected_result["descendant_sha256"]}


def _admit_child_result(root: Path, sample: str, value: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("state") == "native_descendant_received":
        admitted = _admit_completed_root(root, sample)
        if dict(value) != admitted: raise ValueError("feedback Grok v3 child success summary drifted")
        return admitted
    if value.get("kind") in {"definitely_not_contacted", "reconcile_required_after_process_launch"} and root.is_dir() and _plain(root, directory=True) and stable_bytes(root / "result.json") == canonical(dict(value)):
        return dict(value)
    raise ValueError("feedback Grok v3 child result is not durably admitted")


def _strand_isolated_child(root: Path, sample: str, detail: str) -> None:
    if not root.is_dir() or not _plain(root, directory=True) or any((root / name).exists() for name in ("launch-intent.json", "adapter-stdout.bin", "execution-receipt.json", "result.json", ISOLATION_RECONCILE)): return
    _write_new(root / ISOLATION_RECONCILE, canonical({"format_version": 3, "study_id": STUDY_ID, "kind": "isolated_child_reconcile_required", "sample_id": sample, "detail": detail, "provider_calls_made": None, "process_launches": None, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown", "retry_policy": "fresh_output_root_required_no_in_place_retry"}))


async def execute_wave(*, output_root: Path, sample_ids: list[str | int], dspy_input_preparation_path: Path, feedback_path: Path, feedback_sha256: str, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool) -> list[dict[str, Any]]:
    if allow_remote is not True: raise ValueError("feedback Grok v3 requires explicit allow_remote=True")
    _contract(); _raw, feedback, _authority = _feedback(Path(feedback_path), feedback_sha256); samples = [_sample(feedback["wave_id"], sample_id) for sample_id in sample_ids]
    if len(samples) != 10 or len(set(samples)) != 10: raise ValueError("feedback Grok v3 wave must contain exactly ten distinct samples")
    limit = asyncio.Semaphore(10)
    async def one(sample_id: str | int, sample: str) -> dict[str, Any]:
        async with limit:
            gate = Path(output_root) / ".isolated-gates" / f"{sample}-{uuid.uuid4().hex}.gate"; child: asyncio.subprocess.Process | None = None; owner: _ChildTreeOwner | None = None
            argv = [sys.executable, str(Path(__file__).resolve()), "--execute-one", "--allow-remote", "--output-root", str(Path(output_root)), "--sample-id", str(sample_id), "--dspy-input-preparation", str(Path(dspy_input_preparation_path)), "--feedback", str(Path(feedback_path)), "--feedback-sha256", feedback_sha256, "--queue-root", str(Path(queue_root)), "--authorization-acknowledgement-sha256", authorization_acknowledgement_sha256, "--isolation-gate", str(gate)]
            try:
                kwargs: dict[str, Any] = {"stdout": asyncio.subprocess.PIPE, "stderr": asyncio.subprocess.PIPE}
                if os.name == "nt": kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                else: kwargs["start_new_session"] = True
                child = await asyncio.create_subprocess_exec(*argv, **kwargs); owner = _ChildTreeOwner(child); _safe_output_ancestry(gate.parent); gate.parent.mkdir(parents=True, exist_ok=True); _write_new(gate, b"feedback-grok-v3-isolation-gate\n")
                stdout, _stderr = await asyncio.wait_for(child.communicate(), timeout=ISOLATED_CHILD_TIMEOUT_SECONDS)
                if child.returncode != 0: raise ValueError("nonzero child")
                value = json.loads(stdout.decode("utf-8"))
                if not isinstance(value, dict) or canonical(value) != stdout or value.get("sample_id") != sample: raise ValueError("malformed child result")
                return _admit_child_result(Path(output_root) / sample, sample, value)
            except asyncio.CancelledError:
                if owner is not None: await owner.stop()
                elif child is not None: await _stop_unowned_child(child)
                _strand_isolated_child(Path(output_root) / sample, sample, "CancelledError"); raise
            except BaseException as error:
                if owner is not None: await owner.stop()
                elif child is not None: await _stop_unowned_child(child)
                _strand_isolated_child(Path(output_root) / sample, sample, type(error).__name__)
                return {"sample_id": sample, "state": "isolated_child_reconcile_required", "provider_calls_made": None, "process_launches": None, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown"}
            finally:
                if owner is not None: owner.close()
                if gate.exists(): gate.unlink()
                try: gate.parent.rmdir()
                except OSError: pass
    return await asyncio.gather(*(one(sample_id, sample) for sample_id, sample in zip(sample_ids, samples, strict=True)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); modes = parser.add_mutually_exclusive_group(required=True); modes.add_argument("--prepare-only", action="store_true"); modes.add_argument("--execute-one", action="store_true"); modes.add_argument("--execute-wave", action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--sample-id"); parser.add_argument("--dspy-input-preparation", type=Path, required=True); parser.add_argument("--feedback", type=Path, required=True); parser.add_argument("--feedback-sha256", required=True); parser.add_argument("--queue-root", type=Path, required=True); parser.add_argument("--authorization-acknowledgement-sha256", required=True); parser.add_argument("--isolation-gate", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.isolation_gate is not None: _await_isolation_gate(args.isolation_gate)
    common = {"output_root": args.output_root, "dspy_input_preparation_path": args.dspy_input_preparation, "feedback_path": args.feedback, "feedback_sha256": args.feedback_sha256, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.execute_wave:
        if not args.allow_remote or args.sample_id: parser.error("--execute-wave requires --allow-remote and forbids --sample-id")
        result = asyncio.run(execute_wave(**common, sample_ids=list(range(1, 11)), allow_remote=True))
        print(canonical(result).decode("utf-8"), end=""); return 0
    if not args.sample_id: parser.error("--sample-id is required outside --execute-wave")
    common["sample_id"] = args.sample_id
    if args.prepare_only:
        if args.allow_remote: parser.error("--prepare-only forbids --allow-remote")
        result = prepare_one(**common)
    else:
        if not args.allow_remote: parser.error("--execute-one requires --allow-remote")
        result = execute_one(**common, allow_remote=True)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
