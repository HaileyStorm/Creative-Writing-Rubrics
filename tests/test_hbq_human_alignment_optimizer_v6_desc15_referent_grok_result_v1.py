from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc15-referent-grok-result-v1"


def module():
    spec = importlib.util.spec_from_file_location("_desc15_referent_grok_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def inputs() -> dict[str, Path]:
    configured = os.environ.get("CWR_DESC15_REFERENT_RESULT_EVIDENCE_DOCUMENTS")
    if configured is None:
        pytest.skip("set CWR_DESC15_REFERENT_RESULT_EVIDENCE_DOCUMENTS to replay private immutable evidence")
    documents = Path(configured)
    root = documents / "cwr-desc15-referent-grok-eebf740-20260831a"
    return {
        "freeze_root": documents / "cwr-hanna-desc15-referent-freeze-38ac0b7-20260901a",
        "development_freeze_root": documents / "cwr-hanna-broader-freeze-436da1e-20260831a",
        "normalized_root": documents / "cwr-hanna-nextwave-normalized-d5e95ba-20260831a",
        "materialization_root": documents / "cwr-hanna-v5-mixed-materialization-9bb20be-20260830a",
        "frozen_successor_path": documents / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        "hanna_csv_path": documents / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
        "output_root": root,
        "collector_path": root / "collector.json",
        "optimizer_result_path": documents / "cwr-desc15-referent-grok-eebf740-20260831a.optimizer-defe47c-v1.json",
    }


def test_package_pins_file_and_internal_result_hashes_separately():
    value = module()
    value.validate_package()
    assert value.EXTERNAL_RESULT_FILE_SHA256 == "5f074a3998f1f830de6157cca7751ca1aab3200bced8806da3d628d4f7570c4f"
    assert value.EXTERNAL_RESULT_INTERNAL_SHA256 == "97db289ebc4b9e558c53c8659c818cbc248da190187ead9cb651e8049c07ff12"
    assert value.load_analyzer().STUDY_ID == value.ANALYZER_ID


def test_exact_collector_and_optimizer_replay_match_public_result():
    value = module()
    replayed = value.replay(**inputs())
    persisted = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert replayed == persisted
    assert [row["equal_group_mae"] for row in replayed["metrics"]] == pytest.approx([
        0.8551587301587302, 0.8492063492063492, 0.8293650793650793, 0.8373015873015872,
    ])
    assert replayed["qualification"]["qualifiers"] == list(value.CHILDREN)
    assert replayed["qualification"]["sol_status"] == "pending"
    assert replayed["evidence_ceiling"]["native_endpoint_contact_cardinality"] == "unproven"


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
