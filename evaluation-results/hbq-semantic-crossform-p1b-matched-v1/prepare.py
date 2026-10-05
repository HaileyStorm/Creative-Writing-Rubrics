"""Freeze descriptive P1b matched requests without inference or oracle promotion."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
import importlib.util


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generation = load_module('descriptive_p1b_generation', HERE.parent / 'hbq-semantic-crossform-p1b-v1/collect.py')
source_prepare = generation.prepare
canonical, digest, require = source_prepare.canonical, source_prepare.digest, source_prepare.require
POLICY = 'descriptive_synthetic_matched_crossform_v1'
GENERATION_SHA = '45c7ad4ea2eee0d8acecd877d8a1f9f27854c2d537b53fd9b27a0da7956cbb68'
REVIEW_PINS = {
    'reviewer-response.json': 'a70bc70cd0634278b1dcb284ed109b6d6c868357d4503db36c6898c82101035b',
    'validation.json': '4418ea03ce1d8215241cf39b3a797f1d9c695397ce8cbe57253e1def6c7279fb',
    'owner-decision.json': 'e99d799429a3de8925de61667ddfaf998b9b99e284d9306acdaa58b0549f7d35',
}
ROUTES = {
    'short_narrative': ('prose.short_story', 'prose_fiction', 'story', 'complete', 178, 23),
    'novel_work_segment': ('prose.short_form', 'prose_fiction', 'passage', 'excerpt', 170, 22),
    'poem': ('poetry.free_verse', 'poetry', 'poem', 'complete', 89, 12),
}
EXPECTED_COUNTS = {
    'prose.short_story': {'domain_questions': 143, 'hard_gates': 0, 'penalty_questions': 18, 'supplemental_questions': 17},
    'prose.short_form': {'domain_questions': 135, 'hard_gates': 0, 'penalty_questions': 18, 'supplemental_questions': 17},
    'poetry.free_verse': {'domain_questions': 60, 'hard_gates': 0, 'penalty_questions': 18, 'supplemental_questions': 11},
}
POETRY_DIMENSIONS = ['poetic_architecture', 'image_relations', 'language_voice', 'rhythm_lineation',
                     'emotional_reader_effect', 'meaning_resonance']
ROLE_MARKER = r'\b(?:target[ _-]+defect|legitimate[ _-]+style|target[ _-]+descendant)\b'
ENDPOINTS = ('grok', 'sol')
ARMS = ('hbq', 'holistic', 'compact', 'pairwise')
ESTABLISHED = {'short_narrative': ('ttcw14', 'oregon'), 'novel_work_segment': (), 'poem': ('poemetric',)}
TTCW_TESTS_SHA = '1f305d408e3f89bb526023a0f04d58428b096aef66b5d748b81579036f3be5a8'


def read_authorization(root):
    raw = {name: (root / name).read_bytes() for name in REVIEW_PINS}
    require(all(digest(raw[name]) == pin for name, pin in REVIEW_PINS.items()), 'Review/owner authorization commitment differs')
    decision = json.loads(raw['owner-decision.json'])
    require(decision['decision_policy'] == 'descriptive_synthetic_stimuli_without_oracle_promotion_v1'
            and decision['review_sha256'] == REVIEW_PINS['reviewer-response.json']
            and decision['validation_sha256'] == REVIEW_PINS['validation.json']
            and decision['candidate'] is None and decision['accepted_oracle_families'] == []
            and decision['canonical_promotion'] is False and decision['fixed_synthetic_labels'] is False
            and decision['intended_defect_success_rate_eligible'] is False, 'Descriptive authorization differs')
    # Reviews are committed as raw provenance, never decoded into selection labels.
    return {'review/' + name: value for name, value in raw.items()}


def read_accepted(manifest_path, results, *, expected_sha=GENERATION_SHA):
    manifest, frozen, sha = source_prepare.read_manifest(manifest_path)
    require(sha == expected_sha, 'Exact frozen generation manifest differs')
    require(manifest['counts']['families'] == 8 and len(manifest['requests']) == 8, 'All eight prospective families required')
    job_raw = (results / 'job.json').read_bytes()
    require(json.loads(job_raw) == generation.job_binding(manifest, sha), 'Generation job binding differs')
    for name, module in [('collect.py', generation), ('prepare.py', source_prepare)]:
        require(digest(Path(module.__file__).read_bytes()) == manifest['artifacts']['implementation/' + name]['sha256'],
                'Generation verification implementation differs')
    receipts = load_module('descriptive_frozen_receipts', frozen / 'implementation/codex_receipts.py')
    subset = load_module('descriptive_frozen_subset', frozen / 'implementation/schema_subset.py')
    entries = []
    for row in manifest['requests']:
        sample = generation.sample_path(results, row)
        terminal = generation.verify_accepted(sample, row, manifest, sha, frozen, receipts, subset)
        response_raw = (sample / 'response.json').read_bytes()
        commitments = {name + '_sha256': digest((sample / (name + '.json')).read_bytes())
                       for name in ('terminal', 'response', 'native-result', 'validation', 'attempt-started')}
        commitments['derived_artifacts'] = terminal['derived_artifacts']
        entries.append((row, json.loads(response_raw), commitments))
    files = {'private/source-generation-manifest.json': manifest_path.read_bytes(),
             'private/generation-job.json': job_raw}
    return manifest, entries, files, subset


def read_ttcw_tests(path):
    raw = path.read_bytes()
    require(digest(raw) == TTCW_TESTS_SHA, 'Original TTCW questions/definitions commitment differs')
    rows = json.loads(raw)
    require([r['ttcw_idx'] for r in rows] == list(range(1, 15)), 'Original TTCW test identities differ')
    return {'sources/ttcw-tests.json': raw}


def task_contract(artifact_id, form, brief, shared):
    _, kind, scope, completion, _, _ = ROUTES[form]
    constraints = ['Assess only the supplied artifact and context; visible local defects remain assessable.']
    if completion == 'excerpt':
        constraints += ['Explicitly flagged bounded passage; no whole-novel or completed-chapter claim. '
                        'Do not require whole-work closure, unseen setup/payoff or a completed character arc.']
    if form == 'poem':
        constraints += ['Text-only free verse; no required rhyme, fixed meter, linear plot, or change on every line. '
                        'Stillness, juxtaposition, refrain and circular architecture may be legitimate.']
    return {'contract_version': 1, 'contract_id': POLICY + '_' + form, 'artifact_id': artifact_id,
            'context': {'artifact_kind': kind, 'declared_scope': scope, 'completion_status': completion,
                        'background': [brief] + ([shared] if shared else []), 'constraints': constraints, 'audience': []},
            'preferences': [], 'priorities': [], 'weighted_goals': [], 'binding_requirements': []}


def source_inventory(manifest, entries):
    texts, families, mapping, source_to_opaque = {}, [], [], {}
    for row, answer, commitments in entries:
        family = row['family']
        require(answer['family_id'] == family['family_id'] and answer['form'] == family['form']
                and answer['scope'] == family['scope'], 'Accepted family identity differs')
        key = digest(canonical({'source_manifest': digest(canonical(manifest)), 'logical_sample': row['logical_sample_id']}))
        family_id = 'family-' + key[:20]
        ids = []
        private_variants = {}
        for role in source_prepare.VARIANTS:
            variant = answer['variants'][role]
            require(variant['variant_id'] == family['variant_ids'][role], 'Accepted variant identity differs')
            raw = variant['text'].encode('utf-8')
            require(not re.search(ROLE_MARKER, variant['text'], re.IGNORECASE)
                    and not re.search(r'^\s*(?:#{1,6}\s*)?original(?:\s+variant)?(?:\s*[:\-]|\s*$)',
                                      variant['text'], re.IGNORECASE | re.MULTILINE), 'Generation role label leaks into creative text')
            variant_id = 'variant-' + digest(canonical({'family': key, 'text_sha256': digest(raw)}))[:20]
            require(variant_id not in texts, 'Duplicate opaque variant identity')
            texts[variant_id] = {'id': variant_id, 'family_id': family_id, 'form': family['form'],
                                 'sha256': digest(raw), 'bytes': len(raw), 'raw': raw}
            ids.append(variant_id)
            source_to_opaque[variant['variant_id']] = variant_id
            private_variants[variant_id] = {'role': role, 'source_variant_id': variant['variant_id'], 'text_sha256': digest(raw)}
        shared = answer['work_context']
        require(bool(shared) == (family['form'] == 'novel_work_segment'), 'Shared work context does not fit declared form')
        visible = canonical([family['brief'], shared]).decode('utf-8')
        require(not re.search(ROLE_MARKER, visible, re.IGNORECASE)
                and all(value not in visible for value in family['variant_ids'].values()), 'Generation role leaks into shared task context')
        families.append({'family_id': family_id, 'form': family['form'], 'variant_ids': sorted(ids),
                         'brief': family['brief'], 'shared_work_context': shared})
        mapping.append({'family_id': family_id, 'source_family_id': family['family_id'], 'variants': private_variants,
                        'generation_semantics_bundle': family['bundle_id'], 'generation_target_question_id': family['target_question_id'],
                        'source_commitments': commitments})
    require(Counter(f['form'] for f in families) == Counter({'short_narrative': 4, 'novel_work_segment': 2, 'poem': 2})
            and len(texts) == 24, 'Complete form geometry differs')
    pairs, private_pairs = [], []
    family_by_variant = {v: f for f in families for v in f['variant_ids']}
    for original in manifest['pairs']:
        left, right = [source_to_opaque[original[k]] for k in ('left_variant_id', 'right_variant_id')]
        require(left != right and family_by_variant[left]['family_id'] == family_by_variant[right]['family_id'], 'Pair family differs')
        family = family_by_variant[left]
        pair_id = 'pair-' + digest(canonical([POLICY, family['family_id'], sorted([left, right])]))[:20]
        pairs.append({'pair_id': pair_id, 'family_id': family['family_id'], 'form': family['form'], 'left': left, 'right': right})
        private_pairs.append({'pair_id': pair_id, 'source_comparison': original})
    require(len(pairs) == 16 and len({p['pair_id'] for p in pairs}) == 16
            and all(sum(p['family_id'] == f['family_id'] for p in pairs) == 2 for f in families), 'Declared pair inventory differs')
    return texts, families, pairs, {'families': mapping, 'pairs': private_pairs}


def sentinels(families, pairs):
    banks, repeated_pairs = [], []
    for form, count in [('short_narrative', 2), ('novel_work_segment', 1), ('poem', 1)]:
        for kind in ('bank', 'pair'):
            selected = sorted([f for f in families if f['form'] == form],
                              key=lambda f: digest(canonical([POLICY, kind + '_family_sentinel_v1', f['family_id']])))[:count]
            for family in selected:
                options = family['variant_ids'] if kind == 'bank' else [p['pair_id'] for p in pairs if p['family_id'] == family['family_id']]
                chosen = min(options, key=lambda value: digest(canonical([POLICY, kind + '_member_sentinel_v1', value])))
                (banks if kind == 'bank' else repeated_pairs).append(chosen)
    return sorted(banks), sorted(repeated_pairs)


def arm_assets(form, files):
    root = HERE.parent / ('hbq-matched-ttcw-20261004' if form == 'short_narrative' else 'hbq-matched-mfa-v1')
    result = {}
    for arm in (*ARMS[1:], *ESTABLISHED[form]):
        prompt_path = (HERE / 'arms' / ('poemetric.prompt.md' if arm == 'poemetric' else 'poetry-' + arm + '.prompt.md')) if form == 'poem' else root / 'arms' / (arm + '.prompt.md')
        prompt = prompt_path.read_bytes()
        schema_raw = ((HERE if arm == 'poemetric' else root) / 'arms' / (arm + '.schema.json')).read_bytes()
        schema = json.loads(schema_raw)
        if form == 'poem' and arm != 'poemetric':
            properties = schema['properties']['result']['properties'] if arm != 'pairwise' else schema['properties']
            properties['method']['enum'] = ['p1b_free_verse_' + arm + '_v1']
            if arm == 'compact':
                properties['dimensions']['items']['properties']['dimension_id']['enum'] = POETRY_DIMENSIONS
        files[f'arms/{form}/{arm}.prompt.md'] = prompt
        files[f'arms/{form}/{arm}.original.schema.json'] = schema_raw
        files[f'arms/{form}/{arm}.retained.schema.json'] = canonical(schema)
        result[arm] = (prompt.decode('utf-8'), schema)
    return result


def build_design(manifest, entries, files, subset):
    sys.path.insert(0, str(REPO / 'src'))
    from hbqrs import core, runner
    from jsonschema import Draft202012Validator
    mfa = load_module('descriptive_mfa_schema_projection', HERE.parent / 'hbq-matched-mfa-v1/prepare.py')
    files = dict(files)
    paths = {'registry/all_modules.yaml': REPO / 'registry/all_modules.yaml',
             'bundles/all_bundles.yaml': REPO / 'bundles/all_bundles.yaml',
             'schema/hbq_task_contract.schema.json': REPO / 'schema/hbq_task_contract.schema.json',
             'schema/hbq_judge_response.schema.json': REPO / 'schema/hbq_judge_response.schema.json',
             'schema/hbq_verdict.schema.json': REPO / 'schema/hbq_verdict.schema.json',
             'prompts/BINARY_EVALUATION_PROMPT.md': REPO / 'prompts/judge/BINARY_EVALUATION_PROMPT.md',
             'implementation/core.py': REPO / 'src/hbqrs/core.py', 'implementation/runner.py': REPO / 'src/hbqrs/runner.py',
             'implementation/scoring_v2.py': REPO / 'src/hbqrs/scoring_v2.py',
             'implementation/codex_receipts.py': REPO / 'src/hbqrs/codex_receipts.py',
             'implementation/prepare.py': HERE / 'prepare.py',
             'implementation/mfa-prepare.py': Path(mfa.__file__),
             'implementation/validate_response.py': HERE / 'arms/validate_response.py',
             'implementation/mfa-admission.py': HERE.parent / 'hbq-matched-mfa-v1/validate_response.py',
             'implementation/ttcw-admission.py': HERE.parent / 'hbq-matched-ttcw-20261004/validate_response.py',
             'implementation/generation-prepare.py': Path(source_prepare.__file__),
             'implementation/generation-collect.py': Path(generation.__file__),
             'implementation/schema_subset.py': Path(subset.__file__),
             'README.md': HERE / 'README.md'}
    files.update({name: path.read_bytes() for name, path in paths.items()})
    ttcw = load_module('descriptive_ttcw_questions', HERE.parent / 'hbq-matched-ttcw-20261004/prepare.py')
    files['implementation/ttcw-prepare.py'] = Path(ttcw.__file__).read_bytes()
    test_payload = canonical(ttcw.adapted_tests(json.loads(files['sources/ttcw-tests.json']))).decode('utf-8')
    files['sources/ttcw-adapted-tests.json'] = test_payload.encode('utf-8')
    modules = core.load_modules(paths['registry/all_modules.yaml'])
    bundles = core.load_bundles(paths['bundles/all_bundles.yaml'])
    compiled, questions = {}, {}
    for bundle_id in EXPECTED_COUNTS:
        bundle = core.resolve_bundle(bundles, bundle_id)
        compiled[bundle_id] = core.compile_bundle(modules, bundle)
        require(compiled[bundle_id]['counts'] == EXPECTED_COUNTS[bundle_id], 'Canonical bank counts changed; register descendant')
        questions[bundle_id] = core.compiled_questions(compiled[bundle_id])
        files['compiled/' + bundle_id + '.json'] = canonical(compiled[bundle_id])
    texts, families, pairs, private_map = source_inventory(manifest, entries)
    for private in private_map['families']:
        form = next(f['form'] for f in families if f['family_id'] == private['family_id'])
        private['generation_target_in_scoring_bank'] = private['generation_target_question_id'] in {
            q['question']['id'] for q in questions[ROUTES[form][0]]}
    require(sum(not f['generation_target_in_scoring_bank'] for f in private_map['families']) == 2,
            'Generation/scoring target mismatch changed')
    files['private/lineage.json'] = canonical(private_map)
    banks, pair_sentinels = sentinels(families, pairs)
    family_by_id = {f['family_id']: f for f in families}
    assets = {form: arm_assets(form, files) for form in ROUTES}
    contracts, context_records, shared_records = {}, {}, {}
    for artifact_id, item in texts.items():
        family = family_by_id[item['family_id']]
        task = task_contract(artifact_id, item['form'], family['brief'], family['shared_work_context'])
        Draft202012Validator(json.loads(files['schema/hbq_task_contract.schema.json'])).validate(task)
        c = core.compile_bundle(modules, core.resolve_bundle(bundles, ROUTES[item['form']][0]), task_contract=task)
        require(c['counts'] == compiled[ROUTES[item['form']][0]]['counts'], 'Task context changed canonical questions')
        contracts[artifact_id] = task
        task_raw = canonical(task)
        projection = runner._task_contract_judge_context(task)
        context_raw = json.dumps(projection, ensure_ascii=False, indent=2).encode('utf-8')
        context_path = 'contexts/' + digest(context_raw) + '.json'
        files[context_path] = context_raw
        shared_raw = family['shared_work_context'].encode('utf-8')
        shared_path = 'shared-contexts/' + digest(shared_raw) + '.txt'
        files[shared_path] = shared_raw
        shared_records[artifact_id] = {'path': shared_path, 'sha256': digest(shared_raw), 'bytes': len(shared_raw)}
        files['contracts/' + artifact_id + '.json'] = task_raw
        files['inputs/' + artifact_id + '.txt'] = item['raw']
        context_records[artifact_id] = {'path': context_path, 'sha256': digest(context_raw), 'bytes': len(context_raw)}
    files['selection.json'] = canonical({'families': [{k: f[k] for k in ('family_id', 'form', 'variant_ids')} for f in families],
                                        'pairs': pairs, 'bank_sentinel_ids': banks, 'pair_sentinel_ids': pair_sentinels})
    units = []
    for cycle in range(3):
        for artifact_id in sorted(texts):
            if cycle == 0 or artifact_id in banks:
                units.extend({'arm': arm, 'repeat': cycle, 'artifact_id': artifact_id}
                             for arm in (*ARMS[:-1], *ESTABLISHED[texts[artifact_id]['form']]))
        for pair in pairs:
            if cycle == 0 or pair['pair_id'] in pair_sentinels:
                units.extend({'arm': 'pairwise', 'repeat': cycle, 'pair_id': pair['pair_id'], 'orientation': orientation}
                             for orientation in ('AB', 'BA'))
    units.sort(key=lambda u: (u['repeat'], digest(canonical([POLICY, 'unit_order_v1', u]))))
    requests, ordinal = [], Counter()
    pairs_by_id = {p['pair_id']: p for p in pairs}
    for unit in units:
        arm = unit['arm']
        ids = [unit['artifact_id']] if arm != 'pairwise' else [pairs_by_id[unit['pair_id']][k] for k in ('left', 'right')]
        if unit.get('orientation') == 'BA':
            ids.reverse()
        item = texts[ids[0]]
        form, bundle_id = item['form'], ROUTES[item['form']][0]
        family = family_by_id[item['family_id']]
        projection = runner._task_contract_judge_context(contracts[ids[0]])
        context = files[context_records[ids[0]]['path']].decode('utf-8')
        require(all(context_records[i] == context_records[ids[0]] for i in ids), 'Pair context differs')
        packets = [(n // 8 + 1, questions[bundle_id][n:n + 8], runner._batch_response_schema(
            [q['question']['id'] for q in questions[bundle_id][n:n + 8]])) for n in range(0, len(questions[bundle_id]), 8)] if arm == 'hbq' else [(1, [], assets[form][arm][1])]
        for batch, packet, schema in packets:
            retained = canonical(schema)
            portable = mfa.portable_schema(schema)
            subset.validate_schema(portable)
            schema_raw = canonical(portable)
            retained_path = 'retained-schemas/' + digest(retained) + '.json'
            schema_path = 'schemas/' + digest(schema_raw) + '.json'
            files[retained_path], files[schema_path] = retained, schema_raw
            if arm == 'hbq':
                prompt = runner._render_prompt(binary_prompt=files['prompts/BINARY_EVALUATION_PROMPT.md'].decode('utf-8'),
                    artifact={'name': 'Artifact', 'text': item['raw'].decode('utf-8')},
                    contexts=[{'name': 'Shared work context', 'text': family['shared_work_context']}] if family['shared_work_context'] else [],
                    bundle_id=bundle_id, artifact_id=item['id'], questions=packet, task_contract_context=projection)
            else:
                prompt = assets[form][arm][0] + '\n## Frozen common task context\n\n' + context
                if family['shared_work_context']:
                    prompt += '\n## Shared work context\n\n' + family['shared_work_context'] + '\n'
                for i, artifact_id in enumerate(ids):
                    prompt += '\n## Artifact' + (' ' + 'AB'[i] if arm == 'pairwise' else '') + '\n\n' + texts[artifact_id]['raw'].decode('utf-8') + '\n'
                if arm == 'ttcw14':
                    prompt += '\n## Original questions and interpretive definitions\n\n' + test_payload
            require(context in prompt, 'Declared exact task context is absent from judge prompt')
            require(not family['shared_work_context'] or family['shared_work_context'] in prompt,
                    'Declared exact shared context is absent from judge prompt')
            require(not re.search(ROLE_MARKER, prompt, re.IGNORECASE), 'Role marker leaks into judge prompt')
            raw = prompt.encode('utf-8')
            prompt_path = 'prompts/' + digest(raw) + '.txt'
            files[prompt_path] = raw
            sources = [{'id': i, 'input_path': 'inputs/' + i + '.txt', 'sha256': texts[i]['sha256'], 'bytes': texts[i]['bytes'],
                        **({'side': 'AB'[n]} if arm == 'pairwise' else {})} for n, i in enumerate(ids)]
            condition = {**unit, 'form': form, 'family_id': family['family_id'], 'bundle_id': bundle_id, 'batch': batch,
                         'question_ids': [q['question']['id'] for q in packet], 'sources': sources,
                         'task_context': context_records[ids[0]],
                         'shared_work_context': shared_records[ids[0]],
                         'compiled_sha256': digest(files['compiled/' + bundle_id + '.json']),
                         'task_contracts': [{'artifact_id': i, 'path': 'contracts/' + i + '.json',
                                             'sha256': digest(files['contracts/' + i + '.json'])} for i in ids],
                         'prompt_path': prompt_path, 'prompt_sha256': digest(raw), 'prompt_bytes': len(raw),
                         'schema_path': schema_path, 'schema_sha256': digest(schema_raw), 'schema_bytes': len(schema_raw),
                         'retained_schema_path': retained_path, 'retained_schema_sha256': digest(retained)}
            logical = digest(canonical(condition))
            endpoints = ENDPOINTS if int(logical[-1], 16) % 2 == 0 else ENDPOINTS[::-1]
            for endpoint in endpoints:
                ordinal[endpoint] += 1
                request = {**condition, 'logical_sample_id': logical, 'endpoint': endpoint,
                           'endpoint_ordinal': ordinal[endpoint], 'ordinal': len(requests) + 1}
                request['request_sha256'] = digest(canonical(request))
                requests.append(request)
    counts = {endpoint: dict(Counter(r['arm'] for r in requests if r['endpoint'] == endpoint)) for endpoint in ENDPOINTS}
    require(all(c == {'hbq': 640, 'holistic': 32, 'compact': 32, 'pairwise': 48, 'ttcw14': 16, 'oregon': 16, 'poemetric': 8}
                for c in counts.values()), 'Matched request geometry differs')
    summary = {'schema_version': 1, 'study_id': POLICY, 'evidence_class': 'descriptive_ai_synthetic_stimuli',
               'candidate': None, 'oracle_accepted': False, 'fixed_synthetic_labels': False,
               'intended_defect_success_rate_eligible': False, 'human_alignment_claim': False,
               'execution_authority': False, 'provider_calls': 0, 'generation_manifest_file_sha256': GENERATION_SHA,
               'review_file_commitments': REVIEW_PINS, 'counts': {'families': 8, 'texts': 24, 'unordered_pairs': 16,
                   'forms': {'short_narrative': 12, 'novel_work_segment': 6, 'poem': 6}, 'cycles': 3,
                   'bank_sentinels': 4, 'pair_sentinels': 4, 'requests_per_endpoint': 792, 'requests_total': len(requests),
                   'by_arm_per_endpoint': counts}, 'bank_counts': EXPECTED_COUNTS,
               'scope_routes': {f: {'bundle_id': r[0], 'artifact_kind': r[1], 'declared_scope': r[2], 'completion_status': r[3],
                                    'questions': r[4], 'packets': r[5]} for f, r in ROUTES.items()},
               'generation_targets_absent_from_passage_bank': 2, 'exact_generation_target_responsiveness_claim': False,
               'established_comparator': {'state': 'named_adaptations_frozen', 'requests_per_endpoint': 40,
                   'narrative': {'ttcw14': 16, 'oregon': 16}, 'poetry': {'arm': 'poemetric', 'requests': 8,
                       'policy': 'poemetric_free_verse_descendant_v1', 'primary': 'item 10 whole-poem quality, native 1–5; no aggregate',
                       'source': 'https://arxiv.org/pdf/2604.03695v1', 'source_date': '2026-04-04',
                       'source_location': 'Appendix C printed pages 21–23',
                       'repository_revision': 'bb0ebf8b090e91c380fc307d7705f2b7f318e122',
                       'limitations': 'Original fixed-form study; free verse, abstention, quotations, JSON and neutral-brief handling are adaptations; no validated free-verse human alignment',
                       'omitted_items': [12, 13], 'absence_zero_items': [7, 8]}},
               'sentinels': {'bank_ids': banks, 'pair_ids': pair_sentinels, 'policy': 'form 2/1/1; distinct families; salted opaque metadata hash only'},
               'order_policy': 'cycles 0/1/2; salted unit hash within cycle; hash-alternated endpoint lead; canonical leaf order retained',
               'schema_projection': 'MFA portable typed-evidence projection; retained originals; local semantic admission required',
               'admission': {'implementation_path': 'implementation/validate_response.py',
                   'interface': 'semantic_validate(arm,response,request,source_texts,subset,context,schema)',
                   'context_argument': 'Exact decoded task_context artifact plus newline plus exact decoded shared_work_context artifact',
                   'schema_argument': 'Frozen portable request schema; required for every arm'},
               'runtime': {'sol': {'model': 'gpt-6.1-sol', 'reasoning': 'high', 'provider': 'codex',
                   'account_identity_sha256': source_prepare.SECONDARY_ACCOUNT_SHA256, 'live_binding_required': True},
                   'grok': {'model': 'grok-4.7', 'reasoning': 'high', 'provider': 'grok', 'live_binding_required': True},
                   'automatic_retries': 0, 'timeout_seconds': 900, 'native_defaults': True,
                   'temperature_seed_control_supported': False, 'no_ambiguous_resend': True, 'collection_adapter_required': True},
               'requests': requests,
               'artifacts': {name: {'sha256': digest(value), 'bytes': len(value)} for name, value in sorted(files.items())}}
    files['manifest.json'] = canonical(summary)
    return summary, files


def build(manifest_path, results, review_root, ttcw_tests):
    files = read_authorization(review_root)
    manifest, entries, sources, subset = read_accepted(manifest_path, results)
    files.update(sources)
    files.update(read_ttcw_tests(ttcw_tests))
    return build_design(manifest, entries, files, subset)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--results-dir', type=Path, required=True)
    parser.add_argument('--review-root', type=Path, required=True)
    parser.add_argument('--ttcw-tests', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    source_prepare.output_preflight(args.output_root, (args.manifest.resolve().parent, args.results_dir, args.review_root, args.ttcw_tests))
    summary, files = build(args.manifest, args.results_dir, args.review_root, args.ttcw_tests)
    if not args.dry_run:
        args.output_root.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items():
            source_prepare.write_new(source_prepare.within(args.output_root, name), raw)
    print(json.dumps({'state': 'dry_run_without_contact' if args.dry_run else 'prepared_without_contact',
                      'manifest_sha256': digest(files['manifest.json']), 'counts': summary['counts'],
                      'bank_counts': summary['bank_counts'], 'candidate': None, 'oracle_accepted': False,
                      'execution_authority': False, 'established_comparator': summary['established_comparator']}, sort_keys=True))


if __name__ == '__main__':
    main()
