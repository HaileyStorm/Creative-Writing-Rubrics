"""Exact source links, singleton conservation and sealed-field boundaries."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-poetry-architecture-historical-census-v1/census.py"
spec = importlib.util.spec_from_file_location("architecture_census_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path, monkeypatch, wrong_public_link=False):
    public_root = tmp_path / 'public'
    monkeypatch.setattr(census, 'REPOSITORY', public_root)
    files, public_files, slots = {'ablation': [], 'dspy': []}, [], []

    def add(root, path, value, public=False):
        raw = value if isinstance(value, bytes) else census.canonical(value)
        target = (public_root if public else tmp_path / root) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        entry = {'locator': path, 'sha256': census.sha(raw), 'bytes': len(raw)}
        (public_files if public else files[root]).append(entry)
        return census.sha(raw)

    for leaf in ('necessity', 'scope'):
        for repeat in range(1, 3):
            sid = f'slot-{len(slots) + 1:03d}'
            prompt = ('SEALED_PROMPT_' + leaf).encode()
            slot = {'slot_id': sid, 'case_id': 'case-1', 'leaf_id': leaf, 'repeat': repeat, 'prompt_sha256': census.sha(prompt)}
            slots.append(slot)
            base = f'attempts/{sid}/attempt-01'
            raw = ('{"verdicts":[{"question_id":"' + leaf + '","verdict":"YES","note":"SEALED\\q"}]}').encode()
            route = {'kind': 'codex_exact_transport_attestation_v1', 'fallback_used': False,
                'prompt_sha256': slot['prompt_sha256'], 'raw_response_sha256': census.sha(raw),
                'reported': {'provider': 'openai', 'model': 'gpt-5.6-sol', 'reasoning_effort': 'high'}}
            route_sha = add('ablation', base + '/route-attestation.bin', route)
            add('ablation', base + '/raw-response.bin', raw)
            add('ablation', f'adapter-attempts/{sid}/attempt-01/responses/batch-0001.attempt-0001.message.json', raw)
            add('ablation', f'executor-dry/rendered-prompts/{sid}.txt', prompt)
            add('ablation', f'executor-dry/inputs/{sid}.txt', b'SEALED_SOURCE')
            identity = {'controller_id': 'controller', 'slot_id': sid, 'attempt': 1}
            add('ablation', f'claims/{sid}.json', {**identity, 'state': 'claimed_before_contact', 'prompt_sha256': slot['prompt_sha256']})
            add('ablation', f'terminals/{sid}.json', {**identity, **{k: slot[k] for k in ('case_id', 'leaf_id', 'repeat', 'prompt_sha256')},
                'attempt_path': base, 'raw_path': base + '/raw-response.bin', 'route_path': base + '/route-attestation.bin',
                'dispatcher_sha256': census.digest('declared-dispatcher'), 'transport_marker': 'exact_codex_adapter_v1',
                'disposition': 'terminal_accepted', 'raw_sha256': census.sha(raw), 'route_sha256': route_sha,
                'verdict': {'question_id': leaf, 'verdict': 'YES', 'evidence': 'NOT_DECODED'}})
    aggregate = census.digest({s['slot_id']: s['prompt_sha256'] for s in slots})
    add('ablation', 'controller-manifest.json', {'controller_id': 'controller', 'controller_contract_sha256': census.digest('contract'),
                                               'executor_prompt_aggregate_sha256': aggregate, 'slots': slots})
    add('ablation', 'executor-dry/study-manifest.json', {'prompt_aggregate_sha256': aggregate, 'slots': slots})
    add('ablation', 'settlement-plan.v1.json', {'controller_id': 'controller', 'slots': [s['slot_id'] for s in slots]})
    add('ablation', 'settlement.v1.json', b'NOT_DECODED_OUTCOMES\\q')
    settlement = add('dspy', 'dspy-compile-settlement.json', b'NOT_DECODED_OUTCOMES\\q')
    export = add('dspy', 'compiled-static-export.txt', b'NOT_DECODED_EXPORT')
    paths = [f'responses/batch-{i:04d}.attempt-0001.message.json' for i in range(1, 3)]
    for path in paths:
        add('dspy', path, b'NOT_DECODED_DSPY_RESPONSE\\q')
    add(None, 'ablation.json', {'opaque_private_receipt_and_settlement_commitment_sha256': census.digest('unknown-convention')}, public=True)
    add(None, 'dspy.json', {'source_commitments': {'settlement_sha256': census.digest('wrong') if wrong_public_link else settlement,
                                                'static_export_sha256': export},
                          'execution': {'proposal_responses': 1, 'task_responses': 1}, 'mechanical_metrics': 'NOT_DECODED'}, public=True)
    return {'policy': census.POLICY, 'helper_pins': {k: v[1] for k, v in census.HELPERS.items()},
        'roots': [{'locator': root, 'files': entries} for root, entries in files.items()], 'public_artifacts': public_files,
        'ablation': {'root': 'ablation', 'public_locator': 'ablation.json', 'slot_ids': [s['slot_id'] for s in slots],
                    'expected': {'slots': 4, 'cases': 1, 'repeats': 2, 'criterion_positions': {'necessity': 2, 'scope': 2}}},
        'dspy': {'root': 'dspy', 'public_locator': 'dspy.json', 'message_paths': paths, 'expected_retained_messages': 2,
                 'declared_proposal_responses': 1, 'declared_task_responses': 1},
        'hash_only': ['settlement.v1.json', 'dspy-compile-settlement.json', 'compiled-static-export.txt'],
        'excluded_ancestors': ['original', 'v2']}


def test_source_link_dispositions_once_only_and_private_fields(tmp_path, monkeypatch):
    recipe = fixture(tmp_path, monkeypatch)
    report, ledger = census.run(recipe, tmp_path)
    local = report['observed']['ablation_local']
    assert local['singleton_leaf_positions'] == local['historical_accepted_terminals'] == 4
    assert local['duplicate_response_projections_not_added'] == 4
    assert local['public_aggregate_attributed_leaf_positions'] == 0
    assert len({r['position_id_sha256'] for r in ledger['ablation_local_observations']}) == 4
    assert report['observed']['dspy']['retained_messages_hashed_only'] == 2
    assert report['observed']['dspy']['repeated_content_message_positions'] == 1
    assert report['observed']['dspy']['decoded_or_admitted_leaf_positions'] == 0
    assert report['gaps']['ablation_public_private_link'] == 'unresolved_opaque_commitment_convention'
    assert b'SEALED' not in census.canonical({'report': report, 'ledger': ledger})
    assert report['provider_calls_made'] == report['new_provider_votes'] == 0
    assert not census.destination(tmp_path / 'fresh', tmp_path, recipe).exists()


def test_corrupt_receipt_and_unbound_public_source_fail(tmp_path, monkeypatch):
    recipe = fixture(tmp_path, monkeypatch)
    terminal = tmp_path / 'ablation/terminals/slot-001.json'
    terminal.write_bytes(terminal.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Source hash differs'):
        census.run(recipe, tmp_path)
    other = tmp_path / 'wrong-source-link'
    recipe = fixture(other, monkeypatch, wrong_public_link=True)
    with pytest.raises(ValueError, match='public/private source commitment'):
        census.run(recipe, other)
