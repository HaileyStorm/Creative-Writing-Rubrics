"""Mock native execution proves orchestration/lineage, not native or factual results."""
import importlib.util
import json
from pathlib import Path
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


c = load('test_longform_summary_collector', ROOT / 'evaluation-results/hbq-longform-dependency-pilot-v1/collector_summary.py')
fixtures = load('summary_preparation_fixtures', ROOT / 'tests/test_longform_dependency_preparation.py')


@pytest.fixture(scope='module')
def plan():
    sources = fixtures.sources.__wrapped__()
    return sources, fixtures.summary_plan.__wrapped__(sources)


class Receipts:
    reject = False
    def verify(self, sample, provider, **kwargs):
        if self.reject: raise ValueError('Mock own native receipt rejected')
        assert provider['receipt_policy'] == 'codex_native_rollout_v1'
        assert kwargs['model'] == 'gpt-6.1-sol' and kwargs['reasoning'] == 'high'
        for meta in provider['provider_artifacts'].values(): c.pinned(sample, meta['path'], meta)
    def event_identity(self, events, final):
        return json.loads(events)['thread_id'], []


@pytest.fixture
def job(tmp_path, plan):
    sources, (manifest, files) = plan
    frozen = tmp_path / 'frozen'; frozen.mkdir()
    for name, raw in files.items(): c.p.base.write_new(frozen / name, raw)
    output = tmp_path / 'results'; output.mkdir()
    sha = c.p.digest(files['manifest.json']); code_sha = c.p.digest(Path(c.__file__).read_bytes())
    binding = c.collector_binding(manifest, sha, code_sha)
    for name, value in [('job.json', c.p.summary_job_binding(manifest, sha)), ('collector-binding.json', binding),
                        ('account-binding.json', c.p.generation.expected_account_binding(manifest))]: c.record(output / name, value)
    c.p.base.write_new(output / 'frozen-manifest.json', files['manifest.json'])
    state = {'contacts': 0, 'fail': False, 'reject_words': False, 'stop_after': False, 'duplicate': False}
    receipts = Receipts()
    def call(**kwargs):
        assert kwargs['timeout'] == 900 and kwargs['codex_receipt_policy'] == 'codex_native_rollout_v1'
        assert kwargs['attempt_number'] == 1 and kwargs['reasoning'] == 'high'
        kwargs['before_provider_attempt'](); state['contacts'] += 1
        sample = kwargs['output_dir']; row = json.loads((sample / 'condition.json').read_bytes())
        if state['fail']:
            (sample / 'native-failure.txt').write_bytes(b'retained synthetic failure')
            raise RuntimeError('Synthetic provider failure')
        answer = fixtures.answers(sources)[row['work_id']]
        if state['reject_words']: answer['summary_text'] = ' '.join(['summary'] * 649)
        final = c.p.canonical(answer); events = c.p.canonical({'thread_id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'same' if state['duplicate'] else row['work_id']))})
        artifacts = {}
        for name, filename, raw in [('codex_message','native-final.json',final), ('codex_events','native-events.json',events)]:
            c.p.base.write_new(sample / filename, raw); artifacts[name] = c.p.metadata(filename, raw)
        if state['stop_after']: (output / 'STOP').write_bytes(b'stop after current attempt')
        return final.decode('utf-8'), {'receipt_policy': 'codex_native_rollout_v1', 'provider_artifacts': artifacts}
    return {'manifest': manifest, 'files': files, 'frozen': frozen, 'output': output, 'sha': sha, 'code_sha': code_sha,
            'binding': binding, 'receipts': receipts, 'subset': sources[-1], 'state': state, 'call': call}


def collect(job, ordinal=0):
    return c.collect_one(job['manifest']['requests'][ordinal], job['manifest'], job['sha'], job['frozen'], job['output'],
                         job['call'], job['subset'], job['receipts'], job['binding'])


def replay(job, ordinal=0):
    row = job['manifest']['requests'][ordinal]
    return c.verify_sample(c.sample_path(job['output'], row), row, job['manifest'], job['sha'], job['frozen'],
                           job['subset'], job['receipts'], job['binding'])


def test_both_own_summaries_wrapper_roundtrip_to_unchanged_preparer(job):
    assert collect(job, 0) and collect(job, 1) and job['state']['contacts'] == 2
    wrapper = c.receipt_wrapper(job['frozen'] / 'manifest.json', job['output'], job['manifest'], job['sha'], job['frozen'],
                                job['subset'], job['receipts'], job['binding'])
    path = job['output'] / 'summary-receipts.json'
    c.publish_wrapper(path, wrapper); c.publish_wrapper(path, wrapper)
    summaries, retained = c.p.read_summaries(path, job['manifest'], job['files'], job['subset'], job['receipts'])
    assert set(summaries) == {'pg43','pg209'} and 'private/summary-wrapper.json' in retained
    assert wrapper['collector_sha256'] == job['code_sha'] and wrapper['generation_manifest_snapshot']['sha256'] == job['sha']
    assert wrapper['prior_runtime_manifest_file_sha256'] == c.p.RUNTIME_SHA and not wrapper['summary_semantically_verified']
    for row in job['manifest']['requests']:
        sample = c.sample_path(job['output'], row)
        assert (sample / 'source.txt').read_bytes() == job['files'][row['source']['path']]
        assert 'anchors' not in (sample / 'source-units.json').read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='wrapper differs'): c.publish_wrapper(path, {**wrapper, 'oracle_accepted': True})


@pytest.mark.parametrize('kind', ['provider', 'receipt', 'words'])
def test_failure_preserved_no_wrapper_or_resend(job, kind):
    if kind == 'provider': job['state']['fail'] = True
    if kind == 'receipt': job['receipts'].reject = True
    if kind == 'words': job['state']['reject_words'] = True
    assert not collect(job) and job['state']['contacts'] == 1
    terminal, answer = replay(job)
    assert answer is None and terminal['no_resend']
    assert terminal['state'] == ('generation_rejected' if kind == 'words' else 'unadmitted_no_resend')
    with pytest.raises(FileExistsError): collect(job)
    assert job['state']['contacts'] == 1 and not c.sample_path(job['output'], job['manifest']['requests'][1]).exists()
    with pytest.raises(ValueError, match='Both source summaries'): c.receipt_wrapper(job['frozen'] / 'manifest.json', job['output'],
        job['manifest'], job['sha'], job['frozen'], job['subset'], job['receipts'], job['binding'])


def test_stop_before_dispatch_and_after_current_settles(job):
    (job['output'] / 'STOP').write_bytes(b'stop')
    assert not collect(job) and job['state']['contacts'] == 0
    assert replay(job)[0]['state'] == 'unadmitted_no_resend'
    assert (job['output'] / 'stop-observed.json').is_file()


def test_stop_after_current_call_keeps_accepted_own_summary(job):
    job['state']['stop_after'] = True
    assert collect(job) and replay(job)[0]['state'] == 'accepted_generation'
    assert job['state']['contacts'] == 1 and (job['output'] / 'stop-observed.json').is_file()


def test_duplicate_native_identity_not_accepted(job):
    job['state']['duplicate'] = True
    assert collect(job, 0) and not collect(job, 1)
    assert replay(job, 1)[0]['state'] == 'unadmitted_no_resend'


@pytest.mark.parametrize('kind', ['source','prompt','final','account','binding'])
def test_exact_own_source_receipt_job_pins_reject_tamper(job, kind):
    assert collect(job)
    sample = c.sample_path(job['output'], job['manifest']['requests'][0])
    if kind == 'binding':
        (job['output'] / 'collector-binding.json').write_bytes(b'{}')
        with pytest.raises(ValueError, match='binding differs'): c.verify_job(job['output'], job['manifest'], job['sha'], job['code_sha'], job['files']['manifest.json'])
        return
    path = {'source': sample/'source.txt', 'prompt': sample/'prompt.txt', 'final': sample/'native-final.json',
            'account': job['output']/'account-binding.json'}[kind]
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises(ValueError): replay(job)


def test_validate_only_never_imports_helper_probes_or_writes(job, monkeypatch, capsys):
    fresh = job['output'].parent / 'fresh-results'
    monkeypatch.setattr('sys.argv', ['collector_summary.py', '--manifest', str(job['frozen']/'manifest.json'),
        '--manifest-sha256', job['sha'], '--collector-sha256', job['code_sha'], '--results-dir', str(fresh), '--validate-only'])
    original = c.p.load
    def only_readonly(name, path):
        assert Path(path).name != 'secondary-helper.py'
        return original(name, path)
    monkeypatch.setattr(c.p, 'load', only_readonly)
    assert c.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report['provider_calls'] == 0 and report['untouched'] == 2 and not fresh.exists()


def test_occupied_unresolved_no_contact_on_resume(job, monkeypatch):
    sample = c.sample_path(job['output'], job['manifest']['requests'][0]); sample.mkdir()
    monkeypatch.setattr('sys.argv', ['collector_summary.py', '--manifest', str(job['frozen']/'manifest.json'),
        '--manifest-sha256', job['sha'], '--collector-sha256', job['code_sha'], '--results-dir', str(job['output'])])
    with pytest.raises(ValueError, match='unresolved; no resend'): c.main()
    assert job['state']['contacts'] == 0


def test_wrong_manifest_collector_and_fresh_output_pins_refused(job):
    with pytest.raises(ValueError, match='pin differs'): c.load_manifest(job['frozen']/'manifest.json', '0'*64, job['code_sha'])
    with pytest.raises(ValueError, match='pin differs'): c.load_manifest(job['frozen']/'manifest.json', job['sha'], '0'*64)
    with pytest.raises(ValueError, match='outside repository'): c.p.generation.output_preflight(c.HERE / 'results', job['frozen'])
    with pytest.raises(ValueError, match='frozen inputs'): c.p.generation.output_preflight(job['frozen'] / 'results', job['frozen'])
