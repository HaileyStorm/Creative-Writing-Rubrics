"""Strict, endpoint-separated Fresh96 validation analysis from closed evidence roots."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FREEZE = HERE.parent / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
STUDY_ID = "hbq-human-alignment-hanna96-validation-analysis-v1"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ENDPOINT_FILES = {"grok.json": "grok-4.6", "sol.json": "gpt-5.6-sol"}
EXPECTED_EXECUTOR_BINDINGS = {
    "grok-4.6": {"executor_id": "hbq-human-alignment-hanna96-validation-grok-exec-v1", "executor_sha256": "91fa17d51b5f5449998884cda7fe7cf26992dc96931726153f8a308aa4c2ea5b"},
    "gpt-5.6-sol": {"executor_id": "hbq-human-alignment-hanna96-validation-sol-exec-v1", "executor_sha256": "3bcc05b3f201b234419f4288a5bd183cd4de53b138b9ee6841356dffc58ac7f0"},
}
PROJECTION_FIELDS = {"endpoint", "cell_id", "candidate_id", "payload_sha256", "source_binding_sha256", "target_sha256", "scores"}
SET_FIELDS = {"format_version", "study_id", "kind", "endpoint", "executor_binding", "schedule_sha256", "projections", "projection_set_sha256"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("reparsed filesystem artifact")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected filesystem artifact type")


def _safe_ancestry(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    if current.exists():
        _plain(current, directory=True)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=current != absolute or current.is_dir())
    return absolute


def _stable(path: Path) -> bytes:
    path = _safe_ancestry(Path(path))
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def strict(path: Path, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    raw = _stable(path)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _freeze():
    spec = importlib.util.spec_from_file_location("_fresh96_freeze", FREEZE)
    if spec is None or spec.loader is None:
        raise ValueError("Fresh96 freeze module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _projection_set(path: Path, expected_endpoint: str, schedule_sha256: str) -> dict[str, Any]:
    value = strict(path, "endpoint projection set")
    if set(value) != SET_FIELDS or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("kind") != "persisted_endpoint_cell_projection_set" or value.get("endpoint") != expected_endpoint or value.get("schedule_sha256") != schedule_sha256:
        raise ValueError("projection set identity drifted")
    body = dict(value)
    declared = body.pop("projection_set_sha256", None)
    if not isinstance(declared, str) or declared != sha256(body):
        raise ValueError("projection-set commitment drifted")
    binding = value.get("executor_binding")
    if not isinstance(binding, Mapping) or dict(binding) != EXPECTED_EXECUTOR_BINDINGS[expected_endpoint]:
        raise ValueError("projection executor binding drifted")
    rows = value.get("projections")
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("projection row is invalid")
    return {"projections": [dict(row) for row in rows], "projection_set_sha256": declared, "executor_binding": dict(binding)}


def _analyze(schedule: Mapping[str, Any], endpoint_sets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    freeze = _freeze()
    freeze.validate_schedule(schedule)
    if canonical(schedule) != canonical(freeze.build()):
        raise ValueError("schedule differs from the pinned Fresh96 construction")
    cells = {row["cell_id"]: row for row in schedule["cells"]}
    endpoint_metrics = []
    for endpoint in sorted(ENDPOINT_FILES.values()):
        evidence = endpoint_sets.get(endpoint)
        rows = evidence.get("projections") if isinstance(evidence, Mapping) else None
        if not isinstance(rows, list) or len(rows) != 64:
            raise ValueError("endpoint requires exactly 64 persisted projections")
        seen: set[str] = set()
        observations: list[tuple[str, str, float]] = []
        for projection in rows:
            if set(projection) != PROJECTION_FIELDS or projection.get("endpoint") != endpoint:
                raise ValueError("aggregate-only or malformed projection rejected")
            cell_id = projection.get("cell_id")
            if not isinstance(cell_id, str) or cell_id in seen:
                raise ValueError("projection cell is duplicate or invalid")
            seen.add(cell_id)
            cell = cells.get(cell_id)
            if cell is None or projection.get("candidate_id") != cell["candidate_id"] or projection.get("payload_sha256") != cell["payload_sha256"] or projection.get("source_binding_sha256") != cell["source_binding_sha256"] or projection.get("target_sha256") != cell["target_sha256"]:
                raise ValueError("projection cell binding drifted")
            scores = projection.get("scores")
            if not isinstance(scores, Mapping) or set(scores) != set(DIMENSIONS) or any(type(scores[d]) not in (int, float) or not math.isfinite(scores[d]) or not 0 <= scores[d] <= 5 for d in DIMENSIONS):
                raise ValueError("projection scores must be finite 0..5 six-dimension values")
            mae = sum(abs(float(scores[d]) - float(cell["target"][d])) for d in DIMENSIONS) / len(DIMENSIONS)
            observations.append((cell["candidate_id"], cell["prompt_group_id"], mae))
        if seen != set(cells):
            raise ValueError("endpoint is partial or contains unscheduled cells")
        candidates = []
        for candidate_id in sorted({cell["candidate_id"] for cell in cells.values()}):
            groups = {group: [mae for candidate, observed_group, mae in observations if candidate == candidate_id and observed_group == group] for group in sorted({cell["prompt_group_id"] for cell in cells.values()})}
            if len(groups) != 16 or any(len(values) != 2 for values in groups.values()):
                raise ValueError("candidate group geometry drifted")
            group_mae = [sum(values) / len(values) for values in groups.values()]
            candidates.append({"candidate_id": candidate_id, "items": 32, "groups": 16, "equal_group_mae": sum(group_mae) / len(group_mae)})
        endpoint_metrics.append({"endpoint": endpoint, "cells": 64, "executor_binding": evidence["executor_binding"], "projection_set_sha256": evidence["projection_set_sha256"], "candidates": candidates})
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "endpoint_separated_fresh96_validation_mae", "schedule_sha256": schedule["schedule_sha256"], "endpoint_metrics": endpoint_metrics, "authority": {"endpoint_pooling": "forbidden", "imputation": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"}, "interpretation": "Validation-only endpoint-separated measurement; no pooling, imputation, selection, confirmation, or generalization claim."}
    value["result_sha256"] = sha256(value)
    return value


def analyze_frozen_roots(schedule_root: Path, projection_root: Path) -> dict[str, Any]:
    """Analyze only a closed schedule root and a closed pair of endpoint projections."""
    schedule = _freeze().validate_frozen_root(schedule_root)
    root = _safe_ancestry(Path(projection_root))
    _plain(root, directory=True)
    if {entry.name for entry in root.iterdir()} != set(ENDPOINT_FILES):
        raise ValueError("projection root inventory drifted")
    sets = {endpoint: _projection_set(root / filename, endpoint, schedule["schedule_sha256"]) for filename, endpoint in ENDPOINT_FILES.items()}
    return _analyze(schedule, sets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--schedule-root", type=Path, required=True)
    parser.add_argument("--projection-root", type=Path, required=True)
    args = parser.parse_args()
    print(canonical(analyze_frozen_roots(args.schedule_root, args.projection_root)).decode("utf-8"), end="")
