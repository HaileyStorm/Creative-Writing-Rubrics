from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/recovery.py"
BROKER_TEST = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\test_grok_adapter.py")


def load():
    spec = importlib.util.spec_from_file_location("wpb_native_recovery", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw(value))


def rows(count: int = 129) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    values = {
        f"cell-{number:04d}": {
            "cell_id": f"cell-{number:04d}",
            "payload_sha256": hashlib.sha256(f"payload-{number}".encode()).hexdigest(),
        }
        for number in range(count)
    }
    payloads = {cell: f"payload-{number}".encode() for number, cell in enumerate(values)}
    return {"rows": tuple(values.values()), "payloads": payloads, "schedule_sha256": "a" * 64, "core": SimpleNamespace(_outcome=lambda *_args: None)}, values


def plan(value, root: Path, cells: list[dict[str, object]]) -> str:
    schema_path = root / "frozen-schema.json"
    schema_raw = value.canonical({"type": "object"})
    schema_path.write_bytes(schema_raw)
    record = {
        "format_version": 1,
        "kind": "wpb_native_recovery_plan",
        "study_id": value.STUDY_ID,
        "authorization": {"record_sha256": "b" * 64},
        "origin": {"root": str(root / "origin"), "reserved_identity_hashes": []},
        "freeze_root": str(root / "freeze"),
        "response_schema": {"path": str(schema_path), "sha256": value.sha256(schema_raw)},
        "schedule_sha256": "a" * 64,
        "cells": cells,
    }
    content = value.canonical(record)
    (root / value.PLAN_NAME).write_bytes(content)
    for cell in cells:
        value._write_new(root / "cells" / str(cell["cell_id"]) / "prepared.json", cell)
    return value.sha256(content)


def fake_legacy():
    return SimpleNamespace(_valid_response=lambda _core, response: response)


def test_prepare_preserves_origin_and_creates_one_replacement_then_unstarted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    origin, authorization, recovery = tmp_path / "origin", tmp_path / "authorization.json", tmp_path / "recovery"
    origin.mkdir()
    original_payload = b"original evidence remains immutable"
    (origin / "original.bin").write_bytes(original_payload)
    completed = [{"cell_id": f"cell-{number:04d}", "state": "completed"} for number in range(89)]
    terminal = {"cell_id": value.ORIGINAL_TERMINAL_CELL, "state": "consumed_terminal", "claim_sha256": "c" * 64}
    write(origin / "batches/0001/settlement.json", {"cells": completed})
    settlement = raw({"cells": [terminal]})
    (origin / "batches/0009").mkdir(parents=True)
    (origin / "batches/0009/settlement.json").write_bytes(settlement)
    write(origin / "batches/0009/execution" / value.ORIGINAL_TERMINAL_CELL / "response-schema.json", {})
    write(origin / "grok-incomplete.json", {
        "successful_cells": 89, "ambiguous_terminal_cells": 1, "unstarted_cells": 39,
        "last_settlement_sha256": value.sha256(settlement),
    })
    authorization_value = {
        "decision": "owner_authorized_wpb_recovery", "original_successful_cells": 89,
        "original_terminal_cell": value.ORIGINAL_TERMINAL_CELL, "original_unstarted_cells": 39,
        "authorization_record_sha256": value.AUTHORIZATION_RECORD_SHA256,
        "automatic_retry_or_resend": False, "duplicate_logical_votes": False,
    }
    authorization.write_bytes(raw(authorization_value))
    resolution, known_rows = rows(128)
    known_rows[value.ORIGINAL_TERMINAL_CELL] = {"cell_id": value.ORIGINAL_TERMINAL_CELL, "payload_sha256": "d" * 64}
    monkeypatch.setattr(value, "LAST_SETTLEMENT_SHA256", value.sha256(settlement))
    monkeypatch.setattr(value, "ORIGINAL_CLAIM_SHA256", "c" * 64)
    monkeypatch.setattr(value, "_load_legacy", fake_legacy)
    monkeypatch.setattr(value, "_rows", lambda *_args: (resolution, known_rows))
    monkeypatch.setattr(value, "_origin_identity_keys", lambda *_args: set())
    monkeypatch.setattr(value, "_origin_ambiguous_identity_keys", lambda *_args: set())
    monkeypatch.setattr(value, "_origin_identity_components", lambda *_args: (set(), set()))
    result = value.prepare(
        origin_root=origin,
        recovery_root=recovery,
        freeze_root=tmp_path / "freeze",
        authorization_path=authorization,
        incomplete_status_path=origin / "grok-incomplete.json",
        expected_authorization_metadata_sha256=value.sha256(authorization.read_bytes()),
    )
    record = json.loads((recovery / value.PLAN_NAME).read_bytes())
    assert result["provider_calls_made"] == 0
    assert (origin / "original.bin").read_bytes() == original_payload
    assert record["origin"]["inventory"]["original.bin"] == value.sha256(original_payload)
    assert record["cells"][0]["cell_id"] == value.ORIGINAL_TERMINAL_CELL
    assert record["cells"][0]["kind"] == "single_replacement"
    assert len(record["cells"]) == 40
    assert {item["kind"] for item in record["cells"][1:]} == {"unstarted"}


