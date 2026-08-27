from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-polarity-change-manual-treatment-v1"


ARCHIVED_OLD_RUNTIME = pytest.mark.skip(
    reason="Archived P1 manual-treatment dry/render mechanics require the frozen runtime bindings; current bindings have advanced."
)


def study():
    spec = importlib.util.spec_from_file_location("p1_manual_treatment_study", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_checkout_fails_closed_and_manual_treatment_geometry_remains_exact():
    s = study()
    with pytest.raises(ValueError, match="Frozen package bindings drifted"):
        s.verify_package()
    contract = s.load_contract()
    assert contract["status"] == "frozen_development_only_manual_treatment"
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}
    corpus = s.load_corpus()
    s.verify_corpus(corpus)
    s.verify_carriers(corpus)
    slots = s.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 57
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["expected_verdict"] for slot in slots} == {"YES", "NO", "NOT_APPLICABLE"}
    assert len([slot for slot in slots if slot["expected_verdict"] == "NOT_APPLICABLE"]) == 33


def test_eleven_unchanged_na_controls_keep_predecessor_fixture_bytes_and_carriers_exactly():
    s = study()
    predecessor = {fixture["case_id"]: fixture for fixture in s.load_predecessor_corpus()["fixtures"]}
    current = {fixture["case_id"]: fixture for fixture in s.load_corpus()["fixtures"]}
    expected = {case_id for case_id, fixture in predecessor.items() if fixture["state"] == "NOT_APPLICABLE"}
    observed = {case_id for case_id, fixture in current.items() if fixture["state"] == "NOT_APPLICABLE"}
    assert observed == expected
    for case_id in expected:
        assert current[case_id] == predecessor[case_id]
        context = s.task_context_for(current[case_id])
        assert context["declared_scope"] == "out_of_scope"
        assert context["completion_status"] == "complete"
        assert context["constraints"] == [{"id": "evidence_availability", "statement": "relevant_evidence=supplied"}]


def test_corrected_pairs_are_symmetric_and_include_both_comparison_sides():
    s = study()
    cases = {fixture["case_id"]: fixture for fixture in s.load_corpus()["fixtures"]}
    pairs = ("poem-oral", "visual-subjects", "critique-criteria", "ingest-invention")
    for prefix in pairs:
        yes, no = cases[f"{prefix}-yes"], cases[f"{prefix}-no"]
        assert yes["leaf_id"] == no["leaf_id"]
        assert yes["artifact_kind"] == no["artifact_kind"]
        reference = s.MATCHED_PAIR_CARRIERS[prefix]["reference"]
        output_prefix = s.MATCHED_PAIR_CARRIERS[prefix]["output_prefix"]
        assert yes["text"].split("\n", maxsplit=1)[0] == no["text"].split("\n", maxsplit=1)[0] == reference
        assert yes["text"].split("\n", maxsplit=1)[1].startswith(output_prefix)
        assert no["text"].split("\n", maxsplit=1)[1].startswith(output_prefix)
        assert yes["text"].split("\n", maxsplit=1)[1] != no["text"].split("\n", maxsplit=1)[1]
    assert cases["poem-oral-no"]["text"] == "DECLARED PERFORMANCE AIM: a calm, easily articulated lullaby cadence.\nPOEM: The sixth sickly thistle's strengths / twists through three stripped streets."
    for prefix in ("visual-subjects", "critique-criteria", "ingest-invention"):
        assert "\n" in cases[f"{prefix}-yes"]["text"]
        assert "\n" in cases[f"{prefix}-no"]["text"]


