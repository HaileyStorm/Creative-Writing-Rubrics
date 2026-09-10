from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1" / "sol_selected_collection_replay.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("dryad_selected_collection_replay_test", MODULE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def normalized(question_id: str, verdict: str = "YES") -> dict[str, Any]:
    return {"artifact_id": "artifact", "bundle_id": "prose.short_story", "confidence": .9, "evidence": [],
            "judge_id": "codex:gpt-5.6-sol", "note": "fixture", "question_id": question_id,
            "run_id": "run", "verdict": verdict}


def test_schedule_preserves_selected_order_and_rejects_gap_or_reorder() -> None:
    value = load()
    assert value._selected({"selected_request_ordinals": value.SELECTED}) == value.SELECTED
    with pytest.raises(ValueError, match="selected schedule order"):
        value._selected({"selected_request_ordinals": value.SELECTED[:-1]})
    changed = value.SELECTED.copy(); changed[1609], changed[1610] = changed[1610], changed[1609]
    with pytest.raises(ValueError, match="selected schedule order"):
        value._selected({"selected_request_ordinals": changed})


def test_remaining_controller_and_precontact_recovery_are_pinned() -> None:
    value = load()
    assert value.REMAINING_CONTROLLER_SHA256 == "244c8b02e313b19bad75de3dc26156af8c9af1eab14cd1af5679c6f13273c155"
    assert value.PRECONTACT_RECOVERY_SHA256 == "9e9e8fd23c00c4c7e4b1cf66e435543ff9a8a8fdfc2552b045510e12165f9345"


def test_original_normalization_projects_only_verdict_identity_and_rejects_gaps_duplicates() -> None:
    value = load()
    request = {"question_ids": ["q-1", "q-2"]}
    assert value._project({"normalized_verdicts": [normalized("q-1"), normalized("q-2", "NO")]}, request, original=True) == [
        {"question_id": "q-1", "verdict": "YES"}, {"question_id": "q-2", "verdict": "NO"}]
    with pytest.raises(ValueError, match="verdict identities"):
        value._project({"normalized_verdicts": [normalized("q-1"), normalized("q-1")]}, request, original=True)
    with pytest.raises(ValueError, match="normalized verdict record"):
        value._project({"normalized_verdicts": [{"question_id": "q-1", "verdict": "YES"}]}, request, original=True)


def test_phase_classes_preserve_unknown_exit_and_owner_replacements() -> None:
    value = load()
    assert value._phase(1) == "original_native_checkpoint"
    assert value._phase(773) == "owner_authorized_773_replacement"
    assert value._phase(1328) == "unknown_exit_retained_message"
    assert value._phase(1343) == "selected_native_completion"
    assert value._phase(4295) == "owner_authorized_transport_replacement"
    assert value._phase(4306) == "selected_native_completion"
    assert value._phase(4486) == "completed_with_unknown_exit_retained_message"
    assert value._phase(4507, "completed_with_unknown_exit") == "completed_with_unknown_exit_retained_message"


def test_response_path_preserves_parent_and_remaining_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); old = tmp_path / "old"
    monkeypatch.setattr(value, "OLD_SELECTED_ROOT", old)
    remaining, parent = tmp_path / "remaining", tmp_path / "parent"
    request = {"batch_number": 1}; pass_record = {"run_path": "ignored"}
    for ordinal in (4295, 4297, 4306, 4485, 4493, 4506):
        assert value._response_path(remaining, parent, {**request, "ordinal": ordinal}, pass_record, {}) == parent / "requests" / f"{ordinal:04d}" / "response.json"
    for ordinal in (1343, 1610, 4049, 4294, 4296):
        assert value._response_path(remaining, parent, {**request, "ordinal": ordinal}, pass_record, {}) == old / "requests" / f"{ordinal:04d}" / "response.json"
    assert value._response_path(remaining, parent, {**request, "ordinal": 4507}, pass_record, {}) == remaining / "requests" / "4507" / "response.json"


def test_response_path_uses_retained_unknown_exit_message_commitment(tmp_path: Path) -> None:
    value = load()
    for ordinal in (4486, 4492):
        message = tmp_path / "parent" / "requests" / f"{ordinal:04d}" / "native-output" / "responses" / "batch-0013.attempt-0001.message.json"
        record = {"native_files": {"message": {"path": str(message)}}}
        path = value._response_path(tmp_path / "remaining", tmp_path / "parent", {"ordinal": ordinal, "batch_number": 13}, {"run_path": "ignored"}, {ordinal: record})
        assert path == message


def test_future_unknown_exit_commitment_keeps_unproven_process_state(tmp_path: Path) -> None:
    value = load(); ordinal = 4507; response = b'{"verdicts":[]}'
    slot = tmp_path / "requests" / f"{ordinal:04d}"; slot.mkdir(parents=True)
    (slot / "terminal.json").write_text(json.dumps({"state": "completed_with_unknown_exit", "response_sha256": hashlib.sha256(response).hexdigest()}), encoding="utf-8")
    (slot / "provider-record.json").write_text(json.dumps({"completion_class": "completed_with_unknown_exit", "process_success_proven": False}), encoding="utf-8")
    assert value._completion_provenance(tmp_path, ordinal, response, {}) == ("completed_with_unknown_exit", False)


