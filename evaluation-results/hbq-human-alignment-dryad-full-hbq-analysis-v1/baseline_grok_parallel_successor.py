"""Bounded, append-only parallel continuation for a stopped Grok suffix.

The renewed controller owns the historical source epoch and the serial prefix.  A
parallel successor starts at the first untouched ordinal after a frozen stopped
prefix and owns only its new wave records.  Preparation, source checks, and
candidate loading are provider-free; contact is available only to
``dispatch_wave`` after the sealed source closure and shared-fix receipt have
been checked.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import inspect
import json
import re
import sys
import threading
import traceback
import uuid
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parent
SOURCE_EPOCH = "grok_parallel_successor_20260919_r1"
MANIFEST_NAME = "grok-parallel-successor-manifest.json"
WAVE_CAP = 10
MAX_WAVE_SIZE = WAVE_CAP
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PRIOR_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.RLock()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(value if isinstance(value, bytes) else _canon(value))


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object")
    return value, raw


def _descriptor(value: Any, label: str) -> Mapping[str, Any]:
    _need(
        isinstance(value, Mapping)
        and isinstance(value.get("path"), str)
        and isinstance(value.get("sha256"), str)
        and _HASH.fullmatch(value["sha256"]) is not None,
        f"{label} descriptor differs",
    )
    return value


def _bound(value: Any, label: str) -> tuple[dict[str, Any], bytes]:
    descriptor = _descriptor(value, label)
    path = Path(str(descriptor["path"])).resolve()
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ValueError(f"{label} source drift") from error
    _need(_sha(raw) == descriptor["sha256"], f"{label} source drift")
    _need(path.read_bytes() == raw, f"{label} changed while reading")
    return dict(descriptor), raw


def _load_source(path: Path, expected: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, f"{name} source pin differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _need(spec is not None and spec.loader is not None, f"{name} load differs")
    old_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    previous = sys.modules.get(name)
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_bytecode
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    _need(path.read_bytes() == raw, f"{name} source changed")
    return module


def _native_identity(value: Any, label: str = "native identity") -> dict[str, Any]:
    _need(
        isinstance(value, Mapping)
        and isinstance(value.get("request_id_hash"), str)
        and isinstance(value.get("session_id_hash"), str),
        f"{label} differs",
    )
    request = value["request_id_hash"]
    session = value["session_id_hash"]
    _need(_HASH.fullmatch(request) is not None and _HASH.fullmatch(session) is not None, f"{label} differs")
    observed = value.get("observed_turns")
    _need(type(observed) is int and observed == 1, f"{label} differs")
    return {"request_id_hash": request, "session_id_hash": session, "observed_turns": observed}


def _identities_unique(values: Sequence[Mapping[str, Any]]) -> bool:
    requests = [value.get("request_id_hash") for value in values if isinstance(value, Mapping)]
    sessions = [value.get("session_id_hash") for value in values if isinstance(value, Mapping)]
    return (
        len(requests) == len(values)
        and all(isinstance(item, str) and _HASH.fullmatch(item) for item in requests + sessions)
        and len(requests) == len(set(requests))
        and len(sessions) == len(set(sessions))
    )


def _path_descriptor(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": str(path.resolve()), "sha256": _sha(raw)}


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _closure_value(closure: Mapping[str, Any], name: str, *aliases: str) -> Any:
    if name in closure:
        return closure[name]
    for alias in aliases:
        if alias in closure:
            return closure[alias]
    raise ValueError(f"parallel source closure missing {name}")


def _prior_binding(closure: Mapping[str, Any]) -> tuple[dict[str, Any], Path, Path]:
    controller = _descriptor(_closure_value(closure, "prior_controller", "historical_controller"), "prior controller")
    continuation = _closure_value(closure, "prior_continuation", "historical_continuation")
    _need(
        isinstance(continuation, Mapping)
        and isinstance(continuation.get("root"), str)
        and isinstance(continuation.get("manifest_path"), str)
        and isinstance(continuation.get("manifest_sha256"), str)
        and _HASH.fullmatch(continuation["manifest_sha256"]) is not None,
        "prior continuation binding differs",
    )
    controller_path = Path(str(controller["path"])).resolve()
    root = Path(str(continuation["root"])).resolve()
    manifest_path = Path(str(continuation["manifest_path"])).resolve()
    _need(_under(manifest_path, root), "prior continuation manifest escapes root")
    _need(manifest_path.read_bytes() and _sha(manifest_path.read_bytes()) == continuation["manifest_sha256"], "prior continuation manifest drift")
    _need(controller_path.is_file(), "prior controller path differs")
    return dict(controller), root, manifest_path


def _read_prefix_descriptor(
    value: Any,
    prior_pending: Sequence[int],
    prior_manifest_sha: str,
    prior_root: Path,
    prior_controller_sha: str,
    allow_local_exit: bool = False,
) -> dict[str, Any]:
    descriptor, raw = _bound(value, "stopped prefix")
    prefix, _ = _json(Path(descriptor["path"]), "stopped prefix")
    base_keys = {
        "schema_version",
        "prior_continuation",
        "completed_ordinals",
        "remaining_ordinals",
        "owned_exit",
        "loop_result",
    }
    _need(set(prefix) >= base_keys and prefix.get("schema_version") == 1, "stopped prefix schema differs")
    continuation = prefix["prior_continuation"]
    _need(
        isinstance(continuation, Mapping)
        and set(continuation) == {"root", "manifest_sha256", "controller_sha256"}
        and Path(str(continuation["root"])).resolve() == prior_root.resolve()
        and continuation.get("manifest_sha256") == prior_manifest_sha
        and continuation.get("controller_sha256") == prior_controller_sha,
        "stopped prefix prior continuation differs",
    )
    completed_value = prefix.get("completed_ordinals")
    _need(isinstance(completed_value, list) and all(type(item) is int for item in completed_value), "stopped prefix ordinals differ")
    completed = list(completed_value)
    _need(completed == list(prior_pending[: len(completed)]), "stopped prefix is not the exact prior prefix")
    expected_remaining = list(prior_pending[len(completed) :])
    if allow_local_exit:
        expected_remaining = [ordinal for ordinal in expected_remaining if ordinal != 370]
    _need(prefix["remaining_ordinals"] == expected_remaining, "stopped prefix remainder differs")
    owned_exit = prefix["owned_exit"]
    local_exit = (
        allow_local_exit
        and isinstance(owned_exit, Mapping)
        and "local_recovery" in prefix
        and owned_exit.get("exit_code") == 1
    )
    _need(
        isinstance(owned_exit, Mapping)
        and set(owned_exit) == {"exit_code", "session_id"}
        and owned_exit.get("exit_code") in (0, 1)
        and (
            (type(owned_exit.get("session_id")) is int and owned_exit.get("session_id") == 18262)
            if local_exit
            else (isinstance(owned_exit.get("session_id"), str) and owned_exit.get("session_id"))
        ),
        "stopped prefix exit differs",
    )
    loop_result, _loop_raw = _bound(prefix["loop_result"], "stopped prefix loop result")
    if owned_exit["exit_code"] == 0:
        _need(set(prefix) == base_keys, "stopped prefix schema differs")
    elif allow_local_exit and "local_recovery" in prefix:
        _need(set(prefix) == base_keys | {"local_recovery"}, "stopped prefix local recovery schema differs")
    else:
        _need(set(prefix) == base_keys | {"replay_only_recovery"}, "stopped prefix recovery schema differs")
        recovery_descriptor, _recovery_raw = _bound(prefix["replay_only_recovery"], "stopped prefix replay recovery")
        recovery, _ = _json(Path(recovery_descriptor["path"]), "stopped prefix replay recovery")
        _need(
            set(recovery)
            == {
                "schema_version",
                "kind",
                "failed_ordinal",
                "loop_result",
                "terminal",
                "replay",
                "completed_ordinals",
                "provider_calls_made",
                "automatic_resend_authorized",
            }
            and recovery.get("schema_version") == 1
            and recovery.get("kind") == "completed_native_local_replay_recovery"
            and type(recovery.get("failed_ordinal")) is int
            and recovery.get("failed_ordinal") in completed
            and recovery.get("completed_ordinals") == completed
            and recovery.get("provider_calls_made") == 0
            and recovery.get("automatic_resend_authorized") is False,
            "stopped prefix replay recovery differs",
        )
        for key in ("loop_result", "terminal", "replay"):
            bound, _ = _bound(recovery[key], f"stopped prefix recovery {key}")
            _need(isinstance(bound, Mapping), "stopped prefix recovery evidence differs")
        terminal_value, _terminal_raw = _json(Path(recovery["terminal"]["path"]), "stopped prefix recovered terminal")
        replay_value, _replay_raw = _json(Path(recovery["replay"]["path"]), "stopped prefix recovered replay")
        _need(
            terminal_value.get("ordinal") == recovery["failed_ordinal"]
            and terminal_value.get("state") == "completed"
            and isinstance(replay_value.get("ordinals"), list)
            and recovery["failed_ordinal"] in replay_value["ordinals"]
            and replay_value.get("provider_calls_made") == 0,
            "stopped prefix recovered evidence differs",
        )
        replay_terminals = replay_value.get("terminals")
        if isinstance(replay_terminals, list):
            matching = [item for item in replay_terminals if isinstance(item, Mapping) and item.get("ordinal") == recovery["failed_ordinal"]]
            _need(matching and matching[0].get("terminal_sha256") == recovery["terminal"]["sha256"], "stopped prefix recovered terminal binding differs")
    return {
        "descriptor": descriptor,
        "raw": raw,
        "value": prefix,
        "completed_ordinals": completed,
        "remaining_ordinals": expected_remaining,
        "loop_result": loop_result,
        "recovery": prefix.get("replay_only_recovery"),
        "local_recovery": prefix.get("local_recovery"),
    }


def _prior_records(
    module: ModuleType,
    root: Path,
    state: Mapping[str, Any],
    *,
    allowed_unreplayed: set[int] | None = None,
) -> tuple[list[int], list[dict[str, Any]]]:
    pending_value = state.get("pending_ordinals")
    if not isinstance(pending_value, list):
        pending_value = getattr(module, "PENDING", None)
    _need(isinstance(pending_value, list) and all(type(item) is int for item in pending_value), "prior pending ordinals differ")
    pending = list(pending_value)
    replayed: Any = None
    identities: Any = None
    replay_fn = getattr(module, "_replayed", None)
    if callable(replay_fn):
        replayed, identities = replay_fn(root, state)
    else:
        replayed, identities = set(), []
    _need(isinstance(replayed, (set, list, tuple)) and isinstance(identities, list), "prior replay boundary differs")
    replayed_set = set(replayed)
    prefix_len = 0
    while prefix_len < len(pending) and pending[prefix_len] in replayed_set:
        prefix_len += 1
    _need(replayed_set == set(pending[:prefix_len]), "prior replay is not contiguous")
    records_fn = getattr(module, "_records", None)
    if callable(records_fn):
        allowed_unreplayed = allowed_unreplayed or set()
        records = records_fn(root)
        _need(isinstance(records, Mapping), "prior attempt inventory differs")
        for ordinal, terminal in records.items():
            if ordinal in pending[:prefix_len]:
                _need(isinstance(terminal, Mapping) and terminal.get("state") == "completed", "prior prefix has incomplete attempt")
            elif terminal is None:
                raise ValueError("prior continuation has an incomplete attempt")
            elif ordinal not in allowed_unreplayed:
                raise ValueError("prior continuation has an unreplayed terminal attempt")
    prior_ids = state.get("prior_identities")
    _need(isinstance(prior_ids, list) and len(prior_ids) == 335 and _identities_unique(prior_ids), "prior baseline identities differ")
    replay_ids = [_native_identity(item, "prior replay identity") for item in identities]
    _need(_identities_unique([*prior_ids, *replay_ids]), "prior native identity collision")
    return pending[:prefix_len], [*prior_ids, *replay_ids]


def _semantic_prior(module: ModuleType, state: Mapping[str, Any], root: Path, completed: Sequence[int]) -> None:
    """Replay prior new terminals once without contacting the provider."""
    semantic = getattr(module, "_semantic_replay_terminal", None)
    context = state.get("context")
    if not completed:
        return
    _need(callable(semantic) and context is not None, "prior semantic replay contract differs")
    candidate = getattr(context, "candidate", None)
    runtime = getattr(context, "runtime", None)
    parent = getattr(context, "parent", None)
    plan_root = getattr(context, "plan_root", None)
    passes = getattr(context, "passes", None)
    requests = getattr(context, "requests", None)
    _need(
        all(item is not None for item in (candidate, runtime, parent, plan_root, passes, requests)),
        "prior semantic replay context differs",
    )
    queue = None
    historical = state.get("historical")
    if isinstance(historical, Mapping) and isinstance(historical.get("manifest"), Mapping):
        closure = historical["manifest"].get("source_closure", {})
    else:
        closure = state.get("manifest", {}).get("source_closure", {})
    queue_value = closure.get("queue") if isinstance(closure, Mapping) else None
    _need(isinstance(queue_value, Mapping) and isinstance(queue_value.get("path"), str), "prior semantic replay queue differs")
    queue = Path(queue_value["path"])
    broker = candidate.Broker(queue)
    attempt_fn = getattr(module, "_attempt", None)
    for ordinal in completed:
        if not callable(attempt_fn):
            break
        path = attempt_fn(root, ordinal, "terminal.json")
        terminal, _ = _json(path, "prior terminal")
        kwargs = {
            "candidate": candidate,
            "broker": broker,
            "terminal": terminal,
            "terminal_path": path,
            "parent": parent,
            "runtime": runtime,
            "plan_root": plan_root,
            "passes": passes,
            "requests": requests,
        }
        if "terminal_raw" in inspect.signature(semantic).parameters:
            kwargs["terminal_raw"] = path.read_bytes()
        result = semantic(**kwargs)
        _need(isinstance(result, tuple) and len(result) == 3, "prior semantic replay result differs")


def _candidate_binding(closure: Mapping[str, Any]) -> dict[str, Any]:
    if "candidate_loader" in closure:
        _bound(closure["candidate_loader"], "candidate loader provenance")
    candidate_value = _closure_value(closure, "candidate")
    _need(isinstance(candidate_value, Mapping) and isinstance(candidate_value.get("root"), str), "candidate binding differs")
    candidate_root = Path(str(candidate_value["root"])).resolve()
    manifest_sha = candidate_value.get("manifest_sha256") or candidate_value.get("sha256")
    _need(isinstance(manifest_sha, str) and _HASH.fullmatch(manifest_sha), "candidate manifest binding differs")
    manifest_path = candidate_root / "candidate-manifest.json"
    manifest, manifest_raw = _json(manifest_path, "candidate manifest")
    _need(_sha(manifest_raw) == manifest_sha, "candidate manifest differs")
    files = manifest.get("files")
    _need(
        isinstance(files, list)
        and manifest.get("schema_version") == 8
        and manifest.get("kind") == "grok_v8_contention_forwardport_candidate"
        and manifest.get("explicit_exclusion") == ["candidate-manifest.json"]
        and all(
            isinstance(item, Mapping)
            and isinstance(item.get("path"), str)
            and isinstance(item.get("sha256"), str)
            and _HASH.fullmatch(item["sha256"])
            and type(item.get("bytes")) is int
            and item["bytes"] >= 0
            for item in files
        ),
        "candidate file inventory differs",
    )
    expected_files = {item["path"]: item["sha256"] for item in files}
    _need(len(expected_files) == len(files), "candidate file inventory differs")
    actual_files: dict[str, str] = {"candidate-manifest.json": _sha(manifest_raw)}
    for path in candidate_root.rglob("*"):
        _need(not path.is_symlink(), "candidate root contains a link")
        if path.is_file():
            actual_files[path.relative_to(candidate_root).as_posix()] = _sha(path.read_bytes())
    _need(actual_files == {"candidate-manifest.json": _sha(manifest_raw), **expected_files}, "candidate root drift")
    for item in files:
        file_path = candidate_root / item["path"]
        _need(file_path.is_file() and file_path.stat().st_size == item["bytes"], "candidate file byte count differs")
    broker_path = candidate_root / "model_work_queue" / "broker.py"
    package_path = candidate_root / "model_work_queue" / "__init__.py"
    broker_sha = expected_files.get("model_work_queue/broker.py")
    _need(isinstance(broker_sha, str) and package_path.is_file() and broker_path.is_file(), "candidate broker files differ")
    broker_raw = broker_path.read_bytes()
    package_name = "_grok_parallel_candidate_" + _sha((str(candidate_root) + manifest_sha).encode())[:24]
    broker_name = package_name + ".broker"
    old_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    package_module: ModuleType | None = None
    try:
        existing = sys.modules.get(broker_name)
        if isinstance(existing, ModuleType):
            candidate = existing
        else:
            _need(existing is None, "candidate broker load is incomplete")
            package_spec = importlib.util.spec_from_file_location(package_name, package_path, submodule_search_locations=[str(package_path.parent)])
            _need(package_spec is not None and package_spec.loader is not None, "candidate package load")
            package_module = importlib.util.module_from_spec(package_spec)
            sys.modules[package_name] = package_module
            package_spec.loader.exec_module(package_module)
            candidate = importlib.import_module(broker_name)
        _need(Path(str(getattr(candidate, "__file__", ""))).resolve() == broker_path.resolve() and hasattr(candidate, "Broker"), "candidate broker origin differs")
        _need(_sha(broker_path.read_bytes()) == broker_sha, "candidate broker changed")
    except BaseException:
        if package_module is not None:
            sys.modules.pop(package_name, None)
            sys.modules.pop(broker_name, None)
        raise
    finally:
        sys.dont_write_bytecode = old_bytecode
    _need(manifest_path.read_bytes() == manifest_raw and broker_path.read_bytes() == broker_raw, "candidate changed while loading")
    return {
        "loader": None,
        "loader_descriptor": None,
        "candidate": candidate,
        "candidate_root": candidate_root,
        "manifest_sha256": manifest_sha,
        "manifest": manifest,
        "manifest_descriptor": {"path": str(manifest_path), "sha256": manifest_sha},
        "broker_descriptor": {"path": str(broker_path), "sha256": broker_sha},
    }


def _route_binding(value: Any, label: str = "route") -> dict[str, Any]:
    if isinstance(value, Mapping) and isinstance(value.get("path"), str):
        descriptor, raw = _bound(value, label)
        route, _ = _json(Path(descriptor["path"]), label)
        _need(isinstance(route.get("name"), str) or isinstance(route.get("model"), str), f"{label} differs")
        return {
            "descriptor": descriptor,
            "route": route,
            "raw": raw,
            "sha256": descriptor["sha256"],
            "route_sha256": _sha(_canon(route)),
        }
    _need(isinstance(value, Mapping) and isinstance(value.get("name"), str) and isinstance(value.get("sha256"), str), f"{label} differs")
    route = dict(value)
    return {
        "descriptor": route,
        "route": route,
        "raw": _canon(route),
        "sha256": route["sha256"],
        "route_sha256": _sha(_canon(route)),
    }


def _queue_binding(value: Any) -> dict[str, Any]:
    _need(isinstance(value, Mapping) and isinstance(value.get("path"), str), "queue binding differs")
    path = Path(str(value["path"])).resolve()
    _need(path.exists(), "queue root differs")
    result = dict(value)
    if "path_sha256" in result:
        _need(result["path_sha256"] == _sha(str(path).encode()), "queue path binding differs")
    return {"descriptor": result, "path": path}


def _json_descriptor(value: Any, label: str) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    descriptor, raw = _bound(value, label)
    parsed, _ = _json(Path(descriptor["path"]), label)
    return parsed, raw, descriptor


def _source_semantics(closure: Mapping[str, Any], *, candidate_manifest_sha256: str | None = None) -> dict[str, Any]:
    route = _route_binding(_closure_value(closure, "route"))
    gate, _gate_raw, gate_desc = _json_descriptor(_closure_value(closure, "gate"), "gate")
    standing, _standing_raw, standing_desc = _json_descriptor(_closure_value(closure, "standing_source", "standing"), "standing source")
    packet, _packet_raw, packet_desc = _json_descriptor(_closure_value(closure, "packet", "standing_packet"), "standing packet")
    _need(
        all(isinstance(gate.get(key), (str, int)) for key in ("provider", "account_class", "contract_hash", "source_evidence_hash", "updated_at"))
        and gate.get("state") == "healthy"
        and type(gate.get("max_concurrency")) is int
        and gate.get("max_concurrency") >= 1
        and gate.get("source_evidence_hash") == standing_desc["sha256"],
        "gate is not healthy and bound",
    )
    if isinstance(closure.get("route_contract_hash"), str):
        _need(gate.get("contract_hash") == closure["route_contract_hash"], "gate route contract differs")
    scope = standing.get("authorization", {}).get("scope") if isinstance(standing.get("authorization"), Mapping) else standing.get("scope")
    if not isinstance(scope, Mapping):
        scope = standing
    _need(
        standing.get("schema_version") == 3
        and standing.get("allowance_state") == "available"
        and isinstance(scope, Mapping)
        and scope.get("zero_charge_only") is True
        and scope.get("automatic_resend") is False
        and scope.get("paid_fallback") is False,
        "standing source is not zero charge",
    )
    if isinstance(scope.get("route"), str):
        _need(scope["route"] == route["route"].get("name"), "standing route differs")
    actions = packet.get("actions")
    v6_packet = (
        packet.get("schema_version") == 1
        and packet.get("kind") == "grok_standing_authority_v6_append_only_renewal_packet"
        and packet.get("state") == "renewal_sealed_provider_free"
        and isinstance(actions, Mapping)
        and actions.get("activation_authority") is False
        and actions.get("provider_contact_authority") is False
        and actions.get("provider_contact_count") == 0
        and actions.get("request_1088_resend") is False
    )
    v8_packet = (
        packet.get("schema_version") == 1
        and packet.get("kind") == "grok_v8_source_transition_packet"
        and packet.get("state") == "sealed_provider_free_not_activated"
        and packet.get("live_mutations_made") == 0
        and packet.get("provider_calls_made") == 0
        and isinstance(packet.get("preimages"), Mapping)
        and packet["preimages"].get("route_contract_sha256") == closure.get("route_contract_hash")
    )
    _need(v6_packet or v8_packet, "standing packet is not inert")
    packet_candidate = packet.get("candidate_manifest")
    if candidate_manifest_sha256 is not None and isinstance(packet_candidate, Mapping):
        _need(packet_candidate.get("sha256") == candidate_manifest_sha256, "standing packet candidate differs")
    if candidate_manifest_sha256 is not None and isinstance(packet.get("candidate_manifest_sha256"), str):
        _need(packet["candidate_manifest_sha256"] == candidate_manifest_sha256, "standing packet candidate differs")
    fix_value = closure.get("contention_fix_receipt")
    _need(fix_value is not None, "shared contention fix receipt binding is missing")
    fix, _fix_raw, _fix_desc = _json_descriptor(fix_value, "shared contention fix receipt")
    _need(
        fix.get("shared_contention_fix_verified") is True
        and (candidate_manifest_sha256 is None or fix.get("candidate_manifest_sha256") == candidate_manifest_sha256)
        and fix.get("provider_calls_made") == 0,
        "shared contention fix receipt is not affirmative",
    )
    transition = _transition_bindings(
        closure,
        candidate_manifest_sha256=candidate_manifest_sha256,
        route_contract_hash=closure.get("route_contract_hash"),
        standing_source_sha256=standing_desc["sha256"],
    )
    _need(route["route_sha256"] == transition["route_target_sha256"], "route transition target differs")
    return {
        "route": route,
        "gate": gate,
        "standing": standing,
        "packet": packet,
        "descriptors": {"gate": gate_desc, "standing_source": standing_desc, "packet": packet_desc},
        "shared_fix": fix,
        **transition,
    }


def _transition_bindings(
    closure: Mapping[str, Any],
    *,
    candidate_manifest_sha256: str | None,
    route_contract_hash: Any,
    standing_source_sha256: str,
) -> dict[str, Any]:
    """Validate immutable V8 registry, gate, and transition bindings."""
    registry_value = closure.get("registry_descriptor") or closure.get("runtime_registry")
    gate_value = closure.get("gate_descriptor") or closure.get("host_gate")
    transition_value = closure.get("transition_receipt") or closure.get("transition")
    _need(registry_value is not None and gate_value is not None and transition_value is not None, "runtime transition bindings are missing")
    registry_descriptor, _registry_raw, registry_path_descriptor = _json_descriptor(registry_value, "registry transition descriptor")
    gate_descriptor, _gate_raw, gate_path_descriptor = _json_descriptor(gate_value, "gate transition descriptor")
    transition, _transition_raw, transition_descriptor = _json_descriptor(transition_value, "transition receipt")
    _need(
        registry_descriptor.get("schema_version") == 1
        and registry_descriptor.get("kind") == "grok_v8_isolated_registry_transition_descriptor"
        and isinstance(registry_descriptor.get("registry_path"), str)
        and _HASH.fullmatch(str(registry_descriptor.get("pre_registry_sha256")))
        and _HASH.fullmatch(str(registry_descriptor.get("target_registry_sha256")))
        and _HASH.fullmatch(str(registry_descriptor.get("target_route_sha256")))
        and isinstance(registry_descriptor.get("route_contract_sha256"), str),
        "registry transition descriptor differs",
    )
    _need(
        isinstance(route_contract_hash, str)
        and _HASH.fullmatch(route_contract_hash)
        and registry_descriptor.get("route_contract_sha256") == route_contract_hash,
        "route contract hash differs",
    )
    gate_path = Path(str(gate_descriptor.get("path"))).resolve()
    _need(
        gate_descriptor.get("schema_version") == 1
        and gate_descriptor.get("kind") == "grok_v8_gate_transition_descriptor"
        and gate_path.is_file()
        and gate_descriptor.get("route_contract_sha256") == route_contract_hash
        and gate_descriptor.get("pre_row_sha256") == gate_descriptor.get("target_row_sha256")
        and isinstance(gate_descriptor.get("required_storage_postcondition"), Mapping)
        and gate_descriptor["required_storage_postcondition"].get("journal_mode") == "wal"
        and gate_descriptor["required_storage_postcondition"].get("storage_schema_version") == 1,
        "gate transition descriptor differs",
    )
    actions = transition.get("actions")
    _need(
        transition.get("schema_version") == 1
        and transition.get("kind") == "grok_v8_quiescent_transition_receipt"
        and transition.get("state") == "complete"
        and isinstance(actions, Mapping)
        and actions.get("provider_calls_made") == 0
        and actions.get("queue_dispatches") == 0
        and actions.get("automatic_resends") == 0
        and actions.get("global_registry_mutated") is False
        and actions.get("installed_shared_broker_mutated") is False,
        "transition receipt differs",
    )
    gate_receipt = transition.get("gate")
    queue_receipt = transition.get("queue")
    registry_receipt = transition.get("registry")
    route_receipt = transition.get("route")
    runtime_receipt = transition.get("runtime")
    source_receipt = transition.get("source")
    prefix_receipt = transition.get("prefix")
    owner_receipt = transition.get("exclusive_owner")
    verification = transition.get("verification")
    _need(
        isinstance(gate_receipt, Mapping)
        and gate_receipt.get("path") == str(gate_path)
        and _HASH.fullmatch(str(gate_receipt.get("pretransition_db_sha256")))
        and _HASH.fullmatch(str(gate_receipt.get("posttransition_db_sha256")))
        and isinstance(gate_receipt.get("storage_pre"), Mapping)
        and isinstance(gate_receipt.get("storage_post"), Mapping)
        and gate_receipt.get("active_slots_before") == 0
        and gate_receipt.get("active_slots_after") == 0
        and isinstance(queue_receipt, Mapping)
        and _HASH.fullmatch(str(queue_receipt.get("pretransition_db_sha256")))
        and queue_receipt.get("running_rows") == 0
        and isinstance(registry_receipt, Mapping)
        and registry_receipt.get("path") == registry_descriptor.get("registry_path")
        and registry_receipt.get("pre_sha256") == registry_descriptor.get("pre_registry_sha256")
        and registry_receipt.get("target_sha256") == registry_descriptor.get("target_registry_sha256")
        and registry_receipt.get("post_sha256") == registry_descriptor.get("target_registry_sha256")
        and isinstance(route_receipt, Mapping)
        and route_receipt.get("contract_sha256") == route_contract_hash
        and route_receipt.get("target_sha256") == registry_descriptor.get("target_route_sha256")
        and isinstance(runtime_receipt, Mapping)
        and (candidate_manifest_sha256 is None or runtime_receipt.get("candidate_manifest_sha256") == candidate_manifest_sha256)
        and all(
            isinstance(runtime_receipt.get(key), str) and runtime_receipt.get(key)
            for key in (
                "binding_interface_sha256",
                "handoff_manifest_sha256",
                "broker_sha256",
                "adapter_sha256",
                "wrapper_python_path",
                "wrapper_python_sha256",
                "runner_path",
                "runner_sha256",
                "runner_interpreter_path",
                "runner_interpreter_sha256",
                "controller_path",
                "controller_sha256",
                "reader_path",
                "reader_sha256",
            )
        )
        and isinstance(source_receipt, Mapping)
        and source_receipt.get("standing_source_sha256") == standing_source_sha256
        and _HASH.fullmatch(str(source_receipt.get("subscription_receipt_sha256")))
        and _HASH.fullmatch(str(source_receipt.get("cost_evidence_sha256")))
        and isinstance(source_receipt.get("expires_at"), str)
        and isinstance(prefix_receipt, Mapping)
        and isinstance(prefix_receipt.get("receipt_path"), str)
        and _HASH.fullmatch(str(prefix_receipt.get("receipt_sha256")))
        and type(prefix_receipt.get("completed_through")) is int
        and type(prefix_receipt.get("first_untouched_ordinal")) is int
        and prefix_receipt.get("automatic_resend") is False
        and isinstance(owner_receipt, Mapping)
        and all(isinstance(owner_receipt.get(key), str) and owner_receipt.get(key) for key in ("human_owner_id", "work_id", "task_id", "host_id", "workspace_instance_id", "session_id", "registry_lock_path", "gate_transaction", "acquired_at"))
        and isinstance(verification, Mapping)
        and all(verification.get(key) is True for key in ("candidate_inventory_valid", "route_valid", "gate_storage_valid", "doctor_ok", "status_ok", "expected_route_pin_valid")),
        "transition receipt bindings differ",
    )
    for path_key, hash_key in (
        ("wrapper_python_path", "wrapper_python_sha256"),
        ("runner_path", "runner_sha256"),
        ("runner_interpreter_path", "runner_interpreter_sha256"),
        ("reader_path", "reader_sha256"),
    ):
        bound_path = Path(str(runtime_receipt[path_key])).resolve()
        _need(bound_path.is_file() and _sha(bound_path.read_bytes()) == runtime_receipt[hash_key], f"transition runtime {path_key} differs")
    controller_path = Path(str(runtime_receipt["controller_path"])).resolve()
    _need(
        controller_path == Path(__file__).resolve()
        and runtime_receipt["controller_sha256"] == _sha(Path(__file__).read_bytes()),
        "transition runtime controller differs",
    )
    registry_path = Path(str(registry_descriptor["registry_path"])).resolve()
    _need(registry_path.is_file(), "runtime registry path differs")
    _need(_sha(registry_path.read_bytes()) == registry_descriptor["target_registry_sha256"], "runtime registry source differs")
    prefix_path = Path(str(prefix_receipt["receipt_path"])).resolve()
    _need(prefix_path.is_file() and _sha(prefix_path.read_bytes()) == prefix_receipt["receipt_sha256"], "transition prefix receipt differs")
    return {
        "registry_path": registry_path,
        "registry_descriptor": registry_path_descriptor,
        "registry_target_sha256": registry_descriptor["target_registry_sha256"],
        "route_target_sha256": registry_descriptor["target_route_sha256"],
        "gate_path": gate_path,
        "gate_descriptor": gate_path_descriptor,
        "transition_descriptor": transition_descriptor,
        "transition_receipt": transition,
        "prefix_receipt": prefix_receipt,
        "route_contract_hash": route_contract_hash,
    }


def _context_plan_root(context: Any, closure: Mapping[str, Any]) -> Path:
    value = getattr(context, "plan_root", None)
    if value is None and isinstance(context, Mapping):
        value = context.get("plan_root")
    if value is None:
        value = closure.get("plan_root")
    _need(isinstance(value, (str, Path)), "context plan root differs")
    return Path(value).resolve()


def _prior_state(closure: Mapping[str, Any], *, semantic: bool = True) -> dict[str, Any]:
    controller, prior_root, prior_manifest_path = _prior_binding(closure)
    continuation = _closure_value(closure, "prior_continuation", "historical_continuation")
    key = _sha(
        _canon(
            {
                "controller": controller,
                "continuation": continuation,
                "stopped": _closure_value(closure, "stopped_prefix"),
                "local_recovery": closure.get("local_recovery"),
            }
        )
    )
    with _CACHE_LOCK:
        cached = _PRIOR_CACHE.get(key)
    if cached is not None:
        return cached
    module = _load_source(Path(controller["path"]).resolve(), controller["sha256"], "prior controller")
    verify_fn = getattr(module, "verify", None) or getattr(module, "verify_runtime_data_successor", None)
    _need(callable(verify_fn), "prior controller verify contract differs")
    state = verify_fn(continuation_root=prior_root, expected_manifest_sha256=continuation["manifest_sha256"])
    _need(isinstance(state, Mapping), "prior controller state differs")
    prior_pending = state.get("pending_ordinals")
    if not isinstance(prior_pending, list):
        prior_pending = getattr(module, "PENDING", None)
    _need(isinstance(prior_pending, list), "prior pending ordinals differ")
    local_allowed = isinstance(closure.get("local_recovery"), Mapping)
    prior_completed, identities = _prior_records(
        module,
        prior_root,
        state,
        allowed_unreplayed={370} if local_allowed else set(),
    )
    prefix = _read_prefix_descriptor(
        _closure_value(closure, "stopped_prefix"),
        prior_pending,
        continuation["manifest_sha256"],
        prior_root,
        controller["sha256"],
        allow_local_exit=local_allowed,
    )
    _need(prefix["completed_ordinals"] == prior_completed, "stopped prefix does not bind prior replay")
    if local_allowed:
        _need(
            isinstance(prefix.get("local_recovery"), Mapping)
            and dict(prefix["local_recovery"]) == dict(closure["local_recovery"]),
            "stopped prefix local recovery binding differs",
        )
    if semantic:
        _semantic_prior(module, state, prior_root, prior_completed)
    context = state.get("context")
    plan_root = _context_plan_root(context, closure)
    pending = [ordinal for ordinal in prior_pending if not (local_allowed and ordinal == 370)]
    result = {
        "module": module,
        "state": dict(state),
        "root": prior_root,
        "manifest_path": prior_manifest_path,
        "manifest_sha256": continuation["manifest_sha256"],
        "pending": pending,
        "completed": list(prior_completed),
        "prefix": prefix,
        "local_recovery_descriptor": dict(closure["local_recovery"]) if local_allowed else None,
        "identities": identities,
        "context": context,
        "plan_root": plan_root,
    }
    with _CACHE_LOCK:
        _PRIOR_CACHE[key] = result
    return result


def _manifest_path(root: Path) -> Path:
    return root / MANIFEST_NAME


def _manifest(root: Path, expected: str | None = None) -> tuple[dict[str, Any], bytes]:
    value, raw = _json(_manifest_path(root), "parallel successor manifest")
    required = {
        "schema_version", "evidence_class", "source_epoch", "controller_sha256", "source_closure", "source_closure_sha256",
        "prior_continuation", "stopped_prefix", "prior_completed_ordinals", "pending_ordinals", "completed_ordinals",
        "context", "protected_paths", "wave_cap", "provider_calls_made", "execution_authority",
    }
    _need(
        (expected is None or _sha(raw) == expected)
        and set(value) == required
        and value.get("schema_version") == 1
        and value.get("evidence_class") == "dryad_grok_parallel_successor_v1"
        and value.get("source_epoch") == SOURCE_EPOCH
        and value.get("controller_sha256") == _sha(Path(__file__).read_bytes())
        and value.get("source_closure_sha256") == _sha(_canon(value.get("source_closure")))
        and value.get("wave_cap") == WAVE_CAP
        and value.get("provider_calls_made") == 0
        and value.get("execution_authority") is False
        and isinstance(value.get("pending_ordinals"), list)
        and isinstance(value.get("completed_ordinals"), list),
        "parallel successor manifest differs",
    )
    return value, raw


def _protected_paths(closure: Mapping[str, Any], prior: Mapping[str, Any], candidate: Mapping[str, Any], plan_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "prior_controller": dict(_descriptor(_closure_value(closure, "prior_controller", "historical_controller"), "prior controller")),
        "prior_manifest": {"path": str(prior["manifest_path"]), "sha256": prior["manifest_sha256"]},
        "stopped_prefix": dict(_descriptor(_closure_value(closure, "stopped_prefix"), "stopped prefix")),
        "candidate_manifest": dict(candidate["manifest_descriptor"]),
        "candidate_broker": dict(candidate["broker_descriptor"]),
        "plan_root": {"path": str(plan_root)},
    }
    for name in (
        "gate",
        "standing_source",
        "packet",
        "contention_fix_receipt",
        "registry_descriptor",
        "gate_descriptor",
        "transition_receipt",
    ):
        value = closure.get(name)
        if name == "packet" and value is None:
            value = closure.get("standing_packet")
        if name == "registry_descriptor" and value is None:
            value = closure.get("runtime_registry")
        if name == "gate_descriptor" and value is None:
            value = closure.get("host_gate")
        if name == "transition_receipt" and value is None:
            value = closure.get("transition")
        if isinstance(value, Mapping) and isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            result[name] = {"path": value["path"], "sha256": value["sha256"]}
    candidate_root = candidate["candidate_root"]
    result["candidate_root"] = {"path": str(candidate_root)}
    if isinstance(closure.get("candidate_loader"), Mapping):
        result["candidate_loader"] = dict(_descriptor(closure["candidate_loader"], "candidate loader provenance"))
    queue_value = closure.get("queue")
    if isinstance(queue_value, Mapping) and isinstance(queue_value.get("path"), str):
        result["queue_root"] = {"path": str(Path(queue_value["path"]).resolve()), "root_hash": queue_value.get("root_hash")}
    return result


def create(*, continuation_root: Path | str, source_closure: Mapping[str, Any]) -> dict[str, Any]:
    """Create an inert manifest bound to a verified stopped serial prefix."""
    root = Path(continuation_root).resolve()
    _need(not root.exists() or (root.is_dir() and not any(root.iterdir())), "parallel successor root is not fresh")
    _need(isinstance(source_closure, Mapping), "parallel source closure differs")
    _prior_binding(source_closure)
    prior = _prior_state(source_closure)
    candidate = _candidate_binding(source_closure)
    source = _source_semantics(source_closure, candidate_manifest_sha256=candidate["manifest_sha256"])
    local_recovery = _local_recovery_binding(source_closure, prior)
    _queue_binding(_closure_value(source_closure, "queue"))
    _need(not _under(root, prior["root"]) and not _under(prior["root"], root), "parallel root overlaps prior root")
    _need(not _under(root, candidate["candidate_root"]) and not _under(candidate["candidate_root"], root), "parallel root overlaps candidate root")
    pending = list(prior["pending"][len(prior["completed"]) :])
    plan_root = prior["plan_root"]
    closure = dict(source_closure)
    protected_paths = _protected_paths(closure, prior, candidate, plan_root)
    protected_paths.update(
        {
            "runtime_registry": {
                "path": str(source["registry_path"]),
                "sha256": source["registry_target_sha256"],
            },
            "grok_host_gate": {
                "path": str(source["gate_path"]),
                "route_contract_sha256": source["route_contract_hash"],
            },
            "transition_prefix": {
                "path": source["prefix_receipt"]["receipt_path"],
                "sha256": source["prefix_receipt"]["receipt_sha256"],
            },
        }
    )
    if local_recovery is not None:
        protected_paths.update(local_recovery["protected_paths"])
    value = {
        "schema_version": 1,
        "evidence_class": "dryad_grok_parallel_successor_v1",
        "source_epoch": SOURCE_EPOCH,
        "controller_sha256": _sha(Path(__file__).read_bytes()),
        "source_closure": closure,
        "source_closure_sha256": _sha(_canon(closure)),
        "prior_continuation": dict(_closure_value(closure, "prior_continuation", "historical_continuation")),
        "stopped_prefix": dict(_descriptor(_closure_value(closure, "stopped_prefix"), "stopped prefix")),
        "prior_completed_ordinals": list(prior["completed"]),
        "pending_ordinals": pending,
        "completed_ordinals": [],
        "context": {"plan_root": str(plan_root)},
        "protected_paths": protected_paths,
        "wave_cap": WAVE_CAP,
        "provider_calls_made": 0,
        "execution_authority": False,
    }
    _new(_manifest_path(root), value)
    return {
        "manifest_sha256": _sha(_manifest_path(root).read_bytes()),
        "controller_sha256": value["controller_sha256"],
        "source_epoch": SOURCE_EPOCH,
        "next_ordinal": pending[0] if pending else None,
        "pending_ordinals": pending,
        "provider_calls_made": 0,
        "execution_authority": False,
        "plan_root": str(plan_root),
    }


def _state(root: Path, expected: str, *, semantic_prior: bool = True) -> dict[str, Any]:
    manifest, raw = _manifest(root, expected)
    closure = manifest["source_closure"]
    _need(_sha(_canon(closure)) == manifest["source_closure_sha256"], "parallel source closure differs")
    prior = _prior_state(closure, semantic=semantic_prior)
    _need(manifest["prior_completed_ordinals"] == prior["completed"], "parallel prior prefix differs")
    _need(manifest["pending_ordinals"] == prior["pending"][len(prior["completed"]) :], "parallel pending suffix differs")
    candidate = _candidate_binding(closure)
    source = _source_semantics(closure, candidate_manifest_sha256=candidate["manifest_sha256"])
    local_recovery = _local_recovery_binding(closure, prior)
    prefix_receipt = source["prefix_receipt"]
    _need(
        prefix_receipt.get("first_untouched_ordinal") == manifest["pending_ordinals"][0]
        and prefix_receipt.get("completed_through")
        == (370 if local_recovery is not None else prior["completed"][-1]),
        "transition receipt prefix boundary differs",
    )
    queue = _queue_binding(_closure_value(closure, "queue"))
    plan_root = _context_plan_root(prior["context"], closure)
    return {
        "manifest": manifest,
        "manifest_raw": raw,
        "closure": closure,
        "prior": prior,
        "candidate": candidate,
        "source": source,
        "local_recovery": local_recovery,
        "queue": queue,
        "plan_root": plan_root,
        "root": root,
    }


def verify(*, continuation_root: Path | str, expected_manifest_sha256: str) -> dict[str, Any]:
    """Verify the immutable bindings and return the reader-facing state."""
    state = _state(Path(continuation_root).resolve(), expected_manifest_sha256)
    records = _read_records(state, require_complete=False, semantic=False)
    return {
        "manifest": state["manifest"],
        "manifest_raw": state["manifest_raw"],
        "manifest_sha256": _sha(state["manifest_raw"]),
        "source_epoch": SOURCE_EPOCH,
        "prior_continuation": state["manifest"]["prior_continuation"],
        "prior_completed_ordinals": list(state["prior"]["completed"]),
        "pending_ordinals": list(state["manifest"]["pending_ordinals"]),
        "completed_ordinals": records["completed_ordinals"],
        "context": {"plan_root": str(state["plan_root"])},
        "plan_root": str(state["plan_root"]),
        "protected_paths": state["manifest"]["protected_paths"],
        "local_recoveries": [state["local_recovery"]] if state["local_recovery"] is not None else [],
        "provider_calls_made": 0,
        "state": state,
    }


def _record_dirs(root: Path) -> list[tuple[int, Path]]:
    base = root / "attempts"
    if not base.exists():
        return []
    result: list[tuple[int, Path]] = []
    for item in base.iterdir():
        match = re.fullmatch(r"request-(\d{4,})", item.name)
        _need(match is not None and item.is_dir() and not item.is_symlink(), "parallel attempt inventory differs")
        result.append((int(match.group(1)), item))
    return sorted(result)


def _attempt(root: Path, ordinal: int, name: str) -> Path:
    return root / "attempts" / f"request-{ordinal:04d}" / name


def _wave_path(root: Path, start: int, size: int, name: str) -> Path:
    return root / "waves" / f"wave-{start:04d}-slots-{size:02d}-{name}.json"


def _replay_path(root: Path, ordinal: int, size: int) -> Path:
    return root / "replays" / f"wave-{ordinal:04d}-slots-{size:02d}-replay.json"


def _row_for(state: Mapping[str, Any], ordinal: int) -> dict[str, Any]:
    context = state["prior"]["context"]
    requests = getattr(context, "requests", None)
    if requests is None and isinstance(context, Mapping):
        requests = context.get("requests")
    row = requests.get(ordinal) if isinstance(requests, Mapping) else None
    _need(isinstance(row, Mapping), f"parallel request {ordinal} differs")
    result = dict(row)
    parent = getattr(context, "parent", None)
    if parent is None and isinstance(context, Mapping):
        parent = context.get("parent")
    passes = getattr(context, "passes", None)
    if passes is None and isinstance(context, Mapping):
        passes = context.get("passes")
    prompt = result.get("prompt")
    schema_path = result.get("schema_path")
    ids = result.get("question_ids")
    source = result.get("source")
    if parent is not None and callable(getattr(parent, "_request_payload", None)) and isinstance(passes, Mapping):
        prompt, schema_path, ids = parent._request_payload(state["plan_root"], result)
        source = parent._source_for_pass(state["plan_root"], passes[result["pass_id"]])
    _need(isinstance(prompt, str) and isinstance(ids, list) and isinstance(source, Mapping), f"parallel request {ordinal} differs")
    if isinstance(schema_path, Path):
        schema = json.loads(schema_path.read_bytes())
        schema_sha = _sha(schema_path.read_bytes())
    elif isinstance(schema_path, str) and Path(schema_path).is_file():
        schema_path = Path(schema_path)
        schema = json.loads(schema_path.read_bytes())
        schema_sha = _sha(schema_path.read_bytes())
    else:
        schema = result.get("schema") if isinstance(result.get("schema"), Mapping) else {"type": "object"}
        schema_sha = _sha(_canon(schema))
    source_dict = dict(source)
    artifact_path = source_dict.get("artifact_path") or source_dict.get("path")
    if isinstance(artifact_path, str) and Path(artifact_path).is_file():
        source_path = Path(artifact_path).resolve()
        source_raw = source_path.read_bytes()
        source_sha_bound = source_dict.get("sha256")
        _need(source_sha_bound is None or source_sha_bound == _sha(source_raw), f"parallel request {ordinal} source drift")
        source_dict["artifact_path"] = str(source_path)
        source_dict["story_text"] = source_raw.decode("utf-8")
        source_dict["sha256"] = _sha(source_raw)
    _need(isinstance(source_dict.get("story_text"), str), f"parallel request {ordinal} source differs")
    source_sha = source_dict.get("sha256")
    if not isinstance(source_sha, str):
        source_sha = _sha(source_dict["story_text"].encode())
    return {
        "ordinal": ordinal,
        "pass_id": result.get("pass_id"),
        "prompt": prompt,
        "prompt_sha256": result.get("prompt_sha256", _sha(prompt.encode())),
        "schema": schema,
        "schema_sha256": result.get("schema_sha256", schema_sha),
        "question_ids": list(ids),
        "source": source_dict,
        "source_sha256": source_sha,
    }


def _local_recovery_binding(closure: Mapping[str, Any], prior: Mapping[str, Any]) -> dict[str, Any] | None:
    value = closure.get("local_recovery")
    if value is None:
        return None
    adoption_descriptor, _adoption_raw = _bound(value, "local recovery adoption")
    adoption, _ = _json(Path(adoption_descriptor["path"]), "local recovery adoption")
    _need(
        adoption.get("schema_version") == 1
        and adoption.get("kind") == "dryad_local_session_quote_projection_adoption"
        and adoption.get("ordinal") == 370
        and adoption.get("decision") == "adopt_exact_independently_reviewed_local_schema_projection"
        and adoption.get("evidence_class") == "owner_adopted_local_session_schema_recovery"
        and adoption.get("automatic_resend_authorized") is False
        and adoption.get("new_provider_attempts_authorized") == 0
        and adoption.get("ordinary_native_admission") is False
        and adoption.get("original_failed_attempt_preserved") is True
        and adoption.get("coverage_waiver") is False
        and adoption.get("new_direct_user_decision_claimed") is False,
        "local recovery adoption differs",
    )
    accounting = adoption.get("full_collection_accounting")
    _need(
        isinstance(accounting, Mapping)
        and accounting.get("logical_requests") == 2300
        and accounting.get("native_results") == 2297
        and accounting.get("criterion_verdicts") == 17800
        and accounting.get("local_recovery_ordinals") == [70, 254, 370],
        "local recovery accounting differs",
    )
    proposal_descriptor = adoption["proposal"]
    proposal, _proposal_raw, _proposal_descriptor = _json_descriptor(proposal_descriptor, "local recovery proposal")
    review, _review_raw, _review_descriptor = _json_descriptor(adoption["independent_review"], "local recovery review")
    capture, _capture_raw, _capture_descriptor = _json_descriptor(adoption["capture"], "local recovery capture")
    _need(
        proposal.get("schema_version") == 1
        and proposal.get("kind") == "grok370_local_quote_repair_proposal"
        and proposal.get("ordinal") == 370
        and proposal.get("state") == "not_adopted"
        and proposal.get("operation") == "retain exact first 500 source-grounded characters"
        and proposal.get("original_length") == 781
        and proposal.get("proposed_length") == 500
        and proposal.get("schema_valid") is True
        and proposal.get("other_values_unchanged") is True
        and proposal.get("provider_calls_made") == 0
        and review.get("decision") == "GO_exact_local_quote_projection_only"
        and review.get("schema_valid") is True
        and review.get("all_eight_question_ids_and_verdicts_unchanged") is True
        and review.get("all_other_values_unchanged") is True
        and review.get("exact_one_value_change") is True
        and review.get("ordinary_native_admission") is False
        and review.get("original_failure_preserved") is True
        and review.get("original_quote_equals_source") is True
        and capture.get("kind") == "grok370_existing_response_forensic_capture"
        and capture.get("ordinal") == 370
        and capture.get("admission_performed") is False
        and capture.get("answer_modified") is False
        and capture.get("automatic_resend_authorized") is False,
        "local recovery proposal or review differs",
    )
    for key in (
        "attempt_start",
        "original_message",
        "original_terminal",
        "projected_message",
        "response_schema",
        "session_events",
        "session_summary",
        "session_updates",
        "source_artifact",
        "standing_authority",
    ):
        _descriptor(adoption[key], f"local recovery {key}")
        _bound(adoption[key], f"local recovery {key}")
    prior_terminal_path = Path(adoption["original_terminal"]["path"]).resolve()
    expected_terminal_path = prior["root"] / "attempts" / "request-0370" / "terminal.json"
    _need(prior_terminal_path == expected_terminal_path.resolve(), "local recovery terminal path differs")
    terminal, terminal_raw = _json(prior_terminal_path, "local recovery original terminal")
    _need(
        _sha(terminal_raw) == adoption["original_terminal"]["sha256"]
        and terminal.get("ordinal") == 370
        and terminal.get("state") == "ambiguous"
        and terminal.get("contact_admitted") is True
        and terminal.get("session_id") == adoption.get("session_id")
        and terminal.get("native_identity") is None,
        "local recovery original terminal differs",
    )
    attempt_start_path = prior["root"] / "attempts" / "request-0370" / "attempt-start.json"
    _need(
        Path(adoption["attempt_start"]["path"]).resolve() == attempt_start_path.resolve()
        and _sha(attempt_start_path.read_bytes()) == adoption["attempt_start"]["sha256"],
        "local recovery attempt binding differs",
    )
    attempt_start, _ = _json(attempt_start_path, "local recovery attempt start")
    _schema_value, schema_raw = _json(Path(adoption["response_schema"]["path"]), "local recovery response schema")
    _need(
        _sha(schema_raw) == adoption["response_schema"]["sha256"]
        and attempt_start.get("schema_sha256") == adoption["response_schema"]["sha256"],
        "local recovery schema binding differs",
    )
    original_answer, original_answer_raw = _json(Path(adoption["original_message"]["path"]), "local recovery original answer")
    projected_answer, projected_answer_raw = _json(Path(adoption["projected_message"]["path"]), "local recovery projected answer")
    _need(
        _sha(original_answer_raw) == adoption["original_message"]["sha256"] == proposal["original_answer_sha256"]
        and _sha(projected_answer_raw) == adoption["projected_message"]["sha256"] == proposal["proposed_answer_sha256"]
        and _sha(original_answer_raw) == review["original_answer_sha256"]
        and _sha(projected_answer_raw) == review["projected_answer_sha256"],
        "local recovery answer hashes differ",
    )
    original_verdicts = original_answer.get("verdicts")
    projected_verdicts = projected_answer.get("verdicts")
    _need(isinstance(original_verdicts, list) and isinstance(projected_verdicts, list) and len(original_verdicts) == len(projected_verdicts) == 8, "local recovery verdict count differs")
    expected_projection = json.loads(json.dumps(original_answer))
    expected_projection["verdicts"][7]["evidence"][0]["exact_quote"] = projected_verdicts[7]["evidence"][0]["exact_quote"]
    _need(expected_projection == projected_answer, "local recovery changed more than the quote")
    source_path = Path(adoption["source_artifact"]["path"]).resolve()
    source_raw = source_path.read_bytes()
    _need(_sha(source_raw) == adoption["source_artifact"]["sha256"] == proposal["source_sha256"], "local recovery source differs")
    source_text = source_raw.decode("utf-8").rstrip()
    original_quote = original_verdicts[7]["evidence"][0].get("exact_quote")
    projected_quote = projected_verdicts[7]["evidence"][0].get("exact_quote")
    _need(
        isinstance(original_quote, str)
        and isinstance(projected_quote, str)
        and len(original_quote) == 781
        and len(projected_quote) == 500
        and original_quote == source_text
        and projected_quote == source_text[:500],
        "local recovery quote projection differs",
    )
    row = _row_for({"prior": prior, "plan_root": prior["plan_root"]}, 370)
    normalized = _normalize({"prior": prior}, row, {"output": projected_answer}, 370)
    _need([item.get("question_id") for item in normalized] == row["question_ids"], "local recovery normalized question IDs differ")
    return {
        "ordinal": 370,
        "verdicts": normalized,
        "local_identity": {"ordinal": 370, "session_id": adoption["session_id"], "answer_sha256": adoption["projected_message"]["sha256"]},
        "adoption": dict(adoption_descriptor),
        "original_terminal": dict(adoption["original_terminal"]),
        "ordinary_native_admission": False,
        "protected_paths": {
            "adoption": dict(adoption_descriptor),
            **{
                key: dict(adoption[key])
                for key in (
                    "capture",
                    "original_message",
                    "original_terminal",
                    "projected_message",
                    "proposal",
                    "response_schema",
                    "source_artifact",
                    "independent_review",
                )
            },
        },
    }


def _records(root: Path) -> dict[int, dict[str, Any] | None]:
    return {
        ordinal: (_json(_attempt(root, ordinal, "terminal.json"), "parallel terminal")[0] if _attempt(root, ordinal, "terminal.json").is_file() else None)
        for ordinal, _path in _record_dirs(root)
    }


def _validate_replay_receipt(
    *, root: Path, manifest: Mapping[str, Any], manifest_raw: bytes, pending: Sequence[int], replay_path: Path, replay: Mapping[str, Any]
) -> list[int]:
    required = {
        "schema_version",
        "evidence_class",
        "source_epoch",
        "controller_sha256",
        "manifest_sha256",
        "root",
        "ordinals",
        "terminals",
        "native_identities",
        "provider_calls_made",
    }
    _need(
        set(replay) == required
        and replay.get("schema_version") == 1
        and replay.get("evidence_class") == "source_bound_grok_parallel_successor_replay_v1"
        and replay.get("source_epoch") == SOURCE_EPOCH
        and replay.get("controller_sha256") == manifest["controller_sha256"]
        and replay.get("manifest_sha256") == _sha(manifest_raw)
        and Path(str(replay.get("root"))).resolve() == root.resolve()
        and replay.get("provider_calls_made") == 0,
        "parallel replay receipt differs",
    )
    ordinals = replay.get("ordinals")
    terminals = replay.get("terminals")
    identities = replay.get("native_identities")
    _need(
        isinstance(ordinals, list)
        and ordinals
        and all(type(item) is int and item in pending for item in ordinals)
        and len(ordinals) == len(set(ordinals))
        and isinstance(terminals, list)
        and len(terminals) == len(ordinals)
        and isinstance(identities, list)
        and len(identities) == len(ordinals),
        "parallel replay receipt geometry differs",
    )
    start_ordinal, wave_size = ordinals[0], len(ordinals)
    settlement_path = _wave_path(root, start_ordinal, wave_size, "settlement")
    intent_path = _wave_path(root, start_ordinal, wave_size, "intent")
    _need(settlement_path.is_file() and intent_path.is_file(), "parallel wave receipt is missing")
    settlement, _ = _json(settlement_path, "parallel wave settlement")
    intent, intent_raw = _json(intent_path, "parallel wave intent")
    _need(
        set(settlement)
        == {
            "schema_version",
            "source_epoch",
            "controller_sha256",
            "manifest_sha256",
            "start_ordinal",
            "wave_size",
            "ordinals",
            "wave_intent_sha256",
            "replay_sha256",
            "provider_calls_made",
        }
        and settlement.get("schema_version") == 1
        and settlement.get("source_epoch") == SOURCE_EPOCH
        and settlement.get("controller_sha256") == manifest["controller_sha256"]
        and settlement.get("manifest_sha256") == _sha(manifest_raw)
        and settlement.get("start_ordinal") == start_ordinal
        and settlement.get("wave_size") == wave_size
        and settlement.get("ordinals") == ordinals
        and settlement.get("wave_intent_sha256") == _sha(intent_path.read_bytes())
        and settlement.get("replay_sha256") == _sha(replay_path.read_bytes())
        and type(settlement.get("provider_calls_made")) is int,
        "parallel wave settlement differs",
    )
    _need(
        intent.get("source_epoch") == SOURCE_EPOCH
        and intent.get("controller_sha256") == manifest["controller_sha256"]
        and intent.get("manifest_sha256") == _sha(manifest_raw)
        and intent.get("ordinals") == ordinals
        and _sha(intent_raw) == _sha(intent_path.read_bytes()),
        "parallel wave intent differs",
    )
    for ordinal, row, identity in zip(ordinals, terminals, identities, strict=True):
        _need(
            isinstance(row, Mapping)
            and set(row) == {"ordinal", "terminal_sha256", "native_envelope_sha256", "native_identity"}
            and row.get("ordinal") == ordinal
            and row.get("native_identity") == identity,
            "parallel replay receipt terminal differs",
        )
        terminal_path = _attempt(root, ordinal, "terminal.json")
        _need(terminal_path.is_file(), "parallel replay terminal is missing")
        terminal_raw = terminal_path.read_bytes()
        terminal, _ = _json(terminal_path, "parallel replay terminal")
        result = terminal.get("candidate_result")
        artifact = result.get("native_envelope_artifact") if isinstance(result, Mapping) else None
        _need(
            _sha(terminal_raw) == row.get("terminal_sha256")
            and terminal.get("source_epoch") == SOURCE_EPOCH
            and terminal.get("ordinal") == ordinal
            and terminal.get("state") == "completed"
            and terminal.get("native_identity") == identity
            and isinstance(artifact, Mapping)
            and artifact.get("sha256") == row.get("native_envelope_sha256")
            and terminal.get("native_envelope_sha256") == row.get("native_envelope_sha256"),
            "parallel replay receipt terminal binding differs",
        )
    return list(ordinals)


def _completed_new(
    root: Path, pending: Sequence[int], *, manifest: Mapping[str, Any] | None = None, manifest_raw: bytes | None = None
) -> tuple[list[int], dict[int, dict[str, Any]], dict[int, Path]]:
    records = _records(root)
    completed: list[int] = []
    terminals: dict[int, dict[str, Any]] = {}
    receipts: dict[int, Path] = {}
    replay_paths = list((root / "replays").glob("wave-*-slots-*-replay.json")) if (root / "replays").exists() else []
    replayed: set[int] = set()
    for path in replay_paths:
        replay, _ = _json(path, "parallel replay")
        _need(manifest is not None and manifest_raw is not None, "parallel replay manifest binding is missing")
        ordinals = _validate_replay_receipt(root=root, manifest=manifest, manifest_raw=manifest_raw, pending=pending, replay_path=path, replay=replay)
        _need(not replayed.intersection(ordinals), "parallel replay duplicate ordinal")
        for ordinal in ordinals:
            receipts[ordinal] = path
        replayed.update(ordinals)
    for ordinal in pending:
        terminal = records.get(ordinal)
        if terminal is None:
            break
        _need(ordinal in replayed and terminal.get("state") == "completed", "parallel prior cell is not semantically replayed")
        completed.append(ordinal)
        terminals[ordinal] = terminal
    _need(replayed == set(completed), "parallel replay is not a contiguous exact prefix")
    for ordinal, terminal in records.items():
        if ordinal in pending and ordinal not in completed:
            _need(terminal is None, "parallel attempt is incomplete or skipped")
    return completed, terminals, receipts


def _fresh_source_checks(
    state: Mapping[str, Any],
    *,
    wave_raw: bytes | None = None,
    wave_start: int | None = None,
    wave_size: int | None = None,
    row: Mapping[str, Any] | None = None,
) -> None:
    root = state["root"]
    manifest_path = _manifest_path(root)
    _need(manifest_path.read_bytes() == state["manifest_raw"], "parallel manifest changed before contact")
    closure = state["closure"]
    controller = _descriptor(_closure_value(closure, "prior_controller", "historical_controller"), "prior controller")
    _need(_sha(Path(controller["path"]).read_bytes()) == controller["sha256"], "prior controller changed before contact")
    continuation = _closure_value(closure, "prior_continuation", "historical_continuation")
    _need(_sha(Path(continuation["manifest_path"]).read_bytes()) == continuation["manifest_sha256"], "prior continuation changed before contact")
    _bound(_closure_value(closure, "stopped_prefix"), "stopped prefix")
    candidate = _candidate_binding(closure)
    _source_semantics(closure, candidate_manifest_sha256=candidate["manifest_sha256"])
    _queue_binding(_closure_value(closure, "queue"))
    if wave_raw is not None:
        _need(
            type(wave_start) is int
            and type(wave_size) is int
            and _wave_path(root, wave_start, wave_size, "intent").read_bytes() == wave_raw,
            "parallel wave intent changed before contact",
        )
    if row is not None:
        fresh = _row_for(state, row["ordinal"])
        _need(fresh["prompt"] == row["prompt"] and fresh["source"] == row["source"] and fresh["question_ids"] == row["question_ids"], "parallel source changed before contact")


def _contact_outcome(broker: Any, route: Mapping[str, Any], row: Mapping[str, Any], schema: Mapping[str, Any], session_id: str, before_contact: Any) -> Any:
    _need(hasattr(broker, "run_grok_native_request"), "candidate broker contact contract differs")
    return broker.run_grok_native_request(
        route.get("name") or route.get("model"),
        {"prompt": row["prompt"]},
        output_schema=schema,
        nonvisual_max_turns=1,
        session_id=session_id,
        expected_route_sha256=route.get("sha256"),
        before_contact=before_contact,
    )


def _result_identity(result: Mapping[str, Any]) -> dict[str, Any]:
    runtime = result.get("runtime") if isinstance(result.get("runtime"), Mapping) else result
    values = {
        "request_id_hash": runtime.get("request_id_hash", runtime.get("request_id_sha256")),
        "session_id_hash": runtime.get("session_id_hash", runtime.get("session_id_sha256")),
        "observed_turns": runtime.get("observed_turns"),
    }
    return _native_identity(values)


def _normalize(state: Mapping[str, Any], row: Mapping[str, Any], result: Mapping[str, Any], ordinal: int) -> list[dict[str, Any]]:
    output = result.get("output")
    context = state["prior"].get("context")
    runtime = getattr(context, "runtime", None)
    if runtime is None and isinstance(context, Mapping):
        runtime = context.get("runtime")
    runner = getattr(runtime, "runner", None)
    if runner is None and isinstance(runtime, Mapping):
        runner = runtime.get("runner")
    normalize = getattr(runner, "_normalize_batch", None)
    _need(callable(normalize), "prior runtime normalizer contract differs")
    source = row["source"]
    _need(isinstance(getattr(runner, "EVIDENCE_NORMALIZATION_POLICY", None), str), "prior runtime normalization policy differs")
    normalized = normalize(
        output,
        expected_ids=row["question_ids"],
        artifact_id=source.get("opaque_story_id"),
        bundle_id="prose.short_story",
        judge_id="grok:grok-4.6",
        run_id=f"{SOURCE_EPOCH}/{ordinal}",
        artifact_text=source["story_text"],
        context_texts=[],
        normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY,
        repair_audit=[],
    )
    _need(isinstance(normalized, list), "parallel verdicts differ")
    return [dict(item) if isinstance(item, Mapping) else item for item in normalized]


def _candidate_adapter(candidate: Any) -> Any:
    adapter = getattr(candidate, "adapter", None)
    if adapter is not None:
        return adapter
    package = getattr(candidate, "__package__", None)
    _need(isinstance(package, str) and package, "candidate adapter package differs")
    return importlib.import_module(package + ".adapters.grok_exec")


def _semantic_replay_terminal(state: Mapping[str, Any], row: Mapping[str, Any], terminal: Mapping[str, Any], broker: Any) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    terminal_path = _attempt(state["root"], row["ordinal"], "terminal.json")
    terminal_raw = terminal_path.read_bytes()
    _need(terminal.get("state") == "completed" and isinstance(terminal.get("candidate_result"), Mapping), "parallel terminal semantic replay differs")
    result = terminal["candidate_result"]
    descriptor = result.get("native_envelope_artifact")
    _need(isinstance(descriptor, Mapping) and hasattr(broker, "read_grok_native_envelope"), "parallel native envelope contract differs")
    envelope = broker.read_grok_native_envelope(dict(descriptor))
    _need(_sha(envelope) == descriptor.get("sha256") and len(envelope) == descriptor.get("byte_length"), "parallel native envelope differs")
    route = terminal.get("review_route")
    _need(isinstance(route, Mapping), "parallel terminal route differs")
    session_id = terminal.get("session_id")
    _need(
        isinstance(session_id, str)
        and route.get("model")
        and route.get("reported_model")
        and route.get("sha256") == state["source"]["route"]["route_sha256"]
        and terminal.get("route_sha256") == state["source"]["route"]["route_sha256"],
        "parallel terminal session differs",
    )
    schema = row["schema"]
    parsed = broker._parse_grok_exec_envelope(
        _canon({"control": {"version": 1, "state": "completed"}, "result": dict(result)}),
        {**dict(route), "output_schema": schema, "nonvisual_max_turns": 1},
        {"prompt": row["prompt"]},
        expected_session_id=session_id,
    )
    adapter = _candidate_adapter(state["candidate"]["candidate"])
    output, raw_identity, _usage = adapter._parse_grok_envelope(
        envelope,
        model=route["model"],
        reported_model=route["reported_model"],
        session_id=session_id,
        schema=schema,
        max_turns=1,
        exact_turns=True,
    )
    identity = _native_identity(raw_identity, "parallel native identity")
    normalized = _normalize(state, row, {**dict(result), "output": output}, row["ordinal"])
    _need(
        getattr(parsed, "state", None) == "completed"
        and getattr(parsed, "result", None) == result
        and output == result.get("output")
        and identity == terminal.get("native_identity")
        and normalized == terminal.get("verdicts"),
        "parallel semantic replay differs",
    )
    _need(terminal_path.read_bytes() == terminal_raw, "parallel terminal changed during semantic replay")
    return identity, normalized, descriptor.get("sha256")


def _construct_broker(
    candidate: Mapping[str, Any],
    queue: Path,
    ordinal: int,
    row: Mapping[str, Any],
    broker_factory: Any | None,
    host_gate_path: Path,
) -> Any:
    factory = broker_factory or getattr(candidate["candidate"], "Broker", None)
    _need(factory is not None, "candidate broker constructor differs")
    if broker_factory is not None:
        for args in ((queue, ordinal, row), (queue, ordinal), (queue,), ()):
            try:
                return factory(*args)
            except TypeError:
                continue
        raise ValueError("candidate broker constructor differs")
    return factory(queue, grok_host_gate_path=host_gate_path)


class _PreflightStop(RuntimeError):
    pass


def _preflight_candidate(state: Mapping[str, Any], row: Mapping[str, Any], broker: Any) -> None:
    """Run the candidate's supported route/gate preflight without provider contact."""
    _need(hasattr(broker, "run_grok_native_request"), "candidate broker preflight contract differs")
    route = dict(state["source"]["route"]["route"])
    route.setdefault("sha256", state["source"]["route"]["route_sha256"])

    def stop_before_contact() -> None:
        raise _PreflightStop("parallel preflight stop")

    outcome = broker.run_grok_native_request(
        route.get("name") or route.get("model"),
        {"prompt": row["prompt"]},
        output_schema=row["schema"],
        nonvisual_max_turns=1,
        session_id=str(uuid.uuid4()),
        expected_route_sha256=state["source"]["route"]["route_sha256"],
        before_contact=stop_before_contact,
    )
    _need(
        isinstance(outcome, Mapping)
        and outcome.get("state") == "definitely_not_contacted"
        and isinstance(outcome.get("failure"), Mapping)
        and outcome["failure"].get("code") == "before_contact_failed",
        "candidate route/gate preflight did not stop before contact",
    )


