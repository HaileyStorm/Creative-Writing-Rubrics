"""Frozen, provider-free contract and projection helpers for DSPy successor v1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
STUDY_ID = "hbq-figurative-scope-dspy-successor-v1"
LEAVES = {
    "S": "core.freshness_and_non_genericness.no_default_metaphors",
    "P": "penalty.purple_prose.proportion",
    "F": "penalty.purple_prose.fatigue",
}
FORBIDDEN_REMOTE_ENV = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "LITELLM_API_KEY",
    "LITELLM_BASE_URL", "ANTHROPIC_API_KEY", "AZURE_OPENAI_API_KEY",
)
MAX_SCOPE_WORDS = 180
MAX_SCOPE_CHARS = 1200
TRANSCRIPTION_SHA256 = "dedbd5af93df46df8b27b44b69de10654cd1ff214acd56a02d5610ba0a94631f"
EXECUTION_COMMIT = "d3f65b765f1588b9c536834484a141ea6d1a7918"
PRIVATE_AGGREGATE_SHA256 = "4982e2b78572276cff717dfb130dc8742fe4f790a2b6b05dac9eb5779094094c"
PRIVATE_RESULT_SHA256 = "e640103ec7e8b9bb3e2802f1af7f07eb0adf3799185513ec783e833d18fec5df"
PUBLIC_RESULT_NAME = "public-result.json"
PUBLIC_RESULT_SHA256 = "65199fbe4e8ec25ccba324ca9c310ad1235b2e81e4183611cfb591a010f37013"
PUBLIC_CONCLUSION = "No candidate reached the frozen train full-pass threshold, so selection and confirmation remain closed. This development-only result promotes no prompt, rubric wording, leaf, ownership, split, or weight change."


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def artifact_id(record: Mapping[str, Any]) -> str:
    """Use a text commitment, never a controller label, outside the oracle boundary."""
    return sha256_bytes(canonical_json({"units": record["units"]}))[:24]


def design_transcription_hash(corpus: Mapping[str, Any]) -> str:
    """Bind the reviewed source ordering without exposing its controller labels to providers."""
    entries = [(f"fxc-a{101 + index}", record["units"]) for index, record in enumerate(corpus["records"])]
    return sha256_bytes(canonical_json(entries))


def provider_projection(record: Mapping[str, Any], leaf_code: str) -> dict[str, Any]:
    if leaf_code not in LEAVES:
        raise ValueError("Unknown leaf code")
    projection: dict[str, Any] = {
        "artifact_id": artifact_id(record),
        "text": "\n".join(record["units"]),
        "leaf_id": LEAVES[leaf_code],
        "declared_scope": record["declared_scope"],
        "completion_status": record["completion_status"],
    }
    if "provider_scope_facts" in record:
        projection["scope_facts"] = record["provider_scope_facts"]
    return projection


def validate_instruction(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized or len(normalized) > MAX_SCOPE_CHARS or len(normalized.split()) > MAX_SCOPE_WORDS:
        raise ValueError("Candidate must be nonempty and within the frozen scope/materiality limit")
    forbidden = ("no_default_metaphors", "purple_prose", "weight", "bundle", "schema", "example", "demonstration", "chain of thought")
    if any(token in normalized.lower() for token in forbidden):
        raise ValueError("Candidate attempts to change a forbidden surface")
    return normalized


def validate_corpus(corpus: Mapping[str, Any]) -> None:
    records = corpus.get("records")
    if corpus.get("format_version") != 1 or not isinstance(records, list) or len(records) != 18:
        raise ValueError("Confirmation corpus geometry drifted")
    if any(set(record) - {"artifact_id", "units", "declared_scope", "completion_status", "provider_scope_facts"} for record in records):
        raise ValueError("Public corpus contains controller or oracle metadata")
    if any(not isinstance(record.get("units"), list) or not record["units"] for record in records):
        raise ValueError("Confirmation corpus text drifted")
    if len({artifact_id(record) for record in records}) != 18:
        raise ValueError("Opaque artifact identity collision")


def _validate_public_result_value(value: Mapping[str, Any]) -> None:
    expected_execution = {
        "proposer_calls": 4,
        "train_calls": 80,
        "selection_calls": 0,
        "confirmation_calls": 0,
        "accepted_calls": 84,
        "rejected_calls": 0,
        "route": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "zero_incremental_charge": "owner_attested_subscription_route_not_independent_billing_proof",
    }
    expected_train = {
        "unique_candidates": 4,
        "candidate_scores": [[18, 20], [17, 20], [17, 20], [18, 20]],
        "leaf_totals": {"stockness": [32, 32], "proportion": [30, 40], "fatigue": [8, 8]},
        "full_pass_candidates": [0, 4],
        "required_full_pass_candidates": 2,
    }
    expected_keys = {
        "format_version", "study_id", "execution_commit", "source_private_aggregate_sha256",
        "source_private_result_sha256", "execution", "train", "confirmation_accessed", "decision", "conclusion",
    }
    if set(value) != expected_keys:
        raise ValueError("Public result privacy surface drifted")
    _validate_public_result_privacy(value)
    if (
        value.get("format_version") != 1
        or value.get("study_id") != STUDY_ID
        or value.get("execution_commit") != EXECUTION_COMMIT
        or value.get("source_private_aggregate_sha256") != PRIVATE_AGGREGATE_SHA256
        or value.get("source_private_result_sha256") != PRIVATE_RESULT_SHA256
        or value.get("execution") != expected_execution
        or value.get("train") != expected_train
        or value.get("confirmation_accessed") is not False
        or value.get("decision") != "NO_GO"
    ):
        raise ValueError("Public result identity or aggregate arithmetic drifted")
    if value.get("conclusion") != PUBLIC_CONCLUSION:
        raise ValueError("Public result conclusion drifted")


def _validate_public_result_privacy(value: Mapping[str, Any]) -> None:
    forbidden_key_fragments = (
        "path", "candidate_hash", "candidate_text", "raw_prompt", "raw_response", "evidence",
        "quote", "request", "session", "oracle", "partition", "case_label", "controller",
    )

    forbidden_value_fragments = (
        "c:\\", "c:/", "/users/", "session", "raw response", "raw-response", "raw_response",
        "exact quote", "exact-quote", "exact_quote", "private",
    )

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str) or any(token in key.casefold() for token in forbidden_key_fragments):
                    raise ValueError("Public result contains private evidence metadata")
                walk(nested)
        elif isinstance(item, list):
            for nested in item:
                walk(nested)
        elif isinstance(item, str) and any(token in item.casefold() for token in forbidden_value_fragments):
            raise ValueError("Public result contains private evidence text")

    walk(value)


def validate_public_result() -> dict[str, Any]:
    value = load_json(PUBLIC_RESULT_NAME)
    contract = load_json("study-contract.json")
    if sha256_file(ROOT / PUBLIC_RESULT_NAME) != PUBLIC_RESULT_SHA256 or contract.get("public_result_sha256") != PUBLIC_RESULT_SHA256:
        raise ValueError("Public result hash drifted")
    _validate_public_result_value(value)
    return {
        "decision": value["decision"],
        "accepted_calls": value["execution"]["accepted_calls"],
        "source_private_aggregate_sha256": value["source_private_aggregate_sha256"],
    }


def verify_package() -> dict[str, Any]:
    contract = load_json("study-contract.json")
    corpus = load_json("public-confirmation-corpus.json")
    if contract.get("study_id") != STUDY_ID or contract.get("development_only") is not True or contract.get("status") != "settled_no_go_no_promotion":
        raise ValueError("Contract identity drifted")
    if contract["limits"] != {"proposer_calls_max": 4, "train_calls_max": 80, "selection_calls_max": 32, "confirmation_calls_exact": 168, "one_provider_attempt_per_logical_call": True}:
        raise ValueError("Execution limit drifted")
    commitments = ("private_confirmation_oracle_commitment_sha256", "private_predecessor_oracle_commitment_sha256", "private_predecessor_partitions_commitment_sha256", "private_selection_baseline_commitment_sha256")
    if any(not isinstance(contract["bindings"].get(name), str) or len(contract["bindings"][name]) != 64 for name in commitments):
        raise ValueError("Opaque private commitment drifted")
    if contract["bindings"].get("public_confirmation_corpus_sha256") != sha256_file(ROOT / "public-confirmation-corpus.json"):
        raise ValueError("Public corpus binding drifted")
    validate_corpus(corpus)
    if contract["bindings"].get("reviewed_transcription_sha256") != TRANSCRIPTION_SHA256 or design_transcription_hash(corpus) != TRANSCRIPTION_SHA256:
        raise ValueError("Reviewed confirmation transcription drifted")
    if contract.get("result_lineage") != {
        "execution_commit": EXECUTION_COMMIT,
        "private_aggregate_sha256": PRIVATE_AGGREGATE_SHA256,
        "private_result_sha256": PRIVATE_RESULT_SHA256,
    }:
        raise ValueError("Private result lineage drifted")
    public_result = validate_public_result()
    return {"study_id": STUDY_ID, "provider_calls": 0, "confirmation_artifacts": 18, "confirmation_oracle_commitment": contract["bindings"]["private_confirmation_oracle_commitment_sha256"], "confirmation_calls_authorized": 0, "public_result": public_result}
