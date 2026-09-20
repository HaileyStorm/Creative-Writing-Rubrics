from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_parallel_successor.py"
spec = importlib.util.spec_from_file_location("grok_parallel_successor_test", SOURCE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write(path: Path, value: Any, *, raw: bool = False) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if raw else canon(value)
    path.write_bytes(data)
    return {"path": str(path.resolve()), "sha256": sha(data)}


def fixture(tmp_path: Path, *, prefix: list[int] | None = None, candidate_version: int = 8) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    prefix = [100] if prefix is None else prefix
    prior_root = tmp_path / "prior"
    prior_root.mkdir()
    queue = tmp_path / "queue"
    queue.mkdir()
    plan = tmp_path / "plan"
    plan.mkdir()
    candidate_root = tmp_path / f"candidate-v{candidate_version}"
    package_root = candidate_root / "model_work_queue"
    package_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "broker.py").write_text("class Broker:\n    pass\n", encoding="utf-8")
    candidate_files = [
        {"path": str(path.relative_to(candidate_root)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha(path.read_bytes())}
        for path in (package_root / "__init__.py", package_root / "broker.py")
    ]
    candidate_manifest_path = candidate_root / "candidate-manifest.json"
    candidate_manifest_value = {
        "schema_version": candidate_version,
        "kind": "grok_v8_contention_forwardport_candidate" if candidate_version == 8 else "grok_v9_dynamic_standing_authority_candidate",
        "explicit_exclusion": ["candidate-manifest.json"],
        "files": candidate_files,
    }
    candidate_manifest_path.write_bytes(canon(candidate_manifest_value))
    candidate_manifest_sha = sha(candidate_manifest_path.read_bytes())
    prior_pending = list(range(100, 112))
    prior_ids = [
        {"request_id_hash": f"{10000 + index:064x}", "session_id_hash": f"{20000 + index:064x}", "observed_turns": 1}
        for index in range(335)
    ]
    prior_manifest_path = prior_root / "prior-manifest.json"
    prior_manifest = write(prior_manifest_path, {"source_epoch": "renewed-fixture", "provider_calls_made": 0})
    schema = {"type": "object"}
    rows: dict[int, dict[str, Any]] = {}
    for ordinal in prior_pending:
        source_path = tmp_path / f"story-{ordinal}.txt"
        source = f"story-{ordinal}"
        source_path.write_text(source, encoding="utf-8")
        rows[ordinal] = {
            "ordinal": ordinal,
            "prompt": f"prompt-{ordinal}",
            "question_ids": [f"q-{ordinal}"],
            "schema": schema,
            "source": {
                "opaque_story_id": f"story-{ordinal}",
                "story_text": source,
                "artifact_path": str(source_path),
                "sha256": sha(source.encode()),
            },
        }
    identity = {"request_id_hash": f"{30000:064x}", "session_id_hash": f"{40000:064x}", "observed_turns": 1}
    terminal = {"ordinal": 100, "state": "completed", "native_identity": identity, "candidate_result": {"runtime": identity, "output": {"verdicts": [{"question_id": "q-100"}]}, "native_envelope_artifact": {"sha256": sha(b"env"), "byte_length": 3}}, "verdicts": [{"question_id": "q-100"}]}
    attempt = prior_root / "attempts" / "request-0100"
    write(attempt / "terminal.json", terminal)
    write(attempt / "attempt-start.json", {"ordinal": 100})
    write(prior_root / "replays" / "wave-0100.json", {"ordinals": [100], "native_identities": [identity]})
    controller_path = tmp_path / "prior_controller.py"
    controller_path.write_text(
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        f"PENDING = {prior_pending!r}\n"
        f"ROWS = {rows!r}\n"
        f"IDS = {prior_ids!r}\n"
        "class Candidate:\n"
        "    class Broker:\n"
        "        def __init__(self, _queue): pass\n"
        "def verify(*, continuation_root, expected_manifest_sha256):\n"
        "    return {'pending_ordinals': list(PENDING), 'prior_identities': list(IDS), 'context': SimpleNamespace(plan_root=Path(" + repr(str(plan)) + "), requests=ROWS, parent=SimpleNamespace(), passes={}, candidate=Candidate, runtime=SimpleNamespace()), 'manifest': {'source_closure': {'queue': {'path': " + repr(str(queue)) + "}}}}\n"
        "def _replayed(root, state):\n"
        "    if (Path(root) / 'replays' / 'wave-0100.json').is_file():\n"
        "        return {100}, [" + repr(identity) + "]\n"
        "    return set(), []\n"
        "def _records(root):\n"
        "    path = Path(root) / 'attempts' / 'request-0100' / 'terminal.json'\n"
        "    return {100: __import__('json').loads(path.read_text())} if path.is_file() else {}\n"
        "def _attempt(root, ordinal, name):\n"
        "    return Path(root) / 'attempts' / f'request-{ordinal:04d}' / name\n"
        "def _semantic_replay_terminal(**kwargs):\n"
        "    terminal = kwargs['terminal']; return terminal['native_identity'], terminal['verdicts'], {'sha256': 'e' * 64}\n",
        encoding="utf-8",
    )
    controller_desc = {"path": str(controller_path.resolve()), "sha256": sha(controller_path.read_bytes())}
    stopped_path = tmp_path / "stopped-prefix.json"
    loop_result = write(tmp_path / "loop-result.json", {"stopped": True})
    stopped = {
        "schema_version": 1,
        "prior_continuation": {"root": str(prior_root.resolve()), "manifest_sha256": prior_manifest["sha256"], "controller_sha256": controller_desc["sha256"]},
        "completed_ordinals": prefix,
        "remaining_ordinals": prior_pending[len(prefix) :],
        "owned_exit": {"exit_code": 0, "session_id": "fixture-session"},
        "loop_result": loop_result,
    }
    stopped_desc = write(stopped_path, stopped)
    loader_path = tmp_path / "candidate_loader.py"
    loader_path.write_text("from types import SimpleNamespace\ndef load_candidate(root, expected): return SimpleNamespace(), {'schema_version': 8}\n", encoding="utf-8")
    loader_desc = {"path": str(loader_path.resolve()), "sha256": sha(loader_path.read_bytes())}
    route_desc = write(tmp_path / "route.json", {"name": "fixture-route-v8", "model": "fixture-model", "reported_model": "fixture-model"})
    standing_desc = write(tmp_path / "standing.json", {"schema_version": 3, "provider": "fixture", "account_class": "included", "allowance_state": "available", "authorization": {"scope": {"zero_charge_only": True, "automatic_resend": False, "paid_fallback": False, "route": "fixture-route-v8"}}})
    route_contract_hash = "a" * 64
    gate_db = tmp_path / "gate.sqlite3"
    gate_db.write_bytes(b"fixture-gate")
    gate_desc = write(tmp_path / "gate.json", {"provider": "fixture", "account_class": "included", "contract_hash": route_contract_hash, "source_evidence_hash": standing_desc["sha256"], "updated_at": "2099-01-01T00:00:00+00:00", "state": "healthy", "max_concurrency": 10})
    packet_desc = write(tmp_path / "packet.json", {"schema_version": 1, "kind": "grok_v8_source_transition_packet", "state": "sealed_provider_free_not_activated", "candidate_manifest_sha256": candidate_manifest_sha, "preimages": {"route_contract_sha256": route_contract_hash}, "live_mutations_made": 0, "provider_calls_made": 0})
    fix_desc = write(tmp_path / "contention-fix.json", {"shared_contention_fix_verified": True, "candidate_manifest_sha256": candidate_manifest_sha, "provider_calls_made": 0})
    registry_path = tmp_path / "routes.json"
    registry_raw = canon({"fixture": "registry"})
    registry_path.write_bytes(registry_raw)
    registry_sha = sha(registry_raw)
    route_sha = route_desc["sha256"]
    registry_descriptor = write(tmp_path / "registry-descriptor.json", {"schema_version": 1, "kind": "grok_v8_isolated_registry_transition_descriptor", "registry_path": str(registry_path.resolve()), "pre_registry_sha256": "b" * 64, "target_registry_sha256": registry_sha, "pre_route_sha256": "c" * 64, "target_route_sha256": route_sha, "route_contract_sha256": route_contract_hash})
    gate_descriptor = write(tmp_path / "gate-descriptor.json", {"schema_version": 1, "kind": "grok_v8_gate_transition_descriptor", "path": str(gate_db.resolve()), "pre_row_sha256": "d" * 64, "target_row_sha256": "d" * 64, "route_contract_sha256": route_contract_hash, "required_storage_postcondition": {"journal_mode": "wal", "storage_schema_version": 1}})
    runtime_files = {
        "wrapper_python_path": tmp_path / "python.exe",
        "runner_path": tmp_path / "runner.py",
        "runner_interpreter_path": tmp_path / "interpreter.exe",
        "reader_path": tmp_path / "reader.py",
    }
    for path in runtime_files.values():
        path.write_bytes(b"fixture-runtime")
    runtime_receipt = {key: "e" * 64 for key in ("binding_interface_sha256", "handoff_manifest_sha256", "broker_sha256", "adapter_sha256")}
    runtime_receipt.update({
        "candidate_manifest_sha256": candidate_manifest_sha,
        **{key: str(path.resolve()) for key, path in runtime_files.items()},
        **{key.replace("_path", "_sha256"): sha(path.read_bytes()) for key, path in runtime_files.items()},
        "controller_path": str(SOURCE.resolve()),
        "controller_sha256": sha(SOURCE.read_bytes()),
    })
    transition_receipt = write(tmp_path / "transition-receipt.json", {"schema_version": 1, "kind": "grok_v8_quiescent_transition_receipt", "state": "complete", "actions": {"provider_calls_made": 0, "queue_dispatches": 0, "automatic_resends": 0, "global_registry_mutated": False, "installed_shared_broker_mutated": False}, "exclusive_owner": {key: "owner" for key in ("human_owner_id", "work_id", "task_id", "host_id", "workspace_instance_id", "session_id", "registry_lock_path", "gate_transaction", "acquired_at")}, "gate": {"path": str(gate_db.resolve()), "pretransition_db_sha256": "f" * 64, "posttransition_db_sha256": "f" * 64, "pre_row_sha256": "d" * 64, "target_row_sha256": "d" * 64, "post_row_sha256": "d" * 64, "storage_pre": {}, "storage_post": {}, "active_slots_before": 0, "active_slots_after": 0}, "queue": {"root_path": str(queue.resolve()), "queue_db_path": str((queue / "queue.sqlite3").resolve()), "pretransition_db_sha256": "f" * 64, "running_rows": 0}, "registry": {"path": str(registry_path.resolve()), "pre_sha256": "b" * 64, "target_sha256": registry_sha, "post_sha256": registry_sha}, "route": {"name": "fixture-route-v8", "pre_sha256": "c" * 64, "target_sha256": route_sha, "post_sha256": route_sha, "contract_sha256": route_contract_hash}, "runtime": runtime_receipt, "source": {"standing_source_sha256": standing_desc["sha256"], "subscription_receipt_sha256": "1" * 64, "cost_evidence_sha256": "2" * 64, "expires_at": "2099-01-01T00:00:00+00:00"}, "prefix": {"receipt_path": str(stopped_path.resolve()), "receipt_sha256": stopped_desc["sha256"], "completed_through": prefix[-1], "first_untouched_ordinal": 101, "automatic_resend": False}, "verification": {key: True for key in ("candidate_inventory_valid", "route_valid", "gate_storage_valid", "doctor_ok", "status_ok", "expected_route_pin_valid")}})
    closure = {
        "prior_controller": controller_desc,
        "prior_continuation": {"root": str(prior_root.resolve()), "manifest_path": str(prior_manifest_path.resolve()), "manifest_sha256": prior_manifest["sha256"]},
        "stopped_prefix": stopped_desc,
        "candidate_loader": loader_desc,
        "candidate": {"root": str(candidate_root.resolve()), "manifest_sha256": candidate_manifest_sha},
        "route": route_desc,
        "gate": gate_desc,
        "standing_source": standing_desc,
        "packet": packet_desc,
        "contention_fix_receipt": fix_desc,
        "registry_descriptor": registry_descriptor,
        "gate_descriptor": gate_descriptor,
        "transition_receipt": transition_receipt,
        "route_contract_hash": route_contract_hash,
        "queue": {"path": str(queue.resolve()), "root_hash": "queue-root"},
    }
    if candidate_version == 9:
        for key, kind in {
            "packet": "grok370_incident_bound_v9_recovery_packet",
            "registry_descriptor": "grok_v9_registry_transition_descriptor",
            "gate_descriptor": "grok_v9_gate_transition_descriptor",
            "transition_receipt": "grok370_incident_bound_v9_recovery_transition",
        }.items():
            path = Path(closure[key]["path"])
            value = json.loads(path.read_bytes())
            value["kind"] = kind
            closure[key] = write(path, value)
    new_root = tmp_path / "parallel"
    return new_root, closure, {"rows": rows, "prefix": prefix, "pending": prior_pending[len(prefix) :]}


class BrokerFactory:
    def __init__(self, *, behavior: dict[int, str] | None = None, barrier: threading.Barrier | None = None) -> None:
        self.behavior = behavior or {}
        self.barrier = barrier
        self.calls: list[int] = []
        self.lock = threading.Lock()

    def __call__(self, _queue: Path, ordinal: int, _row: Mapping[str, Any]) -> Any:
        owner = self

        class Broker:
            def __init__(self) -> None:
                self.envelope = b""

            def run_grok_native_request(self, _route: str, request: Mapping[str, Any], *, session_id: str, before_contact: Any, **_kwargs: Any) -> dict[str, Any]:
                if owner.behavior.get(ordinal) == "fail_before":
                    raise RuntimeError("before contact failure")
                before_contact()
                if owner.behavior.get(ordinal) == "fail_after":
                    if owner.barrier is not None:
                        owner.barrier.wait(timeout=5)
                    raise RuntimeError("post contact failure")
                if owner.barrier is not None:
                    owner.barrier.wait(timeout=5)
                with owner.lock:
                    owner.calls.append(ordinal)
                identity_value = 50000 if owner.behavior.get(ordinal) == "duplicate" else 50000 + ordinal
                identity = {"request_id_hash": f"{identity_value:064x}", "session_id_hash": f"{60000 + identity_value:064x}", "observed_turns": 1}
                output = {"verdicts": [{"question_id": request["prompt"].replace("prompt-", "q-")}]}
                self.envelope = canon({"identity": identity, "output": output})
                return {"state": "completed", "result": {"runtime": identity, "output": output, "native_envelope_artifact": {"sha256": sha(self.envelope), "byte_length": len(self.envelope)}}}

            def read_grok_native_envelope(self, _descriptor: Mapping[str, Any]) -> bytes:
                return self.envelope

            def _parse_grok_exec_envelope(self, _payload: bytes, _route: Mapping[str, Any], _request: Mapping[str, Any], **_kwargs: Any) -> Any:
                return SimpleNamespace(state="completed", result=json.loads(_payload)["result"])

        return Broker()


@pytest.fixture(autouse=True)
def strict_fixture_normalizer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m, "_normalize", lambda _state, _row, result, _ordinal: result["output"]["verdicts"])
    monkeypatch.setattr(
        m,
        "_candidate_adapter",
        lambda _candidate: SimpleNamespace(
            _parse_grok_envelope=lambda envelope, **_kwargs: (
                json.loads(envelope)["output"],
                json.loads(envelope)["identity"],
                {},
            )
        ),
    )


