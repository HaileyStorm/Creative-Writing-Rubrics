"""Regression checks for the aggregate-only premise-scale ownership result."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path


sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-premise-scale-ownership-v1-result-v1"
AGGREGATE = ROOT / "premise-scale-ownership-public-aggregate.v1.json"
EXPECTED_SHA256 = "bd2fd0f9cb6fcf7e30df54b1759548b48648a7643f361d118e8c72b0a479cc33"
EXPECTED_README_SHA256 = "0924a1415cca7bf5e17d5221a24b13a602b7f5e74965731b333ee19700812850"
EXPECTED_VERIFIER_SHA256 = "8a762890e08b1ca46de9b0318b3ec65194107fa722811ec25685bc394d2a5c1b"


def _verifier():
    spec = importlib.util.spec_from_file_location("premise_scale_ownership_public_result_verifier", ROOT / "verify_output.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_package(tmp_path: Path) -> Path:
    target = tmp_path / "premise-scale-ownership-result"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def _verifier_source_privacy_failures(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    policy_start = source.index("FORBIDDEN_PATTERNS =")
    claims_start = source.index("REQUIRED_READER_CLAIMS =")
    inspected = source[:policy_start] + source[claims_start:]
    patterns = {
        "Windows path": r"[A-Za-z]:[\\/]",
        "fixture or case identifier": r"\b(?:fixture_id|artifact_id|case_id|pair_id)\b",
        "expected label": r"\b(?:expected_label|expected_verdict|expected_state)\b",
        "per-case result": r"\b(?:cell_id|slot_id|verdict)\b",
        "prompt or response": r"\b(?:raw_prompt|raw_response|exact_quote|model_output)\b",
        "provider identifier": r"\b(?:session_id|request_id|run_id|judge_id)\b",
    }
    return [label for label, pattern in patterns.items() if re.search(pattern, inspected, flags=re.IGNORECASE)]


def test_public_result_verifies_with_its_local_command_contract(tmp_path: Path) -> None:
    assert _verifier().check(_copy_package(tmp_path)) == []


def test_aggregate_result_binds_failure_and_source_commitments() -> None:
    data = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert hashlib.sha256(AGGREGATE.read_bytes()).hexdigest() == EXPECTED_SHA256
    assert hashlib.sha256((ROOT / "README.md").read_bytes()).hexdigest() == EXPECTED_README_SHA256
    assert hashlib.sha256((ROOT / "verify_output.py").read_bytes()).hexdigest() == EXPECTED_VERIFIER_SHA256
    assert data["decision"] == "DIAGNOSTIC_FAIL"
    assert data["promotion"] == data["promotion_scope"] == "none"
    assert data["aggregate_counts"] == {
        "planned_slots": 72, "completed_slots": 72, "first_attempt_accepted_slots": 72,
        "scored_cells": 20, "scored_cells_passing": 9, "overall_raw_matches": 37,
        "overall_raw_match_total": 72,
    }
    assert data["opaque_private_receipt_commitments"] == _verifier().EXPECTED_COMMITMENTS


def test_verifier_rejects_result_or_commitment_drift(tmp_path: Path) -> None:
    candidate = _copy_package(tmp_path)
    aggregate = candidate / AGGREGATE.name
    data = json.loads(aggregate.read_text(encoding="utf-8"))
    data["decision"] = "PASS_NO_CHANGE"
    data["promotion"] = "rubric"
    data["aggregate_counts"]["scored_cells_passing"] = 20
    data["opaque_private_receipt_commitments"]["settlement_repair_settlement_sha256"] = "0" * 64
    aggregate.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert "aggregate SHA-256 does not match the fixed public projection" in failures
    assert "public decision or promotion differs from the public contract" in failures
    assert "aggregate counts differ from the public contract" in failures
    assert "opaque private receipt commitments differ from the public contract" in failures


def test_verifier_rejects_private_per_cell_content_and_extra_files(tmp_path: Path) -> None:
    candidate = _copy_package(tmp_path)
    readme = candidate / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nfixture_id expected_verdict slot_id raw_response session_id\n", encoding="utf-8")
    aggregate = candidate / AGGREGATE.name
    data = json.loads(aggregate.read_text(encoding="utf-8"))
    data["cells"] = [{"fixture_id": "private"}]
    aggregate.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    private = candidate / "private" / "receipt.json"
    private.parent.mkdir()
    private.write_text("must remain private\n", encoding="utf-8")
    failures = _verifier().check(candidate)
    assert "forbidden public content: fixture alias" in failures
    assert "forbidden public content: expected label" in failures
    assert "forbidden public content: per-case result" in failures
    assert "forbidden public content: prompt or response" in failures
    assert "forbidden public content: provider metadata" in failures
    assert "aggregate top-level allowlist mismatch" in failures
    assert any("allowlist" in failure for failure in failures)


def test_verifier_rejects_nested_bytecode_cache(tmp_path: Path) -> None:
    candidate = _copy_package(tmp_path)
    cache = candidate / "__pycache__" / "nested" / "verify_output.pyc"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b"not public package content")
    assert any("allowlist" in failure for failure in _verifier().check(candidate))


def test_verifier_source_is_externally_pinned_and_privacy_scrubbed(tmp_path: Path) -> None:
    verifier = ROOT / "verify_output.py"
    assert _verifier_source_privacy_failures(verifier) == []
    mutated = tmp_path / "verify_output.py"
    mutated.write_text(verifier.read_text(encoding="utf-8") + "\nfixture_id = 'not-public'\n", encoding="utf-8")
    assert _verifier_source_privacy_failures(mutated) == ["fixture or case identifier"]
