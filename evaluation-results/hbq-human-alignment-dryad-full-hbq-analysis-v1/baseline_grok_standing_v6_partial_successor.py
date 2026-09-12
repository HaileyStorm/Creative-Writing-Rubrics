"""Append-only successor after the r3 wave completed nine native peers.

The consumed r3 controller and candidate remain immutable evidence.  This
controller starts a new root at ordinal 266 and keeps the shared route's
authorized cap while serializing this caller until the reviewed host fix lands.
"""
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
from typing import Any

ROOT = Path(__file__).resolve().parent
SERIALIZED = ROOT / "baseline_grok_standing_v6_serialized_continuation.py"
SERIALIZED_SHA = "4b94a01fd03fef94a8243d672e7714fab7d7ff8634fa75b0aa21f2585905d309"
PARTIAL_RECONCILIATION_SHA = "8ed665d219881b69da55b597a403322aecd62cab054d284902cf497f7d696515"
HOST_DIAGNOSIS = Path(r"C:\Users\Haile\Documents\Codex\2026-08-12\universal-harness\work\grok-v6-host-slot-operationalerror-diagnosis-20260912\diagnosis.json")
HOST_DIAGNOSIS_SHA = "f59d2753bab6c57144e76e791a40c734d5295336253842267da7fad3b995e452"
PENDING = [266, *range(272, 1611), *range(4049, 4739)]
PEER_ORDINALS = [262, 263, 264, 265, 267, 268, 269, 270, 271]
OPERATIONAL_WAVE_CAP = 1
_HASH = re.compile(r"[0-9a-f]{64}")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object")
    return value


