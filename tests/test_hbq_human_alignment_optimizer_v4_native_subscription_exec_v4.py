from __future__ import annotations

import hashlib
import json
from pathlib import Path
import builtins

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v4"
executor = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v4")
AUTH = "d" * 64


def sol_route() -> dict:
    identity = {"version": 1, "artifacts": [{"path": "codex-fixture.exe", "sha256": "f" * 64}]}
    return {"name": "codex-chatgpt-gpt-5.6-sol", "model": "gpt-5.6-sol", "adapter": "codex_exec", "provider": "openai_codex", "destination": "openai_codex_chatgpt_subscription", "account_class": "subscription", "zero_charge": True, "armed": True, "health": "healthy", "reasoning_effort": "high", "identity_evidence": "requested_only", "trusted": True, "allowed_payload_classes": ["public_repo"], "codex_command": ["codex-fixture.exe"], "codex_command_identity": identity, "cli_version_identity": identity, "auth_status_identity": identity, "codex_cli_version": "codex-cli fixture 1.0", "command": ["python-fixture.exe", str(executor._v3().CODEX_ADAPTER_PATH)], "command_identity": identity, "cost_evidence": {"evidence_hash": "e" * 64, "checked_at": "2026-08-29T00:00:00Z", "expires_at": "2026-08-30T00:00:00Z"}, "auth_receipt_hash": "1" * 64, "timeout_seconds": 60}


class Broker:
    def __init__(self, _root: Path, route: dict): self.route = route
    def _load_registry_live(self): return {"version": 1, "routes": [self.route]}
    def _validate_route(self, candidate, *, verify_command_identity, validate_current_evidence):
        assert candidate == self.route and verify_command_identity and validate_current_evidence


def factory(route: dict): return lambda root: Broker(root, route)


def final_response() -> str:
    names = ["Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity"]
    return json.dumps({"scores": {name: 3 for name in names}, "evidence": {name: "fixture" for name in names}, "coverage": {name: True for name in names}}, separators=(",", ":"))


