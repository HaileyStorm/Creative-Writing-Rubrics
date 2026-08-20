#!/usr/bin/env python3
"""Analyze completed v2 runs without creating a cross-rubric quality score."""

from __future__ import annotations

import argparse
from collections import Counter
from itertools import combinations
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any, Iterable

from jsonschema import Draft202012Validator

from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.longform_runner import _json_bytes as _structured_json_bytes
from hbqrs.longform_runner import _parse_model_json
from hbqrs.longform_runner import _provider_response_schema
from hbqrs.paths import bundles_path, registry_path, schema_dir
from hbqrs.runner import _json_bytes as _runner_json_bytes
from hbqrs.runner import _load_checkpoints, _verdicts_bytes


HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))


def _study_runner():
    import importlib.util

    spec = importlib.util.spec_from_file_location("established_v2_runner", HERE / "run_study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schedule_sha256() -> str:
    return _study_runner().schedule_sha256(CONTRACT)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_journal(work: Path) -> list[dict[str, Any]]:
    runner = _study_runner()
    path = work / runner.JOURNAL_NAME
    records = runner._read_journal(path)
    plans = runner._schedule_events(CONTRACT)
    if len(records) != len(plans) * 2 or records[: len(plans)] != plans:
        raise ValueError("Schedule journal is missing planned events or does not bind to the frozen schedule")
    completions = records[len(plans):]
    for expected, actual in zip(plans, completions):
        expected_bindings = {key: value for key, value in expected.items() if key != "event"}
        actual_bindings = {key: actual.get(key) for key in expected_bindings}
        if actual.get("event") != "completed" or actual_bindings != expected_bindings or not isinstance(actual.get("run_binding_sha256"), str):
            raise ValueError("Schedule journal completion records are missing, duplicated, or reordered")
        arm = next(item for item in CONTRACT["arms"] if item["arm_id"] == expected["arm_id"])
        binding = work / arm["arm_id"] / expected["run_id"] / ("run.json" if arm["kind"] == "hbq" else "pass.json")
        if not binding.is_file() or _sha256(binding) != actual["run_binding_sha256"]:
            raise ValueError("Schedule journal completion does not bind to its run manifest")
    return completions


def _numeric(values: list[float]) -> dict[str, Any]:
    gaps = [abs(left - right) for left, right in combinations(values, 2)]
    return {"values": values, "mean": statistics.fmean(values), "sample_standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0, "minimum": min(values), "maximum": max(values), "range": max(values) - min(values), "mean_absolute_pairwise_difference": statistics.fmean(gaps) if gaps else 0.0}


def _alpha_nominal(rows: Iterable[list[str]]) -> float | None:
    rows = list(rows)
    all_labels: Counter[str] = Counter()
    pairs = disagreements = 0
    for row in rows:
        all_labels.update(row)
        for left, right in combinations(row, 2):
            pairs += 1
            disagreements += left != right
    if not pairs:
        return None
    observed = disagreements / pairs
    total = sum(all_labels.values())
    expected = sum(count * (total - count) for count in all_labels.values()) / (total * (total - 1))
    return 1.0 if expected == 0 and observed == 0 else (None if expected == 0 else 1.0 - observed / expected)


def _read_verdicts(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _hbq_metrics(work: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    arm = "hbq_short_story_one_batch"
    runs = [_read_verdicts(work / arm / f"run-{number:02d}" / "verdicts.jsonl") for number in range(1, 6)]
    ids = [item["question_id"] for item in runs[0]]
    if any([item["question_id"] for item in run] != ids for run in runs[1:]):
        raise ValueError("HBQ question order drifted")
    source = (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    leaves = []
    evidence: Counter[str] = Counter()
    invalid = 0
    verdict_count = 0
    verdicts_with_evidence = 0
    for index, question_id in enumerate(ids):
        labels = [run[index]["verdict"] for run in runs]
        leaves.append({"question_id": question_id, "labels": labels, "exact_all_run_agreement": len(set(labels)) == 1, "modal_label_proportion": max(Counter(labels).values()) / 5})
    for run in runs:
        for row in run:
            verdict_count += 1
            if row.get("evidence"):
                verdicts_with_evidence += 1
            for item in row.get("evidence", []):
                quote, summary = item.get("exact_quote"), item.get("summary")
                if isinstance(quote, str) and quote:
                    evidence["exact_quote"] += 1
                    invalid += quote not in source
                elif isinstance(summary, str) and summary:
                    evidence["summary"] += 1
                else:
                    evidence["untyped_or_empty"] += 1
    scores = [_json(work / arm / f"run-{number:02d}" / "score.json")["final_score"]["observed"] for number in range(1, 6)]
    if invalid:
        raise ValueError("HBQ exact-quote evidence is not grounded in the frozen source")
    typed_total = evidence["exact_quote"] + evidence["summary"]
    return {"question_count": len(ids), "exact_all_run_agreement_rate": statistics.fmean(item["exact_all_run_agreement"] for item in leaves), "mean_modal_label_proportion": statistics.fmean(item["modal_label_proportion"] for item in leaves), "nominal_krippendorff_alpha": _alpha_nominal([item["labels"] for item in leaves]), "observed_score": _numeric(scores), "typed_evidence": {"verdict_denominator": verdict_count, "verdicts_with_nonempty_typed_evidence": verdicts_with_evidence, "verdict_nonempty_typed_evidence_rate": verdicts_with_evidence / verdict_count if verdict_count else None, "evidence_item_denominator": typed_total + evidence["untyped_or_empty"], "typed_evidence_item_count": typed_total, "typed_evidence_item_rate": typed_total / (typed_total + evidence["untyped_or_empty"]) if typed_total + evidence["untyped_or_empty"] else None, "exact_quote_count": evidence["exact_quote"], "summary_count": evidence["summary"], "untyped_or_empty_count": evidence["untyped_or_empty"], "invalid_exact_quote_count": invalid, "exact_quote_denominator": evidence["exact_quote"], "exact_quote_grounded_rate": (evidence["exact_quote"] - invalid) / evidence["exact_quote"] if evidence["exact_quote"] else None}}, leaves


def _native_spec(arm: str) -> tuple[str, list[str], int | None]:
    if arm == "naplan_narrative_2022":
        return "criteria", ["audience", "text_structure", "ideas", "character_and_setting", "vocabulary", "cohesion", "paragraphing", "sentence_structure", "punctuation", "spelling"], 47
    if arm == "cambridge_igcse_0500_p2_mj_2024":
        return "components", ["content_and_structure", "style_and_accuracy"], 40
    if arm == "oregon_narrative_2017":
        return "traits", ["ideas_and_content", "organization", "voice", "word_choice", "sentence_fluency", "conventions"], 36
    raise ValueError(arm)


def _native_metrics(work: Path, arm: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    runs = [_json(work / arm / f"run-{number:02d}" / "result.json") for number in range(1, 6)]
    collection, expected, maximum = _native_spec(arm)
    source = (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    key_name = {"criteria": "criterion_id", "components": "component_id", "traits": "trait_id"}[collection]
    values: dict[str, list[int]] = {key: [] for key in expected}
    quotes: list[str] = []
    totals: list[int] = []
    for run in runs:
        keyed = {item[key_name]: item for item in run[collection]}
        if set(keyed) != set(expected) or len(run[collection]) != len(expected):
            raise ValueError(f"{arm} output set drifted")
        total = sum(item["score"] for item in keyed.values())
        if run["total_score"] != total or not 0 <= total <= maximum:
            raise ValueError(f"{arm} total is not the native sum")
        totals.append(total)
        for key, item in keyed.items():
            values[key].append(item["score"])
            quotes.append(item["exact_quote"])
    criteria = {key: {"values": score, "exact_all_run_agreement": len(set(score)) == 1, "modal_score_proportion": max(Counter(score).values()) / 5} for key, score in values.items()}
    if any(quote not in source for quote in quotes):
        raise ValueError(f"{arm} exact quote is not grounded in the frozen source")
    return {"criterion_count": len(expected), "criterion_exact_all_run_agreement_rate": statistics.fmean(item["exact_all_run_agreement"] for item in criteria.values()), "criterion_mean_modal_score_proportion": statistics.fmean(item["modal_score_proportion"] for item in criteria.values()), "criteria": criteria, "total_score": _numeric(totals), "exact_quote_grounded_rate": statistics.fmean(quote in source for quote in quotes)}, runs


def _provider(record: dict[str, Any]) -> dict[str, Any]:
    reported = record.get("provider", {}).get("reported", {})
    return {"provider": reported.get("provider"), "model": reported.get("model"), "reasoning_effort": reported.get("reasoning_effort")}


def _reported_session(record: dict[str, Any]) -> str:
    session = record.get("provider", {}).get("reported", {}).get("session_id")
    if not isinstance(session, str) or not session:
        raise ValueError("Run lacks a provider-reported session ID needed to prove fresh sessions")
    return session


def _expect_provider(record: dict[str, Any]) -> str:
    if _provider(record) != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider identity or reasoning effort drifted")
    return _reported_session(record)


def _validate_hbq_run(work: Path, number: int) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    arm = "hbq_short_story_one_batch"
    path = work / arm / f"run-{number:02d}"
    manifest = _json(path / "run.json")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, dict) or manifest.get("config_sha256") != hashlib.sha256(_runner_json_bytes(configuration)).hexdigest():
        raise ValueError("HBQ run manifest configuration binding is invalid")
    hbq = CONTRACT["hbq_runtime"]
    expected_ids = _study_runner()._question_sequence()
    if configuration.get("bundle_id") != hbq["bundle_id"] or configuration.get("question_ids") is None:
        raise ValueError("HBQ run has wrong bundle or no selected questions")
    ids = configuration["question_ids"]
    if (len(ids), hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()) != expected_ids:
        raise ValueError("HBQ run does not use the exact frozen 178-question order")
    if configuration.get("artifact_id") != "the-part-that-arrives-first" or configuration.get("provider") != "codex" or configuration.get("model") != "gpt-5.6-sol" or configuration.get("reasoning") != "high" or configuration.get("batch_size") != 256 or configuration.get("strict_ai") is not True:
        raise ValueError("HBQ run configuration drifted")
    artifact = configuration.get("artifact", {})
    if artifact.get("sha256") != CONTRACT["source"]["sha256"] or artifact.get("bytes") != CONTRACT["source"]["bytes"]:
        raise ValueError("HBQ run artifact does not bind to the frozen source")
    prompt_hashes = {item.get("sha256") for item in configuration.get("prompts", [])}
    if not {CONTRACT["asset_hashes"]["binary_prompt"], CONTRACT["asset_hashes"]["judge_prefix"]}.issubset(prompt_hashes) or configuration.get("response_schema", {}).get("sha256") != CONTRACT["asset_hashes"]["response_schema"]:
        raise ValueError("HBQ run prompt or response schema drifted")
    source = (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    checkpointed, checkpoint_count, _ = _load_checkpoints(path, artifact_text=source, context_texts=[])
    if checkpoint_count != 1 or checkpointed != _read_verdicts(path / "verdicts.jsonl") or [item.get("question_id") for item in checkpointed] != ids:
        raise ValueError("HBQ checkpoints are incomplete, unordered, or disagree with verdicts.jsonl")
    responses = sorted((path / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
    if len(responses) != 1:
        raise ValueError("One-batch HBQ arm must have exactly one response checkpoint")
    checkpoint = _json(responses[0])
    if checkpoint.get("format_version") != 2 or any(not verdict.get("evidence") for verdict in checkpointed):
        raise ValueError("HBQ study requires format-version-2 checkpoints with nonempty typed evidence")
    session = _expect_provider(checkpoint)
    score = _json(path / "score.json")
    score_schema = _json(schema_dir() / "hbq_score_report.schema.json")
    errors = sorted(Draft202012Validator(score_schema).iter_errors(score), key=lambda error: list(error.absolute_path))
    if errors or score.get("artifact_id") != "the-part-that-arrives-first" or score.get("bundle_id") != hbq["bundle_id"] or not isinstance(score.get("status"), str):
        raise ValueError("HBQ score report is invalid")
    bundle = resolve_bundle(load_bundles(bundles_path()), hbq["bundle_id"])
    recomputed = score_bundle(load_modules(registry_path()), bundle, checkpointed, artifact_id="the-part-that-arrives-first")
    persisted = {key: value for key, value in score.items() if key != "weight_profile"}
    if recomputed != persisted:
        raise ValueError("HBQ score.json does not match deterministic recomputation from verdicts")
    return checkpointed, score, session


def _validate_native_run(work: Path, arm: dict[str, Any], number: int) -> tuple[dict[str, Any], str]:
    path = work / arm["arm_id"] / f"run-{number:02d}"
    schema = _json(HERE / arm["schema"])
    result = _json(path / "result.json")
    errors = sorted(Draft202012Validator(schema).iter_errors(result), key=lambda error: list(error.absolute_path))
    if errors:
        raise ValueError(f"{arm['arm_id']} result violates frozen schema: {errors[0].message}")
    manifest = _json(path / "pass.json")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, dict) or manifest.get("config_sha256") != hashlib.sha256(_structured_json_bytes(configuration)).hexdigest():
        raise ValueError(f"{arm['arm_id']} pass configuration binding is invalid")
    study = _study_runner()
    prompt = study._prompt((HERE / arm["prompt"]).read_text(encoding="utf-8"), (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8"))
    if configuration.get("name") != f"{arm['arm_id']}-run-{number:02d}" or configuration.get("provider") != "codex" or configuration.get("model") != "gpt-5.6-sol" or configuration.get("reasoning") != "high" or configuration.get("prompt_sha256") != hashlib.sha256(prompt.encode("utf-8")).hexdigest() or configuration.get("schema_sha256") != hashlib.sha256(_structured_json_bytes(schema)).hexdigest():
        raise ValueError(f"{arm['arm_id']} pass configuration drifted")
    response = _json(path / "response.json")
    content = response.get("content")
    if not isinstance(content, str) or response.get("content_sha256") != hashlib.sha256(content.encode("utf-8")).hexdigest():
        raise ValueError(f"{arm['arm_id']} response content hash is invalid")
    try:
        parsed = _parse_model_json(content)
    except Exception as exc:
        raise ValueError(f"{arm['arm_id']} response content is not parseable JSON") from exc
    parsed_errors = sorted(Draft202012Validator(schema).iter_errors(parsed), key=lambda error: list(error.absolute_path))
    if parsed_errors or parsed != result:
        raise ValueError(f"{arm['arm_id']} accepted result does not exactly match parsed response content")
    if response.get("config_sha256") != manifest["config_sha256"] or response.get("prompt_sha256") != configuration["prompt_sha256"] or response.get("schema_sha256") != configuration["schema_sha256"] or response.get("result_sha256") != hashlib.sha256(_structured_json_bytes(parsed)).hexdigest():
        raise ValueError(f"{arm['arm_id']} result is not bound to its accepted response")
    saved_schema = _json(path / "response.schema.json")
    if saved_schema != _provider_response_schema(schema):
        raise ValueError(f"{arm['arm_id']} provider schema drifted")
    return result, _expect_provider(response)


def _copy_and_prove(work: Path, output: Path, arm: dict[str, Any]) -> list[dict[str, Any]]:
    proofs = []
    for number in range(1, 6):
        run_id = f"run-{number:02d}"
        source = work / arm["arm_id"] / run_id
        target = output / arm["arm_id"]
        target.mkdir(parents=True, exist_ok=True)
        if arm["kind"] == "hbq":
            for name in ("verdicts.jsonl", "score.json"):
                path = target / f"{run_id}-{name}"
                path.write_bytes((source / name).read_bytes())
            responses = [_provider(_json(path)) for path in sorted((source / "responses").glob("batch-*.json"))]
            if not responses or len({json.dumps(item, sort_keys=True) for item in responses}) != 1:
                raise ValueError("HBQ provider provenance drift")
            proofs.append({"run_id": run_id, "reported_provider": responses[0], "verdicts_sha256": _sha256(target / f"{run_id}-verdicts.jsonl"), "score_sha256": _sha256(target / f"{run_id}-score.json")})
        else:
            path = target / f"{run_id}.json"
            _write_json(path, _json(source / "result.json"))
            proofs.append({"run_id": run_id, "reported_provider": _provider(_json(source / "response.json")), "result_sha256": _sha256(path)})
    return proofs


def _svg(title: str, description: str, body: str, height: int) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="{height}" viewBox="0 0 960 {height}" role="img" aria-labelledby="t d"><title id="t">{title}</title><desc id="d">{description}</desc><style>text{{font-family:system-ui,sans-serif;fill:#172033}}.muted{{fill:#58657a}}.grid{{stroke:#d8dee8}}.a{{fill:#536dfe}}.b{{fill:#e07a5f}}.c{{fill:#2a9d8f}}.d{{fill:#8d5fd3}}</style><rect width="960" height="{height}" fill="#fbfcff"/>{body}</svg>'


def _charts(summary: dict[str, Any], output: Path) -> None:
    panels = [("HBQ-RS observed score", summary["arms"]["hbq_short_story_one_batch"]["observed_score"]["values"], 100, "a"), ("NAPLAN implementation total", summary["arms"]["naplan_narrative_2022"]["total_score"]["values"], 47, "b"), ("Cambridge implementation total", summary["arms"]["cambridge_igcse_0500_p2_mj_2024"]["total_score"]["values"], 40, "c"), ("Oregon implementation total", summary["arms"]["oregon_narrative_2017"]["total_score"]["values"], 36, "d")]
    body = ['<text x="40" y="42" font-size="26" font-weight="700">Five scores per native numeric scale</text>', '<text x="40" y="68" class="muted" font-size="15">Positions are not cross-rubric quality comparisons.</text>']
    for index, (label, values, high, css) in enumerate(panels):
        y = 120 + index * 105
        body += [f'<text x="40" y="{y}" font-size="17" font-weight="600">{label}</text>', f'<line x1="320" y1="{y - 6}" x2="860" y2="{y - 6}" class="grid"/>', f'<text x="320" y="{y + 20}" class="muted" font-size="13">0</text>', f'<text x="845" y="{y + 20}" class="muted" font-size="13">{high}</text>']
        for run, value in enumerate(values, start=1):
            body.append(f'<circle cx="{320 + 540 * value / high:.1f}" cy="{y - 6 + (run - 3) * 5}" r="7" class="{css}"><title>run {run}: {value}</title></circle>')
        body.append(f'<text x="40" y="{y + 42}" class="muted" font-size="13">SD {statistics.stdev(values):.3f} · range {max(values) - min(values):.3f}</text>')
    _write_text(output / "score-distributions.svg", _svg("Native-scale repeatability", "Four separate numeric-scale panels show five scores each.", "".join(body), 540))
    agreement = [("HBQ leaves", summary["arms"]["hbq_short_story_one_batch"]["exact_all_run_agreement_rate"], "a"), ("NAPLAN criteria", summary["arms"]["naplan_narrative_2022"]["criterion_exact_all_run_agreement_rate"], "b"), ("Cambridge components", summary["arms"]["cambridge_igcse_0500_p2_mj_2024"]["criterion_exact_all_run_agreement_rate"], "c"), ("Oregon traits", summary["arms"]["oregon_narrative_2017"]["criterion_exact_all_run_agreement_rate"], "d")]
    body = ['<text x="40" y="42" font-size="26" font-weight="700">Exact all-five-run agreement</text>', '<text x="40" y="68" class="muted" font-size="15">Coarser output designs can agree more easily.</text>']
    for index, (label, value, css) in enumerate(agreement):
        y = 120 + index * 75
        body += [f'<text x="40" y="{y}" font-size="16" font-weight="600">{label}</text>', f'<rect x="320" y="{y - 22}" width="520" height="28" fill="#e8ecf3"/>', f'<rect x="320" y="{y - 22}" width="{520 * value:.1f}" height="28" class="{css}"/>', f'<text x="860" y="{y}" font-size="15">{value:.1%}</text>']
    _write_text(output / "agreement.svg", _svg("Exact agreement by output unit", "Bars show exact agreement for each method’s native output units.", "".join(body), 410))


def analyze(work: Path, output: Path) -> None:
    frozen, _ = _study_runner().preflight()
    if frozen != CONTRACT:
        raise ValueError("Analyzer contract differs from the frozen execution contract")
    if output.exists():
        raise ValueError("Refusing to merge into or overwrite an existing analysis output directory")
    output.mkdir(parents=True)
    arms: dict[str, Any] = {}
    leaves: list[dict[str, Any]] = []
    contract_hash = _sha256(HERE / "study-contract.json")
    schedule_hash = _schedule_sha256()
    journal = _validate_journal(work)
    provenance = {"format_version": 1, "study_id": CONTRACT["study_id"], "source_sha256": CONTRACT["source"]["sha256"], "protocol_contract_sha256": contract_hash, "schedule_sha256": schedule_hash, "analysis_code_sha256": CONTRACT["asset_hashes"]["study_analyzer"], "asset_hashes": CONTRACT["asset_hashes"], "schedule": CONTRACT["schedule"], "schedule_journal_commitment_sha256": hashlib.sha256(_structured_json_bytes(journal)).hexdigest(), "arms": {}}
    all_sessions: list[str] = []
    for arm in CONTRACT["arms"]:
        sessions: list[str] = []
        if arm["kind"] == "hbq":
            for number in range(1, 6):
                _, _, session = _validate_hbq_run(work, number)
                sessions.append(session)
            metrics, details = _hbq_metrics(work)
        else:
            for number in range(1, 6):
                _, session = _validate_native_run(work, arm, number)
                sessions.append(session)
            metrics, details = _native_metrics(work, arm["arm_id"])
        if len(sessions) != 5 or len(set(sessions)) != 5:
            raise ValueError(f"{arm['arm_id']} does not prove five distinct fresh provider sessions")
        all_sessions.extend(sessions)
        if arm["kind"] == "hbq":
            leaves = details
        arms[arm["arm_id"]] = metrics
        proofs = _copy_and_prove(work, output, arm)
        expected = {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}
        if any(item["reported_provider"] != expected for item in proofs):
            raise ValueError(f"Provider identity or reasoning drifted in {arm['arm_id']}")
        provenance["arms"][arm["arm_id"]] = {"native_scale": arm["native_scale"], "runs": proofs}
    if len(all_sessions) != 20 or len(set(all_sessions)) != 20:
        raise ValueError("Study does not prove 20 globally unique accepted provider sessions")
    session_hashes = sorted(hashlib.sha256(session.encode("utf-8")).hexdigest() for session in all_sessions)
    provenance["fresh_session_commitment"] = {"session_count": 20, "unique_session_count": 20, "commitment_sha256": hashlib.sha256(("\n".join(session_hashes) + "\n").encode("utf-8")).hexdigest()}
    summary = {"format_version": 1, "study_id": CONTRACT["study_id"], "protocol_contract_sha256": contract_hash, "schedule_sha256": schedule_hash, "repetitions": 5, "native_scales_are_not_cross_compared": True, "arms": arms}
    _write_json(output / "summary.json", summary)
    _write_json(output / "hbq-leaf-repeatability.json", {"leaves": leaves})
    _write_json(output / "provenance.json", provenance)
    _charts(summary, output)
    _write_text(output / "comparison.md", "# Completed comparison\n\nThe charts retain native scales. HBQ-RS exposes 178 binary leaves and typed evidence; the established arms expose fewer native outputs. Exact agreement therefore describes repeatability within each output design, not a common quality scale. Interpret diagnostic resolution and coarse-scale stability together, and do not infer validity from repeatability alone.\n")
    files = {path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": _sha256(path)} for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    _write_json(output / "manifest.json", {"format_version": 1, "protocol_contract_sha256": contract_hash, "schedule_sha256": schedule_hash, "analysis_code_sha256": CONTRACT["asset_hashes"]["study_analyzer"], "files": files})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.work_dir.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
