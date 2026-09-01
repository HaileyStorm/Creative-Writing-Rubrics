from __future__ import annotations

import builtins
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v3-heldout-confirmation-v1"


def _load(name: str = "revision_gain_v3"):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(value) + b"\n")


def _target_manifest(study, root: Path) -> Path:
    frozen_root, revision_root = root / "frozen", root / "revisions"
    frozen_items = [{"item_id": item, "source.md": {"path": f"inputs/{item}/source.md", **study._INPUTS[item]["source.md"]}, "prompt.md": {"path": f"inputs/{item}/prompt.md", **study._INPUTS[item]["prompt.md"]}} for item in study._ITEMS]
    frozen = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "verified_external_heldout_inputs", "contract_sha256": study.CONTRACT_SHA256, "source_root": str(root / "unavailable-source-root"), "source_material_copied": False, "items": frozen_items, "revision_schedule_sha256": hashlib.sha256(study.canonical(study.revision_schedule())).hexdigest(), "endpoint_schedule_sha256": hashlib.sha256(study.canonical(study.endpoint_schedule())).hexdigest()}
    frozen_path = frozen_root / "frozen-inputs.json"; _write(frozen_path, frozen)
    source_text = lambda item: (f"frozen source {item}", f"frozen prompt {item}")
    study._read_frozen_source = lambda frozen, item: source_text(item)
    study._pinned_cwr_question_payload = list
    question_root = root / "questions"; questions = study._pinned_cwr_question_payload()
    question_path = question_root / "questions.json"; _write(question_path, questions)
    question = {"path": "questions.json", "bytes": len(question_path.read_bytes()), "sha256": hashlib.sha256(question_path.read_bytes()).hexdigest()}
    feedback_roots = {}
    for item in study._ITEMS:
        feedback_root = root / "feedback" / item; feedback_root.mkdir(parents=True)
        payload = {"source_text": source_text(item)[0], "source_prompt": source_text(item)[1], "question_payload": questions, "feedback_prompt": study._asset("cwr_feedback", study.contract()), "response_schema": json.loads(study._asset("cwr_feedback_schema", study.contract()))}
        _write(feedback_root / "payload.json", payload); payload_sha = hashlib.sha256((feedback_root / "payload.json").read_bytes()).hexdigest()
        event_id = f"feedback-v3-c1-{item}-sol"
        prepared = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "prepared_cwr_feedback", "event_id": event_id, "contract_sha256": study.CONTRACT_SHA256, "frozen_inputs_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(), "source_item_id": item, "route": study.contract()["routes"]["cwr_feedback"], "question_root": str(question_root), "question_payload": question, "runtime_contract_sha256": "035f946ebaaf9211b6b0933473dd09ce204713518a409b4b6d2bc9578c8480ab", "payload_sha256": payload_sha, "provider_calls_made": 0, "process_launches": 0, "no_resend": True}
        _write(feedback_root / "prepared-cell.json", prepared)
        _write(feedback_root / "launch-intent.json", {"format_version": 1, "study_id": study.STUDY_ID, "kind": "one_launch_intent", "prepared_record_sha256": hashlib.sha256((feedback_root / "prepared-cell.json").read_bytes()).hexdigest(), "process_launches": 1, "no_resend": True})
        response = {"findings": [{"location": "opening", "observation": "thin", "repair_target": "ground image"}]}; _write(feedback_root / "response.json", response)
        _write(feedback_root / "native-receipt.json", {"status": 200, "provider_request_id": f"feedback-request-{item}", "provider_session_id": f"feedback-session-{item}", "native_response_id": f"feedback-native-{item}", "provider_model": "gpt-5.6-sol", "reasoning": "high", "tools_enabled": False, "transmitted_payload_sha256": payload_sha, "response_sha256": hashlib.sha256((feedback_root / "response.json").read_bytes()).hexdigest()})
        feedback_roots[item] = str(feedback_root)
    rows = []
    descendants = {}
    for row in study.targets():
        path = root / "targets" / f"{row['blind_target_id']}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"frozen text {row['blind_target_id']}", encoding="utf-8")
        raw = path.read_bytes()
        target = {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if row["kind"] == "source_baseline":
            origin = {"kind": "source_baseline", "source_item_id": row["source_item_id"], "target_event_id": None, "source": study._INPUTS[row["source_item_id"]]["source.md"]}
        else:
            revision_path = revision_root / f"{row['target_event_id']}.md"; revision_path.parent.mkdir(parents=True, exist_ok=True); revision_path.write_bytes(raw)
            descendant = {"path": revision_path.relative_to(revision_root).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            descendants[row["target_event_id"]] = descendant
            origin = {"kind": "revision_descendant", "source_item_id": row["source_item_id"], "target_event_id": row["target_event_id"], "descendant": descendant}
        rows.append({"blind_target_id": row["blind_target_id"], "target": target, "origin": origin})
    records = []
    for event in study.revision_schedule():
        feedback = [{"location": "opening", "observation": "thin", "repair_target": "ground image"}] if event["guidance_arm"] == "cwr_guided" else None
        payload = study.revision_payload(source_text=source_text(event["source_item_id"])[0], source_prompt=source_text(event["source_item_id"])[1], guidance_arm=event["guidance_arm"], cwr_feedback=feedback)
        cell_root = revision_root / "cells" / event["event_id"]; cell_root.mkdir(parents=True)
        payload_path = cell_root / "payload.json"; payload_path.write_bytes(payload)
        payload_binding = {"path": "payload.json", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        feedback_hash = hashlib.sha256((Path(feedback_roots[event["source_item_id"]]) / "native-receipt.json").read_bytes()).hexdigest() if feedback else None
        prepared = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "prepared_revision_cell", "event_id": event["event_id"], "contract_sha256": study.CONTRACT_SHA256, "frozen_inputs_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(), "source_item_id": event["source_item_id"], "guidance_arm": event["guidance_arm"], "generator": study.contract()["routes"]["generator"], "payload": payload_binding, "feedback_receipt_sha256": feedback_hash, "provider_calls_made": 0, "process_launches": 0, "no_resend": True}
        prepared_path = cell_root / "prepared-cell.json"; _write(prepared_path, prepared)
        story = (revision_root / descendants[event["event_id"]]["path"]).read_text(encoding="utf-8")
        response_path = revision_root / f"{event['event_id']}.response.json"; _write(response_path, {"story": story})
        native_path = revision_root / f"{event['event_id']}.native.json"; _write(native_path, {"status": 200, "provider_request_id": f"grok-request-{event['event_id']}", "provider_session_id": f"grok-session-{event['event_id']}", "native_response_id": f"grok-native-{event['event_id']}", "provider_model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "transmitted_payload_sha256": payload_binding["sha256"], "response_sha256": hashlib.sha256(response_path.read_bytes()).hexdigest()})
        bind = lambda path: {"path": path.relative_to(revision_root).as_posix(), "bytes": len(path.read_bytes()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        records.append({"event_id": event["event_id"], "descendant": descendants[event["event_id"]], "prepared_root": str(cell_root), "native_receipt": bind(native_path), "response": bind(response_path), "feedback_root": feedback_roots[event["source_item_id"]] if feedback else None})
    descendant_manifest = {"study_id": study.STUDY_ID, "kind": "frozen_revision_descendants", "contract_sha256": study.CONTRACT_SHA256, "frozen_inputs_sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest(), "events": records}
    descendant_path = revision_root / "descendants.json"; _write(descendant_path, descendant_manifest)
    manifest = root / "target-manifest.json"
    _write(manifest, {"format_version": 1, "study_id": study.STUDY_ID, "kind": "frozen_target_lineage", "contract_sha256": study.CONTRACT_SHA256, "frozen_inputs_root": str(frozen_root), "frozen_inputs": {"path": "frozen-inputs.json", "bytes": len(frozen_path.read_bytes()), "sha256": hashlib.sha256(frozen_path.read_bytes()).hexdigest()}, "revision_root": str(revision_root), "revision_descendant_manifest": {"path": "descendants.json", "bytes": len(descendant_path.read_bytes()), "sha256": hashlib.sha256(descendant_path.read_bytes()).hexdigest()}, "targets": rows})
    return manifest


def _one_receipt_chain(study, tmp_path: Path):
    target_root = tmp_path / "frozen-targets"
    manifest = _target_manifest(study, target_root)
    chosen_event = next(row for row in study.endpoint_schedule() if row["blind_target_id"] == "blind-v3-05")
    for index, event in enumerate([chosen_event]):
        prepared_root = tmp_path / "prepared" / str(index)
        prepared = study.prepare_endpoint_cell(prepared_root=prepared_root, target_root=target_root, target_manifest_path=manifest, endpoint_event_id=event["endpoint_event_id"])
        intent = study.begin_one_launch(prepared_root=prepared_root)
        response = {"overall": 4 if event["measure_id"] == "holistic" else 3, "rationale": "bounded blinded score"}
        response_raw = _canonical(response) + b"\n"
        native = {"status": 200, "provider_request_id": f"request-{index}", "provider_session_id": f"session-{index}", "native_response_id": f"native-{index}", "provider_model": prepared["route"]["model"], "reasoning": prepared["route"]["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": prepared["payload"]["sha256"], "response_sha256": hashlib.sha256(response_raw).hexdigest()}
        _write(prepared_root / "response.json", response)
        _write(prepared_root / "native-receipt.json", native)
        receipt_path = prepared_root / "verified-receipt.json"
        receipt = study.validate_endpoint_receipt(prepared_root=prepared_root, output_path=receipt_path)
        assert receipt["launch_intent_sha256"] == hashlib.sha256(_canonical(intent) + b"\n").hexdigest()
        return receipt_path
    raise AssertionError("missing scheduled endpoint")


def _projection_receipts(study, tmp_path: Path):
    paths, receipts = [], []
    for index, event in enumerate(study.endpoint_schedule()):
        route = study.contract()["routes"]["judges"][event["judge_route_id"]]
        payload_sha = hashlib.sha256(_canonical({"target": event["blind_target_id"], "measure": event["measure_id"]})).hexdigest()
        receipt = {"format_version": 1, "study_id": study.STUDY_ID, "kind": "verified_endpoint_receipt", "prepared_root": str(tmp_path / f"prepared-{index}"), "endpoint_event_id": event["endpoint_event_id"], "prepared_record_sha256": "a" * 64, "launch_intent_sha256": "b" * 64, "payload_sha256": payload_sha, "native_receipt_sha256": "c" * 64, "response_sha256": "d" * 64, "status": 200, "provider_request_id": f"request-{index}", "provider_session_id": f"session-{index}", "native_response_id": f"native-{index}", "provider_model": route["model"], "reasoning": route["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": payload_sha, "response": {"overall": 4 if event["measure_id"] == "holistic" else 3, "rationale": "bounded"}}
        path = tmp_path / f"{index}.json"; _write(path, receipt); paths.append(path); receipts.append(receipt)
    return paths, receipts


def test_exact_v1_heldout_bindings_one_cycle_and_whole_contract_pin():
    study = _load()
    value = study.contract()
    assert list(value["sources"]["items"]) == ["hanna-594", "hanna-731", "hanna-817", "hanna-907"]
    assert value["sources"]["items"]["hanna-594"]["source.md"]["sha256"] == "1ac8b69bb3f547425e3a02270ed168040b15554f37859f5beaf84fdc7d8042ba"
    assert len(study.revision_schedule(value)) == 8
    assert len(study.targets(value)) == 12
    assert len(study.endpoint_schedule(value)) == 48
    assert value["execution_status"].startswith("NO_GO")


def test_whole_contract_hash_rejects_mutation(tmp_path, monkeypatch):
    study = _load("revision_gain_v3_contract_mutation")
    altered = tmp_path / "study-contract.json"
    altered.write_bytes((PACKAGE / "study-contract.json").read_bytes().replace(b"hanna-594", b"hanna-595"))
    monkeypatch.setattr(study, "CONTRACT_PATH", altered)
    study.contract.cache_clear()
    with pytest.raises(ValueError, match="whole contract bytes"):
        study.contract()


def test_matched_payload_is_guided_only_and_endpoint_bytes_are_route_neutral():
    study = _load()
    generic = study.revision_payload(source_text="story", source_prompt="prompt", guidance_arm="generic_no_feedback")
    guided = study.revision_payload(source_text="story", source_prompt="prompt", guidance_arm="cwr_guided", cwr_feedback=[{"location": "opening", "observation": "thin", "repair_target": "ground image"}])
    assert b"cwr_feedback" not in generic and b"cwr_feedback" in guided
    with pytest.raises(ValueError, match="feedback schema"):
        study.revision_payload(source_text="story", source_prompt="prompt", guidance_arm="cwr_guided", cwr_feedback=[{"bad": "shape"}])
    target = study.targets()[0]["blind_target_id"]
    payload = study.endpoint_payload(blind_target_id=target, target_text="story", target_sha256="d" * 64, measure_id="holistic")
    first, second = [row for row in study.endpoint_schedule() if row["blind_target_id"] == target and row["measure_id"] == "holistic"]
    assert study.endpoint_envelope(endpoint_event_id=first["endpoint_event_id"], payload=payload)["route"] != study.endpoint_envelope(endpoint_event_id=second["endpoint_event_id"], payload=payload)["route"]
    assert b"cwr_guided" not in payload and b"generic_no_feedback" not in payload and b"hanna-" not in payload


@pytest.mark.parametrize("tamper", ["status", "response", "response_hash"])
def test_native_replay_rejects_status_response_and_hash_tamper(tmp_path, tamper):
    study = _load()
    path = _one_receipt_chain(study, tmp_path)
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert study.validate_endpoint_receipt(prepared_root=Path(receipt["prepared_root"])) == receipt
    root = path.parent
    if tamper == "response":
        _write(root / "response.json", {"overall": 1, "rationale": "tampered"})
    else:
        native = json.loads((root / "native-receipt.json").read_text(encoding="utf-8"))
        native["status" if tamper == "status" else "response_sha256"] = 500 if tamper == "status" else "0" * 64
        _write(root / "native-receipt.json", native)
    with pytest.raises(ValueError):
        study.validate_endpoint_receipt(prepared_root=root)


@pytest.mark.parametrize("tamper", ["origin", "parent_manifest"])
def test_endpoint_preparation_rejects_arbitrary_target_lineage(tmp_path, tamper):
    study = _load()
    root = tmp_path / "targets"; manifest_path = _target_manifest(study, root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if tamper == "origin":
        manifest["targets"][4]["origin"]["source_item_id"] = "hanna-731"
    else:
        manifest["revision_descendant_manifest"]["sha256"] = "0" * 64
    _write(manifest_path, manifest)
    event = next(row for row in study.endpoint_schedule() if row["blind_target_id"] == "blind-v3-05")
    with pytest.raises(ValueError):
        study.prepare_endpoint_cell(prepared_root=tmp_path / "prepared", target_root=root, target_manifest_path=manifest_path, endpoint_event_id=event["endpoint_event_id"])


def test_revision_preparation_rejects_handcrafted_feedback(tmp_path, monkeypatch):
    study = _load()
    root = tmp_path / "targets"; _target_manifest(study, root)
    frozen_path = root / "frozen" / "frozen-inputs.json"
    monkeypatch.setattr(study, "_read_frozen_source", lambda frozen, item_id: ("frozen source", "frozen prompt"))
    guided = next(row for row in study.revision_schedule() if row["guidance_arm"] == "cwr_guided")
    feedback_root = tmp_path / "handcrafted-feedback"; feedback_root.mkdir(); _write(feedback_root / "prepared-cell.json", {"kind": "verified_cwr_feedback_receipt"})
    with pytest.raises(ValueError):
        study.prepare_revision_cell(prepared_root=tmp_path / "prepared-revision", frozen_inputs_path=frozen_path, event_id=guided["event_id"], feedback_prepared_root=feedback_root)


def test_prepare_revision_cell_reads_frozen_manifest_not_caller_text(tmp_path):
    study = _load()
    root = tmp_path / "targets"; _target_manifest(study, root)
    frozen_path = root / "frozen" / "frozen-inputs.json"
    generic = next(row for row in study.revision_schedule() if row["guidance_arm"] == "generic_no_feedback")
    prepared = study.prepare_revision_cell(prepared_root=tmp_path / "actual-revision-cell", frozen_inputs_path=frozen_path, event_id=generic["event_id"])
    assert prepared["event_id"] == generic["event_id"]
    assert prepared["feedback_receipt_sha256"] is None


def test_pinned_question_runtime_fails_closed_on_v1_runner_drift():
    study = _load()
    with pytest.raises(ValueError, match="pinned V1 runtime src/hbqrs/runner.py drifted"):
        study._pinned_cwr_question_payload()


def test_projection_reopens_verified_receipt_contract_and_keeps_endpoints_separate(tmp_path, monkeypatch):
    study = _load()
    paths, receipts = _projection_receipts(study, tmp_path)
    by_root = {receipt["prepared_root"]: receipt for receipt in receipts}
    monkeypatch.setattr(study, "validate_endpoint_receipt", lambda *, prepared_root, output_path=None: by_root[str(Path(prepared_root))])
    projection = study.project_independent_metrics(endpoint_receipt_paths=paths)
    assert projection["endpoint_results_are_not_pooled"] is True
    assert len(projection["primary_guided_minus_control"]) == 16
    assert len(projection["guided_minus_baseline"]) == 16
    assert len(projection["generic_minus_baseline"]) == 16


def test_projection_rejects_duplicate_native_identity(tmp_path, monkeypatch):
    study = _load()
    paths, receipts = _projection_receipts(study, tmp_path)
    receipts[1]["provider_request_id"] = receipts[0]["provider_request_id"]
    receipts[1]["provider_session_id"] = receipts[0]["provider_session_id"]
    receipts[1]["native_response_id"] = receipts[0]["native_response_id"]
    _write(paths[1], receipts[1])
    by_root = {receipt["prepared_root"]: receipt for receipt in receipts}
    monkeypatch.setattr(study, "validate_endpoint_receipt", lambda *, prepared_root, output_path=None: by_root[str(Path(prepared_root))])
    with pytest.raises(ValueError, match="identity is duplicated"):
        study.project_independent_metrics(endpoint_receipt_paths=paths)


def test_runtime_has_no_optimizer_import_and_executor_is_closed(monkeypatch):
    original = builtins.__import__
    def deny(name, *args, **kwargs):
        if name.split(".")[0] in {"dspy", "optuna"}:
            raise AssertionError("runtime optimizer import")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", deny)
    _load("revision_gain_v3_no_optimizer")
    spec = importlib.util.spec_from_file_location("revision_gain_v3_executor", PACKAGE / "executor.py")
    assert spec and spec.loader
    executor = importlib.util.module_from_spec(spec); spec.loader.exec_module(executor)
    with pytest.raises(executor.ExecutionBlocked, match="provider-free"):
        executor.dispatch_native()
