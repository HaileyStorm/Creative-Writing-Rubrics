import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('census', Path(__file__).with_name('census.py'))
census = importlib.util.module_from_spec(spec)
spec.loader.exec_module(census)


def test_nul_records_keep_whitespace_in_filenames_and_shared_blobs():
    oid = b'a' * 40
    raw = (b'100644 blob ' + oid + b' 4\tevaluation-results/a/has space.json\0'
           + b'100644 blob ' + oid + b' 4\tevaluation-results/b/has\nnewline.txt\0')
    rows = census.parse_tree(raw)
    assert [r['result_directory'] for r in rows] == ['a', 'b']
    assert rows[1]['path'].endswith('has\nnewline.txt')
    assert rows[0]['git_blob_sha1'] == rows[1]['git_blob_sha1']


def test_refuses_truncated_or_unsupported_git_entries():
    oid = b'a' * 40
    with pytest.raises(ValueError, match='incomplete'):
        census.parse_tree(b'100644 blob ' + oid + b' 4\tevaluation-results/a/file')
    with pytest.raises(ValueError, match='unsupported'):
        census.parse_tree(b'120000 blob ' + oid + b' 4\tevaluation-results/a/link\0')
