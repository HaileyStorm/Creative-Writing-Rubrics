from __future__ import annotations
import importlib.util, json, sys
from copy import deepcopy
import pytest
from hbqrs.paths import book_root

ROOT=book_root()/"evaluation-results"/"hbq-figurative-scope-treatment-v1"
def study():
    spec=importlib.util.spec_from_file_location("fst",ROOT/"study.py"); module=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=module; spec.loader.exec_module(module); return module
def read(name): return json.loads((ROOT/name).read_text(encoding="utf-8"))
def analyzer():
    sys.path.insert(0,str(ROOT)); spec=importlib.util.spec_from_file_location("fst_analyze",ROOT/"analyze.py"); module=importlib.util.module_from_spec(spec); assert spec and spec.loader; sys.modules[spec.name]=module; spec.loader.exec_module(module); return module
def responses(s):
    plan=s.build_plan(read("public-synthetic-prompt-scope-corpus.json"),read("study-contract.json")); out=[]
    for index,item in enumerate(plan): out.append({"request_id":item["request_id"],"study_id":item["study_id"],"partition":item["partition"],"arm":item["arm"],"case_id":item["case_id"],"leaf_id":item["leaf_id"],"repeat":item["repeat"],"artifact_sha256":item["artifact_sha256"],"controller_scope_materiality":item["controller_scope_materiality"],"controller_scope_verdict":item["controller_scope_verdict"],"revision_note":"local revision" if item["case_id"]=="isolated-local-defect" else None,"verdict":item["expected_verdict"],"evidence":[{"reference":"synthetic","quote":item["units"][0]}],"provider_provenance":{"route":"codex","model":"gpt-5.6-sol","reasoning":"high","run_id":f"session-{index}"}})
    return out

def test_frozen_development_geometry_and_isolated_controller_note():
    s=study(); contract=read("study-contract.json"); corpus=read("public-synthetic-prompt-scope-corpus.json")
    report=s.verify_package(); plan=s.build_plan(corpus,contract)
    assert report["development_requests"]==len(plan)==168
    assert {row["arm"] for row in plan}=={"baseline","scope_rendering_only"}
    isolated=next(row for row in plan if row["case_id"]=="isolated-local-defect")
    assert isolated["expected_verdict"]=="YES" and isolated["controller_scope_materiality"]=="revision_note"

def test_contract_and_corpus_are_pinned():
    s=study(); contract=read("study-contract.json"); changed=deepcopy(contract); changed["execution"]["development_repeats"]=4
    with pytest.raises(ValueError): s.validate_contract(changed)
    corpus=read("public-synthetic-prompt-scope-corpus.json"); changed=deepcopy(corpus); changed["records"][0]["target_verdicts"]={}
    with pytest.raises(ValueError): s.validate_corpus(changed)

def test_settlement_happy_negative_and_blank_note(tmp_path):
    s=study(); a=analyzer(); rows=responses(s); path=tmp_path/"responses.json"; path.write_text(json.dumps(rows),encoding="utf-8")
    assert a.settle(path)["all_frozen_gates_pass"] is True
    rows[0]["verdict"]="NO" if rows[0]["verdict"]!="NO" else "YES"; path.write_text(json.dumps(rows),encoding="utf-8")
    assert a.settle(path)["negative_result"] is True
    rows=responses(s); next(row for row in rows if row["case_id"]=="isolated-local-defect")["revision_note"]=""; path.write_text(json.dumps(rows),encoding="utf-8")
    assert a.settle(path)["negative_result"] is True
    rows=responses(s); target=next(row for row in rows if row["case_id"]=="high-density-specific-control" and row["arm"]=="scope_rendering_only" and row["repeat"]==2); target["verdict"]="NO" if target["verdict"]!="NO" else "YES"; path.write_text(json.dumps(rows),encoding="utf-8")
    control=a.settle(path)["gates"]["control_regression"]
    assert control["baseline_correct"]==12 and control["candidate_correct"]==11 and control["passed"] is False