def lifecycle_events(*, malformed: bool = False) -> bytes:
    stream = [{"type": "thread.started", "thread_id": "thread-1"}, {"type": "turn.started"}, {"type": "item.started", "item": {"id": "m1", "type": "agent_message", "text": ""}}, {"type": "item.completed", "item": {"id": "m1", "type": "agent_message", "text": final_response()}}, {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
    if malformed: stream.insert(-1, {"type": "error", "error": {"message": "fixture"}})
    return b"".join(json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in stream)


def callback(calls: list[dict], *, malformed: bool = False, precreate_responses: bool = True):
    def invoke(**kwargs):
        calls.append(kwargs); root = kwargs["output_dir"]; responses = root / "responses"
        if precreate_responses: responses.mkdir()
        kwargs["before_provider_attempt"](); responses.mkdir(exist_ok=True)
        raw = lifecycle_events(malformed=malformed); stderr = b""; (responses / "batch-0001.attempt-0001.message.json").write_text(final_response(), encoding="utf-8"); events = responses / "batch-0001.attempt-0001.events.jsonl"; events.write_bytes(raw); stderr_path = root / "raw-codex-stderr.bin"; stderr_path.write_bytes(stderr)
        v3 = executor._v3()
        return final_response(), {"command": v3._expected_codex_command(kwargs["executable"], root), "reported": v3._strict_stderr_labels(stderr), "provider_artifacts": {"codex_events": {"path": events.relative_to(root).as_posix(), "bytes": len(raw), "sha256": executor._sha(raw)}, "codex_stderr": {"path": stderr_path.name, "bytes": 0, "sha256": executor._sha(stderr)}}}
    return invoke


def test_prepare_binds_only_replacement_id_and_admitted_grok_bytes(tmp_path: Path) -> None:
    row = executor._row("v4-sol-replacement-25aec056875cb72c")
    result = executor.prepare_only(output_root=tmp_path, cell_id=row["cell_id"], queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(sol_route()))
    root = tmp_path / row["cell_id"]
    prepared = json.loads(root.joinpath("prepared.json").read_text(encoding="utf-8"))
    assert result["provider_calls_made"] == 0 and prepared["replacement_row"] == row
    assert root.joinpath("matched-grok-task.bin").read_bytes() == Path(row["grok_destination_root"], "native-request.bin").read_bytes()
    with pytest.raises(ValueError, match="only the two replacement"):
        executor.prepare_only(output_root=tmp_path, cell_id="v4-cell-2eb4f20b3db15aac", queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(sol_route()))


def test_runtime_pins_schedule_and_never_imports_optimizers(monkeypatch) -> None:
    attempted: list[str] = []; original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"dspy", "optuna"}: attempted.append(name); raise AssertionError(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    loaded = load_module(PACKAGE / "executor.py", name="hanna_v4_native_subscription_exec_v4_guard")
    assert hashlib.sha256(loaded.SCHEDULE_PATH.read_bytes()).hexdigest() == loaded.SCHEDULE_SHA256
    assert hashlib.sha256(loaded.EXEC_V3_PATH.read_bytes()).hexdigest() == loaded.EXEC_V3_SHA256
    assert attempted == []


def test_execute_is_one_launch_and_never_resends(tmp_path: Path) -> None:
    cell_id = "v4-sol-replacement-af46262aed40d89e"; route = sol_route()
    executor.prepare_only(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    calls: list[dict] = []
    result = executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=callback(calls))
    assert result["process_launches"] == 1 and len(calls) == 1 and calls[0]["capture_jsonl_events"] is True
    receipt = json.loads((tmp_path / cell_id / "execution-receipt.json").read_text(encoding="utf-8"))
    assert result["state"] == "local_codex_lifecycle_received_native_contact_unproven" and receipt["study_id"] == executor.STUDY_ID and receipt["original_item_id"] != receipt["replacement_item_id"]
    with pytest.raises(ValueError, match="refuses to resend"):
        executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=callback(calls))


def test_empty_runner_responses_before_callback_is_not_precontact_residue(tmp_path: Path) -> None:
    cell_id = "v4-sol-replacement-25aec056875cb72c"; route = sol_route(); calls: list[dict] = []
    executor.prepare_only(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    result = executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=callback(calls, precreate_responses=True))
    root = tmp_path / cell_id
    assert result["state"] == "local_codex_lifecycle_received_native_contact_unproven" and len(calls) == 1
    assert root.joinpath("launch-intent.json").exists() and not root.joinpath("precontact-failure.json").exists()


def test_callback_validator_rechecks_all_prepared_entries_and_allows_only_empty_responses(monkeypatch, tmp_path: Path) -> None:
    cell_id = "v4-sol-replacement-25aec056875cb72c"; route = sol_route(); root = tmp_path / cell_id
    executor.prepare_only(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    row = executor._row(cell_id); responses = root / "responses"; responses.mkdir()
    prepared, task, schema = executor._validated_prepared(root, row, AUTH, allow_empty_responses=True)
    assert prepared["cell_id"] == cell_id and task and schema
    original = executor._plain_entry
    for name in sorted(executor.PREPARED_FILES | {"responses"}):
        target = root / name
        with monkeypatch.context() as scoped:
            def reject(path: Path, *, directory: bool = False, target: Path = target):
                if path == target:
                    raise ValueError("fixture callback-time reparse")
                return original(path, directory=directory)
            scoped.setattr(executor, "_plain_entry", reject)
            with pytest.raises(ValueError, match="reparse"):
                executor._validated_prepared(root, row, AUTH, allow_empty_responses=True)
    orphan = root / "callback-extra.bin"; orphan.write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="inventory"):
        executor._validated_prepared(root, row, AUTH, allow_empty_responses=True)
    orphan.unlink()
    (responses / "runner-residue.bin").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="responses residue"):
        executor._validated_prepared(root, row, AUTH, allow_empty_responses=True)


