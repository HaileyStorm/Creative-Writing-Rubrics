from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/recovery_v5_continuation.py"
PROPOSAL = Path(r"C:\Users\Haile\Documents\cwr-wpb-1088-schema-recovery-proposal-20260909-r1")


def load() -> Any:
    spec = importlib.util.spec_from_file_location("wpb1088_continuation_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def adoption(value: Any, path: Path) -> tuple[Path, str]:
    digest = write_json(path, {
        "schema_version": 1,
        "kind": "wpb1088_local_session_projection_owner_adoption",
        "cell_id": value.CELL_ID,
        "decision": "owner_adopts_exact_local_session_projection",
        "proposal_sha256": value.PROPOSAL_SHA256,
        "approved_at": "2026-09-09T23:00:00Z",
        "resend_authority": False,
        "ordinary_native_admission": False,
    })
    return path, digest


@pytest.mark.skipif(not PROPOSAL.is_dir(), reason="local 1088 proposal is not available")
def test_projection_requires_exact_owner_adoption_and_preserves_local_identity(tmp_path: Path) -> None:
    value = load()
    missing = tmp_path / "missing.json"
    with pytest.raises(ValueError, match="adoption.*absent"):
        value.verify_projection(proposal_root=PROPOSAL, expected_proposal_sha256=value.PROPOSAL_SHA256, adoption_path=missing, expected_adoption_sha256="a" * 64)
    path, digest = adoption(value, tmp_path / "adoption.json")
    result = value.verify_projection(proposal_root=PROPOSAL, expected_proposal_sha256=value.PROPOSAL_SHA256, adoption_path=path, expected_adoption_sha256=digest)
    assert result["measurement"]["cell_id"] == value.CELL_ID
    assert result["provenance"]["classification"] == "local_session_schema_recovered"
    assert result["provenance"]["native_admission_permitted"] is False
    assert set(result["local_identity"]) == {"request_id_sha256", "session_id_sha256"}
    wrong = json.loads(path.read_text(encoding="utf-8")); wrong["resend_authority"] = True
    wrong_hash = write_json(path, wrong)
    with pytest.raises(ValueError, match="recovery ceiling"):
        value.verify_projection(proposal_root=PROPOSAL, expected_proposal_sha256=value.PROPOSAL_SHA256, adoption_path=path, expected_adoption_sha256=wrong_hash)


def fake_projection(value: Any) -> dict[str, Any]:
    return {
        "measurement": {"cell_id": value.CELL_ID},
        "provenance": {"classification": "local_session_schema_recovered"},
        "bindings": {"proposal_root": "P", "expected_proposal_sha256": "a" * 64, "adoption_path": "A", "expected_adoption_sha256": "b" * 64},
        "local_identity": {"request_id_sha256": "r" * 64, "session_id_sha256": "s" * 64},
    }


def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, dict[str, Any]]:
    value = load()
    projection = fake_projection(value)
    monkeypatch.setattr(value, "verify_projection", lambda **_kwargs: projection)
    route, gate = {"name": "candidate"}, {"state": "healthy"}
    review_path = tmp_path / "old-review.json"; review_path.write_text("{}", encoding="utf-8")
    authority = {"review": {"path": str(review_path), "sha256": "o" * 64}, "route": route, "gate": gate}
    writes: list[Path] = []

    class Frozen:
        def _write_new(self, path: Path, item: Any) -> bytes:
            writes.append(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
            with path.open("xb") as handle:
                handle.write(raw)
            return raw

    class Old:
        launches = 0
        verified: list[str] = []
        reject_before_attempt = False
        def _authority(self, *, require_live: bool, **_kwargs: Any):
            return {}, authority, Frozen(), []
        def _verify_admission(self, *, cell_id: str, **_kwargs: Any) -> dict[str, Any]:
            type(self).verified.append(cell_id)
            return {"cell_id": cell_id, "native": True}
        def _guard_inflight(self, **_kwargs: Any) -> None:
            return None
        def _admission(self, **_kwargs: Any) -> dict[str, Any]:
            return {"request_id_sha256": "q" * 64, "session_id_sha256": "t" * 64}
        def dispatch(self, *, cell_id: str, **kwargs: Any) -> dict[str, Any]:
            if type(self).reject_before_attempt:
                type(self).reject_before_attempt = False
                raise ValueError("old prior-admission check rejected before attempt")
            self._verify_admission(cell_id=value.CELL_ID, **kwargs)
            self._guard_inflight(**kwargs)
            type(self).launches += 1
            return {"cell_id": cell_id, "status": "completed_pending_v5_admission"}
        def admit(self, *, cell_id: str, **kwargs: Any) -> dict[str, Any]:
            self._verify_admission(cell_id=value.CELL_ID, **kwargs)
            return {"cell_id": cell_id, "admission": self._admission(**kwargs)}

    old = Old()
    monkeypatch.setattr(value, "_old", lambda: old)
    binding = projection["bindings"]
    review = {"format_version": 1, "kind": "wpb1088_prospective_continuation_review", "decision": "approved_wpb1088_local_projection_and_remaining_native_continuation", "wrapper": value._descriptor(value.HELPER_PATH), "frozen_helper": {"path": str(value.FROZEN_HELPER.resolve()), "sha256": value.FROZEN_HELPER_SHA256}, "projection": binding, "remaining_cell_ids": list(value.REMAINING_CELL_IDS), "old_review": authority["review"], "route": route, "route_sha256": value._hash(route), "gate": gate, "gate_sha256": value._hash(gate)}
    arguments = {"recovery_root": tmp_path / "old", "suffix_root": tmp_path / "suffix", "expected_plan_sha256": "p" * 64, "cell_id": value.REMAINING_CELL_IDS[0], "reviewed_path": review_path, "expected_review_sha256": "o" * 64, "candidate": {}, "projection_binding": binding, "independent_continuation_review": review}
    return value, {"old": old, "arguments": arguments, "review": review, "writes": writes}


def test_native_continuation_uses_only_exact_eleven_and_keeps_1088_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, state = harness(tmp_path, monkeypatch)
    result = value.dispatch(**state["arguments"])
    assert result["cell_id"] == value.REMAINING_CELL_IDS[0]
    assert state["old"].launches == 1
    assert value.CELL_ID not in state["old"].verified
    assert state["writes"][0].name == "continuation-wrapper-provenance.json"
    admitted = value.admit(**state["arguments"])
    assert admitted["admission"]["request_id_sha256"] != "r" * 64
    rejected = {**state["arguments"], "cell_id": value.CELL_ID}
    with pytest.raises(ValueError, match="never be resent"):
        value.dispatch(**rejected)
    outside = {**state["arguments"], "cell_id": "wpb-pair-wpb-en-0918"}
    with pytest.raises(ValueError, match="eleven untouched"):
        value.verify_native(**outside)


@pytest.mark.parametrize("mutation", ["wrapper", "route"])
def test_changed_composition_binding_rejects_before_mock_contact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    value, state = harness(tmp_path, monkeypatch)
    if mutation == "wrapper":
        state["review"]["wrapper"] = {"path": str(value.HELPER_PATH), "sha256": "0" * 64}
    else:
        state["review"]["route"] = {"name": "changed"}
    with pytest.raises(ValueError, match="binding"):
        value.dispatch(**state["arguments"])
    assert state["old"].launches == 0


def test_native_identity_cannot_reuse_the_local_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, state = harness(tmp_path, monkeypatch)
    value.dispatch(**state["arguments"])
    state["old"]._admission = lambda **_kwargs: {"request_id_sha256": "r" * 64, "session_id_sha256": "t" * 64}
    with pytest.raises(ValueError, match="reuses 1088"):
        value.admit(**state["arguments"])


@pytest.mark.parametrize("mutation", ["missing", "changed"])
def test_wrapper_provenance_must_survive_for_native_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    value, state = harness(tmp_path, monkeypatch)
    value.dispatch(**state["arguments"])
    path = state["writes"][0]
    if mutation == "missing":
        path.unlink()
    else:
        path.write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="continuation wrapper provenance"):
        value.verify_native(**state["arguments"])


def test_inert_matching_provenance_allows_retry_after_pre_attempt_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, state = harness(tmp_path, monkeypatch)
    type(state["old"]).reject_before_attempt = True
    with pytest.raises(ValueError, match="before attempt"):
        value.dispatch(**state["arguments"])
    assert state["writes"][0].is_file()
    assert value.dispatch(**state["arguments"])["status"] == "completed_pending_v5_admission"
    assert state["old"].launches == 1


@pytest.mark.parametrize("mutation", ["changed", "consumed"])
def test_dispatch_rejects_changed_or_consumed_provenance_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    value, state = harness(tmp_path, monkeypatch)
    value.dispatch(**state["arguments"])
    path = state["writes"][0]
    if mutation == "changed":
        path.write_text('{"changed":true}', encoding="utf-8")
        message = "continuation wrapper provenance"
    else:
        path.with_name("v5-attempt.json").write_text("{}", encoding="utf-8")
        message = "already consumed"
    with pytest.raises(ValueError, match=message):
        value.dispatch(**state["arguments"])
    assert state["old"].launches == 1
