"""Provider-free, source-addressed long-form summary and judging preparation."""
from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generation = load('p4_runtime_generation', HERE.parent / 'hbq-semantic-crossform-p1b-v1/collect.py')
base = generation.prepare
canonical, digest, require = base.canonical, base.digest, base.require
POLICY = 'longform_dependency_pilot_v1'
SUMMARY_POLICY = 'independent_source_summary_v1'
ENDPOINTS = ('grok', 'sol')
SOURCE_PINS = {
    'agent-handoff.json': 'a2fc9099f4e23b9138189fc5d5c97057db01e3c44e8dd58f218caa4f21c7b8e9',
    'provenance.json': '01e5bcc8068464c4679aa292994109f3323e8c77a46d5f1ad7fa1247401f0485',
    'validation.json': 'ef4a5becf5fb72f3be76273706df9edcd7547e4aea27dbf54b7f5ddf86324f51',
    'indexes/pg43.json': '38154fab5b67109646bcb2ca529ed84446936b0f4dd0ca09fce3e5b385e265b7',
    'indexes/pg209.json': '2cde1fb7139c5c31a93c6744cf8fed1c7fb02dd4c0018e530fa3337febd39b74',
}
FETCH_SHA = '9cd448bb37db700e9bdcca77821f620f89aea63a9a6a9fe858ef5f7cca9dbdc1'
RUNTIME_SHA = '45c7ad4ea2eee0d8acecd877d8a1f9f27854c2d537b53fd9b27a0da7956cbb68'
N = 'craft.narrative.'
CASE_LEAVES = {
    'j_event_revelation': [N+'temporal_and_spatial_continuity.chronology', N+'temporal_and_spatial_continuity.elapsed_time', N+'exposition_and_information_management.fair_withholding'],
    'j_handwriting_knowledge': [N+'continuity_and_canon_integrity.knowledge', N+'exposition_and_information_management.reader_state', N+'exposition_and_information_management.fair_withholding'],
    'j_will_distant_link': [N+'continuity_and_canon_integrity.state', N+'continuity_and_canon_integrity.supersession', N+'foreshadowing_setup_and_payoff.preparation'],
    't_frame_transmission': [N+'temporal_and_spatial_continuity.chronology', N+'temporal_and_spatial_continuity.objects', N+'exposition_and_information_management.reader_state'],
    't_quint_identification': [N+'continuity_and_canon_integrity.knowledge', N+'exposition_and_information_management.reader_state', N+'exposition_and_information_management.fair_withholding'],
    't_letter_custody': [N+'temporal_and_spatial_continuity.objects', N+'temporal_and_spatial_continuity.state_update', N+'continuity_and_canon_integrity.knowledge'],
}
SOURCE_POLICY = ('SOURCE PROVENANCE OVERRIDE: These are pre-existing human-authored public-domain novellas, not AI-generated artifacts. '
    'Do not apply a default AI-authorship assumption, infer authorship from style, reward author fame, or treat familiarity as supplied evidence. '
    'No author brief, intended audience, canon decision or human evaluation labels have been supplied. ')


def metadata(path, raw):
    return {'path': path, 'sha256': digest(raw), 'bytes': len(raw)}


