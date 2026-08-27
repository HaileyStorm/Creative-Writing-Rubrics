from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

from hbqrs import runner
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-ox-alpha-polarity-batch-successor-v1"


def load(name: str, file: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules[spec.name] = module
    sys.modules.update(aliases or {})
    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


study = load("ox_recovery_study", "study.py")
live = load("ox_recovery_live", "live.py", {"study": study})
recovery = load("ox_recovery_overlay", "recovery.py", {"live": live})


def test_overlay_preserves_crlf_text_records_when_reconstructing_prompt(monkeypatch, tmp_path):
    prompts = tmp_path / "prompts" / "judge"
    prompts.mkdir(parents=True)
    binary_path = prompts / "BINARY_EVALUATION_PROMPT.md"
    binary_path.write_bytes(b"judge line 1\r\njudge line 2\r\n")
    artifact = tmp_path / "source.md"
    context = tmp_path / "prompt.md"
    contract = tmp_path / "task.json"
    artifact.write_bytes(b"artifact\r\ntext\r\n")
    context.write_bytes(b"context\r\ntext\r\n")
    contract.write_text("{}", encoding="utf-8")
    question = {"question": {"id": "q"}}
    monkeypatch.setattr(recovery, "prompts_dir", lambda: tmp_path / "prompts")
    monkeypatch.setattr(recovery.v1, "_effective_question_ids", lambda *_: ["q"])
    monkeypatch.setattr(recovery, "load_modules", lambda *_: {})
    monkeypatch.setattr(recovery, "load_bundles", lambda *_: {})
    monkeypatch.setattr(recovery, "resolve_bundle", lambda *_: {})
    monkeypatch.setattr(recovery, "materialize_weight_profile", lambda *_: ({}, {}, None))
    monkeypatch.setattr(recovery, "compile_bundle", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(recovery, "compiled_questions", lambda *_: [question])
    row = {"story_id": "story", "question_ids": ["q"]}
    inputs = {"artifact": str(artifact), "prompt": str(context), "task_contract": str(contract)}
    expected = runner._render_prompt(binary_prompt=runner._read_text_record(binary_path)["text"].strip(), artifact=runner._read_text_record(artifact), contexts=[runner._read_text_record(context)], bundle_id="prose.short_story", artifact_id="story", questions=[question], provider="nous", model="stealth/ox-alpha").encode("utf-8")
    assert recovery._expected_prompt(row, inputs, tmp_path / "projection.json") == expected
    assert b"\r\n" in expected


def test_raw_current_runtime_fails_closed_before_historical_recovery_adapter():
    work = Path(os.environ.get("HBQ_OX_ALPHA_SUCCESSOR_ROOT", str(Path.home() / "Documents" / "cwr-ox-alpha-polarity-batch-successor-v1-private-20260822")))
    if not (work / "reconciliation-v1.json").is_file():
        pytest.skip("sealed private successor evidence is unavailable")
    with pytest.raises(ValueError, match=re.escape("Recovery source does not bind the sealed v1 runtime and inputs")):
        recovery._source(work)


def test_historical_recovery_adapter_seals_isolation_and_cached_snapshots():
    from _ox_historical_runtime import (
        BUNDLES_BYTES,
        BUNDLES_RELATIVE,
        BUNDLES_SHA256,
        RUNNER_BYTES,
        RUNNER_RELATIVE,
        RUNNER_SHA256,
        _repository_for_module,
        _snapshot_file,
        historical_recovery,
    )

    canonical_runner = runner
    original_runner = recovery.hbq_runner
    original_bundles_path = recovery.bundles_path
    assert canonical_runner is runner
    with historical_recovery(recovery):
        mounted_runner = recovery.hbq_runner
        mounted_runner_bytes = Path(mounted_runner.__file__).read_bytes()
        assert mounted_runner is not canonical_runner
        assert len(mounted_runner_bytes) == RUNNER_BYTES
        assert hashlib.sha256(mounted_runner_bytes).hexdigest() == RUNNER_SHA256
        mounted_bundles = recovery.bundles_path()
        mounted_bundle_bytes = mounted_bundles.read_bytes()
        assert len(mounted_bundle_bytes) == BUNDLES_BYTES
        assert hashlib.sha256(mounted_bundle_bytes).hexdigest() == BUNDLES_SHA256
        with pytest.raises(ValueError, match="already installed"), historical_recovery(recovery):
            pass
        assert recovery.hbq_runner is mounted_runner
        assert recovery.bundles_path() == mounted_bundles
        assert getattr(recovery, "_ox_historical_recovery_installed", False) is True
    assert recovery.hbq_runner is original_runner
    assert recovery.bundles_path is original_bundles_path
    assert recovery.hbq_runner is canonical_runner
    assert not hasattr(recovery, "_ox_historical_recovery_installed")

    with pytest.raises(RuntimeError, match="leave the adapter installed"), historical_recovery(recovery):
        raise RuntimeError("leave the adapter installed")
    assert recovery.hbq_runner is original_runner
    assert recovery.bundles_path is original_bundles_path
    assert recovery.hbq_runner is canonical_runner
    assert not hasattr(recovery, "_ox_historical_recovery_installed")

    repository = _repository_for_module(recovery)
    bundle_snapshot = _snapshot_file(repository, BUNDLES_RELATIVE, BUNDLES_SHA256, BUNDLES_BYTES)
    original_bundle_bytes = bundle_snapshot.read_bytes()
    try:
        bundle_snapshot.write_bytes(original_bundle_bytes + b"tamper")
        with pytest.raises(ValueError, match=f"Pinned Ox historical bytes were mutated: {BUNDLES_RELATIVE}"), historical_recovery(recovery):
            pass
    finally:
        bundle_snapshot.write_bytes(original_bundle_bytes)
    assert not hasattr(recovery, "_ox_historical_recovery_installed")
    runner_snapshot = _snapshot_file(repository, RUNNER_RELATIVE, RUNNER_SHA256, RUNNER_BYTES)
    assert runner_snapshot.is_file()


def test_private_recovery_overlay_reclassifies_only_the_deterministic_quarantines():
    work = Path(os.environ.get("HBQ_OX_ALPHA_SUCCESSOR_ROOT", str(Path.home() / "Documents" / "cwr-ox-alpha-polarity-batch-successor-v1-private-20260822")))
    if not (work / "reconciliation-v1.json").is_file():
        pytest.skip("sealed private successor evidence is unavailable")
    from _ox_historical_runtime import historical_recovery

    with historical_recovery(recovery):
        payload = recovery.reconcile(work)
    assert payload["source_status_counts"] == {"accepted": 0, "eligible_524": 12, "quarantined": 18, "global_stop": 0}
    assert payload["effective_status_counts"] == {"accepted": 17, "eligible_524": 12, "quarantined": 1, "global_stop": 0}
    assert len(payload["reconciled_results"]) == 17
    assert payload["analysis"]["accepted_records"] == 20
    assert payload["confirmation_available"] is False
    assert payload["production_recommendation"] is None


def test_public_recovery_manifest_is_path_free_and_binds_the_private_evidence():
    manifest_path = ROOT / "recovery-result-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["kind"] == "public_recovery_result_summary"
    assert manifest["source"]["status_counts"] == {"accepted": 0, "eligible_524": 12, "quarantined": 18, "global_stop": 0}
    assert manifest["recovery"]["overlay_sha256"] == "a4b30c0c8804e9b35caf706d9fa42181d7cf2d5ceddb05515ae4de35daf4fa81"
    assert manifest["recovery"]["effective_status_counts"] == {"accepted": 17, "eligible_524": 12, "quarantined": 1, "global_stop": 0}
    assert manifest["recovery"]["accepted_leaf_records"] == 20
    assert manifest["recovery"]["confirmation_available"] is False
    assert manifest["recovery"]["production_recommendation"] is None
    assert manifest["retry_successor"] == {"contract_sha256": "4560826b17a74c8b0a7704d1203a41734e54305acdd2eb2e9216abc2d6d397a9", "logical_calls": 12, "maximum_physical_calls": 60, "prepared": True, "executable": False, "launched": False}
    assert not re.search(r"[A-Za-z]:[\\/]", manifest_path.read_text(encoding="utf-8"))
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "No confirmation or production recommendation is available." in readme
    assert "not executable" in readme and "or launched." in readme