@pytest.mark.parametrize("candidate_version", [8, 9])
def test_create_derives_exact_next_from_frozen_prefix_and_excludes_prior_records(tmp_path: Path, candidate_version: int) -> None:
    root, closure, expected = fixture(tmp_path, prefix=[100], candidate_version=candidate_version)
    result = m.create(continuation_root=root, source_closure=closure)
    assert result["next_ordinal"] == expected["pending"][0]
    manifest, _ = m._manifest(root, result["manifest_sha256"])
    assert manifest["prior_completed_ordinals"] == [100]
    assert manifest["pending_ordinals"] == expected["pending"]
    assert not (root / "attempts" / "request-0100").exists()


def test_candidate_version_and_kind_must_match(tmp_path: Path) -> None:
    _root, closure, _expected = fixture(tmp_path, candidate_version=9)
    manifest_path = Path(closure["candidate"]["root"]) / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schema_version"] = 8
    descriptor = write(manifest_path, manifest)
    closure["candidate"]["manifest_sha256"] = descriptor["sha256"]
    with pytest.raises(ValueError, match="candidate file inventory differs"):
        m._candidate_binding(closure)


def test_candidate_v10_inventory_uses_bounded_attestation_kind(tmp_path: Path) -> None:
    _root, closure, _expected = fixture(tmp_path, candidate_version=9)
    manifest_path = Path(closure["candidate"]["root"]) / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schema_version"] = 10
    manifest["kind"] = "grok_v10_bounded_nonzero_session_attestation_candidate"
    descriptor = write(manifest_path, manifest)
    closure["candidate"]["manifest_sha256"] = descriptor["sha256"]
    binding = m._candidate_binding(closure)
    assert binding["manifest"]["schema_version"] == 10
    assert binding["manifest"]["kind"] == "grok_v10_bounded_nonzero_session_attestation_candidate"


