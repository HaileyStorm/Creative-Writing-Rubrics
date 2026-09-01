from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "evaluation-results" / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v2-slot-visibility"


def module():
    spec = importlib.util.spec_from_file_location("_desc13_lower_step_v2_test", PACKAGE / "executor.py")
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def v1_support():
    path = ROOT / "tests" / "test_hbq_human_alignment_optimizer_v6_desc13_lower_step_grok_exec_v1.py"
    spec = importlib.util.spec_from_file_location("_desc13_lower_step_v1_support", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    try:
        spec.loader.exec_module(value)
    finally:
        sys.modules.pop(spec.name, None)
    return value


def test_contract_pins_every_committed_v1_artifact_and_v2_remains_fresh_root_successor():
    value = module()
    contract = value.contract()
    assert contract == value._expected_contract()
    assert contract["pinned_v1"]["commit"] == value.V1_COMMIT
    assert contract["prohibitions"] == ["fresh output root only", "no fallback or resend", "no provider contact in preparation or slot repair"]


def test_held_winning_slot_visibility_retries_without_crash_overcap_or_contact(tmp_path: Path):
    value = module()
    runtime = value.slot_runtime()
    assert runtime.STUDY_ID == value.STUDY_ID
    output = tmp_path / "fresh-output"
    output.mkdir()
    original_write, original_stable = runtime._write_slot, runtime.stable
    writer_open, release_writer, sharing_seen = threading.Event(), threading.Event(), threading.Event()
    release_holders, ten_holders = threading.Event(), threading.Event()
    guard = threading.Lock()
    holders: dict[str, tuple[Path, dict]] = {}
    maximum_holders = 0
    errors: list[Exception] = []
    contacts = 0

    def write_slot(path: Path, record: dict):
        if path.name == "slot-0.lock" and not writer_open.is_set():
            runtime._plain(path.parent, directory=True)
            with path.open("xb") as handle:
                handle.write(runtime.canonical(record))
                handle.flush()
                os.fsync(handle.fileno())
                writer_open.set()
                assert release_writer.wait(20)
            return
        original_write(path, record)

    def read_slot(path: Path):
        if path.name == "slot-0.lock" and writer_open.is_set() and not release_writer.is_set():
            sharing_seen.set()
            error = PermissionError(5, "Access is denied", str(path))
            error.winerror = 5
            raise error
        return original_stable(path)

    runtime._write_slot, runtime.stable = write_slot, read_slot

    def worker(cell_id: str):
        nonlocal maximum_holders
        try:
            slot = value._acquire_global_slot(runtime, output, cell_id)
            with guard:
                holders[cell_id] = slot
                maximum_holders = max(maximum_holders, len(holders))
                if len(holders) == value.MAX_CONCURRENCY:
                    ten_holders.set()
            if cell_id != "winner":
                assert release_holders.wait(20)
                with guard:
                    held = holders.pop(cell_id)
                runtime._release_global_slot(*held)
        except (AssertionError, OSError, ValueError) as error:
            errors.append(error)

    winner = threading.Thread(target=worker, args=("winner",))
    winner.start()
    assert writer_open.wait(10)
    losers = [threading.Thread(target=worker, args=(f"loser-{index}",)) for index in range(value.MAX_CONCURRENCY)]
    for thread in losers:
        thread.start()
    assert sharing_seen.wait(10)
    release_writer.set()
    winner.join(10)
    assert ten_holders.wait(10)
    with guard:
        held_winner = holders.pop("winner")
    runtime._release_global_slot(*held_winner)
    assert ten_holders.wait(10)
    release_holders.set()
    for thread in losers:
        thread.join(20)
    assert not errors
    assert maximum_holders == value.MAX_CONCURRENCY
    assert contacts == 0
    locks, _root_hash = runtime._slot_root(output)
    assert not list(locks.iterdir())


def test_size_or_mtime_drift_is_retryable_but_stable_corruption_is_rejected(tmp_path: Path):
    value = module()
    runtime = value.slot_runtime()
    output = tmp_path / "fresh-output"
    output.mkdir()
    locks, root_hash = runtime._slot_root(output)
    path = locks / "slot-0.lock"
    record = runtime._slot_record(cell_id="drift", slot=0, output_root_sha256=root_hash)
    runtime._write_slot(path, record)
    original_stable = runtime.stable

    def drift(target: Path):
        raw = original_stable(target)
        target.write_bytes(raw + b" ")
        raise ValueError("stable read drift")

    runtime.stable = drift
    assert value._read_occupied_slot(runtime, path, slot=0, output_root_sha256=root_hash) is None
    runtime.stable = original_stable
    with pytest.raises(ValueError, match="global execution slot"):
        value._read_occupied_slot(runtime, path, slot=0, output_root_sha256=root_hash)


def test_direct_lifecycle_apis_and_main_reject_tampered_package_before_arguments(monkeypatch: pytest.MonkeyPatch):
    value = module()
    calls = 0

    def reject():
        nonlocal calls
        calls += 1
        raise ValueError("V2 package tampered")

    monkeypatch.setattr(value, "validate_package", reject)
    entries = [
        lambda: value.slot_runtime(),
        lambda: value.prepare_all(),
        lambda: value.execute_one(),
        lambda: asyncio.run(value.execute_wave()),
        lambda: value.finalize_collector(),
        lambda: value.replay_collector(),
        lambda: value.main(["--help"]),
    ]
    for entry in entries:
        with pytest.raises(ValueError, match="package tampered"):
            entry()
    assert calls == len(entries)


def test_direct_prepare_rejects_an_extra_package_artifact_before_arguments(monkeypatch: pytest.MonkeyPatch):
    value = module()
    original_iterdir = value.Path.iterdir

    def with_extra(path: Path):
        entries = list(original_iterdir(path))
        if path == value.HERE:
            entries.append(path / "unexpected.txt")
        return iter(entries)

    monkeypatch.setattr(value.Path, "iterdir", with_extra)
    with pytest.raises(ValueError, match="package inventory drifted"):
        value.prepare_all()


def test_validate_package_rejects_contract_and_v1_lineage_tampering(monkeypatch: pytest.MonkeyPatch):
    value = module()
    original_stable = value.stable
    tampered_contract = value._expected_contract()
    tampered_contract["geometry"]["grok_cells"] += 1

    def contract_tamper(path: Path):
        if path == value.HERE / "study-contract.json":
            return value.canonical(tampered_contract)
        return original_stable(path)

    monkeypatch.setattr(value, "stable", contract_tamper)
    with pytest.raises(ValueError, match="study contract drifted"):
        value.validate_package()
    with pytest.raises(ValueError, match="study contract drifted"):
        value.prepare_all()

    monkeypatch.setattr(value, "stable", lambda path: b"tampered" if path == value.V1 / "executor.py" else original_stable(path))
    with pytest.raises(ValueError, match="pinned V1 dependency drifted"):
        value.validate_package()
    with pytest.raises(ValueError, match="pinned V1 dependency drifted"):
        value.execute_one()


def test_v2_repeated_waves_use_windows_safe_slots_without_exceeding_ten_lanes(tmp_path: Path):
    value, support = module(), v1_support()
    shared = support.common(tmp_path)
    for index in range(2):
        args = {**shared, "output_root": tmp_path / f"output-{index}", "queue_root": tmp_path / f"queue-{index}"}
        value.prepare_all(**args)
        concurrency: dict[str, int] = {}
        fake, calls = support.runner(value, concurrency=concurrency)
        rows = asyncio.run(value.execute_wave(**args, allow_remote=True, runner=fake))
        assert len(rows) == calls["count"] == 35
        assert 1 <= concurrency["maximum"] <= value.MAX_CONCURRENCY
