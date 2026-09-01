from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v6-governed-heldout-exec-v1"


def mod():
    spec = importlib.util.spec_from_file_location("revision_v6", ROOT / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def _route(adapter, row, *, command: list[str] | None = None):
    grok = row["route"]["model"] == "grok-4.6"; provider = "xai_grok_build" if grok else "openai_codex"; destination = "xai_grok_build_subscription" if grok else "openai_codex_chatgpt_subscription"
    route = {"adapter": "grok_exec" if grok else "codex_exec", "command": command or ["fixture"], "model": row["route"]["model"], "reasoning_effort": "high", "timeout_seconds": 1, "provider": provider, "destination": destination, "reported_model": "grok-4.6-build", "grok_command": ["fixture"], "grok_command_identity": {"fixture": True}, "codex_command": ["fixture"], "codex_command_identity": {"fixture": True}, "cli_version_command": ["fixture"], "cli_version_identity": {"fixture": True}, "grok_cli_version": "fixture", "codex_cli_version": "fixture", "subscription_receipt_hash": "sub", "auth_status_command": ["fixture"], "auth_status_identity": {"fixture": True}, "auth_receipt_hash": "auth", "nonvisual_max_turns": 1}
    binding = ({"adapter_version": 1, "grok_command": route["grok_command"], "command_identity": route["grok_command_identity"], "model": route["model"], "reported_model": route["reported_model"], "reasoning_effort": "high", "nonvisual_max_turns": 1} if grok else {"adapter_version": 1, "codex_command": route["codex_command"], "command_identity": route["codex_command_identity"], "model": route["model"], "reasoning_effort": "high"})
    proof = {"format_version": 1, "study_id": adapter.STUDY_ID, "kind": "governed_model_work_queue_route_proof", "queue_root": "fixture-queue", "route_name": "fixture", "registry_sha256": "a" * 64, "route_semantic_sha256": adapter.sha(adapter.canonical(route)), "model": route["model"], "adapter": route["adapter"], "provider": provider, "destination": destination, "reasoning": "high", "tools_enabled": False, "zero_charge": True, "account_class": "subscription", "cost_evidence_sha256": "b" * 64, "route_receipt_sha256": "c" * 64, "expected_adapter_runtime_identity_sha256": adapter.sha(adapter.canonical(binding)), "runtime_binding": binding}
    return SimpleNamespace(root=Path("fixture-queue"), _load_json_artifact=lambda _key: {"fixture": True}), route, proof


def _install(adapter, monkeypatch):
    sources = {item: (f"source {item}", f"prompt {item}") for item in adapter.v3()._ITEMS}
    monkeypatch.setattr(adapter, "_frozen_sources", lambda _root: sources)
    monkeypatch.setattr(adapter, "_runtime_questions", lambda _root: [{"id": "q", "question": "fixture"}])
    monkeypatch.setattr(adapter, "_governed_route", lambda row: _route(adapter, row))

    def fake(argv, *, input, **_kwargs):
        prompt = json.loads(input)["prompt"]; schema = json.loads(argv[argv.index("--output-schema-json") + 1])
        if "findings" in schema["properties"]: response = {"findings": [{"location": "x", "observation": "y", "repair_target": "z"}]}
        elif "story" in schema["properties"]: response = {"story": "fixture descendant " + adapter.sha(prompt.encode())}
        else: response = {"overall": 4, "rationale": "fixture"}
        model = argv[argv.index("--model") + 1]; identity = adapter.sha(prompt.encode())
        runtime = ({"adapter_version": 1, "requested_model": "grok-4.6", "reported_model": "grok-4.6-build", "requested_reasoning_effort": "high", "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli", "identity_evidence": "requested_only", "cli_version": "fixture", "request_id_hash": adapter.sha((identity + "r").encode()), "session_id_hash": identity, "observed_turns": 1, "envelope_hash": "a" * 64, "command_identity": {"fixture": True}, "command_identity_hash": adapter.sha(adapter.canonical({"adapter_version": 1, "grok_command": ["fixture"], "model": "grok-4.6", "reported_model": "grok-4.6-build", "reasoning_effort": "high"})), "subscription_receipt_hash": "c" * 64, "execution_policy": "bounded_nonvisual_read_only", "usage_telemetry": {"status": "not_reported"}} if model == "grok-4.6" else {"adapter_version": 1, "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "identity_evidence": "requested_only", "cli_version": "fixture", "events_hash": "a" * 64, "event_projection": {"thread_id": "thread-" + identity}, "raw_output_hash": "b" * 64, "command_identity": {"fixture": True}, "auth_receipt_hash": "c" * 64, "command_identity_hash": adapter.sha(adapter.canonical({"adapter_version": 1, "codex_command": ["fixture"], "model": "gpt-5.6-sol", "reasoning_effort": "high"}))})
        envelope = {"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1, "request_hash": adapter.sha(adapter.canonical({"prompt": prompt})), "output": response, "output_hash": adapter.sha(adapter.canonical(response)), "runtime": runtime}}
        return SimpleNamespace(returncode=0, stdout=json.dumps(envelope, sort_keys=True).encode() + b"\n", stderr=b"")
    monkeypatch.setattr(adapter.subprocess, "run", fake)


def _settle_feedback(adapter, run: Path) -> None:
    rows = [row for row in adapter.schedule() if row["phase"] == "cwr_feedback"]
    for row in rows:
        adapter.prepare_one(run_root=run, event_id=row["event_id"])
    assert all(adapter.dispatch_one(root=run / "cells" / row["phase"] / row["event_id"])["state"] == "settled" for row in rows)


def test_full_60_cell_pipeline_is_receipt_derived_and_endpoint_separated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir()
    rows = adapter.schedule(); assert len(rows) == 60
    for phase in ("cwr_feedback", "revision_generation", "blind_endpoint_judgment"):
        prepared = [adapter.prepare_one(run_root=run, event_id=row["event_id"]) for row in rows if row["phase"] == phase]
        assert all(row["provider_calls_made"] == 0 for row in prepared)
        if phase == "blind_endpoint_judgment":
            paired: dict[tuple[str, str], list[bytes]] = {}
            for row in (row for row in rows if row["phase"] == phase):
                endpoint = row["endpoint"]
                paired.setdefault((endpoint["blind_target_id"], endpoint["measure_id"]), []).append((run / "cells" / phase / row["event_id"] / "outbound-payload.json").read_bytes())
            assert all(len(values) == 2 and values[0] == values[1] for values in paired.values())
        settled = [adapter.dispatch_one(root=run / "cells" / phase / row["event_id"]) for row in rows if row["phase"] == phase]
        assert all(row["state"] == "settled" for row in settled), settled
    projection = adapter.project(run_root=run)
    assert len(projection["primary_guided_minus_control"]) == 16
    assert len(projection["guided_minus_source"]) == len(projection["generic_minus_source"]) == 16
    assert projection["endpoint_results_are_not_pooled"] is True


def test_no_resend_precontact_and_disclosure_or_route_mutation_are_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); row = next(row for row in adapter.schedule() if row["phase"] == "cwr_feedback")
    adapter.prepare_one(run_root=run, event_id=row["event_id"]); root = run / "cells" / row["phase"] / row["event_id"]
    disclosure = json.loads((root / "disclosure.json").read_bytes()); disclosure["model"] = "forged"; disclosure_raw = adapter.canonical(disclosure) + b"\n"; (root / "disclosure.json").write_bytes(disclosure_raw)
    acknowledgement = {"format_version": 1, "study_id": adapter.STUDY_ID, "disclosure_sha256": adapter.sha(disclosure_raw), "acknowledgement_sha256": adapter.ACK}; (root / "acknowledgement.json").write_bytes(adapter.canonical(acknowledgement) + b"\n")
    assert adapter.dispatch_one(root=root)["state"] == "terminal_precontact"
    assert adapter.dispatch_one(root=root)["state"] == "idle_terminal"
    assert not (root / "launch-intent.json").exists()


def test_admission_mutation_is_precontact_terminal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); row = next(row for row in adapter.schedule() if row["phase"] == "cwr_feedback")
    adapter.prepare_one(run_root=run, event_id=row["event_id"]); root = run / "cells" / row["phase"] / row["event_id"]
    admission = json.loads((root / "admission.json").read_bytes()); admission["provider_calls_made"] = 1; (root / "admission.json").write_bytes(adapter.canonical(admission) + b"\n")
    assert adapter.dispatch_one(root=root)["state"] == "terminal_precontact"
    assert not (root / "launch-intent.json").exists()


def test_same_model_command_substitution_is_rejected_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); row = next(row for row in adapter.schedule() if row["phase"] == "cwr_feedback")
    adapter.prepare_one(run_root=run, event_id=row["event_id"]); root = run / "cells" / row["phase"] / row["event_id"]
    monkeypatch.setattr(adapter, "_governed_route", lambda current: _route(adapter, current, command=["other-command"]))
    assert adapter.dispatch_one(root=root)["state"] == "terminal_precontact"
    assert not (root / "launch-intent.json").exists()


def test_native_model_swap_is_reconcile_required_without_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); _settle_feedback(adapter, run); row = next(row for row in adapter.schedule() if row["phase"] == "revision_generation" and row["revision"]["guidance_arm"] == "generic_no_feedback")
    adapter.prepare_one(run_root=run, event_id=row["event_id"]); root = run / "cells" / row["phase"] / row["event_id"]
    def bad(*args, **kwargs):
        result = original(*args, **kwargs)
        raw = json.loads(result.stdout); raw["result"]["runtime"]["reported_model"] = "wrong"; return SimpleNamespace(returncode=0, stdout=json.dumps(raw, sort_keys=True).encode() + b"\n", stderr=b"")
    original = adapter.subprocess.run; monkeypatch.setattr(adapter.subprocess, "run", bad)
    assert adapter.dispatch_one(root=root)["state"] == "terminal_postlaunch_reconcile_required"
    assert not (root / "verified-receipt.json").exists()


