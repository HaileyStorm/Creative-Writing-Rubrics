from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1"
EXPANSION = PACKAGE / "expansion.py"
V13_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v13_train_expansion_v1.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
RECOVERED = Path(r"C:\Users\Haile\Documents\cwr-hanna-dspy-proposal-recovery-cbe403dd-20260904-r1\recovered-descendant.json")
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
ACK = "a" * 64


def module():
    if not EXPANSION.is_file() or not RECOVERED.is_file():
        pytest.skip("V14 DSPy TRAIN expansion source is unavailable")
    spec = importlib.util.spec_from_file_location("v14_dspy_train_expansion", EXPANSION)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def v13_fixture():
    spec = importlib.util.spec_from_file_location("v13_train_expansion_fixture", V13_TEST)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def route_provider():
    return v13_fixture().route_provider()


def common(tmp_path: Path) -> dict:
    return {
        "output_root": tmp_path / "output",
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
        "recovered_descendant": RECOVERED,
        "route_provider": route_provider(),
    }


def report_args(args: dict) -> dict:
    return {key: args[key] for key in args if key not in {"queue_root", "route_provider"}}


def test_schedule_is_fresh_44_item_88_cell_train_expansion_with_endpoint_payload_parity(tmp_path: Path):
    value = module()
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, recovered_descendant=RECOVERED)
    cells = schedule["cells"]
    assert len(cells) == 88
    assert {cell["candidate_id"] for cell in cells} == {CHILD20, DESCENDANT}
    assert {cell["partition"] for cell in cells} == {"train"}
    assert len({cell["item_id"] for cell in cells}) == 44
    groups: dict[str, set[str]] = defaultdict(set)
    paired: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        groups[cell["prompt_group_id"]].add(cell["item_id"])
        paired[cell["item_id"]].add(cell["candidate_id"])
        payload = base64.b64decode(cell["payload_base64"], validate=True)
        assert value.sha256(payload) == cell["payload_sha256"]
        assert "target" not in json.loads(payload)
        assert cell["endpoint_payload_sha256s"]["grok_primary"] == cell["endpoint_payload_sha256s"]["sol_later"] == cell["payload_sha256"]
    assert len(groups) == 22
    assert sorted(map(len, groups.values())) == [1] * 12 + [2] * 3 + [3] * 3 + [4] * 3 + [5]
    assert all(candidates == {CHILD20, DESCENDANT} for candidates in paired.values())
    assert schedule["authority"]["previous_v13"] == "unchanged_not_adopted"
    copied = tmp_path / "recovered-descendant.json"
    copied.write_bytes(RECOVERED.read_bytes() + b"x")
    with pytest.raises(ValueError, match="recovered descendant source drifted"):
        value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, recovered_descendant=copied)


def test_prepare_is_provider_free_and_rejects_output_inside_every_frozen_input_parent(tmp_path: Path):
    value = module()
    prepared = value.prepare_all(**common(tmp_path))
    assert prepared["logical_cells"] == len(prepared["prepared_cells"]) == 88
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    assert all(cell_id.startswith("v14-expansion-") for cell_id in prepared["prepared_cells"])

    for ordinal, source_path in enumerate((RECOVERED, SPLIT, CSV, CONTRACT)):
        output_root = source_path.parent / f"v14-expansion-overlap-{ordinal}"
        assert not output_root.exists()
        before = {path.name for path in source_path.parent.iterdir()}
        args = common(tmp_path)
        args["output_root"] = output_root
        with pytest.raises(ValueError):
            value.prepare_all(**args)
        assert not output_root.exists()
        assert {path.name for path in source_path.parent.iterdir()} == before


