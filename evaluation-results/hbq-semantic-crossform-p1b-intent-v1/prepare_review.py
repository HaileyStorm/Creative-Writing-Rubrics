"""Prepare blinded independent AI intent review; never generate, judge or promote."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
import importlib.util
_spec = importlib.util.spec_from_file_location('p1b_intent_generation', HERE.parent / 'hbq-semantic-crossform-p1b-v1/collect.py')
generation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generation)
prepare = generation.prepare
canonical, digest, require = prepare.canonical, prepare.digest, prepare.require
POLICY = 'blinded_independent_ai_fixture_intent_review_v1'
STATES = ['supported', 'not_supported', 'uncertain']
BRIEF = ('Assess every variant independently against the supplied canonical criterion and neutral creative brief. '
         'Judge quality suitability within the declared form and supplied scope, brief suitability, and each proposed preservation anchor. '
         'The anchors are proposed review aids, not accepted facts; reject unsupported proposals. Role-bearing metadata sentences '
         'have been filtered. An unavailable filtered proposal cannot support preservation and requires uncertainty. '
         'Identify any local criterion failure and the affected anchors; '
         'explain the source-supported connection and unrelated preservation. Quote exact supplied text or shared context as evidence. '
         'Use uncertain when the evidence or artistic interpretation does not settle a judgment. Do not force a unique winner or failure. '
         'For poems, stillness, juxtaposition, literal refrain and circular architecture can be legitimate; do not require linear plotting '
         'or change on every line. For work segments, assess only the supplied bounded work context. '
         'Preserve objections and disagreement. This is an independent AI synthetic-intent review, not human ground truth or rubric scoring.')


def blinded_packet(entries, source_manifest_sha256, total_families):
    """Whitelist reviewer-visible fields; retain source roles only in the private map."""
    families, mapping = [], []
    for row, answer, semantics, commitments in entries:
        family_key = digest(canonical({'source_manifest': source_manifest_sha256, 'logical_sample': row['logical_sample_id']}))
        family_id = 'family-' + family_key[:20]
        anchors, anchor_lineage = [], []
        for i, text in enumerate(answer['preservation_anchors']):
            anchor_id = 'anchor-' + digest(canonical([family_key, i, text]))[:20]
            sentences = re.split(r'(?<=[.!?])\s+', text)
            removed = [sentence for sentence in sentences if re.search(r'\b(original|target[ _]defect|legitimate[ _]style)\b', sentence, re.IGNORECASE)
                       or any(value in sentence for value in row['family']['variant_ids'].values())]
            proposal = ' '.join(sentence for sentence in sentences if sentence not in removed)
            anchors.append({'anchor_id': anchor_id, 'proposal': proposal, 'proposal_available': bool(proposal.strip()),
                            'source_metadata_filtered': bool(removed)})
            anchor_lineage.append({'anchor_id': anchor_id, 'source_anchor': text,
                                   'source_anchor_utf8_sha256': digest(text.encode('utf-8')),
                                   'review_proposal_utf8_sha256': digest(proposal.encode('utf-8')),
                                   'removed_role_bearing_sentences': removed})
        variants, roles = [], {}
        for role in prepare.VARIANTS:
            text = answer['variants'][role]['text']
            label = r'(?:original|target[ _]defect|legitimate[ _]style)(?:\s+variant)?'
            require(not re.search(r'^\s*(?:#{1,6}\s*)?' + label + r'(?:\s*[:\-]|\s*$)', text, re.IGNORECASE | re.MULTILINE),
                    'Generation role label leaks into creative text')
            text_sha = digest(text.encode('utf-8'))
            variant_id = 'variant-' + digest(canonical({'family': family_key, 'text_sha256': text_sha}))[:20]
            variants.append({'variant_id': variant_id, 'text': text})
            roles[variant_id] = {'role': role, 'source_variant_id': answer['variants'][role]['variant_id'],
                                'text_sha256': text_sha, 'proposed_intent_note': answer['variants'][role]['proposed_intent_note']}
        variants.sort(key=lambda v: digest(canonical({'family': family_key, 'variant': v['variant_id'], 'permutation': POLICY})))
        family = {'family_id': family_id, 'form': row['family']['form'], 'scope': row['family']['scope'],
                  'neutral_creative_brief': row['family']['brief'], 'shared_work_context': answer['work_context'],
                  'proposed_preservation_anchors': anchors, 'canonical_target_semantics': semantics, 'variants': variants}
        visible = canonical(family).decode()
        require(all(value not in visible for value in row['family']['variant_ids'].values()), 'Generation role ID leaks into reviewer material')
        require(not re.search(r'\b(target[ _]defect|legitimate[ _]style)\b', visible, re.IGNORECASE), 'Generation role marker leaks into reviewer material')
        families.append(family)
        mapping.append({'family_id': family_id, 'source_family_id': row['family']['family_id'],
                        'logical_sample_id': row['logical_sample_id'], 'ordinal': row['ordinal'],
                        'proposed_defect_intent': row['family']['proposed_defect_intent'],
                        'proposed_legitimate_intent': row['family']['proposed_legitimate_intent'],
                        'generator_proposed_review_notes': answer['proposed_review_notes'],
                        'anchor_metadata_lineage': anchor_lineage,
                        'variants': roles, 'source_commitments': commitments})
    packet = {'schema_version': 1, 'policy': POLICY, 'review_brief': BRIEF, 'families': families,
              'human_labels_supplied': 0, 'scoring_requested': False}
    private = {'schema_version': 1, 'policy': POLICY, 'source_manifest_sha256': source_manifest_sha256,
               'review_packet_sha256': digest(canonical(packet)),
               'total_prospective_families': total_families, 'selected_prefix_families': len(entries),
               'families_outside_selected_prefix': total_families - len(entries), 'families': mapping}
    return packet, private


def review_schema(packet_sha256):
    evidence = {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['source', 'quote'], 'properties': {'source': {'type': 'string', 'enum': ['variant', 'shared_work_context']},
                                                     'quote': {'type': 'string', 'minLength': 1}}}}
    def assessment(extra=None):
        props = {'status': {'type': 'string', 'enum': STATES}, 'evidence': evidence, 'why': {'type': 'string', 'minLength': 1}}
        props.update(extra or {})
        return {'type': 'object', 'additionalProperties': False, 'required': list(props), 'properties': props}
    item = {'family_id': {'type': 'string'}, 'variant_id': {'type': 'string'},
            'criterion': assessment(), 'quality_suitability': assessment(), 'brief_suitability': assessment(),
            'anchors': {'type': 'array', 'items': assessment({'anchor_id': {'type': 'string'}})},
            'local_issue': {'type': 'object', 'additionalProperties': False,
                           'required': ['identified', 'affected_anchor_ids', 'evidence', 'why'],
                           'properties': {'identified': {'type': 'boolean'},
                                          'affected_anchor_ids': {'type': 'array', 'items': {'type': 'string'}},
                                          'evidence': evidence, 'why': {'type': 'string', 'minLength': 1}}}}
    return {'type': 'object', 'additionalProperties': False,
            'required': ['schema_version', 'packet_sha256', 'reviewer_declaration', 'variants', 'unresolved_disagreements'],
            'properties': {'schema_version': {'type': 'integer', 'enum': [1]},
                'packet_sha256': {'type': 'string', 'enum': [packet_sha256]},
                'reviewer_declaration': {'type': 'object', 'additionalProperties': False,
                    'required': ['kind', 'identity', 'independent_of_generator'],
                    'properties': {'kind': {'type': 'string', 'enum': ['independent_ai_intent_review']},
                                   'identity': {'type': 'string', 'minLength': 1}, 'independent_of_generator': {'type': 'boolean'}}},
                'variants': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': list(item), 'properties': item}},
                'unresolved_disagreements': {'type': 'array', 'items': {'type': 'string', 'minLength': 1}}}}


def validate_review(packet, private_map, review, subset):
    """Validate exact source evidence, then expose disagreements without promotion."""
    require(subset.matches_schema(review, review_schema(digest(canonical(packet)))), 'Review schema/packet commitment differs')
    require(private_map['policy'] == packet['policy'] == POLICY, 'Review mapping policy differs')
    require(private_map['review_packet_sha256'] == digest(canonical(packet)), 'Private role map packet commitment differs')
    families = {f['family_id']: f for f in packet['families']}
    maps = {f['family_id']: f for f in private_map['families']}
    require(set(maps) == set(families), 'Private family map differs')
    require(len(maps) == len(private_map['families']) == len(families) == len(packet['families']), 'Duplicate family identity')
    for key, family in families.items():
        variants = maps[key]['variants']
        require(set(variants) == {v['variant_id'] for v in family['variants']}
                and sorted(v['role'] for v in variants.values()) == sorted(prepare.VARIANTS), 'Private role/variant inventory differs')
        lineage = {a['anchor_id']: a for a in maps[key]['anchor_metadata_lineage']}
        require(len(lineage) == len(maps[key]['anchor_metadata_lineage']) == len(family['proposed_preservation_anchors']), 'Private anchor inventory differs')
        for anchor in family['proposed_preservation_anchors']:
            require(anchor['anchor_id'] in lineage, 'Private anchor identity differs')
            source = lineage[anchor['anchor_id']]
            require(digest(anchor['proposal'].encode()) == source['review_proposal_utf8_sha256']
                    and digest(source['source_anchor'].encode()) == source['source_anchor_utf8_sha256']
                    and anchor['proposal_available'] == bool(anchor['proposal'].strip())
                    and anchor['source_metadata_filtered'] == bool(source['removed_role_bearing_sentences']), 'Private anchor lineage commitment differs')
    expected = {(f['family_id'], v['variant_id']) for f in packet['families'] for v in f['variants']}
    seen, results = set(), {}
    for entry in review['variants']:
        key = entry['family_id'], entry['variant_id']
        require(key in expected and key not in seen, 'Review variant missing, duplicate or foreign')
        seen.add(key)
        family = families[key[0]]
        variant = next(v for v in family['variants'] if v['variant_id'] == key[1])
        role = maps[key[0]]['variants'][key[1]]
        require(digest(variant['text'].encode('utf-8')) == role['text_sha256'], 'Private role map text commitment differs')
        anchor_ids = {a['anchor_id'] for a in family['proposed_preservation_anchors']}
        require(len(entry['anchors']) == len(anchor_ids) and {a['anchor_id'] for a in entry['anchors']} == anchor_ids, 'Review anchor inventory differs')
        assessments = [entry[k] for k in ('criterion', 'quality_suitability', 'brief_suitability')] + entry['anchors']
        for assessment in assessments + [entry['local_issue']]:
            if assessment.get('status') != 'uncertain' and assessment is not entry['local_issue']:
                require(bool(assessment['evidence']), 'Settled assessment requires exact source evidence')
            for evidence in assessment['evidence']:
                text = variant['text'] if evidence['source'] == 'variant' else family['shared_work_context']
                require(bool(evidence['quote'].strip()), 'Review evidence quote must be nonblank')
                require(evidence['quote'] in text, 'Review quote is not an exact substring of its own source')
        issue = entry['local_issue']
        affected = issue['affected_anchor_ids']
        require(len(set(affected)) == len(affected) and set(affected) <= anchor_ids, 'Local issue anchor inventory differs')
        if issue['identified']:
            require(bool(issue['evidence']), 'Identified local issue requires exact source evidence')
        else:
            require(not affected, 'Absent local issue cannot claim affected anchors')
        reasons = []
        if any(not anchor['proposal_available'] for anchor in family['proposed_preservation_anchors']):
            reasons.append('filtered_anchor_missing_proposal')
        if any(a['status'] == 'uncertain' for a in assessments): reasons.append('uncertain_assessment')
        if role['role'] in {'original', 'legitimate_style'}:
            if any(a['status'] != 'supported' for a in assessments) or issue['identified']:
                reasons.append('control_not_supported')
        else:
            if entry['criterion']['status'] != 'not_supported' or not issue['identified'] or not affected:
                reasons.append('target_defect_not_locally_identified')
            if any(a['status'] != ('not_supported' if a['anchor_id'] in affected else 'supported') for a in entry['anchors']):
                reasons.append('local_defect_or_unrelated_preservation_not_supported')
        results[key] = {'variant_id': key[1], 'source_role': role['role'], 'blocking_reasons': reasons}
    require(seen == expected, 'Review must assess every variant; no silent ties or omissions')
    family_results = [{'family_id': key, 'variants': [results[(key, v['variant_id'])] for v in family['variants']],
                       'oracle_admission_candidate': not any(results[(key, v['variant_id'])]['blocking_reasons'] for v in family['variants'])}
                      for key, family in families.items()]
    global_block = bool(review['unresolved_disagreements']) or not review['reviewer_declaration']['independent_of_generator']
    if global_block:
        for family in family_results: family['oracle_admission_candidate'] = False
    return {'policy': POLICY, 'review_sha256': digest(canonical(review)), 'families': family_results,
            'reviewer_declaration': review['reviewer_declaration'], 'unresolved_disagreements': review['unresolved_disagreements'],
            'independence_is_supplied_declaration': True, 'ai_review_is_human_label': False,
            'oracle_accepted': False, 'eligible_for_scoring': False,
            'owner_semantic_review_and_separate_scoring_freeze_required': True}


def render_markdown(packet):
    chunks = ['# Independent AI fixture intent review', packet['review_brief']]
    for family in packet['families']:
        chunks += ['## ' + family['family_id'], 'Form: ' + family['form'] + '; scope: ' + family['scope'],
                   family['neutral_creative_brief'], 'Shared work context:', family['shared_work_context'],
                   'Proposed anchors:', canonical(family['proposed_preservation_anchors']).decode(),
                   'Exact canonical target semantics:', canonical(family['canonical_target_semantics']).decode()]
        for variant in family['variants']:
            chunks += ['### ' + variant['variant_id'], variant['text']]
    return ('\n\n'.join(chunks) + '\n').encode('utf-8')


def build(manifest_path, results, *, through_family, manifest_sha256):
    manifest, frozen, source_sha = prepare.read_manifest(manifest_path)
    require(source_sha == manifest_sha256, 'Exact frozen generation manifest differs')
    require(isinstance(through_family, int) and not isinstance(through_family, bool)
            and 1 <= through_family <= len(manifest['requests']), 'Explicit accepted prefix must be within prospective families')
    job_raw = (results / 'job.json').read_bytes()
    require(json.loads(job_raw) == generation.job_binding(manifest, source_sha), 'Generation job binding differs')
    for name, path in [('collect.py', Path(generation.__file__)), ('prepare.py', Path(prepare.__file__))]:
        require(digest(path.read_bytes()) == manifest['artifacts']['implementation/' + name]['sha256'], 'Generation verification implementation differs')
    receipts = prepare.load_module('p1b_intent_frozen_receipts', frozen / 'implementation/codex_receipts.py')
    subset = prepare.load_module('p1b_intent_frozen_subset', frozen / 'implementation/schema_subset.py')
    entries = []
    for row in manifest['requests'][:through_family]:
        sample = generation.sample_path(results, row)
        generation.verify_accepted(sample, row, manifest, source_sha, frozen, receipts, subset)
        response_raw = (sample / 'response.json').read_bytes()
        semantics_raw = generation.read_pinned(frozen, row['semantics_path'], manifest['artifacts'][row['semantics_path']])
        commitments = {'terminal_sha256': digest((sample / 'terminal.json').read_bytes()),
                       'response_sha256': digest(response_raw), 'semantics_sha256': digest(semantics_raw),
                       'native_result_sha256': digest((sample / 'native-result.json').read_bytes()),
                       'validation_sha256': digest((sample / 'validation.json').read_bytes())}
        entries.append((row, json.loads(response_raw), json.loads(semantics_raw), commitments))
    packet, private = blinded_packet(entries, source_sha, manifest['counts']['families'])
    private['generation_job_file_sha256'] = digest(job_raw)
    schema = review_schema(digest(canonical(packet)))
    subset.validate_schema(schema)
    files = {'reviewer/packet.json': canonical(packet), 'reviewer/packet.md': render_markdown(packet),
             'reviewer/response-schema.json': canonical(schema),
             'private/role-map.json': canonical(private), 'implementation/prepare_review.py': Path(__file__).read_bytes()}
    summary = {'policy': POLICY, 'source_manifest_sha256': source_sha, 'through_family': through_family,
               'selected_families': through_family, 'selected_variants': 3 * through_family,
               'prospective_generation_counts': manifest['counts'], 'selected_declared_comparisons': 2 * through_family,
               'total_prospective_families': manifest['counts']['families'], 'families_outside_selected_prefix': manifest['counts']['families'] - through_family,
               'selection': 'Explicit accepted prefix; remaining count does not assert generation completion or untouched state',
               'filtered_anchor_metadata_sentences': sum(len(a['removed_role_bearing_sentences']) for f in private['families'] for a in f['anchor_metadata_lineage']),
               'artifacts': {name: {'sha256': digest(raw), 'bytes': len(raw)} for name, raw in files.items()},
               'provider_calls': 0, 'oracle_accepted': False, 'eligible_for_scoring': False}
    files['manifest.json'] = canonical(summary)
    return summary, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--results-dir', type=Path, required=True)
    parser.add_argument('--through-family', type=int, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    prepare.output_preflight(args.output_root, (args.manifest.resolve().parent, args.results_dir.resolve()))
    summary, files = build(args.manifest, args.results_dir, through_family=args.through_family, manifest_sha256=args.manifest_sha256)
    if not args.dry_run:
        args.output_root.mkdir(parents=True, exist_ok=False)
        for name, raw in files.items(): prepare.write_new(prepare.within(args.output_root, name), raw)
    print(json.dumps({'state': 'dry_run_without_contact' if args.dry_run else 'prepared_without_contact',
                      'manifest_sha256': digest(files['manifest.json']), **summary}, sort_keys=True))


if __name__ == '__main__':
    main()
