"""Source-bound, provider-free HANNA candidate generation only."""
from __future__ import annotations

import hashlib
import importlib
import itertools
import csv
import io
from pathlib import Path
from typing import Any, Mapping, Sequence

from study import (
    CONTRACT,
    _read_bytes_checked,
    canonical,
    derive_eligible_map,
    derive_split_manifest,
    finite,
    sha256,
    validate_eligible_map,
    validate_split_manifest,
)


STUDY_ID = "hbq-human-alignment-optimizer-v1"
FACTOR_NAMES = (
    "construct_framing",
    "scope_materiality",
    "missing_evidence_not_no",
    "human_reference_variant",
)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
SAMPLER = {"algorithm": "deterministic_candidate_profile_v1", "seed": 628811, "temperature": 0}
MODEL_TARGETS = ("gpt-5.6-sol", "grok-4.6")


def _controls() -> Mapping[str, Sequence[str]]:
    controls = CONTRACT["candidate_space"]["controls"]
    if not isinstance(controls, Mapping) or tuple(controls) != FACTOR_NAMES:
        raise ValueError("HANNA harness candidate controls drifted")
    return controls


def _require_factors(factors: Mapping[str, str]) -> dict[str, str]:
    candidate = dict(factors)
    if candidate not in legal_factor_tuples():
        raise ValueError("HANNA harness candidate factors are outside the legal universe")
    return candidate


def legal_factor_tuples() -> list[dict[str, str]]:
    """Enumerate the frozen 3*2*2*3 control universe with stdlib only."""
    controls = _controls()
    return [
        dict(zip(FACTOR_NAMES, values, strict=True))
        for values in itertools.product(*(controls[name] for name in FACTOR_NAMES))
    ]


