from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import time
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_grok_selected_successor.py"
PRIOR_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-grok88-recovery-20260910-r1")
PRIOR_MANIFEST_SHA = "4318e41151a3939a56d5bdec52fa8a6445f93d6ed00aaf80148c4edc7fc06782"
PARTIAL_SHA = "55b0cd67858636af1836889518641c1c77294716dc6f3711ce24e2103cbdd0b8"
FAILED = (203, 205, 211)


def load() -> Any:
    spec = importlib.util.spec_from_file_location("successor_test", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def test_actual_partial202_contract_and_frozen_api() -> None:
    value = load()
    path = PRIOR_ROOT / "partial-wave202-native-replay.json"
    assert sha(path.read_bytes()) == PARTIAL_SHA
    partial = value._partial(path, PARTIAL_SHA)
    assert partial["failed_ordinals"] == [203, 205, 211]
    assert len(partial["all_protected_native_identities"]) == 207
    assert sha(value.PARENT.read_bytes()) == value.PARENT_SHA
    assert sha(value.PRIOR.read_bytes()) == value.PRIOR_SHA


def test_prepare_binds_full_predecessor_inventory_without_provider_contact(tmp_path: Path) -> None:
    value = load()
    result = value.prepare_successor(
        successor_root=tmp_path / "next",
        prior_root=PRIOR_ROOT,
        expected_prior_manifest_sha256=PRIOR_MANIFEST_SHA,
        partial_202_path=PRIOR_ROOT / "partial-wave202-native-replay.json",
        expected_partial_202_sha256=PARTIAL_SHA,
    )
    manifest = json.loads((tmp_path / "next" / "successor-manifest.json").read_bytes())
    assert result["provider_calls_made"] == 0
    assert manifest["pending_ordinals"][:4] == [203, 205, 211, 212]
    assert manifest["predecessor_root_ownership"]["partial_peer_ordinals"] == [202, 204, 206, 207, 208, 209, 210]
    assert "attempts/request-0203/terminal.json" in manifest["prior_inventory"]["files"]
    assert manifest["protected_native_identities"]["count"] == 207
    parent = value._load(value.PARENT, value.PARENT_SHA, "parent")
    prior = value._load(value.PRIOR, value.PRIOR_SHA, "prior")
    partial = value._partial(PRIOR_ROOT / "partial-wave202-native-replay.json", PARTIAL_SHA)
    (tmp_path / "next" / "suffix-epoch.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="copied epoch"):
        value._source_guard(parent, prior, manifest, partial)


def test_partial_hash_is_an_input_not_a_source_edit_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    copied = tmp_path / "partial.json"
    copied.write_bytes((PRIOR_ROOT / "partial-wave202-native-replay.json").read_bytes())
    assert value._partial(copied, sha(copied.read_bytes()))["failed_ordinals"] == list(FAILED)


def test_adoption_is_exactly_the_three_failed_cells(tmp_path: Path) -> None:
    value = load()
    manifest = {"failed_attempts": [{"ordinal": 203}, {"ordinal": 205}, {"ordinal": 211}]}
    manifest["predecessor_root_ownership"] = {"successor_replacements": [203, 205, 211]}
    adoption = {"schema_version": 1, "decision": "approved_exactly_one_selected_successor_replacements", "proposal_sha256": sha(value._canon(manifest)), "replacement_ordinals": [203, 205, 211], "maximum_new_attempts_per_ordinal": 1, "failed_attempts": manifest["failed_attempts"], "execution_authority": True}
    path = tmp_path / "adoption.json"; path.write_bytes(value._canon(adoption))
    assert value._adoption(path, sha(path.read_bytes()), manifest) == adoption
    adoption["replacement_ordinals"] = [203]
    path.write_bytes(value._canon(adoption))
    with pytest.raises(ValueError, match="adoption"):
        value._adoption(path, sha(path.read_bytes()), manifest)


def test_expired_controller_review_blocks_before_any_transport(tmp_path: Path) -> None:
    value = load()
    class Parent:
        def _review(self, *_args: Any, **_kwargs: Any) -> dict[str, str]:
            return {"route_sha256": "a" * 64, "gate_sha256": "b" * 64}
    manifest = {"controller_sha256": "c" * 64, "prior_controller_sha256": value.PRIOR_SHA, "prior_manifest_sha256": "d" * 64, "inner_epoch": {"sha256": "e" * 64}, "partial_202": {"sha256": "f" * 64}, "protected_native_identities": {"sha256": "1" * 64, "commitment_sha256": "2" * 64}}
    now = datetime.now(timezone.utc)
    review = {"schema_version": 1, "decision": "approved_dryad_grok_selected_successor_controller", "controller_sha256": manifest["controller_sha256"], "parent_sha256": value.PARENT_SHA, "prior_controller_sha256": value.PRIOR_SHA, "successor_manifest_sha256": sha(value._canon(manifest)), "prior_manifest_sha256": manifest["prior_manifest_sha256"], "inner_epoch_sha256": manifest["inner_epoch"]["sha256"], "partial_202_sha256": manifest["partial_202"]["sha256"], "protected_identity_file_sha256": manifest["protected_native_identities"]["sha256"], "protected_identity_commitment_sha256": manifest["protected_native_identities"]["commitment_sha256"], "adoption_sha256": "3" * 64, "parent_review_path": str(tmp_path / "parent.json"), "parent_review_sha256": "4" * 64, "route_sha256": "a" * 64, "gate_sha256": "b" * 64, "reviewed_at": (now - timedelta(minutes=20)).isoformat(), "expires_at": (now - timedelta(minutes=10)).isoformat()}
    path = tmp_path / "review.json"; path.write_bytes(value._canon(review))
    with pytest.raises(ValueError, match="not fresh"):
        value._controller_review(path, sha(path.read_bytes()), parent=Parent(), manifest=manifest, manifest_raw=value._canon(manifest), adoption_sha256="3" * 64, epoch={}, live=True)


def test_duplicate_native_identity_is_rejected() -> None:
    value = load()
    identity = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}
    with pytest.raises(ValueError, match="collision"):
        value._identity([identity, identity])


def test_prior_chain_accepts_a_reconciled_successor_as_next_predecessor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    source, protected = tmp_path / "earlier-successor", tmp_path / "identities.json"
    source.mkdir(); (source / "successor-manifest.json").write_bytes(b"fixture"); protected.write_bytes(b"[]")
    manifest = {"controller_sha256": sha(SOURCE.read_bytes()), "inner_epoch": {"sha256": "a" * 64}, "pending_ordinals": [5], "protected_native_identities": {"path": str(protected)}}
    raw = value._canon(manifest)
    partial = {"completed_ordinals": [6], "failed_ordinals": [7], "all_protected_native_identities": []}
    class Parent:
        def _load_epoch(self, *_args: Any) -> tuple[dict[str, Any], bytes]: return {}, b"epoch"
        def _epoch_integrity(self, *_args: Any) -> tuple[Path, Path, Path, dict[int, Any]]: return tmp_path, tmp_path, tmp_path, {}
    monkeypatch.setattr(value, "_manifest", lambda _root: (manifest, raw))
    monkeypatch.setattr(value, "_validated_replays", lambda *_args: ({5}, []))
    _manifest, actual_raw, *_rest = value._prior_chain(Parent(), None, source, sha(raw), partial)
    assert actual_raw == raw


def test_replacement_dispatch_uses_parent_transport_once_per_failed_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    root, protected, queue = tmp_path / "successor", tmp_path / "protected.json", tmp_path / "queue"
    root.mkdir(); queue.mkdir(); protected.write_bytes(b"[]")
    suffix = list(range(212, 222))
    manifest = {"controller_sha256": sha(SOURCE.read_bytes()), "parent_sha256": value.PARENT_SHA, "prior_controller_sha256": value.PRIOR_SHA, "partial_202": {"path": str(tmp_path / "partial.json"), "sha256": "a" * 64}, "inner_epoch": {"sha256": "b" * 64}, "protected_native_identities": {"path": str(protected), "sha256": sha(b"[]")}, "pending_ordinals": [203, 205, 211, *suffix], "predecessor_root_ownership": {"successor_replacements": [203, 205, 211], "successor_untouched_start": 212}}
    raw = value._canon(manifest)
    (root / "successor-manifest.json").write_bytes(raw)
    barrier, active_lock = threading.Barrier(3), threading.Lock()
    active = 0; maximum_active = 0
    failed_transport_ordinals: set[int] = set()
    gate_local = threading.local()
    first_failed = threading.Event()
    class Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"
        def _validate_grok_transport_evidence(self, *_args: Any) -> None: pass
        def _parse_model_json(self, _content: str) -> dict[str, Any]: return {}
        def _normalize_batch(self, *_args: Any, **_kwargs: Any) -> list[dict[str, str]]: return [{"criterion_id": "fixture"}]
    class Transport:
        def bind_grok_broker_transport(self, *, before_contact: Any, **_kwargs: Any) -> Any:
            def call(context: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
                nonlocal active, maximum_active
                ordinal = context["ordinal"]; gate_local.ordinal = ordinal; before_contact(context)
                with active_lock:
                    active += 1; maximum_active = max(maximum_active, active)
                barrier.wait(timeout=5)
                with active_lock:
                    active -= 1
                if ordinal in failed_transport_ordinals:
                    first_failed.set()
                    raise RuntimeError("fixture transport failure")
                return "{}", {"request_id_sha256": sha(f"r{ordinal}".encode()), "session_id_sha256": sha(f"s{ordinal}".encode())}
            return call
    class Runtime:
        runner = Runner(); transport = Transport()
        def verify(self) -> None: pass
    class Parent:
        def _attempt_path(self, directory: Path, ordinal: int, name: str) -> Path: return directory / "attempts" / f"request-{ordinal:04d}" / name
        def _prepare_wave_cell(self, *, root: Path, ordinal: int, slot_index: int, **_kwargs: Any) -> dict[str, Any]:
            source = {"sha256": sha(f"source{ordinal}".encode()), "opaque_story_id": "fixture", "story_text": "fixture"}; context = {"ordinal": ordinal, "run": {"run_id": f"run-{ordinal}"}}
            start = {"context_sha256": sha(value._canon(context))}; path = self._attempt_path(root, ordinal, "attempt-start.json")
            return {"runtime": Runtime(), "row": {"ordinal": ordinal, "pass_id": str(ordinal)}, "passed": source, "source": source, "context": context, "start": start, "start_path": path, "run_root": root / "runs" / str(ordinal), "question_ids": ["fixture"]}
        def _broker(self, *_args: Any) -> object: return object()
        def _source_for_pass(self, _plan: Path, passed: dict[str, str]) -> dict[str, str]: return passed
        def _terminal(self, *, root: Path, ordinal: int, status: str, metadata: Mapping[str, Any] | None, **_kwargs: Any) -> None:
            path = self._attempt_path(root, ordinal, "terminal.json"); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value._canon({"status": status, "provider_metadata": dict(metadata or {})}))
        def _wave_path(self, directory: Path, start: int, size: int, suffix: str) -> Path: return directory / "waves" / f"wave-{start:04d}-slots-{size:02d}-{suffix}.json"
        def _wave_settlement(self, root: Path, *, wave_ordinals: list[int], **_kwargs: Any) -> dict[str, Any]:
            rows = []
            for ordinal in wave_ordinals:
                terminal = self._attempt_path(root, ordinal, "terminal.json"); data = json.loads(terminal.read_bytes()); metadata = data["provider_metadata"]
                row = {"ordinal": ordinal, "status": data["status"], "terminal_sha256": sha(terminal.read_bytes())}
                if data["status"] == "completed": row["native_identity"] = {"request_id_hash": metadata["request_id_sha256"], "session_id_hash": metadata["session_id_sha256"]}
                rows.append(row)
            return {"ordinals": wave_ordinals, "rows": rows}
    parent = Parent(); epoch = {"execution_mode": "fixture", "max_concurrency": 10, "runtime_manifest": {"sha256": "c" * 64}, "runtime_package": {"manifest_sha256": "d" * 64}, "v3_source": {"sha256": "e" * 64}, "selected_schedule": {"sha256": "f" * 64}}
    requests = {ordinal: {"ordinal": ordinal, "pass_id": str(ordinal)} for ordinal in [203, 205, 211, *suffix]}
    monkeypatch.setattr(value, "_manifest", lambda _root: (manifest, raw)); monkeypatch.setattr(value, "_load", lambda *_args: parent)
    monkeypatch.setattr(value, "_partial", lambda *_args: {}); monkeypatch.setattr(value, "_source_guard", lambda *_args: (epoch, b"epoch", tmp_path, requests)); monkeypatch.setattr(value, "_adoption", lambda *_args: {})
    monkeypatch.setattr(value, "_controller_review", lambda *_args, **_kwargs: {"parent_review_path": str(tmp_path / "review.json"), "parent_review_sha256": "f" * 64, "parent_review": {"route": {}}, "route_sha256": "1" * 64, "gate_sha256": "2" * 64})
    queue.rmdir()
    with pytest.raises(ValueError, match="queue"):
        value.dispatch_replacements(successor_root=root, adoption_path=tmp_path / "adoption.json", expected_adoption_sha256="3" * 64, review_path=tmp_path / "review.json", expected_review_sha256="4" * 64, queue_root=queue)
    queue.mkdir()
    result = value.dispatch_replacements(successor_root=root, adoption_path=tmp_path / "adoption.json", expected_adoption_sha256="3" * 64, review_path=tmp_path / "review.json", expected_review_sha256="4" * 64, queue_root=queue)
    assert result["provider_calls_made"] == 3 and result["completed_ordinals"] == [203, 205, 211] and maximum_active == 3
    with pytest.raises(ValueError, match="unreplayed"):
        value.dispatch_replacements(successor_root=root, adoption_path=tmp_path / "adoption.json", expected_adoption_sha256="3" * 64, review_path=tmp_path / "review.json", expected_review_sha256="4" * 64, queue_root=queue)
    barrier = threading.Barrier(10); active = 0; maximum_active = 0; failed_transport_ordinals = {215}
    monkeypatch.setattr(value, "_attempts", lambda *_args: {ordinal: {"status": "completed"} for ordinal in [203, 205, 211]})
    monkeypatch.setattr(value, "_validated_replays", lambda *_args: ({203, 205, 211}, []))
    suffix_result = value.dispatch_wave(start_ordinal=212, wave_size=10, successor_root=root, adoption_path=tmp_path / "adoption.json", expected_adoption_sha256="3" * 64, review_path=tmp_path / "review.json", expected_review_sha256="4" * 64, queue_root=queue)
    assert suffix_result["state"] == "stopped_no_retry" and suffix_result["provider_calls_made"] == 10 and maximum_active == 10
    assert 215 in suffix_result["contact_started_ordinals"] and 215 not in suffix_result["uncontacted_ordinals"]
    delayed_root = tmp_path / "delayed"; delayed_root.mkdir(); (delayed_root / "successor-manifest.json").write_bytes(raw)
    released, peers_waiting = threading.Event(), threading.Event(); delayed_calls = 0
    def delayed_guard(*_args: Any) -> tuple[dict[str, Any], bytes, Path, dict[int, Any]]:
        nonlocal delayed_calls
        delayed_calls += 1
        if getattr(gate_local, "ordinal", None) in {205, 211}:
            peers_waiting.set(); assert released.wait(5)
        return epoch, b"epoch", tmp_path, {ordinal: {"ordinal": ordinal, "pass_id": str(ordinal)} for ordinal in [203, 205, 211]}
    failed_transport_ordinals = {203}; barrier = threading.Barrier(1)
    monkeypatch.setattr(value, "_attempts", lambda *_args: {})
    monkeypatch.setattr(value, "_validated_replays", lambda *_args: (set(), []))
    monkeypatch.setattr(value, "_source_guard", delayed_guard)
    outcome: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: outcome.setdefault("result", value.dispatch_replacements(successor_root=delayed_root, adoption_path=tmp_path / "adoption.json", expected_adoption_sha256="3" * 64, review_path=tmp_path / "review.json", expected_review_sha256="4" * 64, queue_root=queue)))
    failed_terminal = delayed_root / "attempts" / "request-0203" / "terminal.json"
    worker.start(); assert peers_waiting.wait(5) and first_failed.wait(5)
    for _ in range(100):
        if failed_terminal.is_file(): break
        time.sleep(0.01)
    assert failed_terminal.is_file(); released.set(); worker.join(10)
    assert not worker.is_alive() and outcome["result"]["provider_calls_made"] == 1
    assert outcome["result"]["uncontacted_ordinals"] == [205, 211]
