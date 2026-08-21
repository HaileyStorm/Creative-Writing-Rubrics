#!/usr/bin/env python3
"""Verify provider receipts and emit prose-free HANNA supplemental results."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import random
import statistics
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, NOUS_TRANSPORT_POLICY, VALIDATION_FEEDBACK_POLICY, _json_bytes, _load_checkpoints, _question_payload, _render_prompt, _validate_provider_artifacts
from hbqrs.weights import materialize_weight_profile
from study import CONTRACT, HERE, PHASES, _fingerprint, canonical, load_frozen, primary_input, primary_root, provider, sha, validate_dataset_and_metadata, write_json


def _load_primary() -> tuple[Any, Any]:
    study_path = primary_root() / "study.py"
    study_spec = importlib.util.spec_from_file_location("supplemental_primary_study", study_path)
    if study_spec is None or study_spec.loader is None:
        raise ValueError("Primary HANNA study helper unavailable")
    study = importlib.util.module_from_spec(study_spec)
    sys.modules[study_spec.name] = study
    study_spec.loader.exec_module(study)
    analysis_path = primary_root() / "analyze_study.py"
    analysis_spec = importlib.util.spec_from_file_location("supplemental_primary_analysis", analysis_path)
    if analysis_spec is None or analysis_spec.loader is None:
        raise ValueError("Primary HANNA analyzer helper unavailable")
    analysis = importlib.util.module_from_spec(analysis_spec)
    prior = sys.modules.get("study")
    sys.modules["study"] = study
    try:
        analysis_spec.loader.exec_module(analysis)
    finally:
        if prior is None:
            del sys.modules["study"]
        else:
            sys.modules["study"] = prior
    return study, analysis


PRIMARY_STUDY, PRIMARY_ANALYSIS = _load_primary()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None


def _checkpoint_files(run: Path) -> list[Path]:
    return sorted((run / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def receipt(run: Path, record: Mapping[str, Any], expected: Mapping[str, Any]) -> str:
    value = record.get("provider")
    if not isinstance(value, Mapping):
        raise ValueError("Accepted checkpoint lacks a provider receipt")
    if value.get("requested") != {"model": expected["model"], "reasoning_effort": expected["reasoning"]}:
        raise ValueError("Provider receipt request settings drifted")
    reported = value.get("reported")
    if not isinstance(reported, Mapping) or reported.get("provider") != expected["provider"] or reported.get("model") not in expected["reported_models"]:
        raise ValueError("Provider receipt reported settings drifted")
    if value.get("reasoning_attested") is not False or not isinstance(value.get("reasoning_attestation"), str):
        raise ValueError("Supplemental provider reasoning provenance is malformed")
    try:
        _validate_provider_artifacts(run, record)
    except Exception as exc:
        raise ValueError("Provider artifacts do not bind to the accepted checkpoint") from exc
    artifacts = value.get("provider_artifacts")
    if expected["provider"] == "grok":
        if not isinstance(artifacts, Mapping) or set(artifacts) != {"grok_envelope"} or not isinstance(value.get("cli_version"), str) or not _is_hash(value.get("session_id_sha256")) or not _is_hash(value.get("request_id_sha256")):
            raise ValueError("Grok receipt/session/artifact proof is malformed")
        return "grok:" + str(value["session_id_sha256"])
    required = {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}
    if not isinstance(artifacts, Mapping) or set(artifacts) != required or "session_id_sha256" in value or value.get("provider_canonical_model") != expected["provider_canonical_model"] or value.get("tool_free") is not True or value.get("exact_gate_eligible") is not False or value.get("transport_policy") != NOUS_TRANSPORT_POLICY or value.get("logical_provider_request_count") != 1 or value.get("physical_http_attempt_count") not in {1, 2} or value.get("recovered_request_count") not in {0, 1} or not _is_hash(value.get("evidence_sha256")) or not _is_hash(value.get("serialization_proof_sha256")):
        raise ValueError("Nous stateless transport/serialization proof is malformed")
    return "nous:" + str(value["evidence_sha256"]) + ":" + str(value["serialization_proof_sha256"])


def _expected_rows(task_contract: Mapping[str, Any]) -> tuple[Any, Any, list[dict[str, Any]], list[str], Mapping[str, Any]]:
    modules0, bundle0, default = materialize_weight_profile(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    compiled = compile_bundle(modules0, bundle0, task_contract=task_contract)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    rows = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    return modules0, bundle0, rows, [str(item["question"]["id"]) for item in rows], default


def verify_run(work: Path, frozen: Mapping[str, Any], provider_id: str, phase: str, selection: Mapping[str, Any], repetition: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    item = provider(provider_id)
    folder, row = primary_input(frozen, phase, str(selection["item_id"]))
    run = work / "runs" / provider_id / phase / str(selection["item_id"]) / f"run-{repetition:02d}"
    manifest, score = _read(run / "run.json"), _read(run / "score.json")
    config = manifest.get("configuration")
    if manifest.get("format_version") != 3 or not isinstance(config, Mapping) or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(config)).hexdigest():
        raise ValueError("Provider manifest-v3 is malformed or unbound")
    task_contract = _read(folder / "task-contract.json")
    modules, bundle, rows, ids, default_weight = _expected_rows(task_contract)
    expected_inputs = frozen["input_commitments"]["development" if phase in {"development", "repeatability"} else "confirmatory"][str(selection["item_id"])]
    required = {
        "artifact": expected_inputs["source.md"], "contexts": [expected_inputs["prompt.md"]], "task_contract": expected_inputs["task-contract.json"],
        "bundle_id": "prose.short_story", "question_ids": ids, "provider": item["provider"], "model": item["model"], "reasoning": item["reasoning"],
        "batch_size": 32, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY,
        "artifact_id": selection["item_id"], "judge_id": f"{item['provider']}:{item['model']}", "strict_ai": False, "allow_unattested_reasoning": True,
    }
    if _compact(config.get("artifact")) != required["artifact"] or [_compact(value) for value in config.get("contexts", [])] != required["contexts"] or _compact(config.get("task_contract")) != required["task_contract"] or config.get("task_contract", {}).get("contract_id") != "hanna" or any(config.get(key) != value for key, value in required.items() if key not in {"artifact", "contexts", "task_contract"}):
        raise ValueError("Provider run does not exactly reuse the frozen primary inputs/settings")
    runtime = frozen.get("primary_runtime_files", {})
    binary_record = runtime.get("prompts/judge/BINARY_EVALUATION_PROMPT.md") if isinstance(runtime, Mapping) else None
    schema_record = runtime.get("schema/hbq_judge_response.schema.json") if isinstance(runtime, Mapping) else None
    if [_compact(value) for value in config.get("prompts", [])] != [_compact(binary_record)] or _compact(config.get("response_schema")) != _compact(schema_record):
        raise ValueError("Provider run prompt/schema files do not match the exact primary runtime")
    if config.get("weight_profile") != default_weight or config.get("questions_sha256") != hashlib.sha256(_json_bytes(_question_payload(rows))).hexdigest() or config.get("compiled_bundle_sha256") != hashlib.sha256(_json_bytes(compile_bundle(modules, bundle, task_contract=task_contract))).hexdigest():
        raise ValueError("Provider run weight/question binding drifted")
    source, prompt = (folder / "source.md").read_text(encoding="utf-8"), (folder / "prompt.md").read_text(encoding="utf-8")
    binary = (prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8")
    expected_prompts = [_render_prompt(binary_prompt=binary, artifact={"name": "source.md", "text": source}, contexts=[{"name": "prompt.md", "text": prompt}], bundle_id="prose.short_story", artifact_id=str(selection["item_id"]), questions=rows[offset:offset + 32]).encode("utf-8") for offset in range(0, len(rows), 32)]
    checkpoints = _checkpoint_files(run)
    if len(checkpoints) != len(expected_prompts):
        raise ValueError("Provider run does not contain the complete frozen batch schedule")
    receipts: list[str] = []
    previous = None
    for number, (checkpoint, expected_prompt) in enumerate(zip(checkpoints, expected_prompts), 1):
        prompt_path = checkpoint.with_suffix(".prompt.txt.gz")
        try:
            observed_prompt = gzip.decompress(prompt_path.read_bytes())
        except (OSError, EOFError) as exc:
            raise ValueError("Provider checkpoint prompt is unreadable") from exc
        record = _read(checkpoint)
        expected_ids = ids[(number - 1) * 32:number * 32]
        if observed_prompt != expected_prompt or record.get("format_version") != 4 or record.get("batch") != number or record.get("question_ids") != expected_ids or record.get("previous_checkpoint_sha256") != previous or record.get("base_prompt_sha256") != hashlib.sha256(expected_prompt).hexdigest() or record.get("prompt_sha256") != hashlib.sha256(expected_prompt).hexdigest() or record.get("retry_policy") != {"batch_attempts": 3}:
            raise ValueError("Provider checkpoint does not bind the exact primary rendered batch bytes")
        receipts.append(receipt(run, record, item))
        previous = sha(checkpoint)
    try:
        verdicts, count, _ = _load_checkpoints(run, artifact_text=source, context_texts=[prompt], batch_attempts=3, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("Provider checkpoint-v4 recovery/retry verification failed") from exc
    stored = [json.loads(line) for line in (run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if count != len(expected_prompts) or verdicts != stored or [row.get("question_id") for row in stored] != ids or len(receipts) != len(set(receipts)):
        raise ValueError("Provider verdicts or receipts are not complete and unique")
    recomputed = score_bundle(modules, bundle, stored, artifact_id=str(selection["item_id"]), task_contract=task_contract)
    recomputed["weight_profile"] = default_weight
    if recomputed != score:
        raise ValueError("Provider score does not deterministically reconstruct")
    return stored, score, receipts


def _selection(frozen: Mapping[str, Any], phase: str) -> list[Mapping[str, Any]]:
    base = frozen["selection"]["partitions"]["development" if phase in {"development", "repeatability"} else "confirmatory"]
    if phase == "repeatability":
        wanted = {row["item_id"] for row in frozen["selection"]["repeatability"]["items"]}
        return [row for row in base if row["item_id"] in wanted]
    return base


def verify_primary_phase(data: Path, frozen: Mapping[str, Any], phase: str, output: Path) -> list[dict[str, Any]]:
    """Reconstruct a primary GPT phase before using it as a provider baseline."""
    if phase not in {"development", "confirmatory"}:
        raise ValueError("Only primary development or confirmatory output can be a paired baseline")
    primary_work = Path(frozen["primary_work_dir"])
    primary_frozen = _read(primary_work / "frozen-run-contract.json")
    if primary_frozen.get("study_id") != "hbq-human-alignment-v3" or primary_frozen.get("runtime_sha256") != frozen["primary_protocol"]["runtime_sha256"]:
        raise ValueError("Primary baseline work does not bind the exact frozen GPT protocol")
    PRIMARY_STUDY.validate_dataset_binding(data, primary_frozen)
    PRIMARY_ANALYSIS.verify_phase_runs(primary_work, primary_frozen, phase)
    base = primary_frozen["partitions"][phase]
    items = {item.item_id: item for item in PRIMARY_STUDY.load_hanna_items(data)}
    records: list[dict[str, Any]] = []
    for selection in base:
        item = items.get(selection["item_id"])
        if item is None or item.model != selection["model"] or item.story_sha256 != selection["story_sha256"] or item.prompt_sha256 != selection["prompt_sha256"]:
            raise ValueError("Primary baseline HANNA metadata does not match its frozen selection")
        verdicts, score = PRIMARY_ANALYSIS.verify_run(primary_work, primary_frozen, phase, selection, 1)
        folder = primary_work / "inputs" / phase / selection["item_id"]
        records.append(PRIMARY_ANALYSIS.record_for(item, selection, verdicts, score, (folder / "source.md").read_text(encoding="utf-8"), (folder / "prompt.md").read_text(encoding="utf-8"), primary_frozen["mapping_sets"]))
    items_path, summary_path, manifest_path = output / "items.jsonl", output / "summary.json", output / "manifest.json"
    expected_items = "".join(json.dumps(row, sort_keys=True) + "\n" for row in records)
    if items_path.read_text(encoding="utf-8") != expected_items:
        raise ValueError("Primary phase items do not deterministically reconstruct from frozen GPT runs/data")
    summary, manifest = _read(summary_path), _read(manifest_path)
    expected_macro = PRIMARY_ANALYSIS.macro_cluster_bootstrap([row for row in records if row["source_model"] != "Human"], int(primary_frozen["selection"]["seed"]))
    if summary.get("format_version") != 3 or summary.get("study_id") != "hbq-human-alignment-v3" or summary.get("phase") != phase or summary.get("study_contract_sha256") != primary_frozen["study_contract_sha256"] or summary.get("runtime_sha256") != primary_frozen["runtime_sha256"] or summary.get("item_count") != 88 or summary.get("primary_generated_only", {}).get("macro_spearman") != expected_macro:
        raise ValueError("Primary phase summary does not deterministically reconstruct from frozen GPT runs/data")
    expected_manifest = {"format_version": 3, "study_id": "hbq-human-alignment-v3", "phase": phase, "study_contract_sha256": primary_frozen["study_contract_sha256"], "runtime_sha256": primary_frozen["runtime_sha256"], "package_commit": primary_frozen["package_commit"], "files": {path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": sha(path)} for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}}
    if manifest != expected_manifest:
        raise ValueError("Primary phase manifest does not bind its reconstructed public artifacts")
    return records


def verify_phase(work: Path, frozen: Mapping[str, Any], provider_id: str, phase: str) -> list[str]:
    seen: set[str] = set()
    expected_paths: set[Path] = set()
    repetitions = frozen["selection"]["repeatability"]["repetitions"] if phase == "repeatability" else 1
    for row in _selection(frozen, phase):
        for number in range(1, repetitions + 1):
            expected_paths.add(work / "runs" / provider_id / phase / str(row["item_id"]) / f"run-{number:02d}" / "run.json")
            _, _, receipts = verify_run(work, frozen, provider_id, phase, row, number)
            overlap = seen & set(receipts)
            if overlap:
                raise ValueError("Provider receipt/session proof is reused across supplementary runs")
            seen.update(receipts)
    actual_paths = set((work / "runs" / provider_id / phase).glob("*/run-*/run.json"))
    if actual_paths != expected_paths:
        raise ValueError("Provider phase has unmanifested, missing, or mislocated runs")
    return sorted(seen)


def verify_study_receipts(work: Path, frozen: Mapping[str, Any], provider_id: str) -> None:
    all_receipts: set[str] = set()
    for phase in PHASES:
        root = work / "runs" / provider_id / phase
        if not root.exists():
            continue
        receipts = verify_phase(work, frozen, provider_id, phase)
        overlap = all_receipts & set(receipts)
        if overlap:
            raise ValueError("Provider receipt/session proof is reused across supplemental phases")
        all_receipts.update(receipts)


def _records(data: Path, work: Path, frozen: Mapping[str, Any], provider_id: str, phase: str) -> list[dict[str, Any]]:
    items = {item.item_id: item for item in PRIMARY_STUDY.load_hanna_items(data)}
    records: list[dict[str, Any]] = []
    if phase == "repeatability":
        return records
    for selection in _selection(frozen, phase):
        metadata = frozen["rating_metadata"].get(str(selection["item_id"]))
        item = items.get(selection["item_id"])
        if item is None or metadata != {"story_id": item.story_id, "model": item.model, "story_sha256": item.story_sha256, "prompt_sha256": item.prompt_sha256, "ratings_sha256": hashlib.sha256(canonical(item.ratings)).hexdigest()}:
            raise ValueError("Analysis item is not the exact frozen HANNA rating/model record")
        verdicts, score, _ = verify_run(work, frozen, provider_id, phase, selection, 1)
        folder, _ = primary_input(frozen, phase, str(selection["item_id"]))
        records.append(PRIMARY_ANALYSIS.record_for(item, selection, verdicts, score, (folder / "source.md").read_text(encoding="utf-8"), (folder / "prompt.md").read_text(encoding="utf-8"), frozen["selection"]["mapping_sets"]))
    return records


def _repeatability(work: Path, frozen: Mapping[str, Any], provider_id: str) -> dict[str, Any]:
    per_item: list[dict[str, Any]] = []
    leaves: list[list[str]] = []
    for selection in _selection(frozen, "repeatability"):
        runs = [verify_run(work, frozen, provider_id, "repeatability", selection, number) for number in range(1, 6)]
        scores = [float(score["final_score"]["observed"]) for _, score, _ in runs]
        columns = list(zip(*[[row["verdict"] for row in verdicts] for verdicts, _, _ in runs]))
        leaves.extend([list(column) for column in columns])
        per_item.append({"item_id": selection["item_id"], "source_model": selection["model"], "exact_all_five_leaf_agreement": statistics.fmean(len(set(column)) == 1 for column in columns), "score": {"values": scores, "standard_deviation": statistics.stdev(scores), "range": max(scores) - min(scores)}})
    return {"item_count": 11, "repetitions": 5, "per_item": per_item, "leaf_exact_all_five_agreement": statistics.fmean(row["exact_all_five_leaf_agreement"] for row in per_item), "nominal_krippendorff_alpha": PRIMARY_STUDY.alpha_nominal(leaves), "within_item_score_standard_deviation": {"mean": statistics.fmean(row["score"]["standard_deviation"] for row in per_item), "maximum": max(row["score"]["standard_deviation"] for row in per_item)}}


def _paired_gpt_delta(records: list[Mapping[str, Any]], primary_items: Path, phase: str, frozen: Mapping[str, Any], data: Path) -> dict[str, Any]:
    output = primary_items.parent
    summary, manifest = _read(output / "summary.json"), _read(output / "manifest.json")
    primary = frozen["primary_protocol"]
    if primary_items.name != "items.jsonl" or summary.get("format_version") != 3 or summary.get("study_id") != "hbq-human-alignment-v3" or summary.get("phase") != phase or summary.get("study_contract_sha256") != primary["study_contract_sha256"] or summary.get("runtime_sha256") != primary["runtime_sha256"] or summary.get("item_count") != 88 or manifest.get("format_version") != 3 or manifest.get("study_id") != "hbq-human-alignment-v3" or manifest.get("phase") != phase or manifest.get("study_contract_sha256") != primary["study_contract_sha256"] or manifest.get("runtime_sha256") != primary["runtime_sha256"]:
        raise ValueError("Paired GPT items do not bind the matching frozen primary phase analysis")
    files = manifest.get("files")
    item_binding = files.get("items.jsonl") if isinstance(files, Mapping) else None
    if not isinstance(item_binding, Mapping) or item_binding.get("sha256") != sha(primary_items) or item_binding.get("bytes") != primary_items.stat().st_size:
        raise ValueError("Paired GPT item output is not bound by its primary analysis manifest")
    baseline = {row["item_id"]: row for row in verify_primary_phase(data, frozen, phase, output)}
    expected_ids = {row["item_id"] for row in _selection(frozen, phase)}
    if set(baseline) != expected_ids or any(row.get("prompt_group_id") != next(item["prompt_group_id"] for item in _selection(frozen, phase) if item["item_id"] == item_id) for item_id, row in baseline.items()):
        raise ValueError("Paired GPT items do not cover the exact frozen phase selection")
    pairs = [(row["prompt_group_id"], float(row["hbq_full_observed_score"]) - float(baseline[row["item_id"]]["hbq_full_observed_score"])) for row in records if row["item_id"] in baseline and isinstance(row.get("hbq_full_observed_score"), (int, float)) and isinstance(baseline[row["item_id"]].get("hbq_full_observed_score"), (int, float))]
    if len(pairs) != 88:
        raise ValueError("Paired GPT development result does not cover the exact 88-item selection")
    groups = sorted({group for group, _ in pairs}); randomizer = random.Random(560820 + 901)
    by_group = {group: [value for current, value in pairs if current == group] for group in groups}
    samples = sorted(statistics.fmean(value for group in groups for value in by_group[groups[randomizer.randrange(len(groups))]]) for _ in range(1000))
    values = [value for _, value in pairs]
    return {"phase": phase, "item_count": len(pairs), "statistic": "provider HBQ observed score minus GPT HBQ observed score", "cluster": "prompt_group_id", "estimate": statistics.fmean(values), "draws": 1000, "ci_95_low": samples[25], "ci_95_high": samples[974], "descriptive_only": True}


def _build_summary(data: Path, work: Path, frozen: Mapping[str, Any], provider_id: str, phase: str, *, gpt_phase_items: Path | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = _records(data, work, frozen, provider_id, phase)
    generated = [row for row in records if row["source_model"] != "Human"]
    dimensions = {key: PRIMARY_ANALYSIS.dimension_analysis(generated, key, int(frozen["selection"]["selection"]["seed"]) + index) for index, key in enumerate(PRIMARY_STUDY.RATING_DIMENSIONS)} if records else {}
    summary: dict[str, Any] = {"format_version": 1, "study_id": CONTRACT["study_id"], "provider_id": provider_id, "phase": phase, "supplemental_contract_sha256": sha(HERE / "study-contract.json"), "primary_frozen_sha256": frozen["primary_frozen"]["sha256"], "primary_runtime_sha256": frozen["primary_protocol"]["runtime_sha256"], "item_count": len(_selection(frozen, phase)), "primary_generated_only": {"item_count": len(generated), "dimensions": dimensions, "macro_spearman": PRIMARY_ANALYSIS.macro_cluster_bootstrap(generated, int(frozen["selection"]["selection"]["seed"])) if generated else None}, "repeatability": _repeatability(work, frozen, provider_id) if phase == "repeatability" else None, "interpretation_limits": CONTRACT["interpretation_limits"]}
    if phase in {"development", "confirmatory"}:
        if gpt_phase_items is None:
            raise ValueError(f"{phase.title()} analysis requires the matching frozen GPT phase items output for paired deltas")
        summary["paired_hbq_delta_vs_gpt"] = _paired_gpt_delta(records, gpt_phase_items, phase, frozen, data)
    return summary, records


def verify_phase_analysis(data: Path, work: Path, provider_id: str, phase: str, output: Path, *, gpt_phase_items: Path) -> dict[str, Any]:
    frozen = load_frozen(work)
    validate_dataset_and_metadata(data, frozen)
    verify_phase(work, frozen, provider_id, phase)
    verify_study_receipts(work, frozen, provider_id)
    expected, records = _build_summary(data, work, frozen, provider_id, phase, gpt_phase_items=gpt_phase_items)
    summary_path, items_path, manifest_path = output / "summary.json", output / "items.jsonl", output / "manifest.json"
    summary, manifest = _read(summary_path), _read(manifest_path)
    if summary != expected:
        raise ValueError("Supplemental phase summary does not deterministically recompute from frozen runs")
    expected_items = "".join(json.dumps(row, sort_keys=True) + "\n" for row in records)
    if items_path.read_text(encoding="utf-8") != expected_items:
        raise ValueError("Supplemental phase items are not the exact frozen-run derivation")
    expected_manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "provider_id": provider_id, "phase": phase, "supplemental_contract_sha256": sha(HERE / "study-contract.json"), "primary_frozen_sha256": frozen["primary_frozen"]["sha256"], "files": {path.name: _fingerprint(path) for path in output.iterdir() if path.is_file() and path.name != "manifest.json"}}
    if manifest != expected_manifest:
        raise ValueError("Supplemental phase manifest does not bind its recomputed public artifacts")
    return summary


def analyze(data: Path, work: Path, provider_id: str, phase: str, output: Path, *, gpt_phase_items: Path | None = None) -> None:
    if output.exists():
        raise ValueError("Refusing to merge supplementary analysis into an existing output")
    frozen = load_frozen(work)
    if phase not in PHASES:
        raise ValueError("Unknown supplemental phase")
    validate_dataset_and_metadata(data, frozen)
    verify_phase(work, frozen, provider_id, phase)
    verify_study_receipts(work, frozen, provider_id)
    summary, records = _build_summary(data, work, frozen, provider_id, phase, gpt_phase_items=gpt_phase_items)
    output.mkdir(parents=True)
    write_json(output / "summary.json", summary)
    (output / "items.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in records), encoding="utf-8")
    manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "provider_id": provider_id, "phase": phase, "supplemental_contract_sha256": sha(HERE / "study-contract.json"), "primary_frozen_sha256": frozen["primary_frozen"]["sha256"], "files": {path.name: _fingerprint(path) for path in output.iterdir() if path.is_file()}}
    write_json(output / "manifest.json", manifest)
    forbidden = [str(work), str(data), "Worker ID", "Assignment ID"]
    PRIMARY_ANALYSIS.assert_public_safe(output, forbidden)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--provider", choices=[item["provider_id"] for item in CONTRACT["providers"]], required=True)
    parser.add_argument("--phase", choices=PHASES, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--gpt-phase-items", type=Path)
    args = parser.parse_args()
    analyze(args.data_dir.resolve(), args.work_dir.resolve(), args.provider, args.phase, args.output_dir.resolve(), gpt_phase_items=args.gpt_phase_items.resolve() if args.gpt_phase_items else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
