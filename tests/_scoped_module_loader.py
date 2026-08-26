"""Load standalone study scripts without leaking their generic import aliases."""
from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Iterator


_MISSING = object()


@contextmanager
def isolated_import_state(*aliases: str) -> Iterator[None]:
    """Remove generic aliases for an operation, then restore imports exactly."""
    if len(set(aliases)) != len(aliases):
        raise ValueError("Import-state aliases must be unique")
    previous_modules = {alias: sys.modules.get(alias, _MISSING) for alias in aliases}
    previous_path = list(sys.path)
    for alias in aliases:
        sys.modules.pop(alias, None)
    try:
        yield
    finally:
        sys.path[:] = previous_path
        for alias, prior in previous_modules.items():
            if prior is _MISSING:
                sys.modules.pop(alias, None)
            else:
                sys.modules[alias] = prior


def load_module(path: Path, *, name: str, aliases: Mapping[str, ModuleType] | None = None) -> ModuleType:
    """Execute ``path`` while exposing only the requested local import aliases."""
    aliases = dict(aliases or {})
    if name in aliases:
        raise ValueError(f"Module name {name!r} cannot also be a temporary alias")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    previous = {alias: sys.modules.get(alias, _MISSING) for alias in aliases}
    previous_module = sys.modules.get(name, _MISSING)
    sys.modules[name] = module
    sys.modules.update(aliases)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous_module is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous_module
        raise
    finally:
        for alias, prior in previous.items():
            if prior is _MISSING:
                sys.modules.pop(alias, None)
            else:
                sys.modules[alias] = prior
    return module
