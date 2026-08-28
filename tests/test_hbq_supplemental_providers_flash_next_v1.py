from __future__ import annotations

import importlib.util
import json
import os
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest


ROOT = Path(os.path.abspath(__file__)).parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-supplemental-providers-flash-next-v1"


def load():
    spec = importlib.util.spec_from_file_location("flash_next_scaffold_test", PACKAGE / "study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provider_neutral_method_input_checkpoint_is_nonpromotable():
    study = load()
    result = study.validate()
    assert result["provider_calls"] == 0
    assert result["state"] == "OFFLINE_ADAPTER_ONLY"
    assert result["execution_ready"] is False and result["pairable"] is False
    contract = study.contract()
    assert set(contract) == {"format_version", "study_id", "status", "frozen_before_execution", "canonical_root", "purpose", "semantic_contract_sha256", "planning_identity", "method_input_manifest", "adapter_asset_manifest", "invariants", "interpretation_limits"}
    assert set(contract["method_input_manifest"]) == {"artifact", "row_required_fields", "contents", "route_specific_transport"}


def test_45_frozen_method_input_rows_embed_exact_hbq_commitments_without_wire_fields():
    study = load()
    inputs = study._read_method_inputs()
    identity = study.contract()["planning_identity"]
    mapping = study._expected_requests()
    assert len(inputs) == len(mapping) == 45
    assert all(set(value) == {"format_version", "condition_labels", "request", "source_artifact", "question_ids"} for value in inputs)
    assert all(value["condition_labels"] == identity["condition_labels"] and value["source_artifact"] == identity["source_artifact"] for value in inputs)
    canonical_ids = None
    for repetition in range(1, 6):
        batches = [value for request, value in zip(mapping, inputs, strict=True) if request["method_id"] == "hbq" and request["repetition"] == repetition]
        questions = [value["question_ids"] for value in batches]
        assert [len(batch) for batch in questions] == [32, 32, 32, 32, 32, 18]
        ids = [item for batch in questions for item in batch]
        assert len(ids) == len(set(ids)) == 178
        canonical_ids = ids if canonical_ids is None else canonical_ids
        assert ids == canonical_ids


def test_asset_containment_rejects_repository_escape():
    study = load()
    with pytest.raises(ValueError, match="escapes repository containment"):
        study._asset_path({"path": "../outside", "sha256": "0" * 64, "bytes": 0})


def test_reparse_guard_rejects_a_symlink_ancestor_when_supported(tmp_path: Path):
    study = load()
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        pytest.skip("The host does not permit a test symlink")
    with pytest.raises(ValueError, match="symlink or reparse"):
        study._assert_no_reparse_path(link / "candidate.json", "test path")


def test_contract_reader_rejects_a_synthetic_reparse_attribute(monkeypatch: pytest.MonkeyPatch):
    study = load()
    original_lstat = study.os.lstat
    contract_path = study.HERE / "study-contract.json"

    def reparse_lstat(candidate):
        if Path(candidate) == contract_path:
            metadata = original_lstat(candidate)
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return original_lstat(candidate)

    monkeypatch.setattr(study.os, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="study contract contains a symlink or reparse point"):
        study.contract()


def test_contract_reader_rejects_a_synthetic_ancestor_reparse_attribute(monkeypatch: pytest.MonkeyPatch):
    study = load()
    original_lstat = study.os.lstat
    ancestor = study.HERE.parent

    def reparse_lstat(candidate):
        if Path(candidate) == ancestor:
            metadata = original_lstat(candidate)
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return original_lstat(candidate)

    monkeypatch.setattr(study.os, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="study contract contains a symlink or reparse point"):
        study.contract()


def test_contract_reader_rejects_digest_tampering(monkeypatch: pytest.MonkeyPatch):
    study = load()
    tampered = (study.HERE / "study-contract.json").read_bytes().replace(b'"format_version": 2', b'"format_version": 3', 1)
    monkeypatch.setattr(study, "_read_safe_bytes", lambda path, label: tampered)
    with pytest.raises(ValueError, match="Canonical semantic-contract digest drifted"):
        study.contract()


def test_method_input_artifact_rejects_byte_tampering(monkeypatch: pytest.MonkeyPatch):
    study = load()
    artifact = study.HERE / "method-inputs.jsonl"
    original_read = study._read_safe_bytes

    def tampered(path, label):
        value = original_read(path, label)
        return value.replace(b'"format_version":1', b'"format_version":0', 1) if Path(path) == artifact else value

    monkeypatch.setattr(study, "_read_safe_bytes", tampered)
    with pytest.raises(ValueError, match="artifact binding drifted"):
        study._read_method_inputs()


def test_method_input_semantics_reject_order_and_extra_rows():
    study = load()
    rows = study._read_method_inputs()
    swapped = list(rows)
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(ValueError, match="schema or order"):
        study._validate_rows(swapped)
    with pytest.raises(ValueError, match="row count"):
        study._validate_rows(rows + [rows[-1]])


def test_method_input_artifact_reparse_guard(monkeypatch: pytest.MonkeyPatch):
    study = load()
    original_lstat = study.os.lstat
    artifact = study.HERE / "method-inputs.jsonl"

    def reparse_lstat(candidate):
        if Path(candidate) == artifact:
            metadata = original_lstat(candidate)
            return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
        return original_lstat(candidate)

    monkeypatch.setattr(study.os, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="symlink or reparse point"):
        study._read_method_inputs()
