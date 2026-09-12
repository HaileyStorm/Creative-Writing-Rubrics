from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_standing_v6_partial_successor.py"
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-standing-v6-partial-reconciliation-20260912-r3\reconciliation.json")
R3_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok-standing-v6-continuation-20260912-r3-serialized")


def load() -> Any:
    spec = importlib.util.spec_from_file_location("standing_v6_partial_successor_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_partial_schedule_and_reconciliation_are_exact(tmp_path: Path) -> None:
    value = load()
    assert len(value.PENDING) == 2030
    assert value.PENDING[:2] == [266, 272]
    assert value.PENDING[-1] == 4738
    assert set(value.PEER_ORDINALS).isdisjoint(value.PENDING)
    partial = value._partial(RECONCILIATION, value.PARTIAL_RECONCILIATION_SHA)
    assert [item["ordinal"] for item in partial["native_peers"]] == value.PEER_ORDINALS
    assert partial["uncontacted"]["ordinal"] == 266
    assert partial["uncontacted"]["contact_admitted"] is True
    roots = value._source_roots(partial)
    assert sorted(map(int, roots)) == value.PEER_ORDINALS
    assert all(set(item) == {"root", "terminal", "authorization"} for item in roots.values())
    altered = tmp_path / "reconciliation.json"
    altered.write_bytes(RECONCILIATION.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="partial reconciliation differs"):
        value._partial(altered, value.PARTIAL_RECONCILIATION_SHA)


def test_actual_nine_peer_semantic_replay_is_provider_free() -> None:
    value = load()
    partial = value._partial(RECONCILIATION, value.PARTIAL_RECONCILIATION_SHA)
    r3_manifest = json.loads((R3_ROOT / "standing-v6-continuation-manifest.json").read_bytes())
    manifest = {
        "partial_reconciliation": {"path": str(RECONCILIATION), "sha256": value.PARTIAL_RECONCILIATION_SHA},
        "terminal_source_roots": value._source_roots(partial),
        "candidate": r3_manifest["candidate"], "prefix": r3_manifest["prefix"], "queue": r3_manifest["queue"],
    }
    _base, _candidate, _parent, _plan_root, _requests, _epoch, identities, peers = value._peer_context(manifest)
    assert len(identities) == 268
    assert [item["ordinal"] for item in peers] == value.PEER_ORDINALS
    assert sum(len(item["verdicts"]) for item in peers) == partial["native_peer_verdict_count"] == 72


def fixture_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, drift: bool = False, normalize_error: bool = False) -> tuple[Any, Path, list[str]]:
    value = load()
    root = tmp_path / "successor"
    root.mkdir()
    queue = tmp_path / "queue"
    manifest = {
        "controller_sha256": "0" * 64 if drift else sha(SOURCE.read_bytes()),
        "candidate": {"root": str(tmp_path), "manifest_sha256": "c" * 64},
        "packet": {"path": str(tmp_path / "packet"), "sha256": "p" * 64},
        "standing_source": {"path": str(tmp_path / "standing"), "sha256": "s" * 64},
        "queue": {"path": str(queue), "root_hash": "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a", "path_sha256": sha(str(queue.resolve()).encode())},
        "prefix": {}, "partial_reconciliation": {"path": str(tmp_path / "partial"), "sha256": "r" * 64},
        "terminal_source_roots": {}, "pending_ordinals": value.PENDING, "operational_wave_cap": 1,
        "temporary_workaround": {"kind": "caller_wave_serialization"}, "provider_calls_made": 0, "execution_authority": False,
        "serialized_controller": {"path": str(value.SERIALIZED.resolve()), "sha256": value.SERIALIZED_SHA},
        "evidence_class": "dryad_grok_standing_v6_partial_successor_v1", "schema_version": 1,
    }
    raw = canon(manifest)
    manifest_path = root / "standing-v6-partial-successor-manifest.json"
    manifest_path.write_bytes(raw)
    schema_path = tmp_path / "schema.json"
    schema_path.write_bytes(canon({"type": "object"}))
    calls: list[str] = []
    artifact: dict[str, bytes] = {}

    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"
        def _normalize_batch(self, output: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            if normalize_error:
                raise ValueError("fixture normalization error")
            return output["verdicts"]

    class Parent:
        def _plan(self, *_args: Any) -> tuple[dict[str, Any], bytes]: return {}, b""
        def _pass_index(self, *_args: Any) -> dict[str, Any]: return {"pass": {}}
        def _request_payload(self, *_args: Any) -> tuple[str, Path, list[str]]: return "prompt", schema_path, ["q"]
        def _source_for_pass(self, *_args: Any) -> dict[str, str]: return {"sha256": "x", "opaque_story_id": "fixture", "story_text": "story"}
        def _runtime_from_epoch(self, _epoch: Any) -> Any: return SimpleNamespace(runner=Runner())

    class Broker:
        def __init__(self, _root: Path) -> None: pass
        def run_grok_native_request(self, _name: str, _request: Any, *, before_contact: Any, **_kwargs: Any) -> dict[str, Any]:
            before_contact()
            ordinal = 266 if not calls else 272
            calls.append(str(ordinal))
            identity = {"request_id_hash": ("a" if ordinal == 266 else "c") * 64, "session_id_hash": ("b" if ordinal == 266 else "d") * 64, "observed_turns": 1}
            output = {"verdicts": [{"question_id": "q"}]}
            envelope = canon({"output": output, "identity": identity})
            digest = sha(envelope)
            artifact[digest] = envelope
            return {"state": "completed", "result": {"output": output, "runtime": identity, "native_envelope_artifact": {"schema_version": 1, "sha256": digest, "byte_length": len(envelope)}}}
        def read_grok_native_envelope(self, descriptor: dict[str, Any]) -> bytes: return artifact[descriptor["sha256"]]

    class Base:
        def _candidate(self, *_args: Any) -> tuple[Any, dict[str, Any]]: return SimpleNamespace(Broker=Broker), {}
        def _packet(self, *_args: Any) -> dict[str, Any]: return {}
        def _standing(self, *_args: Any) -> dict[str, Any]: return {}
        def _native_identity(self, identity: dict[str, Any], _label: str) -> dict[str, Any]: return identity
        def _semantic_replay_terminal(self, *, terminal: dict[str, Any], **_kwargs: Any) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
            result = terminal["candidate_result"]
            return terminal["native_identity"], terminal["verdicts"], result["native_envelope_artifact"]
        def _public_identity(self, identity: dict[str, Any]) -> dict[str, str]: return {key: identity[key] for key in ("request_id_hash", "session_id_hash")}

    route = {"model": "fixture", "reported_model": "fixture-build", "max_concurrency": 10}
    review = {"route_name": "route", "route_sha256": sha(canon(route)), "gate_sha256": "g" * 64, "route": route, "gate_identity": {}}
    requests = {ordinal: {"ordinal": ordinal, "pass_id": "pass", "prompt_sha256": "a", "schema_sha256": "b", "question_ids": ["q"]} for ordinal in (266, 272)}
    monkeypatch.setattr(value, "_manifest", lambda *_args: (manifest, raw))
    monkeypatch.setattr(value, "_base", lambda: Base())
    monkeypatch.setattr(value, "_diagnosis", dict)
    monkeypatch.setattr(value, "_review", lambda *_args: review)
    monkeypatch.setattr(value, "_peer_context", lambda *_args: (Base(), SimpleNamespace(Broker=Broker), Parent(), tmp_path, requests, {"plan_sha256": "p"}, [], []))
    return value, root, calls


def test_one_cell_dispatch_replay_and_no_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture_dispatch(tmp_path, monkeypatch)
    dispatched = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert dispatched["state"] == "completed_pending_replay"
    assert dispatched["provider_calls_made"] == 1
    assert calls == ["266"]
    with pytest.raises(ValueError, match="prior cell incomplete"):
        value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    with pytest.raises(ValueError, match="dispatch geometry"):
        value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=2, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    replay = value.replay_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1)
    assert replay["ordinals"] == [266]
    assert replay["provider_calls_made"] == 0
    chain = value.verify_standing_v6_replay_chain(continuation_root=root, expected_manifest_sha256=sha((root / "standing-v6-partial-successor-manifest.json").read_bytes()), expected_controller_sha256=sha(SOURCE.read_bytes()))
    assert chain["candidate_native_replay_ordinals"] == [266]
    next_dispatched = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=272, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert next_dispatched["state"] == "completed_pending_replay"
    assert calls == ["266", "272"]


