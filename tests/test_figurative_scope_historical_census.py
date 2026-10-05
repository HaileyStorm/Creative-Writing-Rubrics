"""Historical singleton joins preserve privacy, repetitions and source bindings."""
import gzip
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-figurative-scope-historical-census-v1/census.py"
spec = importlib.util.spec_from_file_location("figurative_census_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path, mismatched_checkpoint=False):
    files, runtime, prepared = [], [], []

    def add(path, value):
        raw = value if isinstance(value, bytes) else census.canonical(value)
        target = tmp_path / 'source' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files.append({'locator': path, 'sha256': census.sha(raw), 'bytes': len(raw)})

    schema, rubric, prompt_template = [census.digest(key) for key in ('original-schema', 'rubric', 'prompt-template')]
    bindings = {'runtime_head': 'historical-head', 'cwr_files': {'schema/hbq_judge_response.schema.json': schema,
        'registry/all_modules.json': rubric, 'prompts/judge/BINARY_EVALUATION_PROMPT.md': prompt_template}}
    for artifact in range(2):
        source = f'SEALED_SOURCE_{artifact}'.encode()
        artifact_id = f'asset-{artifact:03d}'
        artifact_file = artifact_id + '.txt'
        add('inputs/' + artifact_file, source)
        task_raw, compatibility_raw = b'NOT_DECODED_CONTRACT\\q', b'NOT_DECODED_OVERRIDE\\q'
        task_name, compatibility_name = artifact_id + '.json', artifact_id + '.json'
        add('contracts/' + task_name, task_raw)
        add('compatibility/' + compatibility_name, compatibility_raw)
        for arm in ('baseline', 'scope_rendering_only'):
            for repetition in range(1, 4):
                sid = f'slot-{len(runtime) + 1:03d}'
                qid = f'criterion-{artifact}'
                rendered = f'SEALED_PROMPT_{artifact}_{arm}\r\n'.encode()
                checkpoint_prompt = census.newline_bytes(rendered)
                condition = {'arm': arm, 'prompt_sha256': census.sha(rendered), 'rubric_sha256': rubric}
                slot = {'slot_id': sid, 'study_id': 'historical-study', 'artifact_id': artifact_id,
                        'artifact_file': artifact_file, 'artifact_sha256': census.sha(source), 'leaf_id': qid,
                        'arm': arm, 'repetition': repetition, 'logical_sample_id': sid, 'condition': condition}
                runtime.append(slot)
                prepared.append({**slot, 'condition': {**condition, 'prompt_sha256': census.digest(['prepared', sid])},
                                 'logical_sample_id': 'prepared-' + sid})
                add(f'rendered-prompts/{sid}.txt', rendered)
                cfg = {'provider': 'codex', 'model': 'gpt-5.6-sol', 'reasoning': 'high', 'batch_size': 1,
                    'artifact_id': artifact_id, 'bundle_id': 'prose.short_story', 'question_ids': [qid], 'contexts': [],
                    'artifact': {'sha256': census.sha(source), 'bytes': len(source)},
                    'response_schema': {'sha256': schema}, 'prompts': [{'sha256': prompt_template}],
                    'compiled_bundle_sha256': census.digest(['compiled', artifact, arm]), 'questions_sha256': census.digest(qid),
                    'task_contract': None, 'scope_compatibility': None, 'task_contract_judge_context': None}
                if arm != 'baseline':
                    cfg.update(task_contract={'name': task_name, 'sha256': census.sha(task_raw), 'bytes': len(task_raw)},
                        scope_compatibility={'name': compatibility_name, 'sha256': census.sha(compatibility_raw),
                                             'bytes': len(compatibility_raw), 'mode': 'reviewed_override'},
                        task_contract_judge_context={'model_facing': True, 'sha256': census.digest(['context', artifact])})
                prefix = f'runs/{sid}/'
                run_id = 'run-' + sid
                add(prefix + 'run.json', {'format_version': 4, 'run_id': run_id,
                                          'config_sha256': census.digest(['declared-config', sid]), 'configuration': cfg})
                add(prefix + 'response.schema.json', b'FROZEN_PORTABLE_SCHEMA')
                add(prefix + 'responses/batch-0001.prompt.txt.gz', gzip.compress(checkpoint_prompt, mtime=0))
                message = ('{"verdicts":[{"question_id":"' + qid + '","verdict":"YES",'
                           '"evidence":[{"exact_quote":"SEALED\\q"}],"note":"SEALED\\q"}]}').encode()
                accepted_path = 'responses/batch-0001.accepted-0001.message.txt'
                add(prefix + accepted_path, message)
                add(prefix + 'responses/batch-0001.attempt-0001.message.json', message)
                normalized = {'question_id': qid, 'verdict': 'NO' if mismatched_checkpoint and len(runtime) == 1 else 'YES', 'run_id': run_id}
                add(prefix + 'responses/batch-0001.json', {'batch': 1, 'accepted_attempt': 1,
                    'question_ids': [qid], 'previous_checkpoint_sha256': None,
                    **{k: census.sha(checkpoint_prompt) for k in ('prompt_sha256', 'base_prompt_sha256', 'effective_prompt_sha256')},
                    'response_sha256': census.digest('declared-payload'), 'verdicts_sha256': census.digest('declared-verdicts'),
                    'response_artifact': {'path': accepted_path, 'sha256': census.sha(message), 'bytes': len(message)},
                    'rejected_chain': {'count': 0, 'head_sha256': None}, 'normalized_verdicts': [normalized],
                    'provider': {'reported': {'provider': 'openai', 'model': 'gpt-5.6-sol', 'reasoning_effort': 'high', 'session_id': 'session-' + sid}},
                    'normalization_audit': 'NOT_DECODED'})
                add(prefix + 'diagnostic.json', {'status': 'DIAGNOSTIC_SUBSET', 'selected_question_ids': [qid],
                    'artifact_id': artifact_id, 'bundle_id': 'prose.short_story', 'note': 'NOT_DECODED'})
    add('study-manifest.json', {'study_id': 'historical-study', 'planned_requests': 12, 'runtime_bindings': bindings,
                               'contract_sha256': census.digest('study-contract'), 'slots': prepared})
    add('runtime-schedule.json', {'slots': runtime, 'oracle': 'NOT_DECODED'})
    add('dry-run.json', {'mode': 'dry_run', 'provider_calls': 0, 'planned_requests': 12, 'runtime_bindings': bindings,
                        'rendered_prompt_sha256s': {s['slot_id']: s['condition']['prompt_sha256'] for s in runtime}})
    for path in census.HASH_ONLY:
        add(path, b'NOT_DECODED_OUTCOMES\\q')
    return {'policy': census.POLICY, 'helper_pins': {k: v[1] for k, v in census.HELPERS.items()},
        'source_root': 'source', 'roots': [{'locator': 'source', 'files': files}],
        'slot_ids': [s['slot_id'] for s in runtime], 'historical_runtime_bindings': bindings,
        'historical_contract_sha256': census.digest('study-contract'), 'hash_only': census.HASH_ONLY,
        'historical_prompt_projection': 'universal_newlines_only_v1', 'excluded_ancestors': ['original', 'v2'],
        'expected': {'slots': 12, 'arms': {'baseline': 6, 'scope_rendering_only': 6},
                     'repetitions': {'1': 4, '2': 4, '3': 4}, 'criterion_positions': {'criterion-0': 6, 'criterion-1': 6}}}


def test_singleton_repetition_geometry_and_private_field_exclusion(tmp_path):
    recipe = fixture(tmp_path)
    report, ledger = census.run(recipe, tmp_path)
    assert report['observed']['singleton_leaf_positions'] == 12
    assert report['observed']['duplicate_checkpoint_representations_not_added'] == 12
    assert report['observed']['distinct_reported_sessions'] == 12
    assert report['observed']['historical_newline_prompt_projections'] == 12
    assert report['observed']['prepared_runtime_condition_differences'] == 12
    assert len({r['position_id_sha256'] for r in ledger['observations']}) == 12
    assert report['observed']['verdict_states'] == {'YES': 12}
    assert not report['gaps']['native_identity_attestation_available']
    assert b'SEALED' not in census.canonical({'report': report, 'ledger': ledger})
    assert report['provider_calls_made'] == report['new_provider_votes'] == 0
    assert not census.destination(tmp_path / 'fresh', tmp_path, recipe).exists()
    recipe['expected']['arms']['baseline'] = 7
    with pytest.raises(ValueError, match='geometry'):
        census.run(recipe, tmp_path)


def test_changed_source_and_checkpoint_projection_fail(tmp_path):
    recipe = fixture(tmp_path)
    path = tmp_path / 'source/inputs/asset-000.txt'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Source hash differs'):
        census.run(recipe, tmp_path)
    other = tmp_path / 'mismatched-checkpoint'
    recipe = fixture(other, mismatched_checkpoint=True)
    with pytest.raises(ValueError, match='Singleton checkpoint'):
        census.run(recipe, other)
