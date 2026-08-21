#!/usr/bin/env python3
"""Verify current runner provenance and publish prose-free HANNA v3 results."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import statistics
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Mapping, Sequence

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, VALIDATION_FEEDBACK_POLICY, _json_bytes, _load_checkpoints, _question_payload, _render_prompt
from hbqrs.weights import materialize_weight_profile
from study import HERE, RATING_DIMENSIONS, alpha_nominal, fetch_or_verify_dataset, load_hanna_items, mapping_sets, privacy_forbidden_strings, sha256_path, validate_dataset_binding, validate_external_inputs, validate_frozen_contract, write_json


def _load_v2_analysis() -> Any:
    path = HERE.parent / "hbq-human-alignment-v2" / "analyze_study.py"
    spec = importlib.util.spec_from_file_location("hbq_hanna_v2_analysis", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("HANNA v2 analysis helpers are unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    compatibility = sys.modules.get("study")
    if compatibility is None:
        raise RuntimeError("HANNA v3 study module is unavailable")
    injected = {name: getattr(compatibility, name, None) for name in ("rank", "pearson", "spearman")}
    for name, value in (("rank", compatibility._v2.rank), ("pearson", compatibility._v2.pearson), ("spearman", compatibility._v2.spearman)):
        setattr(compatibility, name, value)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, prior in injected.items():
            if prior is None:
                delattr(compatibility, name)
            else:
                setattr(compatibility, name, prior)
    return module


_v2 = _load_v2_analysis()
write_text = _v2.write_text
read_json = _v2.read_json
read_verdicts = _v2.read_verdicts
verdict_bytes = _v2.verdict_bytes
checkpoint_files = _v2.checkpoint_files
typed_evidence_metrics = _v2.typed_evidence_metrics
derive_mapping = _v2.derive_mapping
record_for = _v2.record_for
dimension_analysis = _v2.dimension_analysis
macro_cluster_bootstrap = _v2.macro_cluster_bootstrap
source_model_strata = _v2.source_model_strata
ordinal_agreement = _v2.ordinal_agreement
repeatability_svg = _v2.repeatability_svg
correlation_svg = _v2.correlation_svg
comparison_svg = _v2.comparison_svg
assert_public_safe = _v2.assert_public_safe
strings = _v2.strings


def _retry_policy(frozen: Mapping[str, Any]) -> dict[str, int]:
    value = frozen.get("runner", {}).get("batch_attempts")
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("Frozen batch retry policy is invalid")
    return {"batch_attempts": value}


def _fingerprint(frozen: Mapping[str, Any], suffix: str) -> Mapping[str, Any]:
    matches = [value for key, value in frozen["runtime_files"].items() if key.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"Frozen runtime fingerprint missing or ambiguous: {suffix}")
    return matches[0]


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, dict) else None


def _session_commitment(record: Mapping[str, Any]) -> str:
    provider = record.get("provider")
    if not isinstance(provider, Mapping):
        raise ValueError("Accepted checkpoint lacks provider provenance")
    reported = provider.get("reported")
    if not isinstance(reported, Mapping):
        raise ValueError("Accepted checkpoint lacks reported provider settings")
    session_id = reported.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    session_hash = provider.get("session_id_sha256")
    if isinstance(session_hash, str) and len(session_hash) == 64:
        return session_hash
    raise ValueError("Accepted checkpoint lacks a session commitment")


def _expected_records(frozen: Mapping[str, Any], configuration: Mapping[str, Any], task_contract: Mapping[str, Any]) -> tuple[Any, Any, list[dict[str, Any]], list[str], Mapping[str, Any]]:
    audit = configuration.get("weight_profile")
    if not isinstance(audit, Mapping) or "requested" not in audit:
        raise ValueError("Run lacks an effective weight-profile audit")
    source_modules = load_modules(registry_path())
    source_bundle = resolve_bundle(load_bundles(bundles_path()), frozen["runner"]["bundle_id"])
    modules, bundle, expected_audit = materialize_weight_profile(source_modules, source_bundle, audit["requested"])
    if dict(audit) != expected_audit:
        raise ValueError("Run effective weight profile is not reproducible from its requested profile")
    _, _, default_audit = materialize_weight_profile(source_modules, source_bundle, None)
    frozen_weight_policy = frozen["runner"].get("weight_profile")
    if not isinstance(frozen_weight_policy, Mapping) or frozen_weight_policy.get("requested") is not None or frozen_weight_policy.get("identity") is not True or audit["requested"] is not None or audit.get("identity") is not True or dict(audit) != default_audit:
        raise ValueError("Run does not use the exact frozen default weight profile")
    compiled = compile_bundle(modules, bundle, task_contract=task_contract)
    records = sorted(compiled_questions(compiled), key=lambda item: {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}.get(str(item.get("role")), 99))
    return modules, bundle, records, [str(item["question"]["id"]) for item in records], expected_audit


def verify_run(work: Path, frozen: Mapping[str, Any], phase: str, row: Mapping[str, Any], repetition: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    partition = "development" if phase in {"development", "repeatability"} else "confirmatory"
    folder = work / "runs" / phase / row["item_id"] / f"run-{repetition:02d}"
    manifest = read_json(folder / "run.json")
    score = read_json(folder / "score.json")
    stored_rows = read_verdicts(folder / "verdicts.jsonl")
    configuration = manifest.get("configuration")
    policy = _retry_policy(frozen)
    if manifest.get("format_version") != 3 or not isinstance(configuration, Mapping) or not isinstance(score.get("status"), str):
        raise ValueError(f"Malformed manifest-v3/status for {row['item_id']}")
    if manifest.get("config_sha256") != hashlib.sha256(_json_bytes(configuration)).hexdigest():
        raise ValueError(f"Config hash mismatch for {row['item_id']}")
    if configuration.get("retry_policy") != policy or configuration.get("retry_semantics") != "cumulative_batch_attempts_v1" or configuration.get("evidence_normalization_policy") != EVIDENCE_NORMALIZATION_POLICY or configuration.get("validation_feedback_policy") != VALIDATION_FEEDBACK_POLICY:
        raise ValueError(f"Current retry/normalization policy mismatch for {row['item_id']}")
    inputs = row["external_input"]
    contexts = configuration.get("contexts")
    if not isinstance(contexts, list) or len(contexts) != 1:
        raise ValueError(f"Run must bind exactly one HANNA prompt context for {row['item_id']}")
    if _compact(configuration.get("artifact")) != inputs["source.md"] or _compact(contexts[0]) != inputs["prompt.md"] or _compact(configuration.get("task_contract")) != inputs["task-contract.json"] or configuration.get("task_contract", {}).get("contract_id") != "hanna":
        raise ValueError(f"Run input provenance mismatch for {row['item_id']}")
    task_contract = read_json(work / "inputs" / partition / row["item_id"] / "task-contract.json")
    modules, bundle, records, expected, expected_audit = _expected_records(frozen, configuration, task_contract)
    expected_judge = f"{frozen['provider']['provider']}:{frozen['provider']['model']}"
    if configuration.get("artifact_id") != row["item_id"] or task_contract.get("artifact_id") != row["item_id"] or configuration.get("bundle_id") != frozen["runner"]["bundle_id"] or configuration.get("bundle_version") != bundle.get("version") or configuration.get("judge_id") != expected_judge:
        raise ValueError(f"Run identity mismatch for {row['item_id']}")
    if configuration.get("weight_profile") != expected_audit or expected_audit.get("identity") is not (expected_audit.get("requested") is None or not any(expected_audit.get("requested", {}).get(key) for key in ("domain_weights", "component_weights", "group_weights", "question_weights", "penalty_caps"))):
        raise ValueError(f"Run identity/effective weight profile mismatch for {row['item_id']}")
    if expected != frozen["question_ids"] or configuration.get("question_ids") != expected or configuration.get("questions_sha256") != hashlib.sha256(_json_bytes(_question_payload(records))).hexdigest() or configuration.get("compiled_bundle_sha256") != hashlib.sha256(_json_bytes(compile_bundle(modules, bundle, task_contract=task_contract))).hexdigest():
        raise ValueError(f"Compiled bundle/hash mismatch for {row['item_id']}")
    prompt_fingerprint = _fingerprint(frozen, "prompts/judge/BINARY_EVALUATION_PROMPT.md")
    schema_fingerprint = _fingerprint(frozen, "schema/hbq_judge_response.schema.json")
    if [_compact(item) for item in configuration.get("prompts", [])] != [prompt_fingerprint] or _compact(configuration.get("response_schema")) != schema_fingerprint:
        raise ValueError(f"Prompt/schema fingerprint mismatch for {row['item_id']}")
    expected_provider = {"provider": "openai", "model": frozen["provider"]["model"], "reasoning_effort": frozen["provider"]["reasoning"]}
    if configuration.get("provider") != frozen["provider"]["provider"] or configuration.get("model") != frozen["provider"]["model"] or configuration.get("reasoning") != frozen["provider"]["reasoning"] or configuration.get("strict_ai") is not False or configuration.get("batch_size") != frozen["runner"]["batch_size"]:
        raise ValueError(f"Run settings mismatch for {row['item_id']}")
    source = (work / "inputs" / partition / row["item_id"] / "source.md").read_text(encoding="utf-8")
    prompt = (work / "inputs" / partition / row["item_id"] / "prompt.md").read_text(encoding="utf-8")
    binary_prompt = (HERE.parent.parent / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8")
    expected_prompts = [
        _render_prompt(
            binary_prompt=binary_prompt,
            artifact={"name": configuration["artifact"]["name"], "text": source},
            contexts=[{"name": contexts[0]["name"], "text": prompt}],
            bundle_id=configuration["bundle_id"], artifact_id=configuration["artifact_id"],
            questions=records[offset:offset + frozen["runner"]["batch_size"]],
        ).encode("utf-8")
        for offset in range(0, len(records), frozen["runner"]["batch_size"])
    ]
    for number, expected_prompt in enumerate(expected_prompts, 1):
        checkpoint = folder / "responses" / f"batch-{number:04d}.json"
        prompt_path = checkpoint.with_suffix(".prompt.txt.gz")
        try:
            observed_prompt = gzip.decompress(prompt_path.read_bytes())
        except (OSError, EOFError) as exc:
            raise ValueError(f"Prompt checkpoint is unreadable for {row['item_id']}") from exc
        if observed_prompt != expected_prompt:
            raise ValueError(f"Prompt checkpoint does not match the exact frozen batch for {row['item_id']}")
    try:
        checkpointed, count, _ = _load_checkpoints(folder, artifact_text=source, context_texts=[prompt], batch_attempts=policy["batch_attempts"], normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError(f"Checkpoint-v4 provenance failed for {row['item_id']}: {exc}") from exc
    checkpoints = checkpoint_files(folder)
    expected_batches = (len(expected) + frozen["runner"]["batch_size"] - 1) // frozen["runner"]["batch_size"]
    if count != expected_batches or len(checkpoints) != expected_batches:
        raise ValueError(f"Expected {expected_batches} ordered checkpoints for {row['item_id']}")
    sessions: list[str] = []
    previous: str | None = None
    for number, checkpoint in enumerate(checkpoints, 1):
        record = read_json(checkpoint)
        base_prompt = gzip.decompress(checkpoint.with_suffix(".prompt.txt.gz").read_bytes())
        expected_ids = expected[(number - 1) * frozen["runner"]["batch_size"]:number * frozen["runner"]["batch_size"]]
        if record.get("format_version") != 4 or record.get("batch") != number or record.get("question_ids") != expected_ids or record.get("previous_checkpoint_sha256") != previous or record.get("base_prompt_sha256") != hashlib.sha256(base_prompt).hexdigest() or record.get("prompt_sha256") != hashlib.sha256(base_prompt).hexdigest():
            raise ValueError(f"Checkpoint-v4 chain mismatch for {row['item_id']}")
        reported = record.get("provider", {}).get("reported", {})
        if {key: reported.get(key) for key in expected_provider} != expected_provider:
            raise ValueError(f"Reported provider mismatch for {row['item_id']}")
        sessions.append(_session_commitment(record))
        previous = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if checkpointed != stored_rows or [item.get("question_id") for item in stored_rows] != expected:
        raise ValueError(f"Checkpoint/verdict order mismatch for {row['item_id']}")
    recomputed = score_bundle(modules, bundle, stored_rows, artifact_id=row["item_id"], task_contract=task_contract)
    recomputed["weight_profile"] = configuration.get("weight_profile")
    if recomputed != score:
        raise ValueError(f"Deterministic score mismatch for {row['item_id']}")
    score["provenance"] = {
        "manifest_version": 3, "checkpoint_version": 4,
        "runtime_sha256": frozen["runtime_sha256"],
        "retry_policy": policy, "accepted_checkpoint_count": count,
        "session_commitments": sessions,
    }
    return stored_rows, score


def verify_phase_runs(work: Path, frozen: Mapping[str, Any], phase: str) -> None:
    source_rows = frozen["repeatability"]["items"] if phase == "repeatability" else frozen["partitions"][phase]
    all_sessions: list[tuple[str, set[str]]] = []
    for selected in source_rows:
        row = selected if phase != "repeatability" else next(item for item in frozen["partitions"]["development"] if item["item_id"] == selected["item_id"])
        repetitions = frozen["repeatability"]["repetitions"] if phase == "repeatability" else 1
        for number in range(1, repetitions + 1):
            _, score = verify_run(work, frozen, phase, row, number)
            commitments = list(score["provenance"]["session_commitments"])
            if not commitments or len(commitments) != len(set(commitments)):
                raise ValueError(f"Run requires unique provider sessions within every batch for {row['item_id']}")
            sessions = set(commitments)
            if not sessions:
                raise ValueError(f"Run lacks a session commitment for {row['item_id']}")
            all_sessions.append((f"{phase}/{row['item_id']}/run-{number:02d}", sessions))
    if frozen["provider"].get("fresh_session") is True:
        for (left_label, left), (right_label, right) in combinations(all_sessions, 2):
            if left & right:
                raise ValueError(f"Fresh-session protocol requires pairwise disjoint run sessions: {left_label} and {right_label}")
        for other_phase in ("development", "repeatability", "confirmatory"):
            if other_phase == phase:
                continue
            other_rows = frozen["repeatability"]["items"] if other_phase == "repeatability" else frozen["partitions"][other_phase]
            for selected in other_rows:
                row = selected if other_phase != "repeatability" else next(item for item in frozen["partitions"]["development"] if item["item_id"] == selected["item_id"])
                repetitions = frozen["repeatability"]["repetitions"] if other_phase == "repeatability" else 1
                for number in range(1, repetitions + 1):
                    folder = work / "runs" / other_phase / row["item_id"] / f"run-{number:02d}"
                    if not (folder / "run.json").is_file():
                        continue
                    _, score = verify_run(work, frozen, other_phase, row, number)
                    commitments = list(score["provenance"]["session_commitments"])
                    if not commitments or len(commitments) != len(set(commitments)):
                        raise ValueError(f"Run requires unique provider sessions within every batch for {row['item_id']}")
                    sessions = set(commitments)
                    for left_label, left in all_sessions:
                        if left & sessions:
                            raise ValueError(f"Fresh-session protocol requires study-wide disjoint run sessions: {left_label} and {other_phase}/{row['item_id']}/run-{number:02d}")


def repeatability_metrics(work: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    all_leaves: list[tuple[dict[str, Any], ...]] = []
    per_item: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    retries: list[dict[str, Any]] = []
    for selected in frozen["repeatability"]["items"]:
        row = next(item for item in frozen["partitions"]["development"] if item["item_id"] == selected["item_id"])
        folder = work / "inputs" / "development" / row["item_id"]
        source, prompt = (folder / "source.md").read_text(encoding="utf-8"), (folder / "prompt.md").read_text(encoding="utf-8")
        runs: list[list[dict[str, Any]]] = []
        values: list[float] = []
        session_sets: list[set[str]] = []
        for number in range(1, frozen["repeatability"]["repetitions"] + 1):
            verdicts, score = verify_run(work, frozen, "repeatability", row, number)
            runs.append(verdicts)
            evidence.append(typed_evidence_metrics(verdicts, source, prompt))
            observed = score.get("final_score", {}).get("observed")
            if isinstance(observed, (int, float)):
                values.append(float(observed))
            sessions = set(score["provenance"]["session_commitments"])
            session_sets.append(sessions)
            response_records = [read_json(path) for path in checkpoint_files(work / "runs" / "repeatability" / row["item_id"] / f"run-{number:02d}")]
            retries.append({"accepted_attempts": [record["accepted_attempt"] for record in response_records], "rejected_attempt_count": sum(record["rejected_chain"]["count"] for record in response_records)})
        columns = list(zip(*runs))
        all_leaves.extend(columns)
        standard_deviation = statistics.stdev(values) if len(values) > 1 else 0.0
        per_item.append({"item_id": row["item_id"], "source_model": row["model"], "exact_all_five_leaf_agreement": statistics.fmean(len({item["verdict"] for item in column}) == 1 for column in columns), "score": {"values": values, "standard_deviation": standard_deviation, "range": max(values) - min(values) if values else None}, "session_commitment": {"repetition_session_counts": [len(value) for value in session_sets], "total_distinct_sessions": len(set().union(*session_sets)), "globally_disjoint": not any(left & right for left, right in combinations(session_sets, 2))}})
    if len(frozen["repeatability"]["items"]) != 11:
        raise ValueError("Frozen repeatability summary must contain exactly 11 items")
    keys = ("total", "typed_schema_conformant", "exact_quote", "exact_quote_grounded", "summary", "untyped", "empty")
    sums = {key: sum(item[key] for item in evidence) for key in keys}
    deviations = [item["score"]["standard_deviation"] for item in per_item]
    ranges = [item["score"]["range"] for item in per_item if item["score"]["range"] is not None]
    return {"item_count": 11, "repetitions": frozen["repeatability"]["repetitions"], "per_item": per_item, "leaf_exact_all_five_agreement": statistics.fmean(item["exact_all_five_leaf_agreement"] for item in per_item), "nominal_krippendorff_alpha": alpha_nominal([[item["verdict"] for item in column] for column in all_leaves]), "within_item_score_standard_deviation": {"mean": statistics.fmean(deviations), "maximum": max(deviations), "minimum": min(deviations)}, "within_item_score_range": {"mean": statistics.fmean(ranges) if ranges else None, "maximum": max(ranges) if ranges else None}, "retry_provenance": {"policy": _retry_policy(frozen), "accepted_run_count": len(retries), "rejected_attempt_count": sum(item["rejected_attempt_count"] for item in retries), "rejected_run_count": sum(item["rejected_attempt_count"] > 0 for item in retries), "excluded_from_repetition_metrics": True}, "evidence": {"total": sums["total"], "typed_schema_conformant": sums["typed_schema_conformant"], "typed_schema_conformance_rate": sums["typed_schema_conformant"] / sums["total"] if sums["total"] else None, "exact_quote": sums["exact_quote"], "exact_quote_grounded": sums["exact_quote_grounded"], "exact_quote_grounded_rate": sums["exact_quote_grounded"] / sums["exact_quote"] if sums["exact_quote"] else None, "summary": sums["summary"], "summary_prevalence": sums["summary"] / sums["total"] if sums["total"] else None, "untyped": sums["untyped"], "empty": sums["empty"]}}


def verify_development_analysis(work: Path, frozen: Mapping[str, Any], output: Path) -> None:
    """Require a complete semantic development result, not merely two matching files."""
    verify_phase_runs(work, frozen, "development")
    manifest_path, summary_path, items_path = output / "manifest.json", output / "summary.json", output / "items.jsonl"
    if not manifest_path.is_file() or not summary_path.is_file() or not items_path.is_file():
        raise ValueError("Development analysis is incomplete")
    manifest, summary = read_json(manifest_path), read_json(summary_path)
    expected_manifest = {"format_version": 3, "study_id": frozen["study_id"], "phase": "development", "study_contract_sha256": frozen["study_contract_sha256"], "runtime_sha256": frozen["runtime_sha256"], "package_commit": frozen["package_commit"]}
    if any(manifest.get(key) != value for key, value in expected_manifest.items()):
        raise ValueError("Development analysis manifest does not bind the frozen v3 protocol")
    expected_files = {path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": sha256_path(path)} for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    if manifest.get("files") != expected_files:
        raise ValueError("Development analysis manifest file commitments do not verify")
    required_summary = {
        "format_version": 3, "study_id": frozen["study_id"], "phase": "development",
        "study_contract_sha256": frozen["study_contract_sha256"], "runtime_sha256": frozen["runtime_sha256"],
        "mapping_sets": frozen["mapping_sets"], "dataset": frozen["dataset"], "item_count": 88,
        "published_human_agreement_context": frozen["protocol"]["published_human_agreement_context"],
    }
    if any(summary.get(key) != value for key, value in required_summary.items()):
        raise ValueError("Development analysis summary does not bind the complete v3 protocol")
    primary, secondary = summary.get("primary_generated_only"), summary.get("secondary_all_11")
    if not isinstance(primary, Mapping) or primary.get("item_count") != 80 or not isinstance(secondary, Mapping) or secondary.get("item_count") != 88:
        raise ValueError("Development analysis lacks primary generated-only or all-11 secondary results")
    for section in (primary, secondary):
        dimensions = section.get("dimensions")
        if not isinstance(dimensions, Mapping) or set(dimensions) != set(RATING_DIMENSIONS) or not isinstance(section.get("ordinal_human_agreement"), Mapping):
            raise ValueError("Development analysis lacks six-dimensional human-alignment metrics")
    if not isinstance(primary.get("macro_spearman"), Mapping):
        raise ValueError("Development analysis lacks generated-only macro correlation")
    strata = summary.get("source_model_strata")
    if not isinstance(strata, Mapping) or len(strata) != frozen["selection"]["models"] or any(not isinstance(value, Mapping) or not isinstance(value.get("dimensions"), Mapping) or set(value["dimensions"]) != set(RATING_DIMENSIONS) for value in strata.values()):
        raise ValueError("Development analysis lacks source-model strata")
    rows = [json.loads(line) for line in items_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_rows = frozen["partitions"]["development"]
    if len(rows) != 88 or {row.get("item_id") for row in rows} != {row["item_id"] for row in expected_rows}:
        raise ValueError("Development analysis items do not cover the frozen 88-item selection")
    for row in rows:
        if any(key in row for key in ("story", "prompt", "run_id", "provider")):
            raise ValueError("Development analysis item output is not prose/session safe")


def analyze(data: Path, work: Path, output: Path, phase: str) -> None:
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    frozen = validate_frozen_contract(work)
    validate_dataset_binding(data, frozen)
    validate_external_inputs(work, frozen)
    verify_phase_runs(work, frozen, phase)
    base = frozen["partitions"]["development" if phase in {"development", "repeatability"} else "confirmatory"]
    selections = [next(row for row in base if row["item_id"] == repeat["item_id"]) for repeat in frozen["repeatability"]["items"]] if phase == "repeatability" else base
    items = {item.item_id: item for item in load_hanna_items(data)}
    records = []
    if phase != "repeatability":
        partition = "development" if phase == "development" else "confirmatory"
        for selection in selections:
            verdicts, score = verify_run(work, frozen, phase, selection, 1)
            folder = work / "inputs" / partition / selection["item_id"]
            records.append(record_for(items[selection["item_id"]], selection, verdicts, score, (folder / "source.md").read_text(encoding="utf-8"), (folder / "prompt.md").read_text(encoding="utf-8"), frozen["mapping_sets"]))
    generated = [row for row in records if row["source_model"] != "Human"]
    if records and len(generated) != 80:
        raise ValueError(f"Primary generated-only slice must contain 80 items, found {len(generated)}")
    dimensions = {key: dimension_analysis(generated, key, frozen["selection"]["seed"] + index) for index, key in enumerate(RATING_DIMENSIONS)} if generated else {}
    all_dimensions = {key: dimension_analysis(records, key, frozen["selection"]["seed"] + 100 + index) for index, key in enumerate(RATING_DIMENSIONS)} if records else {}
    generated_items = [items[row["item_id"]] for row in selections if row["model"] != "Human"]
    selected_human = ordinal_agreement(generated_items) if phase != "repeatability" else {}
    all_human = ordinal_agreement([items[row["item_id"]] for row in selections]) if phase != "repeatability" else {}
    repeated = repeatability_metrics(work, frozen) if phase == "repeatability" else None
    summary = {"format_version": 3, "study_id": frozen["study_id"], "phase": phase, "study_contract_sha256": frozen["study_contract_sha256"], "runtime_sha256": frozen["runtime_sha256"], "dataset": frozen["dataset"], "mapping_sets": mapping_sets(), "item_count": len(selections) if phase == "repeatability" else len(records), "primary_generated_only": {"item_count": len(generated), "dimensions": dimensions, "macro_spearman": macro_cluster_bootstrap(generated, frozen["selection"]["seed"]) if generated else None, "ordinal_human_agreement": selected_human}, "secondary_all_11": {"item_count": len(records), "dimensions": all_dimensions, "ordinal_human_agreement": all_human}, "source_model_strata": source_model_strata(records) if records else {}, "published_human_agreement_context": frozen["protocol"]["published_human_agreement_context"], "repeatability": repeated, "interpretation_limits": ["Only already-published HANNA ratings are used; no new human judging occurs.", "HANNA is human-reference context, not literary ground truth."]}
    output.mkdir(parents=True)
    write_json(output / "summary.json", summary)
    write_text(output / "items.jsonl", "".join(json.dumps(row, sort_keys=True) + "\n" for row in records))
    if dimensions:
        write_text(output / "dimension-correlations.svg", correlation_svg(dimensions))
        write_text(output / "human-reference-comparison.svg", comparison_svg(dimensions, selected_human))
    if repeated:
        write_json(output / "repeatability.json", repeated)
        write_text(output / "repeatability.svg", repeatability_svg(repeated))
    write_json(output / "manifest.json", {"format_version": 3, "study_id": frozen["study_id"], "phase": phase, "study_contract_sha256": frozen["study_contract_sha256"], "runtime_sha256": frozen["runtime_sha256"], "package_commit": frozen["package_commit"], "files": {path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": sha256_path(path)} for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}})
    forbidden = [str(work), "Worker ID", "Assignment ID", *privacy_forbidden_strings(data)]
    for item in [items[row["item_id"]] for row in selections]:
        forbidden.extend([item.story, item.prompt])
    for run in (work / "runs" / phase).rglob("run.json"):
        manifest = read_json(run)
        forbidden.append(str(manifest.get("run_id", "")))
        for checkpoint in checkpoint_files(run.parent):
            forbidden.extend(strings(read_json(checkpoint).get("provider", {})))
    assert_public_safe(output, forbidden)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("development", "repeatability", "confirmatory"))
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.data_dir.resolve(), args.work_dir.resolve(), args.output_dir.resolve(), args.phase)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