def test_exact_treatment_appendix_is_rendered_without_ledger_or_holdout_leakage():
    s = study()
    prompt = s.render_provider_prompt("p1mt-v1-ingest-invention-no-r1")
    assert s.TREATMENT_APPENDIX in prompt
    assert "Decide applicability before evidence sufficiency." in prompt
    assert "Apply the same evidence threshold to `YES` and `NO`." in prompt
    assert "SOURCE RECORD: Nell waits at dawn." in prompt
    for forbidden in ("p1mt-v1", "expected_verdict", "sealed-holdout", "oracle"):
        assert forbidden not in prompt
    assert hashlib.sha256(s.TREATMENT_APPENDIX.encode()).hexdigest() == s.load_contract()["bindings"]["treatment_appendix_sha256"]
    expected = {
        "form.poetry.general_poetry.oral_test": ("form.poetry.general_poetry", "When read aloud, does the poem's sound support rather than expose accidental awkwardness?", "YES", 1.5, "scored", "material"),
        "form.visual.visual_prompt_and_canon_fidelity.subjects": ("form.visual.visual_prompt_and_canon_fidelity", "Are all required subjects and no forbidden subjects depicted?", "YES", 2.0, "hard_gate", "material"),
        "op.critique.rubric_directed_critique.criteria": ("op.critique.rubric_directed_critique", "Does the critique apply every active criterion and no unauthorized substitute criteria?", "YES", 2.0, "scored", "material"),
        "op.ingest.source_ingestion_fidelity.no_invention": ("op.ingest.source_ingestion_fidelity", "Is no unsupported content inserted into the ingested source?", "YES", 2.0, "scored", "material"),
    }
    records = s.source_leaf_records()
    assert {leaf: (records[leaf]["module_id"], records[leaf]["text"], records[leaf]["pass_answer"], records[leaf]["weight"], records[leaf]["question_type"], records[leaf]["severity"]) for leaf in expected} == expected
    ownership = json.loads((book_root() / "registry" / "criterion_ownership.json").read_text(encoding="utf-8"))
    assert {leaf: ownership[leaf] for leaf in expected} == {leaf: {"module_id": expected[leaf][0], "question_id": leaf} for leaf in expected}
    fixture = next(item for item in s.load_corpus()["fixtures"] if item["case_id"] == "poem-oral-yes")
    base = "\n\n".join((book_root() / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    live_prompt = s.production_runner._render_prompt(binary_prompt=base, artifact={"name": "public-synthetic-fixture.txt", "text": fixture["text"]}, contexts=[], bundle_id="p1-current-wording-development", artifact_id="public-synthetic-fixture", questions=[s.production_question(fixture["leaf_id"])])
    assert s.TREATMENT_APPENDIX not in live_prompt
    source = (ROOT / "run.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "subprocess" not in source and "--execute" not in source
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "raw_response", "session_id", "api_key", "import dspy", "from dspy")
    for path in ROOT.iterdir():
        if path.suffix in {".py", ".json", ".md"}:
            value = path.read_text(encoding="utf-8")
            assert all(fragment not in value for fragment in forbidden)


def test_mutating_only_expected_state_for_every_fixture_leaves_all_provider_prompt_bytes_unchanged(monkeypatch):
    s = study()
    baseline = s.render_all_provider_prompts()
    altered = deepcopy(s.load_corpus())
    replacement = {"YES": "NO", "NO": "YES", "NOT_APPLICABLE": "YES"}
    for fixture in altered["fixtures"]:
        fixture["state"] = replacement[fixture["state"]]
    monkeypatch.setattr(s, "load_corpus", lambda: altered)
    assert s.render_all_provider_prompts() == baseline
    monkeypatch.undo()


def test_sealed_holdout_contract_has_no_fixture_content_and_requires_all_promotion_gates():
    s = study()
    contract = json.loads((ROOT / "sealed-holdout-contract.json").read_text(encoding="utf-8"))
    s.verify_holdout_contract(contract)
    assert contract["fixture_material"] == "sealed_private_not_in_public_package"
    assert contract["required_coverage"]["matched_not_applicable_cannot_assess_pairs"] is True
    assert contract["required_coverage"]["symmetric_yes_no_comparison_carriers"] == ["visual", "critique", "ingest"]
    assert "independent_sol_high_go" in contract["promotion_gate"]
    assert all("text" not in value and "expected" not in value for value in contract.values() if isinstance(value, dict))


def test_contract_corpus_and_holdout_drift_fail_closed(monkeypatch):
    s = study()
    contract = deepcopy(s.load_contract())
    contract["geometry"]["slots_exact"] = 56
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Manual-treatment geometry drifted"):
        s.verify_package()
    monkeypatch.undo()
    corpus = deepcopy(s.load_corpus())
    corpus["fixtures"][0]["text"] = "changed"
    with pytest.raises(ValueError, match="NOT_APPLICABLE fixture bytes drifted"):
        s.verify_corpus(corpus)
    holdout = json.loads((ROOT / "sealed-holdout-contract.json").read_text(encoding="utf-8"))
    holdout["promotion"] = "prompt"
    with pytest.raises(ValueError, match="Sealed holdout contract drifted"):
        s.verify_holdout_contract(holdout)
    carriers = deepcopy(s.load_carriers())
    carriers["carriers"]["poem-oral-na"]["declared_scope"] = "current_artifact"
    monkeypatch.setattr(s, "load_carriers", lambda: carriers)
    with pytest.raises(ValueError, match="NOT_APPLICABLE carrier drifted"):
        s.verify_carriers(s.load_corpus())


@ARCHIVED_OLD_RUNTIME
def test_dry_run_render_plan_and_public_surface_are_provider_free():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    plan = json.loads(rendered.stdout)
    assert plan["mode"] == "render_plan"
    assert len(plan["rendered_slots"]) == len(plan["prompt_sha256s"]) == 57
    source = (ROOT / "run.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "subprocess" not in source and "--execute" not in source
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "raw_response", "session_id", "api_key", "import dspy", "from dspy")
    for path in ROOT.iterdir():
        if path.suffix in {".py", ".json", ".md"}:
            value = path.read_text(encoding="utf-8")
            assert all(fragment not in value for fragment in forbidden)
