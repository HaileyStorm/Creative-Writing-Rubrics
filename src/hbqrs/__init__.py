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
from .longform import segment_longform
from .longform_runner import run_longform_judge
from .html_config import render_workflow_configurator
from .html_report import render_html_report, render_html_scorecard
from .html_status import render_workflow_status, summarize_workflow_progress
from .html_weights import render_weight_configurator
from .weights import make_weight_profile, materialize_weight_profile
from .batch import run_longform_batch, validate_batch_manifest

__version__ = "1.1.0"

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
    "make_weight_profile",
    "materialize_weight_profile",
    "registry_path",
    "resolve_bundle",
    "run_judge",
    "run_longform_batch",
    "run_longform_judge",
    "render_html_report",
    "render_html_scorecard",
    "render_workflow_configurator",
    "render_workflow_status",
    "render_weight_configurator",
    "segment_longform",
    "score_bundle",
    "summarize_workflow_progress",
    "validate_registry",
    "validate_batch_manifest",
    "walk_tree",
]
