from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results/hbq-human-alignment-wpb-compact-family-native-v1/recovery_v5_suffix.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("wpb_v5_suffix_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_suffix_is_exactly_0918_and_26_later_cells() -> None:
    value = load()
    cells = [{"cell_id": f"old-{index}", "kind": "unstarted"} for index in range(13)]
    cells += [{"cell_id": value.FIRST_V5_CELL, "kind": "unstarted"}]
    cells += [{"cell_id": f"later-{index}", "kind": "unstarted"} for index in range(26)]
    assert [item["cell_id"] for item in value._suffix({"cells": cells})] == [value.FIRST_V5_CELL] + [f"later-{index}" for index in range(26)]


def test_authority_rejects_canonical_queue_and_preserves_dnc_binding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load()
    cells = [{"cell_id": f"old-{index}", "kind": "unstarted"} for index in range(13)]
    cells += [{"cell_id": value.FIRST_V5_CELL, "kind": "unstarted"}]
    cells += [{"cell_id": f"later-{index}", "kind": "unstarted"} for index in range(26)]
    plan, plan_hash = {"cells": cells}, write(tmp_path / "recovery-plan.json", {"cells": cells})
    canonical_queue, isolated_queue = tmp_path / "canonical", tmp_path / "isolated"
    canonical_queue.mkdir(); isolated_queue.mkdir()
    frozen = SimpleNamespace(QUEUE_ROOT=canonical_queue, _read_plan=lambda _root, expected: plan if expected == plan_hash else None, _verify_origin=lambda _plan: None, _load_legacy=lambda: None, _rows=lambda _legacy, _root: ({"schedule_sha256": None, "payloads": {}}, {}), sha256=lambda raw: hashlib.sha256(raw).hexdigest())
    monkeypatch.setattr(value, "_frozen", lambda: frozen)
    package_root = tmp_path / "package"
    broker, adapter = package_root / "model_work_queue/broker.py", package_root / "model_work_queue/adapters/grok_exec.py"
    broker.parent.mkdir(parents=True); adapter.parent.mkdir(parents=True)
    broker.write_text("# candidate\n", encoding="utf-8"); adapter.write_text("# candidate\n", encoding="utf-8")
    files = [{"path": "model_work_queue/broker.py", "sha256": hashlib.sha256(broker.read_bytes()).hexdigest()}, {"path": "model_work_queue/adapters/grok_exec.py", "sha256": hashlib.sha256(adapter.read_bytes()).hexdigest()}]
    manifest = package_root / "candidate-manifest.json"
    manifest_hash = write(manifest, {"schema_version": 6, "kind": "complete_candidate_runtime_probe_set", "explicit_exclusion": ["candidate-manifest.json"], "files": files})
    candidate = {"package_manifest": {"path": str(manifest), "sha256": manifest_hash}, "broker": {"path": str(broker), "sha256": files[0]["sha256"]}, "adapter": {"path": str(adapter), "sha256": files[1]["sha256"]}, "isolated_queue_root": str(isolated_queue)}
    bound = {"package_manifest": {"path": str(manifest.resolve()), "sha256": manifest_hash}, "broker": {"path": str(broker.resolve()), "sha256": files[0]["sha256"]}, "adapter": {"path": str(adapter.resolve()), "sha256": files[1]["sha256"]}, "isolated_queue_root": str(isolated_queue.resolve())}
    route, gate = {"name": "candidate", "model": "grok", "timeout_seconds": 300, "max_concurrency": 1, "nonvisual_max_turns": 1}, {"review": "gate"}
    monkeypatch.setattr(value, "_old_0918", lambda **_kwargs: None)
    review = {"decision": "approved_wpb_v5_side_by_side_suffix", "recovery_plan_sha256": plan_hash, "suffix_root": str((tmp_path / "suffix").resolve()), "cell_ids": [item["cell_id"] for item in cells[13:]], "0918_precontact_derivative": True, "candidate": bound, "route": route, "route_sha256": value._hash(route), "gate": gate, "gate_sha256": value._hash(gate), "helper": {"path": str(value.HELPER_PATH), "sha256": value._hash(value.HELPER_PATH.read_bytes())}, "reviewed_at": "2026-09-08T00:00:00Z", "expires_at": "2099-01-01T00:00:00Z"}
    review_path = tmp_path / "review.json"; review_hash = write(review_path, review)
    old_root, suffix_root = tmp_path / "old", tmp_path / "suffix"
    old_root.mkdir()
    result = value.verify_authority(recovery_root=old_root, suffix_root=suffix_root, expected_plan_sha256=plan_hash, reviewed_path=review_path, expected_review_sha256=review_hash, candidate=candidate)
    assert len(result["cell_ids"]) == 27 and result["provider_calls_made"] == 0
    review["suffix_root"] = str(old_root)
    review_hash = write(review_path, review)
    with pytest.raises(ValueError, match="scope"):
        value.verify_authority(recovery_root=old_root, suffix_root=suffix_root, expected_plan_sha256=plan_hash, reviewed_path=review_path, expected_review_sha256=review_hash, candidate=candidate)
    review["suffix_root"] = str(suffix_root.resolve())
    review_hash = write(review_path, review)
    candidate["isolated_queue_root"] = str(canonical_queue)
    with pytest.raises(ValueError, match="isolated queue"):
        value.verify_authority(recovery_root=old_root, suffix_root=suffix_root, expected_plan_sha256=plan_hash, reviewed_path=review_path, expected_review_sha256=review_hash, candidate=candidate)


@pytest.mark.parametrize("revision", [6, 7])
def test_manifest_revision_keeps_core_pins_and_detects_member_drift(tmp_path: Path, revision: int) -> None:
    value = load()
    root = tmp_path / "candidate"
    files = []
    for name in ("model_work_queue/broker.py", "model_work_queue/adapters/grok_exec.py", "probe/procedure.md"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"reviewed member\n")
        files.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest_path = root / "candidate-manifest.json"
    digest = write(manifest_path, {"schema_version": revision, "kind": "complete_candidate_runtime_probe_set", "explicit_exclusion": ["candidate-manifest.json"], "files": files})
    members = {item["path"]: item["sha256"] for item in files}
    queue, canonical = tmp_path / "isolated", tmp_path / "canonical"; queue.mkdir(); canonical.mkdir()
    candidate = {"package_manifest": {"path": str(manifest_path), "sha256": digest}, "broker": {"path": str(root / "model_work_queue/broker.py"), "sha256": members["model_work_queue/broker.py"]}, "adapter": {"path": str(root / "model_work_queue/adapters/grok_exec.py"), "sha256": members["model_work_queue/adapters/grok_exec.py"]}, "isolated_queue_root": str(queue)}
    assert value._candidate(candidate, SimpleNamespace(QUEUE_ROOT=canonical))["package_manifest"]["sha256"] == digest
    (root / "probe/procedure.md").write_bytes(b"changed after review\n")
    with pytest.raises(ValueError, match="member drifted"):
        value._candidate(candidate, SimpleNamespace(QUEUE_ROOT=canonical))


def test_candidate_rejects_noninteger_manifest_revision(tmp_path: Path) -> None:
    value = load(); root, queue, canonical = tmp_path / "package", tmp_path / "queue", tmp_path / "canonical"
    broker, adapter = root / "model_work_queue/broker.py", root / "model_work_queue/adapters/grok_exec.py"
    broker.parent.mkdir(parents=True); adapter.parent.mkdir(parents=True); broker.write_text("# broker\n", encoding="utf-8"); adapter.write_text("# adapter\n", encoding="utf-8"); queue.mkdir(); canonical.mkdir()
    files = [{"path": "model_work_queue/broker.py", "sha256": hashlib.sha256(broker.read_bytes()).hexdigest()}, {"path": "model_work_queue/adapters/grok_exec.py", "sha256": hashlib.sha256(adapter.read_bytes()).hexdigest()}]
    manifest = root / "candidate-manifest.json"; digest = write(manifest, {"schema_version": True, "kind": "complete_candidate_runtime_probe_set", "explicit_exclusion": ["candidate-manifest.json"], "files": files})
    candidate = {"package_manifest": {"path": str(manifest), "sha256": digest}, "broker": {"path": str(broker), "sha256": files[0]["sha256"]}, "adapter": {"path": str(adapter), "sha256": files[1]["sha256"]}, "isolated_queue_root": str(queue)}
    with pytest.raises(ValueError, match="shape"):
        value._candidate(candidate, SimpleNamespace(QUEUE_ROOT=canonical))


def test_dispatch_success_admits_and_preserves_old_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, harness = _harness(tmp_path, monkeypatch)
    dispatched = value.dispatch(**harness["arguments"])
    assert dispatched["status"] == "completed_pending_v5_admission"
    admitted = value.admit(**harness["arguments"])
    assert admitted["status"] == "admitted"
    assert harness["old_bytes"] == (harness["old_root"] / "immutable.json").read_bytes()
    assert not any(harness["old_root"].rglob("v5-*"))


def test_terminal_outcome_consumes_cell_and_blocks_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, harness = _harness(tmp_path, monkeypatch, terminal=True)
    result = value.dispatch(**harness["arguments"])
    assert result == {"cell_id": "wpb-pair-wpb-en-0918", "status": "terminal_no_resend", "outcome_sha256": value._hash({"state": "definitely_not_contacted", "result": None, "failure": {"code": "gate"}}), "provider_calls_made": 0}
    with pytest.raises(ValueError, match="already consumed"):
        value.dispatch(**harness["arguments"])
    assert harness["broker"].calls == 1


def test_order_blocks_second_cell_until_first_admission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, harness = _harness(tmp_path, monkeypatch)
    later = {**harness["arguments"], "cell_id": "later-0"}
    with pytest.raises(ValueError, match="raw evidence is missing"):
        value.dispatch(**later)
    assert harness["broker"].calls == 0


def test_gate_drift_stops_before_mock_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value, harness = _harness(tmp_path, monkeypatch, gate_drift=True)
    result = value.dispatch(**harness["arguments"])
    assert result["status"] == "terminal_no_resend"
    assert harness["broker"].launches == 0


def test_disjoint_roots_reject_ancestor_and_descendant(tmp_path: Path) -> None:
    value = load()
    with pytest.raises(ValueError, match="disjoint"):
        value._disjoint(tmp_path, tmp_path / "suffix")


def test_old_0918_rejects_wrong_dnc_or_touched_later_cell(tmp_path: Path) -> None:
    value = load()
    root, cell, later = tmp_path / "old", tmp_path / "old/cells" / value.FIRST_V5_CELL, tmp_path / "old/cells/later-0"
    cell.mkdir(parents=True); later.mkdir(parents=True)
    payload = b"prompt"; row = {"cell_id": value.FIRST_V5_CELL, "payload_sha256": hashlib.sha256(payload).hexdigest()}
    for name, item in {"attempt": {"one": 1}, "outcome": {"state": "definitely_not_contacted", "result": None}, "request": {"prompt": "prompt"}, "prepared": {"cell_id": value.FIRST_V5_CELL, "kind": "unstarted", "payload_sha256": row["payload_sha256"]}}.items():
        write(cell / f"{name}.json", item)
    frozen = SimpleNamespace(_load_legacy=lambda: None, _rows=lambda _legacy, _root: ({"schedule_sha256": "schedule", "payloads": {value.FIRST_V5_CELL: payload}}, {value.FIRST_V5_CELL: row}), sha256=lambda raw: hashlib.sha256(raw).hexdigest())
    plan = {"freeze_root": str(root), "schedule_sha256": "schedule"}
    binding = {name: {"path": str((cell / f"{name}.json").resolve()), "sha256": hashlib.sha256((cell / f"{name}.json").read_bytes()).hexdigest()} for name in ("attempt", "outcome", "request", "prepared")}
    value._old_0918(frozen=frozen, plan=plan, root=root, review={"0918_original": {"cell_id": value.FIRST_V5_CELL, **binding}}, suffix=[row, {"cell_id": "later-0", "kind": "unstarted"}])
    binding["outcome"] = {"path": str((cell / "attempt.json").resolve()), "sha256": binding["attempt"]["sha256"]}
    with pytest.raises(ValueError, match="path drifted"):
        value._old_0918(frozen=frozen, plan=plan, root=root, review={"0918_original": {"cell_id": value.FIRST_V5_CELL, **binding}}, suffix=[row, {"cell_id": "later-0", "kind": "unstarted"}])
    write(later / "attempt.json", {"touched": True})
    with pytest.raises(ValueError, match="touched"):
        value._old_0918(frozen=frozen, plan=plan, root=root, review={"0918_original": {"cell_id": value.FIRST_V5_CELL, **{name: {"path": str((cell / f"{name}.json").resolve()), "sha256": hashlib.sha256((cell / f"{name}.json").read_bytes()).hexdigest()} for name in ("attempt", "outcome", "request", "prepared")}}}, suffix=[row, {"cell_id": "later-0", "kind": "unstarted"}])


@pytest.mark.parametrize("expires_in, helper_hash, message", [(299, None, "route timeout"), (600, "0" * 64, "helper")])
def test_authority_requires_live_window_and_helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, expires_in: int, helper_hash: str | None, message: str) -> None:
    value = load()
    old, suffix = tmp_path / "old", tmp_path / "suffix"; old.mkdir(); suffix.mkdir()
    cells = [{"cell_id": f"old-{index}", "kind": "unstarted"} for index in range(13)] + [{"cell_id": value.FIRST_V5_CELL, "kind": "unstarted"}] + [{"cell_id": f"later-{index}", "kind": "unstarted"} for index in range(26)]
    plan = {"cells": cells}
    frozen = SimpleNamespace(_read_plan=lambda _root, _hash: plan, _verify_origin=lambda _plan: None)
    monkeypatch.setattr(value, "_frozen", lambda: frozen)
    monkeypatch.setattr(value, "_old_0918", lambda **_kwargs: None)
    monkeypatch.setattr(value, "_candidate", lambda candidate, _frozen: candidate)
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    route, gate, candidate = {"timeout_seconds": 300, "max_concurrency": 1, "nonvisual_max_turns": 1}, {"gate": "x"}, {"candidate": "x"}
    review = {"decision": "approved_wpb_v5_side_by_side_suffix", "recovery_plan_sha256": "c" * 64, "suffix_root": str(suffix.resolve()), "cell_ids": [item["cell_id"] for item in cells[13:]], "0918_precontact_derivative": True, "route": route, "route_sha256": value._hash(route), "gate": gate, "gate_sha256": value._hash(gate), "candidate": candidate, "helper": {"path": str(value.HELPER_PATH), "sha256": value._hash(value.HELPER_PATH.read_bytes()) if helper_hash is None else helper_hash}, "reviewed_at": (now - __import__("datetime").timedelta(seconds=1)).isoformat(), "expires_at": (now + __import__("datetime").timedelta(seconds=expires_in)).isoformat()}
    review_path = tmp_path / "review.json"; review_hash = write(review_path, review)
    with pytest.raises(ValueError, match=message):
        value._authority(recovery_root=old, suffix_root=suffix, expected_plan_sha256="c" * 64, reviewed_path=review_path, expected_review_sha256=review_hash, candidate=candidate, require_live=True)


