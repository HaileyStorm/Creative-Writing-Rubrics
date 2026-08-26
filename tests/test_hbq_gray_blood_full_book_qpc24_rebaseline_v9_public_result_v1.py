from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
PACKAGE = (
    REPOSITORY
    / "evaluation-results"
    / "hbq-gray-blood-full-book-qpc24-rebaseline-v9-public-result-v1"
)
sys.dont_write_bytecode = True
EXPECTED_VERIFIER_SHA256 = (
    "9d396472b48318d6ac02d78b2c8a39048ea55f27893d64e30205338d0a6ac64d"
)


def _verifier():
    spec = importlib.util.spec_from_file_location(
        "qpc24_v9_public_result", PACKAGE / "verify_output.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load the QPC24 V9 public verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _copy_package(tmp_path: Path) -> Path:
    candidate = tmp_path / "public-result"
    shutil.copytree(PACKAGE, candidate)
    return candidate


def test_v9_public_result_is_aggregate_only_and_full_fidelity() -> None:
    value = _verifier().verify()

    assert value["execution"] == {
        "combined_binary_calls": 150,
        "combined_positions": 3406,
        "full_fidelity": True,
        "prior_structured_calls": 6,
        "provider_calls": 0,
        "sampling": "NONE",
    }
    assert value["comparison"] == {
        "bounds_relation": "NON_STATISTICAL_NONOVERLAP",
        "score_difference_rewrite_minus_author": 10.2167,
    }
    assert value["decision"] == {
        "criterion_ownership_changes": 0,
        "promotion": "NONE",
        "rubric_changes": 0,
        "weight_changes": 0,
    }
    assert (
        sha256((PACKAGE / "verify_output.py").read_bytes()).hexdigest()
        == EXPECTED_VERIFIER_SHA256
    )


def test_v9_public_result_rejects_tampering_private_detail_and_extra_files(
    tmp_path: Path,
) -> None:
    verifier = _verifier()
    candidate = _copy_package(tmp_path)
    aggregate = candidate / "aggregate.v1.json"
    payload = json.loads(aggregate.read_text(encoding="utf-8"))
    payload["artifacts"][0]["coverage"] = 0.5
    aggregate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="identity drifted"):
        verifier.verify(candidate)

    candidate = _copy_package(tmp_path / "readme")
    (candidate / "README.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="README binding drifted"):
        verifier.verify(candidate)

    candidate = _copy_package(tmp_path / "surface")
    (candidate / "unexpected.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError, match="surface drifted"):
        verifier.verify(candidate)

    candidate = _copy_package(tmp_path / "cache")
    cache = candidate / "__pycache__"
    cache.mkdir()
    (cache / "verify_output.pyc").write_bytes(b"generated")
    with pytest.raises(ValueError, match="surface drifted"):
        verifier.verify(candidate)


def test_v9_public_result_rejects_inconsistent_aggregate_arithmetic() -> None:
    verifier = _verifier()
    malformed = deepcopy(verifier.EXPECTED)
    malformed["comparison"]["score_difference_rewrite_minus_author"] = 0.0

    with pytest.raises(ValueError, match="score difference drifted"):
        verifier._assert_arithmetic(malformed)
