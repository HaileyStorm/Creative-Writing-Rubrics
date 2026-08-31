#!/usr/bin/env python3
"""V3 route-load serialization wrapper for the frozen 35-cell broader Grok development execution."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load"
V2_COMMIT = "3611a9dcba2df161b8e3fa89158c0c0b30b70bcf"
V2 = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v2-slot-acquire-transition"
V2_HASHES = {
    V2 / "executor.py": "f530daf37cbd5411d34982de396fb07b33d7227c19bc2a10f7c745abc691a1d6",
    V2 / "study-contract.json": "91a42b143386724109fecf251d357dfff961c4a9553bc31c14bc3dfb37202cd8",
    V2 / "README.md": "186e35b660a9617471935efe8839d3edfa3c183735d2b27dffa4707097c85f59",
    HERE.parents[1] / "tests" / "test_hbq_human_alignment_optimizer_v5_f20_broader_development_grok_exec_v2_slot_acquire_transition.py": "f1a45502de2647bcfd7d662bfdb64f1f55be090e51ce7a613cde8c25e1d304b5",
}


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


def _load_v2() -> ModuleType:
    for path, digest in V2_HASHES.items():
        if sha256(_stable(path)) != digest:
            raise ValueError("pinned V2 dependency drifted")
    path = V2 / "executor.py"
    raw = _stable(path)
    spec = importlib.util.spec_from_file_location("_broader_grok_v3_v2", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned V2")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if _stable(path) != raw:
        raise ValueError("pinned V2 changed during load")
    module.STUDY_ID = STUDY_ID
    return module


def _runtime() -> ModuleType:
    return _load_v2()._runtime()


def _validated_route(runtime: ModuleType, queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]:
    source = runtime.lifecycle().live()
    route, evidence = source._route(Path(queue_root), route_provider)
    route_bytes, evidence_bytes = canonical(route), canonical(evidence)
    def frozen(_queue_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        return json.loads(route_bytes), json.loads(evidence_bytes)
    return frozen


def admit_frozen_root(*args: Any, **kwargs: Any):
    return _runtime().admit_frozen_root(*args, **kwargs)


def prepare_all(*args: Any, **kwargs: Any):
    runtime = _runtime()
    copied = dict(kwargs)
    copied["route_provider"] = _validated_route(runtime, copied["queue_root"], copied.get("route_provider"))
    return runtime.prepare_all(*args, **copied)


def execute_one(*args: Any, **kwargs: Any):
    runtime = _runtime()
    copied = dict(kwargs)
    copied["route_provider"] = _validated_route(runtime, copied["queue_root"], copied.get("route_provider"))
    return runtime.execute_one(*args, **copied)


async def execute_wave(*args: Any, **kwargs: Any):
    runtime = _runtime()
    copied = dict(kwargs)
    copied["route_provider"] = _validated_route(runtime, copied["queue_root"], copied.get("route_provider"))
    return await runtime.execute_wave(*args, **copied)


def finalize_collector(*args: Any, **kwargs: Any):
    return _runtime().finalize_collector(*args, **kwargs)


def replay_collector(*args: Any, **kwargs: Any):
    return _runtime().replay_collector(*args, **kwargs)


def main(argv: list[str] | None = None) -> int:
    runtime = _runtime()
    original_prepare, original_execute, original_wave = runtime.prepare_all, runtime.execute_one, runtime.execute_wave
    def prepared(*args: Any, **kwargs: Any):
        copied = dict(kwargs)
        copied["route_provider"] = _validated_route(runtime, copied["queue_root"], copied.get("route_provider"))
        return original_prepare(*args, **copied)
    def executed(*args: Any, **kwargs: Any):
        copied = dict(kwargs)
        copied["route_provider"] = _validated_route(runtime, copied["queue_root"], copied.get("route_provider"))
        return original_execute(*args, **copied)
    async def waved(*args: Any, **kwargs: Any):
        copied = dict(kwargs)
        copied["route_provider"] = _validated_route(runtime, copied["queue_root"], copied.get("route_provider"))
        previous_execute = runtime.execute_one
        runtime.execute_one = original_execute
        try:
            return await original_wave(*args, **copied)
        finally:
            runtime.execute_one = previous_execute
    runtime.prepare_all, runtime.execute_one, runtime.execute_wave = prepared, executed, waved
    return runtime.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
