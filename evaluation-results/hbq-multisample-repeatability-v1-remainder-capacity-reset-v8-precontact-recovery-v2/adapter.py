"""Default-off exact-one recovery for the recorded V8 seq265 capacity failure."""

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

STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-precontact-recovery-v2"
STATUS = "PREPARED_DEFAULT_OFF"
TARGET_SEQUENCE = 265
ROOT_TASK_ID = "01a04440-c441-7701-8bb7-7e4d5e4ac110"
UNIFIED_SESSION_ID = 27739
POLL_COUNT = 17
REVIEWED_TERMINAL_LINE = 75128
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
EXACT_ONE_ADAPTER = (
    REPOSITORY
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-exact-one-event-adapter-v1"
    / "adapter.py"
)
GUARD_PATH = (
    REPOSITORY
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1"
    / "guard.py"
)
EXPECTED_ADAPTER_SHA256 = (
    "ffc4c1a9e8fbf7a209fa4a5bc61e67b50c8161e74da03233a45690cc9afba734"
)
EXPECTED_GUARD_SHA256 = (
    "fb20800c50dd374d35a6314b2c7889bc1e523cb3ab4346d13f2d27dbaa92b4c8"
)
EXPECTED_EXECUTOR_SHA256 = (
    "515ea015074883be64b64ec63b832c00c8452e65cd1786dd9ba81dc23b92b2d6"
)
EXPECTED_INVOCATION_INPUT_SHA256 = (
    "b2d0a1a072e66680398366addee17328088dfa3ca8ef959e7ed55d88a82f7b6f"
)
EXPECTED_TERMINAL_POLL_INPUT_SHA256 = (
    "3ee4804005040d3a4ad871e456c05e6719ca8fd1166667ca100aa60007f7e4a0"
)
EXPECTED_TERMINAL_OUTPUT_SHA256 = (
    "ca47ff106554c2635369e988b4272866a151f3bf8d73e646be9843b87a737206"
)
EXPECTED_EVENT_SHA256 = (
    "2afb48ef0bbcf3d65926f615ba08f709a97c0c1df2aaf9917a6f5b229446f876"
)
EXPECTED_FAILED_CAPACITY_SHA256 = (
    "cc06b4aceada854aa3b03ff447bb1bdba09abea48fee24ded298bcb369c8212e"
)
EXPECTED_OLD_GUARD_HASHES = {
    "guard-binding.json": "1b74ad649708afb3b4ae5c845ed74053097d72fb82ee88496f437a16d41adca9",
    "guard-journal.jsonl": "7ffe358b2d15fc55b583f7d60959c2b2abdac625fb5ca5b292daaf4ebd5e50fe",
    "claims/sequence-0265.json": "0d1f66685da2c1fda558395225f31d18511ccdcd7c6c7074e8b21668d3422260",
}
# Set only from the independent read-only review of this one historical prefix.
EXPECTED_PREFIX_BYTES = 145742307
EXPECTED_PREFIX_SHA256 = (
    "2f2a14a437c360757975a7ee5ab6dd12f92c7311b863cb9da47c56eebfec05dd"
)
DOCUMENTS = Path(r"C:\Users\Haile\Documents")
EXPECTED_PATHS = {
    "source": DOCUMENTS / "cwr-multisample-repeatability-v1-20260821-44518ab",
    "closed": DOCUMENTS / "cwr-multisample-repeatability-v1-successor-20260821-9422eff",
    "v7": DOCUMENTS / "cwr-multisample-capacity-reset-v7-live-1a2d48d",
    "work": DOCUMENTS / "cwr-multisample-capacity-reset-v8-live-e50dd50",
    "old_guard": DOCUMENTS / "cwr-v8-resume-guard-v1-33127a6",
    "failed_capacity": DOCUMENTS / "cwr-v8-capacity-evidence-265-refresh-e50dd50.json",
    "rollout": Path(
        r"C:\Users\Haile\.codex\sessions\2026\08\27\rollout-2026-08-27T11-24-50-01a04440-c441-7701-8bb7-7e4d5e4ac110.jsonl"
    ),
}
DEFAULT_V8_RUNTIME = Path(
    r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-v8-runtime-e50dd50\evaluation-results\hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8"
)
BINDING = "recovery-binding.json"
JOURNAL = "recovery-journal.jsonl"
LOCK = "recovery.lock"
CLAIMS = "claims"
PREFIX = "rollout-prefix.jsonl"
PARSER_ID = "codex-custom-tool-wrapper-v1"


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _historical_path(name: str, value: Path) -> Path:
    actual = Path(value).absolute()
    expected = Path(EXPECTED_PATHS[name]).absolute()
    if actual != expected:
        raise ValueError(f"{name} is not the exact historical recovery path")
    return actual


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
        if stat.S_ISLNK(item.lstat().st_mode) or bool(
            attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
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
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Immutable artifact already exists: {path}") from exc


def _write_immutable_bytes(path: Path, value: bytes) -> None:
    try:
        with _plain(path, missing_leaf=True).open("xb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise ValueError(f"Immutable artifact already exists: {path}") from exc


@contextmanager
def _recovery_lock(root: Path):
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


def _read_reviewed_prefix(path: Path) -> bytes:
    """Read only the reviewed complete-line prefix of a growing JSONL source."""
    with _plain(path).open("rb") as handle:
        prefix = handle.read(EXPECTED_PREFIX_BYTES)
    if (
        len(prefix) != EXPECTED_PREFIX_BYTES
        or prefix.count(b"\n") != REVIEWED_TERMINAL_LINE
    ):
        raise ValueError("Rollout source lacks the reviewed complete-line prefix")
    return prefix


def _exact_prefix_manifest(prefix: bytes) -> dict[str, Any]:
    if (
        len(prefix) != EXPECTED_PREFIX_BYTES
        or hashlib.sha256(prefix).hexdigest() != EXPECTED_PREFIX_SHA256
    ):
        raise ValueError(
            "Rollout prefix is not the independently reviewed exact historical bytes"
        )
    return {
        "parser_id": "exact-reviewed-prefix-v1",
        "parser_sha256": sha(Path(__file__)),
        "root_task_id": ROOT_TASK_ID,
        "captured_bytes": EXPECTED_PREFIX_BYTES,
        "captured_lines": REVIEWED_TERMINAL_LINE,
        "prefix_sha256": EXPECTED_PREFIX_SHA256,
        "invocation_input_sha256": EXPECTED_INVOCATION_INPUT_SHA256,
        "terminal_poll_input_sha256": EXPECTED_TERMINAL_POLL_INPUT_SHA256,
        "terminal_output_sha256": EXPECTED_TERMINAL_OUTPUT_SHA256,
        "unified_session_id": UNIFIED_SESSION_ID,
        "poll_count": POLL_COUNT,
        "failure_label": "pre_provider_pre_v8_intent_capacity_failure_at_settle_entry",
    }


def capture_rollout_prefix(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Return a stable, complete-line prefix; callers must persist it outside Git."""
    source = _plain(path)
    first = _read_reviewed_prefix(source)
    manifest = _exact_prefix_manifest(first)
    if _read_reviewed_prefix(source) != first:
        raise ValueError(
            "Rollout prefix changed, reparsed, or was truncated during capture"
        )
    return first, {"path": str(source), **manifest}


def _load_adapter() -> Any:
    if sha(EXACT_ONE_ADAPTER) != EXPECTED_ADAPTER_SHA256:
        raise ValueError("Pinned V8 exact-one adapter SHA-256 drifted")
    module = types.ModuleType("cwr_v8_recovery_exact_one")
    module.__file__ = str(EXACT_ONE_ADAPTER)
    exec(  # noqa: S102
        compile(EXACT_ONE_ADAPTER.read_bytes(), str(EXACT_ONE_ADAPTER), "exec"),
        module.__dict__,
    )
    return module


def _load_modules(runtime: Path) -> tuple[Any, Any, Any, Path]:
    if Path(runtime).absolute() != DEFAULT_V8_RUNTIME.absolute():
        raise ValueError("Runtime is not the exact historical recovery path")
    adapter = _load_adapter()
    if sha(GUARD_PATH) != EXPECTED_GUARD_SHA256:
        raise ValueError("Pinned V8 guard SHA-256 drifted")
    guard = adapter._load_guard()
    runtime_root, executor = guard._canonical_runtime(Path(runtime))
    if sha(executor) != EXPECTED_EXECUTOR_SHA256:
        raise ValueError("Pinned V8 executor SHA-256 drifted")
    return adapter, guard, guard._load_v8(executor), runtime_root


def _identities(
    adapter: Any, v8: Any, runtime: Path, prepared_runtime: Mapping[str, Any]
) -> dict[str, Any]:
    value = {
        "exact_one_adapter": {
            "path": str(EXACT_ONE_ADAPTER),
            "sha256": sha(EXACT_ONE_ADAPTER),
        },
        "guard": {"path": str(GUARD_PATH), "sha256": sha(GUARD_PATH)},
        "executor": {
            "path": str(runtime / "executor.py"),
            "sha256": sha(runtime / "executor.py"),
        },
        "successor_runner": adapter._load_pinned_successor_runner(
            v8, prepared_runtime
        ).runtime_identity(),
    }
    for name in ("exact_one_adapter", "guard", "executor"):
        item = value[name]
        if set(item) != {"path", "sha256"} or not isinstance(item["path"], str):
            raise ValueError("Pinned delegate identity shape is malformed")
        _hex(item["sha256"], f"{name} identity")
    runner = value["successor_runner"]
    if not isinstance(runner, Mapping) or set(runner) != {
        "helper_id",
        "path",
        "bytes",
        "sha256",
    }:
        raise ValueError("Pinned successor runner identity is malformed")
    _hex(runner["sha256"], "Successor runner identity")
    return value


def _old_evidence(
    old_guard_root: Path, accepted: list[Mapping[str, Any]], event: Mapping[str, Any]
) -> dict[str, Any]:
    root = _plain(old_guard_root)
    for name, digest in EXPECTED_OLD_GUARD_HASHES.items():
        if sha(_plain(root / name)) != digest:
            raise ValueError(
                "Old guard differs from the independently reviewed historical bytes"
            )
    if {item.name for item in root.iterdir()} != {
        "guard-binding.json",
        "guard-journal.jsonl",
        "guard-journal.lock",
        "claims",
    }:
        raise ValueError("Old guard root has unexpected or missing evidence")
    binding = _json(root / "guard-binding.json")
    rows = _jsonl(root / "guard-journal.jsonl")
    events = {int(value["sequence"]): value for value in [*accepted, event]}
    if not all(sequence in events for sequence in range(261, TARGET_SEQUENCE + 1)):
        raise ValueError("Accepted prefix cannot bind the old guard topology")
    expected_rows = [
        {"event": "guard-prepared", "binding_sha256": sha(root / "guard-binding.json")}
    ]
    claims: dict[int, dict[str, Any]] = {}
    for sequence in range(261, TARGET_SEQUENCE + 1):
        claim = {
            "event": "delegate-intent",
            "sequence": sequence,
            "event_sha256": hashlib.sha256(
                canonical(dict(events[sequence]))
            ).hexdigest(),
        }
        claims[sequence] = claim
        expected_rows.append(claim)
        if sequence != TARGET_SEQUENCE:
            expected_rows.append(
                {
                    "event": "delegate-completed",
                    "sequence": sequence,
                    "event_sha256": claim["event_sha256"],
                }
            )
    if rows != expected_rows:
        raise ValueError(
            "Old guard journal must be exactly 261-264 completed then sole unresolved seq265 intent"
        )
    claims_root = _plain(root / "claims")
    if {item.name for item in claims_root.iterdir()} != {
        f"sequence-{sequence:04d}.json" for sequence in claims
    }:
        raise ValueError("Old guard claims topology is not exact")
    for sequence, expected in claims.items():
        if _json(claims_root / f"sequence-{sequence:04d}.json") != expected:
            raise ValueError("Old guard claim does not bind its exact event")
    if claims[TARGET_SEQUENCE]["event_sha256"] != EXPECTED_EVENT_SHA256:
        raise ValueError(
            "Old guard seq265 claim is not the independently pinned historical event"
        )
    return {
        "root": str(root),
        "binding_sha256": sha(root / "guard-binding.json"),
        "journal_sha256": sha(root / "guard-journal.jsonl"),
        "claim_sha256": sha(claims_root / "sequence-0265.json"),
        "event_sha256": claims[TARGET_SEQUENCE]["event_sha256"],
        "binding_study_id": binding.get("study_id"),
    }


def _assert_no_seq265_artifacts(v8: Any, work: Path, event: Mapping[str, Any]) -> None:
    for row in _jsonl(work / v8.JOURNAL):
        if row.get("sequence") == TARGET_SEQUENCE:
            raise ValueError(
                "V8 seq265 journal evidence exists; precontact recovery is no longer applicable"
            )
    if v8._output_path(work, event).exists():
        raise ValueError(
            "V8 seq265 output or session artifact exists; precontact recovery is no longer applicable"
        )


def _write_root(root: Path, binding: Mapping[str, Any], prefix: bytes) -> None:
    target = _plain(root, missing_leaf=True)
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Recovery root must be a fresh child of an existing directory")
    os.mkdir(target)
    _write_immutable_bytes(target / PREFIX, prefix)
    _write_immutable(target / BINDING, binding)
    _write_immutable(
        target / JOURNAL,
        {"event": "recovery-prepared", "binding_sha256": sha(target / BINDING)},
    )
    with (target / LOCK).open("xb") as handle:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    os.mkdir(target / CLAIMS)


def prepare_recovery(
    *,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    old_guard_root: Path,
    rollout: Path,
    failed_capacity_evidence: Path,
    recovery_root: Path,
    v8_runtime_root: Path = DEFAULT_V8_RUNTIME,
) -> dict[str, Any]:
    """Capture immutable local evidence and create a fresh default-off controller root."""
    for name, value in {
        "source": source_root,
        "closed": closed_root,
        "v7": v7_root,
        "work": work_root,
        "old_guard": old_guard_root,
        "rollout": rollout,
        "failed_capacity": failed_capacity_evidence,
    }.items():
        _historical_path(name, Path(value))
    adapter, guard, v8, runtime = _load_modules(v8_runtime_root)
    work = v8._external(Path(work_root))
    prepared, schedule, admission = v8._verify_prepared(
        source_root, closed_root, v7_root, work
    )
    guard._assert_no_unresolved_v8_state(v8, work)
    accepted = v8._accepted(work, schedule, admission)
    if [row.get("sequence") for row in accepted] != list(range(182, TARGET_SEQUENCE)):
        raise ValueError("V8 accepted prefix is not exactly seq182 through seq264")
    remaining = schedule[len(accepted) :]
    if not remaining or remaining[0].get("sequence") != TARGET_SEQUENCE:
        raise ValueError("V8 seq265 is not the exact next untouched event")
    event = dict(remaining[0])
    _assert_no_seq265_artifacts(v8, work, event)
    v8._require_no_orphan_output_cells(work, remaining)
    old = _old_evidence(Path(old_guard_root), accepted, event)
    identities = _identities(adapter, v8, runtime, prepared["runtime"])
    prefix, rollout_binding = capture_rollout_prefix(Path(rollout))
    failed = _plain(Path(failed_capacity_evidence))
    if sha(failed) != EXPECTED_FAILED_CAPACITY_SHA256:
        raise ValueError(
            "Failed capacity evidence is not the exact historical immutable artifact"
        )
    record = {
        "format_version": 2,
        "study_id": STUDY_ID,
        "status": STATUS,
        "target_sequence": TARGET_SEQUENCE,
        "old_guard": old,
        "rollout": {
            **rollout_binding,
            "failed_capacity_evidence_path": str(failed),
            "failed_capacity_evidence_sha256": sha(failed),
        },
        "identities": identities,
        "roots": {
            "source": str(v8._plain_path(Path(source_root))),
            "closed": str(v8._plain_path(Path(closed_root))),
            "v7": str(v8._plain_path(Path(v7_root))),
        },
        "work": {
            "root": str(work),
            "journal_sha256": sha(work / v8.JOURNAL),
            "accepted_prefix_sha256": hashlib.sha256(canonical(accepted)).hexdigest(),
            "schedule_sha256": sha(work / v8.SCHEDULE),
            "event_sha256": old["event_sha256"],
        },
    }
    _write_root(Path(recovery_root), record, prefix)
    return record


def _binding_root(root: Path) -> dict[str, Any]:
    if {item.name for item in root.iterdir()} != {
        BINDING,
        JOURNAL,
        LOCK,
        CLAIMS,
        PREFIX,
    }:
        raise ValueError("Recovery root has unexpected or missing artifacts")
    binding = _json(root / BINDING)
    if (
        binding.get("study_id") != STUDY_ID
        or binding.get("status") != STATUS
        or binding.get("format_version") != 2
    ):
        raise ValueError("Recovery binding identity drifted")
    if _jsonl(root / JOURNAL) != [
        {"event": "recovery-prepared", "binding_sha256": sha(root / BINDING)}
    ]:
        raise ValueError("Recovery journal is not pristine; refuse replay or resend")
    return binding


def _revalidate_prefix(binding: Mapping[str, Any], root: Path) -> None:
    rollout = binding.get("rollout")
    if (
        not isinstance(rollout, Mapping)
        or rollout.get("parser_id") != "exact-reviewed-prefix-v1"
    ):
        raise ValueError("Rollout parser binding drifted")
    if rollout.get("parser_sha256") != sha(Path(__file__)):
        raise ValueError("Rollout parser source drifted")
    prefix = _plain(root / PREFIX).read_bytes()
    if len(prefix) != rollout.get("captured_bytes") or hashlib.sha256(
        prefix
    ).hexdigest() != rollout.get("prefix_sha256"):
        raise ValueError("Captured rollout prefix snapshot drifted")
    source = _plain(Path(str(rollout.get("path", ""))))
    if _read_reviewed_prefix(source) != prefix:
        raise ValueError("Rollout source prefix changed, reparsed, or was truncated")
    parsed = _exact_prefix_manifest(prefix)
    expected = {
        key: value
        for key, value in rollout.items()
        if key
        not in {
            "failed_capacity_evidence_path",
            "failed_capacity_evidence_sha256",
            "path",
        }
    }
    if parsed != expected:
        raise ValueError("Captured rollout parser commitments drifted")
    failed = _plain(Path(str(rollout.get("failed_capacity_evidence_path", ""))))
    if sha(failed) != rollout.get("failed_capacity_evidence_sha256"):
        raise ValueError("Immutable failed capacity evidence drifted")


def preflight_recovery(
    *,
    recovery_root: Path,
    work_root: Path,
    current_capacity_evidence: Path,
    disclosure_ack: Path,
    v8_runtime_root: Path = DEFAULT_V8_RUNTIME,
) -> dict[str, Any]:
    """Revalidate all local state and the independent current 600-second capacity cap."""
    root = _plain(recovery_root)
    binding = _binding_root(root)
    _revalidate_prefix(binding, root)
    adapter, _guard, v8, runtime = _load_modules(v8_runtime_root)
    work = v8._external(Path(work_root))
    if binding["work"]["root"] != str(work) or binding["work"]["journal_sha256"] != sha(
        work / v8.JOURNAL
    ):
        raise ValueError("V8 work journal changed after recovery preparation")
    prepared, schedule, admission = v8._verify_prepared(
        Path(binding["roots"]["source"]),
        Path(binding["roots"]["closed"]),
        Path(binding["roots"]["v7"]),
        work,
    )
    accepted = v8._accepted(work, schedule, admission)
    if (
        sha(work / v8.SCHEDULE) != binding["work"]["schedule_sha256"]
        or hashlib.sha256(canonical(accepted)).hexdigest()
        != binding["work"]["accepted_prefix_sha256"]
        or [row.get("sequence") for row in accepted]
        != list(range(182, TARGET_SEQUENCE))
    ):
        raise ValueError(
            "V8 accepted prefix or schedule changed after recovery preparation"
        )
    remaining = schedule[len(accepted) :]
    if not remaining or remaining[0].get("sequence") != TARGET_SEQUENCE:
        raise ValueError("V8 seq265 is not the exact next untouched event")
    _assert_no_seq265_artifacts(v8, work, remaining[0])
    identities = _identities(adapter, v8, runtime, prepared["runtime"])
    old = _old_evidence(Path(binding["old_guard"]["root"]), accepted, remaining[0])
    if old != binding["old_guard"] or identities != binding["identities"]:
        raise ValueError("Old guard or pinned delegate identities drifted")
    acknowledgement = v8._external(Path(disclosure_ack))
    if acknowledgement != v8._work_path(
        work, v8.DISCLOSURE_ACK, allow_missing_leaf=False
    ):
        raise ValueError("Recovery requires the exact immutable V8 acknowledgement")
    v8.validate_capacity_evidence(v8._external(Path(current_capacity_evidence)))
    v8._validate_disclosure_ack(work, acknowledgement)
    return {"provider_calls": 0, "target_sequence": TARGET_SEQUENCE, "status": STATUS}


def _no_live_v8_process(work: Path, runtime: Path) -> None:
    """Reject another relevant process while excluding this controller's ancestry."""
    probe = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "$ErrorActionPreference='Stop'; Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    try:
        records = json.loads(probe.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Could not parse the local process inventory") from exc
    if isinstance(records, Mapping):
        records = [records]
    if (
        not isinstance(records, list)
        or not records
        or not all(isinstance(item, Mapping) for item in records)
    ):
        raise ValueError("Local process inventory has an invalid shape")
    parents: dict[int, int] = {}
    for item in records:
        pid, parent = item.get("ProcessId"), item.get("ParentProcessId")
        if (
            type(pid) is not int
            or type(parent) is not int
            or pid < 0
            or parent < 0
            or pid in parents
        ):
            raise ValueError("Local process inventory has invalid process identities")
        parents[pid] = parent
    if os.getpid() not in parents:
        raise ValueError("Local process inventory omitted this controller")
    own: set[int] = set()
    cursor = os.getpid()
    while cursor not in own:
        own.add(cursor)
        parent = parents.get(cursor)
        if parent is None:
            break
        cursor = parent
    forbidden = (str(work).lower(), str(runtime).lower())
    for item in records:
        pid, command = item.get("ProcessId"), item.get("CommandLine")
        if pid in own or not isinstance(command, str):
            continue
        if any(token in command.lower() for token in forbidden):
            raise ValueError(
                "Another V8 process still references the work or frozen runtime root"
            )


def settle_one_after_review(
    *,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    recovery_root: Path,
    current_capacity_evidence: Path,
    disclosure_ack: Path,
    allow_remote: bool = False,
    timeout: float = 3600.0,
    v8_runtime_root: Path = DEFAULT_V8_RUNTIME,
) -> list[dict[str, Any]]:
    """Settle exactly seq265 once after explicit authority; default remains disabled."""
    if not allow_remote:
        raise ValueError("Recovery settlement requires explicit remote authority")
    root = _plain(recovery_root)
    with _recovery_lock(root):
        bound = _json(root / BINDING)
        if {
            "source": str(Path(source_root).absolute()),
            "closed": str(Path(closed_root).absolute()),
            "v7": str(Path(v7_root).absolute()),
        } != bound.get("roots") or str(Path(work_root).absolute()) != bound.get(
            "work", {}
        ).get("root"):
            raise ValueError(
                "Recovery settlement roots differ from the immutable historical binding"
            )
        preflight_recovery(
            recovery_root=root,
            work_root=work_root,
            current_capacity_evidence=current_capacity_evidence,
            disclosure_ack=disclosure_ack,
            v8_runtime_root=v8_runtime_root,
        )
        _no_live_v8_process(Path(work_root), Path(v8_runtime_root))
        claims = _plain(root / CLAIMS)
        if any(claims.iterdir()):
            raise ValueError(
                "Recovery root already has a settlement claim; refuse repeat or resend"
            )
        binding_record = _json(root / BINDING)
        event_hash = binding_record["work"]["event_sha256"]
        claim = {
            "event": "settlement-intent",
            "sequence": TARGET_SEQUENCE,
            "event_sha256": event_hash,
        }
        _write_immutable(claims / f"sequence-{TARGET_SEQUENCE:04d}.json", claim)
        with _plain(root / JOURNAL).open("ab") as handle:
            handle.write(canonical(claim) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

        adapter, guard, v8, _runtime = _load_modules(v8_runtime_root)
        work = v8._external(Path(work_root))
        prepared, schedule, admission = v8._verify_prepared(
            source_root, closed_root, v7_root, work
        )
        guard._assert_no_unresolved_v8_state(v8, work)
        accepted = v8._accepted(work, schedule, admission)
        remaining = schedule[len(accepted) :]
        if (
            [row.get("sequence") for row in accepted]
            != list(range(182, TARGET_SEQUENCE))
            or not remaining
            or remaining[0].get("sequence") != TARGET_SEQUENCE
            or hashlib.sha256(canonical(dict(remaining[0]))).hexdigest() != event_hash
        ):
            raise ValueError("V8 seq265 target changed after the recovery claim")
        _assert_no_seq265_artifacts(v8, work, remaining[0])
        v8._require_no_orphan_output_cells(work, remaining)
        acknowledgement = v8._external(Path(disclosure_ack))
        if acknowledgement != v8._work_path(
            work, v8.DISCLOSURE_ACK, allow_missing_leaf=False
        ):
            raise ValueError("Recovery requires the exact immutable V8 acknowledgement")
        v8._validate_disclosure_ack(work, acknowledgement)
        v8._require_clean_pushed()
        source = v8._plain_path(Path(source_root))
        frozen = v8.read_json(source / "frozen-run-contract.json")
        if v8._runtime_projection(frozen) != prepared["runtime"]:
            raise ValueError("Frozen runtime projection drifted after recovery claim")
        runner = adapter._load_pinned_successor_runner(v8, prepared["runtime"])
        # This is deliberately adjacent to the sole irreversible primitive call.
        v8.validate_capacity_evidence(v8._external(Path(current_capacity_evidence)))
        settled = v8._settle_one(
            runner,
            frozen,
            source,
            work,
            schedule,
            admission,
            accepted,
            dict(remaining[0]),
            v8._external(Path(current_capacity_evidence)),
            acknowledgement,
            timeout,
            prepared["runtime"],
        )
        expected = [*accepted, dict(remaining[0])]
        if settled != expected:
            raise ValueError("Recovery settlement did not accept exactly seq265")
        v8._validate_contact_sessions(source, work, admission, settled)
        completed = {
            "event": "settlement-completed",
            "sequence": TARGET_SEQUENCE,
            "event_sha256": event_hash,
        }
        with _plain(root / JOURNAL).open("ab") as handle:
            handle.write(canonical(completed) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        return settled