def test_dispatch_rejects_controller_drift_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture_dispatch(tmp_path, monkeypatch, drift=True)
    outcome = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    terminal = json.loads((root / "attempts" / "request-0266" / "terminal.json").read_bytes())
    assert outcome["state"] == "stopped_no_retry"
    assert calls == []
    assert terminal["state"] == "definitely_not_contacted"
    assert terminal["before_contact_error"]["error_type"] == "ValueError"


def test_completed_outcome_keeps_result_and_accounting_when_normalization_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture_dispatch(tmp_path, monkeypatch, normalize_error=True)
    outcome = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    terminal = json.loads((root / "attempts" / "request-0266" / "terminal.json").read_bytes())
    assert calls == ["266"]
    assert outcome["state"] == "stopped_no_retry"
    assert outcome["provider_calls_made"] == outcome["completed_provider_outcomes"] == 1
    assert outcome["ambiguous_contact_ordinals"] == []
    assert terminal["state"] == "ambiguous"
    assert terminal["candidate_result"]["native_envelope_artifact"]["sha256"]
    assert terminal["native_identity"]["request_id_hash"] == "a" * 64


def test_request_or_session_identity_reuse_is_rejected_in_dispatch_and_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture_dispatch(tmp_path, monkeypatch)
    collision = {"request_id_hash": "a" * 64, "session_id_hash": "z" * 64, "observed_turns": 1}
    original_context = value._peer_context
    def collision_context(*_args: Any) -> tuple[Any, ...]:
        context = original_context()
        return (*context[:6], [collision], context[7])
    monkeypatch.setattr(value, "_peer_context", collision_context)
    dispatched = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert calls == ["266"]
    assert dispatched["completed_provider_outcomes"] == 1
    assert dispatched["failures"][0]["error_type"] == "ValueError"
    replay_tmp = tmp_path / "replay"
    replay_tmp.mkdir()
    value, root, _calls = fixture_dispatch(replay_tmp, monkeypatch)
    value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="z" * 64)
    original_context = value._peer_context
    def replay_collision_context(*_args: Any) -> tuple[Any, ...]:
        context = original_context()
        return (*context[:6], [collision], context[7])
    monkeypatch.setattr(value, "_peer_context", replay_collision_context)
    with pytest.raises(ValueError, match="native identity collision"):
        value.replay_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1)


def test_callback_rechecks_packet_source_before_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture_dispatch(tmp_path, monkeypatch)
    packet_checks = 0

    class PacketDriftBase:
        def _candidate(self, *_args: Any) -> tuple[None, dict[str, Any]]: return None, {}
        def _packet(self, *_args: Any) -> dict[str, Any]:
            nonlocal packet_checks
            packet_checks += 1
            if packet_checks == 2:
                raise ValueError("packet changed")
            return {}
        def _standing(self, *_args: Any) -> dict[str, Any]: return {}

    monkeypatch.setattr(value, "_base", PacketDriftBase)
    outcome = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=266, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="z" * 64)
    terminal = json.loads((root / "attempts" / "request-0266" / "terminal.json").read_bytes())
    assert outcome["state"] == "stopped_no_retry"
    assert calls == []
    assert packet_checks == 2
    assert terminal["before_contact_error"]["error_type"] == "ValueError"
