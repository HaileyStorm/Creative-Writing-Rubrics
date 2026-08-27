"""Test-only archived runner binding for sealed Ox Alpha v6-v8 evidence.

The external Ox roots committed the shared runner from ``e807c5d``.  They are
historical evidence, not a claim about the current runtime.  This bridge gives
the predecessor loaders that exact byte stream while they mechanically replay
their frozen contracts; it never changes a sealed root or a current launch.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

SOURCE_COMMIT = "e807c5d25519737cff66915c7bbf66a1b87eb853"
RUNNER_RELATIVE = "src/hbqrs/runner.py"
RUNNER_SHA256 = "0a22bf30781d6bbbde4c9b6a6e214891fe95aefddade6f955f5634f6accde4d2"
RUNNER_BYTES = 124_714
BUNDLES_RELATIVE = "bundles/all_bundles.json"
BUNDLES_SHA256 = "06390140d0d1f83b9e8a1a8ab946a4d90ac2b8c6b8d81f84cc44c4cf54a54096"
BUNDLES_BYTES = 513_512

_SNAPSHOTS: dict[tuple[str, str], tuple[tempfile.TemporaryDirectory[str], Path]] = {}
_RUNNER_MODULES: dict[str, ModuleType] = {}


@contextmanager
def historical_recovery(module: ModuleType) -> Iterator[ModuleType]:
    """Temporarily mount the exact runner and bundles sealed by recovery v1.

    This is a test-only historical adapter.  It changes only the imported
    recovery module in memory and restores it on exit; current production
    imports, sealed roots, and provider routes remain untouched.
    """

    if getattr(module, "_ox_historical_recovery_installed", False):
        raise ValueError("Ox historical recovery adapter is already installed")
    repository = _repository_for_module(module)
    runner_snapshot = _snapshot(repository)
    bundles_snapshot = _snapshot_file(repository, BUNDLES_RELATIVE, BUNDLES_SHA256, BUNDLES_BYTES)
    historical_runner = _load_runner(runner_snapshot)
    original_runner = module.hbq_runner
    original_bundles_path = module.bundles_path
    module.hbq_runner = historical_runner
    module.bundles_path = lambda: bundles_snapshot
    module._ox_historical_recovery_installed = True
    try:
        yield module
    finally:
        module.hbq_runner = original_runner
        module.bundles_path = original_bundles_path
        del module._ox_historical_recovery_installed


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


def _repository_for_module(module: ModuleType) -> Path:
    try:
        return _repository(module)
    except ValueError:
        path = Path(module.__file__).resolve()
        for candidate in (path.parent, *path.parents):
            if (candidate / ".git").exists():
                return candidate
        raise ValueError("Ox historical runtime cannot locate its repository") from None


def _snapshot(repository: Path) -> Path:
    return _snapshot_file(repository, RUNNER_RELATIVE, RUNNER_SHA256, RUNNER_BYTES)


def _snapshot_file(repository: Path, relative: str, expected_sha256: str, expected_bytes: int) -> Path:
    key = (str(repository.resolve()), relative)
    cached = _SNAPSHOTS.get(key)
    if cached is not None:
        payload = cached[1].read_bytes()
        if len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise ValueError(f"Pinned Ox historical bytes were mutated: {relative}")
        return cached[1]
    completed = subprocess.run(
        ["git", "show", f"{SOURCE_COMMIT}:{relative}"],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise ValueError(f"Pinned Ox historical file is unavailable: {relative}")
    payload = completed.stdout
    if relative == BUNDLES_RELATIVE and hashlib.sha256(payload).hexdigest() != expected_sha256:
        # The sealed Windows bundle is the historical JSON materialized with
        # CRLF.  Accept that representation only when its exact frozen seal
        # matches; no current bundle bytes are treated as historical.
        payload = payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if len(payload) != expected_bytes or hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError(f"Pinned Ox historical bytes do not match the frozen seal: {relative}")
    prefix = "cwr-ox-historical-runner-" if relative == RUNNER_RELATIVE else "cwr-ox-historical-bundles-"
    lease = tempfile.TemporaryDirectory(prefix=prefix)
    path = Path(lease.name) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    _SNAPSHOTS[key] = lease, path
    return path


def _load_runner(snapshot: Path) -> ModuleType:
    key = str(snapshot)
    cached = _RUNNER_MODULES.get(key)
    if cached is not None:
        return cached
    name = f"hbqrs._ox_historical_runner_{RUNNER_SHA256[:12]}"
    spec = importlib.util.spec_from_file_location(name, snapshot)
    if spec is None or spec.loader is None:
        raise ValueError("Pinned Ox historical runner cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    _RUNNER_MODULES[key] = module
    return module


def _fingerprint(path: Path) -> dict[str, Any]:
    _assert_snapshot(path)
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _assert_snapshot(path: Path) -> None:
    payload = path.read_bytes()
    if len(payload) != RUNNER_BYTES or hashlib.sha256(payload).hexdigest() != RUNNER_SHA256:
        raise ValueError("Pinned Ox historical runner bytes were mutated")
