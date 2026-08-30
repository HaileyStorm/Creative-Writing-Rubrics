#!/usr/bin/env python3
"""One-shot governed Grok descendant collection from an immutable DSPy preparation."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v2"
CONTRACT_PATH = HERE / "study-contract.json"
OPTIMIZER_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1" / "optimizer.py"
OPTIMIZER_CONTRACT_PATH = OPTIMIZER_PATH.with_name("study-contract.json")
NATIVE_EXEC_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
GROK_ADAPTER_PATH = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\adapters\grok_exec.py")
CONTRACT_SHA256 = "48057e730c9c3d16cbcbb79c81b95da046e0adc0e25064961cf79628a008ffd6"
OPTIMIZER_SHA256 = "8355382a5e9e48b020607306412613b6217a14b7aa253596635d2186192fe4e1"
OPTIMIZER_CONTRACT_SHA256 = "c32b563822c6ffe0c48647cb49c1a32f9825b7ee4c64e1a967b3bedc2a8098ec"
NATIVE_EXEC_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
GROK_ADAPTER_SHA256 = "e12e8864094d96d9930602f42588238b94f506b4815f80f0215b7b5290b7b599"
CAPTURE_WRAPPER_PATH = HERE / "capture_wrapper.py"
CAPTURE_WRAPPER_SHA256 = "012144f9e3cb328131111bfc32bcab79ec5581c1020d0681ee883f02bfc58dc8"
PREPARATION_FILE_SHA256 = "dd6dc97e7474d169eef384cafa14ab71237a6b45ea572b8bb9829ca6f8bb3e56"
PREPARATION_SHA256 = "b65b42f839b61550036acd32b4fb151cc1a353fd76235ae9cc1739c3e93e8c60"
SYSTEM_PROMPT = "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."
TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]
PREPARED = frozenset({"dspy-input-preparation.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
OUTPUT_FIELDS = frozenset({"descendant_instruction_base64", "descendant_profile_base64"})


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
        if not _plain(current): raise ValueError(f"balanced DSPy Grok v2 unsafe path: {current}")
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size): raise ValueError("balanced DSPy Grok v2 file identity drifted")
        raw = handle.read(); after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size): raise ValueError("balanced DSPy Grok v2 file changed during read")
    return raw


def _load(path: Path, expected: str, name: str) -> ModuleType:
    raw = stable_bytes(path)
    if sha256(raw) != expected: raise ValueError(f"balanced DSPy Grok v2 pinned dependency drifted: {path.name}")
    module = ModuleType(name); module.__file__ = str(path); exec(compile(raw, str(path), "exec"), module.__dict__)
    if stable_bytes(path) != raw: raise ValueError(f"balanced DSPy Grok v2 loaded dependency drifted: {path.name}")
    return module


def _contract() -> dict[str, Any]:
    raw = stable_bytes(CONTRACT_PATH)
    if sha256(raw) != CONTRACT_SHA256: raise ValueError("balanced DSPy Grok v2 study contract drifted")
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("balanced DSPy Grok v2 study contract is invalid") from error
    expected = {"authority", "dspy", "execution", "format_version", "input", "optimizer", "study_id"}
    if set(value) != expected or value.get("study_id") != STUDY_ID or value.get("format_version") != 2 or value["input"] != {"preparation_file_sha256": PREPARATION_FILE_SHA256, "preparation_sha256": PREPARATION_SHA256, "producer_study_id": "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1"} or value["execution"].get("nonvisual_max_turns") != 1 or value["execution"].get("capture_wrapper_sha256") != CAPTURE_WRAPPER_SHA256:
        raise ValueError("balanced DSPy Grok v2 study contract semantics drifted")
    return value


def _optimizer() -> ModuleType:
    if sha256(stable_bytes(OPTIMIZER_CONTRACT_PATH)) != OPTIMIZER_CONTRACT_SHA256: raise ValueError("balanced DSPy Grok v2 optimizer contract drifted")
    return _load(OPTIMIZER_PATH, OPTIMIZER_SHA256, "_balanced_dspy_v2_optimizer")


def _native() -> ModuleType:
    return _load(NATIVE_EXEC_PATH, NATIVE_EXEC_SHA256, "_balanced_dspy_v2_native")


def _decode(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str): raise ValueError(f"balanced DSPy Grok v2 {label} is not base64")
    try: return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error: raise ValueError(f"balanced DSPy Grok v2 {label} is not base64") from error


def _canonical_object(raw: bytes, *, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"balanced DSPy Grok v2 {label} is invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw: raise ValueError(f"balanced DSPy Grok v2 {label} is not canonical")
    return value


def _preparation(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = stable_bytes(path)
    if sha256(raw) != PREPARATION_FILE_SHA256: raise ValueError("balanced DSPy Grok v2 preparation file hash drifted")
    value = _canonical_object(raw, label="preparation")
    keys = {"format_version", "study_id", "kind", "dspy_program", "inputs", "inputs_sha256", "training_result_sha256", "training_diagnostics_sha256", "dependencies", "provider_calls_made", "dispatch_authority", "runtime_authority", "confirmation", "preparation_sha256"}
    if set(value) != keys or value.get("study_id") != "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1" or value.get("kind") != "dspy_predict_input_preparation" or value.get("preparation_sha256") != PREPARATION_SHA256:
        raise ValueError("balanced DSPy Grok v2 preparation semantics drifted")
    optimizer = _optimizer(); optimizer.contract()
    if value.get("dependencies") != optimizer._output_dependencies() or value.get("dspy_program") != "Predict(BalancedDescendantSignature)@3.3.1" or value.get("provider_calls_made") != 0 or value.get("dispatch_authority") != "none_governed_executor_required" or value.get("runtime_authority") != "none" or value.get("confirmation") != {"status": "unopened", "cells": 0}:
        raise ValueError("balanced DSPy Grok v2 preparation authority or dependency drifted")
    inputs = value.get("inputs")
    if not isinstance(inputs, Mapping) or set(inputs) != {"parent_candidate_id", "parent_instruction_base64", "parent_profile_base64", "training_result_base64", "training_diagnostics_base64"} or value.get("inputs_sha256") != sha256(canonical(dict(inputs))):
        raise ValueError("balanced DSPy Grok v2 preparation input binding drifted")
    for name in ("parent_instruction_base64", "parent_profile_base64", "training_result_base64", "training_diagnostics_base64"): _decode(inputs[name], label=name)
    if not isinstance(inputs["parent_candidate_id"], str) or not inputs["parent_candidate_id"]: raise ValueError("balanced DSPy Grok v2 parent candidate is invalid")
    return raw, value


def _sample(value: str | int) -> str:
    try: number = int(value)
    except (TypeError, ValueError) as error: raise ValueError("balanced DSPy Grok v2 sample id must be 1 through 10") from error
    if str(value) != str(number) or not 1 <= number <= 10: raise ValueError("balanced DSPy Grok v2 sample id must be 1 through 10")
    return f"sample-{number:02d}"


def _prompt(preparation: Mapping[str, Any]) -> bytes:
    """This is an explicit governed serialization, not a claimed DSPy renderer capture."""
    request = {"signature": "BalancedDescendantSignature", "inputs": dict(preparation["inputs"]), "output_fields": sorted(OUTPUT_FIELDS), "constraints": ["Return only the required JSON object.", "Create versioned descendants only.", "No tools, web, plans, memory, or subagents."]}
    return ("Development-only HANNA descendant generation.\n" + canonical(request).decode("utf-8")).encode("utf-8")


def _schema() -> bytes:
    return canonical({"$schema_version": 1, "type": "object", "additionalProperties": False, "required": sorted(OUTPUT_FIELDS), "properties": {field: {"type": "string", "minLength": 1} for field in sorted(OUTPUT_FIELDS)}})


def _write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _safe_output_ancestry(path: Path) -> None:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True): raise ValueError(f"balanced DSPy Grok v2 output ancestry is unsafe: {current}")


def _route(queue_root: Path) -> tuple[ModuleType, Any, dict[str, Any], dict[str, Any]]:
    native = _native(); route, evidence = native.validate_live_grok_route(Path(queue_root))
    if sha256(stable_bytes(GROK_ADAPTER_PATH)) != GROK_ADAPTER_SHA256 or sha256(stable_bytes(CAPTURE_WRAPPER_PATH)) != CAPTURE_WRAPPER_SHA256 or route.get("adapter") != "grok_exec" or route.get("nonvisual_max_turns") != 1 or len(route.get("command", [])) < 2 or Path(route["command"][1]).resolve() != GROK_ADAPTER_PATH.resolve():
        raise ValueError("balanced DSPy Grok v2 actual adapter identity drifted")
    broker = native._load_broker_class()(Path(queue_root))
    return native, broker, route, evidence


def _artifacts(sample: str, raw: bytes, preparation: Mapping[str, Any], prompt: bytes, schema: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement): raise ValueError("balanced DSPy Grok v2 acknowledgement must be lowercase SHA-256")
    route_identity = {name: route[name] for name in ("name", "provider", "model", "adapter", "destination")}
    disclosure = {"format_version": 2, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "sample_id": sample, "route_identity": route_identity, "prompt": {"bytes": len(prompt), "sha256": sha256(prompt), "text": prompt.decode("utf-8")}, "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")}, "system_prompt_override": SYSTEM_PROMPT, "tool_free_argv": TOOL_FREE_ARGV, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    ack = {"format_version": 2, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "sample_id": sample, "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha256(canonical(disclosure)), "destination": route["destination"]}
    proof = {"format_version": 2, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "sample_id": sample, "route_evidence": dict(evidence), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_preparation", "sample_id": sample, "preparation_file_sha256": sha256(raw), "preparation_sha256": preparation["preparation_sha256"], "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "capture_wrapper_sha256": CAPTURE_WRAPPER_SHA256, "parent_candidate_id": preparation["inputs"]["parent_candidate_id"], "parent_instruction_sha256": sha256(_decode(preparation["inputs"]["parent_instruction_base64"], label="parent instruction")), "parent_profile_sha256": sha256(_decode(preparation["inputs"]["parent_profile_base64"], label="parent profile")), "route_evidence": dict(evidence), "disclosure_sha256": sha256(canonical(disclosure)), "acknowledgement_sha256": sha256(canonical(ack)), "route_proof_sha256": sha256(canonical(proof)), "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    return prepared, {"dspy-input-preparation.json": raw, "prompt-request.bin": prompt, "response-schema.json": schema, "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(ack), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def _validate_root(root: Path, files: Mapping[str, bytes]) -> None:
    if not root.is_dir() or not _plain(root, directory=True): raise ValueError("balanced DSPy Grok v2 prepared root is unsafe")
    entries = {entry.name: entry for entry in root.iterdir()}
    if set(entries) != set(files) or any(not _plain(entry, directory=False) for entry in entries.values()): raise ValueError("balanced DSPy Grok v2 prepared inventory drifted")
    for name, raw in files.items():
        if stable_bytes(root / name) != raw: raise ValueError(f"balanced DSPy Grok v2 prepared artifact drifted: {name}")


def prepare_one(*, output_root: Path, sample_id: str | int, dspy_input_preparation_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    _contract(); sample = _sample(sample_id); raw, preparation = _preparation(Path(dspy_input_preparation_path)); prompt, schema = _prompt(preparation), _schema()
    _native, _broker, route, evidence = _route(Path(queue_root)); root = Path(output_root) / sample
    if root.exists(): raise ValueError("balanced DSPy Grok v2 refuses an existing sample root")
    _safe_output_ancestry(root.parent)
    prepared, files = _artifacts(sample, raw, preparation, prompt, schema, route, evidence, authorization_acknowledgement_sha256)
    root.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in files.items(): _write_new(root / name, content)
    except BaseException:
        raise
    return {"format_version": 2, "study_id": STUDY_ID, "sample_id": sample, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "prepared_sha256": sha256(canonical(prepared))}


def _adapter_command(broker: Any, route: Mapping[str, Any], schema: Mapping[str, Any]) -> dict[str, Any]:
    receipt = broker._load_json_artifact(route["subscription_receipt_hash"])
    if route.get("nonvisual_max_turns") != 1: raise ValueError("balanced DSPy Grok v2 route nonvisual turn bound drifted")
    command = [*route["command"], "--grok-command-json", canonical(route["grok_command"]).decode("utf-8"), "--model", route["model"], "--reported-model", route["reported_model"], "--reasoning-effort", route["reasoning_effort"], "--output-schema-json", canonical(schema).decode("utf-8"), "--expected-command-identity-json", canonical(route["grok_command_identity"]).decode("utf-8"), "--cli-version-command-json", canonical(route["cli_version_command"]).decode("utf-8"), "--expected-cli-version-identity-json", canonical(route["cli_version_identity"]).decode("utf-8"), "--expected-cli-version", route["grok_cli_version"], "--subscription-receipt-json", canonical(receipt).decode("utf-8"), "--broker-root", str(broker.root), "--timeout-seconds", str(route["timeout_seconds"]), "--nonvisual-max-turns", str(route["nonvisual_max_turns"])]
    return {**route, "command": command, "output_schema": dict(schema)}


def _adapter_once(broker: Any, route: Mapping[str, Any], request: Mapping[str, Any], capture_path: Path) -> tuple[Any, bytes]:
    """Keep the adapter and its child in Broker's Job Object while teeing exact stdout to evidence."""
    adapter_route = _adapter_command(broker, route, json.loads(_schema().decode("utf-8"))); capture_path = Path(capture_path)
    if capture_path.exists() or sha256(stable_bytes(CAPTURE_WRAPPER_PATH)) != CAPTURE_WRAPPER_SHA256: raise ValueError("balanced DSPy Grok v2 capture wrapper state drifted")
    wrapper_route = {**adapter_route, "command": [sys.executable, str(CAPTURE_WRAPPER_PATH), "--capture-path", str(capture_path.resolve()), "--", *adapter_route["command"]]}
    seen: list[bytes] = []
    def parse(raw: bytes) -> Any:
        seen.append(raw)
        return broker._parse_grok_exec_envelope(raw, adapter_route, dict(request))
    outcome = broker._run_subprocess(wrapper_route, dict(request), parse)
    raw = stable_bytes(capture_path) if capture_path.exists() else b""
    if seen and raw != seen[0]: return SimpleNamespace(state="ambiguous", detail="capture wrapper stdout differs from broker stdout", result=None), raw
    return outcome, raw


