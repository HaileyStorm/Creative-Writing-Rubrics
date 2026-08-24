from __future__ import annotations

import json
import re
from pathlib import Path

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-contextual-justification-treatment-v2-execution-v1-public-result-v1"


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_material_context_aggregate_is_holdout_eligible_not_promoting():
    result = _result()

    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-l2-line-breaks-contextual-justification-treatment-v2-execution-v1"
    assert result["execution"] == {
        "planned_calls": 18,
        "completed_calls": 18,
        "first_attempt_accepted_calls": 18,
        "text_input_slots": 18,
        "image_slots": 0,
        "normalization_events": 0,
    }
    assert result["aggregate_cells"] == {
        "total": 6,
        "zero_of_three": 0,
        "one_of_three": 0,
        "two_of_three": 0,
        "three_of_three": 6,
    }
    assert result["aggregate_verdicts"] == {
        "YES": 9,
        "NO": 6,
        "NOT_APPLICABLE": 3,
        "CANNOT_ASSESS": 0,
    }
    assert result["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert result["promotion"] == "none"
    assert result["dspy"] == "not_implemented"


def test_settlement_bindings_are_exact_sha256_commitments_only():
    bindings = _result()["source_bindings"]

    assert bindings == {
        "execution_claim_sha256": "55266c39a5988d840dc449fff9a4edefd7d260cd0b8fdb283889cfac5975bd99",
        "prepared_settlement_sha256": "a4a41d6a501fe4ad39ce99b2db63c37fe004725199ca10b77b041511c5b1652f",
        "settlement_sha256": "ff075d8fc501bec217ce642d20f916591cab933a41db4b28f65aae702ea94d94",
        "public_aggregate_sha256": "f29113f39e113b4e38e0aab5ad6e26b3737adcca5a698c33e366e2517ac51b85",
        "publication_marker_sha256": "38dffedd275c7783761b0d4fab03610f76d5bd097f03ef3db041494059f04681",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_projection_has_no_private_execution_material_or_paths():
    payload = (ROOT / "public-result.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:[\\/]", payload + readme)
    forbidden = ("expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id")
    assert all(token not in payload for token in forbidden)
    assert Path(ROOT / "public-result.json").is_file()
