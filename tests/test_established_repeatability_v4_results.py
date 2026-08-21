from __future__ import annotations

import hashlib
import json
from pathlib import Path
import py_compile
import runpy
import shutil
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v4"
RESULTS = ROOT / "results"


def _json(name: str) -> dict:
    return json.loads((RESULTS / name).read_text(encoding="utf-8"))


def _verifier():
    return SimpleNamespace(**runpy.run_path(str(RESULTS / "verify_results.py"), run_name="established_v4_publication_verifier"))


def _publication_fixture(tmp_path: Path) -> Path:
    study = tmp_path / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v4"
    shutil.copytree(ROOT, study, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT.parent / "source.md", study.parent / "source.md")
    return study / "results"


def _rehash_publication_file(results: Path, relative: str) -> None:
    path = results / relative
    manifest_path = results / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][relative] = {
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_publication_manifest_hashes_and_privacy_scan() -> None:
    manifest = _verifier().verify()
    assert len(manifest["files"]) == 7
    assert manifest["source_analysis_manifest"] == {"file_count": 31, "bytes": 5205, "sha256": "3267343f9f6653489eca29f45957335458fe304b45a6762695e28d7dd3c81c95"}
    assert manifest["files"]["agreement.svg"] == {"bytes": 1654, "sha256": "6d8a22b8dcb18366813a4a43074c6dd761ab27029ba8058a1271f670fed8ab41"}
    assert manifest["files"]["score-distributions.svg"] == {"bytes": 3607, "sha256": "7a5edd7269366438063e3903064a15fcaa50645eb438797e4f5f773d0fa87d83"}
    assert manifest["publication_transformations"]["score-distributions.svg"] == {
        "kind": "native_axis_correction",
        "arm_id": "oregon_narrative_2017",
        "source_axis_minimum": 0,
        "published_axis_minimum": 6,
        "axis_maximum": 36,
    }
    assert manifest["files"]["derived-repeatability.json"] == {"bytes": 4223, "sha256": "3d503c3f6251a2ab290aa9b9f69d61bd166a3855a24e6b07b7cf8b528176ea6d"}


def test_verifier_rejects_an_unexpected_raw_private_artifact(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    (results / "response.json").write_text('{"private_path":"C:\\\\Users\\\\writer\\\\draft.txt"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected or missing entries"):
        _verifier().verify(results)


def test_verifier_privacy_scans_the_publication_manifest(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    manifest_path = results / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["private_path"] = "C:\\Users\\writer\\draft.txt"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest contains a private runtime field"):
        _verifier().verify(results)


def test_verifier_allows_only_regenerable_python_cache_entries(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    py_compile.compile(str(results / "verify_results.py"), doraise=True)
    _verifier().verify(results)
    cache = results / "__pycache__"
    assert list(cache.glob("verify_results.*.pyc"))
    (cache / "response.json").write_text('{"private":"raw provider output"}', encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected or missing entries"):
        _verifier().verify(results)


def test_verifier_binds_publication_authorization_and_source_bytes(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    study = results.parent
    contract_path = study / "study-contract.json"
    manifest_path = results / "publication-manifest.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["source"]["publication_authorized"] = False
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["protocol_contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="does not authorize"):
        _verifier().verify(results)
    contract["source"]["publication_authorized"] = True
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest["protocol_contract_sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (study.parent / "source.md").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the frozen contract"):
        _verifier().verify(results)


def test_published_metrics_match_the_completed_study() -> None:
    summary = _json("summary.json")
    hbq = summary["arms"]["hbq_short_story_batch32"]
    assert hbq["exact_all_run_agreement_rate"] == pytest.approx(0.9101123595505618)
    assert hbq["mean_modal_label_proportion"] == pytest.approx(0.9707865168539327)
    assert hbq["nominal_krippendorff_alpha"] == pytest.approx(0.8616957801335363)
    assert hbq["observed_score"]["mean"] == pytest.approx(90.6764)
    assert hbq["observed_score"]["sample_standard_deviation"] == pytest.approx(3.2755873877825366)
    assert hbq["observed_score"]["range"] == pytest.approx(8.2961)
    naplan = summary["arms"]["naplan_narrative_2022"]
    cambridge = summary["arms"]["cambridge_igcse_0500_p2_mj_2024"]
    oregon = summary["arms"]["oregon_narrative_2017"]
    assert naplan["total_score"]["values"] == [47] * 5 and naplan["retry_provenance"]["semantic_rejection_count"] == 3
    assert cambridge["total_score"]["values"] == [40, 40, 39, 40, 39]
    assert cambridge["criteria"]["content_and_structure"]["values"] == [16, 16, 15, 16, 15]
    assert oregon["total_score"]["values"] == [36] * 5 and oregon["retry_provenance"]["semantic_rejection_count"] == 3


def test_derived_agreement_scale_width_ceiling_and_conformance_are_exact() -> None:
    derived = _json("derived-repeatability.json")
    agreement = derived["agreement"]
    assert agreement["hbq_short_story_batch32"]["pairwise_repeat_agreement"] == {"numerator": 1695, "denominator": 1780, "proportion": 1695 / 1780}
    assert agreement["hbq_short_story_batch32"]["modal_proportion_distribution"] == {"1.0": 162, "0.8": 7, "0.6": 8, "0.4": 1}
    assert agreement["naplan_narrative_2022"]["pairwise_repeat_agreement"]["numerator"] == 100
    assert agreement["cambridge_igcse_0500_p2_mj_2024"]["pairwise_repeat_agreement"] == {"numerator": 14, "denominator": 20, "proportion": 0.7}
    assert agreement["oregon_narrative_2017"]["pairwise_repeat_agreement"]["numerator"] == 60
    variability = derived["scale_width_normalized_variability"]
    assert {arm: item["scale_width"] for arm, item in variability.items()} == {"hbq_short_story_batch32": 100, "naplan_narrative_2022": 47, "cambridge_igcse_0500_p2_mj_2024": 40, "oregon_narrative_2017": 30}
    assert variability["cambridge_igcse_0500_p2_mj_2024"]["range_percent_of_width"] == 2.5
    ceiling = derived["ceiling_exposure"]
    assert ceiling["naplan_narrative_2022"]["criterion_ceiling_hits"] == 50
    assert ceiling["cambridge_igcse_0500_p2_mj_2024"] == {"total_ceiling_hits": 3, "total_observations": 5, "mean_total_gap": 0.4, "criterion_ceiling_hits": 8, "criterion_observations": 10, "summed_criterion_gap": 2}
    assert ceiling["oregon_narrative_2017"]["criterion_ceiling_hits"] == 30
    conformance = derived["conformance"]
    assert conformance["hbq_short_story_batch32"] == {"accepted_provider_calls": 30, "rejected_provider_calls": 0, "deterministic_quote_to_summary_repairs": 62, "additional_provider_calls": 0}
    assert conformance["naplan_narrative_2022"]["additional_provider_calls"] == 3
    assert conformance["cambridge_igcse_0500_p2_mj_2024"]["additional_provider_calls"] == 0
    assert conformance["oregon_narrative_2017"]["additional_provider_calls"] == 3


def test_verifier_recomputes_derived_metrics_from_preserved_raw_results(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    derived_path = results / "derived-repeatability.json"
    derived = json.loads(derived_path.read_text(encoding="utf-8"))
    derived["agreement"]["hbq_short_story_batch32"]["pairwise_repeat_agreement"]["numerator"] = 1694
    derived_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "derived-repeatability.json")
    with pytest.raises(ValueError, match="Derived agreement"):
        _verifier().verify(results)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda derived: derived.update({"fabricated_section": {"claim": "unsupported"}}),
        lambda derived: derived["scale_width_normalized_variability"].update(
            {"fabricated_arm": {"scale_width": 1}}
        ),
        lambda derived: derived["scale_width_normalized_variability"]["hbq_short_story_batch32"].update(
            {"fabricated_metric": 1}
        ),
    ],
)
def test_verifier_rejects_extra_derived_sections_arms_and_metrics(tmp_path: Path, mutate) -> None:
    results = _publication_fixture(tmp_path)
    derived_path = results / "derived-repeatability.json"
    derived = json.loads(derived_path.read_text(encoding="utf-8"))
    mutate(derived)
    derived_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "derived-repeatability.json")
    with pytest.raises(ValueError, match="unexpected format or section|Scale-width-normalized"):
        _verifier().verify(results)


def test_verifier_recomputes_variability_and_ceiling_gap_from_score_values(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    summary_path = results / "summary.json"
    derived_path = results / "derived-repeatability.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    derived = json.loads(derived_path.read_text(encoding="utf-8"))
    summary["arms"]["hbq_short_story_batch32"]["observed_score"]["sample_standard_deviation"] = 0
    summary["arms"]["hbq_short_story_batch32"]["observed_score"]["mean"] = 100
    derived["scale_width_normalized_variability"]["hbq_short_story_batch32"][
        "sample_standard_deviation_percent_of_width"
    ] = 0
    derived["ceiling_exposure"]["hbq_short_story_batch32"]["mean_total_gap"] = 0
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    derived_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "summary.json")
    _rehash_publication_file(results, "derived-repeatability.json")
    with pytest.raises(ValueError, match="Scale-width-normalized"):
        _verifier().verify(results)


def test_verifier_recomputes_conformance_from_per_run_records(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    summary_path = results / "summary.json"
    derived_path = results / "derived-repeatability.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    derived = json.loads(derived_path.read_text(encoding="utf-8"))
    retry = summary["arms"]["naplan_narrative_2022"]["retry_provenance"]
    retry["attempt_count"] = 5
    retry["rejected_attempt_count"] = 0
    retry["semantic_rejection_count"] = 0
    derived["conformance"]["naplan_narrative_2022"]["rejected_provider_calls"] = 0
    derived["conformance"]["naplan_narrative_2022"]["additional_provider_calls"] = 0
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    derived_path.write_text(json.dumps(derived, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "summary.json")
    _rehash_publication_file(results, "derived-repeatability.json")
    with pytest.raises(ValueError, match="retry aggregates"):
        _verifier().verify(results)


def test_verifier_requires_the_frozen_question_and_repetition_counts(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    leaves_path = results / "hbq-leaf-repeatability.json"
    leaves = json.loads(leaves_path.read_text(encoding="utf-8"))
    leaves["leaves"][0]["labels"].pop()
    leaves_path.write_text(json.dumps(leaves, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "hbq-leaf-repeatability.json")
    with pytest.raises(ValueError, match="question and repetition counts"):
        _verifier().verify(results)


def test_verifier_binds_hbq_question_count_and_sequence_to_the_contract(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    leaves_path = results / "hbq-leaf-repeatability.json"
    summary_path = results / "summary.json"
    leaves = json.loads(leaves_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    leaves["leaves"].pop()
    summary["arms"]["hbq_short_story_batch32"]["question_count"] = 177
    leaves_path.write_text(json.dumps(leaves, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "hbq-leaf-repeatability.json")
    _rehash_publication_file(results, "summary.json")
    with pytest.raises(ValueError, match="question and repetition counts"):
        _verifier().verify(results)


def test_verifier_requires_the_exact_native_criteria(tmp_path: Path) -> None:
    results = _publication_fixture(tmp_path)
    summary_path = results / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    arm = summary["arms"]["naplan_narrative_2022"]
    arm["criteria"].pop("spelling")
    arm["criterion_count"] = 9
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _rehash_publication_file(results, "summary.json")
    with pytest.raises(ValueError, match="exact frozen criteria"):
        _verifier().verify(results)


def test_leaf_publication_is_complete_and_run_ids_are_not_published() -> None:
    leaves = _json("hbq-leaf-repeatability.json")["leaves"]
    assert len(leaves) == 178
    assert all(len(item["labels"]) == 5 for item in leaves)
    assert "session_id" not in json.dumps(_json("provenance.json"))
    assert "run_id" not in json.dumps(leaves)
