"""Test-only pinned-runtime bridge for settled L2 executor suites.

The public executor packages remain immutable.  When the live registry advances,
these tests materialize the executor-declared non-code runtime inputs from its
pinned source commit and make only the in-memory test module read that snapshot.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable


_SNAPSHOTS: dict[tuple[str, str, tuple[str, ...], tuple[tuple[str, str], ...]], tuple[tempfile.TemporaryDirectory[str], dict[str, Path]]] = {}


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
            if relative.startswith("src/"):
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
                return original_git("rev-parse", f"{source_commit}:{relative}")
        return original_git(*args)

    def sha256_file(path: Path | str) -> str:
        return original_sha256_file(redirected(path))

    executor._git = git
    executor.sha256_file = sha256_file
    executor._historical_runtime_tempdir = lease
    executor._historical_runtime_paths = pinned

    def configure(frozen: ModuleType) -> ModuleType:
        _configure_frozen_module(frozen, executor, redirected, pinned)
        return frozen

    for name in ("_source", "_predecessor", "_frozen_predecessor"):
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


def _runtime_paths(executor: ModuleType) -> tuple[str, ...]:
    if hasattr(executor, "RUNTIME_BLOBS"):
        return tuple(executor.RUNTIME_BLOBS)
    return tuple(executor.RUNTIME_PATHS)


def _configure_frozen_module(
    frozen: ModuleType,
    executor: ModuleType,
    redirected: Callable[[Path | str], Path],
    pinned: dict[str, Path],
) -> None:
    """Bind frozen source/predecessor helpers to the snapshot without moving it."""

    frozen._git = executor._git
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

    modules = getattr(frozen, "load_modules", None)
    if modules is not None and "registry/all_modules.json" in pinned:
        frozen.load_modules = lambda _path=None: modules(pinned["registry/all_modules.json"])
    bundles = getattr(frozen, "load_bundles", None)
    if bundles is not None and "bundles/all_bundles.jsonl" in pinned:
        frozen.load_bundles = lambda _path=None: bundles(pinned["bundles/all_bundles.jsonl"])
    load_json = getattr(frozen, "load_json", None)
    if load_json is not None:
        frozen.load_json = lambda path: load_json(redirected(path))

    if "prompts/judge/JUDGE_PREFIX.md" in pinned and "prompts/judge/BINARY_EVALUATION_PROMPT.md" in pinned:
        frozen.binary_prompt = lambda: "\n\n".join(
            pinned[f"prompts/judge/{name}"].read_text(encoding="utf-8").replace("\r\n", "\n").strip()
            for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")
        )
