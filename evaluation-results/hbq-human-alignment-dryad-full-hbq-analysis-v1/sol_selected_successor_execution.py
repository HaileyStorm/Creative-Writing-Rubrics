"""Prospective, no-resend collector for the selected 100-story Dryad schedule."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import uuid
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parent
PARALLEL = ROOT / "sol_parallel_execution_v1.py"
RUNTIME = ROOT / "sol_selected_successor_runtime.py"
SCHEDULE = ROOT / "baseline_selected_schedule.py"
CAPTURE = ROOT.parents[1] / "src" / "hbqrs" / "sol_process_capture.py"
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-completed-message-recovery-1328-1342-20260909-r1\reconciliation.json")
PARALLEL_SHA256 = "d1ec216bfe828a51f73da797f3658ff54a9aebcce4882d36807076bc2da437f6"
SCHEDULE_SHA256 = "20b38d4f14415d2e61da4cc01c002aa82662814ea451e2d83133a1161b971e41"
CAPTURE_SHA256 = "d93a24580b1b492ea116514ba768bb7f7dc5a8e386c925720b434ce94c4d9cb7"
RECONCILIATION_SHA256 = "1e874165e154e3bf5e5159e4d4bea5b3e20abe4ce0b0bb1815925b8cbbe1a951"
LANES = 10
REUSED_REQUESTS = 1342
RECOVERED_ORDINALS = (1328, 1333, 1335, 1336, 1337, 1338, 1339, 1340, 1341, 1342)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _load(path: Path, expected: str, name: str) -> Any:
    raw = path.read_bytes()
    _require(_sha(raw) == expected, f"{name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"{name} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{name} changed during load")
    return module


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _reconciliation(path: Path) -> dict[str, Any]:
    _require(_sha(path.read_bytes()) == RECONCILIATION_SHA256, "reconciliation differs")
    value = _json(path, "reconciliation")
    _require(value.get("recognized_logical_requests") == REUSED_REQUESTS
             and value.get("ordinary_accepted_requests") == 1332
             and value.get("recovered_requests") == len(RECOVERED_ORDINALS)
             and value.get("through_ordinal") == REUSED_REQUESTS
             and value.get("unique_retained_native_threads") == REUSED_REQUESTS
             and value.get("resend_authority") is False
             and value.get("provider_calls_this_reconciliation") == 0
             and value.get("process_success_proven") is False
             and value.get("original_failed_terminals_preserved") is True,
             "reconciliation prefix differs")
    records = value.get("recoveries")
    _require(isinstance(records, list) and [item.get("ordinal") for item in records] == list(RECOVERED_ORDINALS),
             "reconciliation recovery order differs")
    return value


def _prefix(*, plan_root: Path, original_root: Path, replacement_root: Path, old_root: Path, parallel_root: Path,
            reconciliation_path: Path = RECONCILIATION) -> dict[str, Any]:
    parallel = _load(PARALLEL, PARALLEL_SHA256, "old parallel collector")
    helper = parallel._load(parallel.HELPER_PATH, parallel.HELPER_SHA, "old parallel helper")
    old = parallel._load(parallel.OLD_PATH, parallel.OLD_SHA, "old parallel executor")
    plan_root, original_root, replacement_root, old_root, parallel_root = (
        Path(plan_root).resolve(), Path(original_root).resolve(), Path(replacement_root).resolve(), Path(old_root).resolve(),
        Path(parallel_root).resolve())
    boundary = parallel._handoff(old_root, old_root / "requests" / "0829" / "handoff-stop.json")
    prefix = parallel._prefix(helper, old, plan_root, original_root, replacement_root, old_root, boundary)
    threads = set(prefix["thread_ids"])
    manifest_sha = _sha((parallel_root / "campaign-manifest.json").read_bytes())
    identity = prefix["route_identity"]
    recovered = {item["ordinal"]: item for item in _reconciliation(Path(reconciliation_path))["recoveries"]}
    ordinary = 0
    for ordinal in range(boundary, REUSED_REQUESTS + 1):
        request, prompt, schema = helper.request_payload(plan_root, ordinal)
        slot = parallel_root / "requests" / f"{ordinal:04d}"
        _require((slot / "payload" / f"request-{ordinal:04d}.txt").read_bytes() == prompt
                 and (slot / "payload" / f"request-{ordinal:04d}.json").read_bytes() == schema,
                 "historical request payload differs")
        if ordinal not in recovered:
            accepted = old._accepted(helper, slot, request, manifest_sha, identity, threads)
            _require(accepted["thread_id"] in threads, "historical native identity is absent")
            ordinary += 1
            continue
        recovery = recovered[ordinal]
        terminal = _json(slot / "terminal.json", "historical recovered terminal")
        _require(terminal.get("state") == "stopped_no_retry" and recovery.get("process_returncode") is None
                 and recovery.get("process_success_proven") is False and recovery.get("thread_id") not in threads,
                 "historical recovered terminal differs")
        message = Path(recovery["native_files"]["message"]["path"])
        _require(_sha(message.read_bytes()) == recovery["derived_response_sha256"], "recovered final message differs")
        threads.add(recovery["thread_id"])
    _require(ordinary == 504 and len(threads) == REUSED_REQUESTS, "historical prefix identity inventory differs")
    return {"through_ordinal": REUSED_REQUESTS, "thread_ids": sorted(threads), "route_identity": dict(identity),
            "ordinary_accepted_requests": 828 + ordinary, "recovered_requests": len(recovered),
            "reconciliation_sha256": RECONCILIATION_SHA256, "parallel_prefix_sha256": _sha(_canonical(prefix))}


def _remaining(schedule: Mapping[str, Any]) -> list[int]:
    selected = schedule.get("selected_request_ordinals")
    _require(isinstance(selected, list) and len(selected) == 2300 and len(set(selected)) == len(selected)
             and all(type(item) is int for item in selected), "selected schedule ordinals differ")
    _require(selected == list(range(1, 1611)) + list(range(4049, 4739)), "selected schedule order differs")
    remaining = [ordinal for ordinal in selected if ordinal > REUSED_REQUESTS]
    _require(remaining == list(range(1343, 1611)) + list(range(4049, 4739)), "selected successor ordinals differ")
    return remaining


def _manifest(*, schedule: Mapping[str, Any], schedule_sha256: str, prefix: Mapping[str, Any], plan_root: Path,
              expected_plan_sha256: str, parallel_root: Path) -> dict[str, Any]:
    remaining = _remaining(schedule)
    return {"schema_version": 1, "evidence_class": "dryad_selected_sol_successor_prospective_v1",
            "driver_sha256": _sha(Path(__file__).read_bytes()), "runtime_sha256": _sha(RUNTIME.read_bytes()),
            "capture_sha256": CAPTURE_SHA256, "old_parallel_sha256": PARALLEL_SHA256,
            "selected_schedule_sha256": schedule_sha256, "selected_schedule_source_sha256": SCHEDULE_SHA256,
            "plan_root": str(Path(plan_root).resolve()), "original_plan_sha256": expected_plan_sha256,
            "parallel_root": str(Path(parallel_root).resolve()), "parallel_manifest_sha256": _sha((Path(parallel_root) / "campaign-manifest.json").read_bytes()),
            "route_identity": dict(prefix["route_identity"]), "prefix": dict(prefix),
            "counts": {"selected_requests": 2300, "reused_requests": REUSED_REQUESTS, "remaining_requests": len(remaining), "lanes": LANES},
            "remaining_original_ordinals": remaining, "attempt_policy": {"cumulative_attempts": 1, "resend": False},
            "allowance_policy": "owner_assumed_allowance_no_fresh_evidence", "full_study_admitted": False}


def prepare_campaign(*, campaign_root: Path, plan_root: Path, original_root: Path, replacement_root: Path, old_root: Path,
                     parallel_root: Path,
                     selected_schedule: Mapping[str, Any], selected_schedule_sha256: str, expected_plan_sha256: str,
                     reconciliation_path: Path = RECONCILIATION) -> dict[str, Any]:
    schedule_module = _load(SCHEDULE, SCHEDULE_SHA256, "selected schedule")
    verified = schedule_module.verify_selected_schedule(descriptor=selected_schedule, plan_root=plan_root,
                                                        expected_plan_sha256=expected_plan_sha256)
    _require(_sha(_canonical(verified)) == selected_schedule_sha256, "selected schedule hash differs")
    prefix = _prefix(plan_root=plan_root, original_root=original_root, replacement_root=replacement_root,
                     old_root=old_root, parallel_root=parallel_root, reconciliation_path=reconciliation_path)
    manifest = _manifest(schedule=verified, schedule_sha256=selected_schedule_sha256, prefix=prefix, plan_root=plan_root,
                         expected_plan_sha256=expected_plan_sha256, parallel_root=parallel_root)
    root = Path(campaign_root).resolve(); root.mkdir(parents=True, exist_ok=True)
    raw = _canonical(manifest); path = root / "campaign-manifest.json"
    if path.exists():
        _require(path.read_bytes() == raw, "selected successor manifest differs")
    else:
        _new(path, raw)
    descriptor_path = root / "selected-schedule.json"
    descriptor_raw = schedule_module.canonical(verified)
    if descriptor_path.exists():
        _require(descriptor_path.read_bytes() == descriptor_raw, "selected successor schedule differs")
    else:
        _new(descriptor_path, descriptor_raw)
    return manifest


def _validated_completion(slot: Path, request: Mapping[str, Any], runtime: Any) -> tuple[str, dict[str, Any]]:
    native = slot / "native-output"
    _require(_sha((native / "payload" / "prompt.txt").read_bytes()) == request.get("prompt_sha256")
             and _sha((native / "payload" / "schema.json").read_bytes()) == request.get("schema_sha256"),
             "selected successor frozen request payload differs")
    record = _json(slot / "provider-record.json", "selected successor provider record")
    response = (slot / "response.json").read_bytes()
    completion = record.get("completion")
    receipt = _json(slot / "process-completion" / "native-output.json", "selected successor process receipt")
    message = (native / "responses" / f"batch-{request['batch_number']:04d}.attempt-0001.message.json").read_bytes()
    events = (native / "responses" / f"batch-{request['batch_number']:04d}.attempt-0001.events.jsonl").read_bytes()
    stderr = (native / "responses" / f"batch-{request['batch_number']:04d}.attempt-0001.stderr.bin").read_bytes()
    artifacts = record.get("provider_artifacts")
    _require(isinstance(completion, Mapping) and completion == receipt and receipt.get("state") == "completed"
             and receipt.get("exit_code") == 0 and receipt.get("final_message", {}).get("exists") is True
             and receipt["final_message"].get("bytes") == len(message) and receipt["final_message"].get("sha256") == _sha(message)
             and receipt.get("stdout") == {"bytes": len(events), "sha256": _sha(events)}
             and receipt.get("stderr") == {"bytes": len(stderr), "sha256": _sha(stderr)}
             and isinstance(artifacts, Mapping)
             and artifacts.get("codex_events") == {"path": f"responses/batch-{request['batch_number']:04d}.attempt-0001.events.jsonl", "bytes": len(events), "sha256": _sha(events)}
             and artifacts.get("codex_stderr") == {"path": f"responses/batch-{request['batch_number']:04d}.attempt-0001.stderr.bin", "bytes": len(stderr), "sha256": _sha(stderr)},
             "selected successor completion artifacts differ")
    _require(response == message, "selected successor retained response differs")
    try:
        value = json.loads(response.decode("utf-8"))
        schema = json.loads((native / "payload" / "schema.json").read_bytes())
        Draft202012Validator(schema).validate(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise ValueError("selected successor response schema differs") from error
    verdicts, ids = value.get("verdicts") if isinstance(value, Mapping) else None, request.get("question_ids")
    _require(isinstance(verdicts, list) and isinstance(ids, list)
             and [item.get("question_id") for item in verdicts if isinstance(item, Mapping)] == ids,
             "selected successor verdict identities differ")
    thread_id = record.get("native_thread_id")
    _require(record.get("completion_class") in {"completed", "completed_with_wrapper_warning"}
             and isinstance(thread_id, str) and thread_id, "selected successor completion identity differs")
    _require(runtime.replay_completion(output_dir=native, batch_number=request["batch_number"], record=record) == thread_id,
             "selected successor replayed lifecycle identity differs")
    return thread_id, record


def _completed(root: Path, request: Mapping[str, Any], threads: set[str], *, runtime: Any,
               manifest_sha256: str) -> bool:
    ordinal = int(request["ordinal"])
    slot = root / "requests" / f"{ordinal:04d}"
    if not slot.exists():
        return False
    terminal = _json(slot / "terminal.json", "selected successor terminal")
    _require(terminal.get("state") in {"completed", "completed_with_wrapper_warning"}, "ambiguous selected successor terminal cannot restart")
    thread_id = terminal.get("thread_id")
    _require(isinstance(thread_id, str) and thread_id not in threads, "selected successor native identity duplicates")
    start_raw = (slot / "start.json").read_bytes(); start = _json(slot / "start.json", "selected successor start")
    route_raw = (slot / "route.json").read_bytes()
    source_raw = (slot / "source-bindings.json").read_bytes(); source = _json(slot / "source-bindings.json", "selected successor source bindings")
    authorization = _json(slot / "authorization.json", "selected successor authorization")
    _require(start.get("state") == "started" and start.get("ordinal") == ordinal and start.get("attempt") == 1
             and source.get("manifest_sha256") == manifest_sha256
             and start.get("prompt_sha256") == request.get("prompt_sha256")
             and start.get("schema_sha256") == request.get("schema_sha256")
             and source.get("prompt_sha256") == start.get("prompt_sha256") and source.get("schema_sha256") == start.get("schema_sha256")
             and authorization.get("start_sha256") == _sha(start_raw) and authorization.get("ordinal") == ordinal
             and authorization.get("route_sha256") == _sha(route_raw) and authorization.get("source_bindings_sha256") == _sha(source_raw)
             and authorization.get("allowance_policy") == "owner_assumed_allowance_no_fresh_evidence",
             "selected successor persisted precontact binding differs")
    validated_thread, record = _validated_completion(slot, request, runtime)
    _require(validated_thread == thread_id and record.get("completion_class") == terminal.get("state")
             and terminal.get("response_sha256") == _sha((slot / "response.json").read_bytes()),
             "selected successor completed receipt differs")
    threads.add(thread_id)
    return True


def _dispatch_locked(*, campaign_root: Path, queue_root: Path, adapter_override: Any | None = None,
                     stop_path: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); manifest = _json(root / "campaign-manifest.json", "selected successor manifest")
    _require(manifest.get("driver_sha256") == _sha(Path(__file__).read_bytes())
             and manifest.get("runtime_sha256") == _sha(RUNTIME.read_bytes())
             and manifest.get("old_parallel_sha256") == PARALLEL_SHA256
             and manifest.get("selected_schedule_source_sha256") == SCHEDULE_SHA256
             and manifest.get("capture_sha256") == CAPTURE_SHA256 and _sha(CAPTURE.read_bytes()) == CAPTURE_SHA256
             and manifest.get("counts", {}).get("lanes") == LANES,
             "selected successor source binding differs")
    schedule_module = _load(SCHEDULE, SCHEDULE_SHA256, "selected schedule")
    descriptor_path = root / "selected-schedule.json"
    descriptor_raw = descriptor_path.read_bytes()
    descriptor = _json(descriptor_path, "selected successor schedule")
    verified = schedule_module.verify_selected_schedule(descriptor=descriptor, plan_root=manifest["plan_root"],
                                                        expected_plan_sha256=manifest["original_plan_sha256"])
    _require(descriptor_raw == schedule_module.canonical(verified)
             and _sha(descriptor_raw) == manifest.get("selected_schedule_sha256")
             and _remaining(verified) == manifest.get("remaining_original_ordinals"),
             "selected successor schedule binding differs")
    _require(_sha((Path(manifest["plan_root"]) / "plan.json").read_bytes()) == manifest.get("original_plan_sha256")
             and _sha((Path(manifest["parallel_root"]) / "campaign-manifest.json").read_bytes()) == manifest.get("parallel_manifest_sha256"),
             "selected successor historical source binding differs")
    runtime = adapter_override or _load(RUNTIME, _sha(RUNTIME.read_bytes()), "selected successor runtime")
    parallel = _load(PARALLEL, PARALLEL_SHA256, "old parallel collector")
    helper = parallel._load(parallel.HELPER_PATH, parallel.HELPER_SHA, "old parallel helper")
    plan_root = Path(manifest["plan_root"]); route = helper.route_snapshot(Path(queue_root), manifest["route_identity"])
    ordinals = list(manifest["remaining_original_ordinals"]); _require(len(ordinals) == 958, "selected successor remaining count differs")
    threads = set(manifest["prefix"]["thread_ids"]); guard = threading.Lock(); completed: list[int] = []; failures: list[dict[str, Any]] = []

    def run(ordinal: int) -> None:
        request, prompt, schema = helper.request_payload(plan_root, ordinal)
        slot = root / "requests" / f"{ordinal:04d}"; _require(not slot.exists(), "selected successor slot already exists")
        native_output = slot / "native-output"
        _new(native_output / "payload" / "prompt.txt", prompt); _new(native_output / "payload" / "schema.json", schema)
        start = {"schema_version": 1, "state": "started", "ordinal": ordinal, "attempt": 1,
                 "prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}; start_raw = _canonical(start); _new(slot / "start.json", start_raw)
        route_raw = _canonical(route); _new(slot / "route.json", route_raw)
        source = {"manifest_sha256": _sha(_canonical(manifest)), "selected_schedule_sha256": manifest["selected_schedule_sha256"],
                  "original_plan_sha256": manifest["original_plan_sha256"], "driver_sha256": manifest["driver_sha256"],
                  "runtime_sha256": manifest["runtime_sha256"], "capture_sha256": manifest["capture_sha256"],
                  "prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}
        source_raw = _canonical(source); _new(slot / "source-bindings.json", source_raw)
        authorization = {"start_sha256": _sha(start_raw), "ordinal": ordinal, "route_sha256": _sha(route_raw),
                         "source_bindings_sha256": _sha(source_raw), "authorized_at": datetime.now(timezone.utc).isoformat(),
                         "allowance_policy": "owner_assumed_allowance_no_fresh_evidence"}
        authorization_raw = _canonical(authorization); _new(slot / "authorization.json", authorization_raw)

        def gate() -> None:
            _require(_sha(Path(__file__).read_bytes()) == manifest["driver_sha256"]
                     and _sha(RUNTIME.read_bytes()) == manifest["runtime_sha256"]
                     and _sha(CAPTURE.read_bytes()) == manifest["capture_sha256"]
                     and _sha(SCHEDULE.read_bytes()) == manifest["selected_schedule_source_sha256"]
                     and _sha((plan_root / "plan.json").read_bytes()) == manifest["original_plan_sha256"]
                     and (root / "campaign-manifest.json").read_bytes() == _canonical(manifest)
                     and descriptor_path.read_bytes() == descriptor_raw
                     and helper.route_snapshot(Path(queue_root), manifest["route_identity"]) == route
                     and (slot / "start.json").read_bytes() == start_raw
                     and (slot / "route.json").read_bytes() == route_raw
                     and (slot / "source-bindings.json").read_bytes() == source_raw
                     and (slot / "authorization.json").read_bytes() == authorization_raw
                     and (native_output / "payload" / "prompt.txt").read_bytes() == prompt
                     and (native_output / "payload" / "schema.json").read_bytes() == schema,
                     "selected successor precontact binding differs")

        try:
            content, record = runtime.call_codex(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high",
                                                 prompt=prompt.decode("utf-8"), output_dir=native_output,
                                                 response_schema=native_output / "payload" / "schema.json",
                                                 batch_number=request["batch_number"], timeout=300, attempt_number=1,
                                                 before_provider_attempt=gate, receipt_root=slot / "process-completion")
            _new(slot / "response.json", content.encode("utf-8"))
            _new(slot / "provider-record.json", _canonical(record))
            thread_id, validated = _validated_completion(slot, request, runtime)
            with guard:
                _require(thread_id not in threads, "selected successor native identity duplicates")
                threads.add(thread_id)
            _new(slot / "terminal.json", _canonical({"schema_version": 1, "state": validated["completion_class"], "ordinal": ordinal,
                                                        "thread_id": thread_id, "response_sha256": _sha(content.encode("utf-8")),
                                                        "identity_evidence": "requested_only", "provider_attested": False}))
            with guard:
                completed.append(ordinal)
        except BaseException as error:
            if not (slot / "terminal.json").exists():
                _new(slot / "terminal.json", _canonical({"schema_version": 1, "state": "stopped_no_retry", "ordinal": ordinal,
                                                            "error_type": type(error).__name__}))
            raise

    existing = {ordinal for ordinal in ordinals
                if (root / "requests" / f"{ordinal:04d}").exists()
                and _completed(root, helper.request_payload(plan_root, ordinal)[0], threads,
                               runtime=runtime, manifest_sha256=_sha(_canonical(manifest)))}
    pending: dict[Any, int] = {}; next_index = 0; stopped = False
    with ThreadPoolExecutor(max_workers=LANES) as pool:
        while next_index < len(ordinals) or pending:
            while not stopped and len(pending) < LANES and next_index < len(ordinals):
                if stop_path is not None and Path(stop_path).exists():
                    stopped = True; break
                ordinal = ordinals[next_index]; next_index += 1
                if ordinal not in existing:
                    pending[pool.submit(run, ordinal)] = ordinal
            if not pending:
                break
            done, _ignored = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                ordinal = pending.pop(future)
                try:
                    future.result()
                except Exception as error:  # noqa: BLE001 - retain only the type and drain other owned calls.
                    stopped = True; failures.append({"ordinal": ordinal, "error_type": type(error).__name__})
    return {"state": "stopped_no_retry" if failures else ("stopped_by_control" if stopped else "collected"),
            "completed_ordinals": sorted(completed), "skipped_ordinals": sorted(existing), "failures": sorted(failures, key=lambda item: item["ordinal"]),
            "lanes": LANES, "full_study_admitted": False}


def dispatch(*, campaign_root: Path, queue_root: Path, adapter_override: Any | None = None,
             stop_path: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); lock = root / ".collect.lock"; token = uuid.uuid4().hex.encode("ascii")
    _require(not lock.exists(), "selected successor collection lock exists")
    _new(lock, token)
    try:
        return _dispatch_locked(campaign_root=root, queue_root=queue_root, adapter_override=adapter_override, stop_path=stop_path)
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
