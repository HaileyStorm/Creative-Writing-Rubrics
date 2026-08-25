"""Test-only pinned runtime for settled figurative studies.

The studies retain their original contracts and result receipts.  Once the
live figurative leaf changes, their provider-free checks must still exercise
the runtime bytes that those contracts declared, rather than silently reading
the new leaf through the current checkout.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from tests._scoped_module_loader import load_module as load_scoped_module


_SNAPSHOTS: dict[tuple[str, str, str, tuple[tuple[str, str], ...]], tuple[tempfile.TemporaryDirectory[str], Path]] = {}
_RESOLVED_BYTES: dict[tuple[str, str, str], bytes] = {}


def run_cli(module: ModuleType, script: Path, *arguments: str) -> tuple[int, str, str]:
    """Exercise a historical runner without starting a fresh current-runtime process."""

    stdout, stderr = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    runner_name = f"_hbq_figurative_historical_runner_{hashlib.sha256(str(script).encode('utf-8')).hexdigest()[:16]}"
    sys.argv = [str(script), *arguments]
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runner = load_scoped_module(script, name=runner_name, aliases={"study": module})
                runner.main()
            except SystemExit as exc:
                return (exc.code if isinstance(exc.code, int) else 1, stdout.getvalue(), stderr.getvalue())
            return (0, stdout.getvalue(), stderr.getvalue())
    finally:
        sys.argv = old_argv
        sys.modules.pop(runner_name, None)


def install(module: ModuleType, *, source_commit: str) -> ModuleType:
    """Run one historical study against its declared source-commit runtime."""

    repository = Path(module.ROOT).resolve().parents[1]
    study_relative = Path(module.ROOT).resolve().relative_to(repository).as_posix()
    bindings = _runtime_bindings(module)
    key = (str(repository), source_commit, study_relative, tuple(sorted(bindings.items())))
    snapshot = _SNAPSHOTS.get(key)
    if snapshot is None:
        lease = tempfile.TemporaryDirectory(prefix="cwr-hbq-figurative-historical-runtime-")
        root = Path(lease.name)
        _archive_commit(repository, source_commit, root)
        _overlay_study_artifacts(Path(module.ROOT).resolve(), root / study_relative)
        for relative, digest in bindings.items():
            _restore_declared_bytes(root / relative, repository, relative, digest)
        (root / ".git").write_text(f"gitdir: {repository / '.git'}\n", encoding="utf-8")
        snapshot = (lease, root)
        _SNAPSHOTS[key] = snapshot

    lease, root = snapshot
    raw_hashes = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest() for relative in bindings}
    original_root = Path(module.ROOT).resolve()
    original_repository = getattr(module, "REPOSITORY", None)
    original_sha256_file = getattr(module, "sha256_file", None)
    _install_module_paths(module, root, study_relative, original_root, original_repository, bindings, raw_hashes, original_sha256_file, source_commit)
    for value in module.__dict__.values():
        if isinstance(value, ModuleType) and getattr(value, "REPOSITORY", None) == original_repository:
            nested_root = Path(getattr(value, "ROOT", original_root)).resolve()
            try:
                nested_relative = nested_root.relative_to(repository).as_posix()
            except ValueError:
                continue
            _install_module_paths(value, root, nested_relative, nested_root, original_repository, bindings, raw_hashes, getattr(value, "sha256_file", None), source_commit)
    module._historical_runtime_tempdir = lease
    module._historical_runtime_root = root
    module._historical_runtime_hashes = dict(bindings)
    module.assert_historical_runtime = lambda: _assert_runtime_intact(root, raw_hashes)
    return module


def assert_target_mutation_is_detected(module: ModuleType) -> None:
    """Narrow regression guard: a changed pinned target file fails closed."""

    relative = "registry/modules/penalty.purple_prose.yaml"
    path = Path(module._historical_runtime_root) / relative
    original = path.read_bytes()
    path.write_bytes(original + b"\n# mutation coverage only\n")
    try:
        try:
            _assert_runtime_intact(Path(module._historical_runtime_root), module._historical_runtime_hashes)
        except ValueError as exc:
            if "Pinned historical runtime bytes were mutated" not in str(exc):
                raise
        else:
            raise AssertionError("Pinned target mutation was not detected")
    finally:
        path.write_bytes(original)


def _install_module_paths(
    module: ModuleType,
    root: Path,
    study_relative: str,
    original_root: Path,
    original_repository: Any,
    bindings: Mapping[str, str],
    raw_hashes: Mapping[str, str],
    original_sha256_file: Any,
    source_commit: str,
) -> None:
    module.ROOT = root / study_relative
    if original_repository is not None:
        module.REPOSITORY = root
    if original_sha256_file is not None:
        def sha256_file(path: Path | str) -> str:
            candidate = Path(path).resolve()
            try:
                relative = candidate.relative_to(root).as_posix()
            except ValueError:
                return original_sha256_file(path)
            declared = bindings.get(relative)
            if declared is None:
                return original_sha256_file(path)
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != raw_hashes[relative]:
                raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
            return declared
        module.sha256_file = sha256_file
    original_git = getattr(module, "_git", None)
    if original_git is not None:
        def pinned_git(*args: str) -> str:
            if args == ("rev-parse", "HEAD"):
                return source_commit
            return original_git(*args)
        module._git = pinned_git
    if hasattr(module, "_require_exact_head"):
        module._require_exact_head = lambda: None
    if hasattr(module, "head"):
        module.head = lambda: None


def _runtime_bindings(module: ModuleType) -> dict[str, str]:
    contract = json.loads((Path(module.ROOT) / "study-contract.json").read_text(encoding="utf-8"))
    bindings = contract.get("bindings")
    if isinstance(bindings, Mapping) and isinstance(bindings.get("runtime"), Mapping):
        return _validate_bindings(bindings["runtime"])
    paths = getattr(module, "RUNTIME_PATHS", ())
    if not isinstance(paths, tuple) or not paths:
        base = getattr(module, "_base", None)
        paths = getattr(base, "RUNTIME_PATHS", ())
    if not isinstance(paths, tuple) or not paths:
        paths = (
            "prompts/judge/JUDGE_PREFIX.md",
            "prompts/judge/BINARY_EVALUATION_PROMPT.md",
            "schema/hbq_judge_response.schema.json",
            "registry/all_modules.json",
            "registry/question_index.jsonl",
            "registry/criterion_ownership.json",
            "registry/modules/penalty.purple_prose.yaml",
            "src/hbqrs/runner.py",
            "src/hbqrs/cli.py",
        )
    repository = Path(module.ROOT).resolve().parents[1]
    return {str(path): hashlib.sha256((repository / path).read_bytes()).hexdigest() for path in paths}


def _validate_bindings(bindings: Mapping[str, Any]) -> dict[str, str]:
    selected = {str(path): str(digest) for path, digest in bindings.items()}
    if not selected or any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in selected.values()):
        raise ValueError("Historical figurative runtime binding is malformed")
    return selected


def _archive_commit(repository: Path, source_commit: str, destination: Path) -> None:
    completed = subprocess.run(["git", "archive", "--format=tar", source_commit], cwd=repository, capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(f"Historical figurative source commit is unavailable: {source_commit}")
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not (destination / member.name).resolve().is_relative_to(destination.resolve()):
                raise ValueError("Historical figurative archive contains an unsafe path")
        archive.extractall(destination, filter="fully_trusted")


def _overlay_study_artifacts(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def _restore_declared_bytes(path: Path, repository: Path, relative: str, expected: str) -> None:
    cache_key = (str(repository), relative, expected)
    cached = _RESOLVED_BYTES.get(cache_key)
    if cached is not None:
        path.write_bytes(cached)
        return
    candidates = [path.read_bytes()]
    current = repository / relative
    if current.is_file():
        candidates.append(current.read_bytes())
    for commit in subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", relative],
        cwd=repository,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines():
        shown = subprocess.run(
            ["git", "show", f"{commit}:{relative}"], cwd=repository, capture_output=True, check=False
        )
        if not shown.returncode:
            candidates.append(shown.stdout)
    for payload in candidates:
        for candidate in _newline_candidates(
            payload,
            single_lf_outliers=relative == "registry/modules/penalty.purple_prose.yaml",
        ):
            if hashlib.sha256(candidate).hexdigest() == expected:
                path.write_bytes(candidate)
                _RESOLVED_BYTES[cache_key] = candidate
                return
    raise ValueError(f"Historical figurative runtime hash is unavailable: {path}")


def _newline_candidates(payload: bytes, *, single_lf_outliers: bool = False) -> tuple[bytes, ...]:
    lf = payload.replace(b"\r\n", b"\n")
    candidates = [payload, lf, lf.replace(b"\n", b"\r\n")]
    if not single_lf_outliers:
        return tuple(dict.fromkeys(candidates))
    lines = lf.split(b"\n")
    # The historical figurative source has one accidental LF among CRLF
    # separators.  Enumerate only that finite one-outlier family; hash matching
    # remains the authority, so no near match can be accepted.
    for outlier in range(len(lines) - 1):
        pieces: list[bytes] = []
        for index, line in enumerate(lines[:-1]):
            pieces.extend((line, b"\n" if index == outlier else b"\r\n"))
        pieces.append(lines[-1])
        candidates.append(b"".join(pieces))
    return tuple(dict.fromkeys(candidates))


def _assert_runtime_intact(root: Path, expected: Mapping[str, str]) -> None:
    for relative, digest in expected.items():
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
