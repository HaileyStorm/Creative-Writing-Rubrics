from __future__ import annotations

import asyncio
import functools
import importlib.util
import multiprocessing
import queue
import sys
import threading
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load"
V2_TEST = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_exec_v2_slot_acquire_transition.py"
ACK = "a" * 64


def module():
    spec = importlib.util.spec_from_file_location("_broader_exec_v3_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def v2_test_helpers():
    spec = importlib.util.spec_from_file_location("_broader_exec_v3_v2_helpers", V2_TEST)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def route(queue_root: Path):
    return v2_test_helpers().route(queue_root)


def runner(**kwargs):
    return v2_test_helpers().runner(**kwargs)


def common(tmp_path: Path):
    helpers = v2_test_helpers()
    return {"output_root": tmp_path / "roots", "frozen_root": helpers.v1_test_helpers().frozen_root(tmp_path), "queue_root": tmp_path / "queue", "authorization_acknowledgement_sha256": ACK, "route_provider": route}


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


def test_pins_v2_and_rejects_existing_partial_root_without_inspection(tmp_path: Path):
    value = module()
    assert value.V2_COMMIT == "3611a9dcba2df161b8e3fa89158c0c0b30b70bcf"
    assert value.V2_HASHES[value.V2 / "executor.py"] == "f530daf37cbd5411d34982de396fb07b33d7227c19bc2a10f7c745abc691a1d6"
    args = common(tmp_path)
    args["output_root"].mkdir()
    marker = args["output_root"] / "partial-v2-marker.bin"
    marker.write_bytes(b"immutable")
    with pytest.raises(ValueError, match="fresh"):
        value.prepare_all(**args)
    assert marker.read_bytes() == b"immutable"


def test_route_load_is_once_before_full_35_cell_wave_and_native_runs_remain_bounded(tmp_path: Path):
    value, args = module(), common(tmp_path)
    value.prepare_all(**args)
    calls = active = maximum = 0
    route_guard, runner_guard = threading.Lock(), threading.Lock()
    def serialized_route(queue_root):
        nonlocal calls, active, maximum
        with route_guard:
            calls += 1
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.05)
            return route(queue_root)
        finally:
            with route_guard:
                active -= 1
    running = current_max = 0
    def concurrent_runner(**kwargs):
        nonlocal running, current_max
        with runner_guard:
            running += 1
            current_max = max(current_max, running)
        try:
            time.sleep(0.01)
            return runner(**kwargs)
        finally:
            with runner_guard:
                running -= 1
    rows = asyncio.run(value.execute_wave(**{**args, "route_provider": serialized_route}, allow_remote=True, runner=concurrent_runner))
    assert len(rows) == 35 and all(row["state"] == "provisional_scoring_received" for row in rows)
    assert (calls, maximum) == (1, 1)
    assert 1 <= current_max <= 10


def test_eleven_direct_processes_share_exact_ten_v3_slots(tmp_path: Path):
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


def test_cli_wave_loads_route_once_and_restores_inherited_execute_one(monkeypatch, tmp_path: Path):
    value = module()
    route_loads = {"count": 0}
    active = maximum = 0
    guard = threading.Lock()
    class Runtime:
        def __init__(self):
            self.prepare_all = lambda **_kwargs: None
            self.execute_one = self.original_execute
            self.execute_wave = self.original_wave
        def original_execute(self, *, runner, **_kwargs):
            return runner()
        async def original_wave(self, *, queue_root, runner, route_provider, **_kwargs):
            semaphore = asyncio.Semaphore(10)
            async def run_cell():
                async with semaphore:
                    return await asyncio.to_thread(self.execute_one, runner=runner, queue_root=queue_root, route_provider=route_provider)
            return await asyncio.gather(*(run_cell() for _ in range(35)))
        def main(self, _argv):
            def run():
                nonlocal active, maximum
                with guard:
                    active += 1
                    maximum = max(maximum, active)
                try:
                    time.sleep(0.01)
                    return {"state": "received"}
                finally:
                    with guard:
                        active -= 1
            return asyncio.run(self.execute_wave(queue_root=tmp_path / "queue", runner=run, route_provider=None))
    runtime = Runtime()
    def validated(_runtime, _queue_root, _route_provider):
        route_loads["count"] += 1
        return lambda _queue: ({"route": "frozen"}, {"evidence": "frozen"})
    monkeypatch.setattr(value, "_runtime", lambda: runtime)
    monkeypatch.setattr(value, "_validated_route", validated)
    rows = value.main(["--execute-wave"])
    assert len(rows) == 35 and route_loads["count"] == 1 and maximum == 10
    assert runtime.execute_one.__name__ == "executed"
