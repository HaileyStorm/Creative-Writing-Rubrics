"""HBQ-RS public API with imports deferred until their export is requested."""

from __future__ import annotations

from importlib import import_module
from typing import Any


__version__ = "1.2.1"

_EXPORTS = {
    "HBQError": (".core", "HBQError"),
    "book_root": (".paths", "book_root"),
    "bundles_path": (".paths", "bundles_path"),
    "compile_bundle": (".core", "compile_bundle"),
    "compiled_questions": (".core", "compiled_questions"),
    "load_bundles": (".core", "load_bundles"),
    "load_modules": (".core", "load_modules"),
    "load_verdicts": (".core", "load_verdicts"),
    "make_weight_profile": (".weights", "make_weight_profile"),
    "materialize_weight_profile": (".weights", "materialize_weight_profile"),
    "registry_path": (".paths", "registry_path"),
    "resolve_bundle": (".core", "resolve_bundle"),
    "run_judge": (".runner_v2", "run_judge"),
    "run_longform_batch": (".batch", "run_longform_batch"),
    "run_longform_judge": (".longform_runner_v2", "run_longform_judge"),
    "render_html_report": (".html_report", "render_html_report"),
    "render_html_scorecard": (".html_report", "render_html_scorecard"),
    "render_workflow_configurator": (".html_config", "render_workflow_configurator"),
    "render_workflow_status": (".html_status", "render_workflow_status"),
    "render_weight_configurator": (".html_weights", "render_weight_configurator"),
    "segment_longform": (".longform", "segment_longform"),
    "score_bundle": (".scoring_v2", "score_bundle"),
    "summarize_workflow_progress": (".html_status", "summarize_workflow_progress"),
    "validate_batch_manifest": (".batch", "validate_batch_manifest"),
    "validate_registry": (".core", "validate_registry"),
    "walk_tree": (".core", "walk_tree"),
}

__all__ = ["__version__", *_EXPORTS]


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *__all__})
