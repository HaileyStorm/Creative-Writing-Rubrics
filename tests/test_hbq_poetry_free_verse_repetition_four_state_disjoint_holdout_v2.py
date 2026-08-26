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

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2"


def load_current_study():
    spec = importlib.util.spec_from_file_location("s1_four_state_disjoint_holdout_v2_current_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_disjoint_holdout_v2_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return install_historical_runtime(module)
    except LegacyHistoricalRuntimeUnbound as error:
        pytest.skip(str(error))


def test_current_checkout_fails_closed_before_historical_install():
    with pytest.raises(ValueError, match="CWR live HEAD differs from the frozen v2 source head"):
        load_current_study().validate_package()


def test_v2_contract_is_bound_to_immutable_v1_and_review_only_gate():
    module = study()
    module.assert_historical_runtime()
    assert module.contract() == module.expected_contract()
    predecessor = module.contract()["predecessor_v1"]
    assert predecessor["external_evidence_immutable"] is True
    assert predecessor["repair_scope"] == "one_public_carrier_replacement"
    assert set(module.contract()["promotion"].values()) == {"none"}
    assert module.contract()["execution"]["execution_entrypoint"] == "unavailable_until_independent_review"


def test_only_one_carrier_changes_and_new_catalog_frame_has_no_answer_gloss():
    module = study()
    previous = {row["case_id"]: row for row in module._v1().corpus()}
    current = {row["case_id"]: row for row in module.corpus()}
    assert all(current[case_id] == previous[case_id] for case_id in ("s1h-amber", "s1h-cinder", "s1h-drift"))
    replacement = current["s1h-garnet"]["text"].casefold()
    assert replacement.count("item:") == replacement.count("place:") == 4
    assert all(marker not in replacement for marker in ("accidental", "inert", "no separate", "no intended", "no effect", "refrain", "insist"))


def test_shuffled_opaque_schedule_covers_twelve_singleton_slots():
    module = study()
    slots = module.slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 12
    assert all(re.fullmatch(r"q-[0-9a-f]{6}", slot["slot_id"]) for slot in slots)
    assert all(sum(slot["case_id"] == case_id for slot in slots) == 3 for case_id in {slot["case_id"] for slot in slots})


def test_provider_free_render_rejects_study_role_and_case_cues():
    module = study()
    with tempfile.TemporaryDirectory(prefix="hbq-s1h-v2-freeze-") as work:
        module.set_work_root(Path(work))
        report = module.dry_run()
        root = module.execution_root()
        manifest = json.loads((root / "dry-manifest.v2.json").read_text(encoding="utf-8"))
        prompts = sorted((root / "rendered-prompts").glob("*.txt"))
        assert report["provider_calls"] == manifest["provider_calls"] == 0
        assert len(prompts) == manifest["rendered_slots"] == 12
        for prompt in prompts:
            module.assert_prompt_privacy(prompt)
            assert "exact_quote" in prompt.read_text(encoding="utf-8")


def test_public_source_exposes_no_outcome_map_or_execution_switch():
    public = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("public-synthetic-corpus.json", "study-contract.json", "README.md"))
    for case_id in ("s1h-amber", "s1h-garnet", "s1h-cinder", "s1h-drift"):
        assert not re.search(rf'"{case_id}"\s*:\s*"(?:YES|NO|NOT_APPLICABLE|CANNOT_ASSESS)"', public)
    assert "--execute" not in (ROOT / "run.py").read_text(encoding="utf-8")
    for forbidden in ("C:\\Users\\", "target_verdict", "oracle"):
        assert forbidden not in public


def test_verifier_requires_unique_first_attempt_exact_quote_records(monkeypatch):
    module = study()
    expected = {slot["case_id"]: "NO" for slot in module.slots()}
    monkeypatch.setattr(module, "sealed_outcomes", lambda: expected)
    records = [{"slot_id": slot["slot_id"], "raw_verdict": expected[slot["case_id"]], "session_sha256": f"{index:064x}", "accepted_attempt": 1, "rejected_retries": 0, "normalization_events": 0, "exact_quote_valid": True} for index, slot in enumerate(module.slots())]
    assert module.verify_settlement_records(records)["decision"] == "INDEPENDENT_PROMOTION_REVIEW_ELIGIBLE"
    records[2]["exact_quote_valid"] = False
    with pytest.raises(ValueError, match="exact-quote-valid"):
        module.verify_settlement_records(records)
