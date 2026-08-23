"""Regression checks for P1 manual treatment's aggregate-only result."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-polarity-change-manual-treatment-v1-result-v1"
AGGREGATE = ROOT / "p1-manual-treatment-public-aggregate.v1.json"
EXPECTED_SHA256 = "2fa3e3e598b813e562a139ca305bd1af8a22a58ca591539285044824137b2ca3"


def _verifier():
    path = ROOT / "verify_output.py"
    spec = importlib.util.spec_from_file_location("p1_manual_treatment_public_result_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_p1_manual_treatment_result_verifies_with_its_local_command_contract() -> None:
    assert _verifier().check(ROOT) == []


def test_public_p1_manual_treatment_result_digest_and_arithmetic_are_pinned() -> None:
    assert hashlib.sha256(AGGREGATE.read_bytes()).hexdigest() == EXPECTED_SHA256
    data = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    counts = data["aggregate_counts"]
    table = data["canonical_four_state_counts"]
    accuracy = data["accuracy"]
    assert data["decision"] == "MANUAL_TREATMENT_PASS"
    assert data["evidence_scope"] == "development_only"
    assert data["promotion"] == "none"
    assert counts == {
        "planned_slots": 57,
        "completed_slots": 57,
        "first_attempt_accepted_slots": 57,
        "retries": 0,
        "scored_cells": 19,
        "scored_cells_passing": 19,
    }
    assert accuracy == {
        "CANNOT_ASSESS": {"correct": 0, "denominator": 0},
        "NO": {"correct": 12, "denominator": 12},
        "NOT_APPLICABLE": {"correct": 33, "denominator": 33},
        "YES": {"correct": 12, "denominator": 12},
    }
    assert sum(sum(state_counts.values()) for state_counts in table.values()) == 57


def test_verifier_rejects_private_metadata_and_extra_files(tmp_path: Path) -> None:
    candidate = tmp_path / "p1-manual-treatment"
    shutil.copytree(ROOT, candidate)
    (candidate / "unexpected.txt").write_text("must stay aggregate-only\n", encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nC:\\Users\\private\\p1mt-a01 session_id=secret\n",
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert any("allowlist" in failure for failure in failures)
    assert "forbidden public metadata: Windows path" in failures
    assert "forbidden public metadata: fixture alias" in failures
    assert "forbidden public metadata: session identifier" in failures


def test_verifier_rejects_aggregate_mutation(tmp_path: Path) -> None:
    candidate = tmp_path / "p1-manual-treatment"
    shutil.copytree(ROOT, candidate)
    aggregate = candidate / "p1-manual-treatment-public-aggregate.v1.json"
    aggregate.write_text(
        aggregate.read_text(encoding="utf-8").replace('"scored_cells_passing": 19', '"scored_cells_passing": 18'),
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert "aggregate SHA-256 does not match the fixed public projection" in failures
    assert "aggregate counts differ from the public contract" in failures


def test_verifier_rejects_contradictory_readme_append(tmp_path: Path) -> None:
    candidate = tmp_path / "p1-manual-treatment"
    shutil.copytree(ROOT, candidate)
    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nThis result authorizes a rubric change.\n",
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert "README SHA-256 does not match the fixed public interpretation" in failures


def test_verifier_rejects_generic_holdout_gate_replacement(tmp_path: Path) -> None:
    candidate = tmp_path / "p1-manual-treatment"
    shutil.copytree(ROOT, candidate)
    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "sealed same-fixture current-versus-treatment A/B holdout",
            "sealed A/B holdout",
        ),
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert "README SHA-256 does not match the fixed public interpretation" in failures
    assert any("required reader claim" in failure for failure in failures)
