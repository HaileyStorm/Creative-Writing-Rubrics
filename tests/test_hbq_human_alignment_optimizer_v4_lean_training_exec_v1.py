from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-lean-training-exec-v1" / "executor.py"
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
HANNA = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
QUEUE = Path(r"C:\Users\Haile\.codex\state\model-work-queue")
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def _module():
    spec = importlib.util.spec_from_file_location("lean_training_exec", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_provider_free_prepares_cover_one_grok_and_one_sol_training_row(tmp_path: Path):
    module = _module()
    schedule = module.training_schedule(frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    cells = [schedule["partitions"]["training"]["grok"][0], schedule["partitions"]["training"]["sol_sprinkled"][0]]
    for row in cells:
        outcome = module.prepare_one(output_root=tmp_path / row["route_name"], cell_id=row["cell_id"], queue_root=QUEUE,
                                     frozen_successor_path=FROZEN, hanna_csv_path=HANNA,
                                     authorization_acknowledgement_sha256=ACK)
        root = tmp_path / row["route_name"] / row["cell_id"]
        assert outcome["provider_calls_made"] == 0
        assert {path.name for path in root.iterdir()} == module.PREPARED_FILES
        prepared = json.loads((root / "prepared.json").read_text(encoding="utf-8"))
        assert prepared["cell"] == row
        assert prepared["request_sha256"] == row["task_payload_sha256"]
        assert not (root / "launch-intent.json").exists()


def test_rejects_nontraining_and_preexisting_or_launched_roots(tmp_path: Path):
    module = _module()
    schedule = module.training_schedule(frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    row = schedule["partitions"]["training"]["grok"][0]
    with pytest.raises(ValueError, match="frozen training"):
        module.training_row(schedule, schedule["partitions"]["grok_development"][0]["cell_id"])
    root = tmp_path / row["cell_id"]
    root.mkdir(parents=True)
    with pytest.raises(ValueError, match="pre-existing"):
        module.prepare_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN,
                           hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK)
    (root / "launch-intent.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="refuses resend"):
        module.execute_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN,
                           hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK, allow_remote=True)


class _FakeExecution:
    def __init__(self, evidence):
        self.evidence = evidence

    def validate_live_grok_route(self, *_args, **_kwargs):
        return {"name": "grok-build-grok-4.6", "grok_command": ["fake"], "timeout_seconds": 1, "grok_cli_version": "fake", "grok_command_identity": {}}, self.evidence

    def validate_live_sol_route(self, *_args, **_kwargs):
        return {"name": "codex-chatgpt-gpt-5.6-sol", "codex_command": ["fake"], "timeout_seconds": 1, "codex_cli_version": "fake", "codex_command_identity": {}}, self.evidence

    @staticmethod
    def _envelope_identity(_response, _record):
        return "request", "session"

    @staticmethod
    def _codex_event_projection(_events, _parser):
        return {"thread_id": "thread"}

    @staticmethod
    def _load_parse_codex_events():
        return lambda _: {}


def test_tampered_schema_and_wrong_ack_never_reach_runner(tmp_path: Path, monkeypatch):
    module = _module()
    schedule = module.training_schedule(frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    row = schedule["partitions"]["training"]["grok"][0]
    module.prepare_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK)
    root = tmp_path / row["cell_id"]
    evidence = json.loads((root / "prepared.json").read_text(encoding="utf-8"))["route_evidence"]
    monkeypatch.setattr(module, "_load_exec", lambda _route: _FakeExecution(evidence))
    calls = []
    with pytest.raises(ValueError, match="response-schema.json"):
        (root / "response-schema.json").write_bytes(b"{}")
        module.execute_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK, allow_remote=True, call_grok=lambda **_: calls.append(True))
    assert calls == []
    (root / "response-schema.json").write_bytes(json.loads((root / "outbound-payload.json").read_text(encoding="utf-8"))["components"]["response_schema"].encode("utf-8"))
    with pytest.raises(ValueError, match="authorization-acknowledgement.json"):
        module.execute_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256="0" * 64, allow_remote=True, call_grok=lambda **_: calls.append(True))
    assert calls == []


