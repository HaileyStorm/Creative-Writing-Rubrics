from __future__ import annotations

import importlib.util
import sys

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-treatment-v1-result-v1"


def verifier():
    spec = importlib.util.spec_from_file_location("s2_nonpoetry_scope_result_v1", ROOT / "verify_output.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_projection_is_fixed_aggregate_only_diagnostic_failure():
    result = verifier()
    assert result.check() == []
