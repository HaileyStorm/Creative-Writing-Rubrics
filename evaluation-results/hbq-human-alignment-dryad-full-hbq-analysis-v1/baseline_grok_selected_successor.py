"""Owner-adopted successor controller for selected-100 Grok recovery."""
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
PRIOR = ROOT / "baseline_grok_selected_recovery.py"
PARENT_SHA = "eab249cbdaa43cdb7f89364b97079000eda7b71717693711cda1de3de66a2b75"
PRIOR_SHA = "687a60bcdd26227b3bcb6ae5081f3357bceb84b4b29312653617ef3d36887399"
MAX_WAVE = 10
_HASH = re.compile(r"[0-9a-f]{64}")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _need(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} malformed") from error
    _need(isinstance(value, dict), f"{label} object")
    return value


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as out:
        out.write(raw)


def _load(path: Path, expected: str, name: str) -> Any:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, f"{name} differs")
    spec = importlib.util.spec_from_file_location(f"_selected_successor_{name}", path)
    _need(spec is not None and spec.loader is not None, f"{name} load")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _need(path.read_bytes() == raw, f"{name} changed")
    return module


def _inventory(root: Path) -> dict[str, str]:
    _need(root.is_dir() and not root.is_symlink(), "predecessor root differs")
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        _need(not path.is_symlink(), "predecessor root contains link")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = _sha(path.read_bytes())
    return dict(sorted(result.items()))


