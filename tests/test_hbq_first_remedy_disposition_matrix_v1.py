"""Regression checks for the public first-remedy disposition matrix."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-first-remedy-disposition-matrix-v1"


def _verifier():
    path = ROOT / "verify_output.py"
    spec = importlib.util.spec_from_file_location("first_remedy_disposition_matrix_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_first_remedy_disposition_matrix_verifies() -> None:
    assert _verifier().check(ROOT) == []


def test_public_matrix_has_exact_frozen_partition_and_limited_promotions() -> None:
    data = json.loads((ROOT / "matrix.v1.json").read_text(encoding="utf-8"))
    rows = data["rows"]
    assert len(rows) == len({row["finding_id"] for row in rows}) == 77
    assert data["package_geometry"] == {"R0": 2, "L1": 1, "L2": 3, "P1": 11, "S1": 35, "S2": 25}
    assert data["promoted_wording_only_leaf_ids"] == [
        "form.poetry.free_verse.repetition",
        "scope.passage.status",
    ]
    l2 = [row for row in rows if row["package_id"] == "L2"]
    assert [row["disposition"] for row in l2] == [
        "NO_CHANGE_NO_PROMOTION",
        "DIAGNOSTIC_FAIL_NO_PROMOTION",
        "DIAGNOSTIC_FAIL_NO_PROMOTION",
    ]
    assert all(row["structural_changes"] == {"split": False, "owner_change": False, "weight_change": False} for row in rows)
    assert hashlib.sha256((ROOT / "matrix.v1.json").read_bytes()).hexdigest() == _verifier().MATRIX_SHA256


def test_verifier_rejects_extra_file_and_nonpublic_material(tmp_path: Path) -> None:
    candidate = tmp_path / "matrix"
    shutil.copytree(ROOT, candidate)
    (candidate / "__pycache__").mkdir()
    (candidate / "__pycache__" / "private.txt").write_text("not allowed\n", encoding="utf-8")
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nC:\\Users\\example session_id=x\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert any("tree allowlist" in failure for failure in failures)
    assert "forbidden public material: Windows path" in failures
    assert "forbidden public material: session identifier" in failures


def test_verifier_rejects_unsupported_promotion(tmp_path: Path) -> None:
    candidate = tmp_path / "matrix"
    shutil.copytree(ROOT, candidate)
    matrix = candidate / "matrix.v1.json"
    data = json.loads(matrix.read_text(encoding="utf-8"))
    data["rows"][0]["wording_promotion_leaf_ids"] = ["penalty.purple_prose.fatigue"]
    data["rows"][0]["disposition"] = "PROMOTED_WORDING_ONLY"
    matrix.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert "invalid wording promotion scope: c4d62097ce12016c7f3def32d2b8102c19344c316844f38c3b0b1256e2f602c4" in failures
    assert "matrix SHA-256 does not match the fixed public projection" in failures


def test_l2_completion_statement_binding_rejects_missing_or_tampered_statement(tmp_path: Path) -> None:
    binding = _verifier().SETTLED_PUBLIC_RESULTS["l2_public_completion_statement"]
    document = tmp_path / "journey.md"
    document.write_text(binding["normalized_excerpt"] + "\n", encoding="utf-8")
    assert _verifier()._completion_statement_failure(document, binding) is None
    document.write_text("L2 verified only some slots.\n", encoding="utf-8")
    assert _verifier()._completion_statement_failure(document, binding) == "L2 public completion statement is missing or non-unique"
    document.write_text(binding["normalized_excerpt"] + "\n" + binding["normalized_excerpt"] + "\n", encoding="utf-8")
    assert _verifier()._completion_statement_failure(document, binding) == "L2 public completion statement is missing or non-unique"
