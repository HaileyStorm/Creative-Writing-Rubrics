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


def verify_package() -> dict[str, Any]:
    contract = load_json("study-contract.json")
    corpus = load_json("public-confirmation-corpus.json")
    if contract.get("study_id") != STUDY_ID or contract.get("development_only") is not True:
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
    return {"study_id": STUDY_ID, "provider_calls": 0, "confirmation_artifacts": 18, "confirmation_oracle_commitment": contract["bindings"]["private_confirmation_oracle_commitment_sha256"], "confirmation_calls_authorized": 0}
