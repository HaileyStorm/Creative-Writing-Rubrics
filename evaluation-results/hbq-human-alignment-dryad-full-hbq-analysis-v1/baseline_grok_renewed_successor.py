"""Append-only, provider-free controller for the F366 route renewal.

The historical runtime-data successor remains immutable evidence.  This
module binds that source epoch and the retained 280..337 prefix, then owns a
fresh one-cell-at-a-time suffix beginning at ordinal 338.  The fresh route is
used only by prospective contacts; historical terminals continue to replay
through the historical controller and runtime.
"""
from __future__ import annotations

import hashlib
import importlib
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

ROOT = Path(__file__).resolve().parent
CWR_ROOT = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-fresh-verify")
HISTORICAL_CONTROLLER = (
    CWR_ROOT
    / "evaluation-results"
    / "hbq-human-alignment-dryad-full-hbq-analysis-v1"
    / "baseline_grok_runtime_data_successor.py"
)
HISTORICAL_CONTROLLER_SHA256 = (
    "818124921ed9153e2d85c3ab69fb746584af24d307592153824c1d1d8b5e1085"
)
HISTORICAL_ROOT = Path(
    r"C:\Users\Haile\Documents\cwr-dryad-grok-runtime-data-successor-20260912-r1"
)
HISTORICAL_MANIFEST = HISTORICAL_ROOT / "runtime-data-successor-manifest.json"
HISTORICAL_MANIFEST_SHA256 = (
    "9489e98abff81262dffb2076435a30a46a7982380a309f28e5260065f8e2e4d4"
)
RETAINED_PREFIX = (
    CWR_ROOT.parent / "cwr-grok-successor-control-20260914-r1" / "current-prefix.json"
)
RETAINED_PREFIX_SHA256 = (
    "8293b5842c1bc4243bfad1aea1edb25a92c1b16f05d09315bf75d7f483cf8949"
)
PENDING = [*range(338, 1611), *range(4049, 4739)]
WAVE_CAP = 1
LOCAL_RECOVERY_ORDINALS = [70, 254]
SOURCE_EPOCH = "grok_runtime_data_renewal_20260914_r1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_CLOSURE_KEYS = {
    "historical_controller",
    "historical_continuation",
    "retained_prefix",
    "route",
    "gate",
    "standing_source",
    "packet",
}
_MANIFEST_KEYS = {
    "schema_version",
    "evidence_class",
    "source_epoch",
    "controller_sha256",
    "source_closure",
    "source_closure_sha256",
    "pending_ordinals",
    "operational_wave_cap",
    "provider_calls_made",
    "execution_authority",
}
_REVIEW_KEYS = {
    "schema_version",
    "decision",
    "source_epoch",
    "controller_sha256",
    "manifest_sha256",
    "source_closure_sha256",
    "historical_manifest_sha256",
    "retained_prefix_sha256",
    "candidate_manifest_sha256",
    "packet_sha256",
    "standing_source_sha256",
    "first_ordinal",
    "operational_wave_cap",
    "route_name",
    "route",
    "route_sha256",
    "gate_evidence_path",
    "gate_evidence_sha256",
    "gate_sha256",
    "gate_identity",
    "reviewed_at",
    "expires_at",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
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


def _bound(value: Any, label: str) -> Mapping[str, Any]:
    descriptor = _descriptor(value, label)
    try:
        raw = Path(descriptor["path"]).read_bytes()
    except OSError as error:
        raise ValueError(f"{label} source drift") from error
    _need(_sha(raw) == descriptor["sha256"], f"{label} source drift")
    return descriptor


def _route(value: Any) -> Mapping[str, Any]:
    _need(
        isinstance(value, Mapping)
        and isinstance(value.get("name"), str)
        and isinstance(value.get("sha256"), str)
        and _HASH.fullmatch(value["sha256"]) is not None,
        "renewed route descriptor differs",
    )
    return value


def _load_historical(path: Path, expected: str) -> ModuleType:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, "historical controller source pin differs")
    spec = importlib.util.spec_from_file_location(
        "_grok_renewed_historical_controller", path
    )
    _need(
        spec is not None and spec.loader is not None,
        "historical controller load differs",
    )
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    _need(path.read_bytes() == raw, "historical controller changed while loading")
    return module


def _native_identity(value: Any, label: str) -> dict[str, Any]:
    _need(
        isinstance(value, Mapping)
        and set(value) == {"request_id_hash", "session_id_hash", "observed_turns"},
        f"{label} differs",
    )
    result = dict(value)
    _need(
        all(
            isinstance(result[key], str) and _HASH.fullmatch(result[key])
            for key in ("request_id_hash", "session_id_hash")
        )
        and type(result["observed_turns"]) is int
        and result["observed_turns"] == 1,
        f"{label} differs",
    )
    return result


def _identities_unique(values: list[Mapping[str, Any]]) -> bool:
    # Historical commitments retain only these two hashes. New native records
    # are separately validated by _native_identity before entering this union.
    if not all(isinstance(value, Mapping) for value in values):
        return False
    requests = [value.get("request_id_hash") for value in values]
    sessions = [value.get("session_id_hash") for value in values]
    return (
        all(isinstance(value, str) and _HASH.fullmatch(value) for value in requests + sessions)
        and len(requests) == len(set(requests))
        and len(sessions) == len(set(sessions))
    )


