"""Late-capacity, one-settlement composition for the frozen V8 continuation."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import types
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-multisample-repeatability-v1-v8-late-capacity-adapter-v1"
STATUS = "NO_GO_UNTIL_ISOLATED_TESTS_PASS"
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
QUERY_ONLY = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-v8-query-only-process-adapter-v1" / "adapter.py"
EXACT_ONE = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-exact-one-event-adapter-v1" / "adapter.py"
GUARD = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1" / "guard.py"
EXPECTED_QUERY_ONLY_SHA256 = "39405850d20f9963b7ea7a760441611133ecc2d6b0b3d6a26efa17af432e0b53"
EXPECTED_EXACT_ONE_SHA256 = "ffc4c1a9e8fbf7a209fa4a5bc61e67b50c8161e74da03233a45690cc9afba734"
EXPECTED_GUARD_SHA256 = "fb20800c50dd374d35a6314b2c7889bc1e523cb3ab4346d13f2d27dbaa92b4c8"
CONTRACT_PATH = HERE / "study-contract.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _strict(path: Path, label: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or canonical(value) + b"\n" != raw:
        raise ValueError(f"invalid {label}")
    return value


def validate_package() -> dict[str, Any]:
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != {"adapter.py", "README.md", "study-contract.json"}:
        raise ValueError("late-capacity package inventory drifted")
    value = _strict(CONTRACT_PATH, "study contract")
    expected = {
        "bindings": {
            "exact_one": {"path": EXACT_ONE.relative_to(REPOSITORY).as_posix(), "sha256": EXPECTED_EXACT_ONE_SHA256},
            "query_only": {"path": QUERY_ONLY.relative_to(REPOSITORY).as_posix(), "sha256": EXPECTED_QUERY_ONLY_SHA256},
            "resume_guard": {"path": GUARD.relative_to(REPOSITORY).as_posix(), "sha256": EXPECTED_GUARD_SHA256},
        },
        "dispatch": {
            "capacity_supplier": "explicit per-invocation callable returning a fresh external capacity evidence file after final heavy verification",
            "maximum_guard_claims": 1,
            "maximum_v8_settlement_calls": 1,
            "outer_duplicate_precontact": False,
            "query_only_patch": "every guard target reload",
            "retry_disclosure_pause": "terminal_no_resend_requires_distinct_guard_successor",
        },
        "format_version": 1,
        "status": STATUS,
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("late-capacity study contract drifted")
    return value


def _load_query_only() -> Any:
    if sha(QUERY_ONLY) != EXPECTED_QUERY_ONLY_SHA256 or sha(EXACT_ONE) != EXPECTED_EXACT_ONE_SHA256 or sha(GUARD) != EXPECTED_GUARD_SHA256:
        raise ValueError("pinned V8 late-capacity dependency drifted")
    module = types.ModuleType("cwr_v8_late_capacity_query_only")
    module.__file__ = str(QUERY_ONLY)
    exec(compile(QUERY_ONLY.read_bytes(), str(QUERY_ONLY), "exec"), module.__dict__)  # noqa: S102
    if module.STUDY_ID != "hbq-multisample-repeatability-v1-v8-query-only-process-adapter-v1":
        raise ValueError("query-only adapter identity drifted")
    return module


def _same_event(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return canonical(dict(left)) == canonical(dict(right))


def _final_verify(
    *,
    guard: Any,
    v8: Any,
    runtime: Path,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    disclosure_ack: Path,
    guard_event: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], Mapping[str, Any]], Path, Path]:
    """Repeat V8's full local verification only after the guard has claimed one event."""
    if not isinstance(guard_event, Mapping):
        raise ValueError("guard supplied no exact V8 event")  # noqa: TRY004 - preserves the pinned guard's invalid-event contract
    work = v8._external(Path(work_root))
    acknowledgement = v8._external(Path(disclosure_ack))
    if acknowledgement != v8._work_path(work, v8.DISCLOSURE_ACK, allow_missing_leaf=False):
        raise ValueError("disclosure acknowledgement must be the exact immutable V8 work-root acknowledgement")
    v8._validate_disclosure_ack(work, acknowledgement)
    v8._require_clean_pushed()
    binding, schedule, admission = v8._verify_prepared(source_root, closed_root, v7_root, work)
    guard._assert_no_unresolved_v8_state(v8, work)
    accepted = v8._accepted(work, schedule, admission)
    v8._validate_contact_sessions(source_root, work, admission, accepted)
    remaining = schedule[len(accepted) :]
    if not remaining or not _same_event(remaining[0], guard_event):
        raise ValueError("guard-supplied event changed before final V8 verification")
    v8._require_no_orphan_output_cells(work, remaining)
    source = v8._plain_path(Path(source_root))
    frozen = v8.read_json(source / "frozen-run-contract.json")
    if v8._runtime_projection(frozen) != binding["runtime"]:
        raise ValueError("executed V8 runtime projection drifted before delegation")
    return dict(guard_event), (binding, schedule, admission, accepted, frozen), source, acknowledgement


