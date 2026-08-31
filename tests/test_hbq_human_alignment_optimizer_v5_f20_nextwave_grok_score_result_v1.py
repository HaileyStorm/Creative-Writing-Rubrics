from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-result-v1"


def module():
    spec = importlib.util.spec_from_file_location("_v5_nextwave_grok_public_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def copy_publication(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("README.md", "result.json", "study-contract.json", "verify.py"):
        (destination / name).write_bytes((PACKAGE / name).read_bytes())


def refresh_internal_bindings(value, root: Path, result: dict, contract: dict) -> None:
    internal = dict(result)
    internal.pop("result_internal_sha256")
    result["result_internal_sha256"] = value.sha(internal)
    result_raw = value.canonical(result)
    (root / "result.json").write_bytes(result_raw)
    contract["result_internal_sha256"] = result["result_internal_sha256"]
    contract["source_execution"] = result["source_execution"]
    contract["publication_manifest"]["bound_files"] = {
        "README.md": value.sha((root / "README.md").read_bytes()),
        "result.json": value.sha(result_raw),
        "verify.py": value.sha((root / "verify.py").read_bytes()),
    }
    contract_internal = dict(contract)
    contract_internal.pop("contract_internal_sha256")
    contract["contract_internal_sha256"] = value.sha(contract_internal)
    (root / "study-contract.json").write_bytes(value.canonical(contract))


@pytest.fixture
def replay_paths() -> dict[str, Path]:
    names = {
        "output_root": "CWR_HANNA_NEXTWAVE_SCORE_OUTPUT_ROOT",
        "collector": "CWR_HANNA_NEXTWAVE_SCORE_COLLECTOR",
        "materialization_root": "CWR_HANNA_MATERIALIZATION_ROOT",
        "frozen_successor": "CWR_HANNA_FROZEN_SUCCESSOR",
        "hanna_csv": "CWR_HANNA_CSV",
    }
    supplied = {key: os.environ.get(name) for key, name in names.items()}
    if not all(supplied.values()):
        pytest.skip("set all five CWR_HANNA_* source variables to replay the private 33-cell evidence")
    return {key: Path(value) for key, value in supplied.items() if value is not None}


def test_public_result_is_exact_closed_data_only_and_internally_bound():
    value = module()
    result = value.validate_publication()
    comparison = value._derive_comparison(result["metrics"])
    assert len(result["metrics"]) == 11
    assert sum(row["cells"] for row in result["metrics"]) == 33
    assert comparison == {
        "absolute_delta": -0.17592592592592593,
        "baseline_candidate_id": "candidate-102cc7f06c9a99a7",
        "baseline_equal_group_mae": 0.9259259259259259,
        "lowest_observed_candidate_id": "normalized-nextwave-08-conservative-hybrid",
        "lowest_observed_equal_group_mae": 0.75,
        "relative_reduction": 0.19,
    }
    assert result["authority"] == {
        "confirmation": "unopened",
        "endpoint_pooling": "forbidden",
        "general_hanna": "none",
        "promotion": "none",
        "runtime": "none",
        "selection": "none",
        "sol_validation": "none",
    }
    public_data = "\n".join(
        (PACKAGE / name).read_text(encoding="utf-8")
        for name in ("README.md", "result.json", "study-contract.json")
    )
    for forbidden in (
        "C:\\Users\\",
        "\\\\server\\share",
        "session_id",
        "request_id",
        "story_text",
        "native_response_base64",
        "PRIVATE_STORY_SENTINEL",
    ):
        assert forbidden not in public_data
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert all(token not in source for token in ("import dspy", "import optuna", "import requests", "subprocess"))


def test_completed_source_portably_replays_all_33_cells_without_provider_calls(replay_paths: dict[str, Path]):
    replayed = module().replay(**replay_paths)
    assert replayed == {
        "absolute_delta": -0.17592592592592593,
        "baseline_candidate_id": "candidate-102cc7f06c9a99a7",
        "baseline_equal_group_mae": 0.9259259259259259,
        "cells": 33,
        "lowest_observed_candidate_id": "normalized-nextwave-08-conservative-hybrid",
        "lowest_observed_equal_group_mae": 0.75,
        "native_endpoint_contact_cardinality": "unproven",
        "provider_calls_made": 0,
        "relative_reduction": 0.19,
    }


def test_extra_file_readme_verify_and_contract_mutations_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    extra = tmp_path / "extra"
    copy_publication(extra)
    (extra / "raw-output.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(value, "HERE", extra)
    with pytest.raises(ValueError, match="inventory"):
        value.validate_publication()

    readme = tmp_path / "readme"
    copy_publication(readme)
    (readme / "README.md").write_text("mutated", encoding="utf-8")
    monkeypatch.setattr(value, "HERE", readme)
    with pytest.raises(ValueError, match="README.md"):
        value.validate_publication()

    verifier = tmp_path / "verifier"
    copy_publication(verifier)
    (verifier / "verify.py").write_text("# mutated\n", encoding="utf-8")
    monkeypatch.setattr(value, "HERE", verifier)
    with pytest.raises(ValueError, match="verify.py"):
        value.validate_publication()

    contract_root = tmp_path / "contract"
    copy_publication(contract_root)
    contract = json.loads((contract_root / "study-contract.json").read_text(encoding="utf-8"))
    contract["geometry"]["cells"] = 32
    (contract_root / "study-contract.json").write_bytes(value.canonical(contract))
    monkeypatch.setattr(value, "HERE", contract_root)
    with pytest.raises(ValueError, match="contract internal commitment"):
        value.validate_publication()


def test_semantically_identical_noncanonical_contract_bytes_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    value = module()
    copy_publication(tmp_path)
    contract_path = tmp_path / "study-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    reformatted = (json.dumps(contract, ensure_ascii=False, indent=2) + "\n").encode()
    assert reformatted != value.canonical(contract)
    contract_path.write_bytes(reformatted)
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="contract is not canonical"):
        value.validate_publication()


@pytest.mark.parametrize("leak", [r"C:\private\run", "PRIVATE_STORY_SENTINEL"])
def test_rebound_private_readme_is_rejected_after_digest_and_self_commit_recomputation(
    leak: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    value = module()
    copy_publication(tmp_path)
    readme_path = tmp_path / "README.md"
    readme_path.write_text(readme_path.read_text(encoding="utf-8") + "\n" + leak + "\n", encoding="utf-8")
    contract_path = tmp_path / "study-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["publication_manifest"]["bound_files"]["README.md"] = value.sha(readme_path.read_bytes())
    internal = dict(contract)
    internal.pop("contract_internal_sha256")
    contract["contract_internal_sha256"] = value.sha(internal)
    contract_path.write_bytes(value.canonical(contract))
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="sensitive material or a local path"):
        value.validate_publication()


def test_recomputed_metric_tamper_cannot_preserve_stale_comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    copy_publication(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    contract = json.loads((tmp_path / "study-contract.json").read_text(encoding="utf-8"))
    row = result["metrics"][0]
    first_group = next(iter(row["group_mae"]))
    row["group_mae"][first_group] += 0.3
    row["equal_group_mae"] += 0.1
    refresh_internal_bindings(value, tmp_path, result, contract)
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="comparison is not derived"):
        value.validate_publication()


def test_recomputed_comparison_tamper_is_rejected_against_metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    copy_publication(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    contract = json.loads((tmp_path / "study-contract.json").read_text(encoding="utf-8"))
    result["comparison"]["relative_reduction"] = 0.99
    contract["comparison"] = result["comparison"]
    refresh_internal_bindings(value, tmp_path, result, contract)
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="comparison is not derived"):
        value.validate_publication()


def test_recomputed_bindings_cannot_hide_local_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    copy_publication(tmp_path)
    result = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    contract = json.loads((tmp_path / "study-contract.json").read_text(encoding="utf-8"))
    result["evidence_ceiling"] = r"prefix C:\private\run"
    contract["evidence_ceiling"] = result["evidence_ceiling"]
    refresh_internal_bindings(value, tmp_path, result, contract)
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="sensitive material or a local path"):
        value.validate_publication()


def test_nonfinite_in_memory_metric_reaches_semantic_finite_gate():
    value = module()
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    result["metrics"][0]["equal_group_mae"] = math.nan
    with pytest.raises(ValueError, match="not finite numeric data"):
        value._derive_comparison(result["metrics"])
