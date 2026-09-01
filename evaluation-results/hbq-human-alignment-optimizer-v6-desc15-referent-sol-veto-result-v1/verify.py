"""Replay the 39-cell descendant-15 Sol veto result from persisted receipts."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import stat
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-result-v1"
EXECUTOR_STUDY_ID = "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-exec-v1"
EXECUTOR_COMMIT = "cf9c58665eb33bb3b83264d1e9272c7e030cb18b"
EXECUTOR_SHA256 = "f900e2bda4922b44ba5f9a027a889cae56e1b808670c3ef05d441ac664192c92"
COLLECTOR_SHA256 = "ff8905c0f4f537d5806e89294ab6432f56ef0c14bc083968f3405e6c6e580760"
GROK_RESULT_FILE_SHA256 = "5f074a3998f1f830de6157cca7751ca1aab3200bced8806da3d628d4f7570c4f"
GROK_RESULT_INTERNAL_SHA256 = "97db289ebc4b9e558c53c8659c818cbc248da190187ead9cb651e8049c07ff12"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
PARENT_SOL_MAE = 1.1166666666666667
CHILDREN = (
    "broader-nextwave-19-construct_framing-referent-boundary",
    "broader-nextwave-20-missing_evidence_not_no-referent-evidence",
    "broader-nextwave-21-scope_materiality-referent-materiality",
)
GROUPS = (
    "prompt-132112dd8eeb2d4d",
    "prompt-3f844c5cdc6b51ae",
    "prompt-6450c4baa52d6998",
    "prompt-6a99e79cf010b289",
    "prompt-7c393c4bcb3a7484",
    "prompt-8997770ce6efe4d5",
    "prompt-8d3d397a4f6ba0ea",
)
ITEMS = (
    "item-028fc3ac6963b50f",
    "item-0cb9c7afe8527434",
    "item-1568277c2dde9944",
    "item-1b27b9076eef2bc5",
    "item-2377fcf24510aac5",
    "item-242fe0ddf52e6278",
    "item-25d5a1163ca56b27",
    "item-2ba42c130da729fa",
    "item-85b393b19a363e89",
    "item-8776b34674d81280",
    "item-9a254f1a6661a875",
    "item-d5fe1ae06099a06e",
    "item-f6e3af87c879383c",
)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PUBLIC_FILES = {"README.md", "publication-manifest.json", "result.json", "study-contract.json", "verify.py"}
EXPECTED_FACTOR_EDITS = {
    CHILDREN[0]: {"construct_framing": "Step-05 referent boundary:"},
    CHILDREN[1]: {"missing_evidence_not_no": "Step-05 referent evidence:"},
    CHILDREN[2]: {"scope_materiality": "Step-05 referent materiality:"},
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe or reparsed evidence path")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("evidence path type drifted")


def stable(path: Path) -> bytes:
    target = Path(os.path.abspath(path))
    current = Path(target.anchor)
    for part in target.parts[1:]:
        current /= part
        _plain(current, directory=current != target)
    before = os.lstat(target)
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after_open = os.fstat(handle.fileno())
    after = os.lstat(target)
    identity = lambda item: (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode), item.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after_open) or identity(after_open) != identity(after):
        raise ValueError("evidence changed during stable read")
    return raw


def strict(raw: bytes, label: str, *, allow_missing_newline: bool = False) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    accepted = (canonical(value),)
    if allow_missing_newline:
        accepted += (canonical(value)[:-1],)
    if type(value) is not dict or raw not in accepted:
        raise ValueError(f"noncanonical {label}")
    return value


def _admit_grok_result(path: Path) -> dict[str, Any]:
    raw = stable(path)
    if sha256(raw) != GROK_RESULT_FILE_SHA256:
        raise ValueError("frozen Grok optimizer result drifted")
    result = strict(raw, "Grok optimizer result")
    if (
        result.get("result_sha256") != GROK_RESULT_INTERNAL_SHA256
        or sha256({key: value for key, value in result.items() if key != "result_sha256"}) != GROK_RESULT_INTERNAL_SHA256
        or tuple(result.get("qualification", {}).get("qualifiers", ())) != CHILDREN
        or result.get("qualification", {}).get("frozen_before_sol") is not True
        or result.get("authority", {}).get("confirmation") != {"cells": 0, "status": "unopened"}
    ):
        raise ValueError("Grok qualification freeze drifted")
    return result


def _cell_projection(root: Path, supplied: Mapping[str, Any]) -> dict[str, Any]:
    cell_id = supplied.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id.startswith("desc15-sol-veto-"):
        raise ValueError("invalid Sol cell id")
    cell_root = root / cell_id
    _plain(cell_root, directory=True)
    receipt_raw = stable(cell_root / "execution-receipt.json")
    target_raw = stable(cell_root / "target-vector.json")
    prepared_raw = stable(cell_root / "prepared.json")
    payload_raw = stable(cell_root / "outbound-payload.json")
    final_raw = stable(cell_root / "raw-codex-final-response.bin")
    receipt = strict(receipt_raw, "execution receipt")
    target_vector = strict(target_raw, "target vector")
    prepared = strict(prepared_raw, "prepared cell")
    payload = strict(payload_raw, "outbound payload")
    answer = strict(final_raw, "final response", allow_missing_newline=True)
    cell = receipt.get("cell")
    if not isinstance(cell, Mapping):
        raise TypeError("receipt cell is absent")
    candidate = cell.get("candidate_id")
    item_id = cell.get("item_id")
    group = cell.get("prompt_group_id")
    target = cell.get("target")
    factors = payload.get("profile", {}).get("factors", {})
    expected_factor = EXPECTED_FACTOR_EDITS.get(candidate, {})
    if (
        candidate not in CHILDREN
        or item_id not in ITEMS
        or group not in GROUPS
        or target_vector.get("cell_id") != cell_id
        or target_vector.get("item_id") != item_id
        or target_vector.get("story_id") != item_id
        or target_vector.get("target") != target
        or prepared.get("target_vector_sha256") != sha256(target_raw)
        or prepared.get("task_payload_sha256") != sha256(payload_raw)
        or prepared.get("cell") != cell
        or payload.get("item_id") != item_id
        or payload.get("prompt_group_id") != group
        or len(expected_factor) != 1
        or any(marker not in factors.get(name, "") for name, marker in expected_factor.items())
        or any(
            marker in factors.get(name, "")
            for other, edit in EXPECTED_FACTOR_EDITS.items()
            if other != candidate
            for name, marker in edit.items()
        )
        or supplied.get("candidate_id") != candidate
        or supplied.get("source_cell_id") != cell.get("source_cell_id")
        or supplied.get("receipt_sha256") != sha256(receipt_raw)
        or supplied.get("payload_sha256") != sha256(payload_raw)
        or base64.b64decode(supplied.get("payload_base64", ""), validate=True) != payload_raw
        or supplied.get("final_response_sha256") != sha256(final_raw)
        or base64.b64decode(supplied.get("final_response_base64", ""), validate=True) != final_raw
        or supplied.get("human_score_projection") != answer
        or receipt.get("human_score_projection") != answer
        or supplied.get("identity") != receipt.get("identity")
        or supplied.get("effective_settings") != strict(stable(cell_root / "effective-settings.json"), "effective settings")
        or supplied.get("effective_settings_sha256") != receipt.get("effective_settings_sha256")
        or receipt.get("request_sha256") != sha256(payload_raw)
        or receipt.get("final_response_sha256") != sha256(final_raw)
        or receipt.get("process_launches") != 1
        or receipt.get("provider_calls_made") is not None
        or receipt.get("native_endpoint_contact_cardinality") != "unproven"
        or receipt.get("identity", {}).get("requested_model") != "gpt-5.6-sol"
        or receipt.get("identity", {}).get("provider") != "openai_codex"
        or supplied.get("effective_settings", {}).get("tools_enabled") is not False
    ):
        raise ValueError("persisted Sol cell evidence drifted")
    scores = answer.get("scores")
    coverage = answer.get("coverage")
    if not isinstance(scores, Mapping) or not isinstance(coverage, Mapping) or set(scores) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS) or not isinstance(target, Mapping) or set(target) != set(DIMENSIONS):
        raise ValueError("Sol score or target geometry drifted")
    errors: list[float] = []
    false_dimensions: list[str] = []
    for dimension in DIMENSIONS:
        score = scores[dimension]
        expected = target[dimension]
        if type(score) not in (int, float) or type(expected) not in (int, float) or not math.isfinite(score) or not math.isfinite(expected):
            raise ValueError("non-finite Sol score or target")
        errors.append(abs(float(score) - float(expected)))
        if coverage[dimension] is False:
            false_dimensions.append(dimension)
        elif coverage[dimension] is not True:
            raise ValueError("non-boolean coverage")
    return {"candidate_id": candidate, "cell_id": cell_id, "item_id": item_id, "prompt_group_id": group, "absolute_errors": errors, "coverage_false": false_dimensions}


def replay(*, execution_root: Path, collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    grok = _admit_grok_result(Path(grok_result_path))
    collector_raw = stable(Path(collector_path))
    if sha256(collector_raw) != COLLECTOR_SHA256:
        raise ValueError("Sol collector drifted")
    collector = strict(collector_raw, "Sol collector")
    cells = collector.get("cells")
    if (
        collector.get("study_id") != EXECUTOR_STUDY_ID
        or collector.get("kind") != "complete_39_desc15_sol_veto_receipts_cardinality_unproven"
        or collector.get("process_launches") != 39
        or collector.get("provider_calls_made") is not None
        or collector.get("native_endpoint_contact_cardinality") != "unproven"
        or collector.get("parent_sol_reference", {}).get("equal_group_mae") != PARENT_SOL_MAE
        or tuple(collector.get("qualified_children", ())) != CHILDREN
        or collector.get("optimizer_result_file_sha256") != GROK_RESULT_FILE_SHA256
        or collector.get("optimizer_result_internal_sha256") != GROK_RESULT_INTERNAL_SHA256
        or not isinstance(cells, list)
        or len(cells) != 39
    ):
        raise ValueError("Sol collector contract drifted")
    projections = [_cell_projection(Path(execution_root), cell) for cell in cells]
    tuples = {(row["candidate_id"], row["item_id"]) for row in projections}
    if len({row["cell_id"] for row in projections}) != 39 or tuples != {(candidate, item) for candidate in CHILDREN for item in ITEMS}:
        raise ValueError("Sol candidate/item geometry is incomplete")
    grouped: dict[str, dict[str, list[float]]] = {candidate: defaultdict(list) for candidate in CHILDREN}
    coverage_false: list[dict[str, str]] = []
    for row in projections:
        grouped[row["candidate_id"]][row["prompt_group_id"]].extend(row["absolute_errors"])
        coverage_false.extend({"candidate_id": row["candidate_id"], "cell_id": row["cell_id"], "dimension": dimension} for dimension in row["coverage_false"])
    metrics = []
    survivors = []
    for candidate in CHILDREN:
        if set(grouped[candidate]) != set(GROUPS):
            raise ValueError("Sol prompt-group geometry is incomplete")
        group_mae = {group: sum(grouped[candidate][group]) / len(grouped[candidate][group]) for group in GROUPS}
        value = sum(group_mae.values()) / len(GROUPS)
        survives = value < PARENT_SOL_MAE
        if survives:
            survivors.append(candidate)
        metrics.append({
            "candidate_id": candidate,
            "cells": 13,
            "coverage_false": [record for record in coverage_false if record["candidate_id"] == candidate],
            "equal_group_mae": value,
            "group_mae": group_mae,
            "absolute_reduction_from_parent": PARENT_SOL_MAE - value,
            "relative_reduction_from_parent": (PARENT_SOL_MAE - value) / PARENT_SOL_MAE,
            "sol_veto_decision": "survives" if survives else "vetoed",
        })
    grok_metrics = {row["candidate_id"]: row["equal_group_mae"] for row in grok.get("metrics", []) if isinstance(row, Mapping) and row.get("candidate_id") in CHILDREN}
    if set(grok_metrics) != set(CHILDREN):
        raise ValueError("Grok metric references drifted")
    result: dict[str, Any] = {
        "authority": {"confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_qualifiers_then_sol_veto_only", "endpoint_pooling": "forbidden"},
        "claim": "Sol vetoed two of the three Grok-qualified children. Only the missing-evidence referent child improved on the exact Sol parent and survives this development veto; no confirmation, promotion, runtime, or generalization claim follows.",
        "coverage": {"booleans": 234, "false_count": len(coverage_false), "false_records": coverage_false},
        "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 39, "provider_calls_made": None},
        "format_version": 1,
        "geometry": {"confirmation_cells": 0, "development_groups": 7, "development_items": 13, "grok_reference_cells": 52, "sol_cells": 39},
        "grok_development_reference": {"endpoint": "grok-4.6", "parent_equal_group_mae": 0.8551587301587302, "metrics": [{"candidate_id": candidate, "equal_group_mae": grok_metrics[candidate]} for candidate in CHILDREN], "role": "qualification_frozen_before_sol"},
        "kind": "desc15_referent_cross_model_development_sol_veto_result",
        "sol_validation": {"endpoint": "gpt-5.6-sol", "parent_candidate_id": PARENT, "parent_equal_group_mae": PARENT_SOL_MAE, "metrics": metrics, "survivors": survivors, "vetoed": [candidate for candidate in CHILDREN if candidate not in survivors], "role": "veto_only_no_sol_favored_substitution"},
        "source": {"collector_sha256": COLLECTOR_SHA256, "executor_commit": EXECUTOR_COMMIT, "executor_sha256": EXECUTOR_SHA256, "grok_optimizer_result_file_sha256": GROK_RESULT_FILE_SHA256, "grok_optimizer_result_internal_sha256": GROK_RESULT_INTERNAL_SHA256},
        "study_id": STUDY_ID,
    }
    result["result_sha256"] = sha256(result)
    return result


def validate_package() -> dict[str, Any]:
    _plain(HERE, directory=True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("public result package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    result = strict(stable(HERE / "result.json"), "public result")
    manifest = strict(stable(HERE / "publication-manifest.json"), "publication manifest")
    expected_manifest = {"files": {name: sha256(stable(HERE / name)) for name in ("README.md", "result.json", "study-contract.json", "verify.py")}, "format_version": 1, "kind": "desc15_referent_sol_veto_result_publication_manifest", "study_id": STUDY_ID}
    expected_contract = {
        "authority": {"confirmation": "unopened", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_qualifiers_then_sol_veto_only"},
        "format_version": 1,
        "geometry": {"confirmation_cells": 0, "development_groups": 7, "development_items": 13, "grok_reference_cells": 52, "sol_cells": 39},
        "kind": "provider_free_desc15_referent_cross_model_sol_veto_replay",
        "pins": {"collector_sha256": COLLECTOR_SHA256, "executor_commit": EXECUTOR_COMMIT, "executor_sha256": EXECUTOR_SHA256, "grok_optimizer_result_file_sha256": GROK_RESULT_FILE_SHA256, "grok_optimizer_result_internal_sha256": GROK_RESULT_INTERNAL_SHA256},
        "prohibitions": ["no caller aggregates", "no imputation", "no endpoint pooling", "no Sol-favored substitution", "no confirmation, promotion, runtime, or generalization claim"],
        "study_id": STUDY_ID,
    }
    if contract != expected_contract or result.get("study_id") != STUDY_ID or result.get("authority") != contract["authority"] or result.get("geometry") != contract["geometry"] or result.get("source") != {"collector_sha256": COLLECTOR_SHA256, "executor_commit": EXECUTOR_COMMIT, "executor_sha256": EXECUTOR_SHA256, "grok_optimizer_result_file_sha256": GROK_RESULT_FILE_SHA256, "grok_optimizer_result_internal_sha256": GROK_RESULT_INTERNAL_SHA256} or result.get("result_sha256") != sha256({key: value for key, value in result.items() if key != "result_sha256"}) or manifest != expected_manifest:
        raise ValueError("public result package drifted")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-root", type=Path, required=True)
    parser.add_argument("--collector-path", type=Path, required=True)
    parser.add_argument("--grok-result-path", type=Path, required=True)
    args = parser.parse_args(argv)
    print(canonical(replay(execution_root=args.execution_root, collector_path=args.collector_path, grok_result_path=args.grok_result_path)).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
