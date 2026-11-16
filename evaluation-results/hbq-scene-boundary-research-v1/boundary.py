"""Research-only validation of caller-declared UTF-8 scene boundaries."""
import argparse
import hashlib
import json
from pathlib import Path

QUESTIONS = {
    'historical_exit': 'Does the exit place emphasis effectively and create an appropriate relation to what follows?',
    'experimental_local_emphasis': 'Does the final moment place emphasis effectively within the supplied unit?',
    'existing_context_fit': 'Does the scene connect coherently to the preceding and following units when those are supplied?',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def validate(source, expected_sha256, declaration):
    """Check structure, not whether a declared unit is a literary scene.

    Offsets are zero-based UTF-8 bytes with exclusive ends. The exit must be a
    nonempty target suffix; no sentence recognition is performed. Whitespace
    separators are permitted, but all prose must belong to a declared unit.
    An unspecified boundary carries no spans and leaves the source unsegmented.
    """
    require(type(source) is bytes, 'source must be bytes')
    source.decode('utf-8', 'strict')
    require(type(expected_sha256) is str and len(expected_sha256) == 64
            and all(c in '0123456789abcdef' for c in expected_sha256), 'invalid source hash')
    require(digest(source) == expected_sha256, 'source hash mismatch')
    require(type(declaration) is dict and set(declaration) == {'boundary_kind', 'preceding', 'target', 'exit', 'following'}, 'declaration fields differ')
    kind = declaration['boundary_kind']
    require(type(kind) is str and kind in ('terminal', 'interior_supplied', 'interior_withheld', 'unspecified'), 'unknown boundary kind')
    checked = {}
    for role in ('preceding', 'target', 'exit', 'following'):
        item = declaration[role]
        if item is None:
            checked[role] = None
            continue
        require(type(item) is dict and set(item) == {'start', 'end', 'sha256'}, 'span fields differ')
        start, end = item['start'], item['end']
        require(type(start) is int and type(end) is int and 0 <= start < end <= len(source), 'invalid span range')
        source[:start].decode('utf-8', 'strict')
        source[:end].decode('utf-8', 'strict')
        text = source[start:end].decode('utf-8', 'strict')
        require(bool(text.strip()) and digest(source[start:end]) == item['sha256'], 'empty span or span hash mismatch')
        checked[role] = dict(item)
    if kind == 'unspecified':
        require(all(v is None for v in checked.values()), 'unspecified boundary carries unit spans')
    else:
        target, exit_span = checked['target'], checked['exit']
        require(target is not None and exit_span is not None, 'target and exit required')
        require(target['start'] <= exit_span['start'] < exit_span['end'] == target['end'], 'exit is not target suffix')
        require((checked['following'] is not None) == (kind == 'interior_supplied'), 'following contradicts declared scope')
        prior_end = 0
        for unit in (checked[k] for k in ('preceding', 'target', 'following') if checked[k] is not None):
            require(unit['start'] >= prior_end, 'units overlap or are unordered')
            require(not source[prior_end:unit['start']].decode('utf-8').strip(), 'unassigned prose between units')
            prior_end = unit['end']
        require(not source[prior_end:].decode('utf-8').strip(), 'unassigned trailing prose')
    context = {'version': 'research_scene_boundary_v1', 'source_sha256': expected_sha256,
               'source_bytes': len(source), 'boundary_kind': kind, 'spans': checked}
    commitment = digest(canonical(context))
    return {'shared_context': context, 'shared_context_sha256': commitment,
            'question_bindings': [{'id': key, 'text': text, 'shared_context_sha256': commitment}
                                  for key, text in QUESTIONS.items()],
            'status': 'research_declaration_only'}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--declaration', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        declaration = json.loads(args.declaration.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
        result = validate(args.source.read_bytes(), args.source_sha256, declaration)
        encoded = canonical(result)
        with args.output.open('xb') as stream:
            stream.write(encoded)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
