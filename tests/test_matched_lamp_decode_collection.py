"""Provider-free witnesses for the named LAMP continuation; no native claims."""
import importlib.util
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_lamp_decode_collector', REPO / 'evaluation-results/hbq-matched-lamp-20261004/collector_decode.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)


def rows():
    return [{'endpoint': 'grok', 'endpoint_ordinal': ordinal, 'logical_sample_id': str(ordinal).zfill(64)}
            for ordinal in range(1, 8905)]


def imported():
    return {'entries': [{'effective_terminal': {'state': 'accepted', 'native_thread_id': 'native-' + str(n)}}
                        for n in range(1, 6)]}


def test_prefix_union_excludes_five_started_slots_and_keeps_full_denominator(tmp_path):
    manifest = {'requests': rows() + [{'endpoint': 'sol', 'endpoint_ordinal': n} for n in range(1, 8905)]}
    pending, states, ids = d.effective_inventory(manifest, {}, None, tmp_path, None, None, None,
            reader=None, route_root=None, imported=imported(), prepared=True)
    assert len(manifest['requests']) == 17808
    assert len(pending) == 8899 and len(states) == len(ids) == 5
    assert [row['endpoint_ordinal'] for row in pending] == list(range(6, 8905))
    d.c.sample_path(tmp_path, rows()[0]).mkdir()
    with pytest.raises(ValueError, match='cannot be redispatched'):
        d.effective_inventory(manifest, {}, None, tmp_path, None, None, None,
            reader=None, route_root=None, imported=imported(), prepared=True)


def test_effective_union_rejects_duplicate_native_identity(tmp_path):
    prefix = imported(); prefix['entries'][4] = prefix['entries'][0]
    with pytest.raises(ValueError, match='Duplicate effective'):
        d.effective_inventory({'requests': rows()}, {}, None, tmp_path, None, None, None,
            reader=None, route_root=None, imported=prefix, prepared=True)


def test_named_projection_continues_and_preserves_original_failure(tmp_path):
    row = rows()[5]; sample = d.c.sample_path(tmp_path, row); sample.mkdir()
    original = b'{"state":"ambiguous","accepted":false}\n'
    d.c.write_bytes(sample / 'terminal.json', original)
    parent = d.c.CommitState()
    receipt = {'effective_terminal': {'native_thread_id': 'projected-native', 'state': 'accepted'}}
    seen = []
    def strict(*args, commit, **kwargs):
        commit.stop.set(); assert commit.stop.is_set() and not parent.stop.is_set()
        return 'ambiguous'
    with patch.object(d.c, 'collect_one', strict), patch.object(d, 'project', return_value=(receipt, SimpleNamespace(raws={}))), \
            patch.object(d, 'persist_projection', side_effect=lambda *args: seen.append(args)):
        state = d.collect_one(row, {}, {}, None, tmp_path, None, None, None, None, parent, None, None)
    assert state == 'accepted' and not parent.stop.is_set()
    assert parent.native_ids == {'projected-native'} and len(seen) == 1
    assert (sample / 'terminal.json').read_bytes() == original


def test_unknown_failure_stops_and_drains_started_sibling(tmp_path):
    parent = d.c.CommitState(); barrier = threading.Barrier(2); started = []; completed = []
    def strict(row, *args, commit, **kwargs):
        started.append(row['endpoint_ordinal']); barrier.wait(timeout=3)
        if row['endpoint_ordinal'] == 6:
            commit.stop.set(); return 'ambiguous'
        parent.stop.wait(timeout=3); completed.append(row['endpoint_ordinal']); return 'accepted'
    def execute(row):
        return d.collect_one(row, {}, {}, None, tmp_path, None, None, None, None, parent, None, None)
    with patch.object(d.c, 'collect_one', strict), patch.object(d, 'project', side_effect=ValueError('Unknown retry profile')):
        with pytest.raises(ValueError, match='Unknown retry'):
            d.c.dispatch(rows()[5:20], 2, execute, parent)
    assert parent.stop.is_set() and sorted(started) == [6, 7] and completed == [7]


def test_local_failure_does_not_clear_parent_stop_or_allow_prefix_contact(tmp_path):
    parent = d.c.CommitState(); local = d.SampleCommit(parent)
    local.stop.set(); assert local.stop.is_set() and not parent.stop.is_set()
    parent.stop.set(); fresh = d.SampleCommit(parent)
    assert fresh.stop.is_set() and parent.stop.is_set()
    with patch.object(d.c, 'collect_one') as strict:
        with pytest.raises(ValueError, match='cannot contact provider'):
            d.collect_one(rows()[4], {}, {}, None, tmp_path, None, None, None, None, parent, None, None)
        strict.assert_not_called()


