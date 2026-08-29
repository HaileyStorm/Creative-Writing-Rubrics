from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-development-optimizer-v1"
optimizer = load_module(PACKAGE / "optimizer.py", name="hanna_optimizer_v4_development")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}


@pytest.fixture(scope="module")
def schedule_and_v3():
    v3, native = optimizer._load_v3(), optimizer._load_native()
    return native.derive_schedule(**ROOTS), v3, native


def _response(scores: dict[str, float]) -> dict:
    return {"scores": scores, "evidence": {name: "observed" for name in optimizer.DIMENSIONS}, "coverage": {name: True for name in optimizer.DIMENSIONS}}


def _evidence(tmp_path: Path, schedule: dict, v3) -> Path:
    rows = optimizer._training_rows(schedule)
    targets = optimizer._targets(v3=v3, rows=rows, **ROOTS)
    cells = []
    for index, row in enumerate(rows):
        request_id, session_id, response_id = f"request-{index}", f"session-{index}", f"response-{index}"
        response = _response(dict(targets[row["item_id"]]))
        if row["route_name"] == "grok_primary":
            native = {"modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "sessionId": session_id, "requestId": request_id, "structuredOutput": response}
            reported = "grok-4.6-build"
        else:
            native = response
            reported = None
        route = row["route"]
        contact_id = request_id if row["route_name"] == "grok_primary" else response_id
        cells.append({
            "cell_id": row["cell_id"], "parent_cell_id": row["parent_cell_id"], "candidate_id": row["candidate_id"], "task_payload_sha256": row["task_payload_sha256"], "prompt_binding_sha256": optimizer._prompt_binding(row),
            "route_name": row["route_name"], "route_sha256": optimizer.sha256(route),
            "native_request_base64": base64.b64encode(f"request-{index}".encode()).decode(),
            "native_response_base64": base64.b64encode(optimizer.canonical(native)).decode(),
            "native_identity": {"provider": route["provider"], "route_name": route["route_name"], "requested_model": route["requested_model"], "requested_reasoning_effort": route["requested_reasoning_effort"], "effective_model": route["effective_model"], "provider_reported_model": reported, "identity_evidence": route["identity_evidence"], "reasoning_attested": False, "transport_identity": route["transport_identity"], "contact_id": contact_id, "session_id": session_id},
        })
    evidence = {"format_version": 1, "study_id": optimizer.STUDY_ID, "kind": "verified_persisted_v4_native_subscription_training_cells", "v4_native_schedule_sha256": schedule["schedule_sha256"], "cells": cells}
    path = tmp_path / "native-training-evidence.json"
    path.write_bytes(optimizer.canonical(evidence))
    return path


def _verified(event: dict) -> dict:
    expected = dict(event["expected"])
    cell = event["cell"]["cell_id"].encode()
    return {**expected, "prepared_sha256": hashlib.sha256(b"prepared-" + cell).hexdigest(), "intent_sha256": hashlib.sha256(b"intent-" + cell).hexdigest(), "result_sha256": hashlib.sha256(b"result-" + cell).hexdigest()}


def test_optuna_executes_real_deterministic_training_search(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3, _native = schedule_and_v3
    evidence = _evidence(tmp_path, schedule, v3)
    with pytest.raises(ValueError, match="no enabled persisted-native evidence verifier"):
        optimizer.optimize_training_evidence(**ROOTS, native_training_evidence_path=evidence)
    monkeypatch.setattr(optimizer, "_load_pinned_evidence_verifier", lambda: _verified)
    if importlib.util.find_spec("optuna") is None:
        with pytest.raises(ValueError, match="Optuna development dependency is not installed"):
            optimizer.optimize_training_evidence(**ROOTS, native_training_evidence_path=evidence)
        return
    result = optimizer.optimize_training_evidence(**ROOTS, native_training_evidence_path=evidence, seed=17)
    assert result["geometry"] == {"training_cells": 360, "grok_training_cells": 240, "sol_training_cells": 120, "development_cells_admitted": 0, "confirmation_cells_admitted": 0, "candidate_count": 5}
    assert result["lineage"]["v4_native_schedule_sha256"] == schedule["schedule_sha256"]
    assert result["lineage"]["native_training_evidence_sha256"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert result["optimizer_interfaces"]["optuna"] == "development_only_executed"
    assert result["best_trial"]["candidate_id"] in schedule["candidate_ids"]
    assert result["empirical_authority"].startswith("none_")


def test_rejects_verifier_denial_development_leakage_and_caller_aggregates(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3, _native = schedule_and_v3
    evidence = _evidence(tmp_path, schedule, v3)
    monkeypatch.setattr(optimizer, "_load_pinned_evidence_verifier", lambda: lambda event: {"accepted": False})
    with pytest.raises(ValueError, match="evidence verifier rejected"):
        optimizer.optimize_training_evidence(**ROOTS, native_training_evidence_path=evidence)
    monkeypatch.setattr(optimizer, "_load_pinned_evidence_verifier", lambda: _verified)
    value = json.loads(evidence.read_text(encoding="utf-8"))
    development = next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary")
    value["cells"][0]["cell_id"] = development["cell_id"]
    evidence.write_bytes(optimizer.canonical(value))
    with pytest.raises(ValueError, match="training cell order/binding drifted"):
        optimizer.optimize_training_evidence(**ROOTS, native_training_evidence_path=evidence)
    value = json.loads(_evidence(tmp_path, schedule, v3).read_text(encoding="utf-8"))
    value["cells"][0] = {"aggregate": 1}
    evidence.write_bytes(optimizer.canonical(value))
    with pytest.raises(ValueError, match="caller aggregates or synthetic cell shapes"):
        optimizer.optimize_training_evidence(**ROOTS, native_training_evidence_path=evidence)


def test_dspy_is_optional_development_only() -> None:
    if importlib.util.find_spec("dspy") is None:
        with pytest.raises(ValueError, match="DSPy development adapter is not installed"):
            optimizer.load_dspy_proposer()
    source = (PACKAGE / "optimizer.py").read_text(encoding="utf-8")
    assert "import dspy" in source and "import optuna" in source


def test_dspy_constructs_local_frozen_descendant_without_lm(schedule_and_v3, monkeypatch) -> None:
    _schedule, v3, _native = schedule_and_v3
    dspy = optimizer.load_dspy_proposer()
    calls = []
    monkeypatch.setattr(dspy, "configure", lambda *args, **kwargs: calls.append((args, kwargs)))
    proposer = optimizer.build_dspy_frozen_candidate_proposer()
    assert isinstance(proposer, dspy.Module)
    assert {"parent_candidate_id", "parent_instruction_bytes_base64", "parent_profile_bytes_base64", "frozen_training_diagnostics_json"} <= set(proposer.signature.input_fields)
    assert {"descendant_instruction_bytes_base64", "descendant_profile_bytes_base64", "descendant_candidate_sha256"} <= set(proposer.signature.output_fields)
    parent = v3.candidate_pack()[0]
    before = {name: parent[name] for name in ("candidate_id", "candidate_sha256", "instruction_bytes", "profile_bytes", "instruction_sha256", "profile_sha256")}
    diagnostics = {"native_training_evidence_sha256": "1" * 64, "endpoint_sha256": "2" * 64, "train_partition": "train"}
    proposed_instruction = parent["instruction_bytes"] + b"\nDSPy local fake proposal."
    proposed_profile = optimizer.canonical({"proposal": "local fake predictor output"})
    proposed_sha = optimizer.sha256({"parent_candidate_sha256": parent["candidate_sha256"], "instruction_sha256": hashlib.sha256(proposed_instruction).hexdigest(), "profile_sha256": hashlib.sha256(proposed_profile).hexdigest(), "diagnostics_sha256": optimizer.sha256(diagnostics)})
    predictor_calls = []
    def fake_predict(**inputs):
        predictor_calls.append(inputs)
        return SimpleNamespace(descendant_instruction_bytes_base64=base64.b64encode(proposed_instruction).decode(), descendant_profile_bytes_base64=base64.b64encode(proposed_profile).decode(), descendant_candidate_sha256=proposed_sha)
    proposer.predict = fake_predict
    result = proposer(parent=parent, diagnostics=diagnostics)
    assert calls == [] and len(predictor_calls) == 1 and result["predictor_invoked"] is True
    assert {name: parent[name] for name in before} == before
    assert base64.b64decode(result["descendant_instruction_bytes_base64"]) != parent["instruction_bytes"]
    profile = json.loads(base64.b64decode(result["descendant_profile_bytes_base64"]))
    assert profile["candidate_kind"] == "dspy_predict_training_descendant"
    assert profile["dspy_program"] == "Predict(FrozenTrainingDescendantSignature)"
    assert profile["runtime_authority"] == "none"
