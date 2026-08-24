from __future__ import annotations

import json
import re
from pathlib import Path

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1-public-result-v1"


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_contextual_treatment_aggregate_is_complete_and_non_promoting():
    result = _result()

    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1"
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
        "one_of_three": 1,
        "two_of_three": 1,
        "three_of_three": 4,
    }
    assert result["decision"] == "NO_GO_DSPY_ELIGIBLE_ONLY"
    assert result["promotion"] == "none"


def test_settlement_bindings_are_exact_sha256_commitments_only():
    bindings = _result()["source_bindings"]

    assert bindings == {
        "execution_claim_sha256": "27945b2e706c9fa890830a79cbb32ba3dcefeff596f2d2cd1522b86ea1edeb74",
        "prepared_settlement_sha256": "11c5edae26527e06106c13b4a1ac502a627ea183d55e311d9eea6d91dc847b0a",
        "settlement_sha256": "98120328d8656b568228384e460057e3e0b732b45a81171136028966a17acb43",
        "public_aggregate_sha256": "9c7d02af9c878b53623969903730cb706350d8581fec367f3ac97a9b2c1b56f1",
        "publication_marker_sha256": "76a9cc96f5f031713a295c0e6ca2628b73c427c6a709de9e163948b02f7fce09",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_projection_has_no_private_execution_material_or_paths():
    payload = (ROOT / "public-result.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:[\\/]", payload + readme)
    forbidden = ("expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id")
    assert all(token not in payload for token in forbidden)
    assert Path(ROOT / "public-result.json").is_file()
