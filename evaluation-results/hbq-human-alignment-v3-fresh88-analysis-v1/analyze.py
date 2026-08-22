#!/usr/bin/env python3
"""Reconstruct the sealed Fresh88 development analysis without provider contact."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from study import CONTRACT, CONTRACT_PATH, HERE, REPO_ROOT, atomic_output_directory, canonical, ensure_output_disjoint, fingerprint, read_json, sha


def _load_historical_metrics(runtime: Path) -> Any:
    study_path = runtime / "evaluation-results" / "hbq-human-alignment-v3" / "study.py"
    analysis_path = runtime / "evaluation-results" / "hbq-human-alignment-v3" / "analyze_study.py"
    if not study_path.is_file() or not analysis_path.is_file():
        raise ValueError("Historical runtime lacks the pinned HANNA analysis modules")
    study_spec = importlib.util.spec_from_file_location("fresh88_historical_study", study_path)
    analysis_spec = importlib.util.spec_from_file_location("fresh88_historical_analysis", analysis_path)
    if study_spec is None or study_spec.loader is None or analysis_spec is None or analysis_spec.loader is None:
        raise ValueError("Historical HANNA analysis modules are unavailable")
    historical_study = importlib.util.module_from_spec(study_spec)
    previous_path = list(sys.path)
    previous_study = sys.modules.get("study")
    sys.path.insert(0, str(runtime / "src"))
    sys.modules[study_spec.name] = historical_study
    sys.modules["study"] = historical_study
    try:
        study_spec.loader.exec_module(historical_study)
        historical_analysis = importlib.util.module_from_spec(analysis_spec)
        sys.modules[analysis_spec.name] = historical_analysis
        analysis_spec.loader.exec_module(historical_analysis)
        return historical_analysis
    finally:
        sys.path[:] = previous_path
        if previous_study is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous_study


def _historical_runtime(plan: Mapping[str, Any], freeze_receipt: Mapping[str, Any], runtime: Path) -> None:
    manifest = plan.get("base_frozen", {}).get("runtime_manifest")
    files = manifest.get("files") if isinstance(manifest, Mapping) else None
    if not isinstance(files, Mapping) or not files:
        raise ValueError("Fresh88 execution contract lacks a runtime manifest")
    if sha256_canonical(files) != manifest.get("sha256"):
        raise ValueError("Fresh88 execution runtime manifest hash drifted")
    for source_path, binding in files.items():
        if not isinstance(binding, Mapping) or set(binding) != {"path", "bytes", "sha256"}:
            raise ValueError("Historical runtime source binding is malformed")
        source = Path(str(source_path)).resolve()
        try:
            relative = source.relative_to(REPO_ROOT)
        except ValueError as exc:
            raise ValueError("Historical runtime source is outside the canonical repository") from exc
        candidate = runtime / relative
        if not candidate.is_file() or fingerprint(candidate) != {"bytes": binding["bytes"], "sha256": binding["sha256"]}:
            raise ValueError("Supplied historical runtime does not reproduce the frozen execution source")
    source_map = freeze_receipt.get("runtime_source_map")
    if not isinstance(source_map, Mapping) or freeze_receipt.get("runtime_source_manifest_sha256") != CONTRACT["predecessor"]["runtime_source_manifest_sha256"]:
        raise ValueError("Freeze receipt lacks its exact composed historical runtime manifest")


def _analysis_bindings(metrics: Any) -> tuple[Mapping[str, Any], str]:
    policy, sources = CONTRACT["analysis"], CONTRACT["analysis_sources"]
    for name, binding in sources.items():
        path = HERE / name
        if fingerprint(path) != {"bytes": binding["bytes"], "sha256": binding["sha256"]}:
            raise ValueError("Fresh88 analysis source identity drifted")
    dimensions = tuple(getattr(metrics, "RATING_DIMENSIONS", ()))
    if dimensions != tuple(policy["dimensions"]):
        raise ValueError("Historical HANNA dimension order drifted")
    mappings = metrics.mapping_sets()
    if sha256_canonical(mappings) != policy["mapping_sets_sha256"]:
        raise ValueError("Historical HANNA mapping set drifted")
    return policy, sha256_canonical(sources)


def sha256_canonical(value: Any) -> str:
    import hashlib
    return hashlib.sha256(canonical(value)).hexdigest()


def _assert_scheduled_cell_order(frozen: Mapping[str, Any], plan: Mapping[str, Any]) -> list[str]:
    scheduled = frozen.get("fresh_complement", {}).get("scheduled_item_ids")
    cells = plan.get("cells")
    if not isinstance(scheduled, list) or not isinstance(cells, list) or [cell.get("item_id") if isinstance(cell, Mapping) else None for cell in cells] != scheduled:
        raise ValueError("Fresh88 execution plan does not preserve the authoritative scheduled order")
    return list(scheduled)


def _load_inputs(work: Path, authority: Path, artifacts: Path, runtime: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    predecessor = CONTRACT["predecessor"]
    authority_contract = authority / "frozen-successor-contract.json"
    freeze_receipt_path = authority / "freeze-receipt.json"
    plan_path = work / "fresh88-execution-contract.json"
    receipt_path = work / "fresh88-execution-receipt.json"
    matrix_path = work / "fresh88-verifier-matrix.json"
    gate_path = work / "semantic-development-gate.json"
    expected = {
        authority_contract: predecessor["frozen_successor_sha256"],
        freeze_receipt_path: predecessor["freeze_receipt_sha256"],
        plan_path: predecessor["execution_contract_sha256"],
        receipt_path: predecessor["execution_receipt_sha256"],
    }
    if any(not path.is_file() or sha(path) != digest for path, digest in expected.items()):
        raise ValueError("Frozen Fresh88 authority or execution receipt bytes drifted")
    frozen, freeze_receipt, plan, receipt = (read_json(path) for path in (authority_contract, freeze_receipt_path, plan_path, receipt_path))
    if frozen.get("fresh_complement", {}).get("count") != 88 or frozen.get("binding", {}).get("carried_replay_status") != "rejected" or freeze_receipt.get("replay_status") != "rejected":
        raise ValueError("Fresh88 authority/replay status is invalid")
    if receipt != {"format_version": 1, "study_id": predecessor["study_id"], "execution_contract_sha256": predecessor["execution_contract_sha256"], "purpose": "pre_execution_raw_verifier_binding"}:
        raise ValueError("Fresh88 execution receipt is not the pinned pre-execution receipt")
    if plan.get("study_id") != predecessor["study_id"] or plan.get("phase") != "development" or len(plan.get("cells", [])) != 88:
        raise ValueError("Fresh88 execution plan is incomplete")
    _assert_scheduled_cell_order(frozen, plan)
    _historical_runtime(plan, freeze_receipt, runtime)
    if not matrix_path.is_file() or not gate_path.is_file():
        raise ValueError("Fresh88 sealed matrix or development gate is missing")
    if not artifacts.joinpath("runs").is_dir():
        raise ValueError("Fresh88 repair1 raw artifact root is missing its runs directory")
    expected_names = {str(cell.get("item_id")) for cell in plan["cells"]}
    runs_root = artifacts.joinpath("runs")
    if runs_root.is_symlink():
        raise ValueError("Fresh88 repair1 runs root must not be a reparse directory")
    actual_names: set[str] = set()
    resolved_runs = runs_root.resolve()
    for path in runs_root.iterdir():
        if not path.is_dir():
            continue
        if path.is_symlink() or path.resolve().parent != resolved_runs:
            raise ValueError("Fresh88 repair1 run must not be a reparse or alias directory")
        actual_names.add(path.name)
    if expected_names != actual_names:
        raise ValueError("Fresh88 repair1 raw run set has missing or extra directories")
    return frozen, freeze_receipt, plan, {"receipt": receipt, "matrix": read_json(matrix_path), "gate": read_json(gate_path)}


def _historical_verify(runtime: Path, plan: Mapping[str, Any], artifacts: Path) -> list[dict[str, Any]]:
    script = r'''
import json, sys
from pathlib import Path
runtime, artifact_root = Path(sys.argv[1]), Path(sys.argv[2])
sys.path.insert(0, str(runtime / "src"))
from hbqrs.run_verify import verify_binary_run
plan = json.loads(sys.stdin.read())
base = plan["base_frozen"]
rows = []
for cell in plan["cells"]:
    frozen = dict(base); frozen.update({key: cell[key] for key in ("artifact", "contexts", "task_contract")})
    execution = dict(frozen["execution"]); execution["artifact_id"] = cell["item_id"]; frozen["execution"] = execution
    run = artifact_root / cell["run_dir"]
    result = verify_binary_run(run, frozen)
    score = json.loads((run / "score.v2.json").read_text(encoding="utf-8"))
    verdicts = [json.loads(line) for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    final = score.get("final_score", {})
    observed = final.get("observed") if isinstance(final, dict) else None
    if isinstance(observed, bool) or not isinstance(observed, (int, float)):
        raise ValueError("Verified score lacks a finite observed value")
    rows.append({"item_id": cell["item_id"], "result": result, "metrics": {"score": float(observed), "confidence": score.get("confidence", {"status": "UNAVAILABLE"}), "coverage": final.get("coverage", {"status": "UNAVAILABLE"}), "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}, "verdicts": verdicts})
print(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
'''
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run([sys.executable, "-c", script, str(runtime), str(artifacts)], input=json.dumps(plan, ensure_ascii=False), text=True, encoding="utf-8", capture_output=True, env=environment, timeout=3600, check=False)
    if completed.returncode != 0:
        raise ValueError(f"Historical Fresh88 verifier failed: {completed.stderr.strip() or completed.stdout.strip()}")
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Historical Fresh88 verifier returned invalid JSON") from exc
    if not isinstance(value, list) or len(value) != 88 or any(not isinstance(row, Mapping) for row in value):
        raise ValueError("Historical Fresh88 verifier did not return 88 records")
    return [dict(row) for row in value]


def _verify_matrix_gate(plan: Mapping[str, Any], work_artifacts: Mapping[str, Any], verified: list[dict[str, Any]]) -> dict[str, Any]:
    sessions: set[str] = set()
    records: list[dict[str, Any]] = []
    for cell, row in zip(plan["cells"], verified):
        if row.get("item_id") != cell["item_id"]:
            raise ValueError("Historical verification order drifted")
        result = row.get("result")
        if not isinstance(result, Mapping):
            raise ValueError("Historical verification lacks a raw result")
        found = result.get("sessions")
        if not isinstance(found, list) or not found:
            raise ValueError("Historical verification lacks session commitments")
        for session in found:
            digest = session.get("session_id_sha256") if isinstance(session, Mapping) else None
            if not isinstance(digest, str) or len(digest) != 64 or digest in sessions:
                raise ValueError("Fresh88 session commitments are not globally unique")
            sessions.add(digest)
        records.append({"item_id": cell["item_id"], "origin": cell["origin"], "ordinal": cell["ordinal"], "run_dir": cell["run_dir"], "run_sha256": result.get("run_sha256"), "verifier": result, "metrics": row["metrics"]})
    receipt = work_artifacts["receipt"]
    core = {"format_version": 1, "study_id": CONTRACT["predecessor"]["study_id"], "execution_contract_sha256": receipt["execution_contract_sha256"], "execution_receipt_sha256": CONTRACT["predecessor"]["execution_receipt_sha256"], "records": records, "session_count": len(sessions)}
    matrix = {**core, "matrix_sha256": sha256_canonical(core)}
    if matrix != work_artifacts["matrix"]:
        raise ValueError("Fresh88 verifier matrix does not reconstruct from the raw repair1 evidence")
    scores = [float(record["metrics"]["score"]) for record in records]
    diagnostics = {"score": {"mean": statistics.fmean(scores)}, "confidence": {"status": "DERIVED_FROM_VERIFIED_OUTPUTS"}, "order": {"method": "scheduled_ordinal_halves_v1", "records": 88}, "repeatability": {"status": "UNAVAILABLE", "reason": "one_verified_development_pass"}, "calibration": {"status": "UNAVAILABLE", "reason": "no_empirical_comparison"}}
    gate = {"format_version": 1, "study_id": CONTRACT["predecessor"]["study_id"], "phase": "semantic_development_gate", "development_mode": "fresh_88", "matrix_sha256": matrix["matrix_sha256"], "execution_receipt_sha256": matrix["execution_receipt_sha256"], "diagnostics": diagnostics, "next_phase": "repeatability"}
    if gate != work_artifacts["gate"]:
        raise ValueError("Fresh88 semantic development gate does not reconstruct from the verifier matrix")
    return matrix


def _public_safe(rendered: Mapping[str, str], data: Path, metrics: Any, roots: list[Path], selected: list[Mapping[str, Any]], items: Mapping[str, Any]) -> None:
    forbidden = [str(root.resolve()) for root in roots] + ["Worker ID", "Assignment ID", "source.md", "prompt.md", "task-contract.json", "run_id", "provider"]
    forbidden.extend(metrics.privacy_forbidden_strings(data))
    for row in selected:
        item = items[row["item_id"]]
        forbidden.extend((item.story, item.prompt))
    published = "\n".join(rendered.values())
    if any(token and token in published for token in forbidden):
        raise ValueError("Fresh88 public analysis would disclose private prose, path, or identifier data")


def analyze(data: Path, work: Path, authority: Path, artifacts: Path, runtime: Path, output: Path) -> None:
    frozen, freeze_receipt, plan, work_artifacts = _load_inputs(work, authority, artifacts, runtime)
    roots = [data, work, authority, artifacts, runtime]
    ensure_output_disjoint(output, roots)
    metrics = _load_historical_metrics(runtime)
    policy, analysis_source_manifest_sha256 = _analysis_bindings(metrics)
    observed_dataset = metrics.fetch_or_verify_dataset(data)
    csv_name, license_name = CONTRACT["dataset"]["csv_name"], CONTRACT["dataset"]["license_name"]
    expected_dataset = {csv_name: {"sha256": CONTRACT["dataset"]["csv_sha256"], "bytes": observed_dataset.get(csv_name, {}).get("bytes")}, license_name: {"sha256": CONTRACT["dataset"]["license_sha256"], "bytes": observed_dataset.get(license_name, {}).get("bytes")}}
    if observed_dataset != expected_dataset:
        raise ValueError("Restored HANNA CSV or LICENSE does not match the pinned source bytes")
    verified = _historical_verify(runtime, plan, artifacts)
    matrix = _verify_matrix_gate(plan, work_artifacts, verified)
    items = {item.item_id: item for item in metrics.load_hanna_items(data)}
    selection_rows = {row["item_id"]: row for row in frozen.get("selection", {}).get("development", [])}
    canonical_ids = frozen.get("fresh_complement", {}).get("item_ids")
    scheduled_ids = frozen.get("fresh_complement", {}).get("scheduled_item_ids")
    if not isinstance(canonical_ids, list) or not isinstance(scheduled_ids, list) or len(canonical_ids) != 88 or len(set(canonical_ids)) != 88 or set(canonical_ids) != set(scheduled_ids) or set(canonical_ids) != set(selection_rows) or not set(canonical_ids) <= set(items):
        raise ValueError("Fresh88 canonical selection is not the exact 88-item authority selection")
    by_item = {row["item_id"]: row for row in verified}
    execution_ordinal = {item_id: index for index, item_id in enumerate(scheduled_ids, 1)}
    records: list[dict[str, Any]] = []
    mappings = metrics.mapping_sets()
    for selection_ordinal, item_id in enumerate(canonical_ids, 1):
        selected, raw = selection_rows[item_id], by_item[item_id]
        cell = next(cell for cell in plan["cells"] if cell["item_id"] == item_id)
        item = items[item_id]
        if selected.get("story_sha256") != item.story_sha256 or selected.get("prompt_sha256") != item.prompt_sha256 or cell.get("external_input", {}).get("source.md", {}).get("sha256") != item.story_sha256 or cell.get("external_input", {}).get("prompt.md", {}).get("sha256") != item.prompt_sha256:
            raise ValueError("Fresh88/HANNA item binding drifted")
        score = {"final_score": {"observed": raw["metrics"]["score"]}}
        record = metrics.record_for(item, selected, raw["verdicts"], score, item.story, item.prompt, mappings)
        record["execution_ordinal"] = execution_ordinal[item_id]
        record["selection_ordinal"] = selection_ordinal
        records.append(record)
    generated = [record for record in records if record["source_model"] != "Human"]
    if len(generated) != policy["primary_generated_only"]["item_count"]:
        raise ValueError("Fresh88 primary generated-only analysis must contain 80 items")
    if any(record["source_model"] == policy["primary_generated_only"]["exclude_source_model"] for record in generated):
        raise ValueError("Fresh88 generated-only analysis exclusion drifted")
    dimensions = {name: metrics.dimension_analysis(generated, name, policy["bootstrap"]["primary_base_seed"] + index) for index, name in enumerate(policy["dimensions"])}
    all_dimensions = {name: metrics.dimension_analysis(records, name, policy["bootstrap"]["secondary_base_seed"] + index) for index, name in enumerate(policy["dimensions"])}
    generated_items = [items[row["item_id"]] for row in selection_rows.values() if row["model"] != "Human"]
    summary = {"format_version": 1, "study_id": CONTRACT["study_id"], "analysis_kind": CONTRACT["kind"], "analysis": policy, "item_count": 88, "evidence_binding": {"analysis_contract_sha256": sha(CONTRACT_PATH), "analysis_source_manifest_sha256": analysis_source_manifest_sha256, "frozen_successor_sha256": CONTRACT["predecessor"]["frozen_successor_sha256"], "freeze_receipt_sha256": CONTRACT["predecessor"]["freeze_receipt_sha256"], "execution_contract_sha256": CONTRACT["predecessor"]["execution_contract_sha256"], "execution_receipt_sha256": CONTRACT["predecessor"]["execution_receipt_sha256"], "verifier_matrix_sha256": matrix["matrix_sha256"], "semantic_gate_sha256": sha(work / "semantic-development-gate.json"), "historical_runtime_source_manifest_sha256": freeze_receipt["runtime_source_manifest_sha256"], "dataset": observed_dataset}, "primary_generated_only": {"item_count": policy["primary_generated_only"]["item_count"], "dimensions": dimensions, "macro_spearman": metrics.macro_cluster_bootstrap(generated, policy["bootstrap"]["macro_seed"]), "ordinal_human_agreement": metrics.ordinal_agreement(generated_items)}, "secondary_all_11": {"item_count": policy["secondary_all_11"]["item_count"], "dimensions": all_dimensions, "ordinal_human_agreement": metrics.ordinal_agreement([items[item_id] for item_id in canonical_ids])}, "source_model_strata": metrics.source_model_strata(records), "scheduled_order_diagnostics": {"method": "scheduled_ordinal_halves_v1", "early_item_count": 44, "late_item_count": 44, "early_mean_hbq_full_observed_score": statistics.fmean(raw["hbq_full_observed_score"] for raw in records if raw["execution_ordinal"] <= 44), "late_mean_hbq_full_observed_score": statistics.fmean(raw["hbq_full_observed_score"] for raw in records if raw["execution_ordinal"] > 44)}, "mapping_sets": mappings, "interpretation_limits": CONTRACT["interpretation_limits"]}
    items_text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    provisional = {"summary.json": json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", "items.jsonl": items_text}
    _public_safe(provisional, data, metrics, roots, list(selection_rows.values()), items)
    manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "analysis_contract_sha256": sha(CONTRACT_PATH), "summary_evidence_binding_sha256": sha256_canonical(summary["evidence_binding"]), "files": {name: {"bytes": len(text.encode("utf-8")), "sha256": __import__("hashlib").sha256(text.encode("utf-8")).hexdigest()} for name, text in provisional.items()}}
    files = {**provisional, "manifest.json": json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"}
    _public_safe(files, data, metrics, roots, list(selection_rows.values()), items)
    atomic_output_directory(output, files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--authority-dir", required=True, type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--historical-runtime-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.data_dir.resolve(), args.work_dir.resolve(), args.authority_dir.resolve(), args.artifact_dir.resolve(), args.historical_runtime_root.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
