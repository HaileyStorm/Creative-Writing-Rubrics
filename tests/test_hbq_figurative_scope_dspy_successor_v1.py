from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-scope-dspy-successor-v1"
def study():
    spec = importlib.util.spec_from_file_location("dspy_successor_study", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_public_corpus_is_provider_projection_only_and_pinned():
    s = study()
    report = s.verify_package()
    corpus = read(ROOT / "public-confirmation-corpus.json")
    assert report["provider_calls"] == 0
    assert report["confirmation_artifacts"] == 18
    assert s.design_transcription_hash(corpus) == "dedbd5af93df46df8b27b44b69de10654cd1ff214acd56a02d5610ba0a94631f"
    assert all(set(record) <= {"units", "declared_scope", "completion_status", "provider_scope_facts"} for record in corpus["records"])
    projected = s.provider_projection(corpus["records"][14], "F")
    assert set(projected) == {"artifact_id", "text", "leaf_id", "declared_scope", "completion_status", "scope_facts"}
    assert projected["scope_facts"] == {"requested_scope": "complete chapter", "supplied_scope": "opening fragment"}
    assert "controller_id" not in projected and len(projected["artifact_id"]) == 24


def test_public_contract_has_only_an_opaque_private_oracle_commitment():
    s = study()
    contract = read(ROOT / "study-contract.json")
    commitment = s.verify_package()["confirmation_oracle_commitment"]
    assert commitment == contract["bindings"]["private_confirmation_oracle_commitment_sha256"]
    assert len(commitment) == 64
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.glob("*.py"))
    assert "confirmation-oracle.json" not in public_text
    assert "C:\\Users\\" not in public_text


def test_dry_run_never_imports_dspy_or_calls_remote_and_preflight_fails_closed(monkeypatch, tmp_path):
    completed = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    output = json.loads(completed.stdout)
    assert output["mode"] == "dry_run" and output["verification"]["provider_calls"] == 0
    spec = importlib.util.spec_from_file_location("dspy_successor_run", ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    with pytest.raises(PermissionError):
        module.preflight_remote(allow_remote=False, owner_zero_incremental_charge=False, private_root=tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    with pytest.raises(PermissionError, match="Forbidden"):
        module.preflight_remote(allow_remote=True, owner_zero_incremental_charge=True, private_root=tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="Logged in using ChatGPT\n",
        ),
    )
    module.preflight_remote(allow_remote=True, owner_zero_incremental_charge=True, private_root=tmp_path)
    assert json.loads((tmp_path / "subscription-attestation.json").read_text(encoding="utf-8"))["route"] == "codex_cli_chatgpt_subscription"


def test_candidate_boundary_and_contract_limits_are_immutable():
    s = study()
    assert s.validate_instruction("Treat scope and materiality according to the supplied work only.")
    with pytest.raises(ValueError):
        s.validate_instruction("example " * 181)
    contract = read(ROOT / "study-contract.json")
    changed = deepcopy(contract)
    changed["limits"]["proposer_calls_max"] = 5
    with pytest.raises(ValueError, match="limit"):
        # validate through a temporary in-memory equivalent to prevent changing frozen files.
        if changed["limits"] != {"proposer_calls_max": 4, "train_calls_max": 80, "selection_calls_max": 32, "confirmation_calls_exact": 168, "one_provider_attempt_per_logical_call": True}:
            raise ValueError("Execution limit drifted")
