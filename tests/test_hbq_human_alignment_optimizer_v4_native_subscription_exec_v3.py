from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3"
executor = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v3")
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
AUTH = "d" * 64
LIVE = {**ROOTS, "authorization_acknowledgement_sha256": AUTH, "allow_remote": True}


def sol_route() -> dict:
    identity = {"version": 1, "artifacts": [{"path": "codex-fixture.exe", "sha256": "f" * 64}]}
    return {
        "name": executor.SOL_ROUTE_NAME, "model": "gpt-5.6-sol", "adapter": "codex_exec",
        "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription",
        "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy",
        "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True,
        "allowed_payload_classes": ["public_repo"], "codex_command": ["codex-fixture.exe"],
        "codex_command_identity": identity, "cli_version_identity": identity, "auth_status_identity": identity,
        "codex_cli_version": "codex-cli fixture 1.0", "command": ["python-fixture.exe", str(executor.CODEX_ADAPTER_PATH)],
        "command_identity": identity, "cost_evidence": {"evidence_hash": "e" * 64, "checked_at": "2026-08-29T00:00:00Z", "expires_at": "2026-08-30T00:00:00Z"},
        "auth_receipt_hash": "1" * 64, "timeout_seconds": 60,
    }


class FakeBroker:
    def __init__(self, _root: Path, candidate: dict): self.candidate = candidate
    def _load_registry_live(self): return {"version": 1, "routes": [self.candidate]}
    def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence):
        assert candidate == self.candidate and verify_command_identity and validate_current_evidence


def factory(candidate: dict): return lambda root: FakeBroker(root, candidate)


def final_response() -> str:
    names = ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"]
    return json.dumps({"scores": {name: 3 for name in names}, "evidence": {name: "fixture" for name in names}, "coverage": {name: True for name in names}}, separators=(",", ":"))


def events(*, error: bool = False) -> bytes:
    stream = [
        {"type": "thread.started", "thread_id": "thread-1"}, {"type": "turn.started"},
        {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}},
        {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": final_response()}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    if error: stream.insert(-1, {"type": "error", "error": {"message": "fixture"}})
    return b"".join(json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in stream)


@pytest.fixture(scope="module")
def sol_row():
    parent = executor._load_predecessor()
    return next(row for row in parent.derive_schedule(**ROOTS)["mandatory_development"] if row["route_name"] == "sol_validation")


def callback(raw_events: bytes, stderr: bytes):
    def invoke(**kwargs):
        kwargs["before_provider_attempt"]()
        root = kwargs["output_dir"]
        responses = root / "responses"
        responses.mkdir(exist_ok=True)
        (responses / "batch-0001.attempt-0001.message.json").write_text(final_response(), encoding="utf-8")
        path = responses / "batch-0001.attempt-0001.events.jsonl"
        path.write_bytes(raw_events)
        stderr_path = root / "raw-codex-stderr.bin"
        stderr_path.write_bytes(stderr)
        return final_response(), {"command": executor._expected_codex_command(kwargs["executable"], root), "reported": executor._strict_stderr_labels(stderr), "provider_artifacts": {
            "codex_events": {"path": path.relative_to(root).as_posix(), "bytes": len(raw_events), "sha256": executor._sha(raw_events)},
            "codex_stderr": {"path": stderr_path.name, "bytes": len(stderr), "sha256": executor._sha(stderr)},
        }}
    return invoke


def prepare(tmp_path: Path, sol: dict) -> None:
    executor.prepare_only(output_root=tmp_path, cell_id=sol["cell_id"], queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), authorization_acknowledgement_sha256=AUTH, **ROOTS)


def test_pins_v2_contract_runner_and_exact_tool_free_argv() -> None:
    assert hashlib.sha256(executor.EXEC_V2_PATH.read_bytes()).hexdigest() == executor.EXEC_V2_SHA256
    assert hashlib.sha256(executor.EXEC_V2_CONTRACT_PATH.read_bytes()).hexdigest() == executor.EXEC_V2_CONTRACT_SHA256
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["predecessor"]["executor_sha256"] == executor.EXEC_V2_SHA256
    argv = executor._expected_codex_command("fixture", Path("C:/fixture"))
    assert argv.count("code_mode") == 1 and "code_mode_host" not in argv
    assert all(token in argv for token in ("--json", "--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config", "read-only", 'web_search="disabled"', "mcp_servers={}", 'approval_policy="never"'))


def test_local_launcher_persists_empty_stderr_and_exact_argv(monkeypatch, tmp_path: Path) -> None:
    launcher = executor._load_call_codex()
    seen: dict[str, object] = {}
    def fake_run(command, **kwargs):
        seen["command"] = command
        message = Path(command[command.index("--output-last-message") + 1])
        message.write_text(final_response(), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=events(), stderr=b"")
    monkeypatch.setattr(executor.subprocess, "run", fake_run)
    schema = tmp_path / "response-schema.json"; schema.write_text("{}", encoding="utf-8")
    _content, record = launcher(executable="fixture", model="gpt-5.6-sol", reasoning="high", prompt="fixture", output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=60, before_provider_attempt=lambda: None, capture_jsonl_events=True)
    assert seen["command"] == [*executor._expected_codex_command("fixture", tmp_path)[:-1], "-"]
    artifact = record["provider_artifacts"]["codex_stderr"]
    assert artifact == {"path": "raw-codex-stderr.bin", "bytes": 0, "sha256": executor._sha(b"")}
    assert (tmp_path / artifact["path"]).read_bytes() == b""


