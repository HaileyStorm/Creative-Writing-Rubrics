"""Offline-executable, provenance-bound machinery for batch-curve v2.

This module has no provider client.  Its runner accepts an injected fake endpoint,
so the artifact proves local runner/journal/analyzer/verifier semantics only.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from itertools import combinations
import hashlib
import json
import math
from pathlib import Path
import statistics
from typing import Any

from hbqrs import compile_bundle, load_bundles, load_modules, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import HBQError, _normalize_evidence


SIZES = (1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, "all-in-one")
STACK_FIELDS = (
    "source_sha256", "bundle_id", "compiled_bundle_sha256", "question_id_sequence_sha256",
    "question_count", "provider_kind", "model", "reasoning", "fresh_sessions", "tools",
    "network", "retry_semantics", "batch_attempts", "strict_ai", "validation_feedback_policy",
    "checkpoint_format_version", "contract_projection_sha256",
)
JOURNAL_FORMAT = 1
HERE = Path(__file__).resolve().parent
CONTRACT_DIGEST_PATH = HERE / "study-contract.projection.sha256"
HARNESS_NAME = "batch_curve_harness.py"


def _same_json_value(expected: Any, actual: Any) -> bool:
    """Compare JSON values without Python's bool/int or int/float equivalence."""

    if type(expected) is not type(actual):
        return False
    if isinstance(expected, dict):
        return set(expected) == set(actual) and all(
            _same_json_value(value, actual[key]) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(expected) == len(actual) and all(
            _same_json_value(value, candidate) for value, candidate in zip(expected, actual)
        )
    return expected == actual


def _is_literal_int(value: Any) -> bool:
    return type(value) is int


def _is_nonempty_string(value: Any) -> bool:
    return type(value) is str and bool(value)


def _is_string_list(value: Any) -> bool:
    return type(value) is list and all(_is_nonempty_string(item) for item in value)


def _is_batch_size(value: Any) -> bool:
    return (_is_literal_int(value) and value in SIZES) or (
        type(value) is str and value == "all-in-one"
    )


def _is_exact_stack(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != set(STACK_FIELDS):
        return False
    integer_fields = {"question_count", "batch_attempts", "checkpoint_format_version"}
    boolean_fields = {"fresh_sessions", "strict_ai"}
    return all(
        _is_literal_int(value[field])
        if field in integer_fields
        else type(value[field]) is bool
        if field in boolean_fields
        else _is_nonempty_string(value[field])
        for field in STACK_FIELDS
    )


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def resolved_size(size: int | str, question_count: int) -> int:
    if not _is_literal_int(question_count) or question_count < 1:
        raise ValueError("Question count must be positive")
    if size == "all-in-one":
        return question_count
    if not _is_literal_int(size) or size < 1:
        raise ValueError("Batch size must be positive or all-in-one")
    return min(size, question_count)


def partition_question_ids(question_ids: Sequence[str], size: int | str) -> list[list[str]]:
    resolved = resolved_size(size, len(question_ids))
    return [list(question_ids[index:index + resolved]) for index in range(0, len(question_ids), resolved)]


def all_question_items(compiled: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The scorer's full leaf sequence: domains, gates, supplementals, penalties."""
    items = [*compiled["domain_questions"], *compiled["hard_gates"], *compiled["supplemental_questions"]]
    for group in compiled["penalty_groups"]:
        items.extend(group["questions"])
    return items


def question_ids(compiled: Mapping[str, Any]) -> list[str]:
    return [item["question"]["id"] for item in all_question_items(compiled)]


def compiled_projection(compiled: Mapping[str, Any]) -> dict[str, Any]:
    ids = question_ids(compiled)
    return {
        "bundle_id": compiled["bundle_id"], "bundle_version": compiled["bundle_version"], "question_ids": ids,
        "section_counts": {
            "domain": len(compiled["domain_questions"]), "hard_gates": len(compiled["hard_gates"]),
            "supplemental": len(compiled["supplemental_questions"]),
            "penalty": sum(len(group["questions"]) for group in compiled["penalty_groups"]),
        },
    }


def contract_projection(contract: Mapping[str, Any]) -> dict[str, Any]:
    return dict(contract)


def contract_projection_sha256(contract: Mapping[str, Any]) -> str:
    return sha256_value(contract_projection(contract))


def _is_sha256(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _pinned_contract_digest() -> str:
    if not CONTRACT_DIGEST_PATH.is_file():
        raise ValueError("Frozen contract digest companion is missing")
    value = CONTRACT_DIGEST_PATH.read_text(encoding="ascii").strip()
    if not _is_sha256(value):
        raise ValueError("Frozen contract digest companion is malformed")
    return value


def _artifact_path(relative: str) -> Path:
    path = (HERE / relative).resolve()
    try:
        path.relative_to(HERE.parents[2])
    except ValueError as exc:
        raise ValueError("Frozen artifact escapes the study root") from exc
    return path


def _verify_bound_artifact(record: Mapping[str, Any], *, label: str) -> Path:
    path = _artifact_path(str(record.get("path", "")))
    if not path.is_file() or not _is_literal_int(record.get("bytes")) or record["bytes"] < 0 or not _is_sha256(record.get("sha256")):
        raise ValueError(f"Frozen {label} binding is malformed")
    if path.stat().st_size != record["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError(f"Frozen {label} bytes drifted")
    return path


def exact_stack(contract: Mapping[str, Any]) -> dict[str, Any]:
    runtime, source = contract["runtime"], contract["source"]
    stack = {
        "source_sha256": source["sha256"], "bundle_id": runtime["bundle_id"],
        "compiled_bundle_sha256": runtime["compiled_bundle_sha256"],
        "question_id_sequence_sha256": runtime["question_id_sequence_sha256"], "question_count": runtime["question_count"],
        "provider_kind": runtime["provider_kind"], "model": runtime["model"], "reasoning": runtime["reasoning"],
        "fresh_sessions": runtime["fresh_sessions"], "tools": runtime["tools"], "network": runtime["network"],
        "retry_semantics": runtime["retry_semantics"], "batch_attempts": runtime["batch_attempts"],
        "strict_ai": runtime["strict_ai"], "validation_feedback_policy": runtime["validation_feedback_policy"],
        "checkpoint_format_version": runtime["checkpoint_format_version"], "contract_projection_sha256": _pinned_contract_digest(),
    }
    if tuple(stack) != STACK_FIELDS:
        raise AssertionError("exact stack field drift")
    return stack


def validate_contract(contract: Mapping[str, Any], compiled: Mapping[str, Any] | None = None) -> None:
    if (
        not _same_json_value(contract.get("status"), "preregistered_no_empirical_results")
        or contract.get("frozen_before_execution") is not True
    ):
        raise ValueError("Batch curve must remain a frozen preregistration")
    if not _same_json_value(list(SIZES), contract.get("batch_sizes")):
        raise ValueError("Frozen batch-size ladder drifted")
    runtime = contract.get("runtime")
    if not isinstance(runtime, Mapping) or not all(key in runtime for key in STACK_FIELDS[1:-1]):
        raise ValueError("Runtime bindings are incomplete")
    ids = runtime.get("frozen_question_ids")
    if not _is_string_list(ids) or not _is_literal_int(runtime.get("question_count")) or len(ids) != runtime["question_count"] or len(set(ids)) != len(ids):
        raise ValueError("Frozen full question sequence is incomplete")
    if not _same_json_value(hashlib.sha256("\n".join(ids).encode()).hexdigest(), runtime.get("question_id_sequence_sha256")):
        raise ValueError("Frozen question sequence hash drifted")
    blocks = contract.get("screening", {}).get("blocks")
    if not isinstance(blocks, list) or len(blocks) != 3 or any(
        type(block) is not list
        or len(block) != len(SIZES)
        or any(not _is_batch_size(size) for size in block)
        or set(block) != set(SIZES)
        for block in blocks
    ):
        raise ValueError("Frozen schedule is incomplete")
    if contract_projection_sha256(contract) != _pinned_contract_digest():
        raise ValueError("Frozen contract projection differs from its independently pinned digest")
    _verify_bound_artifact(contract.get("source", {}), label="source")
    prompt = runtime.get("prompt")
    if not isinstance(prompt, Mapping):
        raise ValueError("Frozen outbound prompt binding is missing")
    _verify_bound_artifact(prompt, label="outbound prompt")
    if not _same_json_value(runtime.get("prompt_sha256"), prompt.get("sha256")):
        raise ValueError("Frozen outbound prompt hash is inconsistent")
    runner = _artifact_path("../../../src/hbqrs/runner.py")
    if not _same_json_value(runtime.get("runner_revision_sha256"), hashlib.sha256(runner.read_bytes()).hexdigest()):
        raise ValueError("Frozen runner revision drifted")
    _verify_bound_artifact(runtime.get("harness", {}), label="batch-curve harness")
    if not _same_json_value(runtime["harness"].get("path"), HARNESS_NAME):
        raise ValueError("Frozen batch-curve harness path drifted")
    disclosure = contract.get("provider_disclosure", {})
    required = {"destination", "authorization", "retention", "local_artifacts", "provider_mapping"}
    outbound = disclosure.get("outbound_parts")
    if not required <= set(disclosure) or disclosure.get("destination", {}).get("origin") != "https://chatgpt.com" or not isinstance(outbound, list) or outbound != [
        {"name": "source", "path": contract["source"]["path"], "bytes": contract["source"]["bytes"], "sha256": contract["source"]["sha256"]},
        {"name": "question_batch", "bytes": "variable_exact_frozen_subset", "order_sha256": runtime["question_id_sequence_sha256"]},
        {"name": "judge_prompt", "path": prompt["path"], "bytes": prompt["bytes"], "sha256": prompt["sha256"]},
    ]:
        raise ValueError("Local-first provider disclosure is incomplete")
    if contract.get("recommendation_policy", {}).get("default_recommendation") is not None:
        raise ValueError("No recommendation exists before empirical validation")
    if compiled is not None:
        projection = compiled_projection(compiled)
        if not _same_json_value(projection["bundle_id"], runtime["bundle_id"]) or not _same_json_value(projection["question_ids"], ids):
            raise ValueError("Compiled bundle does not match frozen full question sequence")
        if sha256_value(projection) != runtime["compiled_bundle_sha256"]:
            raise ValueError("Compiled bundle projection drifted")


def planned_events(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_contract(contract)
    triples = ((block, within, size) for block, sizes in enumerate(contract["screening"]["blocks"], 1) for within, size in enumerate(sizes, 1))
    return [{"event": "planned", "format_version": JOURNAL_FORMAT, "sequence": sequence, "block": block,
             "within_block": within, "repetition": block, "size": size,
             "contract_projection_sha256": _pinned_contract_digest()}
            for sequence, (block, within, size) in enumerate(triples, 1)]


def _study_inputs(contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    modules = load_modules(registry_path())
    bundle = next((item for item in load_bundles(bundles_path()) if item["bundle_id"] == contract["runtime"]["bundle_id"]), None)
    if bundle is None:
        raise ValueError("Frozen bundle is unavailable for deterministic verification")
    return modules, bundle


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _strict_fixture_verdicts(
    response: Sequence[Mapping[str, Any]], expected_ids: Sequence[str], *, artifact_text: str
) -> list[dict[str, Any]]:
    if isinstance(response, (str, bytes)) or not isinstance(response, Sequence):
        raise ValueError("Fixture response must be a strict verdict sequence")
    expected_keys = {"question_id", "verdict", "confidence", "evidence", "note"}
    evidence_keys = {"kind", "reference", "exact_quote", "summary"}
    normalized: list[dict[str, Any]] = []
    for question_id, raw in zip(expected_ids, response, strict=True):
        if not isinstance(raw, Mapping) or set(raw) != expected_keys or raw.get("question_id") != question_id:
            raise ValueError("Fixture response does not preserve the exact strict verdict schema and order")
        verdict, confidence, evidence, note = raw.get("verdict"), raw.get("confidence"), raw.get("evidence"), raw.get("note")
        if verdict not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or not _is_number(confidence) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("Fixture verdict has an invalid label or confidence")
        if not isinstance(note, str) or not isinstance(evidence, list) or not evidence:
            raise ValueError("Fixture verdict lacks strict evidence or note")
        for item in evidence:
            if not isinstance(item, Mapping) or set(item) != evidence_keys or item.get("kind") not in {"exact_quote", "summary"} or not isinstance(item.get("reference"), str) or not item["reference"].strip():
                raise ValueError("Fixture verdict has invalid typed evidence")
            exact, summary = item.get("exact_quote"), item.get("summary")
            if item["kind"] == "exact_quote":
                valid = isinstance(exact, str) and bool(exact.strip()) and summary is None
            else:
                valid = isinstance(summary, str) and bool(summary.strip()) and exact is None
            if not valid:
                raise ValueError("Fixture verdict evidence kind and payload disagree")
        try:
            _normalize_evidence(evidence, question_id=question_id, artifact_text=artifact_text, context_texts=(), normalization_policy=None)
        except HBQError as exc:
            raise ValueError("Fixture verdict exact quote is not grounded in the frozen source") from exc
        normalized.append(dict(raw))
    if len(response) != len(expected_ids):
        raise ValueError("Fixture response has an incomplete or extra verdict set")
    return normalized


def _fixture_verdicts(ids: Sequence[str]) -> list[dict[str, Any]]:
    return [{"question_id": question_id, "verdict": "YES", "confidence": 1.0,
             "evidence": [{"kind": "summary", "reference": "offline-fixture", "exact_quote": None, "summary": "Deterministic fixture evidence."}],
             "note": "Deterministic fixture verdict."} for question_id in ids]


def _fixture_confidence_rows(verdicts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"question_id": item["question_id"], "verdict": item["verdict"], "assessed": item["verdict"] in {"YES", "NO"}, "weight": 1.0, "confidence": item["confidence"], "canonical_leaf_score": 1.0 if item["verdict"] == "YES" else 0.0}
        for _ in range(3) for item in verdicts
    ]


def _canonical_evaluation(modules: Sequence[dict[str, Any]], bundle: Mapping[str, Any], verdicts: Sequence[dict[str, Any]]) -> dict[str, Any]:
    report = score_bundle(modules, dict(bundle), list(verdicts))
    return {
        "canonical_observed_score": report["final_score"]["observed"],
        "canonical_coverage": report["coverage"],
        "canonical_bounds": {"lower": report["final_score"]["lower"], "upper": report["final_score"]["upper"]},
        "canonical_status": report["status"],
        "hard_gate_status": report["hard_gate_status"],
    }


def verify_journal(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    modules, bundle = _study_inputs(contract)
    validate_contract(contract, compile_bundle(modules, bundle))
    plans = planned_events(contract)
    if len(records) < len(plans) or any(
        not _same_json_value(expected, actual)
        for expected, actual in zip(plans, records[:len(plans)], strict=True)
    ):
        raise ValueError("Journal plan does not exactly bind the frozen schedule")
    tail = records[len(plans):]
    artifact_text = _verify_bound_artifact(contract["source"], label="source").read_text(encoding="utf-8")
    completed: list[dict[str, Any]] = []
    session_ids: set[str] = set()
    call_ids: set[str] = set()
    cursor = 0
    for plan in plans:
        expected_chunks = partition_question_ids(contract["runtime"]["frozen_question_ids"], plan["size"])
        all_verdicts: list[dict[str, Any]] = []
        retries = 0
        for ordinal, expected_ids in enumerate(expected_chunks, 1):
            accepted_row: Mapping[str, Any] | None = None
            for attempt in range(1, int(contract["runtime"]["batch_attempts"]) + 1):
                if cursor >= len(tail):
                    raise ValueError("Journal ends before every physical batch is accepted")
                row = tail[cursor]
                cursor += 1
                if not isinstance(row, Mapping) or type(row.get("event")) is not str or row.get("event") not in {"accepted_call", "rejected_call"}:
                    raise ValueError("Journal execution records must be physical calls before completion")
                expected_call = {**plan, "event": row["event"], "batch_ordinal": ordinal, "attempt": attempt, "question_ids": expected_ids}
                required = set(expected_call) | {"call_id", "provider"}
                if row.get("event") == "accepted_call":
                    required |= {"verdicts", "verdicts_sha256"}
                else:
                    required |= {"rejection_reason", "redacted_response_commitment_sha256"}
                if set(row) != required or any(
                    not _same_json_value(value, row.get(key))
                    for key, value in expected_call.items()
                ):
                    raise ValueError("Physical call record has unexpected fields or does not bind its ordinal, block, size, and contract")
                if not isinstance(row.get("call_id"), str) or not row["call_id"] or row["call_id"] in call_ids:
                    raise ValueError("Physical call IDs must be globally unique")
                call_ids.add(row["call_id"])
                receipt = row.get("provider", {})
                verify_provider_receipt(receipt, contract)
                session_id = receipt.get("session_id")
                if contract["runtime"]["fresh_sessions"] is True and (not isinstance(session_id, str) or session_id in session_ids):
                    raise ValueError("Fresh-session provenance was reused")
                session_ids.add(session_id)
                if row["event"] == "rejected_call":
                    if not isinstance(row.get("rejection_reason"), str) or not row["rejection_reason"]:
                        raise ValueError("Rejected-call provenance lacks a rejection reason")
                    if not _is_sha256(row.get("redacted_response_commitment_sha256")):
                        raise ValueError("Rejected-call provenance lacks a redacted response commitment")
                    retries += 1
                    continue
                accepted_row = row
                break
            if accepted_row is None:
                raise ValueError("Batch retry lineage exhausted without one accepted call")
            verdicts = _strict_fixture_verdicts(accepted_row.get("verdicts", []), expected_ids, artifact_text=artifact_text)
            if not _same_json_value(accepted_row.get("verdicts_sha256"), sha256_value(verdicts)):
                raise ValueError("Accepted strict verdict lineage hash drifted")
            all_verdicts.extend(verdicts)
        if not _same_json_value(
            contract["runtime"]["frozen_question_ids"],
            [row["question_id"] for row in all_verdicts],
        ):
            raise ValueError("Accepted verdicts do not reconstruct the frozen question sequence")
        evaluation = _canonical_evaluation(modules, bundle, all_verdicts)
        if cursor >= len(tail) or not isinstance(tail[cursor], Mapping):
            raise ValueError("Every planned cell requires one terminal completion")
        completion = tail[cursor]
        cursor += 1
        expected_completion = {**plan, "event": "completed", "requested_question_count": len(contract["runtime"]["frozen_question_ids"]), "accepted_call_question_count": len(all_verdicts), "accepted_checkpoint_count": len(expected_chunks), "retry_count": retries, "evaluation": evaluation}
        if set(completion) != set(expected_completion) or not _same_json_value(expected_completion, completion):
            raise ValueError("Completion lacks deterministic score, coverage, bounds, status, or retry lineage")
        completed.append(dict(completion))
    if cursor != len(tail):
        raise ValueError("Journal has extra or unexpected execution records")
    return completed


def verify_provider_receipt(receipt: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    """Enforce the configured Codex-to-provider identity mapping on real receipts."""
    mapping = contract["provider_disclosure"]["provider_mapping"]
    if not isinstance(receipt, Mapping):
        raise ValueError("Provider receipt must be a JSON object")
    if receipt.get("kind") == "offline_fixture":
        if not _is_nonempty_string(receipt.get("session_id")):
            raise ValueError("Offline fixture receipt lacks a session identity")
        return
    required = {"provider": mapping["required_reported_provider"], "model": mapping["required_reported_model"],
                "reasoning_effort": mapping["required_reported_reasoning_effort"]}
    if not _same_json_value(receipt.get("configured_provider_kind"), mapping["configured_provider_kind"]) or not _same_json_value(receipt.get("runner_provider_argument"), mapping["runner_provider_argument"]):
        raise ValueError("Configured provider mapping drifted")
    if not _same_json_value(receipt.get("reported"), required) or not _is_nonempty_string(receipt.get("session_id")):
        raise ValueError("Provider receipt lacks the frozen reported identity or session")


def _accepted_call_sizes(records: Sequence[Mapping[str, Any]], sequence: int) -> list[int]:
    return [len(row["question_ids"]) for row in records if row.get("event") == "accepted_call" and row.get("sequence") == sequence]


def _deep_evidence_valid(item: Mapping[str, Any], records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], stack: Mapping[str, Any]) -> bool:
    evidence = item.get("deep_validation_evidence")
    if (
        not isinstance(evidence, Mapping)
        or not _same_json_value(evidence.get("status"), "passed")
        or not _is_nonempty_string(evidence.get("path"))
        or not _is_sha256(evidence.get("sha256"))
        or not _is_literal_int(evidence.get("bytes"))
        or not _same_json_value(
            evidence.get("journal_commitment_sha256"),
            sha256_value([dict(row) for row in records]),
        )
    ):
        return False
    path = Path(evidence["path"])
    if not path.is_file() or path.stat().st_size != evidence["bytes"] or hashlib.sha256(path.read_bytes()).hexdigest() != evidence["sha256"]:
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    deep = contract["deep_hanna_bracket_validation"]
    expected_items = deep.get("frozen_item_ids")
    expected_keys = {"format_version", "kind", "stack", "size", "item_ids", "repetitions", "cells", "journal_commitment_sha256"}
    repetitions = deep.get("repetitions_per_item_and_size")
    size = item.get("size")
    if (
        not isinstance(payload, Mapping)
        or set(payload) != expected_keys
        or not _is_literal_int(payload.get("format_version"))
        or not _same_json_value(payload.get("format_version"), 1)
        or not _same_json_value(payload.get("kind"), "hanna_batch_curve_deep_validation")
        or not _is_exact_stack(stack)
        or not _is_exact_stack(payload.get("stack"))
        or not _same_json_value(payload.get("stack"), dict(stack))
        or not _is_batch_size(size)
        or not _is_batch_size(payload.get("size"))
        or not _same_json_value(payload.get("size"), size)
        or not _is_string_list(expected_items)
        or len(set(expected_items)) != len(expected_items)
        or not _is_string_list(payload.get("item_ids"))
        or not _same_json_value(payload.get("item_ids"), expected_items)
        or not _is_literal_int(repetitions)
        or repetitions < 1
        or not _is_literal_int(payload.get("repetitions"))
        or not _same_json_value(payload.get("repetitions"), repetitions)
        or not _same_json_value(payload.get("journal_commitment_sha256"), evidence["journal_commitment_sha256"])
    ):
        return False
    cells = payload.get("cells")
    if type(cells) is not list or len(cells) != len(expected_items) * repetitions:
        return False
    expected_pairs = {
        (item_id, repetition)
        for item_id in expected_items
        for repetition in range(1, repetitions + 1)
    }
    observed_pairs: set[tuple[str, int]] = set()
    journal_sessions = {row.get("provider", {}).get("session_id") for row in records if row.get("event") in {"accepted_call", "rejected_call"}}
    deep_sessions: set[str] = set()
    for cell in cells:
        if (
            not isinstance(cell, Mapping)
            or set(cell) != {"item_id", "repetition", "provider_receipt", "result"}
            or not _is_nonempty_string(cell.get("item_id"))
            or not _is_literal_int(cell.get("repetition"))
        ):
            return False
        pair = (cell["item_id"], cell["repetition"])
        if pair not in expected_pairs or pair in observed_pairs:
            return False
        observed_pairs.add(pair)
        receipt = cell.get("provider_receipt")
        result = cell.get("result")
        try:
            if not isinstance(receipt, Mapping) or receipt.get("kind") == "offline_fixture":
                return False
            verify_provider_receipt(receipt, contract)
        except ValueError:
            return False
        session_id = receipt["session_id"]
        if session_id in journal_sessions or session_id in deep_sessions:
            return False
        deep_sessions.add(session_id)
        if not _same_json_value(
            result,
            {"screening_cell_success": True, "canonical_reproduction": True},
        ):
            return False
    return observed_pairs == expected_pairs


def largest_validated_cap(validations: Sequence[Mapping[str, Any]], stack: Mapping[str, Any], contract: Mapping[str, Any], journal_records: Sequence[Mapping[str, Any]] | None = None) -> int | None:
    if tuple(stack) != STACK_FIELDS or not _is_exact_stack(stack):
        raise ValueError("Full exact stack identity is required")
    modules, bundle = _study_inputs(contract)
    validate_contract(contract, compile_bundle(modules, bundle))
    if dict(stack) != exact_stack(contract):
        raise ValueError("Recommendation stack must exactly match the frozen contract stack")
    caps: list[int] = []
    for item in validations:
        if not _same_json_value(item.get("stack"), dict(stack)) or not _same_json_value(item.get("status"), "empirically_validated_successful"):
            continue
        requested, expected, size = item.get("requested_question_count"), item.get("full_question_ids"), item.get("size")
        records = item.get("journal_records", journal_records)
        if not _is_literal_int(requested) or not _same_json_value(requested, contract["runtime"]["question_count"]) or not _is_batch_size(size) or not _same_json_value(expected, contract["runtime"]["frozen_question_ids"]) or not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
            continue
        try:
            if not _deep_evidence_valid(item, records, contract, stack):
                continue
            completions = verify_journal(records, contract)
            sequence = item.get("sequence")
            if not _is_literal_int(sequence) or not any(
                _same_json_value(row["sequence"], sequence)
                and _same_json_value(row["size"], size)
                for row in completions
            ):
                continue
            calls = [row for row in records if row.get("event") in {"accepted_call", "rejected_call"}]
            if not calls or any(row.get("provider", {}).get("kind") == "offline_fixture" for row in calls):
                continue
            sizes = _accepted_call_sizes(records, sequence)
            if sizes == [len(chunk) for chunk in partition_question_ids(expected, size)]:
                caps.append(max(sizes, default=0))
        except (KeyError, TypeError, ValueError):
            continue
    return max(caps, default=None)


def _alpha_nominal(rows: Sequence[Sequence[str]]) -> float | None:
    pooled: Counter[str] = Counter(); observed_pairs = disagreeing_pairs = 0
    for row in rows:
        pooled.update(row)
        for left, right in combinations(row, 2):
            observed_pairs += 1; disagreeing_pairs += left != right
    if not observed_pairs:
        return None
    total = sum(pooled.values())
    expected = sum(count * (total - count) for count in pooled.values()) / (total * (total - 1)) if total > 1 else 0
    observed = disagreeing_pairs / observed_pairs
    return 1.0 if expected == 0 and observed == 0 else (None if expected == 0 else 1.0 - observed / expected)


def repeatability_metrics(repetitions: Sequence[Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Deterministic formulas for three full leaf-result repetitions."""
    if len(repetitions) != 3:
        raise ValueError("Screening metrics require exactly three repetitions")
    ids = [[row.get("question_id") for row in run] for run in repetitions]
    if not ids[0] or len(set(ids[0])) != len(ids[0]) or any(run != ids[0] for run in ids[1:]):
        raise ValueError("Repetitions must contain the same nonempty ordered leaves")
    scores: list[float] = []
    for run in repetitions:
        run_scores: set[float] = set()
        for row in run:
            if row.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or not _is_number(row.get("confidence")) or not 0.0 <= float(row["confidence"]) <= 1.0:
                raise ValueError("Repeatability rows require a valid verdict and bounded numeric confidence")
            if not _is_number(row.get("canonical_observed_score")) or type(row.get("strict_schema_conformant")) is not bool or type(row.get("exact_quote_grounded")) is not bool:
                raise ValueError("Repeatability rows require numeric scores and literal boolean provenance flags")
            run_scores.add(float(row["canonical_observed_score"]))
        if len(run_scores) != 1:
            raise ValueError("Every repetition must carry one consistent canonical work score")
        scores.append(run_scores.pop())
    labels = [[run[index].get("verdict") for run in repetitions] for index in range(len(ids[0]))]
    quotes = [bool(row.get("exact_quote_grounded")) for run in repetitions for row in run]
    conformance = [bool(row.get("strict_schema_conformant")) for run in repetitions for row in run]
    return {
        "exact_all_three_leaf_agreement": statistics.fmean(len(set(row)) == 1 for row in labels),
        "mean_modal_label_proportion": statistics.fmean(max(Counter(row).values()) / 3 for row in labels),
        "nominal_krippendorff_alpha": _alpha_nominal(labels),
        "observed_score_standard_deviation": statistics.stdev(scores),
        "strict_schema_conformance_rate": statistics.fmean(conformance),
        "exact_quote_grounding_rate": statistics.fmean(quotes), "canonical_observed_scores": scores,
    }


def screening_state(metrics: Mapping[str, Any], thresholds: Mapping[str, float]) -> str:
    expected = {
        "minimum_exact_all_three_leaf_agreement", "minimum_mean_modal_label_proportion",
        "minimum_nominal_krippendorff_alpha", "maximum_observed_score_standard_deviation",
        "minimum_strict_schema_conformance_rate", "minimum_exact_quote_grounding_rate",
    }
    if set(thresholds) != expected or any(not _is_number(value) for value in thresholds.values()):
        raise ValueError("Screening thresholds must be complete finite numeric values")
    if any(not 0.0 <= float(thresholds[key]) <= 1.0 for key in expected if key != "maximum_observed_score_standard_deviation") or float(thresholds["maximum_observed_score_standard_deviation"]) < 0:
        raise ValueError("Screening thresholds are outside their declared bounds")
    metric_keys = {
        "minimum_exact_all_three_leaf_agreement": "exact_all_three_leaf_agreement",
        "minimum_mean_modal_label_proportion": "mean_modal_label_proportion",
        "minimum_nominal_krippendorff_alpha": "nominal_krippendorff_alpha",
        "maximum_observed_score_standard_deviation": "observed_score_standard_deviation",
        "minimum_strict_schema_conformance_rate": "strict_schema_conformance_rate",
        "minimum_exact_quote_grounding_rate": "exact_quote_grounding_rate",
    }
    if any(not _is_number(metrics.get(name)) for name in metric_keys.values()):
        raise ValueError("Screening metrics must be finite numeric values")
    if any(not 0.0 <= float(metrics[name]) <= 1.0 for name in metric_keys.values() if name != "observed_score_standard_deviation") or float(metrics["observed_score_standard_deviation"]) < 0:
        raise ValueError("Screening metrics are outside their declared bounds")
    checks = {
        "minimum_exact_all_three_leaf_agreement": metrics["exact_all_three_leaf_agreement"] >= thresholds["minimum_exact_all_three_leaf_agreement"],
        "minimum_mean_modal_label_proportion": metrics["mean_modal_label_proportion"] >= thresholds["minimum_mean_modal_label_proportion"],
        "minimum_nominal_krippendorff_alpha": metrics["nominal_krippendorff_alpha"] is not None and metrics["nominal_krippendorff_alpha"] >= thresholds["minimum_nominal_krippendorff_alpha"],
        "maximum_observed_score_standard_deviation": metrics["observed_score_standard_deviation"] <= thresholds["maximum_observed_score_standard_deviation"],
        "minimum_strict_schema_conformance_rate": metrics["strict_schema_conformance_rate"] >= thresholds["minimum_strict_schema_conformance_rate"],
        "minimum_exact_quote_grounding_rate": metrics["exact_quote_grounding_rate"] >= thresholds["minimum_exact_quote_grounding_rate"],
    }
    return "screening_successful" if all(checks.values()) else "screening_failed"


def bracket_transitions(screened: Mapping[int | str, str]) -> list[dict[str, Any]]:
    """Make every finite-ladder state transition explicit; no unrun size is inferred."""
    if set(screened) != set(SIZES) or any(value not in {"screening_successful", "screening_failed"} for value in screened.values()):
        raise ValueError("Every frozen size must have a completed screening state")
    return [
        {"from": SIZES[index], "to": SIZES[index + 1],
         "transition": f"{screened[SIZES[index]]}_to_{screened[SIZES[index + 1]]}",
         "requires_deep_bracket": screened[SIZES[index]] != screened[SIZES[index + 1]]}
        for index in range(len(SIZES) - 1)
    ]


def position_rows(question_ids_: Sequence[str], *, block: int, within_block: int, size: int | str) -> list[dict[str, Any]]:
    chunks = partition_question_ids(question_ids_, size)
    return [
        {"question_id": question_id, "block": block, "within_block": within_block,
         "run_sequence_number": (block - 1) * len(SIZES) + within_block,
         "batch_ordinal_within_run": batch, "within_batch_question_position": position,
         "actual_batch_question_count": len(chunk), "question_cohort_sha256": hashlib.sha256("\n".join(chunk).encode()).hexdigest()}
        for batch, chunk in enumerate(chunks, 1) for position, question_id in enumerate(chunk, 1)
    ]


def _weighted_quantile(values: Sequence[tuple[float, float]], quantile: float) -> float | None:
    if not values:
        return None
    total = sum(weight for _, weight in values)
    if total <= 0:
        return None
    threshold = total * quantile
    running = 0.0
    for value, weight in sorted(values):
        running += weight
        if running >= threshold:
            return value
    return values[-1][0]


def confidence_diagnostics(rows: Sequence[Mapping[str, Any]], *, expected_question_ids: Sequence[str] | None = None) -> dict[str, Any]:
    if not rows:
        raise ValueError("Confidence diagnostics require rows")
    expected = set(expected_question_ids) if expected_question_ids is not None else None
    if expected is not None and (not expected or len(expected) != len(expected_question_ids or ())):
        raise ValueError("Confidence diagnostics expected question IDs must be unique and nonempty")
    grouped_all: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if type(row.get("assessed")) is not bool or row.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or not _is_number(row.get("weight")) or float(row["weight"]) < 0 or not _is_number(row.get("confidence")) or not 0.0 <= float(row["confidence"]) <= 1.0 or not _is_number(row.get("canonical_leaf_score")):
            raise ValueError("Confidence diagnostics require literal booleans, bounded numeric confidence, and finite numeric weights/scores")
        if row["assessed"] is not (row["verdict"] in {"YES", "NO"}):
            raise ValueError("Confidence diagnostics require assessed state to match the verdict state")
        question_id = row.get("question_id")
        if not isinstance(question_id, str) or not question_id or (expected is not None and question_id not in expected):
            raise ValueError("Confidence diagnostics require valid question IDs")
        expected_score = 1.0 if row["verdict"] == "YES" else 0.0
        if not 0.0 <= float(row["canonical_leaf_score"]) <= 1.0 or float(row["canonical_leaf_score"]) != expected_score:
            raise ValueError("Confidence diagnostics require canonical leaf scores derived from verdict state")
        grouped_all.setdefault(question_id, []).append(row)
    if (expected is not None and set(grouped_all) != expected) or any(len(values) != 3 for values in grouped_all.values()):
        raise ValueError("Confidence diagnostics require exactly three rows for every valid leaf")
    assessed = [row for row in rows if row["assessed"]]
    denominator = sum(float(row["weight"]) for row in rows)
    assessed_mass = sum(float(row["weight"]) for row in assessed)
    confidence_mass = sum(float(row["weight"]) * float(row["confidence"]) for row in assessed)
    score_mass = sum(float(row["weight"]) * float(row["confidence"]) * float(row["canonical_leaf_score"]) for row in assessed)
    weighted_values = [(float(row["confidence"]), float(row["weight"])) for row in assessed]
    mean = confidence_mass / assessed_mass if assessed_mass else None
    variance = (sum(weight * (value - mean) ** 2 for value, weight in weighted_values) / assessed_mass) if mean is not None and assessed_mass else None
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in assessed:
        question_id = row.get("question_id")
        grouped.setdefault(question_id, []).append(row)
    pair_weight = pair_agreement = high_disagreement = stable_mass = flipping_mass = 0.0
    for values in grouped.values():
        weight = statistics.fmean(float(row["weight"]) for row in values)
        labels = [str(row["verdict"]) for row in values]
        stable = len(set(labels)) == 1
        if stable:
            stable_mass += weight
        else:
            flipping_mass += weight
        for left, right in combinations(values, 2):
            pair = weight * statistics.fmean((float(left["confidence"]), float(right["confidence"])))
            pair_weight += pair
            pair_agreement += pair * (left["verdict"] == right["verdict"])
        if not stable and any(float(row["confidence"]) >= 0.8 for row in values):
            high_disagreement += weight
    strata = {}
    for label in ("YES", "NO", "CANNOT_ASSESS"):
        values = [(float(row["confidence"]), float(row["weight"])) for row in assessed if row["verdict"] == label]
        mass = sum(weight for _, weight in values)
        strata[label] = {"assessed_weight": mass, "weighted_mean": (sum(value * weight for value, weight in values) / mass) if mass else None}
    return {
        "mean_assessed_confidence": mean,
        "confidence_adjusted_assessed_mass": confidence_mass / denominator if denominator else None,
        "confidence_weighted_score_sensitivity": score_mass / confidence_mass if confidence_mass else None,
        "confidence_weighted_repeat_agreement": pair_agreement / pair_weight if pair_weight else None,
        "confidence_distribution": {"weighted_mean": mean, "weighted_standard_deviation": math.sqrt(variance) if variance is not None else None, "weighted_quantiles": {"p25": _weighted_quantile(weighted_values, .25), "p50": _weighted_quantile(weighted_values, .5), "p75": _weighted_quantile(weighted_values, .75)}, "strata": strata},
        "stable_vs_flipping": {"stable_question_weight": stable_mass, "flipping_question_weight": flipping_mass},
        "high_confidence_disagreement_mass": high_disagreement,
    }


def offline_matrix(modules: Sequence[dict[str, Any]], bundles: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for bundle in bundles:
        compiled = compile_bundle(modules, bundle); projection = compiled_projection(compiled); ids = projection["question_ids"]
        verdicts = _fixture_verdicts(ids)
        report = score_bundle(modules, bundle, verdicts)
        confidence_rows = _fixture_confidence_rows(verdicts)
        shapes = {str(size): [len(chunk) for chunk in partition_question_ids(ids, size)] for size in SIZES}
        rows.append({"bundle_id": bundle["bundle_id"], "compiled_bundle_sha256": sha256_value(projection), "question_count": len(ids),
                     "question_id_sequence_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
                     "partition_shapes": shapes,
                     "partition_reconstructs_order": all([item for chunk in partition_question_ids(ids, size) for item in chunk] == ids for size in SIZES),
                     "canonical_score_recomputed": _canonical_evaluation(modules, bundle, verdicts),
                      "confidence_diagnostics": confidence_diagnostics(confidence_rows, expected_question_ids=ids),
                     "empirically_validated_successful_size": None})
    return rows


def manual_stack_fixture_checks(modules: Sequence[dict[str, Any]], bundles: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    fixture = json.loads((HERE / "manual-stack-fixtures.json").read_text(encoding="utf-8"))
    stacks = fixture.get("stacks") if isinstance(fixture, Mapping) else None
    if fixture.get("format_version") != 1 or not isinstance(stacks, list) or len(stacks) != 8:
        raise ValueError("Independent manual-stack fixture is malformed")
    by_id = {bundle["bundle_id"]: bundle for bundle in bundles}
    checked: list[dict[str, Any]] = []
    families: set[str] = set()
    bundle_ids: set[str] = set()
    for item in stacks:
        if not isinstance(item, Mapping) or set(item) != {"format_family", "bundle_id", "question_count", "compiled_bundle_sha256", "question_id_sequence_sha256"} or not isinstance(item["format_family"], str) or not item["format_family"] or not isinstance(item["bundle_id"], str) or not isinstance(item["question_count"], int) or not _is_sha256(item.get("compiled_bundle_sha256")) or not _is_sha256(item.get("question_id_sequence_sha256")) or item["format_family"] in families or item["bundle_id"] in bundle_ids:
            raise ValueError("Independent manual-stack fixture has invalid fields")
        families.add(item["format_family"])
        bundle_ids.add(item["bundle_id"])
        bundle = by_id.get(item["bundle_id"])
        if bundle is None:
            raise ValueError("Independent manual-stack fixture refers to an unavailable bundle")
        compiled = compile_bundle(modules, bundle)
        ids = question_ids(compiled)
        projection = compiled_projection(compiled)
        if len(ids) != item["question_count"] or len(set(ids)) != len(ids) or sha256_value(projection) != item["compiled_bundle_sha256"] or hashlib.sha256("\n".join(ids).encode()).hexdigest() != item["question_id_sequence_sha256"]:
            raise ValueError("Independent manual-stack fixture does not match direct core compilation")
        checked.append({
            **dict(item),
            "all_frozen_partition_shapes_reconstruct_order": all([question_id for chunk in partition_question_ids(ids, size) for question_id in chunk] == ids for size in SIZES),
        })
    return checked


def generated_matrix_document(modules: Sequence[dict[str, Any]], bundles: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = offline_matrix(modules, bundles)
    manual = manual_stack_fixture_checks(modules, bundles)
    return {"format_version": 4, "status": "offline_mechanism_support_only",
            "generator": {"module": "batch_curve_harness.generated_matrix_document", "offline_fixture": "offline-fixture-v1", "catalog_bundle_count": len(rows)},
            "claim_boundary": "Derived only from local deterministic compilation and fixture scoring; no provider call, empirical batch-size validation, or recommendation is present.",
            "mechanism_checks": ["compile", "freeze_full_question_order", "partition_frozen_questions", "recompute_canonical_metrics", "extract_secondary_diagnostics"],
            "bundle_rows": rows,
             "representative_manual_stacks": manual}


def run_offline_fixture(contract: Mapping[str, Any], compiled: Mapping[str, Any], endpoint: Callable[[list[str], Mapping[str, Any]], Sequence[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    """Run every scheduled cell through a supplied fake endpoint; never open a network client."""
    validate_contract(contract, compiled); ids = question_ids(compiled); records = planned_events(contract)
    for plan in planned_events(contract):
        accepted = retries = 0
        for ordinal, chunk in enumerate(partition_question_ids(ids, plan["size"]), 1):
            for attempt in range(1, contract["runtime"]["batch_attempts"] + 1):
                context = {"plan": plan, "batch_ordinal": ordinal, "attempt": attempt, "mode": "offline_fixture"}
                call = {**plan, "call_id": f"fixture-{plan['sequence']:02d}-{ordinal:03d}-{attempt}", "batch_ordinal": ordinal, "attempt": attempt, "question_ids": chunk, "provider": {"kind": "offline_fixture", "session_id": f"fixture-session-{plan['sequence']:02d}-{ordinal:03d}-{attempt}"}}
                response = list(endpoint(chunk, context))
                try:
                    verdicts = _strict_fixture_verdicts(response, chunk, artifact_text=_verify_bound_artifact(contract["source"], label="source").read_text(encoding="utf-8"))
                except ValueError as error:
                    records.append({**call, "event": "rejected_call", "rejection_reason": str(error), "redacted_response_commitment_sha256": sha256_value(response)})
                    retries += 1
                    if attempt == contract["runtime"]["batch_attempts"]:
                        raise ValueError("Fixture exhausted frozen retries") from error
                    continue
                records.append({**call, "event": "accepted_call", "verdicts": verdicts, "verdicts_sha256": sha256_value(verdicts)})
                accepted += 1
                break
        modules, bundle = _study_inputs(contract)
        all_verdicts = [verdict for call in records if call.get("event") == "accepted_call" and call.get("sequence") == plan["sequence"] for verdict in call["verdicts"]]
        records.append({**plan, "event": "completed", "requested_question_count": len(ids), "accepted_call_question_count": len(all_verdicts), "accepted_checkpoint_count": accepted, "retry_count": retries, "evaluation": _canonical_evaluation(modules, bundle, all_verdicts)})
    verify_journal(records, contract)
    return records


def execute_offline_contract(contract_path: Path, journal_path: Path) -> list[dict[str, Any]]:
    """The command-line no-call study path; it writes only a local fixture journal."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    modules = load_modules(registry_path())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == contract["runtime"]["bundle_id"])
    compiled = compile_bundle(modules, bundle)
    journal = run_offline_fixture(contract, compiled, lambda ids, _context: _fixture_verdicts(ids))
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    journal_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in journal), encoding="utf-8")
    return journal


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Execute the batch-curve v2 no-call fixture only.")
    parser.add_argument("--offline-fixture", action="store_true", help="Required: this module has no live-provider mode.")
    parser.add_argument("--journal", type=Path, required=True, help="Local JSONL destination for the generated fixture journal.")
    parser.add_argument("--matrix", type=Path, help="Optional generated offline-mechanism matrix destination.")
    args = parser.parse_args()
    if not args.offline_fixture:
        parser.error("Only --offline-fixture is implemented; no provider call is available.")
    execute_offline_contract(Path(__file__).with_name("study-contract.json"), args.journal)
    if args.matrix is not None:
        modules = load_modules(registry_path())
        args.matrix.write_text(json.dumps(generated_matrix_document(modules, load_bundles(bundles_path())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
