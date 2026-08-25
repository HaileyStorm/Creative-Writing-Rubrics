from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10"
PRIVATE_ROOT_ENV = "CWR_S1_FOUR_STATE_V10_PRIVATE_ROOT"


def private_root() -> Path:
    value = os.environ.get(PRIVATE_ROOT_ENV)
    if not value:
        pytest.skip("private S1 v10 evidence root is not configured")
    return Path(value)


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v10_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    value = os.environ.get(PRIVATE_ROOT_ENV)
    if value:
        module.set_private_root(Path(value))
    return module


def test_full_execution_renderer_freeze_is_complete_and_provider_free():
    root = private_root()
    module = study()
    report = module.validate_package()
    root = root / module.PRIVATE_EXECUTION_DIRECTORY
    prompts = [
        (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes()
        for slot in module.build_schedule()
    ]
    dry = json.loads((root / "receipts" / "provider-free-dry-run.v1.json").read_text(encoding="utf-8"))
    assert report["slots"] == 12
    assert sorted(map(len, prompts)) == list(module.EXPECTED_RENDERED_PROMPT_LENGTHS)
    assert dry["provider_calls"] == 0
    assert dry["full_execution_renderer_prompt_checks"] == 12


def test_surrogate_renderer_lengths_are_rejected():
    private_root()
    module = study()
    schedule = module.build_schedule()
    prompts = {slot["opaque_slot_id"]: b"x" * 1726 for slot in schedule}
    with pytest.raises(ValueError, match="surrogate|geometry"):
        module._assert_full_rendered_prompt_geometry(schedule, prompts)


def test_claim_stops_before_claim_write_when_full_prompt_parity_fails(monkeypatch, tmp_path):
    module = study()
    historical_root = private_root() / module.PRIVATE_EXECUTION_DIRECTORY
    historical_claim = historical_root / "execution-claim.v1.json"
    historical_claim_bytes = historical_claim.read_bytes()
    root = tmp_path / "isolated-claim-target"
    root.mkdir()
    schedule = module.build_schedule()
    observed: list[str] = []

    def reject(*_args):
        raise ValueError("synthetic full-prompt parity failure")

    monkeypatch.setattr(module, "_assert_full_rendered_prompt_parity_at_root", reject)
    monkeypatch.setattr(module._v3()._v2(), "_require_privacy_receipt", lambda *_args: None)
    monkeypatch.setattr(module, "_require_protocol_receipt", lambda *_args: None)
    monkeypatch.setattr(module._v3()._base(), "_four_state_original_claim_execution", lambda *_args: observed.append("claim"))
    with pytest.raises(ValueError, match="synthetic full-prompt parity failure"):
        module._claim_execution(root, schedule)
    assert observed == []
    assert not (root / "execution-claim.v1.json").exists()
    assert historical_claim.read_bytes() == historical_claim_bytes


def test_v9_no_result_has_no_contact_or_consumed_slot():
    predecessor = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))["v9_formal_no_result_predecessor"]
    assert predecessor["claim"] == predecessor["acknowledgement"] == 1
    assert predecessor["dispatches"] == predecessor["runs"] == predecessor["provider_contacts"] == 0
    assert predecessor["untouched_slots"] == 12