def _error_info(error: BaseException) -> dict[str, Any]:
    frames = traceback.extract_tb(error.__traceback__)
    frame = frames[-1] if frames else None
    return {"error_type": type(error).__name__, "source": Path(frame.filename).name if frame else "unknown", "line": frame.lineno if frame else 0}


def dispatch_wave(
    *,
    continuation_root: Path | str,
    expected_manifest_sha256: str,
    start_ordinal: int,
    wave_size: int,
    broker_factory: Any | None = None,
) -> dict[str, Any]:
    """Contact one exact contiguous wave and settle it before advancing."""
    root = Path(continuation_root).resolve()
    _need(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= WAVE_CAP, "parallel wave geometry differs")
    state = _state(root, expected_manifest_sha256)
    pending = state["manifest"]["pending_ordinals"]
    completed, _terminals, _receipts = _completed_new(
        root, pending, manifest=state["manifest"], manifest_raw=state["manifest_raw"]
    )
    next_index = len(completed)
    _need(next_index < len(pending) and start_ordinal == pending[next_index], "parallel wave is not the exact next cell")
    wave_ordinals = pending[next_index : next_index + wave_size]
    _need(len(wave_ordinals) == wave_size, "parallel wave exceeds pending suffix")
    _need(not any(_attempt(root, ordinal, "attempt-start.json").exists() for ordinal in wave_ordinals), "parallel attempt intent already exists")
    _need(state["source"].get("shared_fix") is not None, "shared contention fix receipt required")
    rows = [_row_for(state, ordinal) for ordinal in wave_ordinals]
    wave_value = {
        "schema_version": 1,
        "source_epoch": SOURCE_EPOCH,
        "controller_sha256": state["manifest"]["controller_sha256"],
        "manifest_sha256": _sha(state["manifest_raw"]),
        "start_ordinal": start_ordinal,
        "wave_size": wave_size,
        "ordinals": wave_ordinals,
        "route_sha256": state["source"]["route"]["route_sha256"],
        "candidate_manifest_sha256": state["candidate"]["manifest_sha256"],
        "provider_calls_made": 0,
    }
    # Build every broker before the first durable wave/attempt intent.  A
    # constructor failure therefore leaves the untouched suffix retryable.
    brokers = {
        row["ordinal"]: _construct_broker(
            state["candidate"], state["queue"]["path"], row["ordinal"], row, broker_factory, state["source"]["gate_path"]
        )
        for row in rows
    }
    if broker_factory is None:
        _preflight_candidate(state, rows[0], brokers[rows[0]["ordinal"]])
    intent_path = _wave_path(root, start_ordinal, wave_size, "intent")
    _new(intent_path, wave_value)
    intent_raw = intent_path.read_bytes()
    for slot, row in enumerate(rows):
        start = {
            "schema_version": 1,
            "source_epoch": SOURCE_EPOCH,
            "ordinal": row["ordinal"],
            "manifest_sha256": _sha(state["manifest_raw"]),
            "wave": {"start": start_ordinal, "size": wave_size, "slot": slot, "ordinals": wave_ordinals},
            "prompt_sha256": row["prompt_sha256"],
            "schema_sha256": row["schema_sha256"],
            "question_ids": row["question_ids"],
            "source_sha256": row["source_sha256"],
            "route_sha256": state["source"]["route"]["route_sha256"],
            "candidate_manifest_sha256": state["candidate"]["manifest_sha256"],
        }
        _new(_attempt(root, row["ordinal"], "attempt-start.json"), start)
    stop = threading.Event()
    lock = threading.Lock()
    used_identities = list(state["prior"]["identities"])
    for ordinal in completed:
        terminal = _records(root).get(ordinal)
        if isinstance(terminal, Mapping) and isinstance(terminal.get("native_identity"), Mapping):
            used_identities.append(dict(terminal["native_identity"]))
    outcomes: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    def run_cell(row: Mapping[str, Any]) -> dict[str, Any]:
        ordinal = row["ordinal"]
        admitted = False
        session = str(uuid.uuid4())
        outcome: Any = None
        result: Any = None
        identity: Any = None
        start_path = _attempt(root, ordinal, "attempt-start.json")
        try:
            def before_contact() -> None:
                nonlocal admitted
                _need(not stop.is_set(), "parallel wave stopped before contact")
                _fresh_source_checks(state, wave_raw=intent_raw, wave_start=start_ordinal, wave_size=wave_size, row=row)
                _need(state["source"]["shared_fix"] is not None, "shared contention fix receipt required")
                _new(_attempt(root, ordinal, "contact-admission.json"), {
                    "source_epoch": SOURCE_EPOCH,
                    "ordinal": ordinal,
                    "manifest_sha256": _sha(state["manifest_raw"]),
                    "attempt_start_sha256": _sha(start_path.read_bytes()),
                    "wave_intent_sha256": _sha(intent_raw),
                    "route_sha256": state["source"]["route"]["route_sha256"],
                })
                admitted = True

            route = dict(state["source"]["route"]["route"])
            route.setdefault("sha256", state["source"]["route"]["route_sha256"])
            outcome = _contact_outcome(brokers[ordinal], route, row, row["schema"], session, before_contact)
            result = outcome.get("result") if isinstance(outcome, Mapping) and isinstance(outcome.get("result"), Mapping) else outcome
            _need(isinstance(outcome, Mapping) and outcome.get("state", "completed") == "completed" and isinstance(result, Mapping) and admitted, "parallel broker outcome stopped")
            identity = _result_identity(result)
            verdicts = _normalize(state, row, result, ordinal)
            with lock:
                _need(_identities_unique([*used_identities, identity]), "parallel native identity collision")
                used_identities.append(identity)
            terminal = {
                "schema_version": 1,
                "source_epoch": SOURCE_EPOCH,
                "ordinal": ordinal,
                "state": "completed",
                "attempt_start_sha256": _sha(start_path.read_bytes()),
                "session_id": session,
                "review_route": route,
                "route_sha256": state["source"]["route"]["route_sha256"],
                "candidate_manifest_sha256": state["candidate"]["manifest_sha256"],
                "broker_outcome": dict(outcome),
                "candidate_result": dict(result),
                "native_identity": identity,
                "verdicts": verdicts,
                "native_envelope_sha256": (
                    result.get("native_envelope_artifact", {}).get("sha256")
                    if isinstance(result.get("native_envelope_artifact"), Mapping)
                    else None
                ),
            }
        except Exception as error:  # noqa: BLE001 - persist every in-flight outcome.
            stop.set()
            terminal = {
                "schema_version": 1,
                "source_epoch": SOURCE_EPOCH,
                "ordinal": ordinal,
                "state": "ambiguous" if admitted else "definitely_not_contacted",
                "attempt_start_sha256": _sha(start_path.read_bytes()),
                "session_id": session,
                "contact_admitted": admitted,
                "broker_outcome": outcome,
                "error": _error_info(error),
            }
            if isinstance(result, Mapping):
                terminal["candidate_result"] = dict(result)
            if isinstance(identity, Mapping):
                terminal["native_identity"] = dict(identity)
            with lock:
                errors.append({"ordinal": ordinal, **_error_info(error), "contact_admitted": admitted})
        _new(_attempt(root, ordinal, "terminal.json"), terminal)
        with lock:
            outcomes[ordinal] = terminal
        return terminal

    with ThreadPoolExecutor(max_workers=wave_size, thread_name_prefix="grok-parallel") as executor:
        futures: dict[Future[dict[str, Any]], int] = {executor.submit(run_cell, row): row["ordinal"] for row in rows}
        while futures:
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                future.result()
    completed_terminals = [outcomes[item] for item in wave_ordinals if outcomes[item].get("state") == "completed"]
    semantic_error: dict[str, Any] | None = None
    if not errors and len(completed_terminals) == wave_size:
        try:
            for row in rows:
                terminal = outcomes[row["ordinal"]]
                identity, verdicts, envelope_sha = _semantic_replay_terminal(state, row, terminal, brokers[row["ordinal"]])
                _need(identity == terminal["native_identity"] and verdicts == terminal["verdicts"], "parallel semantic replay differs")
                _need(envelope_sha == terminal.get("native_envelope_sha256"), "parallel native envelope binding differs")
        except Exception as error:  # noqa: BLE001 - preserve completed terminals and block advancement.
            semantic_error = _error_info(error)
            stop.set()
    replay_path: Path | None = None
    if not errors and semantic_error is None and len(completed_terminals) == wave_size:
        entries = []
        for ordinal in wave_ordinals:
            terminal_path = _attempt(root, ordinal, "terminal.json")
            terminal = outcomes[ordinal]
            _need(terminal_path.read_bytes() == _canon(terminal), "parallel terminal changed")
            entries.append({
                "ordinal": ordinal,
                "terminal_sha256": _sha(terminal_path.read_bytes()),
                "native_envelope_sha256": terminal.get("native_envelope_sha256"),
                "native_identity": terminal["native_identity"],
            })
        replay_path = _replay_path(root, start_ordinal, wave_size)
        _new(replay_path, {
            "schema_version": 1,
            "evidence_class": "source_bound_grok_parallel_successor_replay_v1",
            "source_epoch": SOURCE_EPOCH,
            "controller_sha256": state["manifest"]["controller_sha256"],
            "manifest_sha256": _sha(state["manifest_raw"]),
            "root": str(root),
            "ordinals": wave_ordinals,
            "terminals": entries,
            "native_identities": [entry["native_identity"] for entry in entries],
            "provider_calls_made": 0,
        })
    settlement = {
        "schema_version": 1,
        "source_epoch": SOURCE_EPOCH,
        "controller_sha256": state["manifest"]["controller_sha256"],
        "manifest_sha256": _sha(state["manifest_raw"]),
        "start_ordinal": start_ordinal,
        "wave_size": wave_size,
        "ordinals": wave_ordinals,
        "wave_intent_sha256": _sha(intent_raw),
        "replay_sha256": _sha(replay_path.read_bytes()) if replay_path else None,
        "provider_calls_made": len([item for item in outcomes.values() if isinstance(item.get("broker_outcome"), Mapping) and item["broker_outcome"].get("state") == "completed"]),
    }
    _new(_wave_path(root, start_ordinal, wave_size, "settlement"), settlement)
    if semantic_error is not None:
        errors.append({"ordinal": start_ordinal, **semantic_error, "phase": "semantic_replay"})
    complete = replay_path is not None and len(completed_terminals) == wave_size
    return {
        "state": "completed_replayed" if complete else "stopped_no_retry",
        "source_epoch": SOURCE_EPOCH,
        "start_ordinal": start_ordinal,
        "wave_size": wave_size,
        "ordinals": wave_ordinals,
        "completed_ordinals": wave_ordinals if complete else [ordinal for ordinal in wave_ordinals if outcomes.get(ordinal, {}).get("state") == "completed"],
        "provider_calls_made": settlement["provider_calls_made"] if not any(item.get("contact_admitted") and item.get("state") != "completed" for item in outcomes.values()) else None,
        "replay_path": str(replay_path) if replay_path else None,
        "errors": errors,
    }


