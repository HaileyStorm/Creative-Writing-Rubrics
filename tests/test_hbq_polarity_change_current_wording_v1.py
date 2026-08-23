from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-polarity-change-current-wording-v1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    return module


def study():
    return load_module("p1_current_wording_study", ROOT / "study.py")


def test_frozen_current_wording_package_has_exact_p1_geometry_and_no_provider_path():
    s = study()
    assert s.verify_package() == {
        "study_id": "hbq-polarity-change-current-wording-v1",
        "status": "frozen_development_only_current_wording_screen",
        "provider_calls": 0,
        "leaves": 11,
        "fixtures": 44,
        "slots": 132,
        "current_wording_bound": True,
    }
    slots = s.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 132
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["leaf_id"] for slot in slots} == set(s.LEAVES)


def test_exact_leaf_and_finding_membership_is_pinned_to_the_public_p1_portfolio():
    s = study()
    assert s.LEAVES == (
        "form.audio.audio_drama_production.no_as_you_know",
        "form.multimodal.text_audio_alignment.no_narrow",
        "form.poetry.general_poetry.oral_test",
        "form.poetry.haiku_in_english.kigo_legible",
        "form.poetry.lyric_song_lyric.no_filler",
        "form.poetry.spoken_word_performance_poetry.page_independence",
        "form.visual.visual_prompt_and_canon_fidelity.subjects",
        "op.critique.rubric_directed_critique.criteria",
        "op.ingest.source_ingestion_fidelity.no_invention",
        "op.ingest.source_ingestion_fidelity.no_omission",
        "sampler.freshness_gain.no_ornate_proxy",
    )
    assert len(s.FINDINGS) == len(set(s.FINDINGS)) == 11
    records = s.source_leaf_records()
    assert tuple(records) == s.LEAVES
    assert all(record["pass_answer"] == "YES" for record in records.values())
    portfolio = json.loads((book_root() / "evaluation-results" / "hbq-first-remedy-portfolio-v1" / "manifest.json").read_text(encoding="utf-8"))
    p1 = next(item for item in portfolio["packages"] if item["package_id"] == "P1")
    assert tuple(p1["finding_ids"]) == s.FINDINGS
    s.verify_audit_membership()
    s.verify_criterion_ownership()


def test_reversed_or_swapped_audit_mapping_fails_closed(monkeypatch):
    s = study()
    original_load_json = s.load_json
    reversed_portfolio = deepcopy(original_load_json(s.PORTFOLIO_PATH))
    p1 = next(item for item in reversed_portfolio["packages"] if item["package_id"] == "P1")
    p1["finding_ids"] = list(reversed(p1["finding_ids"]))
    monkeypatch.setattr(s, "load_json", lambda path: reversed_portfolio if path == s.PORTFOLIO_PATH else original_load_json(path))
    with pytest.raises(ValueError, match="P1 portfolio membership drifted"):
        s.verify_audit_membership()
    monkeypatch.undo()

    ledger = deepcopy(s.load_findings_ledger())
    first = next(row for row in ledger if row["finding_id"] == s.FINDINGS[0])
    first["subjects"] = [s.LEAVES[1]]
    monkeypatch.setattr(s, "load_findings_ledger", lambda: ledger)
    with pytest.raises(ValueError, match="P1 audit finding-to-subject mapping drifted"):
        s.verify_audit_membership()


def test_criterion_ownership_mutation_fails_closed(monkeypatch):
    s = study()
    original_load_json = s.load_json
    altered = deepcopy(original_load_json(s.OWNERSHIP_PATH))
    altered[s.LEAVES[0]]["module_id"] = "wrong.owner"
    monkeypatch.setattr(s, "load_json", lambda path: altered if path == s.OWNERSHIP_PATH else original_load_json(path))
    with pytest.raises(ValueError, match="P1 criterion ownership drifted"):
        s.verify_criterion_ownership()


def test_each_leaf_has_one_public_leaf_specific_fixture_for_each_four_state():
    s = study()
    corpus = s.load_corpus()
    s.verify_corpus(corpus)
    for leaf in s.LEAVES:
        cases = [item for item in corpus["fixtures"] if item["leaf_id"] == leaf]
        assert len(cases) == 4
        assert {item["state"] for item in cases} == set(s.VERDICTS)
        assert len({item["text"] for item in cases}) == 4


def test_contract_or_fixture_drift_fails_closed(monkeypatch):
    s = study()
    contract = deepcopy(s.load_contract())
    contract["geometry"]["slots_exact"] = 131
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="P1 geometry drifted"):
        s.verify_package()
    corpus = deepcopy(s.load_corpus())
    corpus["fixtures"][0]["state"] = "MAYBE"
    with pytest.raises(ValueError, match="Fixture content drifted"):
        s.verify_corpus(corpus)


def test_all_singleton_prompts_use_current_production_renderer_without_oracle_leakage():
    s = study()
    prompts = s.render_all_provider_prompts()
    assert len(prompts) == 132
    slot = next(item for item in s.plan_slots() if item["leaf_id"] == "op.ingest.source_ingestion_fidelity.no_invention")
    prompt = prompts[slot["slot_id"]]
    assert "Is no unsupported content inserted into the ingested source?" in prompt
    assert slot["slot_id"] not in prompt
    assert slot["case_id"] not in prompt
    assert "expected_verdict" not in prompt
    assert "treatment_arm" not in prompt


def test_dry_run_and_render_plan_are_provider_free():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    plan = json.loads(rendered.stdout)
    assert plan["mode"] == "render_plan"
    assert len(plan["rendered_slots"]) == len(plan["prompt_sha256s"]) == 132
    source = (ROOT / "run.py").read_text(encoding="utf-8").lower()
    assert "requests" not in source and "subprocess" not in source and "--execute" not in source


def test_public_package_has_no_private_paths_or_dspy_dependency():
    forbidden = ("C:\\Users\\", "C:/Users/", "Gray Blood", "raw_response", "session_id", "api_key")
    for path in ROOT.iterdir():
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in forbidden)
        assert "import dspy" not in text and "from dspy" not in text
