from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v16-comparative-train-v1"
EXECUTOR = PACKAGE / "executor.py"
CORE = PACKAGE / "study.py"
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
    return load(EXECUTOR, "v16_comparative_native_executor")


def core_sha256() -> str:
    return hashlib.sha256(CORE.read_bytes()).hexdigest()


def source_args() -> dict[str, Path]:
    return {"split_manifest": SPLIT, "hanna_csv": CSV, "successor_contract": CONTRACT}


def common(value: Any, tmp_path: Path, endpoint: str) -> dict[str, Any]:
    queue = tmp_path / f"{endpoint}-queue"
    queue.mkdir()
    support = load(V12_TEST, f"v16_{endpoint}_sol_route_support")
    route, _evidence = support.sol_route()
    return {
        "endpoint": endpoint,
        "output_root": tmp_path / f"{endpoint}-output",
        "queue_root": queue,
        "authorization_acknowledgement_sha256": ACK,
        "expected_core_sha256": core_sha256(),
        **source_args(),
        "grok_route_provider": load(V15_GROK_TEST, f"v16_{endpoint}_grok_route_support")._route_provider(),
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
        return {key: value for key, value in _item(value, row["item_id"]).items() if key != "item_id"}
    items = [_item(value, item_id) for item_id in row["item_ids"]]
    if malformed == "partial":
        return {"items": [items[0]]}
    if malformed == "missing":
        return {"items": items[:-1]}
    if malformed == "duplicate":
        items[-1]["item_id"] = items[0]["item_id"]
    return {"items": items}


def _grok_runner(value: Any, rows: tuple[dict[str, Any], ...], contacts: Counter[str], malformed: str | None = None):
    index = {row["cell_id"]: row for row in rows}
    lock = threading.Lock()

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route: dict[str, Any], before_contact):
        row = index[output_dir.name]
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
        with lock:
            contacts[row["condition"]] += 1
        return {
            "native_request_bytes": json.dumps({"prompt": prompt.decode("utf-8")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "native_response_bytes": response,
            "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
            "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": hashlib.sha256(prompt).hexdigest(), "reasoning_attested": False},
        }

    return run


def _sol_runner(value: Any, rows: tuple[dict[str, Any], ...], contacts: Counter[str], malformed: str | None = None):
    index = {row["cell_id"]: row for row in rows}
    native = load(NATIVE, "v16_comparative_native_sol_command")
    lock = threading.Lock()

    def invoke(**kwargs: Any):
        root = Path(kwargs["output_dir"])
        row = index[root.name]
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
        with lock:
            contacts[row["condition"]] += 1
        return final, {
            "command": native._expected_codex_command(kwargs["executable"], root),
            "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": f"fixture-thread-{row['cell_id']}"},
            "provider_artifacts": {
                "codex_events": {"path": events_path.relative_to(root).as_posix(), "bytes": len(events), "sha256": hashlib.sha256(events).hexdigest()},
                "codex_stderr": {"path": stderr_path.relative_to(root).as_posix(), "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()},
            },
        }

    return invoke


def v15_grok_root(tmp_path: Path) -> Path:
    support = load(V15_GROK_TEST, "v16_comparative_v15_grok_fixture")
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
    support = load(V15_SOL_TEST, "v16_comparative_v15_sol_fixture")
    value = support.load(support.SOL, "v16_comparative_v15_sol")
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


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
def test_endpoint_replays_v15_receipts_and_executes_exact_new_native_panel(tmp_path: Path, endpoint: str):
    value = module()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(**source_args(), expected_core_sha256=args["expected_core_sha256"])
    assert len(resolution["new"]) == 39 and len(resolution["reused"]) == 21
    prepared = value.prepare_all(**args)
    assert prepared["endpoint"] == endpoint and prepared["provider_calls_made"] == prepared["process_launches"] == 0
    assert set(prepared["prepared_cells"]) == {row["cell_id"] for row in resolution["new"]}
    for row in resolution["new"]:
        root = args["output_root"] / row["cell_id"]
        payload = (root / "outbound-payload.json").read_bytes()
        assert payload == base64.b64decode(row["payload_base64"], validate=True)
        assert "target" not in json.loads(payload)

    contacts: Counter[str] = Counter()
    execute = {name: args[name] for name in args if name not in {"endpoint", "expected_core_sha256"}}
    outcomes = value.execute_wave(
        endpoint=endpoint,
        expected_core_sha256=args["expected_core_sha256"],
        **execute,
        allow_remote=True,
        grok_runner=_grok_runner(value, resolution["new"], contacts) if endpoint == "grok" else None,
        call_codex=_sol_runner(value, resolution["new"], contacts) if endpoint == "sol" else None,
    )
    assert len(outcomes) == sum(contacts.values()) == 39
    assert contacts == Counter({value.DIRECT: 29, value.FORWARD: 5, value.REVERSE: 5})

    prior = v15_root(endpoint, tmp_path)
    report = value.report(**report_args(args, prior))
    assert report["endpoint"] == ("grok_primary" if endpoint == "grok" else "sol_later")
    assert report["fresh_native_cell_count"] == 39
    assert report["historical_v15_direct_reuse_count"] == 21
    assert set(report["analysis"]["metrics"]) == {"direct_historical_noncontemporaneous", value.FORWARD, value.REVERSE, "per_story_mean_orders"}

    with pytest.raises(ValueError, match="completed|terminal|resend|claim|inventory"):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=lambda **_kwargs: pytest.fail("completed Grok cell was resent"),
            call_codex=lambda **_kwargs: pytest.fail("completed Sol cell was resent"),
        )
    assert contacts == Counter({value.DIRECT: 29, value.FORWARD: 5, value.REVERSE: 5})

    prepared_path = args["output_root"] / prepared["prepared_cells"][0] / "prepared.json"
    original = prepared_path.read_bytes()
    record = json.loads(original)
    binding = next(name for name in record if name.endswith("payload_sha256"))
    record[binding] = "0" * 64
    prepared_path.write_bytes(value.canonical(record))
    try:
        with pytest.raises((TypeError, ValueError)):
            value.report(**report_args(args, prior))
    finally:
        prepared_path.write_bytes(original)


@pytest.mark.parametrize("endpoint", ("grok", "sol"))
@pytest.mark.parametrize("malformed", ("partial", "missing", "duplicate"))
def test_malformed_comparative_receipt_is_terminal_without_remaining_batch_calls(tmp_path: Path, endpoint: str, malformed: str):
    value = module()
    args = common(value, tmp_path, endpoint)
    resolution = value._resolution(**source_args(), expected_core_sha256=args["expected_core_sha256"])
    value.prepare_all(**args)
    contacts: Counter[str] = Counter()
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
    assert contacts[value.DIRECT] == 29
    assert contacts[value.FORWARD] + contacts[value.REVERSE] == 1
    before = contacts.copy()
    with pytest.raises((TypeError, ValueError)):
        value.execute_wave(
            endpoint=endpoint,
            expected_core_sha256=args["expected_core_sha256"],
            **execute,
            allow_remote=True,
            grok_runner=lambda **_kwargs: pytest.fail("invalid terminal Grok receipt was resent"),
            call_codex=lambda **_kwargs: pytest.fail("invalid terminal Sol receipt was resent"),
        )
    assert contacts == before
