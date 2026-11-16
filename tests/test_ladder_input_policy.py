"""File parsing at the experimental ladder comparison entry point."""
import hashlib
import json

import pytest

from hbqrs import core, ladder_uncertainty
from hbqrs.strict_input import POLICY


def test_ladder_cli_strict_files_and_historical_replay(tmp_path, modules, bundles, capsys):
    bundle = core.resolve_bundle(bundles, 'prose.scene')
    qid = next(row['question']['id'] for row in core.compiled_questions(core.compile_bundle(modules, bundle))
               if row['role'] == 'domain')
    verdict = {'artifact_id': 'synthetic', 'bundle_id': bundle['bundle_id'], 'question_id': qid,
               'verdict': 'YES', 'confidence': 1.0,
               'evidence': [{'reference': 'synthetic', 'summary': 'Synthetic evidence.'}]}
    contract = {'contract_version': 1, 'contract_id': 'synthetic', 'artifact_id': 'synthetic',
                'context': {'artifact_kind': 'prose', 'declared_scope': 'scene', 'completion_status': 'excerpt',
                            'background': [], 'constraints': [], 'audience': []},
                'preferences': [], 'priorities': [], 'weighted_goals': [], 'binding_requirements': []}
    verdict_path, contract_path = tmp_path / 'verdicts.json', tmp_path / 'contract.json'
    ordinary = json.dumps([verdict])
    verdict_path.write_text(ordinary, encoding='utf-8')
    contract_path.write_text(json.dumps(contract), encoding='utf-8')
    args = ['prose.scene', str(verdict_path), '--artifact-id', 'synthetic',
            '--admission-policy', 'strict_import_v2', '--task-contract', str(contract_path)]
    assert ladder_uncertainty.main(args) == 0
    historical = json.loads(capsys.readouterr().out)
    assert ladder_uncertainty.main(args + ['--input-policy', POLICY]) == 0
    strict = json.loads(capsys.readouterr().out)
    assert strict.pop('input_parsing_policy') == POLICY
    assert strict == historical
    assert strict['inputs']['verdicts_file_sha256'] == hashlib.sha256(verdict_path.read_bytes()).hexdigest()
    assert strict['inputs']['task_contract_file_sha256'] == hashlib.sha256(contract_path.read_bytes()).hexdigest()

    verdict_path.write_text(ordinary.replace('"verdict": "YES"', '"verdict": "NO", "verdict": "YES"'), encoding='utf-8')
    with pytest.raises(SystemExit) as error:
        ladder_uncertainty.main(args + ['--input-policy', POLICY])
    assert error.value.code == 2
    capsys.readouterr()
    assert ladder_uncertainty.main(args) == 0
    capsys.readouterr()
    verdict_path.write_text(ordinary, encoding='utf-8')
    contract_path.write_text(json.dumps(contract).replace('"completion_status": "excerpt"',
                             '"completion_status": "complete", "completion_status": "excerpt"'), encoding='utf-8')
    with pytest.raises(SystemExit) as error:
        ladder_uncertainty.main(args + ['--input-policy', POLICY])
    assert error.value.code == 2
