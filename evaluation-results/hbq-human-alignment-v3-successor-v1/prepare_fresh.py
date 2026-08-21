"""Seal the fresh-88 execution plan before a provider run can begin."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from study import AUTHORITY_PIN, CONTRACT, EXECUTION, PROVIDER, atomic_immutable_json, canonical_bindings, freeze_execution_contract, load_authority, runtime_manifest, sha256_path

def binding(path: Path) -> dict[str, Any]:
    path = path.resolve(); return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_path(path)}

def prepare(authority_root: Path, input_root: Path, work: Path, artifact_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    if not dry_run and (work.exists() and any(work.iterdir()) or artifact_root.exists() and any(artifact_root.iterdir())): raise ValueError("Fresh88 prepare requires empty work and artifact targets")
    if (artifact_root / "runs").exists(): raise ValueError("Fresh88 work must be prepared before any raw run directory exists")
    authority = load_authority(authority_root)
    rows = {row["item_id"]: row for row in authority["selection"]["development"]}
    cells = []
    for ordinal, item_id in enumerate(authority["fresh_complement"]["scheduled_item_ids"], 1):
        row = rows[item_id]; directory = input_root / "development" / item_id
        artifact, context, task = (directory / name for name in ("source.md", "prompt.md", "task-contract.json"))
        if not all(path.is_file() for path in (artifact, context, task)): raise ValueError(f"Missing authoritative input: {item_id}")
        external = row["external_input"]
        if {"source.md": {"name":artifact.name,"bytes":artifact.stat().st_size,"sha256":sha256_path(artifact)}, "prompt.md": {"name":context.name,"bytes":context.stat().st_size,"sha256":sha256_path(context)}, "task-contract.json": {"name":task.name,"bytes":task.stat().st_size,"sha256":sha256_path(task)}} != external: raise ValueError(f"Authoritative input drifted: {item_id}")
        if __import__("json").loads(task.read_text(encoding="utf-8")).get("artifact_id") != item_id: raise ValueError(f"Task identity drifted: {item_id}")
        cells.append({"item_id":item_id,"origin":"fresh_full_successor","ordinal":ordinal,"run_dir":f"runs/{item_id}","artifact":binding(artifact),"contexts":[binding(context)],"task_contract":binding(task),"external_input":external})
    base = {**canonical_bindings(), "weight_profile": None, "execution": dict(EXECUTION), "provider": dict(PROVIDER), "runtime_manifest": runtime_manifest()}
    plan = {"format_version":1,"study_id":CONTRACT["study_id"],"authority_contract_sha256":AUTHORITY_PIN["frozen_successor_sha256"],"origin":"fresh_full_successor","phase":"development","base_frozen":base,"cells":cells}
    if dry_run: return {"cells":len(cells),"plan":plan}
    atomic_immutable_json(work / "fresh88-execution-contract.json", plan)
    freeze_execution_contract(work, artifact_root)
    return {"cells":len(cells),"contract":str(work / "fresh88-execution-contract.json")}

def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("authority_root",type=Path); parser.add_argument("input_root",type=Path); parser.add_argument("work",type=Path); parser.add_argument("artifact_root",type=Path); parser.add_argument("--dry-run",action="store_true"); args=parser.parse_args()
    print(prepare(args.authority_root,args.input_root,args.work,args.artifact_root,dry_run=args.dry_run)["cells"])
if __name__ == "__main__": main()
