from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from hbqrs.paths import book_root

REPO = book_root()
PACKAGE = REPO / "evaluation-results" / "cwr-guided-revision-gain-v6-heldout-result-v1"
EXECUTOR = REPO / "evaluation-results" / "cwr-guided-revision-gain-v6-governed-heldout-exec-v1/executor.py"
RUN_ROOT_ENV = "CWR_V6_HELDOUT_RUN_ROOT"

EXPECTED_RESULT = {
    "format_version": 1,
    "study_id": "cwr-guided-revision-gain-v6-heldout-result-v1",
    "source_evidence": {
        "commit": "655e11830676fdf7f6891ce1d80e4cde53a0f106",
        "executor": {
            "path": "evaluation-results/cwr-guided-revision-gain-v6-governed-heldout-exec-v1/executor.py",
            "sha256": "6e5641de603baedbc645f34987455f761085040ab181b6354d707deb5c3cfb9b",
        },
        "external_run_root_basename": "cwr-guided-revision-gain-v6-20260901-655e118-r2",
        "verified_receipts": {
            "cwr_feedback_sol": 4,
            "revision_descendants_grok": 8,
            "blind_endpoint_cells": 48,
            "total": 60,
            "unique_native_identities": 60,
        },
    },
    "endpoint_results_are_not_pooled": True,
    "endpoint_evidence": {
        "gpt-5.6-sol-high": {
            "blind_endpoint_cells": 24,
            "native_endpoint_contact_cardinality": "unproven",
        },
        "grok-4.6-high": {
            "blind_endpoint_cells": 24,
            "native_endpoint_contact_cardinality": 1,
        },
    },
    "mean_score_deltas": {
        "guided_minus_control": {
            "gpt-5.6-sol-high": {"holistic": 1.0, "compact": 0.75},
            "grok-4.6-high": {"holistic": 0.75, "compact": 0.0},
        },
        "guided_minus_source": {
            "gpt-5.6-sol-high": {"holistic": 3.0, "compact": 2.25},
            "grok-4.6-high": {"holistic": 2.75, "compact": 1.5},
        },
        "generic_minus_source": {
            "gpt-5.6-sol-high": {"holistic": 2.0, "compact": 1.5},
            "grok-4.6-high": {"holistic": 2.0, "compact": 1.5},
        },
    },
    "publication_scope": "aggregate_only_no_story_prompt_feedback_unprocessed_output_or_absolute_path",
}


def _executor():
    spec = importlib.util.spec_from_file_location("v6_result_executor", EXECUTOR)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def _run_root() -> Path:
    value = os.environ.get(RUN_ROOT_ENV)
    if not value:
        pytest.skip(f"set {RUN_ROOT_ENV} to replay the externally retained heldout run")
    root = Path(value)
    assert root.is_absolute() and root.is_dir()
    assert root.name == EXPECTED_RESULT["source_evidence"]["external_run_root_basename"]
    return root


def _means(rows: list[dict[str, object]], score_key: str) -> dict[str, dict[str, float]]:
    grouped: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["judge_route_id"]), str(row["measure_id"]))].append(int(row[score_key]))
    return {
        judge: {
            measure: sum(grouped[(judge, measure)]) / len(grouped[(judge, measure)])
            for current_judge, measure in grouped
            if current_judge == judge
        }
        for judge, _measure in grouped
    }


