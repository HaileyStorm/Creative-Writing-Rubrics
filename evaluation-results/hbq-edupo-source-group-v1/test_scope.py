import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('edupo_scope', Path(__file__).with_name('scope.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_static_header_requires_the_expected_write_structure():
    source = b"measures = ('alpha', 'beta')\nwith open(output_file, 'w') as f:\n f.write('filename')\n for m in measures:\n  f.write('\\t'+m)\n  avg[m] = 0\n f.write('\\n')\n"
    assert module.evaluator_header(source) == ['filename', 'alpha', 'beta']
    with pytest.raises(ValueError, match='header-write'):
        module.evaluator_header(source.replace(b"f.write('filename')", b"f.write('wrong')"))


def test_group_and_path_counts_do_not_expose_members():
    groups = [b'ccv', b'source-1', b'source-2', b'source-3', b'source-4']
    rows = [[f'old/p{i:03}.txt'.encode(), groups[i // 20], b'private-rating'] for i in range(100)]
    paths = [f'new/p{i:03}.txt' for i in range(100)]
    result = module.group_summary(rows, paths)
    assert result['source_group_sizes_sorted'] == [20] * 5
    assert result['ccv_tagged_rows'] == 20
    assert result['table_parent_count'] == result['table_to_tree_parent_mappings'] == 1
    assert result['table_paths_ending_in_tree_path'] == result['tree_paths_ending_in_table_path'] == 0
    assert 'private-rating' not in str(result)
    with pytest.raises(ValueError, match='matching differs'):
        module.group_summary(rows, paths[:-1] + [paths[0]])
