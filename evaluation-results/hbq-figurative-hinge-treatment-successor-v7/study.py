from __future__ import annotations
import hashlib, io, json, subprocess, sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from hbqrs import runner
from hbqrs.cli import main as cli

ROOT=Path(__file__).resolve().parent; STUDY_ID="hbq-figurative-hinge-treatment-successor-v7"; HEAD="6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"; TARGET="penalty.purple_prose.metaphor"; PRIVATE="figurative-hinge-treatment-v7-private"; LEDGER="expected-ledger.json"; REVIEW="independent-sol-review.v1.json"; QUOTE="Include at least one exact_quote copied verbatim from the supplied artifact. Summary-only evidence is invalid."
def load(p:Path)->dict[str,Any]: return json.loads(p.read_text(encoding="utf-8"))
def canon(v:Any)->bytes: return (json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False)+"\n").encode()
def sha(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()
def contract()->dict[str,Any]: return load(ROOT/"study-contract.json")
def corpus()->list[dict[str,str]]: return load(ROOT/"public-synthetic-corpus.json")["cases"]
def slots()->list[dict[str,str]]: return [{"slot_id":f"hingev7-{c['case_id']}-r{r}","case_id":c["case_id"],"repeat":str(r),"leaf_id":TARGET} for c in corpus() for r in(1,2)]
def root(p:Path)->Path: return p/PRIVATE
def write(p:Path,b:bytes)->None:
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists() and p.read_bytes()!=b: raise ValueError(f"frozen material drift: {p}")
 if not p.exists(): p.write_bytes(b)
def validate()->dict[str,Any]:
 c=contract(); rows=corpus()
 if c["study_id"]!=STUDY_ID or c["source_anchor"]["commit"]!=HEAD or c["target"]["leaf_id"]!=TARGET: raise ValueError("identity drift")
 if len(rows)!=3 or len({x["case_id"] for x in rows})!=3 or len(slots())!=6: raise ValueError("balanced geometry drift")
 t=c["treatment"]["exact_text"]
 if "compatible and jointly clarify" not in t or "Punctuation" not in t or "familiarity/defaultness" not in t or "density" not in t: raise ValueError("reviewer treatment drift")
 return {"study_id":STUDY_ID,"slots":6,"provider_calls":0,"promotion":"none"}
def head()->None:
 h=subprocess.run(["git","-C",str(ROOT.parents[1]),"rev-parse","HEAD"],capture_output=True,text=True,check=True).stdout.strip()
 if h!=HEAD: raise ValueError(f"exact source HEAD required: {HEAD}, found {h}")
def bundle()->list[dict[str,Any]]:
 leaf=next(json.loads(x) for x in (ROOT.parents[1]/"registry"/"question_index.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(x).get("id")==TARGET)
 return [{"standard":{"id":"HBQ-RS","version":"1.2.0"},"bundle_id":STUDY_ID,"version":1,"title":"Figurative hinge v7 singleton diagnostic","module_ids":[leaf["module_id"]],"task_contract_domain_id":"figurative-hinge-v7","domains":[{"domain_id":"figurative-hinge-v7","title":TARGET,"points":1.0,"components":[{"module_id":leaf["module_id"],"weight":1.0,"include_question_ids":[TARGET]}],"score_mode":"weighted_binary_mean"}],"penalty_modules":[],"hard_gate_policy":{"no_is_invalid":True,"cannot_assess_is_unresolved":True,"not_applicable_requires_condition_or_reason":True,"hard_gates_are_reported_separately":True},"coverage_policy":{"minimum_weighted_coverage":0.0,"below_threshold_status":"PROVISIONAL","score_interval_required_when_unassessed":True,"whole_work_claims_require_whole_work_evidence":True}}]
def task(s:dict[str,str])->dict[str,Any]: return {"contract_version":1,"contract_id":f"{STUDY_ID}-{s['slot_id']}","artifact_id":s["slot_id"],"context":{"artifact_kind":"prose.short_story","declared_scope":"complete supplied passage","completion_status":"complete","background":["Public synthetic figurative hinge v7 diagnostic."],"constraints":["Use only the supplied artifact.",QUOTE,contract()["treatment"]["exact_text"]],"audience":["development-only rubric validation"]},"preferences":[],"priorities":[],"weighted_goals":[],"binding_requirements":[]}
def override(s:dict[str,str],t:dict[str,Any])->dict[str,Any]: return {"format_version":1,"artifact_id":s["slot_id"],"bundle_id":STUDY_ID,"task_contract_sha256":hashlib.sha256(canon(t)).hexdigest(),"contract_id":t["contract_id"],"artifact_kind":t["context"]["artifact_kind"],"declared_scope":t["context"]["declared_scope"],"compatibility_mode":"reviewed_override","decision_id":"figurative-hinge-v7-scope","reviewer":"hbqrs-reviewed-v1","reason":"Reviewed compatibility for a public synthetic figurative hinge v7 diagnostic."}
def command(s:dict[str,str],p:Path,remote:bool=False)->list[str]:
 r=root(p); out=[sys.executable,"-m","hbqrs","--registry",str(r/"catalog"/"registry.json"),"--bundles",str(r/"catalog"/"bundles.json"),"judge",str(r/"inputs"/f"{s['slot_id']}.txt"),"--bundle",STUDY_ID,"--provider","codex","--model","gpt-5.6-sol","--reasoning","high","--strict-ai","--batch-size","1","--batch-attempts","1","--attempt-lifecycle-policy","terminal_sidecar_v1","--artifact-id",s["slot_id"],"--question-id",TARGET,"--task-contract",str(r/"contracts"/f"{s['slot_id']}.json"),"--scope-compatibility-override",str(r/"overrides"/f"{s['slot_id']}.json"),"--output-dir",str(r/"runs"/s["slot_id"])]
 return [*out,"--allow-remote"] if remote else out
def render(s:dict[str,str],p:Path)->list[str]:
 r=root(p); return [sys.executable,"-m","hbqrs","--registry",str(r/"catalog"/"registry.json"),"--bundles",str(r/"catalog"/"bundles.json"),"render-judge","--artifact",str(r/"inputs"/f"{s['slot_id']}.txt"),"--bundle",STUDY_ID,"--provider","codex","--model","gpt-5.6-sol","--strict-ai","--artifact-id",s["slot_id"],"--question-id",TARGET,"--task-contract",str(r/"contracts"/f"{s['slot_id']}.json"),"--scope-compatibility-override",str(r/"overrides"/f"{s['slot_id']}.json"),"--output",str(r/"prompts"/f"{s['slot_id']}.txt")]
def local(c:list[str],**_k:Any)->SimpleNamespace:
 o,e=io.StringIO(),io.StringIO()
 with redirect_stdout(o),redirect_stderr(e): rc=cli(c[3:])
 return SimpleNamespace(returncode=int(rc),stdout=o.getvalue(),stderr=e.getvalue())
def bindings(p:Path)->dict[str,Any]:
 r=root(p); files=sorted([*r.glob("catalog/*.json"),*r.glob("inputs/*.txt"),*r.glob("contracts/*.json"),*r.glob("overrides/*.json")]); prompts=sorted((r/"prompts").glob("*.txt")); ss=slots()
 return {"contract":sha(ROOT/"study-contract.json"),"study":sha(ROOT/"study.py"),"run":sha(ROOT/"run.py"),"corpus":sha(ROOT/"public-synthetic-corpus.json"),"ledger":sha(p/LEDGER),"schedule":hashlib.sha256(canon(ss)).hexdigest(),"materials":hashlib.sha256(canon({str(x.relative_to(r)):sha(x) for x in files})).hexdigest(),"prompts":hashlib.sha256(canon({str(x.relative_to(r)):sha(x) for x in prompts})).hexdigest(),"commands":hashlib.sha256(canon({s["slot_id"]:command(s,p,True) for s in ss})).hexdigest()}
def dry_run(p:Path,runner_call:Any=local)->dict[str,Any]:
 validate();head(); labels=load(p/LEDGER)["labels"]
 if set(labels)!={x["case_id"] for x in corpus()} or set(labels.values())!={"YES","NO"}: raise ValueError("private balanced ledger drift")
 r=root(p);ss=slots();write(r/"catalog"/"registry.json",(ROOT.parents[1]/"registry"/"all_modules.json").read_bytes());write(r/"catalog"/"bundles.json",canon(bundle())); by={x["case_id"]:x for x in corpus()}
 for s in ss:
  t=task(s);write(r/"inputs"/f"{s['slot_id']}.txt",by[s["case_id"]]["text"].encode());write(r/"contracts"/f"{s['slot_id']}.json",canon(t));write(r/"overrides"/f"{s['slot_id']}.json",canon(override(s,t))); q=r/"prompts"/f"{s['slot_id']}.txt";q.parent.mkdir(parents=True,exist_ok=True);z=runner_call(render(s,p),check=False,text=True,encoding="utf-8",capture_output=True)
  if getattr(z,"returncode",1): raise RuntimeError(f"provider-free render failed for {s['slot_id']}: {getattr(z,'stderr','')}")
  q.write_bytes(q.read_bytes().replace(b"\r\n",b"\n").replace(b"\r",b"\n"))
 m={"format_version":1,"study_id":STUDY_ID,"source_head":HEAD,"provider_calls":0,"slots":ss,"max_future_provider_calls":6,"bindings":bindings(p),"promotion":"none"};write(r/"dry-manifest.v1.json",canon(m));return {"provider_calls":0,"slots":6,"manifest_sha256":sha(r/"dry-manifest.v1.json")}
def verify_post_call(p:Path,s:dict[str,str])->dict[str,str]:
 run=root(p)/"runs"/s["slot_id"]; manifest=load(run/"run.json"); config=manifest.get("configuration",{})
 expected={"provider":"codex","model":"gpt-5.6-sol","reasoning":"high","strict_ai":True,"batch_size":1,"retry_policy":{"batch_attempts":1},"retry_semantics":"cumulative_batch_attempts_v1","attempt_lifecycle_policy":"terminal_sidecar_v1","artifact_id":s["slot_id"],"bundle_id":STUDY_ID,"question_ids":[TARGET]}
 if manifest.get("format_version")!=5 or any(config.get(k)!=v for k,v in expected.items()): raise ValueError("post-call run configuration drift")
 checkpoint=load(run/"responses"/"batch-0001.json")
 if checkpoint.get("normalization_audit")!=[] or checkpoint.get("accepted_attempt")!=1 or runner._rejected_records(run,1): raise ValueError("retry or normalization detected")
 reported=checkpoint.get("provider",{}).get("reported",{})
 if {k:reported.get(k) for k in ("provider","model","reasoning_effort")}!={"provider":"openai","model":"gpt-5.6-sol","reasoning_effort":"high"}: raise ValueError("post-call provider identity drift")
 artifact=(root(p)/"inputs"/f"{s['slot_id']}.txt").read_text(encoding="utf-8"); verdicts,n,_=runner._load_checkpoints(run,artifact_text=artifact,context_texts=[],batch_attempts=1,normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY)
 if n!=1 or len(verdicts)!=1 or verdicts[0].get("question_id")!=TARGET or verdicts[0].get("verdict") not in {"YES","NO"}: raise ValueError("strict singleton target verdict required")
 runner._validate_typed_checkpoint_evidence(verdicts[0].get("evidence"),question_id=TARGET);runner._validate_exact_quotes(verdicts[0].get("evidence"),artifact_text=artifact,context_texts=[],question_id=TARGET)
 return {"slot_id":s["slot_id"],"verdict":verdicts[0]["verdict"]}
def execute(p:Path,*,allow_remote:bool=False,acknowledged_zero_incremental_charge:bool=False,runner_call:Any=subprocess.run)->dict[str,Any]:
 head()
 if not allow_remote or not acknowledged_zero_incremental_charge: raise ValueError("dual acknowledgement required")
 m=load(root(p)/"dry-manifest.v1.json"); review=load(p/REVIEW); expected={"manifest":sha(root(p)/"dry-manifest.v1.json"),**m["bindings"]}
 if review.get("study_id")!=STUDY_ID or review.get("source_head")!=HEAD or review.get("decision")!="GO" or review.get("bindings")!=expected: raise ValueError("missing exact-binding Sol GO record")
 if bindings(p)!=m["bindings"]: raise ValueError("provider-visible material drifted")
 claim=root(p)/"execution-claim.v1.json"
 if claim.exists(): raise ValueError("one-shot execution forbids retry or resume")
 write(claim,canon({"study_id":STUDY_ID,"slots":6,"retry_or_resume":"forbidden"}));records=[]
 for s in slots():
  runner_call(command(s,p,True),check=True,text=True,encoding="utf-8",capture_output=True);records.append(verify_post_call(p,s))
 write(root(p)/"execution-result.v1.json",canon({"records":records,"promotion":"none"}));return {"executed_slots":8,"promotion":"none"}
