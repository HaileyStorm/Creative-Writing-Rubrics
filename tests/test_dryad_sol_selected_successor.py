from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "evaluation-results" / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
RUNTIME = DIRECTORY / "sol_selected_successor_runtime.py"
EXECUTION = DIRECTORY / "sol_selected_successor_execution.py"


def load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected() -> list[int]:
    return list(range(1, 1611)) + list(range(4049, 4739))


class FakeV3:
    def __init__(self, stderr: bytes, returncode: int | None) -> None:
        self.stderr = stderr
        self.returncode = returncode
        self.runs = 0
        self.subprocess = self.FakeSubprocess(self)

    class FakeSubprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        def __init__(self, owner: FakeV3) -> None:
            self.owner = owner

        def run(self, command: list[str], **_kwargs: Any) -> Any:
            self.owner.runs += 1
            if self.owner.returncode is None:
                raise OSError("fixture launch failure")
            return SimpleNamespace(returncode=self.owner.returncode, stdout=b'{"type":"thread.started","thread_id":"native-1"}\n', stderr=self.owner.stderr)

    def _expected_codex_command(self, executable: str, _output_root: Path) -> list[str]:
        return [executable, "--output-schema", "placeholder", "--output-last-message", "placeholder", "<prompt-via-stdin>"]

    def _load_parse_codex_events(self) -> object:
        return object()

    def _codex_event_projection(self, _events: bytes, _parser: object) -> dict[str, Any]:
        return {"thread_id": "native-1", "completed_agent_message_text": '{"verdicts":[]}'}

    def _load_call_codex(self) -> Any:
        def invoke(**kwargs: Any) -> tuple[str, dict[str, Any]]:
            command = self._expected_codex_command(kwargs["executable"], kwargs["output_dir"])
            message = Path(command[command.index("--output-last-message") + 1])
            message.parent.mkdir(parents=True, exist_ok=True)
            message.write_text('{"verdicts":[]}', encoding="utf-8")
            completed = self.subprocess.run(command)
            events = message.with_name(message.name.replace("message.json", "events.jsonl"))
            events.write_bytes(completed.stdout)
            descriptor = self._stderr_artifact(kwargs["output_dir"], completed.stderr)
            if completed.returncode != 0 or completed.stderr:
                raise ValueError("fixture V3 diagnostic rejection")
            return message.read_text(encoding="utf-8"), {"command": command, "reported": {}, "provider_artifacts": {"codex_stderr": descriptor}}
        return invoke


@pytest.mark.parametrize(
    ("stderr", "returncode", "expected"),
    [
        (b"ERROR: wrapper warning\nsession id: native-1\n", 0, "completed_with_wrapper_warning"),
        (b"", 0, "completed"),
        (b"ERROR: wrapper warning\n", 1, "reject"),
        (b"", None, "reject"),
        (b"model: another\n", 0, "reject"),
        (b"\xff", 0, "reject"),
    ],
)
def test_runtime_records_zero_exit_warning_without_relaxing_protocol(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stderr: bytes,
    returncode: int | None,
    expected: str,
) -> None:
    value = load(RUNTIME, "dryad_selected_successor_runtime_test")
    fake = FakeV3(stderr, returncode)
    monkeypatch.setattr(value, "_verify", lambda: None)
    monkeypatch.setattr(value, "_base", lambda: fake)
    root = tmp_path / "request" / "native-output"
    schema = root / "payload" / "schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text("{}", encoding="utf-8")
    kwargs = {"executable": "fixture-codex", "model": "gpt-5.6-sol", "reasoning": "high", "prompt": "{}",
              "output_dir": root, "response_schema": schema, "batch_number": 1, "timeout": 1,
              "before_provider_attempt": lambda: None, "receipt_root": root.parent / "process-completion"}
    if expected == "reject":
        with pytest.raises((OSError, ValueError)):
            value.call_codex(**kwargs)
        return
    content, record = value.call_codex(**kwargs)
    receipt = json.loads((root.parent / "process-completion" / "native-output.json").read_bytes())
    assert content == '{"verdicts":[]}' and record["completion_class"] == expected
    assert record["native_thread_id"] == "native-1"
    assert receipt["state"] == "completed" and receipt["exit_code"] == 0
    if expected == "completed_with_wrapper_warning":
        with pytest.raises(ValueError, match="artifacts already exist"):
            value.call_codex(**kwargs)
        assert fake.runs == 1


def test_remaining_selected_ordinals_exclude_unselected_gap() -> None:
    value = load(EXECUTION, "dryad_selected_successor_execution_schedule_test")
    remaining = value._remaining({"selected_request_ordinals": selected()})
    assert remaining == list(range(1343, 1611)) + list(range(4049, 4739))
    assert len(remaining) == 958 and 1611 not in remaining and 4048 not in remaining


