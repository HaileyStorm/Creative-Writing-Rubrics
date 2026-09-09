"""Bind a v5-attested Grok Broker request into one prospective runner callback."""

from __future__ import annotations

import copy
import json
import re
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from . import grok_broker_transport_v2 as _v2
from .core import HBQError
from .runner import GrokTransportEvidenceFailure

_V1_SOURCE_SHA256 = "cd349c9b512a3524f6bd0f9787035af618754f2b06363dc2e9aceda7e72305be"
_V2_SOURCE_SHA256 = "da9698e23aee9eb4fc0daaa76b9d32dfc0090462ad6fede587b865caa363eaa5"
_V5_TRANSPORT_CONTRACT_SHA256 = "08459d7354518e3d8fbf0bc27b2c8308ef4414b2a85550ea18941c7f918ec91b"
_V5_TRANSPORT_CAPABILITY = "grok_nonvisual_history_v5"
_ATTESTED_TOOLS = "deny_wins_none_attested"
_EXECUTION_POLICY = "bounded_nonvisual_deny_wins_attested"
_LOWER_HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_V5_NONVISUAL_TRANSPORT_CONTRACT = {
    "schema_version": 1,
    "name": _V5_TRANSPORT_CAPABILITY,
    "prompt_utf8_bytes": 73_728,
    "request_stdin_bytes": 81_920,
    "prompt_history_line_bytes": 81_920,
    "first_user_message_chunk_line_bytes": 81_920,
    "other_update_line_bytes": 65_536,
    "updates_bytes": 262_144,
    "summary_bytes": 65_536,
    "stdout_bytes": 65_536,
    "stderr_bytes": 65_536,
}

_canonical = _v2._canonical
_file_descriptor = _v2._file_descriptor
_plain_source = _v2._plain_source
_recheck_source_binding = _v2._recheck_source_binding
_sha256 = _v2._sha256
_source_binding = _v2._source_binding
_write_new = _v2._write_new

if _sha256(_canonical(_V5_NONVISUAL_TRANSPORT_CONTRACT)) != _V5_TRANSPORT_CONTRACT_SHA256:
    raise RuntimeError("v5 nonvisual transport contract hash drifted")


