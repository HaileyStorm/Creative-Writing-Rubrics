from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v7"
V6 = Path(r"C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v6-live-unique")
CLOSED = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff")
SOURCE = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")


def module():
    spec = importlib.util.spec_from_file_location("multisample_successor_v7_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def test_contract_pins_v6_admission_and_v7_schedule():
    value = module()
    c = value.contract()
    assert c["study_id"].endswith("successor-v7")
    assert c["schedule"] == {
        "count": 150,
        "first_sequence": 181,
        "last_sequence": 330,
        "source_full_schedule_sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086",
        "sha256": "7866694887a6abcfb78fea4dd220e7ce3c5bb7ebbd85bc529ef18f06fddf89e8",
    }
    assert c["admitted_prefix"]["completed_sequences"] == [179, 180]
    assert c["admitted_prefix"]["settled_precontact_sequence"] == 181
    assert "scope_compatibility_override" not in c
    assert c["cohort_compatibility_policy"]["path"] == "cohort-compatibility-policy.json"


def test_forensic_settlement_is_explicitly_local_not_provider_attestation():
    value = module()
    settlement = value.read_json(PACKAGE / value.FORENSIC_SETTLEMENT)
    projection = settlement["task_history_projection"]
    assert settlement["not_provider_attestation"] is True
    assert projection["command_item_id"] == "exec-0df77963-2a4e-4acb-a2a6-1a9328200f57"
    assert projection["exit_code"] == 1
    assert projection["ordering"] == ["_scope_compatibility", "before_provider_attempt", "_call_codex"]
    assert settlement["settled_sequence"]["provider_contacts"] == 0
    assert settlement["settled_sequence"]["repetition"] == 1
    assert "absence alone" in settlement["settled_sequence"]["settlement_basis"]


@pytest.mark.skipif(not CLOSED.exists(), reason="closed schedule evidence is host-local")
def test_schedule_is_exact_181_330_canonical_suffix():
    value = module()
    schedule = value._fresh_schedule(CLOSED)
    assert [row["sequence"] for row in schedule] == list(range(181, 331))
    assert hashlib.sha256(value.canonical(schedule)).hexdigest() == value.contract()["schedule"]["sha256"]


@pytest.mark.skipif(not V6.exists(), reason="V6 evidence is host-local")
def test_v6_admission_recomputes_completed_contacts_and_preserves_v6_bytes():
    value = module()
    targets = [V6 / name for name in ("v6-binding.json", "schedule.jsonl", "execution-journal.jsonl", "active-epoch-claim.json", "preflight-disclosure.json", "disclosure-acknowledgement.json")]
    before = {path: value.sha(path) for path in targets}
    admitted = value.admit_v6_prefix(V6)
    assert admitted["completed_sequences"] == [179, 180]
    assert admitted["settled_precontact_sequence"] == 181
    assert before == {path: value.sha(path) for path in targets}


@pytest.mark.skipif(not V6.exists(), reason="V6 evidence is host-local")
def test_forged_or_missing_forensic_trace_rejects_v6_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    forged = json.loads((PACKAGE / value.FORENSIC_SETTLEMENT).read_text(encoding="utf-8"))
    forged["task_history_projection"]["ordering"] = ["_call_codex"]
    forged_path = tmp_path / value.FORENSIC_SETTLEMENT
    forged_path.write_text(json.dumps(forged, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="forensic trace settlement"):
        value.admit_v6_prefix(V6)


@pytest.mark.skipif(not V6.exists(), reason="V6 evidence is host-local")
@pytest.mark.parametrize(
    ("section", "field", "forged"),
    [
        ("settled_sequence", "repetition", 5),
        ("task_history_projection", "command_item_id", "forged-command"),
        ("task_history_projection", "captured_command", "python forged.py"),
        ("v6_evidence", "claim_sha256", "0" * 64),
    ],
)
def test_forensic_identity_and_hash_mismatches_reject_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, section: str, field: str, forged: object):
    value = module()
    settlement = json.loads((PACKAGE / value.FORENSIC_SETTLEMENT).read_text(encoding="utf-8"))
    settlement[section][field] = forged
    (tmp_path / value.FORENSIC_SETTLEMENT).write_text(json.dumps(settlement, sort_keys=True) + "\n", encoding="utf-8")
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="forensic trace settlement"):
        value.admit_v6_prefix(V6)


