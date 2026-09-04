from __future__ import annotations

import base64
import copy
import csv
import hashlib
import importlib.util
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v16-comparative-train-v1" / "study.py"
V15 = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v15-rank-discrimination-v1" / "study.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
CONTRACT = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")


def module():
    if not SOURCE.is_file():
        pytest.skip("V16 comparative study is unavailable")
    spec = importlib.util.spec_from_file_location("v16_comparative_train", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def v15_module():
    spec = importlib.util.spec_from_file_location("v16_test_v15", V15)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def source_paths():
    return {"split_manifest": SPLIT, "hanna_csv": CSV, "successor_contract": CONTRACT}


def _keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def _item_answer(value, item_id: str, score: float = 3.0):
    return {
        "item_id": item_id,
        "scores": {dimension: score for dimension in value.DIMS},
        "evidence": {dimension: "Fixture evidence." for dimension in value.DIMS},
        "coverage": {dimension: False for dimension in value.DIMS},
    }


def _measurements(value, schedule):
    rows = [*schedule["reused_direct_cells"], *schedule["cells"]]
    measurements = {}
    for row in rows:
        condition = row["condition"]
        if condition == value.DIRECT:
            item = _item_answer(value, row["item_id"])
            answer = {key: item[key] for key in ("scores", "evidence", "coverage")}
        else:
            score = 1.0 if condition == value.FORWARD else 5.0
            answer = {"items": [_item_answer(value, item_id, score) for item_id in row["item_ids"]]}
        measurements[row["cell_id"]] = {"condition": condition, "answer": answer, "provenance": {"endpoint": "fixture"}}
    return measurements


def test_schedule_binds_real_fifty_item_panel_reuse_and_endpoint_payload_parity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value, prior = module(), v15_module()
    schedule = value.schedule(**source_paths())
    assert schedule["geometry"] == {"comparative_batches": 10, "direct_new": 29, "direct_reused": 21, "groups": 5, "items": 50, "logical_cells": 39, "max_concurrency": 10}
    assert len(schedule["panel"]) == len({row["item_id"] for row in schedule["panel"]}) == 50
    panel_by_group: dict[str, list[dict]] = defaultdict(list)
    for row in schedule["panel"]:
        panel_by_group[row["prompt_group_id"]].append(row)
    original = prior._train48_items(**source_paths())
    original_counts = Counter(row["prompt_group_id"] for row in original)
    selected_groups = [group for group, _count in sorted(original_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:5]]
    assert [row["prompt_group_id"] for row in schedule["groups"]] == selected_groups
    assert [original_counts[group] for group in selected_groups] == [5, 4, 4, 4, 4]
    assert sorted(map(len, panel_by_group.values())) == [10] * 5
    assert sum(row["historical_v15_direct"] for row in schedule["panel"]) == 21
    assert len(schedule["reused_direct_cells"]) == 21
    assert len(schedule["cells"]) == 39
    assert Counter(row["condition"] for row in schedule["cells"]) == {value.DIRECT: 29, value.FORWARD: 5, value.REVERSE: 5}

    prior_schedule = prior.schedule(**source_paths())
    prior_direct = {row["cell_id"]: row for row in prior_schedule["cells"] if row["condition"] == prior.DIRECT}
    panel = {row["item_id"]: row for row in schedule["panel"]}
    for row in schedule["reused_direct_cells"]:
        source = prior_direct[row["source_cell_id"]]
        assert row["payload_base64"] == source["payload_base64"]
        assert row["payload_sha256"] == source["payload_sha256"]
        assert row["source_binding_sha256"] == panel[row["item_id"]]["source_binding_sha256"]

    batches: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in schedule["cells"]:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert value.sha256(payload) == row["payload_sha256"]
        assert row["endpoint_payload_sha256s"] == {"grok_primary": row["payload_sha256"], "sol_later": row["payload_sha256"]}
        outbound = json.loads(payload)
        assert "target" not in set(_keys(outbound))
        assert set(outbound["writing"]) == {"prompt", "story"}
        if row["condition"] in {value.FORWARD, value.REVERSE}:
            batches[row["prompt_group_id"]][row["condition"]] = row
            serial = json.loads(outbound["writing"]["story"])
            assert [item["item_id"] for item in serial] == row["item_ids"]
            assert all(set(item) == {"item_id", "story"} for item in serial)
            assert row["source_binding_sha256s"] == {item_id: panel[item_id]["source_binding_sha256"] for item_id in row["item_ids"]}
            schema = outbound["response_schema"]
            item_schema = schema["properties"]["items"]["items"]
            assert schema["additionalProperties"] is item_schema["additionalProperties"] is False
            assert item_schema["required"] == ["item_id", "scores", "evidence", "coverage"]
            for dimension in value.DIMS:
                assert item_schema["properties"]["scores"]["properties"][dimension] == {"type": "number", "minimum": 1, "maximum": 5}
                assert item_schema["properties"]["evidence"]["properties"][dimension] == {"type": "string", "minLength": 1, "maxLength": 320}
                assert item_schema["properties"]["coverage"]["properties"][dimension] == {"type": "boolean"}
            instruction = outbound["profile"]["condition"]["instruction"].lower()
            assert "ten stories" in instruction and "decimal" in instruction and "input order" in instruction
    assert set(batches) == set(panel_by_group)
    for pair in batches.values():
        assert set(pair) == {value.FORWARD, value.REVERSE}
        assert pair[value.REVERSE]["item_ids"] == list(reversed(pair[value.FORWARD]["item_ids"]))
        assert set(pair[value.FORWARD]["item_ids"]) == {row["item_id"] for row in panel_by_group[pair[value.FORWARD]["prompt_group_id"]]}

    frozen_train = prior._train48_items(**source_paths())
    selected_group = selected_groups[0]
    rows = list(csv.DictReader(CSV.read_text(encoding="utf-8-sig").splitlines()))
    systems: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        group = "prompt-" + hashlib.sha256(row["Prompt"].encode("utf-8")).hexdigest()[:16]
        if group == selected_group and row["Model"] != "Human":
            systems[(row["Story ID"], row["Model"])].append(row)
    source_key, duplicate_key = sorted(systems)[:2]
    assert len(systems) == 10 and len(systems[source_key]) == len(systems[duplicate_key]) == 3
    for row in rows:
        if (row["Story ID"], row["Model"]) == duplicate_key:
            row["Story ID"], row["Model"] = source_key
    broken_csv = tmp_path / "duplicate-system.csv"
    with broken_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    monkeypatch.setattr(prior, "_train48_items", lambda **_kwargs: frozen_train)
    monkeypatch.setattr(value, "_v15", lambda: prior)
    with pytest.raises(ValueError, match="lacks ten non-Human original systems"):
        value._panel(split_manifest=SPLIT, hanna_csv=broken_csv, successor_contract=CONTRACT)


def test_batch_answer_accepts_decimal_json_and_rejects_identity_or_numeric_drift():
    value = module()
    schedule = value.schedule(**source_paths())
    batch = next(row for row in schedule["cells"] if row["condition"] == value.FORWARD)
    expected = batch["item_ids"]
    answer = {"items": [_item_answer(value, item_id, 3.0) for item_id in expected]}
    parsed = value.validate_answer(value.FORWARD, answer, expected_item_ids=expected)
    assert [row["item_id"] for row in parsed["items"]] == expected
    assert all(type(row["scores"][dimension]) is float and row["scores"][dimension] == 3.0 for row in parsed["items"] for dimension in value.DIMS)

    duplicate = copy.deepcopy(answer)
    duplicate["items"][-1]["item_id"] = duplicate["items"][0]["item_id"]
    with pytest.raises(ValueError, match="membership or order"):
        value.validate_answer(value.FORWARD, duplicate, expected_item_ids=expected)
    missing = {"items": answer["items"][:-1]}
    with pytest.raises(ValueError, match="exactly ten"):
        value.validate_answer(value.FORWARD, missing, expected_item_ids=expected)
    nonfinite = copy.deepcopy(answer)
    nonfinite["items"][0]["scores"][value.DIMS[0]] = float("nan")
    with pytest.raises(ValueError, match="finite real"):
        value.validate_answer(value.FORWARD, nonfinite, expected_item_ids=expected)
    boolean = copy.deepcopy(answer)
    boolean["items"][0]["scores"][value.DIMS[0]] = True
    with pytest.raises(ValueError, match="finite real"):
        value.validate_answer(value.FORWARD, boolean, expected_item_ids=expected)
    reversed_order = {"items": list(reversed(answer["items"]))}
    with pytest.raises(ValueError, match="membership or order"):
        value.validate_answer(value.FORWARD, reversed_order, expected_item_ids=expected)
    direct = {key: value_ for key, value_ in _item_answer(value, "unused", 3.0).items() if key != "item_id"}
    assert value.validate_answer(value.DIRECT, direct)["scores"] == {dimension: 3.0 for dimension in value.DIMS}
    foreign = {**direct, "foreign": "field"}
    with pytest.raises(ValueError, match="direct answer shape"):
        value.validate_answer(value.DIRECT, foreign)
    fractional = copy.deepcopy(direct)
    fractional["scores"][value.DIMS[0]] = 3.5
    with pytest.raises(ValueError, match="finite real"):
        value.validate_answer(value.DIRECT, fractional)
    long_direct = copy.deepcopy(direct)
    long_direct["evidence"][value.DIMS[0]] = "x" * 321
    assert value.validate_answer(value.DIRECT, long_direct)["evidence"][value.DIMS[0]] == "x" * 321
    long_batch = copy.deepcopy(answer)
    long_batch["items"][0]["evidence"][value.DIMS[0]] = "x" * 321
    with pytest.raises(ValueError, match="evidence"):
        value.validate_answer(value.FORWARD, long_batch, expected_item_ids=expected)


def test_arithmetic_uses_both_orders_and_requires_every_scheduled_measurement():
    value = module()
    schedule = value.schedule(**source_paths())
    measurements = _measurements(value, schedule)
    analysis = value.analyze(schedule, measurements)
    assert set(analysis["metrics"]) == {"direct_historical_noncontemporaneous", value.FORWARD, value.REVERSE, "per_story_mean_orders"}
    target_rows = schedule["panel"]
    expected_fixed_three_mae = {
        dimension: sum(abs(3.0 - float(row["target"][dimension])) for row in target_rows) / len(target_rows)
        for dimension in value.DIMS
    }
    averaged = analysis["metrics"]["per_story_mean_orders"]["dimensions"]
    assert all(averaged[dimension]["global_item_50_mae"] == pytest.approx(expected_fixed_three_mae[dimension]) for dimension in value.DIMS)
    assert all(values["fixed_three_spearman"] is None for values in averaged.values())
    assert all(values["hanna_compatible_retained_prompt_count"] == 0 and values["hanna_compatible_dropped_prompt_count"] == 5 for values in averaged.values())
    assert analysis["metrics"]["per_story_mean_orders"]["strict_full_five_prompt_complete"] is False
    assert analysis["metrics"]["per_story_mean_orders"]["strict_full_five_prompt_macro_six"] is None

    missing = dict(measurements)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="exactly all reused and new"):
        value.analyze(schedule, missing)


