#!/usr/bin/env python3
"""Materialize public-safe HANNA artifacts from the committed evidence analyzer."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
SOURCE_PACKAGE = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1"
ANALYZER_PATH = SOURCE_PACKAGE / "analyze.py"
VERIFIER_PATH = SOURCE_PACKAGE / "verifier.py"
ANALYZER_SHA256 = "c28f6dee9b1c1353ec1cf9a1eec8b5b9d21c266bbd41ee0acd2beed32c02d18c"
VERIFIER_SHA256 = "543b7f04e30c0deda3e6b05ef80ef4b4466d69a7c59f585bd1c0fd5610bd681b"
SOURCE_COMMIT = "0d14b0dcae34b71045e20217c87f26eafcea4955"
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1"
PUBLIC_STUDY_ID = f"{STUDY_ID}-public-result-v1"
PRODUCER = {
    "schema": "hanna_public_result_v1",
    "source_commit": SOURCE_COMMIT,
    "analyzer_sha256": ANALYZER_SHA256,
    "verifier_sha256": VERIFIER_SHA256,
}
PUBLIC_RESULT_SUMMARY = (
    "The Grok-selected descendant improved four-group Grok MAE from "
    "1.0694444444444444 to 0.875, but reversed on two-group Sol validation "
    "from 1.3680555555555554 to 1.4277777777777778; endpoints are not pooled, "
    "general gain is not observed, Sol native contact cardinality is unproven, "
    "and confirmation remains unopened."
)


def canonical(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_analyzer() -> ModuleType:
    raw = ANALYZER_PATH.read_bytes()
    if sha256(raw) != ANALYZER_SHA256 or sha256(VERIFIER_PATH.read_bytes()) != VERIFIER_SHA256:
        raise ValueError("HANNA public-result producer drifted")
    spec = importlib.util.spec_from_file_location("_hanna_public_result_analyzer", ANALYZER_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA public-result analyzer cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _self_hash(value: dict[str, Any], field: str) -> dict[str, Any]:
    result = dict(value)
    result[field] = sha256(canonical(result))
    return result


def materialize(
    *,
    output_root: Path,
    collection_evidence_path: Path,
    collection_root: Path,
    r4_adoption_path: Path,
    reconciliation_manifest_path: Path,
    frozen_successor_path: Path,
    hanna_csv_path: Path,
) -> dict[str, str]:
    analyzer = _load_analyzer()
    analyzed = analyzer.verify_and_analyze(
        collection_evidence_path=collection_evidence_path,
        collection_root=collection_root,
        r4_adoption_path=r4_adoption_path,
        reconciliation_manifest_path=reconciliation_manifest_path,
        frozen_successor_path=frozen_successor_path,
        hanna_csv_path=hanna_csv_path,
    )
    selection = analyzed["grok_selection"]
    endpoint_result = analyzed["result"]
    selection_bytes = canonical(selection)
    endpoint_result_bytes = canonical(endpoint_result)
    selection_sha = sha256(selection_bytes)
    endpoint_result_sha = sha256(endpoint_result_bytes)
    grok_projection_sha = sha256(canonical(analyzed["grok_projection"]))
    sol_projection_sha = sha256(canonical(analyzed["sol_projection"]))

    sol_by_id = {
        item["candidate_id"]: item["endpoint"]
        for item in endpoint_result["sol_validation"]["sol_endpoints"]
    }
    baseline = selection["baseline_candidate_id"]
    selected = selection["selected_candidate_id"]
    grok_delta = selection["baseline_grok_mean_absolute_error"] - selection["selected_grok_mean_absolute_error"]
    sol_delta = sol_by_id[baseline]["mean_absolute_error"] - sol_by_id[selected]["mean_absolute_error"]

    public_result = _self_hash(
        {
            "format_version": 1,
            "study_id": PUBLIC_STUDY_ID,
            "kind": "public_safe_endpoint_separated_heldout_result",
            "source_study_id": STUDY_ID,
            "producer": PRODUCER,
            "artifacts": {
                "grok_selection": {"file": "grok-selection.json", "sha256": selection_sha},
                "endpoint_result": {"file": "endpoint-result.json", "sha256": endpoint_result_sha},
            },
            "selected_candidate_id": selected,
            "baseline_candidate_id": baseline,
            "endpoint_metrics": {
                "grok_primary": {
                    "prompt_group_count": 4,
                    "baseline_mean_absolute_error": selection["baseline_grok_mean_absolute_error"],
                    "selected_mean_absolute_error": selection["selected_grok_mean_absolute_error"],
                    "baseline_minus_selected_mean_absolute_error": grok_delta,
                    "strict_improvement": selection["strict_grok_improvement"],
                    "evidence_class": "derived_from_pinned_completed_adapter_control",
                },
                "sol_validation": {
                    "prompt_group_count": 2,
                    "baseline_mean_absolute_error": sol_by_id[baseline]["mean_absolute_error"],
                    "selected_mean_absolute_error": sol_by_id[selected]["mean_absolute_error"],
                    "baseline_minus_selected_mean_absolute_error": sol_delta,
                    "nonreversal": endpoint_result["sol_validation"]["sol_nonreversal"],
                    "evidence_class": endpoint_result["sol_validation"]["sol_evidence_ceiling"],
                },
            },
            "no_pooling": True,
            "gain_observed": False,
            "claim": "no_independently_observed_heldout_gain",
            "confirmation": {"status": "unopened", "cells": 0},
            "runtime_authority": "none",
            "limitations": [
                "grok_specific_development_improvement_reversed_on_sol",
                "sol_native_endpoint_contact_cardinality_unproven",
                "confirmation_partition_unopened",
            ],
        },
        "public_result_sha256",
    )

    provenance = _self_hash(
        {
            "format_version": 1,
            "study_id": PUBLIC_STUDY_ID,
            "kind": "public_result_provenance",
            "producer": PRODUCER,
            "source_commitments": {
                "schedule_sha256": "de7fce6600b03181fd429a3018c89468b1d08cf74841905bd341329be4aa437e",
                "collection_file_sha256": sha256(collection_evidence_path.read_bytes()),
                "collection_manifest_sha256": "97820229e2364ec601624e270d9dcda95aa46bb8697008a6768a63535bd4cda8",
                "r4_adoption_sha256": sha256(r4_adoption_path.read_bytes()),
                "reconciliation_manifest_sha256": sha256(reconciliation_manifest_path.read_bytes()),
                "frozen_successor_sha256": sha256(frozen_successor_path.read_bytes()),
            },
            "derived_commitments": {
                "grok_projection_sha256": analyzed["grok_projection"]["projection_sha256"],
                "grok_projection_artifact_sha256": grok_projection_sha,
                "sol_projection_artifact_sha256": sol_projection_sha,
                "grok_selection_artifact_sha256": selection_sha,
                "endpoint_result_embedded_sha256": endpoint_result["result_sha256"],
                "endpoint_result_artifact_sha256": endpoint_result_sha,
                "public_result_artifact_sha256": sha256(canonical(public_result)),
            },
            "public_safety": {
                "status": "public_safe",
                "excluded": [
                    "per_cell_observation_records",
                    "human_reference_values",
                    "raw_provider_output",
                    "filesystem_locations",
                    "provider_contact_identifiers",
                ],
            },
            "no_pooling": True,
            "gain_observed": False,
            "confirmation": {"status": "unopened", "cells": 0},
            "runtime_authority": "none",
        },
        "provenance_sha256",
    )

    selection_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:cwr:hanna-public-result-v1:feedback-selection",
        "type": "object",
        "additionalProperties": False,
        "required": ["format_version", "study_id", "kind", "producer", "source_artifact", "grok_selection"],
        "properties": {
            "format_version": {"const": 1},
            "study_id": {"const": PUBLIC_STUDY_ID},
            "kind": {"const": "hanna_r4_two_phase_grok_selection_feedback"},
            "producer": {"type": "object"},
            "source_artifact": {"type": "object"},
            "grok_selection": {"type": "object"},
        },
    }
    result_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:cwr:hanna-public-result-v1:feedback-result",
        "type": "object",
        "additionalProperties": False,
        "required": ["format_version", "study_id", "kind", "producer", "public_result_summary", "source_artifacts", "endpoint_result", "public_result"],
        "properties": {
            "format_version": {"const": 1},
            "study_id": {"const": PUBLIC_STUDY_ID},
            "kind": {"const": "hanna_r4_two_phase_endpoint_result_feedback"},
            "producer": {"type": "object"},
            "public_result_summary": {"const": PUBLIC_RESULT_SUMMARY},
            "source_artifacts": {"type": "object"},
            "endpoint_result": {"type": "object"},
            "public_result": {"type": "object"},
        },
    }
    source_sha = sha256(Path(__file__).read_bytes())
    producer_contract = {
        "format_version": 1,
        "study_id": PUBLIC_STUDY_ID,
        "kind": "hanna_public_result_feedback_producer_contract",
        "producer_schema": "hanna_public_result_v1",
        "producer_source": {"file": "materialize.py", "sha256": source_sha},
        "source_commit": SOURCE_COMMIT,
        "source_artifacts": {
            "grok_selection": {"file": "grok-selection.json", "sha256": selection_sha},
            "endpoint_result": {"file": "endpoint-result.json", "sha256": endpoint_result_sha},
            "public_result": {"file": "public-result.json", "sha256": sha256(canonical(public_result))},
            "provenance": {"file": "provenance.v1.json", "sha256": sha256(canonical(provenance))},
        },
        "authority": {
            "development_feedback_only": True,
            "selection": False,
            "evaluation": False,
            "runtime": False,
            "confirmation": {"status": "unopened", "cells": 0},
        },
    }
    feedback_selection = {
        "format_version": 1,
        "study_id": PUBLIC_STUDY_ID,
        "kind": "hanna_r4_two_phase_grok_selection_feedback",
        "producer": PRODUCER,
        "source_artifact": {"file": "grok-selection.json", "sha256": selection_sha},
        "grok_selection": selection,
    }
    feedback_result = {
        "format_version": 1,
        "study_id": PUBLIC_STUDY_ID,
        "kind": "hanna_r4_two_phase_endpoint_result_feedback",
        "producer": PRODUCER,
        "public_result_summary": PUBLIC_RESULT_SUMMARY,
        "source_artifacts": {
            "endpoint_result": {"file": "endpoint-result.json", "sha256": endpoint_result_sha},
            "public_result": {"file": "public-result.json", "sha256": sha256(canonical(public_result))},
        },
        "endpoint_result": endpoint_result,
        "public_result": public_result,
    }

    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "grok-selection.json": selection_bytes,
        "endpoint-result.json": endpoint_result_bytes,
        "public-result.json": canonical(public_result),
        "provenance.v1.json": canonical(provenance),
        "study-contract.json": canonical(producer_contract),
        "selection-schema.json": canonical(selection_schema),
        "result-schema.json": canonical(result_schema),
        "feedback-selection.json": canonical(feedback_selection),
        "feedback-result.json": canonical(feedback_result),
    }
    for name, raw in outputs.items():
        (output_root / name).write_bytes(raw)
    return {name: sha256(raw) for name, raw in outputs.items()}


def feedback_manifest(*, package_root: Path, wave_id: str, seed: int) -> dict[str, Any]:
    root = Path(package_root).resolve()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,63}", wave_id) or type(seed) is not int or seed < 0:
        raise ValueError("HANNA feedback descriptor wave_id/seed is invalid")

    def reference(name: str) -> tuple[str, str]:
        path = (root / name).resolve()
        raw = path.read_bytes()
        if name.endswith(".json"):
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or canonical(value) != raw:
                raise ValueError(f"HANNA feedback descriptor {name} is not canonical")
        return str(path), sha256(raw)

    contract_path, contract_sha = reference("study-contract.json")
    source_path, source_sha = reference("materialize.py")
    selection_schema_path, selection_schema_sha = reference("selection-schema.json")
    result_schema_path, result_schema_sha = reference("result-schema.json")
    selection_path, selection_sha = reference("feedback-selection.json")
    result_path, result_sha = reference("feedback-result.json")
    return {
        "format_version": 1,
        "kind": "hanna_r4_two_phase_feedback",
        "study_id": PUBLIC_STUDY_ID,
        "wave_id": wave_id,
        "seed": seed,
        "public_result_summary": PUBLIC_RESULT_SUMMARY,
        "producer": {
            "study_contract_path": contract_path,
            "study_contract_sha256": contract_sha,
            "producer_source_path": source_path,
            "producer_source_sha256": source_sha,
            "selection_schema_path": selection_schema_path,
            "selection_schema_sha256": selection_schema_sha,
            "result_schema_path": result_schema_path,
            "result_schema_sha256": result_schema_sha,
        },
        "artifacts": {
            "selection_path": selection_path,
            "selection_sha256": selection_sha,
            "result_path": result_path,
            "result_sha256": result_sha,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=HERE)
    parser.add_argument("--collection-evidence", type=Path, required=True)
    parser.add_argument("--collection-root", type=Path, required=True)
    parser.add_argument("--r4-adoption", type=Path, required=True)
    parser.add_argument("--reconciliation-manifest", type=Path, required=True)
    parser.add_argument("--frozen-successor", type=Path, required=True)
    parser.add_argument("--hanna-csv", type=Path, required=True)
    parser.add_argument("--feedback-output", type=Path)
    parser.add_argument("--wave-id")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    hashes = materialize(
        output_root=args.output_root,
        collection_evidence_path=args.collection_evidence,
        collection_root=args.collection_root,
        r4_adoption_path=args.r4_adoption,
        reconciliation_manifest_path=args.reconciliation_manifest,
        frozen_successor_path=args.frozen_successor,
        hanna_csv_path=args.hanna_csv,
    )
    if args.feedback_output is not None:
        if args.wave_id is None or args.seed is None:
            parser.error("--feedback-output requires --wave-id and --seed")
        descriptor = feedback_manifest(
            package_root=args.output_root,
            wave_id=args.wave_id,
            seed=args.seed,
        )
        args.feedback_output.write_bytes(canonical(descriptor))
        hashes["feedback_descriptor"] = sha256(canonical(descriptor))
    print(json.dumps(hashes, sort_keys=True))


if __name__ == "__main__":
    main()
