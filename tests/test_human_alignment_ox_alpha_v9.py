"""Adversarial coverage for the v9 unit-retry successor."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from hbqrs.paths import book_root

ROOT=book_root()/"evaluation-results"/"hbq-human-alignment-supplemental-providers-ox-alpha-v9"
V8=Path(r"C:\Users\Haile\Documents\cwr-ox-alpha-v8-full-scoring-20260821-73308d2")

def load(name, file, aliases=None):
    spec=importlib.util.spec_from_file_location(name,ROOT/file); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); prior={key:sys.modules.get(key) for key in aliases or {}}; sys.modules[spec.name]=mod; sys.modules.update(aliases or {})
    try: spec.loader.exec_module(mod)
    finally:
        for key,value in prior.items():
            if value is None: sys.modules.pop(key,None)
            else: sys.modules[key]=value
    return mod

study=load("ox_v9_study","study.py")
runner=load("ox_v9_runner","run_pilot.py",{"study":study})
reporter=load("ox_v9_reporter","analyze_pilot.py",{"study":study})

def test_contract_freezes_unit_retry_caps_pause_and_zero_cost():
    assert study.CONTRACT["protocol"]["units"]==135
    assert study.CONTRACT["protocol"]["attempts_per_unit"]==5
    assert study.CONTRACT["protocol"]["maximum_eligible_524"]==135
    assert study.CONTRACT["protocol"]["maximum_physical_requests"]==270
    assert study.CONTRACT["zero_cost"]=={"no_purchase":True,"stop_on_charge_signal":True,"stop_on_http_402":True}

def test_v8_failed_root_is_exact_one_524_without_completion_or_verdict():
    if not V8.is_dir(): pytest.skip("sealed v8 root unavailable")
    evidence=study.v8_failure(V8)
    assert evidence["provider"]==study.CONTRACT["provider"]
    assert evidence["request"]["name"].endswith(".nous.request.json")
    assert evidence["tree"]["files"]>0

def test_v8_units_are_exact_135_with_only_last_three_leaf_batches():
    if not V8.is_dir(): pytest.skip("sealed v8 root unavailable")
    base=study.parent_v8().load_frozen(V8); units=study.units(base)
    assert len(units)==135
    assert [len(unit["question_ids"]) for unit in units]==([4]*44+[3])*3
    assert len({unit["unit_id"] for unit in units})==135

def test_eligible_524_rejects_inbound_completion(tmp_path):
    run=tmp_path/"run"; rejected=run/"responses"/"rejected"/"batch-0001"; rejected.mkdir(parents=True)
    (rejected/"attempt-0001.json").write_text(json.dumps({"provider":None,"validation_feedback":None,"error":{"message":"HTTP 524"}}),encoding="utf-8")
    root=run/"responses"/"batch-0001.attempt-0001.nous.evidence"/"judge"; root.mkdir(parents=True)
    events=[{"event_type":"judge_boundary","data":{}},{"event_type":"message","data":{"direction":"inbound"}},{"event_type":"http_attempt","data":{"status":524}}]
    (root/"events.jsonl").write_text("".join(json.dumps(item)+"\n" for item in events),encoding="utf-8")
    (root/"receipt.json").write_text(json.dumps({"status":"failure"}),encoding="utf-8")
    unit={"item_id":"hanna-827","question_ids":["core.task_and_brief_fidelity.intervention"]}
    with pytest.raises(ValueError):
        runner._eligible_524(run,unit)

def test_same_unit_cooldown_escalates_after_three_eligible_524s():
    from datetime import datetime, timezone, timedelta
    now=datetime.now(timezone.utc)
    one=[{"status":"eligible_524","at":(now-timedelta(minutes=14)).isoformat()}]
    three=[{"status":"eligible_524","at":(now-timedelta(minutes=29)).isoformat()}]*3
    assert runner._cooldown_ready(one,now) is False
    assert runner._cooldown_ready(three,now) is False
    assert runner._cooldown_ready([{**one[0],"at":(now-timedelta(minutes=15)).isoformat()}],now) is True

def test_state_reconstructs_two_accepted_units_and_next_round(tmp_path):
    for cursor,unit in enumerate(("u1","u2")):
        runner._append_attempt(tmp_path,{"kind":"intent","unit_id":unit,"attempt":1,"round":1,"cursor":cursor,"at":"2026-08-22T00:00:00+00:00","unit":{}})
        runner._append_attempt(tmp_path,{"kind":"result","unit_id":unit,"attempt":1,"round":1,"cursor":cursor,"result":{"status":"accepted","attempt":1,"at":"2026-08-22T00:00:01+00:00"}})
    rebuilt=runner._reconstruct(tmp_path)
    assert list(rebuilt["units"])==["u1","u2"] and rebuilt["round"]==1
    runner._write_state(tmp_path,rebuilt)
    study.immutable_json(tmp_path/"epochs"/"0001.json",{"sequence":1,"round":1,"attempt_count":4,"state":runner._state_fingerprint(rebuilt)})
    assert runner._reconstruct(tmp_path)["round"]==2

def test_state_ignores_interrupted_temp_but_rejects_tamper_and_dangling_intent(tmp_path):
    (tmp_path/".state.crash.tmp").write_text("partial",encoding="utf-8")
    assert runner._state(tmp_path)["units"]=={}
    runner._write_state(tmp_path,runner._reconstruct(tmp_path))
    (tmp_path/"state.json").write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="state drifted"):
        runner._state(tmp_path)
    other=tmp_path/"other"; runner._append_attempt(other,{"kind":"intent","unit_id":"u","attempt":1,"round":1,"cursor":0,"at":"2026-08-22T00:00:00+00:00","unit":{}})
    with pytest.raises(ValueError,match="interrupted attempt"):
        runner._reconstruct(other)

def test_stale_execution_fails_before_claim_or_provider(monkeypatch,tmp_path):
    frozen={"zero_cost_proof":{},"units":[]}
    monkeypatch.setattr(runner,"load_frozen",lambda _:frozen)
    monkeypatch.setattr(runner,"parent_v8",lambda:type("V8",(),{"assert_fresh_at":staticmethod(lambda *_: (_ for _ in ()).throw(ValueError("stale")))})())
    with pytest.raises(ValueError,match="stale"):
        runner.execute_epoch(tmp_path)
    assert not (tmp_path/"execution-claim.json").exists()


def test_interrupted_execution_preserves_claim_for_offline_adjudication(monkeypatch,tmp_path):
    unit={"unit_id":"u000","item_id":"item","question_ids":[],"paths":{"artifact":str(tmp_path/"artifact.md"),"prompt":str(tmp_path/"prompt.md"),"task_contract":str(tmp_path/"task-contract.json")}}
    units=[unit, *[{**unit,"unit_id":f"u{number:03d}"} for number in range(1,135)]]
    study.immutable_json(tmp_path/study.FROZEN_NAME,{})
    monkeypatch.setattr(runner,"load_frozen",lambda _:{"zero_cost_proof":{},"units":units})
    monkeypatch.setattr(runner,"runtime_bindings",lambda:{})
    monkeypatch.setattr(runner,"_assert_identities",lambda *_:None)
    monkeypatch.setattr(runner,"parent_v8",lambda:type("V8",(),{"assert_fresh_at":staticmethod(lambda *_:None)})())
    monkeypatch.setattr(runner,"run_judge",lambda **_: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): runner.execute_epoch(tmp_path)
    assert (tmp_path/"execution-claim.json").is_file()
    assert len(runner._orphan_intents(tmp_path))==1

@pytest.mark.parametrize("field",["model","reasoning","provider_id"])
def test_contract_rejects_provider_drift(monkeypatch,tmp_path,field):
    value=json.loads((ROOT/"study-contract.json").read_text(encoding="utf-8")); value["provider"][field]="paid"; path=tmp_path/"contract.json"; path.write_text(json.dumps(value),encoding="utf-8")
    monkeypatch.setattr(study,"CONTRACT_PATH",path)
    with pytest.raises(ValueError,match="contract drifted"): study.contract()

def test_cursor_reconstructs_across_epochs_and_rejects_same_round_revisit(tmp_path):
    for round_number,cursor,unit in ((1,134,"tail"),(2,0,"head")):
        if round_number==2:
            boundary=runner._reconstruct(tmp_path)
            study.immutable_json(tmp_path/"epochs"/"0001.json",{"sequence":1,"round":1,"attempt_count":2,"state":runner._state_fingerprint(boundary)})
        runner._append_attempt(tmp_path,{"kind":"intent","unit_id":unit,"attempt":1,"round":round_number,"cursor":cursor,"at":"2026-08-22T00:00:00+00:00","unit":{}})
        runner._append_attempt(tmp_path,{"kind":"result","unit_id":unit,"attempt":1,"round":round_number,"cursor":cursor,"result":{"status":"eligible_524","attempt":1,"at":"2026-08-22T00:00:01+00:00","failed_identities":{"session_id":f"s{round_number}","logical_request_id":f"l{round_number}"}}})
    rebuilt=runner._reconstruct(tmp_path)
    assert rebuilt["round"]==2 and rebuilt["cursor"]==1 and rebuilt["eligible_524"]==2
    duplicate=tmp_path/"duplicate"
    for cursor in (0,1):
        runner._append_attempt(duplicate,{"kind":"intent","unit_id":"same","attempt":cursor+1,"round":1,"cursor":cursor,"at":"2026-08-22T00:00:00+00:00","unit":{}})
        runner._append_attempt(duplicate,{"kind":"result","unit_id":"same","attempt":cursor+1,"round":1,"cursor":cursor,"result":{"status":"quarantined"}})
    with pytest.raises(ValueError,match="round/cursor"):
        runner._reconstruct(duplicate)


def test_mixed_terminal_and_eligible_units_close_rounds_two_through_five(tmp_path):
    frozen={"units":[{"unit_id":f"u{number:03d}"} for number in range(135)]}
    sequence=0
    def record(value):
        nonlocal sequence
        sequence+=1; study.immutable_json(tmp_path/"attempt-records"/f"{sequence:06d}.json",{"sequence":sequence,**value})
    for cursor, unit in enumerate(frozen["units"]):
        unit_id=unit["unit_id"]
        record({"kind":"intent","unit_id":unit_id,"attempt":1,"round":1,"cursor":cursor,"at":"2026-08-22T00:00:00+00:00","unit":unit})
        status="eligible_524" if unit_id=="u002" else "quarantined" if unit_id=="u001" else "accepted"
        record({"kind":"result","unit_id":unit_id,"attempt":1,"round":1,"cursor":cursor,"result":{"status":status}})
    state=runner._reconstruct(tmp_path)
    expected=runner._round_start_expected_units(frozen,state,runner._round_attempted_units(tmp_path,round_number=1,frozen=frozen))
    assert expected=={"u002"}
    runner._assert_round_closed(expected,{"u002"},set())
    runner._append(tmp_path,{"round":1,"attempt_count":sequence,"state":runner._state_fingerprint(state)})
    for round_number in range(2,6):
        state=runner._reconstruct(tmp_path)
        assert state["round"]==round_number
        expected=runner._round_start_expected_units(frozen,state,set())
        assert expected=={"u002"}
        runner._assert_round_closed(expected,set(),{"u002"})
        record({"kind":"intent","unit_id":"u002","attempt":round_number,"round":round_number,"cursor":2,"at":"2026-08-22T00:00:00+00:00","unit":frozen["units"][2]})
        record({"kind":"result","unit_id":"u002","attempt":round_number,"round":round_number,"cursor":2,"result":{"status":"eligible_524"}})
        state=runner._reconstruct(tmp_path)
        runner._append(tmp_path,{"round":round_number,"attempt_count":sequence,"state":runner._state_fingerprint(state)})
    state=runner._reconstruct(tmp_path)
    assert state["round"]==6 and len(state["units"]["u002"])==5
    assert runner._round_start_expected_units(frozen,state,set())==set()

def test_identity_guard_rejects_v7_v8_and_internal_collisions(monkeypatch):
    class V8:
        @staticmethod
        def load_frozen(_):
            return {"v7_transport_success":{"global_ids":{"receipt_id":["old-r"],"session_id":["old-s"],"logical_request_id":["old-l"]}}}
    monkeypatch.setattr(runner,"parent_v8",lambda:V8())
    frozen={"v8_failure":{"root":"C:/evidence","failed_identities":{"session_id":"failed-s","logical_request_id":"failed-l","receipt_sha256":"f"*64,"serialization_proof_sha256":"p"*64}}}
    base={"units":{"u":[{"status":"accepted","accepted_identities":{"receipt_id":"new-r","session_id":"new-s","logical_request_id":"old-l"}}]}}
    with pytest.raises(ValueError,match="collides"):
        runner._assert_identities(frozen,base)
    base["units"]["u"][0]["accepted_identities"]["logical_request_id"]="new-l"
    base["units"]["v"]=[{"status":"eligible_524","failed_identities":{"session_id":"new-s","logical_request_id":"another-l","receipt_sha256":"a"*64,"serialization_proof_sha256":"b"*64}}]
    with pytest.raises(ValueError,match="collides"):
        runner._assert_identities(frozen,base)


def test_failed_identity_guard_rejects_v7_v8_and_all_v9_collisions(monkeypatch):
    class V8:
        @staticmethod
        def load_frozen(_):
            return {"v7_transport_success":{"global_ids":{"receipt_id":["old-r"],"session_id":["old-s"],"logical_request_id":["old-l"]}}}
    monkeypatch.setattr(runner,"parent_v8",lambda:V8())
    frozen={"v8_failure":{"root":"C:/evidence","failed_identities":{"session_id":"failed-s","logical_request_id":"failed-l","receipt_sha256":"f"*64,"serialization_proof_sha256":"p"*64}}}
    def failed(**identities):
        return {"status":"eligible_524","failed_identities":{"session_id":"new-s","logical_request_id":"new-l","receipt_sha256":"a"*64,"serialization_proof_sha256":"b"*64,**identities}}
    with pytest.raises(ValueError,match="v7 success"):
        runner._assert_identities(frozen,{"units":{"u":[failed(session_id="old-s")]}})
    with pytest.raises(ValueError,match="v7 success"):
        runner._assert_identities(frozen,{"units":{"u":[failed(logical_request_id="old-l")]}})
    with pytest.raises(ValueError,match="v8 failed"):
        runner._assert_identities(frozen,{"units":{"u":[failed(receipt_sha256="f"*64)]}})
    with pytest.raises(ValueError,match="reused internally"):
        runner._assert_identities(frozen,{"units":{"u":[failed()],"v":[failed()]}})

def test_real_predecessor_paths_exercise_both_accepted_and_524_verifiers():
    v7=Path(r"C:\Users\Haile\Documents\cwr-ox-alpha-v7-cap1-pilot-20260821-5870d76")
    if not V8.is_dir() or not v7.is_dir(): pytest.skip("sealed public Ox predecessor roots unavailable")
    unit=study.units(study.parent_v8().load_frozen(V8))[0]
    accepted=runner._accepted(v7/"runs"/"pilot"/"ox-alpha-v7-01",unit)
    failed=runner._eligible_524(V8/"runs"/"ox-alpha-v8-01",unit)
    assert accepted["accepted_identities"]["logical_request_id"] != failed["failed_identities"]["logical_request_id"]
    assert failed["quiescent_tree"]["files"] > 0


@pytest.mark.parametrize("tamper",[
    lambda boundary,http,manifest: boundary["model_policy"].__setitem__("requested_model","other"),
    lambda boundary,http,manifest: boundary["model_policy"].__setitem__("required_reasoning_effort","low"),
    lambda boundary,http,manifest: boundary.__setitem__("request_schema","codex-nous-tool-free-judge-request-v1"),
    lambda boundary,http,manifest: boundary["transport_policy"].__setitem__("max_physical_attempts_per_logical_request",2),
    lambda boundary,http,manifest: boundary.__setitem__("request_sha256","0"*64),
    lambda boundary,http,manifest: http.__setitem__("request_payload_sha256","0"*64),
    lambda boundary,http,manifest: manifest.__setitem__("requested_provider","other"),
    lambda boundary,http,manifest: manifest.__setitem__("bridge_sha256","0"*64),
], ids=["model","reasoning","schema-v2","cap1","request-sha","payload-sha","provider","runtime"])
def test_eligible_524_rejects_signed_boundary_or_runtime_tamper(tamper):
    if not V8.is_dir(): pytest.skip("sealed v8 root unavailable")
    v8=study.parent_v8(); unit=study.units(v8.load_frozen(V8))[0]
    run=V8/"runs"/"ox-alpha-v8-01"; evidence=run/"responses"/"batch-0001.attempt-0001.nous.evidence"
    proof=next(evidence.rglob("serialization-proof.json")); judge,_=v8.v7_verifier()._judge_leaf(evidence,proof)
    events=runner._events(judge/"events.jsonl"); boundary=copy.deepcopy(next(row["data"] for row in events if row["event_type"]=="judge_boundary"))
    http=copy.deepcopy(next(row["data"] for row in events if row["event_type"]=="http_attempt"))
    manifest=copy.deepcopy(study.read_json(judge/"manifest.json")); tamper(boundary,http,manifest)
    for row in events:
        if row["event_type"]=="judge_boundary": row["data"]=boundary
    bridge=runner._bridge(v8)
    with pytest.raises(ValueError):
        runner._assert_eligible_524_judge_contract(bridge,v8,judge,events,run/"responses"/"batch-0001.attempt-0001.nous.request.json",http,manifest)

def test_report_uses_executor_initial_state_and_rejects_tampered_empty_state(monkeypatch,tmp_path):
    units=[{"unit_id":f"c{cell}-b{batch:04d}","cell_id":f"c{cell}","item_id":f"item-{cell}"} for cell in range(1,4) for batch in range(1,46)]
    monkeypatch.setattr(reporter,"load_frozen",lambda _: {"units":units,"v8_failure":{"root":"C:/evidence","failed_identities":{"session_id":"failed-s","logical_request_id":"failed-l","receipt_sha256":"f"*64,"serialization_proof_sha256":"p"*64}}})
    monkeypatch.setattr(reporter,"_runner",lambda:runner)
    monkeypatch.setattr(runner,"parent_v8",lambda:type("V8",(),{"load_frozen":staticmethod(lambda _: {"v7_transport_success":{"global_ids":{"receipt_id":[],"session_id":[],"logical_request_id":[]}}})})())
    payload=reporter.report(tmp_path)
    assert payload["complete_cells"]==[]
    assert [(row["cell_id"],row["accepted_batches"],len(row["missing_or_quarantined_units"])) for row in payload["attrition"]]==[("c1",0,45),("c2",0,45),("c3",0,45)]
    assert payload["attempt_record_count"]==payload["verified_physical_http_count"]==0
    (tmp_path/"state.json").write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="state drifted"):
        reporter.report(tmp_path)

def test_schedule_freezes_start_cursor_and_visits_all_units_once():
    frozen={"units":[{"unit_id":f"u{number:03d}"} for number in range(135)]}
    scheduled=runner._schedule(frozen,38)
    assert scheduled[0]["unit_id"]=="u038"
    assert len(scheduled)==len({item["unit_id"] for item in scheduled})==135

def test_result_sidecar_categorically_blocks_524_retry(monkeypatch,tmp_path):
    responses=tmp_path/"responses"; responses.mkdir()
    (responses/"batch-0001.attempt-0001.nous.result.json").write_text("{}",encoding="utf-8")
    monkeypatch.setattr(runner,"_v7_shim",lambda _: (_ for _ in ()).throw(AssertionError("must not inspect a completed sidecar")))
    with pytest.raises(ValueError,match="eligible no-result"):
        runner._eligible_524(tmp_path,{"item_id":"x","question_ids":[]})

def test_pause_resume_uses_monotonic_epoch_ids_for_one_protocol_round(tmp_path):
    for epoch_id,start_cursor in ((1,0),(2,6)):
        study.immutable_json(tmp_path/"epoch-invocations"/f"{epoch_id:04d}.json",{"epoch_id":epoch_id,"round":1,"start_cursor":start_cursor})
    study.immutable_json(tmp_path/"pauses"/"0001-six-524.json",{"epoch_id":1,"round":1,"reason":"six_consecutive_eligible_524"})
    assert [row["epoch_id"] for row in runner._invocations(tmp_path)]==[1,2]
    assert not list((tmp_path/"pauses").glob("*-global-stop.json"))

def test_offline_orphan_adjudication_records_no_contact_without_provider(tmp_path):
    unit={"unit_id":"u","item_id":"item","question_ids":[]}
    runner._append_attempt(tmp_path,{"kind":"intent","unit_id":"u","attempt":1,"round":1,"cursor":0,"at":"2026-08-22T00:00:00+00:00","unit":unit})
    study.immutable_json(tmp_path/study.FROZEN_NAME,{})
    study.immutable_json(tmp_path/"execution-claim.json",{"format_version":1,"study_id":study.CONTRACT["study_id"],"kind":"exclusive_round_epoch","pid":999999,"frozen":study.fingerprint(tmp_path/study.FROZEN_NAME)})
    runner.adjudicate_orphan(tmp_path)
    state=runner._state(tmp_path)
    assert state["units"]["u"][0]["status"]=="abandoned_no_contact"
    assert not (tmp_path/"execution-claim.json").exists()
    assert (tmp_path/"recoveries"/"0001-orphan-adjudication.json").is_file()


def test_same_round_resume_uses_authoritative_pending_set_after_six_failures(monkeypatch,tmp_path):
    paths={"artifact":str(tmp_path/"artifact.md"),"prompt":str(tmp_path/"prompt.md"),"task_contract":str(tmp_path/"task-contract.json")}
    units=[{"unit_id":f"u{number:03d}","item_id":"item","question_ids":[],"paths":paths} for number in range(135)]
    frozen={"zero_cost_proof":{},"units":units}
    study.immutable_json(tmp_path/study.FROZEN_NAME,{})
    monkeypatch.setattr(runner,"load_frozen",lambda _:frozen)
    monkeypatch.setattr(runner,"runtime_bindings",lambda:{})
    monkeypatch.setattr(runner,"_assert_identities",lambda *_:None)
    monkeypatch.setattr(runner,"parent_v8",lambda:type("V8",(),{"assert_fresh_at":staticmethod(lambda *_:None)})())
    calls=[]
    def fake_judge(**kwargs):
        unit_id=kwargs["output_dir"].parent.name; calls.append(unit_id)
        if unit_id in {f"u{number:03d}" for number in range(6)}: raise RuntimeError("HTTP 524")
    def failed(_,unit):
        number=int(unit["unit_id"][1:])
        return {"status":"eligible_524","request":{"bytes":1,"sha256":"request"},"prompt":{"bytes":1,"sha256":"prompt"},"failed_identities":{"session_id":f"s{number}","logical_request_id":f"l{number}","receipt_sha256":f"{number:064x}","serialization_proof_sha256":f"{number+135:064x}"}}
    def accepted(_,unit):
        number=int(unit["unit_id"][1:])
        return {"status":"accepted","request":{"bytes":1,"sha256":"request"},"prompt":{"bytes":1,"sha256":"prompt"},"accepted_identities":{"receipt_id":f"r{number}","session_id":f"s{number}","logical_request_id":f"l{number}"}}
    monkeypatch.setattr(runner,"run_judge",fake_judge)
    monkeypatch.setattr(runner,"_eligible_524",failed)
    monkeypatch.setattr(runner,"_accepted",accepted)
    runner.execute_epoch(tmp_path)
    runner.execute_epoch(tmp_path)
    intents=[row for row in runner._attempt_events(tmp_path) if row["kind"]=="intent" and row["round"]==1]
    assert len(calls)==len(intents)==135
    assert [row["unit_id"] for row in intents[:6]]==[f"u{number:03d}" for number in range(6)]
    assert len({row["unit_id"] for row in intents})==135
    assert [row["unit_id"] for row in intents[6:]]==[f"u{number:03d}" for number in range(6,135)]


def test_report_counts_verified_retry_then_success_history(monkeypatch,tmp_path):
    units=[{"unit_id":f"c{cell}-b{batch:04d}","cell_id":f"c{cell}","item_id":f"item-{cell}"} for cell in range(1,4) for batch in range(1,46)]
    first=units[0]["unit_id"]
    history=[
        {"status":"eligible_524","attempt":1,"at":"2026-08-22T00:00:01+00:00","proof":"failed"},
        {"status":"accepted","attempt":2,"at":"2026-08-22T00:01:01+00:00","proof":"accepted"},
    ]
    class Executor:
        @staticmethod
        def _state(_): return {"units":{first:history},"eligible_524":1}
        @staticmethod
        def _assert_identities(*_): pass
        @staticmethod
        def _eligible_524(run,_):
            assert run.name=="attempt-01"; return {"status":"eligible_524","proof":"failed"}
        @staticmethod
        def _accepted(run,_):
            assert run.name=="attempt-02"; return {"status":"accepted","proof":"accepted"}
    monkeypatch.setattr(reporter,"load_frozen",lambda _:{"units":units})
    monkeypatch.setattr(reporter,"_runner",lambda:Executor)
    payload=reporter.report(tmp_path)
    assert payload["attempt_record_count"]==2
    assert payload["verified_physical_http_count"]==2
