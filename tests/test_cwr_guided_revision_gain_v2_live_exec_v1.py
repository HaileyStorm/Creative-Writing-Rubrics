from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v1"
INPUT_ROOT = Path(r"C:\Users\Haile\Documents\cwr-multisample-repeatability-v1-20260821-44518ab")
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"


def _adapter():
    spec = importlib.util.spec_from_file_location("cwr_guided_revision_gain_v2_live", ROOT / "executor.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _GovernedBrokerFixture:
    def __init__(self, adapter, root: Path) -> None:
        self.adapter_module = adapter
        self.root = root
        self.root.mkdir(parents=True)
        self.artifacts: dict[str, bytes] = {}
        self.routes: dict[str, dict] = {}
        for model, kind in (("gpt-5.6-sol", "codex_exec"), ("grok-4.6", "grok_exec")):
            evidence = adapter.canonical({"account_class": "subscription", "zero_charge": True, "model": model})
            evidence_hash = hashlib.sha256(evidence).hexdigest(); self.artifacts[evidence_hash] = evidence
            receipt = adapter.canonical({"account_class": "subscription", "model": model})
            receipt_hash = hashlib.sha256(receipt).hexdigest(); self.artifacts[receipt_hash] = receipt
            common = {
                "name": "fixture-" + model, "model": model, "adapter": kind, "trusted": True,
                "intelligence": 100, "capabilities": ["bounded_nonvisual_read_only"], "zero_charge": True,
                "priority": 1, "destination": adapter.EXPECTED_ROUTES[model]["destination"],
                "allowed_payload_classes": ["public_repo"], "armed": True, "health": "healthy",
                "provider": adapter.EXPECTED_ROUTES[model]["provider"], "account_class": "subscription",
                "cost_evidence": {"version": 1, "kind": "subscription_included", "evidence_hash": evidence_hash,
                                  "checked_at": datetime.now(UTC).isoformat(),
                                  "expires_at": (datetime.now(UTC) + timedelta(minutes=30)).isoformat(),
                                  "allowance_state": "available"},
                "command": [sys.executable, str(root / (kind + ".py"))], "timeout_seconds": 900,
                "cwd_policy": "broker_root", "reasoning_effort": "high", "identity_evidence": "requested_only",
                "output_schema": {"$schema_version": 1},
                "command_identity": {"version": 1, "artifacts": [{"index": 0, "sha256": "1" * 64, "path_hash": "2" * 64}]},
                "cli_version_command": [kind, "--version"],
                "cli_version_identity": {"version": 1, "artifacts": [{"index": 0, "sha256": "3" * 64, "path_hash": "4" * 64}]},
            }
            if kind == "codex_exec":
                common.update({"codex_command": ["codex"], "codex_command_identity": common["command_identity"],
                               "codex_cli_version": "fixture", "auth_status_command": ["codex", "auth"],
                               "auth_status_identity": common["command_identity"], "auth_receipt_hash": receipt_hash})
            else:
                common.update({"grok_command": ["grok"], "grok_command_identity": common["command_identity"],
                               "grok_cli_version": "fixture", "reported_model": adapter.GROK_REPORTED_MODEL,
                               "subscription_receipt_hash": receipt_hash, "max_concurrency": 10, "nonvisual_max_turns": 1})
            self.routes[model] = common
        self.routes_path = root / "routes.json"
        self._write_registry()
        self.validated = 0

    def _write_registry(self) -> None:
        self.routes_path.write_bytes(self.adapter_module.canonical({"version": 1, "intelligence_hierarchy": {"version": 1}, "profiles": {}, "routes": list(self.routes.values())}) + b"\n")

    def _load_registry_live(self):
        return {"version": 1, "intelligence_hierarchy": {"version": 1}, "profiles": {}, "routes": list(self.routes.values())}

    def _validate_route(self, route, *, verify_command_identity, validate_current_evidence):
        self.validated += 1
        if not verify_command_identity or not validate_current_evidence or route.get("zero_charge") is not True:
            raise ValueError("fixture governed route validation failed")
        expiry = datetime.fromisoformat(route["cost_evidence"]["expires_at"])
        if expiry <= datetime.now(UTC) or route["provider"] != self.adapter_module.EXPECTED_ROUTES[route["model"]]["provider"]:
            raise ValueError("fixture governed route is stale or tampered")

    def _load_artifact_bytes(self, digest):
        return self.artifacts[digest]

    def _load_json_artifact(self, digest):
        return json.loads(self.artifacts[digest].decode())

    def _route_semantic_identity_hash(self, route):
        return hashlib.sha256(self.adapter_module.canonical(route)).hexdigest()


def _install_queue(adapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _GovernedBrokerFixture:
    broker = _GovernedBrokerFixture(adapter, tmp_path / "queue")
    monkeypatch.setattr(adapter, "_broker", lambda _root: broker)
    return broker


def _subprocess(adapter, response: dict, *, model: str, observed_turns: int = 1,
                same_grok_identity: bool = False, state: str = "completed"):
    def fake(command, **kwargs):
        request = json.loads(kwargs["input"].decode())
        def argument(name: str) -> str:
            return command[command.index(name) + 1]
        if state != "completed":
            envelope = {"control": {"version": 1, "state": state, "detail": "fixture"}}
        elif model == "grok-4.6":
            runtime = {"adapter_version": 1, "requested_model": model, "reported_model": adapter.GROK_REPORTED_MODEL,
                       "requested_reasoning_effort": "high", "reasoning_attested": False,
                       "reasoning_attestation": "not_reported_by_grok_build_cli", "identity_evidence": "requested_only",
                       "cli_version": "fixture", "session_id_hash": ("c" if same_grok_identity else "b") * 64,
                       "request_id_hash": "c" * 64,
                       "observed_turns": observed_turns, "envelope_hash": "d" * 64, "command_identity": {"fixture": True},
                       "command_identity_hash": hashlib.sha256(adapter.canonical({"adapter_version": 1,
                           "grok_command": json.loads(argument("--grok-command-json")), "model": model,
                           "reported_model": adapter.GROK_REPORTED_MODEL, "reasoning_effort": "high",
                           "nonvisual_max_turns": 1})).hexdigest(),
                       "subscription_receipt_hash": hashlib.sha256(adapter.canonical(json.loads(argument("--subscription-receipt-json")))).hexdigest(),
                       "execution_policy": "bounded_nonvisual_read_only", "usage_telemetry": {"fixture": True},
                       "nonvisual_max_turns": 1}
            envelope = {"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1,
                        "request_hash": hashlib.sha256(adapter.canonical(request)).hexdigest(), "output": response,
                        "output_hash": hashlib.sha256(adapter.canonical(response)).hexdigest(), "runtime": runtime}}
        else:
            runtime = {"adapter_version": 1, "requested_model": model, "requested_reasoning_effort": "high",
                       "identity_evidence": "requested_only", "cli_version": "fixture", "events_hash": "b" * 64,
                       "event_projection": {"schema_version": 1, "thread_id": "fixture-thread", "usage": {"input_tokens": 1}},
                       "raw_output_hash": "c" * 64, "command_identity": {"fixture": True}, "auth_receipt_hash": "d" * 64,
                       "command_identity_hash": hashlib.sha256(adapter.canonical({"adapter_version": 1,
                           "codex_command": json.loads(argument("--codex-command-json")), "model": model,
                           "reasoning_effort": "high"})).hexdigest()}
            runtime["auth_receipt_hash"] = hashlib.sha256(adapter.canonical(json.loads(argument("--auth-receipt-json")))).hexdigest()
            envelope = {"control": {"version": 1, "state": "completed"}, "result": {"schema_version": 1,
                        "request_hash": hashlib.sha256(adapter.canonical(request)).hexdigest(), "output": response,
                        "output_hash": hashlib.sha256(adapter.canonical(response)).hexdigest(), "runtime": runtime}}
        return SimpleNamespace(returncode=0, stdout=adapter.canonical(envelope) + b"\n", stderr=b"")
    return fake


def _freeze(adapter, run: Path):
    if not INPUT_ROOT.is_dir():
        pytest.skip(f"exact local HANNA input fixture is unavailable: {INPUT_ROOT}")
    pilot = adapter._pilot()
    pilot.freeze_inputs(source_root=INPUT_ROOT, work_root=run)
    return pilot


def test_geometry_keeps_four_sol_feedback_and_twenty_sol_blind_judges() -> None:
    adapter = _adapter(); pilot = adapter._pilot()
    feedback = [row["cwr_feedback_event_id"] for row in pilot.revision_schedule() if row["cwr_feedback_event_id"]]
    endpoints = [row for row in pilot.endpoint_schedule()
                 if pilot._prepared_payload(pilot.contract(), phase="blind_endpoint_judgment", event_id=row["endpoint_event_id"])["provider_model"] == "gpt-5.6-sol"]
    assert len(feedback) == 4 and len(set(feedback)) == 4
    assert len(endpoints) == 20
    assert len(pilot.revision_schedule()) == 8 and len(pilot.endpoint_schedule()) == 40


def test_all_twenty_four_sol_cells_use_the_validated_local_lifecycle_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch); pilot = adapter._pilot()
    cells = [("cwr_feedback", row["cwr_feedback_event_id"]) for row in pilot.revision_schedule() if row["cwr_feedback_event_id"]]
    cells += [("blind_endpoint_judgment", row["endpoint_event_id"]) for row in pilot.endpoint_schedule()
              if pilot._prepared_payload(pilot.contract(), phase="blind_endpoint_judgment", event_id=row["endpoint_event_id"])["provider_model"] == "gpt-5.6-sol"]
    for phase, event_id in cells:
        _, route, proof = adapter._governed_route(pilot, queue_root=adapter.DEFAULT_QUEUE_ROOT, phase=phase, event_id=event_id)
        assert route["model"] == "gpt-5.6-sol"
        assert proof["tools_enabled"] is False and proof["zero_charge"] is True
    assert len(cells) == 24 and broker.validated == 24


