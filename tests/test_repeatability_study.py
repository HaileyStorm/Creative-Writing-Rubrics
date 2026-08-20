from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability"


def _analysis_module():
    spec = importlib.util.spec_from_file_location("repeatability_analysis", ROOT / "analyze_study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repeatability_contract_is_frozen_to_the_published_source() -> None:
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    source = ROOT / contract["source"]["path"]
    assert contract["frozen_before_execution"] is True
    assert contract["repetitions"] == 5
    assert 3 <= contract["repetitions"] <= 10
    assert contract["source"]["publication_authorized"] is True
    assert source.stat().st_size == contract["source"]["bytes"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == contract["source"]["sha256"]
    arms = {arm["arm_id"]: arm for arm in contract["arms"]}
    assert set(arms) == {
        "hbq_batched_24",
        "hbq_single_batch",
        "compact_analytic",
        "holistic_anchored",
    }
    assert arms["hbq_batched_24"]["question_id_sequence_sha256"] == (
        arms["hbq_single_batch"]["question_id_sequence_sha256"]
    )
    assert arms["hbq_batched_24"]["question_count"] == 178
    assert arms["hbq_single_batch"]["question_count"] == 178


def test_repeatability_comparator_schemas_are_strict() -> None:
    for path in (ROOT / "arms").glob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False


def test_repeatability_metrics_have_known_boundary_behavior() -> None:
    analysis = _analysis_module()
    assert analysis._alpha_nominal([["YES"] * 5, ["NO"] * 5]) == 1.0
    assert analysis._alpha_nominal([["YES", "NO"] * 2 + ["YES"]]) == 0.0
    summary = analysis._numeric([1.0, 2.0, 3.0])
    assert summary["mean"] == 2.0
    assert summary["range"] == 2.0
    assert summary["mean_absolute_pairwise_difference"] == 4 / 3


def test_published_repeatability_results_match_their_manifest() -> None:
    results = ROOT / "results"
    manifest = json.loads((results / "manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    assert len(files) == 39
    assert set(files) == {
        path.relative_to(results).as_posix()
        for path in results.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    for relative, expected in files.items():
        path = results / relative
        assert path.stat().st_size == expected["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]


def test_published_runs_have_sanitized_ids_and_frozen_provider_settings() -> None:
    results = ROOT / "results"
    forbidden = re.compile(r"(?:[A-Za-z]:\\|/home/|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", re.I)
    for path in results.rglob("*"):
        if path.is_file():
            assert not forbidden.search(path.read_text(encoding="utf-8")), path

    for arm_id, reasoning in (
        ("hbq_batched_24", "medium"),
        ("hbq_single_batch", "medium"),
        ("compact_analytic", "high"),
        ("holistic_anchored", "high"),
    ):
        provenance = json.loads(
            (results / arm_id / "provenance.json").read_text(encoding="utf-8")
        )
        assert [run["run_id"] for run in provenance["runs"]] == [
            f"run-{number:02d}" for number in range(1, 6)
        ]
        for run in provenance["runs"]:
            assert run["reported_provider"] == {
                "provider": "openai",
                "model": "gpt-5.6-sol",
                "reasoning_effort": reasoning,
            }
