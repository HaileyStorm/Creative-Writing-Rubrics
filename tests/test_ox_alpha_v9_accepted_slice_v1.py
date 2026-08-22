"""Focused coverage for the deterministic Ox Alpha v9 accepted-slice analysis."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-ox-alpha-v9-accepted-slice-v1"
OX = Path(r"C:\Users\Haile\Documents\cwr-ox-alpha-v9-scoring-20260822-db87d90")
GPT = Path(r"C:\Users\Haile\Documents\cwr-hanna-fresh88-sol-v1-20260821-w4-repair1-artifacts")
GROK = Path(r"C:\Users\Haile\Documents\cwr-supplemental-providers-v1-grok-hardened-20260821-44518ab-r2")
INPUTS = Path(r"C:\Users\Haile\Documents\cwr-human-reference-v3-d9038f1\inputs\development")

spec = importlib.util.spec_from_file_location("ox_v9_slice", ROOT / "analyze.py")
assert spec and spec.loader
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def _real() -> dict:
    if not all(path.is_dir() for path in (OX, GPT, GROK, INPUTS)):
        pytest.skip("frozen external evidence unavailable")
    return analysis.analyze(OX, GPT, GROK, INPUTS)


def test_frozen_accepted_slice_aggregates():
    result = _real()
    assert result["scope"] == {"accepted_verdicts": 327, "expected_verdicts": 537, "complete_story_scores": False, "imputation": False}
    assert result["verdict_distribution"] == {"CANNOT_ASSESS": 5, "NO": 236, "NOT_APPLICABLE": 30, "YES": 56}
    assert {item: row["accepted_leaves"] for item, row in result["story_coverage"].items()} == {"hanna-827": 160, "hanna-957": 123, "hanna-201": 44}
    assert result["agreement"]["gpt"]["exact_agreement"] == 0.700306
    assert result["agreement"]["gpt"]["cohen_kappa"] == 0.471284
    assert result["agreement"]["grok"]["exact_agreement"] == 0.865443
    assert result["agreement"]["grok"]["cohen_kappa"] == 0.684356
    assert result["quote_evidence"] == {"retained_exact_quotes": 453, "retained_quotes_valid": 453, "invalid_retained_quotes": 0, "normalizations_to_summary": 11}
    assert result["quarantine_classes"] == {"empty_provider_response": 4, "malformed_provider_response": 1, "other_non_524_provider_failure": 1}


def test_checked_result_is_exact_replay():
    assert json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8")) == _real()
    manifest = json.loads((ROOT / "results" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["summary.json"] == analysis._binding(ROOT / "results" / "summary.json")
    rendered = json.dumps(manifest) + (ROOT / "results" / "summary.json").read_text(encoding="utf-8")
    assert "C:\\\\Users" not in rendered

    def keys(value):
        if isinstance(value, dict):
            return set(value).union(*(keys(child) for child in value.values()))
        if isinstance(value, list):
            return set().union(*(keys(child) for child in value), set())
        return set()

    assert not ({"exact_quote", "summary", "note", "artifact", "prompt"} & keys(_real()))


def test_question_order_and_reference_binding_tamper_are_rejected(tmp_path):
    rows = [{"question_id": "a"}, {"question_id": "b"}]
    analysis._assert_ordered_questions(rows, ["a", "b"], "fixture")
    with pytest.raises(ValueError, match="order/content drifted"):
        analysis._assert_ordered_questions(list(reversed(rows)), ["a", "b"], "fixture")

    source = GPT / "runs" / "hanna-827" / "verdicts.jsonl"
    if not source.is_file():
        pytest.skip("frozen GPT evidence unavailable")
    target = tmp_path / "runs" / "hanna-827"
    target.mkdir(parents=True)
    (target / "verdicts.jsonl").write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="binding drifted"):
        analysis.analyze(OX, tmp_path, GROK, INPUTS)


def test_swapped_external_roots_fail_cleanly():
    if not all(path.is_dir() for path in (OX, GPT, GROK, INPUTS)):
        pytest.skip("frozen external evidence unavailable")
    with pytest.raises((FileNotFoundError, ValueError)):
        analysis.analyze(OX, GROK, GPT, INPUTS)
