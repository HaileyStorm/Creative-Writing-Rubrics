from __future__ import annotations

import asyncio
import functools
import hashlib
import importlib.util
import json
import multiprocessing
import queue
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v2-slot-acquire-transition"
V1_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_exec_v1.py"
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("_broader_exec_v2_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def v1_test_helpers():
    spec = importlib.util.spec_from_file_location("_broader_exec_v2_v1_helpers", V1_TEST)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def route(queue_root: Path):
    return v1_test_helpers().route(queue_root)


def runner(**kwargs):
    return v1_test_helpers().runner(**kwargs)


def common(tmp_path: Path):
    return {"output_root": tmp_path / "roots", "frozen_root": v1_test_helpers().frozen_root(tmp_path), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": route}


def gated_runner(counter, guard, entries, release, **kwargs):
    with guard:
        counter["active"] += 1
        counter["maximum"] = max(counter["maximum"], counter["active"])
    entries.put(kwargs["output_dir"].name)
    try:
        if not release.wait(30):
            raise TimeoutError("test gate release timed out")
        return runner(**kwargs)
    finally:
        with guard:
            counter["active"] -= 1


def direct_worker(common_args, cell_id, counter, guard, entries, release, outcomes):
    value = module()
    try:
        result = value.execute_one(**common_args, cell_id=cell_id, allow_remote=True, runner=functools.partial(gated_runner, counter, guard, entries, release))
        outcomes.put(("ok", result.get("cell_id")))
    except BaseException as error:
        outcomes.put(("error", type(error).__name__, str(error)))


def test_pins_v1_and_rejects_existing_partial_root_without_inspection(tmp_path: Path):
    value = module()
    assert value.V1_COMMIT == "a5479d188f1aff30a29f83efee0d0d82af4fb692"
    assert value.V1_HASHES[value.V1 / "executor.py"] == "5627da86559efc7293ed9de40448cff5ae93a757564c9bed1f600e5f7cfc4d0a"
    args = common(tmp_path)
    args["output_root"].mkdir()
    marker = args["output_root"] / "partial-v1-marker.bin"
    marker.write_bytes(b"immutable")
    with pytest.raises(ValueError, match="fresh"):
        value.prepare_all(**args)
    assert marker.read_bytes() == b"immutable"


def test_fileexists_stable_drift_from_release_recreate_is_rescanned_not_fatal(tmp_path: Path):
    value, runtime = module(), module()._runtime()
    root = tmp_path / "roots"
    root.mkdir()
    locks, root_hash = runtime._slot_root(root)
    path = locks / "slot-0.lock"
    old = runtime._slot_record(cell_id="old", slot=0, output_root_sha256=root_hash)
    replacement = runtime._slot_record(cell_id="replacement", slot=0, output_root_sha256=root_hash)
    runtime._write_slot(path, old)
    original_stable, changed = runtime.stable, {"value": False}
    def drifting(candidate):
        if candidate == path and not changed["value"]:
            changed["value"] = True
            path.unlink()
            runtime._write_slot(path, replacement)
            raise ValueError("stable read drift")
        return original_stable(candidate)
    runtime.stable = drifting
    try:
        acquired, record = value._acquire_global_slot(root, "new", runtime)
    finally:
        runtime.stable = original_stable
    try:
        assert changed["value"] and acquired.name == "slot-1.lock"
    finally:
        runtime._release_global_slot(acquired, record)
        runtime._release_global_slot(path, replacement)


def test_ordinary_35_cell_fake_wave_remains_bounded(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    active = maximum = 0
    guard = threading.Lock()
    def concurrent(**kwargs):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.01)
            return runner(**kwargs)
        finally:
            with guard:
                active -= 1
    rows = asyncio.run(value.execute_wave(**args, allow_remote=True, runner=concurrent))
    assert len(rows) == len(prepared["prepared_cells"]) == 35
    assert all(row["state"] == "provisional_scoring_received" for row in rows)
    assert 1 <= maximum <= value.MAX_CONCURRENCY


def test_eleven_direct_processes_share_exact_ten_v2_slots(tmp_path: Path):
    value, args = module(), common(tmp_path)
    prepared = value.prepare_all(**args)
    context = multiprocessing.get_context("spawn")
    with context.Manager() as manager:
        counter, guard, release = manager.dict(active=0, maximum=0), manager.Lock(), manager.Event()
        entries, outcomes = context.Queue(), context.Queue()
        common_args = {key: item for key, item in args.items() if key != "route_provider"}
        common_args["route_provider"] = route
        workers = [context.Process(target=direct_worker, args=(common_args, cell_id, counter, guard, entries, release, outcomes)) for cell_id in prepared["prepared_cells"][:11]]
        for worker in workers:
            worker.start()
        entered = {entries.get(timeout=45) for _ in range(10)}
        assert len(entered) == 10 and counter["maximum"] == 10
        with pytest.raises(queue.Empty):
            entries.get(timeout=0.5)
        release.set()
        for worker in workers:
            worker.join(60)
        assert all(worker.exitcode == 0 for worker in workers)
        assert sorted(outcomes.get(timeout=5) for _ in workers) == [("ok", cell_id) for cell_id in sorted(prepared["prepared_cells"][:11])]
        assert dict(counter) == {"active": 0, "maximum": 10}
