from __future__ import annotations
import csv, hashlib, importlib.util, json, math, shutil, sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]/"evaluation-results"/"hbq-human-alignment-v2"
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/file); assert spec and spec.loader; value=importlib.util.module_from_spec(spec); sys.modules[name]=value; spec.loader.exec_module(value); return value
study=module("hanna_study","study.py"); sys.modules["study"]=study; analysis=module("hanna_analysis","analyze_study.py"); sys.modules["analyze_study"]=analysis; run_study=module("hanna_run","run_study.py"); gate_module=module("hanna_gate","confirmation_gate.py")
def synthetic(path):
    fields=["Story ID","Prompt","Human","Story","Model",*study.RATING_DIMENSIONS,"Worker ID","Assignment ID"]; rows=[]
    for prompt_group in range(96):
        for model in range(11):
            story_id=prompt_group*100+model
            for rater in range(3): rows.append({"Story ID":str(story_id),"Prompt":f"prompt-{prompt_group}","Human":"same","Story":f"story-{prompt_group}-{model}","Model":f"M{model}",**{key:str(prompt_group%5+1) for key in study.RATING_DIMENSIONS},"Worker ID":str(rater),"Assignment ID":f"a-{prompt_group}-{model}-{rater}"})
    with path.open("w",encoding="utf-8",newline="") as handle: writer=csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
def synthetic_external_run(tmp_path, *, session_id="session-1"):
    from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle, score_bundle
    from hbqrs.paths import bundles_path, registry_path
    from hbqrs.runner import _json_bytes, _question_payload
    from hbqrs.weights import materialize_weight_profile
    item=study.HannaItem("hanna-x","999","Generated","prompt text","story text",{key:(3,3,3) for key in study.RATING_DIMENSIONS})
    inputs=tmp_path/"inputs"/"development"/item.item_id; inputs.mkdir(parents=True); (inputs/"source.md").write_text(item.story); (inputs/"prompt.md").write_text(item.prompt); study.write_json(inputs/"task-contract.json",study.make_task_contract(item))
    modules,bundle,_=materialize_weight_profile(load_modules(registry_path()),resolve_bundle(load_bundles(bundles_path()),"prose.short_story"),None); contract=json.loads((inputs/"task-contract.json").read_text()); compiled=compile_bundle(modules,bundle,task_contract=contract); records=sorted(compiled_questions(compiled),key=lambda value:{"hard_gate":0,"domain":1,"penalty":2,"supplemental":3}.get(value.get("role"),99)); ids=[row["question"]["id"] for row in records]
    verdicts=[{"artifact_id":item.item_id,"bundle_id":"prose.short_story","question_id":key,"verdict":"YES","confidence":1.0,"evidence":[{"reference":"r","exact_quote":"story text"}],"note":"" ,"judge_id":"codex:gpt-5.6-sol","run_id":"run-synthetic"} for key in ids]
    package={path.name:study.fingerprint(path) for path in study.package_paths()}; source=study.fingerprint(inputs/"source.md"); prompt=study.fingerprint(inputs/"prompt.md"); task=study.fingerprint(inputs/"task-contract.json")
    configuration={"artifact":{**source,"path":str(inputs/"source.md")},"contexts":[{**prompt,"path":str(inputs/"prompt.md")}],"task_contract":{**task,"path":str(inputs/"task-contract.json"),"contract_id":"hanna"},"weight_profile":_,"bundle_id":"prose.short_story","bundle_version":bundle["version"],"question_ids":ids,"provider":"codex","model":"gpt-5.6-sol","endpoint":None,"api_key_env":None,"temperature":None,"allow_model_mismatch":None,"reasoning":"high","codex_bin":"codex","batch_size":32,"artifact_id":item.item_id,"judge_id":"codex:gpt-5.6-sol","strict_ai":False,"prompts":[{**package["BINARY_EVALUATION_PROMPT.md"],"path":"binary"}],"response_schema":{**package["hbq_judge_response.schema.json"],"path":"schema"},"questions_sha256":hashlib.sha256(_json_bytes(_question_payload(records))).hexdigest(),"compiled_bundle_sha256":hashlib.sha256(_json_bytes(compiled)).hexdigest()}
    folder=tmp_path/"runs"/"development"/item.item_id/"run-01"; (folder/"responses").mkdir(parents=True); run_id="run-synthetic"; study.write_json(folder/"run.json",{"format_version":1,"run_id":run_id,"created_at":"x","config_sha256":hashlib.sha256(_json_bytes(configuration)).hexdigest(),"remote":True,"configuration":configuration}); (folder/"verdicts.jsonl").write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in verdicts)); previous=None; accumulated=[]
    for batch,offset in enumerate(range(0,len(verdicts),32),1):
        chunk=verdicts[offset:offset+32]; accumulated.extend(chunk); prompt_bytes=f"prompt-{batch}".encode(); message_bytes=f'{{"content":"batch-{batch}"}}'.encode(); response={"format_version":2,"batch":batch,"question_ids":[row["question_id"] for row in chunk],"prompt_sha256":hashlib.sha256(prompt_bytes).hexdigest(),"response_sha256":hashlib.sha256(message_bytes).hexdigest(),"previous_checkpoint_sha256":previous,"verdicts_sha256":hashlib.sha256(analysis.verdict_bytes(accumulated)).hexdigest(),"provider":{"reported":{"provider":"openai","model":"gpt-5.6-sol","reasoning_effort":"high","session_id":f"{session_id}-{batch}"}},"normalized_verdicts":chunk}; path=folder/"responses"/f"batch-{batch:04d}.json"; (folder/"responses"/f"batch-{batch:04d}.prompt.txt.gz").write_bytes(__import__("gzip").compress(prompt_bytes,mtime=0)); (folder/"responses"/f"batch-{batch:04d}.message.json").write_bytes(message_bytes); study.write_json(path,response); previous=hashlib.sha256(path.read_bytes()).hexdigest()
    score=score_bundle(modules,bundle,verdicts,artifact_id=item.item_id,task_contract=contract); score["weight_profile"]=_; study.write_json(folder/"score.json",score)
    row={"item_id":item.item_id,"model":"Generated","quartile":1,"prompt_group_id":"prompt-x","story_sha256":item.story_sha256,"prompt_sha256":item.prompt_sha256,"external_input":{"source.md":source,"prompt.md":prompt,"task-contract.json":task}}; frozen={"study_id":"fixture","provider":{"provider":"codex","model":"gpt-5.6-sol","reasoning":"high"},"runner":{"bundle_id":"prose.short_story","batch_size":32},"question_ids":ids,"package_files":package,"partitions":{"development":[row]},"repeatability":{"repetitions":5,"items":[{"item_id":item.item_id,"model":"Generated","partition":"development"}]}}
    return frozen,row,folder
