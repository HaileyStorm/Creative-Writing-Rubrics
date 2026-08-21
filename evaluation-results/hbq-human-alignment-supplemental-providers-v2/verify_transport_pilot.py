#!/usr/bin/env python3
"""Verify pilot transport evidence without reading score files or HANNA ratings."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir
from hbqrs import runner as runner_module
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, _json_bytes, _load_checkpoints, _render_prompt, _validate_provider_artifacts
from hbqrs.weights import materialize_weight_profile

from study import CONTRACT, fingerprint, input_folder, load_frozen, read_json, runtime_bindings, sha


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None


def _timely(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < CONTRACT["transport_pilot"]["maximum_completion_seconds_exclusive"]


_BRIDGE: Any | None = None


def _bridge() -> Any:
    global _BRIDGE
    if _BRIDGE is None:
        path = runner_module.NOUS_LAUNCHER_PATH.parent / "nous_codex_bridge.py"
        spec = importlib.util.spec_from_file_location("hanna_supplemental_v2_bridge", path)
        if spec is None or spec.loader is None:
            raise ValueError("Canonical Nous bridge is unavailable for raw evidence validation")
        _BRIDGE = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = _BRIDGE
        spec.loader.exec_module(_BRIDGE)
    return _BRIDGE


def _inside(root: Path, path: Path) -> Path:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Raw Nous evidence path escapes its pilot run") from exc
    return path


def _artifact(run: Path, path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": path.relative_to(run).as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _tree(run: Path, root: Path) -> dict[str, Any]:
    entries = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(root.rglob("*")) if path.is_file()]
    return {"path": root.relative_to(run).as_posix(), "files": len(entries), "sha256": hashlib.sha256(_json_bytes(entries)).hexdigest()}


def _bridge_hash(value: Any) -> str:
    bridge = _bridge()
    return str(bridge.sha256_bytes(bridge.canonical_bytes(value)))


def _invocation(work: Path) -> dict[str, Any]:
    from run_transport_pilot import _invocation
    record = read_json(work / "pilot-invocation.json")
    frozen = load_frozen(work)
    try:
        expected = _invocation(work, frozen, 600)
    except ValueError as exc:
        raise ValueError("Pilot invocation record does not bind the current protocol/runtime") from exc
    if record != expected:
        raise ValueError("Pilot invocation record does not bind the current protocol/runtime")
    return record


def _claim(work: Path) -> dict[str, Any]:
    path = work / "pilot-execution-claim.json"
    if not path.is_file():
        raise ValueError("Pilot exclusive execution claim is missing, forged, or unbound")
    record = read_json(path)
    expected = {
        "format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_score_blind_pilot_execution",
        "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"),
        "frozen_contract_sha256": sha(work / "frozen-transport-contract.json"), "runtime": runtime_bindings(),
    }
    if any(record.get(key) != value for key, value in expected.items()) or isinstance(record.get("pid"), bool) or not isinstance(record.get("pid"), int) or record["pid"] < 1 or set(record) != {*expected, "pid"}:
        raise ValueError("Pilot exclusive execution claim is missing, forged, or unbound")
    return record


def _expected_prompt(folder: Path, cell: Mapping[str, Any]) -> bytes:
    task_contract = read_json(folder / "task-contract.json")
    modules, bundle, _ = materialize_weight_profile(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    compiled = compile_bundle(modules, bundle, task_contract=task_contract)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    wanted = list(cell["question_ids"])
    selected = [item for item in questions if item["question"]["id"] in set(wanted)]
    if [item["question"]["id"] for item in selected] != wanted:
        raise ValueError("Pilot question sequence cannot be rendered exactly")
    return _render_prompt(
        binary_prompt=(prompts_dir() / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8"),
        artifact={"name": "source.md", "text": (folder / "source.md").read_text(encoding="utf-8")},
        contexts=[{"name": "prompt.md", "text": (folder / "prompt.md").read_text(encoding="utf-8")}],
        bundle_id="prose.short_story", artifact_id=str(cell["item_id"]), questions=selected,
    ).encode("utf-8")


def _raw_transport(run: Path, checkpoint: Mapping[str, Any], prompt: bytes) -> dict[str, Any]:
    """Bind the bridge result, HMAC-sealed evidence receipt, and raw HTTP ledger directly."""
    provider = checkpoint.get("provider")
    if not isinstance(provider, Mapping):
        raise ValueError("Pilot checkpoint lacks a provider receipt")
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}:
        raise ValueError("Pilot checkpoint lacks the complete Nous raw-artifact inventory")
    request = run / "responses" / "batch-0001.attempt-0001.nous.request.json"
    result = run / "responses" / "batch-0001.attempt-0001.nous.result.json"
    evidence_root = run / "responses" / "batch-0001.attempt-0001.nous.evidence"
    if not request.is_file() or not result.is_file() or not evidence_root.is_dir():
        raise ValueError("Pilot raw Nous artifacts are missing")
    expected_artifacts = {"judge_request": _artifact(run, request), "judge_result": _artifact(run, result), "evidence_tree": _tree(run, evidence_root)}
    raw = read_json(result)
    metadata, response = raw.get("metadata"), raw.get("result")
    if raw.get("schema") != "codex-nous-tool-free-judge-result-v1" or not isinstance(metadata, Mapping) or not isinstance(response, Mapping):
        raise ValueError("Pilot raw Nous result is malformed")
    accepted = checkpoint.get("response_artifact")
    if not isinstance(accepted, Mapping) or not isinstance(accepted.get("path"), str):
        raise ValueError("Pilot checkpoint lacks its accepted response artifact")
    accepted_path = _inside(run, run / str(accepted["path"]))
    accepted_bytes = accepted_path.read_bytes() if accepted_path.is_file() else None
    if accepted_bytes is None or dict(accepted) != _artifact(run, accepted_path) or checkpoint.get("response_sha256") != hashlib.sha256(accepted_bytes).hexdigest():
        raise ValueError("Pilot checkpoint accepted response artifact is unbound")
    try:
        accepted_response = json.loads(accepted_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Pilot checkpoint accepted response is not JSON") from exc
    if accepted_response != response:
        raise ValueError("Pilot checkpoint accepted response diverges from the raw Nous result")
    proof_path = _inside(evidence_root, Path(str(metadata.get("serialization_proof_path", ""))))
    evidence_path = _inside(evidence_root, Path(str(metadata.get("evidence_path", ""))))
    if not proof_path.is_file() or not evidence_path.is_dir():
        raise ValueError("Pilot raw Nous result lacks its proof/evidence receipt")
    expected_artifacts["serialization_proof"] = _artifact(run, proof_path)
    if dict(artifacts) != expected_artifacts:
        raise ValueError("Pilot checkpoint artifacts do not commit the exact raw Nous artifacts")
    try:
        _validate_provider_artifacts(run, checkpoint)
        validation = _bridge().validate_evidence(evidence_path)
        proof = _bridge().serialization_proof_status(evidence_root, str(proof_path), expected_sha256=metadata.get("serialization_proof_sha256"))
    except Exception as exc:
        raise ValueError("Pilot raw Nous evidence receipt/proof is invalid") from exc
    if validation.get("valid") is not True or metadata.get("evidence_validation") != validation or not proof.valid:
        raise ValueError("Pilot raw Nous evidence receipt/proof is not replay-valid")
    raw_request = read_json(request)
    expected_request = {
        "schema": "codex-nous-tool-free-judge-request-v1", "model": CONTRACT["provider"]["model"], "reasoning_effort": "max",
        "messages": [{"role": "system", "content": "You are a careful HBQ-RS evaluator. Do not use tools or reveal chain-of-thought."}, {"role": "user", "content": prompt.decode("utf-8")}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "hbqrs_judge", "strict": True, "schema": read_json(schema_dir() / "hbq_judge_response.schema.json")}},
    }
    if raw_request != expected_request:
        raise ValueError("Pilot raw Nous request does not bind the effective rendered prompt")
    bridge_run_manifest = read_json(evidence_path / "manifest.json")
    bridge_receipt = read_json(evidence_path / "receipt.json")
    events = [json.loads(line) for line in (evidence_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    attempts = [entry.get("data") for entry in events if entry.get("event_type") == "http_attempt"]
    if len(attempts) != 1 or not isinstance(attempts[0], Mapping):
        raise ValueError("Pilot raw evidence does not have exactly one physical HTTP attempt")
    attempt = attempts[0]
    started, finished = attempt.get("http_started_monotonic_ns"), attempt.get("http_finished_monotonic_ns")
    if not isinstance(started, int) or not isinstance(finished, int) or finished < started or not isinstance(attempt.get("status"), int) or not 200 <= attempt["status"] < 300:
        raise ValueError("Pilot raw HTTP attempt lacks a valid 2xx status/timing")
    expected_metadata = {
        "transport": "nous_chat_completions_mcp_hardened_v2", "requested_provider": "nous", "configured_route_provider": "nous",
        "requested_model": CONTRACT["provider"]["model"], "provider_reported_model": metadata.get("provider_reported_model"),
        "provider_canonical_model": "deepseek/deepseek-v4-flash-20260731", "requested_reasoning_effort": "max",
        "provider_reported_reasoning_effort": metadata.get("provider_reported_reasoning_effort"), "tool_mode": "judge", "tool_free": True,
        "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0,
        "cross_process_provider_serialization_proven": True, "serialization_proof_sha256": _artifact(run, proof_path)["sha256"],
        "judge_request_sha256": _bridge_hash(raw_request), "judge_response_schema_sha256": _bridge_hash(expected_request["response_format"]), "judge_result_sha256": _bridge_hash(response),
    }
    if metadata.get("provider_reported_model") not in {"deepseek/deepseek-v4-flash-0731", "deepseek/deepseek-v4-flash-20260731"} or metadata.get("provider_reported_reasoning_effort") not in {None, "", "max"} or any(metadata.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("Pilot raw result provider/model/reasoning/recovery metadata drifted")
    if provider.get("evidence_sha256") != hashlib.sha256(_json_bytes({"result": response, "metadata": metadata})).hexdigest() or provider.get("serialization_proof_sha256") != expected_metadata["serialization_proof_sha256"]:
        raise ValueError("Pilot checkpoint receipt does not bind its raw Nous result")
    run_id = bridge_run_manifest.get("run_id")
    if not isinstance(run_id, str) or bridge_receipt.get("run_id") != run_id or bridge_run_manifest.get("requested_model") != CONTRACT["provider"]["model"] or bridge_run_manifest.get("requested_reasoning_effort") != "max":
        raise ValueError("Pilot bridge run/session receipt drifted")
    return {
        "judge_request": _artifact(run, request), "judge_result": _artifact(run, result), "serialization_proof": _artifact(run, proof_path),
        "evidence": {"run_id": run_id, "manifest": _artifact(run, evidence_path / "manifest.json"), "receipt": _artifact(run, evidence_path / "receipt.json"), "events": _artifact(run, evidence_path / "events.jsonl")},
        "http": {"status": attempt["status"], "duration_seconds": (finished - started) / 1_000_000_000},
    }


def _verify_cell(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    path = work / "pilot-receipts" / f"{cell['cell_id']}.json"
    receipt = read_json(path)
    run = work / "runs" / "pilot" / str(cell["cell_id"])
    manifest = read_json(run / "run.json")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(configuration)).hexdigest():
        raise ValueError("Pilot run manifest is malformed")
    folder = input_folder(frozen, cell)
    expected_inputs = cell["inputs"]
    expected = {
        "provider": "nous", "model": CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 16,
        "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "bundle_id": "prose.short_story",
        "question_ids": cell["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True,
    }
    if any(configuration.get(key) != value for key, value in expected.items()) or _compact(configuration.get("artifact")) != expected_inputs["source.md"] or [_compact(item) for item in configuration.get("contexts", [])] != [expected_inputs["prompt.md"]] or _compact(configuration.get("task_contract")) != expected_inputs["task-contract.json"]:
        raise ValueError("Pilot run does not bind its frozen provider/input/batch settings")
    checkpoints = sorted((run / "responses").glob("batch-*.json"))
    if [path.name for path in checkpoints] != ["batch-0001.json"]:
        raise ValueError("Pilot cell does not have exactly one completed provider batch")
    checkpoint = read_json(checkpoints[0])
    prompt = gzip.decompress(checkpoints[0].with_suffix(".prompt.txt.gz").read_bytes())
    provider = checkpoint.get("provider")
    if prompt != _expected_prompt(folder, cell) or checkpoint.get("format_version") != 4 or checkpoint.get("batch") != 1 or checkpoint.get("question_ids") != cell["question_ids"] or checkpoint.get("base_prompt_sha256") != hashlib.sha256(prompt).hexdigest() or checkpoint.get("prompt_sha256") != hashlib.sha256(prompt).hexdigest() or checkpoint.get("retry_policy") != {"batch_attempts": 1} or not isinstance(provider, Mapping):
        raise ValueError("Pilot checkpoint is malformed or unbound")
    raw = _raw_transport(run, checkpoint, prompt)
    try:
        _load_checkpoints(run, artifact_text=(folder / "source.md").read_text(encoding="utf-8"), context_texts=[(folder / "prompt.md").read_text(encoding="utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("Pilot completion is not schema-valid/replayable") from exc
    expected_receipt = {
        "format_version": 1, "study_id": CONTRACT["study_id"], "kind": "score_blind_transport_completion",
        "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_ids": cell["question_ids"],
        "elapsed_seconds": receipt.get("elapsed_seconds"), "run": fingerprint(run / "run.json"),
        "checkpoint": fingerprint(checkpoints[0]), "provider": provider,
        "session": {"mode": "stateless"},
        "raw_transport": raw,
    }
    elapsed = receipt.get("elapsed_seconds")
    if not _timely(elapsed) or receipt != expected_receipt:
        raise ValueError("Pilot receipt has invalid duration, bindings, or score-blind shape")
    return receipt


def verify_pilot(work: Path) -> dict[str, Any]:
    frozen = load_frozen(work)
    _invocation(work)
    _claim(work)
    journal_root = work / "pilot-journal"
    paths = sorted(journal_root.glob("[0-9][0-9][0-9][0-9]-*.json")) if journal_root.is_dir() else []
    records = [read_json(path) for path in paths]
    if len(records) != 3 or [record.get("sequence") for record in records] != [1, 2, 3] or any(record.get("status") != "completed" for record in records):
        raise ValueError("Pilot did not produce exactly three completed cells; preregister batch-8 v3")
    receipts = [_verify_cell(work, frozen, cell) for cell in frozen["cells"]]
    ids = [str(receipt.get("raw_transport", {}).get("evidence", {}).get("run_id", "")) for receipt in receipts]
    if len(set(ids)) != 3:
        raise ValueError("Pilot completion evidence was reused across cells")
    expected_journal = [{"sequence": index, "cell_id": receipt["cell_id"], "status": "completed", "receipt": fingerprint(work / "pilot-receipts" / f"{receipt['cell_id']}.json")} for index, receipt in enumerate(receipts, 1)]
    if records != expected_journal or [path.name for path in paths] != [f"{index:04d}-{receipt['cell_id']}.json" for index, receipt in enumerate(receipts, 1)]:
        raise ValueError("Pilot journal does not exactly bind its immutable receipts")
    return {"status": "PASS", "cells": 3, "comparison_status": CONTRACT["development"]["comparison_status"], "claim": fingerprint(work / "pilot-execution-claim.json"), "verifier": fingerprint(Path(__file__))}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", type=Path, required=True)
    print(json.dumps(verify_pilot(parser.parse_args().work_dir.resolve()), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