def test_candidate_v11_inventory_uses_separated_wrapper_deadline_kind(tmp_path: Path) -> None:
    _root, closure, _expected = fixture(tmp_path, candidate_version=9)
    manifest_path = Path(closure["candidate"]["root"]) / "candidate-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["schema_version"] = 11
    manifest["kind"] = "grok_v11_separated_wrapper_deadline_candidate"
    descriptor = write(manifest_path, manifest)
    closure["candidate"]["manifest_sha256"] = descriptor["sha256"]
    binding = m._candidate_binding(closure)
    assert binding["manifest"]["schema_version"] == 11
    assert binding["manifest"]["kind"] == "grok_v11_separated_wrapper_deadline_candidate"


def test_retry_authority_binds_origin_specific_failed_ordinal(tmp_path: Path) -> None:
    authority_path = tmp_path / "retry-authority.json"
    authority_descriptor = write(
        authority_path,
        {"grok_retry_authorized": True, "billing_changes_authorized": False},
    )
    retained = {
        "manifest_sha256": "a" * 64,
        "controller_sha256": "b" * 64,
        "source_epoch": "grok_parallel_successor_20260919_r1",
        "completed_ordinals": [*range(371, 398), 400, 401, 402],
        "root": str(tmp_path),
    }
    for ordinal in (463,):
        write(
            tmp_path / "attempts" / f"request-{ordinal:04d}" / "terminal.json",
            {"ordinal": ordinal, "state": "ambiguous", "contact_admitted": True},
        )
    descriptor = {
        **authority_descriptor,
        "retry_ordinals": [463],
        "original_manifest_sha256": retained["manifest_sha256"],
        "original_controller_sha256": retained["controller_sha256"],
        "original_source_epoch": retained["source_epoch"],
    }
    bound = m._retry_binding({"retry_authority": descriptor}, retained)
    assert bound and bound["retry_ordinals"] == [463]
    wrong = dict(descriptor, retry_ordinals=[463, 463])
    with pytest.raises(ValueError, match="retry authority ordinals"):
        m._retry_binding({"retry_authority": wrong}, retained)


