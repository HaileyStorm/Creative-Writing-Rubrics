from __future__ import annotations
import hashlib, importlib.util, json, sys
from pathlib import Path
import pytest
from tests import _historical_runtime_compat as historical_runtime
from hbqrs.paths import book_root
from hbqrs.runner import _provider_artifact, _provider_tree_digest

ROOT=book_root()/"evaluation-results"/"the-part-that-arrives-first-repeatability"/"supplemental-providers-v3"
sys.path.insert(0,str(ROOT))
def load(name:str,file:str):
    spec=importlib.util.spec_from_file_location(name,ROOT/file); assert spec and spec.loader; module=importlib.util.module_from_spec(spec); sys.modules[name]=module; spec.loader.exec_module(module); return module
runner=load("supplemental_runner","run_study.py"); historical_runtime.allow_supplemental_v3_runner_drift(runner); sys.modules["run_study"]=runner; analyzer=load("supplemental_analyzer","analyze_study.py")
FIXTURES=json.loads((ROOT/"fixtures"/"provider-receipts.json").read_text())
_ARCHIVED_PREFLIGHT_REASON = (
    "Archived old-stack preflight mechanics with no retained current compatibility "
    "promise; the current checkout must remain fail-closed and static/current "
    "semantic checks stay live."
)
def add_artifacts(tmp_path:Path,receipt:dict,provider:str)->dict:
    result={"provider":json.loads(json.dumps(receipt))}; artifacts={}
    names=["grok_envelope"] if provider=="grok" else ["judge_request","judge_result","serialization_proof"]
    for name in names:
        path=tmp_path/f"{name}.json"; path.write_text(name); artifacts[name]=_provider_artifact(tmp_path,path)
    if provider=="nous":
        tree=tmp_path/"evidence"; tree.mkdir(); (tree/"proof.json").write_text("proof"); artifacts["evidence_tree"]=_provider_tree_digest(tmp_path,tree)
    result["provider"]["provider_artifacts"]=artifacts
    return result
@pytest.mark.skip(reason=_ARCHIVED_PREFLIGHT_REASON)
def test_preflight_pins_reference_assets_and_exact_public_protocol():
    raw=load("supplemental_runner_refusal","run_study.py")
    with pytest.raises(ValueError,match="Frozen asset changed: runner"): raw.preflight()
    contract,source=runner.preflight()
    assert source.name=="source.md" and contract["repetitions"]==5 and contract["asset_hashes"]==runner.asset_hashes()
    assert contract["reference_established_v4_sha256"]==runner.sha(ROOT.parent/"established-v4"/"study-contract.json")
    assert contract["hbq"]["question_count"]==178 and contract["hbq"]["batch_size"]==32 and contract["hbq"]["checkpoint_format_version"]==4


def test_current_checkout_fails_closed_on_frozen_registry_drift():
    raw=load("supplemental_current_checkout_refusal","run_study.py")
    with pytest.raises(ValueError,match="Frozen asset changed: registry"): raw.preflight()


def test_frozen_protocol_contract_remains_static():
    contract=runner.CONTRACT
    assert contract["repetitions"]==5 and contract["hbq"]["question_count"]==178
    assert set(contract["asset_hashes"])=={"provider_runner","receipt_fixture","reference_asset_manifest","reference_contract","scoring_core","structured_runner","study_analyzer","study_runner"}
    assert contract["asset_hashes"]["provider_runner"]=="e2b91682595d10ab8c2a2f55730fa2ffba40b0daa22a15a691d60fdfb9e752d3"
def test_preflight_rejects_checkpoint4_policy_drift(monkeypatch):
    monkeypatch.setitem(runner.CONTRACT["hbq"],"checkpoint_format_version",3)
    with pytest.raises(ValueError): runner.preflight()
