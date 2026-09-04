from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v15-rank-discrimination-v1" / "study.py"
V13_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v13_train_expansion_v1.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
ACK = "a" * 64


def module():
    if not SOURCE.is_file():
        pytest.skip("V15 rank-discrimination source is unavailable")
    spec = importlib.util.spec_from_file_location("v15_rank_discrimination", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def _keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def _route_provider():
    spec = importlib.util.spec_from_file_location("v15_v13_route_fixture", V13_TEST)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value.route_provider()


def _args(tmp_path: Path):
    return {
        "output_root": tmp_path / "output",
        "queue_root": tmp_path / "queue",
        "authorization_acknowledgement_sha256": ACK,
        "split_manifest": SPLIT,
        "hanna_csv": CSV,
        "successor_contract": CONTRACT,
        "route_provider": _route_provider(),
    }


def _response_helper(value):
    v13 = value.load(value.V13, value.V13_COMMIT, value.V13_SHA256, "v15_response_test_v13")
    reconcile = v13.load(v13.RECONCILE, v13.RECONCILE_COMMIT, v13.RECONCILE_SHA256, "v15_response_test_helper")
    return reconcile.helper()


def _native_envelope(value):
    structured = {
        "scores": {dimension: 3 for dimension in value.DIMS},
        "evidence": {dimension: "Fixture evidence." for dimension in value.DIMS},
        "coverage": {dimension: False for dimension in value.DIMS},
    }
    return {
        "modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}},
        "num_turns": 1,
        "requestId": "request-fixture",
        "sessionId": "session-fixture",
        "stopReason": "end_turn",
        "structuredOutput": structured,
        "text": json.dumps(structured, sort_keys=True, separators=(",", ":")),
        "thought": "",
        "total_cost_usd": 0.0,
        "total_cost_usd_ticks": 0,
        "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4},
    }


def _mismatched_native_text(envelope):
    text = copy.deepcopy(envelope["structuredOutput"])
    text["scores"][next(iter(text["scores"]))] = 4
    envelope["text"] = json.dumps(text, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize(
    "mutate, message",
    [
        (
            lambda envelope: envelope["modelUsage"].update(
                {"wrong-model": envelope["modelUsage"].pop("grok-4.6-build")}
            ),
            "model usage",
        ),
        (lambda envelope: envelope["modelUsage"]["grok-4.6-build"].update({"modelCalls": 2}), "model usage"),
        (lambda envelope: envelope.update({"text": "not the structured response"}), "native response text|identity or structured output"),
        (_mismatched_native_text, "identity or structured output"),
        (lambda envelope: envelope.update({"total_cost_usd": 0.1}), "cost or thought"),
    ],
    ids=("wrong_model_usage_key", "multiple_model_calls", "malformed_native_text", "mismatched_native_text", "nonzero_cost"),
)
def test_response_rejects_native_transport_drift(mutate, message):
    value = module()
    helper = _response_helper(value)
    route = {"reported_model": "grok-4.6-build"}
    valid = _native_envelope(value)
    assert value._response(helper, json.dumps(valid, separators=(",", ":")).encode("utf-8"), route, value.DIRECT)[1] == {
        dimension: 3.0 for dimension in value.DIMS
    }
    envelope = copy.deepcopy(valid)
    mutate(envelope)
    with pytest.raises(ValueError, match=message):
        value._response(helper, json.dumps(envelope, separators=(",", ":")).encode("utf-8"), route, value.DIRECT)


def test_schedule_is_train48_paired_target_free_and_order_balanced():
    value = module()
    schedule = value.schedule(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    cells = schedule["cells"]
    assert schedule["geometry"] == {"conditions": 2, "grok_cells": 96, "groups": 24, "items": 48, "max_concurrency": 10, "sol_cells": 0}
    assert len(cells) == len({cell["cell_id"] for cell in cells}) == 96
    assert {cell["condition"] for cell in cells} == {value.DIRECT, value.THRESHOLDS}
    assert {cell["partition"] for cell in cells} == {"train"}
    expected_items = value._train48_items(split_manifest=SPLIT, hanna_csv=CSV, successor_contract=CONTRACT)
    expected_group_sizes: dict[str, int] = defaultdict(int)
    for item in expected_items:
        expected_group_sizes[item["prompt_group_id"]] += 1
    paired: dict[str, list[dict]] = defaultdict(list)
    groups: dict[str, set[str]] = defaultdict(set)
    condition_group_sizes: dict[str, dict[str, int]] = {value.DIRECT: defaultdict(int), value.THRESHOLDS: defaultdict(int)}
    first_conditions: list[str] = []
    for index, cell in enumerate(cells):
        paired[cell["item_id"]].append(cell)
        groups[cell["prompt_group_id"]].add(cell["item_id"])
        condition_group_sizes[cell["condition"]][cell["prompt_group_id"]] += 1
        if index % 2 == 0:
            first_conditions.append(cell["condition"])
        payload = base64.b64decode(cell["payload_base64"], validate=True)
        assert value.sha256(payload) == cell["payload_sha256"]
        outbound = json.loads(payload)
        assert "target" not in set(_keys(outbound))
        assert cell["endpoint_payload_sha256s"] == {"grok_primary": cell["payload_sha256"], "sol_later": cell["payload_sha256"]}
    assert len(paired) == 48 and len(groups) == 24
    assert {group: len(items) for group, items in groups.items()} == expected_group_sizes
    assert condition_group_sizes[value.DIRECT] == condition_group_sizes[value.THRESHOLDS] == expected_group_sizes
    assert first_conditions.count(value.DIRECT) == first_conditions.count(value.THRESHOLDS) == 24
    for item_cells in paired.values():
        assert {cell["condition"] for cell in item_cells} == {value.DIRECT, value.THRESHOLDS}
        direct, ordinal = sorted(item_cells, key=lambda cell: cell["condition"])
        direct_payload = json.loads(base64.b64decode(direct["payload_base64"]))
        ordinal_payload = json.loads(base64.b64decode(ordinal["payload_base64"]))
        assert direct_payload["instruction"] == ordinal_payload["instruction"]
        assert direct_payload["writing"] == ordinal_payload["writing"]
        assert direct_payload["profile"]["shared_hanna_criterion_anchors"] == ordinal_payload["profile"]["shared_hanna_criterion_anchors"]
        assert direct["source_binding_sha256"] == ordinal["source_binding_sha256"]


def test_ordinal_projection_is_24_bit_monotonic_and_direct_zero_is_invalid():
    value = module()
    evidence = {dimension: "fixture evidence" for dimension in value.DIMS}
    coverage = {dimension: False for dimension in value.DIMS}
    all_false = {dimension: {key: False for key in value.THRESHOLD_KEYS} for dimension in value.DIMS}
    scores, projected_coverage, raw = value._validate_answer(
        value.THRESHOLDS, {"thresholds": all_false, "evidence": evidence, "coverage": coverage}
    )
    assert len(raw["raw_threshold_bits"]) * len(value.THRESHOLD_KEYS) == 24
    assert scores == {dimension: 1.0 for dimension in value.DIMS}
    assert projected_coverage == coverage
    nonmonotonic = {dimension: dict(bits) for dimension, bits in all_false.items()}
    nonmonotonic[value.DIMS[0]]["at_least_2"] = False
    nonmonotonic[value.DIMS[0]]["at_least_3"] = True
    with pytest.raises(ValueError, match="nonmonotonic"):
        value._validate_answer(value.THRESHOLDS, {"thresholds": nonmonotonic, "evidence": evidence, "coverage": coverage})
    with pytest.raises(ValueError, match="direct 1-5"):
        value._validate_answer(value.DIRECT, {"scores": {dimension: 0 for dimension in value.DIMS}, "evidence": evidence, "coverage": coverage})


def test_rank_metrics_keep_constant_dimensions_undefined_and_average_ties():
    value = module()
    cells = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for index in range(48):
        cell = {
            "item_id": f"item-{index:02d}",
            "scores": {dimension: 3.0 if dimension == value.DIMS[0] else float(index % 5 + 1) for dimension in value.DIMS},
            "target": {dimension: 3.0 if dimension == value.DIMS[0] else float(index % 5 + 1) for dimension in value.DIMS},
        }
        cells.append(cell)
        group = index if index < 12 else 12 + (index - 12) // 3
        groups[f"group-{group:02d}"].append(cell)
    metrics = value._rank_metrics(cells, groups)
    assert sorted(map(len, groups.values())) == [1] * 12 + [3] * 12
    assert value._rank([1.0, 1.0, 3.0]) == [1.5, 1.5, 3.0]
    assert set(metrics["item_48"]) == set(value.DIMS)
    assert metrics["item_48"][value.DIMS[0]] is None
    assert metrics["item_48_macro"] is None
    assert set(metrics["group_mean_24"]) == set(value.DIMS)


def _native_runner(value):
    def run(*, prompt: bytes, schema_path: Path, output_dir: Path, route, before_contact):
        payload = json.loads(prompt)
        condition = payload["profile"]["condition"]["kind"]
        assert json.loads(schema_path.read_bytes())["required"] == (["scores", "evidence", "coverage"] if condition == value.DIRECT else ["thresholds", "evidence", "coverage"])
        evidence = {dimension: "Fixture evidence." for dimension in value.DIMS}
        coverage = {dimension: False for dimension in value.DIMS}
        if condition == value.DIRECT:
            scores = {
                dimension: 1 + hashlib.sha256(prompt + dimension.encode("utf-8")).digest()[0] % 5
                for dimension in value.DIMS
            }
            structured = {"scores": scores, "evidence": evidence, "coverage": coverage}
        else:
            structured = {
                "thresholds": {
                    dimension: {key: False for key in value.THRESHOLD_KEYS} for dimension in value.DIMS
                },
                "evidence": evidence,
                "coverage": coverage,
            }
        envelope = {
            "modelUsage": {"grok-4.6-build": {"inputTokens": 2, "outputTokens": 2, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "modelCalls": 1, "costUSD": 0.0}},
            "num_turns": 1,
            "requestId": f"request-{output_dir.name}",
            "sessionId": f"session-{output_dir.name}",
            "stopReason": "end_turn",
            "structuredOutput": structured,
            "text": json.dumps(structured, sort_keys=True, separators=(",", ":")),
            "thought": "",
            "total_cost_usd": 0.0,
            "total_cost_usd_ticks": 0,
            "usage": {"input_tokens": 2, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "total_tokens": 4},
        }
        response = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
        responses = output_dir / "responses"
        responses.mkdir()
        (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
        before_contact()
        (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        return {
            "native_request_bytes": json.dumps({"prompt": prompt.decode("utf-8")}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
            "native_response_bytes": response,
            "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "native_endpoint_contact_cardinality": "unproven", "tools_enabled": False},
            "effective_settings": {"route_name": route["name"], "adapter": "grok_exec", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "tool_free_argv": ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"], "system_prompt_override": "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.", "sampler": {"batch_number": 1, "attempt_number": 1, "timeout_seconds": 1.0, "nonvisual_max_turns": 1}, "runner_prompt_artifact_sha256": value.sha256(prompt), "reasoning_attested": False},
        }

    return run


def test_provider_free_preparation_and_full_receipt_projection_keep_all_scores(tmp_path: Path):
    value, args = module(), _args(tmp_path)
    prepared = value.prepare_all(**args)
    assert prepared["study_id"] == value.STUDY_ID
    assert prepared["logical_cells"] == 96
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    assert len(prepared["prepared_cells"]) == 96
    prepared_records = [json.loads((args["output_root"] / cell_id / "prepared.json").read_text(encoding="utf-8")) for cell_id in prepared["prepared_cells"]]
    assert len({json.dumps(record["route"], sort_keys=True) for record in prepared_records}) == 1
    assert len({json.dumps(record["route_evidence"], sort_keys=True) for record in prepared_records}) == 1
    outcomes = value.execute_wave(**args, allow_remote=True, runner=_native_runner(value))
    assert len(outcomes) == 96
    report = value.report(**{key: args[key] for key in args if key not in {"queue_root", "route_provider"}})
    assert report["status"] == "complete_matched_96_cells"
    assert report["invalid_count"] == 0
    assert report["unique_request_ids"] == report["unique_session_ids"] == 96
    assert set(report["metrics"]) == set(report["rank_metrics"]) == {value.DIRECT, value.THRESHOLDS}
    assert report["interpretation"].startswith("TRAIN_only")
    assert all(math.isfinite(cell["scores"][dimension]) and cell["coverage"][dimension] is False for cell in report["cells"] for dimension in value.DIMS)
    assert all("native_response_sha256" in cell and "payload_sha256" in cell for cell in report["cells"])
    direct = [cell for cell in report["cells"] if cell["condition"] == value.DIRECT]
    ordinal = [cell for cell in report["cells"] if cell["condition"] == value.THRESHOLDS]
    assert len(direct) == len(ordinal) == 48
    assert all("raw_scores" in cell and all(1.0 <= score <= 5.0 for score in cell["scores"].values()) for cell in direct)
    assert all("raw_threshold_bits" in cell and all(score == 1.0 for score in cell["scores"].values()) for cell in ordinal)
    assert report["rank_metrics"][value.THRESHOLDS]["item_48_macro"] is None

    accepted = prepared["prepared_cells"][0]
    accepted_root = args["output_root"] / accepted
    before = {
        path.relative_to(accepted_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in accepted_root.rglob("*")
        if path.is_file()
    }
    with pytest.raises(ValueError, match="completed|normal|terminal|resend|claim"):
        value.execute_one(
            **args,
            cell_id=accepted,
            allow_remote=True,
            runner=lambda **_kwargs: pytest.fail("accepted cell was resent"),
        )
    after = {
        path.relative_to(accepted_root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in accepted_root.rglob("*")
        if path.is_file()
    }
    assert after == before

    prepared_path = accepted_root / "prepared.json"
    original = prepared_path.read_bytes()
    try:
        for field, changed in (("route", {"drift": "route"}), ("route_evidence", {"drift": "evidence"})):
            record = json.loads(original)
            record[field] = changed
            prepared_path.write_bytes(value.canonical(record))
            rejected = value.report(**{key: args[key] for key in args if key not in {"queue_root", "route_provider"}})
            assert rejected["status"] == "invalid_or_incomplete_no_full_panel_claim"
            assert rejected["invalid_count"] >= 1
            assert any(cell["cell_id"] == accepted for cell in rejected["invalid_cells"])
            prepared_path.write_bytes(original)
    finally:
        prepared_path.write_bytes(original)
