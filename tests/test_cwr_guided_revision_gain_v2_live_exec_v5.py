from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v5"
QUEUE_ADAPTER_ROOT = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\adapters")


def _adapter():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live_v5", ROOT / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _queue_adapter(name: str):
    spec = importlib.util.spec_from_file_location(f"fixture_{name}", QUEUE_ADAPTER_ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _adapter_preflight_argv(name: str, schema: dict[str, object], broker_root: Path) -> list[str]:
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    command = json.dumps([sys.executable])
    if name == "codex_exec":
        return ["--codex-command-json", command, "--model", "gpt-5.6-sol", "--reasoning-effort", "high", "--output-schema-json", encoded, "--expected-command-identity-json", "{}", "--cli-version-command-json", command, "--expected-cli-version-identity-json", "{}", "--expected-cli-version", "fixture", "--auth-status-command-json", command, "--expected-auth-status-identity-json", "{}", "--auth-receipt-json", "{}", "--broker-root", str(broker_root), "--timeout-seconds", "1"]
    return ["--grok-command-json", command, "--model", "grok-4.6", "--reported-model", "grok-4.6-build", "--reasoning-effort", "high", "--output-schema-json", encoded, "--expected-command-identity-json", "{}", "--cli-version-command-json", command, "--expected-cli-version-identity-json", "{}", "--expected-cli-version", "fixture", "--subscription-receipt-json", "{}", "--broker-root", str(broker_root), "--timeout-seconds", "1", "--nonvisual-max-turns", "1"]


def _prepared_root(adapter, tmp_path: Path) -> tuple[Path, Path]:
    run = tmp_path / "run"
    root = run / "live-cells" / "cwr_feedback" / "fresh-event"
    root.mkdir(parents=True)
    prepared = {"work_root": str(run.resolve()), "phase": "cwr_feedback", "event_id": "fresh-event", "acknowledgement_sha256": adapter.contract()["authorized_acknowledgement_sha256"]}
    payload = {"event_id": "fresh-event", "role": "cwr_feedback", "response_schema": {"type": "object", "additionalProperties": False, "properties": {"findings": {"type": "array"}}, "required": ["findings"]}}
    adapter._write_once(root / "payload.json", payload)
    adapter._write_once(root / "prepared-cell.json", prepared)
    adapter._write_once(root / "governed-route-proof.json", {"fixture": True})
    outbound = adapter._prepare_outbound_payload(root, run_root=run, phase="cwr_feedback", event_id="fresh-event")
    schema = adapter._persist_adapter_schema_binding(run_root=run, root=root, prepared=prepared)
    route = adapter._commitment(run, root / "governed-route-proof.json")
    admission = {"format_version": 1, "study_id": adapter.STUDY_ID, "kind": "provider_free_prepared_cell", "pilot_commit": adapter.contract()["pilot"]["commit"], "phase": "cwr_feedback", "event_id": "fresh-event", "successor_event_id": outbound["identity"]["successor_event_id"], "logical_sample_id": outbound["identity"]["logical_sample_id"], "outbound_payload": outbound["payload"], "adapter_schema": schema, "predecessor_terminal_lineage": adapter.contract()["predecessor"], "authorized_acknowledgement_sha256": prepared["acknowledgement_sha256"], "route_evidence": route, "prepared_root": str(root.resolve()), "prepared": prepared, "provider_calls_made": 0}
    adapter._write_once(root / "live-admission.json", admission)
    return run, root


def _install_prelaunch_fixtures(adapter, monkeypatch: pytest.MonkeyPatch, run: Path, root: Path) -> tuple[list[Path], list[object]]:
    begun: list[Path] = []
    launches: list[object] = []

    class Pilot:
        def _validate_current_prepared(self, *, prepared_root: Path, prepared: object) -> None:
            assert prepared_root == root

        def begin_one_launch(self, *, prepared_root: Path) -> None:
            begun.append(prepared_root)

        def record_terminal_outcome(self, *, prepared_root: Path, process_launches: int, settled: bool) -> dict[str, object]:
            assert prepared_root == root and process_launches == 0 and settled is False
            return {"state": "terminal_precontact"}

    monkeypatch.setattr(adapter, "_pilot", lambda: Pilot())
    monkeypatch.setattr(adapter, "_reauth_route", lambda **_: (None, {}))
    monkeypatch.setattr(adapter, "_build_invocation", lambda **_: (["fixture"], b"{}", 1))
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *args, **kwargs: launches.append((args, kwargs)))
    return begun, launches


@pytest.mark.parametrize("orphan", [
    "adapter-stdout.raw", "adapter-stdout-binding.json", "adapter-stderr.raw",
    "adapter-stderr-binding.json", "adapter-control.json", "adapter-native-binding.json",
    "execution-result.json", "terminal-outcome.json", "reconciliation.json",
    "verified-receipt.json", "reconciled-verified-receipt.json", "feedback-ingest.json",
    "revision-record.json", "endpoint-ingest.json", "launch-intent.json",
])
def test_orphan_terminal_artifacts_reject_before_intent_or_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, orphan: str) -> None:
    adapter = _adapter()
    run, root = _prepared_root(adapter, tmp_path)
    (root / orphan).write_bytes(b"orphan")
    begun, launches = _install_prelaunch_fixtures(adapter, monkeypatch, run, root)
    if orphan == "launch-intent.json":
        with pytest.raises(ValueError, match="inventory"):
            adapter.execute_one(run_root=run, phase="cwr_feedback", event_id="fresh-event", allow_remote=True)
    else:
        result = adapter.execute_one(run_root=run, phase="cwr_feedback", event_id="fresh-event", allow_remote=True)
        assert result["state"] == "terminal_precontact" and result["provider_calls_made"] == 0
    assert begun == [] and launches == []
    assert (root / "terminal-outcome.json").exists() is (orphan == "terminal-outcome.json")


def test_extra_file_and_directory_reject_before_intent_or_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    for name, directory in (("extra.txt", False), ("extra", True)):
        run, root = _prepared_root(adapter, tmp_path / name)
        extra = root / name
        if directory:
            extra.mkdir()
        else:
            extra.write_bytes(b"extra")
        begun, launches = _install_prelaunch_fixtures(adapter, monkeypatch, run, root)
        result = adapter.execute_one(run_root=run, phase="cwr_feedback", event_id="fresh-event", allow_remote=True)
        assert result["state"] == "terminal_precontact" and begun == [] and launches == []


