"""Regression checks for P1's aggregate-only public result package."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-polarity-change-current-wording-v1-result-v1"
AGGREGATE = ROOT / "p1-public-aggregate.v1.json"
EXPECTED_SHA256 = "e85500c3d8dc02f51d503fbfc946b680d9de6711adcead5e9003613623d07070"


def _verifier():
    path = ROOT / "verify_output.py"
    spec = importlib.util.spec_from_file_location("p1_public_result_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_p1_result_verifies_with_its_local_command_contract() -> None:
    assert _verifier().check(ROOT) == []


def test_public_p1_result_digest_and_arithmetic_are_pinned() -> None:
    assert hashlib.sha256(AGGREGATE.read_bytes()).hexdigest() == EXPECTED_SHA256
    data = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    counts = data["aggregate_counts"]
    table = data["canonical_four_state_counts"]
    accuracy = data["accuracy"]
    assert data["decision"] == "DIAGNOSTIC_FAIL"
    assert data["promotion"] == "none"
    assert counts["planned_slots"] == counts["completed_slots"] == counts["first_attempt_accepted_slots"] == 132
    assert counts["scored_cells_passing"] == 29
    assert counts["scored_cells"] == 33
    assert counts["not_applicable_control_cells_matching"] == 6
    assert counts["not_applicable_control_cells"] == 11
    assert accuracy == {
        "CANNOT_ASSESS": {"correct": 33, "denominator": 33},
        "NO": {"correct": 31, "denominator": 33},
        "NOT_APPLICABLE": {"correct": 22, "denominator": 33},
        "YES": {"correct": 24, "denominator": 33},
    }
    assert sum(sum(state_counts.values()) for state_counts in table.values()) == 132


def test_verifier_rejects_private_metadata_and_extra_files(tmp_path: Path) -> None:
    candidate = tmp_path / "p1"
    shutil.copytree(ROOT, candidate)
    (candidate / "unexpected.txt").write_text("must stay aggregate-only\n", encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nC:\\Users\\private\\p1-artifact-001 run_id=duplicate\n",
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert any("allowlist" in failure for failure in failures)
    assert "forbidden public metadata: Windows path" in failures
    assert "forbidden public metadata: fixture alias" in failures
    assert "forbidden public metadata: run identifier" in failures


def test_verifier_rejects_aggregate_mutation(tmp_path: Path) -> None:
    candidate = tmp_path / "p1"
    shutil.copytree(ROOT, candidate)
    aggregate = candidate / "p1-public-aggregate.v1.json"
    aggregate.write_text(
        aggregate.read_text(encoding="utf-8").replace('"scored_cells_passing": 29', '"scored_cells_passing": 30'),
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert "aggregate SHA-256 does not match the fixed public projection" in failures
    assert "aggregate counts differ from the public contract" in failures


def test_verifier_rejects_contradictory_readme_append(tmp_path: Path) -> None:
    candidate = tmp_path / "p1"
    shutil.copytree(ROOT, candidate)
    readme = candidate / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nThis result authorizes a prompt change.\n",
        encoding="utf-8",
    )
    failures = _verifier().check(candidate)
    assert "README SHA-256 does not match the fixed public interpretation" in failures
