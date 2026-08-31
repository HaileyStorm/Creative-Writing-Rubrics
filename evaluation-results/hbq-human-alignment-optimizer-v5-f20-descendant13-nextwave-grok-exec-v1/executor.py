#!/usr/bin/env python3
"""One-shot, tool-free Grok generation from the published descendant-13 profile."""
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
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-exec-v1"
PARENT_COMMIT = "1a432fbf3cc82a42d80c11dceca1f5b4c29d4e85"
PARENT_RELATIVE = "evaluation-results/hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1/profile.json"
PARENT_VERIFY_RELATIVE = "evaluation-results/hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1/verify.py"
PARENT_FILE_SHA256 = "0b9b7b7417c37534689ef3c159e7de1d7cc7a6eb0fb593e4f671a5e2686e9f28"
PARENT_VERIFY_SHA256 = "5c557308c6e724a17d43687a5958f7a901874e8872c3378043021ae467f86a6a"
PARENT_CANDIDATE_ID = "broader-nextwave-13-missing_evidence_not_no"
PARENT_CANDIDATE_SHA256 = "d8e55620d3a91ac17762d9ac40f7be3bb8aa87a478d6593f6ebda906d28b4684"
PREDECESSOR_COMMIT = "544af81c20b24545aca9d12e9ab3c4ced2a183f2"
PREDECESSOR_RELATIVE = "evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-grok-exec-v1/executor.py"
PREDECESSOR_SHA256 = "6c34f0a42db0e06ff717d28a1f80d5c943d4d19d6deb6d6a912ff4e1fbe588e1"
PREDECESSOR_EXECUTOR = REPO / PREDECESSOR_RELATIVE
DEFAULT_PARENT_PROFILE = REPO / PARENT_RELATIVE
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ACK_RE = re.compile(r"[0-9a-f]{64}")
PREPARED = frozenset({"parent-profile.json", "parent-outbound-payload.json", "variant-brief.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]
SYSTEM_PROMPT = "Generate an isolated structured descendant. Do not use memory, tools, web, plans, or subagents."
ROUTE_LOCK = threading.Lock()
PREDECESSOR_LOCK = threading.Lock()
PREDECESSOR_CACHE: ModuleType | None = None

KNOWN_TESTED_MECHANISMS = frozenset({
    "local_evidence", "small_step", "halo_suppression", "untouched_calibration", "polarity_order",
    "symmetric_evidence", "paraphrase_binding", "conservative_hybrid", "connective_hybrid",
    "calibrated_paraphrase", "missing_evidence_not_no", "construct_framing", "human_reference_variant",
    "scope_materiality",
})

VARIANTS = (
    ("scale-adjacency", "all", "adjacent_anchor_boundary", "Use adjacent one-to-five rubric anchors to distinguish a score from its immediate neighbours; state the boundary that separates them."),
    ("speaker-attribution", "Coherence", "speaker_viewpoint_attribution", "Resolve who is speaking, feeling, or acting before rating; never assign a character's view to narration or vice versa."),
    ("temporal-causality-separation", "Coherence", "temporal_causal_relation", "Keep chronological sequence distinct from causal linkage when evaluating whether the writing hangs together."),
    ("surprise-reversal-specificity", "Surprise", "reversal_disclosure", "For Surprise, distinguish a disclosed reversal from information that is merely delayed; do not treat delay alone as a reversal."),
    ("complexity-interrelation", "Complexity", "relational_structure", "For Complexity, distinguish multiple topics from meaningful relations among topics; topic count alone does not establish complexity."),
    ("relevance-task-binding", "Relevance", "task_objective_binding", "For Relevance, bind the score to the stated task or scene objective rather than to the most prominent sentence."),
    ("empathy-perspective-distinction", "Empathy", "emotion_perspective", "For Empathy, distinguish depicting an emotion from enabling perspective-taking by the reader."),
    ("engagement-stakes-distinction", "Engagement", "stakes_duration", "For Engagement, distinguish momentary attention cues from sustained stakes or curiosity across the passage."),
    ("coherence-reference-resolution", "Coherence", "referent_resolution", "Resolve ambiguous pronouns and referents before judging continuity; an unresolved reference is not the same mechanism as a missing causal link."),
    ("rhetorical-question-disambiguation", "Engagement", "rhetorical_function", "Treat rhetorical questions as a structural device, not automatically as reader engagement or uncertainty."),
)


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


def stable(path: Path) -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists(): _plain(current, directory=current != path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("file changed during stable read")
    return raw


def _safe_ancestry(path: Path) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists(): _plain(current, directory=True)
    return absolute


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _safe_output_root(output_root: Path, queue_root: Path, *, fresh: bool) -> Path:
    output, queue = _safe_ancestry(output_root), _safe_ancestry(queue_root)
    if _under(output, REPO) or _under(output, queue) or _under(queue, output):
        raise ValueError("output root must be disjoint from repository and queue")
    if fresh and output.exists(): raise ValueError("output root must be fresh")
    if not fresh and not output.exists(): raise ValueError("output root is absent")
    return output


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict): raise ValueError(f"{label} must be an object")
    return value


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink(): raise ValueError(f"refuses overwrite: {path}")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _blob(commit: str, relative: str) -> bytes:
    import subprocess
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode: raise ValueError("pinned Git blob is absent")
    return result.stdout


def _load_predecessor() -> ModuleType:
    global PREDECESSOR_CACHE
    # The pinned module is dynamically loaded for its descendant-profile gate;
    # serialize the temporary sys.modules registration across ten worker threads.
    with PREDECESSOR_LOCK:
        raw = stable(PREDECESSOR_EXECUTOR)
        if sha256(raw) != PREDECESSOR_SHA256:
            raise ValueError("pinned predecessor executor drifted")
        if PREDECESSOR_CACHE is not None: return PREDECESSOR_CACHE
        if _blob(PREDECESSOR_COMMIT, PREDECESSOR_RELATIVE) != raw: raise ValueError("pinned predecessor executor commitment drifted")
        module = ModuleType("_desc13_nextwave_predecessor"); module.__file__ = str(PREDECESSOR_EXECUTOR); sys.modules[module.__name__] = module
        try: exec(compile(raw, str(PREDECESSOR_EXECUTOR), "exec"), module.__dict__)
        finally: sys.modules.pop(module.__name__, None)
        PREDECESSOR_CACHE = module
        return PREDECESSOR_CACHE


def _parent(parent_profile: Path) -> dict[str, Any]:
    path = Path(parent_profile)
    try: raw = stable(path)
    except OSError as error: raise ValueError("published parent profile drifted") from error
    if sha256(raw) != PARENT_FILE_SHA256 or _blob(PARENT_COMMIT, PARENT_RELATIVE) != raw:
        raise ValueError("published parent profile drifted")
    verify = REPO / PARENT_VERIFY_RELATIVE
    if sha256(stable(verify)) != PARENT_VERIFY_SHA256 or _blob(PARENT_COMMIT, PARENT_VERIFY_RELATIVE) != stable(verify):
        raise ValueError("published parent verifier drifted")
    outer = _json(raw, "published parent profile")
    candidate, instruction, profile = outer.get("candidate"), outer.get("instruction"), outer.get("profile")
    if not isinstance(candidate, Mapping) or candidate.get("candidate_id") != PARENT_CANDIDATE_ID or candidate.get("candidate_sha256") != PARENT_CANDIDATE_SHA256 or not isinstance(instruction, str) or not isinstance(profile, Mapping):
        raise ValueError("published parent identity drifted")
    if outer.get("instruction_sha256") != sha256(instruction.encode("utf-8")) or outer.get("profile_sha256") != sha256(compact(profile)):
        raise ValueError("published parent direct bytes drifted")
    judge_schema = profile.get("immutable_cwr_commitments", {}).get("response_schema") if isinstance(profile.get("immutable_cwr_commitments"), Mapping) else None
    if judge_schema != {"dimensions": list(DIMENSIONS), "format_version": 1, "score_type": "finite_numeric_per_dimension"}:
        raise ValueError("published parent judge schema drifted")
    six_dimension_schema = {"format_version": 1, "type": "object", "additionalProperties": False, "required": ["scores", "evidence", "coverage"], "properties": {field: {"type": "object", "additionalProperties": False, "required": list(DIMENSIONS), "properties": {dimension: ({"type": "number", "minimum": 0, "maximum": 5} if field == "scores" else {"type": "string", "minLength": 1} if field == "evidence" else {"type": "boolean"}) for dimension in DIMENSIONS}} for field in ("scores", "evidence", "coverage")}}
    payload = canonical({"format_version": 1, "instruction": instruction, "profile": profile, "response_schema": six_dimension_schema})
    if sha256(payload) != "e48306dd4e4037a2cb2fa3553ec9287c18f496837b818ab097b59fc382a8f9e1": raise ValueError("published parent outbound payload drifted")
    return {"outer": outer, "instruction": instruction.encode("utf-8"), "profile": compact(profile), "payload": payload, "generator_schema": canonical(_generator_schema_value()), "provenance": {"commit": PARENT_COMMIT, "relative_path": PARENT_RELATIVE, "file_sha256": PARENT_FILE_SHA256, "candidate_id": PARENT_CANDIDATE_ID, "candidate_sha256": PARENT_CANDIDATE_SHA256, "instruction_sha256": outer["instruction_sha256"], "profile_sha256": outer["profile_sha256"], "outbound_payload_sha256": sha256(payload)}}


def _catalog(parent: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for ordinal, (slug, target_dimension, mechanism_family, brief) in enumerate(VARIANTS, 1):
        semantic_label = slug.replace("-", "_")
        if semantic_label in KNOWN_TESTED_MECHANISMS: raise ValueError("candidate mechanism repeats a tested factor")
        row = {"cell_id": f"descendant13-nextwave-{ordinal:02d}-{slug}", "ordinal": ordinal, "variant_id": slug, "semantic_label": semantic_label, "target_dimension": target_dimension, "mechanism_family": mechanism_family, "semantic_intent": f"Evaluate {target_dimension} through {mechanism_family}; this is distinct from every prior factor family.", "brief": brief}
        row["brief_sha256"] = sha256(canonical({"variant_id": slug, "brief": brief}))
        row["prompt_sha256"] = sha256(_prompt(row, parent))
        rows.append(row)
    pairs = {(row["target_dimension"], row["mechanism_family"]) for row in rows}
    if len(rows) != 10 or len({row["cell_id"] for row in rows}) != 10 or len({row["brief_sha256"] for row in rows}) != 10 or len({row["prompt_sha256"] for row in rows}) != 10 or {row["semantic_label"] for row in rows} & KNOWN_TESTED_MECHANISMS or len(pairs) != 10:
        raise ValueError("catalog must contain ten nonduplicate candidates")
    return rows


def _prompt(row: Mapping[str, Any], parent: Mapping[str, Any]) -> bytes:
    return canonical({"format_version": 1, "study_id": STUDY_ID, "task": "Generate one conservative HANNA instruction/profile descendant.", "constraints": ["Return JSON matching the supplied generator schema.", "Preserve the fixed six dimensions, scale, demonstrations, sampler, mapping, and judge schema.", "Apply the stated brief only; do not add tools, web, plans, examples, or scoring dimensions.", "Do not claim a result, selection, promotion, runtime authority, confirmation, or general HANNA gain."], "response_schema": json.loads(parent["generator_schema"].decode("utf-8")), "variant": {"id": row["variant_id"], "target_dimension": row["target_dimension"], "mechanism_family": row["mechanism_family"], "semantic_intent": row["semantic_intent"], "brief": row["brief"]}, "parent": {"outbound_payload": json.loads(parent["payload"].decode("utf-8")), "provenance": parent["provenance"]}})


def _generator_schema_value() -> dict[str, Any]:
    return {"$schema_version": 1, "type": "object", "additionalProperties": False, "required": ["instruction", "profile", "change_summary"], "properties": {"instruction": {"type": "string", "minLength": 1}, "profile": {"type": "object"}, "change_summary": {"type": "string", "minLength": 1}}}


def _route(queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    with ROUTE_LOCK:
        route, evidence = (route_provider or _load_predecessor()._route)(Path(queue_root), None) if route_provider is None else route_provider(Path(queue_root))
    required = {"name": "grok-build-grok-4.6", "model": "grok-4.6", "reported_model": "grok-4.6-build", "adapter": "grok_exec", "provider": "xai_grok_build", "destination": "xai_grok_build_subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high"}
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or any(route.get(key) != value for key, value in required.items()) or len(route.get("grok_command", [])) != 1 or "public_repo" not in route.get("allowed_payload_classes", []) or type(route.get("timeout_seconds")) not in (int, float) or isinstance(route.get("timeout_seconds"), bool) or route["timeout_seconds"] <= 0:
        raise ValueError("current governed Grok route is unsuitable")
    return dict(route), dict(evidence)


def _files(row: Mapping[str, Any], parent: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
    if not ACK_RE.fullmatch(acknowledgement): raise ValueError("acknowledgement must be lowercase SHA-256")
    prompt = _prompt(row, parent)
    brief = {"format_version": 1, "study_id": STUDY_ID, "cell_id": row["cell_id"], "variant_id": row["variant_id"], "semantic_label": row["semantic_label"], "target_dimension": row["target_dimension"], "mechanism_family": row["mechanism_family"], "semantic_intent": row["semantic_intent"], "brief": row["brief"]}
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell_id": row["cell_id"], "destination": route["destination"], "route": route, "route_evidence": evidence, "payload": {"bytes": len(prompt), "sha256": sha256(prompt), "text": prompt.decode("utf-8")}, "generator_response_schema": {"bytes": len(parent["generator_schema"]), "sha256": sha256(parent["generator_schema"]), "text": parent["generator_schema"].decode("utf-8")}, "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": SYSTEM_PROMPT, "provider_calls_made": 0, "process_launches": 0}
    ack = {"format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha256(disclosure)}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "cell_id": row["cell_id"], "route": route, "route_evidence": evidence, "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "descendant13_nextwave_grok_candidate_preparation", "cell": dict(row), "parent": parent["provenance"], "parent_payload_sha256": sha256(parent["payload"]), "prompt_sha256": sha256(prompt), "response_schema_sha256": sha256(parent["generator_schema"]), "disclosure_sha256": sha256(disclosure), "authorization_sha256": sha256(ack), "route_proof_sha256": sha256(proof), "route": route, "route_evidence": evidence, "tools_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    return {"parent-profile.json": compact(parent["outer"]), "parent-outbound-payload.json": parent["payload"], "variant-brief.json": canonical(brief), "prompt-request.bin": prompt, "response-schema.json": parent["generator_schema"], "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(ack), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def _verify_prepared(root: Path, row: Mapping[str, Any], parent: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str, *, completed: bool = False) -> dict[str, Any]:
    _plain(root, directory=True)
    entries = {path.name: path for path in root.iterdir()}
    required = set(PREPARED)
    if completed:
        required |= {"launch-intent.json", "native-request.bin", "native-response.bin", "descendant-result.json", "descendant-instruction.bin", "descendant-profile.json", "runtime-identity.json", "effective-settings.json", "execution-receipt.json", "result.json", "responses"}
    if set(entries) != required:
        raise ValueError("prepared root inventory contains missing, extra, or unsafe artifacts")
    for name, path in entries.items(): _plain(path, directory=completed and name == "responses")
    if completed:
        responses = entries["responses"]
        expected = {"batch-0001.attempt-0001.prompt.txt", "batch-0001.attempt-0001.grok.envelope.json"}
        if {path.name for path in responses.iterdir()} != expected: raise ValueError("runner response lifecycle drifted")
        for path in responses.iterdir(): _plain(path, directory=False)
    expected = _files(row, parent, route, evidence, acknowledgement)
    if any(stable(root / name) != raw for name, raw in expected.items()): raise ValueError("prepared bytes drifted")
    return _json(expected["prepared.json"], "prepared record")


def _manifest(rows: list[dict[str, Any]], parent: Mapping[str, Any]) -> dict[str, Any]:
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "ten_distinct_descendant13_nextwave_generation_catalog", "parent": parent["provenance"], "cells": rows, "aliases": [], "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": {"status": "unopened", "cells": 0}}}
    value["manifest_sha256"] = sha256(value); return value


def prepare_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, parent_profile: Path = DEFAULT_PARENT_PROFILE, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    root = _safe_output_root(Path(output_root), Path(queue_root), fresh=True)
    parent = _parent(parent_profile); rows = _catalog(parent); route, evidence = _route(Path(queue_root), route_provider)
    root.mkdir(parents=True); _plain(root, directory=True); _write_new(root / "catalog.json", canonical(_manifest(rows, parent)))
    for row in rows:
        cell = root / row["cell_id"]; cell.mkdir(); _plain(cell, directory=True)
        for name, raw in _files(row, parent, route, evidence, authorization_acknowledgement_sha256).items(): _write_new(cell / name, raw)
        _verify_prepared(cell, row, parent, route, evidence, authorization_acknowledgement_sha256)
    return {"study_id": STUDY_ID, "prepared_cells": [row["cell_id"] for row in rows], "provider_calls_made": 0, "process_launches": 0}


def _validate_descendant(value: Any, parent: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"instruction", "profile", "change_summary"} or not isinstance(value["instruction"], str) or not isinstance(value["profile"], Mapping) or not isinstance(value["change_summary"], str): raise ValueError("descendant response semantics drifted")
    predecessor = _load_predecessor(); profile = predecessor._descendant_profile(dict(value["profile"]), parent["profile"])
    if profile["instruction_sha256"] != sha256(value["instruction"].encode("utf-8")): raise ValueError("descendant instruction commitment drifted")
    if value["instruction"].encode("utf-8") == parent["instruction"] and compact(profile) == parent["profile"]: raise ValueError("parent-identical descendant is rejected")
    return {"instruction": value["instruction"], "profile": profile, "change_summary": value["change_summary"]}


def _already_emitted(output_root: Path, cell_id: str, descendant: Mapping[str, Any]) -> bool:
    fingerprint = (sha256(descendant["instruction"].encode("utf-8")), sha256(compact(descendant["profile"])))
    for child in output_root.iterdir():
        if child.name in {"catalog.json", cell_id} or not child.is_dir() or (child / "descendant-result.json").exists() is False: continue
        try:
            prior = _json(stable(child / "descendant-result.json"), "prior descendant")
            if (sha256(prior["instruction"].encode("utf-8")), sha256(compact(prior["profile"]))) == fingerprint: return True
        except (KeyError, ValueError): return True
    return False


def _default_runner(**kwargs: Any) -> Mapping[str, Any]:
    """Delegate actual transport to the pinned tool-free predecessor adapter."""
    return _load_predecessor()._default_runner(**kwargs)


def _expected_intent(row: Mapping[str, Any], prepared: Mapping[str, Any], prompt: bytes) -> dict[str, Any]:
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "intent_before_grok_candidate_generation", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared), "prompt_sha256": sha256(prompt), "native_contact_proven": False}


def _validate_native(value: Mapping[str, Any], prompt: bytes, parent: Mapping[str, Any], route: Mapping[str, Any]) -> tuple[bytes, bytes, bytes, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if set(value) != {"native_request_bytes", "native_response_bytes", "content", "identity", "effective_settings"}: raise ValueError("runner result shape drifted")
    request, response, content, identity, settings = value["native_request_bytes"], value["native_response_bytes"], value["content"], value["identity"], value["effective_settings"]
    if not all(isinstance(item, bytes) for item in (request, response, content)) or request != canonical({"prompt": prompt.decode("utf-8")}).rstrip(b"\n"): raise ValueError("native request drifted")
    descendant = _validate_descendant(_json(content, "descendant"), parent)
    if not isinstance(identity, Mapping) or not isinstance(settings, Mapping) or identity.get("provider") != "xai" or identity.get("requested_model") != "grok-4.6" or identity.get("reported_model") != "grok-4.6-build" or identity.get("native_endpoint_contact_cardinality") != "unproven" or identity.get("tools_enabled") is not False or not isinstance(identity.get("request_id"), str) or not isinstance(identity.get("session_id"), str):
        raise ValueError("native identity drifted")
    expected_settings = {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": TOOL_FREE_ARGV, "system_prompt_override": SYSTEM_PROMPT, "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": float(route["timeout_seconds"]), "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": sha256(prompt), "reasoning_attested": False}
    if dict(settings) != expected_settings: raise ValueError("effective settings drifted")
    envelope = _json(response, "native response")
    if envelope.get("requestId") != identity["request_id"] or envelope.get("sessionId") != identity["session_id"] or envelope.get("structuredOutput") != _json(content, "descendant"):
        raise ValueError("native response identity or structured output drifted")
    return request, response, content, dict(identity), dict(settings), descendant


def _completed_records(row: Mapping[str, Any], prepared: Mapping[str, Any], intent: Mapping[str, Any], prompt: bytes, request: bytes, response: bytes, content: bytes, descendant: Mapping[str, Any], identity: Mapping[str, Any], settings: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "grok_candidate_generation_receipt_cardinality_unproven", "cell": dict(row), "prepared_sha256": sha256(prepared), "launch_intent_sha256": sha256(intent), "prompt_sha256": sha256(prompt), "native_request_sha256": sha256(request), "native_response_sha256": sha256(response), "descendant_result_sha256": sha256(content), "descendant_instruction_sha256": sha256(descendant["instruction"].encode("utf-8")), "descendant_profile_sha256": sha256(compact(descendant["profile"])), "identity": dict(identity), "identity_sha256": sha256(identity), "effective_settings_sha256": sha256(settings), "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unproven"}
    result = {"study_id": STUDY_ID, "cell_id": row["cell_id"], "kind": "provisional_grok_candidate_generation_received", "receipt_sha256": sha256(receipt), "provider_calls_made": None, "process_launches": 1, "authority": "none"}
    return receipt, result


def execute_one(*, output_root: Path, cell_id: str, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, parent_profile: Path = DEFAULT_PARENT_PROFILE, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None, _parent_data: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("explicit allow_remote=True is required")
    parent = dict(_parent_data) if _parent_data is not None else _parent(parent_profile); rows = _catalog(parent); row = next((item for item in rows if item["cell_id"] == cell_id), None)
    if row is None: raise ValueError("unknown candidate cell")
    output = _safe_output_root(Path(output_root), Path(queue_root), fresh=False); root = output / cell_id
    if any((root / name).exists() for name in ("launch-intent.json", "result.json", "reconcile-required.json")): raise ValueError("no resend; use a fresh output root")
    route, evidence = _route(Path(queue_root), route_provider); prepared = _verify_prepared(root, row, parent, route, evidence, authorization_acknowledgement_sha256); prompt = stable(root / "prompt-request.bin")
    intent = _expected_intent(row, prepared, prompt)
    launches = 0
    def before_contact() -> None:
        nonlocal launches
        if launches: raise ValueError("runner signalled more than one contact")
        fresh_route, fresh_evidence = _route(Path(queue_root), route_provider)
        if fresh_route != route or fresh_evidence != evidence: raise ValueError("route drifted adjacent to launch")
        _write_new(root / "launch-intent.json", canonical(intent)); launches = 1
    try:
        value = (runner or _default_runner)(prompt=prompt, schema_path=root / "response-schema.json", output_dir=root, route=route, before_contact=before_contact)
    except BaseException as error:
        result = {"study_id": STUDY_ID, "cell_id": cell_id, "kind": "definitely_not_contacted" if launches == 0 else "reconcile_required_after_process_launch", "detail": type(error).__name__, "provider_calls_made": 0 if launches == 0 else None, "process_launches": launches, "retry_policy": "fresh_output_root_required_no_in_place_resend"}
        _write_new(root / "result.json", canonical(result)); return result
    if launches != 1:
        result = {"study_id": STUDY_ID, "cell_id": cell_id, "kind": "definitely_not_contacted", "detail": "runner_returned_without_contact_callback", "provider_calls_made": 0, "process_launches": 0, "retry_policy": "fresh_output_root_required_no_in_place_resend"}; _write_new(root / "result.json", canonical(result)); return result
    try:
        if not isinstance(value, Mapping): raise ValueError("runner result shape drifted")
        request, response, content, identity, settings, descendant = _validate_native(value, prompt, parent, route)
        if _already_emitted(output, cell_id, descendant): raise ValueError("duplicate descendant output is rejected")
        responses = root / "responses"
        if stable(responses / "batch-0001.attempt-0001.prompt.txt") != prompt or stable(responses / "batch-0001.attempt-0001.grok.envelope.json") != response:
            raise ValueError("runner response artifacts differ from native request/response")
        for name, raw in (("native-request.bin", request), ("native-response.bin", response), ("descendant-result.json", content), ("descendant-instruction.bin", descendant["instruction"].encode("utf-8")), ("descendant-profile.json", compact(descendant["profile"])), ("runtime-identity.json", canonical(identity)), ("effective-settings.json", canonical(settings))): _write_new(root / name, raw)
        receipt, result = _completed_records(row, prepared, intent, prompt, request, response, content, descendant, identity, settings)
        _write_new(root / "execution-receipt.json", canonical(receipt)); _write_new(root / "result.json", canonical(result)); return result
    except BaseException as error:
        result = {"study_id": STUDY_ID, "cell_id": cell_id, "kind": "reconcile_required_after_process_launch", "detail": type(error).__name__, "provider_calls_made": None, "process_launches": 1, "retry_policy": "fresh_output_root_required_no_in_place_resend"}; _write_new(root / "result.json", canonical(result)); return result


async def execute_wave(**kwargs: Any) -> list[dict[str, Any]]:
    parent = _parent(Path(kwargs.get("parent_profile", DEFAULT_PARENT_PROFILE))); rows = _catalog(parent); gate = asyncio.Semaphore(10)
    async def run(row: Mapping[str, Any]) -> dict[str, Any]:
        async with gate: return await asyncio.to_thread(execute_one, **kwargs, cell_id=row["cell_id"], _parent_data=parent)
    return list(await asyncio.gather(*(run(row) for row in rows)))


def reconcile_all(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, parent_profile: Path = DEFAULT_PARENT_PROFILE) -> dict[str, Any]:
    parent = _parent(parent_profile); rows = _catalog(parent); root = _safe_output_root(Path(output_root), Path(queue_root), fresh=False); manifest = _manifest(rows, parent)
    if stable(root / "catalog.json") != canonical(manifest): raise ValueError("catalog reparse drifted")
    seen: set[tuple[str, str]] = set()
    for row in rows:
        cell = root / row["cell_id"]; prepared = _json(stable(cell / "prepared.json"), "prepared record"); route, evidence = prepared.get("route"), prepared.get("route_evidence")
        ack = _json(stable(cell / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
        if not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or ack != authorization_acknowledgement_sha256: raise ValueError("prepared route acknowledgement drifted")
        prepared = _verify_prepared(cell, row, parent, route, evidence, ack, completed=True)
        result = _json(stable(cell / "result.json"), "result")
        if result.get("kind") != "provisional_grok_candidate_generation_received": raise ValueError("terminal generation root cannot be reconciled")
        prompt = stable(cell / "prompt-request.bin")
        intent = _expected_intent(row, prepared, prompt)
        if stable(cell / "launch-intent.json") != canonical(intent): raise ValueError("launch intent reparse drifted")
        native = {"native_request_bytes": stable(cell / "native-request.bin"), "native_response_bytes": stable(cell / "native-response.bin"), "content": stable(cell / "descendant-result.json"), "identity": _json(stable(cell / "runtime-identity.json"), "identity"), "effective_settings": _json(stable(cell / "effective-settings.json"), "settings")}
        request, response, content, identity, settings, descendant = _validate_native(native, prompt, parent, route)
        if stable(cell / "responses" / "batch-0001.attempt-0001.prompt.txt") != prompt or stable(cell / "responses" / "batch-0001.attempt-0001.grok.envelope.json") != response:
            raise ValueError("runner response replay drifted")
        if stable(cell / "descendant-instruction.bin") != descendant["instruction"].encode("utf-8") or stable(cell / "descendant-profile.json") != compact(descendant["profile"]): raise ValueError("descendant byte reparse drifted")
        receipt, expected_result = _completed_records(row, prepared, intent, prompt, request, response, content, descendant, identity, settings)
        if stable(cell / "execution-receipt.json") != canonical(receipt) or stable(cell / "result.json") != canonical(expected_result): raise ValueError("terminal receipt/result reparse drifted")
        fingerprint = (sha256(descendant["instruction"].encode("utf-8")), sha256(compact(descendant["profile"])))
        if fingerprint in seen: raise ValueError("duplicate descendant output is rejected")
        seen.add(fingerprint)
    return {"study_id": STUDY_ID, "kind": "reconciled_ten_provisional_grok_descendants", "cells": 10, "provider_calls_made": 0, "process_launches": 0, "authority": "none"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare-all", action="store_true"); mode.add_argument("--execute-one", action="store_true"); mode.add_argument("--execute-wave", action="store_true"); mode.add_argument("--reconcile-all", action="store_true")
    parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--queue-root", type=Path, required=True); parser.add_argument("--parent-profile", type=Path, default=DEFAULT_PARENT_PROFILE); parser.add_argument("--authorization-acknowledgement-sha256", required=True); parser.add_argument("--cell-id"); parser.add_argument("--allow-remote", action="store_true"); args = parser.parse_args(argv)
    common = {"output_root": args.output_root, "queue_root": args.queue_root, "parent_profile": args.parent_profile, "authorization_acknowledgement_sha256": args.authorization_acknowledgement_sha256}
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
        result = reconcile_all(**common)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
