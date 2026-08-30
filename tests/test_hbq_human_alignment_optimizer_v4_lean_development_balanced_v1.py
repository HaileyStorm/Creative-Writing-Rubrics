from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1"
optimizer = load_module(PACKAGE / "optimizer.py", name="hanna_v4_lean_development_balanced_v1")


def _projection(tmp_path: Path) -> tuple[Path, dict]:
    candidates = [f"candidate-{index}" for index in range(5)]
    observations = []
    for route_name, groups in (("grok_primary", range(4)), ("sol_validation", range(2))):
        for group in groups:
            for index, candidate_id in enumerate(candidates):
                observations.append({
                    "cell_id": f"{route_name}-{group}-{index}", "route_name": route_name,
                    "item_id": f"item-{route_name}-{group}", "prompt_group_id": f"group-{route_name}-{group}",
                    "candidate_id": candidate_id, "scores": {"Relevance": float(index + group)},
                    "coverage": {"Relevance": True}, "request_bytes": 100 + index,
                    "identity": {"provider": route_name, "contact_id": f"contact-{route_name}-{group}-{index}", "session_id": f"session-{route_name}-{group}-{index}"},
                })
    targets = {row["item_id"]: {"Relevance": 1.0} for row in observations}
    value = {
        "format_version": 1, "study_id": "hbq-human-alignment-optimizer-v4-lean-training-balanced-v1",
        "kind": "balanced_lean_training_optimizer_observation_projection", "balanced_collection_evidence_sha256": "a" * 64,
        "dependencies": {"balanced_verifier_source_sha256": optimizer.BALANCED_SHA256, "balanced_contract_sha256": optimizer.BALANCED_CONTRACT_SHA256}, "schedule_sha256": "b" * 64,
        "stage": "training", "observations": observations, "human_targets": targets,
        "geometry": {"grok_prompt_groups": 4, "grok_candidates_per_group": 5, "grok_cells": 20, "sol_cells": 10, "total_cells": 30},
        "excluded_terminal": {"cell_id": "terminal", "prompt_group_id": "failed", "grok_cells": 5, "inventory_sha256": "c" * 64, "result_sha256": "d" * 64},
        "confirmation": {"status": "unopened", "cells": 0}, "provider_calls_made": 0, "runtime_authority": "none",
    }
    value["projection_sha256"] = optimizer.sha256(value)
    path = tmp_path / "projection.json"
    path.write_bytes(optimizer.canonical(value))
    return path, value


def _dependencies(replayed: dict):
    def endpoint(rows, _targets, *, expected_items, expected_groups):
        assert len({row["item_id"] for row in rows}) == expected_items
        assert len({row["prompt_group_id"] for row in rows}) == expected_groups
        index = int(rows[0]["candidate_id"].rsplit("-", 1)[1])
        route = rows[0]["route_name"]
        error = (5 - index) if route == "grok_primary" else (5 - index) / 10
        return {"macro_spearman": None, "mean_absolute_error": error, "mean_coverage": 1.0 - index / 20}
    instruction, profile = b"parent", b'{"parent":true}'
    parent = {"candidate_id": "candidate-4", "candidate_sha256": "e" * 64, "instruction_bytes": instruction, "profile_bytes": profile, "instruction_sha256": optimizer.sha256_bytes(instruction), "profile_sha256": optimizer.sha256_bytes(profile)}
    native = SimpleNamespace(_load_v3=lambda: SimpleNamespace(v2_module=lambda: SimpleNamespace(_candidate_endpoint=endpoint), candidate_pack=lambda: [parent]))
    def verify(**kwargs):
        assert set(kwargs) == {"collection_evidence_path", "frozen_successor_path", "hanna_csv_path"}
        return replayed
    return lambda: (SimpleNamespace(verify_balanced_training_receipts=verify), object(), native)


def _inputs(tmp_path: Path, projection: Path) -> dict:
    return {
        "balanced_projection_path": projection,
        "balanced_collection_evidence_path": tmp_path / "balanced-collection.json",
        "frozen_successor_path": tmp_path / "frozen.json",
        "hanna_csv_path": tmp_path / "hanna.csv",
    }


