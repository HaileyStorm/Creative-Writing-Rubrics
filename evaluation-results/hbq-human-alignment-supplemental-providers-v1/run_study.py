#!/usr/bin/env python3
"""Run one provider/phase against the byte-frozen HANNA v3 input projection."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import PHASES, load_frozen, phase_rows, primary_input, provider


def _promotion(work: Path, data: Path) -> dict[str, Any]:
    from promotion_gate import validate_gate
    return validate_gate(work, data)


def _can_run(provider_id: str, phase: str, work: Path, data: Path | None = None) -> None:
    item = provider(provider_id)
    if phase == "development" and item.get("requires_promotion_decision"):
        raise ValueError("Nous Pro has no development phase; it is a conditional post-development provider")
    if phase in {"repeatability", "confirmatory"}:
        if data is None:
            raise ValueError("Later phases require --data-dir to replay-verify the immutable development gate")
        gate = _promotion(work, data)
        from analyze_study import verify_phase, verify_study_receipts
        frozen = load_frozen(work)
        # Both mandatory development conditions must be completed and independently
        # replay-verified before either later phase can begin.
        for mandatory in ("grok_4_6_high", "nous_flash_max"):
            verify_phase(work, frozen, mandatory, "development")
            verify_study_receipts(work, frozen, mandatory)
        eligible = set(gate["eligible_provider_ids"])
        if provider_id not in eligible:
            raise ValueError(f"Provider {provider_id} is not eligible under the immutable promotion decision")
        if phase == "confirmatory":
            for eligible_provider in sorted(eligible):
                verify_phase(work, frozen, eligible_provider, "repeatability")
                verify_study_receipts(work, frozen, eligible_provider)


def execute(work: Path, provider_id: str, phase: str, workers: int, timeout: float, *, data: Path | None = None) -> None:
    frozen = load_frozen(work)
    if phase not in PHASES:
        raise ValueError("Unknown supplemental phase")
    item = provider(provider_id)
    if not 1 <= workers <= item["maximum_workers"]:
        raise ValueError("workers exceeds the frozen provider maximum")
    _can_run(provider_id, phase, work, data)

    def run(job: dict[str, Any]) -> dict[str, Any]:
        folder, _ = primary_input(frozen, phase, str(job["item_id"]))
        output = work / "runs" / provider_id / phase / str(job["item_id"]) / f"run-{job['repetition']:02d}"
        return run_judge(
            artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"],
            task_contract_path=folder / "task-contract.json", bundle_id=frozen["primary_protocol"]["runner"]["bundle_id"],
            provider=item["provider"], model=item["model"], reasoning=item["reasoning"],
            output_dir=output, registry=registry_path(), bundles=bundles_path(),
            batch_size=frozen["primary_protocol"]["runner"]["batch_size"],
            batch_attempts=frozen["primary_protocol"]["runner"]["batch_attempts"],
            allow_remote=True, allow_unattested_reasoning=True,
            resume=(output / "run.json").is_file(), timeout=timeout,
            artifact_id=str(job["item_id"]), strict_ai=False,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(run, job): job for job in phase_rows(frozen, phase)}
        for future in as_completed(futures):
            job = futures[future]
            result = future.result()
            print({"provider": provider_id, "phase": phase, "item_id": job["item_id"], "repetition": job["repetition"], "status": result.get("status")}, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--provider", required=True, choices=[item["provider_id"] for item in __import__("study").CONTRACT["providers"]])
    parser.add_argument("--phase", required=True, choices=PHASES)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=3600)
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()
    execute(args.work_dir.resolve(), args.provider, args.phase, args.workers, args.timeout, data=args.data_dir.resolve() if args.data_dir else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
