"""Run portable acceptance checks on artificial text in a temporary directory."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import boundary


def span(source, start, end):
    return {'start': start, 'end': end, 'sha256': boundary.digest(source[start:end])}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main():
    # Deliberately artificial material exercises multibyte offsets, not quality.
    before = 'A café.\n'.encode('utf-8')
    target = 'Unit β. End.\n'.encode('utf-8')
    after = 'Next Ω.'.encode('utf-8')
    source = before + target + after
    t0, t1 = len(before), len(before) + len(target)
    declaration = {'boundary_kind': 'interior_supplied',
                   'preceding': span(source, 0, t0), 'target': span(source, t0, t1),
                   'exit': span(source, t1 - len(b'End.\n'), t1),
                   'following': span(source, t1, len(source))}
    expected = boundary.validate(source, boundary.digest(source), declaration)
    require(len({q['shared_context_sha256'] for q in expected['question_bindings']}) == 1, 'context bindings diverge')
    altered = copy.deepcopy(declaration)
    withheld_source = source[:t1]
    altered['following'] = None
    for kind in ('terminal', 'interior_withheld'):
        altered['boundary_kind'] = kind
        boundary.validate(withheld_source, boundary.digest(withheld_source), altered)
    unspecified = {'boundary_kind': 'unspecified', **{r: None for r in ('preceding','target','exit','following')}}
    boundary.validate(source, boundary.digest(source), unspecified)

    bad = []
    split = copy.deepcopy(declaration)
    split['preceding']['end'] = before.index('é'.encode()) + 1
    bad.append(('UTF-8 split', source, boundary.digest(source), split))
    overlap = copy.deepcopy(declaration)
    overlap['following'] = span(source, t1 - 1, len(source))
    bad.append(('overlap', source, boundary.digest(source), overlap))
    wrong = copy.deepcopy(declaration); wrong['target']['sha256'] = '0' * 64
    bad.append(('span hash', source, boundary.digest(source), wrong))
    bad.append(('source hash', source, '0' * 64, declaration))
    missing = copy.deepcopy(declaration); missing['following'] = None
    bad.append(('missing following', source, boundary.digest(source), missing))
    terminal = copy.deepcopy(declaration); terminal['boundary_kind'] = 'terminal'
    bad.append(('terminal contradiction', source, boundary.digest(source), terminal))
    unknown = copy.deepcopy(declaration); unknown['boundary_kind'] = 'unspecified'
    bad.append(('unspecified spans', source, boundary.digest(source), unknown))
    gap = copy.deepcopy(declaration); gap['preceding'] = None
    bad.append(('unassigned prose', source, boundary.digest(source), gap))
    boolean = copy.deepcopy(declaration); boolean['target']['start'] = True
    bad.append(('boolean offset', source, boundary.digest(source), boolean))
    exit_span = copy.deepcopy(declaration); exit_span['exit'] = span(source, t0, t1 - 1)
    bad.append(('exit suffix', source, boundary.digest(source), exit_span))
    for name, data, digest, case in bad:
        try:
            boundary.validate(data, digest, case)
        except ValueError:
            pass
        else:
            raise ValueError('accepted invalid case: ' + name)

    temp_parent = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='scene-boundary-check-', dir=temp_parent) as directory:
        root = Path(directory)
        require(root.resolve().parent == temp_parent, 'temporary directory escaped tool folder')
        src, dec, output = root/'source.txt', root/'declaration.json', root/'result.json'
        src.write_bytes(source); dec.write_text(json.dumps(declaration), encoding='utf-8')
        args = [sys.executable, '-O', '-B', str(Path(__file__).with_name('boundary.py')),
                '--source', str(src), '--source-sha256', boundary.digest(source),
                '--declaration', str(dec), '--output', str(output)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        def run():
            return subprocess.run(args, capture_output=True, timeout=30, creationflags=flags)
        first = run()
        require(first.returncode == 0 and output.read_bytes() == boundary.canonical(expected), 'CLI roundtrip failed')
        retained = output.read_bytes()
        require(run().returncode != 0 and output.read_bytes() == retained, 'output overwrite accepted')
        dup = root/'duplicate-output.json'; args[-1] = str(dup)
        dec.write_text('{"boundary_kind":"terminal","boundary_kind":"unspecified"}', encoding='utf-8')
        require(run().returncode != 0 and not dup.exists(), 'duplicate key accepted')
    print('SCENE_BOUNDARY_ACCEPTANCE_PASSED: four kinds; ten invalid declarations; CLI roundtrip, no-overwrite and duplicate-key rejection')


if __name__ == '__main__':
    main()
