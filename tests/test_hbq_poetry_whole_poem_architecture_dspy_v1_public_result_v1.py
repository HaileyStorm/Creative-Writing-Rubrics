from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-whole-poem-architecture-dspy-v1-public-result-v1"


def _module():
    spec = importlib.util.spec_from_file_location("dspy_v6_public_result_verify", ROOT / "verify.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_result_is_exact_aggregate_only_projection() -> None:
    module = _module()
    assert module.validate() == {
        "study_id": "hbq-poetry-whole-poem-architecture-dspy-v1-public-result-v1",
        "state": "valid_aggregate_only_public_result",
        "classification": "HARNESS_INVALID_OPTIMIZATION_NO_TRANSFER_NO_PROMOTION",
        "contacts": 44,
        "promotion": "none",
    }


def test_package_contains_only_the_public_projection_files() -> None:
    assert {
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    } == {"aggregate.v1.json", "README.md", "verify.py"}


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value["execution"].update({"confirmed_provider_contacts": 43}),
        lambda value: value["mechanical_metrics"]["trial_2"].update({"matched": 1}),
        lambda value: value["mechanical_evidence"]["allowed_literal_verdicts"].update({"matched": 1}),
        lambda value: value["manual_semantic_rescore"]["complete_single_part_na_boundary"].update({"missed": 4}),
        lambda value: value["source_commitments"].update({"settlement_sha256": "0" * 64}),
        lambda value: value["decisions"].update({"promotion": "candidate"}),
        lambda value: value["publication"].update({"contains_raw_responses": True}),
    ),
)
def test_tampering_is_rejected(mutate) -> None:
    module = _module()
    altered = deepcopy(module.read_result())
    mutate(altered)
    with pytest.raises(ValueError):
        module.validate(altered)
