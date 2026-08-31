#!/usr/bin/env python3
"""V2 transition-safe wrapper for the frozen 35-cell broader Grok development execution."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v2-slot-acquire-transition"
V1_COMMIT = "a5479d188f1aff30a29f83efee0d0d82af4fb692"
V1 = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v1"
V1_HASHES = {
    V1 / "executor.py": "5627da86559efc7293ed9de40448cff5ae93a757564c9bed1f600e5f7cfc4d0a",
    V1 / "study-contract.json": "6adb3c100fe7280fcd8b9b361eb466e6d14bc8dc5a90182b023a21a27164af3a",
    V1 / "README.md": "3b83fc8d6a747e016d4bf983125f38c5e44e7289b1c10c976a6bfb7905ca4c43",
    HERE.parents[1] / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_exec_v1.py": "ea50e111c82bb7b26fc32fe55a11118218ff0a87911893de30438f61037e5e50",
}
MAX_CONCURRENCY = 10
SLOT_WAIT_SECONDS = 60


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _stable(path: Path) -> bytes:
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def _load_v1() -> ModuleType:
    for path, digest in V1_HASHES.items():
        if sha256(_stable(path)) != digest:
            raise ValueError("pinned V1 dependency drifted")
    path = V1 / "executor.py"
    raw = _stable(path)
    spec = importlib.util.spec_from_file_location("_broader_grok_v2_v1", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned V1")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if _stable(path) != raw:
        raise ValueError("pinned V1 changed during load")
    return module


def _transition_read(module: ModuleType, path: Path, *, slot: int, output_root_sha256: str, before: tuple[int, int, int, int] | None = None) -> tuple[bytes, tuple[int, int, int, int]] | None:
    try:
        module._plain(path, directory=False)
        before = before or module._slot_fingerprint(path)
        raw = module.stable(path)
        after = module._slot_fingerprint(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        if module._sharing_or_lock(error):
            return None
        raise
    except ValueError as error:
        if str(error) != "stable read drift":
            raise
        try:
            after = module._slot_fingerprint(path)
        except FileNotFoundError:
            return None
        except OSError as retry_error:
            if module._sharing_or_lock(retry_error):
                return None
            raise
        if after != before:
            return None
        raise
    if after != before:
        return None
    module._validate_slot(raw, slot=slot, output_root_sha256=output_root_sha256)
    return raw, after


def _acquire_global_slot(output_root: Path, cell_id: str, module: ModuleType | None = None) -> tuple[Path, dict[str, Any]]:
    module = module or _runtime()
    locks, root_hash = module._slot_root(output_root)
    deadline = time.monotonic() + SLOT_WAIT_SECONDS
    observed: dict[Path, tuple[int, int, int, int]] = {}
    while time.monotonic() < deadline:
        for slot in range(MAX_CONCURRENCY):
            path = locks / f"slot-{slot}.lock"
            record = module._slot_record(cell_id=cell_id, slot=slot, output_root_sha256=root_hash)
            try:
                module._write_slot(path, record)
                return path, record
            except FileExistsError:
                try:
                    module._plain(path, directory=False)
                    fingerprint = module._slot_fingerprint(path)
                except FileNotFoundError:
                    observed.pop(path, None)
                    continue
                except OSError as error:
                    if module._sharing_or_lock(error):
                        continue
                    raise
                if observed.get(path) == fingerprint:
                    continue
                read = _transition_read(module, path, slot=slot, output_root_sha256=root_hash, before=fingerprint)
                if read is None:
                    observed.pop(path, None)
                    continue
                _raw, fingerprint = read
                observed[path] = fingerprint
        time.sleep(0.01)
    raise TimeoutError("global Grok ten-slot semaphore did not become available")


def _runtime() -> ModuleType:
    module = _load_v1()
    module.STUDY_ID = STUDY_ID
    module._acquire_global_slot = lambda output_root, cell_id: _acquire_global_slot(output_root, cell_id, module)
    return module


def admit_frozen_root(*args: Any, **kwargs: Any):
    return _runtime().admit_frozen_root(*args, **kwargs)


def prepare_all(*args: Any, **kwargs: Any):
    return _runtime().prepare_all(*args, **kwargs)


def execute_one(*args: Any, **kwargs: Any):
    return _runtime().execute_one(*args, **kwargs)


async def execute_wave(*args: Any, **kwargs: Any):
    return await _runtime().execute_wave(*args, **kwargs)


def finalize_collector(*args: Any, **kwargs: Any):
    return _runtime().finalize_collector(*args, **kwargs)


def replay_collector(*args: Any, **kwargs: Any):
    return _runtime().replay_collector(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    return _runtime().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
