from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-nonwinner-extension-result-v1" / "verify.py"


def module():
    spec = importlib.util.spec_from_file_location("_desc15_sol_extension_result_test", VERIFY)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def inputs() -> dict[str, Path]:
    documents = Path(r"C:\Users\Haile\Documents")
    return {
        "output_root": documents / "cwr-desc15-sol-nonwinner-extension-5f4fbe1-20260901a",
        "candidate_freeze_root": documents / "cwr-hanna-desc14-candidate-freeze-02bdbf5-20260831a",
        "development_freeze_root": documents / "cwr-hanna-broader-freeze-436da1e-20260831a",
        "normalized_root": documents / "cwr-hanna-nextwave-normalized-d5e95ba-20260831a",
        "materialization_root": documents / "cwr-hanna-v5-mixed-materialization-9bb20be-20260830a",
        "frozen_successor_path": documents / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
        "hanna_csv_path": documents / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
        "grok_execution_root": documents / "cwr-desc13-lower-grok-v3-cd67452-20260831a",
        "grok_collector_path": documents / "cwr-desc13-lower-grok-v3-cd67452-20260831a.collector.json",
        "grok_result_path": documents / "cwr-desc13-lower-grok-v3-cd67452-20260831a.result-v2-final.json",
    }


def test_equal_group_metrics_require_three_children_and_seven_groups():
    value = module()
    groups = {candidate: {f"group-{index}": 1.0 + index for index in range(7)} for candidate in value.CHILDREN}
    rows, comparisons = value._metrics(groups, {value.BASELINE: 2.0, value.PARENT: 1.5})
    assert len(rows) == 3 and set(comparisons) == set(value.CHILDREN)
    with pytest.raises(ValueError, match="incomplete"):
        value._metrics({candidate: {} for candidate in value.CHILDREN}, {value.BASELINE: 2.0, value.PARENT: 1.5})
    groups[value.CHILDREN[1]] = {f"different-{index}": 1.0 + index for index in range(7)}
    with pytest.raises(ValueError, match="incompatible"):
        value._metrics(groups, {value.BASELINE: 2.0, value.PARENT: 1.5})


def test_native_json_rejects_duplicate_keys_and_write_once_rejects_a_second_write(tmp_path: Path):
    value = module()
    with pytest.raises(ValueError, match="invalid"):
        value.native_json(b'{"scores":{},"scores":{}}', "native")
    output = tmp_path / "result.json"
    value.write_result(output, {"value": 1})
    with pytest.raises(ValueError, match="fresh"):
        value.write_result(output, {"value": 1})


def test_pinned_extension_executor_and_scope_are_explicit():
    value = module()
    assert value.SOURCE_COMMIT == "5f4fbe1f3fe9e52a2c2082495a2d2e9ff973d9d4"
    assert value.SOURCE_FILES["executor.py"] == "da7b95115265d6c7a7eda1d1893357d871c08e353b53caccbbae516ac40df8e4"
    assert value.CEILING["native_endpoint_contact_cardinality"] == "unproven"


def test_completed_root_replay_matches_the_write_once_result():
    value = module()
    replayed = value.replay(**inputs())
    persisted = json.loads((VERIFY.parent / "result.json").read_text(encoding="utf-8"))
    external = Path(r"C:\Users\Haile\Documents\cwr-desc15-sol-nonwinner-extension-5f4fbe1-20260901a.result-v2.json")
    assert persisted["external_result_v1_sha256"] == "9535cc9e9c4dc732778e2b26503a855cf72a38581347408dfd8970dd8ddeb775"
    assert value.sha256(external.read_bytes()) == persisted["external_result_sha256"]
    assert value.sha256(replayed) == persisted["external_result_sha256"]
    assert json.loads(external.read_text(encoding="utf-8")) == replayed
    assert replayed["coverage"] == persisted["coverage"]
    assert [{key: row[key] for key in ("candidate_id", "cells", "equal_group_mae")} for row in replayed["metrics"]] == [
        {key: row[key] for key in ("candidate_id", "cells", "equal_group_mae")} for row in persisted["metrics"]
    ]
    assert [row["cells"] for row in replayed["metrics"]] == [7, 7, 7]
    assert replayed["evidence_ceiling"]["process_lifecycle_receipts"] == 21
