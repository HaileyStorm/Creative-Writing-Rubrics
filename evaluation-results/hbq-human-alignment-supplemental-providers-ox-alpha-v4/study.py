"""Immutable bindings for the score-blind Ox Alpha v4 transport successor."""
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
PARENT_ROOT = (HERE / "../hbq-human-alignment-supplemental-providers-ox-alpha-v3").resolve()
FROZEN_NAME = "frozen-ox-alpha-v4-transport-contract.json"


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


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
        raise ValueError("Ox v4 roots must remain outside the repository")
    for index, left in enumerate(resolved):
        if any(left == right or _inside(left, right) or _inside(right, left) for right in resolved[index + 1:]):
            raise ValueError("Ox v4 work, predecessor, cost, and input roots must be disjoint")


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
    policy = value.get("transport_pilot")
    expected = {"cells": 3, "batch_size": 8, "question_count": 8, "batch_attempts": 1, "workers": 1, "timeout_seconds": 240, "maximum_http_seconds_exclusive": 100}
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "evidence_status": "provisional_only"}
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v4" or value.get("frozen_before_execution") is not True or not isinstance(policy, Mapping) or {key: policy.get(key) for key in expected} != expected or value.get("provider") != provider:
        raise ValueError("Ox v4 transport contract drifted")
    return value


CONTRACT = load_contract()


