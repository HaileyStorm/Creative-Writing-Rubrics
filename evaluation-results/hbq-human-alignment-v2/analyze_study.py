#!/usr/bin/env python3
"""Verify external HANNA runs and publish prose-free phase-specific results."""
from __future__ import annotations

import argparse, gzip, hashlib, json, random, statistics
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import _json_bytes, _question_payload
from study import RATING_DIMENSIONS, alpha_nominal, canonical_json, fetch_or_verify_dataset, load_hanna_items, mapping_sets, pearson, privacy_forbidden_strings, rank, sha256_path, spearman, validate_external_inputs, validate_frozen_contract, write_json


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value, encoding="utf-8", newline="\n")
def read_json(path: Path) -> dict[str, Any]: return json.loads(path.read_text(encoding="utf-8"))
def read_verdicts(path: Path) -> list[dict[str, Any]]: return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
def verdict_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes: return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True)+"\n" for row in rows).encode()

def typed_evidence_metrics(rows: Sequence[Mapping[str, Any]], source: str, prompt: str) -> dict[str, Any]:
    result = Counter(total=0, typed_schema_conformant=0, exact_quote=0, exact_quote_grounded=0, summary=0, untyped=0, empty=0)
    for verdict in rows:
        for item in verdict.get("evidence", []):
            result["total"] += 1
            exact, summary, quote = item.get("exact_quote"), item.get("summary"), item.get("quote")
            if isinstance(exact, str) and exact.strip() and summary is None and quote is None and set(item) == {"reference", "exact_quote"} and isinstance(item.get("reference"), str) and item["reference"].strip():
                result["typed_schema_conformant"] += 1; result["exact_quote"] += 1; result["exact_quote_grounded"] += int(exact in source or exact in prompt)
            elif isinstance(summary, str) and summary.strip() and exact is None and quote is None and set(item) == {"reference", "summary"} and isinstance(item.get("reference"), str) and item["reference"].strip():
                result["typed_schema_conformant"] += 1; result["summary"] += 1
            elif not any(isinstance(value, str) and value.strip() for value in (exact, summary, quote)):
                result["empty"] += 1
            else: result["untyped"] += 1
    total = result["total"]
    return {"total": total, "typed_schema_conformant": result["typed_schema_conformant"], "typed_schema_conformance_rate": result["typed_schema_conformant"]/total if total else None, "exact_quote": result["exact_quote"], "exact_quote_grounded": result["exact_quote_grounded"], "exact_quote_grounded_rate": result["exact_quote_grounded"]/result["exact_quote"] if result["exact_quote"] else None, "summary": result["summary"], "summary_prevalence": result["summary"]/total if total else None, "untyped": result["untyped"], "empty": result["empty"]}

