from __future__ import annotations

import importlib.util
import json
import shutil
from copy import deepcopy

import pytest

from hbqrs import compile_bundle, load_bundles, load_modules, score_bundle
from hbqrs.paths import book_root, bundles_path, registry_path

ROOT = book_root() / "evaluation-results" / "hbq-polarity-bias-v1"


def _harness():
    spec = importlib.util.spec_from_file_location("polarity_bias_v1", ROOT / "polarity_harness.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _contract():
    return json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))


def _corpus():
    return json.loads((ROOT / "public-synthetic-wording-corpus.json").read_text(encoding="utf-8"))


def _ownership(h):
    return h.load_criterion_ownership(registry_path().parent / "criterion_ownership.json")


def test_synthetic_corpus_has_actual_words_bytes_hashes_and_diverse_real_ownership():
    h = _harness()
    contract = _contract()
    corpus = _corpus()
    ownership = _ownership(h)
    records = h.validate_corpus_file(contract, ROOT / "public-synthetic-wording-corpus.json", ownership)
    assert contract["status"] == "public_synthetic_mechanism_only_no_empirical_results"
    assert corpus["classification"] == "public_synthetic_mechanism_only"
    assert len(records) == 12
    assert {record["split"] for record in records} == {"development", "held_out"}
    assert len({record["module_id"] for record in records}) == 6
    assert all(record["positive_wording_bytes"] == len(h.canonicalize_wording(record["positive_wording"])) for record in records)
    assert all(ownership[record["criterion_key"]] == record["criterion_ownership"] for record in records)
    ownership[records[0]["criterion_key"]]["module_id"] = "wrong.module"
    with pytest.raises(ValueError, match="ownership"):
        h.validate_corpus_file(contract, ROOT / "public-synthetic-wording-corpus.json", ownership)


def test_contract_projection_is_independently_pinned_not_resealable():
    h = _harness()
    contract = _contract()
    h.validate_contract(contract)
    changed = deepcopy(contract)
    changed["privacy"]["forbid_nonpublic_content"] = False
    assert h.projection_sha256(changed) != h.EXPECTED_CONTRACT_PROJECTION_SHA256
    with pytest.raises(ValueError, match="Pinned contract projection"):
        h.validate_contract(changed)
    assert set(contract) == {
        "format_version",
        "study_id",
        "status",
        "frozen_before_execution",
        "production_polarity",
        "conditions",
        "reverse_decode",
        "input_corpus",
        "privacy",
        "interpretation_limits",
    }


@pytest.mark.parametrize(
    ("state", "decoded"),
    [("YES", "NO"), ("NO", "YES"), ("NOT_APPLICABLE", "NOT_APPLICABLE"), ("CANNOT_ASSESS", "CANNOT_ASSESS")],
)
def test_four_state_canonicalization_preserves_metadata(state, decoded):
    h = _harness()
    record = {"verdict": state, "confidence": 0.7, "evidence": [{"summary": "fixture"}], "note": "fixture"}
    assert h.reverse_decode_verdict(record)["verdict"] == decoded
    assert h.canonicalize_verdict(record, "negative_semantic_negation")["evidence"] == record["evidence"]


