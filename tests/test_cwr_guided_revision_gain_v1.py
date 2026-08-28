from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v1"
INPUT_ROOT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")


def _study():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v1", ROOT / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen(study) -> dict:
    value = study.contract()
    inputs = []
    for item_id in sorted(value["source_population"]["input_commitments"]):
        expected = value["source_population"]["input_commitments"][item_id]
        inputs.append({
            "item_id": item_id,
            "source": {"path": f"inputs/{item_id}/source.md", **expected["source.md"]},
            "prompt": {"path": f"inputs/{item_id}/prompt.md", **expected["prompt.md"]},
        })
    revisions, endpoints = study.revision_schedule(value), study.endpoint_schedule(value)
    return {
        "study_id": value["study_id"],
        "study_contract_sha256": study.sha256(study.CONTRACT_PATH),
        "parent_frozen_run_contract_sha256": value["source_population"]["parent_frozen_run_contract_sha256"],
        "source_root_not_persisted": True,
        "source_material_copied": False,
        "inputs": inputs,
        "revision_schedule": revisions,
        "revision_schedule_sha256": hashlib.sha256(study.canonical(revisions)).hexdigest(),
        "endpoint_schedule": endpoints,
        "endpoint_schedule_sha256": hashlib.sha256(study.canonical(endpoints)).hexdigest(),
    }


def _prepare_acknowledged_work(study, work: Path) -> dict:
    study.write_json(work / "frozen-inputs.json", _frozen(study))
    preview = study.write_disclosure_preview(work)
    acknowledgement = {"study_id": preview["study_id"], "preview_sha256": hashlib.sha256(study.canonical(preview)).hexdigest(), "acknowledged": True, "acknowledged_at": "2026-08-27T00:00:00Z"}
    study.write_json(work / study.INITIAL_ACKNOWLEDGEMENT, acknowledgement)
    return preview


