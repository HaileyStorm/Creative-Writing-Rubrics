"""HBQ-RS creative-writing rubrics: compile bundles, score verdicts, export leaves."""

from .core import (
    HBQError,
    compile_bundle,
    compiled_questions,
    load_bundles,
    load_modules,
    load_verdicts,
    resolve_bundle,
    score_bundle,
    validate_registry,
    walk_tree,
)
from .paths import book_root, bundles_path, registry_path
from .runner import run_judge

__version__ = "1.0.0"

__all__ = [
    "HBQError",
    "__version__",
    "book_root",
    "bundles_path",
    "compile_bundle",
    "compiled_questions",
    "load_bundles",
    "load_modules",
    "load_verdicts",
    "registry_path",
    "resolve_bundle",
    "run_judge",
    "score_bundle",
    "validate_registry",
    "walk_tree",
]
