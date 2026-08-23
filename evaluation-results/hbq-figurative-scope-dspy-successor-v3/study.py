"""Provider-free public contract checks for the figurative-scope v3 settlement."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-scope-dspy-successor-v3"
STATUS = "SETTLED_NO_GO"
FINAL_PARENT = {
    "private_aggregate_sha256": "49052db5d5684be418d1b5c563615b206a31a97459189cf3b5436ccdaa363126",
    "private_result_sha256": "67bb8bbecf7abbbaf84fac5c94a583e1e87f7b4a692ee8c27291aa73ef258b61",
}
FINAL_BINDINGS = {
    "private_engine_sha256": "e9f23b62a7be422957a615d0661f9c19ffbf8348062779e3578eb6eac1da6b64",
    "private_freeze_inputs_sha256": "e47ccd885e587de87c27a0e29c9f92a52531e70fa0652fbd2ce17a6f8fc61433",
}
IMPORTED_MISS = {
    "full_reconstruction_complete": True,
    "accepted_and_fully_reconstructed": True,
    "candidate_commitment_sha256": "10e0e26ea20a33768e98abae76a343990401f673e6f0f891bfc04bfa66e39f6c",
    "expected_verdict": "YES",
    "observed_verdict": "NO",
    "typed_evidence_valid": True,
    "historical_result_unchanged": True,
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_contract() -> dict[str, Any]:
    return json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def private_bindings_finalized(contract: Mapping[str, Any]) -> bool:
    parent = contract.get("parent_v2", {})
    bindings = contract.get("bindings", {})
    return all(
        is_sha256(source.get(key))
        for source, key in (
            (parent, "private_aggregate_sha256"),
            (parent, "private_result_sha256"),
            (bindings, "private_engine_sha256"),
            (bindings, "private_freeze_inputs_sha256"),
        )
    )


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected_keys = {
        "format_version", "study_id", "development_only", "status", "parent_v2", "bindings",
        "imported_train_miss", "gates", "calls", "typed_evidence_regression", "promotion", "forbidden",
    }
    if set(contract) != expected_keys:
        raise ValueError("Contract surface drifted")
    if (
        contract.get("format_version") != 1
        or contract.get("study_id") != STUDY_ID
        or contract.get("development_only") is not True
        or contract.get("status") != STATUS
        or contract.get("imported_train_miss") != IMPORTED_MISS
        or contract.get("gates") != {
            "candidates_required_exact": 2,
            "affected_cells_per_candidate_exact": 6,
            "repetitions_per_affected_cell_exact": 3,
            "all_affected_cells_must_pass": True,
            "imported_miss_is_decisive": True,
        }
        or contract.get("calls") != {
            "new_provider_calls_exact": 0,
            "selection_calls_exact": 0,
            "confirmation_calls_exact": 0,
        }
        or contract.get("typed_evidence_regression") != {
            "exact_only_valid": True,
            "summary_only_valid": True,
            "mixed_valid": True,
            "exact_quotes_must_ground": True,
            "malformed_invalid": True,
            "does_not_relabel_historical_v2_result": True,
        }
        or contract.get("promotion") != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}
    ):
        raise ValueError("Frozen v3 no-go contract drifted")
    parent, bindings = contract.get("parent_v2"), contract.get("bindings")
    if not isinstance(parent, Mapping) or set(parent) != {"public_freeze_commit", *FINAL_PARENT} or parent["public_freeze_commit"] != "7febc77483f674a929d1778b7285a3a02c4d3a5a":
        raise ValueError("v2 parent binding drifted")
    if not isinstance(bindings, Mapping) or set(bindings) != set(FINAL_BINDINGS):
        raise ValueError("Private binding surface drifted")
    if {key: parent[key] for key in FINAL_PARENT} != FINAL_PARENT or dict(bindings) != FINAL_BINDINGS:
        raise ValueError("Final private settlement binding drifted")
    if not is_sha256(IMPORTED_MISS["candidate_commitment_sha256"]):
        raise ValueError("Imported miss commitment is malformed")
    return {
        "study_id": STUDY_ID,
        "status": STATUS,
        "provider_calls": 0,
        "private_bindings_finalized": private_bindings_finalized(contract),
        "selection_calls_authorized": 0,
        "confirmation_calls_authorized": 0,
    }


def validate_typed_evidence(evidence: Sequence[Mapping[str, Any]], source_text: str) -> None:
    """Mirror the production typed-evidence shape without normalizing history."""
    if not isinstance(source_text, str) or not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)) or not evidence:
        raise ValueError("Evidence must be a nonempty typed sequence")
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {"kind", "reference", "exact_quote", "summary"}:
            raise ValueError("Evidence item shape is malformed")
        if not isinstance(item["reference"], str) or not item["reference"].strip():
            raise ValueError("Evidence reference is malformed")
        kind, quote, summary = item["kind"], item["exact_quote"], item["summary"]
        if kind == "exact_quote":
            if not isinstance(quote, str) or not quote.strip() or summary is not None:
                raise ValueError("Exact evidence is malformed")
            if quote not in source_text:
                raise ValueError("Exact evidence is ungrounded")
        elif kind == "summary":
            if quote is not None or not isinstance(summary, str) or not summary.strip():
                raise ValueError("Summary evidence is malformed")
        else:
            raise ValueError("Evidence kind is malformed")


def validate_public_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "study_id": STUDY_ID,
        "status": "NO_GO",
        "new_calls": 0,
        "train": {
            "both_candidates_must_pass": True,
            "c1_required_cell_repetitions": 3,
            "c1_maximum_possible_correct_repetitions": 2,
            "decisive_prior_accepted_misses": 1,
        },
        "selection": {"accessed": False, "read": False},
        "confirmation_accessed": False,
        "decision": "NO_PROMOTION",
    }
    if dict(value) != expected:
        raise ValueError("Public no-go settlement drifted")
    return dict(value)


def load_public_result() -> dict[str, Any]:
    return json.loads((ROOT / "public-result.json").read_text(encoding="utf-8"))


def verify_public_result() -> dict[str, Any]:
    result = load_public_result()
    expected_keys = {
        "format_version", "study_id", "status", "new_calls", "train", "selection",
        "confirmation_accessed", "decision", "private_lineage", "privacy",
    }
    if set(result) != expected_keys or result.get("format_version") != 1:
        raise ValueError("Public result surface drifted")
    outcome = {key: result[key] for key in (
        "study_id", "status", "new_calls", "train", "selection", "confirmation_accessed", "decision",
    )}
    validate_public_outcome(outcome)
    if result.get("private_lineage") != {"v2": FINAL_PARENT, "v3": {
        "private_aggregate_sha256": "bfb361e7bcd0dd0544181b9c366c5dee8c920e6175ae8b6779d79bb9ea4f077c",
        "private_result_sha256": "b67552012234580d5f89003d5d7640d138e380faee6daca3e62820602bbbc077",
    }}:
        raise ValueError("Public result lineage drifted")
    if result.get("privacy") != "aggregate_only_no_private_content":
        raise ValueError("Public result privacy declaration drifted")
    return dict(result)