def read_sources(index_root):
    files = {}
    for relative, pin in SOURCE_PINS.items():
        raw = (index_root / relative).read_bytes()
        require(digest(raw) == pin, 'Source index commitment differs: ' + relative)
        files['source-index/' + relative] = raw
    handoff = json.loads(files['source-index/agent-handoff.json'])
    require(json.loads(files['source-index/provenance.json'])['handoff_sha256'] == SOURCE_PINS['agent-handoff.json'], 'Handoff lineage differs')
    fetch_root = index_root.parent / 'source-fetch-001'
    fetch_raw = (fetch_root / 'manifest.json').read_bytes()
    require(digest(fetch_raw) == FETCH_SHA, 'Raw source manifest commitment differs')
    fetch = json.loads(fetch_raw)
    files['source-fetch/manifest.json'] = fetch_raw
    works = {}
    for source in handoff['sources']:
        work_id = Path(source['file']).stem
        raw = (fetch_root / source['file']).read_bytes()
        text = raw.decode('utf-8-sig')
        narrative = (index_root / 'narratives' / source['file']).read_bytes()
        index = json.loads(files['source-index/indexes/' + work_id + '.json'])
        parent = next(r for r in fetch['sources'] if r['id'] == work_id)
        require(digest(raw) == source['source_sha256'] == parent['sha256'] == index['source_sha256']
                and len(raw) == source['raw_bytes'] == parent['bytes'], 'Original source bytes differ')
        lo, hi = source['narrative_char']; blo, bhi = source['narrative_byte']
        require(narrative == text[lo:hi].encode('utf-8') == raw[blo:bhi]
                and digest(narrative) == source['narrative_sha256_utf8'] == index['narrative_sha256']
                and index['source_char'] == [lo, hi] and index['source_byte'] == [blo, bhi], 'Narrative extraction differs')
        require(index['anchors'] == source['anchors'] and len(index['units']) == source['unit_count'], 'Index inventory differs')
        position = lo
        for unit in index['units']:
            a, b = unit['source_char']; x, y = unit['source_byte']
            unit_raw = text[a:b].encode('utf-8')
            require(a == position and unit_raw == raw[x:y] and digest(unit_raw) == unit['sha256']
                    and len(unit_raw) == unit['bytes'] and unit['narrative_char'] == [a-lo, b-lo], 'Source unit coordinates differ')
            position = b
        require(position == hi, 'Units do not cover full narrative')
        for anchor in index['anchors']:
            a, b = anchor['char']; x, y = anchor['byte']
            require(text[a:b] == anchor['quote'] and raw[x:y].decode('utf-8') == anchor['quote'], 'Anchor coordinates differ')
        for relative, value in [('source-fetch/' + source['file'], raw), ('narratives/' + source['file'], narrative)]:
            files[relative] = value
        receipt = (fetch_root / (work_id + '.receipt.json')).read_bytes()
        files['source-fetch/' + work_id + '.receipt.json'] = receipt
        works[work_id] = {'work_id': work_id, 'source': source, 'index': index, 'parent': parent, 'raw_text': text,
                         'narrative': narrative, 'input': metadata('narratives/' + source['file'], narrative)}
    require(set(works) == {'pg43', 'pg209'} and {c['id'] for c in handoff['case_proposals']} == set(CASE_LEAVES), 'Pilot source/case geometry differs')
    require(sum(len(w['index']['units']) for w in works.values()) == 35 and sum(len(w['index']['anchors']) for w in works.values()) == 26, 'Source geometry differs')
    return works, handoff['case_proposals'], files


def runtime_inputs(path):
    manifest, frozen, sha = base.read_manifest(path)
    require(sha == RUNTIME_SHA, 'Designated native runtime source manifest differs')
    generation.verify_external_pins(manifest)
    names = ('secondary-helper.py', 'runner.py', 'codex_receipts.py', 'schema_subset.py')
    files = {'private/source-generation-manifest.json': path.read_bytes()}
    files.update({'implementation/' + n: (frozen / 'implementation' / n).read_bytes() for n in names})
    files.update({'implementation/generation-' + n: (frozen / 'implementation' / n).read_bytes() for n in ('prepare.py', 'collect.py')})
    subset = load('p4_frozen_schema_subset', frozen / 'implementation/schema_subset.py')
    return manifest, files, subset


def own_inputs(files):
    paths = {'implementation/prepare.py': HERE / 'prepare.py', 'README.md': HERE / 'README.md',
             'implementation/validate_response.py': HERE / 'arms/validate_response.py',
             'implementation/core.py': REPO / 'src/hbqrs/core.py', 'implementation/scoring_v2.py': REPO / 'src/hbqrs/scoring_v2.py',
             'implementation/mfa-admission.py': HERE.parent / 'hbq-matched-mfa-v1/validate_response.py',
             'implementation/mfa-prepare.py': HERE.parent / 'hbq-matched-mfa-v1/prepare.py',
             'registry/all_modules.yaml': REPO / 'registry/all_modules.yaml', 'bundles/all_bundles.yaml': REPO / 'bundles/all_bundles.yaml',
             'schema/hbq_task_contract.schema.json': REPO / 'schema/hbq_task_contract.schema.json',
             'prompts/BINARY_EVALUATION_PROMPT.md': REPO / 'prompts/judge/BINARY_EVALUATION_PROMPT.md'}
    paths.update({'arms/' + p.name: p for p in (HERE / 'arms').iterdir() if p.is_file()})
    files.update({n: p.read_bytes() for n, p in paths.items()})