def test_retained_parallel_origins_merge_disjoint_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    descriptors = [
        {"root": str(tmp_path / "r2"), "manifest_path": str(tmp_path / "r2-manifest"), "manifest_sha256": "a" * 64, "controller_path": str(tmp_path / "r2-controller"), "controller_sha256": "b" * 64, "source_epoch": "r2", "completed_ordinals": [1], "replay_receipt": {"path": str(tmp_path / "r2-replay"), "sha256": "c" * 64}},
        {"root": str(tmp_path / "r3"), "manifest_path": str(tmp_path / "r3-manifest"), "manifest_sha256": "d" * 64, "controller_path": str(tmp_path / "r3-controller"), "controller_sha256": "e" * 64, "source_epoch": "r3", "completed_ordinals": [2, 3], "replay_receipt": {"path": str(tmp_path / "r3-replay"), "sha256": "f" * 64}},
    ]

    def fake_origin(closure: Mapping[str, Any], *, semantic: bool = True) -> dict[str, Any]:
        descriptor = closure["retained_parallel_prefix"]
        records = [
            {"ordinal": ordinal, "native_identity": {"request_id_hash": f"{ordinal:064x}", "session_id_hash": f"{ordinal + 100:064x}", "observed_turns": 1}}
            for ordinal in descriptor["completed_ordinals"]
        ]
        return {"descriptor": descriptor, "root": Path(descriptor["root"]), "manifest_sha256": descriptor["manifest_sha256"], "controller_sha256": descriptor["controller_sha256"], "source_epoch": descriptor["source_epoch"], "completed_ordinals": descriptor["completed_ordinals"], "records": records, "identities": [record["native_identity"] for record in records], "replay_receipt": descriptor["replay_receipt"]}

    monkeypatch.setattr(m, "_retained_parallel_binding", fake_origin)
    merged = m._retained_parallel_bindings({"retained_parallel_prefixes": descriptors})
    assert merged["completed_ordinals"] == [1, 2, 3]
    assert len(merged["origins"]) == 2 and len(merged["records"]) == 3