def _read_records(state: Mapping[str, Any], *, require_complete: bool, semantic: bool) -> dict[str, Any]:
    pending = state["manifest"]["pending_ordinals"]
    completed, terminals, receipts = _completed_new(
        state["root"], pending, manifest=state["manifest"], manifest_raw=state["manifest_raw"]
    )
    if require_complete:
        _need(completed == list(pending), "parallel collection is incomplete")
        for ordinal in completed:
            terminal_path = _attempt(state["root"], ordinal, "terminal.json")
            terminal, _ = _json(terminal_path, "parallel terminal")
            _need(terminal.get("source_epoch") == SOURCE_EPOCH, "parallel terminal source epoch differs")
            if semantic:
                row = _row_for(state, ordinal)
                broker = _construct_broker(
                    state["candidate"], state["queue"]["path"], ordinal, row, None, state["source"]["gate_path"]
                )
                _semantic_replay_terminal(state, row, terminal, broker)
    replayed_records: list[dict[str, Any]] = []
    for ordinal in completed:
        terminal_path = _attempt(state["root"], ordinal, "terminal.json")
        terminal = terminals[ordinal]
        result = terminal.get("candidate_result") if isinstance(terminal.get("candidate_result"), Mapping) else {}
        descriptor = result.get("native_envelope_artifact") if isinstance(result, Mapping) else None
        replayed_records.append({
            "ordinal": ordinal,
            "verdicts": terminal.get("verdicts"),
            "native_identity": terminal.get("native_identity"),
            "terminal": {"path": str(terminal_path), "sha256": _sha(terminal_path.read_bytes())},
            "native_envelope_sha256": terminal.get("native_envelope_sha256") or (descriptor.get("sha256") if isinstance(descriptor, Mapping) else None),
            "source_epoch": SOURCE_EPOCH,
            "root": str(state["root"]),
            "manifest_sha256": _sha(state["manifest_raw"]),
            "controller_sha256": state["manifest"]["controller_sha256"],
        })
    return {"completed_ordinals": completed, "terminals": terminals, "receipts": receipts, "records": replayed_records}


