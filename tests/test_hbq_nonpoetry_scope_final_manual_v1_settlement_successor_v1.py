from __future__ import annotations

import importlib.util
import gzip
import json
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-final-manual-v1-settlement-successor-v1"
def study():
    spec = importlib.util.spec_from_file_location("s2_final_manual_settlement_successor", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_settlement_rejects_non_ab_schedule_before_slot_verification(tmp_path: Path, monkeypatch):
    s = study()
    execution = tmp_path / "private" / s.EXECUTION_DIRECTORY
    execution.mkdir(parents=True)
    (execution / "settlement.v1.json").write_text(json.dumps({"study_id": s.STUDY_ID, "decision": "INCOMPLETE", "completed_slots": 0, "planned_slots": 24, "failures": [], "promotion": "none"}), encoding="utf-8")
    (execution / "runtime-schedule.json").write_text('{"study_id":"hbq-nonpoetry-scope-final-manual-v1-execution-v1","provider_calls":0,"slots":[' + ','.join('{"slot_id":"x%02d","arm":"baseline","repeat":1}' % index for index in range(24)) + ']}', encoding="utf-8")
    monkeypatch.setattr(s, "source_commit_is_ancestor", lambda: True)
    monkeypatch.setattr(s, "private_execution_root", lambda _root: execution)
    monkeypatch.setattr(s, "sha256_file", lambda path: s.ORIGINAL_RUNTIME_SCHEDULE_SHA256 if path.name == "runtime-schedule.json" else s.ORIGINAL_INCOMPLETE_SETTLEMENT_SHA256)
    with pytest.raises(ValueError, match="A/B schedule"):
        s.settle(tmp_path / "private")


def test_checkpoint_prompt_comparison_allows_only_crlf_transport_normalization(tmp_path: Path):
    s = study()
    assert s.canonical_prompt_bytes(gzip.decompress(gzip.compress(b"one\r\ntwo\r\n"))) == b"one\ntwo\n"
    with pytest.raises(ValueError, match="lone"):
        s.canonical_prompt_bytes(b"one\rtwo\n")


def test_successor_outputs_are_immutable(tmp_path: Path):
    s = study()
    target = tmp_path / "result.json"
    s.write_once(target, {"value": 1})
    with pytest.raises(ValueError, match="immutable"):
        s.write_once(target, {"value": 2})