def test_real_optuna_recomputes_balanced_geometry_and_freezes_no_substitution(monkeypatch, tmp_path: Path):
    projection, replayed = _projection(tmp_path)
    monkeypatch.setattr(optimizer, "_dependencies", _dependencies(replayed))
    inputs = _inputs(tmp_path, projection)
    result = optimizer.optimize_balanced_projection(**inputs, seed=7)
    assert result["optimizer"] == "optuna.GridSampler@4.9.0"
    assert result["frozen_candidate_id"] == "candidate-4"
    assert result["geometry"] == {"grok_prompt_groups": 4, "grok_candidates_per_group": 5, "grok_cells": 20, "sol_cells": 10, "total_cells": 30}
    assert result["candidate_substitution"] == "forbidden"
    assert result["confirmation"] == {"status": "unopened", "cells": 0}
    assert result["runtime_authority"] == "none" and result["provider_calls_made"] == 0
    expected_dependencies = {
        "balanced_optimizer_source_sha256": optimizer.sha256_bytes(optimizer._stable_bytes(Path(optimizer.__file__))),
        "balanced_optimizer_contract_sha256": optimizer.sha256_bytes(optimizer._stable_bytes(optimizer.CONTRACT_PATH)),
        "balanced_verifier_sha256": optimizer.BALANCED_SHA256,
        "balanced_verifier_contract_sha256": optimizer.BALANCED_CONTRACT_SHA256,
        "lean_development_optimizer_sha256": optimizer.DEVELOPMENT_SHA256,
    }
    assert result["dependencies"] == expected_dependencies
    context = optimizer.training_diagnostics(**inputs, seed=7)
    assert context["training_diagnostics"]["training_result_sha256"] == result["result_sha256"]
    assert context["training_diagnostics"]["dependencies"] == expected_dependencies
    assert context["training_diagnostics"]["training_result_dependencies_sha256"] == optimizer.sha256(expected_dependencies)
    persisted = optimizer.canonical(context["training_diagnostics"])
    assert optimizer.canonical(json.loads(persisted.decode("utf-8"))) == persisted
    assert set(context["training_diagnostics"]["parent"]) == {"candidate_id", "candidate_sha256", "instruction_base64", "instruction_sha256", "profile_base64", "profile_sha256"}
    assert "instruction_bytes" not in context["training_diagnostics"]["parent"]


def test_rejects_fabricated_projection_even_when_its_hash_is_recomputed(monkeypatch, tmp_path: Path):
    projection, replayed = _projection(tmp_path)
    monkeypatch.setattr(optimizer, "_dependencies", _dependencies(replayed))
    value = json.loads(projection.read_text(encoding="utf-8"))
    value["geometry"]["grok_cells"] = 25
    value["projection_sha256"] = optimizer.sha256({key: item for key, item in value.items() if key != "projection_sha256"})
    projection.write_bytes(optimizer.canonical(value))
    try:
        optimizer.optimize_balanced_projection(**_inputs(tmp_path, projection))
    except ValueError as error:
        assert "byte-identical" in str(error)
    else:
        raise AssertionError("fabricated balanced projection was accepted")


def test_real_dspy_preparation_returns_canonical_inputs_without_a_forward_path(monkeypatch, tmp_path: Path):
    projection, replayed = _projection(tmp_path)
    monkeypatch.setattr(optimizer, "_dependencies", _dependencies(replayed))
    prepared = optimizer.prepare_dspy_descendant_inputs(**_inputs(tmp_path, projection), seed=11)
    assert prepared["dspy_program"] == "Predict(BalancedDescendantSignature)@3.3.1"
    assert prepared["provider_calls_made"] == 0
    assert prepared["dispatch_authority"] == "none_governed_executor_required"
    assert prepared["runtime_authority"] == "none"
    assert prepared["confirmation"] == {"status": "unopened", "cells": 0}
    assert prepared["dependencies"] == optimizer._output_dependencies()
    assert set(prepared["inputs"]) == {"parent_candidate_id", "parent_instruction_base64", "parent_profile_base64", "training_result_base64", "training_diagnostics_base64"}
    assert json.loads(base64.b64decode(prepared["inputs"]["training_result_base64"]))["study_id"] == optimizer.STUDY_ID
    assert optimizer.canonical(json.loads(optimizer.canonical(prepared).decode("utf-8"))) == optimizer.canonical(prepared)
    assert not hasattr(optimizer, "build_dspy_descendant_program")


def test_contract_rejects_authority_mutation(monkeypatch, tmp_path: Path):
    value = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    value["authority"]["runtime"] = True
    mutated = tmp_path / "mutated-contract.json"
    mutated.write_bytes(optimizer.canonical(value))
    monkeypatch.setattr(optimizer, "CONTRACT_PATH", mutated)
    try:
        optimizer.contract()
    except ValueError as error:
        assert "fields or authority" in str(error)
    else:
        raise AssertionError("mutated runtime authority was accepted")


