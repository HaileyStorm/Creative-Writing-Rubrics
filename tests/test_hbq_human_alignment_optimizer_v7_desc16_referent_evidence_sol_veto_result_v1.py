from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-result-v1"
DOCUMENTS = Path.home() / "Documents"
EXECUTION_ROOT = DOCUMENTS / "cwr-desc16-referent-evidence-sol-veto-9f48ed8-20260901a"
COLLECTOR = DOCUMENTS / "cwr-desc16-referent-evidence-sol-veto-9f48ed8-20260901a.collector.json"
GROK_RESULT = DOCUMENTS / "cwr-desc16-referent-evidence-grok-989f1d6-20260901a.optimizer-bdf96b8-v1.json"


def module():
    spec = importlib.util.spec_from_file_location("_desc16_referent_sol_veto_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def test_package_is_self_bound_and_keeps_authority_narrow():
    value = module()
    contract = value.validate_package()
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert contract["authority"] == result["authority"]
    assert result["geometry"]["confirmation_cells"] == 0
    assert result["source"] == contract["pins"]
    assert result["authority"] == {
        "confirmation": "unopened", "endpoint_pooling": "forbidden", "generalization": "none",
        "promotion": "none", "runtime": "none", "selection": "grok_qualifiers_then_sol_veto_only",
    }


def test_all_26_receipts_replay_to_a_parent_retention_result():
    value = module()
    replayed = value.replay(execution_root=EXECUTION_ROOT, collector_path=COLLECTOR, grok_result_path=GROK_RESULT)
    assert replayed == json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert [row["equal_group_mae"] for row in replayed["sol_validation"]["metrics"]] == pytest.approx([1.0188492063492063, 1.040873015873016])
    assert replayed["sol_validation"]["survivors"] == []
    assert replayed["sol_validation"]["retained_candidate_id"] == value.PARENT
    assert replayed["coverage"] == {"booleans": 156, "false_count": 1, "false_records": [{"candidate_id": value.CHILDREN[0], "cell_id": "desc16-sol-veto-17a9f8bfc5514b9b", "dimension": "Empathy"}]}
    assert replayed["evidence_ceiling"] == {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 26, "provider_calls_made": None}


def test_receipt_mutation_is_not_hidden_by_the_collector(monkeypatch):
    value = module()
    original = value.stable
    changed = False

    def corrupt(path: Path) -> bytes:
        nonlocal changed
        raw = original(path)
        if not changed and Path(path).name == "execution-receipt.json":
            receipt = json.loads(raw)
            receipt["human_score_projection"]["scores"]["Relevance"] = 0.0
            changed = True
            return value.canonical(receipt)
        return raw

    monkeypatch.setattr(value, "stable", corrupt)
    with pytest.raises(ValueError, match="persisted Sol cell evidence drifted"):
        value.replay(execution_root=EXECUTION_ROOT, collector_path=COLLECTOR, grok_result_path=GROK_RESULT)


@pytest.mark.parametrize("filename", ["target-vector.json", "prepared.json"])
def test_target_lineage_mutation_is_not_hidden_by_the_collector(monkeypatch, filename: str):
    value = module()
    original = value.stable
    changed = False

    def corrupt(path: Path) -> bytes:
        nonlocal changed
        raw = original(path)
        if not changed and Path(path).name == filename:
            changed = True
            record = json.loads(raw)
            if filename == "target-vector.json":
                record["target"]["Relevance"] = 0.0
            else:
                record["task_payload_sha256"] = "0" * 64
            return value.canonical(record)
        return raw

    monkeypatch.setattr(value, "stable", corrupt)
    with pytest.raises(ValueError, match="persisted Sol cell evidence drifted"):
        value.replay(execution_root=EXECUTION_ROOT, collector_path=COLLECTOR, grok_result_path=GROK_RESULT)


def test_parent_result_mutation_is_not_relabelled_as_a_valid_reference(monkeypatch):
    value = module()
    original = value.stable

    def corrupt(path: Path) -> bytes:
        raw = original(path)
        if Path(path) == value.PARENT_PUBLIC_RESULT:
            result = json.loads(raw)
            result["sol_validation"]["metrics"][1]["equal_group_mae"] = 0.0
            return value.canonical(result)
        return raw

    monkeypatch.setattr(value, "stable", corrupt)
    with pytest.raises(ValueError, match="frozen descendant-15 Sol parent result drifted"):
        value.replay(execution_root=EXECUTION_ROOT, collector_path=COLLECTOR, grok_result_path=GROK_RESULT)
