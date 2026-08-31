from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-result-v1"
V4_STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load"
V4_COMMIT = "a95b9df6668da612af26a25c8abd8e8f5cb4027d"
V4_PACKAGE = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load"
V4_FILES = {
    "evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load/executor.py": "ef2b44a5457292d71151a4ab48346a298956acb8126106d0cc186696efeb537c",
    "evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load/study-contract.json": "2a5447980b8de860e0f60de57d04fbd7f9391efd9b62ab861ed5e68c0b7f5032",
    "evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load/README.md": "4a79ed026c951d9a4eef6889c1fd43cf61535f89ddc3d9b862f3c30c3b74b806",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_nextwave_sol6_validation_exec_v4_threadsafe_route_load.py": "74737ea7f6dc4d8294428457037a80da43fee9e08935ec80510ece25043d9611",
}
PUBLIC_FILES = {"README.md", "result.json", "study-contract.json", "verify.py"}
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
AUTHORITY = {"selection": "none", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}
CLAIM = "DESCRIPTIVE_SOL_VALIDATION_ONLY; no pooling, selection, generalization, confirmation, promotion, or runtime claim"
EVIDENCE_CEILING = {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 6, "provider_calls_made": None}
RESULT_KIND = "six_cell_sol_hanna_validation_result"
CONTRACT_KIND = "public_six_cell_sol_hanna_validation_result_contract"
SOURCE_EXECUTION = {
    "grok_collector_sha256": "d2f4c329fb05f31a27578483548855cfb7ab77c26ee75bbb44367019a2e8fe99",
    "grok_result_commit": "3b8202c20eed82f431e1a37024e547cfea1fe6f7",
    "grok_result_sha256": "d0ceafc2abf45e8d8a8db9029bf8184ab3ca12f1d477ad50f0f5fb10e0c58c59",
    "receipt_chain_sha256": "96740be522652933da41eb1143684c0dffab08e7939fe73a97e87d0c7bcfd919",
    "schedule_sha256": "e8de7435e7cb1cab43f2a4d99438b2d136f6b763e758766cf3fe8626e1eda9e5",
    "v4_commit": V4_COMMIT,
    "v4_executor_sha256": V4_FILES["evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load/executor.py"],
    "v4_study_contract_sha256": V4_FILES["evaluation-results/hbq-human-alignment-optimizer-v5-f20-nextwave-sol6-validation-exec-v4-threadsafe-route-load/study-contract.json"],
}
SENSITIVE_KEYS = {"local_path", "payload", "prompt_text", "raw_output", "request_id", "session_id", "story_text", "writing"}
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\[^\\]+|/(?:Users|home|private|tmp)/)")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe or reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe(path: Path, *, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("path does not exist")
        _plain(current, directory=current != absolute or directory)
    return absolute.resolve(strict=True)