def test_admit_requires_v4_attestation_and_refuses_identity_overlap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    cell = "cell-0001"
    payload = b"payload"
    cell_record = {"cell_id": cell, "kind": "single_replacement", "payload_sha256": value.sha256(payload)}
    plan_hash = plan(value, tmp_path, [cell_record])
    resolution = {"rows": (), "payloads": {cell: payload}, "schedule_sha256": "a" * 64, "core": SimpleNamespace(_outcome=lambda *_args: None)}
    monkeypatch.setattr(value, "_load_legacy", fake_legacy)
    monkeypatch.setattr(value, "_rows", lambda *_args: (resolution, {cell: cell_record}))
    monkeypatch.setattr(value, "_payload_for", lambda *_args: payload)
    cell_root = tmp_path / "cells" / cell
    session_id, request_id = "session-1", "request-1"
    answer = {"answer": "accepted by fake legacy core"}
    envelope = {"structuredOutput": answer, "sessionId": session_id, "requestId": request_id, "stopReason": "end_turn", "num_turns": 1,
                "text": json.dumps(answer, sort_keys=True, separators=(",", ":")), "modelUsage": {"grok-4.6-build": {"costUSD": 0.0}}}
    envelope_raw = raw(envelope)
    schema = {"type": "object"}
    schema_raw = value.canonical(schema)
    broker_path, runtime_path, helper_path, queue_root = tmp_path / "broker.py", tmp_path / "runtime.py", tmp_path / "helper.py", tmp_path / "queue"
    for path in (broker_path, runtime_path, helper_path):
        path.write_text("# canonical-shaped test pin\n", encoding="utf-8")
    queue_root.mkdir()
    route = {"name": "test-route"}
    attempt = {"session_id": session_id, "session_id_hash": value.sha256(session_id.encode()), "schema_sha256": value.sha256(schema_raw),
               "route_sha256": value.sha256(route), "broker_path": str(broker_path), "broker_sha256": value.sha256(broker_path.read_bytes()),
               "runtime_source_path": str(runtime_path), "runtime_source_sha256": value.sha256(runtime_path.read_bytes()),
               "helper_source_path": str(helper_path), "helper_source_sha256": value.sha256(helper_path.read_bytes()), "queue_root": str(queue_root)}
    write(cell_root / "attempt.json", attempt)
    value._write_new(cell_root / "route.json", route)
    value._write_new(cell_root / "request.json", {"prompt": payload.decode()})
    value._write_new(cell_root / "response-schema.json", schema)
    result = {
        "schema_version": 2,
        "request_hash": value.sha256(value.canonical({"prompt": payload.decode()})),
        "output": answer,
        "output_hash": value.sha256(answer),
        "runtime": {
            "adapter_version": 4,
            "execution_policy": "bounded_nonvisual_deny_wins_attested",
            "tool_policy_attestation_hash": "e" * 64,
            "execution_contract": {"tools": "deny_wins_none_attested", "max_turns": 1, "output_schema_hash": None, "staged_prompt_sha256": value.sha256(payload), "staged_prompt_byte_length": len(payload)},
            "session_id_hash": value.sha256(session_id.encode()), "request_id_hash": value.sha256(request_id.encode()),
            "envelope_hash": value.sha256(envelope_raw), "reasoning_attested": False,
        },
        "native_envelope_artifact": {"schema_version": 1, "sha256": value.sha256(envelope_raw), "byte_length": len(envelope_raw)},
    }
    result["runtime"]["execution_contract"]["output_schema_hash"] = attempt["schema_sha256"]
    class Broker:
        def __init__(self, _root):
            pass

        def read_grok_native_envelope(self, _descriptor):
            return envelope_raw

        def _parse_grok_exec_envelope(self, raw_envelope, actual_route, actual_request, *, expected_session_id):
            projection = json.loads(raw_envelope)
            assert projection["control"] == {"version": 1, "state": "completed"} and projection["result"] == json.loads((cell_root / "result.json").read_bytes())
            assert actual_route["output_schema"] == schema and actual_route["nonvisual_max_turns"] == 1 and actual_request == {"prompt": payload.decode()}
            assert expected_session_id == session_id and json.loads(envelope_raw)["stopReason"] == "end_turn"
            return SimpleNamespace(state="completed", result=json.loads((cell_root / "result.json").read_bytes()))

    monkeypatch.setattr(value, "QUEUE_ROOT", queue_root)
    monkeypatch.setattr(value, "_load_broker", lambda _path: (SimpleNamespace(), Broker))
    malformed = {**result, "runtime": {key: item for key, item in result["runtime"].items() if key != "tool_policy_attestation_hash"}}
    write(cell_root / "outcome.json", {"state": "completed", "result": malformed, "failure": None})
    write(cell_root / "result.json", malformed)
    (cell_root / "native-envelope.json").write_bytes(envelope_raw)
    with pytest.raises(ValueError, match="adapter-v4"):
        value.admit(recovery_root=tmp_path, expected_plan_sha256=plan_hash, cell_id=cell)
    write(cell_root / "outcome.json", {"state": "completed", "result": result, "failure": None})
    write(cell_root / "result.json", result)
    (cell_root / "native-envelope.json").write_bytes(envelope_raw)
    admitted = value.admit(recovery_root=tmp_path, expected_plan_sha256=plan_hash, cell_id=cell)
    assert admitted["status"] == "admitted" and admitted["provider_calls_made"] == 0

    second = tmp_path / "second"
    second.mkdir()
    second_hash = plan(value, second, [cell_record])
    second_record, _ = value._json(second / value.PLAN_NAME, "plan")
    second_record["origin"]["reserved_identity_hashes"] = [value.sha256({"request_id": request_id, "session_id": session_id})]
    (second / value.PLAN_NAME).write_bytes(value.canonical(second_record))
    second_root = second / "cells" / cell
    for name in ("attempt.json", "outcome.json", "result.json", "native-envelope.json", "route.json", "request.json", "response-schema.json"):
        source = cell_root / name
        target = second_root / name
        target.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="overlaps original"):
        value.admit(recovery_root=second, expected_plan_sha256=value.sha256((second / value.PLAN_NAME).read_bytes()), cell_id=cell)
    assert second_hash != value.sha256((second / value.PLAN_NAME).read_bytes())
    admission_path = cell_root / "admission.json"
    admission = json.loads(admission_path.read_bytes())
    admission["response"] = {"answer": "different score projection"}
    admission_path.write_bytes(value.canonical(admission))
    with pytest.raises(ValueError, match="differs from the canonical result"):
        value._verify_admission(value._read_plan(tmp_path, plan_hash), tmp_path, cell_record)


