from __future__ import annotations

"""Development-only Optuna/DSPy view over the pinned Grok result analyzer."""

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-development-optimizer-v1"
ANALYZER_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v2-v3-exec"
ANALYZER = REPO / "evaluation-results" / ANALYZER_ID / "verify.py"
ANALYZER_CONTRACT = ANALYZER.parent / "study-contract.json"
ANALYZER_SHA256 = "a080cfe32f44e9cca4536445fddaca9c0c79cad724d6a6365dadbeeecdc39b86"
ANALYZER_CONTRACT_SHA256 = "abf2346599fd1221a2d58ce3b8ce80a0ae4c75c9b12cce132ef32e8eb147ca05"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
CANDIDATES = (PARENT, "broader-nextwave-15-construct_framing-speaker-attribution", "broader-nextwave-16-scope_materiality-temporal-causality", "broader-nextwave-17-scope_materiality-sustained-stakes", "broader-nextwave-18-construct_framing-referent-resolution")
SEED = 202608313
WORST_GROUP_WEIGHTS = (0.0, 0.15, 0.30)
STABILITY_WEIGHTS = (0.0, 0.10)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _ancestry(path: Path, directory: bool) -> tuple[tuple[str, int, int, int, int, int | None], ...]:
    target = Path(os.path.abspath(path)); result = []
    for index, current in enumerate((target, *target.parents)):
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("input ancestry contains a reparse point")
        expected = directory if index == 0 else True
        if stat.S_ISDIR(info.st_mode) != expected:
            raise ValueError("input path type drifted")
        result.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_mtime_ns, None if expected else info.st_size))
    return tuple(result)


@dataclass(frozen=True)
class Admitted:
    path: Path
    directory: bool
    ancestry: tuple[tuple[str, int, int, int, int, int | None], ...]
    raw: bytes | None


def _admit(path: Path, *, directory: bool) -> Admitted:
    path = Path(os.path.abspath(path)); before = _ancestry(path, directory)
    if directory:
        return Admitted(path, True, before, None)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    final = _ancestry(path, False); identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != final or before[0][1:4] != identity[:3] or before[0][-1] != identity[-1] or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("input changed during admission")
    return Admitted(path, False, before, raw)


def _verify(value: Admitted) -> None:
    if _ancestry(value.path, value.directory) != value.ancestry:
        raise ValueError("admitted input changed between analyzer and optimizer phases")
    if not value.directory and _admit(value.path, directory=False).raw != value.raw:
        raise ValueError("admitted input bytes changed between analyzer and optimizer phases")


def _strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value = {}
        for key, child in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = child
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def load_result_analyzer() -> ModuleType:
    source, contract = _admit(ANALYZER, directory=False), _admit(ANALYZER_CONTRACT, directory=False)
    if sha256(source.raw or b"") != ANALYZER_SHA256 or sha256(contract.raw or b"") != ANALYZER_CONTRACT_SHA256:
        raise ValueError("pinned lower-step result analyzer drifted")
    if _strict(contract.raw or b"", "result analyzer contract").get("study_id") != ANALYZER_ID:
        raise ValueError("result analyzer contract identity drifted")
    module = ModuleType("_desc13_lower_step_result_analyzer"); module.__file__ = str(ANALYZER); module.__package__ = ""; sys.modules[module.__name__] = module
    try:
        exec(compile(source.raw or b"", str(ANALYZER), "exec"), module.__dict__)  # noqa: S102 -- exact admitted immutable bytes
    finally:
        sys.modules.pop(module.__name__, None)
    _verify(source); _verify(contract)
    if module.STUDY_ID != ANALYZER_ID:
        raise ValueError("result analyzer identity drifted")
    return module


