"""Run only a pre-sealed fresh-88 plan; provider invocation is deliberately narrow."""
from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
import stat
from typing import Any

from hbqrs.runner_v2 import run_judge

from study import CONTRACT, EXECUTION, PROVIDER, RECEIPT_NAME, create_development_gate, load_execution_contract, read_json, sha256_path, verify_matrix

def _worker_count(workers: int) -> int:
    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 4:
        raise ValueError("Fresh88 workers must be an integer from 1 through 4")
    return workers

def _real_directory(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes
    except FileNotFoundError:
        return False
    return path.is_dir() and not path.is_symlink() and not attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT

def _preflight_runs(artifact_root: Path, cells: list[dict[str, Any]]) -> set[str]:
    runs_root = artifact_root / "runs"
    expected = {str(cell["item_id"]) for cell in cells}
    if not runs_root.exists():
        if runs_root.is_symlink():
            raise ValueError("Runs root must be a real non-reparse directory")
        return set()
    if not _real_directory(runs_root):
        raise ValueError("Runs root must be a real non-reparse directory")
    root = runs_root.resolve(strict=True)
    resolved: set[Path] = set()
    existing: set[str] = set()
    for child in runs_root.iterdir():
        if child.name not in expected:
            raise ValueError("Unknown raw run child exists before scheduling")
        if not _real_directory(child):
            raise ValueError("Raw run target must be a real non-reparse directory")
        target = (runs_root / child.name).resolve(strict=True)
        if target.parent != root or target in resolved:
            raise ValueError("Raw run target has a resolved-path alias collision")
        resolved.add(target)
        existing.add(child.name)
    return existing

def run(authority_root: Path, work: Path, artifact_root: Path, *, dry_run: bool = False, workers: int = 1) -> dict[str, Any]:
    workers = _worker_count(workers)
    plan = load_execution_contract(work, authority_root)
    base = plan.get("base_frozen")
    execution = base.get("execution") if isinstance(base, dict) else None
    provider = base.get("provider") if isinstance(base, dict) else None
    if execution != EXECUTION or provider != PROVIDER:
        raise ValueError("Fresh successor runtime pin drifted")
    receipt = read_json(work / RECEIPT_NAME)
    expected_receipt = {"format_version": 1, "study_id": CONTRACT["study_id"], "execution_contract_sha256": sha256_path(work / "fresh88-execution-contract.json"), "purpose": "pre_execution_raw_verifier_binding"}
    if receipt != expected_receipt: raise ValueError("Pre-execution receipt is missing or drifted")
    existing = _preflight_runs(artifact_root, plan["cells"])
    jobs: list[tuple[int, str, Path, bool, dict[str, Any]]] = []
    for ordinal, cell in enumerate(plan["cells"], 1):
        run_dir = artifact_root / cell["run_dir"]
        resume = cell["item_id"] in existing
        cell_execution = {**execution, "artifact_id": cell["item_id"]}
        kwargs = {"artifact_path": cell["artifact"]["path"], "context_paths": [x["path"] for x in cell["contexts"]], "task_contract_path": cell["task_contract"]["path"], "bundle_id": cell_execution["bundle_id"], "provider": cell_execution["provider"], "model": cell_execution["model"], "reasoning": cell_execution["reasoning"], "output_dir": run_dir, "registry": base["registry"]["path"], "bundles": base["bundles"]["path"], "weight_profile": base["weight_profile"], "batch_size": cell_execution["batch_size"], "batch_attempts": cell_execution["batch_attempts"], "strict_ai": cell_execution["strict_ai"], "codex_bin": cell_execution["codex_bin"], "artifact_id": cell_execution["artifact_id"], "judge_id": f"{cell_execution['provider']}:{cell_execution['model']}", "allow_remote": True, "resume": resume}
        jobs.append((ordinal, cell_execution["artifact_id"], run_dir, resume, kwargs))
    if dry_run: return {"cells": len(jobs), "provider_calls": 0}
    futures: dict[Future[Any], tuple[int, str, Path, bool]] = {}
    completed: list[dict[str, Any]] = []
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fresh88")
    try:
        for ordinal, item_id, run_dir, resume, kwargs in jobs:
            futures[executor.submit(run_judge, **kwargs)] = (ordinal, item_id, run_dir, resume)
        for future in as_completed(futures):
            ordinal, item_id, run_dir, resume = futures[future]
            future.result()
            completed.append({"ordinal": ordinal, "item_id": item_id, "run_dir": run_dir.as_posix(), "status": "completed", "resume": resume})
    except BaseException:
        for future in futures:
            future.cancel()
        for future in futures:
            if not future.cancelled():
                try: future.result()
                except BaseException: pass
        raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    matrix = verify_matrix(work, authority_root, artifact_root)
    return {"matrix": matrix["matrix_sha256"], "gate": create_development_gate(work, artifact_root, authority_root), "cells": sorted(completed, key=lambda item: item["ordinal"])}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("authority_root",type=Path); parser.add_argument("work",type=Path); parser.add_argument("artifact_root",type=Path); parser.add_argument("--dry-run",action="store_true"); parser.add_argument("--workers", type=int, default=1); args=parser.parse_args()
    result = run(args.authority_root,args.work,args.artifact_root,dry_run=args.dry_run,workers=args.workers)
    print(result["cells"] if args.dry_run else f"completed {len(result['cells'])}")
if __name__ == "__main__": main()
