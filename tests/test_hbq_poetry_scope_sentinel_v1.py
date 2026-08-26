from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-scope-sentinel-v1"

ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason=(
        "Archived renderer mechanics require the frozen production runtime, "
        "which no longer matches the current CWR checkout."
    )
)


def load_study():
    spec = importlib.util.spec_from_file_location("poetry_scope_sentinel_study", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_checkout_fails_closed_before_archival_mechanics():
    with pytest.raises(ValueError, match="Current production runtime binding drifted"):
        load_study().verify_package()


def test_frozen_s1_subset_preserves_exact_four_state_geometry_and_no_provider_mode():
    s = load_study()
    contract = s.load_contract()
    assert contract["study_id"] == "hbq-poetry-scope-sentinel-v1"
    assert contract["status"] == "frozen_development_only_poetry_scope_sentinel"
    assert contract["development_only"] is True
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}
    assert contract["geometry"] == {"leaves_exact": 5, "states_exact": 4, "artifacts_exact": 20, "repeats_exact": 3, "slots_exact": 60}
    assert contract["promotion"] == {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight", "influence")}
    s.verify_corpus(s.load_corpus())
    slots = s.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 60
    assert {slot["leaf_id"] for slot in slots} == set(s.LEAVES)
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["state"] for slot in slots} == set(s.STATES)
    assert {slot["expected_verdict"] for slot in slots} == set(s.STATE_VERDICTS.values())
    assert s.load_contract()["portfolio_binding"]["additive_to_portfolio"] is False


def test_live_leaf_ownership_audit_findings_and_rejected_polarity_context_are_bound():
    s = load_study()
    contract = s.load_contract()
    observed = s.source_leaf_hashes()
    expected = contract["bindings"]["source_leaves"]
    assert set(observed) == set(expected) == set(s.LEAVES)
    changed = "form.poetry.free_verse.repetition"
    assert observed[changed] != expected[changed]
    assert all(observed[leaf] == expected[leaf] for leaf in s.LEAVES if leaf != changed)
    assert contract["portfolio_binding"]["leaf_findings"] == s.FINDING_IDS
    assert contract["rejected_context"] == {
        "finding_id": "f69aee26f88757d6d364c34b4d921d764cf7944ed0e896f3e18a9189ffe7e8aa",
        "controlling": False,
        "reason": "positive YES orientation remains correct",
    }
    records = s.source_leaf_records()
    assert records["form.poetry.haiku_in_english.sequence_scope"]["pass_answer"] == "YES"
    assert records["form.poetry.pantoum.recontext"]["weight"] == 3.0
    assert records["form.poetry.haiku_in_english.sequence_scope"]["applies_when"] == "The artifact is a multi-stanza sequence and the profile permits one seasonal reference across the sequence."
    assert records["form.poetry.haiku_in_english.sequence_scope"]["evidence_policy"] == {
        "required": True,
        "minimum_references": 1,
        "reference_style": "artifact span, unit ID, timestamp, or source ID",
    }


def test_carriers_keep_scope_separate_from_state_and_cover_complete_excerpt_unknown():
    s = load_study()
    corpus = s.load_corpus()["artifacts"]
    carriers = [s.FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])] for artifact in corpus]
    assert s.load_contract()["carrier_axes"] == {
        "completion_status": ["complete", "excerpt"],
        "parent_status": ["complete", "unknown"],
        "evaluation_scope": ["stanza", "poem", "sequence", "non_poetry"],
        "independent_carrier_metadata": True,
    }
    assert {carrier["completion_status"] for carrier in carriers} == {"complete", "excerpt"}
    assert {carrier["parent_status"] for carrier in carriers} == {"complete", "unknown"}
    assert {carrier["evaluation_scope"] for carrier in carriers} == {"stanza", "poem", "sequence", "non_poetry"}
    for artifact in corpus:
        carrier = s.FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]
        if artifact["state"] in {"localized_issue", "material_failure"}:
            assert carrier["completion_status"] == carrier["parent_status"] == "complete"
        elif artifact["state"] == "missing_required_evidence":
            assert (carrier["completion_status"], carrier["evaluation_scope"], carrier["parent_status"]) == ("excerpt", "stanza", "unknown")
            assert "unavailable" in " ".join(artifact["contexts"]).lower()
        else:
            assert carrier["oracle_verdict"] == "NOT_APPLICABLE"
            assert any(token in " ".join(artifact["contexts"]).lower() for token in ("inactive", "not a", "no "))


