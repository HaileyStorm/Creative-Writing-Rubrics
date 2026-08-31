"""Optional Optuna 4.9.0 GridSampler replay; never imported by runtime modules."""
from collections.abc import Mapping


def grid_replay(candidate_scores: Mapping[str,float], *, seed:int=20260830):
    import optuna
    if optuna.__version__ != "4.9.0": raise ValueError("mixed evaluator requires Optuna 4.9.0")
    candidates=sorted(candidate_scores)
    if not candidates: raise ValueError("mixed evaluator Optuna grid is empty")
    study=optuna.create_study(direction="minimize",sampler=optuna.samplers.GridSampler({"candidate_id":candidates},seed=seed))
    study.optimize(lambda trial:float(candidate_scores[trial.suggest_categorical("candidate_id",candidates)]),n_trials=len(candidates))
    return sorted(({"candidate_id":x.params["candidate_id"],"value":float(x.value)} for x in study.trials),key=lambda x:x["candidate_id"])
