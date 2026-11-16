"""Behavioral coverage for the opt-in verdict-file parser and score command."""
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator

from hbqrs import core
from hbqrs.cli import main
from hbqrs.paths import schema_dir
from hbqrs.strict_input import POLICY, load_verdict_input


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
