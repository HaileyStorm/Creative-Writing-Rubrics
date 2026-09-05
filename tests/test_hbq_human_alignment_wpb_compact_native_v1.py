from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
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
    return {
        "endpoint": endpoint,
        "output_root": root / f"{endpoint}-output",
        "queue_root": queue,
        "freeze_root": FREEZE,
        "authorization_acknowledgement_sha256": ACK,
        "grok_route_provider": load(V15_GROK_TEST, f"wpb_{endpoint}_grok_route_support")._route_provider(),
        "sol_broker_factory": lambda _root: support.Broker(route),
    }


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
            envelope = {
                "modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}},
                "num_turns": 1,
                "requestId": f"request-{output_dir.name}",
                "sessionId": f"session-{output_dir.name}",
                "stopReason": "end_turn",
                "structuredOutput": structured,
                "text": json.dumps(structured, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "thought": "",
                "total_cost_usd": 0.0,
                "total_cost_usd_ticks": 0,
                "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4},
            }
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
            return {
                "native_request_bytes": json.dumps({"prompt": prompt.decode("utf-8")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                "native_response_bytes": response,
                "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
                "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False},
            }
        finally:
            contacts.leave()

    return run


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


@pytest.fixture(scope="module", params=("grok", "sol"))
def completed_native_material(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    endpoint = str(request.param)
    value = executor()
    args = common(value, tmp_path_factory.mktemp(f"wpb-native-{endpoint}"), endpoint)
    resolution = value._resolution(freeze_root=FREEZE)
    prepared = value.prepare_all(**args)
    contacts = Contacts()
    outcomes = value.execute_wave(**execute_args(args), allow_remote=True, grok_runner=grok_runner(value, resolution["rows"], contacts) if endpoint == "grok" else None, call_codex=sol_runner(value, resolution["rows"], contacts) if endpoint == "sol" else None)
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


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
def test_alternate_route_is_rejected_precontact_and_postcontact_failure_is_terminal(tmp_path: Path, endpoint: str) -> None:
    value = executor()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(freeze_root=FREEZE)
    value.prepare_all(**args)
    selected = str(resolution["rows"][0]["cell_id"])
    call = execute_args(args)
    if endpoint == "grok":
        original = args["grok_route_provider"]

        def alternate(queue_root: Path):
            route, evidence = original(queue_root)
            return {**route, "name": "unapproved-alternate-route"}, evidence

        alternate_args = {"grok_route_provider": alternate, "grok_runner": lambda **_kwargs: pytest.fail("alternate route contacted")}
    else:
        support = load(V12_TEST, "wpb_alternate_sol_route_support")
        route, _evidence = support.sol_route()
        alternate_args = {"sol_broker_factory": lambda _root: support.Broker({**route, "name": "unapproved-alternate-route"}), "call_codex": lambda **_kwargs: pytest.fail("alternate route contacted")}
    with pytest.raises((TypeError, ValueError)):
        value.execute_one(**(call | alternate_args), cell_id=selected, allow_remote=True)

    post_args = common(value, tmp_path / "postcontact", endpoint)
    value.prepare_all(**post_args)
    post_call = execute_args(post_args)
    contacts = Contacts()
    with pytest.raises((RuntimeError, TypeError, ValueError)):
        value.execute_one(**post_call, cell_id=selected, allow_remote=True, grok_runner=grok_runner(value, resolution["rows"], contacts, fail_after_contact=True) if endpoint == "grok" else None, call_codex=sol_runner(value, resolution["rows"], contacts, fail_after_contact=True) if endpoint == "sol" else None)
    assert contacts.calls == [selected] and contacts.failed
    failed_root = post_args["output_root"] / selected
    assert (failed_root / "result.json").is_file()
    assert not (failed_root / "execution-receipt.json").exists()
    with pytest.raises((TypeError, ValueError)):
        value.execute_one(**post_call, cell_id=selected, allow_remote=True, grok_runner=lambda **_kwargs: pytest.fail("terminal Grok cell was resent"), call_codex=lambda **_kwargs: pytest.fail("terminal Sol cell was resent"))
    assert contacts.calls == [selected]


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
def test_wave_stops_queued_cells_after_first_terminal_failure_and_never_resends(tmp_path: Path, endpoint: str, monkeypatch: pytest.MonkeyPatch) -> None:
    value = executor()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(freeze_root=FREEZE)
    rows = resolution["rows"]
    initial = tuple(str(row["cell_id"]) for row in rows[: value.MAX_CONCURRENCY])
    failed = initial[0]
    value.prepare_all(**args)
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
            grok_runner=grok_runner(value, rows, contacts, fail_after_contact=True, start_gate=gate, failure_cell=failed, success_release=contacts.failure_observed) if endpoint == "grok" else None,
            call_codex=sol_runner(value, rows, contacts, fail_after_contact=True, start_gate=gate, failure_cell=failed, success_release=contacts.failure_observed) if endpoint == "sol" else None,
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
            grok_runner=lambda **_kwargs: pytest.fail("terminal Grok wave cell was resent"),
            call_codex=lambda **_kwargs: pytest.fail("terminal Sol wave cell was resent"),
        )
    assert set(contacts.calls) == set(initial)