def _revision_records(study, work: Path) -> list[dict]:
    if not INPUT_ROOT.is_dir():
        pytest.skip(f"exact local HANNA input fixture is unavailable: {INPUT_ROOT}")
    value = study.contract()
    frozen = _frozen(study)
    source = {row["item_id"]: row["source"] for row in frozen["inputs"]}
    prompts = {row["item_id"]: row["prompt"] for row in frozen["inputs"]}
    instructions = json.loads((study.HERE / value["generation"]["instruction_asset"]["path"]).read_text(encoding="utf-8"))
    instruction = {
        "asset_sha256": study.sha256(study.HERE / value["generation"]["instruction_asset"]["path"]),
        "neutral_base_instruction_sha256": hashlib.sha256(instructions["neutral_base_revision_instruction"].encode("utf-8")).hexdigest(),
    }
    def commitment(path: Path) -> dict:
        return {"path": path.relative_to(work).as_posix(), "bytes": path.stat().st_size, "sha256": study.sha256(path)}

    def receipt(request_id: str, response: dict, *, role: str, event_id: str, route: dict, sampler: dict, payload: dict) -> dict:
        receipt_root = work / "receipts" / request_id
        receipt_root.mkdir(parents=True, exist_ok=True)
        request = receipt_root / "request.json"
        payload_path = receipt_root / "payload.json"
        identity = receipt_root / "route-intent-profile.json"
        request.write_bytes(study.canonical({"event_id": event_id, "role": role, "route": route, "sampler": sampler}))
        evidence_field = "precomposition_input" if "precomposition_input" in payload else "provider_ready"
        evidence = payload[evidence_field]
        payload_path.write_bytes(study.canonical({"event_id": event_id, "role": role, "request_sha256": study.sha256(request), **{key: value for key, value in payload.items() if key != evidence_field}, evidence_field: evidence}))
        identity.write_bytes(study.canonical(route))
        return {
            "provider_request_id": request_id,
            "route_intent_profile": commitment(identity),
            "request": commitment(request),
            "payload": commitment(payload_path),
            "response": response,
            "request_sha256": study.sha256(request),
            "payload_sha256": study.sha256(payload_path),
            "response_sha256": response["sha256"],
        }

    sampler = {"temperature": 0, "top_p": 1, "seed": 7, "max_output_tokens": 1200}
    records, outputs = [], {}
    for event in study.revision_schedule(value):
        output = work / "descendants" / f"{event['event_id']}.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"descendant for {event['event_id']}", encoding="utf-8")
        descendant = commitment(output)
        source_commitment = {"item_id": event["source_item_id"], **source[event["source_item_id"]]}
        parent = None if event["cycle"] == 1 else {"event_id": event["parent_event_id"], **outputs[event["parent_event_id"]]}
        input_commitment = parent if parent is not None else source_commitment
        input_text = (work / parent["path"]).read_text(encoding="utf-8") if parent is not None else (INPUT_ROOT / source_commitment["path"]).read_text(encoding="utf-8")
        originating_prompt = (INPUT_ROOT / prompts[event["source_item_id"]]["path"]).read_text(encoding="utf-8")
        feedback = None
        if event["guidance_arm"] == "cwr_guided":
            feedback_path = work / "feedback" / f"{event['event_id']}.json"
            feedback_path.parent.mkdir(parents=True, exist_ok=True)
            feedback_path.write_bytes(study.canonical({"findings": [{"location": "Opening image", "observation": f"A specific revision issue for {event['event_id']} remains visible.", "repair_target": "Clarify the image without changing the event."}]}))
            feedback_route = study._route_identity(value, event["cwr_feedback_route_id"])
            feedback_artifact = commitment(feedback_path)
            feedback_receipt = receipt(f"feedback-{event['event_id']}", feedback_artifact, role="cwr_feedback", event_id=event["event_id"], route=feedback_route, sampler=dict(sampler), payload={"input": input_commitment, "feedback_instruction_sha256": study._sha256_value(instructions["cwr_feedback_packet"]), "cwr_runtime_sha256": study._sha256_value(value["cwr_runtime"]), "precomposition_input": {"input_text": input_text, "input_sha256": input_commitment["sha256"], "originating_prompt": originating_prompt, "prompt_sha256": prompts[event["source_item_id"]]["sha256"], "cwr_feedback_instruction": instructions["cwr_feedback_packet"]["instruction"], "cwr_runtime_sha256": study._sha256_value(value["cwr_runtime"])}})
            feedback = {
                "artifact": feedback_artifact,
                "generator": {"role": "cwr_feedback", **feedback_route, "sampler": dict(sampler), "receipt": feedback_receipt},
                "source_request_sha256": feedback_receipt["request_sha256"],
            }
        route = study._route_identity(value, event["generator_route_id"])
        generator_receipt = receipt(f"revision-{event['event_id']}", descendant, role="revision_generation", event_id=event["event_id"], route=route, sampler=dict(sampler), payload={"cycle": event["cycle"], "generator_id": event["generator_id"], "guidance_arm": event["guidance_arm"], "input": input_commitment, "instruction": instruction, "feedback": feedback["artifact"] if feedback is not None else None, "provider_ready": {"input_text": input_text, "input_sha256": input_commitment["sha256"], "originating_prompt": originating_prompt, "prompt_sha256": prompts[event["source_item_id"]]["sha256"], "instruction": instructions["neutral_base_revision_instruction"], "feedback": feedback_path.read_text(encoding="utf-8") if feedback is not None else None}})
        records.append({
            "record_type": "revision",
            "event_id": event["event_id"],
            "source": source_commitment,
            "parent": parent,
            "descendant": descendant,
            "instruction": instruction,
            "feedback": feedback,
            "generator": {"role": "revision_generation", "generator_id": event["generator_id"], **route, "sampler": dict(sampler), "receipt": generator_receipt},
        })
        outputs[event["event_id"]] = descendant
    return records


def test_revision_fixture_skips_only_when_the_exact_local_root_is_absent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    monkeypatch.setitem(globals(), "INPUT_ROOT", tmp_path / "absent-input-root")
    with pytest.raises(pytest.skip.Exception, match="fixture is unavailable"):
        _revision_records(study, tmp_path / "work")


