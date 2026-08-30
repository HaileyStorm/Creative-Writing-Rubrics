"""Provider-free reconciliation of immutable terminal v3 Grok roots."""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v3"
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3"
SOURCE_EXECUTOR_SHA256 = "44279db49369029b97a4e2f1216caf99e876b0548910f157bdb3f60f7ea42d4a"
SOURCE_CONTRACT_SHA256 = "b3f5d39e4d127d7ebd29ab9bbbd9c757f347349448b8c2b4d8c97510202888e2"
SOURCE_FEEDBACK_SHA256 = "5f122e0a90bc624960f53e9db9e8379ade46ed989a2e7c8f6f606c6b5e996064"
SAMPLE_PREFIX = "r4shrink-20260830a"
SOURCE_INVENTORY_SHA256 = {"r4shrink-20260830a-sample-01": "1116f1a453b77ba24f5cff46c0d14e239628a518c6cddc1feac8405637c17eb6", "r4shrink-20260830a-sample-02": "765c97986b81fea0692abd4c64480b5ec446e45ae2ca31481fefb4b028a296ec", "r4shrink-20260830a-sample-03": "b1e2a349060294154ace069cbb6abb69f1c28453e8313170b3ee01c4f89753f9", "r4shrink-20260830a-sample-04": "5b868401818b7b72949d497fb99ce7c998cecb2134d0072930e0622adfdccc2b", "r4shrink-20260830a-sample-05": "07114f70d4eaeab5ad6390c3fef6581ca6af472191216aee1abb685c039fdd03", "r4shrink-20260830a-sample-06": "19797a4b1d83bb116436a7d88fee49e4ac4b3a85e2b3d6190195c67c4071e920", "r4shrink-20260830a-sample-07": "1525e66ef8aa26b208b2981381438d7a251d7f995b0da98a2013b0346296ff3d", "r4shrink-20260830a-sample-08": "9eb03b4f1e8b644741234522e8f8c896445a819a379acfaa3f90c7db80720224", "r4shrink-20260830a-sample-09": "f4ddc243e20562a03bd279d0816e9ba43a35cac7e9f659a2528048fec4f06469", "r4shrink-20260830a-sample-10": "c9c4ebb7b6d498c19380f48ce367fe4b934069f3a45ac1ddf2c59164cdf93b54"}
ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "study-contract.json"
TERMINAL_FILES = frozenset({"adapter-stdout.bin", "authorization-acknowledgement.json", "disclosure.json", "dspy-input-preparation.json", "feedback-producer-contract.json", "feedback-producer-source.bin", "feedback-result-schema.json", "feedback-result.json", "feedback-selection-schema.json", "feedback-selection.json", "launch-intent.json", "prepared.json", "prompt-request.bin", "r4-feedback.json", "response-schema.json", "result.json", "zero-charge-route-proof.json"})
PROFILE_REQUIRED_KEYS = frozenset({"demonstrations", "dimension_weights", "factors", "fixed_mapping", "format_version", "immutable_cwr_commitments", "instruction_sha256", "same_bytes_for_models", "sampler", "study_id"})
PROFILE_ALLOWED_KEYS = PROFILE_REQUIRED_KEYS | {"parent_candidate_id", "version", "wave_id", "descendant_version", "feedback_kind", "lineage"}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def adapter_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def project_canonical(value: Any) -> bytes:
    return adapter_canonical(value) + b"\n"


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("reconcile v3 JSON has a duplicate key")
        value[key] = item
    return value


def _strict_json(raw: bytes, *, label: str) -> Any:
    def finite(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError(token)
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)), parse_float=finite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"reconcile v3 {label} is not strict UTF-8 JSON") from error
    return value


def _object(raw: bytes, *, label: str, canonical: bytes | None = None) -> dict[str, Any]:
    value = _strict_json(raw, label=label)
    if not isinstance(value, dict) or (canonical is not None and canonical != raw):
        raise ValueError(f"reconcile v3 {label} is not canonical object evidence")
    return value


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    try:
        stat = path.lstat()
    except OSError:
        return False
    if os.path.islink(path) or getattr(stat, "st_reparse_tag", 0):
        return False
    return path.is_dir() if directory else path.is_file() if directory is False else True


