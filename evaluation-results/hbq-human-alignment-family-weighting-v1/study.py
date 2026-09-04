"""Provider-free TRAIN-only full-HBQ family-weighting diagnostic."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-family-weighting-v1"
CONTRACT = HERE / "experiment-contract.json"
CONTRACT_SHA256 = "db1a470241e2f5e2c53788f1d63db9f8c807938513151c319e65604844c47884"
ADAPTER = HERE / "source_adapter.py"
ADAPTER_SHA256 = "98539aa645e4d2012416f0d5fd84c7184191ffeffea62473dd8f9db21ab24865"
FAMILIES = ("core", "craft", "form")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _adapter() -> Any:
    if sha256(ADAPTER.read_bytes()) != ADAPTER_SHA256:
        raise ValueError("pinned source adapter drifted")
    spec=importlib.util.spec_from_file_location("_family_weighting_adapter",ADAPTER)
    if spec is None or spec.loader is None: raise ValueError("source adapter cannot load")
    adapter=importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
    return adapter


def contract() -> dict[str, Any]:
    raw=CONTRACT.read_bytes()
    if sha256(raw)!=CONTRACT_SHA256: raise ValueError("family-weighting contract pin drifted")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or canonical(value) != raw or value.get("study_id") != STUDY_ID:
        raise ValueError("family-weighting contract drifted")
    return value


def _rank(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda pair: pair[1]); result = [0.0] * len(values); start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]: end += 1
        for index, _ in ordered[start:end]: result[index] = (start + 1 + end) / 2
        start = end
    return result


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2: raise ValueError("paired ranks required")
    a, b = _rank(left), _rank(right); ma, mb = sum(a) / len(a), sum(b) / len(b)
    da, db = sum((x - ma) ** 2 for x in a), sum((x - mb) ** 2 for x in b)
    return None if da == 0 or db == 0 else sum((x - ma) * (y - mb) for x, y in zip(a, b, strict=True)) / math.sqrt(da * db)


def build_records(*, split_manifest: Path, execution_freeze: Path, fresh88_contract: Path, raw_runs_root: Path, hanna_csv: Path) -> list[dict[str, Any]]:
    adapter=_adapter()
    records=adapter.build_records(split_manifest=Path(split_manifest),execution_freeze=Path(execution_freeze),fresh88_contract=Path(fresh88_contract),raw_runs_root=Path(raw_runs_root),hanna_csv=Path(hanna_csv))
    if adapter.verify_all_one(records).get("state")!="all_one_parity_pass": raise ValueError("adapter all-one parity failed")
    return records


def verify_all_one(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(records) != 48 or len({row.get("item_id") for row in records}) != 48 or len({row.get("prompt_group_id") for row in records}) != 24:
        raise ValueError("exact TRAIN48/24 records required")
    mismatches = [str(row.get("item_id")) for row in records if row.get("all_one_final_score") != row.get("original_final_score")]
    return {"state": "all_one_parity_pass" if not mismatches else "all_one_parity_failed", "mismatch_count": len(mismatches), "mismatched_item_ids": mismatches}


def _group_objective(records: Sequence[Mapping[str, Any]], scores: Mapping[str, float]) -> float | None:
    values=[]
    for group in sorted({str(row["prompt_group_id"]) for row in records}):
        rows=[row for row in records if row["prompt_group_id"]==group]
        if len(rows)<2: continue
        rho=_spearman([float(scores[str(row["item_id"])]) for row in rows],[float(row["human_overall_proxy"]) for row in rows])
        if rho is not None: values.append(rho)
    return None if not values else sum(values)/len(values)


def _pooled_objective(records: Sequence[Mapping[str, Any]], scores: Mapping[str, float]) -> float | None:
    return _spearman([float(scores[str(row["item_id"])]) for row in records], [float(row["human_overall_proxy"]) for row in records])


def _metrics(records: Sequence[Mapping[str, Any]], scores: Mapping[str, float]) -> dict[str, Any]:
    predictions={str(row["item_id"]):1+4*float(scores[str(row["item_id"])] )/100 for row in records}
    target=[float(row["human_overall_proxy"]) for row in records]
    values=[predictions[str(row["item_id"])] for row in records]
    groups=sorted({str(row["prompt_group_id"]) for row in records})
    group_mae=[]
    for group in groups:
        rows=[row for row in records if row["prompt_group_id"]==group]
        group_mae.append(sum(abs(predictions[str(row["item_id"])]-float(row["human_overall_proxy"])) for row in rows)/len(rows))
    axes={}
    for axis in ("Relevance","Coherence","Empathy","Surprise","Engagement","Complexity"):
        axes[axis]={"spearman":_spearman(values,[float(row["human_dimension_means"][axis]) for row in records]),"mae":sum(abs(predictions[str(row["item_id"])]-float(row["human_dimension_means"][axis])) for row in records)/len(records)}
    return {"pooled_spearman":_spearman(values,target),"global_mae":sum(abs(a-b) for a,b in zip(values,target,strict=True))/len(values),"equal_group_mae":sum(group_mae)/len(group_mae),"six_axis_descriptive":axes}


def preflight(records: Sequence[Mapping[str, Any]], rescore: Any) -> dict[str, Any]:
    """Target-free family influence probe; `rescore` returns item-id -> 0..100 score."""
    baseline=dict(rescore({family:1.0 for family in FAMILIES}))
    probes={}
    active=[]
    for family in FAMILIES:
        changed=[]
        for multiplier in (.5,2.0):
            scores=dict(rescore({name:multiplier if name==family else 1.0 for name in FAMILIES}))
            changed.append(sum(scores[str(row["item_id"])]!=baseline[str(row["item_id"])] for row in records))
        probes[family]={"half_changed_item_count":changed[0],"double_changed_item_count":changed[1]}
        if any(changed): active.append(family)
    return {"all_one_scores":baseline,"family_influence":probes,"active_families":active,"state":"identifiable" if active else "all_families_nonidentifiable"}


def fit(records: Sequence[Mapping[str, Any]], rescore: Any) -> dict[str, Any]:
    gate=preflight(records,rescore)
    if gate["state"]!="identifiable": raise ValueError("all family multipliers are mathematically nonidentifiable")
    try:
        import optuna
    except ImportError as error:
        raise ValueError("Optuna 4.9.0 is required") from error
    if getattr(optuna,"__version__",None)!="4.9.0": raise ValueError("Optuna version drifted")
    groups=sorted({str(row["prompt_group_id"]) for row in records}); oof={}; folds=[]
    for fold,heldout in enumerate(groups):
        training=[row for row in records if row["prompt_group_id"]!=heldout]
        def objective(trial: Any, training: Sequence[Mapping[str, Any]] = training)->float:
            multipliers={family:(1.0 if family not in gate["active_families"] else trial.suggest_float(family,.5,2.0)) for family in FAMILIES}
            scores=dict(rescore(multipliers)); rho=_pooled_objective(training,scores)
            penalty=.02*sum(math.log2(multipliers[family])**2 for family in FAMILIES)/3
            return (1.0-(rho if rho is not None else -1.0))+penalty
        sampler=optuna.samplers.TPESampler(seed=20260904+fold); study=optuna.create_study(direction="minimize",sampler=sampler)
        study.enqueue_trial({family:1.0 for family in gate["active_families"]}); study.optimize(objective,n_trials=128,n_jobs=1)
        best={family:(1.0 if family not in gate["active_families"] else float(study.best_params[family])) for family in FAMILIES}
        scores=dict(rescore(best)); oof.update({str(row["item_id"]):float(scores[str(row["item_id"])]) for row in records if row["prompt_group_id"]==heldout})
        folds.append({"heldout_group":heldout,"heldout_item_ids":[str(row["item_id"]) for row in records if row["prompt_group_id"]==heldout],"multipliers":best,"best_objective":float(study.best_value),"trials":128,"seed":20260904+fold})
    return {"preflight":gate,"oof_scores":oof,"folds":folds,"pooled_oof_spearman":_pooled_objective(records,oof),"within_group_defined_context":_group_objective(records,oof)}


def _run_records(*, records: Sequence[Mapping[str, Any]], allow_fit: bool, rescore: Any | None) -> dict[str, Any]:
    parity = verify_all_one(records)
    if parity["state"] != "all_one_parity_pass": raise ValueError("all-one parity must pass before fitting")
    if allow_fit is not True: return {"study_id": STUDY_ID, "state": "non_empirical_synthetic_parity_verified_fit_not_requested", "parity": parity}
    if rescore is None: raise ValueError("exact canonical rescore callback is required")
    fitted=fit(records,rescore)
    all_one=dict(rescore({family:1.0 for family in FAMILIES}))
    fixed={str(row["item_id"]):50.0 for row in records}
    prior={}
    for fold in fitted["folds"]:
        training=[row for row in records if row["prompt_group_id"]!=fold["heldout_group"]]
        means=[sum(float(row["human_overall_proxy"]) for row in training if row["prompt_group_id"]==group)/sum(row["prompt_group_id"]==group for row in training) for group in sorted({row["prompt_group_id"] for row in training})]
        raw=(sum(means)/len(means)-1)*25
        prior.update({item_id:raw for item_id in fold["heldout_item_ids"]})
    return {"study_id":STUDY_ID,"state":"non_empirical_synthetic_fit_complete","parity":parity,"fit":fitted,"metrics":{"oof_fitted":_metrics(records,fitted["oof_scores"]),"all_one_pinned_historical_tree":_metrics(records,all_one),"fixed_three":_metrics(records,fixed),"fold_training_only_human_prior":_metrics(records,prior)},"authority":contract()["authority"]}


def _records_commitment(records: Sequence[Mapping[str, Any]]) -> str:
    keys=("item_id","prompt_group_id","human_overall_proxy","human_dimension_means","original_final_score","all_one_final_score")
    rows=[]
    for row in sorted(records,key=lambda row:str(row["item_id"])):
        commitments=row.get("commitments")
        if not isinstance(commitments,Mapping) or not commitments.get("native"):
            raise ValueError("record lacks persisted native evidence commitment")
        if any(row.get(key) is None for key in keys): raise ValueError("record commitment fields are incomplete")
        rows.append({**{key:row[key] for key in keys},"commitments":dict(commitments)})
    return sha256(rows)


def run_from_sources(*, split_manifest: Path, execution_freeze: Path, fresh88_contract: Path, raw_runs_root: Path, hanna_csv: Path, output_root: Path, allow_fit: bool) -> dict[str, Any]:
    """Authoritative empirical entrypoint; records and scorer are never caller supplied."""
    paths={"split_manifest":Path(split_manifest),"execution_freeze":Path(execution_freeze),"fresh88_contract":Path(fresh88_contract),"hanna_csv":Path(hanna_csv)}
    adapter=_adapter()
    records=adapter.build_records(**paths,raw_runs_root=Path(raw_runs_root))
    if adapter.verify_all_one(records).get("state")!="all_one_parity_pass": raise ValueError("adapter all-one parity failed")
    bindings={name:sha256(path.read_bytes()) for name,path in paths.items()}
    bindings.update({"adapter_sha256":ADAPTER_SHA256,"study_sha256":sha256(Path(__file__).read_bytes()),"contract_sha256":sha256(CONTRACT.read_bytes())})
    receipt={"study_id":STUDY_ID,"state":"source_bound_parity_verified_fit_not_requested","parity":verify_all_one(records),"source_bindings":bindings,"records_commitment_sha256":_records_commitment(records)}
    if allow_fit is not True: return receipt
    if Path(output_root).exists(): raise ValueError("fresh output root required")
    value=_run_records(records=records,allow_fit=True,rescore=lambda multipliers:adapter.rescore(records,multipliers))
    value={**value,"state":"development_fit_complete","source_bindings":bindings,"records_commitment_sha256":_records_commitment(records)}
    root=Path(output_root); root.mkdir(parents=True); (root/"result.json").write_bytes(canonical(value)); return value
