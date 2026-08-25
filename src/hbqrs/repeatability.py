"""Experimental provider-free v1 contracts for repeated and paired A/B studies.

These helpers deliberately describe evidence already produced by a runner. They
are callable as ``hbqrs.repeatability`` and intentionally are not runner/CLI wired.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import statistics
from typing import Any


_HEX = frozenset("0123456789abcdef")
_CONTROL_STATES = frozenset({"supported", "unsupported"})
_CODEX_PROVIDERS = frozenset({"codex", "codex_cli"})
_PATH_KEYS = frozenset({"path", "file", "filename", "directory", "root"})


class RepeatabilityContractError(ValueError):
    """Raised when a proposed repeatability record is not independently usable."""


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON value in one path-independent canonical representation."""
    try:
        payload = json.dumps(
            value, ensure_ascii=True, separators=(",", ":"), sort_keys=True, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RepeatabilityContractError("value must be finite JSON data") from error
    return sha256(payload).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise RepeatabilityContractError(f"{name} must be a mapping")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in _HEX for char in value):
        raise RepeatabilityContractError(f"{name} must be a lowercase SHA-256")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RepeatabilityContractError(f"{name} must be a nonempty string")
    return value


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise RepeatabilityContractError(f"{name} must be a finite number")
    return float(value)


