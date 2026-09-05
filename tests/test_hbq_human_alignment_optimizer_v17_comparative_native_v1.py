from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v17-comparative-train-replication-native-v1"
EXECUTOR = PACKAGE / "executor.py"
CORE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v17-comparative-train-replication-v1" / "study.py"
V15_GROK_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v15_rank_discrimination_v1.py"
V15_SOL_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v15_rank_discrimination_sol_v1.py"
V12_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v12_development_sol_exec_v1.py"
NATIVE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
ACK = "a" * 64


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def module() -> Any:
    return load(EXECUTOR, "v17_comparative_native_executor")


def core_sha256() -> str:
    return hashlib.sha256(CORE.read_bytes()).hexdigest()


def source_args() -> dict[str, Path]:
    return {"split_manifest": SPLIT, "hanna_csv": CSV, "successor_contract": CONTRACT}


def common(value: Any, tmp_path: Path, endpoint: str) -> dict[str, Any]:
    queue = tmp_path / f"{endpoint}-queue"
    queue.mkdir()
    support = load(V12_TEST, f"v17_{endpoint}_sol_route_support")
    route, _evidence = support.sol_route()
    return {
        "endpoint": endpoint,
        "output_root": tmp_path / f"{endpoint}-output",
        "queue_root": queue,
        "authorization_acknowledgement_sha256": ACK,
        "expected_core_sha256": core_sha256(),
        **source_args(),
        "grok_route_provider": load(V15_GROK_TEST, f"v17_{endpoint}_grok_route_support")._route_provider(),
        "sol_broker_factory": lambda _root: support.Broker(route),
    }


def _item(value: Any, item_id: str, score: float = 3.0) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "scores": {dimension: score for dimension in value.DIMS},
        "evidence": {dimension: "Fixture evidence." for dimension in value.DIMS},
        "coverage": {dimension: False for dimension in value.DIMS},
    }


def _answer(value: Any, row: dict[str, Any], malformed: str | None = None) -> dict[str, Any]:
    if row["condition"] == value.DIRECT:
        return {key: item for key, item in _item(value, row["item_id"]).items() if key != "item_id"}
    items = [_item(value, item_id) for item_id in row["item_ids"]]
    if malformed == "partial":
        return {"items": [items[0]]}
    if malformed == "missing":
        return {"items": items[:-1]}
    if malformed == "duplicate":
        items[-1]["item_id"] = items[0]["item_id"]
    return {"items": items}


class Contacts:
    def __init__(self) -> None:
        self.by_condition: Counter[str] = Counter()
        self.entered: list[str] = []
        self.contacted: list[str] = []
        self.contacted_ids: list[str] = []
        self.active = 0
        self.maximum = 0
        self.failed_direct = False
        self.lock = threading.Lock()

    def enter(self, cell_id: str) -> None:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)

            self.entered.append(cell_id)

    def contact(self, cell_id: str, condition: str) -> None:
        with self.lock:
            self.contacted.append(condition)
            self.contacted_ids.append(cell_id)
            self.by_condition[condition] += 1

    def leave(self) -> None:
        with self.lock:
            self.active -= 1

    def fail_direct_once(self, condition: str) -> bool:
        with self.lock:
            if condition != "direct_integer" or self.failed_direct:
                return False
            self.failed_direct = True
            return True


def _grok_runner(value: Any, rows: tuple[dict[str, Any], ...], contacts: Contacts, malformed: str | None = None, fail_direct_after_contact: bool = False):
    index = {row["cell_id"]: row for row in rows}

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route: dict[str, Any], before_contact):
        row = index[output_dir.name]
        contacts.enter(row["cell_id"])
        try:
            time.sleep(0.005)
            expected = base64.b64decode(row["payload_base64"], validate=True)
            assert prompt == expected
            outbound = json.loads(prompt)
            assert "target" not in outbound
            assert json.loads(schema_path.read_bytes()) == outbound["response_schema"]
            structured = _answer(value, row, malformed if row["condition"] != value.DIRECT else None)
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
            contacts.contact(row["cell_id"], row["condition"])
            if fail_direct_after_contact and contacts.fail_direct_once(row["condition"]):
                raise RuntimeError("fixture direct failure after contact")
            return {
            "native_request_bytes": json.dumps({"prompt": prompt.decode("utf-8")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "native_response_bytes": response,
            "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
            "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False},
            }
        finally:
            contacts.leave()

    return run


def _sol_runner(value: Any, rows: tuple[dict[str, Any], ...], contacts: Contacts, malformed: str | None = None, fail_direct_after_contact: bool = False):
    index = {row["cell_id"]: row for row in rows}
    native = load(NATIVE, "v17_comparative_native_sol_command")

    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        row = index[root.name]
        contacts.enter(row["cell_id"])
        try:
            time.sleep(0.005)
            answer = _answer(value, row, malformed if row["condition"] != value.DIRECT else None)
            final = json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            responses = root / "responses"
            responses.mkdir(exist_ok=True)
            kwargs["before_provider_attempt"]()
            events = b"".join(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            for event in (
                {"type": "thread.started", "thread_id": f"fixture-thread-{row['cell_id']}"},
                {"type": "turn.started"},
                {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}},
                {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
                {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}},
            )
            )
            events_path = responses / "batch-0001.attempt-0001.events.jsonl"
            stderr_path = root / "raw-codex-stderr.bin"
            events_path.write_bytes(events)
            (responses / "batch-0001.attempt-0001.message.json").write_text(final, encoding="utf-8")
            stderr_path.write_bytes(b"")
            contacts.contact(row["cell_id"], row["condition"])
            if fail_direct_after_contact and contacts.fail_direct_once(row["condition"]):
                raise RuntimeError("fixture direct failure after contact")
            return final, {
            "command": native._expected_codex_command(kwargs["executable"], root),
            "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{row['cell_id']}"},
            "provider_artifacts": {
                "codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": hashlib.sha256(events).hexdigest()},
                "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()},
            },
            }
        finally:
            contacts.leave()

    return invoke


