from __future__ import annotations

import json
from pathlib import Path

import pytest

from hbqrs import book_root, load_bundles, load_modules

ROOT = book_root()


@pytest.fixture(scope="session")
def modules():
    return load_modules(ROOT / "registry" / "all_modules.json")


@pytest.fixture(scope="session")
def bundles():
    return load_bundles(ROOT / "bundles" / "all_bundles.json")


@pytest.fixture(scope="session")
def module_by_id(modules):
    return {item["module_id"]: item for item in modules}


@pytest.fixture(scope="session")
def bundle_by_id(bundles):
    return {item["bundle_id"]: item for item in bundles}


@pytest.fixture(scope="session")
def manifest():
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
