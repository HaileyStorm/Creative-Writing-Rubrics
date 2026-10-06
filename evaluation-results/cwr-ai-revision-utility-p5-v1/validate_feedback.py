"""Mechanical admission for frozen P5 feedback; no literary quality labels."""
from __future__ import annotations

import hashlib


def schema_errors(value, rule, path='response'):
    errors = []
    kind = rule['type']
    valid = {'object': isinstance(value, dict), 'array': isinstance(value, list),
             'string': isinstance(value, str), 'integer': type(value) is int}[kind]
    if not valid:
        return [path + ': type']
    if 'enum' in rule and value not in rule['enum']:
        errors.append(path + ': enum')
    if kind == 'object':
        props = rule['properties']
        if set(rule.get('required', [])) - set(value):
            errors.append(path + ': required keys')
        if rule.get('additionalProperties') is False and set(value) - set(props):
            errors.append(path + ': extra keys')
        for key in set(value) & set(props):
            errors.extend(schema_errors(value[key], props[key], path + '.' + key))
    elif kind == 'array':
        if not rule.get('minItems', 0) <= len(value) <= rule.get('maxItems', float('inf')):
            errors.append(path + ': item count')
        for index, item in enumerate(value):
            errors.extend(schema_errors(item, rule['items'], f'{path}[{index}]'))
    elif kind == 'string':
        if not rule.get('minLength', 0) <= len(value) <= rule.get('maxLength', float('inf')):
            errors.append(path + ': length')
    return errors


def validate(packet, schema, response, *, packet_sha256):
    errors = schema_errors(response, schema)
    if errors:
        return {'mechanically_admitted': False, 'errors': errors, 'roots': []}
    expected = {row['root_id']: row for row in packet['creative_inputs']}
    ids = [row['root_id'] for row in response['feedbacks']]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        errors.append('Exact distinct frozen root IDs required')
    if response['packet_sha256'] != packet_sha256:
        errors.append('Packet hash differs')
    rows = []
    for feedback in response['feedbacks']:
        own = []
        root = expected[feedback['root_id']]
        body = feedback['feedback_body']
        words = len(body.split())
        if words != packet['feedback_contract']['feedback_words']:
            own.append('Feedback must contain exactly180 whitespace-separated words')
        for issue in feedback['issues']:
            if issue['quote'] not in root['text'] or issue['quote'] not in body:
                own.append('Issue quote must occur verbatim in original text and feedback body')
            if len(set(issue['criterion_ids'])) != len(issue['criterion_ids']):
                own.append('Duplicate criterion IDs')
        errors.extend(feedback['root_id'] + ': ' + error for error in own)
        rows.append({'root_id': feedback['root_id'], 'form': root['form'], 'words': words,
                     'issue_count': len(feedback['issues']), 'errors': own,
                     'feedback_body_sha256': hashlib.sha256(body.encode()).hexdigest()})
    return {'mechanically_admitted': not errors, 'errors': errors, 'roots': rows,
            'creative_quality_judged': False, 'human_validation': False,
            'issue_metadata_is_model_proposal': True, 'candidate_promoted': False}
