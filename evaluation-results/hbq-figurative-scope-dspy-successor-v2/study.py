"""Provider-free verification for the settled aggregate-only v2 record."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-scope-dspy-successor-v2"
STATUS = "SETTLED_INCOMPLETE_NO_PROMOTION"
EXECUTION_COMMIT = "7febc77483f674a929d1778b7285a3a02c4d3a5a"
PRIVATE_AGGREGATE_SHA256 = "49052db5d5684be418d1b5c563615b206a31a97459189cf3b5436ccdaa363126"
PRIVATE_RESULT_SHA256 = "67bb8bbecf7abbbaf84fac5c94a583e1e87f7b4a692ee8c27291aa73ef258b61"
PUBLIC_RESULT_NAME = "public-result.json"
PUBLIC_RESULT_SHA256 = "f2128d0f9868d3608a739a6e10bbbb733f22f1117c479b87caf3115059603753"
PARENT_V1 = {
    "private_aggregate_sha256": "4982e2b78572276cff717dfb130dc8742fe4f790a2b6b05dac9eb5779094094c",
    "private_result_sha256": "e640103ec7e8b9bb3e2802f1af7f07eb0adf3799185513ec783e833d18fec5df",
}
FROZEN_CANDIDATES = [
    {"sha256": "10e0e26ea20a33768e98abae76a343990401f673e6f0f891bfc04bfa66e39f6c", "utf8_bytes": 464},
    {"sha256": "fcd3ef7b95724f43f222061f9f2cdfcb4733348149fa517559dfcea05d1e5ab6", "utf8_bytes": 453},
]
FROZEN_ARTIFACTS = [
    "dc6db347d6ce8a59e642d1f439b2db92547ac9577c4a2862fc4afc404e7c0a9a",
    "2b8a22e976feec16d1fe83617907d69ee73c7f8da4f73984b2618311a525bde5",
    "1a5b90e731b4bb37146b45e8badd22bf8a7a88848def8930d879970c4a501804",
]
FROZEN_BINDINGS = {
    "private_engine_sha256": "db7b63dc9a1f587b28b37cc6a6215c6a466978f346c7e93e5255730dc43360e5",
    "private_freeze_inputs_sha256": "5b405a3a6546da953888224d479f0bff491bf8971a11b72a3ae2854ab6c502af",
}
FROZEN_LIMITS = {
    "proposer_calls_exact": 0,
    "reused_train_rows_exact": 28,
    "fresh_train_calls_exact": 36,
    "selection_calls_if_train_passes_exact": 32,
    "confirmation_calls_exact": 0,
    "one_provider_attempt_per_logical_call": True,
}
FROZEN_GATES = {
    "unaffected_train_rows_per_candidate_exact": 14,
    "fresh_train_rows_per_candidate_exact": 18,
    "both_candidates_must_pass_composite_train": True,
    "selection_cells_per_candidate_exact": 8,
    "selection_repetitions_per_cell_exact": 2,
    "both_candidates_must_pass_selection": True,
    "passing_tie_breaker": "shorter_frozen_candidate_utf8_bytes",
}
FROZEN_TERMINAL_STATUSES = ["INCOMPLETE", "NO_GO", "READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW"]
FROZEN_FORBIDDEN = [
    "candidate_or_synthetic_text_publication",
    "controller_or_case_label_publication",
    "selection_or_held_content_publication",
    "raw_prompt_response_evidence_or_receipt_publication",
    "rubric_leaf_ownership_split_or_weight_change",
    "runtime_dspy_dependency",
    "paid_api_compatible_or_fallback_route",
    "selection_before_both_candidates_pass_composite_train",
    "confirmation_access",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def _validate_public_result(value: Mapping[str, Any]) -> None:
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "INCOMPLETE",
        "execution_commit": EXECUTION_COMMIT,
        "source_private_aggregate_sha256": PRIVATE_AGGREGATE_SHA256,
        "source_private_result_sha256": PRIVATE_RESULT_SHA256,
        "execution": {
            "logical_train_calls": 2,
            "accepted_grounded_scored_misses": 1,
            "terminal_schema_or_quote_failures": 1,
            "retries": 0,
            "selection_accessed": False,
            "selection_read": False,
            "confirmation_accessed": False,
        },
        "scored_miss": {"expected": "YES", "observed": "NO"},
        "terminal_failure": {
            "reason": "schema_or_quote_failure",
            "cause": "v2_validator_rejected_schema_valid_mixed_exact_quote_and_summary_response",
        },
        "decision": "NO_PROMOTION",
        "conclusion": "One grounded TRAIN result was a scored expected-YES/observed-NO miss. The second logical TRAIN call ended terminally when the v2 validator rejected a schema-valid mixed exact_quote+summary response. There were no retries; selection and confirmation stayed closed; this development-only result promotes no prompt, rubric wording, leaf, ownership, split, or weight change.",
    }
    if dict(value) != expected:
        raise ValueError("Public result identity, aggregate arithmetic, or privacy surface drifted")
    serialized = json.dumps(value, sort_keys=True).casefold()
    forbidden = ("c:\\", "c:/", "/users/", "session", "raw_prompt", "raw_response", "candidate_text", "case_label")
    if any(fragment in serialized for fragment in forbidden):
        raise ValueError("Public result contains prohibited private material")


def validate_public_result() -> dict[str, Any]:
    value = load_json(PUBLIC_RESULT_NAME)
    _validate_public_result(value)
    contract = load_json("study-contract.json")
    if sha256_file(ROOT / PUBLIC_RESULT_NAME) != PUBLIC_RESULT_SHA256 or contract.get("public_result_sha256") != PUBLIC_RESULT_SHA256:
        raise ValueError("Public result hash drifted")
    return {"status": value["status"], "decision": value["decision"], "logical_train_calls": value["execution"]["logical_train_calls"]}


def verify_package() -> dict[str, Any]:
    contract = load_json("study-contract.json")
    expected_keys = {
        "format_version", "study_id", "development_only", "status", "parent_v1",
        "candidate_commitments", "corrected_train_artifact_sha256", "bindings", "limits",
        "gates", "result_lineage", "public_result_sha256", "allowed_terminal_statuses", "forbidden",
    }
    if set(contract) != expected_keys:
        raise ValueError("Contract surface drifted")
    if contract.get("format_version") != 1 or contract.get("study_id") != STUDY_ID or contract.get("development_only") is not True:
        raise ValueError("Contract identity drifted")
    if contract.get("status") != STATUS or contract.get("parent_v1") != PARENT_V1:
        raise ValueError("Settled status or predecessor lineage drifted")
    if (
        contract.get("candidate_commitments") != FROZEN_CANDIDATES
        or contract.get("corrected_train_artifact_sha256") != FROZEN_ARTIFACTS
        or contract.get("bindings") != FROZEN_BINDINGS
        or contract.get("limits") != FROZEN_LIMITS
        or contract.get("gates") != FROZEN_GATES
        or contract.get("allowed_terminal_statuses") != FROZEN_TERMINAL_STATUSES
        or contract.get("forbidden") != FROZEN_FORBIDDEN
    ):
        raise ValueError("Retained immutable freeze contract drifted")
    if contract.get("result_lineage") != {
        "execution_commit": EXECUTION_COMMIT,
        "private_aggregate_sha256": PRIVATE_AGGREGATE_SHA256,
        "private_result_sha256": PRIVATE_RESULT_SHA256,
    }:
        raise ValueError("Settled private lineage drifted")
    if contract.get("public_result_sha256") != PUBLIC_RESULT_SHA256:
        raise ValueError("Pinned public result hash drifted")
    result = validate_public_result()
    return {
        "study_id": STUDY_ID,
        "status": STATUS,
        "provider_calls": 0,
        "execution_refused": True,
        "selection_accessed": False,
        "confirmation_accessed": False,
        "public_result": result,
    }