def test_prepare_uses_live_governed_queue_validator_and_rejects_route_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch)
    run = tmp_path / "run"; pilot = _freeze(adapter, run)
    event_id = next(row["cwr_feedback_event_id"] for row in pilot.revision_schedule() if row["cwr_feedback_event_id"])
    admission = adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="cwr_feedback", event_id=event_id,
                                    acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT)
    assert admission["provider_calls_made"] == 0 and broker.validated == 1
    broker.routes["gpt-5.6-sol"]["provider"] = "tampered-provider"; broker._write_registry()
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no launch")))
    result = adapter.execute_one(run_root=run, phase="cwr_feedback", event_id=event_id, allow_remote=True)
    assert result["state"] == "terminal_precontact" and result["process_launches"] == result["native_contacts"] == 0


def test_sol_local_lifecycle_is_usable_but_never_claims_native_cardinality(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch)
    run = tmp_path / "run"; pilot = _freeze(adapter, run)
    event = next(row for row in pilot.revision_schedule() if row["guidance_arm"] == "cwr_guided" and row["cycle"] == 1)
    feedback_id = event["cwr_feedback_event_id"]
    adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="cwr_feedback", event_id=feedback_id,
                        acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(adapter, {"findings": []}, model="gpt-5.6-sol"))
    result = adapter.execute_one(run_root=run, phase="cwr_feedback", event_id=feedback_id, allow_remote=True)
    assert result["state"] == "settled" and result["native_contacts"] == "unproven"
    assert result["evidence_class"] == "sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1"
    ingested = adapter.ingest_feedback(run_root=run, event_id=feedback_id)
    assert ingested["native_endpoint_contact_cardinality"] == "unproven"
    feedback_path = adapter._cell_root(run, "cwr_feedback", feedback_id) / "verified-receipt.json"
    prepared = adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="revision_generation", event_id=event["event_id"],
                                   acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT, lineage_records=[],
                                   feedback_receipt_path=feedback_path)
    assert prepared["prepared"]["provider_model"] == "grok-4.6"


