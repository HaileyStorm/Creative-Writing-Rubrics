from copy import deepcopy
import importlib.util
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from hbqrs import core, runner, ladder_uncertainty, decision_readiness


HERE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-mfa-conditional-benchmark-v1"
spec = importlib.util.spec_from_file_location("conditional_analysis_test", HERE / "analysis.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def test_complete_bank_original_native_and_release_boundaries(modules, bundle_by_id, tmp_path, monkeypatch):
    bundle = bundle_by_id["prose.short_form"]
    contract = {"contract_version": 1, "contract_id": "synthetic", "artifact_id": "synthetic",
        "context": {"artifact_kind": "prose_fiction", "declared_scope": "passage", "completion_status": "excerpt", "background": [], "constraints": [], "audience": []},
        "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}
    compiled = core.compile_bundle(modules, bundle, task_contract=contract)
    ids = [q["question"]["id"] for q in core.compiled_questions(compiled)]
    assert len(ids) == 170
    rows, admitted = [], []
    for i in range(22):
        row = {"batch": i + 1, "question_ids": ids[i * 8:(i + 1) * 8], "request_sha256": a.sha(str(i).encode()),
            "endpoint": "sol", "artifact_id": "synthetic", "bundle_id": "prose.short_form", "logical_sample_id": str(i),
            "task_contract_path": "contract.json", "task_contract_sha256": a.sha(a.canonical(contract)), "sources": [{"id": "synthetic"}]}
        payload = {"verdicts": [{"question_id": q, "verdict": "YES", "confidence": 1, "note": "",
            "evidence": [{"kind": "summary", "reference": "synthetic", "summary": "Synthetic evidence.", "exact_quote": None}]} for q in row["question_ids"]]}
        rows.append(row)
        admitted.append({"request": row, "response": payload, "replay": {"original_strict_native_verified": True}})
    c = SimpleNamespace(pinned=lambda *args: a.canonical(contract), inputs=lambda *args: (b"", b"", {"synthetic": "Synthetic evidence."}, "Synthetic context."))
    runtime = {"core": core, "runner": runner, "ladder": ladder_uncertainty, "readiness": decision_readiness, "modules": modules, "bundle": bundle}
    manifest = {"artifacts": {"contract.json": {}}}
    before = deepcopy((rows, admitted))
    scored = a.score_bank(c, rows, admitted, runtime, tmp_path, manifest)
    assert scored["provenance"]["original_admission_count"] == 1 and scored["provenance"]["new_native_votes"] == 0
    assert scored["historical"]["score"] is not None and scored["candidate"]["score"] is not None
    assert (rows, admitted) == before
    assert a.score_bank(c, rows, admitted[:-1], runtime, tmp_path, manifest)["candidate"]["score"] is None
    bad = deepcopy(admitted)
    bad[0]["replay"]["original_strict_native_verified"] = False
    with pytest.raises(ValueError, match="Native complete-bank"):
        a.score_bank(c, rows, bad, runtime, tmp_path, manifest)
    sample = tmp_path / "native"
    sample.mkdir()
    receipt = {"thread_id": "own-thread", "turn_id": "own-turn"}
    receipt_raw = a.canonical(receipt)
    (sample / "receipt.json").write_bytes(receipt_raw)
    native = {"reported": {"session_id": "own-thread"}, "provider_artifacts": {"codex_receipt": {
        "path": "receipt.json", "sha256": a.sha(receipt_raw), "bytes": len(receipt_raw)}}}
    (sample / "native-result.json").write_bytes(a.canonical(native))
    (sample / "native-identity.json").write_bytes(a.canonical({"session_id": None, "logical_sample_id": "original"}))
    own = SimpleNamespace(SETTLED={"accepted", "semantic_rejected"}, pinned=lambda root, path, meta: a.checked(root / path, meta["sha256"]))
    assert a.native_identity(own, sample, {"endpoint": "sol", "logical_sample_id": "original"}, {"state": "accepted"}) == "own-thread"
    native["reported"]["session_id"] = "foreign-thread"
    (sample / "native-result.json").write_bytes(a.canonical(native))
    with pytest.raises(ValueError, match="Own strict native identity"):
        a.native_identity(own, sample, {"endpoint": "sol", "logical_sample_id": "original"}, {"state": "accepted"})
    ledger = [{"endpoint": e, "logical_sample_id": str(i), "terminal_verified": True, "state": "semantic_rejected"}
              for e in ("sol", "grok") for i in range(5170)]
    outers = {e: {"verified": True} for e in ("sol", "grok")}
    a.label_gate(ledger, outers, True)
    for explicit, entries, outer in ((False, ledger, outers), (True, ledger[:-1], outers), (True, ledger, {})):
        with pytest.raises(ValueError, match="10340 verified terminals"):
            a.released_ballots(SimpleNamespace(), {}, tmp_path / "absent-sealed-source", entries, outer, explicit)
    read = []
    monkeypatch.setattr(a, "metadata_view", lambda p: read.append(p) or {})
    with pytest.raises(ValueError, match="Metadata mode"):
        a.main(["--manifest", "unused", "--metadata-only", "--sealed-source-root", "unopened"])
    assert not read
    extract = a.load_module("conditional_label_fixture_extract", HERE / "extract.py")
    decoded = []
    class Projection(extract.SourceProjection):
        def value(self, begin, end):
            value = super().value(begin, end)
            assert value not in {"UNOPENED_EXCERPT_ONE", "UNOPENED_EXCERPT_TWO", "UNOPENED_RATIONALE"}
            decoded.append(value)
            return value
    source = {"target": {"writer": [["unused", "rater", {"id": i, "Excerpt1": "UNOPENED_EXCERPT_ONE", "Excerpt2": "UNOPENED_EXCERPT_TWO",
                 "Reason": "UNOPENED_RATIONALE", "Preference": "Excerpt1" if i % 2 == 0 else "Excerpt2"}] for i in range(3276)]}}
    raw = a.canonical(source)
    source_root = tmp_path / "source"
    source_path = source_root / "author-style/data/synthetic.json"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(raw)
    hashes = [a.sha(v.encode()) for v in ("UNOPENED_EXCERPT_ONE", "UNOPENED_EXCERPT_TWO")]
    rows, planned = [], []
    for i in range(3276):
        row = {"target_hash": a.sha(a.canonical("target")), "writer_hash": a.sha(a.canonical("writer")),
            "rater_hash": a.sha(a.canonical("rater")), "panel": "expert", "condition": "fewshot", "source_path": "data/synthetic.json",
            "source_position": i, "target_position": 0, "writer_position": 0, "judgment_identity_hash": a.sha(a.canonical(i)), "excerpt_hashes": hashes}
        ballot = {k: row[k] for k in ("target_hash", "writer_hash", "rater_hash", "panel", "condition", "source_path", "source_position", "target_position", "writer_position")}
        ballot.update(metadata_row_sha256=a.sha(a.canonical(row)), source_field="Preference", pair_id="pair")
        ballot["ballot_id"] = a.sha(a.canonical(ballot))
        rows.append(row)
        planned.append(ballot)
    receipt = {"path": "data/synthetic.json", "sha256": a.sha(raw), "bytes": len(raw),
        "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
    selection = {"partition": "confirmation", "metadata_rows": rows, "planned_ballots": planned, "source_receipts": [receipt],
        "pairs": [{"pair_id": "pair", "excerpt_hashes": sorted(hashes), "planned_ballot_ids": [b["ballot_id"] for b in planned]}]}
    def pinned(root, path, meta):
        content = (root / path).read_bytes()
        a.require(len(content) == meta["bytes"] and a.sha(content) == meta["sha256"], "Frozen source differs")
        return content
    reader = SimpleNamespace(sha=a.sha, canonical=a.canonical, pinned=pinned, prepare=SimpleNamespace(extract=SimpleNamespace(SourceProjection=Projection)))
    released = a.released_ballots(reader, selection, source_root, ledger, outers, True)
    assert len(released) == 3276 and all(b["human_state"] == "BINARY" for b in released)
    canonical_left = sorted(hashes)[0]
    assert released[0]["winner"] == ("LEFT" if hashes[0] == canonical_left else "RIGHT")
    assert released[1]["winner"] == ("LEFT" if hashes[1] == canonical_left else "RIGHT")
    source_path.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="Frozen source"):
        a.released_ballots(reader, selection, source_root, ledger, outers, True)


def test_paired_target_inference_all_planned_attrition_and_crossed_leaveouts():
    ballots, decisions = [], {}
    for t in range(10):
        for j in range(2):
            ballots.append({"ballot_id": f"{t}-{j}", "panel": "expert", "condition": "fewshot", "target_hash": str(t),
                "pair_id": str(t), "writer_hash": str(t % 2), "rater_hash": str(j), "human_state": "BINARY", "winner": "LEFT"})
        for arm in a.VIEWS:
            decisions[("sol", arm, str(t), 0)] = "RIGHT" if arm == "historical" else "LEFT"
    result = a.stratum_inference(ballots, decisions, "sol", "expert", "fewshot", a.profile())
    assert result["point_gain"] == 1 and result["paired_target_cluster_95_percent_interval"] == [1, 1]
    assert result["expert_numeric_guard"] and not result["candidate_promoted"]
    assert result["metrics"]["candidate"]["planned_ballots"] == 20
    assert result["crossed_sensitivity"]["rater_hash"]["range"] == [1, 1]
    missing = dict(decisions)
    missing[("sol", "candidate", "0", 0)] = "MISSING_OR_ABSTAINED"
    lost = a.stratum_inference(ballots, missing, "sol", "expert", "fewshot", a.profile())
    assert lost["point_gain"] == .9 and not lost["coverage_guard"] and not lost["attrition_guard"] and not lost["expert_numeric_guard"]
    assert lost["metrics"]["candidate"]["best_worst_bounds"] == [.9, 1]
    assert lost["metrics"]["candidate"]["all_planned_accuracy"] == .9
    assert lost["metrics"]["candidate"]["complete_case_denominator"] == 18
    assert lost["metrics"]["candidate"]["complete_case_correct"] == 18
    assert lost["metrics"]["candidate"]["complete_case_accuracy"] == 1
    assert lost["metrics"]["candidate"]["nondeterminate_prediction_ballots"] == 2
    # A pooled improvement cannot hide dependence on a single reused writer.
    dependent = dict(decisions)
    for t in range(1, 10):
        dependent[("sol", "historical", str(t), 0)] = "LEFT"
    sensitive = [{**b, "writer_hash": "sole-gain" if b["target_hash"] == "0" else "other"} for b in ballots]
    s = a.stratum_inference(sensitive, dependent, "sol", "expert", "fewshot", a.profile())
    assert s["point_gain"] == .1 and not s["crossed_sensitivity"]["writer_hash"]["guard_pass"] and not s["expert_numeric_guard"]
    ties = dict(decisions)
    ties[("sol", "candidate", "0", 0)] = "TIE"
    tie = a.stratum_inference(ballots, ties, "sol", "expert", "fewshot", a.profile())
    assert tie["metrics"]["candidate"]["complete_targets"] == 10 and tie["metrics"]["candidate"]["correct"] == 18
    assert tie["metrics"]["candidate"]["complete_case_denominator"] == 20
    assert tie["metrics"]["candidate"]["complete_case_correct"] == 18
    assert tie["metrics"]["candidate"]["complete_case_accuracy"] == .9
