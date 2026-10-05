"""Receipt provenance, sealed-field exclusion and qualified repeated sequences."""
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-qpc24-historical-census-v1/census.py"
spec = importlib.util.spec_from_file_location("qpc24_census_test", PATH)
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def fixture(tmp_path, duplicate_leaf=False):
    roots, packages, chains, all_slots = {}, {}, {}, {}

    def add(root, path, value):
        raw = value if isinstance(value, bytes) else census.canonical(value) + b'\n'
        target = tmp_path / root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        roots.setdefault(root, {})[path] = {"locator": path, "sha256": census.sha(raw), "bytes": len(raw)}
        return census.sha(raw)

    prompt_rows = [{"role": "unselected", "repetition": 1, "batch": 1,
                    "question_count": 2, "prompt_sha256": census.digest(['unselected', i])}
                   for i in range(121)]
    roles = {"v2": "original", "v3": "rewrite", "v5": "public_control_story"}
    indexes = {"v2": 31, "v3": 71, "v5": 121}
    for origin in roles:
        packages[origin] = {"root": origin, "neutral_root": origin + '-neutral', "freeze": "private-freeze.v1.json" if origin == 'v5' else 'private-freeze.v3.json', "approval": "approval.json"}
        all_slots[origin], chains[origin] = [], []
        for index in ([indexes[origin], 111] if origin == 'v3' else [indexes[origin]]):
            role = "public_control_story" if index == 111 else roles[origin]
            repetition = 2 if index == 111 else 3
            sid = f'{role}-r{repetition}-b01'
            slot = {"base_request_index": index, "slot_id": sid, "role": role, "repetition": repetition,
                    "batch": 1, "question_count": 2, "prompt_sha256": census.digest(['prompt', index]),
                    "source_sha256": census.digest(['source', role])}
            all_slots[origin].append(slot)
            prompt_rows[index - 1] = {k: slot[k] for k in ['role', 'repetition', 'batch', 'question_count', 'prompt_sha256']}
            claim_sha = add(origin, f'scheduler-state/claims/{sid}.claim.v1.json', {"slot_id": sid, "base_request_index": index})
            identity_reported = {"provider": "openai", "model": "historical-sol", "reasoning_effort": "high", "session_id": "same-reported-session"}
            identity_sha = add(origin, f'scheduler-state/reported-identity-receipts/{sid}.v1.json', {
                "slot_id": sid, "claim_sha256": claim_sha, "reported": identity_reported,
                "reported_sha256": census.sha(census.canonical(identity_reported) + b'\n')})
            # Invalid escapes in quotes/notes must remain undecoded, including excluded responses.
            second = 'a' if duplicate_leaf else 'b'
            response = ('{"verdicts":[{"question_id":"a","verdict":"YES","exact_quote":"SEALED\\q"},'
                        '{"question_id":"' + second + '","verdict":"CANNOT_ASSESS","note":"SEALED\\q"}]}').encode()
            response_sha = add(origin + '-neutral', f'slot-{index:04d}/responses/batch-{index:04d}.attempt-0001.message.json', response)
            chains[origin].append({"base_request_index": index, "slot_id": sid, "claim_sha256": claim_sha,
                                   "reported_identity_receipt_sha256": identity_sha, "response_sha256": response_sha})
    controller_sha = add('base', 'qpc24-private-controller.v1.json', {"roles": [
        {"role": role, "source_sha256": census.digest(['source', role])} for role in roles.values()]})
    add('base', 'qpc24-private-binding.v1.json', {"controller_sha256": controller_sha, "prompt_records": prompt_rows})
    orphan_sha = add('v3', 'scheduler-state/claims/public_control_story-r2-b02.claim.v1.json', {"status": "CONTACT_STARTED"})
    # Freeze bytes precede approvals; call/terminal commitments are then added to the freeze lineage.
    for origin in roles:
        binding_path = 'live-controller-binding.v1.json' if origin == 'v5' else 'live-controller-binding.v3.json'
        binding_sha = add(origin, binding_path, {"kind": "historical binding"})
        # Lineage chains need approval hashes, so fixture approval bytes bind a stable local freeze marker.
        freeze_sha = add(origin, packages[origin]['freeze'], {"slots": all_slots[origin]})
        approval_sha = add(origin, 'approval.json', {"private_freeze_sha256": freeze_sha, "controller_binding_sha256": binding_sha})
        for row in chains[origin]:
            index, sid = row['base_request_index'], row['slot_id']
            slot = next(r for r in all_slots[origin] if r['base_request_index'] == index)
            row['call_receipt_sha256'] = add(origin, f'scheduler-state/call-receipts/{sid}.v1.json', {
                "slot_id": sid, "claim_sha256": row['claim_sha256'], "approval_sha256": approval_sha,
                "prompt_sha256": slot['prompt_sha256'], "source_sha256": slot['source_sha256'],
                "response_sha256": row['response_sha256'], "reported_identity_receipt_sha256": row['reported_identity_receipt_sha256']})
            row['terminal_sha256'] = add(origin, f'scheduler-state/terminals/{sid}.terminal.v1.json', {
                "slot_id": sid, "status": "accepted", "receipt_sha256": row['call_receipt_sha256']})
    # Historical production v5 stores receipt lineage inside its freeze. For the tiny fixture,
    # omit the approval's v5 freeze link until after that immutable lineage exists.
    frozen = {"slots": all_slots['v5'], "selection": {"target_voting_calls": 3, "target_voting_positions": 6},
              "v3_lineage": {"inherited_v2_complete_receipt_chains": chains['v2'],
                             "semantic_direct_receipt_chains": chains['v3'][:1], "all_21_direct_receipt_chains": chains['v3'],
                             "orphan": {"accepted_b01_index": 111, "excluded_whole_pass": "public_control_story-r2",
                                        "orphan_b02_claim_sha256": orphan_sha, "orphan_b02_terminal_call_identity": "ABSENT"}}}
    # V5 lineage contains only prior receipts; its own receipt hashes belong to settlement.v1.
    frozen['v3_lineage']['inherited_v2_complete_receipt_chains'] = [dict(r) for r in chains['v2']]
    frozen['v3_lineage']['semantic_direct_receipt_chains'] = [dict(r) for r in chains['v3'][:1]]
    frozen['v3_lineage']['all_21_direct_receipt_chains'] = [dict(r) for r in chains['v3']]
    freeze_sha = add('v5', 'private-freeze.v1.json', frozen)
    approval_sha = add('v5', 'approval.json', {"private_freeze_sha256": freeze_sha,
                                            "controller_binding_sha256": roots['v5']['live-controller-binding.v1.json']['sha256']})
    row = chains['v5'][0]
    call_path = f"scheduler-state/call-receipts/{row['slot_id']}.v1.json"
    slot = all_slots['v5'][0]
    row['call_receipt_sha256'] = add('v5', call_path, {"slot_id": row['slot_id'], "claim_sha256": row['claim_sha256'],
        "approval_sha256": approval_sha, "prompt_sha256": slot['prompt_sha256'], "source_sha256": slot['source_sha256'],
        "response_sha256": row['response_sha256'], "reported_identity_receipt_sha256": row['reported_identity_receipt_sha256']})
    row['terminal_sha256'] = add('v5', f"scheduler-state/terminals/{row['slot_id']}.terminal.v1.json", {
        "slot_id": row['slot_id'], "status": "accepted", "receipt_sha256": row['call_receipt_sha256']})
    settlement_sha = add('v5', 'settlement.v1.json', {"private_freeze_sha256": freeze_sha,
        "new_accepted_receipt_chains": [{k: v for k, v in row.items() if k != 'slot_id'}]})
    add('v5', 'settlement.v2.json', {"private_freeze_sha256": freeze_sha, "settlement_v1_sha256": settlement_sha,
        "archived_acceptance_chains": {"v2": 1, "v3": 1, "v5": 1, "total": 3},
        "archived_response_geometry": {"complete_passes": 3, "verdict_positions": 6},
        "valid_evidence_normalizations": {"total": 170, "v5": 10}})
    return {"policy": census.POLICY, "helper_pins": {k: v[1] for k, v in census.HELPERS.items()},
            "roots": [{"locator": k, "files": list(v.values())} for k, v in roots.items()], "packages": packages,
            "controller_root": "base", "membership": {k: [v] for k, v in indexes.items()}, "excluded_indexes": [111],
            "expected": {"requests": 3, "positions": 6, "chains_by_origin": {"v2": 1, "v3": 1, "v5": 1},
                         "positions_per_pass": 2, "batches_per_pass": 1},
            "question_sequence_sha256": census.sha(census.canonical(['a', 'b']) + b'\n')}


