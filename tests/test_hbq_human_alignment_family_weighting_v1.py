from __future__ import annotations

import ast
import copy
import importlib.util
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluation-results" / "hbq-human-alignment-family-weighting-v1" / "study.py"
ADAPTER = SOURCE.with_name("source_adapter.py")
SPLIT = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\split-manifest.json")
FREEZE = Path(r"C:\Users\Haile\Documents\cwr-hanna-optimizer-grok-primary-dev-20260829-d189d71\execution-freeze.json")
FRESH88 = Path(r"C:\Users\Haile\Documents\cwr-hanna-fresh88-sol-v1-20260821-w4\fresh88-execution-contract.json")
RUNS = Path(r"C:\Users\Haile\Documents\cwr-hanna-fresh88-sol-v1-20260821-w4-repair1-artifacts")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")


def module():
    if not SOURCE.is_file():
        pytest.skip("family-weighting source is unavailable")
    spec = importlib.util.spec_from_file_location("family_weighting_v1", SOURCE)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def adapter_module():
    spec = importlib.util.spec_from_file_location("family_weighting_adapter_v1", ADAPTER)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def records():
    return [
        {
            "item_id": f"item-{group:02d}-{index}",
            "prompt_group_id": f"group-{group:02d}",
            "original_final_score": 50.0,
            "all_one_final_score": 50.0,
            "target_scalar": 3.0,
            "human_overall_proxy": 1.0 + (group + index) % 5,
            "scores": {"Relevance": 0.5},
        }
        for group in range(24)
        for index in range(2)
    ]


def source_paths(output_root: Path):
    return {
        "split_manifest": SPLIT,
        "execution_freeze": FREEZE,
        "fresh88_contract": FRESH88,
        "raw_runs_root": RUNS,
        "hanna_csv": CSV,
        "output_root": output_root,
    }


def test_all_one_parity_requires_exact_train48_loo_geometry_before_fit(tmp_path: Path):
    value = module()
    valid = records()
    assert value.verify_all_one(valid) == {"state": "all_one_parity_pass", "mismatch_count": 0, "mismatched_item_ids": []}
    result = value._run_records(records=valid, allow_fit=False, rescore=None)
    assert result["state"] == "non_empirical_synthetic_parity_verified_fit_not_requested"
    assert result["parity"]["state"] == "all_one_parity_pass"

    changed = [dict(row) for row in valid]
    changed[0]["all_one_final_score"] = 49.0
    assert value.verify_all_one(changed) == {"state": "all_one_parity_failed", "mismatch_count": 1, "mismatched_item_ids": [changed[0]["item_id"]]}
    with pytest.raises(ValueError, match="parity must pass"):
        value._run_records(records=changed, allow_fit=True, rescore=lambda _: {})
    with pytest.raises(ValueError, match="exact TRAIN48/24"):
        value.verify_all_one(valid[:-1])


def test_contract_keeps_fit_development_only_and_defers_optimizer_import():
    value = module()
    contract = value.contract()
    assert contract["geometry"] == {"families": ["core", "craft", "form"], "groups": 24, "items": 48, "leave_one_group_out_folds": 24}
    assert contract["fit"]["parameter_bounds"] == {"core": [0.5, 2.0], "craft": [0.5, 2.0], "form": [0.5, 2.0]}
    assert contract["fit"]["optuna"] == {"n_jobs": 1, "seed": 20260904, "trials_per_leave_one_group_out": 128, "version": "4.9.0"}
    assert contract["authority"] == {"confirmation": "none", "development_train_only": True, "model_prior": "none", "promotion": "none", "runtime": "none", "selection": "none"}
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    top_level_imports = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    all_imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "optuna" not in top_level_imports and "dspy" not in all_imports
    assert "optuna" in all_imports


