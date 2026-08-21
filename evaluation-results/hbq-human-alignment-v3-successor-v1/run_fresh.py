"""Run only a pre-sealed fresh-88 plan; provider invocation is deliberately narrow."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hbqrs.runner_v2 import run_judge

from study import CONTRACT, EXECUTION, PROVIDER, RECEIPT_NAME, create_development_gate, load_execution_contract, read_json, sha256_path, verify_matrix

def run(authority_root: Path, work: Path, artifact_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    plan = load_execution_contract(work, authority_root)
    base = plan.get("base_frozen")
    execution = base.get("execution") if isinstance(base, dict) else None
    provider = base.get("provider") if isinstance(base, dict) else None
    if execution != EXECUTION or provider != PROVIDER:
        raise ValueError("Fresh successor runtime pin drifted")
    receipt = read_json(work / RECEIPT_NAME)
    expected_receipt = {"format_version": 1, "study_id": CONTRACT["study_id"], "execution_contract_sha256": sha256_path(work / "fresh88-execution-contract.json"), "purpose": "pre_execution_raw_verifier_binding"}
    if receipt != expected_receipt: raise ValueError("Pre-execution receipt is missing or drifted")
    expected_dirs = {cell["item_id"] for cell in plan["cells"]}
    existing = {path.name for path in (artifact_root / "runs").glob("*") if path.is_dir()} if (artifact_root / "runs").is_dir() else set()
    if not existing <= expected_dirs: raise ValueError("Extra raw run directory exists before scheduling")
    if dry_run: return {"cells":len(plan["cells"]),"provider_calls":0}
    for cell in plan["cells"]:
        run_dir = artifact_root / cell["run_dir"]
        if run_dir.exists():
            # Resume is permitted only for the exact predeclared cell directory.
            resume = True
        else: resume = False
        cell_execution = {**execution, "artifact_id": cell["item_id"]}
        run_judge(artifact_path=cell["artifact"]["path"], context_paths=[x["path"] for x in cell["contexts"]], task_contract_path=cell["task_contract"]["path"], bundle_id=cell_execution["bundle_id"], provider=cell_execution["provider"], model=cell_execution["model"], reasoning=cell_execution["reasoning"], output_dir=run_dir, registry=base["registry"]["path"], bundles=base["bundles"]["path"], weight_profile=base["weight_profile"], batch_size=cell_execution["batch_size"], batch_attempts=cell_execution["batch_attempts"], strict_ai=cell_execution["strict_ai"], codex_bin=cell_execution["codex_bin"], artifact_id=cell_execution["artifact_id"], judge_id=f"{cell_execution['provider']}:{cell_execution['model']}", allow_remote=True, resume=resume)
    matrix = verify_matrix(work, authority_root, artifact_root)
    return {"matrix":matrix["matrix_sha256"],"gate":create_development_gate(work, artifact_root, authority_root)}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("authority_root",type=Path); parser.add_argument("work",type=Path); parser.add_argument("artifact_root",type=Path); parser.add_argument("--dry-run",action="store_true"); args=parser.parse_args()
    print(run(args.authority_root,args.work,args.artifact_root,dry_run=args.dry_run)["cells"] if args.dry_run else "completed")
if __name__ == "__main__": main()
