from __future__ import annotations

import json
import re
from pathlib import Path

from hbqrs.paths import book_root


ROOT = (
    book_root()
    / "evaluation-results"
    / "hbq-l2-material-context-disjoint-holdout-v1-execution-v1-public-result-v1"
)


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_disjoint_holdout_is_promotion_review_eligible_not_promoting():
    result = _result()

    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-l2-material-context-disjoint-holdout-v1-execution-v1"
    assert result["execution"] == {
        "planned_calls": 15,
        "completed_calls": 15,
        "first_attempt_accepted_calls": 15,
        "text_input_slots": 15,
        "image_slots": 0,
        "normalization_events": 0,
    }
    assert result["aggregate_cells"] == {
        "total": 5,
        "zero_of_three": 0,
        "one_of_three": 0,
        "two_of_three": 0,
        "three_of_three": 5,
    }
    assert result["aggregate_verdicts"] == {
        "YES": 6,
        "NO": 6,
        "NOT_APPLICABLE": 3,
        "CANNOT_ASSESS": 0,
    }
    assert result["decision"] == "PROMOTION_REVIEW_ELIGIBLE"
    assert result["promotion"] == "none"
    assert result["dspy"] == "not_implemented"


def test_settlement_bindings_are_exact_sha256_commitments_only():
    bindings = _result()["source_bindings"]

    assert bindings == {
        "execution_claim_sha256": "9ae9b624be52bbe1192751913f830787e8bf4d3d7021aa7f5e553db2330e9674",
        "prepared_settlement_sha256": "7899421d10b54dd44578ffb4effef08796ac3910ef6273fd6429555dc94d747d",
        "settlement_sha256": "f7c6ef58e9a352db54ab72d9f97b07fcc122b37f8dffbf4ef4f46e517a31ae4b",
        "public_aggregate_sha256": "0a05faca8d27ea8bd3b3224183874a0d861ba8e667716ebd5e304da90913e489",
        "publication_marker_sha256": "03e4d5c4e2d4c0ac294d08fb4f9d093f51ab9ba7249fe81e0e42e63bd17a550b",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_projection_has_no_private_execution_material_or_paths():
    payload = (ROOT / "public-result.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:[\\/]", payload + readme)
    forbidden = ("expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id")
    assert all(token not in payload for token in forbidden)
    assert Path(ROOT / "public-result.json").is_file()