def _route_freeze(route: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    frozen, route_sha256 = _v2._route_freeze(route)
    if (
        type(frozen["timeout_seconds"]) is not int
        or frozen["timeout_seconds"] != 300
        or type(frozen.get("max_concurrency")) is not int
        or frozen["max_concurrency"] != 1
        or type(frozen.get("nonvisual_max_turns")) is not int
        or frozen["nonvisual_max_turns"] != 1
        or type(frozen.get("capabilities")) is not list
        or _V5_TRANSPORT_CAPABILITY not in frozen["capabilities"]
        or frozen.get("nonvisual_transport_contract") != _V5_TRANSPORT_CAPABILITY
    ):
        raise HBQError("Grok broker route lacks the exact v5 nonvisual contract")
    return frozen, route_sha256


def _context_bindings(
    context: Mapping[str, Any], route: Mapping[str, Any]
) -> tuple[str, dict[str, Any], Path, int, int, dict[str, Any]]:
    prompt, schema, output_dir, batch, attempt, bindings = _v2._context_bindings(context, route)
    derived = dict(bindings)
    execution = dict(derived["execution_contract"])
    execution["nonvisual_transport_contract"] = _V5_NONVISUAL_TRANSPORT_CONTRACT
    execution["nonvisual_transport_contract_sha256"] = _V5_TRANSPORT_CONTRACT_SHA256
    derived["execution_contract"] = json.loads(_canonical(execution).decode("utf-8"))
    return prompt, schema, output_dir, batch, attempt, derived


def bind_grok_broker_transport(
    *,
    broker: Any,
    route: Mapping[str, Any],
    before_contact: Callable[[Mapping[str, Any]], None],
    runtime_check: Callable[[], None],
) -> Callable[[Mapping[str, Any]], tuple[str, dict[str, Any]]]:
    """Bind a verified v5 Broker and exact nonvisual route into one callback."""
    frozen_route, route_sha256 = _route_freeze(route)
    source_path, source_bytes = _plain_source(Path(__file__), "v5 Grok broker adapter")
    source_sha256 = _sha256(source_bytes)
    v2_path, v2_bytes = _source_binding(
        Path(_v2.__file__), _V2_SOURCE_SHA256, "v2 Grok broker helper"
    )
    v1_path, v1_bytes = _source_binding(
        Path(_v2._legacy.__file__), _V1_SOURCE_SHA256, "v1 Grok broker helper"
    )
    if not callable(before_contact) or not callable(runtime_check):
        raise HBQError("Grok broker transport requires caller admission and runtime checks")
    method = getattr(broker, "run_grok_native_request", None)
    read_envelope = getattr(broker, "read_grok_native_envelope", None)
    if not callable(method) or not callable(read_envelope):
        raise HBQError("Grok broker transport requires native request and envelope methods")

    def recheck_sources() -> None:
        _recheck_source_binding(source_path, source_bytes, source_sha256, "v5 Grok broker adapter")
        _recheck_source_binding(v2_path, v2_bytes, _V2_SOURCE_SHA256, "v2 Grok broker helper")
        _recheck_source_binding(v1_path, v1_bytes, _V1_SOURCE_SHA256, "v1 Grok broker helper")

    def transport(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        if not isinstance(context, Mapping):
            raise HBQError("Grok broker transport context must be a mapping")
        prompt, schema, output_dir, batch, attempt, bindings = _context_bindings(context, frozen_route)
        if (
            context["transport"].get("protocol") != "injected_grok_attempt_v1"
            or context["transport"].get("declared_sha256") != source_sha256
        ):
            raise HBQError("Grok broker adapter source binding drifted")
        recheck_sources()
        root = output_dir / "responses" / "grok-broker" / f"batch-{batch:04d}-attempt-{attempt:04d}"
        try:
            root.mkdir(parents=True)
        except FileExistsError as error:
            raise HBQError("Grok broker response root already exists; refusing resend") from error
        request = {"prompt": prompt}
        request_bytes = _canonical(request)
        context_bytes = _canonical(bindings)
        _write_new(root / "request.json", request_bytes)
        _write_new(root / "context-bindings.json", context_bytes)
        session_id = str(uuid.uuid4())
        frozen_context = copy.deepcopy(dict(context))
        admitted = False

        def persist_outcome(value: Mapping[str, Any]) -> Path:
            path = root / "outcome.json"
            _write_new(path, _canonical(dict(value)))
            return path

        try:
            runtime_check()

            def hook() -> None:
                nonlocal admitted
                runtime_check()
                recheck_sources()
                before_contact(copy.deepcopy(frozen_context))
                runtime_check()
                recheck_sources()
                admitted = True

            outcome = method(
                frozen_route["name"], request, output_schema=schema, nonvisual_max_turns=1,
                session_id=session_id, before_contact=hook, expected_route_sha256=route_sha256,
            )
            if not isinstance(outcome, Mapping) or set(outcome) != {"state", "result", "failure"}:
                raise HBQError("Grok broker returned a malformed outcome")
            outcome_path = persist_outcome(outcome)
            if not admitted:
                raise HBQError("Grok broker completed without the required admission callback")
            if (
                outcome["state"] != "completed"
                or outcome["failure"] is not None
                or not isinstance(outcome["result"], Mapping)
            ):
                raise HBQError("Grok broker request did not complete")
            result = dict(outcome["result"])
            required = {
                "schema_version", "request_hash", "output", "output_hash", "runtime",
                "native_envelope_artifact",
            }
            if (
                set(result) != required
                or result["schema_version"] != 2
                or result["request_hash"] != _sha256(request_bytes)
                or result["output_hash"] != _sha256(_canonical(result["output"]))
            ):
                raise HBQError("Grok broker result binding drifted")
            runtime = result["runtime"]
            descriptor = result["native_envelope_artifact"]
            if not isinstance(runtime, Mapping) or not isinstance(descriptor, Mapping):
                raise HBQError("Grok broker runtime or envelope descriptor is malformed")
            envelope_bytes = read_envelope(dict(descriptor))
            envelope_path = root / "native-envelope.json"
            _write_new(envelope_path, envelope_bytes)
            envelope = json.loads(envelope_bytes.decode("utf-8"))
            if (
                set(descriptor) != {"schema_version", "sha256", "byte_length"}
                or descriptor.get("schema_version") != 1
                or descriptor.get("sha256") != _sha256(envelope_bytes)
                or descriptor.get("byte_length") != len(envelope_bytes)
                or not isinstance(envelope, Mapping)
                or envelope.get("structuredOutput") != result["output"]
                or envelope.get("sessionId") != session_id
                or not isinstance(envelope.get("requestId"), str)
                or not envelope["requestId"]
                or runtime.get("session_id_hash") != _sha256(session_id.encode("utf-8"))
                or runtime.get("request_id_hash") != _sha256(envelope["requestId"].encode("utf-8"))
                or runtime.get("envelope_hash") != _sha256(envelope_bytes)
                or runtime.get("requested_model") != frozen_route["model"]
                or runtime.get("requested_reasoning_effort") != frozen_route["reasoning_effort"]
                or runtime.get("execution_contract") != bindings["execution_contract"]
            ):
                raise HBQError("Grok broker result identity or execution contract drifted")
            execution = runtime["execution_contract"]
            attestation = runtime.get("tool_policy_attestation_hash")
            if (
                not isinstance(execution, Mapping)
                or execution != bindings["execution_contract"]
                or execution.get("tools") != _ATTESTED_TOOLS
                or type(execution.get("max_turns")) is not int
                or execution["max_turns"] != 1
                or execution.get("nonvisual_transport_contract") != _V5_NONVISUAL_TRANSPORT_CONTRACT
                or execution.get("nonvisual_transport_contract_sha256") != _V5_TRANSPORT_CONTRACT_SHA256
                or type(runtime.get("adapter_version")) is not int
                or runtime["adapter_version"] != 5
                or runtime.get("execution_policy") != _EXECUTION_POLICY
                or runtime.get("identity_evidence") != "requested_only"
                or runtime.get("reasoning_attested") is not False
                or type(runtime.get("nonvisual_max_turns")) is not int
                or runtime["nonvisual_max_turns"] != 1
                or type(runtime.get("observed_turns")) is not int
                or runtime["observed_turns"] != 1
                or not isinstance(attestation, str)
                or _LOWER_HEX_SHA256.fullmatch(attestation) is None
            ):
                raise HBQError("Grok broker result lacks attested v5 nonvisual execution")
            runtime_check()
            recheck_sources()
            receipt = {
                "schema_version": 1,
                "source_sha256": source_sha256,
                "route_sha256": route_sha256,
                "request_sha256": _sha256(request_bytes),
                "context_sha256": _sha256(context_bytes),
                "schema_sha256": bindings["response_schema_sha256"],
                "result_sha256": _sha256(_canonical(result)),
                "outcome_sha256": _sha256(outcome_path.read_bytes()),
                "envelope_sha256": _sha256(envelope_bytes),
                "session_id_hash": _sha256(session_id.encode("utf-8")),
                "request_id_hash": _sha256(envelope["requestId"].encode("utf-8")),
            }
            receipt_path = root / "receipt.json"
            _write_new(receipt_path, _canonical(receipt))
            artifacts = {
                "request": _file_descriptor(output_dir, root / "request.json"),
                "context": _file_descriptor(output_dir, root / "context-bindings.json"),
                "outcome": _file_descriptor(output_dir, outcome_path),
                "envelope": _file_descriptor(output_dir, envelope_path),
                "receipt": _file_descriptor(output_dir, receipt_path),
            }
            metadata = {
                "model": frozen_route["model"],
                "evidence_sha256": _sha256(receipt_path.read_bytes()),
                "request_id_sha256": _sha256(envelope["requestId"].encode("utf-8")),
                "session_id_sha256": _sha256(session_id.encode("utf-8")),
                "reasoning_attested": False,
                "tool_free": True,
                "provider_artifacts": artifacts,
            }
            return json.dumps(result["output"], ensure_ascii=False), metadata
        except Exception:  # noqa: BLE001 - persist a generic rejection without exposing runtime details.
            if not (root / "outcome.json").exists():
                persist_outcome({"state": "adapter_error", "failure": {"code": "adapter_error"}})
            failure_receipt = {
                "schema_version": 1,
                "status": "not_completed",
                "source_sha256": source_sha256,
                "route_sha256": route_sha256,
                "request_sha256": _sha256(request_bytes),
                "context_sha256": _sha256(context_bytes),
                "outcome_sha256": _sha256((root / "outcome.json").read_bytes()),
            }
            envelope_path = root / "native-envelope.json"
            if envelope_path.is_file():
                failure_receipt["envelope_sha256"] = _sha256(envelope_path.read_bytes())
            failure_path = root / "failure-receipt.json"
            _write_new(failure_path, _canonical(failure_receipt))
            artifacts = {
                "receipt": _file_descriptor(output_dir, failure_path),
                "request": _file_descriptor(output_dir, root / "request.json"),
                "context": _file_descriptor(output_dir, root / "context-bindings.json"),
                "outcome": _file_descriptor(output_dir, root / "outcome.json"),
            }
            if envelope_path.is_file():
                artifacts["envelope"] = _file_descriptor(output_dir, envelope_path)
            raise GrokTransportEvidenceFailure(
                evidence_sha256=artifacts["receipt"]["sha256"], provider_artifacts=artifacts,
            ) from None

    return transport
