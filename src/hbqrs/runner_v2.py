"""Current score-run entry point that preserves a v1 parent and writes a v2 descendant."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from . import core
from .runner import run_judge as run_judge_v1
from .scoring_v2 import score_bundle, score_report_version
from .weights import materialize_weight_profile


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write_or_verify(path: Path, value: Mapping[str, Any]) -> None:
    payload = _json_bytes(value)
    if path.is_file():
        if path.read_bytes() != payload:
            raise core.HBQError(f"Persisted v2 score descendant changed: {path}")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _canonical_projection(report: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(report)
    for key in ("$schema", "report_version", "confidence_diagnostics", "parent_score_sha256"):
        value.pop(key, None)
    return value


def persist_v2_descendant(
    *,
    output_dir: str | Path,
    registry: str | Path,
    bundles: str | Path,
    weight_profile: Mapping[str, Any] | None,
    task_contract_path: str | Path | None,
) -> Path | None:
    """Create ``score.v2.json`` from a completed immutable v1 score parent."""

    directory = Path(output_dir).resolve()
    parent_path = directory / "score.json"
    if not parent_path.is_file():
        return None
    parent_bytes = parent_path.read_bytes()
    parent = core.load_data(parent_path)
    if not isinstance(parent, Mapping) or score_report_version(parent) != 1:
        raise core.HBQError(f"Score parent is not an unversioned v1 report: {parent_path}")
    modules = core.load_modules(registry)
    bundle = core.resolve_bundle(core.load_bundles(bundles), str(parent["bundle_id"]))
    materialized_modules, materialized_bundle, weight_audit = materialize_weight_profile(
        modules, bundle, weight_profile
    )
    task_contract = None
    if task_contract_path is not None:
        loaded_contract = core.load_data(task_contract_path)
        if not isinstance(loaded_contract, Mapping):
            raise core.HBQError(f"Task contract must be an object: {task_contract_path}")
        task_contract = loaded_contract
    descendant = score_bundle(
        materialized_modules,
        materialized_bundle,
        core.load_verdicts(directory / "verdicts.jsonl"),
        artifact_id=str(parent["artifact_id"]),
        task_contract=task_contract,
    )
    descendant["weight_profile"] = parent.get("weight_profile", weight_audit)
    descendant["parent_score_sha256"] = hashlib.sha256(parent_bytes).hexdigest()
    if _canonical_projection(descendant) != _canonical_projection(parent):
        raise core.HBQError(f"v2 canonical projection differs from v1 parent: {parent_path}")
    target = directory / "score.v2.json"
    _atomic_write_or_verify(target, descendant)
    return target


def run_judge(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run frozen v1 judging, then atomically persist its deterministic v2 descendant."""

    bound = inspect.signature(run_judge_v1).bind(*args, **kwargs)
    bound.apply_defaults()
    summary = run_judge_v1(*args, **kwargs)
    descendant = persist_v2_descendant(
        output_dir=bound.arguments["output_dir"],
        registry=bound.arguments["registry"],
        bundles=bound.arguments["bundles"],
        weight_profile=bound.arguments["weight_profile"],
        task_contract_path=bound.arguments["task_contract_path"],
    )
    if descendant is None:
        return summary
    return {**summary, "score_report_version": 2, "score_v2": str(descendant)}
