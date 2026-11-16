"""Compare V13 raw and calibrated within-prompt directions without provider calls."""
import argparse
import ast
from collections import Counter, defaultdict
from fractions import Fraction
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path

PINS = {'schedule': '2d66a311912e82f5cc1e4bb411e94493a22e6b0761da43ee6d580972a5d589db',
        'calibration': 'e3900856addc8a4385f0dc578de87ecf88ab921e20a0ab9998bfa653d430caa8',
        'public_result': 'd039289ef0054ad1448bb3d852f505e6362a182ce3adae9610a407d34f912800'}
DIMS = ('Relevance', 'Coherence', 'Empathy', 'Surprise', 'Engagement', 'Complexity')
CHILD = 'broader-nextwave-20-missing_evidence_not_no-referent-evidence'

def require(condition, message):
    if not condition:
        raise ValueError(message)

def load(path, name):
    raw = path.read_bytes()
    require(sha256(raw).hexdigest() == PINS[name], 'source digest mismatch')
    return json.loads(raw)

def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('schedule', 'calibration', 'public-result', 'response-root', 'output'):
        parser.add_argument('--' + arg, type=Path, required=True)
    args = parser.parse_args()
    schedule = load(args.schedule, 'schedule')
    saved = load(args.calibration, 'calibration')
    public = load(args.public_result, 'public_result')
    require(sha256(canonical({k: v for k, v in schedule.items() if k != 'schedule_sha256'})).hexdigest() == schedule['schedule_sha256'], 'schedule commitment mismatch')
    require(saved['input_report_sha256'] == public['source']['v13_canonical_report_sha256'] and public['source']['calibration_output_sha256'] == PINS['calibration'], 'calibration provenance mismatch')
    cells = schedule['cells']
    require(len(cells) == 88 and all(c['partition'] == 'train' and sha256(canonical(c['target'])).hexdigest() == c['target_sha256'] for c in cells), 'training inventory mismatch')
    groups = defaultdict(list)
    for cell in cells:
        if cell['candidate_id'] == CHILD:
            groups[cell['prompt_group_id']].append(cell)
    require(len(groups) == 22 and sum(map(len, groups.values())) == 44 and
            sum(len(rows) > 1 for rows in groups.values()) == 10 and
            len({c['item_id'] for rows in groups.values() for c in rows}) == 44, 'child geometry differs')
    folds = {f['heldout_prompt_group_id']: f for f in saved['folds']}
    require(len(folds) == 22 and set(folds) == set(groups), 'folds differ')
    helper = Path(__file__).resolve().parent.parent / 'hbq-matched-hanna-20261004/prepare.py'
    helper_bytes = helper.read_bytes()
    require(sha256(helper_bytes).hexdigest() == '2d82e4959c3296ccaa6e6521adb46f85588427d429a544b36a2891ebaea8c7b0', 'projection helper differs')
    tree = ast.parse(helper_bytes)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('require', 'project_json')]
    require(len(funcs) == 2, 'projection helper differs')
    env = {'json': json}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(helper), 'exec'), env)
    project = env['project_json']
    raw_scores = {}
    for group in groups.values():
        for cell in group:
            cid = cell['cell_id']
            require(cid.startswith('v13-train-') and len(cid) == 30 and all(c in '0123456789abcdef' for c in cid[10:]), 'unsafe cell ID')
            path = args.response_root / cid / 'native-response.bin'
            require(not any(node.is_symlink() or getattr(node.stat(), 'st_file_attributes', 0) & 1024 for node in (path, *path.parents)), 'unsafe response ancestry')
            before = path.stat()
            response = path.read_bytes()
            after = path.stat()
            require((before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino), 'response changed during read')
            values = project(response, {'structuredOutput': {'scores': {d: True for d in DIMS}}})['structuredOutput']['scores']
            require(all(type(x) in (int, float) and math.isfinite(x) and 0 <= x <= 5 for x in values.values()), 'invalid score')
            raw_scores[cid] = values
    counts = Counter()
    for gid, group in groups.items():
        fold = folds[gid]
        require(set(fold['fit_prompt_group_ids']) == set(groups) - {gid}, 'training fold mismatch')
        predictions = {p['cell_id']: p['scores'] for p in fold['heldout_predictions']}
        require(set(predictions) == {c['cell_id'] for c in group}, 'held-out predictions differ')
        for cell in group:
            for dim in DIMS:
                p = fold['parameters'][dim]
                require(0.1 <= p['slope'] <= 2 and -2 <= p['intercept'] <= 2, 'parameter bounds differ')
                prediction = min(5.0, max(0.0, float(p['slope']) * float(raw_scores[cell['cell_id']][dim]) + float(p['intercept'])))
                require(prediction == predictions[cell['cell_id']][dim], 'raw score does not reproduce saved prediction')
        for a, b in itertools.combinations(group, 2):
            for dim in DIMS:
                def direction(v): return (v > 0) - (v < 0)
                ref = direction(Fraction(str(a['target'][dim])) - Fraction(str(b['target'][dim])))
                orig = direction(Fraction(str(raw_scores[a['cell_id']][dim])) - Fraction(str(raw_scores[b['cell_id']][dim])))
                cal = direction(Fraction(str(predictions[a['cell_id']][dim])) - Fraction(str(predictions[b['cell_id']][dim])))
                counts['all_pair_dimension_cells'] += 1
                counts['all_changed_directions'] += orig != cal
                if not ref:
                    counts['reference_ties'] += 1
                    continue
                counts['eligible'] += 1
                for key, value in (('raw', orig), ('calibrated', cal)):
                    counts[key + ('_tie' if value == 0 else '_concordant' if value == ref else '_discordant')] += 1
    require(counts['all_pair_dimension_cells'] == 240 and counts['reference_ties'] == 37 and counts['eligible'] == 203 and counts['calibrated_tie'] == 115 and counts['calibrated_concordant'] == 57 and counts['calibrated_discordant'] == 31, 'published comparison differs')
    result = {'cohort': {'items': 44, 'prompt_groups': 22, 'multi_item_prompt_groups': 10, 'within_prompt_item_pairs': 40, 'dimensions': 6},
              'counts': dict(sorted(counts.items())), 'source_sha256': PINS,
              'limitations': ['Retrospective TRAIN-only descriptive analysis, not confirmation or population inference.',
                              'Scores from retained responses reproduce saved predictions; this is not fresh admission or a replay of the full historical report.',
                              'Pairs share items, prompts, raters and dimensions; no independence or statistical significance is claimed.'],
              'provider_calls': 0, 'new_human_labels': 0}
    encoded = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    with args.output.open('xb') as stream:
        stream.write(encoded)
    print(json.dumps({'sha256': sha256(encoded).hexdigest(), 'counts': result['counts']}))

if __name__ == '__main__':
    main()
