from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v3-executor-v1"
executor = load_module(PACKAGE / "executor.py", name="hanna_v3_executor_v1")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}


@pytest.fixture(scope="module")
def schedule_and_v3():
    v3 = executor._load_v3()
    return v3.derive_schedule(**ROOTS), v3


def _gate_files(tmp_path: Path, schedule: dict, v3, row: dict) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    payload = executor._payload(v3, row, **ROOTS)
    disclosure = {
        "format_version": 1, "study_id": executor.STUDY_ID, "kind": "pre_contact_local_first_disclosure",
        "cell": {name: row[name] for name in executor.CELL_FIELDS}, "schedule_sha256": schedule["schedule_sha256"],
        "route_identity": executor._route_identity(row),
        "artifacts_leaving_machine": {"outbound_payload": {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "text": payload.decode("utf-8")}},
        "provider_calls_made": 0,
    }
    acknowledgement = tmp_path / "ack.json"
    proof = tmp_path / "proof.json"
    for path, kind in ((acknowledgement, "acknowledgement"), (proof, "zero_charge_route_proof")):
        path.write_bytes(executor.canonical({"format_version": 1, "study_id": executor.STUDY_ID, "kind": kind, "cell_id": row["cell_id"], "disclosure_sha256": executor.digest(disclosure), "acknowledged": True, "attestor": "test"}))
    return acknowledgement, proof


def _trusted(event: dict):
    assert event["gate_kind"] in {"acknowledgement", "zero_charge_route_proof"}
    return {"accepted": True}


def _response() -> dict:
    dimensions = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    return {"scores": {name: 3.0 for name in dimensions}, "evidence": {name: "observed" for name in dimensions}, "coverage": {name: True for name in dimensions}}


@pytest.fixture(autouse=True)
def _private_gate(monkeypatch):
    monkeypatch.setattr(executor, "_load_pinned_gate_verifier", lambda: _trusted)
    monkeypatch.setattr(executor, "_load_pinned_native_request_verifier", lambda: lambda event: {"accepted": True})


def test_prepare_freezes_identical_cross_model_payload_bytes(schedule_and_v3, tmp_path: Path) -> None:
    schedule, v3 = schedule_and_v3
    grok = {(row["item_id"], row["candidate_id"]): row for row in schedule["grok_primary"]}
    sol = next(row for row in schedule["sol_validation"] if (row["item_id"], row["candidate_id"]) in grok)
    left, right = grok[(sol["item_id"], sol["candidate_id"])], sol
    left_ack, left_proof = _gate_files(tmp_path / "left", schedule, v3, left)
    right_ack, right_proof = _gate_files(tmp_path / "right", schedule, v3, right)
    executor.prepare_cell(**ROOTS, cell_id=left["cell_id"], output_root=tmp_path / "output", acknowledgement_path=left_ack, route_proof_path=left_proof)
    executor.prepare_cell(**ROOTS, cell_id=right["cell_id"], output_root=tmp_path / "output", acknowledgement_path=right_ack, route_proof_path=right_proof)
    assert (tmp_path / "output" / left["cell_id"] / "outbound-payload.json").read_bytes() == (tmp_path / "output" / right["cell_id"] / "outbound-payload.json").read_bytes()


def test_disclosure_and_confirmation_fail_before_contact(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    cell = schedule["grok_primary"][0]
    calls = []
    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: calls.append("runner"))
    with pytest.raises(ValueError, match="acknowledgement"):
        executor.prepare_cell(**ROOTS, cell_id=cell["cell_id"], output_root=tmp_path / "output", acknowledgement_path=tmp_path / "missing", route_proof_path=tmp_path / "missing-proof")
    assert calls == []
    with pytest.raises(ValueError, match="confirmation"):
        executor.prepare_cell(**ROOTS, cell_id="confirmation-never-scheduled", output_root=tmp_path / "output", acknowledgement_path=tmp_path / "missing", route_proof_path=tmp_path / "missing-proof")


