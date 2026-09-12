"""Explicit-runtime local-prefix adapter tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_runtime_data_prefix.py"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load() -> Any:
    spec = importlib.util.spec_from_file_location("runtime_data_prefix_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Runtime:
    class _Runner:
        EVIDENCE_NORMALIZATION_POLICY = "fixture"

        def _normalize_batch(self, projection: dict[str, Any], *, expected_ids: list[str], **_kwargs: Any) -> list[dict[str, Any]]:
            assert [item["question_id"] for item in projection["verdicts"]] == expected_ids
            return [dict(item) for item in projection["verdicts"]]

    def __init__(self) -> None:
        self.runner = self._Runner()
        self.calls = 0

    def verify(self) -> None:
        self.calls += 1


class _Parent:
    def _load_epoch(self, *_args: Any) -> tuple[dict[str, Any], bytes]:
        return {"plan_sha256": "p" * 64}, b"epoch"

    def _plan(self, *_args: Any) -> tuple[dict[str, Any], bytes]:
        return {}, b"plan"

    def _pass_index(self, *_args: Any) -> dict[str, dict[str, str]]:
        return {"pass": {"pass_id": "pass"}}

    def _source_for_pass(self, *_args: Any) -> dict[str, str]:
        return {"opaque_story_id": "fixture", "story_text": "fixture"}

    def _runtime_from_epoch(self, *_args: Any) -> Any:
        raise AssertionError("adapter must use the supplied runtime")

    def _attempt_path(self, root: Path, ordinal: int, name: str) -> Path:
        return root / "attempts" / f"request-{ordinal:04d}" / name


def _context(tmp_path: Path, *, duplicate_peer: bool = False) -> tuple[Any, tuple[Any, ...]]:
    adapter = load()
    root = tmp_path / "continuation"; root.mkdir()
    projection = {"verdicts": [{"question_id": f"q{index}", "verdict": "YES"} for index in range(8)]}
    projection_path = root / "local-projection.json"; projection_path.write_bytes(canonical(projection))
    native = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}
    peers = [{"ordinal": 252, "native_identity": native}, {"ordinal": 253, "native_identity": native if duplicate_peer else {"request_id_hash": "c" * 64, "session_id_hash": "d" * 64}}]
    manifest = {"controller_sha256": adapter.E33_SHA256, "proposal": {"path": "proposal", "sha256": "1" * 64},
                "adoption": {"path": "adoption", "sha256": "2" * 64}, "independent_review": {"path": "review", "sha256": "3" * 64},
                "standing_authority": {"path": "standing", "sha256": "4" * 64}, "local_projection": {"path": str(projection_path), "sha256": digest(projection_path.read_bytes())},
                "successor_root": str(tmp_path / "successor"), "successor_manifest_sha256": "5" * 64,
                "inner_epoch": {"sha256": "6" * 64}, "partial": {"sha256": "7" * 64},
                "ownership": {"protected_native_identity_count": 259, "local_recovery_ordinals": [70, 254], "never_contact_ordinals": [254]},
                "successor_inventory": {"sha256": "8" * 64}, "protected_native_identities": {"sha256": "9" * 64}}
    protected = [peer["native_identity"] for peer in peers]
    parent = _Parent()
    requests = {254: {"pass_id": "pass", "question_ids": [f"q{index}" for index in range(8)]}}
    partial = {"failed_attempts": [{"question_ids": [f"q{index}" for index in range(8)]}], "records": peers, "completed_ordinals": [252, 253]}
    e33 = SimpleNamespace(
        LOCAL_ORDINAL=254, PROJECTED_SHA="e" * 64, ORIGINAL_SHA="f" * 64, SOURCE_STORY_SHA="0" * 64,
        _sha=digest, _canon=canonical, _manifest=lambda *_args: (manifest, b"manifest"),
        _source_guard=lambda _manifest: (None, parent, {}, b"epoch", tmp_path, requests, partial),
        _proposal=lambda *_args: {"proposal": True}, _adoption=lambda *_args: {"evidence_class": "fixture_adoption"},
        _review=lambda *_args: {"decision": "GO"}, _standing=lambda *_args: {"kind": "fixture"},
        _retained_answer=lambda _proposal: projection, _project=lambda answer, _proposal: answer,
        _protected_identities=lambda _manifest: protected, _inventory=lambda _root: {},
        _identity=lambda identities: _identity(identities), _replayed=lambda *_args: (set(), []),
        _json=lambda path, _label: json.loads(Path(path).read_text(encoding="utf-8")),
    )
    return adapter, (e33, root, manifest, b"manifest", parent, tmp_path, requests, partial)


def _identity(values: list[dict[str, str]]) -> list[dict[str, str]]:
    pairs = [(item["request_id_hash"], item["session_id_hash"]) for item in values]
    if len(pairs) != len(set(pairs)):
        raise ValueError("native identity collision")
    return values


def test_local_projection_uses_explicit_runtime_and_truthful_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, context = _context(tmp_path)
    runtime = _Runtime()
    monkeypatch.setattr(adapter, "_local_context", lambda **_kwargs: (*context, runtime))
    result = adapter.verify_local_continuation_with_runtime(
        continuation_root=tmp_path / "continuation", expected_manifest_sha256="a" * 64,
        expected_controller_sha256=adapter.E33_SHA256, runtime=runtime)
    assert result["verdicts"] == [{"question_id": f"q{index}", "verdict": "YES"} for index in range(8)]
    assert result["source"]["controller_sha256"] == adapter.E33_SHA256
    assert result["verifier_provenance"]["e33"]["sha256"] == adapter.E33_SHA256
    assert runtime.calls == 2


def test_wrong_e33_pin_rejects_before_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = load()
    source = tmp_path / "e33.py"; source.write_text("value = 1\n", encoding="utf-8")
    monkeypatch.setattr(adapter, "E33_PATH", source)
    with pytest.raises(ValueError, match="e33 source differs"):
        adapter._load_e33()


def test_reused_peer_identity_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, context = _context(tmp_path, duplicate_peer=True)
    runtime = _Runtime()
    monkeypatch.setattr(adapter, "_local_context", lambda **_kwargs: (*context, runtime))
    with pytest.raises(ValueError, match="collision"):
        adapter.verify_local_continuation_with_runtime(
            continuation_root=tmp_path / "continuation", expected_manifest_sha256="a" * 64,
            expected_controller_sha256=adapter.E33_SHA256, runtime=runtime)


def test_empty_untouched_tail_never_calls_runtime_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, context = _context(tmp_path)
    runtime = _Runtime()
    monkeypatch.setattr(adapter, "_local_context", lambda **_kwargs: (*context, runtime))
    result = adapter.verify_untouched_replay_chain_with_runtime(
        continuation_root=tmp_path / "continuation", expected_manifest_sha256="a" * 64,
        expected_controller_sha256=adapter.E33_SHA256, runtime=runtime, approved_v5_routes={})
    assert result["untouched_replay_ordinals"] == [] and result["untouched_terminals"] == []
    assert result["verifier_provenance"]["runtime_verified_before"] is True
    assert runtime.calls == 2