def test_cli_mode_runs_v3_main_only() -> None:
    completed = subprocess.run([sys.executable, str(PACKAGE / "executor.py"), "--help"], capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert "--execute-one-sol" in completed.stdout


def test_timeout_preserves_partial_stdout_and_stderr(monkeypatch, tmp_path: Path) -> None:
    launcher = executor._load_call_codex()
    def timeout(*_args, **_kwargs):
        error = subprocess.TimeoutExpired("fixture", 1)
        error.stdout, error.stderr = b"partial-events", b"partial-stderr"
        raise error
    monkeypatch.setattr(executor.subprocess, "run", timeout)
    schema = tmp_path / "response-schema.json"; schema.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="failed after launch"):
        launcher(executable="fixture", model="gpt-5.6-sol", reasoning="high", prompt="fixture", output_dir=tmp_path, response_schema=schema, batch_number=1, timeout=1, before_provider_attempt=lambda: None, capture_jsonl_events=True)
    assert (tmp_path / "responses" / "batch-0001.attempt-0001.events.jsonl").read_bytes() == b"partial-events"
    assert (tmp_path / "raw-codex-stderr.bin").read_bytes() == b"partial-stderr"


@pytest.mark.parametrize("stderr", [b"", b"model: gpt-5.6-sol\nprovider: openai\nreasoning effort: high\nsession id: thread-1\nuser\n"])
def test_absent_or_matching_stderr_labels_accept_lifecycle(sol_row, tmp_path: Path, stderr: bytes) -> None:
    prepare(tmp_path, sol_row)
    result = executor.execute_sol(output_root=tmp_path, cell_id=sol_row["cell_id"], queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), call_codex=callback(events(), stderr), **LIVE)
    root = tmp_path / sol_row["cell_id"]
    receipt = json.loads(root.joinpath("execution-receipt.json").read_text(encoding="utf-8"))
    assert result["native_contact_proven"] is False and result["native_endpoint_contact_cardinality"] == "unproven"
    assert receipt["raw_stderr_sha256"] == executor._sha(stderr)
    assert result["identity"]["provider_reported_model"] is None and result["identity"]["reasoning_attested"] is False
    executor._validate_completed_inventory(root, is_sol=True)


def test_verifier_binds_stderr_and_rejects_tamper(sol_row, tmp_path: Path) -> None:
    prepare(tmp_path, sol_row)
    result = executor.execute_sol(output_root=tmp_path, cell_id=sol_row["cell_id"], queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), call_codex=callback(events(), b""), **LIVE)
    parent = executor._load_predecessor()
    payload = parent._payload(parent._load_v3(), sol_row, **ROOTS)
    event = {"cell": sol_row, "identity": result["identity"], "native_request_bytes": result["request_bytes"], "outbound_payload": payload, "effective_settings": {
        "route_name": sol_row["route"]["route_name"], "effective_model": sol_row["route"]["effective_model"],
        "requested_reasoning_effort": sol_row["route"]["requested_reasoning_effort"], "tools_enabled": False,
        "web_search_enabled": False, "subagents_enabled": False, "output_schema_sha256": sol_row["response_schema_sha256"],
        "provider_attested": False, "source": "codex_cli_local_events_and_invocation_v1",
    }}
    assert executor.verify_predecessor_receipt(event, execution_root=tmp_path, queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), **ROOTS)["local_lifecycle_verified"] is True
    root = tmp_path / sol_row["cell_id"]
    effective_path = root / "effective-settings.json"
    receipt_path = root / "execution-receipt.json"
    effective = json.loads(effective_path.read_text(encoding="utf-8"))
    effective["local_effective_model"] = "attacker-model"
    effective["local_effective_reasoning_effort"] = "low"
    effective["provider_attested"] = True
    effective_path.write_bytes(executor._canonical(effective))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["effective_settings_sha256"] = executor._sha(executor._canonical(effective))
    receipt["identity"]["effective_model"] = "attacker-model"
    receipt["identity"]["provider_reported_model"] = "attacker-model"
    receipt["identity"]["reasoning_attested"] = True
    receipt_path.write_bytes(executor._canonical(receipt))
    event["identity"] = receipt["identity"]
    with pytest.raises(ValueError, match="local command or stderr projection|identity/contact ceiling"):
        executor.verify_predecessor_receipt(event, execution_root=tmp_path, queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), **ROOTS)


@pytest.mark.parametrize("stderr", [b"model: bad\n", b"provider: other\n", b"reasoning effort: low\n", b"session id: wrong\n", b"model: gpt-5.6-sol\nmodel: gpt-5.6-sol\n", b"model:\n", b"ERROR: fixture\n"])
def test_conflicting_duplicate_malformed_or_error_stderr_reconciles_no_resend(sol_row, tmp_path: Path, stderr: bytes) -> None:
    output = tmp_path / hashlib.sha256(stderr).hexdigest()[:8]
    prepare(output, sol_row)
    result = executor.execute_sol(output_root=output, cell_id=sol_row["cell_id"], queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), call_codex=callback(events(), stderr), **LIVE)
    assert result["state"] == "reconcile_required_after_process_launch" and result["process_launches"] == 1
    with pytest.raises(ValueError, match="refuses to resend"):
        executor.execute_sol(output_root=output, cell_id=sol_row["cell_id"], queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), call_codex=callback(events(), stderr), **LIVE)


def test_jsonl_error_reconciles_and_runtime_never_imports_optimizers(monkeypatch, sol_row, tmp_path: Path) -> None:
    attempted: list[str] = []; original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}: attempted.append(name); raise AssertionError(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    loaded = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v3_guard")
    assert loaded.STUDY_ID.endswith("v3") and attempted == []
    prepare(tmp_path, sol_row)
    result = executor.execute_sol(output_root=tmp_path, cell_id=sol_row["cell_id"], queue_root=tmp_path / "queue", broker_factory=factory(sol_route()), call_codex=callback(events(error=True), b""), **LIVE)
    assert result["state"] == "reconcile_required_after_process_launch"
