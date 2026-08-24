from __future__ import annotations

import json
import re
from pathlib import Path

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-construct-microgate-v2-execution-v2-public-result-v1"


def _result() -> dict:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def test_settled_no_go_aggregate_is_complete_and_non_promoting():
    result = _result()

    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-l2-construct-microgate-v2-execution-v2"
    assert result["execution"] == {
        "planned_calls": 36,
        "completed_calls": 36,
        "normalization_events": 1,
        "visual_attachment_calls": 6,
    }
    assert result["cell_outcomes"] == {
        "total": 12,
        "three_of_three": 10,
        "below_three_of_three": 2,
        "target": {"total": 4, "matched_three_of_three": 4, "below_three_of_three": 0},
        "control": {"total": 8, "three_of_three": 6, "below_three_of_three": 2},
    }
    assert result["decision"] == "NO_GO"
    assert result["promotion"] == "none"


def test_source_bindings_are_exact_sha256_commitments_only():
    bindings = _result()["source_bindings"]

    assert bindings == {
        "public_aggregate_sha256": "40345192ccc0cbdb16370ff9b1fd0cb071c14fb14bde666b23c4f87aa891d988",
        "settlement_sha256": "f2f14c6a78355fbdf54bc0648ff9c2754346125d6554c0eb37f16998b0bae3e2",
        "publication_marker_sha256": "37181809c681c9a34d73ae7745adb0e5c498acd4bb4ebd69c03e2814dd2937a9",
    }
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in bindings.values())


def test_public_package_has_no_private_execution_material_or_paths():
    payload = (ROOT / "public-result.json").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:[\\/]", payload + readme)
    forbidden = ("artifact_text", "expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id")
    assert all(token not in payload for token in forbidden)
    assert Path(ROOT / "public-result.json").is_file()
