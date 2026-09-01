"""Replay the 26-cell descendant-16 Sol veto from immutable local receipts."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-result-v1"
EXECUTOR_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-sol-veto-exec-v1"
EXECUTOR_COMMIT = "9f48ed828e49c640434008979606ccc838cef8da"
EXECUTOR_SHA256 = "fd17b8b2079fe44eddea7aaa611ec6be649503af61ada62cc6f888bee548497c"
COLLECTOR_SHA256 = "d884711a70e88c16ebd5cf1aff12040596ea6d467d3bad3218dda71773dd5654"
GROK_PUBLIC_RESULT_SHA256 = "424a90956d8b68e04bd79b57d3c893dc558b776a087c036057b0dd24a7cbb0fc"
GROK_RESULT_FILE_SHA256 = "53dd32cc52c2f7975f2562e172f735576ae755bf702f3ee687f8e0418c2bdd54"
GROK_RESULT_INTERNAL_SHA256 = "e0c00248520c18676d5ea760c8464195b9b2ea0863f16e2c6cb840ac027f2f9a"
PARENT_RESULT_COMMIT = "79a90ad72ec96d8dcc391f3e8036bfee5b5342d8"
PARENT_RESULT_SHA256 = "23988d59a94988b2604317786f2874fa59b0a411c9aafa677f9be28df32e2e71"
PARENT_PUBLIC_RESULT = HERE.parent / "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-result-v1" / "result.json"
PARENT = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
PARENT_SOL_MAE = 1.0101190476190476
CHILDREN = (
    "broader-nextwave-22-missing_evidence_not_no-referent-contradiction-threshold",
    "broader-nextwave-24-missing_evidence_not_no-referent-dimension-isolation",
)
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
AUTHORITY = {"confirmation": "unopened", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_qualifiers_then_sol_veto_only"}
PUBLIC_FILES = {"README.md", "publication-manifest.json", "result.json", "study-contract.json", "verify.py"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    target = Path(os.path.abspath(path))
    for current in (target, *target.parents):
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed evidence path")
        if stat.S_ISDIR(info.st_mode) != (current != target):
            raise ValueError("evidence path type drifted")
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


def strict(raw: bytes, label: str, *, final: bool = False) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    accepted = (canonical(value), canonical(value)[:-1]) if final else (canonical(value),)
    if type(value) is not dict or raw not in accepted:
        raise ValueError(f"noncanonical {label}")
    return value


def _admit_grok_result(path: Path) -> None:
    raw = stable(path)
    result = strict(raw, "frozen Grok optimizer result")
    if (
        sha256(raw) != GROK_RESULT_FILE_SHA256
        or result.get("result_sha256") != GROK_RESULT_INTERNAL_SHA256
        or sha256({key: value for key, value in result.items() if key != "result_sha256"}) != GROK_RESULT_INTERNAL_SHA256
        or tuple(result.get("qualification", {}).get("qualifiers", ())) != CHILDREN
        or result.get("qualification", {}).get("frozen_before_sol") is not True
    ):
        raise ValueError("frozen Grok qualification result drifted")


def _admit_parent_result() -> None:
    raw = stable(PARENT_PUBLIC_RESULT)
    result = strict(raw, "frozen descendant-15 Sol parent result")
    validation = result.get("sol_validation")
    metrics = validation.get("metrics") if isinstance(validation, Mapping) else None
    matching = [row for row in metrics or () if isinstance(row, Mapping) and row.get("candidate_id") == PARENT]
    if (
        sha256(raw) != PARENT_RESULT_SHA256
        or result.get("study_id") != "hbq-human-alignment-optimizer-v6-desc15-referent-sol-veto-result-v1"
        or not isinstance(metrics, list)
        or len(matching) != 1
        or matching[0].get("equal_group_mae") != PARENT_SOL_MAE
    ):
        raise ValueError("frozen descendant-15 Sol parent result drifted")


def _projection(root: Path, supplied: Mapping[str, Any]) -> dict[str, Any]:
    cell_id = supplied.get("cell_id")
    if not isinstance(cell_id, str) or not cell_id.startswith("desc16-sol-veto-"):
        raise ValueError("invalid Sol cell id")
    cell_root = Path(root) / cell_id
    receipt_raw = stable(cell_root / "execution-receipt.json")
    receipt = strict(receipt_raw, "execution receipt")
    target_raw = stable(cell_root / "target-vector.json")
    target_vector = strict(target_raw, "target vector")
    prepared = strict(stable(cell_root / "prepared.json"), "prepared cell")
    final_raw = stable(cell_root / "raw-codex-final-response.bin")
    answer = strict(final_raw, "final response", final=True)
    cell = receipt.get("cell")
    identity = receipt.get("identity")
    settings = strict(stable(cell_root / "effective-settings.json"), "effective settings")
    payload_raw = stable(cell_root / "outbound-payload.json")
    if not isinstance(cell, Mapping) or not isinstance(identity, Mapping):
        raise TypeError("Sol receipt lacks cell identity")
    candidate, item, group, target = (cell.get(name) for name in ("candidate_id", "item_id", "prompt_group_id", "target"))
    if (
        candidate not in CHILDREN or not isinstance(item, str) or not isinstance(group, str) or not isinstance(target, Mapping)
        or target_vector.get("cell_id") != cell_id or target_vector.get("item_id") != item
        or target_vector.get("story_id") != item or target_vector.get("target") != target
        or prepared.get("cell") != cell or prepared.get("target_vector_sha256") != sha256(target_raw)
        or prepared.get("task_payload_sha256") != sha256(payload_raw)
        or supplied.get("candidate_id") != candidate or supplied.get("source_cell_id") != cell.get("source_cell_id")
        or supplied.get("receipt_sha256") != sha256(receipt_raw) or supplied.get("payload_sha256") != sha256(payload_raw)
        or base64.b64decode(supplied.get("payload_base64", ""), validate=True) != payload_raw
        or supplied.get("final_response_sha256") != sha256(final_raw) or base64.b64decode(supplied.get("final_response_base64", ""), validate=True) != final_raw
        or supplied.get("human_score_projection") != answer or supplied.get("identity") != identity
        or supplied.get("effective_settings") != settings or supplied.get("effective_settings_sha256") != receipt.get("effective_settings_sha256")
        or receipt.get("request_sha256") != sha256(payload_raw) or receipt.get("final_response_sha256") != sha256(final_raw)
        or receipt.get("process_launches") != 1 or receipt.get("provider_calls_made") is not None
        or receipt.get("native_endpoint_contact_cardinality") != "unproven" or identity.get("provider") != "openai_codex"
        or identity.get("requested_model") != "gpt-5.6-sol" or settings.get("tools_enabled") is not False
    ):
        raise ValueError("persisted Sol cell evidence drifted")
    scores, coverage = answer.get("scores"), answer.get("coverage")
    if not isinstance(scores, Mapping) or not isinstance(coverage, Mapping) or set(scores) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS) or set(target) != set(DIMENSIONS):
        raise ValueError("Sol score or target geometry drifted")
    errors, false = [], []
    for dimension in DIMENSIONS:
        score, expected = scores[dimension], target[dimension]
        if type(score) not in (int, float) or type(expected) not in (int, float) or not math.isfinite(score) or not math.isfinite(expected):
            raise ValueError("non-finite Sol score or target")
        errors.append(abs(float(score) - float(expected)))
        if coverage[dimension] is False:
            false.append(dimension)
        elif coverage[dimension] is not True:
            raise ValueError("non-boolean coverage")
    return {"candidate_id": candidate, "cell_id": cell_id, "item_id": item, "prompt_group_id": group, "errors": errors, "coverage_false": false}


def replay(*, execution_root: Path, collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    _admit_grok_result(Path(grok_result_path))
    _admit_parent_result()
    if sha256(stable(HERE.parent / EXECUTOR_ID / "executor.py")) != EXECUTOR_SHA256:
        raise ValueError("pinned Sol executor drifted")
    collector_raw = stable(collector_path)
    collector = strict(collector_raw, "Sol collector")
    cells = collector.get("cells")
    if (
        sha256(collector_raw) != COLLECTOR_SHA256 or collector.get("study_id") != EXECUTOR_ID
        or collector.get("kind") != "complete_derived_desc16_sol_veto_receipts_cardinality_unproven"
        or collector.get("process_launches") != 26 or collector.get("provider_calls_made") is not None
        or collector.get("native_endpoint_contact_cardinality") != "unproven"
        or tuple(collector.get("qualified_children", ())) != CHILDREN
        or collector.get("optimizer_result_file_sha256") != GROK_RESULT_FILE_SHA256
        or collector.get("optimizer_result_internal_sha256") != GROK_RESULT_INTERNAL_SHA256
        or collector.get("parent_sol_reference") != {"candidate_id": PARENT, "equal_group_mae": PARENT_SOL_MAE, "result_commit": PARENT_RESULT_COMMIT, "result_file_sha256": PARENT_RESULT_SHA256}
        or not isinstance(cells, list) or len(cells) != 26
    ):
        raise ValueError("Sol collector contract drifted")
    rows = [_projection(Path(execution_root), cell) for cell in cells]
    expected_pairs = {(candidate, item) for candidate in CHILDREN for item in {row["item_id"] for row in rows}}
    if len({row["cell_id"] for row in rows}) != 26 or len({row["item_id"] for row in rows}) != 13 or {(row["candidate_id"], row["item_id"]) for row in rows} != expected_pairs:
        raise ValueError("Sol candidate/item geometry is incomplete")
    grouped: dict[str, dict[str, list[float]]] = {candidate: defaultdict(list) for candidate in CHILDREN}
    coverage_false = []
    for row in rows:
        grouped[row["candidate_id"]][row["prompt_group_id"]].extend(row["errors"])
        coverage_false.extend({"candidate_id": row["candidate_id"], "cell_id": row["cell_id"], "dimension": dimension} for dimension in row["coverage_false"])
    metrics, survivors = [], []
    for candidate in CHILDREN:
        if len(grouped[candidate]) != 7:
            raise ValueError("Sol prompt-group geometry is incomplete")
        group_mae = {group: sum(values) / len(values) for group, values in sorted(grouped[candidate].items())}
        mae = sum(group_mae.values()) / len(group_mae)
        candidate_false = [row for row in coverage_false if row["candidate_id"] == candidate]
        survives = mae < PARENT_SOL_MAE and not candidate_false
        if survives:
            survivors.append(candidate)
        metrics.append({"candidate_id": candidate, "cells": 13, "coverage_false": candidate_false, "equal_group_mae": mae, "group_mae": group_mae, "absolute_reduction_from_parent": PARENT_SOL_MAE - mae, "relative_reduction_from_parent": (PARENT_SOL_MAE - mae) / PARENT_SOL_MAE, "sol_veto_decision": "survives" if survives else "vetoed"})
    result = {
        "authority": AUTHORITY,
        "claim": "Both desc16 Grok-qualified children were vetoed on Sol, so the exact descendant-15 child20 parent is retained; no confirmation, promotion, runtime, or generalization claim follows.",
        "coverage": {"booleans": 156, "false_count": len(coverage_false), "false_records": coverage_false},
        "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 26, "provider_calls_made": None},
        "format_version": 1,
        "geometry": {"confirmation_cells": 0, "development_groups": 7, "development_items": 13, "grok_reference_cells": 52, "sol_cells": 26},
        "grok_development_reference": {"endpoint": "grok-4.6", "qualified_children": list(CHILDREN), "public_result_file_sha256": GROK_PUBLIC_RESULT_SHA256, "role": "qualification_frozen_before_sol"},
        "kind": "desc16_referent_evidence_cross_model_development_sol_veto_result",
        "sol_validation": {"endpoint": "gpt-5.6-sol", "parent_candidate_id": PARENT, "parent_equal_group_mae": PARENT_SOL_MAE, "metrics": metrics, "survivors": survivors, "vetoed": [candidate for candidate in CHILDREN if candidate not in survivors], "retained_candidate_id": PARENT, "role": "veto_only_no_sol_favored_substitution"},
        "source": {"collector_file_sha256": COLLECTOR_SHA256, "executor_commit": EXECUTOR_COMMIT, "executor_file_sha256": EXECUTOR_SHA256, "grok_public_result_file_sha256": GROK_PUBLIC_RESULT_SHA256, "grok_optimizer_result_file_sha256": GROK_RESULT_FILE_SHA256, "grok_optimizer_result_internal_sha256": GROK_RESULT_INTERNAL_SHA256, "parent_sol_result_commit": PARENT_RESULT_COMMIT, "parent_sol_result_file_sha256": PARENT_RESULT_SHA256},
        "study_id": STUDY_ID,
    }
    result["result_sha256"] = sha256(result)
    return result


def _contract() -> dict[str, Any]:
    return strict(stable(HERE / "study-contract.json"), "study contract")


def validate_package() -> dict[str, Any]:
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("public result package inventory drifted")
    contract, result, manifest = _contract(), strict(stable(HERE / "result.json"), "public result"), strict(stable(HERE / "publication-manifest.json"), "publication manifest")
    expected_manifest = {"files": {name: sha256(stable(HERE / name)) for name in ("README.md", "result.json", "study-contract.json", "verify.py")}, "format_version": 1, "kind": "desc16_referent_evidence_sol_veto_result_publication_manifest", "study_id": STUDY_ID}
    if contract.get("study_id") != STUDY_ID or contract.get("authority") != AUTHORITY or result.get("study_id") != STUDY_ID or result.get("authority") != AUTHORITY or result.get("source") != contract.get("pins") or result.get("result_sha256") != sha256({key: value for key, value in result.items() if key != "result_sha256"}) or manifest != expected_manifest:
        raise ValueError("public result package drifted")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execution-root", type=Path, required=True)
    parser.add_argument("--collector-path", type=Path, required=True)
    parser.add_argument("--grok-result-path", type=Path, required=True)
    args = parser.parse_args(argv)
    validate_package()
    print(canonical(replay(execution_root=args.execution_root, collector_path=args.collector_path, grok_result_path=args.grok_result_path)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
