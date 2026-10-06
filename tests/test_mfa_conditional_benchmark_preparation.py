from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "evaluation-results/hbq-mfa-conditional-benchmark-v1"
spec = importlib.util.spec_from_file_location("conditional_benchmark_prepare_test", HERE / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
extract = prepare.extract


def digest(value):
    return extract.sha(extract.canonical(value))


def test_positional_projection_never_decodes_labels_unknown_values_or_unselected_prose(monkeypatch):
    record = {"Excerpt1": "synthetic first", "Excerpt2": "synthetic second", "id": "id-1",
              "Preference": "DO_NOT_DECODE_PREFERENCE", "win": "DO_NOT_DECODE_WIN",
              "Reason": "DO_NOT_DECODE_REASON", "key": {"Human_Author": "DO_NOT_DECODE_ORIGIN"},
              "new_field": [{"nested": "DO_NOT_DECODE_UNKNOWN"}]}
    skipped = {"Excerpt1": "DO_NOT_DECODE_UNSELECTED_PROSE", "Preference": "DO_NOT_DECODE_UNSELECTED_LABEL"}
    raw = json.dumps({"unselected": {"unselected_writer": [[0, "unselected_rater", skipped]]},
                      "selected": {"writer": [[0, "rater", record], [0, {**record, "user": "lay-rater"}]]}}).encode()
    base = {"target_position": 1, "target_hash": digest("selected"), "writer_position": 0,
            "writer_hash": digest("writer"), "judgment_identity_hash": digest("id-1"),
            "excerpt_hashes": [extract.sha(t.encode()) for t in ("synthetic first", "synthetic second")],
            "excerpt_bytes": [len(t.encode()) for t in ("synthetic first", "synthetic second")]}
    rows = [{**base, "panel": "expert", "source_position": 0, "rater_hash": digest("rater")},
            {**base, "panel": "lay", "source_position": 1, "rater_hash": digest("lay-rater")}]
    original = json.JSONDecoder.raw_decode
    decoded = []

    def observed(self, text, index=0):
        value, end = original(self, text, index)
        decoded.append(value)
        return value, end

    monkeypatch.setattr(json.JSONDecoder, "raw_decode", observed)
    result = extract.SourceProjection(raw).selected_texts(rows)
    assert result == {extract.sha(t.encode()): t.encode() for t in ("synthetic first", "synthetic second")}
    assert not any(isinstance(v, str) and v.startswith("DO_NOT_DECODE") for v in decoded)
    assert not any(isinstance(v, (dict, list)) for v in decoded)
    bad = deepcopy(rows)
    bad[0]["rater_hash"] = digest("different rater")
    with pytest.raises(ValueError, match="Rater or judgment"):
        extract.SourceProjection(raw).selected_texts(bad)


def test_membership_preserves_lay_only_ballot_and_primary_vs_sentinel_request_geometry():
    policy, _ = extract.profile()
    policy = deepcopy(policy)
    targets = [digest("fine target"), digest("fewshot-only target")]
    pairs = [[extract.sha(x.encode()) for x in ("first fine", "second fine")],
             [extract.sha(x.encode()) for x in ("first few", "second few")]]
    rows, units, receipts = [], [], []
    for index, (panel, condition, which) in enumerate((("expert", "finetuned", 0), ("lay", "finetuned", 0), ("lay", "fewshot", 1))):
        path = f"data/quality_{condition}_{panel}_anon.json"
        source = policy["source_files"][path]
        receipts.append({"release": "author-style", "path": path, **source})
        row = {k: None for k in extract.ROW_FIELDS}
        row.update(release="author-style", task="quality", panel=panel, condition=condition,
                   target_hash=targets[which], writer_hash=digest("writer"), rater_hash=digest(str(index)),
                   excerpt_hashes=pairs[which], excerpt_bytes=[10, 11], ordered_pair_hash=digest(pairs[which]),
                   pair_hash=digest(sorted(pairs[which])), source_path=path, target_position=which,
                   writer_position=0, source_position=0, judgment_identity_hash=digest("id"))
        rows.append(row)
        units.append({"release": "author-style", "task": "quality", "panel": panel, "condition": condition,
                      "target_hash": targets[which], "candidate_excerpt_hashes": sorted(pairs[which]),
                      "partition": "confirmation", "eligible": True, "row_original_hash": None,
                      "rows": 1, "unit_sha256": digest(index),
                      "row_memberships": [{"metadata_row_sha256": digest(row), "writer_hash": row["writer_hash"],
                                           "ordered_pair_hash": row["ordered_pair_hash"]}]})
    ledger = {"components": [{"target_hashes": [t], "text_hashes": pair, "partition": "confirmation",
                               "forced_development": False} for t, pair in zip(targets, pairs)], "evaluation_units": units}
    policy["expected"].update(targets=2, fine_targets=1, unique_texts=4, pairs=2, evaluation_units=3, metadata_rows=3, lay_only_pairs=1)
    selection = extract.select(rows, ledger, receipts, policy)
    assert len(selection["planned_ballots"]) == 3
    assert {b["source_field"] for b in selection["planned_ballots"]} == {"Preference"}
    assert {b["fine_model_variant"] for b in selection["planned_ballots"]} == {"UNKNOWN"}
    assert sum(p["panels"] == ["lay"] for p in selection["pairs"]) == 1
    bad_receipts = deepcopy(receipts)
    bad_receipts[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Source receipt differs"):
        extract.select(rows, ledger, bad_receipts, policy)
    overlapping = deepcopy(ledger)
    overlapping["components"].append({"target_hashes": [digest("development")], "text_hashes": [pairs[0][0]],
                                      "partition": "development", "forced_development": False})
    with pytest.raises(ValueError, match="Text crosses partitions"):
        extract.select(rows, overlapping, receipts, policy)
    geometry = {"texts": [{"id": str(n)} for n in range(199)], "pairs": [{"pair_id": str(n)} for n in range(145)],
                "bank_sentinel_ids": ["0", "1"], "pair_sentinel_ids": ["0", "1"]}
    planned = prepare.request_units(geometry)
    primary = [u for u in planned if u["repeat"] == 0]
    assert {u["artifact_id"] for u in primary if u["arm"] == "hbq"} == {str(n) for n in range(199)}
    assert sum(22 if u["arm"] == "hbq" else 1 for u in primary) == 5066
    repeats = [u for u in planned if u["repeat"] != 0]
    assert {u["artifact_id"] for u in repeats} == {"0", "1"}
    assert sum(22 if u["arm"] == "hbq" else 1 for u in repeats) == 104
