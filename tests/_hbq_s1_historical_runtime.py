"""Test-only historical runtime bridge for S1 provenance packages.

The public studies are immutable records. Their tests must not silently read a
later dirty checkout after the repetition leaf changes. This bridge creates a
temporary archive-backed checkout, restores the bytes each package declared,
and rewrites package-local repository paths only in the imported test module.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any


class LegacyHistoricalRuntimeUnbound(RuntimeError):
    """A legacy record lacks one reproducible historical runtime tree."""


_SNAPSHOTS: dict[
    tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]],
    tuple[tempfile.TemporaryDirectory[str], Path],
] = {}

# These are the only lazy lineage edges that historical S1 packages are
# allowed to expose.  Keep this list explicit: a historical runtime should not
# recursively inspect arbitrary module attributes or follow unrelated imports.
_LAZY_LINEAGE_RESOLVERS = ("_v1", "_v2", "_v3", "_adapter", "_v2_execution", "_base_v2")


def install_historical_runtime(module: ModuleType, *, source_commit: str | None = None) -> ModuleType:
    """Bind ``module`` to its declared historical runtime without mutating evidence."""

    repository = Path(module.REPOSITORY).resolve()
    bindings = _declared_bindings(module)
    commit = source_commit or _declared_commit(module)
    if not commit:
        commit = _unique_commit_for_bindings(repository, bindings)
    if not commit:
        raise LegacyHistoricalRuntimeUnbound(
            "legacy historical runtime is unbound: declared bytes do not identify one reachable source commit"
        )
    overlays = _required_overlay_identity(repository, Path(module.ROOT).name)
    key = (str(repository), commit, tuple(sorted(bindings.items())), overlays)
    snapshot = _SNAPSHOTS.get(key)
    if snapshot is None:
        lease = tempfile.TemporaryDirectory(prefix="cwr-hbq-s1-historical-runtime-")
        root = Path(lease.name)
        _archive_commit(repository, commit, root)
        _overlay_s1_packages(repository, root, tuple(name for name, _digest in overlays))
        for relative, digest in bindings.items():
            _restore_declared_bytes(root / relative, repository, relative, digest)
        (root / ".git").write_text(f"gitdir: {repository / '.git'}\n", encoding="utf-8")
        snapshot = (lease, root)
        _SNAPSHOTS[key] = snapshot

    lease, root = snapshot
    _validate_declared_lineage(module, repository, commit)
    _relocate_module(module, root, repository, bindings, commit)
    _pin_module_head(module, commit, repository)
    _pin_lazy_lineage(module, commit, repository)
    _preserve_original_private_boundary(module, repository)
    _pin_subprocess_runtime(module, root)
    module._historical_runtime_tempdir = lease
    module._historical_runtime_root = root
    module._historical_runtime_hashes = dict(bindings)
    module.assert_historical_runtime = lambda: _assert_runtime_intact(root, bindings)
    return module


def _declared_bindings(module: ModuleType) -> dict[str, str]:
    root = Path(module.ROOT)
    contract_path = root / "study-contract.json"
    if contract_path.is_file():
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        bindings = contract.get("bindings")
        if isinstance(bindings, Mapping):
            for key in ("runtime", "active_runtime"):
                runtime = bindings.get(key)
                if isinstance(runtime, Mapping):
                    return _validate_bindings(runtime)
            if all(isinstance(value, str) for value in bindings.values()):
                return _validate_bindings(bindings)
    for name in ("RUNTIME_BINDINGS", "RUNTIME_SHA256"):
        value = getattr(module, name, None)
        if isinstance(value, Mapping):
            return _validate_bindings(value)
    for name in _LAZY_LINEAGE_RESOLVERS:
        resolver = getattr(module, name, None)
        if not callable(resolver):
            continue
        try:
            nested = resolver()
        except (OSError, ValueError):
            continue
        if isinstance(nested, ModuleType):
            try:
                return _declared_bindings(nested)
            except LegacyHistoricalRuntimeUnbound:
                continue
    raise LegacyHistoricalRuntimeUnbound(
        "legacy historical runtime is unbound: no declared runtime hashes are available"
    )


def _declared_commit(module: ModuleType) -> str | None:
    for name in ("SOURCE_COMMIT", "SOURCE_HEAD"):
        value = getattr(module, name, None)
        if isinstance(value, str) and len(value) == 40:
            return value
    contract_path = Path(module.ROOT) / "study-contract.json"
    if contract_path.is_file():
        source = json.loads(contract_path.read_text(encoding="utf-8")).get("source_checkout")
        if isinstance(source, Mapping) and isinstance(source.get("commit"), str):
            return source["commit"]
    return None


def _validate_bindings(bindings: Mapping[str, Any]) -> dict[str, str]:
    selected = {str(path): str(digest) for path, digest in bindings.items()}
    if not selected or any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in selected.values()):
        raise LegacyHistoricalRuntimeUnbound("legacy historical runtime is unbound: runtime hashes are malformed")
    return selected


def _unique_commit_for_bindings(repository: Path, bindings: Mapping[str, str]) -> str | None:
    candidates: set[str] | None = None
    for relative, expected in bindings.items():
        history = subprocess.run(
            ["git", "log", "--all", "--format=%H", "--", relative], cwd=repository, text=True, capture_output=True, check=True
        ).stdout.splitlines()
        matches = {
            commit for commit in history
            if any(hashlib.sha256(payload).hexdigest() == expected for payload in _git_newline_candidates(repository, commit, relative))
        }
        candidates = matches if candidates is None else candidates & matches
        if not candidates:
            return None
    if candidates and len(candidates) == 1:
        return next(iter(candidates))
    return None


def _git_newline_candidates(repository: Path, commit: str, relative: str) -> tuple[bytes, ...]:
    shown = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=repository, capture_output=True, check=False)
    return _newline_candidates(shown.stdout) if not shown.returncode else ()


def _git_text(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=repository, text=True, encoding="utf-8", capture_output=True, check=False
    )
    if completed.returncode:
        raise LegacyHistoricalRuntimeUnbound(completed.stderr.strip() or "historical Git lookup failed")
    return completed.stdout.strip()


def _validate_declared_lineage(module: ModuleType, repository: Path, commit: str) -> None:
    for name in ("SOURCE_COMMIT", "SOURCE_HEAD"):
        declared = getattr(module, name, None)
        if declared is None:
            continue
        if not isinstance(declared, str) or declared != commit:
            raise LegacyHistoricalRuntimeUnbound(
                f"historical declared {name} does not match pinned commit"
            )
    declared_tree = getattr(module, "SOURCE_TREE", None)
    if declared_tree is None:
        return
    if not isinstance(declared_tree, str) or len(declared_tree) != 40:
        raise LegacyHistoricalRuntimeUnbound("historical declared SOURCE_TREE is malformed")
    actual_tree = _git_text(repository, "rev-parse", f"{commit}^{{tree}}")
    if actual_tree != declared_tree:
        raise LegacyHistoricalRuntimeUnbound("historical declared SOURCE_TREE does not match pinned commit")


def _archive_commit(repository: Path, commit: str, destination: Path) -> None:
    completed = subprocess.run(["git", "archive", "--format=tar", commit], cwd=repository, capture_output=True, check=False)
    if completed.returncode:
        raise LegacyHistoricalRuntimeUnbound("legacy historical runtime is unbound: declared source commit is unavailable")
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not (destination / member.name).resolve().is_relative_to(destination.resolve()):
                raise ValueError("Historical archive contains an unsafe path")
        archive.extractall(destination, filter="fully_trusted")


def _required_overlay_identity(repository: Path, package_name: str) -> tuple[tuple[str, str], ...]:
    names = {package_name}
    clean = "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1"
    family = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v"
    if package_name.startswith(family):
        version = int(package_name.removeprefix(family))
        names.add(clean)
        names.update(f"{family}{prior}" for prior in range(1, version))
        if version >= 4:
            names.add("hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2-public-result-v1")
    if package_name == "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2":
        names.add("hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1")
    if "four-state-disjoint" in package_name:
        names.add("hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10")
    if package_name.endswith("-v2-execution-v2"):
        names.update(
            {
                "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2",
                "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1",
            }
        )
    if package_name.endswith("-v2-execution-v3"):
        names.update(
            {
                "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2-execution-v2",
                "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2",
                "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1",
            }
        )
    identity: list[tuple[str, str]] = []
    for name in sorted(names):
        package = repository / "evaluation-results" / name
        if not package.is_dir():
            raise LegacyHistoricalRuntimeUnbound(f"legacy historical runtime is unbound: required package is unavailable: {name}")
        digest = hashlib.sha256()
        for path in sorted(path for path in package.rglob("*") if path.is_file() and "__pycache__" not in path.parts):
            digest.update(path.relative_to(package).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
        identity.append((name, digest.hexdigest()))
    return tuple(identity)


def _overlay_s1_packages(repository: Path, root: Path, names: tuple[str, ...]) -> None:
    source = repository / "evaluation-results"
    target = root / "evaluation-results"
    target.mkdir(parents=True, exist_ok=True)
    for name in names:
        package = source / name
        if package.is_dir():
            shutil.copytree(package, target / package.name, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))


def _restore_declared_bytes(path: Path, repository: Path, relative: str, expected: str) -> None:
    candidates: list[bytes] = [path.read_bytes()] if path.is_file() else []
    current = repository / relative
    if current.is_file():
        candidates.append(current.read_bytes())
    history = subprocess.run(
        ["git", "log", "--all", "--format=%H", "--", relative], cwd=repository, text=True, capture_output=True, check=True
    ).stdout.splitlines()
    for commit in history:
        candidates.extend(_git_newline_candidates(repository, commit, relative))
    for payload in candidates:
        for candidate in _newline_candidates(payload):
            if hashlib.sha256(candidate).hexdigest() == expected:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(candidate)
                return
    raise LegacyHistoricalRuntimeUnbound(
        f"legacy historical runtime is unbound: declared bytes are unavailable for {relative}"
    )


def _newline_candidates(payload: bytes) -> tuple[bytes, bytes, bytes]:
    lf = payload.replace(b"\r\n", b"\n")
    return payload, lf, lf.replace(b"\n", b"\r\n")


def _relocate_module(module: ModuleType, root: Path, repository: Path, bindings: Mapping[str, str], commit: str) -> None:
    for name, value in tuple(module.__dict__.items()):
        if isinstance(value, Path):
            try:
                relative = value.resolve().relative_to(repository)
            except ValueError:
                continue
            module.__dict__[name] = root / relative
    module.REPOSITORY = root
    original_sha256_file = getattr(module, "sha256_file", None)
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
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != declared:
                raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
            return declared
        module.sha256_file = sha256_file
    original_git = getattr(module, "_git", None)
    if original_git is not None:
        def pinned_git(*args: str) -> str:
            if args == ("rev-parse", "HEAD"):
                return commit
            return original_git(*args)
        module._git = pinned_git


def _pin_lazy_lineage(module: ModuleType, commit: str, repository: Path) -> None:
    """Pin only the bounded lazy lineage edges used by the S1 successors."""

    for name in _LAZY_LINEAGE_RESOLVERS:
        resolver = getattr(module, name, None)
        if not callable(resolver) or getattr(resolver, "_s1_historical_lineage_wrapper", False):
            continue

        @wraps(resolver)
        def load_nested(resolver=resolver, resolver_name=name):
            nested = resolver()
            if not isinstance(nested, ModuleType):
                raise LegacyHistoricalRuntimeUnbound(
                    f"historical lineage resolver {resolver_name} did not return a module"
                )
            declared = _declared_commit(nested)
            if declared is not None and declared != commit:
                raise LegacyHistoricalRuntimeUnbound(
                    f"historical nested {resolver_name} commit mismatch: {declared} != {commit}"
                )
            _pin_module_head(nested, commit, repository)
            _pin_lazy_lineage(nested, commit, repository)
            return nested

        load_nested._s1_historical_lineage_wrapper = True
        # Preserve cache-management hooks expected by the archived studies.
        for hook in ("cache_clear", "cache_info", "cache_parameters"):
            value = getattr(resolver, hook, None)
            if value is not None:
                setattr(load_nested, hook, value)
        module.__dict__[name] = load_nested


def _pin_module_head(module: ModuleType, commit: str, repository: Path) -> None:
    """Pin only recognized historical head lookups while delegating other Git calls."""

    _validate_declared_lineage(module, repository, commit)
    pinned_commit = getattr(module, "_s1_historical_head_commit", None)
    if pinned_commit is not None and pinned_commit != commit:
        raise LegacyHistoricalRuntimeUnbound(
            f"historical nested module commit mismatch: {pinned_commit} != {commit}"
        )
    original_git = getattr(module, "_git", None)
    if pinned_commit is None and callable(original_git) and not getattr(original_git, "_s1_historical_head_wrapper", False):
        @wraps(original_git)
        def pinned_git(*args: str) -> str:
            if args == ("rev-parse", "HEAD"):
                return commit
            return original_git(*args)

        pinned_git._s1_historical_head_wrapper = True
        module._git = pinned_git
        module._s1_historical_head_commit = commit

    for name in ("current_head", "_head"):
        resolver = getattr(module, name, None)
        if not callable(resolver) or getattr(resolver, "_s1_historical_head_lookup_wrapper", False):
            continue
        try:
            observed = resolver()
        except Exception as error:
            raise LegacyHistoricalRuntimeUnbound(f"historical {name} lookup is unavailable") from error
        if name == "current_head":
            if not isinstance(observed, str):
                raise LegacyHistoricalRuntimeUnbound("historical current_head shape is unsupported")
            result: Any = commit
        elif isinstance(observed, str):
            result = commit
        elif isinstance(observed, tuple) and len(observed) == 2 and all(isinstance(value, str) for value in observed):
            declared_tree = getattr(module, "SOURCE_TREE", None)
            if not isinstance(declared_tree, str):
                raise LegacyHistoricalRuntimeUnbound("historical _head tuple lacks declared SOURCE_TREE")
            result = (commit, declared_tree)
        else:
            raise LegacyHistoricalRuntimeUnbound("historical _head shape is unsupported")

        @wraps(resolver)
        def pinned_lookup(*_args: Any, _result: Any = result, **_kwargs: Any) -> Any:
            return _result

        pinned_lookup._s1_historical_head_lookup_wrapper = True
        module.__dict__[name] = pinned_lookup


def _preserve_original_private_boundary(module: ModuleType, repository: Path) -> None:
    original = getattr(module, "set_private_root", None)
    if not callable(original):
        return

    def set_private_root(value: str | Path) -> Any:
        candidate = Path(value).resolve()
        try:
            candidate.relative_to(repository)
        except ValueError:
            pass
        else:
            raise ValueError("private_root must be outside the CWR checkout")
        try:
            repository.relative_to(candidate)
        except ValueError:
            pass
        else:
            raise ValueError("private_root must be disjoint from the CWR checkout")
        return original(value)

    module.set_private_root = set_private_root
    module._historical_original_repository = repository


def _pin_subprocess_runtime(module: ModuleType, root: Path) -> None:
    original = getattr(module, "dry_run", None)
    if not callable(original):
        return

    def dry_run(*args: Any, **kwargs: Any) -> Any:
        previous = os.environ.get("PYTHONPATH")
        historical = str(root / "src")
        os.environ["PYTHONPATH"] = historical if not previous else historical + os.pathsep + previous
        try:
            return original(*args, **kwargs)
        finally:
            if previous is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = previous

    module.dry_run = dry_run


def _assert_runtime_intact(root: Path, bindings: Mapping[str, str]) -> None:
    for relative, digest in bindings.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
