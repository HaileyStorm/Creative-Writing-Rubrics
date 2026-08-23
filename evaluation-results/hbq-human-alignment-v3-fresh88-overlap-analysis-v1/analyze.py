#!/usr/bin/env python3
"""Publish noncanonical overlap views from sealed Fresh88 verdicts only."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from study import CONTRACT, CONTRACT_PATH, HERE, atomic_output_directory, canonical, ensure_output_disjoint, fingerprint, read_json, sha

BASE_ROOT = HERE.parent / "hbq-human-alignment-v3-fresh88-analysis-v1"
ASSESSSED = {"YES", "NO"}


def _load_base() -> Any:
    study_spec = importlib.util.spec_from_file_location("fresh88_overlap_base_study", BASE_ROOT / "study.py")
    analysis_spec = importlib.util.spec_from_file_location("fresh88_overlap_base_analysis", BASE_ROOT / "analyze.py")
    if study_spec is None or study_spec.loader is None or analysis_spec is None or analysis_spec.loader is None:
        raise ValueError("Pinned Fresh88 analysis helpers are unavailable")
    base_study = importlib.util.module_from_spec(study_spec)
    study_spec.loader.exec_module(base_study)
    prior = sys.modules.get("study")
    sys.modules["study"] = base_study
    try:
        module = importlib.util.module_from_spec(analysis_spec)
        sys.modules[analysis_spec.name] = module
        analysis_spec.loader.exec_module(module)
        return module
    finally:
        if prior is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = prior


def implementation_binding() -> dict[str, dict[str, Any]]:
    return {name: fingerprint(HERE / name) for name in ("analyze.py", "study.py", "study-contract.json")}


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _mapping_geometry(mappings: Mapping[str, Sequence[str]]) -> tuple[list[str], dict[str, list[str]]]:
    occurrences = [(dimension, identifier) for dimension, identifiers in mappings.items() for identifier in identifiers]
    unique = sorted({identifier for _, identifier in occurrences})
    owners: dict[str, list[str]] = defaultdict(list)
    for dimension, identifier in occurrences:
        owners[identifier].append(dimension)
    if len(occurrences) != 28 or len(unique) != 27 or owners.get("craft.narrative.narrative_momentum.investment") != ["Empathy", "Engagement"]:
        raise ValueError("Fresh88 mapping geometry is no longer the expected 27-leaf/28-occurrence overlap")
    return unique, dict(owners)


def _state_scores(verdicts: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    result = {str(row.get("question_id")): str(row.get("verdict")) for row in verdicts}
    if len(result) != len(verdicts):
        raise ValueError("Fresh88 verdict identities are not unique")
    return result


def _projection_record(record: Mapping[str, Any], *, identifier: str, values: Sequence[str], targets: Sequence[float]) -> dict[str, Any]:
    assessed = [value for value in values if value in ASSESSSED]
    score = _mean([float(value == "YES") for value in assessed])
    return {
        "item_id": record["item_id"],
        "prompt_group_id": record["prompt_group_id"],
        "source_model": record["source_model"],
        "human_means": {identifier: _mean(targets)},
        "hbq_mapping": {identifier: {
            "score": score,
            "coverage": len(assessed) / len(values) if values else None,
            "unresolved": values.count("CANNOT_ASSESS"),
            "not_applicable": values.count("NOT_APPLICABLE"),
            "question_count": len(values),
        }},
    }


def _dimension_record(record: Mapping[str, Any], dimensions: Sequence[str], identifier: str) -> dict[str, Any]:
    projections = [record["hbq_mapping"][dimension] for dimension in dimensions]
    usable = [(projection["score"], float(record["human_means"][dimension])) for projection, dimension in zip(projections, dimensions) if projection["score"] is not None]
    values = [float(value) for value, _ in usable]
    targets = [target for _, target in usable]
    return _projection_record(record, identifier=identifier, values=["YES"] * len(values), targets=targets) | {
        "hbq_mapping": {identifier: {
            "score": _mean(values),
            "coverage": _mean([float(projection["coverage"]) for projection in projections]),
            "unresolved": sum(int(projection["unresolved"]) for projection in projections),
            "not_applicable": sum(int(projection["not_applicable"]) for projection in projections),
            "question_count": sum(int(projection["question_count"]) for projection in projections),
        }}
    }


def _view_metric(metrics: Any, rows: Sequence[Mapping[str, Any]], identifier: str, seed: int) -> dict[str, Any]:
    result = metrics.dimension_analysis(list(rows), identifier, seed)
    result["aggregation"] = {"identifier": identifier, "item_count": len(rows)}
    return result


def _six_dimension_view(metrics: Any, rows: Sequence[Mapping[str, Any]], dimensions: Sequence[str], seed: int) -> dict[str, Any]:
    per_dimension = {name: metrics.dimension_analysis(list(rows), name, seed + index) for index, name in enumerate(dimensions)}
    return {
        "aggregation": "published six-dimension mapping; macro is the unweighted mean of six dimension Spearman estimates",
        "dimension_count": len(dimensions),
        "occurrence_count": sum(int(rows[0]["hbq_mapping"][name]["question_count"]) for name in dimensions) if rows else 0,
        "dimensions": per_dimension,
        "macro_spearman": metrics.macro_cluster_bootstrap(list(rows), seed),
        "mean_dimension_coverage": _mean([float(value["mean_coverage"]) for value in per_dimension.values() if value["mean_coverage"] is not None]),
    }


def _overlap_view(metrics: Any, records: Sequence[Mapping[str, Any]], dimensions: Sequence[str], mappings: Mapping[str, Sequence[str]], *, weighted: bool, seed: int) -> dict[str, Any]:
    unique, owners = _mapping_geometry(mappings)
    projection: list[dict[str, Any]] = []
    for record in records:
        labels = record["labels"]
        pairs = [(identifier, owner) for identifier in unique for owner in owners[identifier]] if weighted else [(identifier, None) for identifier in unique]
        states = [labels[identifier] for identifier, _ in pairs]
        targets = [float(record["human_means"][owner]) if owner is not None else _mean([float(record["human_means"][dimension]) for dimension in owners[identifier]]) for identifier, owner in pairs]
        projection.append(_projection_record(record, identifier="overlap", values=states, targets=[float(value) for value in targets if value is not None]))
    metric = _view_metric(metrics, projection, "overlap", seed)
    return {
        "aggregation": "Each verdict is unchanged; only this descriptive averaging projection differs.",
        "unique_leaf_count": len(unique),
        "occurrence_count": 28 if weighted else len(unique),
        "duplicate_investment_treatment": "two dimension occurrences retained" if weighted else "one leaf, human target averaged across Empathy and Engagement",
        "spearman": metric,
    }


def _hierarchical_view(metrics: Any, records: Sequence[Mapping[str, Any]], dimensions: Sequence[str], seed: int) -> dict[str, Any]:
    rows = [_dimension_record(record, dimensions, "dimension_macro") for record in records]
    return {
        "aggregation": "Per-story mean of available six dimension scores, compared with the matching mean human dimension rating.",
        "dimension_count": len(dimensions),
        "spearman": _view_metric(metrics, rows, "dimension_macro", seed),
    }


def _native_view(metrics: Any, records: Sequence[Mapping[str, Any]], domains: Sequence[str], seed: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for index, identifier in enumerate(("final_score", *domains)):
        rows = []
        for record in records:
            score = record["native"][identifier]
            rows.append(_projection_record(record, identifier=identifier, values=["YES"] if score["value"] is not None else [], targets=[float(record["human_overall"])]))
            rows[-1]["hbq_mapping"][identifier].update({"score": score["value"], "coverage": score["coverage"]})
        output[identifier] = _view_metric(metrics, rows, identifier, seed + index)
    return {
        "aggregation": "Existing native HBQ report scores only; domain scores are normalized by their own nominal points for descriptive comparability, while final score is retained in native units.",
        "human_target": "HANNA human_overall",
        "final_and_domains": output,
    }


def _leaf_diagnostics(metrics: Any, records: Sequence[Mapping[str, Any]], mappings: Mapping[str, Sequence[str]], seed: int) -> list[dict[str, Any]]:
    unique, owners = _mapping_geometry(mappings)
    output = []
    for index, identifier in enumerate(unique):
        rows = []
        values: list[str] = []
        for record in records:
            states = [record["labels"][identifier]]
            targets = [_mean([float(record["human_means"][dimension]) for dimension in owners[identifier]])]
            rows.append(_projection_record(record, identifier=identifier, values=states, targets=[float(targets[0])]))
            values.extend(states)
        assessed = [value for value in values if value in ASSESSSED]
        output.append({
            "question_id": identifier,
            "module_id": identifier.rsplit(".", 1)[0],
            "mapped_dimensions": owners[identifier],
            "mapping_occurrence_count": len(owners[identifier]),
            "assessment": {"coverage": len(assessed) / len(values), "yes_fraction": _mean([float(value == "YES") for value in assessed]), "cannot_assess": values.count("CANNOT_ASSESS"), "not_applicable": values.count("NOT_APPLICABLE")},
            "alignment": _view_metric(metrics, rows, identifier, seed + index),
        })
    return output


def _native_scores(artifacts: Path, plan: Mapping[str, Any]) -> tuple[dict[str, dict[str, dict[str, float | None]]], list[str]]:
    all_scores: dict[str, dict[str, dict[str, float | None]]] = {}
    domain_ids: set[str] = set()
    for cell in plan["cells"]:
        raw = json.loads((artifacts / cell["run_dir"] / "score.v2.json").read_text(encoding="utf-8"))
        final = raw.get("final_score", {})
        if not isinstance(final, Mapping):
            raise ValueError("Fresh88 native final score is malformed")
        result: dict[str, dict[str, float | None]] = {"final_score": {"value": float(final["observed"]), "coverage": float(raw.get("coverage"))}}
        for domain in raw.get("domains", []):
            if not isinstance(domain, Mapping) or not isinstance(domain.get("domain_id"), str):
                raise ValueError("Fresh88 native domain score is malformed")
            domain_id = str(domain["domain_id"])
            score, nominal = domain.get("score"), domain.get("nominal_points")
            if not isinstance(score, Mapping) or not isinstance(score.get("observed"), (int, float)) or not isinstance(nominal, (int, float)) or not nominal:
                raise ValueError("Fresh88 native domain score lacks an observed nominal score")
            result[domain_id] = {"value": float(score["observed"]) / float(nominal), "coverage": float(domain.get("coverage"))}
            domain_ids.add(domain_id)
        all_scores[str(cell["item_id"])] = result
    if not all(set(values) == {"final_score", *domain_ids} for values in all_scores.values()):
        raise ValueError("Fresh88 native domain geometry varies across sealed runs")
    return all_scores, sorted(domain_ids)


def _public_safe(rendered: Mapping[str, str], base: Any, data: Path, roots: Sequence[Path], selected: Sequence[Mapping[str, Any]], items: Mapping[str, Any]) -> None:
    base._public_safe(rendered, data, base._load_historical_metrics(roots[-1]), list(roots), list(selected), items)


def verify_output(output: Path) -> dict[str, Any]:
    summary_path, diagnostics_path, manifest_path = (output / name for name in CONTRACT["outputs"])
    if not summary_path.is_file() or not diagnostics_path.is_file() or not manifest_path.is_file():
        raise ValueError("Overlap analysis output is incomplete")
    summary, manifest = read_json(summary_path), read_json(manifest_path)
    if summary.get("study_id") != CONTRACT["study_id"] or summary.get("noncanonical") is not True:
        raise ValueError("Overlap analysis summary identity drifted")
    binding = summary.get("evidence_binding")
    if not isinstance(binding, Mapping) or binding.get("implementation") != implementation_binding():
        raise ValueError("Overlap analysis implementation binding drifted")
    expected_files = {name: fingerprint(output / name) for name in CONTRACT["outputs"][:-1]}
    if manifest != {"format_version": 1, "study_id": CONTRACT["study_id"], "analysis_contract_sha256": sha(CONTRACT_PATH), "implementation": implementation_binding(), "summary_evidence_binding_sha256": hashlib.sha256(canonical(binding)).hexdigest(), "files": expected_files}:
        raise ValueError("Overlap analysis manifest does not bind the exact output and implementation")
    geometry = summary.get("mapping_geometry")
    if geometry != {"dimension_count": 6, "unique_leaf_count": 27, "occurrence_count": 28, "duplicate_leaf": {"question_id": "craft.narrative.narrative_momentum.investment", "dimensions": ["Empathy", "Engagement"]}}:
        raise ValueError("Overlap analysis geometry drifted")
    diagnostics = [json.loads(line) for line in diagnostics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(diagnostics) != 27 or len({row.get("question_id") for row in diagnostics}) != 27:
        raise ValueError("Overlap analysis leaf diagnostics do not cover the unique mapping leaves")
    return summary


def analyze(data: Path, work: Path, authority: Path, artifacts: Path, runtime: Path, output: Path) -> dict[str, Any]:
    base = _load_base()
    frozen, freeze_receipt, plan, work_artifacts = base._load_inputs(work, authority, artifacts, runtime)
    roots = [data, work, authority, artifacts, runtime]
    ensure_output_disjoint(output, roots)
    metrics = base._load_historical_metrics(runtime)
    policy, base_source_manifest = base._analysis_bindings(metrics)
    observed_dataset = metrics.fetch_or_verify_dataset(data)
    expected_dataset = {base.CONTRACT["dataset"]["csv_name"]: {"sha256": base.CONTRACT["dataset"]["csv_sha256"], "bytes": observed_dataset.get(base.CONTRACT["dataset"]["csv_name"], {}).get("bytes")}, base.CONTRACT["dataset"]["license_name"]: {"sha256": base.CONTRACT["dataset"]["license_sha256"], "bytes": observed_dataset.get(base.CONTRACT["dataset"]["license_name"], {}).get("bytes")}}
    if observed_dataset != expected_dataset:
        raise ValueError("Restored HANNA bytes do not match the pinned Fresh88 source")
    verified = base._historical_verify(runtime, plan, artifacts)
    matrix = base._verify_matrix_gate(plan, work_artifacts, verified)
    items = {item.item_id: item for item in metrics.load_hanna_items(data)}
    mappings = metrics.mapping_sets()
    dimensions = tuple(policy["dimensions"])
    unique, owners = _mapping_geometry(mappings)
    selected = {row["item_id"]: row for row in frozen["selection"]["development"]}
    canonical_ids = frozen["fresh_complement"]["item_ids"]
    verified_by_id = {row["item_id"]: row for row in verified}
    native_by_id, domain_ids = _native_scores(artifacts, plan)
    records: list[dict[str, Any]] = []
    for item_id in canonical_ids:
        item, raw = items[item_id], verified_by_id[item_id]
        labels = _state_scores(raw["verdicts"])
        if not set(unique) <= set(labels):
            raise ValueError("Fresh88 sealed verdicts omit a mapped overlap leaf")
        score = {"final_score": {"observed": raw["metrics"]["score"]}}
        record = metrics.record_for(item, selected[item_id], raw["verdicts"], score, item.story, item.prompt, mappings)
        record["labels"] = labels
        record["native"] = native_by_id[item_id]
        records.append(record)
    generated = [record for record in records if record["source_model"] != "Human"]
    if len(records) != 88 or len(generated) != 80:
        raise ValueError("Fresh88 selection geometry drifted")
    def views(rows: Sequence[Mapping[str, Any]], seed: int) -> dict[str, Any]:
        return {
            "six_dimension_macro": _six_dimension_view(metrics, rows, dimensions, seed),
            "unique_27_leaf_overlap": _overlap_view(metrics, rows, dimensions, mappings, weighted=False, seed=seed + 100),
            "occurrence_weighted_28_mapping": _overlap_view(metrics, rows, dimensions, mappings, weighted=True, seed=seed + 200),
            "hierarchical_dimension_to_macro": _hierarchical_view(metrics, rows, dimensions, seed + 300),
            "native_hbq_domains_and_final": _native_view(metrics, rows, domain_ids, seed + 400),
        }
    diagnostics = _leaf_diagnostics(metrics, generated, mappings, 561320)
    summary = {
        "format_version": 1,
        "study_id": CONTRACT["study_id"],
        "analysis_kind": CONTRACT["kind"],
        "noncanonical": True,
        "item_counts": {"primary_generated_only": len(generated), "secondary_all_11": len(records)},
        "mapping_geometry": {"dimension_count": len(dimensions), "unique_leaf_count": len(unique), "occurrence_count": sum(len(value) for value in mappings.values()), "duplicate_leaf": {"question_id": "craft.narrative.narrative_momentum.investment", "dimensions": owners["craft.narrative.narrative_momentum.investment"]}},
        "evidence_binding": {"implementation": implementation_binding(), "overlap_contract_sha256": sha(CONTRACT_PATH), "base_analysis_contract_sha256": sha(BASE_ROOT / "study-contract.json"), "base_analysis_source_manifest_sha256": base_source_manifest, "frozen_successor_sha256": base.CONTRACT["predecessor"]["frozen_successor_sha256"], "freeze_receipt_sha256": base.CONTRACT["predecessor"]["freeze_receipt_sha256"], "verifier_matrix_sha256": matrix["matrix_sha256"], "semantic_gate_sha256": sha(work / "semantic-development-gate.json"), "historical_runtime_source_manifest_sha256": freeze_receipt["runtime_source_manifest_sha256"], "dataset": observed_dataset},
        "primary_generated_only": views(generated, 560820),
        "secondary_all_11": views(records, 560920),
        "interpretation_limits": CONTRACT["interpretation_limits"],
    }
    diagnostics_text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in diagnostics)
    provisional = {"summary.json": json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "leaf-diagnostics.jsonl": diagnostics_text}
    _public_safe(provisional, base, data, roots, list(selected.values()), items)
    manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "analysis_contract_sha256": sha(CONTRACT_PATH), "implementation": implementation_binding(), "summary_evidence_binding_sha256": hashlib.sha256(canonical(summary["evidence_binding"])).hexdigest(), "files": {name: {"bytes": len(text.encode("utf-8")), "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()} for name, text in provisional.items()}}
    files = {**provisional, "manifest.json": json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"}
    _public_safe(files, base, data, roots, list(selected.values()), items)
    atomic_output_directory(output, files)
    verify_output(output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    for flag, name in (("--data-dir", "data"), ("--work-dir", "work"), ("--authority-dir", "authority"), ("--artifact-dir", "artifacts"), ("--historical-runtime-root", "runtime"), ("--output-dir", "output")):
        parser.add_argument(flag, required=True, type=Path, dest=name)
    args = parser.parse_args()
    analyze(**{name: Path(value).resolve() for name, value in vars(args).items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
