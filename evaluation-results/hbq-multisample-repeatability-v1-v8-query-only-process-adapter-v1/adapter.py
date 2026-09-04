"""Windows query-only dead-PID adaptation for the pinned V8 exact-one path."""

from __future__ import annotations

import ctypes
import hashlib
import os
import types
from ctypes import wintypes
from pathlib import Path
from typing import Any

STUDY_ID = "hbq-multisample-repeatability-v1-v8-query-only-process-adapter-v1"
STATUS = "DEFAULT_OFF_QUERY_ONLY_PREPARATION"
HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
EXACT_ONE = (
    REPOSITORY
    / "evaluation-results"
    / "hbq-multisample-repeatability-v1-remainder-capacity-reset-v8-exact-one-event-adapter-v1"
    / "adapter.py"
)
EXPECTED_EXACT_ONE_SHA256 = (
    "ffc4c1a9e8fbf7a209fa4a5bc61e67b50c8161e74da03233a45690cc9afba734"
)
BINDING = "query-only-operational-binding.json"
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_INVALID_PARAMETER = 87


def _kernel32() -> Any:
    value = ctypes.WinDLL("kernel32", use_last_error=True)
    value.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    value.OpenProcess.restype = wintypes.HANDLE
    value.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    value.GetExitCodeProcess.restype = wintypes.BOOL
    value.CloseHandle.argtypes = [wintypes.HANDLE]
    value.CloseHandle.restype = wintypes.BOOL
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def query_only_pid_is_dead(pid: int) -> bool:
    """Return true only for absent or exited processes; uncertainty is live."""
    if os.name != "nt" or type(pid) is not int or not 1 <= pid <= 0xFFFFFFFF:
        return False
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ctypes.get_last_error() == ERROR_INVALID_PARAMETER
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value != STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _load_exact_one() -> Any:
    if sha(EXACT_ONE) != EXPECTED_EXACT_ONE_SHA256:
        raise ValueError("Pinned exact-one adapter SHA-256 drifted")
    module = types.ModuleType("cwr_v8_query_only_exact_one")
    module.__file__ = str(EXACT_ONE)
    exec(compile(EXACT_ONE.read_bytes(), str(EXACT_ONE), "exec"), module.__dict__)  # noqa: S102
    return module


def load_query_only_guard() -> Any:
    return load_query_only_exact_one()._load_guard()


def load_query_only_exact_one() -> Any:
    """Decorate every exact-one guard reload; no global module mutation occurs."""
    exact = _load_exact_one()
    original = exact._load_guard

    def load_guard() -> Any:
        guard = original()
        original_target = guard._load_v8

        def load_v8(executor: Path) -> Any:
            target = original_target(executor)
            target._pid_is_dead = query_only_pid_is_dead
            return target

        guard._load_v8 = load_v8
        return guard

    exact._load_guard = load_guard
    return exact


def _record(v8_runtime_root: Path) -> tuple[Any, dict[str, Any]]:
    exact = load_query_only_exact_one()
    guard = exact._load_guard()
    runtime, executor = guard._canonical_runtime(Path(v8_runtime_root))
    guard._plain(Path(__file__))
    guard._plain(EXACT_ONE)
    record = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": STATUS,
        "adapter": {"path": str(Path(__file__)), "sha256": sha(Path(__file__))},
        "exact_one": {"path": str(EXACT_ONE), "sha256": sha(EXACT_ONE)},
        "substitution": {
            "symbol": "target._pid_is_dead",
            "predicate": "OpenProcess(QUERY_LIMITED_INFORMATION)+GetExitCodeProcess",
            "unknown_or_access_denied": "false_fail_closed",
        },
        "guard": {"path": str(exact.GUARD_PATH), "sha256": sha(exact.GUARD_PATH)},
        "executor": {"path": str(executor), "sha256": sha(executor)},
        "runtime": str(runtime),
        "provider_calls": 0,
    }
    return guard, record


def _binding(root: Path, v8_runtime_root: Path) -> dict[str, Any]:
    guard, expected = _record(v8_runtime_root)
    root = guard._plain(Path(root))
    path = guard._plain(root / BINDING)
    if {item.name for item in root.iterdir()} != {
        BINDING
    } or path.read_bytes() != guard.canonical(expected) + b"\n":
        raise ValueError("Supplemental query-only binding drifted")
    return expected


def dispatch_one(
    *, binding_root: Path, allow_remote: bool = False, **kwargs: Any
) -> Any:
    """Gated exact-one dispatch; defaults off and preserves exact adapter gates."""
    _binding(binding_root, Path(kwargs["v8_runtime_root"]))
    if allow_remote is not True:
        raise ValueError(
            "Query-only exact-one dispatch requires explicit remote authority"
        )
    return load_query_only_exact_one().dispatch_one(allow_remote=True, **kwargs)


def preflight_one(
    *, binding_root: Path, allow_remote: bool = False, **kwargs: Any
) -> Any:
    """Run the exact adapter's local precontact gates only after operator authority."""
    _binding(binding_root, Path(kwargs["v8_runtime_root"]))
    if allow_remote is not True:
        raise ValueError("Query-only preflight requires explicit remote authority")
    exact = load_query_only_exact_one()
    guard, target, runtime, _executor = exact._load_pinned_modules(
        Path(kwargs.pop("v8_runtime_root"))
    )
    kwargs.pop("timeout", None)
    return exact._precontact(guard=guard, v8=target, runtime=runtime, **kwargs)


def prepare_operational_binding(root: Path, *, v8_runtime_root: Path) -> dict[str, Any]:
    """Create provider-free supplemental evidence for an operator-reviewed future run."""
    guard, record = _record(v8_runtime_root)
    target = guard._plain(Path(root), missing_leaf=True)
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Operational binding root must be a fresh child")
    loaded = guard._load_v8(Path(record["executor"]["path"]))
    if loaded._pid_is_dead is not query_only_pid_is_dead:
        raise ValueError("Query-only target substitution did not bind")
    target.mkdir()
    guard._write_immutable(target / BINDING, record)
    return record
