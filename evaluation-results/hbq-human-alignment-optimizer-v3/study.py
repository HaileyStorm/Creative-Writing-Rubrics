#!/usr/bin/env python3
"""Grok-volume, Sol-validation schedule and cross-model generalization policy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import statistics
from itertools import combinations
from itertools import zip_longest
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(os.path.abspath(__file__)).parent
V2 = HERE.parent / "hbq-human-alignment-optimizer-v2"
CONTRACT_PATH = HERE / "study-contract.json"
STUDY_ID = "hbq-human-alignment-optimizer-v3"
BASELINE_ID = "candidate-52d1be4bc34e0018"
CONTRACT_SHA256 = "690f96bdb7c52d4863593b90a80f066248b4cb4b9307198ff9ac23b71364fe8b"
QUEUE_RESULT_SHA256 = "bf2f171ca103359120f8aa73700a73a57b5f55e6390dc3a7642e996e060a8376"
QUEUE_OUTPUT_SHA256 = "c2b29d6cfb5f7c50332b841b510316292527e2702d9c1323dedbbbd07847cc27"
GENERATOR_IDENTITY = {
    "route_adapter": "grok_exec",
    "requested_model": "grok-4.6",
    "requested_reasoning_effort": "high",
    "reported_model": "grok-4.6-build",
    "identity_evidence": "requested_only",
    "reasoning_attested": False,
}
INTERNAL_REVIEW_IDENTITY = {
    "kind": "internal_sol_subagent_review_handoff",
    "task": "/root/hanna_grok_wave_sol_refiner",
    "reviewed_material": "unchanged_grok_queue_result_candidate_bytes",
    "native_provider_receipt": None,
    "provider_contact_claim": "none",
    "transport_attestation": None,
}
DESCENDANT_INSTRUCTIONS = {
    "absence-defect-split": "Score each named dimension independently on the supplied scale from that dimension's own observable instantiation. Always give a finite score. Separate thin or missing support from demonstrated weakness. Thin or missing support means the text does not instantiate enough of the construct for the quality to be realized; score the limited instantiation that is actually present, without converting uncertainty into the midpoint of the scale and without treating omission as a flaw. Demonstrated weakness means the text exhibits an actual breakdown of that construct; score that breakdown lower than mere lack of instantiation. Do not carry a high or low result from one dimension into another, and do not let global liking, length, or surface fluency set any dimension. Keep construct meanings unchanged: Relevance is fit to the requested story; Coherence is consistency of events, time, and reference; Empathy is understanding of feeling as depicted or elicited; Surprise is unforeseeable development that still fits; Engagement is hold on attention; Complexity is layered structure and inference load. HANNA human ratings are noisy reference context, not ground truth and not numeric targets. Do not add constructs.",
    "construct-lock-antihalo": "Give every dimension a finite score on the supplied scale. Judge each construct only with material that bears on that construct. Lock meanings so they do not drift or merge: Relevance remains prompt-story fit; Coherence remains internal consistency; Empathy remains feeling-understanding; Surprise remains unexpected yet fit development; Engagement remains sustained interest; Complexity remains structural and inferential richness. Do not score one construct as a proxy for another. Thin support is scarcity of construct-relevant material, not a mandated middle score and not automatic failure. Demonstrated weakness is visible violation or collapse of that construct. Assign different scores to those two states. Never replace judgment with a midpoint default. Block halo from length, style, preference, or any other dimension. HANNA ratings, if seen, only contextualize human noise; do not match them.",
    "realization-without-midpoint": "On the supplied scale, score how fully each listed construct is realized in the text. Every dimension gets a finite score. Magnitude follows realization, not confidence. If support is thin or missing, the construct is only weakly realized; that is not a license to sit at mid-scale. If the text demonstrates a defect, realization is worse than thin support. Do not reward or penalize by defaulting. Keep dimensions non-compensating: unused credit on one construct does not lift another, and a defect on one does not pull the rest. Preserve the distinct meanings of Relevance, Coherence, Empathy, Surprise, Engagement, and Complexity. Treat HANNA human ratings as noisy reference context rather than ground truth or targets. Do not introduce extra constructs.",
}
V2_HASHES = {
    "analyze.py": "dc8479a962e4a0e2d0082a4619e0e52922d9d82663bd97bc6e17694781aef822",
    "study-contract.json": "b7623ff071ebf5404269fd6534a13901845e9ce5350bdab81c9d59b6e96932d5",
}
PROMPT_FIELDS = (
    "task_payload_sha256",
    "candidate_instruction_sha256",
    "candidate_profile_sha256",
    "response_schema_sha256",
    "prompt_sha256",
    "story_sha256",
)
_V2_MODULE: ModuleType | None = None


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract() -> dict[str, Any]:
    if _file_sha(CONTRACT_PATH) != CONTRACT_SHA256:
        raise ValueError("HANNA v3 study contract bytes drifted")
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    required = {
        "format_version", "study_id", "kind", "parent", "governing_invariant", "baseline", "candidate_pack", "frozen_schedule", "routes",
        "schedule", "call_geometry", "endpoint", "evidence", "supplemental", "optimizer_interfaces", "confirmation",
        "result_authority", "interpretation_limits",
    }
    if not isinstance(value, dict) or set(value) != required or value["format_version"] != 1 or value["study_id"] != STUDY_ID:
        raise ValueError("HANNA v3 contract identity or fields drifted")
    if value["parent"] != {
        "study_id": "hbq-human-alignment-optimizer-v2",
        "analyze_sha256": V2_HASHES["analyze.py"],
        "study_contract_sha256": V2_HASHES["study-contract.json"],
        "reuse": "split_derivation_equal_group_endpoint_and_selection_key",
    }:
        raise ValueError("HANNA v3 parent commitments drifted")
    if value["baseline"]["candidate_id"] != BASELINE_ID or value["confirmation"] != {"status": "unopened", "scheduled_cells": 0}:
        raise ValueError("HANNA v3 baseline or confirmation contract drifted")
    if value["call_geometry"] != {
        "parent_full": 732,
        "mandatory": {"grok": 305, "sol": 155, "total": 460, "saved": 272, "saved_fraction": "272/732"},
        "optional_each": 35,
        "with_both_optional": {"total": 530, "saved": 202, "saved_fraction": "202/732"},
    }:
        raise ValueError("HANNA v3 call geometry contract drifted")
    if value["endpoint"] != {
        "unit": "prompt_group_equal_weight",
        "primary": "grok_development_macro_spearman_descending",
        "tie_breakers": ["mean_absolute_error:ascending", "candidate_id:lexicographic"],
        "sol_gate": "chosen_macro_spearman_gte_baseline_and_chosen_mean_absolute_error_lte_baseline",
        "failure": "chosen_candidate_not_validation_eligible_no_sol_favored_substitution",
    }:
        raise ValueError("HANNA v3 endpoint policy contract drifted")
    if (
        value["schedule"].get("unchanged_candidate_task_schema_bytes_across_models") is not True
        or value["schedule"].get("confirmation_cells") != 0
        or value["supplemental"].get("selection_authority") != "none"
        or value["supplemental"].get("absence_or_failure_blocks_grok_sol_policy") is not False
        or value["result_authority"] != "nonempirical_until_native_request_response_trust_is_independently_verified"
        or value["evidence"].get("caller_supplied_metrics_are_empirical") is not False
        or value["evidence"].get("new_receipt_framework") is not False
        or any(interface.get("development_only") is not True or interface.get("runtime_dependency") is not False for interface in value["optimizer_interfaces"].values())
    ):
        raise ValueError("HANNA v3 generalization or authority contract drifted")
    return value


def _implementation_commitment() -> dict[str, str]:
    return {
        "study_py_sha256": _file_sha(Path(os.path.abspath(__file__))),
        "study_contract_sha256": CONTRACT_SHA256,
    }


def v2_module() -> ModuleType:
    global _V2_MODULE
    for filename, expected in V2_HASHES.items():
        if _file_sha(V2 / filename) != expected:
            raise ValueError(f"HANNA v3 pinned v2 {filename} drifted")
    if _V2_MODULE is None:
        spec = importlib.util.spec_from_file_location("_hanna_optimizer_v2_for_v3", V2 / "analyze.py")
        if spec is None or spec.loader is None:
            raise ValueError("HANNA v3 cannot load its pinned v2 analyzer")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _V2_MODULE = module
    return _V2_MODULE


def _control_pair(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for left, right in combinations(candidates, 2):
        distance = sum(left["factors"][name] != right["factors"][name] for name in left["factors"])
        pair = tuple(sorted((left["candidate_id"], right["candidate_id"])))
        ranked.append((-distance, pair, left, right))
    _distance, selected_ids, _left, _right = min(ranked, key=lambda row: (row[0], row[1]))
    by_id = {row["candidate_id"]: row for row in candidates}
    return [dict(by_id[candidate_id]) for candidate_id in selected_ids]


def _descendant_candidate(name: str, instruction: str, control: Mapping[str, Any]) -> dict[str, Any]:
    instruction_bytes = instruction.encode("utf-8")
    instruction_sha = hashlib.sha256(instruction_bytes).hexdigest()
    inherited = json.loads(control["profile_bytes"].decode("utf-8"))["immutable_cwr_commitments"]
    profile_bytes = canonical({
        "format_version": 1,
        "study_id": STUDY_ID,
        "candidate_kind": "grok_generated_sol_anchor_preserved_descendant",
        "candidate_name": name,
        "instruction_sha256": instruction_sha,
        "generation_provenance": {
            "queue_item_id": "7c6df77366ad4739b15a986c50b13431",
            "queue_result_sha256": QUEUE_RESULT_SHA256,
            "queue_output_sha256": QUEUE_OUTPUT_SHA256,
            "finding_name": name,
            "generator_identity": GENERATOR_IDENTITY,
            "internal_review_identity": INTERNAL_REVIEW_IDENTITY,
        },
        "dimension_weights": {name: 1 for name in v2_module().DIMENSIONS},
        "demonstrations": 0,
        "same_bytes_for_models": ["grok-4.6", "gpt-5.6-sol", "deepseek/deepseek-v4-flash-0731", "gpt-5.6-luna"],
        "immutable_cwr_commitments": inherited,
    })
    profile_sha = hashlib.sha256(profile_bytes).hexdigest()
    digest = hashlib.sha256(canonical({"instruction_sha256": instruction_sha, "profile_sha256": profile_sha})).hexdigest()
    return {
        "candidate_id": f"candidate-{digest[:16]}",
        "candidate_sha256": digest,
        "candidate_kind": "queue_promoted_descendant",
        "candidate_name": name,
        "instruction_bytes": instruction_bytes,
        "profile_bytes": profile_bytes,
        "instruction_sha256": instruction_sha,
        "profile_sha256": profile_sha,
    }


def candidate_pack(harness: ModuleType | None = None) -> list[dict[str, Any]]:
    harness = harness or v2_module().parent_modules()[1]
    parents = harness.enumerate_balanced_candidates()
    harness.validate_candidates(parents)
    controls = _control_pair(parents)
    if [row["candidate_id"] for row in controls] != ["candidate-52d1be4bc34e0018", "candidate-b0132f5204b87586"]:
        raise ValueError("HANNA v3 deterministic control pair drifted")
    descendants = [_descendant_candidate(name, DESCENDANT_INSTRUCTIONS[name], controls[0]) for name in sorted(DESCENDANT_INSTRUCTIONS)]
    result = sorted([*controls, *descendants], key=lambda row: row["candidate_id"])
    if len(result) != 5 or len({row["candidate_id"] for row in result}) != 5:
        raise ValueError("HANNA v3 candidate pack geometry drifted")
    return result


def _candidate_pack_contract(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    controls = [row for row in candidates if "factors" in row]
    descendants = sorted((row for row in candidates if row.get("candidate_kind") == "queue_promoted_descendant"), key=lambda row: row["candidate_name"])
    return {
        "count": 5,
        "control_selection": "lexicographically_first_maximum_hamming_distance_pair_over_four_v1_factor_fields",
        "parent_controls": [{key: row[key] for key in ("candidate_id", "candidate_sha256")} for row in controls],
        "descendants": [
            {
                "name": row["candidate_name"],
                **{key: row[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256")},
            }
            for row in descendants
        ],
        "generation_provenance": {
            "queue_item_id": "7c6df77366ad4739b15a986c50b13431",
            "queue_result_sha256": QUEUE_RESULT_SHA256,
            "queue_output_sha256": QUEUE_OUTPUT_SHA256,
            "generator_identity": GENERATOR_IDENTITY,
            "internal_review_identity": INTERNAL_REVIEW_IDENTITY,
        },
    }


def _material(*, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[ModuleType, ModuleType, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    v2 = v2_module()
    study, harness, _freeze_module, freeze = v2._validated_parent(
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    split = study.derive_split_manifest(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    study.validate_split_manifest(split, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    candidates = candidate_pack(harness)
    return study, harness, freeze, split, candidates


def _representatives(split: Mapping[str, Any]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for row in split["items"]:
        if row["partition"] in {"train", "development"}:
            grouped.setdefault((row["partition"], row["prompt_group_id"]), []).append(row["item_id"])
    partitions = {
        partition: [
            {"partition": partition, "prompt_group_id": group, "item_id": min(items)}
            for (candidate_partition, group), items in sorted(grouped.items())
            if candidate_partition == partition
        ]
        for partition in ("train", "development")
    }
    if len(partitions["train"]) != 24 or len(partitions["development"]) != 7:
        raise ValueError("HANNA v3 anchor group geometry drifted")
    interleaved = []
    for train, development in zip_longest(partitions["train"], partitions["development"]):
        if train is not None:
            interleaved.append(train)
        if development is not None:
            interleaved.append(development)
    return interleaved


def _prompt_binding(cell: Mapping[str, Any]) -> dict[str, str]:
    return {field: cell[field] for field in PROMPT_FIELDS}


def _scheduled_cell(source: Mapping[str, Any], *, route_name: str, route: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    key = {
        "study_id": STUDY_ID,
        "route_name": route_name,
        "item_id": source["item_id"],
        "candidate_id": source["candidate_id"],
    }
    return {
        "ordinal": ordinal,
        "cell_id": "v3-cell-" + sha256(key)[:16],
        "source_task_cell_id": source["cell_id"],
        "partition": source["partition"],
        "prompt_group_id": source["prompt_group_id"],
        "item_id": source["item_id"],
        "candidate_id": source["candidate_id"],
        "provider": route["provider"],
        "model": route["model"],
        "configured_reasoning_effort": route["configured_reasoning_effort"],
        "transport_identity": route["transport_identity"],
        "prompt_binding_sha256": sha256(_prompt_binding(source)),
        **_prompt_binding(source),
    }


def derive_schedule(*, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    policy = contract()
    _study, _harness, freeze, split, candidates = _material(
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    candidate_ids = [candidate["candidate_id"] for candidate in candidates]
    if policy["candidate_pack"] != _candidate_pack_contract(candidates):
        raise ValueError("HANNA v3 candidate-pack commitment drifted")
    if policy["baseline"] != {
        "candidate_id": BASELINE_ID,
        "candidate_sha256": next(candidate["candidate_sha256"] for candidate in candidates if candidate["candidate_id"] == BASELINE_ID),
        "kind": "predeclared_first_deterministic_parent_control",
    }:
        raise ValueError("HANNA v3 predeclared baseline commitment drifted")
    parent_index = {(row["model"], row["item_id"], row["candidate_id"]): row for row in freeze["schedule"]}
    active_items = sorted({row["item_id"] for row in split["items"] if row["partition"] in {"train", "development"}})
    if len(active_items) != 61 or len(parent_index) != 732:
        raise ValueError("HANNA v3 parent schedule geometry drifted")
    split_by_item = {row["item_id"]: row for row in split["items"]}
    freeze_module = v2_module().parent_modules()[2]
    source_material = freeze_module._source_material(
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    response_schema_sha = hashlib.sha256(freeze_module.response_schema_bytes()).hexdigest()
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    parent_candidate_ids = {row["candidate_id"] for row in freeze["candidate_commitments"]}
    for item_id in active_items:
        item = split_by_item[item_id]
        source = source_material[item_id]
        for candidate in candidates:
            task_sha = hashlib.sha256(freeze_module._payload_bytes(item=source, candidate=candidate)).hexdigest()
            for model, provider in (("gpt-5.6-sol", "openai"), ("grok-4.6", "xai")):
                key = {"item_id": item_id, "prompt_group_id": item["prompt_group_id"], "partition": item["partition"], "candidate_id": candidate["candidate_id"], "provider": provider, "model": model}
                row = {
                    **key,
                    "cell_id": "v3-source-" + sha256(key)[:16],
                    "task_payload_sha256": task_sha,
                    "candidate_instruction_sha256": candidate["instruction_sha256"],
                    "candidate_profile_sha256": candidate["profile_sha256"],
                    "response_schema_sha256": response_schema_sha,
                    "prompt_sha256": source["prompt_sha256"],
                    "story_sha256": source["story_sha256"],
                }
                if candidate["candidate_id"] in parent_candidate_ids:
                    parent = parent_index[(model, item_id, candidate["candidate_id"])]
                    if {field: row[field] for field in PROMPT_FIELDS} != {field: parent[field] for field in PROMPT_FIELDS}:
                        raise ValueError("HANNA v3 parent-control task bytes drifted")
                    row["cell_id"] = parent["cell_id"]
                index[(model, item_id, candidate["candidate_id"])] = row
    prompt_bindings = []
    for item_id in active_items:
        for candidate_id in candidate_ids:
            sol = index[("gpt-5.6-sol", item_id, candidate_id)]
            grok = index[("grok-4.6", item_id, candidate_id)]
            if _prompt_binding(sol) != _prompt_binding(grok):
                raise ValueError("HANNA v3 parent candidate prompt bytes differ across models")
            prompt_bindings.append({"item_id": item_id, "candidate_id": candidate_id, **_prompt_binding(sol)})
    routes = policy["routes"]
    grok_sources = [index[("grok-4.6", item_id, candidate_id)] for item_id in active_items for candidate_id in candidate_ids]
    grok = [_scheduled_cell(row, route_name="grok_primary", route=routes["grok_primary"], ordinal=index + 1) for index, row in enumerate(grok_sources)]
    representatives = _representatives(split)
    sol = []
    for representative in representatives:
        for candidate_id in candidate_ids:
            source = index[("gpt-5.6-sol", representative["item_id"], candidate_id)]
            sol.append(_scheduled_cell(source, route_name="sol_validation", route=routes["sol_validation"], ordinal=len(sol) + 1))
    development_representatives = [row for row in representatives if row["partition"] == "development"]
    supplemental: dict[str, list[dict[str, Any]]] = {}
    for route_name in ("deepseek_v4_flash", "luna"):
        rows = []
        for representative in development_representatives:
            for candidate_id in candidate_ids:
                source = index[("grok-4.6", representative["item_id"], candidate_id)]
                rows.append(_scheduled_cell(source, route_name=route_name, route=routes[route_name], ordinal=len(rows) + 1))
        supplemental[route_name] = rows
    geometry = {
        "parent_full": 732,
        "mandatory": {"grok": len(grok), "sol": len(sol), "total": len(grok) + len(sol), "saved": 732 - len(grok) - len(sol), "saved_fraction": "272/732"},
        "optional_each": len(supplemental["deepseek_v4_flash"]),
        "with_both_optional": {
            "total": len(grok) + len(sol) + sum(len(rows) for rows in supplemental.values()),
            "saved": 732 - len(grok) - len(sol) - sum(len(rows) for rows in supplemental.values()),
            "saved_fraction": "202/732",
        },
    }
    if geometry != policy["call_geometry"]:
        raise ValueError("HANNA v3 call geometry drifted")
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "provider_free_cross_model_schedule",
        "parent_v2": dict(policy["parent"]),
        "candidate_ids": candidate_ids,
        "candidate_set_sha256": sha256([{"candidate_id": row["candidate_id"], "candidate_sha256": row["candidate_sha256"]} for row in candidates]),
        "unchanged_prompt_bindings_sha256": sha256(prompt_bindings),
        "anchor_representatives": representatives,
        "grok_primary": grok,
        "sol_validation": sol,
        "supplemental": supplemental,
        "call_geometry": geometry,
        "confirmation": {"status": "unopened", "scheduled_cells": 0},
    }
    result["schedule_sha256"] = sha256({key: result[key] for key in ("grok_primary", "sol_validation", "supplemental")})
    return result


def recompute_equal_group_endpoint(
    rows: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, float]],
    *,
    expected_items: int,
) -> dict[str, Any]:
    """Reuse the pinned v2 equal-group endpoint; do not fork metric semantics."""
    return v2_module()._candidate_endpoint(rows, targets, expected_items=expected_items, expected_groups=7)


def _validate_candidate_metrics(metrics: Sequence[Mapping[str, Any]], *, expected_items: int) -> list[dict[str, Any]]:
    _study, harness, _freeze = v2_module().parent_modules()
    candidates = candidate_pack(harness)
    if not isinstance(metrics, Sequence) or isinstance(metrics, (str, bytes)) or len(metrics) != 5:
        raise ValueError("HANNA v3 candidate metrics require exactly five candidates")
    observed = sorted((dict(row) for row in metrics), key=lambda row: row.get("candidate_id", ""))
    expected = sorted(candidates, key=lambda row: row["candidate_id"])
    if [row.get("candidate_id") for row in observed] != [row["candidate_id"] for row in expected]:
        raise ValueError("HANNA v3 candidate metric identities drifted")
    for row, candidate in zip(observed, expected, strict=True):
        if set(row) != {"candidate_id", "candidate_sha256", "development"} or row["candidate_sha256"] != candidate["candidate_sha256"]:
            raise ValueError("HANNA v3 candidate metric commitment drifted")
        endpoint = row["development"]
        if not isinstance(endpoint, Mapping) or set(endpoint) != {
            "item_count", "prompt_group_count", "unit", "dimensions", "macro_spearman", "mean_absolute_error", "mean_coverage"
        }:
            raise ValueError("HANNA v3 endpoint fields drifted")
        if endpoint["item_count"] != expected_items or endpoint["prompt_group_count"] != 7 or endpoint["unit"] != "prompt_group_equal_weight":
            raise ValueError("HANNA v3 endpoint geometry drifted")
        dimensions = endpoint["dimensions"]
        if not isinstance(dimensions, Mapping) or set(dimensions) != set(v2_module().DIMENSIONS):
            raise ValueError("HANNA v3 endpoint dimensions drifted")
        for value in (endpoint["macro_spearman"], endpoint["mean_absolute_error"], endpoint["mean_coverage"]):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError("HANNA v3 endpoint metric is invalid")
        if not -1 <= float(endpoint["macro_spearman"]) <= 1 or float(endpoint["mean_absolute_error"]) < 0 or not 0 <= float(endpoint["mean_coverage"]) <= 1:
            raise ValueError("HANNA v3 endpoint metric is out of range")
        for dimension in v2_module().DIMENSIONS:
            detail = dimensions[dimension]
            if not isinstance(detail, Mapping) or set(detail) != {"spearman", "mean_absolute_error", "mean_coverage"}:
                raise ValueError("HANNA v3 endpoint dimension fields drifted")
            values = (detail["spearman"], detail["mean_absolute_error"], detail["mean_coverage"])
            if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in values):
                raise ValueError("HANNA v3 endpoint dimension metric is invalid")
            if not -1 <= float(detail["spearman"]) <= 1 or float(detail["mean_absolute_error"]) < 0 or not 0 <= float(detail["mean_coverage"]) <= 1:
                raise ValueError("HANNA v3 endpoint dimension metric is out of range")
        if (
            not math.isclose(float(endpoint["macro_spearman"]), statistics.fmean(float(dimensions[name]["spearman"]) for name in v2_module().DIMENSIONS), rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(float(endpoint["mean_absolute_error"]), statistics.fmean(float(dimensions[name]["mean_absolute_error"]) for name in v2_module().DIMENSIONS), rel_tol=1e-12, abs_tol=1e-12)
            or not math.isclose(float(endpoint["mean_coverage"]), statistics.fmean(float(dimensions[name]["mean_coverage"]) for name in v2_module().DIMENSIONS), rel_tol=1e-12, abs_tol=1e-12)
        ):
            raise ValueError("HANNA v3 endpoint aggregate is not independently recomputable")
    return observed


def _schedule_lineage(schedule: Mapping[str, Any]) -> dict[str, str]:
    expected_keys = {
        "format_version", "study_id", "kind", "parent_v2", "candidate_ids", "candidate_set_sha256",
        "unchanged_prompt_bindings_sha256", "anchor_representatives", "grok_primary", "sol_validation",
        "supplemental", "call_geometry", "confirmation", "schedule_sha256",
    }
    if not isinstance(schedule, Mapping) or set(schedule) != expected_keys:
        raise ValueError("HANNA v3 schedule fields drifted")
    policy = contract()
    if (
        schedule["format_version"] != 1
        or schedule["study_id"] != STUDY_ID
        or schedule["kind"] != "provider_free_cross_model_schedule"
        or schedule["parent_v2"] != policy["parent"]
        or schedule["call_geometry"] != policy["call_geometry"]
        or schedule["confirmation"] != policy["confirmation"]
        or schedule["schedule_sha256"]
        != sha256({key: schedule[key] for key in ("grok_primary", "sol_validation", "supplemental")})
    ):
        raise ValueError("HANNA v3 schedule commitment drifted")
    routes = policy["routes"]
    candidates = candidate_pack()
    candidate_ids = [row["candidate_id"] for row in candidates]
    candidate_by_id = {row["candidate_id"]: row for row in candidates}
    expected_candidate_set_sha = sha256([{"candidate_id": row["candidate_id"], "candidate_sha256": row["candidate_sha256"]} for row in candidates])
    if schedule["candidate_ids"] != candidate_ids or schedule["candidate_set_sha256"] != expected_candidate_set_sha:
        raise ValueError("HANNA v3 scheduled candidate pack drifted")
    representatives = schedule["anchor_representatives"]
    if (
        not isinstance(representatives, list)
        or len(representatives) != 31
        or any(set(row) != {"partition", "prompt_group_id", "item_id"} for row in representatives)
        or len({(row["partition"], row["prompt_group_id"], row["item_id"]) for row in representatives}) != 31
        or [row["partition"] for row in representatives[:14]] != [value for _ in range(7) for value in ("train", "development")]
        or any(row["partition"] != "train" for row in representatives[14:])
    ):
        raise ValueError("HANNA v3 anchor representatives drifted")
    route_rows = {
        "grok_primary": schedule["grok_primary"],
        "sol_validation": schedule["sol_validation"],
        "deepseek_v4_flash": schedule["supplemental"].get("deepseek_v4_flash"),
        "luna": schedule["supplemental"].get("luna"),
    }
    expected_counts = {"grok_primary": 305, "sol_validation": 155, "deepseek_v4_flash": 35, "luna": 35}
    cell_keys = {
        "ordinal", "cell_id", "source_task_cell_id", "partition", "prompt_group_id", "item_id", "candidate_id",
        "provider", "model", "configured_reasoning_effort", "transport_identity", "prompt_binding_sha256", *PROMPT_FIELDS,
    }
    for route_name, rows in route_rows.items():
        if not isinstance(rows, list) or len(rows) != expected_counts[route_name]:
            raise ValueError(f"HANNA v3 {route_name} schedule geometry drifted")
        identity = routes[route_name]
        if [row.get("ordinal") for row in rows] != list(range(1, len(rows) + 1)) or len({row.get("cell_id") for row in rows}) != len(rows):
            raise ValueError(f"HANNA v3 {route_name} schedule ordering drifted")
        for row in rows:
            candidate = candidate_by_id.get(row.get("candidate_id"))
            if (
                set(row) != cell_keys
                or candidate is None
                or row.get("candidate_instruction_sha256") != candidate["instruction_sha256"]
                or row.get("candidate_profile_sha256") != candidate["profile_sha256"]
                or row.get("provider") != identity["provider"]
                or row.get("model") != identity["model"]
                or row.get("configured_reasoning_effort") != identity["configured_reasoning_effort"]
                or row.get("transport_identity") != identity["transport_identity"]
                or row.get("partition") not in {"train", "development"}
                or row.get("prompt_binding_sha256") != sha256(_prompt_binding(row))
            ):
                raise ValueError(f"HANNA v3 {route_name} scheduled cell drifted")
    grok_pairs = [(row["item_id"], row["candidate_id"]) for row in schedule["grok_primary"]]
    active_items = sorted({item_id for item_id, _candidate_id in grok_pairs})
    if len(active_items) != 61 or grok_pairs != [(item_id, candidate_id) for item_id in active_items for candidate_id in candidate_ids]:
        raise ValueError("HANNA v3 Grok schedule topology drifted")
    representative_pairs = [(row["item_id"], candidate_id) for row in representatives for candidate_id in candidate_ids]
    if [(row["item_id"], row["candidate_id"]) for row in schedule["sol_validation"]] != representative_pairs:
        raise ValueError("HANNA v3 Sol schedule topology drifted")
    development_pairs = [(row["item_id"], candidate_id) for row in representatives if row["partition"] == "development" for candidate_id in candidate_ids]
    if any([(row["item_id"], row["candidate_id"]) for row in rows] != development_pairs for rows in schedule["supplemental"].values()):
        raise ValueError("HANNA v3 supplemental schedule topology drifted")
    grok_by_pair = {(row["item_id"], row["candidate_id"]): _prompt_binding(row) for row in schedule["grok_primary"]}
    if schedule["unchanged_prompt_bindings_sha256"] != sha256([
        {"item_id": item_id, "candidate_id": candidate_id, **grok_by_pair[(item_id, candidate_id)]}
        for item_id, candidate_id in grok_pairs
    ]):
        raise ValueError("HANNA v3 prompt-binding commitment drifted")
    for rows in (schedule["sol_validation"], *schedule["supplemental"].values()):
        if any(_prompt_binding(row) != grok_by_pair[(row["item_id"], row["candidate_id"])] for row in rows):
            raise ValueError("HANNA v3 cross-model prompt bytes drifted")
    lineage = {
        "schedule_sha256": schedule["schedule_sha256"],
        "candidate_set_sha256": schedule["candidate_set_sha256"],
        "unchanged_prompt_bindings_sha256": schedule["unchanged_prompt_bindings_sha256"],
        "grok_primary_cells_sha256": sha256(schedule["grok_primary"]),
        "sol_validation_cells_sha256": sha256(schedule["sol_validation"]),
    }
    if lineage != policy["frozen_schedule"]:
        raise ValueError("HANNA v3 exact frozen schedule drifted")
    return lineage


def freeze_grok_selection(
    candidate_metrics: Sequence[Mapping[str, Any]],
    *,
    schedule: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze Grok's choice before any Sol metric is admitted."""
    metrics = _validate_candidate_metrics(candidate_metrics, expected_items=13)
    lineage = _schedule_lineage(schedule)
    selected = min(metrics, key=v2_module()._selection_key)["candidate_id"]
    base = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "grok_primary_selection_preview_commitment",
        "model": contract()["routes"]["grok_primary"],
        "candidate_metrics_sha256": sha256(metrics),
        "selected_candidate_id": selected,
        "baseline_candidate_id": BASELINE_ID,
        "schedule_lineage": lineage,
        "implementation": _implementation_commitment(),
        "sol_metrics_admitted": False,
        "empirical_authority": "none",
    }
    return {**base, "commitment_sha256": sha256(base)}


