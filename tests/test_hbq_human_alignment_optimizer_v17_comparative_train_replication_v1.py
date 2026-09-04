from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v17-comparative-train-replication-v1"
SOURCE = PACKAGE / "study.py"
V15 = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v15-rank-discrimination-v1" / "study.py"
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
SUCCESSOR = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
EXPECTED_V17_GROUPS = (
    "prompt-c85edd8245f2bf73",
    "prompt-ea26ed67b3d13cb8",
    "prompt-3ea05aae03d4b979",
    "prompt-6b7fff0c3794370c",
    "prompt-933b864147df69bd",
)


def module():
    if not SOURCE.is_file():
        pytest.skip("V17 replication study is unavailable")
    spec = importlib.util.spec_from_file_location("v17_comparative_train_replication", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def v15_module():
    spec = importlib.util.spec_from_file_location("v17_test_v15", V15)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def source_paths():
    return {"split_manifest": SPLIT, "hanna_csv": CSV, "successor_contract": SUCCESSOR}


def analysis_paths(endpoint: str = "grok_primary"):
    return {"expected_endpoint": endpoint, **source_paths()}


def _keys(value):
    if isinstance(value, dict):
        yield from value
        for child in value.values():
            yield from _keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _keys(child)


def _item_answer(value, item_id: str, score: float) -> dict[str, object]:
    return {
        "item_id": item_id,
        "scores": {dimension: score for dimension in value.DIMS},
        "evidence": {dimension: "Fixture evidence." for dimension in value.DIMS},
        "coverage": {dimension: False for dimension in value.DIMS},
    }


def _measurements(value, schedule, endpoint: str = "grok_primary"):
    measurements = {}
    for row in [*schedule["reused_direct_cells"], *schedule["cells"]]:
        condition = row["condition"]
        if condition == value.DIRECT:
            item = _item_answer(value, row["item_id"], 3.0)
            answer = {key: item[key] for key in ("scores", "evidence", "coverage")}
        else:
            score = 1.0 if condition == value.FORWARD else 5.0
            answer = {"items": [_item_answer(value, item_id, score) for item_id in row["item_ids"]]}
        measurements[row["cell_id"]] = {
            "condition": condition,
            "answer": answer,
            "provenance": {
                "cell_id": row["cell_id"],
                "payload_sha256": row["payload_sha256"],
                "endpoint": endpoint,
            },
        }
    return measurements


def test_pinned_predecessors_and_contract_are_exact_git_blobs():
    value = module()
    assert value.V16_SHA256 == "8e24c0e0469339b3ad0a168bfb4aa5d4532c9cfea85a95d72764dc30037c34aa"
    assert value.V16_CONTRACT_SHA256 == "3d0aaee0e4e37e73d50cbd37969f006ac8b90deeebd74caa9512d323c94d7eb8"
    assert value._v16().V15_SHA256 == "4afeaff679efaf37e702c08841eb30a3317693e677ecfc3ded4dbb4ae4710caf"
    for path, digest, commit in ((value.V16, value.V16_SHA256, value.V16_COMMIT), (value.V16_CONTRACT, value.V16_CONTRACT_SHA256, value.V16_CONTRACT_COMMIT)):
        raw = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        pinned = subprocess.run(["git", "-C", str(ROOT), "show", f"{commit}:{relative}"], capture_output=True, check=True).stdout
        assert hashlib.sha256(raw).hexdigest() == digest
        assert pinned == raw
    assert value.contract()["geometry"] == {
        "comparative_batches": 10,
        "direct_new": 38,
        "direct_reused": 12,
        "groups": 5,
        "items": 50,
        "logical_cells": 48,
        "max_concurrency": 10,
    }


def test_next_five_selection_schedule_and_endpoint_payloads_are_frozen_train_only():
    value, prior = module(), v15_module()
    schedule = value.schedule(**source_paths())
    original = prior._train48_items(**source_paths())
    counts = Counter(row["prompt_group_id"] for row in original)
    ordered = [group for group, _count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]
    assert tuple(ordered[:5]) == tuple(schedule["source"]["v16_predecessor_groups"])
    assert tuple(ordered[5:10]) == EXPECTED_V17_GROUPS
    assert tuple(row["prompt_group_id"] for row in schedule["groups"]) == EXPECTED_V17_GROUPS
    assert [counts[group] for group in ordered[:10]] == [5, 4, 4, 4, 4, 3, 3, 2, 2, 2]
    assert {row["partition"] for row in schedule["groups"]} == {"train"}
    assert {row["partition"] for row in schedule["panel"] if "partition" in row} <= {"train"}
    assert schedule["authority"] == value.contract()["authority"]
    assert all(schedule["authority"][key] == "none" for key in ("confirmation", "generalization", "promotion", "runtime", "selection"))
    assert schedule["authority"]["endpoint_pooling"] == "forbidden"
    assert len(schedule["panel"]) == len({row["item_id"] for row in schedule["panel"]}) == 50
    assert sum(row["historical_v15_direct"] for row in schedule["panel"]) == 12
    assert len(schedule["reused_direct_cells"]) == 12
    assert len(schedule["cells"]) == 48
    assert Counter(row["condition"] for row in schedule["cells"]) == {value.DIRECT: 38, value.FORWARD: 5, value.REVERSE: 5}
    prior_direct = {
        row["cell_id"]: row
        for row in prior.schedule(**source_paths())["cells"]
        if row["condition"] == value.DIRECT
    }
    for row in schedule["reused_direct_cells"]:
        source = prior_direct[row["source_cell_id"]]
        assert row["payload_base64"] == source["payload_base64"]
        assert row["payload_sha256"] == source["payload_sha256"]
        assert row["reuse_provenance"]["v15_cell_id"] == source["cell_id"]

    panel_by_group = defaultdict(list)
    for row in schedule["panel"]:
        panel_by_group[row["prompt_group_id"]].append(row)
    assert set(panel_by_group) == set(EXPECTED_V17_GROUPS)
    assert sorted(map(len, panel_by_group.values())) == [10] * 5
    all_cells = [*schedule["reused_direct_cells"], *schedule["cells"]]
    assert len(all_cells) == 60
    batches = defaultdict(dict)
    for row in all_cells:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert value.sha256(payload) == row["payload_sha256"]
        assert row["endpoint_payload_sha256s"] == {"grok_primary": row["payload_sha256"], "sol_later": row["payload_sha256"]}
        outbound = json.loads(payload)
        assert "target" not in set(_keys(outbound))
        if row["condition"] in {value.FORWARD, value.REVERSE}:
            batches[row["prompt_group_id"]][row["condition"]] = row
            serial = json.loads(outbound["writing"]["story"])
            assert [item["item_id"] for item in serial] == row["item_ids"]
            assert all(set(item) == {"item_id", "story"} for item in serial)
    for group, pair in batches.items():
        assert set(pair) == {value.FORWARD, value.REVERSE}
        assert pair[value.REVERSE]["item_ids"] == list(reversed(pair[value.FORWARD]["item_ids"]))
        assert set(pair[value.FORWARD]["item_ids"]) == {row["item_id"] for row in panel_by_group[group]}


def test_schedule_tampering_and_missing_measurements_are_rejected():
    value = module()
    schedule = value.schedule(**source_paths())
    tampered = copy.deepcopy(schedule)
    tampered["cells"][0]["partition"] = "dev"
    with pytest.raises(ValueError, match="exact rederived V17 schedule"):
        value.analyze(tampered, _measurements(value, schedule), **analysis_paths())
    measurements = _measurements(value, schedule)
    measurements.pop(next(iter(measurements)))
    with pytest.raises(ValueError, match="exactly all reused and new"):
        value.analyze(schedule, measurements, **analysis_paths())
    measurements = _measurements(value, schedule)
    batch_id = next(row["cell_id"] for row in schedule["cells"] if row["condition"] == value.FORWARD)
    measurements[batch_id]["answer"]["items"][1]["item_id"] = measurements[batch_id]["answer"]["items"][0]["item_id"]
    with pytest.raises(ValueError, match="membership or order"):
        value.analyze(schedule, measurements, **analysis_paths())


def test_analysis_rejects_fabricated_schedule_or_cross_endpoint_measurement_provenance():
    value = module()
    schedule = value.schedule(**source_paths())
    fabricated = copy.deepcopy(schedule)
    fabricated["source"]["hanna_csv_sha256"] = "0" * 64
    fabricated["schedule_sha256"] = value.sha256({key: item for key, item in fabricated.items() if key != "schedule_sha256"})
    with pytest.raises(ValueError, match="exact rederived V17 schedule"):
        value.analyze(fabricated, _measurements(value, fabricated), **analysis_paths())
    swapped = _measurements(value, schedule)
    cell_id = next(iter(swapped))
    swapped[cell_id]["provenance"]["cell_id"] = "other-cell"
    with pytest.raises(ValueError, match="provenance does not bind"):
        value.analyze(schedule, swapped, **analysis_paths())
    mixed_endpoint = _measurements(value, schedule, endpoint="sol_later")
    with pytest.raises(ValueError, match="provenance does not bind"):
        value.analyze(schedule, mixed_endpoint, **analysis_paths())
    with pytest.raises(ValueError, match="endpoint is not recognized"):
        value.analyze(schedule, _measurements(value, schedule), **analysis_paths("untrusted"))


def test_analysis_reports_all_orders_coverage_and_expected_fixture_mae():
    value = module()
    schedule = value.schedule(**source_paths())
    analysis = value.analyze(schedule, _measurements(value, schedule), **analysis_paths())
    assert set(analysis["metrics"]) == {"direct_historical_noncontemporaneous", value.FORWARD, value.REVERSE, "per_story_mean_orders"}
    expected_mae = {
        dimension: sum(abs(3.0 - float(row["target"][dimension])) for row in schedule["panel"]) / 50
        for dimension in value.DIMS
    }
    for metric_name in ("direct_historical_noncontemporaneous", "per_story_mean_orders"):
        metric = analysis["metrics"][metric_name]
        assert metric["strict_full_five_prompt_complete"] is False
        assert metric["strict_full_five_prompt_macro_six"] is None
        for dimension in value.DIMS:
            values = metric["dimensions"][dimension]
            assert values["global_item_50_mae"] == pytest.approx(expected_mae[dimension])
            assert values["hanna_compatible_retained_prompt_count"] == 0
            assert values["hanna_compatible_dropped_prompt_count"] == 5
            assert values["fixed_three_spearman"] is None
    forward = analysis["metrics"][value.FORWARD]["dimensions"]
    reverse = analysis["metrics"][value.REVERSE]["dimensions"]
    averaged = analysis["metrics"]["per_story_mean_orders"]["dimensions"]
    for dimension in value.DIMS:
        assert forward[dimension]["global_item_50_mae"] != reverse[dimension]["global_item_50_mae"]
        assert averaged[dimension]["global_item_50_mae"] == pytest.approx(expected_mae[dimension])
    assert analysis["native_admission"].startswith("not_claimed")
    assert analysis["expected_endpoint"] == "grok_primary"


def test_package_has_no_executor_or_provider_dispatch_surface():
    value = module()
    tracked_names = {path.name for path in PACKAGE.iterdir() if path.is_file()}
    assert tracked_names == {"README.md", "experiment-contract.json", "study.py"}
    assert not any(name in vars(value) for name in ("execute", "dispatch", "prepare", "run_provider", "provider_call"))
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")
    assert "provider-free source only" in readme
    assert "NO-GO" in readme
