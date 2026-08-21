#!/usr/bin/env python3
"""Run one provider/phase against the byte-frozen HANNA v3 input projection."""
from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from hbqrs import runner as runner_module
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge

def _sibling(name: str, aliases: dict[str, Any]):
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"supplemental_hanna_{name}", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Supplemental sibling is unavailable: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    prior = {key: sys.modules.get(key) for key in aliases}
    sys.modules.update(aliases)
    try:
        spec.loader.exec_module(module)
    finally:
        for key, previous in prior.items():
            if previous is None: sys.modules.pop(key, None)
            else: sys.modules[key] = previous
    return module

_STUDY = _sibling("study", {})
_ANALYSIS = _sibling("analyze_study", {"study": _STUDY})
_PROMOTION_GATE = _sibling("promotion_gate", {"study": _STUDY, "analyze_study": _ANALYSIS})
CONTRACT_PATH = _STUDY.CONTRACT_PATH
PHASES = _STUDY.PHASES
load_frozen = _STUDY.load_frozen
phase_rows = _STUDY.phase_rows
primary_input = _STUDY.primary_input
provider = _STUDY.provider
sha = _STUDY.sha
_INVOCATION_TEMP_WRITTEN = lambda: None


def _promotion(work: Path, data: Path) -> dict[str, Any]:
    return _PROMOTION_GATE.validate_gate(work, data)


def _binding(path: Path, label: str) -> dict[str, Any]:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"Canonical {label} is unavailable")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def _invocation(work: Path, item: dict[str, Any], provider_id: str, phase: str, workers: int, timeout: float) -> dict[str, Any]:
    value = {
        "format_version": 1,
        "study_id": "hbq-human-alignment-supplemental-providers-v1",
        "supplemental_contract_sha256": sha(CONTRACT_PATH),
        "frozen_contract_sha256": sha(work / "frozen-provider-contract.json"),
        "provider_id": provider_id,
        "phase": phase,
        "workers": workers,
        "timeout": timeout,
        "runner": _binding(Path(runner_module.__file__), "runner.py"),
        "study_runner": _binding(Path(__file__), "run_study.py"),
        "study": _binding(Path(_STUDY.__file__), "study.py"),
        "analyzer": _binding(Path(_ANALYSIS.__file__), "analyze_study.py"),
        "promotion_gate": _binding(Path(_PROMOTION_GATE.__file__), "promotion_gate.py"),
    }
    if item["provider"] == "nous":
        launcher = runner_module.NOUS_LAUNCHER_PATH
        bridge = launcher.parent / "nous_codex_bridge.py"
        value["nous_transport"] = {"bridge": _binding(bridge, "Nous bridge"), "launcher": _binding(launcher, "Nous launcher")}
    path = work / "invocations" / provider_id / f"{phase}.json"
    output_root = work / "runs" / provider_id / phase
    if not path.exists() and output_root.exists() and any(output_root.iterdir()):
        raise ValueError("Refusing invocation-record backfill after provider-phase output artifacts exist")
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{phase}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered); output.flush(); os.fsync(output.fileno())
        _INVOCATION_TEMP_WRITTEN()
        os.link(temporary, path)
    except FileExistsError:
        try:
            observed = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError("Invocation record is partial or unreadable") from exc
        if observed != rendered:
            raise ValueError("Immutable invocation record drifted")
    except BaseException:
        raise
    finally:
        Path(temporary).unlink(missing_ok=True)
    return value


def _can_run(provider_id: str, phase: str, work: Path, data: Path | None = None) -> None:
    item = provider(provider_id)
    if phase == "development" and item.get("requires_promotion_decision"):
        raise ValueError("Nous Pro has no development phase; it is a conditional post-development provider")
    if phase in {"repeatability", "confirmatory"}:
        if data is None:
            raise ValueError("Later phases require --data-dir to replay-verify the immutable development gate")
        gate = _promotion(work, data)
        frozen = load_frozen(work)
        # Both mandatory development conditions must be completed and independently
        # replay-verified before either later phase can begin.
        for mandatory in ("grok_4_6_high", "nous_flash_max"):
            _ANALYSIS.verify_phase(work, frozen, mandatory, "development")
            _ANALYSIS.verify_study_receipts(work, frozen, mandatory)
        eligible = set(gate["eligible_provider_ids"])
        if provider_id not in eligible:
            raise ValueError(f"Provider {provider_id} is not eligible under the immutable promotion decision")
        if phase == "confirmatory":
            for eligible_provider in sorted(eligible):
                _ANALYSIS.verify_phase(work, frozen, eligible_provider, "repeatability")
                _ANALYSIS.verify_study_receipts(work, frozen, eligible_provider)


def execute(work: Path, provider_id: str, phase: str, workers: int, timeout: float, *, data: Path | None = None) -> None:
    frozen = load_frozen(work)
    if phase not in PHASES:
        raise ValueError("Unknown supplemental phase")
    item = provider(provider_id)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(float(timeout)):
        raise ValueError("timeout must be a finite number")
    if not 1 <= workers <= item["maximum_workers"]:
        raise ValueError("workers exceeds the frozen provider maximum")
    if phase == "development" and item.get("requires_promotion_decision"):
        _can_run(provider_id, phase, work, data)
    if item["provider"] == "nous" and workers != 1:
        raise ValueError("Nous requires exactly one worker")
    if item["provider"] == "nous" and timeout < 420:
        raise ValueError("Nous timeout must be at least 420 seconds")
    _can_run(provider_id, phase, work, data)
    _invocation(work, item, provider_id, phase, workers, float(timeout))

    jobs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for job in phase_rows(frozen, phase):
        folder, _ = primary_input(frozen, phase, str(job["item_id"]))
        output = work / "runs" / provider_id / phase / str(job["item_id"]) / f"run-{job['repetition']:02d}"
        kwargs = {
            "artifact_path": folder / "source.md", "context_paths": [folder / "prompt.md"],
            "task_contract_path": folder / "task-contract.json", "bundle_id": frozen["primary_protocol"]["runner"]["bundle_id"],
            "provider": item["provider"], "model": item["model"], "reasoning": item["reasoning"],
            "output_dir": output, "registry": registry_path(), "bundles": bundles_path(),
            "batch_size": frozen["primary_protocol"]["runner"]["batch_size"],
            "batch_attempts": frozen["primary_protocol"]["runner"]["batch_attempts"],
            "allow_remote": True, "allow_unattested_reasoning": True,
            "resume": (output / "run.json").is_file(), "timeout": timeout,
            "artifact_id": str(job["item_id"]), "strict_ai": False,
        }
        jobs.append((job, kwargs))

    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="supplemental-provider")
    futures: dict[Future[Any], dict[str, Any]] = {}
    pending = iter(jobs)

    def submit_next() -> bool:
        try:
            job, kwargs = next(pending)
        except StopIteration:
            return False
        futures[executor.submit(run_judge, **kwargs)] = job
        return True

    try:
        for _ in range(workers):
            if not submit_next(): break
        while futures:
            future = next(as_completed(futures))
            job = futures.pop(future)
            result = future.result()
            print({"provider": provider_id, "phase": phase, "item_id": job["item_id"], "repetition": job["repetition"], "status": result.get("status")}, flush=True)
            submit_next()
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--provider", required=True, choices=[item["provider_id"] for item in _STUDY.CONTRACT["providers"]])
    parser.add_argument("--phase", required=True, choices=PHASES)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    execute(args.work_dir.resolve(), args.provider, args.phase, args.workers, args.timeout, data=args.data_dir.resolve() if args.data_dir else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
