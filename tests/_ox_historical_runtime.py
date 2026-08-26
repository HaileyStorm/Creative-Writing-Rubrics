"""Test-only archived runner binding for sealed Ox Alpha v6-v8 evidence.

The external Ox roots committed the shared runner from ``e807c5d``.  They are
historical evidence, not a claim about the current runtime.  This bridge gives
the predecessor loaders that exact byte stream while they mechanically replay
their frozen contracts; it never changes a sealed root or a current launch.
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


def install(module: ModuleType) -> ModuleType:
    """Patch only a study module's historical runner fingerprint in memory."""

    if getattr(module, "_ox_historical_runner_installed", False):
        return module
    original_bindings = module.runtime_bindings
    snapshot = _snapshot(_repository(module))

    def runtime_bindings() -> dict[str, Any]:
        bindings = dict(original_bindings())
        current = bindings.get("runner")
        if not isinstance(current, dict):
            raise ValueError("Ox historical runtime has no runner binding")
        if current.get("sha256") == RUNNER_SHA256 and current.get("bytes") == RUNNER_BYTES:
            raise ValueError("Ox historical runner bridge is obsolete; remove it instead")
        _assert_snapshot(snapshot)
        bindings["runner"] = _fingerprint(snapshot)
        return bindings

    module.runtime_bindings = runtime_bindings
    _install_parent(module, "_parent_v6")
    _install_parent(module, "parent_v7")
    _install_parent(module, "parent_v8")
    _install_verifier(module, "_parent_v6_verifier", snapshot)
    _install_verifier(module, "v7_verifier", snapshot)
    module._ox_historical_runner_installed = True
    module._ox_historical_runner_snapshot = snapshot
    return module


def install_orphan_adjudication_compat(module: ModuleType) -> ModuleType:
    """Treat only Windows' stale-PID response as a dead historical claimant."""

    if getattr(module, "_ox_orphan_adjudication_compat_installed", False):
        return module
    original_pid_live = module._pid_live

    def pid_live(pid: Any) -> bool:
        try:
            return original_pid_live(pid)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 11:
                return False
            raise

    module._pid_live = pid_live
    module._ox_orphan_adjudication_compat_installed = True
    return module


def _install_parent(module: ModuleType, name: str) -> None:
    parent = getattr(module, name, None)
    if not callable(parent):
        return

    def pinned_parent() -> ModuleType:
        return install(parent())

    setattr(module, name, pinned_parent)


def _install_verifier(module: ModuleType, name: str, snapshot: Path) -> None:
    verifier = getattr(module, name, None)
    if not callable(verifier):
        return

    def pinned_verifier(*args: Any, **kwargs: Any) -> ModuleType:
        return _install_verifier_runner(verifier(*args, **kwargs), snapshot)

    setattr(module, name, pinned_verifier)


def _install_verifier_runner(verifier: ModuleType, snapshot: Path) -> ModuleType:
    if getattr(verifier, "_ox_historical_runner_installed", False):
        return verifier
    original_fingerprint = verifier.fingerprint
    current_runner = Path(verifier.run_judge.__code__.co_filename).resolve()

    def fingerprint(path: Path) -> dict[str, Any]:
        if path.resolve() == current_runner:
            _assert_snapshot(snapshot)
            return _fingerprint(snapshot)
        return original_fingerprint(path)

    verifier.fingerprint = fingerprint
    verifier._ox_historical_runner_installed = True
    return verifier


def _repository(module: ModuleType) -> Path:
    root = getattr(module, "REPO_ROOT", None)
    if not isinstance(root, Path) or not (root / ".git").exists():
        raise ValueError("Ox historical runtime cannot locate its repository")
    return root.resolve()


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
        raise ValueError("Pinned Ox historical runner commit is unavailable")
    payload = completed.stdout
    if len(payload) != RUNNER_BYTES or hashlib.sha256(payload).hexdigest() != RUNNER_SHA256:
        raise ValueError("Pinned Ox historical runner bytes do not match the frozen seal")
    lease = tempfile.TemporaryDirectory(prefix="cwr-ox-historical-runner-")
    path = Path(lease.name) / RUNNER_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    _SNAPSHOTS[key] = lease, path
    return path


def _fingerprint(path: Path) -> dict[str, Any]:
    _assert_snapshot(path)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _assert_snapshot(path: Path) -> None:
    payload = path.read_bytes()
    if len(payload) != RUNNER_BYTES or hashlib.sha256(payload).hexdigest() != RUNNER_SHA256:
        raise ValueError("Pinned Ox historical runner bytes were mutated")
