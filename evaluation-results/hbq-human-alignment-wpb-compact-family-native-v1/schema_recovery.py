"""Provider-free verification for the WPB 0843 schema-projection proposal.

The native adapter rejected this session before it retained a CLI envelope or
request-ID binding. This module can only describe a locally derived,
schema-valid projection of the retained message. It never creates a native
result, admission, dispatch, or provider authority.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from jsonschema import Draft202012Validator

CELL_ID = "wpb-pair-wpb-en-0843"
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
CORE_PATH = HERE.parent / "hbq-human-alignment-wpb-compact-family-v1" / "study.py"
CORE_COMMIT = "b43f68381f3767b590ef68b19ddb8206c8818cda"
CORE_SHA256 = "ef1f8d5e45da1700283ef351ab943ec39abedb103ad1ef979d731d4934d32caf"
ORIGINAL_MESSAGE_SHA256 = "cc3523ce0ea0ff5b3f447e80a60a5ac5367ec8c2175549035dcc88e8976e9380"
PROJECTED_MESSAGE_SHA256 = "9e1b1b529d0f7023efb1e9663ad5092cfc0b7c431b0bf123375818f5db7709cd"
ORIGINAL_MESSAGE_BYTES = 1390
PROJECTED_MESSAGE_BYTES = 1385
SCHEMA_SHA256 = "3e7ff15aa844dd6f6b3c8c091cae5335eb1b290ca5eeddabb0eab6c29afc6b0e"
OUTCOME_SHA256 = "ca63efa971bf358cd35e544dd7fafc4283d42d20e309cdded00e3572cee465a3"
ATTEMPT_SHA256 = "97a39a56d7b7267fbaa397d76951dbdd8ba391fb6cdbc012b1753fa5dc377064"
SESSION_ATTESTATION_SHA256 = "59aa037ef6363e897a9102932b639287eaec11a0b7cc27e31a100e3ebfef004a"
VERIFIED_CANDIDATE_SHA256 = "cee5a61d89bbbc38ab3f678b85c0dc72d88a4ebe0bdec55edf5ac5c239832577"
INCIDENT_KEY = "4322dbf3a7a11295b8357d8d2cc19c05f400991ef51e0d06e870341e4c54dc04"
INCIDENT_REVOKED_AT_UTC = "2026-09-07T16:41:54Z"
_HEX = set("0123456789abcdef")
_MAX_EVIDENCE_LENGTH = 180
_EXPECTED_CHANGES = (
    ("A.evidence.core", 182, 180),
    ("B.evidence.craft", 183, 180),
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} must be UTF-8 JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def _reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _read_exact_json(path: Path, label: str, expected_sha256: str, expected_bytes: int) -> tuple[dict[str, Any], bytes]:
    value, raw = _json(path, label)
    _require(len(raw) == expected_bytes, f"{label} byte length drifted")
    _require(sha256(raw) == expected_sha256, f"{label} hash drifted")
    return value, raw


def _schema_errors(schema: Mapping[str, Any], value: Mapping[str, Any]) -> list[str]:
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: tuple(str(item) for item in error.path))
    return [".".join(str(item) for item in error.path) for error in errors]


def _field(value: Mapping[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        _require(isinstance(current, Mapping) and part in current, f"missing {dotted}")
        current = current[part]
    return current


def _validate_source_cell(source_cell_root: Path, schema_raw: bytes) -> dict[str, Any]:
    outcome, outcome_raw = _json(source_cell_root / "outcome.json", "0843 outcome")
    attempt, attempt_raw = _json(source_cell_root / "attempt.json", "0843 attempt")
    _source_schema, source_schema_raw = _json(source_cell_root / "response-schema.json", "0843 response schema")
    _require(sha256(outcome_raw) == OUTCOME_SHA256, "0843 outcome hash drifted")
    _require(sha256(attempt_raw) == ATTEMPT_SHA256, "0843 attempt hash drifted")
    _require(source_schema_raw == schema_raw and sha256(source_schema_raw) == SCHEMA_SHA256, "0843 source schema differs from proposal schema")
    _require(
        outcome == {
            "failure": {
                "account_class": "subscription",
                "category": "validation_error",
                "code": "validation_structured_output_error",
                "detail": "Grok reported a structured-output validation failure",
                "incident_key": INCIDENT_KEY,
                "provider": "xai_grok_build",
                "provider_error_type": "GrokBuildValidationFailure",
                "revocation": "host_revoked_and_local_projected",
                "route_epoch_hash": "413e2c03957c934e06c06d32a6779349e127b25115fb00fbd65c4df1ea3582d7",
                "schema_version": 1,
                "status": None,
            },
            "result": None,
            "state": "ambiguous",
        },
        "0843 outcome is not the frozen ambiguous validation failure",
    )
    _require(
        attempt.get("cell_id") == CELL_ID
        and attempt.get("schema_sha256") == SCHEMA_SHA256
        and attempt.get("session_id_hash") == "fc8b280d0d33e520f656dad0c0a674bf0cb6a4ca05ce313a10ce3caaee9c3ac7",
        "0843 attempt binding drifted",
    )
    return {
        "outcome_sha256": sha256(outcome_raw),
        "attempt_sha256": sha256(attempt_raw),
        "session_id_hash": attempt["session_id_hash"],
        "session_attestation_sha256": SESSION_ATTESTATION_SHA256,
        "native_result_status": "unavailable_no_cli_envelope_or_request_id_binding",
    }


def _load_frozen_core() -> ModuleType:
    raw = CORE_PATH.read_bytes()
    _require(sha256(raw) == CORE_SHA256, "frozen WPB core source drifted")
    relative = CORE_PATH.relative_to(REPOSITORY).as_posix()
    source_at_commit = subprocess.run(
        ["git", "-C", str(REPOSITORY), "show", f"{CORE_COMMIT}:{relative}"],
        capture_output=True,
        check=False,
    )
    _require(source_at_commit.returncode == 0 and source_at_commit.stdout == raw, "frozen WPB core commit binding drifted")
    name = "_wpb0843_schema_recovery_core"
    _require(name not in sys.modules, "frozen WPB core module cache is not accepted")
    spec = importlib.util.spec_from_file_location(name, CORE_PATH)
    _require(spec is not None and spec.loader is not None, "frozen WPB core cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        exec(compile(raw, str(CORE_PATH), "exec"), module.__dict__)  # noqa: S102 - immutable hash-pinned local source
    finally:
        sys.modules.pop(name, None)
    _require(CORE_PATH.read_bytes() == raw, "frozen WPB core changed during load")
    return module


def _validate_frozen_core(projected: Mapping[str, Any]) -> dict[str, Any]:
    core = _load_frozen_core()
    profile = core.compact_profile()
    base_masses = profile.get("base_family_mass") if isinstance(profile, Mapping) else None
    _require(isinstance(base_masses, Mapping), "frozen WPB core has no family masses")
    core._outcome(projected, {"core": 1.0, "craft": 1.0, "form": 1.0}, base_masses)
    return {"commit": CORE_COMMIT, "sha256": CORE_SHA256, "response_valid": True}


def verify_candidate(*, proposal_root: Path, source_cell_root: Path) -> dict[str, Any]:
    """Verify the exact frozen projection and return a non-admissible local record.

    Both inputs are read-only evidence roots.  The return value records why the
    candidate is a diagnostic projection rather than a native provider result.
    """
    root = Path(proposal_root).resolve()
    source = Path(source_cell_root).resolve()
    original, original_raw = _read_exact_json(root / "original-agent-message.json", "original agent message", ORIGINAL_MESSAGE_SHA256, ORIGINAL_MESSAGE_BYTES)
    projected, projected_raw = _read_exact_json(root / "projected-agent-message.json", "projected agent message", PROJECTED_MESSAGE_SHA256, PROJECTED_MESSAGE_BYTES)
    schema, schema_raw = _read_exact_json(root / "response-schema.json", "proposal response schema", SCHEMA_SHA256, 1130)
    _require(sha256(original_raw) == ORIGINAL_MESSAGE_SHA256 and sha256(projected_raw) == PROJECTED_MESSAGE_SHA256, "proposal message commitment drifted")
    _require(_schema_errors(schema, original) == ["A.evidence.core", "B.evidence.craft"], "original message has unexpected schema violations")
    _require(_schema_errors(schema, projected) == [], "projected message does not satisfy the frozen schema")
    changes: list[dict[str, Any]] = []
    for path, original_length, projected_length in _EXPECTED_CHANGES:
        before, after = _field(original, path), _field(projected, path)
        _require(isinstance(before, str) and isinstance(after, str), f"{path} must remain text")
        _require(len(before) == original_length and len(after) == projected_length == _MAX_EVIDENCE_LENGTH, f"{path} length drifted")
        _require(after == before[:_MAX_EVIDENCE_LENGTH], f"{path} is not the exact schema-bound prefix")
        changes.append({"path": path, "original_characters": original_length, "projected_characters": projected_length, "operation": "prefix_truncate_to_schema_max_length"})
    changed_paths = {item["path"] for item in changes}
    _require(_only_expected_changes(original, projected, "") == changed_paths, "projection changes fields other than the two schema-bound evidence strings")
    source_record = _validate_source_cell(source, schema_raw)
    frozen_core = _validate_frozen_core(projected)
    return {
        "format_version": 1,
        "kind": "wpb0843_local_session_schema_projection_candidate",
        "cell_id": CELL_ID,
        "status": "verified_pending_explicit_owner_adoption",
        "provider_calls_made": 0,
        "message": {
            "original_sha256": sha256(original_raw),
            "original_byte_length": len(original_raw),
            "projected_sha256": sha256(projected_raw),
            "projected_byte_length": len(projected_raw),
            "schema_sha256": sha256(schema_raw),
            "frozen_core": frozen_core,
            "full_field_diff": changes,
            "no_other_changes": True,
        },
        "source": source_record,
        "limitations": {
            "evidence_class": "local_session_diagnostic_projection",
            "original_outcome_remains": "ambiguous_validation_structured_output_error",
            "native_cli_envelope": "not_persisted",
            "request_id_binding": "not_available",
            "native_admission_permitted": False,
            "provider_attempt_permitted": False,
            "result_promotion_permitted": False,
        },
    }


def _only_expected_changes(before: Any, after: Any, prefix: str) -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        _require(set(before) == set(after), "projection object keys drifted")
        changed: set[str] = set()
        for key in before:
            child = f"{prefix}.{key}" if prefix else key
            changed.update(_only_expected_changes(before[key], after[key], child))
        return changed
    if before == after:
        return set()
    return {prefix}


def _validate_verified(verified: Mapping[str, Any]) -> None:
    _require(
        verified.get("kind") == "wpb0843_local_session_schema_projection_candidate"
        and verified.get("cell_id") == CELL_ID
        and verified.get("status") == "verified_pending_explicit_owner_adoption"
        and verified.get("provider_calls_made") == 0,
        "verified candidate shape is malformed",
    )
    message = verified.get("message")
    source = verified.get("source")
    limitations = verified.get("limitations")
    _require(isinstance(message, Mapping) and isinstance(source, Mapping) and isinstance(limitations, Mapping), "verified candidate bindings are malformed")
    _require(message.get("original_sha256") == ORIGINAL_MESSAGE_SHA256 and message.get("projected_sha256") == PROJECTED_MESSAGE_SHA256 and message.get("schema_sha256") == SCHEMA_SHA256 and message.get("frozen_core") == {"commit": CORE_COMMIT, "sha256": CORE_SHA256, "response_valid": True}, "verified candidate message bindings drifted")
    _require(message.get("full_field_diff") == [{"path": path, "original_characters": before, "projected_characters": after, "operation": "prefix_truncate_to_schema_max_length"} for path, before, after in _EXPECTED_CHANGES] and message.get("no_other_changes") is True, "verified candidate field diff drifted")
    _require(source.get("outcome_sha256") == OUTCOME_SHA256 and source.get("attempt_sha256") == ATTEMPT_SHA256 and source.get("session_attestation_sha256") == SESSION_ATTESTATION_SHA256 and source.get("native_result_status") == "unavailable_no_cli_envelope_or_request_id_binding", "verified candidate source binding drifted")
    _require(limitations.get("native_admission_permitted") is False and limitations.get("provider_attempt_permitted") is False and limitations.get("result_promotion_permitted") is False, "verified candidate limitation drifted")
    _require(sha256(dict(verified)) == VERIFIED_CANDIDATE_SHA256, "verified candidate commitment drifted")


def prepare_adoption_candidate(*, verified: Mapping[str, Any]) -> dict[str, Any]:
    """Bind verified evidence into a proposal that still grants no authority."""
    _validate_verified(verified)
    return {
        "format_version": 1,
        "kind": "wpb0843_schema_projection_adoption_candidate",
        "cell_id": CELL_ID,
        "status": "awaiting_new_explicit_owner_adoption",
        "candidate_sha256": VERIFIED_CANDIDATE_SHA256,
        "bindings": {
            "original_message_sha256": ORIGINAL_MESSAGE_SHA256,
            "projected_message_sha256": PROJECTED_MESSAGE_SHA256,
            "response_schema_sha256": SCHEMA_SHA256,
            "outcome_sha256": OUTCOME_SHA256,
            "attempt_sha256": ATTEMPT_SHA256,
            "session_attestation_sha256": SESSION_ATTESTATION_SHA256,
            "incident_key": INCIDENT_KEY,
            "incident_revoked_at_utc": INCIDENT_REVOKED_AT_UTC,
        },
        "required_owner_decision": "owner_adopts_local_session_schema_projection_only",
        "required_scope": "no_new_0843_provider_attempt",
        "provider_calls_made": 0,
        "native_admission_permitted": False,
        "result_promotion_permitted": False,
    }


def _validate_adoption_candidate(candidate: Mapping[str, Any]) -> None:
    required = {
        "format_version", "kind", "cell_id", "status", "candidate_sha256", "bindings", "required_owner_decision", "required_scope",
        "provider_calls_made", "native_admission_permitted", "result_promotion_permitted",
    }
    _require(set(candidate) == required, "adoption candidate has unsupported or missing fields")
    _require(
        candidate.get("format_version") == 1
        and candidate.get("kind") == "wpb0843_schema_projection_adoption_candidate"
        and candidate.get("cell_id") == CELL_ID
        and candidate.get("status") == "awaiting_new_explicit_owner_adoption"
        and candidate.get("required_owner_decision") == "owner_adopts_local_session_schema_projection_only"
        and candidate.get("required_scope") == "no_new_0843_provider_attempt"
        and candidate.get("provider_calls_made") == 0
        and candidate.get("native_admission_permitted") is False
        and candidate.get("result_promotion_permitted") is False,
        "adoption candidate is malformed",
    )
    _require(
        candidate.get("bindings") == {
            "original_message_sha256": ORIGINAL_MESSAGE_SHA256,
            "projected_message_sha256": PROJECTED_MESSAGE_SHA256,
            "response_schema_sha256": SCHEMA_SHA256,
            "outcome_sha256": OUTCOME_SHA256,
            "attempt_sha256": ATTEMPT_SHA256,
            "session_attestation_sha256": SESSION_ATTESTATION_SHA256,
            "incident_key": INCIDENT_KEY,
            "incident_revoked_at_utc": INCIDENT_REVOKED_AT_UTC,
        },
        "adoption candidate bindings drifted",
    )
    _require(candidate.get("candidate_sha256") == VERIFIED_CANDIDATE_SHA256, "adoption candidate does not bind the verified candidate")


def _parse_utc(value: Any, label: str) -> datetime:
    _require(isinstance(value, str) and value.endswith("Z"), f"{label} must be a UTC Z timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError(f"{label} is not an ISO UTC timestamp") from error
    return parsed.astimezone(UTC)


def validate_adoption(*, adoption: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a fresh owner decision while retaining the native-result ceiling."""
    required = {
        "format_version", "kind", "cell_id", "decision", "decision_at_utc", "adoption_candidate_sha256", "bindings", "scope",
        "native_cli_envelope_or_request_id_limitation", "authorizes_new_0843_provider_attempt", "authorizes_native_admission", "authorizes_result_promotion",
    }
    _require(set(adoption) == required, "adoption record has unsupported or missing fields")
    _validate_adoption_candidate(candidate)
    _require(adoption.get("format_version") == 1 and adoption.get("kind") == "wpb0843_schema_projection_owner_adoption" and adoption.get("cell_id") == CELL_ID, "adoption identity is malformed")
    _require(adoption.get("decision") == candidate.get("required_owner_decision") and adoption.get("scope") == candidate.get("required_scope"), "adoption does not contain the required affirmative limited decision")
    _require(adoption.get("adoption_candidate_sha256") == sha256(dict(candidate)), "adoption does not bind the exact candidate")
    _require(adoption.get("bindings") == candidate.get("bindings"), "adoption bindings differ from the candidate")
    _require(adoption.get("native_cli_envelope_or_request_id_limitation") == "accepted_no_cli_envelope_or_request_id_binding" and adoption.get("authorizes_new_0843_provider_attempt") is False and adoption.get("authorizes_native_admission") is False and adoption.get("authorizes_result_promotion") is False, "adoption attempts to exceed the local-session recovery ceiling")
    _require(_parse_utc(adoption.get("decision_at_utc"), "adoption decision_at_utc") > _parse_utc(INCIDENT_REVOKED_AT_UTC, "incident revoked_at_utc"), "adoption must be post-incident")
    return {
        "format_version": 1,
        "kind": "wpb0843_local_session_schema_projection_adoption_validation",
        "cell_id": CELL_ID,
        "status": "accepted_local_projection_not_native_result",
        "adoption_sha256": sha256(dict(adoption)),
        "candidate_sha256": sha256(dict(candidate)),
        "provider_calls_made": 0,
        "native_admission_permitted": False,
        "result_promotion_permitted": False,
        "preserved_original_outcome": "ambiguous_validation_structured_output_error",
    }