def _under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _historical_binding(closure: Mapping[str, Any]) -> tuple[dict[str, Any], bytes]:
    continuation = closure["historical_continuation"]
    _need(
        isinstance(continuation, Mapping)
        and set(continuation)
        == {"root", "manifest_path", "manifest_sha256"},
        "historical continuation binding differs",
    )
    root = Path(str(continuation["root"])).resolve()
    manifest_path = Path(str(continuation["manifest_path"])).resolve()
    _need(
        root == HISTORICAL_ROOT.resolve()
        and manifest_path == HISTORICAL_MANIFEST.resolve()
        and continuation["manifest_sha256"] == HISTORICAL_MANIFEST_SHA256,
        "historical continuation binding differs",
    )
    raw = manifest_path.read_bytes()
    _need(
        _sha(raw) == continuation["manifest_sha256"],
        "historical continuation manifest drift",
    )
    value, _ = _json(manifest_path, "historical continuation manifest")
    _need(
        value.get("controller_sha256") == HISTORICAL_CONTROLLER_SHA256
        and value.get("execution_authority") is False
        and value.get("provider_calls_made") == 0,
        "historical continuation manifest differs",
    )
    return value, raw


def _prefix_bindings(
    descriptor: Mapping[str, Any], continuation: Mapping[str, Any]
) -> dict[str, Any]:
    _need(
        Path(str(descriptor["path"])).resolve() == RETAINED_PREFIX.resolve()
        and descriptor["sha256"] == RETAINED_PREFIX_SHA256,
        "retained prefix source differs",
    )
    value, raw = _json(Path(descriptor["path"]), "retained current prefix")
    required = {
        "kind",
        "recorded_at",
        "manifest",
        "completed_ordinals_in_current_root",
        "current_native_count",
        "request_identity_count",
        "session_identity_count",
        "current_records",
        "remaining_ordinals",
        "remaining_count",
        "next_ordinal",
        "local_recoveries_separate",
        "historical_pre280_replayed_in_this_check",
        "fresh_semantic_replay_performed",
        "provider_calls_made",
        "automatic_resend_authorized",
        "activation_authority",
        "scope",
    }
    _need(set(value) == required, "retained current prefix schema differs")
    _need(
        value["kind"] == "cwr_retained_current_prefix_bindings_v1"
        and value["completed_ordinals_in_current_root"] == list(range(280, 338))
        and value["current_native_count"]
        == value["request_identity_count"]
        == value["session_identity_count"]
        == 58
        and value["remaining_ordinals"] == PENDING
        and value["remaining_count"] == len(PENDING)
        and value["next_ordinal"] == 338
        and value["local_recoveries_separate"] == LOCAL_RECOVERY_ORDINALS
        and value["historical_pre280_replayed_in_this_check"] is False
        and value["fresh_semantic_replay_performed"] is False
        and value["provider_calls_made"] == 0
        and value["automatic_resend_authorized"] is False
        and value["activation_authority"] is False,
        "retained current prefix boundary differs",
    )
    _need(
        value["manifest"] == {
            "path": continuation["manifest_path"],
            "sha256": continuation["manifest_sha256"],
        },
        "retained current prefix manifest binding differs",
    )
    records = value["current_records"]
    _need(
        isinstance(records, list)
        and len(records) == 58
        and all(isinstance(record, Mapping) for record in records)
        and [record.get("ordinal") for record in records]
        == list(range(280, 338)),
        "retained current prefix records differ",
    )
    identities: list[dict[str, Any]] = []
    for ordinal, record in zip(range(280, 338), records, strict=True):
        _need(
            isinstance(record, Mapping)
            and set(record) == {"ordinal", "intent", "terminal", "replay", "native_identity"}
            and record["ordinal"] == ordinal,
            "retained current prefix record differs",
        )
        for name in ("intent", "terminal", "replay"):
            bound = _bound(record[name], f"retained {name}")
            path = Path(bound["path"]).resolve()
            _need(_under(path, HISTORICAL_ROOT), f"retained {name} escapes historical root")
        intent, _intent_raw = _json(
            Path(record["intent"]["path"]), "retained attempt intent"
        )
        terminal, _terminal_raw = _json(
            Path(record["terminal"]["path"]), "retained terminal"
        )
        replay, _replay_raw = _json(
            Path(record["replay"]["path"]), "retained replay"
        )
        identity = _native_identity(
            record["native_identity"], "retained native identity"
        )
        _need(
            intent.get("ordinal") == ordinal
            and terminal.get("ordinal") == ordinal
            and terminal.get("state") == "completed"
            and terminal.get("attempt_start_sha256") == record["intent"]["sha256"]
            and terminal.get("native_identity") == identity
            and replay.get("ordinals") == [ordinal]
            and replay.get("native_identities") == [identity]
            and isinstance(replay.get("terminals"), list)
            and len(replay["terminals"]) == 1
            and replay["terminals"][0].get("ordinal") == ordinal
            and replay["terminals"][0].get("terminal_sha256") == record["terminal"]["sha256"]
            and replay.get("provider_calls_made") == 0,
            "retained current prefix semantic binding differs",
        )
        identities.append(identity)
    _need(
        _identities_unique(identities),
        "retained current prefix native identity collision",
    )
    return {"value": value, "raw": raw, "identities": identities, "sha256": _sha(raw)}


