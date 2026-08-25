"""Test-only pinned-runtime bridge for settled S2 studies.

Historical S2 packages keep their on-disk contracts and result hashes. After
the live registry advances, their tests run against a temporary snapshot of
the declared predecessor runtime. The bridge never treats a declared digest
as proof: restored bytes must hash to it first.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import runpy
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping


_SNAPSHOTS: dict[tuple[str, str, tuple[tuple[str, str], ...], str], tuple[tempfile.TemporaryDirectory[str], Path]] = {}
_UNBOUND: dict[tuple[str, str, tuple[tuple[str, str], ...], str], str] = {}


class HistoricalRuntimeUnbound(ValueError):
    """A declared historical digest has no exact reachable byte source."""


@dataclass(frozen=True)
class CliResult:
    returncode: int
    stdout: str
    stderr: str


def install(module: ModuleType, *, source_commit: str) -> ModuleType:
    """Bind one loaded S2 study to immutable bytes from ``source_commit``."""

    expected = _runtime_bindings(module)
    repository = Path(module.REPOSITORY).resolve()
    package_name = Path(module.ROOT).name
    key = (str(repository), source_commit, tuple(sorted(expected.items())), package_name)
    if key in _UNBOUND:
        raise HistoricalRuntimeUnbound(_UNBOUND[key])
    snapshot = _SNAPSHOTS.get(key)
    if snapshot is None:
        lease = tempfile.TemporaryDirectory(prefix="cwr-hbq-s2-historical-runtime-")
        root = Path(lease.name)
        try:
            _archive_commit(repository, source_commit, root, _required_snapshot_paths(module))
            _overlay_immutable_artifacts(module, repository, root)
            for relative, digest in expected.items():
                _restore_declared_bytes(root / relative, repository, relative, digest)
            _restore_nested_runtime_bindings(root, repository, Path(module.ROOT) / "study-contract.json")
        except HistoricalRuntimeUnbound as exc:
            _UNBOUND[key] = str(exc)
            lease.cleanup()
            raise
        (root / ".git").write_text(f"gitdir: {repository / '.git'}\n", encoding="utf-8")
        snapshot = (lease, root)
        _SNAPSHOTS[key] = snapshot

    lease, root = snapshot
    _relocate_module_paths(module, repository, root)
    _install_runtime_hash_guard(module, root, expected)
    _install_pinned_head(module, source_commit)
    module._historical_runtime_tempdir = lease
    module._historical_runtime_root = root
    module._historical_runtime_hashes = dict(expected)
    module.assert_historical_runtime = lambda: _assert_runtime_intact(root, expected)
    return module


def run_cli(module: ModuleType, script: Path, *arguments: str) -> CliResult:
    """Exercise a historical command surface with its installed snapshot study."""

    stdout, stderr = io.StringIO(), io.StringIO()
    old_argv = sys.argv
    previous = sys.modules.get("study")
    sys.argv = [str(script), *arguments]
    sys.modules["study"] = module
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                code = exc.code
                returncode = code if isinstance(code, int) else 1
            else:
                returncode = 0
    finally:
        sys.argv = old_argv
        if previous is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous
    return CliResult(returncode, stdout.getvalue(), stderr.getvalue())


def _runtime_bindings(module: ModuleType) -> dict[str, str]:
    direct = getattr(module, "RUNTIME_BINDINGS", None)
    if isinstance(direct, Mapping):
        return _validate_bindings(direct)
    contract = json.loads((Path(module.ROOT) / "study-contract.json").read_text(encoding="utf-8"))
    bindings = contract.get("bindings")
    if not isinstance(bindings, Mapping):
        # Execution successors pin a complete predecessor commit rather than a
        # smaller runtime-file list. No digest is fabricated for that case.
        return {}
    return _contract_runtime_bindings(bindings)


def _contract_runtime_bindings(bindings: Mapping[str, Any]) -> dict[str, str]:
    runtime = bindings.get("runtime")
    if isinstance(runtime, Mapping):
        return _validate_bindings(runtime)
    aliases = {
        "source_question_index_sha256": "registry/question_index.jsonl",
        "question_index_sha256": "registry/question_index.jsonl",
        "criterion_ownership_sha256": "registry/criterion_ownership.json",
    }
    selected = {path: bindings[key] for key, path in aliases.items() if isinstance(bindings.get(key), str)}
    if not selected:
        raise ValueError("Historical S2 study does not declare registry bindings")
    return _validate_bindings(selected)


def _validate_bindings(bindings: Mapping[str, Any]) -> dict[str, str]:
    selected = {str(path): str(digest) for path, digest in bindings.items()}
    if not selected or any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in selected.values()):
        raise ValueError("Historical S2 runtime binding is malformed")
    return selected


def _required_snapshot_paths(module: ModuleType) -> tuple[str, ...]:
    contract = json.loads((Path(module.ROOT) / "study-contract.json").read_text(encoding="utf-8"))
    package_name = Path(module.ROOT).name
    packages: set[str] = {package_name.removesuffix("-execution-v1")} if package_name.endswith("-execution-v1") else set()
    predecessor = contract.get("predecessor")
    if isinstance(predecessor, Mapping):
        candidates = predecessor.values() if all(isinstance(value, Mapping) for value in predecessor.values()) else (predecessor,)
        for value in candidates:
            if isinstance(value, Mapping) and isinstance(value.get("study_id"), str):
                packages.add(value["study_id"])
    return ("bundles", "registry", "prompts", "schema", "src", *(f"evaluation-results/{name}" for name in sorted(packages)))


def _archive_commit(repository: Path, source_commit: str, destination: Path, paths: tuple[str, ...]) -> None:
    completed = subprocess.run(["git", "archive", "--format=tar", source_commit, *paths], cwd=repository, capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(f"Historical S2 source commit is unavailable: {source_commit}")
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("Historical S2 archive contains an unsafe path")
        archive.extractall(destination, filter="fully_trusted")


def _overlay_immutable_artifacts(module: ModuleType, repository: Path, destination: Path) -> None:
    """Copy only public package evidence needed by the loaded study."""

    source = Path(module.ROOT).resolve()
    target = destination / "evaluation-results" / source.name
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    contract = json.loads((source / "study-contract.json").read_text(encoding="utf-8"))
    portfolio = contract.get("portfolio_binding")
    paths = {"evaluation-results/hbq-nonpoetry-scope-sentinel-v1/public-synthetic-corpus.json"}
    if isinstance(portfolio, Mapping):
        paths.update(str(portfolio[key]) for key in ("manifest_path", "findings_path") if isinstance(portfolio.get(key), str))
    for relative in paths:
        candidate = repository / relative
        if candidate.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate, target)


def _restore_nested_runtime_bindings(root: Path, repository: Path, contract_path: Path) -> None:
    """Validate every declared predecessor runtime before a successor imports it."""

    initial = json.loads(contract_path.read_text(encoding="utf-8"))
    pending = list(_predecessor_study_ids(initial))
    package_name = contract_path.parent.name
    if package_name.endswith("-execution-v1"):
        pending.append(package_name.removesuffix("-execution-v1"))
    visited: set[str] = set()
    while pending:
        study_id = pending.pop()
        if study_id in visited:
            continue
        visited.add(study_id)
        predecessor_contract = root / "evaluation-results" / study_id / "study-contract.json"
        if not predecessor_contract.is_file():
            raise HistoricalRuntimeUnbound(f"Historical S2 predecessor package is unavailable: {study_id}")
        contract = json.loads(predecessor_contract.read_text(encoding="utf-8"))
        bindings = contract.get("bindings")
        if isinstance(bindings, Mapping):
            for relative, digest in _contract_runtime_bindings(bindings).items():
                _restore_declared_bytes(root / relative, repository, relative, digest)
        pending.extend(_predecessor_study_ids(contract))


def _predecessor_study_ids(contract: Mapping[str, Any]) -> tuple[str, ...]:
    predecessor = contract.get("predecessor")
    if not isinstance(predecessor, Mapping):
        return ()
    candidates = predecessor.values() if all(isinstance(value, Mapping) for value in predecessor.values()) else (predecessor,)
    return tuple(value["study_id"] for value in candidates if isinstance(value, Mapping) and isinstance(value.get("study_id"), str))


def _restore_declared_bytes(path: Path, repository: Path, relative: str, expected: str) -> None:
    initial = tuple(_initial_payloads(path, repository, relative))
    try:
        _normalize_declared_bytes(path, expected, candidate_payloads=initial)
        return
    except ValueError:
        pass
    frozen = tuple(_frozen_snapshot_payloads(repository, relative))
    try:
        _normalize_declared_bytes(path, expected, candidate_payloads=(*initial, *frozen))
        return
    except ValueError:
        pass
    for payload in _git_payloads(repository, relative):
        try:
            _normalize_declared_bytes(path, expected, candidate_payloads=(*initial, *frozen[:128], payload))
            return
        except ValueError:
            continue
    raise HistoricalRuntimeUnbound(f"Historical S2 runtime binding is unavailable: {path}")


def _initial_payloads(path: Path, repository: Path, relative: str) -> Iterable[bytes]:
    if path.is_file():
        yield path.read_bytes()
    current = repository / relative
    if current.is_file():
        yield current.read_bytes()


def _frozen_snapshot_payloads(repository: Path, relative: str) -> Iterable[bytes]:
    matches = 0
    for base in (repository / "evaluation-results", repository / "artifact-receipts"):
        if not base.is_dir():
            continue
        for candidate in base.rglob(Path(relative).name):
            if candidate.is_file():
                yield candidate.read_bytes()
                matches += 1
                if matches >= 128:
                    return


def _git_payloads(repository: Path, relative: str) -> Iterable[bytes]:
    history = subprocess.run(["git", "log", "--all", "--format=%H", "--", relative], cwd=repository, text=True, capture_output=True, check=True).stdout.splitlines()
    for commit in history[:256]:
        shown = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=repository, capture_output=True, check=False)
        if not shown.returncode:
            yield shown.stdout


def _normalize_declared_bytes(path: Path, expected: str, *, candidate_payloads: Iterable[bytes] = ()) -> None:
    """Restore exact bytes, including a recoverable mixed-EOL form, or fail."""

    payloads = [path.read_bytes(), *candidate_payloads]
    candidates: list[bytes] = []
    seen: set[bytes] = set()
    for payload in payloads[:512]:
        for candidate in _newline_candidates(payload):
            if candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    for base in tuple(candidates):
        canonical = _lf(base)
        for pattern in payloads[:128]:
            candidate = _apply_eol_pattern(canonical, pattern)
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                candidates.append(candidate)
    for candidate in candidates:
        if hashlib.sha256(candidate).hexdigest() == expected:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(candidate)
            return
    raise HistoricalRuntimeUnbound(f"Historical S2 runtime binding is unavailable: {path}")


def _newline_candidates(payload: bytes) -> tuple[bytes, bytes, bytes]:
    lf = _lf(payload)
    return payload, lf, lf.replace(b"\n", b"\r\n")


def _lf(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n")


def _apply_eol_pattern(canonical: bytes, pattern: bytes) -> bytes | None:
    if _lf(pattern) != canonical:
        return None
    parts = canonical.split(b"\n")
    result = bytearray(parts[0])
    offset = len(parts[0])
    for part in parts[1:]:
        if pattern[offset:offset + 2] == b"\r\n":
            result.extend(b"\r\n")
            offset += 2
        elif pattern[offset:offset + 1] == b"\n":
            result.extend(b"\n")
            offset += 1
        else:
            return None
        result.extend(part)
        offset += len(part)
    return bytes(result) if offset == len(pattern) else None


def _relocate_module_paths(module: ModuleType, repository: Path, root: Path) -> None:
    for name, value in tuple(module.__dict__.items()):
        if not isinstance(value, Path):
            continue
        try:
            relative = value.resolve().relative_to(repository)
        except ValueError:
            continue
        module.__dict__[name] = root / relative
    module.REPOSITORY = root


def _install_runtime_hash_guard(module: ModuleType, root: Path, expected: Mapping[str, str]) -> None:
    if not expected or not hasattr(module, "sha256_file"):
        return
    original_sha256_file = module.sha256_file

    def sha256_file(path: Path | str) -> str:
        candidate = Path(path).resolve()
        try:
            relative = candidate.relative_to(root).as_posix()
        except ValueError:
            return original_sha256_file(path)
        declared = expected.get(relative)
        if declared is None:
            return original_sha256_file(path)
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != declared:
            raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
        return actual

    module.sha256_file = sha256_file


def _install_pinned_head(module: ModuleType, source_commit: str) -> None:
    original_git = getattr(module, "_git", None)
    if original_git is not None:
        def pinned_git(*args: str) -> str:
            if args == ("rev-parse", "HEAD"):
                return source_commit
            return original_git(*args)
        module._git = pinned_git
    for name in ("current_head", "_current_head"):
        if hasattr(module, name):
            module.__dict__[name] = lambda: source_commit


def _assert_runtime_intact(root: Path, expected: Mapping[str, str]) -> None:
    for relative, digest in expected.items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Pinned historical runtime bytes were mutated: {relative}")
