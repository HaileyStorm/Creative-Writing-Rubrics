"""Offline validation for the public synthetic polarity mechanism corpus."""
from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

STATES = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})
REVERSE_DECODE = {"YES": "NO", "NO": "YES"}
CORPUS_FILENAME = "public-synthetic-wording-corpus.json"
EXPECTED_CONTRACT_PROJECTION_SHA256 = "568bf6224f0386ef174978bb354bfe746a0d78be2132a7625fd6d0aaaab0f13a"
CONTRACT_FIELDS = frozenset({"format_version", "study_id", "status", "frozen_before_execution", "production_polarity", "conditions", "reverse_decode", "input_corpus", "privacy", "interpretation_limits"})
CORPUS_FIELDS = frozenset({"format_version", "corpus_id", "classification", "privacy", "records"})
RECORD_FIELDS = frozenset({"pair_id", "split", "positive_wording", "positive_wording_bytes", "positive_wording_sha256", "negative_wording", "negative_wording_bytes", "negative_wording_sha256", "known_truth_canonical_verdict", "module_id", "question_id", "criterion_key", "criterion_ownership", "review"})
REVIEW_FIELDS = frozenset({"status", "reviewer_provenance", "ambiguity_excluded"})
PUBLIC_FILES = frozenset({"README.md", "study-contract.json", "polarity_harness.py", CORPUS_FILENAME})
WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\\\/]")
POSIX_PATH_PREFIXES = ("/" + "Users/", "/" + "home/", "file:" + "//")
SENSITIVE_TEXT = re.compile(r"(?:\b(?:r[a]w|priv[a]te|s[e]cret|t[o]ken|passw[o]rd|m[a]nuscript)(?:\b|[_-])|\bapi[_-]?key\b)", re.IGNORECASE)
NETWORK_IMPORTS = frozenset({"subprocess", "socket", "urllib", "requests", "httpx"})
EXPECTED_PUBLISHED_CONTENT_SHA256 = {
    "README.md": "b5fabd02552c810a296de2d47c4b6737c9af1697dbaadd6db9367cb09c641e25",
    "study-contract.json": "420d44a87b0cde3bbedf8e8062c70a38ab33d74a14d858353b391abc278025e0",
    CORPUS_FILENAME: "53a01142def5f02a040725f5670f2260d42d6c9529d7dda397b2f5f8b0c49c7b",
}


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonicalize_wording(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("Wording must be text")
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n").strip().encode("utf-8")


def projection_sha256(contract: Mapping[str, Any]) -> str:
    return _sha256(_canonical_json(dict(contract)))


def records_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    return _sha256(_canonical_json(list(records)))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def load_criterion_ownership(path: Path) -> dict[str, dict[str, str]]:
    try:
        ownership = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Criterion ownership registry is not valid JSON") from error
    if not isinstance(ownership, dict) or not all(
        isinstance(key, str)
        and isinstance(value, dict)
        and set(value) == {"module_id", "question_id"}
        and all(isinstance(item, str) and item for item in value.values())
        for key, value in ownership.items()
    ):
        raise ValueError("Criterion ownership registry schema drifted")
    return ownership


def validate_corpus(
    records: Sequence[Mapping[str, Any]], criterion_ownership: Mapping[str, Mapping[str, str]]
) -> None:
    if len(records) != 12 or any(set(record) != RECORD_FIELDS for record in records):
        raise ValueError("Frozen corpus record schema or count drifted")
    if [record["pair_id"] for record in records] != [f"pair-{number:02d}" for number in range(1, 13)]:
        raise ValueError("Frozen corpus order or identifiers drifted")
    questions: set[str] = set(); splits = {"development": set(), "held_out": set()}
    for record in records:
        if record["split"] not in splits or record["known_truth_canonical_verdict"] not in {"YES", "NO"}:
            raise ValueError("Frozen corpus split or truth drifted")
        expected_owner = {"module_id": record["module_id"], "question_id": record["question_id"]}
        if record["question_id"] in questions or record["criterion_key"] != record["question_id"] or record["criterion_ownership"] != expected_owner or criterion_ownership.get(record["criterion_key"]) != expected_owner:
            raise ValueError("Frozen corpus ownership is not unique")
        questions.add(record["question_id"]); splits[record["split"]].add(record["pair_id"])
        for polarity in ("positive", "negative"):
            wording = canonicalize_wording(record[f"{polarity}_wording"])
            if len(wording) != record[f"{polarity}_wording_bytes"] or _sha256(wording) != record[f"{polarity}_wording_sha256"]:
                raise ValueError("Frozen wording bytes or hashes drifted")
        if set(record["review"]) != REVIEW_FIELDS or record["review"] != {"status": "reviewed_public_synthetic_clean_negation", "reviewer_provenance": "public_synthetic_curation_v1", "ambiguity_excluded": True}:
            raise ValueError("Frozen corpus review provenance drifted")
    if any(len(ids) != 6 for ids in splits.values()) or splits["development"] & splits["held_out"] or len({record["module_id"] for record in records}) < 6:
        raise ValueError("Frozen corpus split or ownership diversity drifted")


def validate_contract(contract: Mapping[str, Any]) -> None:
    if set(contract) != CONTRACT_FIELDS or projection_sha256(contract) != EXPECTED_CONTRACT_PROJECTION_SHA256:
        raise ValueError("Pinned contract projection drifted")
    if contract["status"] != "public_synthetic_mechanism_only_no_empirical_results" or contract["frozen_before_execution"] is not True or contract["production_polarity"] != "positive_production_canonical" or contract["conditions"] != ["positive_production", "negative_semantic_negation"] or contract["reverse_decode"] != {"YES": "NO", "NO": "YES", "NOT_APPLICABLE": "NOT_APPLICABLE", "CANNOT_ASSESS": "CANNOT_ASSESS"}:
        raise ValueError("Polarity protocol state drifted")
    binding = contract["input_corpus"]
    if set(binding) != {"filename", "file_sha256", "records_sha256", "record_count", "total_wording_bytes"} or binding["filename"] != CORPUS_FILENAME or not _is_sha256(binding["file_sha256"]) or not _is_sha256(binding["records_sha256"]) or binding["record_count"] != 12 or not isinstance(binding["total_wording_bytes"], int):
        raise ValueError("Frozen corpus binding drifted")
    if contract["privacy"] != {"publication": "public synthetic wording plus aggregate metadata only", "forbid_nonpublic_content": True} or contract["interpretation_limits"] != ["This corpus is public synthetic mechanism-only material, not semantic validity evidence.", "It cannot revise the positive production scorer or polarity.", "Empirical work belongs only in a separately frozen successor with real batch artifacts and results."]:
        raise ValueError("Protocol details drifted")


def validate_corpus_file(
    contract: Mapping[str, Any],
    path: Path,
    criterion_ownership: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    validate_contract(contract)
    binding = contract["input_corpus"]
    if path.name != binding["filename"]: raise ValueError("Frozen corpus filename drifted")
    contents = path.read_bytes()
    if _sha256(contents) != binding["file_sha256"]: raise ValueError("Frozen corpus file commitment drifted")
    try: corpus = json.loads(contents)
    except json.JSONDecodeError as error: raise ValueError("Frozen corpus is not valid JSON") from error
    if not isinstance(corpus, dict) or set(corpus) != CORPUS_FIELDS or corpus.get("format_version") != 1 or corpus.get("corpus_id") != "hbq-polarity-bias-v1-public-synthetic-mechanism-only" or corpus.get("classification") != "public_synthetic_mechanism_only": raise ValueError("Frozen corpus metadata drifted")
    records = corpus.get("records")
    if not isinstance(records, list): raise ValueError("Frozen corpus records must be a list")
    validate_corpus(records, criterion_ownership)
    if records_sha256(records) != binding["records_sha256"] or sum(record["positive_wording_bytes"] + record["negative_wording_bytes"] for record in records) != binding["total_wording_bytes"]: raise ValueError("Frozen corpus semantic commitment drifted")
    return records


def reverse_decode_verdict(record: Mapping[str, Any]) -> dict[str, Any]:
    decoded = deepcopy(dict(record))
    if decoded.get("verdict") not in STATES: raise ValueError("Polarity harness received an invalid verdict state")
    decoded["verdict"] = REVERSE_DECODE.get(decoded["verdict"], decoded["verdict"])
    return decoded


def canonicalize_verdict(record: Mapping[str, Any], polarity: str) -> dict[str, Any]:
    if polarity == "positive_production":
        if record.get("verdict") not in STATES: raise ValueError("Polarity harness received an invalid verdict state")
        return deepcopy(dict(record))
    if polarity == "negative_semantic_negation": return reverse_decode_verdict(record)
    raise ValueError("Unknown polarity")


def _scan_text(relative: str, value: str) -> None:
    if WINDOWS_PATH.search(value) or any(prefix in value for prefix in POSIX_PATH_PREFIXES):
        raise ValueError(f"Publication path in {relative}")
    if SENSITIVE_TEXT.search(value):
        raise ValueError(f"Sensitive publication marker in {relative}")


def _walk_json(relative: str, value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _scan_text(relative, key)
            _walk_json(relative, item)
    elif isinstance(value, list):
        for item in value: _walk_json(relative, item)
    elif isinstance(value, str):
        _scan_text(relative, value)


def _is_network_import(node: ast.Import | ast.ImportFrom) -> bool:
    if isinstance(node, ast.Import):
        return any(alias.name.split(".")[0] in NETWORK_IMPORTS for alias in node.names)
    return node.module is not None and node.module.split(".")[0] in NETWORK_IMPORTS


def verify_publication(root: Path) -> None:
    files = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if files != PUBLIC_FILES:
        raise ValueError("Unexpected polarity publication artifact")
    for relative in sorted(PUBLIC_FILES):
        path = root / relative
        if relative in EXPECTED_PUBLISHED_CONTENT_SHA256 and _sha256(path.read_bytes()) != EXPECTED_PUBLISHED_CONTENT_SHA256[relative]:
            raise ValueError(f"Pinned publication content drifted in {relative}")
        text = path.read_text(encoding="utf-8")
        _scan_text(relative, text)
        if path.suffix == ".json":
            try:
                _walk_json(relative, json.loads(text))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid publication JSON in {relative}") from error
        elif path.suffix == ".py":
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    _scan_text(relative, node.value)
                if isinstance(node, (ast.Import, ast.ImportFrom)) and _is_network_import(node):
                    raise ValueError("Live execution or network publication code")