def _renewed_sources(
    closure: Mapping[str, Any], historical_manifest: Mapping[str, Any]
) -> dict[str, Any]:
    route = _route(closure["route"])
    for name in ("gate", "standing_source", "packet"):
        _bound(closure[name], f"renewed {name}")
    old_closure = historical_manifest.get("source_closure")
    if isinstance(old_closure, Mapping):
        old_route = old_closure.get("route")
        if isinstance(old_route, Mapping) and isinstance(old_route.get("sha256"), str):
            _need(
                route["sha256"] != old_route["sha256"],
                "renewed route reused historical hash",
            )
    gate, _gate_raw = _json(Path(closure["gate"]["path"]), "renewed gate")
    packet, _packet_raw = _json(Path(closure["packet"]["path"]), "renewed packet")
    standing, _standing_raw = _json(
        Path(closure["standing_source"]["path"]), "renewed standing source"
    )
    _need(
        all(
            isinstance(gate.get(key), (str, int))
            for key in (
                "provider",
                "account_class",
                "contract_hash",
                "source_evidence_hash",
                "updated_at",
            )
        )
        and gate.get("state") == "healthy"
        and type(gate.get("max_concurrency")) is int
        and gate.get("max_concurrency") >= 1
        and gate.get("source_evidence_hash")
        == closure["standing_source"]["sha256"],
        "renewed gate is not healthy and bound",
    )
    candidate_manifest = packet.get("candidate_manifest")
    renewed_source = packet.get("renewed_source")
    actions = packet.get("actions")
    packet_scope = packet.get("scope")
    _need(
        packet.get("schema_version") == 1
        and packet.get("kind") == "grok_standing_authority_v6_append_only_renewal_packet"
        and packet.get("state") == "renewal_sealed_provider_free"
        and isinstance(candidate_manifest, Mapping)
        and isinstance(candidate_manifest.get("path"), str)
        and candidate_manifest.get("sha256")
        == historical_manifest["source_closure"]["candidate"]["manifest_sha256"]
        and isinstance(renewed_source, Mapping)
        and isinstance(renewed_source.get("path"), str)
        and renewed_source.get("sha256") == closure["standing_source"]["sha256"]
        and isinstance(renewed_source.get("checked_at"), str)
        and isinstance(renewed_source.get("expires_at"), str)
        and isinstance(renewed_source.get("authority_at"), str)
        and renewed_source.get("fresh_allowance_observation") is False
        and renewed_source.get("new_owner_statement") is False
        and isinstance(actions, Mapping)
        and all(
            actions.get(key) is False
            for key in (
                "activation_authority",
                "provider_contact_authority",
                "installed_source_mutated",
                "live_route_mutated",
                "live_gate_mutated",
                "enqueue",
                "dispatch",
                "request_1088_resend",
            )
        )
        and actions.get("provider_contact_count") == 0
        and isinstance(packet_scope, Mapping)
        and packet_scope.get("automatic_resend") is False
        and packet_scope.get("zero_charge_only") is True
        and packet_scope.get("paid_fallback") is False,
        "renewed packet is not sealed and inert",
    )
    scope = standing.get("authorization", {}).get("scope")
    queue = historical_manifest["source_closure"].get("queue")
    _need(
        standing.get("schema_version") == 3
        and isinstance(standing.get("provider"), str)
        and isinstance(standing.get("account_class"), str)
        and standing.get("allowance_state") == "available"
        and isinstance(standing.get("checked_at"), str)
        and isinstance(standing.get("expires_at"), str)
        and _time(standing["checked_at"], "renewed standing checked_at")
        < _time(standing["expires_at"], "renewed standing expires_at")
        and _time(standing["expires_at"], "renewed standing expires_at")
        > datetime.now(timezone.utc)
        and isinstance(scope, Mapping)
        and scope.get("automatic_resend") is False
        and scope.get("zero_charge_only") is True
        and scope.get("paid_fallback") is False
        and scope.get("route") == route["name"]
        and isinstance(queue, Mapping)
        and scope.get("broker_root_hash") == queue.get("root_hash"),
        "renewed standing source is not available and bound",
    )
    return {"route": route, "gate": gate, "packet": packet, "standing": standing}


def _manifest(root: Path, expected: str | None = None) -> tuple[dict[str, Any], bytes]:
    path = root / "grok-renewed-successor-manifest.json"
    value, raw = _json(path, "renewed successor manifest")
    _need(
        (expected is None or _sha(raw) == expected)
        and set(value) == _MANIFEST_KEYS
        and value.get("schema_version") == 1
        and value.get("evidence_class") == "dryad_grok_renewed_successor_v1"
        and value.get("source_epoch") == SOURCE_EPOCH
        and value.get("controller_sha256") == _sha(Path(__file__).read_bytes())
        and value.get("source_closure_sha256")
        == _sha(_canon(value.get("source_closure")))
        and value.get("pending_ordinals") == PENDING
        and value.get("operational_wave_cap") == WAVE_CAP
        and value.get("provider_calls_made") == 0
        and value.get("execution_authority") is False
        and isinstance(value.get("source_closure"), Mapping)
        and set(value["source_closure"]) == _CLOSURE_KEYS,
        "renewed successor manifest differs",
    )
    return value, raw


