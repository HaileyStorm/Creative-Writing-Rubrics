from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_selected_local_continuation.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("local_continuation_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def test_projection_caps_only_the_schema_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    quote = "x" * 579
    answer = {"verdicts": [{"question_id": str(index), "evidence": [{"exact_quote": "other"}]} for index in range(8)]}
    answer["verdicts"][3]["evidence"][0]["exact_quote"] = quote
    projected = json.loads(canon(answer)); projected["verdicts"][3]["evidence"][0]["exact_quote"] = quote[:500]
    monkeypatch.setattr(value, "SOURCE_STORY_SHA", sha(quote.encode()))
    monkeypatch.setattr(value, "PROJECTED_SHA", sha(canon(projected)))
    assert value._project(answer, {}) == projected
    answer["verdicts"][4]["question_id"] = "drift"
    with pytest.raises(ValueError, match="projected"):
        value._project(answer, {})


def test_proposal_adoption_and_grounding_reject_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    bindings: dict[str, str] = {}
    for index in range(11):
        path = tmp_path / f"source-{index}.txt"; raw = f"source-{index}".encode(); path.write_bytes(raw); bindings[str(path)] = sha(raw)
    proposal = {
        "all_other_values_unchanged": True, "attestation_time_basis": "fixture", "authorizes_new_attempt": False,
        "changes": [{"operation": "retain_first_500_characters", "original_characters": 579, "original_quote_is_exact_full_source": True, "path": "verdicts[3].evidence[0].exact_quote", "projected_characters": 500}],
        "exact_question_id_order_preserved": True, "kind": "dryad254_local_session_quote_projection_proposal", "local_summary_request_id_sha256": "a" * 64,
        "native_cli_envelope_binding": False, "ordinal": 254, "ordinary_native_admission": False, "original_message_sha256": "b" * 64,
        "original_outcome_preserved": True, "process_exit_code": None, "projected_message_sha256": "c" * 64, "provider_calls_made": 0,
        "provider_identity_attested": False, "result_promotion_authority": False, "retained_message_matches_update": True, "schema_sha256": "d" * 64,
        "schema_version": 1, "session_attestation_sha256": "e" * 64, "session_id_sha256": "f" * 64, "source_artifact_sha256": "g" * 64,
        "source_bindings": bindings, "status": "fixture",
    }
    proposal_path = tmp_path / "proposal.json"; proposal_path.write_bytes(canon(proposal)); proposal_hash = sha(proposal_path.read_bytes())
    monkeypatch.setattr(value, "PROPOSAL_SHA", proposal_hash); monkeypatch.setattr(value, "ORIGINAL_SHA", "b" * 64); monkeypatch.setattr(value, "PROJECTED_SHA", "c" * 64); monkeypatch.setattr(value, "SOURCE_STORY_SHA", "g" * 64)
    assert value._proposal(proposal_path, proposal_hash) == proposal
    (tmp_path / "source-4.txt").write_bytes(b"drift")
    with pytest.raises(ValueError, match="proposal source"):
        value._proposal(proposal_path, proposal_hash)


class _Runner:
    EVIDENCE_NORMALIZATION_POLICY = "fixture"

    def _validate_grok_transport_evidence(self, *_args: Any) -> None:
        return None

    def _parse_model_json(self, content: str) -> dict[str, Any]:
        return json.loads(content)

    def _normalize_batch(self, value: Mapping[str, Any], *, expected_ids: list[str], **_kwargs: Any) -> list[dict[str, Any]]:
        assert [item["question_id"] for item in value["verdicts"]] == expected_ids
        return [dict(item) for item in value["verdicts"]]


class _Transport:
    def __init__(self, gate: threading.Barrier | None = None, fail: int | None = None, state: threading.local | None = None, mutate: Callable[[], None] | None = None) -> None:
        self.gate, self.fail, self.state, self.mutate = gate, fail, state, mutate

    def bind_grok_broker_transport(self, *, before_contact: Any, **_kwargs: Any) -> Any:
        def call(context: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
            if self.state is not None:
                self.state.ordinal = context["ordinal"]
            if self.mutate is not None:
                self.mutate()
            before_contact(context)
            if self.gate:
                self.gate.wait(timeout=5)
            if context["ordinal"] == self.fail:
                raise RuntimeError("fixture failure")
            ordinal = context["ordinal"]
            return json.dumps({"verdicts": [{"question_id": f"q{ordinal}", "verdict": "YES", "evidence": [], "confidence": 1, "note": "ok"}]}), {"request_id_sha256": sha(f"r{ordinal}".encode()), "session_id_sha256": sha(f"s{ordinal}".encode())}
        return call


class _Runtime:
    def __init__(self, transport: _Transport) -> None:
        self.runner, self.transport = _Runner(), transport

    def verify(self) -> None:
        return None


class _Parent:
    def __init__(self, transport: _Transport) -> None:
        self.transport = transport

    def _attempt_path(self, root: Path, ordinal: int, name: str) -> Path:
        return root / "attempts" / f"request-{ordinal:04d}" / name

    def _load_epoch(self, *_args: Any) -> tuple[dict[str, Any], bytes]:
        raise AssertionError("fixture should patch this seam")

    def _wave_path(self, root: Path, start: int, size: int, suffix: str) -> Path:
        return root / "waves" / f"wave-{start:04d}-slots-{size:02d}-{suffix}.json"

    def _prepare_wave_cell(self, *, root: Path, ordinal: int, slot_index: int, **_kwargs: Any) -> dict[str, Any]:
        context = {"ordinal": ordinal, "run": {"run_id": f"run-{ordinal}"}}
        start = {"context_sha256": sha(canon(context)), "ordinal": ordinal}
        return {"runtime": _Runtime(self.transport), "row": {"ordinal": ordinal, "pass_id": "fixture"}, "passed": {"pass_id": "fixture"}, "source": {"sha256": "x", "opaque_story_id": "fixture", "story_text": "fixture"}, "context": context, "start": start, "start_path": self._attempt_path(root, ordinal, "attempt-start.json"), "run_root": root / "runs" / str(ordinal), "question_ids": [f"q{ordinal}"]}

    def _broker(self, *_args: Any) -> object:
        return object()

    def _source_for_pass(self, _plan: Path, passed: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"sha256": "x", "opaque_story_id": "fixture", "story_text": "fixture"}

    def _terminal(self, *, root: Path, ordinal: int, status: str, metadata: Mapping[str, Any] | None, **kwargs: Any) -> None:
        path = self._attempt_path(root, ordinal, "terminal.json"); path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ordinal": ordinal, "status": status, "provider_metadata": dict(metadata or {})}
        if "verdicts" in kwargs and kwargs["verdicts"] is not None: record["verdicts"] = kwargs["verdicts"]
        path.write_bytes(canon(record))

    def _wave_settlement(self, root: Path, *, wave_ordinals: list[int], **_kwargs: Any) -> dict[str, Any]:
        rows = []
        for ordinal in wave_ordinals:
            path = self._attempt_path(root, ordinal, "terminal.json"); terminal = json.loads(path.read_bytes())
            row = {"ordinal": ordinal, "status": terminal["status"], "terminal_sha256": sha(path.read_bytes())}
            if terminal["status"] == "completed": row["native_identity"] = {"request_id_hash": terminal["provider_metadata"]["request_id_sha256"], "session_id_hash": terminal["provider_metadata"]["session_id_sha256"]}
            rows.append(row)
        start = self._wave_path(root, wave_ordinals[0], len(wave_ordinals), "start")
        return {"ordinals": wave_ordinals, "rows": rows, "wave_start_sha256": sha(start.read_bytes())}

    def _plan(self, *_args: Any) -> tuple[dict[str, Any], bytes]:
        return {}, b"plan"

    def _runtime_from_epoch(self, *_args: Any) -> object:
        return object()

    def _pass_index(self, *_args: Any) -> dict[str, dict[str, Any]]:
        return {"fixture": {}}

    def _replay_suffix_terminal(self, *, root: Path, row: Mapping[str, Any], **_kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        terminal = json.loads(self._attempt_path(root, row["ordinal"], "terminal.json").read_bytes())
        metadata = terminal["provider_metadata"]
        return terminal["verdicts"], {"request_id_hash": metadata["request_id_sha256"], "session_id_hash": metadata["session_id_sha256"]}


def _dispatch_fixture(value: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: _Transport) -> tuple[Path, dict[str, Any]]:
    root, queue = tmp_path / "continuation", tmp_path / "queue"; root.mkdir(parents=True); queue.mkdir()
    protected = [{"request_id_hash": sha(f"protected-request-{index}".encode()), "session_id_hash": sha(f"protected-session-{index}".encode())} for index in range(259)]
    protected_raw = canon(protected); ids_path = tmp_path / "ids.json"; ids_path.write_bytes(protected_raw)
    manifest = {"controller_sha256": sha(SOURCE.read_bytes()), "inner_epoch": {"path": str(tmp_path / "epoch.json"), "sha256": "e" * 64}, "adoption": {"path": str(tmp_path / "adoption"), "sha256": "a" * 64}, "proposal": {"path": str(tmp_path / "proposal"), "sha256": "p" * 64}, "independent_review": {"path": str(tmp_path / "review"), "sha256": "i" * 64}, "standing_authority": {"path": str(tmp_path / "standing"), "sha256": "s" * 64}, "protected_native_identities": {"path": str(ids_path), "count": 259, "sha256": sha(protected_raw), "commitment_sha256": sha(protected_raw)}, "successor_root": str(tmp_path), "pending_ordinals": value.PENDING, "ownership": {"protected_native_identity_count": 259, "local_recovery_ordinals": [70, 254], "never_contact_ordinals": [254]}}
    raw = canon(manifest); (root / "local-continuation-manifest.json").write_bytes(raw)
    parent = _Parent(transport)
    epoch = {"execution_mode": "fixture", "max_concurrency": 10, "plan_sha256": "l" * 64, "runtime_manifest": {"sha256": "r" * 64}, "runtime_package": {"manifest_sha256": "p" * 64}, "v3_source": {"sha256": "v" * 64}, "selected_schedule": {"sha256": "s" * 64}}
    requests = {ordinal: {"ordinal": ordinal, "pass_id": "fixture"} for ordinal in value.PENDING[:10]}
    monkeypatch.setattr(value, "_manifest", lambda _root, *_args: (manifest, raw)); monkeypatch.setattr(value, "_source_guard", lambda _manifest: (object(), parent, {}, b"epoch", tmp_path, requests, {})); monkeypatch.setattr(value, "_execution_review", lambda *_args, **_kwargs: {"parent_review_path": str(tmp_path / "parent-review"), "parent_review_sha256": "h" * 64, "parent_review": {"route": {}}, "route_sha256": "r" * 64, "gate_sha256": "g" * 64}); monkeypatch.setattr(parent, "_load_epoch", lambda *_args: (epoch, b"epoch"))
    monkeypatch.setattr(value, "_proposal", lambda *_args: {}); monkeypatch.setattr(value, "_adoption", lambda *_args: {}); monkeypatch.setattr(value, "_review", lambda *_args: {}); monkeypatch.setattr(value, "_standing", lambda *_args: {})
    return root, {"queue": queue, "parent": parent, "protected": protected, "ids_path": ids_path}


def test_first_native_wave_is_262_ten_concurrent_and_not_resend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); barrier = threading.Barrier(10); root, fixture = _dispatch_fixture(value, tmp_path, monkeypatch, _Transport(barrier))
    result = value.dispatch_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=10, execution_review_path=tmp_path / "review", expected_execution_review_sha256="z" * 64, queue_root=fixture["queue"])
    assert result["ordinals"] == list(range(262, 272)) and result["provider_calls_made"] == 10 and 254 not in result["contact_started_ordinals"]
    with pytest.raises(ValueError, match="unreplayed"):
        value.dispatch_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=10, execution_review_path=tmp_path / "review", expected_execution_review_sha256="z" * 64, queue_root=fixture["queue"])


