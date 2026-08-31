#!/usr/bin/env python3
"""One-shot Grok execution and exact receipt collection for the v5 HANNA schedule."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1"
EVALUATOR_COMMIT = "7222ebf"
EVALUATOR = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-shrinkage-eval-v1"
EVALUATOR_STUDY = EVALUATOR / "study.py"
EVALUATOR_ANALYZE = EVALUATOR / "analyze.py"
EVALUATOR_STUDY_SHA256 = "0a3572f41d51f488fd4ca779c688c618fbc3e124f7597810e63cc85a452c112d"
EVALUATOR_ANALYZE_SHA256 = "6f0bad6ff4ae6319c58119678bb03e1a49038f981687ed7cc9bd03c6f7c61cb2"
MATERIALIZER_COMMIT = "9447b33"
MATERIALIZER = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1" / "materialize.py"
MATERIALIZER_SHA256 = "aec112f15c7371191ecac70c3772063a40c842846fc52de6f6dc6c1dac9b0bd8"
NATIVE_EXEC = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
NATIVE_EXEC_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
PREPARED = frozenset({"outbound-payload.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
TERMINAL = frozenset({"launch-intent.json", "native-request.bin", "native-response.bin", "runtime-identity.json", "effective-settings.json", "execution-receipt.json", "result.json"})
POSTWRITE_RECONCILE = "postwrite-reconcile.json"
TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def adapter_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> bool:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        return False
    return directory is None or (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))


def _stable(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not _plain(current):
            raise ValueError(f"HANNA v5 live executor unsafe path: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA v5 live executor file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("HANNA v5 live executor file changed during read")
    return raw


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"HANNA v5 live executor refuses overwrite: {path.name}")
    if not _plain(path.parent, directory=True):
        raise ValueError("HANNA v5 live executor parent is unsafe")
    with path.open("xb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"HANNA v5 live executor duplicate key in {label}")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"HANNA v5 live executor invalid JSON: {label}") from error
    if not isinstance(value, dict):
        raise ValueError(f"HANNA v5 live executor {label} must be an object")
    return value


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = _stable(path)
    if sha256(raw) != digest:
        raise ValueError(f"HANNA v5 live executor pinned dependency drifted: {path.name}")
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    if _stable(path) != raw:
        raise ValueError(f"HANNA v5 live executor dependency changed during load: {path.name}")
    return module


def _study() -> ModuleType:
    if sha256(_stable(MATERIALIZER)) != MATERIALIZER_SHA256:
        raise ValueError("HANNA v5 live executor materializer source drifted")
    return _load(EVALUATOR_STUDY, EVALUATOR_STUDY_SHA256, "_hanna_v5_live_study")


def _analyze() -> ModuleType:
    return _load(EVALUATOR_ANALYZE, EVALUATOR_ANALYZE_SHA256, "_hanna_v5_live_analyze")


def _native_exec() -> ModuleType:
    return _load(NATIVE_EXEC, NATIVE_EXEC_SHA256, "_hanna_v5_live_native_exec")


def contract() -> dict[str, Any]:
    value = _strict_json(_stable(HERE / "study-contract.json"), "contract")
    expected = {
        "format_version": 2, "study_id": STUDY_ID, "kind": "deduplicated_descriptive_grok_primary_live_executor",
        "evaluator": {"commit": EVALUATOR_COMMIT, "study_sha256": EVALUATOR_STUDY_SHA256, "analyze_sha256": EVALUATOR_ANALYZE_SHA256},
        "materializer": {"commit": MATERIALIZER_COMMIT, "source_sha256": MATERIALIZER_SHA256},
        "endpoint_evidence": {"native_endpoint_contact_cardinality": "unproven", "strict_v5_projector": "must_reject"},
        "authority": {"confirmation": {"cells": 0, "status": "unopened"}, "provider_launch": "explicit_per_unique_payload_only", "runtime_selection": "none", "selection": "none", "sol_execution": "out_of_scope"},
    }
    if value != expected or canonical(value) != _stable(HERE / "study-contract.json"):
        raise ValueError("HANNA v5 live executor contract drifted")
    return value


def _schedule(*, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[ModuleType, Any, dict[str, Any]]:
    contract()
    study = _study()
    token = study.prepare_grok_schedule(materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    schedule, _ = study._validated_schedule(token)
    if schedule.get("geometry", {}).get("grok_cells") != 33 or len(schedule.get("cells", [])) != 33:
        raise ValueError("HANNA v5 live executor requires exactly 33 Grok cells")
    if any(row.get("route_name") != "grok_primary" for row in schedule["cells"]):
        raise ValueError("HANNA v5 live executor schedule route drifted")
    return study, token, schedule


def _cell(schedule: Mapping[str, Any], cell_id: str) -> dict[str, Any]:
    matches = [dict(row) for row in schedule["cells"] if row.get("cell_id") == cell_id]
    if len(matches) != 1:
        raise ValueError("HANNA v5 live executor requires one frozen Grok cell")
    return matches[0]


def _dedupe(study: ModuleType, schedule: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    canonical_rows: list[dict[str, Any]] = []
    aliases: dict[str, dict[str, Any]] = {}
    by_payload: dict[str, dict[str, Any]] = {}
    for source in schedule["cells"]:
        row = dict(source); payload, _prompt, _schema = _payload(study, row)
        if row["payload_sha256"] != sha256(payload):
            raise ValueError("HANNA v5 live executor dedupe payload binding drifted")
        original = by_payload.get(row["payload_sha256"])
        if original is None:
            by_payload[row["payload_sha256"]] = row; canonical_rows.append(row)
        else:
            aliases[row["cell_id"]] = {"alias_cell_id": row["cell_id"], "canonical_cell_id": original["cell_id"], "payload_sha256": row["payload_sha256"], "alias_candidate_id": row["candidate_id"], "canonical_candidate_id": original["candidate_id"], "provenance_kind": row["provenance_kind"]}
    effective_candidates = sorted({row["candidate_id"] for row in canonical_rows})
    if len(canonical_rows) != 30 or len(aliases) != 3 or len(effective_candidates) != 10 or len({row["payload_sha256"] for row in canonical_rows}) != 30:
        raise ValueError("HANNA v5 live executor expected 30 unique payloads, three aliases, and ten effective candidates")
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "deterministic_payload_alias_manifest", "logical_grok_cells": 33, "unique_payload_cells": 30, "effective_candidates": effective_candidates, "schedule_sha256": schedule["schedule_sha256"], "aliases": [aliases[key] for key in sorted(aliases)], "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}
    manifest["manifest_sha256"] = sha256(manifest)
    return canonical_rows, aliases, manifest


def _payload(study: ModuleType, row: Mapping[str, Any]) -> tuple[bytes, bytes, bytes]:
    payload = study.payload_bytes(row)
    value = _strict_json(payload, "frozen outbound payload")
    schema = value.get("response_schema")
    if not isinstance(schema, dict):
        raise ValueError("HANNA v5 live executor frozen schema is absent")
    schema_raw = canonical(schema)
    if sha256(payload) != row.get("payload_sha256"):
        raise ValueError("HANNA v5 live executor payload hash drifted")
    return payload, payload, schema_raw


def _route(queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    route, evidence = (route_provider or _native_exec().validate_live_grok_route)(Path(queue_root))
    required = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high"}
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or any(route.get(key) != value for key, value in required.items()):
        raise ValueError("HANNA v5 live executor Grok route is not a current zero-charge tool-free route")
    if not isinstance(route.get("grok_command"), list) or len(route["grok_command"]) != 1 or "public_synthetic" not in route.get("allowed_payload_classes", []) and "public_repo" not in route.get("allowed_payload_classes", []):
        raise ValueError("HANNA v5 live executor route cannot carry the disclosed public synthetic payload")
    return dict(route), dict(evidence)


def _artifacts(row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, prompt: bytes, schema: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement):
        raise ValueError("HANNA v5 live executor acknowledgement must be lowercase SHA-256")
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": row["cell_id"], "route": dict(route), "route_evidence": dict(evidence), "payload": {"bytes": len(payload), "sha256": sha256(payload), "text": payload.decode("utf-8")}, "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")}, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "provider_calls_made": 0, "process_launches": 0}
    ack = {"format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha256(disclosure)}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "zero_charge_current_route_proof", "cell_id": row["cell_id"], "route": dict(route), "route_evidence": dict(evidence), "disclosure_sha256": sha256(disclosure), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_grok_primary_native_cell", "cell": dict(row), "schedule_sha256": schedule["schedule_sha256"], "outbound_payload_sha256": sha256(payload), "prompt_request_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "route": dict(route), "route_evidence": dict(evidence), "disclosure_sha256": sha256(disclosure), "authorization_sha256": sha256(ack), "route_proof_sha256": sha256(proof), "tools_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    return prepared, {"outbound-payload.json": payload, "prompt-request.bin": prompt, "response-schema.json": schema, "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(ack), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def _inventory(root: Path) -> set[str]:
    if not root.is_dir() or not _plain(root, directory=True):
        raise ValueError("HANNA v5 live executor root is unsafe")
    names: set[str] = set()
    for entry in root.iterdir():
        if entry.name == "responses":
            if not _plain(entry, directory=True) or {item.name for item in entry.iterdir()} != {"batch-0001.attempt-0001.grok.envelope.json", "batch-0001.attempt-0001.prompt.txt"} or any(not _plain(entry / name, directory=False) for name in ("batch-0001.attempt-0001.grok.envelope.json", "batch-0001.attempt-0001.prompt.txt")):
                raise ValueError("HANNA v5 live executor response inventory is unsafe")
        elif not _plain(entry, directory=False):
            raise ValueError("HANNA v5 live executor root contains an unsafe artifact")
        names.add(entry.name)
    return names


def _verify_prepared(*, output_root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, prompt: bytes, schema: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> tuple[Path, dict[str, Any]]:
    root = Path(output_root) / row["cell_id"]
    if _inventory(root) != set(PREPARED):
        raise ValueError("HANNA v5 live executor requires a pristine prepared root")
    prepared, files = _artifacts(row, schedule, payload, prompt, schema, route, evidence, acknowledgement)
    for name, expected in files.items():
        if _stable(root / name) != expected:
            raise ValueError(f"HANNA v5 live executor prepared artifact drifted: {name}")
    return root, prepared


def _alias_manifest(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw = _stable(root / "alias-manifest.json")
    value = _strict_json(raw, "alias manifest")
    if value != manifest or canonical(value) != raw:
        raise ValueError("HANNA v5 live executor alias manifest drifted")
    return value


def prepare_all(*, output_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    study, _token, schedule = _schedule(materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows, _aliases, manifest = _dedupe(study, schedule)
    root = Path(output_root)
    if root.exists():
        raise ValueError("HANNA v5 live executor requires a fresh output root")
    route, evidence = _route(Path(queue_root), route_provider)
    root.mkdir(parents=True, exist_ok=False)
    if not _plain(root, directory=True):
        raise ValueError("HANNA v5 live executor created unsafe output root")
    _write_new(root / "alias-manifest.json", canonical(manifest))
    for row in rows:
        payload, prompt, schema = _payload(study, row)
        prepared, files = _artifacts(row, schedule, payload, prompt, schema, route, evidence, authorization_acknowledgement_sha256)
        cell_root = root / row["cell_id"]
        cell_root.mkdir(exist_ok=False)
        for name, raw in files.items():
            _write_new(cell_root / name, raw)
        _verify_prepared(output_root=root, row=row, schedule=schedule, payload=payload, prompt=prompt, schema=schema, route=route, evidence=evidence, acknowledgement=authorization_acknowledgement_sha256)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_unique_grok_primary_payload_cells", "schedule_sha256": schedule["schedule_sha256"], "alias_manifest_sha256": sha256(manifest), "prepared_cells": [row["cell_id"] for row in rows], "logical_cells": 33, "unique_payload_cells": 30, "effective_candidates": 10, "provider_calls_made": 0, "process_launches": 0}


def _default_runner(*, prompt: bytes, schema_path: Path, output_dir: Path, route: Mapping[str, Any], before_contact: Callable[[], None]) -> dict[str, Any]:
    native = _native_exec()
    content, record = native._load_call_grok()(executable=route["grok_command"][0], model="grok-4.6", reasoning="high", prompt=prompt.decode("utf-8"), output_dir=output_dir, response_schema=schema_path, batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, allow_unattested_reasoning=True, system_prompt_override="Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", before_provider_attempt=before_contact)
    envelope = _stable(output_dir / "responses" / "batch-0001.attempt-0001.grok.envelope.json")
    request_id, session_id = native._envelope_identity(envelope, record)
    if not isinstance(content, str):
        raise ValueError("HANNA v5 live executor Grok returned nontext content")
    identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": request_id, "session_id": session_id, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
    return {"native_request_bytes": adapter_canonical({"prompt": prompt.decode("utf-8")}), "native_response_bytes": envelope, "identity": identity, "effective_settings": settings}


def _validate_runner_result(value: Any, route: Mapping[str, Any], prompt: bytes) -> tuple[bytes, bytes, dict[str, Any], dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"native_request_bytes", "native_response_bytes", "identity", "effective_settings"}:
        raise ValueError("HANNA v5 live executor native runner result drifted")
    request, response, identity, settings = value["native_request_bytes"], value["native_response_bytes"], value["identity"], value["effective_settings"]
    expected_identity = {"provider", "requested_model", "reported_model", "request_id", "session_id", "native_endpoint_contact_cardinality", "tools_enabled"}
    if not isinstance(request, bytes) or not isinstance(response, bytes) or not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or set(identity) != expected_identity:
        raise ValueError("HANNA v5 live executor native result types drifted")
    if dict(identity).get("provider") != "xai" or identity.get("requested_model") != "grok-4.6" or identity.get("reported_model") != "grok-4.6-build" or identity.get("native_endpoint_contact_cardinality") != "unproven" or identity.get("tools_enabled") is not False or any(not isinstance(identity.get(key), str) or not identity[key] for key in ("request_id", "session_id")):
        raise ValueError("HANNA v5 live executor native identity drifted")
    expected_settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
    if dict(settings) != expected_settings:
        raise ValueError("HANNA v5 live executor effective settings drifted")
    native = _strict_json(response, "native Grok envelope")
    if native.get("requestId") != identity["request_id"] or native.get("sessionId") != identity["session_id"]:
        raise ValueError("HANNA v5 live executor response identity is misassociated")
    return request, response, dict(identity), dict(settings)


def _terminal(root: Path, row: Mapping[str, Any], state: str, *, intent: Mapping[str, Any] | None, detail: str, launches: int) -> dict[str, Any]:
    existing = root / "result.json"
    if existing.exists():
        prior = _strict_json(_stable(existing), "prior terminal result")
        if prior.get("kind") == "local_cli_lifecycle_grok_cell_completed_cardinality_unproven":
            marker = {"format_version": 1, "study_id": STUDY_ID, "kind": "postwrite_reconcile_required", "cell_id": row["cell_id"], "supersedes_result_sha256": sha256(prior), "detail": detail, "retry_policy": "fresh_output_root_required_no_in_place_resend"}
            marker_path = root / POSTWRITE_RECONCILE
            if not marker_path.exists():
                _write_new(marker_path, canonical(marker))
            elif _strict_json(_stable(marker_path), "postwrite reconcile marker") != marker:
                raise ValueError("HANNA v5 live executor postwrite reconcile marker drifted")
            return marker
        return prior
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": state, "cell_id": row["cell_id"], "detail": detail, "process_launches": launches, "provider_calls_made": 0 if state == "definitely_not_contacted" else None, "native_contact_proven": False, "native_endpoint_contact_cardinality": "zero" if state == "definitely_not_contacted" else "unknown", "intent_sha256": sha256(intent) if intent else None}
    _write_new(root / "result.json", canonical(result))
    return result


def execute_one(*, output_root: Path, cell_id: str, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("HANNA v5 live executor requires explicit allow_remote=True")
    study, _token, schedule = _schedule(materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows, aliases, manifest = _dedupe(study, schedule)
    if cell_id in aliases:
        raise ValueError("HANNA v5 live executor alias cell has no execution root or contact")
    row = _cell(schedule, cell_id)
    if row not in rows:
        raise ValueError("HANNA v5 live executor cell is not a unique payload representative")
    if _alias_manifest(Path(output_root), manifest) != manifest:
        raise ValueError("HANNA v5 live executor alias manifest changed")
    payload, prompt, schema = _payload(study, row); route, evidence = _route(Path(queue_root), route_provider)
    root, prepared = _verify_prepared(output_root=Path(output_root), row=row, schedule=schedule, payload=payload, prompt=prompt, schema=schema, route=route, evidence=evidence, acknowledgement=authorization_acknowledgement_sha256)
    intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_native_grok_contact", "cell_id": cell_id, "prepared_sha256": sha256(prepared), "outbound_payload_sha256": sha256(payload), "native_contact_proven": False}
    launches = 0
    def before_contact() -> None:
        nonlocal launches
        if launches:
            raise ValueError("HANNA v5 live executor runner signalled contact more than once")
        fresh_route, fresh_evidence = _route(Path(queue_root), route_provider)
        if fresh_route != route or fresh_evidence != evidence:
            raise ValueError("HANNA v5 live executor route drifted adjacent to launch")
        _write_new(root / "launch-intent.json", canonical(intent)); launches = 1
    try:
        value = (runner or _default_runner)(prompt=prompt, schema_path=root / "response-schema.json", output_dir=root, route=route, before_contact=before_contact)
    except BaseException as error:
        if launches == 0:
            return _terminal(root, row, "definitely_not_contacted", intent=None, detail=type(error).__name__, launches=0)
        return _terminal(root, row, "reconcile_required_after_process_launch", intent=intent, detail=type(error).__name__, launches=1)
    if launches != 1:
        return _terminal(root, row, "definitely_not_contacted", intent=None, detail="runner_returned_without_contact_callback", launches=0)
    try:
        request, response, identity, settings = _validate_runner_result(value, route, prompt)
        if request != adapter_canonical({"prompt": prompt.decode("utf-8")}):
            raise ValueError("HANNA v5 live executor native request bytes differ from frozen prompt")
        _write_new(root / "native-request.bin", request); _write_new(root / "native-response.bin", response)
        _write_new(root / "runtime-identity.json", canonical(identity)); _write_new(root / "effective-settings.json", canonical(settings))
        prompt_artifact = root / "responses" / "batch-0001.attempt-0001.prompt.txt"
        if prompt_artifact.exists() and _stable(prompt_artifact) != prompt:
            raise ValueError("HANNA v5 live executor runner prompt artifact drifted")
        receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_primary_unproven_cardinality_cell_receipt", "cell": row, "prepared_sha256": sha256(prepared), "launch_intent_sha256": sha256(intent), "payload_sha256": sha256(payload), "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "runner_prompt_artifact_sha256": sha256(_stable(prompt_artifact)) if prompt_artifact.exists() else None, "effective_settings_sha256": sha256(settings), "identity": identity, "identity_sha256": sha256(identity), "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
        result = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_cli_lifecycle_grok_cell_completed_cardinality_unproven", "cell_id": cell_id, "receipt_sha256": sha256(receipt), "provider_calls_made": None, "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven"}
        _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical(result))
        _admit_completed(root=root, row=row, schedule=schedule, payload=payload, prompt=prompt, schema=schema, route=route, evidence=evidence, acknowledgement=authorization_acknowledgement_sha256)
        return {"cell_id": cell_id, "state": "local_cli_lifecycle_received", "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    except BaseException as error:
        return _terminal(root, row, "reconcile_required_after_process_launch", intent=intent, detail=type(error).__name__, launches=1)


def _admit_completed(*, root: Path, row: Mapping[str, Any], schedule: Mapping[str, Any], payload: bytes, prompt: bytes, schema: bytes, route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, Any]:
    marker_path = root / POSTWRITE_RECONCILE
    if marker_path.exists():
        marker_raw = _stable(marker_path); marker = _strict_json(marker_raw, "postwrite reconcile marker")
        if canonical(marker) != marker_raw or marker.get("study_id") != STUDY_ID or marker.get("kind") != "postwrite_reconcile_required" or marker.get("cell_id") != row["cell_id"]:
            raise ValueError("HANNA v5 live executor postwrite reconcile marker drifted")
        raise ValueError("HANNA v5 live executor postwrite reconciliation blocks admission and collection")
    names = _inventory(root)
    allowed = set(PREPARED | TERMINAL) | {"responses"}
    if not set(PREPARED | TERMINAL) <= names or "responses" not in names or names - allowed:
        raise ValueError("HANNA v5 live executor completed root inventory drifted")
    prepared, files = _artifacts(row, schedule, payload, prompt, schema, route, evidence, acknowledgement)
    if any(_stable(root / name) != raw for name, raw in files.items()):
        raise ValueError("HANNA v5 live executor completed prepared bytes drifted")
    intent = _strict_json(_stable(root / "launch-intent.json"), "launch intent")
    expected_intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_native_grok_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared), "outbound_payload_sha256": sha256(payload), "native_contact_proven": False}
    if intent != expected_intent:
        raise ValueError("HANNA v5 live executor intent drifted")
    request, response, identity, settings = _validate_runner_result({"native_request_bytes": _stable(root / "native-request.bin"), "native_response_bytes": _stable(root / "native-response.bin"), "identity": _strict_json(_stable(root / "runtime-identity.json"), "identity"), "effective_settings": _strict_json(_stable(root / "effective-settings.json"), "settings")}, route, prompt)
    if request != adapter_canonical({"prompt": prompt.decode("utf-8")}):
        raise ValueError("HANNA v5 live executor persisted request drifted")
    receipt = _strict_json(_stable(root / "execution-receipt.json"), "receipt")
    prompt_artifact = root / "responses" / "batch-0001.attempt-0001.prompt.txt"
    if prompt_artifact.exists() and _stable(prompt_artifact) != prompt:
        raise ValueError("HANNA v5 live executor persisted runner prompt artifact drifted")
    expected_receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_primary_unproven_cardinality_cell_receipt", "cell": row, "prepared_sha256": sha256(prepared), "launch_intent_sha256": sha256(intent), "payload_sha256": sha256(payload), "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "runner_prompt_artifact_sha256": sha256(_stable(prompt_artifact)) if prompt_artifact.exists() else None, "effective_settings_sha256": sha256(settings), "identity": identity, "identity_sha256": sha256(identity), "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    if receipt != expected_receipt:
        raise ValueError("HANNA v5 live executor receipt drifted")
    result = _strict_json(_stable(root / "result.json"), "result")
    expected_result = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_cli_lifecycle_grok_cell_completed_cardinality_unproven", "cell_id": row["cell_id"], "receipt_sha256": sha256(receipt), "provider_calls_made": None, "process_launches": 1, "native_contact_proven": False, "native_endpoint_contact_cardinality": "unproven"}
    if result != expected_result:
        raise ValueError("HANNA v5 live executor result drifted")
    return {"cell_id": row["cell_id"], "payload": payload, "response": response, "identity": identity, "effective_settings": settings}


def finalize_collector(*, output_root: Path, collector_output: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    if Path(collector_output).exists():
        raise ValueError("HANNA v5 live executor refuses an existing collector output")
    study, _token, schedule = _schedule(materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows, _aliases, manifest = _dedupe(study, schedule)
    if route_provider is not None:
        raise ValueError("HANNA v5 live executor finalization replays persisted route evidence; it does not re-arm or substitute a route")
    if _alias_manifest(Path(output_root), manifest) != manifest:
        raise ValueError("HANNA v5 live executor collector alias manifest drifted")
    cells = []
    for row in rows:
        payload, prompt, schema = _payload(study, row)
        root = Path(output_root) / row["cell_id"]
        stored_prepared = _strict_json(_stable(root / "prepared.json"), "prepared")
        acknowledgement = _strict_json(_stable(root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
        if acknowledgement != authorization_acknowledgement_sha256 or not isinstance(stored_prepared.get("route"), Mapping) or not isinstance(stored_prepared.get("route_evidence"), Mapping):
            raise ValueError("HANNA v5 live executor collector preparation binding drifted")
        completed = _admit_completed(root=root, row=row, schedule=schedule, payload=payload, prompt=prompt, schema=schema, route=stored_prepared["route"], evidence=stored_prepared["route_evidence"], acknowledgement=acknowledgement)
        response, identity, settings = completed["response"], completed["identity"], completed["effective_settings"]
        cells.append({"cell_id": row["cell_id"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": sha256(response), "runner_prompt_artifact_sha256": settings["runner_prompt_artifact_sha256"], "effective_settings_sha256": sha256(settings), "identity": identity})
    evidence_value = {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_hanna_local_cli_lifecycle_receipts_cardinality_unproven", "route_name": "grok_primary", "logical_cells": 33, "unique_payload_cells": 30, "effective_candidates": 10, "alias_manifest_sha256": sha256(manifest), "native_endpoint_contact_cardinality": "unproven", "cells": cells}
    raw = canonical(evidence_value)
    _write_new(Path(collector_output), raw)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": evidence_value["kind"], "collector_sha256": sha256(raw), "logical_cells": 33, "unique_payload_cells": 30, "effective_candidates": 10, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0}


def descriptive_project(*, collector_path: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    study, _token, schedule = _schedule(materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows, _aliases, manifest = _dedupe(study, schedule)
    raw = _stable(Path(collector_path)); value = _strict_json(raw, "collector")
    if canonical(value) != raw or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("kind") != "complete_hanna_local_cli_lifecycle_receipts_cardinality_unproven" or value.get("route_name") != "grok_primary" or value.get("native_endpoint_contact_cardinality") != "unproven" or value.get("logical_cells") != 33 or value.get("unique_payload_cells") != 30 or value.get("effective_candidates") != 10 or value.get("alias_manifest_sha256") != sha256(manifest) or not isinstance(value.get("cells"), list) or len(value["cells"]) != 30:
        raise ValueError("HANNA v5 live executor descriptive collector drifted")
    index = {row["cell_id"]: row for row in rows}; seen: set[tuple[str, str]] = set(); observed: list[dict[str, Any]] = []
    analyzer = _analyze(); evaluator_study = analyzer._study(); evaluator_token = evaluator_study.prepare_grok_schedule(materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)); targets = analyzer._targets(evaluator_token)
    for supplied in value["cells"]:
        if not isinstance(supplied, Mapping) or set(supplied) != {"cell_id", "payload_base64", "payload_sha256", "native_response_base64", "native_response_sha256", "runner_prompt_artifact_sha256", "effective_settings_sha256", "identity"}:
            raise ValueError("HANNA v5 live executor descriptive receipt fields drifted")
        row = index.get(supplied["cell_id"])
        payload = base64.b64decode(supplied["payload_base64"], validate=True); response = base64.b64decode(supplied["native_response_base64"], validate=True)
        if row is None or payload != study.payload_bytes(row) or supplied["payload_sha256"] != sha256(payload) or supplied["native_response_sha256"] != sha256(response) or supplied["runner_prompt_artifact_sha256"] != sha256(payload):
            raise ValueError("HANNA v5 live executor descriptive payload/response binding drifted")
        identity = supplied["identity"]
        if not isinstance(identity, Mapping) or set(identity) != {"provider", "requested_model", "reported_model", "request_id", "session_id", "native_endpoint_contact_cardinality", "tools_enabled"} or identity.get("native_endpoint_contact_cardinality") != "unproven" or identity.get("tools_enabled") is not False:
            raise ValueError("HANNA v5 live executor descriptive identity drifted")
        contact = (identity.get("request_id"), identity.get("session_id"))
        if not all(isinstance(part, str) and part for part in contact) or contact in seen:
            raise ValueError("HANNA v5 live executor descriptive receipt contact identity duplicated")
        seen.add(contact); scores, _coverage, _reported = analyzer._v2()._extract_native(response, provider="xai", model="grok-4.6"); target = targets.get(row["item_id"])
        if target is None:
            raise ValueError("HANNA v5 live executor descriptive target drifted")
        observed.append({"cell_id": row["cell_id"], "candidate_id": row["candidate_id"], "prompt_group_id": row["prompt_group_id"], "mean_absolute_error": sum(abs(scores[key] - target[key]) for key in analyzer._v2().DIMENSIONS) / len(analyzer._v2().DIMENSIONS), "effective_settings_sha256": supplied["effective_settings_sha256"]})
    if set(index) != {row["cell_id"] for row in observed}:
        raise ValueError("HANNA v5 live executor descriptive receipts partial")
    groups = [row["prompt_group_id"] for row in schedule["groups"]]; metrics = []
    for candidate in manifest["effective_candidates"]:
        candidate_rows = [row for row in observed if row["candidate_id"] == candidate]
        by_group = {group: [row["mean_absolute_error"] for row in candidate_rows if row["prompt_group_id"] == group] for group in groups}
        if any(len(by_group[group]) != 1 for group in groups):
            raise ValueError("HANNA v5 live executor descriptive equal-group geometry drifted")
        group_mae = {group: by_group[group][0] for group in groups}; metrics.append({"candidate_id": candidate, "equal_group_mae": sum(group_mae.values()) / len(groups), "group_mae": group_mae, "cells": 3})
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "descriptive_equal_group_grok_mae_cardinality_unproven", "collector_sha256": sha256(raw), "alias_manifest_sha256": sha256(manifest), "metrics": sorted(metrics, key=lambda row: (row["equal_group_mae"], row["candidate_id"])), "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}, "claim": "DESCRIPTIVE_DEVELOPMENT_ONLY; strict v5 native projector rejects unproven-cardinality receipts; no general HANNA claim"}
    result["result_sha256"] = sha256(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare-all", action="store_true"); mode.add_argument("--execute-one", action="store_true"); mode.add_argument("--finalize-collector", action="store_true"); mode.add_argument("--descriptive-project", action="store_true")
    parser.add_argument("--allow-remote", action="store_true"); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--collector-output", type=Path); parser.add_argument("--cell-id"); parser.add_argument("--materialization-root", type=Path, required=True); parser.add_argument("--frozen-successor", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--queue-root", type=Path); parser.add_argument("--authorization-acknowledgement-sha256")
    args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "materialization_root": args.materialization_root, "frozen_successor_path": args.frozen_successor, "hanna_csv_path": args.hanna_csv}
    if args.prepare_all:
        if args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256: parser.error("prepare-all requires queue root and acknowledgement and forbids --allow-remote")
        result = prepare_all(**common, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    elif args.execute_one:
        if not args.allow_remote or not args.cell_id or not args.queue_root or not args.authorization_acknowledgement_sha256: parser.error("execute-one requires --allow-remote, cell ID, queue root, and acknowledgement")
        result = execute_one(**common, cell_id=args.cell_id, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, allow_remote=True)
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256: parser.error("finalize-collector requires collector output and acknowledgement and forbids --allow-remote")
        result = finalize_collector(**common, collector_output=args.collector_output, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    else:
        if args.allow_remote or not args.collector_output: parser.error("descriptive-project requires collector output and forbids --allow-remote")
        result = descriptive_project(collector_path=args.collector_output, materialization_root=args.materialization_root, frozen_successor_path=args.frozen_successor, hanna_csv_path=args.hanna_csv)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__":
    raise SystemExit(main())
