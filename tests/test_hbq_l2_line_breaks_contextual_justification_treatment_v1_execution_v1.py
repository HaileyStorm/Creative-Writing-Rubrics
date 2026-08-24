from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from hbqrs.paths import book_root
from tests import _hbq_l2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-contextual-justification-treatment-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("l2_contextual_treatment_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return historical_runtime.install(module)


def test_frozen_executor_binds_treatment_bytes_runtime_leaf_and_pair_hashes():
    s = study()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "source_commit": s.SOURCE_COMMIT, "slots": 18, "provider_calls": 0, "image_slots": 0}
    assert s.SOURCE_COMMIT.startswith("9fe172f")
    assert s.contract()["pair_prompt_hashes"] == s.PAIR_PROMPT_HASHES
    assert s.contract()["compiled_leaf_hash"] == s.COMPILED_LEAF_HASH


def test_schedule_is_exactly_eighteen_sequential_treatment_only_slots_without_metadata_leakage():
    s = study()
    slots = s.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 18
    assert [slot["slot_id"] for slot in slots] == [f"l2contextexec-v1-{index:03d}" for index in range(1, 19)]
    assert {slot["leaf_id"] for slot in slots} == {s.LINE_BREAKS}
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert all(slot["image_input"] is None for slot in slots)
    rendered = "\n".join(slot["prompt"] for slot in slots).casefold()
    for forbidden in ("expected-ledger", "baseline", "necessity", "holdout"):
        assert forbidden not in rendered


def test_aggregate_gate_requires_six_complete_three_of_three_cells():
    s = study()
    slots = s.build_schedule()
    records = [{"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "run_id": slot["run_id"], "verdict": "YES", "normalization_audit": []} for slot in slots]
    settlement, public = s._aggregate_test_only(schedule=slots, records=records, scorer=lambda slot, record: True)
    assert settlement["decision"] == public["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert settlement["aggregate_cells"] == {"zero_of_three": 0, "one_of_three": 0, "two_of_three": 0, "three_of_three": 6, "total": 6}
    settlement, _ = s._aggregate_test_only(schedule=slots, records=records, scorer=lambda slot, record: slot["slot_id"] != "l2contextexec-v1-001")
    assert settlement["decision"] == "NO_GO_DSPY_ELIGIBLE_ONLY"
    with pytest.raises(ValueError, match="every unique singleton"):
        s._aggregate_test_only(schedule=slots, records=records[:-1], scorer=lambda slot, record: True)


def test_execution_needs_explicit_authority_before_any_private_root_access(tmp_path: Path):
    s = study()
    with pytest.raises(ValueError, match="explicit allow-remote"):
        s.execute(tmp_path)


def test_warmed_executor_revalidates_runtime_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    s = study()
    s._lifecycle()
    s._source()
    s.build_schedule()
    drifted = dict(s.RUNTIME_BLOBS)
    drifted["src/hbqrs/runner.py"] = "0" * 40
    monkeypatch.setattr(s, "RUNTIME_BLOBS", drifted)
    contacts: list[str] = []

    def contact_trap(*args, **kwargs):
        contacts.append("contact")
        raise AssertionError("runtime drift reached a contact boundary")

    with pytest.raises(ValueError, match="contract|runtime"):
        s.execute(
            tmp_path,
            allow_remote=True,
            acknowledged_zero_incremental_charge=True,
            runner_call=contact_trap,
            auth_call=contact_trap,
        )
    assert contacts == []
