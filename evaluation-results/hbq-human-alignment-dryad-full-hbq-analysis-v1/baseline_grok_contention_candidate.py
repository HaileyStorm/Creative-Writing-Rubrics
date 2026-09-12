"""Source-bound, code-only loader for the sealed Grok contention candidate."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import stat
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

CANDIDATE_MANIFEST_SHA256 = "c97c18af74ebbaebb1919760274eae5bacf9877373c0d7a8e6a1bae25de104f0"
PARENT_CANDIDATE_MANIFEST_SHA256 = "f366f37dcb5d22cddc23e38a3e89f66d4a2b49cdcbceb97363601c897739e896"
_LOAD_LOCK = threading.RLock()
_CODE_CACHE: dict[tuple[str, str], ModuleType] = {}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _need(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _plain(path: Path | str, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    for candidate in (absolute, *absolute.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        _need(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "candidate path contains a link or reparse point")
    if directory is True:
        _need(absolute.is_dir(), "candidate root differs")
    if directory is False:
        _need(absolute.is_file(), "candidate file differs")
    return absolute


def _read(path: Path) -> bytes:
    checked = _plain(path, directory=False)
    raw = checked.read_bytes()
    _need(checked.read_bytes() == raw, "candidate file changed while reading")
    return raw


def _json(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            _need(isinstance(key, str) and key not in result, "candidate manifest malformed")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("candidate manifest malformed") from error
    _need(isinstance(value, dict), "candidate manifest object")
    return value


def _manifest(root: Path, expected: str) -> tuple[Path, dict[str, Any], dict[str, str]]:
    root = _plain(root, directory=True)
    manifest_path = _plain(root / "candidate-manifest.json", directory=False)
    raw = _read(manifest_path)
    manifest = _json(raw)
    _need(_sha(raw) == expected == CANDIDATE_MANIFEST_SHA256, "candidate manifest differs")
    _need(manifest.get("schema_version") == 8 and manifest.get("kind") == "grok_host_gate_contention_successor_candidate" and manifest.get("parent_candidate_manifest_sha256") == PARENT_CANDIDATE_MANIFEST_SHA256, "candidate manifest differs")
    files = manifest.get("files")
    _need(isinstance(files, list) and manifest.get("explicit_exclusion") == ["candidate-manifest.json"], "candidate file inventory differs")
    hashes = {item.get("path"): item.get("sha256") for item in files if isinstance(item, Mapping)}
    _need(len(hashes) == len(files) == 18 and all(isinstance(path, str) and isinstance(digest, str) for path, digest in hashes.items()), "candidate file inventory differs")
    actual: dict[str, str] = {}
    for path in root.rglob("*"):
        checked = _plain(path)
        if checked.is_file():
            actual[checked.relative_to(root).as_posix()] = _sha(_read(checked))
    _need(actual == {"candidate-manifest.json": _sha(raw), **hashes}, "candidate root drift")
    return root, manifest, dict(hashes)


def load_candidate(root: Path, expected_manifest_sha256: str) -> tuple[ModuleType, dict[str, Any]]:
    """Load the verified broker module without constructing a broker."""
    with _LOAD_LOCK:
        root, manifest, hashes = _manifest(root, expected_manifest_sha256)
        broker_path = _plain(root / "model_work_queue" / "broker.py", directory=False)
        _need(hashes.get("model_work_queue/broker.py") == _sha(_read(broker_path)), "candidate broker differs")
        key = (str(root), expected_manifest_sha256)
        cached = _CODE_CACHE.get(key)
        if cached is not None:
            _need(_plain(str(getattr(cached, "__file__", "")), directory=False) == broker_path and hasattr(cached, "Broker"), "candidate cached code differs")
            return cached, manifest
        package_path = _plain(root / "model_work_queue" / "__init__.py", directory=False)
        package_name = "_grok_contention_candidate_" + _sha((str(root) + expected_manifest_sha256).encode())[:24]
        broker_name = package_name + ".broker"
        old_bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        package_module: ModuleType | None = None
        try:
            existing = sys.modules.get(broker_name)
            if isinstance(existing, ModuleType):
                module = existing
            else:
                _need(existing is None, "candidate broker load is incomplete")
                spec = importlib.util.spec_from_file_location(package_name, package_path, submodule_search_locations=[str(package_path.parent)])
                _need(spec is not None and spec.loader is not None, "candidate package load")
                package_module = importlib.util.module_from_spec(spec)
                sys.modules[package_name] = package_module
                spec.loader.exec_module(package_module)
                module = importlib.import_module(broker_name)
            _need(_plain(str(getattr(module, "__file__", "")), directory=False) == broker_path and hasattr(module, "Broker") and _sha(_read(broker_path)) == hashes["model_work_queue/broker.py"], "candidate broker changed")
            _CODE_CACHE[key] = module
        except BaseException:
            if package_module is not None and sys.modules.get(package_name) is package_module:
                sys.modules.pop(package_name, None)
                sys.modules.pop(broker_name, None)
            raise
        finally:
            sys.dont_write_bytecode = old_bytecode
    return module, manifest


def verify_candidate(root: Path, expected_manifest_sha256: str) -> dict[str, Any]:
    """Verify the sealed candidate closure and return its inert identity."""
    module, manifest = load_candidate(root, expected_manifest_sha256)
    return {"manifest_sha256": expected_manifest_sha256, "broker_path": str(Path(module.__file__).resolve()), "provider_calls_made": 0, "staging_record": {"provider_invocations": manifest["provider_invocations"], "activation_performed": manifest["activation_performed"], "installation_performed": manifest["installation_performed"]}}