def finalize(stage, requests, files, runtime_source, **extra):
    manifest = {'schema_version': 1, 'study_id': POLICY, 'stage': stage, 'candidate': None, 'oracle_accepted': False,
        'human_labels_supplied': 0, 'human_alignment_claim': False, 'execution_authority': False, 'provider_calls_by_preparation': 0,
        'source_generation_manifest_file_sha256': RUNTIME_SHA, 'source_index_commitments': SOURCE_PINS,
        'runtime': {**runtime_source['runtime'], 'outbound_artifacts': 'Exact public human-authored narratives and source unit coordinates for summary generation; judging receives the declared source representation, task context, rubric/comparator criteria and schema. No human labels.'},
        'external_pins': runtime_source['external_pins'], 'requests': requests,
        **extra, 'artifacts': {n: metadata(n, raw) for n, raw in sorted(files.items())}}
    files['manifest.json'] = canonical(manifest)
    return manifest, files


def add_request(condition, files, requests, endpoint, ordinal):
    logical = digest(canonical(condition))
    row = {**condition, 'endpoint': endpoint, 'ordinal': len(requests)+1, 'endpoint_ordinal': ordinal,
           'logical_sample_id': logical}
    row['request_sha256'] = digest(canonical(row))
    requests.append(row)


def freeze_payload(files, prompt, schema):
    raw, schema_raw = prompt.encode('utf-8'), canonical(schema)
    p, s = 'prompts/' + digest(raw) + '.txt', 'schemas/' + digest(schema_raw) + '.json'
    files[p], files[s] = raw, schema_raw
    return {'prompt_path': p, 'prompt_sha256': digest(raw), 'prompt_bytes': len(raw),
            'schema_path': s, 'schema_sha256': digest(schema_raw), 'schema_bytes': len(schema_raw)}


def summary_plan(works, source_files, runtime_source, runtime_files, subset):
    files = {**source_files, **runtime_files}; own_inputs(files)
    requests = []
    for work_id, work in sorted(works.items()):
        schema = json.loads(files['arms/summary.schema.json'])
        schema['properties']['work_id']['enum'] = [work_id]
        schema['properties']['source_narrative_sha256']['enum'] = [work['input']['sha256']]
        subset.validate_schema(schema)
        units = [{k: u[k] for k in ('id', 'kind', 'heading', 'source_char', 'narrative_char')} for u in work['index']['units']]
        prompt = (files['arms/summary.prompt.md'].decode('utf-8') + '\nWORK_ID ' + work_id + '\nSOURCE_NARRATIVE_SHA256 ' + work['input']['sha256']
                  + '\nSOURCE UNIT COORDINATES (source and narrative offsets are distinct)\n' + canonical(units).decode('utf-8')
                  + '\n<<< BEGIN EXACT HUMAN-AUTHORED NARRATIVE >>>\n' + work['narrative'].decode('utf-8') + '<<< END EXACT NARRATIVE >>>\n')
        condition = {'stage': 'summary_generation', 'summary_policy': SUMMARY_POLICY, 'work_id': work_id,
                     'source': work['input'], 'unit_index_sha256': digest(source_files['source-index/indexes/' + work_id + '.json']),
                     **freeze_payload(files, prompt, schema)}
        add_request(condition, files, requests, 'sol', len(requests)+1)
    return finalize('source_summary_generation', requests, files, runtime_source,
                    counts={'works': 2, 'summary_generation_calls': 2, 'judging_requests_planned': 464},
                    summary_policy=SUMMARY_POLICY, summaries_semantically_verified=False)


def validate_summary(row, answer, schema, subset):
    require(subset.matches_schema(answer, schema), 'Summary response schema differs')
    require(answer['work_id'] == row['work_id'] and answer['source_narrative_sha256'] == row['source']['sha256'], 'Summary source identity differs')
    require(650 <= len(answer['summary_text'].split()) <= 1000, 'Summary must contain 650–1000 whitespace-separated words')
    require(1 <= len(answer['attribution_notes']) <= 8 and 1 <= len(answer['uncertainties']) <= 8, 'Summary note cardinality differs')
    require(all(v.strip() for v in [*answer['attribution_notes'], *answer['uncertainties']]), 'Summary attribution/uncertainty is blank')
    return {'accepted_generation': True, 'oracle_accepted': False, 'summary_semantically_verified': False,
            'summary_words': len(answer['summary_text'].split()), 'summary_sha256': digest(answer['summary_text'].encode('utf-8'))}


