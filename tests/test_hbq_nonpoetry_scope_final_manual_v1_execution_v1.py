from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-final-manual-v1-execution-v1"
def study():
    spec = importlib.util.spec_from_file_location("s2_final_manual_execution_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def private_controller(tmp_path: Path, monkeypatch):
    s = study()
    root = tmp_path / "private-controller"
    root.mkdir()
    source = next(json.loads(line) for line in (book_root() / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(line)["id"] == "scope.passage.status")
    baseline = {key: source[key] for key in ("id", "module_id", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")}
    candidate = deepcopy(baseline)
    candidate["text"] = "Does the supplied evaluation avoid an irrelevant completeness penalty for this explicitly declared passage?"
    controller = {"format_version": 1, "study_id": "hbq-nonpoetry-scope-final-manual-v1", "status": "presealed_private_controller_contract", "execution": {"provider_calls_made_exact": 0, "future_calls_exact": 24, "one_leaf_per_request": True}, "questions": {"baseline": baseline, "candidate": candidate}, "fixtures": [{"fixture_id": f"fixture-{index}", "state": state, "artifact_kind": "scope_evaluation_record", "declared_scope": "excerpt" if index < 4 else "catalog", "text": f"synthetic fixture {index}", "contexts": [f"synthetic context {index}"]} for index, state in enumerate(("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch"), start=1)], "expected_oracles": {"localized_issue": "YES", "material_failure": "NO", "missing_required_evidence": "CANNOT_ASSESS", "activation_mismatch": "NOT_APPLICABLE"}}
    contract = json.dumps(controller, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    (root / "controller-contract.v1.json").write_bytes(contract)
    monkeypatch.setattr(s, "PRIVATE_CONTROLLER_ROOT", root)
    monkeypatch.setattr(s, "PRIVATE_CONTROLLER_SHA256", hashlib.sha256(contract).hexdigest())
    public_contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    public_contract["private_controller"]["contract_sha256"] = hashlib.sha256(contract).hexdigest()
    monkeypatch.setattr(s, "contract", lambda: public_contract)
    return s, root / s.PRIVATE_EXECUTION_DIRECTORY


def fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        registry = Path(command[command.index("--registry") + 1])
        modules = json.loads(registry.read_text(encoding="utf-8"))
        question = modules[0]["tree"][0]["children"][0]
        return SimpleNamespace(returncode=0, stdout=("frozen prompt\n" + question["text"] + "\n").encode("utf-8"), stderr=b"")
    if "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def record(slot, *, correct=True):
    ordinal = int(hashlib.sha256(slot["slot_id"].encode("utf-8")).hexdigest()[:12], 16)
    return {
        "slot_id": slot["slot_id"],
        "arm": slot["arm"],
        "fixture_id": slot["fixture_id"],
        "logical_sample_id": slot["logical_sample_id"],
        "verdict": slot["expected_verdict"] if correct else "NO",
        "expected": slot["expected_verdict"],
        "correct": correct,
        "run_id": f"run-{ordinal}",
        "session_id_sha256": f"{ordinal:064x}",
        "checkpoint_chain_head_sha256": f"{1000 + ordinal:064x}",
        "accepted_provider_call_count": 1,
        "rejected_retry_count": 0,
        "batch_attempt_count": 1,
    }


def test_exact_pushed_predecessor_private_controller_and_24_slot_geometry(private_controller):
    s, _root = private_controller
    validated = s.validate_package()
    assert validated["slots"] == 24 and validated["provider_calls"] == 0
    schedule = s.build_schedule()
    assert len(schedule) == len({slot["slot_id"] for slot in schedule}) == 24
    assert {slot["arm"] for slot in schedule} == {"baseline", "candidate"}
    assert {slot["leaf_id"] for slot in schedule} == {"scope.passage.status"}
    assert all(slot["condition"]["batch_attempts"] == 3 for slot in schedule)


def test_private_root_is_explicit_external_and_public_sources_contain_no_personal_path(private_controller):
    s, _root = private_controller
    with pytest.raises(ValueError, match="outside"):
        s.set_private_root(book_root())
    with pytest.raises(ValueError, match="disjoint"):
        s.set_private_root(book_root().parent)
    assert "C:\\Users\\Haile" not in (ROOT / "study.py").read_text(encoding="utf-8")
    assert "C:\\Users\\Haile" not in (ROOT / "study-contract.json").read_text(encoding="utf-8")


def test_cli_dry_run_requires_an_explicit_private_root_before_dispatch():
    completed = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], capture_output=True, text=True, check=False)
    assert completed.returncode == 2
    assert "--private-root" in completed.stderr
    assert "NameError" not in completed.stderr


def test_private_candidate_registry_is_arm_specific_and_command_is_singleton(private_controller):
    s, root = private_controller
    s.prepare()
    slot = next(slot for slot in s.build_schedule() if slot["arm"] == "candidate")
    command = s._command(slot)
    assert command[command.index("--provider") + 1] == "codex"
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert command[command.index("--reasoning") + 1] == "high"
    assert command[command.index("--batch-size") + 1] == "1"
    assert command[command.index("--batch-attempts") + 1] == "3"
    assert command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"
    assert command[command.index("--registry") + 1].endswith("candidate-registry.json")
    assert command.count("--question-id") == 1
    assert json.loads((root / "catalog" / "baseline-registry.json").read_text(encoding="utf-8")) != json.loads((root / "catalog" / "candidate-registry.json").read_text(encoding="utf-8"))
    baseline = next(item for item in s.build_schedule() if item["fixture_id"] == slot["fixture_id"] and item["arm"] == "baseline" and item["repeat"] == slot["repeat"])
    assert s._slot_paths(root, baseline)[0] == s._slot_paths(root, slot)[0]
    assert s._task_contract(baseline) == s._task_contract(slot)


def test_provider_free_dry_run_writes_durable_receipt_and_never_allows_remote(private_controller):
    s, root = private_controller
    result = s.dry_run(runner_call=fake_cwr)
    assert result["provider_calls"] == 0
    assert len(list((root / "rendered-prompts").glob("*.txt"))) == 24
    assert (root / "receipts" / "provider-free-dry-run.v1.json").is_file()
    assert b"\r" not in next((root / "rendered-prompts").glob("*.txt")).read_bytes()
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(runner_call=fake_cwr)


def test_pairwise_rendered_prompt_delta_is_only_the_candidate_wording(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    schedule = s.build_schedule()
    baseline = next(slot for slot in schedule if slot["fixture_id"] == schedule[0]["fixture_id"] and slot["arm"] == "baseline" and slot["repeat"] == 1)
    candidate = next(slot for slot in schedule if slot["fixture_id"] == baseline["fixture_id"] and slot["arm"] == "candidate" and slot["repeat"] == 1)
    baseline_prompt = (root / "rendered-prompts" / f"{baseline['slot_id']}.txt").read_text(encoding="utf-8")
    candidate_prompt = (root / "rendered-prompts" / f"{candidate['slot_id']}.txt").read_text(encoding="utf-8")
    expected = baseline_prompt.replace(s._private_contract()["questions"]["baseline"]["text"], s._private_contract()["questions"]["candidate"]["text"])
    assert candidate_prompt == expected


def test_execution_receipts_require_owner_acknowledgement_and_paid_fallback_is_forbidden(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    s._write_zero_charge_acknowledgement()
    acknowledgement = json.loads((root / "receipts" / "zero-charge-acknowledgement.v1.json").read_text(encoding="utf-8"))
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    assert acknowledgement["acknowledged"] is True
    assert acknowledgement["paid_api_or_fallback_route"] == "forbidden"
    assert len(disclosure["slots"]) == 24 and disclosure["one_leaf_per_call"] is True
    assert disclosure["attempt_lifecycle_policy"] == "terminal_sidecar_v1"


def test_offline_settlement_checks_private_gate_and_keeps_public_result_aggregate_only(private_controller):
    s, root = private_controller
    s.dry_run(runner_call=fake_cwr)
    schedule = s._validated_runtime_schedule()
    s._write_zero_charge_acknowledgement()
    result = s.settle(verifier=lambda _root, slot: record(slot))
    assert result["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    public = json.loads((root / "public-aggregate.v1.json").read_text(encoding="utf-8"))
    assert public == {"study_id": s.STUDY_ID, "decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "completed_slots": 24, "planned_slots": 24, "aggregate_cells": {"candidate_passed": 4, "total": 4}, "promotion": "none"}
    sidecar = json.loads((root / "terminal-sidecar.v1.json").read_text(encoding="utf-8"))
    assert sidecar["format"] == "terminal_sidecar_v1"
    assert sidecar["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    with pytest.raises(ValueError, match="Refusing to mutate frozen"):
        s.settle(verifier=lambda _root, slot: record(slot, correct=slot["arm"] != "candidate" or slot["repeat"] != 1))
    assert json.loads((root / "public-aggregate.v1.json").read_text(encoding="utf-8")) == public