def test_public_result_exactly_reconstructs_the_verified_heldout_run() -> None:
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert result == EXPECTED_RESULT
    assert hashlib.sha256(EXECUTOR.read_bytes()).hexdigest() == result["source_evidence"]["executor"]["sha256"]

    executor, run_root = _executor(), _run_root()
    rows = executor.schedule()
    assert len(rows) == result["source_evidence"]["verified_receipts"]["total"]
    projection = executor.project(run_root=run_root)
    receipts = [
        (row, json.loads((executor._root(run_root, row) / "verified-receipt.json").read_text(encoding="utf-8")))
        for row in rows
    ]
    by_phase = Counter(row["phase"] for row, _receipt in receipts)
    assert by_phase == Counter(cwr_feedback=4, revision_generation=8, blind_endpoint_judgment=48)

    feedback = [(row, receipt) for row, receipt in receipts if row["phase"] == "cwr_feedback"]
    revisions = [(row, receipt) for row, receipt in receipts if row["phase"] == "revision_generation"]
    endpoints = [(row, receipt) for row, receipt in receipts if row["phase"] == "blind_endpoint_judgment"]
    assert len(feedback) == result["source_evidence"]["verified_receipts"]["cwr_feedback_sol"]
    assert {row["route"]["model"] for row, _receipt in feedback} == {"gpt-5.6-sol"}
    assert len(revisions) == result["source_evidence"]["verified_receipts"]["revision_descendants_grok"]
    assert {row["route"]["model"] for row, _receipt in revisions} == {"grok-4.6"}
    assert all(receipt["descendant"] and receipt["native"]["native_endpoint_contact_cardinality"] == 1 for _row, receipt in revisions)

    identities = {
        (str(receipt["native"]["provider_request_id"]), str(receipt["native"]["provider_session_id"]))
        for _row, receipt in receipts
    }
    assert len(identities) == result["source_evidence"]["verified_receipts"]["unique_native_identities"]
    endpoint_by_model: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row, receipt in endpoints:
        endpoint_by_model[str(row["route"]["model"])].append(receipt)
    assert {model: len(values) for model, values in endpoint_by_model.items()} == {"gpt-5.6-sol": 24, "grok-4.6": 24}
    assert {receipt["native"]["native_endpoint_contact_cardinality"] for receipt in endpoint_by_model["gpt-5.6-sol"]} == {"unproven"}
    assert {receipt["native"]["native_endpoint_contact_cardinality"] for receipt in endpoint_by_model["grok-4.6"]} == {1}

    assert set(projection) == {
        "study_id",
        "kind",
        "endpoint_results_are_not_pooled",
        "primary_guided_minus_control",
        "guided_minus_source",
        "generic_minus_source",
    }
    assert projection["endpoint_results_are_not_pooled"] is True
    assert [len(projection[name]) for name in ("primary_guided_minus_control", "guided_minus_source", "generic_minus_source")] == [16, 16, 16]
    actual_means = {
        "guided_minus_control": _means(projection["primary_guided_minus_control"], "guided_minus_control"),
        "guided_minus_source": _means(projection["guided_minus_source"], "arm_minus_source"),
        "generic_minus_source": _means(projection["generic_minus_source"], "arm_minus_source"),
    }
    assert actual_means == result["mean_score_deltas"]

    tampered = json.loads(json.dumps(result))
    tampered["source_evidence"]["verified_receipts"]["unique_native_identities"] = 59
    assert tampered != result


def test_public_package_has_no_paths_or_native_ids() -> None:
    assert sorted(path.name for path in PACKAGE.iterdir()) == ["README.md", "result.json"]
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    counts = result["source_evidence"]["verified_receipts"]
    assert f"{counts['cwr_feedback_sol']} Sol feedback receipts" in readme
    assert f"{counts['revision_descendants_grok']} exact-one Grok revision receipts" in readme
    assert f"{counts['blind_endpoint_cells']} endpoint receipts" in readme
    assert "not pooled" in readme
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.iterdir())
    assert not any(token in public_text for token in ("source_text", "source_prompt", "adapter-stdout", "adapter-stderr", "raw_output", "descendant.md"))
    all_public_source = public_text + Path(__file__).read_text(encoding="utf-8")
    assert not re.search(r"(?i)(?:\b[a-z]:[\\/]|/(?:users|home)/)", all_public_source)
    assert not re.search(r"(?i)\b(?:grok|sol)-(?:request|session|thread)-sha256:", all_public_source)
