"""Test-only pinned-runtime bridge for settled L2 executor suites.

The public executor packages remain immutable.  When the live registry advances,
these tests materialize the executor-declared data and runner inputs from its
pinned source commit and make only the in-memory test module read that snapshot.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


_SNAPSHOTS: dict[tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]], tuple[tempfile.TemporaryDirectory[str], dict[str, Path]]] = {}
_EXPLICIT_RUNNERS: dict[tuple[str, str], ModuleType] = {}


def install_source(module: ModuleType, *, source_commit: str) -> ModuleType:
    """Adapt a public frozen study that declares a nested ``RUNTIME`` map."""

    repository = Path(module.REPOSITORY).resolve()
    runtime = getattr(module, "RUNTIME", None)
    if not isinstance(runtime, dict):
        runtime = getattr(module, "RUNTIME_BLOBS", None)
    if not isinstance(runtime, dict) or not runtime:
        raise ValueError("Historical source study does not declare a runtime map")
    hashes = {
        str(path): str(details["sha256"])
        for path, details in runtime.items()
        if isinstance(details, dict) and isinstance(details.get("sha256"), str)
    }
    git_blobs = all(isinstance(value, str) and len(value) == 40 for value in runtime.values())
    if git_blobs:
        hashes = {
            str(path): hashlib.sha256(_git_bytes(repository, "show", f"{source_commit}:{path}")).hexdigest()
            for path in runtime
        }
    if set(hashes) != set(runtime) and not git_blobs:
        raise ValueError("Historical source runtime bindings are malformed")
    module.SOURCE_COMMIT = source_commit
    module.RUNTIME_PATHS = tuple(runtime)
    module.PINNED_RUNTIME_HASHES = hashes
    module._git = lambda *args: _git(repository, *args)
    module._git_bytes = lambda *args: _git_bytes(repository, *args)
    install(module)
    _bind_data_runtime(module, module._historical_runtime_paths)
    return module


def load_runner(repository: Path | str, source_commit: str) -> ModuleType:
    """Load one exact historical runner without changing the global package."""

    root = Path(repository).resolve()
    key = (str(root), source_commit)
    cached = _EXPLICIT_RUNNERS.get(key)
    if cached is not None:
        return cached

    dependencies = {}
    for relative in ("src/hbqrs/core.py", "src/hbqrs/paths.py", "src/hbqrs/weights.py"):
        expected = _git(root, "rev-parse", f"{source_commit}:{relative}")
        if _git(root, "hash-object", relative) != expected:
            raise ValueError(f"Historical runner dependency differs from pinned source bytes: {relative}")
        dependencies[relative] = expected
    relative = "src/hbqrs/runner.py"
    payload = _git_bytes(root, "show", f"{source_commit}:{relative}")
    runner = _runner_module(payload, root / relative, dependencies)
    _EXPLICIT_RUNNERS[key] = runner
    return runner


def _git(repository: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repository, text=True, encoding="utf-8", capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.strip() or "Historical runner Git lookup failed")
    return done.stdout.strip()


def _git_bytes(repository: Path, *args: str) -> bytes:
    done = subprocess.run(["git", *args], cwd=repository, capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.decode("utf-8", errors="replace").strip() or "Historical runner Git lookup failed")
    return bytes(done.stdout)


def _runner_module(payload: bytes, path: Path, dependencies: dict[str, str]) -> ModuleType:
    identity = hashlib.sha256(payload).hexdigest()
    runner = ModuleType(f"hbqrs._historical_runner_{identity[:16]}")
    runner.__file__ = str(path)
    runner.__package__ = "hbqrs"
    exec(compile(payload, str(path), "exec"), runner.__dict__)
    runner.__historical_source_sha256__ = identity
    runner.__historical_dependency_blobs__ = dependencies
    return runner


def install(executor: ModuleType) -> ModuleType:
    """Adapt one loaded executor to its declared historical data runtime."""

    runtime = _runtime_paths(executor)
    source_commit = str(executor.SOURCE_COMMIT)
    expected_hashes = dict(getattr(executor, "PINNED_RUNTIME_HASHES", {}))
    key = (str(Path(executor.REPOSITORY).resolve()), source_commit, runtime, tuple(sorted((str(path), str(value)) for path, value in expected_hashes.items())))
    snapshot = _SNAPSHOTS.get(key)
    if snapshot is None:
        lease = tempfile.TemporaryDirectory(prefix="cwr-hbq-l2-historical-runtime-")
        root = Path(lease.name)
        pinned: dict[str, Path] = {}
        for relative in runtime:
            if relative.startswith("src/") and relative != "src/hbqrs/runner.py":
                continue
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = executor._git_bytes("show", f"{source_commit}:{relative}")
            # This suite's original Windows runtime used checkout CRLF bytes for
            # selected data files; retain the declared SHA-256, never a guess.
            expected = expected_hashes.get(relative)
            if expected and hashlib.sha256(payload).hexdigest() != expected:
                crlf = payload.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                if hashlib.sha256(crlf).hexdigest() == expected:
                    payload = crlf
                else:
                    raise ValueError(f"Pinned runtime bytes are unavailable: {relative}")
            target.write_bytes(payload)
            pinned[relative] = target
        snapshot = lease, pinned
        _SNAPSHOTS[key] = snapshot
    lease, pinned = snapshot
    historical_modules = _load_historical_modules(executor, pinned)

    original_git = executor._git
    original_sha256_file = executor.sha256_file

    def redirected(path: Path | str) -> Path:
        candidate = Path(path)
        try:
            relative = candidate.resolve().relative_to(Path(executor.REPOSITORY).resolve()).as_posix()
        except ValueError:
            relative = candidate.as_posix().replace("\\", "/")
        return pinned.get(relative, candidate)

    def git(*args: str) -> str:
        if len(args) == 2 and args[0] == "hash-object":
            target = redirected(args[1])
            if target != Path(args[1]):
                relative = next(path for path, candidate in pinned.items() if candidate == target)
                expected_sha256 = expected_hashes.get(relative)
                if expected_sha256:
                    if hashlib.sha256(target.read_bytes()).hexdigest() != expected_sha256:
                        raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
                return original_git("rev-parse", f"{source_commit}:{relative}")
        return original_git(*args)

    def sha256_file(path: Path | str) -> str:
        return original_sha256_file(redirected(path))

    executor._git = git
    executor.sha256_file = sha256_file
    executor._historical_runtime_tempdir = lease
    executor._historical_runtime_root = Path(lease.name)
    executor._historical_runtime_paths = pinned
    executor._historical_runtime_modules = historical_modules

    runner = historical_modules.get("src/hbqrs/runner.py")
    if runner is not None:
        _bind_production_runner(executor, runner)

    def configure(frozen: ModuleType) -> ModuleType:
        _configure_frozen_module(frozen, executor, redirected, pinned, historical_modules)
        return frozen

    for name in ("_source", "_predecessor", "_frozen_predecessor", "_lifecycle"):
        factory = getattr(executor, name, None)
        if factory is None:
            continue
        def wrapped(factory: Callable[[], ModuleType] = factory) -> ModuleType:
            return configure(factory())
        if hasattr(factory, "cache_clear"):
            # A prior failed validation must not leave a stale source module.
            factory.cache_clear()
            wrapped.cache_clear = factory.cache_clear
        executor.__dict__[name] = wrapped
    for name in ("_source", "_predecessor", "_frozen_predecessor", "_lifecycle", "_schedule_template"):
        cached = getattr(executor, name, None)
        if hasattr(cached, "cache_clear"):
            cached.cache_clear()
    return executor


def _load_historical_modules(executor: ModuleType, pinned: dict[str, Path]) -> dict[str, ModuleType]:
    """Execute declared Python runtime bytes under private test-only identities."""

    modules: dict[str, ModuleType] = {}
    runner_path = pinned.get("src/hbqrs/runner.py")
    if runner_path is not None:
        dependencies = {}
        for relative in ("src/hbqrs/core.py", "src/hbqrs/paths.py", "src/hbqrs/weights.py"):
            expected = executor._git("rev-parse", f"{executor.SOURCE_COMMIT}:{relative}")
            if executor._git("hash-object", relative) != expected:
                raise ValueError(f"Historical runner dependency differs from pinned source bytes: {relative}")
            dependencies[relative] = expected
        payload = runner_path.read_bytes()
        runner = _runner_module(payload, runner_path, dependencies)
        modules["src/hbqrs/runner.py"] = runner
    return modules


def _bind_production_runner(module: ModuleType, runner: ModuleType) -> None:
    """Inject a private pinned runner without replacing ``hbqrs.runner`` globally."""

    if hasattr(module, "production_runner"):
        module.production_runner = runner
    if hasattr(module, "_import_production_runner"):
        module._import_production_runner = lambda: runner
    if hasattr(module, "_production_runner"):
        def production_runner() -> ModuleType:
            verifier = getattr(module, "_verify_current_runtime_bytes", None)
            if verifier is not None:
                verifier()
            return runner
        module._production_runner = production_runner


def _bind_data_runtime(module: ModuleType, pinned: dict[str, Path]) -> None:
    modules = getattr(module, "load_modules", None)
    if modules is not None and "registry/all_modules.json" in pinned:
        module.load_modules = lambda _path=None: modules(pinned["registry/all_modules.json"])
    bundles = getattr(module, "load_bundles", None)
    if bundles is not None and "bundles/all_bundles.jsonl" in pinned:
        module.load_bundles = lambda _path=None: bundles(pinned["bundles/all_bundles.jsonl"])
    if "prompts/judge/JUDGE_PREFIX.md" in pinned and "prompts/judge/BINARY_EVALUATION_PROMPT.md" in pinned and hasattr(module, "binary_prompt"):
        module.binary_prompt = lambda: "\n\n".join(
            pinned[f"prompts/judge/{name}"].read_text(encoding="utf-8").replace("\r\n", "\n").strip()
            for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")
        )
    for name in ("compiled_leaf_records", "_schedule_template"):
        cached = getattr(module, name, None)
        if hasattr(cached, "cache_clear"):
            cached.cache_clear()


def _runtime_paths(executor: ModuleType) -> tuple[str, ...]:
    if hasattr(executor, "RUNTIME_BLOBS"):
        return tuple(executor.RUNTIME_BLOBS)
    return tuple(executor.RUNTIME_PATHS)


def _configure_frozen_module(
    frozen: ModuleType,
    executor: ModuleType,
    redirected: Callable[[Path | str], Path],
    pinned: dict[str, Path],
    historical_modules: dict[str, ModuleType],
) -> None:
    """Bind frozen source/predecessor helpers to the snapshot without moving it."""

    frozen._git = executor._git
    runner = historical_modules.get("src/hbqrs/runner.py")
    if runner is not None:
        _bind_production_runner(frozen, runner)
    frozen_runtime = getattr(frozen, "RUNTIME", {})
    if isinstance(frozen_runtime, dict):
        for relative, details in frozen_runtime.items():
            expected = details.get("sha256") if isinstance(details, dict) else None
            path = pinned.get(str(relative))
            if path is None or not isinstance(expected, str) or hashlib.sha256(path.read_bytes()).hexdigest() == expected:
                continue
            crlf = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            if hashlib.sha256(crlf).hexdigest() != expected:
                raise ValueError(f"Frozen source runtime bytes are unavailable: {relative}")
            path.write_bytes(crlf)
    original_sha256_file = getattr(frozen, "sha256_file", None)
    if original_sha256_file is not None:
        frozen.sha256_file = lambda path: original_sha256_file(redirected(path))

    _bind_data_runtime(frozen, pinned)
    load_json = getattr(frozen, "load_json", None)
    if load_json is not None:
        frozen.load_json = lambda path: load_json(redirected(path))
