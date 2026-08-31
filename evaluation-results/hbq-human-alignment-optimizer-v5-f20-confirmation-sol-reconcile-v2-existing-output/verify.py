#!/usr/bin/env python3
"""Provider-free reconciliation of the one terminal confirmation-Sol output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v2-existing-output"
V1_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-exec-v1"
V1_COMMIT = "ab8cf7d6d53e353ccf8fc0c68091d1fb3372cec0"
V1_HASHES = {
    f"evaluation-results/{V1_ID}/executor.py": "e7c91cb400a3d42b59223ab69bf28a447f3deb693a0b3929b6e16ee205f7c1bd",
    f"evaluation-results/{V1_ID}/study-contract.json": "f721d70e1790cf318b65bebe816924d38b42f0e7f4cddd8ebe1d77cf40ff4aa1",
    f"evaluation-results/{V1_ID}/README.md": "f52011a3f6dbe4d77d684f68d544bf9fca12b6daa41a4618eeb030fe24e3e9fc",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_confirmation_sol_exec_v1.py": "477b049285fcc0328a002013d85958a797ad4144c1c67e5be290f53f8d3b0916",
}
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe(path: Path, *, directory: bool | None = None) -> Path:
    absolute, current = Path(os.path.abspath(path)), Path(Path(os.path.abspath(path)).anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("required path is absent")
        _plain(current, directory=current != absolute or directory)
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _git_blob(relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(HERE.parents[1]), "show", f"{V1_COMMIT}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned V1 blob is absent")
    return result.stdout


def _load_v1() -> ModuleType:
    repo = HERE.parents[1]
    for relative, digest in V1_HASHES.items():
        raw = stable(repo / relative)
        if sha256(raw) != digest or _git_blob(relative) != raw:
            raise ValueError("pinned V1 dependency drifted")
    path = repo / f"evaluation-results/{V1_ID}/executor.py"
    raw = stable(path)
    module = ModuleType("_confirmation_sol_v1")
    module.__file__ = str(path)
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, str(path), "exec"), module.__dict__)
    finally:
        sys.modules.pop(module.__name__, None)
    if stable(path) != raw:
        raise ValueError("pinned V1 executor changed during load")
    return module


def _prepared(base: ModuleType, row: Mapping[str, Any], root: Path, acknowledgement: str, v4: ModuleType, v3: ModuleType) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], bytes, bytes]:
    prepared = strict(stable(root / "prepared.json"), "prepared")
    proof, target = strict(stable(root / "zero-charge-route-proof.json"), "route proof"), strict(stable(root / "target-vector.json"), "target vector")
    payload, schema = stable(root / "outbound-payload.json"), stable(root / "response-schema.json")
    route, evidence = v4._frozen_route(proof.get("route"), prepared.get("route_evidence"), v3, require_unexpired=False)
    expected = base._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement)
    if (target != {"format_version": 1, "study_id": base.STUDY_ID, "cell_id": row["cell_id"], "item_id": row["item_id"], "story_id": row["story_id"], "hanna_csv_sha256": base.TARGET_CSV_SHA256, "target": row["target"]}
            or proof.get("route_evidence") != evidence
            or any(stable(root / name) != raw for name, raw in expected.items())):
        raise ValueError("prepared source binding drifted")
    return prepared, route, evidence, payload, schema


def _invalid_terminal(root: Path, row: Mapping[str, Any], base: ModuleType, v3: ModuleType) -> str:
    expected = {"outbound-payload.json", "response-schema.json", "target-vector.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json", "responses", "launch-intent.json", "raw-codex-stderr.bin", "result.json"}
    if {path.name for path in root.iterdir()} != expected:
        raise ValueError("terminal reconciliation inventory drifted")
    result = strict(stable(root / "result.json"), "terminal result")
    if result != {"format_version": 1, "study_id": base.STUDY_ID, "kind": "reconcile_required_after_process_launch", "cell_id": row["cell_id"], "process_launches": 1, "provider_calls_made": None} | {"error_type": "ValueError"}:
        raise ValueError("terminal reconciliation record drifted")
    responses = root / "responses"
    if {path.name for path in responses.iterdir()} != {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"}:
        raise ValueError("terminal response inventory drifted")
    events, final = stable(responses / "batch-0001.attempt-0001.events.jsonl"), stable(responses / "batch-0001.attempt-0001.message.json")
    if stable(root / "raw-codex-stderr.bin") != b"" or not final:
        raise ValueError("terminal raw artifact binding drifted")
    try:
        v3._codex_event_projection(events, v3._load_parse_codex_events())
    except ValueError as error:
        if str(error) != "HANNA native exec Codex JSONL must complete exactly one agent message":
            raise
        return str(error)
    raise ValueError("terminal event unexpectedly became projectable")


def reconcile_existing_output(*, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_acknowledgement_sha256):
        raise ValueError("exact acknowledgement SHA-256 is required")
    source = _load_v1()
    resolution = source._resolve(frozen_root=Path(frozen_root))
    base = source._configured_base(resolution)
    _freeze, v4 = source._sources()
    v3 = base._load_v3()
    root = _safe(Path(output_root), directory=True)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    if {path.name for path in root.iterdir()} != set(rows):
        raise ValueError("confirmation output-root inventory drifted")
    completed = 0
    terminal: dict[str, str] = {}
    for cell_id, row in rows.items():
        cell = root / cell_id
        _plain(cell, directory=True)
        if (cell / "result.json").exists():
            _prepared(base, row, cell, authorization_acknowledgement_sha256, v4, v3)
            terminal[cell_id] = _invalid_terminal(cell, row, base, v3)
            continue
        base._inventory(cell, completed=True)
        prepared, route, evidence, payload, schema = _prepared(base, row, cell, authorization_acknowledgement_sha256, v4, v3)
        final, events, stderr = stable(cell / "raw-codex-final-response.bin"), stable(cell / "raw-codex-events.bin"), stable(cell / "raw-codex-stderr.bin")
        if final != stable(cell / "responses/batch-0001.attempt-0001.message.json") or events != stable(cell / "responses/batch-0001.attempt-0001.events.jsonl"):
            raise ValueError("completed raw response binding drifted")
        projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        answer = base._validate_answer(base._json(cell / "raw-codex-final-response.bin", "final Sol response"))
        receipt, settings, record = (strict(stable(cell / name), name) for name in ("execution-receipt.json", "effective-settings.json", "codex-record.json"))
        identity = receipt.get("identity", {})
        expected_settings = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_attested": False, "event_projection": projection, "route_name": route["name"], "codex_command_identity": route["codex_command_identity"]}
        expected_identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3", "native_endpoint_contact_cardinality": "unproven", "thread_id": projection.get("thread_id"), "session_id": f"local-codex-thread-session:{projection.get('thread_id')}", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}"}
        expected_record = {"command": v3._expected_codex_command(route["codex_command"][0], cell), "provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha256(stderr)}}, "reported": {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}}
        expected_receipt = {"format_version": 1, "study_id": base.STUDY_ID, "kind": "local_codex_lifecycle_receipt", "cell": dict(row), "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "route_evidence": evidence, "effective_settings_sha256": sha256(settings), "launch_intent_sha256": sha256(stable(cell / "launch-intent.json")), "identity": expected_identity, "human_score_projection": answer}
        if (settings != expected_settings or record != expected_record or identity != expected_identity or receipt != expected_receipt
                or projection.get("completed_agent_message_text", "").encode() != final):
            raise ValueError("completed receipt/identity binding drifted")
        completed += 1
    if terminal:
        return {"format_version": 1, "study_id": STUDY_ID, "kind": "existing_output_reconciliation", "source": {"executor_commit": V1_COMMIT, "executor_sha256": V1_HASHES[f"evaluation-results/{V1_ID}/executor.py"]}, "completion": {"logical_cells": 38, "reconciled_complete_cells": completed, "terminal_unprojectable_cells": len(terminal)}, "terminal_exclusions": [{"cell_id": cell_id, "reason": reason} for cell_id, reason in sorted(terminal.items())], "metrics": None, "claim": "INCOMPLETE_CONFIRMATION_SOL_NO_METRIC_OR_COMPARISON_CLAIM"}
    raise ValueError("reconciliation package expects the preserved terminal cell")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--authorization-acknowledgement-sha256", required=True)
    args = parser.parse_args(argv)
    print(canonical(reconcile_existing_output(output_root=args.output_root, frozen_root=args.frozen_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
