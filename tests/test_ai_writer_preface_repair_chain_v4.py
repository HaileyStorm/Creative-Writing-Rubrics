from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from tests import _preface_continuation_historical_runtime as historical_runtime


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-repair-chain-v4"
PUBLIC_SHA = "ad2944e1fb0cd40d9bdfbc880bfcd3764a173bd318a29b732c16bb94e37d96fa"
TERMINAL_SHA = "db2a166e06cac3e42c556d174e33bcb6441b31bc53265190a579dde701fd9855"


def _executor():
    spec = importlib.util.spec_from_file_location("preface_recovery_v4", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return historical_runtime.install(module)


def test_contract_locks_the_exact_v3_lineage_and_one_call_cap():
    executor = _executor(); value = executor.contract()
    assert value["study_id"] == "hbq-ai-writer-preface-v1-repair-chain-v4"
    assert value["lineage"] == {"v3_public_settlement_sha256": PUBLIC_SHA, "v3_private_failed_terminal_sha256": TERMINAL_SHA}
    assert value["recovery"]["kind"] == "pre_contact_infrastructure_recovery"
    assert value["recovery"]["max_additional_attempts"] == 1
    assert value["locked_leaf"] == executor.LOCKED


def test_v3_lineage_requires_the_terminal_to_be_precontact_and_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); public, private = tmp_path / "public", tmp_path / "private"; public.mkdir(); (private / "recovery-attempt").mkdir(parents=True)
    settlement = {"study_id": "hbq-ai-writer-preface-v1-repair-chain-v3"}
    terminal = {"status": "terminal_failure_or_uncertain", "failed_leaf_id": executor.LEAF, "locked": executor.LOCKED, "v2_lineage_is_not_a_vote": True}
    settlement_path, terminal_path = public / "offline-settlement.json", private / "recovery-attempt" / "terminal.json"
    settlement_path.write_text(json.dumps(settlement), encoding="utf-8"); terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    monkeypatch.setattr(executor, "contract", lambda: {"lineage": {"v3_public_settlement_sha256": executor._sha(settlement_path.read_bytes()), "v3_private_failed_terminal_sha256": executor._sha(terminal_path.read_bytes())}})
    monkeypatch.setattr(executor._v3(), "_verify", lambda *_args: (object(), {}))
    _parent, found = executor._verify_v3(public, private, *(tmp_path / name for name in ("ow", "op", "cw", "cp", "v2w", "v2p")))
    assert found["classification"] == "pre_contact_infrastructure_recovery"
    terminal["status"] = "valid_quote_repair"; terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="pre-contact"):
        executor._verify_v3(public, private, *(tmp_path / name for name in ("ow", "op", "cw", "cp", "v2w", "v2p")))


def test_disclosure_is_one_locked_quote_only_sol_subscription_call():
    executor = _executor(); prompt = "LOCKED ORIGINAL: " + json.dumps(executor.LOCKED, sort_keys=True); disclosure = executor._disclosure(prompt)
    assert disclosure["repair_attempt_id"] == executor.ATTEMPT_ID
    assert disclosure["provider"] == {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}
    assert disclosure["locked"] == executor.LOCKED and disclosure["paid_api"] is False and disclosure["human_judgment"] is False


def test_existing_attempt_prevents_another_provider_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); private = tmp_path / "private"; private.mkdir(); executor._atomic(private / executor.PRIVATE_ATTEMPT, {"status": "valid_quote_repair"})
    monkeypatch.setattr(executor, "_verify", lambda *_args: (object(), {}))
    result = executor.execute_one(*(tmp_path / name for name in ("work", "private", "v3w", "v3p", "ow", "op", "cw", "cp", "v2w", "v2p")), allow_remote=True)
    assert result == {"provider_calls": 0, "status": "settled"}


def test_settlement_marks_v3_as_lineage_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private = tmp_path / "work", tmp_path / "private"; work.mkdir(); private.mkdir()
    monkeypatch.setattr(executor, "_verify", lambda *_args: (object(), {"bound": True})); monkeypatch.setattr(executor, "contract", lambda: {"study_id": "hbq-ai-writer-preface-v1-repair-chain-v4"})
    summary = executor.settle_offline(*(path for path in (work, private, tmp_path / "v3w", tmp_path / "v3p", tmp_path / "ow", tmp_path / "op", tmp_path / "cw", tmp_path / "cp", tmp_path / "v2w", tmp_path / "v2p")))
    assert summary["provider_calls"] == 0
    assert summary["v3_lineage"] == {"classification": "pre_contact_infrastructure_recovery", "counts_as_vote": False, "counts_as_repair": False}
    assert summary["recovery"]["attempts"] == 0


def test_actual_sealed_parent_prepares_and_renders_without_contact(tmp_path: Path):
    executor = _executor(); base = Path("C:/Users/Haile/Documents")
    roots = tuple(base / name for name in ("cwr-ai-preface-repair-chain-v3-public-20260822", "cwr-ai-preface-repair-chain-v3-private-20260822", "cwr-ai-preface-pilot-public-20260822", "cwr-ai-preface-pilot-private-20260822", "cwr-ai-preface-continuation-public-20260822", "cwr-ai-preface-continuation-private-20260822", "cwr-ai-preface-repair-chain-public-20260822", "cwr-ai-preface-repair-chain-private-20260822"))
    if not all(path.is_dir() for path in roots): pytest.skip("sealed preface evidence roots unavailable")
    work, private = tmp_path / "public", tmp_path / "private"
    assert executor.prepare(work, private, *roots)["provider_calls"] == 0
    preview = executor.render_next_disclosure(work, private, *roots)
    assert preview["provider_calls"] == 0 and preview["status"] == "pending" and preview["disclosure"]["locked"] == executor.LOCKED
    with pytest.raises(ValueError, match="allow-remote"):
        executor.execute_one(work, private, *roots)
