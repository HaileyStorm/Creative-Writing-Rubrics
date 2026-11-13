"""Count both-covered matched cells using retained private evidence."""
import hashlib
import ast
import json
import math
from pathlib import Path

def main():
    root = Path(__file__).resolve().parents[2]
    published = root / 'evaluation-results/hbq-human-alignment-optimizer-v4-grok-sol-readout-v1'
    raw = (published / 'result-33-pairs.json').read_bytes()
    if not hashlib.sha256(raw).hexdigest() == '3ef7ea2ff8f95484d925f439e0b8e123f2c671d2d4835577bc049abc1bb301ba':
        raise ValueError('projection validation failed at source line 12')
    public = json.loads(raw)
    source = (published / 'compare.py').read_bytes()
    if hashlib.sha256(source).hexdigest() != public['inputs']['analyzer_sha256']:
        raise ValueError('comparison source hash mismatch')
    constants = {}
    for statement in ast.parse(source).body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name) and target.id in ('SOL_SUCCESS_ROOTS', 'DIMENSIONS'):
                    if target.id in constants:
                        raise ValueError('duplicate source constant')
                    constants[target.id] = ast.literal_eval(statement.value)
    if set(constants) != {'SOL_SUCCESS_ROOTS', 'DIMENSIONS'}:
        raise ValueError('missing source constants')
    roots = dict(constants['SOL_SUCCESS_ROOTS'])
    dimensions = tuple(constants['DIMENSIONS'])
    documents = Path.home() / 'Documents'
    scores = []
    contact_ids, session_ids = set(), set()
    identity_fields = ('provider', 'requested_model', 'effective_model', 'provider_reported_model',
                       'requested_reasoning_effort', 'reasoning_attested', 'route_name',
                       'transport_identity', 'identity_evidence')
    for row in public['pairs']:
        sid, gid = (row['sol_cell_id'], row['grok_cell_id'])
        sol_root = documents / roots[sid] / sid
        grok_root = documents / f'cwr-hanna-v4-native-observations-f22bf26-{gid}' / gid
        proof_path = documents / f'cwr-hanna-v4-native-admission-proof-f22bf26-{gid}.json'
        sr = json.loads((sol_root / 'execution-receipt.json').read_bytes())
        gp = json.loads(proof_path.read_bytes())
        sol_raw = (sol_root / 'raw-codex-final-response.bin').read_bytes()
        grok_raw = (grok_root / 'native-response.bin').read_bytes()
        if not (sr['cell_id'] == sid and gp['cell_id'] == gid):
            raise ValueError('projection validation failed at source line 31')
        if not sr['request_sha256'] == gp['native_request_sha256'] == row['prompt_sha256']:
            raise ValueError('projection validation failed at source line 32')
        if not sr['response_schema_sha256'] == public['response_schema_sha256']:
            raise ValueError('projection validation failed at source line 33')
        result_raw = (grok_root / 'result.json').read_bytes()
        result_data = json.loads(result_raw)
        if not hashlib.sha256(result_raw).hexdigest() == gp['destination_result_sha256']:
            raise ValueError('projection validation failed at source line 36')
        if not result_data['native_request_sha256'] == row['prompt_sha256']:
            raise ValueError('projection validation failed at source line 37')
        if not result_data['native_response_sha256'] == gp['native_response_sha256']:
            raise ValueError('projection validation failed at source line 38')
        if not (gp['deduplication_key']['cell_id'] == gid and gp['deduplication_key']['native_request_sha256'] == row['prompt_sha256'] and (gp['deduplication_key']['native_response_sha256'] == gp['native_response_sha256'])):
            raise ValueError('projection validation failed at source line 39')
        if not hashlib.sha256(sol_raw).hexdigest() == sr['final_response_sha256']:
            raise ValueError('projection validation failed at source line 40')
        if not hashlib.sha256(grok_raw).hexdigest() == gp['native_response_sha256']:
            raise ValueError('projection validation failed at source line 41')
        identity = result_data['identity']
        envelope = json.loads(grok_raw)
        if result_data['cell_id'] != gid or result_data['identity_sha256'] != gp['source_identity_sha256']:
            raise ValueError('Grok result identity binding mismatch')
        expected_key = {'cell_id': gid, 'contact_id': identity['contact_id'],
                        'session_id': identity['session_id'], 'native_request_sha256': row['prompt_sha256'],
                        'native_response_sha256': hashlib.sha256(grok_raw).hexdigest()}
        if gp['deduplication_key'] != expected_key or envelope['sessionId'] != identity['session_id'] or envelope['requestId'] != identity['contact_id']:
            raise ValueError('Grok contact or session binding mismatch')
        if identity['contact_id'] in contact_ids or identity['session_id'] in session_ids:
            raise ValueError('Grok contact or session reused')
        contact_ids.add(identity['contact_id'])
        session_ids.add(identity['session_id'])
        if ({f: identity[f] for f in identity_fields} != public['endpoint_identities']['grok'] or
                {f: sr['identity'][f] for f in identity_fields} != public['endpoint_identities']['sol']):
            raise ValueError('endpoint identity mismatch')
        sol, grok = (json.loads(sol_raw), json.loads(grok_raw)['structuredOutput'])
        if not set(sol['scores']) == set(grok['scores']) == set(dimensions):
            raise ValueError('projection validation failed at source line 43')
        if not set(grok['coverage']) == set(sol['coverage']) == set(dimensions):
            raise ValueError('projection validation failed at source line 44')
        if not all((type(grok['coverage'][d]) is bool and type(sol['coverage'][d]) is bool for d in dimensions)):
            raise ValueError('projection validation failed at source line 45')
        if not {d for d in dimensions if not grok['coverage'][d]} == set(row['uncovered_dimensions']):
            raise ValueError('projection validation failed at source line 46')
        for d in dimensions:
            a, b = (grok['scores'][d], sol['scores'][d])
            if not all((isinstance(v, (int, float)) and (not isinstance(v, bool)) and math.isfinite(v) and (0 <= v <= 5) for v in (a, b))):
                raise ValueError('projection validation failed at source line 49')
            if not round(abs(float(a) - float(b)), 4) == row['absolute_difference'][d]:
                raise ValueError('projection validation failed at source line 50')
        scores.append({'item': row['item_id'], 'candidate': row['candidate_id'], 'covered': {d for d in dimensions if grok['coverage'][d] and sol['coverage'][d]}, 'grok': grok['scores'], 'sol': sol['scores']})
    if not (len(scores) == 33 and len({(r['item'], r['candidate']) for r in scores}) == 33):
        raise ValueError('projection validation failed at source line 54')
    if not len({r['item'] for r in scores}) == 7:
        raise ValueError('projection validation failed at source line 55')
    complete = sum(len(row['covered']) == len(dimensions) for row in scores)
    covered = sum(len(row['covered']) for row in scores)
    if covered != 164 or complete != 16:
        raise ValueError('coverage totals do not match retained observations')
    output = {'policy': 'both_endpoint_coverage_summary_v1',
              'source_sha256': hashlib.sha256(raw).hexdigest(),
              'pairs': len(scores), 'item_clusters': 7, 'dimensions_per_pair': len(dimensions),
              'both_covered_dimensions': covered, 'both_complete_pairs': complete,
              'score_scale': {'minimum': 0, 'maximum': 5, 'units': 'score points'},
              'limitations': 'Post-result summary of selected historical observations. Full historical admission was not rerun. Uncovered dimensions are excluded, not imputed. Pairs share seven items; Sol native contact cardinality is unproven. No human alignment, reliability, provider ranking or generalization follows.'}
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))

if __name__ == '__main__':
    main()