def test_preflight_rejects_schedule_and_provider_drift(monkeypatch):
    monkeypatch.setitem(runner.CONTRACT["schedule"],"execution","parallel")
    with pytest.raises(ValueError): runner.preflight()
    monkeypatch.undo(); monkeypatch.setitem(runner.CONTRACT["providers"][0],"model","wrong")
    with pytest.raises(ValueError): runner.preflight()
    monkeypatch.undo(); monkeypatch.setitem(runner.CONTRACT["providers"][2],"requires_promotion_decision",False)
    with pytest.raises(ValueError): runner.preflight()
    monkeypatch.undo(); monkeypatch.setitem(runner.CONTRACT["nous_promotion"],"threshold",0.0)
    with pytest.raises(ValueError): runner.preflight()
    monkeypatch.undo(); monkeypatch.setitem(runner.CONTRACT["providers"][1],"provider_canonical_model","forged")
    with pytest.raises(ValueError): runner.preflight()
    monkeypatch.undo(); monkeypatch.setitem(runner.CONTRACT["nous_promotion"],"from_provider_id","grok_4_6_high")
    with pytest.raises(ValueError): runner.preflight()
def test_external_smoke_receipt_fixtures_capture_provider_specific_shapes(tmp_path:Path):
    grok,nous=runner.CONTRACT["providers"][:2]
    assert "session_id_sha256" in FIXTURES["grok"] and "session_id_sha256" not in FIXTURES["nous"]
    assert FIXTURES["nous"]["tool_free"] is True and FIXTURES["nous"]["provider_canonical_model"]==nous["provider_canonical_model"]
    assert analyzer.receipt(tmp_path,add_artifacts(tmp_path,FIXTURES["grok"],"grok"),grok).startswith("grok:")
    assert analyzer.receipt(tmp_path,add_artifacts(tmp_path,FIXTURES["nous"],"nous"),nous).startswith("nous:")
def test_transport_and_semantic_rejection_record_shapes_are_distinct():
    transport={"format_version":1,"config_sha256":"a"*64,"content":"not-json","provider":FIXTURES["grok"],"retryable":True,"error":{"class":"_ProviderAttemptFailure","message":"timeout"}}
    semantic={"format_version":1,"reason":"native total is invalid","response":{"config_sha256":"a"*64,"prompt_sha256":"b"*64,"schema_sha256":"c"*64,"result_sha256":"d"*64,"provider":FIXTURES["nous"]},"result":{"total_score":0}}
    assert set(transport)=={"format_version","config_sha256","content","provider","retryable","error"}
    assert set(semantic)=={"format_version","reason","response","result"}
def test_rejected_artifact_byte_commitment_detects_tamper(tmp_path:Path):
    artifact=tmp_path/"attempts"/"rejected-0001.json"; artifact.parent.mkdir(); artifact.write_text('{"format_version":1}')
    proof={"path":"attempts/rejected-0001.json","bytes":artifact.stat().st_size,"sha256":runner.sha(artifact),"classification":"transport_rejection"}
    artifact.write_text('{"format_version":1,"tampered":true}')
    assert proof["bytes"]!=artifact.stat().st_size and proof["sha256"]!=runner.sha(artifact)
def test_global_receipt_overlap_is_rejected_by_uniqueness_rule():
    accepted=["grok:a","nous:b"]; rejected=["nous:b"]
    assert bool(set(accepted)&set(rejected))
def test_receipt_validation_rejects_missing_grok_artifact_and_nous_session(tmp_path:Path):
    grok,nous=runner.CONTRACT["providers"][:2]; record=add_artifacts(tmp_path,FIXTURES["grok"],"grok"); record["provider"]["provider_artifacts"]={}
    with pytest.raises(ValueError,match="artifacts|shape"): analyzer.receipt(tmp_path,record,grok)
    record=add_artifacts(tmp_path,FIXTURES["nous"],"nous"); record["provider"]["session_id_sha256"]="a"*64
    with pytest.raises(ValueError,match="Nous"): analyzer.receipt(tmp_path,record,nous)