def test_tie_ranks_are_average_and_constant_correlations_remain_undefined():
    value = module()
    assert value._rank([1.0, 1.0, 3.0]) == [1.5, 1.5, 3.0]
    assert value._spearman([3.0, 3.0], [1.0, 5.0]) is None
    assert value._spearman([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_singleton_group_context_is_undefined_not_a_rank_error():
    value = module()
    row = records()[0]
    assert value._group_objective([row], {row["item_id"]: 50.0}) is None


def test_preflight_and_fake_optuna_fit_keep_all_families_positive_and_loo(monkeypatch: pytest.MonkeyPatch):
    value, adapter = module(), adapter_module()
    rows = records()
    with pytest.raises(ValueError, match="complete core/craft/form"):
        adapter.rescore(rows, {"core": 1.0, "craft": 1.0})
    with pytest.raises(ValueError, match="finite positive"):
        adapter.rescore(rows, {"core": 1.0, "craft": 1.0, "form": 0.0})

    def rescore(multipliers):
        assert set(multipliers) == set(value.FAMILIES)
        assert all(isinstance(weight, float) and weight > 0 for weight in multipliers.values())
        return {
            row["item_id"]: 20.0 + index + 4.0 * multipliers["core"] + 3.0 * multipliers["craft"] + (index % 2) * multipliers["form"]
            for index, row in enumerate(rows)
        }

    preflight = value.preflight(rows, rescore)
    assert preflight["state"] == "identifiable"
    assert preflight["active_families"] == list(value.FAMILIES)
    assert all(count > 0 for family in value.FAMILIES for count in preflight["family_influence"][family].values())

    calls = []

    class Trial:
        def suggest_float(self, name, low, high):
            assert name in value.FAMILIES and (low, high) == (0.5, 2.0)
            return {"core": 1.1, "craft": 0.9, "form": 1.5}[name]

    class Study:
        best_params = {"core": 1.1, "craft": 0.9, "form": 1.5}
        best_value = 0.5

        def enqueue_trial(self, parameters):
            assert parameters == {family: 1.0 for family in value.FAMILIES}

        def optimize(self, objective, *, n_trials, n_jobs):
            calls.append((n_trials, n_jobs))
            assert isinstance(objective(Trial()), float)

    class Sampler:
        def __init__(self, *, seed):
            self.seed = seed

    fake_optuna = SimpleNamespace(__version__="4.9.0", samplers=SimpleNamespace(TPESampler=Sampler), create_study=lambda *, direction, sampler: Study())
    monkeypatch.setitem(sys.modules, "optuna", fake_optuna)
    fitted = value.fit(rows, rescore)
    assert calls == [(128, 1)] * 24
    assert len(fitted["oof_scores"]) == 48
    assert set(fitted) == {"preflight", "oof_scores", "folds", "pooled_oof_spearman", "within_group_defined_context"}
    assert len(fitted["folds"]) == 24
    assert all(fold["trials"] == 128 and len(fold["heldout_item_ids"]) == 2 and set(fold["multipliers"]) == set(value.FAMILIES) for fold in fitted["folds"])


def test_authoritative_source_bound_reconstruction_is_pinned_and_private_helpers_stay_nonempirical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    value, adapter = module(), adapter_module()
    assert set(inspect.signature(value.run_from_sources).parameters) == {"split_manifest", "execution_freeze", "fresh88_contract", "raw_runs_root", "hanna_csv", "output_root", "allow_fit"}
    captured = {}

    def build(**kwargs):
        records = adapter.build_records(**kwargs)
        captured["records"] = records
        return records

    wrapped = SimpleNamespace(build_records=build, verify_all_one=adapter.verify_all_one, rescore=adapter.rescore)
    monkeypatch.setattr(value, "_adapter", lambda: wrapped)
    preexisting_hbqrs = {name: imported for name, imported in sys.modules.items() if name == "hbqrs" or name.startswith("hbqrs.")}
    preexisting_sys_path = list(sys.path)
    for name in preexisting_hbqrs:
        sys.modules.pop(name)
    try:
        receipt = value.run_from_sources(**source_paths(tmp_path / "authoritative"), allow_fit=False)
        rows = captured["records"]
        assert len(rows) == len({row["item_id"] for row in rows}) == 48
        assert len({row["prompt_group_id"] for row in rows}) == 24
        assert receipt["state"] == "source_bound_parity_verified_fit_not_requested"
        assert receipt["parity"] == {"state": "all_one_parity_pass", "mismatch_count": 0, "mismatched_item_ids": []}
        assert receipt["records_commitment_sha256"] == value._records_commitment(rows)
        expected_bindings = {
            "split_manifest": value.sha256(SPLIT.read_bytes()),
            "execution_freeze": value.sha256(FREEZE.read_bytes()),
            "fresh88_contract": value.sha256(FRESH88.read_bytes()),
            "hanna_csv": value.sha256(CSV.read_bytes()),
            "adapter_sha256": value.ADAPTER_SHA256,
            "study_sha256": value.sha256(SOURCE.read_bytes()),
            "contract_sha256": value.sha256(value.CONTRACT.read_bytes()),
        }
        assert receipt["source_bindings"] == expected_bindings
        assert all(len(row["scoring"]["compiled_question_ids"]) == 179 and len(set(row["scoring"]["compiled_question_ids"])) == 179 for row in rows)
        assert all(set(row["commitments"]["source"]) == {"story_sha256", "prompt_sha256", "task_contract_sha256"} and row["commitments"]["native"] for row in rows)
        assert adapter.verify_all_one(rows) == receipt["parity"]
        all_one = adapter.rescore(rows, {family: 1.0 for family in value.FAMILIES})
        changed = adapter.rescore(rows, {"core": 1.0, "craft": 1.0, "form": 1.5})
        assert all_one == {row["item_id"]: row["original_final_score"] for row in rows}
        assert set(changed) == set(all_one) and any(changed[item_id] != all_one[item_id] for item_id in all_one)

        mutated = copy.deepcopy(rows)
        mutated[0]["commitments"]["native"] = {"tampered": True}
        assert value._records_commitment(mutated) != receipt["records_commitment_sha256"]
        private = value._run_records(records=rows, allow_fit=False, rescore=None)
        assert private["state"] == "non_empirical_synthetic_parity_verified_fit_not_requested" and "source_bindings" not in private
        with pytest.raises(TypeError):
            value.run_from_sources(**source_paths(tmp_path / "type-error"), allow_fit=False, records=rows)
        tampered_split = tmp_path / "tampered-split.json"
        tampered_split.write_bytes(SPLIT.read_bytes() + b" ")
        tampered = source_paths(tmp_path / "tampered")
        tampered["split_manifest"] = tampered_split
        with pytest.raises(ValueError, match="split manifest SHA-256 pin drifted"):
            value.run_from_sources(**tampered, allow_fit=False)
    finally:
        for name in [name for name in sys.modules if name == "hbqrs" or name.startswith("hbqrs.")]:
            sys.modules.pop(name)
        sys.modules.update(preexisting_hbqrs)
        sys.path[:] = preexisting_sys_path
