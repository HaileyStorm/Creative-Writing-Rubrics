from __future__ import annotations

import json
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-v3-fresh88-overlap-analysis-v1"
study = load_module(PACKAGE / "study.py", name="fresh88_overlap_analysis_study_v1")
analysis = load_module(
    PACKAGE / "analyze.py",
    name="fresh88_overlap_analysis_v1",
    aliases={"study": study},
)


MAPPINGS = {
    "Relevance": ["task.contract.hanna.prompt_response", "core.task_and_brief_fidelity.operation", "core.audience_and_purpose_fit.use_context"],
    "Coherence": ["form.prose.short_story.unity", "form.prose.short_story.structure", "craft.narrative.plot_and_causality.causal_chain", "craft.narrative.plot_and_causality.consequence", "craft.narrative.scene_construction.progression"],
    "Empathy": ["craft.narrative.characterization.dimensionality", "craft.narrative.characterization.motives", "core.emotional_and_intellectual_effect.earned_emotion", "core.emotional_and_intellectual_effect.aftermath", "craft.narrative.narrative_momentum.investment"],
    "Surprise": ["core.freshness_and_non_genericness.no_cliche", "core.freshness_and_non_genericness.no_stock_beats", "core.freshness_and_non_genericness.unpredictable_specificity", "core.freshness_and_non_genericness.no_default_metaphors", "craft.narrative.theme_and_subtext.open_questions"],
    "Engagement": ["craft.narrative.narrative_momentum.curiosity", "craft.narrative.narrative_momentum.investment", "craft.narrative.narrative_momentum.commitment", "craft.narrative.scene_construction.pressure", "core.language_craft.cadence"],
    "Complexity": ["core.audience_and_purpose_fit.complexity", "craft.narrative.theme_and_subtext.emergence", "craft.narrative.theme_and_subtext.development", "craft.narrative.theme_and_subtext.counterpoint", "craft.narrative.characterization.contradiction"],
}


class Metrics:
    @staticmethod
    def dimension_analysis(rows: list[dict], identifier: str, seed: int) -> dict:
        usable = [row for row in rows if row["hbq_mapping"][identifier]["score"] is not None]
        return {"item_count": len(usable), "spearman": {"estimate": float(seed), "cluster": "prompt_group_id"}, "mean_coverage": sum(row["hbq_mapping"][identifier]["coverage"] for row in usable) / len(usable) if usable else None, "unresolved": sum(row["hbq_mapping"][identifier]["unresolved"] for row in usable), "not_applicable": sum(row["hbq_mapping"][identifier]["not_applicable"] for row in usable)}

    @staticmethod
    def macro_cluster_bootstrap(rows: list[dict], seed: int) -> dict:
        return {"estimate": float(seed), "cluster": "prompt_group_id", "item_count": len(rows)}


def _record(index: int) -> dict:
    labels = {identifier: "YES" if (position + index) % 3 else "NO" for position, identifier in enumerate(sorted({value for values in MAPPINGS.values() for value in values}))}
    labels["craft.narrative.theme_and_subtext.counterpoint"] = "CANNOT_ASSESS"
    mapping = {}
    human = {}
    for position, (dimension, identifiers) in enumerate(MAPPINGS.items(), 1):
        assessed = [labels[identifier] for identifier in identifiers if labels[identifier] in {"YES", "NO"}]
        mapping[dimension] = {"score": sum(value == "YES" for value in assessed) / len(assessed), "coverage": len(assessed) / len(identifiers), "unresolved": len(identifiers) - len(assessed), "not_applicable": 0, "question_count": len(identifiers)}
        human[dimension] = float(position)
    return {"item_id": f"hanna-{index}", "prompt_group_id": f"group-{index}", "source_model": "Model", "human_means": human, "human_overall": 3.0, "hbq_mapping": mapping, "labels": labels, "native": {"final_score": {"value": 12.0, "coverage": 0.9}, "task": {"value": 0.6, "coverage": 0.8}, "character": {"value": 0.7, "coverage": 0.7}}}


def test_contract_and_geometry_make_duplicate_investment_explicit() -> None:
    assert analysis.CONTRACT["analysis_only"] is True
    unique, owners = analysis._mapping_geometry(MAPPINGS)
    assert len(unique) == 27
    assert sum(len(value) for value in MAPPINGS.values()) == 28
    assert owners["craft.narrative.narrative_momentum.investment"] == ["Empathy", "Engagement"]


def test_overlap_and_hierarchical_views_keep_both_denominators() -> None:
    records = [_record(1), _record(2)]
    unique = analysis._overlap_view(Metrics(), records, tuple(MAPPINGS), MAPPINGS, weighted=False, seed=10)
    occurrences = analysis._overlap_view(Metrics(), records, tuple(MAPPINGS), MAPPINGS, weighted=True, seed=20)
    hierarchy = analysis._hierarchical_view(Metrics(), records, tuple(MAPPINGS), 30)
    assert unique["unique_leaf_count"] == 27 and unique["occurrence_count"] == 27
    assert occurrences["unique_leaf_count"] == 27 and occurrences["occurrence_count"] == 28
    assert occurrences["duplicate_investment_treatment"] == "two dimension occurrences retained"
    assert hierarchy["spearman"]["item_count"] == 2


