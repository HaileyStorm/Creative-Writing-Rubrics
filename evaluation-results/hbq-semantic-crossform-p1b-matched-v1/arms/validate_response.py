"""Schema-parametric established-arm admission; no scoring or inference."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def semantic_validate(arm, response, request, source_texts, subset, context='', schema=None):
    if arm != 'poemetric':
        if HERE.name == 'implementation':
            path = HERE / ('ttcw-admission.py' if arm in ('ttcw14', 'oregon') else 'mfa-admission.py')
        else:
            path = HERE.parents[1] / ('hbq-matched-ttcw-20261004' if arm in ('ttcw14', 'oregon') else 'hbq-matched-mfa-v1') / 'validate_response.py'
        validator = _load('descriptive_' + arm + '_admission', path)
        return validator.semantic_validate(arm, response, request, source_texts, subset, context=context, schema=schema)
    errors = []
    if schema is None or not subset.matches_schema(response, schema):
        return {'accepted': False, 'abstention': False, 'errors': ['Response violates frozen POEMetric schema']}
    sources = request.get('sources', [])
    if len(sources) != 1 or sources[0]['id'] not in source_texts:
        return {'accepted': False, 'abstention': False, 'errors': ['Committed poem unavailable']}
    text = source_texts[sources[0]['id']]

    def require(condition, message):
        if not condition:
            errors.append(message)

    def nonblank(value):
        return isinstance(value, str) and bool(value.strip())

    def evidence(items, low, high):
        require(low <= len(items) <= high, 'POEMetric evidence cardinality differs')
        for item in items:
            require(nonblank(item['quote']) and item['quote'] in text, 'POEMetric quote is not an exact poem substring')
            require(nonblank(item['explanation']), 'POEMetric evidence explanation is blank')

    abstention = response['status'] == 'CANNOT_ASSESS'
    if abstention:
        require(response['result'] is None and nonblank(response['abstention_reason']), 'Abstention requires null result and reason')
    else:
        result = response['result']
        require(isinstance(result, dict) and response['abstention_reason'] is None, 'Scored result requires complete result and null abstention')
        if isinstance(result, dict):
            rows = result['diagnostics']
            require(len(rows) == 8 and {r['item_id'] for r in rows} == set(range(1, 9)), 'Diagnostics require items 1–8 exactly once')
            for row in rows:
                require(row['score'] >= 1 or row['item_id'] in (7, 8), 'Absence zero is permitted only for imagery/devices')
                require(nonblank(row['rationale']), 'Diagnostic rationale is blank')
                evidence(row['evidence'], 0 if row['score'] == 0 else 1, 3)
            quality = result['overall_quality']
            require(nonblank(quality['rationale']), 'Whole-poem quality rationale is blank')
            evidence(quality['evidence'], 2, 5)
            require(nonblank(result['literary_devices_comment']) and nonblank(result['quality_comment']), 'Separate comments 9/11 required')
    return {'accepted': not errors, 'abstention': abstention, 'errors': errors}
