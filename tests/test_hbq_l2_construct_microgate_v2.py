from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as cli_runtime
from tests import _hbq_l2_historical_runtime as l2_runtime
from tests import _hbq_s1_historical_runtime as tree_runtime


ROOT = book_root() / "evaluation-results" / "hbq-l2-construct-microgate-v2"
SOURCE_COMMIT = "484134b67b32c6c9ec54ef4b0f6c7451f0e24fe0"


def raw_study():
    spec = importlib.util.spec_from_file_location("l2_construct_microgate_v2", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def study():
    original_path = list(sys.path)
    try:
        module = raw_study()
        repository = Path(module.REPOSITORY).resolve()
        tree_runtime.install_historical_runtime(module, source_commit=SOURCE_COMMIT)
        module.production_runner = l2_runtime.load_runner(repository, SOURCE_COMMIT)
        module.predecessor()
        return module
    finally:
        sys.path[:] = original_path


def test_public_synthetic_freeze_has_six_cases_four_states_and_36_provider_free_slots():
    s = study()
    assert s.verify_package() == {
        "study_id": "hbq-l2-construct-microgate-v2",
        "status": "frozen_provider_free_candidate_line_breaks_microgate",
        "provider_calls": 0,
        "cases": 6,
        "cells": 12,
        "slots": 36,
        "image_fixture_bytes": 129853,
    }
    slots = s.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 36
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["expected_verdict"] for slot in slots} == {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}


def test_current_checkout_drift_remains_fail_closed():
    with pytest.raises(ValueError, match="Active runtime provenance drifted"):
        raw_study().verify_package()


def test_exact_sol_poetry_cases_and_carried_visual_controls_are_frozen():
    s = study()
    cases = s.materialize_artifacts()
    assert cases["p01"]["text"] == "I step\noff the last stair\nand keep\nfalling\nlong after\nthe floor."
    assert cases["p02"]["text"] == "On Tuesday I carried the\nblue folder from the front\ndesk to the back office and\nplaced it beside the copier\nbefore lunch."
    assert cases["p03"]["text"] == "On Tuesday I carried the blue folder from the front desk to the back office and placed it beside the copier before lunch."
    assert cases["p04"]["text"] == "I crossed the floor\nand closed the door."
    assert cases["p02"]["artifact_name"] == "artifact-02.txt"
    assert cases["p03"]["artifact_name"] == "artifact-03.txt"
    assert cases["c03"] == {"case_id": "c03", "artifact_name": "asset-03.png", "artifact_type": "visual_asset", "bundle_id": "visual.environment", "declared_scope": "asset", "completion_status": "complete", "text": "", "image_input_required": True, "image_fixture": "impossible_stairwell_v1"}
    assert cases["c04"] == {"case_id": "c04", "artifact_name": "asset-04.png", "artifact_type": "visual_asset", "bundle_id": "visual.environment", "declared_scope": "asset", "completion_status": "complete", "text": "", "image_input_required": True, "image_fixture": None}
    assert s.load_ledger()["cells"] == {"p01": ["YES", "YES"], "p02": ["NO", "NO"], "p03": ["NOT_APPLICABLE", "NO"], "p04": ["YES", "NO"], "c03": ["NO", "NO"], "c04": ["CANNOT_ASSESS", "CANNOT_ASSESS"]}


