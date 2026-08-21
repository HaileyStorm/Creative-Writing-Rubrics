#!/usr/bin/env python3
"""Fail-closed analysis for established-rubric comparison v3."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.longform_runner import _json_bytes as _structured_json_bytes, _parse_model_json, _provider_response_schema
from hbqrs.paths import bundles_path, registry_path, schema_dir
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, _json_bytes as _runner_json_bytes, _load_checkpoints, _validate_provider_artifacts


HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))


def _runner():
    spec = importlib.util.spec_from_file_location("established_v3_runner", HERE / "run_study.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _v2_helper():
    path = HERE.parent / "established-v2" / "analyze_study.py"
    spec = importlib.util.spec_from_file_location("established_v3_v2_metrics", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HERE = HERE
    module.CONTRACT = CONTRACT
    module._study_runner = _runner
    return module


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _provider(record: dict[str, Any]) -> dict[str, Any]:
    reported = record.get("provider", {}).get("reported", {})
    return {"provider": reported.get("provider"), "model": reported.get("model"), "reasoning_effort": reported.get("reasoning_effort")}


def _session(record: dict[str, Any]) -> str:
    if _provider(record) != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Provider identity or reasoning effort drifted")
    value = record.get("provider", {}).get("reported", {}).get("session_id")
    if not isinstance(value, str) or not value:
        raise ValueError("Accepted response lacks a provider-reported session ID")
    return value


def _require_unique_sessions(sessions: list[str], expected: int) -> None:
    if len(sessions) != expected or len(set(sessions)) != expected:
        raise ValueError("Study does not prove globally unique accepted provider sessions")


def _validate_journal(work: Path) -> list[dict[str, Any]]:
    runner = _runner()
    plans = runner._schedule_events(CONTRACT)
    records = runner._read_journal(work / runner.JOURNAL_NAME)
    if len(records) != 2 * len(plans) or records[:len(plans)] != plans:
        raise ValueError("Schedule journal is missing planned events or does not bind to the frozen schedule")
    completions = records[len(plans):]
    for expected, actual in zip(plans, completions):
        if actual.get("event") != "completed" or {key: actual.get(key) for key in expected if key != "event"} != {key: value for key, value in expected.items() if key != "event"} or not isinstance(actual.get("run_binding_sha256"), str):
            raise ValueError("Schedule journal completion records are missing, duplicated, or reordered")
        arm = next(item for item in CONTRACT["arms"] if item["arm_id"] == expected["arm_id"])
        binding = work / arm["arm_id"] / expected["run_id"] / ("run.json" if arm["kind"] == "hbq" else "pass.json")
        if not binding.is_file() or _sha256(binding) != actual["run_binding_sha256"]:
            raise ValueError("Schedule journal completion does not bind to its run manifest")
    return completions


def _validate_hbq_run(work: Path, number: int) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    runner, runtime = _runner(), CONTRACT["hbq_runtime"]
    path = work / "hbq_short_story_batch32" / f"run-{number:02d}"
    manifest = _json(path / "run.json")
    configuration = manifest.get("configuration")
    if manifest.get("format_version") != 3 or not isinstance(configuration, dict) or manifest.get("config_sha256") != hashlib.sha256(_runner_json_bytes(configuration)).hexdigest():
        raise ValueError("HBQ v3 manifest configuration binding is invalid")
    required = {"bundle_id": runtime["bundle_id"], "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 32, "strict_ai": True, "artifact_id": "the-part-that-arrives-first", "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "evidence_normalization_policy": EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": "validation_feedback_retry_v1"}
    if any(configuration.get(key) != value for key, value in required.items()):
        raise ValueError("HBQ v3 configuration drifted")
    artifact = configuration.get("artifact", {})
    if artifact.get("sha256") != CONTRACT["source"]["sha256"] or artifact.get("bytes") != CONTRACT["source"]["bytes"]:
        raise ValueError("HBQ run artifact does not bind to the frozen source")
    ids = configuration.get("question_ids")
    if not isinstance(ids, list) or (len(ids), hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()) != runner._question_sequence():
        raise ValueError("HBQ run does not use the exact frozen 178-question order")
    prompt_hashes = {item.get("sha256") for item in configuration.get("prompts", []) if isinstance(item, dict)}
    assets = runner._asset_manifest(CONTRACT)["assets"]
    if not {assets["binary_prompt"]["sha256"], assets["judge_prefix"]["sha256"]}.issubset(prompt_hashes) or configuration.get("response_schema", {}).get("sha256") != assets["response_schema"]["sha256"]:
        raise ValueError("HBQ prompt or schema hash drifted")
    source = (HERE / CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    try:
        checkpointed, count, _ = _load_checkpoints(path, artifact_text=source, context_texts=[], batch_attempts=3, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("HBQ checkpoint/retry/normalization replay failed") from exc
    verdict_path = path / "verdicts.jsonl"
    verdicts = [json.loads(line) for line in verdict_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if count != 6 or checkpointed != verdicts or [item.get("question_id") for item in checkpointed] != ids:
        raise ValueError("HBQ checkpoints are incomplete, unordered, or disagree with verdicts.jsonl")
    checkpoints = sorted((path / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
    if len(checkpoints) != 6:
        raise ValueError("HBQ batch32 arm must have exactly six response checkpoints")
    sessions: list[str] = []
    previous: str | None = None
    for batch, checkpoint_path in enumerate(checkpoints, start=1):
        record = _json(checkpoint_path)
        chunk = ids[(batch - 1) * 32:batch * 32]
        if record.get("format_version") != 4 or record.get("batch") != batch or record.get("question_ids") != chunk or record.get("previous_checkpoint_sha256") != previous:
            raise ValueError("HBQ checkpoint does not bind the v4 ordered batch chain")
        if record.get("normalization_policy") != EVIDENCE_NORMALIZATION_POLICY or record.get("validation_feedback_policy") != "validation_feedback_retry_v1" or record.get("retry_policy") != {"batch_attempts": 3}:
            raise ValueError("HBQ checkpoint policy drifted")
        response = record.get("response_artifact")
        if not isinstance(response, dict) or not isinstance(response.get("path"), str):
            raise ValueError("HBQ checkpoint lacks an accepted response artifact")
        raw = path / response["path"]
        if not raw.is_file() or response.get("bytes") != raw.stat().st_size or response.get("sha256") != _sha256(raw) or record.get("response_sha256") != _sha256(raw):
            raise ValueError("HBQ checkpoint accepted response artifact is unbound")
        sessions.append(_session(record))
        previous = _sha256(checkpoint_path)
    score = _json(path / "score.json")
    schema = _json(schema_dir() / "hbq_score_report.schema.json")
    if list(Draft202012Validator(schema).iter_errors(score)):
        raise ValueError("HBQ score report violates the frozen schema")
    bundle = resolve_bundle(load_bundles(bundles_path()), runtime["bundle_id"])
    recomputed = score_bundle(load_modules(registry_path()), bundle, checkpointed, artifact_id="the-part-that-arrives-first")
    if {key: value for key, value in score.items() if key != "weight_profile"} != recomputed:
        raise ValueError("HBQ score.json does not match deterministic recomputation from verdicts")
    return checkpointed, score, sessions


def _validate_native_run(work: Path, arm: dict[str, Any], number: int) -> tuple[dict[str, Any], str]:
    helper = _v2_helper()
    path = work / arm["arm_id"] / f"run-{number:02d}"
    result, session = helper._validate_native_run(work, arm, number)
    manifest = _json(path / "pass.json")
    if manifest.get("format_version") != 1:
        raise ValueError(f"{arm['arm_id']} structured-pass manifest version drifted")
    response = _json(path / "response.json")
    try:
        _validate_provider_artifacts(path, response)
    except Exception as exc:
        raise ValueError(f"{arm['arm_id']} provider artifacts are unbound") from exc
    return result, session


def _copy_and_prove(work: Path, output: Path, arm: dict[str, Any]) -> list[dict[str, Any]]:
    return _v2_helper()._copy_and_prove(work, output, arm)


def _retry_provenance(work: Path) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    for number in range(1, 6):
        base = work / "hbq_short_story_batch32" / f"run-{number:02d}" / "responses"
        checkpoints = [_json(path) for path in sorted(base.glob("batch-[0-9][0-9][0-9][0-9].json"))]
        rejected = list((base / "rejected").glob("batch-[0-9][0-9][0-9][0-9]/attempt-[0-9][0-9][0-9][0-9].json")) if (base / "rejected").is_dir() else []
        runs.append({
            "accepted_checkpoint_count": len(checkpoints),
            "accepted_attempts": [item.get("accepted_attempt") for item in checkpoints],
            "rejected_attempt_count": len(rejected),
            "rejected_batches": sorted({int(_json(path)["batch"]) for path in rejected}),
            "recovered_acceptance_count": sum(isinstance(item.get("recovered_from_rejected"), dict) for item in checkpoints),
            "normalization_repair_count": sum(len(item.get("normalization_audit", [])) for item in checkpoints),
        })
    return {
        "policy": {"batch_attempts": 3, "retry_semantics": "cumulative_batch_attempts_v1", "evidence_normalization_policy": EVIDENCE_NORMALIZATION_POLICY},
        "accepted_run_count": len(runs),
        "rejected_attempt_count": sum(item["rejected_attempt_count"] for item in runs),
        "rejected_run_count": sum(item["rejected_attempt_count"] > 0 for item in runs),
        "recovered_acceptance_count": sum(item["recovered_acceptance_count"] for item in runs),
        "normalization_repair_count": sum(item["normalization_repair_count"] for item in runs),
        "runs": runs,
        "excluded_from_repeatability_metrics": True,
    }


def analyze(work: Path, output: Path) -> None:
    runner = _runner()
    frozen, _ = runner.preflight()
    if frozen != CONTRACT:
        raise ValueError("Analyzer contract differs from frozen execution contract")
    if output.exists():
        raise ValueError("Refusing to merge into or overwrite an existing analysis output directory")
    output.mkdir(parents=True)
    journal = _validate_journal(work)
    helper = _v2_helper()
    arms: dict[str, Any] = {}
    all_sessions: list[str] = []
    provenance: dict[str, Any] = {"format_version": 3, "study_id": CONTRACT["study_id"], "source_sha256": CONTRACT["source"]["sha256"], "protocol_contract_sha256": _sha256(HERE / "study-contract.json"), "schedule_sha256": runner.schedule_sha256(CONTRACT), "asset_manifest": CONTRACT["asset_manifest"], "schedule_journal_commitment_sha256": hashlib.sha256(_structured_json_bytes(journal)).hexdigest(), "arms": {}}
    leaves: list[dict[str, Any]] = []
    for arm in CONTRACT["arms"]:
        sessions: list[str] = []
        if arm["kind"] == "hbq":
            for number in range(1, 6):
                _, _, run_sessions = _validate_hbq_run(work, number)
                sessions.extend(run_sessions)
            metrics, leaves = helper._hbq_metrics(work)
            metrics["retry_provenance"] = _retry_provenance(work)
        else:
            for number in range(1, 6):
                _, session = _validate_native_run(work, arm, number)
                sessions.append(session)
            metrics, _ = helper._native_metrics(work, arm["arm_id"])
        expected = 30 if arm["kind"] == "hbq" else 5
        _require_unique_sessions(sessions, expected)
        all_sessions.extend(sessions)
        proofs = _copy_and_prove(work, output, arm)
        provenance["arms"][arm["arm_id"]] = {"native_scale": arm["native_scale"], "runs": proofs, **({"retry_provenance": metrics["retry_provenance"]} if arm["kind"] == "hbq" else {})}
        arms[arm["arm_id"]] = metrics
    _require_unique_sessions(all_sessions, 45)
    hashes = sorted(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in all_sessions)
    provenance["fresh_session_commitment"] = {"session_count": 45, "unique_session_count": 45, "commitment_sha256": hashlib.sha256(("\n".join(hashes) + "\n").encode("utf-8")).hexdigest()}
    summary = {"format_version": 3, "study_id": CONTRACT["study_id"], "protocol_contract_sha256": provenance["protocol_contract_sha256"], "schedule_sha256": provenance["schedule_sha256"], "repetitions": 5, "native_scales_are_not_cross_compared": True, "arms": arms}
    _write_json(output / "summary.json", summary)
    _write_json(output / "hbq-leaf-repeatability.json", {"leaves": leaves})
    _write_json(output / "provenance.json", provenance)
    helper._charts(summary, output)
    _write_text(output / "comparison.md", "# Completed comparison\n\nEach method remains on its own native scale. This v3 analysis validates replayable evidence normalization and cumulative retry feedback before calculating repeatability; it does not turn agreement into a shared quality ranking.\n")
    files = {path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": _sha256(path)} for path in sorted(output.rglob("*")) if path.is_file() and path.name != "manifest.json"}
    _write_json(output / "manifest.json", {"format_version": 3, "protocol_contract_sha256": provenance["protocol_contract_sha256"], "schedule_sha256": provenance["schedule_sha256"], "files": files})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.work_dir.resolve(), args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
