"""Offline settlement for the frozen 168-request development comparison."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from study import build_plan, load_json, verify_package

def settle(responses_path: Path) -> dict:
    contract=load_json("study-contract.json"); corpus=load_json("public-synthetic-prompt-scope-corpus.json"); plan=build_plan(corpus,contract)
    responses=json.loads(responses_path.read_text(encoding="utf-8")); by_id={row.get("request_id"):row for row in responses if isinstance(row,dict)}
    if not isinstance(responses,list) or len(by_id)!=len(responses) or set(by_id)!={row["request_id"] for row in plan}: raise ValueError("Responses must exactly match the frozen development plan")
    sessions=set(); passed=[]; control_by_arm={"baseline":[],"scope_rendering_only":[]}; gate_rows={"stockness":[],"proportion_material_load":[],"fatigue":[],"isolated_yes_revision_note":[],"recurring_no":[],"excerpt_cannot_assess":[],"control_regression":[],"schema_evidence_provenance":[]}
    for expected in plan:
        row=by_id[expected["request_id"]]; provenance=row.get("provider_provenance",{})
        if any(row.get(key)!=expected[key] for key in ("request_id","study_id","partition","arm","case_id","leaf_id","repeat","artifact_sha256")) or provenance.get("route")!="codex" or provenance.get("model")!="gpt-5.6-sol" or provenance.get("reasoning")!="high" or not isinstance(provenance.get("run_id"),str) or not provenance["run_id"].strip() or provenance["run_id"] in sessions: raise ValueError("Response provenance does not match frozen plan")
        sessions.add(provenance["run_id"]); source="\n".join(expected["units"])
        if not isinstance(row.get("evidence"),list) or not row["evidence"] or any(not isinstance(e,dict) or not isinstance(e.get("reference"),str) or not e["reference"].strip() or not isinstance(e.get("quote"),str) or not e["quote"].strip() or e["quote"] not in source for e in row["evidence"]): raise ValueError("Evidence does not ground in frozen source")
        valid_controller=bool(row.get("controller_scope_materiality")==expected["controller_scope_materiality"] and row.get("controller_scope_verdict")==expected["controller_scope_verdict"] and (expected["case_id"]!="isolated-local-defect" or isinstance(row.get("revision_note"),str) and row["revision_note"].strip()))
        passed_row=row.get("verdict")==expected["expected_verdict"] and valid_controller; passed.append(passed_row); gate_rows["schema_evidence_provenance"].append(True)
        case=expected["case_id"]; leaf=expected["leaf_id"]
        if leaf=="core.freshness_and_non_genericness.no_default_metaphors": gate_rows["stockness"].append(passed_row)
        if leaf=="penalty.purple_prose.proportion": gate_rows["proportion_material_load"].append(passed_row)
        if leaf=="penalty.purple_prose.fatigue": gate_rows["fatigue"].append(passed_row)
        if case=="isolated-local-defect": gate_rows["isolated_yes_revision_note"].append(passed_row)
        if case=="recurring-scope-defect": gate_rows["recurring_no"].append(passed_row)
        if case=="incomplete-scope": gate_rows["excerpt_cannot_assess"].append(passed_row)
        if case in {"low-density-default-control","high-density-specific-control"}: control_by_arm[expected["arm"]].append(passed_row)
    gates={name:{"passed":all(rows),"denominator":len(rows),"correct":sum(rows)} for name,rows in gate_rows.items()}
    baseline=control_by_arm["baseline"]; candidate=control_by_arm["scope_rendering_only"]
    gates["control_regression"]={"passed":sum(candidate)>=sum(baseline),"denominator":len(baseline)+len(candidate),"correct":sum(baseline)+sum(candidate),"baseline_correct":sum(baseline),"candidate_correct":sum(candidate)}
    return {"phase":"development","denominator":len(plan),"gates":gates,"all_frozen_gates_pass":all(item["passed"] for item in gates.values()),"negative_result":not all(item["passed"] for item in gates.values()),"writes":0}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--responses",type=Path,required=True); args=parser.parse_args(); print(json.dumps({"verification":verify_package(),"settlement":settle(args.responses)},sort_keys=True))
if __name__=="__main__": main()
