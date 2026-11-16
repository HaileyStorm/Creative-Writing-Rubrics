"""File-boundary checks for the opt-in completion-envelope parser."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from hbqrs import core
from hbqrs.scoring_completion_envelope import main
from hbqrs.strict_input import POLICY


@pytest.fixture
def files(tmp_path, modules, bundles):
    bundle = core.resolve_bundle(bundles, 'prose.scene')
    qid = next(row['question']['id'] for row in core.compiled_questions(core.compile_bundle(modules, bundle))
               if row['role'] == 'domain')
    row = {'artifact_id': 'synthetic', 'bundle_id': bundle['bundle_id'], 'question_id': qid,
           'verdict': 'YES', 'confidence': 1.0,
           'evidence': [{'reference': 'synthetic', 'summary': 'Synthetic evidence.'}]}
    contract = {'contract_version': 1, 'contract_id': 'synthetic', 'artifact_id': 'synthetic',
                'context': {'artifact_kind': 'prose', 'declared_scope': 'scene', 'completion_status': 'excerpt',
                            'background': [], 'constraints': [], 'audience': []},
                'preferences': [], 'priorities': [], 'weighted_goals': [], 'binding_requirements': []}
    verdict_path, contract_path = tmp_path / 'verdicts.json', tmp_path / 'contract.json'
    verdict_path.write_text(json.dumps([row]), encoding='utf-8')
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    return verdict_path, contract_path


@pytest.mark.parametrize('admission', ['strict_import_v1', 'strict_import_v2'])
def test_strict_file_policy_preserves_valid_results_and_binds_bytes(files, admission, capsys):
    verdict, contract = files
    args = ['prose.scene', str(verdict), '--artifact-id', 'synthetic', '--max-cases', '1',
            '--admission-policy', admission, '--task-contract', str(contract)]
    assert main(args) == 0
    legacy = json.loads(capsys.readouterr().out)
    assert main(args + ['--input-policy', POLICY]) == 0
    strict = json.loads(capsys.readouterr().out)
    assert strict.pop('input_parsing_policy') == POLICY
    assert strict == legacy
    assert strict['input_file_sha256'] == {
        'verdicts': hashlib.sha256(verdict.read_bytes()).hexdigest(),
        'task_contract': hashlib.sha256(contract.read_bytes()).hexdigest()}


@pytest.mark.parametrize('target', ['verdict', 'contract'])
def test_strict_file_policy_rejects_duplicate_keys_before_admission(files, target, capsys):
    verdict, contract = files
    path = verdict if target == 'verdict' else contract
    original = path.read_text(encoding='utf-8')
    if target == 'verdict':
        altered = original.replace('"verdict": "YES"', '"verdict": "NO", "verdict": "YES"')
    else:
        altered = original.replace('"completion_status": "excerpt"',
                                   '"completion_status": "complete", "completion_status": "excerpt"')
    assert altered != original
    path.write_text(altered, encoding='utf-8')
    args = ['prose.scene', str(verdict), '--artifact-id', 'synthetic', '--max-cases', '1',
            '--admission-policy', 'strict_import_v2', '--task-contract', str(contract)]
    assert main(args) == 0
    capsys.readouterr()
    with pytest.raises(core.HBQError, match='duplicate mapping key'):
        main(args + ['--input-policy', POLICY])


def test_strict_file_policy_rejects_nonfinite_contract(files):
    verdict, contract = files
    text = contract.read_text(encoding='utf-8').replace('"contract_version": 1', '"contract_version": NaN')
    contract.write_text(text, encoding='utf-8')
    with pytest.raises(core.HBQError, match='non-finite'):
        main(['prose.scene', str(verdict), '--artifact-id', 'synthetic', '--max-cases', '1',
              '--task-contract', str(contract), '--input-policy', POLICY])


@pytest.mark.parametrize('target', ['verdict', 'contract'])
def test_malformed_yaml_cli_error_does_not_print_source(files, target):
    verdict, contract = files
    path = verdict.with_suffix('.yaml') if target == 'verdict' else contract.with_suffix('.yaml')
    private_marker = 'SYNTHETIC_PRIVATE_SENTINEL_74C9'
    path.write_text(f'{private_marker}: [unfinished\n', encoding='utf-8')
    if target == 'verdict':
        verdict = path
    else:
        contract = path
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / 'src'), PYTHONDONTWRITEBYTECODE='1')
    completed = subprocess.run(
        [sys.executable, '-m', 'hbqrs.scoring_completion_envelope', 'prose.scene', str(verdict),
         '--artifact-id', 'synthetic', '--task-contract', str(contract), '--input-policy', POLICY],
        cwd=root, env=env, capture_output=True, text=True, timeout=60,
    )
    assert completed.returncode != 0
    assert 'invalid YAML' in completed.stderr
    assert private_marker not in completed.stdout + completed.stderr
