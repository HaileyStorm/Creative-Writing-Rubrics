#!/usr/bin/env python3
"""One-shot, tool-free Grok generation of ten HANNA descendant candidates."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-exec-v1"
PUBLIC_RESULT_COMMIT = "f20f8178112bb92c8acc084dcb6d08cdcef3c3bb"
PUBLIC_RESULT = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-result-v1" / "result.json"
PUBLIC_RESULT_SHA256 = "870bc10bb4a491953d43c47dc6764faddb9f9b579eea8e90c655d46722e6c966"
PUBLIC_RESULT_INTERNAL_SHA256 = "c3da5428731bf85da13e3aaa10f36a4407a4efc8deb232b0e473913b5237a7d6"
NATIVE_EXEC = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1" / "executor.py"
NATIVE_EXEC_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
BEST_CELL = "mixed-shrinkage-cell-438c09ad65eb4a22"
BASELINE_CELL = "mixed-shrinkage-cell-4e2c82330254b7ec"
BEST = {"candidate_id": "candidate-69720ac6257db007", "prepared_sha256": "2940f7680a4b0afec8aac68b669b89c0591133d7753066373a73161c1d56d513", "instruction_sha256": "2fc459fd4265c11a3bed56844be134ffe07555595add8a044797770ee5314629", "profile_sha256": "957fe772ee5095c05aec18dfd2e32a64d84eb30bf33e9560603bf14b98a242b7"}
BASELINE = {"candidate_id": "candidate-102cc7f06c9a99a7", "prepared_sha256": "1abf7b775cf6ec18a58d6b49561eb0273b287c74a0b029cb032e1f223447e22a", "instruction_sha256": "f318da394124d72dea4e9fb896d0345c6c5136d4839feae2cff1e389ea642de1", "profile_sha256": "3d90b5bdd1b1cd1673cc45b834485754eb0ee01f89e2c3c7ddf5d31e7d24c74f"}
TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]
PREPARED = frozenset({"parent-outbound-payload.json", "parent-instruction.bin", "parent-profile.json", "variant-brief.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
TERMINAL = frozenset({"launch-intent.json", "native-request.bin", "native-response.bin", "descendant-instruction.bin", "descendant-profile.json", "descendant-result.json", "runtime-identity.json", "effective-settings.json", "execution-receipt.json", "result.json"})
POSTWRITE_RECONCILE = "postwrite-reconcile.json"

VARIANTS = (
    ("baseline-local-evidence", "baseline", "Keep the baseline structure but make a minimal explicit local connective-evidence rule; do not use global intention or prose fluency as a substitute."),
    ("best-small-step", "best", "Take a deliberately smaller step than the parent: retain its calibrated behavior and make only one narrowly justified wording change."),
    ("halo-suppression", "best", "Suppress global intent, style, prestige, and fluency halos. Require dimension-specific local textual evidence before moving a score."),
    ("untouched-calibration", "best", "Change only the dimensions directly supported by local evidence; explicitly preserve calibration for untouched dimensions."),
    ("polarity-order", "baseline", "Make the rubric invariant to prompt polarity and presentation order while preserving dimension names, scale, and output schema."),
    ("symmetric-evidence", "best", "Use symmetric positive and negative evidence rules, avoiding midpoint defaults when the text supplies discriminating evidence."),
    ("paraphrase-binding", "baseline", "Bind score evidence to semantic content rather than surface wording so faithful paraphrases receive equivalent treatment."),
    ("conservative-hybrid", "best", "Combine local evidence, halo suppression, and untouched-dimension calibration conservatively; do not introduce a broad rewrite."),
    ("connective-hybrid", "baseline", "Use a conservative local-connective rule with symmetric counterevidence; preserve all unrelated dimensions exactly unless local evidence requires a change."),
    ("calibrated-paraphrase", "best", "Use paraphrase-tolerant evidence binding with a small learning-rate change and conservative calibration preservation."),
)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError(f"unsafe/reparsed path: {path}")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError(f"unexpected path type: {path}")


def _safe_ancestry(path: Path) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists(): _plain(current, directory=True)
    return absolute


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _disjoint(output: Path, source: Path, queue: Path) -> None:
    repo = _safe_ancestry(HERE.parents[1])
    if any(_under(left, right) or _under(right, left) for left, right in ((output, source), (output, queue), (output, repo))):
        raise ValueError("output root must stay disjoint from source, queue, and repository")


def _safe_output_root(output_root: Path, source_root: Path, queue_root: Path) -> Path:
    output, source, queue = _safe_ancestry(output_root), _safe_ancestry(source_root), _safe_ancestry(queue_root)
    if output.exists(): raise ValueError("output root must be fresh")
    _disjoint(output, source, queue)
    return output


def stable(path: Path) -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part; _plain(current, directory=current != path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("file changed during stable read")
    return raw


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict): raise ValueError(f"{label} must be an object")
    return value


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink(): raise ValueError(f"refuses overwrite: {path}")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _load_native() -> ModuleType:
    raw = stable(NATIVE_EXEC)
    if sha256(raw) != NATIVE_EXEC_SHA256: raise ValueError("pinned native Grok executor drifted")
    module = ModuleType("_hanna_f20_nextwave_native"); module.__file__ = str(NATIVE_EXEC); sys.modules[module.__name__] = module
    try: exec(compile(raw, str(NATIVE_EXEC), "exec"), module.__dict__)
    finally: sys.modules.pop(module.__name__, None)
    if stable(NATIVE_EXEC) != raw: raise ValueError("pinned native Grok executor changed during load")
    return module


def _public_result() -> dict[str, Any]:
    raw = stable(PUBLIC_RESULT); value = _json(raw, "published f20 result")
    if sha256(raw) != PUBLIC_RESULT_SHA256 or value.get("result_sha256") != PUBLIC_RESULT_INTERNAL_SHA256 or value.get("claim") != "DESCRIPTIVE_DEVELOPMENT_ONLY; strict v5 native projector rejects unproven-cardinality receipts; no general HANNA claim":
        raise ValueError("published f20 result commitment drifted")
    metric_ids = [row.get("candidate_id") for row in value.get("metrics", []) if isinstance(row, Mapping)]
    if metric_ids != [BEST["candidate_id"], "candidate-9863032916e37cd2", "candidate-f544c01ab3d15480", "candidate-16e5eb1904290c91", "candidate-3356cd7e47a87f71", "candidate-b3d9e8647959f744", "candidate-8369b42c182b3c3e", "candidate-c39b2d192fb3ed93", "candidate-e1fee4dbee8412ca", BASELINE["candidate_id"]]:
        raise ValueError("published f20 candidate ordering drifted")
    return value


def _profile(profile: Any) -> dict[str, Any]:
    required = {"demonstrations", "dimension_weights", "factors", "fixed_mapping", "format_version", "immutable_cwr_commitments", "instruction_sha256", "same_bytes_for_models", "sampler", "study_id"}
    if not isinstance(profile, dict) or set(profile) not in (required, required | {"version"}) or ("version" in profile and (not isinstance(profile["version"], str) or not profile["version"])):
        raise ValueError("profile geometry drifted")
    weights, factors, immutable, schema, sampler = profile["dimension_weights"], profile["factors"], profile["immutable_cwr_commitments"], profile["immutable_cwr_commitments"].get("response_schema") if isinstance(profile["immutable_cwr_commitments"], Mapping) else None, profile["sampler"]
    if profile["format_version"] != 1 or type(profile["demonstrations"]) is not int or profile["demonstrations"] < 0 or not isinstance(profile["fixed_mapping"], str) or not profile["fixed_mapping"] or not isinstance(profile["instruction_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", profile["instruction_sha256"]) or profile["same_bytes_for_models"] != ["gpt-5.6-sol", "grok-4.6"] or not isinstance(profile["study_id"], str):
        raise ValueError("profile scalar commitments drifted")
    if not isinstance(weights, Mapping) or set(weights) != set(DIMENSIONS) or any(type(value) not in (int, float) or isinstance(value, bool) or not (0 < value <= 1) for value in weights.values()):
        raise ValueError("profile dimension-weight geometry drifted")
    if not isinstance(factors, Mapping) or set(factors) != {"construct_framing", "human_reference_variant", "missing_evidence_not_no", "scope_materiality"} or any(not isinstance(value, str) or not value for value in factors.values()):
        raise ValueError("profile factors drifted")
    if not isinstance(immutable, Mapping) or set(immutable) != {"baseline_control_profile_sha256", "execution_contract_sha256", "mapping_sets_sha256", "response_schema", "runtime_source_manifest_sha256"} or any(not isinstance(immutable[key], str) or not re.fullmatch(r"[0-9a-f]{64}", immutable[key]) for key in ("baseline_control_profile_sha256", "execution_contract_sha256", "mapping_sets_sha256", "runtime_source_manifest_sha256")):
        raise ValueError("profile immutable commitments drifted")
    if not isinstance(schema, Mapping) or schema != {"dimensions": list(DIMENSIONS), "format_version": 1, "score_type": "finite_numeric_per_dimension"}:
        raise ValueError("profile response-schema geometry drifted")
    if not isinstance(sampler, Mapping) or set(sampler) != {"algorithm", "seed", "temperature"} or not isinstance(sampler["algorithm"], str) or type(sampler["seed"]) is not int or type(sampler["temperature"]) not in (int, float) or isinstance(sampler["temperature"], bool) or sampler["temperature"] != 0:
        raise ValueError("profile sampler drifted")
    return dict(profile)


def _descendant_profile(profile: Any, parent_profile: bytes) -> dict[str, Any]:
    candidate, parent = _profile(profile), _profile(_json(parent_profile, "frozen parent profile"))
    immutable = ("demonstrations", "dimension_weights", "fixed_mapping", "immutable_cwr_commitments", "same_bytes_for_models", "sampler", "study_id", "format_version", "version")
    for field in immutable:
        if candidate.get(field) != parent.get(field): raise ValueError(f"descendant changed immutable profile field: {field}")
    if set(candidate["factors"]) != set(parent["factors"]): raise ValueError("descendant factor geometry drifted")
    return candidate


def _six_dimension_schema(value: Any) -> None:
    if not isinstance(value, Mapping) or value.get("format_version") != 1 or value.get("type") != "object" or value.get("additionalProperties") is not False or set(value.get("required", [])) != {"scores", "evidence", "coverage"} or set(value.get("properties", {})) != {"scores", "evidence", "coverage"}:
        raise ValueError("outbound six-dimension schema geometry drifted")
    for field, expected_type in (("scores", "number"), ("evidence", "string"), ("coverage", "boolean")):
        item = value["properties"][field]
        if not isinstance(item, Mapping) or item.get("type") != "object" or item.get("additionalProperties") is not False or set(item.get("required", [])) != set(DIMENSIONS) or set(item.get("properties", {})) != set(DIMENSIONS):
            raise ValueError("outbound dimension field geometry drifted")
        for dimension in DIMENSIONS:
            descriptor = item["properties"][dimension]
            if not isinstance(descriptor, Mapping) or descriptor.get("type") != expected_type: raise ValueError("outbound dimension type drifted")
            if field == "scores" and (descriptor.get("minimum") != 0 or descriptor.get("maximum") != 5): raise ValueError("outbound score scale drifted")
            if field == "evidence" and descriptor.get("minLength") != 1: raise ValueError("outbound evidence rule drifted")


def _parent(source_root: Path, name: str, pinned: Mapping[str, str]) -> tuple[bytes, bytes, dict[str, Any]]:
    root = Path(source_root) / name; prepared_raw = stable(root / "prepared.json")
    if sha256(prepared_raw) != pinned["prepared_sha256"]: raise ValueError("parent prepared bytes drifted")
    prepared = _json(prepared_raw, "parent prepared record"); cell = prepared.get("cell"); payload_raw = stable(root / "outbound-payload.json"); payload = _json(payload_raw, "parent outbound payload")
    if not isinstance(cell, Mapping) or cell.get("candidate_id") != pinned["candidate_id"] or cell.get("candidate_instruction_sha256") != pinned["instruction_sha256"] or cell.get("candidate_profile_sha256") != pinned["profile_sha256"]:
        raise ValueError("parent candidate identity drifted")
    if cell.get("payload_sha256") != sha256(payload_raw) or prepared.get("outbound_payload_sha256") != sha256(payload_raw):
        raise ValueError("parent outbound payload commitment drifted")
    try: embedded = base64.b64decode(str(cell["payload_base64"]), validate=True)
    except (KeyError, ValueError, TypeError) as error: raise ValueError("parent embedded payload binding drifted") from error
    if embedded != payload_raw:
        raise ValueError("parent prepared payload_base64 differs from outbound payload")
    _six_dimension_schema(payload.get("response_schema"))
    instruction, profile = payload.get("instruction"), payload.get("profile")
    if not isinstance(instruction, str) or sha256(instruction.encode("utf-8")) != pinned["instruction_sha256"]:
        raise ValueError("parent instruction/profile bytes drifted")
    profile = _profile(profile)
    # The prepared candidate-profile commitment is distinct from the exact profile embedded in its frozen outbound payload.
    return instruction.encode("utf-8"), compact(profile), {"cell_id": name, **dict(pinned), "outbound_payload_sha256": sha256(payload_raw), "outbound_profile_sha256": sha256(compact(profile)), "outbound_payload_base64": base64.b64encode(payload_raw).decode("ascii")}


def _schema() -> bytes:
    return canonical({"$schema_version": 1, "type": "object", "additionalProperties": False, "required": ["instruction", "profile", "change_summary"], "properties": {"instruction": {"type": "string", "minLength": 1}, "profile": {"type": "object"}, "change_summary": {"type": "string", "minLength": 1}}})


def _catalog(source_root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    _public_result()
    parents = {}
    for parent_name, pin in (("baseline", BASELINE), ("best", BEST)):
        instruction, profile, provenance = _parent(source_root, BASELINE_CELL if parent_name == "baseline" else BEST_CELL, pin)
        parents[parent_name] = {"instruction": instruction, "profile": profile, "provenance": provenance, "outbound_payload": base64.b64decode(provenance["outbound_payload_base64"], validate=True)}
    rows = []
    for ordinal, (slug, parent_name, brief) in enumerate(VARIANTS, 1):
        row = {"cell_id": f"nextwave-{ordinal:02d}-{slug}", "ordinal": ordinal, "variant_id": slug, "parent": parent_name, "brief": brief}
        prompt = _prompt(row, parents[parent_name]); row["prompt_sha256"] = sha256(prompt); row["brief_sha256"] = sha256(canonical({"variant_id": slug, "brief": brief, "parent": parent_name})); rows.append(row)
    if len(rows) != 10 or len({row["cell_id"] for row in rows}) != 10 or len({row["brief_sha256"] for row in rows}) != 10 or len({row["prompt_sha256"] for row in rows}) != 10:
        raise ValueError("next-wave catalog is not ten distinct generation cells")
    return rows, parents


def _prompt(row: Mapping[str, Any], parent: Mapping[str, Any]) -> bytes:
    value = {"format_version": 1, "study_id": STUDY_ID, "task": "Generate one versioned HANNA instruction/profile descendant.", "constraints": ["Return JSON matching the supplied schema.", "Preserve the fixed six dimensions and exact score scale.", "Make the stated change only; do not add demonstrations, tools, web, planning, or new scoring dimensions.", "The descendant instruction/profile pair must not be byte-identical to the parent pair.", "This is candidate generation only: do not claim a result, selection, promotion, runtime authority, confirmation, or general HANNA gain."], "variant": {"id": row["variant_id"], "brief": row["brief"]}, "parent": {"instruction": parent["instruction"].decode("utf-8"), "profile": json.loads(parent["profile"].decode("utf-8")), "provenance": parent["provenance"]}}
    return canonical(value)


def _route(queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    route, evidence = (route_provider or _load_native().validate_live_grok_route)(Path(queue_root))
    required = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high"}
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or any(route.get(key) != value for key, value in required.items()) or len(route.get("grok_command", [])) != 1 or "public_repo" not in route.get("allowed_payload_classes", []):
        raise ValueError("current governed Grok route is unsuitable")
    return dict(route), dict(evidence)


def _files(row: Mapping[str, Any], parent: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement): raise ValueError("acknowledgement must be lowercase SHA-256")
    prompt, schema = _prompt(row, parent), _schema(); brief = {"format_version": 1, "study_id": STUDY_ID, "cell_id": row["cell_id"], "variant_id": row["variant_id"], "brief": row["brief"], "parent": row["parent"]}
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": row["cell_id"], "destination": route["destination"], "route": route, "route_evidence": evidence, "payload": {"bytes": len(prompt), "sha256": sha256(prompt), "text": prompt.decode("utf-8")}, "response_schema": {"bytes": len(schema), "sha256": sha256(schema), "text": schema.decode("utf-8")}, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "provider_calls_made": 0, "process_launches": 0}
    ack = {"format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha256(disclosure)}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "cell_id": row["cell_id"], "route": route, "route_evidence": evidence, "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "f20_nextwave_grok_candidate_preparation", "cell": dict(row), "source": {"public_result_commit": PUBLIC_RESULT_COMMIT, "public_result_sha256": PUBLIC_RESULT_SHA256, "public_result_internal_sha256": PUBLIC_RESULT_INTERNAL_SHA256, "parent": parent["provenance"]}, "parent_outbound_payload_sha256": sha256(parent["outbound_payload"]), "parent_instruction_sha256": sha256(parent["instruction"]), "parent_profile_sha256": sha256(parent["profile"]), "prompt_request_sha256": sha256(prompt), "response_schema_sha256": sha256(schema), "disclosure_sha256": sha256(disclosure), "authorization_sha256": sha256(ack), "route_proof_sha256": sha256(proof), "route": route, "route_evidence": evidence, "tools_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    return {"parent-outbound-payload.json": parent["outbound_payload"], "parent-instruction.bin": parent["instruction"], "parent-profile.json": parent["profile"], "variant-brief.json": canonical(brief), "prompt-request.bin": prompt, "response-schema.json": schema, "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(ack), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def _inventory(root: Path, *, completed: bool = False) -> set[str]:
    _plain(root, directory=True); entries = {item.name: item for item in root.iterdir()}
    expected_root = set(PREPARED) | (set(TERMINAL) | {"responses"} if completed else set())
    if set(entries) != expected_root: raise ValueError("root inventory has missing or extra artifacts")
    for name, item in entries.items():
        _plain(item, directory=name == "responses")
    if completed:
        responses = entries.get("responses")
        expected = {"batch-0001.attempt-0001.prompt.txt", "batch-0001.attempt-0001.grok.envelope.json"}
        if responses is None or {item.name for item in responses.iterdir()} != expected: raise ValueError("runner response artifacts drifted")
        for item in responses.iterdir(): _plain(item, directory=False)
    return set(entries)


def _top_inventory(root: Path, rows: list[Mapping[str, Any]]) -> None:
    _plain(root, directory=True)
    expected = {"catalog.json", *(str(row["cell_id"]) for row in rows)}
    entries = {item.name: item for item in root.iterdir()}
    if set(entries) != expected: raise ValueError("top-level output inventory has missing or extra artifacts")
    for name, item in entries.items(): _plain(item, directory=name != "catalog.json")


def _verify(root: Path, row: Mapping[str, Any], parent: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> tuple[dict[str, Any], bytes]:
    if _inventory(root) != set(PREPARED): raise ValueError("prepared root is not pristine")
    expected = _files(row, parent, route, evidence, acknowledgement)
    if any(stable(root / name) != raw for name, raw in expected.items()): raise ValueError("prepared bytes drifted")
    return _json(expected["prepared.json"], "prepared record"), expected["prompt-request.bin"]


def _manifest(rows: list[dict[str, Any]], parents: Mapping[str, Mapping[str, Any]], source_root: Path) -> dict[str, Any]:
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "ten_distinct_f20_nextwave_generation_catalog", "public_result_commit": PUBLIC_RESULT_COMMIT, "public_result_sha256": PUBLIC_RESULT_SHA256, "source_root": str(Path(source_root)), "parents": {name: value["provenance"] for name, value in parents.items()}, "cells": rows, "aliases": [], "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}
    manifest["manifest_sha256"] = sha256(manifest); return manifest


def prepare_all(*, output_root: Path, source_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    source, queue = _safe_ancestry(Path(source_root)), _safe_ancestry(Path(queue_root)); root = _safe_output_root(Path(output_root), source, queue)
    rows, parents = _catalog(source); route, evidence = _route(queue, route_provider)
    root.mkdir(parents=True, exist_ok=False); _plain(root, directory=True)
    manifest = _manifest(rows, parents, Path(source_root)); _write_new(root / "catalog.json", canonical(manifest))
    for row in rows:
        cell = root / row["cell_id"]; cell.mkdir(); _plain(cell, directory=True)
        for name, raw in _files(row, parents[row["parent"]], route, evidence, authorization_acknowledgement_sha256).items(): _write_new(cell / name, raw)
        _verify(cell, row, parents[row["parent"]], route, evidence, authorization_acknowledgement_sha256)
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_ten_f20_nextwave_grok_generation_cells", "prepared_cells": [row["cell_id"] for row in rows], "aliases": 0, "provider_calls_made": 0, "process_launches": 0, "evidence_ceiling": "provisional_candidate_generation_only"}


def _default_runner(*, prompt: bytes, schema_path: Path, output_dir: Path, route: Mapping[str, Any], before_contact: Callable[[], None]) -> dict[str, Any]:
    native = _load_native()
    content, record = native._load_call_grok()(executable=route["grok_command"][0], model="grok-4.6", reasoning="high", prompt=prompt.decode("utf-8"), output_dir=output_dir, response_schema=schema_path, batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, allow_unattested_reasoning=True, system_prompt_override="Generate an isolated structured descendant. Do not use memory, tools, web, plans, or subagents.", before_provider_attempt=before_contact)
    raw = stable(output_dir / "responses" / "batch-0001.attempt-0001.grok.envelope.json"); request_id, session_id = native._envelope_identity(raw, record)
    if not isinstance(content, str): raise ValueError("Grok returned nontext content")
    identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": request_id, "session_id": session_id, "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": "Generate an isolated structured descendant. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
    return {"native_request_bytes": canonical({"prompt": prompt.decode("utf-8")}).rstrip(b"\n"), "native_response_bytes": raw, "content": content.encode("utf-8"), "identity": identity, "effective_settings": settings}


def _validate_runner(value: Any, route: Mapping[str, Any], prompt: bytes, parent_profile: bytes) -> tuple[bytes, bytes, bytes, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not isinstance(value, Mapping) or set(value) != {"native_request_bytes", "native_response_bytes", "content", "identity", "effective_settings"}: raise ValueError("runner result shape drifted")
    request, response, content, identity, settings = value["native_request_bytes"], value["native_response_bytes"], value["content"], value["identity"], value["effective_settings"]
    if not all(isinstance(item, bytes) for item in (request, response, content)) or not isinstance(identity, Mapping) or not isinstance(settings, Mapping): raise ValueError("runner result types drifted")
    required_identity = {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}
    if any(identity.get(key) != expected for key, expected in required_identity.items()) or any(not isinstance(identity.get(key), str) or not identity[key] for key in ("request_id", "session_id")): raise ValueError("runner identity drifted")
    expected_settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": "Generate an isolated structured descendant. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
    if dict(settings) != expected_settings: raise ValueError("effective settings drifted")
    envelope = _json(response, "native Grok envelope")
    if envelope.get("requestId") != identity["request_id"] or envelope.get("sessionId") != identity["session_id"]: raise ValueError("response identity is misassociated")
    descendant = _json(content, "Grok descendant")
    if set(descendant) != {"instruction", "profile", "change_summary"} or not isinstance(descendant["instruction"], str) or not descendant["instruction"].strip() or not isinstance(descendant["profile"], dict) or not isinstance(descendant["change_summary"], str) or not descendant["change_summary"].strip(): raise ValueError("descendant response semantics drifted")
    if envelope.get("structuredOutput") != descendant: raise ValueError("native envelope structured output differs from descendant bytes")
    profile = _descendant_profile(descendant["profile"], parent_profile)
    if profile["instruction_sha256"] != sha256(descendant["instruction"].encode("utf-8")): raise ValueError("descendant profile instruction commitment drifted")
    return request, response, content, dict(identity), dict(settings), descendant


def _terminal(root: Path, row: Mapping[str, Any], kind: str, detail: str, launches: int, intent: Mapping[str, Any] | None) -> dict[str, Any]:
    result_path = root / "result.json"
    if result_path.exists(): return _json(stable(result_path), "terminal result")
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": kind, "cell_id": row["cell_id"], "detail": detail, "provider_calls_made": 0 if launches == 0 else None, "process_launches": launches, "native_endpoint_contact_cardinality": "zero" if launches == 0 else "unknown", "intent_sha256": sha256(intent) if intent else None, "retry_policy": "fresh_output_root_required_no_in_place_resend"}
    _write_new(result_path, canonical(result)); return result


def _completed_records(row: Mapping[str, Any], prepared: Mapping[str, Any], intent: Mapping[str, Any], prompt_artifact: bytes, request: bytes, response: bytes, content: bytes, descendant: Mapping[str, Any], identity: Mapping[str, Any], settings: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_candidate_generation_receipt_cardinality_unproven", "cell": dict(row), "prepared_sha256": sha256(prepared), "launch_intent_sha256": sha256(intent), "prompt_sha256": sha256(prompt_artifact), "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "descendant_result_sha256": sha256(content), "descendant_instruction_sha256": sha256(descendant["instruction"].encode("utf-8")), "descendant_profile_sha256": sha256(compact(descendant["profile"])), "change_summary_sha256": sha256(descendant["change_summary"].encode("utf-8")), "runner_prompt_artifact_sha256": sha256(prompt_artifact), "effective_settings_sha256": sha256(settings), "identity": dict(identity), "identity_sha256": sha256(identity), "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "provisional_grok_candidate_generation_received", "cell_id": row["cell_id"], "receipt_sha256": sha256(receipt), "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven", "authority": "none"}
    return receipt, result


def execute_one(*, output_root: Path, cell_id: str, source_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("explicit allow_remote=True is required")
    source, queue, output = _safe_ancestry(Path(source_root)), _safe_ancestry(Path(queue_root)), _safe_ancestry(Path(output_root)); _disjoint(output, source, queue)
    rows, parents = _catalog(source); _top_inventory(output, rows); matches = [row for row in rows if row["cell_id"] == cell_id]
    if len(matches) != 1: raise ValueError("unknown next-wave cell")
    row = matches[0]; root = output / cell_id
    if any((root / name).exists() for name in ("launch-intent.json", "result.json", POSTWRITE_RECONCILE)): raise ValueError("no resend; use a fresh output root")
    route, evidence = _route(queue, route_provider); prepared, prompt = _verify(root, row, parents[row["parent"]], route, evidence, authorization_acknowledgement_sha256)
    intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_grok_candidate_generation", "cell_id": cell_id, "prepared_sha256": sha256(prepared), "prompt_sha256": sha256(prompt), "native_contact_proven": False}
    launches = 0
    def before_contact() -> None:
        nonlocal launches
        if launches: raise ValueError("runner signalled more than one contact")
        fresh_route, fresh_evidence = _route(queue, route_provider)
        if fresh_route != route or fresh_evidence != evidence: raise ValueError("route drifted adjacent to launch")
        _write_new(root / "launch-intent.json", canonical(intent)); launches = 1
    try:
        value = (runner or _default_runner)(prompt=prompt, schema_path=root / "response-schema.json", output_dir=root, route=route, before_contact=before_contact)
    except BaseException as error:
        return _terminal(root, row, "definitely_not_contacted" if launches == 0 else "reconcile_required_after_process_launch", type(error).__name__, launches, intent if launches else None)
    if launches != 1: return _terminal(root, row, "definitely_not_contacted", "runner_returned_without_contact_callback", 0, None)
    try:
        parent = parents[row["parent"]]
        request, response, content, identity, settings, descendant = _validate_runner(value, route, prompt, parent["profile"])
        if request != canonical({"prompt": prompt.decode("utf-8")}).rstrip(b"\n"): raise ValueError("native request differs from frozen prompt")
        if descendant["instruction"].encode("utf-8") == parent["instruction"] and compact(descendant["profile"]) == parent["profile"]: raise ValueError("parent-identical descendant is rejected")
        descendant_instruction, descendant_profile = descendant["instruction"].encode("utf-8"), compact(descendant["profile"])
        if not descendant_instruction or not descendant_profile: raise ValueError("empty descendant")
        for name, raw in (("native-request.bin", request), ("native-response.bin", response), ("descendant-instruction.bin", descendant_instruction), ("descendant-profile.json", descendant_profile), ("descendant-result.json", content), ("runtime-identity.json", canonical(identity)), ("effective-settings.json", canonical(settings))): _write_new(root / name, raw)
        prompt_artifact = root / "responses" / "batch-0001.attempt-0001.prompt.txt"
        if stable(prompt_artifact) != prompt: raise ValueError("real runner prompt artifact drifted")
        receipt, result = _completed_records(row, prepared, intent, prompt_artifact.read_bytes(), request, response, content, descendant, identity, settings)
        _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical(result)); _inventory(root, completed=True)
        return {"cell_id": cell_id, "state": "provisional_candidate_received", "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    except BaseException as error:
        if (root / "result.json").exists():
            prior = _json(stable(root / "result.json"), "prior result"); marker = {"format_version": 1, "study_id": STUDY_ID, "kind": "postwrite_reconcile_required", "cell_id": cell_id, "supersedes_result_sha256": sha256(prior), "detail": type(error).__name__, "retry_policy": "fresh_output_root_required_no_in_place_resend"}
            if not (root / POSTWRITE_RECONCILE).exists(): _write_new(root / POSTWRITE_RECONCILE, canonical(marker))
            return marker
        return _terminal(root, row, "reconcile_required_after_process_launch", type(error).__name__, 1, intent)


async def execute_wave(*, output_root: Path, source_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows, _parents = _catalog(Path(source_root)); gate = asyncio.Semaphore(10)
    async def run(row: Mapping[str, Any]) -> dict[str, Any]:
        async with gate:
            return await asyncio.to_thread(execute_one, output_root=output_root, source_root=source_root, queue_root=queue_root, authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=allow_remote, route_provider=route_provider, runner=runner, cell_id=row["cell_id"])
    return list(await asyncio.gather(*(run(row) for row in rows)))


def reconcile_all(*, output_root: Path, source_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    """Reparse all ten completed roots without provider, route, or resend activity."""
    source, queue, root = _safe_ancestry(Path(source_root)), _safe_ancestry(Path(queue_root)), _safe_ancestry(Path(output_root)); _disjoint(root, source, queue)
    rows, parents = _catalog(source); _top_inventory(root, rows); expected_catalog = _manifest(rows, parents, source); actual_catalog_raw = stable(root / "catalog.json")
    if actual_catalog_raw != canonical(expected_catalog): raise ValueError("catalog reparse drifted")
    seen_contacts: set[tuple[str, str]] = set(); seen_descendants: set[tuple[str, str]] = set()
    for row in rows:
        cell_root = root / row["cell_id"]; _inventory(cell_root, completed=True)
        prepared = _json(stable(cell_root / "prepared.json"), "prepared record"); route, evidence = prepared.get("route"), prepared.get("route_evidence")
        ack = _json(stable(cell_root / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
        if ack != authorization_acknowledgement_sha256 or not isinstance(route, Mapping) or not isinstance(evidence, Mapping): raise ValueError("prepared acknowledgement or route drifted")
        expected = _files(row, parents[row["parent"]], route, evidence, ack)
        if any(stable(cell_root / name) != raw for name, raw in expected.items()): raise ValueError("prepared artifact reparse drifted")
        prompt, runner_prompt = stable(cell_root / "prompt-request.bin"), stable(cell_root / "responses" / "batch-0001.attempt-0001.prompt.txt")
        if runner_prompt != prompt: raise ValueError("persisted runner prompt differs from frozen prompt-request")
        request, response, content, identity, settings, descendant = _validate_runner({"native_request_bytes": stable(cell_root / "native-request.bin"), "native_response_bytes": stable(cell_root / "native-response.bin"), "content": stable(cell_root / "descendant-result.json"), "identity": _json(stable(cell_root / "runtime-identity.json"), "identity"), "effective_settings": _json(stable(cell_root / "effective-settings.json"), "settings")}, route, prompt, parents[row["parent"]]["profile"])
        intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_grok_candidate_generation", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared), "prompt_sha256": sha256(prompt), "native_contact_proven": False}
        if stable(cell_root / "launch-intent.json") != canonical(intent) or request != canonical({"prompt": prompt.decode("utf-8")}).rstrip(b"\n") or stable(cell_root / "descendant-instruction.bin") != descendant["instruction"].encode("utf-8") or stable(cell_root / "descendant-profile.json") != compact(descendant["profile"]): raise ValueError("persisted launch/descendant binding drifted")
        contact = (identity["request_id"], identity["session_id"]); descendant_pair = (sha256(stable(cell_root / "descendant-instruction.bin")), sha256(stable(cell_root / "descendant-profile.json")))
        if contact in seen_contacts or descendant_pair in seen_descendants: raise ValueError("duplicate contact or descendant across next-wave roots")
        seen_contacts.add(contact); seen_descendants.add(descendant_pair)
        expected_receipt, expected_result = _completed_records(row, prepared, intent, runner_prompt, request, response, content, descendant, identity, settings)
        if stable(cell_root / "execution-receipt.json") != canonical(expected_receipt) or stable(cell_root / "result.json") != canonical(expected_result): raise ValueError("receipt/result binding drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "reconciled_ten_provisional_grok_descendants", "cells": 10, "provider_calls_made": 0, "process_launches": 0, "native_endpoint_contact_cardinality": "unproven", "authority": "none"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare-all", action="store_true"); mode.add_argument("--execute-one", action="store_true"); mode.add_argument("--execute-wave", action="store_true"); mode.add_argument("--reconcile-all", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--source-root", type=Path, required=True); parser.add_argument("--queue-root", type=Path, required=True); parser.add_argument("--authorization-acknowledgement-sha256", required=True); parser.add_argument("--cell-id"); parser.add_argument("--allow-remote", action="store_true"); args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "source_root": args.source_root, "queue_root": args.queue_root, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
    if args.prepare_all:
        if args.allow_remote: parser.error("prepare-all forbids --allow-remote")
        result = prepare_all(**common)
    elif args.execute_one:
        if not args.allow_remote or not args.cell_id: parser.error("execute-one requires --allow-remote and --cell-id")
        result = execute_one(**common, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote: parser.error("execute-wave requires --allow-remote")
        result = asyncio.run(execute_wave(**common, allow_remote=True))
    else:
        if args.allow_remote: parser.error("reconcile-all forbids --allow-remote")
        result = reconcile_all(output_root=args.output_root, source_root=args.source_root, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