def replay_collection(*, continuation_root: Path | str, expected_manifest_sha256: str, require_complete: bool = True) -> dict[str, Any]:
    """Read settled new-wave records without mutating the continuation root."""
    root = Path(continuation_root).resolve()
    state = _state(root, expected_manifest_sha256, semantic_prior=False)
    before = {path: _sha(Path(path).read_bytes()) for path in [str(_manifest_path(root))] if Path(path).is_file()}
    records = _read_records(state, require_complete=require_complete, semantic=require_complete)
    _need(all(Path(path).is_file() and _sha(Path(path).read_bytes()) == digest for path, digest in before.items()), "parallel reader changed manifest")
    pending = [ordinal for ordinal in state["manifest"]["pending_ordinals"] if ordinal not in records["completed_ordinals"]]
    return {
        "source_epoch": SOURCE_EPOCH,
        "manifest": state["manifest"],
        "manifest_sha256": _sha(state["manifest_raw"]),
        "plan_root": str(state["plan_root"]),
        "prior_continuation": {
            "root": str(state["prior"]["root"]),
            "manifest_sha256": state["prior"]["manifest_sha256"],
            "controller_sha256": state["manifest"]["source_closure"]["prior_controller"]["sha256"],
        },
        "prior_completed_ordinals": list(state["prior"]["completed"]),
        "pending_ordinals": pending,
        "completed_ordinals": records["completed_ordinals"],
        "records": records["records"],
        "protected_paths": state["manifest"]["protected_paths"],
        "local_recoveries": [state["local_recovery"]] if state["local_recovery"] is not None else [],
        "source_closure": state["manifest"]["source_closure"],
        "provider_calls_made": 0,
    }


__all__ = ["MAX_WAVE_SIZE", "SOURCE_EPOCH", "WAVE_CAP", "_canon", "_identities_unique", "_sha", "create", "dispatch_wave", "replay_collection", "verify"]
