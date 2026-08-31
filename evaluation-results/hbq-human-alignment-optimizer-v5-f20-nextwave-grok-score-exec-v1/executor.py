#!/usr/bin/env python3
"""One-shot, development-only Grok scoring for the immutable normalized next-wave candidates."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-score-exec-v1"
NORMALIZER_COMMIT = "d5e95bab97b61eb9062241a409da03b68d2b0761"
NORMALIZER = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-normalize-v1" / "executor.py"
NORMALIZER_SHA256 = "a7e35f8cbdc879f0a95420a37882edee917d3e85b744c933f5f05ba770586071"
NORMALIZER_CONTRACT_SHA256 = "1635fcdebe715b3538f1c3d10c1dd9428bd2ca99db09a5d14e0f5b63a9e94766"
SOURCE_MANIFEST_SHA256 = "7eba326fca7f6621edbc9a809d9305b580f6487fc6ba4de4c9f3e9d9c88a5a36"
LIVE_EXEC = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1" / "executor.py"
LIVE_EXEC_SHA256 = "331c9749e29779de450f83871cf9b23001e1d705227f3b4d0b0de8a650292079"
BASELINE = "candidate-102cc7f06c9a99a7"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PREPARED = frozenset({"outbound-payload.json", "prompt-request.bin", "response-schema.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
TERMINAL = frozenset({"launch-intent.json", "native-request.bin", "native-response.bin", "runtime-identity.json", "effective-settings.json", "execution-receipt.json", "result.json"})
TOOL_FREE_ARGV = ["--max-turns", "1", "--no-leader", "--no-subagents", "--disable-web-search", "--no-plan", "--tools", "", "--permission-mode", "dontAsk", "--sandbox", "read-only", "--verbatim"]

def canonical(value: Any) -> bytes: return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
def sha256(value: bytes | Any) -> str: return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()
def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)): raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory: raise ValueError("unexpected path type")
def _safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists(): _plain(current, directory=True if current != absolute else None)
    return absolute
def _under(path: Path, parent: Path) -> bool: return path == parent or parent in path.parents
def _disjoint(*paths: Path) -> None:
    values = [_safe(path) for path in paths]
    if any(_under(a, b) or _under(b, a) for index, a in enumerate(values) for b in values[index + 1:]): raise ValueError("source, output, queue, and repository must be disjoint")
def stable(path: Path) -> bytes:
    path = _safe(path); _plain(path, directory=False); before = os.lstat(path)
    with path.open("rb") as handle: opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size): raise ValueError("stable read drift")
    return raw
def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    try: value = json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error: raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict): raise ValueError(f"{label} must be object")
    return value
def write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink(): raise ValueError("refuses overwrite")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())
def load(path: Path, digest: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest: raise ValueError("pinned dependency drifted")
    module = ModuleType(name); module.__file__ = str(path); sys.modules[name] = module
    try: exec(compile(raw, str(path), "exec"), module.__dict__)
    finally: sys.modules.pop(name, None)
    if stable(path) != raw: raise ValueError("dependency changed during load")
    return module
def normalizer() -> ModuleType:
    if sha256(stable(NORMALIZER.parent / "study-contract.json")) != NORMALIZER_CONTRACT_SHA256: raise ValueError("pinned normalizer contract drifted")
    return load(NORMALIZER, NORMALIZER_SHA256, "_nextwave_score_normalizer")
def live() -> ModuleType: return load(LIVE_EXEC, LIVE_EXEC_SHA256, "_nextwave_score_live")

def _normalized(root: Path) -> list[dict[str, Any]]:
    root = _safe(root); repo = _safe(HERE.parents[1]); _disjoint(root, repo)
    source = normalizer(); source.verify_all(source_root=Path(r"C:\Users\Haile\Documents\cwr-hanna-nextwave-grok-544af81-20260831a"), output_root=root)
    if sha256(stable(root / "source-manifest.json")) != SOURCE_MANIFEST_SHA256: raise ValueError("normalized source manifest drifted")
    names = {path.name for path in root.iterdir()}
    expected = {"source-manifest.json", *(f"nextwave-{ordinal:02d}-{slug}.json" for ordinal, slug in enumerate(("baseline-local-evidence", "best-small-step", "halo-suppression", "untouched-calibration", "polarity-order", "symmetric-evidence", "paraphrase-binding", "conservative-hybrid", "connective-hybrid", "calibrated-paraphrase"), 1))}
    if names != expected: raise ValueError("normalized source inventory drifted")
    records = [strict(stable(root / name), "normalized candidate") for name in sorted(expected - {"source-manifest.json"})]
    for record in records:
        if record.get("study_id") != source.STUDY_ID or record.get("kind") != "locally_normalized_provisional_grok_descendant" or record.get("authority", {}).get("selection") != "none": raise ValueError("normalized candidate authority drifted")
        normalized = record.get("normalized", {})
        if sha256(normalized.get("instruction", "").encode()) != normalized.get("instruction_sha256") or sha256(json.dumps(normalized.get("profile"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) != normalized.get("profile_sha256"): raise ValueError("normalized candidate binding drifted")
    return records

def schedule(*, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> tuple[ModuleType, dict[str, Any]]:
    source = live(); study, _token, prior = source._schedule(materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path)
    templates = [row for row in prior["cells"] if row["candidate_id"] == BASELINE]
    if len(templates) != 3 or len(prior.get("groups", [])) != 3: raise ValueError("f20 development geometry drifted")
    candidates = [{"candidate_id": BASELINE, "instruction": strict(study.payload_bytes(templates[0]), "baseline payload")["instruction"], "profile": strict(study.payload_bytes(templates[0]), "baseline payload")["profile"], "source_cell": "baseline"}]
    for record in _normalized(normalized_root): candidates.append({"candidate_id": "normalized-" + record["source_cell"]["cell_id"], "instruction": record["normalized"]["instruction"], "profile": record["normalized"]["profile"], "source_cell": record["source_cell"]["cell_id"], "source_record_sha256": sha256(canonical(record))})
    cells = []
    for candidate in candidates:
        for template in templates:
            payload = strict(study.payload_bytes(template), "baseline payload"); payload["instruction"] = candidate["instruction"]; payload["profile"] = candidate["profile"]
            raw = canonical(payload); cell_id = "nextwave-score-" + sha256(canonical({"candidate": candidate["candidate_id"], "group": template["prompt_group_id"]}))[:16]
            cells.append({"cell_id": cell_id, "candidate_id": candidate["candidate_id"], "source_cell": candidate["source_cell"], "item_id": template["item_id"], "prompt_group_id": template["prompt_group_id"], "partition": "development", "payload_sha256": sha256(raw), "candidate_instruction_sha256": sha256(candidate["instruction"].encode()), "candidate_profile_sha256": sha256(json.dumps(candidate["profile"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()), "payload_base64": base64.b64encode(raw).decode()})
    if len(cells) != 33 or len({row["cell_id"] for row in cells}) != 33 or len({row["payload_sha256"] for row in cells}) != 33: raise ValueError("next-wave scoring geometry drifted")
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "frozen_33_cell_grok_development_schedule", "normalized_source_manifest_sha256": SOURCE_MANIFEST_SHA256, "groups": prior["groups"], "cells": cells, "confirmation": {"status": "unopened", "cells": 0}, "authority": "development_only"}; value["schedule_sha256"] = sha256(value)
    return source, value

def payload(row: Mapping[str, Any]) -> tuple[bytes, bytes, bytes]:
    raw = base64.b64decode(row["payload_base64"], validate=True); value = strict(raw, "outbound payload"); schema = value.get("response_schema")
    if sha256(raw) != row["payload_sha256"] or not isinstance(schema, dict): raise ValueError("frozen payload drifted")
    return raw, raw, canonical(schema)
def route(queue_root: Path, provider=None): return live()._route(queue_root, provider)
def validate_frozen_route(route_value: Any, evidence: Any) -> None:
    required={"name":"grok-build-grok-4.6","model":"grok-4.6","reported_model":"grok-4.6-build","adapter":"grok_exec","provider":"xai_grok_build","destination":"xai_grok_build_subscription","zero_charge":True,"armed":True,"health":"healthy","reasoning_effort":"high"}
    if not isinstance(route_value,Mapping) or not isinstance(evidence,Mapping) or any(route_value.get(key)!=value for key,value in required.items()) or not isinstance(route_value.get("grok_command"),list) or len(route_value["grok_command"])!=1 or not isinstance(route_value.get("allowed_payload_classes"),list) or not ({"public_repo","public_synthetic"}&set(route_value["allowed_payload_classes"])): raise ValueError("persisted zero-charge route/evidence semantics drifted")
def artifacts(row, schedule_value, raw, prompt, schema, route_value, evidence, acknowledgement):
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement): raise ValueError("invalid acknowledgement")
    disclosure = {"format_version":1,"study_id":STUDY_ID,"kind":"local_first_exact_outbound_disclosure","cell_id":row["cell_id"],"route":route_value,"route_evidence":evidence,"payload":{"sha256":sha256(raw),"bytes":len(raw),"text":raw.decode()},"response_schema":{"sha256":sha256(schema),"bytes":len(schema),"text":schema.decode()},"tools_enabled":False,"web_search_enabled":False,"subagents_enabled":False,"tool_free_argv":TOOL_FREE_ARGV,"provider_calls_made":0,"process_launches":0}
    ack = {"format_version":1,"study_id":STUDY_ID,"kind":"authorization_acknowledgement_reference","cell_id":row["cell_id"],"acknowledgement_sha256":acknowledgement,"disclosure_sha256":sha256(disclosure)}
    proof = {"format_version":1,"study_id":STUDY_ID,"kind":"zero_charge_current_route_proof","cell_id":row["cell_id"],"route":route_value,"route_evidence":evidence,"zero_charge_only":True,"paid_fallback_forbidden":True,"provider_calls_made":0,"process_launches":0}
    prepared={"format_version":1,"study_id":STUDY_ID,"kind":"prepared_normalized_nextwave_grok_scoring_cell","cell":dict(row),"schedule_sha256":schedule_value["schedule_sha256"],"outbound_payload_sha256":sha256(raw),"prompt_request_sha256":sha256(prompt),"response_schema_sha256":sha256(schema),"route":route_value,"route_evidence":evidence,"disclosure_sha256":sha256(disclosure),"authorization_sha256":sha256(ack),"route_proof_sha256":sha256(proof),"tools_enabled":False,"provider_calls_made":0,"process_launches":0}
    return prepared,{"outbound-payload.json":raw,"prompt-request.bin":prompt,"response-schema.json":schema,"disclosure.json":canonical(disclosure),"authorization-acknowledgement.json":canonical(ack),"zero-charge-route-proof.json":canonical(proof),"prepared.json":canonical(prepared)}

def inventory(root: Path) -> set[str]:
    _plain(root, directory=True); names={path.name for path in root.iterdir()}
    for path in root.iterdir():
        if path.name == "responses":
            _plain(path,directory=True)
            if {item.name for item in path.iterdir()} != {"batch-0001.attempt-0001.grok.envelope.json","batch-0001.attempt-0001.prompt.txt"}: raise ValueError("response inventory drifted")
            for item in path.iterdir(): _plain(item,directory=False)
        else: _plain(path,directory=False)
    return names
def prepared_bytes(root,row,schedule_value,raw,prompt,schema,route_value,evidence,ack):
    prepared, files=artifacts(row,schedule_value,raw,prompt,schema,route_value,evidence,ack)
    if any(stable(root/name)!=value for name,value in files.items()): raise ValueError("prepared binding drifted")
    return prepared
def verify_prepared(root,row,schedule_value,raw,prompt,schema,route_value,evidence,ack):
    if inventory(root) != set(PREPARED): raise ValueError("prepared root not pristine")
    return prepared_bytes(root,row,schedule_value,raw,prompt,schema,route_value,evidence,ack)

def prepare_all(*, output_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider=None):
    root=_safe(output_root); _disjoint(root,_safe(normalized_root),_safe(queue_root),_safe(HERE.parents[1]),_safe(materialization_root),_safe(frozen_successor_path),_safe(hanna_csv_path))
    if root.exists(): raise ValueError("output root must be fresh")
    source,schedule_value=schedule(normalized_root=normalized_root,materialization_root=materialization_root,frozen_successor_path=frozen_successor_path,hanna_csv_path=hanna_csv_path); route_value,evidence=source._route(queue_root,route_provider)
    root.mkdir(parents=True); _plain(root,directory=True); write_new(root/"schedule.json",canonical(schedule_value))
    for row in schedule_value["cells"]:
        cell=root/row["cell_id"]; cell.mkdir(); raw,prompt,schema=payload(row); _prepared,files=artifacts(row,schedule_value,raw,prompt,schema,route_value,evidence,authorization_acknowledgement_sha256)
        for name,value in files.items(): write_new(cell/name,value)
        verify_prepared(cell,row,schedule_value,raw,prompt,schema,route_value,evidence,authorization_acknowledgement_sha256)
    return {"format_version":1,"study_id":STUDY_ID,"kind":"prepared_33_normalized_nextwave_grok_scoring_cells","prepared_cells":[x["cell_id"] for x in schedule_value["cells"]],"logical_cells":33,"effective_candidates":11,"provider_calls_made":0,"process_launches":0}

def execute_one(*, output_root: Path, cell_id: str, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider=None, runner=None):
    if allow_remote is not True: raise ValueError("explicit allow_remote required")
    source,schedule_value=schedule(normalized_root=normalized_root,materialization_root=materialization_root,frozen_successor_path=frozen_successor_path,hanna_csv_path=hanna_csv_path); row=next((x for x in schedule_value["cells"] if x["cell_id"]==cell_id),None)
    if row is None: raise ValueError("unknown cell")
    root=_safe(output_root)/cell_id
    if any((root/name).exists() for name in ("launch-intent.json","result.json")): raise ValueError("no resend; fresh root required")
    route_value,evidence=source._route(queue_root,route_provider); raw,prompt,schema=payload(row); prepared=verify_prepared(root,row,schedule_value,raw,prompt,schema,route_value,evidence,authorization_acknowledgement_sha256); intent={"format_version":1,"study_id":STUDY_ID,"kind":"intent_before_native_grok_contact","cell_id":cell_id,"prepared_sha256":sha256(prepared),"outbound_payload_sha256":sha256(raw),"native_contact_proven":False}; launched=False
    def before_contact():
        nonlocal launched
        if launched: raise ValueError("more than one contact")
        fresh_route,fresh_evidence=source._route(queue_root,route_provider)
        if fresh_route!=route_value or fresh_evidence!=evidence: raise ValueError("route drift")
        write_new(root/"launch-intent.json",canonical(intent)); launched=True
    try: value=(runner or source._default_runner)(prompt=prompt,schema_path=root/"response-schema.json",output_dir=root,route=route_value,before_contact=before_contact)
    except BaseException as error:
        result={"format_version":1,"study_id":STUDY_ID,"kind":"definitely_not_contacted" if not launched else "reconcile_required_after_process_launch","cell_id":cell_id,"detail":type(error).__name__,"provider_calls_made":0 if not launched else None,"process_launches":int(launched),"native_endpoint_contact_cardinality":"zero" if not launched else "unknown","intent_sha256":sha256(intent) if launched else None,"retry_policy":"fresh_output_root_required_no_in_place_resend"}; write_new(root/"result.json",canonical(result)); return result
    if not launched: raise ValueError("runner returned without contact")
    try:
        request,response,identity,settings=source._validate_runner_result(value,route_value,prompt)
        if request!=source.adapter_canonical({"prompt":prompt.decode()}): raise ValueError("request differs from frozen prompt")
        for name,value in (("native-request.bin",request),("native-response.bin",response),("runtime-identity.json",canonical(identity)),("effective-settings.json",canonical(settings))): write_new(root/name,value)
        prompt_artifact=root/"responses"/"batch-0001.attempt-0001.prompt.txt"
        if not prompt_artifact.exists() or stable(prompt_artifact)!=prompt: raise ValueError("runner prompt artifact drifted")
        receipt={"format_version":1,"study_id":STUDY_ID,"kind":"normalized_nextwave_grok_scoring_receipt_cardinality_unproven","cell":row,"prepared_sha256":sha256(prepared),"launch_intent_sha256":sha256(intent),"payload_sha256":sha256(raw),"native_request_sha256":sha256(request),"native_response_sha256":sha256(response),"runner_prompt_artifact_sha256":sha256(prompt),"effective_settings_sha256":sha256(settings),"identity":identity,"identity_sha256":sha256(identity),"provider_calls_made":None,"process_launches":1,"native_endpoint_contact_cardinality":"unproven"}
        result={"format_version":1,"study_id":STUDY_ID,"kind":"provisional_normalized_nextwave_grok_scoring_received","cell_id":cell_id,"receipt_sha256":sha256(receipt),"provider_calls_made":None,"process_launches":1,"native_endpoint_contact_cardinality":"unproven"}
        write_new(root/"execution-receipt.json",canonical(receipt)); write_new(root/"result.json",canonical(result)); return {"cell_id":cell_id,"state":"provisional_scoring_received","provider_calls_made":None,"process_launches":1,"native_endpoint_contact_cardinality":"unproven"}
    except BaseException as error:
        result={"format_version":1,"study_id":STUDY_ID,"kind":"reconcile_required_after_process_launch","cell_id":cell_id,"detail":type(error).__name__,"provider_calls_made":None,"process_launches":1,"native_endpoint_contact_cardinality":"unknown","intent_sha256":sha256(intent),"retry_policy":"fresh_output_root_required_no_in_place_resend"}; write_new(root/"result.json",canonical(result)); return result

def admit(root, row, schedule_value, raw, prompt, schema, route_value, evidence, acknowledgement, source):
    if inventory(root) != set(PREPARED | TERMINAL | {"responses"}): raise ValueError("completed root inventory drifted")
    prepared = prepared_bytes(root,row,schedule_value,raw,prompt,schema,route_value,evidence,acknowledgement)
    intent = {"format_version":1,"study_id":STUDY_ID,"kind":"intent_before_native_grok_contact","cell_id":row["cell_id"],"prepared_sha256":sha256(prepared),"outbound_payload_sha256":sha256(raw),"native_contact_proven":False}
    if stable(root/"launch-intent.json") != canonical(intent): raise ValueError("launch intent drifted")
    request,response,identity,settings=source._validate_runner_result({"native_request_bytes":stable(root/"native-request.bin"),"native_response_bytes":stable(root/"native-response.bin"),"identity":strict(stable(root/"runtime-identity.json"),"identity"),"effective_settings":strict(stable(root/"effective-settings.json"),"settings")},route_value,prompt)
    if request != source.adapter_canonical({"prompt":prompt.decode()}) or stable(root/"responses"/"batch-0001.attempt-0001.prompt.txt") != prompt: raise ValueError("request/prompt binding drifted")
    if stable(root/"responses"/"batch-0001.attempt-0001.grok.envelope.json") != response: raise ValueError("persisted envelope differs from native response")
    receipt={"format_version":1,"study_id":STUDY_ID,"kind":"normalized_nextwave_grok_scoring_receipt_cardinality_unproven","cell":row,"prepared_sha256":sha256(prepared),"launch_intent_sha256":sha256(intent),"payload_sha256":sha256(raw),"native_request_sha256":sha256(request),"native_response_sha256":sha256(response),"runner_prompt_artifact_sha256":sha256(prompt),"effective_settings_sha256":sha256(settings),"identity":identity,"identity_sha256":sha256(identity),"provider_calls_made":None,"process_launches":1,"native_endpoint_contact_cardinality":"unproven"}
    result={"format_version":1,"study_id":STUDY_ID,"kind":"provisional_normalized_nextwave_grok_scoring_received","cell_id":row["cell_id"],"receipt_sha256":sha256(receipt),"provider_calls_made":None,"process_launches":1,"native_endpoint_contact_cardinality":"unproven"}
    if stable(root/"execution-receipt.json") != canonical(receipt) or stable(root/"result.json") != canonical(result): raise ValueError("receipt/result binding drifted")
    return request, response, identity, settings

def finalize_collector(*, output_root: Path, collector_output: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, authorization_acknowledgement_sha256: str):
    collector=_safe(collector_output); _disjoint(collector,_safe(output_root),_safe(normalized_root),_safe(HERE.parents[1]),_safe(materialization_root),_safe(frozen_successor_path),_safe(hanna_csv_path))
    if collector.exists(): raise ValueError("collector output must be fresh")
    source,schedule_value=schedule(normalized_root=normalized_root,materialization_root=materialization_root,frozen_successor_path=frozen_successor_path,hanna_csv_path=hanna_csv_path)
    if {path.name for path in Path(output_root).iterdir()} != {"schedule.json",*(row["cell_id"] for row in schedule_value["cells"])} or stable(Path(output_root)/"schedule.json") != canonical(schedule_value): raise ValueError("output schedule inventory drifted")
    cells=[]; frozen_route=None; frozen_evidence=None
    for row in schedule_value["cells"]:
        root=Path(output_root)/row["cell_id"]; stored=strict(stable(root/"prepared.json"),"prepared"); ack=strict(stable(root/"authorization-acknowledgement.json"),"acknowledgement").get("acknowledgement_sha256")
        if ack != authorization_acknowledgement_sha256 or not isinstance(stored.get("route"),Mapping) or not isinstance(stored.get("route_evidence"),Mapping): raise ValueError("collector acknowledgement or route binding drifted")
        if frozen_route is None: frozen_route, frozen_evidence = stored["route"], stored["route_evidence"]
        if stored["route"] != frozen_route or stored["route_evidence"] != frozen_evidence: raise ValueError("collector route/evidence differs across cells")
        raw,prompt,schema=payload(row); request,response,identity,settings=admit(root,row,schedule_value,raw,prompt,schema,stored["route"],stored["route_evidence"],ack,source)
        cells.append({"cell_id":row["cell_id"],"payload_base64":row["payload_base64"],"payload_sha256":row["payload_sha256"],"native_request_base64":base64.b64encode(request).decode(),"native_request_sha256":sha256(request),"native_response_base64":base64.b64encode(response).decode(),"native_response_sha256":sha256(response),"identity":identity,"effective_settings":settings,"effective_settings_sha256":sha256(settings)})
    validate_frozen_route(frozen_route,frozen_evidence)
    value={"format_version":1,"study_id":STUDY_ID,"kind":"complete_33_normalized_nextwave_grok_receipts_cardinality_unproven","schedule_sha256":schedule_value["schedule_sha256"],"authorization_acknowledgement_sha256":authorization_acknowledgement_sha256,"route":frozen_route,"route_evidence":frozen_evidence,"cells":cells,"native_endpoint_contact_cardinality":"unproven","provider_calls_made":0,"process_launches":0}; write_new(collector,canonical(value)); return {"format_version":1,"study_id":STUDY_ID,"kind":value["kind"],"collector_sha256":sha256(value),"cells":33,"provider_calls_made":0,"process_launches":0}

def descriptive_project(*, collector_path: Path, output_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path):
    collector,output=_safe(collector_path),_safe(output_root); _disjoint(collector,output,_safe(normalized_root),_safe(HERE.parents[1]),_safe(materialization_root),_safe(frozen_successor_path),_safe(hanna_csv_path)); source,schedule_value=schedule(normalized_root=normalized_root,materialization_root=materialization_root,frozen_successor_path=frozen_successor_path,hanna_csv_path=hanna_csv_path); raw=stable(collector); value=strict(raw,"collector")
    expected_collector={"format_version","study_id","kind","schedule_sha256","authorization_acknowledgement_sha256","route","route_evidence","cells","native_endpoint_contact_cardinality","provider_calls_made","process_launches"}
    if canonical(value)!=raw or set(value)!=expected_collector or type(value.get("format_version")) is not int or value.get("format_version")!=1 or value.get("study_id")!=STUDY_ID or value.get("kind")!="complete_33_normalized_nextwave_grok_receipts_cardinality_unproven" or value.get("schedule_sha256")!=schedule_value["schedule_sha256"] or not isinstance(value.get("authorization_acknowledgement_sha256"),str) or not re.fullmatch(r"[0-9a-f]{64}",value["authorization_acknowledgement_sha256"]) or value.get("native_endpoint_contact_cardinality")!="unproven" or type(value.get("provider_calls_made")) is not int or value.get("provider_calls_made")!=0 or type(value.get("process_launches")) is not int or value.get("process_launches")!=0 or not isinstance(value.get("cells"),list) or len(value["cells"])!=33: raise ValueError("collector drifted")
    validate_frozen_route(value.get("route"),value.get("route_evidence"))
    index={row["cell_id"]:row for row in schedule_value["cells"]}
    if {path.name for path in output.iterdir()} != {"schedule.json",*index} or stable(output/"schedule.json") != canonical(schedule_value): raise ValueError("proof-root inventory or persisted schedule drifted")
    seen=set(); analyzer=source._analyze(); token=analyzer._study().prepare_grok_schedule(materialization_root=materialization_root,frozen_successor_path=frozen_successor_path,hanna_csv_path=hanna_csv_path); targets=analyzer._targets(token); observed=[]
    for supplied in value["cells"]:
        expected_cell={"cell_id","payload_base64","payload_sha256","native_request_base64","native_request_sha256","native_response_base64","native_response_sha256","identity","effective_settings","effective_settings_sha256"}
        if not isinstance(supplied,Mapping) or set(supplied)!=expected_cell: raise ValueError("collector cell fields drifted")
        row=index.get(supplied.get("cell_id")); request=base64.b64decode(supplied.get("native_request_base64",""),validate=True); response=base64.b64decode(supplied.get("native_response_base64",""),validate=True)
        if row is None or supplied.get("payload_base64")!=row["payload_base64"] or supplied.get("payload_sha256")!=row["payload_sha256"] or supplied.get("native_request_sha256")!=sha256(request) or supplied.get("native_response_sha256")!=sha256(response) or supplied.get("effective_settings_sha256")!=sha256(supplied.get("effective_settings")): raise ValueError("collector payload/response/settings drifted")
        identity=supplied.get("identity",{}); contact=(identity.get("request_id"),identity.get("session_id"))
        if not isinstance(identity,Mapping) or set(identity)!={"provider","requested_model","reported_model","request_id","session_id","native_endpoint_contact_cardinality","tools_enabled"} or identity.get("provider")!="xai" or identity.get("requested_model")!="grok-4.6" or identity.get("reported_model")!="grok-4.6-build" or identity.get("native_endpoint_contact_cardinality")!="unproven" or identity.get("tools_enabled") is not False or not all(isinstance(x,str) and x for x in contact) or contact in seen: raise ValueError("duplicate or invalid native identity")
        root=output/row["cell_id"]; stored=strict(stable(root/"prepared.json"),"prepared"); acknowledgement=strict(stable(root/"authorization-acknowledgement.json"),"acknowledgement").get("acknowledgement_sha256")
        if acknowledgement!=value["authorization_acknowledgement_sha256"] or stored.get("route")!=value["route"] or stored.get("route_evidence")!=value["route_evidence"]: raise ValueError("collector route/evidence differs from persisted execution proof")
        payload_raw,prompt,schema=payload(row); persisted_request,persisted_response,persisted_identity,persisted_settings=admit(root,row,schedule_value,payload_raw,prompt,schema,stored["route"],stored["route_evidence"],acknowledgement,source)
        if (request,response,dict(identity),supplied["effective_settings"]) != (persisted_request,persisted_response,persisted_identity,persisted_settings): raise ValueError("collector differs from persisted execution receipt")
        validated_request, validated_response, validated_identity, validated_settings=source._validate_runner_result({"native_request_bytes":request,"native_response_bytes":response,"identity":identity,"effective_settings":supplied["effective_settings"]},value["route"],base64.b64decode(row["payload_base64"],validate=True))
        if validated_request != source.adapter_canonical({"prompt":base64.b64decode(row["payload_base64"],validate=True).decode()}) or validated_response != response or validated_identity != identity or validated_settings != supplied["effective_settings"]: raise ValueError("independently reconstructed request/settings drifted")
        envelope=strict(response,"collector native response")
        if envelope.get("requestId")!=contact[0] or envelope.get("sessionId")!=contact[1]: raise ValueError("response identity misassociation")
        seen.add(contact); scores,_coverage,_reported=analyzer._v2()._extract_native(response,provider="xai",model="grok-4.6"); target=targets.get(row["item_id"])
        if target is None: raise ValueError("target drifted")
        observed.append({"candidate_id":row["candidate_id"],"prompt_group_id":row["prompt_group_id"],"mae":sum(abs(scores[key]-target[key]) for key in DIMENSIONS)/6})
    if set(index)!={item["cell_id"] for item in value["cells"]}: raise ValueError("partial collector")
    metrics=[]
    for candidate in sorted({row["candidate_id"] for row in schedule_value["cells"]}):
        groups={group["prompt_group_id"]:[x["mae"] for x in observed if x["candidate_id"]==candidate and x["prompt_group_id"]==group["prompt_group_id"]] for group in schedule_value["groups"]}
        if any(len(x)!=1 for x in groups.values()): raise ValueError("equal-group geometry drifted")
        mae={key:value[0] for key,value in groups.items()}; metrics.append({"candidate_id":candidate,"equal_group_mae":sum(mae.values())/3,"group_mae":mae,"cells":3})
    result={"format_version":1,"study_id":STUDY_ID,"kind":"descriptive_equal_group_grok_mae_cardinality_unproven","collector_sha256":sha256(raw),"metrics":sorted(metrics,key=lambda x:(x["equal_group_mae"],x["candidate_id"])),"native_endpoint_contact_cardinality":"unproven","authority":{"selection":"development_only_provisional","promotion":"none","runtime":"none","confirmation":{"status":"unopened","cells":0}},"claim":"DESCRIPTIVE_DEVELOPMENT_ONLY; no Sol, general, promotion, or runtime HANNA claim"}; result["result_sha256"]=sha256(result); return result

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); mode=parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare-all",action="store_true"); mode.add_argument("--execute-one",action="store_true"); mode.add_argument("--finalize-collector",action="store_true"); mode.add_argument("--descriptive-project",action="store_true")
    parser.add_argument("--output-root",type=Path,required=True); parser.add_argument("--normalized-root",type=Path,required=True); parser.add_argument("--materialization-root",type=Path,required=True); parser.add_argument("--frozen-successor",type=Path,required=True); parser.add_argument("--hanna-csv",type=Path,required=True); parser.add_argument("--queue-root",type=Path); parser.add_argument("--collector-output",type=Path); parser.add_argument("--authorization-acknowledgement-sha256"); parser.add_argument("--cell-id"); parser.add_argument("--allow-remote",action="store_true"); args=parser.parse_args(argv)
    common={"output_root":args.output_root,"normalized_root":args.normalized_root,"materialization_root":args.materialization_root,"frozen_successor_path":args.frozen_successor,"hanna_csv_path":args.hanna_csv,"queue_root":args.queue_root,"authorization_acknowledgement_sha256":args.authorization_acknowledgement_sha256}
    if args.prepare_all:
        if args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256: parser.error("prepare requires queue/ack and forbids remote")
        result=prepare_all(**common)
    elif args.execute_one:
        if not args.allow_remote or not args.cell_id: parser.error("execute requires allow_remote and cell")
        result=execute_one(**common,cell_id=args.cell_id,allow_remote=True)
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256: parser.error("finalize requires collector/ack and forbids remote")
        result=finalize_collector(output_root=args.output_root,collector_output=args.collector_output,normalized_root=args.normalized_root,materialization_root=args.materialization_root,frozen_successor_path=args.frozen_successor,hanna_csv_path=args.hanna_csv,authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    else:
        if args.allow_remote or not args.collector_output: parser.error("project requires collector and forbids remote")
        result=descriptive_project(collector_path=args.collector_output,output_root=args.output_root,normalized_root=args.normalized_root,materialization_root=args.materialization_root,frozen_successor_path=args.frozen_successor,hanna_csv_path=args.hanna_csv)
    print(canonical(result).decode(),end=""); return 0
if __name__=="__main__": raise SystemExit(main())
