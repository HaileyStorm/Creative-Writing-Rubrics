"""Mechanical P5 original admission; no creative quality or human labels."""
from __future__ import annotations

import hashlib
import json


def validate(packet, schema, response):
    """Validate the frozen schema subset, root identity, bounds and exact anchors."""
    errors = []

    def check(value, rule, path):
        kind = rule['type']
        valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
                 'string': isinstance(value, str), 'integer': type(value) is int}[kind]
        if not valid:
            errors.append(path + ': type')
            return
        if 'enum' in rule and value not in rule['enum']:
            errors.append(path + ': enum')
        if kind == 'object':
            props = rule['properties']
            if set(rule.get('required', [])) - set(value):
                errors.append(path + ': required keys')
            if rule.get('additionalProperties') is False and set(value) - set(props):
                errors.append(path + ': extra keys')
            for key in set(value) & set(props):
                check(value[key], props[key], path + '.' + key)
        elif kind == 'array':
            if not rule.get('minItems', 0) <= len(value) <= rule.get('maxItems', float('inf')):
                errors.append(path + ': item count')
            for index, item in enumerate(value):
                check(item, rule['items'], f'{path}[{index}]')
        elif kind == 'string':
            if not rule.get('minLength', 0) <= len(value) <= rule.get('maxLength', float('inf')):
                errors.append(path + ': length')

    check(response, schema, 'response')
    if errors:
        return {'mechanically_admitted': False, 'errors': errors, 'roots': []}
    expected = {row['root_id']: row for row in packet['roots']}
    ids = [draft['root_id'] for draft in response['drafts']]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        errors.append('Exact distinct frozen root IDs required')
    rows = []
    for draft in response['drafts']:
        root = expected[draft['root_id']]
        bounds = root['bounds']
        words = len(draft['text'].split())
        lines = sum(bool(line.strip()) for line in draft['text'].splitlines())
        context_words = len(draft['work_context'].split())
        own = []
        if draft['form'] != root['form']:
            own.append('form differs')
        if not bounds['min_words'] <= words <= bounds['max_words']:
            own.append('word bounds')
        if root['form'] == 'poem' and not bounds['min_nonempty_lines'] <= lines <= bounds['max_nonempty_lines']:
            own.append('line bounds')
        if (root['form'] == 'excerpt' and not 50 <= context_words <= 100) or (root['form'] != 'excerpt' and draft['work_context'] != ''):
            own.append('work context bounds')
        if any(anchor['quote'] not in draft['text'] for anchor in draft['preservation_anchors']):
            own.append('anchor is not exact contiguous source quote')
        errors.extend(draft['root_id'] + ': ' + error for error in own)
        rows.append({'root_id': draft['root_id'], 'form': draft['form'], 'words': words,
                     'nonempty_lines': lines, 'context_words': context_words,
                     'text_sha256': hashlib.sha256(draft['text'].encode()).hexdigest(),
                     'anchor_count': len(draft['preservation_anchors']), 'errors': own})
    return {'mechanically_admitted': not errors, 'errors': errors, 'roots': rows,
            'creative_quality_judged': False, 'human_validation': False,
            'anchors_are_generator_proposals': True, 'candidate_promoted': False}
