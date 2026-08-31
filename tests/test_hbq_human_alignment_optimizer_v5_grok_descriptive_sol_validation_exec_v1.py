from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-grok-descriptive-sol-validation-exec-v1"
SOURCE = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-live-856451a-20260830a")
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("_v5_sol_followup", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value; spec.loader.exec_module(value)
    return value


def route():
    identity = {"version": 1, "artifacts": [{"path": "fixture", "sha256": "f" * 64}]}
    return {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True, "allowed_payload_classes": ["public_repo"], "codex_command": ["codex-fixture.exe"], "codex_command_identity": identity, "cli_version_identity": identity, "auth_status_identity": identity, "codex_cli_version": "fixture", "command": ["python-fixture.exe", str(module()._load_v3().CODEX_ADAPTER_PATH)], "command_identity": identity, "cost_evidence": {"evidence_hash": "e" * 64, "checked_at": "2026-08-30T00:00:00Z", "expires_at": "2026-09-01T00:00:00Z"}, "auth_receipt_hash": "1" * 64, "timeout_seconds": 60}


class Broker:
    def __init__(self, _root: Path): self.route = route()
    def _load_registry_live(self): return {"version": 1, "routes": [self.route]}
    def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence): assert candidate == self.route and verify_command_identity and validate_current_evidence


def factory(root: Path): return Broker(root)


