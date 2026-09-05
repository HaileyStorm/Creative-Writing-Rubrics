from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-wpb-compact-family-native-v1"
EXECUTOR = PACKAGE / "executor.py"
CORE = ROOT / "evaluation-results" / "hbq-human-alignment-wpb-compact-family-v1" / "study.py"
V15_GROK_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v15_rank_discrimination_v1.py"
V12_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v12_development_sol_exec_v1.py"
NATIVE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
GROK_ADAPTER_TEST = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\test_grok_adapter.py")
QUEUE_TOOLS_ROOT = GROK_ADAPTER_TEST.parents[1]
FREEZE = Path(r"C:\Users\Haile\Documents\cwr-wpb-pilot-source-freeze-20260904-r3")
ACK = "a" * 64
FAMILIES = ("core", "craft", "form")


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def executor() -> Any:
    return load(EXECUTOR, "wpb_compact_native_executor")


def core_sha256() -> str:
    return hashlib.sha256(CORE.read_bytes()).hexdigest()


def common(value: Any, root: Path, endpoint: str) -> dict[str, Any]:
    queue = root / f"{endpoint}-queue"
    queue.mkdir(parents=True)
    support = load(V12_TEST, f"wpb_{endpoint}_sol_route_support")
    route, _evidence = support.sol_route()
    def grok_broker_factory(queue_root: Path, broker_type: type[Any], _error_type: type[Exception]) -> Any:
        broker = broker_type(queue_root, grok_host_gate_path=root / "temporary-grok-host-gate.sqlite3")
        broker.init()
        broker.run_grok_native_contact = lambda _route, contact: {"state": "completed", "result": contact(), "failure": None}
        return broker

    arguments = {
        "endpoint": endpoint,
        "output_root": root / f"{endpoint}-output",
        "queue_root": queue,
        "freeze_root": FREEZE,
        "authorization_acknowledgement_sha256": ACK,
    }
    if endpoint == "sol":
        arguments["sol_broker_factory"] = lambda _root: support.Broker(route)
    else:
        route_support = load(V15_GROK_TEST, "wpb_grok_route_support")
        arguments["grok_route_provider"] = lambda queue_root: route_support._route_provider()(queue_root)
        arguments["grok_broker_factory"] = grok_broker_factory
    return arguments


def answer(value: Any) -> dict[str, Any]:
    side = {
        "scores": {family: 3 for family in FAMILIES},
        "coverage": {family: "assessed" for family in FAMILIES},
        "evidence": {family: "Fixture evidence." for family in FAMILIES},
    }
    return {"A": side, "B": side, "observed_winner": "TIE"}


def profile() -> dict[str, float]:
    return {family: 1.0 for family in FAMILIES}


def keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(keys(item) for item in value)) if value else set()
    return set()


class Contacts:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.active = 0
        self.maximum = 0
        self.failed = False
        self.failure_started = threading.Event()
        self.failure_observed = threading.Event()
        self.lock = threading.Lock()

    def enter(self, cell_id: str) -> None:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            self.calls.append(cell_id)

    def leave(self) -> None:
        with self.lock:
            self.active -= 1

    def fail_once(self) -> bool:
        with self.lock:
            if self.failed:
                return False
            self.failed = True
            return True


def native_envelope(structured: dict[str, Any], session_id: str, request_id: str) -> dict[str, Any]:
    return {
        "modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}},
        "num_turns": 1, "requestId": request_id, "sessionId": session_id, "stopReason": "end_turn", "structuredOutput": structured,
        "text": json.dumps(structured, ensure_ascii=False, sort_keys=True, separators=(",", ":")), "thought": "", "total_cost_usd": 0.0, "total_cost_usd_ticks": 0,
        "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4},
    }


