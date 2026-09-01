from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-result-v1" / "verify.py"


def module():
    spec = importlib.util.spec_from_file_location("_desc13_sol_result_test", VERIFY)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    try: spec.loader.exec_module(value)
    finally: sys.modules.pop(spec.name, None)
    return value


def test_equal_group_metrics_require_all_three_candidates_and_seven_groups():
    value = module()
    rows, comparison = value._metrics({candidate: {f"group-{index}": 1.0 + index for index in range(7)} for candidate in (value.BASELINE, value.PARENT, value.WINNER)})
    assert len(rows) == 3 and comparison["baseline_to_winner"]["relative_reduction"] == 0.0
    with pytest.raises(ValueError, match="incomplete"):
        value._metrics({value.BASELINE: {}, value.PARENT: {}, value.WINNER: {}})


def test_committed_executor_and_grok_pins_are_explicit():
    value = module()
    assert value.SOURCE_COMMIT == "f1a06c7a83aaf85e90030735360da33fd9fc2219"
    assert value.GROK_RESULT_SHA256 == "7b31b817a324bb874f24e270b1446b03e142dc1ea0f71edf45da14504ce7d5a2"
    assert value.CEILING["native_endpoint_contact_cardinality"] == "unproven"


def test_exact_package_admission_rejects_extra_contract_and_forged_metrics(monkeypatch, tmp_path: Path):
    value = module(); fixture = tmp_path / "package"; fixture.mkdir()
    for name in ("README.md", "result.json", "study-contract.json", "verify.py"):
        (fixture / name).write_bytes((VERIFY.parent / name).read_bytes())
    monkeypatch.setattr(value, "HERE", fixture)
    contract = json.loads((fixture / "study-contract.json").read_text()); contract["forged"] = True
    (fixture / "study-contract.json").write_bytes(value.canonical(contract))
    with pytest.raises(ValueError, match="contract/result"):
        value.validate_package()
    (fixture / "study-contract.json").write_bytes((VERIFY.parent / "study-contract.json").read_bytes())
    result = json.loads((fixture / "result.json").read_text()); result["metrics"] = [{"forged": index} for index in range(3)]
    (fixture / "result.json").write_bytes(value.canonical(result))
    with pytest.raises(ValueError, match="contract/result"):
        value.validate_package()


def test_completed_root_replay_matches_the_write_once_result():
    value = module()
    documents = Path(r"C:\Users\Haile\Documents")
    result = value.replay(
        output_root=documents / "cwr-desc13-lower-sol-validation-f1a06c7-20260831a",
        candidate_freeze_root=documents / "cwr-hanna-desc14-candidate-freeze-02bdbf5-20260831a",
        development_freeze_root=documents / "cwr-hanna-broader-freeze-436da1e-20260831a",
        normalized_root=documents / "cwr-hanna-nextwave-normalized-d5e95ba-20260831a",
        materialization_root=documents / "cwr-hanna-v5-mixed-materialization-9bb20be-20260830a",
        frozen_successor_path=documents / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        hanna_csv_path=documents / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
        grok_execution_root=documents / "cwr-desc13-lower-grok-v3-cd67452-20260831a",
        grok_collector_path=documents / "cwr-desc13-lower-grok-v3-cd67452-20260831a.collector.json",
        grok_result_path=documents / "cwr-desc13-lower-grok-v3-cd67452-20260831a.result-v2-final.json",
    )
    persisted = json.loads((VERIFY.parent / "result.json").read_text(encoding="utf-8"))
    assert result == persisted and [row["cells"] for row in result["metrics"]] == [7, 7, 7]
