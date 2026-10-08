"""Four-state descriptive repeat agreement from byte-bound historical leaves."""
from __future__ import annotations

import argparse
import ast
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).absolute().parent
REPO = HERE.parents[1]
PROFILE_SHA = 'f1f62383fcdc6e9727ac51216031493a03a6a5e2d90d7a40d348ce7ed50f8b71'
STATES = ('YES', 'NO', 'NOT_APPLICABLE', 'CANNOT_ASSESS')
HBQ = 'hbq_short_story_batch32'


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def encode(value):
    if isinstance(value, Fraction): return {'numerator': value.numerator, 'denominator': value.denominator}
    raise TypeError(type(value).__name__)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False, default=encode) + '\n').encode()


def tree_canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def extract(raw, names, namespace):
    nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in names]
    require(len(nodes) == len(names) and {n.name for n in nodes} == set(names), 'Pinned function extraction differs')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'pinned-selective-read', 'exec'), namespace)
    return namespace


def metric(subjects):
    require(bool(subjects) and all(len(s) == 5 and all(v in STATES for v in s) for s in subjects), 'Complete five-state sequences required')
    marginal = Counter({s: 0 for s in STATES})
    categories = Counter({**{'stable_' + s: 0 for s in STATES},
                          'changing_with_yes_and_no': 0, 'changing_without_yes_and_no': 0})
    table = [[0] * 4 for _ in STATES]
    for labels in subjects:
        marginal.update(labels)
        unique = set(labels)
        key = ('stable_' + labels[0] if len(unique) == 1 else
               'changing_with_yes_and_no' if {'YES', 'NO'} <= unique else 'changing_without_yes_and_no')
        categories[key] += 1
        for a, b in combinations(labels, 2): table[STATES.index(a)][STATES.index(b)] += 1
    n = len(subjects); labels_n = 5 * n; pairs_n = 10 * n
    same = sum(table[i][i] for i in range(4))
    yes_no = table[0][1] + table[1][0]
    assessed_other = sum(table[a][b] + table[b][a] for a in (0, 1) for b in (2, 3))
    na_ca = table[2][3] + table[3][2]
    require(sum(marginal.values()) == labels_n and sum(map(sum, table)) == pairs_n and
            sum(categories.values()) == n and same + yes_no + assessed_other + na_ca == pairs_n,
            'Four-state count partition differs')
    observed = Fraction(same, pairs_n)
    probabilities = {s: Fraction(marginal[s], labels_n) for s in STATES}
    chance = sum(p * p for p in probabilities.values())
    kappa = (observed - chance) / (1 - chance) if chance != 1 else None
    stable = sum(categories['stable_' + s] for s in STATES)
    return {'subjects': n, 'raw_labels': labels_n, 'repeat_pairs': pairs_n, 'state_counts': dict(marginal),
        'state_fractions': probabilities, 'subject_categories': dict(categories), 'all_five_equal_subjects': stable,
        'all_five_equal_fraction': Fraction(stable, n), 'label_cross_tab': table, 'same_label_pairs': same,
        'yes_no_pairs': yes_no, 'assessed_vs_other_pairs': assessed_other, 'not_applicable_vs_cannot_assess_pairs': na_ca,
        'observed_agreement': observed, 'marginal_chance_agreement': chance, 'fleiss_form_kappa': kappa,
        'kappa_status': 'undefined_single_category_margin' if kappa is None else 'defined'}


def safe_output(output, protected_roots, plain_node):
    require(output.is_absolute() and '..' not in output.parts and not output.exists(), 'Fresh plain absolute output required')
    for path in reversed((output.parent, *output.parent.parents)):
        info = plain_node(path)
        require(stat.S_ISDIR(info.st_mode), 'Output ancestor is not a plain directory')
    require(all(root.is_absolute() and '..' not in root.parts and
                not output.is_relative_to(root) and not root.is_relative_to(output) for root in protected_roots),
            'Output overlaps retained source evidence')


