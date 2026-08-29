#!/usr/bin/env python3
"""Development-only deterministic Optuna search over frozen v3 training evidence."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import json
import statistics
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v3" / "study.py"
V4_NATIVE_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-v1" / "executor.py"
STUDY_ID = "hbq-human-alignment-optimizer-v4-development-optimizer-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
CELL_KEYS = {"cell_id", "parent_cell_id", "candidate_id", "task_payload_sha256", "prompt_binding_sha256", "route_name", "route_sha256", "native_request_base64", "native_response_base64", "native_identity"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256(value: Any) -> str:
    return sha256_bytes(canonical(value))


def _load_v3() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_hanna_v4_development_parent", V3_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA v4 cannot load v3")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.contract()
    return module


def _load_native() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_hanna_v4_native_parent", V4_NATIVE_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA v4 native-subscription successor is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _training_rows(schedule: Mapping[str, Any]) -> list[dict[str, Any]]:
    pool = schedule.get("optional_training_pool")
    rows = pool.get("cells") if isinstance(pool, Mapping) else None
    if not isinstance(rows, list) or len(rows) != 360 or sum(row["route_name"] == "grok_primary" for row in rows) != 240 or sum(row["route_name"] == "sol_validation" for row in rows) != 120:
        raise ValueError("HANNA v4 frozen v3 training geometry drifted")
    if any(row["partition"] != "train" for row in rows) or len({row["cell_id"] for row in rows}) != 360:
        raise ValueError("HANNA v4 train/dev/confirmation separation drifted")
    return rows


def _targets(*, v3: ModuleType, rows: Sequence[Mapping[str, Any]], frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, dict[str, float]]:
    parent_study = v3.v2_module().parent_modules()[0]
    eligible = parent_study.derive_eligible_map(Path(frozen_successor_path), Path(hanna_csv_path))
    wanted = {row["item_id"] for row in rows}
    source = {row["item_id"]: row for row in eligible if row["item_id"] in wanted}
    if len(wanted) != 48 or set(source) != wanted:
        raise ValueError("HANNA v4 training target IDs drifted")
    by_story = {row["story_id"]: row["item_id"] for row in source.values()}
    ratings: dict[str, list[Mapping[str, str]]] = {item_id: [] for item_id in wanted}
    with Path(hanna_csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for record in csv.DictReader(handle):
            item_id = by_story.get(record.get("Story ID", ""))
            if item_id is not None:
                ratings[item_id].append(record)
    result: dict[str, dict[str, float]] = {}
    for item_id, item in source.items():
        records = ratings[item_id]
        if len(records) != 3 or any(record.get("Model") != item["source_model"] for record in records):
            raise ValueError("HANNA v4 training ratings drifted")
        result[item_id] = {dimension: statistics.fmean(float(record[dimension]) for record in records) for dimension in DIMENSIONS}
    return result


def _decode(value: Any, *, label: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError(f"HANNA v4 {label} is not base64")
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as error:
        raise ValueError(f"HANNA v4 {label} is not base64") from error


def _load_pinned_evidence_verifier() -> Any:
    """Private trust seam for persisted native-subscription prepared/contact evidence."""
    raise ValueError("HANNA v4 has no enabled persisted-native evidence verifier")


def _prompt_binding(row: Mapping[str, Any]) -> str:
    fields = ("task_payload_sha256", "candidate_instruction_sha256", "candidate_profile_sha256", "response_schema_sha256", "prompt_sha256", "story_sha256")
    return sha256({field: row[field] for field in fields})


def _expected_attestation(*, row: Mapping[str, Any], request: bytes, response: bytes) -> dict[str, Any]:
    request_sha = sha256_bytes(request)
    return {
        "accepted": True,
        "native_request_sha256": request_sha,
        "native_response_sha256": sha256_bytes(response),
        "prompt_binding_sha256": _prompt_binding(row),
        "exact_request_binding_sha256": sha256({"cell_id": row["cell_id"], "prompt_binding_sha256": _prompt_binding(row), "native_request_sha256": request_sha}),
    }


def _validate_evidence(*, evidence_path: Path, schedule: Mapping[str, Any], native: ModuleType, v3: ModuleType, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    payload = Path(evidence_path).read_bytes()
    try:
        evidence = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA v4 training evidence is invalid") from error
    if not isinstance(evidence, dict) or canonical(evidence) != payload:
        raise ValueError("HANNA v4 training evidence is noncanonical")
    if set(evidence) != {"format_version", "study_id", "kind", "v4_native_schedule_sha256", "cells"} or evidence["format_version"] != 1 or evidence["study_id"] != STUDY_ID or evidence["kind"] != "verified_persisted_v4_native_subscription_training_cells" or evidence["v4_native_schedule_sha256"] != schedule["schedule_sha256"]:
        raise ValueError("HANNA v4 training evidence identity drifted")
    rows = _training_rows(schedule)
    cells = evidence["cells"]
    if not isinstance(cells, list) or len(cells) != len(rows):
        raise ValueError("HANNA v4 requires all and only frozen v3 training cells")
    if any(not isinstance(cell, Mapping) or set(cell) != CELL_KEYS for cell in cells):
        raise ValueError("HANNA v4 caller aggregates or synthetic cell shapes are rejected")
    if [cell.get("cell_id") if isinstance(cell, Mapping) else None for cell in cells] != [row["cell_id"] for row in rows]:
        raise ValueError("HANNA v4 training cell order/binding drifted")
    observations: list[dict[str, Any]] = []
    contacts: set[tuple[str, str, str, str]] = set()
    for supplied, row in zip(cells, rows, strict=True):
        for field in ("cell_id", "parent_cell_id", "candidate_id", "task_payload_sha256", "route_name"):
            if supplied[field] != row[field]:
                raise ValueError("HANNA v4 native cell is misassociated with frozen v4 route row")
        if supplied["prompt_binding_sha256"] != _prompt_binding(row) or supplied["route_sha256"] != sha256(row["route"]):
            raise ValueError("HANNA v4 frozen prompt or route binding drifted")
        request, response = _decode(supplied["native_request_base64"], label="native request"), _decode(supplied["native_response_base64"], label="native response")
        identity = supplied["native_identity"]
        identity = native._validate_identity(identity, row)
        contact = (identity["provider"], identity["contact_id"], identity["session_id"])
        if contact in contacts:
            raise ValueError("HANNA v4 duplicate native contact identity")
        contacts.add(contact)
        expected = _expected_attestation(row=row, request=request, response=response)
        attestation = _load_pinned_evidence_verifier()({"evidence_path": str(evidence_path), "cell": dict(row), "native_request_bytes": request, "native_response_bytes": response, "native_identity": identity, "expected": expected})
        external_hashes = {"prepared_sha256", "intent_sha256", "result_sha256"}
        if (not isinstance(attestation, Mapping) or set(attestation) != set(expected) | external_hashes
                or any(attestation[key] != expected[key] for key in expected)
                or any(not isinstance(attestation[key], str) or len(attestation[key]) != 64 or any(char not in "0123456789abcdef" for char in attestation[key]) for key in external_hashes)):
            raise ValueError("HANNA v4 persisted native evidence verifier rejected or failed exact prepared/contact/request/response attestation")
        scores, coverage = native._extract_native(response, row=row, identity=identity)
        observations.append({**row, "scores": scores, "coverage": coverage, "native_request_bytes": len(request), "native_response_sha256": sha256_bytes(response)})
    return observations, _targets(v3=v3, rows=rows, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))


def _candidate_metrics(*, observations: Sequence[Mapping[str, Any]], targets: Mapping[str, Mapping[str, float]], v3: ModuleType) -> dict[str, Any]:
    v2 = v3.v2_module()
    result: dict[str, Any] = {}
    for route_name, expected_items, expected_groups in (("grok_primary", 48, 24), ("sol_validation", 24, 24)):
        per_candidate = []
        for candidate in v3.candidate_pack():
            rows = [row for row in observations if row["route_name"] == route_name and row["candidate_id"] == candidate["candidate_id"]]
            endpoint = v2._candidate_endpoint(rows, targets, expected_items=expected_items, expected_groups=expected_groups)
            if endpoint["macro_spearman"] is None:
                raise ValueError("HANNA v4 train endpoint has undefined correlation")
            per_candidate.append({"candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "train": endpoint, "mean_native_request_bytes": statistics.fmean(float(row["native_request_bytes"]) for row in rows)})
        result[route_name] = per_candidate
    return result


def load_dspy_proposer() -> Any:
    """Development-only optional adapter. It is never loaded by evaluation/runtime code."""
    try:
        import dspy  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("HANNA v4 DSPy development adapter is not installed") from error
    return dspy


def build_dspy_frozen_candidate_proposer() -> Any:
    """Construct a local-only DSPy proposal shape; it never configures or calls an LM."""
    dspy = load_dspy_proposer()

    class FrozenTrainingDescendantSignature(dspy.Signature):
        """Version a descendant from exact parent bytes and frozen training diagnostics."""
        parent_candidate_id: str = dspy.InputField()
        parent_instruction_bytes_base64: str = dspy.InputField()
        parent_profile_bytes_base64: str = dspy.InputField()
        parent_instruction_sha256: str = dspy.InputField()
        parent_profile_sha256: str = dspy.InputField()
        frozen_training_diagnostics_json: str = dspy.InputField()
        descendant_instruction_bytes_base64: str = dspy.OutputField()
        descendant_profile_bytes_base64: str = dspy.OutputField()
        descendant_candidate_sha256: str = dspy.OutputField()

    class FrozenTrainingCandidateProposer(dspy.Module):
        signature = FrozenTrainingDescendantSignature

        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(FrozenTrainingDescendantSignature)

        @staticmethod
        def _inputs(*, parent: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
            required_parent = {"candidate_id", "candidate_sha256", "instruction_bytes", "profile_bytes", "instruction_sha256", "profile_sha256"}
            if not isinstance(parent, Mapping) or not required_parent <= set(parent) or not isinstance(parent["instruction_bytes"], bytes) or not isinstance(parent["profile_bytes"], bytes):
                raise ValueError("HANNA v4 DSPy proposer parent bytes are invalid")
            if not isinstance(diagnostics, Mapping) or set(diagnostics) != {"native_training_evidence_sha256", "endpoint_sha256", "train_partition"} or diagnostics["train_partition"] != "train":
                raise ValueError("HANNA v4 DSPy proposer diagnostics are not frozen training-only inputs")
            if sha256_bytes(parent["instruction_bytes"]) != parent["instruction_sha256"] or sha256_bytes(parent["profile_bytes"]) != parent["profile_sha256"]:
                raise ValueError("HANNA v4 DSPy proposer parent byte commitments drifted")
            diagnostic_sha = sha256(dict(diagnostics))
            return ({
                "parent_candidate_id": parent["candidate_id"],
                "parent_instruction_bytes_base64": base64.b64encode(parent["instruction_bytes"]).decode("ascii"),
                "parent_profile_bytes_base64": base64.b64encode(parent["profile_bytes"]).decode("ascii"),
                "parent_instruction_sha256": parent["instruction_sha256"],
                "parent_profile_sha256": parent["profile_sha256"],
                "frozen_training_diagnostics_json": canonical(dict(diagnostics)).decode("utf-8"),
            }, diagnostic_sha)

        @staticmethod
        def _validated_output(*, parent: Mapping[str, Any], diagnostics: Mapping[str, Any], diagnostic_sha: str, inputs: Mapping[str, Any], prediction: Any) -> dict[str, Any]:
            fields = ("descendant_instruction_bytes_base64", "descendant_profile_bytes_base64", "descendant_candidate_sha256")
            values = {field: getattr(prediction, field, None) for field in fields}
            if any(not isinstance(value, str) for value in values.values()):
                raise ValueError("HANNA v4 DSPy prediction outputs are incomplete")
            try:
                instruction = base64.b64decode(values["descendant_instruction_bytes_base64"].encode("ascii"), validate=True)
                proposed_profile_bytes = base64.b64decode(values["descendant_profile_bytes_base64"].encode("ascii"), validate=True)
                proposed_profile = json.loads(proposed_profile_bytes.decode("utf-8"))
            except (UnicodeEncodeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("HANNA v4 DSPy prediction outputs are not valid versionable bytes") from error
            if not instruction or instruction == parent["instruction_bytes"] or not isinstance(proposed_profile, dict):
                raise ValueError("HANNA v4 DSPy prediction did not propose a distinct instruction/profile")
            proposed_candidate_sha = sha256({"parent_candidate_sha256": parent["candidate_sha256"], "instruction_sha256": sha256_bytes(instruction), "profile_sha256": sha256_bytes(proposed_profile_bytes), "diagnostics_sha256": diagnostic_sha})
            if values["descendant_candidate_sha256"] != proposed_candidate_sha:
                raise ValueError("HANNA v4 DSPy proposed candidate hash is misbound")
            profile = {
                "format_version": 1,
                "candidate_kind": "dspy_predict_training_descendant",
                "parent": {"candidate_id": parent["candidate_id"], "candidate_sha256": parent["candidate_sha256"], "instruction_sha256": parent["instruction_sha256"], "profile_sha256": parent["profile_sha256"]},
                "frozen_training_diagnostics": dict(diagnostics),
                "proposed_profile_sha256": sha256_bytes(proposed_profile_bytes),
                "proposed_candidate_sha256": proposed_candidate_sha,
                "dspy_program": "Predict(FrozenTrainingDescendantSignature)",
                "runtime_authority": "none",
            }
            profile_bytes = canonical(profile)
            candidate_sha = sha256({"parent_candidate_sha256": parent["candidate_sha256"], "instruction_sha256": sha256_bytes(instruction), "profile_sha256": sha256_bytes(profile_bytes), "diagnostics_sha256": diagnostic_sha})
            return {
                **dict(inputs),
                "descendant_instruction_bytes_base64": base64.b64encode(instruction).decode("ascii"),
                "descendant_profile_bytes_base64": base64.b64encode(profile_bytes).decode("ascii"),
                "descendant_candidate_sha256": candidate_sha,
                "predictor_invoked": True,
            }

        def forward(self, *, parent: Mapping[str, Any], diagnostics: Mapping[str, Any]) -> dict[str, Any]:
            inputs, diagnostic_sha = self._inputs(parent=parent, diagnostics=diagnostics)
            prediction = self.predict(**inputs)
            return self._validated_output(parent=parent, diagnostics=diagnostics, diagnostic_sha=diagnostic_sha, inputs=inputs, prediction=prediction)

    return FrozenTrainingCandidateProposer()


def optimize_training_evidence(*, frozen_successor_path: Path, hanna_csv_path: Path, native_training_evidence_path: Path, seed: int = 20260829, storage: str | None = None) -> dict[str, Any]:
    """Run a deterministic, development-only candidate search from raw training cells."""
    if not isinstance(seed, int):
        raise ValueError("HANNA v4 optimizer seed is invalid")
    v3, native = _load_v3(), _load_native()
    schedule = native.derive_schedule(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    observations, targets = _validate_evidence(evidence_path=Path(native_training_evidence_path), schedule=schedule, native=native, v3=v3, frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    by_model = _candidate_metrics(observations=observations, targets=targets, v3=v3)
    grok = {row["candidate_id"]: row for row in by_model["grok_primary"]}
    candidate_ids = sorted(grok)
    try:
        import optuna  # type: ignore[import-not-found]
    except ImportError as error:
        raise ValueError("HANNA v4 Optuna development dependency is not installed; refusing simulated optimization") from error
    sampler = optuna.samplers.GridSampler({"candidate_id": candidate_ids}, seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler, storage=storage, study_name="hanna-v4-development", load_if_exists=False)
    def objective(trial: Any) -> float:
        candidate_id = trial.suggest_categorical("candidate_id", candidate_ids)
        metric = grok[candidate_id]
        alignment = float(metric["train"]["macro_spearman"])
        efficiency = float(metric["mean_native_request_bytes"])
        value = alignment - (efficiency / 1_000_000_000.0)
        trial.set_user_attr("candidate_id", candidate_id)
        trial.set_user_attr("alignment", alignment)
        trial.set_user_attr("mean_native_request_bytes", efficiency)
        return value
    study.optimize(objective, n_trials=len(candidate_ids), catch=())
    best = study.best_trial
    return {
        "format_version": 1, "study_id": STUDY_ID, "kind": "development_only_deterministic_optuna_search",
        "status": "nonempirical_training_only_no_confirmation_or_runtime_authority",
        "lineage": {"v4_native_schedule_sha256": schedule["schedule_sha256"], "parent_v3_schedule_sha256": schedule["parent_v3_schedule_sha256"], "native_training_evidence_sha256": sha256_bytes(Path(native_training_evidence_path).read_bytes()), "seed": seed, "sampler": "optuna.GridSampler", "storage": storage},
        "geometry": {"training_cells": 360, "grok_training_cells": 240, "sol_training_cells": 120, "development_cells_admitted": 0, "confirmation_cells_admitted": 0, "candidate_count": 5},
        "endpoint": {"unit": "prompt_group_equal_weight", "grok_subscription": by_model["grok_primary"], "sol_codex_subscription_train_descriptive_only": by_model["sol_validation"]},
        "best_trial": {"number": best.number, "candidate_id": best.params["candidate_id"], "objective": best.value, "alignment": best.user_attrs["alignment"], "mean_native_request_bytes": best.user_attrs["mean_native_request_bytes"]},
        "optimizer_interfaces": {"optuna": "development_only_executed", "dspy": "development_only_installed_program_available_not_invoked" if importlib.util.find_spec("dspy") is not None else "development_only_dependency_unavailable"},
        "empirical_authority": "none_until_separate_native_receipt_and_frozen_development_confirmation_gates",
    }
