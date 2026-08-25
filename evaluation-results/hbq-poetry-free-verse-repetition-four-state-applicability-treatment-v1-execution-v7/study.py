"""Fresh v7 successor: provider-compatible exact-quote response schema."""
from __future__ import annotations
import hashlib, importlib.util, json, sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parent; REPOSITORY=ROOT.parents[1]
STUDY_ID="hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v7"; SOURCE_COMMIT="6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"; SOURCE_TREE="16f49b15706852ce64f5688f952b4f968707dc04"
V6_PATH=ROOT.parent/"hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v6"/"study.py"; V6_SHA256="af8e9f4df532083ca8079ece7afeb71a913d0855115574d702946098358c03d8"; V6_CONTRACT_SHA256="d859bdf16f0bc868f141cec223a85dc149c621a9450ba292c5fa6b210b6f63a4"
PROMPT_SOURCE=ROOT/"exact-quote-binary-prompt.md"; PROMPT_SHA256="70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"; SCHEMA_SOURCE=ROOT/"exact-quote-response.schema.json"; SCHEMA_SHA256="a72bf60e40f809e2acd89035c76ac3b000032d3d01fa7d8e7235f78a8a73b4fc"
CONTROLLER_SHA256="25f5d70ca50fae5ff35ac8731ed6a128d01a74c53802e04df290b7dc75e0fc85"; LEDGER_SHA256="1c045fdf28fd94e5721de0b88f9ceaa8691fedbf44695db57926cf7a2e3a2bdf"; VERIFIER_SHA256="3f79a39b42462886b1f9d25a3a8a4ebf30fe0029eda892855737dee93c3128e7"; FIXTURE_SHA256={"7eee7bbe1e394a506b88001566786dbf970004bf86d28e7370d517d6f5684c3d","262c3dbfd3c584462e5b4078e324cf8a3516be5ee9d4ecefb2ce20616d715fa7","5277854c7cfa6d324c4fd977b43926d5c74fd79a35094c5212a4e0ffc5c4e675","1fa7859c544799a182a81f374693274dd94e48eb3b264c99f5559467b4e0185c"}; PRIVATE_EXECUTION_DIRECTORY="execution-v7-preexecution-freeze-v1"; SLOTS,ARMS,REPEATS=12,("candidate",),(1,2,3); BUNDLE_ID="diagnostic.poetry_free_verse_repetition_four_state_applicability_v7"; SUCCESSOR_FILES=("study.py","run.py","study-contract.json","exact-quote-binary-prompt.md","exact-quote-response.schema.json")
_CONFIGURED=False; _PROTOCOL_BASE=None
def sha256_file(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
@lru_cache(maxsize=1)
def _v6():
    if not V6_PATH.is_file() or sha256_file(V6_PATH)!=V6_SHA256:raise ValueError("Frozen v6 successor drifted")
    c=V6_PATH.parent/"study-contract.json"
    if not c.is_file() or sha256_file(c)!=V6_CONTRACT_SHA256:raise ValueError("Frozen v6 lineage contract drifted")
    s=importlib.util.spec_from_file_location("_s1_v7",V6_PATH)
    if s is None or s.loader is None:raise ValueError("Frozen v6 successor unavailable")
    m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
def _configure():
    global _CONFIGURED,_PROTOCOL_BASE
    value=_v6()
    if _CONFIGURED:return value
    v5=value._configure();v4=v5._v4();v3=v4._v3();base,v2,v1,clean=v3._base(),v3._v2(),v3._v2()._v1(),v3._v2()._v1()._adapter()
    for m in(value,v5,v4,v3,v2,v1,clean,base):
        m.ROOT=ROOT;m.REPOSITORY=REPOSITORY;m.STUDY_ID=STUDY_ID;m.SOURCE_COMMIT=SOURCE_COMMIT;m.SOURCE_TREE=SOURCE_TREE;m.CONTROLLER_SHA256=CONTROLLER_SHA256;m.LEDGER_SHA256=LEDGER_SHA256;m.VERIFIER_SHA256=VERIFIER_SHA256;m.PRIVATE_EXECUTION_DIRECTORY=PRIVATE_EXECUTION_DIRECTORY;m.SLOTS=SLOTS;m.ARMS=ARMS;m.REPEATS=REPEATS;m.BUNDLE_ID=BUNDLE_ID;m.SUCCESSOR_FILES=SUCCESSOR_FILES;m._private_freeze=_private_freeze;m.validate_package=validate_package
    _PROTOCOL_BASE=v3._protocol_prompt_scan;v3._protocol_prompt_scan=_protocol_prompt_scan;v3._write_protocol_receipt=_write_protocol_receipt;v3._require_protocol_receipt=_require_protocol_receipt;_CONFIGURED=True;return value
def provider_schema_subset(schema:Mapping[str,Any])->None:
    def walk(node:Any,path:str)->None:
        if isinstance(node,Mapping):
            if "const" in node and isinstance(node["const"],str) and node.get("type")!="string":raise ValueError(f"provider schema subset requires type:string for const at {path}")
            if "enum" in node and isinstance(node["enum"],list) and all(isinstance(x,str) for x in node["enum"]) and node.get("type")!="string":raise ValueError(f"provider schema subset requires type:string for enum at {path}")
            for key,item in node.items():walk(item,f"{path}/{key}")
        elif isinstance(node,list):
            for i,item in enumerate(node):walk(item,f"{path}/{i}")
    walk(schema,"$")
def _private_freeze():
    v6=_v6();v3=v6._v5()._v4()._v3();base=v3._base();cp,lp,vp=base._private_paths()
    if any(not p.is_file() or sha256_file(p)!=d for p,d in((cp,CONTROLLER_SHA256),(lp,LEDGER_SHA256),(vp,VERIFIER_SHA256))):raise ValueError("Private v7 controller, ledger, or verifier drifted")
    c,l=base._load_json(cp),base._load_json(lp);f,m=c.get("fixture_matrix"),l.get("slot_mapping")
    if c.get("study_id")!=STUDY_ID or c.get("format_version")!=7 or l.get("study_id")!=STUDY_ID or l.get("format_version")!=7 or not isinstance(f,list) or len(f)!=4 or not isinstance(m,list) or len(m)!=SLOTS:raise ValueError("Private v7 freeze geometry drifted")
    ids={str(x.get("fixture_id")) for x in f}; hashes={base.sha256_bytes(str(x.get("text")).encode()) for x in f}
    if len(ids)!=4 or hashes!=FIXTURE_SHA256:raise ValueError("Private v7 fixture commitments drifted")
    absence=[str(x.get("text")) for x in f if x.get("state")=="absence"]
    if len(absence)!=1:raise ValueError("Private v7 requires one absence fixture")
    v6.one_independent_clause_recurrence_free(absence[0]);art={};geometry=set();slots=set()
    for x in m:
        fid,aid,sid,repeat=str(x.get("fixture_id")),str(x.get("opaque_artifact_id")),str(x.get("opaque_slot_id")),int(x.get("repeat"))
        if fid not in ids or x.get("arm")!="candidate" or not v3._v2().OPAQUE_ARTIFACT.fullmatch(aid) or not v3._v2().OPAQUE_SLOT.fullmatch(sid) or repeat not in REPEATS:raise ValueError("Private v7 opaque mapping drifted")
        if art.setdefault(fid,aid)!=aid:raise ValueError("Fixture maps to multiple artifacts")
        geometry.add((fid,repeat));slots.add(sid)
    if len(set(art.values()))!=4 or geometry!={(x,r) for x in ids for r in REPEATS} or len(slots)!=SLOTS:raise ValueError("Private v7 schedule incomplete")
    return c,l
def _protocol_prompt_scan(schedule,prompts):
    if _PROTOCOL_BASE is None:raise ValueError("Protocol scanner unavailable")
    return {**_PROTOCOL_BASE(schedule,prompts),"format_version":7}
def _write_protocol_receipt(root,schedule):
    v3=_v6()._v5()._v4()._v3();r=v3._protocol_receipt(root,schedule);v3._base()._write_or_verify(root/"receipts"/"evidence-protocol-scan.v7.json",v3._base().canonical_json(r));return r
def _require_protocol_receipt(root,schedule):
    v3=_v6()._v5()._v4()._v3();p=root/"receipts"/"evidence-protocol-scan.v7.json"
    if not p.is_file() or v3._base()._load_json(p)!=v3._protocol_receipt(root,schedule):raise ValueError("Exact v7 evidence-protocol receipt required before claim")
def contract():
    x=json.loads((ROOT/"study-contract.json").read_text());
    if not isinstance(x,dict):raise TypeError("Study contract object required")
    return x
def _expected_contract():
    prior=json.loads((V6_PATH.parent/"study-contract.json").read_text())
    return {"format_version":7,"study_id":STUDY_ID,"status":"frozen_unexecuted_provider_schema_successor","source_checkout":{"commit":SOURCE_COMMIT,"tree":SOURCE_TREE,"exact_head_required_before_claim":True},"v6_consumed_outcome":{"package_path":V6_PATH.parent.relative_to(REPOSITORY).as_posix(),"executor_sha256":V6_SHA256,"contract_sha256":V6_CONTRACT_SHA256,"execution_claim_sha256":"49da5ba992f721cffb3ae48cd04f7775d920f79067d55547f1c8cec646064efa","zero_charge_acknowledgement_sha256":"a294c8775a49c91e8c51c92981de85e832d865cfa66f469d2dd9e2ba2806d02d","dispatch_start_sha256":"2eb68e76be4196c962e5b699d60c397f85f199b98b41293df8f536ced8ecbcf4","dispatch_failure_sha256":"15b06ca8e307db9c204d67fc4704ff7841f99d072af23922084eb69f5c033804","run_sha256":"d3a28a49ea9cecc3f5c29206802c78635909058f8633e70471e7632e5e4d1cec","rejected_attempt_sha256":"8202c905268c5829b92319bc3df0477dca429e5635b647396d264897ed40cc69","claim":1,"acknowledgement":1,"dispatches":1,"runs":1,"physical_attempts":1,"rejected_provider_retryable_failure_http_status":400,"error_code":"invalid_json_schema","raw_content_bytes":0,"accepted":0,"settled":0,"terminal":0,"untouched_slots":11,"formal_result":"NO_RESULT","promotion":"none","dspy":"not_authorized","wording_inference":"forbidden"},"inherited_v5_and_earlier_lineage_contract_sha256":V6_CONTRACT_SHA256,"candidate":prior["candidate"],"private_commitments":{"controller_sha256":CONTROLLER_SHA256,"ledger_sha256":LEDGER_SHA256,"verifier_sha256":VERIFIER_SHA256,"fixture_text_sha256":sorted(FIXTURE_SHA256)},"provider_schema_subset_gate":{"const_string_type_required":True,"string_enum_type_required":True,"checked_before_claim":True,"failure":"NO_RESULT_REFREEZE_REQUIRED"},"evidence_protocol":{**prior["evidence_protocol"],"response_schema_sha256":SCHEMA_SHA256},"identifier_boundary":prior["identifier_boundary"],"geometry":prior["geometry"],"execution":prior["execution"],"gating":prior["gating"],"promotion":"none","dspy":"not_implemented_runtime"}
def validate_package():
    value=_configure();v3=value._v5()._v4()._v3()
    if contract()!=_expected_contract():raise ValueError("V7 contract or lineage drifted")
    if v3._v2()._git("rev-parse",f"{SOURCE_COMMIT}^{{tree}}")!=SOURCE_TREE:raise ValueError("Frozen tree unavailable")
    for p,d in v3._v2()._v1()._adapter().RUNTIME_SHA256.items():
        if sha256_file(REPOSITORY/p)!=d:raise ValueError(f"Frozen runtime drifted: {p}")
    if sha256_file(PROMPT_SOURCE)!=PROMPT_SHA256 or sha256_file(SCHEMA_SOURCE)!=SCHEMA_SHA256:raise ValueError("Protocol source drifted")
    schema=json.loads(SCHEMA_SOURCE.read_text());provider_schema_subset(schema);item=schema["properties"]["verdicts"]["items"]["properties"];evidence=item["evidence"]["items"]["properties"]
    if evidence["kind"]!={"type":"string","const":"exact_quote"} or item["verdict"]!={"type":"string","enum":["YES","NO","NOT_APPLICABLE","CANNOT_ASSESS"]}:raise ValueError("Provider-compatible kind/verdict schema binding drifted")
    _private_freeze();schedule=v3.build_schedule()
    if len(schedule)!=SLOTS or any(not v3._v2().OPAQUE_ARTIFACT.fullmatch(x["fixture_id"]) for x in schedule):raise ValueError("V7 opaque schedule drifted")
    return {"study_id":STUDY_ID,"source_commit":SOURCE_COMMIT,"slots":SLOTS,"provider_calls":0,"provider_artifacts":4,"summary_evidence_available":False,"normalization_events_required":0,"success_authorizes_only":"fresh_disjoint_holdout"}
def set_private_root(p):return _configure().set_private_root(p)
def build_schedule():return _configure()._v5()._v4()._v3().build_schedule()
def dry_run(p,*,runner_call=None):v=_configure();return v.dry_run(p) if runner_call is None else v.dry_run(p,runner_call=runner_call)
def execute(p,*,allow_remote=False,acknowledged_zero_incremental_charge=False,runner_call=None):
    v=_configure();kw={"allow_remote":allow_remote,"acknowledged_zero_incremental_charge":acknowledged_zero_incremental_charge}
    if runner_call is not None:kw["runner_call"]=runner_call
    return v.execute(p,**kw)
def settle(p,*,verifier=None):return _configure().settle(p,verifier=verifier)
def command_for(slot,p,*,render=False):return _configure().command_for(slot,p,render=render)