def summary_job_binding(manifest, manifest_sha):
    return {'schema_version': 1, 'generation_manifest_sha256': manifest_sha, 'summary_policy': SUMMARY_POLICY,
            'runtime': manifest['runtime'], 'external_pins': manifest['external_pins'],
            'implementation_pins': {k: v['sha256'] for k, v in manifest['artifacts'].items() if k.startswith('implementation/')},
            'automatic_retries': 0, 'no_ambiguous_resend': True, 'oracle_accepted': False}


def read_summaries(wrapper_path, expected_plan, expected_files, subset, receipts=None):
    require(wrapper_path is not None, 'Required independently generated summaries are pending; judging freeze refused')
    raw = wrapper_path.read_bytes(); wrapper = json.loads(raw); root = wrapper_path.resolve().parent
    require(wrapper['schema_version'] == 1 and wrapper['policy'] == 'longform_source_summary_receipts_v1', 'Summary wrapper policy differs')
    generation_path = (root / wrapper['generation_manifest']['path']).resolve()
    generation_raw = generation_path.read_bytes(); expected_sha = digest(expected_files['manifest.json'])
    require(digest(generation_raw) == wrapper['generation_manifest']['sha256'] == expected_sha
            and json.loads(generation_raw) == expected_plan, 'Exact source summary generation freeze differs')
    frozen = generation_path.parent
    for name, meta in expected_plan['artifacts'].items():
        require(base.within(frozen, name).read_bytes() == expected_files[name], 'Summary generation artifact differs')
    entries = wrapper['summaries']
    require(len(entries) == 2 and {e['work_id'] for e in entries} == {'pg43', 'pg209'}, 'Both distinct source summaries required')
    if receipts is None:
        receipts = load('p4_summary_receipts', frozen / 'implementation/codex_receipts.py')
    summaries, retained, native_ids = {}, {'private/summary-wrapper.json': raw}, set()
    for entry in entries:
        row = next(r for r in expected_plan['requests'] if r['work_id'] == entry['work_id'])
        sample = (root / entry['sample_path']).resolve()
        require(entry['logical_sample_id'] == row['logical_sample_id'], 'Summary logical identity differs')
        require(json.loads((sample.parent / 'job.json').read_bytes()) == summary_job_binding(expected_plan, expected_sha), 'Summary job binding differs')
        terminal_raw = (sample / 'terminal.json').read_bytes(); terminal = json.loads(terminal_raw)
        require(terminal['state'] == 'accepted_generation' and terminal['no_resend'] is True
                and terminal['manifest_sha256'] == expected_sha and terminal['logical_sample_id'] == row['logical_sample_id'], 'Summary is not a settled accepted own attempt')
        raw_records = {n: (sample / (n + '.json')).read_bytes() for n in ('condition', 'attempt-started', 'native-result', 'response', 'validation')}
        require(all(digest(v) == terminal[n + '_sha256'] for n, v in raw_records.items()), 'Summary attempt commitment differs')
        require(json.loads(raw_records['condition']) == row, 'Summary condition differs')
        started = json.loads(raw_records['attempt-started'])
        require(started['manifest_sha256'] == expected_sha and started['logical_sample_id'] == row['logical_sample_id']
                and started['attempt'] == 1 and started['no_resend'] is True
                and started['prompt_sha256'] == row['prompt_sha256'] and started['schema_sha256'] == row['schema_sha256'], 'Summary attempt source/prompt/schema differs')
        account_raw = (sample.parent / 'account-binding.json').read_bytes()
        require(digest(account_raw) == started['account_binding_sha256']
                and json.loads(account_raw) == generation.expected_account_binding(expected_plan), 'Summary secondary account binding differs')
        prompt_raw, schema_raw = expected_files[row['prompt_path']], expected_files[row['schema_path']]
        require((sample / 'prompt.txt').read_bytes() == prompt_raw and (sample / 'schema.json').read_bytes() == schema_raw, 'Summary prompt/schema copy differs')
        provider = json.loads(raw_records['native-result'])
        final_raw = base.within(sample, provider['provider_artifacts']['codex_message']['path']).read_bytes()
        receipts.verify(sample, provider, prompt=prompt_raw.decode('utf-8'), model=expected_plan['runtime']['model'],
                        reasoning=expected_plan['runtime']['reasoning'], final_raw=final_raw)
        events = base.within(sample, provider['provider_artifacts']['codex_events']['path']).read_bytes()
        native_id, _ = receipts.event_identity(events, final_raw)
        require(native_id not in native_ids, 'Duplicate native summary identity'); native_ids.add(native_id)
        answer = json.loads(raw_records['response'])
        require(answer == json.loads(final_raw), 'Summary response differs from native final')
        validation = validate_summary(row, answer, json.loads(schema_raw), subset)
        require(validation == json.loads(raw_records['validation']), 'Summary admission differs')
        summary_meta = terminal['derived_summary']
        summary_raw = base.within(sample, summary_meta['path']).read_bytes()
        require(summary_raw == answer['summary_text'].encode('utf-8') and digest(summary_raw) == summary_meta['sha256']
                and len(summary_raw) == summary_meta['bytes'], 'Derived summary differs from accepted own source')
        summaries[row['work_id']] = answer
        stem = 'private/summary-lineage/' + row['work_id'] + '/'
        retained.update({stem + n + '.json': v for n, v in raw_records.items()})
        retained[stem + 'terminal.json'] = terminal_raw
        retained[stem + 'account-binding.json'] = account_raw
        for name, meta in provider['provider_artifacts'].items():
            retained[stem + name + '.bin'] = base.within(sample, meta['path']).read_bytes()
    retained['private/summary-generation-manifest.json'] = generation_raw
    return summaries, retained