def events(answer: str, token: str) -> bytes:
    stream = [{"type": "thread.started", "thread_id": "thread-" + token}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": answer}}, {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
    return b"".join(json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in stream)


def runner(**kwargs):
    root, prompt = kwargs["output_dir"], kwargs["prompt"]
    (root / "responses").mkdir(); kwargs["before_provider_attempt"]()
    score = 2 if hashlib.sha256(prompt.encode()).hexdigest().startswith("d46") or hashlib.sha256(prompt.encode()).hexdigest().startswith("ab2") else 3
    names = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
    answer = json.dumps({"scores": {name: score for name in names}, "evidence": {name: "fixture" for name in names}, "coverage": {name: True for name in names}}, separators=(",", ":"))
    response = root / "responses" / "batch-0001.attempt-0001.message.json"; response.write_text(answer, encoding="utf-8")
    raw = events(answer, hashlib.sha256(prompt.encode()).hexdigest()[:12]); event_path = root / "responses" / "batch-0001.attempt-0001.events.jsonl"; event_path.write_bytes(raw)
    stderr = root / "raw-codex-stderr.bin"; stderr.write_bytes(b"")
    v3 = module()._load_v3()
    return answer, {"command": v3._expected_codex_command(kwargs["executable"], root), "provider_artifacts": {"codex_events": {"path": event_path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, "codex_stderr": {"path": stderr.name, "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()}}}


def prepared(tmp_path: Path):
    value = module(); result = value.prepare_all(output_root=tmp_path / "roots", source_root=SOURCE, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)
    return value, tmp_path / "roots", result


def write_json(value, path: Path, payload: dict):
    path.write_bytes(value.canonical(payload))


def execute_all(value, output: Path, queue_root: Path) -> None:
    for row in value.ROWS:
        value.execute_one(output_root=output, cell_id=row["cell_id"], queue_root=queue_root, authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)


def test_prepare_four_pinned_roots_without_contact(tmp_path: Path):
    value, output, result = prepared(tmp_path)
    assert result == {"cells": 4, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "authority": "descriptive_validation_only"}
    assert {item.name for item in output.iterdir()} == {row["cell_id"] for row in value.ROWS}
    assert [hashlib.sha256((output / row["cell_id"] / "outbound-payload.json").read_bytes()).hexdigest() for row in value.ROWS] == [row["payload_sha256"] for row in value.ROWS]


def test_all_four_bind_production_order_raw_messages_and_project(tmp_path: Path):
    value, output, _ = prepared(tmp_path)
    for row in value.ROWS:
        outcome = value.execute_one(output_root=output, cell_id=row["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
        assert outcome["native_endpoint_contact_cardinality"] == "unproven"
    projection = value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)
    assert projection["metrics"] == pytest.approx({"candidate-102cc7f06c9a99a7": 7/6, "candidate-69720ac6257db007": 13/18})
    assert projection["authority"]["selection"] == "none" and projection["authority"]["endpoint_pooling"] == "forbidden"
    receipt = json.loads((output / value.ROWS[0]["cell_id"] / "execution-receipt.json").read_text())
    assert receipt["final_response_sha256"] == hashlib.sha256((output / value.ROWS[0]["cell_id"] / "raw-codex-final-response.bin").read_bytes()).hexdigest()


def test_tamper_swap_partial_reparse_and_no_resend_are_rejected(tmp_path: Path):
    value, output, _ = prepared(tmp_path); first, second = value.ROWS[:2]
    value.execute_one(output_root=output, cell_id=first["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
    with pytest.raises(ValueError, match="no resend"):
        value.execute_one(output_root=output, cell_id=first["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
    root = output / second["cell_id"]; (root / "orphan.bin").write_bytes(b"bad")
    with pytest.raises(ValueError, match="inventory"):
        value.execute_one(output_root=output, cell_id=second["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
    (root / "orphan.bin").unlink(); (root / "outbound-payload.json").write_bytes(b"{}")
    with pytest.raises(ValueError, match="prepared bindings"):
        value.execute_one(output_root=output, cell_id=second["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)


def test_postlaunch_partial_is_terminal_and_swapped_raw_response_is_rejected(tmp_path: Path):
    value, output, _ = prepared(tmp_path); first, second, third, fourth = value.ROWS
    def partial(**kwargs):
        (kwargs["output_dir"] / "responses").mkdir(); kwargs["before_provider_attempt"](); raise OSError("fixture postlaunch")
    partial_root = tmp_path / "partial"; value.prepare_all(output_root=partial_root, source_root=SOURCE, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)
    terminal = value.execute_one(output_root=partial_root, cell_id=third["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=partial)
    assert terminal["state"] == "reconcile_required_after_process_launch"
    with pytest.raises(ValueError, match="no resend"):
        value.execute_one(output_root=partial_root, cell_id=third["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
    for row in (first, second, third, fourth):
        value.execute_one(output_root=output, cell_id=row["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
    (output / second["cell_id"] / "raw-codex-final-response.bin").write_bytes((output / fourth["cell_id"] / "raw-codex-final-response.bin").read_bytes())
    with pytest.raises(ValueError, match="receipt evidence"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)


def test_projection_rejects_score_payload_and_duplicate_identity_mutations(tmp_path: Path):
    value, output, _ = prepared(tmp_path)
    for row in value.ROWS:
        value.execute_one(output_root=output, cell_id=row["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=runner)
    first, second = value.ROWS[:2]; first_root, second_root = output / first["cell_id"], output / second["cell_id"]
    receipt_path = first_root / "execution-receipt.json"; original = receipt_path.read_bytes(); receipt = json.loads(original); receipt["human_score_projection"]["scores"]["Relevance"] = 0
    receipt_path.write_bytes(value.canonical(receipt))
    with pytest.raises(ValueError, match="receipt evidence"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)
    receipt_path.write_bytes(original)
    payload = (second_root / "outbound-payload.json"); payload_original = payload.read_bytes(); payload.write_bytes(b"{}")
    with pytest.raises(ValueError, match="prepared source"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)
    payload.write_bytes(payload_original)
    second_receipt = second_root / "execution-receipt.json"; second_original = second_receipt.read_bytes(); changed = json.loads(second_original); changed["identity"] = json.loads(original)["identity"]
    second_receipt.write_bytes(value.canonical(changed))
    with pytest.raises(ValueError, match="duplicate or absent"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)


def test_projection_rejects_semantic_provenance_and_local_first_mutations(tmp_path: Path):
    value, output, _ = prepared(tmp_path)
    execute_all(value, output, tmp_path / "queue")
    root = output / value.ROWS[0]["cell_id"]
    cases = (("disclosure.json", lambda v: v.__setitem__("destination", "other")), ("disclosure.json", lambda v: v.__setitem__("tools_enabled", True)), ("disclosure.json", lambda v: v.__setitem__("provider_calls_made", 1)), ("authorization-acknowledgement.json", lambda v: v.__setitem__("acknowledgement_sha256", "b" * 64)), ("zero-charge-route-proof.json", lambda v: v.__setitem__("zero_charge_only", False)), ("zero-charge-route-proof.json", lambda v: v.__setitem__("paid_fallback_forbidden", False)), ("prepared.json", lambda v: v["source"].__setitem__("public_result_commit", "0" * 40)), ("execution-receipt.json", lambda v: v["identity"].__setitem__("provider", "other")), ("execution-receipt.json", lambda v: v.__setitem__("process_launches", 2)), ("execution-receipt.json", lambda v: v.__setitem__("route_evidence", {"forged": True})))
    for name, mutate in cases:
        path = root / name; original = path.read_bytes(); value_json = json.loads(original); mutate(value_json); path.write_bytes(value.canonical(value_json))
        with pytest.raises(ValueError):
            value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)
        path.write_bytes(original)
    extra = output / "unexpected.bin"; extra.write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="output-root inventory"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)


def test_projection_rejects_coherent_route_evidence_and_command_forgery(tmp_path: Path):
    value, output, _ = prepared(tmp_path)
    execute_all(value, output, tmp_path / "queue")
    root = output / value.ROWS[0]["cell_id"]
    prepared_path = root / "prepared.json"; proof_path = root / "zero-charge-route-proof.json"
    receipt_path = root / "execution-receipt.json"; intent_path = root / "launch-intent.json"

    prepared_json = json.loads(prepared_path.read_text()); proof = json.loads(proof_path.read_text()); receipt = json.loads(receipt_path.read_text())
    forged_evidence = {"checked_at": "never", "zero_charge": False, "evidence_hash": "0" * 64}
    prepared_json["route_evidence"] = forged_evidence; proof["route_evidence"] = forged_evidence; receipt["route_evidence"] = forged_evidence
    prepared_json["route_proof_sha256"] = value.sha(proof)
    write_json(value, proof_path, proof); write_json(value, prepared_path, prepared_json)
    intent = json.loads(intent_path.read_text()); intent["prepared_sha256"] = value.sha(prepared_json); write_json(value, intent_path, intent)
    receipt["launch_intent_sha256"] = value.sha(intent); write_json(value, receipt_path, receipt)
    with pytest.raises(ValueError, match="prepared source"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)

    command_root = tmp_path / "command"; command_root.mkdir()
    value, output, _ = prepared(command_root)
    execute_all(value, output, tmp_path / "command" / "queue")
    root = output / value.ROWS[0]["cell_id"]
    prepared_path = root / "prepared.json"; proof_path = root / "zero-charge-route-proof.json"
    settings_path = root / "effective-settings.json"; record_path = root / "codex-record.json"
    receipt_path = root / "execution-receipt.json"; intent_path = root / "launch-intent.json"
    prepared_json = json.loads(prepared_path.read_text()); proof = json.loads(proof_path.read_text()); settings = json.loads(settings_path.read_text())
    forged_route = dict(proof["route"]); forged_route["name"] = "forged-route"; forged_route["codex_command"] = ["forged-codex.exe"]
    forged_identity = {"version": 1, "artifacts": [{"path": "forged", "sha256": "0" * 64}]}
    forged_route["codex_command_identity"] = forged_identity
    proof["route"] = forged_route; prepared_json["route_command"] = "forged-codex.exe"; prepared_json["route_proof_sha256"] = value.sha(proof)
    settings["route_name"] = forged_route["name"]; settings["codex_command_identity"] = forged_identity
    write_json(value, proof_path, proof); write_json(value, prepared_path, prepared_json); write_json(value, settings_path, settings)
    record = json.loads(record_path.read_text()); record["command"] = value._load_v3()._expected_codex_command("forged-codex.exe", root); write_json(value, record_path, record)
    intent = json.loads(intent_path.read_text()); intent["prepared_sha256"] = value.sha(prepared_json); write_json(value, intent_path, intent)
    receipt = json.loads(receipt_path.read_text()); receipt["effective_settings_sha256"] = value.sha(settings); receipt["launch_intent_sha256"] = value.sha(intent); write_json(value, receipt_path, receipt)
    with pytest.raises(ValueError, match="prepared source"):
        value.project_descriptive(output_root=output, queue_root=tmp_path / "command" / "queue", authorization_acknowledgement_sha256=ACK, broker_factory=factory)


def test_real_reparse_payload_is_rejected_before_callback(tmp_path: Path):
    value, output, _ = prepared(tmp_path); row = value.ROWS[0]; root = output / row["cell_id"]
    target, replacement = root / "outbound-payload.json", tmp_path / "replacement.bin"; replacement.write_bytes(target.read_bytes()); target.unlink()
    try:
        os.symlink(replacement, target)
    except (NotImplementedError, OSError):
        pytest.skip("host cannot create a test symlink")
    calls = []
    def never(**kwargs): calls.append(kwargs); raise AssertionError("must not launch")
    with pytest.raises(ValueError, match="unsafe/reparsed"):
        value.execute_one(output_root=output, cell_id=row["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=ACK, allow_remote=True, broker_factory=factory, call_codex=never)
    assert calls == []


def test_runtime_has_no_optimizer_dependency():
    source = (PACKAGE / "executor.py").read_text(encoding="utf-8").lower()
    assert "import dspy" not in source and "import optuna" not in source
