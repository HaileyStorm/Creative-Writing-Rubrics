from __future__ import annotations

import hashlib
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from shutil import copytree, ignore_patterns
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_standing_v6_serialized_continuation.py"
CANDIDATE_SOURCE = Path(r"C:\Users\Haile\Documents\Codex\2026-08-12\universal-harness\work\grok-standing-authority-v6-candidate\isolated\candidate-v6-standing")


def load() -> Any:
    spec = importlib.util.spec_from_file_location("standing_v6_serialized_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def candidate_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "candidate"
    copytree(CANDIDATE_SOURCE, destination, ignore=ignore_patterns("__pycache__"))
    return destination


def test_public_contract_and_pending_prefix_are_preserved() -> None:
    value = load()
    assert len(value.PENDING) == 2039 and value.PENDING[0] == 262 and value.PENDING[-1] == 4738
    assert 70 not in value.PENDING and 254 not in value.PENDING
    assert all(callable(getattr(value, name)) for name in (
        "prepare_standing_v6_continuation", "verify_standing_v6_continuation",
        "dispatch_standing_v6_wave", "replay_standing_v6_wave",
        "verify_standing_v6_replay_chain",
    ))


def test_cold_real_candidate_ten_thread_load_is_single_completed_code_module(tmp_path: Path) -> None:
    value = load()
    root = candidate_copy(tmp_path)
    with ThreadPoolExecutor(max_workers=10) as executor:
        loaded = list(executor.map(lambda _: value._candidate(root, value.CANDIDATE_MANIFEST_SHA)[0], range(10)))
    assert len({id(module) for module in loaded}) == 1
    assert loaded[0].__package__.startswith("_standing_v6_candidate_")
    assert not list(root.rglob("__pycache__"))


def test_cached_candidate_code_still_rejects_inventory_drift(tmp_path: Path) -> None:
    value = load()
    root = candidate_copy(tmp_path)
    module, _manifest = value._candidate(root, value.CANDIDATE_MANIFEST_SHA)
    (root / "model_work_queue" / "broker.py").write_bytes((root / "model_work_queue" / "broker.py").read_bytes() + b"\n# test drift\n")
    with pytest.raises(ValueError, match="candidate root drift"):
        value._candidate(root, value.CANDIDATE_MANIFEST_SHA)
    assert module.Broker is not None


def dispatch_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, callback_failure: bool = False) -> tuple[Any, Path, list[str]]:
    value = load()
    root = tmp_path / "continuation"
    root.mkdir()
    queue = tmp_path / "queue"
    manifest = {
        "controller_sha256": sha(SOURCE.read_bytes()),
        "candidate": {"root": str(tmp_path), "manifest_sha256": "c" * 64},
        "packet": {"path": str(tmp_path / "packet"), "sha256": "p" * 64},
        "standing_source": {"path": str(tmp_path / "standing"), "sha256": "s" * 64},
        "queue": {"path": str(queue), "root_hash": "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a", "path_sha256": sha(str(queue.resolve()).encode())},
        "pending_ordinals": value.PENDING,
    }
    raw = canon(manifest)
    (root / "standing-v6-continuation-manifest.json").write_bytes(raw)
    (tmp_path / "schema.json").write_bytes(canon({"type": "object"}))
    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"
        def _normalize_batch(self, output: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return output["verdicts"]
    class Parent:
        def _runtime_from_epoch(self, _epoch: Any) -> Any: return SimpleNamespace(runner=Runner())
        def _plan(self, *_args: Any) -> tuple[dict[str, Any], bytes]: return {}, b""
        def _pass_index(self, *_args: Any) -> dict[str, Any]: return {"pass": {}}
        def _request_payload(self, *_args: Any) -> tuple[str, Path, list[str]]: return "prompt", tmp_path / "schema.json", ["q"]
        def _source_for_pass(self, *_args: Any) -> dict[str, str]: return {"sha256": "x", "opaque_story_id": "fixture", "story_text": "story"}
    requests = {262: {"ordinal": 262, "pass_id": "pass", "prompt_sha256": "a", "schema_sha256": "b", "question_ids": ["q"]}, 263: {"ordinal": 263, "pass_id": "pass", "prompt_sha256": "a", "schema_sha256": "b", "question_ids": ["q"]}}
    route = {"model": "fixture-model", "reported_model": "fixture-build"}
    review = {"queue_root": str(queue), "route_name": "route", "route_sha256": sha(canon(route)), "gate_sha256": "g" * 64, "route": route, "gate_identity": {}}
    calls: list[str] = []
    artifacts: dict[str, bytes] = {}
    class Broker:
        def __init__(self, _root: Path) -> None: pass
        def run_grok_native_request(self, _name: str, _request: Any, *, before_contact: Any, **_kwargs: Any) -> dict[str, Any]:
            try:
                before_contact()
            except ValueError:
                return {"state": "definitely_not_contacted", "result": None, "failure": {"code": "before_contact_failed"}}
            ordinal = 262 if not calls else 263
            calls.append(str(ordinal))
            identity = {"request_id_hash": str(ordinal)[-1] * 64, "session_id_hash": str(ordinal)[-1] * 64, "observed_turns": 1}
            output = {"verdicts": [{"question_id": "q"}]}
            envelope = canon({"output": output, "identity": identity})
            digest = sha(envelope)
            artifacts[digest] = envelope
            return {"state": "completed", "result": {"output": output, "runtime": identity, "native_envelope_artifact": {"schema_version": 1, "sha256": digest, "byte_length": len(envelope)}}}
        def read_grok_native_envelope(self, descriptor: dict[str, Any]) -> bytes: return artifacts[descriptor["sha256"]]
        def _parse_grok_exec_envelope(self, raw: bytes, *_args: Any, **_kwargs: Any) -> Any: return SimpleNamespace(state="completed", result=json.loads(raw)["result"])
    adapter = SimpleNamespace(_parse_grok_envelope=lambda raw, **_kwargs: (json.loads(raw)["output"], json.loads(raw)["identity"], {}))
    candidate = SimpleNamespace(Broker=Broker, __package__="fixture_candidate")
    monkeypatch.setattr(value, "_manifest", lambda *_args: (manifest, raw))
    monkeypatch.setattr(value, "_candidate", lambda *_args: (candidate, {}))
    monkeypatch.setattr(value, "_packet", lambda *_args: {})
    monkeypatch.setattr(value, "_standing", lambda *_args: {})
    review_calls = 0
    def fixture_review(*_args: Any) -> dict[str, Any]:
        nonlocal review_calls
        review_calls += 1
        if callback_failure and review_calls == 2: raise ValueError("private callback detail")
        return review
    monkeypatch.setattr(value, "_review", fixture_review)
    monkeypatch.setattr(value, "_prefix_context", lambda *_args: (object(), Parent(), tmp_path, requests, {"plan_sha256": "p"}, []))
    monkeypatch.setattr(value.importlib, "import_module", lambda _name: adapter)
    return value, root, calls


def test_synthetic_dispatch_semantic_replay_and_no_resend_accounting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = dispatch_fixture(tmp_path, monkeypatch)
    dispatched = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert dispatched["state"] == "completed_pending_replay" and dispatched["provider_calls_made"] == 1
    with pytest.raises(ValueError, match="prior cell incomplete"):
        value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    assert calls == ["262"]
    replay = value.replay_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1)
    assert replay["provider_calls_made"] == 0 and replay["native_identities"][0]["observed_turns"] == 1
    verified = value.verify_standing_v6_replay_chain(continuation_root=root, expected_manifest_sha256=sha((root / "standing-v6-continuation-manifest.json").read_bytes()), expected_controller_sha256=sha(SOURCE.read_bytes()))
    assert verified["candidate_native_replay_ordinals"] == [262] and verified["provider_calls_made"] == 0


def test_callback_error_provenance_is_bounded_before_broker_collapses_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, root, calls = dispatch_fixture(tmp_path, monkeypatch, callback_failure=True)
    outcome = value.dispatch_standing_v6_wave(continuation_root=root, start_ordinal=262, wave_size=1, arming_review_path=tmp_path / "review", expected_arming_review_sha256="z" * 64)
    terminal = json.loads((root / "attempts" / "request-0262" / "terminal.json").read_bytes())
    provenance = terminal["before_contact_error"]
    assert outcome["state"] == "stopped_no_retry" and calls == []
    assert set(provenance) == {"source", "function", "line", "error_type"}
    assert provenance["error_type"] == "ValueError" and provenance["line"] > 0
    assert "private callback detail" not in json.dumps(terminal)
