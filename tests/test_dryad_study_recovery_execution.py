from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXECUTION = ROOT / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/baseline_measurement_execution.py"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("field", ["study_recovery_manifest_path", "expected_study_recovery_manifest_sha256"])
def test_mixed_partial_source_amendment_is_rejected_before_filesystem_work(tmp_path, monkeypatch, field):
    execution = _load(EXECUTION, "dryad_partial_study_boundary")
    monkeypatch.setattr(execution, "_plain", lambda *_args, **_kwargs: pytest.fail("filesystem work before mode rejection"))
    anchors = {name: "a" * 64 for name in (
        "expected_plan_sha256", "expected_initialization_sha256", "expected_previous_settlement_sha256",
        "expected_prepared_sha256", "expected_review_sha256", "expected_source_sha256",
        "expected_operational_renewal_sha256")}
    anchors[field] = tmp_path / "recovered-study.json" if field.endswith("path") else "b" * 64
    with pytest.raises(ValueError, match="use a settled-cohort operational renewal"):
        execution.prepare_partial_source_amendment(tmp_path, tmp_path, tmp_path, 8, **anchors)


def test_executor_uses_the_real_recovered_study_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _load(ROOT / "tests/test_dryad_baseline_recovered_study.py", "dryad_recovered_study_support")
    recovered_case = helper.case.__wrapped__(tmp_path, monkeypatch)
    execution_root = tmp_path / "execution"
    execution_root.mkdir()
    original = execution_root / recovered_case.original.name
    recovered_case.original.rename(original)
    recovered_case.original = original
    helper.materialize(recovered_case)
    execution = _load(EXECUTION, "dryad_recovery_execution_loader")
    plan_root = tmp_path / "plan"
    plan_root.mkdir()
    descendant = recovered_case.descendant
    manifest = descendant / "recovered-study.json"
    manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
    manifest_sha256 = _hash(manifest.read_bytes())
    source_raw = recovered_case.source["story_text"].encode("utf-8")
    record = {
        "pass_id": recovered_case.subject.TARGET_PASS_ID,
        "run_path": original.name,
        "logical_sample_id": recovered_case.subject.LOGICAL_SAMPLE_ID,
        "opaque_story_id": recovered_case.subject.STORY_ID,
        "input_path": "synthetic-input.txt",
        "source_sha256": _hash(source_raw),
        "source_bytes": len(source_raw),
    }
    original_load = execution._load
    assert execution.SOURCE_PINS[execution.RECOVERED_STUDY_SOURCE] == _hash(
        execution.RECOVERED_STUDY_SOURCE.read_bytes())
    monkeypatch.setattr(execution, "_load", lambda path, raw, prefix: recovered_case.subject
                        if Path(path) == execution.RECOVERED_STUDY_SOURCE else original_load(path, raw, prefix))
    monkeypatch.setattr(execution, "_source", lambda _record, _plan_root: (tmp_path / "synthetic-input.txt", source_raw))
    monkeypatch.setattr(execution, "STUDY_RECOVERY_ADOPTION_SHA256",
                        manifest_value["reader_inputs"]["expected_adoption_sha256"])
    context = execution._study_recovery_context(
        {execution.RECOVERED_STUDY_SOURCE: execution.RECOVERED_STUDY_SOURCE.read_bytes()},
        execution_root, plan_root, {record["pass_id"]: record}, recovered_case.runtime,
        study_recovery_manifest_path=manifest,
        expected_study_recovery_manifest_sha256=manifest_sha256)
    assert context is not None
    assert context["target_pass_id"] == record["pass_id"]
    assert context["descendant_root"] == descendant
    assert context["expected_study_recovery"] == recovered_case.result["expected_study_recovery"]
    assert recovered_case.subject._inventory(original) == recovered_case.original_inventory
