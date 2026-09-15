from __future__ import annotations

import importlib.util
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_renewed_successor.py"
spec = importlib.util.spec_from_file_location("grok_renewed_successor_test", SOURCE)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_historical_hash_pairs_join_new_native_identities_without_reminting() -> None:
    historical = {"request_id_hash": "1" * 64, "session_id_hash": "2" * 64}
    current = {"request_id_hash": "3" * 64, "session_id_hash": "4" * 64, "observed_turns": 1}
    assert m._identities_unique([historical, current])
    assert not m._identities_unique([historical, {**current, "session_id_hash": "2" * 64}])
    assert not m._identities_unique([historical, {**current, "request_id_hash": "1" * 64}])
    with pytest.raises(ValueError):
        m._native_identity(historical, "new terminal")


def _write(path: Path, value: Any) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(m._canon(value))
    return {"path": str(path), "sha256": m._sha(path.read_bytes())}


def _source_closure(tmp_path: Path) -> dict[str, Any]:
    standing = _write(
        tmp_path / "renewed-standing.json",
        {
            "schema_version": 3,
            "provider": "fixture",
            "account_class": "included",
            "allowance_state": "available",
            "checked_at": "2099-01-01T00:00:00+00:00",
            "expires_at": "2099-01-02T00:00:00+00:00",
            "authorization": {
                "scope": {
                    "automatic_resend": False,
                    "zero_charge_only": True,
                    "paid_fallback": False,
                    "route": "grok-renewed-fixture",
                    "broker_root_hash": "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a",
                }
            },
        },
    )
    gate = _write(
        tmp_path / "renewed-gate.json",
        {
            "provider": "fixture",
            "account_class": "included",
            "contract_hash": "contract",
            "source_evidence_hash": standing["sha256"],
            "state": "healthy",
            "max_concurrency": 1,
            "updated_at": "2099-01-01T00:00:00+00:00",
        },
    )
    old_manifest, _ = m._json(m.HISTORICAL_MANIFEST, "historical")
    candidate_manifest = old_manifest["source_closure"]["candidate"]["manifest_sha256"]
    packet = _write(
        tmp_path / "renewed-packet.json",
        {
            "schema_version": 1,
            "kind": "grok_standing_authority_v6_append_only_renewal_packet",
            "state": "renewal_sealed_provider_free",
            "candidate_manifest": {
                "path": "candidate-manifest.json",
                "sha256": candidate_manifest,
            },
            "renewed_source": {
                "path": "renewed-standing.json",
                "sha256": standing["sha256"],
                "checked_at": "2099-01-01T00:00:00+00:00",
                "expires_at": "2099-01-02T00:00:00+00:00",
                "authority_at": "2098-12-31T00:00:00+00:00",
                "fresh_allowance_observation": False,
                "new_owner_statement": False,
            },
            "actions": {
                "activation_authority": False,
                "provider_contact_authority": False,
                "installed_source_mutated": False,
                "live_route_mutated": False,
                "live_gate_mutated": False,
                "enqueue": False,
                "dispatch": False,
                "provider_contact_count": 0,
                "request_1088_resend": False,
            },
            "scope": {
                "automatic_resend": False,
                "zero_charge_only": True,
                "paid_fallback": False,
            },
            "predecessor_packet": {},
            "files": [],
            "manifest_conditions": {},
            "remaining_gate": "fixture",
        },
    )
    route = {"model": "fixture-renewed", "reported_model": "fixture-renewed"}
    return {
        "historical_controller": {
            "path": str(m.HISTORICAL_CONTROLLER),
            "sha256": m.HISTORICAL_CONTROLLER_SHA256,
        },
        "historical_continuation": {
            "root": str(m.HISTORICAL_ROOT),
            "manifest_path": str(m.HISTORICAL_MANIFEST),
            "manifest_sha256": m.HISTORICAL_MANIFEST_SHA256,
        },
        "retained_prefix": {
            "path": str(m.RETAINED_PREFIX),
            "sha256": m.RETAINED_PREFIX_SHA256,
        },
        "route": {"name": "grok-renewed-fixture", "sha256": m._sha(m._canon(route))},
        "gate": gate,
        "standing_source": standing,
        "packet": packet,
    }


