from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-lean-training-verifier-v1" / "verifier.py"
COLLECTOR_PATH = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-lean-training-exec-v1" / "executor.py"
DOCUMENTS = Path.home() / "Documents"
FROZEN = DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json"
HANNA = DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


class _SyntheticExecution:
    def __init__(self, collector, exec_v1, exec_v3):
        self.collector, self.exec_v1, self.exec_v3 = collector, exec_v1, exec_v3
        self.grok_identity = {"version": 1, "fixture": "grok"}
        self.sol_identity = {"version": 1, "fixture": "sol"}

    def validate_live_grok_route(self, *_args, **_kwargs):
        route = {"name": "grok-build-grok-4.6", "grok_command": ["fixture-grok"], "timeout_seconds": 1,
                 "grok_cli_version": "fixture-grok 1", "grok_command_identity": self.grok_identity}
        evidence = {"grok_cli_version": route["grok_cli_version"], "grok_command_identity_sha256": self.collector.sha256(self.collector.canonical(self.grok_identity))}
        return route, evidence

    def validate_live_sol_route(self, *_args, **_kwargs):
        route = {"name": "codex-chatgpt-gpt-5.6-sol", "codex_command": ["fixture-codex"], "timeout_seconds": 1,
                 "codex_cli_version": "fixture-codex 1", "codex_command_identity": self.sol_identity}
        evidence = {"codex_cli_version": route["codex_cli_version"], "codex_command_identity_sha256": self.collector.sha256(self.collector.canonical(self.sol_identity))}
        return route, evidence

    def _envelope_identity(self, response: bytes, record: dict):
        return self.exec_v1._envelope_identity(response, record)

    def _codex_event_projection(self, events: bytes, parser):
        return self.exec_v3._codex_event_projection(events, parser)

    def _load_parse_codex_events(self):
        return self.exec_v3._load_parse_codex_events()


def _identity(row: dict, index: int) -> dict:
    route = row["route"]
    if row["route_name"] == "grok_primary":
        return {"provider": route["provider"], "route_name": route["route_name"], "requested_model": "grok-4.6",
                "requested_reasoning_effort": "high", "effective_model": "grok-4.6-build", "provider_reported_model": "grok-4.6-build",
                "identity_evidence": "requested_and_cli_envelope_reported_model_reasoning_unattested", "reasoning_attested": False,
                "transport_identity": "grok_build_saved_session_subscription_tool_free_v1", "contact_id": f"request-{index}", "session_id": f"session-{index}"}
    thread = f"thread-{index}"
    return {"provider": route["provider"], "route_name": route["route_name"], "requested_model": "gpt-5.6-sol",
            "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None,
            "identity_evidence": "requested_and_local_effective_settings_only_stderr_labels_may_be_absent_not_provider_attested",
            "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3",
            "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread}", "session_id": f"local-codex-thread-session:{thread}"}


def _structured(row: dict, targets: dict[str, dict[str, float]], dimensions: tuple[str, ...]) -> dict:
    return {"scores": dict(targets[row["item_id"]]), "evidence": {name: "synthetic collector finalizer fixture" for name in dimensions}, "coverage": {name: True for name in dimensions}}


