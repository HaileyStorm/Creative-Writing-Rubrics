"""Provider-free boundaries; mock receipts do not attest native or literary results."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = Path(r'C:\Users\Haile\Documents\cwr-resume-control-20260919-r1\successor-program-20261004')
spec = importlib.util.spec_from_file_location('test_longform_prepare', ROOT / 'evaluation-results/hbq-longform-dependency-pilot-v1/prepare.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
admission = p.load('test_longform_admission', p.HERE / 'arms/validate_response.py')


@pytest.fixture(scope='module')
def sources():
    index = PROGRAM / 'longform-dependency/source-index-001'
    if not index.exists(): pytest.skip('Exact local frozen public source index unavailable')
    works, cases, files = p.read_sources(index)
    runtime, runtime_files, subset = p.runtime_inputs(PROGRAM / 'semantic-crossform/frozen-001/manifest.json')
    return works, cases, files, runtime, runtime_files, subset


@pytest.fixture(scope='module')
def summary_plan(sources):
    works, _, files, runtime, runtime_files, subset = sources
    return p.summary_plan(works, files, runtime, runtime_files, subset)


def answers(sources):
    return {work_id: {'schema_version': 1, 'work_id': work_id, 'source_narrative_sha256': work['input']['sha256'],
        'summary_text': ' '.join(['Synthetic mechanical summary.'] * 230),
        'attribution_notes': ['Attributions remain narrator and character reports.'], 'uncertainties': ['Ontology remains unresolved.']}
        for work_id, work in sources[0].items()}


@pytest.fixture(scope='module')
def design(sources):
    works, cases, files, runtime, runtime_files, subset = sources
    before = copy.deepcopy((works, cases, files))
    result = p.judging_plan(works, cases, files, runtime, runtime_files, subset, answers(sources), {})
    assert before == (works, cases, files)
    return result


def test_original_coordinates_crlf_and_case_inventory(sources):
    works, cases, _, _, _, _ = sources
    assert sum(len(w['index']['units']) for w in works.values()) == 35
    assert sum(len(w['index']['anchors']) for w in works.values()) == 26
    assert works['pg209']['index']['units'][0]['kind'] == 'narrative_frame'
    assert all(b'\r\n' in w['narrative'] and w['narrative'].endswith(b'\r\n') for w in works.values())
    assert sum(map(len, p.CASE_LEAVES.values())) == 18 and len(set(q for ids in p.CASE_LEAVES.values() for q in ids)) == 10
    for case in cases:
        work = works[Path(case['source']).stem]
        body = p.anchored_representation(work, case)
        for lo, hi in case['context_windows_char']:
            assert work['raw_text'][lo:hi].encode('utf-8') in body
        assert b'not an interpretation oracle' in body


@pytest.mark.parametrize('relative', ['source-index-001/narratives/pg43.txt', 'source-index-001/indexes/pg43.json', 'source-fetch-001/pg43.txt'])
def test_changed_source_boundary_refused(tmp_path, sources, relative):
    source = PROGRAM / 'longform-dependency'
    for folder in ('source-index-001', 'source-fetch-001'): shutil.copytree(source / folder, tmp_path / folder)
    path = tmp_path / relative; path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError, match='differ'): p.read_sources(tmp_path / 'source-index-001')


def test_summary_generation_independent_of_cases_maps_and_leaves(sources, summary_plan):
    manifest, files = summary_plan
    assert len(manifest['requests']) == 2 and manifest['counts']['summary_generation_calls'] == 2
    for row in manifest['requests']:
        prompt = files[row['prompt_path']]
        assert sources[0][row['work_id']]['narrative'] in prompt
        for marker in [*p.CASE_LEAVES, 'minimal_map', 'j1_received', 't3_burned', 'craft.narrative.', 'target_defect', 'legitimate_style']:
            assert marker.encode() not in prompt
        schema = json.loads(files[row['schema_path']])
        assert schema['properties']['source_narrative_sha256']['enum'] == [row['source']['sha256']]


@pytest.mark.parametrize('words', [649, 1001])
def test_summary_word_budget_refused_before_judging(sources, summary_plan, words):
    row = summary_plan[0]['requests'][0]
    answer = answers(sources)[row['work_id']]
    answer['summary_text'] = ' '.join(['summary'] * words)
    with pytest.raises(ValueError, match='650–1000'):
        p.validate_summary(row, answer, json.loads(summary_plan[1][row['schema_path']]), sources[-1])


def test_distinct_contracts_complete_banks_repeats_and_exact_context(design, sources):
    manifest, files = design
    assert manifest['counts']['requests_total'] == 464 and manifest['counts']['diagnostic_requests'] == 216
    assert manifest['candidate'] is None and not manifest['execution_authority'] and not manifest['oracle_accepted']
    sentinel = manifest['whole_bank_sentinel']['work_id']
    for endpoint in p.ENDPOINTS:
        full = [r for r in manifest['requests'] if r['endpoint'] == endpoint and r['contract'] == 'whole_work_baseline' and r['arm'] == 'hbq']
        assert len(full) == 112
        for work_id in sources[0]:
            cycles = {r['repeat'] for r in full if r['work_id'] == work_id}
            assert cycles == ({0, 1, 2} if work_id == sentinel else {0})
            for cycle in cycles:
                rows = sorted([r for r in full if r['work_id'] == work_id and r['repeat'] == cycle], key=lambda r: r['batch'])
                assert len(rows) == 28 and len([q for r in rows for q in r['question_ids']]) == 219
                assert len(set(q for r in rows for q in r['question_ids'])) == 219
    for row in manifest['requests']:
        prompt = files[row['prompt_path']]
        assert files[row['task_context']['path']] in prompt and b'"audience": []' in prompt
        source = row['sources'][0]
        assert files[source['input_path']] in prompt
        assert row['target_original'] == sources[0][row['work_id']]['input']
        if row['contract'] == 'unscored_dependency_diagnostic':
            assert not row['whole_work_artistic_score'] and not row['full_bank_score_eligible']
            if row['arm'] == 'hbq': assert len(row['question_ids']) == 3
        else:
            assert row['context_arm'] == 'raw_full'
            assert files[source['input_path']] == sources[0][row['work_id']]['narrative']
    assert not manifest['context_delivery']['supported_context_window_or_native_delivery_proven']


def test_summary_cannot_quote_unavailable_original_or_prompt_directive(design, sources):
    manifest, files = design; subset = sources[-1]
    row = next(r for r in manifest['requests'] if r['arm'] == 'hbq' and r['context_arm'] == 'summary_only')
    text = files[row['sources'][0]['input_path']].decode('utf-8')
    context = files[row['task_context']['path']].decode('utf-8')
    source_quote = sources[0][row['work_id']]['index']['anchors'][0]['quote']
    def response(quote):
        return {'verdicts': [{'question_id': q, 'verdict': 'YES', 'confidence': 1, 'note': 'Mechanical witness only.',
            'evidence': [{'kind': 'exact_quote', 'reference': 'available source', 'exact_quote': quote, 'summary': None}]} for q in row['question_ids']]}
    validate = lambda quote: admission.semantic_validate('hbq', response(quote), row, {row['work_id']: text}, subset,
        context=context, schema=json.loads(files[row['schema_path']]))['accepted']
    assert source_quote not in text and not validate(source_quote)
    assert validate('"audience": []')
    assert not validate(row['question_ids'][0])


class ReceiptMock:
    reject = False
    duplicate = False
    def verify(self, sample, provider, **kwargs):
        if self.reject: raise ValueError('Mock native receipt rejected')
        assert kwargs['prompt'] and kwargs['final_raw'] and kwargs['model'] == 'gpt-6.1-sol'
    def event_identity(self, events, final):
        return ('same' if self.duplicate else events.decode()), []


@pytest.fixture
def saved_summaries(tmp_path, summary_plan, sources):
    plan, files = summary_plan; frozen = tmp_path / 'summary-frozen'; frozen.mkdir()
    for name, raw in files.items(): p.base.write_new(frozen / name, raw)
    output = tmp_path / 'summary-results'; output.mkdir()
    manifest_sha = p.digest(files['manifest.json'])
    p.base.write_new(output / 'job.json', p.canonical(p.summary_job_binding(plan, manifest_sha)))
    account = p.canonical(p.generation.expected_account_binding(plan)); p.base.write_new(output / 'account-binding.json', account)
    entries = []
    for row in plan['requests']:
        sample = output / row['work_id']; sample.mkdir()
        answer = answers(sources)[row['work_id']]; final = p.canonical(answer)
        provider = {'provider_artifacts': {'codex_message': {'path': 'final.json'}, 'codex_events': {'path': 'events.txt'}}}
        raw_records = {'condition': p.canonical(row), 'response': p.canonical(answer), 'native-result': p.canonical(provider),
            'validation': p.canonical(p.validate_summary(row, answer, json.loads(files[row['schema_path']]), sources[-1])),
            'attempt-started': p.canonical({'manifest_sha256': manifest_sha, 'logical_sample_id': row['logical_sample_id'],
                'attempt': 1, 'no_resend': True, 'prompt_sha256': row['prompt_sha256'], 'schema_sha256': row['schema_sha256'],
                'account_binding_sha256': p.digest(account)})}
        for name, raw in raw_records.items(): p.base.write_new(sample / (name + '.json'), raw)
        for name, raw in [('prompt.txt', files[row['prompt_path']]), ('schema.json', files[row['schema_path']]),
                          ('final.json', final), ('events.txt', row['work_id'].encode()), ('summary.txt', answer['summary_text'].encode())]:
            p.base.write_new(sample / name, raw)
        terminal = {'state': 'accepted_generation', 'no_resend': True, 'manifest_sha256': manifest_sha,
            'logical_sample_id': row['logical_sample_id'], **{n+'_sha256': p.digest(v) for n,v in raw_records.items()},
            'derived_summary': p.metadata('summary.txt', answer['summary_text'].encode())}
        p.base.write_new(sample / 'terminal.json', p.canonical(terminal))
        entries.append({'work_id': row['work_id'], 'logical_sample_id': row['logical_sample_id'], 'sample_path': str(sample.relative_to(tmp_path))})
    wrapper = {'schema_version': 1, 'policy': 'longform_source_summary_receipts_v1',
        'generation_manifest': {'path': 'summary-frozen/manifest.json', 'sha256': manifest_sha}, 'summaries': entries}
    path = tmp_path / 'summary-receipts.json'; path.write_bytes(p.canonical(wrapper))
    return path, ReceiptMock(), output, wrapper


def test_exact_two_source_summary_receipts_and_immutable_lineage(saved_summaries, summary_plan, sources):
    path, receipts, _, _ = saved_summaries
    before = copy.deepcopy(summary_plan)
    summaries, lineage = p.read_summaries(path, *summary_plan, sources[-1], receipts)
    assert summaries == answers(sources) and summary_plan == before
    assert 'private/summary-wrapper.json' in lineage and 'private/summary-generation-manifest.json' in lineage


@pytest.mark.parametrize('failure', ['receipt', 'duplicate_native', 'derived', 'response', 'account', 'missing_work'])
def test_unadmitted_summary_never_enters_judging(saved_summaries, summary_plan, sources, failure):
    path, receipts, output, wrapper = saved_summaries
    if failure == 'receipt': receipts.reject = True
    if failure == 'duplicate_native': receipts.duplicate = True
    if failure in ('derived', 'response'):
        name = 'summary.txt' if failure == 'derived' else 'response.json'
        target = output / wrapper['summaries'][0]['work_id'] / name
        target.write_bytes(target.read_bytes() + b'changed')
    if failure == 'account': (output / 'account-binding.json').write_bytes(b'{}')
    if failure == 'missing_work':
        wrapper['summaries'].pop(); path.write_bytes(p.canonical(wrapper))
    with pytest.raises(ValueError): p.read_summaries(path, *summary_plan, sources[-1], receipts)


def test_missing_summary_pending_dry_run_refuses_actual_freeze(tmp_path, sources, summary_plan, monkeypatch, capsys):
    monkeypatch.setattr(p, 'read_sources', lambda *a: sources[:3])
    monkeypatch.setattr(p, 'runtime_inputs', lambda *a: sources[3:])
    monkeypatch.setattr(p, 'summary_plan', lambda *a: summary_plan)
    output = tmp_path / 'fresh'
    args = ['prepare.py', '--source-index', str(tmp_path / 'inputs/index'), '--runtime-manifest', str(tmp_path / 'runtime/manifest.json'), '--output-root', str(output)]
    monkeypatch.setattr('sys.argv', args + ['--dry-run'])
    assert p.main() == 0 and json.loads(capsys.readouterr().out)['freeze_refused'] and not output.exists()
    monkeypatch.setattr('sys.argv', args)
    assert p.main() == 2 and not output.exists()
    capsys.readouterr()
    with pytest.raises(ValueError, match='pending'): p.read_summaries(None, *summary_plan, sources[-1])
    with pytest.raises(ValueError, match='outside repository'): p.base.output_preflight(p.HERE / 'private-output')
    with pytest.raises(ValueError, match='retained input'): p.base.output_preflight(tmp_path / 'inputs/nested', (tmp_path / 'inputs',))
