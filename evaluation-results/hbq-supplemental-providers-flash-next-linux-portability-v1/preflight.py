#!/usr/bin/env python3
"""Provider-free Linux diagnostic for exact Flash-Next v1 adapter bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import stat
import sys
from types import ModuleType
from typing import Any


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]
CONTRACT_PATH = PACKAGE / "study-contract.json"
EVIDENCE_NAME = "exclusive-published-self-integrity-linux-diagnostic.json"
PREDECESSOR_PATHS = {
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/study-contract.json",
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/adapter.py",
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/runtime-policy.json",
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/adapter-assets.json",
    "evaluation-results/hbq-supplemental-providers-flash-next-v1/study.py",
    "tests/test_hbq_flash_next_linux_adapter_v1.py",
    "tests/test_hbq_supplemental_providers_flash_next_v1.py",
}
ACTION_SURFACE = "no network, provider, dispatch, model, or billing implementation or observed action"
CLASSIFICATION = "exclusive_published_self_integrity_linux_diagnostic"
NO_GO = "NO_GO_NATIVE_PORTABILITY_OR_PROMOTION"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def object_sha256(value: dict[str, Any]) -> str:
    return sha256(canonical(value))


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_reparse(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def assert_no_reparse(path: Path, label: str) -> Path:
    absolute = Path(os.path.abspath(path))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if _is_reparse(cursor):
            raise ValueError(f"{label} crosses a symlink or reparse point")
    return absolute


def _identity(path: Path) -> tuple[int, int, int]:
    metadata = os.stat(path, follow_symlinks=False)
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def safe_bytes(path: Path, label: str) -> bytes:
    absolute = assert_no_reparse(path, label)
    if not absolute.is_file():
        raise ValueError(f"{label} is not a regular file")
    before = os.stat(absolute, follow_symlinks=False)
    value = absolute.read_bytes()
    after = os.stat(absolute, follow_symlinks=False)
    assert_no_reparse(absolute, label)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"{label} changed while being read")
    return value


def _contract() -> dict[str, Any]:
    try:
        value = json.loads(safe_bytes(CONTRACT_PATH, "successor contract").decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Successor contract bytes are malformed") from error
    if not isinstance(value, dict):
        raise ValueError("Successor contract must be an object")
    unsigned = dict(value)
    digest = unsigned.pop("semantic_contract_sha256", None)
    required = {"format_version", "study_id", "status", "semantic_contract_sha256", "predecessor", "allowed_cli_commands", "execution_constraints", "evidence_classification", "interpretation_limits"}
    if set(value) != required or not _is_sha256(digest) or digest != object_sha256(unsigned):
        raise ValueError("Successor semantic contract digest drifted")
    if value["format_version"] != 1 or value["study_id"] != "hbq-supplemental-providers-flash-next-linux-portability-v1" or value["status"] != "provider_free_linux_diagnostic_no_go":
        raise ValueError("Successor identity drifted")
    if value["allowed_cli_commands"] != ["plan", "verify", "validate-evidence"]:
        raise ValueError("Successor CLI surface drifted")
    if value["execution_constraints"] != {"linux_only": True, "evidence_root": "new, caller-supplied, external, non-reparse directory", "action_surface": ACTION_SURFACE, "native_portability": NO_GO}:
        raise ValueError("Successor execution constraints drifted")
    if value["evidence_classification"] != CLASSIFICATION or not isinstance(value["interpretation_limits"], list) or len(value["interpretation_limits"]) != 4:
        raise ValueError("Successor interpretation limits drifted")
    return value


def _asset_path(raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path or "\\" in raw_path:
        raise ValueError("Predecessor asset path is malformed")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError("Predecessor asset path escapes the repository")
    candidate = ROOT.joinpath(*relative.parts)
    assert_no_reparse(ROOT, "repository root")
    assert_no_reparse(candidate, "predecessor asset")
    try:
        candidate.resolve().relative_to(ROOT.resolve())
    except ValueError as error:
        raise ValueError("Predecessor asset escapes the repository") from error
    return candidate


def _validate_predecessor_records(assets: Any) -> list[dict[str, Any]]:
    if not isinstance(assets, list) or len(assets) != len(PREDECESSOR_PATHS):
        raise ValueError("Predecessor asset bindings drifted")
    if not all(isinstance(record, dict) and set(record) == {"path", "bytes", "sha256"} for record in assets):
        raise ValueError("Predecessor asset record drifted")
    paths = [record["path"] for record in assets]
    if set(paths) != PREDECESSOR_PATHS or len(set(paths)) != len(paths):
        raise ValueError("Predecessor asset path set drifted")
    if any(not isinstance(record["bytes"], int) or record["bytes"] < 1 or not _is_sha256(record["sha256"]) for record in assets):
        raise ValueError("Predecessor asset record drifted")
    return assets


def _read_predecessor_assets() -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    predecessor = _contract().get("predecessor")
    if not isinstance(predecessor, dict) or set(predecessor) != {"study_id", "assets"} or predecessor["study_id"] != "hbq-supplemental-providers-flash-next-v1":
        raise ValueError("Predecessor identity drifted")
    records = _validate_predecessor_records(predecessor["assets"])
    contents: dict[str, bytes] = {}
    observed: list[dict[str, Any]] = []
    for record in records:
        content = safe_bytes(_asset_path(record["path"]), "predecessor asset")
        actual = {"path": record["path"], "bytes": len(content), "sha256": sha256(content)}
        if actual != record:
            raise ValueError(f"Predecessor asset binding drifted: {record['path']}")
        contents[record["path"]] = content
        observed.append(actual)
    return observed, contents


def predecessor_bindings() -> list[dict[str, Any]]:
    return _read_predecessor_assets()[0]


def successor_bindings() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in (Path(__file__).resolve(), CONTRACT_PATH.resolve()):
        content = safe_bytes(path, "successor source")
        records.append({"path": str(path), "bytes": len(content), "sha256": sha256(content)})
    return records


def _load_bound_adapter(adapter_bytes: bytes, adapter_record: dict[str, Any]) -> ModuleType:
    if sha256(adapter_bytes) != adapter_record["sha256"] or len(adapter_bytes) != adapter_record["bytes"]:
        raise ValueError("Bound adapter bytes drifted before execution")
    module = ModuleType("flash_next_linux_portability_bound_adapter")
    module.__file__ = str(_asset_path(adapter_record["path"]))
    exec(compile(adapter_bytes, module.__file__, "exec"), module.__dict__)
    return module


def plan() -> dict[str, Any]:
    contract = _contract()
    return {"study_id": contract["study_id"], "state": "NO_GO_PROVIDER_FREE_PORTABILITY_PLAN", "evidence_classification": CLASSIFICATION, "predecessor_assets": predecessor_bindings(), "action_surface": ACTION_SURFACE, "native_linux_execution": "not_attested"}


def _require_linux_before_mutation() -> None:
    if platform.system() != "Linux" or sys.platform != "linux" or os.name != "posix":
        raise ValueError("Linux diagnostic requires Linux and refuses mutation on this host")
    if any(not hasattr(os, name) for name in ("O_NOFOLLOW", "O_DIRECTORY")) or os.link not in os.supports_dir_fd or os.replace not in os.supports_dir_fd:
        raise ValueError("Linux diagnostic requires POSIX no-follow directory-relative publication semantics")


def _create_new_external_root(value: Path) -> tuple[Path, int, tuple[int, int, int]]:
    root = Path(os.path.abspath(value))
    if root.exists() or os.path.lexists(root):
        raise ValueError("Evidence root must be a new path and refuses resume or overwrite")
    parent = assert_no_reparse(root.parent, "evidence-root parent")
    if not parent.is_dir():
        raise ValueError("Evidence-root parent must be an existing directory")
    try:
        root.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Evidence root must be external to the repository")
    os.mkdir(root, 0o700)
    assert_no_reparse(root, "evidence root")
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        identity = _identity(root)
        opened = os.fstat(descriptor)
        if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode)):
            raise ValueError("Evidence root identity drifted during exclusive creation")
        return root, descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _assert_root_identity(root: Path, descriptor: int, expected: tuple[int, int, int]) -> None:
    assert_no_reparse(root, "evidence root")
    opened = os.fstat(descriptor)
    if _identity(root) != expected or (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode)) != expected:
        raise ValueError("Evidence root identity drifted")


def _filesystem_facts(path: Path) -> dict[str, int]:
    metadata = os.stat(path, follow_symlinks=False)
    volume = os.statvfs(path)
    return {"device": metadata.st_dev, "inode": metadata.st_ino, "mode": stat.S_IMODE(metadata.st_mode), "block_size": volume.f_bsize, "fragment_size": volume.f_frsize, "blocks": volume.f_blocks, "name_max": volume.f_namemax}


def _python_facts() -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    content = safe_bytes(executable, "Python executable")
    return {"declared_path": str(Path(sys.executable)), "resolved_path": str(executable), "sha256": sha256(content), "bytes": len(content), "version": sys.version, "implementation": platform.python_implementation()}


def _checkpoint(adapter: ModuleType, root: Path, descriptor: int, expected: tuple[int, int, int]) -> None:
    _assert_root_identity(root, descriptor, expected)
    adapter.assert_no_reparse(root, "evidence root")


def _run_adapter_primitives(adapter: ModuleType, root: Path, descriptor: int, expected: tuple[int, int, int]) -> dict[str, bool]:
    _checkpoint(adapter, root, descriptor, expected)
    exclusive = root / "primitive" / "exclusive.json"
    adapter._atomic_exclusive(exclusive, b"exclusive-v1\n")
    _checkpoint(adapter, root, descriptor, expected)
    try:
        adapter._atomic_exclusive(exclusive, b"must-not-replace\n")
    except FileExistsError:
        immutable_target_refusal = True
    else:
        raise ValueError("Exclusive publication unexpectedly replaced a target")
    _checkpoint(adapter, root, descriptor, expected)
    replacement = root / "primitive" / "replace.json"
    adapter._atomic_replace(replacement, b"first\n")
    adapter._atomic_replace(replacement, b"second\n")
    if safe_bytes(replacement, "replacement primitive target") != b"second\n":
        raise ValueError("Atomic replacement bytes drifted")
    _checkpoint(adapter, root, descriptor, expected)
    adversarial = root / "adversarial"
    target = adversarial / "target"
    target.mkdir(parents=True)
    alias = adversarial / "alias"
    os.symlink(target, alias, target_is_directory=True)
    try:
        adapter._atomic_exclusive(alias / "blocked.json", b"blocked\n")
    except ValueError:
        nested_symlink_refusal = True
    else:
        raise ValueError("Adapter accepted a nested symlink path")
    root_alias = adversarial / "root-alias"
    os.symlink(root, root_alias, target_is_directory=True)
    try:
        adapter._safe_root(root_alias)
    except ValueError:
        root_symlink_refusal = True
    else:
        raise ValueError("Adapter accepted a symlink root")
    _checkpoint(adapter, root, descriptor, expected)
    return {"exclusive_create": True, "atomic_replace": True, "directory_fsync_path_exercised": True, "immutable_target_refusal": immutable_target_refusal, "nested_symlink_refusal": nested_symlink_refusal, "root_symlink_refusal": root_symlink_refusal, "sampled_root_identity_stable": True}


def _expected_command(root: Path) -> list[list[str]]:
    return [[str(Path(sys.executable).resolve()), str(Path(__file__).resolve()), "verify", str(root)]]


def verify(evidence_root: Path) -> dict[str, Any]:
    _require_linux_before_mutation()
    root, descriptor, identity = _create_new_external_root(evidence_root)
    try:
        assets, contents = _read_predecessor_assets()
        adapter_path = "evaluation-results/hbq-supplemental-providers-flash-next-v1/adapter.py"
        adapter_record = next(record for record in assets if record["path"] == adapter_path)
        adapter = _load_bound_adapter(contents[adapter_path], adapter_record)
        checks = _run_adapter_primitives(adapter, root, descriptor, identity)
        _assert_root_identity(root, descriptor, identity)
        contract = _contract()
        unsigned = {"format_version": 1, "study_id": contract["study_id"], "state": NO_GO, "evidence_classification": CLASSIFICATION, "validation_scope": "schema_and_self_integrity_only_not_native_provenance", "interpretation": "exclusive-published self-integrity diagnostic; not native execution or provenance proof", "commands": _expected_command(root), "host": {"system": platform.system(), "release": platform.release(), "version": platform.version(), "machine": platform.machine(), "architecture": list(platform.architecture()), "python": _python_facts(), "filesystem": _filesystem_facts(root)}, "root_identity": {"device": identity[0], "inode": identity[1], "file_type": identity[2]}, "predecessor_assets": assets, "successor_assets": successor_bindings(), "checks": checks, "action_surface": ACTION_SURFACE}
        evidence = {**unsigned, "self_integrity_sha256": object_sha256(unsigned)}
        adapter._atomic_exclusive(root / EVIDENCE_NAME, canonical(evidence))
        _assert_root_identity(root, descriptor, identity)
    finally:
        os.close(descriptor)
    return validate_evidence(root)


def _validate_host(host: Any) -> None:
    if not isinstance(host, dict) or set(host) != {"system", "release", "version", "machine", "architecture", "python", "filesystem"} or host["system"] != "Linux" or not all(isinstance(host[key], str) and host[key] for key in ("release", "version", "machine")) or not isinstance(host["architecture"], list) or len(host["architecture"]) != 2 or not all(isinstance(item, str) and item for item in host["architecture"]):
        raise ValueError("Diagnostic host facts drifted")
    python_facts = host["python"]
    if not isinstance(python_facts, dict) or set(python_facts) != {"declared_path", "resolved_path", "sha256", "bytes", "version", "implementation"} or not all(isinstance(python_facts[key], str) and python_facts[key] for key in ("declared_path", "resolved_path", "version", "implementation")) or not _is_sha256(python_facts["sha256"]) or not isinstance(python_facts["bytes"], int) or python_facts["bytes"] < 1:
        raise ValueError("Diagnostic Python facts drifted")
    filesystem = host["filesystem"]
    if not isinstance(filesystem, dict) or set(filesystem) != {"device", "inode", "mode", "block_size", "fragment_size", "blocks", "name_max"} or any(not isinstance(value, int) or value < 0 for value in filesystem.values()) or any(filesystem[key] < 1 for key in ("block_size", "fragment_size", "blocks", "name_max")):
        raise ValueError("Diagnostic filesystem facts drifted")


def validate_evidence(evidence_root: Path) -> dict[str, Any]:
    root = assert_no_reparse(Path(os.path.abspath(evidence_root)), "evidence root")
    if not root.is_dir():
        raise ValueError("Evidence root is unavailable")
    try:
        evidence = json.loads(safe_bytes(root / EVIDENCE_NAME, "Linux diagnostic").decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Linux diagnostic is malformed") from error
    if not isinstance(evidence, dict):
        raise ValueError("Linux diagnostic must be an object")
    unsigned = dict(evidence)
    digest = unsigned.pop("self_integrity_sha256", None)
    required = {"format_version", "study_id", "state", "evidence_classification", "validation_scope", "interpretation", "commands", "host", "root_identity", "predecessor_assets", "successor_assets", "checks", "action_surface"}
    if set(unsigned) != required or not _is_sha256(digest) or digest != object_sha256(unsigned):
        raise ValueError("Linux diagnostic self-integrity drifted")
    if unsigned["format_version"] != 1 or unsigned["study_id"] != _contract()["study_id"] or unsigned["state"] != NO_GO or unsigned["evidence_classification"] != CLASSIFICATION or unsigned["validation_scope"] != "schema_and_self_integrity_only_not_native_provenance" or unsigned["interpretation"] != "exclusive-published self-integrity diagnostic; not native execution or provenance proof" or unsigned["action_surface"] != ACTION_SURFACE:
        raise ValueError("Linux diagnostic identity drifted")
    if unsigned["commands"] != _expected_command(root):
        raise ValueError("Linux diagnostic command record drifted")
    _validate_host(unsigned["host"])
    identity = unsigned["root_identity"]
    if not isinstance(identity, dict) or set(identity) != {"device", "inode", "file_type"} or any(not isinstance(identity[key], int) or identity[key] < 0 for key in identity):
        raise ValueError("Linux diagnostic root identity drifted")
    if unsigned["predecessor_assets"] != predecessor_bindings() or unsigned["successor_assets"] != successor_bindings():
        raise ValueError("Linux diagnostic source bindings drifted")
    expected_checks = {"exclusive_create", "atomic_replace", "directory_fsync_path_exercised", "immutable_target_refusal", "nested_symlink_refusal", "root_symlink_refusal", "sampled_root_identity_stable"}
    if not isinstance(unsigned["checks"], dict) or set(unsigned["checks"]) != expected_checks or not all(isinstance(value, bool) and value for value in unsigned["checks"].values()):
        raise ValueError("Linux diagnostic primitive checks drifted")
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "verify", "validate-evidence"))
    parser.add_argument("evidence_root", nargs="?", type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        if args.evidence_root is not None:
            parser.error("plan accepts no evidence root")
        result = plan()
    else:
        if args.evidence_root is None:
            parser.error(f"{args.command} requires an evidence root")
        result = verify(args.evidence_root) if args.command == "verify" else validate_evidence(args.evidence_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
