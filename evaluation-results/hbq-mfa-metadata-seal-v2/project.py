"""Seal exact MFA releases and expose only outcome-blind source geometry."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RECIPE = HERE / 'source-recipe.json'
RECIPE_SHA256 = '61bea810009347727c7b781085aea2189521e1944a76dcea59dd0ab8ad02245e'
_spec = importlib.util.spec_from_file_location('mfa_seal_v1', HERE.parent / 'hbq-mfa-metadata-seal-v1' / 'project.py')
_v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v1)
canonical, sha, identity, git_blob, write = (_v1.canonical, _v1.sha, _v1.identity, _v1.git_blob, _v1.write)
POLICY = 'mfa_outcome_blind_metadata_v2'
KNOWN_SHA256 = {
    'f529644fd72ee400f3bc326400247df228412ec3': '84dc98276179578414eb6bfae44d61c53c23bfdfeb6fba2190df4707ef58d3f3',
    'd6c0ff45544f24911f5beac98aff56bc67cfcc5b': '9dbb9a3c33b028c122117dfcf1311a11d0b9147c0fd9e9d82f2a5f71b00f2e72',
    '120caa03e5f12ea75e1920fefbd6582ca7eec2f4': '1491b60db465d883b4abe66d7363463b5a6b98f84ef9a3f0af578ff280cac525',
    '75b74c8e5392a4684f4090b5dc05e9943ae43f99': '7e4f1f197cece376fb09ed3d9c8e0d6f1494ff4f28767d04b0da2858ee0eea04',
}


def optional_identity(value):
    return identity(value) if isinstance(value, (str, int)) and not isinstance(value, bool) and value != '' else None


def original_metadata(record, field='Original'):
    value = record.get(field)
    return {'original_present': field in record,
            'original_is_text': isinstance(value, str),
            'original_hash': sha(value.encode('utf-8')) if isinstance(value, str) else None,
            'original_bytes': len(value.encode('utf-8')) if isinstance(value, str) else None}


def project(data, filename, release):
    """Only structural identities, ordered excerpts and explicit Original leave sealing."""
    if not isinstance(data, dict):
        raise ValueError('Unexpected source root structure')
    task, condition, panel = Path(filename).name.split('_')[:3]
    rows = []
    for target_position, (target, authors) in enumerate(data.items()):
        if not isinstance(target, str) or not isinstance(authors, dict):
            raise ValueError('Unexpected target grouping')
        for writer_position, (writer, judgments) in enumerate(authors.items()):
            if not isinstance(writer, str) or not isinstance(judgments, list):
                raise ValueError('Unexpected writer grouping')
            for index, judgment in enumerate(judgments):
                if not isinstance(judgment, list) or len(judgment) not in (2, 3) or not isinstance(judgment[-1], dict):
                    raise ValueError('Unexpected judgment structure')
                record = judgment[-1]
                rater = judgment[1] if len(judgment) == 3 else record.get('user')
                excerpts = [record.get('Excerpt1'), record.get('Excerpt2')]
                if not all(isinstance(text, str) and text for text in excerpts):
                    raise ValueError('Missing source excerpt; no inferred artifact')
                hashes = [sha(text.encode('utf-8')) for text in excerpts]
                target_hash, writer_hash = optional_identity(target), optional_identity(writer)
                row = {'release': release, 'source_path': filename,
                       'task': task, 'condition': condition, 'panel': panel,
                       'target_hash': target_hash, 'writer_hash': writer_hash,
                       'rater_hash': optional_identity(rater),
                       'judgment_identity_hash': optional_identity(record.get('id')),
                       'source_position': index, 'target_position': target_position,
                       'writer_position': writer_position, 'excerpt_hashes': hashes,
                       'excerpt_bytes': [len(text.encode('utf-8')) for text in excerpts],
                       'pair_hash': identity({'target': target_hash, 'condition': condition, 'excerpts': sorted(hashes)}),
                       'ordered_pair_hash': identity({'target': target_hash, 'condition': condition, 'excerpts': hashes}),
                       **original_metadata(record)}
                row['metadata_record_hash'] = identity({k: v for k, v in row.items() if k not in ('release', 'source_path')})
                rows.append(row)
    return rows


def project_references(data, release, path):
    """Source parser names writer/original; never infer identities from root keys."""
    references = []
    nodes = [(data, [])]
    while nodes:
        node, position = nodes.pop()
        if isinstance(node, dict):
            fields = [field for field in ('original', 'Original') if field in node]
            if not fields and 'writer' in node:
                fields = ['original']
            for field in fields:
                # A field-name identity is distinct from any inferred outer-key identity.
                writer = optional_identity(node.get('writer'))
                references.append({'release': release, 'source_path': path,
                                   'source_position': position, 'writer_hash': writer,
                                   'writer_identity_basis': 'explicit_writer_field' if writer else 'unverified',
                                   'source_original_field': field,
                                   'original_field_basis': 'pinned_source_parser' if field == 'original' else 'uppercase_compatibility',
                                   **original_metadata(node, field)})
            nodes.extend((value, position + [index]) for index, value in reversed(list(enumerate(node.values())))
                         if isinstance(value, (dict, list)))
        elif isinstance(node, list):
            nodes.extend((value, position + [index]) for index, value in reversed(list(enumerate(node)))
                         if isinstance(value, (dict, list)))
    return references


def count_geometry(rows):
    groups = defaultdict(set)
    for row in rows:
        # Missing labels are not a shared identity across distinct source groups.
        target = row['target_hash'] or ('missing', row['source_path'], row['target_position'])
        writer = row['writer_hash'] or ('missing', row['source_path'], row['target_position'], row['writer_position'])
        groups[(target, writer)].add(row['pair_hash'])
    variants = Counter(len(pairs) for pairs in groups.values())
    present = lambda key: {r[key] for r in rows if r[key] is not None}
    return {'judgment_rows': len(rows), 'nominal_target_writer_groups': len(groups),
            'target_writer_pair_memberships': sum(map(len, groups.values())),
            'groups_with_multiple_exact_pairs': sum(n for k, n in variants.items() if k > 1),
            'group_exact_pair_count_histogram': {str(k): n for k, n in sorted(variants.items())},
            'pairs': len(present('pair_hash')), 'ordered_pairs': len(present('ordered_pair_hash')),
            'target_identifiers': len(present('target_hash')), 'writer_identifiers': len(present('writer_hash')),
            'rater_identifiers': len(present('rater_hash')),
            'missing_rater_rows': sum(r['rater_hash'] is None for r in rows),
            'missing_record_identity_rows': sum(r['judgment_identity_hash'] is None for r in rows),
            'missing_target_rows': sum(r['target_hash'] is None for r in rows),
            'missing_writer_rows': sum(r['writer_hash'] is None for r in rows),
            'distinct_exact_excerpts': len({h for r in rows for h in r['excerpt_hashes']}),
            'original_present_rows': sum(r['original_present'] for r in rows),
            'original_text_rows': sum(r['original_is_text'] for r in rows),
            'missing_original_rows': sum(not r['original_is_text'] for r in rows),
            'distinct_original_hashes': len(present('original_hash'))}


def overlap(left, right):
    fields = ('metadata_record_hash', 'pair_hash', 'ordered_pair_hash', 'target_hash',
              'writer_hash', 'rater_hash', 'judgment_identity_hash', 'original_hash')
    result = {}
    for field in fields:
        a, b = (Counter(r[field] for r in rows if r[field] is not None) for rows in (left, right))
        result[field] = {'shared_distinct': len(a.keys() & b.keys()),
                         'shared_occurrences_minimum': sum((a & b).values()),
                         'left_only_distinct': len(a.keys() - b.keys()),
                         'right_only_distinct': len(b.keys() - a.keys())}
    a, b = ({h for r in rows for h in r['excerpt_hashes']} for rows in (left, right))
    result['excerpt_hash'] = {'shared_distinct': len(a & b), 'left_only_distinct': len(a - b), 'right_only_distinct': len(b - a)}
    return result


def reference_links(rows, references):
    catalogue = defaultdict(set)
    catalogue_writers = {r['writer_hash'] for r in references if r['writer_hash'] is not None}
    for reference in references:
        if reference['writer_hash'] is not None and reference['original_hash'] is not None:
            catalogue[reference['writer_hash']].add(reference['original_hash'])
    targets = {r['target_hash'] for r in rows if r['target_hash'] is not None}
    outcome_originals = defaultdict(set)
    for row in rows:
        if row['target_hash'] is not None and row['original_hash'] is not None:
            outcome_originals[row['target_hash']].add(row['original_hash'])
    exact = [r for r in rows if r['target_hash'] is not None and r['original_hash'] is not None
             and r['original_hash'] in catalogue.get(r['target_hash'], set())]
    return {'catalogue_writer_identifiers': len(catalogue_writers), 'outcome_target_identifiers': len(targets),
            'shared_writer_target_identifier_hashes': len(catalogue_writers & targets),
            'catalogue_writer_identifiers_without_outcome_target_match': len(catalogue_writers - targets),
            'outcome_target_identifiers_without_catalogue_writer_match': len(targets - catalogue_writers),
            'catalogue_writer_identifiers_with_multiple_original_hashes': sum(len(hashes) > 1 for hashes in catalogue.values()),
            'outcome_target_identifiers_with_multiple_original_hashes': sum(len(hashes) > 1 for hashes in outcome_originals.values()),
            'outcome_rows_missing_target_identity': sum(r['target_hash'] is None for r in rows),
            'outcome_rows_missing_original_text': sum(r['original_hash'] is None for r in rows),
            'outcome_rows_with_target_identifier_match': sum(r['target_hash'] in catalogue_writers for r in rows),
            'outcome_rows_without_catalogue_target_identifier_match': sum(r['target_hash'] is not None and r['target_hash'] not in catalogue_writers for r in rows),
            'outcome_rows_with_target_match_but_unmatched_original_hash': sum(
                r['target_hash'] in catalogue_writers and r['original_hash'] is not None
                and r['original_hash'] not in catalogue.get(r['target_hash'], set()) for r in rows),
            'outcome_rows_with_exact_target_and_original_match': len(exact),
            'distinct_exact_target_original_links': len({(r['target_hash'], r['original_hash']) for r in exact}),
            'exact_matched_rows_with_multiple_catalogue_original_variants': sum(len(catalogue[r['target_hash']]) > 1 for r in exact),
            'basis': 'catalogue explicit writer hash equals outcome target hash AND exact original UTF8 hash; no participant independence inferred'}


def aggregate(rows, references, releases):
    keys = sorted({(r['release'], r['task'], r['condition'], r['panel']) for r in rows})
    groups = []
    for release, task, condition, panel in keys:
        selected = [r for r in rows if (r['release'], r['task'], r['condition'], r['panel']) == (release, task, condition, panel)]
        groups.append({'release': release, 'task': task, 'condition': condition, 'panel': panel, **count_geometry(selected)})
    left, right = releases
    cross = []
    for task, condition, panel in sorted({(r['task'], r['condition'], r['panel']) for r in rows}):
        selected = [[r for r in rows if (r['release'], r['task'], r['condition'], r['panel']) == (release, task, condition, panel)] for release in releases]
        cross.append({'task': task, 'condition': condition, 'panel': panel, **overlap(*selected)})
    ref_counts = []
    for release in releases:
        selected = [r for r in references if r['release'] == release]
        hashes = {r['original_hash'] for r in selected if r['original_hash'] is not None}
        outcome_rows = [r for r in rows if r['release'] == release]
        outcome_hashes = {r['original_hash'] for r in outcome_rows if r['original_hash'] is not None}
        links = reference_links(outcome_rows, selected)
        ref_counts.append({'release': release, 'explicit_original_records': len(selected),
                           'distinct_original_hashes': len(hashes),
                           'missing_writer_identity_records': sum(r['writer_hash'] is None for r in selected),
                           'missing_original_text_records': sum(not r['original_is_text'] for r in selected),
                           'exact_original_hashes_shared_with_outcome_rows': len(hashes & outcome_hashes),
                           'outcome_original_hashes_without_recognized_catalogue_match': len(outcome_hashes - hashes),
                           'source_original_field_counts': dict(sorted(Counter(r['source_original_field'] for r in selected).items())),
                           'catalogue_schema': 'source_parser_writer_original_fields; released_root_shape_unverified',
                           'writer_target_links': links,
                           'reference_identity_links': 'exact_writer_target_and_original_hash_matches_observed'
                               if links['distinct_exact_target_original_links'] else 'unverified'})
    reference_sets = [{r['original_hash'] for r in references if r['release'] == release and r['original_hash'] is not None} for release in releases]
    return {'judgment_rows': len(rows), 'by_release_task_condition_panel': groups,
            'cross_release': {'left': left, 'right': right, 'by_task_condition_panel': cross,
                              'all_rows': overlap(*[[r for r in rows if r['release'] == release] for release in releases])},
            'references': ref_counts,
            'cross_release_recognized_reference_hashes': len(reference_sets[0] & reference_sets[1]),
            'identifier_namespace': {'encoding': 'v1 canonical JSON SHA256 for identifiers; exact UTF8 SHA256 for text',
                                     'comparison': 'shared raw source-label namespace; cross-release equality is diagnostic only',
                                     'rater_identity': 'source identifier hashes do not establish independent humans or panel identity',
                                     'record_identity': 'id hashes exclude missing values; no missing identity is synthesized',
                                     'reference_identity': 'catalogue writer identifies target author in pinned parser; compare its exact identifier hash to outcome target, never generated writer',
                                     'pair_identity': 'v1 target/condition/sorted exact excerpts; excludes writer, task, panel and release',
                                     'row_identity': 'whitelisted metadata and positions only; never complete raw judgment equality'},
            'independent_work_count': None, 'independent_participant_count': None,
            'metadata_commitment_sha256': sha(canonical({'rows': rows, 'references': references}))}


def load_recipe():
    raw = RECIPE.read_bytes()
    recipe = json.loads(raw)
    if sha(canonical(recipe)) != RECIPE_SHA256:
        raise ValueError('Frozen recipe digest mismatch')
    return raw, recipe


def validate_source(raw, blob, size):
    if len(raw) != size or git_blob(raw) != blob:
        raise ValueError('Source bytes differ from frozen Git blob/size')
    digest = sha(raw)
    if blob in KNOWN_SHA256 and digest != KNOWN_SHA256[blob]:
        raise ValueError('Source SHA256 differs from prior exact source receipt')
    return digest


def read_bounded(path, size):
    with path.open('rb') as handle:
        return handle.read(size + 1)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect from frozen source destination refused')


def fetch(url, size):
    with build_opener(NoRedirect).open(Request(url, headers={'User-Agent': 'CWR-outcome-blind-source-audit/2'}), timeout=45) as response:
        if response.status != 200 or response.url != url:
            raise ValueError('Source retrieval changed frozen destination or did not return HTTP200')
        return response.read(size + 1)


def find_cached(release, path, blob, size, roots, recipe):
    # Exact paths only: do not scan or open unrelated cached outcomes.
    locators = [(release, path)] + [(r['release'], p) for r in recipe['releases'] for p, b, n, _ in r['sources'] if (b, n) == (blob, size)]
    for root in roots:
        candidates = [root / name / p for name, p in locators] + [root / p for _, p in locators]
        for candidate in dict.fromkeys(candidates):
            if candidate.is_file():
                raw = read_bounded(candidate, size)
                if len(raw) == size and git_blob(raw) == blob:
                    return raw, str(candidate.resolve())
    return None, None


def run(output, source_root=None, cache_roots=(), recipe=None, recipe_raw=None):
    if recipe is None:
        recipe_raw, recipe = load_recipe()
    output = Path(output).resolve()
    roots = ([Path(source_root).resolve()] if source_root else []) + [Path(p).resolve() for p in cache_roots]
    inputs = [REPO, HERE, *roots]
    if output.exists() or any(output.is_relative_to(p) or p.is_relative_to(output) for p in inputs):
        raise ValueError('Use a fresh private destination outside repository and inputs')
    output.mkdir(parents=True, exist_ok=False)
    recipe_raw = recipe_raw if recipe_raw is not None else canonical(recipe)
    implementation = Path(__file__).read_bytes()
    invocation = {'policy': POLICY, 'source_mode': 'local_replay' if source_root else 'bounded_exact_pinned_raw_files',
                  'recipe_sha256': sha(recipe_raw), 'projector_sha256': sha(implementation),
                  'v1_projector_sha256': sha(Path(_v1.__file__).read_bytes()),
                  'source_root': str(roots[0]) if source_root else None,
                  'cache_roots': [str(p) for p in roots[1 if source_root else 0:]],
                  'automatic_network_retries': 0, 'target_opening_authorized': False,
                  'purpose': recipe['terms'], 'released_fields': 'hashes/counts/lengths/structural positions only'}
    write(output / 'invocation.json', canonical(invocation))
    write(output / 'source-recipe.json', recipe_raw)
    write(output / 'implementation' / 'project-v2.py', implementation)
    write(output / 'implementation' / 'project-v1.py', Path(_v1.__file__).read_bytes())
    rows, references, receipts, by_blob = [], [], [], {}
    current = None
    try:
        for release in recipe['releases']:
            for path, blob, size, kind in release['sources']:
                current = {'release': release['release'], 'repository': release['repository'],
                           'revision': release['revision'], 'path': path, 'git_blob_sha1': blob, 'bytes': size, 'kind': kind}
                ordinal = len(receipts)
                write(output / 'requests' / f'{ordinal:03d}.json', canonical(current))
                reused = blob in by_blob
                if reused:
                    raw, origin = by_blob[blob]
                    mode = 'same_run_exact_blob_reuse'
                else:
                    raw, origin = find_cached(release['release'], path, blob, size, roots, recipe)
                    mode = 'existing_exact_blob_cache' if raw is not None else 'pinned_remote_file'
                    if raw is None:
                        if source_root:
                            raise ValueError('Local replay missing exact pinned source bytes')
                        origin = f"https://raw.githubusercontent.com/{release['repository']}/{release['revision']}/{path}"
                        raw = fetch(origin, size)
                sealed = output / 'sealed-source' / release['release'] / path
                write(sealed, raw)
                write(output / 'received' / f'{ordinal:03d}.json', canonical({**current,
                      'received_bytes': len(raw), 'received_git_blob_sha1': git_blob(raw),
                      'received_sha256': sha(raw), 'retrieval_mode': mode,
                      'retrieval_origin': origin, 'accepted': False}))
                digest = validate_source(raw, blob, size)
                if sha(read_bounded(sealed, size)) != digest:
                    raise ValueError('Sealed source SHA256 read-back mismatch')
                by_blob[blob] = (raw, origin)
                data = json.loads(raw)
                projected = project(data, path, release['release']) if kind == 'outcomes' else project_references(data, release['release'], path)
                (rows if kind == 'outcomes' else references).extend(projected)
                receipt = {**current, 'sha256': digest, 'retrieval_mode': mode, 'retrieval_origin': origin,
                           'metadata_rows': len(projected), 'metadata_sha256': sha(canonical(projected))}
                receipts.append(receipt)
                write(output / 'receipts' / f'{ordinal:03d}.json', canonical(receipt))
                write(output / 'metadata-parts' / f'{ordinal:03d}.json', canonical(projected))
        summary = {'policy': POLICY, 'source_receipts': [{k: v for k, v in receipt.items() if k != 'retrieval_origin'} for receipt in receipts],
                   'cohort': aggregate(rows, references, [r['release'] for r in recipe['releases']]),
                   'target_values_released': False, 'rationales_released': False, 'excerpts_released': False,
                   'human_alignment_results': None, 'recipe_sha256': sha(recipe_raw),
                   'limitations': ['Repeated releases, source labels, raters, texts and pairs are not independent works or participants',
                                   'Unknown fields and raw outcomes remain sealed; no fuzzy joins, normalization, vote transfer or majority selection',
                                   'Catalogue writer/original fields are source-grounded; released root shape is unverified and only exact writer-target/original hash matches establish metadata links',
                                   'This audit does not freeze candidates, partition or authorize target opening']}
        private = {'rows': rows, 'references': references}
        write(output / 'private-metadata.json', canonical(private))
        write(output / 'summary.json', canonical(summary))
        write(output / 'terminal.json', canonical({'state': 'completed_blinded_projection',
              'summary_sha256': sha(canonical(summary)), 'private_metadata_sha256': sha(canonical(private)),
              'target_opening_authorized': False}))
        return summary
    except Exception as exc:
        write(output / 'terminal.json', canonical({'state': 'failed_preserved', 'error_class': type(exc).__name__,
              'source_locator': current, 'completed_sources': len(receipts), 'error': 'Source ingest or projection failed; sealed prefix retained'}))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, help='Provider-free exact-byte replay; missing sources fail')
    parser.add_argument('--cache-root', type=Path, action='append', default=[], help='Reuse exact pinned blobs, including a v1 sealed-source root')
    args = parser.parse_args()
    summary = run(args.private_output, args.source_root, args.cache_root)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