def test_grok_requires_native_request_session_and_exact_one_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch)
    run = tmp_path / "run"; pilot = _freeze(adapter, run)
    events = [row for row in pilot.revision_schedule() if row["guidance_arm"] == "generic_no_feedback" and row["cycle"] == 1]
    good, bad = events[0], events[1]
    adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="revision_generation", event_id=good["event_id"],
                        acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT, lineage_records=[])
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(adapter, {"story": "exact one"}, model="grok-4.6"))
    settled = adapter.execute_one(run_root=run, phase="revision_generation", event_id=good["event_id"], allow_remote=True)
    assert settled["state"] == "settled" and settled["native_contacts"] == settled["provider_calls_made"] == 1, settled
    assert settled["evidence_class"] == "grok_native_request_session_exact_one_contact_v1"
    adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="revision_generation", event_id=bad["event_id"],
                        acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT, lineage_records=[])
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(adapter, {"story": "same identities"}, model="grok-4.6", same_grok_identity=True))
    rejected = adapter.execute_one(run_root=run, phase="revision_generation", event_id=bad["event_id"], allow_remote=True)
    assert rejected["state"] == "terminal_postlaunch_reconcile_required" and rejected["native_contacts"] == "unproven"


def _persist_ambiguous_completed_sol(adapter, pilot, root: Path, response: dict) -> None:
    prepared = json.loads((root / "prepared-cell.json").read_text(encoding="utf-8"))
    admission = json.loads((root / "live-admission.json").read_text(encoding="utf-8"))
    broker, route = adapter._reauth_route(pilot=pilot, run_root=Path(prepared["work_root"]), phase=prepared["phase"],
                                          event_id=prepared["event_id"], binding=admission["route_evidence"])
    command, stdin, _ = adapter._build_invocation(broker=broker, root=root, prepared=prepared, route=route)
    pilot.begin_one_launch(prepared_root=root)
    control = _subprocess(adapter, response, model="gpt-5.6-sol")(command, input=stdin).stdout
    adapter._write_control_once(root / "adapter-control.json", control)
    pilot.record_terminal_outcome(prepared_root=root, process_launches=1, settled=False)


