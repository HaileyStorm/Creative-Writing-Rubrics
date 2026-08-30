from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-freeze-v3"
freeze = load_module(PACKAGE / "executor.py", name="feedback_grok_freeze_v3")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def _roots(root: Path) -> None:
    for number in range(1, 11):
        sample = f"feedback-wave-sample-{number:02d}"; cell = root / sample; cell.mkdir(parents=True)
        prepared = {"feedback_sha256": "1" * 64, "r4_result_sha256": "2" * 64, "r4_selection_sha256": "3" * 64, "seed": 17, "wave_id": "feedback-wave", "parent_candidate_id": "baseline", "parent_instruction_sha256": "4" * 64, "parent_profile_sha256": "5" * 64, "preparation_file_sha256": "6" * 64}
        runtime = {"request_id_hash": f"{number:064x}", "session_id_hash": f"{number + 100:064x}"}
        descendant = {"descendant_instruction_base64": base64.b64encode(f"instruction {number}".encode()).decode(), "descendant_profile_base64": base64.b64encode(f'{{"profile":{number}}}'.encode()).decode()}
        (cell / "prepared.json").write_bytes(_canonical(prepared)); (cell / "runtime-identity.json").write_bytes(_canonical(runtime)); (cell / "execution-receipt.json").write_bytes(_canonical({"sample_id": sample, "receipt": number})); (cell / "result.json").write_bytes(_canonical({"descendant": descendant}))


