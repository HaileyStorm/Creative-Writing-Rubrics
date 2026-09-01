from __future__ import annotations

import base64
import builtins
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1"


def module():
    spec = importlib.util.spec_from_file_location("desc18", PACKAGE / "study.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_open_validation_replication_has_exact_64_cell_geometry_and_retained_lineage():
    value = module()
    schedule = value.materialize()
    assert schedule["geometry"] == {"candidates": 2, "grok_cells": 64, "open_validation_groups": 16, "open_validation_items": 32, "sol_cells": 0}
    assert [row["candidate_id"] for row in schedule["candidates"]] == [value.PARENT_ID, value.CHILD_ID]
    assert [row["candidate_sha256"] for row in schedule["candidates"]] == [value.PARENT_CANDIDATE_SHA256, value.CHILD_CANDIDATE_SHA256]
    assert len(schedule["cells"]) == 64
    assert {row["partition"] for row in schedule["cells"]} == {"open_validation_development"}
    assert {row["route_name"] for row in schedule["cells"]} == {"grok_primary"}


def test_parent_bytes_are_unchanged_and_child20_only_replaces_the_retained_profile():
    value = module()
    source, source_schedule = value._source_schedule()
    schedule = value.materialize()
    source_parent = {row["item_id"]: row for row in source_schedule["cells"] if row["candidate_id"] == value.PARENT_ID}
    for row in schedule["cells"]:
        payload = base64.b64decode(row["payload_base64"], validate=True)
        assert row["endpoint_payload_sha256s"] == {"grok_primary": row["payload_sha256"], "sol_veto_if_qualified": row["payload_sha256"]}
        original = base64.b64decode(source_parent[row["item_id"]]["payload_base64"], validate=True)
        if row["candidate_id"] == value.PARENT_ID:
            assert payload == original
        else:
            parent_value = source._strict_raw(original, "parent")
            child_value = source._strict_raw(payload, "child")
            assert {key: item for key, item in child_value.items() if key != "profile"} == {key: item for key, item in parent_value.items() if key != "profile"}
            assert child_value["profile"] != parent_value["profile"]


def test_open_source_targets_and_bindings_are_exact_but_never_enter_the_payload():
    value = module()
    schedule = value.materialize()
    for row in schedule["cells"]:
        payload = json.loads(base64.b64decode(row["payload_base64"], validate=True))
        assert {"target", "target_sha256", "source_binding_sha256"}.isdisjoint(payload)
        assert set(row["target"]) == {"Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"}
    assert schedule["source"] == {"fresh96_validation_freeze_study_sha256": value.SOURCE_SHA256, "public_open_validation_only": True, "private_freeze_read": False}
    assert schedule["authority"]["confirmation"] == "unopened"
    assert schedule["authority"]["reserve"] == "unopened"


def test_frozen_root_replays_deterministically_and_rejects_tampering(tmp_path: Path):
    value = module()
    root = tmp_path / "freeze"
    schedule = value.freeze(root)
    assert value.validate_frozen_root(root) == schedule
    raw = (root / "schedule.json").read_bytes()
    (root / "schedule.json").write_bytes(raw.replace(b'"grok_primary"', b'"grok_primarx"', 1))
    with pytest.raises(ValueError, match="persisted schedule|identity|pairing|endpoint"):
        value.validate_frozen_root(root)


def test_source_and_contract_byte_drift_are_rejected(monkeypatch: pytest.MonkeyPatch):
    value = module()
    monkeypatch.setattr(value, "SOURCE_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="bytes drifted"):
        value.materialize()
    value = module()
    monkeypatch.setattr(value, "CONTRACT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="contract bytes"):
        value.contract()


def test_runtime_import_has_no_dspy_or_optuna_dependency(monkeypatch: pytest.MonkeyPatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}:
            raise AssertionError(f"runtime optimizer import attempted: {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    value = module()
    value.materialize()
    text = (PACKAGE / "study.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in text and "import optuna" not in text
