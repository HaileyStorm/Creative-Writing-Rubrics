from __future__ import annotations

import json
import re

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-c03-visual-control-successor-v1-execution-v1-public-result-v1"


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_aggregate_is_complete_and_non_promoting():
    result = _result()

    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-l2-c03-visual-control-successor-v1-execution-v1"
    assert result["execution"] == {
        "planned_calls": 12,
        "completed_calls": 12,
        "valid_calls": 12,
        "normalization_events": 0,
    }
    assert result["aggregate_cells"] == {
        "total": 4,
        "correct_repeat_histogram": {"0": 0, "1": 1, "2": 2, "3": 1},
    }
    assert result["decision"] == "NO_GO"
    assert result["promotion"] == "none"
    assert result["interpretation"] == (
        "The exact multimodal diagnostic is insufficiently repeatable; "
        "it supports no line-break or rubric conclusion."
    )


def test_source_bindings_are_exact_sha256_commitments_only():
    bindings = _result()["source_bindings"]

    assert bindings == {
        "execution_claim_sha256": "fb5d22a789989a053a536ec65daca0b0733bbbc94be78e09666c84275b3eb596",
        "settlement_prepared_sha256": "74f097816d8211a6efeb4cc70b59f8ce6608f9678af8b293fbd47a87250b7504",
        "settlement_sha256": "a56dfe5616de31805d56c17f058aee24ae9ea4c1d54422a0e5c3b8cd7480aa8b",
        "public_aggregate_sha256": "1ca133682182be0f0fe1ab056e55b53a72141a1af006ea0c4eaf4abc3253fd6b",
        "publication_marker_sha256": "639f2d3e4f5ba92d2200a5348cdc78dba88eec48ef7a5be484388aedab3e0dd8",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_projection_excludes_individual_material_and_paths():
    package = "\n".join(
        (ROOT / name).read_text(encoding="utf-8")
        for name in ("README.md", "public-result.json")
    ).lower()

    assert not re.search(r"[a-z]:[\\/]", package)
    forbidden = ("artifact_text", "expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id")
    assert all(token not in package for token in forbidden)