def test_contact_once_then_reconcile_required_never_resends(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    cell = schedule["grok_primary"][0]
    acknowledgement, proof = _gate_files(tmp_path, schedule, v3, cell)
    executor.prepare_cell(**ROOTS, cell_id=cell["cell_id"], output_root=tmp_path / "output", acknowledgement_path=acknowledgement, route_proof_path=proof)
    calls = []
    def runner(row, payload, before_contact):
        calls.append((row, payload))
        before_contact()
        raise TimeoutError("ambiguous after dispatch")
    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: runner)
    first = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "output", cell_id=cell["cell_id"], allow_remote=True)
    second = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "output", cell_id=cell["cell_id"], allow_remote=True)
    assert first["state"] == "reconcile_required" and first["provider_calls_made"] == 1
    assert second == {"cell_id": cell["cell_id"], "state": "reconcile_required", "provider_calls_made": 0, "resumed": True}
    assert len(calls) == 1


def test_precontact_runner_failure_stays_pending_and_resume_revalidates_root(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    cell = schedule["grok_primary"][0]
    acknowledgement, proof = _gate_files(tmp_path, schedule, v3, cell)
    executor.prepare_cell(**ROOTS, cell_id=cell["cell_id"], output_root=tmp_path / "output", acknowledgement_path=acknowledgement, route_proof_path=proof)
    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: (_ for _ in ()).throw(ValueError("not installed")))
    assert executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "output", cell_id=cell["cell_id"], allow_remote=True) == {"cell_id": cell["cell_id"], "state": "pending_precontact", "provider_calls_made": 0}
    assert not (tmp_path / "output" / cell["cell_id"] / "intent.json").exists()
    (tmp_path / "output" / cell["cell_id"] / "outbound-payload.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="prepared root binding drifted"):
        executor.prepare_cell(**ROOTS, cell_id=cell["cell_id"], output_root=tmp_path / "output", acknowledgement_path=acknowledgement, route_proof_path=proof)


def test_native_identity_misassociation_is_rejected(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    cell = schedule["grok_primary"][0]
    acknowledgement, proof = _gate_files(tmp_path, schedule, v3, cell)
    executor.prepare_cell(**ROOTS, cell_id=cell["cell_id"], output_root=tmp_path / "output", acknowledgement_path=acknowledgement, route_proof_path=proof)
    def runner(_row, _payload, before_contact):
        before_contact()
        return {"request_bytes": b"native request", "response_bytes": executor.canonical({"modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "sessionId": "s", "requestId": "r", "structuredOutput": _response()}), "identity": {"provider": "xai", "requested_model": "grok-4.6", "reported_model": "wrong", "transport_identity": cell["transport_identity"], "native_response_id": "response", "native_request_id": "r", "native_session_id": "s"}}
    monkeypatch.setattr(executor, "_load_pinned_runner", lambda: runner)
    result = executor.dispatch_prepared_cell(**ROOTS, output_root=tmp_path / "output", cell_id=cell["cell_id"], allow_remote=True)
    assert result["state"] == "reconcile_required"


def test_projection_has_no_caller_aggregate_path_and_requires_native_cells(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="acknowledgement is invalid"):
        executor.project_mandatory_cells(**ROOTS, output_root=tmp_path / "no-native-cells")


def test_full_prepared_persisted_native_projection_freezes_grok_then_validates_sol(schedule_and_v3, tmp_path: Path, monkeypatch) -> None:
    schedule, v3 = schedule_and_v3
    all_rows = executor._all_mandatory(schedule)
    rows = [row for row in all_rows if row["partition"] == "development"]
    assert len(all_rows) == 460
    assert len(rows) == 100
    assert sum(row["model"] == "grok-4.6" for row in rows) == 65
    assert sum(row["model"] == "gpt-5.6-sol" for row in rows) == 35
    targets = executor._scheduled_targets(v3=v3, rows=rows, **ROOTS)
    assert set(targets) == {row["item_id"] for row in rows}
    _parent_study, _harness, _freeze, _split, candidates = v3._material(**ROOTS)
    freeze_module = v3.v2_module().parent_modules()[2]
    material = freeze_module._source_material(**ROOTS)
    by_candidate = {candidate["candidate_id"]: candidate for candidate in candidates}
    def exact_payload(_v3, row, **_roots):
        candidate, source = by_candidate[row["candidate_id"]], material[row["item_id"]]
        components = {
            "task_payload": freeze_module._payload_bytes(item=source, candidate=candidate).decode("utf-8"),
            "candidate_instruction": candidate["instruction_bytes"].decode("utf-8"),
            "candidate_profile": candidate["profile_bytes"].decode("utf-8"),
            "response_schema": freeze_module.response_schema_bytes().decode("utf-8"),
            "prompt": source["prompt"], "story": source["story"],
        }
        return executor.canonical({"format_version": 1, "study_id": executor.STUDY_ID, "components": components})
    monkeypatch.setattr(executor, "_load_v3", lambda: v3)
    monkeypatch.setattr(v3, "derive_schedule", lambda **_roots: schedule)
    monkeypatch.setattr(executor, "_payload", exact_payload)
    for index, row in enumerate(rows):
        root = tmp_path / "native" / row["cell_id"]
        acknowledgement, proof = _gate_files(tmp_path / "gates" / row["cell_id"], schedule, v3, row)
        executor.prepare_cell(**ROOTS, cell_id=row["cell_id"], output_root=tmp_path / "native", acknowledgement_path=acknowledgement, route_proof_path=proof)
        response = _response()
        response["scores"] = dict(targets[row["item_id"]])
        request_id, session_id, response_id = f"request-{index}", f"session-{index}", f"response-{index}"
        if row["provider"] == "xai":
            native = {"modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1, "sessionId": session_id, "requestId": request_id, "structuredOutput": response}
            reported = "grok-4.6-build"
        else:
            native = {"id": response_id, "model": row["model"], "choices": [{"message": {"content": json.dumps(response)}}]}
            reported = row["model"]
        request = f"request-bytes-{index}".encode()
        native_bytes = executor.canonical(native)
        identity = {"provider": row["provider"], "requested_model": row["model"], "reported_model": reported, "transport_identity": row["transport_identity"], "native_response_id": response_id, "native_request_id": request_id, "native_session_id": session_id}
        prepared = executor._read_canonical(root / "prepared.json", label="prepared")
        intent = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "intent_before_native_contact", "cell_id": row["cell_id"], "prepared_sha256": executor.digest(prepared), "provider_calls_made_before_intent": 0}
        (root / "intent.json").write_bytes(executor.canonical(intent))
        (root / "native-request.bin").write_bytes(request)
        (root / "native-response.bin").write_bytes(native_bytes)
        result = {"format_version": 1, "study_id": executor.STUDY_ID, "kind": "native_cell_result", "state": "native_returned_unprojected", "cell_id": row["cell_id"], "intent_sha256": executor.digest(intent), "native_request_sha256": hashlib.sha256(request).hexdigest(), "native_response_sha256": hashlib.sha256(native_bytes).hexdigest(), "identity": identity, "identity_sha256": executor.digest(identity), "provider_calls_made": 1}
        (root / "result.json").write_bytes(executor.canonical(result))
    projected = executor.project_mandatory_cells(**ROOTS, output_root=tmp_path / "native")
    assert projected["grok_selection"]["selected_candidate_id"] in schedule["candidate_ids"]
    assert projected["sol_validation"]["grok_selected_candidate_id"] == projected["grok_selection"]["selected_candidate_id"]
    assert projected["sol_validation"]["status"] == "sol_generalization_gate_passed"
    assert projected["confirmation"] == {"status": "unopened", "scheduled_cells": 0}
    assert projected["empirical_authority"].startswith("none_")


def test_runtime_never_imports_optimizer_packages(monkeypatch) -> None:
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("optimizer import is forbidden at runtime")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    assert executor._load_pinned_runner.__name__ == "_load_pinned_runner"
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8")
    assert "import dspy" not in source and "import optuna" not in source