def test_expected_artifact_reparse_rejects_before_intent_or_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    run, root = _prepared_root(adapter, tmp_path)
    payload = root / "payload.json"
    target = tmp_path / "payload-target.json"
    target.write_bytes(payload.read_bytes())
    payload.unlink()
    try:
        payload.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    begun, launches = _install_prelaunch_fixtures(adapter, monkeypatch, run, root)
    result = adapter.execute_one(run_root=run, phase="cwr_feedback", event_id="fresh-event", allow_remote=True)
    assert result["state"] == "terminal_precontact" and begun == [] and launches == []


def test_settled_inventory_is_provider_and_phase_specific_for_authority_rereads(tmp_path: Path) -> None:
    adapter = _adapter()
    names = adapter._PREPARED_ROOT_FILES | adapter._SETTLED_ROOT_FILES | frozenset({"feedback-ingest.json"})
    sol_root = tmp_path / "sol" / "live-cells" / "cwr_feedback" / "fresh-event"
    sol_root.mkdir(parents=True)
    for name in names:
        (sol_root / name).write_bytes(b"{}\n")
    adapter._validate_cell_inventory(root=sol_root, state="settled", phase="cwr_feedback", provider_model="gpt-5.6-sol")
    (sol_root / "adapter-native-binding.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        adapter._validate_cell_inventory(root=sol_root, state="settled", phase="cwr_feedback", provider_model="gpt-5.6-sol")

    grok_root = tmp_path / "grok" / "live-cells" / "cwr_feedback" / "fresh-event"
    grok_root.mkdir(parents=True)
    for name in names:
        (grok_root / name).write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        adapter._validate_cell_inventory(root=grok_root, state="settled", phase="cwr_feedback", provider_model="grok-4.6")
    (grok_root / "adapter-native-binding.json").write_bytes(b"{}\n")
    adapter._validate_cell_inventory(root=grok_root, state="settled", phase="cwr_feedback", provider_model="grok-4.6")
    (grok_root / "revision-record.json").write_bytes(b"{}\n")
    with pytest.raises(ValueError, match="inventory"):
        adapter._validate_cell_inventory(root=grok_root, state="settled", phase="cwr_feedback", provider_model="grok-4.6")


def test_reconcile_pending_inventory_preserves_grok_native_binding_but_rejects_it_for_sol(tmp_path: Path) -> None:
    adapter = _adapter()
    names = adapter._PREPARED_ROOT_FILES | adapter._RECONCILE_PENDING_FILES | frozenset({"adapter-native-binding.json"})
    root = tmp_path / "run" / "live-cells" / "revision_generation" / "fresh-event"
    root.mkdir(parents=True)
    for name in names:
        (root / name).write_bytes(b"{}\n")
    adapter._validate_cell_inventory(root=root, state="reconcile_pending", phase="revision_generation", provider_model="grok-4.6")
    with pytest.raises(ValueError, match="inventory"):
        adapter._validate_cell_inventory(root=root, state="reconcile_pending", phase="revision_generation", provider_model="gpt-5.6-sol")


def test_real_shared_adapter_preflight_accepts_decorated_schemas_without_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    pilot = adapter._pilot()
    underlying = [
        json.loads(pilot._asset("cwr-feedback.schema.json", pilot.contract()["assets"]["cwr-feedback.schema.json"]).decode("utf-8")),
        adapter._REVISION_RESPONSE_SCHEMA,
        json.loads(pilot._asset("score.schema.json", pilot.contract()["assets"]["score.schema.json"]).decode("utf-8")),
    ]
    for name in ("codex_exec", "grok_exec"):
        queue_adapter = _queue_adapter(name)
        launches: list[object] = []
        monkeypatch.setattr(queue_adapter.subprocess, "Popen", lambda *args, **kwargs: launches.append((args, kwargs)))
        for schema in underlying:
            decorated = adapter._decorate_adapter_schema(schema)
            sink = io.StringIO()
            code = queue_adapter.run(_adapter_preflight_argv(name, decorated, tmp_path), stdin=io.BytesIO(adapter.canonical({"prompt": "caf\u00e9\nfixture"})), stdout=sink)
            control = json.loads(sink.getvalue())
            assert code == 0 and control["control"]["state"] == "definitely_not_contacted"
            assert "output schema needs" not in control["control"]["detail"]
            assert "identity" in control["control"]["detail"]
        assert launches == []


def test_v2_undecorated_schema_fails_shared_adapter_preflight_before_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    queue_adapter = _queue_adapter("codex_exec")
    launches: list[object] = []
    monkeypatch.setattr(queue_adapter.subprocess, "Popen", lambda *args, **kwargs: launches.append((args, kwargs)))
    sink = io.StringIO()
    code = queue_adapter.run(_adapter_preflight_argv("codex_exec", adapter._REVISION_RESPONSE_SCHEMA, tmp_path), stdin=io.BytesIO(adapter.canonical({"prompt": "fixture"})), stdout=sink)
    assert code == 0 and json.loads(sink.getvalue()) == {"control": {"detail": "output schema needs $schema_version=1", "state": "definitely_not_contacted", "version": 1}}
    assert launches == []


def test_schema_binding_and_invocation_preserve_pilot_schema_and_canonical_prompt(tmp_path: Path) -> None:
    adapter = _adapter()
    pilot = adapter._pilot()
    schemas = {
        "cwr_feedback": json.loads(pilot._asset("cwr-feedback.schema.json", pilot.contract()["assets"]["cwr-feedback.schema.json"]).decode("utf-8")),
        "revision_generation": adapter._REVISION_RESPONSE_SCHEMA,
        "blind_endpoint_judgment": json.loads(pilot._asset("score.schema.json", pilot.contract()["assets"]["score.schema.json"]).decode("utf-8")),
    }
    for phase, underlying in schemas.items():
        run = tmp_path / phase; root = run / "live-cells" / phase / "fresh-event"; root.mkdir(parents=True)
        payload = {"event_id": "fresh-event", "role": phase}
        if phase != "revision_generation":
            payload["response_schema"] = underlying
        (root / "payload.json").write_bytes(adapter.canonical(payload) + b"\n")
        prepared = {"work_root": str(run.resolve()), "phase": phase, "event_id": "fresh-event"}
        adapter._prepare_outbound_payload(root, run_root=run, phase=phase, event_id="fresh-event")
        adapter._persist_adapter_schema_binding(run_root=run, root=root, prepared=prepared)
        decorated = adapter._read_adapter_schema(run_root=run, root=root, prepared=prepared)
        assert decorated["$schema_version"] == 1
        assert {key: value for key, value in decorated.items() if key != "$schema_version"} == underlying
        assert set(decorated) == {"$schema_version", *underlying}
        if phase == "cwr_feedback":
            binding_path = root / "adapter-schema-binding.json"
            original_binding = binding_path.read_bytes()
            binding = json.loads(original_binding.decode("utf-8"))
            binding["adapter_output_schema"]["properties"] = {}
            binding_path.write_bytes(adapter.canonical(binding) + b"\n")
            with pytest.raises(ValueError, match="schema binding drifted"):
                adapter._read_adapter_schema(run_root=run, root=root, prepared=prepared)
            binding_path.write_bytes(original_binding)
    root = tmp_path / "cwr_feedback" / "live-cells" / "cwr_feedback" / "fresh-event"
    prepared = {"work_root": str((tmp_path / "cwr_feedback").resolve()), "phase": "cwr_feedback", "event_id": "fresh-event"}
    route = {"command": ["fixture"], "adapter": "codex_exec", "codex_command": ["fixture"], "model": "gpt-5.6-sol", "reasoning_effort": "high", "codex_command_identity": {}, "cli_version_command": ["fixture"], "cli_version_identity": {}, "codex_cli_version": "fixture", "auth_status_command": ["fixture"], "auth_status_identity": {}, "auth_receipt_hash": "a" * 64, "timeout_seconds": 1}
    command, stdin, timeout = adapter._build_invocation(broker=type("Broker", (), {"root": tmp_path, "_load_json_artifact": staticmethod(lambda _: {})})(), root=root, prepared=prepared, route=route)
    schema = json.loads(command[command.index("--output-schema-json") + 1])
    assert timeout == 1 and schema["$schema_version"] == 1
    assert stdin == adapter.canonical({"prompt": adapter._read_outbound_payload(root, run_root=Path(prepared["work_root"]), phase="cwr_feedback", event_id="fresh-event")[1].decode("utf-8")})


def test_predecessor_lineage_rejects_contract_tamper() -> None:
    adapter = _adapter()
    predecessor = copy.deepcopy(adapter.contract()["predecessor"])
    predecessor["native_contacts"] = 1
    with pytest.raises(ValueError, match="predecessor contract drifted"):
        adapter._validate_predecessor_lineage(predecessor)


def test_v4_identity_is_fresh_against_v2_and_run_root() -> None:
    adapter = _adapter()
    v2_path = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v2" / "executor.py"
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live_v2_for_identity", v2_path)
    assert spec and spec.loader
    v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v2)
    event_id = "feedback-v2-revision-v2-c1-hanna-1035-grok-4.6-cwr_guided"
    v3_a = adapter._successor_event_id(Path(r"C:\fresh-v3-a"), "cwr_feedback", event_id)
    v3_b = adapter._successor_event_id(Path(r"C:\fresh-v3-b"), "cwr_feedback", event_id)
    assert v3_a.startswith("exec-v4-") and v3_a != v3_b
    assert v3_a != v2._successor_event_id(Path(r"C:\fresh-v3-a"), "cwr_feedback", event_id)


