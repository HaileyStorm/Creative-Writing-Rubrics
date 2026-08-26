from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v2-execution-v2"

ARCHIVED_FREEZE = pytest.mark.skip(
    reason=(
        "Archived freeze mechanics require reconstructing a package absent from "
        "declared source commit 6ae9ee0; the current checkout remains fail-closed."
    )
)


def study():
    spec = importlib.util.spec_from_file_location("s1_incidental_v2_public_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_checkout_fails_closed_before_archival_mechanics():
    with pytest.raises(ValueError, match="V2 source identity drifted"):
        study().validate_package()


def test_archived_v2_preserves_v1_carrier_candidate_and_terminal_lineage_but_uses_new_slots():
    value = study()
    contract = value.contract()
    assert contract["status"] == "provider_free_frozen_unexecuted"
    assert contract["execution"]["provider"] == "codex"
    assert contract["execution"]["slots"] == 3
    assert value.artifact() == value._v1().artifact()
    assert {row["slot_id"] for row in value.slots()}.isdisjoint({row["slot_id"] for row in value._v1().slots()})
    assert value.contract()["predecessor"]["terminal_sha256"] == value.V1_TERMINAL_SHA256
    assert value.contract()["candidate"] == value.inherited_candidate_contract()
    assert value.contract()["candidate_sha256"] == value.V1_CANDIDATE_SHA256
    task = value._task(value.slots()[0])
    assert task["context"]["background"] == ["Evaluate the recurrence of the determiner ‘the’ across the supplied poem."]


def test_v2_rejects_a_mutated_inherited_candidate_contract_before_freeze(monkeypatch):
    value = study()
    altered = {"leaf_id": value.LEAF_ID, "text": "mutated candidate wording"}
    monkeypatch.setattr(value, "inherited_candidate_contract", lambda: altered)
    with pytest.raises(ValueError, match="V2 inherited candidate"):
        value.candidate_leaf()


@ARCHIVED_FREEZE
def test_v2_dry_freeze_is_provider_free_and_uses_three_new_raw_prompts(tmp_path: Path):
    value = study()
    result = value.dry_freeze(tmp_path)
    assert result["provider_calls"] == 0 and result["slots"] == 3
    root = tmp_path / "execution-dry-v2"
    assert {path.stem.split(".")[0] for path in (root / "frozen-prompts").glob("*.txt")} == {"v2-3d1a", "v2-7fe4", "v2-c928"}
