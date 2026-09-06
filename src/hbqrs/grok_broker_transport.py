"""Compose a caller-supplied governed Grok Broker into one runner transport call.

The caller must supply an already verified Broker instance, an immutable verified route,
and a runtime-check callback.  This module never initializes a broker, launches a
provider process directly, or offers a standalone live entry point.  Callable identity
is not evidence that a provider, route, or runtime is authentic.
"""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .core import HBQError
from .runner import GrokTransportEvidenceFailure


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_descriptor(output_dir: Path, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": path.relative_to(output_dir).as_posix(), "bytes": len(raw), "sha256": _sha256(raw)}


def _write_new(path: Path, value: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(value)


def _route_freeze(route: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    try:
        frozen = json.loads(_canonical(copy.deepcopy(dict(route))).decode("utf-8"))
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise HBQError("Grok broker route must be JSON-freezable") from error
    required = {"name", "adapter", "model", "reasoning_effort", "timeout_seconds"}
    if not required <= set(frozen) or not isinstance(frozen["name"], str) or not frozen["name"]:
        raise HBQError("Grok broker route lacks a valid name")
    if frozen["adapter"] != "grok_exec" or frozen["model"] != "grok-4.6" or frozen["reasoning_effort"] != "high":
        raise HBQError("Grok broker route adapter, model, or reasoning drifted")
    timeout = frozen["timeout_seconds"]
    if type(timeout) not in (int, float) or isinstance(timeout, bool) or timeout <= 0:
        raise HBQError("Grok broker route timeout must be positive")
    return frozen, _sha256(_canonical(frozen))


def _context_bindings(context: Mapping[str, Any], route: Mapping[str, Any]) -> tuple[str, dict[str, Any], Path, int, int, dict[str, Any]]:
    required = {"prompt", "response_schema", "output_dir", "batch", "attempt", "provider", "transport", "run"}
    if not required <= set(context) or context.get("format_version") != 1:
        raise HBQError("Grok broker context lacks runner bindings")
    for field in ("prompt", "response_schema", "batch", "attempt", "provider", "transport", "run"):
        if not isinstance(context[field], Mapping):
            raise HBQError("Grok broker context has invalid nested bindings")
    prompt = context["prompt"].get("text")
    schema_text = context["response_schema"].get("text")
    output_dir = context["output_dir"]
    batch = context["batch"].get("number")
    attempt = context["attempt"].get("number")
    if not isinstance(prompt, str) or not isinstance(schema_text, str) or not isinstance(output_dir, str):
        raise HBQError("Grok broker context has invalid prompt, schema, or output directory")
    prompt_bytes = prompt.encode("utf-8")
    schema_bytes = schema_text.encode("utf-8")
    for field, raw in (("prompt", prompt_bytes), ("response_schema", schema_bytes)):
        record = context[field]
        if (record.get("encoding") != "utf-8" or record.get("sha256") != _sha256(raw)
                or type(record.get("bytes")) is not int or record["bytes"] != len(raw)):
            raise HBQError("Grok broker context prompt or schema binding drifted")
    schema = json.loads(schema_text)
    if not isinstance(schema, dict):
        raise HBQError("Grok broker response schema must be an object")
    provider = context["provider"]
    if (provider.get("provider") != "grok" or provider.get("endpoint") is not None
            or provider.get("model") != route["model"] or provider.get("reasoning") != route["reasoning_effort"]
            or context["transport"].get("timeout") != route["timeout_seconds"]):
        raise HBQError("Grok broker context route binding drifted")
    if (type(batch) is not int or batch < 1 or type(attempt) is not int or attempt != 1
            or type(context["attempt"].get("batch_attempts")) is not int or context["attempt"]["batch_attempts"] != 1):
        raise HBQError("Grok broker context requires a positive batch and attempt 1")
    execution = {"schema_version": 1, "output_schema_hash": _sha256(_canonical(schema)),
                 "max_turns": 1, "tools": "none", "staged_prompt_sha256": _sha256(prompt_bytes),
                 "staged_prompt_byte_length": len(prompt_bytes)}
    bindings = {
        "prompt_sha256": _sha256(prompt_bytes), "prompt_bytes": len(prompt_bytes),
        "response_schema_sha256": _sha256(schema_bytes), "response_schema_bytes": len(schema_bytes),
        "batch_number": batch, "attempt_number": attempt, "model": route["model"],
        "reasoning_effort": route["reasoning_effort"], "timeout_seconds": route["timeout_seconds"],
        "execution_contract": json.loads(_canonical(dict(execution)).decode("utf-8")),
        "run": dict(context["run"]), "transport": dict(context["transport"]),
        "question_ids": context["batch"].get("question_ids"),
    }
    return prompt, dict(schema), Path(output_dir), batch, attempt, bindings


def bind_grok_broker_transport(
    *,
    broker: Any,
    route: Mapping[str, Any],
    before_contact: Callable[[Mapping[str, Any]], None],
    runtime_check: Callable[[], None],
) -> Callable[[Mapping[str, Any]], tuple[str, dict[str, Any]]]:
    """Bind a verified Broker and immutable Grok route into one runner callback.

    The caller, not this adapter, proves Broker identity, route authority, source
    provenance, and runtime eligibility.  This callback never falls back to a CLI
    or another provider.  A callable argument alone is never accepted as proof of
    provider contact, code identity, or route authorization.
    """
    frozen_route, route_sha256 = _route_freeze(route)
    source_path = Path(__file__).resolve()
    source_bytes = source_path.read_bytes()
    source_sha256 = _sha256(source_bytes)
    if not callable(before_contact) or not callable(runtime_check):
        raise HBQError("Grok broker transport requires caller admission and runtime checks")
    method = getattr(broker, "run_grok_native_request", None)
    read_envelope = getattr(broker, "read_grok_native_envelope", None)
    if not callable(method) or not callable(read_envelope):
        raise HBQError("Grok broker transport requires native request and envelope methods")

    def transport(context: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        if not isinstance(context, Mapping):
            raise HBQError("Grok broker transport context must be a mapping")
        prompt, schema, output_dir, batch, attempt, bindings = _context_bindings(context, frozen_route)
        if (context["transport"].get("protocol") != "injected_grok_attempt_v1"
                or context["transport"].get("declared_sha256") != source_sha256
                or source_path.read_bytes() != source_bytes):
            raise HBQError("Grok broker adapter source binding drifted")
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

        def persist_outcome(value: Mapping[str, Any]) -> Path:
            path = root / "outcome.json"
            _write_new(path, _canonical(dict(value)))
            return path

        try:
            runtime_check()

            def hook() -> None:
                runtime_check()
                if source_path.read_bytes() != source_bytes:
                    raise HBQError("Grok broker adapter source changed before contact")
                before_contact(copy.deepcopy(frozen_context))
                runtime_check()
                if source_path.read_bytes() != source_bytes:
                    raise HBQError("Grok broker adapter source changed during admission")

            outcome = method(
                frozen_route["name"], request, output_schema=schema, nonvisual_max_turns=1,
                session_id=session_id, before_contact=hook, expected_route_sha256=route_sha256,
            )
            if not isinstance(outcome, Mapping) or set(outcome) != {"state", "result", "failure"}:
                raise HBQError("Grok broker returned a malformed outcome")
            outcome_path = persist_outcome(outcome)
            if outcome["state"] != "completed" or outcome["failure"] is not None or not isinstance(outcome["result"], Mapping):
                raise HBQError("Grok broker request did not complete")
            result = dict(outcome["result"])
            required = {"schema_version", "request_hash", "output", "output_hash", "runtime", "native_envelope_artifact"}
            if set(result) != required or result["schema_version"] != 2 or result["request_hash"] != _sha256(request_bytes) or result["output_hash"] != _sha256(_canonical(result["output"])):
                raise HBQError("Grok broker result binding drifted")
            runtime = result["runtime"]
            descriptor = result["native_envelope_artifact"]
            if not isinstance(runtime, Mapping) or not isinstance(descriptor, Mapping):
                raise HBQError("Grok broker runtime or envelope descriptor is malformed")
            envelope_bytes = read_envelope(dict(descriptor))
            envelope_path = root / "native-envelope.json"
            _write_new(envelope_path, envelope_bytes)
            envelope = json.loads(envelope_bytes.decode("utf-8"))
            if (set(descriptor) != {"schema_version", "sha256", "byte_length"} or descriptor.get("schema_version") != 1
                    or descriptor.get("sha256") != _sha256(envelope_bytes) or descriptor.get("byte_length") != len(envelope_bytes)
                    or not isinstance(envelope, Mapping) or envelope.get("structuredOutput") != result["output"]
                    or envelope.get("sessionId") != session_id or not isinstance(envelope.get("requestId"), str) or not envelope["requestId"]
                    or runtime.get("session_id_hash") != _sha256(session_id.encode("utf-8"))
                    or runtime.get("request_id_hash") != _sha256(envelope["requestId"].encode("utf-8"))
                    or runtime.get("envelope_hash") != _sha256(envelope_bytes)
                    or runtime.get("requested_model") != frozen_route["model"]
                    or runtime.get("requested_reasoning_effort") != frozen_route["reasoning_effort"]
                    or runtime.get("execution_contract") != bindings["execution_contract"]):
                raise HBQError("Grok broker result identity or execution contract drifted")
            execution = runtime["execution_contract"]
            if not isinstance(execution, Mapping) or execution.get("tools") != "none" or execution.get("max_turns") != 1:
                raise HBQError("Grok broker result is not tool-free one-turn execution")
            runtime_check()
            if source_path.read_bytes() != source_bytes:
                raise HBQError("Grok broker adapter source changed after contact")
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
                "reasoning_attested": runtime.get("reasoning_attested") is True,
                "tool_free": True,
                "provider_artifacts": artifacts,
            }
            return json.dumps(result["output"], ensure_ascii=False), metadata
        except Exception:
            if not (root / "outcome.json").exists():
                persist_outcome({"state": "adapter_error", "failure": {"code": "adapter_error"}})
            failure_receipt = {
                "schema_version": 1, "status": "not_completed",
                "source_sha256": source_sha256, "route_sha256": route_sha256,
                "request_sha256": _sha256(request_bytes), "context_sha256": _sha256(context_bytes),
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