def test_dispatch_stops_terminal_outcome_and_never_resends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    resolution, known_rows = rows()
    cell = "cell-0001"
    cells = [{"cell_id": cell, "kind": "single_replacement", "payload_sha256": known_rows[cell]["payload_sha256"]}]
    cells.extend({"cell_id": f"recovery-{number:02d}", "kind": "unstarted", "payload_sha256": "f" * 64} for number in range(39))
    plan_hash = plan(value, tmp_path, cells)
    broker_path, runtime_path, helper_path, queue_root = tmp_path / "broker.py", tmp_path / "runtime.py", tmp_path / "helper.py", tmp_path / "queue"
    broker_path.write_text("# synthetic broker source\n", encoding="utf-8")
    runtime_path.write_text("# synthetic v4 runtime source\n", encoding="utf-8")
    helper_path.write_text("# synthetic helper source\n", encoding="utf-8")
    queue_root.mkdir()
    route = {"name": "synthetic-grok"}
    review = {
        "decision": "approved_wpb_native_recovery_dispatch", "recovery_plan_sha256": plan_hash,
        "authorization_record_sha256": "b" * 64,
        "broker": {"path": str(broker_path.resolve()), "sha256": value.sha256(broker_path.read_bytes())},
        "runtime": {"path": str(runtime_path.resolve()), "sha256": value.sha256(runtime_path.read_bytes()), "adapter_version": 4},
        "helper": {"path": str(helper_path.resolve()), "sha256": value.sha256(helper_path.read_bytes())},
        "route_sha256": value.sha256(route),
    }
    review_path = tmp_path / "review.json"
    review_path.write_bytes(value.canonical(review))
    monkeypatch.setattr(value, "_load_legacy", fake_legacy)
    monkeypatch.setattr(value, "_rows", lambda *_args: (resolution, known_rows))
    monkeypatch.setattr(value, "QUEUE_ROOT", queue_root)

    class Broker:
        def __init__(self, _root):
            pass

        def run_grok_native_request(self, *_args, **_kwargs):
            return {"state": "definitely_not_contacted", "result": None, "failure": {"code": "blocked"}}

        def read_grok_native_envelope(self, _descriptor):
            raise AssertionError("completed envelope was not expected")

    monkeypatch.setattr(value, "_load_broker", lambda _path: (SimpleNamespace(), Broker))
    result = value.dispatch(
        recovery_root=tmp_path, expected_plan_sha256=plan_hash, cell_id=cell, route=route,
        reviewed_authorization_path=review_path, expected_review_sha256=value.sha256(review_path.read_bytes()),
        broker_path=broker_path, runtime_source_path=runtime_path, helper_source_path=helper_path, queue_root=queue_root,
    )
    assert result["status"] == "terminal_no_resend"
    with pytest.raises(ValueError, match="campaign stopped"):
        value.dispatch(
            recovery_root=tmp_path, expected_plan_sha256=plan_hash, cell_id="recovery-00", route=route,
            reviewed_authorization_path=review_path, expected_review_sha256=value.sha256(review_path.read_bytes()),
            broker_path=broker_path, runtime_source_path=runtime_path, helper_source_path=helper_path, queue_root=queue_root,
        )


