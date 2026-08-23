from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-scope-sentinel-v1-settlement-successor-v1"
SOURCE_ROOT = Path(os.environ.get("CWR_S1_SETTLEMENT_SOURCE_ROOT", r"C:\Users\Haile\Documents\cwr-s1-poetry-scope-sentinel-execution-v1-postcommit-9e22d71-20260823"))


def study():
    spec = importlib.util.spec_from_file_location("s1_settlement_successor_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def accepted_record(slot: dict[str, object]) -> dict[str, object]:
    ordinal = 10 * int(str(slot["slot_id"]).split("-")[-2]) + int(str(slot["slot_id"]).split("-")[-1].removeprefix("r"))
    return {
        "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": slot["expected_verdict"],
        "expected": slot["expected_verdict"], "correct": True, "session_id_sha256": f"{ordinal:064x}",
        "checkpoint_chain_head_sha256": f"{1000 + ordinal:064x}",
    }


@pytest.fixture
def source_root() -> Path:
    if not SOURCE_ROOT.is_dir():
        pytest.skip("S1 completed external source evidence is not available on this host")
    return SOURCE_ROOT


def test_historical_runtime_binding_allows_head_advance():
    s = study()
    report = s.validate_package()
    assert report == {
        "study_id": s.STUDY_ID,
        "execution_slots": 60,
        "provider_calls": 0,
        "historical_runtime_head": "9e22d715b0c05a8a411c48c6cf8471053c26a731",
    }
    assert s._git("rev-parse", "HEAD") != s.HISTORICAL_RUNTIME_HEAD


def test_command_boundary_cannot_execute_or_write_the_original_evidence():
    study_text = (ROOT / "study.py").read_text(encoding="utf-8")
    command_text = (ROOT / "run.py").read_text(encoding="utf-8")
    assert "execution.execute(" not in study_text
    assert "execution.settle(" not in study_text
    assert "execution.prepare(" not in study_text
    assert "--execute" not in command_text
    assert "--allow-remote" not in command_text


def test_settlement_reads_source_without_changing_any_source_byte(source_root: Path, tmp_path: Path):
    s = study()
    before = source_snapshot(source_root)
    result = s.settle(source_root, tmp_path / "successor-private", verifier=lambda _root, slot: accepted_record(slot))
    assert result["provider_calls"] == 0
    assert result["completed_execution_slots"] == 60
    assert source_snapshot(source_root) == before
    assert hashlib.sha256((source_root / "settlement.json").read_bytes()).hexdigest() == s.SOURCE_SETTLEMENT_SHA256
    assert hashlib.sha256((source_root / "public-aggregate.json").read_bytes()).hexdigest() == s.SOURCE_PUBLIC_SHA256


def test_nested_destination_is_rejected_without_changing_source_bytes(source_root: Path):
    s = study()
    before = source_snapshot(source_root)
    with pytest.raises(ValueError, match="disjoint"):
        s.settle(source_root, source_root / "nested-successor-output")
    with pytest.raises(ValueError, match="disjoint"):
        s.settle(source_root / "nested-source", source_root)
    assert source_snapshot(source_root) == before


def test_declared_historical_blob_tamper_fails_closed(monkeypatch):
    s = study()
    tampered = dict(s.RUNTIME_BLOBS)
    tampered["src/hbqrs/runner.py"] = "0" * 40
    monkeypatch.setattr(s, "RUNTIME_BLOBS", tampered)
    with pytest.raises(ValueError, match="Historical runtime"):
        s.validate_package()


def test_declared_run_tamper_fails_full_per_slot_verifier(source_root: Path, tmp_path: Path):
    s = study()
    copied = tmp_path / "source-copy"
    shutil.copytree(source_root, copied)
    execution = s._execution()
    schedule, _ = s._validate_source(copied, execution)
    run = copied / "runs" / str(schedule[0]["slot_id"]) / "run.json"
    run.write_bytes(run.read_bytes() + b"\n")
    with pytest.raises((ValueError, s.runner.HBQError)):
        execution._verify_slot(copied, schedule[0])


def test_integrity_failure_is_incomplete_and_public_projection_is_allowlisted(tmp_path: Path):
    s = study()
    result = s.settle(tmp_path / "missing-source", tmp_path / "successor-private")
    public = json.loads((tmp_path / "successor-private" / "public-aggregate.json").read_text(encoding="utf-8"))
    assert result["decision"] == "INCOMPLETE"
    assert public["publicable"] is False
    assert s._privacy_failures(public) == []
    text = json.dumps(public, sort_keys=True).lower()
    for forbidden in ("\\\\users\\\\", "prompt", "evidence", "session_id", "run_id"):
        assert forbidden not in text
