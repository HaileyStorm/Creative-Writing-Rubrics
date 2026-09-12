from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_contention_successor.py"
STAGED_BARRIER = Path(r"C:\Users\Haile\Documents\Codex\2026-08-12\universal-harness\work\grok-healthy-code-rotation-transition-barrier-20260912\owned_launch_barrier.py")
STAGED_BARRIER_SHA256 = "37451e3dfab9b6d6cf6f8282ff4d12f20ea18aac76397cd4e22b6558980c7024"
V5_EPOCH_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-local254-continuation-20260910-r1")
V5_EPOCH_SHA256 = "74012a612915137c43e35eff5bb64b413be0b2dabbdc3aa52ceb4b88d1a245d6"
SNAPSHOT_MANIFEST = Path(r"C:\Users\Haile\Documents\cwr-historical-schema-snapshot-20260912-r1\snapshot-manifest.json")
SNAPSHOT_MANIFEST_SHA256 = "b899f5cd789e840f134b95fec457ed02f4a3a7e9f448e7d0e3b635e90665fdd4"
PARENT = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_v5_suffix.py"


def sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def canon(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def load() -> Any:
    spec = importlib.util.spec_from_file_location("grok_c97_successor_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_staged_barrier_helper_loads_code_only_with_dataclass_registration() -> None:
    value = load(); helper = value._load(STAGED_BARRIER, STAGED_BARRIER_SHA256, "c97_staged_barrier_test")
    assert helper.BarrierBinding.__module__ == "c97_staged_barrier_test" and hasattr(helper, "acquire")


def test_actual_v5_runtime_and_frozen_request_derivation_are_code_only(tmp_path: Path) -> None:
    value = load(); parent = value._load(PARENT, sha(PARENT.read_bytes()), "c97_v5_parent_test")
    epoch, _epoch_raw = parent._load_epoch(V5_EPOCH_ROOT, V5_EPOCH_SHA256)
    runtime = value._load(value.SNAPSHOT, value.SNAPSHOT_HELPERS_SHA256, "c97_v5_snapshot_test").load_runtime_from_epoch(epoch, snapshot_manifest_path=SNAPSHOT_MANIFEST, expected_snapshot_manifest_sha256=SNAPSHOT_MANIFEST_SHA256)
    plan_root = Path(epoch["plan_root"]); plan, _plan_raw = parent._plan(plan_root, epoch["plan_sha256"]); row = parent._request_index(plan)[330]; prompt, schema, ids = parent._request_payload(plan_root, row); source = parent._source_for_pass(plan_root, parent._pass_index(plan)[row["pass_id"]])
    batch = {"schema_version": 1, "kind": "grok_c97_frozen_batch", "parent": {"source": {"path": str(PARENT), "sha256": sha(PARENT.read_bytes())}, "epoch_root": str(V5_EPOCH_ROOT), "epoch_sha256": V5_EPOCH_SHA256, "plan_root": str(plan_root)}, "ordinals": [330], "requests": [{"ordinal": 330, "pass_id": row["pass_id"], "prompt": prompt, "prompt_sha256": sha(prompt.encode()), "schema": {"path": str(schema), "sha256": sha(schema.read_bytes())}, "schema_sha256": sha(schema.read_bytes()), "question_ids": ids, "source": source}], "provider_calls_made": 0}
    path = tmp_path / "batch.json"; path.write_bytes(canon(batch))
    _batch, rows = value._batch({"path": str(path), "sha256": sha(path.read_bytes())}, sha(path.read_bytes()))
    runtime.verify(); assert rows[0]["ordinal"] == 330 and len(runtime.questions) == 178


def write(path: Path, value: Any) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(canon(value))
    return {"path": str(path), "sha256": sha(path.read_bytes())}


def state_fixture(value: Any, tmp_path: Path, *, duplicate: str | None = None, count: int = 10,
                  contact_failure: str | None = None) -> tuple[dict[str, Any], list[int]]:
    route = tmp_path / "route.json"; write(route, {"name": "c97", "model": "fixture", "reported_model": "fixture"})
    gate = write(tmp_path / "gate.json", {}); standing = write(tmp_path / "standing.json", {}); barrier_packet = write(tmp_path / "barrier.json", {})
    calls: list[int] = []; first_contact = threading.Event(); rendezvous = threading.Barrier(count)
    class Broker:
        def __init__(self, _queue: Path) -> None:
            if first_contact.is_set(): raise AssertionError("broker factory re-entered after contact")
            calls.append(-1)
        def run_grok_native_request(self, _name: str, _request: Any, *, before_contact: Any, session_id: str, **_kwargs: Any) -> dict[str, Any]:
            before_contact(); first_contact.set(); rendezvous.wait(timeout=5)
            ordinal = int(_request["prompt"].split("-")[-1]); request = "a" * 64 if duplicate == "request" else f"{ordinal:064x}"
            if ordinal == 279 + count and contact_failure is not None:
                return {"state": contact_failure, "result": None, "failure": {}}
            session = "b" * 64 if duplicate == "session" else f"{ordinal + 100:064x}"
            return {"state": "completed", "result": {"output": {"verdicts": [{"question_id": f"q-{ordinal}"}]}, "runtime": {"request_id_hash": request, "session_id_hash": session, "observed_turns": 1}, "native_envelope_artifact": {"sha256": "c" * 64, "byte_length": 1}}}
    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"
        def _normalize_batch(self, output: Any, **_kwargs: Any) -> list[dict[str, Any]]: return output["verdicts"]
    runtime = SimpleNamespace(runner=Runner(), verify=lambda: None)
    rows = []
    for ordinal in range(280, 280 + count):
        schema = tmp_path / f"schema-{ordinal}.json"; write(schema, {"type": "object"})
        prompt = f"prompt-{ordinal}"; rows.append({"ordinal": ordinal, "prompt": prompt, "prompt_sha256": sha(prompt.encode()), "schema_sha256": sha(schema.read_bytes()), "question_ids": [f"q-{ordinal}"], "schema": {"path": str(schema), "sha256": sha(schema.read_bytes())}, "source": {"opaque_story_id": f"story-{ordinal}", "story_text": "story"}})
    queue = tmp_path / "queue"; queue.mkdir()
    manifest = {"controller_sha256": sha(SOURCE.read_bytes()), "new_route": {"path": str(route), "sha256": sha(route.read_bytes())}, "new_gate": gate, "standing_packet": standing, "barrier_packet": barrier_packet, "frozen_batch": {"path": "fixture", "sha256": "f" * 64}, "queue": {"path": str(queue), "root_hash": "fixture", "path_sha256": sha(str(queue.resolve()).encode())}, "candidate": {"manifest_sha256": value.CANDIDATE_MANIFEST_SHA256}, "barrier_binding": {}}
    return {"manifest": manifest, "manifest_raw": canon({"fixture": True}), "candidate": SimpleNamespace(Broker=Broker, __package__="fixture"), "adapter": SimpleNamespace(), "identities": [], "rows": rows, "runtime": runtime}, calls


def patch_dispatch(monkeypatch: pytest.MonkeyPatch, value: Any, state: dict[str, Any], *, busy: bool = False) -> None:
    class Lease:
        def __init__(self) -> None:
            self.active = 0; self.maximum = 0; self.lock = threading.Lock()
        def assert_held(self, *_args: Any) -> None:
            with self.lock:
                self.active += 1; self.maximum = max(self.maximum, self.active)
            time.sleep(0.002)
            with self.lock: self.active -= 1
    class Binding:
        @classmethod
        def parse(cls, _value: Any) -> object: return object()
    class Barrier:
        BarrierBinding = Binding
        @staticmethod
        @contextmanager
        def acquire(*_args: Any):
            if busy: raise RuntimeError("busy")
            yield lease
    lease = Lease()
    activation = {"barrier_helper": {"path": "fixture", "sha256": "x" * 64}}
    def fixed_state(root: Path, *_args: Any) -> dict[str, Any]:
        root.mkdir(parents=True, exist_ok=True)
        (root / "grok-c97-contention-successor-manifest.json").write_bytes(state["manifest_raw"])
        return state
    monkeypatch.setattr(value, "_state", fixed_state)
    monkeypatch.setattr(value, "_activation", lambda *_args: activation)
    monkeypatch.setattr(value, "_load", lambda *_args: Barrier)
    monkeypatch.setattr(value, "_authority", lambda *_args: {})
    monkeypatch.setattr(value, "_batch", lambda *_args: ({}, state["rows"]))
    monkeypatch.setattr(value, "_semantic", lambda **kwargs: (kwargs["terminal"]["native_identity"], kwargs["terminal"]["verdicts"], {"sha256": "c" * 64}))
    state["lease"] = lease


def test_ten_native_calls_replay_under_one_preconstructed_barrier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, calls = state_fixture(value, tmp_path); patch_dispatch(monkeypatch, value, state)
    result = value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert result == {"state": "completed_replayed", "provider_calls_made": 10, "completed_ordinals": list(range(280, 290))}
    assert calls == [-1] * 10
    replay = json.loads((tmp_path / "run" / "replays" / "wave-0280-slots-10.json").read_bytes())
    assert replay["ordinals"] == list(range(280, 290)) and len(replay["terminals"]) == 10
    assert state["lease"].maximum == 1


def test_existing_wave_intent_blocks_a_second_contact_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, calls = state_fixture(value, tmp_path); patch_dispatch(monkeypatch, value, state)
    value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    with pytest.raises(ValueError, match="wave already started"):
        value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert calls == [-1] * 10


def test_final_partial_wave_uses_its_actual_slot_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, calls = state_fixture(value, tmp_path, count=3); patch_dispatch(monkeypatch, value, state)
    result = value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert result == {"state": "completed_replayed", "provider_calls_made": 3, "completed_ordinals": [280, 281, 282]}
    assert calls == [-1] * 3 and (tmp_path / "run" / "replays" / "wave-0280-slots-03.json").is_file()


def test_crash_after_durable_intent_blocks_reconstruction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, calls = state_fixture(value, tmp_path); patch_dispatch(monkeypatch, value, state)
    def crash(_queue: Path) -> None:
        calls.append(-2); raise RuntimeError("simulated crash")
    state["candidate"] = SimpleNamespace(Broker=crash, __package__="fixture")
    with pytest.raises(RuntimeError, match="simulated crash"):
        value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    first = list(calls)
    with pytest.raises(ValueError, match="wave already started"):
        value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert calls == first


def test_post_contact_failure_preserves_known_broker_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, _calls = state_fixture(value, tmp_path, count=1); patch_dispatch(monkeypatch, value, state)
    def fail_normalization(*_args: Any, **_kwargs: Any) -> list[dict[str, Any]]: raise ValueError("normalization")
    state["runtime"].runner._normalize_batch = fail_normalization
    result = value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    terminal = json.loads((tmp_path / "run" / "attempts" / "request-0280" / "terminal.json").read_bytes())
    assert result["completed_provider_outcomes"] == result["provider_calls_made"] == 1
    assert result["ambiguous_contact_ordinals"] == []
    assert terminal["state"] == "ambiguous" and terminal["contact_admitted"] is True and terminal["broker_contact_state"] == "completed"
    assert terminal["session_id"] and terminal["candidate_result"]["runtime"]["observed_turns"] == 1 and terminal["native_identity"]["observed_turns"] == 1


@pytest.mark.parametrize("contact_failure", ["definitely_not_contacted", "ambiguous"])
def test_partial_wave_preserves_authoritative_contact_accounting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contact_failure: str) -> None:
    value = load()
    state, _calls = state_fixture(value, tmp_path, contact_failure=contact_failure)
    patch_dispatch(monkeypatch, value, state)
    result = value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64,
                                           activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    terminal = json.loads((tmp_path / "run" / "attempts" / "request-0289" / "terminal.json").read_bytes())
    assert terminal["contact_admitted"] is True and terminal["state"] == contact_failure
    assert result["completed_provider_outcomes"] == 9
    assert result["completed_ordinals"] == list(range(280, 289))
    assert result["provider_calls_made"] == (9 if contact_failure == "definitely_not_contacted" else None)
    assert result["ambiguous_contact_ordinals"] == ([] if contact_failure == "definitely_not_contacted" else [289])


def test_semantic_replay_rejects_broker_wrapper_contract_failure(tmp_path: Path) -> None:
    value = load(); schema = tmp_path / "schema.json"; write(schema, {"type": "object"})
    identity = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64, "observed_turns": 1}
    result = {"output": {"verdicts": [{"question_id": "q"}]}, "native_envelope_artifact": {"sha256": sha(b"raw"), "byte_length": 3}}
    class Broker:
        def read_grok_native_envelope(self, _descriptor: Any) -> bytes: return b"raw"
        def _parse_grok_exec_envelope(self, *_args: Any, **_kwargs: Any) -> Any: return SimpleNamespace(state="ambiguous", result={})
    class Adapter:
        def _parse_grok_envelope(self, *_args: Any, **_kwargs: Any) -> tuple[Any, Any, Any]: return result["output"], identity, {}
    runner = SimpleNamespace(EVIDENCE_NORMALIZATION_POLICY="fixture", _normalize_batch=lambda output, **_kwargs: output["verdicts"])
    row = {"ordinal": 280, "prompt": "frozen", "schema": {"path": str(schema)}, "question_ids": ["q"], "source": {"opaque_story_id": "story", "story_text": "story"}}
    terminal = {"state": "completed", "candidate_result": result, "review_route": {"model": "fixture", "reported_model": "fixture"}, "route_sha256": sha(canon({"model": "fixture", "reported_model": "fixture"})), "session_id": "session", "native_identity": identity, "verdicts": result["output"]["verdicts"]}
    with pytest.raises(ValueError, match="semantic replay"):
        value._semantic(candidate=SimpleNamespace(), adapter=Adapter(), broker=Broker(), runtime=SimpleNamespace(runner=runner), row=row, terminal=terminal)


