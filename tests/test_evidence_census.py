"""Behavioral boundaries for the provider-free retained evidence projection."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / "evaluation-results/hbq-evidence-census-pass-a-v1/census.py"
SPEC = importlib.util.spec_from_file_location("evidence_census", MODULE)
assert SPEC is not None and SPEC.loader is not None
census = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(census)


def _source(kind: str = "replay") -> dict:
    return {"id": "native", "cohort": "fixture", "kind": kind,
            "endpoint": "sol", "plan_id": "plan", "path": "native.json"}


def _packet(ordinal: int, identity: str) -> dict:
    return {"ordinal": ordinal, "state": "accepted", "verdict_count": 1,
            "native_identity": {"thread_id": identity}, "normalized_verdicts_sha256": "a" * 64}


def test_duplicate_replay_does_not_merge_independent_same_content_repeat() -> None:
    slots: list = []
    plan = {"requests": [
        {"ordinal": 1, "logical_sample_id": "first-pass"},
        {"ordinal": 2, "logical_sample_id": "planned-repeat"}]}
    replay = {"records": [_packet(1, "thread-first"), _packet(1, "thread-first"),
                           _packet(2, "thread-repeat")]}
    result = census.replay_projection(replay, _source(), plan, slots)
    assert result["observed"]["accepted_packet_verdicts"] == 2
    assert result["observed"]["slot_dispositions"] == {"accepted": 2}
    assert slots[0]["replayed_duplicate_records"] == 1
    assert slots[0]["slot_sha256"] != slots[1]["slot_sha256"]
    assert result["observed"]["unique_native_identities"] == 2


def test_missing_native_leaf_stays_missing_despite_derived_prediction(tmp_path: Path) -> None:
    plan = {"requests": [{"ordinal": 1, "logical_sample_id": "first"},
                         {"ordinal": 2, "logical_sample_id": "second"}]}
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    replay = {"plan_sha256": census.hashlib.sha256((tmp_path / "plan.json").read_bytes()).hexdigest(),
              "accepted_verdict_count": 1, "records": [_packet(1, "thread")],
              "score_ready_verdict_rows": [{"verdicts": [{"question_id": "q1", "verdict": "YES"}]}],
              "unresolved_ordinals": [2], "declared_nonresponses": [
                  {"ordinal": 2, "missing_verdict_count": 1}]}
    (tmp_path / "native.json").write_text(json.dumps(replay), encoding="utf-8")
    (tmp_path / "prediction.json").write_text(json.dumps({
        "native_verdict_count_by_endpoint": {"sol": 1},
        "predictions": [{"question_id": "q2", "verdict": "CANNOT_ASSESS"}]}), encoding="utf-8")
    descriptor = {"sources": [
        {"id": "plan", "cohort": "fixture", "kind": "plan", "path": "plan.json"},
        _source(), {"id": "prediction", "cohort": "fixture", "kind": "derived_prediction",
                    "path": "prediction.json"}], "remaining_joins": []}
    report, slots = census.build_census(tmp_path, descriptor)
    assert report["totals"]["observed_ttcw_pron_dryad_native_verdict_rows"] == 1
    assert report["totals"]["retained_declared_ttcw_pron_dryad_native_verdicts"] == 1
    missing = next(row for row in slots if row["kind"] == "native_packet" and row["ordinal"] == 2)
    assert missing["disposition"] == "declared_nonresponse"
    assert missing["no_resend"] is True
    assert missing["missing_question_count"] == 1
    assert report["sources"][-1]["new_native_votes"] == 0


def test_absent_source_is_not_reported_as_zero_evidence(tmp_path: Path) -> None:
    report, slots = census.build_census(tmp_path, {"sources": [_source()], "remaining_joins": []})
    assert report["sources"][0]["disposition"] == "absent"
    assert "observed" not in report["sources"][0]
    assert "declared" not in report["sources"][0]
    assert slots == []
    assert report["status"] == "partial_census"


def test_conflicting_accepted_identity_is_unresolved_and_not_an_extra_vote() -> None:
    slots: list = []
    result = census.replay_projection({"records": [_packet(1, "first"), _packet(1, "second")]},
                                     _source(), {"requests": [{"ordinal": 1}]}, slots)
    assert result["observed"]["accepted_packet_verdicts"] == 0
    assert slots[0]["disposition"] == "unresolved_identity_conflict"
    assert slots[0]["no_resend"] is True


def test_retained_local_repair_preserves_one_original_vote() -> None:
    packet = _packet(1, "original-thread")
    packet["state"] = "accepted_local_projection"
    slots: list = []
    result = census.replay_projection({"records": [packet, packet]}, _source(),
                                     {"requests": [{"ordinal": 1}]}, slots)
    assert result["observed"]["accepted_packet_verdicts"] == 1
    assert result["observed"]["slot_dispositions"] == {"repaired": 1}
    assert slots[0]["replayed_duplicate_records"] == 1


def test_exports_omit_private_fields_and_refuse_overwrite(tmp_path: Path) -> None:
    control = tmp_path / "control"
    control.mkdir()
    (control / "native.json").write_text(json.dumps({"records": [_packet(1, "secret-thread")],
        "prose": "private-prose", "preferences": "private-label", "account": "private-account"}), encoding="utf-8")
    descriptor = {"sources": [_source()], "remaining_joins": []}
    output = tmp_path / "output"
    census.write_census(control, output, descriptor)
    before = {p.name: p.read_bytes() for p in output.iterdir()}
    for content in before.values():
        for private in (b"secret-thread", b"private-prose", b"private-label", b"private-account"):
            assert private not in content
    with pytest.raises(FileExistsError):
        census.write_census(control, output, descriptor)
    assert before == {p.name: p.read_bytes() for p in output.iterdir()}


def test_lamp_ambiguous_receipt_remains_reserved_without_vote_inference() -> None:
    slots: list = []
    result = census.lamp_projection({"native_receipts": {"sol": {"accepted": 71, "planned": 72,
        "nonaccepted": [{"ordinal": 21, "state": "unknown_exit_requires_reconciliation"}]}}},
        {"id": "repeat", "kind": "lamp_repeat"}, slots)
    assert result["endpoint_receipts"]["sol"]["declared"] == {"accepted": 71, "planned": 72}
    assert slots[0]["no_resend"] is True
    assert slots[0]["disposition"] == "unresolved_reserved"
    assert "accepted_packet_verdicts" not in result["observed"]