def test_candidate_override_changes_only_line_breaks_question_text_and_never_promotes():
    s = study()
    canonical = s.canonical_question(s.LINE_BREAKS)
    candidate = s.question_for(s.LINE_BREAKS)
    restored = deepcopy(candidate)
    restored["question"]["text"] = canonical["question"]["text"]
    assert restored == canonical
    assert candidate["question"]["text"] == "Does each supplied line break make a controlled, legible contribution to rhythm, syntax, emphasis, image, ambiguity, or pace?"
    assert s.question_for(s.NECESSITY) == s.canonical_question(s.NECESSITY)
    assert s.load_contract()["promotion"] == {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"}


def test_predecessor_and_failed_execution_lineage_are_bound_without_becoming_votes():
    s = study()
    s.verify_predecessor()
    history = s.load_contract()["history"]
    assert history["failed_execution"]["execution_checkout_commit"] == "608025bf2c230aae594b9ed3b75371cc0a6267e3"
    assert history["failed_execution"]["failed_root_manifest_study_source_commit"] == "a711c856e33516d4cc1f29fac889a802143623a8"
    assert history["failed_execution"]["accepted_slots"] == 6
    assert history["failed_execution"]["slot_7"] == {"relative_attempt_path": "runs/l2microexec-v2-007/attempts/attempt-01", "receipt_sha256": "e28ae2e046f0dc5debf366b81aae2657ed653ad544043c2502879fbc6fd37191", "terminal_sidecar_sha256": "5f8e668f8060ac405b67610c4f85573e154f6370ed38c73f6a62bbf52aa8189c", "response_sha256": "8422011443b9583406a3a2a1372640b318fc6de54bdf6dce223dc79c68b98803", "provider_verdict": "NOT_APPLICABLE", "local_enum": ["YES", "NO", "CANNOT_ASSESS"], "disposition": "schema_valid_response_rejected_by_local_three_state_enum"}
    assert history["failed_execution"]["later_slots_blocked_before_dispatch"] == 17
    assert history["failed_execution"]["rubric_result"] == history["failed_execution"]["aggregate"] == history["failed_execution"]["settlement"] == "none"
    assert history["failed_execution"]["non_voting"] is True
    assert s.predecessor().load_ledger()["cells"]["c03"] == ["NO", "NO"]


def test_provider_prompt_generation_is_ledger_blind_and_reuses_visual_fixture_only():
    s = study()
    requests = s.render_all_provider_inputs()
    assert len(requests) == 36
    prompts = "\n".join(request["prompt"] for request in requests.values())
    assert "expected_verdict" not in prompts and "non_voting_diagnostic" not in prompts
    assert s.CANDIDATE_TEXT in requests["l2micro-v2-001"]["prompt"]
    assert "artifact-02.txt" in prompts and "artifact-03.txt" in prompts
    assert "prose-wrap-02.txt" not in prompts and "prose-line-03.txt" not in prompts
    assert s.canonical_question(s.NECESSITY)["question"]["text"] in requests["l2micro-v2-004"]["prompt"]
    present = [value for slot, value in requests.items() if 25 <= int(slot.rsplit("-", 1)[1]) <= 30]
    absent = [value for slot, value in requests.items() if int(slot.rsplit("-", 1)[1]) >= 31]
    assert all(len(value["image_inputs"]) == 1 for value in present)
    assert all(not value["image_inputs"] for value in absent)
    assert s.public_attachment_record(present[0]["image_inputs"][0]) == {"fixture_id": "stairwell-01.png", "mime_type": "image/png", "bytes": 129853, "sha256": "104631a4d662f2435e000cca86921a68dbb303ed58cd24759a717c7ae171ceb7"}


def test_binding_or_ledger_drift_fails_closed(monkeypatch: pytest.MonkeyPatch):
    s = study()
    ledger = deepcopy(s.load_ledger())
    ledger["cells"]["p03"] = ["NO", "NO"]
    with pytest.raises(ValueError, match="Four-state expected ledger"):
        s.verify_ledger(ledger)
    contract = deepcopy(s.load_contract())
    contract["candidate_override"]["text"] = "different"
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Candidate-only override"):
        s.verify_package()


def test_active_runtime_and_predecessor_drift_fail_closed_before_direct_prompt_render(monkeypatch: pytest.MonkeyPatch):
    s = study()
    original = s.sha256_file

    def drifted(path: Path) -> str:
        if path == s.REPOSITORY / "src/hbqrs/runner.py":
            return "0" * 64
        return original(path)

    monkeypatch.setattr(s, "sha256_file", drifted)
    with pytest.raises(ValueError, match="Active runtime provenance"):
        s.verify_active_bindings()

    monkeypatch.setattr(s, "verify_predecessor", lambda: (_ for _ in ()).throw(ValueError("Pinned predecessor provenance drifted")))
    with pytest.raises(ValueError, match="Pinned predecessor provenance"):
        s.provider_request("l2micro-v2-001")


def test_command_surface_is_provider_free():
    original_path = tuple(sys.path)
    value = study()
    dry = cli_runtime.run_cli(value, ROOT / "run.py", "--dry-run")
    plan = cli_runtime.run_cli(value, ROOT / "run.py", "--render-plan")
    assert dry[0] == plan[0] == 0
    assert json.loads(dry[1])["verification"]["provider_calls"] == 0
    assert len(json.loads(plan[1])["rendered_slots"]) == 36
    assert tuple(sys.path) == original_path
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "import dspy" not in text and "from dspy" not in text
        assert "--execute" not in text and "subprocess.run" not in text
