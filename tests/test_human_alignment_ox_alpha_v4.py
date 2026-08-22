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


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v4"
FAILED_ROOT = Path(os.environ.get("CWR_OX_V3_FAILED_ROOT", r"C:\Users\Haile\Documents\cwr-ox-alpha-v3-cap1-pilot-20260821-e807c5d"))


def load(name: str, filename: str, aliases: dict[str, object] | None = None):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    prior = {key: sys.modules.get(key) for key in aliases or {}}
    sys.modules[spec.name] = module
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


study = load("ox_alpha_v4_study", "study.py")
pilot = load("ox_alpha_v4_pilot", "run_transport_pilot.py", {"study": study})
verify = load("ox_alpha_v4_verify", "verify_transport_pilot.py", {"study": study})


def frozen() -> dict:
    return {"cells": [{"cell_id": f"ox-alpha-v4-{number:02d}", "item_id": f"item-{number}", "question_ids": [str(question) for question in range(8)]} for number in range(1, 4)]}


def test_contract_is_eight_leaf_serial_cap1_and_score_blind():
    policy = study.CONTRACT["transport_pilot"]
    assert {key: policy[key] for key in ("cells", "batch_size", "question_count", "batch_attempts", "workers", "timeout_seconds", "maximum_http_seconds_exclusive")} == {"cells": 3, "batch_size": 8, "question_count": 8, "batch_attempts": 1, "workers": 1, "timeout_seconds": 240, "maximum_http_seconds_exclusive": 100}
    assert policy["required_shared_runner_option"] == "max_physical_http_attempts_per_logical_request=1"
    text = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in ("study-contract.json", "run_transport_pilot.py", "verify_transport_pilot.py"))
    assert "score.json" not in text and "HANNA ratings" not in text
    assert "No retry, escalation, paid route, DSPy, or human route follows" in policy["failure_rule"]


def test_parent_package_tree_is_exact_and_parent_hash_drift_fails_closed(monkeypatch):
    parent = study._parent_v3()
    assert parent.CONTRACT["study_id"] == "hbq-human-alignment-supplemental-providers-ox-alpha-v3"
    readme = (study.PARENT_ROOT / "README.md").read_text(encoding="utf-8")
    assert "parent launcher timed out" in readme and "127.808 seconds" in readme and "No result was accepted" in readme
    changed = dict(study.CONTRACT)
    changed["parent_v3"] = {**changed["parent_v3"], "files": {**changed["parent_v3"]["files"], "study.py": "0" * 64}}
    monkeypatch.setattr(study, "CONTRACT", changed)
    with pytest.raises(ValueError, match="parent file drifted"):
        study._parent_v3()


def test_failed_v3_exact_root_proves_one_cap1_timeout_and_permanent_closure():
    if not FAILED_ROOT.is_dir():
        pytest.skip("set CWR_OX_V3_FAILED_ROOT for immutable predecessor verification")
    observed = study.failed_v3_commitments(FAILED_ROOT)
    assert observed["accepted_result"] is False
    assert observed["historical_http_attempts"] == [{"status": 524, "duration_ns": 127_808_027_500}]


def test_failed_v3_missing_or_drifted_root_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="unavailable|drifted"):
        study.failed_v3_commitments(tmp_path)


def test_failed_v3_rejects_extra_terminal_evidence(monkeypatch):
    if not FAILED_ROOT.is_dir():
        pytest.skip("set CWR_OX_V3_FAILED_ROOT for immutable predecessor verification")
    original = study._tree
    def forged(path: Path, **kwargs):
        result = original(path, **kwargs)
        if path.resolve() == FAILED_ROOT.resolve() and not kwargs.get("excluded"):
            return {"files": result["files"] + 1, "sha256": result["sha256"]}
        return result
    monkeypatch.setattr(study, "_tree", forged)
    with pytest.raises(ValueError, match="extra, missing, or drifted"):
        study.failed_v3_commitments(FAILED_ROOT)


