#!/usr/bin/env python3
"""Tool-free, paired Sol measurement of the already-frozen Fresh96 panel."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v10-fresh96-confirmation-sol-exec-v1"
FREEZE = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1"
FREEZE_STUDY_SHA256 = "38ea9c9c0cf96dfc0ca32b64ee6639515600bc01b93e204cdd397bae393b2a6f"
FREEZE_CONTRACT_SHA256 = "acf8fbf0f3ef5937d963e53fecf286ae3a606eb62302b0e918468e74b17d9348"
GROK_RESULT = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-result-v1" / "result.json"
GROK_RESULT_VERIFIER = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-result-v1" / "verify.py"
GROK_RESULT_COMMIT = "fa24f3b"
GROK_RESULT_SHA256 = "e94055aeb3993785a3bee1ba09f4a00ba8e6eeb0b48d065d5c983a7097b07c18"
GROK_RESULT_VERIFIER_SHA256 = "f08422dd99170daff6eb6555ff61d83cac53df4e3f58c0b86bb7c742f00a35b9"
GROK_EXECUTOR = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-exec-v1" / "executor.py"
GROK_EXECUTOR_SHA256 = "f361d334a8ac6e1eb6900ff348ac98a933dbb5393862e693eaf77fe1d66cdfc3"
GROK_EXECUTOR_COMMIT = "1c10bae"
GROK_RECONCILER = HERE.parent / "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-reconcile-v1" / "reconcile.py"
GROK_RECONCILER_SHA256 = "6c132ade2b95bad54a580736e9e8b66fef4cb8b9733f91c0398dd35e4488293d"
GROK_RECONCILER_COMMIT = "c7d9191"
HANNA_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"
V9 = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-exec-v1" / "executor.py"
V9_COMMIT = "926f8f1"
V9_SHA256 = "578a488b8b85b67705e7db1d560134a1c24714ab201efba336ca3611979e72b7"
BASELINE = "candidate-102cc7f06c9a99a7"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
MAX_CONCURRENCY = 10


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def stable(path: Path) -> bytes:
    path = Path(path)
    before = os.lstat(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("unsafe source artifact")
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("stable source read drifted")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _blob(commit: str, path: Path) -> bytes:
    relative = path.relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError(f"pinned Git blob unavailable: {relative}")
    return result.stdout


def _load(path: Path, digest: str, commit: str, name: str) -> ModuleType:
    raw = stable(path)
    if sha256(raw) != digest or _blob(commit, path) != raw:
        raise ValueError("pinned dependency drifted or is not committed")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("pinned dependency cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned dependency changed during load")
    return module


def _freeze() -> ModuleType:
    if sha256(stable(FREEZE / "study-contract.json")) != FREEZE_CONTRACT_SHA256:
        raise ValueError("V10 freeze contract drifted")
    return _load(FREEZE / "study.py", FREEZE_STUDY_SHA256, "1c10bae", "_v10_sol_freeze")


def _qualification() -> dict[str, Any]:
    raw = stable(GROK_RESULT)
    if sha256(raw) != GROK_RESULT_SHA256 or _blob(GROK_RESULT_COMMIT, GROK_RESULT) != raw:
        raise ValueError("frozen Grok qualification result drifted")
    value = strict(raw, "Grok qualification result")
    comparison = value.get("comparison")
    if (sha256(stable(GROK_RESULT_VERIFIER)) != GROK_RESULT_VERIFIER_SHA256 or _blob(GROK_RESULT_COMMIT, GROK_RESULT_VERIFIER) != stable(GROK_RESULT_VERIFIER)
            or sha256(stable(GROK_EXECUTOR)) != GROK_EXECUTOR_SHA256 or _blob(GROK_EXECUTOR_COMMIT, GROK_EXECUTOR) != stable(GROK_EXECUTOR)
            or sha256(stable(GROK_RECONCILER)) != GROK_RECONCILER_SHA256 or _blob(GROK_RECONCILER_COMMIT, GROK_RECONCILER) != stable(GROK_RECONCILER)
            or value.get("study_id") != "hbq-human-alignment-optimizer-v10-fresh96-confirmation-grok-result-v1" or value.get("endpoint") != "grok_primary" or not isinstance(comparison, Mapping) or comparison.get("baseline_candidate_id") != BASELINE or comparison.get("child_candidate_id") != CHILD or not isinstance(comparison.get("child20_minus_baseline"), (int, float)) or float(comparison["child20_minus_baseline"]) >= 0):
        raise ValueError("Grok qualification does not permit Sol measurement")
    return value


def _rows(freeze_root: Path) -> tuple[dict[str, Any], ...]:
    schedule = _freeze().validate_frozen_root(Path(freeze_root)); cells = schedule.get("cells")
    if not isinstance(cells, list) or len(cells) != 64 or len({row.get("item_id") for row in cells if isinstance(row, Mapping)}) != 32 or len({row.get("prompt_group_id") for row in cells if isinstance(row, Mapping)}) != 16:
        raise ValueError("V10 frozen geometry drifted")
    rows: list[dict[str, Any]] = []
    for source in cells:
        if not isinstance(source, Mapping) or source.get("candidate_id") not in {BASELINE, CHILD}:
            raise ValueError("V10 frozen candidate drifted")
        payload = base64.b64decode(str(source.get("payload_base64", "")), validate=True)
        if sha256(payload) != source.get("payload_sha256") or source.get("endpoint_payload_sha256s") != {"grok_primary": source["payload_sha256"], "sol_later": source["payload_sha256"]} or not isinstance(source.get("target"), Mapping) or set(source["target"]) != set(DIMENSIONS):
            raise ValueError("exact paired Sol payload binding drifted")
        rows.append({"cell_id": "v10-sol-" + sha256({"source": source["cell_id"]})[:16], "source_cell_id": source["cell_id"], "candidate_id": source["candidate_id"], "item_id": source["item_id"], "story_id": source["item_id"], "prompt_group_id": source["prompt_group_id"], "payload_base64": source["payload_base64"], "payload_sha256": source["payload_sha256"], "payload_parity": "frozen_fresh96_schedule_exact_payload_bytes", "target": {key: float(source["target"][key]) for key in DIMENSIONS}})
    if len({row["cell_id"] for row in rows}) != 64 or {(row["candidate_id"], row["item_id"]) for row in rows} != {(candidate, row["item_id"]) for candidate in (BASELINE, CHILD) for row in rows if row["candidate_id"] == BASELINE}:
        raise ValueError("paired Sol cell geometry drifted")
    return tuple(sorted(rows, key=lambda row: row["cell_id"]))


def _resolution(freeze_root: Path) -> dict[str, Any]:
    qualification = _qualification(); schedule = _freeze().validate_frozen_root(Path(freeze_root)); private = schedule.get("private_source")
    if not isinstance(private, Mapping) or private.get("hanna_csv_sha256") != HANNA_CSV_SHA256:
        raise ValueError("Fresh96 HANNA source lineage drifted")
    return {"status": "qualified_measurement_only", "rows": _rows(Path(freeze_root)), "schedule": schedule, "qualification": qualification, "bindings": {"grok_result_commit": GROK_RESULT_COMMIT, "grok_result_sha256": GROK_RESULT_SHA256, "grok_result_verifier_sha256": GROK_RESULT_VERIFIER_SHA256, "grok_executor_commit": GROK_EXECUTOR_COMMIT, "grok_executor_sha256": GROK_EXECUTOR_SHA256, "grok_reconciler_commit": GROK_RECONCILER_COMMIT, "grok_reconciler_sha256": GROK_RECONCILER_SHA256, "grok_collector_sha256": str(qualification["source"]["collector_sha256"]), "hanna_csv_sha256": HANNA_CSV_SHA256, "replay_input_commitments": {"freeze_root": sha256(canonical(schedule)), "grok_result": GROK_RESULT_SHA256, "grok_result_verifier": GROK_RESULT_VERIFIER_SHA256, "grok_executor": GROK_EXECUTOR_SHA256, "grok_reconciler": GROK_RECONCILER_SHA256, "hanna_csv": HANNA_CSV_SHA256}}}


def validate_response_quality(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != {"scores", "evidence", "coverage"}:
        raise ValueError("Sol response schema drifted")
    scores, evidence, coverage = value["scores"], value["evidence"], value["coverage"]
    if not all(isinstance(item, Mapping) and set(item) == set(DIMENSIONS) for item in (scores, evidence, coverage)):
        raise ValueError("Sol response dimensions drifted")
    for dimension in DIMENSIONS:
        score, text, covered = scores[dimension], evidence[dimension], coverage[dimension]
        normalized = " ".join(text.split()).casefold() if isinstance(text, str) else ""
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(float(score)) or not 0 <= float(score) <= 5 or type(covered) is not bool or not normalized or normalized in {"x", "n/a", "na", "none", "missing", "redacted", "[placeholder]", "placeholder"} or len(normalized) < 3 or re.search(r"\b(?:search(?:ing)?|look(?:ing)?|inspect(?:ing)?) (?:the )?workspace\b|\bworkspace (?:search|lookup)\b", normalized) or normalized.startswith(("file:", "source:", "http:", "https:", "\\\\", "/", "./", "../", "see attached", "see workspace", "workspace:", "path:")):
            raise ValueError("Sol response evidence is unusable")
    return dict(value)


def _runtime(resolution: Mapping[str, Any]) -> tuple[ModuleType, ModuleType]:
    v9 = _load(V9, V9_SHA256, V9_COMMIT, "_v10_sol_v9_lifecycle")
    compatibility = dict(resolution)
    bindings = dict(resolution["bindings"])
    bindings.update({"result_analyzer_commit": GROK_RESULT_COMMIT, "result_analyzer_sha256": GROK_RESULT_VERIFIER_SHA256, "result_analyzer_contract_sha256": GROK_RESULT_VERIFIER_SHA256, "grok_result_internal_sha256": GROK_RESULT_SHA256, "grok_execution_commit": GROK_EXECUTOR_COMMIT, "parent_sol_reference": {"candidate_id": BASELINE, "comparison": "same_frozen_fresh96_confirmation_sol_only", "source": "v10_frozen_schedule"}})
    compatibility["bindings"] = bindings
    lifecycle, runtime = v9._configured_lifecycle(compatibility)
    lifecycle.STUDY_ID = STUDY_ID
    lifecycle.QUALIFIED_CHILDREN = (BASELINE, CHILD)
    lifecycle.PARENT_CANDIDATE_ID = BASELINE
    lifecycle.RESULT_FILE_SHA256 = GROK_RESULT_SHA256
    lifecycle.RESULT_INTERNAL_SHA256 = None
    runtime.STUDY_ID = STUDY_ID
    runtime.SOURCE_RESULT_FILE_SHA256 = GROK_RESULT_SHA256
    runtime.RESULT_INTERNAL_SHA256 = None
    original = runtime._validate_answer
    runtime._validate_answer = lambda value: validate_response_quality(original(value))
    inherited_prepared = runtime._prepared

    def prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
        files = inherited_prepared(row, payload, schema, target, route, evidence, acknowledgement)
        value = strict(files["prepared.json"], "inherited Sol preparation")
        source = dict(value["source"])
        for key in ("frozen_grok_qualifiers", "parent_sol_reference", "sol_role", "independently_replayed_grok_result_sha256", "independently_replayed_grok_result_internal_sha256", "result_analyzer_commit", "result_analyzer_sha256", "result_analyzer_contract_sha256"):
            source.pop(key, None)
        source.update({"v10_grok_qualification_result_sha256": GROK_RESULT_SHA256, "v10_grok_executor_sha256": GROK_EXECUTOR_SHA256, "v10_grok_reconciler_sha256": GROK_RECONCILER_SHA256, "hanna_csv_sha256": HANNA_CSV_SHA256, "sol_role": "measurement_only_after_grok_qualification", "endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "generalization": "none"})
        value["source"] = source
        files["prepared.json"] = runtime.canonical(value)
        return files

    runtime._prepared = prepared
    return lifecycle, runtime


def validate_package() -> dict[str, Any]:
    expected_files = {"README.md", "executor.py", "study-contract.json"}
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != expected_files:
        raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    required = {"authority": {"confirmation": "measurement_only", "endpoint_pooling": "forbidden", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "none", "sol": "validation_only_after_grok_qualification"}, "format_version": 1, "geometry": {"candidates": 2, "groups": 16, "items": 32, "max_concurrency": 10, "sol_cells": 64}, "kind": "fresh96_future_confirmation_paired_sol_validation_execution", "study_id": STUDY_ID}
    pins = {"freeze_commit": "1c10bae", "freeze_study_sha256": FREEZE_STUDY_SHA256, "grok_result_commit": GROK_RESULT_COMMIT, "grok_result_sha256": GROK_RESULT_SHA256, "grok_result_verifier_sha256": GROK_RESULT_VERIFIER_SHA256, "grok_executor_commit": GROK_EXECUTOR_COMMIT, "grok_executor_sha256": GROK_EXECUTOR_SHA256, "grok_reconciler_commit": GROK_RECONCILER_COMMIT, "grok_reconciler_sha256": GROK_RECONCILER_SHA256, "hanna_csv_sha256": HANNA_CSV_SHA256, "v9_sol_lifecycle_commit": V9_COMMIT, "v9_sol_lifecycle_sha256": V9_SHA256}
    if any(contract.get(key) != value for key, value in required.items()) or contract.get("pins") != pins: raise ValueError("study contract drifted")
    return contract


def prepare_all(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    validate_package(); resolution = _resolution(Path(freeze_root))
    if Path(output_root).exists(): raise ValueError("fresh output root required")
    lifecycle, runtime = _runtime(resolution); lifecycle._disjoint(Path(output_root), HERE, REPO, Path(queue_root), Path(freeze_root), GROK_RESULT)
    route, evidence, _v3 = runtime._route(Path(queue_root), broker_factory); Path(output_root).mkdir(parents=True)
    for row in resolution["rows"]:
        root = Path(output_root) / row["cell_id"]; root.mkdir(); payload = base64.b64decode(row["payload_base64"], validate=True); schema = runtime.canonical(json.loads(payload.decode("utf-8"))["response_schema"])
        for name, raw in runtime._prepared(row, payload, schema, row["target"], route, evidence, authorization_acknowledgement_sha256).items(): runtime._write_new(root / name, raw)
    return {"study_id": STUDY_ID, "state": "prepared_exact_64_paired_sol_measurement_cells", "cells": 64, "groups": 16, "provider_calls_made": 0, "process_launches": 0, "max_concurrency": MAX_CONCURRENCY}


def _disjoint(lifecycle: ModuleType, *paths: Path) -> None:
    lifecycle._disjoint(*(Path(path) for path in paths))


def _pending_rows(lifecycle: ModuleType, runtime: ModuleType, output_root: Path, rows: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
    entries = lifecycle._output_inventory(Path(output_root), rows)
    terminal_names = {"launch-intent.json", "execution-receipt.json", "result.json", "precontact-failure.json"}
    pending: list[Mapping[str, Any]] = []
    for row in rows:
        root = entries[str(row["cell_id"])]
        if any((root / name).exists() for name in terminal_names):
            continue
        runtime._inventory(root, completed=False)
        pending.append(row)
    return tuple(pending)


def execute_one(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> dict[str, Any]:
    validate_package()
    if allow_remote is not True: raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(Path(freeze_root)); lifecycle, runtime = _runtime(resolution); rows = {row["cell_id"]: row for row in resolution["rows"]}
    if cell_id not in rows: raise ValueError("unknown V10 Sol cell")
    _disjoint(lifecycle, Path(output_root), HERE, REPO, Path(queue_root), Path(freeze_root), GROK_RESULT, GROK_EXECUTOR, GROK_RECONCILER); lifecycle._prepared_inventory(runtime, Path(output_root), tuple(rows.values())); locks = lifecycle._locks(Path(output_root))
    try: return lifecycle._execute_prepared(base=runtime, row=rows[cell_id], output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
    finally:
        if locks.exists() and not any(locks.iterdir()): locks.rmdir()


def execute_wave(*, output_root: Path, freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., Any] | None = None) -> list[dict[str, Any]]:
    validate_package()
    if allow_remote is not True: raise ValueError("execution requires explicit allow_remote=True")
    resolution = _resolution(Path(freeze_root)); lifecycle, runtime = _runtime(resolution)
    _disjoint(lifecycle, Path(output_root), HERE, REPO, Path(queue_root), Path(freeze_root), GROK_RESULT, GROK_EXECUTOR, GROK_RECONCILER)
    pending = _pending_rows(lifecycle, runtime, Path(output_root), resolution["rows"])
    locks = lifecycle._locks(Path(output_root))
    try:
        def run(row: Mapping[str, Any]) -> dict[str, Any]: return lifecycle._execute_prepared(base=runtime, row=row, output_root=Path(output_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, locks=locks, broker_factory=broker_factory, call_codex=call_codex)
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool: return list(pool.map(run, pending))
    finally:
        if locks.exists() and not any(locks.iterdir()): locks.rmdir()


def _collector(*, output_root: Path, freeze_root: Path, acknowledgement: str) -> dict[str, Any]:
    resolution = _resolution(Path(freeze_root)); lifecycle, runtime = _runtime(resolution); entries = lifecycle._output_inventory(Path(output_root), resolution["rows"]); v4, cells, identities, route, evidence, normal_receipt_cells, reconciled_terminal_cells = lifecycle.sol_v4(), [], set(), None, None, 0, 0
    for row in resolution["rows"]:
        root = entries[row["cell_id"]]; names = {path.name for path in root.iterdir()}; normal, terminal = "execution-receipt.json" in names, "result.json" in names
        if normal == terminal: raise ValueError("each V10 Sol cell must contain exactly one normal receipt or terminal reconciliation")
        if normal:
            admitted = lifecycle._admit_completed_cell(runtime, v4, row, root, acknowledgement); normal_receipt_cells += 1
            cell = {"cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "admission": "normal_execution_receipt", "payload_base64": base64.b64encode(admitted["payload"]).decode(), "payload_sha256": sha256(admitted["payload"]), "final_response_base64": base64.b64encode(admitted["final"]).decode(), "final_response_sha256": sha256(admitted["final"]), "receipt_sha256": sha256(admitted["receipt"]), "identity": admitted["identity"], "effective_settings": admitted["settings"], "effective_settings_sha256": sha256(admitted["settings"]), "human_score_projection": admitted["answer"]}
        else:
            admitted = _admit_terminal_cell(lifecycle, runtime, row, root, acknowledgement); reconciled_terminal_cells += 1
            cell = {"cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "admission": "reconciled_terminal_final_message", "payload_base64": base64.b64encode(admitted["payload"]).decode(), "payload_sha256": sha256(admitted["payload"]), "final_response_base64": base64.b64encode(admitted["final"]).decode(), "final_response_sha256": sha256(admitted["final"]), "raw_events_sha256": sha256(admitted["events"]), "raw_stderr_sha256": sha256(admitted["stderr"]), "identity": admitted["identity"], "human_score_projection": admitted["answer"]}
        if admitted["identity_key"] in identities: raise ValueError("duplicate Sol lifecycle identity across normal and reconciled cells")
        identities.add(admitted["identity_key"]); route, evidence = route or admitted["route"], evidence or admitted["route_evidence"]
        if admitted["route"] != route or admitted["route_evidence"] != evidence: raise ValueError("Sol route/evidence differs across cells")
        cells.append(cell)
    if normal_receipt_cells + reconciled_terminal_cells != 64: raise ValueError("V10 Sol mixed collector geometry drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "complete_64_fresh96_paired_sol_mixed_receipts_terminal_reconciliation_cardinality_unproven", "authorization_acknowledgement_sha256": acknowledgement, "grok_qualification_sha256": GROK_RESULT_SHA256, "schedule_sha256": resolution["schedule"]["schedule_sha256"], "route": route, "route_evidence": evidence, "cells": cells, "normal_receipt_cells": normal_receipt_cells, "reconciled_terminal_cells": reconciled_terminal_cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": None, "process_launches": 0, "historical_process_launches": 64, "no_resend": True}


def _terminal_projection(events: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value: raise ValueError("duplicate key in Codex JSONL event")
            value[key] = item
        return value
    try:
        records = [json.loads(line, object_pairs_hook=pairs) for line in events.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("Codex JSONL events are unreadable") from error
    if len(records) < 4 or not all(isinstance(record, Mapping) for record in records): raise ValueError("Codex JSONL event count/type drifted")
    if [records[0].get("type"), records[1].get("type"), records[-1].get("type")] != ["thread.started", "turn.started", "turn.completed"]: raise ValueError("Codex terminal turn sequence drifted")
    thread_id = records[0].get("thread_id")
    if not isinstance(thread_id, str) or not thread_id or not isinstance(records[-1].get("usage"), Mapping): raise ValueError("Codex terminal identity/usage drifted")
    middle = records[2:-1]
    if any(record.get("type") not in {"item.started", "item.completed"} for record in middle): raise ValueError("Codex JSONL has nonterminal output after turn start")
    for record in middle:
        if record.get("type") == "item.started":
            item = record.get("item")
            if not isinstance(item, Mapping) or item.get("type") != "agent_message" or not isinstance(item.get("id"), str) or not item["id"] or item.get("text") != "": raise ValueError("Codex agent-message start sequence drifted")
    messages = [record.get("item") for record in middle if record.get("type") == "item.completed" and isinstance(record.get("item"), Mapping) and record["item"].get("type") == "agent_message"]
    if not messages or middle[-1].get("item") != messages[-1]: raise ValueError("final completed agent message is not the last output")
    final = messages[-1].get("text")
    if not isinstance(final, str): raise TypeError("final completed agent message lacks text")
    for interim in messages[:-1]:
        text = interim.get("text")
        if not isinstance(text, str): raise TypeError("interim agent message lacks text")
        value = _final_object(text.encode("utf-8"))
        if any(value["coverage"].get(name) is not False or value["scores"].get(name) != 0 for name in DIMENSIONS): raise ValueError("interim agent message is not non-authoritative zero coverage")
    return {"thread_id": thread_id, "usage": dict(records[-1]["usage"]), "completed_agent_message_text": final}


def _final_object(raw: bytes) -> dict[str, Any]:
    value = strict(raw + (b"\n" if not raw.endswith(b"\n") else b""), "reconciled final agent message")
    if canonical(value).rstrip(b"\n") != raw.rstrip(b"\n"):
        raise ValueError("reconciled final agent message formatting drifted")
    return value


def _admit_terminal_cell(lifecycle: ModuleType, runtime: ModuleType, row: Mapping[str, Any], root: Path, acknowledgement: str) -> dict[str, Any]:
    v4, v3 = lifecycle.sol_v4(), runtime._load_v3()
    required_before_read = {"prepared.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "target-vector.json", "outbound-payload.json", "response-schema.json", "launch-intent.json", "raw-codex-stderr.bin", "result.json", "responses"}
    if not required_before_read.issubset({path.name for path in root.iterdir()}): raise ValueError("terminal reconciliation inventory is incomplete")
    prepared = runtime._canonical_json(root / "prepared.json", "prepared")
    acknowledgement_file = runtime._canonical_json(root / "authorization-acknowledgement.json", "acknowledgement")
    proof = runtime._canonical_json(root / "zero-charge-route-proof.json", "route proof")
    target = runtime._canonical_json(root / "target-vector.json", "target vector")
    payload, schema = runtime.stable(root / "outbound-payload.json"), runtime.stable(root / "response-schema.json")
    route, evidence = v4._frozen_route(proof.get("route"), prepared.get("route_evidence"), v3, require_unexpired=False)
    expected = runtime._prepared(row, payload, schema, row["target"], route, evidence, acknowledgement)
    required = set(expected) | {"launch-intent.json", "raw-codex-stderr.bin", "result.json", "responses"}
    if {path.name for path in root.iterdir()} != required: raise ValueError("terminal reconciliation inventory drifted")
    if any(runtime.stable(root / name) != raw for name, raw in expected.items()) or acknowledgement_file.get("acknowledgement_sha256") != acknowledgement or target.get("target") != row["target"] or prepared.get("cell") != row or sha256(payload) != row["payload_sha256"]: raise ValueError("terminal prepared/payload binding drifted")
    intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared)}
    if runtime._canonical_json(root / "launch-intent.json", "launch intent") != intent: raise ValueError("terminal launch intent drifted")
    result = runtime._canonical_json(root / "result.json", "terminal result")
    if set(result) != {"format_version", "study_id", "kind", "cell_id", "process_launches", "provider_calls_made", "error_type"} or result != {**result, "format_version": 1, "study_id": STUDY_ID, "kind": "reconcile_required_after_process_launch", "cell_id": row["cell_id"], "process_launches": 1, "provider_calls_made": None} or not isinstance(result["error_type"], str) or not result["error_type"]: raise ValueError("terminal postlaunch result drifted")
    responses = root / "responses"
    if {path.name for path in responses.iterdir()} != {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"}: raise ValueError("terminal response inventory drifted")
    events, stderr = runtime.stable(responses / "batch-0001.attempt-0001.events.jsonl"), runtime.stable(root / "raw-codex-stderr.bin")
    projection = _terminal_projection(events); final = runtime.stable(responses / "batch-0001.attempt-0001.message.json")
    if projection["completed_agent_message_text"].encode("utf-8") != final: raise ValueError("terminal final event/message binding drifted")
    answer = validate_response_quality(_final_object(final)); labels = v3._strict_stderr_labels(stderr)
    if labels["session_id"] is not None and labels["session_id"] != projection["thread_id"]: raise ValueError("terminal stderr/session identity is misassociated")
    identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "reasoning_attested": False, "thread_id": projection["thread_id"], "session_id": f"local-codex-thread-session:{labels['session_id'] or projection['thread_id']}", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{projection['thread_id']}"}
    return {"payload": payload, "final": final, "events": events, "stderr": stderr, "answer": answer, "identity": identity, "identity_key": (identity["thread_id"], identity["session_id"], identity["contact_id"]), "route": route, "route_evidence": evidence}


def reconcile_existing_output(*, output_root: Path, freeze_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    """Recover final messages from terminal process evidence without any remote action."""
    validate_package(); resolution = _resolution(Path(freeze_root)); lifecycle, runtime = _runtime(resolution)
    _disjoint(lifecycle, Path(output_root), HERE, REPO, Path(freeze_root), GROK_RESULT, GROK_EXECUTOR, GROK_RECONCILER)
    entries = lifecycle._output_inventory(Path(output_root), resolution["rows"]); cells: list[dict[str, Any]] = []; identities: set[tuple[str, str, str]] = set(); route = evidence = None
    for row in resolution["rows"]:
        admitted = _admit_terminal_cell(lifecycle, runtime, row, entries[row["cell_id"]], authorization_acknowledgement_sha256)
        if admitted["identity_key"] in identities: raise ValueError("duplicate terminal lifecycle identity")
        identities.add(admitted["identity_key"]); route, evidence = route or admitted["route"], evidence or admitted["route_evidence"]
        if admitted["route"] != route or admitted["route_evidence"] != evidence: raise ValueError("terminal route/evidence differs across cells")
        cells.append({"cell_id": row["cell_id"], "source_cell_id": row["source_cell_id"], "candidate_id": row["candidate_id"], "payload_base64": row["payload_base64"], "payload_sha256": row["payload_sha256"], "final_response_base64": base64.b64encode(admitted["final"]).decode("ascii"), "final_response_sha256": sha256(admitted["final"]), "raw_events_sha256": sha256(admitted["events"]), "raw_stderr_sha256": sha256(admitted["stderr"]), "identity": admitted["identity"], "human_score_projection": admitted["answer"]})
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "reconciled_64_fresh96_paired_sol_final_messages_cardinality_unproven", "authorization_acknowledgement_sha256": authorization_acknowledgement_sha256, "grok_qualification_sha256": GROK_RESULT_SHA256, "schedule_sha256": resolution["schedule"]["schedule_sha256"], "route": route, "route_evidence": evidence, "cells": cells, "native_endpoint_contact_cardinality": "unproven", "provider_calls_made": 0, "process_launches": 0, "historical_process_launches": 64, "authority": {"endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none", "sol": "measurement_only"}}


def write_reconciled_collector(*, output_root: Path, freeze_root: Path, queue_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    validate_package()
    if Path(collector_output).exists(): raise ValueError("collector output must be fresh")
    lifecycle, runtime = _runtime(_resolution(Path(freeze_root)))
    _disjoint(lifecycle, Path(collector_output), HERE, REPO, Path(output_root), Path(queue_root), Path(freeze_root), GROK_RESULT, GROK_EXECUTOR, GROK_RECONCILER)
    value = reconcile_existing_output(output_root=Path(output_root), freeze_root=Path(freeze_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)
    runtime._write_new(Path(collector_output), canonical(value))
    return replay_reconciled_collector(output_root=Path(output_root), freeze_root=Path(freeze_root), collector_path=Path(collector_output), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)


def replay_reconciled_collector(*, output_root: Path, freeze_root: Path, collector_path: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    supplied = strict(stable(Path(collector_path)), "reconciled Sol collector")
    expected = reconcile_existing_output(output_root=Path(output_root), freeze_root=Path(freeze_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)
    if supplied != expected: raise ValueError("reconciled collector differs from terminal output")
    return {"study_id": STUDY_ID, "collector_sha256": sha256(supplied), "cells": 64, "provider_calls_made": 0, "process_launches": 0, "historical_process_launches": 64, "native_endpoint_contact_cardinality": "unproven", "equal_group_projection_ready": True, "authority": supplied["authority"]}


def finalize_collector(*, output_root: Path, freeze_root: Path, queue_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    validate_package()
    if Path(collector_output).exists(): raise ValueError("collector output must be fresh")
    lifecycle, runtime = _runtime(_resolution(Path(freeze_root)))
    _disjoint(lifecycle, Path(collector_output), HERE, REPO, Path(output_root), Path(queue_root), Path(freeze_root), GROK_RESULT, GROK_EXECUTOR, GROK_RECONCILER)
    value = _collector(output_root=Path(output_root), freeze_root=Path(freeze_root), acknowledgement=authorization_acknowledgement_sha256); runtime._write_new(Path(collector_output), canonical(value))
    return {"study_id": STUDY_ID, "collector_sha256": sha256(value), "cells": 64, "normal_receipt_cells": value["normal_receipt_cells"], "reconciled_terminal_cells": value["reconciled_terminal_cells"], "provider_calls_made": None, "process_launches": 0, "historical_process_launches": 64, "native_endpoint_contact_cardinality": "unproven", "no_resend": True}


def replay_collector(*, output_root: Path, freeze_root: Path, collector_path: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    validate_package(); supplied = strict(stable(Path(collector_path)), "Sol collector"); expected = _collector(output_root=Path(output_root), freeze_root=Path(freeze_root), acknowledgement=authorization_acknowledgement_sha256)
    if supplied != expected: raise ValueError("collector differs from persisted Sol receipts")
    return {"study_id": STUDY_ID, "collector_sha256": sha256(supplied), "cells": 64, "normal_receipt_cells": supplied["normal_receipt_cells"], "reconciled_terminal_cells": supplied["reconciled_terminal_cells"], "provider_calls_made": None, "process_launches": 0, "historical_process_launches": 64, "native_endpoint_contact_cardinality": "unproven", "no_resend": True, "authority": {"endpoint_pooling": "forbidden", "selection": "none", "promotion": "none", "runtime": "none", "generalization": "none"}}


if __name__ == "__main__":
    raise SystemExit("Use the callable API; provider execution requires an explicit reviewed invocation.")
