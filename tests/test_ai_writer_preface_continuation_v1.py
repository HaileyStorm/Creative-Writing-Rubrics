from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-ai-writer-preface-v1-continuation-v1"


def _live_roots() -> tuple[Path, Path]:
    public, private = os.environ.get("CWR_PREFACE_LIVE_PUBLIC_ROOT"), os.environ.get("CWR_PREFACE_LIVE_PRIVATE_ROOT")
    if not public or not private:
        pytest.skip("set CWR_PREFACE_LIVE_PUBLIC_ROOT and CWR_PREFACE_LIVE_PRIVATE_ROOT for sealed-evidence integration")
    return Path(public), Path(private)


def _executor():
    spec = importlib.util.spec_from_file_location("preface_continuation_v1", PACKAGE / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _originals(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    public, private = _live_roots()
    before = {str(path): _sha(path.read_bytes()) for root in (public, private) for path in root.rglob("*") if path.is_file()}
    return public, private, before


def _prepared(executor, tmp_path: Path):
    old_public, old_private, before = _originals(tmp_path)
    work, private = tmp_path / "continuation-public", tmp_path / "continuation-private"
    return old_public, old_private, before, work, private, executor.prepare(work, private, old_public, old_private)


def _assert_originals(tmp_path: Path, before: dict[str, str]) -> None:
    public, private = _live_roots()
    after = {str(path): _sha(path.read_bytes()) for root in (public, private) for path in root.rglob("*") if path.is_file()}
    assert after == before


def test_quote_validation_rejects_whitespace_and_requires_contiguous_normalized_source():
    executor = _executor()
    assert executor._valid_quote("quoted line", "before quoted line after")
    assert not executor._valid_quote("e\u0301", "é")
    assert not executor._valid_quote("quoted line ", "before quoted line")
    assert not executor._valid_quote("\tquoted line", "before quoted line after")
    assert not executor._valid_quote("   \t\n", "source text")
    assert not executor._valid_quote("quoted\nline", "quoted line")


def test_portable_quote_payload_and_exception_provenance_checks():
    executor = _executor()
    locked = {"question_id": "leaf", "verdict": "YES", "confidence": 0.5}
    payload = {"verdicts": [{**locked, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": "verbatim", "summary": None}], "note": "fixture"}]}
    assert executor._quote_repair_payload_valid(payload, {"locked": locked}, "a verbatim source")
    payload["verdicts"][0]["evidence"][0]["exact_quote"] = "  \t"
    assert not executor._quote_repair_payload_valid(payload, {"locked": locked}, "a verbatim source")
    failure = RuntimeError("fixture"); failure.provider_record = {"reported": {"session_id": "known"}}
    assert executor._exception_provider_record(failure) == {"reported": {"session_id": "known"}}


def test_portable_synthetic_evidence_rejects_out_of_order_terminal_and_tracks_failed_session(tmp_path: Path):
    executor = _executor(); work, private, original = tmp_path / "public", tmp_path / "private", tmp_path / "original"
    suffix = [{"sequence": 18}, {"sequence": 19}]
    path = executor._terminal(private, 19); executor._atomic(path, {"format_version": 1, "status": "terminal_failure_or_uncertain", "cell": suffix[1], "session_id_sha256": _sha("failed")})
    executor._append(work / executor.PUBLIC_JOURNAL, {"event": "terminal_failure_or_uncertain", "sequence": 19, "private_terminal_sha256": _sha(path.read_bytes())})
    with pytest.raises(ValueError, match="earlier schedule gap"):
        executor._settled(work, private, suffix)
    (original / "execution-journal.jsonl").parent.mkdir(parents=True)
    (original / "execution-journal.jsonl").write_text("", encoding="utf-8")
    assert _sha("failed") in executor._known_sessions(work, private, original)


def test_prepare_is_zero_call_and_freezes_exact_suffix_without_mutating_originals(tmp_path: Path):
    executor = _executor(); old_public, old_private, before, work, private, result = _prepared(executor, tmp_path)
    assert result == {"provider_calls": 0, "suffix_cells": 7, "scored_cells_remaining": 7, "repair_pending": True}
    assert [row["sequence"] for row in executor._rows(work / executor.PUBLIC_SCHEDULE)] == list(range(18, 25))
    binding = json.loads((work / executor.PUBLIC_BINDING).read_text())
    assert set(binding["original"]["cells_1_17"]) == {f"{number:04d}" for number in range(1, 18)}
    _assert_originals(tmp_path, before)
    altered = json.loads((work / executor.PUBLIC_BINDING).read_text()); altered["study_id"] = "tampered"
    executor._atomic(work / executor.PUBLIC_BINDING, altered)
    with pytest.raises(ValueError, match="drifted"):
        executor.render_next_disclosure(work, private, old_public, old_private)


def test_disclosure_and_capacity_require_explicit_gate_and_never_reuse_parent_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); old_public, old_private, before, work, private, _ = _prepared(executor, tmp_path)
    preview = executor.render_next_disclosure(work, private, old_public, old_private)
    assert preview["provider_calls"] == 0 and preview["disclosure"]["sequence"] == 18
    assert "actual_origin" not in json.dumps(preview["disclosure"])
    with pytest.raises(ValueError, match="allow-remote"):
        executor.run_capacity_preflight(work, private, old_public, old_private)
    parent = executor._parent()
    calls = {"count": 0}
    def fake_call(**_kwargs):
        calls["count"] += 1
        return '{"ready":true}', {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "new-capacity-session"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", fake_call)
    assert executor.run_capacity_preflight(work, private, old_public, old_private, allow_remote=True)["sequence"] == 18
    assert calls["count"] == 1
    assert executor._capacity(work, private, 18)["status"] == "ready"
    _assert_originals(tmp_path, before)


def test_suffix_attempt_is_one_per_cell_and_later_failure_advances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); old_public, old_private, _before, work, private, _ = _prepared(executor, tmp_path)
    parent = executor._parent()
    calls = {"count": 0}
    def fake_call(**kwargs):
        calls["count"] += 1
        if "capacity preflight" in kwargs["prompt"]: return '{"ready":true}', {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"capacity-{calls['count']}"}}
        error = RuntimeError("fixture structural failure")
        error.provider_record = {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "failed-scored-session"}}
        raise error
    monkeypatch.setattr(parent._runner(), "_call_codex", fake_call)
    executor.run_capacity_preflight(work, private, old_public, old_private, allow_remote=True)
    failed = executor.execute_one(work, private, old_public, old_private, allow_remote=True)
    assert failed["status"] == "terminal_failure_or_uncertain" and failed["sequence"] == 18
    assert json.loads(executor._terminal(private, 18).read_text())["session_id_sha256"] == _sha("failed-scored-session")
    assert _sha("failed-scored-session") in executor._known_sessions(work, private, old_public)
    assert executor.render_next_disclosure(work, private, old_public, old_private)["disclosure"]["sequence"] == 19
    with pytest.raises(ValueError, match="capacity-preflight"):
        executor.execute_one(work, private, old_public, old_private, allow_remote=True)


def test_repair_only_targets_failed_leaf_with_locked_fields_and_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); old_public, old_private, before, work, private, _ = _prepared(executor, tmp_path)
    parent = executor._parent(); prompt, metadata = executor._repair_prompt(parent, old_private, full_regrade=False)
    assert metadata["failed_leaf_id"] == "craft.narrative.characterization.contradiction"
    assert json.dumps(metadata["locked"], sort_keys=True) in prompt
    preview = executor.render_repair_disclosure(work, private, old_public, old_private)
    assert preview["disclosure"]["repair_kind"] == "quote_only"
    def fake_call(**_kwargs):
        locked = metadata["locked"]
        quote = executor._repair_text(parent, old_private).strip().split()[0]
        response = {"verdicts": [{**locked, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote, "summary": None}], "note": "fixture"}]}
        return json.dumps(response), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "repair-quote-session"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", fake_call)
    result = executor.repair_cell17(work, private, old_public, old_private, allow_remote=True)
    assert result["status"] == "valid_quote_repair"
    terminal = json.loads((private / executor.PRIVATE_REPAIRS / "quote-only" / "terminal.json").read_text())
    assert terminal["logical_sample_id"] == "preface-cell-0017" and terminal["locked"] == metadata["locked"]
    with pytest.raises(ValueError, match="bounded"):
        executor.repair_cell17(work, private, old_public, old_private, allow_remote=True)
    _assert_originals(tmp_path, before)