def _shared_adapter_bytes(value: object, newline: bytes = b"\n") -> bytes:
    return json.dumps(value, sort_keys=True).encode("ascii") + newline


def _completed_envelope() -> dict[str, object]:
    return {"control": {"version": 1, "state": "completed"}, "result": {
        "schema_version": 1, "request_hash": "a" * 64,
        "output": {"story": "caf\u00e9"}, "output_hash": "b" * 64, "runtime": {},
    }}


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_accepts_exact_shared_adapter_serialization_and_preserves_unicode(tmp_path: Path, newline: bytes) -> None:
    adapter = _adapter()
    raw = _shared_adapter_bytes(_completed_envelope(), newline)
    assert b"caf\\u00e9" in raw and b"caf\xc3\xa9" not in raw
    state, result = adapter._control_from_adapter(raw)
    assert state == "completed" and result is not None and result["output"]["story"] == "caf\u00e9"
    root = tmp_path / "run" / "live-cells" / "revision_generation" / "fresh-event"
    root.mkdir(parents=True)
    raw_binding = adapter._persist_raw_stdout(root, raw)
    adapter._write_control_once(root / "adapter-control.json", raw)
    assert raw_binding == {"path": "live-cells/revision_generation/fresh-event/adapter-stdout.raw", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    bound = json.loads((root / "adapter-stdout-binding.json").read_text(encoding="utf-8"))
    assert bound["raw_stdout"] == raw_binding
    assert adapter._stored_adapter_stdout(root) == raw


@pytest.mark.parametrize("raw", [
    lambda value: adapter_canonical(value),
    lambda value: b"\xef\xbb\xbf" + _shared_adapter_bytes(value),
    lambda value: _shared_adapter_bytes(value) + b"\n",
    lambda value: _shared_adapter_bytes(value)[:-1],
])
def test_rejects_alternate_stdout_formats_after_raw_persistence(tmp_path: Path, raw) -> None:
    adapter = _adapter()
    value = _completed_envelope()
    payload = raw(value)
    root = tmp_path / "run" / "live-cells" / "revision_generation" / "fresh-event"
    root.mkdir(parents=True)
    adapter._persist_raw_stdout(root, payload)
    with pytest.raises(ValueError, match="stdout"):
        adapter._control_from_adapter(payload)
    assert (root / "adapter-stdout.raw").read_bytes() == payload


def adapter_canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"


def test_execute_persists_raw_stdout_before_terminal_parse_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    root = tmp_path / "run" / "live-cells" / "cwr_feedback" / "fresh-event"
    root.mkdir(parents=True)

    class Pilot:
        def begin_one_launch(self, *, prepared_root: Path) -> None:
            assert prepared_root == root

        def record_terminal_outcome(self, *, prepared_root: Path, process_launches: int, settled: bool) -> dict[str, object]:
            assert prepared_root == root and process_launches == 1 and settled is False
            return {"state": "terminal_postlaunch_reconcile_required"}

    malformed = b'{"control": {"state": "completed"}}\n'
    monkeypatch.setattr(adapter, "_pilot", lambda: Pilot())
    monkeypatch.setattr(adapter, "_reauth_admission", lambda **_: ({"route_evidence": {"sha256": "a" * 64}}, {"provider_model": "gpt-5.6-sol"}))
    monkeypatch.setattr(adapter, "_reauth_route", lambda **_: (None, {}))
    monkeypatch.setattr(adapter, "_build_invocation", lambda **_: (["fixture"], b"{}", 1))
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=malformed))
    result = adapter.execute_one(run_root=tmp_path / "run", phase="cwr_feedback", event_id="fresh-event", allow_remote=True)
    assert result["state"] == "terminal_postlaunch_reconcile_required"
    assert (root / "adapter-stdout.raw").read_bytes() == malformed
    assert not (root / "adapter-control.json").exists()


