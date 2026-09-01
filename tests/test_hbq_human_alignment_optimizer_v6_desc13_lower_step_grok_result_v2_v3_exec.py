from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v2-v3-exec"


def test_package_and_exact_v3_blob_pins_are_provider_free():
    spec = importlib.util.spec_from_file_location("_v2_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    value.validate_package()
    assert value._executor().STUDY_ID == value.EXECUTOR_ID
    assert "dspy" not in (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()


def test_loader_refuses_bytes_that_do_not_match_the_admitted_source():
    spec = importlib.util.spec_from_file_location("_v2_result_swap", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    with pytest.raises(ValueError, match="after admission"):
        value._load(PACKAGE / "verify.py", "_mismatch", b"not the admitted source")
