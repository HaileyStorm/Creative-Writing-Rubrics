from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-repair-chain-v3"
PUBLIC_SHA = "627cf7039c5bec363184db1216fe344b08ed8b2f128f60413ce07f16c26e758a"
TERMINAL_SHA = "f5eab90a89ce209acda14b35601ebd39b25fb18a7b29cd1e16b534980fc76074"


def _executor():
    spec = importlib.util.spec_from_file_location("preface_recovery_v3", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_package_compiles_and_contract_locks_one_recovery_attempt():
    executor = _executor()
    value = executor.contract()
    assert value["study_id"] == "hbq-ai-writer-preface-v1-repair-chain-v3"
    assert value["lineage"] == {"v2_public_settlement_sha256": PUBLIC_SHA, "v2_private_failed_terminal_sha256": TERMINAL_SHA}
    assert value["recovery"]["kind"] == "pre_contact_infrastructure_recovery"
    assert value["recovery"]["max_additional_attempts"] == 1
    assert value["locked_leaf"] == executor.LOCKED


def test_v2_lineage_requires_the_exact_settlement_and_precontact_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor()
    public, private = tmp_path / "public", tmp_path / "private"
    (private / "repair-attempts" / "01").mkdir(parents=True); public.mkdir()
    settlement = {"study_id": "hbq-ai-writer-preface-v1-repair-chain-v2"}
    terminal = {"status": "terminal_failure_or_uncertain", "failed_leaf_id": executor.LEAF, "locked": executor.LOCKED, "provider_attestation": "unavailable"}
    settlement_path, terminal_path = public / "offline-settlement.json", private / "repair-attempts" / "01" / "terminal.json"
    settlement_path.write_text(json.dumps(settlement), encoding="utf-8"); terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    monkeypatch.setattr(executor, "contract", lambda: {"lineage": {"v2_public_settlement_sha256": executor._sha(settlement_path.read_bytes()), "v2_private_failed_terminal_sha256": executor._sha(terminal_path.read_bytes())}})
    found = executor._verify_v2(public, private)
    assert found["classification"] == "pre_contact_infrastructure_recovery"
    terminal["provider_attestation"] = "attested"; terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="pre-contact"):
        executor._verify_v2(public, private)


def test_disclosure_is_quote_only_and_keeps_the_original_lock(monkeypatch: pytest.MonkeyPatch):
    executor = _executor()
    prompt = "LOCKED ORIGINAL: " + json.dumps(executor.LOCKED, sort_keys=True)
    disclosure = executor._disclosure(prompt)
    assert disclosure["repair_attempt_id"] == "cell17-quote-recovery-v3-01"
    assert disclosure["failed_leaf_id"] == executor.LEAF
    assert disclosure["locked"] == executor.LOCKED
    assert disclosure["paid_api"] is False
    assert disclosure["human_judgment"] is False
    assert disclosure["prompt_sha256"] == executor._sha(prompt)


def test_existing_terminal_blocks_a_second_provider_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor()
    private = tmp_path / "private"; private.mkdir()
    executor._atomic(private / executor.PRIVATE_ATTEMPT, {"status": "valid_quote_repair"})
    monkeypatch.setattr(executor, "_verify", lambda *_args: (object(), {}))
    result = executor.execute_one(*(tmp_path / name for name in ("work", "private", "ow", "op", "cw", "cp", "v2w", "v2p")), allow_remote=True)
    assert result == {"provider_calls": 0, "status": "settled"}


def test_settlement_labels_v2_as_lineage_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor()
    work, private = tmp_path / "work", tmp_path / "private"; work.mkdir(); private.mkdir()
    monkeypatch.setattr(executor, "_verify", lambda *_args: (object(), {"bound": True}))
    monkeypatch.setattr(executor, "contract", lambda: {"study_id": "hbq-ai-writer-preface-v1-repair-chain-v3"})
    summary = executor.settle_offline(*(path for path in (work, private, tmp_path / "ow", tmp_path / "op", tmp_path / "cw", tmp_path / "cp", tmp_path / "v2w", tmp_path / "v2p")))
    assert summary["provider_calls"] == 0
    assert summary["v2_lineage"] == {"classification": "pre_contact_infrastructure_recovery", "counts_as_vote": False, "counts_as_repair": False}
    assert summary["recovery"]["attempts"] == 0


def test_actual_sealed_parents_prepare_and_render_without_provider_contact(tmp_path: Path):
    executor = _executor()
    base = Path(os.environ.get("CWR_PREFACE_EVIDENCE_ROOT", "C:/Users/Haile/Documents"))
    original_work, original_private = base / "cwr-ai-preface-pilot-public-20260822", base / "cwr-ai-preface-pilot-private-20260822"
    continuation_work, continuation_private = base / "cwr-ai-preface-continuation-public-20260822", base / "cwr-ai-preface-continuation-private-20260822"
    v2_work, v2_private = base / "cwr-ai-preface-repair-chain-public-20260822", base / "cwr-ai-preface-repair-chain-private-20260822"
    if not all(path.is_dir() for path in (original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)):
        pytest.skip("sealed preface evidence roots unavailable")
    work, private = tmp_path / "public", tmp_path / "private"
    assert executor.prepare(work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)["provider_calls"] == 0
    preview = executor.render_next_disclosure(work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
    assert preview["provider_calls"] == 0
    assert preview["status"] == "pending"
    assert preview["disclosure"]["locked"] == executor.LOCKED
    with pytest.raises(ValueError, match="allow-remote"):
        executor.execute_one(work, private, original_work, original_private, continuation_work, continuation_private, v2_work, v2_private)
