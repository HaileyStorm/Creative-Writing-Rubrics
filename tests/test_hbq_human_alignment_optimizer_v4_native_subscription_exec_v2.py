from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v2"
V1_PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1"
executor = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v2")
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
        "name": executor.SOL_ROUTE_NAME,
        "model": "gpt-5.6-sol",
        "adapter": "codex_exec",
        "provider": "openai_codex",
        "destination": "openai_codex_chatgpt_subscription",
        "account_class": "subscription",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "reasoning_effort": "high",
        "identity_evidence": "requested_only",
        "trusted": True,
        "allowed_payload_classes": ["public_repo"],
        "codex_command": ["codex-fixture.exe"],
        "codex_command_identity": identity,
        "cli_version_identity": identity,
        "auth_status_identity": identity,
        "codex_cli_version": "codex-cli fixture 1.0",
        "command": ["python-fixture.exe", str(executor.CODEX_ADAPTER_PATH)],
        "command_identity": identity,
        "cost_evidence": {
            "evidence_hash": "e" * 64,
            "checked_at": "2026-08-29T00:00:00Z",
            "expires_at": "2026-08-30T00:00:00Z",
        },
        "auth_receipt_hash": "1" * 64,
        "timeout_seconds": 60,
    }


def grok_route() -> dict:
    identity = {"version": 1, "artifacts": [{"path": "grok-fixture.exe", "sha256": "b" * 64}]}
    return {
        "name": executor.ROUTE_NAME,
        "model": "grok-4.6",
        "adapter": "grok_exec",
        "provider": "xai_grok_build",
        "destination": "xai_grok_build_subscription",
        "account_class": "subscription",
        "zero_charge": True,
        "armed": True,
        "health": "healthy",
        "reasoning_effort": "high",
        "reported_model": "grok-4.6-build",
        "identity_evidence": "requested_only",
        "allowed_payload_classes": ["public_repo"],
        "grok_command": ["grok-fixture.exe"],
        "grok_command_identity": identity,
        "cli_version_identity": identity,
        "grok_cli_version": "grok fixture 1.0",
        "cost_evidence": {"evidence_hash": "a" * 64},
        "subscription_receipt_hash": "c" * 64,
        "timeout_seconds": 60,
    }


class FakeBroker:
    def __init__(self, _root: Path, candidate: dict):
        self.candidate = candidate

    def _load_registry_live(self):
        return {"version": 1, "routes": [self.candidate]}

    def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence):
        assert candidate == self.candidate
        assert verify_command_identity is True and validate_current_evidence is True


def factory(candidate: dict):
    return lambda root: FakeBroker(root, candidate)


def valid_final_response() -> str:
    dimensions = ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"]
    return json.dumps(
        {
            "scores": {name: 3 for name in dimensions},
            "evidence": {name: "fixture evidence" for name in dimensions},
            "coverage": {name: True for name in dimensions},
        },
        separators=(",", ":"),
    )


def codex_events(*, malformed: bool = False, error: bool = False, extra: bool = False) -> bytes:
    if malformed:
        return b"not-json\n"
    events = [
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}},
        {
            "type": "item.completed",
            "item": {"id": "m1", "type": "agent_message", "text": valid_final_response()},
        },
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
    ]
    if error:
        events.insert(-1, {"type": "error", "error": {"message": "fixture"}})
    if extra:
        events.append({"type": "turn.started"})
    return b"".join(json.dumps(event, separators=(",", ":")).encode() + b"\n" for event in events)


def sol_call(raw_events: bytes, prompts: list[bytes] | None = None):
    def invoke(**kwargs):
        assert kwargs["capture_jsonl_events"] is True
        assert kwargs["model"] == "gpt-5.6-sol" and kwargs["reasoning"] == "high"
        kwargs["before_provider_attempt"]()
        if prompts is not None:
            prompts.append(kwargs["prompt"].encode("utf-8"))
        root = kwargs["output_dir"]
        responses = root / "responses"
        responses.mkdir(exist_ok=True)
        final = valid_final_response()
        (responses / "batch-0001.attempt-0001.message.json").write_text(final, encoding="utf-8")
        events_path = responses / "batch-0001.attempt-0001.events.jsonl"
        events_path.write_bytes(raw_events)
        return final, {
            "command": executor._expected_codex_command(kwargs["executable"], root),
            "reported": {
                "model": "gpt-5.6-sol",
                "provider": "openai",
                "reasoning_effort": "high",
                "session_id": "thread-1",
            },
            "provider_artifacts": {
                "codex_events": {
                    "path": events_path.relative_to(root).as_posix(),
                    "bytes": len(raw_events),
                    "sha256": executor._sha(raw_events),
                }
            },
        }

    return invoke


