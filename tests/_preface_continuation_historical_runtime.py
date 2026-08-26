"""Test-only archived runner binding for the sealed preface continuation chain.

The continuation's public binding committed the parent runner at ``e807c5d``.
It is not a current-runtime acceptance claim: this bridge supplies that exact
historical byte stream only while replaying the immutable v3-v5 lineage tests.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any


SOURCE_COMMIT = "e807c5d25519737cff66915c7bbf66a1b87eb853"
RUNNER_RELATIVE = "src/hbqrs/runner.py"
RUNNER_SHA256 = "0a22bf30781d6bbbde4c9b6a6e214891fe95aefddade6f955f5634f6accde4d2"
RUNNER_BYTES = 124_714

_SNAPSHOTS: dict[str, tuple[tempfile.TemporaryDirectory[str], Path]] = {}


def install(executor: ModuleType) -> ModuleType:
    """Redirect only the continuation binding's runner fingerprint to its seal."""

    continuation = _continuation(executor)
    if getattr(continuation, "_preface_historical_runner_installed", False):
        return executor

    parent = continuation._parent()
    current_runner = (Path(parent.REPOSITORY) / RUNNER_RELATIVE).resolve()
    current = current_runner.read_bytes()
    if hashlib.sha256(current).hexdigest() == RUNNER_SHA256 and len(current) == RUNNER_BYTES:
        raise ValueError("Historical runner bridge is obsolete; remove it instead of shadowing current runtime")

    snapshot = _snapshot(Path(parent.REPOSITORY))
    original_fingerprint = continuation._fingerprint

    def fingerprint(path: Path) -> dict[str, Any]:
        if path.resolve() == current_runner:
            _assert_snapshot(snapshot)
            return original_fingerprint(snapshot)
        return original_fingerprint(path)

    continuation._fingerprint = fingerprint
    continuation._preface_historical_runner_installed = True
    continuation._preface_historical_runner_snapshot = snapshot
    return executor


def _continuation(executor: ModuleType) -> ModuleType:
    direct = getattr(executor, "_continuation", None)
    if callable(direct):
        return direct()
    for name in ("_v3", "_v4"):
        nested = getattr(executor, name, None)
        if callable(nested):
            return _continuation(nested())
    raise ValueError("Preface recovery executor has no continuation parent")


def _snapshot(repository: Path) -> Path:
    key = str(repository.resolve())
    cached = _SNAPSHOTS.get(key)
    if cached is not None:
        return cached[1]
    completed = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{RUNNER_RELATIVE}"],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError("Pinned preface historical runner commit is unavailable")
    payload = completed.stdout
    if len(payload) != RUNNER_BYTES or hashlib.sha256(payload).hexdigest() != RUNNER_SHA256:
        raise ValueError("Pinned preface historical runner bytes do not match the continuation seal")
    lease = tempfile.TemporaryDirectory(prefix="cwr-preface-continuation-historical-runner-")
    path = Path(lease.name) / RUNNER_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    _SNAPSHOTS[key] = lease, path
    return path


def _assert_snapshot(path: Path) -> None:
    payload = path.read_bytes()
    if len(payload) != RUNNER_BYTES or hashlib.sha256(payload).hexdigest() != RUNNER_SHA256:
        raise ValueError("Pinned preface historical runner bytes were mutated")
