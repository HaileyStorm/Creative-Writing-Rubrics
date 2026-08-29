"""Guard-owned, exact-one-event adapter for the frozen V8 continuation."""

from __future__ import annotations

import hashlib
import types
from pathlib import Path
from typing import Any, Mapping


STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-exact-one-event-adapter-v1"
STATUS = "EXACT_ONE_EVENT_ONLY"
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
GUARD_PATH = REPOSITORY / "evaluation-results" / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1" / "guard.py"
EXPECTED_GUARD_SHA256 = "fb20800c50dd374d35a6314b2c7889bc1e523cb3ab4346d13f2d27dbaa92b4c8"
EXPECTED_GUARD_STUDY_ID = "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-resume-guard-v1"
EXPECTED_V8_EXECUTOR_SHA256 = "515ea015074883be64b64ec63b832c00c8452e65cd1786dd9ba81dc23b92b2d6"
DEFAULT_V8_RUNTIME = Path(r"C:\Users\Haile\Documents\Creative-Writing-Rubrics-v8-runtime-e50dd50\evaluation-results\hbq-multisample-repeatability-v1-remainder-capacity-reset-successor-v8")


class RetryPauseTerminal(RuntimeError):
    """V8 guard v1 permanently stops after a changed-payload retry pause."""


def canonical(value: Any) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_guard() -> Any:
    if _sha(GUARD_PATH) != EXPECTED_GUARD_SHA256:
        raise ValueError("Pinned pushed V8 guard SHA-256 drifted")
    module = types.ModuleType("cwr_v8_exact_one_event_guard")
    module.__file__ = str(GUARD_PATH)
    exec(compile(GUARD_PATH.read_bytes(), str(GUARD_PATH), "exec"), module.__dict__)
    if module.STUDY_ID != EXPECTED_GUARD_STUDY_ID:
        raise ValueError("Pinned V8 guard study identity drifted")
    return module


def _load_pinned_modules(v8_runtime_root: Path) -> tuple[Any, Any, Path, Path]:
    guard = _load_guard()
    runtime, executor = guard._canonical_runtime(Path(v8_runtime_root))
    if _sha(executor) != EXPECTED_V8_EXECUTOR_SHA256:
        raise ValueError("Pinned frozen V8 executor SHA-256 drifted")
    return guard, guard._load_v8(executor), runtime, executor


def _load_pinned_successor_runner(v8: Any, runtime_projection: Mapping[str, Any]) -> Any:
    """Load the frozen V8 helper only after the target runtime is validated."""
    files = runtime_projection.get("files") if isinstance(runtime_projection, Mapping) else None
    relative = v8.SUCCESSOR_RUNNER.relative_to(v8.REPO).as_posix()
    expected = [item for item in files or [] if isinstance(item, Mapping) and item.get("path") == relative]
    if len(expected) != 1 or v8._runtime_file(v8.SUCCESSOR_RUNNER, require_tracked=False) != expected[0]:
        raise ValueError("Pinned V8 successor runner projection drifted")
    runner = v8._load_successor_runner()
    identity = runner.runtime_identity()
    if (
        not isinstance(identity, Mapping)
        or set(identity) != {"helper_id", "path", "bytes", "sha256"}
        or identity.get("path") != v8.SUCCESSOR_RUNNER.name
        or identity.get("bytes") != expected[0].get("bytes")
        or identity.get("sha256") != expected[0].get("sha256")
        or not callable(getattr(runner, "dispatch_event", None))
    ):
        raise ValueError("Pinned V8 successor runner identity drifted")
    return runner


