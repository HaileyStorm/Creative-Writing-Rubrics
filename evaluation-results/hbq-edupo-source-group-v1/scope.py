"""Check source groups and the published EduPo evaluator's static header."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREDECESSOR = HERE.parent / 'hbq-edupo-metadata-qualification-v1' / 'metadata.py'
PREDECESSOR_SHA256 = 'dbc8a5a31859744f301e6d455cd209a93ce5a883ceefb8b3857806e5e78cc71c'
AUTO_GIT = '1ac5ecbc5db1f5488a5b16d4d7950b9afd97e1b0'
EVALUATOR_GIT = '6faaa6160648477905d87eb87a5b1cdb21b95aa6'


def load_predecessor():
    if hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest() != PREDECESSOR_SHA256:
        raise ValueError('predecessor source changed')
    spec = importlib.util.spec_from_file_location('edupo_prior_metadata', PREDECESSOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluator_header(raw):
    """Inspect the pinned code's straight-line header writes without execution."""
    tree = ast.parse(raw)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign) and
                   len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id == 'measures']
    if len(assignments) != 1:
        raise ValueError('unique measures assignment required')
    measures = ast.literal_eval(assignments[0].value)
    if not isinstance(measures, tuple) or not measures or any(not isinstance(x, str) for x in measures):
        raise ValueError('invalid measures literal')
    writers = [n for n in tree.body if isinstance(n, ast.With) and len(n.items) == 1
               and isinstance(n.items[0].optional_vars, ast.Name) and n.items[0].optional_vars.id == 'f']
    if len(writers) != 1 or len(writers[0].body) < 3:
        raise ValueError('unique file writer required')
    first, loop, third = writers[0].body[:3]
    expected = lambda code: ast.dump(ast.parse(code).body[0], include_attributes=False)
    if (ast.dump(first, include_attributes=False) != expected("f.write('filename')")
            or not isinstance(loop, ast.For) or ast.dump(loop.target, include_attributes=False) != ast.dump(ast.Name(id='m', ctx=ast.Store()), include_attributes=False)
            or ast.dump(loop.iter, include_attributes=False) != ast.dump(ast.Name(id='measures', ctx=ast.Load()), include_attributes=False)
            or not loop.body or ast.dump(loop.body[0], include_attributes=False) != expected("f.write('\\t'+m)")
            or ast.dump(third, include_attributes=False) != expected("f.write('\\n')")):
        raise ValueError('header-write structure differs')
    return ['filename', *measures]


def group_summary(rows, paths):
    normalize = lambda x: x.replace(b'\\', b'/')
    basename = lambda x: x.rsplit(b'/', 1)[-1]
    parent = lambda x: x.rsplit(b'/', 1)[0] if b'/' in x else b''
    keys = [normalize(row[0]) for row in rows]
    groups = [row[1].strip().lower() for row in rows]
    source_groups = Counter(groups)
    tree_paths = [x.encode('utf-8') for x in paths]
    lookup = {basename(p): p for p in tree_paths}
    if len(keys) != 100 or len(set(keys)) != 100 or len(lookup) != 100 or any(basename(x) not in lookup for x in keys):
        raise ValueError('source key or tree matching differs')
    pairs = [(key, lookup[basename(key)]) for key in keys]
    return {'source_group_count': len(source_groups), 'source_group_sizes_sorted': sorted(source_groups.values()),
            'ccv_tagged_rows': source_groups.get(b'ccv', 0),
            'table_parent_count': len({parent(x) for x in keys}),
            'table_to_tree_parent_mappings': len({(parent(x), parent(y)) for x, y in pairs}),
            'table_paths_ending_in_tree_path': sum(x == y or x.endswith(b'/' + y) for x, y in pairs),
            'tree_paths_ending_in_table_path': sum(x == y or y.endswith(b'/' + x) for x, y in pairs)}


def project(combined: bytes, tree: dict, automatic: bytes, evaluator: bytes):
    prior = load_predecessor()
    checked = prior.project(combined, tree)
    if (checked['table_rows'], checked['one_to_one_basename_matches']) != (100, 100):
        raise ValueError('predecessor census differs')
    if prior.git_object(b'blob', automatic) != AUTO_GIT or prior.git_object(b'blob', evaluator) != EVALUATOR_GIT:
        raise ValueError('automatic table or evaluator pin differs')
    rows = iter(prior.tsv_rows(combined)); header = next(rows)
    if header[:2] != [b'filename', b'system']:
        raise ValueError('combined table header differs')
    data = list(rows)
    groups = group_summary(data, [x['path'] for x in tree['tree'] if x['type'] == 'blob'])
    table_header = [x.decode('ascii') for x in next(prior.tsv_rows(automatic))]
    direct_header = evaluator_header(evaluator)
    return {'schema': 'edupo-source-group-v1', 'prior_aggregate_schema': checked['schema'],
            'prior_implementation_sha256': PREDECESSOR_SHA256,
            'combined_table_git_blob_sha1': prior.TABLE_GIT, 'poem_tree_git_sha1': prior.TREE_GIT,
            'automatic_table_git_blob_sha1': AUTO_GIT, 'evaluator_git_blob_sha1': EVALUATOR_GIT,
            'source_group_metadata': groups, 'automatic_header_columns': len(table_header),
            'direct_evaluator_header_columns': len(direct_header),
            'direct_evaluator_header_equals_automatic_table': direct_header == table_header,
            'historical_execution_or_content_join_attested': False,
            'individual_ratings_or_poem_contents_decoded': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('combined', 'tree', 'automatic', 'evaluator'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(project(args.combined.read_bytes(), json.loads(args.tree.read_bytes()),
                             args.automatic.read_bytes(), args.evaluator.read_bytes()),
                     sort_keys=True, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