@pytest.mark.parametrize("malformed", [True])
def test_malformed_lifecycle_never_reports_success(tmp_path: Path, malformed: bool) -> None:
    cell_id = "v4-sol-replacement-af46262aed40d89e"; route = sol_route(); calls: list[dict] = []
    executor.prepare_only(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    result = executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=callback(calls, malformed=malformed))
    assert result["state"] == "reconcile_required_after_process_launch" and len(calls) == 1 and not (tmp_path / cell_id / "execution-receipt.json").exists()


def test_empty_runner_residue_is_preserved_and_requires_fresh_root(tmp_path: Path) -> None:
    cell_id = "v4-sol-replacement-25aec056875cb72c"; route = sol_route(); root = tmp_path / cell_id; provider_callbacks: list[bool] = []
    executor.prepare_only(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    def precontact(**kwargs):
        kwargs["output_dir"].joinpath("responses").mkdir(); provider_callbacks.append(False); raise OSError("fixture startup")
    result = executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=precontact)
    failure = json.loads(root.joinpath("precontact-failure.json").read_text(encoding="utf-8"))
    assert result["state"] == "pending_precontact_fresh_root_required" and provider_callbacks == [False]
    assert failure["process_launches"] == 0 and failure["retry_policy"] == "fresh_output_root_required_no_in_place_retry"
    assert not root.joinpath("launch-intent.json").exists() and not root.joinpath("result.json").exists() and not root.joinpath("execution-receipt.json").exists()
    with pytest.raises(ValueError, match="fresh output root"):
        executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=precontact)
    r2 = tmp_path / "r2"; calls: list[dict] = []
    executor.prepare_only(output_root=r2, cell_id=cell_id, queue_root=r2 / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    retry = executor.execute_sol(output_root=r2, cell_id=cell_id, queue_root=r2 / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=callback(calls))
    assert retry["state"] == "local_codex_lifecycle_received_native_contact_unproven" and len(calls) == 1


@pytest.mark.parametrize("defect", ["orphan", "mutated_task", "reparse", "disclosure", "proof", "prepared"])
def test_prelaunch_rejects_unsafe_prepared_root_without_callback(monkeypatch, tmp_path: Path, defect: str) -> None:
    cell_id = "v4-sol-replacement-25aec056875cb72c"; route = sol_route()
    executor.prepare_only(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, broker_factory=factory(route))
    root = tmp_path / cell_id; calls: list[dict] = []
    if defect == "orphan":
        root.joinpath("orphan.bin").write_bytes(b"unexpected")
    elif defect == "mutated_task":
        task = root / "matched-grok-task.bin"; task.write_bytes(b"!" + task.read_bytes()[1:])
    elif defect in {"disclosure", "proof", "prepared"}:
        names = {"disclosure": "disclosure.json", "proof": "zero-charge-route-proof.json", "prepared": "prepared.json"}
        path = root / names[defect]; value = json.loads(path.read_text(encoding="utf-8"))
        if defect == "prepared": value["schedule_sha256"] = "0" * 64
        else: value["cell_id"] = "tampered"
        path.write_bytes(executor._canonical(value))
    else:
        original = executor._plain_entry
        def reject(path: Path, *, directory: bool = False):
            if path == root / "matched-grok-task.bin": raise ValueError("fixture reparse")
            return original(path, directory=directory)
        monkeypatch.setattr(executor, "_plain_entry", reject)
    def callback(**kwargs):
        calls.append(kwargs); kwargs["before_provider_attempt"](); return "{}", {}
    with pytest.raises(ValueError, match="inventory|task/schema|reparse|disclosure|route proof|preparation"):
        executor.execute_sol(output_root=tmp_path, cell_id=cell_id, queue_root=tmp_path / "queue", authorization_acknowledgement_sha256=AUTH, allow_remote=True, broker_factory=factory(route), call_codex=callback)
    assert calls == [] and not root.joinpath("launch-intent.json").exists() and not root.joinpath("result.json").exists()