def v15_grok_root(tmp_path: Path) -> Path:
    support = load(V15_GROK_TEST, "v17_comparative_v15_grok_fixture")
    value = support.module()
    root = tmp_path / "v15-grok"
    root.mkdir()
    args = support._args(root)
    value.prepare_all(**args)
    assert len(value.execute_wave(**args, allow_remote=True, runner=support._native_runner(value))) == 96
    report = value.report(**{name: args[name] for name in ("output_root", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract")})
    assert report["status"] == "complete_matched_96_cells"
    return args["output_root"]


def v15_sol_root(tmp_path: Path) -> Path:
    support = load(V15_SOL_TEST, "v17_comparative_v15_sol_fixture")
    value = support.load(support.SOL, "v17_comparative_v15_sol")
    root = tmp_path / "v15-sol"
    root.mkdir()
    args = support.common(root)
    call_args = {name: item for name, item in args.items() if name != "route_evidence"}
    value.prepare_all(**call_args)
    rows = value._resolution(**{name: args[name] for name in ("split_manifest", "hanna_csv", "successor_contract")})["rows"]
    assert len(value.execute_wave(**call_args, allow_remote=True, call_codex=support.fake_codex(value, rows, [], {"active": 0, "maximum": 0}))) == 96
    report = value.report(**{name: args[name] for name in ("output_root", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract")})
    assert report["status"] == "complete_matched_96_cells"
    return args["output_root"]


def v15_root(endpoint: str, tmp_path: Path) -> Path:
    return v15_grok_root(tmp_path) if endpoint == "grok" else v15_sol_root(tmp_path)


def report_args(args: dict[str, Any], root: Path) -> dict[str, Any]:
    return {
        name: args[name]
        for name in ("endpoint", "output_root", "expected_core_sha256", "authorization_acknowledgement_sha256", "split_manifest", "hanna_csv", "successor_contract")
    } | {"v15_root": root, "v15_acknowledgement_sha256": ACK}


def test_native_and_source_contracts_are_pinned_and_tamper_rejecting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    resolution = value._resolution(**source_args(), expected_core_sha256=core_sha256())
    native_contract = json.loads((PACKAGE / "study-contract.json").read_bytes())
    assert value.STUDY_ID == native_contract["study_id"]
    assert value.SOURCE_STUDY_ID == resolution["schedule"]["study_id"]
    assert value.sha256((PACKAGE / "study-contract.json").read_bytes()) == value.CONTRACT_SHA256
    execution = value._execution_schedule(resolution)
    assert execution["study_id"] == value.STUDY_ID
    assert execution["v17_native_contract_sha256"] == value.CONTRACT_SHA256
    assert execution["v17_core_sha256"] == core_sha256()

    altered_contract = tmp_path / "altered-contract.json"
    altered_contract.write_bytes(b"{}\n")
    monkeypatch.setattr(value, "CONTRACT", altered_contract)
    with pytest.raises(ValueError, match="native contract drifted"):
        value._resolution(**source_args(), expected_core_sha256=core_sha256())
    monkeypatch.setattr(value, "CONTRACT", PACKAGE / "study-contract.json")
    monkeypatch.setattr(value, "CORE_CONTRACT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="pinned runtime dependency drifted"):
        value._resolution(**source_args(), expected_core_sha256=core_sha256())


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
def test_endpoint_executes_exact_48_fresh_then_replays_12_pinned_v15_receipts(tmp_path: Path, endpoint: str):
    value = module()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(**source_args(), expected_core_sha256=args["expected_core_sha256"])
    assert value.MAX_CONCURRENCY == 10
    assert len(resolution["new"]) == 48 and len(resolution["reused"]) == 12
    assert Counter(row["condition"] for row in resolution["new"]) == Counter({value.DIRECT: 38, value.FORWARD: 5, value.REVERSE: 5})

    prepared = value.prepare_all(**args)
    assert prepared["endpoint"] == endpoint
    assert prepared["provider_calls_made"] == prepared["process_launches"] == prepared["native_contact_count"] == 0
    assert set(prepared["prepared_cells"]) == {row["cell_id"] for row in resolution["new"]}
    for row in resolution["new"]:
        root = args["output_root"] / row["cell_id"]
        payload = (root / "outbound-payload.json").read_bytes()
        assert payload == base64.b64decode(row["payload_base64"], validate=True)
        assert "target" not in json.loads(payload)
    if endpoint == "sol":
        prepared_metadata = json.loads((args["output_root"] / prepared["prepared_cells"][0] / "prepared.json").read_bytes())
        source = prepared_metadata["source"]
        assert source["v17_core_sha256"] == args["expected_core_sha256"]
        assert source["v17_schedule_sha256"] == resolution["schedule_sha256"]
        assert source["v17_native_contract_sha256"] == value.CONTRACT_SHA256
        assert source["result_analyzer_commit"] == value.CORE_COMMIT
        assert source["result_analyzer_sha256"] == args["expected_core_sha256"]
        assert source["result_analyzer_contract_sha256"] == value.CORE_CONTRACT_SHA256
        assert not {"public_result_commit", "source_result_file_sha256", "source_executor_commit", "source_executor_sha256", "schedule_sha256", "collector_sha256", "result_internal_sha256"} & set(source)

    contacts = Contacts()
    execute = {name: args[name] for name in args if name not in {"endpoint", "expected_core_sha256"}}
    outcomes = value.execute_wave(
        endpoint=endpoint,
        expected_core_sha256=args["expected_core_sha256"],
        **execute,
        allow_remote=True,
        grok_runner=_grok_runner(value, resolution["new"], contacts) if endpoint == "grok" else None,
        call_codex=_sol_runner(value, resolution["new"], contacts) if endpoint == "sol" else None,
    )
    assert len(outcomes) == sum(contacts.by_condition.values()) == 48
    assert {outcome["state"] for outcome in outcomes} == ({"provisional_scoring_received"} if endpoint == "grok" else {"local_codex_lifecycle_received_native_contact_unproven"})
    assert contacts.by_condition == Counter({value.DIRECT: 38, value.FORWARD: 5, value.REVERSE: 5})
    assert contacts.maximum <= value.MAX_CONCURRENCY
    scheduled_rows = resolution["new"] if endpoint == "grok" else value._sol_rows(None, resolution)
    pilot = next(row for row in scheduled_rows if row["condition"] in {value.FORWARD, value.REVERSE})
    initial_ids = {pilot["cell_id"], *(row["cell_id"] for row in scheduled_rows if row["condition"] == value.DIRECT)}
    outcome_ids = [outcome["cell_id"] for outcome in outcomes]
    assert set(outcome_ids[:39]) == initial_ids
    assert set(outcome_ids[39:]) == {row["cell_id"] for row in resolution["new"]} - initial_ids
    assert contacts.entered.index(pilot["cell_id"]) < 39

    prior = v15_root(endpoint, tmp_path)
    report = value.report(**report_args(args, prior))
    assert report["endpoint"] == ("grok_primary" if endpoint == "grok" else "sol_later")
    assert report["fresh_native_cell_count"] == 48
    assert report["historical_v15_direct_reuse_count"] == 12
    assert report["v17_core_sha256"] == args["expected_core_sha256"] == core_sha256()
    assert report["v17_core_commit"] == value.CORE_COMMIT
    assert report["v17_core_contract_sha256"] == value.CORE_CONTRACT_SHA256
    assert report["v17_native_contract_sha256"] == value.CONTRACT_SHA256
    assert report["measurement_provenance"]["fresh_acknowledgement_sha256"] == ACK
    assert len(report["measurement_provenance"]["cells"]) == 60
    assert report["analysis"]["expected_endpoint"] == report["endpoint"]
    assert set(report["analysis"]["metrics"]) == {"direct_historical_noncontemporaneous", value.FORWARD, value.REVERSE, "per_story_mean_orders"}

    cell_root = args["output_root"] / prepared["prepared_cells"][0]
    artifacts = {
        "raw": cell_root / ("native-response.bin" if endpoint == "grok" else "raw-codex-final-response.bin"),
        "identity": cell_root / ("runtime-identity.json" if endpoint == "grok" else "execution-receipt.json"),
        "receipt": cell_root / "execution-receipt.json",
        "acknowledgement": cell_root / "authorization-acknowledgement.json",
        "route": cell_root / "prepared.json",
        "payload": cell_root / "outbound-payload.json",
    }
    for label, artifact in artifacts.items():
        original = artifact.read_bytes()
        if label == "identity":
            mutated = json.loads(original)
            (mutated["identity"] if endpoint == "sol" else mutated)["request_id" if endpoint == "grok" else "thread_id"] = "tampered-identity"
            artifact.write_bytes(value.canonical(mutated))
        elif label == "route":
            mutated = json.loads(original)
            mutated["route_evidence"] = {"tampered": True}
            artifact.write_bytes(value.canonical(mutated))
        else:
            artifact.write_bytes(b"{}\n")
        try:
            with pytest.raises((TypeError, ValueError)):
                value.report(**report_args(args, prior))
        finally:
            artifact.write_bytes(original)

    with pytest.raises(ValueError, match="completed|terminal|resend|claim|inventory"):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=lambda **_kwargs: pytest.fail("completed Grok cell was resent"),
            call_codex=lambda **_kwargs: pytest.fail("completed Sol cell was resent"),
        )
    assert contacts.by_condition == Counter({value.DIRECT: 38, value.FORWARD: 5, value.REVERSE: 5})


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
@pytest.mark.parametrize("malformed", ("partial", "missing", "duplicate"))
def test_malformed_comparative_receipt_is_terminal_without_resend(tmp_path: Path, endpoint: str, malformed: str):
    value = module()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(**source_args(), expected_core_sha256=args["expected_core_sha256"])
    value.prepare_all(**args)
    contacts = Contacts()
    execute = {name: args[name] for name in args if name not in {"endpoint", "expected_core_sha256"}}
    with pytest.raises((TypeError, ValueError)):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=_grok_runner(value, resolution["new"], contacts, malformed) if endpoint == "grok" else None,
            call_codex=_sol_runner(value, resolution["new"], contacts, malformed) if endpoint == "sol" else None,
        )
    assert 0 < contacts.by_condition[value.DIRECT] <= 38
    assert contacts.by_condition[value.FORWARD] + contacts.by_condition[value.REVERSE] == 1
    assert len(contacts.contacted_ids) == len(set(contacts.contacted_ids))
    before = contacts.by_condition.copy()
    with pytest.raises((TypeError, ValueError)):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=lambda **_kwargs: pytest.fail("invalid terminal Grok receipt was resent"),
            call_codex=lambda **_kwargs: pytest.fail("invalid terminal Sol receipt was resent"),
        )
    assert contacts.by_condition == before


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
def test_postcontact_direct_failure_is_terminal_and_wave_never_recontacts(tmp_path: Path, endpoint: str):
    value = module()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(**source_args(), expected_core_sha256=args["expected_core_sha256"])
    value.prepare_all(**args)
    contacts = Contacts()
    execute = {name: args[name] for name in args if name not in {"endpoint", "expected_core_sha256"}}
    with pytest.raises(ValueError, match="terminal non-success outcomes|preserve receipts"):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=_grok_runner(value, resolution["new"], contacts, fail_direct_after_contact=True) if endpoint == "grok" else None,
            call_codex=_sol_runner(value, resolution["new"], contacts, fail_direct_after_contact=True) if endpoint == "sol" else None,
        )
    assert contacts.failed_direct
    before = contacts.by_condition.copy()
    with pytest.raises((TypeError, ValueError)):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=lambda **_kwargs: pytest.fail("post-contact Grok cell was resent"),
            call_codex=lambda **_kwargs: pytest.fail("post-contact Sol cell was resent"),
        )
    assert contacts.by_condition == before


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
def test_unapproved_alternate_route_is_rejected_before_contact(tmp_path: Path, endpoint: str):
    value = module()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(**source_args(), expected_core_sha256=args["expected_core_sha256"])
    value.prepare_all(**args)
    execute = {name: args[name] for name in args if name not in {"endpoint", "expected_core_sha256", "grok_route_provider", "sol_broker_factory"}}
    if endpoint == "grok":
        original_route = args["grok_route_provider"]

        def alternate_route(queue_root: Path):
            route, evidence = original_route(queue_root)
            return {**route, "name": "unapproved-alternate-route"}, evidence

        route_args = {"grok_route_provider": alternate_route, "grok_runner": lambda **_kwargs: pytest.fail("alternate Grok route contacted")}
    else:
        support = load(V12_TEST, "v17_alternate_sol_route_support")
        route, _evidence = support.sol_route()
        route_args = {
            "sol_broker_factory": lambda _root: support.Broker({**route, "name": "unapproved-alternate-route"}),
            "call_codex": lambda **_kwargs: pytest.fail("alternate Sol route contacted"),
        }
    with pytest.raises((TypeError, ValueError)):
        value.execute_one(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            cell_id=resolution["new"][0]["cell_id"],
            allow_remote=True,
            **route_args,
        )
