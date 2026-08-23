from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from _scoped_module_loader import load_module


def _script(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "script.py"
    path.write_text(source, encoding="utf-8")
    return path


def test_successful_load_removes_new_temporary_alias(tmp_path: Path) -> None:
    alias, name = "scoped_loader_success_alias", "scoped_loader_success_module"
    dependency = ModuleType(alias)
    dependency.value = "bound"
    loaded = load_module(_script(tmp_path, "import scoped_loader_success_alias\nvalue = scoped_loader_success_alias.value\n"), name=name, aliases={alias: dependency})
    try:
        assert loaded.value == "bound"
        assert sys.modules[name] is loaded
        assert alias not in sys.modules
    finally:
        sys.modules.pop(name, None)


def test_failed_load_removes_new_alias_and_module(tmp_path: Path) -> None:
    alias, name = "scoped_loader_failure_alias", "scoped_loader_failure_module"
    dependency = ModuleType(alias)
    with pytest.raises(RuntimeError, match="expected failure"):
        load_module(_script(tmp_path, "raise RuntimeError('expected failure')\n"), name=name, aliases={alias: dependency})
    assert alias not in sys.modules
    assert name not in sys.modules


def test_successful_load_restores_preexisting_alias(tmp_path: Path) -> None:
    alias, name = "scoped_loader_existing_alias", "scoped_loader_existing_module"
    original = ModuleType(alias)
    original.value = "original"
    dependency = ModuleType(alias)
    dependency.value = "temporary"
    sys.modules[alias] = original
    try:
        loaded = load_module(_script(tmp_path, "import scoped_loader_existing_alias\nvalue = scoped_loader_existing_alias.value\n"), name=name, aliases={alias: dependency})
        assert loaded.value == "temporary"
        assert sys.modules[alias] is original
    finally:
        sys.modules.pop(name, None)
        sys.modules.pop(alias, None)


def test_rejects_module_name_alias_collision(tmp_path: Path) -> None:
    name = "scoped_loader_collision_module"
    original = ModuleType(name)
    sys.modules[name] = original
    try:
        with pytest.raises(ValueError, match="cannot also be a temporary alias"):
            load_module(_script(tmp_path, "value = 1\n"), name=name, aliases={name: ModuleType(name)})
        assert sys.modules[name] is original
    finally:
        sys.modules.pop(name, None)
