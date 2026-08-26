from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-other-lexical-overlap-ownership-v1"
ARCHIVED_REASON = (
    "Archived lexical-overlap mechanics require six exact historical module snapshots "
    "that are unavailable in CWR Git history; preserve the frozen package and await a "
    "versioned successor or restored snapshot."
)


def load_study():
    spec = importlib.util.spec_from_file_location("other_lexical_overlap_study", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_current_checkout_fails_closed_while_frozen_contract_geometry_remains_bound():
    study = load_study()
    with pytest.raises(ValueError, match="Current production runtime binding drifted"):
        study.verify_package()
    contract = study.load_contract()
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}
    assert contract["geometry"] == {"blocks_exact": 3, "semantic_conditions_per_block_exact": 6, "matched_carriers_exact": 2, "leaves_per_block_exact": 2, "repeats_exact": 3, "slots_exact": 216}
    assert contract["labels"] == ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]
    assert contract["scoring"] == study.SCORING
    assert contract["promotion"] == {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}
    study.verify_corpus(study.load_corpus())
    assert len(study.verify_assets(contract)) == 6
    slots = study.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 216
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["expected_verdict"] for slot in slots} == study.VERDICTS


def test_exact_l2_findings_leaf_ownership_and_pair_specific_oracles_are_bound():
    study = load_study()
    assert study.FINDING_IDS == (
        "338b510127809018cc8f14b2674e5960ac6bb70d8692e7af300d74a3eab0ed80",
        "984e94e56c811360f817c98f76022d74e2c399454dec8874078bc70e59198bc4",
        "ff3c0acd77e9eae45b077e6ffe458c8c7b34e00fac6606f1e581d5a37755cb9a",
    )
    records = study.source_leaf_records()
    assert set(records) == {leaf for pair in study.BLOCK_LEAVES.values() for leaf in pair}
    assert records["form.poetry.free_verse.necessity"]["text"] == "Does free-verse form feel necessary to the poem's movement and voice?"
    assert records["form.visual.environment_or_location_illustration.perspective"]["text"] == "Are perspective, scale, and geometry coherent?"
    artifacts = study.materialize_artifacts()
    free = [tuple(item["expected"].values()) for item in artifacts if item["block_id"] == "free_verse_form_scope" and item["carrier"] == "isolated"]
    assert ("YES", "NO") in free and ("NO", "YES") in free
    prose = [tuple(item["expected"].values()) for item in artifacts if item["block_id"] == "prose_poem_image_relation" and item["carrier"] == "isolated"]
    assert prose.count(("YES", "NOT_APPLICABLE")) == 1
    assert ("YES", "NO") not in prose and ("NO", "YES") not in prose
    visual = [tuple(item["expected"].values()) for item in artifacts if item["block_id"] == "visual_perspective"]
    assert all(left == right for left, right in visual)


def test_visual_assets_are_real_png_image_inputs_not_textual_substitutes():
    study = load_study()
    fixtures = study.verify_assets(study.load_contract())
    assert len(fixtures) == 6
    assert all((ROOT / item["path"]).read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for item in fixtures.values())
    requests = study.render_all_provider_inputs()
    visual_slots = [slot for slot in study.plan_slots() if slot["block_id"] == "visual_perspective"]
    assert len(visual_slots) == 72
    assert all(len(requests[slot["slot_id"]]["image_inputs"]) == 1 for slot in visual_slots)
    assert all(requests[slot["slot_id"]]["image_inputs"][0]["mime_type"] == "image/png" for slot in visual_slots)
    assert all(not requests[slot["slot_id"]]["image_inputs"] for slot in study.plan_slots() if slot["block_id"] != "visual_perspective")
    visual_artifacts = [item for item in study.materialize_artifacts() if item["block_id"] == "visual_perspective"]
    assert all(item["text"] == "" and item["image_fixture"] in fixtures for item in visual_artifacts)
    generator_path = ROOT / "assets" / "generate_visual_fixtures.py"
    spec = importlib.util.spec_from_file_location("l2_fixture_generator", generator_path)
    generator = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(generator)
    assert all((ROOT / item["path"]).read_bytes() == generator.png_bytes(item["fixture_id"]) for item in fixtures.values())


def test_rendered_singleton_prompts_use_production_renderer_without_ledger_leakage():
    study = load_study()
    requests = study.render_all_provider_inputs()
    assert len(requests) == 216
    rendered = "\n".join(request["prompt"] for request in requests.values())
    assert all(finding_id not in rendered for finding_id in study.FINDING_IDS)
    assert "expected_verdict" not in rendered and "condition_id" not in rendered and "oracle" not in rendered
    assert "form.poetry.free_verse.necessity" in requests["l2-v1-001"]["prompt"]
    assert "form.visual.environment_or_location_illustration.perspective" in requests["l2-v1-145"]["prompt"]
    assert all(re.fullmatch(r"(?:artifact|asset)-\d{2}\.(?:txt|png)", item["artifact_name"]) for item in study.materialize_artifacts())
    assert all(token not in rendered for token in ("free_verse_form_scope", "prose_poem_image_relation", "visual_perspective", "form-only", "scope-only", "general-only"))


def test_oracle_ledger_and_completion_context_are_noninterfering(monkeypatch):
    study = load_study()
    slot_id = "l2-v1-001"
    original_prompt = study.provider_request(slot_id)["prompt"]
    original = study.load_corpus()
    altered = deepcopy(original)
    altered["blocks"][0]["conditions"][0]["expected"] = ["NO", "CANNOT_ASSESS"]
    assert altered["blocks"][0]["conditions"][0]["completion_status"] == original["blocks"][0]["conditions"][0]["completion_status"]
    monkeypatch.setattr(study, "load_corpus", lambda: altered)
    assert study.provider_request(slot_id)["prompt"] == original_prompt


def test_contract_and_oracle_drift_fail_closed(monkeypatch):
    study = load_study()
    corpus = deepcopy(study.load_corpus())
    corpus["blocks"][0]["conditions"][1]["expected"] = ["NO", "YES"]
    with pytest.raises(ValueError, match="Free-verse"):
        study.verify_corpus(corpus)
    corpus = deepcopy(study.load_corpus())
    corpus["blocks"][1]["conditions"][1]["expected"] = ["YES", "NO"]
    with pytest.raises(ValueError, match="Prose-image"):
        study.verify_corpus(corpus)
    corpus = deepcopy(study.load_corpus())
    corpus["blocks"][2]["conditions"][0]["expected"] = ["YES", "NO"]
    with pytest.raises(ValueError, match="Visual block"):
        study.verify_corpus(corpus)
    contract = deepcopy(study.load_contract())
    contract["image_delivery"]["text_substitution_forbidden"] = False
    monkeypatch.setattr(study, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Image-input"):
        study.verify_package()


@pytest.mark.skip(reason=ARCHIVED_REASON)
def test_provider_free_commands_retain_the_archived_runtime_boundary():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    plan = json.loads(rendered.stdout)
    assert len(plan["rendered_slots"]) == 216 and len(plan["image_input_slots"]) == 72


def test_provider_free_sources_have_no_execution_surface():
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "import dspy" not in text and "from dspy" not in text
        assert "--execute" not in text and "requests" not in text.lower()
