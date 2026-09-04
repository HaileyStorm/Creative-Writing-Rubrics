"""Provider-free, endpoint-separated diagnostics for the frozen V14 TRAIN44 pair."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
GROK = HERE / "expansion.py"
SOL = HERE / "expansion_sol.py"
CHILD20 = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DESCENDANT = "candidate-62195a3b90edd96d"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
ENDPOINTS = {"grok_primary": "grok", "sol_later": "sol"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("diagnostic report module cannot load")
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def receipt_reports(*, grok_root: Path, grok_acknowledgement_sha256: str, sol_root: Path, sol_acknowledgement_sha256: str, split_manifest: Path, hanna_csv: Path, successor_contract: Path, recovered_descendant: Path) -> dict[str, Mapping[str, Any]]:
    grok, sol = _module(GROK, "_v14_train_diagnostic_grok"), _module(SOL, "_v14_train_diagnostic_sol")
    return {
        "grok": grok.report(output_root=Path(grok_root), authorization_acknowledgement_sha256=grok_acknowledgement_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant)),
        "sol": sol.report(output_root=Path(sol_root), authorization_acknowledgement_sha256=sol_acknowledgement_sha256, split_manifest=Path(split_manifest), hanna_csv=Path(hanna_csv), successor_contract=Path(successor_contract), recovered_descendant=Path(recovered_descendant)),
    }


def _number(value: Any, label: str) -> float:
    if type(value) not in {int, float} or isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError(f"invalid {label}")
    return float(value)


def _rank(values: Sequence[float]) -> list[float]:
    order, ranks, start = sorted(range(len(values)), key=values.__getitem__), [0.0] * len(values), 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for index in order[start:end]:
            ranks[index] = (start + 1 + end) / 2
        start = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    left_mean, right_mean = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return None if denominator == 0 else numerator / denominator


def _dimension(rows: Sequence[Mapping[str, Any]], dimension: str) -> dict[str, Any]:
    scores = [_number(row["scores"][dimension], "score") for row in rows]
    targets = [_number(row["target"][dimension], "target") for row in rows]
    errors = [score - target for score, target in zip(scores, targets, strict=True)]
    eligible = correct = reversed_pairs = model_tied = 0
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            human = (targets[left] > targets[right]) - (targets[left] < targets[right])
            if human == 0:
                continue
            eligible += 1
            model = (scores[left] > scores[right]) - (scores[left] < scores[right])
            if model == 0:
                model_tied += 1
            elif model == human:
                correct += 1
            else:
                reversed_pairs += 1
    if eligible == 0 or correct + reversed_pairs + model_tied != eligible:
        raise ValueError("invalid pairwise TRAIN diagnostic geometry")
    score_mean, target_mean = sum(scores) / len(scores), sum(targets) / len(targets)
    score_sd = math.sqrt(sum((score - score_mean) ** 2 for score in scores) / len(scores))
    target_sd = math.sqrt(sum((target - target_mean) ** 2 for target in targets) / len(targets))
    return {"item_count": len(rows), "item_weighted_mae": sum(abs(error) for error in errors) / len(errors), "mean_signed_error": sum(errors) / len(errors), "score_sd": score_sd, "human_target_sd": target_sd, "score_to_target_sd_ratio": None if target_sd == 0 else score_sd / target_sd, "spearman_midrank": _pearson(_rank(scores), _rank(targets)), "human_nontied_pair_count": eligible, "correct_pair_count": correct, "reversed_pair_count": reversed_pairs, "model_tied_pair_count": model_tied, "pair_accuracy": correct / eligible, "half_credit_tie_concordance": (correct + model_tied / 2) / eligible}


def _validate(endpoint: str, report: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if report.get("endpoint") != endpoint or report.get("authority", {}).get("endpoint_pooling") != "forbidden":
        raise ValueError("report is not the required endpoint-separated receipt projection")
    cells = report.get("cells")
    if not isinstance(cells, list) or len(cells) != 88:
        raise ValueError("report is not the frozen 88-cell TRAIN44 projection")
    by_candidate: dict[str, list[dict[str, Any]]] = {CHILD20: [], DESCENDANT: []}
    identifiers: set[str] = set()
    for cell in cells:
        if not isinstance(cell, Mapping) or not isinstance(cell.get("cell_id"), str) or cell["cell_id"] in identifiers:
            raise ValueError("ambiguous receipt cell")
        identifiers.add(cell["cell_id"])
        candidate = cell.get("candidate_id")
        if candidate not in by_candidate or cell.get("partition") != "train" or not isinstance(cell.get("item_id"), str) or not isinstance(cell.get("prompt_group_id"), str):
            raise ValueError("non-TRAIN or non-paired receipt cell")
        scores, target = cell.get("scores"), cell.get("target")
        if not isinstance(scores, Mapping) or not isinstance(target, Mapping) or set(scores) != set(DIMS) or set(target) != set(DIMS):
            raise ValueError("receipt lacks raw six-dimension scores or targets")
        for dimension in DIMS:
            score, human = _number(scores[dimension], "score"), _number(target[dimension], "target")
            if not 0 <= score <= 5 or not 0 <= human <= 5:
                raise ValueError("receipt score or target is out of range")
        by_candidate[candidate].append(dict(cell))
    for candidate, rows in by_candidate.items():
        items = {row["item_id"] for row in rows}; groups = {row["prompt_group_id"] for row in rows}
        if len(rows) != 44 or len(items) != 44 or len(groups) != 22:
            raise ValueError(f"{candidate} is not the frozen TRAIN44/22 projection")
    child = {row["item_id"]: row for row in by_candidate[CHILD20]}
    descendant = {row["item_id"]: row for row in by_candidate[DESCENDANT]}
    if set(child) != set(descendant):
        raise ValueError("candidate receipt items are not paired")
    for item_id, row in child.items():
        other = descendant[item_id]
        if row["prompt_group_id"] != other["prompt_group_id"] or row["target"] != other["target"]:
            raise ValueError("candidate receipt source binding drifted")
    return {candidate: sorted(rows, key=lambda row: row["item_id"]) for candidate, rows in by_candidate.items()}


def diagnose(*, grok_report: Mapping[str, Any], sol_report: Mapping[str, Any]) -> dict[str, Any]:
    reports = {"grok_primary": _validate("grok_primary", grok_report), "sol_later": _validate("sol_later", sol_report)}
    endpoints: dict[str, Any] = {}
    for endpoint, rows_by_candidate in reports.items():
        metrics = {candidate: {dimension: _dimension(rows, dimension) for dimension in DIMS} for candidate, rows in rows_by_candidate.items()}
        change = {dimension: {name: metrics[DESCENDANT][dimension][name] - metrics[CHILD20][dimension][name] for name in ("item_weighted_mae", "mean_signed_error", "score_to_target_sd_ratio", "pair_accuracy", "half_credit_tie_concordance") if metrics[DESCENDANT][dimension][name] is not None and metrics[CHILD20][dimension][name] is not None} | {"spearman_midrank": None if metrics[DESCENDANT][dimension]["spearman_midrank"] is None or metrics[CHILD20][dimension]["spearman_midrank"] is None else metrics[DESCENDANT][dimension]["spearman_midrank"] - metrics[CHILD20][dimension]["spearman_midrank"], "correct_pair_count": metrics[DESCENDANT][dimension]["correct_pair_count"] - metrics[CHILD20][dimension]["correct_pair_count"], "reversed_pair_count": metrics[DESCENDANT][dimension]["reversed_pair_count"] - metrics[CHILD20][dimension]["reversed_pair_count"], "model_tied_pair_count": metrics[DESCENDANT][dimension]["model_tied_pair_count"] - metrics[CHILD20][dimension]["model_tied_pair_count"]} for dimension in DIMS}
        endpoints[endpoint] = {"metrics": metrics, "descendant_minus_child20": change}
    return {"format_version": 1, "kind": "frozen_v14_train44_endpoint_diagnostic", "definitions": {"mae": "mean absolute score-target error across 44 items", "signed_error": "mean score-target across 44 items", "spearman": "Pearson correlation of average-tie ranks", "pairwise": "unordered pairs with non-equal human targets; model ties are reported separately and receive half credit only in half_credit_tie_concordance"}, "endpoints": endpoints}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grok-root", type=Path, required=True); parser.add_argument("--grok-acknowledgement-sha256", required=True)
    parser.add_argument("--sol-root", type=Path, required=True); parser.add_argument("--sol-acknowledgement-sha256", required=True)
    parser.add_argument("--split-manifest", type=Path, required=True); parser.add_argument("--hanna-csv", type=Path, required=True); parser.add_argument("--successor-contract", type=Path, required=True); parser.add_argument("--recovered-descendant", type=Path, required=True)
    args = parser.parse_args(argv)
    print(canonical(diagnose(**{f"{key}_report": value for key, value in receipt_reports(grok_root=args.grok_root, grok_acknowledgement_sha256=args.grok_acknowledgement_sha256, sol_root=args.sol_root, sol_acknowledgement_sha256=args.sol_acknowledgement_sha256, split_manifest=args.split_manifest, hanna_csv=args.hanna_csv, successor_contract=args.successor_contract, recovered_descendant=args.recovered_descendant).items()})).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