def grok_runner(value: Any, rows: tuple[dict[str, Any], ...], contacts: Contacts, *, fail_after_contact: bool = False, start_gate: threading.Barrier | None = None, failure_cell: str | None = None, success_release: threading.Event | None = None):
    index = {str(row["cell_id"]): row for row in rows}

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route: dict[str, Any], before_contact):
        row = index[output_dir.name]
        contacts.enter(str(row["cell_id"]))
        try:
            if start_gate is not None:
                start_gate.wait(timeout=10)
            time.sleep(0.002)
            assert prompt == base64.b64decode(row["payload_base64"], validate=True)
            outbound = json.loads(prompt)
            assert json.loads(schema_path.read_bytes()) == outbound["response_schema"]
            assert not {"category", "source_model", "preferred_side", "chosen_score", "rejected_score", "target"} & set(outbound)
            structured = answer(value)
            envelope = native_envelope(structured, f"session-{output_dir.name}", f"request-{output_dir.name}")
            response = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            responses = output_dir / "responses"
            responses.mkdir()
            before_contact()
            (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
            (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
            if fail_after_contact and (str(row["cell_id"]) == failure_cell if failure_cell is not None else contacts.fail_once()):
                contacts.failure_started.set()
                raise RuntimeError("fixture post-contact failure")
            if success_release is not None:
                assert success_release.wait(timeout=10)
            proof = value._shared_result_path(output_dir)
            proof.parent.mkdir(exist_ok=True)
            proof.write_bytes(value.canonical(shared_result(value, prompt, json.loads(schema_path.read_bytes()), route, response)))
            return {
                "native_request_bytes": json.dumps({"prompt": prompt.decode("utf-8")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                "native_response_bytes": response,
                "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
                "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False},
            }
        finally:
            contacts.leave()

    return run


def shared_result(value: Any, prompt: bytes, schema: dict[str, Any], route: dict[str, Any], raw: bytes) -> dict[str, Any]:
    """Synthetic transport evidence for component tests; never provider proof."""
    compact = lambda obj: json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    envelope = json.loads(raw)
    output = envelope["structuredOutput"]
    runtime = {
        "adapter_version": 2, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build",
        "requested_reasoning_effort": "high", "reasoning_attested": False,
        "reasoning_attestation": "not_reported_by_grok_build_cli", "identity_evidence": "requested_only",
        "cli_version": route["grok_cli_version"], "session_id_hash": value.sha256(envelope["sessionId"].encode()),
        "request_id_hash": value.sha256(envelope["requestId"].encode()), "envelope_hash": value.sha256(raw),
        "command_identity": route["grok_command_identity"],
        "command_identity_hash": value.sha256(compact({"adapter_version": 2, "grok_command": route["grok_command"],
                                                        "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high"})),
        "subscription_receipt_hash": route["subscription_receipt_hash"], "execution_policy": "bounded_nonvisual_read_only",
        "usage_telemetry": {"status": "reported", "total_cost_usd": 0.0, "total_cost_usd_ticks": 0, "model_cost_usd": 0.0},
        "execution_contract": {"schema_version": 1, "output_schema_hash": value.sha256(compact(schema)),
                               "max_turns": 1, "tools": "none", "staged_prompt_sha256": value.sha256(prompt), "staged_prompt_byte_length": len(prompt)},
        "transport": {"schema_version": 1, "exit_code": 0, "stdout_byte_length": len(raw), "stderr_byte_length": 0},
        "nonvisual_max_turns": 1, "observed_turns": 1,
    }
    return {"schema_version": 2, "request_hash": value.sha256(compact({"prompt": prompt.decode("utf-8")})),
            "output": output, "output_hash": value.sha256(compact(output)), "runtime": runtime,
            "native_envelope_artifact": {"schema_version": 1, "sha256": value.sha256(raw), "byte_length": len(raw)}}


def sol_runner(value: Any, rows: tuple[dict[str, Any], ...], contacts: Contacts, *, fail_after_contact: bool = False, start_gate: threading.Barrier | None = None, failure_cell: str | None = None, success_release: threading.Event | None = None):
    index = {str(row["cell_id"]): row for row in rows}
    native = load(NATIVE, "wpb_native_sol_command")

    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        row = index[root.name]
        contacts.enter(str(row["cell_id"]))
        try:
            if start_gate is not None:
                start_gate.wait(timeout=10)
            time.sleep(0.002)
            final = json.dumps(answer(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            responses = root / "responses"
            responses.mkdir(exist_ok=True)
            kwargs["before_provider_attempt"]()
            events = b"".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n" for event in ({"type": "thread.started", "thread_id": f"fixture-thread-{row['cell_id']}"}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}}, {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}}))
            events_path = responses / "batch-0001.attempt-0001.events.jsonl"
            stderr_path = root / "raw-codex-stderr.bin"
            events_path.write_bytes(events)
            (responses / "batch-0001.attempt-0001.message.json").write_text(final, encoding="utf-8")
            stderr_path.write_bytes(b"")
            if fail_after_contact and (str(row["cell_id"]) == failure_cell if failure_cell is not None else contacts.fail_once()):
                contacts.failure_started.set()
                raise RuntimeError("fixture post-contact failure")
            if success_release is not None:
                assert success_release.wait(timeout=10)
            return final, {"command": native._expected_codex_command(kwargs["executable"], root), "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{row['cell_id']}"}, "provider_artifacts": {"codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": hashlib.sha256(events).hexdigest()}, "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}}}
        finally:
            contacts.leave()

    return invoke


def execute_args(args: dict[str, Any]) -> dict[str, Any]:
    return dict(args)


def prepare_args(args: dict[str, Any]) -> dict[str, Any]:
    return {name: item for name, item in args.items() if name != "grok_broker_factory"}


def broker_fixture(value: Any) -> tuple[Any, Any, dict[str, Any]]:
    if str(QUEUE_TOOLS_ROOT) not in sys.path:
        sys.path.insert(0, str(QUEUE_TOOLS_ROOT))
    support = load(GROK_ADAPTER_TEST, "wpb_grok_broker_fixture")
    case = support.GrokAdapterTests("runTest")
    case.setUp()
    case.broker, support.GrokNativeProviderError = value._grok_broker(
        case.root,
        lambda root, broker_type, _error_type: broker_type(root, grok_host_gate_path=case.grok_host_gate),
    )
    route = case.route()
    case.write_route(route)
    return case, support, route


@pytest.fixture(scope="module", params=("sol",))
def completed_native_material(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    endpoint = str(request.param)
    value = executor()
    args = common(value, tmp_path_factory.mktemp(f"wpb-native-{endpoint}"), endpoint)
    resolution = value._resolution(freeze_root=FREEZE)
    prepared = value.prepare_all(**prepare_args(args))
    contacts = Contacts()
    outcomes = value.execute_wave(**execute_args(args), allow_remote=True, call_codex=sol_runner(value, resolution["rows"], contacts))
    assert len(outcomes) == len(contacts.calls) == 129
    report = value.report(endpoint=endpoint, output_root=args["output_root"], freeze_root=FREEZE, authorization_acknowledgement_sha256=ACK, profile=profile())
    return {"value": value, "args": args, "resolution": resolution, "prepared": prepared, "contacts": contacts, "report": report}


def test_source_contract_and_provider_free_preparation() -> None:
    value = executor()
    resolution = value._resolution(freeze_root=FREEZE)
    contract = json.loads((PACKAGE / "study-contract.json").read_bytes())
    assert value.CORE_SHA256 == core_sha256() == contract["core"]["sha256"]
    assert value.MAX_CONCURRENCY == contract["execution"]["max_concurrency"] == 10
    assert len(resolution["rows"]) == 129
    assert Counter(row["partition"] for row in resolution["rows"]) == Counter({"train": 105, "dev": 24})


def test_grok_native_broker_guard_is_explicitly_gated_and_persists_terminal_outcomes(tmp_path: Path) -> None:
    value = executor()

    case, _support, route = broker_fixture(value)
    try:
        root = tmp_path / "revoked"
        root.mkdir()
        invoked = False

        def forbidden(**_kwargs: Any) -> dict[str, Any]:
            nonlocal invoked
            invoked = True
            return {"unexpected": True}

        case.broker._revoke_grok_route(route, "fixture revocation")
        guarded = value._brokered_grok_runner(broker=case.broker, route_name=route["name"], runner=forbidden)
        with pytest.raises(value.GrokNativeContactOutcome, match="did not complete") as error:
            guarded(output_dir=root, prompt=b"fixture")
        assert error.value.state == "definitely_not_contacted"
        assert not invoked
        outcome = json.loads((root / "broker-contact-outcome.json").read_bytes())
        assert outcome["state"] == "definitely_not_contacted"
        assert outcome["failure"]["category"] != "billing_error"
    finally:
        case.tearDown()


def test_single_root_grok_paths_are_retired(tmp_path: Path) -> None:
    value = executor()
    args = {"endpoint": "grok", "output_root": tmp_path / "output", "queue_root": tmp_path / "queue", "freeze_root": FREEZE, "authorization_acknowledgement_sha256": ACK}
    with pytest.raises(ValueError, match="retired"):
        value.prepare_all(**args)
    with pytest.raises(ValueError, match="retired"):
        value.execute_one(**args, cell_id="unused", allow_remote=True)
    with pytest.raises(ValueError, match="retired"):
        value.execute_wave(**args, allow_remote=True)
    assert not args["output_root"].exists()


def test_pinned_grok_broker_loader_rejects_cached_module_bypass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = executor()
    monkeypatch.setitem(sys.modules, "_wpb_pinned_model_work_queue", object())
    with pytest.raises(ValueError, match="module cache"):
        value._grok_broker(tmp_path / "queue", None)
    monkeypatch.undo()
    monkeypatch.setitem(sys.modules, "_wpb_pinned_model_work_queue.image_canary", object())
    with pytest.raises(ValueError, match="module cache"):
        value._grok_broker(tmp_path / "queue", None)


def test_grok_broker_factory_receives_the_isolated_canonical_provider_error_class(tmp_path: Path) -> None:
    value = executor()
    received: dict[str, Any] = {}

    def factory(root: Path, broker_type: type[Any], error_type: type[Exception]) -> Any:
        received.update({"root": root, "broker_type": broker_type, "error_type": error_type})
        return broker_type(root, grok_host_gate_path=tmp_path / "host-gate.sqlite3")

    broker, error_type = value._grok_broker(tmp_path / "queue", factory)
    assert type(broker) is received["broker_type"]
    assert received["error_type"] is error_type
    assert error_type.__name__ == "GrokNativeProviderError"
    assert error_type.__module__ == "_wpb_pinned_model_work_queue.broker"


def test_pinned_grok_broker_dependency_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = executor()
    monkeypatch.setattr(value, "IMAGE_CANARY_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="drift"):
        value._grok_broker(tmp_path / "queue", None)
    assert not any(name.startswith("_wpb_pinned_model_work_queue") for name in sys.modules)


def test_grok_broker_typed_and_unknown_failures(tmp_path: Path) -> None:
    value = executor()

    case, support, route = broker_fixture(value)
    try:
        complete_root = tmp_path / "completed"
        complete_root.mkdir()
        result = {"native": "receipt"}
        guarded = value._brokered_grok_runner(broker=case.broker, route_name=route["name"], runner=lambda **_kwargs: result)
        assert guarded(output_dir=complete_root, prompt=b"fixture") == result
        assert not (complete_root / "broker-contact-outcome.json").exists()

        quota_root = tmp_path / "quota"
        quota_root.mkdir()
        calls = 0

        def quota(**_kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            raise support.GrokNativeProviderError(status=402, code="usage_balance_exhausted", provider_error_type="HTTPStatusError")

        guarded = value._brokered_grok_runner(broker=case.broker, route_name=route["name"], runner=quota)
        with pytest.raises(value.GrokNativeContactOutcome) as error:
            guarded(output_dir=quota_root, prompt=b"fixture")
        assert calls == 1 and error.value.state == "ambiguous"
        quota_outcome = json.loads((quota_root / "broker-contact-outcome.json").read_bytes())
        assert quota_outcome["failure"]["status"] == 402
        assert quota_outcome["failure"]["revocation"] == "host_revoked_and_local_projected"
        no_resend_root = tmp_path / "quota-no-resend"
        no_resend_root.mkdir()
        with pytest.raises(value.GrokNativeContactOutcome):
            guarded(output_dir=no_resend_root, prompt=b"fixture")
        assert calls == 1
    finally:
        case.tearDown()

    case, _support, route = broker_fixture(value)
    try:
        ambiguous_root = tmp_path / "ambiguous"
        ambiguous_root.mkdir()
        calls = 0

        def unstructured(**_kwargs: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            raise RuntimeError("unstructured fixture failure")

        guarded = value._brokered_grok_runner(broker=case.broker, route_name=route["name"], runner=unstructured)
        with pytest.raises(value.GrokNativeContactOutcome) as error:
            guarded(output_dir=ambiguous_root, prompt=b"fixture")
        record = json.loads((ambiguous_root / "broker-contact-outcome.json").read_bytes())
        assert calls == 1 and error.value.state == record["state"] == "ambiguous"
        assert record["failure"].get("status") != 402
        assert record["failure"].get("category") != "billing_error"
    finally:
        case.tearDown()


def test_full_native_endpoint_fixtures_replay_real_receipts_and_bind_analyzer(completed_native_material: dict[str, Any]) -> None:
    value, args, resolution, prepared, contacts, report = (completed_native_material[name] for name in ("value", "args", "resolution", "prepared", "contacts", "report"))
    assert prepared["provider_calls_made"] == prepared["process_launches"] == prepared["native_contact_count"] == 0
    assert len(prepared["prepared_cells"]) == 129
    assert contacts.maximum <= 10 and len(set(contacts.calls)) == 129
    assert report["endpoint"] == prepared["endpoint"]
    assert report["measurement_count"] == 129
    assert report["core_sha256"] == core_sha256()
    assert report["analysis"]["study_id"] == value.STUDY_ID
    assert report["analysis"]["authority"] == "development_screening_only"
    assert report["analysis"]["mae"] == "not_applicable_pairwise_preference_target"
    assert report["local_terminal_receipt_count"] == 129
    assert report["native_endpoint_contact_cardinality"] == "unproven"
    forbidden = {"category", "source_model", "preferred_side", "chosen_score", "rejected_score", "target", "local_targets"}
    for row in resolution["rows"]:
        assert row["target"] == value.TRANSPORT_TARGET
        payload = json.loads(base64.b64decode(row["payload_base64"], validate=True))
        assert not forbidden & keys(payload)
    if prepared["endpoint"] == "sol":
        metadata = json.loads((args["output_root"] / prepared["prepared_cells"][0] / "prepared.json").read_bytes())
        source = metadata["source"]
        assert source["transport_target_sha256"] == value.sha256(value.TRANSPORT_TARGET)
        assert source["target_vector_semantics"] == "fixed transport sentinel only; WPB local targets are absent"
        assert source["wpb_core_sha256"] == core_sha256()
        assert source["wpb_native_contract_sha256"] == value.CONTRACT_SHA256
        assert not {"hanna_csv_sha256", "public_result_commit", "source_result_file_sha256", "source_executor_commit", "source_executor_sha256", "grok_result_sha256", "grok_result_internal_sha256", "grok_execution_commit", "grok_executor_sha256", "grok_collector_sha256", "result_internal_sha256"} & set(source)


def test_report_rejects_raw_identity_receipt_ack_route_and_payload_mutations(completed_native_material: dict[str, Any]) -> None:
    value, args, prepared = (completed_native_material[name] for name in ("value", "args", "prepared"))
    endpoint = prepared["endpoint"]
    root = args["output_root"] / prepared["prepared_cells"][0]
    artifacts = {
        "raw": root / ("native-response.bin" if endpoint == "grok" else "raw-codex-final-response.bin"),
        "identity": root / ("runtime-identity.json" if endpoint == "grok" else "execution-receipt.json"),
        "receipt": root / "execution-receipt.json",
        "ack": root / "authorization-acknowledgement.json",
        "route": root / "prepared.json",
        "payload": root / "outbound-payload.json",
    }
    for label, artifact in artifacts.items():
        original = artifact.read_bytes()
        if label == "identity":
            record = json.loads(original)
            (record["identity"] if endpoint == "sol" else record)["thread_id" if endpoint == "sol" else "request_id"] = "tampered-identity"
            artifact.write_bytes(value.canonical(record))
        elif label == "route":
            record = json.loads(original)
            record["route_evidence"] = {"tampered": True}
            artifact.write_bytes(value.canonical(record))
        else:
            artifact.write_bytes(b"{}\n")
        try:
            with pytest.raises((TypeError, ValueError)):
                value.report(endpoint=endpoint, output_root=args["output_root"], freeze_root=FREEZE, authorization_acknowledgement_sha256=ACK, profile=profile())
        finally:
            artifact.write_bytes(original)


@pytest.mark.parametrize("endpoint", ("sol",))
def test_alternate_route_is_rejected_precontact_and_postcontact_failure_is_terminal(tmp_path: Path, endpoint: str) -> None:
    value = executor()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(freeze_root=FREEZE)
    value.prepare_all(**prepare_args(args))
    selected = str(resolution["rows"][0]["cell_id"])
    call = execute_args(args)
    if endpoint == "grok":
        original = args["grok_route_provider"]

        def alternate(queue_root: Path):
            route, evidence = original(queue_root)
            return {**route, "name": "unapproved-alternate-route"}, evidence

        alternate_args = {"grok_route_provider": alternate, "grok_runner_factory": lambda _error: lambda **_kwargs: pytest.fail("alternate route contacted")}
    else:
        support = load(V12_TEST, "wpb_alternate_sol_route_support")
        route, _evidence = support.sol_route()
        alternate_args = {"sol_broker_factory": lambda _root: support.Broker({**route, "name": "unapproved-alternate-route"}), "call_codex": lambda **_kwargs: pytest.fail("alternate route contacted")}
    with pytest.raises((TypeError, ValueError)):
        value.execute_one(**(call | alternate_args), cell_id=selected, allow_remote=True)

    post_args = common(value, tmp_path / "postcontact", endpoint)
    value.prepare_all(**prepare_args(post_args))
    post_call = execute_args(post_args)
    contacts = Contacts()
    with pytest.raises((RuntimeError, TypeError, ValueError)):
        value.execute_one(**post_call, cell_id=selected, allow_remote=True, call_codex=sol_runner(value, resolution["rows"], contacts, fail_after_contact=True))
    assert contacts.calls == [selected] and contacts.failed
    failed_root = post_args["output_root"] / selected
    assert (failed_root / "result.json").is_file()
    assert not (failed_root / "execution-receipt.json").exists()
    with pytest.raises((TypeError, ValueError)):
        value.execute_one(**post_call, cell_id=selected, allow_remote=True, call_codex=lambda **_kwargs: pytest.fail("terminal Sol cell was resent"))
    assert contacts.calls == [selected]


@pytest.mark.parametrize("endpoint", ("sol",))
def test_wave_stops_queued_cells_after_first_terminal_failure_and_never_resends(tmp_path: Path, endpoint: str, monkeypatch: pytest.MonkeyPatch) -> None:
    value = executor()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(freeze_root=FREEZE)
    rows = resolution["rows"]
    initial = tuple(str(row["cell_id"]) for row in rows[: value.MAX_CONCURRENCY])
    failed = initial[0]
    value.prepare_all(**prepare_args(args))
    contacts = Contacts()
    gate = threading.Barrier(value.MAX_CONCURRENCY)
    original_pool = ThreadPoolExecutor

    class ObservingPool(original_pool):
        def submit(self, fn: Any, /, *submit_args: Any, **submit_kwargs: Any):
            future = super().submit(fn, *submit_args, **submit_kwargs)
            if submit_args and str(submit_args[0]["cell_id"]) == failed:
                future.add_done_callback(lambda _future: contacts.failure_observed.set())
            return future

    monkeypatch.setattr(value, "ThreadPoolExecutor", ObservingPool)
    with pytest.raises((RuntimeError, TypeError, ValueError)):
        value.execute_wave(
            **execute_args(args),
            allow_remote=True,
            call_codex=sol_runner(value, rows, contacts, fail_after_contact=True, start_gate=gate, failure_cell=failed, success_release=contacts.failure_observed),
        )
    assert contacts.maximum == value.MAX_CONCURRENCY
    assert set(contacts.calls) == set(initial)
    assert len(contacts.calls) == value.MAX_CONCURRENCY
    failed_root = args["output_root"] / failed
    assert (failed_root / "result.json").is_file()
    assert not (failed_root / "execution-receipt.json").exists()
    assert sum((args["output_root"] / cell_id / "execution-receipt.json").is_file() for cell_id in initial) == value.MAX_CONCURRENCY - 1
    with pytest.raises((TypeError, ValueError)):
        value.execute_wave(
            **execute_args(args),
            allow_remote=True,
            call_codex=lambda **_kwargs: pytest.fail("terminal Sol wave cell was resent"),
        )
    assert set(contacts.calls) == set(initial)