def test_prior_admission_replays_recorded_review_not_renewal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    value = load(); cell = tmp_path / "suffix/cells/first"; cell.mkdir(parents=True)
    old_review, new_review = tmp_path / "review-a.json", tmp_path / "review-b.json"
    write(old_review, {"a": 1}); write(new_review, {"b": 2})
    attempt = {"review": {"path": str(old_review), "sha256": "a" * 64}}
    write(cell / "v5-attempt.json", attempt); admission = {"admitted": True}; write(cell / "v5-admission.json", admission)
    before = {(cell / name).name: (cell / name).read_bytes() for name in ("v5-attempt.json", "v5-admission.json")}
    captured: dict[str, Any] = {}
    monkeypatch.setattr(value, "_admission_evidence", lambda **kwargs: (captured.update(kwargs) or ({}, {}, SimpleNamespace(), cell, {}, {}, b"", "request", "session", "result")))
    monkeypatch.setattr(value, "_admission", lambda **_kwargs: admission)
    assert value._verify_admission(recovery_root=tmp_path / "old", suffix_root=tmp_path / "suffix", expected_plan_sha256="p" * 64, cell_id="first", reviewed_path=new_review, expected_review_sha256="b" * 64, candidate={}) == admission
    assert captured["reviewed_path"] == str(old_review) and captured["expected_review_sha256"] == "a" * 64
    assert before == {(cell / name).name: (cell / name).read_bytes() for name in ("v5-attempt.json", "v5-admission.json")}