def test_balanced_prompt_disjoint_stable_selection(tmp_path):
    synthetic(tmp_path/study.CSV_NAME); items=study.load_hanna_items(tmp_path); selected=study.select_partitions(items,seed=560820); assert selected==study.select_partitions(items,seed=560820); assert [len(selected[key]) for key in study.PARTITIONS]==[88,88]; assert {row["item_id"] for row in selected["development"]}.isdisjoint({row["item_id"] for row in selected["confirmatory"]}); assert {row["prompt_sha256"] for row in selected["development"]}.isdisjoint({row["prompt_sha256"] for row in selected["confirmatory"]}); assert all(sum(row["model"]==model and row["quartile"]==quartile for row in selected["development"])==2 for model in {row["model"] for row in selected["development"]} for quartile in range(1,5))
def test_rejects_bad_rater_count(tmp_path):
    synthetic(tmp_path/study.CSV_NAME); lines=(tmp_path/study.CSV_NAME).read_text().splitlines(); (tmp_path/study.CSV_NAME).write_text("\n".join(lines[:-1]));
    with pytest.raises(ValueError,match="exactly three"): study.load_hanna_items(tmp_path)
def test_mapping_present_and_contract_goal_is_dynamic():
    ids=study.compiled_question_ids(); study.assert_mapping_valid(ids); assert "task.contract.hanna.prompt_response" in ids and len(ids)==179
def test_fingerprint_drift_math_and_svg(tmp_path):
    path=tmp_path/"x"; path.write_text("before"); expected={"x":study.fingerprint(path)}; study.assert_frozen_package_files(expected,[path]); path.write_text("after")
    with pytest.raises(ValueError,match="drifted"): study.assert_frozen_package_files(expected,[path])
    first=study.bootstrap_correlation([1,2,3,4],[1,2,3,4],seed=7,draws=20); assert first==study.bootstrap_correlation([1,2,3,4],[1,2,3,4],seed=7,draws=20) and first["estimate"]==1
    dimensions={key:{"spearman":{"estimate":.2,"ci_95_low":.1,"ci_95_high":.3}} for key in study.RATING_DIMENSIONS}; assert analysis.correlation_svg(dimensions)==analysis.correlation_svg(dimensions)