def test_external_roots_reject_repo_and_overlap():
    with pytest.raises(ValueError, match="outside the repository"):
        study._external_disjoint(study.REPO_ROOT)
    external = Path(tempfile.gettempdir()) / "cwr-ox-v4-external-root-test"
    with pytest.raises(ValueError, match="disjoint"):
        study._external_disjoint(external, external / "child")


def test_executor_passes_cap1_eight_leaf_and_strict_timeout(monkeypatch, tmp_path):
    source, prompt, task = (tmp_path / name for name in ("source.md", "prompt.md", "task-contract.json"))
    source.write_text("story", encoding="utf-8"); prompt.write_text("prompt", encoding="utf-8"); task.write_text("{}", encoding="utf-8")
    cell = frozen()["cells"][0]
    called: dict[str, object] = {}
    monkeypatch.setattr(pilot, "input_paths", lambda *_: (source, prompt, task))
    monkeypatch.setattr(pilot, "run_judge", lambda **kwargs: called.update(kwargs))
    verifier = types.ModuleType("verify_transport_pilot")
    verifier.verify_cell = lambda *_: {"run": {}, "checkpoint": {}, "logical_request_id": "logical", "payload": {}, "raw_evidence": {}, "provider_receipt": {}}
    prior = sys.modules.get("verify_transport_pilot"); sys.modules["verify_transport_pilot"] = verifier
    try:
        pilot._execute_one(tmp_path, frozen(), cell)
    finally:
        if prior is None: sys.modules.pop("verify_transport_pilot", None)
        else: sys.modules["verify_transport_pilot"] = prior
    assert called["max_physical_http_attempts_per_logical_request"] == 1
    assert called["batch_attempts"] == 1 and called["batch_size"] == 8 and called["timeout"] == 240 and called["resume"] is False


def test_failure_is_journaled_once_and_closes_root(monkeypatch, tmp_path):
    (tmp_path / study.FROZEN_NAME).write_text("{}", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(pilot, "assert_launch_freshness", lambda _: None)
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {})
    monkeypatch.setattr(pilot, "fingerprint", lambda _: {"name": "pilot-invocation.json"})
    monkeypatch.setattr(pilot, "_claim", lambda _: None)
    monkeypatch.setattr(pilot, "_execute_one", lambda *_: calls.append("sent") or (_ for _ in ()).throw(RuntimeError("timeout")))
    monkeypatch.setattr(pilot, "_terminal_failure_seal", lambda *_: {"quiescence": "launcher_returned_and_terminal_tree_stable"})
    with pytest.raises(RuntimeError, match="timeout"):
        pilot.execute(tmp_path)
    assert calls == ["sent"]
    with pytest.raises(ValueError, match="immutable evidence"):
        pilot.execute(tmp_path)
    assert calls == ["sent"]


def test_outer_timeout_is_uncertain_not_a_permanent_close(monkeypatch, tmp_path):
    (tmp_path / study.FROZEN_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pilot, "load_frozen", lambda _: frozen())
    monkeypatch.setattr(pilot, "assert_launch_freshness", lambda _: None)
    monkeypatch.setattr(pilot, "_invocation", lambda *_: {})
    monkeypatch.setattr(pilot, "fingerprint", lambda _: {"name": "pilot-invocation.json"})
    monkeypatch.setattr(pilot, "_claim", lambda _: None)
    monkeypatch.setattr(pilot, "_execute_one", lambda *_: (_ for _ in ()).throw(RuntimeError("Nous bridge launcher timed out")))
    with pytest.raises(RuntimeError, match="timed out"):
        pilot.execute(tmp_path)
    assert (tmp_path / "pilot-uncertain.json").is_file()
    assert not (tmp_path / "pilot-journal").exists()
    with pytest.raises(ValueError, match="immutable evidence"):
        pilot.execute(tmp_path)