def _supplemental_summary(supplied: Mapping[str, Any] | None) -> dict[str, Any]:
    supplied = dict(supplied or {})
    if not set(supplied).issubset({"deepseek_v4_flash", "luna"}):
        raise ValueError("HANNA v3 supplemental provider is unknown")
    result = {}
    routes = contract()["routes"]
    for name in ("deepseek_v4_flash", "luna"):
        value = supplied.get(name)
        common = {"identity": routes[name], "role": "provisional_nonblocking_signal", "selection_authority": "none"}
        if value is None:
            result[name] = {**common, "status": "absent"}
        elif isinstance(value, Mapping) and value.get("status") == "failed" and set(value) == {"status", "reason_code"} and isinstance(value["reason_code"], str) and value["reason_code"]:
            result[name] = {**common, "status": "failed", "reason_code": value["reason_code"]}
        else:
            metrics = _validate_candidate_metrics(value, expected_items=7)
            result[name] = {
                **common,
                "status": "available_nonempirical",
                "descriptive_top_candidate_id": min(metrics, key=v2_module()._selection_key)["candidate_id"],
                "candidate_metrics_sha256": sha256(metrics),
            }
    return result


def validate_sol_generalization(
    grok_commitment: Mapping[str, Any],
    grok_candidate_metrics: Sequence[Mapping[str, Any]],
    sol_anchor_metrics: Sequence[Mapping[str, Any]],
    *,
    schedule: Mapping[str, Any],
    supplemental: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Allow Sol to validate or veto the frozen Grok choice, never replace it."""
    lineage = _schedule_lineage(schedule)
    expected_commitment = freeze_grok_selection(grok_candidate_metrics, schedule=schedule)
    if dict(grok_commitment) != expected_commitment:
        raise ValueError("HANNA v3 Grok selection commitment drifted")
    sol = _validate_candidate_metrics(sol_anchor_metrics, expected_items=7)
    by_candidate = {row["candidate_id"]: row["development"] for row in sol}
    selected_id = expected_commitment["selected_candidate_id"]
    selected = by_candidate[selected_id]
    baseline = by_candidate[BASELINE_ID]
    macro_not_reversed = float(selected["macro_spearman"]) >= float(baseline["macro_spearman"])
    mae_not_reversed = float(selected["mean_absolute_error"]) <= float(baseline["mean_absolute_error"])
    eligible = macro_not_reversed and mae_not_reversed
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "cross_model_generalization_validation_nonempirical",
        "grok_commitment_sha256": expected_commitment["commitment_sha256"],
        "grok_candidate_metrics_sha256": expected_commitment["candidate_metrics_sha256"],
        "sol_anchor_metrics_sha256": sha256(sol),
        "schedule_lineage": lineage,
        "implementation": _implementation_commitment(),
        "grok_selected_candidate_id": selected_id,
        "predeclared_baseline_candidate_id": BASELINE_ID,
        "validation_eligible": eligible,
        "status": "sol_generalization_gate_passed" if eligible else "sol_generalization_gate_failed_no_substitution",
        "sol_gate": {
            "macro_spearman_not_reversed": macro_not_reversed,
            "mean_absolute_error_not_reversed": mae_not_reversed,
            "selected": {"macro_spearman": selected["macro_spearman"], "mean_absolute_error": selected["mean_absolute_error"]},
            "baseline": {"macro_spearman": baseline["macro_spearman"], "mean_absolute_error": baseline["mean_absolute_error"]},
        },
        "sol_favored_alternative_considered": False,
        "replacement_candidate_id": None,
        "supplemental": _supplemental_summary(supplemental),
        "confirmation": {"status": "unopened", "scheduled_cells": 0},
        "empirical_authority": "none_until_native_request_response_trust_is_independently_verified",
    }
