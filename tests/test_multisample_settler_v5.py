from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from _scoped_module_loader import isolated_import_state


SETTLER = (
    Path(__file__).resolve().parents[1]
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-remainder-capacity-reset-settler-v5"
    / "settle.py"
)


@pytest.fixture(autouse=True)
def _isolate_generic_study_alias():
    with isolated_import_state("study"):
        yield


def settler():
    spec = importlib.util.spec_from_file_location("multisample_settler_v5", SETTLER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freeze_v4_live_exact():
    frozen = settler().freeze()
    assert frozen["batch_count"] == 6
    assert frozen["verdict_count"] == 179


def test_settle_requires_empty_root(tmp_path):
    module = settler()
    (tmp_path / "x").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        module.settle(tmp_path)


def test_owner_validator_is_invoked_and_failure_propagates(monkeypatch):
    module = settler()
    called = []

    def owner_validator():
        def fail(*args):
            called.append(args)
            raise ValueError("owner failure")

        return fail

    monkeypatch.setattr(module, "_owner_validator", owner_validator)
    with pytest.raises(ValueError, match="owner failure"):
        module.freeze()
    assert called


def test_committed_execution_has_exact_lineage_counts():
    execution = settler().execution()
    assert execution["lineage_sessions"]["source"]["unique_count"] == 146
    assert execution["lineage_sessions"]["closed"]["unique_count"] == 183
