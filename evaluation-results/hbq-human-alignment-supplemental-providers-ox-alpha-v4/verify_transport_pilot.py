#!/usr/bin/env python3
"""Verify Ox Alpha v4 transport evidence without score or label analysis."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, prompts_dir, registry_path, schema_dir
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, NOUS_TRANSPORT_POLICY, _json_bytes, _load_checkpoints, _render_prompt, _validate_provider_artifacts, run_judge
from hbqrs.weights import materialize_weight_profile
from study import CONTRACT, FROZEN_NAME, assert_invocation_freshness, fingerprint, input_paths, judge_assets, load_frozen, read_json, runtime_bindings


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None


def _inside(root: Path, path: Path) -> Path:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Ox v4 raw evidence path escapes its run") from exc
    return path


def _artifact(run: Path, path: Path) -> dict[str, Any]:
    _inside(run, path)
    return {"path": path.relative_to(run).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _expected_prompt(frozen: Mapping[str, Any], folder: Path, cell: Mapping[str, Any]) -> bytes:
    assets = frozen.get("judge_assets")
    if assets != judge_assets() or not isinstance(assets, Mapping) or assets.get("strict_ai") is not False or assets.get("judge_prefix", {}).get("included") is not False:
        raise ValueError("Ox v4 judge-prefix policy or assets drifted")
    modules, bundle, _ = materialize_weight_profile(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    compiled = compile_bundle(modules, bundle, task_contract=read_json(folder / "task-contract.json"))
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    requested = list(cell["question_ids"])
    selected = [item for item in questions if item["question"]["id"] in set(requested)]
    if [item["question"]["id"] for item in selected] != requested:
        raise ValueError("Ox v4 frozen question sequence cannot render its prompt")
    names = [item["name"] for item in assets["active_prompts"]]
    if names != ["BINARY_EVALUATION_PROMPT.md"]:
        raise ValueError("Ox v4 active judge-instruction policy drifted")
    binary = "\n\n".join((prompts_dir() / "judge" / name).read_text(encoding="utf-8").strip() for name in names)
    return _render_prompt(binary_prompt=binary, artifact={"name": "source.md", "text": (folder / "source.md").read_text(encoding="utf-8")}, contexts=[{"name": "prompt.md", "text": (folder / "prompt.md").read_text(encoding="utf-8")}], bundle_id="prose.short_story", artifact_id=str(cell["item_id"]), questions=selected, provider="nous", model=CONTRACT["provider"]["model"]).encode("utf-8")


def _raw_transport(run: Path, checkpoint: Mapping[str, Any], prompt: bytes, frozen: Mapping[str, Any]) -> dict[str, Any]:
    provider = checkpoint.get("provider")
    cap1 = {**NOUS_TRANSPORT_POLICY, "max_physical_attempts_per_logical_request": 1}
    expected_provider = {"requested": {"model": CONTRACT["provider"]["model"], "reasoning_effort": "max"}, "reported": {"provider": "nous", "model": CONTRACT["provider"]["model"]}, "provider_canonical_model": CONTRACT["provider"]["provider_canonical_model"], "transport_policy": cap1, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0}
    if not isinstance(provider, Mapping) or any(provider.get(key) != value for key, value in expected_provider.items()):
        raise ValueError("Ox v4 requires one unrecovered physical HTTP attempt")
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}:
        raise ValueError("Ox v4 provider artifact receipt is incomplete")
    evidence_ref = artifacts["evidence_tree"].get("path") if isinstance(artifacts["evidence_tree"], Mapping) else None
    if not isinstance(evidence_ref, str):
        raise ValueError("Ox v4 evidence root is unbound")
    evidence = _inside(run, run / evidence_ref)
    events_path, receipt_path = evidence / "events.jsonl", evidence / "receipt.json"
    if not events_path.is_file() or not receipt_path.is_file():
        raise ValueError("Ox v4 raw evidence lacks event or provider receipt")
    try:
        _validate_provider_artifacts(run, checkpoint)
    except Exception as exc:
        raise ValueError("Ox v4 raw provider artifacts are invalid") from exc
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    attempts = [event.get("data") for event in events if isinstance(event, Mapping) and event.get("event_type") == "http_attempt"]
    if len(attempts) != 1 or not isinstance(attempts[0], Mapping):
        raise ValueError("Ox v4 raw evidence has a second physical HTTP attempt")
    attempt = attempts[0]
    started, finished, status = attempt.get("http_started_monotonic_ns"), attempt.get("http_finished_monotonic_ns"), attempt.get("status")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (started, finished, status)) or finished <= started or not 200 <= status < 300 or (finished - started) / 1_000_000_000 >= CONTRACT["transport_pilot"]["maximum_http_seconds_exclusive"]:
        raise ValueError("Ox v4 HTTP attempt is non-2xx or not below 100 seconds")
    logical_id, payload_sha = attempt.get("logical_request_id"), attempt.get("request_payload_sha256")
    if not isinstance(logical_id, str) or not logical_id or not isinstance(payload_sha, str) or len(payload_sha) != 64:
        raise ValueError("Ox v4 raw HTTP attempt lacks logical request or payload binding")
    bridge_receipt = read_json(receipt_path)
    run_id = bridge_receipt.get("run_id")
    if bridge_receipt.get("status") != "success" or not isinstance(run_id, str) or not run_id:
        raise ValueError("Ox v4 bridge provider receipt is not successful")
    request_ref, result_ref = (artifacts[name].get("path") if isinstance(artifacts[name], Mapping) else None for name in ("judge_request", "judge_result"))
    if not isinstance(request_ref, str) or not isinstance(result_ref, str):
        raise ValueError("Ox v4 raw request/result bindings are missing")
    request, result = _inside(run, run / request_ref), _inside(run, run / result_ref)
    if not request.is_file() or not result.is_file() or artifacts["judge_request"] != _artifact(run, request) or artifacts["judge_result"] != _artifact(run, result):
        raise ValueError("Ox v4 raw request/result artifact drifted")
    raw_request = read_json(request)
    expected_request = {"schema": CONTRACT["transport_pilot"]["required_request_schema"], "model": CONTRACT["provider"]["model"], "reasoning_effort": "max", "max_physical_http_attempts_per_logical_request": 1, "messages": [{"role": "system", "content": "You are a careful HBQ-RS evaluator. Do not use tools or reveal chain-of-thought."}, {"role": "user", "content": prompt.decode("utf-8")}], "response_format": {"type": "json_schema", "json_schema": {"name": "hbqrs_judge", "strict": True, "schema": read_json(schema_dir() / "hbq_judge_response.schema.json")}}}
    if frozen.get("judge_assets") != judge_assets() or raw_request != expected_request:
        raise ValueError("Ox v4 raw request does not bind the frozen judge prompt or response schema")
    return {"receipt_id": f"nous:{provider['evidence_sha256']}:{provider['serialization_proof_sha256']}", "session_id": run_id, "logical_request_id": logical_id, "payload": {"sha256": payload_sha, "judge_request": _artifact(run, request)}, "raw_evidence": {"root": artifacts["evidence_tree"], "events": _artifact(run, events_path), "judge_result": _artifact(run, result)}, "provider_receipt": _artifact(run, receipt_path)}


def _invocation(work: Path) -> dict[str, Any]:
    record = read_json(work / "pilot-invocation.json")
    expected = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "score_blind_cap1_transport_pilot", "contract": fingerprint(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract": fingerprint(work / FROZEN_NAME), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "execution": CONTRACT["execution"], "runtime": runtime_bindings(), "runner": fingerprint(Path(run_judge.__code__.co_filename)), "pilot_runner": fingerprint(Path(__file__).resolve().parent / "run_transport_pilot.py"), "pilot_verifier": fingerprint(Path(__file__))}
    if any(record.get(key) != value for key, value in expected.items()) or not isinstance(record.get("zero_cost_fresh_at_invocation"), str) or set(record) != {*expected, "zero_cost_fresh_at_invocation"}:
        raise ValueError("Ox v4 invocation is unbound")
    assert_invocation_freshness(load_frozen(work), record["zero_cost_fresh_at_invocation"])
    return record


def _claim(work: Path) -> dict[str, Any]:
    record = read_json(work / "pilot-execution-claim.json")
    expected = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_cap1_transport_execution", "invocation": fingerprint(work / "pilot-invocation.json")}
    if any(record.get(key) != value for key, value in expected.items()) or isinstance(record.get("pid"), bool) or not isinstance(record.get("pid"), int) or set(record) != {*expected, "pid"}:
        raise ValueError("Ox v4 exclusive claim is unbound")
    return record


def verify_cell(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    run = work / "runs" / "pilot" / str(cell["cell_id"])
    manifest = read_json(run / "run.json")
    configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(configuration)).hexdigest():
        raise ValueError("Ox v4 run manifest is malformed")
    artifact, prompt, task = input_paths(frozen, cell)
    policy = {**NOUS_TRANSPORT_POLICY, "max_physical_attempts_per_logical_request": 1}
    expected = {"provider": "nous", "model": CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 8, "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "bundle_id": "prose.short_story", "question_ids": cell["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True, "nous_transport_policy": policy, "nous_model_policy": {"requested_model": CONTRACT["provider"]["model"], "provider_canonical_model": CONTRACT["provider"]["provider_canonical_model"], "required_reasoning_effort": "max"}}
    assets = frozen.get("judge_assets")
    if any(configuration.get(key) != value for key, value in expected.items()) or _compact(configuration.get("artifact")) != cell["inputs"]["source.md"] or [_compact(item) for item in configuration.get("contexts", [])] != [cell["inputs"]["prompt.md"]] or _compact(configuration.get("task_contract")) != cell["inputs"]["task-contract.json"] or [_compact(item) for item in configuration.get("prompts", [])] != assets.get("active_prompts") or _compact(configuration.get("response_schema")) != assets.get("response_schema"):
        raise ValueError("Ox v4 run settings or inputs drifted")
    checkpoints = sorted((run / "responses").glob("batch-*.json"))
    if [path.name for path in checkpoints] != ["batch-0001.json"] or list((run / "responses" / "rejected").rglob("*.json")):
        raise ValueError("Ox v4 requires one clean batch")
    checkpoint = read_json(checkpoints[0])
    prompt_bytes = gzip.decompress(checkpoints[0].with_suffix(".prompt.txt.gz").read_bytes())
    if checkpoint.get("format_version") != 4 or checkpoint.get("batch") != 1 or checkpoint.get("question_ids") != cell["question_ids"] or checkpoint.get("retry_policy") != {"batch_attempts": 1} or checkpoint.get("accepted_attempt") != 1 or checkpoint.get("recovered_from_rejected") is not None or checkpoint.get("rejected_chain") != {"count": 0, "head_sha256": None} or prompt_bytes != _expected_prompt(frozen, artifact.parent, cell) or checkpoint.get("base_prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest() or checkpoint.get("prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest():
        raise ValueError("Ox v4 checkpoint is unbound or recovered")
    try:
        _load_checkpoints(run, artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[prompt.read_text(encoding="utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("Ox v4 completion is not schema-valid") from exc
    raw = _raw_transport(run, checkpoint, prompt_bytes, frozen)
    return {"run": fingerprint(run / "run.json"), "checkpoint": fingerprint(checkpoints[0]), "logical_request_id": raw["logical_request_id"], "payload": raw["payload"], "raw_evidence": raw["raw_evidence"], "provider_receipt": raw["provider_receipt"], "session_id": raw["session_id"], "receipt_id": raw["receipt_id"]}


def verify_pilot(work: Path) -> dict[str, Any]:
    frozen = load_frozen(work)
    invocation = _invocation(work)
    _claim(work)
    paths = sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json"))
    records = [read_json(path) for path in paths]
    if len(records) != 3 or [record.get("sequence") for record in records] != [1, 2, 3] or any(record.get("status") != "completed" for record in records):
        raise ValueError("Ox v4 did not produce three completed transport cells")
    proofs = [verify_cell(work, frozen, cell) for cell in frozen["cells"]]
    if any(len({proof[key] for proof in proofs}) != 3 for key in ("session_id", "receipt_id", "logical_request_id")):
        raise ValueError("Ox v4 reuses a provider session, receipt, or logical request")
    bound = fingerprint(work / "pilot-invocation.json")
    expected = [{"sequence": number, "cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": bound, "receipt": fingerprint(work / "pilot-receipts" / f"{cell['cell_id']}.json"), "logical_request_id": proof["logical_request_id"]} for number, (cell, proof) in enumerate(zip(frozen["cells"], proofs), 1)]
    if records != expected or [path.name for path in paths] != [f"{number:04d}-{cell['cell_id']}.json" for number, cell in enumerate(frozen["cells"], 1)]:
        raise ValueError("Ox v4 journal does not bind immutable receipts")
    return {"status": "PASS", "cells": 3, "claim": fingerprint(work / "pilot-execution-claim.json"), "invocation": fingerprint(work / "pilot-invocation.json"), "verifier": fingerprint(Path(__file__))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    print(json.dumps(verify_pilot(parser.parse_args().work_dir.resolve()), sort_keys=True))
