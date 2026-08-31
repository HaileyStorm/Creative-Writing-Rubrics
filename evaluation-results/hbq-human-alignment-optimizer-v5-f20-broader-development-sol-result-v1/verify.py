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
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-result-v1"
SOURCE_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-sol-validation-v1"
SOURCE_COMMIT = "d27fd700cb754bad036609f799ef7c9dac3d7a61"
SOURCE = HERE.parent / SOURCE_ID / "executor.py"
SOURCE_FILES = {
    f"evaluation-results/{SOURCE_ID}/executor.py": "dc093e764e29fcfca2997b24e3b1467c94fef2b6f472961e3296566af596fb66",
    f"evaluation-results/{SOURCE_ID}/study-contract.json": "eff9b08f894ccdde3d4e8d869f8e606f74408e88c2cefd99f2d1ed0fc3765c40",
    f"evaluation-results/{SOURCE_ID}/README.md": "2e50b03d8105e7ec358fa626fe4403ddf92daa614bcbfd7ea9f6c1dfa01e3960",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_broader_development_sol_validation_v1.py": "8e4772adb4cd419f66387881cab6b4744da2523f13af5787d98c171203e16d10",
}
GROK_RESULT_COMMIT = "5f50fbc2c345a55203cd2891d80037a797c6a1b4"
GROK_RESULT_SHA256 = "89d18aa68e8285dd9cbe8f996413672aec3c19b740c869b2bbca66c54ccd3a32"
BASELINE = "candidate-102cc7f06c9a99a7"
PARENT = "normalized-nextwave-08-conservative-hybrid"
DESCENDANT = "broader-nextwave-13-missing_evidence_not_no"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
AUTHORITY = {"selection": "none", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}
CLAIM = "DESCRIPTIVE_SOL_VALIDATION_ONLY; no pooling, selection, generalization, confirmation, promotion, or runtime claim"
EVIDENCE_CEILING = {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 21, "provider_calls_made": None}
RESULT_KIND = "twenty_one_cell_broader_sol_hanna_validation_result"
CONTRACT_KIND = "public_twenty_one_cell_broader_sol_hanna_validation_result_contract"
EXPECTED_RESULT_INTERNAL_SHA256 = "6070eab736ba2de3adad4c2449b4129fabb0c96e94c699db6df454718d53b063"
SOURCE_EXECUTION = {
    "grok_collector_sha256": "09a76419e4be6be186b580b985487f764c50ec3a164125bf934e717ea8ffb18b",
    "grok_result_commit": GROK_RESULT_COMMIT,
    "grok_result_internal_sha256": "ca07eb5db86aaf237b90b89be635aa7f45ca0ec791d616bfa3e5f05955e832fc",
    "grok_result_sha256": GROK_RESULT_SHA256,
    "hanna_csv_sha256": "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b",
    "receipt_chain_sha256": "b5d4160c26201789040632cb65e5a83076c2acbfc54befb539f9a07e4bc18646",
    "schedule_sha256": "bdb40b0f24f07ea938d57951768101a93ff62575919075abcd7bb9534e12c52c",
    "source_commit": SOURCE_COMMIT,
    "source_executor_sha256": SOURCE_FILES[f"evaluation-results/{SOURCE_ID}/executor.py"],
}
PUBLIC_FILES = {"README.md", "result.json", "study-contract.json", "verify.py"}
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
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("path does not exist")
        _plain(current, directory=current != absolute or directory)
    return absolute.resolve(strict=True)


def stable(path: Path) -> bytes:
    path = _safe(path, directory=False); before = os.lstat(path)
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
                raise ValueError("public surface contains sensitive material")
            _reject_sensitive(child)
    elif isinstance(value, list):
        for child in value:
            _reject_sensitive(child)
    elif isinstance(value, str) and PATH_PATTERN.search(value):
        raise ValueError("public surface contains a local path")