def _parent_v3() -> Any:
    parent = CONTRACT["parent_v3"]
    for name, digest in parent["files"].items():
        path = PARENT_ROOT / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"Ox v3 parent file drifted: {name}")
    spec = importlib.util.spec_from_file_location("ox_alpha_v4_parent_v3", PARENT_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Ox v3 parent helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get("study")
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if prior is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = prior
    if module.CONTRACT.get("study_id") != parent["study_id"]:
        raise ValueError("Ox v3 parent contract is not the pinned study")
    return module


def _tree(root: Path, *, excluded: set[str] = set()) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"Required evidence tree is unavailable: {root}")
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file() and path.name not in excluded]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _historical_http_attempts(evidence_root: Path) -> list[dict[str, int]]:
    attempts: list[dict[str, int]] = []
    for path in sorted(evidence_root.rglob("events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line, object_pairs_hook=_unique)
            if not isinstance(event, Mapping) or event.get("event_type") != "http_attempt":
                continue
            data = event.get("data")
            if not isinstance(data, Mapping):
                raise ValueError("Failed Ox v3 HTTP event is malformed")
            status, started, finished = data.get("status"), data.get("http_started_monotonic_ns"), data.get("http_finished_monotonic_ns")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in (status, started, finished)) or finished <= started:
                raise ValueError("Failed Ox v3 HTTP event is malformed")
            attempts.append({"status": status, "duration_ns": finished - started})
    return attempts


def failed_v3_commitments(root: Path) -> dict[str, Any]:
    root = root.resolve()
    expected = CONTRACT["failed_v3"]
    committed: dict[str, Any] = {}
    for relative, binding in expected["commitments"].items():
        path = root / relative
        observed = fingerprint(path)
        if observed != {"name": path.name, **binding}:
            raise ValueError(f"Failed Ox v3 commitment drifted: {relative}")
        committed[relative] = {"path": relative, **binding}
    raw_spec = expected["raw_evidence_tree"]
    evidence_root = root / raw_spec["path"]
    observed_tree = {"path": raw_spec["path"], **_tree(evidence_root, excluded=set(raw_spec["excluded"])), "excluded": raw_spec["excluded"]}
    if observed_tree != raw_spec:
        raise ValueError("Failed Ox v3 raw evidence tree drifted")
    if _tree(root) != expected["complete_work_tree"]:
        raise ValueError("Failed Ox v3 root has extra, missing, or drifted terminal evidence")
    attempts = _historical_http_attempts(evidence_root)
    if len(attempts) != 1 or attempts[0]["status"] != 524 or attempts[0]["duration_ns"] <= 100_000_000_000:
        raise ValueError("Failed Ox v3 does not prove one cap-1 HTTP 524 request exceeding 100 seconds")
    journal = read_json(root / "pilot-journal" / "0001-ox-alpha-v3-01.json")
    if journal.get("status") != "failed" or journal.get("cell_id") != "ox-alpha-v3-01":
        raise ValueError("Failed Ox v3 journal no longer closes its root")
    run = root / "runs" / "pilot" / "ox-alpha-v3-01"
    if (run / "responses" / "batch-0001.json").exists() or (root / "pilot-receipts").exists():
        raise ValueError("Failed Ox v3 unexpectedly contains an accepted result")
    return {"work_dir": str(root), "commitments": committed, "raw_evidence_tree": observed_tree, "historical_http_attempts": attempts, "accepted_result": False}


def runtime_bindings() -> dict[str, Any]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    paths = {"runner": Path(runner_module.__file__), "launcher": launcher, "bridge": launcher.parent / "nous_codex_bridge.py"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("Canonical Nous transport runtime is unavailable")
    return {name: fingerprint(path) for name, path in paths.items()}


def judge_assets() -> dict[str, Any]:
    prefix = prompts_dir() / "judge" / "JUDGE_PREFIX.md"
    binary = prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"
    schema = schema_dir() / "hbq_judge_response.schema.json"
    return {"strict_ai": False, "judge_prefix": {"included": False, "file": fingerprint(prefix)}, "active_prompts": [fingerprint(binary)], "response_schema": fingerprint(schema)}


def _cells(failed_root: Path) -> tuple[Any, list[dict[str, Any]], list[Path]]:
    parent = _parent_v3()
    frozen = read_json(failed_root / parent.FROZEN_NAME)
    inherited = frozen.get("cells")
    if not isinstance(inherited, list) or len(inherited) != 3:
        raise ValueError("Failed Ox v3 root lacks three frozen public cells")
    result: list[dict[str, Any]] = []
    input_roots: list[Path] = []
    for number, cell in enumerate(inherited, 1):
        if not isinstance(cell, Mapping):
            raise ValueError("Failed Ox v3 cell is malformed")
        inputs, paths = cell.get("inputs"), cell.get("paths")
        if not isinstance(inputs, Mapping) or not isinstance(paths, Mapping):
            raise ValueError("Failed Ox v3 cell lacks frozen public inputs")
        artifact, prompt, task = (Path(str(paths.get(key, ""))) for key in ("artifact", "prompt", "task_contract"))
        if artifact.parent != prompt.parent or artifact.parent != task.parent:
            raise ValueError("Ox v4 expects one public input root per predecessor cell")
        observed = {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)}
        if observed != inputs:
            raise ValueError("Failed Ox v3 public input bytes drifted")
        question_ids = list(cell.get("question_ids", []))[:8]
        if len(question_ids) != 8 or len(set(question_ids)) != 8 or any(not isinstance(value, str) for value in question_ids):
            raise ValueError("Failed Ox v3 cannot supply an eight-leaf transport cell")
        item_id = cell.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("Failed Ox v3 cell has no public item identifier")
        input_roots.append(artifact.parent.resolve())
        result.append({"cell_id": f"ox-alpha-v4-{number:02d}", "item_id": item_id, "inputs": observed, "paths": dict(paths), "question_ids": question_ids})
    if len({cell["item_id"] for cell in result}) != 3:
        raise ValueError("Ox v4 requires three distinct public cells")
    return parent, result, input_roots


def _fresh_zero_proof(parent: Any, proof_path: Path, checked_at: str) -> dict[str, Any]:
    proof = parent._fresh_zero_proof(parent._parent_v2(), proof_path, checked_at)
    return proof


def _external_roots(work: Path, failed: Mapping[str, Any], proof: Mapping[str, Any], input_roots: list[Path]) -> dict[str, Any]:
    failed_root = Path(str(failed.get("work_dir", "")))
    proof_path = Path(str(proof.get("path", "")))
    catalog = Path(str(proof.get("catalog", {}).get("root", ""))) if isinstance(proof.get("catalog"), Mapping) else Path()
    usage = Path(str(proof.get("usage", {}).get("root", ""))) if isinstance(proof.get("usage"), Mapping) else Path()
    roots = [work, failed_root, proof_path, catalog, usage, *input_roots]
    if any(not str(path) or str(path) == "." for path in roots):
        raise ValueError("Ox v4 external root binding is malformed")
    _external_disjoint(*roots)
    return {"work": str(work.resolve()), "failed_v3": str(failed_root.resolve()), "zero_cost_proof": str(proof_path.resolve()), "zero_cost_catalog": str(catalog.resolve()), "zero_cost_usage": str(usage.resolve()), "inputs": [str(path.resolve()) for path in input_roots]}


def freeze_work(failed_v3_work: Path, zero_cost_proof: Path, work: Path) -> dict[str, Any]:
    if work.exists() and any(work.iterdir()):
        raise ValueError("Ox v4 requires a fresh empty external work root")
    failed = failed_v3_commitments(failed_v3_work)
    parent, cells, input_roots = _cells(failed_v3_work)
    checked_at = datetime.now(timezone.utc).isoformat()
    proof = _fresh_zero_proof(parent, zero_cost_proof, checked_at)
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, failed, proof, input_roots), "failed_v3": failed, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**proof, "freshness_checked_at": checked_at}, "cells": cells}
    immutable_json(work / FROZEN_NAME, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    failed = value.get("failed_v3")
    if not isinstance(failed, Mapping):
        raise ValueError("Ox v4 frozen contract lacks its failed-v3 binding")
    parent, cells, input_roots = _cells(Path(str(failed.get("work_dir", ""))))
    current_failed = failed_v3_commitments(Path(str(failed.get("work_dir", ""))))
    proof = value.get("zero_cost_proof")
    if not isinstance(proof, Mapping) or not isinstance(proof.get("freshness_checked_at"), str):
        raise ValueError("Ox v4 frozen contract lacks zero-cost proof")
    current_proof = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), proof["freshness_checked_at"])
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, current_failed, current_proof, input_roots), "failed_v3": current_failed, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**current_proof, "freshness_checked_at": proof["freshness_checked_at"]}, "cells": cells}
    if value != expected:
        raise ValueError("Ox v4 frozen transport contract drifted")
    return value


def assert_invocation_freshness(frozen: Mapping[str, Any], checked_at: str) -> None:
    parent, _, _ = _cells(Path(str(frozen["failed_v3"]["work_dir"])))
    proof = frozen.get("zero_cost_proof")
    if not isinstance(proof, Mapping):
        raise ValueError("Ox v4 zero-cost proof is malformed")
    current = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), checked_at)
    if proof != {**current, "freshness_checked_at": proof.get("freshness_checked_at")}:
        raise ValueError("Ox v4 zero-cost proof drifted at the required freshness point")


def assert_launch_freshness(frozen: Mapping[str, Any]) -> None:
    assert_invocation_freshness(frozen, datetime.now(timezone.utc).isoformat())


def input_paths(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    paths = cell.get("paths")
    if not isinstance(paths, Mapping):
        raise ValueError("Ox v4 cell paths are malformed")
    artifact, prompt, task = (Path(str(paths.get(key, ""))) for key in ("artifact", "prompt", "task_contract"))
    observed = {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)}
    if observed != cell.get("inputs"):
        raise ValueError("Ox v4 cell input bytes drifted")
    if cell not in frozen.get("cells", []):
        raise ValueError("Ox v4 cell is not frozen")
    return artifact, prompt, task
