"""Optional development-only Optuna 4.9 GridSampler replay."""
from __future__ import annotations

from collections.abc import Mapping


def grid_replay(candidate_scores: Mapping[str, float], *, seed: int = 20260830) -> list[dict[str, float | str]]:
    import optuna
    if optuna.__version__ != "4.9.0":
        raise ValueError("HANNA shrinkage development replay requires Optuna 4.9.0")
    candidates = sorted(candidate_scores)
    if not candidates:
        raise ValueError("HANNA shrinkage Optuna grid is empty")
    sampler = optuna.samplers.GridSampler({"candidate_id": candidates}, seed=seed)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(lambda trial: float(candidate_scores[trial.suggest_categorical("candidate_id", candidates)]), n_trials=len(candidates))
    return sorted(({"candidate_id": trial.params["candidate_id"], "value": float(trial.value)} for trial in study.trials), key=lambda row: str(row["candidate_id"]))