def test_reconciled_receipt_is_the_sole_downstream_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch)
    run = tmp_path / "run"; pilot = _freeze(adapter, run)
    event = next(row for row in pilot.revision_schedule() if row["guidance_arm"] == "cwr_guided" and row["cycle"] == 1)
    feedback_id = event["cwr_feedback_event_id"]
    adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="cwr_feedback", event_id=feedback_id,
                        acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT)
    root = adapter._cell_root(run, "cwr_feedback", feedback_id)
    _persist_ambiguous_completed_sol(adapter, pilot, root, {"findings": []})
    reconciled = adapter.reconcile_existing_receipt(run_root=run, phase="cwr_feedback", event_id=feedback_id,
                                                    reconciliation_acknowledgement_sha256=ACK)
    assert reconciled["provider_calls_made"] == reconciled["process_launches"] == 0
    authority = root / "reconciled-verified-receipt.json"
    assert adapter.ingest_feedback(run_root=run, event_id=feedback_id)["verified_receipt"]["path"].endswith("reconciled-verified-receipt.json")
    prepared = adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="revision_generation", event_id=event["event_id"],
                                   acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT, lineage_records=[],
                                   feedback_receipt_path=authority)
    assert prepared["prepared"]["phase"] == "revision_generation"


def test_dual_receipts_are_rejected_without_remint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch)
    run = tmp_path / "run"; pilot = _freeze(adapter, run)
    feedback_id = next(row["cwr_feedback_event_id"] for row in pilot.revision_schedule() if row["cwr_feedback_event_id"])
    adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="cwr_feedback", event_id=feedback_id,
                        acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT)
    root = adapter._cell_root(run, "cwr_feedback", feedback_id)
    monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(adapter, {"findings": []}, model="gpt-5.6-sol"))
    assert adapter.execute_one(run_root=run, phase="cwr_feedback", event_id=feedback_id, allow_remote=True)["state"] == "settled"
    original = root / "verified-receipt.json"; reconciled = root / "reconciled-verified-receipt.json"
    original.rename(reconciled)
    with pytest.raises(ValueError, match="terminal outcome"):
        adapter.ingest_feedback(run_root=run, event_id=feedback_id)
    reconciled.rename(original)
    reconciled.write_bytes(original.read_bytes())
    with pytest.raises(ValueError, match="exactly one verified receipt authority"):
        adapter.ingest_feedback(run_root=run, event_id=feedback_id)
    with pytest.raises(ValueError, match="duplicate or remint"):
        adapter.reconcile_existing_receipt(run_root=run, phase="cwr_feedback", event_id=feedback_id,
                                           reconciliation_acknowledgement_sha256=ACK)


