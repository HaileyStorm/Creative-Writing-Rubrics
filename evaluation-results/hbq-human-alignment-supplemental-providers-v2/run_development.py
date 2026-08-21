#!/usr/bin/env python3
"""Run the pre-enabled batch-16 Flash development condition; analysis is separate."""
from __future__ import annotations

import argparse
from pathlib import Path

from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge

from enable_development import enable
from study import CONTRACT, _parent, fingerprint, immutable_json, load_frozen, runtime_bindings, sha


def _invocation(work: Path, enablement: dict) -> dict:
    return {
        "format_version": 1, "study_id": CONTRACT["study_id"], "kind": "batch_16_development",
        "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"),
        "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"),
        "enablement": fingerprint(work / "development-enablement.json"), "provider": CONTRACT["provider"],
        "batch_size": 16, "workers": 1, "timeout_seconds": 600.0, "runtime": runtime_bindings(),
        "runner": fingerprint(Path(run_judge.__code__.co_filename)), "study": fingerprint(Path(__file__).resolve().parent / "study.py"),
        "development_enabler": fingerprint(Path(__file__).resolve().parent / "enable_development.py"),
        "development_runner": fingerprint(Path(__file__)), "comparison_status": enablement["development"]["comparison_status"],
    }


def execute(work: Path, *, timeout: float = 600) -> None:
    if timeout != 600:
        raise ValueError("Frozen v2 development requires timeout 600 seconds")
    frozen = load_frozen(work)
    enablement = enable(work)
    invocation = _invocation(work, enablement)
    immutable_json(work / "development-invocation.json", invocation)
    parent = _parent(); parent_frozen = parent.load_frozen(Path(frozen["parent_work_dir"]))
    for row in parent.phase_rows(parent_frozen, "development"):
        folder, _ = parent.primary_input(parent_frozen, "development", str(row["item_id"]))
        output = work / "runs" / "development" / str(row["item_id"]) / "run-01"
        run_judge(
            artifact_path=folder / "source.md", context_paths=[folder / "prompt.md"], task_contract_path=folder / "task-contract.json",
            bundle_id="prose.short_story", provider="nous", model=CONTRACT["provider"]["model"], reasoning="max",
            output_dir=output, registry=registry_path(), bundles=bundles_path(), question_ids=parent_frozen["selection"]["question_ids"],
            batch_size=16, batch_attempts=3, allow_remote=True, timeout=timeout, artifact_id=str(row["item_id"]), strict_ai=False,
            allow_unattested_reasoning=True, resume=(output / "run.json").is_file(),
        )


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True); parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    execute(args.work_dir.resolve(), timeout=args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