def test_timeout_persists_partial_stdout_and_stderr_without_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    root = tmp_path / "run" / "live-cells" / "cwr_feedback" / "fresh-event"
    root.mkdir(parents=True)

    class Pilot:
        def begin_one_launch(self, *, prepared_root: Path) -> None:
            assert prepared_root == root

        def record_terminal_outcome(self, *, prepared_root: Path, process_launches: int, settled: bool) -> dict[str, object]:
            assert prepared_root == root and process_launches == 1 and settled is False
            return {"state": "terminal_postlaunch_reconcile_required"}

    timeout = subprocess.TimeoutExpired(["fixture"], 1, output=b"partial stdout", stderr=b"partial stderr")
    monkeypatch.setattr(adapter, "_pilot", lambda: Pilot())
    monkeypatch.setattr(adapter, "_reauth_admission", lambda **_: ({"route_evidence": {"sha256": "a" * 64}}, {"provider_model": "gpt-5.6-sol"}))
    monkeypatch.setattr(adapter, "_reauth_route", lambda **_: (None, {}))
    monkeypatch.setattr(adapter, "_build_invocation", lambda **_: (["fixture"], b"{}", 1))
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *_a, **_k: (_ for _ in ()).throw(timeout))
    result = adapter.execute_one(run_root=tmp_path / "run", phase="cwr_feedback", event_id="fresh-event", allow_remote=True)
    assert result["state"] == "terminal_postlaunch_reconcile_required"
    assert result["provider_calls_made"] == result["native_contacts"] == "unproven"
    assert {row["stream"] for row in result["partial_adapter_streams"]} == {"stdout", "stderr"}
    assert (root / "adapter-stdout.raw").read_bytes() == b"partial stdout"
    assert (root / "adapter-stderr.raw").read_bytes() == b"partial stderr"
    assert (root / "adapter-stdout-binding.json").exists() and (root / "adapter-stderr-binding.json").exists()
    assert json.loads((root / "adapter-stdout-binding.json").read_text(encoding="utf-8"))["raw_stdout"]["bytes"] == len(b"partial stdout")
    assert json.loads((root / "adapter-stderr-binding.json").read_text(encoding="utf-8"))["raw_stderr"]["bytes"] == len(b"partial stderr")
    assert not (root / "adapter-control.json").exists() and not (root / "verified-receipt.json").exists()


def test_raw_stdout_binding_tamper_is_rejected(tmp_path: Path) -> None:
    adapter = _adapter()
    raw = _shared_adapter_bytes(_completed_envelope())
    root = tmp_path / "run" / "live-cells" / "revision_generation" / "fresh-event"
    root.mkdir(parents=True)
    adapter._persist_raw_stdout(root, raw)
    adapter._write_control_once(root / "adapter-control.json", raw)
    (root / "adapter-stdout.raw").write_bytes(raw.replace(b"request_hash", b"requestXhash"))
    with pytest.raises(ValueError, match="raw stdout binding"):
        adapter._stored_adapter_stdout(root)


def test_outbound_payload_carries_fresh_v3_identity(tmp_path: Path) -> None:
    adapter = _adapter()
    run = tmp_path / "fresh-run"; root = run / "live-cells" / "cwr_feedback" / "feedback-v2-original"
    root.mkdir(parents=True)
    pilot_payload = {"event_id": "feedback-v2-original", "source_text": "immutable source"}
    (root / "payload.json").write_bytes(adapter.canonical(pilot_payload) + b"\n")
    outbound = adapter._prepare_outbound_payload(root, run_root=run, phase="cwr_feedback", event_id="feedback-v2-original")
    identity, raw = adapter._read_outbound_payload(root, run_root=run, phase="cwr_feedback", event_id="feedback-v2-original")
    assert outbound["identity"] == identity
    assert identity["study_id"] == adapter.STUDY_ID and identity["successor_event_id"] != "feedback-v2-original"
    assert raw != (root / "payload.json").read_bytes()
    assert json.loads(raw.decode("utf-8"))["pilot_payload"] == pilot_payload


