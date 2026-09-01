from __future__ import annotations

import base64
import builtins
import importlib.util
import json
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v8-desc17-generalization-development-optimizer-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc17_generalization_optimizer", PACKAGE / "analyzer.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def fixture(value, levels=None):
    groups = [f"group-{number}" for number in range(7)]
    item_groups = [(f"item-{number:02}", groups[min(number // 2, 6)]) for number in range(13)]
    if levels is None:
        levels = {candidate: [1.0 + index / 10] * 7 for index, candidate in enumerate(value.ENGINE.CANDIDATES)}
    targets = {item: {dimension: 0.0 for dimension in value.DIMENSIONS} for item, _group in item_groups}
    cells, receipts = [], []
    for candidate in value.ENGINE.CANDIDATES:
        for item, group in item_groups:
            cell_id = f"{candidate}-{item}"
            payload = value.canonical({"candidate": candidate, "item": item})
            response = value.canonical({"scores": {dimension: levels[candidate][groups.index(group)] for dimension in value.DIMENSIONS}, "coverage": {dimension: True for dimension in value.DIMENSIONS}})
            cells.append({"candidate_id": candidate, "cell_id": cell_id, "item_id": item, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": value.sha256(payload), "prompt_group_id": group})
            receipts.append({"cell_id": cell_id, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": value.sha256(payload), "native_request_base64": base64.b64encode(b"request").decode("ascii"), "native_request_sha256": value.sha256(b"request"), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": value.sha256(response), "identity": {"request_id": cell_id, "session_id": "session-" + cell_id}, "effective_settings": {"tools_enabled": False}, "effective_settings_sha256": value.sha256({"tools_enabled": False})})
    schedule = {"format_version": 1, "study_id": value.EXECUTOR_ID, "kind": "frozen_desc17_generalization_grok_development_execution_schedule", "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "sol_cells": 0, "confirmation_cells": 0}, "frozen_schedule_sha256": value.FREEZE_SCHEDULE_SHA256, "schedule_sha256": "s" * 64, "cells": cells}
    collector = {"format_version": 1, "study_id": value.EXECUTOR_ID, "kind": "complete_52_desc17_generalization_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": "a" * 64, "route": {"route": "grok"}, "route_evidence": {"fixture": True}, "cells": receipts, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 52}

    def extractor(raw, *, provider, model):
        assert provider == "xai" and model == "grok-4.6"
        parsed = json.loads(raw)
        return parsed["scores"], parsed["coverage"], {"model": model}

    return schedule, collector, targets, extractor


def projection(value, metrics):
    return {"format_version": 1, "study_id": value.STUDY_ID, "kind": "desc17_generalization_grok_development_equal_group_projection", "authority": value.ENGINE.AUTHORITY, "metrics": metrics, "source_execution": {"collector_sha256": "c" * 64, "executor_sha256": value.ENGINE.EXECUTOR_HASHES["executor.py"], "frozen_schedule_sha256": value.FREEZE_SCHEDULE_SHA256, "schedule_sha256": "s" * 64}}


def metric(candidate, groups):
    return {"candidate_id": candidate, "cells": 13, "equal_group_mae": sum(groups.values()) / 7, "group_mae": groups, "coverage_false": []}


def settle_ntfs_timestamps(*paths):
    for path in paths:
        previous = None
        for _ in range(25):
            current = path.stat().st_mtime_ns
            if current == previous:
                break
            previous = current
            time.sleep(0.02)
        else:
            pytest.fail(f"timestamp did not settle: {path}")


def test_package_pins_desc17_freeze_and_committed_executor_bytes(monkeypatch):
    value = module()
    contract = value.validate_package()
    assert contract["pinned_freeze"] == {"commit": "2c551441339003caeb13b75a5d420ba52c1f6882", "manifest_file_sha256": value.FREEZE_MANIFEST_SHA256, "schedule_file_sha256": value.FREEZE_SCHEDULE_FILE_SHA256, "schedule_sha256": value.FREEZE_SCHEDULE_SHA256}
    assert contract["executor_binding"] == "committed_exact_public_file_hashes"
    assert contract["pinned_executor"] == {"commit": value.EXECUTOR_COMMIT, "files": value.EXECUTOR_FILES, "study_id": value.EXECUTOR_ID}
    for name, digest in value.EXECUTOR_FILES.items():
        relative = (value.EXECUTOR_ROOT / name).relative_to(ROOT).as_posix()
        committed = subprocess.run(["git", "show", f"{value.EXECUTOR_COMMIT}:{relative}"], cwd=ROOT, capture_output=True, check=True).stdout
        assert value.sha256(committed) == digest
        assert committed == (value.EXECUTOR_ROOT / name).read_bytes()
    assert value.load_executor().STUDY_ID == value.EXECUTOR_ID
    monkeypatch.setitem(value.EXECUTOR_FILES, "executor.py", "0" * 64)
    with pytest.raises(ValueError, match="binding drifted"):
        value.load_executor()


def test_executor_binding_rejects_malformed_hashes(monkeypatch):
    value = module()
    monkeypatch.setitem(value.EXECUTOR_FILES, "executor.py", "not-a-sha256")
    with pytest.raises(ValueError, match="binding is malformed"):
        value.load_executor()


def test_import_does_not_load_dspy_or_optuna(monkeypatch):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("development library imported at module load")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    module()


def test_projection_independently_recomputes_52_native_cells_and_rejects_partial_or_tampered_receipts():
    value = module()
    levels = {value.PARENT: [1.0] * 7, value.CHILDREN[0]: [0.9] * 7, value.CHILDREN[1]: [0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0], value.CHILDREN[2]: [1.1] * 7}
    schedule, collector, targets, extractor = fixture(value, levels)
    result = value._project(schedule, collector, targets, extractor)
    rows = {row["candidate_id"]: row for row in result["metrics"]}
    assert rows[value.PARENT]["equal_group_mae"] == pytest.approx(1.0)
    assert rows[value.CHILDREN[1]]["group_mae"]["group-0"] == pytest.approx(0.8)
    collector["cells"].pop()
    with pytest.raises(ValueError, match="collector|partial"):
        value._project(schedule, collector, targets, extractor)
    schedule, collector, targets, extractor = fixture(value)
    collector["cells"][0]["native_response_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="sha256|receipt|collector"):
        value._project(schedule, collector, targets, extractor)


def test_real_optuna_and_dspy_freeze_only_parent_relative_qualifiers():
    value = module()
    value.ENGINE.EXECUTOR_HASHES = {"executor.py": "e" * 64}
    groups = {f"group-{number}": 1.0 for number in range(7)}
    metrics = [metric(value.PARENT, groups), metric(value.CHILDREN[0], {name: 0.9 for name in groups}), metric(value.CHILDREN[1], {"group-0": 1.2, **{name: 0.9 for name in groups if name != "group-0"}}), metric(value.CHILDREN[2], {name: 1.1 for name in groups})]
    checked = value._validated_metrics(projection(value, metrics))
    optimizer = value.run_optuna(checked)
    qualification = value.qualify(checked, optimizer)
    evidence = value.build_dspy_evidence(checked, qualification)
    assert optimizer["sampler"] == "GridSampler" and optimizer["completed_trials"] == 24 and len(optimizer["settings"]) == 6
    assert qualification["parent_candidate_id"] == value.PARENT
    assert qualification["qualifiers"] == [value.CHILDREN[0]] and qualification["frozen_before_sol"] is True
    assert qualification["sol_veto"]["role"] == "veto_only_no_sol_favored_substitution"
    assert evidence["evidence_examples"] == 4 and evidence["lm_calls"] == evidence["predict_calls"] == 0


def test_fabricated_metric_shape_and_duplicate_grid_settings_are_rejected():
    value = module()
    value.ENGINE.EXECUTOR_HASHES = {"executor.py": "e" * 64}
    groups = {f"group-{number}": 1.0 for number in range(7)}
    metrics = [metric(value.PARENT, groups), metric(value.CHILDREN[0], {name: 0.9 for name in groups}), metric(value.CHILDREN[1], {name: 1.1 for name in groups}), metric(value.CHILDREN[2], {name: 1.2 for name in groups})]
    malformed = deepcopy(metrics)
    malformed[0]["equal_group_mae"] = 0.0
    with pytest.raises(ValueError, match="equal-group|metrics"):
        value._validated_metrics(projection(value, malformed))
    checked = value._validated_metrics(projection(value, metrics))
    duplicated = value.run_optuna(checked)
    duplicated["settings"][1] = deepcopy(duplicated["settings"][0])
    with pytest.raises(ValueError, match="grid|recompute"):
        value.qualify(checked, duplicated)


def test_external_collector_is_accepted_only_via_exact_executor_replay(tmp_path, monkeypatch):
    value = module()
    schedule, collector, targets, extractor = fixture(value)
    roots = {}
    for name in ("freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "output_root"):
        roots[name] = tmp_path / name
        roots[name].mkdir()
    for name in ("frozen_successor_path", "hanna_csv_path"):
        roots[name] = tmp_path / f"{name}.json"
        roots[name].write_bytes(b"{}\n")
    (roots["output_root"] / "schedule.json").write_bytes(value.canonical(schedule))
    roots["collector_path"] = tmp_path / "external-immutable-collector.json"
    roots["collector_path"].write_bytes(value.canonical(collector))
    settle_ntfs_timestamps(*roots.values())
    value.ENGINE.EXECUTOR_HASHES = {"executor.py": "e" * 64}
    fake_executor = SimpleNamespace(frozen_schedule=lambda _root: schedule, replay_collector=lambda **kwargs: {"cells": 52, "collector_sha256": value.sha256(roots["collector_path"].read_bytes()), "equal_group_projection_ready": True, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None})
    fake_base = SimpleNamespace(_load_freeze=lambda _repo: SimpleNamespace(_v3=lambda: SimpleNamespace(v2_module=lambda: SimpleNamespace(_extract_native=extractor))))
    monkeypatch.setattr(value.ENGINE, "load_executor", lambda: fake_executor)
    monkeypatch.setattr(value.ENGINE, "load_base", lambda: fake_base)
    monkeypatch.setattr(value.ENGINE, "_development_targets", lambda *_args, **_kwargs: targets)
    result = value.replay_projection(**roots)
    assert result["source_execution"]["collector_sha256"] == value.sha256(roots["collector_path"].read_bytes())
    assert len(result["metrics"]) == 4
    def mutate_then_replay(**_kwargs):
        (roots["output_root"] / "mutation.json").write_bytes(b"{}\n")
        return {"cells": 52, "collector_sha256": value.sha256(roots["collector_path"].read_bytes()), "equal_group_projection_ready": True, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None}

    mutating_executor = SimpleNamespace(frozen_schedule=lambda _root: schedule, replay_collector=mutate_then_replay)
    monkeypatch.setattr(value.ENGINE, "load_executor", lambda: mutating_executor)
    with pytest.raises(ValueError, match="changed between replay|nested replay evidence changed"):
        value.replay_projection(**roots)


def test_fabricated_objective_is_rejected_and_empty_qualifiers_make_zero_sol_calls():
    value = module()
    groups = {f"group-{number}": 1.0 for number in range(7)}
    metrics = [metric(candidate, {name: 1.0 + index / 10 for name in groups}) for index, candidate in enumerate(value.ENGINE.CANDIDATES)]
    optimizer = value.run_optuna(metrics)
    fabricated = json.loads(json.dumps(optimizer))
    fabricated["settings"][0]["objective_by_candidate"][value.CHILDREN[0]] = 0.0
    with pytest.raises(ValueError, match="recompute"):
        value.qualify(metrics, fabricated)
    qualification = value.qualify(metrics, optimizer)
    assert qualification["qualifiers"] == []
    assert qualification["development_decision"] == "retain_parent_zero_sol_calls"
    assert qualification["sol_veto"]["calls_made"] == 0


def test_result_output_is_write_once(tmp_path):
    value = module()
    output = tmp_path / "result.json"
    value.write_result(output, {"study_id": value.STUDY_ID})
    with pytest.raises(ValueError, match="fresh"):
        value.write_result(output, {"study_id": value.STUDY_ID})