def validate_authoritative_split(*, frozen_successor_path: Path, hanna_csv_path: Path) -> str:
    """Re-use the source-bound study derivation; no caller-supplied split is accepted."""
    split = derive_split_manifest(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    validate_split_manifest(split, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    return sha256(split)


def rendered_instruction_bytes(factors: Mapping[str, str]) -> bytes:
    factors = _require_factors(factors)
    wording = (
        "Assess the supplied writing using the fixed six HANNA dimensions.\n"
        f"Construct framing: {factors['construct_framing']}.\n"
        f"Scope/materiality: {factors['scope_materiality']}.\n"
        f"Missing evidence policy: {factors['missing_evidence_not_no']}.\n"
        f"Human-reference presentation: {factors['human_reference_variant']}.\n"
        "Use the immutable CWR mapping and response schema committed in the profile.\n"
        "Return no demonstrations, examples, or unstated scoring dimensions.\n"
    )
    return wording.encode("utf-8")


def rendered_profile_bytes(factors: Mapping[str, str]) -> bytes:
    factors = _require_factors(factors)
    parent = CONTRACT["parents"]["fresh88_primary"]
    space = CONTRACT["candidate_space"]
    return canonical({
        "format_version": 1,
        "study_id": STUDY_ID,
        "factors": factors,
        "instruction_sha256": hashlib.sha256(rendered_instruction_bytes(factors)).hexdigest(),
        "fixed_mapping": space["fixed_mapping"],
        "dimension_weights": space["fixed_dimension_weights"],
        "demonstrations": 0,
        "sampler": SAMPLER,
        "same_bytes_for_models": list(MODEL_TARGETS),
        "immutable_cwr_commitments": {
            "execution_contract_sha256": parent["execution_contract_sha256"],
            "runtime_source_manifest_sha256": parent["runtime_source_manifest_sha256"],
            "mapping_sets_sha256": parent["mapping_sets_sha256"],
            "baseline_control_profile_sha256": space["baseline_control_profile_sha256"],
            "response_schema": {"format_version": 1, "dimensions": list(DIMENSIONS), "score_type": "finite_numeric_per_dimension"},
        },
    })


def candidate_record(factors: Mapping[str, str]) -> dict[str, Any]:
    factors = _require_factors(factors)
    instruction = rendered_instruction_bytes(factors)
    profile = rendered_profile_bytes(factors)
    commitment = {
        "instruction_sha256": hashlib.sha256(instruction).hexdigest(),
        "profile_sha256": hashlib.sha256(profile).hexdigest(),
    }
    digest = hashlib.sha256(canonical(commitment)).hexdigest()
    return {
        "candidate_id": f"candidate-{digest[:16]}",
        "candidate_sha256": digest,
        "factors": factors,
        "instruction_bytes": instruction,
        "profile_bytes": profile,
        **commitment,
    }


def enumerate_balanced_candidates() -> list[dict[str, Any]]:
    """Derive six legal profiles with exact marginal balance for every factor."""
    controls = _controls()
    ordered = {
        name: sorted(values, key=lambda value: hashlib.sha256(f"628811:{name}:{value}".encode("utf-8")).hexdigest())
        for name, values in controls.items()
    }
    pattern = ((0, 0, 0, 0), (0, 1, 1, 1), (1, 0, 1, 2), (1, 1, 0, 0), (2, 0, 0, 1), (2, 1, 1, 2))
    records = sorted((candidate_record({name: ordered[name][indices[position]] for position, name in enumerate(FACTOR_NAMES)}) for indices in pattern), key=lambda row: row["candidate_id"])
    if len({row["candidate_id"] for row in records}) != 6:
        raise ValueError("HANNA harness candidate identities collided")
    return records


def candidate_set_sha256(candidates: Sequence[Mapping[str, Any]]) -> str:
    validate_candidates(candidates)
    projection = [{key: row[key] for key in ("candidate_id", "candidate_sha256", "factors", "instruction_sha256", "profile_sha256")} for row in candidates]
    return sha256(projection)


def validate_candidates(candidates: Sequence[Mapping[str, Any]]) -> None:
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or len(candidates) != 6:
        raise ValueError("HANNA harness requires exactly six candidates")
    expected = enumerate_balanced_candidates()
    if len(candidates) != len(expected):
        raise ValueError("HANNA harness candidates are not the frozen balanced derivation")
    for observed, derived in zip(candidates, expected, strict=True):
        if not isinstance(observed, Mapping) or dict(observed) != derived:
            raise ValueError("HANNA harness candidates are not the frozen balanced derivation")


def candidate_bytes_for_model(candidate: Mapping[str, Any], model: str) -> tuple[bytes, bytes]:
    """Expose the same committed instruction/profile pair for either planned model."""
    if model not in MODEL_TARGETS:
        raise ValueError("HANNA harness model target is invalid")
    if not isinstance(candidate, Mapping):
        raise ValueError("HANNA harness candidate is invalid")
    expected = next((row for row in enumerate_balanced_candidates() if row["candidate_id"] == candidate.get("candidate_id")), None)
    if expected is None or dict(candidate) != expected:
        raise ValueError("HANNA harness candidate is not the frozen derivation")
    return expected["instruction_bytes"], expected["profile_bytes"]


def _validated_authoritative_inputs(*, frozen_successor_path: Path, hanna_csv_path: Path, candidates: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
    validate_candidates(candidates)
    split = derive_split_manifest(frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    validate_split_manifest(split, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    eligible = derive_eligible_map(frozen_successor_path, hanna_csv_path)
    validate_eligible_map(eligible, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    return [dict(row) for row in candidates], split, eligible


def dspy_candidate_wording_adapter_contract() -> dict[str, Any]:
    return {
        "optional": True,
        "development_only": True,
        "runtime_dependency": False,
        "input": "authoritative_train_item_map_and_frozen_candidates",
        "output": "deterministic_train_only_examples_with_pinned_human_targets",
        "dspy_signature": {
            "inputs": ["candidate_instruction", "candidate_profile", "prompt", "story"],
            "targets": list(DIMENSIONS),
        },
        "metric": {
            "name": "six_dimension_mean_absolute_error",
            "direction": "minimize",
            "purpose": "development_training_diagnostic_only",
        },
        "provider_or_model_call": False,
        "selection_authority": "none",
    }


def _pinned_human_targets(*, hanna_csv_path: Path, eligible: Sequence[Mapping[str, str]]) -> dict[str, dict[str, Any]]:
    raw = _read_bytes_checked(Path(hanna_csv_path))
    if hashlib.sha256(raw).hexdigest() != CONTRACT["dataset"]["csv_sha256"]:
        raise ValueError("HANNA harness pinned CSV hash drifted")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("HANNA harness pinned CSV cannot be read") from exc
    fields = {
        "Story ID", "Prompt", "Human", "Story", "Model", *DIMENSIONS,
        "Worker ID", "Assignment ID", "Work time in seconds", "Name",
    }
    if not rows or set(rows[0]) != fields:
        raise ValueError("HANNA harness pinned CSV schema drifted")
    by_story: dict[str, list[Mapping[str, str]]] = {}
    for row in rows:
        story_id = row.get("Story ID")
        if not isinstance(story_id, str):
            raise ValueError("HANNA harness pinned CSV story identifier is invalid")
        by_story.setdefault(story_id, []).append(row)
    targets: dict[str, dict[str, Any]] = {}
    for item in eligible:
        rows_for_story = by_story.get(item["story_id"], [])
        if len(rows_for_story) != 3 or any(row.get("Model") != item["source_model"] for row in rows_for_story):
            raise ValueError("HANNA harness source story rows drifted")
        prompts = {row.get("Prompt") for row in rows_for_story}
        stories = {row.get("Story") for row in rows_for_story}
        if len(prompts) != 1 or len(stories) != 1 or not all(isinstance(value, str) and value for value in (*prompts, *stories)):
            raise ValueError("HANNA harness source prose rows drifted")
        prompt = next(iter(prompts))
        if hashlib.sha256(prompt.encode("utf-8")).hexdigest() != item["prompt_sha256"]:
            raise ValueError("HANNA harness source prompt binding drifted")
        target = {}
        for dimension in DIMENSIONS:
            values = []
            for row in rows_for_story:
                try:
                    value = float(row[dimension])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("HANNA harness human reference target is invalid") from exc
                finite(value, low=1.0, high=5.0, label="human reference target")
                values.append(value)
            target[dimension] = sum(values) / len(values)
        targets[item["item_id"]] = {"prompt": prompt, "story": next(iter(stories)), "target": target, "rating_count": len(rows_for_story)}
    if set(targets) != {row["item_id"] for row in eligible}:
        raise ValueError("HANNA harness source target coverage drifted")
    return targets


def dspy_train_only_examples(*, frozen_successor_path: Path, hanna_csv_path: Path, candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Freeze DSPy-shaped train examples without importing DSPy or exposing held-out partitions."""
    candidates, split, eligible = _validated_authoritative_inputs(
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
        candidates=candidates,
    )
    partitions = {row["item_id"]: row["partition"] for row in split["items"]}
    train_items = [row for row in eligible if partitions.get(row["item_id"]) == "train"]
    if len(train_items) != 48 or any(partitions.get(row["item_id"]) != "train" for row in train_items):
        raise ValueError("HANNA harness train-only DSPy projection drifted")
    targets = _pinned_human_targets(hanna_csv_path=hanna_csv_path, eligible=train_items)
    examples = []
    for candidate in candidates:
        for item in train_items:
            source = targets[item["item_id"]]
            inputs = {
                "candidate_instruction": candidate["instruction_bytes"].decode("utf-8"),
                "candidate_profile": candidate["profile_bytes"].decode("utf-8"),
                "prompt": source["prompt"],
                "story": source["story"],
            }
            target = dict(source["target"])
            binding = {"candidate_id": candidate["candidate_id"], "item_id": item["item_id"], "input_sha256": hashlib.sha256(canonical(inputs)).hexdigest(), "target_sha256": hashlib.sha256(canonical(target)).hexdigest()}
            examples.append({
                "example_id": "dspy-train-" + hashlib.sha256(canonical(binding)).hexdigest()[:16],
                "study_id": STUDY_ID,
                "partition": "train",
                "candidate_id": candidate["candidate_id"],
                "candidate_sha256": candidate["candidate_sha256"],
                "item_id": item["item_id"],
                "prompt_group_id": item["prompt_group_id"],
                "input": inputs,
                "target": target,
                "input_sha256": binding["input_sha256"],
                "target_sha256": binding["target_sha256"],
                "rating_count": source["rating_count"],
                "selection_authority": "none",
            })
    if len(examples) != len(candidates) * len(train_items) or any(row["partition"] != "train" for row in examples):
        raise ValueError("HANNA harness train-only DSPy example geometry drifted")
    return examples


def optuna_explore_legal_tuples(*, n_trials: int) -> list[dict[str, str]]:
    """Optionally explore legal factors locally without accepting a score, result, or selection."""
    if not isinstance(n_trials, int) or isinstance(n_trials, bool) or n_trials < 1:
        raise ValueError("HANNA harness Optuna trial count is invalid")
    try:
        optuna = importlib.import_module("optuna")
    except ImportError as exc:
        raise RuntimeError("Optuna is optional and is not installed") from exc
    controls = _controls()
    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=628811))

    def propose(trial: Any) -> float:
        factors = {name: trial.suggest_categorical(name, list(controls[name])) for name in FACTOR_NAMES}
        _require_factors(factors)
        return 0.0

    study.optimize(propose, n_trials=n_trials)
    return [{name: trial.params[name] for name in FACTOR_NAMES} for trial in study.trials]