@pytest.mark.parametrize("duplicate", ["request", "session"])
def test_each_native_identity_dimension_blocks_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duplicate: str) -> None:
    value = load(); state, _calls = state_fixture(value, tmp_path, duplicate=duplicate); patch_dispatch(monkeypatch, value, state)
    result = value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert result["state"] == "stopped_no_retry" and not list((tmp_path / "run" / "replays").glob("*.json"))


def test_busy_barrier_blocks_before_broker_construction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, calls = state_fixture(value, tmp_path); patch_dispatch(monkeypatch, value, state, busy=True)
    with pytest.raises(RuntimeError, match="busy"):
        value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert calls == []


def test_new_route_drift_stops_before_native_completion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state, _calls = state_fixture(value, tmp_path); patch_dispatch(monkeypatch, value, state)
    Path(state["manifest"]["new_route"]["path"]).write_bytes(canon({"name": "drifted"}))
    result = value.dispatch_contention_wave(continuation_root=tmp_path / "run", expected_manifest_sha256="m" * 64, activation_packet_path=tmp_path / "activation", expected_activation_packet_sha256="a" * 64)
    assert result["state"] == "stopped_no_retry" and not list((tmp_path / "run" / "replays").glob("*.json"))


def test_closed_prefix_rejects_terminal_identity_drift(tmp_path: Path) -> None:
    value = load(); terminal = write(tmp_path / "terminal.json", {"ordinal": 280, "native_identity": {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}})
    commitments = write(tmp_path / "commitments.json", {"kind": "grok_c97_identity_commitments", "provider_calls_made": 0, "native_identities": [{"request_id_hash": f"{item:064x}", "session_id_hash": f"{1000 + item:064x}"} for item in range(277)]})
    receipt = write(tmp_path / "receipt.json", {"ordinals": [280], "terminals": [{"ordinal": 280, "native_identity": {"request_id_hash": "x" * 64, "session_id_hash": "b" * 64}}], "native_identities": [{"request_id_hash": "x" * 64, "session_id_hash": "b" * 64}]})
    inventory = write(tmp_path / "inventory.json", {"kind": "grok_c97_current_prefix_inventory", "provider_calls_made": 0, "completed_logical_ordinals": [280], "replays": [{"ordinals": [280], "receipt": receipt}], "native_identities": [{"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}], "terminals": [{"ordinal": 280, "terminal": terminal, "native_identity": {"request_id_hash": "x" * 64, "session_id_hash": "b" * 64}}]})
    empty = write(tmp_path / "empty.json", {})
    local = write(tmp_path / "local.json", {"kind": "grok_c97_local_decisions", "provider_calls_made": 0, "decisions": [70, 254]})
    completed = list(range(1, 281)); prefix = write(tmp_path / "prefix.json", {"schema_version": 1, "kind": "grok_c97_closed_prefix_descriptor", "ancestry": empty, "identity_commitments": commitments, "local_decisions": local, "current_prefix_inventory": inventory, "stop_proof": empty, "owned_exit_proof": empty, "completed_logical_ordinals": completed, "remaining_ordinals": value.LOGICAL_ORDINALS[len(completed):], "provider_calls_made": 0})
    with pytest.raises(ValueError, match="terminal identity"):
        value._closed_prefix(prefix, prefix["sha256"])