def test_grok_receipt_authority_rederives_from_bound_raw_stdout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    run = tmp_path / "fresh-run"; root = run / "live-cells" / "revision_generation" / "fresh-event"
    root.mkdir(parents=True)
    prepared = {"work_root": str(run.resolve()), "phase": "revision_generation", "event_id": "fresh-event", "payload": {"sha256": "1" * 64}}
    (root / "payload.json").write_bytes(adapter.canonical({"event_id": "fresh-event"}) + b"\n")
    adapter._prepare_outbound_payload(root, run_root=run, phase="revision_generation", event_id="fresh-event")
    actual = {"prepared_record_sha256": "a" * 64, "launch_intent_sha256": "b" * 64, "frozen_manifest_sha256": "c" * 64, "provider_request_id": "grok-request-sha256:" + "d" * 64, "session_id": "grok-session-sha256:" + "e" * 64, "status": 200, "provider_model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "transmitted_payload_sha256": hashlib.sha256(adapter._read_outbound_payload(root, run_root=run, phase="revision_generation", event_id="fresh-event")[1]).hexdigest(), "returned_response_sha256": "f" * 64, "response": {"story": "x"}}
    runtime = {"command_identity": {"version": 1, "artifacts": []}, "command_identity_hash": "a" * 64}
    raw_value = _completed_envelope(); raw_value["result"]["runtime"] = runtime
    raw = _shared_adapter_bytes(raw_value)
    adapter._persist_raw_stdout(root, raw); adapter._write_control_once(root / "adapter-control.json", raw)
    adapter._write_grok_native_binding(root=root, run_root=run, native=actual, route={"grok_command_identity": runtime["command_identity"]}, control_raw=raw)
    normalized = dict(actual); normalized["transmitted_payload_sha256"] = prepared["payload"]["sha256"]
    monkeypatch.setattr(adapter, "_receipt_from_control", lambda **_: actual)
    monkeypatch.setattr(adapter, "_read_admission", lambda **_: ({"route_evidence": {}}, prepared))
    monkeypatch.setattr(adapter, "_reauth_route", lambda **_: (None, {"grok_command_identity": runtime["command_identity"]}))
    adapter._verify_grok_native_binding(pilot=object(), root=root, prepared=prepared, verified={"native_receipt": normalized})
    (root / "adapter-stdout.raw").write_bytes(raw + b"x")
    with pytest.raises(ValueError, match="raw stdout binding"):
        adapter._verify_grok_native_binding(pilot=object(), root=root, prepared=prepared, verified={"native_receipt": normalized})


def test_projection_requires_all_forty_authorities_from_one_run_and_target_freeze() -> None:
    adapter = _adapter()
    common = {"run_root": "C:/fresh-run", "frozen_inputs_sha256": "a" * 64, "target_root": "C:/fresh-targets", "target_manifest": {"path": "target-manifest.json", "bytes": 10, "sha256": "b" * 64}}
    assert adapter._require_single_projection_boundary([dict(common) for _ in range(40)]) == common
    spliced = [dict(common) for _ in range(40)]
    spliced[-1] = {**common, "target_root": "C:/other-targets"}
    with pytest.raises(ValueError, match="splices multiple runs or target freezes"):
        adapter._require_single_projection_boundary(spliced)


def test_v3_terminal_root_is_a_no_resend_lineage_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    predecessor = adapter.contract()["predecessor"]
    assert predecessor["reconcile_or_resend"] is False and len(predecessor["terminal_inventory_sha256"]) == 4
    monkeypatch.setattr(adapter, "_pilot", lambda: None)
    with pytest.raises(ValueError, match="overlaps immutable predecessor evidence"):
        adapter.prepare_one(run_root=adapter.V3_TERMINAL_RUN_ROOT, source_root=Path("unused"), phase="cwr_feedback", event_id="unused", acknowledgement_sha256="unused")
    assert adapter._successor_event_id(Path(r"C:\fresh-v4-run"), "cwr_feedback", "feedback-v2-x") != "feedback-v2-x"


def _grok_receipt_fixture(adapter, root: Path, *, payload: bytes, event_id: str = "revision-fixture") -> tuple[dict[str, object], dict[str, object], bytes]:
    root.mkdir(parents=True)
    identity = {"version": 1, "artifacts": [{"index": 0, "path_hash": "1" * 64, "sha256": "2" * 64}]}
    receipt_hash = "3" * 64
    runtime = {
        "adapter_version": 1,
        "requested_model": "grok-4.6",
        "reported_model": "grok-4.6-build",
        "requested_reasoning_effort": "high",
        "reasoning_attested": False,
        "reasoning_attestation": "not_reported_by_grok_build_cli",
        "identity_evidence": "requested_only",
        "cli_version": "fixture",
        "session_id_hash": "4" * 64,
        "request_id_hash": "5" * 64,
        "observed_turns": 1,
        "envelope_hash": "6" * 64,
        "command_identity": identity,
        "command_identity_hash": "7" * 64,
        "subscription_receipt_hash": receipt_hash,
        "execution_policy": "bounded_nonvisual_read_only",
        "usage_telemetry": {"status": "reported"},
        "nonvisual_max_turns": 1,
    }
    response = {"story": "fixture"}
    envelope = {"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": hashlib.sha256(adapter.canonical({"prompt": payload.decode("utf-8")})).hexdigest(), "output": response, "output_hash": hashlib.sha256(adapter.canonical(response)).hexdigest(), "runtime": runtime}}
    raw = _shared_adapter_bytes(envelope)
    prepared = {"work_root": str(root.parent.parent.parent.resolve()), "phase": "revision_generation", "event_id": event_id, "provider_model": "grok-4.6", "reasoning": "high", "frozen_manifest_sha256": "8" * 64}
    adapter._write_once(root / "prepared-cell.json", prepared)
    adapter._write_once(root / "launch-intent.json", {"fixture": True})
    adapter._write_once(root / "governed-route-proof.json", {"route_receipt_sha256": receipt_hash})
    return prepared, {"grok_command_identity": identity}, raw


def test_v4_accepts_command_identity_while_v3_rejects_its_ephemeral_hash_domain(tmp_path: Path) -> None:
    adapter = _adapter()
    pilot = SimpleNamespace(canonical=adapter.canonical)
    payload = b'{"successor":"v4"}\n'
    root = tmp_path / "v4" / "live-cells" / "revision_generation" / "revision-fixture"
    prepared, route, raw = _grok_receipt_fixture(adapter, root, payload=payload)
    accepted = adapter._receipt_from_control(pilot=pilot, root=root, prepared=prepared, route=route, control_raw=raw, payload_override=payload)
    assert accepted["provider_request_id"].startswith("grok-request-sha256:")

    v3_path = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v3" / "executor.py"
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live_v3_identity_rejection", v3_path)
    assert spec and spec.loader
    v3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v3)
    old_root = tmp_path / "v3" / "live-cells" / "revision_generation" / "revision-fixture"
    old_payload = {"fixture": "v3"}
    old_root.mkdir(parents=True)
    v3._write_once(old_root / "payload.json", old_payload)
    old_prepared = {**prepared, "work_root": str((tmp_path / "v3").resolve())}
    v3._write_once(old_root / "prepared-cell.json", old_prepared)
    v3._prepare_outbound_payload(old_root, run_root=tmp_path / "v3", phase="revision_generation", event_id="revision-fixture")
    old_payload_raw = (old_root / "outbound-payload.json").read_bytes()
    _, _, old_raw = _grok_receipt_fixture(v3, old_root / "scratch", payload=old_payload_raw)
    old_value = json.loads(old_raw.decode("ascii"))
    old_value["result"]["runtime"]["command_identity_hash"] = "7" * 64
    old_value["result"]["runtime"]["subscription_receipt_hash"] = "3" * 64
    old_value["result"]["request_hash"] = hashlib.sha256(v3.canonical({"prompt": old_payload_raw.decode("utf-8")})).hexdigest()
    old_value["result"]["output_hash"] = hashlib.sha256(v3.canonical(old_value["result"]["output"])).hexdigest()
    v3._write_once(old_root / "launch-intent.json", {"fixture": True})
    v3._write_once(old_root / "governed-route-proof.json", {"route_receipt_sha256": "3" * 64, "expected_adapter_runtime_identity_sha256": "9" * 64})
    with pytest.raises(ValueError, match="Grok completion identity drifted"):
        v3._receipt_from_control(pilot=SimpleNamespace(canonical=v3.canonical), root=old_root, prepared=old_prepared, control_raw=_shared_adapter_bytes(old_value))