def stable(path: Path) -> bytes:
    path = _safe(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, child in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = child
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _canonical(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = stable(path); value = strict(raw, label)
    if raw != canonical(value):
        raise ValueError(f"{label} is not canonical")
    return raw, value


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in SENSITIVE_KEYS:
                raise ValueError("public surface contains local or sensitive material")
            _reject_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive(child)
    elif isinstance(value, str) and PATH_PATTERN.search(value):
        raise ValueError("public surface contains a local path")


def _load_v4() -> Any:
    repo = HERE.parents[1]
    for relative, digest in V4_FILES.items():
        raw = stable(repo / relative)
        blob = subprocess.run(["git", "-C", str(repo), "show", f"{V4_COMMIT}:{relative}"], capture_output=True, check=False)
        if sha256(raw) != digest or blob.returncode != 0 or blob.stdout != raw:
            raise ValueError("pinned V4 dependency drifted")
    spec = importlib.util.spec_from_file_location("_sol6_v4_result_replay", V4_PACKAGE / "executor.py")
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned V4 executor")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


def _reported_record(base: Any, v3: Any, route: Mapping[str, Any], cell: Path, events: bytes, stderr: bytes) -> dict[str, Any]:
    return {
        "command": v3._expected_codex_command(route["codex_command"][0], cell),
        "provider_artifacts": {
            "codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha256(events)},
            "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha256(stderr)},
        },
        "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": None},
    }


def _metrics(group_mae: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    for candidate, groups in group_mae.items():
        if len(groups) != 3:
            raise ValueError("incomplete equal-group geometry")
        rows.append({"candidate_id": candidate, "cells": 3, "equal_group_mae": sum(groups.values()) / 3, "group_mae": groups})
    rows.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    baseline = next((row for row in rows if row["candidate_id"] == "candidate-102cc7f06c9a99a7"), None)
    candidate = next((row for row in rows if row["candidate_id"] == "normalized-nextwave-08-conservative-hybrid"), None)
    if baseline is None or candidate is None or baseline["equal_group_mae"] <= 0:
        raise ValueError("expected candidate identities drifted")
    delta = candidate["equal_group_mae"] - baseline["equal_group_mae"]
    return rows, {"baseline_candidate_id": baseline["candidate_id"], "baseline_equal_group_mae": baseline["equal_group_mae"], "candidate_id": candidate["candidate_id"], "candidate_equal_group_mae": candidate["equal_group_mae"], "absolute_delta": delta, "relative_reduction": -delta / baseline["equal_group_mae"]}


def replay(*, output_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path, acknowledgement_sha256: str) -> dict[str, Any]:
    v4 = _load_v4()
    root = _safe(output_root, directory=True)
    base, schedule, rows, bindings = v4._schedule(normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, grok_execution_root=grok_execution_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path)
    v4._configure(base, rows, schedule, bindings)
    if {path.name for path in root.iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("completed V4 root inventory drifted")
    groups = {row["prompt_group_id"] for row in rows}
    values: dict[str, dict[str, float]] = {v4.BASELINE: {}, v4.CANDIDATE: {}}
    identities: set[tuple[str, str, str]] = set()
    commitments: list[dict[str, str]] = []
    route_value = evidence_value = None
    v3 = base._load_v3()
    for row in rows:
        cell = root / row["cell_id"]
        base._inventory(cell, completed=True)
        _prepared_raw, prepared = _canonical(cell / "prepared.json", "prepared")
        _disclosure_raw, disclosure = _canonical(cell / "disclosure.json", "disclosure")
        _ack_raw, acknowledgement = _canonical(cell / "authorization-acknowledgement.json", "acknowledgement")
        _proof_raw, proof = _canonical(cell / "zero-charge-route-proof.json", "route proof")
        _target_raw, target_file = _canonical(cell / "target-vector.json", "target vector")
        _intent_raw, intent = _canonical(cell / "launch-intent.json", "launch intent")
        _receipt_raw, receipt = _canonical(cell / "execution-receipt.json", "receipt")
        _record_raw, record = _canonical(cell / "codex-record.json", "Codex record")
        _settings_raw, settings = _canonical(cell / "effective-settings.json", "effective settings")
        payload, schema = stable(cell / "outbound-payload.json"), stable(cell / "response-schema.json")
        final, events, stderr = stable(cell / "raw-codex-final-response.bin"), stable(cell / "raw-codex-events.bin"), stable(cell / "raw-codex-stderr.bin")
        response_events = stable(cell / "responses" / "batch-0001.attempt-0001.events.jsonl")
        projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        answer = base._validate_answer(base._json(cell / "raw-codex-final-response.bin", "final response"))
        route, evidence = v4._frozen_route(proof.get("route"), prepared.get("route_evidence"), v3, require_unexpired=False)
        expected = base._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement_sha256)
        expected_settings = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_attested": False, "event_projection": projection, "route_name": route["name"], "codex_command_identity": route["codex_command_identity"]}
        identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3", "native_endpoint_contact_cardinality": "unproven", "thread_id": projection.get("thread_id"), "session_id": f"local-codex-thread-session:{projection.get('thread_id')}", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}"}
        expected_intent = {"format_version": 1, "study_id": V4_STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared)}
        expected_receipt = {"format_version": 1, "study_id": V4_STUDY_ID, "kind": "local_codex_lifecycle_receipt", "cell": dict(row), "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "route_evidence": evidence, "effective_settings_sha256": sha256(settings), "launch_intent_sha256": sha256(stable(cell / "launch-intent.json")), "identity": identity, "human_score_projection": answer}
        key = (identity["thread_id"], identity["session_id"], identity["contact_id"])
        if (route_value is None): route_value, evidence_value = route, evidence
        if (route != route_value or evidence != evidence_value or any(stable(cell / name) != raw for name, raw in expected.items()) or proof.get("route") != route or proof.get("route_evidence") != evidence or acknowledgement.get("acknowledgement_sha256") != acknowledgement_sha256 or target_file.get("target") != row["target"] or intent != expected_intent or sha256(payload) != row["payload_sha256"] or prepared.get("cell") != row or settings != expected_settings or record != _reported_record(base, v3, route, cell, events, stderr) or receipt != expected_receipt or final != stable(cell / "responses" / "batch-0001.attempt-0001.message.json") or response_events != events or projection.get("completed_agent_message_text", "").encode() != final or not all(isinstance(item, str) and item for item in key) or key in identities):
            raise ValueError("V4 receipt/source/identity binding drifted")
        identities.add(key)
        commitments.append({"cell_id": row["cell_id"], "events_sha256": sha256(events), "final_response_sha256": sha256(final), "launch_intent_sha256": sha256(stable(cell / "launch-intent.json")), "prepared_sha256": sha256(prepared), "receipt_sha256": sha256(stable(cell / "execution-receipt.json"))})
        values[row["candidate_id"]][row["prompt_group_id"]] = sum(abs(answer["scores"][dimension] - row["target"][dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS)
    if any(set(group_values) != groups or len(group_values) != 3 for group_values in values.values()) or len(identities) != 6:
        raise ValueError("six-cell equal-group or identity geometry drifted")
    metrics, comparison = _metrics(values)
    observed_source = {"v4_commit": V4_COMMIT, "v4_executor_sha256": V4_FILES[next(key for key in V4_FILES if key.endswith("/executor.py"))], "v4_study_contract_sha256": V4_FILES[next(key for key in V4_FILES if key.endswith("/study-contract.json"))], "grok_result_commit": v4.GROK_RESULT_COMMIT, "grok_result_sha256": bindings["result_sha256"], "grok_collector_sha256": bindings["collector_sha256"], "schedule_sha256": schedule["schedule_sha256"], "receipt_chain_sha256": sha256(commitments)}
    if observed_source != SOURCE_EXECUTION:
        raise ValueError("pinned V4/Grok source commitments drifted")
    return {"authority": AUTHORITY, "claim": CLAIM, "evidence_ceiling": EVIDENCE_CEILING, "group_mae": values, "metrics": metrics, "comparison": comparison, "source_execution": SOURCE_EXECUTION}


def validate_publication() -> dict[str, Any]:
    root = _safe(HERE, directory=True)
    if {path.name for path in root.iterdir()} != PUBLIC_FILES:
        raise ValueError("public package inventory drifted")
    readme = stable(root / "README.md").decode("utf-8"); _reject_sensitive(readme)
    contract_raw, contract = _canonical(root / "study-contract.json", "study contract")
    result_raw, result = _canonical(root / "result.json", "public result")
    _reject_sensitive(contract); _reject_sensitive(result)
    if (set(contract) != {"authority", "contract_internal_sha256", "evidence_ceiling", "format_version", "kind", "publication_manifest", "result_internal_sha256", "source_execution", "study_id"}
            or contract.get("format_version") != 1 or contract.get("study_id") != STUDY_ID or contract.get("kind") != CONTRACT_KIND
            or contract.get("authority") != AUTHORITY or contract.get("evidence_ceiling") != EVIDENCE_CEILING or contract.get("source_execution") != SOURCE_EXECUTION):
        raise ValueError("contract fields drifted")
    internal_contract = dict(contract); internal_contract.pop("contract_internal_sha256")
    if contract["contract_internal_sha256"] != sha256(internal_contract):
        raise ValueError("contract commitment drifted")
    manifest = contract["publication_manifest"]
    if set(manifest) != {"bound_files", "inventory"} or manifest["inventory"] != sorted(PUBLIC_FILES) or set(manifest["bound_files"]) != {"README.md", "result.json", "verify.py"}:
        raise ValueError("publication manifest drifted")
    for name, digest in manifest["bound_files"].items():
        if not re.fullmatch(r"[0-9a-f]{64}", str(digest)) or sha256(stable(root / name)) != digest:
            raise ValueError("public file binding drifted")
    if (set(result) != {"authority", "claim", "comparison", "evidence_ceiling", "format_version", "kind", "metrics", "result_internal_sha256", "source_execution", "study_id"}
            or result.get("study_id") != STUDY_ID or result.get("format_version") != 1 or result.get("kind") != RESULT_KIND
            or result.get("authority") != AUTHORITY or result.get("claim") != CLAIM or result.get("evidence_ceiling") != EVIDENCE_CEILING or result.get("source_execution") != SOURCE_EXECUTION):
        raise ValueError("result identity drifted")
    internal_result = dict(result); internal_result.pop("result_internal_sha256")
    if result["result_internal_sha256"] != sha256(internal_result) or contract["result_internal_sha256"] != result["result_internal_sha256"] or contract["source_execution"] != result["source_execution"] or contract["authority"] != result["authority"] or contract["evidence_ceiling"] != result["evidence_ceiling"]:
        raise ValueError("result/contract binding drifted")
    rows = result["metrics"]
    if not isinstance(rows, list) or len(rows) != 2 or {row.get("candidate_id") for row in rows} != {"candidate-102cc7f06c9a99a7", "normalized-nextwave-08-conservative-hybrid"}:
        raise ValueError("published metric geometry drifted")
    for row in rows:
        if set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae"} or row["cells"] != 3 or len(row["group_mae"]) != 3 or not all(type(value) in (int, float) and math.isfinite(value) for value in [row["equal_group_mae"], *row["group_mae"].values()]) or row["equal_group_mae"] != sum(row["group_mae"].values()) / 3:
            raise ValueError("published metric values drifted")
    derived_metrics, comparison = _metrics({row["candidate_id"]: row["group_mae"] for row in rows})
    if rows != derived_metrics or result["comparison"] != comparison:
        raise ValueError("published comparison drifted")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the public Sol6 result package, or replay a supplied immutable V4 root.")
    for name in ("output-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "acknowledgement-sha256"):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    supplied = [getattr(args, name.replace("-", "_")) for name in ("output-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "acknowledgement-sha256")]
    if any(item is not None for item in supplied) and not all(item is not None for item in supplied):
        parser.error("provide every replay input or none")
    publication = validate_publication()
    if all(item is not None for item in supplied):
        replayed = replay(output_root=Path(args.output_root), normalized_root=Path(args.normalized_root), materialization_root=Path(args.materialization_root), frozen_successor_path=Path(args.frozen_successor), hanna_csv_path=Path(args.hanna_csv), grok_execution_root=Path(args.grok_execution_root), grok_collector_path=Path(args.grok_collector), grok_result_path=Path(args.grok_result), acknowledgement_sha256=args.acknowledgement_sha256)
        if {key: replayed[key] for key in ("authority", "claim", "evidence_ceiling", "metrics", "comparison", "source_execution")} != {key: publication[key] for key in ("authority", "claim", "evidence_ceiling", "metrics", "comparison", "source_execution")}:
            raise ValueError("independent replay differs from public result")
        print(canonical({"cells": 6, "provider_calls_made": 0, "replay": "verified"}).decode(), end="")
    else:
        print(canonical({"binding_scope": sorted(PUBLIC_FILES), "provider_calls_made": 0, "publication": "verified"}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