def native_runner(value, cells: list[dict], contacts: list[str], concurrency: dict[str, int]):
    targets, zero_cell, lock = {cell["cell_id"]: cell["target"] for cell in cells}, cells[0]["cell_id"], threading.Lock()

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        assert json.loads(schema_path.read_bytes())["required"] == ["scores", "evidence", "coverage"]
        cell_id = output_dir.name
        with lock:
            concurrency["active"] += 1
            concurrency["maximum"] = max(concurrency["maximum"], concurrency["active"])
        try:
            time.sleep(0.01)
            scores = {dimension: 0.0 if cell_id == zero_cell else float(targets[cell_id][dimension]) + 0.25 for dimension in value.DIMS}
            structured = {"scores": scores, "evidence": {dimension: "Fixture evidence is present." for dimension in value.DIMS}, "coverage": {dimension: False for dimension in value.DIMS}}
            envelope = {"modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}}, "num_turns": 1, "requestId": f"request-{cell_id}", "sessionId": f"session-{cell_id}", "stopReason": "end_turn", "structuredOutput": structured, "text": json.dumps(structured, sort_keys=True, separators=(",", ":")), "thought": "", "total_cost_usd": 0.0, "total_cost_usd_ticks": 0, "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4}}
            response = json.dumps(envelope, ensure_ascii=False, indent=2).encode()
            responses = output_dir / "responses"
            responses.mkdir()
            (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
            before_contact()
            with lock:
                contacts.append(cell_id)
            (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
            return {"native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(), "native_response_bytes": response, "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False}, "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False}}
        finally:
            with lock:
                concurrency["active"] -= 1

    return run


def test_execute_once_admits_full_numeric_all_zero_false_coverage_and_recomputes_unequal_group_mae(tmp_path: Path):
    value, args = module(), common(tmp_path)
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT, recovered_descendant=RECOVERED)
    value.prepare_all(**args)
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    results = value.execute_wave(**args, allow_remote=True, runner=native_runner(value, schedule["cells"], contacts, concurrency))
    assert len(results) == 88
    assert set(contacts) == {cell["cell_id"] for cell in schedule["cells"]}
    assert 2 <= concurrency["maximum"] <= 10
    assert all(result["process_launches"] == 1 for result in results)

    report = value.report(**report_args(args))
    assert len(report["cells"]) == report["unique_request_ids"] == report["unique_session_ids"] == 88
    assert any(all(cell["scores"][dimension] == 0.0 for dimension in value.DIMS) for cell in report["cells"])
    assert all(math.isfinite(cell["scores"][dimension]) and cell["coverage"][dimension] is False for cell in report["cells"] for dimension in value.DIMS)
    expected: dict[str, float] = {}
    for candidate in (CHILD20, DESCENDANT):
        groups: dict[str, list[float]] = defaultdict(list)
        for cell in report["cells"]:
            if cell["candidate_id"] == candidate:
                groups[cell["prompt_group_id"]].append(sum(abs(cell["scores"][dimension] - cell["target"][dimension]) for dimension in value.DIMS) / len(value.DIMS))
        expected[candidate] = sum(sum(errors) / len(errors) for errors in groups.values()) / len(groups)
    observed = {row["candidate_id"]: row["equal_group_mean_item_mae"] for row in report["metrics"]}
    assert observed == pytest.approx(expected)
    assert all(row["item_count"] == 44 and row["group_count"] == 22 and len(row["per_group_mean_item_mae"]) == 22 for row in report["metrics"])

    before = {path.relative_to(args["output_root"]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in args["output_root"].rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="no resend|terminal evidence|root inventory"):
        value.execute_wave(**args, allow_remote=True, runner=lambda **_kwargs: pytest.fail("resend invoked runner"))
    after = {path.relative_to(args["output_root"]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in args["output_root"].rglob("*") if path.is_file()}
    assert after == before

    original_adapted = value._adapted
    for fault, message in (("identity", "identity"), ("schema", "schema")):
        @contextmanager
        def altered_adapted(schedule_value, _fault=fault):
            with original_adapted(schedule_value) as v13:
                original_bound = v13.bound

                @contextmanager
                def altered_bound(*, schedule_value):
                    with original_bound(schedule_value=schedule_value) as (lifecycle, runtime, v9, v11):
                        admit = lifecycle.admit

                        def altered_admit(*inner_args, **inner_kwargs):
                            request, response, identity, settings = admit(*inner_args, **inner_kwargs)
                            envelope = json.loads(response)
                            if _fault == "identity":
                                envelope["requestId"] = ""
                            else:
                                envelope["structuredOutput"]["scores"].pop("Complexity")
                                envelope["text"] = json.dumps(envelope["structuredOutput"], sort_keys=True, separators=(",", ":"))
                            return request, value.canonical(envelope), identity, settings

                        lifecycle.admit = altered_admit
                        try:
                            yield lifecycle, runtime, v9, v11
                        finally:
                            lifecycle.admit = admit

                v13.bound = altered_bound
                try:
                    yield v13
                finally:
                    v13.bound = original_bound

        value._adapted = altered_adapted
        try:
            with pytest.raises(ValueError, match=message):
                value.report(**report_args(args))
        finally:
            value._adapted = original_adapted
