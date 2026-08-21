from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
import types
from pathlib import Path

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-v2"


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules.update(aliases or {})
    try:
        spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


study = load("supplemental_hanna_v2_study", "study.py")
pilot = load("supplemental_hanna_v2_pilot", "run_transport_pilot.py", {"study": study})
verify = load("supplemental_hanna_v2_verify", "verify_transport_pilot.py", {"study": study})
enable = load("supplemental_hanna_v2_enable", "enable_development.py", {"study": study, "verify_transport_pilot": verify})
development = load("supplemental_hanna_v2_development", "run_development.py", {"study": study, "enable_development": enable})


def frozen() -> dict:
    return {"cells": [{"cell_id": f"pilot-{number:02d}", "item_id": f"item-{number}", "question_ids": [str(index) for index in range(16)]} for number in range(1, 4)]}


def completed_records(tmp_path: Path, receipts: list[dict]) -> None:
    (tmp_path / "pilot-receipts").mkdir()
    journal = tmp_path / "pilot-journal"; journal.mkdir()
    records = []
    for sequence, receipt in enumerate(receipts, 1):
        path = tmp_path / "pilot-receipts" / f"{receipt['cell_id']}.json"
        path.write_text(json.dumps(receipt), encoding="utf-8")
        records.append({"sequence": sequence, "cell_id": receipt["cell_id"], "status": "completed", "receipt": study.fingerprint(path)})
    for item in records:
        (journal / f"{item['sequence']:04d}-{item['cell_id']}.json").write_text(json.dumps(item), encoding="utf-8")


def test_parent_hashes_and_no_scoreblind_analysis_surface():
    parent = study.CONTRACT["parent_v1"]
    for name, digest in parent["files"].items():
        assert hashlib.sha256((study.PARENT_ROOT / name).read_bytes()).hexdigest() == digest
    assert "score.json" not in (ROOT / "verify_transport_pilot.py").read_text(encoding="utf-8")
    assert "HANNA ratings" in study.CONTRACT["privacy"]["pilot"]
    assert study.CONTRACT["development"]["comparison_status"] == "unmatched_to_primary_32"


def test_parent_runtime_tamper_fails_closed(monkeypatch):
    changed = dict(study.CONTRACT)
    changed["parent_v1"] = {**study.CONTRACT["parent_v1"], "runner_sha256": "0" * 64}
    monkeypatch.setattr(study, "CONTRACT", changed)
    with pytest.raises(ValueError, match="runner binding drifted"):
        study._parent()


def test_pilot_rejects_timeout_mutation_before_provider_work(tmp_path):
    with pytest.raises(ValueError, match="requires timeout 600"):
        pilot.execute(tmp_path, timeout=599)
    assert not (tmp_path / "runs").exists()


