from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v3"
QUEUE_ADAPTER_ROOT = Path(r"C:\Users\Haile\.codex\tools\model_work_queue\adapters")


def _adapter():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live_v3", ROOT / "executor.py")
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


def test_v3_identity_is_fresh_against_v2_and_run_root() -> None:
    adapter = _adapter()
    v2_path = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v2" / "executor.py"
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live_v2_for_identity", v2_path)
    assert spec and spec.loader
    v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v2)
    event_id = "feedback-v2-revision-v2-c1-hanna-1035-grok-4.6-cwr_guided"
    v3_a = adapter._successor_event_id(Path(r"C:\fresh-v3-a"), "cwr_feedback", event_id)
    v3_b = adapter._successor_event_id(Path(r"C:\fresh-v3-b"), "cwr_feedback", event_id)
    assert v3_a.startswith("exec-v3-") and v3_a != v3_b
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
    raw = _shared_adapter_bytes(_completed_envelope())
    adapter._persist_raw_stdout(root, raw); adapter._write_control_once(root / "adapter-control.json", raw)
    actual = {"prepared_record_sha256": "a" * 64, "launch_intent_sha256": "b" * 64, "frozen_manifest_sha256": "c" * 64, "provider_request_id": "grok-request-sha256:" + "d" * 64, "session_id": "grok-session-sha256:" + "e" * 64, "status": 200, "provider_model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "transmitted_payload_sha256": hashlib.sha256(adapter._read_outbound_payload(root, run_root=run, phase="revision_generation", event_id="fresh-event")[1]).hexdigest(), "returned_response_sha256": "f" * 64, "response": {"story": "x"}}
    adapter._write_grok_native_binding(root=root, run_root=run, native=actual)
    normalized = dict(actual); normalized["transmitted_payload_sha256"] = prepared["payload"]["sha256"]
    monkeypatch.setattr(adapter, "_receipt_from_control", lambda **_: actual)
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


def test_v2_terminal_root_is_a_no_resend_lineage_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    predecessor = adapter.contract()["predecessor"]
    assert predecessor["reconcile_or_resend"] is False and predecessor["provider_calls_made"] == predecessor["native_contacts"] == 0
    assert predecessor["adapter_control"]["detail"] == "output schema needs $schema_version=1"
    monkeypatch.setattr(adapter, "_pilot", lambda: None)
    with pytest.raises(ValueError, match="immutable v2 terminal run root"):
        adapter.prepare_one(run_root=adapter.V2_TERMINAL_RUN_ROOT, source_root=Path("unused"), phase="cwr_feedback", event_id="unused", acknowledgement_sha256="unused")
    assert adapter._successor_event_id(Path(r"C:\fresh-v3-run"), "cwr_feedback", "feedback-v2-x") != "feedback-v2-x"
