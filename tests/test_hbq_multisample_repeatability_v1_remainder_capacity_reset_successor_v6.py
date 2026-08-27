from __future__ import annotations

import importlib.util
import inspect
import hashlib
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v6"
SOURCE = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
CLOSED = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-successor-20260821-9422eff")
V4 = Path(r"C:\Users\Haile\Documents\cwr-multisample-capacity-reset-v4-live-1c587bc-20260822")
V5 = Path(r"C:\Users\Haile\Documents\cwr-multisample-v5-owner-validated-settlement-20260822\offline-recovered-completion.json")


def module():
    spec = importlib.util.spec_from_file_location("multisample_successor_v6_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


HAS_EXTERNAL_EVIDENCE = all(path.exists() for path in (SOURCE, CLOSED, V4, V5))


def test_contract_pins_admission_and_untouched_suffix():
    value = module().contract()
    assert value["supersedes"]["v4_package_commit"] == "1c587bc311e0f303e809d842ec1035e5e81eb60b"
    assert value["lineage"]["capacity_reset_v4_commit"] == "1c587bc311e0f303e809d842ec1035e5e81eb60b"
    assert value["admitted_prefix"]["sequence"] == 178
    assert value["schedule"] == {
        "count": 152,
        "first_sequence": 179,
        "last_sequence": 330,
        "source_full_schedule_sha256": "96b91f124d2a889f4fa47b70d67c16604927f33928ca4ad5d302713c84f8f086",
        "sha256": "6f22cdcd4501e1de4c90ec9c756c2006a7dcef9e9ee8c446ce8b985f2bb3ec4b",
    }
    assert value["execution"]["max_workers"] == 1
    assert value["execution"]["journal_commit_order"] == "ascending sequence only"
    assert value["evaluation_population"] == {
        "generated_stories": 10,
        "human_story": 1,
        "primary": {"stories": 10, "cells": 300},
        "secondary": {"stories": 1, "cells": 30},
        "total_cells": 330,
    }
    assert value["accounting"]["suffix_logical_cells"] == 152
    assert value["accounting"]["suffix_minimum_physical_provider_contacts"] == 277
    assert value["accounting"]["suffix_retry_ceiling"] == 831
    lineage = value["lineage"]
    for key in ("closed_successor_study_git_blob_oid_sha1", "closed_successor_runner_git_blob_oid_sha1", "remainder_study_git_blob_oid_sha1"):
        assert len(lineage[key]) == 40
        assert "sha256" not in key
    assert value["capacity_gate"]["attestation"] == "local_host_observation_only"
    assert value["capacity_gate"]["does_not_attest"] == ["provider_acceptance", "future_capacity"]


@pytest.mark.skipif(not HAS_EXTERNAL_EVIDENCE, reason="immutable multisample evidence roots are host-local")
def test_admit_sequence_178_checks_v4_and_v5_without_writing():
    value = module()
    before = {path: value.sha(path) for path in (V4 / "execution-journal.jsonl", V4 / "active-epoch-claim.json", V5)}
    admitted = value.admit_sequence_178(V4, V5)
    after = {path: value.sha(path) for path in before}
    assert admitted["sequence"] == 178
    assert admitted["v4_run_sha256"] == admitted["v5_completion_sha256"]
    assert before == after


@pytest.mark.skipif(not HAS_EXTERNAL_EVIDENCE, reason="immutable multisample evidence roots are host-local")
def test_admission_rejects_tampered_v5_sidecar(tmp_path: Path):
    value = module()
    copied = tmp_path / "offline-recovered-completion.json"
    shutil.copy2(V5, copied)
    record = json.loads(copied.read_text(encoding="utf-8"))
    record["reason"] = "changed"
    copied.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sidecar drifted"):
        value.admit_sequence_178(V4, copied)


@pytest.mark.skipif(not HAS_EXTERNAL_EVIDENCE, reason="immutable multisample evidence roots are host-local")
def test_prepare_and_dry_run_create_only_fresh_179_330_root(tmp_path: Path):
    value = module()
    work = tmp_path / "v6-work"
    source_before = value.sha(SOURCE / "frozen-run-contract.json")
    closed_before = {name: value.sha(CLOSED / name) for name in ("predecessor-binding.json", "successor-schedule-journal.jsonl")}
    prepared = value.prepare(SOURCE, CLOSED, V4, V5, work)
    assert prepared["provider_calls"] == 0
    assert prepared["admitted_sequence"] == 178
    assert (work / value.BINDING).is_file()
    assert (work / value.ADMISSION).is_file()
    assert len(value._jsonl(work / value.SCHEDULE)) == 152
    assert value._jsonl(work / value.SCHEDULE)[0]["sequence"] == 179
    disclosure = value.read_json(work / value.DISCLOSURE)
    assert disclosure["destination"] == "codex"
    assert disclosure["profile"]["model"] == "gpt-5.6-sol"
    assert len(disclosure["cells"]) == 152
    assert all(cell["source_path_identifier"].startswith("inputs/") for cell in disclosure["cells"])
    assert all(cell["payload"]["provider_payloads"] for cell in disclosure["cells"])
    assert all("rendered_prompts" not in cell["payload"] and "schema" not in cell["payload"] for cell in disclosure["cells"])
    assert all(cell["outbound_artifacts"] for cell in disclosure["cells"])
    assert all("utf8" in artifact for cell in disclosure["cells"] for artifact in cell["outbound_artifacts"])
    assert all("prompt_utf8" in payload["request"] and "response_schema_utf8" in payload["request"] for cell in disclosure["cells"] for payload in cell["payload"]["provider_payloads"])
    hbq_cells = [cell for cell in disclosure["cells"] if cell["arm_id"] == "hbq_short_story_batch32"]
    native_cells = [cell for cell in disclosure["cells"] if cell["arm_id"] != "hbq_short_story_batch32"]
    assert all(len(cell["payload"]["provider_payloads"]) == 6 for cell in hbq_cells)
    assert all(len(cell["payload"]["provider_payloads"]) == 1 for cell in native_cells)
    assert value.make_disclosure_ack(work / value.DISCLOSURE)["disclosure_sha256"] == value.sha(work / value.DISCLOSURE)
    reloaded = value.execute(SOURCE, CLOSED, V4, V5, work, dry_run=True)
    assert reloaded["provider_calls"] == 0
    assert reloaded["completed"] == 0
    assert reloaded["first_sequence"] == 179
    assert reloaded["last_sequence"] == 330
    assert reloaded["accounting"]["logical_cells"] == 152
    assert reloaded["accounting"]["minimum_physical_provider_contacts"] == 277
    assert reloaded["accounting"]["retry_ceiling"] == 831
    assert source_before == value.sha(SOURCE / "frozen-run-contract.json")
    assert closed_before == {name: value.sha(CLOSED / name) for name in closed_before}


def test_current_runner_never_dispatches_without_explicit_remote_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    monkeypatch.setattr(value, "prepare", lambda *args: None)
    monkeypatch.setattr(value, "_verify_prepared", lambda *args: ({}, [], {"sequence": 178}))
    monkeypatch.setattr(value, "_accepted", lambda *args: [])
    with pytest.raises(ValueError, match="allow-remote"):
        value.execute(SOURCE, CLOSED, V4, V5, tmp_path / "work", dry_run=False)


def test_one_worker_protocol_has_no_cli_concurrency_override():
    value = module()
    assert value.MAX_WORKERS == 1
    assert "max_workers" not in inspect.signature(value.execute).parameters
    assert "--max-workers" not in (PACKAGE / "executor.py").read_text(encoding="utf-8")


def test_pinned_git_objects_are_not_labeled_sha256():
    value = module()
    successor = value._pinned_successor_source()
    remainder = value._pinned_remainder_source()
    assert "files_sha256" in successor
    assert all("git_blob_oid_sha1" in record and "sha256" not in record for record in successor["files"])
    assert "git_blob_oid_sha1" in remainder and "sha256" not in remainder
    value._git_sha1_object_format()


def test_one_cell_epoch_has_no_thread_fanout():
    value = module()
    assert value.MAX_WORKERS == 1
    assert not hasattr(value, "_run_wave")


def test_journal_rejects_unresolved_intent_after_admission(tmp_path: Path):
    value = module()
    schedule = [{"sequence": 179, "item_id": "fixture", "arm_id": "compact_analytic", "repetition": 1}]
    admission = {"sequence": 178}
    work = tmp_path / "work"
    work.mkdir()
    (work / value.JOURNAL).write_bytes(value.canonical({"event": "admitted-prefix", **admission}) + b"\n")
    proof, digest = value._proof(work, 179, {
        "kind": "external_current_capacity_evidence_v2",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "assertion": "capacity_available",
        "attestation": "local_host_observation_only",
        "observed_at": "2026-08-27T00:00:00+00:00",
        "observation": {"surface": "native_codex_quota_surface", "reference": "test"},
        "unprojected": "discarded",
    })
    assert json.loads(proof.read_text(encoding="utf-8")) == {
        "capacity": {
            "assertion": "capacity_available",
            "attestation": "local_host_observation_only",
            "kind": "external_current_capacity_evidence_v2",
            "model": "gpt-5.6-sol",
            "observation": {"reference": "test", "surface": "native_codex_quota_surface"},
            "observed_at": "2026-08-27T00:00:00+00:00",
            "provider": "codex",
        },
        "sequence": 179,
    }
    value._append(work / value.JOURNAL, {"event": "attempt-intent", "sequence": 179, "capacity_proof_sha256": digest, "observed_at": "2026-08-27T00:00:00+00:00"})
    with pytest.raises(ValueError, match="unresolved attempt intent"):
        value._accepted(work, schedule, admission)


def test_journal_rejects_completion_out_of_sequence(tmp_path: Path):
    value = module()
    schedule = [{"sequence": 179}, {"sequence": 180}]
    admission = {"sequence": 178}
    work = tmp_path / "work"
    work.mkdir()
    (work / value.JOURNAL).write_bytes(value.canonical({"event": "admitted-prefix", **admission}) + b"\n")
    _, digest = value._proof(work, 180, {
        "kind": "external_current_capacity_evidence_v2",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "assertion": "capacity_available",
        "attestation": "local_host_observation_only",
        "observed_at": "2026-08-27T00:00:00+00:00",
        "observation": {"surface": "native_codex_quota_surface", "reference": "test"},
    })
    value._append(work / value.JOURNAL, {"event": "attempt-intent", "sequence": 180, "capacity_proof_sha256": digest, "observed_at": "2026-08-27T00:00:00+00:00"})
    with pytest.raises(ValueError, match="ordered prefix"):
        value._accepted(work, schedule, admission)


def _capacity_receipt(observed_at: str | None = None) -> dict[str, object]:
    return {
        "kind": "external_current_capacity_evidence_v2",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "assertion": "capacity_available",
        "attestation": "local_host_observation_only",
        "observed_at": observed_at or datetime.now(UTC).isoformat(),
        "observation": {"surface": "native_codex_quota_surface", "reference": "test-receipt"},
    }


def _fake_epoch(value, tmp_path: Path):
    work = tmp_path / "work"
    work.mkdir()
    (work / value.BINDING).write_text("{}\n", encoding="utf-8")
    (tmp_path / "frozen-run-contract.json").write_text("{}\n", encoding="utf-8")
    def fake_disclosure(source, event, frozen):
        return {
            "sequence": event["sequence"],
            "item_id": event["item_id"],
            "arm_id": event["arm_id"],
            "repetition": event["repetition"],
            "source_path_identifier": "inputs/test-item/source.md",
            "outbound_artifacts": [{"role": "artifact", "utf8": "fixture prose"}],
            "payload": {"provider_payloads": [{"batch": 1, "request": {"prompt_utf8": "fixture prompt batch 1", "response_schema_utf8": "{}"}, "payload_sha256": "f" * 64}], "rubric": []},
        }

    value._event_disclosure = fake_disclosure
    admission = {"sequence": 178}
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", **admission})
    receipt_path = tmp_path / "capacity.json"
    receipt_path.write_text(json.dumps(_capacity_receipt()) + "\n", encoding="utf-8")
    event = {"sequence": 179, "item_id": "test-item", "arm_id": "compact_analytic", "repetition": 1}
    (work / value.DISCLOSURE).write_text(json.dumps({"cells": [fake_disclosure(tmp_path, event, {})]}) + "\n", encoding="utf-8")
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    return work, admission, receipt_path, event


class _SuccessfulFakeRunner:
    def _revalidate_predecessor_event(self, source, frozen, event):
        return None

    def _v1_runner(self):
        return self

    def _run_event(self, runner, event, frozen, source, work, timeout, before_provider_attempt=None):
        if before_provider_attempt is not None and event["arm_id"] == "hbq_short_story_batch32":
            before_provider_attempt({"attempt": {"number": 1}})
        output = work / "runs" / event["item_id"] / event["arm_id"] / "run-01" / "pass.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        response = output.parent / "responses" / "batch-0001.attempt-0001.message.json"
        response.parent.mkdir(parents=True, exist_ok=True)
        response.write_text('{}\n', encoding="utf-8")
        output.write_text('{"session_id":"fresh-test-session"}\n', encoding="utf-8")
        return output

    def _validate_global_sessions(self, source, work, events):
        return None


def test_stale_capacity_fails_before_claim_or_intent(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    receipt_path.write_text(json.dumps(_capacity_receipt("2020-01-01T00:00:00+00:00")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not current"):
        value._settle_one(_SuccessfulFakeRunner(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert not (work / value.CLAIM).exists()
    assert len(value._read_journal(work)) == 1


def test_predispatch_failure_removes_claim_and_writes_no_intent(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)

    class FailingPreflight(_SuccessfulFakeRunner):
        def _revalidate_predecessor_event(self, source, frozen, event):
            raise ValueError("source drift before dispatch")

    with pytest.raises(ValueError, match="source drift"):
        value._settle_one(FailingPreflight(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert not (work / value.CLAIM).exists()
    assert len(value._read_journal(work)) == 1


def test_disclosure_acknowledgement_is_exact_before_dispatch(tmp_path: Path):
    value = module()
    work, _, _, _ = _fake_epoch(value, tmp_path)
    bad = json.loads((work / value.DISCLOSURE_ACK).read_text(encoding="utf-8"))
    bad["disclosure_sha256"] = "0" * 64
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        value._validate_disclosure_ack(work, work / value.DISCLOSURE_ACK)
    assert not (work / value.CLAIM).exists()


def test_tampered_exact_payload_is_rejected_before_dispatch(tmp_path: Path):
    value = module()
    work, _, _, event = _fake_epoch(value, tmp_path)
    disclosure = value.read_json(work / value.DISCLOSURE)
    disclosure["cells"][0]["payload"]["provider_payloads"][0]["request"]["prompt_utf8"] = "tampered"
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Exact disclosed provider payload drifted"):
        value._validate_disclosed_payload(work, tmp_path, event, {})


def test_worker_failure_keeps_claim_and_intent_for_fail_closed_reentry(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)

    class FailedWorker(_SuccessfulFakeRunner):
        def _run_event(self, *args, **kwargs):
            raise RuntimeError("worker failed after intent")

    with pytest.raises(RuntimeError, match="worker failed"):
        value._settle_one(FailedWorker(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert (work / value.CLAIM).exists()
    assert value._read_journal(work)[-1]["event"] == "attempt-intent"
    with pytest.raises(ValueError, match="unresolved attempt intent"):
        value._accepted(work, [event], admission)


def test_successful_cell_removes_claim_and_counts_output_as_accepted(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    accepted = value._settle_one(_SuccessfulFakeRunner(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert [row["sequence"] for row in accepted] == [179]
    assert not (work / value.CLAIM).exists()
    assert value._accounting([event], accepted)["accepted_cells"] == 1
    assert value._journaled_provider_contacts(work, [event]) == 1


def test_accounting_distinguishes_152_logical_cells_and_277_minimum_contacts():
    value = module()
    schedule = [{"sequence": i, "arm_id": "hbq_short_story_batch32" if i < 204 else "compact_analytic"} for i in range(179, 331)]
    accounting = value._accounting(schedule, [])
    assert accounting["logical_cells"] == 152
    assert accounting["minimum_physical_provider_contacts"] == 277
    assert accounting["retry_ceiling"] == 831


def test_recorded_provider_contacts_include_native_and_hbq_retries(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    native = {"item_id": "native", "arm_id": "compact_analytic", "repetition": 1}
    native_responses = value._output_path(work, native).parent / "responses"
    native_responses.mkdir(parents=True)
    for attempt in (1, 2):
        (native_responses / f"batch-0001.attempt-{attempt:04d}.message.json").write_text("{}\n", encoding="utf-8")
    assert value._recorded_provider_contacts(work, native) == 2

    hbq = {"item_id": "hbq", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    hbq_responses = value._output_path(work, hbq).parent / "responses"
    hbq_responses.mkdir(parents=True)
    for batch, accepted_attempt in ((1, 2), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1)):
        (hbq_responses / f"batch-{batch:04d}.json").write_text(
            json.dumps({"accepted_attempt": accepted_attempt}) + "\n", encoding="utf-8"
        )
    assert value._recorded_provider_contacts(work, hbq) == 7


def test_unresolved_hbq_rejected_attempts_contribute_exact_contact_bounds(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"item_id": "hbq", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    rejected = value._output_path(work, event).parent / "responses" / "rejected"
    rejected.mkdir(parents=True)
    (rejected / "batch-0001").mkdir()
    (rejected / "batch-0001" / "attempt-0001.json").write_text(
        json.dumps({"stage": "model_output", "raw_content": {"text": "rejected response"}}) + "\n",
        encoding="utf-8",
    )
    (rejected / "batch-0002").mkdir()
    (rejected / "batch-0002" / "attempt-0001.json").write_text(
        json.dumps({"stage": "provider_failure", "raw_content": {"text": None}}) + "\n",
        encoding="utf-8",
    )
    assert value._unresolved_contact_bounds(work, event) == {
        "observed_contact_lower_bound": 1,
        "uncertain_contact_evidence_count": 1,
        "contact_upper_bound": 18,
    }


def test_unresolved_hbq_accepted_attempt_already_includes_its_rejected_sidecar(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"item_id": "hbq", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    responses = value._output_path(work, event).parent / "responses"
    responses.mkdir(parents=True)
    (responses / "batch-0001.json").write_text('{"accepted_attempt":2}\n', encoding="utf-8")
    rejected = responses / "rejected" / "batch-0001"
    rejected.mkdir(parents=True)
    (rejected / "attempt-0001.json").write_text(json.dumps({"stage": "model_output", "raw_content": {"text": "already counted"}}) + "\n", encoding="utf-8")
    assert value._unresolved_contact_bounds(work, event) == {
        "observed_contact_lower_bound": 2,
        "uncertain_contact_evidence_count": 0,
        "contact_upper_bound": 18,
    }


def _retry_context(work: Path, attempt_number: int = 2, batch_number: int = 1) -> dict[str, object]:
    prompt = f"changed validation-feedback retry {attempt_number} batch {batch_number}"
    schema = '{"type":"object"}'
    return {
        "format_version": 1,
        "run": {"run_id": "retry-fixture", "config_sha256": "c" * 64},
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "endpoint": None},
        "batch": {"number": batch_number, "question_ids": [f"q-{batch_number}"]},
        "attempt": {"number": attempt_number, "batch_attempts": 3},
        "prompt": {"encoding": "utf-8", "text": prompt, "bytes": len(prompt.encode("utf-8")), "sha256": __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest(), "base_prompt_sha256": "b" * 64},
        "response_schema": {"encoding": "utf-8", "text": schema, "bytes": len(schema.encode("utf-8")), "sha256": __import__("hashlib").sha256(schema.encode("utf-8")).hexdigest()},
        "validation_feedback_policy": "validation_feedback_v1",
        "validation_feedback": {"reason": "fixture terminal rejection"},
        "rejected_chain": {"count": attempt_number - 1, "head_sha256": hashlib.sha256((work / "runs" / "test-item" / "hbq_short_story_batch32" / "run-01" / "responses" / "rejected" / f"batch-{batch_number:04d}" / f"attempt-{attempt_number - 1:04d}.json").read_bytes()).hexdigest()},
        "output_dir": str(work / "runs" / "test-item" / "hbq_short_story_batch32" / "run-01"),
    }


def _base_retry_context(work: Path, batch_number: int = 1) -> dict[str, object]:
    prompt = f"fixture prompt batch {batch_number}"
    schema = "{}"
    return {
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "endpoint": None},
        "batch": {"number": batch_number, "question_ids": [f"q-{batch_number}"]},
        "attempt": {"number": 1, "batch_attempts": 3},
        "prompt": {"encoding": "utf-8", "text": prompt, "bytes": len(prompt.encode("utf-8")), "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "base_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()},
        "response_schema": {"encoding": "utf-8", "text": schema, "bytes": len(schema.encode("utf-8")), "sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest()},
    }


class _RetryFakeRunner(_SuccessfulFakeRunner):
    def __init__(self) -> None:
        self.provider_contacts = 0
        self.calls = 0

    def _run_event(self, runner, event, frozen, source, work, timeout, before_provider_attempt=None):
        assert before_provider_attempt is not None
        self.calls += 1
        output = work / "runs" / event["item_id"] / event["arm_id"] / "run-01"
        if self.provider_contacts == 0:
            before_provider_attempt(_base_retry_context(work))
            self.provider_contacts += 1
            rejected = output / "responses" / "rejected" / "batch-0001"
            rejected.mkdir(parents=True)
            raw = "terminal"
            (rejected / "attempt-0001.json").write_text(json.dumps({"stage": "model_output", "raw_content": {"encoding": "utf-8", "text": raw, "bytes": len(raw.encode("utf-8")), "sha256": __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()}}) + "\n", encoding="utf-8")
        if self.provider_contacts == 1:
            before_provider_attempt(_retry_context(work, 2))
            self.provider_contacts += 1
            rejected = output / "responses" / "rejected" / "batch-0001"
            raw = "terminal second"
            (rejected / "attempt-0002.json").write_text(json.dumps({"stage": "model_output", "raw_content": {"encoding": "utf-8", "text": raw, "bytes": len(raw.encode("utf-8")), "sha256": __import__("hashlib").sha256(raw.encode("utf-8")).hexdigest()}}) + "\n", encoding="utf-8")
            before_provider_attempt(_retry_context(work, 3))
        else:
            before_provider_attempt(_retry_context(work, 3))
            self.provider_contacts += 1
        responses = output / "responses"
        responses.mkdir(parents=True, exist_ok=True)
        for batch, accepted_attempt in ((1, 2), (2, 1), (3, 1), (4, 1), (5, 1), (6, 1)):
            (responses / f"batch-{batch:04d}.json").write_text(json.dumps({"accepted_attempt": accepted_attempt}) + "\n", encoding="utf-8")
        target = output / "run.json"
        target.write_text('{"session_id":"retry-fixture"}\n', encoding="utf-8")
        return target


def test_changed_retry_pauses_before_second_contact_then_resumes_with_bound_ack_and_fresh_capacity(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    event = {**event, "arm_id": "hbq_short_story_batch32"}
    disclosure = value.read_json(work / value.DISCLOSURE)
    disclosure["cells"][0]["arm_id"] = event["arm_id"]
    disclosure["cells"][0]["payload"]["provider_payloads"][0]["question_ids"] = ["q-1"]
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    value._event_disclosure = lambda *_args: disclosure["cells"][0]
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    receipt_path.write_text(json.dumps(_capacity_receipt((datetime.now(UTC) - timedelta(seconds=30)).isoformat())) + "\n", encoding="utf-8")
    runner = _RetryFakeRunner()
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert runner.provider_contacts == 1
    assert not (work / value.CLAIM).exists()
    assert [row["event"] for row in value._read_journal(work)] == ["admitted-prefix", "attempt-intent", "retry-disclosure-pause"]
    assert value._accepted(work, [event], admission) == []
    pause = value._read_journal(work)[-1]
    retry_disclosure = value._retry_disclosure_path(work, pause["retry_disclosure_sha256"])
    assert value.read_json(retry_disclosure)["provider_attempt_context"] == _retry_context(work)

    with pytest.raises(ValueError, match="retry disclosure acknowledgement"):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert runner.provider_contacts == 1

    retry_ack = value._retry_ack_path(work, pause["retry_disclosure_sha256"])
    retry_ack.parent.mkdir(exist_ok=True)
    mismatched = value.make_retry_disclosure_ack(retry_disclosure, acknowledgement_id="owner-review-20260827-01", acknowledged_at=datetime.now(UTC).isoformat())
    mismatched["retry_disclosure_sha256"] = "0" * 64
    retry_ack.write_text(json.dumps(mismatched) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not exactly bind"):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0, retry_disclosure_ack=retry_ack)
    assert runner.provider_contacts == 1
    retry_ack.write_text(json.dumps(value.make_retry_disclosure_ack(retry_disclosure, acknowledgement_id="owner-review-20260827-01", acknowledged_at=datetime.now(UTC).isoformat())) + "\n", encoding="utf-8")
    receipt_path.write_text(json.dumps(_capacity_receipt(datetime.now(UTC).isoformat())) + "\n", encoding="utf-8")
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0, retry_disclosure_ack=retry_ack)
    assert runner.provider_contacts == 2
    second_pause = value._read_journal(work)[-1]
    second_disclosure = value._retry_disclosure_path(work, second_pause["retry_disclosure_sha256"])
    second_ack = value._retry_ack_path(work, second_pause["retry_disclosure_sha256"])
    second_ack.write_text(json.dumps(value.make_retry_disclosure_ack(second_disclosure, acknowledgement_id="owner-review-20260827-02", acknowledged_at=datetime.now(UTC).isoformat())) + "\n", encoding="utf-8")
    receipt_path.write_text(json.dumps(_capacity_receipt(datetime.now(UTC).isoformat())) + "\n", encoding="utf-8")
    accepted = value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0, retry_disclosure_ack=second_ack)
    assert accepted == [event]
    assert runner.provider_contacts == 3
    journal = value._read_journal(work)
    retry_intents = [row for row in journal if row["event"] == "retry-intent"]
    assert [row["retry_disclosure_sha256"] for row in retry_intents] == [pause["retry_disclosure_sha256"], second_pause["retry_disclosure_sha256"]]
    assert all(row["retry_capacity_proof_sha256"] != row["prior_capacity_proof_sha256"] for row in retry_intents)
    assert not (work / value.CLAIM).exists()


def test_retry_ack_rejects_placeholder_and_mismatched_disclosure(tmp_path: Path):
    value = module()
    disclosure = tmp_path / "retry.json"
    disclosure.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="non-placeholder"):
        value.make_retry_disclosure_ack(disclosure, acknowledgement_id="placeholder", acknowledged_at=datetime.now(UTC).isoformat())


def test_initial_intent_observed_at_must_match_its_capacity_proof(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 179, "item_id": "item", "arm_id": "compact_analytic", "repetition": 1}
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", "sequence": 178})
    receipt = _capacity_receipt()
    _, digest = value._proof(work, 179, receipt)
    value._append(work / value.JOURNAL, {"event": "attempt-intent", "sequence": 179, "capacity_proof_sha256": digest, "observed_at": "2020-01-01T00:00:00+00:00"})
    with pytest.raises(ValueError, match="does not match its capacity proof"):
        value._accepted(work, [event], {"sequence": 178})


def test_cross_batch_retry_recovery_uses_latest_retry_intent_and_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    event = {"sequence": 179, "item_id": "item", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", "sequence": 178})
    first = _capacity_receipt((datetime.now(UTC) - timedelta(seconds=10)).isoformat())
    _, first_digest = value._proof(work, 179, first)
    value._append(work / value.JOURNAL, {"event": "attempt-intent", "sequence": 179, "capacity_proof_sha256": first_digest, "observed_at": first["observed_at"]})
    batch_one = _capacity_receipt((datetime.now(UTC) - timedelta(seconds=5)).isoformat())
    _, batch_one_digest = value._proof(work, 179, batch_one)
    latest = _capacity_receipt(datetime.now(UTC).isoformat())
    _, latest_digest = value._proof(work, 179, latest)
    first_disclosure, disclosure_digest = "a" * 64, "b" * 64
    ack_root = work / value.RETRY_ACKS
    ack_root.mkdir()
    first_ack = ack_root / f"{first_disclosure}.json"
    ack = ack_root / f"{disclosure_digest}.json"
    first_ack.write_text("{}\n", encoding="utf-8")
    ack.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(value, "_validate_retry_ack", lambda *args: {})
    value._append(work / value.JOURNAL, {"event": "retry-intent", "sequence": 179, "prior_capacity_proof_sha256": first_digest, "retry_capacity_proof_sha256": batch_one_digest, "retry_disclosure_sha256": first_disclosure, "retry_ack_sha256": value.sha(first_ack), "observed_at": batch_one["observed_at"]})
    value._append(work / value.JOURNAL, {"event": "retry-intent", "sequence": 179, "prior_capacity_proof_sha256": batch_one_digest, "retry_capacity_proof_sha256": latest_digest, "retry_disclosure_sha256": disclosure_digest, "retry_ack_sha256": value.sha(ack), "observed_at": latest["observed_at"]})
    recovery_path = value._materialize_unresolved_recovery(work, [event], value._read_journal(work))
    assert recovery_path is not None
    record = value.read_json(recovery_path)["attempts"][0]
    assert record["active_intent_kind"] == "retry-intent"
    assert record["active_capacity_proof_sha256"] == latest_digest
    assert record["retry_authorization"] == {
        "prior_capacity_proof_sha256": batch_one_digest,
        "retry_disclosure_sha256": disclosure_digest,
        "retry_ack_sha256": value.sha(ack),
    }


def test_paused_concurrent_or_crash_left_claim_blocks_resume_without_unlink(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    event = {**event, "arm_id": "hbq_short_story_batch32"}
    disclosure = value.read_json(work / value.DISCLOSURE)
    disclosure["cells"][0]["arm_id"] = event["arm_id"]
    disclosure["cells"][0]["payload"]["provider_payloads"][0]["question_ids"] = ["q-1"]
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    value._event_disclosure = lambda *_args: disclosure["cells"][0]
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(_RetryFakeRunner(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    claim = value._claim(work, tmp_path, event)
    before = claim.read_bytes()
    with pytest.raises(ValueError, match="Exclusive v6 claim"):
        value._settle_one(_RetryFakeRunner(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert claim.read_bytes() == before


def test_paused_current_orphan_run_json_is_rejected_before_resume_dispatch(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    event = {**event, "arm_id": "hbq_short_story_batch32"}
    disclosure = value.read_json(work / value.DISCLOSURE)
    disclosure["cells"][0]["arm_id"] = event["arm_id"]
    disclosure["cells"][0]["payload"]["provider_payloads"][0]["question_ids"] = ["q-1"]
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    value._event_disclosure = lambda *_args: disclosure["cells"][0]
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    runner = _RetryFakeRunner()
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    target = value._output_path(work, event)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="orphan run.json"):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert runner.provider_contacts == 1


def test_paused_hbq_all_accepted_checkpoints_without_score_are_rejected(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    event = {**event, "arm_id": "hbq_short_story_batch32"}
    disclosure = value.read_json(work / value.DISCLOSURE)
    cell = disclosure["cells"][0]
    cell["arm_id"] = event["arm_id"]
    base = cell["payload"]["provider_payloads"][0]
    cell["payload"]["provider_payloads"] = [
        {**base, "batch": batch, "question_ids": [f"q-{batch}"]}
        for batch in range(1, 7)
    ]
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    value._event_disclosure = lambda *_args: cell
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    runner = _RetryFakeRunner()
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    responses = value._output_path(work, event).parent / "responses"
    for batch in range(1, 7):
        (responses / f"batch-{batch:04d}.json").write_text(json.dumps({"accepted_attempt": 1, "question_ids": [f"q-{batch}"], "normalized_verdicts": [{"question_id": f"q-{batch}"}]}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="all accepted batch checkpoints"):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert runner.provider_contacts == 1


def test_paused_same_receipt_without_retry_ack_leaves_journal_and_output_unchanged(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    event = {**event, "arm_id": "hbq_short_story_batch32"}
    disclosure = value.read_json(work / value.DISCLOSURE)
    disclosure["cells"][0]["arm_id"] = event["arm_id"]
    disclosure["cells"][0]["payload"]["provider_payloads"][0]["question_ids"] = ["q-1"]
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    value._event_disclosure = lambda *_args: disclosure["cells"][0]
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    runner = _RetryFakeRunner()
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    before = {path.relative_to(work).as_posix(): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    with pytest.raises(ValueError, match="retry disclosure acknowledgement"):
        value._settle_one(runner, {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    after = {path.relative_to(work).as_posix(): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    assert after == before
    assert runner.provider_contacts == 1


def test_paused_partial_manifest_and_terminal_rejection_remain_resumable(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    event = {**event, "arm_id": "hbq_short_story_batch32"}
    disclosure = value.read_json(work / value.DISCLOSURE)
    disclosure["cells"][0]["arm_id"] = event["arm_id"]
    disclosure["cells"][0]["payload"]["provider_payloads"][0]["question_ids"] = ["q-1"]
    (work / value.DISCLOSURE).write_text(json.dumps(disclosure) + "\n", encoding="utf-8")
    value._event_disclosure = lambda *_args: disclosure["cells"][0]
    (work / value.DISCLOSURE_ACK).write_text(json.dumps(value.make_disclosure_ack(work / value.DISCLOSURE)) + "\n", encoding="utf-8")
    with pytest.raises(value._load_hbq_runner().RetryDisclosurePause):
        value._settle_one(_RetryFakeRunner(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    target = value._output_path(work, event)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"run_id": "partial", "config_sha256": "a" * 64, "configuration": {}}) + "\n", encoding="utf-8")
    value._require_paused_cell_resumable(work, event)


@pytest.mark.parametrize("arm_id", ["compact_analytic", "hbq_short_story_batch32"])
def test_journal_rejects_tampered_provider_contact_count(tmp_path: Path, arm_id: str):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    admission = {"sequence": 178}
    event = {"sequence": 179, "item_id": "item", "arm_id": arm_id, "repetition": 1}
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", **admission})
    receipt = _capacity_receipt()
    _, digest = value._proof(work, 179, receipt)
    value._append(work / value.JOURNAL, {"event": "attempt-intent", "sequence": 179, "capacity_proof_sha256": digest, "observed_at": receipt["observed_at"]})
    output = value._output_path(work, event)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("{}\n", encoding="utf-8")
    responses = output.parent / "responses"
    responses.mkdir()
    if arm_id == "hbq_short_story_batch32":
        for batch in range(1, 7):
            (responses / f"batch-{batch:04d}.json").write_text('{"accepted_attempt": 1}\n', encoding="utf-8")
    else:
        (responses / "batch-0001.attempt-0001.message.json").write_text("{}\n", encoding="utf-8")
    value._append(work / value.JOURNAL, {"event": "provider-contacts", "sequence": 179, "capacity_proof_sha256": digest, "recorded_provider_contacts": 999})
    value._append(work / value.JOURNAL, {"event": "completed", "sequence": 179, "capacity_proof_sha256": digest, "output_sha256": value.sha(output)})
    with pytest.raises(ValueError, match="provider-contact evidence"):
        value._accepted(work, [event], admission)


def test_orphan_output_is_rejected_before_claim_or_intent(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    orphan = value._output_path(work, event)
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="orphan output adoption"):
        value._settle_one(_SuccessfulFakeRunner(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert not (work / value.CLAIM).exists()
    assert len(value._read_journal(work)) == 1


def test_completed_journal_order_is_true_contiguous_prefix(tmp_path: Path):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    admission = {"sequence": 178}
    schedule = [{"sequence": 179, "item_id": "a", "arm_id": "compact_analytic", "repetition": 1}, {"sequence": 180, "item_id": "b", "arm_id": "compact_analytic", "repetition": 1}]
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", **admission})
    for event in schedule:
        receipt = _capacity_receipt()
        _, digest = value._proof(work, event["sequence"], receipt)
        value._append(work / value.JOURNAL, {"event": "attempt-intent", "sequence": event["sequence"], "capacity_proof_sha256": digest, "observed_at": receipt["observed_at"]})
        output = value._output_path(work, event)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("{}\n", encoding="utf-8")
        if event["sequence"] == 180:
            value._append(work / value.JOURNAL, {"event": "completed", "sequence": 180, "capacity_proof_sha256": digest, "output_sha256": value.sha(output)})
            with pytest.raises(ValueError, match="ordered prefix"):
                value._accepted(work, schedule, admission)
            break


def test_nested_work_root_is_rejected(tmp_path: Path):
    value = module()
    source, closed, v4 = (tmp_path / name for name in ("source", "closed", "v4"))
    for path in (source, closed, v4):
        path.mkdir()
    v5 = tmp_path / "v5.json"
    v5.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="disjoint"):
        value._roots(source, closed, v4, v5, source / "nested-work")


def test_missing_sibling_work_root_is_allowed_after_ancestry_validation(tmp_path: Path):
    value = module()
    source, closed, v4 = (tmp_path / name for name in ("source", "closed", "v4"))
    for path in (source, closed, v4):
        path.mkdir()
    v5 = tmp_path / "v5.json"
    v5.write_text("{}\n", encoding="utf-8")
    work = tmp_path / "fresh-v6-work"
    roots = value._roots(source, closed, v4, v5, work)
    assert roots[-1] == work
    assert not work.exists()


def test_reparse_capacity_proofs_and_runs_are_rejected_before_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    (work / value.PROOFS).mkdir()
    (work / "runs").mkdir()
    original = value._is_reparse

    def redirected(path: Path) -> bool:
        return path.name in {value.PROOFS, "runs"} or original(path)

    monkeypatch.setattr(value, "_is_reparse", redirected)
    with pytest.raises(ValueError, match="reparse point"):
        value._proof(work, 179, _capacity_receipt())
    with pytest.raises(ValueError, match="reparse point"):
        value._output_path(work, {"item_id": "x", "arm_id": "compact_analytic", "repetition": 1})


def test_nested_source_and_runtime_reparse_entries_are_rejected_before_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    source = tmp_path / "source"
    nested = source / "inputs" / "item" / "source.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("private prose\n", encoding="utf-8")
    original = value._is_reparse
    monkeypatch.setattr(value, "_is_reparse", lambda candidate: candidate == nested or original(candidate))
    with pytest.raises(ValueError, match="symlink/reparse point"):
        value._external_file_record(nested, source, "artifact")

    runtime = tmp_path / "runtime.py"
    runtime.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(value, "_is_reparse", lambda candidate: candidate == runtime or original(candidate))
    with pytest.raises(ValueError, match="symlink/reparse point"):
        value._runtime_file(runtime, require_tracked=False)


def test_ambiguous_contact_is_bounded_and_never_resent(tmp_path: Path):
    value = module()
    work, admission, receipt_path, event = _fake_epoch(value, tmp_path)
    dispatches = 0

    class AmbiguousWorker(_SuccessfulFakeRunner):
        def _run_event(self, *args, **kwargs):
            nonlocal dispatches
            dispatches += 1
            output = work / "runs" / event["item_id"] / event["arm_id"] / "run-01"
            (output / "responses").mkdir(parents=True)
            (output / "responses" / "batch-0001.attempt-0001.message.json").write_text("{}\n", encoding="utf-8")
            raise TimeoutError("contact outcome is ambiguous")

    with pytest.raises(TimeoutError, match="ambiguous"):
        value._settle_one(AmbiguousWorker(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    with pytest.raises(ValueError, match="unresolved attempt intent"):
        value._accepted(work, [event], admission)
    recovery = value.read_json(work / value.UNRESOLVED_RECOVERY)
    assert recovery["status"] == "operator_settlement_required_no_resend"
    assert recovery["attempts"][0]["observed_contact_lower_bound"] == 1
    assert recovery["attempts"][0]["contact_upper_bound"] == 3
    with pytest.raises(ValueError, match="output tree"):
        value._settle_one(AmbiguousWorker(), {}, tmp_path, work, [event], admission, [], event, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert dispatches == 1


def test_expired_receipt_after_clean_checkpoint_leaves_next_cell_unclaimed(tmp_path: Path):
    value = module()
    work, admission, receipt_path, first = _fake_epoch(value, tmp_path)
    second = {**first, "sequence": 180, "item_id": "test-item-two"}
    accepted = value._settle_one(_SuccessfulFakeRunner(), {}, tmp_path, work, [first, second], admission, [], first, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    receipt_path.write_text(json.dumps(_capacity_receipt((datetime.now(UTC) - timedelta(seconds=601)).isoformat())) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not current"):
        value._settle_one(_SuccessfulFakeRunner(), {}, tmp_path, work, [first, second], admission, accepted, second, receipt_path, work / value.DISCLOSURE_ACK, 1.0)
    assert not (work / value.CLAIM).exists()
    assert [row["event"] for row in value._read_journal(work)] == ["admitted-prefix", "attempt-intent", "provider-contacts", "completed"]


def test_execute_reports_capacity_expiry_pause_at_the_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    evidence = tmp_path / "capacity.json"
    ack = work / value.DISCLOSURE_ACK
    ack.write_text("{}\n", encoding="utf-8")
    first = {"sequence": 179, "item_id": "first", "arm_id": "compact_analytic", "repetition": 1}
    second = {"sequence": 180, "item_id": "second", "arm_id": "compact_analytic", "repetition": 1}
    monkeypatch.setattr(value, "_external", lambda path, **kwargs: Path(path))
    monkeypatch.setattr(value, "_verify_prepared", lambda *args: ({"runtime": {}}, [first, second], {"sequence": 178}))
    monkeypatch.setattr(value, "_accepted", lambda *args: [first])
    monkeypatch.setattr(value, "validate_capacity_evidence", lambda *args, **kwargs: {})
    monkeypatch.setattr(value, "_validate_disclosure_ack", lambda *args: {})
    monkeypatch.setattr(value, "_require_clean_pushed", lambda: None)
    monkeypatch.setattr(value, "_load_successor_runner", lambda: object())
    monkeypatch.setattr(value, "read_json", lambda *args: {"contract": {}})
    monkeypatch.setattr(value, "_runtime_projection", lambda *args: {})
    monkeypatch.setattr(value, "_settle_one", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("Capacity evidence is not current")))
    monkeypatch.setattr(value, "_journaled_provider_contacts", lambda *args: 1)
    monkeypatch.setattr(value, "_accounting", lambda schedule, accepted: {"accepted_cells": len(accepted)})
    result = value.execute(source, tmp_path / "closed", tmp_path / "v4", tmp_path / "v5.json", work, evidence, allow_remote=True, disclosure_ack=ack)
    assert result["paused"] == "capacity_receipt_expired_after_clean_checkpoint"
    assert result["completed"] == 1
    assert result["remaining"] == 1
    assert result["next_sequence"] == 180


def test_public_execute_reports_retry_pause_then_forwards_retry_ack_on_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    evidence = tmp_path / "capacity.json"
    ack = work / value.DISCLOSURE_ACK
    retry_ack = work / "retry-disclosure-acknowledgements" / ("a" * 64 + ".json")
    ack.write_text("{}\n", encoding="utf-8")
    event = {"sequence": 179, "item_id": "first", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", "sequence": 178})
    calls: list[Path | None] = []
    monkeypatch.setattr(value, "_external", lambda path, **kwargs: Path(path))
    monkeypatch.setattr(value, "_verify_prepared", lambda *args: ({"runtime": {}}, [event], {"sequence": 178}))
    monkeypatch.setattr(value, "_accepted", lambda *args: [])
    monkeypatch.setattr(value, "validate_capacity_evidence", lambda *args, **kwargs: _capacity_receipt())
    monkeypatch.setattr(value, "_validate_disclosure_ack", lambda *args: {})
    monkeypatch.setattr(value, "_validate_retry_ack", lambda *args: {})
    monkeypatch.setattr(value, "_require_clean_pushed", lambda: None)
    monkeypatch.setattr(value, "_load_successor_runner", lambda: object())
    monkeypatch.setattr(value, "read_json", lambda *args: {"contract": {}})
    monkeypatch.setattr(value, "_runtime_projection", lambda *args: {})
    monkeypatch.setattr(value, "_journaled_provider_contacts", lambda *args: 1)
    monkeypatch.setattr(value, "_accounting", lambda schedule, accepted: {"accepted_cells": len(accepted)})

    def paused_once(*args, **kwargs):
        calls.append(kwargs.get("retry_disclosure_ack", args[-1]))
        if len(calls) == 1:
            value._append(work / value.JOURNAL, {"event": "retry-disclosure-pause", "sequence": 179, "retry_disclosure_sha256": "a" * 64})
            raise value._load_hbq_runner().RetryDisclosurePause("pause")
        return [event]

    monkeypatch.setattr(value, "_settle_one", paused_once)
    first = value.execute(source, tmp_path / "closed", tmp_path / "v4", tmp_path / "v5.json", work, evidence, allow_remote=True, disclosure_ack=ack)
    assert first["paused"] == "retry_disclosure_required_before_changed_payload"
    second = value.execute(source, tmp_path / "closed", tmp_path / "v4", tmp_path / "v5.json", work, evidence, allow_remote=True, disclosure_ack=ack, retry_disclosure_ack=retry_ack)
    assert second["remaining"] == 0
    assert calls == [None, retry_ack]


def test_expired_receipt_with_later_retry_pause_reports_pause_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    ack = work / value.DISCLOSURE_ACK
    ack.write_text("{}\n", encoding="utf-8")
    first = {"sequence": 179, "item_id": "first", "arm_id": "compact_analytic", "repetition": 1}
    paused = {"sequence": 180, "item_id": "paused", "arm_id": "hbq_short_story_batch32", "repetition": 1}
    value._append(work / value.JOURNAL, {"event": "admitted-prefix", "sequence": 178})
    value._append(work / value.JOURNAL, {"event": "retry-disclosure-pause", "sequence": 180, "retry_disclosure_sha256": "a" * 64})
    evidence = tmp_path / "expired-capacity.json"
    evidence.write_text(json.dumps(_capacity_receipt("2020-01-01T00:00:00+00:00")) + "\n", encoding="utf-8")
    before = {path.relative_to(work).as_posix(): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    monkeypatch.setattr(value, "_external", lambda path, **kwargs: Path(path))
    monkeypatch.setattr(value, "_verify_prepared", lambda *args: ({"runtime": {}}, [first, paused], {"sequence": 178}))
    monkeypatch.setattr(value, "_accepted", lambda *args: [first])
    monkeypatch.setattr(value, "_journaled_provider_contacts", lambda *args: 1)
    monkeypatch.setattr(value, "_accounting", lambda schedule, accepted: {"accepted_cells": len(accepted)})
    monkeypatch.setattr(value, "_settle_one", lambda *args, **kwargs: pytest.fail("paused stale state must not dispatch"))
    result = value.execute(source, tmp_path / "closed", tmp_path / "v4", tmp_path / "v5.json", work, evidence, allow_remote=True, disclosure_ack=ack)
    after = {path.relative_to(work).as_posix(): path.read_bytes() for path in work.rglob("*") if path.is_file()}
    assert result["paused"] == "retry_disclosure_required_before_changed_payload"
    assert result["next_sequence"] == 180
    assert result["paused"] != "capacity_receipt_expired_after_clean_checkpoint"
    assert after == before


@pytest.mark.parametrize("name", ["preflight-disclosure.json", "v6-binding.json", "admitted-sequence-178.json", "schedule.jsonl", "execution-journal.jsonl", "disclosure-acknowledgement.json", "retry-disclosures", "retry-disclosure-acknowledgements", "capacity-proofs", "runs"])
def test_prepared_work_tree_rejects_reparse_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str):
    value = module()
    work = tmp_path / "work"
    work.mkdir()
    path = work / name
    if name in {value.PROOFS, "runs"}:
        path.mkdir()
    else:
        path.write_text("{}\n", encoding="utf-8")
    original = value._is_reparse
    monkeypatch.setattr(value, "_is_reparse", lambda candidate: candidate.name == name or original(candidate))
    with pytest.raises(ValueError, match="work root contains a symlink/reparse entry"):
        value._assert_plain_work_tree(work)
