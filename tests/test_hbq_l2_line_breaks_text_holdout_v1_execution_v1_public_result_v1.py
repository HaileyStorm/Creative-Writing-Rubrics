from __future__ import annotations

import json
import re
from pathlib import Path

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-text-holdout-v1-execution-v1-public-result-v1"


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_text_only_aggregate_is_complete_and_non_promoting():
    result = _result()

    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-l2-line-breaks-text-holdout-v1-execution-v1"
    assert result["execution"] == {
        "planned_calls": 24,
        "completed_calls": 24,
        "text_input_slots": 24,
        "image_slots": 0,
        "normalization_events": 0,
    }
    assert result["aggregate_cells"] == {
        "total": 8,
        "zero_of_three": 1,
        "one_of_three": 0,
        "two_of_three": 1,
        "three_of_three": 6,
    }
    assert result["target_control_cells"] == {
        "candidate": {"three_of_three": 3, "below_three_of_three": 1},
        "control": {"three_of_three": 3, "below_three_of_three": 1},
    }
    assert result["decision"] == "NO_GO"
    assert result["promotion"] == "none"


def test_settlement_bindings_are_exact_sha256_commitments_only():
    bindings = _result()["source_bindings"]

    assert bindings == {
        "execution_claim_sha256": "01002de156801cb753005c2a18d84edd6a6e09ca5790598f91ec46740178d1f8",
        "prepared_settlement_sha256": "39f94e0e5b8a70d827787e203bb2199665ab7738ed4ee0c0781509fed3e69d79",
        "settlement_sha256": "b15af6fbf4832b30557d691c91491ba56df03a4754138752e78fa249f1ba9f1b",
        "public_aggregate_sha256": "4b63143d52cea7a158cad96ebf55555423c068407ebb63030761d44c2dd89f51",
        "publication_marker_sha256": "f68ca9d04bb4ffa223b4e76174e7b069528a3d0473959cf7e1883cb48a56ae17",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_projection_has_no_private_execution_material_or_paths():
    payload = (ROOT / "public-result.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:[\\/]", payload + readme)
    forbidden = ("expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id")
    assert all(token not in payload for token in forbidden)
    assert Path(ROOT / "public-result.json").is_file()