def test_precontact_failure_stops_waiting_peers_before_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); state = threading.local(); peers_waiting, release = threading.Event(), threading.Event()
    root, fixture = _dispatch_fixture(value, tmp_path, monkeypatch, _Transport(state=state))
    def proposal(*_args: Any) -> dict[str, Any]:
        if getattr(state, "ordinal", None) == 262:
            assert peers_waiting.wait(5)
            raise ValueError("fixture precontact failure")
        peers_waiting.set(); assert release.wait(5)
        return {}
    monkeypatch.setattr(value, "_proposal", proposal)
    outcome: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: outcome.setdefault("result", value.dispatch_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=3, execution_review_path=tmp_path / "review", expected_execution_review_sha256="z" * 64, queue_root=fixture["queue"])))
    worker.start(); assert peers_waiting.wait(5)
    terminal = root / "attempts" / "request-0262" / "terminal.json"
    for _ in range(100):
        if terminal.is_file(): break
        time.sleep(0.01)
    assert terminal.is_file(); release.set(); worker.join(10)
    assert not worker.is_alive() and outcome["result"]["provider_calls_made"] == 0
    assert outcome["result"]["admitted_ordinals"] == [] and outcome["result"]["uncontacted_ordinals"] == [262, 263, 264]


def test_native_identity_collision_is_rejected() -> None:
    value = load(); identity = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}
    with pytest.raises(ValueError, match="collision"):
        value._identity([identity, identity])


