#!/usr/bin/env python3
"""Analyze supplemental-provider v3 without altering the primary GPT study."""
from __future__ import annotations
import argparse, hashlib, json, statistics
from pathlib import Path
from typing import Any, Mapping
from jsonschema import Draft202012Validator
from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.longform_runner import _parse_model_json, _provider_response_schema
from hbqrs.paths import bundles_path, registry_path, schema_dir
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, NOUS_TRANSPORT_POLICY, VALIDATION_FEEDBACK_POLICY, _json_bytes, _load_checkpoints, _validate_provider_artifacts
from run_study import CONTRACT, HERE, JOURNAL_NAME, _binding, _journal, _prompt, _promotion_decision, _reference_runner, preflight, schedule_events, sha, source_path

def read(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"Expected object: {path}")
    return value
def checkpoints(path:Path)->list[Path]: return sorted((path/"responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
def _hash(value:str)->bool: return len(value)==64 and all(char in "0123456789abcdef" for char in value)
def receipt(run:Path,record:Mapping[str,Any],provider:Mapping[str,Any])->str:
    value=record.get("provider")
    if not isinstance(value,Mapping): raise ValueError("Accepted response lacks provider receipt")
    requested,reported=value.get("requested"),value.get("reported")
    if requested!={"model":provider["model"],"reasoning_effort":provider["reasoning"]} or not isinstance(reported,Mapping) or reported.get("provider")!=provider["provider"] or reported.get("model") not in provider["reported_models"] or value.get("reasoning_attested") is not False or not isinstance(value.get("reasoning_attestation"),str): raise ValueError("Provider receipt model/reasoning provenance drifted")
    try: _validate_provider_artifacts(run,record)
    except Exception as exc: raise ValueError("Provider artifacts are missing or not bound") from exc
    artifacts=value.get("provider_artifacts")
    if provider["provider"]=="grok":
        if not isinstance(value.get("cli_version"),str) or not _hash(str(value.get("session_id_sha256",""))) or not _hash(str(value.get("request_id_sha256",""))) or not isinstance(artifacts,Mapping) or set(artifacts)!={"grok_envelope"}: raise ValueError("Grok receipt shape/provenance drifted")
        return "grok:"+str(value["session_id_sha256"])
    required={"judge_request","judge_result","serialization_proof","evidence_tree"}
    if "session_id_sha256" in value or value.get("provider_canonical_model")!=provider["provider_canonical_model"] or value.get("tool_free") is not True or value.get("exact_gate_eligible") is not False or value.get("logical_provider_request_count")!=1 or value.get("physical_http_attempt_count") not in {1,2} or value.get("recovered_request_count") not in {0,1} or value.get("transport_policy")!=NOUS_TRANSPORT_POLICY or not _hash(str(value.get("evidence_sha256",""))) or not _hash(str(value.get("serialization_proof_sha256",""))) or not isinstance(artifacts,Mapping) or set(artifacts)!=required: raise ValueError("Nous stateless receipt/provenance drifted")
    return "nous:"+str(value["evidence_sha256"])+":"+str(value["serialization_proof_sha256"])
def _numeric(values:list[float])->dict[str,Any]: return {"values":values,"mean":statistics.fmean(values),"sample_standard_deviation":statistics.stdev(values) if len(values)>1 else 0.0,"range":max(values)-min(values)}
def _validate_journal(work:Path,provider_id:str)->None:
    path=work/"providers"/provider_id/JOURNAL_NAME; plans=schedule_events(provider_id); rows=_journal(path)
    if len(rows)!=len(plans)*2 or rows[:len(plans)]!=plans: raise ValueError("Study journal is incomplete or does not bind the frozen schedule")
    for expected,actual in zip(plans,rows[len(plans):]):
        binding=_binding(work,provider_id,expected["method_id"],expected["run_id"]); required={key:value for key,value in expected.items() if key!="event"}
        if actual.get("event")!="completed" or {key:actual.get(key) for key in required}!=required or not binding.is_file() or actual.get("run_binding_sha256")!=sha(binding): raise ValueError("Study completion journal does not bind its manifest")
def _hbq(work:Path,provider:Mapping[str,Any],run:int)->tuple[float,list[str],dict[str,Any]]:
    path=work/"providers"/provider["provider_id"]/"hbq"/f"run-{run:02d}"; manifest=read(path/"run.json"); config=manifest.get("configuration",{}); ids=config.get("question_ids",[]); sequence=hashlib.sha256(("\n".join(ids)+"\n").encode()).hexdigest() if isinstance(ids,list) and all(isinstance(x,str) for x in ids) else None
    required={"bundle_id":CONTRACT["hbq"]["bundle_id"],"provider":provider["provider"],"model":provider["model"],"reasoning":provider["reasoning"],"allow_unattested_reasoning":True,"strict_ai":True,"batch_size":32,"retry_policy":{"batch_attempts":3},"retry_semantics":CONTRACT["hbq"]["retry_semantics"],"evidence_normalization_policy":EVIDENCE_NORMALIZATION_POLICY,"validation_feedback_policy":VALIDATION_FEEDBACK_POLICY,"artifact_id":"the-part-that-arrives-first"}
    if manifest.get("format_version")!=CONTRACT["hbq"]["manifest_format_version"] or not isinstance(config,dict) or manifest.get("config_sha256")!=hashlib.sha256(_json_bytes(config)).hexdigest() or config.get("artifact",{}).get("sha256")!=CONTRACT["source"]["sha256"] or config.get("artifact",{}).get("bytes")!=CONTRACT["source"]["bytes"] or (len(ids),sequence)!=(178,CONTRACT["hbq"]["question_id_sequence_sha256"]) or any(config.get(key)!=value for key,value in required.items()): raise ValueError("HBQ run configuration drifted")
    rows,count,_=_load_checkpoints(path,artifact_text=source_path().read_text(encoding="utf-8"),context_texts=[],batch_attempts=3,normalization_policy=EVIDENCE_NORMALIZATION_POLICY); paths=checkpoints(path)
    verdicts=[json.loads(line) for line in (path/"verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if count!=6 or len(paths)!=6 or rows!=verdicts or [row.get("question_id") for row in rows]!=ids: raise ValueError("HBQ checkpoints are incomplete, unordered, or disagree with verdicts.jsonl")
    previous=None
    for batch,checkpoint in enumerate(paths,1):
        record=read(checkpoint); response=record.get("response_artifact"); raw=path/response["path"] if isinstance(response,dict) and isinstance(response.get("path"),str) else None; chunk=ids[(batch-1)*32:batch*32]
        if record.get("format_version")!=CONTRACT["hbq"]["checkpoint_format_version"] or record.get("batch")!=batch or record.get("question_ids")!=chunk or record.get("previous_checkpoint_sha256")!=previous or record.get("retry_policy")!={"batch_attempts":3} or not isinstance(record.get("accepted_attempt"),int) or not 1<=record["accepted_attempt"]<=3 or record.get("normalization_policy")!=EVIDENCE_NORMALIZATION_POLICY or record.get("validation_feedback_policy")!=VALIDATION_FEEDBACK_POLICY or raw is None or not raw.is_file() or response.get("bytes")!=raw.stat().st_size or response.get("sha256")!=sha(raw) or record.get("response_sha256")!=sha(raw): raise ValueError("HBQ checkpoint v4 response/retry provenance drifted")
        previous=sha(checkpoint)
    score=read(path/"score.json"); schema=read(schema_dir()/"hbq_score_report.schema.json")
    if list(Draft202012Validator(schema).iter_errors(score)): raise ValueError("HBQ score violates its frozen schema")
    recomputed=score_bundle(load_modules(registry_path()),resolve_bundle(load_bundles(bundles_path()),CONTRACT["hbq"]["bundle_id"]),rows,artifact_id="the-part-that-arrives-first")
    if {key:value for key,value in score.items() if key!="weight_profile"}!=recomputed: raise ValueError("HBQ score does not deterministically recompute from accepted verdicts")
    value=score.get("final_score",{}).get("observed")
    if not isinstance(value,(int,float)): raise ValueError("HBQ observed score is missing")
    rejected=list((path/"responses"/"rejected").glob("batch-[0-9][0-9][0-9][0-9]/attempt-[0-9][0-9][0-9][0-9].json")) if (path/"responses"/"rejected").is_dir() else []
    return float(value),[receipt(path,read(item),provider) for item in paths],{"verdicts_sha256":sha(path/"verdicts.jsonl"),"score_sha256":sha(path/"score.json"),"final_checkpoint_sha256":sha(paths[-1]),"accepted_checkpoint_count":len(paths),"rejected_attempt_count":len(rejected),"rejected_attempts_excluded_from_repeatability":True}
def _native_spec(method_id:str)->tuple[str,list[str],int]:
    return {"naplan":("criteria",["audience","text_structure","ideas","character_and_setting","vocabulary","cohesion","paragraphing","sentence_structure","punctuation","spelling"],47),"cambridge":("components",["content_and_structure","style_and_accuracy"],40),"oregon":("traits",["ideas_and_content","organization","voice","word_choice","sentence_fluency","conventions"],36)}[method_id]
def _native(work:Path,provider:Mapping[str,Any],method:Mapping[str,Any],run:int)->tuple[float,str,dict[str,Any]]:
    path=work/"providers"/provider["provider_id"]/method["method_id"]/f"run-{run:02d}"; manifest=read(path/"pass.json"); config=manifest.get("configuration",{}); source=source_path().read_text(encoding="utf-8"); schema=read(HERE/method["schema"]); prompt=_prompt((HERE/method["prompt"]).read_text(encoding="utf-8"),source)
    if manifest.get("format_version")!=1 or manifest.get("config_sha256")!=hashlib.sha256(_json_bytes(config)).hexdigest() or config.get("name")!=f"{provider['provider_id']}-{method['method_id']}-run-{run:02d}" or config.get("prompt_sha256")!=hashlib.sha256(prompt.encode()).hexdigest() or config.get("schema_sha256")!=hashlib.sha256(_json_bytes(schema)).hexdigest() or config.get("provider")!=provider["provider"] or config.get("model")!=provider["model"] or config.get("reasoning")!=provider["reasoning"] or config.get("allow_unattested_reasoning") is not True: raise ValueError("Native run configuration drifted")
    response,result=read(path/"response.json"),read(path/"result.json"); content=response.get("content")
    if not isinstance(content,str) or response.get("config_sha256")!=manifest["config_sha256"] or response.get("prompt_sha256")!=config["prompt_sha256"] or response.get("schema_sha256")!=config["schema_sha256"] or response.get("content_sha256")!=hashlib.sha256(content.encode()).hexdigest(): raise ValueError("Native response binding drifted")
    try: parsed=_parse_model_json(content)
    except Exception as exc: raise ValueError("Native response is not JSON") from exc
    provider_schema=schema if provider["provider"] in {"grok","nous"} else _provider_response_schema(schema)
    if list(Draft202012Validator(schema).iter_errors(parsed)) or parsed!=result or response.get("result_sha256")!=hashlib.sha256(_json_bytes(parsed)).hexdigest() or read(path/"response.schema.json")!=provider_schema: raise ValueError("Native result/schema binding drifted")
    collection,ids,maximum=_native_spec(method["method_id"]); items=result.get(collection); value=result.get("total_score")
    if not isinstance(items,list) or not isinstance(value,(int,float)) or len(items)!=len(ids): raise ValueError("Native total/components are missing")
    key={"criteria":"criterion_id","components":"component_id","traits":"trait_id"}[collection]; keyed={item.get(key):item for item in items if isinstance(item,dict)}
    if set(keyed)!=set(ids) or len(keyed)!=len(items) or any(not isinstance(item.get("score"),(int,float)) or not isinstance(item.get("exact_quote"),str) or item["exact_quote"] not in source for item in keyed.values()) or value!=sum(item["score"] for item in keyed.values()) or not 0<=value<=maximum: raise ValueError("Native totals, IDs, ranges, or exact-quote grounding drifted")
    try: _reference_runner()._validate_native_result(result,method["reference_arm"],source)
    except ValueError as exc: raise ValueError("Native strict semantic validation drifted") from exc
    attempts=path/"attempts"; rejected=sorted(attempts.glob("rejected-*.json")) if attempts.is_dir() else []; failed=sorted(attempts.glob("failed-*.json")) if attempts.is_dir() else []; all_records=sorted(attempts.glob("*.json")) if attempts.is_dir() else []; attempt_receipts=[]; attempt_records=[]
    if set(all_records)!=set(rejected+failed) or len(rejected)+len(failed)>CONTRACT["native_runtime"]["attempts_per_repetition"]-1 or _reference_runner()._native_next_attempt(path)-1>CONTRACT["native_runtime"]["attempts_per_repetition"]: raise ValueError("Native retry provenance is forged or exceeds the frozen policy")
    for attempt in rejected+failed:
        record=read(attempt)
        if "reason" in record:
            response_rejected,result_rejected,reason=record.get("response"),record.get("result"),record.get("reason")
            if not isinstance(response_rejected,dict) or not isinstance(result_rejected,dict) or not isinstance(reason,str): raise ValueError("Native semantic rejection is malformed")
            attempt_receipts.append(receipt(path,response_rejected,provider))
            if response_rejected.get("config_sha256")!=manifest["config_sha256"] or response_rejected.get("prompt_sha256")!=config["prompt_sha256"] or response_rejected.get("schema_sha256")!=config["schema_sha256"] or response_rejected.get("result_sha256")!=hashlib.sha256(_json_bytes(result_rejected)).hexdigest(): raise ValueError("Native semantic rejection is not bound to this run")
            try: _reference_runner()._validate_native_result(result_rejected,method["reference_arm"],source)
            except ValueError as exc:
                if str(exc)!=reason: raise ValueError("Native semantic rejection reason is not reproducible")
            else: raise ValueError("Native semantic rejection accepted a valid result")
            attempt_records.append({"path":attempt.relative_to(path).as_posix(),"bytes":attempt.stat().st_size,"sha256":sha(attempt),"classification":"semantic_rejection","reproduced_reason":reason})
        else:
            content=record.get("content")
            if record.get("format_version")!=1 or record.get("config_sha256")!=manifest["config_sha256"] or not isinstance(record.get("provider"),dict) or not isinstance(content,str): raise ValueError("Native transport attempt content is unbound")
            attempt_receipts.append(receipt(path,{"provider":record["provider"]},provider))
            try: parsed_failed=_parse_model_json(content)
            except Exception: parsed_failed=None
            if "retryable" in record:
                if not isinstance(record.get("retryable"),bool) or not isinstance(record.get("error"),dict): raise ValueError("Native transport attempt shape drifted")
            elif record.get("content_sha256")!=hashlib.sha256(content.encode()).hexdigest() or parsed_failed is not None and not list(Draft202012Validator(schema).iter_errors(parsed_failed)): raise ValueError("Native failed attempt is malformed")
            attempt_records.append({"path":attempt.relative_to(path).as_posix(),"bytes":attempt.stat().st_size,"sha256":sha(attempt),"classification":"transport_rejection" if "retryable" in record else "schema_failure"})
    accepted=receipt(path,response,provider)
    if accepted in attempt_receipts or len(attempt_receipts)!=len(set(attempt_receipts)): raise ValueError("Native accepted/rejected provider receipts are not disjoint")
    return float(value),accepted,{"result_sha256":sha(path/"result.json"),"response_sha256":sha(path/"response.json"),"component_scores":{name:keyed[name]["score"] for name in ids},"rejected_attempt_count":len(rejected),"failed_attempt_count":len(failed),"rejected_receipts":attempt_receipts,"rejected_attempt_artifacts":attempt_records,"rejected_receipt_commitment_sha256":hashlib.sha256(("\n".join(sorted(attempt_receipts))+"\n").encode()).hexdigest(),"rejected_attempts_excluded_from_repeatability":True}
def analyze(work:Path,output:Path)->None:
    preflight()
    if output.exists(): raise ValueError("Refusing to merge into an existing output directory")
    providers=[item for item in CONTRACT["providers"] if (work/"providers"/item["provider_id"]).is_dir()]; summary={"format_version":3,"study_id":CONTRACT["study_id"],"providers":{},"native_scale_rule":"Native results remain within their named scale; no cross-scale arithmetic."}; receipts=[]; rejected_receipts=[]; methods={item["method_id"]:item for item in CONTRACT["methods"]}
    required={"grok_4_6_high","nous_flash_max"}
    if not required.issubset({item["provider_id"] for item in providers}) or any(item.get("requires_promotion_decision") and not (work/CONTRACT["nous_promotion"]["decision_artifact_required"]).is_file() for item in providers): raise ValueError("Both mandatory baseline providers must be complete and promoted Pro requires a decision artifact")
    if any(item.get("requires_promotion_decision") for item in providers): _promotion_decision(work)
    for provider in providers:
        _validate_journal(work,provider["provider_id"]); values={key:[] for key in methods}; proofs={key:[] for key in methods}
        for run in range(1,6):
            value,observations,proof=_hbq(work,provider,run); values["hbq"].append(value); receipts.extend(observations); proofs["hbq"].append(proof)
            for key in ("naplan","cambridge","oregon"):
                value,observation,proof=_native(work,provider,methods[key],run); values[key].append(value); receipts.append(observation); rejected_receipts.extend(proof.pop("rejected_receipts")); proofs[key].append(proof)
        summary["providers"][provider["provider_id"]]={"provider":provider["provider"],"model":provider["model"],"reasoning":provider["reasoning"],"provisional_reasoning":True,"methods":{key:{"native_scale":methods[key]["native_scale"],"within_scale_repeatability":_numeric(values[key]),"run_commitments":proofs[key]} for key in methods}}
    expected_receipts=len(providers)*45
    if len(receipts)!=expected_receipts or len(set(receipts))!=expected_receipts or len(rejected_receipts)!=len(set(rejected_receipts)) or set(receipts)&set(rejected_receipts): raise ValueError("Supplemental study does not prove study-wide unique accepted/rejected provider receipts")
    if {"grok_4_6_high","nous_flash_max"}.issubset(summary["providers"]):
        grok,nous=[summary["providers"][key]["methods"]["hbq"]["within_scale_repeatability"]["values"] for key in ("grok_4_6_high","nous_flash_max")]
        summary["paired_hbq_descriptive_delta"]={"left":"grok_4_6_high","right":"nous_flash_max","values":[left-right for left,right in zip(grok,nous)],"not_a_cross_rubric_score":True}
    summary["receipt_count"]=expected_receipts; summary["receipt_commitment_sha256"]=hashlib.sha256(("\n".join(sorted(receipts))+"\n").encode()).hexdigest(); output.mkdir(parents=True)
    (output/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    if "paired_hbq_descriptive_delta" in summary:
        body="".join(f'<text x="30" y="{55+index*24}" font-size="17">run {index+1}: {value:.3f}</text>' for index,value in enumerate(summary["paired_hbq_descriptive_delta"]["values"])); (output/"paired-hbq-deltas.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="190"><text x="25" y="28" font-size="19">Paired HBQ observed-score delta: Grok − Nous Flash</text>{body}</svg>',encoding="utf-8")
    files={path.name:{"bytes":path.stat().st_size,"sha256":sha(path)} for path in output.iterdir() if path.is_file()}; (output/"manifest.json").write_text(json.dumps({"format_version":3,"protocol_contract_sha256":sha(HERE/"study-contract.json"),"files":files},indent=2)+"\n",encoding="utf-8")
def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--work-dir",required=True,type=Path); parser.add_argument("--output-dir",required=True,type=Path); args=parser.parse_args(); analyze(args.work_dir.resolve(),args.output_dir.resolve()); return 0
if __name__=="__main__": raise SystemExit(main())
