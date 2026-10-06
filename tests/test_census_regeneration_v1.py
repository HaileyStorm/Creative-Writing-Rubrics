import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("regeneration_test", ROOT /
    "evaluation-results/hbq-census-pass-b-dispositions-v1/regenerate_v1.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def test_multiple_ancestor_and_representation_edges_never_dispatch_or_add_votes():
    cohorts = [{"id": "observed", "interface": "run"},
               {"id": "metadata", "interface": "five_root"}]
    registry = {"declaration_packages": [
        {"id": p, "locator": p, "artifact_commitments": []} for p in ("ancestor", "current", "nonvoting", "metadata")],
        "coverage_edges": [
            {"source_type": "declaration_package", "source": "ancestor", "relationship": "excluded_ancestor", "census": "observed"},
            {"source_type": "declaration_package", "source": "current", "relationship": "joins_existing_positions", "census": "observed"},
            {"source_type": "declaration_package", "source": "current", "relationship": "replaces_declaration", "census": "observed"},
            {"source_type": "declaration_package", "source": "nonvoting", "relationship": "nonvoting_output", "census": "observed"},
            {"source_type": "declaration_package", "source": "metadata", "relationship": "metadata_membership_only", "census": "metadata"}]}
    assert len(r.owned_cohorts({"cohorts": cohorts})) == 2
    packages = r.package_dispositions(registry, cohorts)
    assert packages[1]["regeneration_cohorts"] == ["observed"]
    assert sum(p["additional_observed_votes_from_declaration"] for p in packages) == 0
    with pytest.raises(ValueError, match="Duplicate cohort"):
        r.owned_cohorts({"cohorts": cohorts + [cohorts[0]]})


def test_changed_implementation_pin_rejects_before_import_or_observation(tmp_path, monkeypatch):
    path = tmp_path / "adapter.py"
    path.write_bytes(b"raise AssertionError('must not import')")
    item = {"id": "one", "interface": "run", "implementation": {
        "root": "repository", "locator": "adapter.py", "bytes": path.stat().st_size, "sha256": "0" * 64}}
    monkeypatch.setattr(r, "load", lambda *args: pytest.fail("pin failure must precede import"))
    with pytest.raises(ValueError, match="Source pin differs"):
        r.invoke(item, {"repository": tmp_path})


def test_retained_f_prefix_joins_existing_position_once_without_nonnative_identity():
    identity = {"request_id_hash": "a" * 64, "session_id_hash": "b" * 64}
    def row(ordinal, proof):
        return {"ordinal": ordinal, "pass_id_sha256": "c" * 64, "source_sha256": "d" * 64,
                "historical_replay_input_commitments_sha256": "e" * 64, "question_ids": ["leaf"],
                "leaves": [{"question_id": "leaf", "verdict": "YES"}], "proof": proof}
    base = {"positions": [row(1, {"native_identity": identity}), row(2, None)],
            "ordinary_native_identities": [identity], "historical_excluded_native_identities": []}
    joined = [row(2, {"native_identity": None, "disposition": "adopted_projection_without_native_identity"})]
    counts = r.f_membership(base, joined)
    assert counts["logical_positions"] == counts["ordered_metadata_leaves"] == 2
    assert counts["native_identity_members"] == 1 and counts["new_votes_from_prefix_join"] == 0
    with pytest.raises(ValueError, match="second observation"):
        r.f_membership(base, [row(1, {"native_identity": identity})])


def test_reuse_rejects_changed_retained_source_before_saved_artifact_reads(tmp_path):
    item = {"id": "native_f", "implementation": {"sha256": "a" * 64},
            "recipe": {"sha256": "b" * 64}, "retained_metadata": {"base_ledger": {"sha256": "c" * 64}}}
    receipt = {"implementation_sha256": "a" * 64, "recipe_sha256": "b" * 64,
               "cohort_descriptor_sha256": r.sha(r.canonical(item))}
    item["retained_metadata"]["base_ledger"]["sha256"] = "d" * 64
    with pytest.raises(ValueError, match="Reuse cohort pins differ"):
        r.reuse_cohort(item, tmp_path, receipt)
