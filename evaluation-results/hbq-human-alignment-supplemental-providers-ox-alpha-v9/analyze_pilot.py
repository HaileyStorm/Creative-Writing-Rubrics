#!/usr/bin/env python3
"""Complete-case-only v9 reporter; partial cells never receive scores."""
from __future__ import annotations
import argparse, importlib.util, json, os, tempfile
from pathlib import Path
from typing import Any, Mapping
from hbqrs.core import load_bundles, load_modules, resolve_bundle
from hbqrs.scoring_v2 import score_bundle
from hbqrs.paths import bundles_path, registry_path
from study import CONTRACT, fingerprint, load_frozen, read_json, sha, parent_v8


def _runner():
    spec=importlib.util.spec_from_file_location("ox_alpha_v9_report_runner",Path(__file__).with_name("run_pilot.py"))
    if spec is None or spec.loader is None: raise ValueError("v9 executor is unavailable")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def _accepted(row: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    hits = [item for item in row if item.get("status") == "accepted"]
    return hits[0] if len(hits) == 1 else None


def report(work: Path) -> dict[str, Any]:
    frozen, executor = load_frozen(work), _runner()
    current=executor._state(work); units=current["units"]
    executor._assert_identities(frozen,current)
    known_units={unit["unit_id"] for unit in frozen["units"]}
    if set(units) - known_units: raise ValueError("v9 history references an unknown frozen unit")
    cells, attrition, verified_physical = [], [], 0
    details={}
    for unit in frozen["units"]:
        attempts=units.get(unit["unit_id"],[]); terminal=attempts[-1] if attempts else None
        detail={"unit_id":unit["unit_id"],"attempt_count":len(attempts),"terminal_state":terminal.get("status") if terminal else "unattempted","eligible_524_history":[item["attempt"] for item in attempts if item.get("status")=="eligible_524"]}
        if terminal and terminal.get("status")=="quarantined": detail["quarantine_cause"]=terminal.get("reason") or terminal.get("verification") or terminal.get("error")
        for attempt in attempts:
            if attempt.get("status") not in {"accepted", "eligible_524"}: continue
            run=work/"attempts"/unit["unit_id"]/f"attempt-{attempt['attempt']:02d}"
            proof=executor._accepted(run,unit) if attempt["status"]=="accepted" else executor._eligible_524(run,unit)
            if attempt != {**proof,"attempt":attempt["attempt"],"at":attempt["at"]}: raise ValueError("v9 attempt authority does not match verified transport evidence")
            verified_physical += 1
        details[unit["unit_id"]]=detail
    for cell_id in [cell["cell_id"] for cell in frozen["units"][::45]]:
        selected = [unit for unit in frozen["units"] if unit["cell_id"] == cell_id]; accepted = [_accepted(units.get(unit["unit_id"], [])) for unit in selected]
        missing = [unit["unit_id"] for unit, hit in zip(selected, accepted) if hit is None]
        if missing:
            attrition.append({"cell_id": cell_id, "accepted_batches": 45-len(missing), "missing_or_quarantined_units": [details[unit_id] for unit_id in missing]})
            continue
        verdicts = []
        for unit, hit in zip(selected, accepted):
            run = work / "attempts" / unit["unit_id"] / f"attempt-{hit['attempt']:02d}"
            proof=executor._accepted(run,unit)
            expected={**proof,"attempt":hit["attempt"],"at":hit["at"]}
            if hit != expected: raise ValueError("v9 accepted authority does not match raw transport verification")
            verdicts.extend(json.loads(line) for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())
        task = read_json(Path(selected[0]["paths"]["task_contract"])); score = score_bundle(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), verdicts, artifact_id=selected[0]["item_id"], task_contract=task)
        static=parent_v8().parent_v2().static_ablation(verdicts,task,selected[0]["item_id"])
        cells.append({"cell_id": cell_id, "item_id": selected[0]["item_id"], "primary_score": score["final_score"]["observed"], "static_178_ablation_score": static["final_score"]["observed"], "gpt_primary_score": selected[0]["gpt_reference"]["primary_score"], "gpt_static_178_ablation_score": selected[0]["gpt_reference"]["static_ablation_score"], "evidence_status": "provisional_only"})
    attempts=sum(len(rows) for rows in units.values())
    return {"format_version": 1, "study_id": CONTRACT["study_id"], "complete_cells": cells, "attrition": attrition, "eligible_524": current["eligible_524"], "attempt_record_count":attempts,"verified_physical_http_count":verified_physical,"physical_request_ceiling": CONTRACT["protocol"]["maximum_physical_requests"], "three_item_mean": sum(item["primary_score"] for item in cells)/3 if len(cells)==3 else None, "three_item_static_178_mean":sum(item["static_178_ablation_score"] for item in cells)/3 if len(cells)==3 else None,"exact_gate_eligible": False, "evidence_status": "provisional_only"}


def publish(work: Path, output: Path) -> None:
    if output.exists(): raise ValueError("refusing to overwrite v9 public report")
    frozen=load_frozen(work)
    roots=[work,Path(str(frozen["v8_failure"]["root"])),Path(str(frozen["zero_cost_proof"]["path"])),Path(str(frozen["zero_cost_proof"]["catalog"]["root"])),Path(str(frozen["zero_cost_proof"]["usage"]["root"]))]
    if any(output.resolve()==root.resolve() or output.resolve() in root.resolve().parents or root.resolve() in output.resolve().parents for root in roots): raise ValueError("v9 public output must be disjoint from private evidence")
    payload = report(work); output.parent.mkdir(parents=True,exist_ok=True); stage=Path(tempfile.mkdtemp(prefix=f".{output.name}.",dir=output.parent))
    try:
        text=json.dumps(payload,sort_keys=True,indent=2)+"\n"
        forbidden=[str(root.resolve()) for root in roots]+["source.md","prompt.md","task-contract.json"]
        if any(token and token in text for token in forbidden): raise ValueError("v9 public output would leak private inputs")
        (stage/"summary.json").write_text(text,encoding="utf-8")
        manifest={"format_version":1,"study_id":CONTRACT["study_id"],"contract_sha256":sha(Path(__file__).with_name("study-contract.json")),"summary":fingerprint(stage/"summary.json")}
        (stage/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n",encoding="utf-8")
        if any(token and token in "\n".join(item.read_text(encoding="utf-8") for item in stage.iterdir()) for token in forbidden): raise ValueError("v9 public output leaks private inputs")
        os.replace(stage,output)
    except Exception:
        for path in stage.glob("*"): path.unlink(missing_ok=True)
        stage.rmdir(); raise


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--work-dir",required=True,type=Path); parser.add_argument("--output-dir",required=True,type=Path); args=parser.parse_args(); publish(args.work_dir.resolve(),args.output_dir.resolve())
