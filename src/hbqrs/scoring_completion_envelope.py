"""Opt-in finite completion envelope for historical HBQ-RS scores.

This separate policy does not alter the historical report or verdicts. It
enumerates scorer-only YES, NO, and NOT_APPLICABLE replacements for unassessed
score/status questions. It never treats synthetic
completions as admitted evidence, new judge outputs, or confidence intervals.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from . import core, scoring_v2
from .paths import bundles_path, registry_path
from .strict_input import POLICY as STRICT_INPUT_POLICY, load_structured_input

POLICY = 'finite_scorer_completion_envelope_v2'
REPLACEMENTS = ('NO', 'YES', 'NOT_APPLICABLE')
MAX_CASES = 19683
CORE_SHA256 = '8c6022efc005f45e40df2ca9e7f8d508c50af6ae7197384b5798773ea968162a'


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def completion_envelope(
    modules: Sequence[dict[str, Any]], bundle: dict[str, Any], verdicts: list[dict[str, Any]], *,
    artifact_id: str, task_contract: Mapping[str, Any] | None = None,
    admission_policy: str = 'strict_import_v1', max_cases: int = MAX_CASES,
) -> dict[str, Any]:
    """Enumerate rounded historical scores, or withhold the numeric envelope.

    The original inputs must pass strict import admission. Supplemental
    unknowns are counted separately under the pinned core. Other verdicts and
    the contract remain fixed.
    An over-limit calculation or any non-SCORED completion has no envelope.
    """
    if type(max_cases) is not int or not 1 <= max_cases <= MAX_CASES:
        raise ValueError('max_cases must be an integer from 1 through 19683')
    if admission_policy not in ('strict_import_v1', 'strict_import_v2', 'strict_import_v3'):
        raise ValueError('a strict import policy is required')
    if type(artifact_id) is not str or not artifact_id.strip():
        raise ValueError('a nonblank artifact_id is required')
    if type(verdicts) is not list or any(type(row) is not dict or type(row.get('question_id')) is not str for row in verdicts):
        raise ValueError('verdicts must be a list with explicit question IDs')
    if hashlib.sha256(Path(core.__file__).read_bytes()).hexdigest() != CORE_SHA256:
        raise ValueError('unsupported core implementation for supplemental exclusion')
    before = {'modules': _digest(modules), 'bundle': _digest(bundle), 'verdicts': _digest(verdicts),
              'task_contract': _digest(task_contract), 'artifact_id': _digest(artifact_id)}
    admission = None
    if admission_policy == 'strict_import_v3':
        admission = scoring_v2.validate_import_admission(modules, bundle, verdicts, artifact_id=artifact_id,
                                                          task_contract=task_contract, admission_policy=admission_policy)
    compiled = core.compile_bundle(modules, bundle, task_contract=task_contract)
    compiled_rows = core.compiled_questions(compiled)
    if any(row['role'] not in ('domain', 'hard_gate', 'penalty', 'supplemental') for row in compiled_rows):
        raise ValueError('unsupported compiled role')
    selected = [row['question']['id'] for row in compiled_rows]
    scored = {row['question']['id'] for row in compiled_rows if row['role'] != 'supplemental'}
    supplemental = set(selected) - scored
    ids = [row['question_id'] for row in verdicts]
    if len(selected) != len(set(selected)) or len(ids) != len(set(ids)) or not set(ids) <= set(selected):
        raise ValueError('selected or verdict identities are duplicated or out of scope')
    if admission is None:
        admission = scoring_v2.validate_import_admission(modules, bundle, verdicts, artifact_id=artifact_id,
                                                          task_contract=task_contract, admission_policy=admission_policy)
    historical = core.score_bundle(modules, bundle, verdicts, artifact_id=artifact_id, task_contract=task_contract)
    positions = [index for index, row in enumerate(verdicts)
                 if row['verdict'] == 'CANNOT_ASSESS' and row['question_id'] in scored]
    omitted = sorted(scored - set(ids))
    supplemental_unassessed = sum(row['verdict'] == 'CANNOT_ASSESS' and row['question_id'] in supplemental
                                  for row in verdicts)
    supplemental_omitted = len(supplemental - set(ids))
    count = len(REPLACEMENTS) ** (len(positions) + len(omitted))
    result: dict[str, Any] = {
        'policy': POLICY, 'input_sha256': before, 'admission': admission,
        'historical_status': historical['status'], 'historical_final_score': historical['final_score'],
        'explicit_unassessed': len(positions), 'omitted_questions': len(omitted),
        'supplemental_unassessed': supplemental_unassessed, 'supplemental_omitted': supplemental_omitted,
        'core_sha256': CORE_SHA256,
        'required_completions': count, 'maximum_completions': max_cases,
        'completion_states': list(REPLACEMENTS), 'numeric_completion_bounds': None,
        'limitations': 'Fixed other verdicts and contract; supplemental unknowns are excluded from score/status '
                       'enumeration under the pinned core. Scorer-only synthetic completions do not establish '
                       'admissible evidence, human alignment, population reliability, statistical confidence or '
                       'a range beyond the enumerated replacements. Values use historical score rounding.',
    }
    if count > max_cases:
        result['status'] = 'NOT_COMPUTED_LIMIT'
    else:
        scores: list[float] = []
        non_scored = 0
        for states in itertools.product(REPLACEMENTS, repeat=len(positions) + len(omitted)):
            candidate = deepcopy(verdicts)
            for index, state in zip(positions, states[:len(positions)]):
                candidate[index]['verdict'] = state
            for qid, state in zip(omitted, states[len(positions):]):
                candidate.append({'artifact_id': artifact_id, 'bundle_id': bundle['bundle_id'],
                                  'question_id': qid, 'verdict': state, 'confidence': 0.0, 'evidence': [],
                                  'note': 'Scorer-only completion; no source evidence is asserted.'})
            report = core.score_bundle(modules, bundle, candidate, artifact_id=artifact_id, task_contract=task_contract)
            score = report['final_score']['observed']
            if report['status'] != 'SCORED' or type(score) not in (int, float) or not math.isfinite(score):
                non_scored += 1
            else:
                scores.append(score)
        if len(scores) + non_scored != count:
            raise RuntimeError('incomplete enumeration')
        result['non_scored_completions'] = non_scored
        if non_scored:
            result['status'] = 'INDETERMINATE_NON_SCORED_COMPLETION'
        else:
            result['status'] = 'ENUMERATED_FIXED_VERDICT_COMPLETIONS'
            result['numeric_completion_bounds'] = {'lower': min(scores), 'upper': max(scores)}
    if before != {'modules': _digest(modules), 'bundle': _digest(bundle), 'verdicts': _digest(verdicts),
                  'task_contract': _digest(task_contract), 'artifact_id': _digest(artifact_id)}:
        raise RuntimeError('input mutation detected')
    return result


def _read_input(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    if path.suffix.lower() == '.json':
        value = json.loads(text)
    elif path.suffix.lower() == '.jsonl':
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif path.suffix.lower() in ('.yaml', '.yml'):
        value = yaml.safe_load(text)
    else:
        raise core.HBQError('Input must be JSON, JSONL, YAML, or YML')
    return value, hashlib.sha256(raw).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle')
    parser.add_argument('verdicts', type=Path)
    parser.add_argument('--artifact-id', required=True)
    parser.add_argument('--task-contract', type=Path)
    parser.add_argument('--admission-policy', choices=('strict_import_v1', 'strict_import_v2', 'strict_import_v3'), default='strict_import_v1')
    parser.add_argument('--input-policy', choices=('historical_v1', STRICT_INPUT_POLICY), default='historical_v1',
                        help='structured-file parsing policy for verdicts and any task contract')
    parser.add_argument('--max-cases', type=int, default=MAX_CASES)
    args = parser.parse_args(argv)
    modules = core.load_modules(registry_path())
    bundle = core.resolve_bundle(core.load_bundles(bundles_path()), args.bundle)
    def read_input(path: Path) -> tuple[Any, str]:
        if args.input_policy == 'historical_v1':
            return _read_input(path)
        value, receipt = load_structured_input(path)
        return value, receipt['sha256']

    data, verdicts_bytes_hash = read_input(args.verdicts)
    verdicts = core._normalize_verdict_records(data, reject_conflicting_compact_ids=True)
    contract, contract_bytes_hash = read_input(args.task_contract) if args.task_contract else (None, None)
    result = completion_envelope(modules, bundle, verdicts, artifact_id=args.artifact_id,
                                 task_contract=contract, admission_policy=args.admission_policy, max_cases=args.max_cases)
    result['input_file_sha256'] = {'verdicts': verdicts_bytes_hash, 'task_contract': contract_bytes_hash}
    if args.input_policy != 'historical_v1':
        result['input_parsing_policy'] = args.input_policy
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
