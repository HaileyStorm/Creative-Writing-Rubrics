"""Exhaustively compare one synthetic ladder's binary completions to its bounds."""
import hashlib
import itertools
import json
from pathlib import Path

from hbqrs import core, ladder_uncertainty
from hbqrs.paths import bundles_path, registry_path

root = Path(__file__).resolve().parents[2]
source = root / 'evaluation-results/hbq-scorer-verdict-influence-v1/aggregate.json'
raw = source.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'b0b15150b835e1b6d291429db286eb9f08b0ab4544a31fceccf0dc583b75cfcc'
data = json.loads(raw)
modules = core.load_modules(registry_path())
bundle = core.resolve_bundle(core.load_bundles(bundles_path()), 'prose.short_story')
ids = ('core.holistic_artistic_success.threshold_1_functional',
       'core.holistic_artistic_success.threshold_2_effective',
       'core.holistic_artistic_success.threshold_3_keepworthy',
       'core.holistic_artistic_success.threshold_4_exceptional')
states = ('YES', 'NO', 'CANNOT_ASSESS', 'NOT_APPLICABLE')
summary = []
for bank in ('synthetic_A', 'synthetic_B'):
    base = [{'question_id': leaf['question_id'], 'verdict': leaf['raw_before']}
            for leaf in data['leaf_simulations'] if leaf['bank'] == bank]
    assert len(base) == 178 and all(sum(r['question_id'] == q for r in base) == 1 for q in ids)
    total = 0
    violations = []
    for configuration in itertools.product(states, repeat=4):
        selected = dict(zip(ids, configuration))
        rows = [{**r, 'verdict': selected.get(r['question_id'], r['verdict'])} for r in base]
        interval = ladder_uncertainty.score_bundle(modules, bundle, rows, admission_policy='historical_permissive_v1')['candidate_report']['final_score']
        unknown = [q for q in ids if selected[q] == 'CANNOT_ASSESS']
        for completion in itertools.product(('YES', 'NO'), repeat=len(unknown)):
            choice = dict(zip(unknown, completion))
            resolved = [{**r, 'verdict': choice.get(r['question_id'], r['verdict'])} for r in rows]
            score = ladder_uncertainty.score_bundle(modules, bundle, resolved, admission_policy='historical_permissive_v1')['candidate_report']['final_score']['observed']
            total += 1
            if score is None or interval['lower'] is None or interval['upper'] is None or not interval['lower'] <= score <= interval['upper']:
                violations.append({'configuration': selected, 'completion': choice, 'interval': interval, 'score': score})
    summary.append({'bank': bank, 'configurations': 256, 'binary_completions': total, 'violations': violations})
paths = ('src/hbqrs/core.py', 'src/hbqrs/scoring_v2.py', 'src/hbqrs/ladder_uncertainty.py',
         'registry/all_modules.json', 'bundles/all_bundles.json', 'bundles/prose.short_story.yaml')
result = {'source_sha256': hashlib.sha256(raw).hexdigest(),
          'source_code_sha256': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
          'ladder': ids, 'states': states, 'results': summary,
          'scope': 'Post-result synthetic analysis of all 256 states of one four-level ladder in each of two fixed short-story banks, resolving only CANNOT_ASSESS to YES/NO, keeping all other verdicts and NOT_APPLICABLE fixed. This is not a general proof, a human-validity study, or a promotion gate.'}
print(json.dumps(result, indent=2, sort_keys=True))
