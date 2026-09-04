from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v10-child20-development-profile-v1"


def module():
    spec = importlib.util.spec_from_file_location("_child20_profile_test", PACKAGE / "verify.py")
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


def test_literal_profile_reconstructs_without_provider_or_private_root():
    value = module()
    assert value.validate_package() == {
        "authority": "development_recommendation_only",
        "instruction_sha256": "e172abcab5284fe415d82cff30e1851f08c6ba8d4baccc764eeccf788a6e036d",
        "profile_sha256": "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20",
        "study_id": value.STUDY_ID,
    }
    profile = json.loads((PACKAGE / "profile.json").read_bytes())
    assert len(profile["instruction"].encode("utf-8")) == 794
    assert len(value.canonical(profile["profile"]).rstrip()) == 1644
    assert value.main([]) == 0
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert "private_root" not in source and "import dspy" not in source and "import optuna" not in source


@pytest.mark.parametrize("field", ["instruction", "profile"])
def test_literal_instruction_or_profile_mutation_is_rejected(tmp_path: Path, field: str):
    value = module()
    copy = copied_package(tmp_path)
    profile = json.loads((copy / "profile.json").read_bytes())
    if field == "instruction":
        profile["instruction"] += " drift"
    else:
        profile["profile"]["factors"]["missing_evidence_not_no"] += " drift"
    rewrite(copy / "profile.json", profile)
    with pytest.raises(ValueError, match="profile file drifted"):
        value.validate_package(copy)


def test_literal_profile_envelope_and_hash_mutations_are_rejected():
    value = module()
    profile = json.loads((PACKAGE / "profile.json").read_bytes())
    profile["profile_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash drifted"):
        value.verify_literal(profile)
    profile = json.loads((PACKAGE / "profile.json").read_bytes())
    profile["unexpected"] = True
    with pytest.raises(ValueError, match="envelope drifted"):
        value.verify_literal(profile)


def test_contract_and_result_pin_mutations_are_rejected(tmp_path: Path):
    value = module()
    copy = copied_package(tmp_path)
    contract = json.loads((copy / "study-contract.json").read_bytes())
    contract["authority"]["runtime"] = "allowed"
    rewrite(copy / "study-contract.json", contract)
    with pytest.raises(ValueError, match="contract envelope drifted"):
        value.validate_package(copy)
    original = value.RESULT_PINS["sol_confirmation"]["sha256"]
    value.RESULT_PINS["sol_confirmation"]["sha256"] = "0" * 64
    try:
        with pytest.raises(ValueError, match="sol_confirmation result drifted"):
            value.verify_result_pins()
    finally:
        value.RESULT_PINS["sol_confirmation"]["sha256"] = original
    original = value.V10_STUDY_SHA256
    value.V10_STUDY_SHA256 = "0" * 64
    try:
        with pytest.raises(ValueError, match="pinned V10 constructor drifted"):
            value.reconstruct_child()
    finally:
        value.V10_STUDY_SHA256 = original
