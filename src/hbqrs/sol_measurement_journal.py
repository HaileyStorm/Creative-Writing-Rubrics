"""Exclusive per-request Sol evidence; campaign admission belongs to the caller."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from . import sol_broker_transport as transport
from .core import HBQError, _normalize_verdict_records


def _write(path: Path, raw: bytes) -> None:
    with path.open("xb") as output:
        output.write(raw)
        output.flush()


def _validate_request(request: Mapping[str, Any], prompt: bytes, schema: bytes) -> dict[str, Any]:
    value = transport._strict_json(transport._canonical(dict(request)), "request journal binding")
    if set(value) != {
        "plan_sha256", "ordinal", "pass_id", "logical_sample_id", "question_ids",
        "prompt_sha256", "prompt_bytes", "schema_sha256", "schema_bytes",
        "execution_source_sha256", "authorization_sha256", "route_sha256",
    }:
        raise HBQError("Sol journal request fields differ")
    for key in ("plan_sha256", "prompt_sha256", "schema_sha256", "execution_source_sha256",
                "authorization_sha256", "route_sha256"):
        if not isinstance(value[key], str) or transport._SHA256.fullmatch(value[key]) is None:
            raise HBQError("Sol journal commitment differs")
    ids = value["question_ids"]
    if (type(value["ordinal"]) is not int or value["ordinal"] < 1
            or any(not isinstance(value[key], str) or not value[key] for key in ("pass_id", "logical_sample_id"))
            or not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids)
            or len(set(ids)) != len(ids)):
        raise HBQError("Sol journal request identity differs")
    for name, raw in (("prompt", prompt), ("schema", schema)):
        if (not isinstance(raw, bytes) or value[f"{name}_sha256"] != transport._sha256(raw)
                or type(value[f"{name}_bytes"]) is not int or value[f"{name}_bytes"] != len(raw)):
            raise HBQError("Sol journal payload binding differs")
    prompt.decode("utf-8")
    Draft202012Validator.check_schema(transport._strict_json(schema, "planned schema"))
    return value


def _output(final: bytes, schema: bytes, question_ids: list[str]) -> list[dict[str, Any]]:
    value = transport._strict_json(final, "journal final message")
    Draft202012Validator(transport._strict_json(schema, "journal schema")).validate(value)
    rows = _normalize_verdict_records(value)
    if [row.get("question_id") for row in rows] != question_ids:
        raise HBQError("Sol journal output question order or coverage differs")
    return rows


def run_request(
    destination: Path, *, request: Mapping[str, Any], prompt_utf8: bytes,
    planned_schema_utf8: bytes, disclosure: Mapping[str, Any], route_snapshot: Mapping[str, Any],
    broker: Any, event_replayer: Callable[[bytes], Mapping[str, Any]],
    precontact_gate: Callable[[], None],
) -> dict[str, Any]:
    """Run once after caller admission; every created directory consumes this attempt.

    The mandatory gate owns current source, reviewer-window and campaign checks.
    It runs before reservation and again inside the transport's contact boundary.
    A receipt is evidence only; this function cannot approve a study or a route.
    """
    if not callable(precontact_gate) or not callable(event_replayer):
        raise HBQError("Sol journal requires admission and native replay gates")
    binding = _validate_request(request, prompt_utf8, planned_schema_utf8)
    frozen_disclosure = transport._canonical(dict(disclosure))
    frozen_route = transport._canonical(dict(route_snapshot))
    if transport._sha256(frozen_route) != binding["route_sha256"]:
        raise HBQError("Sol journal route differs")
    precontact_gate()
    destination = Path(destination)
    destination.mkdir()  # Existing partial attempts must never become retries.
    start = {"schema_version": 1, "request": binding,
             "disclosure_sha256": transport._sha256(frozen_disclosure)}
    start_raw = transport._canonical(start)
    _write(destination / "start.json", start_raw)
    for name, raw in (("prompt.txt", prompt_utf8), ("schema.json", planned_schema_utf8),
                      ("disclosure.json", frozen_disclosure), ("route.json", frozen_route)):
        _write(destination / name, raw)
    receipt = None
    projection = None
    state, failure = "ambiguous", "request_execution_failed"
    try:
        receipt = transport.run_sol_native_batch(
            broker, prompt_utf8=prompt_utf8, planned_schema_utf8=planned_schema_utf8,
            disclosure=transport._strict_json(frozen_disclosure, "disclosure"),
            route_snapshot=transport._strict_json(frozen_route, "route"),
            expected_route_sha256=binding["route_sha256"], event_replayer=event_replayer,
            precontact_hook=precontact_gate,
        )
        state, failure = receipt.state, receipt.failure_code
        if receipt.state == "completed":
            _output(receipt.final_message_bytes, planned_schema_utf8, binding["question_ids"])
            projection = dict(event_replayer(receipt.events_bytes))
    except Exception:  # noqa: BLE001 - A started attempt is consumed even when diagnostics fail.
        state, failure = "ambiguous", "request_execution_or_validation_failed"
    retained = {}
    if receipt is not None:
        retained = asdict(receipt)
        for field, name in (("events_bytes", "events.jsonl"), ("final_message_bytes", "final.json")):
            raw = retained.pop(field)
            if raw is not None:
                _write(destination / name, raw)
        retained.pop("parsed_output")
    terminal = {"schema_version": 1, "evidence_class": "sol_request_journal",
                "start_sha256": transport._sha256(start_raw), "state": state,
                "failure_code": failure, "receipt": retained, "event_projection": projection}
    # Failure here leaves an unresolved start. The caller must reconcile, never resend.
    raw = transport._canonical(terminal)
    _write(destination / "terminal.json", raw)
    return {"state": state, "terminal_sha256": transport._sha256(raw)}


def replay_request(
    destination: Path, *, expected_terminal_sha256: str, expected_request: Mapping[str, Any],
    event_replayer: Callable[[bytes], Mapping[str, Any]],
) -> dict[str, Any]:
    """Recompute one externally anchored journal without creating provider authority."""
    destination = Path(destination)
    terminal_raw = (destination / "terminal.json").read_bytes()
    if transport._sha256(terminal_raw) != expected_terminal_sha256:
        raise HBQError("Sol journal terminal commitment differs")
    terminal = transport._strict_json(terminal_raw, "terminal journal")
    start_raw = (destination / "start.json").read_bytes()
    if terminal["start_sha256"] != transport._sha256(start_raw):
        raise HBQError("Sol journal start commitment differs")
    start = transport._strict_json(start_raw, "start journal")
    prompt, schema = (destination / "prompt.txt").read_bytes(), (destination / "schema.json").read_bytes()
    binding = _validate_request(expected_request, prompt, schema)
    if start != {"schema_version": 1, "request": binding,
                 "disclosure_sha256": transport._sha256((destination / "disclosure.json").read_bytes())}:
        raise HBQError("Sol journal request commitment differs")
    if transport._sha256((destination / "route.json").read_bytes()) != binding["route_sha256"]:
        raise HBQError("Sol journal retained route differs")
    receipt = terminal["receipt"]
    if terminal["state"] not in {"completed", "ambiguous", "definitely_not_contacted"}:
        raise HBQError("Sol journal terminal state differs")
    if receipt.get("state") != "completed":
        if terminal["state"] == "completed" or any((destination / name).exists() for name in ("final.json", "events.jsonl")):
            raise HBQError("Sol journal incomplete receipt differs")
        if receipt:
            expected = asdict(transport._receipt(
                receipt["state"], route_sha256=binding["route_sha256"], prompt=prompt,
                planned_schema=schema, canonical_schema=transport._canonical(transport._strict_json(schema, "schema")),
                disclosure=(destination / "disclosure.json").read_bytes(), failure_code=receipt["failure_code"],
            ))
            for key in ("events_bytes", "final_message_bytes", "parsed_output"):
                expected.pop(key)
            if receipt != expected or receipt["state"] not in {"ambiguous", "definitely_not_contacted"}:
                raise HBQError("Sol journal incomplete receipt binding differs")
        return {"state": terminal["state"], "admitted_rows": [], "full_pass_admitted": False}
    final, events = (destination / "final.json").read_bytes(), (destination / "events.jsonl").read_bytes()
    canonical_schema = transport._canonical(transport._strict_json(schema, "schema"))
    disclosure = (destination / "disclosure.json").read_bytes()
    for field, raw in (("schema_artifact", canonical_schema), ("disclosure_artifact", disclosure),
                       ("events_artifact", events), ("final_message_artifact", final)):
        if receipt[field] != {"sha256": transport._sha256(raw), "byte_length": len(raw)}:
            raise HBQError("Sol journal artifact descriptor differs")
    if (receipt["failure_code"] is not None
            or (terminal["state"] == "completed" and terminal["failure_code"] is not None)
            or receipt["raw_final_message_sha256"] != transport._sha256(final)
            or receipt["raw_final_message_byte_length"] != len(final)
            or receipt["events_sha256"] != transport._sha256(events)
            or receipt["events_byte_length"] != len(events)
            or receipt["output_sha256"] != transport._sha256(transport._canonical(transport._strict_json(final, "final")))
            or receipt["request_sha256"] != transport._sha256(transport._canonical({"prompt": prompt.decode("utf-8")}))
            or receipt["route_sha256"] != binding["route_sha256"]
            or receipt["prompt_sha256"] != binding["prompt_sha256"]
            or receipt["prompt_byte_length"] != len(prompt)
            or receipt["planned_schema_sha256"] != binding["schema_sha256"]
            or receipt["planned_schema_byte_length"] != len(schema)
            or receipt["canonical_schema_sha256"] != transport._sha256(canonical_schema)
            or receipt["canonical_schema_byte_length"] != len(canonical_schema)
            or receipt["disclosure_sha256"] != start["disclosure_sha256"]
            or receipt["disclosure_byte_length"] != len(disclosure)
            or receipt["requested_model"] != "gpt-5.6-sol"
            or receipt["requested_reasoning_effort"] != "high"
            or receipt["identity_evidence"] != "requested_only"
            or receipt["provider_contact_cardinality_evidence"] != "unattested"
            or any(receipt[key] is not True for key in ("one_provider_bearing_cli_invocation_observed",
                                                       "one_turn_observed", "zero_tool_activity_observed"))):
        raise HBQError("Sol journal native receipt differs")
    projection = dict(event_replayer(events))
    if ((terminal["event_projection"] is not None and projection != terminal["event_projection"])
            or (terminal["state"] == "completed" and terminal["event_projection"] is None)
            or set(projection) != {"schema_version", "thread_id", "usage"}
            or not isinstance(projection["thread_id"], str) or not projection["thread_id"]):
        raise HBQError("Sol journal event replay differs")
    if terminal["state"] != "completed":
        return {"state": terminal["state"], "admitted_rows": [], "full_pass_admitted": False}
    return {"state": "completed", "admitted_rows": _output(final, schema, binding["question_ids"]),
            "thread_id": projection["thread_id"], "identity_evidence": "requested_only",
            "provider_contact_cardinality_evidence": "unattested", "full_pass_admitted": False}
