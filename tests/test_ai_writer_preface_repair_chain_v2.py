from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-repair-chain-v2"


def _roots() -> tuple[Path, Path, Path, Path]:
    names = ("CWR_PREFACE_LIVE_PUBLIC_ROOT", "CWR_PREFACE_LIVE_PRIVATE_ROOT", "CWR_PREFACE_CONTINUATION_PUBLIC_ROOT", "CWR_PREFACE_CONTINUATION_PRIVATE_ROOT")
    values = [os.environ.get(name) for name in names]
    if not all(values):
        pytest.skip("set the four CWR_PREFACE_*_ROOT variables for sealed-evidence integration")
    return tuple(Path(str(value)) for value in values)  # type: ignore[return-value]


def _executor():
    spec = importlib.util.spec_from_file_location("preface_repair_chain_v2", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _prepared(executor, tmp_path: Path):
    original_work, original_private, continuation_work, continuation_private = _roots()
    work, private = tmp_path / "repair-public", tmp_path / "repair-private"
    executor.prepare(work, private, original_work, original_private, continuation_work, continuation_private)
    return work, private, original_work, original_private, continuation_work, continuation_private


def _valid_response(executor, parent, original_private: Path, leaf: str, *, session: str) -> tuple[str, dict[str, object]]:
    _prompt, metadata = _fast_repair_prompt(executor, parent, original_private, leaf)
    quote = executor._source_text(metadata["item"]).strip().split()[0]
    payload = {"verdicts": [{**metadata["locked"], "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote, "summary": None}], "note": "fixture"}]}
    return json.dumps(payload), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": session}}


def _fast_repair_prompt(executor, parent, original_private: Path, leaf: str):
    cell, item, rows = executor._original_cell(parent, original_private)
    source = next(row for row in rows if row["question_id"] == leaf)
    locked = {"question_id": leaf, "verdict": source["verdict"], "confidence": source["confidence"]}
    return "LOCKED ORIGINAL: " + json.dumps(locked, sort_keys=True), {"cell": cell, "item": item, "locked": locked, "logical_sample_id": "preface-cell-0017", "failed_leaf_id": leaf}


def test_offline_prepare_disclosure_and_settlement_never_call_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path)
    parent, _ = executor._verify(work, private, original_work, original_private, continuation_work, continuation_private)
    monkeypatch.setattr(executor, "_repair_prompt", lambda parent, original_private, leaf: _fast_repair_prompt(executor, parent, original_private, leaf))
    monkeypatch.setattr(parent._runner(), "_call_codex", lambda **_kwargs: pytest.fail("offline operation called provider"))
    preview = executor.render_next_disclosure(work, private, original_work, original_private, continuation_work, continuation_private)
    assert preview["provider_calls"] == 0
    assert preview["disclosure"]["failed_leaf_id"] == "craft.narrative.point_of_view_and_focalization.distance"
    settlement = executor.settle_offline(work, private, original_work, original_private, continuation_work, continuation_private)
    assert settlement["provider_calls"] == 0
    assert settlement["repair_sensitivity"]["status"] == "pending"
    assert settlement["primary_analysis"]["original_valid_cells"] == 22
    assert settlement["primary_analysis"]["original_expected_cells"] == 23
    assert settlement["primary_analysis"]["missing_original_cell"] == 17
    with pytest.raises(ValueError, match="allow-remote"):
        executor.execute_one(work, private, original_work, original_private, continuation_work, continuation_private)


def test_tampered_parent_or_binding_is_rejected(tmp_path: Path):
    executor = _executor(); work, private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path)
    binding = json.loads((work / executor.PUBLIC_BINDING).read_text(encoding="utf-8")); binding["study_id"] = "tampered"
    executor._atomic(work / executor.PUBLIC_BINDING, binding)
    with pytest.raises(ValueError, match="binding drifted"):
        executor.render_next_disclosure(work, private, original_work, original_private, continuation_work, continuation_private)


def test_valid_quote_repair_is_locked_and_the_three_attempt_cap_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path)
    parent, _ = executor._verify(work, private, original_work, original_private, continuation_work, continuation_private)
    monkeypatch.setattr(executor, "_repair_prompt", lambda parent, original_private, leaf: _fast_repair_prompt(executor, parent, original_private, leaf))
    sent: list[str] = []
    def fake_call(**kwargs):
        prompt = str(kwargs["prompt"])
        locked_line = next(line for line in prompt.splitlines() if line.startswith("LOCKED ORIGINAL: "))
        locked = json.loads(locked_line.split(": ", 1)[1]); sent.append(locked["question_id"])
        return _valid_response(executor, parent, original_private, locked["question_id"], session=f"chain-session-{len(sent)}")
    monkeypatch.setattr(parent._runner(), "_call_codex", fake_call)
    result = executor.execute_one(work, private, original_work, original_private, continuation_work, continuation_private, allow_remote=True)
    assert result["provider_calls"] == 1
    assert result["status"] == "valid_quote_repair"
    assert result["repair_attempt_id"] == "cell17-quote-repair-chain-v2-01"
    assert result["combined_status"] == "pending"
    assert sent == ["craft.narrative.point_of_view_and_focalization.distance"]
    accepted, terminals = executor._prior_repairs(parent, original_private, continuation_private, work, private)
    assert sent[0] in accepted and len(terminals) == 2
    successor = executor.render_next_disclosure(work, private, original_work, original_private, continuation_work, continuation_private)
    assert successor["status"] == "pending"
    assert successor["disclosure"]["failed_leaf_id"] != sent[0]

    capped_work, capped_private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path / "capped")
    attempts = {"count": 0}
    def invalid_quote(**kwargs):
        attempts["count"] += 1
        locked = json.loads(next(line for line in str(kwargs["prompt"]).splitlines() if line.startswith("LOCKED ORIGINAL: ")).split(": ", 1)[1])
        payload = {"verdicts": [{**locked, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": "not a literal source quote", "summary": None}], "note": "fixture"}]}
        return json.dumps(payload), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"invalid-session-{attempts['count']}"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", invalid_quote)
    for _ in range(3):
        assert executor.execute_one(capped_work, capped_private, original_work, original_private, continuation_work, continuation_private, allow_remote=True)["status"] == "invalid_quote_repair"
    capped = executor.render_next_disclosure(capped_work, capped_private, original_work, original_private, continuation_work, continuation_private)
    assert capped["status"] == "unavailable"
    assert capped["repair_state"]["reason"] == "quote_repair_cap_exhausted"


def test_unjournaled_terminal_and_exclusive_claim_cannot_advance_or_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path)
    parent, _ = executor._verify(work, private, original_work, original_private, continuation_work, continuation_private)
    monkeypatch.setattr(executor, "_repair_prompt", lambda parent, original_private, leaf: _fast_repair_prompt(executor, parent, original_private, leaf))
    executor._atomic(private / executor.PRIVATE_ATTEMPTS / "01" / "terminal.json", {"format_version": 1, "status": "valid_quote_repair", "repair_attempt_id": "cell17-quote-repair-chain-v2-01"})
    with pytest.raises(ValueError, match="identity|evidence"):
        executor.render_next_disclosure(work, private, original_work, original_private, continuation_work, continuation_private)

    claimed_work, claimed_private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path / "claimed")
    executor._claim(claimed_work)
    monkeypatch.setattr(parent._runner(), "_call_codex", lambda **_kwargs: pytest.fail("second caller contacted provider"))
    with pytest.raises(ValueError, match="Exclusive repair claim"):
        executor.execute_one(claimed_work, claimed_private, original_work, original_private, continuation_work, continuation_private, allow_remote=True)

    work2, private2, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path / "uncertain")
    def uncertain(**_kwargs):
        error = RuntimeError("fixture transport uncertainty")
        error.provider_record = {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "uncertain-session"}}
        error.content = '{"partial":"provider bytes"}'
        raise error
    monkeypatch.setattr(parent._runner(), "_call_codex", uncertain)
    result = executor.execute_one(work2, private2, original_work, original_private, continuation_work, continuation_private, allow_remote=True)
    assert result["status"] == "terminal_failure_or_uncertain"
    terminal = json.loads((private2 / executor.PRIVATE_ATTEMPTS / "01" / "terminal.json").read_text(encoding="utf-8"))
    assert terminal["response"] == '{"partial":"provider bytes"}'
    assert terminal["response_sha256"] == _sha(terminal["response"])
    assert terminal["response_provenance"] == "provider_attempt_failure_content"
    assert executor.render_next_disclosure(work2, private2, original_work, original_private, continuation_work, continuation_private)["status"] == "unavailable"

    work3, private3, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path / "nonquote")
    def nonquote(**kwargs):
        locked = json.loads(next(line for line in str(kwargs["prompt"]).splitlines() if line.startswith("LOCKED ORIGINAL: ")).split(": ", 1)[1])
        payload = {"verdicts": [{**locked, "evidence": [{"kind": "summary", "reference": "artifact", "exact_quote": None, "summary": "fixture"}], "note": "fixture"}]}
        return json.dumps(payload), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "nonquote-session"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", nonquote)
    result = executor.execute_one(work3, private3, original_work, original_private, continuation_work, continuation_private, allow_remote=True)
    assert result["status"] == "non_quote_repair_failure" and result["combined_status"] == "unavailable"
    assert executor.render_next_disclosure(work3, private3, original_work, original_private, continuation_work, continuation_private)["status"] == "unavailable"


