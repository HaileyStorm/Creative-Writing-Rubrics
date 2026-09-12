"""Serialize only fixed-namespace WPB code loaders shared by concurrent freezes."""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from types import ModuleType
from typing import Any


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest() -> dict[str, Any]:
    path = Path(__file__).resolve()
    return {"format_version": 1, "kind": "wpb_frozen_import_serialization_source_manifest_v1",
            "successor": {"path": str(path), "sha256": _hash(path)}}


def _lock(state: dict[str, Any]) -> threading.RLock:
    value = state.setdefault("frozen_import_lock", threading.RLock())
    _require(hasattr(value, "__enter__") and hasattr(value, "__exit__"), "frozen import lock is invalid")
    return value


def _instrument(value: Any, lock: threading.RLock) -> Any:
    if isinstance(value, ModuleType):
        if getattr(value, "_wpb_frozen_import_serialized", False):
            return value
        for name in ("_load_exact", "_load_frozen_core", "_load_legacy", "_load_broker", "_grok_broker_module", "_load", "_frozen"):
            original = getattr(value, name, None)
            if callable(original):
                def guarded(*args: Any, __original: Any = original, **kwargs: Any) -> Any:
                    with lock:
                        return _instrument(__original(*args, **kwargs), lock)
                setattr(value, name, guarded)
        for name in ("_module", "_pinned_selection", "_pinned_v5", "_continuation", "_pinned_core", "_pinned_recovery"):
            original = getattr(value, name, None)
            if callable(original):
                def factory(*args: Any, __original: Any = original, **kwargs: Any) -> Any:
                    with lock:
                        return _instrument(__original(*args, **kwargs), lock)
                setattr(value, name, factory)
        value._wpb_frozen_import_serialized = True
    elif isinstance(value, tuple):
        return tuple(_instrument(item, lock) for item in value)
    return value


def install_on_legacy(legacy: ModuleType, shared_state: dict[str, Any]) -> ModuleType:
    """Instrument explicit WPB loader/factory boundaries with one reentrant lock."""
    lock = _lock(shared_state)
    original = getattr(legacy, "_load_exact", None)
    if callable(original) and not getattr(legacy, "_wpb_exact_loader_serialized", False):
        def load_exact(*args: Any, **kwargs: Any) -> Any:
            with lock:
                return _instrument(original(*args, **kwargs), lock)
        legacy._load_exact = load_exact
        legacy._wpb_exact_loader_serialized = True
    return _instrument(legacy, lock)
