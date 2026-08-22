"""Immutable bindings for the score-blind Ox Alpha v5 transport successor."""
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
PARENT_ROOT = (HERE / "../hbq-human-alignment-supplemental-providers-ox-alpha-v4").resolve()
FROZEN_NAME = "frozen-ox-alpha-v5-transport-contract.json"
V4_COMPLETE_TREE = {"files": 21, "sha256": "7fac71f91b0e547d9d8aaebb84a9e35540c9519f70b485c1f0dd63cfe56c7e05"}
V4_FILES = {
    "README.md": "27810505e7884f1e736fd0a09afdb2dbd3cb8a38439807683fc2b00743cf0c21",
    "prepare_transport_successor.py": "40b67aff8e07f4270ce557e0a62e6fba9595c58fff697a5546453476fd4db926",
    "run_transport_pilot.py": "815a4bbfd74cdbb5c4b85106490ce57ecdf35d252cf400ff6652b1e549c1e6be",
    "study-contract.json": "4168e34c0db21135c32c1f7c1b7278e2e8e1b7555b60042f9bb5ce8e64c29a1f",
    "study.py": "db00c98baa0d9ddf8b25c36611bd8ffbeda89b1f6bf7d4a161b4a07521850c32",
    "verify_transport_pilot.py": "5a1a98007398eff794a76eef993a78a995539f4306ad2274f35aeefb32e86968",
}


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


