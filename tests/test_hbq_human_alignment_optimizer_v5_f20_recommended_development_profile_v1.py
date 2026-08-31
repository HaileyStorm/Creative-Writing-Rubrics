from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1"


def module():
    spec = importlib.util.spec_from_file_location("_recommended_profile_test", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def copied_package(tmp_path: Path) -> Path:
    copy = tmp_path / "package"
    shutil.copytree(PACKAGE, copy)
    return copy


def rewrite(path: Path, value: dict) -> None:
    path.write_bytes(module().canonical(value))


def test_literal_profile_reconstructs_from_the_pinned_constructor_and_has_no_runtime_optimizer():
    value = module()
    summary = value.validate_package()
    assert summary == {"study_id": value.STUDY_ID, "candidate_id": value.CANDIDATE_ID, "authority": "development_recommendation_only", "profile_sha256": "e78451385ea0d071869cb29ba9d5c1046694b1c7d17f2c6700523673e9cbdc99"}
    assert value.main([]) == 0
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "freeze.descendants" in source
    assert "import dspy" not in source and "import optuna" not in source


def test_literal_prompt_or_profile_mutation_is_rejected(tmp_path: Path):
    value = module(); copy = copied_package(tmp_path)
    profile = json.loads((copy / "profile.json").read_text(encoding="utf-8"))
    profile["instruction"] += " drift"
    rewrite(copy / "profile.json", profile)
    with pytest.raises(ValueError, match="profile file drifted"):
        value.validate_package(copy)


def test_declared_profile_hash_drift_is_rejected_before_constructor_admission():
    value = module()
    profile = json.loads((PACKAGE / "profile.json").read_text(encoding="utf-8"))
    profile["profile_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="literal profile hash drifted"):
        value._verify_profile(profile)


def test_authority_and_result_pin_drift_are_rejected(tmp_path: Path):
    value = module(); copy = copied_package(tmp_path)
    contract = json.loads((copy / "study-contract.json").read_text(encoding="utf-8"))
    contract["authority"]["runtime"] = "allowed"
    rewrite(copy / "study-contract.json", contract)
    with pytest.raises(ValueError, match="authority or pin drifted"):
        value.validate_package(copy)
    original = value.RESULT_PINS["grok_confirmation"]["sha256"]
    value.RESULT_PINS["grok_confirmation"]["sha256"] = "0" * 64
    try:
        with pytest.raises(ValueError, match="pin drifted"):
            value._verify_result_pins()
    finally:
        value.RESULT_PINS["grok_confirmation"]["sha256"] = original


def test_committed_sol_confirmation_and_broader_schedule_pins_resolve():
    value = module()
    sol = value.RESULT_PINS["sol_confirmation_v3"]
    assert sol["commit"] == "66859894b8081d83bd54ff4e9c40c0dd3050d0c5"
    assert value._blob(sol["commit"], sol["relative_path"]) == (ROOT / sol["relative_path"]).read_bytes()
    result = json.loads((ROOT / value.RESULT_PINS["broader_development_grok"]["relative_path"]).read_text(encoding="utf-8"))
    assert result["source_execution"]["freeze_schedule_sha256"] == value.FREEZE_SCHEDULE_SHA256
