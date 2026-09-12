from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_runtime_data_successor.py"
spec = importlib.util.spec_from_file_location("runtime_data_successor_test", SOURCE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def put(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(m._canon(value))
    return m._sha(path.read_bytes())


def test_pending_tail_is_fixed_after_accepted_279_recovery() -> None:
    assert m.PENDING == [*range(280, 1611), *range(4049, 4739)]
    assert len(m.PENDING) == 2021 and m.WAVE_CAP == 1


def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, normalize_error: bool = False) -> tuple[Any, Path, list[str]]:
    calls: list[str] = []
    ids = [f"q{number}" for number in range(8)]
    route = {"model": "grok-4.6", "reported_model": "grok-4.6-build"}
    route_sha = m._sha(m._canon(route))
    def bound(name: str) -> dict[str, str]:
        path = tmp_path / f"{name}.json"
        return {"path": str(path), "sha256": put(path, {"name": name})}
    gate = tmp_path / "gate.json"; gate_sha = put(gate, {"provider": "x", "account_class": "included", "contract_hash": "c", "source_evidence_hash": "s", "state": "healthy"})
    packet = tmp_path / "packet.json"; packet_sha = put(packet, {"packet": 1})
    standing = tmp_path / "standing.json"; standing_sha = put(standing, {"standing": 1})
    original = tmp_path / "original"; original.mkdir()
    original_manifest = original / "standing-v6-partial-successor-manifest.json"; original_manifest.write_bytes(b"original")
    closure = {"candidate": {"root": str(tmp_path), "manifest_sha256": "c" * 64}, "queue": {"path": str(tmp_path / "queue"), "root_hash": "q", "path_sha256": "p"}, "route": {"name": "grok", "sha256": route_sha}, "packet": {"path": str(packet), "sha256": packet_sha}, "standing_source": {"path": str(standing), "sha256": standing_sha}, "gate": {"path": str(gate), "sha256": gate_sha}, "runtime_loader": bound("loader"), "prefix_adapter": bound("prefix"), "recovery_controller": bound("recovery-controller"), "snapshot_manifest": bound("snapshot"), "recovery_record": bound("recovery-record"), "recovery_adoption": bound("recovery-adoption"), "original_continuation": {"root": str(original), "manifest_sha256": m._sha(original_manifest.read_bytes())}}
    manifest = {"controller_sha256": m._sha(SOURCE.read_bytes()), "source_closure": closure, "source_closure_sha256": m._sha(m._canon(closure))}
    raw = m._canon(manifest)
    (tmp_path / "runtime-data-successor-manifest.json").write_bytes(raw)
    result = {"output": {"verdicts": [{"question_id": item} for item in ids]}, "runtime": {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64, "observed_turns": 1}, "native_envelope_artifact": {"sha256": "e" * 64, "byte_length": 1}}

    class Broker:
        def __init__(self, _path: Path) -> None: pass
        def run_grok_native_request(self, _route: str, _request: Any, **kwargs: Any) -> dict[str, Any]:
            kwargs["before_contact"](); calls.append("280")
            return {"state": "completed", "result": result}

    def normalize(output: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        if normalize_error: raise ValueError("normalization")
        return output["verdicts"]

    runtime = SimpleNamespace(verify=lambda: None, runner=SimpleNamespace(EVIDENCE_NORMALIZATION_POLICY="policy", _normalize_batch=normalize))
    parent = SimpleNamespace(_request_payload=lambda *_args: ("prompt", tmp_path / "schema.json", ids), _source_for_pass=lambda *_args: {"sha256": "story", "opaque_story_id": "artifact", "story_text": "text"})
    put(tmp_path / "schema.json", {})
    base = SimpleNamespace(_native_identity=lambda value, _label: dict(value), _candidate=lambda *_args: {}, _packet=lambda *_args: {}, _standing=lambda *_args: {}, _semantic_replay_terminal=lambda **kwargs: (kwargs["terminal"]["native_identity"], kwargs["terminal"]["verdicts"], kwargs["terminal"]["candidate_result"]["native_envelope_artifact"]))
    context = SimpleNamespace(runtime=runtime, candidate=SimpleNamespace(Broker=Broker), parent=parent, base=base, plan_root=tmp_path, passes={"p": {}}, requests={ordinal: {"pass_id": "p", "question_ids": ids, "prompt_sha256": "prompt", "schema_sha256": "schema"} for ordinal in (280, 281)})
    state = {"manifest": manifest, "manifest_raw": raw, "context": context, "recovered": {"ordinal": 279}, "adoption": {}, "prior_identities": [{"request_id_hash": f"{index:064x}", "session_id_hash": f"{index + 9000:064x}"} for index in range(277)]}
    review = {"route_name": "grok", "route": route, "route_sha256": route_sha, "gate_sha256": gate_sha, "gate_identity": {"provider": "x", "account_class": "included", "contract_hash": "c", "source_evidence_hash": "s", "state": "healthy"}}
    monkeypatch.setattr(m, "verify_runtime_data_successor", lambda **_kwargs: state)
    monkeypatch.setattr(m, "_review", lambda *_args: review)
    return m, tmp_path, calls


def test_single_dispatch_replay_then_next_ordinal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture(tmp_path, monkeypatch)
    result = value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    assert result["state"] == "completed_pending_replay" and calls == ["280"]
    replay = value.replay_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1)
    assert replay["provider_calls_made"] == 0
    assert value._next(value._records(root), value._replayed(root, value.verify_runtime_data_successor())[0]) == 281


@pytest.mark.parametrize("field", ["request_id_hash", "session_id_hash"])
def test_duplicate_ids_are_independent_collisions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    value, root, calls = fixture(tmp_path, monkeypatch)
    state = value.verify_runtime_data_successor()
    state["prior_identities"][0][field] = "a" * 64 if field == "request_id_hash" else "b" * 64
    result = value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    assert calls == ["280"] and result["completed_provider_outcomes"] == 1
    terminal = json.loads(value._attempt(root, 280, "terminal.json").read_bytes())
    assert terminal["candidate_result"]["runtime"][field]


@pytest.mark.parametrize("name", ["runtime_loader", "prefix_adapter", "recovery_controller", "snapshot_manifest", "recovery_record", "recovery_adoption", "packet", "standing_source", "gate"])
def test_precontact_source_drift_has_zero_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    value, root, calls = fixture(tmp_path, monkeypatch)
    state = value.verify_runtime_data_successor()
    path = Path(state["manifest"]["source_closure"][name]["path"]); path.write_bytes(b"drift")
    result = value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    terminal = json.loads(value._attempt(root, 280, "terminal.json").read_bytes())
    assert result["provider_calls_made"] == 0 and calls == []
    assert terminal["state"] == "definitely_not_contacted" and terminal["before_contact_error"]["error_type"] == "ValueError"


def test_completed_result_is_retained_after_postcontact_validation_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture(tmp_path, monkeypatch, normalize_error=True)
    result = value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    terminal = json.loads(value._attempt(root, 280, "terminal.json").read_bytes())
    assert calls == ["280"] and result["completed_provider_outcomes"] == result["provider_calls_made"] == 1
    assert terminal["state"] == "ambiguous" and terminal["candidate_result"]["native_envelope_artifact"]["sha256"] == "e" * 64


def test_replayed_future_identity_blocks_a_separate_next_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = fixture(tmp_path, monkeypatch)
    value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    value.replay_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1)
    result = value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=281, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    terminal = json.loads(value._attempt(root, 281, "terminal.json").read_bytes())
    assert calls == ["280", "280"] and result["completed_provider_outcomes"] == 1
    assert terminal["candidate_result"]["runtime"]["request_id_hash"] == "a" * 64


