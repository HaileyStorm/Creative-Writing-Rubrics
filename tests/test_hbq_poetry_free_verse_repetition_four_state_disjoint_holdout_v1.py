from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
from pathlib import Path

import pytest
from _hbq_s1_historical_runtime import (
    LegacyHistoricalRuntimeUnbound,
    install_historical_runtime,
)

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1"


def load_current_study():
    spec = importlib.util.spec_from_file_location("s1_four_state_disjoint_holdout_v1_current_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_disjoint_holdout_v1_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return install_historical_runtime(module)
    except LegacyHistoricalRuntimeUnbound as error:
        pytest.skip(str(error))


def test_current_checkout_fails_closed_before_historical_install():
    with pytest.raises(ValueError, match="CWR live HEAD differs from the frozen holdout source head"):
        load_current_study().validate_package()


def test_contract_preserves_v10_lineage_and_freezes_review_only_gate():
    module = study()
    module.assert_historical_runtime()
    value = module.contract()
    assert value == module.expected_contract()
    assert value["predecessor_v10"]["decision"] == "HOLDOUT_ELIGIBLE_ON_SUCCESS"
    assert value["gate"] == {
        "required": "twelve_of_twelve_exact_first_attempt_raw_verdicts",
        "success_authorizes_only": "INDEPENDENT_PROMOTION_REVIEW",
        "automatic_promotion": False,
    }
    assert set(value["promotion"].values()) == {"none"}
    assert value["dspy"] == "forbidden_for_this_holdout"


def test_shuffled_opaque_twelve_slot_geometry_is_complete():
    module = study()
    slots = module.slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 12
    assert all(re.fullmatch(r"q-[0-9a-f]{6}", slot["slot_id"]) for slot in slots)
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["case_id"] for slot in slots} == {row["case_id"] for row in module.corpus()}
    assert all(sum(slot["case_id"] == case_id for slot in slots) == 3 for case_id in {slot["case_id"] for slot in slots})


def test_provider_free_production_render_freezes_all_prompts_without_role_cues():
    module = study()
    with tempfile.TemporaryDirectory(prefix="hbq-s1h-freeze-") as work:
        module.set_work_root(Path(work))
        value = module.dry_run()
        root = module.execution_root()
        manifest = json.loads((root / "dry-manifest.v1.json").read_text(encoding="utf-8"))
        prompts = sorted((root / "rendered-prompts").glob("*.txt"))
        assert value["provider_calls"] == manifest["provider_calls"] == 0
        assert value["rendered_slots"] == manifest["rendered_slots"] == len(prompts) == 12
        assert set(manifest["rendered_prompt_sha256"]) == {slot["slot_id"] for slot in module.slots()}
        for prompt in prompts:
            module.assert_rendered_prompt_privacy(prompt)
            assert "exact_quote" in prompt.read_text(encoding="utf-8")


def test_public_package_contains_no_case_to_expected_state_mapping():
    public = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.iterdir() if path.is_file())
    for case_id in ("s1h-amber", "s1h-birch", "s1h-cinder", "s1h-drift"):
        assert not re.search(rf'"{case_id}"\s*:\s*"(?:YES|NO|NOT_APPLICABLE|CANNOT_ASSESS)"', public)
    assert '"expected_states"' not in (ROOT / "public-synthetic-corpus.json").read_text(encoding="utf-8")


def test_settlement_requires_unique_sessions_and_exact_quote_validity(monkeypatch):
    module = study()
    expected = {slot["case_id"]: "NO" for slot in module.slots()}
    monkeypatch.setattr(module, "sealed_outcomes", lambda: expected)
    records = []
    for ordinal, slot in enumerate(module.slots()):
        records.append({
            "slot_id": slot["slot_id"],
            "raw_verdict": expected[slot["case_id"]],
            "session_sha256": f"{ordinal:064x}",
            "accepted_attempt": 1,
            "rejected_retries": 0,
            "normalization_events": 0,
            "exact_quote_valid": True,
        })
    result = module.verify_settlement_records(records)
    assert result["decision"] == "INDEPENDENT_PROMOTION_REVIEW_ELIGIBLE"
    records[1]["session_sha256"] = records[0]["session_sha256"]
    with pytest.raises(ValueError, match="session"):
        module.verify_settlement_records(records)