def test_qualified_repeats_exclusions_privacy_and_reported_session_gap(tmp_path):
    recipe = fixture(tmp_path)
    report, ledger = census.run(recipe, tmp_path)
    assert report['observed']['accepted_voting_chains'] == 3
    assert report['observed']['qualified_leaf_positions'] == 6
    assert len({r['position_id_sha256'] for r in ledger['leaves']}) == 6
    assert report['observed']['excluded_accepted_chains'] == 1
    assert report['observed']['historical_reserved_claims_hashed'] == 1
    assert report['gaps']['duplicate_reported_session_request_positions'] == 2
    assert report['inherited_declarations']['evidence_normalizations']['total'] == 170
    assert b'SEALED' not in census.canonical({'report': report, 'ledger': ledger})
    assert report['provider_calls_made'] == report['new_provider_votes'] == 0
    assert not census.destination(tmp_path / 'fresh', tmp_path, recipe).exists()
    with pytest.raises(ValueError, match='overlaps'):
        census.destination(tmp_path / 'v2/new', tmp_path, recipe)


def test_changed_receipt_and_duplicate_criterion_sequence_fail(tmp_path):
    recipe = fixture(tmp_path)
    path = tmp_path / 'v2/scheduler-state/terminals/original-r3-b01.terminal.v1.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='Source hash differs'):
        census.run(recipe, tmp_path)
    other = tmp_path / 'duplicate'
    recipe = fixture(other, duplicate_leaf=True)
    with pytest.raises(ValueError, match='criterion sequence'):
        census.run(recipe, other)
