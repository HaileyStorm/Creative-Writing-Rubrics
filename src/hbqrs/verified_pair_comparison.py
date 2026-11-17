"""Compare two locally verified binary runs under the same declared task.

This verifies saved bytes against frozen inputs using the current offline
verifier. It does not authenticate a provider or prove a review occurred.
Inputs must be stable, trusted local files while the comparison runs.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from . import core, decision_readiness, run_verify

POLICY = 'verified_binary_pair_point_order_v1'


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def _load_verified_json(path: Path, expected_sha256: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise core.HBQError('Verified pair input changed after run verification')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise core.HBQError('Verified pair input must be an object')
    return value


def _bound_data(binding: Any, label: str) -> dict[str, Any]:
    path = run_verify._bound_file(binding, label=label)
    value = core.load_data(path)
    if not isinstance(value, dict):
        raise core.HBQError(f'Frozen {label} must be an object')
    run_verify._bound_file(binding, label=label)
    return value


def _common_configuration(configuration: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(configuration))
    for key in ('artifact', 'artifact_id', 'task_contract', 'scope_compatibility'):
        if key not in result:
            raise core.HBQError(f'Verified run configuration lacks {key}')
        del result[key]
    for context in result['contexts']:
        del context['path']
    return result


def _binding_signature(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {'bytes': binding['bytes'], 'sha256': binding['sha256']}


def _side(run_dir: str | Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    frozen = deepcopy(dict(frozen))
    if frozen.get('task_contract') is None or frozen.get('scope_compatibility_override') is None:
        raise core.HBQError('Pair comparison requires a task contract and reviewed scope override for each run')
    if frozen.get('longform_scope_compatibility_proof') is not None:
        raise core.HBQError('Long-form scope proofs are not supported by this pair policy')
    directory = Path(run_dir).resolve()
    verified = run_verify.verify_binary_run(directory, frozen)
    manifest = _load_verified_json(directory / 'run.json', verified['run_sha256'])
    report = _load_verified_json(directory / 'score.v2.json', verified['score_v2_sha256'])
    task = _bound_data(frozen['task_contract'], 'task contract')
    override = _bound_data(frozen['scope_compatibility_override'], 'scope compatibility override')
    artifact_id = frozen['execution']['artifact_id']
    if task.get('artifact_id') != artifact_id or override.get('artifact_id') != artifact_id:
        raise core.HBQError('Pair artifact binding differs')
    task_common = deepcopy(task)
    del task_common['artifact_id']
    override_common = deepcopy(override)
    del override_common['artifact_id']
    del override_common['task_contract_sha256']
    configuration = manifest['configuration']
    if configuration['scope_compatibility'].get('mode') != 'reviewed_override':
        raise core.HBQError('Unsupported pair scope compatibility mode')
    return {'artifact_id': artifact_id, 'artifact_name': configuration['artifact']['name'],
            'task': task_common, 'scope': override_common,
            'configuration': _common_configuration(configuration),
            'frozen_bindings': {key: _binding_signature(frozen[key]) for key in
                                ('registry', 'bundles', 'response_schema', 'score_v1_schema', 'score_v2_schema')},
            'sessions': {item['session_id_sha256'] for item in verified['sessions']},
            'run_sha256': verified['run_sha256'], 'score_sha256': verified['score_v2_sha256'],
            'report': report}


def compare_verified_binary_runs(
    left_run: str | Path, left_frozen: Mapping[str, Any],
    right_run: str | Path, right_frozen: Mapping[str, Any],
) -> dict[str, Any]:
    """Return point order only when both saved runs and shared context match.

    Run verification checks saved response and prompt consistency. It does not
    independently authenticate provider sessions, historical settings, review,
    or a judgment's correctness. This policy supports reviewed direct-run scope
    overrides only; other scope modes remain unsupported. Its interval relation
    uses historical score bounds, which need not contain every resolved score.
    """
    left, right = _side(left_run, left_frozen), _side(right_run, right_frozen)
    result = {'policy': POLICY, 'left_artifact_id': left['artifact_id'], 'right_artifact_id': right['artifact_id'],
              'left_run_sha256': left['run_sha256'], 'right_run_sha256': right['run_sha256'],
              'left_score_sha256': left['score_sha256'], 'right_score_sha256': right['score_sha256'],
              'provider_identity_authenticated': False, 'human_review_authenticated': False,
              'context_origin_authenticated': False,
              'meaning': 'fixed_input_scorer_order_not_human_preference'}
    if left['artifact_id'] == right['artifact_id'] or left['run_sha256'] == right['run_sha256']:
        return dict(result, relation='INCOMPARABLE', reason='artifact_or_run_identity_reused')
    if left['sessions'] & right['sessions']:
        return dict(result, relation='INCOMPARABLE', reason='provider_session_reused')
    shared_keys = ('artifact_name', 'task', 'scope', 'configuration', 'frozen_bindings')
    for key in shared_keys:
        if _canonical(left[key]) != _canonical(right[key]):
            return dict(result, relation='INCOMPARABLE', reason=f'{key}_differs')
    shared = {key: left[key] for key in shared_keys}
    context_sha = hashlib.sha256(_canonical(shared)).hexdigest()
    interval = decision_readiness.interval_comparison(left['report'], right['report'],
                                                       comparison_context_sha256=context_sha)
    result.update(shared_context_sha256=context_sha, interval_relation=interval['relation'],
                  interval_reason=interval['reason'],
                  interval_bounds_kind='historical_scorer_bounds',
                  interval_completion_envelope_guaranteed=False)
    if interval['relation'] in ('INELIGIBLE', 'INCOMPARABLE'):
        return dict(result, relation=interval['relation'], reason=interval['reason'])
    if interval['reason'] not in ('strictly_separated_bounds', 'intervals_overlap_or_touch'):
        return dict(result, relation='UNRESOLVED', reason=interval['reason'])
    a, b = left['report']['final_score']['observed'], right['report']['final_score']['observed']
    return dict(result, relation='LEFT' if a > b else 'RIGHT' if b > a else 'TIE',
                reason='observed_point_order', left_score=a, right_score=b)