@pytest.mark.parametrize("stderr", [b"", b"ERROR: recovered diagnostic warning\n"])
def test_runtime_replays_real_frozen_lifecycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stderr: bytes) -> None:
    value = load(RUNTIME, "selected_sol_real_lifecycle")
    base = value._base()
    final = '{"verdicts":[]}'
    rows = [
        {"type": "thread.started", "thread_id": "real-parser-fixture"},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"id": "message-1", "type": "agent_message", "text": ""}},
        {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": final}},
        {"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 4}},
    ]
    event_bytes = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append(command)
        Path(command[command.index("--output-last-message") + 1]).write_text(final, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout=event_bytes, stderr=stderr)

    base.subprocess = SimpleNamespace(run=fake_run, TimeoutExpired=subprocess.TimeoutExpired)
    monkeypatch.setattr(value, "_base", lambda: base)
    native = tmp_path / "native-output"
    schema = native / "payload" / "schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_bytes(b"{}")
    gates: list[bool] = []
    content, record = value.call_codex(
        executable="fixture-codex", model="gpt-5.6-sol", reasoning="high", prompt="{}", output_dir=native,
        response_schema=schema, batch_number=1, timeout=1, receipt_root=tmp_path / "process-completion",
        before_provider_attempt=lambda: gates.append(True),
    )
    assert content == final and gates == [True] and len(calls) == 1
    assert value.replay_completion(output_dir=native, batch_number=1, record=record) == "real-parser-fixture"
    with pytest.raises(ValueError, match="lifecycle identity"):
        value.replay_completion(output_dir=native, batch_number=1, record={**record, "native_thread_id": "wrong-thread"})
    events = native / "responses" / "batch-0001.attempt-0001.events.jsonl"
    events.write_bytes(b"".join((json.dumps(row) + "\n").encode() for row in rows[:-1]))
    with pytest.raises(ValueError):
        value.replay_completion(output_dir=native, batch_number=1, record=record)
    assert len(calls) == 1


def campaign(value: Any, root: Path, *, prefix_ids: list[str] | None = None) -> list[int]:
    ordinals = value._remaining({"selected_request_ordinals": selected()})
    plan = root / "plan"; plan.mkdir(parents=True)
    plan_raw = b"fixture plan"; (plan / "plan.json").write_bytes(plan_raw)
    parallel = root / "parallel"; parallel.mkdir()
    parallel_raw = b"fixture parallel"; (parallel / "campaign-manifest.json").write_bytes(parallel_raw)
    descriptor = {"selected_request_ordinals": selected()}
    descriptor_raw = value._canonical(descriptor)
    manifest = {
        "schema_version": 1,
        "driver_sha256": value._sha(Path(value.__file__).read_bytes()),
        "runtime_sha256": value._sha(value.RUNTIME.read_bytes()),
        "old_parallel_sha256": value.PARALLEL_SHA256,
        "selected_schedule_source_sha256": value.SCHEDULE_SHA256,
        "capture_sha256": value.CAPTURE_SHA256,
        "counts": {"lanes": 10},
        "plan_root": str(plan),
        "original_plan_sha256": value._sha(plan_raw),
        "parallel_root": str(parallel),
        "parallel_manifest_sha256": value._sha(parallel_raw),
        "selected_schedule_sha256": value._sha(descriptor_raw),
        "route_identity": {},
        "prefix": {"thread_ids": prefix_ids or []},
        "remaining_original_ordinals": ordinals,
    }
    (root / "campaign-manifest.json").write_bytes(value._canonical(manifest))
    (root / "selected-schedule.json").write_bytes(descriptor_raw)
    return ordinals


class DispatchRuntime:
    def __init__(self, *, fail_ordinal: int | None = None, identity: str | None = None) -> None:
        self.fail_ordinal = fail_ordinal
        self.identity = identity
        self.calls: list[int] = []
        self.active = 0
        self.maximum = 0
        self.lock = threading.Lock()

    def replay_completion(self, *, output_dir: Path, batch_number: int, record: dict[str, Any]) -> str:
        events = json.loads((output_dir / "responses" / f"batch-{batch_number:04d}.attempt-0001.events.jsonl").read_bytes())
        message = (output_dir / "responses" / f"batch-{batch_number:04d}.attempt-0001.message.json").read_text(encoding="utf-8")
        if events["thread_id"] != record["native_thread_id"] or events["message"] != message:
            raise ValueError("fixture lifecycle identity differs")
        return events["thread_id"]

    def call_codex(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        ordinal = int(kwargs["batch_number"])
        kwargs["before_provider_attempt"]()
        with self.lock:
            self.calls.append(ordinal)
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            if ordinal == self.fail_ordinal:
                raise ValueError("fixture failure")
            time.sleep(0.001)
            content = json.dumps({"verdicts": [{"question_id": f"q-{ordinal}"}]})
            root = Path(kwargs["output_dir"])
            responses = root / "responses"; responses.mkdir(parents=True)
            message = responses / f"batch-{ordinal:04d}.attempt-0001.message.json"
            events = responses / f"batch-{ordinal:04d}.attempt-0001.events.jsonl"
            stderr = responses / f"batch-{ordinal:04d}.attempt-0001.stderr.bin"
            event_bytes = json.dumps({"thread_id": self.identity or f"thread-{ordinal}", "message": content}).encode()
            message.write_text(content, encoding="utf-8"); events.write_bytes(event_bytes); stderr.write_bytes(b"")
            completion = {"format_version": 1, "state": "completed", "exit_code": 0,
                          "stdout": {"bytes": len(event_bytes), "sha256": hashlib.sha256(event_bytes).hexdigest()},
                          "stderr": {"bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()},
                          "final_message": {"exists": True, "bytes": len(content.encode()), "sha256": hashlib.sha256(content.encode()).hexdigest()}}
            receipt = Path(kwargs["receipt_root"]); receipt.mkdir(parents=True)
            (receipt / "native-output.json").write_text(json.dumps(completion), encoding="utf-8")
            return content, {
                "completion_class": "completed",
                "native_thread_id": self.identity or f"thread-{ordinal}",
                "completion": completion,
                "provider_artifacts": {
                    "codex_events": {"path": events.relative_to(root).as_posix(), "bytes": len(event_bytes), "sha256": hashlib.sha256(event_bytes).hexdigest()},
                    "codex_stderr": {"path": stderr.relative_to(root).as_posix(), "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()},
                },
            }
        finally:
            with self.lock:
                self.active -= 1


def install_dispatch_fakes(monkeypatch: pytest.MonkeyPatch, value: Any, runtime: DispatchRuntime) -> None:
    class Helper:
        @staticmethod
        def route_snapshot(_queue: Path, _identity: dict[str, Any]) -> dict[str, Any]:
            return {"codex_command": ["fixture-codex"]}

        @staticmethod
        def request_payload(_plan: Path, ordinal: int) -> tuple[dict[str, Any], bytes, bytes]:
            return {"ordinal": ordinal, "batch_number": ordinal, "question_ids": [f"q-{ordinal}"],
                    "prompt_sha256": value._sha(b"{}"), "schema_sha256": value._sha(b"{}")}, b"{}", b"{}"

    parallel = SimpleNamespace(HELPER_PATH=Path("helper"), HELPER_SHA256="fixture", HELPER_SHA="fixture", _load=lambda *_args: Helper)
    schedule = SimpleNamespace(canonical=value._canonical, verify_selected_schedule=lambda **kwargs: kwargs["descriptor"])

    def fake_load(path: Path, _expected: str, _name: str) -> Any:
        if path == value.PARALLEL:
            return parallel
        if path == value.RUNTIME:
            return runtime
        if path == value.SCHEDULE:
            return schedule
        raise AssertionError(path)

    monkeypatch.setattr(value, "_load", fake_load)


def test_dispatch_uses_only_selected_requests_and_at_most_ten_lanes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(EXECUTION, "dryad_selected_successor_execution_dispatch_test")
    root = tmp_path / "campaign"; ordinals = campaign(value, root)
    runtime = DispatchRuntime(); install_dispatch_fakes(monkeypatch, value, runtime)

    result = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)

    assert result["state"] == "collected" and runtime.maximum <= 10
    assert set(runtime.calls) == set(ordinals) and len(runtime.calls) == len(ordinals)
    assert all(1343 <= ordinal <= 1610 or 4049 <= ordinal <= 4738 for ordinal in runtime.calls)


def test_dispatch_skips_accepted_and_refuses_ambiguous_residue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(EXECUTION, "dryad_selected_successor_execution_resume_test")
    root = tmp_path / "campaign"; ordinals = campaign(value, root)
    accepted = root / "requests" / f"{ordinals[0]:04d}"; accepted.mkdir(parents=True)
    native = accepted / "native-output"; schema = native / "payload" / "schema.json"; schema.parent.mkdir(parents=True); schema.write_text("{}", encoding="utf-8")
    (native / "payload" / "prompt.txt").write_bytes(b"{}")
    retained = DispatchRuntime(identity="already-complete")
    content, record = retained.call_codex(output_dir=native, batch_number=ordinals[0], receipt_root=accepted / "process-completion",
                                          before_provider_attempt=lambda: None)
    start = {"state": "started", "ordinal": ordinals[0], "attempt": 1, "prompt_sha256": value._sha(b"{}"), "schema_sha256": value._sha(b"{}")}
    start_raw = value._canonical(start); (accepted / "start.json").write_bytes(start_raw)
    route_raw = value._canonical({}); (accepted / "route.json").write_bytes(route_raw)
    manifest_sha = value._sha((root / "campaign-manifest.json").read_bytes())
    source = {"prompt_sha256": value._sha(b"{}"), "schema_sha256": value._sha(b"{}"), "manifest_sha256": manifest_sha}
    source_raw = value._canonical(source); (accepted / "source-bindings.json").write_bytes(source_raw)
    (accepted / "authorization.json").write_bytes(value._canonical({"start_sha256": value._sha(start_raw), "ordinal": ordinals[0],
                                                                        "route_sha256": value._sha(route_raw), "source_bindings_sha256": value._sha(source_raw),
                                                                        "allowance_policy": "owner_assumed_allowance_no_fresh_evidence"}))
    (accepted / "response.json").write_text(content, encoding="utf-8")
    (accepted / "provider-record.json").write_bytes(value._canonical(record))
    (accepted / "terminal.json").write_bytes(value._canonical({"state": "completed", "thread_id": "already-complete",
                                                              "response_sha256": value._sha(content.encode())}))
    runtime = DispatchRuntime(); install_dispatch_fakes(monkeypatch, value, runtime)

    result = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)

    assert result["skipped_ordinals"] == [ordinals[0]] and ordinals[0] not in runtime.calls
    (accepted / "response.json").write_text('{"verdicts":[]}', encoding="utf-8")
    request = {"ordinal": ordinals[0], "batch_number": ordinals[0], "question_ids": [f"q-{ordinals[0]}"],
               "prompt_sha256": value._sha(b"{}"), "schema_sha256": value._sha(b"{}")}
    with pytest.raises(ValueError, match="retained response|verdict identities"):
        value._completed(root, request, set(), runtime=runtime, manifest_sha256=manifest_sha)
    (accepted / "response.json").write_text(content, encoding="utf-8")
    (native / "payload" / "prompt.txt").write_bytes(b"wrong frozen story")
    with pytest.raises(ValueError, match="frozen request payload"):
        value._completed(root, request, set(), runtime=runtime, manifest_sha256=manifest_sha)
    (native / "payload" / "prompt.txt").write_bytes(b"{}")
    with pytest.raises(ValueError, match="precontact binding"):
        value._completed(root, request, set(), runtime=runtime, manifest_sha256="0" * 64)
    wrong_record = {**record, "native_thread_id": "wrong-thread"}
    (accepted / "provider-record.json").write_bytes(value._canonical(wrong_record))
    with pytest.raises(ValueError, match="lifecycle identity"):
        value._completed(root, request, set(), runtime=runtime, manifest_sha256=manifest_sha)

    rejected = tmp_path / "rejected"; campaign(value, rejected)
    slot = rejected / "requests" / f"{ordinals[0]:04d}"; slot.mkdir(parents=True)
    (slot / "terminal.json").write_bytes(value._canonical({"state": "stopped_no_retry", "thread_id": "unknown"}))
    with pytest.raises(ValueError, match="ambiguous"):
        value.dispatch(campaign_root=rejected, queue_root=tmp_path, adapter_override=DispatchRuntime())

    locked = tmp_path / "locked"; campaign(value, locked)
    (locked / ".collect.lock").write_bytes(b"foreign")
    with pytest.raises(ValueError, match="collection lock"):
        value.dispatch(campaign_root=locked, queue_root=tmp_path, adapter_override=DispatchRuntime())


def test_dispatch_stops_and_drains_after_failure_or_duplicate_prefix_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(EXECUTION, "dryad_selected_successor_execution_failure_test")
    root = tmp_path / "campaign"; ordinals = campaign(value, root)
    runtime = DispatchRuntime(fail_ordinal=ordinals[0]); install_dispatch_fakes(monkeypatch, value, runtime)

    result = value.dispatch(campaign_root=root, queue_root=tmp_path, adapter_override=runtime)

    assert result["state"] == "stopped_no_retry" and result["failures"] == [{"ordinal": ordinals[0], "error_type": "ValueError"}]
    assert runtime.maximum <= 10
    terminal = json.loads((root / "requests" / f"{ordinals[0]:04d}" / "terminal.json").read_bytes())
    assert terminal["state"] == "stopped_no_retry"

    duplicate = tmp_path / "duplicate"; campaign(value, duplicate, prefix_ids=["duplicate-thread"])
    duplicate_runtime = DispatchRuntime(identity="duplicate-thread")
    install_dispatch_fakes(monkeypatch, value, duplicate_runtime)
    duplicate_result = value.dispatch(campaign_root=duplicate, queue_root=tmp_path, adapter_override=duplicate_runtime)
    assert duplicate_result["state"] == "stopped_no_retry"
    assert duplicate_result["failures"][0]["error_type"] == "ValueError"