def _descendant(value: Any, preparation: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    if not isinstance(value, Mapping) or set(value) != OUTPUT_FIELDS: raise ValueError("balanced DSPy Grok v2 adapter output schema drifted")
    instruction = _decode(value["descendant_instruction_base64"], label="descendant instruction")
    profile = _decode(value["descendant_profile_base64"], label="descendant profile")
    try: text = instruction.decode("utf-8"); profile_value = json.loads(profile.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("balanced DSPy Grok v2 descendant bytes are invalid") from error
    if not text.strip() or "\x00" in text or not isinstance(profile_value, dict) or not profile_value or canonical(profile_value) != profile:
        raise ValueError("balanced DSPy Grok v2 descendant semantics are invalid")
    parent_instruction = _decode(preparation["inputs"]["parent_instruction_base64"], label="parent instruction")
    parent_profile = _decode(preparation["inputs"]["parent_profile_base64"], label="parent profile")
    if instruction == parent_instruction or profile == parent_profile: raise ValueError("balanced DSPy Grok v2 descendant is parent-identical")
    output = {field: str(value[field]) for field in sorted(OUTPUT_FIELDS)}
    lineage = {"parent_candidate_id": str(preparation["inputs"]["parent_candidate_id"]), "parent_instruction_sha256": sha256(parent_instruction), "parent_profile_sha256": sha256(parent_profile), "descendant_instruction_sha256": sha256(instruction), "descendant_profile_sha256": sha256(profile)}
    return output, lineage


def _persist_terminal(root: Path, sample: str, *, state: str, control_raw: bytes, detail: str | None, launches: int) -> dict[str, Any]:
    capture = root / "adapter-stdout.bin"
    if capture.exists():
        if control_raw and stable_bytes(capture) != control_raw: raise ValueError("balanced DSPy Grok v2 persisted capture differs from adapter stdout")
    elif control_raw:
        _write_new(capture, control_raw)
    result = {"format_version": 2, "study_id": STUDY_ID, "kind": state, "sample_id": sample, "adapter_stdout_sha256": sha256(control_raw) if control_raw else None, "detail": detail, "provider_calls_made": 0 if state == "definitely_not_contacted" else None, "process_launches": launches, "native_contact_proven": False, "native_endpoint_contact_cardinality": "zero" if state == "definitely_not_contacted" else "unknown"}
    _write_new(root / "result.json", canonical(result)); return result


def execute_one(*, output_root: Path, sample_id: str | int, dspy_input_preparation_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("balanced DSPy Grok v2 requires explicit allow_remote=True")
    _contract(); sample = _sample(sample_id); raw, preparation = _preparation(Path(dspy_input_preparation_path)); prompt, schema_raw = _prompt(preparation), _schema(); root = Path(output_root) / sample
    if any((root / name).exists() for name in ("launch-intent.json", "adapter-stdout.bin", "execution-receipt.json", "result.json")): raise ValueError("balanced DSPy Grok v2 forbids resend from a stranded root")
    _native, broker, route, evidence = _route(Path(queue_root)); prepared, files = _artifacts(sample, raw, preparation, prompt, schema_raw, route, evidence, authorization_acknowledgement_sha256); _validate_root(root, files)
    intent = {"format_version": 2, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(canonical(prepared)), "prompt_sha256": sha256(prompt), "route_evidence": evidence, "native_contact_proven": False}
    _write_new(root / "launch-intent.json", canonical(intent))
    try: outcome, control_raw = _adapter_once(broker, route, {"prompt": prompt.decode("utf-8")}, root / "adapter-stdout.bin")
    except BaseException as error:
        return _persist_terminal(root, sample, state="reconcile_required_after_process_launch", control_raw=b"", detail=type(error).__name__, launches=1)
    state = getattr(outcome, "state", None); detail = getattr(outcome, "detail", None)
    if state == "definitely_not_contacted": return _persist_terminal(root, sample, state=state, control_raw=control_raw, detail=detail, launches=1)
    if state != "completed": return _persist_terminal(root, sample, state="reconcile_required_after_process_launch", control_raw=control_raw, detail=detail, launches=1)
    try:
        if not control_raw: raise ValueError("balanced DSPy Grok v2 adapter omitted control evidence")
        control = json.loads(control_raw.decode("utf-8")); result = getattr(outcome, "result", None)
        if not isinstance(control, dict) or control.get("control") != {"version": 1, "state": "completed"} or control.get("result") != result or not isinstance(result, Mapping): raise ValueError("balanced DSPy Grok v2 adapter control truth drifted")
        output, lineage = _descendant(result.get("output"), preparation); runtime = result.get("runtime")
        if not isinstance(runtime, Mapping) or runtime.get("adapter_version") != 1 or runtime.get("request_id_hash") == runtime.get("session_id_hash") or sha256(canonical(output)) != result.get("output_hash"):
            raise ValueError("balanced DSPy Grok v2 adapter runtime or output binding drifted")
        receipt = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_native_receipt", "sample_id": sample, "prepared_sha256": sha256(canonical(prepared)), "launch_intent_sha256": sha256(canonical(intent)), "adapter_stdout_sha256": sha256(control_raw), "preparation_file_sha256": sha256(raw), "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(schema_raw), "route_evidence": evidence, "provider_calls_made": 1, "process_launches": 1, "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "runtime": dict(runtime), "lineage": lineage, "descendant_output_sha256": sha256(canonical(output))}
        final = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_result", "sample_id": sample, "descendant": output, "descendant_sha256": sha256(canonical(output)), "provider_calls_made": 1, "process_launches": 1}
        capture = root / "adapter-stdout.bin"
        if capture.exists():
            if stable_bytes(capture) != control_raw: raise ValueError("balanced DSPy Grok v2 capture differs from completed adapter stdout")
        else:
            _write_new(capture, control_raw)
        _write_new(root / "adapter-control-envelope.json", canonical(control)); _write_new(root / "runtime-identity.json", canonical(dict(runtime))); _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical(final))
        return {"sample_id": sample, "state": "native_descendant_received", "provider_calls_made": 1, "process_launches": 1, "descendant_sha256": final["descendant_sha256"]}
    except BaseException as error:
        capture = root / "adapter-stdout.bin"
        if capture.exists():
            if control_raw and stable_bytes(capture) != control_raw: raise ValueError("balanced DSPy Grok v2 capture differs from failed adapter stdout")
        elif control_raw:
            _write_new(capture, control_raw)
        return _persist_terminal(root, sample, state="reconcile_required_after_process_launch", control_raw=b"", detail=type(error).__name__, launches=1)


def _admit_completed_root(cell: Path, sample: str) -> tuple[dict[str, Any], str, str, str, str, str, str]:
    expected = PREPARED | {"launch-intent.json", "adapter-stdout.bin", "adapter-control-envelope.json", "runtime-identity.json", "execution-receipt.json", "result.json"}
    if not cell.is_dir() or not _plain(cell, directory=True) or {entry.name for entry in cell.iterdir()} != expected or any(not _plain(entry, directory=False) for entry in cell.iterdir()): raise ValueError("balanced DSPy Grok v2 all-ten inventory is incomplete or unsafe")
    raw = {name: stable_bytes(cell / name) for name in expected}; preparation_raw, preparation = _preparation(cell / "dspy-input-preparation.json"); prompt, schema = raw["prompt-request.bin"], raw["response-schema.json"]
    if preparation_raw != raw["dspy-input-preparation.json"] or prompt != _prompt(preparation) or schema != _schema(): raise ValueError("balanced DSPy Grok v2 persisted input, prompt, or schema drifted")
    disclosure = _canonical_object(raw["disclosure.json"], label="disclosure"); ack = _canonical_object(raw["authorization-acknowledgement.json"], label="acknowledgement"); proof = _canonical_object(raw["zero-charge-route-proof.json"], label="route proof"); prepared = _canonical_object(raw["prepared.json"], label="prepared record"); intent = _canonical_object(raw["launch-intent.json"], label="launch intent")
    route = disclosure.get("route_identity"); evidence = proof.get("route_evidence")
    if (not isinstance(route, Mapping) or set(route) != {"name", "provider", "model", "adapter", "destination"} or route.get("provider") != "xai_grok_build" or route.get("model") != "grok-4.6" or route.get("adapter") != "grok_exec" or not isinstance(evidence, Mapping) or proof.get("study_id") != STUDY_ID or proof.get("sample_id") != sample or proof.get("zero_charge_only") is not True or proof.get("paid_fallback_forbidden") is not True): raise ValueError("balanced DSPy Grok v2 persisted route proof drifted")
    expected_disclosure = {"format_version": 2, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "sample_id": sample, "route_identity": dict(route), "prompt": {"bytes": len(prompt), "sha256": sha256(prompt), "text": prompt.decode("utf-8")}, "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")}, "system_prompt_override": SYSTEM_PROMPT, "tool_free_argv": TOOL_FREE_ARGV, "tools_enabled": False, "web_search_enabled": False, "plans_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    expected_ack = {"format_version": 2, "study_id": STUDY_ID, "kind": "caller_authorization_acknowledgement_reference", "sample_id": sample, "acknowledgement_sha256": ack.get("acknowledgement_sha256"), "disclosure_sha256": sha256(raw["disclosure.json"]), "destination": route["destination"]}
    if disclosure != expected_disclosure or not re.fullmatch(r"[0-9a-f]{64}", str(ack.get("acknowledgement_sha256"))) or ack != expected_ack: raise ValueError("balanced DSPy Grok v2 persisted disclosure or acknowledgement drifted")
    parent_instruction = _decode(preparation["inputs"]["parent_instruction_base64"], label="parent instruction"); parent_profile = _decode(preparation["inputs"]["parent_profile_base64"], label="parent profile")
    expected_prepared = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_preparation", "sample_id": sample, "preparation_file_sha256": sha256(preparation_raw), "preparation_sha256": preparation["preparation_sha256"], "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "capture_wrapper_sha256": CAPTURE_WRAPPER_SHA256, "parent_candidate_id": preparation["inputs"]["parent_candidate_id"], "parent_instruction_sha256": sha256(parent_instruction), "parent_profile_sha256": sha256(parent_profile), "route_evidence": dict(evidence), "disclosure_sha256": sha256(raw["disclosure.json"]), "acknowledgement_sha256": sha256(raw["authorization-acknowledgement.json"]), "route_proof_sha256": sha256(raw["zero-charge-route-proof.json"]), "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    expected_intent = {"format_version": 2, "study_id": STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "prompt_sha256": sha256(prompt), "route_evidence": dict(evidence), "native_contact_proven": False}
    if prepared != expected_prepared or intent != expected_intent: raise ValueError("balanced DSPy Grok v2 persisted prepared or launch binding drifted")
    try: control = json.loads(raw["adapter-stdout.bin"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("balanced DSPy Grok v2 adapter stdout is invalid") from error
    stored_control = _canonical_object(raw["adapter-control-envelope.json"], label="stored adapter control")
    if not isinstance(control, dict) or control.get("control") != {"version": 1, "state": "completed"} or control.get("result") is None or stored_control != control: raise ValueError("balanced DSPy Grok v2 adapter control is not completed truth")
    adapter_result = control["result"]; runtime = adapter_result.get("runtime") if isinstance(adapter_result, Mapping) else None
    output, lineage = _descendant(adapter_result.get("output") if isinstance(adapter_result, Mapping) else None, preparation)
    if (not isinstance(runtime, Mapping) or set(adapter_result) != {"schema_version", "request_hash", "output", "output_hash", "runtime"} or adapter_result.get("schema_version") != 1 or adapter_result.get("request_hash") != sha256(canonical({"prompt": prompt.decode("utf-8")})) or adapter_result.get("output_hash") != sha256(canonical(output)) or runtime.get("adapter_version") != 1 or runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != "grok-4.6-build" or runtime.get("requested_reasoning_effort") != "high" or runtime.get("reasoning_attested") is not False or runtime.get("identity_evidence") != "requested_only" or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != 1 or runtime.get("observed_turns") != 1 or runtime.get("cli_version") != evidence.get("grok_cli_version") or runtime.get("subscription_receipt_hash") != evidence.get("subscription_receipt_hash") or sha256(canonical(runtime.get("command_identity"))) != evidence.get("grok_command_identity_sha256")):
        raise ValueError("balanced DSPy Grok v2 adapter runtime identity drifted")
    if _canonical_object(raw["runtime-identity.json"], label="runtime identity") != runtime: raise ValueError("balanced DSPy Grok v2 persisted runtime identity drifted")
    result = _canonical_object(raw["result.json"], label="result"); receipt = _canonical_object(raw["execution-receipt.json"], label="receipt")
    expected_result = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_result", "sample_id": sample, "descendant": output, "descendant_sha256": sha256(canonical(output)), "provider_calls_made": 1, "process_launches": 1}
    expected_receipt = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_native_receipt", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "launch_intent_sha256": sha256(raw["launch-intent.json"]), "adapter_stdout_sha256": sha256(raw["adapter-stdout.bin"]), "preparation_file_sha256": sha256(preparation_raw), "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "route_evidence": dict(evidence), "provider_calls_made": 1, "process_launches": 1, "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "runtime": dict(runtime), "lineage": lineage, "descendant_output_sha256": sha256(canonical(output))}
    if result != expected_result or receipt != expected_receipt: raise ValueError("balanced DSPy Grok v2 persisted result or receipt drifted")
    request_id, session_id = runtime.get("request_id_hash"), runtime.get("session_id_hash")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (request_id, session_id)): raise ValueError("balanced DSPy Grok v2 runtime contact identity is invalid")
    return {"sample_id": sample, "execution_root": str(cell), "prepared_sha256": sha256(raw["prepared.json"]), "receipt_sha256": sha256(raw["execution-receipt.json"]), "descendant_sha256": result["descendant_sha256"], "request_id_hash": request_id, "session_id_hash": session_id}, sha256(prompt), sha256(schema), sha256(preparation_raw), request_id, session_id, result["descendant_sha256"]


def freeze_all_ten(*, output_root: Path, manifest_path: Path) -> dict[str, Any]:
    """Provider-free all-sample admission; it has no optimizer or confirmation authority."""
    _contract()
    if sha256(stable_bytes(GROK_ADAPTER_PATH)) != GROK_ADAPTER_SHA256 or sha256(stable_bytes(CAPTURE_WRAPPER_PATH)) != CAPTURE_WRAPPER_SHA256: raise ValueError("balanced DSPy Grok v2 shared adapter or capture wrapper identity drifted before freeze")
    root = Path(output_root); rows: list[dict[str, Any]] = []; prompts: set[str] = set(); schemas: set[str] = set(); preparations: set[str] = set(); requests: set[str] = set(); sessions: set[str] = set(); descendants: set[str] = set()
    for number in range(1, 11):
        row, prompt_hash, schema_hash, prep_hash, request_id, session_id, descendant_hash = _admit_completed_root(root / _sample(number), _sample(number))
        if request_id in requests or session_id in sessions: raise ValueError("balanced DSPy Grok v2 request/session identity is duplicated")
        if descendant_hash in descendants: raise ValueError("balanced DSPy Grok v2 descendant is duplicated")
        requests.add(request_id); sessions.add(session_id); descendants.add(descendant_hash); prompts.add(prompt_hash); schemas.add(schema_hash); preparations.add(prep_hash); rows.append(row)
    if not (len(prompts) == len(schemas) == len(preparations) == 1): raise ValueError("balanced DSPy Grok v2 all-ten prompt/schema/preparation bytes differ")
    manifest = {"format_version": 2, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v2_all_ten_frozen_descendants", "samples": rows, "shared_prompt_sha256": next(iter(prompts)), "shared_response_schema_sha256": next(iter(schemas)), "preparation_file_sha256": next(iter(preparations)), "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "evaluation_authority": "none", "freeze_provider_calls_made": 0, "source_provider_calls_made": 10}
    manifest["manifest_sha256"] = sha256(canonical(manifest)); target = Path(manifest_path)
    if target.exists(): raise ValueError("balanced DSPy Grok v2 refuses to overwrite a freeze manifest")
    _safe_output_ancestry(target.parent)
    _write_new(target, canonical(manifest)); return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true"); modes.add_argument("--execute-one", action="store_true"); modes.add_argument("--freeze-all-ten", action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--sample-id"); parser.add_argument("--dspy-input-preparation", type=Path); parser.add_argument("--queue-root", type=Path); parser.add_argument("--authorization-acknowledgement-sha256"); parser.add_argument("--manifest-path", type=Path)
    args = parser.parse_args(argv)
    if args.freeze_all_ten:
        if args.allow_remote or args.sample_id or args.dspy_input_preparation or args.queue_root or args.authorization_acknowledgement_sha256 or not args.manifest_path: parser.error("--freeze-all-ten needs only --output-root and --manifest-path")
        result = freeze_all_ten(output_root=args.output_root, manifest_path=args.manifest_path)
    else:
        if not all((args.sample_id, args.dspy_input_preparation, args.queue_root, args.authorization_acknowledgement_sha256)): parser.error("sample, preparation, queue, and acknowledgement are required")
        common = {"output_root": args.output_root, "sample_id": args.sample_id, "dspy_input_preparation_path": args.dspy_input_preparation, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
        if args.prepare_only:
            if args.allow_remote: parser.error("--prepare-only forbids --allow-remote")
            result = prepare_one(**common)
        else:
            if not args.allow_remote: parser.error("--execute-one requires --allow-remote")
            result = execute_one(**common, allow_remote=True)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
