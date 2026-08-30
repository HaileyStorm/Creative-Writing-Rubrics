#!/usr/bin/env python3
"""Balanced, development-only Optuna/DSPy analysis over a frozen verifier projection."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-lean-development-balanced-v1"
CONTRACT_PATH = HERE / "study-contract.json"
BALANCED_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-training-balanced-v1" / "verifier.py"
BALANCED_SHA256 = "c65953bb8b0e0b9aae52c5a65418c265b3e9898bfa916b8aca01d354f087caea"
BALANCED_CONTRACT_PATH = BALANCED_PATH.with_name("study-contract.json")
BALANCED_CONTRACT_SHA256 = "b0382ecc6d95ee0c69e94ec9c960a204c99a57eb44cbffc1a5ef35f4b108a3ff"
DEVELOPMENT_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-lean-development-v1" / "optimizer.py"
DEVELOPMENT_SHA256 = "cbbf3b51a875ff4c0c1b72379e089cbd8f0a76cb2a0da5da74f31a13b4de377f"
PROJECTION_KEYS = frozenset({
    "format_version", "study_id", "kind", "balanced_collection_evidence_sha256", "dependencies",
    "schedule_sha256", "stage", "observations", "human_targets", "geometry", "excluded_terminal",
    "confirmation", "provider_calls_made", "runtime_authority", "projection_sha256",
})
CONTRACT_FIELDS = frozenset({"authority", "format_version", "geometry", "input", "kind", "optimizer", "parent", "study_id"})
CONTRACT_EXPECTED = {
    "authority": {"candidate_substitution": False, "confirmation": {"cells": 0, "status": "unopened"}, "provider_dispatch": False, "runtime": False},
    "format_version": 1,
    "geometry": {"candidates": 5, "grok": {"cells": 20, "items": 4, "prompt_groups": 4}, "sol_sprinkled": {"cells": 10, "items": 2, "prompt_groups": 2}},
    "input": "pinned_balanced_verifier_replay_plus_byte_identical_projection",
    "kind": "development_only_balanced_optuna_dspy_successor",
    "optimizer": {"dspy": "3.3.1_Predict_input_preparation_only", "objective": "minimize_0.8_grok_mae_plus_0.2_sol_mae_with_additive_coverage_and_request_penalties", "optuna": "4.9.0_GridSampler"},
    "parent": {"lean_development_optimizer_sha256": DEVELOPMENT_SHA256, "study_id": "hbq-human-alignment-optimizer-v4-lean-training-balanced-v1", "verifier_contract_sha256": BALANCED_CONTRACT_SHA256, "verifier_sha256": BALANCED_SHA256},
    "study_id": STUDY_ID,
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(value: Any) -> str:
    return sha256_bytes(canonical(value))


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError(f"HANNA balanced development path is reparsed: {path}")
    if directory is True and not stat.S_ISDIR(info.st_mode):
        raise ValueError(f"HANNA balanced development expected directory: {path}")
    if directory is False and not stat.S_ISREG(info.st_mode):
        raise ValueError(f"HANNA balanced development expected plain file: {path}")


def _stable_bytes(path: Path) -> bytes:
    absolute, current = Path(os.path.abspath(path)), Path(Path(os.path.abspath(path)).anchor)
    for part in absolute.parts[1:]:
        current /= part
        _plain(current)
    _plain(absolute, directory=False)
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError("HANNA balanced development file identity drifted")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
            raise ValueError("HANNA balanced development file changed during read")
    return raw


def _canonical_object(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = _stable_bytes(path)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA balanced development {label} is unavailable or invalid") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA balanced development {label} is noncanonical")
    return raw, value


def _load(path: Path, expected_sha256: str, name: str) -> ModuleType:
    raw = _stable_bytes(path)
    if sha256_bytes(raw) != expected_sha256:
        raise ValueError(f"HANNA balanced development pinned {path.name} bytes drifted")
    module = ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    if sha256_bytes(_stable_bytes(path)) != expected_sha256:
        raise ValueError(f"HANNA balanced development pinned {path.name} changed during load")
    return module


def _dependencies() -> tuple[ModuleType, ModuleType, ModuleType]:
    balanced = _load(BALANCED_PATH, BALANCED_SHA256, "_hanna_balanced_verifier")
    if sha256_bytes(_stable_bytes(BALANCED_CONTRACT_PATH)) != BALANCED_CONTRACT_SHA256:
        raise ValueError("HANNA balanced development pinned verifier contract drifted")
    balanced.contract()
    development = _load(DEVELOPMENT_PATH, DEVELOPMENT_SHA256, "_hanna_lean_development")
    native = development._load_native()
    return balanced, development, native


def contract() -> dict[str, Any]:
    _raw, value = _canonical_object(CONTRACT_PATH, label="study contract")
    if set(value) != CONTRACT_FIELDS or value != CONTRACT_EXPECTED:
        raise ValueError("HANNA balanced development contract fields or authority drifted")
    return value


def _output_dependencies() -> dict[str, str]:
    return {
        "balanced_optimizer_source_sha256": sha256_bytes(_stable_bytes(Path(__file__))),
        "balanced_optimizer_contract_sha256": sha256_bytes(_stable_bytes(CONTRACT_PATH)),
        "balanced_verifier_sha256": BALANCED_SHA256,
        "balanced_verifier_contract_sha256": BALANCED_CONTRACT_SHA256,
        "lean_development_optimizer_sha256": DEVELOPMENT_SHA256,
    }


def _validate_projection(projection: Mapping[str, Any]) -> None:
    if set(projection) != PROJECTION_KEYS:
        raise ValueError("HANNA balanced development accepts only the balanced verifier projection")
    body = dict(projection)
    digest = body.pop("projection_sha256", None)
    if digest != sha256(body):
        raise ValueError("HANNA balanced development projection hash drifted")
    if (
        projection.get("format_version") != 1
        or projection.get("study_id") != "hbq-human-alignment-optimizer-v4-lean-training-balanced-v1"
        or projection.get("kind") != "balanced_lean_training_optimizer_observation_projection"
        or projection.get("stage") != "training"
        or projection.get("provider_calls_made") != 0
        or projection.get("runtime_authority") != "none"
        or projection.get("confirmation") != {"status": "unopened", "cells": 0}
    ):
        raise ValueError("HANNA balanced development projection authority drifted")
    dependencies = projection.get("dependencies")
    if (
        not isinstance(dependencies, Mapping)
        or dependencies.get("balanced_verifier_source_sha256") != BALANCED_SHA256
        or dependencies.get("balanced_contract_sha256") != BALANCED_CONTRACT_SHA256
    ):
        raise ValueError("HANNA balanced development projection verifier binding drifted")
    if projection.get("geometry") != {"grok_prompt_groups": 4, "grok_candidates_per_group": 5, "grok_cells": 20, "sol_cells": 10, "total_cells": 30}:
        raise ValueError("HANNA balanced development projection geometry drifted")


def _verified_projection(*, balanced_projection_path: Path, balanced_collection_evidence_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[bytes, dict[str, Any], ModuleType, ModuleType, ModuleType]:
    supplied_raw, _supplied = _canonical_object(Path(balanced_projection_path), label="balanced verifier projection")
    balanced, development, native = _dependencies()
    replayed = balanced.verify_balanced_training_receipts(
        collection_evidence_path=Path(balanced_collection_evidence_path),
        frozen_successor_path=Path(frozen_successor_path),
        hanna_csv_path=Path(hanna_csv_path),
    )
    if not isinstance(replayed, dict) or supplied_raw != canonical(replayed):
        raise ValueError("HANNA balanced development supplied projection is not byte-identical to pinned verifier replay")
    _validate_projection(replayed)
    return supplied_raw, replayed, balanced, development, native


def _candidate_ids(observations: Sequence[Mapping[str, Any]]) -> list[str]:
    raw = {row.get("candidate_id") for row in observations}
    if len(raw) != 5 or any(not isinstance(candidate, str) for candidate in raw):
        raise ValueError("HANNA balanced development candidate geometry drifted")
    return sorted(raw)


def _validate_observations(projection: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]], list[str]]:
    observations = projection.get("observations")
    targets = projection.get("human_targets")
    if not isinstance(observations, list) or not isinstance(targets, Mapping):
        raise ValueError("HANNA balanced development projection observations are invalid")
    normalized = [dict(row) for row in observations if isinstance(row, Mapping)]
    if len(normalized) != 30 or len(normalized) != len(observations):
        raise ValueError("HANNA balanced development projection observations are incomplete")
    candidate_ids = _candidate_ids(normalized)
    contacts: set[tuple[str, str, str]] = set()
    routes = {"grok_primary": [], "sol_validation": []}
    for row in normalized:
        route_name, identity = row.get("route_name"), row.get("identity")
        if route_name not in routes or not isinstance(identity, Mapping):
            raise ValueError("HANNA balanced development projection route or identity is invalid")
        contact = (identity.get("provider"), identity.get("contact_id"), identity.get("session_id"))
        if not all(isinstance(value, str) and value for value in contact) or contact in contacts:
            raise ValueError("HANNA balanced development projection contact identity drifted")
        contacts.add(contact); routes[route_name].append(row)
    grok, sol = routes["grok_primary"], routes["sol_validation"]
    if len(grok) != 20 or len(sol) != 10:
        raise ValueError("HANNA balanced development route geometry drifted")
    for route, rows, expected_items, expected_groups in (("grok_primary", grok, 4, 4), ("sol_validation", sol, 2, 2)):
        if len({row.get("item_id") for row in rows}) != expected_items or len({row.get("prompt_group_id") for row in rows}) != expected_groups:
            raise ValueError("HANNA balanced development item/group geometry drifted")
        if {row.get("candidate_id") for row in rows} != set(candidate_ids):
            raise ValueError("HANNA balanced development candidate substitution is forbidden")
        for candidate_id in candidate_ids:
            selected = [row for row in rows if row.get("candidate_id") == candidate_id]
            if len(selected) != expected_items:
                raise ValueError("HANNA balanced development candidate endpoint is incomplete")
    target_rows = {row.get("item_id") for row in normalized}
    if set(targets) != target_rows or any(not isinstance(value, Mapping) for value in targets.values()):
        raise ValueError("HANNA balanced development human target geometry drifted")
    return normalized, {str(key): dict(value) for key, value in targets.items()}, candidate_ids


def _endpoints(_development: ModuleType, native: ModuleType, observations: Sequence[Mapping[str, Any]], targets: Mapping[str, Mapping[str, float]], candidate_ids: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
    """Keep descriptive Spearman nulls; selection uses defined error and coverage fields."""
    v2 = native._load_v3().v2_module()
    result: dict[str, list[dict[str, Any]]] = {}
    for name, route_name, expected_items, expected_groups in (
        ("grok", "grok_primary", 4, 4),
        ("sol_sprinkled", "sol_validation", 2, 2),
    ):
        rows_for_route = [row for row in observations if row["route_name"] == route_name]
        endpoints = []
        for candidate_id in candidate_ids:
            rows = [row for row in rows_for_route if row["candidate_id"] == candidate_id]
            endpoint = v2._candidate_endpoint(rows, targets, expected_items=expected_items, expected_groups=expected_groups)
            if not isinstance(endpoint.get("mean_absolute_error"), (int, float)) or not isinstance(endpoint.get("mean_coverage"), (int, float)):
                raise ValueError("HANNA balanced development endpoint error or coverage is undefined")
            endpoints.append({"candidate_id": candidate_id, "endpoint": endpoint, "mean_request_bytes": sum(float(row["request_bytes"]) for row in rows) / len(rows)})
        result[name] = endpoints
    return result


def _optuna() -> Any:
    try:
        import optuna  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("HANNA balanced development requires Optuna 4.9.0") from error
    if optuna.__version__ != "4.9.0":
        raise ValueError("HANNA balanced development Optuna version drifted")
    return optuna


def optimize_balanced_projection(*, balanced_projection_path: Path, balanced_collection_evidence_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, seed: int = 20260830) -> dict[str, Any]:
    """Recompute from a byte-identical replay of the pinned balanced verifier."""
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("HANNA balanced development Optuna seed is invalid")
    contract()
    raw, projection, _balanced, development, native = _verified_projection(
        balanced_projection_path=Path(balanced_projection_path), balanced_collection_evidence_path=Path(balanced_collection_evidence_path),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path),
    )
    observations, targets, candidate_ids = _validate_observations(projection)
    endpoints = _endpoints(development, native, observations, targets, candidate_ids)
    grok = {row["candidate_id"]: row for row in endpoints["grok"]}
    sol = {row["candidate_id"]: row for row in endpoints["sol_sprinkled"]}
    optuna = _optuna()
    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.GridSampler({"candidate_id": candidate_ids}, seed=seed))

    def objective(trial: Any) -> float:
        candidate_id = trial.suggest_categorical("candidate_id", candidate_ids)
        grok_error = float(grok[candidate_id]["endpoint"]["mean_absolute_error"])
        sol_error = float(sol[candidate_id]["endpoint"]["mean_absolute_error"])
        grok_coverage = float(grok[candidate_id]["endpoint"]["mean_coverage"])
        request_bytes = float(grok[candidate_id]["mean_request_bytes"])
        value = 0.8 * grok_error + 0.2 * sol_error + (1.0 - grok_coverage) / 1_000_000.0 + request_bytes / 1_000_000_000_000.0
        trial.set_user_attr("grok_mean_absolute_error", grok_error)
        trial.set_user_attr("sol_sprinkled_mean_absolute_error", sol_error)
        trial.set_user_attr("grok_mean_coverage", grok_coverage)
        trial.set_user_attr("mean_grok_request_bytes", request_bytes)
        return value

    study.optimize(objective, n_trials=5, catch=())
    best = study.best_trial
    result = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "balanced_development_only_optuna_result",
        "balanced_projection_sha256": sha256_bytes(raw), "balanced_projection_result_sha256": projection["projection_sha256"],
        "dependencies": _output_dependencies(),
        "schedule_sha256": projection["schedule_sha256"], "seed": seed, "optimizer": "optuna.GridSampler@4.9.0",
        "objective": "minimize_0.8_grok_mean_absolute_error_plus_0.2_sol_sprinkled_mean_absolute_error_plus_additive_grok_coverage_penalty_1e-6_plus_additive_request_byte_penalty_1e-12",
        "endpoints": endpoints, "frozen_candidate_id": best.params["candidate_id"],
        "best_trial": {"number": best.number, "objective": best.value, "grok_mean_absolute_error": best.user_attrs["grok_mean_absolute_error"], "sol_sprinkled_mean_absolute_error": best.user_attrs["sol_sprinkled_mean_absolute_error"], "grok_mean_coverage": best.user_attrs["grok_mean_coverage"]},
        "geometry": projection["geometry"], "excluded_terminal": projection["excluded_terminal"],
        "candidate_substitution": "forbidden", "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none", "provider_calls_made": 0,
    }
    result["result_sha256"] = sha256(result)
    return result


def _parent_descriptor(native: ModuleType, result: Mapping[str, Any]) -> dict[str, str]:
    candidate_id = result.get("frozen_candidate_id")
    parents = [candidate for candidate in native._load_v3().candidate_pack() if candidate.get("candidate_id") == candidate_id]
    if len(parents) != 1:
        raise ValueError("HANNA balanced development frozen parent candidate drifted")
    parent = parents[0]
    instruction, profile = parent.get("instruction_bytes"), parent.get("profile_bytes")
    if (
        not isinstance(candidate_id, str)
        or not isinstance(parent.get("candidate_sha256"), str)
        or not isinstance(instruction, bytes)
        or not isinstance(profile, bytes)
        or sha256_bytes(instruction) != parent.get("instruction_sha256")
        or sha256_bytes(profile) != parent.get("profile_sha256")
    ):
        raise ValueError("HANNA balanced development frozen parent bytes drifted")
    return {
        "candidate_id": candidate_id,
        "candidate_sha256": parent["candidate_sha256"],
        "instruction_base64": base64.b64encode(instruction).decode("ascii"),
        "instruction_sha256": sha256_bytes(instruction),
        "profile_base64": base64.b64encode(profile).decode("ascii"),
        "profile_sha256": sha256_bytes(profile),
    }


def training_diagnostics(*, balanced_projection_path: Path, balanced_collection_evidence_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, seed: int = 20260830) -> dict[str, Any]:
    result = optimize_balanced_projection(
        balanced_projection_path=Path(balanced_projection_path), balanced_collection_evidence_path=Path(balanced_collection_evidence_path),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), seed=seed,
    )
    _balanced, _development, native = _dependencies()
    diagnostics = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "balanced_verified_optuna_training_diagnostics",
        "training_result_sha256": result["result_sha256"], "optimizer": result["optimizer"], "seed": seed,
        "best_trial": result["best_trial"], "endpoints": result["endpoints"], "geometry": result["geometry"],
        "parent": _parent_descriptor(native, result),
        "dependencies": _output_dependencies(), "training_result_dependencies_sha256": sha256(result["dependencies"]),
        "confirmation": {"status": "unopened", "cells": 0}, "runtime_authority": "none",
    }
    diagnostics["diagnostics_sha256"] = sha256(diagnostics)
    return {"training_result": result, "training_result_bytes": canonical(result), "training_diagnostics": diagnostics, "training_diagnostics_bytes": canonical(diagnostics)}


def load_dspy() -> Any:
    try:
        import dspy  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("HANNA balanced development requires DSPy 3.3.1") from error
    if dspy.__version__ != "3.3.1":
        raise ValueError("HANNA balanced development DSPy version drifted")
    return dspy


def _decode(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"HANNA balanced development {label} is not base64")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise ValueError(f"HANNA balanced development {label} is not base64") from error


def prepare_dspy_descendant_inputs(*, balanced_projection_path: Path, balanced_collection_evidence_path: Path, frozen_successor_path: Path, hanna_csv_path: Path, seed: int = 20260830) -> dict[str, Any]:
    """Construct exact DSPy inputs locally; a governed successor owns any invocation."""
    dspy = load_dspy()

    class BalancedDescendantSignature(dspy.Signature):
        parent_candidate_id: str = dspy.InputField()
        parent_instruction_base64: str = dspy.InputField()
        parent_profile_base64: str = dspy.InputField()
        training_result_base64: str = dspy.InputField()
        training_diagnostics_base64: str = dspy.InputField()
        descendant_instruction_base64: str = dspy.OutputField()
        descendant_profile_base64: str = dspy.OutputField()

    dspy.Predict(BalancedDescendantSignature)
    context = training_diagnostics(
        balanced_projection_path=Path(balanced_projection_path), balanced_collection_evidence_path=Path(balanced_collection_evidence_path),
        frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), seed=seed,
    )
    result, diagnostics = context["training_result"], context["training_diagnostics"]
    parent = diagnostics.get("parent")
    if not isinstance(parent, Mapping) or set(parent) != {"candidate_id", "candidate_sha256", "instruction_base64", "instruction_sha256", "profile_base64", "profile_sha256"}:
        raise ValueError("HANNA balanced development DSPy parent descriptor is invalid")
    instruction = _decode(parent["instruction_base64"], label="DSPy parent instruction")
    profile = _decode(parent["profile_base64"], label="DSPy parent profile")
    if (
        parent.get("candidate_id") != result.get("frozen_candidate_id")
        or sha256_bytes(instruction) != parent.get("instruction_sha256")
        or sha256_bytes(profile) != parent.get("profile_sha256")
    ):
        raise ValueError("HANNA balanced development DSPy parent descriptor drifted")
    inputs = {
        "parent_candidate_id": parent["candidate_id"], "parent_instruction_base64": parent["instruction_base64"],
        "parent_profile_base64": parent["profile_base64"],
        "training_result_base64": base64.b64encode(context["training_result_bytes"]).decode("ascii"),
        "training_diagnostics_base64": base64.b64encode(context["training_diagnostics_bytes"]).decode("ascii"),
    }
    prepared = {
        "format_version": 1, "study_id": STUDY_ID, "kind": "dspy_predict_input_preparation",
        "dspy_program": "Predict(BalancedDescendantSignature)@3.3.1", "inputs": inputs,
        "inputs_sha256": sha256_bytes(canonical(inputs)), "training_result_sha256": result["result_sha256"],
        "training_diagnostics_sha256": diagnostics["diagnostics_sha256"], "dependencies": _output_dependencies(), "provider_calls_made": 0,
        "dispatch_authority": "none_governed_executor_required", "runtime_authority": "none",
        "confirmation": {"status": "unopened", "cells": 0},
    }
    prepared["preparation_sha256"] = sha256(prepared)
    return prepared
