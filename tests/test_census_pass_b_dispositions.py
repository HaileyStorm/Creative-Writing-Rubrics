"""Independent hash-only provenance, missing-root and immutable-output boundaries."""
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-census-pass-b-dispositions-v1/census.py"
spec = importlib.util.spec_from_file_location("pass_b_dispositions_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path):
    source, control, repo = (tmp_path / name for name in ("source", "control", "repo"))
    for root in (source, control, repo):
        root.mkdir()
    (source / "retained").mkdir()
    # Invalid JSON deliberately proves that private outcome/prose values are never decoded.
    raw = b'not-json PRIVATE-TARGET PRIVATE-PROSE'
    (source / "retained" / "terminal.json").write_bytes(raw)
    public = json.dumps({"observed": {"accepted_units": 9}, "unused": "never exported"}).encode()
    (control / "prior.json").write_bytes(public)
    item = {"id": "parent", "family": "poetry", "root": "source", "locator": "retained",
            "disposition": "verified_historical_metadata", "basis": "fixture metadata only",
            "declared": {"planned_calls": 12}, "artifacts": [
                {"locator": "terminal.json", "sha256": census.sha(raw), "bytes": len(raw)}]}
    recipe = {"policy": census.POLICY, "common_sha256": census.COMMON_SHA256,
              "prior_censuses": [{"id": "E", "root": "control", "locator": "prior.json",
                                  "sha256": census.sha(public), "bytes": len(public),
                                  "counts": {"inherited_accepted_units": "observed.accepted_units"}}],
              "records": [item, {**item, "id": "ancestor", "disposition": "superseded_ancestor",
                                  "parent": "parent"},
                          {**item, "id": "missing", "locator": "absent"}]}
    return recipe, source, control, repo


def test_hash_only_dispositions_do_not_create_native_votes_or_zero_missingness(tmp_path):
    recipe, source, control, repo = fixture(tmp_path)
    before = (source / "retained/terminal.json").read_bytes()
    report, ledger = census.census(recipe, source, control, repo)
    parent, ancestor, missing = report["records"]
    assert parent["observed"]["committed_artifacts"] == 1
    assert ancestor["disposition"] == "superseded_ancestor"
    assert missing["disposition"] == "inaccessible_root" and missing["observed"] is None
    assert missing["declared"] == {"planned_calls": 12}
    assert all(row["new_native_joins"] is None for row in report["records"])
    assert report["prior_censuses"][0]["inherited_counts"] == {"inherited_accepted_units": 9}
    assert report["new_provider_votes"] == report["provider_calls_made"] == 0
    assert report["counts"]["verified_artifacts"] == 2  # Shared ancestor is one artifact.
    assert b'PRIVATE-' not in census.canonical({"report": report, "ledger": ledger})
    assert b'never exported' not in census.canonical(report)
    assert (source / "retained/terminal.json").read_bytes() == before


def test_commitment_missing_metadata_and_fresh_output_boundaries(tmp_path):
    recipe, source, control, repo = fixture(tmp_path)
    artifact = source / "retained/terminal.json"
    artifact.write_bytes(b'changed')
    with pytest.raises(ValueError, match="Source hash differs"):
        census.census(recipe, source, control, repo)
    artifact.unlink()
    report, _ = census.census(recipe, source, control, repo)
    assert report["records"][0]["disposition"] == "unresolved_missing_metadata"
    assert report["records"][0]["missing_commitments"] == 1
    roots = {"source": source, "control": control, "repository": repo}
    with pytest.raises(ValueError, match="retained source"):
        census.output_path(source / "retained/new", recipe, roots)
    with pytest.raises(ValueError, match="fresh"):
        census.output_path(source, recipe, roots)
    assert census.output_path(tmp_path / "new-output", recipe, roots) == tmp_path / "new-output"
    assert not (tmp_path / "new-output").exists()
