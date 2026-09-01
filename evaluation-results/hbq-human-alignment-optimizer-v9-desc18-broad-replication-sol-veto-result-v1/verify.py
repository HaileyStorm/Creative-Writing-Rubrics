"""Independently replay the exact 64-cell Desc18 Sol veto evidence."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
import stat
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-result-v1"
EXECUTOR_ID = "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1"
EXECUTOR = HERE.parent / EXECUTOR_ID / "executor.py"
EXECUTOR_COMMIT = "926f8f158d2551c2edb6ba40888d875a1aaf18a8"
EXECUTOR_SHA256 = "578a488b8b85b67705e7db1d560134a1c24714ab201efba336ca3611979e72b7"
COLLECTOR_SHA256 = "b8ab670bfb54426640a2c825bb964d0e28c7e16cd7803787c148a12b5240a2e9"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
AUTHORITY = {"confirmation": "unopened", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_qualification_then_sol_veto_only"}
PUBLIC_FILES = {"README.md", "publication-manifest.json", "result.json", "study-contract.json", "verify.py"}
README_SHA256 = "07e0cb5de32837ffe49ff09161bdb76bc2c3fa5b914cf0a0b036d41e3b6dba25"
RESULT_SHA256 = "f74cd54bbe88bd549a86e42ed46dcca4a68252ea168c4cf116225c0a69e06a0f"
CONTRACT_SHA256 = "3ae522fd93a770759195001da46b083b2753e49ec42ff70d0ee6f055cb5c2368"
TEST_SHA256 = "f2f387a4c0b305ae52d0d799f12b25596ff903ad172f80ce91ed6b86d9b4261e"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    target = Path(os.path.abspath(path))
    for current in (target, *target.parents):
        item = os.lstat(current)
        if stat.S_ISLNK(item.st_mode) or bool(getattr(item, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed evidence path")
    before = os.lstat(target)
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after_open = os.fstat(handle.fileno())
    after = os.lstat(target)
    key = lambda item: (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode), item.st_size)
    if key(before) != key(opened) or key(opened) != key(after_open) or key(after_open) != key(after):
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


def _blob(path: Path) -> bytes:
    relative = path.relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{EXECUTOR_COMMIT}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned executor blob is unavailable")
    return result.stdout


def executor_module() -> ModuleType:
    raw = stable(EXECUTOR)
    if sha256(raw) != EXECUTOR_SHA256 or _blob(EXECUTOR) != raw:
        raise ValueError("pinned Sol executor drifted or is not committed")
    spec = importlib.util.spec_from_file_location("_desc18_sol_result_executor", EXECUTOR)
    if spec is None or spec.loader is None:
        raise ValueError("pinned Sol executor cannot load")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if stable(EXECUTOR) != raw:
        raise ValueError("pinned Sol executor changed during load")
    return module


def _projection(module: ModuleType, *, execution_root: Path, collector: Mapping[str, Any], grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolution = module._resolution(grok_execution_root=Path(grok_execution_root), freeze_root=Path(freeze_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path))
    if resolution.get("status") != "qualified" or resolution.get("qualification", {}).get("qualifiers") != [CHILD]:
        raise ValueError("Grok qualification is not the frozen child20-only input")
    expected = {row["cell_id"]: row for row in resolution["rows"]}
    cells = collector.get("cells")
    if not isinstance(cells, list) or len(cells) != 64:
        raise ValueError("incomplete Sol collector")
    rows, coverage_false = [], []
    for supplied in cells:
        if not isinstance(supplied, Mapping) or supplied.get("cell_id") not in expected:
            raise ValueError("unknown or duplicate Sol collector cell")
        row = expected.pop(supplied["cell_id"])
        root = Path(execution_root) / row["cell_id"]
        target_vector = strict(stable(root / "target-vector.json"), "target vector")
        prepared = strict(stable(root / "prepared.json"), "prepared cell")
        payload = stable(root / "outbound-payload.json")
        answer = strict(stable(root / "raw-codex-final-response.bin"), "final response", final=True)
        target = target_vector.get("target")
        if (target_vector.get("cell_id") != row["cell_id"] or target_vector.get("item_id") != row["item_id"] or target_vector.get("story_id") != row["item_id"]
                or target != row["target"] or prepared.get("cell", {}).get("candidate_id") != row["candidate_id"]
                or prepared.get("target_vector_sha256") != sha256(stable(root / "target-vector.json"))
                or prepared.get("task_payload_sha256") != sha256(payload)
                or payload != base64.b64decode(supplied.get("payload_base64", ""), validate=True)
                or supplied.get("payload_sha256") != sha256(payload)
                or supplied.get("human_score_projection") != answer):
            raise ValueError("prepared target/payload/response binding drifted")
        scores, coverage = answer.get("scores"), answer.get("coverage")
        if not isinstance(target, Mapping) or not isinstance(scores, Mapping) or not isinstance(coverage, Mapping) or set(target) != set(DIMENSIONS) or set(scores) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS):
            raise ValueError("Sol response or target geometry drifted")
        errors = []
        for dimension in DIMENSIONS:
            score, truth = scores[dimension], target[dimension]
            if type(score) not in (int, float) or type(truth) not in (int, float) or not math.isfinite(score) or not math.isfinite(truth) or coverage[dimension] is not True:
                raise ValueError("nonfinite or incomplete Sol score/coverage")
            errors.append(abs(float(score) - float(truth)))
        rows.append({"candidate_id": row["candidate_id"], "cell_id": row["cell_id"], "item_id": row["item_id"], "prompt_group_id": row["prompt_group_id"], "item_mae": sum(errors) / len(errors)})
    if expected or len({row["cell_id"] for row in rows}) != 64:
        raise ValueError("incomplete Sol replay geometry")
    return rows, coverage_false


def replay(*, execution_root: Path, collector_path: Path, grok_execution_root: Path, freeze_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    validate_package()
    module = executor_module()
    collector_raw = stable(Path(collector_path)); collector = strict(collector_raw, "Sol collector")
    if sha256(collector_raw) != COLLECTOR_SHA256:
        raise ValueError("wrong immutable Sol collector")
    certificate = module.replay_collector(output_root=Path(execution_root), collector_path=Path(collector_path), authorization_acknowledgement_sha256=ACK, grok_execution_root=Path(grok_execution_root), freeze_root=Path(freeze_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path))
    if certificate.get("collector_sha256") != COLLECTOR_SHA256 or certificate.get("cells") != 64:
        raise ValueError("executor replay certificate drifted")
    rows, coverage_false = _projection(module, execution_root=Path(execution_root), collector=collector, grok_execution_root=Path(grok_execution_root), freeze_root=Path(freeze_root), grok_collector_path=Path(grok_collector_path), grok_result_path=Path(grok_result_path))
    grouped: dict[str, dict[str, list[float]]] = {candidate: defaultdict(list) for candidate in (PARENT, CHILD)}
    for row in rows:
        grouped[row["candidate_id"]][row["prompt_group_id"]].append(row["item_mae"])
    metrics = []
    for candidate in (PARENT, CHILD):
        if len(grouped[candidate]) != 16 or any(len(items) != 2 for items in grouped[candidate].values()):
            raise ValueError("exact 32-item/16-group Sol geometry drifted")
        group_mae = {group: sum(items) / len(items) for group, items in sorted(grouped[candidate].items())}
        metrics.append({"candidate_id": candidate, "cells": 32, "equal_group_mae": sum(group_mae.values()) / 16, "group_mae": group_mae})
    parent, child = metrics
    if coverage_false or not child["equal_group_mae"] < parent["equal_group_mae"]:
        raise ValueError("child20 does not survive Sol veto")
    result = {"authority": AUTHORITY, "claim": "On this exact public/open Desc18 development replay, child20 has lower Sol equal-group MAE than descendant13 and survives the pre-frozen Grok-qualified Sol veto. No promotion, runtime, endpoint-pooling, general, or confirmation claim follows.", "coverage": {"booleans": 384, "false_count": 0, "false_records": []}, "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 64, "provider_calls_made": None}, "format_version": 1, "geometry": {"confirmation_cells": 0, "development_groups": 16, "development_items": 32, "sol_cells": 64}, "kind": "desc18_open_fresh96_cross_model_sol_veto_result", "sol_validation": {"endpoint": "gpt-5.6-sol", "parent_candidate_id": PARENT, "parent_equal_group_mae": parent["equal_group_mae"], "metrics": metrics, "relative_reduction_from_parent": (parent["equal_group_mae"] - child["equal_group_mae"]) / parent["equal_group_mae"], "retained_candidate_id": CHILD, "role": "veto_only_no_sol_favored_substitution", "survivors": [CHILD], "vetoed": []}, "source": {"collector_file_sha256": COLLECTOR_SHA256, "executor_commit": EXECUTOR_COMMIT, "executor_file_sha256": EXECUTOR_SHA256, "executor_replay": certificate, "grok_optimizer_result_file_sha256": module.RESULT_FILE_SHA256, "grok_optimizer_result_internal_sha256": module.RESULT_INTERNAL_SHA256}, "study_id": STUDY_ID}
    result["result_sha256"] = sha256(result)
    return result


def validate_package() -> dict[str, Any]:
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("public result package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    result = strict(stable(HERE / "result.json"), "public result")
    expected_contract = {"authority": AUTHORITY, "format_version": 1, "geometry": {"development_groups": 16, "development_items": 32, "sol_cells": 64}, "kind": "provider_free_desc18_open_fresh96_sol_veto_replay", "pins": {"collector_file_sha256": COLLECTOR_SHA256, "executor_commit": EXECUTOR_COMMIT, "executor_file_sha256": EXECUTOR_SHA256}, "prohibitions": ["no caller aggregates", "no imputation", "no endpoint pooling", "no Sol-favored substitution", "no confirmation promotion runtime or general claim"], "study_id": STUDY_ID}
    test_path = REPO / "tests" / "test_hbq_human_alignment_optimizer_v9_desc18_broad_replication_sol_veto_result_v1.py"
    manifest = strict(stable(HERE / "publication-manifest.json"), "publication manifest")
    expected_manifest = {"files": {"README.md": README_SHA256, "result.json": RESULT_SHA256, "study-contract.json": CONTRACT_SHA256, "test": TEST_SHA256, "verify.py": sha256(stable(HERE / "verify.py"))}, "format_version": 1, "kind": "desc18_sol_veto_result_publication_manifest", "study_id": STUDY_ID}
    if (contract != expected_contract or sha256(stable(HERE / "README.md")) != README_SHA256 or sha256(stable(HERE / "result.json")) != RESULT_SHA256
            or sha256(stable(HERE / "study-contract.json")) != CONTRACT_SHA256 or sha256(stable(test_path)) != TEST_SHA256
            or manifest != expected_manifest or result.get("study_id") != STUDY_ID or result.get("authority") != AUTHORITY
            or result.get("result_sha256") != sha256({key: value for key, value in result.items() if key != "result_sha256"})):
        raise ValueError("public Sol result package drifted")
    return contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("execution-root", "collector-path", "grok-execution-root", "freeze-root", "grok-collector-path", "grok-result-path"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    validate_package()
    print(canonical(replay(execution_root=args.execution_root, collector_path=args.collector_path, grok_execution_root=args.grok_execution_root, freeze_root=args.freeze_root, grok_collector_path=args.grok_collector_path, grok_result_path=args.grok_result_path)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