@pytest.mark.parametrize(("key", "legacy_kind"), [
    ("packet", "grok_v8_source_transition_packet"),
    ("registry_descriptor", "grok_v8_isolated_registry_transition_descriptor"),
    ("gate_descriptor", "grok_v8_gate_transition_descriptor"),
    ("transition_receipt", "grok_v8_quiescent_transition_receipt"),
])
def test_v9_rejects_legacy_transition_labels(tmp_path: Path, key: str, legacy_kind: str) -> None:
    root, closure, _expected = fixture(tmp_path, candidate_version=9)
    path = Path(closure[key]["path"])
    value = json.loads(path.read_bytes())
    value["kind"] = legacy_kind
    closure[key] = write(path, value)
    with pytest.raises(ValueError, match="standing packet|transition descriptor|transition receipt"):
        m.create(continuation_root=root, source_closure=closure)


@pytest.mark.parametrize("wave_size", [2, 10])
@pytest.mark.parametrize("candidate_version", [8, 9])
def test_dispatch_wave_uses_actual_rendezvous_and_unique_intents(tmp_path: Path, wave_size: int, candidate_version: int) -> None:
    root, closure, expected = fixture(tmp_path, candidate_version=candidate_version)
    created = m.create(continuation_root=root, source_closure=closure)
    factory = BrokerFactory(barrier=threading.Barrier(wave_size))
    result = m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=wave_size, broker_factory=factory)
    assert result["state"] == "completed_replayed"
    assert result["completed_ordinals"] == expected["pending"][:wave_size]
    assert sorted(factory.calls) == expected["pending"][:wave_size]
    replay = m.replay_collection(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], require_complete=False)
    assert replay["completed_ordinals"] == expected["pending"][:wave_size]
    assert [row["ordinal"] for row in replay["records"]] == expected["pending"][:wave_size]
    with pytest.raises(ValueError, match="exact next|attempt intent"):
        m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=factory)