def test_forged_v6_root_is_rejected_before_any_settlement_read(tmp_path: Path):
    value = module()
    forged_root = tmp_path / "forged-v6"
    forged_root.mkdir()
    with pytest.raises(ValueError, match="immutable binding"):
        value.admit_v6_prefix(forged_root)


def test_policy_binds_all_eleven_hanna_contracts_and_engineering_reviewer():
    value = module()
    policy = value._cohort_policy()
    assert len(policy["entries"]) == 11
    assert {entry["artifact_id"] for entry in policy["entries"]} == {"hanna-52", "hanna-178", "hanna-225", "hanna-382", "hanna-445", "hanna-523", "hanna-594", "hanna-731", "hanna-817", "hanna-907", "hanna-1035"}
    assert policy["decision"]["reviewer_role"] == "engineering agent, not human/user"


@pytest.mark.skipif(not SOURCE.exists(), reason="frozen source evidence is host-local")
def test_override_schema_is_exact_and_bound_to_hanna_523():
    value = module()
    event = {"item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "sequence": 181, "repetition": 1}
    path = SOURCE / "inputs" / "hanna-523" / "task-contract.json"
    frozen = {"contract": {"arms": [{"arm_id": event["arm_id"], "kind": "hbq", "bundle_id": "prose.short_story"}]}}
    override = value._scope_override_value(SOURCE, event, frozen)
    assert override is not None
    assert set(override) == {"format_version", "artifact_id", "bundle_id", "task_contract_sha256", "contract_id", "artifact_kind", "declared_scope", "compatibility_mode", "decision_id", "reviewer", "reason"}
    assert override["task_contract_sha256"] == value.sha(path)
    assert override["artifact_id"] == "hanna-523"
    assert override["compatibility_mode"] == "reviewed_override"


@pytest.mark.skipif(not SOURCE.exists(), reason="frozen source evidence is host-local")
def test_override_drift_is_rejected_before_dispatch(tmp_path: Path):
    value = module()
    source, work = SOURCE, tmp_path / "work"
    event = {"item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "sequence": 181, "repetition": 1}
    work.mkdir()
    frozen = {"contract": {"arms": [{"arm_id": event["arm_id"], "kind": "hbq", "bundle_id": "prose.short_story"}]}}
    value._materialize_scope_overrides(work, source, [event], frozen)
    override_path = work / value.OVERRIDES / value._scope_override_name(event)
    forged = json.loads(override_path.read_text(encoding="utf-8"))
    forged["reason"] = "forged"
    override_path.write_text(json.dumps(forged) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="scope compatibility override drifted"):
        value._validate_scope_overrides(work, source, [event], frozen)


def test_acknowledgement_is_reusable_only_for_byte_identical_disclosure(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    disclosure = work / value.DISCLOSURE
    disclosure.write_text('{"cells":[]}\n', encoding="utf-8")
    ack = value.make_disclosure_ack(disclosure)
    ack_path = work / value.DISCLOSURE_ACK
    ack_path.write_text(json.dumps(ack) + "\n", encoding="utf-8")
    assert value._validate_disclosure_ack(work, ack_path) == ack
    disclosure.write_text('{"cells":[{"sequence":182}]}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        value._validate_disclosure_ack(work, ack_path)


def test_forensic_journal_entry_must_precede_any_intent(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    admission = {"sequence": 180}
    schedule = [{"sequence": 181}, {"sequence": 182}]
    (work / value.JOURNAL).write_bytes(value.canonical({"event": "admitted-prefix", **admission}) + b"\n")
    with pytest.raises(ValueError, match="forensic settlement"):
        value._accepted(work, schedule, admission)


def test_unresolved_intent_is_not_resendable(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    admission = {"sequence": 180}
    settlement_hash = value.sha(PACKAGE / value.FORENSIC_SETTLEMENT)
    (work / value.PROOFS).mkdir()
    proof_payload = {"sequence": 182, "capacity": {"observed_at": "2026-08-27T00:00:00+00:00"}}
    proof_temp = work / value.PROOFS / "proof.json"
    proof_temp.write_text(json.dumps(proof_payload) + "\n", encoding="utf-8")
    proof_digest = value.sha(proof_temp)
    proof_temp.rename(work / value.PROOFS / (proof_digest + ".json"))
    rows = [
        {"event": "admitted-prefix", **admission},
        {"event": "forensic-precontact", "sequence": 181, "settlement_sha256": settlement_hash},
        {"event": "attempt-intent", "sequence": 182, "capacity_proof_sha256": proof_digest, "observed_at": "2026-08-27T00:00:00+00:00"},
    ]
    (work / value.JOURNAL).write_bytes(b"".join(value.canonical(row) + b"\n" for row in rows))
    with pytest.raises(ValueError, match="unresolved attempt intent"):
        value._accepted(work, [{"sequence": 181, "item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "repetition": 1}, {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}], admission)


def test_dispatch_passes_full_disclosed_cell_and_predecessor_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work, source = tmp_path / "work", tmp_path / "source"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    cell = {**event, "payload": {"provider_payloads": [{"batch": 1, "request": {"prompt_utf8": "p", "response_schema_utf8": "{}"}}]}}
    (work / value.DISCLOSURE).write_text(json.dumps({"profile": value.contract()["provider"], "cells": [cell]}) + "\n", encoding="utf-8")
    predecessor = object()
    monkeypatch.setattr(value, "_load_predecessor_runner", lambda: predecessor)
    captured = {}
    class Helper:
        def runtime_identity(self):
            return {"helper_id": "fixture", "path": "runner.py", "bytes": 1, "sha256": "f" * 64}

        def dispatch_event(self, **kwargs):
            captured.update(kwargs)
            return tmp_path / "result.json"
    frozen = {"contract": {"arms": [{"arm_id": "compact_analytic", "kind": "native", "bundle_id": "unused"}]}}
    assert value._dispatch_event(Helper(), event, frozen, source, work, 1.0, lambda _: None) == tmp_path / "result.json"
    assert captured["disclosed_cell"] == cell
    assert captured["disclosure_profile"] == value.contract()["provider"]
    assert captured["predecessor_runner"] is predecessor
    assert captured["scope_compatibility_override_path"] is None
    commitments = {
        "provider": {key: value.contract()["provider"][key] for key in ("provider", "model", "reasoning")},
        "disclosure_profile": value.contract()["provider"],
        "disclosed_cell_sha256": hashlib.sha256(value.canonical(cell)).hexdigest(),
        "disclosure_profile_sha256": hashlib.sha256(value.canonical(value.contract()["provider"])).hexdigest(),
        "helper": Helper().runtime_identity(),
    }
    captured["provider_boundary_check"]({}, commitments)
    commitments["helper"] = {"forged": True}
    with pytest.raises(ValueError, match="Provider-boundary commitments"):
        captured["provider_boundary_check"]({}, commitments)


def test_integrated_helper_runs_v7_provider_boundary_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work, source = tmp_path / "work", tmp_path / "source"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    payload = value._provider_payload(1, b"prompt", b"{}", [])
    cell = {**event, "outbound_artifacts": [{"role": "artifact"}, {"role": "originating_prompt"}], "payload": {"provider_payloads": [payload], "rubric": []}}
    (work / value.DISCLOSURE).write_text(json.dumps({"profile": value.contract()["provider"], "cells": [cell], "scope_compatibility_overrides": []}) + "\n", encoding="utf-8")
    helper = value._load_successor_runner()
    calls = []
    def fake_native(**kwargs):
        kwargs["before_provider_attempt"]({"attempt": {"number": 1}, "batch": {"number": 1, "question_ids": []}, "prompt": {"encoding": "utf-8", "text": "prompt"}, "response_schema": {"encoding": "utf-8", "text": "{}"}, "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}})
        return tmp_path / "pass.json"
    monkeypatch.setattr(helper, "_dispatch_native", fake_native)
    monkeypatch.setattr(value, "_load_predecessor_runner", lambda: object())
    result = value._dispatch_event(helper, event, {"contract": {"provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}, "arms": [{"arm_id": "compact_analytic", "kind": "native", "bundle_id": "unused"}]}}, source, work, 1.0, lambda context: calls.append(context))
    assert result == tmp_path / "pass.json"
    assert calls == [{"attempt": {"number": 1}, "batch": {"number": 1, "question_ids": []}, "prompt": {"encoding": "utf-8", "text": "prompt"}, "response_schema": {"encoding": "utf-8", "text": "{}"}, "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high"}}]


def _native_retry_output(value, work: Path, event: dict[str, object]) -> Path:
    output = value._output_path(work, event).parent
    (output / "responses").mkdir(parents=True)
    (output / "responses" / "batch-0001.attempt-0001.message.json").write_text('{"attempt":"base"}\n', encoding="utf-8")
    (output / "retry-attempts" / "attempt-0001").mkdir(parents=True)
    (output / "retry-attempts" / "attempt-0002" / "responses").mkdir(parents=True)
    (output / "retry-attempts" / "attempt-0002" / "responses" / "batch-0001.attempt-0001.message.json").write_text('{"attempt":"retry"}\n', encoding="utf-8")
    return output


def test_native_retry_completion_journals_two_physical_contacts(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event_181 = {"sequence": 181, "item_id": "hanna-523", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    output = _native_retry_output(value, work, event)
    target = output / "pass.json"
    target.write_text("{}\n", encoding="utf-8")
    admission = {"sequence": 180}
    receipt = {"kind": "external_current_capacity_evidence_v2", "provider": "codex", "model": "gpt-5.6-sol", "assertion": "capacity_available", "attestation": "local_host_observation_only", "observed_at": "2026-08-27T00:00:00+00:00", "observation": {"surface": "native_codex_quota_surface", "reference": "fixture"}}
    _, digest = value._proof(work, 182, receipt)
    settlement_hash = value.sha(PACKAGE / value.FORENSIC_SETTLEMENT)
    rows = [
        {"event": "admitted-prefix", **admission},
        {"event": "forensic-precontact", "sequence": 181, "settlement_sha256": settlement_hash},
        {"event": "attempt-intent", "sequence": 182, "capacity_proof_sha256": digest, "observed_at": receipt["observed_at"]},
        {"event": "provider-contacts", "sequence": 182, "capacity_proof_sha256": digest, "recorded_provider_contacts": 2},
        {"event": "completed", "sequence": 182, "capacity_proof_sha256": digest, "output_sha256": value.sha(target)},
    ]
    (work / value.JOURNAL).write_bytes(b"".join(value.canonical(row) + b"\n" for row in rows))
    schedule = [event_181, event]
    assert value._recorded_provider_contacts(work, event) == 2
    assert value._accepted(work, schedule, admission) == schedule
    assert value._journaled_provider_contacts(work, schedule) == 2


def test_native_retry_unresolved_bounds_count_nested_retry_message_once(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    _native_retry_output(value, work, event)
    assert value._unresolved_contact_bounds(work, event) == {"observed_contact_lower_bound": 2, "uncertain_contact_evidence_count": 0, "contact_upper_bound": 3}


def test_native_retry_rejects_archived_attempt_one_response_even_when_retry_two_exists(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    output = _native_retry_output(value, work, event)
    archive_responses = output / "retry-attempts" / "attempt-0001" / "responses"
    archive_responses.mkdir()
    (archive_responses / "batch-0001.attempt-0001.message.json").write_text('{"attempt":"archived-duplicate"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate canonical attempt-one"):
        value._unresolved_contact_bounds(work, event)


def test_native_retry_rejects_duplicate_message_content_at_different_paths(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    output = _native_retry_output(value, work, event)
    base = output / "responses" / "batch-0001.attempt-0001.message.json"
    retry = output / "retry-attempts" / "attempt-0002" / "responses" / "batch-0001.attempt-0001.message.json"
    retry.write_bytes(base.read_bytes())
    with pytest.raises(ValueError, match="content is duplicated"):
        value._recorded_provider_contacts(work, event)


def test_native_retry_rejects_shadow_entry_in_allowed_response_root(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    output = _native_retry_output(value, work, event)
    (output / "responses" / "unexpected").mkdir()
    (output / "responses" / "shadow.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="one exact message"):
        value._recorded_provider_contacts(work, event)


def test_native_retry_rejects_empty_retry_attempts_root(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 182, "item_id": "hanna-52", "arm_id": "compact_analytic", "repetition": 1}
    output = value._output_path(work, event).parent
    (output / "responses").mkdir(parents=True)
    (output / "responses" / "batch-0001.attempt-0001.message.json").write_text('{"attempt":"base"}\n', encoding="utf-8")
    (output / "retry-attempts").mkdir()
    with pytest.raises(ValueError, match="unexpected attempt root"):
        value._unresolved_contact_bounds(work, event)
