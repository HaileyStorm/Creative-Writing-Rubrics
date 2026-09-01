from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-result-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc17_generalization_grok_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def inputs() -> dict[str, Path]:
    configured = os.environ.get("CWR_DESC17_GENERALIZATION_RESULT_EVIDENCE_DOCUMENTS")
    if configured is None:
        pytest.skip("set CWR_DESC17_GENERALIZATION_RESULT_EVIDENCE_DOCUMENTS to replay private immutable evidence")
    documents = Path(configured)
    root = documents / "cwr-desc17-generalization-grok-69e7a40-20260901d"
    return {
        "freeze_root": documents / "cwr-hanna-desc17-generalization-freeze-commit-pending-20260901a",
        "development_freeze_root": documents / "cwr-hanna-broader-freeze-436da1e-20260831a",
        "normalized_root": documents / "cwr-hanna-nextwave-normalized-d5e95ba-20260831a",
        "materialization_root": documents / "cwr-hanna-v5-mixed-materialization-9bb20be-20260830a",
        "frozen_successor_path": documents / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        "hanna_csv_path": documents / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
        "output_root": root,
        "collector_path": documents / "cwr-desc17-generalization-grok-69e7a40-20260901d.collector.json",
        "optimizer_result_path": documents / "cwr-desc17-generalization-grok-69e7a40-20260901d.optimizer-71abad0-v1.json",
    }


def test_package_pins_file_and_internal_result_hashes_separately():
    value = module()
    value.validate_package()
    assert value.EXTERNAL_RESULT_FILE_SHA256 == "68168bb6988e0b6997321760a8b6cf3f763b90955d751d1362e859f6789c1847"
    assert value.EXTERNAL_RESULT_INTERNAL_SHA256 == "a904d23639d4f17c625b50be2f1502e8bb91e5f8c0f7ec971e52db3bda994d53"
    assert value.load_analyzer().STUDY_ID == value.ANALYZER_ID


def test_stable_read_rejects_an_ancestor_change(monkeypatch):
    value = module()
    original = value.ancestry
    calls = 0

    def drifting(path, *, directory):
        nonlocal calls
        calls += 1
        observed = original(path, directory=directory)
        return observed if calls == 1 else observed + ((0, 0, 0, 0, 0),)

    monkeypatch.setattr(value, "ancestry", drifting)
    with pytest.raises(ValueError, match="changed during stable read"):
        value.stable(PACKAGE / "result.json")


def test_load_analyzer_rechecks_admitted_bytes_after_execution(monkeypatch):
    value = module()
    original = value.stable
    analyzer_reads = 0

    def drifting(path, *, directory=False):
        nonlocal analyzer_reads
        raw = original(path, directory=directory)
        if Path(path).name == "analyzer.py":
            analyzer_reads += 1
            if analyzer_reads == 2:
                return raw + b"\n"
        return raw

    monkeypatch.setattr(value, "stable", drifting)
    with pytest.raises(ValueError, match="changed during load"):
        value.load_analyzer()


def test_exact_private_evidence_replay_records_zero_qualifiers_and_zero_sol_calls():
    value = module()
    replayed = value.replay(**inputs())
    persisted = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert replayed == persisted
    assert [row["equal_group_mae"] for row in replayed["metrics"]] == pytest.approx([
        1.0432539682539683,
        1.3388888888888888,
        1.1746031746031744,
        1.10515873015873,
    ])
    qualification = replayed["qualification"]
    assert qualification["qualifiers"] == []
    assert qualification["sol_calls_made"] == 0
    assert qualification["all_children_fail_raw_equal_group_mae"] is True
    assert qualification["all_children_fail_six_setting_robustness"] is True
    assert replayed["authority"] == value.AUTHORITY
    assert replayed["evidence_ceiling"]["native_endpoint_contact_cardinality"] == "unproven"


def test_coherently_repinned_caller_aggregate_substitution_still_fails_independent_replay(tmp_path: Path, monkeypatch):
    value = module()
    paths = inputs()
    source = json.loads(paths["optimizer_result_path"].read_text(encoding="utf-8"))
    source["metrics"][0]["equal_group_mae"] = 0.0
    source["result_sha256"] = value.sha256({key: item for key, item in source.items() if key != "result_sha256"})
    fabricated = tmp_path / "optimizer.json"
    raw = value.canonical(source)
    fabricated.write_bytes(raw)
    monkeypatch.setattr(value, "EXTERNAL_RESULT_FILE_SHA256", value.sha256(raw))
    monkeypatch.setattr(value, "EXTERNAL_RESULT_INTERNAL_SHA256", source["result_sha256"])
    paths["optimizer_result_path"] = fabricated
    with pytest.raises(ValueError, match="independent optimizer replay differs"):
        value.replay(**paths)
