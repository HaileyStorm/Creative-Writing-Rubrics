from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v6-single-replacement"


def adapter():
    spec = importlib.util.spec_from_file_location("v6_single_replacement", ROOT / "executor.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def test_terminal_is_exact_and_no_resend() -> None:
    mod = adapter(); value = mod.verify_terminal()
    assert value["no_resend"] is True and set(value["inventory"]) == mod.TERMINAL_FILES


def test_prepare_rejects_bad_ack_before_provider(tmp_path: Path) -> None:
    mod = adapter()
    with pytest.raises(ValueError, match="authorized"):
        mod.prepare_replacement(run_root=tmp_path / "run", source_root=tmp_path, acknowledgement_sha256="0" * 64, queue_root=tmp_path / "queue")


def test_cannot_execute_or_adopt_without_a_fresh_prepared_success(tmp_path: Path) -> None:
    mod = adapter()
    with pytest.raises(ValueError, match="prepared"):
        mod.execute_replacement(run_root=tmp_path / "run", allow_remote=True)
    with pytest.raises(ValueError, match="prepared"):
        mod.adopt_original_event(run_root=tmp_path / "run")


def test_contract_pins_v5_and_single_original_event() -> None:
    mod = adapter(); contract = mod.contract()
    stored = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    assert contract["base_executor_sha256"] == stored["base_executor_sha256"] == mod.V5_SHA256
    assert contract["original_event_id"] == mod.EVENT_ID


def test_post_prepare_admission_schema_or_outbound_tamper_rejects_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = adapter(); base = mod._base()
    route = {"command": ["fixture"], "grok_command": ["fixture"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "grok_command_identity": {"fixture": True}, "cli_version_command": ["fixture"], "cli_version_identity": {}, "grok_cli_version": "fixture", "subscription_receipt_hash": "fixture", "timeout_seconds": 1, "nonvisual_max_turns": 1}
    proof = {"queue_root": str(tmp_path / "queue"), "route_receipt_sha256": "e" * 64, "route": "fixture"}
    broker = SimpleNamespace(root=tmp_path / "queue", _load_json_artifact=lambda _hash: {})
    monkeypatch.setattr(base, "_governed_route", lambda *args, **kwargs: (broker, route, proof))
    source = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
    launches: list[object] = []; monkeypatch.setattr(mod, "_SUBPROCESS_RUN", lambda *args, **kwargs: launches.append((args, kwargs)))
    for name, mutate, expected in (
        ("replacement-admission.json", lambda value: value.__setitem__("provider_calls_made", 999), "admission"),
        ("adapter-schema-binding.json", lambda value: value.__setitem__("adapter_output_schema_sha256", "0" * 64), "prepared payload"),
        ("outbound-payload.json", lambda value: value["identity"].__setitem__("study_id", "forged"), "admission or outbound"),
    ):
        run = tmp_path / name; mod.prepare_replacement(run_root=run, source_root=source, acknowledgement_sha256=mod.ACK, queue_root=tmp_path / "queue")
        root = mod._replacement_root(run); forged = json.loads((root / name).read_text(encoding="utf-8")); mutate(forged)
        (root / name).write_bytes(mod.canonical(forged) + b"\n")
        with pytest.raises(ValueError, match=expected):
            mod.execute_replacement(run_root=run, allow_remote=True)
        assert not (root / "launch-intent.json").exists()
    assert launches == []
    extra = tmp_path / "extra"; mod.prepare_replacement(run_root=extra, source_root=source, acknowledgement_sha256=mod.ACK, queue_root=tmp_path / "queue")
    (extra / "unexpected.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="run-root inventory"):
        mod.execute_replacement(run_root=extra, allow_remote=True)
    assert launches == []


def test_predecessor_id_set_is_computed_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = adapter(); base = mod._base()
    route = {"command": ["fixture"], "grok_command": ["fixture"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "grok_command_identity": {"fixture": True}, "cli_version_command": ["fixture"], "cli_version_identity": {}, "grok_cli_version": "fixture", "subscription_receipt_hash": "fixture", "timeout_seconds": 1, "nonvisual_max_turns": 1}
    proof = {"queue_root": str(tmp_path / "queue"), "route_receipt_sha256": "e" * 64, "route": "fixture"}
    broker = SimpleNamespace(root=tmp_path / "queue", _load_json_artifact=lambda _hash: {})
    monkeypatch.setattr(base, "_governed_route", lambda *args, **kwargs: (broker, route, proof))
    source = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
    run = tmp_path / "id-preflight"; mod.prepare_replacement(run_root=run, source_root=source, acknowledgement_sha256=mod.ACK, queue_root=tmp_path / "queue")
    launches: list[object] = []; monkeypatch.setattr(mod, "_SUBPROCESS_RUN", lambda *args, **kwargs: launches.append((args, kwargs)))
    monkeypatch.setattr(mod, "_prior_native_ids", lambda: (_ for _ in ()).throw(ValueError("duplicate predecessor identities")))
    with pytest.raises(ValueError, match="duplicate predecessor"):
        mod.execute_replacement(run_root=run, allow_remote=True)
    assert launches == [] and not (mod._replacement_root(run) / "launch-intent.json").exists()


def test_duplicate_native_identity_is_terminal_after_one_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = adapter(); base = mod._base()
    route = {"command": ["fixture"], "grok_command": ["fixture"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high", "grok_command_identity": {"fixture": True}, "cli_version_command": ["fixture"], "cli_version_identity": {}, "grok_cli_version": "fixture", "subscription_receipt_hash": "fixture", "timeout_seconds": 1, "nonvisual_max_turns": 1}
    proof = {"queue_root": str(tmp_path / "queue"), "route_receipt_sha256": "e" * 64, "route": "fixture"}
    broker = SimpleNamespace(root=tmp_path / "queue", _load_json_artifact=lambda _hash: {})
    monkeypatch.setattr(base, "_governed_route", lambda *args, **kwargs: (broker, route, proof))
    source = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
    run = tmp_path / "duplicate-response"; mod.prepare_replacement(run_root=run, source_root=source, acknowledgement_sha256=mod.ACK, queue_root=tmp_path / "queue")
    outbound = (mod._replacement_root(run) / "outbound-payload.json").read_text(encoding="utf-8")
    runtime = {"adapter_version": 1, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "reasoning_attested": False, "reasoning_attestation": "requested_only", "identity_evidence": "requested_only", "cli_version": "fixture", "session_id_hash": "a" * 64, "request_id_hash": "b" * 64, "observed_turns": 1, "envelope_hash": "c" * 64, "command_identity": route["grok_command_identity"], "command_identity_hash": "d" * 64, "subscription_receipt_hash": proof["route_receipt_sha256"], "execution_policy": {}, "usage_telemetry": {}, "nonvisual_max_turns": 1}
    output = {"story": "A duplicate native identity."}
    raw = json.dumps({"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": mod._sha(mod.canonical({"prompt": outbound})), "output": output, "output_hash": mod._sha(mod.canonical(output)), "runtime": runtime}}, sort_keys=True).encode("ascii") + b"\n"
    launches: list[object] = []; monkeypatch.setattr(mod, "_SUBPROCESS_RUN", lambda *args, **kwargs: (launches.append((args, kwargs)), SimpleNamespace(returncode=0, stdout=raw))[1])
    monkeypatch.setattr(mod, "_prior_native_ids", lambda: {f"grok-request-sha256:{'b' * 64}"})
    result = mod.execute_replacement(run_root=run, allow_remote=True)
    assert result["state"] == "terminal_postlaunch_reconcile_required" and len(launches) == 1
    with pytest.raises(ValueError, match="prelaunch inventory"):
        mod.execute_replacement(run_root=run, allow_remote=True)


def test_fake_one_launch_adopts_only_after_success_and_freezes_ten_targets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = adapter(); base = mod._base()
    route = {
        "command": ["fixture"], "grok_command": ["fixture"], "model": "grok-4.6",
        "reported_model": "grok-4.6-build", "reasoning_effort": "high",
        "grok_command_identity": {"fixture": True}, "cli_version_command": ["fixture"],
        "cli_version_identity": {}, "grok_cli_version": "fixture", "subscription_receipt_hash": "fixture",
        "timeout_seconds": 1, "nonvisual_max_turns": 1,
    }
    proof = {"queue_root": str(tmp_path / "queue"), "route_receipt_sha256": "e" * 64, "route": "fixture"}
    broker = SimpleNamespace(root=tmp_path / "queue", _load_json_artifact=lambda _hash: {})
    monkeypatch.setattr(base, "_governed_route", lambda *args, **kwargs: (broker, route, proof))
    run = tmp_path / "v6-run"
    source = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
    admission = mod.prepare_replacement(run_root=run, source_root=source, acknowledgement_sha256=mod.ACK, queue_root=tmp_path / "queue")
    assert admission["provider_calls_made"] == 0
    root = mod._replacement_root(run)
    outbound = (root / "outbound-payload.json").read_text(encoding="utf-8")
    runtime = {
        "adapter_version": 1, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build",
        "requested_reasoning_effort": "high", "reasoning_attested": False, "reasoning_attestation": "requested_only",
        "identity_evidence": "requested_only", "cli_version": "fixture", "session_id_hash": "a" * 64,
        "request_id_hash": "b" * 64, "observed_turns": 1, "envelope_hash": "c" * 64,
        "command_identity": route["grok_command_identity"], "command_identity_hash": "d" * 64,
        "subscription_receipt_hash": proof["route_receipt_sha256"], "execution_policy": {},
        "usage_telemetry": {}, "nonvisual_max_turns": 1,
    }
    output = {"story": "A complete replacement story."}
    raw = json.dumps({"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": mod._sha(mod.canonical({"prompt": outbound})), "output": output, "output_hash": mod._sha(mod.canonical(output)), "runtime": runtime}}, sort_keys=True).encode("ascii") + b"\n"
    launches: list[object] = []
    monkeypatch.setattr(mod, "_SUBPROCESS_RUN", lambda *args, **kwargs: (launches.append((args, kwargs)), SimpleNamespace(returncode=0, stdout=raw))[1])
    result = mod.execute_replacement(run_root=run, allow_remote=True)
    assert result["state"] == "settled" and result["process_launches"] == 1, result.get("error")
    assert len(launches) == 1
    authority = json.loads((root / "replacement-authority.json").read_text(encoding="utf-8"))
    assert authority["actual_native_receipt"]["transmitted_payload_sha256"] == mod._sha((root / "outbound-payload.json").read_bytes())
    assert authority["actual_native_receipt"]["transmitted_payload_sha256"] != admission["prepared"]["payload"]["sha256"]
    monkeypatch.setattr(base, "_governed_route", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("route expired after launch")))
    binding_path = root / "adapter-stdout-binding.json"; binding_raw = binding_path.read_bytes()
    swapped = json.loads(binding_raw); swapped["control"]["sha256"] = "0" * 64
    binding_path.write_bytes(mod.canonical(swapped) + b"\n")
    with pytest.raises(ValueError, match="stdout/control"):
        mod.adopt_original_event(run_root=run)
    binding_path.write_bytes(binding_raw)
    record = mod.adopt_original_event(run_root=run)
    assert record["event_id"] == mod.EVENT_ID
    assert mod.validate_full_lineage(run_root=run)["record_count"] == 8
    frozen = mod.freeze_targets(run_root=run, source_root=source, target_root=tmp_path / "targets")
    assert frozen["kind"] == "frozen_blind_targets"
    assert len(frozen["targets"]) == 10
    assert len({row["blind_target_id"] for row in frozen["targets"]}) == 10
    assert (tmp_path / "targets" / "target-manifest.json").is_file()
    (run / "post-settle-extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ValueError, match="run-root inventory"):
        mod.validate_full_lineage(run_root=run)
    with pytest.raises(ValueError, match="run-root inventory"):
        mod.freeze_targets(run_root=run, source_root=source, target_root=tmp_path / "second-targets")
    (run / "post-settle-extra.txt").unlink()
    (run / "descendants" / "unexpected-extra-vote.md").write_text("extra", encoding="utf-8")
    (run / "adoptions" / "unexpected-extra-adoption.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="adopted inventory"):
        mod.validate_full_lineage(run_root=run)
    with pytest.raises(ValueError):
        mod.execute_replacement(run_root=run, allow_remote=True)
    assert len(launches) == 1
