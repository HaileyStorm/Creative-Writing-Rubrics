from __future__ import annotations

import builtins
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1"
FREEZE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1" / "study.py"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
LIVE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a")
LIVE_FREEZE = Path(r"C:\Users\Haile\Documents\cwr-hanna-desc18-open-freeze-83d7be7-20260901a")
LIVE_COLLECTOR = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a.reconciled-v1.collector.json")
LIVE_RESULT = Path(r"C:\Users\Haile\Documents\cwr-desc18-broad-grok-4d3b2ef-20260901a.optimizer-result-v1.json")


def load():
    spec = importlib.util.spec_from_file_location("_desc18_sol_veto", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def freeze(root: Path):
    spec = importlib.util.spec_from_file_location("_desc18_sol_freeze_test", FREEZE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.freeze(root)


def test_package_pins_frozen_optimizer_result_and_reviewed_dependencies():
    value = load()
    contract = value.validate_package()
    assert contract["frozen_optimizer_result"] == {"file_sha256": "da6f567763f4b4f0bece074a47bcf34a247e2c337dbaaee09f3ee9f69cd5aaa9", "internal_sha256": "a399ca0f626cc62eccd352b256385d8892c5799455494b76ca5d539c1e3072a6"}
    assert contract["geometry"]["sol_cells_if_child20_qualifies"] == 64
    assert contract["pinned_dependencies"]["desc16_sol_lifecycle"]["commit"] == "9f48ed828e49c640434008979606ccc838cef8da"


def test_schedule_rows_are_64_matched_exact_frozen_payload_bytes(tmp_path: Path):
    value = load()
    schedule = freeze(tmp_path / "freeze")
    rows = value._rows(schedule)
    source = {row["cell_id"]: row for row in schedule["cells"]}
    assert len(rows) == 64 and len({row["cell_id"] for row in rows}) == 64
    assert {row["candidate_id"] for row in rows} == {value.PARENT, value.CHILD}
    assert len({row["prompt_group_id"] for row in rows}) == 16
    assert all(row["payload_base64"] == source[row["source_cell_id"]]["payload_base64"] for row in rows)


def test_wrong_optimizer_stops_before_output_root_or_route(tmp_path: Path):
    value = load()
    freeze_root, output_root = tmp_path / "freeze", tmp_path / "output"
    freeze(freeze_root)
    (tmp_path / "result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="wrong immutable"):
        value.prepare_all(output_root=output_root, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, grok_execution_root=tmp_path / "grok", freeze_root=freeze_root, grok_collector_path=tmp_path / "collector.json", grok_result_path=tmp_path / "result.json")
    assert not output_root.exists()


def test_nonqualifier_is_a_zero_call_no_root_no_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = load()
    freeze_root, output_root = tmp_path / "freeze", tmp_path / "output"
    freeze(freeze_root)
    monkeypatch.setattr(value, "_replay_optimizer", lambda **_kwargs: {"qualification": {"qualifiers": []}})
    result = value.prepare_all(output_root=output_root, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, grok_execution_root=tmp_path / "grok", freeze_root=freeze_root, grok_collector_path=tmp_path / "collector.json", grok_result_path=tmp_path / "result.json")
    assert result["state"] == "not_qualified_zero_sol_calls"
    assert result["provider_calls_made"] == result["process_launches"] == 0 and not output_root.exists()


@pytest.mark.parametrize("evidence", ("", "x", "y", "[placeholder]", "Searching the workspace for proof", "file:C:/temp/story.txt"))
def test_response_quality_rejects_placeholder_or_pointer_evidence(evidence: str):
    value = load()
    response = {"scores": {name: 3.0 for name in value.DIMENSIONS}, "coverage": {name: True for name in value.DIMENSIONS}, "evidence": {name: "specific grounded observation" for name in value.DIMENSIONS}}
    response["evidence"]["Empathy"] = evidence
    with pytest.raises(ValueError, match="evidence"):
        value.validate_response_quality(response)


def test_response_quality_rejects_all_zero_score_vector():
    value = load()
    response = {"scores": {name: 0.0 for name in value.DIMENSIONS}, "coverage": {name: True for name in value.DIMENSIONS}, "evidence": {name: "specific grounded observation" for name in value.DIMENSIONS}}
    with pytest.raises(ValueError, match="all-zero"):
        value.validate_response_quality(response)


def test_collector_shape_requires_format_and_exact_cell_keys():
    value = load()
    cell = {"cell_id": "a", "source_cell_id": "b", "candidate_id": value.CHILD, "payload_base64": "", "payload_sha256": "0" * 64, "final_response_base64": "", "final_response_sha256": "0" * 64, "receipt_sha256": "0" * 64, "identity": {}, "effective_settings": {}, "effective_settings_sha256": "0" * 64, "human_score_projection": {}}
    collector = {"format_version": 1, "study_id": value.STUDY_ID, "kind": "complete_desc18_matched_sol_veto_receipts_cardinality_unproven", "authorization_acknowledgement_sha256": ACK, "optimizer_result_file_sha256": value.RESULT_FILE_SHA256, "optimizer_result_internal_sha256": value.RESULT_INTERNAL_SHA256, "parent_candidate_id": value.PARENT, "qualified_children": [value.CHILD], "route": {}, "route_evidence": {}, "cells": [cell] * 64, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}
    assert len(value._validate_collector_shape(collector, ACK)) == 64
    collector["format_version"] = 2
    with pytest.raises(ValueError, match="collector"):
        value._validate_collector_shape(collector, ACK)
    collector["format_version"] = 1
    collector["cells"][0] = {**cell, "unexpected": True}
    with pytest.raises(ValueError, match="cell fields"):
        value._validate_collector_cell_shape(collector["cells"][0])


def test_collector_output_disjoint_rejects_output_child(tmp_path: Path):
    value = load()
    lifecycle = value.desc16_lifecycle()
    output_root = tmp_path / "output"; output_root.mkdir()
    queue_root = tmp_path / "queue"; queue_root.mkdir()
    freeze_root = tmp_path / "freeze"; freeze_root.mkdir()
    grok_root = tmp_path / "grok"; grok_root.mkdir()
    collector = tmp_path / "collector.json"; collector.write_text("{}\n", encoding="utf-8")
    result = tmp_path / "result.json"; result.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="disjoint"):
        value._collector_output_disjoint(lifecycle, collector_output=output_root / "collector.json", output_root=output_root, queue_root=queue_root, grok_execution_root=grok_root, freeze_root=freeze_root, grok_collector_path=collector, grok_result_path=result)


def test_import_does_not_load_development_libraries(monkeypatch: pytest.MonkeyPatch):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("development library imported at executor module load")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    load()


def test_replays_frozen_reconciliation_and_optimizer_before_sol(tmp_path: Path):
    if not all((LIVE_ROOT.is_dir(), LIVE_FREEZE.is_dir(), LIVE_COLLECTOR.is_file(), LIVE_RESULT.is_file())):
        pytest.skip("immutable Desc18 evidence is not present")
    value = load()
    result = value._replay_optimizer(grok_execution_root=LIVE_ROOT, freeze_root=LIVE_FREEZE, grok_collector_path=LIVE_COLLECTOR, grok_result_path=LIVE_RESULT)
    assert result["result_sha256"] == value.RESULT_INTERNAL_SHA256
    assert result["qualification"]["qualifiers"] == [value.CHILD]
