from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-repair-chain-v5"
PUBLIC_SHA = "abccaeed386bf83521971011f57e9e2e0756adf9b140a365ff52ddc5519288d4"
TERMINAL_SHA = "3f7947f9e1dfb3743d8abd1a672063d007eb2a27dadc03bb1dff78387bb2f53f"


def _executor():
    spec = importlib.util.spec_from_file_location("preface_recovery_v5", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def test_contract_freezes_exact_v4_lineage_and_one_call_cap():
    executor = _executor(); value = executor.contract()
    assert value["study_id"] == "hbq-ai-writer-preface-v1-repair-chain-v5"
    assert value["lineage"] == {"v4_public_settlement_sha256": PUBLIC_SHA, "v4_private_failed_terminal_sha256": TERMINAL_SHA}
    assert value["recovery"]["kind"] == "pre_contact_infrastructure_recovery" and value["recovery"]["max_additional_attempts"] == 1
    assert value["locked_leaf"] == executor.LOCKED


def test_v4_lineage_must_be_a_locked_precontact_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); public, private = tmp_path / "public", tmp_path / "private"; public.mkdir(); (private / "recovery-attempt").mkdir(parents=True)
    settlement = {"study_id": "hbq-ai-writer-preface-v1-repair-chain-v4"}; terminal = {"status": "terminal_failure_or_uncertain", "failed_leaf_id": executor.LEAF, "locked": executor.LOCKED, "v3_lineage_is_not_a_vote": True}
    settlement_path, terminal_path = public / "offline-settlement.json", private / "recovery-attempt" / "terminal.json"; settlement_path.write_text(json.dumps(settlement), encoding="utf-8"); terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    monkeypatch.setattr(executor, "contract", lambda: {"lineage": {"v4_public_settlement_sha256": executor._sha(settlement_path.read_bytes()), "v4_private_failed_terminal_sha256": executor._sha(terminal_path.read_bytes())}})
    monkeypatch.setattr(executor._v4(), "_verify", lambda *_args: (object(), {}))
    _parent, found = executor._verify_v4(public, private, *(tmp_path / name for name in ("v3w", "v3p", "ow", "op", "cw", "cp", "v2w", "v2p")))
    assert found["classification"] == "pre_contact_infrastructure_recovery"
    terminal["status"] = "valid_quote_repair"; terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
    with pytest.raises(ValueError, match="pre-contact"):
        executor._verify_v4(public, private, *(tmp_path / name for name in ("v3w", "v3p", "ow", "op", "cw", "cp", "v2w", "v2p")))


def test_disclosure_is_one_locked_quote_only_subscription_request():
    executor = _executor(); prompt = "LOCKED ORIGINAL: " + json.dumps(executor.LOCKED, sort_keys=True); disclosure = executor._disclosure(prompt)
    assert disclosure["repair_attempt_id"] == executor.ATTEMPT_ID and disclosure["locked"] == executor.LOCKED
    assert disclosure["provider"] == {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}
    assert disclosure["paid_api"] is False and disclosure["human_judgment"] is False


def test_existing_terminal_blocks_second_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); private = tmp_path / "private"; private.mkdir(); executor._atomic(private / executor.PRIVATE_ATTEMPT, {"status": "valid_quote_repair"})
    monkeypatch.setattr(executor, "_verify", lambda *_args: (object(), {}))
    result = executor.execute_one(*(tmp_path / name for name in ("work", "private", "v4w", "v4p", "v3w", "v3p", "ow", "op", "cw", "cp", "v2w", "v2p")), allow_remote=True)
    assert result == {"provider_calls": 0, "status": "settled"}


def test_settlement_marks_v4_as_lineage_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private = tmp_path / "work", tmp_path / "private"; work.mkdir(); private.mkdir()
    monkeypatch.setattr(executor, "_verify", lambda *_args: (object(), {"bound": True})); monkeypatch.setattr(executor, "contract", lambda: {"study_id": "hbq-ai-writer-preface-v1-repair-chain-v5"})
    summary = executor.settle_offline(*(path for path in (work, private, tmp_path / "v4w", tmp_path / "v4p", tmp_path / "v3w", tmp_path / "v3p", tmp_path / "ow", tmp_path / "op", tmp_path / "cw", tmp_path / "cp", tmp_path / "v2w", tmp_path / "v2p")))
    assert summary["provider_calls"] == 0 and summary["recovery"]["attempts"] == 0
    assert summary["v4_lineage"] == {"classification": "pre_contact_infrastructure_recovery", "counts_as_vote": False, "counts_as_repair": False}


def test_actual_v4_parent_prepares_and_renders_without_provider_contact(tmp_path: Path):
    executor = _executor(); base = Path("C:/Users/Haile/Documents")
    roots = tuple(base / name for name in ("cwr-ai-preface-repair-chain-v4-public-20260822", "cwr-ai-preface-repair-chain-v4-private-20260822", "cwr-ai-preface-repair-chain-v3-public-20260822", "cwr-ai-preface-repair-chain-v3-private-20260822", "cwr-ai-preface-pilot-public-20260822", "cwr-ai-preface-pilot-private-20260822", "cwr-ai-preface-continuation-public-20260822", "cwr-ai-preface-continuation-private-20260822", "cwr-ai-preface-repair-chain-public-20260822", "cwr-ai-preface-repair-chain-private-20260822"))
    if not all(path.is_dir() for path in roots): pytest.skip("sealed preface evidence roots unavailable")
    work, private = tmp_path / "public", tmp_path / "private"; assert executor.prepare(work, private, *roots)["provider_calls"] == 0
    preview = executor.render_next_disclosure(work, private, *roots)
    assert preview["provider_calls"] == 0 and preview["status"] == "pending" and preview["disclosure"]["locked"] == executor.LOCKED
    with pytest.raises(ValueError, match="allow-remote"): executor.execute_one(work, private, *roots)
