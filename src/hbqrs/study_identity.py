"""Small, provider-free identities and summaries for repeated rubric studies."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import math
import re
from typing import Any


_SLUG = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_PATH_KEYS = frozenset({"path", "file", "filename", "directory", "root"})


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")


def _slug(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SLUG.fullmatch(value):
        raise ValueError(f"{name} must be a public-safe slug")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase 64-hex SHA-256")
    return value


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _looks_like_path(value: str) -> bool:
    return value.startswith(("/", "\\", "~", "//")) or "\\" in value or bool(re.match(r"^[A-Za-z]:/", value))


def _condition_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key = _slug(key, "condition key")
            lowered = key.casefold()
            if lowered in _PATH_KEYS or lowered.endswith(("_path", "_file", "_filename")):
                raise ValueError("condition must not contain path-like keys")
            if lowered.endswith("_sha256"):
                result[key] = _sha256(item, key)
            else:
                result[key] = _condition_value(item)
        return result
    if isinstance(value, list):
        return [_condition_value(item) for item in value]
    if isinstance(value, tuple):
        return [_condition_value(item) for item in value]
    if isinstance(value, str):
        if _looks_like_path(value):
            raise ValueError("condition must not contain path-like values")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("condition must not contain non-finite values")
        return value
    raise ValueError("condition must be JSON-compatible")


def condition_sha256(condition: Mapping[str, Any]) -> str:
    """Hash a path-free condition that commits to its prompt and rubric bytes."""
    if not isinstance(condition, Mapping) or not condition:
        raise ValueError("condition must be a nonempty mapping")
    normalized = _condition_value(condition)
    for key in ("prompt_sha256", "rubric_sha256"):
        if key not in normalized:
            raise ValueError(f"condition requires {key}")
    return sha256(_canonical(normalized)).hexdigest()


def logical_sample_id(
    *,
    study_id: str,
    artifact_id: str,
    artifact_sha256: str,
    condition: Mapping[str, Any],
    repetition: int,
    rubric_revision: str,
) -> str:
    """Return the stable identifier for one intended repeated-study slot."""
    return "sample:" + sha256(
        _canonical(
            {
                "study_id": _slug(study_id, "study_id"),
                "artifact_id": _slug(artifact_id, "artifact_id"),
                "artifact_sha256": _sha256(artifact_sha256, "artifact_sha256"),
                "condition_sha256": condition_sha256(condition),
                "repetition": _positive_int(repetition, "repetition"),
                "rubric_revision": _slug(rubric_revision, "rubric_revision"),
            }
        )
    ).hexdigest()


def _event_count(record: Mapping[str, Any], key: str) -> int:
    value = record.get(key, [])
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return _count(value, key)


def _run_counts(record: Mapping[str, Any]) -> tuple[int, int]:
    run = record.get("verified_run")
    if not isinstance(run, Mapping):
        raise ValueError("verified_run must be a mapping")
    accepted = _count(run.get("accepted_provider_call_count"), "accepted_provider_call_count")
    rejected = _count(run.get("rejected_retry_count"), "rejected_retry_count")
    attempts = _count(run.get("batch_attempt_count"), "batch_attempt_count")
    if accepted + rejected != attempts:
        raise ValueError("verified run counts must equal batch_attempt_count")
    return accepted, rejected


def _repairs(record: Mapping[str, Any], sample: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_repairs = record.get("repair_attempts", [])
    if not isinstance(raw_repairs, Sequence) or isinstance(raw_repairs, (str, bytes, bytearray)):
        raise ValueError("repair_attempts must be a sequence")
    repairs: list[dict[str, str]] = []
    for raw in raw_repairs:
        if not isinstance(raw, Mapping):
            raise ValueError("repair attempt must be a mapping")
        repair_id = _slug(raw.get("repair_id"), "repair_id")
        condition = raw.get("condition")
        if not isinstance(condition, Mapping):
            raise ValueError("repair condition must be a mapping")
        revision = _slug(raw.get("rubric_revision"), "repair rubric_revision")
        repairs.append(
            {
                "repair_id": repair_id,
                "repair_condition_sha256": condition_sha256(condition),
                "repair_rubric_revision": revision,
                "repair_logical_sample_id": logical_sample_id(
                    study_id=sample["study_id"], artifact_id=sample["artifact_id"], artifact_sha256=sample["artifact_sha256"],
                    condition=condition, repetition=sample["repetition"], rubric_revision=revision,
                ),
            }
        )
    return repairs


def _sample(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValueError("each schedule record must be a mapping")
    condition = record.get("condition")
    if not isinstance(condition, Mapping):
        raise ValueError("condition must be a mapping")
    study_id = _slug(record.get("study_id"), "study_id")
    artifact_id = _slug(record.get("artifact_id"), "artifact_id")
    artifact_sha256 = _sha256(record.get("artifact_sha256"), "artifact_sha256")
    rubric_revision = _slug(record.get("rubric_revision"), "rubric_revision")
    repetition = _positive_int(record.get("repetition"), "repetition")
    accepted_calls, rejected_retries = _run_counts(record)
    sample = {
        "study_id": study_id,
        "artifact_id": artifact_id,
        "artifact_sha256": artifact_sha256,
        "condition": _condition_value(condition),
        "condition_sha256": condition_sha256(condition),
        "repetition": repetition,
        "rubric_revision": rubric_revision,
    }
    sample["logical_sample_id"] = logical_sample_id(study_id=study_id, artifact_id=artifact_id, artifact_sha256=artifact_sha256, condition=condition, repetition=repetition, rubric_revision=rubric_revision)
    sample["accepted_provider_call_count"] = accepted_calls
    sample["rejected_retry_count"] = rejected_retries
    sample["normalization_event_count"] = _event_count(record, "normalization_events")
    sample["repair_attempts"] = _repairs(record, sample)
    return sample


def validate_schedule(records: Sequence[Mapping[str, Any]], *, repetitions: int) -> list[dict[str, Any]]:
    """Validate complete repeat slots; condition and rubric revision never pool."""
    repetitions = _positive_int(repetitions, "repetitions")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise ValueError("records must be a sequence")
    samples = [_sample(record) for record in records]
    if len({row["study_id"] for row in samples}) != 1:
        raise ValueError("schedule must contain exactly one study_id")
    duplicate_ids = [sample_id for sample_id, count in Counter(row["logical_sample_id"] for row in samples).items() if count > 1]
    if duplicate_ids:
        raise ValueError("duplicate logical sample")
    repair_ids = [repair["repair_id"] for row in samples for repair in row["repair_attempts"]]
    if len(repair_ids) != len(set(repair_ids)):
        raise ValueError("duplicate repair_id")
    groups: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(list)
    for row in samples:
        groups[(row["study_id"], row["artifact_id"], row["artifact_sha256"], row["condition_sha256"], row["rubric_revision"])].append(row["repetition"])
    expected = list(range(1, repetitions + 1))
    for values in groups.values():
        if sorted(values) != expected:
            raise ValueError("missing or noncontiguous repetitions")
    return sorted(samples, key=lambda row: (row["study_id"], row["artifact_id"], row["condition_sha256"], row["rubric_revision"], row["repetition"]))


def private_projection(records: Sequence[Mapping[str, Any]], *, repetitions: int) -> dict[str, Any]:
    """Keep each logical slot and its independently verified event counts distinct."""
    samples = validate_schedule(records, repetitions=repetitions)
    return {"format_version": 1, "repetitions_per_condition": repetitions, "logical_samples": samples}


def public_projection(records: Sequence[Mapping[str, Any]], *, repetitions: int) -> dict[str, Any]:
    """Publish only safe aggregate series; retries and repairs are not repetitions."""
    samples = validate_schedule(records, repetitions=repetitions)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in samples:
        series_id = sha256(_canonical({"condition_sha256": row["condition_sha256"], "rubric_revision": row["rubric_revision"]})).hexdigest()
        groups[(row["condition_sha256"], series_id)].append(row)
    conditions = [
        {
            "condition_sha256": condition_hash,
            "series_id": series_id,
            "logical_repetition_count": len(rows),
            "accepted_provider_call_count": sum(row["accepted_provider_call_count"] for row in rows),
            "rejected_retry_count": sum(row["rejected_retry_count"] for row in rows),
            "normalization_event_count": sum(row["normalization_event_count"] for row in rows),
            "repair_attempt_count": sum(len(row["repair_attempts"]) for row in rows),
        }
        for (condition_hash, series_id), rows in sorted(groups.items())
    ]
    return {"format_version": 1, "repetitions_per_condition": repetitions, "logical_repetition_count": len(samples), "conditions": conditions}
