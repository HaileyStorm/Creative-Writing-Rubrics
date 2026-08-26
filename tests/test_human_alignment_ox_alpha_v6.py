"""Regression coverage for the Ox Alpha v6 transport successor."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types

import pytest

from hbqrs.paths import book_root
from tests import _ox_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v6"
UNCERTAIN_ROOT = Path(os.environ.get("CWR_OX_V5_UNCERTAIN_ROOT", r"C:\Users\Haile\Documents\cwr-ox-alpha-v5-cap1-pilot-20260821-a037ac8"))
CURRENT_CAP1_PROOF = Path(os.environ.get("CWR_OX_CAP1_ZERO_COST_PROOF", r"C:\Users\Haile\Documents\cwr-ox-alpha-zero-cost-proof-cap1-20260821.json"))


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules[spec.name] = module; sys.modules.update(aliases or {})
    try: spec.loader.exec_module(module)
    finally:
        for key, value in prior.items():
            if value is None: sys.modules.pop(key, None)
            else: sys.modules[key] = value
    return module


study = historical_runtime.install(load("ox_alpha_v6_study", "study.py"))
pilot = load("ox_alpha_v6_pilot", "run_transport_pilot.py", {"study": study})
verify = load("ox_alpha_v6_verify", "verify_transport_pilot.py", {"study": study})


def frozen() -> dict:
    return {"uncertain_v5": {"accepted_global_ids": {"session_id": "v5-session", "receipt_id": "v5-receipt", "logical_request_id": "v5-logical"}}, "cells": [{"cell_id": f"ox-alpha-v6-{number:02d}", "item_id": f"item-{number}", "question_ids": [str(question) for question in range(4)]} for number in range(1, 4)]}


def terminal_boundary() -> dict:
    return {"event_type": "judge_boundary", "data": {"request_schema": study.CONTRACT["transport_pilot"]["required_request_schema"], "model_policy": {"provider_canonical_model": study.CONTRACT["provider"]["provider_canonical_model"], "requested_model": study.CONTRACT["provider"]["model"], "required_reasoning_effort": "max"}, "transport_policy": {**pilot.NOUS_TRANSPORT_POLICY, "max_physical_attempts_per_logical_request": 1}, "zero_tools": True}}


def test_contract_is_four_leaf_serial_cap1_and_score_blind():
    policy = study.CONTRACT["transport_pilot"]
    assert {key: policy[key] for key in ("cells", "batch_size", "question_count", "batch_attempts", "workers", "timeout_seconds", "maximum_http_seconds_exclusive")} == {"cells": 3, "batch_size": 4, "question_count": 4, "batch_attempts": 1, "workers": 1, "timeout_seconds": 240, "maximum_http_seconds_exclusive": 150}
    text = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("study-contract.json", "run_transport_pilot.py", "verify_transport_pilot.py"))
    assert "score.json" not in text and "HANNA ratings" not in text
    assert policy["required_shared_runner_option"] == "max_physical_http_attempts_per_logical_request=1"
    assert "Only a normal launcher return with a stable sealed Judge non-2xx receipt" in policy["failure_rule"]
    assert "ambiguous, recovered, non-cap-1, validation-drift, or duplicate-completion" in policy["failure_rule"]
    assert policy["sla_revision_evidence"] == "The raw-HTTP ceiling alone changes from below 100 to below 150 seconds. Independent v4 eight-leaf evidence took 111.8683733 seconds and the exact v5 four-leaf predecessor took 111.9468465 seconds, demonstrating an endpoint floor rather than an avoidable batch-size delay."


def test_raw_http_sla_is_exclusive_at_150_seconds():
    assert verify._within_raw_http_sla(149_999_999_999) is True
    assert verify._within_raw_http_sla(150_000_000_000) is False
    assert verify._within_raw_http_sla(0) is False


def test_parent_package_is_exact_and_hash_drift_fails_closed(monkeypatch):
    parent = study._parent_v5()
    assert parent.CONTRACT["study_id"] == "hbq-human-alignment-supplemental-providers-ox-alpha-v5"
    changed = dict(study.V5_FILES); changed["study.py"] = "0" * 64
    monkeypatch.setattr(study, "V5_FILES", changed)
    with pytest.raises(ValueError, match="parent file drifted"):
        study._parent_v5()


def test_contract_rejects_predecessor_or_sla_rationale_drift(monkeypatch):
    contract = study.read_json(study.CONTRACT_PATH)
    altered = {**contract, "uncertain_v5": {**contract["uncertain_v5"], "later_mutation_forbidden": False}}
    monkeypatch.setattr(study, "read_json", lambda _: altered)
    with pytest.raises(ValueError, match="contract drifted"):
        study.load_contract()


def test_uncertain_v5_exact_root_proves_one_accepted_cap1_slow_http():
    if not UNCERTAIN_ROOT.is_dir(): pytest.skip("set CWR_OX_V5_UNCERTAIN_ROOT for immutable predecessor verification")
    observed = study.uncertain_v5_commitments(UNCERTAIN_ROOT)
    assert observed["historical_http_attempts"] == [{"status": 200, "duration_ns": 111_946_846_500}]
    assert observed["status"] == "permanently_blocked_uncertain"
    assert observed["journal_present"] is False
    assert set(observed["accepted_global_ids"]) == {"session_id", "receipt_id", "logical_request_id"}
    assert not (UNCERTAIN_ROOT / "pilot-receipts").exists()
    assert not (UNCERTAIN_ROOT / "runs" / "pilot" / "ox-alpha-v5-02").exists()


def test_uncertain_v5_missing_or_extra_evidence_fails_closed(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="unavailable|extra, missing, or drifted"):
        study.uncertain_v5_commitments(tmp_path)
    if not UNCERTAIN_ROOT.is_dir(): pytest.skip("set CWR_OX_V5_UNCERTAIN_ROOT for immutable predecessor verification")
    original = study._tree
    monkeypatch.setattr(study, "_tree", lambda root: {"files": original(root)["files"] + 1, "sha256": original(root)["sha256"]})
    with pytest.raises(ValueError, match="extra, missing, or drifted"):
        study.uncertain_v5_commitments(UNCERTAIN_ROOT)


@pytest.mark.skip(reason="archived pending a genuinely fresh zero-cost proof; replay must not bypass current freshness")
def test_current_cap1_proof_freezes_and_reloads_without_provider_contact():
    if not UNCERTAIN_ROOT.is_dir() or not CURRENT_CAP1_PROOF.is_file():
        pytest.skip("set CWR_OX_V5_UNCERTAIN_ROOT and CWR_OX_CAP1_ZERO_COST_PROOF for the real no-provider freeze/reload check")
    with tempfile.TemporaryDirectory(prefix="cwr-ox-v6-freeze-") as directory:
        work = Path(directory) / "work"
        frozen = study.freeze_work(UNCERTAIN_ROOT, CURRENT_CAP1_PROOF, work)
        assert study.load_frozen(work) == frozen
        assert (work / study.FROZEN_NAME).is_file()
        assert not (work / "runs").exists()


def test_cells_are_first_four_v5_leaves_without_reselection():
    if not UNCERTAIN_ROOT.is_dir(): pytest.skip("set CWR_OX_V5_UNCERTAIN_ROOT for immutable predecessor verification")
    _, cells, _ = study._cells(UNCERTAIN_ROOT)
    expected = ["core.task_and_brief_fidelity.intervention", "core.task_and_brief_fidelity.completion_flag", "core.task_and_brief_fidelity.no_meta_substitution", "core.length_and_scope_fit.form"]
    assert [cell["question_ids"] for cell in cells] == [expected, expected, expected]
    assert [cell["item_id"] for cell in cells] == ["hanna-827", "hanna-957", "hanna-201"]


def test_real_v5_evidence_parent_selects_judge_leaf_and_provelock_sibling():
    if not UNCERTAIN_ROOT.is_dir(): pytest.skip("set CWR_OX_V5_UNCERTAIN_ROOT for immutable predecessor verification")
    evidence = UNCERTAIN_ROOT / "runs" / "pilot" / "ox-alpha-v5-01" / "responses" / "batch-0001.attempt-0001.nous.evidence"
    proof = next(evidence.rglob("serialization-proof.json"))
    judge, prove = verify._judge_leaf(evidence, proof)
    assert judge.name == "20260822T024208.242298Z-a3211ed4e977408a824ba17cfe7ab30c"
    assert prove.name == "20260822T024201.781828Z-a2763cb2a70044bcbb6fbbace10a2a48"
    events = [json.loads(line) for line in (judge / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    verify._assert_proof_binding(events, proof)


def test_evidence_leaf_selection_rejects_ambiguous_or_unbound_synthetic_tree(tmp_path):
    evidence = tmp_path / "parent"; prove = evidence / "prove"; judge = evidence / "judge"
    prove.mkdir(parents=True); judge.mkdir()
    proof = prove / "serialization-proof.json"; proof.write_text("{}", encoding="utf-8")
    (prove / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (prove / "events.jsonl").write_text(json.dumps({"event_type": "serialization_proof"}) + "\n", encoding="utf-8")
    (judge / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (judge / "events.jsonl").write_text(json.dumps({"event_type": "judge_boundary"}) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 200}}) + "\n", encoding="utf-8")
    assert verify._judge_leaf(evidence, proof) == (judge, prove)
    extra = evidence / "extra"; extra.mkdir()
    (extra / "events.jsonl").write_text(json.dumps({"event_type": "other"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="one Judge leaf"):
        verify._judge_leaf(evidence, proof)


def test_success_evidence_rejects_provelock_http_attempt(tmp_path):
    evidence = tmp_path / "parent"; prove = evidence / "prove"; judge = evidence / "judge"; prove.mkdir(parents=True); judge.mkdir()
    proof = prove / "serialization-proof.json"; proof.write_text("{}", encoding="utf-8")
    (prove / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (prove / "events.jsonl").write_text(json.dumps({"event_type": "serialization_proof"}) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 200}}) + "\n", encoding="utf-8")
    (judge / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (judge / "events.jsonl").write_text(json.dumps({"event_type": "judge_boundary"}) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 200}}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one Judge HTTP attempt"):
        verify._judge_leaf(evidence, proof)


def test_external_roots_reject_repo_and_overlap():
    with pytest.raises(ValueError, match="outside the repository"):
        study._external_disjoint(study.REPO_ROOT)
    external = Path(tempfile.gettempdir()) / "cwr-ox-v5-external-root-test"
    with pytest.raises(ValueError, match="disjoint"):
        study._external_disjoint(external, external / "child")


def test_executor_passes_cap1_four_leaf_and_strict_timeout(monkeypatch, tmp_path):
    source, prompt, task = (tmp_path / name for name in ("source.md", "prompt.md", "task-contract.json"))
    source.write_text("story", encoding="utf-8"); prompt.write_text("prompt", encoding="utf-8"); task.write_text("{}", encoding="utf-8")
    called: dict[str, object] = {}
    monkeypatch.setattr(pilot, "input_paths", lambda *_: (source, prompt, task)); monkeypatch.setattr(pilot, "run_judge", lambda **kwargs: called.update(kwargs))
    verifier = types.ModuleType("verify_transport_pilot"); verifier.verify_cell = lambda *_: {"run": {}, "checkpoint": {}, "logical_request_id": "logical", "payload": {}, "raw_evidence": {}, "provider_receipt": {}}
    prior = sys.modules.get("verify_transport_pilot"); sys.modules["verify_transport_pilot"] = verifier
    try: pilot._execute_one(tmp_path, frozen(), frozen()["cells"][0])
    finally:
        if prior is None: sys.modules.pop("verify_transport_pilot", None)
        else: sys.modules["verify_transport_pilot"] = prior
    assert called["max_physical_http_attempts_per_logical_request"] == 1
    assert called["batch_attempts"] == 1 and called["batch_size"] == 4 and called["timeout"] == 240 and called["resume"] is False


def test_outer_timeout_is_uncertain_and_permanent(monkeypatch, tmp_path):
    (tmp_path / study.FROZEN_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen()); monkeypatch.setattr(pilot, "assert_launch_freshness", lambda _: None)
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {}); monkeypatch.setattr(pilot, "fingerprint", lambda _: {"name": "pilot-invocation.json"}); monkeypatch.setattr(pilot, "_claim", lambda _: None)
    monkeypatch.setattr(pilot, "_execute_one", lambda *_: (_ for _ in ()).throw(RuntimeError("Nous bridge launcher timed out")))
    with pytest.raises(RuntimeError, match="timed out"): pilot.execute(tmp_path)
    assert (tmp_path / "pilot-uncertain.json").is_file() and not (tmp_path / "pilot-journal").exists()
    with pytest.raises(ValueError, match="immutable evidence"): pilot.execute(tmp_path)


@pytest.mark.parametrize("duplicate", ["session_id", "receipt_id", "logical_request_id"])
def test_execute_records_global_duplicate_as_uncertain(monkeypatch, tmp_path, duplicate):
    (tmp_path / study.FROZEN_NAME).write_text("{}", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen()); monkeypatch.setattr(pilot, "assert_launch_freshness", lambda _: None)
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {}); monkeypatch.setattr(pilot, "fingerprint", lambda path: {"name": path.name, "bytes": 1, "sha256": "a" * 64}); monkeypatch.setattr(pilot, "_claim", lambda _: None)
    monkeypatch.setattr(pilot, "_execute_one", lambda _work, _frozen, cell: {"logical_request_id": f"logical-{cell['cell_id']}"})
    verifier = types.ModuleType("verify_transport_pilot")
    def fail_global(work):
        calls.append(str(work)); raise ValueError(f"Ox v6 reuses a provider {duplicate}")
    verifier.verify_pilot = fail_global
    prior = sys.modules.get("verify_transport_pilot"); sys.modules["verify_transport_pilot"] = verifier
    try:
        with pytest.raises(ValueError, match="global verification failed"):
            pilot.execute(tmp_path)
    finally:
        if prior is None: sys.modules.pop("verify_transport_pilot", None)
        else: sys.modules["verify_transport_pilot"] = prior
    uncertain = study.read_json(tmp_path / "pilot-uncertain.json")
    assert calls == [str(tmp_path)]
    assert uncertain["reason"] == "completed_pilot_global_verification_failed:ValueError"
    assert len(list((tmp_path / "pilot-journal").glob("*.json"))) == 3


def test_terminal_failure_requires_stable_sealed_tree(monkeypatch, tmp_path):
    evidence = tmp_path / "runs" / "pilot" / "ox-alpha-v6-01" / "responses" / "batch-0001.attempt-0001.nous.evidence"; prove = evidence / "prove"; judge = evidence / "judge"; prove.mkdir(parents=True); judge.mkdir()
    (prove / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (prove / "events.jsonl").write_text(json.dumps({"event_type": "serialization_proof"}) + "\n", encoding="utf-8")
    (judge / "receipt.json").write_text(json.dumps({"status": "failure", "sealed_at": "now", "terminal_chain_sha256": "a", "events_sha256": "b"}), encoding="utf-8")
    (judge / "events.jsonl").write_text(json.dumps(terminal_boundary()) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 524}}) + "\n", encoding="utf-8")
    monkeypatch.setattr(pilot.time, "sleep", lambda _: None)
    assert pilot._terminal_failure_seal(tmp_path, frozen()["cells"][0])["quiescence"] == "launcher_returned_and_terminal_tree_stable"
    snapshots = iter(({"files": 2, "sha256": "a"}, {"files": 3, "sha256": "b"})); monkeypatch.setattr(pilot, "_tree", lambda _: next(snapshots))
    with pytest.raises(ValueError, match="not stable"): pilot._terminal_failure_seal(tmp_path, frozen()["cells"][0])


def test_terminal_failure_rejects_extra_or_provelock_http(monkeypatch, tmp_path):
    evidence = tmp_path / "runs" / "pilot" / "ox-alpha-v6-01" / "responses" / "batch-0001.attempt-0001.nous.evidence"; prove = evidence / "prove"; judge = evidence / "judge"; prove.mkdir(parents=True); judge.mkdir()
    (prove / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (prove / "events.jsonl").write_text(json.dumps({"event_type": "serialization_proof"}) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 200}}) + "\n", encoding="utf-8")
    (judge / "receipt.json").write_text(json.dumps({"status": "failure", "sealed_at": "now", "terminal_chain_sha256": "a", "events_sha256": "b"}), encoding="utf-8")
    (judge / "events.jsonl").write_text(json.dumps(terminal_boundary()) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 524}}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one Judge HTTP attempt"):
        pilot._terminal_failure_seal(tmp_path, frozen()["cells"][0])


def test_terminal_failure_rejects_missing_or_noncap1_boundary_policy(monkeypatch, tmp_path):
    evidence = tmp_path / "runs" / "pilot" / "ox-alpha-v6-01" / "responses" / "batch-0001.attempt-0001.nous.evidence"; prove = evidence / "prove"; judge = evidence / "judge"; prove.mkdir(parents=True); judge.mkdir()
    (prove / "receipt.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (prove / "events.jsonl").write_text(json.dumps({"event_type": "serialization_proof"}) + "\n", encoding="utf-8")
    (judge / "receipt.json").write_text(json.dumps({"status": "failure", "sealed_at": "now", "terminal_chain_sha256": "a", "events_sha256": "b"}), encoding="utf-8")
    bad = terminal_boundary(); bad["data"] = {**bad["data"], "transport_policy": {**bad["data"]["transport_policy"], "max_physical_attempts_per_logical_request": 2}}
    (judge / "events.jsonl").write_text(json.dumps(bad) + "\n" + json.dumps({"event_type": "http_attempt", "data": {"status": 524}}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact request-v2 cap-1 transport/model policy"):
        pilot._terminal_failure_seal(tmp_path, frozen()["cells"][0])


def test_unsealed_terminal_policy_failure_becomes_uncertain(monkeypatch, tmp_path):
    (tmp_path / study.FROZEN_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen()); monkeypatch.setattr(pilot, "assert_launch_freshness", lambda _: None)
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {}); monkeypatch.setattr(pilot, "fingerprint", lambda _: {"name": "pilot-invocation.json"}); monkeypatch.setattr(pilot, "_claim", lambda _: None)
    monkeypatch.setattr(pilot, "_execute_one", lambda *_: (_ for _ in ()).throw(ValueError("non-cap-1 terminal boundary")))
    monkeypatch.setattr(pilot, "_terminal_failure_seal", lambda *_: (_ for _ in ()).throw(ValueError("exact request-v2 cap-1 transport/model policy")))
    with pytest.raises(ValueError, match="uncertain and blocked"):
        pilot.execute(tmp_path)
    assert study.read_json(tmp_path / "pilot-uncertain.json")["reason"] == "terminal_bridge_quiescence_unproven:ValueError"


def test_verifier_rejects_duplicate_sessions_receipts_or_logical_ids(monkeypatch, tmp_path):
    value = frozen(); journal = tmp_path / "pilot-journal"; journal.mkdir(); receipts = tmp_path / "pilot-receipts"; receipts.mkdir(); invocation = {"name": "pilot-invocation.json", "bytes": 1, "sha256": "a" * 64}; proofs = []
    for number, cell in enumerate(value["cells"], 1):
        receipt = receipts / f"{cell['cell_id']}.json"; receipt.write_text("{}", encoding="utf-8")
        proof = {"run": {}, "checkpoint": {}, "logical_request_id": f"logical-{number}", "payload": {}, "raw_evidence": {}, "provider_receipt": {}, "session_id": "same", "receipt_id": "same"}; proofs.append(proof)
        (journal / f"{number:04d}-{cell['cell_id']}.json").write_text(json.dumps({"sequence": number, "cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation, "receipt": {"name": receipt.name, "bytes": 2, "sha256": "b" * 64}, "logical_request_id": proof["logical_request_id"]}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: value); monkeypatch.setattr(verify, "_invocation", lambda _: {}); monkeypatch.setattr(verify, "_claim", lambda _: {})
    monkeypatch.setattr(verify, "fingerprint", lambda path: invocation if path.name == "pilot-invocation.json" else {"name": path.name, "bytes": 2, "sha256": "b" * 64})
    monkeypatch.setattr(verify, "verify_cell", lambda _w, _f, cell: next(proof for proof, candidate in zip(proofs, value["cells"]) if candidate == cell))
    with pytest.raises(ValueError, match="reuses"): verify.verify_pilot(tmp_path)


@pytest.mark.parametrize("duplicate", ["session_id", "receipt_id", "logical_request_id"])
def test_verifier_rejects_accepted_v5_global_id(monkeypatch, tmp_path, duplicate):
    value = frozen(); journal = tmp_path / "pilot-journal"; journal.mkdir(); proofs = []
    for number, cell in enumerate(value["cells"], 1):
        proof = {"run": {}, "checkpoint": {}, "logical_request_id": f"logical-{number}", "payload": {}, "raw_evidence": {}, "provider_receipt": {}, "session_id": f"session-{number}", "receipt_id": f"receipt-{number}"}
        if number == 1:
            proof[duplicate] = value["uncertain_v5"]["accepted_global_ids"][duplicate]
        proofs.append(proof)
        (journal / f"{number:04d}-{cell['cell_id']}.json").write_text(json.dumps({"sequence": number, "status": "completed"}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: value); monkeypatch.setattr(verify, "_invocation", lambda _: {}); monkeypatch.setattr(verify, "_claim", lambda _: {})
    monkeypatch.setattr(verify, "verify_cell", lambda _w, _f, cell: next(proof for proof, candidate in zip(proofs, value["cells"]) if candidate == cell))
    with pytest.raises(ValueError, match="accepted-v5"):
        verify.verify_pilot(tmp_path)


def test_verifier_rejects_tampered_receipt_body(monkeypatch, tmp_path):
    value = frozen(); journal = tmp_path / "pilot-journal"; journal.mkdir(); receipts = tmp_path / "pilot-receipts"; receipts.mkdir(); proofs = []
    for number, cell in enumerate(value["cells"], 1):
        proof = {"run": {"n": number}, "checkpoint": {}, "logical_request_id": f"logical-{number}", "payload": {}, "raw_evidence": {}, "provider_receipt": {}, "session_id": f"session-{number}", "receipt_id": f"receipt-{number}"}; proofs.append(proof)
        (receipts / f"{cell['cell_id']}.json").write_text(json.dumps({"tampered_or_unbound": True}), encoding="utf-8")
        (journal / f"{number:04d}-{cell['cell_id']}.json").write_text(json.dumps({"sequence": number, "status": "completed"}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: value); monkeypatch.setattr(verify, "_invocation", lambda _: {}); monkeypatch.setattr(verify, "_claim", lambda _: {})
    monkeypatch.setattr(verify, "verify_cell", lambda _w, _f, cell: next(proof for proof, candidate in zip(proofs, value["cells"]) if candidate == cell))
    with pytest.raises(ValueError, match="semantic body drifted"):
        verify.verify_pilot(tmp_path)
