"""Provider-free pending recovery scaffold for V8 sequence 265.

The prior guard claim remains unresolved. Independent review of the persisted
app rollout is required before a later version may authorize live recovery;
this version therefore keeps settlement disabled.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import types
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-precontact-recovery-v1"
STATUS = "NO_GO_PENDING_APP_ROLLOUT"
TARGET_SEQUENCE = 265
ROOT_TASK_ID = "01a04440-c441-7701-8bb7-7e4d5e4ac110"
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
EXACT_ONE_ADAPTER = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-exact-one-event-adapter-v1" / "adapter.py"
GUARD_PATH = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1" / "guard.py"
EXPECTED_ADAPTER_SHA256 = "ffc4c1a9e8fbf7a209fa4a5bc61e67b50c8161e74da03233a45690cc9afba734"
EXPECTED_GUARD_SHA256 = "fb20800c50dd374d35a6314b2c7889bc1e523cb3ab4346d13f2d27dbaa92b4c8"
EXPECTED_EXECUTOR_SHA256 = "515ea015074883be64b64ec63b832c00c8452e65cd1786dd9ba81dc23b92b2d6"
DEFAULT_V8_RUNTIME = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-v8-runtime-e50dd50\evaluation-results\hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8")
BINDING = "recovery-binding.json"
JOURNAL = "recovery-journal.jsonl"
LOCK = "recovery.lock"
CLAIMS = "claims"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plain(path: Path, *, missing_leaf: bool = False) -> Path:
    value = Path(path).absolute()
    for index, item in enumerate([*reversed(value.parents), value]):
        if index == 0:
            continue
        if not item.exists():
            if missing_leaf and item == value:
                continue
            raise ValueError(f"Missing required path: {item}")
        attributes = getattr(item.lstat(), "st_file_attributes", 0)
        if stat.S_ISLNK(item.lstat().st_mode) or bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Reparse points are forbidden: {item}")
    return value


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(_plain(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _plain(path).read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError("Journal row is not an object")
        rows.append(value)
    return rows


def _write_immutable(path: Path, value: Mapping[str, Any]) -> None:
    try:
        with _plain(path, missing_leaf=True).open("xb") as handle:
            handle.write(canonical(dict(value)) + b"\n")
            handle.flush(); os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Immutable artifact already exists: {path}") from exc


@contextmanager
def _recovery_lock(root: Path):
    """Serialize inspection, recovery claim creation, and the lone settlement."""
    path = _plain(root / LOCK)
    if not path.is_file() or path.stat().st_size != 1:
        raise ValueError("Recovery lock is malformed")
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


def _hex(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a lowercase SHA-256 hex commitment")
    return value


def _identities(adapter: Any, v8: Any, runtime: Path, prepared_runtime: Mapping[str, Any]) -> dict[str, Any]:
    value = {"exact_one_adapter": {"path": str(EXACT_ONE_ADAPTER), "sha256": sha(EXACT_ONE_ADAPTER)}, "guard": {"path": str(GUARD_PATH), "sha256": sha(GUARD_PATH)}, "executor": {"path": str(runtime / "executor.py"), "sha256": sha(runtime / "executor.py")}, "successor_runner": adapter._load_pinned_successor_runner(v8, prepared_runtime).runtime_identity()}
    for name in ("exact_one_adapter", "guard", "executor"):
        item = value[name]
        if set(item) != {"path", "sha256"} or not isinstance(item["path"], str):
            raise ValueError("Pinned delegate identity shape is malformed")
        _hex(item["sha256"], f"{name} identity")
    runner = value["successor_runner"]
    if not isinstance(runner, Mapping) or set(runner) != {"helper_id", "path", "bytes", "sha256"}:
        raise ValueError("Pinned successor runner identity is malformed")
    _hex(runner["sha256"], "Successor runner identity")
    return value


def _load_adapter() -> Any:
    if sha(EXACT_ONE_ADAPTER) != EXPECTED_ADAPTER_SHA256:
        raise ValueError("Pinned V8 exact-one adapter SHA-256 drifted")
    module = types.ModuleType("cwr_v8_recovery_exact_one")
    module.__file__ = str(EXACT_ONE_ADAPTER)
    exec(compile(EXACT_ONE_ADAPTER.read_bytes(), str(EXACT_ONE_ADAPTER), "exec"), module.__dict__)  # noqa: S102
    return module


def _load_modules(runtime: Path) -> tuple[Any, Any, Any, Path]:
    adapter = _load_adapter()
    if sha(GUARD_PATH) != EXPECTED_GUARD_SHA256:
        raise ValueError("Pinned V8 guard SHA-256 drifted")
    guard = adapter._load_guard()
    runtime_root, executor = guard._canonical_runtime(Path(runtime))
    if sha(executor) != EXPECTED_EXECUTOR_SHA256:
        raise ValueError("Pinned V8 executor SHA-256 drifted")
    return adapter, guard, guard._load_v8(executor), runtime_root


def _old_evidence(old_guard_root: Path, accepted: list[Mapping[str, Any]], event: Mapping[str, Any]) -> dict[str, Any]:
    root = _plain(old_guard_root)
    entries = {item.name for item in root.iterdir()}
    required = {"guard-binding.json", "guard-journal.jsonl", "guard-journal.lock", "claims"}
    if entries != required:
        raise ValueError("Old guard root has unexpected or missing evidence")
    binding = _json(root / "guard-binding.json")
    rows = _jsonl(root / "guard-journal.jsonl")
    events = {int(value["sequence"]): value for value in [*accepted, event]}
    if not all(sequence in events for sequence in range(261, TARGET_SEQUENCE + 1)):
        raise ValueError("Accepted prefix cannot bind the old guard topology")
    expected_rows = [{"event": "guard-prepared", "binding_sha256": sha(root / "guard-binding.json")}]
    expected_claims: dict[int, dict[str, Any]] = {}
    for sequence in range(261, TARGET_SEQUENCE + 1):
        claim = {"event": "delegate-intent", "sequence": sequence, "event_sha256": hashlib.sha256(canonical(dict(events[sequence]))).hexdigest()}
        expected_claims[sequence] = claim
        expected_rows.append(claim)
        if sequence != TARGET_SEQUENCE:
            expected_rows.append({"event": "delegate-completed", "sequence": sequence, "event_sha256": claim["event_sha256"]})
    if rows != expected_rows:
        raise ValueError("Old guard journal must be exactly 261-264 completed then sole unresolved seq265 intent")
    claims_dir = _plain(root / "claims")
    if {item.name for item in claims_dir.iterdir()} != {f"sequence-{sequence:04d}.json" for sequence in expected_claims}:
        raise ValueError("Old guard claims topology is not exact")
    for sequence, expected in expected_claims.items():
        if _json(claims_dir / f"sequence-{sequence:04d}.json") != expected:
            raise ValueError("Old guard claim does not bind its exact event")
    event_hash = expected_claims[TARGET_SEQUENCE]["event_sha256"]
    return {"root": str(root), "binding_sha256": sha(root / "guard-binding.json"), "journal_sha256": sha(root / "guard-journal.jsonl"), "claim_sha256": sha(claims_dir / "sequence-0265.json"), "event_sha256": event_hash, "binding_study_id": binding.get("study_id")}


def _objects(value: object) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    if isinstance(value, Mapping):
        found.append(value)
        for item in value.values(): found.extend(_objects(item))
    elif isinstance(value, list):
        for item in value: found.extend(_objects(item))
    return found


def _has_text(value: object, expected: str) -> bool:
    if isinstance(value, str): return expected in value
    if isinstance(value, int): return expected == str(value)
    if isinstance(value, Mapping): return any(_has_text(item, expected) for item in value.values())
    if isinstance(value, list): return any(_has_text(item, expected) for item in value)
    return False


def _rollout(path: Path, failed_capacity: Path, event: Mapping[str, Any], identities: Mapping[str, Any]) -> dict[str, Any]:
    raw = _plain(path).read_bytes()
    lines = [(line, json.loads(line)) for line in raw.splitlines() if line]
    if not lines:
        raise ValueError("Codex rollout JSONL is empty")
    meta_index = next((index for index, (_line, record) in enumerate(lines) if any(item.get("payload", {}).get("id") == ROOT_TASK_ID for item in _objects(record) if isinstance(item.get("payload"), Mapping))), None)
    if meta_index is None:
        raise ValueError("Codex rollout lacks the exact root task session_meta")
    adapter_text, capacity_text, event_text = str(EXACT_ONE_ADAPTER), str(_plain(failed_capacity)), hashlib.sha256(canonical(dict(event))).hexdigest()
    exec_matches = [(index, item) for index, (_line, record) in enumerate(lines) for item in _objects(record) if item.get("name") in {"functions.exec", "exec_command"} and _has_text(item, adapter_text) and _has_text(item, capacity_text) and _has_text(item, event_text)]
    if len(exec_matches) != 1:
        raise ValueError("Codex rollout lacks the exact V8 adapter capacity invocation")
    exec_index, exec_call = exec_matches[0]
    exec_id = exec_call.get("call_id") or exec_call.get("id")
    if not isinstance(exec_id, str): raise TypeError("Codex exec call lacks a stable call ID")
    exec_output_index = next((index for index in range(exec_index + 1, len(lines)) if any(item.get("call_id") == exec_id and "27739" in canonical(item).decode("utf-8") for item in _objects(lines[index][1]))), None)
    if exec_output_index is None: raise ValueError("Codex rollout lacks unified session_id 27739 for the adapter invocation")
    stdin_matches = [(index, item) for index in range(exec_output_index + 1, len(lines)) for item in _objects(lines[index][1]) if item.get("name") in {"functions.write_stdin", "write_stdin"} and _has_text(item, "27739")]
    if len(stdin_matches) != 1: raise ValueError("Codex rollout lacks one matching write_stdin call")
    stdin_index, stdin_call = stdin_matches[0]
    stdin_id = stdin_call.get("call_id") or stdin_call.get("id")
    if not isinstance(stdin_id, str): raise TypeError("Codex write_stdin call lacks a stable call ID")
    terminal_index = next((index for index in range(stdin_index + 1, len(lines)) if any(item.get("call_id") == stdin_id and "\"exit_code\":1" in canonical(item).decode("utf-8") and "ValueError: Capacity evidence is not current" in canonical(item).decode("utf-8") and "delegate_precontact.validate_capacity_evidence" in canonical(item).decode("utf-8") and "_settle_one" not in canonical(item).decode("utf-8") for item in _objects(lines[index][1]))), None)
    if terminal_index is None: raise ValueError("Codex rollout lacks the exact pre-settlement terminal capacity failure")
    selected = [meta_index, exec_index, exec_output_index, stdin_index, terminal_index]
    return {"path": str(_plain(path)), "sha256": sha(path), "line_sha256": [hashlib.sha256(lines[index][0]).hexdigest() for index in selected], "root_task_id": ROOT_TASK_ID, "exec_call_id": exec_id, "write_stdin_call_id": stdin_id, "unified_session_id": 27739, "failed_capacity_evidence_path": str(_plain(failed_capacity)), "failed_capacity_evidence_sha256": sha(failed_capacity), "event_sha256": event_text, "delegate_identities": dict(identities)}


def _no_live_v8_process(work: Path, runtime: Path) -> None:
    probe = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Select-Object -ExpandProperty CommandLine"], check=True, capture_output=True, text=True, timeout=20)
    forbidden = (str(work).lower(), str(runtime).lower())
    if any(any(token in line.lower() for token in forbidden) for line in probe.stdout.splitlines()):
        raise ValueError("A V8 process still references the work or frozen runtime root")


def _assert_no_seq265_artifacts(v8: Any, work: Path, event: Mapping[str, Any]) -> None:
    for row in _jsonl(work / v8.JOURNAL):
        if row.get("sequence") == TARGET_SEQUENCE:
            raise ValueError("V8 seq265 journal evidence exists; precontact recovery is no longer applicable")
    output = v8._output_path(work, event)
    if output.exists():
        raise ValueError("V8 seq265 output or session artifact exists; precontact recovery is no longer applicable")


def _write_root(root: Path, binding: Mapping[str, Any]) -> None:
    target = _plain(root, missing_leaf=True)
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Recovery root must be a fresh child of an existing directory")
    os.mkdir(target)
    _write_immutable(target / BINDING, binding)
    _write_immutable(target / JOURNAL, {"event": "recovery-prepared", "binding_sha256": sha(target / BINDING)})
    with (target / LOCK).open("xb") as handle:
        handle.write(b"\0"); handle.flush(); os.fsync(handle.fileno())
    os.mkdir(target / CLAIMS)


def prepare_recovery(*, source_root: Path, closed_root: Path, v7_root: Path, work_root: Path, old_guard_root: Path, rollout: Path, failed_capacity_evidence: Path, current_capacity_evidence: Path, recovery_root: Path, v8_runtime_root: Path = DEFAULT_V8_RUNTIME) -> dict[str, Any]:
    """Create the new controller root; provider calls and settlement are impossible here."""
    adapter, guard, v8, runtime = _load_modules(v8_runtime_root)
    work = v8._external(Path(work_root))
    binding, schedule, admission = v8._verify_prepared(source_root, closed_root, v7_root, work)
    guard._assert_no_unresolved_v8_state(v8, work)
    accepted = v8._accepted(work, schedule, admission)
    if not accepted or [row["sequence"] for row in accepted] != list(range(182, TARGET_SEQUENCE)):
        raise ValueError("V8 accepted prefix is not exactly seq182 through seq264")
    remaining = schedule[len(accepted):]
    if not remaining or remaining[0].get("sequence") != TARGET_SEQUENCE:
        raise ValueError("V8 seq265 is not the exact next untouched event")
    event = dict(remaining[0])
    _assert_no_seq265_artifacts(v8, work, event)
    v8._require_no_orphan_output_cells(work, remaining)
    old = _old_evidence(old_guard_root, accepted, event)
    identities = _identities(adapter, v8, runtime, binding["runtime"])
    rollout_value = _rollout(rollout, Path(failed_capacity_evidence), event, identities)
    v8.validate_capacity_evidence(v8._external(Path(current_capacity_evidence)))
    record = {"format_version": 1, "study_id": STUDY_ID, "status": STATUS, "target_sequence": TARGET_SEQUENCE,
              "old_guard": old, "rollout": rollout_value, "identities": identities,
              "roots": {"source": str(v8._plain_path(Path(source_root))), "closed": str(v8._plain_path(Path(closed_root))), "v7": str(v8._plain_path(Path(v7_root)))},
              "work": {"root": str(work), "journal_sha256": sha(work / v8.JOURNAL), "accepted_prefix_sha256": hashlib.sha256(canonical(accepted)).hexdigest(), "schedule_sha256": sha(work / v8.SCHEDULE), "event_sha256": old["event_sha256"]}}
    _write_root(recovery_root, record)
    return record


def preflight_recovery(*, recovery_root: Path, work_root: Path, current_capacity_evidence: Path, disclosure_ack: Path, v8_runtime_root: Path = DEFAULT_V8_RUNTIME) -> dict[str, Any]:
    """Recheck immutable binding and fresh 600-second V8 capacity evidence."""
    root = _plain(recovery_root)
    if {item.name for item in root.iterdir()} != {BINDING, JOURNAL, LOCK, CLAIMS}:
        raise ValueError("Recovery root has unexpected or missing artifacts")
    binding = _json(root / BINDING)
    if binding.get("study_id") != STUDY_ID or binding.get("status") != STATUS:
        raise ValueError("Recovery binding identity drifted")
    if _jsonl(root / JOURNAL) != [{"event": "recovery-prepared", "binding_sha256": sha(root / BINDING)}]:
        raise ValueError("Recovery journal is not pristine; refuse replay or resend")
    adapter, _guard, v8, runtime = _load_modules(v8_runtime_root)
    work = v8._external(Path(work_root))
    if binding["work"]["root"] != str(work) or binding["work"]["journal_sha256"] != sha(work / v8.JOURNAL):
        raise ValueError("V8 work journal changed after precontact recovery preparation")
    _current_binding, schedule, admission = v8._verify_prepared(Path(binding["roots"]["source"]), Path(binding["roots"]["closed"]), Path(binding["roots"]["v7"]), work)
    accepted = v8._accepted(work, schedule, admission)
    if (sha(work / v8.SCHEDULE) != binding["work"]["schedule_sha256"]
            or hashlib.sha256(canonical(accepted)).hexdigest() != binding["work"]["accepted_prefix_sha256"]
            or [row.get("sequence") for row in accepted] != list(range(182, TARGET_SEQUENCE))):
        raise ValueError("V8 accepted prefix or schedule changed after precontact recovery preparation")
    remaining = schedule[len(accepted):]
    if not remaining or remaining[0].get("sequence") != TARGET_SEQUENCE:
        raise ValueError("V8 seq265 is not the exact next untouched event")
    _assert_no_seq265_artifacts(v8, work, remaining[0])
    identities = _identities(adapter, v8, runtime, _current_binding["runtime"])
    old = _old_evidence(Path(binding["old_guard"]["root"]), accepted, remaining[0])
    rollout = _rollout(Path(binding["rollout"]["path"]), Path(binding["rollout"]["failed_capacity_evidence_path"]), remaining[0], identities)
    if old != binding["old_guard"] or rollout != binding["rollout"] or identities != binding["identities"]:
        raise ValueError("Old guard, app rollout, capacity evidence, or pinned delegate identities drifted")
    if v8._external(Path(disclosure_ack)) != v8._work_path(work, v8.DISCLOSURE_ACK, allow_missing_leaf=False):
        raise ValueError("Recovery requires the exact immutable V8 acknowledgement")
    v8.validate_capacity_evidence(v8._external(Path(current_capacity_evidence)))
    v8._validate_disclosure_ack(work, v8._external(Path(disclosure_ack)))
    return {"provider_calls": 0, "target_sequence": TARGET_SEQUENCE, "status": STATUS}


def settle_one_after_review(*, source_root: Path, closed_root: Path, v7_root: Path, work_root: Path, recovery_root: Path, current_capacity_evidence: Path, disclosure_ack: Path, allow_remote: bool = False, timeout: float = 3600.0, v8_runtime_root: Path = DEFAULT_V8_RUNTIME) -> list[dict[str, Any]]:
    """Reserved exact-one settlement implementation; live use is currently NO-GO.

    The claim is intentionally written before calling the frozen primitive, so
    a crash, timeout, or ambiguous native result cannot be retried by this
    package.
    """
    if STATUS == "NO_GO_PENDING_APP_ROLLOUT":
        raise ValueError("V8 seq265 recovery is NO-GO until the real app rollout is independently reviewed")
    if not allow_remote:
        raise ValueError("Recovery settlement requires explicit remote authority")
    root = _plain(recovery_root)
    with _recovery_lock(root):
        # This re-reads the old guard and app rollout before an irreversible claim.
        preflight_recovery(recovery_root=root, work_root=work_root, current_capacity_evidence=current_capacity_evidence, disclosure_ack=disclosure_ack, v8_runtime_root=v8_runtime_root)
        _no_live_v8_process(Path(work_root), Path(v8_runtime_root))
        claims = _plain(root / CLAIMS)
        if any(claims.iterdir()):
            raise ValueError("Recovery root already has a settlement claim; refuse repeat or resend")
        binding_record = _json(root / BINDING)
        event_hash = binding_record["work"]["event_sha256"]
        claim = {"event": "settlement-intent", "sequence": TARGET_SEQUENCE, "event_sha256": event_hash}
        _write_immutable(claims / f"sequence-{TARGET_SEQUENCE:04d}.json", claim)
        with _plain(root / JOURNAL).open("ab") as handle:
            handle.write(canonical(claim) + b"\n"); handle.flush(); os.fsync(handle.fileno())
        adapter, guard, v8, _runtime = _load_modules(v8_runtime_root)
        work = v8._external(Path(work_root))
        target_binding, schedule, admission = v8._verify_prepared(source_root, closed_root, v7_root, work)
        guard._assert_no_unresolved_v8_state(v8, work)
        accepted = v8._accepted(work, schedule, admission)
        remaining = schedule[len(accepted):]
        if ([row.get("sequence") for row in accepted] != list(range(182, TARGET_SEQUENCE))
                or not remaining or remaining[0].get("sequence") != TARGET_SEQUENCE
                or hashlib.sha256(canonical(dict(remaining[0]))).hexdigest() != event_hash):
            raise ValueError("V8 seq265 target changed after the recovery claim")
        v8._require_no_orphan_output_cells(work, remaining)
        v8.validate_capacity_evidence(v8._external(Path(current_capacity_evidence)))
        v8._validate_disclosure_ack(work, v8._external(Path(disclosure_ack)))
        v8._require_clean_pushed()
        source = v8._plain_path(Path(source_root))
        frozen = v8.read_json(source / "frozen-run-contract.json")
        if v8._runtime_projection(frozen) != target_binding["runtime"]:
            raise ValueError("Frozen runtime projection drifted after recovery claim")
        runner = adapter._load_pinned_successor_runner(v8, target_binding["runtime"])
        settled = v8._settle_one(runner, frozen, source, work, schedule, admission, accepted, dict(remaining[0]), v8._external(Path(current_capacity_evidence)), v8._external(Path(disclosure_ack)), timeout, target_binding["runtime"])
        expected = [*accepted, dict(remaining[0])]
        if settled != expected:
            raise ValueError("Recovery settlement did not accept exactly seq265")
        v8._validate_contact_sessions(source, work, admission, settled)
        completed = {"event": "settlement-completed", "sequence": TARGET_SEQUENCE, "event_sha256": event_hash}
        with _plain(root / JOURNAL).open("ab") as handle:
            handle.write(canonical(completed) + b"\n"); handle.flush(); os.fsync(handle.fileno())
        return settled