def test_saved_projection_receipt_cannot_hide_source_mutation(tmp_path):
    sample = tmp_path / 'sample'; sample.mkdir()
    d.c.write_bytes(sample / 'native-result.json', b'original ambiguous result')
    pins = d.artifacts(sample); d.verify_artifacts(sample, pins)
    (sample / 'native-result.json').write_bytes(b'changed result')
    with pytest.raises(ValueError, match='Immutable sample'):
        d.verify_artifacts(sample, pins)


def test_real_incomplete_prefix_keeps_slot5_ambiguous_and_preserves_all_original_evidence(tmp_path):
    manifest_path = d.PROGRAM / 'lamp-reference/frozen-001/manifest.json'
    if not manifest_path.exists() or not hasattr(d.load('lamp_decode_test_reader', d.READER), 'saved_completion'):
        pytest.skip('Pinned local frozen inputs/pure reader unavailable')
    reader_sha = d.digest(d.READER.read_bytes()); reader = d.implementation(reader_sha)
    tools = Path(r'C:\Users\Haile\.codex\tools')
    sys.path.insert(0, str(tools))
    manifest = json.loads(d.c.p.checked(manifest_path, d.c.MANIFEST_SHA)); root = manifest_path.parent
    subset, validator, receipts = [d.load('lamp_decode_real_' + name, root / 'implementation' / (name + '.py'))
                                  for name in ('schema_subset', 'validate_response', 'codex_receipts')]
    for name in ('schema_subset', 'validate_response', 'codex_receipts'):
        d.c.p.checked(root / 'implementation' / (name + '.py'), manifest['artifacts']['implementation/' + name + '.py']['sha256'])
    before = d.artifacts(d.SOURCE); target_existed = d.TARGET.exists()
    route_root = Path(r'C:\Users\Haile\.codex\state\model-work-queue-cwr-placeholder-r31')
    binding = d.c.verify_job_binding(d.SOURCE, manifest, root, d.c.MANIFEST_SHA, 'grok', tools)
    row = next(row for row in manifest['requests'] if row['endpoint'] == 'grok' and row['endpoint_ordinal'] == 4)
    entry, reads = d.project(d.c.sample_path(d.SOURCE, row), row, manifest, binding, root, subset, validator, reader, route_root)
    assert entry['effective_terminal']['state'] == 'accepted'
    assert entry['effective_terminal']['strict_v5_satisfied'] is False
    assert entry['original_native_envelope_reconstructed'] is False and entry['physical_contact_cardinality_proven'] is False
    assert reads.raws['updates_projection'] and entry['history_commitments']['updates']['sha256']
    with pytest.raises(ValueError, match='incomplete-prefix'):
        d.prefix(manifest, root, tools, receipts, subset, validator, reader, route_root)
    prefix, snapshots = d.prefix(manifest, root, tools, receipts, subset, validator, reader, route_root, allow_incomplete=True)
    assert prefix['strict_admissions'] == 1 and prefix['projected_admissions'] == 3
    assert set(snapshots) == {'1', '2', '4'} and len(set(prefix['native_ids'])) == 5
    assert prefix['unresolved_source_observations'] == [5] and prefix['human_release_eligible'] is False
    assert prefix['entries'][4]['effective_terminal']['state'] == 'ambiguous'
    assert [value['effective_terminal']['native_thread_id'] for value in prefix['entries']] == prefix['native_ids']
    assert all(value['effective_terminal']['strict_v5_satisfied'] is False
               for value in prefix['entries'] if value['policy'] == d.POLICY)
    for ordinal, files in snapshots.items():
        for name, raw in files.items(): d.c.write_bytes(tmp_path / 'prefix-snapshots' / ordinal / name, raw)
    pending, states, ids = d.effective_inventory(manifest, binding, root, tmp_path, receipts, subset, validator,
            reader=reader, route_root=route_root, imported=prefix)
    assert len(pending) == 8899 and len(states) == len(ids) == 5 and pending[0]['endpoint_ordinal'] == 6
    assert states == ['accepted', 'accepted', 'accepted', 'accepted', 'ambiguous']
    raw_updates = tmp_path / 'prefix-snapshots/2/updates'
    raw_updates.write_bytes(raw_updates.read_bytes() + b'\n')
    with pytest.raises(ValueError):
        row2 = next(row for row in manifest['requests'] if row['endpoint'] == 'grok' and row['endpoint_ordinal'] == 2)
        d.effective_replay(d.c.sample_path(tmp_path, row2), row2, manifest, binding, root, receipts, subset, validator,
                output=tmp_path, reader=reader, route_root=route_root, imported=prefix)
    assert d.artifacts(d.SOURCE) == before and d.TARGET.exists() == target_existed