def _endpoint_records(study, work: Path) -> tuple[dict[str, dict], list[dict]]:
    value = study.contract()
    sampler = {"temperature": 0, "top_p": 1, "seed": 7, "max_output_tokens": 1200}
    targets: dict[str, dict] = {}
    for blind_target_id in {event["blind_target_id"] for event in study.endpoint_schedule(value)}:
        path = work / "targets" / f"{blind_target_id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"The bell rang and rain fell for {blind_target_id}.", encoding="utf-8")
        targets[blind_target_id] = {"path": path.relative_to(work).as_posix(), "bytes": path.stat().st_size, "sha256": study.sha256(path)}
    measures = {measure["measure_id"]: measure for measure in value["endpoint_evaluation"]["measures"]}
    records: list[dict] = []
    for event in study.endpoint_schedule(value):
        measure = measures[event["measure_id"]]
        response = {"overall": measure["minimum"], "rationale": "The text is clear.", "evidence": [{"quote": "The bell rang", "explanation": "concrete action"}, {"quote": "rain fell", "explanation": "specific image"}]}
        if event["measure_id"] == "compact_analytic":
            response["dimensions"] = {"clarity": 1, "coherence": 1, "specificity": 1, "control": 1}
        response_path = work / "endpoint-responses" / f"{event['endpoint_event_id']}.json"
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_bytes(study.canonical(response))
        response_commitment = {"path": response_path.relative_to(work).as_posix(), "bytes": response_path.stat().st_size, "sha256": study.sha256(response_path)}
        route = study._route_identity(value, event["judge_route_id"])
        request_path = work / "endpoint-receipts" / f"{event['endpoint_event_id']}.request.json"
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_bytes(study.canonical({"event_id": event["endpoint_event_id"], "role": "blind_endpoint_judgment", "route": route, "sampler": sampler}))
        request = {"path": request_path.relative_to(work).as_posix(), "bytes": request_path.stat().st_size, "sha256": study.sha256(request_path)}
        instrument = {"prompt_sha256": measure["prompt"]["sha256"], "schema_sha256": measure["schema"]["sha256"]}
        payload_path = work / "endpoint-receipts" / f"{event['endpoint_event_id']}.payload.json"
        payload_path.write_bytes(study.canonical({"event_id": event["endpoint_event_id"], "role": "blind_endpoint_judgment", "request_sha256": request["sha256"], "blind_target_id": event["blind_target_id"], "target": targets[event["blind_target_id"]], "instrument": instrument, "provider_ready": {"target_text": (work / targets[event["blind_target_id"]]["path"]).read_text(encoding="utf-8"), "prompt": (study.HERE / measure["prompt"]["path"]).read_text(encoding="utf-8"), "schema": (study.HERE / measure["schema"]["path"]).read_text(encoding="utf-8")}}))
        payload = {"path": payload_path.relative_to(work).as_posix(), "bytes": payload_path.stat().st_size, "sha256": study.sha256(payload_path)}
        identity_path = work / "endpoint-receipts" / f"{event['endpoint_event_id']}.route-intent-profile.json"
        provider_request_id = f"endpoint-{event['endpoint_event_id']}"
        identity_path.write_bytes(study.canonical(route))
        identity = {"path": identity_path.relative_to(work).as_posix(), "bytes": identity_path.stat().st_size, "sha256": study.sha256(identity_path)}
        receipt = {"provider_request_id": provider_request_id, "route_intent_profile": identity, "request": request, "payload": payload, "response": response_commitment, "request_sha256": request["sha256"], "payload_sha256": payload["sha256"], "response_sha256": response_commitment["sha256"]}
        records.append({"record_type": "endpoint", "endpoint_event_id": event["endpoint_event_id"], "blind_target_id": event["blind_target_id"], "target": targets[event["blind_target_id"]], "instrument": instrument, "judge": {"role": "blind_endpoint_judgment", **route, "sampler": dict(sampler), "receipt": receipt}, "response": response})
    return targets, records


