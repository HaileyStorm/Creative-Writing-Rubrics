import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('edupo_metadata', Path(__file__).with_name('metadata.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_byte_tsv_handles_quotes_and_rejects_malformed_fields():
    raw = b'filename\tvalue\r\n"first\tname"\t"one\r\ntwo"\r\n"other"\t"a""b"\r\n'
    assert list(module.tsv_rows(raw)) == [[b'filename', b'value'], [b'first\tname', b'one\r\ntwo'],
                                          [b'other', b'a"b']]
    with pytest.raises(ValueError):
        list(module.tsv_rows(b'"unterminated'))


def test_pins_and_git_tree_encoding_fail_closed():
    assert module.tree_object([]) == '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
    with pytest.raises(ValueError, match='table bytes'):
        module.project(b'not the pinned file', {})
    with pytest.raises(ValueError, match='tree root'):
        module.verify_tree({'sha': 'not-the-root', 'truncated': False})


def test_presence_is_syntax_not_value_decoding():
    assert module.NUMBER.fullmatch(b'-1.25e+2')
    assert not module.NUMBER.fullmatch(b'NaN')
    assert not module.NUMBER.fullmatch(b'')
