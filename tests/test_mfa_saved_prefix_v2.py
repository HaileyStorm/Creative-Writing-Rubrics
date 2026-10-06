"""Metadata-only reservation and immutable source witnesses; no native execution."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / 'evaluation-results/hbq-native-transport-recovery-v1/continue_mfa_saved_prefix_v2.py'
SPEC = importlib.util.spec_from_file_location('test_mfa_saved_prefix_v2_owned', PATH)
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class MFASavedPrefixV2Tests(unittest.TestCase):
    def test_source_dispositions_reserved_once_not_admitted_or_resent(self):
        rows = [{'endpoint': 'grok', 'endpoint_ordinal': n, 'logical_sample_id': f'logical-{n}',
                 'request_sha256': f'request-{n}'} for n in range(1, 435)]
        prefix = [dict(row, state='ambiguous' if row['endpoint_ordinal'] == 131 else 'accepted',
                       native_identity=f'native-{row["endpoint_ordinal"]}') for row in rows[:147]]
        inventory = [{'ordinal': n, 'native_identity': f'native-{n}', 'terminal_sha256': f'terminal-{n}',
                      'retained_artifacts': {'prompt.txt': f'prompt-{n}'},
                      'state': 'ambiguous' if n in (267, 301, 302, 303) else 'semantic_rejected' if n == 148 else 'accepted'}
                     for n in range(148, 307)]
        before = copy.deepcopy((prefix, inventory))
        reserved = p.reserve_once(prefix, rows, inventory)
        self.assertEqual((prefix, inventory), before)
        self.assertEqual([entry['endpoint_ordinal'] for entry in reserved if entry['state'] == 'ambiguous'], [131, 267, 301, 302, 303])
        self.assertEqual(reserved[147]['state'], 'semantic_rejected')
        self.assertTrue(all(entry['no_resend'] and entry['new_votes'] == 0 and not entry['source_admission_replayed'] for entry in reserved))
        self.assertTrue(all('response' not in entry for entry in reserved))
        plan = {'endpoint': 'grok', 'reserved_through': 306, 'prefix': reserved,
                'untouched_request_sha256s': [row['request_sha256'] for row in rows[306:]],
                'endpoint_denominator': 434, 'full_planned_denominator': 868, 'human_label_gate': 'full_verified_plus_explicit'}
        suffix = p.f.suffix_rows(plan, {'manifest': {'requests': rows}})
        self.assertEqual([row['endpoint_ordinal'] for row in suffix], list(range(307, 435)))
        self.assertEqual(len(suffix), 128)
        gate = p.old.label_gate(plan, ['accepted'] * 128, [], explicit=True)
        self.assertEqual(gate['planned'], 868)
        self.assertFalse(gate['human_release_eligible'])
        duplicate = copy.deepcopy(inventory)
        duplicate[0]['native_identity'] = prefix[0]['native_identity']
        with self.assertRaises(ValueError):
            p.reserve_once(prefix, rows, duplicate)
        with self.assertRaises(ValueError):
            p.reserve_once(prefix, rows, inventory[:-1])
        with self.assertRaises(ValueError):
            p.reserve_once(reserved, rows, inventory)

    def test_changed_source_pin_rejected_and_excluded_json_never_decoded(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.json'
            raw = b'{"metadata": 4, "excluded": [UNDECODABLE]}'
            source.write_bytes(raw)
            committed = p.digest(raw)
            self.assertEqual(p.pinned(source, committed), raw)
            self.assertEqual(p.pinned(source, p.meta(raw)), raw)
            with self.assertRaises(ValueError):
                p.pinned(source, {'sha256': committed, 'bytes': len(raw) + 1})
            self.assertEqual(p.metadata_reader()(raw, {'metadata': True}), {'metadata': 4})
            source.write_bytes(raw + b' ')
            with self.assertRaises(ValueError):
                p.pinned(source, committed)


if __name__ == '__main__':
    unittest.main()