def _grok_call(row: dict, index: int, targets: dict[str, dict[str, float]], dimensions: tuple[str, ...], execution: _SyntheticExecution):
    def call(**kwargs):
        kwargs["before_provider_attempt"]()
        identity = _identity(row, index)
        response = _json({"modelUsage": {"grok-4.6-build": {}}, "stopReason": "end_turn", "num_turns": 1,
                          "sessionId": identity["session_id"], "requestId": identity["contact_id"], "structuredOutput": _structured(row, targets, dimensions)})
        responses = kwargs["output_dir"] / "responses"; responses.mkdir()
        prompt = kwargs["prompt"].encode("utf-8")
        (responses / "batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
        (responses / "batch-0001.attempt-0001.grok.envelope.json").write_bytes(response)
        record = {"provider_artifacts": {"grok_envelope": {"path": "responses/batch-0001.attempt-0001.grok.envelope.json", "bytes": len(response), "sha256": _sha(response)}},
                  "cli_version": "fixture-grok 1", "requested": {"model": "grok-4.6", "reasoning_effort": "high"},
                  "reported": {"provider": "grok", "model": "grok-4.6-build"}, "reasoning_attested": False,
                  "request_id_sha256": _sha(identity["contact_id"].encode("utf-8")), "session_id_sha256": _sha(identity["session_id"].encode("utf-8"))}
        return "", record
    return call


def _sol_call(row: dict, index: int, targets: dict[str, dict[str, float]], dimensions: tuple[str, ...], execution: _SyntheticExecution):
    def call(**kwargs):
        kwargs["before_provider_attempt"]()
        identity = _identity(row, index)
        response = _json(_structured(row, targets, dimensions))
        events = b"\n".join((_json({"type": "thread.started", "thread_id": identity["contact_id"].rsplit(":", 1)[1]}).rstrip(), _json({"type": "turn.started"}).rstrip(), _json({"type": "item.completed", "item": {"id": "fixture", "type": "agent_message", "text": response.decode("utf-8")}}).rstrip(), _json({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}).rstrip())) + b"\n"
        responses = kwargs["output_dir"] / "responses"; responses.mkdir()
        (responses / "batch-0001.attempt-0001.events.jsonl").write_bytes(events)
        (responses / "batch-0001.attempt-0001.message.json").write_bytes(response)
        stderr = b""
        (kwargs["output_dir"] / "raw-codex-stderr.bin").write_bytes(stderr)
        command = execution.exec_v3._expected_codex_command("fixture-codex", kwargs["output_dir"])
        record = {"command": command, "provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": _sha(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": 0, "sha256": _sha(stderr)}}, "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}}
        return response.decode("utf-8"), record
    return call


def _genuine_collection(tmp_path: Path):
    verifier = _load(VERIFIER_PATH, "lean_verifier")
    collector = _load(COLLECTOR_PATH, "lean_collector")
    _collector, optimizer, native, exec_v1, exec_v3 = verifier._dependencies()
    schedule, rows = verifier._rows(optimizer, FROZEN, HANNA)
    targets = optimizer._targets(native, rows, frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    execution = _SyntheticExecution(collector, exec_v1, exec_v3)
    collector._load_exec = lambda _route_name: execution
    roots, output = [], tmp_path / "roots"
    for index, row in enumerate(rows):
        payload, task, schema = collector._payload(native, row, frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
        route, evidence = collector._route(execution, row, tmp_path / "queue", None)
        root = output / row["cell_id"]
        collector._prepared_root(native, root, row, schedule, payload, task, schema, evidence, ACK)
        result = collector.execute_one(output_root=output, cell_id=row["cell_id"], queue_root=tmp_path / "queue", frozen_successor_path=FROZEN, hanna_csv_path=HANNA, authorization_acknowledgement_sha256=ACK, allow_remote=True, schedule_loader=lambda **_: schedule, call_grok=_grok_call(row, index, targets, optimizer.DIMENSIONS, execution) if row["route_name"] == "grok_primary" else None, call_codex=_sol_call(row, index, targets, optimizer.DIMENSIONS, execution) if row["route_name"] == "sol_validation" else None)
        assert result["process_launches"] == 1
        roots.append({"cell_id": row["cell_id"], "execution_root": str(root)})
    manifest = collector.emit_collector_receipts(output_path=tmp_path / "collector-receipts.json", frozen_successor_path=FROZEN, hanna_csv_path=HANNA, references=roots, schedule_loader=lambda **_: schedule)
    assert manifest["kind"] == "lean_training_collector_receipts"
    return verifier, tmp_path / "collector-receipts.json", roots


def test_only_collector_finalizers_can_supply_the_full_35_receipt_projection(tmp_path: Path):
    verifier, evidence, roots = _genuine_collection(tmp_path)
    projection = verifier.verify_training_receipts(collection_evidence_path=evidence, frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
    assert projection["geometry"] == {"grok_cells": 25, "sol_cells": 10, "total_cells": 35}
    assert projection["dependencies"]["verifier_source_sha256"] == _sha(VERIFIER_PATH.read_bytes())
    assert projection["sol_evidence_class"] == "local_codex_lifecycle_received_native_contact_unproven"
    first = Path(roots[0]["execution_root"])
    (first / "grok-record.json").write_bytes(_json({}))
    with pytest.raises(ValueError, match="Grok record is empty"):
        verifier.verify_training_receipts(collection_evidence_path=evidence, frozen_successor_path=FROZEN, hanna_csv_path=HANNA)