def test_hanna_compatible_prompt_drop_is_labeled_while_strict_primary_stays_undefined():
    value = module()
    groups = [f"group-{index}" for index in range(5)]
    rows = []
    for index, group in enumerate(groups):
        for score, target in ((1.0, 1.0), (5.0, 5.0)):
            rows.append(
                {
                    "item_id": f"{group}-{score}",
                    "prompt_group_id": group,
                    "scores": {dimension: 3.0 if index == 0 else score for dimension in value.DIMS},
                    "target": {dimension: target for dimension in value.DIMS},
                }
            )
    metrics = value._dimension_metrics(rows, groups)
    assert metrics["hanna_compatible_macro_six"] == pytest.approx(1.0)
    assert metrics["strict_full_five_prompt_complete"] is False
    assert metrics["strict_full_five_prompt_macro_six"] is None
    for dimension in value.DIMS:
        values = metrics["dimensions"][dimension]
        assert values["hanna_compatible_mean_defined_prompt_spearman"] == pytest.approx(1.0)
        assert values["hanna_compatible_retained_prompt_ids"] == groups[1:]
        assert values["hanna_compatible_dropped_prompt_ids"] == [groups[0]]
        assert values["hanna_compatible_retained_prompt_count"] == 4
        assert values["hanna_compatible_dropped_prompt_count"] == 1
