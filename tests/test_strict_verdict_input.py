"""Behavioral coverage for the opt-in verdict-file parser and score command."""
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from hbqrs import core
from hbqrs.cli import main
from hbqrs.paths import schema_dir
from hbqrs.strict_input import POLICY, load_verdict_input
from hbqrs.weights import make_weight_profile


@pytest.mark.parametrize(('suffix', 'text'), [
    ('.json', '{"a": 1, "a": 2}'),
    ('.json', '{"nested": {"a": 1, "\\u0061": 2}}'),
    ('.jsonl', '{"a": 1}\n{"a": 1, "a": 2}\n'),
    ('.yaml', 'outer:\n  key: 1\n  key: 2\n'),
    ('.yml', 'base: &base {key: 1}\nmerged: {<<: *base, key: 2}\n'),
    ('.json', '{"a": NaN}'),
    ('.json', '{"a": 1e999}'),
    ('.yaml', 'a: .inf\n'),
    ('.yaml', 'a: &a [*a]\n'),
    ('.yaml', '1: value\n'),
    ('.yaml', 'a: 2026-01-01\n'),
])
def test_rejects_ambiguous_or_non_json_compatible_data(tmp_path, suffix, text):
    path = tmp_path / ('input' + suffix)
    path.write_text(text, encoding='utf-8')
    with pytest.raises(core.HBQError):
        load_verdict_input(path)


@pytest.mark.parametrize(('suffix', 'text', 'expected'), [
    ('.json', '{"a": [1, true, null]}', {'a': [1, True, None]}),
    ('.jsonl', '{"a": 1}\n\n{"a": 2}\n', [{'a': 1}, {'a': 2}]),
    ('.yaml', 'a: &item {x: 1}\nb: *item\n', {'a': {'x': 1}, 'b': {'x': 1}}),
])
def test_accepts_valid_file_and_reports_exact_digest(tmp_path, suffix, text, expected):
    path = tmp_path / ('input' + suffix)
    raw = text.encode('utf-8')
    path.write_bytes(raw)
    value, receipt = load_verdict_input(path)
    assert value == expected
    assert receipt == {'policy': POLICY, 'sha256': hashlib.sha256(raw).hexdigest()}


def test_real_score_cli_strict_input_and_historical_replay(tmp_path, modules, bundles, capsys):
    bundle = core.resolve_bundle(bundles, 'prose.scene')
    qid = next(row['question']['id'] for row in core.compiled_questions(core.compile_bundle(modules, bundle))
               if row['role'] == 'domain')
    row = {'artifact_id': 'synthetic', 'bundle_id': bundle['bundle_id'], 'question_id': qid,
           'verdict': 'YES', 'confidence': 1.0,
           'evidence': [{'reference': 'synthetic', 'summary': 'Synthetic evidence.'}]}
    ordinary = json.dumps(row)
    ambiguous = ordinary.replace('"verdict": "YES"', '"verdict": "NO", "verdict": "YES"')
    assert ambiguous != ordinary
    path = tmp_path / 'verdicts.json'
    path.write_text('[' + ambiguous + ']', encoding='utf-8')
    common = ['score', 'prose.scene', str(path), '--artifact-id', 'synthetic',
              '--admission-policy', 'strict_import_v2']
    with pytest.raises(SystemExit) as error:
        main(common + ['--verdict-input-policy', POLICY])
    assert error.value.code == 2
    capsys.readouterr()
    assert main(common) == 0
    historical = json.loads(capsys.readouterr().out)
    assert historical['import_admission']['supplied_questions'] == 1
    assert 'verdict_input' not in historical
    path.write_text('[' + ordinary + ']', encoding='utf-8')
    assert main(common + ['--verdict-input-policy', POLICY]) == 0
    strict = json.loads(capsys.readouterr().out)
    assert strict['verdict_input']['sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert {key: value for key, value in strict.items() if key != 'verdict_input'} == historical
    assert main(common + ['--report-version', '2', '--verdict-input-policy', POLICY]) == 0
    report_v2 = json.loads(capsys.readouterr().out)
    schema = json.loads((schema_dir() / 'hbq_score_report.v2.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(report_v2)


def test_score_auxiliary_files_are_opt_in_strict_and_hash_bound(tmp_path, modules, bundles, capsys):
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
    profile = make_weight_profile(modules, bundle, profile_id='synthetic')
    verdict_path, contract_path, profile_path = (tmp_path / name for name in ('verdicts.json', 'contract.json', 'weights.json'))
    verdict_path.write_text(json.dumps([verdict]), encoding='utf-8')
    contract_text = json.dumps(contract)
    profile_text = json.dumps(profile)
    contract_path.write_text(contract_text, encoding='utf-8')
    profile_path.write_text(profile_text, encoding='utf-8')
    common = ['score', 'prose.scene', str(verdict_path), '--artifact-id', 'synthetic',
              '--admission-policy', 'strict_import_v2', '--verdict-input-policy', POLICY,
              '--task-contract', str(contract_path), '--weight-profile', str(profile_path)]
    assert main(common) == 0
    historical = json.loads(capsys.readouterr().out)
    assert 'score_auxiliary_inputs' not in historical
    assert main(common + ['--auxiliary-input-policy', POLICY]) == 0
    strict = json.loads(capsys.readouterr().out)
    receipt = strict.pop('score_auxiliary_inputs')
    assert strict == historical
    assert receipt == {'policy': POLICY,
                       'task_contract': {'policy': POLICY, 'sha256': hashlib.sha256(contract_path.read_bytes()).hexdigest()},
                       'weight_profile': {'policy': POLICY, 'sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest()}}
    assert main(common + ['--report-version', '2', '--auxiliary-input-policy', POLICY]) == 0
    report_v2 = json.loads(capsys.readouterr().out)
    schema = json.loads((schema_dir() / 'hbq_score_report.v2.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(report_v2)

    duplicate_contract = contract_text.replace('"completion_status": "excerpt"',
                                               '"completion_status": "complete", "completion_status": "excerpt"')
    assert duplicate_contract != contract_text
    contract_path.write_text(duplicate_contract, encoding='utf-8')
    assert main(common) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as error:
        main(common + ['--auxiliary-input-policy', POLICY])
    assert error.value.code == 2
    capsys.readouterr()
    contract_path.write_text(contract_text, encoding='utf-8')

    duplicate_profile = profile_text.replace('"profile_id": "synthetic"',
                                             '"profile_id": "different", "profile_id": "synthetic"')
    assert duplicate_profile != profile_text
    profile_path.write_text(duplicate_profile, encoding='utf-8')
    assert main(common) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as error:
        main(common + ['--auxiliary-input-policy', POLICY])
    assert error.value.code == 2
