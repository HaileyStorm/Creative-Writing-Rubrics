"""Synthetic chain and label-boundary witnesses; no native/provider claims."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import Mock

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ttcw_chain_test", REPO / "evaluation-results/hbq-matched-ttcw-20261004/analysis_chain.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def rows():
    return [{"endpoint": endpoint, "endpoint_ordinal": n, "logical_sample_id": endpoint + str(n),
             "request_sha256": endpoint + "-request-" + str(n)} for endpoint in ("sol", "grok") for n in (1, 2)]


def record(row, state="accepted"):
    return {"request": row, "state": state, "accepted": {"response": "synthetic"} if state == "accepted" else None,
            "terminal_sha256": "terminal-" + row["logical_sample_id"], "source_index": 0}


def test_join_retains_original_missing_denominator_and_failure_not_replacement():
    originals = a.planned_rows({"requests": rows()}, expected=4)
    left, right = rows()[:2]
    joined = a.merge([{("sol", left["logical_sample_id"]): record(left)},
                      {("sol", right["logical_sample_id"]): record(right, "unadmitted_no_resend")}], originals)
    assert len(joined) == 4
    assert [v["state"] for v in joined.values()] == ["accepted", "unadmitted_no_resend", "not_collected", "not_collected"]
    with pytest.raises(ValueError, match="Duplicate attempted"):
        a.merge([{("sol", left["logical_sample_id"]): record(left, "ambiguous")},
                 {("sol", left["logical_sample_id"]): record(left)}], originals)


@pytest.mark.parametrize("change", ["duplicate", "ordinal", "endpoint"])
def test_original_geometry_cannot_narrow_or_duplicate(change):
    planned = rows()
    if change == "duplicate": planned[1]["logical_sample_id"] = planned[0]["logical_sample_id"]
    elif change == "ordinal": planned[1]["endpoint_ordinal"] = 3
    else: planned[1]["endpoint"] = "grok"
    with pytest.raises(ValueError): a.planned_rows({"requests": planned}, expected=4)


def test_chain_lineage_binds_all_prior_outcomes_and_terminal_hashes():
    prior = {("sol", row["logical_sample_id"]): record(row, "semantic_rejected") for row in rows()[:2]}
    receipts = [{"endpoint_ordinal": rec["request"]["endpoint_ordinal"], "logical_sample_id": rec["request"]["logical_sample_id"],
                 "request_sha256": rec["request"]["request_sha256"], "terminal_sha256": rec["terminal_sha256"]} for rec in prior.values()]
    source = {"continuation": {"reserved_through_endpoint_ordinal": 2, "reserved_endpoint": "sol",
        "no_resend_reserved_prefix": True, "prefix_receipts": receipts, "prefix_jobs": [{"job_sha256": "job-one"}]}}
    a.lineage(source, "sol", prior, ["job-one"])
    receipts[1]["terminal_sha256"] = "changed"
    with pytest.raises(ValueError, match="lineage"):
        a.lineage(source, "sol", prior, ["job-one"])
    receipts[1]["terminal_sha256"] = prior[("sol", "sol2")]["terminal_sha256"]
    with pytest.raises(ValueError, match="source-job"):
        a.lineage(source, "sol", prior, ["wrong-job"])


@pytest.mark.parametrize("state", ["not_collected", "in_progress_or_unresolved", "unknown"])
def test_labels_remain_closed_for_any_unsettled_planned_slot(state):
    joined = {str(n): {"state": "accepted"} for n in range(4)}
    joined["3"]["state"] = state
    with pytest.raises(ValueError, match="every original planned"):
        a.label_release_gate(joined, expected=4)
    joined["3"]["state"] = "completed_schema_rejected"
    a.label_release_gate(joined, expected=4)


def test_release_checks_full_denominator_before_label_reader_or_scorer():
    old = SimpleNamespace(load_labels=Mock(side_effect=AssertionError("Labels opened prematurely")))
    with pytest.raises(ValueError):
        a.release_labels({}, {"one": {"state": "accepted"}}, {}, {}, {"analysis": old}, Path("sealed-never-opened"))
    old.load_labels.assert_not_called()


def test_named_receipt_cannot_add_vote_or_silently_promote_an_already_accepted_slot(tmp_path):
    loaded = a.modules()
    prepare = loaded["prepare"]
    row = rows()[2]
    path = tmp_path / "receipt.json"
    saved = {"logical_sample_id": row["logical_sample_id"], "no_resend": True, "endpoint": "grok"}
    path.write_bytes(prepare.canonical(saved))
    joined = {("grok", row["logical_sample_id"]): record(row)}
    with pytest.raises(ValueError, match="one original failed slot"):
        a.apply_reconciliation({"path": str(path), "sha256": prepare.digest(path.read_bytes())}, joined, [], {}, loaded, None)


def test_legacy_imports_preserve_other_study_namespaces_and_strict_missing_bank_behavior():
    previous = sys.modules.get("prepare")
    sentinel = SimpleNamespace(other_study=True)
    sys.modules["prepare"] = sentinel
    try:
        loaded = a.modules()
        assert sys.modules["prepare"] is sentinel
        old = loaded["analysis"]
        scorer = SimpleNamespace(score_bundle=Mock(side_effect=AssertionError("Incomplete bank scored")))
        report = old.score_story("hbq", [], {"core": scorer, "questions": []})
        assert report["score"] is None and report["state"] == "incomplete_native_packets_no_score"
        scorer.score_bundle.assert_not_called()
        assert old.BOOTSTRAP_SEED == 20261004
    finally:
        if previous is None: sys.modules.pop("prepare", None)
        else: sys.modules["prepare"] = previous
