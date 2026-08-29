from __future__ import annotations

import inspect
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from _scoped_module_loader import load_module


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v3"
DOCUMENTS = Path.home() / "Documents"
ROOTS = {
    "frozen_successor_path": DOCUMENTS / "cwr-hanna-successor-fresh88-freeze-v4" / "frozen-successor-contract.json",
    "hanna_csv_path": DOCUMENTS / "cwr-hanna-pinned-data-282f275" / "hanna_stories_annotations.csv",
}
study = load_module(PACKAGE / "study.py", name="hanna_optimizer_study_v3")


@pytest.fixture(scope="module")
def schedule() -> dict:
    return study.derive_schedule(**ROOTS)


def _candidates() -> list[dict]:
    _parent_study, harness, _freeze = study.v2_module().parent_modules()
    return study.candidate_pack(harness)


def _endpoint(macro: float, mae: float, *, items: int) -> dict:
    dimensions = {
        dimension: {"spearman": macro, "mean_absolute_error": mae, "mean_coverage": 1.0}
        for dimension in study.v2_module().DIMENSIONS
    }
    return {
        "item_count": items,
        "prompt_group_count": 7,
        "unit": "prompt_group_equal_weight",
        "dimensions": dimensions,
        "macro_spearman": macro,
        "mean_absolute_error": mae,
        "mean_coverage": 1.0,
    }


def _metrics(*, items: int, overrides: dict[str, tuple[float, float]] | None = None) -> list[dict]:
    overrides = overrides or {}
    return [
        {
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": candidate["candidate_sha256"],
            "development": _endpoint(*overrides.get(candidate["candidate_id"], (0.2, 0.8)), items=items),
        }
        for candidate in _candidates()
    ]


def test_model_specific_geometry_and_savings_are_exact(schedule: dict) -> None:
    assert len(schedule["grok_primary"]) == 305
    assert len(schedule["sol_validation"]) == 155
    assert {name: len(rows) for name, rows in schedule["supplemental"].items()} == {"deepseek_v4_flash": 35, "luna": 35}
    assert Counter(row["partition"] for row in schedule["grok_primary"]) == {"train": 240, "development": 65}
    assert Counter(row["partition"] for row in schedule["sol_validation"]) == {"train": 120, "development": 35}
    assert schedule["call_geometry"] == {
        "parent_full": 732,
        "mandatory": {"grok": 305, "sol": 155, "total": 460, "saved": 272, "saved_fraction": "272/732"},
        "optional_each": 35,
        "with_both_optional": {"total": 530, "saved": 202, "saved_fraction": "202/732"},
    }
    assert {(row["provider"], row["model"]) for row in schedule["grok_primary"]} == {("xai", "grok-4.6")}
    assert {(row["provider"], row["model"]) for row in schedule["sol_validation"]} == {("openai", "gpt-5.6-sol")}
    assert {(row["provider"], row["model"]) for row in schedule["supplemental"]["deepseek_v4_flash"]} == {("nous", "deepseek/deepseek-v4-flash-0731")}
    assert {(row["provider"], row["model"]) for row in schedule["supplemental"]["luna"]} == {("openai", "gpt-5.6-luna")}


