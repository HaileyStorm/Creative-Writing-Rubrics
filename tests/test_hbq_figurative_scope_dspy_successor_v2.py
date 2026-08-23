from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-scope-dspy-successor-v2"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    sys.path.insert(0, str(ROOT))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(ROOT))
    return module


def study():
    return load_module("dspy_successor_v2_study", ROOT / "study.py")


def read_contract() -> dict:
    return json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))


def test_frozen_contract_binds_parent_candidates_artifacts_and_geometry():
    s = study()
    report = s.verify_package()
    contract = read_contract()
    assert report == {
        "study_id": "hbq-figurative-scope-dspy-successor-v2",
        "status": "PENDING_EXECUTION",
        "provider_calls": 0,
        "private_bindings_finalized": True,
        "fresh_train_calls": 36,
        "selection_calls_authorized": 0,
        "confirmation_calls_authorized": 0,
    }
    assert contract["parent_v1"] == {
        "private_aggregate_sha256": "4982e2b78572276cff717dfb130dc8742fe4f790a2b6b05dac9eb5779094094c",
        "private_result_sha256": "e640103ec7e8b9bb3e2802f1af7f07eb0adf3799185513ec783e833d18fec5df",
    }
    assert contract["candidate_commitments"] == [
        {"sha256": "10e0e26ea20a33768e98abae76a343990401f673e6f0f891bfc04bfa66e39f6c", "utf8_bytes": 464},
        {"sha256": "fcd3ef7b95724f43f222061f9f2cdfcb4733348149fa517559dfcea05d1e5ab6", "utf8_bytes": 453},
    ]
    assert contract["corrected_train_artifact_sha256"] == [
        "dc6db347d6ce8a59e642d1f439b2db92547ac9577c4a2862fc4afc404e7c0a9a",
        "2b8a22e976feec16d1fe83617907d69ee73c7f8da4f73984b2618311a525bde5",
        "1a5b90e731b4bb37146b45e8badd22bf8a7a88848def8930d879970c4a501804",
    ]
    assert contract["limits"] == {
        "proposer_calls_exact": 0,
        "reused_train_rows_exact": 28,
        "fresh_train_calls_exact": 36,
        "selection_calls_if_train_passes_exact": 32,
        "confirmation_calls_exact": 0,
        "one_provider_attempt_per_logical_call": True,
    }


def test_contract_bindings_are_final_and_malformed_hashes_fail(monkeypatch):
    s = study()
    contract = read_contract()
    assert contract["bindings"] == {
        "private_engine_sha256": "db7b63dc9a1f587b28b37cc6a6215c6a466978f346c7e93e5255730dc43360e5",
        "private_freeze_inputs_sha256": "5b405a3a6546da953888224d479f0bff491bf8971a11b72a3ae2854ab6c502af",
    }
    changed = deepcopy(contract)
    changed["bindings"]["private_engine_sha256"] = "not-a-hash"
    monkeypatch.setattr(s, "load_contract", lambda: changed)
    with pytest.raises(ValueError, match="private_engine_sha256"):
        s.verify_package()


def outcome(*, train_passes: int, selection_passes: int = 0) -> dict:
    accessed = train_passes == 2
    return {
        "study_id": "hbq-figurative-scope-dspy-successor-v2",
        "status": "READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW" if accessed and selection_passes == 2 else "NO_GO",
        "calls": {"proposer": 0, "fresh_train": 36, "selection": 32 if accessed else 0, "confirmation": 0},
        "train": {"reused_rows": 28, "fresh_rows": 36, "composite_pass_candidates": train_passes},
        "selection": {"accessed": accessed, "calls": 32 if accessed else 0, "full_pass_candidates": selection_passes if accessed else 0},
        "confirmation_accessed": False,
    }


@pytest.mark.parametrize(
    ("train_passes", "selection_passes", "status"),
    [(0, 0, "NO_GO"), (1, 0, "NO_GO"), (2, 0, "NO_GO"), (2, 1, "NO_GO"), (2, 2, "READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW")],
)
def test_terminal_outcomes_enforce_conditional_selection(train_passes, selection_passes, status):
    s = study()
    value = outcome(train_passes=train_passes, selection_passes=selection_passes)
    assert value["status"] == status
    assert s.validate_public_outcome(value) == value


