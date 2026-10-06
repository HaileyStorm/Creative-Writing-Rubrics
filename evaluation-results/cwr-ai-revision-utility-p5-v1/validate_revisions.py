"""Mechanical revision admission; preservation and utility are later measurements."""
from __future__ import annotations

import hashlib

from validate_feedback import schema_errors


def validate(packet, schema, response, *, packet_sha256):
    errors = schema_errors(response, schema)
    if errors:
        return {'mechanically_admitted': False, 'errors': errors, 'roots': []}
    expected = {row['original']['root_id']: row for row in packet['revision_inputs']}
    ids = [row['root_id'] for row in response['revisions']]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        errors.append('Exact distinct frozen root IDs required')
    if response['packet_sha256'] != packet_sha256:
        errors.append('Packet hash differs')
    rows = []
    for revision in response['revisions']:
        original = expected[revision['root_id']]['original']
        bounds = expected[revision['root_id']]['revision_bounds']
        words = len(revision['text'].split())
        lines = sum(bool(line.strip()) for line in revision['text'].splitlines())
        own = []
        if not bounds['min_words'] <= words <= bounds['max_words']:
            own.append('Revision word allowance')
        if original['form'] == 'poem' and not bounds['min_nonempty_lines'] <= lines <= bounds['max_nonempty_lines']:
            own.append('Poem line bounds')
        if revision['work_context'] != original['work_context']:
            own.append('Original work context changed')
        errors.extend(revision['root_id'] + ': ' + error for error in own)
        rows.append({'root_id': revision['root_id'], 'form': original['form'], 'words': words,
                     'original_words': len(original['text'].split()), 'nonempty_lines': lines,
                     'text_sha256': hashlib.sha256(revision['text'].encode()).hexdigest(),
                     'unchanged_text': revision['text'] == original['text'], 'errors': own})
    return {'mechanically_admitted': not errors, 'errors': errors, 'roots': rows,
            'source_preservation_judged': False, 'creative_quality_judged': False,
            'utility_measured': False, 'human_validation': False, 'candidate_promoted': False}
