"""Regression checks for S2's aggregate-only public result package."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-nonpoetry-scope-sentinel-v1-result-v1"
AGGREGATE = ROOT / "s2-public-aggregate.v1.json"
EXPECTED_SHA256 = "49d6ef3843062580bbbda0b362756634f993613600269d4176be0bb157c9d453"


def _verifier():
    path = ROOT / "verify_output.py"
    spec = importlib.util.spec_from_file_location("s2_public_result_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_s2_result_verifies_with_its_local_command_contract() -> None:
    assert _verifier().check(ROOT) == []


def test_public_s2_result_digest_and_arithmetic_are_pinned() -> None:
    assert hashlib.sha256(AGGREGATE.read_bytes()).hexdigest() == EXPECTED_SHA256
    data = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    counts = data["aggregate_counts"]
    table = data["canonical_four_state_counts"]
    assert data["decision"] == "DIAGNOSTIC_FAIL"
    assert data["promotion"] == "none"
    assert counts["planned_slots"] == counts["completed_slots"] == counts["first_attempt_accepted_slots"] == 60
    assert counts["scored_cells_passing"] == 10
    assert counts["scored_cells"] == 15
    assert counts["not_applicable_control_cells_matching"] == counts["not_applicable_control_cells"] == 5
    assert sum(sum(state_counts.values()) for state_counts in table.values()) == 60


def test_verifier_rejects_private_metadata_and_extra_files(tmp_path: Path) -> None:
    candidate = tmp_path / "s2"
    shutil.copytree(ROOT, candidate)
    (candidate / "unexpected.txt").write_text("must stay aggregate-only\n", encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nC:\\Users\\private\\synthetic-01\\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert any("allowlist" in failure for failure in failures)
    assert "forbidden public metadata: Windows path" in failures
    assert "forbidden public metadata: fixture alias" in failures
