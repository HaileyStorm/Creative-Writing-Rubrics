"""Provider-free frozen contract checks for figurative scope successor v2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-scope-dspy-successor-v2"
PENDING_ENGINE = "PENDING_PRIVATE_ENGINE_SHA256"
PENDING_FREEZE = "PENDING_PRIVATE_FREEZE_INPUTS_SHA256"
PARENT_V1 = {
    "private_aggregate_sha256": "4982e2b78572276cff717dfb130dc8742fe4f790a2b6b05dac9eb5779094094c",
    "private_result_sha256": "e640103ec7e8b9bb3e2802f1af7f07eb0adf3799185513ec783e833d18fec5df",
}
CANDIDATES = [
    {"sha256": "10e0e26ea20a33768e98abae76a343990401f673e6f0f891bfc04bfa66e39f6c", "utf8_bytes": 464},
    {"sha256": "fcd3ef7b95724f43f222061f9f2cdfcb4733348149fa517559dfcea05d1e5ab6", "utf8_bytes": 453},
]
CORRECTED_ARTIFACTS = [
    "dc6db347d6ce8a59e642d1f439b2db92547ac9577c4a2862fc4afc404e7c0a9a",
    "2b8a22e976feec16d1fe83617907d69ee73c7f8da4f73984b2618311a525bde5",
    "1a5b90e731b4bb37146b45e8badd22bf8a7a88848def8930d879970c4a501804",
]
LIMITS = {
    "proposer_calls_exact": 0,
    "reused_train_rows_exact": 28,
    "fresh_train_calls_exact": 36,
    "selection_calls_if_train_passes_exact": 32,
    "confirmation_calls_exact": 0,
    "one_provider_attempt_per_logical_call": True,
}
GATES = {
    "unaffected_train_rows_per_candidate_exact": 14,
    "fresh_train_rows_per_candidate_exact": 18,
    "both_candidates_must_pass_composite_train": True,
    "selection_cells_per_candidate_exact": 8,
    "selection_repetitions_per_cell_exact": 2,
    "both_candidates_must_pass_selection": True,
    "passing_tie_breaker": "shorter_frozen_candidate_utf8_bytes",
}
TERMINAL_STATUSES = {"NO_GO", "READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW"}
FORBIDDEN_REMOTE_ENV = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "LITELLM_API_KEY",
    "LITELLM_BASE_URL", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_contract() -> dict[str, Any]:
    return json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def private_bindings_finalized(contract: Mapping[str, Any]) -> bool:
    bindings = contract.get("bindings", {})
    return is_sha256(bindings.get("private_engine_sha256")) and is_sha256(bindings.get("private_freeze_inputs_sha256"))


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected_keys = {
        "format_version", "study_id", "development_only", "status", "parent_v1",
        "candidate_commitments", "corrected_train_artifact_sha256", "bindings",
        "limits", "gates", "allowed_terminal_statuses", "forbidden",
    }
    if set(contract) != expected_keys:
        raise ValueError("Contract surface drifted")
    if (
        contract.get("format_version") != 1
        or contract.get("study_id") != STUDY_ID
        or contract.get("development_only") is not True
        or contract.get("status") != "PENDING_EXECUTION"
        or contract.get("parent_v1") != PARENT_V1
        or contract.get("candidate_commitments") != CANDIDATES
        or contract.get("corrected_train_artifact_sha256") != CORRECTED_ARTIFACTS
        or contract.get("limits") != LIMITS
        or contract.get("gates") != GATES
        or set(contract.get("allowed_terminal_statuses", [])) != TERMINAL_STATUSES
    ):
        raise ValueError("Frozen v2 identity or gate drifted")
    bindings = contract.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != {"private_engine_sha256", "private_freeze_inputs_sha256"}:
        raise ValueError("Private binding surface drifted")
    for key, pending in (("private_engine_sha256", PENDING_ENGINE), ("private_freeze_inputs_sha256", PENDING_FREEZE)):
        if bindings[key] != pending and not is_sha256(bindings[key]):
            raise ValueError(f"{key} must be its explicit placeholder or a lowercase SHA-256")
    if len(set(CORRECTED_ARTIFACTS)) != 3 or len({item["sha256"] for item in CANDIDATES}) != 2:
        raise ValueError("Frozen commitment collision")
    return {
        "study_id": STUDY_ID,
        "status": "PENDING_EXECUTION",
        "provider_calls": 0,
        "private_bindings_finalized": private_bindings_finalized(contract),
        "fresh_train_calls": 36,
        "selection_calls_authorized": 0,
        "confirmation_calls_authorized": 0,
    }


def validate_public_outcome(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the aggregate-only terminal projection returned by the private engine."""
    expected_keys = {"study_id", "status", "calls", "train", "selection", "confirmation_accessed"}
    if set(value) != expected_keys or value.get("study_id") != STUDY_ID:
        raise ValueError("Public outcome surface drifted")
    status = value.get("status")
    if status not in TERMINAL_STATUSES or value.get("confirmation_accessed") is not False:
        raise ValueError("Invalid terminal status or confirmation access")
    calls = value.get("calls")
    if calls != {
        "proposer": 0,
        "fresh_train": 36,
        "selection": 32 if value.get("selection", {}).get("accessed") else 0,
        "confirmation": 0,
    }:
        raise ValueError("Call geometry drifted")
    train = value.get("train")
    if not isinstance(train, Mapping) or set(train) != {"reused_rows", "fresh_rows", "composite_pass_candidates"}:
        raise ValueError("TRAIN aggregate surface drifted")
    if train.get("reused_rows") != 28 or train.get("fresh_rows") != 36 or train.get("composite_pass_candidates") not in (0, 1, 2):
        raise ValueError("TRAIN aggregate arithmetic drifted")
    selection = value.get("selection")
    if not isinstance(selection, Mapping) or set(selection) != {"accessed", "calls", "full_pass_candidates"}:
        raise ValueError("Selection aggregate surface drifted")
    accessed = selection.get("accessed")
    if accessed is not (train["composite_pass_candidates"] == 2):
        raise ValueError("Selection was not gated by both composite TRAIN passes")
    if accessed:
        if selection.get("calls") != 32 or selection.get("full_pass_candidates") not in (0, 1, 2):
            raise ValueError("Selection aggregate arithmetic drifted")
    elif selection != {"accessed": False, "calls": 0, "full_pass_candidates": 0}:
        raise ValueError("Closed selection contains results")
    ready = status == "READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW"
    if ready is not (accessed and selection["full_pass_candidates"] == 2):
        raise ValueError("Terminal status disagrees with selection gate")
    return dict(value)

