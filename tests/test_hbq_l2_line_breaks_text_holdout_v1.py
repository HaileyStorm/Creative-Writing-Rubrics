from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-text-holdout-v1"


def study():
    spec = importlib.util.spec_from_file_location("hbq_l2_line_breaks_text_holdout_v1_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_freeze_has_exact_text_only_geometry_and_mixed_crossed_expectations():
    s = study()
    assert s.verify_package() == {
        "study_id": "hbq-l2-line-breaks-text-holdout-v1",
        "status": "frozen_provider_free_text_only_candidate_line_break_holdout",
        "provider_calls": 0,
        "cases": 4,
        "cells": 8,
        "slots": 24,
        "image_input_slots": 0,
    }
    assert s.load_ledger()["cells"] == {
        "t01": ["YES", "YES"],
        "t02": ["NO", "NO"],
        "t03": ["NOT_APPLICABLE", "NO"],
        "t04": ["YES", "NO"],
    }
    slots = s.plan_slots()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 24
    assert {slot["repeat"] for slot in slots} == {1, 2, 3}
    assert {slot["expected_verdict"] for slot in slots} == {"YES", "NO", "NOT_APPLICABLE"}


def test_texts_are_frozen_and_images_are_not_part_of_the_holdout_surface():
    s = study()
    assert s.materialize_artifacts() == {
        "t01": {"case_id": "t01", "artifact_name": "artifact-11.txt", "artifact_type": "poetry", "bundle_id": "poetry.free_verse", "declared_scope": "poem", "completion_status": "complete", "text": "Before dawn\nthe tram rail\ngives back\nthe green of its signal.", "image_input_required": False, "image_fixture": None},
        "t02": {"case_id": "t02", "artifact_name": "artifact-12.txt", "artifact_type": "poetry", "bundle_id": "poetry.free_verse", "declared_scope": "poem", "completion_status": "complete", "text": "Clerks archived the\nminutes beneath the\ncabinet after the\nnoon delivery.", "image_input_required": False, "image_fixture": None},
        "t03": {"case_id": "t03", "artifact_name": "artifact-13.txt", "artifact_type": "poetry", "bundle_id": "poetry.free_verse", "declared_scope": "poem", "completion_status": "complete", "text": "The mineral exhibit dimmed behind its glass at closing.", "image_input_required": False, "image_fixture": None},
        "t04": {"case_id": "t04", "artifact_name": "artifact-14.txt", "artifact_type": "poetry", "bundle_id": "poetry.free_verse", "declared_scope": "poem", "completion_status": "complete", "text": "A narrow moon hangs white above the lane;\nthe last bus leaves, and leaves the rain again.", "image_input_required": False, "image_fixture": None},
    }


def test_t02_breaks_are_deliberately_arbitrary_and_t04_is_a_formal_rhymed_couplet():
    texts = {case["case_id"]: case["text"] for case in study().load_corpus()["cases"]}
    assert [line.rsplit(" ", 1)[-1] for line in texts["t02"].splitlines()[:-1]] == ["the", "the", "the"]
    assert texts["t04"].splitlines() == [
        "A narrow moon hangs white above the lane;",
        "the last bus leaves, and leaves the rain again.",
    ]
    assert texts["t04"].splitlines()[0].rstrip(";.,").endswith("lane")
    assert texts["t04"].splitlines()[1].rstrip(";.,").endswith("again")


def test_candidate_delta_is_line_break_question_text_only_and_canonical_control_is_unchanged():
    s = study()
    canonical = s.canonical_question(s.LINE_BREAKS)
    candidate = s.question_for(s.LINE_BREAKS)
    restored = deepcopy(candidate)
    restored["question"]["text"] = canonical["question"]["text"]
    assert restored == canonical
    assert candidate["question"]["text"] == s.CANDIDATE_TEXT
    assert s.question_for(s.NECESSITY) == s.canonical_question(s.NECESSITY)
    assert s.load_contract()["promotion"] == {"prompt": "none", "rubric": "none", "leaf": "none", "ownership": "none", "split": "none", "merge": "none", "weight": "none"}


def test_provider_inputs_are_ledger_blind_text_only_and_use_the_canonical_renderer():
    s = study()
    inputs = s.render_all_provider_inputs()
    assert len(inputs) == 24
    assert all(not request["image_inputs"] for request in inputs.values())
    prompts = "\n".join(request["prompt"] for request in inputs.values())
    assert s.CANDIDATE_TEXT in inputs["l2text-v1-001"]["prompt"]
    assert s.canonical_question(s.NECESSITY)["question"]["text"] in inputs["l2text-v1-004"]["prompt"]
    for forbidden in ("expected_verdict", "expected-ledger", "text-holdout", "YES/YES", "NO/NO", "NOT_APPLICABLE/NO", "YES/NO"):
        assert forbidden not in prompts
    assert "holdout" not in prompts.lower()


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _trigrams(text: str) -> set[tuple[str, str, str]]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return set(zip(words, words[1:], words[2:]))


def test_new_texts_have_no_byte_collision_or_lexical_trigram_overlap_with_prior_public_corpora():
    s = study()
    targets = [case["text"] for case in s.load_corpus()["cases"]]
    prior_texts: list[str] = []
    for path in (book_root() / "evaluation-results").rglob("public*.json"):
        if ROOT in path.parents:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        prior_texts.extend(_strings(payload))
    assert all(text not in prior_texts for text in targets)
    target_trigrams = {text: _trigrams(text) for text in targets}
    for prior in prior_texts:
        previous = _trigrams(prior)
        for target, grams in target_trigrams.items():
            if not grams or not previous:
                continue
            assert not (grams & previous), (target, prior, grams & previous)


def test_pinned_source_runtime_lineage_and_git_blob_drift_fail_closed(monkeypatch: pytest.MonkeyPatch):
    s = study()
    original = s.sha256_file

    def drifted(path: Path) -> str:
        if path == s.REPOSITORY / "src/hbqrs/runner.py":
            return "0" * 64
        return original(path)

    with monkeypatch.context() as context:
        context.setattr(s, "sha256_file", drifted)
        with pytest.raises(ValueError, match="Pinned production runtime"):
            s.verify_bindings()
    original_run = s.subprocess.run

    def bad_blob(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(args, 0, "0" * 40 + "\n", "")
        return original_run(args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(s.subprocess, "run", bad_blob)
        with pytest.raises(ValueError, match="Git blob provenance"):
            s.verify_bindings()
    contract = deepcopy(s.load_contract())
    contract["history"]["visual_controls"] = "reuse"
    monkeypatch.setattr(s, "load_contract", lambda: contract)
    with pytest.raises(ValueError, match="Contract policy"):
        s.verify_package()


def test_command_surface_is_provider_free():
    dry = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    plan = subprocess.run([sys.executable, str(ROOT / "run.py"), "--render-plan"], text=True, capture_output=True, check=True)
    assert json.loads(dry.stdout)["verification"]["provider_calls"] == 0
    assert len(json.loads(plan.stdout)["rendered_slots"]) == 24
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        source = path.read_text(encoding="utf-8")
        assert "import dspy" not in source and "from dspy" not in source
        assert "--execute" not in source
