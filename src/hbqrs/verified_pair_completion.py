"""Finite completion analysis for locally verified binary-run pairs.

Stable trusted files are required throughout. This is a scorer-only envelope,
not authenticated provider execution, review, or human preference.
"""
from copy import deepcopy
import hashlib
from pathlib import Path

from . import completion_readiness, core, run_verify, runner
from .verified_pair_comparison import compare_verified_binary_runs
from .weights import materialize_weight_profile


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_side(run, frozen, expected_run_sha, expected_score_sha, max_cases):
    frozen = deepcopy(dict(frozen))
    run = Path(run).resolve()
    verified = run_verify.verify_binary_run(run, frozen)
    if verified['run_sha256'] != expected_run_sha or verified['score_v2_sha256'] != expected_score_sha:
        raise core.HBQError('Run changed between pair and completion verification')
    manifest = run_verify._json(run / 'run.json')
    if _sha(run / 'run.json') != expected_run_sha:
        raise core.HBQError('Run manifest changed')
    verdict_path = run / 'verdicts.jsonl'
    verdict_sha = verified['commitments']['verdicts']['sha256']
    if _sha(verdict_path) != verdict_sha:
        raise core.HBQError('Verdict bank changed')
    verdicts = core.load_verdicts(verdict_path)
    if _sha(verdict_path) != verdict_sha:
        raise core.HBQError('Verdict bank changed')
    registry = run_verify._bound_file(frozen['registry'], label='registry')
    bundles = run_verify._bound_file(frozen['bundles'], label='bundles')
    task_path = run_verify._bound_file(frozen['task_contract'], label='task contract')
    modules = core.load_modules(registry)
    bundle = core.resolve_bundle(core.load_bundles(bundles), frozen['execution']['bundle_id'])
    modules, bundle, weight_audit = materialize_weight_profile(modules, bundle, frozen.get('weight_profile'))
    task = core.load_data(task_path)
    compiled = core.compile_bundle(modules, bundle, task_contract=task)
    if hashlib.sha256(runner._json_bytes(compiled)).hexdigest() != manifest['configuration']['compiled_bundle_sha256']:
        raise core.HBQError('Compiled scoring inputs differ from verified run')
    for name in ('registry', 'bundles', 'task_contract'):
        run_verify._bound_file(frozen[name], label=name)
    out = completion_readiness.readiness(modules, bundle, verdicts,
        artifact_id=frozen['execution']['artifact_id'], task_contract=task,
        admission_policy='strict_import_v3', max_cases=max_cases)
    historical = deepcopy(out['historical_report'])
    historical['weight_profile'] = weight_audit
    if (_sha(run / 'score.json') != verified['score_sha256']
            or run_verify._json(run / 'score.json') != historical
            or _sha(run / 'score.json') != verified['score_sha256']):
        raise core.HBQError('Completion analysis does not reproduce the verified historical score')
    for name in ('registry', 'bundles', 'task_contract'):
        run_verify._bound_file(frozen[name], label=name)
    if (_sha(verdict_path) != verdict_sha or _sha(run / 'run.json') != expected_run_sha
            or _sha(run / 'score.v2.json') != expected_score_sha):
        raise core.HBQError('Run changed during completion analysis')
    return out['completion_readiness'], out['completion_envelope']


def compare_verified_completion_runs(left_run, left_frozen, right_run, right_frozen, *, max_cases=243):
    """Compare finite completion envelopes under verified shared conditions.

    The cap applies separately to each bank. Strict import admission is required;
    unsupported inputs raise and non-scored or over-limit completions withhold
    the relation. Files must remain stable and trusted throughout the call.
    """
    if type(max_cases) is not int or not 1 <= max_cases <= completion_readiness.MAX_CASES:
        raise ValueError('max_cases outside supported range')
    base = compare_verified_binary_runs(left_run, left_frozen, right_run, right_frozen)
    if base['relation'] in ('INELIGIBLE', 'INCOMPARABLE'):
        return {'historical': base, 'completion': {'policy': 'verified_binary_pair_completion_v1',
                'relation': base['relation'], 'reason': base['reason']}}
    left, left_detail = _read_side(left_run, left_frozen, base['left_run_sha256'], base['left_score_sha256'], max_cases)
    right, right_detail = _read_side(right_run, right_frozen, base['right_run_sha256'], base['right_score_sha256'], max_cases)
    if left['status'] != 'AVAILABLE' or right['status'] != 'AVAILABLE':
        relation, reason = 'UNAVAILABLE', 'one_or_both_completion_readiness_unavailable'
    elif left['bounds']['lower'] > right['bounds']['upper']:
        relation, reason = 'LEFT_ABOVE', 'strictly_separated_completion_ranges'
    elif right['bounds']['lower'] > left['bounds']['upper']:
        relation, reason = 'RIGHT_ABOVE', 'strictly_separated_completion_ranges'
    else:
        relation, reason = 'INCONCLUSIVE', 'completion_ranges_overlap_or_touch'
    return {'historical': base, 'completion': {'policy': 'verified_binary_pair_completion_v1',
        'relation': relation, 'reason': reason, 'left': left, 'right': right,
        'left_envelope': left_detail, 'right_envelope': right_detail,
        'completion_scope': 'independent_fixed_other_verdict_replacements_not_joint_evidence',
        'provider_identity_authenticated': False, 'human_preference_established': False}}