def _full_mixed_endpoint_wave(adapter, broker, pilot, run: Path, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    records: list[dict] = []
    feedback_paths: dict[str, Path] = {}
    for event in pilot.revision_schedule():
        feedback_path = None
        if event["cwr_feedback_event_id"]:
            feedback_id = event["cwr_feedback_event_id"]
            adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="cwr_feedback", event_id=feedback_id,
                                acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT,
                                lineage_records=records)
            monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(adapter, {"findings": []}, model="gpt-5.6-sol"))
            assert adapter.execute_one(run_root=run, phase="cwr_feedback", event_id=feedback_id, allow_remote=True)["state"] == "settled"
            adapter.ingest_feedback(run_root=run, event_id=feedback_id)
            feedback_path = feedback_paths[feedback_id] = adapter._cell_root(run, "cwr_feedback", feedback_id) / "verified-receipt.json"
        adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="revision_generation", event_id=event["event_id"],
                            acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT,
                            lineage_records=records, feedback_receipt_path=feedback_path)
        monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(adapter, {"story": f"descendant {event['event_id']}"}, model="grok-4.6"))
        assert adapter.execute_one(run_root=run, phase="revision_generation", event_id=event["event_id"], allow_remote=True)["state"] == "settled"
        records.append(adapter.ingest_revision(run_root=run, event_id=event["event_id"], lineage_records=records,
                                               feedback_receipt_path=feedback_path))
    target_root = run / "targets"
    adapter.freeze_targets(run_root=run, source_root=INPUT_ROOT, lineage_records=records, target_root=target_root)
    manifest = target_root / "target-manifest.json"
    authorities: list[Path] = []
    for index, event in enumerate(pilot.endpoint_schedule()):
        event_id = event["endpoint_event_id"]
        adapter.prepare_one(run_root=run, source_root=INPUT_ROOT, phase="blind_endpoint_judgment", event_id=event_id,
                            acknowledgement_sha256=ACK, queue_root=adapter.DEFAULT_QUEUE_ROOT,
                            target_root=target_root, target_manifest_path=manifest)
        generic = pilot._prepared_payload(pilot.contract(), phase="blind_endpoint_judgment", event_id=event_id)
        upper = 7 if event["measure_id"] == "holistic" else 5
        score = 1 + (index % upper)
        monkeypatch.setattr(adapter, "_SUBPROCESS_RUN", _subprocess(
            adapter, {"overall": score, "rationale": "fixture independent endpoint score"},
            model=generic["provider_model"]))
        result = adapter.execute_one(run_root=run, phase="blind_endpoint_judgment", event_id=event_id, allow_remote=True)
        assert result["state"] == "settled"
        authority = adapter._cell_root(run, "blind_endpoint_judgment", event_id) / "verified-receipt.json"
        adapter.ingest_endpoint(run_root=run, event_id=event_id)
        authorities.append(authority)
    assert len(authorities) == 40
    return authorities


def test_full_mixed_forty_cell_projection_replays_both_evidence_classes_and_rejects_damage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(); broker = _install_queue(adapter, tmp_path, monkeypatch)
    run = tmp_path / "run"; pilot = _freeze(adapter, run)
    authorities = _full_mixed_endpoint_wave(adapter, broker, pilot, run, monkeypatch)
    projection = adapter.project(endpoint_receipt_paths=authorities)
    assert projection["kind"] == "independently_recomputed_mixed_endpoint_projection"
    assert projection["endpoint_results_are_not_pooled"] is True
    evidence = {row["judge_route_id"]: row for row in projection["endpoint_evidence"]}
    assert evidence["grok-4.6-high"]["endpoint_count"] == 20
    assert evidence["grok-4.6-high"]["native_endpoint_contact_cardinality"] == 1
    assert evidence["gpt-5.6-sol-high"]["endpoint_count"] == 20
    assert evidence["gpt-5.6-sol-high"]["native_endpoint_contact_cardinality"] == "unproven"
    assert len(projection["primary_guided_minus_control"]) == 16
    assert len(projection["arm_minus_baseline"]) == 32
    assert len(projection["summaries"]) == 4 and all(row["sample_count"] == 4 for row in projection["summaries"])
    with pytest.raises(ValueError, match="incomplete"):
        adapter.project(endpoint_receipt_paths=authorities[:-1])
    victim = authorities[0]; original = victim.read_bytes()
    tampered = json.loads(original.decode()); tampered["response"]["overall"] = 99
    victim.write_bytes(adapter.canonical(tampered) + b"\n")
    with pytest.raises(ValueError):
        adapter.project(endpoint_receipt_paths=authorities)
    victim.write_bytes(original)
    duplicate = victim.parent / "reconciled-verified-receipt.json"; duplicate.write_bytes(original)
    with pytest.raises(ValueError, match="exactly one verified receipt authority"):
        adapter.project(endpoint_receipt_paths=authorities)