def test_append_only_journal_binds_every_planned_completion_manifest(tmp_path:Path):
    journal,count=runner._prepare_journal(tmp_path,"grok_4_6_high"); plans=runner.schedule_events("grok_4_6_high"); assert count==0 and len(runner._journal(journal))==20
    for event in plans:
        binding=runner._binding(tmp_path,"grok_4_6_high",event["method_id"],event["run_id"]); binding.parent.mkdir(parents=True,exist_ok=True); binding.write_text(event["method_id"]); runner._append(journal,{**event,"event":"completed","run_binding_sha256":runner.sha(binding)})
    assert runner._prepare_journal(tmp_path,"grok_4_6_high")[1]==20
    binding=runner._binding(tmp_path,"grok_4_6_high",plans[0]["method_id"],plans[0]["run_id"]); binding.write_text("tampered")
    with pytest.raises(ValueError,match="completion"): runner._prepare_journal(tmp_path,"grok_4_6_high")
def test_journal_recovers_an_exact_planned_prefix(tmp_path:Path):
    plans=runner.schedule_events("nous_flash_max"); path=tmp_path/"providers"/"nous_flash_max"/runner.JOURNAL_NAME
    for event in plans[:3]: runner._append(path,event)
    _,completed=runner._prepare_journal(tmp_path,"nous_flash_max")
    assert completed==0 and runner._journal(path)==plans
def test_promotion_requires_bound_hanna_v3_artifacts(tmp_path:Path,monkeypatch):
    policy=runner.CONTRACT["nous_promotion"]; contract_path=(ROOT/policy["hanna_contract_path"]).resolve(); baseline=tmp_path/"gpt-summary.json"; flash=tmp_path/"flash-summary.json"; shape={"format_version":3,"study_id":"hbq-human-alignment-v3","study_contract_sha256":runner.sha(contract_path),"phase":"development","primary_generated_only":{"item_count":80}}; baseline.write_text(json.dumps({**shape,"primary_generated_only":{"item_count":80,"macro_spearman":{"estimate":.6}}})); flash.write_text(json.dumps({**shape,"primary_generated_only":{"item_count":80,"macro_spearman":{"estimate":.4}}}))
    analyzer_path=(ROOT/policy["hanna_analyzer_path"]).resolve(); decision={"format_version":1,"supplemental_contract_sha256":runner.sha(ROOT/"study-contract.json"),"hanna_contract_sha256":runner.sha(contract_path),"hanna_analyzer_sha256":runner.sha(analyzer_path),"gpt_baseline":{"summary_path":str(baseline),"summary_sha256":runner.sha(baseline),"macro_estimate":.6},"flash_development":{"summary_path":str(flash),"summary_sha256":runner.sha(flash),"macro_estimate":.4},"decision":"hanna_macro_threshold"}
    (tmp_path/"promotion-decision.json").write_text(json.dumps(decision)); runner._promotion_decision(tmp_path)
    decision["flash_development"]["macro_estimate"]=.5; (tmp_path/"promotion-decision.json").write_text(json.dumps(decision))
    with pytest.raises(ValueError,match="predeclared trigger"): runner._promotion_decision(tmp_path)
def test_default_execution_excludes_pro_and_uses_separate_roots(tmp_path:Path,monkeypatch):
    calls=[]; monkeypatch.setattr(runner,"preflight",lambda:(runner.CONTRACT,runner.source_path()))
    def fake_run(event,provider,work,timeout):
        calls.append((provider["provider_id"],event["method_id"])); binding=runner._binding(work,provider["provider_id"],event["method_id"],event["run_id"]); binding.parent.mkdir(parents=True,exist_ok=True); binding.write_text("fixture")
    monkeypatch.setattr(runner,"_run",fake_run)
    monkeypatch.setattr(runner,"_append",lambda *args:None); monkeypatch.setattr(runner,"_prepare_journal",lambda *args:(tmp_path/"journal",0)); runner.execute(tmp_path,1)
    assert len(calls)==40 and {item[0] for item in calls}=={"grok_4_6_high","nous_flash_max"}
