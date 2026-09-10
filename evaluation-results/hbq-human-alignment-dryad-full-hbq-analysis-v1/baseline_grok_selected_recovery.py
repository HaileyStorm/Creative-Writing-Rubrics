"""Owner-gated, provider-free recovery controller for selected Grok v5 work."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import threading
from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PARENT = ROOT / "baseline_grok_v5_suffix.py"
PARENT_SHA256 = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
PARTIAL_REPLAY_SHA256 = "ace8d594f0faf58e6557e0f49e923e3a24252818c3f2b96943f4d1ea5a71723e"
PROTECTED_COMMITMENT = "02be0a957f2984738d0283246eda5117802c1099c62bcbf0c4eb6b0ccbeaab3a"
REPLACEMENT = 88
UNTOUCHED_START = 92
PROTECTED_NATIVE_COUNT = 89
MAX_WAVE = 10
_HASH = re.compile(r"[0-9a-f]{64}")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is malformed") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(raw)


def _inventory(root: Path) -> dict[str, str]:
    _require(root.is_dir() and not root.is_symlink(), "old V5 root differs")
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        _require(not path.is_symlink(), "old V5 root contains a link")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
    return dict(sorted(result.items()))


def _load_parent(expected: str) -> Any:
    raw = PARENT.read_bytes()
    _require(_sha(raw) == expected == PARENT_SHA256, "frozen Grok parent differs")
    spec = importlib.util.spec_from_file_location("_dryad_grok_selected_recovery_parent", PARENT)
    _require(spec is not None and spec.loader is not None, "frozen Grok parent cannot load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _require(PARENT.read_bytes() == raw, "frozen Grok parent changed during load")
    return module


def _pending(epoch: Mapping[str, Any]) -> list[int]:
    schedule = epoch.get("remaining_request_ordinals")
    _require(isinstance(schedule, list) and all(type(item) is int for item in schedule), "inner selected schedule differs")
    expected = [REPLACEMENT, *range(UNTOUCHED_START, 1611), *range(4049, 4739)]
    _require(schedule == [*range(81, 1611), *range(4049, 4739)] and all(item in schedule for item in expected),
             "inner selected schedule differs")
    return expected


def _inner(parent: Any, root: Path, expected: str) -> tuple[dict[str, Any], bytes, Path, dict[int, Any]]:
    epoch, raw = parent._load_epoch(root, expected)
    plan_root, _old_root, _prefix_root, requests = parent._epoch_integrity(root, epoch)
    _pending(epoch)
    _require(REPLACEMENT in requests and all(ordinal in requests for ordinal in _pending(epoch)), "inner request inventory differs")
    return epoch, raw, plan_root, requests


def _identity_file(path: Path, expected_sha256: str | None = None) -> list[dict[str, str]]:
    try:
        raw = path.read_bytes()
        values = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("protected native identities are malformed") from error
    _require(expected_sha256 is None or _sha(raw) == expected_sha256, "protected native identities changed")
    _require(isinstance(values, list) and len(values) == PROTECTED_NATIVE_COUNT, "protected native identities differ")
    identities = [dict(value) for value in values if isinstance(value, Mapping)]
    _require(len(identities) == PROTECTED_NATIVE_COUNT and all(set(value) == {"request_id_hash", "session_id_hash"} for value in identities),
             "protected native identities differ")
    request_ids = [value["request_id_hash"] for value in identities]
    session_ids = [value["session_id_hash"] for value in identities]
    _require(all(isinstance(value, str) and _HASH.fullmatch(value) for value in request_ids + session_ids)
             and len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)),
             "protected native identities differ")
    _require(_identity_commitment(identities) == PROTECTED_COMMITMENT, "protected native identity commitment differs")
    return identities


def _identity_commitment(identities: Sequence[Mapping[str, str]]) -> str:
    return _sha(_canonical([{"request_id_hash": item["request_id_hash"], "session_id_hash": item["session_id_hash"]} for item in identities]))


def _partial(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    _require(_sha(raw) == expected == PARTIAL_REPLAY_SHA256, "partial replay differs")
    replay = _json(path, "partial replay")
    counts, wave, boundary = replay.get("counts"), replay.get("partial_wave"), replay.get("identity_boundary")
    _require(isinstance(counts, Mapping) and isinstance(wave, Mapping) and isinstance(boundary, Mapping)
             and counts.get("recognized_logical_requests") == 90 and counts.get("recognized_native_identities") == PROTECTED_NATIVE_COUNT
             and counts.get("recognized_verdicts") == 702 and wave.get("gap_ordinal") == REPLACEMENT
             and wave.get("completed_ordinals") == [82, 83, 84, 85, 86, 87, 89, 90, 91]
             and boundary.get("combined_native_count") == PROTECTED_NATIVE_COUNT
             and boundary.get("combined_native_identity_commitment_sha256") == PROTECTED_COMMITMENT
             and boundary.get("request_ids_unique") is True and boundary.get("session_ids_unique") is True,
             "partial replay differs")
    return replay


def _failed_88(source_root: Path) -> dict[str, str]:
    attempt = source_root / "attempts" / "request-0088"
    start, contact, terminal = (attempt / name for name in ("attempt-start.json", "contact-admission.json", "terminal.json"))
    start_value, contact_value, terminal_value = _json(start, "old failed 88 start"), _json(contact, "old failed 88 contact"), _json(terminal, "old failed 88 terminal")
    _require(terminal_value.get("status") == "ambiguous" and terminal_value.get("contact_admitted") is True
             and "provider_metadata" not in terminal_value and "raw_response" not in terminal_value
             and start_value.get("ordinal") == REPLACEMENT and contact_value.get("ordinal") == REPLACEMENT
             and contact_value.get("attempt_start_sha256") == _sha(start.read_bytes())
             and contact_value.get("context_sha256") == start_value.get("context_sha256"), "old failed 88 binding differs")
    return {"attempt_start_sha256": _sha(start.read_bytes()), "contact_admission_sha256": _sha(contact.read_bytes()),
            "terminal_sha256": _sha(terminal.read_bytes()), "prompt_sha256": start_value["prompt_sha256"],
            "schema_sha256": start_value["schema_sha256"], "context_sha256": start_value["context_sha256"]}


def _manifest(root: Path) -> tuple[dict[str, Any], bytes]:
    path = root / "recovery-manifest.json"
    raw, value = path.read_bytes(), _json(path, "recovery manifest")
    required = {"schema_version", "evidence_class", "controller_sha256", "parent_source", "source_epoch", "inner_epoch",
                "source_epoch_inventory", "partial_replay", "failed_ordinal_88", "protected_native_identities", "pending_ordinals",
                "provider_calls_made", "execution_authority"}
    _require(set(value) == required and value.get("schema_version") == 2
             and value.get("evidence_class") == "dryad_grok_selected_recovery_outer_controller_v2"
             and value.get("controller_sha256") == _sha(Path(__file__).read_bytes())
             and value.get("pending_ordinals") == [REPLACEMENT, *range(UNTOUCHED_START, 1611), *range(4049, 4739)]
             and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False,
             "recovery manifest differs")
    return value, raw


def prepare_recovery(*, recovery_root: Path, inner_epoch_root: Path, expected_inner_epoch_sha256: str,
                     expected_parent_sha256: str, partial_replay_path: Path, expected_partial_replay_sha256: str,
                     protected_native_identities: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Create a new outer root; it never creates a broker or contact."""
    parent = _load_parent(expected_parent_sha256)
    source_root = Path(inner_epoch_root).resolve()
    epoch, epoch_raw, _plan_root, _requests = _inner(parent, source_root, expected_inner_epoch_sha256)
    _partial(Path(partial_replay_path), expected_partial_replay_sha256)
    failed = _failed_88(source_root)
    protected = [dict(item) for item in protected_native_identities]
    root = Path(recovery_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _require(not any(root.iterdir()), "recovery root must be empty")
    _new(root / "suffix-epoch.json", epoch_raw)
    protected_raw = _canonical(protected)
    _new(root / "protected-native-identities.json", protected_raw)
    _identity_file(root / "protected-native-identities.json", _sha(protected_raw))
    inventory = _inventory(source_root)
    value = {
        "schema_version": 2,
        "evidence_class": "dryad_grok_selected_recovery_outer_controller_v2",
        "controller_sha256": _sha(Path(__file__).read_bytes()),
        "parent_source": {"path": str(PARENT), "sha256": expected_parent_sha256},
        "source_epoch": {"root": str(source_root), "sha256": expected_inner_epoch_sha256},
        "inner_epoch": {"path": str(root / "suffix-epoch.json"), "sha256": _sha(epoch_raw), "parent_executor_sha256": epoch["executor_source"]["sha256"]},
        "source_epoch_inventory": {"sha256": _sha(_canonical(inventory)), "files": inventory},
        "partial_replay": {"path": str(Path(partial_replay_path).resolve()), "sha256": expected_partial_replay_sha256},
        "failed_ordinal_88": failed,
        "protected_native_identities": {"path": str(root / "protected-native-identities.json"), "sha256": _sha(protected_raw),
                                        "count": PROTECTED_NATIVE_COUNT, "combined_commitment_sha256": PROTECTED_COMMITMENT},
        "pending_ordinals": _pending(epoch), "provider_calls_made": 0, "execution_authority": False,
    }
    _new(root / "recovery-manifest.json", _canonical(value))
    return {"recovery_manifest_sha256": _sha((root / "recovery-manifest.json").read_bytes()),
            "inner_epoch_sha256": _sha(epoch_raw), "provider_calls_made": 0, "execution_authority": False}


def _time(value: Any, label: str) -> datetime:
    _require(isinstance(value, str), f"{label} differs")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _require(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _adoption(path: Path, expected: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw, value = path.read_bytes(), _json(path, "replacement adoption")
    failed = manifest["failed_ordinal_88"]
    required = {"schema_version", "decision", "proposal_sha256", "replacement_ordinal", "maximum_new_attempts_per_ordinal",
                "old_failed_attempt_start_sha256", "old_failed_terminal_sha256", "prompt_sha256", "schema_sha256", "execution_authority"}
    _require(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1
             and value.get("decision") == "approved_exactly_one_replacement_ordinal_88"
             and value.get("proposal_sha256") == _sha(_canonical(dict(manifest)))
             and value.get("replacement_ordinal") == REPLACEMENT and value.get("maximum_new_attempts_per_ordinal") == 1
             and value.get("old_failed_attempt_start_sha256") == failed["attempt_start_sha256"]
             and value.get("old_failed_terminal_sha256") == failed["terminal_sha256"]
             and value.get("prompt_sha256") == failed["prompt_sha256"] and value.get("schema_sha256") == failed["schema_sha256"]
             and value.get("execution_authority") is True, "replacement adoption differs")
    return value


def _controller_review(path: Path, expected: str, *, manifest: Mapping[str, Any], manifest_raw: bytes,
                       parent_review: Mapping[str, Any], adoption_sha256: str, live: bool = True) -> dict[str, Any]:
    raw, value = path.read_bytes(), _json(path, "controller independent review")
    required = {"schema_version", "decision", "controller_sha256", "parent_sha256", "recovery_manifest_sha256", "inner_epoch_sha256",
                "partial_replay_sha256", "protected_identity_file_sha256", "protected_identity_commitment_sha256", "adoption_sha256",
                "parent_review_sha256", "route_sha256", "gate_sha256", "reviewed_at", "expires_at"}
    _require(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1
             and value.get("decision") == "approved_dryad_grok_selected_recovery_controller"
             and value.get("controller_sha256") == manifest["controller_sha256"]
             and value.get("parent_sha256") == manifest["parent_source"]["sha256"]
             and value.get("recovery_manifest_sha256") == _sha(manifest_raw)
             and value.get("inner_epoch_sha256") == manifest["inner_epoch"]["sha256"]
             and value.get("partial_replay_sha256") == manifest["partial_replay"]["sha256"]
             and value.get("protected_identity_file_sha256") == manifest["protected_native_identities"]["sha256"]
             and value.get("protected_identity_commitment_sha256") == manifest["protected_native_identities"]["combined_commitment_sha256"]
             and value.get("adoption_sha256") == adoption_sha256 and value.get("parent_review_sha256") == parent_review["_sha256"]
             and value.get("route_sha256") == parent_review["route_sha256"] and value.get("gate_sha256") == parent_review["gate_sha256"],
             "controller independent review differs")
    reviewed, expires, now = _time(value["reviewed_at"], "controller review time"), _time(value["expires_at"], "controller review expiry"), datetime.now(timezone.utc)
    if live:
        _require(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "controller independent review is not fresh for 300 seconds")
    return value


def _source_guard(parent: Any, manifest: Mapping[str, Any], source_epoch_raw: bytes) -> tuple[dict[str, Any], bytes, Path, dict[int, Any]]:
    source_root = Path(manifest["source_epoch"]["root"])
    _require(_inventory(source_root) == manifest["source_epoch_inventory"]["files"]
             and _sha(_canonical(manifest["source_epoch_inventory"]["files"])) == manifest["source_epoch_inventory"]["sha256"],
             "old V5 inventory changed")
    epoch, raw, plan_root, requests = _inner(parent, source_root, manifest["source_epoch"]["sha256"])
    _require(raw == source_epoch_raw, "old V5 source epoch changed")
    return epoch, raw, plan_root, requests


def _attempts(root: Path, parent: Any) -> dict[int, dict[str, Any] | None]:
    base = root / "attempts"
    if not base.exists():
        return {}
    records: dict[int, dict[str, Any] | None] = {}
    for directory in base.iterdir():
        match = re.fullmatch(r"request-(\d{4})", directory.name)
        _require(match is not None and directory.is_dir() and not directory.is_symlink(), "recovery attempt inventory differs")
        ordinal = int(match.group(1))
        start = parent._attempt_path(root, ordinal, "attempt-start.json")
        terminal = parent._attempt_path(root, ordinal, "terminal.json")
        _require(start.is_file() and ordinal not in records, "recovery attempt inventory differs")
        records[ordinal] = _json(terminal, "recovery terminal") if terminal.is_file() else None
    return records


def _replay_path(root: Path, start: int, size: int) -> Path:
    return root / "replays" / f"wave-{start:04d}-slots-{size:02d}.json"


def _replay_receipt(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes, epoch: Mapping[str, Any], path: Path) -> dict[str, Any]:
    value = _json(path, "recovery replay")
    required = {"schema_version", "evidence_class", "controller_sha256", "recovery_manifest_sha256", "inner_epoch_sha256",
                "wave_start_sha256", "settlement_sha256", "ordinals", "terminals", "native_identities", "provider_calls_made"}
    _require(set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "source_bound_recovery_wave_replay_v1"
             and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("recovery_manifest_sha256") == _sha(manifest_raw)
             and value.get("inner_epoch_sha256") == manifest["inner_epoch"]["sha256"] and value.get("provider_calls_made") == 0
             and isinstance(value.get("ordinals"), list) and value["ordinals"] and isinstance(value.get("terminals"), list)
             and len(value["ordinals"]) == len(value["terminals"]) == len(value.get("native_identities", [])), "recovery replay receipt differs")
    start = value["ordinals"][0]
    wave_path = parent._wave_path(root, start, len(value["ordinals"]), "start")
    settlement_path = parent._wave_path(root, start, len(value["ordinals"]), "settlement")
    _require(_sha(wave_path.read_bytes()) == value["wave_start_sha256"] and _sha(settlement_path.read_bytes()) == value["settlement_sha256"],
             "recovery replay wave binding differs")
    settlement = _json(settlement_path, "recovery settlement")
    for ordinal, terminal, identity in zip(value["ordinals"], value["terminals"], value["native_identities"], strict=True):
        _require(isinstance(terminal, Mapping) and set(terminal) == {"ordinal", "terminal_sha256", "controller_authorization_sha256"}
                 and terminal.get("ordinal") == ordinal and terminal.get("terminal_sha256") == _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()),
                 "recovery replay terminal binding differs")
        _require(isinstance(identity, Mapping) and set(identity) == {"request_id_hash", "session_id_hash"}
                 and all(isinstance(identity[key], str) and _HASH.fullmatch(identity[key]) for key in identity), "recovery replay identities differ")
        _auth, auth_sha = _historical_authorization(root, parent, manifest, manifest_raw, ordinal, epoch)
        _require(terminal.get("controller_authorization_sha256") == auth_sha
                 and any(row.get("ordinal") == ordinal and row.get("terminal_sha256") == terminal["terminal_sha256"]
                         and row.get("native_identity") == identity for row in settlement.get("rows", [])),
                 "recovery replay authorization binding differs")
    return value


def _validated_replay_chain(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes,
                            epoch: Mapping[str, Any]) -> tuple[set[int], list[dict[str, str]]]:
    completed: set[int] = set()
    identities: list[dict[str, str]] = []
    for path in sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else ():
        value = _replay_receipt(root, parent, manifest, manifest_raw, epoch, path)
        _require(not (completed & set(value["ordinals"])), "recovery replay ordinal duplicates")
        completed.update(value["ordinals"])
        identities.extend(dict(item) for item in value["native_identities"])
    request_ids = [item["request_id_hash"] for item in identities]
    session_ids = [item["session_id_hash"] for item in identities]
    _require(len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "recovery replay identity duplicate")
    return completed, identities


def _unique_identities(identities: Sequence[Mapping[str, str]], message: str) -> None:
    request_ids = [item["request_id_hash"] for item in identities]
    session_ids = [item["session_id_hash"] for item in identities]
    _require(len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), message)


def _next_pending(records: Mapping[int, Mapping[str, Any] | None], pending: Sequence[int], replayed: set[int]) -> int:
    _require(set(records) <= set(pending), "recovery attempt is outside pending schedule")
    for index, ordinal in enumerate(pending):
        terminal = records.get(ordinal)
        if terminal is None:
            _require(not any(number in records for number in pending[index + 1:]), "recovery cannot skip a pending ordinal")
            for previous in pending[:index]:
                _require(previous in replayed, "recovery prior ordinal requires completed replay")
            return ordinal
        _require(terminal.get("status") == "completed", "recovery prior ordinal is incomplete or ambiguous")
        _require(ordinal in replayed, "recovery prior ordinal requires replay")
    raise ValueError("recovery has no remaining ordinal")


def _outer_authorization(root: Path, *, ordinal: int, manifest_raw: bytes, manifest: Mapping[str, Any],
                         start_path: Path, adoption_path: Path, adoption_sha256: str, review_path: Path, review_sha256: str,
                         parent_review: Mapping[str, Any]) -> None:
    _new(root / "controller-authorizations" / f"request-{ordinal:04d}.json", _canonical({
        "schema_version": 1, "ordinal": ordinal, "controller_sha256": manifest["controller_sha256"],
        "recovery_manifest_sha256": _sha(manifest_raw), "attempt_start_sha256": _sha(start_path.read_bytes()),
        "adoption_path": str(adoption_path), "adoption_sha256": adoption_sha256,
        "controller_review_path": str(review_path), "controller_review_sha256": review_sha256,
        "route_sha256": parent_review["route_sha256"], "gate_sha256": parent_review["gate_sha256"],
        "authorized_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }))


def _historical_authorization(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes, ordinal: int,
                              epoch: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    path = root / "controller-authorizations" / f"request-{ordinal:04d}.json"
    raw, value = path.read_bytes(), _json(path, "controller authorization")
    required = {"schema_version", "ordinal", "controller_sha256", "recovery_manifest_sha256", "attempt_start_sha256", "adoption_path",
                "adoption_sha256", "controller_review_path", "controller_review_sha256", "route_sha256", "gate_sha256", "authorized_at"}
    _require(set(value) == required and value.get("schema_version") == 1 and value.get("ordinal") == ordinal
             and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("recovery_manifest_sha256") == _sha(manifest_raw)
             and value.get("attempt_start_sha256") == _sha(parent._attempt_path(root, ordinal, "attempt-start.json").read_bytes()),
             "controller authorization differs")
    _adoption(Path(value["adoption_path"]), value["adoption_sha256"], manifest)
    start = _json(parent._attempt_path(root, ordinal, "attempt-start.json"), "recovery attempt start")
    parent_review = parent._review(Path(start["review"]["path"]), start["review"]["sha256"], epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, live=False)
    parent_review = {**parent_review, "_sha256": start["review"]["sha256"]}
    _controller_review(Path(value["controller_review_path"]), value["controller_review_sha256"], manifest=manifest,
                       manifest_raw=manifest_raw, parent_review=parent_review, adoption_sha256=value["adoption_sha256"], live=False)
    _require(value["route_sha256"] == start["route_sha256"] == parent_review["route_sha256"]
             and value["gate_sha256"] == start["gate_sha256"] == parent_review["gate_sha256"], "controller authorization route differs")
    return value, _sha(raw)


def _dispatch(*, recovery_root: Path, ordinals: list[int], adoption_path: Path, expected_adoption_sha256: str,
              reviewed_path: Path, expected_review_sha256: str, controller_review_path: Path,
              expected_controller_review_sha256: str, queue_root: Path, broker_factory: Any | None = None) -> dict[str, Any]:
    root = Path(recovery_root).resolve()
    manifest, manifest_raw = _manifest(root)
    _require(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"], "recovery controller changed")
    parent = _load_parent(manifest["parent_source"]["sha256"])
    # Keep both epochs live: the source root is immutable evidence and the copied epoch is the parent executor input.
    source_epoch, source_epoch_raw, _source_plan, _source_requests = _inner(parent, Path(manifest["source_epoch"]["root"]), manifest["source_epoch"]["sha256"])
    _require(_inventory(Path(manifest["source_epoch"]["root"])) == manifest["source_epoch_inventory"]["files"], "old V5 inventory changed")
    epoch, epoch_raw, plan_root, requests = _inner(parent, root, manifest["inner_epoch"]["sha256"])
    _require(epoch_raw == source_epoch_raw and epoch == source_epoch and manifest["inner_epoch"]["path"] == str(root / "suffix-epoch.json"),
             "copied inner epoch differs")
    pending = _pending(epoch)
    _require(1 <= len(ordinals) <= MAX_WAVE and ordinals == pending[pending.index(ordinals[0]):pending.index(ordinals[0]) + len(ordinals)],
             "recovery wave order differs")
    records = _attempts(root, parent)
    replayed_ordinals, recovered_identities = _validated_replay_chain(root, parent, manifest, manifest_raw, epoch)
    _require(ordinals[0] == _next_pending(records, pending, replayed_ordinals), "recovery wave is not exact next pending ordinal")
    starts = [parent._attempt_path(root, ordinal, "attempt-start.json") for ordinal in ordinals]
    _require(not any(path.exists() for path in starts), "recovery existing slot cannot resend")
    _adoption(Path(adoption_path), expected_adoption_sha256, manifest)
    _require(ordinals[0] == REPLACEMENT or REPLACEMENT in _attempts(root, parent), "replacement must precede untouched collection")
    parent_review = parent._review(Path(reviewed_path), expected_review_sha256, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, live=True)
    parent_review = {**parent_review, "_sha256": expected_review_sha256}
    _controller_review(Path(controller_review_path), expected_controller_review_sha256, manifest=manifest, manifest_raw=manifest_raw,
                       parent_review=parent_review, adoption_sha256=expected_adoption_sha256)
    protected = _identity_file(Path(manifest["protected_native_identities"]["path"]), manifest["protected_native_identities"]["sha256"])
    protected.extend(recovered_identities)
    _unique_identities(protected, "recovery replay overlaps protected identities")
    prepared = [parent._prepare_wave_cell(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, plan_root=plan_root,
                                          requests=requests, review_path=Path(reviewed_path), review_sha256=expected_review_sha256,
                                          review=parent_review, ordinal=ordinal, wave_start_ordinal=ordinals[0],
                                          wave_ordinals=ordinals, slot_index=index)
                for index, ordinal in enumerate(ordinals)]
    for item in prepared:
        _new(item["start_path"], _canonical(item["start"]))
    wave_start = {
        "format_version": 1, "epoch_sha256": manifest["inner_epoch"]["sha256"], "epoch_source_sha256": _sha(epoch_raw),
        "execution_mode": epoch["execution_mode"], "max_concurrency": epoch["max_concurrency"], "start_ordinal": ordinals[0],
        "wave_size": len(ordinals), "ordinals": ordinals, "review": {"path": str(Path(reviewed_path)), "sha256": expected_review_sha256},
        "route_sha256": parent_review["route_sha256"], "gate_sha256": parent_review["gate_sha256"],
        "runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"],
        "runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"], "v3_sha256": epoch["v3_source"]["sha256"],
        "selected_schedule_sha256": epoch["selected_schedule"]["sha256"],
        "rows": [{"ordinal": item["row"]["ordinal"], "slot_index": index, "pass_id": item["row"]["pass_id"],
                  "source_sha256": item["source"]["sha256"], "context_sha256": item["start"]["context_sha256"],
                  "attempt_start_sha256": _sha(item["start_path"].read_bytes())} for index, item in enumerate(prepared)],
    }
    wave_path = parent._wave_path(root, ordinals[0], len(ordinals), "start")
    _new(wave_path, _canonical(wave_start))
    wave_start_sha256 = _sha(wave_path.read_bytes())
    stop, lock, identities, results, failures, admitted_ordinals, contact_started = threading.Event(), threading.Lock(), list(protected), {}, [], [], []

    def cell(item: Mapping[str, Any]) -> None:
        runtime, row, passed = item["runtime"], item["row"], item["passed"]
        ordinal, start_path, context, source, run_root = row["ordinal"], item["start_path"], item["context"], item["source"], item["run_root"]
        admitted = contact_started_here = False
        content: str | None = None
        metadata: Mapping[str, Any] | None = None
        try:
            broker = parent._broker(runtime, Path(queue_root), broker_factory)

            def before_contact(callback_context: Mapping[str, Any]) -> None:
                nonlocal admitted, contact_started_here
                _require(not stop.is_set() and _sha(_canonical(dict(callback_context))) == item["start"]["context_sha256"],
                         "recovery stopped or callback context differs")
                _require(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"]
                         and (root / "recovery-manifest.json").read_bytes() == manifest_raw, "recovery controller or manifest changed before contact")
                _source_guard(parent, manifest, source_epoch_raw)
                current, current_raw, current_plan, current_requests = _inner(parent, root, manifest["inner_epoch"]["sha256"])
                _require(current_raw == epoch_raw and current == epoch and current_plan == plan_root and current_requests[ordinal] == row,
                         "copied inner epoch or request changed before contact")
                _partial(Path(manifest["partial_replay"]["path"]), manifest["partial_replay"]["sha256"])
                _identity_file(Path(manifest["protected_native_identities"]["path"]), manifest["protected_native_identities"]["sha256"])
                _adoption(Path(adoption_path), expected_adoption_sha256, manifest)
                live_parent = parent._review(Path(reviewed_path), expected_review_sha256, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=current, live=True)
                live_parent = {**live_parent, "_sha256": expected_review_sha256}
                _controller_review(Path(controller_review_path), expected_controller_review_sha256, manifest=manifest, manifest_raw=manifest_raw,
                                   parent_review=live_parent, adoption_sha256=expected_adoption_sha256)
                _require(live_parent["route_sha256"] == parent_review["route_sha256"] and live_parent["gate_sha256"] == parent_review["gate_sha256"],
                         "route or gate changed before contact")
                runtime.verify()
                _require(parent._source_for_pass(plan_root, passed) == source, "payload source changed before contact")
                _outer_authorization(root, ordinal=ordinal, manifest_raw=manifest_raw, manifest=manifest, start_path=start_path,
                                     adoption_path=Path(adoption_path), adoption_sha256=expected_adoption_sha256,
                                     review_path=Path(controller_review_path), review_sha256=expected_controller_review_sha256,
                                     parent_review=live_parent)
                _require(not stop.is_set(), "recovery stopped before native contact")
                _new(parent._attempt_path(root, ordinal, "contact-admission.json"), _canonical({
                    "format_version": 1, "ordinal": ordinal, "epoch_sha256": manifest["inner_epoch"]["sha256"],
                    "attempt_start_sha256": _sha(start_path.read_bytes()), "context_sha256": item["start"]["context_sha256"],
                    "route_sha256": live_parent["route_sha256"], "gate_sha256": live_parent["gate_sha256"],
                    "admitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }))
                admitted = True
                with lock:
                    admitted_ordinals.append(ordinal)
                    contact_started.append(ordinal)
                contact_started_here = True

            transport = runtime.transport.bind_grok_broker_transport(broker=broker, route=parent_review["route"], before_contact=before_contact,
                                                                       runtime_check=runtime.verify)
            content, metadata = transport(context)
            _require(isinstance(content, str) and isinstance(metadata, Mapping) and admitted, "transport returned without admitted contact")
            runtime.runner._validate_grok_transport_evidence(run_root, metadata)
            normalized = runtime.runner._normalize_batch(runtime.runner._parse_model_json(content), expected_ids=item["question_ids"],
                artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=context["run"]["run_id"],
                artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
            runtime.verify()
            _source_guard(parent, manifest, source_epoch_raw)
            current, current_raw, current_plan, current_requests = _inner(parent, root, manifest["inner_epoch"]["sha256"])
            _require(current == epoch and current_raw == epoch_raw and current_plan == plan_root and current_requests[ordinal] == row,
                     "recovery epoch changed after contact")
            identity = {"request_id_hash": metadata["request_id_sha256"], "session_id_hash": metadata["session_id_sha256"]}
            with lock:
                _require(identity not in identities and identity["request_id_hash"] not in {x["request_id_hash"] for x in identities}
                         and identity["session_id_hash"] not in {x["session_id_hash"] for x in identities}, "recovery native identity duplicate")
                identities.append(identity)
            parent._terminal(root=root, ordinal=ordinal, epoch_sha256=manifest["inner_epoch"]["sha256"], start_path=start_path, status="completed",
                             run_root=run_root, contact_admitted=True, context=context, content=content, metadata=metadata, verdicts=normalized)
            with lock:
                results[ordinal] = {"ordinal": ordinal, "status": "completed_pending_replay", "contact_admitted": True,
                                    "contact_started": True, "provider_calls_made": 1}
        except BaseException as error:  # noqa: BLE001
            stop.set()
            if not parent._attempt_path(root, ordinal, "terminal.json").exists():
                parent._terminal(root=root, ordinal=ordinal, epoch_sha256=manifest["inner_epoch"]["sha256"], start_path=start_path,
                                 status="ambiguous", run_root=run_root, contact_admitted=admitted, context=context, content=content, metadata=metadata)
            with lock:
                failures.append({"ordinal": ordinal, "error_type": type(error).__name__, "contact_admitted": admitted,
                                 "contact_started": contact_started_here})

    with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="dryad-grok-recovery") as pool:
        futures = {pool.submit(cell, item): item["row"]["ordinal"] for item in prepared}
        while futures:
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                future.result()
    settlement = parent._wave_settlement(root, epoch_sha256=manifest["inner_epoch"]["sha256"], start_ordinal=ordinals[0],
                                          wave_ordinals=ordinals, wave_start_sha256=wave_start_sha256)
    _new(parent._wave_path(root, ordinals[0], len(ordinals), "settlement"), _canonical(settlement))
    return {"state": "stopped_no_retry" if failures else "completed_pending_replay", "ordinals": ordinals,
            "rows": [results.get(ordinal, {"ordinal": ordinal, "status": "ambiguous", "contact_admitted": False,
                                               "contact_started": False, "provider_calls_made": 0}) for ordinal in ordinals],
            "failures": sorted(failures, key=lambda item: item["ordinal"]), "admitted_ordinals": sorted(admitted_ordinals),
            "contact_started_ordinals": sorted(contact_started), "completed_ordinals": sorted(results),
            "uncontacted_ordinals": sorted(set(ordinals) - set(contact_started)), "provider_calls_made": len(contact_started)}


def dispatch_replacement(**kwargs: Any) -> dict[str, Any]:
    return _dispatch(ordinals=[REPLACEMENT], **kwargs)


def dispatch_wave(*, start_ordinal: int, wave_size: int, **kwargs: Any) -> dict[str, Any]:
    _require(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE, "recovery wave geometry differs")
    _require(start_ordinal >= UNTOUCHED_START, "recovery waves after replacement begin at 92")
    root = Path(kwargs["recovery_root"]).resolve()
    manifest, _raw = _manifest(root)
    pending = manifest["pending_ordinals"]
    _require(start_ordinal in pending, "recovery wave is outside selected schedule")
    start = pending.index(start_ordinal)
    ordinals = pending[start:start + wave_size]
    _require(len(ordinals) == wave_size, "recovery wave exceeds selected schedule")
    return _dispatch(ordinals=ordinals, **kwargs)


def replay_wave(*, recovery_root: Path, start_ordinal: int, wave_size: int, approved_v5_routes: Mapping[str, Any],
                protected_native_identities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Read settled terminals through frozen parent replay helpers, without contact."""
    root = Path(recovery_root).resolve()
    manifest, manifest_raw = _manifest(root)
    parent = _load_parent(manifest["parent_source"]["sha256"])
    _require(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"]
             and (root / "recovery-manifest.json").read_bytes() == manifest_raw
             and 1 <= wave_size <= MAX_WAVE, "recovery replay guard differs")
    epoch, epoch_raw, plan_root, requests = _inner(parent, root, manifest["inner_epoch"]["sha256"])
    _source_guard(parent, manifest, epoch_raw)
    pending = _pending(epoch)
    _require(start_ordinal in pending, "recovery replay outside selected schedule")
    start = pending.index(start_ordinal)
    ordinals = pending[start:start + wave_size]
    _require(len(ordinals) == wave_size, "recovery replay exceeds selected schedule")
    identity_path = Path(manifest["protected_native_identities"]["path"])
    protected = _identity_file(identity_path, manifest["protected_native_identities"]["sha256"])
    supplied = [dict(item) for item in protected_native_identities]
    _require(supplied == protected, "recovery replay protected identities differ")
    _replayed_ordinals, recovered_identities = _validated_replay_chain(root, parent, manifest, manifest_raw, epoch)
    protected.extend(recovered_identities)
    _unique_identities(protected, "recovery replay overlaps protected identities")
    _wave, wave_raw = parent._wave_start(root, epoch_sha256=manifest["inner_epoch"]["sha256"], start_ordinal=start_ordinal, wave_size=wave_size)
    settlement_path = parent._wave_path(root, start_ordinal, wave_size, "settlement")
    settlement = _json(settlement_path, "recovery settlement")
    _require(settlement.get("wave_start_sha256") == _sha(wave_raw) and settlement.get("ordinals") == ordinals
             and len(settlement.get("rows", [])) == wave_size, "recovery settlement differs")
    plan, _ = parent._plan(plan_root, epoch["plan_sha256"])
    passes, runtime, identities = parent._pass_index(plan), parent._runtime_from_epoch(epoch), []
    for ordinal, settled in zip(ordinals, settlement["rows"], strict=True):
        row = requests[ordinal]
        _require(settled.get("ordinal") == ordinal and settled.get("status") == "completed"
                 and settled.get("terminal_sha256") == _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()),
                 "recovery replay terminal differs")
        verdicts, identity = parent._replay_suffix_terminal(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch,
            runtime=runtime, plan_root=plan_root, passed=passes[row["pass_id"]], row=row, approved_v5_routes=approved_v5_routes)
        _require(settled.get("native_identity") == identity and verdicts, "recovery replay identity differs")
        identities.append(identity)
    all_identities = protected + identities
    request_ids = [item["request_id_hash"] for item in all_identities]
    session_ids = [item["session_id_hash"] for item in all_identities]
    _require(len(request_ids) == len(set(request_ids)) and len(session_ids) == len(set(session_ids)), "recovery replay identity duplicate")
    terminals = []
    for ordinal in ordinals:
        _auth, authorization_sha = _historical_authorization(root, parent, manifest, manifest_raw, ordinal, epoch)
        terminals.append({"ordinal": ordinal, "terminal_sha256": _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()),
                          "controller_authorization_sha256": authorization_sha})
    result = {"schema_version": 1, "evidence_class": "source_bound_recovery_wave_replay_v1", "controller_sha256": manifest["controller_sha256"],
              "recovery_manifest_sha256": _sha(manifest_raw), "inner_epoch_sha256": manifest["inner_epoch"]["sha256"],
              "wave_start_sha256": _sha(wave_raw), "settlement_sha256": _sha(settlement_path.read_bytes()), "ordinals": ordinals,
              "terminals": terminals, "native_identities": identities, "provider_calls_made": 0}
    replay_path = _replay_path(root, start_ordinal, wave_size)
    _new(replay_path, _canonical(result))
    return result
