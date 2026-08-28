"""Provider-free, source-bound HANNA execution-freeze manifests."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from offline_harness import MODEL_TARGETS, SAMPLER, enumerate_balanced_candidates, validate_candidates
from study import CONTRACT, _is_hash, _read_bytes_checked, _exact, canonical, checked_path, derive_eligible_map, derive_split_manifest, sha256, validate_split_manifest


STUDY_ID = CONTRACT["study_id"]
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ROUTES = {
    "gpt-5.6-sol": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "transport_identity": "openai_responses_api_v1", "paid_api": False, "no_charge_proof_required_before_contact": "trusted_zero_charge_route_receipt"},
    "grok-4.6": {"provider": "xai", "model": "grok-4.6", "reasoning_effort": "high", "transport_identity": "xai_chat_completions_api_v1", "paid_api": False, "no_charge_proof_required_before_contact": "trusted_zero_charge_route_receipt"},
}


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def response_schema() -> dict[str, Any]:
    dimensions = {name: {"type": "number", "minimum": 0, "maximum": 5} for name in DIMENSIONS}
    evidence = {name: {"type": "string", "minLength": 1} for name in DIMENSIONS}
    coverage = {name: {"type": "boolean"} for name in DIMENSIONS}
    return {
        "format_version": 1,
        "type": "object",
        "additionalProperties": False,
        "required": ["scores", "evidence", "coverage"],
        "properties": {
            "scores": {"type": "object", "additionalProperties": False, "required": list(DIMENSIONS), "properties": dimensions},
            "evidence": {"type": "object", "additionalProperties": False, "required": list(DIMENSIONS), "properties": evidence},
            "coverage": {"type": "object", "additionalProperties": False, "required": list(DIMENSIONS), "properties": coverage},
        },
    }


def response_schema_bytes() -> bytes:
    return canonical(response_schema())


def _source_material(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, dict[str, str]]:
    eligible = derive_eligible_map(frozen_successor_path, hanna_csv_path)
    raw = _read_bytes_checked(checked_path(hanna_csv_path, must_exist=True))
    if _hash_bytes(raw) != CONTRACT["dataset"]["csv_sha256"]:
        raise ValueError("HANNA execution CSV hash drifted")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("HANNA execution CSV cannot be decoded") from exc
    stories: dict[str, tuple[str, str]] = {}
    for row in rows:
        story_id, prompt, story = row.get("Story ID"), row.get("Prompt"), row.get("Story")
        if not all(isinstance(value, str) for value in (story_id, prompt, story)):
            raise ValueError("HANNA execution CSV row is malformed")
        observed = (prompt, story)
        if story_id in stories and stories[story_id] != observed:
            raise ValueError("HANNA execution source item is inconsistent")
        stories[story_id] = observed
    result: dict[str, dict[str, str]] = {}
    for item in eligible:
        source = stories.get(item["story_id"])
        if source is None:
            raise ValueError("HANNA execution source item is missing")
        prompt, story = source
        if _hash_bytes(prompt.encode("utf-8")) != item["prompt_sha256"]:
            raise ValueError("HANNA execution prompt hash drifted")
        result[item["item_id"]] = {"prompt": prompt, "story": story, "prompt_sha256": item["prompt_sha256"], "story_sha256": _hash_bytes(story.encode("utf-8"))}
    return result


def _payload_bytes(*, item: Mapping[str, str], candidate: Mapping[str, Any]) -> bytes:
    return canonical({
        "format_version": 1,
        "study_id": STUDY_ID,
        "task": "score the supplied writing against the supplied prompt using the exact six-dimension schema",
        "prompt": item["prompt"],
        "writing": item["story"],
        "instruction": candidate["instruction_bytes"].decode("utf-8"),
        "profile": json.loads(candidate["profile_bytes"].decode("utf-8")),
        "response_schema": response_schema(),
    })


def _schedule(candidates: Sequence[Mapping[str, Any]], split: Mapping[str, Any], sources: Mapping[str, Mapping[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in sorted((row for row in split["items"] if row["partition"] in {"train", "development"}), key=lambda row: row["item_id"]):
        source = sources[item["item_id"]]
        for candidate in candidates:
            task_bytes = _payload_bytes(item=source, candidate=candidate)
            for model in MODEL_TARGETS:
                route = ROUTES[model]
                cell_key = {"item_id": item["item_id"], "prompt_group_id": item["prompt_group_id"], "partition": item["partition"], "candidate_id": candidate["candidate_id"], "provider": route["provider"], "model": route["model"]}
                rows.append({
                    **cell_key,
                    "cell_id": "cell-" + sha256(cell_key)[:16],
                    "task_payload_sha256": _hash_bytes(task_bytes),
                    "candidate_instruction_sha256": candidate["instruction_sha256"],
                    "candidate_profile_sha256": candidate["profile_sha256"],
                    "response_schema_sha256": _hash_bytes(response_schema_bytes()),
                    "prompt_sha256": source["prompt_sha256"],
                    "story_sha256": source["story_sha256"],
                })
    return rows


def _canaries() -> list[dict[str, Any]]:
    schema_sha = _hash_bytes(response_schema_bytes())
    rows = []
    for model in MODEL_TARGETS:
        route = ROUTES[model]
        task = canonical({"format_version": 1, "kind": "public_synthetic_transport_canary", "prompt": "Synthetic test prompt.", "writing": "Synthetic test writing.", "response_schema": response_schema()})
        identity = {"provider": route["provider"], "model": route["model"], "task_payload_sha256": _hash_bytes(task)}
        rows.append({**identity, "canary_id": "canary-" + sha256(identity)[:16], "response_schema_sha256": schema_sha, "metric_eligible": False, "selection_eligible": False})
    return rows


def acknowledgement_preview(disclosure: Mapping[str, Any]) -> dict[str, Any]:
    """Describe the future external acknowledgement without minting one locally."""
    if not isinstance(disclosure, Mapping):
        raise ValueError("HANNA acknowledgement preview requires a disclosure")
    return {"format_version": 1, "study_id": STUDY_ID, "acknowledgement_kind": "local_first_remote_execution", "disclosure_sha256": None, "acknowledged": False, "external_owner_attestation_required": True, "trusted_executor_required": True}


def future_native_receipt_contract() -> dict[str, Any]:
    """A non-accepting preview of evidence a future trusted executor must supply."""
    return {"format_version": 1, "study_id": STUDY_ID, "status": "unimplemented", "required_fields": ["cell_id", "provider", "model", "transport_identity", "reasoning_effort", "paid_api", "zero_charge_route_receipt_sha256", "request_sha256", "status", "session_id", "response_sha256", "response"], "acceptance": "UNIMPLEMENTED_BLOCKER"}


def derive_execution_freeze(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    candidates = enumerate_balanced_candidates()
    validate_candidates(candidates)
    split = derive_split_manifest(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    validate_split_manifest(split, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    sources = _source_material(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    schedule = _schedule(candidates, split, sources)
    candidate_commitments = [{key: candidate[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256")} for candidate in candidates]
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_execution_freeze",
        "provider_execution": "not_implemented",
        "split_sha256": sha256(split),
        "frozen_successor_sha256": _hash_bytes(_read_bytes_checked(checked_path(frozen_successor_path, must_exist=True))),
        "hanna_csv_sha256": _hash_bytes(_read_bytes_checked(checked_path(hanna_csv_path, must_exist=True))),
        "candidate_commitments": candidate_commitments,
        "response_schema_sha256": _hash_bytes(response_schema_bytes()),
        "sampler": SAMPLER,
        "routes": [ROUTES[model] for model in MODEL_TARGETS],
        "schedule": schedule,
        "schedule_sha256": sha256(schedule),
        "canaries": _canaries(),
        "confirmation": {"status": "structurally_unreachable", "cells": 76},
    }


def execution_disclosure(freeze: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    validate_execution_freeze(freeze, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "mode": "prepared_execution_freeze_only",
        "execution_freeze_sha256": sha256(freeze),
        "remote_destinations": [ROUTES[model] for model in MODEL_TARGETS],
        "artifacts_leaving_machine": ["per-cell prompt and writing bytes", "candidate instruction/profile bytes", "response-schema bytes"],
        "local_commitments": {"schedule_sha256": freeze["schedule_sha256"], "response_schema_sha256": freeze["response_schema_sha256"], "frozen_successor_sha256": freeze["frozen_successor_sha256"], "hanna_csv_sha256": freeze["hanna_csv_sha256"]},
        "acknowledgement_preview": acknowledgement_preview(freeze),
        "future_native_receipt_contract": future_native_receipt_contract(),
        "not_a_dispatch_authorization": True,
    }


def validate_execution_freeze(value: Mapping[str, Any], *, frozen_successor_path: Path, hanna_csv_path: Path) -> None:
    keys = {"format_version", "study_id", "kind", "provider_execution", "split_sha256", "frozen_successor_sha256", "hanna_csv_sha256", "candidate_commitments", "response_schema_sha256", "sampler", "routes", "schedule", "schedule_sha256", "canaries", "confirmation"}
    _exact(value, keys, "execution freeze")
    if value["format_version"] != 1 or value["study_id"] != STUDY_ID or value["kind"] != "provider_free_execution_freeze" or value["provider_execution"] != "not_implemented" or value["sampler"] != SAMPLER or value["routes"] != [ROUTES[model] for model in MODEL_TARGETS] or value["confirmation"] != {"status": "structurally_unreachable", "cells": 76}:
        raise ValueError("HANNA execution freeze identity drifted")
    if not all(_is_hash(value[key]) for key in ("split_sha256", "frozen_successor_sha256", "hanna_csv_sha256", "response_schema_sha256", "schedule_sha256")) or value["response_schema_sha256"] != _hash_bytes(response_schema_bytes()) or value["schedule_sha256"] != sha256(value["schedule"]):
        raise ValueError("HANNA execution freeze hash drifted")
    candidates = enumerate_balanced_candidates()
    expected_candidates = [{key: candidate[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256")} for candidate in candidates]
    if value["candidate_commitments"] != expected_candidates:
        raise ValueError("HANNA execution candidate commitments drifted")
    if not isinstance(value["schedule"], list) or len(value["schedule"]) != 732:
        raise ValueError("HANNA execution schedule geometry drifted")
    ids, dimensions = set(), set()
    for row in value["schedule"]:
        _exact(row, {"item_id", "prompt_group_id", "partition", "candidate_id", "provider", "model", "cell_id", "task_payload_sha256", "candidate_instruction_sha256", "candidate_profile_sha256", "response_schema_sha256", "prompt_sha256", "story_sha256"}, "execution cell")
        if row["partition"] not in {"train", "development"} or row["cell_id"] in ids or not row["cell_id"].startswith("cell-") or not all(_is_hash(row[key]) for key in ("task_payload_sha256", "candidate_instruction_sha256", "candidate_profile_sha256", "response_schema_sha256", "prompt_sha256", "story_sha256")):
            raise ValueError("HANNA execution cell is invalid")
        ids.add(row["cell_id"])
        dimensions.add((row["item_id"], row["candidate_id"], row["provider"], row["model"]))
    if len(dimensions) != 732:
        raise ValueError("HANNA execution cells are not unique")
    if not isinstance(value["canaries"], list) or value["canaries"] != _canaries():
        raise ValueError("HANNA transport canaries drifted")
    expected = derive_execution_freeze(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    if value != expected:
        raise ValueError("HANNA execution freeze is not the source-bound derivation")


def provider_ready_payload(*, freeze: Mapping[str, Any], cell_id: str, frozen_successor_path: Path, hanna_csv_path: Path) -> bytes:
    """Rebuild one exact, unpersisted payload; this function never dispatches it."""
    validate_execution_freeze(freeze, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    sources = _source_material(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    candidates = {row["candidate_id"]: row for row in enumerate_balanced_candidates()}
    cell = next((row for row in freeze["schedule"] if row["cell_id"] == cell_id), None)
    if cell is None:
        raise ValueError("HANNA execution cell is unknown")
    payload = _payload_bytes(item=sources[cell["item_id"]], candidate=candidates[cell["candidate_id"]])
    if _hash_bytes(payload) != cell["task_payload_sha256"]:
        raise ValueError("HANNA execution payload binding drifted")
    return payload