def test_five_candidate_pack_has_deterministic_controls_and_exact_queue_descendants() -> None:
    candidates = _candidates()
    controls = [row for row in candidates if "factors" in row]
    assert [row["candidate_id"] for row in controls] == ["candidate-52d1be4bc34e0018", "candidate-b0132f5204b87586"]
    assert sum(controls[0]["factors"][name] != controls[1]["factors"][name] for name in controls[0]["factors"]) == 4
    all_parent = study.v2_module().parent_modules()[1].enumerate_balanced_candidates()
    assert study._control_pair(all_parent) == controls

    queue_path = Path.home() / ".codex" / "state" / "model-work-queue" / "inbox" / "cwr-hanna-grok-dev" / "7c6df77366ad4739b15a986c50b13431.json"
    if not queue_path.exists():
        pytest.skip("immutable generation-provenance inbox result is not installed on this host")
    raw = queue_path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == study.QUEUE_RESULT_SHA256
    result = json.loads(raw)
    assert result["result"]["output_hash"] == study.QUEUE_OUTPUT_SHA256
    runtime = result["result"]["runtime"]
    assert study.GENERATOR_IDENTITY == {
        "route_adapter": result["route"]["adapter"],
        "requested_model": runtime["requested_model"],
        "requested_reasoning_effort": runtime["requested_reasoning_effort"],
        "reported_model": runtime["reported_model"],
        "identity_evidence": runtime["identity_evidence"],
        "reasoning_attested": runtime["reasoning_attested"],
    }
    assert study.INTERNAL_REVIEW_IDENTITY == {
        "kind": "internal_sol_subagent_review_handoff",
        "task": "/root/hanna_grok_wave_sol_refiner",
        "reviewed_material": "unchanged_grok_queue_result_candidate_bytes",
        "native_provider_receipt": None,
        "provider_contact_claim": "none",
        "transport_attestation": None,
    }
    exact = {}
    for finding in result["result"]["output"]["findings"]:
        name, remainder = finding.split(" | mechanism: ", 1)
        exact[name] = remainder.split(" | exact_instruction: ", 1)[1]
    assert exact == study.DESCENDANT_INSTRUCTIONS
    descendants = {row["candidate_name"]: row for row in candidates if row.get("candidate_kind") == "queue_promoted_descendant"}
    assert set(descendants) == set(exact)
    for name, candidate in descendants.items():
        assert candidate["instruction_bytes"] == exact[name].encode("utf-8")
        profile = json.loads(candidate["profile_bytes"])
        assert profile["generation_provenance"]["queue_result_sha256"] == study.QUEUE_RESULT_SHA256
        assert profile["generation_provenance"]["generator_identity"] == study.GENERATOR_IDENTITY
        assert profile["generation_provenance"]["internal_review_identity"] == study.INTERNAL_REVIEW_IDENTITY
        assert profile["instruction_sha256"] == hashlib.sha256(candidate["instruction_bytes"]).hexdigest()


def test_sol_anchors_are_group_balanced_lexical_and_partition_interleaved(schedule: dict) -> None:
    representatives = schedule["anchor_representatives"]
    assert len(representatives) == 31
    assert [row["partition"] for row in representatives[:14]] == [value for _ in range(7) for value in ("train", "development")]
    assert {row["partition"] for row in representatives[14:]} == {"train"}
    assert Counter(row["prompt_group_id"] for row in schedule["sol_validation"]) == {row["prompt_group_id"]: 5 for row in representatives}
    assert len({(row["prompt_group_id"], row["candidate_id"]) for row in schedule["sol_validation"]}) == 155
    assert all(set(Counter(row["prompt_group_id"] for row in rows).values()) == {5} for rows in schedule["supplemental"].values())

    parent_study, _harness, _freeze, split, _candidates_value = study._material(**ROOTS)
    del parent_study
    by_group: dict[str, list[str]] = {}
    for row in split["items"]:
        if row["partition"] in {"train", "development"}:
            by_group.setdefault(row["prompt_group_id"], []).append(row["item_id"])
    assert {row["prompt_group_id"]: row["item_id"] for row in representatives} == {group: min(items) for group, items in by_group.items()}


def test_candidate_prompt_bindings_are_unchanged_across_every_model(schedule: dict) -> None:
    grok = {(row["item_id"], row["candidate_id"]): row for row in schedule["grok_primary"]}
    for rows in (schedule["sol_validation"], *schedule["supplemental"].values()):
        for row in rows:
            primary = grok[(row["item_id"], row["candidate_id"])]
            assert row["prompt_binding_sha256"] == primary["prompt_binding_sha256"]
            assert {field: row[field] for field in study.PROMPT_FIELDS} == {field: primary[field] for field in study.PROMPT_FIELDS}
    assert len({row["candidate_id"] for row in schedule["grok_primary"]}) == 5
    assert schedule == study.derive_schedule(**ROOTS)


def test_no_schedule_can_open_confirmation(schedule: dict) -> None:
    all_rows = [*schedule["grok_primary"], *schedule["sol_validation"], *schedule["supplemental"]["deepseek_v4_flash"], *schedule["supplemental"]["luna"]]
    assert all(row["partition"] in {"train", "development"} for row in all_rows)
    assert schedule["confirmation"] == {"status": "unopened", "scheduled_cells": 0}