def test_runtime_drift_after_semantic_replay_prevents_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, _calls = fixture(tmp_path, monkeypatch)
    value.dispatch_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1, arming_review_path=root / "review", expected_arming_review_sha256="v" * 64)
    state = value.verify_runtime_data_successor(); drifted = False
    original_replay = state["context"].base._semantic_replay_terminal
    def replay_then_drift(**kwargs: Any) -> tuple[Any, Any, Any]:
        nonlocal drifted
        result = original_replay(**kwargs); drifted = True
        return result
    state["context"].base._semantic_replay_terminal = replay_then_drift
    state["context"].runtime.verify = lambda: (_ for _ in ()).throw(ValueError("runtime drift")) if drifted else None
    with pytest.raises(ValueError, match="runtime drift"):
        value.replay_runtime_data_successor(continuation_root=root, expected_manifest_sha256="m" * 64, start_ordinal=280, wave_size=1)
    assert not value._replay(root, 280).exists()


def test_adoption_requires_the_exact_accepted_recovery_record(tmp_path: Path) -> None:
    record = tmp_path / "recovery.json"; record_sha = put(record, {"recovery": 279})
    adoption = tmp_path / "adoption.json"
    recovered = {"original_terminal": {"sha256": "t" * 64}, "native_identity": {"request_id_hash": "r" * 64, "session_id_hash": "s" * 64}}
    closure = {"recovery_record": {"path": str(record), "sha256": record_sha}, "recovery_adoption": {"path": str(adoption), "sha256": ""}, "recovery_controller": {"sha256": "c" * 64}, "runtime_loader": {"sha256": "l" * 64}, "prefix_adapter": {"sha256": "p" * 64}, "snapshot_manifest": {"sha256": "m" * 64}, "original_continuation": {"manifest_sha256": "o" * 64}}
    accepted = {"schema_version": 1, "decision": "approved_native_279_runtime_data_recovery", "recovery_record": closure["recovery_record"], "recovery_source_sha256": "c" * 64, "loader_sha256": "l" * 64, "prefix_adapter_sha256": "p" * 64, "snapshot_manifest_sha256": "m" * 64, "original_continuation_manifest_sha256": "o" * 64, "original_terminal_sha256": "t" * 64, "native_identity": recovered["native_identity"], "approved_at": "2026-09-12T00:00:00Z", "reviewer": "reviewer", "provider_calls_made": 0, "automatic_resend_authorized": False}
    closure["recovery_adoption"]["sha256"] = put(adoption, accepted)
    assert m._adoption(SimpleNamespace(), closure, recovered)["decision"] == accepted["decision"]
    rejected = {**accepted, "native_identity": {"request_id_hash": "x" * 64, "session_id_hash": "s" * 64}}
    closure["recovery_adoption"]["sha256"] = put(adoption, rejected)
    with pytest.raises(ValueError, match="adoption differs"):
        m._adoption(SimpleNamespace(), closure, recovered)
