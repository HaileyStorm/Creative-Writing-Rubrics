#!/usr/bin/env python3
"""Round-robin cap-1 v9 executor; every attempt has an isolated run root."""
from __future__ import annotations
import argparse, gzip, hashlib, importlib.util, json, os, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from hbqrs import runner as hbq_runner
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, run_judge
from study import CONTRACT, FROZEN_NAME, fingerprint, immutable_json, load_frozen, read_json, runtime_bindings, parent_v8, sha, tree

UNIT_COUNT = CONTRACT["protocol"]["units"]
QUIESCENCE_SECONDS = 2.0


def _records(work: Path) -> list[dict[str, Any]]:
    root = work / "epochs"
    if not root.exists(): return []
    paths = sorted(root.glob("[0-9][0-9][0-9][0-9].json")); rows = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if [row.get("sequence") for row in rows] != list(range(1, len(rows) + 1)): raise ValueError("v9 epoch journal malformed")
    return rows


def _append(work: Path, row: Mapping[str, Any]) -> None:
    rows = _records(work); immutable_json(work / "epochs" / f"{len(rows)+1:04d}.json", {"sequence": len(rows)+1, **row})


def _invocations(work: Path) -> list[dict[str, Any]]:
    root=work/"epoch-invocations"
    if not root.exists(): return []
    paths=sorted(root.glob("[0-9][0-9][0-9][0-9].json")); rows=[read_json(path) for path in paths]
    if len(paths)!=len(list(root.iterdir())) or [row.get("epoch_id") for row in rows] != list(range(1,len(rows)+1)):
        raise ValueError("v9 epoch invocation authority is malformed")
    return rows


def _schedule(frozen: Mapping[str, Any], start_cursor: int) -> list[Mapping[str, Any]]:
    units=frozen.get("units")
    if not isinstance(units,list) or len(units)!=UNIT_COUNT or not isinstance(start_cursor,int) or isinstance(start_cursor,bool) or not 0 <= start_cursor < UNIT_COUNT:
        raise ValueError("v9 frozen schedule or cursor is malformed")
    scheduled=[units[(start_cursor+offset)%UNIT_COUNT] for offset in range(UNIT_COUNT)]
    ids=[unit.get("unit_id") for unit in scheduled if isinstance(unit,Mapping)]
    if len(ids)!=UNIT_COUNT or len(set(ids))!=UNIT_COUNT:
        raise ValueError("v9 schedule does not visit every unit exactly once")
    return scheduled


