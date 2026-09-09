"""Provider-free, order-preserving schedule amendments for the Dryad baseline."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TRAIN_COUNT = 70
DEV_COUNT = 30
STORY_COUNT = TRAIN_COUNT + DEV_COUNT
REQUESTS_PER_STORY = 23
LEAVES_PER_STORY = 178
GROK_REUSED_PREFIX_REQUESTS = 80
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha(value: Any, label: str) -> str:
    _require(isinstance(value, str) and _HASH.fullmatch(value) is not None, f"{label} must be a lowercase SHA-256")
    return value


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _plan(plan_root: Path | str, expected_plan_sha256: str) -> tuple[Path, dict[str, Any], bytes]:
    root = Path(plan_root).absolute()
    path = root / "plan.json"
    raw = path.read_bytes()
    _require(sha256(raw) == _sha(expected_plan_sha256, "Original plan"), "Original plan hash differs")
    plan = _json(raw, "Original plan")
    _require(plan.get("dispatch_batch_size") == 8 and plan.get("empirical_batch_cap") is None, "Original plan dispatch differs")
    passes, requests = plan.get("passes"), plan.get("requests")
    _require(isinstance(passes, list) and len(passes) == 236 and isinstance(requests, list) and len(requests) == 5428,
             "Original plan geometry differs")
    return root, plan, raw


def _question_ids(records: Sequence[Mapping[str, Any]]) -> list[str]:
    flattened: list[str] = []
    for batch, record in enumerate(records, start=1):
        question_ids = record.get("question_ids")
        expected = 2 if batch == REQUESTS_PER_STORY else 8
        _require(isinstance(question_ids, list) and len(question_ids) == expected
                 and all(isinstance(item, str) and item for item in question_ids), "Question batch geometry differs")
        flattened.extend(question_ids)
    _require(len(flattened) == LEAVES_PER_STORY and len(set(flattened)) == len(flattened), "Question inventory differs")
    return flattened


def _inventory(plan: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[int, dict[str, Any]], list[str], list[str], list[str]]:
    passes = plan["passes"]
    pass_index = {row.get("pass_id"): dict(row) for row in passes if isinstance(row, Mapping) and isinstance(row.get("pass_id"), str)}
    _require(len(pass_index) == 236, "Original pass inventory differs")
    train = [row["pass_id"] for row in passes if isinstance(row, Mapping) and row.get("partition") == "TRAIN"]
    dev = [row["pass_id"] for row in passes if isinstance(row, Mapping) and row.get("partition") == "DEV"]
    _require(len(train) == 176 and len(dev) == 60 and set(train).isdisjoint(dev), "Original partition inventory differs")
    requests = plan["requests"]
    request_index = {row.get("ordinal"): dict(row) for row in requests if isinstance(row, Mapping) and type(row.get("ordinal")) is int}
    _require(set(request_index) == set(range(1, 5429)), "Original request inventory differs")
    first_records = [row for row in request_index.values() if row.get("pass_id") == passes[0].get("pass_id")]
    first_records.sort(key=lambda row: row["batch_number"])
    return pass_index, request_index, train, dev, _question_ids(first_records)


def _selected_passes(
    pass_index: Mapping[str, Mapping[str, Any]], request_index: Mapping[int, Mapping[str, Any]],
    selected_train_ids: Sequence[str], selected_dev_ids: Sequence[str], train_order: Sequence[str], dev_order: Sequence[str],
    canonical_question_ids: Sequence[str],
) -> list[dict[str, Any]]:
    train_ids, dev_ids = list(selected_train_ids), list(selected_dev_ids)
    _require(train_ids == list(train_order[:TRAIN_COUNT]) and dev_ids == list(dev_order[:DEV_COUNT]),
             "Selected IDs must be the first original partition IDs")
    selected: list[dict[str, Any]] = []
    for partition, pass_ids in (("TRAIN", train_ids), ("DEV", dev_ids)):
        for pass_id in pass_ids:
            passed = pass_index.get(pass_id)
            _require(isinstance(passed, Mapping) and passed.get("partition") == partition, "Selected pass binding differs")
            records = [row for row in request_index.values() if row.get("pass_id") == pass_id]
            records.sort(key=lambda row: row["batch_number"])
            ordinals = [row.get("ordinal") for row in records]
            _require(len(records) == REQUESTS_PER_STORY and [row.get("batch_number") for row in records] == list(range(1, 24))
                     and all(type(ordinal) is int for ordinal in ordinals), "Selected pass request geometry differs")
            _require(_question_ids(records) == list(canonical_question_ids), "Selected pass question order differs")
            selected.append({"partition": partition, "pass_id": pass_id, "logical_sample_id": passed.get("logical_sample_id"),
                             "request_ordinals": ordinals, "leaves": len(canonical_question_ids)})
    _require(len(selected) == STORY_COUNT, "Selected story count differs")
    return selected


def build_selected_schedule(
    *, plan_root: Path | str, expected_plan_sha256: str, selected_train_ids: Sequence[str], selected_dev_ids: Sequence[str],
) -> dict[str, Any]:
    """Derive the immutable 70-TRAIN/30-DEV amendment without scores or model output."""
    _root, plan, raw = _plan(plan_root, expected_plan_sha256)
    pass_index, request_index, train_order, dev_order, canonical_question_ids = _inventory(plan)
    selected = _selected_passes(pass_index, request_index, selected_train_ids, selected_dev_ids, train_order, dev_order,
                                canonical_question_ids)
    request_ordinals = [ordinal for row in selected for ordinal in row["request_ordinals"]]
    _require(len(request_ordinals) == STORY_COUNT * REQUESTS_PER_STORY and len(set(request_ordinals)) == len(request_ordinals),
             "Selected request inventory differs")
    _require(request_ordinals[:GROK_REUSED_PREFIX_REQUESTS] == list(range(1, GROK_REUSED_PREFIX_REQUESTS + 1)), "Consumed Grok prefix is not retained")
    grok_remaining = request_ordinals[GROK_REUSED_PREFIX_REQUESTS:]
    _require(grok_remaining[0] == 81 and 1610 in request_ordinals and 4049 in request_ordinals
             and request_ordinals[request_ordinals.index(1610) + 1] == 4049, "Selected TRAIN to DEV order differs")
    descriptor = {
        "schema_version": 1,
        "evidence_class": "dryad_selected_schedule_provider_free",
        "original_plan_sha256": sha256(raw),
        "selection_rule": "first_original_partition_order",
        "counts": {"stories": STORY_COUNT, "TRAIN": TRAIN_COUNT, "DEV": DEV_COUNT, "requests": len(request_ordinals),
                   "leaves_per_story": len(canonical_question_ids), "requests_per_story": REQUESTS_PER_STORY,
                   "grok_minimum_retained_prefix_requests": GROK_REUSED_PREFIX_REQUESTS,
                   "grok_remaining_requests": len(grok_remaining)},
        "selected_train_ids": list(selected_train_ids),
        "selected_dev_ids": list(selected_dev_ids),
        "question_ids": canonical_question_ids,
        "selected_passes": selected,
        "selected_request_ordinals": request_ordinals,
        "grok_remaining_request_ordinals": grok_remaining,
    }
    return descriptor


def verify_selected_schedule(*, descriptor: Mapping[str, Any], plan_root: Path | str, expected_plan_sha256: str) -> dict[str, Any]:
    required = {"schema_version", "evidence_class", "original_plan_sha256", "selection_rule", "counts", "selected_train_ids",
                "selected_dev_ids", "question_ids", "selected_passes", "selected_request_ordinals", "grok_remaining_request_ordinals"}
    _require(isinstance(descriptor, Mapping) and set(descriptor) == required, "Selected schedule schema differs")
    _require(descriptor.get("original_plan_sha256") == _sha(expected_plan_sha256, "Original plan")
             and descriptor.get("selection_rule") == "first_original_partition_order", "Selected schedule source differs")
    expected = build_selected_schedule(plan_root=plan_root, expected_plan_sha256=expected_plan_sha256,
                                       selected_train_ids=descriptor.get("selected_train_ids", []),
                                       selected_dev_ids=descriptor.get("selected_dev_ids", []))
    _require(dict(descriptor) == expected, "Selected schedule descriptor differs")
    return expected
