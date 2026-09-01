from __future__ import annotations

import base64
import builtins
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc15-referent-development-optimizer-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc15_referent_optimizer", PACKAGE / "analyzer.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def fixtures(value, levels=None):
    groups = [f"group-{index}" for index in range(7)]
    item_groups = [(f"item-{index:02}", groups[min(index // 2, 6)]) for index in range(13)]
    if levels is None:
        levels = {candidate: [1.0 + index / 10] * 7 for index, candidate in enumerate(value.CANDIDATES)}
    targets = {item: {dimension: 0.0 for dimension in value.DIMENSIONS} for item, _group in item_groups}
    cells = []
    collector_cells = []
    for candidate in value.CANDIDATES:
        for item_index, (item, group) in enumerate(item_groups):
            cell_id = f"cell-{candidate}-{item}"
            payload = value.canonical({"candidate": candidate, "item": item})
            score = levels[candidate][groups.index(group)]
            response_value = {
                "scores": {dimension: score for dimension in value.DIMENSIONS},
                "coverage": {dimension: not (candidate == value.CHILDREN[0] and item == "item-00" and dimension == "Coherence") for dimension in value.DIMENSIONS},
            }
            response = value.canonical(response_value)
            cells.append({
                "candidate_id": candidate,
                "cell_id": cell_id,
                "item_id": item,
                "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": value.sha256(payload),
                "prompt_group_id": group,
            })
            collector_cells.append({
                "cell_id": cell_id,
                "payload_base64": base64.b64encode(payload).decode("ascii"),
                "payload_sha256": value.sha256(payload),
                "native_request_base64": base64.b64encode(b"request").decode("ascii"),
                "native_request_sha256": value.sha256(b"request"),
                "native_response_base64": base64.b64encode(response).decode("ascii"),
                "native_response_sha256": value.sha256(response),
                "identity": {"request_id": cell_id, "session_id": "session-" + cell_id},
                "effective_settings": {"tools_enabled": False},
                "effective_settings_sha256": value.sha256({"tools_enabled": False}),
            })
    schedule = {
        "format_version": 1,
        "study_id": value.EXECUTOR_ID,
        "kind": "frozen_desc15_referent_grok_development_execution_schedule",
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0, "confirmation_cells": 0},
        "frozen_schedule_sha256": value.FREEZE_SCHEDULE_SHA256,
        "schedule_sha256": "s" * 64,
        "cells": cells,
    }
    collector = {
        "format_version": 1,
        "study_id": value.EXECUTOR_ID,
        "kind": "complete_52_desc15_referent_grok_receipts_cardinality_unproven",
        "schedule_sha256": schedule["schedule_sha256"],
        "authorization_acknowledgement_sha256": "a" * 64,
        "route": {"route": "grok"},
        "route_evidence": {"evidence": "fixture"},
        "cells": collector_cells,
        "native_endpoint_contact_cardinality": "unproven",
        "provider_calls_made": None,
        "process_launches": 52,
    }

    def extractor(raw, *, provider, model):
        assert provider == "xai" and model == "grok-4.6"
        parsed = json.loads(raw)
        return parsed["scores"], parsed["coverage"], {"model": model}

    return schedule, collector, targets, extractor


def projection(value, metrics):
    return {
        "format_version": 1,
        "study_id": value.STUDY_ID,
        "kind": "desc15_referent_grok_development_equal_group_projection",
        "authority": value.AUTHORITY,
        "metrics": metrics,
        "source_execution": {
            "collector_sha256": "c" * 64,
            "executor_sha256": value.EXECUTOR_HASHES["executor.py"],
            "frozen_schedule_sha256": value.FREEZE_SCHEDULE_SHA256,
            "schedule_sha256": "s" * 64,
        },
    }


def metric(candidate, groups, coverage_false=None):
    return {
        "candidate_id": candidate,
        "cells": 13,
        "equal_group_mae": sum(groups.values()) / 7,
        "group_mae": groups,
        "coverage_false": [] if coverage_false is None else coverage_false,
    }


def test_package_and_exact_executor_are_provider_free_and_development_only():
    value = module()
    contract = value.validate_package()
    assert value.load_executor().STUDY_ID == value.EXECUTOR_ID
    assert contract["runtime_dependencies"]["production"] == "none"
    source = (PACKAGE / "analyzer.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "http" not in source


def test_module_import_has_no_optuna_or_dspy_runtime_dependency(monkeypatch):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("development library imported at module load")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    module()


def test_projection_averages_thirteen_items_within_seven_groups_and_preserves_coverage():
    value = module()
    levels = {
        value.PARENT: [1.0] * 7,
        value.CHILDREN[0]: [0.9] * 7,
        value.CHILDREN[1]: [0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        value.CHILDREN[2]: [1.1] * 7,
    }
    schedule, collector, targets, extractor = fixtures(value, levels)
    result = value._project(schedule, collector, targets, extractor)
    rows = {row["candidate_id"]: row for row in result["metrics"]}
    assert rows[value.PARENT]["cells"] == 13
    assert rows[value.PARENT]["equal_group_mae"] == pytest.approx(1.0)
    assert rows[value.CHILDREN[1]]["group_mae"]["group-0"] == pytest.approx(0.8)
    assert rows[value.CHILDREN[0]]["coverage_false"] == [{"dimension": "Coherence", "item_id": "item-00", "prompt_group_id": "group-0"}]
    assert result["evidence_ceiling"] == {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 52, "provider_calls_made": None}


def test_replay_projection_binds_executor_replay_collector_and_exact_source_inputs(tmp_path, monkeypatch):
    value = module()
    schedule, collector, targets, extractor = fixtures(value)
    roots = {}
    for name in ("freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "output_root"):
        roots[name] = tmp_path / name
        roots[name].mkdir()
    for name in ("frozen_successor_path", "hanna_csv_path"):
        roots[name] = tmp_path / f"{name}.json"
        roots[name].write_bytes(b"{}\n")
    (roots["output_root"] / "schedule.json").write_bytes(value.canonical(schedule))
    roots["collector_path"] = tmp_path / "collector.json"
    roots["collector_path"].write_bytes(value.canonical(collector))
    fake_executor = SimpleNamespace(
        frozen_schedule=lambda freeze_root: schedule,
        replay_collector=lambda **kwargs: {
            "cells": 52,
            "collector_sha256": value.sha256(value.canonical(collector)),
            "equal_group_projection_ready": True,
            "native_endpoint_contact_cardinality": "unproven",
            "provider_calls_made": None,
        },
    )
    fake_base = SimpleNamespace(_load_freeze=lambda _repo: SimpleNamespace(_v3=lambda: SimpleNamespace(v2_module=lambda: SimpleNamespace(_extract_native=extractor))))
    monkeypatch.setattr(value, "load_executor", lambda: fake_executor)
    monkeypatch.setattr(value, "load_base", lambda: fake_base)
    monkeypatch.setattr(value, "_development_targets", lambda *_args, **_kwargs: targets)
    result = value.replay_projection(**roots)
    assert result["source_execution"] == {
        "collector_sha256": value.sha256(value.canonical(collector)),
        "executor_sha256": value.EXECUTOR_HASHES["executor.py"],
        "frozen_schedule_sha256": value.FREEZE_SCHEDULE_SHA256,
        "schedule_sha256": schedule["schedule_sha256"],
    }
    assert len(result["metrics"]) == 4


def test_real_optuna_grid_and_dspy_examples_freeze_only_parent_relative_qualifiers():
    value = module()
    groups = [f"group-{index}" for index in range(7)]
    metrics = [
        metric(value.PARENT, {group: 1.0 for group in groups}),
        metric(value.CHILDREN[0], {group: 0.9 for group in groups}),
        metric(value.CHILDREN[1], {"group-0": 1.2, **{group: 0.9 for group in groups[1:]}}),
        metric(value.CHILDREN[2], {group: 1.1 for group in groups}),
    ]
    checked = value._validated_metrics(projection(value, metrics))
    optimizer = value.run_optuna(checked)
    qualification = value.qualify(checked, optimizer)
    dspy = value.build_dspy_evidence(checked, qualification)
    assert optimizer["sampler"] == "GridSampler" and optimizer["completed_trials"] == 24
    assert len(optimizer["settings"]) == 6
    assert qualification["qualifiers"] == [value.CHILDREN[0]]
    assert qualification["frozen_before_sol"] is True
    assert qualification["sol_veto"] == {
        "calls_made": 0,
        "eligible_candidates": [value.CHILDREN[0]],
        "role": "veto_only_no_sol_favored_substitution",
        "status": "pending_for_frozen_qualifiers",
    }
    assert dspy["evidence_examples"] == 4
    assert dspy["lm_calls"] == dspy["predict_calls"] == 0


def test_qualification_rejects_duplicated_easy_settings_and_fabricated_objectives():
    value = module()
    groups = [f"group-{index}" for index in range(7)]
    metrics = [
        metric(value.PARENT, {group: 1.0 for group in groups}),
        metric(value.CHILDREN[0], {"group-0": 1.2, **{group: 0.9 for group in groups[1:]}}),
        metric(value.CHILDREN[1], {group: 1.1 for group in groups}),
        metric(value.CHILDREN[2], {group: 1.2 for group in groups}),
    ]
    optimizer = value.run_optuna(metrics)
    duplicated = {**optimizer, "settings": [optimizer["settings"][0]] * 6}
    with pytest.raises(ValueError, match="grid"):
        value.qualify(metrics, duplicated)
    fabricated = json.loads(json.dumps(optimizer))
    fabricated["settings"][0]["objective_by_candidate"][value.CHILDREN[0]] = 0.0
    with pytest.raises(ValueError, match="recompute"):
        value.qualify(metrics, fabricated)


def test_no_qualifier_retains_parent_and_requires_zero_sol_calls():
    value = module()
    groups = [f"group-{index}" for index in range(7)]
    metrics = [metric(candidate, {group: 1.0 + index / 10 for group in groups}) for index, candidate in enumerate(value.CANDIDATES)]
    optimizer = value.run_optuna(metrics)
    qualification = value.qualify(metrics, optimizer)
    assert qualification["qualifiers"] == []
    assert qualification["development_decision"] == "retain_parent_zero_sol_calls"
    assert qualification["sol_veto"]["calls_made"] == 0
    assert qualification["sol_veto"]["status"] == "not_required_no_qualifiers"


def test_caller_aggregates_partial_cells_and_mixed_groups_are_rejected():
    value = module()
    schedule, collector, targets, extractor = fixtures(value)
    collector["cells"].pop()
    with pytest.raises(ValueError, match="collector|partial"):
        value._project(schedule, collector, targets, extractor)
    groups = {f"group-{index}": 1.0 for index in range(7)}
    metrics = [metric(candidate, groups) for candidate in value.CANDIDATES]
    source = projection(value, metrics)
    source["metrics"][0] = {"candidate_id": value.PARENT, "equal_group_mae": 0.0}
    with pytest.raises(ValueError, match="metric shape"):
        value._validated_metrics(source)


def test_result_write_is_fresh_only(tmp_path):
    value = module()
    output = tmp_path / "result.json"
    value.write_result(output, {"result": "fixture"})
    assert output.read_bytes() == value.canonical({"result": "fixture"})
    with pytest.raises(ValueError, match="fresh"):
        value.write_result(output, {"result": "replacement"})


def test_nested_tree_commitment_detects_in_place_receipt_drift_without_root_mtime_change(tmp_path):
    value = module()
    root = tmp_path / "evidence"
    nested = root / "cell"
    nested.mkdir(parents=True)
    receipt = nested / "receipt.bin"
    receipt.write_bytes(b"before")
    root_identity = value._ancestry(root, directory=True)
    before = value._tree_commitment(root)
    receipt.write_bytes(b"after!")
    assert value._ancestry(root, directory=True) == root_identity
    assert value._tree_commitment(root) != before