def test_v4_prefix_identity_collision_rejects_new_admission(tmp_path: Path) -> None:
    value = load(); payload = b"prompt"; row = {"payload_sha256": hashlib.sha256(payload).hexdigest()}
    prefix = [{"cell_id": f"v4-{number}"} for number in range(12)]; prefix.insert(1, {"cell_id": "wpb-pair-wpb-en-0843"})
    plan = {"cells": prefix + [{"cell_id": value.FIRST_V5_CELL}], "freeze_root": str(tmp_path), "origin": {"reserved_identity_hashes": [], "reserved_request_id_hashes": [], "reserved_session_id_hashes": []}}
    frozen = SimpleNamespace(_load_legacy=lambda: SimpleNamespace(_valid_response=lambda _core, output: output), _rows=lambda _legacy, _root: ({"payloads": {value.FIRST_V5_CELL: payload}, "schedule_sha256": None, "core": object()}, {value.FIRST_V5_CELL: row}), sha256=lambda raw: hashlib.sha256(raw).hexdigest(), _verify_admission=lambda _plan, _root, item: {"identity_sha256": value._hash({"request_id": "v4-0", "session_id": "s"}) if item["cell_id"] == "v4-0" else value._hash(str(item["cell_id"])), "request_id_sha256": value._hash(("r" + str(item["cell_id"])).encode()), "session_id_sha256": value._hash(("s" + str(item["cell_id"])).encode())})
    with pytest.raises(ValueError, match="native-v4"):
        value._admission(plan=plan, frozen=frozen, recovery_root=tmp_path, cell=tmp_path / value.FIRST_V5_CELL, result={"output": {}}, runtime={"tool_policy_attestation_hash": "t" * 64}, envelope_raw=b"{}", request_id="v4-0", session_id="s", result_sha256="r", expected_plan_sha256="p" * 64, expected_review_sha256="q" * 64)


