from __future__ import annotations

import builtins
import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1"
MANIFEST = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-reconcile-v1-52dc2157-e0b5c104\reconciliation-manifest.json")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
study = load_module(PACKAGE / "study.py", name="hanna_v4_heldout_study")
analyze = load_module(PACKAGE / "analyze.py", name="hanna_v4_heldout_analyze")


@pytest.fixture(scope="module")
def schedule():
    return study.build_schedule(reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def _self_rehash(value: dict) -> None:
    body = {key: item for key, item in value.items() if key != "manifest_sha256"}
    value["manifest_sha256"] = study.sha256(body)


def test_real_reconciliation_manifest_replay_geometry_profile_binding_and_parity(schedule):
    baseline = study._baseline(study._v3())
    manifest = study._reconciliation_manifest(MANIFEST, baseline=baseline)
    assert manifest["manifest_sha256"] == study.RECONCILIATION_MANIFEST_SHA256
    assert manifest["source"]["terminal_roots"] == manifest["source"]["completed_native_identities"] == 10
    assert schedule["baseline"]["candidate_id"] == study.BASELINE_ID
    assert schedule["geometry"] == {"candidates": 11, "grok_cells": 44, "sol_cells": 22, "total_cells": 66}
    assert len(schedule["groups"]) == 4 and schedule["sol_sprinkled_group_count"] == 2
    for row in manifest["samples"]:
        profile = json.loads(__import__("base64").b64decode(row["normalized_output"]["descendant_profile_base64"]))
        assert profile["instruction_sha256"] == row["lineage"]["descendant_instruction_sha256"]
    for group in schedule["groups"][:2]:
        paired = [row for row in schedule["cells"] if row["item_id"] == group["item_id"] and row["candidate_id"] == schedule["baseline"]["candidate_id"]]
        assert len(paired) == 2 and study.payload_bytes(paired[0]) == study.payload_bytes(paired[1])


@pytest.mark.parametrize("path", [
    ("source", "source_root"),
    ("samples", 0, "raw_output", "descendant_instruction_base64"),
    ("samples", 0, "normalized_output", "descendant_profile_base64"),
])
def test_self_rehashed_source_raw_or_normalized_tamper_is_rejected(tmp_path: Path, path):
    value = json.loads(MANIFEST.read_text(encoding="utf-8"))
    target = value
    for part in path[:-1]: target = target[part]
    target[path[-1]] = "forged"
    _self_rehash(value)
    copied = tmp_path / "forged.json"; copied.write_bytes(study.canonical(value))
    with pytest.raises(ValueError, match="manifest file hash"):
        study._reconciliation_manifest(copied, baseline=study._baseline(study._v3()))


def test_self_rehashed_train_confirmation_schedule_and_analysis_are_rejected(schedule):
    for mutation in ("train", "confirmation"):
        forged = json.loads(json.dumps(schedule))
        if mutation == "train": forged["groups"][0]["item_id"] = "hanna-141"
        else: forged["confirmation"] = {"status": "opened", "cells": 1}
        forged["schedule_sha256"] = study.sha256({key: forged[key] for key in ("reconciliation", "baseline", "candidate_order", "groups", "sol_sprinkled_group_count", "cells", "geometry", "missing_terminal_policy", "tie_break", "confirmation")})
        with pytest.raises(ValueError, match="byte-match"):
            analyze.analyze(schedule=forged, reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)
    with pytest.raises(ValueError, match="NO-GO until"):
        analyze.analyze(schedule=schedule, reconciliation_manifest_path=MANIFEST, frozen_successor_path=FROZEN, hanna_csv_path=CSV)


def test_reconciler_source_pin_and_optimizer_runtime_import_rejected(monkeypatch):
    original_hash = study.RECONCILER_SHA256; study.RECONCILER_SHA256 = "0" * 64
    try:
        with pytest.raises(ValueError, match="pinned reconciler source"):
            study._reconciliation_manifest(MANIFEST, baseline=study._baseline(study._v3()))
    finally:
        study.RECONCILER_SHA256 = original_hash
    original_import = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}: raise AssertionError("development optimizer imported at runtime")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    load_module(PACKAGE / "study.py", name="hanna_v4_heldout_real_import_study")
    load_module(PACKAGE / "analyze.py", name="hanna_v4_heldout_real_import_analyze")