@pytest.fixture(scope="module")
def parent_material():
    parent = executor._load_predecessor()
    schedule = parent.derive_schedule(**ROOTS)
    grok = next(row for row in schedule["mandatory_development"] if row["route_name"] == "grok_primary")
    sol = next(row for row in schedule["mandatory_development"] if row["route_name"] == "sol_validation")
    return parent, grok, sol


def parent_payload(parent, row: dict) -> bytes:
    return parent._payload(parent._load_v3(), row, **ROOTS)


def test_exact_predecessor_pins_and_localized_codex_argv() -> None:
    assert hashlib.sha256(executor.EXEC_V1_PATH.read_bytes()).hexdigest() == executor.EXEC_V1_SHA256
    assert hashlib.sha256(executor.EXEC_V1_CONTRACT_PATH.read_bytes()).hexdigest() == executor.EXEC_V1_CONTRACT_SHA256
    contract = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["predecessor"] == {
        "study_id": "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1",
        "executor_sha256": executor.EXEC_V1_SHA256,
        "contract_sha256": executor.EXEC_V1_CONTRACT_SHA256,
    }
    v1 = load_module(V1_PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v1_for_v2_pin")
    root = Path("C:/fixture/cell")
    expected = v1._expected_codex_command("codex-fixture.exe", root)
    host_index = expected.index("code_mode_host")
    expected[host_index] = "code_mode"
    actual = executor._expected_codex_command("codex-fixture.exe", root)
    assert actual == expected
    assert actual.count("code_mode") == 1 and "code_mode_host" not in actual
    assert actual[actual.index("code_mode") - 1] == "--disable"
    for invariant in (
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        'web_search="disabled"',
        "mcp_servers={}",
        'approval_policy="never"',
        "read-only",
        "<prompt-via-stdin>",
    ):
        assert invariant in actual


def test_default_localized_launcher_emits_actual_v2_argv(monkeypatch, tmp_path: Path) -> None:
    assert executor.execute_sol.__globals__["_load_call_codex"] is executor._load_call_codex
    launcher = executor._load_call_codex()
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):
        captured["command"] = list(command)
        captured["input"] = kwargs["input"]
        message_path = Path(command[command.index("--output-last-message") + 1])
        message_path.write_text(valid_final_response(), encoding="utf-8")
        stderr = (
            b"model: gpt-5.6-sol\nprovider: openai\nreasoning effort: high\n"
            b"session id: thread-1\nuser\n"
        )
        return subprocess.CompletedProcess(command, 0, stdout=codex_events(), stderr=stderr)

    monkeypatch.setattr(launcher.__globals__["subprocess"], "run", fake_run)
    schema = tmp_path / "response-schema.json"
    schema.write_text("{}\n", encoding="utf-8")
    callbacks: list[str] = []
    content, record = launcher(
        executable="codex-fixture.exe",
        model="gpt-5.6-sol",
        reasoning="high",
        prompt="fixture prompt",
        output_dir=tmp_path,
        response_schema=schema,
        batch_number=1,
        timeout=60,
        attempt_number=1,
        before_provider_attempt=lambda: callbacks.append("launch"),
        capture_jsonl_events=True,
    )
    expected_record = executor._expected_codex_command("codex-fixture.exe", tmp_path)
    assert captured["command"] == [*expected_record[:-1], "-"]
    assert captured["input"] == b"fixture prompt" and callbacks == ["launch"]
    assert "code_mode_host" not in captured["command"]
    assert captured["command"].count("code_mode") == 1
    assert content == valid_final_response()
    assert record["command"] == expected_record
    assert record["provider_artifacts"]["codex_events"]["sha256"] == executor._sha(codex_events())


def test_prepare_preserves_exact_matched_prompt_and_schema_bytes(parent_material, tmp_path: Path) -> None:
    parent, grok, sol = parent_material
    executor.prepare_only(
        output_root=tmp_path / "grok",
        cell_id=grok["cell_id"],
        queue_root=tmp_path / "queue",
        broker_factory=factory(grok_route()),
        authorization_acknowledgement_sha256=AUTH,
        **ROOTS,
    )
    executor.prepare_only(
        output_root=tmp_path / "sol",
        cell_id=sol["cell_id"],
        queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()),
        authorization_acknowledgement_sha256=AUTH,
        **ROOTS,
    )
    grok_root = tmp_path / "grok" / grok["cell_id"]
    sol_root = tmp_path / "sol" / sol["cell_id"]
    assert grok_root.joinpath("prompt-request.bin").read_bytes() == sol_root.joinpath(
        "prompt-request.bin"
    ).read_bytes()
    assert grok_root.joinpath("response-schema.json").read_bytes() == sol_root.joinpath(
        "response-schema.json"
    ).read_bytes()
    source = json.loads(parent_payload(parent, sol).decode("utf-8"))["components"]
    assert sol_root.joinpath("prompt-request.bin").read_bytes() == source["task_payload"].encode("utf-8")
    assert sol_root.joinpath("response-schema.json").read_bytes() == source["response_schema"].encode("utf-8")