def test_publication_allows_only_its_exact_source_set_and_scans_every_allowed_file(tmp_path):
    h = _harness()
    public = tmp_path / "public"
    shutil.copytree(ROOT, public, ignore=shutil.ignore_patterns("__pycache__"))
    h.verify_publication(public)
    (public / "README.md").write_text((public / "README.md").read_text(encoding="utf-8") + "\nprivate\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Pinned publication content"):
        h.verify_publication(public)
    shutil.copytree(ROOT, public, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    contract = json.loads((public / "study-contract.json").read_text(encoding="utf-8"))
    contract["note"] = "raw"
    (public / "study-contract.json").write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(ValueError, match="Pinned publication content"):
        h.verify_publication(public)
    shutil.copytree(ROOT, public, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    (public / "polarity_harness.py").write_text((public / "polarity_harness.py").read_text(encoding="utf-8") + "\nLEAK = 'C:\\\\Users\\\\test'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="path"):
        h.verify_publication(public)
    shutil.copytree(ROOT, public, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    (public / "__pycache__").mkdir()
    (public / "__pycache__" / "polarity_harness.cpython-314.pyc").write_bytes(b"fixture")
    with pytest.raises(ValueError, match="Unexpected"):
        h.verify_publication(public)
    network_public = tmp_path / "network-public"
    shutil.copytree(ROOT, network_public, ignore=shutil.ignore_patterns("__pycache__"))
    (network_public / "polarity_harness.py").write_text((network_public / "polarity_harness.py").read_text(encoding="utf-8") + "\nfrom urllib import request\n", encoding="utf-8")
    with pytest.raises(ValueError, match="network"):
        h.verify_publication(network_public)
    marker_public = tmp_path / "marker-public"
    shutil.copytree(ROOT, marker_public, ignore=shutil.ignore_patterns("__pycache__"))
    (marker_public / "polarity_harness.py").write_text((marker_public / "polarity_harness.py").read_text(encoding="utf-8") + "\nLEAK = 'private_path'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Sensitive"):
        h.verify_publication(marker_public)


def test_canonical_scorer_exercises_gates_penalties_na_cannot_bounds_and_invalid_status():
    modules = load_modules(registry_path())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == "prose.flash")
    compiled = compile_bundle(modules, bundle)
    ids = [
        item["question"]["id"]
        for section in ("domain_questions", "hard_gates", "supplemental_questions")
        for item in compiled[section]
    ] + [item["question"]["id"] for group in compiled["penalty_groups"] for item in group["questions"]]
    answers = [
        {"artifact_id": "fixture", "question_id": question_id, "verdict": "YES", "confidence": 0.7, "evidence": [{"reference": "fixture", "quote": "fixture"}]}
        for question_id in dict.fromkeys(ids)
    ]
    baseline = score_bundle(modules, bundle, answers)
    assert baseline["status"] == "SCORED"
    assert baseline["hard_gate_status"] == "VALID"
    assert baseline["penalty_deduction"]["observed"] == 0.0

    penalty = deepcopy(answers)
    penalty_id = compiled["penalty_groups"][0]["questions"][0]["question"]["id"]
    next(item for item in penalty if item["question_id"] == penalty_id)["verdict"] = "NO"
    penalty_report = score_bundle(modules, bundle, penalty)
    assert penalty_report["penalty_deduction"]["observed"] > 0.0
    assert penalty_report["final_score"]["observed"] < baseline["final_score"]["observed"]

    hard = deepcopy(answers)
    hard_id = compiled["hard_gates"][0]["question"]["id"]
    next(item for item in hard if item["question_id"] == hard_id)["verdict"] = "NO"
    hard_report = score_bundle(modules, bundle, hard)
    assert hard_report["hard_gate_status"] == "INVALID"
    assert hard_report["status"] == "INELIGIBLE"

    not_applicable = deepcopy(answers)
    cannot_assess = deepcopy(answers)
    not_applicable[0]["verdict"] = "NOT_APPLICABLE"
    cannot_assess[1]["verdict"] = "CANNOT_ASSESS"
    not_applicable_report = score_bundle(modules, bundle, not_applicable)
    cannot_assess_report = score_bundle(modules, bundle, cannot_assess)
    assert not_applicable_report["coverage"] == baseline["coverage"]
    assert not_applicable_report["final_score"] == baseline["final_score"]
    assert cannot_assess_report["coverage"] < baseline["coverage"]
    assert cannot_assess_report["final_score"]["lower"] < cannot_assess_report["final_score"]["observed"] <= cannot_assess_report["final_score"]["upper"]

    invalid = deepcopy(answers)
    invalid[0]["verdict"] = "MAYBE"
    invalid_report = score_bundle(modules, bundle, invalid)
    assert invalid_report["status"] == "SCORED"
    assert invalid_report["coverage"] < baseline["coverage"]
    assert any("invalid state" in issue for issue in invalid_report["issues"])
    with pytest.raises(ValueError, match="invalid verdict"):
        _harness().canonicalize_verdict(invalid[0], "positive_production")


def test_negative_wording_decodes_to_an_identical_canonical_score_report():
    h = _harness()
    modules = load_modules(registry_path())
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == "prose.flash")
    compiled = compile_bundle(modules, bundle)
    ids = [
        item["question"]["id"]
        for section in ("domain_questions", "hard_gates", "supplemental_questions")
        for item in compiled[section]
    ] + [item["question"]["id"] for group in compiled["penalty_groups"] for item in group["questions"]]
    positive = [
        {"artifact_id": "fixture", "question_id": question_id, "verdict": "YES", "confidence": 0.7, "evidence": [{"reference": "fixture", "quote": "fixture"}]}
        for question_id in dict.fromkeys(ids)
    ]
    for question_id, state in {
        compiled["domain_questions"][0]["question"]["id"]: "NO",
        compiled["domain_questions"][1]["question"]["id"]: "NOT_APPLICABLE",
        compiled["domain_questions"][2]["question"]["id"]: "CANNOT_ASSESS",
        compiled["hard_gates"][0]["question"]["id"]: "NO",
        compiled["penalty_groups"][0]["questions"][0]["question"]["id"]: "NO",
    }.items():
        next(item for item in positive if item["question_id"] == question_id)["verdict"] = state
    negative_raw = deepcopy(positive)
    for answer in negative_raw:
        answer["verdict"] = {"YES": "NO", "NO": "YES"}.get(answer["verdict"], answer["verdict"])
    positive_canonical = [h.canonicalize_verdict(answer, "positive_production") for answer in positive]
    negative_canonical = [h.canonicalize_verdict(answer, "negative_semantic_negation") for answer in negative_raw]
    assert {answer["verdict"] for answer in positive_canonical} == {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
    assert negative_canonical == positive_canonical
    assert score_bundle(modules, bundle, negative_canonical) == score_bundle(modules, bundle, positive_canonical)
