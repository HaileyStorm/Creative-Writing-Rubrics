"""Opt-in construction of matched paired-judgment payloads.

The returned bytes are model-facing task content, not provider transport bytes.
This does not authenticate prior receipts or prove what a provider received.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .repeatability import (
    DerivedReuseReceipt,
    RepeatabilityContractError,
    content_address,
    paired_comparison_commitment,
)


def _verified_address(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise RepeatabilityContractError('address must be a mapping')
    fields = dict(value)
    digest = fields.pop('content_address_sha256', None)
    version = fields.pop('format_version', None)
    if type(version) is not int or version != 1:
        raise RepeatabilityContractError('address version is invalid')
    try:
        rebuilt = content_address(**fields)
    except TypeError as error:
        raise RepeatabilityContractError('address fields are invalid') from error
    if rebuilt['content_address_sha256'] != digest:
        raise RepeatabilityContractError('address hash does not match')
    return rebuilt


def build_paired_payloads(
    *, comparison_id: str, instruction: str, artifact_a: str, artifact_b: str,
    address_a: Mapping[str, Any], address_b: Mapping[str, Any],
    reuse_a: DerivedReuseReceipt, reuse_b: DerivedReuseReceipt,
    ab_nonce: str, ba_nonce: str, judge_stack_sha256: str,
    paired_contract_sha256: str, provider: str,
    deterministic_control_support: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Construct two UTF-8 task bodies with identical instruction and swapped text.

    Callers supply independent opaque nonces; keep the AB/BA mapping private.
    Source addresses bind UTF-8 text and must share all non-artifact fields.
    """
    if any(not isinstance(x, str) or not x for x in (instruction, artifact_a, artifact_b)):
        raise RepeatabilityContractError('instruction and artifacts must be nonempty text')
    if any(not isinstance(n, str) or not re.fullmatch(r'[0-9a-f]{32}', n) for n in (ab_nonce, ba_nonce)) or ab_nonce == ba_nonce:
        raise RepeatabilityContractError('two distinct 128-bit hexadecimal nonces are required')
    first, second = _verified_address(address_a), _verified_address(address_b)
    for address, artifact in ((first, artifact_a), (second, artifact_b)):
        try:
            actual = hashlib.sha256(artifact.encode('utf-8')).hexdigest()
        except UnicodeEncodeError as error:
            raise RepeatabilityContractError('artifact must be valid UTF-8 text') from error
        if address['artifact_sha256'] != actual:
            raise RepeatabilityContractError('artifact text does not match its address')
    def shared(address: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in address.items() if k not in {'artifact_sha256', 'content_address_sha256'}}
    if shared(first) != shared(second):
        raise RepeatabilityContractError('source addresses have different evaluation contexts')
    if not isinstance(reuse_a, DerivedReuseReceipt) or not isinstance(reuse_b, DerivedReuseReceipt):
        raise RepeatabilityContractError('source reuse receipts are required')
    if reuse_a.content_address_sha256 != first['content_address_sha256'] or reuse_b.content_address_sha256 != second['content_address_sha256']:
        raise RepeatabilityContractError('reuse receipts do not match source addresses')

    def render(nonce: str, x: str, y: str) -> bytes:
        value = {'instruction': instruction, 'first': x, 'second': y, 'request_id': nonce}
        try:
            return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True).encode('utf-8')
        except UnicodeEncodeError as error:
            raise RepeatabilityContractError('instruction must be valid UTF-8 text') from error

    ab, ba = render(ab_nonce, artifact_a, artifact_b), render(ba_nonce, artifact_b, artifact_a)
    commitment = paired_comparison_commitment(
        comparison_id=comparison_id, artifact_a_reuse=reuse_a, artifact_b_reuse=reuse_b,
        judge_stack_sha256=judge_stack_sha256, paired_contract_sha256=paired_contract_sha256,
        ab_request_bytes=ab, ba_request_bytes=ba, provider=provider,
        deterministic_control_support=deterministic_control_support,
        identity_control=artifact_a == artifact_b,
    )
    return {'commitment': commitment, 'ab_task_bytes': ab, 'ba_task_bytes': ba}
