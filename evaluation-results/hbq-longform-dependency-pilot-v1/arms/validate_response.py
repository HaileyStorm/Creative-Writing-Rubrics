"""Exact available-source admission; no literary oracle or score aggregation."""
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent


def semantic_validate(arm, response, request, source_texts, subset, context='', schema=None):
    path = HERE / 'mfa-admission.py' if HERE.name == 'implementation' else HERE.parents[1] / 'hbq-matched-mfa-v1/validate_response.py'
    spec = importlib.util.spec_from_file_location('p4_available_source_admission', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.semantic_validate(arm, response, request, source_texts, subset, context=context, schema=schema)
