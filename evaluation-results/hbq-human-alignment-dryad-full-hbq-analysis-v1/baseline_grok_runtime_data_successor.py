"""One-cell Grok continuation after the separately adopted 279 recovery."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import traceback
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
RECOVERY = HERE / "baseline_runtime_data_recovery.py"
PENDING = [*range(280, 1611), *range(4049, 4739)]
WAVE_CAP = 1
_HASH = re.compile(r"[0-9a-f]{64}")
_CLOSURE_KEYS = {"runtime_loader", "prefix_adapter", "recovery_controller", "original_continuation",
                 "snapshot_manifest", "recovery_record", "recovery_adoption", "candidate", "packet",
                 "standing_source", "queue", "route", "gate"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(_canon(value))


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object")
    return value, raw


def _load(path: Path, expected: str) -> ModuleType:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, "runtime data successor source pin differs")
    spec = importlib.util.spec_from_file_location("_runtime_data_successor_recovery", path)
    _need(spec is not None and spec.loader is not None, "runtime data recovery load differs")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(path.read_bytes() == raw, "runtime data recovery source changed")
    return module


def _descriptor(value: Any, label: str) -> Mapping[str, Any]:
    _need(isinstance(value, Mapping) and isinstance(value.get("path"), str)
          and isinstance(value.get("sha256"), str) and _HASH.fullmatch(value["sha256"]) is not None,
          f"{label} descriptor differs")
    return value


def _bound(value: Any, label: str) -> Mapping[str, Any]:
    descriptor = _descriptor(value, label)
    try:
        raw = Path(descriptor["path"]).read_bytes()
    except OSError as error:
        raise ValueError(f"{label} source drift") from error
    _need(_sha(raw) == descriptor["sha256"], f"{label} source drift")
    return descriptor


def _manifest(root: Path, expected: str | None = None) -> tuple[dict[str, Any], bytes]:
    path = root / "runtime-data-successor-manifest.json"
    value, raw = _json(path, "runtime data successor manifest")
    required = {"schema_version", "evidence_class", "controller_sha256", "source_closure",
                "source_closure_sha256", "pending_ordinals", "operational_wave_cap", "provider_calls_made",
                "execution_authority"}
    _need((expected is None or _sha(raw) == expected) and set(value) == required
          and value.get("schema_version") == 1
          and value.get("evidence_class") == "dryad_grok_runtime_data_successor_v1"
          and value.get("controller_sha256") == _sha(Path(__file__).read_bytes())
          and value.get("pending_ordinals") == PENDING and value.get("operational_wave_cap") == WAVE_CAP
          and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False
          and isinstance(value.get("source_closure"), Mapping)
          and set(value["source_closure"]) == _CLOSURE_KEYS
          and value.get("source_closure_sha256") == _sha(_canon(value["source_closure"])),
          "runtime data successor manifest differs")
    return value, raw


def create_runtime_data_successor(*, continuation_root: Path, source_closure: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze only explicitly supplied prospective source bindings."""
    root = Path(continuation_root).resolve()
    _need(not root.exists() or (root.is_dir() and not any(root.iterdir())), "runtime data successor root is not fresh")
    _need(set(source_closure) == _CLOSURE_KEYS, "runtime data successor source closure differs")
    for name in ("runtime_loader", "prefix_adapter", "recovery_controller", "snapshot_manifest", "recovery_record",
                 "recovery_adoption", "packet", "standing_source", "gate"):
        _bound(source_closure[name], name)
    original = source_closure["original_continuation"]
    candidate, queue, route = source_closure["candidate"], source_closure["queue"], source_closure["route"]
    _need(isinstance(original, Mapping) and isinstance(original.get("root"), str)
          and isinstance(original.get("manifest_sha256"), str), "original continuation binding differs")
    _need(isinstance(candidate, Mapping) and isinstance(candidate.get("root"), str)
          and isinstance(candidate.get("manifest_sha256"), str), "candidate binding differs")
    _need(isinstance(queue, Mapping) and isinstance(queue.get("path"), str)
          and isinstance(queue.get("root_hash"), str) and isinstance(queue.get("path_sha256"), str), "queue binding differs")
    _need(isinstance(route, Mapping) and isinstance(route.get("name"), str) and isinstance(route.get("sha256"), str), "route binding differs")
    value = {"schema_version": 1, "evidence_class": "dryad_grok_runtime_data_successor_v1",
             "controller_sha256": _sha(Path(__file__).read_bytes()), "source_closure": dict(source_closure),
             "source_closure_sha256": _sha(_canon(source_closure)), "pending_ordinals": PENDING,
             "operational_wave_cap": WAVE_CAP, "provider_calls_made": 0, "execution_authority": False}
    _new(root / "runtime-data-successor-manifest.json", value)
    return value