def test_mapping_and_privacy_guard(tmp_path):
    metrics=analysis.derive_mapping([{"question_id":"a","verdict":"YES"},{"question_id":"b","verdict":"NO"},{"question_id":"c","verdict":"CANNOT_ASSESS"}],{"R":["a","b","c"]})["R"]; assert metrics["score"]==.5 and metrics["coverage"]==2/3 and metrics["unresolved"]==1
    path=tmp_path/"public.json"; path.write_text(json.dumps({"item_id":"hanna-1"})); analysis.assert_public_safe(tmp_path,forbidden=["secret prose"]); path.write_text("secret prose")
    with pytest.raises(ValueError,match="leaks"): analysis.assert_public_safe(tmp_path,forbidden=["secret prose"])
def test_typed_evidence_and_permutation_invariant_ordinal_context():
    metrics=analysis.typed_evidence_metrics([{"evidence":[{"reference":"r","exact_quote":"exact"},{"reference":"s","summary":"summary"},{"reference":"u","quote":"legacy"},{}]}],"exact","prompt")
    assert metrics["typed_schema_conformant"]==2 and metrics["exact_quote_grounded"]==1 and metrics["summary"]==1 and metrics["untyped"]==1 and metrics["empty"]==1
    items=[study.HannaItem("a","1","M","p","s",{key:(1,3,5) for key in study.RATING_DIMENSIONS}),study.HannaItem("b","2","M","p","s",{key:(2,2,4) for key in study.RATING_DIMENSIONS})]
    swapped=[study.HannaItem(item.item_id,item.story_id,item.model,item.prompt,item.story,{key:tuple(reversed(value)) for key,value in item.ratings.items()}) for item in items]
    assert analysis.ordinal_agreement(items)==analysis.ordinal_agreement(swapped)
def test_runner_has_explicit_phases_and_blinded_setting():
    text=(ROOT/"run_study.py").read_text(encoding="utf-8")
    assert 'PHASES = ("development", "repeatability", "confirmatory")' in text and "strict_ai=False" in text and '"all"' not in text
def test_checkpoint_glob_and_global_session_proof_are_exact():
    text=(ROOT/"analyze_study.py").read_text(encoding="utf-8")
    assert 'glob("batch-[0-9][0-9][0-9][0-9].json")' in text and "message.json" in text and "global_session_sets" in text and "run_ids" not in text
def test_pinned_provenance_and_no_new_human_judging_claims():
    contract=study.load_contract(); dataset=contract["dataset"]
    assert dataset["upstream_commit"]=="282f27536a5d05ad4ce14298abcd70c45668fed2" and dataset["upstream_commit"] in dataset["csv_url"] and contract["selection"]["prompt_groups"]==96
    readme=(ROOT/"README.md").read_text(encoding="utf-8").lower()
    assert "never recruits" in readme and "writingprompts" in readme and "mit attribution" in readme
    names={path.name for path in study.package_paths()}
    assert {"weights.py","paths.py","hbq_task_contract.schema.json","hbq_score_report.schema.json"} <= names
def test_actual_worker_assignment_values_are_privacy_audit_inputs(tmp_path):
    synthetic(tmp_path/study.CSV_NAME)
    forbidden=study.privacy_forbidden_strings(tmp_path)
    assert "a-0-10-0" in forbidden and "0" not in forbidden
def test_primary_slice_and_null_chart_contracts():
    text=(ROOT/"analyze_study.py").read_text(encoding="utf-8")
    assert 'source_model"] != "Human"' in text and 'len(generated) != 80' in text and "effective_draws" in text
    dimensions={key:{"spearman":{"estimate":None,"ci_95_low":None,"ci_95_high":None,"effective_draws":0}} for key in study.RATING_DIMENSIONS}
    assert "undefined" in analysis.correlation_svg(dimensions)