def task_contract(work_id, diagnostic):
    return {'contract_version': 1, 'contract_id': POLICY + ('_dependency' if diagnostic else '_whole_work'), 'artifact_id': work_id,
            'context': {'artifact_kind': 'prose_fiction', 'declared_scope': 'manuscript', 'completion_status': 'complete',
                'background': [], 'audience': [], 'constraints': [SOURCE_POLICY,
                    'The target is the original complete novella. Available reduced context is not complete-work artistic evidence; preserve CANNOT_ASSESS where evidence is missing.'
                    if diagnostic else 'Assess the supplied complete original novella only; no summary or annotated map is available.']},
            'preferences': [], 'priorities': [], 'weighted_goals': [], 'binding_requirements': []}


def anchored_representation(work, case):
    parts = ['SOURCE-ADDRESSED EXCERPTS; offsets below refer to ORIGINAL SOURCE characters, not narrative-relative positions.\n']
    start, end = work['source']['narrative_char']
    for lo, hi in case['context_windows_char']:
        require(start <= lo < hi <= end, 'Case window escapes original narrative')
        parts += [f'\nSOURCE CHAR [{lo},{hi})\n', work['raw_text'][lo:hi], '\n']
    anchors = {a['id']: a for a in work['index']['anchors']}
    require(set(case['anchors']) <= anchors.keys(), 'Case anchor absent')
    parts += ['\nPROPOSED AGENT ANNOTATIONS (not an interpretation oracle)\n',
              json.dumps({'minimal_map': case['minimal_map'], 'uncertainty': case['uncertainty'],
                          'anchor_addresses': [anchors[a] for a in case['anchors']]}, ensure_ascii=False, indent=2)]
    return ''.join(parts).encode('utf-8')


def render_hbq(runner, binary, representation, packet, work_id, projection, diagnostic_brief):
    marker = '__P4_EXACT_SOURCE_BODY_SPLICE_V1__'
    prefix = SOURCE_POLICY + diagnostic_brief + '\n'
    prompt = runner._render_prompt(binary_prompt=prefix + binary, artifact={'name': work_id, 'text': marker}, contexts=[],
        bundle_id='prose.novella', artifact_id=work_id, questions=packet, task_contract_context=projection)
    require(prompt.count(marker) == 1 and marker not in representation, 'Exact body splice marker collides')
    return prompt.replace(marker, representation, 1)