def test_six_dimension_and_native_views_report_coverage_and_no_remap() -> None:
    records = [_record(1), _record(2)]
    six = analysis._six_dimension_view(Metrics(), records, tuple(MAPPINGS), 40)
    native = analysis._native_view(Metrics(), records, ["character", "task"], 50)
    assert six["dimension_count"] == 6 and six["occurrence_count"] == 28
    assert six["dimensions"]["Complexity"]["mean_coverage"] < 1
    assert set(native["final_and_domains"]) == {"final_score", "character", "task"}
    assert native["final_and_domains"]["final_score"]["mean_coverage"] == 0.9


def test_leaf_diagnostics_are_public_identifier_only() -> None:
    records = [_record(1), _record(2)]
    diagnostics = analysis._leaf_diagnostics(Metrics(), records, MAPPINGS, 60)
    investment = next(row for row in diagnostics if row["question_id"].endswith("investment"))
    assert len(diagnostics) == 27
    assert investment["mapping_occurrence_count"] == 2
    assert investment["mapped_dimensions"] == ["Empathy", "Engagement"]
    assert "private prose" not in json.dumps(diagnostics).lower()


def test_output_refuses_merge_and_private_overlap(tmp_path: Path) -> None:
    output = tmp_path / "output"
    analysis.atomic_output_directory(output, {"summary.json": "{}\n", "leaf-diagnostics.jsonl": "", "manifest.json": "{}\n"})
    with pytest.raises(ValueError, match="Refusing"):
        analysis.atomic_output_directory(output, {"summary.json": "{}\n"})
    with pytest.raises(ValueError, match="disjoint"):
        analysis.ensure_output_disjoint(tmp_path / "private" / "output", [tmp_path / "private"])


def test_projection_preserves_all_unassessed_and_not_applicable_states() -> None:
    record = {"item_id": "hanna-1", "prompt_group_id": "group", "source_model": "Model"}
    projection = analysis._projection_record(record, identifier="probe", values=["CANNOT_ASSESS", "NOT_APPLICABLE"], targets=[2.0, 4.0])
    value = projection["hbq_mapping"]["probe"]
    assert value == {"score": None, "coverage": 0.0, "unresolved": 1, "not_applicable": 1, "question_count": 2}
    assert projection["human_means"]["probe"] == 3.0


def test_native_score_extraction_normalizes_domains_without_changing_final_units(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "hanna-1"; run.mkdir(parents=True)
    (run / "score.v2.json").write_text(json.dumps({"coverage": 0.75, "final_score": {"observed": 13.5}, "domains": [{"domain_id": "task", "nominal_points": 8.0, "coverage": 0.5, "score": {"observed": 2.0}}, {"domain_id": "character", "nominal_points": 15.0, "coverage": 1.0, "score": {"observed": 12.0}}]}), encoding="utf-8")
    values, domains = analysis._native_scores(tmp_path, {"cells": [{"item_id": "hanna-1", "run_dir": "runs/hanna-1"}]})
    assert domains == ["character", "task"]
    assert values["hanna-1"]["final_score"] == {"value": 13.5, "coverage": 0.75}
    assert values["hanna-1"]["task"] == {"value": 0.25, "coverage": 0.5}
    assert values["hanna-1"]["character"] == {"value": 0.8, "coverage": 1.0}


def test_generated_real_fresh88_output_replays_when_mounted(tmp_path: Path) -> None:
    data = Path("C:/Users/Haile/Documents/cwr-hanna-pinned-data-282f275")
    work = Path("C:/Users/Haile/Documents/cwr-hanna-fresh88-sol-v1-20260821-w4")
    authority = Path("C:/Users/Haile/Documents/cwr-hanna-successor-fresh88-freeze-v4")
    artifacts = Path("C:/Users/Haile/Documents/cwr-hanna-fresh88-sol-v1-20260821-w4-repair1-artifacts")
    runtime = Path("C:/Users/Haile/Documents/Creative-Writing-Rubrics-fresh88-parent-runtime-f3aed43")
    if not all(path.is_dir() for path in (data, work, authority, artifacts, runtime)):
        pytest.skip("requires explicitly mounted sealed Fresh88 inputs")
    output = tmp_path / "replay"
    analysis.analyze(data, work, authority, artifacts, runtime, output)
    summary = analysis.verify_output(output)
    primary = summary["primary_generated_only"]
    assert primary["unique_27_leaf_overlap"]["spearman"]["spearman"]["estimate"] == pytest.approx(-0.09014775122983233)
    assert primary["occurrence_weighted_28_mapping"]["spearman"]["spearman"]["estimate"] == pytest.approx(-0.09215367277874827)
    assert primary["hierarchical_dimension_to_macro"]["spearman"]["spearman"]["estimate"] == pytest.approx(-0.03775134336184484)
    assert primary["native_hbq_domains_and_final"]["final_and_domains"]["final_score"]["spearman"]["estimate"] == pytest.approx(-0.04406145228576549)
    binding = summary["evidence_binding"]
    assert binding["implementation"] == analysis.implementation_binding()
    assert not any("C:/Users/Haile" in line for line in (output / "summary.json").read_text(encoding="utf-8").splitlines())