def _identity(values: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = [dict(item) for item in values if isinstance(item, Mapping)]
    _need(len(result) == len(values) and all(set(item) == {"request_id_hash", "session_id_hash"} for item in result), "native identities differ")
    requests = [item["request_id_hash"] for item in result]
    sessions = [item["session_id_hash"] for item in result]
    _need(all(isinstance(item, str) and _HASH.fullmatch(item) for item in requests + sessions)
          and len(requests) == len(set(requests)) and len(sessions) == len(set(sessions)), "native identity collision")
    return result


def _identity_file(path: Path) -> list[dict[str, str]]:
    try:
        values = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("protected native identities malformed") from error
    _need(isinstance(values, list), "protected native identities differ")
    return _identity(values)


def _partial(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    _need(_sha(raw) == expected, "partial-202 differs")
    value = _json(path, "partial-202")
    required = {"schema_version", "evidence_class", "controller_sha256", "recovery_manifest_sha256", "inner_epoch_sha256",
                "prior_logical_count", "recognized_logical_count", "recognized_native_identity_count", "partial_criterion_verdict_count",
                "failed_wave_admitted", "resend_authority", "provider_calls_made", "completed_ordinals", "failed_ordinals",
                "failed_attempts", "records", "native_identities", "all_protected_native_identities",
                "all_protected_native_identity_commitment_sha256", "wave_start_sha256", "settlement_sha256"}
    _need(set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "source_bound_partial_recovery_wave_replay_v1"
          and type(value.get("prior_logical_count")) is int and value.get("recognized_logical_count") == value.get("prior_logical_count") + len(value.get("completed_ordinals", []))
          and type(value.get("recognized_native_identity_count")) is int and type(value.get("partial_criterion_verdict_count")) is int
          and value.get("failed_wave_admitted") is False and value.get("resend_authority") is False and value.get("provider_calls_made") == 0
          and isinstance(value.get("completed_ordinals"), list) and isinstance(value.get("failed_ordinals"), list)
          and all(type(item) is int for item in [*value["completed_ordinals"], *value["failed_ordinals"]]),
          "partial-202 contract differs")
    identities = _identity(value["all_protected_native_identities"])
    _need(len(identities) == value["recognized_native_identity_count"] and value.get("all_protected_native_identity_commitment_sha256") == _sha(_canon(identities)),
          "partial-202 identity commitment differs")
    failed = value["failed_attempts"]
    _need(isinstance(failed, list) and failed and [item.get("ordinal") for item in failed if isinstance(item, Mapping)] == value["failed_ordinals"] and len(set(value["failed_ordinals"])) == len(value["failed_ordinals"]),
          "partial-202 failed inventory differs")
    for item in failed:
        _need(isinstance(item, Mapping) and set(item) == {"ordinal", "attempt_start_sha256", "contact_admission_sha256", "terminal_sha256", "prompt_sha256", "schema_sha256", "question_ids", "retained_complete_answer"}
              and item.get("retained_complete_answer") is False and isinstance(item.get("question_ids"), list)
              and all(isinstance(v, str) and _HASH.fullmatch(v) for k, v in item.items() if k.endswith("sha256")), "partial-202 failed record differs")
    records = value["records"]
    _need(isinstance(records, list) and len(records) == len(value["completed_ordinals"]) and _identity(value["native_identities"]) == [dict(item["native_identity"]) for item in records if isinstance(item, Mapping)],
          "partial-202 records differ")
    return value


def _pending(epoch: Mapping[str, Any], failed: Sequence[int], untouched_start: int) -> list[int]:
    expected = [*failed, *[item for item in epoch.get("remaining_request_ordinals", []) if item >= untouched_start]]
    schedule = epoch.get("remaining_request_ordinals")
    _need(isinstance(schedule, list) and list(failed) and all(type(value) is int for value in schedule) and all(value in schedule for value in expected),
          "selected successor schedule differs")
    return expected


def _manifest(root: Path) -> tuple[dict[str, Any], bytes]:
    path = root / "successor-manifest.json"
    raw, value = path.read_bytes(), _json(path, "successor manifest")
    required = {"schema_version", "evidence_class", "controller_sha256", "parent_sha256", "prior_controller_sha256", "prior_root", "prior_manifest_sha256",
                "prior_inventory", "inner_epoch", "partial_202", "failed_attempts", "protected_native_identities", "pending_ordinals",
                "predecessor_root_ownership", "provider_calls_made", "execution_authority"}
    _need(set(value) == required and value.get("schema_version") == 2 and value.get("evidence_class") == "dryad_grok_selected_successor_controller_v2"
          and value.get("controller_sha256") == _sha(Path(__file__).read_bytes()) and value.get("parent_sha256") == PARENT_SHA
          and isinstance(value.get("prior_controller_sha256"), str) and _HASH.fullmatch(value["prior_controller_sha256"]) and isinstance(value.get("pending_ordinals"), list)
          and value.get("provider_calls_made") == 0 and value.get("execution_authority") is False, "successor manifest differs")
    return value, raw


def _prior_chain(parent: Any, prior: Any | None, source: Path, expected_manifest: str, partial: Mapping[str, Any]) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, Path, dict[int, Any]]:
    if (source / "recovery-manifest.json").is_file():
        _need(prior is not None, "frozen predecessor controller is unavailable")
        manifest, manifest_raw = prior._manifest(source)
        epoch, epoch_raw, plan_root, requests = prior._inner(parent, source, manifest["inner_epoch"]["sha256"])
        prior._source_guard(parent, manifest, epoch_raw)
        replayed, native = prior._validated_replay_chain(source, parent, manifest, manifest_raw, epoch)
        protected = prior._identity_file(Path(manifest["protected_native_identities"]["path"]), manifest["protected_native_identities"]["sha256"])
    else:
        manifest, manifest_raw = _manifest(source)
        epoch, epoch_raw = parent._load_epoch(source, manifest["inner_epoch"]["sha256"])
        plan_root, _old, _prefix, requests = parent._epoch_integrity(source, epoch)
        replayed, native = _validated_replays(source, parent, manifest, manifest_raw)
        protected = _identity_file(Path(manifest["protected_native_identities"]["path"]))
    _need(_sha(manifest_raw) == expected_manifest, "prior manifest differs")
    partial_boundary = min([*partial["completed_ordinals"], *partial["failed_ordinals"]])
    _need(replayed == {ordinal for ordinal in manifest["pending_ordinals"] if ordinal < partial_boundary}, "predecessor replay chain incomplete")
    _need(all(item in partial["all_protected_native_identities"] for item in _identity([*protected, *native])), "partial omits predecessor identity")
    return manifest, manifest_raw, epoch, epoch_raw, plan_root, requests


def _verify_partial_source(source: Path, partial: Mapping[str, Any], expected_manifest: str, expected_controller: str, requests: Mapping[int, Any]) -> None:
    _need(partial.get("controller_sha256") == expected_controller and partial.get("recovery_manifest_sha256") == expected_manifest, "partial predecessor binding differs")
    records = {item.get("ordinal"): item for item in partial["records"] if isinstance(item, Mapping)}
    _need(set(records) == set(partial["completed_ordinals"]), "partial peer records differ")
    for ordinal, record in records.items():
        terminal = source / "attempts" / f"request-{ordinal:04d}" / "terminal.json"
        value = _json(terminal, "partial peer terminal")
        metadata = value.get("provider_metadata")
        _need(record.get("terminal_sha256") == _sha(terminal.read_bytes()) and value.get("status") == "completed" and isinstance(metadata, Mapping)
              and record.get("native_identity") == {"request_id_hash": metadata.get("request_id_sha256"), "session_id_hash": metadata.get("session_id_sha256")},
              "partial peer source differs")
    for failed in partial["failed_attempts"]:
        ordinal = failed["ordinal"]
        attempt = source / "attempts" / f"request-{ordinal:04d}"
        start, contact, terminal = (attempt / name for name in ("attempt-start.json", "contact-admission.json", "terminal.json"))
        start_value, terminal_value = _json(start, "partial failed start"), _json(terminal, "partial failed terminal")
        _need(ordinal in requests and start_value.get("ordinal") == ordinal and terminal_value.get("status") == "ambiguous" and contact.is_file()
              and start_value.get("prompt_sha256") == failed["prompt_sha256"] and start_value.get("schema_sha256") == failed["schema_sha256"]
              and start_value.get("question_ids") == failed["question_ids"] and _sha(start.read_bytes()) == failed["attempt_start_sha256"]
              and _sha(contact.read_bytes()) == failed["contact_admission_sha256"] and _sha(terminal.read_bytes()) == failed["terminal_sha256"],
              "partial failed source differs")


def prepare_successor(*, successor_root: Path, prior_root: Path, expected_prior_manifest_sha256: str, partial_202_path: Path, expected_partial_202_sha256: str) -> dict[str, Any]:
    """Create an inert successor; it neither creates a broker nor contacts a provider."""
    parent = _load(PARENT, PARENT_SHA, "parent")
    prior = _load(PRIOR, PRIOR_SHA, "prior") if (Path(prior_root) / "recovery-manifest.json").is_file() else None
    source, partial_path = Path(prior_root).resolve(), Path(partial_202_path).resolve()
    partial = _partial(partial_path, expected_partial_202_sha256)
    prior_manifest, prior_raw, epoch, epoch_raw, _plan, requests = _prior_chain(parent, prior, source, expected_prior_manifest_sha256, partial)
    _verify_partial_source(source, partial, _sha(prior_raw), prior_manifest["controller_sha256"], requests)
    root = Path(successor_root).resolve(); root.mkdir(parents=True, exist_ok=True)
    _need(not any(root.iterdir()), "successor root must be empty")
    _new(root / "suffix-epoch.json", epoch_raw)
    identities = _identity(partial["all_protected_native_identities"]); identity_raw = _canon(identities)
    failed_ordinals = list(partial["failed_ordinals"]); untouched_start = max([*partial["completed_ordinals"], *failed_ordinals]) + 1
    _new(root / "protected-native-identities.json", identity_raw)
    inventory = _inventory(source)
    value = {"schema_version": 2, "evidence_class": "dryad_grok_selected_successor_controller_v2", "controller_sha256": _sha(Path(__file__).read_bytes()),
             "parent_sha256": PARENT_SHA, "prior_controller_sha256": prior_manifest["controller_sha256"], "prior_root": str(source), "prior_manifest_sha256": _sha(prior_raw),
             "prior_inventory": {"sha256": _sha(_canon(inventory)), "files": inventory},
             "inner_epoch": {"path": str(root / "suffix-epoch.json"), "sha256": _sha(epoch_raw), "parent_executor_sha256": epoch["executor_source"]["sha256"]},
             "partial_202": {"path": str(partial_path), "sha256": expected_partial_202_sha256, "identity_commitment_sha256": _sha(identity_raw)},
             "failed_attempts": partial["failed_attempts"],
             "protected_native_identities": {"path": str(root / "protected-native-identities.json"), "sha256": _sha(identity_raw), "count": len(identities), "commitment_sha256": _sha(identity_raw)},
             "pending_ordinals": _pending(epoch, failed_ordinals, untouched_start), "predecessor_root_ownership": {"prior_completed_through": partial["prior_logical_count"], "partial_peer_ordinals": partial["completed_ordinals"], "successor_replacements": failed_ordinals, "successor_untouched_start": untouched_start},
             "provider_calls_made": 0, "execution_authority": False}
    _new(root / "successor-manifest.json", _canon(value))
    return {"successor_manifest_sha256": _sha((root / "successor-manifest.json").read_bytes()), "provider_calls_made": 0, "execution_authority": False}


def _time(value: Any, label: str) -> datetime:
    _need(isinstance(value, str), f"{label} differs")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{label} differs") from error
    _need(parsed.tzinfo is not None, f"{label} differs")
    return parsed.astimezone(timezone.utc)


def _adoption(path: Path, expected: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
    raw, value = path.read_bytes(), _json(path, "successor adoption")
    required = {"schema_version", "decision", "proposal_sha256", "replacement_ordinals", "maximum_new_attempts_per_ordinal", "failed_attempts", "execution_authority"}
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1
          and value.get("decision") == "approved_exactly_one_selected_successor_replacements"
          and value.get("proposal_sha256") == _sha(_canon(dict(manifest))) and value.get("replacement_ordinals") == manifest["predecessor_root_ownership"]["successor_replacements"]
          and value.get("maximum_new_attempts_per_ordinal") == 1 and value.get("failed_attempts") == manifest["failed_attempts"]
          and value.get("execution_authority") is True, "successor adoption differs")
    return value


def _controller_review(path: Path, expected: str, *, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes, adoption_sha256: str, epoch: Mapping[str, Any], live: bool) -> dict[str, Any]:
    raw, value = path.read_bytes(), _json(path, "successor controller review")
    required = {"schema_version", "decision", "controller_sha256", "parent_sha256", "prior_controller_sha256", "successor_manifest_sha256", "prior_manifest_sha256", "inner_epoch_sha256", "partial_202_sha256", "protected_identity_file_sha256", "protected_identity_commitment_sha256", "adoption_sha256", "parent_review_path", "parent_review_sha256", "route_sha256", "gate_sha256", "reviewed_at", "expires_at"}
    _need(_sha(raw) == expected and set(value) == required and value.get("schema_version") == 1
          and value.get("decision") == "approved_dryad_grok_selected_successor_controller"
          and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("parent_sha256") == PARENT_SHA and value.get("prior_controller_sha256") == manifest["prior_controller_sha256"]
          and value.get("successor_manifest_sha256") == _sha(manifest_raw) and value.get("prior_manifest_sha256") == manifest["prior_manifest_sha256"]
          and value.get("inner_epoch_sha256") == manifest["inner_epoch"]["sha256"] and value.get("partial_202_sha256") == manifest["partial_202"]["sha256"]
          and value.get("protected_identity_file_sha256") == manifest["protected_native_identities"]["sha256"]
          and value.get("protected_identity_commitment_sha256") == manifest["protected_native_identities"]["commitment_sha256"]
          and value.get("adoption_sha256") == adoption_sha256, "successor controller review differs")
    parent_review = parent._review(Path(value["parent_review_path"]), value["parent_review_sha256"], epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, live=live)
    _need(value.get("route_sha256") == parent_review["route_sha256"] and value.get("gate_sha256") == parent_review["gate_sha256"], "successor route review differs")
    if live:
        reviewed, expires, now = _time(value["reviewed_at"], "controller review time"), _time(value["expires_at"], "controller review expiry"), datetime.now(timezone.utc)
        _need(reviewed <= now < expires and expires - now >= timedelta(seconds=300), "successor controller review is not fresh for 300 seconds")
    return {**value, "parent_review": parent_review}


def _source_guard(parent: Any, prior: Any | None, manifest: Mapping[str, Any], partial: Mapping[str, Any]) -> tuple[dict[str, Any], bytes, Path, dict[int, Any]]:
    source = Path(manifest["prior_root"])
    _need(_inventory(source) == manifest["prior_inventory"]["files"] and _sha(_canon(manifest["prior_inventory"]["files"])) == manifest["prior_inventory"]["sha256"], "predecessor inventory changed")
    _need(_partial(Path(manifest["partial_202"]["path"]), manifest["partial_202"]["sha256"]) == partial, "partial replay changed")
    if (source / "recovery-manifest.json").is_file():
        _need(prior is not None, "frozen predecessor controller is unavailable")
        prior_manifest, prior_raw = prior._manifest(source)
        epoch, epoch_raw, plan_root, requests = prior._inner(parent, source, manifest["inner_epoch"]["sha256"])
    else:
        prior_manifest, prior_raw = _manifest(source)
        epoch, epoch_raw = parent._load_epoch(source, manifest["inner_epoch"]["sha256"])
        plan_root, _old, _prefix, requests = parent._epoch_integrity(source, epoch)
    _need(_sha(prior_raw) == manifest["prior_manifest_sha256"] and prior_manifest["controller_sha256"] == manifest["prior_controller_sha256"], "prior manifest changed")
    _need(epoch_raw == Path(manifest["inner_epoch"]["path"]).read_bytes(), "copied epoch differs")
    return epoch, epoch_raw, plan_root, requests


def _attempts(root: Path, parent: Any) -> dict[int, dict[str, Any] | None]:
    base = root / "attempts"
    if not base.exists():
        return {}
    result: dict[int, dict[str, Any] | None] = {}
    for directory in base.iterdir():
        match = re.fullmatch(r"request-(\d{4})", directory.name)
        _need(match is not None and directory.is_dir() and not directory.is_symlink(), "successor attempt inventory differs")
        ordinal = int(match.group(1)); start = parent._attempt_path(root, ordinal, "attempt-start.json"); terminal = parent._attempt_path(root, ordinal, "terminal.json")
        _need(start.is_file() and ordinal not in result, "successor attempt inventory differs")
        result[ordinal] = _json(terminal, "successor terminal") if terminal.is_file() else None
    return result


def _replay_path(root: Path, start: int, size: int) -> Path:
    return root / "replays" / f"wave-{start:04d}-slots-{size:02d}.json"


def _validated_replays(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes) -> tuple[set[int], list[dict[str, str]]]:
    complete: set[int] = set(); identities: list[dict[str, str]] = []
    for path in sorted((root / "replays").glob("wave-*-slots-*.json")) if (root / "replays").exists() else ():
        value = _json(path, "successor replay")
        required = {"schema_version", "evidence_class", "controller_sha256", "successor_manifest_sha256", "inner_epoch_sha256", "wave_start_sha256", "settlement_sha256", "ordinals", "terminals", "native_identities", "provider_calls_made"}
        _need(set(value) == required and value.get("schema_version") == 1 and value.get("evidence_class") == "source_bound_successor_wave_replay_v1"
              and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("successor_manifest_sha256") == _sha(manifest_raw)
              and value.get("inner_epoch_sha256") == manifest["inner_epoch"]["sha256"] and value.get("provider_calls_made") == 0
              and isinstance(value.get("ordinals"), list) and value["ordinals"] and len(value["ordinals"]) == len(value.get("terminals", [])) == len(value.get("native_identities", [])), "successor replay differs")
        wave = parent._wave_path(root, value["ordinals"][0], len(value["ordinals"]), "start"); settlement = parent._wave_path(root, value["ordinals"][0], len(value["ordinals"]), "settlement")
        _need(_sha(wave.read_bytes()) == value["wave_start_sha256"] and _sha(settlement.read_bytes()) == value["settlement_sha256"] and not (complete & set(value["ordinals"])), "successor replay binding differs")
        for ordinal, terminal in zip(value["ordinals"], value["terminals"], strict=True):
            _need(isinstance(terminal, Mapping) and terminal.get("ordinal") == ordinal and terminal.get("terminal_sha256") == _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()), "successor replay terminal differs")
        complete.update(value["ordinals"]); identities.extend(_identity(value["native_identities"]))
    _identity(identities)
    return complete, identities


