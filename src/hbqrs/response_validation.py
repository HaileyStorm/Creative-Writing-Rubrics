"""Validate a supplied complete response bank without executing a judge.

This opt-in API validates supplied text/records against the supplied bundle and
task. It does not authenticate their source, establish what a judge received,
verify native execution, decide applicability or evaluate literary quality.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from hbqrs import core, runner, scoring_v2
from hbqrs.strict_input import _check_tree
from hbqrs.selector_integrity import EXACT, admit_bundle_selectors, resolve_selector_policy

__all__ = ["ResponseBankValidationError", "validate_response_bank"]


class ResponseBankValidationError(core.HBQError):
    """Typed rejection with no supplied response or source text in its message."""

    def __init__(self, failure_type: str, *, batch_number: int | None = None):
        self.failure_type = failure_type
        self.batch_number = batch_number
        message = "Response bank rejected: " + failure_type
        if batch_number is not None:
            message += " (batch " + str(batch_number) + ")"
        super().__init__(message)


def _reject(failure_type: str, *, batch_number: int | None = None) -> None:
    raise ResponseBankValidationError(failure_type, batch_number=batch_number) from None


def _snapshot(value: Any) -> Any:
    try:
        _check_tree(value, set(), set())
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        _reject("INPUT_DATA")


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def validate_response_bank(
    modules: Sequence[dict[str, Any]],
    bundle: dict[str, Any],
    batches: Sequence[Mapping[str, Any]],
    *,
    artifact_id: str,
    artifact_text: str,
    context_texts: Sequence[str] = (),
    task_contract: Mapping[str, Any] | None = None,
    selector_policy: str | None = None,
) -> dict[str, Any]:
    """Validate raw JSON batches covering every compiled question exactly once.

    Each batch has exactly ``question_ids`` (a nonempty list of strings) and
    ``response_text`` (raw JSON text, preserving duplicate-key detection).
    Flattened request IDs must equal the complete role-ordered compiled bank;
    response verdict order may differ and is normalized to request order.

    New calls default to exact_selector_ids_v1 admission and a versioned v2
    receipt whose supplied-input digest binds that selector policy. Explicit
    historical_permissive_v1 preserves the original v1 receipt and digest.
    Selector admission is checked before response JSON parsing.

    The API always uses finite/unique-key JSON parsing, strict_import_v3,
    typed evidence and exact contiguous quote matching against artifact/context.
    Supplied modules and bundle must satisfy their existing canonical schemas,
    including recursive group/child shapes, before compilation.
    It never repairs quotes, scores a bank or calls a provider. Canonical CA
    semantics are retained: CA is a supported value, not a quality decision;
    the current wire contract does not require its note to be nonblank. NA
    requires its existing strict-import activation reason. Summaries and source
    references are declarations, not proof of truth or referenced locations.

    Snapshots/digests bind supplied values only. They are not frozen execution,
    prompt/schema transport, native/provider provenance or source authentication.
    ``membership_complete`` concerns IDs; CA/NA remain in ``verdict_counts``.
    No file paths, native IDs, jobs, outcomes or dataset population are inferred.
    """
    if (type(modules) not in (list, tuple) or any(type(item) is not dict for item in modules)
            or type(bundle) is not dict
            or type(batches) not in (list, tuple) or type(context_texts) not in (list, tuple)
            or type(artifact_id) is not str or not artifact_id.strip()
            or type(artifact_text) is not str or any(type(text) is not str for text in context_texts)
            or task_contract is not None and type(task_contract) is not dict):
        _reject("INPUT_DATA")
    try:
        resolved_selector_policy, _ = resolve_selector_policy(selector_policy)
    except core.HBQError:
        _reject("SELECTOR_POLICY")
    source = _snapshot({"modules": list(modules), "bundle": bundle, "batches": list(batches),
                        "artifact_id": artifact_id, "artifact_text": artifact_text,
                        "context_texts": list(context_texts), "task_contract": task_contract})
    if resolved_selector_policy == EXACT:
        source["selector_policy"] = resolved_selector_policy
    try:
        input_digest = _digest(_canonical(source))
        source_bindings = {"artifact_sha256": _digest(source["artifact_text"].encode("utf-8")),
                           "context_sha256s": [_digest(text.encode("utf-8")) for text in source["context_texts"]]}
    except (UnicodeError, ValueError, TypeError, RecursionError):
        _reject("INPUT_DATA")
    modules, bundle, batches, task = (source[key] for key in ("modules", "bundle", "batches", "task_contract"))
    artifact_id = source["artifact_id"]
    # Use the existing recursive schemas at the input boundary rather than
    # catching AttributeError from arbitrary malformed nested structures.
    module_schema = core.load_data(runner.schema_dir() / "hbq_rubric.schema.json")
    bundle_schema = core.load_data(runner.schema_dir() / "hbq_bundle.schema.json")
    module_validator = Draft202012Validator(module_schema)
    if (not all(module_validator.is_valid(record) for record in modules)
            or not Draft202012Validator(bundle_schema).is_valid(bundle)):
        _reject("BANK_DEFINITION_OR_TASK")
    try:
        admit_bundle_selectors(modules, bundle, resolved_selector_policy)
        # Validate any selected versioned task schema before its compilation.
        scoring_v2.validate_import_admission(modules, bundle, [], artifact_id=artifact_id,
            task_contract=task, admission_policy="strict_import_v3")
        compiled = core.compile_bundle(modules, bundle, task_contract=task)
        role_order = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
        questions = sorted(core.compiled_questions(compiled), key=lambda row: role_order.get(str(row.get("role")), 99))
        expected = [row["question"]["id"] for row in questions]
    except OverflowError:
        # Finite arbitrary-size JSON integers may exceed the canonical
        # compiler's float-based weight representation. Classify this numeric
        # definition failure here; do not hide unrelated AttributeError bugs.
        _reject("BANK_DEFINITION_OR_TASK")
    except (core.HBQError, KeyError, TypeError, ValueError):
        _reject("BANK_DEFINITION_OR_TASK")
    if not expected or any(type(qid) is not str or not qid for qid in expected) or len(set(expected)) != len(expected):
        _reject("BANK_DEFINITION_OR_TASK")
    flattened = []
    for number, batch in enumerate(batches, 1):
        if (type(batch) is not dict or set(batch) != {"question_ids", "response_text"}
                or type(batch["question_ids"]) is not list or not batch["question_ids"]
                or any(type(qid) is not str or not qid for qid in batch["question_ids"])
                or type(batch["response_text"]) is not str):
            _reject("BATCH_INPUT", batch_number=number)
        flattened.extend(batch["question_ids"])
    if len(flattened) != len(set(flattened)):
        _reject("DUPLICATE_REQUEST_ID")
    if set(flattened) != set(expected):
        _reject("BANK_MEMBERSHIP")
    if flattened != expected:
        _reject("REQUEST_ORDER")
    normalized, receipts = [], []
    for number, batch in enumerate(batches, 1):
        ids = batch["question_ids"]
        try:
            raw = batch["response_text"].encode("utf-8")
        except UnicodeError:
            _reject("RESPONSE_JSON", batch_number=number)
        if not raw or len(raw) > runner.MAX_RESPONSE_BYTES:
            _reject("RESPONSE_SIZE", batch_number=number)
        try:
            payload = runner._parse_model_json(batch["response_text"], policy=runner.RESPONSE_JSON_FINITE_POLICY)
        except (ValueError, TypeError, RecursionError):
            _reject("RESPONSE_JSON", batch_number=number)
        schema = runner._batch_response_schema(ids)
        if not Draft202012Validator(schema).is_valid(payload):
            _reject("RESPONSE_SCHEMA", batch_number=number)
        try:
            values = runner._normalize_batch(payload, expected_ids=ids, artifact_id=artifact_id,
                bundle_id=bundle["bundle_id"], judge_id="offline_semantic_validation_only",
                run_id="offline_semantic_validation_only", artifact_text=source["artifact_text"],
                context_texts=source["context_texts"], normalization_policy=None)
        except (core.HBQError, ValueError, TypeError, KeyError):
            _reject("RESPONSE_SEMANTICS", batch_number=number)
        normalized.extend(values)
        receipts.append({"batch_number": number, "question_ids": list(ids), "response_sha256": _digest(raw),
                         "derived_schema_sha256": _digest(runner._json_bytes(schema))})
    if [row["question_id"] for row in normalized] != expected:
        _reject("BANK_MEMBERSHIP")
    try:
        admission = scoring_v2.validate_import_admission(modules, bundle, normalized, artifact_id=artifact_id,
            task_contract=task, admission_policy="strict_import_v3")
    except (core.HBQError, ValueError, TypeError, KeyError):
        _reject("IMPORT_ADMISSION")
    if admission["omitted_questions"] != 0 or admission["supplied_questions"] != len(expected):
        _reject("BANK_MEMBERSHIP")
    counts = Counter({verdict: 0 for verdict in ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")})
    counts.update(row["verdict"] for row in normalized)
    clean = [{key: value for key, value in row.items() if key not in {"judge_id", "run_id"}} for row in normalized]
    result = {"policy": "supplied_complete_response_bank_v1", "status": "SEMANTICS_VALIDATED_ONLY",
        "membership_complete": True, "question_count": len(expected), "batch_count": len(batches),
        "artifact_id": artifact_id, "bundle_id": bundle["bundle_id"], "verdict_counts": dict(counts),
        "all_binary_assessed": counts["NOT_APPLICABLE"] == counts["CANNOT_ASSESS"] == 0,
        "normalized_verdicts": clean, "import_admission": admission,
        "supplied_inputs_sha256": input_digest, "supplied_source_bindings": source_bindings, "batches": receipts,
        "native_provenance": None, "quality_verified": False, "score": None, "repairs": []}
    if resolved_selector_policy == EXACT:
        result["policy"] = "supplied_complete_response_bank_v2"
        result["selector_policy"] = resolved_selector_policy
    return result
