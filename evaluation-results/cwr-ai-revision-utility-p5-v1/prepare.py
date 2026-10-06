"""Freeze original AI drafts and a paired P5 revision protocol before generation."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

OWNER = '01a10839-a735-7bf2-a05a-68afadb52755'
REPO = Path(__file__).resolve().parents[2]
DESIGN = 'cwr-ai-revision-utility-p5-v1'
MATCHED_MANIFEST = '4e139dc1ef859be838cbe9ee8c579285845074032c6a00867a1b03859fdec2ff'
FORMS = (
    ('story', 'prose.short_story', 'self_contained_short_story', [
        'A night bus dispatcher must decide whether to record a missed connection honestly after a colleague quietly covers the cost of a passenger\'s taxi. Grounded close third person; an ordinary institutional choice with a local consequence, not a speech about virtue.',
        'Two adults close a municipal swimming pool for the winter and disagree about a pencilled message found in a locker. First-person narration with recoverable limits of knowledge; leave room for affection and irritation.',
        'A neighborhood chess club loses its room and bargains with a custodian for temporary use of a hall. Light social comedy in which competence and embarrassment coexist. Give the negotiation a complete local outcome.',
        'Neighbors share an improvised greenhouse and discover that their agreed heating schedule is costing one household more than the others. A restrained domestic story with competing reasonable interests and a consequential choice.',
        'In an invented market a person may trade away exactly one remembered hour, but not choose which later memory will depend on it. Write a modest speculative story with intelligible local rules and a complete emotionally ambivalent transaction.',
        'An adult sorts an old cassette collection with a sibling and recognizes a hum recorded during a past power cut. Use a recoverable nonlinear presentation and a local decision about what to keep; do not claim an omniscient account of another person\'s mind.',
    ]),
    ('excerpt', 'prose.short_form', 'bounded_prose_excerpt', [
        'A scene from an invented expedition novel: two archive translators disagree about whether a shipping instruction refers to a route or a person. Their work has an immediate practical consequence. Preserve the larger expedition as unresolved background.',
        'A scene from an invented cooperative novel: a meeting reconstructs who promised a disputed delivery, using several speakers whose memories differ. Keep their actual access to facts intelligible; the larger conflict remains unfinished.',
        'A scene from an invented civic speculative novel: a mountain town must choose how to distribute a reservoir\'s unusual night-time warmth. Establish only the local rule and scene conflict needed here, without claiming a whole-novel resolution.',
        'A scene from an invented historical maritime novel: a lighthouse keeper and a visiting chart maker confront a discrepancy between an old drawing and the visible coast. Choose an invented place and period; no factual historical claim is required.',
        'A scene from an invented workplace novel: a night-shift assembly team responds to an unexpected change in a tally while an absent member\'s explanation remains unavailable. A temporary decision may close the scene, not the whole work.',
        'A scene from an invented ferry-town novel: a kitchen worker and a relief cook disagree about a food inventory during a cancelled crossing. Give the exchange concrete work and subtext; keep later developments outside the supplied excerpt.',
    ]),
    ('poem', 'poetry.free_verse', 'complete_free_verse_poem', [
        'A free-verse poem organized around the radiator, slippers and a small coin in a waiting room. A connected image field may stay contemplative or circular; no narrative plot or progression on every line is required.',
        'A free-verse poem about shelves being moved in a small bookshop, the dust their outlines leave and an address written on a scrap. Let literal objects support a distinctive voice; recurrence is optional and need not be defective.',
        'A free-verse poem organized around an almost empty tram platform at night, a blue gutter and the sound after a vehicle has gone. Circular return or juxtaposition is welcome; avoid a forced moral or explanatory ending.',
        'A free-verse poem around reflections dividing as a swimming pool drains. Stillness, repeated language and discontinuous attention may be legitimate formal choices. Let the poem stand as a complete work.',
        'A free-verse poem around a sibling\'s annotated map and roads that have changed names. Keep a connected field of material marks and felt absence without requiring a linear memory story.',
        'A free-verse poem with cut fruit, a kitchen window and the pause before a summer storm. Favor particular language and formal intention; quietness and unresolved perception are not predetermined failures.',
    ]),
)
BATCH_IDS = (
    ('r01', 'r02', 'r07', 'r11', 'r13', 'r17'),
    ('r03', 'r05', 'r08', 'r09', 'r14', 'r18'),
    ('r04', 'r06', 'r10', 'r12', 'r15', 'r16'),
)
HELD_BACK = ('r05', 'r06', 'r11', 'r12', 'r17', 'r18')


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def roots():
    rows = []
    for form, bundle, scope, briefs in FORMS:
        for brief in briefs:
            root_id = f'r{len(rows) + 1:02d}'
            rows.append({'root_id': root_id, 'form': form, 'bundle_id': bundle, 'scope': scope,
                         'brief': brief, 'bounds': {'min_words': 140 if form == 'poem' else 350,
                                                  'max_words': 210 if form == 'poem' else 550,
                                                  'min_nonempty_lines': 22 if form == 'poem' else None,
                                                  'max_nonempty_lines': 36 if form == 'poem' else None}})
    return rows


def response_schema(batch_id, ids):
    draft = {'type': 'object', 'additionalProperties': False,
        'required': ['root_id', 'form', 'title', 'text', 'work_context', 'preservation_anchors'],
        'properties': {'root_id': {'type': 'string', 'enum': list(ids)},
            'form': {'type': 'string', 'enum': ['story', 'excerpt', 'poem']},
            'title': {'type': 'string', 'minLength': 1, 'maxLength': 120},
            'text': {'type': 'string', 'minLength': 400, 'maxLength': 12000},
            'work_context': {'type': 'string', 'maxLength': 1500},
            'preservation_anchors': {'type': 'array', 'minItems': 3, 'maxItems': 6,
                'items': {'type': 'object', 'additionalProperties': False,
                    'required': ['quote', 'purpose'], 'properties': {
                        'quote': {'type': 'string', 'minLength': 8, 'maxLength': 400},
                        'purpose': {'type': 'string', 'minLength': 8, 'maxLength': 400}}}}}}
    return {'type': 'object', 'additionalProperties': False,
        'required': ['schema_version', 'batch_id', 'drafts'], 'properties': {
            'schema_version': {'type': 'integer', 'enum': [1]},
            'batch_id': {'type': 'string', 'enum': [batch_id]},
            'drafts': {'type': 'array', 'minItems': 6, 'maxItems': 6, 'items': draft}}}


def protocol(rows, banks):
    return {'schema_version': 1, 'study_id': DESIGN, 'evidence_class': 'prospective_ai_revision_utility',
        'objective': 'Compare unchanged original, strong generic-feedback revision and CWR-feedback revision on twelve distinct AI drafts; retain six roots for conditional confirmation.',
        'development_root_ids': [r['root_id'] for r in rows if r['root_id'] not in HELD_BACK],
        'held_back_root_ids': list(HELD_BACK), 'development_roots': 12, 'held_back_roots': 6,
        'forms': {'story': 4, 'excerpt': 4, 'poem': 4}, 'held_back_per_form': 2,
        'roots': rows, 'canonical_scope_banks': banks,
        'arms': ['unchanged_original', 'strong_generic_feedback_revision', 'cwr_feedback_revision'],
        'generation_and_editor': {'surface': 'native Codex child', 'model': 'gpt-6.1-sol', 'reasoning': 'high',
            'fresh_conversation': True, 'same_model_account_and_effort_required_across_revision_arms': True,
            'original_generation_batches': 3, 'original_generator_calls_counted_separately': True,
            'effective_settings_verified_from_native_journal_before_admission': True,
            'sampler_controls_not_exposed_by_native_surface': None,
            'equal_inference_token_budget_proven': False},
        'feedback_contract': {'maximum_issues': 3, 'feedback_words': 180,
            'count_rule': 'Whitespace-separated words in the feedback body, including quotations; protocol labels are excluded.',
            'creative_context_identical_between_arms': True,
            'generic': 'Strong independent craft feedback on concrete improvement opportunities, voice, internal coherence and intended effect; no canonical rubric supplied.',
            'cwr': 'Same artifact/brief/context plus the complete correctly scoped canonical question payload; at most three source-grounded repair opportunities, not forced failures.',
            'rubric_payload_is_the_intervention': True,
            'facts_and_artistic_choices_are_not_fixed_oracles': True},
        'revision_contract': {'revisions_per_arm': 1, 'same_revision_instruction': True,
            'same_source_context_and_word_allowance': True, 'feedback_words': 180, 'maximum_issues': 3,
            'word_count_delta_fraction_max': 0.20, 'source_overwrite_allowed': False,
            'instruction': 'Revise the supplied original once using the supplied feedback. Preserve its intended situation, factual commitments, voice and declared form. Make only improvements justified by the source and feedback. Return the complete revised text, with original work context unchanged. Do not discuss the process.',
            'native_hidden_reasoning_token_budget_unavailable': True,
            'budget_disclosure': 'Equal visible feedback length, issue cap, input context, revision word allowance and model/effort are enforced. Equal hidden compute or sampler budget is not asserted.'},
        'evaluation_contract': {'endpoints': ['grok', 'sol'], 'secondary_sol_account_preferred': True,
            'endpoint_concurrency_cap_each': 10, 'blind_arm_and_feedback': True,
            'fresh_judge_contexts': True, 'primary_preference_measure': 'CWR-feedback revision versus strong-generic revision, both orders; ties count half and order effects stay visible.',
            'other_pairwise_pairs': ['original versus generic', 'original versus CWR'],
            'measures': ['complete correctly scoped canonical bank', 'matched holistic', 'matched compact', 'voice preservation', 'source-grounded introduced defects', 'bidirectional pairwise'],
            'registered_repeat_root_ids': ['r01', 'r07', 'r13'], 'repeat_cycles_on_all_three_arms': 3,
            'feedback_generation_endpoint_not_independent_of_sol_judge_model': True,
            'grok_is_separate_evaluation_endpoint': True,
            'human_labels_created': 0, 'human_utility_claim': False,
            'scores_not_pooled_across_unlike_scales': True,
            'analysis_cluster': 'original root; revisions, orders and cycles are repeated measurements',
            'planned_primary_analysis': 'Root-mean CWR-versus-generic preference per endpoint and form; root-cluster bootstrap95% interval with fixed seed20261004,10000resamples. Report missingness, order effects, voice preservation and introduced defects separately.',
            'positive_utility_margin': 0.10,
            'held_back_release': 'Complete the twelve-root development evaluation and exact native admission first. An explicit recorded controller decision may open six held-back roots only under the unchanged frozen mechanism and separately frozen request/analysis manifest. No development-based rewrite of held-back briefs or targets.',
            'exact_evaluation_requests_not_yet_frozen': True},
        'generation_admission': {'mechanical_only': True, 'bounds_schema_identity_and_exact_anchor_quotes': True,
            'creative_quality_not_a_generation_acceptance_label': True,
            'rejected_outputs_retained': True, 'no_ambiguous_resend': True,
            'held_back_sources_may_be_visible_to_generation_and_custody_controller': True,
            'held_back_sources_excluded_from_development_feedback_revision_and_evaluation': True},
        'human_validation': False, 'candidate_promoted': False, 'full_goal_complete': False,
        'prior_historical_revision_studies_relabelled': False}


def freeze(out, source):
    assert os.environ.get('CODEX_THREAD_ID') == OWNER
    assert not out.exists(), 'Original generation is create-only; preserve occupied attempts'
    sys.path.insert(0, r'C:\Users\Haile\.codex\tools')
    from working_sentinel import read_sentinel
    parent = out.parent.resolve()
    assert any(c['work_id'] == 'cwr-p5-ai-revision-output-20261006' and c['task_id'] == c['session_id'] == OWNER
               and c['host_id'] == 'local' and c['reservations'] == [{'kind': 'tree', 'path': 'successor-program-20261004/revision-utility'}]
               for c in read_sentinel(parent / '.working')['claims'])
    raw = (source / 'manifest.json').read_bytes()
    assert sha(raw) == MATCHED_MANIFEST
    inherited = json.loads(raw)
    banks, files = {}, {}
    for bundle, expected in (('prose.short_story', 178), ('prose.short_form', 170), ('poetry.free_verse', 89)):
        path = 'compiled/' + bundle + '.json'
        raw = (source / path).read_bytes()
        assert sha(raw) == inherited['artifacts'][path]['sha256']
        compiled = json.loads(raw)
        assert sum(compiled['counts'][k] for k in ('domain_questions', 'penalty_questions', 'supplemental_questions')) == expected
        banks[bundle] = {'sha256': sha(raw), 'leaves': expected, 'source_manifest_sha256': MATCHED_MANIFEST}
        files[path] = raw
    rows = roots()
    design = protocol(rows, banks)
    assert len(rows) == 18 and len(set(r['root_id'] for r in rows)) == 18
    assert Counter(r['form'] for r in rows if r['root_id'] not in HELD_BACK) == {'story': 4, 'excerpt': 4, 'poem': 4}
    assert Counter(r['form'] for r in rows if r['root_id'] in HELD_BACK) == {'story': 2, 'excerpt': 2, 'poem': 2}
    assert {i for batch in BATCH_IDS for i in batch} == {r['root_id'] for r in rows}
    files['protocol.json'] = canonical(design)
    requests = []
    for index, ids in enumerate(BATCH_IDS, 1):
        batch_id = f'p5-g{index:02d}'
        selected = [r for r in rows if r['root_id'] in ids]
        packet = {'schema_version': 1, 'batch_id': batch_id, 'roots': selected,
            'instructions': 'Generate six entirely new AI first drafts. Follow each brief and bounds earnestly; do not plant defects, imitate existing manuscripts or supply judgments. Preserve different voices and legitimate nonlinear, circular or contemplative forms. For excerpts supply50-100words of invented shared work context and only claim the visible scene. For stories/poems work_context must be empty. Return3-6 proposed preservation anchors per draft with exact contiguous quotes from its text and an explanation of why they matter. Anchors are proposals, not accepted literary or human labels. Titles are separate from text. Return only JSON matching the supplied response schema.'}
        ppath, spath = f'originals/{batch_id}/packet.json', f'originals/{batch_id}/response-schema.json'
        files[ppath], files[spath] = canonical(packet), canonical(response_schema(batch_id, ids))
        requests.append({'batch_id': batch_id, 'root_ids': list(ids), 'packet_path': ppath,
                         'packet_sha256': sha(files[ppath]), 'response_schema_path': spath,
                         'response_schema_sha256': sha(files[spath]), 'attempts': 1})
    files['implementation/prepare.py'] = Path(__file__).read_bytes()
    manifest = {'study_id': DESIGN, 'owner_task': OWNER, 'stage': 'original_generation_only',
        'protocol_sha256': sha(files['protocol.json']), 'source_manifest_sha256': MATCHED_MANIFEST,
        'requests': requests, 'artifacts': {p: {'bytes': len(raw), 'sha256': sha(raw)} for p, raw in files.items()},
        'new_provider_calls_made_by_freeze': 0, 'generation_performed': False,
        'feedback_and_revisions_performed': False, 'human_targets_opened': False, 'full_goal_complete': False}
    out.mkdir()
    for name, raw in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)
    for name, raw in files.items():
        assert (out / name).read_bytes() == raw
    with (out / 'manifest.json').open('xb') as stream:
        stream.write(canonical(manifest))
    print(json.dumps({'manifest_sha256': sha(canonical(manifest)), 'protocol_sha256': manifest['protocol_sha256'],
                      'generation_batches': 3, 'development_roots': 12, 'held_back_roots': 6, 'provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-matched-frozen', type=Path, required=True)
    args = parser.parse_args()
    freeze(args.out.resolve(), args.source_matched_frozen.resolve())
