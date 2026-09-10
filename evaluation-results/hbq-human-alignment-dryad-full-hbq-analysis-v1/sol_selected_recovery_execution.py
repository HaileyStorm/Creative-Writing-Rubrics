"""Fail-closed, owner-authorized replacement collector for ten Sol transport failures."""

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

ROOT = Path(__file__).resolve().parent
OLD = ROOT / "sol_selected_successor_execution.py"
RUNTIME = ROOT / "sol_selected_successor_runtime.py"
SCHEDULE = ROOT / "baseline_selected_schedule.py"
CAPTURE = ROOT.parents[1] / "src" / "hbqrs" / "sol_process_capture.py"
AUTHORITY_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-connection-stop-20260910-r1")
OLD_SHA256 = "9f0a839ab729341c92035aaadfc58e997244e1f24afe324f1abd8434f72fbdba"
RUNTIME_SHA256 = "f9207bfc891831fabc5a24ab742798cb87601912065a6a61e4231810c12c5259"
SCHEDULE_SHA256 = "20b38d4f14415d2e61da4cc01c002aa82662814ea451e2d83133a1161b971e41"
CAPTURE_SHA256 = "d93a24580b1b492ea116514ba768bb7f7dc5a8e386c925720b434ce94c4d9cb7"
ADOPTION_SHA256 = "2cae3f1bc63d0b25a9ef8c64cbb5a06222f2f1607fb3f78dce0d7019871c89bb"
PROPOSAL_SHA256 = "19f1a54e162c20a345e4f171496eb24a84c1c7dbe2394d0ad549439dd8c94232"
INCIDENT_SHA256 = "40e35c322f91af8900940c7a8c4da640b264434d3b2a3735044e16f6f2ff0dbb"
OLD_MANIFEST_SHA256 = "99e0ed0ff4fcd303d1f86c6ebd75da385b0fafe9ffb45ce2644713e8a6c9c391"
LANES = 10
PREFIX_COUNT = 1857
SELECTED_COUNT = 2300
REPLACEMENTS = (4295, 4297, 4298, 4299, 4300, 4301, 4302, 4303, 4304, 4305)
UNTOUCHED = tuple(range(4306, 4739))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode("utf-8"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _load(path: Path, expected: str, name: str) -> Any:
    raw = path.read_bytes()
    _require(_sha(raw) == expected, f"{name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"{name} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(path.read_bytes() == raw, f"{name} changed during load")
    return module


def _authority(authority_root: Path = AUTHORITY_ROOT) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, str]]:
    root = Path(authority_root).resolve()
    paths = {"adoption": root / "owner-replacement-adoption.json", "proposal": root / "replacement-proposal.json", "incident": root / "incident.json"}
    expected = {"adoption": ADOPTION_SHA256, "proposal": PROPOSAL_SHA256, "incident": INCIDENT_SHA256}
    for name, path in paths.items():
        _require(_sha(path.read_bytes()) == expected[name], f"recovery {name} differs")
    adoption, proposal, incident = (_json(paths[name], f"recovery {name}") for name in ("adoption", "proposal", "incident"))
    _require(adoption.get("decision") == "owner_authorized_one_replacement_per_failed_ordinal"
             and adoption.get("proposal_sha256") == PROPOSAL_SHA256 and adoption.get("incident_sha256") == INCIDENT_SHA256
             and adoption.get("failed_ordinals") == list(REPLACEMENTS) and adoption.get("maximum_new_attempts_per_ordinal") == 1
             and adoption.get("replacement_class") == "owner_authorized_transport_replacement"
             and proposal.get("execution_authority") is False and proposal.get("failed_ordinals") == list(REPLACEMENTS)
             and proposal.get("incident_sha256") == INCIDENT_SHA256 and proposal.get("maximum_new_attempts_per_ordinal") == 1
             and incident.get("manifest_sha256") == OLD_MANIFEST_SHA256 and incident.get("recognized_logical_requests") == PREFIX_COUNT
             and incident.get("failed_ordinals") == list(REPLACEMENTS) and incident.get("untouched_ordinals") == list(UNTOUCHED)
             and incident.get("original_attempts_preserved") is True and incident.get("resend_authority") is False,
             "recovery authority differs")
    records = incident.get("records")
    _require(isinstance(records, list) and [record.get("ordinal") for record in records] == list(REPLACEMENTS)
             and all(record.get("final_message_exists") is False for record in records), "recovery incident records differ")
    return adoption, proposal, incident, {name: expected[name] for name in paths}


