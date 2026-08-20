#!/usr/bin/env python3
"""Run one explicit frozen HANNA phase from an external work directory."""
from __future__ import annotations
import argparse, hashlib, json, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import run_judge
from study import canonical_json, sha256_path, validate_frozen_contract

PHASES = ("development", "repeatability", "confirmatory")
def gate(work: Path, frozen: dict) -> None:
    path=work/"confirmation-gate.json"
    if not path.is_file(): raise ValueError("Confirmatory phase requires immutable confirmation-gate.json")
    value=json.loads(path.read_text(encoding="utf-8")); expected={"format_version":1,"study_id":frozen["study_id"],"frozen_contract_sha256":sha256_path(work/"frozen-run-contract.json"),"package_commit":frozen["package_commit"],"mapping_sets_sha256":frozen["mapping_sets_sha256"],"question_ids_sha256":hashlib.sha256(canonical_json(frozen["question_ids"])).hexdigest()}
    if any(value.get(key)!=item for key,item in expected.items()): raise ValueError("Confirmation gate does not bind unchanged frozen protocol")
    analysis=Path(value.get("development_analysis_dir", "")); manifest=analysis/"manifest.json"; summary=analysis/"summary.json"
    if not manifest.is_file() or not summary.is_file() or sha256_path(manifest)!=value.get("development_analysis_manifest_sha256") or sha256_path(summary)!=value.get("development_analysis_summary_sha256"): raise ValueError("Confirmation gate development-analysis hashes do not verify")
def jobs(frozen: dict, phase: str) -> list[dict]:
    if phase=="repeatability": rows=[{"kind":phase,"repetition":number,**row} for row in frozen["repeatability"]["items"] for number in range(1,frozen["repeatability"]["repetitions"]+1)]
    else: rows=[{"kind":phase,"repetition":1,**row} for row in frozen["partitions"][phase]]
    random.Random(frozen["selection"]["seed"]).shuffle(rows); return rows
def execute(work: Path, phase: str, workers: int, timeout: float) -> None:
    frozen=validate_frozen_contract(work)
    if phase=="confirmatory": gate(work,frozen)
    if not 1<=workers<=frozen["runner"]["maximum_workers"]: raise ValueError("workers exceeds frozen maximum")
    def run(job: dict):
        inputs=work/"inputs"/job.get("partition",job["kind"])/job["item_id"]; output=work/"runs"/job["kind"]/job["item_id"]/f"run-{job['repetition']:02d}"
        return run_judge(artifact_path=inputs/"source.md",context_paths=[inputs/"prompt.md"],task_contract_path=inputs/"task-contract.json",bundle_id=frozen["runner"]["bundle_id"],provider=frozen["provider"]["provider"],model=frozen["provider"]["model"],reasoning=frozen["provider"]["reasoning"],output_dir=output,registry=registry_path(),bundles=bundles_path(),batch_size=frozen["runner"]["batch_size"],allow_remote=frozen["runner"]["allow_remote"],resume=(output/"run.json").is_file(),timeout=timeout,artifact_id=job["item_id"],strict_ai=False)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures={executor.submit(run,job):job for job in jobs(frozen,phase)}
        for future in as_completed(futures): job=futures[future]; print({"phase":phase,"item_id":job["item_id"],"repetition":job["repetition"],"status":future.result().get("status")},flush=True)
def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--work-dir",required=True,type=Path); parser.add_argument("--phase",required=True,choices=PHASES); parser.add_argument("--workers",type=int,default=2); parser.add_argument("--timeout",type=float,default=3600); args=parser.parse_args(); execute(args.work_dir.resolve(),args.phase,args.workers,args.timeout); return 0
if __name__=="__main__": raise SystemExit(main())