def test_report_stays_closed_until_every_recovery_cell_is_admitted(tmp_path: Path) -> None:
    value = load()
    cells = [{"cell_id": f"cell-{number:04d}", "kind": "unstarted", "payload_sha256": "a" * 64} for number in range(40)]
    plan_hash = plan(value, tmp_path, cells)
    report = value.report(recovery_root=tmp_path, expected_plan_sha256=plan_hash, profile={"core": 1.0})
    assert report == {
        "status": "closed_incomplete", "authority": "development_screening_only", "original_successful_cells": 89,
        "recovered_native_cells": 0, "required_recovered_native_cells": 40, "metrics": None,
    }


def test_report_rejects_summary_when_its_raw_evidence_is_missing(tmp_path: Path) -> None:
    value = load()
    cells = [{"cell_id": f"cell-{number:04d}", "kind": "unstarted", "payload_sha256": "a" * 64} for number in range(40)]
    plan_hash = plan(value, tmp_path, cells)
    value._write_new(tmp_path / "cells/cell-0000/admission.json", {
        "cell_id": "cell-0000", "plan_sha256": plan_hash, "payload_sha256": "a" * 64,
    })
    with pytest.raises(ValueError, match="raw evidence is missing"):
        value.report(recovery_root=tmp_path, expected_plan_sha256=plan_hash, profile={"core": 1.0})


def test_broker_and_frozen_analyzer_serializers_have_explicit_boundaries() -> None:
    value = load()
    legacy = value._load_legacy()
    core = legacy._core()
    response = {"A": {"score": 1}}
    assert value.canonical(response) == b'{"A":{"score":1}}'
    assert core.canonical(response) == b'{"A":{"score":1}}\n'
    assert value.sha256(response) != core.sha256(core.canonical(response))


def test_canonical_broker_accepts_a_derived_control_projection_provider_free() -> None:
    tools_root = BROKER_TEST.parent.parent
    prior_modules = set(sys.modules)
    sys.path.insert(0, str(tools_root))
    case = None
    try:
        spec = importlib.util.spec_from_file_location("wpb_canonical_grok_fixture", BROKER_TEST)
        assert spec and spec.loader
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        case = fixture.GrokAdapterTests("runTest")
        case.setUp()
        try:
            schema = json.loads(fixture.WPB_SCHEMA_PATH.read_bytes())
            route = case.route("wpb_schema", output_schema=schema)
            request = {"prompt": "Provider-free canonical recovery parser fixture."}
            outcome = case.broker._run_grok_exec(route, request)
            assert outcome.state == "completed" and isinstance(outcome.result, dict)
            native = case.broker.read_grok_native_envelope(outcome.result["native_envelope_artifact"])
            session_id = json.loads(native)["sessionId"]
            projection = fixture._canonical({"control": {"version": 1, "state": "completed"}, "result": outcome.result})
            replayed = case.broker._parse_grok_exec_envelope(projection, route, request, expected_session_id=session_id)
            assert replayed.state == "completed" and replayed.result == outcome.result
        finally:
            case.tearDown()
    finally:
        if case is not None:
            case.doCleanups()
        sys.path.remove(str(tools_root))
        for name in set(sys.modules) - prior_modules:
            sys.modules.pop(name, None)