def _time(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _need(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _base() -> Any:
    raw = SERIALIZED.read_bytes()
    _need(_sha(raw) == SERIALIZED_SHA, "serialized v6 controller differs")
    spec = importlib.util.spec_from_file_location("_partial_successor_serialized", SERIALIZED)
    _need(spec is not None and spec.loader is not None, "serialized v6 controller load")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(SERIALIZED.read_bytes() == raw, "serialized v6 controller changed")
    return module


def _partial(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    value = _json(path, "r3 partial reconciliation")
    required = {
        "schema_version", "state", "root", "controller_sha256", "manifest_sha256",
        "candidate_manifest_sha256", "completed_provider_outcomes", "native_peers", "uncontacted", "remaining_ordinals",
        "remaining_logical_count", "new_operation_authority", "automatic_resend",
        "local_recovery_ordinals", "logical_prefix_including_prior_local_recoveries",
        "native_peer_verdict_count", "coverage_floor", "inventory", "inventory_sha256",
        "supervisor_result", "independent_review", "recorded_at", "whole_wave_replay_exists",
    }
    _need(_sha(raw) == expected == PARTIAL_RECONCILIATION_SHA and set(value) == required, "r3 partial reconciliation differs")
    _need(value.get("state") == "nine_native_peers_replayed_one_definitely_not_contacted" and value.get("controller_sha256") == SERIALIZED_SHA and value.get("candidate_manifest_sha256") == "f366f37dcb5d22cddc23e38a3e89f66d4a2b49cdcbceb97363601c897739e896" and value.get("automatic_resend") is False and value.get("new_operation_authority") is False, "r3 partial reconciliation state differs")
    root = Path(value["root"])
    _need(_sha((root / "standing-v6-continuation-manifest.json").read_bytes()) == value.get("manifest_sha256") and value.get("remaining_ordinals") == PENDING and value.get("remaining_logical_count") == len(PENDING) == 2030 and value.get("local_recovery_ordinals") == [70, 254] and value.get("logical_prefix_including_prior_local_recoveries") == 270 and value.get("completed_provider_outcomes") == 9 and value.get("native_peer_verdict_count") == 72 and value.get("independent_review", {}).get("all_native_identities_unique_against_prior259") is True, "r3 partial reconciliation schedule differs")
    peers = value.get("native_peers")
    _need(isinstance(peers, list) and [item.get("ordinal") for item in peers if isinstance(item, Mapping)] == PEER_ORDINALS and len(peers) == len(PEER_ORDINALS), "r3 partial peer ownership differs")
    uncontacted = value.get("uncontacted")
    _need(isinstance(uncontacted, Mapping) and uncontacted.get("ordinal") == 266 and uncontacted.get("contact_admitted") is True and uncontacted.get("provider_contact") is False and isinstance(uncontacted.get("terminal"), Mapping), "r3 ordinal 266 differs")
    terminal = uncontacted["terminal"]
    _need(_sha(Path(terminal["path"]).read_bytes()) == terminal["sha256"] and _json(Path(terminal["path"]), "r3 ordinal 266 terminal").get("state") == "definitely_not_contacted", "r3 ordinal 266 terminal differs")
    for peer in peers:
        _need(isinstance(peer, Mapping) and isinstance(peer.get("terminal"), Mapping) and isinstance(peer.get("authorization"), Mapping) and isinstance(peer.get("native_identity"), Mapping), "r3 peer descriptor differs")
        terminal = peer["terminal"]
        authorization = peer["authorization"]
        _need(_sha(Path(terminal["path"]).read_bytes()) == terminal["sha256"] and _sha(Path(authorization["path"]).read_bytes()) == authorization["sha256"], "r3 peer source drift")
    return value


def _diagnosis() -> dict[str, Any]:
    raw = HOST_DIAGNOSIS.read_bytes()
    value = _json(HOST_DIAGNOSIS, "host slot diagnosis")
    _need(_sha(raw) == HOST_DIAGNOSIS_SHA and value.get("decision") == "high_confidence_sqlite_writer_lock_contention_exact_statement_unproven" and value.get("supported_concurrency", {}).get("only_self_contention_free_caller_setting") == 1 and value.get("smallest_remedy", {}).get("ordinal266_automatic_resend") is False, "host slot diagnosis differs")
    return value


def _source_roots(partial: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    roots: dict[str, dict[str, Any]] = {}
    for peer in partial["native_peers"]:
        ordinal = peer["ordinal"]
        terminal = peer["terminal"]
        roots[str(ordinal)] = {"root": partial["root"], "terminal": {"path": terminal["path"], "sha256": terminal["sha256"]}, "authorization": dict(peer["authorization"])}
    return roots


def _manifest(root: Path, expected: str | None = None) -> tuple[dict[str, Any], bytes]:
    path = root / "standing-v6-partial-successor-manifest.json"
    raw, value = path.read_bytes(), _json(path, "v6 partial successor manifest")
    required = {
        "schema_version", "evidence_class", "controller_sha256", "serialized_controller", "candidate",
        "packet", "standing_source", "queue", "prefix", "partial_reconciliation",
        "terminal_source_roots", "pending_ordinals", "operational_wave_cap", "temporary_workaround",
        "provider_calls_made", "execution_authority",
    }
    _need((expected is None or _sha(raw) == expected) and set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "dryad_grok_standing_v6_partial_successor_v1" and value.get("controller_sha256") == _sha(Path(__file__).read_bytes()) and value.get("serialized_controller") == {"path": str(SERIALIZED.resolve()), "sha256": SERIALIZED_SHA} and value.get("pending_ordinals") == PENDING and value.get("operational_wave_cap") == OPERATIONAL_WAVE_CAP and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False, "v6 partial successor manifest differs")
    workaround = value.get("temporary_workaround")
    _need(isinstance(workaround, Mapping) and workaround == {"kind": "caller_wave_serialization", "incident_key": "91755a065e8f991033b7e0315a3c8a2bf153168e16fe27122264b6630153801b", "diagnosis": {"path": str(HOST_DIAGNOSIS), "sha256": HOST_DIAGNOSIS_SHA}, "removal_gate": "reviewed_shared_host_fix_and_independent_route_candidate_binding_in_a_new_source_version"}, "v6 partial successor workaround differs")
    return value, raw


def _peer_context(manifest: Mapping[str, Any]) -> tuple[Any, Any, Any, Path, dict[int, Any], Mapping[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    base = _base()
    partial = _partial(Path(manifest["partial_reconciliation"]["path"]), manifest["partial_reconciliation"]["sha256"])
    _need(manifest["terminal_source_roots"] == _source_roots(partial), "r3 terminal source root map differs")
    candidate, _candidate_manifest = base._candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
    _e33, prefix = base._prefix(manifest["prefix"]["descriptor"])
    _need(prefix["source"] == manifest["prefix"]["source"] and prefix["protected_paths"] == manifest["prefix"]["protected_paths"], "v6 partial successor prefix changed")
    _e33, parent, plan_root, requests, epoch, protected = base._prefix_context({"prefix": manifest["prefix"]})
    runtime = parent._runtime_from_epoch(epoch)
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]
    passes = parent._pass_index(plan)
    broker = candidate.Broker(Path(manifest["queue"]["path"]))
    identities = [*protected]
    request_ids = {item["request_id_hash"] for item in identities}
    session_ids = {item["session_id_hash"] for item in identities}
    records: list[dict[str, Any]] = []
    for peer in partial["native_peers"]:
        ordinal = peer["ordinal"]
        terminal_path = Path(peer["terminal"]["path"])
        terminal = _json(terminal_path, "r3 native peer terminal")
        identity, verdicts, _descriptor = base._semantic_replay_terminal(candidate=candidate, broker=broker, terminal=terminal, terminal_path=terminal_path, parent=parent, runtime=runtime, plan_root=plan_root, passes=passes, requests=requests)
        _need(identity == peer["native_identity"] and identity["request_id_hash"] not in request_ids and identity["session_id_hash"] not in session_ids and len(verdicts) == peer["verdict_count"], "r3 peer semantic replay differs")
        identities.append(identity)
        request_ids.add(identity["request_id_hash"])
        session_ids.add(identity["session_id_hash"])
        records.append({"ordinal": ordinal, "terminal_sha256": peer["terminal"]["sha256"], "native_identity": base._public_identity(identity), "question_ids": list(requests[ordinal]["question_ids"]), "verdicts": verdicts, "owner_root": manifest["terminal_source_roots"][str(ordinal)]})
    return base, candidate, parent, plan_root, requests, epoch, identities, records


def prepare_standing_v6_continuation(*, continuation_root: Path, local_prefix: Mapping[str, Any], candidate_root: Path, expected_candidate_manifest_sha256: str, packet_path: Path, expected_packet_sha256: str, standing_source_path: Path, expected_standing_source_sha256: str, queue_root: Path, expected_queue_root_hash: str, partial_reconciliation_path: Path, expected_partial_reconciliation_sha256: str) -> dict[str, Any]:
    base = _base()
    candidate_root = Path(candidate_root).resolve()
    base._candidate(candidate_root, expected_candidate_manifest_sha256)
    base._packet(Path(packet_path), expected_packet_sha256, Path(standing_source_path), expected_standing_source_sha256)
    base._standing(Path(standing_source_path), expected_standing_source_sha256)
    _diagnosis()
    partial = _partial(Path(partial_reconciliation_path), expected_partial_reconciliation_sha256)
    _need(expected_queue_root_hash == "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a", "v6 queue root hash differs")
    _e33, prefix = base._prefix(local_prefix)
    root = Path(continuation_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _need(not any(root.iterdir()), "v6 partial successor root must be fresh")
    queue_path = str(Path(queue_root).resolve())
    value = {
        "schema_version": 1, "evidence_class": "dryad_grok_standing_v6_partial_successor_v1", "controller_sha256": _sha(Path(__file__).read_bytes()),
        "serialized_controller": {"path": str(SERIALIZED.resolve()), "sha256": SERIALIZED_SHA},
        "candidate": {"root": str(candidate_root), "manifest_sha256": expected_candidate_manifest_sha256},
        "packet": {"path": str(Path(packet_path).resolve()), "sha256": expected_packet_sha256},
        "standing_source": {"path": str(Path(standing_source_path).resolve()), "sha256": expected_standing_source_sha256},
        "queue": {"path": queue_path, "root_hash": expected_queue_root_hash, "path_sha256": _sha(queue_path.encode())},
        "prefix": {"descriptor": dict(local_prefix), "source": prefix["source"], "protected_paths": prefix["protected_paths"]},
        "partial_reconciliation": {"path": str(Path(partial_reconciliation_path).resolve()), "sha256": expected_partial_reconciliation_sha256},
        "terminal_source_roots": _source_roots(partial), "pending_ordinals": PENDING, "operational_wave_cap": OPERATIONAL_WAVE_CAP,
        "temporary_workaround": {"kind": "caller_wave_serialization", "incident_key": "91755a065e8f991033b7e0315a3c8a2bf153168e16fe27122264b6630153801b", "diagnosis": {"path": str(HOST_DIAGNOSIS), "sha256": HOST_DIAGNOSIS_SHA}, "removal_gate": "reviewed_shared_host_fix_and_independent_route_candidate_binding_in_a_new_source_version"},
        "provider_calls_made": 0, "execution_authority": False,
    }
    _new(root / "standing-v6-partial-successor-manifest.json", _canon(value))
    return {"manifest_sha256": _sha((root / "standing-v6-partial-successor-manifest.json").read_bytes()), "controller_sha256": value["controller_sha256"], "provider_calls_made": 0}


def verify_standing_v6_continuation(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    manifest, raw = _manifest(root, expected_manifest_sha256)
    _need(expected_controller_sha256 == manifest["controller_sha256"] == _sha(Path(__file__).read_bytes()), "v6 partial successor controller pin differs")
    base = _base()
    base._packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    standing = base._standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _diagnosis()
    _base_value, _candidate, _parent, _plan_root, _requests, _epoch, _identities, peers = _peer_context(manifest)
    return {"evidence_class": manifest["evidence_class"], "pending_ordinals": list(PENDING), "peer_native_replay_ordinals": PEER_ORDINALS, "peer_native_verdicts": {item["ordinal"]: {"terminal_sha256": item["terminal_sha256"], "question_ids": item["question_ids"], "verdicts": item["verdicts"]} for item in peers}, "candidate": dict(manifest["candidate"]), "packet": dict(manifest["packet"]), "standing_source": {"path": manifest["standing_source"]["path"], "sha256": manifest["standing_source"]["sha256"], "allowance_evidence": standing["allowance_evidence"], "authority_at": standing["authorization"]["authority_at"]}, "terminal_source_roots": dict(manifest["terminal_source_roots"]), "protected_paths": {"continuation_manifest": {"path": str(root / "standing-v6-partial-successor-manifest.json"), "sha256": _sha(raw)}, "controller": {"path": str(Path(__file__).resolve()), "sha256": manifest["controller_sha256"]}, "serialized_controller": dict(manifest["serialized_controller"]), "partial_reconciliation": dict(manifest["partial_reconciliation"]), "candidate": dict(manifest["candidate"]), "packet": dict(manifest["packet"]), "standing_source": dict(manifest["standing_source"]), "queue": dict(manifest["queue"])}, "provider_calls_made": 0}


def _review(path: Path, expected: str, manifest: Mapping[str, Any], manifest_raw: bytes, start_ordinal: int) -> dict[str, Any]:
    value = _json(path, "v6 partial successor review")
    raw = path.read_bytes()
    required = {
        "schema_version", "decision", "controller_sha256", "manifest_sha256", "candidate_manifest_sha256",
        "packet_sha256", "standing_source_sha256", "partial_reconciliation_sha256", "queue_root",
        "queue_root_hash", "queue_path_sha256", "route_name", "route_sha256", "route",
        "gate_evidence_path", "gate_evidence_sha256", "gate_sha256", "gate_identity", "first_ordinal",
        "operational_wave_cap", "reviewed_at", "expires_at",
    }
    queue = manifest["queue"]
    gate = _json(Path(value["gate_evidence_path"]), "v6 partial successor gate evidence") if isinstance(value.get("gate_evidence_path"), str) else {}
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1 and value.get("decision") == "approved_dryad_grok_standing_v6_partial_successor_wave" and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("manifest_sha256") == _sha(manifest_raw) and value.get("candidate_manifest_sha256") == manifest["candidate"]["manifest_sha256"] and value.get("packet_sha256") == manifest["packet"]["sha256"] and value.get("standing_source_sha256") == manifest["standing_source"]["sha256"] and value.get("partial_reconciliation_sha256") == manifest["partial_reconciliation"]["sha256"] and value.get("queue_root") == str(Path(queue["path"]).resolve()) and value.get("queue_root_hash") == queue["root_hash"] and value.get("queue_path_sha256") == queue["path_sha256"] and value.get("first_ordinal") == start_ordinal and value.get("operational_wave_cap") == OPERATIONAL_WAVE_CAP and isinstance(value.get("route"), Mapping) and _sha(_canon(dict(value["route"]))) == value.get("route_sha256") and value["route"].get("max_concurrency") == 10 and _sha(Path(value["gate_evidence_path"]).read_bytes()) == value.get("gate_evidence_sha256") == value.get("gate_sha256") and value.get("gate_identity") == {"provider": gate.get("provider"), "account_class": gate.get("account_class"), "contract_hash": gate.get("contract_hash"), "source_evidence_hash": gate.get("source_evidence_hash"), "state": gate.get("state")} and gate.get("state") == "healthy", "v6 partial successor review differs")
    now, reviewed, expires = datetime.now(timezone.utc), _time(value["reviewed_at"], "v6 partial successor review time"), _time(value["expires_at"], "v6 partial successor review expiry")
    _need(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "v6 partial successor review is not fresh")
    return value


def _attempt_path(root: Path, ordinal: int, name: str) -> Path:
    return root / "attempts" / f"request-{ordinal:04d}" / name


def _wave_path(root: Path, start: int, suffix: str) -> Path:
    directory = root / "replays" if suffix == "replay" else root / "waves"
    return directory / f"wave-{start:04d}-slots-01-{suffix}.json"


def _attempts(root: Path) -> dict[int, dict[str, Any] | None]:
    base = root / "attempts"
    if not base.exists():
        return {}
    result: dict[int, dict[str, Any] | None] = {}
    for item in base.iterdir():
        match = re.fullmatch(r"request-(\d{4})", item.name)
        _need(match is not None and item.is_dir() and not item.is_symlink(), "v6 partial successor attempt inventory differs")
        ordinal = int(match.group(1))
        _need(ordinal in PENDING and ordinal not in result and _attempt_path(root, ordinal, "attempt-start.json").is_file(), "v6 partial successor attempt inventory differs")
        terminal = _attempt_path(root, ordinal, "terminal.json")
        result[ordinal] = _json(terminal, "v6 partial successor terminal") if terminal.is_file() else None
    return result


def _replayed(root: Path, manifest: Mapping[str, Any], manifest_raw: bytes) -> tuple[set[int], list[dict[str, Any]]]:
    ordinals: set[int] = set()
    identities: list[dict[str, Any]] = []
    replay_dir = root / "replays"
    for path in sorted(replay_dir.glob("wave-*-slots-01-replay.json")) if replay_dir.exists() else []:
        value = _json(path, "v6 partial successor replay")
        required = {"schema_version", "evidence_class", "controller_sha256", "manifest_sha256", "candidate_manifest_sha256", "packet_sha256", "standing_source_sha256", "partial_reconciliation_sha256", "ordinals", "terminals", "native_identities", "provider_calls_made"}
        current = value.get("ordinals")
        _need(set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "source_bound_standing_v6_partial_successor_replay_v1" and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("manifest_sha256") == _sha(manifest_raw) and value.get("candidate_manifest_sha256") == manifest["candidate"]["manifest_sha256"] and value.get("packet_sha256") == manifest["packet"]["sha256"] and value.get("standing_source_sha256") == manifest["standing_source"]["sha256"] and value.get("partial_reconciliation_sha256") == manifest["partial_reconciliation"]["sha256"] and isinstance(current, list) and len(current) == 1 and current[0] in PENDING and not (ordinals & set(current)) and value.get("provider_calls_made") == 0, "v6 partial successor replay differs")
        ordinal = current[0]
        terminal = value.get("terminals")
        _need(isinstance(terminal, list) and len(terminal) == 1 and terminal[0].get("ordinal") == ordinal and terminal[0].get("terminal_sha256") == _sha(_attempt_path(root, ordinal, "terminal.json").read_bytes()), "v6 partial successor replay terminal differs")
        ordinals.add(ordinal)
        identities.extend(value["native_identities"])
    request_ids = [item.get("request_id_hash") for item in identities]
    session_ids = [item.get("session_id_hash") for item in identities]
    _need(all(isinstance(item, str) and _HASH.fullmatch(item) for item in request_ids + session_ids) and len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "v6 partial successor native identity collision")
    return ordinals, identities


def _next(records: Mapping[int, Mapping[str, Any] | None], replayed: set[int]) -> int:
    for index, ordinal in enumerate(PENDING):
        terminal = records.get(ordinal)
        if terminal is None:
            _need(not any(item in records for item in PENDING[index + 1:]) and all(item in replayed for item in PENDING[:index]), "v6 partial successor cannot skip or bypass unreplayed cell")
            return ordinal
        _need(terminal.get("state") == "completed" and ordinal in replayed, "v6 partial successor prior cell incomplete or unreplayed")
    raise ValueError("v6 partial successor has no remaining ordinal")


def _callback_error(error: BaseException) -> dict[str, Any]:
    frames = traceback.extract_tb(error.__traceback__)
    frame = frames[-1] if frames else None
    return {"source": Path(frame.filename).name if frame else "unknown", "function": frame.name if frame else "unknown", "line": frame.lineno if frame else 0, "error_type": type(error).__name__}


def _identity_is_new(identity: Mapping[str, Any], known: list[Mapping[str, Any]]) -> bool:
    return identity["request_id_hash"] not in {item["request_id_hash"] for item in known} and identity["session_id_hash"] not in {item["session_id_hash"] for item in known}


def dispatch_standing_v6_wave(*, continuation_root: Path, start_ordinal: int, wave_size: int, arming_review_path: Path, expected_arming_review_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    manifest, manifest_raw = _manifest(root)
    _need(type(start_ordinal) is int and type(wave_size) is int and wave_size == OPERATIONAL_WAVE_CAP and start_ordinal in PENDING, "v6 partial successor dispatch geometry differs")
    base = _base()
    base._candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
    base._packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    base._standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _diagnosis()
    review = _review(Path(arming_review_path), expected_arming_review_sha256, manifest, manifest_raw, start_ordinal)
    _base_value, candidate, parent, plan_root, requests, epoch, peer_identities, _peers = _peer_context(manifest)
    records, replayed, descendant_identities = _attempts(root), *_replayed(root, manifest, manifest_raw)
    _need(start_ordinal == _next(records, replayed) and not _attempt_path(root, start_ordinal, "attempt-start.json").exists(), "v6 partial successor wave is not exact next pending")
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]
    passes = parent._pass_index(plan)
    row = requests[start_ordinal]
    prompt, schema_path, question_ids = parent._request_payload(plan_root, row)
    source = parent._source_for_pass(plan_root, passes[row["pass_id"]])
    schema = json.loads(schema_path.read_bytes())
    start = {"schema_version": 1, "ordinal": start_ordinal, "v5_plan_sha256": epoch["plan_sha256"], "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "packet_sha256": manifest["packet"]["sha256"], "standing_source_sha256": manifest["standing_source"]["sha256"], "partial_reconciliation_sha256": manifest["partial_reconciliation"]["sha256"], "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"], "question_ids": question_ids, "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"], "source_sha256": source["sha256"], "wave": {"start": start_ordinal, "size": 1, "slot": 0, "ordinals": [start_ordinal]}}
    start_path = _attempt_path(root, start_ordinal, "attempt-start.json")
    _new(start_path, _canon(start))
    _new(_wave_path(root, start_ordinal, "start"), _canon({"ordinals": [start_ordinal], "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"], "operational_wave_cap": 1}))
    admitted, session_id, outcome, result, identity, callback_failure = False, None, None, None, None, None
    try:
        broker = candidate.Broker(Path(manifest["queue"]["path"]))
        def before_contact() -> None:
            nonlocal admitted, callback_failure
            try:
                _need(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"] and (root / "standing-v6-partial-successor-manifest.json").read_bytes() == manifest_raw, "v6 partial successor controller changed before contact")
                fresh_base = _base()
                fresh_base._packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
                fresh_base._standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
                _diagnosis(), _peer_context(manifest)
                fresh = _review(Path(arming_review_path), expected_arming_review_sha256, manifest, manifest_raw, start_ordinal)
                _need(fresh["route_sha256"] == review["route_sha256"] and fresh["gate_sha256"] == review["gate_sha256"] and parent._source_for_pass(plan_root, passes[row["pass_id"]]) == source, "v6 partial successor source or route changed before contact")
                _new(root / "controller-authorizations" / f"request-{start_ordinal:04d}.json", _canon({"ordinal": start_ordinal, "manifest_sha256": _sha(manifest_raw), "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "review_sha256": expected_arming_review_sha256, "route_sha256": fresh["route_sha256"], "gate_sha256": fresh["gate_sha256"], "operational_wave_cap": 1}))
                admitted = True
            except Exception as error:
                callback_failure = _callback_error(error)
                raise
        session_id = str(uuid.uuid4())
        outcome = broker.run_grok_native_request(review["route_name"], {"prompt": prompt}, output_schema=schema, nonvisual_max_turns=1, session_id=session_id, expected_route_sha256=review["route_sha256"], before_contact=before_contact)
        state, result = outcome.get("state"), outcome.get("result")
        if state != "completed" or not isinstance(result, Mapping) or not admitted:
            terminal = {"schema_version": 1, "ordinal": start_ordinal, "state": state if state in {"definitely_not_contacted", "ambiguous"} else "ambiguous", "attempt_start_sha256": _sha(start_path.read_bytes()), "session_id": session_id, "broker_outcome": outcome, "contact_admitted": admitted}
            if callback_failure is not None:
                terminal["before_contact_error"] = callback_failure
            _new(_attempt_path(root, start_ordinal, "terminal.json"), _canon(terminal))
            return {"state": "stopped_no_retry", "ordinals": [start_ordinal], "completed_ordinals": [], "failures": [{"ordinal": start_ordinal, "error_type": "BrokerOutcome", "contact_admitted": admitted}], "provider_calls_made": None if terminal["state"] != "definitely_not_contacted" else 0, "completed_provider_outcomes": 0, "ambiguous_contact_ordinals": [] if terminal["state"] == "definitely_not_contacted" else [start_ordinal]}
        record = result.get("runtime")
        _need(isinstance(record, Mapping), "v6 partial successor candidate result differs")
        identity = base._native_identity({"request_id_hash": record.get("request_id_hash"), "session_id_hash": record.get("session_id_hash"), "observed_turns": record.get("observed_turns")}, "v6 partial successor native identity")
        all_identities = [*peer_identities, *descendant_identities]
        _need(_identity_is_new(identity, all_identities), "v6 partial successor native identity collision")
        normalized = parent._runtime_from_epoch(epoch).runner._normalize_batch(result.get("output"), expected_ids=question_ids, artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=f"standing-v6/{start_ordinal}", artifact_text=source["story_text"], context_texts=[], normalization_policy=parent._runtime_from_epoch(epoch).runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
        terminal = {"schema_version": 1, "ordinal": start_ordinal, "state": "completed", "attempt_start_sha256": _sha(start_path.read_bytes()), "session_id": session_id, "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "route_sha256": review["route_sha256"], "gate_identity": review["gate_identity"], "review_route": review["route"], "broker_outcome": outcome, "candidate_result": dict(result), "native_identity": identity, "verdicts": normalized}
        _new(_attempt_path(root, start_ordinal, "terminal.json"), _canon(terminal))
        return {"state": "completed_pending_replay", "ordinals": [start_ordinal], "completed_ordinals": [start_ordinal], "failures": [], "provider_calls_made": 1, "completed_provider_outcomes": 1, "ambiguous_contact_ordinals": []}
    except Exception as error:  # noqa: BLE001
        if not _attempt_path(root, start_ordinal, "terminal.json").exists():
            terminal = {"schema_version": 1, "ordinal": start_ordinal, "state": "ambiguous" if admitted else "definitely_not_contacted", "attempt_start_sha256": _sha(start_path.read_bytes()), "session_id": session_id, "broker_outcome": outcome, "error_type": type(error).__name__, "error_source": "dispatch_standing_v6_wave:cell"}
            if callback_failure is not None:
                terminal["before_contact_error"] = callback_failure
            if isinstance(result, Mapping):
                terminal["candidate_result"] = dict(result)
            if isinstance(identity, Mapping):
                terminal["native_identity"] = dict(identity)
            _new(_attempt_path(root, start_ordinal, "terminal.json"), _canon(terminal))
        completed_outcome = isinstance(outcome, Mapping) and outcome.get("state") == "completed"
        return {"state": "stopped_no_retry", "ordinals": [start_ordinal], "completed_ordinals": [], "failures": [{"ordinal": start_ordinal, "error_type": type(error).__name__, "contact_admitted": admitted}], "provider_calls_made": 1 if completed_outcome else (None if admitted else 0), "completed_provider_outcomes": 1 if completed_outcome else 0, "ambiguous_contact_ordinals": [] if completed_outcome else ([start_ordinal] if admitted else [])}


def replay_standing_v6_wave(*, continuation_root: Path, start_ordinal: int, wave_size: int) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    manifest, manifest_raw = _manifest(root)
    _need(type(start_ordinal) is int and type(wave_size) is int and wave_size == OPERATIONAL_WAVE_CAP and start_ordinal in PENDING, "v6 partial successor replay geometry differs")
    base = _base()
    base._packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    base._standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _base_value, candidate, parent, plan_root, requests, epoch, peer_identities, _peers = _peer_context(manifest)
    replayed, descendant_identities = _replayed(root, manifest, manifest_raw)
    _need(start_ordinal not in replayed, "v6 partial successor replay already exists")
    terminal_path = _attempt_path(root, start_ordinal, "terminal.json")
    terminal = _json(terminal_path, "v6 partial successor terminal")
    _need(terminal.get("candidate_manifest_sha256") == manifest["candidate"]["manifest_sha256"], "v6 partial successor terminal differs")
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]
    passes = parent._pass_index(plan)
    broker = candidate.Broker(Path(manifest["queue"]["path"]))
    identity, _normalized, descriptor = base._semantic_replay_terminal(candidate=candidate, broker=broker, terminal=terminal, terminal_path=terminal_path, parent=parent, runtime=parent._runtime_from_epoch(epoch), plan_root=plan_root, passes=passes, requests=requests)
    _need(_identity_is_new(identity, [*peer_identities, *descendant_identities]), "v6 partial successor native identity collision")
    result = {"schema_version": 1, "evidence_class": "source_bound_standing_v6_partial_successor_replay_v1", "controller_sha256": manifest["controller_sha256"], "manifest_sha256": _sha(manifest_raw), "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "packet_sha256": manifest["packet"]["sha256"], "standing_source_sha256": manifest["standing_source"]["sha256"], "partial_reconciliation_sha256": manifest["partial_reconciliation"]["sha256"], "ordinals": [start_ordinal], "terminals": [{"ordinal": start_ordinal, "terminal_sha256": _sha(terminal_path.read_bytes()), "native_envelope_sha256": descriptor["sha256"], "native_identity": identity}], "native_identities": [identity], "provider_calls_made": 0}
    _new(_wave_path(root, start_ordinal, "replay"), _canon(result))
    return result


def verify_standing_v6_replay_chain(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    manifest, manifest_raw = _manifest(root, expected_manifest_sha256)
    _need(expected_controller_sha256 == manifest["controller_sha256"] == _sha(Path(__file__).read_bytes()), "v6 partial successor controller pin differs")
    base = _base()
    base._packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    base._standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _base_value, candidate, parent, plan_root, requests, epoch, peer_identities, peers = _peer_context(manifest)
    replayed, descendant_identities = _replayed(root, manifest, manifest_raw)
    _need(len({item["request_id_hash"] for item in [*peer_identities, *descendant_identities]}) == len(peer_identities) + len(descendant_identities) and len({item["session_id_hash"] for item in [*peer_identities, *descendant_identities]}) == len(peer_identities) + len(descendant_identities), "v6 partial successor combined identity collision")
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]
    passes = parent._pass_index(plan)
    broker = candidate.Broker(Path(manifest["queue"]["path"]))
    terminals = [{"ordinal": item["ordinal"], "terminal_sha256": item["terminal_sha256"], "native_identity": item["native_identity"]} for item in peers]
    verdicts_by_ordinal = {item["ordinal"]: {"terminal_sha256": item["terminal_sha256"], "question_ids": item["question_ids"], "verdicts": item["verdicts"]} for item in peers}
    for ordinal in sorted(replayed):
        terminal_path = _attempt_path(root, ordinal, "terminal.json")
        terminal = _json(terminal_path, "v6 partial successor terminal")
        identity, normalized, _descriptor = base._semantic_replay_terminal(candidate=candidate, broker=broker, terminal=terminal, terminal_path=terminal_path, parent=parent, runtime=parent._runtime_from_epoch(epoch), plan_root=plan_root, passes=passes, requests=requests)
        terminals.append({"ordinal": ordinal, "terminal_sha256": _sha(terminal_path.read_bytes()), "native_identity": base._public_identity(identity)})
        verdicts_by_ordinal[ordinal] = {"terminal_sha256": _sha(terminal_path.read_bytes()), "question_ids": list(requests[ordinal]["question_ids"]), "verdicts": normalized}
    terminals.sort(key=lambda item: item["ordinal"])
    all_identities = [item["native_identity"] for item in terminals]
    return {"candidate_native_replay_ordinals": [item["ordinal"] for item in terminals], "candidate_native_identities": all_identities, "candidate_native_terminals": terminals, "candidate_native_verdicts": verdicts_by_ordinal, "candidate": dict(manifest["candidate"]), "packet": dict(manifest["packet"]), "standing_source": dict(manifest["standing_source"]), "queue": dict(manifest["queue"]), "terminal_source_roots": dict(manifest["terminal_source_roots"]), "owner_root_extension": {"native_peer_ordinals": PEER_ORDINALS, "descendant_pending_ordinals": list(PENDING), "partial_reconciliation": dict(manifest["partial_reconciliation"])}, "provider_calls_made": 0}
