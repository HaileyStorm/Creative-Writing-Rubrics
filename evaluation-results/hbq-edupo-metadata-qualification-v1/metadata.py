"""Metadata-only qualification of the pinned EduPo evaluation table and tree."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

TABLE_SHA256 = 'f438b60c4fe1ad6aee1eba09400b10387cc55ea889720a7e36a40ba443572eb2'
TABLE_GIT = 'a196f9124590f9dbf144ed86746045b80713b22a'
TREE_GIT = '9348556886c5365dec644e54a3ff5f1a3f834325'
NUMBER = re.compile(rb'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?')
PAIRS = [('ChatGPT-Semantics', 'Human-Semantics'), ('ChatGPT-Syntax', 'Human-Syntax'),
         ('ChatGPT-Rhyming', 'Human-Rhyming'), ('ChatGPT-Metre', 'Human-Metre'),
         *[(x, 'Human-Overall-Imp') for x in
           ('ChatGPT-Semantics', 'ChatGPT-Syntax', 'ChatGPT-Rhyming', 'ChatGPT-Metre')]]


def git_object(kind: bytes, content: bytes) -> str:
    return hashlib.sha1(kind + b' ' + str(len(content)).encode('ascii') + b'\0' + content).hexdigest()


def tsv_rows(raw: bytes):
    """Parse TSV syntax as bytes; no data field is decoded as text."""
    row, field = [], bytearray()
    i = 0
    quoted = closed = False
    start = True
    while i < len(raw):
        byte = raw[i]
        if quoted:
            if byte == 34:
                if i + 1 < len(raw) and raw[i + 1] == 34:
                    field.append(34); i += 2; continue
                quoted, closed = False, True
            else:
                field.append(byte)
            i += 1; continue
        if byte == 34 and start:
            quoted, start = True, False; i += 1; continue
        if closed and byte not in (9, 10, 13):
            raise ValueError('invalid quoted field suffix')
        if byte == 9:
            row.append(bytes(field)); field.clear(); start, closed = True, False
        elif byte in (10, 13):
            if byte == 13 and i + 1 < len(raw) and raw[i + 1] == 10:
                i += 1
            row.append(bytes(field)); field.clear()
            if row != [b'']:
                yield row
            row, start, closed = [], True, False
        else:
            if byte == 34:
                raise ValueError('invalid unquoted quote')
            field.append(byte); start = False
        i += 1
    if quoted:
        raise ValueError('unterminated field')
    if row or field or closed:
        row.append(bytes(field)); yield row


def tree_object(entries):
    ordered = sorted(entries, key=lambda x: x[1] + (b'/' if x[0] == b'40000' else b''))
    body = b''.join(mode + b' ' + name + b'\0' + bytes.fromhex(digest)
                    for mode, name, digest in ordered)
    return git_object(b'tree', body)


def verify_tree(tree):
    if tree.get('sha') != TREE_GIT or tree.get('truncated') is not False:
        raise ValueError('unexpected tree root')
    entries = tree['tree']
    dirs = [x for x in entries if x['type'] == 'tree']
    files = [x for x in entries if x['type'] == 'blob']
    if len(entries) != 101 or len(dirs) != 1 or len(files) != 100:
        raise ValueError('unexpected tree shape')
    directory = dirs[0]
    prefix = directory['path'] + '/'
    if directory['mode'] != '040000' or '/' in directory['path']:
        raise ValueError('unexpected directory entry')
    if any(x['mode'] != '100644' or not x['path'].startswith(prefix)
           or '/' in x['path'][len(prefix):] for x in files):
        raise ValueError('unexpected file entry')
    names = [x['path'][len(prefix):].encode('utf-8') for x in files]
    if len(set(names)) != 100 or any(not n or b'/' in n or b'\0' in n for n in names):
        raise ValueError('duplicate or malformed tree filename')
    child = tree_object([(b'100644', n, x['sha']) for n, x in zip(names, files)])
    root = tree_object([(b'40000', directory['path'].encode('utf-8'), child)])
    if child != directory['sha'] or root != TREE_GIT:
        raise ValueError('Git tree object hashes do not match')
    return names


def project(raw: bytes, tree):
    if hashlib.sha256(raw).hexdigest() != TABLE_SHA256 or git_object(b'blob', raw) != TABLE_GIT:
        raise ValueError('table bytes do not match pins')
    names = verify_tree(tree)
    iterator = iter(tsv_rows(raw))
    header = [x.decode('ascii') for x in next(iterator)]
    if len(header) != 18 or len(set(header)) != 18 or header[:2] != ['filename', 'system']:
        raise ValueError('unexpected table header')
    records = list(iterator)
    if len(records) != 100 or any(len(row) != len(header) for row in records):
        raise ValueError('unexpected table shape')
    keys = [row[0] for row in records]
    basename = lambda x: x.replace(b'\\', b'/').rsplit(b'/', 1)[-1]
    counts = Counter(names)
    key_names = [basename(x) for x in keys]
    matched = sum(counts[n] == 1 for n in key_names)
    statuses = {name: [bool(NUMBER.fullmatch(row[header.index(name)].strip())) for row in records]
                for name in {name for pair in PAIRS for name in pair}}
    pairs = []
    for left, right in PAIRS:
        a, b = statuses[left], statuses[right]
        pairs.append({'left': left, 'right': right, 'left_decimal_syntax': sum(a),
                      'right_decimal_syntax': sum(b), 'both_decimal_syntax': sum(x and y for x, y in zip(a, b)),
                      'presence_mismatches': sum(x != y for x, y in zip(a, b))})
    return {'schema': 'edupo-metadata-qualification-v1', 'table_sha256': TABLE_SHA256,
            'table_git_blob_sha1': TABLE_GIT, 'poem_tree_git_sha1': TREE_GIT,
            'table_rows': len(records), 'tree_files': len(names), 'unique_table_keys': len(set(keys)),
            'unique_table_basenames': len(set(key_names)), 'unique_tree_basenames': len(counts),
            'one_to_one_basename_matches': matched,
            'exact_evaluation_relative_path_matches': sum(x in {b'poems/' + e['path'].encode('utf-8')
                                                                for e in tree['tree'] if e['type'] == 'blob'} for x in keys),
            'decimal_syntax_presence_pairs': pairs, 'scores_decoded': False,
            'poem_contents_opened': False, 'source_receipts_or_run_attested': False,
            'dataset_rights_or_unused_status_established': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--table', required=True, type=Path)
    parser.add_argument('--tree', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(project(args.table.read_bytes(), json.loads(args.tree.read_bytes())),
                     sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