def _admit_inputs(**paths: Path) -> dict[str, Admitted]:
    roots = {"candidate_freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "output_root"}
    return {name: _admit(Path(path), directory=name in roots) for name, path in paths.items()}


def _projection(analyzer: ModuleType, sources: Mapping[str, Admitted]) -> dict[str, Any]:
    value = analyzer.replay(**{name: source.path for name, source in sources.items()})
    if not isinstance(value, Mapping):
        raise TypeError("result analyzer did not return a projection")
    return dict(value)


def _metrics(projection: Mapping[str, Any]) -> list[dict[str, Any]]:
    if projection.get("study_id") != ANALYZER_ID or projection.get("kind") != "descriptive_descendant13_lower_step_grok_development_equal_group_mae":
        raise ValueError("foreign result-analyzer projection")
    if projection.get("authority") != {"selection": "grok_development_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}:
        raise ValueError("projection authority drifted")
    source = projection.get("source_execution")
    required_source = {"candidate_manifest_sha256", "development_schedule_sha256", "executor_commit", "executor_sha256", "collector_sha256"}
    if not isinstance(source, Mapping) or set(source) != required_source or source.get("candidate_manifest_sha256") != "0487398345b28388fb6e35d879e5ea6f771f65802488e3fc33cf0426b530cecd":
        raise ValueError("projection lacks exact execution/freeze commitments")
    rows = projection.get("metrics")
    if not isinstance(rows, list) or len(rows) != 5:
        raise ValueError("projection candidate geometry drifted")
    output = []; candidates: set[str] = set(); common_groups: set[str] | None = None
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae"}:
            raise ValueError("projection metric shape drifted")
        candidate, groups = row.get("candidate_id"), row.get("group_mae")
        if not isinstance(candidate, str) or candidate not in CANDIDATES or candidate in candidates or row.get("cells") != 7 or not isinstance(groups, Mapping) or len(groups) != 7:
            raise ValueError("projection candidate or group identity drifted")
        group_ids = set(groups)
        if common_groups is None: common_groups = group_ids
        if group_ids != common_groups: raise ValueError("foreign or mixed development groups")
        values = []
        for item in groups.values():
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item): raise ValueError("projection group MAE is invalid")
            values.append(float(item))
        if isinstance(row.get("equal_group_mae"), bool) or not isinstance(row.get("equal_group_mae"), (int, float)) or not math.isclose(float(row["equal_group_mae"]), sum(values) / 7, rel_tol=0, abs_tol=1e-15):
            raise ValueError("projection equal-group MAE does not recompute")
        output.append({"candidate_id": candidate, "equal_group_mae": float(row["equal_group_mae"]), "group_mae": dict(sorted((str(key), float(value)) for key, value in groups.items()))}); candidates.add(candidate)
    if candidates != set(CANDIDATES) or common_groups is None: raise ValueError("incomplete candidate projection")
    return sorted(output, key=lambda row: row["candidate_id"])


def objective(metric: Mapping[str, Any], worst_weight: float, stability_weight: float) -> float:
    values = tuple(float(value) for value in metric["group_mae"].values()); mean = float(metric["equal_group_mae"])
    return mean + worst_weight * (max(values) - mean) + stability_weight * sum(abs(value - mean) for value in values) / len(values)


def run_optuna(metrics: list[Mapping[str, Any]]) -> dict[str, Any]:
    import optuna
    ids = [str(row["candidate_id"]) for row in metrics]; by_id = {str(row["candidate_id"]): row for row in metrics}
    grid = {"candidate_id": ids, "worst_group_weight": list(WORST_GROUP_WEIGHTS), "stability_weight": list(STABILITY_WEIGHTS)}
    optuna.logging.set_verbosity(optuna.logging.WARNING); study = optuna.create_study(direction="minimize", sampler=optuna.samplers.GridSampler(grid, seed=SEED))
    def evaluate(trial: Any) -> float:
        candidate = trial.suggest_categorical("candidate_id", ids); worst = float(trial.suggest_categorical("worst_group_weight", list(WORST_GROUP_WEIGHTS))); stability = float(trial.suggest_categorical("stability_weight", list(STABILITY_WEIGHTS)))
        return objective(by_id[candidate], worst, stability)
    expected = len(ids) * len(WORST_GROUP_WEIGHTS) * len(STABILITY_WEIGHTS); study.optimize(evaluate, n_trials=expected)
    if len(study.trials) != expected or any(trial.state.name != "COMPLETE" for trial in study.trials): raise ValueError("Optuna grid did not complete")
    grouped: dict[tuple[float, float], list[tuple[str, float]]] = defaultdict(list)
    for trial in study.trials: grouped[(float(trial.params["worst_group_weight"]), float(trial.params["stability_weight"]))].append((str(trial.params["candidate_id"]), float(trial.value)))
    settings = []; counts: dict[str, int] = defaultdict(int)
    for (worst, stability), values in sorted(grouped.items()):
        ranked = sorted(values, key=lambda pair: (pair[1], pair[0])); settings.append({"worst_group_weight": worst, "stability_weight": stability, "winner": ranked[0][0], "margin": ranked[1][1] - ranked[0][1]}); counts[ranked[0][0]] += 1
    highest_count = max(counts.values())
    tied = sorted(candidate for candidate, count in counts.items() if count == highest_count)
    raw_mae_winner = min(metrics, key=lambda row: (row["equal_group_mae"], row["candidate_id"]))["candidate_id"]
    return {"library": f"optuna@{optuna.__version__}", "sampler": "GridSampler", "seed": SEED, "completed_trials": expected, "settings": settings, "winner_counts": dict(sorted(counts.items())), "raw_mae_winner": raw_mae_winner, "robustness": {"status": "unique_optimizer_winner" if len(tied) == 1 else "no_unique_optimizer_winner", "winning_setting_count": highest_count, "tied_candidates": tied, "deterministic_serialization_order": tied, "note": "Ordering is serialization-only and does not select a candidate when settings split."}, "candidate_metrics": {row["candidate_id"]: row for row in metrics}}


def build_dspy_training_view(metrics: list[Mapping[str, Any]], optimizer: Mapping[str, Any]) -> dict[str, Any]:
    import dspy
    class ReplayedEvidence(dspy.Signature):
        candidate_id: str = dspy.InputField(); group_mae_json: str = dspy.InputField(); equal_group_mae: float = dspy.OutputField()
    examples = [dspy.Example(candidate_id=row["candidate_id"], group_mae_json=canonical(row["group_mae"]).decode(), equal_group_mae=row["equal_group_mae"]).with_inputs("candidate_id", "group_mae_json") for row in metrics]
    return {"library": f"dspy@{dspy.__version__}", "signature": ReplayedEvidence.__name__, "evidence_examples": len(examples), "evidence_chain_sha256": sha256([example.toDict() for example in examples]), "raw_mae_best_candidate": optimizer["raw_mae_winner"], "robustness_status": optimizer["robustness"]["status"], "lm_calls": 0, "predict_calls": 0, "proposal_generated": False}


def claim_for(optimizer: Mapping[str, Any]) -> str:
    status = optimizer["robustness"]["status"]
    if status == "no_unique_optimizer_winner":
        interpretation = "the robustness grid has no unique optimizer winner or selection"
    elif status == "unique_optimizer_winner":
        interpretation = "the robustness grid has one development-only ordering, not a promotion or cross-endpoint selection"
    else:
        raise ValueError("unknown robustness status")
    return f"The sole evidence input is the pinned result-analyzer replay projection. {optimizer['raw_mae_winner']} is the raw equal-group-MAE leader; {interpretation}. Optuna and DSPy add no provider, Sol, confirmation, pooled, general, promotion, or runtime authority."


def analyze(*, candidate_freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path) -> dict[str, Any]:
    sources = _admit_inputs(candidate_freeze_root=candidate_freeze_root, development_freeze_root=development_freeze_root, normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, output_root=output_root, collector_path=collector_path); projection = _projection(load_result_analyzer(), sources)
    for source in sources.values(): _verify(source)
    metrics = _metrics(projection); optimizer = run_optuna(metrics); dspy_view = build_dspy_training_view(metrics, optimizer)
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "development_only_desc13_lower_step_grok_optimizer", "source": {"result_analyzer_sha256": ANALYZER_SHA256, "result_analyzer_contract_sha256": ANALYZER_CONTRACT_SHA256, "projection_sha256": sha256(projection), "collector_sha256": projection["source_execution"]["collector_sha256"]}, "geometry": {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}, "optimizer": optimizer, "dspy_training_view": dspy_view, "authority": {"selection": "development_only_" + optimizer["robustness"]["status"] + "_pending_sol", "promotion": "none", "runtime": "none", "sol_validation": "required_before_any_cross_endpoint_claim", "confirmation": {"status": "unopened", "cells": 0}}, "claim": claim_for(optimizer)}
    result["result_sha256"] = sha256(result); return result


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("development optimizer result output must be fresh")
    _ancestry(target.parent, True)
    with target.open("xb") as handle:
        handle.write(canonical(dict(result)))
        handle.flush()
        os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    names = ("candidate-freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor-path", "hanna-csv-path", "output-root", "collector-path")
    for name in names: parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv); values = {name.replace("-", "_"): getattr(args, name.replace("-", "_")) for name in names}
    result = analyze(**values)
    if args.result_output is not None: write_result(args.result_output, result)
    print(canonical(result).decode(), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
