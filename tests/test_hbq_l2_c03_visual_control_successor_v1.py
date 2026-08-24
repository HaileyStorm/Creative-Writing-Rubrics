from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-c03-visual-control-successor-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("hbq_l2_c03_visual_control_successor_v1_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_freeze_is_provider_free_and_has_exact_visual_geometry():
    study = load_study()
    assert study.verify_package()["provider_calls"] == 0
    assert study.verify_package()["image_fixture_bytes"] == {
        "structural_plane_incompatible_v1": 211503,
        "structural_plane_coherent_v1": 211503,
    }
    slots = study.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 12
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {(slot["case_id"], slot["leaf_id"]) for slot in slots} == {
        ("s01", "form.visual.environment_or_location_illustration.perspective"),
        ("s01", "form.visual.visual_craft_and_artifact_control.perspective"),
        ("s02", "form.visual.environment_or_location_illustration.perspective"),
        ("s02", "form.visual.visual_craft_and_artifact_control.perspective"),
    }
    contract = study.load_contract()
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}
    assert contract["promotion"] == {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"}
    assert contract["review_requirement"] == {"required_before_execution_successor": True, "reviewer": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning": "high", "independence": "independent"}, "status": "satisfied", "reviewed": True, "conclusion": "GO_for_diagnosis_only_execution_successor_design"}


def test_png_bindings_are_deterministic_text_free_and_structurally_distinct():
    study = load_study()
    fixtures = study.fixture_module().fixture_png_bytes()
    assert {name: hashlib.sha256(value).hexdigest() for name, value in fixtures.items()} == {
        "structural_plane_incompatible_v1": "d62f03a278a686a8710a96cdbceba0941611b7314878100580038d304efe24ff",
        "structural_plane_coherent_v1": "51c1ae52cc7d377594ca7c48f585f6f90dcf5057f697ab468eb4f7b898ce3f50",
    }
    assert all(value.startswith(b"\x89PNG\r\n\x1a\n") for value in fixtures.values())
    invariants = study.fixture_module().pixel_invariants()
    assert invariants["dimensions"] == (320, 220)
    assert invariants["text_or_directional_marks"] == "absent_by_generator_surface"
    assert invariants["coherent"]["derived_support_intersection"] == invariants["coherent"]["declared_vanishing_point"] == (160, 36)
    assert invariants["incompatible"]["derived_left_support_intersection"] != invariants["incompatible"]["derived_right_support_intersection"]
    assert invariants["coherent"]["longitudinal_rays"] == invariants["incompatible"]["longitudinal_rays"] == 6
    assert invariants["coherent"]["transverse_rows"] == invariants["incompatible"]["transverse_rows"] == 5
    assert invariants["fixtures_distinct"]


def test_expected_ledger_remains_separate_from_neutral_provider_inputs():
    study = load_study()
    assert study.load_ledger()["cells"] == {"s01": ["NO", "NO"], "s02": ["YES", "YES"]}
    corpus = json.loads((ROOT / "public-synthetic-corpus.json").read_text(encoding="utf-8"))
    assert all("expected" not in case and case["text"] == "" for case in corpus["cases"])
    inputs = study.render_all_provider_inputs()
    assert len(inputs) == 12
    for request in inputs.values():
        assert len(request["image_inputs"]) == 1
        assert "expected_verdict" not in request["prompt"]
        assert "expected-ledger" not in request["prompt"]
        assert "structural_plane_incompatible_v1" not in request["prompt"]
        assert "structural_plane_coherent_v1" not in request["prompt"]


def test_provider_free_commands_cannot_execute_or_import_dspy():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    plan = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    assert len(json.loads(plan.stdout)["rendered_slots"]) == 12
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        source = path.read_text(encoding="utf-8")
        assert "import dspy" not in source and "from dspy" not in source
        assert "--execute" not in source and "subprocess.run" not in source
