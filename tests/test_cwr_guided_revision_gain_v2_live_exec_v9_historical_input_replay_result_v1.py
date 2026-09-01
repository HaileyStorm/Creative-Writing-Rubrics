from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v9-historical-input-replay-result-v1"
V8_RESULT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v8-crlf-replay-result-v1" / "result.json"
LIVE_V7_ROOT = Path(r"C:\Users\Haile\Documents\cwr-revision-gain-v7-endpoints-1affc2c-20260831b")


def mod():
    spec = importlib.util.spec_from_file_location("v9_historical_input_replay", ROOT / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def _live_root() -> Path:
    if not LIVE_V7_ROOT.is_dir():
        pytest.skip("completed immutable V7 root is not present on this host")
    return LIVE_V7_ROOT.resolve()


def test_contract_binds_historical_git_bytes_not_current_v6() -> None:
    package = mod()
    contract = package.contract()
    historical = contract["historical_v6"]
    assert historical == {
        "commit": "c24a9eccaa5faea820f7a2b392e53293240792b1",
        "repository_path": "evaluation-results/cwr-guided-revision-gain-v2-live-exec-v6-single-replacement/executor.py",
        "git_blob_oid": "100c9e70ebe4d550249c47e5f775b30d4515361a",
        "sha256": "e0f4181e4daed637b6c8e438e71b90129505bd2191202dd2ef43e0f7e406d172",
    }
    assert package.sha(package._git_blob()) == historical["sha256"]
    source = (ROOT / "executor.py").read_text(encoding="utf-8")
    for forbidden in ("allow_remote", "execute_endpoint_wave", "model-work-queue", "requests.", "http://", "https://"):
        assert forbidden not in source


def test_rejects_historical_blob_and_current_dependency_substitution(monkeypatch: pytest.MonkeyPatch) -> None:
    package = mod()
    monkeypatch.setattr(package, "HISTORICAL_V6_GIT_BLOB_OID", "0" * 40)
    with pytest.raises(ValueError, match="Git blob binding"):
        package._git_blob()
    package = mod()
    monkeypatch.setattr(package, "_git_blob", lambda: b"current V6 successor bytes")
    with pytest.raises(ValueError, match="Git blob content drifted"):
        package._load_historical_v6()


def test_live_immutable_root_replay_matches_published_v8_projection() -> None:
    package = mod()
    result = package.replay_completed_v7(source_root=_live_root())
    assert result["provider_calls_made"] == 0
    assert result["evidence_status"] == "historical_development_evidence_only"
    assert len(result["underlying_endpoint_rows"]) == 40
    assert len(result["primary_guided_minus_control"]) == 16
    assert len(result["arm_minus_baseline"]) == 32
    assert result["endpoint_results_are_not_pooled"] is True
    assert result["study_id"] == package.STUDY_ID
    assert result["v8_projection_parity"] == {"expected_sha256": package.V8_PROJECTION_SHA256, "actual_sha256": package.V8_PROJECTION_SHA256, "status": "exact_parity"}
    published = json.loads(V8_RESULT.read_text(encoding="utf-8"))
    assert package._projection(result) == package._projection(published)


def test_rejects_mutated_receipt_and_immutable_source(tmp_path: Path) -> None:
    package = mod()
    copied = tmp_path / "completed-v7"
    shutil.copytree(_live_root(), copied)
    receipt = next((copied / "cells").glob("*/verified-receipt.json"))
    original_receipt = receipt.read_bytes()
    forged = json.loads(original_receipt)
    forged["response"]["overall"] = 99
    receipt.write_bytes(package.canonical(forged) + b"\n")
    with pytest.raises(ValueError):
        package.replay_completed_v7(source_root=copied.resolve())
    receipt.write_bytes(original_receipt)
    immutable = copied / "immutable-inputs.json"
    immutable.write_bytes(immutable.read_bytes() + b" ")
    with pytest.raises(ValueError):
        package.replay_completed_v7(source_root=copied.resolve())