def _adoption(recovery: ModuleType, closure: Mapping[str, Any], recovered: Mapping[str, Any]) -> dict[str, Any]:
    value, raw = _json(Path(_descriptor(closure["recovery_adoption"], "recovery adoption")["path"]), "279 recovery adoption")
    _need(_sha(raw) == closure["recovery_adoption"]["sha256"], "279 recovery adoption drift")
    required = {"schema_version", "decision", "recovery_record", "recovery_source_sha256", "loader_sha256",
                "prefix_adapter_sha256", "snapshot_manifest_sha256", "original_continuation_manifest_sha256",
                "original_terminal_sha256", "native_identity", "approved_at", "reviewer", "provider_calls_made",
                "automatic_resend_authorized"}
    record = _descriptor(closure["recovery_record"], "recovery record")
    original = closure["original_continuation"]
    _need(set(value) == required and value.get("schema_version") == 1
          and value.get("decision") == "approved_native_279_runtime_data_recovery"
          and value.get("recovery_record") == dict(record)
          and value.get("recovery_source_sha256") == closure["recovery_controller"]["sha256"]
          and value.get("loader_sha256") == closure["runtime_loader"]["sha256"]
          and value.get("prefix_adapter_sha256") == closure["prefix_adapter"]["sha256"]
          and value.get("snapshot_manifest_sha256") == closure["snapshot_manifest"]["sha256"]
          and value.get("original_continuation_manifest_sha256") == original["manifest_sha256"]
          and value.get("original_terminal_sha256") == recovered["original_terminal"]["sha256"]
          and value.get("native_identity") == recovered["native_identity"]
          and isinstance(value.get("approved_at"), str) and isinstance(value.get("reviewer"), str)
          and value.get("provider_calls_made") == 0 and value.get("automatic_resend_authorized") is False,
          "279 recovery adoption differs")
    return value


