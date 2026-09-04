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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v13-train-expansion-v1"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
V11_ITEM_IDS = {
    "item-09006dab15b970e6",
    "item-f0124faa5a62734e",
    "item-b5161cbf50b87beb",
    "item-8c65749a245496a2",
}
ACK = "a" * 64


def module():
    path = PACKAGE / "study.py"
    if not path.is_file():
        pytest.skip("V13 source is not present yet")
    spec = importlib.util.spec_from_file_location("v13_train_expansion", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def route_provider():
    now = datetime.now(timezone.utc)
    route = {
        "name": "grok-build-grok-4.6",
        "model": "grok-4.6",
        "reported_model": "grok-4.6-build",
        "adapter": "grok_exec",
        "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription",
        "account_class": "subscription",
        "identity_evidence": "requested_only",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "trusted": True,
        "reasoning_effort": "high",
        "grok_command": ["fixture"],
        "grok_command_identity": {"version": 1, "artifacts": []},
        "cli_version_identity": {"version": 1, "artifacts": []},
        "grok_cli_version": "fixture",
        "subscription_receipt_hash": "2" * 64,
        "cost_evidence": {
            "allowance_state": "available",
            "checked_at": (now - timedelta(seconds=1)).isoformat(),
            "evidence_hash": "1" * 64,
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "kind": "subscription_included",
            "version": 1,
        },
        "allowed_payload_classes": ["public_repo"],
        "timeout_seconds": 1.0,
    }
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    evidence = {
        "route_name": route["name"],
        "route_sha256": hashlib.sha256(canonical(route)).hexdigest(),
        "cost_evidence_hash": route["cost_evidence"]["evidence_hash"],
        "subscription_receipt_hash": route["subscription_receipt_hash"],
        "grok_cli_version": route["grok_cli_version"],
        "cli_version_identity_sha256": hashlib.sha256(canonical(route["cli_version_identity"])).hexdigest(),
        "grok_command_identity_sha256": hashlib.sha256(canonical(route["grok_command_identity"])).hexdigest(),
        "registry_sha256": "3" * 64,
    }
    return lambda _queue: (route, evidence)


def common(tmp_path: Path) -> dict:
    return {
        "output_root": tmp_path / "output",
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
        "route_provider": route_provider(),
    }


def test_schedule_is_exact_44_item_88_cell_train_expansion_with_target_free_payloads():
    value = module()
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    cells = schedule["cells"]
    assert len(cells) == 88
    assert {cell["candidate_id"] for cell in cells} == {BASELINE, CHILD20}
    assert {cell["partition"] for cell in cells} == {"train"}
    item_ids = {cell["item_id"] for cell in cells}
    assert len(item_ids) == 44 and not item_ids.intersection(V11_ITEM_IDS)
    grouped: dict[str, set[str]] = defaultdict(set)
    pairs: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        grouped[cell["prompt_group_id"]].add(cell["item_id"])
        pairs[cell["item_id"]].add(cell["candidate_id"])
        payload = base64.b64decode(cell["payload_base64"], validate=True)
        assert value.sha256(payload) == cell["payload_sha256"]
        assert "target" not in json.loads(payload)
        assert cell["endpoint_payload_sha256s"]["grok_primary"] == cell["endpoint_payload_sha256s"]["sol_later"] == cell["payload_sha256"]
    assert len(grouped) == 22
    assert sorted(map(len, grouped.values())) == [1] * 12 + [2] * 3 + [3] * 3 + [4] * 3 + [5]
    assert all(candidates == {BASELINE, CHILD20} for candidates in pairs.values())


def test_prepare_all_is_provider_free_for_exact_88_cell_train_expansion(tmp_path: Path):
    value = module()
    result = value.prepare_all(**common(tmp_path))
    assert result["provider_calls_made"] == result["process_launches"] == 0
    assert result["logical_cells"] == len(result["prepared_cells"]) == 88


def test_frozen_short_story_is_admitted_but_pointer_tampering_stops_before_native_contact(tmp_path: Path):
    value, args = module(), common(tmp_path)
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    short_cell = next(
        cell for cell in schedule["cells"]
        if len(json.loads(base64.b64decode(cell["payload_base64"]))["writing"]["story"]) < 120
    )
    value.prepare_all(**args)
    payload_path = args["output_root"] / short_cell["cell_id"] / "outbound-payload.json"
    payload = json.loads(payload_path.read_bytes())
    payload["writing"]["story"] = "x"
    payload_path.write_bytes(value.canonical(payload))
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    with pytest.raises(ValueError, match="prepared binding drifted"):
        value.execute_one(**args, cell_id=short_cell["cell_id"], allow_remote=True, runner=native_runner(value, schedule["cells"], contacts, concurrency))
    assert contacts == []


def native_runner(value, cells: list[dict], contacts: list[str], concurrency: dict[str, int], *, fault: str | None = None):
    targets = {cell["cell_id"]: cell["target"] for cell in cells}
    lock = threading.Lock()

    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        assert json.loads(schema_path.read_bytes())["required"] == ["scores", "evidence", "coverage"]
        cell_id = output_dir.name
        with lock:
            concurrency["active"] += 1
            concurrency["maximum"] = max(concurrency["maximum"], concurrency["active"])
        try:
            time.sleep(0.01)
            target = targets[cell_id]
            scores = {
                dimension: 0.0 if cell_id.endswith("0") else float(target[dimension]) + 0.25
                for dimension in value.DIMS
            }
            structured = {
                "scores": scores,
                "evidence": {dimension: "Fixture evidence is present." for dimension in value.DIMS},
                "coverage": {dimension: dimension != "Empathy" for dimension in value.DIMS},
            }
            if fault == "schema":
                structured["scores"].pop("Complexity")
            response_value = {
                "modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}},
                "num_turns": 1,
                "requestId": "" if fault == "identity" else f"request-{cell_id}",
                "sessionId": f"session-{cell_id}",
                "stopReason": "end_turn",
                "structuredOutput": structured,
                "text": json.dumps(structured, sort_keys=True, separators=(",", ":")),
                "thought": None if fault == "thought" else "",
                "total_cost_usd": 0.0,
                "total_cost_usd_ticks": 0,
                "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4},
            }
            response = json.dumps(response_value, ensure_ascii=False, indent=2).encode()
            responses = output_dir / "responses"
            responses.mkdir()
            (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
            before_contact()
            with lock:
                contacts.append(cell_id)
            (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
            return {
                "native_request_bytes": json.dumps({"prompt": prompt.decode()}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(),
                "native_response_bytes": response,
                "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": response_value["requestId"], "session_id": response_value["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
                "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False},
            }
        finally:
            with lock:
                concurrency["active"] -= 1

    return run


def report_args(args: dict) -> dict:
    return {key: args[key] for key in args if key not in {"queue_root", "route_provider"}}


def test_execute_88_admits_finite_all_zero_scores_and_reports_equal_group_item_mae(tmp_path: Path):
    value, args = module(), common(tmp_path)
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    value.prepare_all(**args)
    contacts: list[str] = []
    concurrency = {"active": 0, "maximum": 0}
    results = value.execute_wave(**args, allow_remote=True, runner=native_runner(value, schedule["cells"], contacts, concurrency))
    assert len(results) == 88
    assert set(contacts) == {cell["cell_id"] for cell in schedule["cells"]}
    assert 2 <= concurrency["maximum"] <= 10
    assert all(result["process_launches"] == 1 and result["native_endpoint_contact_cardinality"] == "unproven" for result in results)

    report = value.report(**report_args(args))
    assert len(report["cells"]) == report["unique_request_ids"] == report["unique_session_ids"] == 88
    assert any(all(cell["scores"][dimension] == 0.0 for dimension in value.DIMS) for cell in report["cells"])
    assert all(math.isfinite(cell["scores"][dimension]) for cell in report["cells"] for dimension in value.DIMS)
    assert all(cell["coverage"]["Empathy"] is False for cell in report["cells"])

    expected: dict[str, float] = {}
    for candidate in (BASELINE, CHILD20):
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

    original_bound = value.bound
    for fault, message in (("identity", "identity"), ("schema", "schema"), ("thought", "thought")):
        @contextmanager
        def altered_bound(*, schedule_value, _fault=fault):
            with original_bound(schedule_value=schedule_value) as (lifecycle, runtime, v9, v11):
                admit = lifecycle.admit

                def altered_admit(*inner_args, **inner_kwargs):
                    request, response, identity, settings = admit(*inner_args, **inner_kwargs)
                    envelope = json.loads(response)
                    if _fault == "identity":
                        envelope["requestId"] = ""
                    elif _fault == "schema":
                        envelope["structuredOutput"]["scores"].pop("Complexity")
                        envelope["text"] = json.dumps(envelope["structuredOutput"], sort_keys=True, separators=(",", ":"))
                    else:
                        envelope["thought"] = None
                    return request, value.canonical(envelope), identity, settings

                lifecycle.admit = altered_admit
                try:
                    yield lifecycle, runtime, v9, v11
                finally:
                    lifecycle.admit = admit

        value.bound = altered_bound
        try:
            with pytest.raises(ValueError, match=message):
                value.report(**report_args(args))
        finally:
            value.bound = original_bound
