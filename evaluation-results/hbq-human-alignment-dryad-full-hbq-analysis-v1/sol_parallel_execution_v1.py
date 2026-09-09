"""Bounded ten-lane successor for frozen Sol requests after a reviewed handoff."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
HELPER_PATH = ROOT / "sol_continuation_native_v1.py"
OLD_PATH = ROOT / "sol_continuation_execution_v1.py"
HELPER_SHA = "2ca242c3fa004b86da1defddad24a8c76cecf0dd092138c42778b45eae042ddf"
OLD_SHA = "ea3c6a8a710fd469c8bb6340c72ead24540ba2e0d356044c72dc7182612c0757"
CAMPAIGN_ROOT = Path("C:/Users/Haile/Documents/cwr-dryad-sol-parallel-20260909-r1")
HANDOFF_SHA = "238d8808431278577e919dfe36fa15c52561660c40d1dcd7cdf47066444bd0ec"
START = 774
MAX = 5428
LANES = 10
MODEL = "gpt-5.6-sol"
REASONING = "high"
TIMEOUT = 300


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canon(v: Any) -> bytes:
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _req(v: bool, m: str) -> None:
    if not v:
        raise ValueError(m)


def _json(raw: bytes, label: str) -> dict:
    try:
        v = json.loads(raw.decode())
    except Exception as e:
        raise ValueError(label) from e
    _req(isinstance(v, dict), label)
    return v


def _new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(raw)


def _load(path: Path, sha: str, name: str):
    raw = path.read_bytes()
    _req(_sha(raw) == sha, f"{name} source differs")
    spec = importlib.util.spec_from_file_location(name, path)
    _req(spec and spec.loader, f"{name} load")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _req(path.read_bytes() == raw, f"{name} changed")
    return m


def _handoff(old_root: Path, marker: Path) -> int:
    _req(not (old_root / ".collect.lock").exists(), "old continuation lock exists")
    raw = marker.read_bytes()
    _req(_sha(raw) == HANDOFF_SHA, "handoff hash differs")
    value = _json(raw, "handoff marker")
    _req(
        marker.resolve() == (old_root / "requests/0829/handoff-stop.json").resolve()
        and value.get("schema_version") == 1
        and value.get("evidence_class") == "intentional_precontact_parallel_handoff"
        and value.get("boundary_ordinal") == 829
        and value.get("expected_accepted_prefix_through") == 828
        and value.get("new_execution_concurrency") == 10
        and value.get("consumed_request") is False
        and value.get("resend_authority") is False
        and value.get("restart_old_collector") is False,
        "handoff differs",
    )
    slot = old_root / "requests/0829"
    _req(
        slot.is_dir()
        and {path.name for path in slot.iterdir()} == {"handoff-stop.json"},
        "handoff slot contacted",
    )
    return 829


def _prefix(
    helper,
    old,
    plan: Path,
    original: Path,
    replacement: Path,
    old_root: Path,
    boundary: int,
):
    pred = dict(helper.predecessor(plan, original, replacement))
    _req(
        pred.get("through_ordinal") == 773 and pred.get("verdict_count") == 5986,
        "prefix differs",
    )
    threads = set(pred["thread_ids"])
    manifest_raw = (old_root / "campaign-manifest.json").read_bytes()
    manifest = _json(manifest_raw, "old manifest")
    _req(
        manifest == old._manifest(HELPER_SHA, pred, plan, original, replacement),
        "old manifest binding differs",
    )
    identity = pred["route_identity"]
    ledger = []
    verdict_count = pred["verdict_count"]
    for ordinal in range(START, boundary):
        req, _, _ = helper.request_payload(plan, ordinal)
        _req(req.get("ordinal") == ordinal, "old request gap")
        slot = old_root / "requests" / f"{ordinal:04d}"
        accepted = old._accepted(
            helper,
            slot,
            req,
            _sha(manifest_raw),
            identity,
            threads,
        )
        verdict_count += len(accepted["verdicts"])
        ledger.append(
            {
                "ordinal": ordinal,
                "thread_id": accepted["thread_id"],
                "files": {
                    name: _sha((slot / name).read_bytes())
                    for name in (
                        "start.json",
                        "authorization.json",
                        "route.json",
                        "response.json",
                        "provider-record.json",
                        "terminal.json",
                    )
                },
            }
        )
    _req(len(threads) == 828 and verdict_count == 6408, "handoff prefix totals differ")
    pred["thread_ids"] = sorted(threads)
    pred["through_ordinal"] = boundary - 1
    pred["verdict_count"] = verdict_count
    pred["old_campaign_manifest_sha256"] = _sha(manifest_raw)
    pred["continuation_ledger"] = ledger
    return pred


def collect(
    plan_root: Path,
    original_root: Path,
    replacement_root: Path,
    queue_root: Path,
    old_root: Path,
    handoff_marker: Path,
    *,
    through_ordinal: int,
    adapter_override=None,
    stop_path: Path | None = None,
) -> dict:
    _req(
        type(through_ordinal) is int and START <= through_ordinal <= MAX,
        "boundary differs",
    )
    helper = _load(HELPER_PATH, HELPER_SHA, "parallel helper")
    old = _load(OLD_PATH, OLD_SHA, "parallel predecessor")
    plan, original, replacement, old_root = map(
        lambda p: Path(p).resolve(),
        (plan_root, original_root, replacement_root, old_root),
    )
    boundary = _handoff(old_root, Path(handoff_marker))
    _req(through_ordinal >= boundary, "through precedes handoff")
    prefix = _prefix(helper, old, plan, original, replacement, old_root, boundary)
    identity = prefix["route_identity"]
    route = helper.route_snapshot(queue_root, identity)
    adapter = adapter_override or helper.adapter()
    root = CAMPAIGN_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".collect.lock"
    _req(not lock.exists(), "parallel lock exists")
    manifest = {
        "schema_version": 1,
        "evidence_class": "sol_parallel_execution_v1",
        "driver_sha256": _sha(Path(__file__).read_bytes()),
        "helper_sha256": HELPER_SHA,
        "old_sha256": OLD_SHA,
        "plan_root": str(plan),
        "old_root": str(old_root),
        "handoff_sha256": _sha(Path(handoff_marker).read_bytes()),
        "predecessor": prefix,
        "route_identity": identity,
        "lanes": LANES,
        "user_authority": "owner_requested_parallelism_controller_selected_ten",
        "full_study_admitted": False,
    }
    manifest_raw = _canon(manifest)
    mp = root / "campaign-manifest.json"
    if mp.exists():
        _req(mp.read_bytes() == manifest_raw, "parallel manifest differs")
    else:
        _new(mp, manifest_raw)
    token = uuid.uuid4().hex.encode()
    _new(lock, token)
    threads = set(prefix["thread_ids"])
    guard = threading.Lock()
    completed = []

    def run(ordinal: int):
        req, prompt, schema = helper.request_payload(plan, ordinal)
        _req(req.get("ordinal") == ordinal, "ordinal differs")
        slot = root / "requests" / f"{ordinal:04d}"
        _req(not slot.exists(), "parallel slot already exists")
        _new(slot / "payload" / f"request-{ordinal:04d}.txt", prompt)
        _new(slot / "payload" / f"request-{ordinal:04d}.json", schema)
        started = datetime.now(timezone.utc)
        clock = time.monotonic()
        start = {
            "schema_version": 1,
            "state": "started",
            "ordinal": ordinal,
            "manifest_sha256": _sha(manifest_raw),
            "payload": {"prompt_sha256": _sha(prompt), "schema_sha256": _sha(schema)},
            "attempt": 1,
        }
        sr = _canon(start)
        _new(slot / "start.json", sr)

        def gate():
            _req(
                _sha(Path(__file__).read_bytes()) == manifest["driver_sha256"]
                and _sha(HELPER_PATH.read_bytes()) == HELPER_SHA
                and _sha(OLD_PATH.read_bytes()) == OLD_SHA
                and mp.read_bytes() == manifest_raw
                and helper.route_snapshot(queue_root, identity) == route
                and (slot / "start.json").read_bytes() == sr
                and (slot / "payload" / f"request-{ordinal:04d}.txt").read_bytes()
                == prompt
                and (slot / "payload" / f"request-{ordinal:04d}.json").read_bytes()
                == schema,
                "parallel binding differs",
            )
            rr = _canon(route)
            _new(slot / "route.json", rr)
            _new(
                slot / "authorization.json",
                _canon(
                    {
                        "start_sha256": _sha(sr),
                        "ordinal": ordinal,
                        "route_sha256": _sha(rr),
                        "authorized_at": datetime.now(timezone.utc).isoformat(),
                        "allowance_policy": "owner_assumed_allowance_no_fresh_evidence",
                    }
                ),
            )

        failure = None
        ended = None
        elapsed = None
        try:
            content, record = adapter.call_codex(
                executable=route["codex_command"][0],
                model=MODEL,
                reasoning=REASONING,
                prompt=prompt.decode(),
                output_dir=slot,
                response_schema=slot / "payload" / f"request-{ordinal:04d}.json",
                batch_number=req["batch_number"],
                timeout=TIMEOUT,
                attempt_number=1,
                before_provider_attempt=gate,
            )
            ended = datetime.now(timezone.utc)
            elapsed = time.monotonic() - clock
            raw = content.encode()
            _new(slot / "response.json", raw)
            _new(slot / "provider-record.json", _canon(record))
            native = helper.validate_native(slot, req, route, raw, record)
            with guard:
                _req(native["thread_id"] not in threads, "thread collision")
                threads.add(native["thread_id"])
            terminal = {
                "schema_version": 1,
                "state": "accepted",
                "ordinal": ordinal,
                "start_sha256": _sha(sr),
                "response_sha256": native["response_sha256"],
                "thread_id": native["thread_id"],
            }
        except Exception as e:
            failure = e
            terminal = {
                "schema_version": 1,
                "state": "stopped_no_retry",
                "ordinal": ordinal,
                "start_sha256": _sha(sr),
                "error_type": type(e).__name__,
            }
        timing_raw = _canon(
            {
                "start_sha256": _sha(sr),
                "started_at": started.isoformat(),
                "ended_at": (ended or datetime.now(timezone.utc)).isoformat(),
                "elapsed_monotonic_seconds": elapsed
                if elapsed is not None
                else time.monotonic() - clock,
                "local_adapter_overlap_evidence_only": True,
            }
        )
        _new(slot / "dispatch-timing.json", timing_raw)
        terminal["dispatch_timing_sha256"] = _sha(timing_raw)
        _new(slot / "terminal.json", _canon(terminal))
        if failure is not None:
            raise failure
        with guard:
            completed.append(ordinal)
        return True

    try:
        existing = (
            {
                int(path.name)
                for path in (root / "requests").iterdir()
                if path.is_dir() and path.name.isdigit()
            }
            if (root / "requests").exists()
            else set()
        )
        for ordinal in sorted(existing):
            _req(
                boundary <= ordinal <= through_ordinal,
                "parallel existing slot boundary differs",
            )
            slot = root / "requests" / f"{ordinal:04d}"
            request, _, _ = helper.request_payload(plan, ordinal)
            old._accepted(helper, slot, request, _sha(manifest_raw), identity, threads)
            terminal = _json((slot / "terminal.json").read_bytes(), "parallel terminal")
            _req(
                terminal.get("dispatch_timing_sha256")
                == _sha((slot / "dispatch-timing.json").read_bytes()),
                "parallel timing binding differs",
            )
            completed.append(ordinal)
        pending = {}
        next_ordinal = boundary
        failed = False
        failures = []
        controlled = False
        with ThreadPoolExecutor(max_workers=LANES) as pool:
            while (next_ordinal <= through_ordinal and not failed) or pending:
                while (
                    not failed
                    and len(pending) < LANES
                    and next_ordinal <= through_ordinal
                    and not (stop_path and Path(stop_path).exists())
                ):
                    if next_ordinal in existing:
                        next_ordinal += 1
                        continue
                    pending[pool.submit(run, next_ordinal)] = next_ordinal
                    next_ordinal += 1
                if stop_path and Path(stop_path).exists():
                    controlled = True
                if not pending:
                    break
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    ordinal = pending.pop(future)
                    try:
                        future.result()
                    except Exception as error:
                        failed = True
                        failures.append(
                            {"ordinal": ordinal, "error_type": type(error).__name__}
                        )
                # already-running futures are drained by the loop; no new submissions after failure.
        state = (
            "stopped_no_retry"
            if failed
            else (
                "stopped_by_control"
                if controlled and next_ordinal <= through_ordinal
                else "collected"
            )
        )
        return {
            "state": state,
            "completed_ordinals": sorted(completed),
            "failures": sorted(failures, key=lambda row: row["ordinal"]),
            "through_ordinal": through_ordinal,
            "lanes": LANES,
            "full_study_admitted": False,
            "automatic_dispatch": False,
        }
    finally:
        if lock.is_file() and lock.read_bytes() == token:
            lock.unlink()