def test_failure_stops_new_contact_and_preserves_completed_peer(tmp_path: Path) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    factory = BrokerFactory(behavior={expected["pending"][1]: "fail_after"}, barrier=threading.Barrier(2))
    result = m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=2, broker_factory=factory)
    assert result["state"] == "stopped_no_retry"
    terminals = m._records(root)
    assert terminals[expected["pending"][0]]["state"] == "completed"
    assert terminals[expected["pending"][1]]["state"] == "ambiguous"
    assert not list((root / "replays").glob("*.json"))


def test_duplicate_native_identity_rejects_wave_without_replay(tmp_path: Path) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    factory = BrokerFactory(behavior={expected["pending"][0]: "duplicate", expected["pending"][1]: "duplicate"})
    result = m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=2, broker_factory=factory)
    assert result["state"] == "stopped_no_retry"
    assert not list((root / "replays").glob("*.json"))


def test_source_drift_before_contact_is_fail_closed(tmp_path: Path) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    source_path = Path(expected["rows"][expected["pending"][0]]["source"]["artifact_path"])
    source_path.write_text("drifted", encoding="utf-8")
    factory = BrokerFactory()
    with pytest.raises(ValueError, match="source drift"):
        m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=factory)
    assert factory.calls == []


def test_semantic_replay_rejection_preserves_terminals_and_blocks_advance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    monkeypatch.setattr(m, "_semantic_replay_terminal", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("semantic replay differs")))
    result = m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=BrokerFactory())
    assert result["state"] == "stopped_no_retry"
    assert (root / "attempts" / f"request-{expected['pending'][0]:04d}" / "terminal.json").is_file()
    with pytest.raises(ValueError, match="semantically replayed"):
        m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=BrokerFactory())


