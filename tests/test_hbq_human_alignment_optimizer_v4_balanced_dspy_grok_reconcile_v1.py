from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v1"
SOURCE = Path(r"C:\Users\Haile\Documents\cwr-hanna-v4-balanced-dspy-grok-v2-475f5d2f-dd6dc97e")
reconciler = load_module(PACKAGE / "reconciler.py", name="hanna_v4_balanced_dspy_grok_reconcile_v1")


@pytest.fixture()
def terminal_source(tmp_path: Path) -> Path:
    if not SOURCE.is_dir():
        pytest.skip("frozen v2 terminal source is unavailable on this host")
    target = tmp_path / "terminal-source"
    shutil.copytree(SOURCE, target)
    return target


def _control(path: Path) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _write_control(path: Path, value: dict) -> None:
    path.write_bytes(reconciler.adapter_canonical(value))


def _rehash_output(value: dict) -> None:
    result = value["result"]
    result["output_hash"] = reconciler.sha256(reconciler.adapter_canonical(result["output"]))


def test_reconciles_live_shaped_all_ten_with_zero_new_contact_and_audited_derivation(terminal_source: Path, tmp_path: Path):
    manifest = reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "reconciled")
    stored = (tmp_path / "reconciled" / "reconciliation-manifest.json").read_bytes()
    assert reconciler.project_canonical(manifest) == stored
    assert manifest["reconciliation_provider_calls_made"] == manifest["reconciliation_process_launches"] == 0
    assert manifest["source"]["completed_native_identities"] == manifest["source"]["source_process_launches"] == 10
    assert len(manifest["samples"]) == 10
    assert manifest["samples"][3]["derivation"]["base64_audit"]["profile"]["removed_ascii_whitespace"] == [{"offset": 1708, "byte": "0x20"}]
    assert manifest["samples"][5]["derivation"]["factors"] == "opaque_model_supplied_not_v1_factor_conformance"
    assert manifest["samples"][8]["lineage"]["parent_candidate_id"] == "candidate-52d1be4bc34e0018"
    assert json.loads(base64.b64decode(manifest["samples"][0]["normalized_output"]["descendant_profile_base64"]))["instruction_sha256"] == manifest["samples"][0]["lineage"]["descendant_instruction_sha256"]


def test_fresh_target_rejection_and_clean_target_idempotence(terminal_source: Path, tmp_path: Path):
    first = reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "one")
    with pytest.raises(ValueError, match="existing target"):
        reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "one")
    second = reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "two")
    assert reconciler.project_canonical(first) == reconciler.project_canonical(second)


@pytest.mark.parametrize("artifact", ["prompt-request.bin", "response-schema.json", "prepared.json", "launch-intent.json", "result.json"])
def test_source_tamper_and_extra_artifact_reject_before_target_write(terminal_source: Path, tmp_path: Path, artifact: str):
    path = terminal_source / "sample-01" / artifact
    path.write_bytes(path.read_bytes() + b"x")
    target = tmp_path / "reconciled"
    with pytest.raises(ValueError):
        reconciler.reconcile_all(source_root=terminal_source, target_root=target)
    assert not target.exists()
    extra = terminal_source / "sample-01" / "extra.bin"
    extra.write_bytes(b"extra")
    with pytest.raises(ValueError):
        reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "extra")


def test_control_swaps_and_duplicate_request_or_session_reject(terminal_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    first, second = terminal_source / "sample-01" / "adapter-stdout.bin", terminal_source / "sample-02" / "adapter-stdout.bin"
    first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
    first.write_bytes(second_bytes); second.write_bytes(first_bytes)
    with pytest.raises(ValueError, match="control commitment"):
        reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "swapped")
    first.write_bytes(first_bytes); second.write_bytes(second_bytes)
    duplicate = _control(second); duplicate["result"]["runtime"]["request_id_hash"] = _control(first)["result"]["runtime"]["request_id_hash"]
    _write_control(second, duplicate)
    monkeypatch.setitem(reconciler.SOURCE_CONTROL_SHA256, "sample-02", reconciler.sha256(second.read_bytes()))
    monkeypatch.setattr(reconciler, "_contract", lambda: {})
    with pytest.raises(ValueError, match="duplicate request"):
        reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "duplicate")


@pytest.mark.parametrize("mutation", ["invalid_base64", "invalid_json", "parent_instruction"])
def test_base64_json_and_parent_identity_rejections(terminal_source: Path, tmp_path: Path, mutation: str, monkeypatch: pytest.MonkeyPatch):
    path = terminal_source / "sample-01" / "adapter-stdout.bin"; control = _control(path); output = control["result"]["output"]
    if mutation == "invalid_base64":
        output["descendant_profile_base64"] = "%%%"
    elif mutation == "invalid_json":
        output["descendant_profile_base64"] = base64.b64encode(b'{"a":NaN}').decode("ascii")
    else:
        preparation = json.loads((terminal_source / "sample-01" / "dspy-input-preparation.json").read_bytes())
        output["descendant_instruction_base64"] = preparation["inputs"]["parent_instruction_base64"]
    _rehash_output(control); _write_control(path, control)
    monkeypatch.setitem(reconciler.SOURCE_CONTROL_SHA256, "sample-01", reconciler.sha256(path.read_bytes()))
    with pytest.raises(ValueError):
        reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / mutation)


def test_reparse_source_is_rejected(terminal_source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    original = reconciler._plain
    def unsafe(path: Path, *, directory: bool | None = None) -> bool:
        return False if Path(path).name == "adapter-stdout.bin" else original(path, directory=directory)
    monkeypatch.setattr(reconciler, "_plain", unsafe)
    with pytest.raises(ValueError, match="unsafe"):
        reconciler.reconcile_all(source_root=terminal_source, target_root=tmp_path / "reparse")


def test_reconciler_has_no_provider_capable_surface():
    source = (PACKAGE / "reconciler.py").read_text(encoding="utf-8")
    assert "import subprocess" not in source and "model_work_queue" not in source and "allow_remote" not in source and "def reconcile_all(*, source_root: Path, target_root: Path)" in source
    assert tuple(reconciler.reconcile_all.__annotations__) == ("source_root", "target_root", "return")
