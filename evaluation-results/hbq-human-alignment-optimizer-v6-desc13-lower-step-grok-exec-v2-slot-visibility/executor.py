#!/usr/bin/env python3
"""Windows-safe slot-visibility successor for the lower-step Grok execution."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v2-slot-visibility"
V1_COMMIT = "6411361bc2929f95cc7d745ddd90a5162e2226c5"
V1 = HERE.parent / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v1"
V1_TEST = REPO / "tests" / "test_hbq_human_alignment_optimizer_v6_desc13_lower_step_grok_exec_v1.py"
V1_HASHES = {
    V1 / "executor.py": "ad86eb68ccd2bad67473e3f54f6191fb8654b2bfd33a937efbbcda94e3a49ec6",
    V1 / "study-contract.json": "66017a72f570d388d5f5cb84ac66b9cfd05bb42e711ac0d1770b6156c2fbcddd",
    V1 / "README.md": "ea0378ae7a25cf5dd78ecbec4e8cf837fb10d4b52a29ce8a20cd84f81354abc5",
    V1_TEST: "4e32afceb8c609153b9266fdc636c3a56bd9529ffe3f86db138bca28357c2a8c",
}
MAX_CONCURRENCY = 10
SLOT_WAIT_SECONDS = 60.0
SLOT_RETRY_SECONDS = 0.01
PACKAGE_FILES = frozenset({"README.md", "executor.py", "study-contract.json"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def stable(path: Path) -> bytes:
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode), before.st_size)
    if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size) or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("stable read drift")
    return raw


def _blob(path: Path) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{V1_COMMIT}:{path.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned V1 Git blob is absent")
    return result.stdout


def _load_v1() -> ModuleType:
    for path, digest in V1_HASHES.items():
        raw = stable(path)
        if sha256(raw) != digest or _blob(path) != raw:
            raise ValueError("pinned V1 dependency drifted")
    path = V1 / "executor.py"
    raw = stable(path)
    spec = importlib.util.spec_from_file_location("_desc13_lower_step_v2_v1", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned V1")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if stable(path) != raw:
        raise ValueError("pinned V1 changed during load")
    return module


def _sharing_or_lock(error: OSError) -> bool:
    return isinstance(error, PermissionError) and getattr(error, "winerror", None) == 5 or getattr(error, "winerror", None) in {32, 33}


def _read_occupied_slot(runtime: ModuleType, path: Path, *, slot: int, output_root_sha256: str) -> tuple[bytes, tuple[int, int, int, int]] | None:
    before: tuple[int, int, int, int] | None = None
    try:
        runtime._plain(path, directory=False)
        before = runtime._slot_fingerprint(path)
        raw = runtime.stable(path)
        after = runtime._slot_fingerprint(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        if not _sharing_or_lock(error):
            raise
        try:
            runtime._plain(path, directory=False)
            after = runtime._slot_fingerprint(path)
        except FileNotFoundError:
            return None
        except OSError as retry_error:
            if not _sharing_or_lock(retry_error):
                raise
            return None
        if before is None or after != before:
            return None
        return None
    except ValueError as error:
        if str(error) != "stable read drift":
            raise
        try:
            runtime._plain(path, directory=False)
            after = runtime._slot_fingerprint(path)
        except FileNotFoundError:
            return None
        except OSError as retry_error:
            if _sharing_or_lock(retry_error):
                return None
            raise
        if before is None or after[:2] != before[:2] or after == before:
            raise
        return None
    if after != before:
        return None
    runtime._validate_slot(raw, slot=slot, output_root_sha256=output_root_sha256)
    return raw, after


def _acquire_global_slot(runtime: ModuleType, output_root: Path, cell_id: str) -> tuple[Path, dict[str, Any]]:
    locks, root_hash = runtime._slot_root(output_root)
    deadline = time.monotonic() + SLOT_WAIT_SECONDS
    while time.monotonic() < deadline:
        for slot in range(MAX_CONCURRENCY):
            path = locks / f"slot-{slot}.lock"
            record = runtime._slot_record(cell_id=cell_id, slot=slot, output_root_sha256=root_hash)
            try:
                runtime._write_slot(path, record)
                return path, record
            except FileExistsError:
                read = _read_occupied_slot(runtime, path, slot=slot, output_root_sha256=root_hash)
                if read is None and path.exists():
                    try:
                        runtime._slot_fingerprint(path)
                    except FileNotFoundError:
                        pass
                    except OSError as error:
                        if not _sharing_or_lock(error):
                            raise
        time.sleep(SLOT_RETRY_SECONDS)
    raise TimeoutError("global Grok ten-slot semaphore did not become available")


def _expected_contract() -> dict[str, Any]:
    return {
        "format_version": 1,
        "kind": "windows_safe_slot_visibility_successor",
        "study_id": STUDY_ID,
        "pinned_v1": {
            "commit": V1_COMMIT,
            "executor_sha256": V1_HASHES[V1 / "executor.py"],
            "study_contract_sha256": V1_HASHES[V1 / "study-contract.json"],
            "readme_sha256": V1_HASHES[V1 / "README.md"],
            "test_sha256": V1_HASHES[V1_TEST],
        },
        "geometry": {"candidates": 5, "development_groups": 7, "grok_cells": 35},
        "prohibitions": ["fresh output root only", "no fallback or resend", "no provider contact in preparation or slot repair"],
    }


def contract() -> dict[str, Any]:
    raw = stable(HERE / "study-contract.json")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid study contract") from error
    if not isinstance(value, dict) or canonical(value) != raw or value != _expected_contract():
        raise ValueError("study contract drifted")
    return value


def _package_source_inventory() -> None:
    _plain(HERE, directory=True)
    entries = {path.name: path for path in HERE.iterdir()}
    if set(entries) - {"__pycache__"} != PACKAGE_FILES:
        raise ValueError("V2 package inventory drifted")
    for name in PACKAGE_FILES:
        _plain(entries[name], directory=False)
    cache = entries.get("__pycache__")
    if cache is not None:
        _plain(cache, directory=True)
        for path in cache.iterdir():
            _plain(path, directory=False)
            if path.suffix != ".pyc":
                raise ValueError("unsafe V2 package cache artifact")


def validate_package() -> None:
    _package_source_inventory()
    contract()
    _load_v1()


def _runtime() -> ModuleType:
    validate_package()
    module = _load_v1()
    module.STUDY_ID = STUDY_ID
    expected_v1_contract = module._expected_contract()
    module.contract = lambda: expected_v1_contract
    original_v3_runtime = module.v3_runtime

    def patched_v3_runtime() -> ModuleType:
        v3 = original_v3_runtime()
        original_runtime = v3._runtime

        def patched_runtime() -> ModuleType:
            runtime = original_runtime()
            runtime._acquire_global_slot = lambda output_root, cell_id: _acquire_global_slot(runtime, output_root, cell_id)
            return runtime

        v3._runtime = patched_runtime
        return v3

    module.v3_runtime = patched_v3_runtime
    return module


def slot_runtime() -> ModuleType:
    module = _runtime()
    runtime = module.v3_runtime()._runtime()
    runtime.STUDY_ID = STUDY_ID
    return runtime


def prepare_all(**kwargs: Any):
    return _runtime().prepare_all(**kwargs)


def execute_one(**kwargs: Any):
    return _runtime().execute_one(**kwargs)


async def execute_wave(**kwargs: Any):
    return await _runtime().execute_wave(**kwargs)


def finalize_collector(**kwargs: Any):
    return _runtime().finalize_collector(**kwargs)


def replay_collector(**kwargs: Any):
    return _runtime().replay_collector(**kwargs)


def main(argv: list[str] | None = None) -> int:
    return _runtime().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
