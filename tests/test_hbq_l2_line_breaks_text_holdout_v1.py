from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterator

import pytest

from hbqrs.paths import book_root
from tests import _hbq_figurative_historical_runtime as cli_runtime
from tests import _hbq_l2_historical_runtime as historical_runtime


ROOT = book_root() / "evaluation-results" / "hbq-l2-line-breaks-text-holdout-v1"
FROZEN_COMMIT = "1290b6e7a244fc9388003240959e21504ca8cbf5"
PREDECESSOR_INVENTORY_COMMIT = "650f18dfee724db65d8bbc7fa2c7920ebcec1a9d"
CURRENT_CORPUS_SHA256 = "4f0dff1277d687a0bc821fe45dbc723dcecebe839cf812fcf8ffc9727bdd56d0"


def raw_study():
    spec = importlib.util.spec_from_file_location("hbq_l2_line_breaks_text_holdout_v1_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def study():
    module = raw_study()
    return historical_runtime.install_source(module, source_commit=module.PINNED_COMMIT)


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


def _git_show(commit: str, relative: str) -> bytes:
    result = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=ROOT.parents[1], capture_output=True, check=True)
    return bytes(result.stdout)


def _predecessor_public_json_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", PREDECESSOR_INVENTORY_COMMIT, "evaluation-results"],
        cwd=ROOT.parents[1],
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=True,
    )
    return [
        relative
        for relative in result.stdout.splitlines()
        if Path(relative).name.startswith("public") and Path(relative).suffix.lower() == ".json"
    ]


def test_new_texts_have_no_byte_collision_or_lexical_trigram_overlap_with_prior_public_corpora():
    s = study()
    targets = [case["text"] for case in s.load_corpus()["cases"]]
    assert subprocess.run(
        ["git", "rev-parse", f"{FROZEN_COMMIT}^"], cwd=ROOT.parents[1], text=True, capture_output=True, check=True
    ).stdout.strip() == PREDECESSOR_INVENTORY_COMMIT
    corpus_relative = (ROOT / "public-synthetic-corpus.json").relative_to(ROOT.parents[1]).as_posix()
    current_corpus = (ROOT / "public-synthetic-corpus.json").read_bytes()
    frozen_corpus = _git_show(FROZEN_COMMIT, corpus_relative)
    assert hashlib.sha256(frozen_corpus).hexdigest() == CURRENT_CORPUS_SHA256
    assert current_corpus == frozen_corpus
    assert s.load_contract()["bindings"]["corpus"]["sha256"] == CURRENT_CORPUS_SHA256
    prior_texts: list[str] = []
    for relative in _predecessor_public_json_paths():
        payload = json.loads(_git_show(PREDECESSOR_INVENTORY_COMMIT, relative))
        prior_texts.extend(_strings(payload))
    assert all(text not in prior_texts for text in targets)
    target_trigrams = {text: _trigrams(text) for text in targets}
    for prior in prior_texts:
        previous = _trigrams(prior)
        for target, grams in target_trigrams.items():
            if not grams or not previous:
                continue
            assert not (grams & previous), (target, prior, grams & previous)

    for name in (
        "hbq-l2-line-breaks-contextual-justification-treatment-v1",
        "hbq-l2-line-breaks-contextual-justification-treatment-v2",
    ):
        contextual = book_root() / "evaluation-results" / name
        contract = json.loads((contextual / "study-contract.json").read_text(encoding="utf-8"))
        assert contract["development_only"] is True
        assert contract["future_treatment_execution"]["permitted_here"] is False
        assert contract["scope"]["promotion"] == "none"
        assert "treatment-only" in (contextual / "README.md").read_text(encoding="utf-8").casefold()
        contextual_texts = json.loads((contextual / "public-synthetic-corpus.json").read_text(encoding="utf-8"))
        assert all(target in _strings(contextual_texts) for target in targets)
    result_path = book_root() / "evaluation-results" / "hbq-l2-line-breaks-text-holdout-v1-execution-v1-public-result-v1" / "public-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["decision"] == "NO_GO" and result["promotion"] == "none"


def test_pinned_source_runtime_lineage_and_git_blob_drift_fail_closed(monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValueError, match="Pinned production runtime drifted"):
        raw_study().verify_package()
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
    dry = cli_runtime.run_cli(study(), ROOT / "run.py", "--dry-run")
    plan = cli_runtime.run_cli(study(), ROOT / "run.py", "--render-plan")
    assert dry[0] == plan[0] == 0
    assert json.loads(dry[1])["verification"]["provider_calls"] == 0
    assert len(json.loads(plan[1])["rendered_slots"]) == 24
    for path in ROOT.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        source = path.read_text(encoding="utf-8")
        assert "import dspy" not in source and "from dspy" not in source
        assert "--execute" not in source
