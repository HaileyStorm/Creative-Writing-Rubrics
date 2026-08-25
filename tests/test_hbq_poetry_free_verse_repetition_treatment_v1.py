from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import subprocess
import sys

import pytest

from _hbq_s1_historical_runtime import (
    LegacyHistoricalRuntimeUnbound,
    _declared_bindings,
    _unique_commit_for_bindings,
    install_historical_runtime,
)
from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-treatment-v1"


def study():
    spec = importlib.util.spec_from_file_location("s1_free_verse_repetition_treatment", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return install_historical_runtime(module)
    except LegacyHistoricalRuntimeUnbound as error:
        pytest.skip(str(error))


def test_legacy_package_without_source_commit_fails_closed_instead_of_guessing_a_runtime():
    spec = importlib.util.spec_from_file_location("s1_free_verse_repetition_treatment_unbound", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    assert not hasattr(module, "SOURCE_COMMIT")
    assert _unique_commit_for_bindings(module.REPOSITORY, _declared_bindings(module)) is None
    with pytest.raises(LegacyHistoricalRuntimeUnbound, match="legacy historical runtime is unbound"):
        install_historical_runtime(module)


def test_freeze_is_provider_free_with_exact_private_four_fixture_ab_geometry():
    s = study()
    assert s.validate_package() == {
        "study_id": s.STUDY_ID,
        "provider_calls": 0,
        "opaque_slots": 24,
        "private_fixture_commitments": 4,
        "holdout_eligible_on_verified_success": True,
    }
    contract = s.load_contract()
    assert contract["provider_execution"] == {
        "permitted_now": False,
        "provider_calls_made_now_exact": 0,
        "planned_new_provider_calls_exact": 24,
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "zero_paid_route_required": True,
        "semantic_retries_permitted": False,
        "one_leaf_per_request": True,
    }
    assert contract["geometry"] == {
        "private_fixture_commitments_exact": 4,
        "arms_exact": 2,
        "repeats_exact": 3,
        "opaque_slots_exact": 24,
        "same_fixture_ab": True,
    }


def test_candidate_is_exact_and_preserves_live_leaf_ownership_and_influence_fields():
    s = study()
    source, candidate = s.source_leaf(), s.candidate_leaf()
    assert candidate["text"] == (
        "Presence of recurrence alone does not satisfy this criterion. Answer YES only "
        "when the supplied instances show that recurrence changes pressure or meaning; "
        "when recurrence is present but does not do so, answer NO."
    )
    assert s.source_owner() == {"module_id": "form.poetry.free_verse", "question_id": s.LEAF_ID}
    for key in s.PRESERVED_FIELDS:
        assert candidate[key] == source[key]
    assert s.load_contract()["promotion"] == {
        "prompt": "none", "rubric": "none", "leaf": "none", "owner": "none",
        "weight": "none", "influence": "none", "split": "none",
    }


def test_public_schedule_is_opaque_and_cannot_leak_private_fixture_arm_repeat_or_label_mapping():
    s = study()
    schedule = s.opaque_schedule()
    assert len(schedule) == len({row["opaque_slot_id"] for row in schedule}) == 24
    assert all(set(row) == {"opaque_slot_id"} for row in schedule)
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.suffix in {".json", ".py", ".md"})
    assert "fixture_id" not in public_text
    assert "terminal slot records" in public_text
    assert "summary_boolean_attestation_accepted" in public_text


def test_test_source_contains_no_absolute_or_private_fixture_material():
    s = study()
    test_source = __file__ and open(__file__, encoding="utf-8").read()
    string_literals = [node.value for node in ast.walk(ast.parse(test_source)) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    commitment_tokens = [*s.FIXTURE_COMMITMENTS, s.PRIVATE_CONTROLLER_COMMITMENT, s.PRIVATE_LEDGER_COMMITMENT]
    private_marker = "pri" + "vate"
    absolute_prefixes = (chr(67) + ":" + chr(92), chr(67) + ":" + chr(47))
    assert all(token not in test_source for token in commitment_tokens)
    assert all(
        not value.startswith(absolute_prefixes)
        and not (private_marker in value.casefold() and (chr(47) in value or chr(92) in value or value.endswith(".json")))
        for value in string_literals
    )
    assert all(hashlib.sha256(value.encode("utf-8")).hexdigest() not in s.PRIVATE_VALUE_SHA256 for value in string_literals)


def test_contract_requires_private_terminal_records_not_summary_attestation_for_any_gate():
    s = study()
    gate = s.load_contract()["development_gate"]
    assert gate["derivation"] == "private_verified_terminal_slot_records_only"
    assert gate["summary_boolean_attestation_accepted"] is False
    assert gate["pass_authorizes_only"] == "disjoint_holdout"
    assert not hasattr(s, "assess_private_controller_attestation")


def test_contract_drift_fails_closed_and_dry_run_is_the_only_command_surface():
    s = study()
    contract = deepcopy(s.load_contract())
    contract["development_gate"]["candidate_required"] = "11/12"
    original = s.load_contract
    s.load_contract = lambda: contract
    with pytest.raises(ValueError, match="contract"):
        s.validate_package()
    s.load_contract = original
    completed = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], capture_output=True, text=True, check=True)
    report = json.loads(completed.stdout)
    assert report["provider_calls"] == 0
    assert len(report["opaque_slot_ids"]) == 24
    source = (ROOT / "run.py").read_text(encoding="utf-8").casefold()
    assert "requests" not in source and "execute" not in source and "dspy" not in source
