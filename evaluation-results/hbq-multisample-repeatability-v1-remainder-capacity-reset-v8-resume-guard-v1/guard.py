"""Provider-free, fail-closed controller for a future V8 delegation."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import types
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Mapping


STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1"
STATUS = "CONTROL_GUARD_ONLY"
V8_DIR = Path(__file__).resolve().parents[1] / "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8"
V8_EXECUTOR_RELATIVE = Path("executor.py")
EXPECTED_V8_EXECUTOR_SHA256 = "515ea015074883be64b64ec63b832c00c8452e65cd1786dd9ba81dc23b92b2d6"
EXPECTED_V8_STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8"
BINDING = "guard-binding.json"
JOURNAL = "guard-journal.jsonl"
LOCK = "guard-journal.lock"
CLAIMS = "claims"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_reparse(path: Path) -> bool:
    info = path.lstat()
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _plain(path: Path, *, missing_leaf: bool = False) -> Path:
    candidate = Path(path).absolute()
    chain = list(reversed(candidate.parents)) + [candidate]
    for index, part in enumerate(chain):
        if index == 0:
            continue
        if not part.exists():
            if missing_leaf and part == candidate:
                continue
            raise ValueError(f"Required path is missing: {part}")
        if _is_reparse(part):
            raise ValueError(f"Reparse points are forbidden: {part}")
    return candidate


def _write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    payload = canonical(dict(value)) + b"\n"
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Immutable evidence already exists: {path}") from exc


@contextmanager
def _journal_lock(root: Path):
    path = _plain(root / LOCK)
    if not path.is_file() or path.stat().st_size != 1:
        raise ValueError("Guard journal lock is malformed")
    with path.open("r+b") as handle:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_guard(root: Path, value: Mapping[str, Any]) -> None:
    with _journal_lock(root):
        journal = _plain(root / JOURNAL)
        with journal.open("ab") as handle:
            handle.write(canonical(dict(value)) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Missing journal: {path}")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Journal row is not an object: {path}")
        rows.append(value)
    return rows


def _load_v8(executor: Path = V8_DIR / "executor.py") -> Any:
    source = _plain(executor)
    payload = source.read_bytes()
    module = types.ModuleType("cwr_v8_resume_guard_target")
    module.__file__ = str(source)
    exec(compile(payload, str(source), "exec"), module.__dict__)
    module._resume_guard_executor_path = str(source)
    module._resume_guard_executor_sha256 = hashlib.sha256(payload).hexdigest()
    return module


def _canonical_runtime(runtime_root: Path) -> tuple[Path, Path]:
    root = _plain(runtime_root)
    executor = _plain(root / V8_EXECUTOR_RELATIVE)
    if executor.parent != root:
        raise ValueError("V8 executor must be the fixed relative path beneath its runtime root")
    if sha(executor) != EXPECTED_V8_EXECUTOR_SHA256:
        raise ValueError("Canonical V8 executor SHA-256 drifted")
    contract = _json(_plain(root / "study-contract.json"))
    if contract.get("study_id") != EXPECTED_V8_STUDY_ID:
        raise ValueError("Canonical V8 study identity drifted")
    return root, executor


def _v8_static_identity(v8: Any, runtime_root: Path, executor: Path, work: Path) -> dict[str, Any]:
    contract_path = executor.with_name("study-contract.json")
    prepared = {}
    for name in (v8.BINDING, v8.ADMISSION, v8.SCHEDULE, v8.DISCLOSURE):
        path = _plain(work / name)
        if not path.is_file():
            raise ValueError(f"V8 prepared artifact is not a file: {path}")
        prepared[name] = sha(path)
    identity = work.stat()
    executor_sha = sha(executor)
    if getattr(v8, "_resume_guard_executor_path", None) != str(executor) or getattr(v8, "_resume_guard_executor_sha256", None) != executor_sha:
        raise ValueError("Loaded V8 module bytes or path are not bound to the requested executor")
    if executor_sha != EXPECTED_V8_EXECUTOR_SHA256 or v8.contract().get("study_id") != EXPECTED_V8_STUDY_ID:
        raise ValueError("Loaded V8 module identity is not the pinned canonical runtime")
    return {
        "canonical_runtime": {"root": str(runtime_root), "executor_relative_path": V8_EXECUTOR_RELATIVE.as_posix(), "executor_sha256": EXPECTED_V8_EXECUTOR_SHA256, "study_id": EXPECTED_V8_STUDY_ID},
        "executor": {"path": str(executor), "sha256": executor_sha},
        "study_contract": {"path": str(contract_path), "sha256": sha(_plain(contract_path))},
        "external_work_root": {"path": str(work), "st_dev": identity.st_dev, "st_ino": identity.st_ino},
        "prepared_artifacts": prepared,
    }


def prepare_guard(
    *,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    guard_root: Path,
    v8_runtime_root: Path = V8_DIR,
) -> dict[str, Any]:
    """Create an exclusive immutable binding; this never calls a provider."""
    runtime, executor = _canonical_runtime(v8_runtime_root)
    target = _load_v8(executor)
    work = _plain(work_root)
    # Run the target's full preparation verifier before binding its mutable root.
    binding, schedule, admission = target._verify_prepared(source_root, closed_root, v7_root, work)
    if not isinstance(binding, Mapping) or not isinstance(schedule, list) or not isinstance(admission, Mapping):
        raise ValueError("V8 preparation verifier returned an invalid shape")
    root = _plain(guard_root, missing_leaf=True)
    if root.exists():
        raise ValueError("Guard root must be created exclusively")
    if not root.parent.is_dir():
        raise ValueError("Guard parent must already exist")
    for protected in (Path(source_root).absolute(), Path(closed_root).absolute(), Path(v7_root).absolute(), work, executor.parent):
        if root == protected or root in protected.parents or protected in root.parents:
            raise ValueError("Guard root must be disjoint from V8 source, predecessor, and external work roots")
    os.mkdir(root)
    try:
        record = {
            "format_version": 1,
            "study_id": STUDY_ID,
            "status": STATUS,
            "v8_study_id": EXPECTED_V8_STUDY_ID,
            "v8_identity": _v8_static_identity(target, runtime, executor, work),
            "v8_prepared_runtime_projection": binding.get("runtime"),
        }
        _write_immutable(root / BINDING, record)
        _write_immutable(root / JOURNAL, {"event": "guard-prepared", "binding_sha256": sha(root / BINDING)})
        with (root / LOCK).open("xb") as handle:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        os.mkdir(root / CLAIMS)
        return record
    except Exception:
        # A partially written control root is intentionally never reusable.
        raise


def _guard_binding(root: Path) -> dict[str, Any]:
    root = _plain(root)
    entries = {item.name for item in root.iterdir()}
    if entries != {BINDING, JOURNAL, LOCK, CLAIMS}:
        raise ValueError("Guard root has unexpected, missing, or orphaned entries")
    for name in (BINDING, JOURNAL, LOCK):
        child = _plain(root / name)
        if not child.is_file():
            raise ValueError("Guard evidence must be regular files")
    value = _json(root / BINDING)
    if value.get("study_id") != STUDY_ID or value.get("status") != STATUS:
        raise ValueError("Guard binding identity drifted")
    claims = _plain(root / CLAIMS)
    if not claims.is_dir():
        raise ValueError("Guard claims root is not a directory")
    rows = _guard_rows(root)
    expected = {"event": "guard-prepared", "binding_sha256": sha(root / BINDING)}
    if not rows or rows[0] != expected:
        raise ValueError("Guard journal binding drifted")
    return value


def _guard_rows(root: Path) -> list[dict[str, Any]]:
    with _journal_lock(root):
        return _jsonl(_plain(root / JOURNAL))


def _claims(root: Path) -> dict[int, dict[str, Any]]:
    directory = _plain(root / CLAIMS)
    values: dict[int, dict[str, Any]] = {}
    for path in directory.iterdir():
        plain = _plain(path)
        if not plain.is_file() or not plain.name.startswith("sequence-") or not plain.name.endswith(".json"):
            raise ValueError("Guard claim topology is malformed")
        value = _json(plain)
        sequence = value.get("sequence")
        if set(value) != {"event", "sequence", "event_sha256"} or value.get("event") != "delegate-intent" or not isinstance(sequence, int) or plain.name != f"sequence-{sequence:04d}.json" or sequence in values:
            raise ValueError("Guard claim is malformed")
        values[sequence] = value
    return values


def _validate_guard_journal(root: Path, accepted: list[Mapping[str, Any]], next_event: Mapping[str, Any], *, pending_completion: int | None = None) -> set[int]:
    rows = _guard_rows(root)
    active: dict[int, dict[str, Any]] = {}
    completed: set[int] = set()
    accepted_sequences = {int(row["sequence"]) for row in accepted}
    for row in rows[1:]:
        sequence = row.get("sequence")
        if not isinstance(sequence, int):
            raise ValueError("Guard journal sequence is malformed")
        if row.get("event") == "delegate-intent":
            if set(row) != {"event", "sequence", "event_sha256"} or sequence in active or sequence in completed:
                raise ValueError("Guard intent is malformed or repeated")
            active[sequence] = row
        elif row.get("event") == "delegate-completed":
            if set(row) != {"event", "sequence", "event_sha256"} or active.get(sequence, {}).get("event_sha256") != row.get("event_sha256"):
                raise ValueError("Guard completion is malformed or unbound")
            active.pop(sequence)
            completed.add(sequence)
        else:
            raise ValueError("Guard journal contains an unknown event")
    if active:
        if set(active) != {pending_completion} or pending_completion not in accepted_sequences:
            raise ValueError("A prior delegated V8 intent lacks completion; refuse rerun or resend")
    if not completed.issubset(accepted_sequences):
        raise ValueError("A prior guarded delegate did not become a V8 accepted completion")
    if int(next_event["sequence"]) in completed:
        raise ValueError("The next V8 sequence is already guarded; refuse rerun")
    return completed


def _validate_claims(root: Path, accepted: list[Mapping[str, Any]], next_event: Mapping[str, Any], completed: set[int], *, pending_completion: int | None = None) -> None:
    accepted_sequences = {int(event["sequence"]) for event in accepted}
    claims = _claims(root)
    next_sequence = int(next_event["sequence"])
    if next_sequence in claims:
        raise ValueError("An existing guard claim blocks rerun or resend of the next V8 sequence")
    for sequence in claims:
        if sequence not in accepted_sequences:
            raise ValueError("Guard claim does not have an accepted V8 completion")
        if sequence == pending_completion:
            if sequence in completed:
                raise ValueError("Pending guard completion is already journaled")
        elif sequence not in completed:
            raise ValueError("Accepted V8 sequence lacks a completed guard claim journal row")


def _create_claim(root: Path, event: Mapping[str, Any]) -> dict[str, Any]:
    sequence = event.get("sequence")
    if not isinstance(sequence, int):
        raise ValueError("Guard event sequence is malformed")
    value = {"event": "delegate-intent", "sequence": sequence, "event_sha256": hashlib.sha256(canonical(event)).hexdigest()}
    path = _plain(root / CLAIMS / f"sequence-{sequence:04d}.json", missing_leaf=True)
    try:
        _write_immutable(path, value)
    except ValueError as exc:
        raise ValueError("An existing guard claim blocks rerun or resend") from exc
    return value


def _assert_no_unresolved_v8_state(v8: Any, work: Path) -> None:
    active: set[int] = set()
    for row in _jsonl(work / v8.JOURNAL):
        kind, sequence = row.get("event"), row.get("sequence")
        if kind in {"attempt-intent", "retry-intent", "retry-disclosure-pause"}:
            if not isinstance(sequence, int):
                raise ValueError("V8 unresolved state has a malformed sequence")
            active.add(sequence)
        elif kind == "completed" and isinstance(sequence, int):
            active.discard(sequence)
    if active:
        raise ValueError("V8 has unresolved intent or pause; refuse rerun or resend")


def _recompute_contacts(v8: Any, work: Path, accepted: list[Mapping[str, Any]]) -> int:
    rows = _jsonl(work / v8.JOURNAL)
    journaled = {row.get("sequence"): row for row in rows if row.get("event") == "provider-contacts"}
    total = 0
    for event in accepted:
        sequence = int(event["sequence"])
        if sequence == 182:
            continue
        row = journaled.pop(sequence, None)
        if row is None or not isinstance(row.get("recorded_provider_contacts"), int):
            raise ValueError("Accepted V8 event lacks a journaled provider-contact count")
        physical = len(v8._physical_output_sessions(v8._output_path(work, event).parent, event))
        if physical != row["recorded_provider_contacts"]:
            raise ValueError("Physical provider-contact topology does not equal the V8 journal")
        total += physical
    if journaled:
        raise ValueError("V8 journal has provider-contact evidence for a nonaccepted event")
    return total


def preflight(
    *,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    guard_root: Path,
    v8_runtime_root: Path = V8_DIR,
    _pending_completion: int | None = None,
) -> dict[str, Any]:
    """Verify all target and control evidence without contacting a provider."""
    runtime, executor = _canonical_runtime(v8_runtime_root)
    target = _load_v8(executor)
    work = _plain(work_root)
    root = _plain(guard_root)
    record = _guard_binding(root)
    if record["v8_identity"] != _v8_static_identity(target, runtime, executor, work):
        raise ValueError("V8 source, prepared identity, or external work-root identity drifted")
    binding, schedule, admission = target._verify_prepared(source_root, closed_root, v7_root, work)
    if record.get("v8_prepared_runtime_projection") != binding.get("runtime"):
        raise ValueError("V8 prepared runtime projection drifted")
    # `_accepted` creates recovery material only when it discovers an active
    # intent. Reject that state before entering it, so preflight remains read-only.
    _assert_no_unresolved_v8_state(target, work)
    accepted = target._accepted(work, schedule, admission)
    target._validate_contact_sessions(source_root, work, admission, accepted)
    remaining = schedule[len(accepted):]
    if not remaining:
        if _pending_completion is None:
            raise ValueError("V8 has no untouched sequence remaining")
        next_event: Mapping[str, Any] = {"sequence": -1}
    else:
        next_event = remaining[0]
        target._require_no_orphan_output_cells(work, remaining)
    completed = _validate_guard_journal(root, accepted, next_event, pending_completion=_pending_completion)
    _validate_claims(root, accepted, next_event, completed, pending_completion=_pending_completion)
    contacts = _recompute_contacts(target, work, accepted)
    return {"status": STATUS, "next_event": dict(next_event) if remaining else None, "accepted": len(accepted), "accepted_prefix": [dict(event) for event in accepted], "v8_physical_provider_contacts": contacts, "provider_calls": 0}


def dispatch_next(
    *,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    guard_root: Path,
    delegate: Callable[[Mapping[str, Any]], Any] | None = None,
    allow_remote: bool = False,
    v8_runtime_root: Path = V8_DIR,
) -> Any:
    """Journal one guarded delegate call. The default is provider-disabled."""
    result = preflight(source_root=source_root, closed_root=closed_root, v7_root=v7_root, work_root=work_root, guard_root=guard_root, v8_runtime_root=v8_runtime_root)
    if not allow_remote or delegate is None:
        raise ValueError("Remote delegation is disabled unless an explicit injected delegate is allowed")
    root = _plain(guard_root)
    event = result["next_event"]
    before = result["accepted_prefix"]
    claim = _create_claim(root, event)
    _append_guard(root, claim)
    outcome = delegate(event)
    # A delegate return is not success evidence. Re-read V8 without allowing a
    # stale target, altered session topology, or missing completion to be hidden.
    postflight = preflight(source_root=source_root, closed_root=closed_root, v7_root=v7_root, work_root=work_root, guard_root=guard_root, v8_runtime_root=v8_runtime_root, _pending_completion=int(event["sequence"]))
    if postflight["accepted_prefix"] != [*before, event]:
        raise ValueError("Delegate did not settle exactly the claimed next V8 sequence")
    _append_guard(root, {"event": "delegate-completed", "sequence": event["sequence"], "event_sha256": claim["event_sha256"]})
    return outcome