def _stable(path: Path) -> bytes:
    if not _plain(path, directory=False):
        raise ValueError(f"reconcile v3 unsafe or missing file: {path}")
    first = path.read_bytes(); second = path.read_bytes()
    if first != second:
        raise ValueError(f"reconcile v3 source changed while reading: {path}")
    return first


def _ancestry(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    if Path(path).absolute() != absolute:
        raise ValueError("reconcile v3 source path is unstable")
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists() and not _plain(current, directory=True):
            raise ValueError("reconcile v3 source ancestry is unsafe")


def _contract() -> dict[str, Any]:
    raw = _stable(CONTRACT); value = _object(raw, label="study contract", canonical=project_canonical(_strict_json(raw, label="study contract")))
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v3_terminal_reconciliation", "source": {"study_id": SOURCE_STUDY_ID, "executor_sha256": SOURCE_EXECUTOR_SHA256, "contract_sha256": SOURCE_CONTRACT_SHA256, "feedback_sha256": SOURCE_FEEDBACK_SHA256, "sample_prefix": SAMPLE_PREFIX, "terminal_inventory_sha256": SOURCE_INVENTORY_SHA256}, "authority": {"confirmation": {"status": "unopened", "cells": 0}, "local_only": True, "evaluation": False, "selection": False, "promotion": False, "runtime": False}}
    if value != expected:
        raise ValueError("reconcile v3 study contract semantics drifted")
    return value


def _b64(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str) or not value or not value.isascii() or re.search(r"\s", value):
        raise ValueError(f"reconcile v3 {label} base64 is invalid")
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except ValueError as error:
        raise ValueError(f"reconcile v3 {label} base64 is invalid") from error
    if base64.b64encode(raw).decode("ascii") != value:
        raise ValueError(f"reconcile v3 {label} base64 is noncanonical")
    return raw


def _inventory(cell: Path) -> dict[str, bytes]:
    if not _plain(cell, directory=True):
        raise ValueError("reconcile v3 terminal root is unsafe")
    entries = {item.name for item in cell.iterdir()}
    if entries != TERMINAL_FILES:
        raise ValueError("reconcile v3 terminal root inventory drifted")
    raw = {name: _stable(cell / name) for name in TERMINAL_FILES}
    if any(_plain(cell / name, directory=True) for name in TERMINAL_FILES):
        raise ValueError("reconcile v3 terminal artifact is not a plain file")
    digest = _inventory_digest(raw)
    if SOURCE_INVENTORY_SHA256.get(cell.name) != digest:
        raise ValueError("reconcile v3 terminal inventory is not the frozen live evidence")
    return raw


def _inventory_digest(raw: dict[str, bytes]) -> str:
    return sha256("".join(f"{name}:{sha256(raw[name])}\n" for name in sorted(raw)).encode("utf-8"))


def _prepared(raw: dict[str, bytes], sample: str) -> tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]:
    prepared = _object(raw["prepared.json"], label="prepared", canonical=project_canonical(_strict_json(raw["prepared.json"], label="prepared")))
    feedback = _object(raw["r4-feedback.json"], label="feedback", canonical=project_canonical(_strict_json(raw["r4-feedback.json"], label="feedback")))
    if sha256(raw["r4-feedback.json"]) != SOURCE_FEEDBACK_SHA256:
        raise ValueError("reconcile v3 feedback hash is not the frozen live feedback")
    expected = {"format_version": 3, "study_id": SOURCE_STUDY_ID, "kind": "feedback_bound_grok_v3_preparation", "sample_id": sample, "feedback_sha256": SOURCE_FEEDBACK_SHA256, "preparation_file_sha256": sha256(raw["dspy-input-preparation.json"]), "prompt_sha256": sha256(raw["prompt-request.bin"]), "response_schema_sha256": sha256(raw["response-schema.json"]), "disclosure_sha256": sha256(raw["disclosure.json"]), "acknowledgement_sha256": sha256(raw["authorization-acknowledgement.json"]), "route_proof_sha256": sha256(raw["zero-charge-route-proof.json"]), "provider_calls_made": 0, "process_launches": 0, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "selection_authority": "none"}
    for key, value in expected.items():
        if prepared.get(key) != value:
            raise ValueError(f"reconcile v3 prepared binding drifted: {key}")
    if prepared.get("feedback_sha256") != sha256(raw["r4-feedback.json"]):
        raise ValueError("reconcile v3 prepared feedback binding drifted")
    route, evidence = prepared.get("route"), prepared.get("route_evidence")
    if not isinstance(route, dict) or not isinstance(evidence, dict):
        raise ValueError("reconcile v3 prepared route binding is invalid")
    required_route = {"name": "grok-build-grok-4.6", "provider": "xai_grok_build", "adapter": "grok_exec", "destination": "xai_grok_build_subscription", "account_class": "subscription", "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "identity_evidence": "requested_only", "nonvisual_max_turns": 1, "armed": True, "zero_charge": True, "health": "healthy", "grok_cli_version": evidence.get("grok_cli_version"), "subscription_receipt_hash": evidence.get("subscription_receipt_hash")}
    if any(route.get(key) != value for key, value in required_route.items()) or route.get("allowed_payload_classes") != ["public_repo", "public_synthetic"] or not isinstance(route.get("grok_command"), list) or not isinstance(route.get("grok_command_identity"), dict) or not isinstance(route.get("cli_version_identity"), dict):
        raise ValueError("reconcile v3 prepared route policy drifted")
    if set(evidence) != {"cli_version_identity_sha256", "cost_evidence_hash", "grok_cli_version", "grok_command_identity_sha256", "registry_sha256", "route_name", "route_sha256", "subscription_receipt_hash"} or evidence["route_name"] != route["name"] or evidence["grok_cli_version"] != route["grok_cli_version"] or evidence["subscription_receipt_hash"] != route["subscription_receipt_hash"] or evidence["grok_command_identity_sha256"] != sha256(project_canonical(route["grok_command_identity"])) or evidence["cli_version_identity_sha256"] != sha256(project_canonical(route["cli_version_identity"])) or any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for key, value in evidence.items() if key not in {"grok_cli_version", "route_name"}):
        raise ValueError("reconcile v3 route evidence drifted")
    proof = _object(raw["zero-charge-route-proof.json"], label="route proof", canonical=project_canonical(_strict_json(raw["zero-charge-route-proof.json"], label="route proof")))
    if proof != {"format_version": 3, "study_id": SOURCE_STUDY_ID, "kind": "current_zero_charge_route_proof", "sample_id": sample, "route_evidence": evidence, "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}:
        raise ValueError("reconcile v3 route proof drifted")
    intent = _object(raw["launch-intent.json"], label="launch intent", canonical=project_canonical(_strict_json(raw["launch-intent.json"], label="launch intent")))
    expected_intent = {"format_version": 3, "study_id": SOURCE_STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": sha256(raw["prepared.json"]), "prompt_sha256": sha256(raw["prompt-request.bin"]), "route_evidence": prepared.get("route_evidence"), "native_contact_proven": False}
    if intent != expected_intent:
        raise ValueError("reconcile v3 launch intent binding drifted")
    return prepared, raw["prompt-request.bin"], route, evidence


def _terminal(raw: dict[str, bytes], sample: str) -> dict[str, Any]:
    result = _object(raw["result.json"], label="terminal result", canonical=project_canonical(_strict_json(raw["result.json"], label="terminal result")))
    detail = "subprocess deadline expired after contact" if sample.endswith("-sample-06") else "ValueError"
    expected = {"format_version": 3, "study_id": SOURCE_STUDY_ID, "kind": "reconcile_required_after_process_launch", "sample_id": sample, "adapter_stdout_sha256": sha256(raw["adapter-stdout.bin"]) if raw["adapter-stdout.bin"] else None, "detail": detail, "provider_calls_made": None, "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unknown"}
    if result != expected:
        raise ValueError("reconcile v3 source is not the exact recoverable terminal state")
    return result


def _runtime(value: Any, route: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"adapter_version", "cli_version", "command_identity", "command_identity_hash", "envelope_hash", "execution_policy", "identity_evidence", "nonvisual_max_turns", "observed_turns", "reasoning_attestation", "reasoning_attested", "reported_model", "request_id_hash", "requested_model", "requested_reasoning_effort", "session_id_hash", "subscription_receipt_hash", "usage_telemetry"}:
        raise ValueError("reconcile v3 runtime shape drifted")
    hashes = ("command_identity_hash", "envelope_hash", "request_id_hash", "session_id_hash", "subscription_receipt_hash")
    if any(not isinstance(value[name], str) or not re.fullmatch(r"[0-9a-f]{64}", value[name]) for name in hashes) or value["request_id_hash"] == value["session_id_hash"]:
        raise ValueError("reconcile v3 runtime identity is invalid")
    expected_identity = sha256(adapter_canonical({"adapter_version": 1, "grok_command": route["grok_command"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"]}))
    telemetry = value["usage_telemetry"]
    if value["adapter_version"] != 1 or value["requested_model"] != route["model"] or value["reported_model"] != route["reported_model"] or value["requested_reasoning_effort"] != route["reasoning_effort"] or value["execution_policy"] != "bounded_nonvisual_read_only" or value["nonvisual_max_turns"] != route["nonvisual_max_turns"] or value["observed_turns"] != 1 or value["reasoning_attested"] is not False or value["reasoning_attestation"] != "not_reported_by_grok_build_cli" or value["identity_evidence"] != route["identity_evidence"] or value["cli_version"] != route["grok_cli_version"] or value["subscription_receipt_hash"] != evidence["subscription_receipt_hash"] or value["command_identity"] != route["grok_command_identity"] or value["command_identity_hash"] != expected_identity or not isinstance(telemetry, dict):
        raise ValueError("reconcile v3 runtime policy drifted")
    if set(telemetry) != {"model_cost_usd", "status", "total_cost_usd", "total_cost_usd_ticks"} or telemetry["status"] != "reported" or any(not isinstance(telemetry[name], (int, float)) or isinstance(telemetry[name], bool) or not math.isfinite(telemetry[name]) or telemetry[name] < 0 for name in ("model_cost_usd", "total_cost_usd")) or not isinstance(telemetry["total_cost_usd_ticks"], int) or telemetry["total_cost_usd_ticks"] < 0:
        raise ValueError("reconcile v3 usage telemetry drifted")
    return value


def _control(raw: bytes, prompt: bytes, route: dict[str, Any], evidence: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not raw.endswith(b"\r\n") or raw.endswith(b"\r\n\r\n"):
        raise ValueError("reconcile v3 adapter transport framing is invalid")
    control = _object(raw[:-2], label="adapter stdout")
    if set(control) != {"control", "result"} or control["control"] != {"state": "completed", "version": 1} or not isinstance(control["result"], dict):
        raise ValueError("reconcile v3 adapter control is not completed")
    result = control["result"]
    if set(result) != {"output", "output_hash", "request_hash", "runtime", "schema_version"} or result.get("schema_version") != 1 or not isinstance(result.get("output"), dict):
        raise ValueError("reconcile v3 adapter result shape drifted")
    expected_request = sha256(adapter_canonical({"prompt": prompt.decode("utf-8")}))
    output = result["output"]
    if result.get("request_hash") != expected_request or result.get("output_hash") != sha256(adapter_canonical(output)):
        raise ValueError("reconcile v3 adapter-domain request/output commitment drifted")
    return control, output, _runtime(result["runtime"], route, evidence)


def _profile(raw: bytes, instruction: bytes) -> tuple[bytes, dict[str, Any]]:
    try:
        instruction.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("reconcile v3 instruction is not UTF-8") from error
    if not instruction or b"\x00" in instruction:
        raise ValueError("reconcile v3 instruction is unsafe")
    profile = _strict_json(raw, label="raw descendant profile")
    if not isinstance(profile, dict):
        raise ValueError("reconcile v3 raw descendant profile is not an object")
    if not PROFILE_REQUIRED_KEYS <= set(profile) <= PROFILE_ALLOWED_KEYS or not isinstance(profile.get("instruction_sha256"), str) or not isinstance(profile["dimension_weights"], dict) or not isinstance(profile["factors"], dict) or not isinstance(profile["immutable_cwr_commitments"], dict) or not isinstance(profile["same_bytes_for_models"], list) or not isinstance(profile["sampler"], dict):
        raise ValueError("reconcile v3 descendant profile semantics drifted")
    if profile["format_version"] not in {1, 2} or profile["demonstrations"] != 0 or not isinstance(profile["fixed_mapping"], str) or not isinstance(profile["study_id"], str) or any(not isinstance(profile[key], str) for key in {"parent_candidate_id", "version", "wave_id", "descendant_version", "feedback_kind"} & set(profile)) or ("lineage" in profile and not isinstance(profile["lineage"], dict)):
        raise ValueError("reconcile v3 descendant profile semantics drifted")
    if any(not isinstance(name, str) or not isinstance(weight, (int, float)) or isinstance(weight, bool) or not math.isfinite(weight) for name, weight in profile["dimension_weights"].items()) or any(not isinstance(name, str) or not isinstance(factor, str) for name, factor in profile["factors"].items()):
        raise ValueError("reconcile v3 descendant profile value is invalid")
    repaired = dict(profile); repaired["instruction_sha256"] = sha256(instruction)
    return project_canonical(repaired), profile


def _row(cell: Path, sample: str) -> dict[str, Any]:
    raw = _inventory(cell)
    prepared, prompt, route, evidence = _prepared(raw, sample)
    terminal = _terminal(raw, sample)
    control, output, runtime = _control(raw["adapter-stdout.bin"], prompt, route, evidence)
    if set(output) != {"descendant_instruction_base64", "descendant_profile_base64"}:
        raise ValueError("reconcile v3 adapter output shape drifted")
    instruction = _b64(output["descendant_instruction_base64"], label="instruction")
    profile_raw = _b64(output["descendant_profile_base64"], label="profile")
    canonical_profile, raw_profile = _profile(profile_raw, instruction)
    canonical_output = {"descendant_instruction_base64": base64.b64encode(instruction).decode("ascii"), "descendant_profile_base64": base64.b64encode(canonical_profile).decode("ascii")}
    raw_output = adapter_canonical(output)
    row = {"sample_id": sample, "source_root": str(cell), "source_inventory_sha256": _inventory_digest(raw), "source_terminal": terminal, "source_adapter_stdout_sha256": sha256(raw["adapter-stdout.bin"]), "source_control": control, "raw_output": output, "raw_output_sha256": sha256(raw_output), "raw_instruction_base64": output["descendant_instruction_base64"], "raw_instruction_sha256": sha256(instruction), "raw_profile_base64": output["descendant_profile_base64"], "raw_profile_sha256": sha256(profile_raw), "canonical_descendant": canonical_output, "canonical_descendant_sha256": sha256(project_canonical(canonical_output)), "canonical_profile_sha256": sha256(canonical_profile), "repair": {"kind": "project_canonical_profile_instruction_sha256", "raw_profile_instruction_sha256": raw_profile["instruction_sha256"], "canonical_profile_instruction_sha256": sha256(instruction), "raw_profile_final_newline": profile_raw.endswith(b"\n"), "canonical_profile_final_newline": True, "source_result_relabelled": False}, "runtime": runtime, "source_native_contact_status": "completed_adapter_control_replayed_while_source_terminal_remains_reconcile_required", "reconciliation_provider_calls_made": 0, "reconciliation_process_launches": 0}
    return row


def _excluded(cell: Path, sample: str) -> dict[str, Any]:
    raw = _inventory(cell); _prepared(raw, sample); terminal = _terminal(raw, sample)
    if raw["adapter-stdout.bin"]:
        raise ValueError("reconcile v3 exclusion must be the exact empty-control terminal")
    return {"sample_id": sample, "source_root": str(cell), "source_inventory_sha256": _inventory_digest(raw), "source_terminal": terminal, "exclusion": "no_adapter_control_bytes_no_resend_fresh_v4_replacement_required", "reconciliation_provider_calls_made": 0, "reconciliation_process_launches": 0}


def _roots(source: Path) -> list[tuple[str, Path]]:
    _ancestry(source)
    if not _plain(source, directory=True):
        raise ValueError("reconcile v3 source root is unsafe")
    cells = {item.name: item for item in source.iterdir() if item.is_dir() and "-sample-" in item.name}
    expected = {f"{SAMPLE_PREFIX}-sample-{number:02d}" for number in range(1, 11)}
    if set(cells) != expected:
        raise ValueError("reconcile v3 requires exactly ten completed recoverable roots")
    unknown = {item.name for item in source.iterdir()} - expected
    if unknown:
        raise ValueError("reconcile v3 source root has an unexpected artifact")
    return [(name, cells[name]) for name in sorted(cells)]


def reconcile_partial(*, source_root: Path, manifest_path: Path) -> dict[str, Any]:
    _contract(); source = Path(source_root); target = Path(manifest_path); _ancestry(source)
    if Path(os.path.abspath(target)) == Path(os.path.abspath(source)) or Path(os.path.abspath(source)) in Path(os.path.abspath(target)).parents:
        raise ValueError("reconcile v3 manifest target must stay outside source root")
    before: dict[str, str] = {}; rows: list[dict[str, Any]] = []; excluded: dict[str, Any] | None = None
    contacts: set[str] = set(); raw_outputs: set[str] = set(); descendants: set[str] = set(); instructions: set[str] = set(); profiles: set[str] = set()
    for sample, cell in _roots(source):
        if sample.endswith("-sample-06"):
            excluded = _excluded(cell, sample); before[str(cell)] = excluded["source_inventory_sha256"]
            continue
        row = _row(cell, sample); rows.append(row); before[str(cell)] = row["source_inventory_sha256"]
        runtime = row["runtime"]; request, session = runtime["request_id_hash"], runtime["session_id_hash"]
        if request in contacts or session in contacts or request == session or row["raw_output_sha256"] in raw_outputs or row["canonical_descendant_sha256"] in descendants or row["raw_instruction_sha256"] in instructions or row["canonical_profile_sha256"] in profiles:
            raise ValueError("reconcile v3 cross-root identity or descendant is duplicated")
        contacts.update({request, session}); raw_outputs.add(row["raw_output_sha256"]); descendants.add(row["canonical_descendant_sha256"]); instructions.add(row["raw_instruction_sha256"]); profiles.add(row["canonical_profile_sha256"])
    if len(rows) != 9 or len(contacts) != 18 or excluded is None:
        raise ValueError("reconcile v3 partial aggregate cardinality drifted")
    for sample, cell in _roots(source):
        replay = _excluded(cell, sample) if sample.endswith("-sample-06") else _row(cell, sample)
        if replay["source_inventory_sha256"] != before[str(cell)]:
            raise ValueError("reconcile v3 source changed during reconciliation")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "balanced_dspy_grok_v3_reconciled_partial_nine_descendants", "source": {"study_id": SOURCE_STUDY_ID, "executor_sha256": SOURCE_EXECUTOR_SHA256, "contract_sha256": SOURCE_CONTRACT_SHA256, "feedback_sha256": SOURCE_FEEDBACK_SHA256, "terminal_roots": 10, "source_process_launches": 10, "completed_adapter_controls": 9, "unrecoverable_terminal_roots": 1}, "samples": rows, "excluded_terminal": excluded, "completion": {"status": "partial", "completed_aggregate_freeze": False, "missing_replacement": "fresh_v4_sample_06_descendant_required"}, "authority": {"confirmation": {"status": "unopened", "cells": 0}, "local_only": True, "evaluation": False, "selection": False, "promotion": False, "runtime": False}, "reconciliation_provider_calls_made": 0, "reconciliation_process_launches": 0}
    manifest["manifest_sha256"] = sha256(project_canonical(manifest))
    _ancestry(target.parent)
    target.parent.mkdir(parents=True, exist_ok=True)
    _ancestry(target.parent)
    if not _plain(target.parent, directory=True):
        raise ValueError("reconcile v3 manifest parent is unsafe")
    try:
        with target.open("xb") as handle:
            handle.write(project_canonical(manifest)); handle.flush(); os.fsync(handle.fileno())
    except FileExistsError as error:
        raise ValueError("reconcile v3 refuses to overwrite a manifest") from error
    return manifest


def reconcile_all(*, source_root: Path, manifest_path: Path) -> dict[str, Any]:
    """Compatibility spelling for the only supported partial reconciliation."""
    return reconcile_partial(source_root=source_root, manifest_path=manifest_path)