def verify_runtime_data_successor(*, continuation_root: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    manifest, raw = _manifest(root, expected_manifest_sha256)
    closure = manifest["source_closure"]
    _need(Path(closure["runtime_loader"]["path"]).resolve() == (HERE / "baseline_runtime_data_snapshot.py").resolve()
          and Path(closure["prefix_adapter"]["path"]).resolve() == (HERE / "baseline_runtime_data_prefix.py").resolve()
          and Path(closure["recovery_controller"]["path"]).resolve() == RECOVERY.resolve(),
          "runtime data successor runtime source path differs")
    for name in ("runtime_loader", "prefix_adapter", "recovery_controller", "snapshot_manifest", "recovery_record",
                 "recovery_adoption", "packet", "standing_source", "gate"):
        _bound(closure[name], name)
    recovery = _load(Path(_bound(closure["recovery_controller"], "recovery controller")["path"]), closure["recovery_controller"]["sha256"])
    original = closure["original_continuation"]
    context = recovery.build_context(
        continuation_root=Path(original["root"]), expected_manifest_sha256=original["manifest_sha256"],
        snapshot_manifest_path=Path(closure["snapshot_manifest"]["path"]),
        expected_snapshot_manifest_sha256=closure["snapshot_manifest"]["sha256"],
        expected_loader_sha256=closure["runtime_loader"]["sha256"],
        expected_prefix_adapter_sha256=closure["prefix_adapter"]["sha256"])
    _need(context.manifest["candidate"]["root"] == closure["candidate"]["root"]
          and context.manifest["candidate"]["manifest_sha256"] == closure["candidate"]["manifest_sha256"]
          and context.manifest["packet"]["sha256"] == closure["packet"]["sha256"]
          and context.manifest["standing_source"]["sha256"] == closure["standing_source"]["sha256"]
          and context.manifest["queue"]["path"] == closure["queue"]["path"]
          and context.manifest["queue"]["path_sha256"] == closure["queue"]["path_sha256"]
          and context.manifest["queue"]["root_hash"] == closure["queue"]["root_hash"],
          "runtime data successor source closure changed")
    _need(len(context.identities) == 276, "279 recovery context boundary differs")
    record, record_raw = _json(Path(closure["recovery_record"]["path"]), "recovery record")
    _need(_sha(record_raw) == closure["recovery_record"]["sha256"], "recovery record drift")
    recovered = recovery.recover_279(context=context, expected_terminal_sha256=record["original_terminal"]["sha256"],
                                     review_path=Path(record["historical_review"]["path"]),
                                     expected_review_sha256=record["historical_review"]["sha256"])
    _need(record == recovered, "recovery record semantic mismatch")
    adoption = _adoption(recovery, closure, recovered)
    prior = [*context.identities, recovered["native_identity"]]
    _need(len(prior) == 277 and _identities_unique(prior), "adopted native identity boundary differs")
    return {"manifest": manifest, "manifest_raw": raw, "context": context, "recovered": recovered,
            "adoption": adoption, "prior_identities": prior, "provider_calls_made": 0}


def _time(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _need(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _review(path: Path, expected: str, state: Mapping[str, Any], start: int) -> dict[str, Any]:
    value, raw = _json(path, "runtime data successor review")
    manifest, closure = state["manifest"], state["manifest"]["source_closure"]
    required = {"schema_version", "decision", "controller_sha256", "manifest_sha256", "source_closure_sha256",
                "recovery_record_sha256", "recovery_adoption_sha256", "first_ordinal", "operational_wave_cap",
                "route_name", "route", "route_sha256", "gate_evidence_path", "gate_evidence_sha256", "gate_sha256",
                "gate_identity", "reviewed_at", "expires_at"}
    gate = _json(Path(value["gate_evidence_path"]), "runtime data successor gate")[0] if isinstance(value.get("gate_evidence_path"), str) else {}
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1
          and value.get("decision") == "approved_dryad_grok_runtime_data_successor_wave"
          and value.get("controller_sha256") == manifest["controller_sha256"]
          and value.get("manifest_sha256") == _sha(state["manifest_raw"])
          and value.get("source_closure_sha256") == manifest["source_closure_sha256"]
          and value.get("recovery_record_sha256") == closure["recovery_record"]["sha256"]
          and value.get("recovery_adoption_sha256") == closure["recovery_adoption"]["sha256"]
          and value.get("first_ordinal") == start and value.get("operational_wave_cap") == WAVE_CAP
          and value.get("route_name") == closure["route"]["name"] and isinstance(value.get("route"), Mapping)
          and _sha(_canon(dict(value["route"]))) == value.get("route_sha256") == closure["route"]["sha256"]
          and _sha(Path(value["gate_evidence_path"]).read_bytes()) == value.get("gate_evidence_sha256") == value.get("gate_sha256") == closure["gate"]["sha256"]
          and value.get("gate_identity") == {key: gate.get(key) for key in ("provider", "account_class", "contract_hash", "source_evidence_hash", "state")}
          and gate.get("state") == "healthy", "runtime data successor review differs")
    now, reviewed, expires = datetime.now(timezone.utc), _time(value["reviewed_at"], "review time"), _time(value["expires_at"], "review expiry")
    _need(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "runtime data successor review is not fresh")
    return value


def _attempt(root: Path, ordinal: int, name: str) -> Path:
    return root / "attempts" / f"request-{ordinal:04d}" / name


def _replay(root: Path, ordinal: int) -> Path:
    return root / "replays" / f"wave-{ordinal:04d}-slots-01-replay.json"


def _records(root: Path) -> dict[int, dict[str, Any] | None]:
    base = root / "attempts"
    if not base.exists():
        return {}
    result: dict[int, dict[str, Any] | None] = {}
    for item in base.iterdir():
        match = re.fullmatch(r"request-(\d{4})", item.name)
        _need(match is not None and item.is_dir() and not item.is_symlink(), "successor attempt inventory differs")
        ordinal = int(match.group(1))
        _need(ordinal in PENDING and ordinal not in result and _attempt(root, ordinal, "attempt-start.json").is_file(), "successor attempt inventory differs")
        terminal = _attempt(root, ordinal, "terminal.json")
        result[ordinal] = _json(terminal, "successor terminal")[0] if terminal.is_file() else None
    return result


def _replayed(root: Path, state: Mapping[str, Any]) -> tuple[set[int], list[dict[str, Any]]]:
    ordinals: set[int] = set(); identities: list[dict[str, Any]] = []
    for path in sorted((root / "replays").glob("wave-*-slots-01-replay.json")) if (root / "replays").exists() else []:
        value, _raw = _json(path, "successor replay")
        required = {"schema_version", "evidence_class", "controller_sha256", "manifest_sha256", "source_closure_sha256",
                    "recovery_record_sha256", "recovery_adoption_sha256", "ordinals", "terminals", "native_identities", "provider_calls_made"}
        current = value.get("ordinals")
        _need(set(value) == required and value.get("schema_version") == 1
              and value.get("evidence_class") == "source_bound_runtime_data_successor_replay_v1"
              and value.get("controller_sha256") == state["manifest"]["controller_sha256"]
              and value.get("manifest_sha256") == _sha(state["manifest_raw"])
              and value.get("source_closure_sha256") == state["manifest"]["source_closure_sha256"]
              and value.get("recovery_record_sha256") == state["manifest"]["source_closure"]["recovery_record"]["sha256"]
              and value.get("recovery_adoption_sha256") == state["manifest"]["source_closure"]["recovery_adoption"]["sha256"]
              and isinstance(current, list) and len(current) == 1 and current[0] in PENDING and not (ordinals & set(current))
              and value.get("provider_calls_made") == 0, "successor replay differs")
        ordinal = current[0]; terminal = value.get("terminals"); native = value.get("native_identities")
        _need(isinstance(terminal, list) and len(terminal) == 1 and terminal[0].get("ordinal") == ordinal
              and terminal[0].get("terminal_sha256") == _sha(_attempt(root, ordinal, "terminal.json").read_bytes())
              and isinstance(native, list) and len(native) == 1 and isinstance(native[0], Mapping), "successor replay terminal differs")
        actual = _json(_attempt(root, ordinal, "terminal.json"), "successor terminal")[0]
        _need(actual.get("ordinal") == ordinal and actual.get("native_identity") == native[0]
              and terminal[0].get("native_identity") == native[0], "successor replay identity differs")
        ordinals.add(ordinal); identities.extend(native)
    _need(_identities_unique(identities), "successor replay native identity collision")
    return ordinals, identities


def _identities_unique(values: list[Mapping[str, Any]]) -> bool:
    request = [item.get("request_id_hash") for item in values]; sessions = [item.get("session_id_hash") for item in values]
    return all(isinstance(item, str) and _HASH.fullmatch(item) for item in request + sessions) and len(request) == len(set(request)) and len(sessions) == len(set(sessions))


def _next(records: Mapping[int, Mapping[str, Any] | None], replayed: set[int]) -> int:
    for index, ordinal in enumerate(PENDING):
        terminal = records.get(ordinal)
        if terminal is None:
            _need(not any(item in records for item in PENDING[index + 1:]) and all(item in replayed for item in PENDING[:index]), "successor cannot skip or bypass unreplayed cell")
            return ordinal
        _need(terminal.get("state") == "completed" and ordinal in replayed, "successor prior cell incomplete or unreplayed")
    raise ValueError("successor has no remaining ordinal")


def _callback_error(error: BaseException) -> dict[str, Any]:
    frames = traceback.extract_tb(error.__traceback__); frame = frames[-1] if frames else None
    return {"source": Path(frame.filename).name if frame else "unknown", "function": frame.name if frame else "unknown",
            "line": frame.lineno if frame else 0, "error_type": type(error).__name__}


def dispatch_runtime_data_successor(*, continuation_root: Path, expected_manifest_sha256: str, start_ordinal: int,
                                    wave_size: int, arming_review_path: Path, expected_arming_review_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    _need(type(start_ordinal) is int and type(wave_size) is int and wave_size == WAVE_CAP and start_ordinal in PENDING, "successor dispatch geometry differs")
    state = verify_runtime_data_successor(continuation_root=root, expected_manifest_sha256=expected_manifest_sha256)
    records, replayed, previous = _records(root), *_replayed(root, state)
    _need(_identities_unique([*state["prior_identities"], *previous]), "successor native identity collision")
    _need(start_ordinal == _next(records, replayed) and not _attempt(root, start_ordinal, "attempt-start.json").exists(), "successor dispatch is not exact next pending")
    review = _review(Path(arming_review_path), expected_arming_review_sha256, state, start_ordinal)
    context, closure, runtime = state["context"], state["manifest"]["source_closure"], state["context"].runtime
    row = context.requests[start_ordinal]; prompt, schema_path, ids = context.parent._request_payload(context.plan_root, row)
    source = context.parent._source_for_pass(context.plan_root, context.passes[row["pass_id"]]); schema = json.loads(schema_path.read_bytes())
    start = {"schema_version": 1, "ordinal": start_ordinal, "candidate_manifest_sha256": closure["candidate"]["manifest_sha256"],
             "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"], "question_ids": ids,
             "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"], "source_sha256": source["sha256"],
             "wave": {"start": start_ordinal, "size": 1, "slot": 0, "ordinals": [start_ordinal]}}
    start_path = _attempt(root, start_ordinal, "attempt-start.json"); _new(start_path, start)
    admitted = False; callback_failure: dict[str, Any] | None = None; session_id: str | None = None; outcome: Any = None; result: Any = None; identity: Any = None
    try:
        broker = context.candidate.Broker(Path(closure["queue"]["path"]))
        def before_contact() -> None:
            nonlocal admitted, callback_failure
            try:
                runtime.verify()
                _need(_sha(Path(__file__).read_bytes()) == state["manifest"]["controller_sha256"]
                      and (root / "runtime-data-successor-manifest.json").read_bytes() == state["manifest_raw"], "successor controller changed before contact")
                original = closure["original_continuation"]
                _need(_sha((Path(original["root"]) / "standing-v6-partial-successor-manifest.json").read_bytes())
                      == original["manifest_sha256"], "successor original continuation changed before contact")
                for name in ("runtime_loader", "prefix_adapter", "recovery_controller", "snapshot_manifest", "recovery_record",
                             "recovery_adoption", "packet", "standing_source", "gate"):
                    _bound(closure[name], name)
                context.base._candidate(Path(closure["candidate"]["root"]), closure["candidate"]["manifest_sha256"])
                context.base._packet(Path(closure["packet"]["path"]), closure["packet"]["sha256"],
                                     Path(closure["standing_source"]["path"]), closure["standing_source"]["sha256"])
                context.base._standing(Path(closure["standing_source"]["path"]), closure["standing_source"]["sha256"])
                fresh = _review(Path(arming_review_path), expected_arming_review_sha256, state, start_ordinal)
                fresh_source = context.parent._source_for_pass(context.plan_root, context.passes[row["pass_id"]])
                _need(fresh["route_sha256"] == review["route_sha256"] and fresh["gate_sha256"] == review["gate_sha256"] and fresh_source == source, "successor source or route changed before contact")
                _new(root / "controller-authorizations" / f"request-{start_ordinal:04d}.json", {"ordinal": start_ordinal,
                     "manifest_sha256": _sha(state["manifest_raw"]), "source_closure_sha256": state["manifest"]["source_closure_sha256"],
                     "recovery_record_sha256": closure["recovery_record"]["sha256"], "recovery_adoption_sha256": closure["recovery_adoption"]["sha256"],
                     "review_sha256": expected_arming_review_sha256, "route_sha256": fresh["route_sha256"], "gate_sha256": fresh["gate_sha256"], "operational_wave_cap": 1})
                admitted = True
            except Exception as error:
                callback_failure = _callback_error(error); raise
        session_id = str(uuid.uuid4())
        outcome = broker.run_grok_native_request(review["route_name"], {"prompt": prompt}, output_schema=schema,
                                                  nonvisual_max_turns=1, session_id=session_id,
                                                  expected_route_sha256=review["route_sha256"], before_contact=before_contact)
        result = outcome.get("result") if isinstance(outcome, Mapping) else None
        if outcome.get("state") != "completed" or not isinstance(result, Mapping) or not admitted:
            terminal = {"schema_version": 1, "ordinal": start_ordinal, "state": outcome.get("state") if isinstance(outcome, Mapping) and outcome.get("state") in {"definitely_not_contacted", "ambiguous"} else "ambiguous", "attempt_start_sha256": _sha(start_path.read_bytes()), "session_id": session_id, "broker_outcome": outcome, "contact_admitted": admitted}
            if callback_failure is not None: terminal["before_contact_error"] = callback_failure
            _new(_attempt(root, start_ordinal, "terminal.json"), terminal)
            return {"state": "stopped_no_retry", "ordinals": [start_ordinal], "completed_ordinals": [], "failures": [{"ordinal": start_ordinal, "error_type": "BrokerOutcome", "contact_admitted": admitted}], "provider_calls_made": 0 if terminal["state"] == "definitely_not_contacted" else None, "completed_provider_outcomes": 0, "ambiguous_contact_ordinals": [] if terminal["state"] == "definitely_not_contacted" else [start_ordinal]}
        record = result.get("runtime"); _need(isinstance(record, Mapping), "successor candidate result differs")
        identity = context.base._native_identity({"request_id_hash": record.get("request_id_hash"), "session_id_hash": record.get("session_id_hash"), "observed_turns": record.get("observed_turns")}, "successor native identity")
        _need(_identities_unique([*state["prior_identities"], *previous, identity]), "successor native identity collision")
        normalized = runtime.runner._normalize_batch(result.get("output"), expected_ids=ids, artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=f"standing-v6/{start_ordinal}", artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
        runtime.verify()
        terminal = {"schema_version": 1, "ordinal": start_ordinal, "state": "completed", "attempt_start_sha256": _sha(start_path.read_bytes()), "session_id": session_id, "candidate_manifest_sha256": closure["candidate"]["manifest_sha256"], "route_sha256": review["route_sha256"], "gate_identity": review["gate_identity"], "review_route": dict(review["route"]), "broker_outcome": outcome, "candidate_result": dict(result), "native_identity": identity, "verdicts": normalized}
        _new(_attempt(root, start_ordinal, "terminal.json"), terminal)
        return {"state": "completed_pending_replay", "ordinals": [start_ordinal], "completed_ordinals": [start_ordinal], "failures": [], "provider_calls_made": 1, "completed_provider_outcomes": 1, "ambiguous_contact_ordinals": []}
    except Exception as error:  # noqa: BLE001 - preserve the bounded post-contact outcome
        if not _attempt(root, start_ordinal, "terminal.json").exists():
            terminal = {"schema_version": 1, "ordinal": start_ordinal, "state": "ambiguous" if admitted else "definitely_not_contacted", "attempt_start_sha256": _sha(start_path.read_bytes()), "session_id": session_id, "broker_outcome": outcome, "error_type": type(error).__name__, "error_source": "dispatch_runtime_data_successor:cell"}
            if callback_failure is not None: terminal["before_contact_error"] = callback_failure
            if isinstance(result, Mapping): terminal["candidate_result"] = dict(result)
            if isinstance(identity, Mapping): terminal["native_identity"] = dict(identity)
            _new(_attempt(root, start_ordinal, "terminal.json"), terminal)
        completed = isinstance(outcome, Mapping) and outcome.get("state") == "completed"
        return {"state": "stopped_no_retry", "ordinals": [start_ordinal], "completed_ordinals": [], "failures": [{"ordinal": start_ordinal, "error_type": type(error).__name__, "contact_admitted": admitted}], "provider_calls_made": 1 if completed else (None if admitted else 0), "completed_provider_outcomes": 1 if completed else 0, "ambiguous_contact_ordinals": [] if completed else ([start_ordinal] if admitted else [])}


def replay_runtime_data_successor(*, continuation_root: Path, expected_manifest_sha256: str, start_ordinal: int, wave_size: int) -> dict[str, Any]:
    root = Path(continuation_root).resolve(); _need(type(start_ordinal) is int and type(wave_size) is int and wave_size == WAVE_CAP and start_ordinal in PENDING, "successor replay geometry differs")
    state = verify_runtime_data_successor(continuation_root=root, expected_manifest_sha256=expected_manifest_sha256)
    replayed, previous = _replayed(root, state); _need(start_ordinal not in replayed, "successor replay already exists")
    context, closure = state["context"], state["manifest"]["source_closure"]
    terminal_path = _attempt(root, start_ordinal, "terminal.json"); terminal = _json(terminal_path, "successor terminal")[0]
    broker = context.candidate.Broker(Path(closure["queue"]["path"]))
    identity, _normalized, descriptor = context.base._semantic_replay_terminal(candidate=context.candidate, broker=broker, terminal=terminal, terminal_path=terminal_path, parent=context.parent, runtime=context.runtime, plan_root=context.plan_root, passes=context.passes, requests=context.requests)
    _need(_identities_unique([*state["prior_identities"], *previous, identity]), "successor native identity collision")
    value = {"schema_version": 1, "evidence_class": "source_bound_runtime_data_successor_replay_v1", "controller_sha256": state["manifest"]["controller_sha256"], "manifest_sha256": _sha(state["manifest_raw"]), "source_closure_sha256": state["manifest"]["source_closure_sha256"], "recovery_record_sha256": closure["recovery_record"]["sha256"], "recovery_adoption_sha256": closure["recovery_adoption"]["sha256"], "ordinals": [start_ordinal], "terminals": [{"ordinal": start_ordinal, "terminal_sha256": _sha(terminal_path.read_bytes()), "native_envelope_sha256": descriptor["sha256"], "native_identity": identity}], "native_identities": [identity], "provider_calls_made": 0}
    context.runtime.verify()
    _new(_replay(root, start_ordinal), value)
    return value


def verify_runtime_data_replay_chain(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve(); state = verify_runtime_data_successor(continuation_root=root, expected_manifest_sha256=expected_manifest_sha256)
    _need(expected_controller_sha256 == state["manifest"]["controller_sha256"] == _sha(Path(__file__).read_bytes()), "successor controller pin differs")
    replayed, _prior_replays = _replayed(root, state); context, closure = state["context"], state["manifest"]["source_closure"]
    broker = context.candidate.Broker(Path(closure["queue"]["path"])); terminals: list[dict[str, Any]] = []; verdicts: dict[int, Any] = {}; identities = list(state["prior_identities"])
    for ordinal in sorted(replayed):
        path = _attempt(root, ordinal, "terminal.json"); terminal = _json(path, "successor terminal")[0]
        identity, normalized, _descriptor = context.base._semantic_replay_terminal(candidate=context.candidate, broker=broker, terminal=terminal, terminal_path=path, parent=context.parent, runtime=context.runtime, plan_root=context.plan_root, passes=context.passes, requests=context.requests)
        _need(_identities_unique([*identities, identity]), "successor native identity collision"); identities.append(identity)
        terminals.append({"ordinal": ordinal, "terminal_sha256": _sha(path.read_bytes()), "native_identity": identity}); verdicts[ordinal] = {"terminal_sha256": _sha(path.read_bytes()), "question_ids": list(context.requests[ordinal]["question_ids"]), "verdicts": normalized}
    context.runtime.verify()
    return {"candidate_native_replay_ordinals": sorted(replayed), "candidate_native_identities": identities, "candidate_native_terminals": terminals, "candidate_native_verdicts": verdicts, "recovered_279": state["recovered"], "adoption": state["adoption"], "provider_calls_made": 0}
