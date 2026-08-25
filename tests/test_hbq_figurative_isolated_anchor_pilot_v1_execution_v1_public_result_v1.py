from __future__ import annotations

import importlib.util
import inspect
import json
import sys

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-figurative-isolated-anchor-pilot-v1-execution-v1-public-result-v1"
SOURCE = ROOT.parent / "hbq-figurative-isolated-anchor-pilot-v1-execution-v1"


def verifier():
    spec = importlib.util.spec_from_file_location("figurative_anchor_public_result", ROOT / "verify.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def settled_verifier():
    spec = importlib.util.spec_from_file_location("figurative_anchor_settled_verifier", SOURCE / "verify_settled.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_public_result_is_exact_aggregate_only_and_valid():
    value = verifier().validate()
    assert value == {
        "study_id": "hbq-figurative-isolated-anchor-pilot-v1-execution-v1-public-result-v1",
        "state": "valid_aggregate_only_public_result",
        "completed_slots": 18,
        "controls_correct": 12,
        "target_correct": 5,
        "decision": "MANUAL_TARGET_UNSTABLE_NO_GO_DSPY_ELIGIBLE",
        "promotion": "none",
    }


def test_public_interpretation_does_not_claim_substantive_wording_failure():
    aggregate = json.loads((ROOT / "aggregate.v1.json").read_text(encoding="utf-8"))
    assert aggregate["target"]["cells"] == {
        "cooperative_anchor": {"correct": 3, "total": 3},
        "incompatible_imagery_anchor": {"correct": 2, "total": 3},
    }
    assert aggregate["interpretation"]["not_supported"] == "stable substantive wording failure"
    assert aggregate["interpretation"]["promotion"] == "none"
    assert aggregate["controls"]["core.freshness_and_non_genericness.no_default_metaphors"]["role"] == "stockness_owner"
    assert aggregate["controls"]["penalty.purple_prose.proportion"]["role"] == "density_owner"


def test_public_files_exclude_private_payloads_and_absolute_user_paths():
    forbidden = (
        "C:\\Users\\Haile",
        '"artifact_text":',
        '"session_id":',
        '"run_id":',
        "normalized_verdicts",
        "provider_artifacts",
    )
    for path in ROOT.iterdir():
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert all(token not in text for token in forbidden), path.name


def test_settled_verifier_does_not_delegate_to_settle_idempotence():
    source = inspect.getsource(settled_verifier().verify_settled)
    assert ".settle(" not in source
    assert "_verify_slot" in source
    assert "_expected_settlement" in source


def test_executor_readme_uses_portable_private_root_example():
    text = (SOURCE / "README.md").read_text(encoding="utf-8")
    assert "C:\\Users\\Haile" not in text
    assert "$privateRoot = 'C:\\path\\outside\\CWR\\figurative-anchor-pilot-private'" in text
