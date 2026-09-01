from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-grok-result-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc16_referent_grok_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def inputs() -> dict[str, Path]:
    configured = os.environ.get("CWR_DESC16_REFERENT_RESULT_EVIDENCE_DOCUMENTS")
    if configured is None:
        pytest.skip("set CWR_DESC16_REFERENT_RESULT_EVIDENCE_DOCUMENTS to replay private immutable evidence")
    documents = Path(configured)
    root = documents / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a"
    return {
        "freeze_root": documents / "cwr-hanna-desc16-referent-evidence-freeze-commit-pending-20260901a",
        "development_freeze_root": documents / "cwr-hanna-broader-freeze-436da1e-20260831a",
        "normalized_root": documents / "cwr-hanna-nextwave-normalized-d5e95ba-20260831a",
        "materialization_root": documents / "cwr-hanna-v5-mixed-materialization-9bb20be-20260830a",
        "frozen_successor_path": documents / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        "hanna_csv_path": documents / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
        "output_root": root,
        "collector_path": documents / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a.collector.json",
        "optimizer_result_path": documents / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a.optimizer-bdf96b8-v1.json",
    }


def test_package_pins_file_and_internal_result_hashes_separately():
    value = module()
    value.validate_package()
    assert value.EXTERNAL_RESULT_FILE_SHA256 == "53dd32cc52c2f7975f2562e172f735576ae755bf702f3ee687f8e0418c2bdd54"
    assert value.EXTERNAL_RESULT_INTERNAL_SHA256 == "e0c00248520c18676d5ea760c8464195b9b2ea0863f16e2c6cb840ac027f2f9a"
    assert value.load_analyzer().STUDY_ID == value.ANALYZER_ID


def test_exact_collector_and_optimizer_replay_match_public_result():
    value = module()
    replayed = value.replay(**inputs())
    persisted = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert replayed == persisted
    assert [row["equal_group_mae"] for row in replayed["metrics"]] == pytest.approx([
        0.8531746031746031, 0.8253968253968254, 0.8730158730158729, 0.8174603174603174,
    ])
    qualification = replayed["qualification"]
    assert qualification["qualifiers"] == list(value.QUALIFIERS)
    assert qualification["rejected_candidates"] == [value.CHILDREN[1]]
    assert qualification["assessments"][1] == {
        "candidate_id": value.CHILDREN[1],
        "raw_equal_group_mae_strictly_below_parent": False,
        "no_worse_than_parent_all_six_robustness_settings": False,
        "qualifies_for_sol_veto": False,
    }
    assert qualification["sol_status"] == "pending"
    assert replayed["evidence_ceiling"]["native_endpoint_contact_cardinality"] == "unproven"


def test_reductions_are_relative_to_the_fresh_matched_wave_parent():
    value = module()
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    parent = result["metrics"][0]["equal_group_mae"]
    assert parent == pytest.approx(0.8531746031746031)
    for row in result["metrics"][1:]:
        assert row["relative_reduction_from_parent"] == pytest.approx((parent - row["equal_group_mae"]) / parent)
    assert result["metrics"][1]["relative_reduction_from_parent"] == pytest.approx(0.032558139534883734)
    assert result["metrics"][3]["relative_reduction_from_parent"] == pytest.approx(0.041860465116279055)
    assert result["metrics"][2]["relative_reduction_from_parent"] < 0
    assert value.PARENT == result["qualification"]["parent_candidate_id"]


def test_result_materialization_is_fresh_only(tmp_path: Path):
    value = module()
    output = tmp_path / "result.json"
    value.write_result(output, {"value": 1})
    with pytest.raises(ValueError, match="fresh"):
        value.write_result(output, {"value": 1})


def test_optimizer_result_rejects_coherently_repinned_caller_aggregate_substitution(tmp_path: Path, monkeypatch):
    value = module()
    paths = inputs()
    fabricated = tmp_path / "optimizer.json"
    source = json.loads(paths["optimizer_result_path"].read_text(encoding="utf-8"))
    source["metrics"][0]["equal_group_mae"] = 0.0
    source["result_sha256"] = value.sha256({key: item for key, item in source.items() if key != "result_sha256"})
    raw = value.canonical(source)
    fabricated.write_bytes(raw)
    monkeypatch.setattr(value, "EXTERNAL_RESULT_FILE_SHA256", value.sha256(raw))
    monkeypatch.setattr(value, "EXTERNAL_RESULT_INTERNAL_SHA256", source["result_sha256"])
    paths["optimizer_result_path"] = fabricated
    with pytest.raises(ValueError, match="independent optimizer replay differs"):
        value.replay(**paths)
