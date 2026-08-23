"""Regression checks for P1's aggregate-only NO_EFFECT holdout result."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-polarity-change-manual-treatment-holdout-v1-result-v1"
AGGREGATE = ROOT / "p1-manual-treatment-holdout-public-aggregate.v1.json"
EXPECTED_SHA256 = "b6e5169dd044675cbb4665c0e39ab13348ec1fea6268398fb05e714ec0d6feec"
SOURCE_CONTRACT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-polarity-change-manual-treatment-holdout-v1-execution-v1" / "study-contract.json"


def _verifier():
    path = ROOT / "verify_output.py"
    spec = importlib.util.spec_from_file_location("p1_manual_treatment_holdout_public_result_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_package(tmp_path: Path) -> Path:
    candidate = tmp_path / "p1-manual-treatment-holdout"
    shutil.copytree(ROOT, candidate)
    return candidate


def test_public_p1_holdout_no_effect_result_verifies_with_its_local_command_contract() -> None:
    assert _verifier().check(ROOT) == []


def test_no_effect_gates_and_source_commitments_are_pinned() -> None:
    assert hashlib.sha256(AGGREGATE.read_bytes()).hexdigest() == EXPECTED_SHA256
    data = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert data["decision"] == "NO_EFFECT"
    assert data["promotion"] == data["promotion_scope"] == "none"
    assert data["aggregate_counts"] == {
        "planned_slots": 120,
        "completed_slots": 120,
        "first_attempt_accepted_slots": 120,
        "retries": 0,
    }
    assert data["gate_results"] == {
        "current_controls": {"passed": 12, "total": 12},
        "treatment_controls": {"passed": 12, "total": 12},
        "combined_controls": {"passed": 24, "total": 24},
        "current_target_cells": {"passed": 15, "total": 16},
        "treatment_target_cells": {"passed": 15, "total": 16},
        "current_raw_target_matches": {"matched": 47, "total": 48},
        "treatment_raw_target_matches": {"matched": 46, "total": 48},
        "target_improvements": 0,
        "stable_defect_in_both_families": False,
    }
    assert data["opaque_private_receipt_commitments"] == _verifier().EXPECTED_COMMITMENTS
    assert hashlib.sha256(SOURCE_CONTRACT.read_bytes()).hexdigest() == "86691961131402886826568cfda40fad17d9943771612441ceb6882a87ddff2c"
    assert data["opaque_private_receipt_commitments"]["study_contract_sha256"] == hashlib.sha256(SOURCE_CONTRACT.read_bytes()).hexdigest()


def test_verifier_rejects_no_effect_gate_or_commitment_drift(tmp_path: Path) -> None:
    candidate = _copy_package(tmp_path)
    aggregate = candidate / AGGREGATE.name
    data = json.loads(aggregate.read_text(encoding="utf-8"))
    data["decision"] = "GO_PROMOTION"
    data["promotion"] = "prompt"
    data["gate_results"]["target_improvements"] = 1
    data["opaque_private_receipt_commitments"]["settlement_sha256"] = "0" * 64
    aggregate.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert "aggregate SHA-256 does not match the fixed public projection" in failures
    assert "public decision or promotion differs from the public contract" in failures
    assert "NO_EFFECT gate results differ from the public contract" in failures
    assert "opaque private receipt commitments differ from the public contract" in failures


def test_verifier_rejects_equivalence_claim_and_private_holdout_fields(tmp_path: Path) -> None:
    candidate = _copy_package(tmp_path)
    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nH07 expected_label raw_prompt raw_response: equivalent performance.\n",
        encoding="utf-8",
    )
    aggregate = candidate / AGGREGATE.name
    data = json.loads(aggregate.read_text(encoding="utf-8"))
    data["cells"] = [{"fixture_id": "private"}]
    aggregate.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert "forbidden public content: private fixture alias" in failures
    assert "forbidden public content: private fixture label" in failures
    assert "forbidden public content: private prompt or response" in failures
    assert "forbidden public content: equivalence claim" in failures
    assert "aggregate top-level allowlist mismatch" in failures


def test_verifier_rejects_extra_nested_file(tmp_path: Path) -> None:
    candidate = _copy_package(tmp_path)
    nested = candidate / "private" / "receipt.json"
    nested.parent.mkdir()
    nested.write_text("must stay private\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert any("allowlist" in failure for failure in failures)
