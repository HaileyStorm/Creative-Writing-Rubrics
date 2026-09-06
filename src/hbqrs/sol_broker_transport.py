"""One bounded native-Sol Broker request with caller-owned admission.

This is a per-batch transport primitive.  It neither constructs a Broker nor
selects or arms a route.  A future caller owns study and source admission; the
supplied Broker handles its own route and runtime gates.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Literal

from .core import HBQError

_ROUTE_NAME = "codex-chatgpt-gpt-5.6-sol"
_MODEL = "gpt-5.6-sol"
_REASONING = "high"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_STATE = {"completed", "definitely_not_contacted", "ambiguous"}


class _RetainedBindingFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactDescriptor:
    """A Broker content-addressed artifact descriptor."""

    sha256: str
    byte_length: int


@dataclass(frozen=True)
class SolNativeReceipt:
    """Bounded evidence returned by one native Sol Broker request."""

    state: Literal["completed", "definitely_not_contacted", "ambiguous"]
    route_sha256: str
    prompt_sha256: str
    prompt_byte_length: int
    planned_schema_sha256: str
    planned_schema_byte_length: int
    canonical_schema_sha256: str
    canonical_schema_byte_length: int
    disclosure_sha256: str
    disclosure_byte_length: int
    request_sha256: str | None = None
    output_sha256: str | None = None
    raw_final_message_sha256: str | None = None
    raw_final_message_byte_length: int | None = None
    events_sha256: str | None = None
    events_byte_length: int | None = None
    schema_artifact: ArtifactDescriptor | None = None
    disclosure_artifact: ArtifactDescriptor | None = None
    events_artifact: ArtifactDescriptor | None = None
    final_message_artifact: ArtifactDescriptor | None = None
    final_message_bytes: bytes | None = None
    events_bytes: bytes | None = None
    parsed_output: Any | None = None
    requested_model: str | None = None
    requested_reasoning_effort: str | None = None
    identity_evidence: str | None = None
    provider_contact_cardinality_evidence: str | None = None
    one_provider_bearing_cli_invocation_observed: bool | None = None
    one_turn_observed: bool | None = None
    zero_tool_activity_observed: bool | None = None
    failure_code: str | None = None


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json(raw: bytes, label: str) -> Any:
    if not isinstance(raw, bytes):
        raise HBQError(f"Sol {label} must be UTF-8 bytes")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in values:
            if key in output:
                raise ValueError("duplicate JSON object key")
            output[key] = value
        return output

    def constant(_: str) -> Any:
        raise ValueError("non-finite JSON number")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HBQError(f"Sol {label} is not strict UTF-8 JSON") from error


def _descriptor(value: Any, label: str) -> ArtifactDescriptor:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema_version", "sha256", "byte_length"}
        or value.get("schema_version") != 1
        or not isinstance(value.get("sha256"), str)
        or _SHA256.fullmatch(value["sha256"]) is None
        or type(value.get("byte_length")) is not int
        or value["byte_length"] <= 0
    ):
        raise HBQError(f"Sol {label} artifact descriptor is invalid")
    return ArtifactDescriptor(value["sha256"], value["byte_length"])


def _read_artifact(
    reader: Callable[[dict[str, Any]], bytes], descriptor: ArtifactDescriptor, label: str
) -> bytes:
    raw = reader({"schema_version": 1, "sha256": descriptor.sha256, "byte_length": descriptor.byte_length})
    if not isinstance(raw, bytes) or len(raw) != descriptor.byte_length or _sha256(raw) != descriptor.sha256:
        raise HBQError(f"Sol {label} artifact readback does not match its descriptor")
    return raw


def _receipt(
    state: Literal["completed", "definitely_not_contacted", "ambiguous"],
    *,
    route_sha256: str,
    prompt: bytes,
    planned_schema: bytes,
    canonical_schema: bytes,
    disclosure: bytes,
    failure_code: str | None = None,
) -> SolNativeReceipt:
    return SolNativeReceipt(
        state=state,
        route_sha256=route_sha256,
        prompt_sha256=_sha256(prompt),
        prompt_byte_length=len(prompt),
        planned_schema_sha256=_sha256(planned_schema),
        planned_schema_byte_length=len(planned_schema),
        canonical_schema_sha256=_sha256(canonical_schema),
        canonical_schema_byte_length=len(canonical_schema),
        disclosure_sha256=_sha256(disclosure),
        disclosure_byte_length=len(disclosure),
        failure_code=failure_code,
    )


def run_sol_native_batch(
    broker: Any,
    *,
    prompt_utf8: bytes,
    planned_schema_utf8: bytes,
    disclosure: Mapping[str, Any],
    expected_route_sha256: str,
    route_snapshot: Mapping[str, Any],
    event_replayer: Callable[[bytes], Mapping[str, Any]],
    precontact_hook: Callable[[], None] | None = None,
) -> SolNativeReceipt:
    """Run one pinned native Sol request and bind its retained Broker artifacts.

    Completed receipts report requested identity only.  They do not attest the
    accepted model or reasoning effort, a provider-call count, or tools being
    disabled; the execution contract reports one observed CLI invocation, turn,
    and zero observed tools.
    """
    if not isinstance(expected_route_sha256, str) or _SHA256.fullmatch(expected_route_sha256) is None:
        raise HBQError("Sol expected route SHA-256 is invalid")
    if not isinstance(route_snapshot, Mapping):
        raise HBQError("Sol route snapshot must be a mapping")
    try:
        frozen_route = json.loads(_canonical(dict(route_snapshot)).decode("utf-8"))
    except (TypeError, UnicodeDecodeError, ValueError) as error:
        raise HBQError("Sol route snapshot must be canonical JSON data") from error
    if _sha256(_canonical(frozen_route)) != expected_route_sha256:
        raise HBQError("Sol route snapshot does not match the expected route SHA-256")
    if (
        frozen_route.get("name") != _ROUTE_NAME or frozen_route.get("model") != _MODEL
        or frozen_route.get("reasoning_effort") != _REASONING
        or not isinstance(frozen_route.get("codex_cli_version"), str)
        or not frozen_route["codex_cli_version"]
        or not isinstance(frozen_route.get("codex_command"), list)
        or not isinstance(frozen_route.get("codex_command_identity"), Mapping)
        or not isinstance(frozen_route.get("auth_receipt_hash"), str)
        or _SHA256.fullmatch(frozen_route["auth_receipt_hash"]) is None
    ):
        raise HBQError("Sol route snapshot lacks native Sol runtime bindings")
    if precontact_hook is not None and not callable(precontact_hook):
        raise HBQError("Sol precontact hook must be callable")
    if not callable(event_replayer):
        raise HBQError("Sol event replayer must be callable")
    if not isinstance(prompt_utf8, bytes):
        raise HBQError("Sol prompt must be UTF-8 bytes")
    try:
        prompt_text = prompt_utf8.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HBQError("Sol prompt must be UTF-8 bytes") from error
    if prompt_text.encode("utf-8") != prompt_utf8:
        raise HBQError("Sol prompt UTF-8 bytes are not stable")
    schema = _strict_json(planned_schema_utf8, "planned schema")
    if not isinstance(schema, dict):
        raise HBQError("Sol planned schema must have an object root")
    if not isinstance(disclosure, Mapping):
        raise HBQError("Sol disclosure must be a mapping")
    try:
        frozen_disclosure = json.loads(_canonical(dict(disclosure)).decode("utf-8"))
        canonical_schema = _canonical(schema)
        canonical_disclosure = _canonical(frozen_disclosure)
    except (TypeError, UnicodeDecodeError, ValueError) as error:
        raise HBQError("Sol schema or disclosure must be canonical JSON data") from error

    method = getattr(broker, "run_codex_native_request", None)
    read_artifact = getattr(broker, "read_codex_native_artifact", None)
    read_events = getattr(broker, "read_codex_native_events", None)
    read_final = getattr(broker, "read_codex_native_final_message", None)
    if not all(callable(value) for value in (method, read_artifact, read_events, read_final)):
        raise HBQError("Sol transport requires public Broker request and artifact readers")

    request = {"prompt": prompt_text}
    request_bytes = _canonical(request)
    precontact_calls = 0

    def before_contact() -> None:
        nonlocal precontact_calls
        precontact_calls += 1
        if precontact_calls > 1:
            raise HBQError("Sol precontact hook was invoked more than once")
        if precontact_hook is not None:
            precontact_hook()

    try:
        outcome = method(
            _ROUTE_NAME,
            request,
            expected_route_sha256=expected_route_sha256,
            output_schema=schema,
            disclosure=frozen_disclosure,
            max_turns=1,
            before_contact=before_contact,
        )
    except Exception:  # noqa: BLE001 - A call was attempted; contact cannot be excluded.
        return _receipt(
            "ambiguous", route_sha256=expected_route_sha256, prompt=prompt_utf8,
            planned_schema=planned_schema_utf8, canonical_schema=canonical_schema,
            disclosure=canonical_disclosure, failure_code="broker_invocation_raised",
        )

    base = {
        "route_sha256": expected_route_sha256, "prompt": prompt_utf8,
        "planned_schema": planned_schema_utf8, "canonical_schema": canonical_schema,
        "disclosure": canonical_disclosure,
    }
    if not isinstance(outcome, Mapping) or set(outcome) != {"state", "result", "failure"}:
        return _receipt("ambiguous", **base, failure_code="malformed_broker_outcome")
    state = outcome.get("state")
    if state not in _STATE:
        return _receipt("ambiguous", **base, failure_code="unsupported_broker_state")
    if state != "completed":
        if outcome.get("result") is not None:
            return _receipt("ambiguous", **base, failure_code="noncompleted_result_present")
        return _receipt(state, **base)
    if precontact_calls != 1:
        return _receipt("ambiguous", **base, failure_code="precontact_hook_count_invalid")

    try:
        result = outcome["result"]
        if outcome.get("failure") is not None or not isinstance(result, Mapping):
            raise HBQError("Sol completed result is invalid")
        required = {
            "schema_version", "request_hash", "output", "output_hash", "runtime",
            "native_events_artifact", "native_final_message_artifact", "route_sha256",
        }
        if set(result) != required or result.get("schema_version") != 2:
            raise HBQError("Sol completed result shape is invalid")
        if result["request_hash"] != _sha256(request_bytes) or result["route_sha256"] != expected_route_sha256:
            raise HBQError("Sol request or route binding drifted")
        output_bytes = _canonical(result["output"])
        if result["output_hash"] != _sha256(output_bytes):
            raise HBQError("Sol canonical output hash drifted")
        runtime = result["runtime"]
        if not isinstance(runtime, Mapping):
            raise HBQError("Sol runtime is invalid")
        runtime_required = {
            "adapter_version", "requested_model", "requested_reasoning_effort", "identity_evidence",
            "provider_contact_cardinality_evidence", "one_provider_bearing_cli_invocation_observed",
            "one_turn_observed", "cli_version", "events_hash", "event_projection", "raw_output_hash",
            "command_identity", "command_identity_hash", "auth_receipt_hash", "execution_contract",
        }
        if set(runtime) != runtime_required:
            raise HBQError("Sol runtime shape is invalid")
        if (
            runtime["adapter_version"] != 2 or runtime["requested_model"] != _MODEL
            or runtime["requested_reasoning_effort"] != _REASONING
            or runtime["identity_evidence"] != "requested_only"
            or runtime["provider_contact_cardinality_evidence"] != "unattested"
            or runtime["one_provider_bearing_cli_invocation_observed"] is not True
            or runtime["one_turn_observed"] is not True
            or runtime["cli_version"] != frozen_route["codex_cli_version"]
            or runtime["command_identity"] != frozen_route["codex_command_identity"]
            or runtime["command_identity_hash"] != _sha256(_canonical({
                "adapter_version": 2, "codex_command": frozen_route["codex_command"],
                "model": _MODEL, "reasoning_effort": _REASONING,
            }))
            or runtime["auth_receipt_hash"] != frozen_route["auth_receipt_hash"]
            or not isinstance(runtime["events_hash"], str) or _SHA256.fullmatch(runtime["events_hash"]) is None
            or not isinstance(runtime["raw_output_hash"], str) or _SHA256.fullmatch(runtime["raw_output_hash"]) is None
        ):
            raise HBQError("Sol requested identity binding drifted")
        schema_descriptor = _descriptor(runtime["execution_contract"].get("output_schema_artifact"), "schema")
        disclosure_descriptor = _descriptor(runtime["execution_contract"].get("disclosure_artifact"), "disclosure")
        expected_contract = {
            "schema_version": 1,
            "prompt_sha256": _sha256(prompt_utf8),
            "prompt_byte_length": len(prompt_utf8),
            "output_schema_artifact": {
                "schema_version": 1, "sha256": schema_descriptor.sha256,
                "byte_length": schema_descriptor.byte_length,
            },
            "disclosure_artifact": {
                "schema_version": 1, "sha256": disclosure_descriptor.sha256,
                "byte_length": disclosure_descriptor.byte_length,
            },
            "max_turns": 1,
            "zero_tool_activity_observed": True,
            "payload_classification": frozen_disclosure.get("payload_classification"),
        }
        if runtime["execution_contract"] != expected_contract:
            raise HBQError("Sol execution contract drifted")
        events_descriptor = _descriptor(result["native_events_artifact"], "events")
        final_descriptor = _descriptor(result["native_final_message_artifact"], "final message")
        try:
            schema_bytes = _read_artifact(read_artifact, schema_descriptor, "schema")
            disclosure_bytes = _read_artifact(read_artifact, disclosure_descriptor, "disclosure")
            events_bytes = _read_artifact(read_events, events_descriptor, "events")
            final_message_bytes = _read_artifact(read_final, final_descriptor, "final message")
            projection = event_replayer(events_bytes)
            final_output = _strict_json(final_message_bytes, "final message")
            if (
                schema_bytes != canonical_schema or disclosure_bytes != canonical_disclosure
                or _canonical(final_output) != output_bytes or _sha256(events_bytes) != runtime["events_hash"]
                or _sha256(final_message_bytes) != runtime["raw_output_hash"]
                or not isinstance(projection, Mapping)
                or set(projection) != {"schema_version", "thread_id", "usage"}
                or projection != runtime["event_projection"]
            ):
                raise HBQError("Sol retained artifacts do not bind the result")
        except Exception as error:  # All failures follow a completed Broker response.
            raise _RetainedBindingFailure from error
    except _RetainedBindingFailure:
        return _receipt("ambiguous", **base, failure_code="retained_artifact_or_event_replay_invalid")
    except (AttributeError, HBQError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        return _receipt("ambiguous", **base, failure_code="completed_result_binding_invalid")

    return replace(
        _receipt("completed", **base),
        request_sha256=_sha256(request_bytes), output_sha256=_sha256(output_bytes),
        raw_final_message_sha256=_sha256(final_message_bytes), raw_final_message_byte_length=len(final_message_bytes),
        events_sha256=_sha256(events_bytes), events_byte_length=len(events_bytes),
        schema_artifact=schema_descriptor, disclosure_artifact=disclosure_descriptor,
        events_artifact=events_descriptor, final_message_artifact=final_descriptor,
        final_message_bytes=final_message_bytes, events_bytes=events_bytes, parsed_output=final_output,
        requested_model=runtime["requested_model"], requested_reasoning_effort=runtime["requested_reasoning_effort"],
        identity_evidence=runtime["identity_evidence"],
        provider_contact_cardinality_evidence=runtime["provider_contact_cardinality_evidence"],
        one_provider_bearing_cli_invocation_observed=runtime["one_provider_bearing_cli_invocation_observed"],
        one_turn_observed=runtime["one_turn_observed"],
        zero_tool_activity_observed=runtime["execution_contract"]["zero_tool_activity_observed"],
    )
