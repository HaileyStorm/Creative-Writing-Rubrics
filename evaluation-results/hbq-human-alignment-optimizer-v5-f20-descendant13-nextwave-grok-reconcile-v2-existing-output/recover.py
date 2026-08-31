#!/usr/bin/env python3
"""Provider-free recovery of the immutable descendant-13 Grok output tree."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-reconcile-v2-existing-output"
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-exec-v1"
SOURCE_COMMIT = "1424f79d7dd99dd6d95249e57b973572bc7d515f"
SOURCE_RELATIVE = "evaluation-results/hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-exec-v1/executor.py"
SOURCE_SHA256 = "14412535b946cbf6f8b758452b39d17a9d7de5558a7b7f0edc712a7838bc19b6"
SOURCE_EXECUTOR = REPO / SOURCE_RELATIVE
SOURCE_FILES = frozenset({
    "parent-profile.json", "parent-outbound-payload.json", "variant-brief.json",
    "prompt-request.bin", "response-schema.json", "disclosure.json",
    "authorization-acknowledgement.json", "zero-charge-route-proof.json",
    "prepared.json", "launch-intent.json", "result.json", "responses",
})
RESPONSE_FILES = frozenset({"batch-0001.attempt-0001.prompt.txt", "batch-0001.attempt-0001.grok.envelope.json"})
EXPECTED_FAILURES = {
    "descendant13-nextwave-01-scale-adjacency": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-02-speaker-attribution": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-03-temporal-causality-separation": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-04-surprise-reversal-specificity": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-05-complexity-interrelation": ("profile_factors_drift", "profile factors drifted"),
    "descendant13-nextwave-06-relevance-task-binding": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-07-empathy-perspective-distinction": ("profile_factors_drift", "profile factors drifted"),
    "descendant13-nextwave-08-engagement-stakes-distinction": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-09-coherence-reference-resolution": ("profile_geometry_drift", "profile geometry drifted"),
    "descendant13-nextwave-10-rhetorical-question-disambiguation": ("profile_factors_drift", "profile factors drifted"),
}
EXPECTED_ENVELOPE_SHA256 = {
    "descendant13-nextwave-01-scale-adjacency": "5c2816b0b007649fe5936f064de6eb6062795eff55c5a2c89b2f4af49a9def60",
    "descendant13-nextwave-02-speaker-attribution": "5a16ab7b99497f4912680afbaad6974d7949bee25db593f95bd915fdf9e017b8",
    "descendant13-nextwave-03-temporal-causality-separation": "73defa4de26a4fc9d53fd1b522dfb91339139e26b59314112c505685bec5ec10",
    "descendant13-nextwave-04-surprise-reversal-specificity": "9cc414ef0ebdcfbf042c77e9921aebea4c850f5619e56c1aae0752e579986cf3",
    "descendant13-nextwave-05-complexity-interrelation": "7e2450e8880715d1c8b5fc2bc904fe02394f0dcf898b23f41e89ff34d3865be5",
    "descendant13-nextwave-06-relevance-task-binding": "6b1f89d0fc763eb2bded57992ebeef67a48f77dde39edaa4d6676024b07b6763",
    "descendant13-nextwave-07-empathy-perspective-distinction": "3baea37b600f474396db0d168b53a43b55741fa42082d72fb201f56e03219bb4",
    "descendant13-nextwave-08-engagement-stakes-distinction": "0f1861e49ae99f42c969ada1e8e7d6b62f4760a7c86e08c8828cc9f29a3dd96d",
    "descendant13-nextwave-09-coherence-reference-resolution": "0bae24c86c9f67635c775c699df7c35e305cd7a2f4fc6a4acf2f8a6539d06d58",
    "descendant13-nextwave-10-rhetorical-question-disambiguation": "7b459091861c5f26228f34b40f5be22ec4d489596df936ae82d3927f2474ee8e",
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError(f"unsafe/reparsed path: {path}")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError(f"unexpected path type: {path}")


def _safe_ancestry(path: Path) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=True)
    return absolute


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def stable(path: Path) -> bytes:
    path = Path(os.path.abspath(path)); _safe_ancestry(path.parent); _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    fields = ("st_dev", "st_ino", "st_size")
    if any(getattr(before, field) != getattr(opened, field) or getattr(opened, field) != getattr(after, field) for field in fields):
        raise ValueError("file changed during stable read")
    return raw


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")  # noqa: TRY004
    return value


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(f"refuses overwrite: {path}")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _source() -> Any:
    raw = stable(SOURCE_EXECUTOR)
    if sha256(raw) != SOURCE_SHA256 or _blob(SOURCE_COMMIT, SOURCE_RELATIVE) != raw:
        raise ValueError("pinned generator/source catalog drifted")
    spec = importlib.util.spec_from_file_location("_descendant13_existing_output_source", SOURCE_EXECUTOR)
    if spec is None or spec.loader is None:
        raise ValueError("pinned generator/source catalog cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _fresh_target(source_root: Path, target_root: Path) -> tuple[Path, Path]:
    source, target = _safe_ancestry(source_root), _safe_ancestry(target_root)
    if not source.is_dir() or target.exists() or _under(target, source) or _under(source, target) or _under(target, REPO):
        raise ValueError("target must be a fresh disjoint directory outside the repository and source")
    return source, target


def _inventory(root: Path, expected: frozenset[str], label: str) -> dict[str, Path]:
    _plain(root, directory=True)
    entries = {path.name: path for path in root.iterdir()}
    if set(entries) != expected:
        raise ValueError(f"{label} inventory drifted")
    return entries


def _terminal(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "study_id": SOURCE_STUDY_ID, "cell_id": row["cell_id"],
        "kind": "reconcile_required_after_process_launch", "detail": "ValueError",
        "provider_calls_made": None, "process_launches": 1,
        "retry_policy": "fresh_output_root_required_no_in_place_resend",
    }


def _proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"instruction", "profile", "change_summary"}:
        raise ValueError("envelope structured proposal shape drifted")
    instruction, profile, change_summary = value["instruction"], value["profile"], value["change_summary"]
    if not isinstance(instruction, str) or not isinstance(profile, Mapping) or not isinstance(change_summary, str):
        raise ValueError("envelope structured proposal semantics drifted")  # noqa: TRY004
    return {
        "instruction": instruction, "change_summary": change_summary,
        "instruction_sha256": sha256(instruction.encode("utf-8")),
        "profile_sha256": sha256(compact(dict(profile))),
    }


def recover(*, source_root: Path, target_root: Path) -> dict[str, Any]:
    """Read one immutable terminal wave and write one new rejection manifest."""
    source_root, target_root = _fresh_target(Path(source_root), Path(target_root))
    source = _source(); parent = source._parent(source.DEFAULT_PARENT_PROFILE); rows = source._catalog(parent)
    expected_catalog = source.canonical(source._manifest(rows, parent))
    expected_cells = {row["cell_id"] for row in rows}
    if expected_cells != set(EXPECTED_FAILURES) or expected_cells != set(EXPECTED_ENVELOPE_SHA256):
        raise ValueError("pinned source catalog classification drifted")
    entries = _inventory(source_root, frozenset({"catalog.json", *expected_cells}), "source root")
    if stable(entries["catalog.json"]) != expected_catalog:
        raise ValueError("source catalog reparse drifted")
    request_ids: set[str] = set(); session_ids: set[str] = set(); recovered: list[dict[str, Any]] = []
    for row in rows:
        cell_id = row["cell_id"]; cell = entries[cell_id]
        _inventory(cell, SOURCE_FILES, f"{cell_id} terminal")
        prepared = _json(stable(cell / "prepared.json"), "prepared record")
        route, evidence = prepared.get("route"), prepared.get("route_evidence")
        acknowledgement = _json(stable(cell / "authorization-acknowledgement.json"), "acknowledgement").get("acknowledgement_sha256")
        if not isinstance(route, Mapping) or not isinstance(evidence, Mapping) or not isinstance(acknowledgement, str):
            raise ValueError("prepared route acknowledgement drifted")  # noqa: TRY004
        expected_files = source._files(row, parent, route, evidence, acknowledgement)
        if any(stable(cell / name) != raw for name, raw in expected_files.items()):
            raise ValueError("prepared source bytes drifted")
        prompt = stable(cell / "prompt-request.bin")
        intent = source._expected_intent(row, prepared, prompt)
        if stable(cell / "launch-intent.json") != source.canonical(intent):
            raise ValueError("launch intent reparse drifted")
        if stable(cell / "result.json") != source.canonical(_terminal(row)):
            raise ValueError("terminal result reparse drifted")
        response_entries = _inventory(cell / "responses", RESPONSE_FILES, f"{cell_id} responses")
        if stable(response_entries["batch-0001.attempt-0001.prompt.txt"]) != prompt:
            raise ValueError("response prompt binding drifted")
        envelope_raw = stable(response_entries["batch-0001.attempt-0001.grok.envelope.json"])
        if sha256(envelope_raw) != EXPECTED_ENVELOPE_SHA256[cell_id]:
            raise ValueError("response envelope source pin drifted")
        envelope = _json(envelope_raw, "response envelope")
        if set(envelope) != {"text", "stopReason", "sessionId", "requestId", "thought", "usage", "num_turns", "total_cost_usd", "total_cost_usd_ticks", "modelUsage", "structuredOutput"}:
            raise ValueError("response envelope shape drifted")
        if envelope["stopReason"] != "end_turn" or not isinstance(envelope["text"], str) or not isinstance(envelope["thought"], str) or not isinstance(envelope["usage"], Mapping) or not isinstance(envelope["modelUsage"], Mapping) or type(envelope["num_turns"]) is not int or envelope["num_turns"] != 1:
            raise ValueError("response envelope semantics drifted")
        if _json(envelope["text"].encode("utf-8"), "response envelope text") != envelope["structuredOutput"]:
            raise ValueError("response envelope text binding drifted")
        model_usage = envelope["modelUsage"]
        if set(model_usage) != {"grok-4.6-build"} or not isinstance(model_usage["grok-4.6-build"], Mapping):
            raise ValueError("response envelope model usage identity drifted")
        model_usage = model_usage["grok-4.6-build"]
        if set(model_usage) != {"inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "modelCalls", "costUSD"} or model_usage["modelCalls"] != 1:
            raise ValueError("response envelope model usage shape drifted")
        if any(type(model_usage[key]) is not int or model_usage[key] < 0 for key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")) or type(model_usage["costUSD"]) not in (int, float) or model_usage["costUSD"] < 0:
            raise ValueError("response envelope model usage values drifted")
        request_id, session_id = envelope.get("requestId"), envelope.get("sessionId")
        if not isinstance(request_id, str) or not request_id or not isinstance(session_id, str) or not session_id or request_id in request_ids or session_id in session_ids:
            raise ValueError("duplicate or absent envelope request/session identity")
        request_ids.add(request_id); session_ids.add(session_id)
        proposal = _proposal(envelope.get("structuredOutput"))
        try:
            source._validate_descendant(envelope["structuredOutput"], parent)
        except ValueError as error:
            strict_error = str(error)
        else:
            raise ValueError("unexpected admissible proposal")
        failure_class, expected_error = EXPECTED_FAILURES[cell_id]
        if strict_error != expected_error:
            raise ValueError("strict invalid-profile classification drifted")
        recovered.append({
            "cell": dict(row), "status": "rejected_invalid_profile_proposal",
            "failure_class": failure_class, "strict_error": strict_error,
            "proposal": proposal, "envelope_sha256": sha256(envelope_raw),
            "prompt_sha256": sha256(prompt), "prepared_sha256": sha256(prepared),
            "launch_intent_sha256": sha256(intent),
            "route_proof_sha256": prepared["route_proof_sha256"],
            "authorization_sha256": prepared["authorization_sha256"],
            "envelope_request_id": request_id, "envelope_session_id": session_id,
            "original_terminal": _terminal(row),
        })
    manifest = {
        "format_version": 1, "study_id": STUDY_ID,
        "kind": "provider_free_recovery_of_rejected_descendant13_grok_proposals",
        "source": {"study_id": SOURCE_STUDY_ID, "commit": SOURCE_COMMIT, "executor_relative_path": SOURCE_RELATIVE, "executor_sha256": SOURCE_SHA256, "catalog_sha256": sha256(expected_catalog), "envelope_sha256_by_cell": EXPECTED_ENVELOPE_SHA256},
        "cells": recovered,
        "classification_counts": {"rejected_invalid_profile_proposals": 10, "profile_geometry_drift": 7, "profile_factors_drift": 3},
        "provider_calls_made": 0, "process_launches": 0,
        "process_launches_scope": "provider_or_executor_only; local Git provenance subprocesses are excluded",
        "original_process_launches_per_cell": 1,
        "original_provider_calls_made_per_cell": "unknown",
        "native_endpoint_contact_cardinality": "unproven_not_reconstructed",
        "authority": {"selection": "none", "promotion": "none", "runtime": "none", "confirmation": "none"},
    }
    manifest["manifest_sha256"] = sha256(manifest)
    target_root.mkdir(parents=True); _plain(target_root, directory=True)
    _write_new(target_root / "recovery-manifest.json", canonical(manifest))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    args = parser.parse_args(argv)
    sys.stdout.buffer.write(canonical(recover(source_root=args.source_root, target_root=args.target_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