def test_synthetic_grok_and_sol_success_persist_required_native_evidence(tmp_path: Path, monkeypatch):
    module = _module()
    schedule = module.training_schedule(frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    rows = [schedule["partitions"]["training"]["grok"][0], schedule["partitions"]["training"]["sol_sprinkled"][0]]
    for row in rows:
        module.prepare_one(output_root=tmp_path / row["route_name"], cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK)
        root = tmp_path / row["route_name"] / row["cell_id"]
        evidence = json.loads((root / "prepared.json").read_text(encoding="utf-8"))["route_evidence"]
        monkeypatch.setattr(module, "_load_exec", lambda _route: _FakeExecution(evidence))
        if row["route_name"] == "grok_primary":
            def grok(**kwargs):
                kwargs["before_provider_attempt"](); response = b'{"modelUsage":{"grok-4.6-build":{}},"requestId":"request","sessionId":"session"}'
                responses = kwargs["output_dir"] / "responses"; responses.mkdir(); (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8"); (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
                return "", {"provider_artifacts": {"grok_envelope": {"path": "responses/batch-0001.attempt-0001.grok.envelope.json", "bytes": len(response), "sha256": module.sha256(response)}}, "cli_version": "fake", "requested": {"model": "grok-4.6", "reasoning_effort": "high"}, "reported": {"provider": "grok", "model": "grok-4.6-build"}, "reasoning_attested": False}
            module.execute_one(output_root=tmp_path / row["route_name"], cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK, allow_remote=True, call_grok=grok)
            required = {"raw-grok-envelope.bin", "grok-record.json", "effective-settings.json", "execution-receipt.json", "result.json"}
        else:
            def sol(**kwargs):
                kwargs["before_provider_attempt"](); responses = kwargs["output_dir"] / "responses"; responses.mkdir(); (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(b"{}\n"); (responses / "batch-0001.attempt-0001.message.json").write_bytes(b"{}"); (kwargs["output_dir"] / "raw-codex-stderr.bin").write_bytes(b"")
                events = b"{}\n"; return "{}", {"provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": module.sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": 0, "sha256": module.sha256(b"")}}}
            module.execute_one(output_root=tmp_path / row["route_name"], cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK, allow_remote=True, call_codex=sol)
            required = {"raw-codex-events.bin", "raw-codex-final-response.bin", "raw-codex-stderr.bin", "codex-record.json", "effective-settings.json", "execution-receipt.json", "result.json"}
        assert required <= {path.name for path in root.iterdir()}


def test_collector_manifest_is_the_verifier_input_not_an_old_projection(tmp_path: Path):
    module = _module()
    schedule = {"schedule_sha256": "a" * 64, "partitions": {"training": {"grok": [{"cell_id": f"g-{i}", "route_name": "grok_primary"} for i in range(25)], "sol_sprinkled": [{"cell_id": f"s-{i}", "route_name": "sol_validation"} for i in range(10)]}}}
    rows = [*schedule["partitions"]["training"]["grok"], *schedule["partitions"]["training"]["sol_sprinkled"]]
    manifest = module.emit_collector_receipts(output_path=tmp_path / "lean-training-collector-receipts.json", frozen_successor_path=FROZEN, hanna_csv_path=HANNA, references=[{"cell_id": row["cell_id"], "execution_root": str(tmp_path / row["cell_id"])} for row in rows], schedule_loader=lambda **_: schedule)
    assert set(manifest) == {"format_version", "study_id", "kind", "collector_executor_sha256", "collector_contract_sha256", "optimizer_sha256", "native_executor_sha256", "schedule_sha256", "stage", "cells"}
    assert manifest["kind"] == "lean_training_collector_receipts"


def test_postlaunch_finalization_error_is_reconcile_required(tmp_path: Path, monkeypatch):
    module = _module()
    schedule = module.training_schedule(frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    row = schedule["partitions"]["training"]["grok"][0]
    module.prepare_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK)
    root = tmp_path / row["cell_id"]
    evidence = json.loads((root / "prepared.json").read_text(encoding="utf-8"))["route_evidence"]
    monkeypatch.setattr(module, "_load_exec", lambda _route: _FakeExecution(evidence))
    def bad_grok(**kwargs):
        kwargs["before_provider_attempt"](); response = b"{}"; responses = kwargs["output_dir"] / "responses"; responses.mkdir(); (responses / "batch-0001.attempt-0001.prompt.txt").write_text(kwargs["prompt"], encoding="utf-8"); (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        return "", {"provider_artifacts": {"grok_envelope": {"path": "unexpected.json", "bytes": len(response), "sha256": module.sha256(response)}}}
    result = module.execute_one(output_root=tmp_path, cell_id=row["cell_id"], queue_root=QUEUE, frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK, allow_remote=True, call_grok=bad_grok)
    assert result["kind"] == "reconcile_required_after_process_launch"
    assert json.loads((root / "result.json").read_text(encoding="utf-8"))["kind"] == "reconcile_required_after_process_launch"
