"""Prospective continuation of the frozen v5 WPB suffix after local 1088 recovery."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
HELPER_PATH = Path(__file__).resolve()
FROZEN_HELPER = HERE / "recovery_v5_suffix.py"
FROZEN_HELPER_SHA256 = "2d1b1a5a3a9191a8580325da3d303d158ab4a736052c38a1fc01e8bcd41ab504"
SCHEMA_HELPER = HERE / "schema_recovery.py"
SCHEMA_HELPER_SHA256 = "ddc20ac7a57083eca8322631c741be35dd5cc54382800022ce9ee859e57d9105"
CELL_ID = "wpb-pair-wpb-en-1088"
PROPOSAL_SHA256 = "8bbe7e51a6f395a9ec3eeaff52f521eef0823a1b1604373f29fbcdccffee671a"
ORIGINAL_MESSAGE_SHA256 = "5bc53f84756bb63a6fdc7a5806302a4b7ef075b2861166c74a42440d0951cb46"
PROJECTED_MESSAGE_SHA256 = "a2255d3acb4b7d8b464afc2b16e3706e4c12361e693a682b256031a42683b3b0"
SCHEMA_SHA256 = "3e7ff15aa844dd6f6b3c8c091cae5335eb1b290ca5eeddabb0eab6c29afc6b0e"
REMAINING_CELL_IDS = (
    "wpb-pair-wpb-en-1093", "wpb-pair-wpb-en-1102", "wpb-pair-wpb-en-1130",
    "wpb-pair-wpb-en-1138", "wpb-pair-wpb-en-1149", "wpb-pair-wpb-en-1153",
    "wpb-pair-wpb-en-1159", "wpb-pair-wpb-en-1176", "wpb-pair-wpb-en-1181",
    "wpb-pair-wpb-en-1185", "wpb-pair-wpb-en-1192",
)
_HEX = set("0123456789abcdef")
_LOCK = threading.RLock()


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _hex(value: Any, label: str) -> str:
    _require(isinstance(value, str) and len(value) == 64 and set(value) <= _HEX, f"{label} must be a lowercase SHA-256")
    return value


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    _require(path.is_file(), f"{label} is absent")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not UTF-8 JSON") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value, raw


def _descriptor(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _hash(path.read_bytes())}


def _load(path: Path, digest: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    _require(_hash(raw) == digest, f"{name} source drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{name} changed during load")
    return module


def _old() -> ModuleType:
    return _load(FROZEN_HELPER, FROZEN_HELPER_SHA256, "wpb1088_frozen_v5")


def _schema() -> ModuleType:
    return _load(SCHEMA_HELPER, SCHEMA_HELPER_SHA256, "wpb1088_schema_recovery")


def _utc(value: Any) -> None:
    _require(isinstance(value, str), "owner adoption approved_at must be an ISO UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("owner adoption approved_at must be an ISO UTC timestamp") from error
    _require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, "owner adoption approved_at must be UTC")


def _diff(before: Any, after: Any, prefix: str = "") -> set[str]:
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        _require(set(before) == set(after), "projection object keys drifted")
        return set().union(*(_diff(before[key], after[key], f"{prefix}.{key}" if prefix else key) for key in before))
    return set() if before == after else {prefix}


def _source_bindings(value: Mapping[str, Any]) -> dict[str, str]:
    bindings = value.get("source_bindings")
    _require(isinstance(bindings, Mapping) and len(bindings) == 9, "proposal source bindings are malformed")
    normalized: dict[str, str] = {}
    for raw_path, digest in bindings.items():
        _require(isinstance(raw_path, str), "proposal source path is malformed")
        path = Path(raw_path).resolve()
        normalized[str(path)] = _hex(digest, "proposal source hash")
        _require(path.is_file() and _hash(path.read_bytes()) == digest, "proposal source drifted")
    return normalized


def _validate_projection(proposal_root: Path, expected_proposal_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    proposal, proposal_raw = _json(proposal_root / "proposal.json", "1088 proposal")
    _require(_hash(proposal_raw) == _hex(expected_proposal_sha256, "expected proposal hash"), "1088 proposal hash drifted")
    _require(expected_proposal_sha256 == PROPOSAL_SHA256, "1088 proposal is not the independently reviewed proposal")
    required = {"format_version", "kind", "cell_id", "status", "authorizes_new_attempt", "ordinary_native_admission", "result_promotion_authority", "provider_calls_made", "native_cli_envelope_binding", "process_exit_code", "provider_identity_attested", "original_outcome_preserved", "retained_message_matches_update", "all_other_values_unchanged", "changes", "original_message_sha256", "projected_message_sha256", "schema_sha256", "frozen_core", "local_summary_request_id_sha256", "session_id_sha256", "session_attestation_sha256", "source_bindings", "attestation_time_basis"}
    _require(set(proposal) == required, "1088 proposal fields drifted")
    _require(proposal.get("format_version") == 1 and proposal.get("kind") == "wpb1088_local_session_schema_projection_candidate" and proposal.get("cell_id") == CELL_ID and proposal.get("status") == "verified_pending_independent_review_and_owner_adoption", "1088 proposal identity drifted")
    _require(proposal.get("authorizes_new_attempt") is False and proposal.get("ordinary_native_admission") is False and proposal.get("result_promotion_authority") is False and proposal.get("provider_calls_made") == 0 and proposal.get("native_cli_envelope_binding") == "missing" and proposal.get("process_exit_code") is None and proposal.get("provider_identity_attested") is False and proposal.get("original_outcome_preserved") is True and proposal.get("retained_message_matches_update") is True and proposal.get("all_other_values_unchanged") is True, "1088 proposal exceeds its local recovery ceiling")
    _require(proposal.get("original_message_sha256") == ORIGINAL_MESSAGE_SHA256 and proposal.get("projected_message_sha256") == PROJECTED_MESSAGE_SHA256 and proposal.get("schema_sha256") == SCHEMA_SHA256 and proposal.get("frozen_core") == {"commit": "b43f68381f3767b590ef68b19ddb8206c8818cda", "sha256": "ef1f8d5e45da1700283ef351ab943ec39abedb103ad1ef979d731d4934d32caf", "response_valid": True}, "1088 proposal commitments drifted")
    originals, original_raw = _json(proposal_root / "original-agent-message.json", "1088 original message")
    projected, projected_raw = _json(proposal_root / "projected-agent-message.json", "1088 projected message")
    schema, schema_raw = _json(proposal_root / "response-schema.json", "1088 proposal schema")
    _require(_hash(original_raw) == ORIGINAL_MESSAGE_SHA256 and _hash(projected_raw) == PROJECTED_MESSAGE_SHA256 and _hash(schema_raw) == SCHEMA_SHA256, "1088 projection artifact drifted")
    before, after = originals.get("B", {}).get("evidence", {}).get("core"), projected.get("B", {}).get("evidence", {}).get("core")
    _require(isinstance(before, str) and isinstance(after, str) and len(before) == 181 and len(after) == 180 and after == before[:180] and _diff(originals, projected) == {"B.evidence.core"}, "1088 projection must be the exact one-character evidence prefix")
    _require(proposal.get("changes") == [{"operation": "prefix_truncate_to_schema_max_length", "original_characters": 181, "path": "B.evidence.core", "projected_characters": 180}], "1088 proposal diff declaration drifted")
    _source_bindings(proposal)
    return proposal, originals, projected, schema


def verify_projection(*, proposal_root: Path | str, expected_proposal_sha256: str, adoption_path: Path | str, expected_adoption_sha256: str) -> dict[str, Any]:
    """Return the owner-adopted 1088 local projection; it is never native evidence."""
    root, adoption_file = Path(proposal_root).resolve(), Path(adoption_path).resolve()
    proposal, _original, projected, _proposal_schema = _validate_projection(root, expected_proposal_sha256)
    adoption, adoption_raw = _json(adoption_file, "1088 owner adoption")
    _require(_hash(adoption_raw) == _hex(expected_adoption_sha256, "expected adoption hash"), "1088 owner adoption hash drifted")
    required = {"schema_version", "kind", "cell_id", "decision", "proposal_sha256", "approved_at", "resend_authority", "ordinary_native_admission"}
    _require(set(adoption) == required and adoption.get("schema_version") == 1 and adoption.get("kind") == "wpb1088_local_session_projection_owner_adoption" and adoption.get("cell_id") == CELL_ID and adoption.get("decision") == "owner_adopts_exact_local_session_projection" and adoption.get("proposal_sha256") == expected_proposal_sha256 and adoption.get("resend_authority") is False and adoption.get("ordinary_native_admission") is False, "1088 owner adoption is malformed or exceeds the local recovery ceiling")
    _utc(adoption.get("approved_at"))
    source = {Path(path).name: digest for path, digest in _source_bindings(proposal).items()}
    _require(source.get("v5-attempt.json") is not None and source.get("request.json") is not None and source.get("outcome.json") is not None, "1088 source cell binding is absent")
    source_root = Path(next(path for path in _source_bindings(proposal) if path.endswith("\\v5-attempt.json") or path.endswith("/v5-attempt.json"))).parent
    attempt, _attempt_raw = _json(source_root / "v5-attempt.json", "1088 attempt")
    outcome, _outcome_raw = _json(source_root / "outcome.json", "1088 outcome")
    _require(attempt.get("cell_id") == CELL_ID and attempt.get("payload_sha256") and attempt.get("request_sha256") == source["request.json"] and attempt.get("session_id_hash") == proposal.get("session_id_sha256") and outcome.get("state") == "ambiguous" and outcome.get("result") is None, "1088 source cell drifted")
    schema_helper = _schema()
    frozen_core = schema_helper._validate_frozen_core(projected)
    payload_sha256 = _hex(attempt["payload_sha256"], "1088 payload hash")
    return {
        "measurement": {"endpoint": "grok", "cell_id": CELL_ID, "payload_sha256": payload_sha256,
                        "measurement_provenance": {"endpoint": "grok", "cell_id": CELL_ID, "payload_sha256": payload_sha256, "parsed_response_sha256": schema_helper._frozen_response_sha256(projected)},
                        "response": projected},
        "provenance": {"classification": "local_session_schema_recovered", "native_admission_permitted": False, "proposal_kind": proposal["kind"], "schema_sha256": SCHEMA_SHA256, "frozen_core": frozen_core, "full_field_diff": proposal["changes"]},
        "bindings": {"proposal_root": str(root), "expected_proposal_sha256": expected_proposal_sha256, "adoption_path": str(adoption_file), "expected_adoption_sha256": expected_adoption_sha256},
        "local_identity": {"request_id_sha256": proposal["local_summary_request_id_sha256"], "session_id_sha256": proposal["session_id_sha256"]},
    }


def _projection_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    _require(set(binding) == {"proposal_root", "expected_proposal_sha256", "adoption_path", "expected_adoption_sha256"}, "projection binding fields drifted")
    return verify_projection(**dict(binding))


def _composition(*, projection_binding: Mapping[str, Any], independent_continuation_review: Mapping[str, Any], require_live: bool, old_kwargs: Mapping[str, Any]) -> tuple[dict[str, Any], ModuleType, dict[str, Any], ModuleType]:
    projection = _projection_binding(projection_binding)
    old = _old()
    _plan, authority, frozen, _suffix = old._authority(require_live=require_live, **dict(old_kwargs))
    review = dict(independent_continuation_review)
    required = {"format_version", "kind", "decision", "wrapper", "frozen_helper", "projection", "remaining_cell_ids", "old_review", "route", "route_sha256", "gate", "gate_sha256"}
    _require(set(review) == required and review.get("format_version") == 1 and review.get("kind") == "wpb1088_prospective_continuation_review" and review.get("decision") == "approved_wpb1088_local_projection_and_remaining_native_continuation", "continuation review identity drifted")
    _require(review.get("wrapper") == _descriptor(HELPER_PATH) and review.get("frozen_helper") == {"path": str(FROZEN_HELPER.resolve()), "sha256": FROZEN_HELPER_SHA256}, "continuation helper binding drifted")
    _require(review.get("projection") == projection["bindings"] and review.get("remaining_cell_ids") == list(REMAINING_CELL_IDS), "continuation projection or target binding drifted")
    _require(review.get("old_review") == authority["review"] and review.get("route") == authority["route"] and review.get("gate") == authority["gate"] and review.get("route_sha256") == _hash(authority["route"]) and review.get("gate_sha256") == _hash(authority["gate"]), "continuation old review, route, or gate binding drifted")
    return projection, old, authority, frozen


def _native_target(cell_id: str) -> None:
    _require(cell_id != CELL_ID, "1088 is a local projection and must never be resent or natively admitted")
    _require(cell_id in REMAINING_CELL_IDS, "continuation is limited to the eleven untouched native cells")


def _provenance(cell_id: str, projection: Mapping[str, Any], review: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "kind": "wpb1088_continuation_wrapper_provenance", "cell_id": cell_id, "wrapper": _descriptor(HELPER_PATH), "frozen_helper": {"path": str(FROZEN_HELPER.resolve()), "sha256": FROZEN_HELPER_SHA256}, "projection": dict(projection["bindings"]), "continuation_review_sha256": _hash(dict(review))}


def _verify_provenance(*, suffix_root: Path | str, cell_id: str, projection: Mapping[str, Any], review: Mapping[str, Any]) -> None:
    actual, _raw = _json(Path(suffix_root).resolve() / "cells" / cell_id / "continuation-wrapper-provenance.json", "continuation wrapper provenance")
    _require(actual == _provenance(cell_id, projection, review), "continuation wrapper provenance drifted")


def _prepare_provenance(*, frozen: ModuleType, suffix_root: Path | str, cell_id: str, projection: Mapping[str, Any], review: Mapping[str, Any]) -> None:
    cell = Path(suffix_root).resolve() / "cells" / cell_id
    path, expected = cell / "continuation-wrapper-provenance.json", _provenance(cell_id, projection, review)
    consumed = tuple(cell / name for name in ("v5-attempt.json", "outcome.json", "v5-admission.json"))
    _require(not any(marker.exists() for marker in consumed), "v5 cell is already consumed; no retry")
    if path.exists():
        _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=review)
        return
    try:
        frozen._write_new(path, expected)
    except FileExistsError:
        _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=review)


def _with_overrides(*, old: ModuleType, projection: Mapping[str, Any], composition: Callable[[], Any], provenance_check: Callable[[], None], operation: Callable[[], Any]) -> Any:
    old_verify, old_guard, old_admission = old._verify_admission, old._guard_inflight, old._admission
    def verify(**kwargs: Any) -> Any:
        if kwargs.get("cell_id") == CELL_ID:
            return {"cell_id": CELL_ID, "classification": projection["provenance"]["classification"]}
        return old_verify(**kwargs)
    def guard(**kwargs: Any) -> Any:
        result = old_guard(**kwargs)
        composition()
        provenance_check()
        return result
    def admission(**kwargs: Any) -> Any:
        value = old_admission(**kwargs)
        _require(value.get("request_id_sha256") != projection["local_identity"]["request_id_sha256"] and value.get("session_id_sha256") != projection["local_identity"]["session_id_sha256"], "new native cell reuses 1088 local request or session identity")
        return value
    with _LOCK:
        old._verify_admission, old._guard_inflight, old._admission = verify, guard, admission
        try:
            return operation()
        finally:
            old._verify_admission, old._guard_inflight, old._admission = old_verify, old_guard, old_admission


def dispatch(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str, reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any], projection_binding: Mapping[str, Any], independent_continuation_review: Mapping[str, Any]) -> dict[str, Any]:
    _native_target(cell_id)
    old_kwargs = {"recovery_root": recovery_root, "suffix_root": suffix_root, "expected_plan_sha256": expected_plan_sha256, "reviewed_path": reviewed_path, "expected_review_sha256": expected_review_sha256, "candidate": candidate}
    projection, old, _authority, frozen = _composition(projection_binding=projection_binding, independent_continuation_review=independent_continuation_review, require_live=True, old_kwargs=old_kwargs)
    _prepare_provenance(frozen=frozen, suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=independent_continuation_review)
    return _with_overrides(old=old, projection=projection, composition=lambda: _composition(projection_binding=projection_binding, independent_continuation_review=independent_continuation_review, require_live=True, old_kwargs=old_kwargs), provenance_check=lambda: _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=independent_continuation_review), operation=lambda: old.dispatch(cell_id=cell_id, **old_kwargs))


def admit(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str, reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any], projection_binding: Mapping[str, Any], independent_continuation_review: Mapping[str, Any]) -> dict[str, Any]:
    _native_target(cell_id)
    old_kwargs = {"recovery_root": recovery_root, "suffix_root": suffix_root, "expected_plan_sha256": expected_plan_sha256, "reviewed_path": reviewed_path, "expected_review_sha256": expected_review_sha256, "candidate": candidate}
    projection, old, _authority, _frozen = _composition(projection_binding=projection_binding, independent_continuation_review=independent_continuation_review, require_live=False, old_kwargs=old_kwargs)
    _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=independent_continuation_review)
    return _with_overrides(old=old, projection=projection, composition=lambda: _composition(projection_binding=projection_binding, independent_continuation_review=independent_continuation_review, require_live=False, old_kwargs=old_kwargs), provenance_check=lambda: _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=independent_continuation_review), operation=lambda: old.admit(cell_id=cell_id, **old_kwargs))


def verify_native(*, recovery_root: Path | str, suffix_root: Path | str, expected_plan_sha256: str, cell_id: str, reviewed_path: Path | str, expected_review_sha256: str, candidate: Mapping[str, Any], projection_binding: Mapping[str, Any], independent_continuation_review: Mapping[str, Any]) -> dict[str, Any]:
    _native_target(cell_id)
    old_kwargs = {"recovery_root": recovery_root, "suffix_root": suffix_root, "expected_plan_sha256": expected_plan_sha256, "reviewed_path": reviewed_path, "expected_review_sha256": expected_review_sha256, "candidate": candidate}
    projection, old, _authority, _frozen = _composition(projection_binding=projection_binding, independent_continuation_review=independent_continuation_review, require_live=False, old_kwargs=old_kwargs)
    _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=independent_continuation_review)
    return _with_overrides(old=old, projection=projection, composition=lambda: _composition(projection_binding=projection_binding, independent_continuation_review=independent_continuation_review, require_live=False, old_kwargs=old_kwargs), provenance_check=lambda: _verify_provenance(suffix_root=suffix_root, cell_id=cell_id, projection=projection, review=independent_continuation_review), operation=lambda: old._verify_admission(cell_id=cell_id, **old_kwargs))
