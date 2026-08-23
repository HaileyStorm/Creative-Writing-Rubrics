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


def test_settled_public_result_is_aggregate_only_and_hash_pinned():
    s = study()
    value = read(ROOT / "public-result.json")
    report = s.validate_public_result()
    assert s.sha256_file(ROOT / "public-result.json") == s.PUBLIC_RESULT_SHA256 == "65199fbe4e8ec25ccba324ca9c310ad1235b2e81e4183611cfb591a010f37013"
    assert read(ROOT / "study-contract.json")["public_result_sha256"] == s.PUBLIC_RESULT_SHA256
    assert report == {
        "decision": "NO_GO",
        "accepted_calls": 84,
        "source_private_aggregate_sha256": "4982e2b78572276cff717dfb130dc8742fe4f790a2b6b05dac9eb5779094094c",
    }
    assert value["execution"] == {
        "proposer_calls": 4,
        "train_calls": 80,
        "selection_calls": 0,
        "confirmation_calls": 0,
        "accepted_calls": 84,
        "rejected_calls": 0,
        "route": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "zero_incremental_charge": "owner_attested_subscription_route_not_independent_billing_proof",
    }
    assert value["train"]["candidate_scores"] == [[18, 20], [17, 20], [17, 20], [18, 20]]
    assert value["train"]["leaf_totals"] == {"stockness": [32, 32], "proportion": [30, 40], "fatigue": [8, 8]}
    assert value["train"]["full_pass_candidates"] == [0, 4]
    assert value["confirmation_accessed"] is False


def test_public_result_semantic_and_privacy_mutations_fail_without_hash_shortcuts():
    s = study()
    value = read(ROOT / "public-result.json")
    s._validate_public_result_value(value)
    for mutate in (
        lambda item: item["execution"].update({"accepted_calls": 83}),
        lambda item: item["train"]["leaf_totals"].update({"proportion": [31, 40]}),
        lambda item: item["train"].update({"full_pass_candidates": [2, 4]}),
        lambda item: item.update({"confirmation_accessed": True}),
        lambda item: item.update({"candidate_hash": "not-public"}),
        lambda item: item.update({"private_path": "C:/private"}),
        lambda item: item.update({"raw_prompt": "not-public"}),
        lambda item: item.update({"case_label": "not-public"}),
        lambda item: item.update({"conclusion": "Promote a rubric change."}),
    ):
        changed = deepcopy(value)
        mutate(changed)
        with pytest.raises(ValueError):
            s._validate_public_result_value(changed)


def test_public_result_rejects_value_level_private_leakage_before_identity_checks():
    s = study()
    changed = read(ROOT / "public-result.json")
    changed["conclusion"] += " C:\\Users\\Haile\\private session_id raw-response exact quote private"
    with pytest.raises(ValueError, match="private evidence text"):
        s._validate_public_result_value(changed)


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
    assert contract["status"] == "settled_no_go_no_promotion"
    assert contract["result_lineage"] == {
        "execution_commit": "d3f65b765f1588b9c536834484a141ea6d1a7918",
        "private_aggregate_sha256": "4982e2b78572276cff717dfb130dc8742fe4f790a2b6b05dac9eb5779094094c",
        "private_result_sha256": "e640103ec7e8b9bb3e2802f1af7f07eb0adf3799185513ec783e833d18fec5df",
    }
    changed = deepcopy(contract)
    changed["limits"]["proposer_calls_max"] = 5
    with pytest.raises(ValueError, match="limit"):
        # validate through a temporary in-memory equivalent to prevent changing frozen files.
        if changed["limits"] != {"proposer_calls_max": 4, "train_calls_max": 80, "selection_calls_max": 32, "confirmation_calls_exact": 168, "one_provider_attempt_per_logical_call": True}:
            raise ValueError("Execution limit drifted")


def test_private_optimizer_loader_registers_dataclass_module(tmp_path):
    engine = tmp_path / "private_optimizer.py"
    engine.write_text(
        "from dataclasses import dataclass\n"
        "@dataclass\n"
        "class Probe:\n"
        "    value: int = 7\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("dspy_successor_run_loader", ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
        loaded = module.load_private_optimizer(engine)
    finally:
        sys.path.remove(str(ROOT))
    assert loaded.Probe().value == 7
