from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-grok-descriptive-sol-validation-result-v1"


def module():
    spec = importlib.util.spec_from_file_location("_v5_sol_public_result", PACKAGE / "verify.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value; spec.loader.exec_module(value)
    return value


@pytest.fixture
def live_root() -> Path:
    raw = os.environ.get("CWR_HANNA_SOL_VALIDATION_LIVE_ROOT")
    if not raw:
        pytest.skip("set CWR_HANNA_SOL_VALIDATION_LIVE_ROOT to verify the private completed root")
    return Path(raw)


def copy_publication(value, destination: Path) -> tuple[Path, Path]:
    result_path, contract_path = destination / "result.json", destination / "study-contract.json"
    for name in ("README.md", "result.json", "study-contract.json"):
        (destination / name).write_bytes((PACKAGE / name).read_bytes())
    return result_path, contract_path


def rewrite_publication(value, result_path: Path, contract_path: Path, mutate) -> None:
    result, contract = json.loads(result_path.read_text(encoding="utf-8")), json.loads(contract_path.read_text(encoding="utf-8"))
    mutate(result); internal = dict(result); internal.pop("result_internal_sha256"); result["result_internal_sha256"] = value.sha(internal)
    result_raw = value.canonical(result); result_path.write_bytes(result_raw)
    contract["result_file_sha256"] = value.sha(result_raw); contract["result_internal_sha256"] = result["result_internal_sha256"]; contract["source_execution"] = result["source_execution"]
    contract_path.write_bytes(value.canonical(contract))


def test_completed_root_rederives_the_public_data_only_projection(live_root: Path):
    result = module().verify(live_root)
    assert result == {
        "absolute_delta": -0.1347222222222222,
        "baseline_mae": 0.9236111111111112,
        "candidate_mae": 0.788888888888889,
        "cells": 4,
        "native_endpoint_contact_cardinality": "unproven",
        "relative_reduction": 0.14586466165413528,
    }


def test_public_surface_is_closed_and_excludes_raw_or_local_material():
    result = json.loads((PACKAGE / "result.json").read_text(encoding="utf-8"))
    assert set(result) == {"authority", "cell_commitments", "claim", "comparison", "evidence_ceiling", "format_version", "kind", "metrics", "publication_geometry", "result_internal_sha256", "source_execution", "study_id"}
    public = (PACKAGE / "result.json").read_text(encoding="utf-8") + (PACKAGE / "README.md").read_text(encoding="utf-8")
    for forbidden in ("C:\\", "thread_id", "session_id", "contact_id", "raw-codex", "scores", "coverage", "Leonardo DiCaprio"):
        assert forbidden not in public
    assert len({row["lifecycle_identity_sha256"] for row in result["cell_commitments"]}) == 4
    assert {path.name for path in PACKAGE.iterdir() if path.is_file()} == {"README.md", "result.json", "study-contract.json", "verify.py"}
    source = (PACKAGE / "verify.py").read_text(encoding="utf-8").lower()
    assert all(token not in source for token in ("import dspy", "import optuna", "import requests", "subprocess"))


def test_projection_rejects_missing_live_evidence_root(tmp_path: Path):
    with pytest.raises(ValueError, match="live root tree commitment"):
        module().verify(tmp_path)


def test_public_metric_rewrite_is_rejected_before_live_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module()
    path, contract_path = copy_publication(value, tmp_path)
    result = json.loads(path.read_text(encoding="utf-8")); result["metrics"][0]["equal_group_mae"] = 0.0; path.write_bytes(value.canonical(result))
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="public result commitment"):
        value.verify(tmp_path)


def test_recomputed_hashes_do_not_authorize_renamed_sensitive_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value = module(); path, contract_path = copy_publication(value, tmp_path)
    rewrite_publication(value, path, contract_path, lambda result: result["source_execution"].__setitem__("harmless_note", r"C:\private\run"))
    monkeypatch.setattr(value, "HERE", tmp_path)
    with pytest.raises(ValueError, match="sensitive material or a local path"):
        value.verify(tmp_path)
    path, contract_path = copy_publication(value, tmp_path)
    rewrite_publication(value, path, contract_path, lambda result: result["metrics"][0].__setitem__("renamed_sensitive_material", "PRIVATE_STORY_SENTINEL"))
    with pytest.raises(ValueError, match="sensitive material or a local path"):
        value.verify(tmp_path)
    path, contract_path = copy_publication(value, tmp_path)
    rewrite_publication(value, path, contract_path, lambda result: result.__setitem__("claim", r"prefix=\\server\share\private"))
    with pytest.raises(ValueError, match="sensitive material or a local path"):
        value.verify(tmp_path)
    value._reject_sensitive("ordinary prose // keeps harmless double slashes")