def test_reminted_native_ids_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); _settle_feedback(adapter, run); row = next(row for row in adapter.schedule() if row["phase"] == "revision_generation" and row["revision"]["guidance_arm"] == "generic_no_feedback")
    row2 = row
    # Fresh cell roots are mandatory; prepare the same logical cell in an isolated fresh run.
    run2 = tmp_path / "run2"; run2.mkdir(); _settle_feedback(adapter, run2); adapter.prepare_one(run_root=run2, event_id=row2["event_id"]); root2 = run2 / "cells" / row2["phase"] / row2["event_id"]
    assert adapter.dispatch_one(root=root2)["state"] == "settled"
    native = json.loads((root2 / "native-receipt.json").read_bytes()); native["provider_request_id"] = "grok-request-sha256:forged"; native_raw = adapter.canonical(native) + b"\n"; (root2 / "native-receipt.json").write_bytes(native_raw)
    receipt = json.loads((root2 / "verified-receipt.json").read_bytes()); receipt["native"] = native; receipt["native_receipt_sha256"] = adapter.sha(native_raw); receipt_raw = adapter.canonical(receipt) + b"\n"; (root2 / "verified-receipt.json").write_bytes(receipt_raw)
    execution = json.loads((root2 / "execution-result.json").read_bytes()); execution["receipt"] = adapter.bind(root2, root2 / "verified-receipt.json"); (root2 / "execution-result.json").write_bytes(adapter.canonical(execution) + b"\n")
    with pytest.raises(ValueError, match="native identity"):
        adapter.replay_receipt(root=root2)


