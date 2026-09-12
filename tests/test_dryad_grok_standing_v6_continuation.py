from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from shutil import copytree, ignore_patterns
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_standing_v6_continuation.py"
READER = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_successor_collection_replay.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("standing_v6_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def load_reader() -> Any:
    spec = importlib.util.spec_from_file_location("standing_v6_reader_test", READER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def canon(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def candidate_copy(tmp_path: Path) -> Path:
    source = Path(r"C:\Users\Haile\Documents\Codex\2026-08-12\universal-harness\work\grok-standing-authority-v6-candidate\isolated\candidate-v6-standing")
    destination = tmp_path / "candidate"
    copytree(source, destination, ignore=ignore_patterns("__pycache__"))
    return destination


def test_pending_is_exact_and_prefix_ordinals_are_unreachable() -> None:
    value = load()
    assert len(value.PENDING) == 2039 and value.PENDING[0] == 262 and value.PENDING[-1] == 4738
    assert 70 not in value.PENDING and 254 not in value.PENDING and 261 not in value.PENDING
    with pytest.raises(ValueError, match="cannot skip"):
        value._next({263: {"state": "completed"}}, set())


def test_candidate_manifest_rejects_file_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "candidate"; package = root / "model_work_queue"; package.mkdir(parents=True)
    (package / "__init__.py").write_text(""); (package / "broker.py").write_text("class Broker: pass\nclass GrokNativeProviderError(Exception): pass\nclass QueueError(Exception): pass\n")
    files = []
    for path in [package / "__init__.py", package / "broker.py"]:
        files.append({"path": path.relative_to(root).as_posix(), "sha256": sha(path.read_bytes()), "bytes": len(path.read_bytes())})
    manifest = {"baseline_manifest_sha256": "a" * 64, "explicit_exclusion": ["candidate-manifest.json"], "files": files, "kind": "complete_candidate_runtime_probe_set", "schema_version": 7}
    path = root / "candidate-manifest.json"; path.write_bytes(canon(manifest)); digest = sha(path.read_bytes())
    monkeypatch.setattr(value, "CANDIDATE_MANIFEST_SHA", digest)
    _module, parsed = value._candidate(root, digest)
    assert parsed["schema_version"] == 7
    (package / "broker.py").write_text("class Broker: changed = True\n")
    with pytest.raises(ValueError, match="candidate root drift"):
        value._candidate(root, digest)


def test_expired_review_blocks_before_candidate_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); queue = tmp_path / "queue"; manifest = {"controller_sha256": sha(SOURCE.read_bytes()), "candidate": {"manifest_sha256": "c" * 64}, "packet": {"sha256": "p" * 64}, "standing_source": {"sha256": "s" * 64}, "queue": {"path": str(queue.resolve()), "root_hash": "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a"}}
    raw = canon(manifest); now = datetime.now(timezone.utc)
    gate = {"provider": "grok", "account_class": "subscription", "contract_hash": "c" * 64, "source_evidence_hash": "s" * 64, "state": "healthy"}; gate_path = tmp_path / "gate.json"; gate_path.write_bytes(canon(gate)); route = {"name": "fixture"}; route_hash, gate_hash = sha(canon(route)), sha(gate_path.read_bytes()); review = {"schema_version": 1, "decision": "approved_dryad_grok_standing_v6_untouched_wave", "controller_sha256": manifest["controller_sha256"], "manifest_sha256": sha(raw), "candidate_manifest_sha256": "c" * 64, "packet_sha256": "p" * 64, "standing_source_sha256": "s" * 64, "queue_root": str(queue.resolve()), "queue_root_hash": "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a", "queue_path_sha256": sha(str(queue.resolve()).encode()), "route_name": "fixture", "route_sha256": route_hash, "route": route, "gate_evidence_path": str(gate_path), "gate_evidence_sha256": gate_hash, "gate_sha256": gate_hash, "gate_identity": gate, "reviewed_at": (now - timedelta(minutes=20)).isoformat(), "expires_at": (now - timedelta(minutes=10)).isoformat()}
    path = tmp_path / "review.json"; path.write_bytes(canon(review))
    with pytest.raises(ValueError, match="not fresh"):
        value._review(path, sha(path.read_bytes()), manifest, raw)


def test_replay_record_rejects_duplicate_native_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root = tmp_path / "root"; (root / "replays").mkdir(parents=True); (root / "attempts" / "request-0262").mkdir(parents=True); (root / "attempts" / "request-0263").mkdir(parents=True)
    identity = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64, "observed_turns": 1}; manifest = {"controller_sha256": "c" * 64, "candidate": {"manifest_sha256": "d" * 64}, "packet": {"sha256": "e" * 64}, "standing_source": {"sha256": "f" * 64}}
    raw = canon(manifest)
    for ordinal in (262, 263): (root / "attempts" / f"request-{ordinal:04d}" / "terminal.json").write_bytes(canon({"ordinal": ordinal}))
    record = {"schema_version": 1, "evidence_class": "source_bound_standing_v6_candidate_replay_v1", "controller_sha256": "c" * 64, "manifest_sha256": sha(raw), "candidate_manifest_sha256": "d" * 64, "packet_sha256": "e" * 64, "standing_source_sha256": "f" * 64, "ordinals": [262, 263], "terminals": [{"ordinal": 262, "terminal_sha256": sha((root / "attempts" / "request-0262" / "terminal.json").read_bytes())}, {"ordinal": 263, "terminal_sha256": sha((root / "attempts" / "request-0263" / "terminal.json").read_bytes())}], "native_identities": [identity, identity], "provider_calls_made": 0}
    (root / "replays" / "wave-0262-slots-02.json").write_bytes(canon(record))
    with pytest.raises(ValueError, match="collision"):
        value._replayed(root, manifest, raw)


def test_real_candidate_envelope_descriptor_rejects_tamper(tmp_path: Path) -> None:
    value = load(); candidate_root = candidate_copy(tmp_path)
    module, _manifest = value._candidate(candidate_root, value.CANDIDATE_MANIFEST_SHA)
    broker = module.Broker(tmp_path / "queue"); raw = b"sealed synthetic envelope"; digest = sha(raw); path = broker.artifacts / digest[:2] / digest[2:]; path.parent.mkdir(parents=True); path.write_bytes(raw)
    descriptor = {"schema_version": 1, "sha256": digest, "byte_length": len(raw)}
    assert broker.read_grok_native_envelope(descriptor) == raw
    path.write_bytes(b"tampered")
    with pytest.raises(module.QueueError):
        broker.read_grok_native_envelope(descriptor)


def test_real_candidate_exposes_replay_callable_shape_without_root_bytecode(tmp_path: Path) -> None:
    value = load(); candidate_root = candidate_copy(tmp_path)
    module, _manifest = value._candidate(candidate_root, value.CANDIDATE_MANIFEST_SHA)
    assert {"route_name", "request", "output_schema", "nonvisual_max_turns", "session_id", "before_contact", "expected_route_sha256"} <= set(inspect.signature(module.Broker.run_grok_native_request).parameters)
    assert {"raw", "route", "request", "expected_session_id"} <= set(inspect.signature(module.Broker._parse_grok_exec_envelope).parameters)
    previous_bytecode = sys.dont_write_bytecode; sys.dont_write_bytecode = True
    try:
        adapter = __import__(module.__package__ + ".adapters.grok_exec", fromlist=["_parse_grok_envelope"])
    finally:
        sys.dont_write_bytecode = previous_bytecode
    assert {"raw", "model", "reported_model", "session_id", "schema", "max_turns", "exact_turns"} <= set(inspect.signature(adapter._parse_grok_envelope).parameters)
    assert value._inventory(candidate_root) == {"candidate-manifest.json": sha((candidate_root / "candidate-manifest.json").read_bytes()), **{item["path"]: item["sha256"] for item in json.loads((candidate_root / "candidate-manifest.json").read_bytes())["files"]}}


def _dispatch_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, states: list[str], normalize_failure: bool = False) -> tuple[Any, Path, list[str]]:
    value = load(); root = tmp_path / "continuation"; root.mkdir(); queue = tmp_path / "queue"
    manifest = {"controller_sha256": sha(SOURCE.read_bytes()), "candidate": {"root": str(tmp_path), "manifest_sha256": "c" * 64}, "packet": {"path": str(tmp_path / "packet"), "sha256": "p" * 64}, "standing_source": {"path": str(tmp_path / "standing"), "sha256": "s" * 64}, "queue": {"path": str(queue), "root_hash": "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a", "path_sha256": sha(str(queue.resolve()).encode())}, "pending_ordinals": value.PENDING}
    raw = canon(manifest); (root / "standing-v6-continuation-manifest.json").write_bytes(raw)
    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"
        def _normalize_batch(self, output: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            if normalize_failure: raise ValueError("fixture normalization failed")
            return output["verdicts"]
    class Parent:
        def _runtime_from_epoch(self, _epoch: Any) -> Any: return type("Runtime", (), {"runner": Runner()})()
        def _plan(self, *_args: Any) -> tuple[dict[str, Any], bytes]: return {}, b""
        def _pass_index(self, *_args: Any) -> dict[str, Any]: return {"pass": {}}
        def _request_payload(self, *_args: Any) -> tuple[str, Path, list[str]]: return "prompt", tmp_path / "schema.json", ["q"]
        def _source_for_pass(self, *_args: Any) -> dict[str, str]: return {"sha256": "x", "opaque_story_id": "fixture", "story_text": "story"}
    (tmp_path / "schema.json").write_bytes(canon({"type": "object"}))
    requests = {ordinal: {"ordinal": ordinal, "pass_id": "pass", "prompt_sha256": "a", "schema_sha256": "b", "question_ids": ["q"]} for ordinal in (262, 263)}
    route = {"model": "fixture-model", "reported_model": "fixture-build"}
    review = {"queue_root": str(queue), "route_name": "route", "route_sha256": sha(canon(route)), "gate_sha256": "g" * 64, "route": route, "gate_identity": {}}
    artifacts: dict[str, bytes] = {}; calls: list[str] = []
    class Broker:
        def __init__(self, _root: Path) -> None: pass
        def run_grok_native_request(self, _name: str, _request: Any, *, before_contact: Any, **_kwargs: Any) -> dict[str, Any]:
            before_contact(); state = states.pop(0); calls.append(state)
            if state != "completed": return {"state": state, "result": None, "failure": {"provider_error_type": "Fixture"}}
            ordinal = 262 if len(calls) == 1 else 263; identity = {"request_id_hash": str(ordinal)[-1] * 64, "session_id_hash": str(ordinal)[-1] * 64, "observed_turns": 1}; output = {"verdicts": [{"question_id": "q"}]}; envelope = canon({"output": output, "identity": identity}); digest = sha(envelope); artifacts[digest] = envelope
            return {"state": "completed", "failure": None, "result": {"output": output, "runtime": identity, "native_envelope_artifact": {"schema_version": 1, "sha256": digest, "byte_length": len(envelope)}}}
        def read_grok_native_envelope(self, descriptor: dict[str, Any]) -> bytes: return artifacts[descriptor["sha256"]]
        def _parse_grok_exec_envelope(self, raw: bytes, *_args: Any, **_kwargs: Any) -> Any: return SimpleNamespace(state="completed", result=json.loads(raw)["result"])
    adapter = SimpleNamespace(_parse_grok_envelope=lambda raw, **_kwargs: (json.loads(raw)["output"], json.loads(raw)["identity"], {}))
    candidate = SimpleNamespace(Broker=Broker, __package__="fixture_candidate")
    monkeypatch.setattr(value, "_manifest", lambda *_args: (manifest, raw)); monkeypatch.setattr(value, "_candidate", lambda *_args: (candidate, {})); monkeypatch.setattr(value, "_packet", lambda *_args: {}); monkeypatch.setattr(value, "_standing", lambda *_args: {}); monkeypatch.setattr(value, "_review", lambda *_args: review); monkeypatch.setattr(value, "_prefix_context", lambda *_args: (object(), Parent(), tmp_path, requests, {"plan_sha256": "p"}, []))
    monkeypatch.setattr(value.importlib, "import_module", lambda _name: adapter)
    return value, root, calls


def test_dispatch_replays_candidate_semantics_before_next_wave(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = _dispatch_fixture(tmp_path, monkeypatch, states=["completed", "completed"])
    first = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert first["state"] == "completed_pending_replay" and first["provider_calls_made"] == 1
    replay = value.replay_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1)
    assert replay["native_identities"] == [{"request_id_hash": "2" * 64, "session_id_hash": "2" * 64, "observed_turns": 1}]
    verified = value.verify_standing_v6_replay_chain(continuation_root=root, expected_manifest_sha256=sha((root / "standing-v6-continuation-manifest.json").read_bytes()), expected_controller_sha256=sha(SOURCE.read_bytes()))
    public_identity = {"request_id_hash": "2" * 64, "session_id_hash": "2" * 64}
    assert verified["candidate_native_replay_ordinals"] == [262] and verified["candidate_native_identities"] == [public_identity]
    assert verified["candidate_native_terminals"][0]["native_identity"] == public_identity == load_reader()._identity(verified["candidate_native_terminals"][0]["native_identity"], "fixture")
    second = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=263, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert second["state"] == "completed_pending_replay" and calls == ["completed", "completed"]


def test_noncompleted_candidate_outcome_is_terminal_and_not_resent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = _dispatch_fixture(tmp_path, monkeypatch, states=["ambiguous"])
    outcome = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    terminal = json.loads((root / "attempts/request-0262/terminal.json").read_bytes())
    assert outcome["state"] == "stopped_no_retry" and terminal["state"] == "ambiguous" and terminal["broker_outcome"]["state"] == "ambiguous"
    assert outcome["provider_calls_made"] is None and outcome["completed_provider_outcomes"] == 0 and outcome["ambiguous_contact_ordinals"] == [262]
    with pytest.raises(ValueError, match="prior cell incomplete"):
        value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert calls == ["ambiguous"]


def test_normalization_failure_retains_candidate_result_and_blocks_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = _dispatch_fixture(tmp_path, monkeypatch, states=["completed"], normalize_failure=True)
    outcome = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    terminal = json.loads((root / "attempts/request-0262/terminal.json").read_bytes())
    assert outcome["state"] == "stopped_no_retry" and terminal["state"] == "ambiguous" and terminal["candidate_result"]["output"]["verdicts"] == [{"question_id": "q"}] and terminal["native_identity"]["observed_turns"] == 1
    assert outcome["provider_calls_made"] == outcome["completed_provider_outcomes"] == 1 and outcome["ambiguous_contact_ordinals"] == []
    with pytest.raises(ValueError, match="prior cell incomplete"):
        value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert calls == ["completed"]
