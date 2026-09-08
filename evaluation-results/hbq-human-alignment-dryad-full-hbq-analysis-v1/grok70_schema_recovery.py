"""Read the adopted ordinal-70 quote derivative without native admission or writes."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

TERMINAL_OUTCOME_SHA256 = "94ca9ce1dd9de1064441f075d44412b7e7b487dbf207fac81cdb5c1a69f44b7f"
PROPOSAL_FILES = {"PROPOSAL.md", "commitments.json", "original-agent-message.json",
                  "derivative-agent-message.json", "response-schema.json"}
DELTA_PATH = ["verdicts", 3, "evidence", 0, "exact_quote"]
DELTA_LABEL = "verdicts[3].evidence[0].exact_quote"
EXTRACTION_RULE = "exactly_one_agent_message_chunk_utf8_text"
ADOPTED_SCOPE = {
    "logical_request_ordinal": 70, "native_cli_envelope_request_id_binding": "missing",
    "ordinary_native_admission": False, "original_preserved": True, "provider_contact_authority": False,
    "resend_authority": False, "transformation": DELTA_LABEL + " first 500 unicode codepoints only",
    "wpb_0843_adoption": False,
}
_MAX_BYTES = 256_000


def _require(value: bool, label: str) -> None:
    if not value:
        raise ValueError(label)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= set("0123456789abcdef")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, "Recovery JSON contains duplicate keys")
        result[key] = value
    return result


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError(label + " is not strict JSON") from error
    _require(isinstance(value, dict), label + " must be an object")
    return value


def _read_bound(path: Path, digest: str, label: str, size: int | None = None) -> bytes:
    _require(_hex(digest), label + " hash anchor differs")
    _require(size is None or type(size) is int and 0 <= size <= _MAX_BYTES, label + " size anchor differs")
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(_MAX_BYTES + 1)
    except OSError as error:
        raise ValueError(label + " is unavailable") from error
    _require(len(raw) <= _MAX_BYTES and _sha(raw) == digest and (size is None or len(raw) == size),
             label + " bytes differ")
    return raw


def _same_path(actual: Path, expected: Any, label: str) -> None:
    _require(isinstance(expected, str) and bool(expected) and Path(actual).resolve() == Path(expected).resolve(),
             label + " path differs from adopted evidence")


def _adoption(path: Path, expected_sha256: str, proposal_root: Path, review_path: Path) -> dict[str, Any]:
    value = _json(_read_bound(path, expected_sha256, "Owner adoption"), "Owner adoption")
    _require(set(value) == {"decision", "implementation_admission_status", "independent_review", "owner_decision",
                           "proposal_files_sha256", "proposal_root", "schema_version", "scope"}
             and type(value["schema_version"]) is int and value["schema_version"] == 1
             and value["decision"] == "adopt_exact_grok70_quote_repair"
             and value["implementation_admission_status"] == "pending_reviewed_integration"
             and _canonical(value["scope"]) == _canonical(ADOPTED_SCOPE), "Owner adoption scope differs")
    owner = value["owner_decision"]
    _require(isinstance(owner, dict) and set(owner) == {"explicit", "recorded_at", "reference"}
             and owner["explicit"] is True and isinstance(owner["reference"], str) and bool(owner["reference"].strip())
             and isinstance(owner["recorded_at"], str) and owner["recorded_at"].endswith(("Z", "+00:00")),
             "Explicit owner decision is missing")
    try:
        datetime.fromisoformat(owner["recorded_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Owner decision time differs") from error
    files, review = value["proposal_files_sha256"], value["independent_review"]
    _require(isinstance(files, dict) and set(files) == PROPOSAL_FILES and all(_hex(item) for item in files.values()),
             "Adopted proposal bindings differ")
    _require(isinstance(review, dict) and set(review) == {"path", "sha256"} and _hex(review["sha256"]),
             "Adopted review binding differs")
    _same_path(proposal_root, value["proposal_root"], "Proposal")
    _same_path(review_path, review["path"], "Review")
    return value


def _quote(value: dict[str, Any]) -> str:
    try:
        quote = value["verdicts"][3]["evidence"][0]["exact_quote"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("Required quote path differs") from error
    _require(isinstance(quote, str), "Required exact quote must be text")
    return quote


def _no_schema_references(value: Any) -> bool:
    if isinstance(value, dict):
        return not ({"$ref", "$dynamicRef", "$recursiveRef"} & set(value)) and all(
            _no_schema_references(item) for item in value.values())
    return not isinstance(value, list) or all(_no_schema_references(item) for item in value)


def _semantic_proof(original: dict[str, Any], derivative: dict[str, Any], schema: dict[str, Any], source: str) -> dict[str, Any]:
    before, after = _quote(original), _quote(derivative)
    _require(len(before) == 543 and len(after) == 500 and after == before[:500], "Quote truncation differs")
    expected = copy.deepcopy(original)
    expected["verdicts"][3]["evidence"][0]["exact_quote"] = after
    _require(_canonical(expected) == _canonical(derivative), "Recovery changes more than the sole quote field")
    _require(before in source and after in source, "Recovery quotes are not exact source substrings")
    _require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
             and _no_schema_references(schema), "Recovery schema is not the self-contained adopted draft")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    original_errors = list(validator.iter_errors(original))
    derivative_errors = list(validator.iter_errors(derivative))
    _require(len(original_errors) == 1 and list(original_errors[0].absolute_path) == DELTA_PATH
             and original_errors[0].validator == "maxLength" and original_errors[0].validator_value == 500
             and original_errors[0].instance == before and not derivative_errors, "Recovery schema proof differs")
    return {"derivative_codepoints": 500, "derivative_schema_error_count": 0, "derivative_source_substring": True,
            "exact_semantic_delta_path": DELTA_LABEL, "first_500_codepoints_exact": True, "original_codepoints": 543,
            "original_schema_error_count": 1, "original_schema_error_path": DELTA_LABEL,
            "original_source_substring": True, "semantic_diff_count": 1}


def _extract_original(raw: bytes) -> tuple[bytes, str]:
    lines = raw.splitlines()
    _require(bool(lines) and all(line.strip() for line in lines), "Session container has blank or missing records")
    messages: list[bytes] = []
    sessions: set[str] = set()
    for line in lines:
        record = _json(line, "Session update")
        params = record.get("params")
        _require(isinstance(params, dict) and isinstance(params.get("sessionId"), str) and bool(params["sessionId"]),
                 "Session update identity is missing")
        sessions.add(params["sessionId"])
        update = params.get("update")
        _require(isinstance(update, dict), "Session update shape differs")
        if update.get("sessionUpdate") == "agent_message_chunk":
            content = update.get("content")
            _require(record.get("method") == "session/update" and isinstance(content, dict)
                     and set(content) == {"type", "text"} and content["type"] == "text"
                     and isinstance(content["text"], str), "Agent-message extraction shape differs")
            messages.append(content["text"].encode("utf-8"))
    _require(len(messages) == 1 and len(sessions) == 1, "Session extraction must contain exactly one agent message and identity")
    return messages[0], _sha(next(iter(sessions)).encode("utf-8"))


def _verify_commitments(value: dict[str, Any], original: bytes, derivative: bytes, schema: bytes,
                        source: dict[str, Any], extraction: dict[str, Any]) -> None:
    expected = {
        "authority": {"admission_authority": False, "native_mutation_authority": False, "owner_adoption_required": True,
                      "provider_contact_authority": False, "resend_authority": False},
        "ceiling": {"native_cli_envelope_request_id_binding": "missing", "promotable_as_accepted_result": False,
                    "reason": "native CLI envelope was not retained after structured-output validation error"},
        "derivative_agent_message": {"bytes": len(derivative), "semantic_delta_path": DELTA_LABEL,
                                     "sha256": _sha(derivative), "transformation": "first_500_unicode_codepoints_only"},
        "kind": "grok70_schema_recovery_proposal_commitments",
        "original_agent_message": {"bytes": len(original), "extraction": EXTRACTION_RULE, "sha256": _sha(original),
                                   "source_updates_container_sha256": extraction["container_sha256"]},
        "response_schema": {"bytes": len(schema), "sha256": _sha(schema)},
        "schema_validation": {"derivative_error_count": 0, "draft": "2020-12", "maximum_codepoints": 500,
                              "original_error_count": 1, "original_error_path": DELTA_LABEL, "original_length_codepoints": 543},
        "schema_version": 1,
        "source_substring_proof": {"derivative_quote_is_substring": True, "original_quote_is_substring": True,
                                   "source_relative_path": source["relative_path"], "source_sha256": source["sha256"]},
        "status": "proposal_only",
    }
    _require(_canonical(value) == _canonical(expected), "Adopted proposal commitments differ")


def _recover_judgment(proposal_root: Path, *, adoption_path: Path, expected_adoption_sha256: str,
                       review_path: Path, source_path: Path, updates_path: Path, terminal_outcome_path: Path,
                       terminal_outcome_sha256: str) -> dict[str, Any]:
    adoption = _adoption(adoption_path, expected_adoption_sha256, proposal_root, review_path)
    files = {name: _read_bound(Path(proposal_root) / name, digest, "Proposal " + name)
             for name, digest in adoption["proposal_files_sha256"].items()}
    review_sha = adoption["independent_review"]["sha256"]
    review = _json(_read_bound(review_path, review_sha, "Independent review"), "Independent review")
    _require(set(review) == {"authority", "checks", "evidence_ceiling", "evidence_paths", "evidence_class", "extraction",
                            "proposal_files", "schema_version", "source_input"}
             and type(review["schema_version"]) is int and review["schema_version"] == 1
             and review["evidence_class"] == "independent_grok70_schema_recovery_candidate_review_v1"
             and review["proposal_files"] == adoption["proposal_files_sha256"]
             and review["evidence_ceiling"] == {"native_cli_envelope_request_id_binding": "missing",
                                                "promotable_as_accepted_result": False, "recovery_class": "candidate_only"},
             "Independent review scope differs")
    _require(review["authority"] == {key: False for key in ("admission_authority", "execution_authority",
             "native_mutation_authority", "owner_adoption", "provider_contact_authority", "resend_authority", "study_admission")},
             "Historical candidate review authority differs")
    paths, source_binding, extraction = review["evidence_paths"], review["source_input"], review["extraction"]
    _require(isinstance(paths, dict) and set(paths) == {"source_input", "source_updates_container"}
             and isinstance(source_binding, dict) and set(source_binding) == {"bytes", "relative_path", "sha256"}
             and isinstance(extraction, dict) and set(extraction) == {"agent_message_count", "container_bytes", "container_sha256",
                 "extracted_bytes", "original_agent_message_sha256", "rule"}
             and type(extraction["agent_message_count"]) is int and extraction["agent_message_count"] == 1
             and extraction["rule"] == EXTRACTION_RULE, "Independent extraction bindings differ")
    _same_path(source_path, paths["source_input"], "Source")
    _same_path(updates_path, paths["source_updates_container"], "Session container")
    source_raw = _read_bound(source_path, source_binding["sha256"], "Source input", source_binding["bytes"])
    updates_raw = _read_bound(updates_path, extraction["container_sha256"], "Session container", extraction["container_bytes"])
    extracted, session_sha = _extract_original(updates_raw)
    original_raw, derivative_raw, schema_raw = (files[name] for name in (
        "original-agent-message.json", "derivative-agent-message.json", "response-schema.json"))
    _require(extracted == original_raw and len(extracted) == extraction["extracted_bytes"]
             and _sha(extracted) == extraction["original_agent_message_sha256"], "Preserved session extraction differs")
    original, derivative, schema = (_json(raw, label) for raw, label in (
        (original_raw, "Original judgment"), (derivative_raw, "Derivative judgment"), (schema_raw, "Response schema")))
    checks = _semantic_proof(original, derivative, schema, source_raw.decode("utf-8"))
    _require(_canonical(checks) == _canonical(review["checks"]), "Independent semantic proof differs")
    commitments = _json(files["commitments.json"], "Proposal commitments")
    _verify_commitments(commitments, original_raw, derivative_raw, schema_raw, source_binding, extraction)
    outcome = _json(_read_bound(terminal_outcome_path, terminal_outcome_sha256, "Original terminal outcome"), "Original terminal outcome")
    failure = outcome.get("failure")
    _require(set(outcome) == {"failure", "result", "state"} and outcome["state"] == "ambiguous" and outcome["result"] is None
             and isinstance(failure, dict) and failure.get("category") == "validation_error"
             and failure.get("code") == "validation_structured_output_error"
             and failure.get("provider_error_type") == "GrokBuildValidationFailure", "Original terminal outcome differs")
    provenance = {
        "schema_version": 1, "recovery_class": "study_recovered_quote_repair", "logical_request_ordinal": 70,
        "owner_adopted": True, "native_admission": False, "native_cli_envelope_request_id_binding": "missing",
        "provider_contact_authority": False, "resend_authority": False, "native_mutation_authority": False, "provider_calls": 0,
        "identity_evidence": "preserved_session_artifact_only", "provider_attested": False,
        "adoption_sha256": expected_adoption_sha256, "review_sha256": review_sha,
        "owner_adopted_at": adoption["owner_decision"]["recorded_at"],
        "proposal_files_sha256": dict(adoption["proposal_files_sha256"]), "original_sha256": _sha(original_raw),
        "derivative_sha256": _sha(derivative_raw), "response_schema_sha256": _sha(schema_raw),
        "source_sha256": source_binding["sha256"], "source_relative_path": source_binding["relative_path"],
        "source_bytes": len(source_raw), "original_bytes": len(original_raw), "derivative_bytes": len(derivative_raw),
        "updates_sha256": _sha(updates_raw), "updates_bytes": len(updates_raw), "session_identifier_sha256": session_sha,
        "extraction_rule": EXTRACTION_RULE, "terminal_outcome_sha256": terminal_outcome_sha256,
        "interpreter_sha256": _sha(Path(__file__).read_bytes()), "checks": checks,
    }
    return {"judgment": derivative, "study_recovered_quote_repair": provenance}


def recover_judgment(proposal_root: Path, *, adoption_path: Path, expected_adoption_sha256: str,
                      review_path: Path, source_path: Path, updates_path: Path, terminal_outcome_path: Path) -> dict[str, Any]:
    """Verify the adopted study derivative under the fixed ordinal-70 terminal binding."""
    return _recover_judgment(proposal_root, adoption_path=adoption_path, expected_adoption_sha256=expected_adoption_sha256,
                              review_path=review_path, source_path=source_path, updates_path=updates_path,
                              terminal_outcome_path=terminal_outcome_path, terminal_outcome_sha256=TERMINAL_OUTCOME_SHA256)
