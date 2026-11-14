"""Source-only WPB development selector; no provider calls or target writes.

The actual freeze is not read unless --run is explicitly supplied. Excluded
rows are scanned as bytes only. Even selected target score fields are skipped.
"""
from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
from pathlib import Path

RECIPE = Path(__file__).resolve().parent / 'RECIPE.md'
RECIPE_SHA = '04e58c61334b89c3a094a2c68b16c0bfb28c71584a5a5ca047401afa7d51d326'
PINS = {
    'default-schedule.json': 'f24f785b5ed100d9fbe98542172aef18cf7581bf030a9bd3d241e5e712f08f9f',
    'execution-inputs.json': '812fbd9a5994c7e109e1f53e397db9c9c7f08e8cf898a2f0bfd3f57a88a13a3a',
    'local-targets.json': 'b87d3daf192879c0fdd429c7bfa670047a60ebe78ac26bb04ab4cb86e546a828',
    'provenance-selection-manifest.json': '2ea729edaa7d048d5e6136e18186598b788a5239ae9e504d364e2f1f1840b997',
    'split-manifest.json': '101660d24eb81ae05f0779c0f402b48d68d988d25118f7cef125bf583a923ef1',
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def pinned(path: Path, expected: str) -> bytes:
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError('Pinned file differs')
    return raw


def whitespace(buf: bytes, i: int) -> int:
    while i < len(buf) and buf[i] in b' \t\r\n':
        i += 1
    return i


def string_end(buf: bytes, i: int) -> int:
    if buf[i:i+1] != b'"':
        raise ValueError('Expected JSON string')
    i += 1
    while i < len(buf):
        if buf[i] == 92:
            i += 2
        elif buf[i] == 34:
            return i + 1
        else:
            i += 1
    raise ValueError('Unterminated JSON string')


def value_end(buf: bytes, i: int) -> int:
    i = whitespace(buf, i)
    if i >= len(buf):
        raise ValueError('Missing JSON value')
    if buf[i] == 34:
        return string_end(buf, i)
    if buf[i] in (91, 123):
        stack = [93 if buf[i] == 91 else 125]
        i += 1
        while stack and i < len(buf):
            c = buf[i]
            if c == 34:
                i = string_end(buf, i)
                continue
            if c in (91, 123):
                stack.append(93 if c == 91 else 125)
            elif c in (93, 125):
                if c != stack.pop():
                    raise ValueError('Mismatched JSON boundary')
            i += 1
        if stack:
            raise ValueError('Unterminated JSON value')
        return i
    j = i
    while j < len(buf) and buf[j] not in b',}] \t\r\n':
        j += 1
    if i == j:
        raise ValueError('Empty JSON value')
    return j


def fields(buf: bytes, start: int, end: int) -> dict[str, tuple[int, int]]:
    i = whitespace(buf, start)
    if buf[i:i+1] != b'{':
        raise ValueError('Expected object')
    i += 1
    result = {}
    while True:
        i = whitespace(buf, i)
        if buf[i:i+1] == b'}':
            if whitespace(buf, i + 1) != end:
                raise ValueError('Object boundary differs')
            return result
        e = string_end(buf, i)
        key = json.loads(buf[i:e])  # field names only, never excluded values
        if key in result:
            raise ValueError('Duplicate object field')
        i = whitespace(buf, e)
        if buf[i:i+1] != b':':
            raise ValueError('Missing object colon')
        i = whitespace(buf, i + 1)
        e = value_end(buf, i)
        result[key] = (i, e)
        i = whitespace(buf, e)
        if buf[i:i+1] == b',':
            i += 1
        elif buf[i:i+1] != b'}':
            raise ValueError('Invalid object delimiter')


def array_items(buf: bytes, bounds: tuple[int, int]):
    start, end = bounds
    i = whitespace(buf, start)
    if buf[i:i+1] != b'[':
        raise ValueError('Expected array')
    i += 1
    while True:
        i = whitespace(buf, i)
        if buf[i:i+1] == b']':
            if whitespace(buf, i + 1) != end:
                raise ValueError('Array boundary differs')
            return
        e = value_end(buf, i)
        yield (i, e)
        i = whitespace(buf, e)
        if buf[i:i+1] == b',':
            i += 1
        elif buf[i:i+1] != b']':
            raise ValueError('Invalid array delimiter')


def decode_field(buf: bytes, mapping: dict, key: str):
    a, b = mapping[key]
    return json.loads(buf[a:b])


def json_string(value: str) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def selected_rows(buf: bytes, array_key: str, allow: set[str], requested: tuple[str, ...], *, id_key: str = 'cell_id', prefix: str = '') -> dict:
    top = fields(buf, 0, len(buf))
    result = {}
    encoded_ids = {json_string(cell.removeprefix(prefix)): cell for cell in allow if cell.startswith(prefix)}
    if len(encoded_ids) != len(allow):
        raise ValueError('Allowlist encoding differs')
    for begin, end in array_items(buf, top[array_key]):
        row = fields(buf, begin, end)
        a, b = row[id_key]
        cell = encoded_ids.get(buf[a:b])
        if cell is None:
            continue  # excluded row values, including its ID, are never decoded
        if cell in result:
            raise ValueError('Duplicate allowed cell')
        result[cell] = {key: decode_field(buf, row, key) for key in requested}
    if set(result) != allow:
        raise ValueError('Missing allowed cells')
    return result


def make_payload(prompt: str, a: str, b: str) -> bytes:
    return ('Evaluate the two responses to the writing request for overall creative-writing quality. '
            'Choose the stronger response; use TIE only if they are genuinely tied.\n\n'
            f'Writing request:\n{prompt}\n\nResponse A:\n{a}\n\nResponse B:\n{b}\n\n'
            'Reply with exactly one token: A, B, or TIE.').encode('utf-8')


def analyze(freeze_root: Path) -> dict:
    pinned(RECIPE, RECIPE_SHA)
    raw = {name: pinned(freeze_root / name, pin) for name, pin in PINS.items()}
    schedule = json.loads(raw['default-schedule.json'])
    if schedule.get('confirmation_excluded') is not True or schedule.get('open_partitions') != ['train', 'dev']:
        raise ValueError('Development schedule boundary differs')
    cells = schedule['cells']
    by_id = {r['cell_id']: r for r in cells}
    if len(cells) != 129 or len(by_id) != 129 or collections.Counter(r['partition'] for r in cells) != {'train': 105, 'dev': 24}:
        raise ValueError('Development schedule geometry differs')
    allow = set(by_id)
    inputs = selected_rows(raw['execution-inputs.json'], 'cells', allow,
                           ('partition', 'prompt', 'prompt_sha256', 'response_a', 'response_a_sha256',
                            'response_b', 'response_b_sha256', 'payload_utf8_base64', 'payload_sha256'))
    targets = selected_rows(raw['local-targets.json'], 'targets', allow,
                            ('partition', 'category', 'source_row_sha256', 'preferred_side'))
    # Select metadata with the same raw-ID allowlist; do not decode closed rows.
    selected = selected_rows(raw['provenance-selection-manifest.json'], 'selected', allow,
                             ('category', 'partition', 'row_sha256', 'prompt_sha256', 'response_sha256s'),
                             id_key='row_id', prefix='wpb-pair-')
    wanted_categories = {r['category'] for r in selected.values()}
    split_raw = raw['split-manifest.json']
    split_top = fields(split_raw, 0, len(split_raw))
    category_keys = {json_string(cat): cat for cat in wanted_categories}
    categories = {}
    for start, end in array_items(split_raw, split_top['partitions']):
        row = fields(split_raw, start, end)
        a, b = row['category']
        cat = category_keys.get(split_raw[a:b])
        if cat is None:
            continue
        if cat in categories:
            raise ValueError('Duplicate selected category')
        categories[cat] = decode_field(split_raw, row, 'partition')
    if len(selected) != 129 or set(selected) != allow:
        raise ValueError('Selected metadata differs from schedule')
    per_cat = collections.defaultdict(collections.Counter)
    for cell in allow:
        row, target, meta, sched = inputs[cell], targets[cell], selected[cell], by_id[cell]
        part, cat = target['partition'], target['category']
        if part != sched['partition'] or row['partition'] != part or meta['partition'] != part or meta['category'] != cat or categories.get(cat) != part or meta['row_sha256'] != target['source_row_sha256']:
            raise ValueError('Partition or source binding differs')
        a, b, prompt = row['response_a'], row['response_b'], row['prompt']
        if not all(isinstance(s, str) for s in (a, b, prompt)):
            raise ValueError('Input text is not a string')
        for field, text in [('prompt_sha256', prompt), ('response_a_sha256', a), ('response_b_sha256', b)]:
            if digest(text.encode('utf-8')) != row[field]:
                raise ValueError('Input text commitment differs')
        if row['prompt_sha256'] != meta['prompt_sha256'] or sorted([row['response_a_sha256'], row['response_b_sha256']]) != sorted(meta['response_sha256s']):
            raise ValueError('Selected provenance differs from input commitments')
        payload = base64.b64decode(row['payload_utf8_base64'], validate=True)
        if payload != make_payload(prompt, a, b) or digest(payload) != row['payload_sha256'] or row['payload_sha256'] != sched['payload_sha256']:
            raise ValueError('Payload binding differs')
        preferred = target['preferred_side']
        if preferred not in ('A', 'B'):
            raise ValueError('Preferred side invalid')
        winner = 'A' if len(a) > len(b) else 'B' if len(b) > len(a) else None
        outcome = 'tie' if winner is None else 'win' if winner == preferred else 'loss'
        per_cat[(part, cat)][outcome] += 1
    output = {}
    for part, expected_cats in [('train', 35), ('dev', 8)]:
        values = [counts for (p, _), counts in per_cat.items() if p == part]
        if len(values) != expected_cats or any(sum(counts.values()) != 3 for counts in values):
            raise ValueError('Category geometry differs')
        total = sum(values, collections.Counter())
        output[part] = {'pairs': sum(total.values()), 'categories': len(values),
                        'wins': total['win'], 'losses': total['loss'], 'ties': total['tie'],
                        'category_macro_win_proportion': sum(c['win'] / 3 for c in values) / len(values)}
    return {'scope': 'POST_RESULT_OPENED_DEVELOPMENT_ONLY', 'rule': 'longer_unicode_codepoints_ties_not_wins',
            'partitions': output, 'recipe_sha256': RECIPE_SHA, 'source_sha256': PINS,
            'confirmation_values_decoded': False, 'target_scores_decoded': False,
            'provider_calls': 0, 'new_labels': 0}


def self_test() -> None:
    data = {'targets': [
        {'cell_id': 'open', 'partition': 'train', 'preferred_side': 'A', 'chosen_score': 'DO_NOT_DECODE_SCORE'},
        {'cell_id': 'closed', 'partition': 'confirmation', 'preferred_side': 'DO_NOT_DECODE_CLOSED', 'other': 'quoted } ] \\ \"'}]}
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
    output = selected_rows(encoded, 'targets', {'open'}, ('partition', 'preferred_side'))
    assert output == {'open': {'partition': 'train', 'preferred_side': 'A'}}
    print('Synthetic selector check passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--self-test', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--freeze-root', type=Path, help='Path to the existing WPB r3 freeze')
    options = parser.parse_args()
    if options.self_test:
        self_test()
    else:
        if options.freeze_root is None:
            parser.error('--run requires --freeze-root')
        print(json.dumps(analyze(options.freeze_root), sort_keys=True, indent=2))