def _exact_event(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return canonical(dict(left)) == canonical(dict(right))


def _precontact(
    *,
    guard: Any,
    v8: Any,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    guard_root: Path,
    runtime: Path,
    capacity_evidence: Path,
    disclosure_ack: Path,
    guard_event: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]], Path, Mapping[str, Any]]:
    """Run only local gates before the guard may create an intent."""
    if guard_event is None:
        guard_preflight = guard.preflight(
            source_root=source_root,
            closed_root=closed_root,
            v7_root=v7_root,
            work_root=work_root,
            guard_root=guard_root,
            v8_runtime_root=runtime,
        )
        event = guard_preflight.get("next_event")
    else:
        event = guard_event
    if not isinstance(event, Mapping):
        raise ValueError("V8 guard has no exact untouched event to delegate")
    work = v8._external(Path(work_root))
    evidence = v8._external(Path(capacity_evidence))
    acknowledgement = v8._external(Path(disclosure_ack))
    if acknowledgement != v8._work_path(work, v8.DISCLOSURE_ACK, allow_missing_leaf=False):
        raise ValueError("Disclosure acknowledgement must be the exact immutable V8 work-root acknowledgement")
    receipt = v8.validate_capacity_evidence(evidence)
    v8._validate_disclosure_ack(work, acknowledgement)
    v8._require_clean_pushed()
    binding, schedule, admission = v8._verify_prepared(source_root, closed_root, v7_root, work)
    guard._assert_no_unresolved_v8_state(v8, work)
    accepted = v8._accepted(work, schedule, admission)
    v8._validate_contact_sessions(source_root, work, admission, accepted)
    remaining = schedule[len(accepted) :]
    if not remaining or not _exact_event(remaining[0], event):
        raise ValueError("V8 guard event is no longer the exact next untouched event")
    v8._require_no_orphan_output_cells(work, remaining)
    source = v8._plain_path(Path(source_root))
    frozen = v8.read_json(source / "frozen-run-contract.json")
    if v8._runtime_projection(frozen) != binding["runtime"]:
        raise ValueError("Executed V8 runtime projection drifted before delegation")
    return dict(event), (binding, schedule, admission), source, receipt


def dispatch_one(
    *,
    source_root: Path,
    closed_root: Path,
    v7_root: Path,
    work_root: Path,
    guard_root: Path,
    capacity_evidence: Path,
    disclosure_ack: Path,
    allow_remote: bool = False,
    timeout: float = 3600.0,
    v8_runtime_root: Path = DEFAULT_V8_RUNTIME,
) -> Any:
    """Delegate one and only one V8 event through the pinned guard.

    A V8 retry-disclosure pause remains terminal in this v1 adapter. A later
    version needs a new, independently reviewed guard rather than a resend.
    """
    if not allow_remote:
        raise ValueError("Exact-one delegation requires explicit remote authority")
    guard, v8, runtime, _executor = _load_pinned_modules(Path(v8_runtime_root))
    expected_event, prepared, source, _receipt = _precontact(
        guard=guard,
        v8=v8,
        source_root=Path(source_root),
        closed_root=Path(closed_root),
        v7_root=Path(v7_root),
        work_root=Path(work_root),
        guard_root=Path(guard_root),
        runtime=runtime,
        capacity_evidence=Path(capacity_evidence),
        disclosure_ack=Path(disclosure_ack),
    )
    settle_calls = 0

    def delegate(guard_event: Mapping[str, Any]) -> Any:
        nonlocal settle_calls
        # Revalidate the target after the guard claim, then use only V8's
        # settlement primitive. Neither V8 execute nor dispatch is reachable.
        event, current_prepared, current_source, _ = _precontact(
            guard=guard,
            v8=v8,
            source_root=Path(source_root),
            closed_root=Path(closed_root),
            v7_root=Path(v7_root),
            work_root=Path(work_root),
            guard_root=Path(guard_root),
            runtime=runtime,
            capacity_evidence=Path(capacity_evidence),
            disclosure_ack=Path(disclosure_ack),
            guard_event=guard_event,
        )
        if not _exact_event(event, expected_event) or not _exact_event(guard_event, expected_event):
            raise ValueError("Guard-supplied event changed before frozen V8 settlement")
        if settle_calls:
            raise ValueError("Exact-one adapter refuses a second V8 settlement call")
        settle_calls += 1
        binding, schedule, admission = current_prepared
        work = v8._external(Path(work_root))
        accepted = v8._accepted(work, schedule, admission)
        frozen = v8.read_json(current_source / "frozen-run-contract.json")
        target_runner = _load_pinned_successor_runner(v8, binding["runtime"])
        try:
            settled = v8._settle_one(
                target_runner,
                frozen,
                current_source,
                work,
                schedule,
                admission,
                accepted,
                dict(expected_event),
                v8._external(Path(capacity_evidence)),
                v8._external(Path(disclosure_ack)),
                timeout,
                binding["runtime"],
            )
        except v8._load_hbq_runner().RetryDisclosurePause as exc:
            raise RetryPauseTerminal("V8 retry-disclosure pause is terminal under guard v1; do not resend") from exc
        if settled != [*accepted, dict(expected_event)]:
            raise ValueError("Frozen V8 settlement did not accept exactly the one guarded event")
        v8._validate_contact_sessions(current_source, work, admission, settled)
        return settled

    return guard.dispatch_next(
        source_root=Path(source_root),
        closed_root=Path(closed_root),
        v7_root=Path(v7_root),
        work_root=Path(work_root),
        guard_root=Path(guard_root),
        delegate=delegate,
        allow_remote=True,
        v8_runtime_root=runtime,
    )