def test_clean_sol_lifecycle_is_accepted_without_contact_overclaim(parent_material, tmp_path: Path) -> None:
    parent, _grok, sol = parent_material
    executor.prepare_only(
        output_root=tmp_path,
        cell_id=sol["cell_id"],
        queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()),
        authorization_acknowledgement_sha256=AUTH,
        **ROOTS,
    )
    prompts: list[bytes] = []
    result = executor.execute_sol(
        output_root=tmp_path,
        cell_id=sol["cell_id"],
        queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()),
        call_codex=sol_call(codex_events(), prompts),
        **LIVE,
    )
    root = tmp_path / sol["cell_id"]
    receipt = json.loads(root.joinpath("execution-receipt.json").read_text(encoding="utf-8"))
    record = json.loads(root.joinpath("codex-record.json").read_text(encoding="utf-8"))
    assert result["state"] == "local_codex_lifecycle_received_native_contact_unproven"
    assert result["native_contact_proven"] is False and result["native_endpoint_contact_cardinality"] == "unproven"
    assert prompts == [root.joinpath("prompt-request.bin").read_bytes()]
    assert receipt["study_id"] == executor.STUDY_ID
    assert receipt["identity"]["transport_identity"] == "codex_chatgpt_subscription_exec_tool_free_v2"
    assert record["command"] == executor._expected_codex_command("codex-fixture.exe", root)
    event = {
        "cell": sol,
        "identity": result["identity"],
        "native_request_bytes": result["request_bytes"],
        "outbound_payload": parent_payload(parent, sol),
        "effective_settings": {
            "route_name": sol["route"]["route_name"],
            "effective_model": sol["route"]["effective_model"],
            "requested_reasoning_effort": sol["route"]["requested_reasoning_effort"],
            "tools_enabled": False,
            "web_search_enabled": False,
            "subagents_enabled": False,
            "output_schema_sha256": sol["response_schema_sha256"],
            "provider_attested": False,
            "source": "codex_cli_local_events_and_invocation_v1",
        },
    }
    assert executor.verify_predecessor_receipt(
        event,
        execution_root=tmp_path,
        queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()),
        **ROOTS,
    ) == {
        "accepted": False,
        "local_lifecycle_verified": True,
        "native_endpoint_contact_cardinality": "unproven",
        "reason": "local_codex_thread_events_do_not_attest_native_endpoint_contact_cardinality",
    }


@pytest.mark.parametrize(
    "raw",
    [
        codex_events(malformed=True),
        codex_events(error=True),
        codex_events(extra=True),
    ],
)
def test_malformed_error_or_extra_events_reconcile_and_never_resend(
    parent_material, tmp_path: Path, raw: bytes
) -> None:
    _parent, _grok, sol = parent_material
    output_root = tmp_path / hashlib.sha256(raw).hexdigest()[:8]
    executor.prepare_only(
        output_root=output_root,
        cell_id=sol["cell_id"],
        queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()),
        authorization_acknowledgement_sha256=AUTH,
        **ROOTS,
    )
    result = executor.execute_sol(
        output_root=output_root,
        cell_id=sol["cell_id"],
        queue_root=tmp_path / "queue",
        broker_factory=factory(sol_route()),
        call_codex=sol_call(raw),
        **LIVE,
    )
    assert result["state"] == "reconcile_required_after_process_launch"
    assert result["process_launches"] == 1 and result["native_contact_proven"] is False
    with pytest.raises(ValueError, match="refuses to resend"):
        executor.execute_sol(
            output_root=output_root,
            cell_id=sol["cell_id"],
            queue_root=tmp_path / "queue",
            broker_factory=factory(sol_route()),
            call_codex=sol_call(raw),
            **LIVE,
        )


def test_runtime_imports_neither_dspy_nor_optuna(monkeypatch) -> None:
    attempted: list[str] = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0].lower() in {"dspy", "optuna"}:
            attempted.append(name)
            raise AssertionError(f"runtime optimizer import forbidden: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    loaded = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v2_import_guard")
    assert loaded.STUDY_ID == "hbq-human-alignment-optimizer-v4-native-subscription-exec-v2"
    assert attempted == []
