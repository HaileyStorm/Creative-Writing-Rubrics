"""Regression coverage for the Ox Alpha v7 checkpoint-selector repair."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import gzip

import pytest

from hbqrs.paths import book_root
from tests import _ox_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-human-alignment-supplemental-providers-ox-alpha-v7"
V6_ROOT = Path(os.environ.get("CWR_OX_V6_UNCERTAIN_ROOT", r"C:\Users\Haile\Documents\cwr-ox-alpha-v6-cap1-pilot-20260821-c36f380"))
CAP1_PROOF = Path(os.environ.get("CWR_OX_CAP1_ZERO_COST_PROOF", r"C:\Users\Haile\Documents\cwr-ox-alpha-zero-cost-proof-cap1-20260821.json"))


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


study = historical_runtime.install(load("ox_alpha_v7_study", "study.py"))
verify = load("ox_alpha_v7_verify", "verify_transport_pilot.py", {"study": study})


def test_contract_is_exact_v6_successor_with_cap1_policy():
    policy = study.CONTRACT["transport_pilot"]
    assert study.CONTRACT["parent_v6"]["study_id"] == "hbq-human-alignment-supplemental-providers-ox-alpha-v6"
    assert policy["workers"] == 1
    assert policy["batch_size"] == policy["question_count"] == 4
    assert policy["batch_attempts"] == 1
    assert policy["timeout_seconds"] == 240
    assert policy["maximum_http_seconds_exclusive"] == 150
    assert "111.5274232" in study.CONTRACT["uncertain_v6"]["required_state"]
    assert "checkpoint selector globbed request and result JSON" in study.CONTRACT["uncertain_v6"]["required_state"]
    assert "prompt assets or source/context text" in study.CONTRACT["uncertain_v6"]["required_state"]


def test_v6_parent_package_is_pinned_and_hash_drift_fails_closed(monkeypatch):
    parent = study._parent_v6()
    assert parent.CONTRACT["study_id"] == "hbq-human-alignment-supplemental-providers-ox-alpha-v6"
    changed = dict(study.V6_FILES)
    changed["study.py"] = "0" * 64
    monkeypatch.setattr(study, "V6_FILES", changed)
    with pytest.raises(ValueError, match="parent file drifted"):
        study._parent_v6()


def test_real_v6_selector_is_one_checkpoint_not_provider_sidecars():
    if not V6_ROOT.is_dir():
        pytest.skip("set CWR_OX_V6_UNCERTAIN_ROOT for immutable predecessor verification")
    response_root = V6_ROOT / "runs" / "pilot" / "ox-alpha-v6-01" / "responses"
    selected = verify.checkpoint_paths(response_root)
    assert [path.name for path in selected] == ["batch-0001.json"]
    assert (response_root / "batch-0001.attempt-0001.nous.request.json").is_file()
    assert (response_root / "batch-0001.attempt-0001.nous.result.json").is_file()
    assert all(".nous." not in path.name for path in selected)


def test_real_v6_prompt_rebuild_preserves_crlf_bytes():
    if not V6_ROOT.is_dir():
        pytest.skip("set CWR_OX_V6_UNCERTAIN_ROOT for immutable predecessor verification")
    parent = study._parent_v6()
    frozen = parent.load_frozen(V6_ROOT)
    cell = frozen["cells"][0]
    artifact = Path(cell["paths"]["artifact"])
    checkpoint = V6_ROOT / "runs" / "pilot" / "ox-alpha-v6-01" / "responses" / "batch-0001.json"
    persisted = gzip.decompress(checkpoint.with_suffix(".prompt.txt.gz").read_bytes())
    assert b"\r\n" in (book_root() / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_bytes()
    assert verify._expected_prompt(frozen, artifact.parent, cell) == persisted
    semantic = verify.verify_cell(V6_ROOT, frozen, cell)
    assert semantic["checkpoint"]["name"] == "batch-0001.json"
    assert semantic["logical_request_id"] == "1dd4a83cfca840cc8054d948659cf49c"


def test_real_v6_complete_tree_and_semantic_predecessor_receipt():
    if not V6_ROOT.is_dir():
        pytest.skip("set CWR_OX_V6_UNCERTAIN_ROOT for immutable predecessor verification")
    observed = study.uncertain_v6_commitments(V6_ROOT)
    assert observed["complete_work_tree"] == study.V6_COMPLETE_TREE
    assert observed["historical_http_attempts"] == [{"status": 200, "duration_ns": 111_527_423_200}]
    assert observed["accepted_message_and_checkpoint"] is True
    assert observed["journal_present"] is False
    assert observed["semantic_receipt_present"] is False
    assert set(observed["accepted_global_ids"]) == {"session_id", "receipt_id", "logical_request_id"}
    assert observed["corrected_selector_semantic_verification"]["checkpoint"]["name"] == "batch-0001.json"
    assert not (V6_ROOT / "pilot-journal").exists()
    assert not (V6_ROOT / "pilot-receipts").exists()


@pytest.mark.skip(reason="archived pending a genuinely fresh zero-cost proof; replay must not bypass current freshness")
def test_real_v6_freeze_reload_and_stale_proof_rejection_without_provider_contact():
    if not V6_ROOT.is_dir() or not CAP1_PROOF.is_file():
        pytest.skip("set CWR_OX_V6_UNCERTAIN_ROOT and CWR_OX_CAP1_ZERO_COST_PROOF for the no-provider freeze check")
    with tempfile.TemporaryDirectory(prefix="cwr-ox-v7-freeze-") as directory:
        work = Path(directory) / "work"
        frozen = study.freeze_work(V6_ROOT, CAP1_PROOF, work)
        assert study.load_frozen(work) == frozen
        assert not (work / "runs").exists()
    with pytest.raises(ValueError, match="not fresh"):
        study._fresh_zero_proof(study._parent_v6(), CAP1_PROOF, "2099-01-01T00:00:00+00:00")


def test_checkpoint_selector_rejects_near_matches(tmp_path):
    for name in ("batch-0001.json", "batch-1.json", "batch-0001.extra.json", "batch-١٢٣٤.json", "batch-0001.attempt-0001.nous.request.json", "batch-0001.attempt-0001.nous.result.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [path.name for path in verify.checkpoint_paths(tmp_path)] == ["batch-0001.json"]
