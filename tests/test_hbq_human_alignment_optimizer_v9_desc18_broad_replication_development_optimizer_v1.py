from __future__ import annotations

import base64
import builtins
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-development-optimizer-v1"
CANDIDATES = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1" / "study.py"


def load():
    spec = importlib.util.spec_from_file_location("_desc18_optimizer", PACKAGE / "analyzer.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def freeze(root: Path):
    spec = importlib.util.spec_from_file_location("_desc18_freeze_test", CANDIDATES)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value.freeze(root)


def collector(value, schedule, *, child_score: float = 2.0, evidence: str = "grounded local evidence"):
    cells = []
    for row in schedule["cells"]:
        score = child_score if row["candidate_id"] == value.CHILD else 3.0
        response = value.canonical({"structuredOutput": {"scores": {dimension: score for dimension in value.DIMENSIONS}, "coverage": {dimension: True for dimension in value.DIMENSIONS}, "evidence": {dimension: evidence for dimension in value.DIMENSIONS}}})
        request = value.canonical({"cell_id": row["cell_id"]})
        cells.append({"cell_id": row["cell_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "native_request_base64": base64.b64encode(request).decode("ascii"), "native_request_sha256": value.sha256(request), "native_response_base64": base64.b64encode(response).decode("ascii"), "native_response_sha256": value.sha256(response), "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "request_id": "request-" + row["cell_id"], "session_id": "session-" + row["cell_id"], "tools_enabled": False}, "effective_settings": {"tools_enabled": False}, "effective_settings_sha256": value.sha256({"tools_enabled": False})})
    return {"format_version": 1, "study_id": value.EXECUTOR_ID, "kind": "complete_64_desc18_open_validation_grok_receipts_cardinality_unproven", "schedule_sha256": schedule["schedule_sha256"], "authorization_acknowledgement_sha256": "a" * 64, "route": {"route": "grok"}, "route_evidence": {"fixture": True}, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 64}


def test_package_pins_committed_executor_contract_readme_and_regression_test(monkeypatch: pytest.MonkeyPatch):
    value = load()
    contract = value.validate_package()
    assert contract["pinned_freeze"]["commit"] == "83d7be718c99c1135302ccb4f8d339a4c68f292f"
    assert contract["pinned_executor"] == {"commit": "4d3b2ef20f5fad4ea0974e888f37550d4b8480f2", "files": value.EXECUTOR_FILES, "study_id": value.EXECUTOR_ID}
    value.validate_executor_binding()
    monkeypatch.setitem(value.EXECUTOR_FILES, "executor.py", "0" * 64)
    with pytest.raises(ValueError, match="binding"):
        value.validate_executor_binding()


def test_import_does_not_load_development_libraries(monkeypatch: pytest.MonkeyPatch):
    original = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("development library imported at module load")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    load()


def test_reconstructs_committed_public_open_fresh96_targets(tmp_path: Path):
    value = load()
    schedule = freeze(tmp_path / "freeze")
    reconstructed = value.reconstruct_open_targets(tmp_path / "freeze")
    assert reconstructed == schedule
    assert len(reconstructed["cells"]) == 64
    assert {row["partition"] for row in reconstructed["cells"]} == {"open_validation_development"}
    assert len({row["prompt_group_id"] for row in reconstructed["cells"]}) == 16


def test_independent_64_receipt_projection_uses_equal_prompt_group_weighting(tmp_path: Path):
    value = load()
    schedule = freeze(tmp_path / "freeze")
    projected = value._project(schedule, collector(value, schedule))
    rows = {row["candidate_id"]: row for row in projected["metrics"]}
    assert rows[value.PARENT]["cells"] == rows[value.CHILD]["cells"] == 32
    assert len(rows[value.PARENT]["group_mae"]) == len(rows[value.CHILD]["group_mae"]) == 16
    assert rows[value.CHILD]["equal_group_mae"] < rows[value.PARENT]["equal_group_mae"]
    optimizer = value.run_optuna(projected["metrics"])
    decision = value.qualify(projected["metrics"], optimizer)
    assert optimizer["sampler"] == "GridSampler" and optimizer["completed_trials"] == 12
    assert decision["qualifiers"] == [value.CHILD]
    dspy = value.build_dspy_evidence(projected["metrics"], decision)
    assert dspy["lm_calls"] == dspy["predict_calls"] == 0 and dspy["evidence_examples"] == 2


@pytest.mark.parametrize("mutation", ("partial", "duplicate_identity", "payload", "zero", "placeholder", "coverage", "evidence", "score"))
def test_rejects_partial_duplicate_misassociated_and_placeholder_native_receipts(tmp_path: Path, mutation: str):
    value = load()
    schedule = freeze(tmp_path / "freeze")
    evidence = collector(value, schedule)
    if mutation == "partial":
        evidence["cells"].pop()
    elif mutation == "duplicate_identity":
        evidence["cells"][1]["identity"] = dict(evidence["cells"][0]["identity"])
    elif mutation == "payload":
        evidence["cells"][0]["payload_sha256"] = "0" * 64
    else:
        first = evidence["cells"][0]
        response = value.strict(base64.b64decode(first["native_response_base64"]), "fixture")
        structured = response["structuredOutput"]
        if mutation == "zero":
            structured["scores"] = {dimension: 0.0 for dimension in value.DIMENSIONS}
        elif mutation == "placeholder":
            structured["evidence"]["Coherence"] = "[placeholder]"
        elif mutation == "coverage":
            structured["coverage"]["Coherence"] = "yes"
        elif mutation == "evidence":
            structured["evidence"]["Coherence"] = 3
        else:
            structured["scores"]["Coherence"] = True
        raw = value.canonical(response)
        first["native_response_base64"] = base64.b64encode(raw).decode("ascii")
        first["native_response_sha256"] = value.sha256(raw)
    with pytest.raises((TypeError, ValueError), match="collector|identity|binding|native|placeholder|partial"):
        value._project(schedule, evidence)


def test_replay_rejects_caller_aggregate_and_writes_only_fresh_result(tmp_path: Path):
    value = load()
    schedule = freeze(tmp_path / "freeze")
    path = tmp_path / "collector.json"
    path.write_bytes(value.canonical(collector(value, schedule)))
    projection = value.replay_projection(freeze_root=tmp_path / "freeze", collector_path=path)
    assert projection["source_execution"]["executor_binding"]["status"] == "exact_committed"
    tampered = value.strict(path.read_bytes(), "fixture")
    tampered["metrics"] = []
    path.write_bytes(value.canonical(tampered))
    with pytest.raises(ValueError, match="caller aggregate"):
        value.replay_projection(freeze_root=tmp_path / "freeze", collector_path=path)