def run(evidence, output):
    source_raw = Path(__file__).read_bytes()
    profile_raw = (HERE / 'profile.json').read_bytes()
    require(sha(profile_raw) == PROFILE_SHA, 'Frozen profile differs')
    profile = json.loads(profile_raw)
    require(profile['states'] == list(STATES) and profile['planned'] == {'items': 11, 'repetitions': 5, 'runs': 55,
        'question_positions_per_run': 179, 'item_question_subjects': 1969, 'raw_labels': 9845, 'repeat_index_pair_comparisons': 19690}, 'Method geometry differs')
    # Reuse only reviewed, pinned plain-path/stable-byte functions, never probe main.
    proof_raw = (evidence / 'source.py').read_bytes()
    pin = profile['evidence_pins']['source.py']
    require(len(proof_raw) == pin['bytes'] and sha(proof_raw) == pin['sha256'], 'Historical byte verifier differs')
    ns = extract(proof_raw, ('stamp', 'opened_identity', 'node', 'ancestors', 'checked'),
                 {'stat': stat, 'os': os, 'Path': Path, 'require': require, 'sha': sha})
    checked = ns['checked']
    raw_evidence = {name: checked(evidence / name, pin) for name, pin in profile['evidence_pins'].items()}
    reader_pin = profile['lexical_reader_pin']
    reader = checked(REPO / reader_pin['locator'], reader_pin)
    project = extract(reader, ('require', 'project_json'), {'json': json})['project_json']
    contract_pin = profile['contract_pin']
    contract = json.loads(checked(REPO / contract_pin['locator'], contract_pin))
    require(contract['study_id'] == 'hbq-multisample-repeatability-v1' and contract['repetitions'] == 5 and
            next(a for a in contract['arms'] if a['arm_id'] == HBQ)['question_count'] == 179, 'Historical question contract differs')
    selection = json.loads(raw_evidence['selected-cells.json'])
    descriptors = json.loads(raw_evidence['verified-tree-descriptors.json'])
    terminal = json.loads(raw_evidence['terminal.json'])
    require(terminal['status'] == 'verified_historical_bytes' and terminal['verified_cells'] == 55 and
            terminal['selected_cells_sha256'] == sha(raw_evidence['selected-cells.json']) and
            terminal['private_descriptors_sha256'] == sha(raw_evidence['verified-tree-descriptors.json']), 'Historical qualification receipt differs')
    cells = selection['cells']; cohorts = selection['cohorts']
    require(len(cells) == len(descriptors) == 55 and [d['cell'] for d in descriptors] == cells,
            'Exact qualified descriptor cells differ')
    protected = {REPO, evidence.absolute(), *(Path(c['source_root']) for c in cells),
                 *(Path(c['run_binding_path']).parent for c in cells)}
    safe_output(output, protected, ns['node'])
    items = set()
    for name, pin in profile['cohorts'].items():
        group = sorted(cohorts[name])
        require(len(group) == len(set(group)) == pin['items'] and sha(canonical(group)) == pin['membership_sha256'] and
                items.isdisjoint(group), 'Qualified cohort partition differs')
        items.update(group)
    require(set(cohorts) == set(profile['cohorts']) and len(items) == 11 and
            {(c['item_id'], c['repetition']) for c in cells} == {(i, r) for i in items for r in range(1, 6)} and
            all(c['arm_id'] == HBQ for c in cells) and len({c['run_binding_path'] for c in cells}) == 55, 'Registered HBQ run grid differs')
    frozen = []
    for entry in descriptors:
        cell = entry['cell']; records = entry['records']
        require(sha(tree_canonical(records)) == cell['run_tree_sha256'], 'Saved complete tree commitment differs')
        by_name = {r['path']: r for r in records}
        require(len(by_name) == len(records) and by_name['verdicts.jsonl'] == entry['verdict_file'] and
                by_name['run.json']['sha256'] == cell['run_binding_sha256'], 'Saved exact verdict/run descriptor differs')
        binding = Path(cell['run_binding_path']); root = Path(cell['source_root'])
        require(binding == root / 'runs' / cell['item_id'] / HBQ / f"run-{cell['repetition']:02d}" / 'run.json', 'Exact binding geometry differs')
        manifest_raw = checked(binding, by_name['run.json'])
        verdict_raw = checked(binding.parent / 'verdicts.jsonl', by_name['verdicts.jsonl'])
        require(verdict_raw.endswith(b'\n'), 'Partial verdict JSONL tail')
        frozen.append((cell, manifest_raw, verdict_raw))
    # All110 registered files are verified before any manifest/label projection.
    by_item = {i: {} for i in items}; orders = {}; commitments = []
    for cell, manifest_raw, verdict_raw in frozen:
        qids = project(manifest_raw, {'configuration': {'question_ids': True}})['configuration']['question_ids']
        require(isinstance(qids, list) and len(qids) == len(set(qids)) == 179 and
                all(isinstance(q, str) and bool(q) for q in qids), '179 unique manifest question positions required')
        lines = verdict_raw.splitlines()
        require(len(lines) == 179 and all(line.strip() for line in lines), 'Complete 179-row verdict file required')
        rows = [project(line, {'question_id': True, 'verdict': True}) for line in lines]
        require([r['question_id'] for r in rows] == qids and all(r['verdict'] in STATES for r in rows), 'Bound question order or four-state label differs')
        item = cell['item_id']; repetition = cell['repetition']
        require(item not in orders or orders[item] == qids, 'Question positions change across repeated runs')
        orders[item] = qids; by_item[item][repetition] = [r['verdict'] for r in rows]
        commitments.append({'item_id': item, 'repetition': repetition, 'run_sha256': sha(manifest_raw),
                            'verdict_sha256': sha(verdict_raw), 'question_order_sha256': sha(canonical(qids))})
    subjects = {i: list(zip(*(by_item[i][r] for r in range(1, 6)), strict=True)) for i in items}
    rows = []; private = []
    for name, group in cohorts.items():
        group = sorted(group); all_subjects = [s for item in group for s in subjects[item]]
        metrics = metric(all_subjects); per_item = []
        for ordinal, item in enumerate(group, 1):
            per_item.append({'ordinal': ordinal, **metric(subjects[item])})
            private.append({'cohort': name, 'ordinal': ordinal, 'item_id': item, 'question_ids': orders[item],
                            'labels_by_question': subjects[item]})
        require(metrics['subjects'] == len(group) * 179 and metrics['observed_agreement'] ==
                sum(r['observed_agreement'] for r in per_item) / len(group), 'Equal-item observed agreement differs')
        rows.append({'cohort': name, 'items': len(group), 'prompt_groups': profile['cohorts'][name]['prompt_groups'],
            'repetitions': 5, 'question_positions_per_item': 179, 'metrics': metrics, 'per_item': per_item})
    require(sum(r['metrics']['raw_labels'] for r in rows) == 9845 and
            sum(r['metrics']['repeat_pairs'] for r in rows) == 19690, 'Full prespecified denominators differ')
    require(Path(__file__).read_bytes() == source_raw, 'Analysis source changed during projection')
    report = {'schema_version': 1, 'policy': profile['policy'], 'source_sha256': sha(source_raw),
        'profile_sha256': PROFILE_SHA, 'evidence_pins': profile['evidence_pins'], 'cohort_commitments': profile['cohorts'],
        'planned': profile['planned'], 'available_runs': 55, 'missing_runs': 0, 'states': list(STATES), 'rows': rows,
        'historical_requested_provider': {k: contract['provider'][k] for k in ('provider', 'model', 'reasoning')},
        'method': profile['agreement'], 'transition_table': profile['transition_table'], 'interpretation': profile['interpretation'],
        'provider_calls': 0, 'human_targets_materialized': False, 'native_admission_replayed': False,
        'current_tools_disabled_qualification': False, 'interendpoint_measured': False, 'promotion': False}
    return report, {'items': private, 'run_commitments': commitments}, protected, ns['node'], source_raw


def create(path, raw):
    with path.open('xb') as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    require(path.read_bytes() == raw, 'Output readback differs')


def main():
    parser = argparse.ArgumentParser()
    for flag in ('evidence-root', 'output'): parser.add_argument('--' + flag, required=True, type=Path)
    args = parser.parse_args()
    require('..' not in args.output.parts and '..' not in args.evidence_root.parts, 'Traversing input/output locator')
    output = args.output.absolute(); evidence = args.evidence_root.absolute()
    report, private, protected, plain_node, source_raw = run(evidence, output)
    safe_output(output, protected, plain_node)
    require(Path(__file__).read_bytes() == source_raw, 'Analysis source changed before publication')
    output.mkdir(); create(output / 'report.json', canonical(report)); create(output / 'private-labels.json', canonical(private))
    print(json.dumps({'report_sha256': sha(canonical(report)), 'private_labels_sha256': sha(canonical(private)),
                      'runs': 55, 'raw_labels': 9845, 'cohort_rows': len(report['rows'])}))


if __name__ == '__main__': main()