@ARCHIVED_OLD_RUNTIME
def test_repeats_are_identical_and_expected_label_mutation_cannot_change_prompts():
    s = load_study()
    baseline = s.render_all_provider_prompts()
    mutated_labels = {
        "localized_issue": "CANNOT_ASSESS",
        "material_failure": "NOT_APPLICABLE",
        "missing_required_evidence": "YES",
        "activation_mismatch": "NO",
    }
    assert s.render_all_provider_prompts(mutated_labels) == baseline
    for artifact_number in range(1, 21):
        repeats = [baseline[f"pss-v1-{artifact_number:02d}-r{repeat}"] for repeat in range(1, 4)]
        assert repeats[0] == repeats[1] == repeats[2]


@ARCHIVED_OLD_RUNTIME
def test_singleton_production_renderer_excludes_local_ledger_metadata():
    s = load_study()
    prompts = s.render_all_provider_prompts()
    slots = s.plan_slots()
    assert len(prompts) == len(slots) == 60
    for slot in slots:
        prompt = prompts[slot["slot_id"]]
        assert slot["leaf_id"] in prompt
        assert slot["slot_id"] not in prompt
        assert slot["fixture_id"] not in prompt
        assert slot["state"] not in prompt
        assert "expected_verdict" not in prompt
        assert "oracle_verdict" not in prompt
    haiku_prompt = prompts["pss-v1-13-r1"]
    assert "The artifact is a multi-stanza sequence and the profile permits one seasonal reference across the sequence." in haiku_prompt
    assert '"minimum_references": 1' in haiku_prompt


def test_pantoum_fixture_links_every_repeated_line_to_new_context():
    s = load_study()
    pairs = s.pantoum_repeated_line_pairs()
    assert len(pairs) == 8
    artifact = next(item for item in s.load_corpus()["artifacts"] if item["leaf_id"] == "form.poetry.pantoum.recontext" and item["state"] == "localized_issue")
    lines = [line for stanza in artifact["text"].split("\n\n") for line in stanza.splitlines()]
    for _, earlier, later in pairs:
        normalized = lambda value: value.rstrip(".—,;").casefold()
        assert normalized(lines[earlier]) == normalized(lines[later])
        prior_neighbors = (lines[earlier - 1] if earlier else None, lines[earlier + 1] if earlier + 1 < len(lines) else None)
        later_neighbors = (lines[later - 1] if later else None, lines[later + 1] if later + 1 < len(lines) else None)
        assert lines[earlier] != lines[later] or prior_neighbors != later_neighbors


def test_contract_and_corpus_drift_fail_closed(monkeypatch):
    s = load_study()
    original = s.load_contract()
    contract = deepcopy(original)
    contract["sealed_successor_gate"]["candidate_required"] = "11/12"
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Sealed successor gate drifted"):
        s.verify_package()
    altered = deepcopy(s.load_corpus())
    altered["artifacts"][0]["state"] = "other"
    with pytest.raises(ValueError, match="Artifact matrix drifted"):
        s.verify_corpus(altered)
    # Exercise later portfolio guards with actual current hashes in memory;
    # the frozen package's raw-current failure remains asserted above.
    contract = deepcopy(original)
    contract["portfolio_binding"]["leaf_findings"][s.LEAVES[0]] = s.FINDING_IDS[s.LEAVES[1]]
    contract["bindings"]["runtime"] = {path: s.sha256_file(s.REPOSITORY / path) for path in s.RUNTIME_PATHS}
    contract["bindings"]["source_leaves"] = s.source_leaf_hashes()
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="S1 portfolio boundary drifted"):
        s.verify_package()
    contract = deepcopy(original)
    contract["portfolio_binding"]["this_first_staged_subset_slots_exact"] = 61
    contract["bindings"]["runtime"] = {path: s.sha256_file(s.REPOSITORY / path) for path in s.RUNTIME_PATHS}
    contract["bindings"]["source_leaves"] = s.source_leaf_hashes()
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="S1 portfolio boundary drifted"):
        s.verify_package()


def test_provider_free_command_surface_and_public_privacy_boundary():
    for flag in ("--dry-run", "--render-plan"):
        result = subprocess.run([sys.executable, str(ROOT / "run.py"), flag], text=True, capture_output=True, check=False)
        assert result.returncode != 0
        assert "Current production runtime binding drifted" in result.stderr
    assert load_study().load_contract()["provider_execution"]["new_provider_calls_exact"] == 0
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "api_key", "session_id")
    for path in ROOT.iterdir():
        if path.suffix in {".py", ".json", ".md"}:
            value = path.read_text(encoding="utf-8")
            assert all(fragment not in value for fragment in forbidden)
    source = (ROOT / "run.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "--execute" not in source and "dspy" not in source