def test_helper_admits_a_real_canonical_broker_fixture_provider_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    tools_root = BROKER_TEST.parent.parent
    prior_modules = set(sys.modules)
    sys.path.insert(0, str(tools_root))
    case = None
    try:
        spec = importlib.util.spec_from_file_location("wpb_helper_canonical_grok_fixture", BROKER_TEST)
        assert spec and spec.loader
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        case = fixture.GrokAdapterTests("runTest")
        case.setUp()
        try:
            synthetic = fixture.FAKE.replace('"form": "not_assessable"', '"form": "assessed"')
            assert synthetic != fixture.FAKE and synthetic.count('"form": "assessed"') == fixture.FAKE.count('"form": "assessed"') + 1
            case.fake.write_text(synthetic, encoding="utf-8")
            legacy = value._load_legacy()
            freeze = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
            resolution, known_rows = value._rows(legacy, freeze)
            cell_id = next(iter(known_rows))
            payload = resolution["payloads"][cell_id]
            schema = json.loads(fixture.WPB_SCHEMA_PATH.read_bytes())
            schema_raw = value.canonical(schema)
            route = case.route("wpb_schema", output_schema=schema)
            outcome = case.broker._run_grok_exec(route, {"prompt": payload.decode("utf-8")})
            assert outcome.state == "completed" and isinstance(outcome.result, dict)
            result = outcome.result
            envelope = case.broker.read_grok_native_envelope(result["native_envelope_artifact"])
            root = tmp_path / "recovery"
            root.mkdir()
            schema_path = root / "frozen-schema.json"
            schema_path.write_bytes(schema_raw)
            record = {
                "format_version": 1, "kind": "wpb_native_recovery_plan", "study_id": value.STUDY_ID,
                "authorization": {"record_sha256": "a" * 64}, "origin": {"root": str(tmp_path / "origin"), "reserved_identity_hashes": []},
                "freeze_root": str(freeze), "schedule_sha256": resolution["schedule_sha256"],
                "response_schema": {"path": str(schema_path), "sha256": value.sha256(schema_raw)},
                "cells": [{"cell_id": cell_id, "kind": "single_replacement", "payload_sha256": known_rows[cell_id]["payload_sha256"]}],
            }
            plan_raw = value.canonical(record)
            (root / value.PLAN_NAME).write_bytes(plan_raw)
            cell_root = root / "cells" / cell_id
            value._write_new(cell_root / "prepared.json", record["cells"][0])
            broker_path = BROKER_TEST.parent / "broker.py"
            runtime_path = BROKER_TEST.parent / "adapters" / "grok_exec.py"
            attempt = {
                "cell_id": cell_id, "plan_sha256": value.sha256(plan_raw), "payload_sha256": value.sha256(payload),
                "schema_sha256": value.sha256(schema_raw), "route_sha256": value.sha256(route), "broker_path": str(broker_path),
                "broker_sha256": value.sha256(broker_path.read_bytes()), "runtime_source_path": str(runtime_path),
                "runtime_source_sha256": value.sha256(runtime_path.read_bytes()), "helper_source_path": str(SOURCE),
                "helper_source_sha256": value.sha256(SOURCE.read_bytes()), "queue_root": str(case.broker.root),
                "session_id": json.loads(envelope)["sessionId"], "session_id_hash": result["runtime"]["session_id_hash"],
                "requested_model": route["model"], "requested_reasoning_effort": route["reasoning_effort"],
            }
            value._write_new(cell_root / "attempt.json", attempt)
            value._write_new(cell_root / "route.json", route)
            value._write_new(cell_root / "request.json", {"prompt": payload.decode("utf-8")})
            value._write_new(cell_root / "response-schema.json", schema)
            value._write_new(cell_root / "outcome.json", {"state": "completed", "result": result, "failure": None})
            value._write_new(cell_root / "result.json", result)
            (cell_root / "native-envelope.json").write_bytes(envelope)
            monkeypatch.setattr(value, "QUEUE_ROOT", case.broker.root)
            admitted = value.admit(recovery_root=root, expected_plan_sha256=value.sha256(plan_raw), cell_id=cell_id)
            assert admitted["status"] == "admitted"
            route_path = cell_root / "route.json"
            route_path.write_bytes(value.canonical({**route, "name": "tampered"}))
            with pytest.raises(ValueError, match="commitment drifted"):
                value._verify_admission(value._read_plan(root, value.sha256(plan_raw)), root, record["cells"][0])
        finally:
            case.tearDown()
    finally:
        if case is not None:
            case.doCleanups()
        sys.path.remove(str(tools_root))
        for name in set(sys.modules) - prior_modules:
            sys.modules.pop(name, None)