def _old_campaign(incident: Mapping[str, Any], old_root: Path) -> set[str]:
    root = Path(old_root).resolve()
    _require(_sha((root / "collection-result.json").read_bytes()) == incident.get("collection_result_sha256"),
             "old selected collection result differs")
    _require(not (root / ".collect.lock").exists(), "old selected collection lock exists")
    _require(all(not (root / "requests" / f"{ordinal:04d}").exists() for ordinal in UNTOUCHED),
             "old selected untouched slot exists")
    identities: set[str] = set()
    records = incident.get("records")
    _require(isinstance(records, list) and len(records) == len(REPLACEMENTS), "recovery incident records differ")
    for record, ordinal in zip(records, REPLACEMENTS, strict=True):
        files = record.get("files"); slot = root / "requests" / f"{ordinal:04d}"
        _require(record.get("ordinal") == ordinal and Path(record.get("slot_path", "")).resolve() == slot
                 and isinstance(files, Mapping) and files, "recovery failed slot differs")
        for relative, expected in files.items():
            _require(isinstance(relative, str) and isinstance(expected, Mapping)
                     and _sha((slot / relative).read_bytes()) == expected.get("sha256"), "recovery failed artifact differs")
        events_path = next((slot / relative for relative in files if relative.endswith(".events.jsonl")), None)
        _require(events_path is not None, "recovery failed event log differs")
        try:
            rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("recovery failed event log differs") from error
        started = {row.get("thread_id") for row in rows if isinstance(row, Mapping) and row.get("type") == "thread.started" and isinstance(row.get("thread_id"), str)}
        _require(len(started) == 1, "recovery failed native identity differs")
        identities.update(started)
    _require(len(identities) == len(REPLACEMENTS), "recovery failed native identity duplicates")
    return identities