def test_contract_binds_exact_parent_inputs_runtime_instructions_and_instruments() -> None:
    study = _study()
    value = study.contract()
    source = value["source_population"]
    assert source["parent_frozen_run_contract_sha256"] == "5fb06e5a4775ecfe1cee10132e52100733c7e765e8eae9865374bb23f1addddd"
    assert source["pilot_item_ids"] == sorted(source["input_commitments"])[:6]
    assert source["held_back_item_ids"] == sorted(source["input_commitments"])[6:]
    assert value["provider_routes"]["deepseek-v4-flash-max"]["model"] == "deepseek/deepseek-v4-flash-0731"
    assert value["provider_routes"]["deepseek-v4-flash-max"]["reasoning"] == "max"
    assert value["endpoint_evaluation"]["non_cwr_primary"] is True
    assert all(not measure["prompt"]["path"].startswith("../") for measure in value["endpoint_evaluation"]["measures"])
    instructions = json.loads((study.HERE / value["generation"]["instruction_asset"]["path"]).read_text(encoding="utf-8"))
    assert set(instructions["arm_difference"]) == {"cwr_guided", "generic_no_feedback"}
    assert value["remote_disclosure"]["phase_call_counts"] == {"cwr_feedback": 24, "revision_generation": 48, "blind_endpoint_judgment": 216}
    assert value["reporting"]["raw_scale_pooling"] is False
    assert value["endpoint_evaluation"]["judging_protocol"] == {"blind": True, "stateless": True, "identical_prompt_per_measure_across_judges": True}


def test_revision_and_endpoint_schedules_are_fixed_anonymous_and_complete() -> None:
    study = _study()
    revisions = study.revision_schedule()
    endpoints = study.endpoint_schedule()
    assert len(revisions) == 48
    assert len([event for event in revisions if event["cycle"] == 1]) == 32
    assert len([event for event in revisions if event["cycle"] == 2]) == 16
    assert all(event["parent_event_id"].startswith("revision-v1-c1-") for event in revisions if event["cycle"] == 2)
    assert len(endpoints) == 216
    assert [event["dispatch_order"] for event in endpoints] == list(range(1, 217))
    assert all(set(event) == {"blind_target_id", "endpoint_event_id", "judge_route_id", "measure_id", "dispatch_order"} for event in endpoints)
    assert len({event["blind_target_id"] for event in endpoints}) == 54
    assert {(event["judge_route_id"], event["measure_id"]) for event in endpoints} == {
        ("gpt-5.6-sol-high", "holistic_anchored"), ("gpt-5.6-sol-high", "compact_analytic"),
        ("grok-4.6-high", "holistic_anchored"), ("grok-4.6-high", "compact_analytic"),
    }


