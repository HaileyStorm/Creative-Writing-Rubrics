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


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v3"

HISTORICAL_RUNNER = {
    "name": "runner.py",
    "bytes": 124714,
    "sha256": "0a22bf30781d6bbbde4c9b6a6e214891fe95aefddade6f955f5634f6accde4d2",
}
ARCHIVED_HISTORICAL_RUNNER = pytest.mark.skip(
    reason=(
        "Archived exact v3 runner byte equality requires the immutable e807c5d runtime; "
        "current runtime mismatch remains fail-closed and active cap-1 checks stay live."
    )
)


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


study = load("ox_alpha_v3_study", "study.py")
pilot = load("ox_alpha_v3_pilot", "run_transport_pilot.py", {"study": study})
verify = load("ox_alpha_v3_verify", "verify_transport_pilot.py", {"study": study})


def frozen() -> dict:
    return {"cells": [{"cell_id": f"ox-alpha-v3-{number:02d}", "item_id": f"item-{number}", "question_ids": [str(question) for question in range(16)]} for number in range(1, 4)]}


def test_contract_is_serial_16_leaf_and_score_blind():
    policy = study.CONTRACT["transport_pilot"]
    assert {key: policy[key] for key in ("cells", "batch_size", "question_count", "batch_attempts", "workers", "timeout_seconds")} == {"cells": 3, "batch_size": 16, "question_count": 16, "batch_attempts": 1, "workers": 1, "timeout_seconds": 100}
    text = (ROOT / "verify_transport_pilot.py").read_text(encoding="utf-8")
    assert "score.json" not in text and "HANNA ratings" not in text
    assert policy["required_shared_runner_option"] == "max_physical_http_attempts_per_logical_request=1"
    assert study.CONTRACT["execution"] == {"status": "preregistered_cap1_unexecuted", "required_shared_runner_option": "max_physical_http_attempts_per_logical_request=1", "required_request_schema": "codex-nous-tool-free-judge-request-v2", "launch_gate": "Fresh zero-cost catalog and usage proof plus a reviewed shared cap-1 runtime are required before launch."}


def test_current_runtime_bindings_keep_active_cap1_assets():
    observed = study.runtime_bindings()
    assert observed["launcher"] == {
        "name": "launch-bridge.ps1",
        "bytes": 5687,
        "sha256": "c54da5c1dd13e225e8da44239e94ef692539669e7ba62899b66d64abbed2b076",
    }
    assert observed["bridge"] == {
        "name": "nous_codex_bridge.py",
        "bytes": 220090,
        "sha256": "ff4eb873ef2625ba2074bfdf94b377288f43398f8f92b25eeb0a5a77dd4515a0",
    }
    assert observed["runner"]["name"] == "runner.py"
    assert observed["runner"] != HISTORICAL_RUNNER


@ARCHIVED_HISTORICAL_RUNNER
def test_historical_runner_binding_is_retained_as_immutable_provenance():
    assert study.runtime_bindings()["runner"] == HISTORICAL_RUNNER


def test_raw_current_runner_mismatch_fails_closed(monkeypatch, tmp_path):
    current_runtime = study.runtime_bindings()
    cells = frozen()["cells"]
    failed = {"work_dir": "failed-v2-root"}
    proof = {"path": "zero-cost-proof", "marker": "fresh"}
    checked_at = "2026-08-26T00:00:00+00:00"

    monkeypatch.setattr(study, "_cells", lambda _: (object(), cells, []))
    monkeypatch.setattr(study, "_fresh_zero_proof", lambda *_: proof)
    monkeypatch.setattr(study, "failed_v2_commitments", lambda _: failed)
    monkeypatch.setattr(study, "_external_roots", lambda *_: {"work": "current-work"})
    monkeypatch.setattr(study, "fingerprint", lambda path: {"name": Path(path).name, "bytes": 1, "sha256": "a" * 64})
    monkeypatch.setattr(study, "judge_assets", lambda: {"active": True})
    monkeypatch.setattr(study, "runtime_bindings", lambda: current_runtime)

    frozen_value = {
        "format_version": 1,
        "study_id": study.CONTRACT["study_id"],
        "frozen_before_execution": True,
        "contract": {"name": "study-contract.json", "bytes": 1, "sha256": "a" * 64},
        "external_roots": {"work": "current-work"},
        "failed_v2": failed,
        "provider": study.CONTRACT["provider"],
        "pilot": study.CONTRACT["transport_pilot"],
        "runtime": {**current_runtime, "runner": HISTORICAL_RUNNER},
        "judge_assets": {"active": True},
        "zero_cost_proof": {**proof, "freshness_checked_at": checked_at},
        "cells": cells,
    }
    (tmp_path / study.FROZEN_NAME).write_text(json.dumps(frozen_value), encoding="utf-8")

    with pytest.raises(ValueError, match="Ox v3 frozen transport contract drifted"):
        study.load_frozen(tmp_path)


