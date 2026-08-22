#!/usr/bin/env python3
"""Verify Ox Alpha v6 transport evidence without score or label analysis."""
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
    try: path.resolve().relative_to(root.resolve())
    except ValueError as exc: raise ValueError("Ox v6 raw evidence path escapes its run") from exc
    return path


def _artifact(run: Path, path: Path) -> dict[str, Any]:
    _inside(run, path)
    return {"path": path.relative_to(run).as_posix(), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _judge_leaf(evidence: Path, proof_path: Path) -> tuple[Path, Path]:
    """Select the one sealed Judge leaf and its bound ProveLock sibling."""
    if proof_path.parent.parent != evidence or not proof_path.is_file():
        raise ValueError("Ox v6 serialization proof is not a direct evidence sibling")
    try:
        children = sorted(path for path in evidence.iterdir() if path.is_dir())
    except OSError as exc:
        raise ValueError("Ox v6 evidence parent is unreadable") from exc
    judge = []
    records_by_child: dict[Path, list[Any]] = {}
    for child in children:
        events = child / "events.jsonl"
        try:
            records = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("Ox v6 evidence leaf events are unreadable") from exc
        records_by_child[child] = records
        if any(isinstance(record, Mapping) and record.get("event_type") == "judge_boundary" for record in records):
            judge.append(child)
    if len(children) != 2 or len(judge) != 1 or proof_path.parent == judge[0]:
        raise ValueError("Ox v6 evidence parent must contain one Judge leaf and one ProveLock sibling")
    prove = proof_path.parent
    receipt = read_json(prove / "receipt.json")
    if receipt.get("status") != "success" or not any(
        isinstance(record, Mapping) and record.get("event_type") == "serialization_proof"
        for record in [json.loads(line) for line in (prove / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    ):
        raise ValueError("Ox v6 ProveLock sibling is not sealed")
    prove_attempts = [record for record in records_by_child[prove] if isinstance(record, Mapping) and record.get("event_type") == "http_attempt"]
    judge_attempts = [record for record in records_by_child[judge[0]] if isinstance(record, Mapping) and record.get("event_type") == "http_attempt"]
    if prove_attempts or len(judge_attempts) != 1:
        raise ValueError("Ox v6 evidence parent must bind exactly one Judge HTTP attempt")
    return judge[0], prove


def _assert_proof_binding(events: list[Any], proof_path: Path) -> None:
    outcomes = [record.get("data") for record in events if isinstance(record, Mapping) and record.get("event_type") == "outcome"]
    metadata = outcomes[0].get("metadata") if len(outcomes) == 1 and isinstance(outcomes[0], Mapping) else None
    if not isinstance(metadata, Mapping) or metadata.get("serialization_proof_sha256") != hashlib.sha256(proof_path.read_bytes()).hexdigest() or Path(str(metadata.get("serialization_proof_path", ""))).resolve() != proof_path.resolve():
        raise ValueError("Ox v6 Judge leaf does not bind its ProveLock sibling")


def _expected_prompt(frozen: Mapping[str, Any], folder: Path, cell: Mapping[str, Any]) -> bytes:
    assets = frozen.get("judge_assets")
    if assets != judge_assets() or not isinstance(assets, Mapping) or assets.get("strict_ai") is not False or assets.get("judge_prefix", {}).get("included") is not False:
        raise ValueError("Ox v6 judge-prefix policy or assets drifted")
    modules, bundle, _ = materialize_weight_profile(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    compiled = compile_bundle(modules, bundle, task_contract=read_json(folder / "task-contract.json"))
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    questions = sorted(compiled_questions(compiled), key=lambda item: roles.get(str(item.get("role")), 99))
    requested = list(cell["question_ids"])
    selected = [item for item in questions if item["question"]["id"] in set(requested)]
    if [item["question"]["id"] for item in selected] != requested: raise ValueError("Ox v6 frozen question sequence cannot render its prompt")
    names = [item["name"] for item in assets["active_prompts"]]
    if names != ["BINARY_EVALUATION_PROMPT.md"]: raise ValueError("Ox v6 active judge-instruction policy drifted")
    binary = "\n\n".join((prompts_dir() / "judge" / name).read_text(encoding="utf-8").strip() for name in names)
    return _render_prompt(binary_prompt=binary, artifact={"name": "source.md", "text": (folder / "source.md").read_text(encoding="utf-8")}, contexts=[{"name": "prompt.md", "text": (folder / "prompt.md").read_text(encoding="utf-8")}], bundle_id="prose.short_story", artifact_id=str(cell["item_id"]), questions=selected, provider="nous", model=CONTRACT["provider"]["model"]).encode("utf-8")


def _within_raw_http_sla(duration_ns: int) -> bool:
    return 0 < duration_ns < CONTRACT["transport_pilot"]["maximum_http_seconds_exclusive"] * 1_000_000_000


def _raw_transport(run: Path, checkpoint: Mapping[str, Any], prompt: bytes, frozen: Mapping[str, Any]) -> dict[str, Any]:
    provider = checkpoint.get("provider")
    cap1 = {**NOUS_TRANSPORT_POLICY, "max_physical_attempts_per_logical_request": 1}
    expected = {"requested": {"model": CONTRACT["provider"]["model"], "reasoning_effort": "max"}, "reported": {"provider": "nous", "model": CONTRACT["provider"]["model"]}, "provider_canonical_model": CONTRACT["provider"]["provider_canonical_model"], "transport_policy": cap1, "logical_provider_request_count": 1, "physical_http_attempt_count": 1, "recovered_request_count": 0}
    if not isinstance(provider, Mapping) or any(provider.get(key) != value for key, value in expected.items()): raise ValueError("Ox v6 requires one unrecovered physical HTTP attempt")
    artifacts = provider.get("provider_artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}: raise ValueError("Ox v6 provider artifact receipt is incomplete")
    evidence_ref = artifacts["evidence_tree"].get("path") if isinstance(artifacts["evidence_tree"], Mapping) else None
    if not isinstance(evidence_ref, str): raise ValueError("Ox v6 evidence root is unbound")
    evidence = _inside(run, run / evidence_ref)
    try: _validate_provider_artifacts(run, checkpoint)
    except Exception as exc: raise ValueError("Ox v6 raw provider artifacts are invalid") from exc
    proof_ref = artifacts["serialization_proof"].get("path") if isinstance(artifacts["serialization_proof"], Mapping) else None
    if not isinstance(proof_ref, str): raise ValueError("Ox v6 serialization proof binding is missing")
    proof_path = _inside(run, run / proof_ref)
    if artifacts["serialization_proof"] != _artifact(run, proof_path): raise ValueError("Ox v6 serialization proof artifact drifted")
    judge_leaf, _ = _judge_leaf(evidence, proof_path)
    events_path, receipt_path = judge_leaf / "events.jsonl", judge_leaf / "receipt.json"
    if not events_path.is_file() or not receipt_path.is_file(): raise ValueError("Ox v6 Judge leaf lacks event or provider receipt")
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    _assert_proof_binding(events, proof_path)
    attempts = [event.get("data") for event in events if isinstance(event, Mapping) and event.get("event_type") == "http_attempt"]
    if len(attempts) != 1 or not isinstance(attempts[0], Mapping): raise ValueError("Ox v6 raw evidence has a second physical HTTP attempt")
    attempt = attempts[0]; started, finished, status = attempt.get("http_started_monotonic_ns"), attempt.get("http_finished_monotonic_ns"), attempt.get("status")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (started, finished, status)) or not _within_raw_http_sla(finished - started) or not 200 <= status < 300:
        raise ValueError("Ox v6 HTTP attempt is non-2xx or not below 150 seconds")
    logical_id, payload_sha = attempt.get("logical_request_id"), attempt.get("request_payload_sha256")
    if not isinstance(logical_id, str) or not logical_id or not isinstance(payload_sha, str) or len(payload_sha) != 64: raise ValueError("Ox v6 raw HTTP attempt lacks logical request or payload binding")
    bridge = read_json(receipt_path); run_id = bridge.get("run_id")
    if bridge.get("status") != "success" or not isinstance(run_id, str) or not run_id: raise ValueError("Ox v6 bridge provider receipt is not successful")
    request_ref, result_ref = (artifacts[name].get("path") if isinstance(artifacts[name], Mapping) else None for name in ("judge_request", "judge_result"))
    if not isinstance(request_ref, str) or not isinstance(result_ref, str): raise ValueError("Ox v6 raw request/result bindings are missing")
    request, result = _inside(run, run / request_ref), _inside(run, run / result_ref)
    if not request.is_file() or not result.is_file() or artifacts["judge_request"] != _artifact(run, request) or artifacts["judge_result"] != _artifact(run, result): raise ValueError("Ox v6 raw request/result artifact drifted")
    raw_request = read_json(request)
    expected_request = {"schema": CONTRACT["transport_pilot"]["required_request_schema"], "model": CONTRACT["provider"]["model"], "reasoning_effort": "max", "max_physical_http_attempts_per_logical_request": 1, "messages": [{"role": "system", "content": "You are a careful HBQ-RS evaluator. Do not use tools or reveal chain-of-thought."}, {"role": "user", "content": prompt.decode("utf-8")}], "response_format": {"type": "json_schema", "json_schema": {"name": "hbqrs_judge", "strict": True, "schema": read_json(schema_dir() / "hbq_judge_response.schema.json")}}}
    if frozen.get("judge_assets") != judge_assets() or raw_request != expected_request: raise ValueError("Ox v6 raw request does not bind the frozen judge prompt or response schema")
    return {"receipt_id": f"nous:{provider['evidence_sha256']}:{provider['serialization_proof_sha256']}", "session_id": run_id, "logical_request_id": logical_id, "payload": {"sha256": payload_sha, "judge_request": _artifact(run, request)}, "raw_evidence": {"root": artifacts["evidence_tree"], "judge_leaf": _artifact(run, judge_leaf / "receipt.json"), "events": _artifact(run, events_path), "judge_result": _artifact(run, result)}, "provider_receipt": _artifact(run, receipt_path)}


def _invocation(work: Path) -> dict[str, Any]:
    record = read_json(work / "pilot-invocation.json")
    expected = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "score_blind_cap1_transport_pilot", "contract": fingerprint(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract": fingerprint(work / FROZEN_NAME), "provider": CONTRACT["provider"], "pilot": CONTRACT["transport_pilot"], "execution": CONTRACT["execution"], "runtime": runtime_bindings(), "runner": fingerprint(Path(run_judge.__code__.co_filename)), "pilot_runner": fingerprint(Path(__file__).resolve().parent / "run_transport_pilot.py"), "pilot_verifier": fingerprint(Path(__file__))}
    if any(record.get(key) != value for key, value in expected.items()) or not isinstance(record.get("zero_cost_fresh_at_invocation"), str) or set(record) != {*expected, "zero_cost_fresh_at_invocation"}: raise ValueError("Ox v6 invocation is unbound")
    assert_invocation_freshness(load_frozen(work), record["zero_cost_fresh_at_invocation"])
    return record


def _claim(work: Path) -> dict[str, Any]:
    record = read_json(work / "pilot-execution-claim.json")
    expected = {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_cap1_transport_execution", "invocation": fingerprint(work / "pilot-invocation.json")}
    if any(record.get(key) != value for key, value in expected.items()) or isinstance(record.get("pid"), bool) or not isinstance(record.get("pid"), int) or set(record) != {*expected, "pid"}: raise ValueError("Ox v6 exclusive claim is unbound")
    return record


def verify_cell(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    run = work / "runs" / "pilot" / str(cell["cell_id"]); manifest = read_json(run / "run.json"); configuration = manifest.get("configuration")
    if not isinstance(configuration, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(configuration)).hexdigest(): raise ValueError("Ox v6 run manifest is malformed")
    artifact, prompt, _ = input_paths(frozen, cell); policy = {**NOUS_TRANSPORT_POLICY, "max_physical_attempts_per_logical_request": 1}
    expected = {"provider": "nous", "model": CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 4, "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "bundle_id": "prose.short_story", "question_ids": cell["question_ids"], "strict_ai": False, "allow_unattested_reasoning": True, "nous_transport_policy": policy, "nous_model_policy": {"requested_model": CONTRACT["provider"]["model"], "provider_canonical_model": CONTRACT["provider"]["provider_canonical_model"], "required_reasoning_effort": "max"}}
    assets = frozen.get("judge_assets")
    if any(configuration.get(key) != value for key, value in expected.items()) or _compact(configuration.get("artifact")) != cell["inputs"]["source.md"] or [_compact(item) for item in configuration.get("contexts", [])] != [cell["inputs"]["prompt.md"]] or _compact(configuration.get("task_contract")) != cell["inputs"]["task-contract.json"] or [_compact(item) for item in configuration.get("prompts", [])] != assets.get("active_prompts") or _compact(configuration.get("response_schema")) != assets.get("response_schema"): raise ValueError("Ox v6 run settings or inputs drifted")
    checkpoints = sorted((run / "responses").glob("batch-*.json"))
    if [path.name for path in checkpoints] != ["batch-0001.json"] or list((run / "responses" / "rejected").rglob("*.json")): raise ValueError("Ox v6 requires one clean batch")
    checkpoint = read_json(checkpoints[0]); prompt_bytes = gzip.decompress(checkpoints[0].with_suffix(".prompt.txt.gz").read_bytes())
    if checkpoint.get("format_version") != 4 or checkpoint.get("batch") != 1 or checkpoint.get("question_ids") != cell["question_ids"] or checkpoint.get("retry_policy") != {"batch_attempts": 1} or checkpoint.get("accepted_attempt") != 1 or checkpoint.get("recovered_from_rejected") is not None or checkpoint.get("rejected_chain") != {"count": 0, "head_sha256": None} or prompt_bytes != _expected_prompt(frozen, artifact.parent, cell) or checkpoint.get("base_prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest() or checkpoint.get("prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest(): raise ValueError("Ox v6 checkpoint is unbound or recovered")
    try: _load_checkpoints(run, artifact_text=artifact.read_text(encoding="utf-8"), context_texts=[prompt.read_text(encoding="utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc: raise ValueError("Ox v6 completion is not schema-valid") from exc
    raw = _raw_transport(run, checkpoint, prompt_bytes, frozen)
    return {"run": fingerprint(run / "run.json"), "checkpoint": fingerprint(checkpoints[0]), "logical_request_id": raw["logical_request_id"], "payload": raw["payload"], "raw_evidence": raw["raw_evidence"], "provider_receipt": raw["provider_receipt"], "session_id": raw["session_id"], "receipt_id": raw["receipt_id"]}


def _expected_receipt(cell: Mapping[str, Any], proof: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 2, "study_id": CONTRACT["study_id"], "kind": "cap1_transport_completion", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_ids": cell["question_ids"], **{key: proof[key] for key in ("run", "checkpoint", "logical_request_id", "payload", "raw_evidence", "provider_receipt")}}


def verify_pilot(work: Path) -> dict[str, Any]:
    frozen = load_frozen(work); _invocation(work); _claim(work)
    paths = sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json")); records = [read_json(path) for path in paths]
    if len(records) != 3 or [record.get("sequence") for record in records] != [1, 2, 3] or any(record.get("status") != "completed" for record in records): raise ValueError("Ox v6 did not produce three completed transport cells")
    proofs = [verify_cell(work, frozen, cell) for cell in frozen["cells"]]
    if any(len({proof[key] for proof in proofs}) != 3 for key in ("session_id", "receipt_id", "logical_request_id")): raise ValueError("Ox v6 reuses a provider session, receipt, or logical request")
    predecessor = frozen.get("uncertain_v5")
    ancestor_ids = predecessor.get("accepted_global_ids") if isinstance(predecessor, Mapping) else None
    if not isinstance(ancestor_ids, Mapping) or any(not isinstance(ancestor_ids.get(key), str) or not ancestor_ids[key] for key in ("session_id", "receipt_id", "logical_request_id")):
        raise ValueError("Ox v6 lacks bound accepted-v5 provider identities")
    if any(any(proof[key] == ancestor_ids[key] for proof in proofs) for key in ("session_id", "receipt_id", "logical_request_id")):
        raise ValueError("Ox v6 reuses an accepted-v5 provider session, receipt, or logical request")
    receipt_paths = [work / "pilot-receipts" / f"{cell['cell_id']}.json" for cell in frozen["cells"]]
    if not (work / "pilot-receipts").is_dir() or sorted(path.name for path in (work / "pilot-receipts").iterdir()) != sorted(path.name for path in receipt_paths): raise ValueError("Ox v6 receipt set is malformed")
    for cell, proof, path in zip(frozen["cells"], proofs, receipt_paths):
        if read_json(path) != _expected_receipt(cell, proof): raise ValueError("Ox v6 immutable receipt semantic body drifted")
    bound = fingerprint(work / "pilot-invocation.json")
    expected = [{"sequence": number, "cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": bound, "receipt": fingerprint(work / "pilot-receipts" / f"{cell['cell_id']}.json"), "logical_request_id": proof["logical_request_id"]} for number, (cell, proof) in enumerate(zip(frozen["cells"], proofs), 1)]
    if records != expected or [path.name for path in paths] != [f"{number:04d}-{cell['cell_id']}.json" for number, cell in enumerate(frozen["cells"], 1)]: raise ValueError("Ox v6 journal does not bind immutable receipts")
    return {"status": "PASS", "cells": 3, "claim": fingerprint(work / "pilot-execution-claim.json"), "invocation": fingerprint(work / "pilot-invocation.json"), "verifier": fingerprint(Path(__file__))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", required=True, type=Path)
    print(json.dumps(verify_pilot(parser.parse_args().work_dir.resolve()), sort_keys=True))
