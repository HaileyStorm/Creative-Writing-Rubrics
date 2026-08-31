from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v2"


def _adapter():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live_v2", ROOT / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_outbound_payload_carries_fresh_v2_identity(tmp_path: Path) -> None:
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


def test_v1_terminal_root_is_a_no_resend_lineage_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    predecessor = adapter.contract()["predecessor"]
    assert predecessor["reconcile_or_resend"] is False and len(predecessor["terminal_cells"]) == 2
    monkeypatch.setattr(adapter, "_pilot", lambda: None)
    with pytest.raises(ValueError, match="immutable v1 terminal run root"):
        adapter.prepare_one(run_root=adapter.V1_TERMINAL_RUN_ROOT, source_root=Path("unused"), phase="cwr_feedback", event_id="unused", acknowledgement_sha256="unused")
    assert adapter._successor_event_id(Path(r"C:\fresh-v2-run"), "cwr_feedback", "feedback-v2-x") != "feedback-v2-x"
