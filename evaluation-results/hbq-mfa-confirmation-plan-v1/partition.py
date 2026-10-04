"""Outcome-blind, component-preserving MFA partition design candidate."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
_spec = importlib.util.spec_from_file_location('mfa_partition_seal', HERE.parent / 'hbq-mfa-metadata-seal-v2' / 'project.py')
seal = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seal)
canonical, sha = seal.canonical, seal.sha
POLICY = 'mfa_outcome_blind_component_partition_v1'


def load_inputs(source):
    """Read only the three whitelisted metadata/commitment files, once each."""
    source = Path(source).resolve()
    raw = {name: (source / name).read_bytes() for name in
           ('private-metadata.json', 'summary.json', 'source-recipe.json')}
    metadata, summary, recipe = (json.loads(raw[name]) for name in raw)
    if sha(canonical(recipe)) != seal.RECIPE_SHA256:
        raise ValueError('Pinned canonical recipe digest mismatch')
    if summary.get('policy') != seal.POLICY or summary.get('recipe_sha256') != sha(raw['source-recipe.json']):
        raise ValueError('Source summary policy or recipe file SHA256 mismatch')
    if any(summary.get(key) is not False for key in
           ('target_values_released', 'rationales_released', 'excerpts_released')):
        raise ValueError('Source summary is not a blinded metadata seal')
    if summary.get('human_alignment_results') is not None:
        raise ValueError('Source summary contains alignment results')
    if set(metadata) != {'rows', 'references'} or not metadata['rows']:
        raise ValueError('Missing metadata rows/references')
    releases = [r['release'] for r in recipe['releases']]
    if summary.get('cohort') != seal.aggregate(metadata['rows'], metadata['references'], releases):
        raise ValueError('Private metadata differs from source cohort commitment')
    receipts = summary.get('source_receipts', [])
    expected = [(release, item) for release in recipe['releases'] for item in release['sources']]
    if len(receipts) != len(expected):
        raise ValueError('Missing source metadata receipts')
    for receipt, (release, (path, blob, size, kind)) in zip(receipts, expected):
        binding = {'release': release['release'], 'repository': release['repository'],
                   'revision': release['revision'], 'path': path, 'git_blob_sha1': blob,
                   'bytes': size, 'kind': kind}
        if any(receipt.get(k) != v for k, v in binding.items()):
            raise ValueError('Source receipt differs from pinned recipe')
        part = [r for r in metadata['rows' if kind == 'outcomes' else 'references']
                if r['release'] == release['release'] and r['source_path'] == path]
        if receipt.get('metadata_rows') != len(part) or receipt.get('metadata_sha256') != sha(canonical(part)):
            raise ValueError('Source receipt metadata commitment mismatch')
    for kind, field in [('outcomes', 'rows'), ('references', 'references')]:
        if sum(r['metadata_rows'] for r in receipts if r['kind'] == kind) != len(metadata[field]):
            raise ValueError('Metadata records are not fully covered by source receipts')
    commitments = {name.replace('.json', '').replace('-', '_') + '_file_sha256': sha(value)
                   for name, value in raw.items()}
    commitments['recipe_canonical_json_lf_sha256'] = sha(canonical(recipe))
    commitments['metadata_canonical_json_lf_sha256'] = sha(canonical(metadata))
    return metadata, commitments


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def design(metadata, *, exposure=None, development_targets=20, confirmation_targets=30,
           development_fine_targets=12, confirmation_fine_targets=18):
    rows, references = metadata['rows'], metadata['references']
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in
           (development_targets, confirmation_targets, development_fine_targets, confirmation_fine_targets)):
        raise ValueError('Partition counts must be nonnegative integers')
    targets = sorted({r['target_hash'] for r in rows if r.get('target_hash') is not None})
    if not targets or any(not _hash(r.get('target_hash')) or len(r.get('excerpt_hashes', [])) != 2
                          or not all(_hash(h) for h in r['excerpt_hashes'])
                          or (r.get('original_hash') is not None and not _hash(r['original_hash'])) for r in rows):
        raise ValueError('Missing target identity or exact text hashes')
    parent = {t: t for t in targets}
    def find(t):
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t
    def join(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)
    texts = defaultdict(set)
    pairs = defaultdict(set)
    for row in rows:
        target = row['target_hash']
        texts[target].update(row['excerpt_hashes'])
        if row.get('original_hash') is not None:
            texts[target].add(row['original_hash'])
        pairs[target].add(tuple(sorted(row['excerpt_hashes'])))
    for reference in references:
        if reference.get('writer_hash') in parent and reference.get('original_hash') is not None:
            if not _hash(reference['original_hash']):
                raise ValueError('Invalid catalogue text hash')
            texts[reference['writer_hash']].add(reference['original_hash'])
    owners = {}
    for target in targets:
        for text in sorted(texts[target]):
            if text in owners:
                join(target, owners[text])
            else:
                owners[text] = target
    groups = defaultdict(list)
    for target in targets:
        groups[find(target)].append(target)
    components = sorted(groups.values(), key=lambda members: tuple(members))
    exposure = {} if exposure is None else exposure
    if not isinstance(exposure, dict) or set(exposure) - {'target_hashes', 'text_hashes', 'audit_complete'}:
        raise ValueError('Exposure metadata accepts only target_hashes, text_hashes, audit_complete')
    exposed_targets, exposed_texts = (set(exposure.get(k, [])) for k in ('target_hashes', 'text_hashes'))
    if not all(_hash(h) for h in exposed_targets | exposed_texts) or not isinstance(exposure.get('audit_complete', False), bool):
        raise ValueError('Exposure identifiers must be exact SHA256 hashes')
    forced = {i for i, members in enumerate(components) if exposed_targets.intersection(members)
              or any(exposed_texts.intersection(texts[t]) for t in members)}
    fine = {r['target_hash'] for r in rows if r['release'] == 'author-style' and r['condition'] == 'finetuned'}
    weights = [(len(members), len(set(members) & fine)) for members in components]
    start = tuple(sum(weights[i][j] for i in forced) for j in (0, 1))
    states = {start: tuple(sorted(forced))} if start[0] <= development_targets and start[1] <= development_fine_targets else {}
    # At most (development_targets+1)*(development_fine_targets+1) states.
    for i, (count, fine_count) in enumerate(weights):
        if i in forced:
            continue
        for (n, f), selected in list(states.items()):
            key = n + count, f + fine_count
            if key[0] <= development_targets and key[1] <= development_fine_targets:
                states.setdefault(key, selected + (i,))
    chosen = states.get((development_targets, development_fine_targets))
    pending = []
    if len(targets) != development_targets + confirmation_targets:
        pending.append('Nominal total target count differs from observed target count')
    if len(fine) != development_fine_targets + confirmation_fine_targets:
        pending.append('Nominal total fine target count differs from observed primary fine target count')
    if chosen is None:
        pending.append('No whole-component assignment satisfies development counts and exposure constraints')
    assignment = {} if pending else {t: 'development' if i in chosen else 'confirmation'
                                    for i, members in enumerate(components) for t in members}
    component_ledger = [{'component_sha256': sha(canonical(members)), 'target_hashes': members,
                         'text_hashes': sorted({h for t in members for h in texts[t]}),
                         'forced_development': i in forced,
                         'partition': assignment.get(members[0], 'unassigned')}
                        for i, members in enumerate(components)]
    units = {}
    denominators = defaultdict(list)
    catalogue = defaultdict(set)
    for ref in references:
        catalogue[(ref['release'], ref.get('writer_hash'))].add(ref.get('original_hash'))
    for row in rows:
        partition = assignment.get(row['target_hash'], 'unassigned')
        scope = (partition, row['release'], row['task'], row['panel'], row['condition'])
        denominators[scope].append(row)
        style = row['task'] == 'style'
        original = row.get('original_hash') if style else None
        eligible = not style or (row.get('original_present') is True and row.get('original_is_text') is True and original is not None)
        identity = {'release': row['release'], 'task': row['task'], 'panel': row['panel'],
                    'condition': row['condition'], 'target_hash': row['target_hash'],
                    'candidate_excerpt_hashes': sorted(row['excerpt_hashes']), 'row_original_hash': original}
        unit_hash = sha(canonical(identity))
        unit = units.setdefault(unit_hash, {**identity, 'unit_sha256': unit_hash, 'partition': partition,
                                    'eligible': eligible, 'rows': 0,
                                    'row_memberships': [],
                                    'catalogue_reference_match': bool(style and original is not None and original in catalogue[(row['release'], row['target_hash'])])})
        unit['rows'] += 1
        unit['row_memberships'].append({'metadata_row_sha256': sha(canonical(row)),
                                        'writer_hash': row.get('writer_hash'),
                                        'ordered_pair_hash': row['ordered_pair_hash']})
    counts = []
    for scope, selected in sorted(denominators.items()):
        scoped_units = [u for u in units.values() if (u['partition'], u['release'], u['task'], u['panel'], u['condition']) == scope]
        counts.append(dict(zip(('partition', 'release', 'task', 'panel', 'condition'), scope),
                           **seal.count_geometry(selected), evaluation_units=len(scoped_units),
                           eligible_units=sum(u['eligible'] for u in scoped_units),
                           ineligible_units=sum(not u['eligible'] for u in scoped_units),
                           present_style_reference_catalogue_mismatch_units=sum(u['task'] == 'style' and u['eligible'] and not u['catalogue_reference_match'] for u in scoped_units)))
    intersections = {}
    for name, mapping in [('target', {t: {t} for t in targets}), ('text', texts), ('candidate_pair', pairs)]:
        sides = [{v for t in targets if assignment.get(t) == side for v in mapping[t]}
                 for side in ('development', 'confirmation')]
        intersections[name + '_crosspartition_count'] = len(sides[0] & sides[1]) if assignment else None
    if assignment and any(intersections.values()):
        raise ValueError('Crosspartition invariant failed')
    unmatched = len(exposed_targets - set(targets)) + len(exposed_texts - set(owners))
    ledger = {'policy': POLICY, 'components': component_ledger, 'evaluation_units': sorted(units.values(), key=lambda u: u['unit_sha256'])}
    summary = {'policy': POLICY, 'state': 'pending_design_decision' if pending else 'partition_design_candidate',
               'pending_decisions': pending, 'primary_release': 'author-style', 'sensitivity_release': 'good-writing',
               'target_count': len(targets), 'fine_target_count': len(fine), 'component_count': len(components),
               'partition_target_counts': {side: sum(assignment.get(t) == side for t in targets)
                                           for side in ('development', 'confirmation', 'unassigned')}
                   if assignment else {'development': 0, 'confirmation': 0, 'unassigned': len(targets)},
               'partition_fine_target_counts': {side: sum(assignment.get(t) == side for t in fine)
                                                for side in ('development', 'confirmation', 'unassigned')}
                   if assignment else {'development': 0, 'confirmation': 0, 'unassigned': len(fine)},
               'component_target_count_histogram': dict(sorted(Counter(len(c) for c in components).items())),
               'forced_development_component_count': len(forced),
               'requested_counts': {'development_targets': development_targets, 'confirmation_targets': confirmation_targets,
                                    'development_fine_targets': development_fine_targets, 'confirmation_fine_targets': confirmation_fine_targets},
               'exposure_audit': {'status': 'supplied_complete' if exposure.get('audit_complete') is True and (exposed_targets or exposed_texts) and not unmatched else 'incomplete',
                                  'declared_targets': len(exposed_targets), 'declared_texts': len(exposed_texts), 'unmatched_identifiers': unmatched,
                                  'unused_data_certified': False},
               'crosspartition_checks': intersections, 'denominators': counts,
               'unassigned_catalogue_reference_records': sum(r.get('writer_hash') not in parent for r in references),
               'private_membership_ledger_sha256': sha(canonical(ledger)),
               'candidate_scoring_frozen': False, 'target_opening_authorized': False, 'provider_contact_authorized': False,
               'limitations': ['Metadata label hashes do not establish independent authors, works or raters',
                               'Public/pretraining exposure remains unknown; empty exposure input is an incomplete audit',
                               'Present row references remain distinct from catalogue references; no votes transferred',
                               'GoodWriting is related-release sensitivity only; no independent cohort claim']}
    return summary, ledger


def validate_output(output, source, exposure_path=None):
    output = Path(output).resolve()
    for root in [REPO, Path(source).resolve()] + ([Path(exposure_path).resolve()] if exposure_path else []):
        if output == root or output.is_relative_to(root) or root.is_relative_to(output):
            raise ValueError('Fresh private output must be outside repository and input paths')
    if output.exists():
        raise ValueError('Private output must not exist')
    return output


def run(source, output, *, exposure_path=None, dry_run=False, **counts):
    output = validate_output(output, source, exposure_path)
    metadata, commitments = load_inputs(source)
    exposure_raw = Path(exposure_path).read_bytes() if exposure_path else None
    exposure = json.loads(exposure_raw) if exposure_raw is not None else None
    summary, ledger = design(metadata, exposure=exposure, **counts)
    summary['source_commitments'] = commitments
    summary['exposure_metadata_file_sha256'] = sha(exposure_raw) if exposure_raw is not None else None
    summary['implementation_file_sha256'] = sha(Path(__file__).read_bytes())
    if not dry_run:
        output.mkdir(parents=True, exist_ok=False)
        seal.write(output / 'private-membership.json', canonical(ledger))
        seal.write(output / 'summary.json', canonical(summary))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--private-output', required=True, type=Path)
    parser.add_argument('--exposure-metadata', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(canonical(run(args.source_root, args.private_output, exposure_path=args.exposure_metadata, dry_run=args.dry_run)).decode(), end='')


if __name__ == '__main__':
    main()
