"""Opt-in uncertainty-preserving ladder descendants of historical score reports.

This policy changes effective scoring states, never the original judge verdicts.
It retains historical aggregation and conservative rubric sensitivity bounds;
it does not infer missing assessments or calibrate literary quality.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from . import core, scoring_v2
from .paths import bundles_path, registry_path
from .repeatability import canonical_json_sha256


POLICY = "uncertainty_preserving_ladder_v1"


def _project(
    compiled: Mapping[str, Any], verdicts: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    indexed, issues = core._verdict_index(verdicts)
    ladders: dict[str, list[tuple[str, int, Mapping[str, Any]]]] = defaultdict(list)
    for record in compiled["domain_questions"]:
        question = record["question"]
        if question.get("question_type") != "subjective_threshold":
            continue
        module_id, qid = record["module_id"], question["id"]
        try:
            order = int(qid.rsplit("threshold_", 1)[-1].split("_", 1)[0])
        except (ValueError, IndexError):
            order = len(ladders[module_id]) + 1
        ladders[module_id].append((qid, order, record))
    projected = deepcopy(list(verdicts))
    first_indices: dict[str, int] = {}
    for index, record in enumerate(verdicts):
        if isinstance(record.get("question_id"), str):
            first_indices.setdefault(record["question_id"], index)
    changes = []
    for module_id, ladder in ladders.items():
        failed: list[str] = []
        unavailable: list[str] = []
        for qid, _, record in sorted(ladder, key=lambda item: item[1]):
            state = core._get_verdict(record, indexed, issues)["verdict"]
            if state == "YES" and (failed or unavailable):
                effective = "NO" if failed else "CANNOT_ASSESS"
                projected[first_indices[qid]]["verdict"] = effective
                changes.append({
                    "question_id": qid, "module_id": module_id,
                    "raw_state": state, "effective_state": effective,
                    "reason": "explicit_lower_no" if failed else "unavailable_lower_prerequisite",
                    "blocking_question_ids": list(failed or unavailable),
                })
            if state == "NO":
                failed.append(qid)
            elif state in {"CANNOT_ASSESS", "NOT_APPLICABLE"}:
                unavailable.append(qid)
    return projected, changes


def score_bundle(
    modules: Sequence[dict[str, Any]], bundle: dict[str, Any],
    verdicts: Sequence[dict[str, Any]], *, artifact_id: str | None = None,
    task_contract: Mapping[str, Any] | None = None,
    admission_policy: str = "strict_import_v1",
) -> dict[str, Any]:
    """Return separate historical and candidate reports with immutable lineage.

    Admission validates the originals before projecting any state. The projected
    ladder is a fixed point of the historical enforcer, allowing both reports to
    use the same v2 scorer without changing its implementation or defaults.
    """
    historical = scoring_v2.score_bundle(
        modules, bundle, verdicts, artifact_id=artifact_id,
        task_contract=task_contract, admission_policy=admission_policy,
    )
    compiled = core.compile_bundle(modules, bundle, task_contract=task_contract)
    projected, changes = _project(compiled, verdicts)
    candidate = scoring_v2.score_bundle(
        modules, bundle, projected, artifact_id=artifact_id,
        task_contract=task_contract, admission_policy="historical_permissive_v1",
    )
    if "import_admission" in historical:
        candidate["import_admission"] = deepcopy(historical["import_admission"])
    context = {
        "aggregation_policy": "historical_v1",
        "compiled_bundle_sha256": canonical_json_sha256(compiled),
        "task_contract_sha256": None if task_contract is None else canonical_json_sha256(task_contract),
    }
    context["scoring_context_sha256"] = canonical_json_sha256({"scoring_policy": POLICY, **context})
    candidate["scoring_policy"] = POLICY
    candidate["scoring_context"] = context
    candidate["ladder_projection"] = {
        "policy": POLICY,
        "raw_verdicts_sha256": canonical_json_sha256(list(verdicts)),
        "historical_parent_report_sha256": canonical_json_sha256(historical),
        "projected_verdicts_sha256": canonical_json_sha256(projected),
        "state_basis": "effective_scoring_states_not_new_judge_verdicts",
        "admission_basis": "original_verdicts_before_projection",
        "changes": changes,
    }
    return {"historical_report": historical, "candidate_report": candidate}


def _read_input(path: Path) -> tuple[Any, str]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig")
    if path.suffix.lower() == ".jsonl":
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    elif path.suffix.lower() == ".json":
        value = json.loads(text)
    elif path.suffix.lower() in {".yaml", ".yml"}:
        value = yaml.safe_load(text)
    else:
        raise core.HBQError("Input must be JSON, JSONL, YAML, or YML")
    return value, hashlib.sha256(raw).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", help="Existing bundle ID")
    parser.add_argument("verdicts", type=Path)
    parser.add_argument("--task-contract", type=Path)
    parser.add_argument("--artifact-id")
    parser.add_argument("--admission-policy", default="strict_import_v1",
                        choices=("strict_import_v1", "historical_permissive_v1"))
    args = parser.parse_args(argv)
    try:
        modules = core.load_modules(registry_path())
        bundle = core.resolve_bundle(core.load_bundles(bundles_path()), args.bundle)
        data, verdicts_sha256 = _read_input(args.verdicts)
        verdicts = core._normalize_verdict_records(data)
        contract = None
        inputs = {"verdicts_file_sha256": verdicts_sha256}
        if args.task_contract:
            contract, contract_sha256 = _read_input(args.task_contract)
            if not isinstance(contract, Mapping):
                raise core.HBQError("Task contract must be an object")
            inputs["task_contract_file_sha256"] = contract_sha256
        output = score_bundle(
            modules, bundle, verdicts, artifact_id=args.artifact_id,
            task_contract=contract, admission_policy=args.admission_policy,
        )
        output["inputs"] = inputs
    except (OSError, ValueError, yaml.YAMLError) as error:
        parser.exit(2, f"ladder uncertainty: {error}\n")
    print(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