def _next_pending(records: Mapping[int, Mapping[str, Any] | None], pending: Sequence[int], replayed: set[int]) -> int:
    _need(set(records) <= set(pending), "successor attempt outside schedule")
    for index, ordinal in enumerate(pending):
        terminal = records.get(ordinal)
        if terminal is None:
            _need(not any(value in records for value in pending[index + 1:]) and all(value in replayed for value in pending[:index]), "successor cannot skip or bypass unreplayed cell")
            return ordinal
        _need(terminal.get("status") == "completed" and ordinal in replayed, "successor prior cell incomplete or unreplayed")
    raise ValueError("successor has no remaining ordinal")


def _authorization(root: Path, ordinal: int, manifest: Mapping[str, Any], manifest_raw: bytes, start: Path, adoption: Path, adoption_sha: str, review: Path, review_sha: str, route: str, gate: str) -> str:
    path = root / "controller-authorizations" / f"request-{ordinal:04d}.json"
    value = {"schema_version": 1, "ordinal": ordinal, "controller_sha256": manifest["controller_sha256"], "successor_manifest_sha256": _sha(manifest_raw), "attempt_start_sha256": _sha(start.read_bytes()), "adoption_path": str(adoption), "adoption_sha256": adoption_sha, "controller_review_path": str(review), "controller_review_sha256": review_sha, "route_sha256": route, "gate_sha256": gate, "authorized_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _new(path, _canon(value)); return _sha(path.read_bytes())


def _historical_authorization(root: Path, parent: Any, manifest: Mapping[str, Any], manifest_raw: bytes, ordinal: int) -> str:
    path = root / "controller-authorizations" / f"request-{ordinal:04d}.json"; raw, value = path.read_bytes(), _json(path, "successor authorization")
    required = {"schema_version", "ordinal", "controller_sha256", "successor_manifest_sha256", "attempt_start_sha256", "adoption_path", "adoption_sha256", "controller_review_path", "controller_review_sha256", "route_sha256", "gate_sha256", "authorized_at"}
    _need(set(value) == required and value.get("schema_version") == 1 and value.get("ordinal") == ordinal and value.get("controller_sha256") == manifest["controller_sha256"] and value.get("successor_manifest_sha256") == _sha(manifest_raw) and value.get("attempt_start_sha256") == _sha(parent._attempt_path(root, ordinal, "attempt-start.json").read_bytes()), "successor authorization differs")
    return _sha(raw)


def _dispatch(*, successor_root: Path, ordinals: list[int], adoption_path: Path, expected_adoption_sha256: str, review_path: Path, expected_review_sha256: str, queue_root: Path, broker_factory: Any | None = None) -> dict[str, Any]:
    root = Path(successor_root).resolve(); manifest, manifest_raw = _manifest(root)
    queue = Path(queue_root).resolve()
    _need(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"] and queue.is_dir() and not queue.is_symlink(), "successor controller changed or queue is inactive")
    parent = _load(PARENT, manifest["parent_sha256"], "parent")
    prior = _load(PRIOR, PRIOR_SHA, "prior") if manifest["prior_controller_sha256"] == PRIOR_SHA else None
    partial = _partial(Path(manifest["partial_202"]["path"]), manifest["partial_202"]["sha256"])
    epoch, epoch_raw, plan_root, requests = _source_guard(parent, prior, manifest, partial)
    pending = manifest["pending_ordinals"]
    _need(1 <= len(ordinals) <= MAX_WAVE and ordinals == pending[pending.index(ordinals[0]):pending.index(ordinals[0]) + len(ordinals)], "successor wave order differs")
    records = _attempts(root, parent); replayed, replay_identities = _validated_replays(root, parent, manifest, manifest_raw)
    _need(ordinals[0] == _next_pending(records, pending, replayed), "successor wave is not exact next pending")
    failed = manifest["predecessor_root_ownership"]["successor_replacements"]
    if ordinals[0] == failed[0]: _need(ordinals == failed, "replacement wave must be the adopted failed set")
    else: _need(set(failed).issubset(replayed), "partial replacement blocks untouched suffix")
    starts = [parent._attempt_path(root, ordinal, "attempt-start.json") for ordinal in ordinals]
    _need(not any(path.exists() for path in starts), "successor existing slot cannot resend")
    _adoption(Path(adoption_path), expected_adoption_sha256, manifest)
    review = _controller_review(Path(review_path), expected_review_sha256, parent=parent, manifest=manifest, manifest_raw=manifest_raw, adoption_sha256=expected_adoption_sha256, epoch=epoch, live=True)
    protected = _identity_file(Path(manifest["protected_native_identities"]["path"])); _need(_sha(_canon(protected)) == manifest["protected_native_identities"]["sha256"], "protected identities changed")
    identities = _identity([*protected, *replay_identities])
    prepared = [parent._prepare_wave_cell(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, plan_root=plan_root, requests=requests, review_path=Path(review["parent_review_path"]), review_sha256=review["parent_review_sha256"], review=review["parent_review"], ordinal=ordinal, wave_start_ordinal=ordinals[0], wave_ordinals=ordinals, slot_index=index) for index, ordinal in enumerate(ordinals)]
    for item in prepared: _new(item["start_path"], _canon(item["start"]))
    wave = {"format_version": 1, "epoch_sha256": manifest["inner_epoch"]["sha256"], "epoch_source_sha256": _sha(epoch_raw), "execution_mode": epoch["execution_mode"], "max_concurrency": epoch["max_concurrency"], "start_ordinal": ordinals[0], "wave_size": len(ordinals), "ordinals": ordinals, "review": {"path": str(review["parent_review_path"]), "sha256": review["parent_review_sha256"]}, "route_sha256": review["route_sha256"], "gate_sha256": review["gate_sha256"], "runtime_manifest_sha256": epoch["runtime_manifest"]["sha256"], "runtime_package_manifest_sha256": epoch["runtime_package"]["manifest_sha256"], "v3_sha256": epoch["v3_source"]["sha256"], "selected_schedule_sha256": epoch["selected_schedule"]["sha256"], "rows": [{"ordinal": item["row"]["ordinal"], "slot_index": index, "pass_id": item["row"]["pass_id"], "source_sha256": item["source"]["sha256"], "context_sha256": item["start"]["context_sha256"], "attempt_start_sha256": _sha(item["start_path"].read_bytes())} for index, item in enumerate(prepared)]}
    wave_path = parent._wave_path(root, ordinals[0], len(ordinals), "start"); _new(wave_path, _canon(wave))
    results: dict[int, dict[str, Any]] = {}; failures: list[dict[str, Any]] = []
    admitted_ordinals: set[int] = set(); contact_started: set[int] = set(); stop, lock = threading.Event(), threading.Lock()
    def cell(item: Mapping[str, Any]) -> None:
        ordinal, admitted, content, metadata = item["row"]["ordinal"], False, None, None
        try:
            _need(not stop.is_set(), "successor stopped before native contact"); runtime, source = item["runtime"], item["source"]
            broker = parent._broker(runtime, queue, broker_factory)
            def before_contact(context: Mapping[str, Any]) -> None:
                nonlocal admitted
                _need(not stop.is_set() and _sha(_canon(dict(context))) == item["start"]["context_sha256"], "successor context changed")
                _need(_sha(Path(__file__).read_bytes()) == manifest["controller_sha256"] and (root / "successor-manifest.json").read_bytes() == manifest_raw, "successor source changed before contact")
                current, raw, current_plan, current_requests = _source_guard(parent, prior, manifest, partial)
                _need(current == epoch and raw == epoch_raw and current_plan == plan_root and current_requests[ordinal] == item["row"], "successor epoch changed before contact")
                protected_now = _identity_file(Path(manifest["protected_native_identities"]["path"]))
                _need(_sha(_canon(protected_now)) == manifest["protected_native_identities"]["sha256"], "protected identities changed before contact")
                _adoption(Path(adoption_path), expected_adoption_sha256, manifest)
                live = _controller_review(Path(review_path), expected_review_sha256, parent=parent, manifest=manifest, manifest_raw=manifest_raw, adoption_sha256=expected_adoption_sha256, epoch=current, live=True)
                _need(live["route_sha256"] == review["route_sha256"] and live["gate_sha256"] == review["gate_sha256"], "route or gate changed before contact")
                runtime.verify(); _need(parent._source_for_pass(plan_root, item["passed"]) == source, "payload source changed before contact")
                with lock:
                    _need(not stop.is_set(), "successor stopped before native admission")
                    _authorization(root, ordinal, manifest, manifest_raw, item["start_path"], Path(adoption_path), expected_adoption_sha256, Path(review_path), expected_review_sha256, live["route_sha256"], live["gate_sha256"])
                    _new(parent._attempt_path(root, ordinal, "contact-admission.json"), _canon({"format_version": 1, "ordinal": ordinal, "epoch_sha256": manifest["inner_epoch"]["sha256"], "attempt_start_sha256": _sha(item["start_path"].read_bytes()), "context_sha256": item["start"]["context_sha256"], "route_sha256": live["route_sha256"], "gate_sha256": live["gate_sha256"], "admitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")})); admitted = True
                    admitted_ordinals.add(ordinal); contact_started.add(ordinal)
            transport = runtime.transport.bind_grok_broker_transport(broker=broker, route=review["parent_review"]["route"], before_contact=before_contact, runtime_check=runtime.verify)
            content, metadata = transport(item["context"]); _need(isinstance(content, str) and isinstance(metadata, Mapping) and admitted, "transport returned without admitted contact")
            runtime.runner._validate_grok_transport_evidence(item["run_root"], metadata)
            normalized = runtime.runner._normalize_batch(runtime.runner._parse_model_json(content), expected_ids=item["question_ids"], artifact_id=source["opaque_story_id"], bundle_id="prose.short_story", judge_id="grok:grok-4.6", run_id=item["context"]["run"]["run_id"], artifact_text=source["story_text"], context_texts=[], normalization_policy=runtime.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])
            identity = {"request_id_hash": metadata["request_id_sha256"], "session_id_hash": metadata["session_id_sha256"]}
            with lock:
                _identity([*identities, identity]); identities.append(identity)
            parent._terminal(root=root, ordinal=ordinal, epoch_sha256=manifest["inner_epoch"]["sha256"], start_path=item["start_path"], status="completed", run_root=item["run_root"], contact_admitted=True, context=item["context"], content=content, metadata=metadata, verdicts=normalized)
            with lock:
                results[ordinal] = {"ordinal": ordinal, "status": "completed_pending_replay", "contact_admitted": True, "contact_started": True, "provider_calls_made": 1}
        except BaseException as error:  # noqa: BLE001
            with lock:
                stop.set()
            if not parent._attempt_path(root, ordinal, "terminal.json").exists(): parent._terminal(root=root, ordinal=ordinal, epoch_sha256=manifest["inner_epoch"]["sha256"], start_path=item["start_path"], status="ambiguous", run_root=item["run_root"], contact_admitted=admitted, context=item["context"], content=content, metadata=metadata)
            with lock:
                failures.append({"ordinal": ordinal, "error_type": type(error).__name__, "contact_admitted": admitted, "contact_started": admitted})
    with ThreadPoolExecutor(max_workers=len(prepared), thread_name_prefix="dryad-grok-successor") as executor:
        futures = {executor.submit(cell, item): item["row"]["ordinal"] for item in prepared}
        while futures:
            done, _ = wait(tuple(futures), return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future); future.result()
    settlement = parent._wave_settlement(root, epoch_sha256=manifest["inner_epoch"]["sha256"], start_ordinal=ordinals[0], wave_ordinals=ordinals, wave_start_sha256=_sha(wave_path.read_bytes())); _new(parent._wave_path(root, ordinals[0], len(ordinals), "settlement"), _canon(settlement))
    return {"state": "stopped_no_retry" if failures else "completed_pending_replay", "ordinals": ordinals, "rows": [results.get(ordinal, {"ordinal": ordinal, "status": "ambiguous", "contact_admitted": ordinal in admitted_ordinals, "contact_started": ordinal in contact_started, "provider_calls_made": int(ordinal in contact_started)}) for ordinal in ordinals], "failures": sorted(failures, key=lambda item: item["ordinal"]), "admitted_ordinals": sorted(admitted_ordinals), "contact_started_ordinals": sorted(contact_started), "completed_ordinals": sorted(results), "uncontacted_ordinals": sorted(set(ordinals) - contact_started), "provider_calls_made": len(contact_started)}