def _fresh_capacity_file(v8: Any, capacity_supplier: Callable[[], Path]) -> Path:
    supplied = capacity_supplier()
    if not isinstance(supplied, Path):
        raise TypeError("capacity supplier must return pathlib.Path")
    evidence = v8._external(supplied)
    before = os.stat(evidence)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("capacity supplier must return a regular immutable evidence file")
    digest = sha(evidence)
    v8.validate_capacity_evidence(evidence)
    after = os.stat(evidence)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, digest) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, sha(evidence)):
        raise ValueError("capacity evidence changed during its fresh validation")
    return evidence


def dispatch_one(
    *,
    binding_root: Path,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    guard_root: Path,
    disclosure_ack: Path,
    capacity_supplier: Callable[[], Path],
    allow_remote: bool = False,
    timeout: float = 3600.0,
    v8_runtime_root: Path,
) -> Any:
    """Settle one guarded V8 event, sourcing capacity only at the final local gate."""
    validate_package()
    query = _load_query_only()
    query._binding(Path(binding_root), Path(v8_runtime_root))
    if allow_remote is not True:
        raise ValueError("late-capacity exact-one dispatch requires explicit remote authority")
    if not callable(capacity_supplier):
        raise TypeError("capacity supplier must be callable")
    exact = query.load_query_only_exact_one()
    guard, v8, runtime, _executor = exact._load_pinned_modules(Path(v8_runtime_root))
    settlement_calls = 0
    supplier_calls = 0

    def delegate(guard_event: Mapping[str, Any]) -> Any:
        nonlocal settlement_calls, supplier_calls
        event, prepared, source, acknowledgement = _final_verify(
            guard=guard,
            v8=v8,
            runtime=runtime,
            source_root=Path(source_root),
            closed_root=Path(closed_root),
            v7_root=Path(v7_root),
            work_root=Path(work_root),
            disclosure_ack=Path(disclosure_ack),
            guard_event=guard_event,
        )
        if not _same_event(event, guard_event):
            raise ValueError("final V8 event differs from the claimed guard event")
        binding, schedule, admission, accepted, frozen = prepared
        work = v8._external(Path(work_root))
        target_runner = exact._load_pinned_successor_runner(v8, binding["runtime"])
        if supplier_calls:
            raise ValueError("late-capacity adapter refuses a second capacity supplier call")
        supplier_calls += 1
        evidence = _fresh_capacity_file(v8, capacity_supplier)
        if settlement_calls:
            raise ValueError("late-capacity adapter refuses a second V8 settlement call")
        settlement_calls += 1
        try:
            settled = v8._settle_one(
                target_runner,
                frozen,
                source,
                work,
                schedule,
                admission,
                accepted,
                dict(event),
                evidence,
                acknowledgement,
                timeout,
                binding["runtime"],
            )
        except v8._load_hbq_runner().RetryDisclosurePause as exc:
            raise exact.RetryPauseTerminal("V8 retry-disclosure pause is terminal under the late-capacity adapter; do not resend") from exc
        if settled != [*accepted, dict(event)]:
            raise ValueError("frozen V8 settlement did not accept exactly the one guarded event")
        return settled

    outcome = guard.dispatch_next(
        source_root=Path(source_root),
        closed_root=Path(closed_root),
        v7_root=Path(v7_root),
        work_root=Path(work_root),
        guard_root=Path(guard_root),
        delegate=delegate,
        allow_remote=True,
        v8_runtime_root=runtime,
    )
    if settlement_calls != 1 or supplier_calls != 1:
        raise ValueError("guarded V8 dispatch did not perform exactly one final capacity settlement")
    return outcome
