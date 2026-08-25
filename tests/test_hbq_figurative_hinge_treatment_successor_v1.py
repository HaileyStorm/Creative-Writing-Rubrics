from __future__ import annotations

import importlib.util
import sys

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-figurative-hinge-treatment-successor-v1"


def study():
    spec = importlib.util.spec_from_file_location("figurative_hinge_treatment", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hinge_pilot_is_small_control_pure_and_keeps_ownership():
    s = study()
    assert s.validate() == {"study_id": s.STUDY_ID, "slots": 8, "provider_calls": 0, "promotion": "none"}
    assert len(s.schedule()) == 8
    text = s.contract()["treatment"]["exact_text"]
    assert "explicit connective" in text and "not itself a hinge" in text
    assert "familiarity/defaultness" in text and "density" in text


def test_public_cases_have_no_expected_labels():
    s = study()
    assert all(set(case) == {"case_id", "text"} for case in s.corpus())
    assert {slot["case_id"] for slot in s.schedule()} == {"f1", "g2", "h3", "j4"}