def create(
    *, continuation_root: Path, source_closure: Mapping[str, Any]
) -> dict[str, Any]:
    """Create an inert manifest for a fresh renewal continuation root."""
    root = Path(continuation_root).resolve()
    _need(
        not root.exists() or (root.is_dir() and not any(root.iterdir())),
        "renewed successor root is not fresh",
    )
    _need(
        isinstance(source_closure, Mapping)
        and set(source_closure) == _CLOSURE_KEYS,
        "renewed successor source closure differs",
    )
    historical_controller = _descriptor(
        source_closure["historical_controller"], "historical controller"
    )
    _need(
        Path(historical_controller["path"]).resolve()
        == HISTORICAL_CONTROLLER.resolve()
        and historical_controller["sha256"] == HISTORICAL_CONTROLLER_SHA256,
        "historical controller binding differs",
    )
    historical_manifest, _historical_raw = _historical_binding(source_closure)
    _bound(source_closure["retained_prefix"], "retained prefix")
    _prefix_bindings(source_closure["retained_prefix"], source_closure["historical_continuation"])
    _renewed_sources(source_closure, historical_manifest)
    _route(source_closure["route"])
    value = {
        "schema_version": 1,
        "evidence_class": "dryad_grok_renewed_successor_v1",
        "source_epoch": SOURCE_EPOCH,
        "controller_sha256": _sha(Path(__file__).read_bytes()),
        "source_closure": dict(source_closure),
        "source_closure_sha256": _sha(_canon(source_closure)),
        "pending_ordinals": PENDING,
        "operational_wave_cap": WAVE_CAP,
        "provider_calls_made": 0,
        "execution_authority": False,
    }
    manifest_path = root / "grok-renewed-successor-manifest.json"
    _new(manifest_path, _canon(value))
    return {
        "manifest_sha256": _sha(manifest_path.read_bytes()),
        "controller_sha256": value["controller_sha256"],
        "source_epoch": SOURCE_EPOCH,
        "next_ordinal": PENDING[0],
        "provider_calls_made": 0,
        "execution_authority": False,
    }


def _historical_state(closure: Mapping[str, Any]) -> dict[str, Any]:
    """Load and semantically verify the immutable historical source epoch."""
    historical_controller = _descriptor(
        closure["historical_controller"], "historical controller"
    )
    historical_manifest, _raw = _historical_binding(closure)
    module = _load_historical(
        Path(historical_controller["path"]), historical_controller["sha256"]
    )
    continuation = closure["historical_continuation"]
    root = Path(str(continuation["root"])).resolve()
    state = module.verify_runtime_data_successor(
        continuation_root=root,
        expected_manifest_sha256=continuation["manifest_sha256"],
    )
    replayed, replay_identities = module._replayed(root, state)
    _need(
        sorted(replayed) == list(range(280, 338)),
        "historical retained replay boundary differs",
    )
    prior = state.get("prior_identities")
    _need(
        isinstance(prior, list)
        and len(prior) == 277
        and _identities_unique(prior)
        and _identities_unique(replay_identities),
        "historical native identity boundary differs",
    )
    _need(
        _identities_unique([*prior, *replay_identities]),
        "historical native identity collision",
    )
    _need(
        state.get("manifest", {}).get("controller_sha256")
        == HISTORICAL_CONTROLLER_SHA256
        and historical_manifest.get("controller_sha256")
        == HISTORICAL_CONTROLLER_SHA256,
        "historical controller provenance differs",
    )
    return {
        "controller": module,
        "manifest": historical_manifest,
        "state": state,
        "replayed": replayed,
        "replay_identities": replay_identities,
        "prior_identities": list(prior),
    }


def verify(
    *, continuation_root: Path, expected_manifest_sha256: str
) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    manifest, raw = _manifest(root, expected_manifest_sha256)
    closure = manifest["source_closure"]
    historical_manifest, _historical_raw = _historical_binding(closure)
    prefix = _prefix_bindings(
        closure["retained_prefix"], closure["historical_continuation"]
    )
    renewed = _renewed_sources(closure, historical_manifest)
    historical = _historical_state(closure)
    _need(
        historical["replayed"] == set(range(280, 338))
        and historical["replay_identities"] == prefix["identities"],
        "historical retained prefix differs",
    )
    combined = [*historical["prior_identities"], *prefix["identities"]]
    _need(
        len(combined) == 335 and _identities_unique(combined),
        "renewed native identity boundary differs",
    )
    return {
        "manifest": manifest,
        "manifest_raw": raw,
        "historical": historical,
        "prefix": prefix,
        "renewed": renewed,
        "context": historical["state"]["context"],
        "prior_identities": combined,
        "pending_ordinals": list(PENDING),
        "next_ordinal": PENDING[0],
        "provider_calls_made": 0,
        "source_epoch": SOURCE_EPOCH,
    }


