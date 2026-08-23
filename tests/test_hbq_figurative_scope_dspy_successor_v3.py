from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-scope-dspy-successor-v3"


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
    return load_module("dspy_successor_v3_study", ROOT / "study.py")


def read_contract() -> dict:
    return json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))


def test_frozen_no_go_binds_v2_reconstruction_and_keeps_all_later_stages_closed():
    s = study()
    report = s.verify_package()
    contract = read_contract()
    assert report == {
        "study_id": "hbq-figurative-scope-dspy-successor-v3",
        "status": "SETTLED_NO_GO",
        "provider_calls": 0,
        "private_bindings_finalized": True,
        "selection_calls_authorized": 0,
        "confirmation_calls_authorized": 0,
    }
    assert contract["parent_v2"]["public_freeze_commit"] == "7febc77483f674a929d1778b7285a3a02c4d3a5a"
    assert contract["imported_train_miss"] == s.IMPORTED_MISS
    assert contract["imported_train_miss"]["expected_verdict"] == "YES"
    assert contract["imported_train_miss"]["observed_verdict"] == "NO"
    assert contract["gates"] == {
        "candidates_required_exact": 2,
        "affected_cells_per_candidate_exact": 6,
        "repetitions_per_affected_cell_exact": 3,
        "all_affected_cells_must_pass": True,
        "imported_miss_is_decisive": True,
    }
    assert contract["calls"] == {"new_provider_calls_exact": 0, "selection_calls_exact": 0, "confirmation_calls_exact": 0}
    assert set(contract["promotion"].values()) == {"none"}


def test_final_private_hashes_are_pinned_and_malformed_hashes_fail_closed(monkeypatch):
    s = study()
    contract = read_contract()
    changed = deepcopy(contract)
    changed["bindings"]["private_engine_sha256"] = "not-a-hash"
    monkeypatch.setattr(s, "load_contract", lambda: changed)
    with pytest.raises(ValueError, match="Final private settlement binding drifted"):
        s.verify_package()


@pytest.mark.parametrize(
    "evidence",
    [
        [{"kind": "exact_quote", "reference": "r", "exact_quote": "source phrase", "summary": None}],
        [{"kind": "summary", "reference": "r", "exact_quote": None, "summary": "source is described"}],
        [
            {"kind": "exact_quote", "reference": "r1", "exact_quote": "source phrase", "summary": None},
            {"kind": "summary", "reference": "r2", "exact_quote": None, "summary": "source is described"},
        ],
    ],
)
def test_production_compatible_typed_evidence_accepts_exact_summary_and_mixed(evidence):
    study().validate_typed_evidence(evidence, "prefix source phrase suffix")


@pytest.mark.parametrize(
    "evidence",
    [
        [{"kind": "exact_quote", "reference": "r", "exact_quote": "not in source", "summary": None}],
        [{"kind": "summary", "reference": "r", "exact_quote": "not null", "summary": "summary"}],
        [{"kind": "exact_quote", "reference": " ", "exact_quote": "source phrase", "summary": None}],
        [{"kind": "unknown", "reference": "r", "exact_quote": None, "summary": "summary"}],
    ],
)
def test_typed_evidence_rejects_ungrounded_and_malformed_records(evidence):
    with pytest.raises(ValueError):
        study().validate_typed_evidence(evidence, "prefix source phrase suffix")


def test_dry_run_is_provider_free_and_reports_final_hashes():
    completed = subprocess.run([sys.executable, str(ROOT / "run.py"), "--dry-run"], text=True, capture_output=True, check=True)
    value = json.loads(completed.stdout)
    assert value["mode"] == "dry_run"
    assert value["verification"]["provider_calls"] == 0
    assert value["verification"]["private_bindings_finalized"] is True
    module = load_module("dspy_successor_v3_run_pending", ROOT / "run.py")
    with pytest.raises(FileNotFoundError, match="inputs are unavailable"):
        module.load_bound_private_engine(Path("missing-private-root"))


def test_public_result_is_settled_aggregate_only_no_go_with_pinned_lineage():
    s = study()
    result = s.verify_public_result()
    assert result["status"] == "NO_GO"
    assert result["new_calls"] == 0
    assert result["selection"] == {"accessed": False, "read": False}
    assert result["confirmation_accessed"] is False
    assert result["private_lineage"]["v2"] == s.FINAL_PARENT
    assert result["private_lineage"]["v3"] == {
        "private_aggregate_sha256": "bfb361e7bcd0dd0544181b9c366c5dee8c920e6175ae8b6779d79bb9ea4f077c",
        "private_result_sha256": "b67552012234580d5f89003d5d7640d138e380faee6daca3e62820602bbbc077",
    }


def test_public_result_mutation_fails_closed(monkeypatch):
    s = study()
    result = s.load_public_result()
    result["selection"]["read"] = True
    monkeypatch.setattr(s, "load_public_result", lambda: result)
    with pytest.raises(ValueError, match="Public no-go settlement drifted"):
        s.verify_public_result()


def test_settlement_loads_only_hash_bound_private_engine(monkeypatch, tmp_path):
    module = load_module("dspy_successor_v3_run_loader", ROOT / "run.py")
    engine = tmp_path / "private_engine.py"
    freeze = tmp_path / "freeze-inputs.json"
    engine.write_text(
        "def execute(*, public_root, private_root):\n"
        "    return {'study_id': 'hbq-figurative-scope-dspy-successor-v3', 'status': 'NO_GO', "
        "'new_calls': 0, 'train': {'both_candidates_must_pass': True, "
        "'c1_required_cell_repetitions': 3, 'c1_maximum_possible_correct_repetitions': 2, "
        "'decisive_prior_accepted_misses': 1}, 'selection': {'accessed': False, 'read': False}, "
        "'confirmation_accessed': False, 'decision': 'NO_PROMOTION'}\n",
        encoding="utf-8",
    )
    freeze.write_text("{}\n", encoding="utf-8")
    contract = read_contract()
    contract["parent_v2"]["private_aggregate_sha256"] = "a" * 64
    contract["parent_v2"]["private_result_sha256"] = "b" * 64
    contract["bindings"] = {
        "private_engine_sha256": hashlib.sha256(engine.read_bytes()).hexdigest(),
        "private_freeze_inputs_sha256": hashlib.sha256(freeze.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(module, "load_contract", lambda: contract)
    loaded = module.load_bound_private_engine(tmp_path)
    assert module.validate_public_outcome(loaded.execute(public_root=ROOT, private_root=tmp_path))["status"] == "NO_GO"
    freeze.write_text('{"drift":true}\n', encoding="utf-8")
    with pytest.raises(PermissionError, match="binding drifted"):
        module.load_bound_private_engine(tmp_path)


def test_public_package_excludes_private_and_sensitive_content():
    forbidden = ("default-one-charged", "default-three-charged", "specific-three-routine", "C:\\Users\\", "C:/Users/", "session_id", "raw_response")
    for path in ROOT.iterdir():
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        assert all(fragment not in text for fragment in forbidden)
        assert "import dspy" not in text and "from dspy" not in text
    assert "--execute" not in (ROOT / "run.py").read_text(encoding="utf-8")
