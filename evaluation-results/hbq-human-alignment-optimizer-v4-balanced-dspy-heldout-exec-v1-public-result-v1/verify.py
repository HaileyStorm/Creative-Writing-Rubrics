#!/usr/bin/env python3
"""Provider-free verification for the compact public HANNA result."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
FILES = {
    "grok-selection.json": "1cc2d24ae3e6793683d1e3ec1118b0358ef3861099e5dc00f3588bac3ac38eb3",
    "endpoint-result.json": "2c9e6716e2419e420ee03a6d0bb64b1a2863df00bc44f666320b17732207d227",
    "public-result.json": "4bc51804857841b59d6ed5150993460f0dbb9767b22591526e37d14b88ea97b7",
    "provenance.v1.json": "f3ec4adc9b07dac635b034a8ecbc3cdf81021d03f860d936c9fc1d30d9dbfd85",
    "study-contract.json": "8022c4387718cd6491b7a6a83d6a64da7a42c85d7d640f18d42ee5d9eb70e4df",
    "selection-schema.json": "4e169f7d46fdcf62d73b73649f63c39d94cb191a09eb9ea6999a8f1a162fd48a",
    "result-schema.json": "b0f220be3bff0888fda12a87fc918d8d982eca1f4d0292638fae67c60629e2b1",
    "feedback-selection.json": "5b49688f85a530a7ab22cee382514bfd659eec4ef2d8bb68a9b223554aefb816",
    "feedback-result.json": "2ecaf697c8ff729e3545e7004113b0ac186428623d4116fa4e505df950bd1a25",
}
PRODUCER = {
    "schema": "hanna_public_result_v1",
    "source_commit": "0d14b0dcae34b71045e20217c87f26eafcea4955",
    "analyzer_sha256": "c28f6dee9b1c1353ec1cf9a1eec8b5b9d21c266bbd41ee0acd2beed32c02d18c",
    "verifier_sha256": "543b7f04e30c0deda3e6b05ef80ef4b4466d69a7c59f585bd1c0fd5610bd681b",
}
SOURCE_COMMITMENTS = {
    "schedule_sha256": "de7fce6600b03181fd429a3018c89468b1d08cf74841905bd341329be4aa437e",
    "collection_file_sha256": "62ec4b713aeba90b595a9b7428b428fd7c76738b2426192ca76a7a19ac13c37f",
    "collection_manifest_sha256": "97820229e2364ec601624e270d9dcda95aa46bb8697008a6768a63535bd4cda8",
    "r4_adoption_sha256": "369c42f544ff316a53bf541ac18d712f31ed3d566d41444a815a3fd43bcdd73b",
    "reconciliation_manifest_sha256": "26b91ea23f04b55909db775b75c1bf7ae2d4819d2acc8346244548296e229bf3",
    "frozen_successor_sha256": "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7",
}
DERIVED_COMMITMENTS = {
    "grok_projection_sha256": "21286491f14d6be279bbff25787b3860b94ec78e2a0b6f8526c054941148be3a",
    "grok_projection_artifact_sha256": "b063f0f7b808249ee25d59e64c3702c91498597ea96fcf84bbb29576ee3fead4",
    "sol_projection_artifact_sha256": "dae25d9d03f27f06a2146761e23e12d8da683dbe9554e8cfa23ec9b52d5ef2ae",
    "grok_selection_artifact_sha256": FILES["grok-selection.json"],
    "endpoint_result_embedded_sha256": "494e5ad7a87e091976a4b4c0dc85708b9327b079c9952712a8fd266cc8f0ec31",
    "endpoint_result_artifact_sha256": FILES["endpoint-result.json"],
    "public_result_artifact_sha256": FILES["public-result.json"],
}
PUBLIC_STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1-public-result-v1"
PUBLIC_RESULT_SUMMARY = (
    "The Grok-selected descendant improved four-group Grok MAE from "
    "1.0694444444444444 to 0.875, but reversed on two-group Sol validation "
    "from 1.3680555555555554 to 1.4277777777777778; endpoints are not pooled, "
    "general gain is not observed, Sol native contact cardinality is unproven, "
    "and confirmation remains unopened."
)
DISALLOWED_KEYS = frozenset(
    {
        "observations",
        "human_targets",
        "raw_response",
        "raw_responses",
        "request_id",
        "session_id",
        "contact_id",
        "local_path",
        "absolute_path",
    }
)
WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")


def canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _plain_file(path: Path) -> bytes:
    info = os.lstat(path)
    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    ):
        raise ValueError("HANNA public-result artifact is not a plain file")
    return path.read_bytes()


def _object(path: Path) -> dict[str, Any]:
    raw = _plain_file(path)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA public-result artifact is invalid JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError("HANNA public-result artifact is not canonical JSON")
    return value


def _reject_private_surface(value: Any) -> None:
    if isinstance(value, dict):
        if DISALLOWED_KEYS.intersection(value):
            raise ValueError("HANNA public-result artifact exposes a private evidence field")
        for item in value.values():
            _reject_private_surface(item)
    elif isinstance(value, list):
        for item in value:
            _reject_private_surface(item)
    elif isinstance(value, str) and WINDOWS_ABSOLUTE.match(value):
        raise ValueError("HANNA public-result artifact exposes an absolute local path")


def _self_hash(value: dict[str, Any], field: str) -> str:
    body = dict(value)
    digest = body.pop(field, None)
    if not isinstance(digest, str) or digest != sha256(canonical(body)):
        raise ValueError(f"HANNA public-result {field} drifted")
    return digest


def verify(root: Path = HERE) -> dict[str, Any]:
    root = Path(root)
    values: dict[str, dict[str, Any]] = {}
    for name, expected in FILES.items():
        raw = _plain_file(root / name)
        if sha256(raw) != expected:
            raise ValueError(f"HANNA public-result {name} hash drifted")
        values[name] = _object(root / name)
        _reject_private_surface(values[name])

    selection = values["grok-selection.json"]
    endpoint_result = values["endpoint-result.json"]
    public = values["public-result.json"]
    provenance = values["provenance.v1.json"]

    if (
        selection.get("kind") != "heldout_grok_selection_frozen_before_sol"
        or selection.get("selected_candidate_id") != "candidate-0ca942ad28cb4104"
        or selection.get("baseline_candidate_id") != "candidate-52d1be4bc34e0018"
        or selection.get("selected_grok_mean_absolute_error") != 0.875
        or selection.get("baseline_grok_mean_absolute_error") != 1.0694444444444444
        or selection.get("strict_grok_improvement") is not True
        or len(selection.get("grok_endpoints", [])) != 11
    ):
        raise ValueError("HANNA public-result Grok selection semantics drifted")

    endpoint_body = dict(endpoint_result)
    embedded_result_sha = endpoint_body.pop("result_sha256", None)
    if embedded_result_sha != DERIVED_COMMITMENTS["endpoint_result_embedded_sha256"] or embedded_result_sha != sha256(canonical(endpoint_body)):
        raise ValueError("HANNA public-result endpoint result self-hash drifted")
    if (
        endpoint_result.get("grok_selection") != selection
        or endpoint_result.get("grok_projection_sha256") != DERIVED_COMMITMENTS["grok_projection_sha256"]
        or endpoint_result.get("sol_projection_sha256") != DERIVED_COMMITMENTS["sol_projection_artifact_sha256"]
        or endpoint_result.get("no_pooling") is not True
        or endpoint_result.get("gain_observed") is not False
        or endpoint_result.get("claim") != "no_independently_observed_heldout_gain"
        or endpoint_result.get("confirmation") != {"status": "unopened", "cells": 0}
        or endpoint_result.get("runtime_authority") != "none"
    ):
        raise ValueError("HANNA public-result endpoint result semantics drifted")
    sol = endpoint_result.get("sol_validation", {})
    sol_by_id = {
        item.get("candidate_id"): item.get("endpoint")
        for item in sol.get("sol_endpoints", [])
        if isinstance(item, dict)
    }
    if (
        sol.get("sol_nonreversal") is not False
        or sol.get("sol_evidence_ceiling") != "local_lifecycle_verified_native_endpoint_contact_cardinality_unproven"
        or sol_by_id.get("candidate-52d1be4bc34e0018", {}).get("mean_absolute_error") != 1.3680555555555554
        or sol_by_id.get("candidate-0ca942ad28cb4104", {}).get("mean_absolute_error") != 1.4277777777777778
    ):
        raise ValueError("HANNA public-result Sol validation semantics drifted")

    _self_hash(public, "public_result_sha256")
    if (
        public.get("producer") != PRODUCER
        or public.get("artifacts")
        != {
            "grok_selection": {"file": "grok-selection.json", "sha256": FILES["grok-selection.json"]},
            "endpoint_result": {"file": "endpoint-result.json", "sha256": FILES["endpoint-result.json"]},
        }
        or public.get("no_pooling") is not True
        or public.get("gain_observed") is not False
        or public.get("confirmation") != {"status": "unopened", "cells": 0}
        or public.get("runtime_authority") != "none"
        or public.get("selected_candidate_id") != selection["selected_candidate_id"]
        or public.get("baseline_candidate_id") != selection["baseline_candidate_id"]
    ):
        raise ValueError("HANNA public-result compact presentation drifted")
    metrics = public.get("endpoint_metrics", {})
    if (
        metrics.get("grok_primary", {}).get("baseline_minus_selected_mean_absolute_error") != 0.19444444444444442
        or metrics.get("grok_primary", {}).get("strict_improvement") is not True
        or metrics.get("sol_validation", {}).get("baseline_minus_selected_mean_absolute_error") != -0.059722222222222454
        or metrics.get("sol_validation", {}).get("nonreversal") is not False
    ):
        raise ValueError("HANNA public-result compact metrics drifted")

    _self_hash(provenance, "provenance_sha256")
    if (
        provenance.get("producer") != PRODUCER
        or provenance.get("source_commitments") != SOURCE_COMMITMENTS
        or provenance.get("derived_commitments") != DERIVED_COMMITMENTS
        or provenance.get("public_safety")
        != {
            "status": "public_safe",
            "excluded": [
                "per_cell_observation_records",
                "human_reference_values",
                "raw_provider_output",
                "filesystem_locations",
                "provider_contact_identifiers",
            ],
        }
        or provenance.get("no_pooling") is not True
        or provenance.get("gain_observed") is not False
        or provenance.get("confirmation") != {"status": "unopened", "cells": 0}
        or provenance.get("runtime_authority") != "none"
    ):
        raise ValueError("HANNA public-result provenance drifted")

    contract = values["study-contract.json"]
    selection_schema = values["selection-schema.json"]
    result_schema = values["result-schema.json"]
    feedback_selection = values["feedback-selection.json"]
    feedback_result = values["feedback-result.json"]
    materializer_sha = sha256(_plain_file(root / "materialize.py"))
    if (
        contract.get("study_id") != PUBLIC_STUDY_ID
        or contract.get("kind") != "hanna_public_result_feedback_producer_contract"
        or contract.get("producer_schema") != PRODUCER["schema"]
        or contract.get("source_commit") != PRODUCER["source_commit"]
        or contract.get("producer_source") != {"file": "materialize.py", "sha256": materializer_sha}
        or contract.get("authority")
        != {
            "development_feedback_only": True,
            "selection": False,
            "evaluation": False,
            "runtime": False,
            "confirmation": {"status": "unopened", "cells": 0},
        }
    ):
        raise ValueError("HANNA public-result producer contract drifted")
    expected_sources = {
        "grok_selection": {"file": "grok-selection.json", "sha256": FILES["grok-selection.json"]},
        "endpoint_result": {"file": "endpoint-result.json", "sha256": FILES["endpoint-result.json"]},
        "public_result": {"file": "public-result.json", "sha256": FILES["public-result.json"]},
        "provenance": {"file": "provenance.v1.json", "sha256": FILES["provenance.v1.json"]},
    }
    if contract.get("source_artifacts") != expected_sources:
        raise ValueError("HANNA public-result producer source artifacts drifted")
    if (
        selection_schema.get("$id") != "urn:cwr:hanna-public-result-v1:feedback-selection"
        or selection_schema.get("properties", {}).get("study_id") != {"const": PUBLIC_STUDY_ID}
        or result_schema.get("$id") != "urn:cwr:hanna-public-result-v1:feedback-result"
        or result_schema.get("properties", {}).get("study_id") != {"const": PUBLIC_STUDY_ID}
        or result_schema.get("properties", {}).get("public_result_summary") != {"const": PUBLIC_RESULT_SUMMARY}
    ):
        raise ValueError("HANNA public-result feedback schemas drifted")
    if (
        feedback_selection.get("study_id") != PUBLIC_STUDY_ID
        or feedback_selection.get("producer") != PRODUCER
        or feedback_selection.get("source_artifact") != expected_sources["grok_selection"]
        or feedback_selection.get("grok_selection") != selection
    ):
        raise ValueError("HANNA public-result feedback selection drifted")
    if (
        feedback_result.get("study_id") != PUBLIC_STUDY_ID
        or feedback_result.get("producer") != PRODUCER
        or feedback_result.get("public_result_summary") != PUBLIC_RESULT_SUMMARY
        or feedback_result.get("source_artifacts")
        != {
            "endpoint_result": expected_sources["endpoint_result"],
            "public_result": expected_sources["public_result"],
        }
        or feedback_result.get("endpoint_result") != endpoint_result
        or feedback_result.get("public_result") != public
    ):
        raise ValueError("HANNA public-result feedback result drifted")

    return {
        "status": "verified",
        "selected_candidate_id": selection["selected_candidate_id"],
        "gain_observed": False,
        "files": dict(FILES),
    }


def main() -> None:
    print(json.dumps(verify(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
