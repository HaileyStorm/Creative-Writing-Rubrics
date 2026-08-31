from __future__ import annotations

import base64
import importlib.util
import json
import multiprocessing
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-validation-v1"
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("_broader_sol_validation", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def claim_worker(locks: str, root: str, cell_id: str, write_terminal: bool, started, release, outcomes):
    value = module()
    claim = None
    try:
        claim = value._claim_cell(Path(locks), Path(root), cell_id)
        outcomes.put("claimed")
        started.set()
        if write_terminal:
            (Path(root) / "launch-intent.json").write_bytes(b"{}\n")
        release.wait(20)
    except BaseException as error:
        outcomes.put(type(error).__name__)
    finally:
        value._release(claim)


def fixture(value, tmp_path: Path):
    groups = [{"prompt_group_id": f"group-{index}", "item_id": f"item-{index}"} for index in range(7)]
    candidates = [value.PARENT, *sorted(value.CHILDREN)]
    cells, targets = [], {}
    execution = tmp_path / "grok"
    execution.mkdir()
    for group in groups:
        targets[group["item_id"]] = {dimension: 2.0 for dimension in value.DIMENSIONS}
        for ordinal, candidate in enumerate(candidates):
            cell_id = f"grok-{ordinal}-{group['item_id']}"
            payload = value.canonical({"candidate": candidate, "item": group["item_id"], "response_schema": {"type": "object"}})
            cells.append({"cell_id": cell_id, "candidate_id": candidate, **group, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": value.sha256(payload)})
            root = execution / cell_id
            root.mkdir()
            (root / "outbound-payload.json").write_bytes(payload)
    baseline = []
    for group in groups:
        payload = value.canonical({"candidate": value.BASELINE, "item": group["item_id"], "response_schema": {"type": "object"}})
        baseline.append({"cell_id": f"baseline-{group['item_id']}", "source_cell_id": None, "candidate_id": value.BASELINE, **group, "story_id": group["item_id"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": value.sha256(payload), "target": targets[group["item_id"]]})
    schedule = {"study_id": value.FREEZE_ID, "groups": groups, "cells": cells}
    result = {"study_id": value.RESULT_ID, "authority": {"selection": "grok_development_only"}, "selection": {"candidate_id": value.PARENT}, "metrics": [{"candidate_id": candidate} for candidate in candidates]}
    return schedule, result, targets, execution, baseline


def test_parent_and_descendant_winner_geometries_keep_grok_payloads_exact(monkeypatch, tmp_path: Path):
    value = module(); schedule, result, targets, execution, baseline = fixture(value, tmp_path)
    monkeypatch.setattr(value, "_baseline_rows", lambda *_args: baseline)
    parent_rows = value._rows(None, schedule, result, targets, execution, tmp_path, tmp_path, tmp_path)
    assert len(parent_rows) == 14
    child = sorted(value.CHILDREN)[0]
    result["selection"] = {"candidate_id": child}
    child_rows = value._rows(None, schedule, result, targets, execution, tmp_path, tmp_path, tmp_path)
    assert len(child_rows) == 21
    by_source = {row["cell_id"]: row for row in schedule["cells"]}
    for row in child_rows:
        if row["source_cell_id"] is not None:
            source = by_source[row["source_cell_id"]]
            assert row["payload_base64"] == source["payload_base64"]
            assert row["payload_sha256"] == source["payload_sha256"]


def test_baseline_uses_pinned_parent_material_and_seven_groups(tmp_path: Path):
    value = module(); material = tmp_path / "material"; material.mkdir()
    instruction, profile = b"baseline instruction", b'{"factors":{}}'
    (material / "parent-instruction.bin").write_bytes(instruction)
    (material / "parent-profile.bin").write_bytes(profile)
    materialization = value.canonical({"provider_calls_made": 0, "process_launches": 0, "artifacts": {"parent-instruction.bin": value.sha256(instruction), "parent-profile.bin": value.sha256(profile)}})
    (material / "materialization.json").write_bytes(materialization)
    groups = [{"prompt_group_id": f"g{index}", "item_id": f"i{index}"} for index in range(7)]
    captured = []
    class SourceFreeze:
        def _source_material(self, **_kwargs):
            return {group["item_id"]: {"prompt": group["item_id"], "story": "story"} for group in groups}
        def _payload_bytes(self, *, item, candidate):
            captured.append(candidate)
            return value.canonical({"study_id": "old", "prompt": item["prompt"], "response_schema": {"type": "object"}})
    class V2:
        def parent_modules(self): return (None, None, SourceFreeze())
    class V3:
        def v2_module(self): return V2()
    class Freeze:
        def _v3(self): return V3()
    targets = {group["item_id"]: {dimension: 2.0 for dimension in value.DIMENSIONS} for group in groups}
    schedule = {"groups": groups, "materialization_file_sha256": value.sha256(materialization)}
    rows = value._baseline_rows(Freeze(), schedule, targets, material, tmp_path / "frozen", tmp_path / "hanna.csv")
    assert len(rows) == 7 and {row["candidate_id"] for row in rows} == {value.BASELINE}
    assert all(candidate["candidate_id"] == value.BASELINE and candidate["instruction_bytes"] == instruction and candidate["profile_bytes"] == profile for candidate in captured)
    (material / "materialization.json").write_bytes(value.canonical({"provider_calls_made": 1, "process_launches": 0, "artifacts": {"parent-instruction.bin": value.sha256(instruction), "parent-profile.bin": value.sha256(profile)}}))
    with pytest.raises(ValueError, match="materialization"):
        value._baseline_rows(Freeze(), schedule, targets, material, tmp_path / "frozen", tmp_path / "hanna.csv")


def test_prepare_is_zero_contact_and_fake_wave_stays_at_two_lanes(monkeypatch, tmp_path: Path):
    value = module(); schedule, result, targets, execution, baseline = fixture(value, tmp_path)
    monkeypatch.setattr(value, "_baseline_rows", lambda *_args: baseline)
    rows = value._rows(None, schedule, result, targets, execution, tmp_path, tmp_path, tmp_path)
    resolution = {"rows": rows, "schedule": {"schedule_sha256": "s"}, "bindings": {"grok_result_commit": "0" * 40, "grok_result_sha256": "1" * 64, "grok_result_internal_sha256": "2" * 64, "grok_collector_sha256": "3" * 64, "hanna_csv_sha256": "4" * 64}}
    monkeypatch.setattr(value, "_resolve", lambda **_kwargs: resolution)
    state, guard = {"active": 0, "maximum": 0, "calls": 0}, threading.Lock()
    class Base:
        canonical = staticmethod(value.canonical)
        @staticmethod
        def _route(*_args): return ({"route": "fixture"}, {"evidence": "fixture"}, None)
        @staticmethod
        def _prepared(row, payload, schema, target, route, evidence, acknowledgement):
            return {"outbound-payload.json": payload, "response-schema.json": schema, "prepared.json": value.canonical({"cell": row, "target": target, "ack": acknowledgement})}
        @staticmethod
        def _write_new(path, raw): path.write_bytes(raw)
        @staticmethod
        def execute_one(**kwargs):
            with guard:
                state["active"] += 1; state["maximum"] = max(state["maximum"], state["active"]); state["calls"] += 1
            try:
                time.sleep(0.02)
                return {"cell_id": kwargs["cell_id"], "state": "fixture"}
            finally:
                with guard: state["active"] -= 1
    monkeypatch.setattr(value, "_configured_base", lambda _resolution: Base())
    root = tmp_path / "sol"
    queue_root = tmp_path / "queue"; queue_root.mkdir()
    prepared = value.prepare_all(output_root=root, queue_root=queue_root, authorization_acknowledgement_sha256=ACK)
    assert prepared["cells"] == 14 and prepared["provider_calls_made"] == prepared["process_launches"] == 0
    completed = value.execute_wave(output_root=root, queue_root=queue_root, authorization_acknowledgement_sha256=ACK, allow_remote=True)
    assert len(completed) == 14 and state == {"active": 0, "maximum": 2, "calls": 14}


def test_rejects_unknown_or_baseline_winner_and_payload_tamper(monkeypatch, tmp_path: Path):
    value = module(); schedule, result, targets, execution, baseline = fixture(value, tmp_path)
    monkeypatch.setattr(value, "_baseline_rows", lambda *_args: baseline)
    result["selection"] = {"candidate_id": value.BASELINE}
    with pytest.raises(ValueError, match="not admitted"):
        value._winner(result)
    result["selection"] = {"candidate_id": "unknown"}
    with pytest.raises(ValueError, match="not admitted"):
        value._winner(result)
    result["selection"] = {"candidate_id": value.PARENT}
    source = schedule["cells"][0]
    (execution / source["cell_id"] / "outbound-payload.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="payload"):
        value._rows(None, schedule, result, targets, execution, tmp_path, tmp_path, tmp_path)


def test_same_cell_cross_process_claim_allows_one_launch_only(tmp_path: Path):
    value = module(); root, locks = tmp_path / "cell", tmp_path / "locks"
    root.mkdir(); locks.mkdir()
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        started, release, outcomes = manager.Event(), manager.Event(), manager.Queue()
        first = context.Process(target=claim_worker, args=(str(locks), str(root), "cell", True, started, release, outcomes))
        second = context.Process(target=claim_worker, args=(str(locks), str(root), "cell", False, started, release, outcomes))
        first.start(); assert started.wait(20)
        second.start(); time.sleep(0.1); release.set()
        first.join(30); second.join(30)
        assert first.exitcode == second.exitcode == 0
        assert sorted(outcomes.get(timeout=5) for _ in range(2)) == ["ValueError", "claimed"]


def test_package_has_no_runtime_optimizer_imports_or_live_readiness_claim():
    value = module()
    assert value.validate_package()["study_id"] == value.STUDY_ID
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert "no live result is ready" in readme
    overclaim = dict(value.validate_package()); overclaim["authority"] = dict(overclaim["authority"], generalization="supported")
    with pytest.raises(ValueError, match="contract"):
        value._validate_contract(overclaim)