def test_protected_identity_commitment_blocks_preflight_and_callback_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root, fixture = _dispatch_fixture(value, tmp_path, monkeypatch, _Transport())
    fixture["ids_path"].write_bytes(b"[]")
    with pytest.raises(ValueError, match="protected native identities changed"):
        value.dispatch_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=1, execution_review_path=tmp_path / "review", expected_execution_review_sha256="z" * 64, queue_root=fixture["queue"])

    value = load(); transport = _Transport(); root, fixture = _dispatch_fixture(value, tmp_path / "callback", monkeypatch, transport)
    transport.mutate = lambda: fixture["ids_path"].write_bytes(b"[]")
    result = value.dispatch_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=1, execution_review_path=tmp_path / "review", expected_execution_review_sha256="z" * 64, queue_root=fixture["queue"])
    assert result["provider_calls_made"] == 0 and result["admitted_ordinals"] == [] and result["uncontacted_ordinals"] == [262]


def test_replay_uses_frozen_terminal_seam_and_never_contacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); root, fixture = _dispatch_fixture(value, tmp_path, monkeypatch, _Transport(threading.Barrier(1)))
    value.dispatch_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=1, execution_review_path=tmp_path / "review", expected_execution_review_sha256="z" * 64, queue_root=fixture["queue"])
    replay = value.replay_untouched_wave(continuation_root=root, start_ordinal=262, wave_size=1, approved_v5_routes={}, protected_native_identities=fixture["protected"])
    assert replay["ordinals"] == [262] and replay["provider_calls_made"] == 0 and len(replay["native_identities"]) == 1