def test_duplicate_verified_leaf_is_rejected_before_combined_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path)
    parent, _ = executor._verify(work, private, original_work, original_private, continuation_work, continuation_private)
    leaf = "craft.narrative.point_of_view_and_focalization.distance"
    response, _record = _valid_response(executor, parent, original_private, leaf, session="duplicate-session")
    duplicate = {"status": "valid_quote_repair", "failed_leaf_id": leaf, "response": response}
    for attempt in range(1, 3):
        executor._atomic(private / executor.PRIVATE_ATTEMPTS / f"{attempt:02d}" / "terminal.json", {"format_version": 1})
    monkeypatch.setattr(executor, "_verify_attempt", lambda *_args: duplicate)
    with pytest.raises(ValueError, match="duplicates"):
        executor._prior_repairs(parent, original_private, continuation_private, work, private)


def test_tampered_public_disclosure_or_journal_cannot_advance_a_repair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); work, private, original_work, original_private, continuation_work, continuation_private = _prepared(executor, tmp_path)
    parent, _ = executor._verify(work, private, original_work, original_private, continuation_work, continuation_private)
    monkeypatch.setattr(executor, "_repair_prompt", lambda parent, original_private, leaf: _fast_repair_prompt(executor, parent, original_private, leaf))
    monkeypatch.setattr(parent._runner(), "_call_codex", lambda **kwargs: _valid_response(executor, parent, original_private, json.loads(next(line for line in str(kwargs["prompt"]).splitlines() if line.startswith("LOCKED ORIGINAL: ")).split(": ", 1)[1])["question_id"], session="tamper-session"))
    assert executor.execute_one(work, private, original_work, original_private, continuation_work, continuation_private, allow_remote=True)["status"] == "valid_quote_repair"
    rows = executor._rows(work / executor.PUBLIC_JOURNAL); rows[-1]["private_terminal_sha256"] = "0" * 64
    (work / executor.PUBLIC_JOURNAL).write_bytes(b"".join(executor._canonical(row) + b"\n" for row in rows))
    with pytest.raises(ValueError, match="journal evidence"):
        executor.render_next_disclosure(work, private, original_work, original_private, continuation_work, continuation_private)