def test_outcome_rejects_early_selection_confirmation_and_call_drift():
    s = study()
    base = outcome(train_passes=1)
    mutations = []
    early = deepcopy(base)
    early["selection"] = {"accessed": True, "calls": 32, "full_pass_candidates": 2}
    early["calls"]["selection"] = 32
    mutations.append(early)
    confirmation = deepcopy(base)
    confirmation["confirmation_accessed"] = True
    mutations.append(confirmation)
    proposer = deepcopy(base)
    proposer["calls"]["proposer"] = 1
    mutations.append(proposer)
    short_train = deepcopy(base)
    short_train["calls"]["fresh_train"] = 35
    mutations.append(short_train)
    false_ready = deepcopy(base)
    false_ready["status"] = "READY_FOR_SEPARATE_CONFIRMATION_FREEZE_REVIEW"
    mutations.append(false_ready)
    for changed in mutations:
        with pytest.raises(ValueError):
            s.validate_public_outcome(changed)


def test_public_package_contains_no_private_material_or_runtime_dependency():
    forbidden_content = (
        "default-one-charged", "default-three-charged", "specific-three-routine",
        "Grief was thunder", "Nets breathed on pegs", "Mara's world shattered",
    )
    for path in ROOT.iterdir():
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in forbidden_content)
        assert "import dspy" not in text and "from dspy" not in text
        assert "C:\\Users\\" not in text and "C:/Users/" not in text
    contract = read_contract()
    assert set(contract["bindings"]) == {"private_engine_sha256", "private_freeze_inputs_sha256"}
    assert contract["limits"]["confirmation_calls_exact"] == 0


def test_dry_run_does_not_load_private_engine_or_call_remote():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "--dry-run"],
        text=True,
        capture_output=True,
        check=True,
    )
    value = json.loads(completed.stdout)
    assert value["mode"] == "dry_run"
    assert value["verification"]["provider_calls"] == 0
    assert value["verification"]["private_bindings_finalized"] is True


def test_remote_preflight_requires_both_flags_and_forbids_api_routes(monkeypatch, tmp_path):
    module = load_module("dspy_successor_v2_run_preflight", ROOT / "run.py")
    with pytest.raises(PermissionError):
        module.preflight_remote(allow_remote=False, owner_zero_incremental_charge=False, private_root=tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    with pytest.raises(PermissionError, match="Forbidden"):
        module.preflight_remote(allow_remote=True, owner_zero_incremental_charge=True, private_root=tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr="Logged in using ChatGPT\n"),
    )
    module.preflight_remote(allow_remote=True, owner_zero_incremental_charge=True, private_root=tmp_path)
    attestation = json.loads((tmp_path / "subscription-attestation.json").read_text(encoding="utf-8"))
    assert attestation["route"] == "codex_cli_chatgpt_subscription"


def test_private_engine_is_loaded_only_when_both_private_hashes_match(monkeypatch, tmp_path):
    module = load_module("dspy_successor_v2_run_loader", ROOT / "run.py")
    engine = tmp_path / "private_engine.py"
    freeze = tmp_path / "freeze-inputs.json"
    engine.write_text("def execute(*, public_root, private_root):\n    return {}\n", encoding="utf-8")
    freeze.write_text("{}\n", encoding="utf-8")
    contract = read_contract()
    contract["bindings"] = {
        "private_engine_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
        "private_freeze_inputs_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(module, "load_contract", lambda: contract)
    monkeypatch.setattr(module, "verify_package", lambda: {"private_bindings_finalized": True})
    loaded = module.load_bound_private_engine(tmp_path)
    assert callable(loaded.execute)
    freeze.write_text('{"drift":true}\n', encoding="utf-8")
    with pytest.raises(PermissionError, match="binding drifted"):
        module.load_bound_private_engine(tmp_path)


def test_placeholder_contract_refuses_private_engine_loading(monkeypatch, tmp_path):
    module = load_module("dspy_successor_v2_run_pending", ROOT / "run.py")
    contract = read_contract()
    contract["bindings"] = {
        "private_engine_sha256": "PENDING_PRIVATE_ENGINE_SHA256",
        "private_freeze_inputs_sha256": "PENDING_PRIVATE_FREEZE_INPUTS_SHA256",
    }
    monkeypatch.setattr(module, "load_contract", lambda: contract)
    monkeypatch.setattr(module, "verify_package", lambda: {"private_bindings_finalized": False})
    with pytest.raises(PermissionError, match="placeholders"):
        module.load_bound_private_engine(tmp_path)