@pytest.mark.parametrize("mutator", [
    lambda result, route: result["runtime"].__setitem__("command_identity", {"version": 1, "artifacts": []}),
    lambda result, route: result["runtime"].__setitem__("request_id_hash", "not-hex"),
    lambda result, route: result["runtime"].__setitem__("session_id_hash", result["runtime"]["request_id_hash"]),
    lambda result, route: result["runtime"].__setitem__("requested_model", "wrong-model"),
    lambda result, route: result["runtime"].__setitem__("subscription_receipt_hash", "f" * 64),
    lambda result, route: result.__setitem__("output_hash", "f" * 64),
])
def test_v4_grok_receipt_rejects_identity_and_receipt_tampering(tmp_path: Path, mutator) -> None:
    adapter = _adapter()
    payload = b'{"successor":"v4"}\n'
    root = tmp_path / "run" / "live-cells" / "revision_generation" / "revision-fixture"
    prepared, route, raw = _grok_receipt_fixture(adapter, root, payload=payload)
    value = json.loads(raw.decode("ascii"))
    mutator(value["result"], route)
    with pytest.raises(ValueError):
        adapter._receipt_from_control(pilot=SimpleNamespace(canonical=adapter.canonical), root=root, prepared=prepared, route=route, control_raw=_shared_adapter_bytes(value), payload_override=payload)


