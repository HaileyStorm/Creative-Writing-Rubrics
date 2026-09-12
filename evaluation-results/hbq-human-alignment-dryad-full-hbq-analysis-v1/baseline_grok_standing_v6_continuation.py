"""Prospective v6-runtime continuation after the verified v5/local prefix.

The candidate transport name remains ``grok_nonvisual_history_v5``.  This
module never substitutes the candidate for the frozen v5 runtime or replays a
v6 result through the v5 parser.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
import threading
import uuid
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
E33 = ROOT / "baseline_grok_selected_local_continuation.py"
PARENT = ROOT / "baseline_grok_v5_suffix.py"
E33_SHA = "e33e5c9276cdcdcdf22f4182787fae97d3a9f6315b6ff1dbac66f29148731e7a"
PARENT_SHA = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
CANDIDATE_MANIFEST_SHA = "f366f37dcb5d22cddc23e38a3e89f66d4a2b49cdcbceb97363601c897739e896"
PACKET_SHA = "585e9ce443cc9302b606f6c945a13b95b035a389fea89e701c20c15ba7793e2c"
STANDING_SHA = "15a5abcbb7c9745a04be9c0c13c3066a484841c610288374868bdf82a4387eaa"
MAX_WAVE = 10
PENDING = [*range(262, 1611), *range(4049, 4739)]
_HASH = re.compile(r"[0-9a-f]{64}")


def _sha(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def _canon(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
def _need(value: bool, message: str) -> None:
    if not value: raise ValueError(message)
def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output: output.write(raw)
def _json(path: Path, label: str) -> dict[str, Any]:
    try: value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object"); return value
def _time(value: Any, label: str) -> datetime:
    try: parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error: raise ValueError(f"{label} differs") from error
    _need(parsed.tzinfo is not None, f"{label} differs"); return parsed.astimezone(timezone.utc)
def _load(path: Path, expected: str, label: str) -> Any:
    raw = path.read_bytes(); _need(_sha(raw) == expected, f"{label} differs")
    spec = importlib.util.spec_from_file_location(f"_standing_v6_{label}", path)
    _need(spec is not None and spec.loader is not None, f"{label} load")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    _need(path.read_bytes() == raw, f"{label} changed"); return module


def _native_identity(value: Any, label: str) -> dict[str, Any]:
    fields = {"request_id_hash", "session_id_hash", "observed_turns"}
    _need(isinstance(value, Mapping) and set(value) == fields, f"{label} differs")
    result = dict(value)
    _need(all(isinstance(result[key], str) and _HASH.fullmatch(result[key]) for key in ("request_id_hash", "session_id_hash")) and type(result["observed_turns"]) is int and result["observed_turns"] == 1, f"{label} differs")
    return result


def _public_identity(value: Any) -> dict[str, str]:
    identity = _native_identity(value, "v6 candidate native identity")
    return {key: identity[key] for key in ("request_id_hash", "session_id_hash")}
def _inventory(root: Path) -> dict[str, str]:
    _need(root.is_dir() and not root.is_symlink(), "root differs")
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        _need(not path.is_symlink(), "root contains link")
        if path.is_file(): result[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
    return dict(sorted(result.items()))


def _candidate(root: Path, expected: str) -> tuple[Any, dict[str, Any]]:
    manifest_path = root / "candidate-manifest.json"; raw = manifest_path.read_bytes(); value = _json(manifest_path, "candidate manifest")
    _need(_sha(raw) == expected == CANDIDATE_MANIFEST_SHA and value.get("schema_version") == 7 and value.get("kind") == "complete_candidate_runtime_probe_set", "candidate manifest differs")
    files = value.get("files"); _need(isinstance(files, list) and value.get("explicit_exclusion") == ["candidate-manifest.json"], "candidate file inventory differs")
    expected_files = {item["path"]: item["sha256"] for item in files if isinstance(item, Mapping) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str)}
    _need(len(expected_files) == len(files) and _inventory(root) == {"candidate-manifest.json": _sha(raw), **expected_files}, "candidate root drift")
    broker_path = root / "model_work_queue" / "broker.py"; broker_sha = expected_files.get("model_work_queue/broker.py")
    _need(isinstance(broker_sha, str), "candidate broker missing")
    package = root / "model_work_queue" / "__init__.py"; package_name = "_standing_v6_" + _sha(str(root).encode())[:16]; package_spec = importlib.util.spec_from_file_location(package_name, package, submodule_search_locations=[str(package.parent)])
    _need(package_spec is not None and package_spec.loader is not None, "candidate package load")
    previous_bytecode = sys.dont_write_bytecode; sys.dont_write_bytecode = True
    try:
        package_module = importlib.util.module_from_spec(package_spec); sys.modules[package_spec.name] = package_module; package_spec.loader.exec_module(package_module)
        spec = importlib.util.spec_from_file_location(package_name + ".broker", broker_path)
        _need(spec is not None and spec.loader is not None, "candidate broker load")
        module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous_bytecode
    _need(_sha(broker_path.read_bytes()) == broker_sha and hasattr(module, "Broker"), "candidate broker changed")
    return module, value


def _packet(path: Path, expected: str, standing_path: Path, standing_expected: str) -> dict[str, Any]:
    raw, value = path.read_bytes(), _json(path, "v6 final packet")
    _need(_sha(raw) == expected == PACKET_SHA and set(value) == {"schema_version", "kind", "candidate_manifest", "files", "state", "activation_authority", "provider_contact_count"} and value.get("state") == "provider_free_sealed" and value.get("activation_authority") is False and value.get("provider_contact_count") == 0, "v6 final packet differs")
    candidate = value["candidate_manifest"]; _need(candidate.get("sha256") == CANDIDATE_MANIFEST_SHA, "packet candidate differs")
    files = {item.get("path"): item.get("sha256") for item in value["files"] if isinstance(item, Mapping)}
    _need(files.get("standing-source-evidence.json") == standing_expected and _sha(standing_path.read_bytes()) == standing_expected, "packet standing source differs")
    return value


def _standing(path: Path, expected: str) -> dict[str, Any]:
    value = _json(path, "standing authority source"); raw = path.read_bytes(); auth = value.get("authorization"); scope = auth.get("scope") if isinstance(auth, Mapping) else None
    _need(_sha(raw) == expected == STANDING_SHA and value.get("schema_version") == 3 and value.get("allowance_evidence") == "owner_authorized_standing_zero_charge_assumption_v1" and value.get("allowance_state") == "available" and isinstance(auth, Mapping) and isinstance(scope, Mapping) and auth.get("authority_at") == "2026-09-09T19:00:18.842739+00:00" and scope.get("first_untouched_ordinal") == 262 and scope.get("max_concurrency") == 10 and scope.get("timeout_seconds") == 300 and scope.get("nonvisual_max_turns") == 1 and scope.get("nonvisual_transport_contract") == "grok_nonvisual_history_v5" and scope.get("zero_charge_only") is True and scope.get("paid_fallback") is False and scope.get("automatic_resend") is False and scope.get("image_input") is False, "standing authority source differs")
    return value


def _prefix(descriptor: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    required = {"root", "manifest_sha256", "controller_sha256"}; _need(set(descriptor) == required and descriptor.get("controller_sha256") == E33_SHA, "v5/local prefix descriptor differs")
    e33 = _load(E33, E33_SHA, "e33 controller")
    verified = e33.verify_local_continuation(continuation_root=Path(descriptor["root"]), expected_manifest_sha256=descriptor["manifest_sha256"], expected_controller_sha256=descriptor["controller_sha256"])
    _need(verified.get("ordinal") == 254 and verified.get("provider_calls_made") == 0 and verified.get("ownership", {}).get("local_recovery_ordinals") == [70, 254], "v5/local prefix verification differs")
    return e33, verified


def _manifest(root: Path, expected: str | None = None) -> tuple[dict[str, Any], bytes]:
    path = root / "standing-v6-continuation-manifest.json"; raw, value = path.read_bytes(), _json(path, "v6 continuation manifest")
    required = {"schema_version", "evidence_class", "controller_sha256", "e33_sha256", "parent_sha256", "candidate", "packet", "standing_source", "queue", "prefix", "pending_ordinals", "provider_calls_made", "execution_authority"}
    _need((expected is None or _sha(raw) == expected) and set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "dryad_grok_standing_v6_prospective_continuation_v1" and value.get("controller_sha256") == _sha(Path(__file__).read_bytes()) and value.get("e33_sha256") == E33_SHA and value.get("parent_sha256") == PARENT_SHA and value.get("pending_ordinals") == PENDING and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False, "v6 continuation manifest differs")
    return value, raw


def prepare_standing_v6_continuation(*, continuation_root: Path, local_prefix: Mapping[str, Any], candidate_root: Path, expected_candidate_manifest_sha256: str, packet_path: Path, expected_packet_sha256: str, standing_source_path: Path, expected_standing_source_sha256: str, queue_root: Path, expected_queue_root_hash: str) -> dict[str, Any]:
    e33, prefix = _prefix(local_prefix); candidate_root = Path(candidate_root).resolve(); _candidate(candidate_root, expected_candidate_manifest_sha256); _packet(Path(packet_path), expected_packet_sha256, Path(standing_source_path), expected_standing_source_sha256); _standing(Path(standing_source_path), expected_standing_source_sha256)
    root = Path(continuation_root).resolve(); root.mkdir(parents=True, exist_ok=True); _need(not any(root.iterdir()), "v6 continuation root must be fresh")
    prefix_manifest, _ = e33._manifest(Path(local_prefix["root"]), local_prefix["manifest_sha256"])
    _need(expected_queue_root_hash == "a993de5a057f9d3c2df510619720e91c2df8fbbc5fc9c8494fc0bab33b57227a", "v6 queue root hash differs")
    queue_path = str(Path(queue_root).resolve())
    value = {"schema_version": 1, "evidence_class": "dryad_grok_standing_v6_prospective_continuation_v1", "controller_sha256": _sha(Path(__file__).read_bytes()), "e33_sha256": E33_SHA, "parent_sha256": PARENT_SHA, "candidate": {"root": str(candidate_root), "manifest_sha256": expected_candidate_manifest_sha256}, "packet": {"path": str(Path(packet_path).resolve()), "sha256": expected_packet_sha256}, "standing_source": {"path": str(Path(standing_source_path).resolve()), "sha256": expected_standing_source_sha256}, "queue": {"path": queue_path, "root_hash": expected_queue_root_hash, "path_sha256": _sha(queue_path.encode())}, "prefix": {"descriptor": dict(local_prefix), "source": prefix["source"], "protected_paths": prefix["protected_paths"], "e33_manifest": {"path": str(Path(local_prefix["root"]) / "local-continuation-manifest.json"), "sha256": local_prefix["manifest_sha256"]}, "successor_root": prefix_manifest["successor_root"], "inner_epoch_sha256": prefix_manifest["inner_epoch"]["sha256"]}, "pending_ordinals": PENDING, "provider_calls_made": 0, "execution_authority": False}
    _new(root / "standing-v6-continuation-manifest.json", _canon(value)); return {"manifest_sha256": _sha((root / "standing-v6-continuation-manifest.json").read_bytes()), "controller_sha256": value["controller_sha256"], "provider_calls_made": 0}


def verify_standing_v6_continuation(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve(); manifest, raw = _manifest(root, expected_manifest_sha256)
    _need(expected_controller_sha256 == manifest["controller_sha256"] == _sha(Path(__file__).read_bytes()), "v6 controller pin differs")
    _candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
    _packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    standing = _standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _e33, prefix = _prefix(manifest["prefix"]["descriptor"])
    _need(prefix["source"] == manifest["prefix"]["source"] and prefix["protected_paths"] == manifest["prefix"]["protected_paths"], "v5/local prefix changed")
    return {"evidence_class": manifest["evidence_class"], "pending_ordinals": list(PENDING), "prefix": prefix, "candidate": dict(manifest["candidate"]), "packet": dict(manifest["packet"]), "standing_source": {"path": manifest["standing_source"]["path"], "sha256": manifest["standing_source"]["sha256"], "allowance_evidence": standing["allowance_evidence"], "authority_at": standing["authorization"]["authority_at"]}, "protected_paths": {"continuation_manifest": {"path": str(root / "standing-v6-continuation-manifest.json"), "sha256": _sha(raw)}, "controller": {"path": str(Path(__file__).resolve()), "sha256": manifest["controller_sha256"]}, "candidate": dict(manifest["candidate"]), "packet": dict(manifest["packet"]), "standing_source": dict(manifest["standing_source"]), "queue": dict(manifest["queue"])}, "provider_calls_made": 0}


def _review(path: Path, expected: str, manifest: Mapping[str, Any], manifest_raw: bytes) -> dict[str, Any]:
    value = _json(path, "v6 arming review"); raw = path.read_bytes()
    required = {"schema_version", "decision", "controller_sha256", "manifest_sha256", "candidate_manifest_sha256", "packet_sha256", "standing_source_sha256", "queue_root", "queue_root_hash", "queue_path_sha256", "route_name", "route_sha256", "route", "gate_evidence_path", "gate_evidence_sha256", "gate_sha256", "gate_identity", "reviewed_at", "expires_at"}
    queue = manifest["queue"]; actual_queue = str(Path(queue["path"]).resolve()); gate = _json(Path(value["gate_evidence_path"]), "v6 reviewed gate evidence") if isinstance(value.get("gate_evidence_path"), str) else {}
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1 and value.get("decision") == "approved_dryad_grok_standing_v6_untouched_wave" and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("manifest_sha256") == _sha(manifest_raw) and value.get("candidate_manifest_sha256") == manifest["candidate"]["manifest_sha256"] and value.get("packet_sha256") == manifest["packet"]["sha256"] and value.get("standing_source_sha256") == manifest["standing_source"]["sha256"] and value.get("queue_root") == actual_queue and value.get("queue_root_hash") == queue["root_hash"] and value.get("queue_path_sha256") == _sha(actual_queue.encode()) and isinstance(value.get("route_name"), str) and isinstance(value.get("route"), Mapping) and _sha(_canon(dict(value["route"]))) == value.get("route_sha256") and _sha(Path(value["gate_evidence_path"]).read_bytes()) == value.get("gate_evidence_sha256") == value.get("gate_sha256") and value.get("gate_identity") == {"provider": gate.get("provider"), "account_class": gate.get("account_class"), "contract_hash": gate.get("contract_hash"), "source_evidence_hash": gate.get("source_evidence_hash"), "state": gate.get("state")} and gate.get("state") == "healthy", "v6 arming review differs")
    now, reviewed, expires = datetime.now(timezone.utc), _time(value["reviewed_at"], "v6 review time"), _time(value["expires_at"], "v6 review expiry")
    _need(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "v6 arming review is not fresh")
    return value


def _prefix_context(manifest: Mapping[str, Any]) -> tuple[Any, Any, Path, dict[int, Any], Mapping[str, Any], list[dict[str, str]]]:
    e33, _prefix_value = _prefix(manifest["prefix"]["descriptor"])
    prefix_manifest, _raw = e33._manifest(Path(manifest["prefix"]["descriptor"]["root"]), manifest["prefix"]["descriptor"]["manifest_sha256"])
    _successor, parent, _source, _epoch_raw, plan_root, requests, partial = e33._source_guard(prefix_manifest)
    epoch, _raw_epoch = parent._load_epoch(Path(prefix_manifest["successor_root"]), prefix_manifest["inner_epoch"]["sha256"])
    return e33, parent, plan_root, requests, epoch, e33._identity(partial["all_protected_native_identities"])


def _attempt_path(root: Path, ordinal: int, name: str) -> Path: return root / "attempts" / f"request-{ordinal:04d}" / name
def _wave_path(root: Path, start: int, size: int, suffix: str) -> Path: return root / "waves" / f"wave-{start:04d}-slots-{size:02d}-{suffix}.json"
def _attempts(root: Path) -> dict[int, dict[str, Any] | None]:
    base = root / "attempts"
    if not base.exists(): return {}
    result: dict[int, dict[str, Any] | None] = {}
    for item in base.iterdir():
        match = re.fullmatch(r"request-(\d{4})", item.name); _need(match is not None and item.is_dir() and not item.is_symlink(), "v6 attempt inventory differs")
        ordinal = int(match.group(1)); _need(ordinal in PENDING and ordinal not in result and _attempt_path(root, ordinal, "attempt-start.json").is_file(), "v6 attempt inventory differs")
        terminal = _attempt_path(root, ordinal, "terminal.json"); result[ordinal] = _json(terminal, "v6 terminal") if terminal.is_file() else None
    return result
def _next(records: Mapping[int, Mapping[str, Any] | None], replayed: set[int]) -> int:
    for index, ordinal in enumerate(PENDING):
        terminal = records.get(ordinal)
        if terminal is None:
            _need(not any(item in records for item in PENDING[index + 1:]) and all(item in replayed for item in PENDING[:index]), "v6 continuation cannot skip or bypass unreplayed cell")
            return ordinal
        _need(terminal.get("state") == "completed" and ordinal in replayed, "v6 prior cell incomplete or unreplayed")
    raise ValueError("v6 continuation has no remaining ordinal")


def _replayed(root: Path, manifest: Mapping[str, Any], manifest_raw: bytes) -> tuple[set[int], list[dict[str, Any]]]:
    ordinals: set[int] = set(); identities: list[dict[str, Any]] = []
    for path in sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else []:
        value = _json(path, "v6 replay")
        required = {"schema_version", "evidence_class", "controller_sha256", "manifest_sha256", "candidate_manifest_sha256", "packet_sha256", "standing_source_sha256", "ordinals", "terminals", "native_identities", "provider_calls_made"}
        current = value.get("ordinals")
        _need(set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "source_bound_standing_v6_candidate_replay_v1" and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("manifest_sha256") == _sha(manifest_raw) and value.get("candidate_manifest_sha256") == manifest["candidate"]["manifest_sha256"] and value.get("packet_sha256") == manifest["packet"]["sha256"] and value.get("standing_source_sha256") == manifest["standing_source"]["sha256"] and isinstance(current, list) and current and not (ordinals & set(current)) and value.get("provider_calls_made") == 0, "v6 replay differs")
        for ordinal, terminal in zip(current, value["terminals"], strict=True): _need(terminal.get("ordinal") == ordinal and terminal.get("terminal_sha256") == _sha(_attempt_path(root, ordinal, "terminal.json").read_bytes()), "v6 replay terminal differs")
        ordinals.update(current); identities.extend(_native_identity(item, "v6 replay native identity") for item in value["native_identities"])
    request_ids = [item.get("request_id_hash") for item in identities]; session_ids = [item.get("session_id_hash") for item in identities]
    _need(all(isinstance(item, str) and _HASH.fullmatch(item) for item in request_ids + session_ids) and len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "v6 native identity collision")
    return ordinals, identities


def _semantic_replay_terminal(*, candidate: Any, broker: Any, terminal: Mapping[str, Any], terminal_path: Path, parent: Any, runtime: Any, plan_root: Path, passes: Mapping[str, Any], requests: Mapping[int, Any]) -> tuple[dict[str, Any], dict[str, Any], Mapping[str, Any]]:
    result = terminal.get("candidate_result")
    _need(terminal.get("state") == "completed" and isinstance(result, Mapping), "v6 terminal differs")
    descriptor = result.get("native_envelope_artifact")
    _need(isinstance(descriptor, Mapping), "v6 envelope descriptor differs")
    envelope = broker.read_grok_native_envelope(dict(descriptor))
    _need(descriptor.get("sha256") == _sha(envelope) and descriptor.get("byte_length") == len(envelope), "v6 candidate envelope differs")
    ordinal = terminal.get("ordinal"); _need(type(ordinal) is int and ordinal in requests, "v6 terminal ordinal differs")
    row, source = requests[ordinal], parent._source_for_pass(plan_root, passes[requests[ordinal]["pass_id"]])
    prompt, schema_path, _ids = parent._request_payload(plan_root, row); schema = json.loads(schema_path.read_bytes())
    route, session_id = terminal.get("review_route"), terminal.get("session_id")
    _need(isinstance(route, Mapping) and isinstance(session_id, str) and isinstance(route.get("model"), str) and isinstance(route.get("reported_model"), str) and _sha(_canon(dict(route))) == terminal.get("route_sha256"), "v6 envelope binding differs")
    parsed = broker._parse_grok_exec_envelope(_canon({"control": {"version": 1, "state": "completed"}, "result": dict(result)}), {**dict(route), "output_schema": schema, "nonvisual_max_turns": 1}, {"prompt": prompt}, expected_session_id=session_id)
    adapter = importlib.import_module(candidate.__package__ + ".adapters.grok_exec")
    output, identity, _usage = adapter._parse_grok_envelope(envelope, model=route["model"], reported_model=route["reported_model"], session_id=session_id, schema=schema, max_turns=1, exact_turns=True)
    native_identity = _native_identity(identity, "v6 candidate native identity")
    normalized = runtime.runner._normalize_batch(output, expected_ids=row["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=f"standing-v6/{ordinal}", artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
    _need(parsed.state == "completed" and parsed.result == result and output == result.get("output") and native_identity == terminal.get("native_identity") and normalized == terminal.get("verdicts") and [item["question_id"] for item in normalized] == row["question_ids"], "v6 terminal semantic replay differs")
    return native_identity, normalized, descriptor


def dispatch_standing_v6_wave(*, continuation_root: Path, start_ordinal: int, wave_size: int, arming_review_path: Path, expected_arming_review_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve(); manifest, manifest_raw = _manifest(root)
    _need(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE and start_ordinal in PENDING, "v6 dispatch geometry differs")
    candidate, _candidate_manifest = _candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
    _packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"]); _standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    review = _review(Path(arming_review_path), expected_arming_review_sha256, manifest, manifest_raw)
    _e33, parent, plan_root, requests, epoch, protected_ids = _prefix_context(manifest); runtime = parent._runtime_from_epoch(epoch)
    records, replayed, old_ids = _attempts(root), *_replayed(root, manifest, manifest_raw)
    ordinals = PENDING[PENDING.index(start_ordinal):PENDING.index(start_ordinal) + wave_size]
    _need(len(ordinals) == wave_size and ordinals[0] == _next(records, replayed) and not any(_attempt_path(root, ordinal, "attempt-start.json").exists() for ordinal in ordinals), "v6 wave is not exact next pending")
    plan = parent._plan(plan_root, epoch["plan_sha256"])[0]; passes = parent._pass_index(plan); prepared: list[dict[str, Any]] = []
    for index, ordinal in enumerate(ordinals):
        row = requests[ordinal]; prompt, schema_path, question_ids = parent._request_payload(plan_root, row); source = parent._source_for_pass(plan_root, passes[row["pass_id"]]); schema_raw = schema_path.read_bytes(); schema = json.loads(schema_raw)
        start = {"schema_version": 1, "ordinal": ordinal, "v5_plan_sha256": epoch["plan_sha256"], "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "packet_sha256": manifest["packet"]["sha256"], "standing_source_sha256": manifest["standing_source"]["sha256"], "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"], "question_ids": question_ids, "prompt_sha256": row["prompt_sha256"], "schema_sha256": row["schema_sha256"], "source_sha256": source["sha256"], "wave": {"start": ordinals[0], "size": len(ordinals), "slot": index, "ordinals": ordinals}}
        path = _attempt_path(root, ordinal, "attempt-start.json"); _new(path, _canon(start)); prepared.append({"ordinal": ordinal, "row": row, "prompt": prompt, "schema": schema, "question_ids": question_ids, "source": source, "start": start, "start_path": path})
    _new(_wave_path(root, ordinals[0], len(ordinals), "start"), _canon({"ordinals": ordinals, "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"]}))
    stop, lock = threading.Event(), threading.Lock(); results: dict[int, dict[str, Any]] = {}; failures: list[dict[str, Any]] = []; identities = [*protected_ids, *old_ids]; request_ids = {item["request_id_hash"] for item in identities}; session_ids = {item["session_id_hash"] for item in identities}
    def cell(item: Mapping[str, Any]) -> None:
        ordinal, admitted, session_id, outcome, result, identity = item["ordinal"], False, None, None, None, None
        try:
            broker = candidate.Broker(Path(manifest["queue"]["path"]))
            def before_contact() -> None:
                nonlocal admitted
                _need(not stop.is_set() and _sha(Path(__file__).read_bytes()) == manifest["controller_sha256"] and (root / "standing-v6-continuation-manifest.json").read_bytes() == manifest_raw, "v6 controller changed before contact")
                _candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"]); _packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"]); _standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"]); _prefix_context(manifest)
                fresh = _review(Path(arming_review_path), expected_arming_review_sha256, manifest, manifest_raw); _need(fresh["route_sha256"] == review["route_sha256"] and fresh["gate_sha256"] == review["gate_sha256"] and parent._source_for_pass(plan_root, passes[item["row"]["pass_id"]]) == item["source"], "v6 source or route changed before contact")
                with lock:
                    _need(not stop.is_set(), "v6 stopped before admission"); _new(root / "controller-authorizations" / f"request-{ordinal:04d}.json", _canon({"ordinal": ordinal, "manifest_sha256": _sha(manifest_raw), "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "review_sha256": expected_arming_review_sha256, "route_sha256": fresh["route_sha256"], "gate_sha256": fresh["gate_sha256"]})); admitted = True
            session_id = str(uuid.uuid4()); outcome = broker.run_grok_native_request(review["route_name"], {"prompt": item["prompt"]}, output_schema=item["schema"], nonvisual_max_turns=1, session_id=session_id, expected_route_sha256=review["route_sha256"], before_contact=before_contact)
            state, result = outcome.get("state"), outcome.get("result")
            if state != "completed" or not isinstance(result, Mapping) or not admitted:
                with lock: stop.set()
                _new(_attempt_path(root, ordinal, "terminal.json"), _canon({"schema_version": 1, "ordinal": ordinal, "state": state if state in {"definitely_not_contacted", "ambiguous"} else "ambiguous", "attempt_start_sha256": _sha(item["start_path"].read_bytes()), "session_id": session_id, "broker_outcome": outcome, "contact_admitted": admitted}))
                with lock: failures.append({"ordinal": ordinal, "error_type": "BrokerOutcome", "contact_admitted": admitted})
                return
            native = result.get("native_envelope_artifact"); record = result.get("runtime"); _need(isinstance(native, Mapping) and isinstance(record, Mapping), "v6 candidate result differs")
            identity = _native_identity({"request_id_hash": record.get("request_id_hash"), "session_id_hash": record.get("session_id_hash"), "observed_turns": record.get("observed_turns")}, "v6 native identity")
            normalized = runtime.runner._normalize_batch(result.get("output"), expected_ids=item["question_ids"], artifact_id=item["source"]["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=f"standing-v6/{ordinal}", artifact_text=item["source"]["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
            with lock: _need(identity["request_id_hash"] not in request_ids and identity["session_id_hash"] not in session_ids, "v6 native identity collision"); identities.append(identity); request_ids.add(identity["request_id_hash"]); session_ids.add(identity["session_id_hash"])
            terminal = {"schema_version": 1, "ordinal": ordinal, "state": "completed", "attempt_start_sha256": _sha(item["start_path"].read_bytes()), "session_id": session_id, "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "route_sha256": review["route_sha256"], "gate_identity": review["gate_identity"], "review_route": review["route"], "broker_outcome": outcome, "candidate_result": dict(result), "native_identity": identity, "verdicts": normalized}; _new(_attempt_path(root, ordinal, "terminal.json"), _canon(terminal)); results[ordinal] = terminal
        except Exception as error:  # noqa: BLE001 - terminal evidence must capture every bounded local failure
            with lock: stop.set()
            if not _attempt_path(root, ordinal, "terminal.json").exists():
                terminal = {"schema_version": 1, "ordinal": ordinal, "state": "ambiguous" if admitted else "definitely_not_contacted", "attempt_start_sha256": _sha(item["start_path"].read_bytes()), "session_id": session_id, "broker_outcome": outcome, "error_type": type(error).__name__, "error_source": "dispatch_standing_v6_wave:cell"}
                if isinstance(result, Mapping): terminal["candidate_result"] = dict(result)
                if isinstance(identity, Mapping): terminal["native_identity"] = dict(identity)
                _new(_attempt_path(root, ordinal, "terminal.json"), _canon(terminal))
            with lock: failures.append({"ordinal": ordinal, "error_type": type(error).__name__, "contact_admitted": admitted})
    with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="dryad-grok-standing-v6") as executor:
        futures = [executor.submit(cell, item) for item in prepared]
        while futures:
            done, pending = wait(futures, return_when=FIRST_COMPLETED); futures = list(pending)
            for future in done: future.result()
    completed_provider_outcomes = 0
    ambiguous_contact_ordinals: list[int] = []
    for ordinal in ordinals:
        terminal = _json(_attempt_path(root, ordinal, "terminal.json"), "v6 terminal")
        outcome = terminal.get("broker_outcome")
        if isinstance(outcome, Mapping) and outcome.get("state") == "completed":
            completed_provider_outcomes += 1
        elif terminal.get("state") != "definitely_not_contacted":
            ambiguous_contact_ordinals.append(ordinal)
    return {"state": "completed_pending_replay" if not failures else "stopped_no_retry", "ordinals": ordinals, "completed_ordinals": sorted(results), "failures": sorted(failures, key=lambda item: item["ordinal"]), "provider_calls_made": None if ambiguous_contact_ordinals else completed_provider_outcomes, "completed_provider_outcomes": completed_provider_outcomes, "ambiguous_contact_ordinals": ambiguous_contact_ordinals}


def replay_standing_v6_wave(*, continuation_root: Path, start_ordinal: int, wave_size: int) -> dict[str, Any]:
    root = Path(continuation_root).resolve(); manifest, manifest_raw = _manifest(root); _need(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE and start_ordinal in PENDING, "v6 replay geometry differs")
    candidate, _candidate_manifest = _candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"]); _packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"]); _standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _e33, parent, plan_root, requests, epoch, protected_ids = _prefix_context(manifest); runtime = parent._runtime_from_epoch(epoch); plan = parent._plan(plan_root, epoch["plan_sha256"])[0]; passes = parent._pass_index(plan)
    ordinals = PENDING[PENDING.index(start_ordinal):PENDING.index(start_ordinal) + wave_size]; replayed, old_ids = _replayed(root, manifest, manifest_raw); _need(not (set(ordinals) & replayed), "v6 replay already exists")
    broker, identities, terminals = candidate.Broker(Path(manifest["queue"]["path"])), [*protected_ids, *old_ids], []
    for ordinal in ordinals:
        terminal_path = _attempt_path(root, ordinal, "terminal.json"); terminal = _json(terminal_path, "v6 terminal")
        _need(terminal.get("candidate_manifest_sha256") == manifest["candidate"]["manifest_sha256"], "v6 terminal differs")
        identity, _normalized, descriptor = _semantic_replay_terminal(candidate=candidate, broker=broker, terminal=terminal, terminal_path=terminal_path, parent=parent, runtime=runtime, plan_root=plan_root, passes=passes, requests=requests)
        _need(identity not in identities, "v6 terminal semantic replay differs"); identities.append(identity); terminals.append({"ordinal": ordinal, "terminal_sha256": _sha(terminal_path.read_bytes()), "native_envelope_sha256": descriptor["sha256"], "native_identity": identity})
    result = {"schema_version": 1, "evidence_class": "source_bound_standing_v6_candidate_replay_v1", "controller_sha256": manifest["controller_sha256"], "manifest_sha256": _sha(manifest_raw), "candidate_manifest_sha256": manifest["candidate"]["manifest_sha256"], "packet_sha256": manifest["packet"]["sha256"], "standing_source_sha256": manifest["standing_source"]["sha256"], "ordinals": ordinals, "terminals": terminals, "native_identities": [item["native_identity"] for item in terminals], "provider_calls_made": 0}
    _new(root / "replays" / f"wave-{start_ordinal:04d}-slots-{wave_size:02d}.json", _canon(result)); return result


def verify_standing_v6_replay_chain(*, continuation_root: Path, expected_manifest_sha256: str, expected_controller_sha256: str) -> dict[str, Any]:
    root = Path(continuation_root).resolve(); manifest, manifest_raw = _manifest(root, expected_manifest_sha256); _need(expected_controller_sha256 == manifest["controller_sha256"] == _sha(Path(__file__).read_bytes()), "v6 controller pin differs")
    _candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"]); _packet(Path(manifest["packet"]["path"]), manifest["packet"]["sha256"], Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"]); _standing(Path(manifest["standing_source"]["path"]), manifest["standing_source"]["sha256"])
    _e33, parent, plan_root, requests, epoch, _protected = _prefix_context(manifest); runtime = parent._runtime_from_epoch(epoch); plan = parent._plan(plan_root, epoch["plan_sha256"])[0]; passes = parent._pass_index(plan); replayed, identities = _replayed(root, manifest, manifest_raw); broker = None; terminals: list[dict[str, Any]] = []; verdicts_by_ordinal: dict[int, dict[str, Any]] = {}
    for path in sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else []:
        record = _json(path, "v6 replay record")
        for ordinal in record["ordinals"]:
            terminal_path = _attempt_path(root, ordinal, "terminal.json"); terminal = _json(terminal_path, "v6 terminal"); candidate, _ = _candidate(Path(manifest["candidate"]["root"]), manifest["candidate"]["manifest_sha256"])
            if broker is None: broker = candidate.Broker(Path(manifest["queue"]["path"]))
            identity, normalized, _descriptor = _semantic_replay_terminal(candidate=candidate, broker=broker, terminal=terminal, terminal_path=terminal_path, parent=parent, runtime=runtime, plan_root=plan_root, passes=passes, requests=requests)
            terminal_hash = _sha(terminal_path.read_bytes()); terminals.append({"ordinal": ordinal, "terminal_sha256": terminal_hash, "native_identity": _public_identity(identity)}); verdicts_by_ordinal[ordinal] = {"terminal_sha256": terminal_hash, "question_ids": list(requests[ordinal]["question_ids"]), "verdicts": normalized}
    _need([item["ordinal"] for item in terminals] == sorted(replayed), "v6 replay ownership differs")
    return {"candidate_native_replay_ordinals": sorted(replayed), "candidate_native_identities": [_public_identity(item) for item in identities], "candidate_native_terminals": terminals, "candidate_native_verdicts": verdicts_by_ordinal, "candidate": dict(manifest["candidate"]), "packet": dict(manifest["packet"]), "standing_source": dict(manifest["standing_source"]), "queue": dict(manifest["queue"]), "provider_calls_made": 0}