def _pinned_v3_roots(root: Path) -> ModuleType:
    raw = subprocess.check_output(["git", "show", "6aebdbd:evaluation-results/hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3/executor.py"], cwd=ROOT)
    module = ModuleType("pinned_v3_for_freeze"); module.__file__ = str(ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-exec-v3" / "executor.py"); exec(compile(raw, module.__file__, "exec"), module.__dict__)
    prep = {"inputs": {"parent_candidate_id": "baseline", "parent_instruction_base64": base64.b64encode(b"parent").decode(), "parent_profile_base64": base64.b64encode(b'{"p":true}').decode(), "training_result_base64": base64.b64encode(b"{}").decode(), "training_diagnostics_base64": base64.b64encode(b"{}").decode()}, "preparation_sha256": "b" * 64}; prep_raw = module.canonical(prep)
    class V2:
        @staticmethod
        def _preparation(_path: Path): return prep_raw, prep
        @staticmethod
        def _schema(): return module.canonical({"$schema_version": 1, "type": "object"})
        @staticmethod
        def _decode(value: str, **_kwargs): return base64.b64decode(value.encode(), validate=True)
        @staticmethod
        def _descendant(value, _prep):
            instruction = base64.b64decode(value["descendant_instruction_base64"].encode(), validate=True)
            profile = base64.b64decode(value["descendant_profile_base64"].encode(), validate=True)
            return value, {"parent_candidate_id": "baseline", "parent_instruction_sha256": module.sha256(b"parent"), "parent_profile_sha256": module.sha256(b'{"p":true}'), "descendant_instruction_sha256": module.sha256(instruction), "descendant_profile_sha256": module.sha256(profile)}
    module._v2 = lambda: V2()
    authority = {"feedback-producer-contract.json": module.canonical({"study_id": "r4-study"}), "feedback-producer-source.bin": b"source", "feedback-selection-schema.json": module.canonical({"type": "object"}), "feedback-result-schema.json": module.canonical({"type": "object"}), "feedback-selection.json": module.canonical({"study_id": "r4-study"}), "feedback-result.json": module.canonical({"study_id": "r4-study", "public_result_summary": "summary"})}
    feedback = {"format_version": 1, "kind": "hanna_r4_two_phase_feedback", "study_id": "r4-study", "wave_id": "pinned-wave", "seed": 9, "public_result_summary": "summary", "producer": {"study_contract_path": "unused", "study_contract_sha256": module.sha256(authority["feedback-producer-contract.json"]), "producer_source_path": "unused", "producer_source_sha256": module.sha256(authority["feedback-producer-source.bin"]), "selection_schema_path": "unused", "selection_schema_sha256": module.sha256(authority["feedback-selection-schema.json"]), "result_schema_path": "unused", "result_schema_sha256": module.sha256(authority["feedback-result-schema.json"])}, "artifacts": {"selection_path": "unused", "selection_sha256": module.sha256(authority["feedback-selection.json"]), "result_path": "unused", "result_sha256": module.sha256(authority["feedback-result.json"])}}
    feedback_raw = module.canonical(feedback); feedback = {**feedback, "r4_result_sha256": feedback["artifacts"]["result_sha256"], "r4_selection_sha256": feedback["artifacts"]["selection_sha256"]}
    identity: dict = {}; route = {"name": "grok-build-grok-4.6", "provider": "xai_grok_build", "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "adapter": "grok_exec", "destination": "xai_grok_build_subscription", "grok_command_identity": identity}; evidence = {"route_name": route["name"], "route_sha256": "1" * 64, "grok_cli_version": "fixture", "subscription_receipt_hash": "2" * 64, "grok_command_identity_sha256": module.sha256(module.canonical(identity))}
    for number in range(1, 11):
        sample = f"pinned-wave-sample-{number:02d}"; cell = root / sample; cell.mkdir(parents=True); prepared, files = module._artifacts(V2(), sample, prep_raw, prep, feedback_raw, feedback, authority, route, evidence, "a" * 64)
        for name, contents in files.items(): (cell / name).write_bytes(contents)
        output = {"descendant_instruction_base64": base64.b64encode(f"descendant {number}".encode()).decode(), "descendant_profile_base64": base64.b64encode(json.dumps({"child": number}, separators=(",", ":")).encode()).decode()}
        lineage = V2._descendant(output, prep)[1]
        intent = {"format_version": 3, "study_id": module.STUDY_ID, "kind": "adapter_subprocess_launch_intent_not_native_contact", "sample_id": sample, "prepared_sha256": module.sha256(module.canonical(prepared)), "prompt_sha256": prepared["prompt_sha256"], "route_evidence": evidence, "native_contact_proven": False}; request = f"{number:064x}"; session = f"{number + 100:064x}"; runtime = {"adapter_version": 1, "requested_model": route["model"], "reported_model": route["reported_model"], "requested_reasoning_effort": route["reasoning_effort"], "reasoning_attested": False, "identity_evidence": "requested_only", "execution_policy": "bounded_nonvisual_read_only", "nonvisual_max_turns": 1, "observed_turns": 1, "cli_version": evidence["grok_cli_version"], "subscription_receipt_hash": evidence["subscription_receipt_hash"], "command_identity": identity, "request_id_hash": request, "session_id_hash": session}; adapter_result = {"schema_version": 1, "request_hash": module.sha256(module.canonical({"prompt": (cell / "prompt-request.bin").read_bytes().decode()})), "output": output, "output_hash": module.sha256(module.canonical(output)), "runtime": runtime}; control = {"control": {"version": 1, "state": "completed"}, "result": adapter_result}; control_raw = module.canonical(control)
        receipt = {"format_version": 3, "study_id": module.STUDY_ID, "kind": "feedback_bound_grok_v3_native_receipt", "sample_id": sample, "prepared_sha256": module.sha256(module.canonical(prepared)), "launch_intent_sha256": module.sha256(module.canonical(intent)), "adapter_stdout_sha256": module.sha256(control_raw), "feedback_sha256": module.sha256(feedback_raw), "prompt_sha256": prepared["prompt_sha256"], "response_schema_sha256": prepared["response_schema_sha256"], "route_evidence": evidence, "provider_calls_made": 1, "process_launches": 1, "native_contact_proven": True, "native_endpoint_contact_cardinality": "proven_exactly_one", "runtime": runtime, "lineage": lineage, "descendant_output_sha256": module.sha256(module.canonical(output))}; result = {"format_version": 3, "study_id": module.STUDY_ID, "kind": "feedback_bound_grok_v3_result", "sample_id": sample, "descendant": output, "descendant_sha256": module.sha256(module.canonical(output)), "provider_calls_made": 1, "process_launches": 1}
        (cell / "launch-intent.json").write_bytes(module.canonical(intent)); (cell / "adapter-stdout.bin").write_bytes(control_raw); (cell / "adapter-control-envelope.json").write_bytes(module.canonical(control)); (cell / "runtime-identity.json").write_bytes(module.canonical(runtime)); (cell / "execution-receipt.json").write_bytes(module.canonical(receipt)); (cell / "result.json").write_bytes(module.canonical(result))
    return module


@pytest.fixture()
def complete(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "roots"; _roots(root)
    def admit(cell: Path, sample: str) -> dict:
        if not (cell / "result.json").is_file(): raise ValueError("fixture missing result")
        return {"sample_id": sample, "state": "native_descendant_received", "provider_calls_made": 1, "process_launches": 1, "descendant_sha256": freeze.sha256(_canonical(json.loads((cell / "result.json").read_bytes())["descendant"]))}
    monkeypatch.setattr(freeze, "_load_v3", lambda: SimpleNamespace(_admit_completed_root=admit))
    return root


def test_freeze_admits_exact_ten_and_refuses_manifest_overwrite(complete: Path, tmp_path: Path):
    manifest = freeze.freeze_all_ten(output_root=complete, manifest_path=tmp_path / "manifest.json")
    assert len(manifest["samples"]) == 10 and manifest["freeze_provider_calls_made"] == 0 and manifest["confirmation"] == {"status": "unopened", "cells": 0}
    with pytest.raises(ValueError, match="overwrite"):
        freeze.freeze_all_ten(output_root=complete, manifest_path=tmp_path / "manifest.json")


def test_freeze_replays_production_shaped_roots_with_pinned_v3_admission(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "production"; pinned = _pinned_v3_roots(root); monkeypatch.setattr(freeze, "_load_v3", lambda: pinned)
    manifest = freeze.freeze_all_ten(output_root=root, manifest_path=tmp_path / "production-manifest.json")
    assert len(manifest["samples"]) == 10 and manifest["shared_lineage"]["wave_id"] == "pinned-wave"
    (root / "pinned-wave-sample-01" / "postwrite-reconcile.json").write_bytes(_canonical({"terminal": True}))
    with pytest.raises(ValueError):
        freeze.freeze_all_ten(output_root=root, manifest_path=tmp_path / "terminal.json")


@pytest.mark.parametrize("target", ["manifest.json", "feedback-wave-sample-01/manifest.json"])
def test_freeze_rejects_manifest_inside_wave_before_admission(complete: Path, monkeypatch: pytest.MonkeyPatch, target: str):
    called: list[str] = []; monkeypatch.setattr(freeze, "_load_v3", lambda: called.append("admit") or SimpleNamespace())
    before = {path.relative_to(complete): path.read_bytes() for path in complete.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="outside output root"):
        freeze.freeze_all_ten(output_root=complete, manifest_path=complete / target)
    after = {path.relative_to(complete): path.read_bytes() for path in complete.rglob("*") if path.is_file()}
    assert not called and before == after


@pytest.mark.parametrize("kind", ["request", "session", "cross_contact", "descendant", "missing", "extra", "reparse"])
def test_freeze_rejects_cross_root_and_inventory_tamper(complete: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str):
    cells = sorted(complete.iterdir())
    if kind in {"request", "session"}:
        runtime = json.loads((cells[1] / "runtime-identity.json").read_bytes()); original = json.loads((cells[0] / "runtime-identity.json").read_bytes()); runtime[f"{kind}_id_hash"] = original[f"{kind}_id_hash"]; (cells[1] / "runtime-identity.json").write_bytes(_canonical(runtime))
    elif kind == "cross_contact":
        runtime = json.loads((cells[1] / "runtime-identity.json").read_bytes()); original = json.loads((cells[0] / "runtime-identity.json").read_bytes()); runtime["session_id_hash"] = original["request_id_hash"]; (cells[1] / "runtime-identity.json").write_bytes(_canonical(runtime))
    elif kind == "descendant":
        result = json.loads((cells[1] / "result.json").read_bytes()); result["descendant"] = json.loads((cells[0] / "result.json").read_bytes())["descendant"]; (cells[1] / "result.json").write_bytes(_canonical(result))
    elif kind == "missing": (cells[0] / "result.json").unlink()
    elif kind == "extra": (complete / "orphan").mkdir()
    else:
        original = freeze._plain; monkeypatch.setattr(freeze, "_plain", lambda path, directory=None: False if Path(path).name == "result.json" else original(path, directory=directory))
    with pytest.raises(ValueError):
        freeze.freeze_all_ten(output_root=complete, manifest_path=tmp_path / f"{kind}.json")