def _time(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _need(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _review(
    path: Path,
    expected: str,
    state: Mapping[str, Any],
    start: int,
) -> dict[str, Any]:
    value, raw = _json(path, "renewed successor review")
    manifest = state["manifest"]
    closure = manifest["source_closure"]
    gate, _gate_raw = _json(Path(value["gate_evidence_path"]), "renewed gate evidence")
    _need(
        _sha(raw) == expected
        and set(value) == _REVIEW_KEYS
        and value.get("schema_version") == 1
        and value.get("decision") == "approved_dryad_grok_renewed_successor_wave"
        and value.get("source_epoch") == SOURCE_EPOCH
        and value.get("controller_sha256") == manifest["controller_sha256"]
        and value.get("manifest_sha256") == _sha(state["manifest_raw"])
        and value.get("source_closure_sha256") == manifest["source_closure_sha256"]
        and value.get("historical_manifest_sha256")
        == closure["historical_continuation"]["manifest_sha256"]
        and value.get("retained_prefix_sha256") == closure["retained_prefix"]["sha256"]
        and value.get("candidate_manifest_sha256")
        == state["historical"]["manifest"]["source_closure"]["candidate"][
            "manifest_sha256"
        ]
        and value.get("packet_sha256") == closure["packet"]["sha256"]
        and value.get("standing_source_sha256") == closure["standing_source"]["sha256"]
        and value.get("first_ordinal") == start
        and value.get("operational_wave_cap") == WAVE_CAP
        and value.get("route_name") == closure["route"]["name"]
        and isinstance(value.get("route"), Mapping)
        and _sha(_canon(dict(value["route"])))
        == value.get("route_sha256")
        == closure["route"]["sha256"]
        and _sha(Path(value["gate_evidence_path"]).read_bytes())
        == value.get("gate_evidence_sha256")
        == value.get("gate_sha256")
        == closure["gate"]["sha256"]
        and value.get("gate_identity")
        == {
            key: gate.get(key)
            for key in ("provider", "account_class", "contract_hash", "source_evidence_hash", "state")
        }
        and gate.get("state") in (None, "healthy"),
        "renewed successor review differs",
    )
    now = datetime.now(timezone.utc)
    reviewed = _time(value["reviewed_at"], "renewed review time")
    expires = _time(value["expires_at"], "renewed review expiry")
    _need(
        reviewed <= now < expires and expires - now >= timedelta(seconds=300),
        "renewed successor review is not fresh",
    )
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
        _need(
            match is not None
            and item.is_dir()
            and not item.is_symlink(),
            "renewed attempt inventory differs",
        )
        ordinal = int(match.group(1))
        _need(
            ordinal in PENDING
            and ordinal not in result
            and _attempt(root, ordinal, "attempt-start.json").is_file(),
            "renewed attempt inventory differs",
        )
        terminal = _attempt(root, ordinal, "terminal.json")
        result[ordinal] = (
            _json(terminal, "renewed terminal")[0] if terminal.is_file() else None
        )
    return result


def _replayed(
    root: Path, state: Mapping[str, Any]
) -> tuple[set[int], list[dict[str, Any]]]:
    ordinals: set[int] = set()
    identities: list[dict[str, Any]] = []
    manifest = state["manifest"]
    closure = manifest["source_closure"]
    replay_dir = root / "replays"
    for path in (
        sorted(replay_dir.glob("wave-*-slots-01-replay.json"))
        if replay_dir.exists()
        else []
    ):
        value, _raw = _json(path, "renewed replay")
        current = value.get("ordinals")
        _need(
            set(value)
            == {
                "schema_version",
                "evidence_class",
                "source_epoch",
                "controller_sha256",
                "manifest_sha256",
                "source_closure_sha256",
                "historical_manifest_sha256",
                "retained_prefix_sha256",
                "packet_sha256",
                "standing_source_sha256",
                "route_sha256",
                "gate_sha256",
                "ordinals",
                "terminals",
                "native_identities",
                "provider_calls_made",
            }
            and value.get("schema_version") == 1
            and value.get("evidence_class")
            == "source_bound_grok_renewed_successor_replay_v1"
            and value.get("source_epoch") == SOURCE_EPOCH
            and value.get("controller_sha256") == manifest["controller_sha256"]
            and value.get("manifest_sha256") == _sha(state["manifest_raw"])
            and value.get("source_closure_sha256")
            == manifest["source_closure_sha256"]
            and value.get("historical_manifest_sha256")
            == closure["historical_continuation"]["manifest_sha256"]
            and value.get("retained_prefix_sha256")
            == closure["retained_prefix"]["sha256"]
            and value.get("packet_sha256") == closure["packet"]["sha256"]
            and value.get("standing_source_sha256")
            == closure["standing_source"]["sha256"]
            and value.get("route_sha256") == closure["route"]["sha256"]
            and value.get("gate_sha256") == closure["gate"]["sha256"]
            and isinstance(current, list)
            and len(current) == 1
            and current[0] in PENDING
            and current[0] not in ordinals
            and value.get("provider_calls_made") == 0,
            "renewed replay differs",
        )
        ordinal = current[0]
        terminals = value.get("terminals")
        native = value.get("native_identities")
        terminal_path = _attempt(root, ordinal, "terminal.json")
        _need(
            isinstance(terminals, list)
            and len(terminals) == 1
            and terminals[0].get("ordinal") == ordinal
            and terminals[0].get("terminal_sha256")
            == _sha(terminal_path.read_bytes())
            and isinstance(native, list)
            and len(native) == 1,
            "renewed replay terminal differs",
        )
        actual, _actual_raw = _json(terminal_path, "renewed replay terminal")
        identity = _native_identity(native[0], "renewed replay native identity")
        _need(
            actual.get("ordinal") == ordinal
            and actual.get("native_identity") == identity
            and terminals[0].get("native_identity") == identity,
            "renewed replay identity differs",
        )
        ordinals.add(ordinal)
        identities.append(identity)
    _need(
        _identities_unique(identities),
        "renewed replay native identity collision",
    )
    return ordinals, identities


def _next(records: Mapping[int, Mapping[str, Any] | None], replayed: set[int]) -> int:
    for index, ordinal in enumerate(PENDING):
        terminal = records.get(ordinal)
        if terminal is None:
            _need(
                not any(item in records for item in PENDING[index + 1:])
                and all(item in replayed for item in PENDING[:index]),
                "renewed successor cannot skip or bypass unreplayed cell",
            )
            return ordinal
        _need(
            terminal.get("state") == "completed" and ordinal in replayed,
            "renewed successor prior cell incomplete or unreplayed",
        )
    raise ValueError("renewed successor has no remaining ordinal")


def _callback_error(error: BaseException) -> dict[str, Any]:
    frames = traceback.extract_tb(error.__traceback__)
    frame = frames[-1] if frames else None
    return {
        "source": Path(frame.filename).name if frame else "unknown",
        "function": frame.name if frame else "unknown",
        "line": frame.lineno if frame else 0,
        "error_type": type(error).__name__,
    }


def _semantic_replay_terminal(
    *,
    candidate: Any,
    broker: Any,
    terminal: Mapping[str, Any],
    terminal_path: Path,
    parent: Any,
    runtime: Any,
    plan_root: Path,
    passes: Mapping[str, Any],
    requests: Mapping[int, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], Mapping[str, Any]]:
    """Reparse one renewed native envelope under this source epoch."""
    terminal_raw = terminal_path.read_bytes()
    result = terminal.get("candidate_result")
    _need(
        terminal.get("state") == "completed" and isinstance(result, Mapping),
        "renewed terminal differs",
    )
    descriptor = result.get("native_envelope_artifact")
    _need(isinstance(descriptor, Mapping), "renewed envelope descriptor differs")
    envelope = broker.read_grok_native_envelope(dict(descriptor))
    _need(
        descriptor.get("sha256") == _sha(envelope)
        and descriptor.get("byte_length") == len(envelope),
        "renewed candidate envelope differs",
    )
    ordinal = terminal.get("ordinal")
    _need(type(ordinal) is int and ordinal in requests, "renewed terminal ordinal differs")
    row = requests[ordinal]
    source = parent._source_for_pass(plan_root, passes[row["pass_id"]])
    prompt, schema_path, _ids = parent._request_payload(plan_root, row)
    schema = json.loads(schema_path.read_bytes())
    route, session_id = terminal.get("review_route"), terminal.get("session_id")
    _need(
        isinstance(route, Mapping)
        and isinstance(session_id, str)
        and isinstance(route.get("model"), str)
        and isinstance(route.get("reported_model"), str)
        and _sha(_canon(dict(route))) == terminal.get("route_sha256"),
        "renewed envelope binding differs",
    )
    parsed = broker._parse_grok_exec_envelope(
        _canon({"control": {"version": 1, "state": "completed"}, "result": dict(result)}),
        {**dict(route), "output_schema": schema, "nonvisual_max_turns": 1},
        {"prompt": prompt},
        expected_session_id=session_id,
    )
    adapter = importlib.import_module(candidate.__package__ + ".adapters.grok_exec")
    output, raw_identity, _usage = adapter._parse_grok_envelope(
        envelope,
        model=route["model"],
        reported_model=route["reported_model"],
        session_id=session_id,
        schema=schema,
        max_turns=1,
        exact_turns=True,
    )
    native_identity = _native_identity(raw_identity, "renewed candidate native identity")
    normalized = runtime.runner._normalize_batch(
        output,
        expected_ids=row["question_ids"],
        artifact_id=source["opaque_story_id"],
        bundle_id="prose.short_story",
        judge_id="grok:grok-4.6",
        run_id=f"{SOURCE_EPOCH}/{ordinal}",
        artifact_text=source["story_text"],
        context_texts=[],
        normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY,
        repair_audit=[],
    )
    _need(
        parsed.state == "completed"
        and parsed.result == result
        and output == result.get("output")
        and native_identity == terminal.get("native_identity")
        and normalized == terminal.get("verdicts")
        and [item["question_id"] for item in normalized] == row["question_ids"],
        "renewed terminal semantic replay differs",
    )
    _need(terminal_path.read_bytes() == terminal_raw, "renewed terminal changed")
    return native_identity, normalized, descriptor


def dispatch(
    *,
    continuation_root: Path,
    expected_manifest_sha256: str,
    start_ordinal: int,
    wave_size: int,
    arming_review_path: Path,
    expected_arming_review_sha256: str,
) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    _need(
        type(start_ordinal) is int
        and type(wave_size) is int
        and wave_size == WAVE_CAP
        and start_ordinal in PENDING,
        "renewed dispatch geometry differs",
    )
    state = verify(
        continuation_root=root, expected_manifest_sha256=expected_manifest_sha256
    )
    records, replayed, descendants = _records(root), *_replayed(root, state)
    _need(
        _identities_unique([*state["prior_identities"], *descendants]),
        "renewed native identity collision",
    )
    _need(
        start_ordinal == _next(records, replayed)
        and not _attempt(root, start_ordinal, "attempt-start.json").exists(),
        "renewed dispatch is not exact next pending",
    )
    review = _review(
        Path(arming_review_path),
        expected_arming_review_sha256,
        state,
        start_ordinal,
    )
    context = state["context"]
    closure = state["manifest"]["source_closure"]
    runtime = context.runtime
    row = context.requests[start_ordinal]
    prompt, schema_path, ids = context.parent._request_payload(
        context.plan_root, row
    )
    source = context.parent._source_for_pass(
        context.plan_root, context.passes[row["pass_id"]]
    )
    schema = json.loads(schema_path.read_bytes())
    start = {
        "schema_version": 1,
        "source_epoch": SOURCE_EPOCH,
        "ordinal": start_ordinal,
        "historical_manifest_sha256": closure["historical_continuation"][
            "manifest_sha256"
        ],
        "retained_prefix_sha256": closure["retained_prefix"]["sha256"],
        "candidate_manifest_sha256": state["historical"]["manifest"]["source_closure"][
            "candidate"
        ]["manifest_sha256"],
        "packet_sha256": closure["packet"]["sha256"],
        "standing_source_sha256": closure["standing_source"]["sha256"],
        "route_sha256": review["route_sha256"],
        "gate_sha256": review["gate_sha256"],
        "question_ids": ids,
        "prompt_sha256": row["prompt_sha256"],
        "schema_sha256": row["schema_sha256"],
        "source_sha256": source["sha256"],
        "wave": {
            "start": start_ordinal,
            "size": 1,
            "slot": 0,
            "ordinals": [start_ordinal],
        },
    }
    start_path = _attempt(root, start_ordinal, "attempt-start.json")
    _new(start_path, _canon(start))
    admitted = False
    callback_failure: dict[str, Any] | None = None
    session_id: str | None = None
    outcome: Any = None
    result: Any = None
    identity: Any = None
    try:
        broker = context.candidate.Broker(
            Path(state["historical"]["manifest"]["source_closure"]["queue"]["path"])
        )

        def before_contact() -> None:
            nonlocal admitted, callback_failure
            try:
                runtime.verify()
                _need(
                    _sha(Path(__file__).read_bytes())
                    == state["manifest"]["controller_sha256"]
                    and (root / "grok-renewed-successor-manifest.json").read_bytes()
                    == state["manifest_raw"],
                    "renewed controller changed before contact",
                )
                _bound(
                    closure["historical_controller"], "historical controller"
                )
                _historical_binding(closure)
                _prefix_bindings(
                    closure["retained_prefix"],
                    closure["historical_continuation"],
                )
                _need(
                    state["historical"]["manifest"]["controller_sha256"]
                    == HISTORICAL_CONTROLLER_SHA256,
                    "historical source changed before contact",
                )
                _renewed_sources(closure, state["historical"]["manifest"])
                fresh = _review(
                    Path(arming_review_path),
                    expected_arming_review_sha256,
                    state,
                    start_ordinal,
                )
                fresh_source = context.parent._source_for_pass(
                    context.plan_root, context.passes[row["pass_id"]]
                )
                _need(
                    fresh["route_sha256"] == review["route_sha256"]
                    and fresh["gate_sha256"] == review["gate_sha256"]
                    and fresh_source == source,
                    "renewed source or route changed before contact",
                )
                _new(
                    root
                    / "controller-authorizations"
                    / f"request-{start_ordinal:04d}.json",
                    _canon(
                        {
                            "source_epoch": SOURCE_EPOCH,
                            "ordinal": start_ordinal,
                            "manifest_sha256": _sha(state["manifest_raw"]),
                            "source_closure_sha256": state["manifest"][
                                "source_closure_sha256"
                            ],
                            "historical_manifest_sha256": closure[
                                "historical_continuation"
                            ]["manifest_sha256"],
                            "retained_prefix_sha256": closure["retained_prefix"][
                                "sha256"
                            ],
                            "review_sha256": expected_arming_review_sha256,
                            "route_sha256": fresh["route_sha256"],
                            "gate_sha256": fresh["gate_sha256"],
                            "packet_sha256": closure["packet"]["sha256"],
                            "standing_source_sha256": closure["standing_source"][
                                "sha256"
                            ],
                            "operational_wave_cap": WAVE_CAP,
                        }
                    ),
                )
                admitted = True
            except Exception as error:
                callback_failure = _callback_error(error)
                raise

        session_id = str(uuid.uuid4())
        outcome = broker.run_grok_native_request(
            review["route_name"],
            {"prompt": prompt},
            output_schema=schema,
            nonvisual_max_turns=1,
            session_id=session_id,
            expected_route_sha256=review["route_sha256"],
            before_contact=before_contact,
        )
        result = outcome.get("result") if isinstance(outcome, Mapping) else None
        if (
            not isinstance(outcome, Mapping)
            or outcome.get("state") != "completed"
            or not isinstance(result, Mapping)
            or not admitted
        ):
            terminal_state = (
                outcome.get("state")
                if isinstance(outcome, Mapping)
                and outcome.get("state") in {"definitely_not_contacted", "ambiguous"}
                else "ambiguous"
            )
            terminal = {
                "schema_version": 1,
                "source_epoch": SOURCE_EPOCH,
                "ordinal": start_ordinal,
                "state": terminal_state,
                "attempt_start_sha256": _sha(start_path.read_bytes()),
                "session_id": session_id,
                "broker_outcome": outcome,
                "contact_admitted": admitted,
            }
            if callback_failure is not None:
                terminal["before_contact_error"] = callback_failure
            _new(_attempt(root, start_ordinal, "terminal.json"), _canon(terminal))
            return {
                "state": "stopped_no_retry",
                "ordinals": [start_ordinal],
                "completed_ordinals": [],
                "failures": [
                    {
                        "ordinal": start_ordinal,
                        "error_type": "BrokerOutcome",
                        "contact_admitted": admitted,
                    }
                ],
                "provider_calls_made": (
                    0 if terminal_state == "definitely_not_contacted" else None
                ),
                "completed_provider_outcomes": 0,
                "ambiguous_contact_ordinals": (
                    [] if terminal_state == "definitely_not_contacted" else [start_ordinal]
                ),
            }
        record = result.get("runtime")
        _need(isinstance(record, Mapping), "renewed candidate result differs")
        identity = _native_identity(
            {
                "request_id_hash": record.get("request_id_hash"),
                "session_id_hash": record.get("session_id_hash"),
                "observed_turns": record.get("observed_turns"),
            },
            "renewed native identity",
        )
        _need(
            _identities_unique([*state["prior_identities"], *descendants, identity]),
            "renewed native identity collision",
        )
        normalized = runtime.runner._normalize_batch(
            result.get("output"),
            expected_ids=ids,
            artifact_id=source["opaque_story_id"],
            bundle_id="prose.short_story",
            judge_id="grok:grok-4.6",
            run_id=f"{SOURCE_EPOCH}/{start_ordinal}",
            artifact_text=source["story_text"],
            context_texts=[],
            normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY,
            repair_audit=[],
        )
        runtime.verify()
        terminal = {
            "schema_version": 1,
            "source_epoch": SOURCE_EPOCH,
            "ordinal": start_ordinal,
            "state": "completed",
            "attempt_start_sha256": _sha(start_path.read_bytes()),
            "session_id": session_id,
            "historical_manifest_sha256": closure["historical_continuation"][
                "manifest_sha256"
            ],
            "retained_prefix_sha256": closure["retained_prefix"]["sha256"],
            "candidate_manifest_sha256": state["historical"]["manifest"][
                "source_closure"
            ]["candidate"]["manifest_sha256"],
            "packet_sha256": closure["packet"]["sha256"],
            "standing_source_sha256": closure["standing_source"]["sha256"],
            "route_sha256": review["route_sha256"],
            "gate_sha256": review["gate_sha256"],
            "gate_identity": review["gate_identity"],
            "review_route": dict(review["route"]),
            "broker_outcome": outcome,
            "candidate_result": dict(result),
            "native_identity": identity,
            "verdicts": normalized,
        }
        _new(_attempt(root, start_ordinal, "terminal.json"), _canon(terminal))
        return {
            "state": "completed_pending_replay",
            "ordinals": [start_ordinal],
            "completed_ordinals": [start_ordinal],
            "failures": [],
            "provider_calls_made": 1,
            "completed_provider_outcomes": 1,
            "ambiguous_contact_ordinals": [],
        }
    except Exception as error:  # noqa: BLE001 - preserve post-contact evidence
        terminal_path = _attempt(root, start_ordinal, "terminal.json")
        if not terminal_path.exists():
            terminal = {
                "schema_version": 1,
                "source_epoch": SOURCE_EPOCH,
                "ordinal": start_ordinal,
                "state": "ambiguous" if admitted else "definitely_not_contacted",
                "attempt_start_sha256": _sha(start_path.read_bytes()),
                "session_id": session_id,
                "broker_outcome": outcome,
                "error_type": type(error).__name__,
                "error_source": "dispatch_grok_renewed_successor:cell",
            }
            if callback_failure is not None:
                terminal["before_contact_error"] = callback_failure
            if isinstance(result, Mapping):
                terminal["candidate_result"] = dict(result)
            if isinstance(identity, Mapping):
                terminal["native_identity"] = dict(identity)
            _new(terminal_path, _canon(terminal))
        completed = isinstance(outcome, Mapping) and outcome.get("state") == "completed"
        return {
            "state": "stopped_no_retry",
            "ordinals": [start_ordinal],
            "completed_ordinals": [],
            "failures": [
                {
                    "ordinal": start_ordinal,
                    "error_type": type(error).__name__,
                    "contact_admitted": admitted,
                }
            ],
            "provider_calls_made": 1 if completed else (None if admitted else 0),
            "completed_provider_outcomes": 1 if completed else 0,
            "ambiguous_contact_ordinals": (
                [] if completed else ([start_ordinal] if admitted else [])
            ),
        }


def replay(
    *,
    continuation_root: Path,
    expected_manifest_sha256: str,
    start_ordinal: int,
    wave_size: int,
) -> dict[str, Any]:
    root = Path(continuation_root).resolve()
    _need(
        type(start_ordinal) is int
        and type(wave_size) is int
        and wave_size == WAVE_CAP
        and start_ordinal in PENDING,
        "renewed replay geometry differs",
    )
    state = verify(
        continuation_root=root, expected_manifest_sha256=expected_manifest_sha256
    )
    replayed, previous = _replayed(root, state)
    _need(start_ordinal not in replayed, "renewed replay already exists")
    context = state["context"]
    closure = state["manifest"]["source_closure"]
    terminal_path = _attempt(root, start_ordinal, "terminal.json")
    terminal, _terminal_raw = _json(terminal_path, "renewed terminal")
    _need(
        terminal.get("source_epoch") == SOURCE_EPOCH
        and terminal.get("route_sha256") == closure["route"]["sha256"]
        and terminal.get("packet_sha256") == closure["packet"]["sha256"]
        and terminal.get("standing_source_sha256")
        == closure["standing_source"]["sha256"],
        "renewed terminal source epoch differs",
    )
    broker = context.candidate.Broker(
        Path(state["historical"]["manifest"]["source_closure"]["queue"]["path"])
    )
    identity, _normalized, descriptor = _semantic_replay_terminal(
        candidate=context.candidate,
        broker=broker,
        terminal=terminal,
        terminal_path=terminal_path,
        parent=context.parent,
        runtime=context.runtime,
        plan_root=context.plan_root,
        passes=context.passes,
        requests=context.requests,
    )
    _need(
        _identities_unique([*state["prior_identities"], *previous, identity]),
        "renewed replay native identity collision",
    )
    value = {
        "schema_version": 1,
        "evidence_class": "source_bound_grok_renewed_successor_replay_v1",
        "source_epoch": SOURCE_EPOCH,
        "controller_sha256": state["manifest"]["controller_sha256"],
        "manifest_sha256": _sha(state["manifest_raw"]),
        "source_closure_sha256": state["manifest"]["source_closure_sha256"],
        "historical_manifest_sha256": closure["historical_continuation"][
            "manifest_sha256"
        ],
        "retained_prefix_sha256": closure["retained_prefix"]["sha256"],
        "packet_sha256": closure["packet"]["sha256"],
        "standing_source_sha256": closure["standing_source"]["sha256"],
        "route_sha256": closure["route"]["sha256"],
        "gate_sha256": closure["gate"]["sha256"],
        "ordinals": [start_ordinal],
        "terminals": [
            {
                "ordinal": start_ordinal,
                "terminal_sha256": _sha(terminal_path.read_bytes()),
                "native_envelope_sha256": descriptor["sha256"],
                "native_identity": identity,
            }
        ],
        "native_identities": [identity],
        "provider_calls_made": 0,
    }
    context.runtime.verify()
    _new(_replay(root, start_ordinal), _canon(value))
    return value
