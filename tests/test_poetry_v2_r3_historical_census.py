"""Historical singleton counting, excluded-field privacy and receipt boundaries."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-poetry-v2-r3-historical-census-v1/census.py"
spec = importlib.util.spec_from_file_location("poetry_r3_census_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path, mismatched_projection=False):
    files, slots = {"source": [], "neutral": []}, []

    def add(root, path, value):
        raw = value if isinstance(value, bytes) else census.canonical(value)
        target = tmp_path / root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        files[root].append({"locator": path, "sha256": census.sha(raw), "bytes": len(raw)})

    study, contract, qid = "historical-poetry", census.digest('contract'), "scope.poetry_poem.form"
    binding = {"study_id": study, "study_contract_sha256": contract,
               "route": "codex", "model": "historical-sol", "reasoning": "high"}
    for case in range(2):
        for arm in range(2):
            for repeat in range(1, 4):
                sid = f'slot-{len(slots) + 1:03d}'
                source = f'SEALED_SOURCE_{case}'.encode()
                prompt = f'SEALED_PROMPT_{case}_{arm}'.encode()
                slot = {"slot_id": sid, "case_id": str(case), "arm": str(arm), "repeat": repeat,
                        "fixture_sha256": census.sha(source), "prompt_sha256": census.sha(prompt)}
                slots.append(slot)
                add('source', f'inputs/{sid}.txt', source)
                add('source', f'rendered-prompts/{sid}.txt', prompt)
                identity = {"study_id": study, "slot_id": sid, "attempt": 1}
                receipt = {key: binding[key] for key in ('route', 'model', 'reasoning')}
                receipt.update(prompt_sha256=slot['prompt_sha256'], fixture_sha256=slot['fixture_sha256'])
                add('source', f'claims/{sid}.json', {**identity, **receipt, "state": "claimed_before_contact"})
                leaf = ('{"question_id":"' + qid + '","verdict":"YES","evidence":[{"exact_quote":"SEALED\\q"}]}')
                projected = leaf.replace('"YES"', '"NO"') if mismatched_projection and len(slots) == 1 else leaf
                payload = '{"verdicts":[' + leaf + '],"note":"SEALED\\q"}'
                terminal = census.canonical({**identity, "state": "terminal_valid", "receipt": receipt,
                                             "response_sha256": census.digest('declared-full-payload')})[:-1]
                add('source', f'terminals/{sid}.json', terminal + (',"payload":' + payload + ',"verdict":' + projected + '}').encode())
                add('neutral', sid + '/responses/batch-0001.attempt-0001.message.json', payload.encode())
    add('source', 'controller-manifest.json', {"study_id": study, "contract_sha256": contract, "slots": slots,
        "prompt_aggregate_sha256": census.digest({s['slot_id']: s['prompt_sha256'] for s in slots})})
    add('source', 'controller-binding.v1.json', binding)
    add('source', 'settlement-plan.v1.json', {"study_id": study, "valid_terminals_required": 12})
    add('source', 'settlement.v1.json', b'NOT_DECODED_SETTLEMENT\\q')
    add('source', 'controller.py', b'NOT_EXECUTED')
    return {"policy": census.POLICY, "helper_pins": {k: v[1] for k, v in census.HELPERS.items()},
            "source_root": "source", "neutral_root": "neutral",
            "roots": [{"locator": root, "files": entries} for root, entries in files.items()],
            "slot_ids": [s['slot_id'] for s in slots], "question_id": qid,
            "expected": {"slots": 12, "fixtures": 2, "arms": 2, "repeats": 3, "prompt_hashes": 4},
            "historical_study_source": {"sha256": census.digest('declared-study')},
            "excluded_ancestors": ['original', 'r2']}


def test_singleton_repeat_geometry_and_privacy_boundary(tmp_path):
    recipe = fixture(tmp_path)
    report, ledger = census.run(recipe, tmp_path)
    assert report['observed']['historical_valid_terminal_observations'] == 12
    assert report['observed']['singleton_leaf_positions'] == 12
    assert report['observed']['duplicate_terminal_projections_not_added'] == 12
    assert len({r['position_id_sha256'] for r in ledger['observations']}) == 12
    assert report['observed']['verdict_states'] == {'YES': 12}
    assert report['gaps'] == {'native_identity_unavailable_observations': 12,
                             'canonical_payload_hashes_retained_declared_not_verified': 12}
    assert b'SEALED' not in census.canonical({'report': report, 'ledger': ledger})
    assert report['provider_calls_made'] == report['new_provider_votes'] == 0
    assert not census.destination(tmp_path / 'fresh', tmp_path, recipe).exists()
    with pytest.raises(ValueError, match='overlaps'):
        census.destination(tmp_path / 'source/new', tmp_path, recipe)
    recipe['expected']['repeats'] = 2
    with pytest.raises(ValueError, match='geometry'):
        census.run(recipe, tmp_path)


def test_changed_receipt_and_duplicate_projection_fail(tmp_path):
    recipe = fixture(tmp_path)
    terminal = tmp_path / 'source/terminals/slot-001.json'
    terminal.write_bytes(terminal.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Source hash differs'):
        census.run(recipe, tmp_path)
    other = tmp_path / 'different-projection'
    recipe = fixture(other, mismatched_projection=True)
    with pytest.raises(ValueError, match='duplicate verdict projection'):
        census.run(recipe, other)