def judging_plan(works, cases, source_files, runtime_source, runtime_files, subset, summaries, summary_files):
    require(set(summaries) == set(works), 'Both independently generated summaries are required before judging freeze')
    files = {**source_files, **runtime_files, **summary_files}; own_inputs(files)
    sys.path.insert(0, str(REPO / 'src'))
    from hbqrs import core, runner
    from jsonschema import Draft202012Validator
    mfa = load('p4_portable_schema', HERE.parent / 'hbq-matched-mfa-v1/prepare.py')
    modules = core.load_modules(REPO / 'registry/all_modules.yaml')
    bundle = core.resolve_bundle(core.load_bundles(REPO / 'bundles/all_bundles.yaml'), 'prose.novella')
    compiled = core.compile_bundle(modules, bundle); questions = core.compiled_questions(compiled)
    require(compiled['counts'] == {'domain_questions': 175, 'hard_gates': 1, 'penalty_questions': 18, 'supplemental_questions': 25}
            and len(questions) == len({q['question']['id'] for q in questions}) == 219, 'Canonical novella geometry differs')
    by_id = {q['question']['id']: q for q in questions}
    require(set(q for ids in CASE_LEAVES.values() for q in ids) <= by_id.keys(), 'Mapped case leaf absent from canonical novella')
    files['compiled/prose.novella.json'] = canonical(compiled)
    contract_schema = json.loads(files['schema/hbq_task_contract.schema.json'])
    contracts, contexts = {}, {}
    for work_id in works:
        for scope in ('diagnostic', 'whole_work'):
            contract = task_contract(work_id, scope == 'diagnostic')
            Draft202012Validator(contract_schema).validate(contract)
            require(core.compiled_questions(core.compile_bundle(modules, bundle, task_contract=contract)) == questions, 'Context altered canonical questions')
            path = 'contracts/' + work_id + '-' + scope + '.json'; files[path] = canonical(contract)
            projection = runner._task_contract_judge_context(contract)
            raw = json.dumps(projection, ensure_ascii=False, indent=2).encode('utf-8')
            context_path = 'contexts/' + digest(raw) + '.json'; files[context_path] = raw
            contexts[(work_id, scope)] = metadata(context_path, raw)
            contracts[(work_id, scope)] = {'artifact_id': work_id, 'path': path, 'sha256': digest(files[path]), 'projection': projection}
    assets = {}
    for kind, arm in [('dependency', 'holistic'), ('novella', 'holistic'), ('novella', 'compact')]:
        original = (HERE.parent / 'hbq-matched-ttcw-20261004/arms' / (arm + '.schema.json')).read_bytes()
        schema = json.loads(original)
        schema['properties']['result']['properties']['method']['enum'] = ['p4_' + kind + '_' + arm + '_v1']
        files['arms/' + kind + '-' + arm + '.original.schema.json'] = original
        files['arms/' + kind + '-' + arm + '.retained.schema.json'] = canonical(schema)
        assets[(kind, arm)] = schema
    sentinel = min(works, key=lambda w: digest(canonical([POLICY, 'whole_bank_sentinel_metadata_v1', w, works[w]['input']['sha256']])))
    units = []
    for case in cases:
        work_id = Path(case['source']).stem; work = works[work_id]
        answer = summaries[work_id]
        summary_raw = (answer['summary_text'] + '\n\nATTRIBUTION NOTES\n' + '\n'.join(answer['attribution_notes'])
                       + '\nUNRESOLVED UNCERTAINTIES\n' + '\n'.join(answer['uncertainties'])).encode('utf-8')
        variants = {'raw_full': work['narrative'], 'anchored_map': anchored_representation(work, case), 'summary_only': summary_raw}
        for mode, raw in variants.items():
            path = 'representations/' + digest(raw) + '.txt'; files[path] = raw
            for cycle in range(3):
                for arm in ('hbq', 'holistic'):
                    units.append({'contract': 'unscored_dependency_diagnostic', 'scope': 'diagnostic', 'case_id': case['id'],
                        'case_question': case['question'], 'work_id': work_id, 'context_arm': mode, 'repeat': cycle, 'arm': arm,
                        'input': metadata(path, raw), 'packets': [CASE_LEAVES[case['id']]] if arm == 'hbq' else [[]]})
    for work_id, work in works.items():
        for cycle in range(3):
            for arm in ('hbq', 'holistic', 'compact'):
                if arm == 'hbq' and cycle > 0 and work_id != sentinel: continue
                units.append({'contract': 'whole_work_baseline', 'scope': 'whole_work', 'work_id': work_id,
                    'context_arm': 'raw_full', 'repeat': cycle, 'arm': arm, 'input': work['input'],
                    'packets': [[q['question']['id'] for q in questions[n:n+8]] for n in range(0, 219, 8)] if arm == 'hbq' else [[]]})
    units.sort(key=lambda u: (u['repeat'], digest(canonical([POLICY, 'unit_order_v1', u]))))
    requests, ordinals = [], Counter()
    for unit in units:
        work_id, scope, arm = unit['work_id'], unit['scope'], unit['arm']
        diagnostic = scope == 'diagnostic'
        context_meta = contexts[(work_id, scope)]; context = files[context_meta['path']].decode('utf-8')
        contract_meta = {k: v for k, v in contracts[(work_id, scope)].items() if k != 'projection'}
        representation = files[unit['input']['path']].decode('utf-8')
        brief = ('Unscored dependency diagnostic for the original complete novella, using only the supplied representation. Missing original evidence may require CANNOT_ASSESS; no whole-work score or oracle. '
                 'Never quote unavailable original text from memory. Case question: ' + unit['case_question']) if diagnostic else 'Whole-work baseline; complete original narrative supplied. No summary or annotated dependency map is supplied.'
        for batch, ids in enumerate(unit['packets'], 1):
            retained = runner._batch_response_schema(ids) if arm == 'hbq' else assets[('dependency' if diagnostic else 'novella', arm)]
            schema = mfa.portable_schema(retained); subset.validate_schema(schema)
            retained_path = 'retained-schemas/' + digest(canonical(retained)) + '.json'; files[retained_path] = canonical(retained)
            if arm == 'hbq':
                prompt = render_hbq(runner, files['prompts/BINARY_EVALUATION_PROMPT.md'].decode('utf-8'), representation,
                    [by_id[i] for i in ids], work_id, contracts[(work_id, scope)]['projection'], brief)
            else:
                name = ('dependency' if diagnostic else 'novella') + '-' + arm + '.prompt.md'
                prompt = SOURCE_POLICY + brief + '\n' + files['arms/' + name].decode('utf-8') + '\nTASK CONTEXT\n' + context + '\nEXACT AVAILABLE REPRESENTATION\n' + representation
            require(context in prompt and representation in prompt, 'Declared context/source bytes absent from prompt')
            condition = {k: v for k, v in unit.items() if k not in ('scope', 'packets', 'input', 'case_question')}
            condition.update(artifact_id=work_id, bundle_id='prose.novella', batch=batch, question_ids=ids,
                sources=[{'id': work_id, 'input_path': unit['input']['path'], 'sha256': unit['input']['sha256'], 'bytes': unit['input']['bytes']}],
                target_original=works[work_id]['input'], task_context=context_meta, task_contracts=[contract_meta],
                compiled_sha256=digest(files['compiled/prose.novella.json']), full_bank_score_eligible=not diagnostic and arm == 'hbq',
                whole_work_artistic_score=not diagnostic, prompt_policy='human_authored_source_override_v1',
                rendering_policy='exact_source_body_splice_v1' if arm == 'hbq' else 'exact_source_concat_v1',
                retained_schema_path=retained_path, retained_schema_sha256=digest(files[retained_path]), **freeze_payload(files, prompt, schema))
            for endpoint in ENDPOINTS if int(digest(canonical(condition))[-1], 16) % 2 == 0 else ENDPOINTS[::-1]:
                ordinals[endpoint] += 1; add_request(condition, files, requests, endpoint, ordinals[endpoint])
    counts = Counter((r['contract'], r['endpoint'], r['arm']) for r in requests)
    require(len(requests) == 464 and all(counts[('unscored_dependency_diagnostic', ep, a)] == 54 for ep in ENDPOINTS for a in ('hbq', 'holistic'))
            and all(counts[('whole_work_baseline', ep, 'hbq')] == 112 and counts[('whole_work_baseline', ep, 'holistic')] == 6
                    and counts[('whole_work_baseline', ep, 'compact')] == 6 for ep in ENDPOINTS), 'P4 judging geometry differs')
    return finalize('matched_judging_preparation', requests, files, runtime_source,
        counts={'works': 2, 'cases': 6, 'case_leaf_instances': 18, 'unique_case_leaves': 10, 'cycles': 3,
                'diagnostic_requests': 216, 'whole_work_requests': 248, 'requests_total': 464, 'requests_per_endpoint': 232,
                'whole_bank_leaves': 219, 'whole_bank_packets': 28, 'summary_generation_calls_separate': 2},
        whole_bank_sentinel={'work_id': sentinel, 'selection_policy': 'whole_bank_sentinel_metadata_v1', 'cycles': [0, 1, 2]},
        context_delivery={'full_narrative_bytes': {w: x['input']['bytes'] for w, x in works.items()},
            'raw_full_request_source_bytes_sum': sum(r['sources'][0]['bytes'] for r in requests if r['context_arm'] == 'raw_full'),
            'all_prompt_bytes_sum': sum(r['prompt_bytes'] for r in requests), 'supported_context_window_or_native_delivery_proven': False},
        scoring={'diagnostic': 'Never aggregate selected three leaves into a whole-work score; preserve native CA/N/A and source access.',
                 'whole_work': 'Only unique admitted complete219-leaf banks may use frozen canonical scoring_v2; gates/coverage/bounds retained.'},
        runtime_bindings={'sol': 'Designated secondary source runtime; exact helper/CLI/account pins retained; live job/account gate remains required.',
                          'grok': 'Endpoint-neutral requests only; reviewed route/model/account/deadline binding required before dispatch.'},
        limitations=['Two famous human-authored novellas; model familiarity possible, no unseen-work generalization.',
            'Agent maps and summaries are proposed source representations, not human labels or interpretation oracles.',
            'Summary admission attests source/native lineage and structure, not factual or aesthetic correctness.',
            'Reduced-context diagnostic ratings are scoped and cannot establish whole-work artistic validation.',
            'Full input bytes in frozen prompt do not establish native context delivery or absence of truncation.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-index', type=Path, required=True)
    parser.add_argument('--runtime-manifest', type=Path, required=True)
    parser.add_argument('--summary-manifest', type=Path)
    parser.add_argument('--prepare-summary', action='store_true')
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        require(not (args.prepare_summary and args.summary_manifest), 'Summary generation and judging inputs are distinct modes')
        base.output_preflight(args.output_root, (args.source_index, args.source_index.parent / 'source-fetch-001', args.runtime_manifest.resolve().parent,
                                               *((args.summary_manifest,) if args.summary_manifest else ())))
        works, cases, source_files = read_sources(args.source_index.resolve())
        runtime, runtime_files, subset = runtime_inputs(args.runtime_manifest.resolve())
        plan, files = summary_plan(works, source_files, runtime, runtime_files, subset)
        if not args.prepare_summary and args.summary_manifest is None:
            print(json.dumps({'state': 'pending_independent_source_summaries', 'freeze_refused': True,
                              'summary_generation_calls_required': 2, 'judging_requests_planned': 464, 'provider_calls': 0, 'candidate': None}))
            return 0 if args.dry_run else 2
        if not args.prepare_summary:
            wrapper = json.loads(args.summary_manifest.read_bytes())
            wrapper_root = args.summary_manifest.resolve().parent
            retained_roots = [(wrapper_root / wrapper['generation_manifest']['path']).resolve().parent]
            retained_roots += [(wrapper_root / e['sample_path']).resolve().parent for e in wrapper['summaries']]
            base.output_preflight(args.output_root, retained_roots)
            summaries, lineage = read_summaries(args.summary_manifest.resolve(), plan, files, subset)
            plan, files = judging_plan(works, cases, source_files, runtime, runtime_files, subset, summaries, lineage)
        if not args.dry_run:
            args.output_root.mkdir(parents=True, exist_ok=False)
            for name, raw in files.items(): base.write_new(base.within(args.output_root, name), raw)
        print(json.dumps({'state': 'dry_run_without_contact' if args.dry_run else 'prepared_without_contact',
            'stage': plan['stage'], 'manifest_sha256': digest(files['manifest.json']), 'counts': plan['counts'],
            'artifact_bytes': sum(len(v) for v in files.values()), 'provider_calls': 0, 'candidate': None,
            'whole_bank_sentinel': plan.get('whole_bank_sentinel'), 'context_delivery': plan.get('context_delivery')}, sort_keys=True))
        return 0
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, 'Long-form preparation failed: ' + str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
