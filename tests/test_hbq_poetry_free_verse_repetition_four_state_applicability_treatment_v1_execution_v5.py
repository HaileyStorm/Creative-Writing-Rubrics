from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v5"


def study():
    spec = importlib.util.spec_from_file_location("s1_four_state_v5_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_absence_control_rejects_common_word_recurrence_and_preserves_natural_single_sentence() -> None:
    value = study()
    value.recurrence_free_absence_text("Limestone fog crosses the harbor; gulls wheel, shutters rattle, dusk arrives.")
    with pytest.raises(ValueError, match="lexical token"):
        value.recurrence_free_absence_text("The lantern shakes while the harbor sleeps.")
    with pytest.raises(ValueError, match="single-sentence"):
        value.recurrence_free_absence_text("Limestone fog crosses harbor. Gulls wheel beyond shutters.")


def test_v5_contract_retains_v4_and_v2_lineage_and_requires_construct_gate() -> None:
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["v4_provider_free_predecessor"]["provider_calls"] == 0
    assert contract["v2_historical_preexecution_snapshot"]["provider_calls_at_snapshot"] == 0
    assert contract["v2_current_outcome_binding"]["formal_result"] == "NO_RESULT"
    assert contract["absence_construct_gate"] == {
        "artifact_text_only": True, "casefolded_lexical_tokens_unique": True,
        "contiguous_two_token_phrases_unique": True, "single_sentence_single_line": True,
        "failure": "NO_RESULT_REFREEZE_REQUIRED",
    }
