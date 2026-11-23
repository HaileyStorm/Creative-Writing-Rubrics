"""Verify public historical source commitments without executing the source."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

RESULT_COMMIT = '2ba7cb245007f88724a4e243a97dc9abb174e0b2'
SOURCE_COMMIT = 'd27fd700cb754bad036609f799ef7c9dac3d7a61'
PACKAGE = 'hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1'
SOURCE = 'hbq-human-alignment-optimizer-v5-f20-broader-development-sol-validation-v1'
SOURCES = {
    f'evaluation-results/{SOURCE}/executor.py': 'dc093e764e29fcfca2997b24e3b1467c94fef2b6f472961e3296566af596fb66',
    f'evaluation-results/{SOURCE}/study-contract.json': 'eff9b08f894ccdde3d4e8d869f8e606f74408e88c2cefd99f2d1ed0fc3765c40',
    f'evaluation-results/{SOURCE}/README.md': '2e50b03d8105e7ec358fa626fe4403ddf92daa614bcbfd7ea9f6c1dfa01e3960',
    'tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_sol_validation_v1.py': '8e4772adb4cd419f66387881cab6b4744da2523f13af5787d98c171203e16d10',
}
PUBLIC_FILES = {
    'README.md': '00a4527783c55e7b64bdefff320358bb1c3a84c70dc90106bca0a75cffb363ba',
    'result.json': '34441a265fbf4d654b2de4e89acfcc4b436029f0ff8c7cca47c9759ffc922fa3',
    'verify.py': '21e209f0c9e72a2a0ad187306200ed33de57bdd4eccfa896b29d64157aedc938',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def git_file(repo, commit, path):
    return subprocess.run(['git', '-C', str(repo), 'show', commit + ':' + path],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def verify(repo):
    base = 'evaluation-results/' + PACKAGE + '/'
    files = {name: git_file(repo, RESULT_COMMIT, base + name)
             for name in (*PUBLIC_FILES, 'study-contract.json')}
    contract = json.loads(files['study-contract.json'])
    result = json.loads(files['result.json'])
    for name, digest in PUBLIC_FILES.items():
        require(sha256(files[name]).hexdigest() == digest, 'public file differs: ' + name)
    require(contract['publication_manifest']['bound_files'] == PUBLIC_FILES, 'public file commitments differ')
    require(contract['source_execution'] == result['source_execution'], 'source declarations differ')
    require(result['source_execution']['source_commit'] == SOURCE_COMMIT, 'source commit differs')
    require(result['source_execution']['source_executor_sha256'] == SOURCES[f'evaluation-results/{SOURCE}/executor.py'],
            'executor commitment differs')
    require(SOURCE_COMMIT.encode() in files['verify.py'] and
            all(digest.encode() in files['verify.py'] for digest in SOURCES.values()),
            'verifier source commitments differ')
    for path, digest in SOURCES.items():
        require(sha256(git_file(repo, SOURCE_COMMIT, path)).hexdigest() == digest,
                'historical Git object differs: ' + path)
    return {'status': 'public_source_bytes_verified', 'result_commit': RESULT_COMMIT,
            'source_commit': SOURCE_COMMIT, 'source_file_count': len(SOURCES),
            'provider_calls': 0, 'historical_execution_authenticated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().repo), sort_keys=True))


if __name__ == '__main__':
    main()