def _prefix(path: Path, expected_sha256: str, old_root: Path, old_manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    _require(_sha(raw) == expected_sha256, "independent prefix replay differs")
    value = _json(Path(path), "independent prefix replay")
    _require(value.get("evidence_class") == "selected100_sol_stopped_successful_prefix_independent_replay"
             and value.get("recognized_logical_requests") == PREFIX_COUNT and value.get("recognized_verdicts") == 14376
             and value.get("manifest_sha256") == OLD_MANIFEST_SHA256 and value.get("collection_result_sha256") == "2d9dc66229f111311e5957696788b67a7a0e797b737c94c6a3f8506ab535cd7b"
             and value.get("prefix_replay_sha256") == "69bf33fde6bba29d715d38186b74617db8c10a54f93569e22d5fbaa57242f5de"
             and value.get("source_driver_sha256") == OLD_SHA256 and value.get("source_runtime_sha256") == RUNTIME_SHA256
             and value.get("accepted_via_existing_paths") == 1847 and value.get("new_zero_exit_completed_requests") == 515
             and value.get("old_unknown_exit_recoveries") == 10 and value.get("failed_requests") == 10
             and value.get("unique_accepted_native_threads") == PREFIX_COUNT and value.get("untouched_requests") == len(UNTOUCHED)
             and value.get("provider_calls_this_replay") == 0 and value.get("resend_authority") is False and value.get("full_study_admitted") is False,
             "independent prefix replay summary differs")
    prefix = old_manifest.get("prefix")
    _require(isinstance(prefix, Mapping) and isinstance(prefix.get("thread_ids"), list) and len(prefix["thread_ids"]) == 1342,
             "old selected prefix identities differ")
    ids = list(prefix["thread_ids"])
    records = value.get("records")
    _require(isinstance(records, list) and len(records) == 515 and value.get("new_zero_exit_completed_requests") == 515
             and len({record.get("ordinal") for record in records if isinstance(record, Mapping)}) == 515,
             "independent prefix completed inventory differs")
    for record in records:
        ordinal, files = record.get("ordinal"), record.get("files")
        _require(type(ordinal) is int and isinstance(files, Mapping) and files, "independent prefix record differs")
        slot = Path(old_root).resolve() / "requests" / f"{ordinal:04d}"
        for relative, expected in files.items():
            _require(isinstance(relative, str) and isinstance(expected, str) and len(expected) == 64
                     and _sha((slot / relative).read_bytes()) == expected, "independent prefix artifact differs")
        terminal = _json(slot / "terminal.json", "independent prefix terminal")
        thread_id = terminal.get("thread_id")
        _require(terminal.get("state") in {"completed", "completed_with_wrapper_warning"} and isinstance(thread_id, str) and thread_id,
                 "independent prefix terminal differs")
        ids.append(thread_id)
    _require(len(ids) == PREFIX_COUNT and len(set(ids)) == PREFIX_COUNT, "independent prefix identities differ")
    return {**value, "thread_ids": ids}


def _static(old_root: Path, prefix_path: Path, expected_prefix_sha256: str, authority_root: Path) -> tuple[Any, Any, dict[str, Any], dict[str, Any]]:
    old = _load(OLD, OLD_SHA256, "frozen selected collector")
    runtime = _load(RUNTIME, RUNTIME_SHA256, "frozen selected runtime")
    _require(_sha(CAPTURE.read_bytes()) == CAPTURE_SHA256 and _sha(SCHEDULE.read_bytes()) == SCHEDULE_SHA256, "frozen recovery dependency differs")
    _require(_sha(Path(old_root).resolve().joinpath("campaign-manifest.json").read_bytes()) == OLD_MANIFEST_SHA256,
             "old selected campaign manifest differs")
    _adoption, _proposal, incident, _authority_hashes = _authority(authority_root)
    _old_campaign(incident, Path(old_root))
    manifest = _json(Path(old_root).resolve() / "campaign-manifest.json", "old selected campaign manifest")
    return old, runtime, _prefix(prefix_path, expected_prefix_sha256, old_root, manifest), manifest


def prepare_campaign(*, campaign_root: Path, old_campaign_root: Path, plan_root: Path, selected_schedule: Mapping[str, Any],
                     selected_schedule_sha256: str, expected_plan_sha256: str, prefix_replay_path: Path,
                     expected_prefix_replay_sha256: str, authority_root: Path = AUTHORITY_ROOT) -> dict[str, Any]:
    _old, _runtime, prefix, old_manifest = _static(old_campaign_root, prefix_replay_path, expected_prefix_replay_sha256, authority_root)
    schedule = _load(SCHEDULE, SCHEDULE_SHA256, "frozen selected schedule")
    verified = schedule.verify_selected_schedule(descriptor=selected_schedule, plan_root=plan_root, expected_plan_sha256=expected_plan_sha256)
    _require(_sha(_canonical(verified)) == selected_schedule_sha256
             and verified.get("selected_request_ordinals") == list(range(1, 1611)) + list(range(4049, 4739)), "selected schedule differs")
    plan = Path(plan_root).resolve()
    _require(_sha((plan / "plan.json").read_bytes()) == expected_plan_sha256
             and Path(old_manifest.get("plan_root", "")).resolve() == plan
             and old_manifest.get("original_plan_sha256") == expected_plan_sha256
             and old_manifest.get("selected_schedule_sha256") == selected_schedule_sha256,
             "old selected plan or schedule differs")
    adoption, _proposal, _incident, authority = _authority(authority_root)
    manifest = {
        "schema_version": 1, "evidence_class": "selected100_sol_owner_authorized_transport_recovery_v1",
        "driver_sha256": _sha(Path(__file__).read_bytes()), "frozen_collector_sha256": OLD_SHA256,
        "frozen_runtime_sha256": RUNTIME_SHA256, "capture_sha256": CAPTURE_SHA256, "selected_schedule_sha256": selected_schedule_sha256,
        "selected_schedule_source_sha256": SCHEDULE_SHA256, "old_campaign_root": str(Path(old_campaign_root).resolve()),
        "old_manifest_sha256": OLD_MANIFEST_SHA256, "old_route_identity": old_manifest.get("route_identity"),
        "plan_root": str(Path(plan_root).resolve()), "original_plan_sha256": expected_plan_sha256,
        "prefix_replay_path": str(Path(prefix_replay_path).resolve()), "prefix_replay_sha256": expected_prefix_replay_sha256,
        "prefix_thread_ids": prefix["thread_ids"], "authority_root": str(Path(authority_root).resolve()), "authority_sha256": authority,
        "replacement_ordinals": list(REPLACEMENTS), "untouched_ordinals": list(UNTOUCHED),
        "counts": {"recognized_prefix": PREFIX_COUNT, "owner_replacements": len(REPLACEMENTS), "untouched": len(UNTOUCHED), "selected_collection": SELECTED_COUNT, "lanes": LANES},
        "replacement_class": adoption["replacement_class"], "allowance_policy": "owner_assumed_allowance_no_fresh_evidence", "full_study_admitted": False,
    }
    root = Path(campaign_root).resolve(); root.mkdir(parents=True, exist_ok=True)
    for name, raw in (("campaign-manifest.json", _canonical(manifest)), ("selected-schedule.json", schedule.canonical(verified))):
        path = root / name
        if path.exists():
            _require(path.read_bytes() == raw, f"recovery {name} differs")
        else:
            _new(path, raw)
    return manifest


def _request(old: Any, plan_root: Path, ordinal: int) -> tuple[dict[str, Any], bytes, bytes]:
    parallel = old._load(old.PARALLEL, old.PARALLEL_SHA256, "frozen selected parallel collector")
    helper = parallel._load(parallel.HELPER_PATH, parallel.HELPER_SHA, "frozen selected helper")
    return helper.request_payload(plan_root, ordinal)


def _completed(root: Path, request: Mapping[str, Any], threads: set[str], *, old: Any, runtime: Any, manifest_sha256: str) -> bool:
    slot = root / "requests" / f"{int(request['ordinal']):04d}"
    if not slot.exists():
        return False
    terminal = _json(slot / "terminal.json", "recovery terminal")
    _require(terminal.get("state") in {"completed", "completed_with_wrapper_warning"}, "incomplete recovery slot cannot resume")
    start = _json(slot / "start.json", "recovery start"); source = _json(slot / "source-bindings.json", "recovery source")
    authorization = _json(slot / "authorization.json", "recovery authorization")
    ordinal = int(request["ordinal"]); replacement = ordinal in REPLACEMENTS
    _require(start.get("ordinal") == ordinal and start.get("attempt") == 1 and start.get("logical_attempt") == (2 if replacement else 1)
             and start.get("phase") == ("owner_authorized_transport_replacement" if replacement else "untouched")
             and source.get("manifest_sha256") == manifest_sha256 and authorization.get("manifest_sha256") == manifest_sha256
             and authorization.get("replacement_class") == ("owner_authorized_transport_replacement" if replacement else "untouched_fresh_collection")
             and terminal.get("phase") == start.get("phase") and terminal.get("logical_attempt") == start.get("logical_attempt")
             and terminal.get("replacement_class") == ("owner_authorized_transport_replacement" if replacement else None),
             "recovery persisted binding differs")
    return old._completed(root, request, threads, runtime=runtime, manifest_sha256=manifest_sha256)


def _dispatch_phase(*, ordinals: list[int], root: Path, plan_root: Path, queue_root: Path, manifest: Mapping[str, Any], old: Any,
                    runtime: Any, threads: set[str], stop_path: Path | None) -> tuple[list[int], list[dict[str, Any]]]:
    parallel = old._load(old.PARALLEL, old.PARALLEL_SHA256, "frozen selected parallel collector")
    helper = parallel._load(parallel.HELPER_PATH, parallel.HELPER_SHA, "frozen selected helper")
    route = helper.route_snapshot(Path(queue_root), manifest["old_route_identity"])
    manifest_raw = _canonical(manifest); descriptor_raw = (root / "selected-schedule.json").read_bytes(); threads_lock = threading.Lock()
    completed: list[int] = []; failures: list[dict[str, Any]] = []

    def run(ordinal: int) -> None:
        request, prompt, schema = helper.request_payload(plan_root, ordinal)
        slot = root / "requests" / f"{ordinal:04d}"; _require(not slot.exists(), "recovery request slot already exists")
        native = slot / "native-output"; _new(native / "payload" / "prompt.txt", prompt); _new(native / "payload" / "schema.json", schema)
        replacement = ordinal in REPLACEMENTS; phase = "owner_authorized_transport_replacement" if replacement else "untouched"
        start = {"schema_version": 1, "state": "started", "ordinal": ordinal, "attempt": 1, "logical_attempt": 2 if replacement else 1,
                 "phase": phase, "prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}
        start_raw = _canonical(start); _new(slot / "start.json", start_raw); route_raw = _canonical(route); _new(slot / "route.json", route_raw)
        source = {"manifest_sha256": _sha(manifest_raw), "old_manifest_sha256": OLD_MANIFEST_SHA256,
                  "frozen_collector_sha256": OLD_SHA256, "frozen_runtime_sha256": RUNTIME_SHA256, "capture_sha256": CAPTURE_SHA256,
                  "selected_schedule_source_sha256": SCHEDULE_SHA256, "selected_schedule_sha256": manifest["selected_schedule_sha256"],
                  "prefix_replay_sha256": manifest["prefix_replay_sha256"], "prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}
        source_raw = _canonical(source); _new(slot / "source-bindings.json", source_raw)
        authorization = {"schema_version": 1, "manifest_sha256": _sha(manifest_raw), "ordinal": ordinal, "start_sha256": _sha(start_raw),
                         "route_sha256": _sha(route_raw), "source_bindings_sha256": _sha(source_raw), "replacement_class": "owner_authorized_transport_replacement" if replacement else "untouched_fresh_collection",
                         "authority_sha256": manifest["authority_sha256"] if replacement else {}, "allowance_policy": manifest["allowance_policy"], "authorized_at": datetime.now(timezone.utc).isoformat()}
        authorization_raw = _canonical(authorization); _new(slot / "authorization.json", authorization_raw)

        def gate() -> None:
            _require(_sha(Path(__file__).read_bytes()) == manifest["driver_sha256"] and _sha(OLD.read_bytes()) == OLD_SHA256
                     and _sha(RUNTIME.read_bytes()) == RUNTIME_SHA256 and _sha(CAPTURE.read_bytes()) == CAPTURE_SHA256
                     and _sha(SCHEDULE.read_bytes()) == SCHEDULE_SHA256 and _sha((plan_root / "plan.json").read_bytes()) == manifest["original_plan_sha256"]
                     and (root / "campaign-manifest.json").read_bytes() == manifest_raw and (root / "selected-schedule.json").read_bytes() == descriptor_raw
                     and _sha(Path(manifest["prefix_replay_path"]).read_bytes()) == manifest["prefix_replay_sha256"]
                     and helper.route_snapshot(Path(queue_root), manifest["old_route_identity"]) == route
                     and (slot / "start.json").read_bytes() == start_raw and (slot / "route.json").read_bytes() == route_raw
                     and (slot / "source-bindings.json").read_bytes() == source_raw and (slot / "authorization.json").read_bytes() == authorization_raw
                     and (native / "payload" / "prompt.txt").read_bytes() == prompt and (native / "payload" / "schema.json").read_bytes() == schema,
                     "recovery precontact binding differs")
            _adoption, _proposal, incident, authority = _authority(Path(manifest["authority_root"]))
            _require(authority == manifest["authority_sha256"], "recovery authority manifest binding differs")
            _old_campaign(incident, Path(manifest["old_campaign_root"]))

        try:
            content, record = runtime.call_codex(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high", prompt=prompt.decode("utf-8"),
                                                  output_dir=native, response_schema=native / "payload" / "schema.json", batch_number=request["batch_number"],
                                                  timeout=300, attempt_number=1, before_provider_attempt=gate, receipt_root=slot / "process-completion")
            _new(slot / "response.json", content.encode("utf-8")); _new(slot / "provider-record.json", _canonical(record))
            thread_id, validated = old._validated_completion(slot, request, runtime)
            with threads_lock:
                _require(thread_id not in threads, "recovery native identity duplicates")
                threads.add(thread_id)
            _new(slot / "terminal.json", _canonical({"schema_version": 1, "state": validated["completion_class"], "ordinal": ordinal, "thread_id": thread_id,
                                                        "response_sha256": _sha(content.encode("utf-8")), "phase": phase, "logical_attempt": 2 if replacement else 1,
                                                        "replacement_class": "owner_authorized_transport_replacement" if replacement else None, "provider_attested": False}))
            with threads_lock:
                completed.append(ordinal)
        except BaseException as error:
            if not (slot / "terminal.json").exists():
                _new(slot / "terminal.json", _canonical({"schema_version": 1, "state": "stopped_no_retry", "ordinal": ordinal, "phase": phase, "error_type": type(error).__name__}))
            raise

    pending: dict[Any, int] = {}; index = 0; stopped = False
    with ThreadPoolExecutor(max_workers=LANES) as pool:
        while index < len(ordinals) or pending:
            while not stopped and len(pending) < LANES and index < len(ordinals):
                if stop_path is not None and Path(stop_path).exists():
                    stopped = True; break
                ordinal = ordinals[index]; index += 1; pending[pool.submit(run, ordinal)] = ordinal
            if not pending:
                break
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                ordinal = pending.pop(future)
                try:
                    future.result()
                except Exception as error:  # noqa: BLE001 - retain only a non-sensitive error type and drain submitted work.
                    stopped = True; failures.append({"ordinal": ordinal, "error_type": type(error).__name__})
    if stopped and not failures:
        failures.append({"ordinal": None, "error_type": "StoppedByControl"})
    return sorted(completed), sorted(failures, key=lambda item: (-1 if item["ordinal"] is None else item["ordinal"]))


def _dispatch_locked(*, campaign_root: Path, queue_root: Path, adapter_override: Any | None = None, stop_path: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); manifest = _json(root / "campaign-manifest.json", "recovery manifest")
    _require(manifest.get("driver_sha256") == _sha(Path(__file__).read_bytes()) and manifest.get("frozen_collector_sha256") == OLD_SHA256
             and manifest.get("frozen_runtime_sha256") == RUNTIME_SHA256 and manifest.get("capture_sha256") == CAPTURE_SHA256
             and manifest.get("replacement_ordinals") == list(REPLACEMENTS) and manifest.get("untouched_ordinals") == list(UNTOUCHED)
             and manifest.get("counts", {}).get("selected_collection") == SELECTED_COUNT, "recovery manifest differs")
    schedule = _load(SCHEDULE, SCHEDULE_SHA256, "frozen selected schedule")
    descriptor_raw = (root / "selected-schedule.json").read_bytes(); descriptor = _json(root / "selected-schedule.json", "recovery selected schedule")
    verified = schedule.verify_selected_schedule(descriptor=descriptor, plan_root=manifest["plan_root"], expected_plan_sha256=manifest["original_plan_sha256"])
    _require(descriptor_raw == schedule.canonical(verified) and _sha(descriptor_raw) == manifest["selected_schedule_sha256"],
             "recovery selected schedule differs")
    old, frozen_runtime, prefix, _old_manifest = _static(Path(manifest["old_campaign_root"]), Path(manifest["prefix_replay_path"]), manifest["prefix_replay_sha256"], Path(manifest["authority_root"]))
    runtime = adapter_override or frozen_runtime; plan_root = Path(manifest["plan_root"]); manifest_sha = _sha(_canonical(manifest)); threads = set(prefix["thread_ids"])
    _adoption, _proposal, incident, authority = _authority(Path(manifest["authority_root"]))
    _require(authority == manifest.get("authority_sha256"), "recovery authority manifest binding differs")
    failed_threads = _old_campaign(incident, Path(manifest["old_campaign_root"]))
    _require(not (threads & failed_threads), "failed original native identity duplicates prefix")
    threads.update(failed_threads)
    ordinals = list(REPLACEMENTS) + list(UNTOUCHED)
    existing: list[int] = []
    for ordinal in ordinals:
        request, _prompt, _schema = _request(old, plan_root, ordinal)
        if (root / "requests" / f"{ordinal:04d}").exists():
            _require(_completed(root, request, threads, old=old, runtime=runtime, manifest_sha256=manifest_sha), "recovery existing slot differs")
            existing.append(ordinal)
    phase1 = [item for item in REPLACEMENTS if item not in existing]
    completed1, failures1 = _dispatch_phase(ordinals=phase1, root=root, plan_root=plan_root, queue_root=queue_root, manifest=manifest, old=old, runtime=runtime, threads=threads, stop_path=stop_path)
    if failures1:
        return {"state": "stopped_no_retry", "phase": "owner_authorized_transport_replacement", "completed_ordinals": completed1, "skipped_ordinals": existing, "failures": failures1,
                "logical_collection_count": PREFIX_COUNT + len(existing) + len(completed1), "logical_collection_target": SELECTED_COUNT, "full_study_admitted": False}
    phase2 = [item for item in UNTOUCHED if item not in existing]
    completed2, failures2 = _dispatch_phase(ordinals=phase2, root=root, plan_root=plan_root, queue_root=queue_root, manifest=manifest, old=old, runtime=runtime, threads=threads, stop_path=stop_path)
    return {"state": "stopped_no_retry" if failures2 else "collected", "phase": "untouched", "completed_ordinals": completed1 + completed2,
            "skipped_ordinals": existing, "failures": failures2, "logical_collection_count": PREFIX_COUNT + len(existing) + len(completed1) + len(completed2),
            "logical_collection_target": SELECTED_COUNT, "full_study_admitted": False}


def dispatch(*, campaign_root: Path, queue_root: Path, adapter_override: Any | None = None, stop_path: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); lock = root / ".collect.lock"; token = uuid.uuid4().hex.encode("ascii")
    _require(not lock.exists(), "recovery collection lock exists")
    _new(lock, token)
    try:
        return _dispatch_locked(campaign_root=root, queue_root=queue_root, adapter_override=adapter_override, stop_path=stop_path)
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