def test_failed_v2_requires_exact_historical_524_524_root():
    configured = os.environ.get("CWR_OX_V2_FAILED_ROOT")
    if not configured:
        pytest.skip("set CWR_OX_V2_FAILED_ROOT for the immutable predecessor check")
    observed = study.failed_v2_commitments(Path(configured))
    assert observed["historical_http_statuses"] == [524, 524]
    assert observed["raw_evidence_tree"]["files"] == 7


def test_failed_v2_missing_or_drifted_commitment_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="unavailable|commitment drifted"):
        study.failed_v2_commitments(tmp_path)


def test_failed_v2_rejects_extra_terminal_evidence(monkeypatch):
    configured = os.environ.get("CWR_OX_V2_FAILED_ROOT")
    if not configured:
        pytest.skip("set CWR_OX_V2_FAILED_ROOT for the immutable predecessor check")
    monkeypatch.setattr(study, "_complete_tree", lambda _: {"files": 18, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="extra, missing, or drifted"):
        study.failed_v2_commitments(Path(configured))


def test_parent_hash_drift_fails_closed(monkeypatch):
    changed = dict(study.CONTRACT)
    changed["parent_v2"] = {**changed["parent_v2"], "files": {**changed["parent_v2"]["files"], "study.py": "0" * 64}}
    monkeypatch.setattr(study, "CONTRACT", changed)
    with pytest.raises(ValueError, match="parent file drifted"):
        study._parent_v2()


def test_executor_passes_the_shared_cap1_option(monkeypatch, tmp_path):
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
    assert called["batch_attempts"] == 1 and called["batch_size"] == 16


def test_external_roots_reject_repo_and_overlap(tmp_path):
    with pytest.raises(ValueError, match="outside the repository"):
        study._external_disjoint(study.REPO_ROOT)
    external = Path(tempfile.gettempdir()) / "cwr-ox-v3-external-root-test"
    with pytest.raises(ValueError, match="disjoint"):
        study._external_disjoint(external, external / "child")


def test_judge_prefix_policy_and_schema_are_frozen():
    assets = study.judge_assets()
    assert assets["strict_ai"] is False
    assert assets["judge_prefix"]["included"] is False
    assert [item["name"] for item in assets["active_prompts"]] == ["BINARY_EVALUATION_PROMPT.md"]
    assert assets["response_schema"]["name"] == "hbq_judge_response.schema.json"


def test_prompt_policy_drift_is_rejected_before_rendering(monkeypatch, tmp_path):
    monkeypatch.setattr(verify, "judge_assets", lambda: {"drift": True})
    with pytest.raises(ValueError, match="judge-prefix policy or assets drifted"):
        verify._expected_prompt({"judge_assets": {}}, tmp_path, {})


def test_future_verifier_rejects_duplicate_session_or_receipt(monkeypatch, tmp_path):
    value = frozen()
    journal = tmp_path / "pilot-journal"; journal.mkdir()
    receipts = tmp_path / "pilot-receipts"; receipts.mkdir()
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
