#!/usr/bin/env python3
"""Recompute frozen HANNA development endpoints from exact native cell envelopes."""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import statistics
import sys
import tempfile
import unicodedata
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Sequence


HERE = Path(os.path.abspath(__file__)).parent
PARENT = HERE.parent / "hbq-human-alignment-optimizer-v1"
CONTRACT_PATH = HERE / "study-contract.json"
ANALYZE_PATH = HERE / "analyze.py"
STUDY_ID = "hbq-human-alignment-optimizer-v2"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
INPUT_KEYS = {"format_version", "study_id", "kind", "execution_freeze_sha256", "cells"}
CELL_KEYS = {"cell_id", "task_payload_sha256", "native_response_base64", "native_receipt"}
RECEIPT_KEYS = {
    "format_version", "study_id", "kind", "cell_id", "provider", "model", "transport_identity",
    "request_sha256", "native_response_sha256", "status", "physical_provider_contacts",
    "native_response_id_sha256", "native_request_id_sha256", "native_session_id_sha256", "receipt_id",
}
ATTESTATION_KEYS = {
    "format_version", "study_id", "gate_kind", "receipt_sha256", "native_response_sha256", "cell_id",
    "provider", "model", "transport_identity", "verified", "binding_verifier_id", "binding_root_id",
}
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_NATIVE_RESPONSE_BYTES = 1024 * 1024
ReceiptBindingVerifier = Callable[[Mapping[str, Any]], Mapping[str, Any]]
_PARENT_MODULES: tuple[ModuleType, ModuleType, ModuleType] | None = None

EXPECTED_GEOMETRY = {
    "eligible_items": 80,
    "prompt_groups": 39,
    "partitions": {
        "train": {"items": 48, "groups": 24},
        "development": {"items": 13, "groups": 7},
        "confirmation": {"items": 19, "groups": 8},
    },
    "candidates": 6,
    "providers": ["gpt-5.6-sol", "grok-4.6"],
    "required_native_cells": 732,
    "train_cells": 576,
    "development_cells": 156,
    "confirmation_cells": 0,
}
EXPECTED_NATIVE_EVIDENCE = {
    "format": "canonical_json_exact_raw_native_cell_receipts_v1",
    "cell_fields": ["cell_id", "task_payload_sha256", "native_response_base64", "native_receipt"],
    "caller_aggregates_accepted": False,
    "complete_schedule_required": True,
    "raw_native_bytes_hashed_without_reserialization": True,
    "receipt_binding_verifier_required": True,
    "request_response_provider_model_transport_and_contact_identity_binding_required": True,
    "cryptographically_pinned_external_trust_root": False,
    "empirical_selection_authority": "none_until_a_versioned_successor_pins_and_verifies_an_external_trust_root",
}
EXPECTED_ENDPOINT = {
    "dimensions": list(DIMENSIONS),
    "unit": "prompt_group_equal_weight",
    "development_group_count": 7,
    "within_group_aggregation": "arithmetic_mean_of_item_values_per_dimension",
    "macro_spearman": "arithmetic_mean_of_six_tie_aware_spearman_coefficients_across_seven_prompt_group_means",
    "mean_absolute_error": "arithmetic_mean_of_42_prompt_group_by_dimension_absolute_errors",
    "all_six_spearman_coefficients_required_for_every_reported_development_endpoint": True,
    "selection_preview_partition": "development",
    "selection_preview_provider": "gpt-5.6-sol",
    "tie_breakers": ["mean_absolute_error:ascending", "candidate_id:lexicographic"],
    "grok_role": "separate_descriptive_screen_guard_only",
}
EXPECTED_OPTIMIZER_INTERFACES = {
    name: {"development_only": True, "runtime_dependency": False, "selection_authority": "none"}
    for name in ("dspy", "optuna")
}
EXPECTED_CONFIRMATION = {"status": "unopened", "accepted_evidence_cells": 0, "selection_cannot_open_confirmation": True}
EXPECTED_OUTPUTS = {
    "aggregate_only": True,
    "no_overwrite_atomic_file": True,
    "provenance": ["analyze_py_sha256", "python_implementation", "python_version", "python_cache_tag", "unicode_database_version", "runtime_identity_sha256"],
    "forbidden": ["prompt prose", "story prose", "raw provider response", "session identifier", "request identifier", "local path"],
}
EXPECTED_INTERPRETATION_LIMITS = [
    "HANNA is human-reference context, not literary ground truth.",
    "A development selection is neither a production prompt nor a confirmed alignment gain.",
    "Receipt binding labels are caller-supplied and not cryptographic external trust; all metrics and the deterministic selection preview are non-empirical.",
    "Grok endpoints are descriptive and never pooled with or substituted for the Sol selector.",
    "The parent v1 Sol adapter does not transmit or natively attest its configured reasoning effort; the Grok adapter requests but does not natively attest reasoning effort.",
    "This analyzer makes no provider calls and accepts no caller-supplied aggregate metrics.",
]


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _runtime_identity() -> dict[str, Any]:
    return {
        "python_implementation": sys.implementation.name,
        "python_version": list(sys.version_info[:3]),
        "python_cache_tag": sys.implementation.cache_tag,
        "unicode_database_version": unicodedata.unidata_version,
    }


