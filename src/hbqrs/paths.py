"""Locate the HBQ-RS book files for both a git checkout and an installed wheel."""

from __future__ import annotations

import os
from pathlib import Path

REQUIRED = Path("registry") / "all_modules.json"


def book_root() -> Path:
    """Return the directory that contains ``registry/``, ``bundles/``, and ``schema/``."""

    env = os.environ.get("HBQRS_ROOT")
    if env:
        root = Path(env).expanduser().resolve()
        if (root / REQUIRED).is_file():
            return root
        raise FileNotFoundError(f"HBQRS_ROOT={env} does not contain {REQUIRED}")

    packaged = Path(__file__).resolve().parent / "book"
    if (packaged / REQUIRED).is_file():
        return packaged

    for parent in Path(__file__).resolve().parents:
        if (parent / REQUIRED).is_file():
            return parent

    raise FileNotFoundError(
        "Could not find the HBQ-RS book. Clone the repository, set HBQRS_ROOT, "
        "or install the package from git so registry files are included."
    )


def registry_path() -> Path:
    return book_root() / "registry" / "all_modules.json"


def bundles_path() -> Path:
    return book_root() / "bundles" / "all_bundles.json"


def schema_dir() -> Path:
    return book_root() / "schema"


def prompts_dir() -> Path:
    return book_root() / "prompts"


def examples_dir() -> Path:
    return book_root() / "examples"