def test_failed_pilot_is_immutable_and_never_retries(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "frozen-transport-contract.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {})
    monkeypatch.setattr(pilot, "_execute_one", lambda *_: calls.append("sent") or (_ for _ in ()).throw(RuntimeError("transport failed")))
    with pytest.raises(RuntimeError, match="transport failed"):
        pilot.execute(tmp_path)
    assert calls == ["sent"]
    with pytest.raises(ValueError, match="preregister batch-8"):
        pilot.execute(tmp_path)
    assert calls == ["sent"]


def test_exclusive_claim_allows_one_process_only(monkeypatch, tmp_path):
    (tmp_path / "frozen-transport-contract.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    gate = threading.Barrier(2); outcomes = []
    def claim():
        gate.wait()
        try:
            pilot._claim(tmp_path, frozen()); outcomes.append("claimed")
        except ValueError:
            outcomes.append("blocked")
    left, right = threading.Thread(target=claim), threading.Thread(target=claim)
    left.start(); right.start(); left.join(); right.join()
    assert sorted(outcomes) == ["blocked", "claimed"]
    assert json.loads((tmp_path / "pilot-execution-claim.json").read_text(encoding="utf-8"))["kind"] == "exclusive_score_blind_pilot_execution"


def test_journal_records_are_atomic_and_reject_torn_or_duplicate_writes(tmp_path):
    gate = threading.Barrier(2); outcomes = []
    def append():
        gate.wait()
        try:
            pilot._append_journal(tmp_path, {"cell_id": "pilot-01", "status": "completed"}); outcomes.append("written")
        except ValueError:
            outcomes.append("blocked")
    left, right = threading.Thread(target=append), threading.Thread(target=append)
    left.start(); right.start(); left.join(); right.join()
    assert sorted(outcomes) == ["blocked", "written"]
    journal = tmp_path / "pilot-journal"
    assert [path.name for path in journal.glob("*.json")] == ["0001-pilot-01.json"]
    (journal / "0002-pilot-02.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        pilot._journal_records(tmp_path)


def test_verify_rejects_reused_completion_evidence(monkeypatch, tmp_path):
    value = frozen(); receipts = []
    for cell in value["cells"]:
        receipts.append({"cell_id": cell["cell_id"], "provider": {"evidence_sha256": "a" * 64, "serialization_proof_sha256": "b" * 64}})
    completed_records(tmp_path, receipts)
    monkeypatch.setattr(verify, "load_frozen", lambda _: value)
    monkeypatch.setattr(verify, "_invocation", lambda _: {})
    monkeypatch.setattr(verify, "_claim", lambda _: {})
    monkeypatch.setattr(verify, "_verify_cell", lambda _work, _frozen, cell: next(item for item in receipts if item["cell_id"] == cell["cell_id"]))
    with pytest.raises(ValueError, match="reused"):
        verify.verify_pilot(tmp_path)


def test_verify_rejects_timeout_boundary_and_missing_three(monkeypatch, tmp_path):
    value = frozen()
    journal = tmp_path / "pilot-journal"; journal.mkdir()
    (journal / "0001-pilot-01.json").write_text(json.dumps({"sequence": 1, "cell_id": "pilot-01", "status": "completed"}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: value)
    monkeypatch.setattr(verify, "_invocation", lambda _: {})
    monkeypatch.setattr(verify, "_claim", lambda _: {})
    with pytest.raises(ValueError, match="exactly three"):
        verify.verify_pilot(tmp_path)
    assert verify._timely(99.999) is True
    assert verify._timely(100) is False
    assert verify._timely(True) is False


def test_development_enablement_requires_verified_pilot(monkeypatch, tmp_path):
    monkeypatch.setattr(enable, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(enable, "verify_pilot", lambda _: (_ for _ in ()).throw(ValueError("pilot failed")))
    with pytest.raises(ValueError, match="pilot failed"):
        enable.enable(tmp_path)
    assert not (tmp_path / "development-enablement.json").exists()


def test_development_enablement_carries_unmatched_label(monkeypatch, tmp_path):
    (tmp_path / "frozen-transport-contract.json").write_text("{}", encoding="utf-8")
    journal = tmp_path / "pilot-journal"; journal.mkdir()
    (journal / "0001-pilot-01.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pilot-execution-claim.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(enable, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(enable, "verify_pilot", lambda _: {"status": "PASS", "cells": 3, "comparison_status": "unmatched_to_primary_32"})
    value = enable.enable(tmp_path)
    assert value["development"]["comparison_status"] == "unmatched_to_primary_32"
    assert value["study"] == study.fingerprint(ROOT / "study.py") and value["development_enabler"] == study.fingerprint(ROOT / "enable_development.py")


def test_verifier_rejects_missing_or_forged_claim_and_invocation_verifier_drift(monkeypatch, tmp_path):
    frozen_contract = tmp_path / "frozen-transport-contract.json"; frozen_contract.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(verify, "runtime_bindings", lambda: {})
    with pytest.raises(ValueError, match="claim"):
        verify._claim(tmp_path)
    claim = {"format_version": 1, "study_id": study.CONTRACT["study_id"], "kind": "exclusive_score_blind_pilot_execution", "contract_sha256": study.sha(ROOT / "study-contract.json"), "frozen_contract_sha256": study.sha(frozen_contract), "runtime": {}, "pid": 0}
    (tmp_path / "pilot-execution-claim.json").write_text(json.dumps(claim), encoding="utf-8")
    with pytest.raises(ValueError, match="claim"):
        verify._claim(tmp_path)
    claim["pid"] = 1; (tmp_path / "pilot-execution-claim.json").write_text(json.dumps(claim), encoding="utf-8")
    assert verify._claim(tmp_path)["pid"] == 1
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    monkeypatch.setattr(verify, "load_frozen", lambda _: frozen())
    monkeypatch.setitem(sys.modules, "run_transport_pilot", pilot)
    pilot._invocation(tmp_path, frozen(), 600)
    invocation = json.loads((tmp_path / "pilot-invocation.json").read_text(encoding="utf-8")); invocation["pilot_verifier"]["sha256"] = "0" * 64
    (tmp_path / "pilot-invocation.json").write_text(json.dumps(invocation), encoding="utf-8")
    with pytest.raises(ValueError, match="invocation"):
        verify._invocation(tmp_path)


def test_invocation_and_development_helper_pins_fail_closed_on_drift(monkeypatch, tmp_path):
    frozen_contract = tmp_path / "frozen-transport-contract.json"; frozen_contract.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "runtime_bindings", lambda: {})
    pilot_record = pilot._invocation(tmp_path, frozen(), 600)
    assert pilot_record["study"] == study.fingerprint(ROOT / "study.py")
    forged_pilot = dict(pilot_record); forged_pilot["study"] = {**forged_pilot["study"], "sha256": "0" * 64}
    with pytest.raises(ValueError, match="Immutable"):
        study.immutable_json(tmp_path / "pilot-invocation.json", forged_pilot)
    (tmp_path / "development-enablement.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(development, "runtime_bindings", lambda: {})
    enablement = {"development": study.CONTRACT["development"]}
    development_record = development._invocation(tmp_path, enablement)
    assert development_record["study"] == study.fingerprint(ROOT / "study.py")
    assert development_record["development_enabler"] == study.fingerprint(ROOT / "enable_development.py")
    development_path = tmp_path / "development-invocation.json"; study.immutable_json(development_path, development_record)
    forged_development = dict(development_record); forged_development["development_enabler"] = {**forged_development["development_enabler"], "sha256": "0" * 64}
    with pytest.raises(ValueError, match="Immutable"):
        study.immutable_json(development_path, forged_development)


def test_development_runner_cannot_cross_the_pilot_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(development, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(development, "enable", lambda _: (_ for _ in ()).throw(ValueError("pilot not verified")))
    monkeypatch.setattr(development, "run_judge", lambda **_: pytest.fail("development must not send before enablement"))
    with pytest.raises(ValueError, match="pilot not verified"):
        development.execute(tmp_path)


def raw_transport_fixture(monkeypatch, tmp_path, *, recovered: int = 0, status: int = 200, finished: int = 20, receipt_run_id: str = "bridge-run"):
    run = tmp_path / "run"; responses = run / "responses"; evidence = responses / "batch-0001.attempt-0001.nous.evidence"; bridge_run = evidence / "bridge-run"
    bridge_run.mkdir(parents=True)
    request = responses / "batch-0001.attempt-0001.nous.request.json"; result = responses / "batch-0001.attempt-0001.nous.result.json"; accepted = responses / "batch-0001.accepted-0001.message.txt"; proof = evidence / "serialization-proof.json"
    prompt = b"frozen effective prompt"
    response_format = {"type": "json_schema", "json_schema": {"name": "hbqrs_judge", "strict": True, "schema": json.loads((book_root() / "schema" / "hbq_judge_response.schema.json").read_text(encoding="utf-8"))}}
    raw_request = {"schema": "codex-nous-tool-free-judge-request-v1", "model": study.CONTRACT["provider"]["model"], "reasoning_effort": "max", "messages": [{"role": "system", "content": "You are a careful HBQ-RS evaluator. Do not use tools or reveal chain-of-thought."}, {"role": "user", "content": prompt.decode()}], "response_format": response_format}
    request.write_text(json.dumps(raw_request), encoding="utf-8"); proof.write_text("{}", encoding="utf-8")
    (bridge_run / "manifest.json").write_text(json.dumps({"run_id": "bridge-run", "requested_model": study.CONTRACT["provider"]["model"], "requested_reasoning_effort": "max"}), encoding="utf-8")
    (bridge_run / "receipt.json").write_text(json.dumps({"run_id": receipt_run_id}), encoding="utf-8")
    (bridge_run / "events.jsonl").write_text(json.dumps({"event_type": "http_attempt", "data": {"status": status, "http_started_monotonic_ns": 10, "http_finished_monotonic_ns": finished}}) + "\n", encoding="utf-8")
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    metadata = {"transport": "nous_chat_completions_mcp_hardened_v2", "requested_provider": "nous", "configured_route_provider": "nous", "requested_model": study.CONTRACT["provider"]["model"], "provider_reported_model": "deepseek/deepseek-v4-flash-0731", "provider_canonical_model": "deepseek/deepseek-v4-flash-20260731", "requested_reasoning_effort": "max", "provider_reported_reasoning_effort": None, "tool_mode": "judge", "tool_free": True, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": recovered, "cross_process_provider_serialization_proven": True, "serialization_proof_path": str(proof), "serialization_proof_sha256": verify._artifact(run, proof)["sha256"], "evidence_path": str(bridge_run), "evidence_validation": {"valid": True}}
    response = {"verdicts": []}; metadata["judge_request_sha256"] = hashlib.sha256(canonical(raw_request)).hexdigest(); metadata["judge_response_schema_sha256"] = hashlib.sha256(canonical(response_format)).hexdigest(); metadata["judge_result_sha256"] = hashlib.sha256(canonical(response)).hexdigest()
    result.write_text(json.dumps({"schema": "codex-nous-tool-free-judge-result-v1", "result": response, "metadata": metadata}), encoding="utf-8")
    accepted.write_text(json.dumps(response), encoding="utf-8")
    provider = {"provider_artifacts": {"judge_request": verify._artifact(run, request), "judge_result": verify._artifact(run, result), "serialization_proof": verify._artifact(run, proof), "evidence_tree": verify._tree(run, evidence)}}
    provider["evidence_sha256"] = hashlib.sha256(verify._json_bytes({"result": response, "metadata": metadata})).hexdigest(); provider["serialization_proof_sha256"] = metadata["serialization_proof_sha256"]
    monkeypatch.setattr(verify, "_validate_provider_artifacts", lambda *_: None)
    monkeypatch.setattr(verify, "_bridge", lambda: types.SimpleNamespace(validate_evidence=lambda _: {"valid": True}, serialization_proof_status=lambda *_args, **_kwargs: types.SimpleNamespace(valid=True), canonical_bytes=canonical, sha256_bytes=lambda value: hashlib.sha256(value).hexdigest()))
    return run, {"provider": provider, "response_artifact": verify._artifact(run, accepted), "response_sha256": hashlib.sha256(accepted.read_bytes()).hexdigest()}, prompt


def test_raw_transport_binds_bridge_result_receipt_http_and_session(monkeypatch, tmp_path):
    run, checkpoint, prompt = raw_transport_fixture(monkeypatch, tmp_path)
    raw = verify._raw_transport(run, checkpoint, prompt)
    assert raw["evidence"]["run_id"] == "bridge-run" and raw["http"]["status"] == 200


def test_bridge_metadata_hash_uses_compact_canonical_bytes_not_runner_pretty_json(monkeypatch):
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    monkeypatch.setattr(verify, "_bridge", lambda: types.SimpleNamespace(canonical_bytes=canonical, sha256_bytes=lambda value: hashlib.sha256(value).hexdigest()))
    value = {"schema": "x", "messages": [{"role": "user", "content": "x"}]}
    assert verify._bridge_hash(value) == hashlib.sha256(canonical(value)).hexdigest()
    assert verify._bridge_hash(value) != hashlib.sha256(verify._json_bytes(value)).hexdigest()


@pytest.mark.parametrize("kind", ["hmac", "recovery", "http", "timing", "session", "raw"])
def test_raw_transport_rejects_evidence_recovery_status_or_session_tamper(monkeypatch, tmp_path, kind):
    run, checkpoint, prompt = raw_transport_fixture(monkeypatch, tmp_path, recovered=1 if kind == "recovery" else 0, status=524 if kind == "http" else 200, finished=5 if kind == "timing" else 20, receipt_run_id="forged" if kind == "session" else "bridge-run")
    if kind == "hmac":
        monkeypatch.setattr(verify, "_bridge", lambda: types.SimpleNamespace(validate_evidence=lambda _: (_ for _ in ()).throw(ValueError("invalid HMAC")), serialization_proof_status=lambda *_args, **_kwargs: types.SimpleNamespace(valid=True)))
    if kind == "raw":
        path = run / "responses" / "batch-0001.attempt-0001.nous.result.json"
        path.write_text(json.dumps({"forged": True}), encoding="utf-8")
    with pytest.raises(ValueError):
        verify._raw_transport(run, checkpoint, prompt)


def test_raw_transport_rejects_one_sided_accepted_response_divergence(monkeypatch, tmp_path):
    run, checkpoint, prompt = raw_transport_fixture(monkeypatch, tmp_path)
    accepted = run / "responses" / "batch-0001.accepted-0001.message.txt"
    accepted.write_text(json.dumps({"verdicts": ["forged"]}), encoding="utf-8")
    checkpoint["response_artifact"] = verify._artifact(run, accepted)
    checkpoint["response_sha256"] = hashlib.sha256(accepted.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="diverges"):
        verify._raw_transport(run, checkpoint, prompt)