def _exact(value: Mapping[str, Any], keys: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"HANNA v2 {label} fields are invalid")


def checked_path(path: Path, *, must_exist: bool) -> Path:
    candidate = Path(os.path.abspath(path))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        metadata = os.lstat(current)
        attributes = getattr(metadata, "st_file_attributes", 0)
        if os.path.islink(current) or attributes & 0x400:
            raise ValueError("HANNA v2 paths may not contain links or reparses")
    if must_exist and not candidate.exists():
        raise ValueError(f"HANNA v2 path does not exist: {candidate}")
    return candidate


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_disjoint(*paths: Path) -> None:
    resolved = [checked_path(path, must_exist=path.exists()) for path in paths]
    for index, left in enumerate(resolved):
        for right in resolved[index + 1 :]:
            if _contains(left, right) or _contains(right, left):
                raise ValueError("HANNA v2 input and output paths must be disjoint")


def _ancestry_snapshot(path: Path) -> tuple[tuple[int, int, int, int], ...]:
    candidate = Path(os.path.abspath(path))
    current = Path(candidate.anchor)
    result = []
    for part in candidate.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            break
        metadata = os.lstat(current)
        result.append((metadata.st_dev, metadata.st_ino, metadata.st_mode, getattr(metadata, "st_file_attributes", 0)))
    return tuple(result)