def test_fake_prose_cannot_freeze_as_a_hanna_input(tmp_path: Path) -> None:
    study = _study()
    source_root = tmp_path / "external-inputs"
    for item_id in study.contract()["source_population"]["input_commitments"]:
        folder = source_root / "inputs" / item_id
        folder.mkdir(parents=True)
        (folder / "source.md").write_text("fabricated source", encoding="utf-8")
        (folder / "prompt.md").write_text("fabricated prompt", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen HANNA source.md binding drifted"):
        study.freeze_inputs(source_root, tmp_path / "work")


def test_frozen_input_and_acknowledgement_validation_are_exact_and_no_prose(tmp_path: Path) -> None:
    study = _study()
    work = tmp_path / "work"
    frozen = _frozen(study)
    study.write_json(work / "frozen-inputs.json", frozen)
    assert study.validate_frozen_inputs(work) == frozen
    preview = study.write_disclosure_preview(work)
    preview_text = (work / "disclosure-preview.json").read_text(encoding="utf-8")
    assert "provider_calls_made" in preview_text
    assert "fabricated source" not in preview_text
    assert preview["phases"] == {
        "cwr_feedback": {"call_count": 24, "payload_composition": study.contract()["remote_disclosure"]["payload_composition"]["cwr_feedback"]},
        "revision_generation": {"call_count": 48, "payload_composition": study.contract()["remote_disclosure"]["payload_composition"]["revision_generation"]},
        "blind_endpoint_judgment": {"call_count": 216, "payload_composition": study.contract()["remote_disclosure"]["payload_composition"]["blind_endpoint_judgment"]},
    }
    assert (work / "disclosure-preview.canonical.sha256").read_text(encoding="ascii") == hashlib.sha256(study.canonical(preview)).hexdigest() + "\n"
    acknowledgement = {
        "study_id": preview["study_id"],
        "preview_sha256": hashlib.sha256(study.canonical(preview)).hexdigest(),
        "acknowledged": True,
        "acknowledged_at": "2026-08-27T00:00:00Z",
    }
    acknowledgement_path = work / "acknowledgement.json"
    study.write_json(acknowledgement_path, acknowledgement)
    assert study.validate_disclosure_acknowledgement(work, acknowledgement_path) == acknowledgement
    study.write_json(work / "disclosure-preview.json", {"tampered": True})
    with pytest.raises(ValueError, match="preview binding"):
        study.validate_disclosure_acknowledgement(work, acknowledgement_path)
    study.write_json(work / "disclosure-preview.json", preview)
    acknowledgement["preview_sha256"] = "0" * 64
    study.write_json(acknowledgement_path, acknowledgement)
    with pytest.raises(ValueError, match="acknowledgement binding"):
        study.validate_disclosure_acknowledgement(work, acknowledgement_path)
    frozen = _frozen(study)
    frozen["unreviewed_prose"] = "must not enter a disclosure preview"
    study.write_json(work / "frozen-inputs-extra.json", frozen)
    (work / "frozen-inputs.json").unlink()
    (work / "frozen-inputs-extra.json").replace(work / "frozen-inputs.json")
    with pytest.raises(ValueError, match="contract binding"):
        study.validate_frozen_inputs(work)
    frozen = _frozen(study)
    frozen["inputs"][0]["source"]["path"] = "inputs/other/source.md"
    study.write_json(work / "frozen-inputs.json", frozen)
    with pytest.raises(ValueError, match="input fingerprint"):
        study.validate_frozen_inputs(work)


def test_scalar_difference_calculation_uses_validated_endpoint_manifest_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    study = _study()
    events = study.endpoint_schedule()
    values = study.contract()
    minimum = {measure["measure_id"]: measure["minimum"] for measure in values["endpoint_evaluation"]["measures"]}
    records = [{"endpoint_event_id": event["endpoint_event_id"], "response": {"overall": minimum[event["measure_id"]]}} for event in events]
    calls: list[tuple[Path, Path, Path]] = []
    def validated(work_root: Path, revision_manifest: Path, endpoint_manifest: Path) -> list[dict]:
        calls.append((work_root, revision_manifest, endpoint_manifest))
        return records
    monkeypatch.setattr(study, "validate_endpoint_lineage", validated)
    work, revisions, endpoints = tmp_path / "work", tmp_path / "revisions.jsonl", tmp_path / "endpoints.jsonl"
    result = study._calculate_differences_from_validated_records(records)
    assert len(result["primary_guided_minus_control"]) == 96
    assert {row["guided_minus_control"] for row in result["primary_guided_minus_control"]} == {0.0}
    assert len(result["cycle2_child_minus_cycle1_parent"]) == 64
    assert {row["guidance_arm"] for row in result["cycle2_child_minus_cycle1_parent"]} == {"cwr_guided", "generic_no_feedback"}
    assert len(result["equal_weight_summaries_by_judge_measure_scale"]) == 4
    assert {row["scale"]["maximum"] for row in result["equal_weight_summaries_by_judge_measure_scale"]} == {5, 7}
    records.reverse()
    assert study._calculate_differences_from_validated_records(records) == result
    records[0]["response"]["overall"] = 1.0
    with pytest.raises(ValueError, match="score record"):
        study._calculate_differences_from_validated_records(records)
    with pytest.raises(ValueError, match="cannot promote"):
        study.calculate_differences(work, revisions, endpoints)
    assert calls == [(work, revisions, endpoints)]
    with pytest.raises(TypeError):
        study.calculate_differences(records)  # type: ignore[call-arg]


def test_revision_lineage_is_immutable_and_rejects_control_feedback(tmp_path: Path) -> None:
    study = _study()
    work = tmp_path / "work"
    _prepare_acknowledged_work(study, work)
    records = _revision_records(study, work)
    manifest = work / "revision-lineage.jsonl"
    study.write_jsonl(manifest, records)
    assert study.validate_revision_lineage(work, manifest) == records
    with pytest.raises(ValueError, match="overwrite"):
        study.write_jsonl(manifest, records)
    control = next(record for record in records if record["event_id"].endswith("generic_no_feedback"))
    control["feedback"] = records[0]["feedback"]
    invalid = work / "invalid-revision-lineage.jsonl"
    study.write_jsonl(invalid, records)
    with pytest.raises(ValueError, match="Control revision lineage"):
        study.validate_revision_lineage(work, invalid)
    sampler_records = _revision_records(study, work)
    sampler_records[0]["generator"]["sampler"] = {"temperature": 0}
    sampler_invalid = work / "invalid-sampler-revision-lineage.jsonl"
    study.write_jsonl(sampler_invalid, sampler_records)
    with pytest.raises(ValueError, match="sampler schema"):
        study.validate_revision_lineage(work, sampler_invalid)
    duplicate_records = _revision_records(study, work)
    guided = [record for record in duplicate_records if record["feedback"] is not None]
    guided[1]["feedback"] = guided[0]["feedback"]
    duplicate_invalid = work / "duplicate-feedback-revision-lineage.jsonl"
    study.write_jsonl(duplicate_invalid, duplicate_records)
    with pytest.raises(ValueError, match="nonempty and unique"):
        study.validate_revision_lineage(work, duplicate_invalid)
    pair_records = _revision_records(study, work)
    paired_control = next(record for record in pair_records if record["event_id"] == pair_records[0]["event_id"].replace("cwr_guided", "generic_no_feedback"))
    paired_control["generator"]["sampler"]["seed"] = 8
    pair_receipt = paired_control["generator"]["receipt"]
    pair_request_path = work / pair_receipt["request"]["path"]
    pair_request = json.loads(pair_request_path.read_text(encoding="utf-8"))
    pair_request["sampler"]["seed"] = 8
    pair_request_path.write_bytes(study.canonical(pair_request))
    pair_receipt["request"].update({"bytes": pair_request_path.stat().st_size, "sha256": study.sha256(pair_request_path)})
    pair_receipt["request_sha256"] = pair_receipt["request"]["sha256"]
    pair_payload_path = work / pair_receipt["payload"]["path"]
    pair_payload = json.loads(pair_payload_path.read_text(encoding="utf-8"))
    pair_payload["request_sha256"] = pair_receipt["request_sha256"]
    pair_payload_path.write_bytes(study.canonical(pair_payload))
    pair_receipt["payload"].update({"bytes": pair_payload_path.stat().st_size, "sha256": study.sha256(pair_payload_path)})
    pair_receipt["payload_sha256"] = pair_receipt["payload"]["sha256"]
    pair_invalid = work / "pair-sampler-revision-lineage.jsonl"
    study.write_jsonl(pair_invalid, pair_records)
    with pytest.raises(ValueError, match="Matched guided/control"):
        study.validate_revision_lineage(work, pair_invalid)
    request_id_records = _revision_records(study, work)
    request_id_records[1]["generator"]["receipt"]["provider_request_id"] = request_id_records[0]["generator"]["receipt"]["provider_request_id"]
    request_id_invalid = work / "duplicate-request-id-revision-lineage.jsonl"
    study.write_jsonl(request_id_invalid, request_id_records)
    with pytest.raises(ValueError, match="provider_request_id"):
        study.validate_revision_lineage(work, request_id_invalid)
    semantic_records = _revision_records(study, work)
    receipt = semantic_records[0]["generator"]["receipt"]
    request_path = work / receipt["request"]["path"]
    request_path.write_bytes(study.canonical({"event_id": semantic_records[0]["event_id"], "role": "revision_generation"}))
    receipt["request"].update({"bytes": request_path.stat().st_size, "sha256": study.sha256(request_path)})
    receipt["request_sha256"] = receipt["request"]["sha256"]
    payload_path = work / receipt["payload"]["path"]
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    payload["request_sha256"] = receipt["request_sha256"]
    payload_path.write_bytes(study.canonical(payload))
    receipt["payload"].update({"bytes": payload_path.stat().st_size, "sha256": study.sha256(payload_path)})
    receipt["payload_sha256"] = receipt["payload"]["sha256"]
    semantic_invalid = work / "semantic-request-revision-lineage.jsonl"
    study.write_jsonl(semantic_invalid, semantic_records)
    with pytest.raises(ValueError, match="request semantic"):
        study.validate_revision_lineage(work, semantic_invalid)


def test_feedback_packet_rejects_legacy_finding_shape_and_excesses() -> None:
    study = _study()
    instructions = json.loads((study.HERE / "revision-instructions.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="shape or size"):
        study._validate_feedback_packet(study.canonical({"finding": "legacy permissive fixture"}), instructions)
    with pytest.raises(ValueError, match="shape or size"):
        study._validate_feedback_packet(study.canonical({"findings": [{"location": "opening", "observation": "visible issue", "repair_target": "repair"}, {"location": "middle", "observation": "visible issue", "repair_target": "repair"}, {"location": "ending", "observation": "visible issue", "repair_target": "repair"}, {"location": "after", "observation": "too many", "repair_target": "repair"}]}), instructions)


def test_cwr_precomposition_binds_exact_frozen_instruction_and_runtime() -> None:
    study = _study()
    source_text, prompt_text = "source text", "originating prompt"
    source = {"sha256": hashlib.sha256(source_text.encode("utf-8")).hexdigest()}
    prompt = {"sha256": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()}
    instruction, runtime = "frozen CWR instruction", "a" * 64
    payload = {"input_text": source_text, "input_sha256": source["sha256"], "originating_prompt": prompt_text, "prompt_sha256": prompt["sha256"], "cwr_feedback_instruction": instruction, "cwr_runtime_sha256": runtime}
    study._validate_cwr_precomposition_input(payload, input_commitment=source, prompt_commitment=prompt, expected_instruction=instruction, expected_runtime_sha256=runtime)
    payload["cwr_feedback_instruction"] = "other instruction"
    with pytest.raises(ValueError, match="precomposition"):
        study._validate_cwr_precomposition_input(payload, input_commitment=source, prompt_commitment=prompt, expected_instruction=instruction, expected_runtime_sha256=runtime)
    payload["cwr_feedback_instruction"] = instruction
    payload["cwr_runtime_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="precomposition"):
        study._validate_cwr_precomposition_input(payload, input_commitment=source, prompt_commitment=prompt, expected_instruction=instruction, expected_runtime_sha256=runtime)


def test_endpoint_disclosure_preview_is_immutable_and_separately_acknowledged(tmp_path: Path) -> None:
    study = _study()
    work = tmp_path / "work"
    _prepare_acknowledged_work(study, work)
    revision_manifest = work / "revision-lineage.jsonl"
    study.write_jsonl(revision_manifest, _revision_records(study, work))
    preview = study.write_endpoint_disclosure_preview(work, revision_manifest)
    assert preview["call_count"] == 216
    assert (work / "endpoint-disclosure-preview.canonical.sha256").read_text(encoding="ascii") == hashlib.sha256(study.canonical(preview)).hexdigest() + "\n"
    with pytest.raises(ValueError, match="overwrite"):
        study.write_endpoint_disclosure_preview(work, revision_manifest)
    acknowledgement = {"study_id": preview["study_id"], "phase": preview["phase"], "preview_sha256": hashlib.sha256(study.canonical(preview)).hexdigest(), "acknowledged": True, "acknowledged_at": "2026-08-27T00:00:00Z"}
    acknowledgement_path = work / "endpoint-acknowledgement.json"
    study.write_json(acknowledgement_path, acknowledgement)
    assert study.validate_endpoint_disclosure_acknowledgement(work, revision_manifest, acknowledgement_path) == acknowledgement
    acknowledgement["phase"] = "wrong"
    study.write_json(acknowledgement_path, acknowledgement)
    with pytest.raises(ValueError, match="Endpoint disclosure acknowledgement"):
        study.validate_endpoint_disclosure_acknowledgement(work, revision_manifest, acknowledgement_path)


def test_endpoint_manifest_is_revalidated_before_revision_gain_calculation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    work = tmp_path / "work"
    _prepare_acknowledged_work(study, work)
    revisions = work / "revision-lineage.jsonl"
    study.write_jsonl(revisions, _revision_records(study, work))
    targets, records = _endpoint_records(study, work)
    monkeypatch.setattr(study, "_revision_targets", lambda _value, _records: targets)
    endpoints = work / "endpoint-lineage.jsonl"
    study.write_jsonl(endpoints, records)
    endpoint_preview = study.write_endpoint_disclosure_preview(work, revisions)
    study.write_json(work / study.ENDPOINT_ACKNOWLEDGEMENT, {"study_id": endpoint_preview["study_id"], "phase": endpoint_preview["phase"], "preview_sha256": hashlib.sha256(study.canonical(endpoint_preview)).hexdigest(), "acknowledged": True, "acknowledged_at": "2026-08-27T00:00:00Z"})
    assert len(study.validate_endpoint_lineage(work, revisions, endpoints)) == 216
    with pytest.raises(ValueError, match="cannot promote"):
        study.calculate_differences(work, revisions, endpoints)
    records[0]["response"]["overall"] = 1 if records[0]["response"]["overall"] != 1 else 2
    altered = work / "altered-endpoint-lineage.jsonl"
    study.write_jsonl(altered, records)
    with pytest.raises(ValueError, match="receipt binding"):
        study.calculate_differences(work, revisions, altered)


def test_endpoint_responses_require_integer_scores_and_grounded_quotes() -> None:
    study = _study()
    measure = study.contract()["endpoint_evaluation"]["measures"][0]
    response = {
        "overall": 4,
        "rationale": "The text is clear.",
        "evidence": [{"quote": "the bell rang", "explanation": "concrete action"}, {"quote": "rain fell", "explanation": "specific image"}],
    }
    study._validate_endpoint_response(response, measure, "the bell rang and rain fell")
    response["overall"] = 4.0
    with pytest.raises(ValueError, match="in-scale integer"):
        study._validate_endpoint_response(response, measure, "the bell rang and rain fell")
    response["overall"] = 4
    response["evidence"][1]["quote"] = "invented wording"
    with pytest.raises(ValueError, match="grounded"):
        study._validate_endpoint_response(response, measure, "the bell rang and rain fell")
    response["evidence"][1]["quote"] = "the bell rang"
    with pytest.raises(ValueError, match="grounded"):
        study._validate_endpoint_response(response, measure, "the bell rang and rain fell")
    response["evidence"][1]["quote"] = "rain fell"
    response["rationale"] = "x" * 901
    with pytest.raises(ValueError, match="rationale"):
        study._validate_endpoint_response(response, measure, "the bell rang and rain fell")


def test_receipt_and_reparse_guards_reject_untrusted_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    with pytest.raises(ValueError, match="receipt"):
        study._validate_receipt(tmp_path, {"provider_request_id": "r", "request_sha256": "0" * 64, "payload_sha256": "0" * 64, "response_sha256": "not-a-hash"})
    manifest = tmp_path / "manifest.jsonl"
    study.write_jsonl(manifest, [{"record_type": "test"}])
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == manifest or original(path))
    with pytest.raises(ValueError, match="Reparse point"):
        study._read_jsonl(manifest)


def test_ancestor_reparse_guard_rejects_child_artifact_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    parent = tmp_path / "reparse-parent"
    child = parent / "child.jsonl"
    parent.mkdir()
    study.write_jsonl(child, [{"record_type": "test"}])
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == parent or original(path))
    with pytest.raises(ValueError, match="Reparse point"):
        study._read_jsonl(child)


def test_write_helpers_reject_final_dangling_reparse_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    study = _study()
    final = tmp_path / "dangling-final.json"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == final or original(path))
    with pytest.raises(ValueError, match="Reparse point"):
        study.write_json(final, {"safe": False})
    with pytest.raises(ValueError, match="Reparse point"):
        study.write_jsonl(final, [{"record_type": "test"}])
    hash_final = tmp_path / "dangling-final.sha256"
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == hash_final or original(path))
    with pytest.raises(ValueError, match="Reparse point"):
        study._write_immutable_bytes(hash_final, b"0" * 64 + b"\n", label="companion hash")