def test_fresh_grok_reconciliation_retries_only_from_exact_reconciling_inventory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    run = tmp_path / "fresh-run"; root = run / "live-cells" / "revision_generation" / "fresh-event"
    root.mkdir(parents=True)
    for name in adapter._PREPARED_ROOT_FILES | frozenset({"launch-intent.json", "terminal-outcome.json"}):
        adapter._write_once(root / name, {})
    runtime = {"command_identity": {"version": 1, "artifacts": []}, "command_identity_hash": "a" * 64}
    raw_value = _completed_envelope(); raw_value["result"]["runtime"] = runtime
    raw = _shared_adapter_bytes(raw_value)
    adapter._persist_raw_stdout(root, raw); adapter._write_control_once(root / "adapter-control.json", raw)
    prepared = {"work_root": str(run.resolve()), "phase": "revision_generation", "event_id": "fresh-event", "provider_model": "grok-4.6", "reasoning": "high", "payload": {"sha256": "1" * 64}}
    (root / "prepared-cell.json").unlink()
    adapter._write_once(root / "prepared-cell.json", prepared)
    native = {"prepared_record_sha256": "a" * 64, "launch_intent_sha256": "b" * 64, "frozen_manifest_sha256": "c" * 64, "provider_request_id": "grok-request-sha256:" + "d" * 64, "session_id": "grok-session-sha256:" + "e" * 64, "status": 200, "provider_model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "transmitted_payload_sha256": "f" * 64, "returned_response_sha256": "0" * 64, "response": {"story": "x"}}

    class Pilot:
        failures = 1

        def reconcile_postlaunch(self, *, prepared_root: Path, acknowledgement_sha256: str) -> None:
            assert acknowledgement_sha256 == adapter.contract()["authorized_acknowledgement_sha256"]
            adapter._write_once(prepared_root / "reconciliation.json", {})

        def validate_receipt(self, *, prepared_root: Path, receipt: object, output_path: Path) -> dict[str, object]:
            assert prepared_root == root and receipt
            if self.failures:
                self.failures -= 1
                raise ValueError("fixture validation failure")
            adapter._write_once(output_path, {"fixture": True})
            return {"provider_request_id": native["provider_request_id"]}

    pilot = Pilot()
    monkeypatch.setattr(adapter, "_pilot", lambda: pilot)
    def read_admission(**kwargs):
        if kwargs["inventory_state"] == "reconcile_pending" and (root / "reconciliation.json").exists():
            raise ValueError("fixture no longer pending")
        return {"route_evidence": {}}, prepared
    monkeypatch.setattr(adapter, "_read_admission", read_admission)
    monkeypatch.setattr(adapter, "_reauth_route", lambda **_: (None, {"grok_command_identity": runtime["command_identity"]}))
    monkeypatch.setattr(adapter, "_receipt_from_control", lambda **_: native)
    with pytest.raises(ValueError, match="fixture validation failure"):
        adapter.reconcile_existing_receipt(run_root=run, phase="revision_generation", event_id="fresh-event", reconciliation_acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"])
    adapter._validate_cell_inventory(root=root, state="reconciling", phase="revision_generation", provider_model="grok-4.6")
    with pytest.raises(ValueError, match="acknowledgement"):
        adapter.reconcile_existing_receipt(run_root=run, phase="revision_generation", event_id="fresh-event", reconciliation_acknowledgement_sha256="f" * 64)
    result = adapter.reconcile_existing_receipt(run_root=run, phase="revision_generation", event_id="fresh-event", reconciliation_acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"])
    assert result["provider_calls_made"] == result["process_launches"] == 0
    adapter._validate_cell_inventory(root=root, state="reconciled", phase="revision_generation", provider_model="grok-4.6")


def test_v5_import_materializes_four_exact_pilot_parent_records_without_source_mutation(tmp_path: Path) -> None:
    adapter = _adapter()
    source = adapter.V4_DERIVED_RUN_ROOT
    before = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    records, feedback = adapter.import_cycle_one(output_root=tmp_path / "v5-run")
    assert len(records) == 4 and len(feedback) == 2
    assert all(set(record) == {"event_id", "source", "parent", "descendant", "generator", "generator_receipt", "cwr_feedback"} and record["parent"] is None for record in records)
    pilot = adapter._imported_sol_reader(adapter._pilot())
    for record in records:
        pilot._read_verified_receipt(tmp_path / "v5-run" / record["generator_receipt"]["path"], expected_event_id=record["event_id"], expected_phase="revision_generation")
        if record["cwr_feedback"] is not None:
            pilot._read_verified_receipt(tmp_path / "v5-run" / record["cwr_feedback"]["verified_receipt"]["path"], expected_event_id=record["cwr_feedback"]["event_id"], expected_phase="cwr_feedback")
    assert before == {path: path.read_bytes() for path in before}


def test_v5_prepares_both_cycle_two_feedback_cells_from_imported_parents_without_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    run = tmp_path / "v5-run"
    records, _feedback = adapter.import_cycle_one(output_root=run)
    monkeypatch.setattr(adapter, "_governed_route", lambda *_args, **_kwargs: (None, {}, {"fixture": True}))
    source_root = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-preflight-20260820-d\work")
    events = ["feedback-v2-revision-v2-c2-hanna-1035-grok-4.6-cwr_guided", "feedback-v2-revision-v2-c2-hanna-178-grok-4.6-cwr_guided"]
    for event_id in events:
        prepared = adapter.prepare_one(run_root=run, source_root=source_root, phase="cwr_feedback", event_id=event_id, acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"], lineage_records=records)
        assert prepared["provider_calls_made"] == 0


def test_v5_prepares_both_generic_cycle_two_revisions_without_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); run = tmp_path / "v5-run"
    records, _ = adapter.import_cycle_one(output_root=run)
    monkeypatch.setattr(adapter, "_governed_route", lambda *_args, **_kwargs: (None, {}, {"fixture": True}))
    source_root = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-preflight-20260820-d\work")
    for event_id in ("revision-v2-c2-hanna-1035-grok-4.6-generic_no_feedback", "revision-v2-c2-hanna-178-grok-4.6-generic_no_feedback"):
        prepared = adapter.prepare_one(run_root=run, source_root=source_root, phase="revision_generation", event_id=event_id, acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"], lineage_records=records)
        assert prepared["provider_calls_made"] == 0


SOURCE_ROOT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-preflight-20260820-d\work")


def test_v5_auto_import_then_accepts_two_pilot_authenticated_cycle_two_feedbacks_and_freezes_all_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    monkeypatch.setattr(adapter, "_governed_route", lambda *_args, **_kwargs: (None, {}, {"fixture": True}))
    route = {"grok_command_identity": {"fixture": "grok-command"}}
    raw = _shared_adapter_bytes({"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": "0" * 64, "output": {}, "output_hash": "0" * 64, "runtime": {"command_identity": route["grok_command_identity"], "command_identity_hash": "a" * 64}}})
    monkeypatch.setattr(adapter, "_reauth_admission", lambda *, root, phase, event_id, **_: adapter._read_admission(root=root, phase=phase, event_id=event_id))
    monkeypatch.setattr(adapter, "_reauth_route", lambda **_: (None, route))
    monkeypatch.setattr(adapter, "_build_invocation", lambda **_: (["fixture"], b"{}", 1))
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=raw, stderr=b""))
    def local_sol_fixture(*, root: Path, prepared: dict[str, object], **_) -> dict[str, object]:
        response = {"findings": [{"location": "opening", "observation": "fixture observation", "repair_target": "fixture repair"}]}
        return {"format_version": 1, "study_id": adapter.STUDY_ID, "kind": "verified_local_codex_lifecycle_receipt", "evidence_class": "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1", "prepared_root": str(root.resolve()), "event_id": prepared["event_id"], "phase": prepared["phase"], "prepared_record_sha256": adapter._sha256((root / "prepared-cell.json").read_bytes()), "launch_intent_sha256": adapter._sha256((root / "launch-intent.json").read_bytes()), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_model": prepared["provider_model"], "reasoning": prepared["reasoning"], "tools_enabled": False, "payload_sha256": prepared["payload"]["sha256"], "response_sha256": adapter._sha256(adapter.canonical(response)), "response": response, "local_lifecycle": {"events_hash": "b" * 64, "raw_output_hash": "c" * 64, "thread_id_sha256": "d" * 64, "command_identity_hash": "e" * 64, "auth_receipt_hash": "f" * 64, "native_endpoint_contact_cardinality": "unproven"}}
    def grok_fixture(*, root: Path, prepared: dict[str, object], **_) -> dict[str, object]:
        response = {"story": f"Provider-free adapter fixture descendant for {prepared['event_id']}."}
        request_id = hashlib.sha256(f"request:{prepared['event_id']}".encode()).hexdigest()
        session_id = hashlib.sha256(f"session:{prepared['event_id']}".encode()).hexdigest()
        return {"prepared_record_sha256": adapter._sha256((root / "prepared-cell.json").read_bytes()), "launch_intent_sha256": adapter._sha256((root / "launch-intent.json").read_bytes()), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_request_id": f"grok-request-sha256:{request_id}", "session_id": f"grok-session-sha256:{session_id}", "status": 200, "provider_model": prepared["provider_model"], "reasoning": prepared["reasoning"], "tools_enabled": False, "transmitted_payload_sha256": prepared["payload"]["sha256"], "returned_response_sha256": adapter._sha256(adapter.canonical(response)), "response": response}
    monkeypatch.setattr(adapter, "_sol_lifecycle_verified", local_sol_fixture)
    monkeypatch.setattr(adapter, "_receipt_from_control", grok_fixture)
    run = tmp_path / "v5-run"
    feedback_events = ["feedback-v2-revision-v2-c2-hanna-1035-grok-4.6-cwr_guided", "feedback-v2-revision-v2-c2-hanna-178-grok-4.6-cwr_guided"]
    first = adapter.prepare_one(run_root=run, source_root=SOURCE_ROOT, phase="cwr_feedback", event_id=feedback_events[0], acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"])
    second = adapter.prepare_one(run_root=run, source_root=SOURCE_ROOT, phase="cwr_feedback", event_id=feedback_events[1], acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"])
    assert first["provider_calls_made"] == second["provider_calls_made"] == 0
    feedback_paths: dict[str, Path] = {}
    for event_id in feedback_events:
        root = run / "live-cells" / "cwr_feedback" / event_id
        assert adapter.execute_one(run_root=run, phase="cwr_feedback", event_id=event_id, allow_remote=True)["state"] == "settled"
        feedback_paths[event_id] = root / "verified-receipt.json"
    for event_id in feedback_events:
        assert adapter.ingest_feedback(run_root=run, event_id=event_id)["event_id"] == event_id
    cycle_one, _imported_feedback = adapter.import_cycle_one(output_root=run)
    cycle_two: list[dict[str, object]] = []
    pilot = adapter._imported_sol_reader(adapter._pilot())
    for event in pilot.revision_schedule():
        if event["cycle"] != 2:
            continue
        feedback_path = feedback_paths.get(event["cwr_feedback_event_id"])
        admission = adapter.prepare_one(run_root=run, source_root=SOURCE_ROOT, phase="revision_generation", event_id=event["event_id"], acknowledgement_sha256=adapter.contract()["authorized_acknowledgement_sha256"], lineage_records=cycle_one, feedback_receipt_path=feedback_path)
        assert admission["provider_calls_made"] == 0
        assert adapter.execute_one(run_root=run, phase="revision_generation", event_id=event["event_id"], allow_remote=True)["state"] == "settled"
        cycle_two.append(adapter.ingest_revision(run_root=run, event_id=event["event_id"], lineage_records=cycle_one, feedback_receipt_path=feedback_path))
    records = [*cycle_one, *cycle_two]
    validated = pilot.validate_revision_lineage(work_root=run, records=records)
    assert validated["record_count"] == 8
    manifest = adapter.freeze_targets(run_root=run, source_root=SOURCE_ROOT, lineage_records=records, target_root=tmp_path / "targets")
    assert len(manifest["targets"]) == 10
    for target in pilot.targets():
        pilot._target_from_manifest(tmp_path / "targets", tmp_path / "targets" / "target-manifest.json", target["blind_target_id"], manifest["frozen_manifest_sha256"])


def test_v5_import_rejects_tampered_pinned_sol_source_and_partial_or_missing_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    run = tmp_path / "v5-run"
    adapter.import_cycle_one(output_root=run)
    event_id = next(iter(adapter.V3_SOL_FEEDBACK_RECEIPTS))
    source_receipt = adapter.V3_TERMINAL_RUN_ROOT / "live-cells" / "cwr_feedback" / event_id / "verified-receipt.json"
    stable_bytes = adapter._stable_bytes
    def forged_source(path: Path, *, label: str) -> bytes:
        raw = stable_bytes(path, label=label)
        return raw + b"x" if Path(path).resolve() == source_receipt.resolve() else raw
    monkeypatch.setattr(adapter, "_stable_bytes", forged_source)
    with pytest.raises(ValueError, match="immutable v3 Sol feedback receipt drifted"):
        adapter.import_cycle_one(output_root=run)
    monkeypatch.undo()
    imported = run / "imports" / "cwr_feedback" / f"{event_id}.json"
    original = imported.read_bytes()
    altered = json.loads(original.decode("utf-8")); altered["response"] = {"findings": []}
    imported.write_bytes(adapter.canonical(altered) + b"\n")
    with pytest.raises(ValueError, match="imported Sol feedback drifted"):
        adapter.import_cycle_one(output_root=run)
    imported.write_bytes(original)
    imported.unlink()
    with pytest.raises(ValueError, match="incomplete or has extra artifacts"):
        adapter.import_cycle_one(output_root=run)
    partial = tmp_path / "partial"; partial.mkdir()
    with pytest.raises(ValueError, match="must be fresh"):
        adapter.import_cycle_one(output_root=partial)
    complete = tmp_path / "complete"
    adapter.import_cycle_one(output_root=complete)
    (complete / "imports" / "unexpected-empty-directory").mkdir()
    with pytest.raises(ValueError, match="incomplete or has extra artifacts"):
        adapter.import_cycle_one(output_root=complete)


def test_v5_import_rejects_rederived_v4_grok_receipt_forgery(tmp_path: Path) -> None:
    adapter = _adapter()
    run = tmp_path / "v5-run"
    records, _ = adapter.import_cycle_one(output_root=run)
    imported = run / records[0]["generator_receipt"]["path"]
    forged = json.loads(imported.read_text(encoding="utf-8"))
    forged["provider_request_id"] = "forged-request"
    forged["session_id"] = "forged-session"
    forged["native_receipt"]["provider_request_id"] = "forged-request"
    forged["native_receipt"]["session_id"] = "forged-session"
    imported.write_bytes(adapter.canonical(forged) + b"\n")
    with pytest.raises(ValueError, match="imported Grok receipt binding drifted"):
        adapter.import_cycle_one(output_root=run)


def test_v5_import_root_and_prepare_reject_immutable_overlap_and_reparse_before_writes(tmp_path: Path) -> None:
    adapter = _adapter()
    for immutable in (adapter.V3_TERMINAL_RUN_ROOT, adapter.V4_DERIVED_RUN_ROOT):
        descendant = immutable / "must-not-create-v5"
        for root in (immutable, immutable.parent, descendant):
            with pytest.raises(ValueError, match="overlaps immutable predecessor evidence"):
                adapter.import_cycle_one(output_root=root)
            with pytest.raises(ValueError, match="overlaps immutable predecessor evidence"):
                adapter.prepare_one(run_root=root, source_root=SOURCE_ROOT, phase="cwr_feedback", event_id="unused", acknowledgement_sha256="unused")
        assert not descendant.exists()
    target = tmp_path / "target"; target.mkdir()
    link = tmp_path / "reparse"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable on this Windows host")
    with pytest.raises(ValueError, match="unsafe or reparsed ancestry"):
        adapter.import_cycle_one(output_root=link / "output")
    with pytest.raises(ValueError, match="unsafe or reparsed ancestry"):
        adapter.prepare_one(run_root=link / "output", source_root=SOURCE_ROOT, phase="cwr_feedback", event_id="unused", acknowledgement_sha256="unused")
    assert not (target / "output").exists()


def test_v5_v4_source_inventory_rejects_extra_directory_without_mutating_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    copied = tmp_path / "v4-copy"
    shutil.copytree(adapter.V4_DERIVED_RUN_ROOT, copied)
    monkeypatch.setattr(adapter, "V4_DERIVED_RUN_ROOT", copied)
    (copied / "unexpected-empty-directory").mkdir()
    with pytest.raises(ValueError, match="immutable v4 import inventory drifted"):
        adapter._validate_v4_import_root()