def test_grok_freezes_primary_choice_before_sol_and_sol_can_only_validate(schedule: dict) -> None:
    candidates = _candidates()
    baseline = study.BASELINE_ID
    selected = next(row["candidate_id"] for row in candidates if row["candidate_id"] != baseline)
    grok = _metrics(items=13, overrides={baseline: (0.4, 0.6), selected: (0.8, 0.3)})
    commitment = study.freeze_grok_selection(grok, schedule=schedule)
    assert commitment["selected_candidate_id"] == selected
    assert commitment["model"]["model"] == "grok-4.6"
    assert commitment["sol_metrics_admitted"] is False
    assert "sol" not in inspect.signature(study.freeze_grok_selection).parameters

    sol = _metrics(items=7, overrides={baseline: (0.5, 0.4), selected: (0.6, 0.3)})
    decision = study.validate_sol_generalization(commitment, grok, sol, schedule=schedule)
    assert decision["grok_selected_candidate_id"] == selected
    assert decision["validation_eligible"] is True
    assert decision["status"] == "sol_generalization_gate_passed"
    assert decision["sol_favored_alternative_considered"] is False
    assert decision["replacement_candidate_id"] is None


@pytest.mark.parametrize("selected_sol,failed_axis", [
    ((0.49, 0.3), "macro_spearman_not_reversed"),
    ((0.6, 0.41), "mean_absolute_error_not_reversed"),
])
def test_sol_reversal_vetoes_grok_without_sol_favored_substitution(schedule: dict, selected_sol: tuple[float, float], failed_axis: str) -> None:
    candidates = _candidates()
    selected, sol_favorite = [row["candidate_id"] for row in candidates if row["candidate_id"] != study.BASELINE_ID][:2]
    grok = _metrics(items=13, overrides={selected: (0.9, 0.1)})
    commitment = study.freeze_grok_selection(grok, schedule=schedule)
    sol = _metrics(items=7, overrides={study.BASELINE_ID: (0.5, 0.4), selected: selected_sol, sol_favorite: (0.95, 0.05)})
    decision = study.validate_sol_generalization(commitment, grok, sol, schedule=schedule)
    assert decision["grok_selected_candidate_id"] == selected
    assert decision["validation_eligible"] is False
    assert decision["status"] == "sol_generalization_gate_failed_no_substitution"
    assert decision["sol_gate"][failed_axis] is False
    assert decision["replacement_candidate_id"] is None
    assert sol_favorite not in json.dumps({key: value for key, value in decision.items() if key != "supplemental"})


def test_supplemental_absence_failure_or_signal_never_changes_grok_sol_policy(schedule: dict) -> None:
    selected = next(row["candidate_id"] for row in _candidates() if row["candidate_id"] != study.BASELINE_ID)
    grok = _metrics(items=13, overrides={selected: (0.8, 0.2)})
    commitment = study.freeze_grok_selection(grok, schedule=schedule)
    sol = _metrics(items=7, overrides={study.BASELINE_ID: (0.5, 0.5), selected: (0.6, 0.4)})
    absent = study.validate_sol_generalization(commitment, grok, sol, schedule=schedule)
    failed = study.validate_sol_generalization(
        commitment,
        grok,
        sol,
        schedule=schedule,
        supplemental={"deepseek_v4_flash": {"status": "failed", "reason_code": "provider_unavailable"}},
    )
    supplemental_top = _candidates()[3]["candidate_id"]
    signaled = study.validate_sol_generalization(
        commitment,
        grok,
        sol,
        schedule=schedule,
        supplemental={"luna": _metrics(items=7, overrides={supplemental_top: (0.99, 0.01)})},
    )
    core = lambda value: {key: item for key, item in value.items() if key != "supplemental"}
    assert core(absent) == core(failed) == core(signaled)
    assert absent["supplemental"]["deepseek_v4_flash"]["status"] == "absent"
    assert failed["supplemental"]["deepseek_v4_flash"]["status"] == "failed"
    assert signaled["supplemental"]["luna"]["descriptive_top_candidate_id"] == supplemental_top
    assert all(row["selection_authority"] == "none" for row in signaled["supplemental"].values())