def verify_run(work: Path, frozen: Mapping[str, Any], phase: str, row: Mapping[str, Any], repetition: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    folder = work / "runs" / phase / row["item_id"] / f"run-{repetition:02d}"
    manifest, score, rows = read_json(folder/"run.json"), read_json(folder/"score.json"), read_verdicts(folder/"verdicts.jsonl")
    configuration = manifest.get("configuration", {})
    inputs = row["external_input"]
    if manifest.get("format_version") != 1 or not manifest.get("config_sha256") or not isinstance(score.get("status"), str): raise ValueError(f"Malformed run manifest/status for {row['item_id']}")
    if manifest.get("config_sha256") != hashlib.sha256(_json_bytes(configuration)).hexdigest(): raise ValueError(f"Config hash mismatch for {row['item_id']}")
    if configuration.get("artifact", {}).get("sha256") != inputs["source.md"]["sha256"] or configuration.get("contexts", [{}])[0].get("sha256") != inputs["prompt.md"]["sha256"] or configuration.get("task_contract", {}).get("sha256") != inputs["task-contract.json"]["sha256"]: raise ValueError(f"Run input provenance mismatch for {row['item_id']}")
    task_contract=read_json(work/"inputs"/("development" if phase in {"development","repeatability"} else "confirmatory")/row["item_id"] / "task-contract.json")
    modules=load_modules(registry_path()); bundle=resolve_bundle(load_bundles(bundles_path()), frozen["runner"]["bundle_id"]); compiled=compile_bundle(modules,bundle,task_contract=task_contract)
    records=sorted(compiled_questions(compiled),key=lambda item:{"hard_gate":0,"domain":1,"penalty":2,"supplemental":3}.get(str(item.get("role")),99)); expected=[str(item["question"]["id"]) for item in records]
    if expected != frozen["question_ids"] or configuration.get("questions_sha256") != hashlib.sha256(_json_bytes(_question_payload(records))).hexdigest() or configuration.get("compiled_bundle_sha256") != hashlib.sha256(_json_bytes(compiled)).hexdigest(): raise ValueError(f"Compiled bundle/hash mismatch for {row['item_id']}")
    def compact(value): return {key:value.get(key) for key in ("name","bytes","sha256")} if isinstance(value,dict) else None
    if [compact(item) for item in configuration.get("prompts",[])] != [frozen["package_files"]["BINARY_EVALUATION_PROMPT.md"]] or compact(configuration.get("response_schema")) != frozen["package_files"]["hbq_judge_response.schema.json"]: raise ValueError(f"Prompt/schema fingerprint mismatch for {row['item_id']}")
    if configuration.get("question_ids") != expected or [item.get("question_id") for item in rows] != expected: raise ValueError(f"Question order mismatch for {row['item_id']}")
    if configuration.get("provider") != frozen["provider"]["provider"] or configuration.get("model") != frozen["provider"]["model"] or configuration.get("reasoning") != frozen["provider"]["reasoning"] or configuration.get("strict_ai") is not False or configuration.get("batch_size") != frozen["runner"]["batch_size"]: raise ValueError(f"Run settings mismatch for {row['item_id']}")
    checkpoints = sorted((folder/"responses").glob("batch-*.json")); previous=None; accumulated=[]
    if len(checkpoints) != 1: raise ValueError(f"Expected one full-bundle checkpoint for {row['item_id']}")
    for number, checkpoint in enumerate(checkpoints, 1):
        record=read_json(checkpoint); prompt=checkpoint.with_suffix(".prompt.txt.gz")
        if record.get("format_version") != 2 or record.get("batch") != number or record.get("previous_checkpoint_sha256") != previous or record.get("question_ids") != expected or not prompt.is_file(): raise ValueError(f"Checkpoint chain mismatch for {row['item_id']}")
        if record.get("prompt_sha256") != hashlib.sha256(gzip.decompress(prompt.read_bytes())).hexdigest(): raise ValueError(f"Checkpoint prompt mismatch for {row['item_id']}")
        accumulated.extend(record.get("normalized_verdicts", []))
        if record.get("verdicts_sha256") != hashlib.sha256(verdict_bytes(accumulated)).hexdigest(): raise ValueError(f"Checkpoint verdict hash mismatch for {row['item_id']}")
        reported=record.get("provider", {}).get("reported", {})
        if {"provider":reported.get("provider"),"model":reported.get("model"),"reasoning_effort":reported.get("reasoning_effort")} != {"provider":"openai","model":frozen["provider"]["model"],"reasoning_effort":frozen["provider"]["reasoning"]}: raise ValueError(f"Reported provider mismatch for {row['item_id']}")
        previous=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if accumulated != rows: raise ValueError(f"Checkpoint/verdicts mismatch for {row['item_id']}")
    recomputed=score_bundle(modules,bundle,rows,artifact_id=row["item_id"],task_contract=task_contract); recomputed["weight_profile"]=configuration.get("weight_profile")
    if recomputed != score: raise ValueError(f"Deterministic score mismatch for {row['item_id']}")
    return rows, score

def verify_phase_runs(work: Path, frozen: Mapping[str, Any], phase: str) -> None:
    source_rows = frozen["repeatability"]["items"] if phase == "repeatability" else frozen["partitions"][phase]
    for row in source_rows:
        repetitions = frozen["repeatability"]["repetitions"] if phase == "repeatability" else 1
        if phase == "repeatability":
            row = next(item for item in frozen["partitions"]["development"] if item["item_id"] == row["item_id"])
        run_ids=[]; session_ids=[]
        for number in range(1, repetitions+1):
            verify_run(work, frozen, phase, row, number)
            run_ids.append(read_json(work/"runs"/phase/row["item_id"]/f"run-{number:02d}"/"run.json")["run_id"])
            checkpoint=read_json(work/"runs"/phase/row["item_id"]/f"run-{number:02d}"/"responses"/"batch-0001.json")
            session=checkpoint.get("provider",{}).get("reported",{}).get("session_id")
            session_ids.append(session)
        if phase == "repeatability" and (len(set(run_ids)) != repetitions or any(not isinstance(item,str) or not item.strip() for item in session_ids) or len(set(session_ids)) != repetitions): raise ValueError(f"Repeatability requires five distinct nonblank Codex-reported session IDs for {row['item_id']}")

def derive_mapping(rows: Sequence[Mapping[str, Any]], mappings: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    labels={str(row.get("question_id")):str(row.get("verdict")) for row in rows}; output={}
    for dimension, ids in mappings.items():
        states=[labels.get(item,"CANNOT_ASSESS") for item in ids]; assessed=[state for state in states if state in {"YES","NO"}]
        output[dimension]={"score":sum(state=="YES" for state in assessed)/len(assessed) if assessed else None,"coverage":len(assessed)/len(ids),"unresolved":states.count("CANNOT_ASSESS"),"not_applicable":states.count("NOT_APPLICABLE"),"question_count":len(ids)}
    return output
def score_value(score: Mapping[str, Any]) -> float | None:
    value=score.get("final_score",{}).get("observed") if isinstance(score.get("final_score"),Mapping) else None; return float(value) if isinstance(value,(int,float)) else None
def record_for(item: Any, selection: Mapping[str, Any], rows: Sequence[Mapping[str, Any]], score: Mapping[str, Any], source: str, prompt: str, mappings: Mapping[str,Sequence[str]]) -> dict[str,Any]:
    return {"item_id":item.item_id,"story_id":item.story_id,"source_model":item.model,"quartile":selection["quartile"],"prompt_group_id":selection["prompt_group_id"],"story_sha256":item.story_sha256,"prompt_sha256":item.prompt_sha256,"human_ratings":{key:list(item.ratings[key]) for key in RATING_DIMENSIONS},"human_means":item.human_means,"human_overall":item.human_overall,"hbq_full_observed_score":score_value(score),"hbq_mapping":derive_mapping(rows,mappings),"evidence":typed_evidence_metrics(rows,source,prompt)}

def cluster_bootstrap(records: Sequence[Mapping[str,Any]], dimension: str, seed: int, draws: int=1000) -> dict[str,Any]:
    def statistic(rows):
        usable=[row for row in rows if row["hbq_mapping"][dimension]["score"] is not None]
        return spearman([float(row["hbq_mapping"][dimension]["score"]) for row in usable],[float(row["human_means"][dimension]) for row in usable])
    point=statistic(records); grouped=defaultdict(list)
    for row in records: grouped[row["prompt_group_id"]].append(row)
    generator=random.Random(seed); groups=sorted(grouped); values=[]
    for _ in range(draws):
        sampled=[item for _index in groups for item in grouped[groups[generator.randrange(len(groups))]]]; value=statistic(sampled)
        if value is not None: values.append(value)
    values.sort(); return {"estimate":point,"draws":draws,"effective_draws":len(values),"cluster":"prompt_group_id","ci_95_low":values[round(.025*(len(values)-1))] if values else None,"ci_95_high":values[round(.975*(len(values)-1))] if values else None}
def dimension_analysis(records, dimension, seed):
    usable=[row for row in records if row["hbq_mapping"][dimension]["score"] is not None]
    return {"item_count":len(usable),"spearman":cluster_bootstrap(records,dimension,seed),"pearson":pearson([float(row["hbq_mapping"][dimension]["score"]) for row in usable],[float(row["human_means"][dimension]) for row in usable]),"mean_coverage":statistics.fmean(row["hbq_mapping"][dimension]["coverage"] for row in usable) if usable else None,"unresolved":sum(row["hbq_mapping"][dimension]["unresolved"] for row in usable),"not_applicable":sum(row["hbq_mapping"][dimension]["not_applicable"] for row in usable)}
def macro_cluster_bootstrap(records, seed, draws=1000):
    groups=defaultdict(list)
    for row in records: groups[row["prompt_group_id"]].append(row)
    names=sorted(groups); generator=random.Random(seed)
    def value(rows):
        values=[]
        for dimension in RATING_DIMENSIONS:
            usable=[row for row in rows if row["hbq_mapping"][dimension]["score"] is not None]
            correlation=spearman([float(row["hbq_mapping"][dimension]["score"]) for row in usable],[float(row["human_means"][dimension]) for row in usable])
            if correlation is not None: values.append(correlation)
        return statistics.fmean(values) if values else None
    samples=[]
    for _ in range(draws):
        result=value([row for _group in names for row in groups[names[generator.randrange(len(names))]]])
        if result is not None: samples.append(result)
    samples.sort(); point=value(records)
    return {"estimate":point,"draws":draws,"effective_draws":len(samples),"cluster":"prompt_group_id","ci_95_low":samples[round(.025*(len(samples)-1))] if samples else None,"ci_95_high":samples[round(.975*(len(samples)-1))] if samples else None}
def source_model_strata(records):
    groups=defaultdict(list)
    for row in records: groups[row["source_model"]].append(row)
    return {model:{"item_count":len(rows),"dimensions":{dimension:spearman([float(row["hbq_mapping"][dimension]["score"]) for row in rows if row["hbq_mapping"][dimension]["score"] is not None],[float(row["human_means"][dimension]) for row in rows if row["hbq_mapping"][dimension]["score"] is not None]) for dimension in RATING_DIMENSIONS}} for model,rows in sorted(groups.items())}
def ordinal_agreement(items: Sequence[Any]) -> dict[str,Any]:
    return {dimension:{"statistic":"mean within-item ordinal concordance = 1 - mean pairwise absolute rating difference / 4","item_count":len(items),"value":statistics.fmean(1-abs(left-right)/4 for item in items for left,right in combinations(item.ratings[dimension],2))} for dimension in RATING_DIMENSIONS}

def repeatability_metrics(work: Path, frozen: Mapping[str,Any]) -> dict[str,Any]:
    all_leaves=[]; per_item=[]; evidence=[]
    for repeat in frozen["repeatability"]["items"]:
        row=next(item for item in frozen["partitions"]["development"] if item["item_id"]==repeat["item_id"]); source=(work/"inputs"/"development"/row["item_id"]/"source.md").read_text(encoding="utf-8"); prompt=(work/"inputs"/"development"/row["item_id"]/"prompt.md").read_text(encoding="utf-8"); runs=[]; scores=[]
        for number in range(1,frozen["repeatability"]["repetitions"]+1):
            verdicts,score=verify_run(work,frozen,"repeatability",row,number); runs.append(verdicts); value=score_value(score); scores.extend([] if value is None else [value]); evidence.append(typed_evidence_metrics(verdicts,source,prompt))
        columns=list(zip(*[[item["verdict"] for item in run] for run in runs])); all_leaves.extend(columns); per_item.append({"item_id":row["item_id"],"source_model":row["model"],"exact_all_five_leaf_agreement":statistics.fmean(len(set(column))==1 for column in columns),"score":{"values":scores,"standard_deviation":statistics.stdev(scores) if len(scores)>1 else 0.0,"range":max(scores)-min(scores) if scores else None}})
    keys=("total","typed_schema_conformant","exact_quote","exact_quote_grounded","summary","untyped","empty"); sums={key:sum(item[key] for item in evidence) for key in keys}; total=sums["total"]
    deviations=[item["score"]["standard_deviation"] for item in per_item]; ranges=[item["score"]["range"] for item in per_item if item["score"]["range"] is not None]
    if len(per_item) != 11: raise ValueError("Frozen repeatability summary must contain exactly 11 items")
    return {"item_count":11,"repetitions":frozen["repeatability"]["repetitions"],"per_item":per_item,"leaf_exact_all_five_agreement":statistics.fmean(item["exact_all_five_leaf_agreement"] for item in per_item),"nominal_krippendorff_alpha":alpha_nominal(all_leaves),"within_item_score_standard_deviation":{"mean":statistics.fmean(deviations),"maximum":max(deviations),"minimum":min(deviations)},"within_item_score_range":{"mean":statistics.fmean(ranges) if ranges else None,"maximum":max(ranges) if ranges else None},"evidence":{"total":total,"typed_schema_conformant":sums["typed_schema_conformant"],"typed_schema_conformance_rate":sums["typed_schema_conformant"]/total if total else None,"exact_quote":sums["exact_quote"],"exact_quote_grounded":sums["exact_quote_grounded"],"exact_quote_grounded_rate":sums["exact_quote_grounded"]/sums["exact_quote"] if sums["exact_quote"] else None,"summary":sums["summary"],"summary_prevalence":sums["summary"]/total if total else None,"untyped":sums["untyped"],"empty":sums["empty"]}}

def svg(title, description, body): return f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="500" viewBox="0 0 960 500" role="img" aria-labelledby="title desc"><title id="title">{title}</title><desc id="desc">{description}</desc><style>text{{font-family:system-ui,sans-serif;fill:#172033}}.m{{fill:#58657a}}</style><rect width="960" height="500" fill="#fbfcff"/>{body}</svg>'
def correlation_svg(dimensions):
    body=['<text x="40" y="42" font-size="26" font-weight="700">HBQ and HANNA by dimension</text>','<text x="40" y="68" class="m">Prompt-cluster bootstrap intervals.</text>']
    for index,key in enumerate(RATING_DIMENSIONS):
        value=dimensions[key]["spearman"]; estimate=value["estimate"]
        label="undefined" if estimate is None else f'{estimate:.3f} [{value["ci_95_low"]:.3f}, {value["ci_95_high"]:.3f}]'
        body.append(f'<text x="70" y="{120+index*52}" font-size="17">{key}: {label}; effective bootstrap draws {value.get("effective_draws",0)}</text>')
    return svg("HANNA correlations","Six prompt-clustered Spearman estimates and intervals.",''.join(body))
def comparison_svg(dimensions,human): return svg("Human-reference context","HBQ correlations beside the selected-slice ordinal agreement statistic.",''.join(f'<text x="70" y="{120+i*52}" font-size="17">{key}: HBQ {"undefined" if dimensions[key]["spearman"]["estimate"] is None else f"{dimensions[key]["spearman"]["estimate"]:.3f}"}; ordinal agreement {human[key]["value"]:.3f}</text>' for i,key in enumerate(RATING_DIMENSIONS)))
def repeatability_svg(metrics): return svg("HANNA repeatability","Per-item score variability and leaf agreement.",f'<text x="70" y="130" font-size="24">Exact all-five leaf agreement: {metrics["leaf_exact_all_five_agreement"]:.1%}</text><text x="70" y="190" font-size="24">Nominal alpha: {metrics["nominal_krippendorff_alpha"]:.3f}</text><text x="70" y="250" font-size="24">Mean within-item score SD: {metrics["within_item_score_standard_deviation"]["mean"]:.3f}</text>')
def assert_public_safe(output: Path, forbidden: Iterable[str]) -> None:
    for path in output.rglob("*"):
        if path.is_file() and any(value and value in path.read_text(encoding="utf-8") for value in forbidden): raise ValueError(f"Public output leaks forbidden data: {path.name}")
def strings(value):
    if isinstance(value,str): return [value]
    if isinstance(value,dict): return [text for item in value.values() for text in strings(item)]
    if isinstance(value,list): return [text for item in value for text in strings(item)]
    return []

def analyze(data: Path, work: Path, output: Path, phase: str) -> None:
    if output.exists(): raise ValueError(f"Output already exists: {output}")
    fetch_or_verify_dataset(data); frozen=validate_frozen_contract(work); validate_external_inputs(work,frozen); verify_phase_runs(work,frozen,phase)
    base_selections=frozen["partitions"]["development" if phase in {"development","repeatability"} else "confirmatory"]
    selections=([next(row for row in base_selections if row["item_id"]==repeat["item_id"]) for repeat in frozen["repeatability"]["items"]] if phase=="repeatability" else base_selections)
    items={item.item_id:item for item in load_hanna_items(data)}; mappings=frozen["mapping_sets"]; records=[]
    if phase != "repeatability":
        for selection in selections:
            rows,score=verify_run(work,frozen,phase,selection,1); folder=work/"inputs"/("development" if phase=="development" else "confirmatory")/selection["item_id"]; records.append(record_for(items[selection["item_id"]],selection,rows,score,(folder/"source.md").read_text(encoding="utf-8"),(folder/"prompt.md").read_text(encoding="utf-8"),mappings))
    generated=[row for row in records if row["source_model"] != "Human"]
    if records and len(generated) != 80: raise ValueError(f"Primary generated-only slice must contain 80 items, found {len(generated)}")
    dimensions={key:dimension_analysis(generated,key,frozen["selection"]["seed"]+index) for index,key in enumerate(RATING_DIMENSIONS)} if generated else {}
    all_dimensions={key:dimension_analysis(records,key,frozen["selection"]["seed"]+100+index) for index,key in enumerate(RATING_DIMENSIONS)} if records else {}
    generated_items=[items[row["item_id"]] for row in selections if row["model"] != "Human"]
    human=ordinal_agreement(generated_items) if phase != "repeatability" else {}
    all_human=ordinal_agreement([items[row["item_id"]] for row in selections]) if phase != "repeatability" else {}
    repeated=repeatability_metrics(work,frozen) if phase=="repeatability" else None
    summary={"format_version":2,"study_id":frozen["study_id"],"phase":phase,"dataset":frozen["dataset"],"mapping_sets":mappings,"item_count":len(selections) if phase=="repeatability" else len(records),"primary_generated_only":{"item_count":len(generated),"dimensions":dimensions,"macro_spearman":macro_cluster_bootstrap(generated,frozen["selection"]["seed"]) if generated else None,"ordinal_human_agreement":human},"secondary_all_11":{"item_count":len(records),"dimensions":all_dimensions,"ordinal_human_agreement":all_human},"source_model_strata":source_model_strata(records) if records else {},"published_human_agreement_context":"HANNA paper reports ICC(2,k) approximately .29-.56; this selected-slice statistic is not a ceiling.","repeatability":repeated,"interpretation_limits":["Only already-published HANNA ratings are used; no new human judging occurs.","HANNA is human-reference context, not literary ground truth."]}
    output.mkdir(parents=True); write_json(output/"summary.json",summary); write_text(output/"items.jsonl",''.join(json.dumps(row,sort_keys=True)+"\n" for row in records));
    if dimensions: write_text(output/"dimension-correlations.svg",correlation_svg(dimensions)); write_text(output/"human-reference-comparison.svg",comparison_svg(dimensions,human))
    if repeated: write_json(output/"repeatability.json",repeated); write_text(output/"repeatability.svg",repeatability_svg(repeated))
    write_json(output/"manifest.json",{"format_version":2,"study_id":frozen["study_id"],"phase":phase,"package_commit":frozen["package_commit"],"mapping_sets_sha256":frozen["mapping_sets_sha256"],"question_ids_sha256":hashlib.sha256(canonical_json(frozen["question_ids"])).hexdigest(),"files":{path.relative_to(output).as_posix():{"bytes":path.stat().st_size,"sha256":sha256_path(path)} for path in sorted(output.rglob("*")) if path.is_file() and path.name!="manifest.json"}})
    forbidden=[]
    for item in [items[row["item_id"]] for row in selections]: forbidden += [item.story,item.prompt]
    forbidden += [str(work),"Worker ID","Assignment ID",*privacy_forbidden_strings(data)]
    for run in (work/"runs"/phase).rglob("run.json"):
        manifest=read_json(run); forbidden += [str(manifest.get("run_id",""))]
        for checkpoint in (run.parent/"responses").glob("batch-*.json"):
            provider=read_json(checkpoint).get("provider",{}); forbidden += strings(provider)
    assert_public_safe(output,forbidden)

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--data-dir",required=True,type=Path); parser.add_argument("--work-dir",required=True,type=Path); parser.add_argument("--phase",required=True,choices=("development","repeatability","confirmatory")); parser.add_argument("--output-dir",required=True,type=Path); args=parser.parse_args(); analyze(args.data_dir.resolve(),args.work_dir.resolve(),args.output_dir.resolve(),args.phase); return 0
if __name__=="__main__": raise SystemExit(main())