def test_public_result_binds_retained_subset_metrics_limits_and_commitments():
    public_result_path = PACKAGE / "public-result.json"
    raw = public_result_path.read_text(encoding="utf-8")
    result = json.loads(raw)

    assert set(result) == {
        "format_version",
        "study_id",
        "status",
        "privacy",
        "geometry",
        "excluded_grok_group",
        "optimizer",
        "limits",
        "next_step",
        "provenance",
    }
    assert result["status"] == "DEVELOPMENT_ONLY_NO_PROMOTION"
    assert result["privacy"] == "aggregate_only_no_private_content_or_local_paths"
    assert set(result["geometry"]) == {
        "grok_retained_cells",
        "grok_retained_complete_prompt_groups",
        "sol_sprinkled_cells",
        "total_retained_cells",
    }
    assert result["geometry"] == {
        "grok_retained_cells": 20,
        "grok_retained_complete_prompt_groups": 4,
        "sol_sprinkled_cells": 10,
        "total_retained_cells": 30,
    }
    assert set(result["excluded_grok_group"]) == {
        "cells",
        "prompt_groups",
        "reason",
        "terminal_cell_id",
        "terminal_inventory_sha256",
        "terminal_result_sha256",
    }
    assert result["excluded_grok_group"] == {
        "cells": 5,
        "prompt_groups": 1,
        "reason": "immutable_terminal_no_resend",
        "terminal_cell_id": "v4-cell-327fe788866eb61b",
        "terminal_inventory_sha256": "48f1f9b8ca0aaa4289bbeb185629e5403d7d736d486ff31c973d26467c68ac66",
        "terminal_result_sha256": "ae47330428b9cb459d5dee6f8225406fa7712b237101415a54c38baf3237ceb8",
    }
    assert set(result["optimizer"]) == {
        "implementation",
        "objective",
        "selected_existing_baseline_candidate_id",
        "objective_value",
        "grok_mean_absolute_error",
        "sol_sprinkled_mean_absolute_error",
        "grok_mean_coverage",
        "scope",
        "current_candidate_improvement_over_baseline_within_retained_subset",
        "selection_uses_spearman",
        "undefined_spearman_imputed",
    }
    assert result["optimizer"] == {
        "implementation": "optuna.GridSampler@4.9.0",
        "objective": "0.8_grok_mae_plus_0.2_sol_mae_plus_additive_coverage_penalty_1e-6_plus_additive_request_byte_penalty_1e-12",
        "selected_existing_baseline_candidate_id": "candidate-52d1be4bc34e0018",
        "objective_value": 1.5722222267539725,
        "grok_mean_absolute_error": 1.638888888888889,
        "sol_sprinkled_mean_absolute_error": 1.3055555555555556,
        "grok_mean_coverage": 1.0,
        "scope": "retained_balanced_subset_only",
        "current_candidate_improvement_over_baseline_within_retained_subset": False,
        "selection_uses_spearman": False,
        "undefined_spearman_imputed": False,
    }
    assert set(result["limits"]) == {
        "confirmation",
        "grok_reasoning",
        "sol_native_endpoint_contact_cardinality",
        "dspy",
        "descendant_gain_claim",
    }
    assert result["limits"] == {
        "confirmation": "unopened",
        "grok_reasoning": "requested_high_unattested",
        "sol_native_endpoint_contact_cardinality": "unproven_local_lifecycle_only",
        "dspy": "3.3.1_exact_inputs_prepared_no_dispatch",
        "descendant_gain_claim": "not_established",
    }
    assert set(result["provenance"]) == {
        "balanced_optimizer_source_sha256",
        "balanced_optimizer_contract_sha256",
        "balanced_result_internal_sha256",
        "balanced_result_canonical_bytes_sha256",
        "balanced_projection_internal_sha256",
    }
    assert result["provenance"] == {
        "balanced_optimizer_source_sha256": "8355382a5e9e48b020607306412613b6217a14b7aa253596635d2186192fe4e1",
        "balanced_optimizer_contract_sha256": "c32b563822c6ffe0c48647cb49c1a32f9825b7ee4c64e1a967b3bedc2a8098ec",
        "balanced_result_internal_sha256": "9b6a51779cc525267e7b2217ee65ee31535370bb8ff0afed11d8e3d99dbb2f42",
        "balanced_result_canonical_bytes_sha256": "6d3d55bcf82b55be2b831d5ca39409d8ef87a2d5cba747a471dc3c232aa3b500",
        "balanced_projection_internal_sha256": "9e7b8a084ad6cb746a929398168d24f11df50381b81ff18044a05ffb09aef2b3",
    }
    assert result["provenance"]["balanced_optimizer_source_sha256"] == hashlib.sha256(
        (PACKAGE / "optimizer.py").read_bytes()
    ).hexdigest()
    assert result["provenance"]["balanced_optimizer_contract_sha256"] == hashlib.sha256(
        (PACKAGE / "study-contract.json").read_bytes()
    ).hexdigest()
    assert "C:\\Users\\" not in raw
