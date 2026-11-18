"""Verify whole-work binary inputs and reconstruct long-form contexts.

Requires stable, trusted local inputs. Does not execute a model or authenticate
provider identity, map truth or the preceding structured-pass receipts.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from . import core, longform, longform_runner, run_verify, runner


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify_longform_contexts(run_dir, frozen):
    """Verify a saved binary run, its map identity and deterministic contexts.

    Only full-judging whole-work proofs are supported. Inputs must remain stable
    and trusted; verification does not establish an atomic filesystem snapshot,
    truthful map summaries, human review or prior structured-pass provenance.
    The receipt contains local proof paths and is intended for local use.
    """
    frozen = deepcopy(dict(frozen))
    if frozen.get('scope_compatibility_override') is not None:
        raise core.HBQError('A direct-run override is not a long-form proof')
    proof = frozen.get('longform_scope_compatibility_proof')
    if not isinstance(proof, dict) or proof.get('mode') != 'longform_prevalidated_route' or proof.get('scope_id') != 'work':
        raise core.HBQError('A whole-work long-form proof is required')
    run_dir = Path(run_dir).resolve()
    verified = run_verify.verify_binary_run(run_dir, frozen)
    run_path = run_dir / 'run.json'
    run_bytes = run_path.read_bytes()
    if sha(run_bytes) != verified['run_sha256']:
        raise core.HBQError('Verified run changed')
    manifest = json.loads(run_bytes)
    if manifest['configuration']['scope_compatibility'] != proof:
        raise core.HBQError('Verified run proof differs')
    artifact = run_verify._bound_file(frozen['artifact'], label='artifact')
    registry = run_verify._bound_file(frozen['registry'], label='registry')
    bundles = run_verify._bound_file(frozen['bundles'], label='bundles')
    contexts = run_verify._bound_files(frozen['contexts'], label='contexts')
    plan_path = Path(proof['route_plan']['path'])
    plan, _, scope, _, _, generated = runner._longform_plan_scope(
        route_plan_path=plan_path, artifact_path=artifact,
        artifact_id=frozen['execution']['artifact_id'], bundle_id=frozen['execution']['bundle_id'],
        registry_path=registry, bundles_path=bundles, context_paths=contexts)
    if plan['execution_mode'] != 'full_judging' or scope['scope_id'] != 'work' or len(generated) != 3:
        raise core.HBQError('Only full-judging whole-work contexts are supported')
    root = plan_path.parent
    source = root / '.private/inputs/artifact.txt'
    raw = source.read_bytes()
    source_binding = plan['source_artifact']
    if source_binding['path'] != '.private/inputs/artifact.txt' or len(raw) != source_binding['bytes'] or sha(raw) != source_binding['sha256']:
        raise core.HBQError('Persisted source differs')
    segmentation = longform.segment_longform(raw.decode('utf-8'), artifact_id=plan['artifact_id'])
    map_bytes, task_bytes, completion_bytes = [p.read_bytes() for p in contexts[-3:]]
    if [sha(x) for x in (map_bytes, task_bytes, completion_bytes)] != [v['sha256'] for v in generated]:
        raise core.HBQError('Generated contexts changed')
    longform.validate_long_form_map(json.loads(map_bytes), segmentation=segmentation)
    task = runner._longform_runtime_contract(plan['route']['task_contract'], scope_id='work',
        artifact_id=plan['artifact_id'], execution_scope=scope['execution_scope'], normalize_absence=False)
    expected_task = longform_runner._contract_judge_context(task)
    expected_completion = longform_runner._completion_judge_context(
        plan['route']['artifact_profile']['completion_status'], scope_kind='global', scope_id='work')
    if task_bytes != runner._json_bytes(expected_task) or completion_bytes != runner._json_bytes(expected_completion):
        raise core.HBQError('Deterministic context reconstruction differs')
    for name in ('artifact', 'registry', 'bundles', 'task_contract'):
        run_verify._bound_file(frozen[name], label=name)
    run_verify._bound_files(frozen['contexts'], label='contexts')
    if (sha(run_path.read_bytes()) != verified['run_sha256'] or sha(source.read_bytes()) != source_binding['sha256']
            or sha(plan_path.read_bytes()) != proof['route_plan']['sha256']):
        raise core.HBQError('Input changed during verification')
    return {'policy': 'verified_longform_context_v1', 'binary_verification': verified,
        'run_sha256': verified['run_sha256'], 'score_v2_sha256': verified['score_v2_sha256'], 'scope_proof': proof,
        'source_sha256': source_binding['sha256'], 'map_sha256': sha(map_bytes),
        'task_context_sha256': sha(task_bytes), 'completion_context_sha256': sha(completion_bytes),
        'provider_identity_authenticated': False, 'map_truth_established': False,
        'structured_pass_provenance_verified': False, 'atomic_snapshot_established': False}