def _new_state(
    tmp_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[str]]:
    closure = _source_closure(tmp_path)
    old_manifest, _ = m._json(m.HISTORICAL_MANIFEST, "historical")
    prefix = m._prefix_bindings(closure["retained_prefix"], closure["historical_continuation"])
    old_ids = [
        {
            "request_id_hash": f"{index:064x}",
            "session_id_hash": f"{index + 10000:064x}",
            "observed_turns": 1,
        }
        for index in range(277)
    ]
    context_manifest = old_manifest
    schema = _write(tmp_path / "schema.json", {"type": "object"})
    row = {
        "pass_id": "p",
        "prompt": "prompt-338",
        "prompt_sha256": m._sha(b"prompt-338"),
        "schema_sha256": schema["sha256"],
        "question_ids": ["q-338"],
    }
    source = {
        "opaque_story_id": "story-338",
        "story_text": "story",
        "sha256": m._sha(b"story"),
    }
    calls: list[str] = []

    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"

        def _normalize_batch(self, output: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return output["verdicts"]

    class Base:
        pass

    class Broker:
        def __init__(self, _queue: Path) -> None:
            pass

        def run_grok_native_request(self, _route: str, _request: Any, **kwargs: Any) -> dict[str, Any]:
            kwargs["before_contact"]()
            calls.append("contact")
            return {
                "state": "completed",
                "result": {
                    "output": {"verdicts": [{"question_id": "q-338"}]},
                    "runtime": {
                        "request_id_hash": "f" * 64,
                        "session_id_hash": "e" * 64,
                        "observed_turns": 1,
                    },
                    "native_envelope_artifact": {"sha256": "c" * 64, "byte_length": 1},
                },
            }

    parent = SimpleNamespace(
        _request_payload=lambda *_args: ("prompt-338", Path(schema["path"]), ["q-338"]),
        _source_for_pass=lambda *_args: source,
    )
    context = SimpleNamespace(
        manifest=context_manifest,
        candidate=SimpleNamespace(Broker=Broker),
        parent=parent,
        base=Base(),
        runtime=SimpleNamespace(
            runner=Runner(),
            verify=lambda: None,
        ),
        plan_root=tmp_path,
        passes={"p": {}},
        requests={338: row},
    )
    manifest = {
        "schema_version": 1,
        "evidence_class": "dryad_grok_renewed_successor_v1",
        "source_epoch": m.SOURCE_EPOCH,
        "controller_sha256": m._sha(SOURCE.read_bytes()),
        "source_closure": closure,
        "source_closure_sha256": m._sha(m._canon(closure)),
        "pending_ordinals": m.PENDING,
        "operational_wave_cap": 1,
        "provider_calls_made": 0,
        "execution_authority": False,
    }
    root = tmp_path / "continuation"
    root.mkdir()
    manifest_raw = m._canon(manifest)
    (root / "grok-renewed-successor-manifest.json").write_bytes(manifest_raw)
    historical = {
        "manifest": old_manifest,
        "state": {"context": context},
        "prior_identities": old_ids,
        "replayed": set(range(280, 338)),
        "replay_identities": prefix["identities"],
    }
    state = {
        "manifest": manifest,
        "manifest_raw": manifest_raw,
        "historical": historical,
        "context": context,
        "prior_identities": [*old_ids, *prefix["identities"]],
        "source_epoch": m.SOURCE_EPOCH,
    }
    return (
        state,
        {"model": "fixture-renewed", "reported_model": "fixture-renewed"},
        root,
        calls,
    )


def _review_value(state: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    closure = state["manifest"]["source_closure"]
    gate, _ = m._json(Path(closure["gate"]["path"]), "gate")
    now = m.datetime.now(m.timezone.utc)
    return {
        "schema_version": 1,
        "decision": "approved_dryad_grok_renewed_successor_wave",
        "source_epoch": m.SOURCE_EPOCH,
        "controller_sha256": state["manifest"]["controller_sha256"],
        "manifest_sha256": m._sha(state["manifest_raw"]),
        "source_closure_sha256": state["manifest"]["source_closure_sha256"],
        "historical_manifest_sha256": closure["historical_continuation"]["manifest_sha256"],
        "retained_prefix_sha256": closure["retained_prefix"]["sha256"],
        "candidate_manifest_sha256": state["historical"]["manifest"]["source_closure"]["candidate"]["manifest_sha256"],
        "packet_sha256": closure["packet"]["sha256"],
        "standing_source_sha256": closure["standing_source"]["sha256"],
        "first_ordinal": 338,
        "operational_wave_cap": 1,
        "route_name": closure["route"]["name"],
        "route": dict(route),
        "route_sha256": m._sha(m._canon(dict(route))),
        "gate_evidence_path": closure["gate"]["path"],
        "gate_evidence_sha256": closure["gate"]["sha256"],
        "gate_sha256": closure["gate"]["sha256"],
        "gate_identity": {
            key: gate.get(key)
            for key in ("provider", "account_class", "contract_hash", "source_evidence_hash", "state")
        },
        "reviewed_at": (now - m.timedelta(seconds=1)).isoformat(),
        "expires_at": (now + m.timedelta(hours=1)).isoformat(),
    }


def test_create_binds_the_immutable_prefix_and_starts_at_338(tmp_path: Path) -> None:
    closure = _source_closure(tmp_path)
    result = m.create(continuation_root=tmp_path / "continuation", source_closure=closure)
    assert result["next_ordinal"] == 338 and result["provider_calls_made"] == 0
    manifest, raw = m._manifest(tmp_path / "continuation", result["manifest_sha256"])
    assert manifest["source_epoch"] == m.SOURCE_EPOCH
    assert manifest["source_closure"]["historical_continuation"]["manifest_sha256"] == m.HISTORICAL_MANIFEST_SHA256
    assert m._sha(raw) == result["manifest_sha256"]


def test_dispatch_replay_and_intent_boundary_are_append_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, route, root, calls = _new_state(tmp_path)
    review = _review_value(state, route)
    monkeypatch.setattr(m, "verify", lambda **_kwargs: state)
    monkeypatch.setattr(m, "_review", lambda *_args: review)
    monkeypatch.setattr(m, "_historical_state", lambda _closure: state["historical"])
    def semantic(**kwargs: Any) -> tuple[dict[str, Any], list[dict[str, Any]], Mapping[str, Any]]:
        terminal = kwargs["terminal"]
        result = terminal["candidate_result"]
        assert terminal["state"] == "completed"
        assert isinstance(result["native_envelope_artifact"], Mapping)
        assert terminal["native_identity"]["observed_turns"] == 1
        return (
            terminal["native_identity"],
            terminal["verdicts"],
            result["native_envelope_artifact"],
        )
    monkeypatch.setattr(m, "_semantic_replay_terminal", semantic)
    first = m.dispatch(
        continuation_root=root,
        expected_manifest_sha256="m" * 64,
        start_ordinal=338,
        wave_size=1,
        arming_review_path=tmp_path / "review.json",
        expected_arming_review_sha256="r" * 64,
    )
    assert first["state"] == "completed_pending_replay" and calls == ["contact"]
    replayed = m.replay(
        continuation_root=root,
        expected_manifest_sha256="m" * 64,
        start_ordinal=338,
        wave_size=1,
    )
    assert replayed["ordinals"] == [338] and m._next(m._records(root), {338}) == 339
    with pytest.raises(ValueError, match="exact next|prior cell"):
        m.dispatch(
            continuation_root=root,
            expected_manifest_sha256="m" * 64,
            start_ordinal=338,
            wave_size=1,
            arming_review_path=tmp_path / "review.json",
            expected_arming_review_sha256="r" * 64,
        )
    assert calls == ["contact"]


def test_dispatch_rejects_consumed_337_before_contact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, route, root, calls = _new_state(tmp_path)
    review = _review_value(state, route)
    monkeypatch.setattr(m, "verify", lambda **_kwargs: state)
    monkeypatch.setattr(m, "_review", lambda *_args: review)
    with pytest.raises(ValueError, match="geometry"):
        m.dispatch(
            continuation_root=root,
            expected_manifest_sha256="m" * 64,
            start_ordinal=337,
            wave_size=1,
            arming_review_path=tmp_path / "review.json",
            expected_arming_review_sha256="r" * 64,
        )
    assert calls == []


def test_prefix_identity_collision_is_rejected() -> None:
    first = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64, "observed_turns": 1}
    duplicate_request = {**first, "session_id_hash": "c" * 64}
    duplicate_session = {**first, "request_id_hash": "d" * 64}
    assert not m._identities_unique([first, duplicate_request])
    assert not m._identities_unique([first, duplicate_session])


def test_review_route_hash_must_bind_the_fresh_epoch(
    tmp_path: Path,
) -> None:
    state, route, _root, _calls = _new_state(tmp_path)
    review = _review_value(state, route)
    path = tmp_path / "review.json"
    raw = m._canon(review)
    path.write_bytes(raw)
    assert m._review(path, m._sha(raw), state, 338)["route"] == route
    review["route"] = {"model": "drifted", "reported_model": "drifted"}
    drifted = m._canon(review)
    path.write_bytes(drifted)
    with pytest.raises(ValueError, match="review differs"):
        m._review(path, m._sha(drifted), state, 338)
