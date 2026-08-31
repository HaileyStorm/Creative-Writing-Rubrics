from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1"
NORMALIZED = Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-normalized-d5e95ba-20260831a")
MATERIALIZATION = Path(r"C:\Users\Haile\Documents\cwr-hanna-v5-mixed-materialization-9bb20be-20260830a")
FROZEN = Path(r"C:\Users\Haile\Documents\cwr-hanna-successor-fresh88-freeze-v4\frozen-successor-contract.json")
CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
ACK = "a" * 64

def module():
    spec = importlib.util.spec_from_file_location("_nextwave_score_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec); sys.modules[spec.name] = value; spec.loader.exec_module(value)
    return value

def route(_root):
    return ({"name":"grok-build-grok-4.6","model":"grok-4.6","reported_model":"grok-4.6-build","adapter":"grok_exec","provider":"xai_grok_build","destination":"xai_grok_build_subscription","zero_charge":True,"armed":True,"health":"healthy","reasoning_effort":"high","grok_command":["fixture"],"allowed_payload_classes":["public_synthetic"],"timeout_seconds":1.0},{"fixture":"route"})

def runner(**kwargs):
    prompt, root, value = kwargs["prompt"], kwargs["output_dir"], kwargs["route"]; kwargs["before_contact"](); token = hashlib.sha256(prompt + str(root).encode()).hexdigest(); responses=root/"responses"; responses.mkdir(); (responses/"batch-0001.attempt-0001.prompt.txt").write_bytes(prompt)
    scores={key:3.0 for key in ("Relevance","Coherence","Empathy","Surprise","Engagement","Complexity")}; envelope={"requestId":"request-"+token,"sessionId":"session-"+token,"modelUsage":{"grok-4.6-build":{}},"stopReason":"end_turn","num_turns":1,"structuredOutput":{"scores":scores,"evidence":{key:"fixture" for key in scores},"coverage":{key:True for key in scores}}}; raw=json.dumps(envelope,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode(); (responses/"batch-0001.attempt-0001.grok.envelope.json").write_bytes(raw)
    identity={"provider":"xai","requested_model":"grok-4.6","reported_model":"grok-4.6-build","request_id":envelope["requestId"],"session_id":envelope["sessionId"],"native_endpoint_contact_cardinality":"unproven","tools_enabled":False}
    settings={"route_name":value["name"],"adapter":"grok_exec","requested_model":"grok-4.6","reported_model":"grok-4.6-build","requested_reasoning_effort":"high","tools_enabled":False,"web_search_enabled":False,"subagents_enabled":False,"tool_free_argv":["--max-turns","1","--no-leader","--no-subagents","--disable-web-search","--no-plan","--tools","","--permission-mode","dontAsk","--sandbox","read-only","--verbatim"],"system_prompt_override":"Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents.","sampler":{"batch_number":1,"attempt_number":1,"timeout_seconds":1.0,"nonvisual_max_turns":1},"runner_prompt_artifact_sha256":hashlib.sha256(prompt).hexdigest(),"reasoning_attested":False}
    return {"native_request_bytes":json.dumps({"prompt":prompt.decode()},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode(),"native_response_bytes":raw,"identity":identity,"effective_settings":settings}

def common(tmp_path): return {"output_root":tmp_path/"roots","normalized_root":NORMALIZED,"materialization_root":MATERIALIZATION,"frozen_successor_path":FROZEN,"hanna_csv_path":CSV,"queue_root":tmp_path/"queue","authorization_acknowledgement_sha256":ACK,"route_provider":route}

def test_exact_normalized_source_freezes_33_cells(tmp_path):
    value=module(); prepared=value.prepare_all(**common(tmp_path)); assert len(prepared["prepared_cells"])==33 and prepared["effective_candidates"]==11
    schedule=json.loads((tmp_path/"roots"/"schedule.json").read_bytes()); assert len(schedule["cells"])==33 and len({row["payload_sha256"] for row in schedule["cells"]})==33
    assert schedule["confirmation"]=={"status":"unopened","cells":0}
    assert {row["candidate_id"] for row in schedule["cells"]} >= {value.BASELINE}

def test_one_shot_frozen_request_and_no_resend(tmp_path):
    value=module(); args=common(tmp_path); prepared=value.prepare_all(**args); source, frozen_schedule=value.schedule(normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV); value.schedule=lambda **_kwargs:(source,frozen_schedule); cell=prepared["prepared_cells"][0]
    received=value.execute_one(**args,cell_id=cell,allow_remote=True,runner=runner); assert received["state"]=="provisional_scoring_received"
    root=tmp_path/"roots"/cell; assert (root/"prompt-request.bin").read_bytes()==(root/"responses"/"batch-0001.attempt-0001.prompt.txt").read_bytes()
    with pytest.raises(ValueError,match="no resend"): value.execute_one(**args,cell_id=cell,allow_remote=True,runner=runner)
    (root/"unexpected.bin").write_bytes(b"x")
    raw,prompt,schema=value.payload(next(row for row in frozen_schedule["cells"] if row["cell_id"]==cell)); stored=json.loads((root/"prepared.json").read_bytes())
    with pytest.raises(ValueError,match="inventory"): value.admit(root,next(row for row in frozen_schedule["cells"] if row["cell_id"]==cell),frozen_schedule,raw,prompt,schema,stored["route"],stored["route_evidence"],ACK,source)

def test_source_tamper_disjoint_and_no_optimizer_runtime(tmp_path):
    value=module()
    with pytest.raises(ValueError,match="disjoint"): value.prepare_all(output_root=NORMALIZED/"out",normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV,queue_root=tmp_path/"q",authorization_acknowledgement_sha256=ACK,route_provider=route)
    text=(PACKAGE/"executor.py").read_text().lower(); assert "import dspy" not in text and "import optuna" not in text

def test_full_fake_33_cell_collector_projection_and_tamper_reject(tmp_path):
    value=module(); args=common(tmp_path); prepared=value.prepare_all(**args); source,frozen_schedule=value.schedule(normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV); value.schedule=lambda **_kwargs:(source,frozen_schedule)
    for cell in prepared["prepared_cells"]:
        assert value.execute_one(**args,cell_id=cell,allow_remote=True,runner=runner)["state"]=="provisional_scoring_received"
    collector=tmp_path/"collector.json"
    finalized=value.finalize_collector(output_root=args["output_root"],collector_output=collector,normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV,authorization_acknowledgement_sha256=ACK)
    assert finalized["cells"]==33
    with pytest.raises(ValueError,match="acknowledgement"):
        value.finalize_collector(output_root=args["output_root"],collector_output=tmp_path/"bad-ack.json",normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV,authorization_acknowledgement_sha256="b"*64)
    projected=value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    assert len(projected["metrics"])==11 and projected["authority"]["confirmation"]=={"status":"unopened","cells":0}
    original=collector.read_bytes(); supplied=json.loads(original); supplied["cells"][0]["native_response_sha256"]="0"*64; collector.write_bytes(value.canonical(supplied))
    with pytest.raises(ValueError,match="payload/response/settings"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    supplied=json.loads(original); supplied["extra"]="forbidden"; collector.write_bytes(value.canonical(supplied))
    with pytest.raises(ValueError,match="collector drifted"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    supplied=json.loads(original); supplied["cells"][0]["effective_settings_sha256"]="0"*64; collector.write_bytes(value.canonical(supplied))
    with pytest.raises(ValueError,match="settings"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    supplied=json.loads(original); supplied["cells"][0]["effective_settings"]={"forged":True}; supplied["cells"][0]["effective_settings_sha256"]=value.sha256(supplied["cells"][0]["effective_settings"]); collector.write_bytes(value.canonical(supplied))
    with pytest.raises(ValueError,match="collector differs from persisted execution receipt"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    supplied=json.loads(original); supplied["format_version"]=True; collector.write_bytes(value.canonical(supplied))
    with pytest.raises(ValueError,match="collector drifted"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    supplied=json.loads(original); supplied["route"]["provider"]="forged"; supplied["route_evidence"]={"forged":True}; collector.write_bytes(value.canonical(supplied))
    with pytest.raises(ValueError,match="route/evidence"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    collector.write_bytes(original); first=prepared["prepared_cells"][0]; envelope=args["output_root"]/first/"responses"/"batch-0001.attempt-0001.grok.envelope.json"; envelope.write_bytes(b'{"tampered":true}')
    with pytest.raises(ValueError,match="envelope differs"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
    envelope.write_bytes(base64.b64decode(json.loads(original)["cells"][0]["native_response_base64"]))
    (args["output_root"] / "unexpected.bin").write_bytes(b"x")
    with pytest.raises(ValueError,match="proof-root inventory"):
        value.descriptive_project(collector_path=collector,output_root=args["output_root"],normalized_root=NORMALIZED,materialization_root=MATERIALIZATION,frozen_successor_path=FROZEN,hanna_csv_path=CSV)