def test_terminal_failure_requires_stable_sealed_tree(monkeypatch, tmp_path):
    evidence = tmp_path / "runs" / "pilot" / "ox-alpha-v4-01" / "responses" / "batch-0001.attempt-0001.nous.evidence" / "child"
    evidence.mkdir(parents=True)
    (evidence / "receipt.json").write_text(json.dumps({"status": "failure", "sealed_at": "now", "terminal_chain_sha256": "a", "events_sha256": "b"}), encoding="utf-8")
    (evidence / "events.jsonl").write_text(json.dumps({"event_type": "http_attempt", "data": {"status": 524}}) + "\n", encoding="utf-8")
    monkeypatch.setattr(pilot.time, "sleep", lambda _: None)
    cell = frozen()["cells"][0]
    assert pilot._terminal_failure_seal(tmp_path, cell)["quiescence"] == "launcher_returned_and_terminal_tree_stable"
    snapshots = iter(({"files": 2, "sha256": "a"}, {"files": 3, "sha256": "b"}))
    monkeypatch.setattr(pilot, "_tree", lambda _: next(snapshots))
    with pytest.raises(ValueError, match="not stable"):
        pilot._terminal_failure_seal(tmp_path, cell)


def test_historical_freshness_is_checked_at_invocation_time_only(monkeypatch):
    frozen_value = {"failed_v3": {"work_dir": "failed"}, "zero_cost_proof": {"path": "proof", "freshness_checked_at": "2026-08-22T01:00:00+00:00", "marker": "bound"}}
    calls: list[str] = []
    monkeypatch.setattr(study, "_cells", lambda _: (object(), [], []))
    monkeypatch.setattr(study, "_fresh_zero_proof", lambda _parent, _path, checked_at: calls.append(checked_at) or {"path": "proof", "marker": "bound"})
    study.assert_invocation_freshness(frozen_value, "2026-08-22T02:00:00+00:00")
    assert calls == ["2026-08-22T02:00:00+00:00"]


def test_verifier_rejects_duplicate_sessions_receipts_or_logical_ids(monkeypatch, tmp_path):
    value = frozen(); journal = tmp_path / "pilot-journal"; journal.mkdir(); receipts = tmp_path / "pilot-receipts"; receipts.mkdir()
    invocation = {"name": "pilot-invocation.json", "bytes": 1, "sha256": "a" * 64}
    proofs = []
    for number, cell in enumerate(value["cells"], 1):
        receipt = receipts / f"{cell['cell_id']}.json"; receipt.write_text("{}", encoding="utf-8")
        proof = {"run": {}, "checkpoint": {}, "logical_request_id": f"logical-{number}", "payload": {}, "raw_evidence": {}, "provider_receipt": {}, "session_id": "same", "receipt_id": "same"}
        proofs.append(proof)
        (journal / f"{number:04d}-{cell['cell_id']}.json").write_text(json.dumps({"sequence": number, "cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation, "receipt": {"name": receipt.name, "bytes": 2, "sha256": "b" * 64}, "logical_request_id": proof["logical_request_id"]}), encoding="utf-8")
    monkeypatch.setattr(verify, "load_frozen", lambda _: value)
    monkeypatch.setattr(verify, "_invocation", lambda _: {})
    monkeypatch.setattr(verify, "_claim", lambda _: {})
    monkeypatch.setattr(verify, "fingerprint", lambda path: invocation if path.name == "pilot-invocation.json" else {"name": path.name, "bytes": 2, "sha256": "b" * 64})
    monkeypatch.setattr(verify, "verify_cell", lambda _w, _f, cell: next(proof for proof, candidate in zip(proofs, value["cells"]) if candidate == cell))
    with pytest.raises(ValueError, match="reuses"):
        verify.verify_pilot(tmp_path)


def test_prompt_policy_drift_is_rejected_before_rendering(monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "judge_assets", lambda: {"drift": True})
    with pytest.raises(ValueError, match="judge-prefix policy or assets drifted"):
        verify._expected_prompt({"judge_assets": {}}, tmp_path, {})