def test_confirmation_gate_binds_both_analysis_hashes():
    text=(ROOT/"confirmation_gate.py").read_text(encoding="utf-8")+(ROOT/"run_study.py").read_text(encoding="utf-8")
    analyzer=(ROOT/"analyze_study.py").read_text(encoding="utf-8")
    assert "development_analysis_manifest_sha256" in text and "development_analysis_summary_sha256" in text and 'get("reported",{}).get("session_id")' in analyzer
def test_executed_synthetic_run_verification_and_score_tamper_rejection(tmp_path):
    frozen,row,folder=synthetic_external_run(tmp_path)
    rows,score=analysis.verify_run(tmp_path,frozen,"development",row,1)
    assert len(rows)==179 and score["artifact_id"]==row["item_id"]
    message=folder/"responses"/"batch-0001.message.json"; message.write_text("tamper")
    with pytest.raises(ValueError,match="response/message"): analysis.verify_run(tmp_path,frozen,"development",row,1)
    score["status"]="TAMPERED"; study.write_json(folder/"score.json",score)
    message.write_bytes(b'{"content":"batch-1"}')
    with pytest.raises(ValueError,match="Deterministic score mismatch"): analysis.verify_run(tmp_path,frozen,"development",row,1)
def test_executed_confirmation_gate_hash_validation(tmp_path,monkeypatch):
    frozen,row,_=synthetic_external_run(tmp_path); frozen.update({"mapping_sets_sha256":"m","package_commit":"c"}); study.write_json(tmp_path/"frozen-run-contract.json",frozen); development=tmp_path/"analysis"; development.mkdir(); summary={"study_id":"fixture","phase":"development"}; study.write_json(development/"summary.json",summary); manifest={"format_version":2,"study_id":"fixture","phase":"development","package_commit":"c","mapping_sets_sha256":"m","question_ids_sha256":hashlib.sha256(study.canonical_json(frozen["question_ids"])).hexdigest(),"files":{"summary.json":{"sha256":study.sha256_path(development/"summary.json")}}}; study.write_json(development/"manifest.json",manifest)
    monkeypatch.setattr(gate_module,"validate_frozen_contract",lambda work:frozen); monkeypatch.setattr(gate_module,"verify_phase_runs",lambda work,contract,phase:None)
    gate_module.create_gate(tmp_path,development); run_study.gate(tmp_path,frozen)
    (development/"summary.json").write_text("tamper")
    with pytest.raises(ValueError,match="hashes"): run_study.gate(tmp_path,frozen)
def test_executed_repeat_session_rejection_and_eleven_item_aggregation(tmp_path,monkeypatch):
    frozen,row,folder=synthetic_external_run(tmp_path,session_id="same-session")
    for number in range(1,6):
        destination=tmp_path/"runs"/"repeatability"/row["item_id"]/f"run-{number:02d}"; shutil.copytree(folder,destination)
        manifest=json.loads((destination/"run.json").read_text()); manifest["run_id"]=f"distinct-run-{number}"; study.write_json(destination/"run.json",manifest)
    with pytest.raises(ValueError,match="globally disjoint"): analysis.verify_phase_runs(tmp_path,frozen,"repeatability")
    rows,score=analysis.verify_run(tmp_path,frozen,"development",row,1); repeated=[]
    for number in range(11):
        item_id=f"hanna-repeat-{number}"; item_dir=tmp_path/"inputs"/"development"/item_id; item_dir.mkdir(parents=True); (item_dir/"source.md").write_text("story text"); (item_dir/"prompt.md").write_text("prompt text"); repeated.append({"item_id":item_id,"model":f"M{number}","partition":"development"})
        frozen["partitions"]["development"].append({**row,"item_id":item_id,"model":f"M{number}"})
    frozen["repeatability"]={"repetitions":5,"items":repeated}
    def varied_verify(*args,**kwargs):
        selected=args[3]; repetition=args[4]; index=int(selected["item_id"].rsplit("-",1)[-1])+1
        varied=json.loads(json.dumps(score)); varied["final_score"]["observed"]=index*repetition
        return rows,varied
    monkeypatch.setattr(analysis,"verify_run",varied_verify)
    metrics=analysis.repeatability_metrics(tmp_path,frozen)
    assert metrics["item_count"]==11 and len(metrics["per_item"])==11
    assert metrics["within_item_score_standard_deviation"]["mean"]==pytest.approx(6*math.sqrt(2.5))
