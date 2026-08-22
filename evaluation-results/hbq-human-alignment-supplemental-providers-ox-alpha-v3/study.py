"""Immutable score-blind Ox Alpha transport-successor bindings."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

from hbqrs import runner as runner_module
from hbqrs.paths import prompts_dir, schema_dir

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
CONTRACT_PATH = HERE / "study-contract.json"
PARENT_ROOT = (HERE / "../hbq-human-alignment-supplemental-providers-ox-alpha-v2").resolve()
FROZEN_NAME = "frozen-ox-alpha-v3-transport-contract.json"


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON key: {key}")
        value[key] = item
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Required file is unavailable: {path}")
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _external_disjoint(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if any(_inside(path, REPO_ROOT) for path in resolved):
        raise ValueError("Ox v3 roots must remain outside the repository")
    for index, left in enumerate(resolved):
        if any(left == right or _inside(left, right) or _inside(right, left) for right in resolved[index + 1:]):
            raise ValueError("Ox v3 work, predecessor, cost, and input roots must be disjoint")


def judge_assets() -> dict[str, Any]:
    prefix = prompts_dir() / "judge" / "JUDGE_PREFIX.md"
    binary = prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"
    schema = schema_dir() / "hbq_judge_response.schema.json"
    return {"strict_ai": False, "judge_prefix": {"included": False, "file": fingerprint(prefix)}, "active_prompts": [fingerprint(binary)], "response_schema": fingerprint(schema)}


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    pilot = value.get("transport_pilot")
    expected = {"cells": 3, "batch_size": 16, "question_count": 16, "batch_attempts": 1, "workers": 1, "timeout_seconds": 100, "maximum_http_seconds_exclusive": 100}
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "evidence_status": "provisional_only"}
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v3" or value.get("frozen_before_execution") is not True or not isinstance(pilot, Mapping) or {key: pilot.get(key) for key in expected} != expected or value.get("provider") != provider:
        raise ValueError("Ox v3 transport contract drifted")
    return value


CONTRACT = load_contract()


def _parent_v2() -> Any:
    parent = CONTRACT["parent_v2"]
    for name, digest in parent["files"].items():
        path = PARENT_ROOT / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"Ox v2 parent file drifted: {name}")
    spec = importlib.util.spec_from_file_location("ox_alpha_v3_parent_v2", PARENT_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Ox v2 parent helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get("study")
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous
    return module


def _tree(root: Path, *, excluded: set[str]) -> dict[str, Any]:
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file() and path.name not in excluded]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _complete_tree(root: Path) -> dict[str, Any]:
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _historical_statuses(evidence_root: Path) -> list[int]:
    statuses: list[int] = []
    for path in sorted(evidence_root.rglob("events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line, object_pairs_hook=_unique)
            if isinstance(event, Mapping) and event.get("event_type") == "http_attempt":
                data = event.get("data")
                if not isinstance(data, Mapping) or isinstance(data.get("status"), bool) or not isinstance(data.get("status"), int):
                    raise ValueError("Failed Ox v2 HTTP event is malformed")
                statuses.append(data["status"])
    return statuses


def failed_v2_commitments(root: Path) -> dict[str, Any]:
    root = root.resolve()
    expected = CONTRACT["failed_v2"]
    committed: dict[str, Any] = {}
    for relative, binding in expected["commitments"].items():
        path = root / relative
        observed = fingerprint(path)
        if observed != {"name": path.name, **binding}:
            raise ValueError(f"Failed Ox v2 commitment drifted: {relative}")
        committed[relative] = {"path": relative, **binding}
    raw_spec = expected["raw_evidence_tree"]
    evidence_root = root / raw_spec["path"]
    observed_tree = {"path": raw_spec["path"], **_tree(evidence_root, excluded=set(raw_spec["excluded"])), "excluded": raw_spec["excluded"]}
    if observed_tree != raw_spec:
        raise ValueError("Failed Ox v2 raw evidence tree drifted")
    if _complete_tree(root) != expected["complete_work_tree"]:
        raise ValueError("Failed Ox v2 root has extra, missing, or drifted terminal evidence")
    if _historical_statuses(evidence_root) != [524, 524]:
        raise ValueError("Failed Ox v2 evidence no longer binds the two HTTP 524 attempts")
    journal = read_json(root / "pilot-journal" / "0001-ox-alpha-v2-01.json")
    if journal.get("status") != "failed" or journal.get("cell_id") != "ox-alpha-v2-01":
        raise ValueError("Failed Ox v2 journal no longer closes its root")
    return {"work_dir": str(root), "commitments": committed, "raw_evidence_tree": observed_tree, "historical_http_statuses": [524, 524]}


def runtime_bindings() -> dict[str, Any]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    paths = {"runner": Path(runner_module.__file__), "launcher": launcher, "bridge": launcher.parent / "nous_codex_bridge.py"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("Canonical Nous transport runtime is unavailable")
    return {name: fingerprint(path) for name, path in paths.items()}


def _cells(failed_root: Path) -> tuple[Any, list[dict[str, Any]], list[Path]]:
    parent = _parent_v2()
    # The predecessor's complete immutable work tree is checked before this read.
    # Its execution runtime is historical and no longer needs to match today's bridge.
    frozen = parent.read_json(failed_root / parent.FROZEN_NAME)
    inherited = frozen.get("cells")
    if not isinstance(inherited, list) or len(inherited) != 3:
        raise ValueError("Failed Ox v2 root lacks three frozen public cells")
    result: list[dict[str, Any]] = []
    input_roots: list[Path] = []
    for number, cell in enumerate(inherited, 1):
        if not isinstance(cell, Mapping):
            raise ValueError("Failed Ox v2 cell is malformed")
        artifact, prompt, task = parent.input_paths(cell)
        if artifact.parent != prompt.parent or artifact.parent != task.parent:
            raise ValueError("Ox v3 expects one public input root per predecessor cell")
        input_roots.append(artifact.parent.resolve())
        identifiers = list(cell.get("primary_question_ids", []))[:16]
        if len(identifiers) != 16 or len(set(identifiers)) != 16:
            raise ValueError("Failed Ox v2 cannot supply a 16-leaf transport cell")
        result.append({"cell_id": f"ox-alpha-v3-{number:02d}", "item_id": cell.get("item_id"), "inputs": cell.get("inputs"), "paths": cell.get("paths"), "question_ids": identifiers})
    if len({cell["item_id"] for cell in result}) != 3 or any(not isinstance(cell["item_id"], str) for cell in result):
        raise ValueError("Ox v3 requires three distinct public cells")
    return parent, result, input_roots


def _fresh_zero_proof(parent: Any, proof_path: Path, checked_at: str) -> dict[str, Any]:
    proof = parent._zero_cost_proof(proof_path)
    parent._assert_fresh_at(proof, checked_at)
    return proof


def _external_roots(work: Path, failed: Mapping[str, Any], proof: Mapping[str, Any], input_roots: list[Path]) -> dict[str, Any]:
    failed_root = Path(str(failed.get("work_dir", "")))
    proof_path = Path(str(proof.get("path", "")))
    catalog = Path(str(proof.get("catalog", {}).get("root", ""))) if isinstance(proof.get("catalog"), Mapping) else Path()
    usage = Path(str(proof.get("usage", {}).get("root", ""))) if isinstance(proof.get("usage"), Mapping) else Path()
    roots = [work, failed_root, proof_path, catalog, usage, *input_roots]
    if any(not str(path) or str(path) == "." for path in roots):
        raise ValueError("Ox v3 external root binding is malformed")
    _external_disjoint(*roots)
    return {"work": str(work.resolve()), "failed_v2": str(failed_root.resolve()), "zero_cost_proof": str(proof_path.resolve()), "zero_cost_catalog": str(catalog.resolve()), "zero_cost_usage": str(usage.resolve()), "inputs": [str(path.resolve()) for path in input_roots]}


def freeze_work(failed_v2_work: Path, zero_cost_proof: Path, work: Path) -> dict[str, Any]:
    if work.exists() and any(work.iterdir()):
        raise ValueError("Ox v3 requires a fresh empty external work root")
    failed = failed_v2_commitments(failed_v2_work)
    parent, cells, input_roots = _cells(failed_v2_work)
    checked_at = datetime.now(timezone.utc).isoformat()
    proof = _fresh_zero_proof(parent, zero_cost_proof, checked_at)
    roots = _external_roots(work, failed, proof, input_roots)
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": roots, "failed_v2": failed, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**proof, "freshness_checked_at": checked_at}, "cells": cells}
    immutable_json(work / FROZEN_NAME, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    failed = value.get("failed_v2")
    if not isinstance(failed, Mapping):
        raise ValueError("Ox v3 frozen contract lacks its failed-v2 binding")
    parent, cells, input_roots = _cells(Path(str(failed.get("work_dir", ""))))
    proof = value.get("zero_cost_proof")
    if not isinstance(proof, Mapping):
        raise ValueError("Ox v3 frozen contract lacks zero-cost proof")
    current_proof = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), str(proof.get("freshness_checked_at", "")))
    current_failed = failed_v2_commitments(Path(str(failed.get("work_dir", ""))))
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, current_failed, current_proof, input_roots), "failed_v2": current_failed, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**current_proof, "freshness_checked_at": proof.get("freshness_checked_at")}, "cells": cells}
    if value != expected:
        raise ValueError("Ox v3 frozen transport contract drifted")
    return value


def assert_invocation_freshness(frozen: Mapping[str, Any], checked_at: str) -> None:
    parent, _, _ = _cells(Path(str(frozen["failed_v2"]["work_dir"])))
    sealed = frozen.get("zero_cost_proof")
    if not isinstance(sealed, Mapping):
        raise ValueError("Ox v3 zero-cost proof is malformed")
    proof = _fresh_zero_proof(parent, Path(str(sealed.get("path", ""))), checked_at)
    if sealed != {**proof, "freshness_checked_at": sealed.get("freshness_checked_at")}:
        raise ValueError("Ox v3 zero-cost proof drifted before launch")


def assert_launch_freshness(frozen: Mapping[str, Any]) -> None:
    assert_invocation_freshness(frozen, datetime.now(timezone.utc).isoformat())


def input_paths(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    parent, cells, _ = _cells(Path(str(frozen["failed_v2"]["work_dir"])))
    inherited = parent.read_json(Path(str(frozen["failed_v2"]["work_dir"])) / parent.FROZEN_NAME)
    index = next((number for number, candidate in enumerate(cells) if candidate == cell), None)
    if index is None:
        raise ValueError("Ox v3 cell is not frozen")
    artifact, prompt, task = parent.input_paths(inherited["cells"][index])
    if {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)} != cell.get("inputs"):
        raise ValueError("Ox v3 cell input bytes drifted")
    return artifact, prompt, task
