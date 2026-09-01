"""Governed native executor for the immutable V3 heldout revision study.

This successor freezes current CWR questions and all outbound bytes before a
one-shot native contact.  It never accepts routes, feedback, or blind targets
from a caller: each is derived from the frozen manifest or prior receipts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "cwr-guided-revision-gain-v6-governed-heldout-exec-v1"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
V3_ROOT = REPO / "evaluation-results" / "cwr-guided-revision-gain-v3-heldout-confirmation-v1"
V3_CONTRACT = V3_ROOT / "study-contract.json"
V3_SHA = "0a8f8543e6cceecc9351ef191708874e7cdb51ae4e90b138e258dd9ac5de28fe"
V3_STUDY_SHA = "5fda85242f5b509d91ec79a5bf302b431833cd82558b68fe2dea24c350fe5c76"
_PREPARED = frozenset({"payload.json", "outbound-payload.json", "prepared-cell.json", "disclosure.json", "acknowledgement.json", "governed-route-proof.json", "adapter-schema-binding.json", "admission.json"})
_PROOF_KEYS = frozenset({"format_version", "study_id", "kind", "queue_root", "route_name", "registry_sha256", "route_semantic_sha256", "model", "adapter", "provider", "destination", "reasoning", "tools_enabled", "zero_charge", "account_class", "cost_evidence_sha256", "route_receipt_sha256", "expected_adapter_runtime_identity_sha256", "runtime_binding"})


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value): raise ValueError("V6 digest is not exact SHA-256 hex")
    return value


def stable_read(path: Path, *, label: str = "artifact") -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try: info = os.lstat(current)
        except FileNotFoundError as error: raise ValueError(f"V6 {label} is missing") from error
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400): raise ValueError(f"V6 {label} is reparsed")
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode): raise ValueError(f"V6 {label} is not a plain file")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_size, opened.st_size, after.st_size) != (len(raw), len(raw), len(raw)): raise ValueError(f"V6 {label} changed during read")
    return raw


def write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle: handle.write(canonical(value) + b"\n")


def write_bytes_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle: handle.write(raw)


def bind(root: Path, path: Path) -> dict[str, Any]:
    raw = stable_read(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": sha(raw)}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None: raise ValueError("V6 pinned module is unavailable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def v3():
    if sha(stable_read(V3_CONTRACT, label="V3 contract")) != V3_SHA: raise ValueError("V6 V3 contract drifted")
    if sha(stable_read(V3_ROOT / "study.py", label="V3 study")) != V3_STUDY_SHA: raise ValueError("V6 V3 study drifted")
    return _load(V3_ROOT / "study.py", "revision_v6_v3")


def schedule() -> list[dict[str, Any]]:
    study = v3(); contract = study.contract()
    feedback = [{"phase": "cwr_feedback", "event_id": f"feedback-v3-c1-{item}-sol", "route": contract["routes"]["cwr_feedback"]} for item in study._ITEMS]
    revisions = [{"phase": "revision_generation", "event_id": row["event_id"], "route": contract["routes"]["generator"], "revision": row} for row in study.revision_schedule()]
    endpoints = [{"phase": "blind_endpoint_judgment", "event_id": row["endpoint_event_id"], "route": contract["routes"]["judges"][row["judge_route_id"]], "endpoint": row} for row in study.endpoint_schedule()]
    rows = feedback + revisions + endpoints
    if len(rows) != 60 or len({row["event_id"] for row in rows}) != 60: raise ValueError("V6 immutable V3 geometry drifted")
    return rows


def event(event_id: str) -> dict[str, Any]:
    row = next((row for row in schedule() if row["event_id"] == event_id), None)
    if row is None: raise ValueError("V6 event is unscheduled")
    return row


def _current_questions() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source = str(REPO / "src")
    if source not in sys.path: sys.path.insert(0, source)
    from hbqrs.core import (
        compile_bundle,
        compiled_questions,
        load_bundles,
        load_modules,
        resolve_bundle,
    )
    from hbqrs.runner import _question_payload
    runtime_contract = json.loads(stable_read(REPO / "evaluation-results" / "cwr-guided-revision-gain-v1" / "study-contract.json", label="V1 runtime contract"))
    modules = REPO / "registry" / "all_modules.json"; bundles = REPO / "bundles" / "all_bundles.json"
    bundle = resolve_bundle(load_bundles(bundles), runtime_contract["cwr_runtime"]["bundle_id"])
    payload = _question_payload(compiled_questions(compile_bundle(load_modules(modules), bundle)))
    manifest = {"format_version": 1, "kind": "current_cwr_question_manifest", "python_executable": sys.executable, "executor_sha256": sha(stable_read(HERE / "executor.py", label="V6 executor")), "registry": {"path": "registry/all_modules.json", "sha256": sha(stable_read(modules))}, "bundles": {"path": "bundles/all_bundles.json", "sha256": sha(stable_read(bundles))}, "question_payload_sha256": sha(canonical(payload)), "question_count": len(payload)}
    return payload, manifest


def freeze_run(*, run_root: Path, source_root: Path) -> dict[str, Any]:
    """Create one immutable run boundary before any route is consulted."""
    root = Path(run_root)
    if root.exists(): raise ValueError("V6 run root must be fresh")
    root.mkdir(parents=True)
    frozen = v3().freeze_inputs(source_root=Path(source_root))
    questions, manifest = _current_questions()
    write_once(root / "frozen-inputs.json", frozen)
    write_once(root / "current-cwr-question-manifest.json", manifest)
    write_bytes_once(root / "current-cwr-question-payload.json", canonical(questions))
    return {"study_id": STUDY_ID, "provider_calls_made": 0, "process_launches": 0, "frozen_inputs": bind(root, root / "frozen-inputs.json"), "question_manifest": bind(root, root / "current-cwr-question-manifest.json")}


def _frozen_sources(run_root: Path) -> dict[str, tuple[str, str]]:
    root = Path(run_root); raw = stable_read(root / "frozen-inputs.json", label="frozen inputs")
    frozen = json.loads(raw)
    if canonical(frozen) + b"\n" != raw: raise ValueError("V6 frozen inputs are noncanonical")
    return {item: v3()._read_frozen_source(frozen, item) for item in v3()._ITEMS}


def _runtime_questions(run_root: Path) -> list[dict[str, Any]]:
    root = Path(run_root); manifest_raw = stable_read(root / "current-cwr-question-manifest.json", label="question manifest"); payload_raw = stable_read(root / "current-cwr-question-payload.json", label="question payload")
    manifest, payload = json.loads(manifest_raw), json.loads(payload_raw)
    current_payload, current_manifest = _current_questions()
    if canonical(manifest) + b"\n" != manifest_raw or manifest != current_manifest or canonical(payload) != payload_raw or payload != current_payload: raise ValueError("V6 current CWR runtime drifted; prepare a fresh run")
    return payload


def _broker():
    tools = r"C:\Users\Haile\.codex\tools"
    if tools not in sys.path: sys.path.insert(0, tools)
    from model_work_queue.broker import Broker  # type: ignore[import-not-found]
    return Broker(Path(r"C:\Users\Haile\.codex\state\model-work-queue"))


def _governed_route(row: Mapping[str, Any]) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Resolve live authority from the canonical queue; no caller-supplied route exists."""
    expected = dict(row["route"]); broker = _broker(); registry = broker._load_registry_live()
    choices = [route for route in registry["routes"] if route.get("model") == expected["model"]]
    if len(choices) != 1: raise ValueError("V6 current governed route is missing or ambiguous")
    route = choices[0]; broker._validate_route(route, verify_command_identity=True, validate_current_evidence=True)
    expected_adapter = "grok_exec" if expected["model"] == "grok-4.6" else "codex_exec"
    provider = "xai_grok_build" if expected_adapter == "grok_exec" else "openai_codex"
    destination = "xai_grok_build_subscription" if expected_adapter == "grok_exec" else "openai_codex_chatgpt_subscription"
    required = {"adapter": expected_adapter, "provider": provider, "destination": destination, "model": expected["model"], "reasoning_effort": expected["reasoning"], "zero_charge": True, "armed": True, "health": "healthy", "account_class": "subscription", "identity_evidence": "requested_only"}
    if any(route.get(key) != value for key, value in required.items()) or "public_repo" not in route.get("allowed_payload_classes", []): raise ValueError("V6 route does not satisfy the frozen disclosure contract")
    registry_raw = stable_read(broker.routes_path, label="governed route registry")
    if json.loads(registry_raw) != registry: raise ValueError("V6 governed route registry changed during validation")
    cost = broker._load_artifact_bytes(route["cost_evidence"]["evidence_hash"])
    receipt_key = "subscription_receipt_hash" if expected_adapter == "grok_exec" else "auth_receipt_hash"
    receipt = broker._load_artifact_bytes(route[receipt_key])
    runtime = ({"adapter_version": 1, "grok_command": route["grok_command"], "command_identity": route["grok_command_identity"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"], "nonvisual_max_turns": route["nonvisual_max_turns"]} if expected_adapter == "grok_exec" else {"adapter_version": 1, "codex_command": route["codex_command"], "command_identity": route["codex_command_identity"], "model": route["model"], "reasoning_effort": route["reasoning_effort"]})
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "governed_model_work_queue_route_proof", "queue_root": str(broker.root), "route_name": route["name"], "registry_sha256": sha(registry_raw), "route_semantic_sha256": broker._route_semantic_identity_hash(route), "model": route["model"], "adapter": route["adapter"], "provider": route["provider"], "destination": route["destination"], "reasoning": route["reasoning_effort"], "tools_enabled": False, "zero_charge": True, "account_class": "subscription", "cost_evidence_sha256": sha(cost), "route_receipt_sha256": sha(receipt), "expected_adapter_runtime_identity_sha256": sha(canonical(runtime)), "runtime_binding": runtime}
    return broker, dict(route), proof


def _root(run_root: Path, row: Mapping[str, Any]) -> Path:
    return Path(run_root) / "cells" / str(row["phase"]) / str(row["event_id"])


def _payload_for(*, run_root: Path, row: Mapping[str, Any]) -> dict[str, Any]:
    study = v3(); sources = _frozen_sources(run_root); phase = row["phase"]
    if phase == "cwr_feedback":
        item = row["event_id"].removeprefix("feedback-v3-c1-").removesuffix("-sol")
        text, prompt = sources[item]
        return {"source_text": text, "source_prompt": prompt, "question_payload": _runtime_questions(run_root), "feedback_prompt": study._asset("cwr_feedback", study.contract()), "response_schema": json.loads(study._asset("cwr_feedback_schema", study.contract()))}
    if phase == "revision_generation":
        revision = row["revision"]; text, prompt = sources[revision["source_item_id"]]
        for item in study._ITEMS:
            replay_receipt(root=_root(run_root, event(f"feedback-v3-c1-{item}-sol")))
        findings = None
        if revision["guidance_arm"] == "cwr_guided":
            feedback_root = _root(run_root, event(revision["feedback_event_id"]))
            findings = replay_receipt(root=feedback_root)["response"]["findings"]
        return json.loads(study.revision_payload(source_text=text, source_prompt=prompt, guidance_arm=revision["guidance_arm"], cwr_feedback=findings).decode())
    targets = finalize_targets_from_receipts(run_root=run_root); endpoint = row["endpoint"]
    text, target_sha = targets[endpoint["blind_target_id"]]
    return json.loads(study.endpoint_payload(blind_target_id=endpoint["blind_target_id"], target_text=text, target_sha256=target_sha, measure_id=endpoint["measure_id"]).decode())


def _schema(row: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    if row["phase"] == "revision_generation": underlying = {"type": "object", "additionalProperties": False, "properties": {"story": {"type": "string"}}, "required": ["story"]}
    else: underlying = payload["response_schema"]
    if not isinstance(underlying, Mapping): raise TypeError("V6 response schema is invalid")
    return {"$schema_version": 1, **dict(underlying)}


def _validate_plain_inventory(root: Path, names: frozenset[str]) -> None:
    info = os.lstat(root)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400): raise ValueError("V6 cell root is unsafe")
    actual = frozenset(path.name for path in root.iterdir())
    if actual != names: raise ValueError("V6 cell inventory drifted")
    for name in actual: stable_read(root / name, label="cell inventory artifact")


def prepare_one(*, run_root: Path, event_id: str, acknowledgement_sha256: str = ACK) -> dict[str, Any]:
    """Provider-free prepare of one legal, receipt-derived stage cell."""
    if acknowledgement_sha256 != ACK: raise ValueError("V6 acknowledgement is not the authorized exact hash")
    row = event(event_id); root = _root(run_root, row)
    if root.exists(): raise ValueError("V6 preparation requires a fresh cell root")
    payload = _payload_for(run_root=Path(run_root), row=row)
    broker, route, proof = _governed_route(row)
    del broker
    expected_adapter = "grok_exec" if row["route"]["model"] == "grok-4.6" else "codex_exec"
    if route.get("model") != row["route"]["model"] or route.get("reasoning_effort") != row["route"]["reasoning"] or route.get("adapter") != expected_adapter:
        raise ValueError("V6 governed route cannot substitute the frozen provider/model identity")
    write_once(root / "payload.json", payload)
    write_bytes_once(root / "outbound-payload.json", canonical(payload))
    outbound = stable_read(root / "outbound-payload.json")
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "event_id": event_id, "destination": row["route"]["destination"], "provider": proof["provider"], "model": row["route"]["model"], "reasoning": row["route"]["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": sha(outbound), "transmitted_payload_bytes": len(outbound)}
    write_once(root / "disclosure.json", disclosure)
    write_once(root / "acknowledgement.json", {"format_version": 1, "study_id": STUDY_ID, "disclosure_sha256": sha(stable_read(root / "disclosure.json")), "acknowledgement_sha256": ACK})
    write_once(root / "governed-route-proof.json", proof)
    schema = _schema(row, payload)
    write_once(root / "adapter-schema-binding.json", {"format_version": 1, "study_id": STUDY_ID, "schema": schema, "schema_sha256": sha(canonical(schema))})
    prepared = {"format_version": 1, "study_id": STUDY_ID, "event_id": event_id, "phase": row["phase"], "route": row["route"], "payload": bind(root, root / "payload.json"), "outbound": bind(root, root / "outbound-payload.json"), "provider_calls_made": 0, "process_launches": 0, "no_fallback": True, "no_resend": True}
    write_once(root / "prepared-cell.json", prepared)
    write_once(root / "admission.json", {"format_version": 1, "study_id": STUDY_ID, "prepared_sha256": sha(stable_read(root / "prepared-cell.json")), "route_proof_sha256": sha(stable_read(root / "governed-route-proof.json")), "provider_calls_made": 0, "process_launches": 0, "no_resend": True})
    _validate_plain_inventory(root, _PREPARED)
    return prepared


def _read_prepared(root: Path) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    if not (root / "prepared-cell.json").is_file(): raise ValueError("V6 prepared cell is missing")
    prepared = json.loads(stable_read(root / "prepared-cell.json")); row = event(prepared.get("event_id", ""))
    settled = _PREPARED | {"launch-intent.json", "adapter-stdout.raw", "adapter-stderr.raw", "adapter-control.json", "response.json", "native-receipt.json", "verified-receipt.json", "execution-result.json"}
    if row["phase"] == "revision_generation": settled = settled | {"descendant.md"}
    names = frozenset(path.name for path in root.iterdir())
    terminal = _PREPARED | {"launch-intent.json", "adapter-stdout.raw", "adapter-stderr.raw", "terminal-outcome.json"}
    reconciled = settled | {"terminal-outcome.json", "reconciliation.json"}
    if names not in {_PREPARED, settled, terminal, reconciled}: raise ValueError("V6 cell inventory drifted")
    _validate_plain_inventory(root, names)
    payload = stable_read(root / "outbound-payload.json")
    proof_raw = stable_read(root / "governed-route-proof.json"); proof = json.loads(proof_raw)
    expected_adapter = "grok_exec" if row["route"]["model"] == "grok-4.6" else "codex_exec"
    physical_destination = "xai_grok_build_subscription" if expected_adapter == "grok_exec" else "openai_codex_chatgpt_subscription"
    proof_identity = {"format_version": 1, "study_id": STUDY_ID, "kind": "governed_model_work_queue_route_proof", "model": row["route"]["model"], "adapter": expected_adapter, "destination": physical_destination, "reasoning": row["route"]["reasoning"], "tools_enabled": False, "zero_charge": True, "account_class": "subscription"}
    if set(proof) != _PROOF_KEYS or any(proof.get(key) != value for key, value in proof_identity.items()) or not isinstance(proof.get("provider"), str) or not proof["provider"]:
        raise ValueError("V6 governed route proof identity drifted")
    disclosure_raw = stable_read(root / "disclosure.json"); disclosure = json.loads(disclosure_raw); acknowledgement = json.loads(stable_read(root / "acknowledgement.json"))
    expected_disclosure = {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "destination": row["route"]["destination"], "provider": proof["provider"], "model": row["route"]["model"], "reasoning": row["route"]["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": sha(payload), "transmitted_payload_bytes": len(payload)}
    expected_prepared = {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "phase": row["phase"], "route": row["route"], "payload": bind(root, root / "payload.json"), "outbound": bind(root, root / "outbound-payload.json"), "provider_calls_made": 0, "process_launches": 0, "no_fallback": True, "no_resend": True}
    if prepared != expected_prepared or canonical(prepared) + b"\n" != stable_read(root / "prepared-cell.json") or stable_read(root / "payload.json") != canonical(json.loads(stable_read(root / "payload.json"))) + b"\n" or payload != canonical(json.loads(stable_read(root / "payload.json"))): raise ValueError("V6 immutable prepared binding drifted")
    if disclosure != expected_disclosure or canonical(disclosure) + b"\n" != disclosure_raw or acknowledgement != {"format_version": 1, "study_id": STUDY_ID, "disclosure_sha256": sha(disclosure_raw), "acknowledgement_sha256": ACK}: raise ValueError("V6 disclosure or acknowledgement drifted")
    admission_raw = stable_read(root / "admission.json"); admission = json.loads(admission_raw)
    expected_admission = {"format_version": 1, "study_id": STUDY_ID, "prepared_sha256": sha(stable_read(root / "prepared-cell.json")), "route_proof_sha256": sha(proof_raw), "provider_calls_made": 0, "process_launches": 0, "no_resend": True}
    if admission != expected_admission or canonical(admission) + b"\n" != admission_raw: raise ValueError("V6 provider-free admission drifted")
    return prepared, row, payload


def _build_invocation(broker: Any, root: Path, route: Mapping[str, Any]) -> tuple[list[str], bytes, int]:
    binding = json.loads(stable_read(root / "adapter-schema-binding.json")); schema = binding.get("schema"); raw = stable_read(root / "outbound-payload.json")
    prepared = json.loads(stable_read(root / "prepared-cell.json")); row = event(prepared.get("event_id", "")); expected_schema = _schema(row, json.loads(raw))
    if binding != {"format_version": 1, "study_id": STUDY_ID, "schema": expected_schema, "schema_sha256": sha(canonical(expected_schema))}: raise ValueError("V6 adapter schema binding drifted")
    schema = expected_schema
    if route["adapter"] == "grok_exec": args = ["--grok-command-json", canonical(route["grok_command"]).decode(), "--model", route["model"], "--reported-model", route["reported_model"], "--reasoning-effort", route["reasoning_effort"], "--output-schema-json", canonical(schema).decode(), "--expected-command-identity-json", canonical(route["grok_command_identity"]).decode(), "--cli-version-command-json", canonical(route["cli_version_command"]).decode(), "--expected-cli-version-identity-json", canonical(route["cli_version_identity"]).decode(), "--expected-cli-version", route["grok_cli_version"], "--subscription-receipt-json", canonical(broker._load_json_artifact(route["subscription_receipt_hash"])).decode(), "--broker-root", str(broker.root), "--timeout-seconds", str(route["timeout_seconds"]), "--nonvisual-max-turns", str(route["nonvisual_max_turns"])]
    elif route["adapter"] == "codex_exec": args = ["--codex-command-json", canonical(route["codex_command"]).decode(), "--model", route["model"], "--reasoning-effort", route["reasoning_effort"], "--output-schema-json", canonical(schema).decode(), "--expected-command-identity-json", canonical(route["codex_command_identity"]).decode(), "--cli-version-command-json", canonical(route["cli_version_command"]).decode(), "--expected-cli-version-identity-json", canonical(route["cli_version_identity"]).decode(), "--expected-cli-version", route["codex_cli_version"], "--auth-status-command-json", canonical(route["auth_status_command"]).decode(), "--expected-auth-status-identity-json", canonical(route["auth_status_identity"]).decode(), "--auth-receipt-json", canonical(broker._load_json_artifact(route["auth_receipt_hash"])).decode(), "--broker-root", str(broker.root), "--timeout-seconds", str(route["timeout_seconds"])]
    else: raise ValueError("V6 route adapter is unsupported")
    return [*route["command"], *args], canonical({"prompt": raw.decode("utf-8")}), int(route["timeout_seconds"])


def _control(raw: bytes) -> tuple[str, Mapping[str, Any] | None]:
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith((b"\n", b"\r\n")): raise ValueError("V6 adapter stdout serialization is invalid")
    newline = b"\r\n" if raw.endswith(b"\r\n") else b"\n"; value = json.loads(raw[:-len(newline)].decode("ascii"))
    if json.dumps(value, sort_keys=True).encode("ascii") + newline != raw: raise ValueError("V6 adapter stdout is not canonical")
    control, result = value.get("control"), value.get("result")
    if not isinstance(control, Mapping) or control.get("version") != 1 or control.get("state") not in {"completed", "definitely_not_contacted", "ambiguous"}: raise ValueError("V6 adapter control state is invalid")
    return str(control["state"]), result if isinstance(result, Mapping) else None


def _validate_response(row: Mapping[str, Any], response: Mapping[str, Any]) -> str | None:
    if row["phase"] == "cwr_feedback":
        findings = response.get("findings")
        if set(response) != {"findings"} or not isinstance(findings, list) or not findings or any(not isinstance(item, Mapping) or set(item) != {"location", "observation", "repair_target"} or not all(isinstance(item[key], str) and item[key] for key in item) for item in findings): raise ValueError("V6 feedback response schema drifted")
        return None
    if row["phase"] == "revision_generation":
        story = response.get("story")
        if set(response) != {"story"} or not isinstance(story, str) or not story: raise ValueError("V6 revision response schema drifted")
        return story
    overall, rationale = response.get("overall"), response.get("rationale"); lower, upper = (1, 7) if row["endpoint"]["measure_id"] == "holistic" else (1, 5)
    if set(response) != {"overall", "rationale"} or not isinstance(overall, int) or isinstance(overall, bool) or not lower <= overall <= upper or not isinstance(rationale, str) or not rationale: raise ValueError("V6 endpoint response schema drifted")
    return None


def _validate_runtime(*, route: Mapping[str, Any], result: Mapping[str, Any], runtime: Mapping[str, Any]) -> None:
    if result.get("schema_version") != 1 or runtime.get("adapter_version") != 1 or runtime.get("requested_model") != route["model"] or runtime.get("requested_reasoning_effort") != route["reasoning_effort"] or runtime.get("identity_evidence") != "requested_only" or runtime.get("cli_version") != route["grok_cli_version" if route["adapter"] == "grok_exec" else "codex_cli_version"]:
        raise ValueError("V6 adapter runtime identity drifted")
    if route["adapter"] == "grok_exec":
        required = {"adapter_version", "requested_model", "reported_model", "requested_reasoning_effort", "reasoning_attested", "reasoning_attestation", "identity_evidence", "cli_version", "session_id_hash", "request_id_hash", "observed_turns", "envelope_hash", "command_identity", "command_identity_hash", "subscription_receipt_hash", "execution_policy", "usage_telemetry", "nonvisual_max_turns"}
        telemetry = runtime.get("usage_telemetry")
        if set(runtime) != required or runtime.get("reported_model") != route["reported_model"] or runtime.get("reasoning_attested") is not False or runtime.get("reasoning_attestation") != "not_reported_by_grok_build_cli" or runtime.get("execution_policy") != "bounded_nonvisual_read_only" or runtime.get("nonvisual_max_turns") != route.get("nonvisual_max_turns") or not isinstance(runtime.get("command_identity"), Mapping) or not isinstance(telemetry, Mapping) or telemetry.get("status") not in {"not_reported", "reported"} or not isinstance(runtime.get("session_id_hash"), str) or not isinstance(runtime.get("request_id_hash"), str) or runtime.get("session_id_hash") == runtime.get("request_id_hash") or runtime.get("observed_turns") != 1:
            raise ValueError("V6 Grok runtime shape drifted")
        expected_hash = sha(canonical({"adapter_version": 1, "grok_command": route["grok_command"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": route["reasoning_effort"]}))
        if runtime["command_identity"] != route["grok_command_identity"] or runtime["command_identity_hash"] != expected_hash:
            raise ValueError("V6 Grok command identity drifted")
    else:
        required = {"adapter_version", "requested_model", "requested_reasoning_effort", "identity_evidence", "cli_version", "events_hash", "event_projection", "raw_output_hash", "command_identity", "auth_receipt_hash", "command_identity_hash"}
        if set(runtime) != required or not isinstance(runtime.get("command_identity"), Mapping) or not isinstance(runtime.get("event_projection"), Mapping) or not isinstance(runtime.get("events_hash"), str) or not isinstance(runtime.get("auth_receipt_hash"), str):
            raise ValueError("V6 Sol runtime shape drifted")
        expected_hash = sha(canonical({"adapter_version": 1, "codex_command": route["codex_command"], "model": route["model"], "reasoning_effort": route["reasoning_effort"]}))
        if runtime["command_identity"] != route["codex_command_identity"] or runtime["command_identity_hash"] != expected_hash:
            raise ValueError("V6 Sol command identity drifted")


def _terminal(root: Path, *, state: str, launches: int, contacts: object, error: Exception | None = None) -> dict[str, Any]:
    write_once(root / "terminal-outcome.json", {"format_version": 1, "study_id": STUDY_ID, "state": state, "process_launches": launches, "provider_calls_made": contacts, "no_resend": True, **({"error_type": type(error).__name__} if error else {})})
    return {"state": state, "process_launches": launches, "provider_calls_made": contacts, "no_resend": True, **({"error_type": type(error).__name__} if error else {})}


def dispatch_one(*, root: Path) -> dict[str, Any]:
    """One governed native launch.  Terminal/reconcile roots are deliberately idle."""
    root = Path(root)
    if (root / "execution-result.json").exists() or (root / "terminal-outcome.json").exists(): return {"state": "idle_terminal", "provider_calls_made": 0, "process_launches": 0, "no_resend": True}
    try:
        _prepared, row, payload = _read_prepared(root)
        broker, route, proof = _governed_route(row)
        persisted = json.loads(stable_read(root / "governed-route-proof.json"))
        if {key: persisted[key] for key in persisted} != {key: proof[key] for key in persisted}: raise ValueError("V6 live governed route changed after preparation")
        argv, stdin, timeout = _build_invocation(broker, root, route)
    except Exception as error: return _terminal(root, state="terminal_precontact", launches=0, contacts=0, error=error)  # noqa: BLE001
    write_once(root / "launch-intent.json", {"format_version": 1, "study_id": STUDY_ID, "process_launches": 1, "no_resend": True})
    try: completed = subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout, check=False)
    except Exception as error: return _terminal(root, state="terminal_postlaunch_reconcile_required", launches=1, contacts="unproven", error=error)  # noqa: BLE001
    write_bytes_once(root / "adapter-stdout.raw", completed.stdout); write_bytes_once(root / "adapter-stderr.raw", completed.stderr)
    if completed.returncode != 0: return _terminal(root, state="terminal_postlaunch_reconcile_required", launches=1, contacts="unproven")
    try:
        state, result = _control(completed.stdout)
        if state != "completed" or result is None: return _terminal(root, state="terminal_postlaunch_reconcile_required", launches=1, contacts=0 if state == "definitely_not_contacted" else "unproven")
        response, runtime = result.get("output"), result.get("runtime")
        if not isinstance(response, Mapping) or not isinstance(runtime, Mapping): raise TypeError("V6 native adapter output shape is invalid")
        if result.get("request_hash") != sha(canonical({"prompt": payload.decode()})) or result.get("output_hash") != sha(canonical(response)): raise ValueError("V6 native adapter payload binding drifted")
        _validate_runtime(route=route, result=result, runtime=runtime)
        receipt_field = "subscription_receipt_hash" if route["adapter"] == "grok_exec" else "auth_receipt_hash"
        if runtime[receipt_field] != proof["route_receipt_sha256"]: raise ValueError("V6 adapter receipt evidence drifted")
        story = _validate_response(row, response)
        route_identity = {"provider": route["provider"], "destination": route["destination"], "adapter": route["adapter"], "model": route["model"], "reasoning": route["reasoning_effort"], "tools_enabled": False}
        if route["model"] == "grok-4.6":
            request_id, session_id = runtime.get("request_id_hash"), runtime.get("session_id_hash")
            if not isinstance(request_id, str) or not isinstance(session_id, str) or request_id == session_id or runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != route["reported_model"] or runtime.get("requested_reasoning_effort") != "high" or runtime.get("observed_turns") != 1: raise ValueError("V6 Grok native identity drifted")
            native = {"provider_request_id": "grok-request-sha256:" + request_id, "provider_session_id": "grok-session-sha256:" + session_id, "native_endpoint_contact_cardinality": 1, "evidence_class": "grok_native_request_session_exact_one_contact_v1"}
        else:
            event_projection = runtime.get("event_projection"); thread = event_projection.get("thread_id") if isinstance(event_projection, Mapping) else None
            if not isinstance(thread, str) or not thread or runtime.get("requested_model") != "gpt-5.6-sol" or runtime.get("requested_reasoning_effort") != "high": raise ValueError("V6 Sol native lifecycle identity drifted")
            thread_hash = sha(thread.encode()); native = {"provider_request_id": "sol-thread-sha256:" + thread_hash, "provider_session_id": "sol-thread-sha256:" + thread_hash, "native_endpoint_contact_cardinality": "unproven", "evidence_class": "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1"}
        write_once(root / "adapter-control.json", json.loads(completed.stdout)); write_once(root / "response.json", dict(response))
        write_once(root / "native-receipt.json", {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "provider_model": route["model"], "reasoning": "high", "tools_enabled": False, "route_identity": route_identity, "transmitted_payload_sha256": sha(payload), "raw_adapter_stdout_sha256": sha(completed.stdout), "raw_adapter_stderr_sha256": sha(completed.stderr), **native})
        descendant = None
        if story is not None: write_bytes_once(root / "descendant.md", story.encode()); descendant = bind(root, root / "descendant.md")
        receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "verified_native_receipt", "event_id": row["event_id"], "phase": row["phase"], "prepared_sha256": sha(stable_read(root / "prepared-cell.json")), "payload_sha256": sha(payload), "native_receipt_sha256": sha(stable_read(root / "native-receipt.json")), "response_sha256": sha(stable_read(root / "response.json")), "descendant": descendant, "response": dict(response), "native": json.loads(stable_read(root / "native-receipt.json"))}
        write_once(root / "verified-receipt.json", receipt)
        write_once(root / "execution-result.json", {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "state": "settled", "process_launches": 1, "provider_calls_made": native["native_endpoint_contact_cardinality"], "no_resend": True, "receipt": bind(root, root / "verified-receipt.json")})
        return {"state": "settled", "process_launches": 1, "provider_calls_made": native["native_endpoint_contact_cardinality"], "verified_receipt": bind(root, root / "verified-receipt.json")}
    except Exception as error: return _terminal(root, state="terminal_postlaunch_reconcile_required", launches=1, contacts="unproven", error=error)  # noqa: BLE001


def replay_receipt(*, root: Path) -> dict[str, Any]:
    root = Path(root); receipt_raw = stable_read(root / "verified-receipt.json", label="verified receipt"); receipt = json.loads(receipt_raw); _prepared, row, payload = _read_prepared(root)
    native_raw, response_raw = stable_read(root / "native-receipt.json"), stable_read(root / "response.json"); native, response = json.loads(native_raw), json.loads(response_raw); story = _validate_response(row, response)
    schema_raw = stable_read(root / "adapter-schema-binding.json", label="adapter schema binding"); schema_binding = json.loads(schema_raw); expected_schema = _schema(row, json.loads(payload))
    if schema_binding != {"format_version": 1, "study_id": STUDY_ID, "schema": expected_schema, "schema_sha256": sha(canonical(expected_schema))} or canonical(schema_binding) + b"\n" != schema_raw: raise ValueError("V6 adapter schema replay drifted")
    raw = stable_read(root / "adapter-stdout.raw", label="native adapter stdout"); stderr = stable_read(root / "adapter-stderr.raw", label="native adapter stderr"); state, result = _control(raw)
    control_raw = stable_read(root / "adapter-control.json", label="adapter control")
    if state != "completed" or not isinstance(result, Mapping) or canonical(json.loads(raw)) + b"\n" != control_raw:
        raise ValueError("V6 adapter control replay drifted")
    raw_response, runtime = result.get("output"), result.get("runtime")
    if not isinstance(raw_response, Mapping) or not isinstance(runtime, Mapping) or dict(raw_response) != response or result.get("request_hash") != sha(canonical({"prompt": payload.decode()})) or result.get("output_hash") != sha(canonical(response)):
        raise ValueError("V6 native adapter payload or tools replay drifted")
    proof = json.loads(stable_read(root / "governed-route-proof.json")); binding = proof["runtime_binding"]
    if proof.get("expected_adapter_runtime_identity_sha256") != sha(canonical(binding)): raise ValueError("V6 route runtime binding drifted")
    replay_route = {"adapter": proof["adapter"], "model": proof["model"], "reasoning_effort": proof["reasoning"], "reported_model": binding.get("reported_model", "grok-4.6-build"), "nonvisual_max_turns": binding.get("nonvisual_max_turns"), "grok_cli_version": runtime.get("cli_version"), "codex_cli_version": runtime.get("cli_version"), "grok_command": binding.get("grok_command"), "codex_command": binding.get("codex_command"), "grok_command_identity": binding.get("command_identity"), "codex_command_identity": binding.get("command_identity")}
    _validate_runtime(route=replay_route, result=result, runtime=runtime)
    receipt_field = "subscription_receipt_hash" if replay_route["adapter"] == "grok_exec" else "auth_receipt_hash"
    if runtime[receipt_field] != proof["route_receipt_sha256"]: raise ValueError("V6 adapter receipt replay drifted")
    for value in (runtime.get("command_identity_hash"), runtime.get(receipt_field), native.get("raw_adapter_stdout_sha256"), native.get("raw_adapter_stderr_sha256"), native.get("transmitted_payload_sha256"), proof.get("route_receipt_sha256"), proof.get("expected_adapter_runtime_identity_sha256")):
        _hash(value)
    if row["route"]["model"] == "grok-4.6":
        for value in (runtime.get("session_id_hash"), runtime.get("request_id_hash"), runtime.get("envelope_hash")): _hash(value)
    else:
        for value in (runtime.get("events_hash"), runtime.get("raw_output_hash")): _hash(value)
    descendant = None
    if story is not None:
        if stable_read(root / "descendant.md") != story.encode(): raise ValueError("V6 descendant bytes drifted")
        descendant = bind(root, root / "descendant.md")
    expected = {"format_version": 1, "study_id": STUDY_ID, "kind": "verified_native_receipt", "event_id": row["event_id"], "phase": row["phase"], "prepared_sha256": sha(stable_read(root / "prepared-cell.json")), "payload_sha256": sha(payload), "native_receipt_sha256": sha(native_raw), "response_sha256": sha(response_raw), "descendant": descendant, "response": response, "native": native}
    if canonical(receipt) + b"\n" != receipt_raw or receipt != expected: raise ValueError("V6 receipt replay drifted")
    expected_adapter = "grok_exec" if row["route"]["model"] == "grok-4.6" else "codex_exec"
    expected_route = {"provider": proof["provider"], "destination": proof["destination"], "adapter": expected_adapter, "model": row["route"]["model"], "reasoning": row["route"]["reasoning"], "tools_enabled": False}
    if row["route"]["model"] == "grok-4.6":
        request_id, session_id = runtime.get("request_id_hash"), runtime.get("session_id_hash")
        if not isinstance(request_id, str) or not isinstance(session_id, str) or request_id == session_id or runtime.get("requested_model") != "grok-4.6" or runtime.get("reported_model") != "grok-4.6-build" or runtime.get("requested_reasoning_effort") != "high" or runtime.get("observed_turns") != 1: raise ValueError("V6 Grok native replay identity drifted")
        expected_native_ids = ("grok-request-sha256:" + request_id, "grok-session-sha256:" + session_id, 1)
    else:
        projection = runtime.get("event_projection"); thread = projection.get("thread_id") if isinstance(projection, Mapping) else None
        if not isinstance(thread, str) or not thread or runtime.get("requested_model") != "gpt-5.6-sol" or runtime.get("requested_reasoning_effort") != "high": raise ValueError("V6 Sol native replay identity drifted")
        expected_native_ids = ("sol-thread-sha256:" + sha(thread.encode()), "sol-thread-sha256:" + sha(thread.encode()), "unproven")
    if native.get("provider_model") != row["route"]["model"] or native.get("reasoning") != "high" or native.get("tools_enabled") is not False or native.get("route_identity") != expected_route or (native.get("provider_request_id"), native.get("provider_session_id"), native.get("native_endpoint_contact_cardinality")) != expected_native_ids or native.get("transmitted_payload_sha256") != sha(payload) or native.get("raw_adapter_stdout_sha256") != sha(raw) or native.get("raw_adapter_stderr_sha256") != sha(stderr): raise ValueError("V6 receipt native identity drifted")
    execution_raw = stable_read(root / "execution-result.json", label="execution result"); execution = json.loads(execution_raw)
    expected_execution = {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "state": "settled", "process_launches": 1, "provider_calls_made": expected_native_ids[2], "no_resend": True, "receipt": bind(root, root / "verified-receipt.json")}
    if execution != expected_execution or canonical(execution) + b"\n" != execution_raw: raise ValueError("V6 execution result replay drifted")
    return receipt


def finalize_targets_from_receipts(*, run_root: Path) -> dict[str, tuple[str, str]]:
    study, sources = v3(), _frozen_sources(run_root); descendants: dict[str, str] = {}
    for row in schedule():
        if row["phase"] != "revision_generation": continue
        receipt = replay_receipt(root=_root(run_root, row)); descendant = receipt.get("descendant")
        if not isinstance(descendant, Mapping): raise TypeError("V6 revision receipt lacks an immutable descendant")
        descendants[row["event_id"]] = stable_read(_root(run_root, row) / str(descendant["path"])).decode()
    values: dict[str, tuple[str, str]] = {}
    for target in study.targets():
        text = sources[target["source_item_id"]][0] if target["kind"] == "source_baseline" else descendants.get(target["target_event_id"], "")
        if not text: raise ValueError("V6 target freeze requires all eight receipt-derived descendants")
        values[target["blind_target_id"]] = (text, sha(text.encode()))
    if len(values) != 12: raise ValueError("V6 blind target geometry drifted")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "receipt_derived_frozen_blind_targets", "targets": [{"blind_target_id": key, "bytes": len(value[0].encode()), "sha256": value[1]} for key, value in sorted(values.items())]}
    path = Path(run_root) / "frozen-targets.json"
    if path.exists():
        if stable_read(path) != canonical(manifest) + b"\n": raise ValueError("V6 frozen targets drifted")
    else: write_once(path, manifest)
    return values


def project(*, run_root: Path) -> dict[str, Any]:
    study = v3(); observed: dict[str, int] = {}; identities: set[tuple[str, str]] = set()
    all_identities: set[tuple[str, str]] = set()
    for cell in schedule():
        receipt = replay_receipt(root=_root(run_root, cell)); native = receipt["native"]
        identity = (str(native.get("provider_request_id")), str(native.get("provider_session_id")))
        if identity in all_identities: raise ValueError("V6 native identity is duplicated across the 60-cell run")
        all_identities.add(identity)
    if len(all_identities) != 60: raise ValueError("V6 run-wide native identity geometry is incomplete")
    for row in schedule():
        if row["phase"] != "blind_endpoint_judgment": continue
        receipt = replay_receipt(root=_root(run_root, row)); native = receipt["native"]; identity = (str(native.get("provider_request_id")), str(native.get("provider_session_id")))
        if identity in identities: raise ValueError("V6 endpoint native identity is duplicated")
        identities.add(identity); observed[row["event_id"]] = receipt["response"]["overall"]
    if len(observed) != 48: raise ValueError("V6 endpoint projection requires all 48 native receipts")
    target_by_event = {row["target_event_id"]: row["blind_target_id"] for row in study.targets() if row["target_event_id"]}; baselines = {row["source_item_id"]: row["blind_target_id"] for row in study.targets() if row["kind"] == "source_baseline"}
    primary: list[dict[str, Any]] = []; guided_source: list[dict[str, Any]] = []; generic_source: list[dict[str, Any]] = []
    for revision in study.revision_schedule():
        control = revision["event_id"].replace("-cwr_guided", "-generic_no_feedback")
        for judge in study.contract()["routes"]["judges"]:
            for measure in ("holistic", "compact"):
                current = observed[f"endpoint-v3-{target_by_event[revision['event_id']]}-{measure}-{judge}"]; source = observed[f"endpoint-v3-{baselines[revision['source_item_id']]}-{measure}-{judge}"]
                item = {"source_item_id": revision["source_item_id"], "judge_route_id": judge, "measure_id": measure, "arm_minus_source": current - source}
                (guided_source if revision["guidance_arm"] == "cwr_guided" else generic_source).append(item)
                if revision["guidance_arm"] == "cwr_guided": primary.append({"source_item_id": revision["source_item_id"], "judge_route_id": judge, "measure_id": measure, "guided_minus_control": current - observed[f"endpoint-v3-{target_by_event[control]}-{measure}-{judge}"]})
    return {"study_id": STUDY_ID, "kind": "independently_replayed_endpoint_projection", "endpoint_results_are_not_pooled": True, "primary_guided_minus_control": primary, "guided_minus_source": guided_source, "generic_minus_source": generic_source}


def status(*, root: Path) -> dict[str, Any]:
    """Read-only state inspector; it cannot reopen a terminal one-shot cell."""
    root = Path(root)
    if (root / "execution-result.json").is_file():
        receipt = replay_receipt(root=root)
        return {"study_id": STUDY_ID, "state": "settled", "event_id": receipt["event_id"], "provider_calls_made": receipt["native"]["native_endpoint_contact_cardinality"], "no_resend": True}
    if (root / "terminal-outcome.json").is_file():
        value = json.loads(stable_read(root / "terminal-outcome.json", label="terminal outcome"))
        if value.get("study_id") != STUDY_ID or value.get("no_resend") is not True: raise ValueError("V6 terminal outcome drifted")
        return {"study_id": STUDY_ID, "state": value["state"], "event_id": json.loads(stable_read(root / "prepared-cell.json"))["event_id"], "provider_calls_made": value["provider_calls_made"], "no_resend": True}
    _prepared, row, _payload = _read_prepared(root)
    return {"study_id": STUDY_ID, "state": "prepared", "event_id": row["event_id"], "provider_calls_made": 0, "no_resend": True}


def reconcile_one(*, root: Path) -> dict[str, Any]:
    """Provider-free terminal inspection; reconciliation never remints or resends."""
    root = Path(root)
    if (root / "execution-result.json").is_file():
        receipt = replay_receipt(root=root)
        return {"study_id": STUDY_ID, "state": "settled", "event_id": receipt["event_id"], "process_launches": 0, "provider_calls_made": 0, "no_resend": True}
    outcome_path = root / "terminal-outcome.json"
    outcome = json.loads(stable_read(outcome_path, label="terminal outcome"))
    if outcome.get("study_id") != STUDY_ID or outcome.get("state") != "terminal_postlaunch_reconcile_required" or outcome.get("process_launches") != 1 or outcome.get("no_resend") is not True:
        raise ValueError("V6 reconciliation requires one exact postlaunch terminal outcome")
    required = _PREPARED | {"launch-intent.json", "adapter-stdout.raw", "adapter-stderr.raw", "terminal-outcome.json"}
    _validate_plain_inventory(root, required)
    try:
        _prepared, row, payload = _read_prepared(root); raw = stable_read(root / "adapter-stdout.raw", label="reconciliation stdout"); stderr = stable_read(root / "adapter-stderr.raw", label="reconciliation stderr")
        state, result = _control(raw)
    except Exception:  # noqa: BLE001
        return {"study_id": STUDY_ID, "state": "reconcile_required", "process_launches": 0, "provider_calls_made": 0, "no_resend": True}
    if state != "completed" or not isinstance(result, Mapping): return {"study_id": STUDY_ID, "state": "reconcile_required", "process_launches": 0, "provider_calls_made": 0, "no_resend": True}
    try:
        response, runtime = result.get("output"), result.get("runtime")
        if not isinstance(response, Mapping) or not isinstance(runtime, Mapping) or result.get("request_hash") != sha(canonical({"prompt": payload.decode()})) or result.get("output_hash") != sha(canonical(response)): raise ValueError("V6 reconciliation control drifted")
        proof = json.loads(stable_read(root / "governed-route-proof.json")); binding = proof["runtime_binding"]
        route = {"adapter": proof["adapter"], "model": proof["model"], "reasoning_effort": proof["reasoning"], "reported_model": binding.get("reported_model", "grok-4.6-build"), "nonvisual_max_turns": binding.get("nonvisual_max_turns"), "grok_cli_version": runtime.get("cli_version"), "codex_cli_version": runtime.get("cli_version"), "grok_command": binding.get("grok_command"), "codex_command": binding.get("codex_command"), "grok_command_identity": binding.get("command_identity"), "codex_command_identity": binding.get("command_identity")}
        schema_raw = stable_read(root / "adapter-schema-binding.json", label="reconciliation schema binding"); schema_binding = json.loads(schema_raw); expected_schema = _schema(row, json.loads(payload))
        if schema_binding != {"format_version": 1, "study_id": STUDY_ID, "schema": expected_schema, "schema_sha256": sha(canonical(expected_schema))} or canonical(schema_binding) + b"\n" != schema_raw or proof.get("expected_adapter_runtime_identity_sha256") != sha(canonical(binding)):
            raise ValueError("V6 reconciliation replay binding drifted")
        _validate_runtime(route=route, result=result, runtime=runtime); receipt_field = "subscription_receipt_hash" if route["adapter"] == "grok_exec" else "auth_receipt_hash"
        if runtime[receipt_field] != proof["route_receipt_sha256"]: raise ValueError("V6 reconciliation receipt evidence drifted")
        for value in (runtime.get("command_identity_hash"), runtime.get(receipt_field), proof.get("route_receipt_sha256"), proof.get("expected_adapter_runtime_identity_sha256")):
            _hash(value)
        if route["adapter"] == "grok_exec":
            for value in (runtime.get("session_id_hash"), runtime.get("request_id_hash"), runtime.get("envelope_hash")): _hash(value)
        else:
            for value in (runtime.get("events_hash"), runtime.get("raw_output_hash")): _hash(value)
        story = _validate_response(row, response)
        if route["model"] == "grok-4.6":
            native = {"provider_request_id": "grok-request-sha256:" + runtime["request_id_hash"], "provider_session_id": "grok-session-sha256:" + runtime["session_id_hash"], "native_endpoint_contact_cardinality": 1, "evidence_class": "grok_native_request_session_exact_one_contact_v1"}
        else:
            thread = runtime["event_projection"].get("thread_id")
            if not isinstance(thread, str) or not thread: raise ValueError("V6 reconciliation Sol lifecycle identity drifted")
            token = "sol-thread-sha256:" + sha(thread.encode()); native = {"provider_request_id": token, "provider_session_id": token, "native_endpoint_contact_cardinality": "unproven", "evidence_class": "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1"}
        route_identity = {"provider": proof["provider"], "destination": proof["destination"], "adapter": route["adapter"], "model": route["model"], "reasoning": route["reasoning_effort"], "tools_enabled": False}
        write_once(root / "adapter-control.json", json.loads(raw)); write_once(root / "response.json", dict(response)); write_once(root / "native-receipt.json", {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "provider_model": route["model"], "reasoning": "high", "tools_enabled": False, "route_identity": route_identity, "transmitted_payload_sha256": sha(payload), "raw_adapter_stdout_sha256": sha(raw), "raw_adapter_stderr_sha256": sha(stderr), **native})
        descendant = None
        if story is not None: write_bytes_once(root / "descendant.md", story.encode()); descendant = bind(root, root / "descendant.md")
        receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "verified_native_receipt", "event_id": row["event_id"], "phase": row["phase"], "prepared_sha256": sha(stable_read(root / "prepared-cell.json")), "payload_sha256": sha(payload), "native_receipt_sha256": sha(stable_read(root / "native-receipt.json")), "response_sha256": sha(stable_read(root / "response.json")), "descendant": descendant, "response": dict(response), "native": json.loads(stable_read(root / "native-receipt.json"))}
        write_once(root / "verified-receipt.json", receipt); write_once(root / "reconciliation.json", {"format_version": 1, "study_id": STUDY_ID, "terminal_outcome_sha256": sha(stable_read(outcome_path)), "raw_stdout_sha256": sha(raw), "raw_stderr_sha256": sha(stderr), "provider_calls_made": 0, "process_launches": 0, "no_resend": True})
        write_once(root / "execution-result.json", {"format_version": 1, "study_id": STUDY_ID, "event_id": row["event_id"], "state": "settled", "process_launches": 1, "provider_calls_made": native["native_endpoint_contact_cardinality"], "no_resend": True, "receipt": bind(root, root / "verified-receipt.json")})
        replay_receipt(root=root)
        return {"study_id": STUDY_ID, "state": "settled", "process_launches": 0, "provider_calls_made": 0, "no_resend": True}
    except Exception:  # noqa: BLE001
        return {"study_id": STUDY_ID, "state": "reconcile_required", "process_launches": 0, "provider_calls_made": 0, "no_resend": True}


def _cli() -> None:
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-inputs"); freeze.add_argument("--run-root", type=Path, required=True); freeze.add_argument("--source-root", type=Path, required=True)
    prepare = commands.add_parser("prepare-one"); prepare.add_argument("--run-root", type=Path, required=True); prepare.add_argument("--event-id", required=True); prepare.add_argument("--acknowledgement-sha256", required=True)
    execute = commands.add_parser("execute-one"); execute.add_argument("--root", type=Path, required=True)
    inspect = commands.add_parser("status"); inspect.add_argument("--root", type=Path, required=True)
    reconcile = commands.add_parser("reconcile-one"); reconcile.add_argument("--root", type=Path, required=True)
    target = commands.add_parser("finalize-targets"); target.add_argument("--run-root", type=Path, required=True)
    projection = commands.add_parser("project"); projection.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "freeze-inputs": result = freeze_run(run_root=args.run_root, source_root=args.source_root)
    elif args.command == "prepare-one": result = prepare_one(run_root=args.run_root, event_id=args.event_id, acknowledgement_sha256=args.acknowledgement_sha256)
    elif args.command == "execute-one": result = dispatch_one(root=args.root)
    elif args.command == "status": result = status(root=args.root)
    elif args.command == "reconcile-one": result = reconcile_one(root=args.root)
    elif args.command == "finalize-targets": result = {"study_id": STUDY_ID, "target_count": len(finalize_targets_from_receipts(run_root=args.run_root)), "provider_calls_made": 0}
    else: result = project(run_root=args.run_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    _cli()
