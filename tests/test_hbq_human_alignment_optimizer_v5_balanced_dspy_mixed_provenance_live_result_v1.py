from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-result-v1"


def _module():
    spec = importlib.util.spec_from_file_location("_hanna_v5_live_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_publication_rechecks_exact_descriptive_result_and_authority_ceiling():
    value = _module().verify()
    assert value == {
        "effective_candidates": 10,
        "logical_cells": 33,
        "unique_payload_cells": 30,
        "result_sha256": "c3da5428731bf85da13e3aaa10f36a4407a4efc8deb232b0e473913b5237a7d6",
        "evidence_ceiling": "Grok-only descriptive development evidence with unproven native endpoint contact cardinality",
    }


def test_tampered_internal_commitment_or_authority_is_rejected(monkeypatch):
    module = _module(); original = module._read
    result = original("result.json"); result["authority"] = {"selection": "winner"}
    monkeypatch.setattr(module, "_read", lambda name: result if name == "result.json" else original(name))
    with pytest.raises(ValueError, match="publication authority"):
        module.verify()
    monkeypatch.setattr(module, "_read", original)
    result = original("result.json"); result["metrics"][0]["equal_group_mae"] = 0.0
    monkeypatch.setattr(module, "_read", lambda name: result if name == "result.json" else original(name))
    with pytest.raises(ValueError, match="equal-group MAE"):
        module.verify()


def test_geometry_and_source_artifact_substitutions_are_rejected(monkeypatch):
    module = _module(); original = module._read
    contract = original("study-contract.json"); contract["geometry"]["aliases"] = 2
    monkeypatch.setattr(module, "_read", lambda name: contract if name == "study-contract.json" else original(name))
    with pytest.raises(ValueError, match="publication contract"):
        module.verify()
    monkeypatch.setattr(module, "_read", original)
    contract, result = original("study-contract.json"), original("result.json")
    replacement = "0" * 64; contract["source_artifacts"]["collector_file_sha256"] = replacement; result["source_artifacts"]["collector_file_sha256"] = replacement; result["collector_sha256"] = replacement
    monkeypatch.setattr(module, "_read", lambda name: contract if name == "study-contract.json" else result)
    with pytest.raises(ValueError, match="publication contract"):
        module.verify()


def test_result_is_data_only_and_does_not_embed_provider_material():
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert set(result) == {"alias_manifest_sha256", "authority", "claim", "collector_sha256", "format_version", "kind", "metrics", "native_endpoint_contact_cardinality", "publication_geometry", "result_sha256", "source_artifacts", "study_id"}
    assert "native_response" not in (PACKAGE / "result.json").read_text(encoding="utf-8")
