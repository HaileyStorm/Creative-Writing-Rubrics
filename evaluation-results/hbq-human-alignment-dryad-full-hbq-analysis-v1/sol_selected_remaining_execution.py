"""Collect only the 232 never-started selected Sol requests after a reviewed prefix."""

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
PARENT = ROOT / "sol_selected_recovery_execution.py"
RUNTIME = ROOT / "sol_selected_successor_runtime.py"
COMPLETION = ROOT / "sol_retained_completion.py"
PARENT_SHA256 = "81fd1e27fbff5f5ffc5b4c7a6a94e477705d0d59c9af8149e40fd3a58d0555fe"
PARENT_MANIFEST_SHA256 = "99ecb63de1e09afa72440c41858c84d94e00b96a44bae47419d4cf390944362d"
PARENT_RESULT_SHA256 = "44e89eab82c114d568babaf66e7147a98cb2e5d54a3b6fd00902f56ca84750f8"
RUNTIME_SHA256 = "f9207bfc891831fabc5a24ab742798cb87601912065a6a61e4231810c12c5259"
LANES = 10
PARENT_PREFIX_COUNT = 1857
RECONCILED_PREFIX_COUNT = 2068
SELECTED_COUNT = 2300
RETAINED_UNKNOWN = tuple(range(4486, 4493))
REMAINING = tuple(range(4507, 4739))
PARENT_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-recovery-20260910-r1")
RECONCILIATION = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-completed-message-recovery-4486-4492-20260910-r1\reconciliation.json")
RECONCILIATION_SHA256 = "8a0860386ee148d22cf09c85b07fabf54b58a6c762ada72b166e932e1628c317"
PRECONTACT_RECOVERY = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-precontact-recovery-20260910-r1\reconciliation.json")
PRECONTACT_RECOVERY_SHA256 = "9e9e8fd23c00c4c7e4b1cf66e435543ff9a8a8fdfc2552b045510e12165f9345"
R2_ROOT = Path(r"C:\Users\Haile\Documents\cwr-dryad-sol-selected100-remaining-20260910-r2")
R2_CONTROLLER_SHA256 = "9d80c94fec1dba4f38207884a78e969d651911f6e63e4930ae64947ec6d5ec8f"
R2_MANIFEST_SHA256 = "e3343fa19ab6ec570bc65b42bdad1f6fe1a0215c1be103211e11e0b80663e9de"
R2_RESULT_SHA256 = "e6eda1c4212cf5b81e35303116eb8da9c37b2437dadbccf2a434123dbc1fc4eb"


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
    raw = Path(path).read_bytes()
    _require(_sha(raw) == expected, f"{name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"{name} cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(Path(path).read_bytes() == raw, f"{name} changed during load")
    return module


def _completed_ordinals() -> list[int]:
    return [4295, *range(4297, 4306), *range(4306, 4486), *range(4493, 4507)]


def _reconciliation(path: Path, expected_sha256: str) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    raw = Path(path).read_bytes()
    _require(_sha(raw) == expected_sha256, "completed-message reconciliation differs")
    value = _json(Path(path), "completed-message reconciliation")
    _require(value.get("evidence_class") == "selected100_sol_unchanged_completed_message_reconciliation"
             and value.get("recognized_logical_requests") == RECONCILED_PREFIX_COUNT and value.get("recognized_verdicts") == 16010
             and value.get("through_original_ordinal") == 4506 and value.get("new_completed_message_recoveries") == len(RETAINED_UNKNOWN)
             and value.get("new_rc_zero_completed_requests") == len(_completed_ordinals()) and value.get("total_unknown_exit_message_recoveries") == 17
             and value.get("unique_accepted_native_threads") == RECONCILED_PREFIX_COUNT and value.get("resend_authority") is False
             and value.get("provider_calls_this_reconciliation") == 0 and value.get("process_success_proven_for_recoveries") is False
             and value.get("original_failed_terminals_preserved") is True and value.get("full_study_admitted") is False,
             "completed-message reconciliation summary differs")
    recovered = value.get("recoveries")
    completed = value.get("completed_records")
    _require(isinstance(recovered, list) and [item.get("ordinal") for item in recovered if isinstance(item, Mapping)] == list(RETAINED_UNKNOWN)
             and isinstance(completed, list) and [item.get("ordinal") for item in completed if isinstance(item, Mapping)] == _completed_ordinals(),
             "completed-message reconciliation records differ")
    return value, {int(item["ordinal"]): dict(item) for item in completed}, {int(item["ordinal"]): dict(item) for item in recovered}


def _hash_inventory(slot: Path, files: Mapping[str, Any], label: str) -> None:
    _require(files and all(isinstance(relative, str) and relative and not Path(relative).is_absolute() and ".." not in Path(relative).parts and type(expected) is str and len(expected) == 64
                           and _sha((slot / relative).read_bytes()) == expected for relative, expected in files.items()),
             f"{label} artifact inventory differs")


def _precontact_failure(path: Path = PRECONTACT_RECOVERY, expected_sha256: str = PRECONTACT_RECOVERY_SHA256) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    _require(_sha(raw) == expected_sha256, "precontact recovery differs")
    value = _json(Path(path), "precontact recovery")
    inventory = ["authorization.json", "native-output/payload/prompt.txt", "native-output/payload/schema.json", "route.json", "source-bindings.json", "start.json", "terminal.json"]
    root_files = {"campaign-manifest.json", "collection-result.json", "independent-review.json", "launch-receipt.json", "preparation-receipt.json", "run-remaining232.py", "selected-schedule.json", "source-at-precontact-failure-provenance-only.py"}
    expected_files = root_files | {f"requests/{ordinal:04d}/{name}" for ordinal in range(4507, 4517) for name in inventory}
    files = value.get("files")
    _require(value.get("schema_version") == 1 and value.get("evidence_class") == "deterministically_uncontacted_argument_binding_failure"
             and value.get("prior_root") == str(R2_ROOT) and value.get("prior_controller_sha256") == R2_CONTROLLER_SHA256
             and value.get("prior_manifest_sha256") == R2_MANIFEST_SHA256 and value.get("prior_result_sha256") == R2_RESULT_SHA256
             and value.get("frozen_runtime_sha256") == RUNTIME_SHA256 and value.get("recognized_prefix") == RECONCILED_PREFIX_COUNT
             and value.get("affected_ordinals") == list(range(4507, 4517)) and value.get("slot_file_inventory") == inventory
             and value.get("rejected_keyword") == "request" and value.get("signature_binding_rejects_before_function_body") is True
             and value.get("provider_contacts") == 0 and value.get("model_request_resend") is False and value.get("old_attempts_preserved") is True
             and value.get("full_study_admitted") is False and isinstance(files, Mapping) and set(files) == expected_files,
             "precontact recovery summary differs")
    _require(all(isinstance(relative, str) and not Path(relative).is_absolute() and ".." not in Path(relative).parts
                     and type(expected) is str and len(expected) == 64 and _sha((R2_ROOT / relative).read_bytes()) == expected
                     for relative, expected in files.items()), "precontact recovery inventory differs")
    actual_files = {item.relative_to(R2_ROOT).as_posix() for item in R2_ROOT.rglob("*") if item.is_file()}
    _require(actual_files == expected_files, "precontact recovery file set differs")
    _require(not (R2_ROOT / ".collect.lock").exists(), "precontact recovery lock exists")
    return value


def _parent_context(*, parent_root: Path, reconciliation_path: Path, expected_reconciliation_sha256: str,
                    expected_parent_manifest_sha256: str) -> tuple[Any, Any, Any, dict[str, Any], dict[str, Any], set[str]]:
    parent_root = Path(parent_root).resolve()
    _require(not (parent_root / ".collect.lock").exists(), "parent selected collection lock exists")
    parent_manifest_raw = (parent_root / "campaign-manifest.json").read_bytes()
    _require(_sha(parent_manifest_raw) == expected_parent_manifest_sha256 == PARENT_MANIFEST_SHA256,
             "parent selected manifest differs")
    parent_manifest = _json(parent_root / "campaign-manifest.json", "parent selected manifest")
    _require(parent_manifest.get("driver_sha256") == PARENT_SHA256 and parent_manifest.get("frozen_runtime_sha256") == RUNTIME_SHA256
             and parent_manifest.get("counts", {}).get("selected_collection") == SELECTED_COUNT,
             "parent selected manifest source differs")
    parent = _load(PARENT, PARENT_SHA256, "frozen selected recovery collector")
    runtime = _load(RUNTIME, RUNTIME_SHA256, "frozen selected runtime")
    completion = _load(COMPLETION, _sha(COMPLETION.read_bytes()), "completed-message validator")
    old, frozen_runtime, prefix, _old_manifest = parent._static(
        Path(parent_manifest["old_campaign_root"]), Path(parent_manifest["prefix_replay_path"]),
        parent_manifest["prefix_replay_sha256"], Path(parent_manifest["authority_root"]))
    _require(frozen_runtime is not None and len(prefix.get("thread_ids", [])) == PARENT_PREFIX_COUNT,
             "parent selected prefix differs")
    result_raw = (parent_root / "collection-result.json").read_bytes()
    _require(_sha(result_raw) == PARENT_RESULT_SHA256, "parent selected result differs")
    result = _json(parent_root / "collection-result.json", "parent selected result")
    completed = _completed_ordinals()
    _require(result.get("state") == "stopped_no_retry" and result.get("logical_collection_count") == 2061
             and result.get("logical_collection_target") == SELECTED_COUNT and result.get("completed_ordinals") == completed
             and [item.get("ordinal") for item in result.get("failures", []) if isinstance(item, Mapping)] == list(RETAINED_UNKNOWN),
             "parent selected result differs")
    reconciliation, completed_records, recovery_records = _reconciliation(reconciliation_path, expected_reconciliation_sha256)
    _require(reconciliation.get("manifest_sha256") == expected_parent_manifest_sha256
             and reconciliation.get("collection_result_sha256") == _sha(result_raw)
             and reconciliation.get("parent_root") == str(parent_root) and reconciliation.get("previous_recognized_requests") == PARENT_PREFIX_COUNT,
             "completed-message reconciliation parent binding differs")
    plan_root = Path(parent_manifest["plan_root"])
    threads = set(prefix["thread_ids"])
    _require(len(threads) == PARENT_PREFIX_COUNT, "parent prefix identities differ")
    _adoption, _proposal, incident, _authority = parent._authority(Path(parent_manifest["authority_root"]))
    excluded = parent._old_campaign(incident, Path(parent_manifest["old_campaign_root"]))
    _require(not (threads & excluded), "old failed native identity duplicates prefix")
    reserved = set(threads) | set(excluded)
    for ordinal in completed:
        slot = parent_root / "requests" / f"{ordinal:04d}"
        _hash_inventory(slot, completed_records[ordinal].get("files", {}), "parent accepted")
        terminal = _json(slot / "terminal.json", "parent accepted terminal")
        thread_id = terminal.get("thread_id")
        _require(terminal.get("state") in {"completed", "completed_with_wrapper_warning"} and terminal.get("ordinal") == ordinal
                 and isinstance(thread_id, str) and thread_id and thread_id not in reserved, "parent accepted terminal differs")
        reserved.add(thread_id)
    threads = reserved - excluded
    for ordinal in RETAINED_UNKNOWN:
        request, _prompt, _schema = parent._request(old, plan_root, ordinal)
        slot = parent_root / "requests" / f"{ordinal:04d}"
        _hash_inventory(slot, recovery_records[ordinal].get("files", {}), "retained unknown-exit")
        source, route = _json(slot / "source-bindings.json", "retained source bindings"), _json(slot / "route.json", "retained route")
        terminal = _json(slot / "terminal.json", "retained terminal")
        _require(terminal.get("state") == "stopped_no_retry" and terminal.get("ordinal") == ordinal
                 and terminal.get("phase") == "untouched", "retained unknown-exit terminal differs")
        _content, thread_id, _record = completion.validate_completed_unknown_exit(
            slot=slot, request=request, frozen_runtime=runtime, route=route, source=source,
            expected_record=recovery_records[ordinal])
        _require(thread_id not in reserved, "retained unknown-exit native identity duplicates")
        reserved.add(thread_id); threads.add(thread_id)
    _require(len(threads) == RECONCILED_PREFIX_COUNT and all(not (parent_root / "requests" / f"{ordinal:04d}").exists() for ordinal in REMAINING),
             "reconciled parent prefix differs")
    _require(_sha((parent_root / "collection-result.json").read_bytes()) == _sha(result_raw), "parent selected result changed during validation")
    return parent, runtime, completion, parent_manifest, reconciliation, threads


def prepare_campaign(*, campaign_root: Path, parent_campaign_root: Path = PARENT_ROOT, reconciliation_path: Path = RECONCILIATION,
                     expected_reconciliation_sha256: str = RECONCILIATION_SHA256,
                     expected_parent_manifest_sha256: str = PARENT_MANIFEST_SHA256) -> dict[str, Any]:
    precontact = _precontact_failure()
    _parent, _runtime, _completion, parent_manifest, _reconciliation_value, threads = _parent_context(
        parent_root=parent_campaign_root, reconciliation_path=reconciliation_path,
        expected_reconciliation_sha256=expected_reconciliation_sha256,
        expected_parent_manifest_sha256=expected_parent_manifest_sha256)
    descriptor = (Path(parent_campaign_root).resolve() / "selected-schedule.json").read_bytes()
    root = Path(campaign_root).resolve()
    manifest = {
        "schema_version": 1,
        "evidence_class": "selected100_sol_remaining_collection_with_completed_unknown_exit_recognition_v1",
        "driver_sha256": PARENT_SHA256,
        "actual_controller_sha256": _sha(Path(__file__).read_bytes()),
        "completion_validator_sha256": _sha(COMPLETION.read_bytes()),
        "frozen_runtime_sha256": RUNTIME_SHA256,
        "parent_campaign_root": str(Path(parent_campaign_root).resolve()),
        "parent_manifest_sha256": expected_parent_manifest_sha256,
        "parent_collection_result_sha256": _sha((Path(parent_campaign_root).resolve() / "collection-result.json").read_bytes()),
        "plan_root": parent_manifest["plan_root"], "original_plan_sha256": parent_manifest["original_plan_sha256"],
        "selected_schedule_sha256": _sha(descriptor), "old_route_identity": parent_manifest["old_route_identity"],
        "reconciliation_path": str(Path(reconciliation_path).resolve()), "reconciliation_sha256": expected_reconciliation_sha256,
        "precontact_recovery_path": str(PRECONTACT_RECOVERY.resolve()), "precontact_recovery_sha256": PRECONTACT_RECOVERY_SHA256,
        "precontact_recovery_inventory_sha256": _sha(_canonical(precontact["files"])),
        "prior_precontact_failure_root": str(R2_ROOT), "prior_precontact_failure_manifest_sha256": R2_MANIFEST_SHA256,
        "prior_precontact_failure_result_sha256": R2_RESULT_SHA256,
        "recognized_prefix_thread_ids_sha256": _sha(_canonical(sorted(threads))),
        "remaining_original_ordinals": list(REMAINING),
        "counts": {"recognized_prefix": RECONCILED_PREFIX_COUNT, "recognized_unknown_exit": len(RETAINED_UNKNOWN),
                   "remaining_requests": len(REMAINING), "selected_collection": SELECTED_COUNT, "lanes": LANES},
        "attempt_policy": {"cumulative_attempts": 1, "resend": False}, "full_study_admitted": False,
    }
    root.mkdir(parents=True, exist_ok=True)
    for name, raw in (("campaign-manifest.json", _canonical(manifest)), ("selected-schedule.json", descriptor)):
        path = root / name
        if path.exists():
            _require(path.read_bytes() == raw, f"remaining collection {name} differs")
        else:
            _new(path, raw)
    return manifest


class CompletionAwareRuntime:
    """Keep the frozen launch path intact and recognize only its retained unknown-exit completion."""

    def __init__(self, child_runtime: Any, frozen_runtime: Any, validator: Any) -> None:
        self._child_runtime, self._frozen_runtime, self._validator = child_runtime, frozen_runtime, validator

    def call_codex(self, **kwargs: Any) -> tuple[str, dict[str, Any]]:
        values = dict(kwargs)
        request = values.pop("request", None)
        _require(isinstance(request, Mapping), "remaining runtime request differs")
        try:
            return self._child_runtime.call_codex(**values)
        except ValueError:
            native = Path(values["output_dir"]).resolve()
            slot = native.parent
            content, _thread_id, record = self._validator.validate_completed_unknown_exit(
                slot=slot, request=request, frozen_runtime=self._frozen_runtime,
                route=_json(slot / "route.json", "remaining route"),
                source=_json(slot / "source-bindings.json", "remaining source bindings"))
            return content, record


def _validate_existing(root: Path, request: Mapping[str, Any], threads: set[str], *, old: Any, runtime: Any,
                       validator: Any, manifest_sha256: str) -> bool:
    ordinal = int(request["ordinal"])
    slot = root / "requests" / f"{ordinal:04d}"
    if not slot.exists():
        return False
    terminal = _json(slot / "terminal.json", "remaining terminal")
    state, thread_id = terminal.get("state"), terminal.get("thread_id")
    _require(state in {"completed", "completed_with_wrapper_warning", "completed_with_unknown_exit"}
             and isinstance(thread_id, str) and thread_id and thread_id not in threads,
             "incomplete remaining slot cannot resume")
    start_raw = (slot / "start.json").read_bytes(); route_raw = (slot / "route.json").read_bytes(); source_raw = (slot / "source-bindings.json").read_bytes()
    start, source, authorization = _json(slot / "start.json", "remaining start"), _json(slot / "source-bindings.json", "remaining source"), _json(slot / "authorization.json", "remaining authorization")
    _require(start.get("state") == "started" and start.get("ordinal") == ordinal and start.get("attempt") == 1
             and start.get("logical_attempt") == 1 and start.get("phase") == "remaining_untouched"
             and source.get("manifest_sha256") == manifest_sha256 and source.get("prompt_sha256") == request.get("prompt_sha256")
             and source.get("schema_sha256") == request.get("schema_sha256") and authorization.get("manifest_sha256") == manifest_sha256
             and authorization.get("ordinal") == ordinal and authorization.get("start_sha256") == _sha(start_raw)
             and authorization.get("route_sha256") == _sha(route_raw) and authorization.get("source_bindings_sha256") == _sha(source_raw),
             "remaining persisted binding differs")
    if state == "completed_with_unknown_exit":
        content, validated_thread, record = validator.validate_completed_unknown_exit(
            slot=slot, request=request, frozen_runtime=runtime, route=_json(slot / "route.json", "remaining route"), source=source)
        _require((slot / "response.json").read_bytes() == content.encode("utf-8")
                 and (slot / "provider-record.json").read_bytes() == _canonical(record),
                 "remaining retained completion persistence differs")
    else:
        validated_thread, record = old._validated_completion(slot, request, runtime)
    _require(validated_thread == thread_id and record.get("completion_class") == state
             and terminal.get("response_sha256") == _sha((slot / "response.json").read_bytes()),
             "remaining completed receipt differs")
    threads.add(thread_id)
    return True


def _dispatch_locked(*, campaign_root: Path, queue_root: Path, adapter_override: Any | None = None,
                     stop_path: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); manifest = _json(root / "campaign-manifest.json", "remaining manifest")
    expected_counts = {"recognized_prefix": RECONCILED_PREFIX_COUNT, "recognized_unknown_exit": len(RETAINED_UNKNOWN),
                       "remaining_requests": len(REMAINING), "selected_collection": SELECTED_COUNT, "lanes": LANES}
    _require(manifest.get("driver_sha256") == PARENT_SHA256 and manifest.get("actual_controller_sha256") == _sha(Path(__file__).read_bytes())
             and manifest.get("completion_validator_sha256") == _sha(COMPLETION.read_bytes())
             and manifest.get("frozen_runtime_sha256") == RUNTIME_SHA256 and manifest.get("remaining_original_ordinals") == list(REMAINING)
             and manifest.get("counts") == expected_counts and manifest.get("full_study_admitted") is False,
             "remaining manifest differs")
    precontact = _precontact_failure(Path(manifest.get("precontact_recovery_path", "")), manifest.get("precontact_recovery_sha256", ""))
    _require(manifest.get("precontact_recovery_inventory_sha256") == _sha(_canonical(precontact["files"]))
             and manifest.get("prior_precontact_failure_root") == str(R2_ROOT)
             and manifest.get("prior_precontact_failure_manifest_sha256") == R2_MANIFEST_SHA256
             and manifest.get("prior_precontact_failure_result_sha256") == R2_RESULT_SHA256,
             "remaining precontact recovery binding differs")
    parent, frozen_runtime, validator, _parent_manifest, _reconciliation_value, threads = _parent_context(
        parent_root=Path(manifest["parent_campaign_root"]), reconciliation_path=Path(manifest["reconciliation_path"]),
        expected_reconciliation_sha256=manifest["reconciliation_sha256"], expected_parent_manifest_sha256=manifest["parent_manifest_sha256"])
    descriptor = (root / "selected-schedule.json").read_bytes()
    parent_root = Path(manifest["parent_campaign_root"])
    _require(_sha(descriptor) == manifest.get("selected_schedule_sha256") and descriptor == (parent_root / "selected-schedule.json").read_bytes()
             and _sha((parent_root / "collection-result.json").read_bytes()) == manifest.get("parent_collection_result_sha256")
             and _sha(_canonical(sorted(threads))) == manifest.get("recognized_prefix_thread_ids_sha256"),
             "remaining prefix binding differs")
    plan_root = Path(manifest["plan_root"])
    _require(_sha((plan_root / "plan.json").read_bytes()) == manifest.get("original_plan_sha256"), "remaining plan differs")
    old = parent._load(parent.OLD, parent.OLD_SHA256, "frozen selected collector")
    parallel = old._load(old.PARALLEL, old.PARALLEL_SHA256, "frozen selected parallel collector")
    helper = parallel._load(parallel.HELPER_PATH, parallel.HELPER_SHA, "frozen selected helper")
    route = helper.route_snapshot(Path(queue_root), manifest["old_route_identity"])
    requests = {ordinal: helper.request_payload(plan_root, ordinal) for ordinal in REMAINING}
    manifest_raw = _canonical(manifest); manifest_sha256 = _sha(manifest_raw)
    active_runtime = CompletionAwareRuntime(adapter_override or frozen_runtime, frozen_runtime, validator)
    existing: set[int] = set()
    for ordinal, (request, _prompt, _schema) in requests.items():
        if (root / "requests" / f"{ordinal:04d}").exists():
            _require(_validate_existing(root, request, threads, old=old, runtime=frozen_runtime, validator=validator,
                                       manifest_sha256=manifest_sha256), "remaining existing slot differs")
            existing.add(ordinal)
    guard = threading.Lock(); completed: list[int] = []; failures: list[dict[str, Any]] = []

    def run(ordinal: int) -> None:
        request, prompt, schema = requests[ordinal]
        slot = root / "requests" / f"{ordinal:04d}"; _require(not slot.exists(), "remaining request slot already exists")
        native = slot / "native-output"; _new(native / "payload" / "prompt.txt", prompt); _new(native / "payload" / "schema.json", schema)
        start = {"schema_version": 1, "state": "started", "ordinal": ordinal, "attempt": 1, "logical_attempt": 1,
                 "phase": "remaining_untouched", "prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}
        start_raw = _canonical(start); route_raw = _canonical(route); _new(slot / "start.json", start_raw); _new(slot / "route.json", route_raw)
        source = {"manifest_sha256": manifest_sha256, "parent_driver_sha256": PARENT_SHA256, "actual_controller_sha256": manifest["actual_controller_sha256"],
                  "completion_validator_sha256": manifest["completion_validator_sha256"], "frozen_runtime_sha256": RUNTIME_SHA256,
                  "parent_manifest_sha256": manifest["parent_manifest_sha256"], "reconciliation_sha256": manifest["reconciliation_sha256"],
                  "prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)}
        source_raw = _canonical(source); _new(slot / "source-bindings.json", source_raw)
        authorization = {"schema_version": 1, "manifest_sha256": manifest_sha256, "ordinal": ordinal, "start_sha256": _sha(start_raw),
                         "route_sha256": _sha(route_raw), "source_bindings_sha256": _sha(source_raw), "authorized_at": datetime.now(timezone.utc).isoformat(),
                         "attempt_policy": manifest["attempt_policy"]}
        authorization_raw = _canonical(authorization); _new(slot / "authorization.json", authorization_raw)

        def gate() -> None:
            _require(_sha(Path(__file__).read_bytes()) == manifest["actual_controller_sha256"] and _sha(PARENT.read_bytes()) == PARENT_SHA256
                     and _sha(RUNTIME.read_bytes()) == RUNTIME_SHA256 and _sha(COMPLETION.read_bytes()) == manifest["completion_validator_sha256"]
                     and (root / "campaign-manifest.json").read_bytes() == manifest_raw and (root / "selected-schedule.json").read_bytes() == descriptor
                     and _sha((parent_root / "campaign-manifest.json").read_bytes()) == manifest["parent_manifest_sha256"]
                     and _sha((parent_root / "collection-result.json").read_bytes()) == manifest["parent_collection_result_sha256"]
                     and _sha(Path(manifest["reconciliation_path"]).read_bytes()) == manifest["reconciliation_sha256"]
                     and _sha(Path(manifest["precontact_recovery_path"]).read_bytes()) == manifest["precontact_recovery_sha256"]
                     and _sha((R2_ROOT / "campaign-manifest.json").read_bytes()) == manifest["prior_precontact_failure_manifest_sha256"]
                     and _sha((R2_ROOT / "collection-result.json").read_bytes()) == manifest["prior_precontact_failure_result_sha256"]
                     and _sha((plan_root / "plan.json").read_bytes()) == manifest["original_plan_sha256"]
                     and (slot / "start.json").read_bytes() == start_raw and (slot / "route.json").read_bytes() == route_raw
                     and (slot / "source-bindings.json").read_bytes() == source_raw and (slot / "authorization.json").read_bytes() == authorization_raw
                     and (native / "payload" / "prompt.txt").read_bytes() == prompt and (native / "payload" / "schema.json").read_bytes() == schema
                     and helper.route_snapshot(Path(queue_root), manifest["old_route_identity"]) == route,
                     "remaining precontact binding differs")

        try:
            content, record = active_runtime.call_codex(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high",
                                                        prompt=prompt.decode("utf-8"), output_dir=native, response_schema=native / "payload" / "schema.json",
                                                        batch_number=request["batch_number"], timeout=300, attempt_number=1,
                                                        before_provider_attempt=gate, receipt_root=slot / "process-completion", request=request)
            _new(slot / "response.json", content.encode("utf-8")); _new(slot / "provider-record.json", _canonical(record))
            if record.get("completion_class") == "completed_with_unknown_exit":
                retained_content, thread_id, validated = validator.validate_completed_unknown_exit(slot=slot, request=request, frozen_runtime=frozen_runtime,
                                                                                           route=route, source=source)
                _require(retained_content == content and (slot / "response.json").read_bytes() == retained_content.encode("utf-8")
                         and (slot / "provider-record.json").read_bytes() == _canonical(validated),
                         "remaining retained completion persistence differs")
            else:
                thread_id, validated = old._validated_completion(slot, request, frozen_runtime)
            with guard:
                _require(thread_id not in threads, "remaining native identity duplicates")
                threads.add(thread_id)
            _new(slot / "terminal.json", _canonical({"schema_version": 1, "state": validated["completion_class"], "ordinal": ordinal,
                                                        "thread_id": thread_id, "response_sha256": _sha(content.encode("utf-8")),
                                                        "phase": "remaining_untouched", "process_success_proven": validated.get("process_success_proven", True),
                                                        "provider_attested": False}))
            with guard:
                completed.append(ordinal)
        except BaseException as error:
            if not (slot / "terminal.json").exists():
                _new(slot / "terminal.json", _canonical({"schema_version": 1, "state": "stopped_no_retry", "ordinal": ordinal,
                                                            "phase": "remaining_untouched", "error_type": type(error).__name__}))
            raise

    pending: dict[Any, int] = {}; index = 0; stopped = False; ordinals = [item for item in REMAINING if item not in existing]
    with ThreadPoolExecutor(max_workers=LANES) as pool:
        while index < len(ordinals) or pending:
            while not stopped and len(pending) < LANES and index < len(ordinals):
                if stop_path is not None and Path(stop_path).exists():
                    stopped = True; break
                ordinal = ordinals[index]; index += 1; pending[pool.submit(run, ordinal)] = ordinal
            if not pending:
                break
            done, _ignored = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                ordinal = pending.pop(future)
                try:
                    future.result()
                except Exception as error:  # noqa: BLE001 - preserve only the error class and drain launched calls.
                    stopped = True; failures.append({"ordinal": ordinal, "error_type": type(error).__name__})
    accepted_new = len(existing) + len(completed)
    return {"state": "stopped_no_retry" if failures else ("stopped_by_control" if stopped else "collected"),
            "completed_ordinals": sorted(completed), "skipped_ordinals": sorted(existing), "failures": sorted(failures, key=lambda item: item["ordinal"]),
            "recognized_logical_requests": RECONCILED_PREFIX_COUNT + accepted_new, "logical_collection_target": SELECTED_COUNT,
            "accepted_new": accepted_new, "recognized_unknown_exit": len(RETAINED_UNKNOWN), "lanes": LANES, "full_study_admitted": False}


def dispatch(*, campaign_root: Path, queue_root: Path, adapter_override: Any | None = None,
             stop_path: Path | None = None) -> dict[str, Any]:
    root = Path(campaign_root).resolve(); lock = root / ".collect.lock"; token = uuid.uuid4().hex.encode("ascii")
    _require(not lock.exists(), "remaining collection lock exists")
    _new(lock, token)
    try:
        return _dispatch_locked(campaign_root=root, queue_root=queue_root, adapter_override=adapter_override, stop_path=stop_path)
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
