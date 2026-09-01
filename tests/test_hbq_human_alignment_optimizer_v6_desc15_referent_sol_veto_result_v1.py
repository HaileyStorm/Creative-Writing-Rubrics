from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-result-v1"
DOCUMENTS = Path.home() / "Documents"
EXECUTION_ROOT = DOCUMENTS / "cwr-desc15-referent-sol-veto-a435881-20260831a"
COLLECTOR = DOCUMENTS / "cwr-desc15-referent-sol-veto-a435881-20260831a.collector.json"
GROK_RESULT = DOCUMENTS / "cwr-desc15-referent-grok-eebf740-20260831a.optimizer-defe47c-v1.json"


def module():
    spec = importlib.util.spec_from_file_location("_desc15_referent_sol_veto_result", PACKAGE / "verify.py")
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
    assert result["authority"] == {
        "confirmation": "unopened",
        "endpoint_pooling": "forbidden",
        "generalization": "none",
        "promotion": "none",
        "runtime": "none",
        "selection": "grok_qualifiers_then_sol_veto_only",
    }
    assert result["geometry"]["confirmation_cells"] == 0
    assert contract["pins"] == result["source"]


def test_all_39_receipts_replay_to_endpoint_separated_veto_result():
    value = module()
    replayed = value.replay(execution_root=EXECUTION_ROOT, collector_path=COLLECTOR, grok_result_path=GROK_RESULT)
    assert replayed == json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert [row["equal_group_mae"] for row in replayed["sol_validation"]["metrics"]] == pytest.approx([
        1.1371031746031746,
        1.0101190476190476,
        1.14484126984127,
    ])
    assert replayed["sol_validation"]["survivors"] == [value.CHILDREN[1]]
    assert replayed["sol_validation"]["vetoed"] == [value.CHILDREN[0], value.CHILDREN[2]]
    assert replayed["coverage"] == {"booleans": 234, "false_count": 0, "false_records": []}
    assert replayed["evidence_ceiling"] == {
        "native_endpoint_contact_cardinality": "unproven",
        "process_lifecycle_receipts": 39,
        "provider_calls_made": None,
    }


def test_receipt_mutation_is_not_hidden_by_unchanged_collector(monkeypatch):
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


def test_file_and_internal_result_hashes_are_distinct_and_exact():
    value = module()
    raw = (PACKAGE / "result.json").read_bytes()
    result = json.loads(raw)
    assert value.sha256(raw) == "23988d59a94988b2604317786f2874fa59b0a411c9aafa677f9be28df32e2e71"
    assert result["result_sha256"] == "eb570725e91f8190c8e7427e50b65a518c9317f04d5e81bd2a0b355d1fa7f4dc"
    assert value.sha256({key: item for key, item in result.items() if key != "result_sha256"}) == result["result_sha256"]
