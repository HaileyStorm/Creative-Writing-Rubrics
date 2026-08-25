from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parents[1]
PACKAGE = HERE / "evaluation-results" / "hbq-qpc24-exact-head-successor-v1-terminal-v4"


def test_public_v4_terminal_projection_is_aggregate_only_and_nonvoting() -> None:
    spec = importlib.util.spec_from_file_location("qpc24_terminal", PACKAGE / "verify_terminal.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    value = module.verify()
    assert value["planned_provider_calls"] == 150
    assert value["contacted_provider_calls"] == 1
    assert value["accepted_provider_calls"] == value["voting_provider_calls"] == 0
    assert value["untouched_provider_calls"] == 149
