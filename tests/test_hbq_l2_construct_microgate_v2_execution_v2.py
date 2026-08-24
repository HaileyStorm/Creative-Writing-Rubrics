from __future__ import annotations
import importlib.util, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import pytest
from hbqrs.paths import book_root
ROOT = book_root() / "evaluation-results" / "hbq-l2-construct-microgate-v2-execution-v2"
def study():
    spec = importlib.util.spec_from_file_location("l2_v2_exec", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module
@pytest.fixture
def private_root():
    root = Path(tempfile.mkdtemp(prefix="cwr-l2-v2-exec-")); yield root; shutil.rmtree(root, ignore_errors=True)
@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    for name in tuple(os.environ):
        if "API_KEY" in name.upper() or name.upper().startswith("OPENAI_API_"): monkeypatch.delenv(name, raising=False)
def fake_auth(command, **kwargs):
    assert kwargs["timeout"] == 20 and "OPENAI_API_KEY" not in kwargs["env"]
    if command[-1] == "--version": return type("R", (), {"returncode": 0, "stdout": "codex test", "stderr": ""})()
    return type("R", (), {"returncode": 0, "stdout": "ChatGPT subscription", "stderr": ""})()
def accepted(contacts, verdict="YES", quote=None):
    def call(command, **kwargs):
        contacts.append((command, kwargs)); output = Path(command[command.index("--output-last-message") + 1]); assert output.parent.is_dir()
        question_id = next(line for line in kwargs["input"].splitlines() if '"question_id":' in line).split('"')[3]
        evidence={"kind":"exact_quote","reference":"synthetic","exact_quote":quote,"summary":None} if quote is not None else {"kind":"summary","reference":"synthetic","exact_quote":None,"summary":"Grounded."}
        output.write_text(json.dumps({"verdicts":[{"question_id":question_id,"verdict":verdict,"confidence":0.8,"evidence":[evidence],"note":"test"}]}), encoding="utf-8")
        return type("R", (), {"returncode":0,"stdout":"done","stderr":"provider: openai\nmodel: gpt-5.6-sol\nreasoning effort: high\n"})()
    return call
def record(slot, verdict="YES"):
    return {"slot_id":slot["slot_id"],"logical_sample_id":slot["logical_sample_id"],"run_id":slot["run_id"],"verdict":verdict,"response_sha256":"a"*64,"attachment_sha256":slot["image_input"]["sha256"] if slot["image_input"] else None,"normalization_audit":[]}
def test_geometry_bindings_and_nonvoting_failed_lineage():
    s=study(); assert s.validate_package()["slots"] == 36; slots=s.build_schedule()
    assert len(slots) == len({x["slot_id"] for x in slots}) == 36
    assert len({(x["case_id"],x["leaf_id"]) for x in slots}) == 12 and sum(x["image_input"] is not None for x in slots) == 6
    failed=s.contract()["failed_execution"]; assert failed["non_voting"] is True and failed["root_basename"] == "cwr-l2-construct-v2-execution-final-5c6352e-20260824" and failed["accepted_slots"] == 4 and failed["later_slots_blocked_before_dispatch"] == 31 and failed["execution_claim_sha256"] == "97ff5740d5615d4ef3b87269aac51cba6270c59f61b7f052a33f402bbad1d545"
    assert s.contract()["gating"] == {"target_cells":{"leaf_id":"form.poetry.free_verse.line_breaks","count":4},"control_cells":{"canonical_necessity":4,"visual":4,"total":8},"only_all_12_cells_three_of_three":"HOLDOUT_ELIGIBLE_ON_SUCCESS","any_target_or_control_cell_below_three_of_three":"NO_GO"}
def test_prompts_are_production_shaped_and_ledger_blind():
    s=study(); slots=s.build_schedule(); artifacts=s._artifact_by_case(); records=s._frozen_leaf_records()
    for slot in slots:
        question=json.loads(s.canonical_json(records[slot["leaf_id"]]).decode("utf-8"))
        if slot["leaf_id"] == "form.poetry.free_verse.line_breaks": question["question"]["text"]=s._predecessor().CANDIDATE_TEXT
        artifact=artifacts[slot["case_id"]]
        expected=s._production_runner()._render_prompt(binary_prompt=s._frozen_binary_prompt(),artifact={"name":artifact["artifact_name"],"text":artifact["text"]},contexts=[],bundle_id=artifact["bundle_id"],artifact_id="public-synthetic-artifact",questions=[question],task_contract_context=s._task_context(artifact))
        assert slot["prompt"] == expected
    assert all("expected_verdict" not in x["prompt"] and "expected-ledger" not in x["prompt"] for x in slots)
    assert all(x["slot_id"].startswith("l2microexec-v2q-") for x in slots)
    aggregate=s.sha256_bytes(s.canonical_json({x["slot_id"]:x["prompt_sha256"] for x in slots}))
    assert len(aggregate)==64 and aggregate != "bc182dc2a6c2d66cc1d642eb399fe9be28657ae87f1995d03b140e8bfffd81d9"
def test_dry_run_exact_png_and_no_image_control(private_root):
    s=study(); report=s.dry_run(private_root, auth_call=fake_auth); assert report["provider_calls"] == 0 and report["planned_slots"] == 36
    c03=next(x for x in s.build_schedule() if x["case_id"] == "c03"); c04=next(x for x in s.build_schedule() if x["case_id"] == "c04")
    assert c03["artifact_sha256"] != s.sha256_bytes(c03["artifact_text"].encode()) and "--image" in s.command_for(c03, private_root) and "--image" not in s.command_for(c04, private_root)
    assert (private_root/"inputs"/"stairwell-01.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
def test_atomic_claim_and_no_old_root_reuse(private_root):
    s=study(); s.dry_run(private_root, auth_call=fake_auth); s._claim_execution(private_root,s.build_schedule())
    with pytest.raises(ValueError,match="claim already exists"): s.execute(private_root,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=accepted([]),auth_call=fake_auth)
    assert not (private_root/"runs"/"l2microexec-v2q-001").exists()
@pytest.mark.parametrize("mode",["nonzero","timeout","zero"])
def test_one_contact_failure_blocks_35_later_slots(private_root,mode):
    s=study(); s.dry_run(private_root,auth_call=fake_auth); contacts=[]
    def call(command,**kwargs):
        contacts.append(True)
        if mode=="timeout": raise subprocess.TimeoutExpired(command,kwargs["timeout"])
        return type("R",(),{"returncode":1 if mode=="nonzero" else 0,"stdout":"zero","stderr":"bad"})()
    with pytest.raises(RuntimeError,match="no resend"): s.execute(private_root,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=call,auth_call=fake_auth)
    terminals=[json.loads(s._sidecar_path(private_root,x).read_text()) for x in s.build_schedule()]
    assert len(contacts)==1 and terminals[0]["state"]=="ambiguous_contact" and sum(x["state"]=="blocked_before_dispatch" for x in terminals[1:])==35
def test_not_applicable_and_36_contact_success(private_root):
    s=study(); s.dry_run(private_root,auth_call=fake_auth); contacts=[]
    assert s.execute(private_root,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=accepted(contacts,"NOT_APPLICABLE"),auth_call=fake_auth)["completed_slots"]==36
    assert len(contacts)==36 and all(json.loads(s._sidecar_path(private_root,x).read_text())["state"]=="accepted" for x in s.build_schedule())
    settlement=s.settle(private_root,scorer=lambda _slot,_record: True)
    public=json.loads((private_root/"public-aggregate.v1.json").read_text()); marker=json.loads((private_root/"settlement-publication.v1.json").read_text())
    assert settlement["decision"]=="HOLDOUT_ELIGIBLE_ON_SUCCESS" and public["target_control_cells"]=={"target":{"three_of_three":4,"below_three_of_three":0},"control":{"three_of_three":8,"below_three_of_three":0}}
    assert marker["public_sha256"]==s.sha256_file(private_root/"public-aggregate.v1.json") and marker["settlement_sha256"]==s.sha256_file(private_root/"settlement.v1.json")
def test_diagnostic_mutation_rejected(private_root):
    s=study(); s.dry_run(private_root,auth_call=fake_auth); s.execute(private_root,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=accepted([]),auth_call=fake_auth)
    slot=s.build_schedule()[0]; path=s._attempt_dir(private_root,slot)/"local-output"/"stdout.txt"; path.write_bytes(path.read_bytes()+b"x")
    with pytest.raises(ValueError,match="diagnostic"): s.settle(private_root,scorer=lambda _slot,_record: True)
def test_four_state_aggregate_and_aggregate_only_publication():
    s=study(); slots=s.build_schedule(); states=("YES","NO","NOT_APPLICABLE","CANNOT_ASSESS")
    result,public=s._aggregate_test_only(schedule=slots,records=[record(x,states[i%4]) for i,x in enumerate(slots)],scorer=lambda _slot,_record: True)
    assert result["aggregate_cells"]=={"zero_of_three":0,"one_of_three":0,"two_of_three":0,"three_of_three":12,"total":12}
    assert result["verdict_counts"]=={"CANNOT_ASSESS":9,"NO":9,"NOT_APPLICABLE":9,"YES":9}
    assert result["decision"]=="HOLDOUT_ELIGIBLE_ON_SUCCESS" and public["target_control_cells"]=={"target":{"three_of_three":4,"below_three_of_three":0},"control":{"three_of_three":8,"below_three_of_three":0}} and "verdict_counts" not in public

@pytest.mark.parametrize("kind",["target_zero","control_zero","variance"])
def test_any_candidate_or_control_miss_is_no_go(kind):
    s=study(); slots=s.build_schedule(); scores={slot["slot_id"]:True for slot in slots}
    target=next(slot for slot in slots if slot["leaf_id"]==s.TARGET_LEAF)
    control=next(slot for slot in slots if slot["leaf_id"]!=s.TARGET_LEAF)
    if kind=="target_zero":
        for slot in slots:
            if (slot["case_id"],slot["leaf_id"]) == (target["case_id"],target["leaf_id"]): scores[slot["slot_id"]]=False
    elif kind=="control_zero":
        for slot in slots:
            if (slot["case_id"],slot["leaf_id"]) == (control["case_id"],control["leaf_id"]): scores[slot["slot_id"]]=False
    else: scores[target["slot_id"]]=False
    result,public=s._aggregate_test_only(schedule=slots,records=[record(slot) for slot in slots],scorer=lambda slot,_record:scores[slot["slot_id"]])
    assert result["decision"]=="NO_GO" and public["target_control_cells"]["target"]["below_three_of_three"] >= (1 if kind!="control_zero" else 0) and public["target_control_cells"]["control"]["below_three_of_three"] >= (1 if kind=="control_zero" else 0)

@pytest.mark.parametrize("mutation",["receipt","response"])
def test_receipt_or_response_mutation_rejected(private_root,mutation):
    s=study(); s.dry_run(private_root,auth_call=fake_auth); s.execute(private_root,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=accepted([]),auth_call=fake_auth)
    slot=s.build_schedule()[0]
    path=(s._attempt_dir(private_root,slot)/"receipt.json") if mutation=="receipt" else s._response_path(private_root,slot)
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError): s.settle(private_root,scorer=lambda _slot,_record: True)

def test_prepared_transaction_recovery_and_claim_requirement(private_root):
    s=study(); slots=s.build_schedule(); settlement,public=s._aggregate_test_only(schedule=slots,records=[record(slot) for slot in slots],scorer=lambda _slot,_record: True)
    with pytest.raises(ValueError,match="immutable execution claim"): s._write_settlement(private_root,settlement,public)
    claim=s._claim_execution(private_root,slots); bound=s.sha256_bytes(s.canonical_json(claim)); settlement["execution_claim_sha256"]=bound; public["execution_claim_sha256"]=bound
    def interrupted(path,value):
        if path.name=="public-aggregate.v1.json": raise RuntimeError("crash")
        s._write_or_verify(path,value)
    with pytest.raises(RuntimeError,match="crash"): s._write_settlement(private_root,settlement,public,writer=interrupted)
    s._write_settlement(private_root,settlement,public)
    assert (private_root/"settlement-publication.v1.json").is_file()

def test_canonical_quote_normalization_is_typed_and_replayable():
    s=study(); slot=next(x for x in s.build_schedule() if x["case_id"]=="p01")
    def payload(quote): return {"verdicts":[{"question_id":slot["leaf_id"],"verdict":"YES","confidence":0.8,"evidence":[{"kind":"exact_quote","reference":"synthetic","exact_quote":quote,"summary":None}],"note":"test"}]}
    repaired=s._validate_response(slot,payload("I step\n off")); evidence=repaired["verdict"]["evidence"][0]
    assert evidence=={"reference":"synthetic","summary":"I step\n off"} and repaired["normalization_audit"]==[{"question_id":slot["leaf_id"],"evidence_index":1,"raw_sha256":s.sha256_bytes(b"I step\n off"),"from":"exact_quote","to":"summary","reason":"not_verbatim"}]
    exact=s._validate_response(slot,payload("I step\noff")); assert exact["verdict"]["evidence"][0]=={"reference":"synthetic","exact_quote":"I step\noff"} and exact["normalization_audit"]==[]

@pytest.mark.parametrize("evidence",[
    {"kind":"exact_quote","reference":"synthetic","exact_quote":"","summary":None},
    {"kind":"summary","reference":"synthetic","exact_quote":None,"summary":""},
])
def test_empty_or_malformed_evidence_rejects(evidence):
    s=study(); slot=s.build_schedule()[0]
    payload={"verdicts":[{"question_id":slot["leaf_id"],"verdict":"YES","confidence":0.8,"evidence":[evidence],"note":"test"}]}
    with pytest.raises(ValueError,match="normalization"): s._validate_response(slot,payload)

def test_settlement_exposes_only_normalization_event_count(private_root):
    s=study(); s.dry_run(private_root,auth_call=fake_auth); s.execute(private_root,allow_remote=True,acknowledged_zero_incremental_charge=True,runner_call=accepted([],quote="not a verbatim quote"),auth_call=fake_auth)
    settlement=s.settle(private_root,scorer=lambda _slot,_record: True); public=json.loads((private_root/"public-aggregate.v1.json").read_text())
    assert settlement["normalization_events"]==36 and public["normalization_events"]==36 and "normalization_audit" not in public

def test_runtime_byte_drift_fails_closed_before_normalization(monkeypatch):
    s=study(); slot=s.build_schedule()[0]; original=s.sha256_file; imports=[]
    monkeypatch.setattr(s,"sha256_file",lambda path: "0"*64 if str(path).replace("\\","/").endswith("src/hbqrs/runner.py") else original(path))
    monkeypatch.setattr(s,"_import_production_runner",lambda: imports.append(True))
    payload={"verdicts":[{"question_id":slot["leaf_id"],"verdict":"YES","confidence":0.8,"evidence":[{"kind":"summary","reference":"synthetic","exact_quote":None,"summary":"Grounded."}],"note":"test"}]}
    with pytest.raises(ValueError,match="Current runtime differs"): s._validate_response(slot,payload)
    assert imports==[]