def _attempt_events(work: Path) -> list[dict[str, Any]]:
    root=work/"attempt-records"
    if not root.exists(): return []
    paths=sorted(root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")); rows=[json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if len(paths)!=len(list(root.iterdir())) or [row.get("sequence") for row in rows] != list(range(1,len(rows)+1)): raise ValueError("v9 attempt authority is malformed")
    return rows


def _round_attempted_units(work: Path, *, round_number: int, frozen: Mapping[str, Any]) -> set[str]:
    """Derive this round's consumed units solely from immutable intent records."""
    if not isinstance(round_number, int) or isinstance(round_number, bool) or round_number < 1:
        raise ValueError("v9 round number is malformed")
    known = {str(unit.get("unit_id")) for unit in frozen.get("units", []) if isinstance(unit, Mapping)}
    if len(known) != UNIT_COUNT:
        raise ValueError("v9 frozen units are malformed")
    attempted = {
        str(row["unit_id"])
        for row in _attempt_events(work)
        if row.get("kind") == "intent" and row.get("round") == round_number
    }
    if not attempted <= known:
        raise ValueError("v9 attempt authority references an unknown unit")
    return attempted


def _pending_round_schedule(work: Path, frozen: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[list[Mapping[str, Any]], set[str]]:
    round_number, cursor = state.get("round"), state.get("cursor")
    if not isinstance(round_number, int) or isinstance(round_number, bool) or not isinstance(cursor, int) or isinstance(cursor, bool):
        raise ValueError("v9 reconstructed round state is malformed")
    attempted = _round_attempted_units(work, round_number=round_number, frozen=frozen)
    return [unit for unit in _schedule(frozen, cursor) if str(unit["unit_id"]) not in attempted], attempted


def _round_start_expected_units(frozen: Mapping[str, Any], state: Mapping[str, Any], attempted_this_round: set[str]) -> set[str]:
    """Units that must be visited before this protocol round can close."""
    units = frozen.get("units")
    history = state.get("units")
    if not isinstance(units, list) or not isinstance(history, Mapping):
        raise ValueError("v9 round-start state is malformed")
    expected: set[str] = set()
    for unit in units:
        if not isinstance(unit, Mapping) or not isinstance(unit.get("unit_id"), str):
            raise ValueError("v9 frozen unit is malformed")
        unit_id = unit["unit_id"]
        prior = history.get(unit_id, [])
        if not isinstance(prior, list): raise ValueError("v9 unit history is malformed")
        terminal = any(isinstance(row, Mapping) and row.get("status") in ("accepted", "quarantined") for row in prior)
        if not terminal and len(prior) < CONTRACT["protocol"]["attempts_per_unit"]:
            expected.add(unit_id)
    if not attempted_this_round <= {str(unit["unit_id"]) for unit in units}:
        raise ValueError("v9 round has unknown attempted units")
    return expected


def _assert_round_closed(expected: set[str], already_visited: set[str], dispatched: set[str]) -> None:
    if already_visited & dispatched or already_visited | dispatched != expected:
        raise ValueError("v9 round did not visit every eligible unresolved unit exactly once")


def initial_state(*, completed_rounds: int = 0) -> dict[str, Any]:
    if not isinstance(completed_rounds, int) or isinstance(completed_rounds, bool) or completed_rounds < 0:
        raise ValueError("v9 completed-round count is malformed")
    return {"format_version":1,"study_id":CONTRACT["study_id"],"round":completed_rounds+1,"cursor":0,"eligible_524":0,"consecutive_524":0,"units":{}}


def _state_fingerprint(state: Mapping[str, Any]) -> dict[str, Any]:
    raw=(json.dumps(state,sort_keys=True,indent=2)+"\n").encode("utf-8")
    return {"name":"state.json","bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def _reconstruct_rows(rows: list[Mapping[str, Any]], *, completed_rounds: int) -> dict[str, Any]:
    state=initial_state(completed_rounds=completed_rounds)
    pending={}; seen_round_unit=set(); last_cursor=None
    for row in rows:
        key=(row.get("unit_id"),row.get("attempt"))
        if row.get("kind")=="intent":
            cursor=row.get("cursor")
            if key in pending or not isinstance(cursor,int) or isinstance(cursor,bool) or not 0 <= cursor < UNIT_COUNT:
                raise ValueError("duplicate or malformed v9 attempt intent")
            if not isinstance(row.get("round"),int) or not 1 <= row["round"] <= state["round"] or (row.get("round"), row.get("unit_id")) in seen_round_unit:
                raise ValueError("v9 round/cursor authority is malformed")
            seen_round_unit.add((row["round"], row["unit_id"]))
            pending[key]=row
        elif row.get("kind")=="result":
            if key not in pending: raise ValueError("v9 result lacks immutable intent")
            intent=pending.pop(key); result=row.get("result")
            if row.get("round") != intent.get("round") or row.get("cursor") != intent.get("cursor"):
                raise ValueError("v9 result does not bind its intent cursor")
            if not isinstance(result,Mapping): raise ValueError("v9 result is malformed")
            state["units"].setdefault(str(row["unit_id"]),[]).append(dict(result))
            if result.get("status")=="eligible_524": state["eligible_524"]+=1; state["consecutive_524"]+=1
            else: state["consecutive_524"]=0
            last_cursor=int(intent["cursor"])
        else: raise ValueError("unknown v9 attempt authority record")
    if pending: raise ValueError("v9 has interrupted attempt intent; no resume is safe")
    if last_cursor is not None and any(row.get("round")==state["round"] for row in rows): state["cursor"]=(last_cursor + 1) % UNIT_COUNT
    return state


def _reconstruct(work: Path) -> dict[str, Any]:
    rows=_attempt_events(work); completed=_records(work); prior_count=0
    for number, record in enumerate(completed,1):
        if set(record)!={"sequence","round","attempt_count","state"} or record.get("sequence")!=number or record.get("round")!=number or not isinstance(record.get("attempt_count"),int) or isinstance(record.get("attempt_count"),bool) or not prior_count <= record["attempt_count"] <= len(rows) or not isinstance(record.get("state"),Mapping):
            raise ValueError("v9 epoch journal is malformed")
        boundary=_reconstruct_rows(rows[:record["attempt_count"]],completed_rounds=number-1)
        if _state_fingerprint(boundary)!=record["state"]:
            raise ValueError("v9 completed epoch state does not bind its authoritative attempt prefix")
        prior_count=record["attempt_count"]
    return _reconstruct_rows(rows,completed_rounds=len(completed))


def _state(work: Path) -> dict[str, Any]:
    rebuilt=_reconstruct(work); path=work/"state.json"
    if not path.exists(): return rebuilt
    cached=json.loads(path.read_text(encoding="utf-8"))
    if cached != rebuilt: raise ValueError("v9 mutable state drifted from append-only authority")
    return rebuilt


def _write_state(work: Path, state: Mapping[str, Any]) -> None:
    expected=_reconstruct(work)
    if state != expected: raise ValueError("refusing to write state that cannot reconstruct from authority")
    path=work/"state.json"; path.parent.mkdir(parents=True,exist_ok=True); rendered=json.dumps(state,sort_keys=True,indent=2)+"\n"
    fd,temp=tempfile.mkstemp(prefix=".state.",suffix=".tmp",dir=work)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as out: out.write(rendered); out.flush(); os.fsync(out.fileno())
        for attempt in range(4):
            try: os.replace(temp,path); break
            except PermissionError:
                if attempt==3: raise
                time.sleep(0.05*(attempt+1))
    finally:
        Path(temp).unlink(missing_ok=True)


def _append_attempt(work: Path, row: Mapping[str, Any]) -> Path:
    rows=_attempt_events(work); immutable_json(work/"attempt-records"/f"{len(rows)+1:06d}.json",{"sequence":len(rows)+1,**row})
    return work / "attempt-records" / f"{len(rows)+1:06d}.json"


def _orphan_intents(work: Path) -> dict[tuple[Any, Any], dict[str, Any]]:
    pending: dict[tuple[Any, Any], dict[str, Any]] = {}
    for row in _attempt_events(work):
        key = (row.get("unit_id"), row.get("attempt"))
        if row.get("kind") == "intent":
            if key in pending: raise ValueError("v9 attempt authority has duplicate pending intent")
            pending[key] = row
        elif row.get("kind") == "result":
            if key not in pending: raise ValueError("v9 attempt authority has result without intent")
            pending.pop(key)
        else:
            raise ValueError("v9 attempt authority has unknown record")
    return pending


def _pid_live(pid: Any) -> bool:
    if not isinstance(pid,int) or isinstance(pid,bool) or pid <= 0: raise ValueError("v9 orphan claim PID is malformed")
    try: os.kill(pid,0)
    except ProcessLookupError: return False
    except OSError as exc:
        if getattr(exc,"winerror",None)==87: return False
        raise
    except PermissionError: return True
    return True


def _recovery_records(work: Path) -> list[dict[str, Any]]:
    root = work / "recoveries"
    if not root.exists(): return []
    paths = sorted(root.glob("[0-9][0-9][0-9][0-9]-orphan-adjudication.json"))
    rows = [read_json(path) for path in paths]
    if len(paths) != len(list(root.iterdir())) or [row.get("sequence") for row in rows] != list(range(1, len(rows) + 1)):
        raise ValueError("v9 recovery authority is malformed")
    return rows


def _claim_value(work: Path) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    path = work / "execution-claim.json"
    value = read_json(path)
    expected = {"format_version", "study_id", "kind", "pid", "frozen"}
    if set(value) != expected or value.get("format_version") != 1 or value.get("study_id") != CONTRACT["study_id"] or value.get("kind") != "exclusive_round_epoch" or not isinstance(value.get("pid"), int) or isinstance(value.get("pid"), bool) or value["pid"] <= 0 or value.get("frozen") != fingerprint(work / FROZEN_NAME):
        raise ValueError("v9 orphan execution claim is malformed or unbound")
    return path, value, fingerprint(path)


def _record_orphan_recovery(work: Path, *, claim_fingerprint: Mapping[str, Any], intent: Mapping[str, Any], result_record: Path) -> Path:
    rows = _recovery_records(work)
    path = work / "recoveries" / f"{len(rows)+1:04d}-orphan-adjudication.json"
    immutable_json(path, {
        "sequence": len(rows) + 1,
        "study_id": CONTRACT["study_id"],
        "kind": "offline_orphan_adjudication",
        "claim": dict(claim_fingerprint),
        "intent": {key: intent[key] for key in ("unit_id", "attempt", "round", "cursor")},
        "result_authority": fingerprint(result_record),
        "resolution": "claim_removed_after_validated_offline_adjudication",
    })
    return path


def adjudicate_orphan(work: Path) -> None:
    """Offline-only recovery of a crashed intent; never emits a provider request."""
    pending = _orphan_intents(work)
    if len(pending)!=1: raise ValueError("v9 has no single orphan intent to adjudicate")
    claim_path, claim, claim_fingerprint = _claim_value(work)
    if _pid_live(claim.get("pid")): raise ValueError("v9 orphan claimant is still live")
    intent=next(iter(pending.values())); unit=intent.get("unit")
    if not isinstance(unit,Mapping): raise ValueError("v9 orphan intent lacks frozen unit")
    attempt=work/"attempts"/str(intent["unit_id"])/f"attempt-{int(intent['attempt']):02d}"
    if not attempt.exists():
        result={"status":"abandoned_no_contact","reason":"dead_claimant_no_attempt_directory"}
    else:
        try: result=_eligible_524(attempt,unit)
        except Exception as exc: raise ValueError("v9 orphan has uncertain provider-contact evidence and remains fail-closed") from exc
    result.update({"attempt":intent["attempt"],"at":datetime.now(timezone.utc).isoformat()})
    result_record = _append_attempt(work,{"kind":"result","unit_id":intent["unit_id"],"attempt":intent["attempt"],"round":intent["round"],"cursor":intent["cursor"],"result":result})
    _write_state(work,_reconstruct(work))
    _record_orphan_recovery(work, claim_fingerprint=claim_fingerprint, intent=intent, result_record=result_record)
    if fingerprint(claim_path) != claim_fingerprint:
        raise ValueError("v9 orphan execution claim changed during recovery")
    claim_path.unlink()


def _claim(work: Path) -> None:
    path = work / "execution-claim.json"; value = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_round_epoch", "pid": os.getpid(), "frozen": fingerprint(work / FROZEN_NAME)}
    rendered = json.dumps(value, sort_keys=True, indent=2)+"\n"
    try: fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc: raise ValueError("v9 is claimed; resume only after a clean epoch boundary") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as out: out.write(rendered); out.flush(); os.fsync(out.fileno())


def _v7_shim(unit: Mapping[str, Any]) -> tuple[Any, Mapping[str, Any], dict[str, Any], dict[str, Any]]:
    """V9 is a retry wrapper; all accepted semantics remain v7's verifier."""
    v8 = parent_v8()
    v7v = v8.v7_verifier()
    frozen = {"judge_assets": v8.judge_assets()}
    cell = {"item_id": unit["item_id"], "question_ids": list(unit["question_ids"])}
    return v8, v7v, frozen, cell


def _bridge(v8: Any) -> Any:
    """Import only the canonical bridge bytecode already pinned by frozen v8 runtime."""
    bridge_path = hbq_runner.NOUS_LAUNCHER_PATH.parent / "nous_codex_bridge.py"
    if fingerprint(bridge_path) != v8.runtime_bindings()["bridge"]:
        raise ValueError("v9 canonical bridge drifted from the frozen v8 runtime")
    spec = importlib.util.spec_from_file_location("ox_alpha_v9_pinned_bridge", bridge_path)
    if spec is None or spec.loader is None: raise ValueError("v9 canonical bridge is unavailable")
    module = importlib.util.module_from_spec(spec)
    prior=sys.modules.get(spec.name); sys.modules[spec.name]=module
    try: spec.loader.exec_module(module)
    finally:
        if prior is None: sys.modules.pop(spec.name,None)
        else: sys.modules[spec.name]=prior
    return module


def _events(path: Path) -> list[dict[str, Any]]:
    try: return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise ValueError("v9 evidence events are unreadable") from exc


def _hash_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    result={key:value.get(key) for key in ("bytes","sha256")}
    if not isinstance(result["bytes"],int) or not isinstance(result["sha256"],str): raise ValueError("v9 artifact hash binding is malformed")
    return result


def _quiescent_tree(run: Path) -> dict[str, Any]:
    first=tree(run); time.sleep(QUIESCENCE_SECONDS); second=tree(run)
    if first != second: raise ValueError("v9 launcher-returned attempt is not quiescent")
    return first


def _assert_eligible_524_judge_contract(bridge: Any, v8: Any, judge: Path, judge_events: list[dict[str, Any]], request_path: Path, judge_http: Mapping[str, Any], manifest: Mapping[str, Any] | None = None) -> None:
    """Bind the signed Judge boundary and its one HTTP payload to v9's frozen route."""
    provider = CONTRACT["provider"]
    if provider != {"provider_id":"ox_alpha_max","provider":"nous","model":"stealth/ox-alpha","provider_canonical_model":"stealth/ox-alpha","reasoning":"max","allow_unattested_reasoning":True,"evidence_status":"provisional_only"}:
        raise ValueError("v9 Ox provider allowance drifted")
    boundaries = [row.get("data") for row in judge_events if row.get("event_type") == "judge_boundary"]
    if len(boundaries) != 1 or not isinstance(boundaries[0], Mapping):
        raise ValueError("eligible 524 lacks one signed Judge boundary")
    boundary = boundaries[0]
    request = read_json(request_path)
    try:
        messages, response_format, model, reasoning, cap = bridge.validate_judge_request(request)
    except Exception as exc:
        raise ValueError("eligible 524 stored request is not a valid Judge v2 request") from exc
    normalized = {"schema": CONTRACT["protocol"]["request_schema"], "messages": messages, "response_format": response_format, "model": model, "reasoning_effort": reasoning, "max_physical_http_attempts_per_logical_request": cap}
    payload = {"model": model, "reasoning_effort": reasoning, "messages": messages, "response_format": response_format}
    expected_model = bridge.judge_model_policy(provider["model"])
    expected_transport = bridge.judge_transport_policy(CONTRACT["protocol"]["cap"])
    expected_request_sha = bridge.sha256_bytes(bridge.canonical_bytes(normalized))
    expected_payload_sha = bridge.sha256_bytes(bridge.canonical_bytes(payload))
    if model != provider["model"] or reasoning != provider["reasoning"] or cap != CONTRACT["protocol"]["cap"]:
        raise ValueError("eligible 524 stored request drifts from the frozen Ox allowance")
    if boundary.get("request_schema") != CONTRACT["protocol"]["request_schema"] or boundary.get("model_policy") != expected_model or boundary.get("transport_policy") != expected_transport or boundary.get("request_sha256") != expected_request_sha or boundary.get("zero_tools") is not True:
        raise ValueError("eligible 524 signed Judge boundary drifts from the frozen route")
    if judge_http.get("request_payload_sha256") != expected_payload_sha:
        raise ValueError("eligible 524 signed HTTP payload does not match its stored Judge request")
    manifest = read_json(judge / "manifest.json") if manifest is None else manifest
    runtime_bridge = v8.runtime_bindings().get("bridge")
    if not isinstance(runtime_bridge, Mapping) or manifest.get("bridge_sha256") != runtime_bridge.get("sha256") or manifest.get("requested_provider") != provider["provider"] or manifest.get("requested_model") != provider["model"] or manifest.get("requested_reasoning_effort") != provider["reasoning"] or manifest.get("transport") != "nous-chat-completions-mcp":
        raise ValueError("eligible 524 Judge evidence drifts from the frozen runtime")


def _eligible_524(run: Path, unit: Mapping[str, Any]) -> dict[str, Any]:
    """A retry requires a sealed, pinned, no-result bridge failure and nothing else."""
    responses=run / "responses"; rejected=sorted((responses / "rejected").rglob("attempt-0001.json"))
    evidence_roots=sorted(path for path in responses.glob("*.nous.evidence") if path.is_dir())
    prompt_paths=sorted(responses.glob("batch-[0-9][0-9][0-9][0-9].prompt.txt.gz"))
    request_paths=sorted(responses.glob("*.nous.request.json"))
    result_paths=sorted(responses.glob("*.nous.result.json"))
    if len(rejected) != 1 or len(evidence_roots) != 1 or len(prompt_paths) != 1 or len(request_paths) != 1 or result_paths or list(responses.glob("batch-[0-9][0-9][0-9][0-9].json")) or any((run / name).exists() for name in ("verdicts.jsonl", "score.json", "score.v2.json")):
        raise ValueError("attempt is not an eligible no-result failure")
    record=read_json(rejected[0])
    if record.get("provider") is not None or record.get("validation_feedback") is not None or "HTTP 524" not in str(record.get("error", {}).get("message", "")):
        raise ValueError("attempt failure is not a raw 524")
    v8, v7v, _, _ = _v7_shim(unit)
    evidence=evidence_roots[0]
    proof_paths=sorted(evidence.rglob("serialization-proof.json"))
    if len(proof_paths) != 1: raise ValueError("eligible 524 lacks one serialization proof")
    try:
        judge, prove=v7v._judge_leaf(evidence, proof_paths[0])
    except Exception as exc: raise ValueError("eligible 524 lacks canonical Judge/ProveLock topology") from exc
    bridge=_bridge(v8)
    for leaf in (judge, prove):
        try: bridge.validate_evidence(leaf)
        except Exception as exc: raise ValueError("eligible 524 evidence chain or HMAC is invalid") from exc
    status=bridge.serialization_proof_status(evidence, str(proof_paths[0]), expected_sha256=sha(proof_paths[0]))
    if not getattr(status, "valid", False): raise ValueError("eligible 524 serialization proof is not canonical")
    judge_events, prove_events=_events(judge / "events.jsonl"), _events(prove / "events.jsonl")
    judge_http=[item.get("data") for item in judge_events if item.get("event_type")=="http_attempt"]
    prove_http=[item.get("data") for item in prove_events if item.get("event_type")=="http_attempt"]
    if len(judge_http)!=1 or not isinstance(judge_http[0],Mapping) or judge_http[0].get("status")!=524 or prove_http or any(item.get("event_type")=="message" and item.get("data",{}).get("direction")=="inbound" for item in judge_events):
        raise ValueError("attempt is not exactly one outbound-only Judge HTTP 524")
    _assert_eligible_524_judge_contract(bridge, v8, judge, judge_events, request_paths[0], judge_http[0])
    receipt=read_json(judge / "receipt.json")
    logical_id, session_id=judge_http[0].get("logical_request_id"), receipt.get("run_id")
    receipt_sha, proof_sha=receipt.get("receipt_sha256"),sha(proof_paths[0])
    if receipt.get("status")!="failure" or any(not isinstance(value,str) or len(value)!=64 for value in (receipt_sha,proof_sha)) or not isinstance(logical_id,str) or not logical_id or not isinstance(session_id,str) or not session_id:
        raise ValueError("attempt 524 failure receipt or identities are malformed")
    return {"status":"eligible_524", "rejected":fingerprint(rejected[0]), "request":_hash_binding(fingerprint(request_paths[0])), "prompt":_hash_binding(fingerprint(prompt_paths[0])), "failed_identities":{"logical_request_id":logical_id,"session_id":session_id,"receipt_sha256":receipt_sha,"serialization_proof_sha256":proof_sha}, "judge_receipt":fingerprint(judge / "receipt.json"), "prove_receipt":fingerprint(prove / "receipt.json"), "serialization_proof":fingerprint(proof_paths[0]), "quiescent_tree":_quiescent_tree(run)}


def _accepted(run: Path, unit: Mapping[str, Any]) -> dict[str, Any]:
    """Verify an accepted unit with v7's raw contract and runner schema replay."""
    v8, v7v, shim_frozen, shim_cell=_v7_shim(unit)
    artifact, prompt, _ = v8.input_paths(unit)
    responses=run / "responses"; checkpoints=v7v.checkpoint_paths(responses)
    if len(checkpoints)!=1 or list((responses / "rejected").rglob("*.json")) or not (run / "verdicts.jsonl").is_file():
        raise ValueError("accepted attempt lacks one clean completed batch")
    checkpoint=read_json(checkpoints[0]); prompt_path=checkpoints[0].with_suffix(".prompt.txt.gz")
    if checkpoint.get("format_version")!=4 or checkpoint.get("batch")!=1 or checkpoint.get("previous_checkpoint_sha256") is not None or checkpoint.get("question_ids")!=shim_cell["question_ids"] or checkpoint.get("retry_policy")!={"batch_attempts":1} or checkpoint.get("accepted_attempt")!=1 or checkpoint.get("recovered_from_rejected") is not None or checkpoint.get("rejected_chain")!={"count":0,"head_sha256":None}:
        raise ValueError("accepted checkpoint does not satisfy v9's cap-1 contract")
    prompt_bytes=gzip.decompress(prompt_path.read_bytes())
    expected=v7v._expected_prompt(shim_frozen, artifact.parent, shim_cell)
    if prompt_bytes != expected or checkpoint.get("base_prompt_sha256")!=hashlib.sha256(expected).hexdigest() or checkpoint.get("prompt_sha256")!=hashlib.sha256(expected).hexdigest():
        raise ValueError("accepted checkpoint prompt is unbound")
    raw=v7v._raw_transport(run, checkpoint, prompt_bytes, shim_frozen)
    try:
        replayed,count,previous=hbq_runner._load_checkpoints(run, artifact_text=artifact.read_bytes().decode("utf-8"), context_texts=[prompt.read_bytes().decode("utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc: raise ValueError("accepted checkpoint/schema replay failed") from exc
    stored=[json.loads(line) for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if count!=1 or previous!=sha(checkpoints[0]) or replayed!=stored or [row.get("question_id") for row in stored]!=shim_cell["question_ids"]:
        raise ValueError("accepted verdicts do not exactly reconstruct")
    return {"status":"accepted", "run":fingerprint(run / "run.json"), "checkpoint":fingerprint(checkpoints[0]), "verdicts":fingerprint(run / "verdicts.jsonl"), "request":_hash_binding(raw["payload"]["judge_request"]), "prompt":_hash_binding(fingerprint(prompt_path)), "accepted_identities":{key:raw[key] for key in ("receipt_id","session_id","logical_request_id")}}


def _cooldown_ready(prior: list[Mapping[str, Any]], now: datetime) -> bool:
    eligible = [row for row in prior if row.get("status") == "eligible_524"]
    if not eligible: return True
    last = datetime.fromisoformat(str(eligible[-1]["at"]))
    minutes = CONTRACT["pause"]["after_three_consecutive_minutes"] if len(eligible) >= 3 else CONTRACT["pause"]["same_unit_minutes"]
    return (now - last).total_seconds() >= minutes * 60


def _assert_identities(frozen: Mapping[str, Any], state: Mapping[str, Any]) -> None:
    """Accepted identities are globally unique; failed identities are typed but never scores."""
    accepted={"receipt_id":[],"session_id":[],"logical_request_id":[]}; failed={"session_id":[],"logical_request_id":[],"receipt_sha256":[],"serialization_proof_sha256":[]}
    for attempts in state["units"].values():
        for row in attempts:
            if row.get("status")=="accepted":
                identities=row.get("accepted_identities")
                if not isinstance(identities,Mapping): raise ValueError("accepted unit lacks typed provider identities")
                for key in accepted:
                    value=identities.get(key)
                    if not isinstance(value,str) or not value: raise ValueError("accepted unit identity is malformed")
                    accepted[key].append(value)
            elif row.get("status")=="eligible_524":
                identities=row.get("failed_identities")
                if not isinstance(identities,Mapping): raise ValueError("eligible 524 lacks typed failed identities")
                for key in failed:
                    value=identities.get(key)
                    if not isinstance(value,str) or not value: raise ValueError("failed unit identity is malformed")
                    failed[key].append(value)
    if any(len(values)!=len(set(values)) for values in (*accepted.values(),*failed.values())):
        raise ValueError("v9 provider identities are reused internally")
    predecessor=frozen["v8_failure"]["failed_identities"]
    if not isinstance(predecessor,Mapping): raise ValueError("v9 lacks typed v8 failure identities")
    v8=parent_v8(); inherited=v8.load_frozen(Path(str(frozen["v8_failure"]["root"])))["v7_transport_success"]["global_ids"]
    for key in ("session_id","logical_request_id"):
        if set(accepted[key]) & ({str(predecessor.get(key,""))} | set(inherited.get(key,[]))):
            raise ValueError("v9 accepted identity collides with v7 success or v8 failure lineage")
    if set(accepted["receipt_id"]) & set(inherited.get("receipt_id",[])):
        raise ValueError("v9 accepted receipt collides with v7 success lineage")
    for key in ("session_id","logical_request_id"):
        if set(failed[key]) & set(inherited.get(key,[])):
            raise ValueError("v9 failed identity collides with v7 success lineage")
    for key in failed:
        ancestor=predecessor.get(key)
        if isinstance(ancestor,str) and ancestor in failed[key]:
            raise ValueError("v9 failed identity collides with v8 failed lineage")
    if any(set(accepted[key]) & set(failed[key]) for key in ("session_id","logical_request_id")):
        raise ValueError("v9 accepted identity collides with a failed attempt")


def execute_epoch(work: Path, *, timeout: float = 600.0) -> None:
    frozen = load_frozen(work)
    now=datetime.now(timezone.utc).isoformat(); parent_v8().assert_fresh_at(frozen["zero_cost_proof"], now)
    state = _state(work); _assert_identities(frozen,state)
    pauses=work/"pauses"
    if pauses.is_dir() and list(pauses.glob("*-global-stop.json")): raise ValueError("v9 has an immutable global stop and is fail-closed")
    _write_state(work,state)
    epoch=state["round"]; epoch_id=len(_invocations(work))+1; start_cursor=state["cursor"]
    invocation = {"epoch_id":epoch_id,"frozen": fingerprint(work / FROZEN_NAME), "runtime": runtime_bindings(), "at": now, "round":epoch,"start_cursor":start_cursor}
    immutable_json(work / "epoch-invocations" / f"{epoch_id:04d}.json", invocation)
    _claim(work)
    try:
        deferred=False; dispatched_ids=set(); scheduled, attempted_this_round = _pending_round_schedule(work, frozen, state)
        expected_ids = _round_start_expected_units(frozen, state, attempted_this_round)
        already_visited = attempted_this_round & expected_ids
        unit_cursors = {str(unit["unit_id"]): cursor for cursor, unit in enumerate(frozen["units"])}
        for unit in scheduled:
            cursor=unit_cursors[str(unit["unit_id"])]
            prior = state["units"].get(unit["unit_id"], []); attempts = len(prior)
            if any(row["status"] in ("accepted", "quarantined") for row in prior) or attempts >= CONTRACT["protocol"]["attempts_per_unit"]: continue
            if not _cooldown_ready(prior, datetime.now(timezone.utc)): deferred=True; continue
            if state["eligible_524"] >= CONTRACT["protocol"]["maximum_eligible_524"]: deferred=True; break
            if sum(len(rows) for rows in state["units"].values()) >= CONTRACT["protocol"]["maximum_physical_requests"]: deferred=True; break
            attempt_dir = work / "attempts" / unit["unit_id"] / f"attempt-{attempts+1:02d}"
            _append_attempt(work,{"kind":"intent","unit_id":unit["unit_id"],"attempt":attempts+1,"round":epoch,"cursor":cursor,"at":datetime.now(timezone.utc).isoformat(),"unit":unit})
            dispatched_ids.add(str(unit["unit_id"]))
            try:
                run_judge(artifact_path=Path(unit["paths"]["artifact"]), context_paths=[Path(unit["paths"]["prompt"])], task_contract_path=Path(unit["paths"]["task_contract"]), bundle_id="prose.short_story", provider="nous", model="stealth/ox-alpha", reasoning="max", output_dir=attempt_dir, registry=registry_path(), bundles=bundles_path(), question_ids=unit["question_ids"], batch_size=len(unit["question_ids"]), batch_attempts=1, allow_remote=True, timeout=timeout, artifact_id=unit["item_id"], strict_ai=False, allow_unattested_reasoning=True, resume=False, max_physical_http_attempts_per_logical_request=1)
                row = _accepted(attempt_dir, unit); state["consecutive_524"] = 0
            except Exception as exc:
                if "402" in str(exc) or "charge" in str(exc).lower() or "payment" in str(exc).lower():
                    immutable_json(work/"pauses"/f"{epoch_id:04d}-global-stop.json",{"study_id":CONTRACT["study_id"],"epoch_id":epoch_id,"round":epoch,"reason":"charge_or_http_402","error":{"class":type(exc).__name__,"message":str(exc)[:1000]}})
                    raise ValueError("v9 global fail-stop: charge signal or HTTP 402") from exc
                try: row = _eligible_524(attempt_dir, unit); state["eligible_524"] += 1; state["consecutive_524"] += 1
                except Exception as verify: row = {"status": "quarantined", "error": {"class": type(exc).__name__, "message": str(exc)[:1000]}, "verification": {"class": type(verify).__name__, "message": str(verify)[:1000]}}; state["consecutive_524"] = 0
            anchor=next((item for item in prior if item.get("status") in ("eligible_524","accepted") and "request" in item),None)
            if anchor is not None and (row.get("request") != anchor.get("request") or row.get("prompt") != anchor.get("prompt")):
                row={"status":"quarantined","reason":"retry_request_or_prompt_hash_drift","observed":row,"anchor":anchor}; state["consecutive_524"]=0
            row.update({"attempt": attempts+1, "at": datetime.now(timezone.utc).isoformat()}); _append_attempt(work,{"kind":"result","unit_id":unit["unit_id"],"attempt":attempts+1,"round":epoch,"cursor":cursor,"result":row}); state=_reconstruct(work); _assert_identities(frozen,state); _write_state(work, state)
            if state["consecutive_524"] >= CONTRACT["pause"]["consecutive_eligible_524"]:
                immutable_json(work / "pauses" / f"{epoch_id:04d}-six-524.json", {"study_id": CONTRACT["study_id"], "epoch_id":epoch_id,"round":epoch,"reason": "six_consecutive_eligible_524", "state": fingerprint(work / "state.json")}); deferred=True; break
        if not deferred:
            _assert_round_closed(expected_ids, already_visited, dispatched_ids)
            _append(work, {"round": epoch, "attempt_count":len(_attempt_events(work)), "state":_state_fingerprint(state)}); state=_reconstruct(work); _write_state(work, state)
    finally:
        try:
            if not _orphan_intents(work): (work / "execution-claim.json").unlink(missing_ok=True)
        except ValueError:
            pass


if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--work-dir",required=True,type=Path); parser.add_argument("--timeout",type=float,default=600.0); parser.add_argument("--adjudicate-orphan",action="store_true"); args=parser.parse_args()
    if args.adjudicate_orphan: adjudicate_orphan(args.work_dir.resolve())
    else: execute_epoch(args.work_dir.resolve(),timeout=args.timeout)