def dispatch_replacements(**kwargs: Any) -> dict[str, Any]:
    manifest, _raw = _manifest(Path(kwargs["successor_root"]).resolve())
    return _dispatch(ordinals=list(manifest["predecessor_root_ownership"]["successor_replacements"]), **kwargs)


def dispatch_wave(*, start_ordinal: int, wave_size: int, **kwargs: Any) -> dict[str, Any]:
    _need(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE, "successor wave geometry differs")
    manifest, _raw = _manifest(Path(kwargs["successor_root"]).resolve()); pending = manifest["pending_ordinals"]
    _need(start_ordinal in pending, "successor wave outside schedule"); index = pending.index(start_ordinal); ordinals = pending[index:index + wave_size]
    _need(len(ordinals) == wave_size and all(ordinal >= manifest["predecessor_root_ownership"]["successor_untouched_start"] for ordinal in ordinals), "successor wave exceeds suffix")
    return _dispatch(ordinals=ordinals, **kwargs)


def replay_wave(*, successor_root: Path, start_ordinal: int, wave_size: int, approved_v5_routes: Mapping[str, Any], protected_native_identities: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Replay settled native terminals with the frozen parent; no provider is contacted."""
    root = Path(successor_root).resolve(); manifest, manifest_raw = _manifest(root)
    parent = _load(PARENT, manifest["parent_sha256"], "parent")
    prior = _load(PRIOR, PRIOR_SHA, "prior") if manifest["prior_controller_sha256"] == PRIOR_SHA else None
    partial = _partial(Path(manifest["partial_202"]["path"]), manifest["partial_202"]["sha256"])
    epoch, _raw, plan_root, requests = _source_guard(parent, prior, manifest, partial)
    _need(type(start_ordinal) is int and type(wave_size) is int and 1 <= wave_size <= MAX_WAVE, "successor replay geometry differs")
    wave_path = parent._wave_path(root, start_ordinal, wave_size, "start"); wave = _json(wave_path, "successor wave"); ordinals = wave.get("ordinals")
    _need(isinstance(ordinals, list) and len(ordinals) == wave_size and ordinals[0] == start_ordinal and all(ordinal in manifest["pending_ordinals"] for ordinal in ordinals), "successor replay wave differs")
    protected = _identity_file(Path(manifest["protected_native_identities"]["path"]))
    _need([dict(item) for item in protected_native_identities] == protected, "successor replay protected identities differ")
    prior_replays, previous = _validated_replays(root, parent, manifest, manifest_raw); _need(not (prior_replays & set(ordinals)), "successor replay already exists")
    settlement_path = parent._wave_path(root, start_ordinal, wave_size, "settlement"); settlement = _json(settlement_path, "successor settlement")
    _need(settlement.get("ordinals") == ordinals and settlement.get("wave_start_sha256") == _sha(wave_path.read_bytes()) and isinstance(settlement.get("rows"), list) and len(settlement["rows"]) == wave_size, "successor settlement differs")
    plan, _ = parent._plan(plan_root, epoch["plan_sha256"]); passes, runtime, identities = parent._pass_index(plan), parent._runtime_from_epoch(epoch), []
    for ordinal, settled in zip(ordinals, settlement["rows"], strict=True):
        row, terminal_path = requests[ordinal], parent._attempt_path(root, ordinal, "terminal.json")
        _need(isinstance(settled, Mapping) and settled.get("ordinal") == ordinal and settled.get("status") == "completed" and settled.get("terminal_sha256") == _sha(terminal_path.read_bytes()), "successor replay terminal differs")
        verdicts, identity = parent._replay_suffix_terminal(root=root, epoch_sha256=manifest["inner_epoch"]["sha256"], epoch=epoch, runtime=runtime, plan_root=plan_root, passed=passes[row["pass_id"]], row=row, approved_v5_routes=approved_v5_routes)
        _need(verdicts and settled.get("native_identity") == identity, "successor replay identity differs"); identities.append(identity)
    _identity([*protected, *previous, *identities])
    result = {"schema_version": 1, "evidence_class": "source_bound_successor_wave_replay_v1", "controller_sha256": manifest["controller_sha256"], "successor_manifest_sha256": _sha(manifest_raw), "inner_epoch_sha256": manifest["inner_epoch"]["sha256"], "wave_start_sha256": _sha(wave_path.read_bytes()), "settlement_sha256": _sha(settlement_path.read_bytes()), "ordinals": ordinals, "terminals": [{"ordinal": ordinal, "terminal_sha256": _sha(parent._attempt_path(root, ordinal, "terminal.json").read_bytes()), "controller_authorization_sha256": _historical_authorization(root, parent, manifest, manifest_raw, ordinal)} for ordinal in ordinals], "native_identities": identities, "provider_calls_made": 0}
    _new(_replay_path(root, start_ordinal, wave_size), _canon(result)); return result