def test_build_invocation_supplies_every_current_adapter_argument(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); _settle_feedback(adapter, run)
    sol = next(row for row in adapter.schedule() if row["phase"] == "cwr_feedback")
    grok = next(row for row in adapter.schedule() if row["phase"] == "revision_generation" and row["revision"]["guidance_arm"] == "generic_no_feedback")
    adapter.prepare_one(run_root=run, event_id=grok["event_id"])
    for row in (sol, grok):
        root = run / "cells" / row["phase"] / row["event_id"]
        broker, route, _proof = _route(adapter, row); argv, _stdin, _timeout = adapter._build_invocation(broker, root, route)
        required = {"--model", "--reasoning-effort", "--output-schema-json", "--expected-command-identity-json", "--cli-version-command-json", "--expected-cli-version-identity-json", "--expected-cli-version", "--broker-root", "--timeout-seconds"}
        if route["adapter"] == "grok_exec": required |= {"--grok-command-json", "--reported-model", "--subscription-receipt-json", "--nonvisual-max-turns"}
        else: required |= {"--codex-command-json", "--auth-status-command-json", "--expected-auth-status-identity-json", "--auth-receipt-json"}
        assert required <= set(argv)


def test_reconcile_uses_only_persisted_raw_and_preserves_terminal_lineage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); _settle_feedback(adapter, run)
    row = next(row for row in adapter.schedule() if row["phase"] == "revision_generation" and row["revision"]["guidance_arm"] == "generic_no_feedback")
    adapter.prepare_one(run_root=run, event_id=row["event_id"]); root = run / "cells" / row["phase"] / row["event_id"]
    broker, route, _proof = _route(adapter, row); argv, stdin, timeout = adapter._build_invocation(broker, root, route); completed = adapter.subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout, check=False)
    adapter.write_once(root / "launch-intent.json", {"format_version": 1, "study_id": adapter.STUDY_ID, "process_launches": 1, "no_resend": True}); adapter.write_bytes_once(root / "adapter-stdout.raw", completed.stdout); adapter.write_bytes_once(root / "adapter-stderr.raw", completed.stderr)
    adapter.write_once(root / "terminal-outcome.json", {"format_version": 1, "study_id": adapter.STUDY_ID, "state": "terminal_postlaunch_reconcile_required", "process_launches": 1, "provider_calls_made": "unproven", "no_resend": True})
    terminal_before = (root / "terminal-outcome.json").read_bytes(); runner = adapter.subprocess.run; monkeypatch.setattr(adapter.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("reconcile must not launch")))
    assert adapter.reconcile_one(root=root)["state"] == "settled"
    assert (root / "terminal-outcome.json").read_bytes() == terminal_before
    assert adapter.status(root=root)["state"] == "settled"
    assert adapter.reconcile_one(root=root)["state"] == "settled"

    monkeypatch.setattr(adapter.subprocess, "run", runner)
    run2 = tmp_path / "run2"; run2.mkdir(); sol = next(item for item in adapter.schedule() if item["phase"] == "cwr_feedback"); adapter.prepare_one(run_root=run2, event_id=sol["event_id"]); bad = run2 / "cells" / sol["phase"] / sol["event_id"]
    broker, route, _proof = _route(adapter, sol); argv, stdin, timeout = adapter._build_invocation(broker, bad, route); malformed = adapter.subprocess.run(argv, input=stdin, capture_output=True, timeout=timeout, check=False); raw = json.loads(malformed.stdout); raw["result"]["runtime"]["events_hash"] = "not-sha256"; malformed_raw = json.dumps(raw, sort_keys=True).encode() + b"\n"
    adapter.write_once(bad / "launch-intent.json", {"format_version": 1, "study_id": adapter.STUDY_ID, "process_launches": 1, "no_resend": True}); adapter.write_bytes_once(bad / "adapter-stdout.raw", malformed_raw); adapter.write_bytes_once(bad / "adapter-stderr.raw", b"")
    adapter.write_once(bad / "terminal-outcome.json", {"format_version": 1, "study_id": adapter.STUDY_ID, "state": "terminal_postlaunch_reconcile_required", "process_launches": 1, "provider_calls_made": "unproven", "no_resend": True})
    assert adapter.reconcile_one(root=bad)["state"] == "reconcile_required"
    assert not (bad / "verified-receipt.json").exists() and not (bad / "execution-result.json").exists()
    assert not (bad / "adapter-control.json").exists() and not (bad / "response.json").exists() and not (bad / "native-receipt.json").exists()


def test_replay_rejects_self_consistent_schema_binding_swap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = mod(); _install(adapter, monkeypatch); run = tmp_path / "run"; run.mkdir(); _settle_feedback(adapter, run)
    row = next(row for row in adapter.schedule() if row["phase"] == "revision_generation" and row["revision"]["guidance_arm"] == "generic_no_feedback")
    adapter.prepare_one(run_root=run, event_id=row["event_id"]); root = run / "cells" / row["phase"] / row["event_id"]
    assert adapter.dispatch_one(root=root)["state"] == "settled"
    binding = json.loads((root / "adapter-schema-binding.json").read_bytes()); binding["schema"] = {"$schema_version": 1, "type": "object"}; binding["schema_sha256"] = adapter.sha(adapter.canonical(binding["schema"])); (root / "adapter-schema-binding.json").write_bytes(adapter.canonical(binding) + b"\n")
    with pytest.raises(ValueError, match="schema replay"):
        adapter.replay_receipt(root=root)