def _read_bytes(path: Path, *, maximum: int | None = None) -> bytes:
    path = checked_path(path, must_exist=True)
    if not path.is_file():
        raise ValueError("HANNA v2 input is not a regular file")
    ancestry = _ancestry_snapshot(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("HANNA v2 input cannot be opened without following the accepted path") from error
    try:
        before = os.fstat(descriptor)
        if maximum is not None and before.st_size > maximum:
            raise ValueError("HANNA v2 native evidence exceeds the size limit")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    final = os.stat(path, follow_symlinks=False)
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(after) or identity(after) != identity(final) or _ancestry_snapshot(path) != ancestry:
        raise ValueError("HANNA v2 input changed while being read")
    return raw


def read_canonical_object(path: Path, *, maximum: int | None = None) -> tuple[dict[str, Any], bytes]:
    raw = _read_bytes(path, maximum=maximum)
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("HANNA v2 input must be canonical JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError("HANNA v2 input must be canonical JSON")
    return value, raw


def _snapshot(path: Path) -> dict[str, Any]:
    raw = _read_bytes(path)
    metadata = os.stat(path, follow_symlinks=False)
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "bytes": len(raw),
        "mtime_ns": metadata.st_mtime_ns,
        "sha256": sha256_bytes(raw),
    }


def _assert_snapshot(path: Path, expected: Mapping[str, Any]) -> None:
    if _snapshot(path) != dict(expected):
        raise ValueError("HANNA v2 immutable input changed during analysis")


def _load(path: Path, name: str, aliases: Mapping[str, ModuleType]) -> ModuleType:
    previous = {alias: sys.modules.get(alias) for alias in aliases}
    try:
        sys.modules.update(aliases)
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ValueError("HANNA v2 parent module cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for alias, prior in previous.items():
            if prior is None:
                sys.modules.pop(alias, None)
            else:
                sys.modules[alias] = prior


def parent_modules() -> tuple[ModuleType, ModuleType, ModuleType]:
    global _PARENT_MODULES
    if _PARENT_MODULES is None:
        study = _load(PARENT / "study.py", "_hanna_optimizer_v1_study", {})
        harness = _load(PARENT / "offline_harness.py", "_hanna_optimizer_v1_harness", {"study": study})
        freeze = _load(
            PARENT / "execution_freeze.py",
            "_hanna_optimizer_v1_freeze",
            {"study": study, "offline_harness": harness},
        )
        _PARENT_MODULES = study, harness, freeze
    return _PARENT_MODULES


def _validate_contract_semantics(contract: Mapping[str, Any]) -> None:
    _exact(
        contract,
        {
            "format_version", "study_id", "kind", "parent", "geometry", "native_evidence",
            "endpoint", "optimizer_interfaces", "confirmation", "outputs", "interpretation_limits",
        },
        "study contract",
    )
    if (
        contract["format_version"] != 1
        or contract["study_id"] != STUDY_ID
        or contract["kind"] != "provider_free_supplied_receipt_development_analyzer_selection_preview"
        or contract["geometry"] != EXPECTED_GEOMETRY
        or contract["native_evidence"] != EXPECTED_NATIVE_EVIDENCE
        or contract["endpoint"] != EXPECTED_ENDPOINT
        or contract["optimizer_interfaces"] != EXPECTED_OPTIMIZER_INTERFACES
        or contract["confirmation"] != EXPECTED_CONFIRMATION
        or contract["outputs"] != EXPECTED_OUTPUTS
        or contract["interpretation_limits"] != EXPECTED_INTERPRETATION_LIMITS
    ):
        raise ValueError("HANNA v2 critical study contract semantics drifted")
    parent = contract["parent"]
    _exact(
        parent,
        {"study_id", "study_contract_sha256", "study_source_sha256", "offline_harness_sha256", "execution_freeze_sha256"},
        "parent contract",
    )
    if parent["study_id"] != "hbq-human-alignment-optimizer-v1":
        raise ValueError("HANNA v2 parent study identity drifted")


def _validated_parent(*, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[ModuleType, ModuleType, ModuleType, dict[str, Any]]:
    try:
        contract = json.loads(_read_bytes(CONTRACT_PATH).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA v2 study contract cannot be parsed") from error
    _validate_contract_semantics(contract)
    parent = contract["parent"]
    commitments = {
        "study-contract.json": "study_contract_sha256",
        "study.py": "study_source_sha256",
        "offline_harness.py": "offline_harness_sha256",
        "execution_freeze.py": "execution_freeze_sha256",
    }
    for filename, field in commitments.items():
        if sha256_bytes(_read_bytes(PARENT / filename)) != parent[field]:
            raise ValueError(f"HANNA v2 parent {filename} bytes drifted")
    study, harness, freeze_module = parent_modules()
    freeze = freeze_module.derive_execution_freeze(
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    freeze_module.validate_execution_freeze(
        freeze,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    split = study.derive_split_manifest(
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    counts = {
        partition: sum(row["partition"] == partition for row in split["items"])
        for partition in ("train", "development", "confirmation")
    }
    group_counts = {
        partition: sum(row["partition"] == partition for row in split["groups"])
        for partition in ("train", "development", "confirmation")
    }
    if counts != {"train": 48, "development": 13, "confirmation": 19} or group_counts != {"train": 24, "development": 7, "confirmation": 8}:
        raise ValueError("HANNA v2 frozen partition geometry drifted")
    if len(freeze["schedule"]) != 732 or any(row["partition"] == "confirmation" for row in freeze["schedule"]):
        raise ValueError("HANNA v2 parent execution geometry drifted")
    return study, harness, freeze_module, freeze


def _human_targets(*, study: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, dict[str, float]]:
    eligible = study.derive_eligible_map(frozen_successor_path, hanna_csv_path)
    study.validate_eligible_map(
        eligible,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    raw = _read_bytes(hanna_csv_path)
    if sha256_bytes(raw) != study.CONTRACT["dataset"]["csv_sha256"]:
        raise ValueError("HANNA v2 dataset hash drifted")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError("HANNA v2 dataset cannot be parsed") from error
    by_story: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        by_story.setdefault(row.get("Story ID", ""), []).append(row)
    result: dict[str, dict[str, float]] = {}
    for item in eligible:
        ratings = by_story.get(item["story_id"], [])
        if len(ratings) != 3 or any(row.get("Model") != item["source_model"] for row in ratings):
            raise ValueError("HANNA v2 human-reference source rows drifted")
        if {sha256_bytes(row["Prompt"].encode("utf-8")) for row in ratings} != {item["prompt_sha256"]}:
            raise ValueError("HANNA v2 prompt binding drifted")
        means: dict[str, float] = {}
        for dimension in DIMENSIONS:
            try:
                values = [float(row[dimension]) for row in ratings]
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("HANNA v2 human-reference rating is invalid") from error
            if any(not math.isfinite(value) or value < 1 or value > 5 for value in values):
                raise ValueError("HANNA v2 human-reference rating is out of range")
            means[dimension] = statistics.fmean(values)
        result[item["item_id"]] = means
    if len(result) != 80:
        raise ValueError("HANNA v2 human-reference coverage drifted")
    return result


def _validate_scores(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != {"scores", "evidence", "coverage"}:
        raise ValueError("HANNA v2 native structured response schema drifted")
    if any(not isinstance(value.get(field), Mapping) or set(value[field]) != set(DIMENSIONS) for field in ("scores", "evidence", "coverage")):
        raise ValueError("HANNA v2 native structured response dimensions drifted")
    scores: dict[str, float] = {}
    for dimension in DIMENSIONS:
        score = value["scores"][dimension]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)) or not 0 <= float(score) <= 5:
            raise ValueError("HANNA v2 native score is invalid")
        if not isinstance(value["evidence"][dimension], str) or not value["evidence"][dimension]:
            raise ValueError("HANNA v2 native evidence text is invalid")
        if not isinstance(value["coverage"][dimension], bool):
            raise ValueError("HANNA v2 native coverage is invalid")
        scores[dimension] = float(score)
    return scores


def _extract_native(native_bytes: bytes, *, provider: str, model: str) -> tuple[dict[str, float], dict[str, bool], dict[str, Any]]:
    if len(native_bytes) > MAX_NATIVE_RESPONSE_BYTES:
        raise ValueError("HANNA v2 native response exceeds the per-cell size limit")
    try:
        native = json.loads(native_bytes.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("HANNA v2 native response bytes are not JSON") from error
    if not isinstance(native, Mapping):
        raise ValueError("HANNA v2 native response envelope is invalid")
    if provider == "openai":
        if native.get("model") != model:
            raise ValueError("HANNA v2 Sol native model identity drifted")
        response_id = native.get("id")
        if not isinstance(response_id, str) or not response_id.strip():
            raise ValueError("HANNA v2 Sol native response identifier is missing")
        choices = native.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
            raise ValueError("HANNA v2 Sol native response choice geometry drifted")
        message = choices[0].get("message")
        if not isinstance(message, Mapping) or not isinstance(message.get("content"), str):
            raise ValueError("HANNA v2 Sol native response content is missing")
        try:
            response = json.loads(message["content"], parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("HANNA v2 Sol native content is not JSON") from error
        identity = {
            "reported_provider": None,
            "reported_model": native["model"],
            "native_response_id_sha256": sha256_bytes(response_id.encode("utf-8")),
            "native_request_id_sha256": None,
            "native_session_id_sha256": None,
        }
    elif provider == "xai":
        usage = native.get("modelUsage")
        if not isinstance(usage, Mapping) or set(usage) != {"grok-4.6-build"} or not isinstance(usage["grok-4.6-build"], Mapping):
            raise ValueError("HANNA v2 Grok native model identity drifted")
        if model != "grok-4.6" or native.get("stopReason") != "end_turn" or native.get("num_turns") != 1:
            raise ValueError("HANNA v2 Grok native completion geometry drifted")
        if not all(isinstance(native.get(field), str) and native[field].strip() for field in ("sessionId", "requestId")):
            raise ValueError("HANNA v2 Grok native identifiers are missing")
        if isinstance(native.get("structuredOutputError"), str) and native["structuredOutputError"].strip():
            raise ValueError("HANNA v2 Grok native response reported a structured-output error")
        response = native.get("structuredOutput")
        identity = {
            "reported_provider": "grok",
            "reported_model": "grok-4.6-build",
            "native_response_id_sha256": None,
            "native_request_id_sha256": sha256_bytes(native["requestId"].encode("utf-8")),
            "native_session_id_sha256": sha256_bytes(native["sessionId"].encode("utf-8")),
        }
    else:
        raise ValueError("HANNA v2 native provider is unsupported")
    scores = _validate_scores(response)
    coverage = {dimension: bool(response["coverage"][dimension]) for dimension in DIMENSIONS}
    return scores, coverage, identity


def _verify_native_receipt(
    *,
    receipt: Any,
    native_bytes: bytes,
    cell: Mapping[str, Any],
    route: Mapping[str, Any],
    verifier: ReceiptBindingVerifier,
) -> dict[str, Any]:
    _exact(receipt, RECEIPT_KEYS, "native receipt")
    binding = {key: receipt[key] for key in RECEIPT_KEYS if key != "receipt_id"}
    expected_id = "native-receipt-" + sha256_bytes(canonical(binding))[:16]
    if (
        receipt["format_version"] != 1
        or receipt["study_id"] != STUDY_ID
        or receipt["kind"] != "native_cell_receipt_claim"
        or receipt["cell_id"] != cell["cell_id"]
        or receipt["provider"] != cell["provider"]
        or receipt["model"] != cell["model"]
        or receipt["transport_identity"] != route["transport_identity"]
        or receipt["request_sha256"] != cell["task_payload_sha256"]
        or receipt["native_response_sha256"] != sha256_bytes(native_bytes)
        or receipt["status"] != "success"
        or receipt["physical_provider_contacts"] != 1
        or receipt["receipt_id"] != expected_id
    ):
        raise ValueError("HANNA v2 native receipt binding is invalid")
    identifier_fields = ("native_response_id_sha256", "native_request_id_sha256", "native_session_id_sha256")
    if any(not _is_hash_or_none(receipt[field]) for field in identifier_fields) or all(receipt[field] is None for field in identifier_fields):
        raise ValueError("HANNA v2 native receipt identifiers are invalid")
    receipt_bytes = canonical(receipt)
    event = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "gate_kind": "native_cell_receipt",
        "cell": dict(cell),
        "route": dict(route),
        "receipt_bytes": receipt_bytes,
        "native_response_bytes": native_bytes,
    }
    attestation = verifier(event)
    _exact(attestation, ATTESTATION_KEYS, "receipt binding attestation")
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "gate_kind": "native_cell_receipt",
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "native_response_sha256": sha256_bytes(native_bytes),
        "cell_id": cell["cell_id"],
        "provider": cell["provider"],
        "model": cell["model"],
        "transport_identity": route["transport_identity"],
        "verified": True,
    }
    if any(attestation.get(key) != value for key, value in expected.items()):
        raise ValueError("HANNA v2 receipt binding verifier rejected the exact binding")
    if not all(isinstance(attestation.get(key), str) and attestation[key] for key in ("binding_verifier_id", "binding_root_id")):
        raise ValueError("HANNA v2 receipt binding verifier identity is invalid")
    return dict(attestation)


def _is_hash_or_none(value: Any) -> bool:
    return value is None or (isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value))


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for position in range(start, end):
            result[order[position]] = rank
        start = end
    return result


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("HANNA v2 Spearman inputs are invalid")
    left_ranks, right_ranks = _ranks(left), _ranks(right)
    left_mean, right_mean = statistics.fmean(left_ranks), statistics.fmean(right_ranks)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left_ranks, right_ranks, strict=True))
    left_scale = sum((a - left_mean) ** 2 for a in left_ranks)
    right_scale = sum((b - right_mean) ** 2 for b in right_ranks)
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / math.sqrt(left_scale * right_scale)


def _candidate_endpoint(
    rows: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, float]],
    *,
    expected_items: int,
    expected_groups: int,
) -> dict[str, Any]:
    if len(rows) != expected_items or len({row["item_id"] for row in rows}) != expected_items:
        raise ValueError("HANNA v2 candidate endpoint cell geometry drifted")
    by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        group = row.get("prompt_group_id")
        if not isinstance(group, str) or not group:
            raise ValueError("HANNA v2 candidate endpoint prompt group is invalid")
        by_group.setdefault(group, []).append(row)
    if len(by_group) != expected_groups:
        raise ValueError("HANNA v2 candidate endpoint prompt-group geometry drifted")
    dimensions: dict[str, Any] = {}
    errors: list[float] = []
    coverage: list[float] = []
    for dimension in DIMENSIONS:
        predicted = []
        human = []
        group_coverage = []
        for group in sorted(by_group):
            grouped = by_group[group]
            predicted.append(statistics.fmean(float(row["scores"][dimension]) for row in grouped))
            human.append(statistics.fmean(float(targets[row["item_id"]][dimension]) for row in grouped))
            group_coverage.append(statistics.fmean(1.0 if row["coverage"][dimension] else 0.0 for row in grouped))
        correlation = spearman(predicted, human)
        dimensions[dimension] = {
            "spearman": correlation,
            "mean_absolute_error": statistics.fmean(abs(a - b) for a, b in zip(predicted, human, strict=True)),
            "mean_coverage": statistics.fmean(group_coverage),
        }
        errors.extend(abs(a - b) for a, b in zip(predicted, human, strict=True))
        coverage.extend(group_coverage)
    correlations = [dimensions[dimension]["spearman"] for dimension in DIMENSIONS]
    return {
        "item_count": expected_items,
        "prompt_group_count": expected_groups,
        "unit": "prompt_group_equal_weight",
        "dimensions": dimensions,
        "macro_spearman": None if any(value is None for value in correlations) else statistics.fmean(correlations),
        "mean_absolute_error": statistics.fmean(errors),
        "mean_coverage": statistics.fmean(coverage),
    }


def _selection_key(row: Mapping[str, Any]) -> tuple[float, float, str]:
    endpoint = row["development"]
    if endpoint["macro_spearman"] is None:
        raise ValueError("HANNA v2 selection preview endpoint is undefined")
    return (-float(endpoint["macro_spearman"]), float(endpoint["mean_absolute_error"]), str(row["candidate_id"]))


def _recompute(
    *,
    evidence: Mapping[str, Any],
    freeze: Mapping[str, Any],
    targets: Mapping[str, Mapping[str, float]],
    candidates: Sequence[Mapping[str, Any]],
    receipt_binding_verifier: ReceiptBindingVerifier,
) -> tuple[dict[str, Any], str, str, dict[str, str]]:
    _exact(evidence, INPUT_KEYS, "native evidence")
    if evidence["format_version"] != 1 or evidence["study_id"] != STUDY_ID or evidence["kind"] != "exact_native_train_development_cell_evidence":
        raise ValueError("HANNA v2 native evidence identity is invalid")
    freeze_sha = sha256_bytes(canonical(freeze))
    if evidence["execution_freeze_sha256"] != freeze_sha:
        raise ValueError("HANNA v2 native evidence freeze binding drifted")
    cells = evidence["cells"]
    if not isinstance(cells, list) or len(cells) != 732:
        raise ValueError("HANNA v2 requires exactly 732 native cells")
    schedule = freeze["schedule"]
    if [row.get("cell_id") if isinstance(row, Mapping) else None for row in cells] != [row["cell_id"] for row in schedule]:
        raise ValueError("HANNA v2 native cells must exactly match frozen schedule order")
    observations: list[dict[str, Any]] = []
    response_chain: list[dict[str, str]] = []
    contact_identities: set[tuple[str, str | None, str | None, str | None]] = set()
    binding_identities: set[tuple[str, str]] = set()
    for supplied, cell in zip(cells, schedule, strict=True):
        _exact(supplied, CELL_KEYS, "native cell")
        if supplied["cell_id"] != cell["cell_id"] or supplied["task_payload_sha256"] != cell["task_payload_sha256"]:
            raise ValueError("HANNA v2 native cell request binding drifted")
        route = next((row for row in freeze["routes"] if row.get("model") == cell["model"]), None)
        if not isinstance(route, Mapping):
            raise ValueError("HANNA v2 frozen route identity drifted")
        if route["provider"] != cell["provider"] or route["model"] != cell["model"]:
            raise ValueError("HANNA v2 frozen route identity drifted")
        encoded = supplied["native_response_base64"]
        if not isinstance(encoded, str):
            raise ValueError("HANNA v2 native response encoding is invalid")
        try:
            native_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
        except (UnicodeEncodeError, ValueError) as error:
            raise ValueError("HANNA v2 native response encoding is invalid") from error
        scores, coverage, reported = _extract_native(native_bytes, provider=cell["provider"], model=cell["model"])
        receipt = supplied["native_receipt"]
        attestation = _verify_native_receipt(
            receipt=receipt,
            native_bytes=native_bytes,
            cell=cell,
            route=route,
            verifier=receipt_binding_verifier,
        )
        if (
            receipt["native_response_id_sha256"] != reported["native_response_id_sha256"]
            or receipt["native_request_id_sha256"] != reported["native_request_id_sha256"]
            or receipt["native_session_id_sha256"] != reported["native_session_id_sha256"]
        ):
            raise ValueError("HANNA v2 native receipt identifier binding drifted")
        contact_identity = (
            cell["provider"],
            receipt["native_response_id_sha256"],
            receipt["native_request_id_sha256"],
            receipt["native_session_id_sha256"],
        )
        if contact_identity in contact_identities:
            raise ValueError("HANNA v2 native contact identity is duplicated")
        contact_identities.add(contact_identity)
        binding_identities.add((attestation["binding_verifier_id"], attestation["binding_root_id"]))
        observations.append({
            "cell_id": cell["cell_id"],
            "candidate_id": cell["candidate_id"],
            "item_id": cell["item_id"],
            "prompt_group_id": cell["prompt_group_id"],
            "partition": cell["partition"],
            "provider": cell["provider"],
            "model": cell["model"],
            "scores": scores,
            "coverage": coverage,
            "reported_identity": {"provider": reported["reported_provider"], "model": reported["reported_model"]},
        })
        response_chain.append({
            "cell_id": cell["cell_id"],
            "native_response_sha256": sha256_bytes(native_bytes),
            "receipt_sha256": sha256_bytes(canonical(receipt)),
        })
    if len(binding_identities) != 1:
        raise ValueError("HANNA v2 native receipts must share one binding verifier and root label")
    candidate_ids = [row["candidate_id"] for row in candidates]
    providers: dict[str, Any] = {}
    for model in ("gpt-5.6-sol", "grok-4.6"):
        reported_identities = {
            (row["reported_identity"]["provider"], row["reported_identity"]["model"])
            for row in observations if row["model"] == model
        }
        if len(reported_identities) != 1:
            raise ValueError("HANNA v2 native reported provider/model identity is inconsistent")
        candidate_metrics = []
        for candidate in candidates:
            item = {
                "candidate_id": candidate["candidate_id"],
                "candidate_sha256": candidate["candidate_sha256"],
            }
            rows = [
                row for row in observations
                if row["model"] == model and row["candidate_id"] == candidate["candidate_id"] and row["partition"] == "development"
            ]
            item["development"] = _candidate_endpoint(rows, targets, expected_items=13, expected_groups=7)
            candidate_metrics.append(item)
        if [row["candidate_id"] for row in candidate_metrics] != candidate_ids:
            raise ValueError("HANNA v2 frozen candidate identity drifted")
        providers[model] = {
            "role": "development_selector" if model == "gpt-5.6-sol" else "separate_descriptive_screen_guard_only",
            "candidate_metrics": candidate_metrics,
            "reported_identity": next(iter(reported_identities)),
        }
    if any(
        row["development"]["macro_spearman"] is None
        for provider in providers.values()
        for row in provider["candidate_metrics"]
    ):
        raise ValueError("HANNA v2 reported development endpoints require six defined dimension correlations for every candidate")
    sol_metrics = providers["gpt-5.6-sol"]["candidate_metrics"]
    selected = min(sol_metrics, key=_selection_key)["candidate_id"]
    verifier_id, root_id = next(iter(binding_identities))
    return providers, selected, sha256_bytes(canonical(response_chain)), {"binding_verifier_id": verifier_id, "binding_root_id": root_id}


def _published_identity(path: Path) -> dict[str, Any]:
    raw = _read_bytes(path)
    metadata = os.stat(path, follow_symlinks=False)
    return {"device": metadata.st_dev, "inode": metadata.st_ino, "bytes": len(raw), "sha256": sha256_bytes(raw)}


def _remove_exact_published_link(path: Path, expected: Mapping[str, Any]) -> None:
    if not os.path.lexists(path):
        return
    first = _published_identity(path)
    second = _published_identity(path)
    if first != dict(expected) or second != dict(expected):
        raise ValueError("HANNA v2 post-link drift cleanup refused a nonmatching final")
    os.unlink(path)
    if os.path.lexists(path):
        raise ValueError("HANNA v2 exact post-link drift cleanup did not remove the final")


def _publish_no_overwrite(path: Path, payload: bytes) -> None:
    path = checked_path(path, must_exist=False)
    parent = checked_path(path.parent, must_exist=True)
    if not parent.is_dir() or path.exists() or os.path.lexists(path):
        raise ValueError("HANNA v2 output must be a new file")
    parent_ancestry = _ancestry_snapshot(parent)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_identity = _published_identity(temporary)
        if _ancestry_snapshot(parent) != parent_ancestry:
            raise ValueError("HANNA v2 output parent changed before publication")
        try:
            if os.link in os.supports_dir_fd:
                directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                directory = os.open(parent, directory_flags)
                try:
                    os.link(temporary.name, path.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
                finally:
                    os.close(directory)
            else:
                os.link(temporary, path, follow_symlinks=False)
        except FileExistsError as error:
            raise ValueError("HANNA v2 output already exists; refusing overwrite") from error
        if _ancestry_snapshot(parent) != parent_ancestry:
            _remove_exact_published_link(path, temporary_identity)
            raise ValueError("HANNA v2 output parent changed during publication")
        if _read_bytes(path) != payload:
            raise ValueError("HANNA v2 published output bytes drifted")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def analyze(
    *,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
    native_evidence_path: Path,
    output_path: Path,
    receipt_binding_verifier: ReceiptBindingVerifier,
) -> dict[str, Any]:
    paths = [
        Path(frozen_successor_path),
        Path(hanna_csv_path),
        Path(native_evidence_path),
        Path(output_path),
        CONTRACT_PATH,
        ANALYZE_PATH,
        *(PARENT / name for name in ("study-contract.json", "study.py", "offline_harness.py", "execution_freeze.py")),
    ]
    _require_disjoint(Path(frozen_successor_path), Path(hanna_csv_path), Path(native_evidence_path), Path(output_path))
    for path in paths:
        checked_path(path, must_exist=path != Path(output_path))
    immutable_paths = [path for path in paths if path != Path(output_path)]
    snapshots = {path: _snapshot(path) for path in immutable_paths}
    study, harness, _freeze_module, freeze = _validated_parent(
        frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path),
    )
    candidates = harness.enumerate_balanced_candidates()
    harness.validate_candidates(candidates)
    if len(candidates) != 6:
        raise ValueError("HANNA v2 requires exactly six frozen candidates")
    evidence, evidence_bytes = read_canonical_object(Path(native_evidence_path), maximum=MAX_INPUT_BYTES)
    targets = _human_targets(
        study=study,
        frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path),
    )
    providers, selected, native_chain_sha, binding_identity = _recompute(
        evidence=evidence,
        freeze=freeze,
        targets=targets,
        candidates=candidates,
        receipt_binding_verifier=receipt_binding_verifier,
    )
    for model, provider_summary in providers.items():
        route = next((row for row in freeze["routes"] if row.get("model") == model), None)
        if not isinstance(route, Mapping):
            raise ValueError("HANNA v2 frozen route identity drifted")
        reported_provider, reported_model = provider_summary.pop("reported_identity")
        provider_summary["identity"] = {
            "requested": {
                "provider": route["provider"],
                "model": route["model"],
                "configured_reasoning_effort": route["reasoning_effort"],
                "transport_identity": route["transport_identity"],
            },
            "reported_native": {"provider": reported_provider, "model": reported_model},
            "supplied_receipt_binding": binding_identity,
        }
        provider_summary["reasoning_attestation_limit"] = (
            "Parent v1 OpenAI chat adapter neither transmits nor natively attests its configured reasoning effort"
            if model == "gpt-5.6-sol"
            else "Parent v1 Grok CLI requests but its native envelope does not attest reasoning effort"
        )
    contract_bytes = _read_bytes(CONTRACT_PATH)
    runtime_identity = _runtime_identity()
    summary = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "development_only_native_cell_recomputation",
        "status": "supplied_receipt_metrics_nonempirical_confirmation_unopened",
        "evidence": {
            "study_contract_sha256": sha256_bytes(contract_bytes),
            "analyze_py_sha256": snapshots[ANALYZE_PATH]["sha256"],
            "runtime_identity": runtime_identity,
            "runtime_identity_sha256": sha256_bytes(canonical(runtime_identity)),
            "parent_execution_freeze_sha256": sha256_bytes(canonical(freeze)),
            "frozen_successor_sha256": snapshots[Path(frozen_successor_path)]["sha256"],
            "hanna_csv_sha256": snapshots[Path(hanna_csv_path)]["sha256"],
            "native_evidence_sha256": sha256_bytes(evidence_bytes),
            "native_evidence_bytes": len(evidence_bytes),
            "ordered_native_response_chain_sha256": native_chain_sha,
            "supplied_receipt_binding_verifier": binding_identity,
            "native_cell_count": 732,
            "train_cell_count": 576,
            "development_cell_count": 156,
            "confirmation_cell_count": 0,
        },
        "geometry": {
            "eligible_items": 80,
            "prompt_groups": 39,
            "partitions": {
                "train": {"items": 48, "groups": 24},
                "development": {"items": 13, "groups": 7},
                "confirmation": {"items": 19, "groups": 8},
            },
            "candidate_count": 6,
            "provider_count": 2,
        },
        "providers": providers,
        "selection_preview": {
            "candidate_id": selected,
            "provider": "openai",
            "model": "gpt-5.6-sol",
            "partition": "development",
            "rule": "macro_spearman_desc_then_mean_absolute_error_asc_then_candidate_id_lexicographic",
            "empirical_authority": "none_unpinned_cryptographic_trust_root",
            "production_authority": "none",
            "confirmation_authority": "none",
        },
        "confirmation": {
            "status": "unopened",
            "item_count": 19,
            "group_count": 8,
            "accepted_evidence_cells": 0,
        },
        "optimizer_interfaces": {
            "dspy": "development_only_not_imported_no_runtime_or_selection_authority",
            "optuna": "development_only_not_imported_no_runtime_or_selection_authority",
        },
        "interpretation_limits": [
            "HANNA is human-reference context, not literary ground truth.",
            "This supplied-receipt selection preview is non-empirical and is not a confirmed alignment gain or production prompt.",
            "Grok is reported separately and is not pooled with or substituted for Sol.",
        ],
        "privacy": "Aggregate-only output contains no prose, raw responses, session IDs, request IDs, or local paths.",
    }
    for path, snapshot in snapshots.items():
        _assert_snapshot(path, snapshot)
    payload = canonical(summary)
    _publish_no_overwrite(Path(output_path), payload)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-successor-contract", required=True, type=Path)
    parser.add_argument("--hanna-csv", required=True, type=Path)
    parser.add_argument("--native-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    raise ValueError(
        "HANNA v2 CLI cannot inject the required receipt-binding verifier; "
        "an approved local integration must call analyze(..., receipt_binding_verifier=...)"
    )


if __name__ == "__main__":
    raise SystemExit(main())