def _ordered_hashes(value: Any, name: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RepeatabilityContractError(f"{name} must be an ordered sequence")
    return [_sha256(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _session_hashes(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise RepeatabilityContractError(f"{name} must be a nonempty ordered sequence")
    hashes = tuple(
        sha256(_text(session, f"{name}[{index}]").encode("utf-8")).hexdigest()
        for index, session in enumerate(value)
    )
    if len(set(hashes)) != len(hashes):
        raise RepeatabilityContractError("accepted session identity was reused within one replicate")
    return hashes


def _path_free_json(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise RepeatabilityContractError(f"{name} keys must be nonempty strings")
            lowered = key.casefold()
            if lowered in _PATH_KEYS or "path" in lowered or lowered.endswith(("_bin", "_file")):
                raise RepeatabilityContractError(f"{name} must not contain local-path settings")
            normalized[key] = _path_free_json(item, f"{name}.{key}")
        return normalized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_path_free_json(item, name) for item in value]
    if isinstance(value, str):
        if value.startswith(("/", "\\", "~")) or "\\" in value or (len(value) > 2 and value[1:3] == ":/"):
            raise RepeatabilityContractError(f"{name} must not contain local-path values")
        return value
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise RepeatabilityContractError(f"{name} must be finite JSON data")


def _controls(value: Any, provider: str) -> dict[str, dict[str, Any]]:
    raw = _mapping(value, "deterministic_control_support")
    if set(raw) != {"seed", "temperature"}:
        raise RepeatabilityContractError("deterministic_control_support requires exactly seed and temperature")
    normalized: dict[str, dict[str, Any]] = {}
    for control, raw_control in raw.items():
        record = _mapping(raw_control, f"{control} support")
        if set(record) != {"state", "value"} or record["state"] not in _CONTROL_STATES:
            raise RepeatabilityContractError(f"{control} support requires state and value")
        state = record["state"]
        supported_value = record["value"]
        if state == "unsupported" and supported_value is not None:
            raise RepeatabilityContractError(f"unsupported {control} must have a null value")
        if state == "supported" and supported_value is None:
            raise RepeatabilityContractError(f"supported {control} requires a committed value")
        normalized[control] = {"state": state, "value": supported_value}
    if provider.casefold() in _CODEX_PROVIDERS and any(
        normalized[name]["state"] != "unsupported" or normalized[name]["value"] is not None
        for name in ("seed", "temperature")
    ):
        raise RepeatabilityContractError("Codex requires explicit unsupported seed and temperature controls")
    return normalized


def content_address(
    *,
    artifact_sha256: str,
    context_sha256: Sequence[str],
    compiled_bundle_sha256: str,
    question_sha256: str,
    prompt_sha256: str,
    response_schema_sha256: str,
    judge_stack: Mapping[str, Any],
    provider: str,
    model: str,
    reasoning: str | None,
    deterministic_control_support: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a path-free identity for bytes and the complete judging stack.

    Context order is intentionally retained: changing prefix order changes the
    task.  Retry/dispatch configuration deliberately lives in a distinct run
    configuration: it does not change identical evaluation content.
    """
    provider = _text(provider, "provider")
    identity = {
        "format_version": 1,
        "artifact_sha256": _sha256(artifact_sha256, "artifact_sha256"),
        "context_sha256": _ordered_hashes(context_sha256, "context_sha256"),
        "compiled_bundle_sha256": _sha256(compiled_bundle_sha256, "compiled_bundle_sha256"),
        "question_sha256": _sha256(question_sha256, "question_sha256"),
        "prompt_sha256": _sha256(prompt_sha256, "prompt_sha256"),
        "response_schema_sha256": _sha256(response_schema_sha256, "response_schema_sha256"),
        "judge_stack": _path_free_json(_mapping(judge_stack, "judge_stack"), "judge_stack"),
        "provider": provider,
        "model": _text(model, "model"),
        "reasoning": reasoning if reasoning is None else _text(reasoning, "reasoning"),
        "deterministic_control_support": _controls(deterministic_control_support, provider),
    }
    canonical_json_sha256(identity)  # validates nested JSON before publishing it.
    return {**identity, "content_address_sha256": canonical_json_sha256(identity)}


def run_config_sha256(run_config: Mapping[str, Any]) -> str:
    """Hash path-free dispatch settings separately from evaluation content."""
    normalized = _path_free_json(_mapping(run_config, "run_config"), "run_config")
    return canonical_json_sha256({"format_version": 1, "run_config": normalized})


@dataclass(frozen=True)
class FreshReplicateReceipt:
    """One independently dispatched, accepted replicate, never a retry."""

    replicate_group_id: str
    replicate_index: int
    content_address_sha256: str
    run_config_sha256: str
    accepted_session_id_sha256: tuple[str, ...]
    run_receipt_sha256: str
    score: float
    observation_kind: str = "fresh_replicate"

    def __post_init__(self) -> None:
        _text(self.replicate_group_id, "replicate_group_id")
        if isinstance(self.replicate_index, bool) or not isinstance(self.replicate_index, int) or self.replicate_index < 1:
            raise RepeatabilityContractError("replicate_index must be a positive integer")
        _sha256(self.content_address_sha256, "content_address_sha256")
        _sha256(self.run_config_sha256, "run_config_sha256")
        if not self.accepted_session_id_sha256:
            raise RepeatabilityContractError("accepted session identities must be nonempty")
        for index, session in enumerate(self.accepted_session_id_sha256):
            _sha256(session, f"accepted_session_id_sha256[{index}]")
        if len(set(self.accepted_session_id_sha256)) != len(self.accepted_session_id_sha256):
            raise RepeatabilityContractError("accepted session identity was reused within one replicate")
        _sha256(self.run_receipt_sha256, "run_receipt_sha256")
        _finite_number(self.score, "score")
        if self.observation_kind != "fresh_replicate":
            raise RepeatabilityContractError("fresh receipt observation_kind is malformed")

    def as_dict(self) -> dict[str, Any]:
        return {
            "format_version": 1,
            "replicate_group_id": self.replicate_group_id,
            "replicate_index": self.replicate_index,
            "content_address_sha256": self.content_address_sha256,
            "run_config_sha256": self.run_config_sha256,
            "accepted_session_id_sha256": list(self.accepted_session_id_sha256),
            "run_receipt_sha256": self.run_receipt_sha256,
            "score": self.score,
            "observation_kind": self.observation_kind,
        }

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.as_dict())


def fresh_replicate_receipt(
    *,
    replicate_group_id: str,
    replicate_index: int,
    content_address_sha256: str,
    run_config_sha256: str,
    accepted_session_ids: Sequence[str],
    run_receipt_sha256: str,
    score: float,
) -> FreshReplicateReceipt:
    """Seal a fresh run without recording raw accepted session identities."""
    if isinstance(replicate_index, bool) or not isinstance(replicate_index, int) or replicate_index < 1:
        raise RepeatabilityContractError("replicate_index must be a positive integer")
    return FreshReplicateReceipt(
        replicate_group_id=_text(replicate_group_id, "replicate_group_id"),
        replicate_index=replicate_index,
        content_address_sha256=_sha256(content_address_sha256, "content_address_sha256"),
        run_config_sha256=_sha256(run_config_sha256, "run_config_sha256"),
        accepted_session_id_sha256=_session_hashes(accepted_session_ids, "accepted_session_ids"),
        run_receipt_sha256=_sha256(run_receipt_sha256, "run_receipt_sha256"),
        score=_finite_number(score, "score"),
    )


@dataclass(frozen=True)
class DerivedReuseReceipt:
    """A content-addressed reuse, explicitly not an independent observation."""

    source_receipt_sha256: str
    content_address_sha256: str
    reuse_purpose: str
    independent_observation: bool = False
    observation_kind: str = "derived_reuse"

    def __post_init__(self) -> None:
        _sha256(self.source_receipt_sha256, "source_receipt_sha256")
        _sha256(self.content_address_sha256, "content_address_sha256")
        _text(self.reuse_purpose, "reuse_purpose")
        if self.independent_observation is not False or self.observation_kind != "derived_reuse":
            raise RepeatabilityContractError("derived reuse must remain a non-independent observation")

    def as_dict(self) -> dict[str, Any]:
        return {
            "format_version": 1,
            "source_receipt_sha256": self.source_receipt_sha256,
            "content_address_sha256": self.content_address_sha256,
            "reuse_purpose": self.reuse_purpose,
            "independent_observation": self.independent_observation,
            "observation_kind": self.observation_kind,
        }

    @property
    def receipt_sha256(self) -> str:
        return canonical_json_sha256(self.as_dict())


def derived_reuse_receipt(
    *,
    source: FreshReplicateReceipt,
    requested_content_address_sha256: str,
    reuse_purpose: str,
) -> DerivedReuseReceipt:
    """Bind a reuse record to exactly one completed fresh receipt."""
    if not isinstance(source, FreshReplicateReceipt):
        raise RepeatabilityContractError("reuse source must be a fresh replicate receipt")
    requested = _sha256(requested_content_address_sha256, "requested_content_address_sha256")
    if requested != source.content_address_sha256:
        raise RepeatabilityContractError("requested content address does not match reuse source")
    return DerivedReuseReceipt(
        source_receipt_sha256=source.receipt_sha256,
        content_address_sha256=requested,
        reuse_purpose=_text(reuse_purpose, "reuse_purpose"),
    )


def _validate_fresh_group(receipts: Sequence[FreshReplicateReceipt]) -> list[FreshReplicateReceipt]:
    if not isinstance(receipts, Sequence) or isinstance(receipts, (str, bytes, bytearray)) or len(receipts) < 2:
        raise RepeatabilityContractError("a replicate group requires at least two fresh receipts")
    if any(not isinstance(receipt, FreshReplicateReceipt) for receipt in receipts):
        raise RepeatabilityContractError("derived reuse records are not independent observations")
    rows = list(receipts)
    groups = {row.replicate_group_id for row in rows}
    addresses = {row.content_address_sha256 for row in rows}
    run_configs = {row.run_config_sha256 for row in rows}
    indices = [row.replicate_index for row in rows]
    sessions = [session for row in rows for session in row.accepted_session_id_sha256]
    run_hashes = [row.run_receipt_sha256 for row in rows]
    if len(groups) != 1 or len(addresses) != 1:
        raise RepeatabilityContractError("replicate group must share one content address")
    if len(run_configs) != 1:
        raise RepeatabilityContractError("exact replicate group must share one run configuration")
    if sorted(indices) != list(range(1, len(rows) + 1)):
        raise RepeatabilityContractError("replicate indices must be complete and unique from one")
    if len(sessions) != len(set(sessions)):
        raise RepeatabilityContractError("accepted session identity was reused")
    if len(run_hashes) != len(set(run_hashes)):
        raise RepeatabilityContractError("run receipt was reused")
    return sorted(rows, key=lambda row: row.replicate_index)


def summarize_replicate_group(receipts: Sequence[FreshReplicateReceipt]) -> dict[str, Any]:
    """Summarize fresh runs; retries/batch_attempts never enter this statistic."""
    rows = _validate_fresh_group(receipts)
    scores = [row.score for row in rows]
    median = statistics.median(scores)
    deviations = [abs(score - median) for score in scores]
    return {
        "format_version": 1,
        "replicate_group_id": rows[0].replicate_group_id,
        "content_address_sha256": rows[0].content_address_sha256,
        "run_config_sha256": rows[0].run_config_sha256,
        "independent_observation_count": len(rows),
        "batch_attempts_are_statistical_replication": False,
        "median": median,
        "mad": statistics.median(deviations),
        "sample_standard_deviation": statistics.stdev(scores),
        "range": max(scores) - min(scores),
        "per_run_receipt_sha256": [row.receipt_sha256 for row in rows],
    }


def paired_comparison_commitment(
    *,
    comparison_id: str,
    artifact_a_reuse: DerivedReuseReceipt,
    artifact_b_reuse: DerivedReuseReceipt,
    judge_stack_sha256: str,
    paired_contract_sha256: str,
    ab_request_bytes: bytes,
    ba_request_bytes: bytes,
    provider: str,
    deterministic_control_support: Mapping[str, Mapping[str, Any]],
    identity_control: bool = False,
) -> dict[str, Any]:
    """Commit a paired study to exactly one AB and one BA presentation."""
    provider = _text(provider, "provider")
    if not isinstance(artifact_a_reuse, DerivedReuseReceipt) or not isinstance(artifact_b_reuse, DerivedReuseReceipt):
        raise RepeatabilityContractError("paired artifacts must be validated derived reuse receipts")
    if not isinstance(identity_control, bool):
        raise RepeatabilityContractError("identity_control must be boolean")
    same_content = artifact_a_reuse.content_address_sha256 == artifact_b_reuse.content_address_sha256
    if same_content != identity_control:
        raise RepeatabilityContractError("identity_control must be true exactly when artifact content addresses are equal")
    ab_request_sha256 = sha256(_bytes(ab_request_bytes, "ab_request_bytes")).hexdigest()
    ba_request_sha256 = sha256(_bytes(ba_request_bytes, "ba_request_bytes")).hexdigest()
    if ab_request_sha256 == ba_request_sha256:
        raise RepeatabilityContractError("AB and BA requests must be distinct committed bytes")
    commitment = {
        "format_version": 1,
        "comparison_id": _text(comparison_id, "comparison_id"),
        "orders": ["AB", "BA"],
        "artifact_a_content_address_sha256": artifact_a_reuse.content_address_sha256,
        "artifact_b_content_address_sha256": artifact_b_reuse.content_address_sha256,
        "judge_stack_sha256": _sha256(judge_stack_sha256, "judge_stack_sha256"),
        "paired_contract_sha256": _sha256(paired_contract_sha256, "paired_contract_sha256"),
        "artifact_a_source_receipt_sha256": artifact_a_reuse.source_receipt_sha256,
        "artifact_b_source_receipt_sha256": artifact_b_reuse.source_receipt_sha256,
        "artifact_a_reuse_receipt_sha256": artifact_a_reuse.receipt_sha256,
        "artifact_b_reuse_receipt_sha256": artifact_b_reuse.receipt_sha256,
        "ab_request_sha256": ab_request_sha256,
        "ba_request_sha256": ba_request_sha256,
        "provider": provider,
        "deterministic_control_support": _controls(deterministic_control_support, provider),
        "identity_control": identity_control,
    }
    return {**commitment, "commitment_sha256": canonical_json_sha256(commitment)}


def _bytes(value: Any, name: str) -> bytes:
    if not isinstance(value, bytes) or not value:
        raise RepeatabilityContractError(f"{name} must be nonempty bytes")
    return value


def _validated_paired_commitment(commitment: Mapping[str, Any]) -> dict[str, Any]:
    committed = dict(_mapping(commitment, "commitment"))
    required = {
        "format_version", "comparison_id", "orders", "artifact_a_content_address_sha256",
        "artifact_b_content_address_sha256", "judge_stack_sha256", "paired_contract_sha256",
        "artifact_a_source_receipt_sha256", "artifact_b_source_receipt_sha256",
        "artifact_a_reuse_receipt_sha256", "artifact_b_reuse_receipt_sha256", "ab_request_sha256",
        "ba_request_sha256", "provider", "deterministic_control_support", "identity_control", "commitment_sha256",
    }
    if set(committed) != required or committed.get("orders") != ["AB", "BA"]:
        raise RepeatabilityContractError("paired commitment is malformed")
    expected_hash = canonical_json_sha256({key: committed[key] for key in required - {"commitment_sha256"}})
    if committed["commitment_sha256"] != expected_hash:
        raise RepeatabilityContractError("paired commitment hash does not match")
    _text(committed["comparison_id"], "comparison_id")
    _text(committed["provider"], "provider")
    if not isinstance(committed["identity_control"], bool):
        raise RepeatabilityContractError("identity_control must be boolean")
    for key in (
        "artifact_a_content_address_sha256", "artifact_b_content_address_sha256", "judge_stack_sha256",
        "paired_contract_sha256", "artifact_a_source_receipt_sha256", "artifact_b_source_receipt_sha256",
        "artifact_a_reuse_receipt_sha256", "artifact_b_reuse_receipt_sha256", "ab_request_sha256",
        "ba_request_sha256", "commitment_sha256",
    ):
        _sha256(committed[key], key)
    if committed["ab_request_sha256"] == committed["ba_request_sha256"]:
        raise RepeatabilityContractError("paired commitment did not distinguish AB and BA requests")
    same_content = committed["artifact_a_content_address_sha256"] == committed["artifact_b_content_address_sha256"]
    if same_content != committed["identity_control"]:
        raise RepeatabilityContractError("identity_control must match artifact content equality")
    _controls(committed["deterministic_control_support"], committed["provider"])
    return committed


def paired_response_envelope(
    *,
    commitment: Mapping[str, Any],
    presentation_order: str,
    request_bytes: bytes,
    accepted_session_ids: Sequence[str],
    response_bytes: bytes,
) -> dict[str, Any]:
    """Wrap one provider-facing response with local receipt fields after return."""
    if presentation_order not in {"AB", "BA"}:
        raise RepeatabilityContractError("paired response order is invalid")
    committed = _validated_paired_commitment(commitment)
    request_sha256 = sha256(_bytes(request_bytes, "request_bytes")).hexdigest()
    if request_sha256 != committed[f"{presentation_order.casefold()}_request_sha256"]:
        raise RepeatabilityContractError("request bytes do not match committed presentation order")
    raw_response = _bytes(response_bytes, "response_bytes")
    try:
        output = dict(_mapping(json.loads(raw_response.decode("utf-8")), "paired model output"))
    except (UnicodeDecodeError, json.JSONDecodeError, RepeatabilityContractError) as error:
        raise RepeatabilityContractError("paired response bytes must be strict UTF-8 JSON") from error
    if set(output) != {"winner"} or output["winner"] not in {"FIRST", "SECOND", "TIE"}:
        raise RepeatabilityContractError("paired model output must contain only winner FIRST, SECOND, or TIE")
    session_hashes = list(_session_hashes(accepted_session_ids, "accepted_session_ids"))
    response_bytes_sha256 = sha256(raw_response).hexdigest()
    model_output_sha256 = canonical_json_sha256(output)
    receipt = {
        "commitment_sha256": committed["commitment_sha256"],
        "presentation_order": presentation_order,
        "request_sha256": request_sha256,
        "accepted_session_id_sha256": session_hashes,
        "response_bytes_sha256": response_bytes_sha256,
        "model_output_sha256": model_output_sha256,
    }
    return {
        "commitment_sha256": committed["commitment_sha256"],
        "presentation_order": presentation_order,
        "request_sha256": request_sha256,
        "model_output": output,
        "model_output_sha256": model_output_sha256,
        "accepted_session_id_sha256": session_hashes,
        "response_bytes_sha256": response_bytes_sha256,
        "response_receipt_sha256": canonical_json_sha256(receipt),
    }


def _artifact_winner(order: str, position_winner: str) -> str:
    if position_winner == "TIE":
        return "TIE"
    if order == "AB":
        return "A" if position_winner == "FIRST" else "B"
    return "B" if position_winner == "FIRST" else "A"


def validate_paired_comparison(
    commitment: Mapping[str, Any], responses: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Accept only a complete AB/BA pair with identical committed inputs."""
    committed = _validated_paired_commitment(commitment)
    if not isinstance(responses, Sequence) or isinstance(responses, (str, bytes, bytearray)) or len(responses) != 2:
        raise RepeatabilityContractError("paired comparison requires exactly AB and BA responses")
    accepted: list[dict[str, Any]] = []
    for raw in responses:
        response = dict(_mapping(raw, "paired response"))
        required_response = {
            "commitment_sha256", "presentation_order", "request_sha256", "model_output",
            "model_output_sha256", "accepted_session_id_sha256", "response_bytes_sha256", "response_receipt_sha256",
        }
        if set(response) != required_response:
            raise RepeatabilityContractError("paired response envelope is malformed")
        if response["presentation_order"] not in {"AB", "BA"}:
            raise RepeatabilityContractError("paired response order is invalid")
        if response["commitment_sha256"] != committed["commitment_sha256"]:
            raise RepeatabilityContractError("paired response commitment does not match")
        expected_request = committed[f"{response['presentation_order'].casefold()}_request_sha256"]
        if response["request_sha256"] != expected_request:
            raise RepeatabilityContractError("paired response request does not match committed presentation order")
        _sha256(response["request_sha256"], "request_sha256")
        model_output = _mapping(response["model_output"], "paired model output")
        if set(model_output) != {"winner"} or model_output["winner"] not in {"FIRST", "SECOND", "TIE"}:
            raise RepeatabilityContractError("paired model output must contain only winner FIRST, SECOND, or TIE")
        if response["model_output_sha256"] != canonical_json_sha256(model_output):
            raise RepeatabilityContractError("paired response model output does not match its sealed hash")
        _sha256(response["model_output_sha256"], "model_output_sha256")
        sessions = response["accepted_session_id_sha256"]
        if not isinstance(sessions, Sequence) or isinstance(sessions, (str, bytes, bytearray)) or not sessions:
            raise RepeatabilityContractError("paired response requires accepted session identities")
        for index, session in enumerate(sessions):
            _sha256(session, f"accepted_session_id_sha256[{index}]")
        if len(set(sessions)) != len(sessions):
            raise RepeatabilityContractError("paired response reused a session identity")
        _sha256(response["response_bytes_sha256"], "response_bytes_sha256")
        _sha256(response["response_receipt_sha256"], "response_receipt_sha256")
        expected_receipt = canonical_json_sha256({
            "commitment_sha256": response["commitment_sha256"],
            "presentation_order": response["presentation_order"],
            "request_sha256": response["request_sha256"],
            "accepted_session_id_sha256": list(sessions),
            "response_bytes_sha256": response["response_bytes_sha256"],
            "model_output_sha256": response["model_output_sha256"],
        })
        if response["response_receipt_sha256"] != expected_receipt:
            raise RepeatabilityContractError("paired response receipt does not bind its envelope")
        accepted.append({
            **response,
            "normalized_artifact_winner": _artifact_winner(response["presentation_order"], model_output["winner"]),
        })
    if {row["presentation_order"] for row in accepted} != {"AB", "BA"}:
        raise RepeatabilityContractError("paired comparison must include one AB and one BA response")
    sessions = [session for row in accepted for session in row["accepted_session_id_sha256"]]
    if len(sessions) != len(set(sessions)):
        raise RepeatabilityContractError("paired comparison reused a session identity")
    if len({row["response_receipt_sha256"] for row in accepted}) != 2:
        raise RepeatabilityContractError("paired comparison reused a response receipt")
    ordered = sorted(accepted, key=lambda row: row["presentation_order"])
    first, second = ordered
    winners = {row["normalized_artifact_winner"] for row in ordered}
    positions = (first["model_output"]["winner"], second["model_output"]["winner"])
    if committed["identity_control"]:
        if positions == ("TIE", "TIE"):
            classification = "identity_control_agreement_tie"
        elif "TIE" in positions:
            classification = "identity_control_tie_mismatch"
        elif positions in {("FIRST", "FIRST"), ("SECOND", "SECOND")}:
            classification = "identity_control_position_agreement"
        else:
            classification = "identity_control_position_disagreement"
    elif len(winners) == 1:
        classification = {
            "A": "agreement_artifact_a", "B": "agreement_artifact_b", "TIE": "agreement_tie",
        }[first["normalized_artifact_winner"]]
    elif "TIE" in winners:
        classification = "tie_mismatch"
    elif positions == ("FIRST", "FIRST"):
        classification = "order_primacy"
    elif positions == ("SECOND", "SECOND"):
        classification = "order_recency"
    else:
        raise RepeatabilityContractError("paired response order effect is not classifiable")
    return {
        "commitment_sha256": committed["commitment_sha256"],
        "responses": ordered,
        "agreement_classification": classification,
    }
