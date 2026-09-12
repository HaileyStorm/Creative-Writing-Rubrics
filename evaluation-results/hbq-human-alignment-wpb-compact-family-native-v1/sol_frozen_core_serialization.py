"""Narrow synchronization for concurrent schema-recovery frozen-core loads."""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
V5 = HERE / "grok_selection_freeze_v5.py"
V5_SHA256 = "217885d7d8d291a55e7042811765e90fa343759c4bbacd813b67444067c6f37e"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _state_lock(shared_state: dict[str, Any]) -> threading.RLock:
    lock = shared_state.setdefault("frozen_core_lock", threading.RLock())
    _require(hasattr(lock, "__enter__") and hasattr(lock, "__exit__"), "frozen-core shared lock is invalid")
    return lock


def source_manifest() -> dict[str, Any]:
    return {"format_version": 1, "kind": "wpb_frozen_core_serialization_source_manifest_v1",
            "successor": {"path": str(Path(__file__).resolve()), "sha256": _sha256(Path(__file__).resolve())},
            "historical_v5": {"path": str(V5.resolve()), "sha256": V5_SHA256}}


def configure_v5_verifier(loaded_v5_module: ModuleType, shared_state: dict[str, Any]) -> ModuleType:
    """Configure each private schema helper with one shared loader lock."""
    _require(Path(loaded_v5_module.__file__).resolve() == V5.resolve() and _sha256(V5) == V5_SHA256,
             "historical v5 verifier differs")
    lock = _state_lock(shared_state)
    original_pinned_selection = loaded_v5_module._pinned_selection

    def pinned_selection() -> ModuleType:
        selection = original_pinned_selection()
        original_module = selection._module

        def load(path: Path, name: str) -> ModuleType:
            helper = original_module(path, name)
            if Path(path).resolve() == selection.SCHEMA_RECOVERY_HELPER.resolve():
                original_loader = helper._load_frozen_core

                def load_frozen_core() -> ModuleType:
                    with lock:
                        return original_loader()

                helper._load_frozen_core = load_frozen_core
            return helper

        selection._module = load
        return selection

    loaded_v5_module._pinned_selection = pinned_selection
    loaded_v5_module._wpb_frozen_core_serialization_manifest = source_manifest()
    return loaded_v5_module


def install_on_legacy(legacy: ModuleType, shared_state: dict[str, Any]) -> ModuleType:
    """Configure only pinned v5 verifier loads through the legacy exact loader."""
    original_load_exact = legacy._load_exact

    def load_exact(path: Path, expected: str, name: str) -> ModuleType:
        module = original_load_exact(path, expected, name)
        if Path(path).resolve() == V5.resolve():
            _require(expected == V5_SHA256, "historical v5 verifier pin differs")
            return configure_v5_verifier(module, shared_state)
        return module

    legacy._load_exact = load_exact
    return legacy
