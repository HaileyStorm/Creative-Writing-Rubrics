from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-treatment-v1-execution-v1-public-result-v1"
EXACT_BYTES = {
    "README.md": "a4a90ccff646d82ad3645a052fa79801950e71f61d726620141d0adc92b3ab77",
    "public-result.json": "4d8acdd796678eba8457e230ae61a8b8472c43ca2176125f211614ce2db26b50",
}
SOURCE_BINDINGS = {
    "execution_claim_sha256": "47ca7835d9dd1ab459c83497b13f75fcbe54ceceea5d81917a1511d6817f566e",
    "settlement_sha256": "3172dda9be846f21ff4a0308b2ef0303f10123cbc6b64a51b3246ecf563661cc",
    "source_public_aggregate_sha256": "0f0de5d2a38d110e01e80664692edf4da0415131805e6e721b3e5aaa8e7bbf8a",
    "terminal_slot_records_sha256": "fcdc6f3e278b431e5e99daec2ff3cf8f50a05684ac236f31192d3816830e3f00",
}


def _validate(root: Path) -> None:
    assert root.is_dir()
    for name, expected_sha256 in EXACT_BYTES.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected_sha256

    result = json.loads((root / "public-result.json").read_text(encoding="utf-8"))
    assert result["format_version"] == 1
    assert result["study_id"] == "hbq-poetry-free-verse-repetition-treatment-v1-execution-v1"
    assert result["source_bindings"] == SOURCE_BINDINGS
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in SOURCE_BINDINGS.values())
    assert result["execution"] == {
        "planned_calls": 24,
        "completed_calls": 24,
        "first_attempt_accepted_calls": 24,
        "semantic_retries": 0,
    }
    assert result["aggregate_matches"] == {
        "candidate_target": {"matched": 3, "total": 3},
        "candidate_controls": {
            "matched": 6,
            "total": 9,
            "misses": 3,
            "miss_pattern": "one disputed NOT_APPLICABLE-versus-NO control repeated three times",
        },
        "current_target": {"matched": 2, "total": 3},
    }
    assert result["decision"] == "NO_GO"
    assert result["promotion"] == "none"
    assert result["interpretation"] == {
        "candidate_wording_substantively_falsified": False,
        "frozen_control_panel_supports_promotion": False,
        "next_step": "fresh isolated control treatment for the disputed recurrence boundary",
    }
    assert result["dspy"] == "not_used"

    package = "\n".join((root / name).read_text(encoding="utf-8") for name in EXACT_BYTES).lower()
    assert not re.search(r"[a-z]:[\\/]", package)
    forbidden = ("expected_ledger", "exact_quote", "verdict_counts", "slot_id", "case_id", "cwr-s1-final")
    assert all(token not in package for token in forbidden)


def test_public_result_is_exact_complete_and_aggregate_only():
    _validate(ROOT)


def test_tampered_copy_fails_exact_public_projection_validation(tmp_path: Path):
    copied = tmp_path / "public-result"
    shutil.copytree(ROOT, copied)
    public_result = copied / "public-result.json"
    public_result.write_text(
        public_result.read_text(encoding="utf-8").replace('"matched": 6', '"matched": 7', 1),
        encoding="utf-8",
    )

    with pytest.raises(AssertionError):
        _validate(copied)
