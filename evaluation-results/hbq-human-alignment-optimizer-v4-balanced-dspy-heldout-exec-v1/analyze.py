#!/usr/bin/env python3
"""Endpoint-separated held-out gain analysis over a replayed verifier projection."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
VERIFIER_PATH = HERE / "verifier.py"
METRICS_PATH = HERE.parent / "hbq-human-alignment-optimizer-v2" / "analyze.py"
METRICS_SHA256 = "dc8479a962e4a0e2d0082a4619e0e52922d9d82663bd97bc6e17694781aef822"
BASELINE_ID = "candidate-52d1be4bc34e0018"
_FROZEN_TOKEN = object()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _verifier() -> ModuleType:
    raw = VERIFIER_PATH.read_bytes()
    module = ModuleType("_heldout_verifier"); module.__file__ = str(VERIFIER_PATH); sys.modules[module.__name__] = module
    exec(compile(raw, str(VERIFIER_PATH), "exec"), module.__dict__)
    return module


def _metrics() -> ModuleType:
    raw = METRICS_PATH.read_bytes()
    if sha256(raw) != METRICS_SHA256: raise ValueError("HANNA heldout metrics source drifted")
    module = ModuleType("_heldout_metrics"); module.__file__ = str(METRICS_PATH)
    exec(compile(raw, str(METRICS_PATH), "exec"), module.__dict__)
    return module


def _endpoint(rows: Sequence[Mapping[str, Any]], targets: Mapping[str, Mapping[str, float]], *, items: int, groups: int) -> dict[str, Any]:
    return _metrics()._candidate_endpoint(rows, targets, expected_items=items, expected_groups=groups)


@dataclass(frozen=True)
class FrozenGrokSelection:
    phase: Any
    selection: Mapping[str, Any]
    verifier: ModuleType
    _selection_bytes: bytes
    _selection_sha256: str
    _token: object


def freeze_grok_selection(*, collection_evidence_path: Path, collection_root: Path, r4_adoption_path: Path, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> FrozenGrokSelection:
    verifier = _verifier()
    phase = verifier.verify_grok_phase(collection_evidence_path=Path(collection_evidence_path), collection_root=Path(collection_root), r4_adoption_path=Path(r4_adoption_path), reconciliation_manifest_path=Path(reconciliation_manifest_path), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    selection = verifier.select_grok(phase.projection)
    selection_bytes = canonical(selection)
    return FrozenGrokSelection(phase=phase, selection=selection, verifier=verifier, _selection_bytes=selection_bytes, _selection_sha256=sha256(selection_bytes), _token=_FROZEN_TOKEN)


def _validated_selection(frozen: FrozenGrokSelection) -> dict[str, Any]:
    if not isinstance(frozen, FrozenGrokSelection) or frozen._token is not _FROZEN_TOKEN:
        raise ValueError("HANNA heldout analysis rejects caller-created or self-hashed projections")
    current = canonical(dict(frozen.selection))
    recomputed = canonical(frozen.verifier.select_grok(frozen.phase.projection))
    if current != frozen._selection_bytes or recomputed != frozen._selection_bytes or sha256(frozen._selection_bytes) != frozen._selection_sha256:
        raise ValueError("HANNA heldout frozen Grok selection was mutated or substituted")
    return json.loads(frozen._selection_bytes)


def validate_sol_nonreversal(*, frozen: FrozenGrokSelection, collection_evidence_path: Path, collection_root: Path, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    selection = _validated_selection(frozen)
    projection = frozen.verifier.verify_sol_phase(grok_phase=frozen.phase, frozen_selection=selection, collection_evidence_path=Path(collection_evidence_path), collection_root=Path(collection_root), reconciliation_manifest_path=Path(reconciliation_manifest_path), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    rows, targets = projection.get("observations"), projection.get("human_targets")
    if projection.get("kind") != "heldout_independently_replayed_sol_observations" or projection.get("grok_projection_sha256") != selection.get("grok_projection_sha256") or projection.get("frozen_selection_sha256") != frozen._selection_sha256 or not isinstance(rows, list) or not isinstance(targets, Mapping):
        raise ValueError("HANNA heldout Sol projection lineage drifted")
    selected = selection.get("selected_candidate_id")
    if not isinstance(selected, str): raise ValueError("HANNA heldout frozen Grok candidate is invalid")
    sol = [dict(row) for row in rows if isinstance(row, Mapping) and row.get("route_name") == "sol_validation"]
    if len(sol) != 22 or any(row.get("identity", {}).get("evidence_class") != "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven" for row in sol):
        raise ValueError("HANNA heldout Sol evidence ceiling/geometry drifted")
    endpoints = {}
    for candidate_id in (BASELINE_ID, selected):
        candidate_rows = [row for row in sol if row.get("candidate_id") == candidate_id]
        if len(candidate_rows) != 2: raise ValueError("HANNA heldout Sol candidate is incomplete")
        if len({(row.get("item_id"), row.get("prompt_group_id")) for row in candidate_rows}) != 2: raise ValueError("HANNA heldout Sol item/group pairing drifted")
        endpoints[candidate_id] = _endpoint(candidate_rows, targets, items=2, groups=2)
    baseline_error, selected_error = float(endpoints[BASELINE_ID]["mean_absolute_error"]), float(endpoints[selected]["mean_absolute_error"])
    return projection, {"selected_candidate_id": selected, "baseline_candidate_id": BASELINE_ID, "sol_endpoints": [{"candidate_id": candidate, "endpoint": endpoints[candidate]} for candidate in (BASELINE_ID, selected)], "sol_nonreversal": selected_error <= baseline_error, "sol_evidence_ceiling": "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"}


def verify_and_analyze(*, collection_evidence_path: Path, collection_root: Path, r4_adoption_path: Path, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    frozen = freeze_grok_selection(collection_evidence_path=collection_evidence_path, collection_root=collection_root, r4_adoption_path=r4_adoption_path, reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    sol_projection, sol = validate_sol_nonreversal(frozen=frozen, collection_evidence_path=collection_evidence_path, collection_root=collection_root, reconciliation_manifest_path=reconciliation_manifest_path, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    selection = frozen.selection; gain = bool(selection["strict_grok_improvement"] and sol["sol_nonreversal"])
    result = {"format_version": 1, "study_id": "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1", "kind": "heldout_endpoint_separated_gain_result", "grok_projection_sha256": selection["grok_projection_sha256"], "sol_projection_sha256": sha256(canonical(sol_projection)), "grok_selection": selection, "sol_validation": sol, "gain_observed": gain, "claim": "four_group_grok_adapter_control_gain_with_two_group_sol_local_lifecycle_nonreversal" if gain else "no_independently_observed_heldout_gain", "no_pooling": True, "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none"}
    result["result_sha256"] = sha256(canonical(result))
    return {"grok_projection": frozen.phase.projection, "grok_selection": selection, "sol_projection": sol_projection, "result": result}
