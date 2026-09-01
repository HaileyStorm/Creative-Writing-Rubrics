from __future__ import annotations

import base64
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-validation-exec-v1"
ACK = "a" * 64
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module():
    spec = importlib.util.spec_from_file_location("_desc13_lower_sol_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def fake_schedule(value):
    groups = [{"prompt_group_id": f"group-{index}", "item_id": f"item-{index}"} for index in range(7)]
    children = ["broader-nextwave-18-construct_framing-referent-resolution", "child-b", "child-c", "child-d"]
    candidates = [{"candidate_id": value.PARENT}, *({"candidate_id": child} for child in children)]
    cells = []
    for group in groups:
        for candidate in candidates:
            payload = value.canonical({"candidate": candidate["candidate_id"], "item": group["item_id"], "response_schema": {"type": "object"}})
            cells.append({"cell_id": f"grok-{candidate['candidate_id']}-{group['item_id']}", "candidate_id": candidate["candidate_id"], **group, "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": value.sha256(payload)})
    schedule = {"study_id": value.GROK_EXECUTOR_ID, "groups": groups, "candidates": candidates, "cells": cells}
    schedule["schedule_sha256"] = value.sha256(schedule)
    schedule["development_schedule_sha256"] = "d" * 64
    return schedule


def fake_broader(value, targets):
    class SourceFreeze:
        @staticmethod
        def _source_material(**_kwargs):
            return {item_id: {"item": item_id} for item_id in targets}

        @staticmethod
        def _payload_bytes(*, item, candidate):
            return value.canonical({"study_id": "old", "candidate": candidate["candidate_id"], "item": item["item"], "response_schema": {"type": "object"}})

    class V2:
        @staticmethod
        def _extract_native(response, **_kwargs):
            score = json.loads(response)["score"]
            return ({dimension: score for dimension in DIMS}, {dimension: True for dimension in DIMS}, {})

        @staticmethod
        def parent_modules():
            return None, None, SourceFreeze()

    class V3:
        BASELINE_ID = "original-baseline"

        @staticmethod
        def _material(**_kwargs):
            return None, None, None, {"items": [{"partition": "development", "prompt_group_id": f"group-{index}", "item_id": f"item-{index}"} for index in range(7)]}, [{"candidate_id": "original-baseline", "instruction_bytes": b"baseline", "profile_bytes": b"{}"}]

        @staticmethod
        def v2_module():
            return V2()

    class Broader:
        @staticmethod
        def _v3():
            return V3()

    return Broader()


def fixture_result(value, schedule):
    return {
        "study_id": value.ANALYZER_ID,
        "selection": {"candidate_id": "broader-nextwave-18-construct_framing-referent-resolution", "equal_group_mae": 1.0},
        "source_execution": {
            "executor_commit": "cd67452ceb018e18f5d2d3315c544af0d47f23ef",
            "executor_sha256": "00c1df7da792c36e4d1532765977299c5001c0119097985a089a8935fd014b14",
            "collector_sha256": "6ca1fc13244f93719d672a127ddf10cc492ea2207e5649fab1058bdbea923ae6",
            "development_schedule_sha256": schedule["development_schedule_sha256"],
        },
        "result_internal_sha256": "f" * 64,
    }


def test_committed_result_replay_resolves_referent_then_preserves_observed_grok_payload_bytes(monkeypatch, tmp_path: Path):
    value, schedule = module(), fake_schedule(module())
    output = tmp_path / "grok"; output.mkdir()
    (output / "schedule.json").write_bytes(value.canonical(schedule))
    for row in schedule["cells"]:
        root = output / row["cell_id"]; root.mkdir()
        (root / "outbound-payload.json").write_bytes(base64.b64decode(row["payload_base64"]))
    result = fixture_result(value, schedule)
    result_path = tmp_path / "result.json"; result_path.write_bytes(value.canonical(result))
    targets = {group["item_id"]: {dimension: 2.0 for dimension in DIMS} for group in schedule["groups"]}
    broad = fake_broader(value, targets)

    class Analyzer:
        @staticmethod
        def replay(**_kwargs): return result

    monkeypatch.setattr(value, "RESULT_SHA256", value.sha256(value.canonical(result)))
    rebuilt, replayed, _raw = value._result_projection(analyzer=Analyzer(), candidate_freeze_root=tmp_path, development_freeze_root=tmp_path, normalized_root=tmp_path, materialization_root=tmp_path, frozen_successor_path=tmp_path, hanna_csv_path=tmp_path, grok_execution_root=output, grok_collector_path=tmp_path / "collector.json", grok_result_path=result_path)
    assert replayed["selection"]["candidate_id"] == "broader-nextwave-18-construct_framing-referent-resolution"
    monkeypatch.setattr(value, "_baseline_rows", lambda **_kwargs: [{"cell_id": f"base-{index}", "source_cell_id": None, "candidate_id": "original-baseline", "prompt_group_id": f"group-{index}", "item_id": f"item-{index}", "story_id": f"item-{index}", "payload_base64": "e30=", "payload_sha256": value.sha256(b"{}"), "payload_parity": "deterministic_same_freeze_reconstruction_not_observed_in_this_grok_wave", "target": targets[f"item-{index}"]} for index in range(7)])
    rows = value._rows(broader=broad, schedule=rebuilt, result=replayed, targets=targets, grok_execution_root=output, frozen_successor_path=tmp_path, hanna_csv_path=tmp_path)
    assert len(rows) == 21
    source_by_id = {row["cell_id"]: row for row in schedule["cells"]}
    for row in rows:
        if row["source_cell_id"] is not None:
            source = source_by_id[row["source_cell_id"]]
            assert row["payload_base64"] == source["payload_base64"]
            assert row["payload_sha256"] == source["payload_sha256"]
            assert row["payload_parity"] == "observed_exact_grok_outbound_bytes"


def test_baseline_reconstruction_is_explicitly_unobserved_and_uses_same_grok_study_identity():
    value = module()
    schedule = {"groups": [{"prompt_group_id": f"group-{index}", "item_id": f"item-{index}"} for index in range(7)]}
    targets = {group["item_id"]: {dimension: 2.0 for dimension in DIMS} for group in schedule["groups"]}
    rows = value._baseline_rows(broader=fake_broader(value, targets), schedule=schedule, targets=targets, frozen_successor_path=Path.cwd(), hanna_csv_path=Path.cwd())
    assert len(rows) == 7 and {row["payload_parity"] for row in rows} == {"deterministic_same_freeze_reconstruction_not_observed_in_this_grok_wave"}
    assert all(json.loads(base64.b64decode(row["payload_base64"]))["study_id"] == value.GROK_EXECUTOR_ID for row in rows)


def test_prepare_is_zero_contact_and_fake_wave_stays_at_two_lanes(monkeypatch, tmp_path: Path):
    value = module()
    rows = tuple({"cell_id": f"sol-{index}", "candidate_id": "candidate", "payload_base64": base64.b64encode(value.canonical({"response_schema": {"type": "object"}})).decode("ascii"), "payload_sha256": "x", "payload_parity": "fixture", "target": {dimension: 2.0 for dimension in DIMS}} for index in range(21))
    resolution = {"rows": rows, "schedule": {"schedule_sha256": "schedule"}, "bindings": {"result_analyzer_commit": "0" * 40, "result_analyzer_sha256": "1" * 64, "result_analyzer_contract_sha256": "2" * 64, "grok_result_sha256": "3" * 64, "grok_result_internal_sha256": "4" * 64, "grok_execution_commit": "5" * 40, "grok_collector_sha256": "6" * 64, "grok_executor_sha256": "7" * 64, "hanna_csv_sha256": "8" * 64}}
    monkeypatch.setattr(value, "_resolve", lambda **_kwargs: resolution)
    state, guard = {"active": 0, "maximum": 0, "calls": 0}, threading.Lock()

    class Base:
        canonical = staticmethod(value.canonical)

        @staticmethod
        def _route(*_args): return {"route": "fixture"}, {"evidence": "fixture"}, None

        @staticmethod
        def _prepared(row, payload, schema, target, route, evidence, acknowledgement):
            return {"outbound-payload.json": payload, "response-schema.json": schema, "prepared.json": value.canonical({"row": row, "ack": acknowledgement})}

        @staticmethod
        def _write_new(path, raw): path.write_bytes(raw)

        @staticmethod
        def execute_one(**kwargs):
            with guard:
                state["active"] += 1; state["maximum"] = max(state["maximum"], state["active"]); state["calls"] += 1
            try:
                time.sleep(0.01)
                return {"cell_id": kwargs["cell_id"], "state": "fixture"}
            finally:
                with guard: state["active"] -= 1

    monkeypatch.setattr(value, "_configured_base", lambda _resolution: Base())
    source_roots = {name: tmp_path / name for name in ("candidate", "development", "normalized", "materialization", "successor", "csv", "grok", "collector", "result")}
    for path in source_roots.values():
        path.mkdir()
    common = {"output_root": tmp_path / "sol", "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "candidate_freeze_root": source_roots["candidate"], "development_freeze_root": source_roots["development"], "normalized_root": source_roots["normalized"], "materialization_root": source_roots["materialization"], "frozen_successor_path": source_roots["successor"], "hanna_csv_path": source_roots["csv"], "grok_execution_root": source_roots["grok"], "grok_collector_path": source_roots["collector"], "grok_result_path": source_roots["result"]}
    common["queue_root"].mkdir()
    prepared = value.prepare_all(**common)
    assert prepared["cells"] == 21 and prepared["provider_calls_made"] == prepared["process_launches"] == 0
    completed = value.execute_wave(**common, allow_remote=True)
    assert len(completed) == state["calls"] == 21 and state["maximum"] == 2


def test_result_replay_mismatch_is_rejected_and_package_has_no_runtime_optimizer_imports(monkeypatch, tmp_path: Path):
    value = module()
    schedule = fake_schedule(value)
    output = tmp_path / "grok"; output.mkdir()
    (output / "schedule.json").write_bytes(value.canonical(schedule))
    result = fixture_result(value, schedule)
    result_path = tmp_path / "result.json"; result_path.write_bytes(value.canonical(result))
    monkeypatch.setattr(value, "RESULT_SHA256", value.sha256(value.canonical(result)))

    class Analyzer:
        @staticmethod
        def replay(**_kwargs): return {**result, "selection": {"candidate_id": value.PARENT}}

    with pytest.raises(ValueError, match="differs from independent V2 replay"):
        value._result_projection(analyzer=Analyzer(), candidate_freeze_root=tmp_path, development_freeze_root=tmp_path, normalized_root=tmp_path, materialization_root=tmp_path, frozen_successor_path=tmp_path, hanna_csv_path=tmp_path, grok_execution_root=output, grok_collector_path=tmp_path / "collector.json", grok_result_path=result_path)
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
    assert module().validate_package()["study_id"] == value.STUDY_ID


def test_resolve_rejects_target_source_mutation_after_analyzer_replay(monkeypatch, tmp_path: Path):
    value = module()
    hanna = tmp_path / "hanna.csv"; hanna.write_bytes(b"before")

    class Freeze:
        @staticmethod
        def validate_frozen_root(_path): pass

    replay = {
        "selection": {"candidate_id": "broader-nextwave-18-construct_framing-referent-resolution"},
        "source_execution": {"executor_commit": "0" * 40, "executor_sha256": "1" * 64, "collector_sha256": "2" * 64},
        "result_internal_sha256": "3" * 64,
    }
    commits = iter(({"all": "before"}, {"all": "before"}, {"all": "mutated"}))
    monkeypatch.setattr(value, "candidate_study", lambda: Freeze())
    monkeypatch.setattr(value, "broader_study", lambda: Freeze())
    monkeypatch.setattr(value, "result_analyzer", lambda: object())
    monkeypatch.setattr(value, "_input_commitments", lambda _inputs: next(commits))
    monkeypatch.setattr(value, "_result_projection", lambda **_kwargs: ({"schedule_sha256": "fixture"}, replay, b"result"))
    monkeypatch.setattr(value, "_targets", lambda *_args: {"item": {dimension: 9.0 for dimension in DIMS}})
    monkeypatch.setattr(value, "_rows", lambda **_kwargs: ())

    with pytest.raises(ValueError, match="changed during Sol target/row reconstruction"):
        value._resolve(
            candidate_freeze_root=tmp_path, development_freeze_root=tmp_path, normalized_root=tmp_path,
            materialization_root=tmp_path, frozen_successor_path=tmp_path, hanna_csv_path=hanna,
            grok_execution_root=tmp_path, grok_collector_path=tmp_path, grok_result_path=tmp_path,
        )


def test_resolve_keeps_precheck_csv_hash_when_mutation_follows_final_commitment(monkeypatch, tmp_path: Path):
    value = module()
    hanna = tmp_path / "hanna.csv"; hanna.write_bytes(b"before")

    class Freeze:
        @staticmethod
        def validate_frozen_root(_path): pass

    replay = {
        "selection": {"candidate_id": "broader-nextwave-18-construct_framing-referent-resolution"},
        "source_execution": {"executor_commit": "0" * 40, "executor_sha256": "1" * 64, "collector_sha256": "2" * 64},
        "result_internal_sha256": "3" * 64,
    }
    calls = {"count": 0}

    def commitments(_inputs):
        calls["count"] += 1
        if calls["count"] == 3:
            hanna.write_bytes(b"after")
        return {"all": "same"}

    monkeypatch.setattr(value, "candidate_study", lambda: Freeze())
    monkeypatch.setattr(value, "broader_study", lambda: Freeze())
    monkeypatch.setattr(value, "result_analyzer", lambda: object())
    monkeypatch.setattr(value, "_input_commitments", commitments)
    monkeypatch.setattr(value, "_result_projection", lambda **_kwargs: ({"schedule_sha256": "fixture"}, replay, b"result"))
    monkeypatch.setattr(value, "_targets", lambda *_args: {"item": {dimension: 2.0 for dimension in DIMS}})
    monkeypatch.setattr(value, "_rows", lambda **_kwargs: ())

    resolution = value._resolve(
        candidate_freeze_root=tmp_path, development_freeze_root=tmp_path, normalized_root=tmp_path,
        materialization_root=tmp_path, frozen_successor_path=tmp_path, hanna_csv_path=hanna,
        grok_execution_root=tmp_path, grok_collector_path=tmp_path, grok_result_path=tmp_path,
    )
    assert resolution["bindings"]["hanna_csv_sha256"] == value.sha256(b"before")


@pytest.mark.parametrize("entrypoint", ("prepare_all", "execute_one", "execute_wave"))
def test_direct_lifecycle_entrypoints_fail_closed_on_package_admission_drift(monkeypatch, tmp_path: Path, entrypoint: str):
    value = module()
    monkeypatch.setattr(value, "validate_package", lambda: (_ for _ in ()).throw(ValueError("forged package contract")))
    common = {"output_root": tmp_path / "output", "queue_root": tmp_path, "authorization_acknowledgement_sha256": ACK}
    with pytest.raises(ValueError, match="forged package contract"):
        if entrypoint == "prepare_all":
            getattr(value, entrypoint)(**common)
        elif entrypoint == "execute_one":
            getattr(value, entrypoint)(**common, cell_id="cell", allow_remote=True)
        else:
            getattr(value, entrypoint)(**common, allow_remote=True)