def test_low_coverage_is_carried_as_qualification_failure_without_filtering() -> None:
    value = load()
    rows = [{"pass_id": "pass-19", "coverage": .8607}, {"pass_id": "pass-42", "coverage": .8648},
            {"pass_id": "pass-43", "coverage": .88}]
    assert value._qualification_failures(rows) == [
        {"pass_id": "pass-19", "coverage": .8607, "reason": "coverage_below_0.88"},
        {"pass_id": "pass-42", "coverage": .8648, "reason": "coverage_below_0.88"}]


def test_preflight_rejects_live_lock_before_reading_result(tmp_path: Path) -> None:
    value = load()
    raw = MODULE.read_bytes(); (tmp_path / ".collect.lock").write_bytes(b"live")
    (tmp_path / "campaign-manifest.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="collection lock"):
        value._preflight(tmp_path, hashlib.sha256(b"{}").hexdigest(), "0" * 64, hashlib.sha256(raw).hexdigest())


def test_preflight_rejects_incomplete_result_before_context(tmp_path: Path) -> None:
    value = load(); manifest = b"{}"
    result = json.dumps({"state": "stopped_no_retry", "logical_collection_count": 1857, "logical_collection_target": 2300,
                         "failures": [{"ordinal": 4295}], "full_study_admitted": False}).encode()
    (tmp_path / "campaign-manifest.json").write_bytes(manifest); (tmp_path / "collection-result.json").write_bytes(result)
    with pytest.raises(ValueError, match="not finished"):
        value._preflight(tmp_path, hashlib.sha256(manifest).hexdigest(), hashlib.sha256(result).hexdigest(), hashlib.sha256(MODULE.read_bytes()).hexdigest())


def test_public_replay_accepts_only_remaining_terminal_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    manifest = json.dumps({"evidence_class": "selected100_sol_remaining_collection_with_completed_unknown_exit_recognition_v1",
                           "parent_campaign_root": str(tmp_path / "parent")}).encode()
    result = json.dumps({"state": "collected", "recognized_logical_requests": 2300, "logical_collection_target": 2300,
                         "failures": [], "full_study_admitted": False}).encode()
    (tmp_path / "campaign-manifest.json").write_bytes(manifest); (tmp_path / "collection-result.json").write_bytes(result)
    recoveries = [{"ordinal": ordinal} for ordinal in value.REMAINING_UNKNOWN_EXIT]
    monkeypatch.setattr(value, "_remaining_context", lambda *_args: (object(), object(), object(), object(), object(), {"recoveries": recoveries},
                                                                       set(), {"selected_request_ordinals": value.SELECTED}, {"requests": []}))
    monkeypatch.setattr(value, "_validate_remaining", lambda *_args: {"thread"})
    rows = [{"pass_id": "pass-19", "coverage": .8607, "canonical_verdicts": [{}] * 178,
             "request_commitments": [{"process_success_proven": False}]}]
    monkeypatch.setattr(value, "_rows", lambda *_args: (rows, value._qualification_failures(rows)))
    replay = value.replay_collected(campaign_root=tmp_path, expected_campaign_manifest_sha256=hashlib.sha256(manifest).hexdigest(),
                                    expected_collection_result_sha256=hashlib.sha256(result).hexdigest(),
                                    expected_composer_sha256=hashlib.sha256(MODULE.read_bytes()).hexdigest())
    assert replay["accepted_native_thread_ids"] == ["thread"] and replay["full_study_admitted"] is False
    assert replay["unknown_exit_commitments"] == [{"process_success_proven": False}]


def test_remaining_inventory_requires_all_232_slots_and_keeps_unknown_exit_available(tmp_path: Path) -> None:
    value = load(); plan = {"requests": [{"ordinal": ordinal} for ordinal in range(1, 5429)]}

    class Remaining:
        REMAINING = tuple(range(4507, 4739))

        @staticmethod
        def _sha(raw: bytes) -> str:
            return hashlib.sha256(raw).hexdigest()

        @staticmethod
        def _canonical(item: Any) -> bytes:
            return json.dumps(item, sort_keys=True).encode()

        @staticmethod
        def _validate_existing(_root: Path, request: dict[str, int], threads: set[str], **kwargs: Any) -> bool:
            assert kwargs["old"] is old
            thread = f"remaining-{request['ordinal']}"; assert thread not in threads; threads.add(thread); return True

    threads = {f"prefix-{ordinal}" for ordinal in range(1, 2069)}
    old = object()
    assert len(value._validate_remaining(tmp_path, Remaining, old, object(), object(), {}, threads, plan)) == 2300
