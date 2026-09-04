from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v14-dspy-train-pilot-v1" / "diagnostics.py"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def module():
    spec = importlib.util.spec_from_file_location("v14_train_diagnostics", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def report(endpoint: str, *, partition: str = "train") -> dict:
    value = {"endpoint": endpoint, "authority": {"endpoint_pooling": "forbidden"}, "cells": []}
    for item in range(44):
        target = 1 + item / 100
        for candidate in (CHILD, DESCENDANT):
            score = target + 0.5 if candidate == CHILD else 1.0
            value["cells"].append({"cell_id": f"{endpoint}-{candidate}-{item}", "candidate_id": candidate, "item_id": f"item-{item}", "prompt_group_id": f"group-{item % 22}", "partition": partition, "scores": {dimension: score for dimension in DIMS}, "target": {dimension: target for dimension in DIMS}})
    return value


def test_ties_bias_and_half_credit_concordance_are_explicit():
    value = module()
    result = value.diagnose(grok_report=report("grok_primary"), sol_report=report("sol_later"))
    child = result["endpoints"]["grok_primary"]["metrics"][CHILD]["Relevance"]
    descendant = result["endpoints"]["grok_primary"]["metrics"][DESCENDANT]["Relevance"]
    assert child["mean_signed_error"] == pytest.approx(0.5)
    assert child["item_weighted_mae"] == pytest.approx(0.5)
    assert child["correct_pair_count"] == child["human_nontied_pair_count"] == 946
    assert descendant["correct_pair_count"] == descendant["reversed_pair_count"] == 0
    assert descendant["model_tied_pair_count"] == descendant["human_nontied_pair_count"] == 946
    assert descendant["pair_accuracy"] == 0
    assert descendant["half_credit_tie_concordance"] == pytest.approx(0.5)


def test_diagnostic_is_cell_order_symmetric():
    value = module(); grok, sol = report("grok_primary"), report("sol_later")
    expected = value.diagnose(grok_report=grok, sol_report=sol)
    grok_reverse, sol_reverse = copy.deepcopy(grok), copy.deepcopy(sol)
    grok_reverse["cells"].reverse(); sol_reverse["cells"].reverse()
    assert value.diagnose(grok_report=grok_reverse, sol_report=sol_reverse) == expected


@pytest.mark.parametrize("mutate", ["geometry", "partition", "aggregate_only"])
def test_rejects_nonfrozen_geometry_or_partition(mutate: str):
    value = module(); grok, sol = report("grok_primary"), report("sol_later")
    if mutate == "geometry":
        grok["cells"].pop()
    elif mutate == "partition":
        sol["cells"][0]["partition"] = "development"
    else:
        grok["metrics"] = []; del grok["cells"]
    with pytest.raises(ValueError):
        value.diagnose(grok_report=grok, sol_report=sol)
