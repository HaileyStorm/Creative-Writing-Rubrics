"""Static privacy and integrity checks for the public blinded flip-audit packet."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-blind-flip-audit-v1"


def read_json(name: str) -> dict:
    return json.loads((PACKAGE / name).read_text(encoding="utf-8"))


def test_public_packet_has_the_declared_aggregate_counts_and_labels():
    result = read_json("results.json")
    assert result["format_version"] == 1
    assert result["study"] == "hbq-ai-writer-preface-blind-flip-audit-v1"
    assert result["comparison"] == {
        "replicated_full_prefix_no_no_vs_none_yes_yes": 19,
        "quote_valid_blinded_reviews": 3,
        "excluded_for_missing_exact_evidence": 16,
    }
    assert result["comparison"]["quote_valid_blinded_reviews"] + result["comparison"]["excluded_for_missing_exact_evidence"] == result["comparison"]["replicated_full_prefix_no_no_vs_none_yes_yes"]
    assert result["reviewer_labels"]["reviewer_a"] == {"material": 1, "minor": 1, "borderline": 1, "invalid": 0}
    assert result["reviewer_labels"]["reviewer_b"] == {"material": 0, "minor": 2, "borderline": 1, "invalid": 0}
    assert result["joint_reading"] == {
        "textually_supported": 3,
        "materiality_disputed": 3,
        "inference": "Sensitivity improved in this slice; scope or materiality specificity may fall.",
    }
    assert result["limitations"] == {
        "answers_question_per_call_or_batching": False,
        "paid_evaluation": False,
        "new_or_live_human_judging": False,
        "public_raw_evidence": False,
    }


def test_public_commitments_are_sha256_only_and_disclose_no_location():
    commitments = read_json("source-commitments.json")
    assert commitments["format_version"] == 1
    assert commitments["algorithm"] == "sha256"
    assert len(commitments["private_source_commitments"]) == 6
    assert all(re.fullmatch(r"[0-9a-f]{64}", value) for value in commitments["private_source_commitments"].values())
    assert "locations" in commitments["disclosure"]


def test_public_files_contain_no_raw_evidence_or_local_path_markers():
    public_files = sorted(PACKAGE.glob("*"))
    assert {path.name for path in public_files} == {"README.md", "results.json", "source-commitments.json"}
    combined = "\n".join(path.read_text(encoding="utf-8") for path in public_files)
    assert not re.search(r"[A-Za-z]:[\\/]", combined)
    assert "/Users/" not in combined
    assert not re.search(r"blind-[0-9a-f]{8}\b", combined)
    assert "\"item_id\"" not in combined
    assert "\"question_id\"" not in combined
    assert "\"session_id\"" not in combined
    assert "```" not in combined


def test_commitment_values_are_stable_sha256_literals():
    commitments = read_json("source-commitments.json")["private_source_commitments"]
    fingerprint = json.dumps(commitments, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(fingerprint).hexdigest() == "f3b08700ada34f867f2a881da4ebfd6c9e1c4fc8f909e14f89bf0b4338786545"
