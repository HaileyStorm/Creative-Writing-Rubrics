from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-lean-pilot"
INPUT_ROOT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")


def _study():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2", ROOT / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _commit(root: Path, path: Path) -> dict:
    return {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _native(study, prepared_root: Path, *, request_id: str, response: dict, output: Path) -> dict:
    raw = (prepared_root / "prepared-cell.json").read_bytes()
    prepared = json.loads(raw.decode("utf-8"))
    intent = study.begin_one_launch(prepared_root=prepared_root)
    receipt = {"prepared_record_sha256": hashlib.sha256(raw).hexdigest(), "launch_intent_sha256": hashlib.sha256(study.canonical(intent) + b"\n").hexdigest(), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_request_id": request_id, "session_id": f"session-{request_id}", "status": 200, "provider_model": prepared["provider_model"], "reasoning": prepared["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": prepared["payload"]["sha256"], "returned_response_sha256": hashlib.sha256(study.canonical(response)).hexdigest(), "response": response}
    return study.validate_receipt(prepared_root=prepared_root, receipt=receipt, output_path=output)


def _frozen(study, tmp_path: Path) -> Path:
    if not INPUT_ROOT.is_dir():
        pytest.skip(f"exact local HANNA input fixture is unavailable: {INPUT_ROOT}")
    work = tmp_path / "work"
    frozen = study.freeze_inputs(source_root=INPUT_ROOT, work_root=work)
    assert frozen["source_material_copied"] is False
    assert (work / "frozen-cwr-question-payload.json").is_file()
    return work


def _lineage(study, tmp_path: Path, work: Path) -> list[dict]:
    records, descendants, value = [], {}, study.contract()
    for event in study.revision_schedule():
        feedback_path = None
        if event["guidance_arm"] == "cwr_guided":
            feedback_root = tmp_path / "feedback" / event["event_id"]
            study.prepare_cell(work_root=work, prepared_root=feedback_root, phase="cwr_feedback", event_id=event["cwr_feedback_event_id"], acknowledgement_sha256="a" * 64, source_root=INPUT_ROOT, revision_records=records)
            feedback_path = work / "receipts" / f"{event['cwr_feedback_event_id']}.json"
            _native(study, feedback_root, request_id=f"feedback-{event['event_id']}", response={"findings": [{"location": "opening", "observation": "specific issue", "repair_target": "repair it"}]}, output=feedback_path)
        revision_root = tmp_path / "revision" / event["event_id"]
        study.prepare_cell(work_root=work, prepared_root=revision_root, phase="revision_generation", event_id=event["event_id"], acknowledgement_sha256="a" * 64, source_root=INPUT_ROOT, revision_records=records, feedback_receipt_path=feedback_path)
        receipt_path = work / "receipts" / f"{event['event_id']}.json"
        story = f"immutable {event['event_id']}"
        _native(study, revision_root, request_id=f"revision-{event['event_id']}", response={"story": story}, output=receipt_path)
        descendant_path = work / "descendants" / f"{event['event_id']}.md"
        descendant_path.parent.mkdir(parents=True, exist_ok=True)
        descendant_path.write_text(story, encoding="utf-8")
        source = value["sources"]["items"][event["source_item_id"]]
        records.append({"event_id": event["event_id"], "source": {"item_id": event["source_item_id"], "source.md": source["source.md"], "prompt.md": source["prompt.md"]}, "parent": None if event["parent_event_id"] is None else {"event_id": event["parent_event_id"], "descendant": descendants[event["parent_event_id"]]}, "descendant": _commit(work, descendant_path), "generator": {"model": "grok-4.6", "reasoning": "high", "tools_enabled": False}, "generator_receipt": _commit(work, receipt_path), "cwr_feedback": None if feedback_path is None else {"event_id": event["cwr_feedback_event_id"], "verified_receipt": _commit(work, feedback_path)}})
        descendants[event["event_id"]] = records[-1]["descendant"]
    return records


def test_contract_pins_current_runner_exact_sources_geometry_and_tools_disabled() -> None:
    study = _study()
    value = study.contract()
    assert value["cwr_runtime"]["runner"] == {"path": "src/hbqrs/runner.py", "bytes": 190321, "sha256": "de1dccd28c8ba544207b3b000d086948fa8c429a327b055762e8d7032e3fa938"}
    assert sorted(value["sources"]["items"]) == ["hanna-1035", "hanna-178"]
    assert value["geometry"] == {"sources": 2, "cycles": 2, "arms": 2, "revision_cells": 8, "cwr_feedback_cells": 4, "blind_targets": 10, "endpoint_cells": 40, "remote_contacts": 52}
    assert all(route["tools_enabled"] is False and route["paid_api"] is False for route in [value["routes"]["generator"], value["routes"]["cwr_feedback"], *value["routes"]["judges"].values()])


def test_freeze_preparation_and_receipts_bind_real_runner_payload_source_and_hex_acknowledgement(tmp_path: Path) -> None:
    study = _study()
    work = _frozen(study, tmp_path)
    event = study.revision_schedule()[0]
    prepared = study.prepare_cell(work_root=work, prepared_root=tmp_path / "feedback", phase="cwr_feedback", event_id=event["cwr_feedback_event_id"], acknowledgement_sha256="a" * 64, source_root=INPUT_ROOT)
    payload = json.loads((tmp_path / "feedback" / "payload.json").read_text(encoding="utf-8"))
    assert prepared["provider_calls_made"] == prepared["process_launches"] == 0
    assert payload["question_payload"] == study._cwr_question_payload(study.contract())
    assert payload["source_text"] == (INPUT_ROOT / "inputs" / event["source_item_id"] / "source.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        study.prepare_cell(work_root=work, prepared_root=tmp_path / "bad", phase="cwr_feedback", event_id=event["cwr_feedback_event_id"], acknowledgement_sha256="A" * 64, source_root=INPUT_ROOT)
    verified = _native(study, tmp_path / "feedback", request_id="feedback-1", response={"findings": []}, output=work / "receipts" / "feedback.json")
    assert verified["kind"] == "verified_native_receipt" and verified["session_id"] == "session-feedback-1"
    with pytest.raises(ValueError, match="terminal"):
        study.prepare_cell(work_root=work, prepared_root=tmp_path / "feedback", phase="cwr_feedback", event_id=event["cwr_feedback_event_id"], acknowledgement_sha256="a" * 64, source_root=INPUT_ROOT)
    tampered_root = tmp_path / "tampered"
    study.prepare_cell(work_root=work, prepared_root=tampered_root, phase="cwr_feedback", event_id=event["cwr_feedback_event_id"], acknowledgement_sha256="a" * 64, source_root=INPUT_ROOT)
    (tampered_root / "payload.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="commitment drifted"):
        _native(study, tampered_root, request_id="tampered", response={"findings": []}, output=work / "receipts" / "tampered.json")
    assert not (tampered_root / "launch-intent.json").exists()


def test_fabricated_sources_and_unfrozen_endpoint_targets_fail_closed(tmp_path: Path) -> None:
    study = _study()
    fake = tmp_path / "fake"
    for item_id in study.contract()["sources"]["items"]:
        path = fake / "inputs" / item_id
        path.mkdir(parents=True)
        (path / "source.md").write_text("fabricated", encoding="utf-8")
        (path / "prompt.md").write_text("fabricated", encoding="utf-8")
    with pytest.raises(ValueError, match="binding drifted"):
        study.freeze_inputs(source_root=fake, work_root=tmp_path / "bad-work")
    work = _frozen(study, tmp_path)
    endpoint = study.endpoint_schedule()[0]
    with pytest.raises(ValueError, match="frozen target manifest"):
        study.prepare_cell(work_root=work, prepared_root=tmp_path / "unfrozen", phase="blind_endpoint_judgment", event_id=endpoint["endpoint_event_id"], acknowledgement_sha256="b" * 64)


def test_lineage_binds_each_guided_sol_receipt_each_grok_receipt_and_cycle_two_parent(tmp_path: Path) -> None:
    study = _study()
    work = _frozen(study, tmp_path)
    records = _lineage(study, tmp_path, work)
    assert study.validate_revision_lineage(work_root=work, records=records)["record_count"] == 8
    records[-1]["parent"] = None
    with pytest.raises(ValueError, match="parent lineage"):
        study.validate_revision_lineage(work_root=work, records=records)
    records[-1]["parent"] = {"event_id": study.revision_schedule()[-1]["parent_event_id"], "descendant": records[3]["descendant"]}
    records[-1]["descendant"]["path"] = "inputs/hanna-178/source.md"
    with pytest.raises(ValueError, match="descendant"):
        study.validate_revision_lineage(work_root=work, records=records)
    cycle_two = study.revision_schedule()[4]
    forged_parent = dict(records[0])
    forged_parent.pop("generator_receipt")
    with pytest.raises(ValueError, match="parent record"):
        study.prepare_cell(work_root=work, prepared_root=tmp_path / "forged-parent", phase="cwr_feedback", event_id=cycle_two["cwr_feedback_event_id"], acknowledgement_sha256="a" * 64, source_root=INPUT_ROOT, revision_records=[forged_parent])


def test_targets_are_frozen_and_projection_uses_only_persisted_verified_receipts(tmp_path: Path) -> None:
    study = _study()
    work = _frozen(study, tmp_path)
    records = _lineage(study, tmp_path, work)
    target_root = tmp_path / "targets"
    manifest = study.prepare_targets(work_root=work, target_root=target_root, source_root=INPUT_ROOT, revision_records=records)
    assert len(manifest["targets"]) == 10
    receipt_paths = []
    payload_hashes = {}
    for event in study.endpoint_schedule():
        root = tmp_path / "endpoint" / event["endpoint_event_id"]
        prepared = study.prepare_cell(work_root=work, prepared_root=root, phase="blind_endpoint_judgment", event_id=event["endpoint_event_id"], acknowledgement_sha256="b" * 64, target_root=target_root, target_manifest_path=target_root / "target-manifest.json")
        key = (event["blind_target_id"], event["measure_id"])
        payload_hashes.setdefault(key, set()).add(prepared["payload"]["sha256"])
        score = 6 if "cwr_guided" in event["blind_target_id"] and event["measure_id"] == "holistic" else 4
        if event["measure_id"] == "compact":
            score = 4 if "cwr_guided" in event["blind_target_id"] else 3
        path = work / "endpoint-receipts" / f"{event['endpoint_event_id']}.json"
        _native(study, root, request_id=event["endpoint_event_id"], response={"overall": score, "rationale": "grounded"}, output=path)
        receipt_paths.append(path)
    projection = study.project_independent_metrics(endpoint_receipt_paths=receipt_paths)
    assert all(len(values) == 1 for values in payload_hashes.values())
    assert len(projection["primary_guided_minus_control"]) == 16
    assert len(projection["arm_minus_baseline"]) == 32
    assert all(row["guided_minus_control"] > 0 for row in projection["primary_guided_minus_control"])
    with pytest.raises(ValueError, match="incomplete"):
        study.project_independent_metrics(endpoint_receipt_paths=receipt_paths[:-1])
    fake = tmp_path / "minimal-handcrafted.json"
    fake.write_bytes(study.canonical({"study_id": study.STUDY_ID, "kind": "verified_native_receipt", "event_id": study.endpoint_schedule()[0]["endpoint_event_id"], "phase": "blind_endpoint_judgment"}) + b"\n")
    with pytest.raises(ValueError, match="handcrafted|revalidation"):
        study.project_independent_metrics(endpoint_receipt_paths=[fake, *receipt_paths[1:]])
    manifest_path = target_root / "target-manifest.json"
    manifest_path.write_bytes(study.canonical({**manifest, "targets": manifest["targets"][:1]}) + b"\n")
    with pytest.raises(ValueError, match="inventory"):
        study._target_from_manifest(target_root, manifest_path, manifest["targets"][0]["blind_target_id"], manifest["frozen_manifest_sha256"])
    forged = json.loads(study.canonical(manifest).decode("utf-8"))
    forged["targets"][0]["origin"]["source_item_id"] = "hanna-178"
    manifest_path.write_bytes(study.canonical(forged) + b"\n")
    with pytest.raises(ValueError, match="baseline target origin"):
        study._target_from_manifest(target_root, manifest_path, forged["targets"][0]["blind_target_id"], forged["frozen_manifest_sha256"])


def test_terminal_outcomes_never_offer_resend() -> None:
    study = _study()
    assert study.terminal_outcome(process_launches=0, settled=False) == {"state": "terminal_precontact", "fresh_output_root_required": True, "no_resend": True}
    assert study.terminal_outcome(process_launches=1, settled=False) == {"state": "terminal_postlaunch_reconcile_required", "fresh_output_root_required": False, "no_resend": True}


def test_one_launch_lifecycle_blocks_second_launch_and_persists_reconcile_terminal(tmp_path: Path) -> None:
    study = _study()
    work = _frozen(study, tmp_path)
    event = study.revision_schedule()[1]
    root = tmp_path / "control"
    study.prepare_cell(work_root=work, prepared_root=root, phase="revision_generation", event_id=event["event_id"], acknowledgement_sha256="c" * 64, source_root=INPUT_ROOT)
    assert study.begin_one_launch(prepared_root=root)["process_launches"] == 1
    with pytest.raises(FileExistsError):
        study.begin_one_launch(prepared_root=root)
    with pytest.raises(ValueError, match="cannot become precontact"):
        study.record_terminal_outcome(prepared_root=root, process_launches=0, settled=False)
    assert study.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)["state"] == "terminal_postlaunch_reconcile_required"
    with pytest.raises(ValueError, match="terminal"):
        study.begin_one_launch(prepared_root=root)


def test_receipt_schema_and_postlaunch_reconciliation_are_both_required(tmp_path: Path) -> None:
    study = _study()
    work = _frozen(study, tmp_path)
    event = study.revision_schedule()[0]
    root = tmp_path / "reconcile"
    study.prepare_cell(work_root=work, prepared_root=root, phase="cwr_feedback", event_id=event["cwr_feedback_event_id"], acknowledgement_sha256="d" * 64, source_root=INPUT_ROOT)
    raw = (root / "prepared-cell.json").read_bytes()
    prepared = json.loads(raw.decode("utf-8"))
    intent = study.begin_one_launch(prepared_root=root)
    bad = {"prepared_record_sha256": hashlib.sha256(raw).hexdigest(), "launch_intent_sha256": hashlib.sha256(study.canonical(intent) + b"\n").hexdigest(), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_request_id": "receipt-1", "session_id": "session-1", "status": 200, "provider_model": prepared["provider_model"], "reasoning": prepared["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": prepared["payload"]["sha256"], "returned_response_sha256": hashlib.sha256(study.canonical({"wrong": True})).hexdigest(), "response": {"wrong": True}}
    with pytest.raises(ValueError, match="feedback response schema"):
        study.validate_receipt(prepared_root=root, receipt=bad, output_path=work / "receipts" / "bad.json")
    good_response = {"findings": []}
    good = {**bad, "returned_response_sha256": hashlib.sha256(study.canonical(good_response)).hexdigest(), "response": good_response}
    assert study.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)["state"] == "terminal_postlaunch_reconcile_required"
    with pytest.raises(ValueError, match="reconciliation"):
        study.validate_receipt(prepared_root=root, receipt=good, output_path=work / "receipts" / "unreconciled.json")
    study.reconcile_postlaunch(prepared_root=root, acknowledgement_sha256="e" * 64)
    assert study.validate_receipt(prepared_root=root, receipt=good, output_path=work / "receipts" / "reconciled.json")["kind"] == "verified_native_receipt"