def test_local_stopped_prefix_binds_actual_integer_owner_session(tmp_path: Path) -> None:
    _root, closure, _expected = fixture(tmp_path)
    prior_continuation = closure["prior_continuation"]
    prefix = json.loads(Path(closure["stopped_prefix"]["path"]).read_bytes())
    prefix["completed_ordinals"] = list(range(338, 370))
    prefix["remaining_ordinals"] = [371]
    prefix["owned_exit"] = {"exit_code": 1, "session_id": 18262}
    prefix["local_recovery"] = write(tmp_path / "local-recovery.json", {"kind": "completed_native_local_replay_recovery"})
    descriptor = write(tmp_path / "stopped-prefix-local.json", prefix)
    result = m._read_prefix_descriptor(
        descriptor,
        list(range(338, 372)),
        prior_continuation["manifest_sha256"],
        Path(prior_continuation["root"]),
        closure["prior_controller"]["sha256"],
        allow_local_exit=True,
    )
    assert result["completed_ordinals"] == list(range(338, 370))
    assert result["remaining_ordinals"] == [371]

    prefix["owned_exit"] = {"exit_code": 1, "session_id": "18262"}
    wrong_descriptor = write(tmp_path / "stopped-prefix-local-wrong-session.json", prefix)
    with pytest.raises(ValueError, match="stopped prefix exit differs"):
        m._read_prefix_descriptor(
            wrong_descriptor,
            list(range(338, 372)),
            prior_continuation["manifest_sha256"],
            Path(prior_continuation["root"]),
            closure["prior_controller"]["sha256"],
            allow_local_exit=True,
        )


def test_replay_collection_public_default_rejects_partial_coverage(tmp_path: Path) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=BrokerFactory())
    with pytest.raises(ValueError, match="incomplete"):
        m.replay_collection(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"])


def test_replay_collection_rejects_altered_terminal_or_receipt(tmp_path: Path) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=BrokerFactory())
    terminal_path = root / "attempts" / f"request-{expected['pending'][0]:04d}" / "terminal.json"
    terminal_path.write_bytes(terminal_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="receipt terminal|settlement"):
        m.replay_collection(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], require_complete=False)
    terminal_path.write_bytes(terminal_path.read_bytes().rstrip())
    replay_path = next((root / "replays").glob("*.json"))
    receipt = json.loads(replay_path.read_bytes())
    receipt["terminals"][0]["terminal_sha256"] = "0" * 64
    replay_path.write_bytes(canon(receipt))
    with pytest.raises(ValueError, match="receipt terminal|settlement"):
        m.replay_collection(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], require_complete=False)