def _load_source() -> Any:
    repo = HERE.parents[1]
    for relative, digest in SOURCE_FILES.items():
        raw = stable(repo / relative)
        blob = subprocess.run(["git", "-C", str(repo), "show", f"{SOURCE_COMMIT}:{relative}"], capture_output=True, check=False)
        if sha256(raw) != digest or blob.returncode != 0 or blob.stdout != raw:
            raise ValueError("pinned broader Sol executor dependency drifted")
    raw = stable(SOURCE)
    spec = importlib.util.spec_from_file_location("_broader_sol_result_source", SOURCE)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned broader Sol executor")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if raw != stable(SOURCE):
        raise ValueError("pinned broader Sol executor changed during load")
    return module


def _reported_record(v3: Any, route: Mapping[str, Any], cell: Path, events: bytes, stderr: bytes) -> dict[str, Any]:
    return {"command": v3._expected_codex_command(route["codex_command"][0], cell), "provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha256(stderr)}}, "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}}


def _metrics(group_mae: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows = []
    for candidate, groups in group_mae.items():
        if len(groups) != 7:
            raise ValueError("equal-group geometry is incomplete")
        rows.append({"candidate_id": candidate, "cells": 7, "equal_group_mae": sum(groups.values()) / 7, "group_mae": groups})
    rows.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    indexed = {row["candidate_id"]: row for row in rows}
    if set(indexed) != {BASELINE, PARENT, DESCENDANT} or indexed[BASELINE]["equal_group_mae"] <= 0 or indexed[PARENT]["equal_group_mae"] <= 0:
        raise ValueError("candidate geometry drifted")
    def comparison(left: str, right: str) -> dict[str, Any]:
        delta = indexed[right]["equal_group_mae"] - indexed[left]["equal_group_mae"]
        return {"from_candidate_id": left, "from_equal_group_mae": indexed[left]["equal_group_mae"], "to_candidate_id": right, "to_equal_group_mae": indexed[right]["equal_group_mae"], "absolute_delta": delta, "relative_reduction": -delta / indexed[left]["equal_group_mae"]}
    return rows, {"baseline_to_parent": comparison(BASELINE, PARENT), "parent_to_descendant": comparison(PARENT, DESCENDANT), "baseline_to_descendant": comparison(BASELINE, DESCENDANT)}


def replay(*, output_root: Path, frozen_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path, acknowledgement_sha256: str) -> dict[str, Any]:
    source = _load_source()
    resolution = source._resolve(frozen_root=frozen_root, normalized_root=normalized_root, materialization_root=materialization_root, frozen_successor_path=frozen_successor_path, hanna_csv_path=hanna_csv_path, grok_execution_root=grok_execution_root, grok_collector_path=grok_collector_path, grok_result_path=grok_result_path, grok_result_commit=GROK_RESULT_COMMIT)
    if resolution["bindings"]["grok_result_sha256"] != GROK_RESULT_SHA256 or resolution["result"].get("selection", {}).get("candidate_id") != DESCENDANT:
        raise ValueError("pinned Grok result selection/source drifted")
    base = source._configured_base(resolution)
    _freeze, v4, _verifier = source._sources()
    root = _safe(output_root, directory=True)
    rows = resolution["rows"]
    if len(rows) != 21 or {path.name for path in root.iterdir()} != {row["cell_id"] for row in rows}:
        raise ValueError("completed 21-cell root inventory drifted")
    groups = {row["prompt_group_id"] for row in rows}; values = {BASELINE: {}, PARENT: {}, DESCENDANT: {}}
    identities: set[tuple[str, str, str]] = set(); commitments: list[dict[str, str]] = []
    route_value = evidence_value = None; v3 = base._load_v3()
    for row in rows:
        cell = root / row["cell_id"]; base._inventory(cell, completed=True)
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
        expected_intent = {"format_version": 1, "study_id": SOURCE_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared)}
        expected_receipt = {"format_version": 1, "study_id": SOURCE_ID, "kind": "local_codex_lifecycle_receipt", "cell": dict(row), "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "route_evidence": evidence, "effective_settings_sha256": sha256(settings), "launch_intent_sha256": sha256(stable(cell / "launch-intent.json")), "identity": identity, "human_score_projection": answer}
        key = (identity["thread_id"], identity["session_id"], identity["contact_id"])
        if route_value is None: route_value, evidence_value = route, evidence
        if (route != route_value or evidence != evidence_value or any(stable(cell / name) != raw for name, raw in expected.items()) or proof.get("route") != route or proof.get("route_evidence") != evidence or acknowledgement.get("acknowledgement_sha256") != acknowledgement_sha256 or target_file.get("target") != row["target"] or intent != expected_intent or sha256(payload) != row["payload_sha256"] or prepared.get("cell") != row or settings != expected_settings or record != _reported_record(v3, route, cell, events, stderr) or receipt != expected_receipt or final != stable(cell / "responses" / "batch-0001.attempt-0001.message.json") or response_events != events or projection.get("completed_agent_message_text", "").encode() != final or not all(isinstance(item, str) and item for item in key) or key in identities):
            raise ValueError("receipt/source/identity binding drifted")
        identities.add(key); commitments.append({"cell_id": row["cell_id"], "events_sha256": sha256(events), "final_response_sha256": sha256(final), "launch_intent_sha256": sha256(stable(cell / "launch-intent.json")), "prepared_sha256": sha256(prepared), "receipt_sha256": sha256(stable(cell / "execution-receipt.json"))})
        values[row["candidate_id"]][row["prompt_group_id"]] = sum(abs(answer["scores"][dimension] - row["target"][dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS)
    if len(identities) != 21 or any(set(group_values) != groups or len(group_values) != 7 for group_values in values.values()):
        raise ValueError("21-cell equal-group or identity geometry drifted")
    metrics, comparison = _metrics(values)
    observed_source = {"source_commit": SOURCE_COMMIT, "source_executor_sha256": SOURCE_FILES[f"evaluation-results/{SOURCE_ID}/executor.py"], "grok_result_commit": GROK_RESULT_COMMIT, "grok_result_sha256": GROK_RESULT_SHA256, "grok_result_internal_sha256": resolution["bindings"]["grok_result_internal_sha256"], "grok_collector_sha256": resolution["bindings"]["grok_collector_sha256"], "schedule_sha256": resolution["schedule"]["schedule_sha256"], "hanna_csv_sha256": resolution["bindings"]["hanna_csv_sha256"], "receipt_chain_sha256": sha256(commitments)}
    if observed_source != SOURCE_EXECUTION:
        raise ValueError("pinned broader Sol source commitments drifted")
    return {"authority": AUTHORITY, "claim": CLAIM, "evidence_ceiling": EVIDENCE_CEILING, "metrics": metrics, "comparison": comparison, "source_execution": SOURCE_EXECUTION}


def validate_publication() -> dict[str, Any]:
    root = _safe(HERE, directory=True)
    if {path.name for path in root.iterdir()} != PUBLIC_FILES:
        raise ValueError("public package inventory drifted")
    readme = stable(root / "README.md").decode("utf-8"); _reject_sensitive(readme)
    _contract_raw, contract = _canonical(root / "study-contract.json", "study contract")
    _result_raw, result = _canonical(root / "result.json", "public result")
    _reject_sensitive(contract); _reject_sensitive(result)
    expected_contract = {"authority", "contract_internal_sha256", "evidence_ceiling", "format_version", "kind", "publication_manifest", "result_internal_sha256", "source_execution", "study_id"}
    expected_result = {"authority", "claim", "comparison", "evidence_ceiling", "format_version", "kind", "metrics", "result_internal_sha256", "source_execution", "study_id"}
    if set(contract) != expected_contract or set(result) != expected_result or contract.get("study_id") != STUDY_ID or result.get("study_id") != STUDY_ID or contract.get("format_version") != 1 or result.get("format_version") != 1 or contract.get("kind") != CONTRACT_KIND or result.get("kind") != RESULT_KIND or contract.get("authority") != AUTHORITY or result.get("authority") != AUTHORITY or result.get("claim") != CLAIM or contract.get("evidence_ceiling") != EVIDENCE_CEILING or result.get("evidence_ceiling") != EVIDENCE_CEILING or contract.get("source_execution") != SOURCE_EXECUTION or result.get("source_execution") != SOURCE_EXECUTION:
        raise ValueError("publication identity or authority drifted")
    internal_contract = dict(contract); internal_contract.pop("contract_internal_sha256")
    internal_result = dict(result); internal_result.pop("result_internal_sha256")
    if contract["contract_internal_sha256"] != sha256(internal_contract) or result["result_internal_sha256"] != sha256(internal_result) or result["result_internal_sha256"] != EXPECTED_RESULT_INTERNAL_SHA256 or contract["result_internal_sha256"] != result["result_internal_sha256"] or contract["source_execution"] != result["source_execution"]:
        raise ValueError("publication commitment drifted")
    manifest = contract["publication_manifest"]
    if set(manifest) != {"bound_files", "inventory"} or manifest["inventory"] != sorted(PUBLIC_FILES) or set(manifest["bound_files"]) != {"README.md", "result.json", "verify.py"}:
        raise ValueError("publication manifest drifted")
    for name, digest in manifest["bound_files"].items():
        if not re.fullmatch(r"[0-9a-f]{64}", str(digest)) or sha256(stable(root / name)) != digest:
            raise ValueError("public file binding drifted")
    rows = result["metrics"]
    if not isinstance(rows, list) or len(rows) != 3 or {row.get("candidate_id") for row in rows} != {BASELINE, PARENT, DESCENDANT}:
        raise ValueError("public metric geometry drifted")
    group_mae: dict[str, dict[str, float]] = {}
    for row in rows:
        if set(row) != {"candidate_id", "cells", "equal_group_mae", "group_mae"} or row["cells"] != 7 or len(row["group_mae"]) != 7 or not all(type(item) in (int, float) and math.isfinite(item) for item in [row["equal_group_mae"], *row["group_mae"].values()]) or row["equal_group_mae"] != sum(row["group_mae"].values()) / 7:
            raise ValueError("public metric values drifted")
        group_mae[row["candidate_id"]] = row["group_mae"]
    derived, comparison = _metrics(group_mae)
    if rows != derived or result["comparison"] != comparison:
        raise ValueError("public comparison drifted")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the public 21-cell Sol result, or replay a supplied immutable root.")
    for name in ("output-root", "frozen-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "acknowledgement-sha256"):
        parser.add_argument("--" + name)
    args = parser.parse_args(argv)
    names = ("output-root", "frozen-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "acknowledgement-sha256")
    supplied = [getattr(args, name.replace("-", "_")) for name in names]
    if any(item is not None for item in supplied) and not all(item is not None for item in supplied):
        parser.error("provide every replay input or none")
    publication = validate_publication()
    if all(item is not None for item in supplied):
        replayed = replay(output_root=Path(args.output_root), frozen_root=Path(args.frozen_root), normalized_root=Path(args.normalized_root), materialization_root=Path(args.materialization_root), frozen_successor_path=Path(args.frozen_successor), hanna_csv_path=Path(args.hanna_csv), grok_execution_root=Path(args.grok_execution_root), grok_collector_path=Path(args.grok_collector), grok_result_path=Path(args.grok_result), acknowledgement_sha256=args.acknowledgement_sha256)
        if {key: replayed[key] for key in ("authority", "claim", "evidence_ceiling", "metrics", "comparison", "source_execution")} != {key: publication[key] for key in ("authority", "claim", "evidence_ceiling", "metrics", "comparison", "source_execution")}:
            raise ValueError("independent replay differs from public result")
        print(canonical({"cells": 21, "provider_calls_made": 0, "replay": "verified"}).decode(), end="")
    else:
        print(canonical({"binding_scope": sorted(PUBLIC_FILES), "provider_calls_made": 0, "publication": "verified"}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