def test_invalid_quote_allows_one_fresh_unanchored_full_fallback_and_rejects_schedule_gaps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); old_public, old_private, _before, work, private, _ = _prepared(executor, tmp_path)
    parent = executor._parent(); quote_prompt, metadata = executor._repair_prompt(parent, old_private, full_regrade=False)
    full_prompt, _ = executor._repair_prompt(parent, old_private, full_regrade=True)
    assert "LOCKED ORIGINAL:" in quote_prompt and "LOCKED ORIGINAL:" not in full_prompt
    def invalid_quote(**_kwargs):
        locked = metadata["locked"]
        response = {"verdicts": [{**locked, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": " \t", "summary": None}], "note": "fixture"}]}
        return json.dumps(response), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "invalid-quote-session"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", invalid_quote)
    assert executor.repair_cell17(work, private, old_public, old_private, allow_remote=True)["status"] == "invalid_quote_repair"
    full_disclosure = executor.render_repair_disclosure(work, private, old_public, old_private, full_regrade=True)["disclosure"]
    assert full_disclosure["repair_kind"] == "full_single_leaf_regrade" and "no locked original" in full_disclosure["outbound_content"]
    def full_regrade(**_kwargs):
        quote = executor._repair_text(parent, old_private).strip().split()[0]
        response = {"verdicts": [{"question_id": metadata["failed_leaf_id"], "verdict": "NO", "confidence": 0.5, "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote, "summary": None}], "note": "fresh fixture regrade"}]}
        return json.dumps(response), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "full-regrade-session"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", full_regrade)
    assert executor.repair_cell17(work, private, old_public, old_private, allow_remote=True, full_regrade=True)["status"] == "valid_full_single_leaf_regrade"
    with pytest.raises(ValueError, match="immutable"):
        executor.repair_cell17(work, private, old_public, old_private, allow_remote=True, full_regrade=True)
    suffix = executor._rows(work / executor.PUBLIC_SCHEDULE)
    cell = suffix[1]; terminal = {"format_version": 1, "status": "terminal_failure_or_uncertain", "cell": cell}
    path = executor._terminal(private, cell["sequence"]); executor._atomic(path, terminal)
    executor._append(work / executor.PUBLIC_JOURNAL, {"event": "terminal_failure_or_uncertain", "sequence": cell["sequence"], "private_terminal_sha256": _sha(path.read_bytes())})
    with pytest.raises(ValueError, match="earlier schedule gap"):
        executor.render_next_disclosure(work, private, old_public, old_private)


def test_canonically_malformed_quote_repair_is_invalid_and_unblocks_full_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    executor = _executor(); old_public, old_private, _before, work, private, _ = _prepared(executor, tmp_path)
    parent = executor._parent(); _prompt, metadata = executor._repair_prompt(parent, old_private, full_regrade=False)
    def malformed_quote(**_kwargs):
        quote = executor._repair_text(parent, old_private).strip().split()[0]
        response = {"verdicts": [{**metadata["locked"], "evidence": [{"kind": "exact_quote", "reference": "artifact", "exact_quote": quote, "summary": None}]}]}
        return json.dumps(response), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "malformed-quote-session"}}
    monkeypatch.setattr(parent._runner(), "_call_codex", malformed_quote)
    assert executor.repair_cell17(work, private, old_public, old_private, allow_remote=True)["status"] == "invalid_quote_repair"
    assert executor.render_repair_disclosure(work, private, old_public, old_private, full_regrade=True)["disclosure"]["repair_kind"] == "full_single_leaf_regrade"


def test_settlement_reports_23_original_units_and_separate_repair_sensitivity(tmp_path: Path):
    executor = _executor(); old_public, old_private, _before, work, private, _ = _prepared(executor, tmp_path)
    suffix = executor._rows(work / executor.PUBLIC_SCHEDULE)
    for cell in suffix:
        terminal = {"format_version": 1, "status": "completed", "cell": cell}
        path = executor._terminal(private, cell["sequence"]); executor._atomic(path, terminal)
        executor._append(work / executor.PUBLIC_JOURNAL, {"event": "completed", "sequence": cell["sequence"], "private_terminal_sha256": _sha(path.read_bytes())})
    summary = executor.settle_offline(work, private, old_public, old_private)
    assert summary["primary_analysis"]["original_expected_cells"] == 23
    assert summary["primary_analysis"]["original_valid_cells"] == 23
    assert summary["primary_analysis"]["missing_original_cell"] == 17
    assert summary["primary_analysis"]["valid_cells_by_arm"] == {"none": 8, "current_full": 8, "strictness_only": 7}
    assert summary["primary_analysis"]["intact_repeatability_units"] == 11
    assert summary["repair_sensitivity"]["separate_from_primary"] is True
