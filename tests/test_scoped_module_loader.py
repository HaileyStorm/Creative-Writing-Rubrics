from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

import pytest

from _scoped_module_loader import isolated_import_state, load_module


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


def test_isolated_import_state_restores_alias_and_ordered_path(tmp_path: Path) -> None:
    alias = "scoped_state_existing_alias"
    original = ModuleType(alias)
    original_path = list(sys.path)
    sys.modules[alias] = original
    try:
        with isolated_import_state(alias):
            assert alias not in sys.modules
            sys.modules[alias] = ModuleType(alias)
            sys.path.insert(0, str(tmp_path))
        assert sys.modules[alias] is original
        assert sys.path == original_path
    finally:
        sys.modules.pop(alias, None)
        sys.path[:] = original_path


def test_isolated_import_state_restores_after_exception(tmp_path: Path) -> None:
    alias = "scoped_state_exception_alias"
    original = ModuleType(alias)
    original_path = list(sys.path)
    sys.modules[alias] = original
    try:
        with pytest.raises(RuntimeError, match="expected isolated failure"):
            with isolated_import_state(alias):
                sys.modules[alias] = ModuleType(alias)
                sys.path.append(str(tmp_path))
                raise RuntimeError("expected isolated failure")
        assert sys.modules[alias] is original
        assert sys.path == original_path
    finally:
        sys.modules.pop(alias, None)
        sys.path[:] = original_path
