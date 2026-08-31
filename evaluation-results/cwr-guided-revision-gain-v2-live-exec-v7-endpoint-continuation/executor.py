#!/usr/bin/env python3
"""One-shot endpoint continuation for the immutable V6 revision lineage."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STUDY_ID = "cwr-guided-revision-gain-v2-live-exec-v7-endpoint-continuation"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
V6_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v6-single-replacement" / "executor.py"
V6_SHA256 = "e0f4181e4daed637b6c8e438e71b90129505bd2191202dd2ef43e0f7e406d172"
V5_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v5" / "executor.py"
V5_SHA256 = "42ce0b571c638e9b7883af0706fdff023f6c8805c34a48220d366237dce862a9"
V6_ROOT = Path(r"C:\Users\Haile\Documents\cwr-revision-gain-v6-replacement-c24a9ec-20260831a")
TARGET_ROOT = Path(r"C:\Users\Haile\Documents\cwr-revision-gain-v6-targets-c24a9ec-20260831a")
TARGET_MANIFEST_SHA256 = "c139d7868f0226b2e507baa47c19f2b90adac1ee5ad7856bc12648972d7ae71a"
DEFAULT_QUEUE_ROOT = Path(r"C:\Users\Haile\.codex\state\model-work-queue")
_SUBPROCESS_RUN = subprocess.run

def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def read(path: Path, *, label: str = "artifact") -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part; info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(f"V7 {label} is reparsed")
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError(f"V7 {label} is unsafe")
    before = (info.st_dev, info.st_ino, info.st_size)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if before != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"V7 {label} changed during read")
    return raw

def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle: handle.write(canonical(value) + b"\n")

def write_raw(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle: handle.write(raw)

def commitment(root: Path, path: Path) -> dict[str, Any]:
    raw = read(path); return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": sha(raw)}

def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path); assert spec and spec.loader
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def v6():
    if sha(read(V6_PATH, label="pinned V6 executor")) != V6_SHA256: raise ValueError("V7 V6 executor pin drifted")
    return _load(V6_PATH, "v7_v6")

def v5():
    if sha(read(V5_PATH, label="pinned V5 executor")) != V5_SHA256: raise ValueError("V7 V5 executor pin drifted")
    return _load(V5_PATH, "v7_v5")

def contract() -> dict[str, Any]:
    expected = {"format_version": 2, "study_id": STUDY_ID, "authorized_acknowledgement_sha256": ACK,
        "v6_executor_sha256": V6_SHA256, "v6_root": str(V6_ROOT), "v5_executor_sha256": V5_SHA256,
        "target_root": str(TARGET_ROOT), "target_manifest_sha256": TARGET_MANIFEST_SHA256,
        "geometry": {"endpoints": 40, "grok": 20, "sol": 20, "grok_max_concurrency": 10, "sol_max_concurrency": 2},
        "disclosure": {"payload_classification": "public_repo", "tools_enabled": False, "no_resend": True}}
    if canonical(expected) + b"\n" != read(HERE / "study-contract.json", label="contract"): raise ValueError("V7 contract drifted")
    return expected

def _inputs() -> tuple[Any, Any, list[dict[str, Any]]]:
    base = v6(); base.validate_full_lineage(run_root=V6_ROOT)
    manifest = TARGET_ROOT / "target-manifest.json"
    if sha(read(manifest, label="frozen target manifest")) != TARGET_MANIFEST_SHA256: raise ValueError("V7 frozen target manifest drifted")
    pilot = base._pilot(base._base()); adoption = json.loads(read(V6_ROOT / "adoptions" / f"{base.EVENT_ID}.json"))
    records = [*base._carry_records(base._base(), V6_ROOT), adoption["record"]]
    if pilot.validate_revision_lineage(work_root=V6_ROOT, records=records)["record_count"] != 8: raise ValueError("V7 lineage is incomplete")
    return base, pilot, records

def endpoint_schedule() -> list[dict[str, Any]]:
    _base, pilot, _records = _inputs(); rows = pilot.endpoint_schedule()
    if len(rows) != 40 or {row["judge_route_id"] for row in rows} != {"grok-4.6-high", "gpt-5.6-sol-high"}: raise ValueError("V7 endpoint geometry drifted")
    return rows

def _cell_root(run_root: Path, event_id: str) -> Path:
    return Path(run_root) / "cells" / event_id

def _event_model(event: Mapping[str, Any]) -> str:
    route = event.get("judge_route_id")
    if route == "grok-4.6-high": return "grok-4.6"
    if route == "gpt-5.6-sol-high": return "gpt-5.6-sol"
    raise ValueError("V7 endpoint judge route drifted")

def _safe_run_root(run_root: Path, *, fresh: bool = False) -> Path:
    run_root = Path(os.path.abspath(run_root))
    current = Path(run_root.anchor)
    for part in run_root.parts[1:]:
        current /= part
        if not current.exists(): break
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400): raise ValueError("V7 output root ancestry is reparsed")
    protected = (ROOT.resolve(), V6_ROOT.resolve(), TARGET_ROOT.resolve())
    if any(run_root == path or path in run_root.parents or run_root in path.parents for path in protected): raise ValueError("V7 output root overlaps source or immutable lineage")
    if fresh and run_root.exists(): raise ValueError("V7 run root must be fresh")
    return run_root

def _disjoint(left: Path, right: Path, label: str) -> None:
    left, right = Path(left).resolve(), Path(right).resolve()
    if left == right or left in right.parents or right in left.parents: raise ValueError(f"V7 {label} roots overlap")

def _route(*, pilot: Any, queue_root: Path, event_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    return v5()._governed_route(pilot, queue_root=Path(queue_root), phase="blind_endpoint_judgment", event_id=event_id)

def _route_proof(*, pilot: Any, queue_root: Path, event_id: str) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    broker, route, proof = _route(pilot=pilot, queue_root=queue_root, event_id=event_id)
    return broker, route, {**proof, "study_id": STUDY_ID, "phase": "blind_endpoint_judgment", "event_id": event_id}

def _prepared_files() -> set[str]:
    return {"payload.json", "prepared-cell.json", "governed-route-proof.json", "outbound-payload.json", "adapter-schema-binding.json", "admission.json"}

def _settled_extra(model: str) -> set[str]:
    base = {"launch-intent.json", "adapter-stdout.raw", "adapter-stdout-binding.json", "adapter-control.json", "verified-receipt.json", "execution-result.json", "endpoint-ingest.json"}
    return base | ({"adapter-native-binding.json"} if model == "grok-4.6" else set())

def _inventory(root: Path, expected: set[str]) -> None:
    info = os.lstat(root)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400): raise ValueError("V7 cell root is unsafe")
    children = list(root.iterdir())
    if {child.name for child in children} != expected: raise ValueError("V7 cell inventory drifted")
    for child in children: read(child, label="cell artifact")

def _run_inventory(run_root: Path, endpoint_ids: set[str]) -> None:
    info = os.lstat(run_root)
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("V7 run root is unsafe")
    if {path.name for path in run_root.iterdir()} != {"cells", "immutable-inputs.json", "prepared-index.json"}:
        raise ValueError("V7 run-root inventory drifted")
    cells = run_root / "cells"
    if not cells.is_dir() or {path.name for path in cells.iterdir()} != endpoint_ids:
        raise ValueError("V7 endpoint cell inventory drifted")

def _expected_admission(*, run_root: Path, root: Path, event_id: str, prepared: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version":1,"study_id":STUDY_ID,"kind":"provider_free_endpoint_prepared","event_id":event_id,"provider_model":prepared["provider_model"],"reasoning":prepared["reasoning"],"tools_enabled":False,"prepared":dict(prepared),"outbound_payload":commitment(run_root,root/"outbound-payload.json"),"route_proof":commitment(run_root,root/"governed-route-proof.json"),"immutable_inputs":commitment(run_root,run_root/"immutable-inputs.json"),"target_manifest":commitment(TARGET_ROOT,TARGET_ROOT/"target-manifest.json"),"v6_executor_sha256":V6_SHA256,"v5_executor_sha256":V5_SHA256,"acknowledgement_sha256":ACK,"provider_calls_made":0,"process_launches":0,"no_resend":True}

def _validate_prepared_index(run_root: Path, schedule: list[Mapping[str, Any]]) -> None:
    path = run_root / "prepared-index.json"; raw = read(path, label="prepared index"); value = json.loads(raw)
    expected = {"format_version":1,"study_id":STUDY_ID,"kind":"prepared_endpoint_index","cells":[commitment(run_root,_cell_root(run_root,row["endpoint_event_id"])/"admission.json") for row in schedule]}
    if canonical(value)+b"\n" != raw or value != expected: raise ValueError("V7 prepared-index binding drifted")

def _outbound(*, run_root: Path, event_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    identity = {"study_id": STUDY_ID, "event_id": event_id, "logical_sample_id": sha(canonical({"v6_manifest": TARGET_MANIFEST_SHA256, "event_id": event_id})), "successor_event_id": "v7-" + sha(canonical({"run_root": str(run_root.resolve()), "event_id": event_id}))[:24]}
    return {"format_version": 1, "kind": "versioned_endpoint_outbound_payload", "identity": identity, "pilot_payload": dict(payload)}

def _validated_endpoint_inputs(pilot: Any) -> tuple[dict[str, Any], str, dict[str, tuple[dict[str, Any], str]]]:
    """Validate the immutable V6/target boundary once, then reuse exact bytes."""
    value = pilot.contract(); frozen = pilot._read_frozen(V6_ROOT, study_value=value)
    frozen_sha = sha(read(V6_ROOT / "frozen-inputs.json", label="frozen inputs"))
    manifest_raw = read(TARGET_ROOT / "target-manifest.json", label="frozen target manifest")
    manifest = json.loads(manifest_raw)
    if (canonical(manifest) + b"\n" != manifest_raw or manifest.get("work_root") != str(V6_ROOT.resolve())
            or manifest.get("frozen_manifest_sha256") != frozen_sha or not isinstance(manifest.get("targets"), list)):
        raise ValueError("V7 frozen target manifest boundary drifted")
    targets: dict[str, tuple[dict[str, Any], str]] = {}
    for row in manifest["targets"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("blind_target_id"), str) or not isinstance(row.get("target"), Mapping):
            raise ValueError("V7 frozen target manifest target is invalid")
        target = dict(row["target"]); relative = target.get("path")
        if not isinstance(relative, str) or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in Path(relative).parts):
            raise ValueError("V7 frozen target path is unsafe")
        actual = commitment(TARGET_ROOT, TARGET_ROOT / relative)
        if actual != target or row["blind_target_id"] in targets:
            raise ValueError("V7 frozen target commitment drifted")
        targets[row["blind_target_id"]] = (target, read(TARGET_ROOT / relative, label="frozen blind target").decode("utf-8"))
    expected = {row["blind_target_id"] for row in pilot.targets(value)}
    if set(targets) != expected or len(targets) != 10:
        raise ValueError("V7 frozen target inventory drifted")
    return value, frozen_sha, targets

def _prepare_endpoint_cell(*, pilot: Any, study_value: Mapping[str, Any], frozen_sha: str, targets: Mapping[str, tuple[dict[str, Any], str]], root: Path, event: Mapping[str, Any]) -> dict[str, Any]:
    event_id = event["endpoint_event_id"]
    generic = pilot._prepared_payload(study_value, phase="blind_endpoint_judgment", event_id=event_id)
    target, target_text = targets[event["blind_target_id"]]
    measure = event["measure_id"]
    payload = {"blind_target_text": target_text,
               "endpoint_prompt": pilot._asset(f"{measure}.prompt.md", study_value["assets"][f"{measure}.prompt.md"]).decode("utf-8"),
               "response_schema": json.loads(pilot._asset("score.schema.json", study_value["assets"]["score.schema.json"]).decode("utf-8"))}
    write(root / "payload.json", payload)
    return _prepared_from_payload(pilot=pilot, study_value=study_value, frozen_sha=frozen_sha, target=target, root=root, event=event)

def _prepared_from_payload(*, pilot: Any, study_value: Mapping[str, Any], frozen_sha: str, target: Mapping[str, Any], root: Path, event: Mapping[str, Any]) -> dict[str, Any]:
    event_id = event["endpoint_event_id"]
    generic = pilot._prepared_payload(study_value, phase="blind_endpoint_judgment", event_id=event_id)
    prepared = {"format_version": 1, "study_id": pilot.STUDY_ID, "kind": "prepared_cell", "work_root": str(V6_ROOT.resolve()),
                "frozen_manifest_sha256": frozen_sha, "acknowledgement_sha256": ACK, "provider_calls_made": 0, "process_launches": 0,
                "payload": commitment(root, root / "payload.json"), "phase": "blind_endpoint_judgment", "event_id": event_id,
                "provider_model": generic["provider_model"], "reasoning": generic["reasoning"], "tools_enabled": False,
                "endpoint_target": {"target_root": str(TARGET_ROOT.resolve()), "target_manifest": commitment(TARGET_ROOT, TARGET_ROOT / "target-manifest.json"),
                                    "blind_target_id": event["blind_target_id"], "target": target}, "no_resend": True,
                "precontact_failure": "terminal_fresh_root_required", "postlaunch_failure": "terminal_reconcile_required_no_resend"}
    return prepared

def _validate_prepared_fast(*, pilot: Any, study_value: Mapping[str, Any], frozen_sha: str, targets: Mapping[str, tuple[dict[str, Any], str]], root: Path, prepared: Mapping[str, Any], event: Mapping[str, Any]) -> None:
    target, target_text = targets[event["blind_target_id"]]
    measure = event["measure_id"]
    payload = {"blind_target_text": target_text,
               "endpoint_prompt": pilot._asset(f"{measure}.prompt.md", study_value["assets"][f"{measure}.prompt.md"]).decode("utf-8"),
               "response_schema": json.loads(pilot._asset("score.schema.json", study_value["assets"]["score.schema.json"]).decode("utf-8"))}
    payload_raw = read(root / "payload.json", label="prepared payload")
    expected = _prepared_from_payload(pilot=pilot, study_value=study_value, frozen_sha=frozen_sha, target=target, root=root, event=event)
    prepared_raw = read(root / "prepared-cell.json", label="prepared cell")
    if canonical(payload) + b"\n" != payload_raw or canonical(prepared) + b"\n" != prepared_raw or dict(prepared) != expected:
        raise ValueError("V7 prepared endpoint binding drifted")

def prepare_all(*, run_root: Path, acknowledgement_sha256: str, queue_root: Path = DEFAULT_QUEUE_ROOT) -> list[dict[str, Any]]:
    if acknowledgement_sha256 != ACK: raise ValueError("V7 acknowledgement is invalid")
    run_root = _safe_run_root(Path(run_root), fresh=True); _base, pilot, _records = _inputs(); _disjoint(run_root, Path(queue_root), "work/queue")
    manifest = TARGET_ROOT / "target-manifest.json"; run_root.mkdir(parents=True); prepared_rows=[]
    rows = pilot.endpoint_schedule()
    study_value, frozen_sha, targets = _validated_endpoint_inputs(pilot)
    immutable = {"format_version": 1, "study_id": STUDY_ID, "kind": "validated_immutable_v6_endpoint_inputs",
                 "v6_executor_sha256": V6_SHA256, "v5_executor_sha256": V5_SHA256,
                 "v6_lineage": {"record_count": len(_records), "revision_lineage_sha256": sha(canonical(_records))},
                 "frozen_inputs_sha256": frozen_sha, "target_manifest": commitment(TARGET_ROOT, manifest),
                 "target_ids": sorted(targets)}
    write(run_root / "immutable-inputs.json", immutable)
    route_cache: dict[str, tuple[Any, dict[str, Any], dict[str, Any]]] = {}
    for event in rows:
        event_id = event["endpoint_event_id"]; root = _cell_root(run_root, event_id); model = _event_model(event)
        if model not in route_cache:
            route_cache[model] = _route_proof(pilot=pilot, queue_root=Path(queue_root), event_id=event_id)
        _broker, _route_value, cached_proof = route_cache[model]
        proof = {**cached_proof, "event_id": event_id}
        value = _prepare_endpoint_cell(pilot=pilot, study_value=study_value, frozen_sha=frozen_sha, targets=targets, root=root, event=event)
        write(root / "prepared-cell.json", value)
        write(root / "governed-route-proof.json", proof); payload=json.loads(read(root / "payload.json")); outbound=_outbound(run_root=run_root,event_id=event_id,payload=payload); write(root / "outbound-payload.json",outbound)
        schema={"$schema_version":1,**payload["response_schema"]}; write(root / "adapter-schema-binding.json", {"format_version":1,"study_id":STUDY_ID,"adapter_output_schema":schema,"adapter_output_schema_sha256":sha(canonical(schema))})
        admission=_expected_admission(run_root=run_root,root=root,event_id=event_id,prepared=value)
        write(root/"admission.json",admission); _inventory(root,_prepared_files()); prepared_rows.append(admission)
    write(run_root/"prepared-index.json", {"format_version":1,"study_id":STUDY_ID,"kind":"prepared_endpoint_index","cells":[commitment(run_root,_cell_root(run_root,row["event_id"])/"admission.json") for row in prepared_rows]})
    return prepared_rows

def _context() -> tuple[Any, Any, list[dict[str, Any]], dict[str, Any], str, dict[str, tuple[dict[str, Any], str]]]:
    base,pilot,records = _inputs(); study_value,frozen_sha,targets = _validated_endpoint_inputs(pilot)
    return base,pilot,records,study_value,frozen_sha,targets

def _read_admission(run_root: Path, event_id: str, context: tuple[Any, Any, list[dict[str, Any]], dict[str, Any], str, dict[str, tuple[dict[str, Any], str]]] | None = None) -> tuple[Any,dict[str,Any],dict[str,Any],dict[str,Any]]:
    _base,pilot,_records,study_value,frozen_sha,targets = _context() if context is None else context; schedule=pilot.endpoint_schedule(); _run_inventory(run_root,{row["endpoint_event_id"] for row in schedule}); _validate_prepared_index(run_root,schedule); root=_cell_root(run_root,event_id); _inventory(root,_prepared_files()); raw=read(root/"admission.json"); admission=json.loads(raw); prepared=json.loads(read(root/"prepared-cell.json")); payload=json.loads(read(root/"payload.json")); outbound=_outbound(run_root=run_root,event_id=event_id,payload=payload); event=next((row for row in schedule if row["endpoint_event_id"]==event_id),None)
    immutable_path=run_root/"immutable-inputs.json"; immutable_raw=read(immutable_path,label="immutable inputs"); immutable=json.loads(immutable_raw)
    schema={"$schema_version":1,**payload["response_schema"]}; schema_value=json.loads(read(root/"adapter-schema-binding.json")); expected_schema={"format_version":1,"study_id":STUDY_ID,"adapter_output_schema":schema,"adapter_output_schema_sha256":sha(canonical(schema))}
    proof_raw=read(root/"governed-route-proof.json"); proof=json.loads(proof_raw)
    if (not event or canonical(admission)+b"\n"!=raw or admission!=_expected_admission(run_root=run_root,root=root,event_id=event_id,prepared=prepared) or json.loads(read(root/"outbound-payload.json"))!=outbound or canonical(immutable)+b"\n"!=immutable_raw or immutable.get("study_id")!=STUDY_ID or immutable.get("v6_executor_sha256")!=V6_SHA256 or immutable.get("v5_executor_sha256")!=V5_SHA256 or immutable.get("target_manifest")!=commitment(TARGET_ROOT,TARGET_ROOT/"target-manifest.json") or canonical(schema_value)+b"\n"!=read(root/"adapter-schema-binding.json") or schema_value!=expected_schema or canonical(proof)+b"\n"!=proof_raw or proof.get("study_id")!=STUDY_ID or proof.get("event_id")!=event_id or proof.get("model")!=prepared.get("provider_model") or proof.get("tools_enabled") is not False):
        raise ValueError("V7 admission or immutable input binding drifted")
    _validate_prepared_fast(pilot=pilot, study_value=study_value, frozen_sha=frozen_sha, targets=targets, root=root, prepared=prepared, event=event); return pilot,admission,prepared,event

def _call_args(broker: Any, route: Mapping[str,Any], schema: Mapping[str,Any], outbound: bytes) -> tuple[list[str],bytes,int]:
    if route["adapter"] == "codex_exec":
        args=["--codex-command-json",canonical(route["codex_command"]).decode(),"--model",route["model"],"--reasoning-effort",route["reasoning_effort"],"--output-schema-json",canonical(schema).decode(),"--expected-command-identity-json",canonical(route["codex_command_identity"]).decode(),"--cli-version-command-json",canonical(route["cli_version_command"]).decode(),"--expected-cli-version-identity-json",canonical(route["cli_version_identity"]).decode(),"--expected-cli-version",route["codex_cli_version"],"--auth-status-command-json",canonical(route["auth_status_command"]).decode(),"--expected-auth-status-identity-json",canonical(route["auth_status_identity"]).decode(),"--auth-receipt-json",canonical(broker._load_json_artifact(route["auth_receipt_hash"])).decode(),"--broker-root",str(broker.root),"--timeout-seconds",str(route["timeout_seconds"])]
    else:
        args=["--grok-command-json",canonical(route["grok_command"]).decode(),"--model",route["model"],"--reported-model",route["reported_model"],"--reasoning-effort",route["reasoning_effort"],"--output-schema-json",canonical(schema).decode(),"--expected-command-identity-json",canonical(route["grok_command_identity"]).decode(),"--cli-version-command-json",canonical(route["cli_version_command"]).decode(),"--expected-cli-version-identity-json",canonical(route["cli_version_identity"]).decode(),"--expected-cli-version",route["grok_cli_version"],"--subscription-receipt-json",canonical(broker._load_json_artifact(route["subscription_receipt_hash"])).decode(),"--broker-root",str(broker.root),"--timeout-seconds",str(route["timeout_seconds"]),"--nonvisual-max-turns",str(route["nonvisual_max_turns"])]
    return [*route["command"],*args],canonical({"prompt":outbound.decode("utf-8")}),int(route["timeout_seconds"])

def _control(raw: bytes) -> tuple[str,Mapping[str,Any]|None]:
    try: value=json.loads(raw.decode("ascii").rstrip("\r\n"))
    except (UnicodeDecodeError,json.JSONDecodeError) as error: raise ValueError("V7 adapter stdout is invalid") from error
    control=value.get("control") if isinstance(value,Mapping) else None
    if not isinstance(control,Mapping) or control.get("version")!=1 or control.get("state") not in {"completed","definitely_not_contacted","ambiguous"}: raise ValueError("V7 adapter control drifted")
    result=value.get("result")
    if control["state"]=="completed" and (set(value)!={"control","result"} or control!={"version":1,"state":"completed"} or not isinstance(result,Mapping)): raise ValueError("V7 completion result drifted")
    return control["state"],result if control["state"]=="completed" else None

def _receipt(*,pilot:Any,run_root:Path,root:Path,prepared:Mapping[str,Any],event:Mapping[str,Any],route:Mapping[str,Any],raw:bytes)->dict[str,Any]:
    state,result=_control(raw)
    if state!="completed" or result is None: raise ValueError("V7 completed control is required")
    outbound=read(root/"outbound-payload.json"); runtime,response=result.get("runtime"),result.get("output")
    if result.get("schema_version")!=1 or result.get("request_hash")!=sha(canonical({"prompt":outbound.decode("utf-8")})) or result.get("output_hash")!=sha(canonical(response)) or not isinstance(runtime,Mapping) or not isinstance(response,Mapping): raise ValueError("V7 adapter result binding drifted")
    pilot._validate_response_schema(prepared,response)
    intent=read(root/"launch-intent.json"); common={"format_version":1,"study_id":STUDY_ID,"prepared_root":str(root.resolve()),"event_id":event["endpoint_event_id"],"phase":"blind_endpoint_judgment","prepared_record_sha256":sha(read(root/"prepared-cell.json")),"launch_intent_sha256":sha(intent),"frozen_manifest_sha256":prepared["frozen_manifest_sha256"],"provider_model":prepared["provider_model"],"reasoning":prepared["reasoning"],"tools_enabled":False,"payload_sha256":sha(outbound),"response_sha256":sha(canonical(response)),"response":dict(response)}
    proof=json.loads(read(root/"governed-route-proof.json"))
    if prepared["provider_model"]=="grok-4.6":
        keys={"adapter_version","requested_model","reported_model","requested_reasoning_effort","reasoning_attested","reasoning_attestation","identity_evidence","cli_version","session_id_hash","request_id_hash","observed_turns","envelope_hash","command_identity","command_identity_hash","subscription_receipt_hash","execution_policy","usage_telemetry","nonvisual_max_turns"}
        if set(runtime)!=keys or runtime.get("adapter_version")!=1 or runtime.get("requested_model")!="grok-4.6" or runtime.get("reported_model")!="grok-4.6-build" or runtime.get("requested_reasoning_effort")!="high" or runtime.get("reasoning_attested") is not False or runtime.get("identity_evidence")!="requested_only" or runtime.get("observed_turns")!=1 or runtime.get("nonvisual_max_turns")!=1 or runtime.get("command_identity")!=route.get("grok_command_identity") or runtime.get("subscription_receipt_hash")!=proof.get("route_receipt_sha256") or any(not isinstance(runtime.get(key),str) or not re.fullmatch(r"[0-9a-f]{64}",runtime[key]) for key in ("session_id_hash","request_id_hash","envelope_hash","command_identity_hash","subscription_receipt_hash")) or runtime["session_id_hash"]==runtime["request_id_hash"]: raise ValueError("V7 Grok runtime identity drifted")
        native={"provider_request_id":"grok-request-sha256:"+runtime["request_id_hash"],"session_id":"grok-session-sha256:"+runtime["session_id_hash"]}
        return {**common,"kind":"verified_v7_grok_endpoint_receipt","evidence_class":"grok_native_request_session_exact_one_contact_v1","native_endpoint_contact_cardinality":1,"native":native,"runtime":dict(runtime)}
    required={"adapter_version","requested_model","requested_reasoning_effort","identity_evidence","cli_version","events_hash","event_projection","raw_output_hash","command_identity","auth_receipt_hash","command_identity_hash"}
    if set(runtime)!=required or runtime.get("adapter_version")!=1 or runtime.get("requested_model")!="gpt-5.6-sol" or runtime.get("requested_reasoning_effort")!="high" or runtime.get("identity_evidence")!="requested_only" or runtime.get("auth_receipt_hash")!=proof.get("route_receipt_sha256") or runtime.get("command_identity_hash")!=proof.get("expected_adapter_runtime_identity_sha256") or any(not isinstance(runtime.get(key),str) or not re.fullmatch(r"[0-9a-f]{64}",runtime[key]) for key in ("events_hash","raw_output_hash","auth_receipt_hash","command_identity_hash")) or not isinstance(runtime.get("event_projection"),Mapping) or not isinstance(runtime["event_projection"].get("thread_id"),str) or not runtime["event_projection"]["thread_id"]: raise ValueError("V7 Sol lifecycle identity drifted")
    return {**common,"kind":"verified_v7_sol_endpoint_receipt","evidence_class":"sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1","native_endpoint_contact_cardinality":"unproven","local_lifecycle":{"events_hash":runtime["events_hash"],"raw_output_hash":runtime["raw_output_hash"],"thread_id_sha256":sha(runtime["event_projection"]["thread_id"].encode()),"command_identity_hash":runtime["command_identity_hash"],"auth_receipt_hash":runtime["auth_receipt_hash"]}}

def execute_one(*,run_root:Path,event_id:str,allow_remote:bool,queue_root:Path=DEFAULT_QUEUE_ROOT,_context_value:tuple[Any, Any, list[dict[str, Any]], dict[str, Any], str, dict[str, tuple[dict[str, Any], str]]] | None=None)->dict[str,Any]:
    if allow_remote is not True: raise ValueError("V7 requires explicit allow_remote=True")
    run_root=_safe_run_root(Path(run_root)); root=_cell_root(run_root,event_id)
    if (root/"launch-intent.json").exists(): raise ValueError("V7 cell is one-shot and cannot resend")
    pilot,admission,prepared,event=_read_admission(run_root,event_id,context=_context_value)
    try:
        broker,route,current=_route_proof(pilot=pilot,queue_root=Path(queue_root),event_id=event_id); persisted=json.loads(read(root/"governed-route-proof.json")); stable=set(persisted)-{"validated_at"}
        if any(persisted.get(key)!=current.get(key) for key in stable): raise ValueError("V7 fresh governed route drifted")
        _disjoint(run_root,Path(current["queue_root"]),"work/queue")
        schema=json.loads(read(root/"adapter-schema-binding.json"))["adapter_output_schema"]; command,stdin,timeout=_call_args(broker,route,schema,read(root/"outbound-payload.json")); pilot.begin_one_launch(prepared_root=root)
    except Exception as error:
        if (root/"launch-intent.json").exists(): raise
        outcome=pilot.record_terminal_outcome(prepared_root=root,process_launches=0,settled=False)
        return {"study_id":STUDY_ID,"event_id":event_id,"state":outcome["state"],"provider_calls_made":0,"process_launches":0,"error_type":type(error).__name__,"error":str(error)}
    try:
        done=_SUBPROCESS_RUN(command,input=stdin,capture_output=True,check=False,timeout=timeout); write_raw(root/"adapter-stdout.raw",done.stdout); write(root/"adapter-stdout-binding.json",{"format_version":1,"study_id":STUDY_ID,"raw_stdout":commitment(run_root,root/"adapter-stdout.raw")})
        if done.returncode!=0: raise ValueError("V7 subprocess did not settle")
        state,_result=_control(done.stdout); write(root/"adapter-control.json",json.loads(done.stdout.decode("ascii")))
        if state!="completed": raise ValueError("V7 endpoint did not complete")
        receipt=_receipt(pilot=pilot,run_root=run_root,root=root,prepared=prepared,event=event,route=route,raw=done.stdout)
        if prepared["provider_model"]=="grok-4.6": write(root/"adapter-native-binding.json",{"format_version":1,"study_id":STUDY_ID,"outbound_payload":commitment(run_root,root/"outbound-payload.json"),"receipt":receipt})
        write(root/"verified-receipt.json",receipt); write(root/"endpoint-ingest.json",{"format_version":1,"study_id":STUDY_ID,"event_id":event_id,"verified_receipt":commitment(run_root,root/"verified-receipt.json"),"provider_model":receipt["provider_model"],"evidence_class":receipt["evidence_class"],"native_endpoint_contact_cardinality":receipt["native_endpoint_contact_cardinality"]})
        result={"format_version":1,"study_id":STUDY_ID,"event_id":event_id,"state":"settled","provider_calls_made":receipt["native_endpoint_contact_cardinality"],"process_launches":1,"no_resend":True,"verified_receipt":commitment(run_root,root/"verified-receipt.json")}; write(root/"execution-result.json",result); _inventory(root,_prepared_files()|_settled_extra(prepared["provider_model"])); return result
    except Exception as error:
        pilot.record_terminal_outcome(prepared_root=root,process_launches=1,settled=False)
        return {"study_id":STUDY_ID,"event_id":event_id,"state":"terminal_postlaunch_reconcile_required","provider_calls_made":"unproven","process_launches":1,"no_resend":True,"error_type":type(error).__name__,"error":str(error)}

def execute_endpoint_wave(*,run_root:Path,event_ids:list[str],allow_remote:bool,queue_root:Path=DEFAULT_QUEUE_ROOT)->list[dict[str,Any]]:
    rows={row["endpoint_event_id"]:row for row in endpoint_schedule()}
    if len(event_ids)!=len(set(event_ids)) or any(event_id not in rows for event_id in event_ids): raise ValueError("V7 wave event identities are invalid")
    results=[]; context = _context()
    for model,workers in (("grok-4.6",10),("gpt-5.6-sol",2)):
        ids=[event_id for event_id in event_ids if _event_model(rows[event_id])==model]
        with ThreadPoolExecutor(max_workers=workers) as pool: results.extend(pool.map(lambda item:execute_one(run_root=run_root,event_id=item,allow_remote=allow_remote,queue_root=queue_root,_context_value=context),ids))
    return results

def _replay_receipt(run_root:Path,path:Path,context:tuple[Any, Any, list[dict[str, Any]], dict[str, Any], str, dict[str, tuple[dict[str, Any], str]]] | None=None)->tuple[dict[str,Any],dict[str,Any]]:
    raw=read(path,label="receipt"); receipt=json.loads(raw)
    if canonical(receipt)+b"\n"!=raw or path.name!="verified-receipt.json": raise ValueError("V7 receipt is not canonical authority")
    event_id=receipt.get("event_id"); _base,pilot,_records,study_value,frozen_sha,targets=_context() if context is None else context; schedule=pilot.endpoint_schedule(); _run_inventory(run_root,{row["endpoint_event_id"] for row in schedule}); _validate_prepared_index(run_root,schedule); root=_cell_root(run_root,event_id); prepared=json.loads(read(root/"prepared-cell.json")); admission_raw=read(root/"admission.json"); admission=json.loads(admission_raw); payload=json.loads(read(root/"payload.json")); event=next((row for row in schedule if row["endpoint_event_id"]==event_id),None)
    if not event or canonical(admission)+b"\n"!=admission_raw or admission!=_expected_admission(run_root=run_root,root=root,event_id=event_id,prepared=prepared): raise ValueError("V7 replay admission drifted")
    _validate_prepared_fast(pilot=pilot,study_value=study_value,frozen_sha=frozen_sha,targets=targets,root=root,prepared=prepared,event=event); _inventory(root,_prepared_files()|_settled_extra(prepared["provider_model"]))
    stdout=read(root/"adapter-stdout.raw",label="raw adapter stdout"); stdout_binding=json.loads(read(root/"adapter-stdout-binding.json")); control_raw=read(root/"adapter-control.json"); state,result=_control(stdout)
    expected_stdout_binding={"format_version":1,"study_id":STUDY_ID,"raw_stdout":commitment(run_root,root/"adapter-stdout.raw")}
    envelope=json.loads(stdout.decode("ascii")); expected_stdout=json.dumps(envelope,sort_keys=True).encode("ascii")+b"\n"
    if (state!="completed" or result is None or canonical(stdout_binding)+b"\n"!=read(root/"adapter-stdout-binding.json") or stdout_binding!=expected_stdout_binding or stdout!=expected_stdout or control_raw!=canonical(envelope)+b"\n" or result.get("output")!=receipt.get("response") or result.get("output_hash")!=receipt.get("response_sha256") or result.get("request_hash")!=sha(canonical({"prompt":read(root/"outbound-payload.json").decode("utf-8")}))): raise ValueError("V7 raw adapter replay drifted")
    if path.resolve()!=(root/"verified-receipt.json").resolve() or receipt.get("prepared_root")!=str(root.resolve()) or receipt.get("payload_sha256")!=sha(read(root/"outbound-payload.json")) or receipt.get("prepared_record_sha256")!=sha(read(root/"prepared-cell.json")) or receipt.get("launch_intent_sha256")!=sha(read(root/"launch-intent.json")) or receipt.get("provider_model")!=prepared["provider_model"] or receipt.get("reasoning")!=prepared["reasoning"] or receipt.get("tools_enabled") is not False: raise ValueError("V7 receipt authority drifted")
    response=receipt.get("response"); limits=(1,7) if event["measure_id"]=="holistic" else (1,5)
    if not isinstance(response,Mapping) or set(response)!={"overall","rationale"} or not isinstance(response.get("overall"),int) or isinstance(response["overall"],bool) or not limits[0]<=response["overall"]<=limits[1] or not isinstance(response.get("rationale"),str) or not response["rationale"] or receipt.get("response_sha256")!=sha(canonical(response)): raise ValueError("V7 endpoint score schema drifted")
    if prepared["provider_model"]=="grok-4.6":
        native=receipt.get("native"); binding=json.loads(read(root/"adapter-native-binding.json"))
        expected_native={"provider_request_id":"grok-request-sha256:"+result["runtime"]["request_id_hash"],"session_id":"grok-session-sha256:"+result["runtime"]["session_id_hash"]}
        if receipt.get("kind")!="verified_v7_grok_endpoint_receipt" or receipt.get("evidence_class")!="grok_native_request_session_exact_one_contact_v1" or receipt.get("native_endpoint_contact_cardinality")!=1 or not isinstance(native,Mapping) or native!=expected_native or native.get("provider_request_id")==native.get("session_id") or binding.get("receipt")!=receipt or receipt.get("runtime")!=result.get("runtime"): raise ValueError("V7 Grok receipt replay drifted")
    else:
        runtime=result.get("runtime",{}); local=receipt.get("local_lifecycle",{}); expected_thread=sha(runtime.get("event_projection",{}).get("thread_id","").encode())
        if receipt.get("kind")!="verified_v7_sol_endpoint_receipt" or receipt.get("evidence_class")!="sol_local_codex_lifecycle_native_endpoint_cardinality_unproven_v1" or receipt.get("native_endpoint_contact_cardinality")!="unproven" or local.get("events_hash")!=runtime.get("events_hash") or local.get("raw_output_hash")!=runtime.get("raw_output_hash") or local.get("thread_id_sha256")!=expected_thread or local.get("command_identity_hash")!=runtime.get("command_identity_hash") or local.get("auth_receipt_hash")!=runtime.get("auth_receipt_hash"): raise ValueError("V7 Sol receipt replay drifted")
    ingest=json.loads(read(root/"endpoint-ingest.json")); expected_ingest={"format_version":1,"study_id":STUDY_ID,"event_id":event_id,"verified_receipt":commitment(run_root,root/"verified-receipt.json"),"provider_model":receipt["provider_model"],"evidence_class":receipt["evidence_class"],"native_endpoint_contact_cardinality":receipt["native_endpoint_contact_cardinality"]}
    result_value=json.loads(read(root/"execution-result.json")); expected_result={"format_version":1,"study_id":STUDY_ID,"event_id":event_id,"state":"settled","provider_calls_made":receipt["native_endpoint_contact_cardinality"],"process_launches":1,"no_resend":True,"verified_receipt":commitment(run_root,root/"verified-receipt.json")}
    if canonical(ingest)+b"\n"!=read(root/"endpoint-ingest.json") or ingest!=expected_ingest or canonical(result_value)+b"\n"!=read(root/"execution-result.json") or result_value!=expected_result: raise ValueError("V7 endpoint ingest/result replay drifted")
    return receipt,event

def project_independent_metrics(*,receipt_paths:list[Path])->dict[str,Any]:
    if len(receipt_paths)!=40: raise ValueError("V7 needs forty persisted endpoint authorities")
    run_roots={str(Path(path).resolve().parents[2]) for path in receipt_paths}
    if len(run_roots)!=1: raise ValueError("V7 projection cannot splice endpoint runs")
    run_root=Path(next(iter(run_roots))); context=_context(); schedule={row["endpoint_event_id"]:row for row in context[1].endpoint_schedule()}; scores={}; evidence={}; grok_requests=set(); grok_sessions=set(); sol_threads=set()
    for path in receipt_paths:
        receipt,event=_replay_receipt(run_root,Path(path),context=context); event_id=event["endpoint_event_id"]
        if event_id in scores or event_id not in schedule: raise ValueError("V7 endpoint receipt is duplicate or unscheduled")
        scores[event_id]=receipt["response"]["overall"]; item={"evidence_class":receipt["evidence_class"],"native_endpoint_contact_cardinality":receipt["native_endpoint_contact_cardinality"]}; previous=evidence.setdefault(event["judge_route_id"],item)
        if previous!=item: raise ValueError("V7 endpoint evidence identity changed")
        if receipt["provider_model"]=="grok-4.6":
            request_id=receipt["native"]["provider_request_id"]; session_id=receipt["native"]["session_id"]
            if request_id in grok_requests or session_id in grok_sessions: raise ValueError("V7 Grok endpoint identities were pooled")
            grok_requests.add(request_id); grok_sessions.add(session_id)
        else:
            identity=receipt["local_lifecycle"]["thread_id_sha256"]
            if identity in sol_threads: raise ValueError("V7 Sol endpoint identities were pooled")
            sol_threads.add(identity)
    if set(scores)!=set(schedule): raise ValueError("V7 endpoint evidence is incomplete")
    _base,pilot,_records,_study_value,_frozen_sha,_prepared_targets=context; targets={row["target_event_id"]:row["blind_target_id"] for row in pilot.targets() if row["target_event_id"]}; baselines={row["source_item_id"]:row["blind_target_id"] for row in pilot.targets() if row["kind"]=="source_baseline"}; primary=[]; arm=[]
    for revision in pilot.revision_schedule():
        target=targets[revision["event_id"]]
        for judge in pilot.contract()["routes"]["judges"]:
            for measure in ("holistic","compact"):
                eid=f"endpoint-v2-{target}-{measure}-{judge}"; baseline=f"endpoint-v2-{baselines[revision['source_item_id']]}-{measure}-{judge}"; arm.append({"source_item_id":revision["source_item_id"],"cycle":revision["cycle"],"guidance_arm":revision["guidance_arm"],"judge_route_id":judge,"measure_id":measure,"event_id":revision["event_id"],"arm_minus_baseline":scores[eid]-scores[baseline],**evidence[judge]})
                if revision["guidance_arm"]=="cwr_guided":
                    control=pilot._revision_id(revision["cycle"],revision["source_item_id"],"generic_no_feedback"); cid=f"endpoint-v2-{targets[control]}-{measure}-{judge}"; primary.append({"source_item_id":revision["source_item_id"],"cycle":revision["cycle"],"judge_route_id":judge,"measure_id":measure,"guided_event_id":revision["event_id"],"control_event_id":control,"guided_minus_control":scores[eid]-scores[cid],**evidence[judge]})
    summaries=[]
    for judge in pilot.contract()["routes"]["judges"]:
        for measure in ("holistic","compact"):
            values=[row["guided_minus_control"] for row in primary if row["judge_route_id"]==judge and row["measure_id"]==measure]; summaries.append({"judge_route_id":judge,"measure_id":measure,"sample_count":len(values),"mean_guided_minus_control":sum(values)/len(values),"positive":sum(value>0 for value in values),"zero":sum(value==0 for value in values),"negative":sum(value<0 for value in values),**evidence[judge]})
    return {"study_id":STUDY_ID,"kind":"independently_recomputed_v7_separate_endpoint_projection","pinned_v5_semantics_sha256":V5_SHA256,"endpoint_results_are_not_pooled":True,"endpoint_evidence":[{"judge_route_id":judge,"endpoint_count":20,**evidence[judge]} for judge in pilot.contract()["routes"]["judges"]],"primary_guided_minus_control":primary,"arm_minus_baseline":arm,"summaries":summaries}