def test_dispatch_semantic_replay_invokes_candidate_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, closure, expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    calls: list[int] = []
    original = m._candidate_adapter

    def adapter(candidate: Any) -> Any:
        calls.append(1)
        return original(candidate)

    monkeypatch.setattr(m, "_candidate_adapter", adapter)
    m.dispatch_wave(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"], start_ordinal=expected["pending"][0], wave_size=1, broker_factory=BrokerFactory())
    assert calls == [1]


def test_transition_runtime_path_hash_drift_is_rejected(tmp_path: Path) -> None:
    root, closure, _expected = fixture(tmp_path)
    created = m.create(continuation_root=root, source_closure=closure)
    runtime_path = Path(json.loads(Path(closure["transition_receipt"]["path"]).read_bytes())["runtime"]["runner_path"])
    runtime_path.write_bytes(b"drifted-runtime")
    with pytest.raises(ValueError, match="transition runtime runner_path"):
        m.verify(continuation_root=root, expected_manifest_sha256=created["manifest_sha256"])


def test_local370_adoption_is_classified_without_native_identity_and_blocks_resend_or_verdict_drift(
    tmp_path: Path,
) -> None:
    adoption_path = Path(r"C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\grok370-forensic-recovery\adoption.json")
    if not adoption_path.is_file():
        pytest.skip("local370 adoption packet is unavailable")
    adoption = json.loads(adoption_path.read_bytes())
    source_path = Path(adoption["source_artifact"]["path"])
    source_sha = sha(source_path.read_bytes())

    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"

        @staticmethod
        def _normalize_batch(output: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return output["verdicts"]

    context = SimpleNamespace(
        plan_root=tmp_path,
        requests={
            370: {
                "ordinal": 370,
                "prompt": "fixture prompt",
                "question_ids": [
                    "core.length_and_scope_fit.no_padding",
                    "core.length_and_scope_fit.no_underbuild",
                    "core.audience_and_purpose_fit.complexity",
                    "core.audience_and_purpose_fit.tone",
                    "core.audience_and_purpose_fit.explanation",
                    "core.audience_and_purpose_fit.intensity",
                    "core.audience_and_purpose_fit.vocabulary",
                    "core.audience_and_purpose_fit.length",
                ],
                "schema": {"type": "object"},
                "source": {"opaque_story_id": "story-370", "artifact_path": str(source_path), "sha256": source_sha, "story_text": source_path.read_text(encoding="utf-8")},
            }
        },
        parent=None,
        passes={},
        runtime=SimpleNamespace(runner=Runner()),
    )
    prior_root = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-renewed-successor-global-20260919-r1")
    prior = {"root": prior_root, "context": context, "plan_root": tmp_path}
    descriptor = {"path": str(adoption_path), "sha256": sha(adoption_path.read_bytes())}
    value = m._local_recovery_binding({"local_recovery": descriptor}, prior)
    assert value and value["ordinal"] == 370 and value["ordinary_native_admission"] is False
    assert len(value["verdicts"]) == 8 and "request_id_hash" not in value["local_identity"]

    resend = dict(adoption)
    resend["automatic_resend_authorized"] = True
    resend_path = tmp_path / "resend-adoption.json"
    resend_path.write_bytes(canon(resend))
    with pytest.raises(ValueError, match="adoption differs"):
        m._local_recovery_binding({"local_recovery": {"path": str(resend_path), "sha256": sha(resend_path.read_bytes())}}, prior)

    projected = json.loads(Path(adoption["projected_message"]["path"]).read_bytes())
    projected["verdicts"][0]["verdict"] = "NO"
    projected_path = tmp_path / "changed-projection.json"
    projected_path.write_bytes(canon(projected))
    changed = dict(adoption)
    changed["projected_message"] = {"path": str(projected_path), "sha256": sha(projected_path.read_bytes())}
    changed_path = tmp_path / "changed-adoption.json"
    changed_path.write_bytes(canon(changed))
    with pytest.raises(ValueError, match="answer hashes|changed more"):
        m._local_recovery_binding({"local_recovery": {"path": str(changed_path), "sha256": sha(changed_path.read_bytes())}}, prior)
