from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8"
V7 = Path(r"C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v7-live-1a2d48d")
CLOSED = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff")
SOURCE = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")


def module():
    spec = importlib.util.spec_from_file_location("multisample_successor_v8_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_contract_reuses_v7_policy_and_exact_schedule():
    value = module()
    assert value.contract()["schedule"] == {
        "count": 149,
        "first_sequence": 182,
        "last_sequence": 330,
        "source_full_schedule_sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086",
        "sha256": "98fc94c7cd75bbea4f913a144871f31a0ea743695611f797fb86ca7e2e977bd7",
    }
    assert value.contract()["cohort_compatibility_policy"] == {
        "path": "evaluation-results/hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v7/cohort-compatibility-policy.json",
        "sha256": value.EXPECTED_COHORT_POLICY,
    }
    assert value.sha(value.COHORT_POLICY) == value.EXPECTED_COHORT_POLICY


@pytest.mark.skipif(not CLOSED.exists(), reason="closed schedule evidence is host-local")
def test_fresh_schedule_is_canonical_182_330_suffix():
    value = module()
    schedule = value._fresh_schedule(CLOSED)
    assert [row["sequence"] for row in schedule] == list(range(182, 331))
    assert hashlib.sha256(value.canonical(schedule)).hexdigest() == value.contract()["schedule"]["sha256"]


@pytest.mark.skipif(not V7.exists(), reason="V7 evidence is host-local")
def test_adoption_recomputes_v7_manifest_and_preserves_v7_bytes():
    value = module()
    targets = [
        V7 / "v7-binding.json", V7 / value.SCHEDULE, V7 / value.JOURNAL,
        V7 / value.CLAIM, V7 / value.DISCLOSURE, V7 / value.DISCLOSURE_ACK,
        V7 / value.PROOFS / f"{value.EXPECTED_V7_CAPACITY_PROOF}.json",
    ]
    before = {path: value.sha(path) for path in targets}
    admission = value.admit_v7_prefix(SOURCE, CLOSED, V7)
    assert admission["sequence"] == 182
    assert admission["logical_completed_sequences"] == [179, 180, 182]
    assert admission["zero_contact_sequence"] == 181
    assert admission["session_bearing"] == [{
        "sequence": 182, "session_id": value.EXPECTED_V7_SESSION,
        "recorded_provider_contacts": 1, "output_tree_sha256": value.EXPECTED_V7_OUTPUT_TREE,
    }]
    assert admission["session_registry"]["count"] == 336
    assert [(row["label"], row["count"]) for row in admission["session_registry"]["records"]] == [
        ("source_1_76", 146), ("closed_77_177", 181), ("v4_178", 6),
        ("v6_179_180", 2), ("adopted_v7_182", 1),
    ]
    assert before == {path: value.sha(path) for path in targets}


@pytest.mark.skipif(not V7.exists(), reason="V7 evidence is host-local")
def test_forged_settlement_or_v7_manifest_race_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    projected = tmp_path / "package"
    projected.mkdir()
    forged = json.loads((PACKAGE / value.V7_SETTLEMENT).read_text(encoding="utf-8"))
    forged["event"]["repetition"] = 5
    (projected / value.V7_SETTLEMENT).write_text(json.dumps(forged), encoding="utf-8")
    monkeypatch.setattr(value, "HERE", projected)
    with pytest.raises(ValueError, match="settlement"):
        value.admit_v7_prefix(SOURCE, CLOSED, V7)

    copied = tmp_path / "v7-copy"
    shutil.copytree(V7, copied)
    payload = copied / "runs" / "hanna-523" / "naplan_narrative_2022" / "run-01" / "result.json"
    payload.write_text(payload.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    monkeypatch.setattr(value, "HERE", PACKAGE)
    with pytest.raises(ValueError):
        value.admit_v7_prefix(SOURCE, CLOSED, copied)


@pytest.mark.skipif(not V7.exists(), reason="V7 evidence is host-local")
def test_failure_projection_and_mid_validation_manifest_mutation_reject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    projected = tmp_path / "package"
    projected.mkdir()
    forged = json.loads((PACKAGE / value.V7_SETTLEMENT).read_text(encoding="utf-8"))
    forged["failure_projection"]["cause"] = "different"
    (projected / value.V7_SETTLEMENT).write_text(json.dumps(forged), encoding="utf-8")
    monkeypatch.setattr(value, "HERE", projected)
    with pytest.raises(ValueError, match="failure projection"):
        value.admit_v7_prefix(SOURCE, CLOSED, V7)

    copied = tmp_path / "v7-race"
    shutil.copytree(V7, copied)
    monkeypatch.setattr(value, "HERE", PACKAGE)
    original = value._historical_session_registry

    def mutate(*args):
        result = original(*args)
        path = copied / "runs" / "hanna-523" / "naplan_narrative_2022" / "run-01" / "result.json"
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(value, "_historical_session_registry", mutate)
    with pytest.raises(ValueError, match="changed during adoption"):
        value.admit_v7_prefix(SOURCE, CLOSED, copied)


def test_fixture_session_extraction_handles_native_and_hbq_shapes(tmp_path: Path):
    value = module()
    native = tmp_path / "native"
    native.mkdir()
    (native / "response.json").write_text(json.dumps({"provider": {"reported": {"session_id": "native-session"}}}), encoding="utf-8")
    (native / "responses").mkdir()
    (native / "responses" / "batch-0001.attempt-0001.message.json").write_text('{"attempt":1}', encoding="utf-8")
    (native / "attempts").mkdir()
    (native / "attempts" / "rejected-0001.json").write_text(json.dumps({"response": {"provider": {"reported": {"session_id": "native-rejected"}}}}), encoding="utf-8")
    (native / "retry-attempts" / "attempt-0001").mkdir(parents=True)
    retry_responses = native / "retry-attempts" / "attempt-0002" / "responses"
    retry_responses.mkdir(parents=True)
    (retry_responses / "batch-0001.attempt-0001.message.json").write_text('{"attempt":2}', encoding="utf-8")
    assert value._output_sessions(native, {"arm_id": "naplan_narrative_2022"}) == ["native-rejected", "native-session"]
    hbq = tmp_path / "hbq"
    (hbq / "responses").mkdir(parents=True)
    (hbq / "run.json").write_text(json.dumps({"configuration": {"question_ids": []}}), encoding="utf-8")
    for batch in range(1, 7):
        accepted_attempt = 2 if batch == 1 else 1
        (hbq / "responses" / f"batch-{batch:04d}.json").write_text(json.dumps({"batch": batch, "accepted_attempt": accepted_attempt, "provider": {"reported": {"session_id": f"hbq-{batch}"}}}), encoding="utf-8")
        for attempt in range(1, accepted_attempt + 1):
            (hbq / "responses" / f"batch-{batch:04d}.attempt-{attempt:04d}.message.json").write_text("{}", encoding="utf-8")
    rejected = hbq / "responses" / "rejected" / "batch-0001"
    rejected.mkdir(parents=True)
    (rejected / "attempt-0001.json").write_text(json.dumps({"response": {"provider": {"reported": {"session_id": "hbq-rejected"}}}}), encoding="utf-8")
    assert value._output_sessions(hbq, {"arm_id": "hbq_short_story_batch32"}) == [*[f"hbq-{batch}" for batch in range(1, 7)], "hbq-rejected"]
    (hbq / "responses" / "batch-0001.attempt-0002.message.json").unlink()
    with pytest.raises(ValueError, match="ordinals"):
        value._output_sessions(hbq, {"arm_id": "hbq_short_story_batch32"})
    (hbq / "responses" / "batch-0001.attempt-0002.message.json").write_text('{"attempt":2}', encoding="utf-8")
    (hbq / "responses" / "batch-0001.json").write_text(json.dumps({"batch": 1, "provider": {"reported": {"session_id": "hbq-1"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="accepted_attempt"):
        value._output_sessions(hbq, {"arm_id": "hbq_short_story_batch32"})


def test_native_session_record_and_message_ordinals_must_match(tmp_path: Path):
    value = module()
    output = tmp_path / "native"
    (output / "responses").mkdir(parents=True)
    (output / "responses" / "batch-0001.attempt-0001.message.json").write_text('{"attempt":1}', encoding="utf-8")
    (output / "response.json").write_text(json.dumps({"provider": {"reported": {"session_id": "accepted"}}}), encoding="utf-8")
    (output / "attempts").mkdir()
    (output / "attempts" / "rejected-0001.json").write_text(json.dumps({"response": {"provider": {"reported": {"session_id": "rejected"}}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="ordinals"):
        value._output_sessions(output, {"arm_id": "naplan_narrative_2022"})


def test_native_rejected_filenames_must_be_contiguous(tmp_path: Path):
    value = module()
    output = tmp_path / "native"
    attempts = output / "attempts"
    attempts.mkdir(parents=True)
    record = json.dumps({"response": {"provider": {"reported": {"session_id": "rejected"}}}})
    (attempts / "rejected-0002.json").write_text(record, encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous"):
        value._native_rejected_sessions(output)
    (attempts / "rejected-0001.json").write_text(record, encoding="utf-8")
    (attempts / "rejected-0004.json").write_text(record, encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous"):
        value._native_rejected_sessions(output)


def test_paused_native_resume_reuses_contiguous_rejected_topology(tmp_path: Path):
    value = module()
    event = {"sequence": 183, "item_id": "new", "arm_id": "naplan_narrative_2022", "repetition": 1}
    attempts = tmp_path / "work" / "runs" / "new" / "naplan_narrative_2022" / "run-01" / "attempts"
    attempts.mkdir(parents=True)
    record = json.dumps({"reason": "semantic", "response": {"provider": {"reported": {"session_id": "rejected"}}}})
    (attempts / "rejected-0002.json").write_text(record, encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous"):
        value._require_paused_cell_resumable(tmp_path / "work", event)
    (attempts / "rejected-0001.json").write_text(record, encoding="utf-8")
    (attempts / "rejected-0004.json").write_text(record, encoding="utf-8")
    with pytest.raises(ValueError, match="contiguous"):
        value._require_paused_cell_resumable(tmp_path / "work", event)


def test_session_validator_excludes_only_zero_contact_181_and_includes_adopted_182(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work = tmp_path / "work"
    output = work / "runs" / "new" / "native" / "run-01"
    output.mkdir(parents=True)
    (output / "response.json").write_text(json.dumps({"provider": {"reported": {"session_id": "fresh-session"}}}), encoding="utf-8")
    (output / "responses").mkdir()
    (output / "responses" / "batch-0001.attempt-0001.message.json").write_text('{"attempt":1}', encoding="utf-8")
    (output / "attempts").mkdir()
    rejected = output / "attempts" / "rejected-0001.json"
    rejected.write_text(json.dumps({"response": {"provider": {"reported": {"session_id": "fresh-rejected-session"}}}}), encoding="utf-8")
    (output / "retry-attempts" / "attempt-0001").mkdir(parents=True)
    retry_responses = output / "retry-attempts" / "attempt-0002" / "responses"
    retry_responses.mkdir(parents=True)
    (retry_responses / "batch-0001.attempt-0001.message.json").write_text('{"attempt":2}', encoding="utf-8")

    class Study:
        @staticmethod
        def _session_ids(_source: Path) -> list[str]:
            return ["source-session"]

    monkeypatch.setattr(value, "_load_successor_study", lambda: Study())
    registry = {"ids": ["source-session", value.EXPECTED_V7_SESSION], "count": 2, "excluded_zero_contact_sequence": 181}
    registry["sha256"] = hashlib.sha256(value.canonical(registry["ids"])).hexdigest()
    admission = {"session_bearing": [{"sequence": 182, "session_id": value.EXPECTED_V7_SESSION, "recorded_provider_contacts": 1}], "session_registry": registry}
    value._validate_contact_sessions(Path("C:/source"), work, admission, [
        {"sequence": 182, "item_id": "hanna-523", "arm_id": "naplan_narrative_2022", "repetition": 1},
        {"sequence": 183, "item_id": "new", "arm_id": "native", "repetition": 1},
    ])
    rejected.write_text(json.dumps({"response": {"provider": {"reported": {"session_id": value.EXPECTED_V7_SESSION}}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="collides"):
        value._validate_contact_sessions(Path("C:/source"), work, admission, [{"sequence": 183, "item_id": "new", "arm_id": "native", "repetition": 1}])


@pytest.mark.skipif(not (V7.exists() and CLOSED.exists() and SOURCE.exists()), reason="host-local CWR evidence is unavailable")
def test_dry_run_adopts_182_and_never_dispatches_it(tmp_path: Path):
    value = module()
    result = value.execute(SOURCE, CLOSED, V7, tmp_path / "v8-work", dry_run=True)
    assert result["provider_calls"] == 0
    assert result["admitted_sequence"] == result["adopted_sequence"] == 182
    assert result["completed"] == 1
    assert result["cells"] == 148
    assert result["first_sequence"] == 183
    journal = value._jsonl(tmp_path / "v8-work" / value.JOURNAL)
    assert [row["event"] for row in journal] == ["admitted-prefix", "adopted-v7-output"]
    assert result["accounting"]["minimum_physical_provider_contacts"] == 269