def test_contract_encodes_cross_model_generalization_and_no_runtime_optimizer_dependency() -> None:
    policy = study.contract()
    assert "no candidate may be promoted for being Grok-specific" in policy["governing_invariant"]
    assert policy["routes"]["grok_primary"]["role"] == "primary_iteration_and_selection_preview"
    assert policy["routes"]["sol_validation"]["role"] == "cross_model_generalization_validation_only"
    assert policy["endpoint"]["failure"] == "chosen_candidate_not_validation_eligible_no_sol_favored_substitution"
    assert policy["evidence"]["new_receipt_framework"] is False
    assert policy["evidence"]["caller_supplied_metrics_are_empirical"] is False
    assert all(value["development_only"] is True and value["runtime_dependency"] is False for value in policy["optimizer_interfaces"].values())
    source = (PACKAGE / "study.py").read_text(encoding="utf-8")
    assert "import dspy" not in source and "import optuna" not in source
    assert all(token not in source for token in ("urllib", "subprocess", "requests"))


def test_every_contract_byte_is_frozen_against_semantic_mutation(tmp_path: Path, monkeypatch) -> None:
    original = json.loads((PACKAGE / "study-contract.json").read_text(encoding="utf-8"))
    mutations = (
        lambda value: value["routes"]["grok_primary"].update(provider="mutated"),
        lambda value: value["routes"]["deepseek_v4_flash"].update(model="mutated"),
        lambda value: value["evidence"].update(required_per_cell_bindings=[]),
        lambda value: value["optimizer_interfaces"]["dspy"].update(objective="grok_specific"),
        lambda value: value.update(governing_invariant="mutated"),
        lambda value: value["interpretation_limits"].clear(),
    )
    mutated_path = tmp_path / "study-contract.json"
    monkeypatch.setattr(study, "CONTRACT_PATH", mutated_path)
    for mutate in mutations:
        value = json.loads(json.dumps(original))
        mutate(value)
        mutated_path.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(ValueError, match="study contract bytes drifted"):
            study.contract()


def test_decision_binds_metrics_schedule_and_implementation(schedule: dict) -> None:
    selected = next(row["candidate_id"] for row in _candidates() if row["candidate_id"] != study.BASELINE_ID)
    grok = _metrics(items=13, overrides={selected: (0.8, 0.2)})
    sol = _metrics(items=7, overrides={study.BASELINE_ID: (0.5, 0.5), selected: (0.6, 0.4)})
    commitment = study.freeze_grok_selection(grok, schedule=schedule)
    decision = study.validate_sol_generalization(commitment, grok, sol, schedule=schedule)
    assert decision["grok_commitment_sha256"] == commitment["commitment_sha256"]
    assert decision["grok_candidate_metrics_sha256"] == study.sha256(sorted(grok, key=lambda row: row["candidate_id"]))
    assert decision["sol_anchor_metrics_sha256"] == study.sha256(sorted(sol, key=lambda row: row["candidate_id"]))
    assert decision["schedule_lineage"] == commitment["schedule_lineage"]
    assert decision["schedule_lineage"]["schedule_sha256"] == schedule["schedule_sha256"]
    assert decision["implementation"]["study_contract_sha256"] == study.CONTRACT_SHA256
    assert decision["implementation"]["study_py_sha256"] == study._file_sha(PACKAGE / "study.py")

    mutated = json.loads(json.dumps(schedule))
    mutated["sol_validation"][0]["provider"] = "mutated"
    mutated["schedule_sha256"] = study.sha256({key: mutated[key] for key in ("grok_primary", "sol_validation", "supplemental")})
    with pytest.raises(ValueError, match="scheduled cell drifted"):
        study.validate_sol_generalization(commitment, grok, sol, schedule=mutated)


def test_v2_analyzer_is_hash_pinned_and_endpoint_is_reused(monkeypatch) -> None:
    v2 = study.v2_module()
    called = {}

    def endpoint(rows, targets, *, expected_items, expected_groups):
        called.update({"rows": rows, "targets": targets, "items": expected_items, "groups": expected_groups})
        return {"reused": True}

    monkeypatch.setattr(v2, "_candidate_endpoint", endpoint)
    assert study.recompute_equal_group_endpoint([], {}, expected_items=7) == {"reused": True}
    assert called == {"rows": [], "targets": {}, "items": 7, "groups": 7}
    monkeypatch.setitem(study.V2_HASHES, "analyze.py", "0" * 64)
    with pytest.raises(ValueError, match="pinned v2 analyze.py drifted"):
        study.v2_module()
