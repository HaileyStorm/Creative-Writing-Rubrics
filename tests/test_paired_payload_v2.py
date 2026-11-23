from __future__ import annotations

import hashlib
import json

import pytest

from hbqrs.paired_payload_v2 import build_paired_payloads
from hbqrs.repeatability import (
    RepeatabilityContractError, content_address, derived_reuse_receipt,
    fresh_replicate_receipt, paired_response_envelope, validate_paired_comparison,
)

def h(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

CONTROLS = {'seed': {'state': 'unsupported', 'value': None},
            'temperature': {'state': 'unsupported', 'value': None}}

def source(text: str, label: str, context: str = 'context'):
    address = content_address(artifact_sha256=h(text), context_sha256=[h(context)],
        compiled_bundle_sha256=h('bundle'), question_sha256=h('question'),
        prompt_sha256=h('prompt'), response_schema_sha256=h('schema'),
        judge_stack={'provider': 'fixture'}, provider='codex', model='fixture',
        reasoning='high', deterministic_control_support=CONTROLS)
    fresh = fresh_replicate_receipt(replicate_group_id=label, replicate_index=1,
        content_address_sha256=address['content_address_sha256'], run_config_sha256=h('run'),
        accepted_session_ids=[label], run_receipt_sha256=h(label), score=50)
    return address, derived_reuse_receipt(source=fresh,
        requested_content_address_sha256=address['content_address_sha256'], reuse_purpose='paired')

def args(a='A poem', b='B poem'):
    aa, ra = source(a, 'a'); ab, rb = source(b, 'b')
    return dict(comparison_id='fixture', instruction='Choose FIRST, SECOND or TIE',
        artifact_a=a, artifact_b=b, address_a=aa, address_b=ab, reuse_a=ra, reuse_b=rb,
        ab_nonce='a'*32, ba_nonce='b'*32, judge_stack_sha256=h('paired judge'),
        paired_contract_sha256=h('paired contract'), provider='codex',
        deterministic_control_support=CONTROLS)

def test_swapped_payloads_flow_through_existing_pair_validation():
    result = build_paired_payloads(**args(a='A,\nα', b='B "quote"'))
    ab, ba = json.loads(result['ab_task_bytes']), json.loads(result['ba_task_bytes'])
    assert (ab['first'], ab['second']) == (ba['second'], ba['first']) == ('A,\nα', 'B "quote"')
    assert ab['instruction'] == ba['instruction']
    c = result['commitment']
    assert not c['identity_control']
    responses = [paired_response_envelope(commitment=c, presentation_order=order,
        request_bytes=result[order.lower() + '_task_bytes'], accepted_session_ids=[order],
        response_bytes=payload) for order, payload in [('AB', b'{"winner":"FIRST"}'), ('BA', b'{"winner":"SECOND"}')]]
    assert validate_paired_comparison(c, responses)['agreement_classification'] == 'agreement_artifact_a'

def test_identity_is_actual_text_with_validated_same_context():
    result = build_paired_payloads(**args(a='identical', b='identical'))
    assert result['commitment']['identity_control'] is True
    assert result['ab_task_bytes'] != result['ba_task_bytes']
    changed = args(a='identical', b='identical')
    changed['address_b'], changed['reuse_b'] = source('identical', 'other', context='different')
    with pytest.raises(RepeatabilityContractError, match='different evaluation contexts'):
        build_paired_payloads(**changed)

def test_rejects_unbound_text_descriptors_receipts_and_nonces():
    cases = []
    x = args(); x['artifact_a'] = 'not the committed poem'; cases.append(x)
    x = args(); x['address_a'] = {**x['address_a'], 'content_address_sha256': h('wrong')}; cases.append(x)
    x = args(); x['reuse_a'] = x['reuse_b']; cases.append(x)
    x = args(); x['ba_nonce'] = x['ab_nonce']; cases.append(x)
    for x in cases:
        with pytest.raises(RepeatabilityContractError):
            build_paired_payloads(**x)
