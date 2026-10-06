"""Source-grounded P5 response admission; this does not establish literary truth."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def legacy_validator():
    path = HERE / 'mfa_validate_response.py'
    if not path.exists():
        path = HERE.parent / 'hbq-matched-mfa-v1' / 'validate_response.py'
    spec = importlib.util.spec_from_file_location('p5_mfa_admission', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def semantic_validate(arm, response, request, source_texts, subset, context='', schema=None):
    if schema is None or not subset.matches_schema(response, schema):
        return {'accepted': False, 'abstention': False, 'errors': ['Frozen response schema violated or missing']}
    if arm in ('hbq', 'holistic', 'compact', 'pairwise'):
        return legacy_validator().semantic_validate(arm, response, request, source_texts,
                                                   subset, context=context, schema=schema)
    if arm != 'preservation':
        return {'accepted': False, 'abstention': False, 'errors': ['Unknown P5 instrument']}
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    def nonblank(value):
        return isinstance(value, str) and bool(value.strip())

    sources = request.get('sources', [])
    roles = {item.get('role'): item['id'] for item in sources}
    if (len(sources) != 2 or set(roles) != {'reference', 'candidate'}
            or len({item['id'] for item in sources}) != 2
            or any(item['id'] not in source_texts for item in sources)):
        return {'accepted': False, 'abstention': False, 'errors': ['Two committed source roles required']}
    original, candidate = (source_texts[roles[role]] for role in ('reference', 'candidate'))
    abstention = response['status'] == 'CANNOT_ASSESS'
    if abstention:
        require(response['result'] is None and nonblank(response['abstention_reason']),
                'Abstention requires null result and nonblank reason')
    else:
        result = response['result']
        require(isinstance(result, dict) and response['abstention_reason'] is None,
                'Scored preservation requires result and null abstention reason')
        if isinstance(result, dict):
            require(nonblank(result['rationale']), 'Preservation rationale is blank')
            require(1 <= len(result['voice_evidence']) <= 3, 'Voice evidence requires one to three source pairs')
            require(len(result['introduced_defects']) <= 3, 'Introduced defect cap exceeded')
            for item in [*result['voice_evidence'], *result['introduced_defects']]:
                require(nonblank(item['reference_quote']) and item['reference_quote'] in original,
                        'Reference quotation is not exact')
                require(nonblank(item['candidate_quote']) and item['candidate_quote'] in candidate,
                        'Candidate quotation is not exact')
                require(nonblank(item['explanation']), 'Source comparison explanation is blank')
    return {'accepted': not errors, 'abstention': abstention, 'errors': errors}
