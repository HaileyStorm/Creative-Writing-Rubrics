from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import struct
import zlib

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-construct-microgate-v1"


def load_study():
    spec = importlib.util.spec_from_file_location("l2_construct_microgate_study", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fixture_invariants():
    path = ROOT / "assets" / "generate_geometry_fixture.py"
    spec = importlib.util.spec_from_file_location("l2_construct_microgate_fixture", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.pixel_invariants()


def test_freeze_has_exact_microgate_geometry_and_provider_free_boundary():
    study = load_study()
    assert study.verify_package() == {
        "study_id": "hbq-l2-construct-microgate-v1",
        "status": "frozen_provider_free_construct_microgate",
        "provider_calls": 0,
        "cases": 4,
        "cells": 8,
        "slots": 24,
        "image_fixture_bytes": 129853,
    }
    slots = study.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 24
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["expected_verdict"] for slot in slots} == {"YES", "NO", "CANNOT_ASSESS"}
    contract = study.load_contract()
    assert contract["provider_execution"] == {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}
    assert contract["lifecycle"] == {"policy": "terminal_sidecar_v1", "remote_execution_surface": "absent", "retry_or_resume": "not_authorized_by_freeze"}


def test_cases_bind_exact_existing_leaves_and_separate_expected_ledger():
    study = load_study()
    assert study.CASE_LEAVES == {
        "c01": ("form.poetry.free_verse.line_breaks", "form.poetry.free_verse.necessity"),
        "c02": ("form.poetry.free_verse.line_breaks", "form.poetry.free_verse.necessity"),
        "c03": ("form.visual.environment_or_location_illustration.perspective", "form.visual.visual_craft_and_artifact_control.perspective"),
        "c04": ("form.visual.environment_or_location_illustration.perspective", "form.visual.visual_craft_and_artifact_control.perspective"),
    }
    assert study.load_ledger() == {"format_version": 2, "study_id": "hbq-l2-construct-microgate-v1", "fixture_binding": {"c03": "impossible_stairwell_v1"}, "cells": {"c01": ["YES", "YES"], "c02": ["NO", "NO"], "c03": ["NO", "NO"], "c04": ["CANNOT_ASSESS", "CANNOT_ASSESS"]}}
    corpus = json.loads((ROOT / "public-synthetic-corpus.json").read_text(encoding="utf-8"))
    assert all("expected" not in case for case in corpus["cases"])
    assert corpus["cases"][0]["text"].count("\n") == 3 and "\\n" not in corpus["cases"][0]["text"]
    records = study.compiled_leaf_records()
    assert records["form.poetry.free_verse.necessity"]["question"]["text"] == "Does free-verse form feel necessary to the poem's movement and voice?"
    assert records["form.visual.environment_or_location_illustration.perspective"]["question"]["text"] == "Are perspective, scale, and geometry coherent?"
    assert all(record["question"]["applies_when"] == "The criterion is relevant to the requested artifact, scope, and operation." for record in records.values())
    assert study.CASE_ACTIVATIONS == {"c01": ("poetry.free_verse", "poetry", "poem"), "c02": ("poetry.free_verse", "poetry", "poem"), "c03": ("visual.environment", "visual_asset", "asset"), "c04": ("visual.environment", "visual_asset", "asset")}


def test_deterministic_impossible_stairwell_png_and_absent_image_control_are_distinct():
    study = load_study()
    png = study.stairwell_png_bytes()
    assert png.startswith(bytes((137, 80, 78, 71, 13, 10, 26, 10)))
    assert len(png) == 129853
    requests = study.render_all_provider_inputs()
    visual_present = [slot for slot in study.plan_slots() if slot["case_id"] == "c03"]
    visual_absent = [slot for slot in study.plan_slots() if slot["case_id"] == "c04"]
    assert len(visual_present) == len(visual_absent) == 6
    assert all(len(requests[slot["slot_id"]]["image_inputs"]) == 1 for slot in visual_present)
    attachment = requests[visual_present[0]["slot_id"]]["image_inputs"][0]
    assert study.public_attachment_record(attachment) == {"fixture_id": "stairwell-01.png", "mime_type": "image/png", "bytes": 129853, "sha256": "104631a4d662f2435e000cca86921a68dbb303ed58cd24759a717c7ae171ceb7"}
    assert attachment["attachment_bytes"] == png
    assert struct.unpack(">II", png[16:24]) == (240, 180)
    idat_size = struct.unpack(">I", png[33:37])[0]
    raw = zlib.decompress(png[41:41 + idat_size])
    assert bytes((98, 146, 173)) in raw
    assert bytes((205, 117, 62)) in raw
    assert bytes((109, 61, 38)) in raw
    invariants = fixture_invariants()
    assert invariants["closed_loop"]["landings"] == (0, 1, 2, 3)
    assert invariants["closed_loop"]["successors"] == (1, 2, 3, 0)
    assert invariants["closed_loop"]["returns_to_zero"] and invariants["closed_loop"]["all_flights_marked_up"]
    assert invariants["closed_loop"]["marker_pixels_present"] == (True, True, True, True)
    assert invariants["closed_loop"]["edge_pixels_present"] == (True, True, True, True)
    assert invariants["occlusion"]["foreground_masks_behind"]
    assert all(not requests[slot["slot_id"]]["image_inputs"] for slot in visual_absent)
    assert all("image_input_required=true" in requests[slot["slot_id"]]["prompt"] for slot in visual_present + visual_absent)
    assert all('"completion_status": "complete"' in requests[slot["slot_id"]]["prompt"] for slot in visual_absent)


def test_prompts_are_production_rendered_and_cannot_receive_expected_ledger_metadata():
    study = load_study()
    prompts = "\n".join(item["prompt"] for item in study.render_all_provider_inputs().values())
    assert "expected_verdict" not in prompts
    assert "expected-ledger" not in prompts
    assert "systematic_miss" not in prompts
    assert all(case_id not in prompts for case_id in study.CASE_LEAVES)
    assert "form.poetry.free_verse.line_breaks" in study.provider_request("l2micro-v1-001")["prompt"]
    assert "form.poetry.free_verse.necessity" in study.provider_request("l2micro-v1-004")["prompt"]
    assert "form.visual.environment_or_location_illustration.perspective" in study.provider_request("l2micro-v1-013")["prompt"]


def test_drift_in_ledger_or_review_gate_fails_closed(monkeypatch: pytest.MonkeyPatch):
    study = load_study()
    ledger = deepcopy(study.load_ledger())
    ledger["cells"]["c03"] = ["YES", "NO"]
    with pytest.raises(ValueError, match="Expected ledger"):
        study.verify_ledger(ledger)
    contract = deepcopy(study.load_contract())
    contract["review_requirement"]["status"] = "approved"
    monkeypatch.setattr(study, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Contract policy"):
        study.verify_package()


def test_gates_are_exhaustive_for_one_two_and_zero_of_three():
    study = load_study()
    assert study.load_contract()["gating"] == {
        "fixture_driven_close": "24_of_24_slots_and_8_of_8_cells_at_3_of_3",
        "one_of_three": "variance_no_go",
        "two_of_three": "variance_no_go",
        "systematic_miss": "any_cell_at_0_of_3_may_authorize_leaf_specific_treatment_design_only",
    }


def test_provider_free_commands_have_no_execution_surface():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    rendered = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    plan = json.loads(rendered.stdout)
    assert len(plan["rendered_slots"]) == 24 and len(plan["image_input_slots"]) == 6
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert "import dspy" not in text and "from dspy" not in text
        assert "--execute" not in text and "subprocess.run" not in text