def _tree(root: Path) -> dict[str, Any]:
    if not root.is_dir():
        raise ValueError(f"Required evidence tree is unavailable: {root}")
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"files": len(entries), "sha256": hashlib.sha256(canonical(entries)).hexdigest()}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _external_disjoint(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if any(_inside(path, REPO_ROOT) for path in resolved):
        raise ValueError("Ox v5 roots must remain outside the repository")
    for index, left in enumerate(resolved):
        if any(left == right or _inside(left, right) or _inside(right, left) for right in resolved[index + 1:]):
            raise ValueError("Ox v5 work, predecessor, cost, and input roots must be disjoint")


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered); output.flush(); os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != rendered:
                raise ValueError(f"Immutable record drifted: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    expected = {"cells": 3, "batch_size": 4, "question_count": 4, "batch_attempts": 1, "workers": 1, "timeout_seconds": 240, "maximum_http_seconds_exclusive": 100}
    provider = {"provider_id": "ox_alpha_max", "provider": "nous", "model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "reasoning": "max", "allow_unattested_reasoning": True, "evidence_status": "provisional_only"}
    if value.get("format_version") != 1 or value.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v5" or value.get("frozen_before_execution") is not True or not isinstance(value.get("transport_pilot"), Mapping) or {key: value["transport_pilot"].get(key) for key in expected} != expected or value.get("provider") != provider:
        raise ValueError("Ox v5 transport contract drifted")
    return value


CONTRACT = load_contract()


def _parent_v4() -> Any:
    for name, digest in V4_FILES.items():
        path = PARENT_ROOT / name
        if not path.is_file() or sha(path) != digest:
            raise ValueError(f"Ox v4 parent file drifted: {name}")
    spec = importlib.util.spec_from_file_location("ox_alpha_v5_parent_v4", PARENT_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Ox v4 parent helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    prior = sys.modules.get("study")
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if prior is None: sys.modules.pop("study", None)
        else: sys.modules["study"] = prior
    if module.CONTRACT.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v4":
        raise ValueError("Ox v4 parent contract is not the pinned study")
    return module


def _http_attempts(evidence: Path) -> list[dict[str, int]]:
    attempts: list[dict[str, int]] = []
    for path in sorted(evidence.rglob("events.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line, object_pairs_hook=_unique)
            if not isinstance(event, Mapping) or event.get("event_type") != "http_attempt": continue
            data = event.get("data")
            if not isinstance(data, Mapping): raise ValueError("Uncertain Ox v4 HTTP event is malformed")
            status, started, finished = data.get("status"), data.get("http_started_monotonic_ns"), data.get("http_finished_monotonic_ns")
            if any(isinstance(item, bool) or not isinstance(item, int) for item in (status, started, finished)) or finished <= started:
                raise ValueError("Uncertain Ox v4 HTTP event is malformed")
            attempts.append({"status": status, "duration_ns": finished - started})
    return attempts


def uncertain_v4_commitments(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if _tree(root) != V4_COMPLETE_TREE:
        raise ValueError("Uncertain Ox v4 root has extra, missing, or drifted evidence")
    committed = {relative: fingerprint(root / relative) for relative in ("frozen-ox-alpha-v4-transport-contract.json", "pilot-execution-claim.json", "pilot-invocation.json", "pilot-uncertain.json")}
    uncertain = read_json(root / "pilot-uncertain.json")
    if uncertain.get("study_id") != "hbq-human-alignment-supplemental-providers-ox-alpha-v4" or uncertain.get("kind") != "blocked_uncertain_transport_outcome" or uncertain.get("cell_id") != "ox-alpha-v4-01" or uncertain.get("reason") != "terminal_bridge_quiescence_unproven:ValueError":
        raise ValueError("Ox v4 root is not permanently blocked and uncertain")
    if (root / "pilot-journal").exists() or (root / "pilot-receipts").exists():
        raise ValueError("Uncertain Ox v4 root has forbidden later completion mutation")
    run = root / "runs" / "pilot" / "ox-alpha-v4-01"
    checkpoint = read_json(run / "responses" / "batch-0001.json")
    provider = checkpoint.get("provider")
    if checkpoint.get("accepted_attempt") != 1 or not isinstance(provider, Mapping) or provider.get("logical_provider_request_count") != 1 or provider.get("physical_http_attempt_count") != 1 or provider.get("recovered_request_count") != 0:
        raise ValueError("Uncertain Ox v4 root lacks its cap-1 accepted checkpoint")
    message = run / "responses" / "batch-0001.accepted-0001.message.txt"
    if not message.is_file() or not message.read_text(encoding="utf-8").strip():
        raise ValueError("Uncertain Ox v4 root lacks its accepted message")
    evidence = run / "responses" / "batch-0001.attempt-0001.nous.evidence"
    attempts = _http_attempts(evidence)
    if attempts != [{"status": 200, "duration_ns": 111_868_373_300}]:
        raise ValueError("Uncertain Ox v4 does not prove one cap-1 HTTP 200 at the sealed raw duration")
    return {"work_dir": str(root), "complete_work_tree": V4_COMPLETE_TREE, "commitments": committed, "historical_http_attempts": attempts, "accepted_message_and_checkpoint": True, "journal_present": False, "status": "permanently_blocked_uncertain"}


def runtime_bindings() -> dict[str, Any]:
    launcher = runner_module.NOUS_LAUNCHER_PATH
    paths = {"runner": Path(runner_module.__file__), "launcher": launcher, "bridge": launcher.parent / "nous_codex_bridge.py"}
    if any(not path.is_file() for path in paths.values()): raise ValueError("Canonical Nous transport runtime is unavailable")
    return {name: fingerprint(path) for name, path in paths.items()}


def judge_assets() -> dict[str, Any]:
    prefix = prompts_dir() / "judge" / "JUDGE_PREFIX.md"
    binary = prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md"
    schema = schema_dir() / "hbq_judge_response.schema.json"
    return {"strict_ai": False, "judge_prefix": {"included": False, "file": fingerprint(prefix)}, "active_prompts": [fingerprint(binary)], "response_schema": fingerprint(schema)}


def _cells(uncertain_root: Path) -> tuple[Any, list[dict[str, Any]], list[Path]]:
    parent = _parent_v4()
    frozen = read_json(uncertain_root / parent.FROZEN_NAME)
    inherited = frozen.get("cells")
    if not isinstance(inherited, list) or len(inherited) != 3: raise ValueError("Uncertain Ox v4 root lacks three frozen public cells")
    result, input_roots = [], []
    for number, cell in enumerate(inherited, 1):
        if not isinstance(cell, Mapping) or not isinstance(cell.get("inputs"), Mapping) or not isinstance(cell.get("paths"), Mapping): raise ValueError("Uncertain Ox v4 cell is malformed")
        paths = dict(cell["paths"])
        artifact, prompt, task = (Path(str(paths.get(key, ""))) for key in ("artifact", "prompt", "task_contract"))
        observed = {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)}
        if observed != cell["inputs"] or artifact.parent != prompt.parent or artifact.parent != task.parent: raise ValueError("Uncertain Ox v4 public input bytes drifted")
        question_ids = list(cell.get("question_ids", []))[:4]
        if len(question_ids) != 4 or len(set(question_ids)) != 4 or any(not isinstance(item, str) for item in question_ids): raise ValueError("Uncertain Ox v4 cannot supply four transport leaves")
        item_id = cell.get("item_id")
        if not isinstance(item_id, str) or not item_id: raise ValueError("Uncertain Ox v4 cell lacks a public item identifier")
        result.append({"cell_id": f"ox-alpha-v5-{number:02d}", "item_id": item_id, "inputs": observed, "paths": paths, "question_ids": question_ids})
        input_roots.append(artifact.parent.resolve())
    if len({cell["item_id"] for cell in result}) != 3: raise ValueError("Ox v5 requires three distinct public cells")
    return parent, result, input_roots


def _fresh_zero_proof(parent: Any, proof_path: Path, checked_at: str) -> dict[str, Any]:
    return parent._fresh_zero_proof(parent._parent_v3(), proof_path, checked_at)


def _external_roots(work: Path, predecessor: Mapping[str, Any], proof: Mapping[str, Any], input_roots: list[Path]) -> dict[str, Any]:
    parent_root = Path(str(predecessor.get("work_dir", "")))
    proof_path = Path(str(proof.get("path", "")))
    catalog = Path(str(proof.get("catalog", {}).get("root", ""))) if isinstance(proof.get("catalog"), Mapping) else Path()
    usage = Path(str(proof.get("usage", {}).get("root", ""))) if isinstance(proof.get("usage"), Mapping) else Path()
    roots = [work, parent_root, proof_path, catalog, usage, *input_roots]
    if any(not str(path) or str(path) == "." for path in roots): raise ValueError("Ox v5 external root binding is malformed")
    _external_disjoint(*roots)
    return {"work": str(work.resolve()), "uncertain_v4": str(parent_root.resolve()), "zero_cost_proof": str(proof_path.resolve()), "zero_cost_catalog": str(catalog.resolve()), "zero_cost_usage": str(usage.resolve()), "inputs": [str(path.resolve()) for path in input_roots]}


def freeze_work(uncertain_v4_work: Path, zero_cost_proof: Path, work: Path) -> dict[str, Any]:
    if work.exists() and any(work.iterdir()): raise ValueError("Ox v5 requires a fresh empty external work root")
    predecessor = uncertain_v4_commitments(uncertain_v4_work)
    parent, cells, input_roots = _cells(uncertain_v4_work)
    checked_at = datetime.now(timezone.utc).isoformat()
    proof = _fresh_zero_proof(parent, zero_cost_proof, checked_at)
    value = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, predecessor, proof, input_roots), "uncertain_v4": predecessor, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**proof, "freshness_checked_at": checked_at}, "cells": cells}
    immutable_json(work / FROZEN_NAME, value)
    return value


def load_frozen(work: Path) -> dict[str, Any]:
    value = read_json(work / FROZEN_NAME)
    predecessor = value.get("uncertain_v4")
    if not isinstance(predecessor, Mapping): raise ValueError("Ox v5 frozen contract lacks uncertain-v4 binding")
    parent, cells, input_roots = _cells(Path(str(predecessor.get("work_dir", ""))))
    current_predecessor = uncertain_v4_commitments(Path(str(predecessor.get("work_dir", ""))))
    proof = value.get("zero_cost_proof")
    if not isinstance(proof, Mapping) or not isinstance(proof.get("freshness_checked_at"), str): raise ValueError("Ox v5 frozen contract lacks zero-cost proof")
    current_proof = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), proof["freshness_checked_at"])
    expected = {"format_version": 1, "study_id": CONTRACT["study_id"], "frozen_before_execution": True, "contract": fingerprint(CONTRACT_PATH), "external_roots": _external_roots(work, current_predecessor, current_proof, input_roots), "uncertain_v4": current_predecessor, "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "runtime": runtime_bindings(), "judge_assets": judge_assets(), "zero_cost_proof": {**current_proof, "freshness_checked_at": proof["freshness_checked_at"]}, "cells": cells}
    if value != expected: raise ValueError("Ox v5 frozen transport contract drifted")
    return value


def assert_invocation_freshness(frozen: Mapping[str, Any], checked_at: str) -> None:
    parent, _, _ = _cells(Path(str(frozen["uncertain_v4"]["work_dir"])))
    proof = frozen.get("zero_cost_proof")
    if not isinstance(proof, Mapping): raise ValueError("Ox v5 zero-cost proof is malformed")
    current = _fresh_zero_proof(parent, Path(str(proof.get("path", ""))), checked_at)
    if proof != {**current, "freshness_checked_at": proof.get("freshness_checked_at")}:
        raise ValueError("Ox v5 zero-cost proof drifted at the required freshness point")


def assert_launch_freshness(frozen: Mapping[str, Any]) -> None:
    assert_invocation_freshness(frozen, datetime.now(timezone.utc).isoformat())


def input_paths(frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    if cell not in frozen.get("cells", []): raise ValueError("Ox v5 cell is not frozen")
    paths = cell.get("paths")
    if not isinstance(paths, Mapping): raise ValueError("Ox v5 cell paths are malformed")
    artifact, prompt, task = (Path(str(paths.get(key, ""))) for key in ("artifact", "prompt", "task_contract"))
    observed = {"source.md": fingerprint(artifact), "prompt.md": fingerprint(prompt), "task-contract.json": fingerprint(task)}
    if observed != cell.get("inputs"): raise ValueError("Ox v5 cell input bytes drifted")
    return artifact, prompt, task