@pytest.mark.parametrize("mutation, message", [("schema", "schema commitment"), ("replay", "envelope replay")])
def test_admission_rejects_schema_or_replay_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, message: str) -> None:
    value, harness = _harness(tmp_path, monkeypatch)
    value.dispatch(**harness["arguments"])
    cell = harness["suffix_root"] / "cells" / "wpb-pair-wpb-en-0918"
    if mutation == "schema":
        write(cell / "response-schema.json", {"type": "string"})
    else:
        harness["broker"].parse_state = "ambiguous"
    with pytest.raises(ValueError, match=message):
        value.admit(**harness["arguments"])


def _harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, terminal: bool = False, gate_drift: bool = False) -> tuple[Any, dict[str, Any]]:
    value = load()
    old_root, suffix_root, queue = tmp_path / "old", tmp_path / "suffix", tmp_path / "queue"
    old_root.mkdir(); queue.mkdir(); (old_root / "immutable.json").write_text('{"old":true}', encoding="utf-8")
    old_bytes = (old_root / "immutable.json").read_bytes()
    cell_id, later_id, payload, schema = value.FIRST_V5_CELL, "later-0", b"prompt", {"type": "object"}
    route, gate, candidate = {"name": "candidate", "model": "grok", "reasoning_effort": "high", "timeout_seconds": 300, "max_concurrency": 1, "nonvisual_max_turns": 1}, {"review": "gate"}, {"isolated_queue_root": str(queue), "broker": {"path": "broker", "sha256": "b" * 64}, "adapter": {"path": "adapter", "sha256": "a" * 64}, "package_manifest": {"path": "manifest", "sha256": "m" * 64}}
    row = {"cell_id": cell_id, "payload_sha256": hashlib.sha256(payload).hexdigest()}
    prefix = [{"cell_id": f"v4-{number}", "kind": "unstarted"} for number in range(12)]
    prefix.insert(1, {"cell_id": "wpb-pair-wpb-en-0843", "kind": "unstarted"})
    plan = {"freeze_root": str(tmp_path), "schedule_sha256": "schedule", "origin": {"reserved_identity_hashes": [], "reserved_request_id_hashes": [], "reserved_session_id_hashes": []}, "cells": prefix + [{"cell_id": cell_id, "kind": "unstarted"}, {"cell_id": later_id, "kind": "unstarted"}]}

    class Broker:
        calls = 0
        launches = 0
        parse_state = "completed"
        envelope = b""

        def __init__(self, _queue: Path) -> None:
            pass

        def run_grok_native_request(self, _route: str, request: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            type(self).calls += 1
            try:
                kwargs["before_contact"]()
            except ValueError:
                return {"state": "definitely_not_contacted", "result": None, "failure": {"code": "gate"}}
            if terminal:
                return {"state": "definitely_not_contacted", "result": None, "failure": {"code": "gate"}}
            type(self).launches += 1
            session = kwargs["session_id"]
            output = {"answer": "ok"}
            envelope = {"structuredOutput": output, "requestId": "request-1", "sessionId": session}
            type(self).envelope = value._canonical(envelope)
            execution = {"tools": "deny_wins_none_attested", "max_turns": 1, "output_schema_hash": value._hash(schema), "staged_prompt_sha256": row["payload_sha256"], "staged_prompt_byte_length": len(payload), "nonvisual_transport_contract": {"name": "v5"}, "nonvisual_transport_contract_sha256": value._hash({"name": "v5"})}
            runtime = {"adapter_version": 5, "identity_evidence": "requested_only", "execution_policy": "bounded_nonvisual_deny_wins_attested", "reasoning_attested": False, "tool_policy_attestation_hash": "t" * 64, "requested_model": route["model"], "requested_reasoning_effort": route["reasoning_effort"], "request_id_hash": value._hash(b"request-1"), "session_id_hash": value._hash(session.encode()), "envelope_hash": value._hash(type(self).envelope), "execution_contract": execution}
            result = {"schema_version": 2, "request_hash": value._hash(request), "output": output, "output_hash": value._hash(output), "runtime": runtime, "native_envelope_artifact": {"schema_version": 1, "sha256": value._hash(type(self).envelope), "byte_length": len(type(self).envelope)}}
            return {"state": "completed", "result": result, "failure": None}

        def read_grok_native_envelope(self, _descriptor: dict[str, Any]) -> bytes:
            return type(self).envelope

        def _parse_grok_exec_envelope(self, _projection: bytes, _route: dict[str, Any], _request: dict[str, Any], **_kwargs: Any) -> Any:
            return SimpleNamespace(state=type(self).parse_state, result=None if type(self).parse_state != "completed" else json.loads(_projection.decode())["result"])

    def write_new(path: Path, item: Any) -> bytes:
        raw = value._canonical(item); path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(raw)
        return raw

    legacy = SimpleNamespace(_valid_response=lambda _core, output: output)
    frozen = SimpleNamespace(_frozen_schema=lambda _plan: schema, _load_legacy=lambda: legacy, _rows=lambda _legacy, _root: ({"schedule_sha256": "schedule", "payloads": {cell_id: payload, later_id: payload}, "core": object()}, {cell_id: row, later_id: {"cell_id": later_id, "payload_sha256": row["payload_sha256"]}}), sha256=lambda raw: hashlib.sha256(raw).hexdigest(), _write_new=write_new, _load_broker=lambda _path: (None, Broker), _verify_admission=lambda _plan, _root, item: {"identity_sha256": value._hash(str(item["cell_id"])), "request_id_sha256": value._hash(("request-" + str(item["cell_id"])).encode()), "session_id_sha256": value._hash(("session-" + str(item["cell_id"])).encode())})
    review_path = tmp_path / "review.json"; review_hash = "r" * 64; write(review_path, {"review": "mock"})
    authority = {"route": route, "gate": gate, "candidate": candidate, "review": {"path": str(review_path), "sha256": review_hash}, "helper": {"path": str(value.HELPER_PATH), "sha256": value._hash(value.HELPER_PATH.read_bytes())}}
    suffix = [{"cell_id": cell_id, "kind": "unstarted"}, {"cell_id": later_id, "kind": "unstarted"}]
    monkeypatch.setattr(value, "_authority", lambda **_kwargs: (plan, authority, frozen, suffix))
    observations = [{"path": "gate", "row": {"state": "healthy"}}, {"path": "gate", "row": {"state": "revoked"}}] if gate_drift else [{"path": "gate", "row": {"state": "healthy"}}]
    monkeypatch.setattr(value, "_observe_gate", lambda *_args, **_kwargs: observations[min(len(observations) - 1, _kwargs.get("initial", False) is False)])
    arguments = {"recovery_root": old_root, "suffix_root": suffix_root, "expected_plan_sha256": "p" * 64, "cell_id": cell_id, "reviewed_path": review_path, "expected_review_sha256": review_hash, "candidate": candidate}
    return value, {"arguments": arguments, "old_root": old_root, "old_bytes": old_bytes, "suffix_root": suffix_root, "broker": Broker}
