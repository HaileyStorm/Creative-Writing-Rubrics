#!/usr/bin/env python3
"""Four-cell, descriptive-only Sol follow-up for the published v5 Grok readout."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import csv
import io
import math
from types import ModuleType
from typing import Any, Callable, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-grok-descriptive-sol-validation-exec-v1"
PUBLIC_RESULT_COMMIT = "f20f8178112bb92c8acc084dcb6d08cdcef3c3bb"
PUBLIC_RESULT = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-result-v1" / "result.json"
SOURCE_RESULT_FILE_SHA256 = "ba43a42d7959ae184cb1bd341062a82bac49a04a39f68e5af1bf0405d9c4ce3d"
SOURCE_EXECUTOR_COMMIT = "856451a906ff387ead4d7627b28a5418c8a52f83"
SOURCE_EXECUTOR = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1" / "executor.py"
SOURCE_EXECUTOR_SHA256 = "331c9749e29779de450f83871cf9b23001e1d705227f3b4d0b0de8a650292079"
SCHEDULE_SHA256 = "5056e681cbcef92aef3335ed58d7a20dabf3a8c4b962f5e463752ce827d39104"
COLLECTOR_SHA256 = "4af3adcfabf4410e895468e929f368bbfb0f20fbf834df767a2fb646fd0b6809"
ALIAS_MANIFEST_SHA256 = "fe79880e3d3a719255784900e21c28d04caa5f849649d1327658971b7f86d35f"
RESULT_INTERNAL_SHA256 = "c3da5428731bf85da13e3aaa10f36a4407a4efc8deb232b0e473913b5237a7d6"
V3_EXECUTOR = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3" / "executor.py"
V3_EXECUTOR_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
PREPARED = frozenset({"outbound-payload.json", "response-schema.json", "target-vector.json", "disclosure.json", "authorization-acknowledgement.json", "zero-charge-route-proof.json", "prepared.json"})
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
TARGET_CSV = Path(r"C:\Users\Haile\Documents\cwr-hanna-pinned-data-282f275\hanna_stories_annotations.csv")
TARGET_CSV_SHA256 = "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"

# These rows identify published Grok payloads, not a new selection surface.
ROWS = (
    {"cell_id": "sol-v5-descriptive-baseline-g1", "source_cell_id": "mixed-shrinkage-cell-4e2c82330254b7ec", "candidate_id": "candidate-102cc7f06c9a99a7", "prompt_group_id": "prompt-7c393c4bcb3a7484", "item_id": "item-2377fcf24510aac5", "story_id": "813", "payload_sha256": "b83151f2befc01004b560f9492d7df52786113c4c2cf5b7307fb9f5cf6cf12cc", "target": {"Relevance": 5/3, "Coherence": 5/3, "Empathy": 1.0, "Surprise": 5/3, "Engagement": 1.0, "Complexity": 1.0}},
    {"cell_id": "sol-v5-descriptive-baseline-g2", "source_cell_id": "mixed-shrinkage-cell-c356bfea797c9b9c", "candidate_id": "candidate-102cc7f06c9a99a7", "prompt_group_id": "prompt-8997770ce6efe4d5", "item_id": "item-0cb9c7afe8527434", "story_id": "567", "payload_sha256": "42917fe83f126b81b4dc654537b98e47498f158a1048c4704b7bdaa094a43f8a", "target": {"Relevance": 4/3, "Coherence": 10/3, "Empathy": 5/3, "Surprise": 8/3, "Engagement": 3.0, "Complexity": 8/3}},
    {"cell_id": "sol-v5-descriptive-low-g1", "source_cell_id": "mixed-shrinkage-cell-6d8fec359a711302", "candidate_id": "candidate-69720ac6257db007", "prompt_group_id": "prompt-7c393c4bcb3a7484", "item_id": "item-2377fcf24510aac5", "story_id": "813", "payload_sha256": "d46b0503130cadcf5ccb3b4ef64ae70f2d7c0108bf2763d54ad479e47bfed765", "target": {"Relevance": 5/3, "Coherence": 5/3, "Empathy": 1.0, "Surprise": 5/3, "Engagement": 1.0, "Complexity": 1.0}},
    {"cell_id": "sol-v5-descriptive-low-g2", "source_cell_id": "mixed-shrinkage-cell-438c09ad65eb4a22", "candidate_id": "candidate-69720ac6257db007", "prompt_group_id": "prompt-8997770ce6efe4d5", "item_id": "item-0cb9c7afe8527434", "story_id": "567", "payload_sha256": "ab262c9de71fa144245b777c8a115698c08fe060b366deb044356ae3391ecdfb", "target": {"Relevance": 4/3, "Coherence": 10/3, "Empathy": 5/3, "Surprise": 8/3, "Engagement": 3.0, "Complexity": 8/3}},
)
SCHEMA_SHA256 = "a91e6a8d619c93e70e981fdee6c564a35d0b2c5b6bc1e8afe9b7ab314fe2225a"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(raw: bytes | Any) -> str:
    return hashlib.sha256(raw if isinstance(raw, bytes) else canonical(raw)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError(f"unsafe/reparsed path: {path}")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError(f"unexpected path type: {path}")


def stable(path: Path) -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part; _plain(current, directory=current != path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("file changed during stable read")
    return raw


def _json(path: Path, label: str) -> dict[str, Any]:
    try: value = json.loads(stable(path).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict): raise ValueError(f"{label} must be an object")
    return value


def _canonical_json(path: Path, label: str) -> dict[str, Any]:
    raw = stable(path); value = _json(path, label)
    if canonical(value) != raw: raise ValueError(f"{label} is not canonical")
    return value


def _git_blob(commit: str, relative: str) -> bytes:
    completed = subprocess.run(["git", "-C", str(HERE.parents[1]), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if completed.returncode != 0 or not completed.stdout: raise ValueError("pinned Git source is unavailable")
    return completed.stdout


def _validate_target(row: Mapping[str, Any], hanna_csv_path: Path) -> dict[str, float]:
    raw = stable(Path(hanna_csv_path))
    if sha(raw) != TARGET_CSV_SHA256: raise ValueError("pinned HANNA target CSV drifted")
    try: rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as error: raise ValueError("pinned HANNA target CSV is invalid") from error
    matching = [item for item in rows if item.get("Story ID") == row["story_id"]]
    if len(matching) != 3: raise ValueError("frozen HANNA target row cardinality drifted")
    target: dict[str, float] = {}
    for dimension in DIMENSIONS:
        values = []
        for item in matching:
            value = item.get(dimension)
            try: number = float(value)
            except (TypeError, ValueError) as error: raise ValueError("frozen HANNA target is nonnumeric") from error
            if not math.isfinite(number) or isinstance(value, bool): raise ValueError("frozen HANNA target is nonfinite")
            values.append(number)
        target[dimension] = sum(values) / len(values)
    if target != row["target"]: raise ValueError("frozen HANNA target vector drifted")
    return target


def _validate_answer(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != {"scores", "evidence", "coverage"}: raise ValueError("Sol final object schema drifted")
    scores, evidence, coverage = value.get("scores"), value.get("evidence"), value.get("coverage")
    if (not isinstance(scores, dict) or not isinstance(evidence, dict) or not isinstance(coverage, dict)
            or set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS) or set(coverage) != set(DIMENSIONS)):
        raise ValueError("Sol final object dimensions drifted")
    for dimension in DIMENSIONS:
        score = scores[dimension]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 5:
            raise ValueError("Sol final score type/range drifted")
        if not isinstance(evidence[dimension], str) or not evidence[dimension] or not isinstance(coverage[dimension], bool):
            raise ValueError("Sol final evidence/coverage type drifted")
    return dict(value)


def _overlaps(left: Path, right: Path) -> bool:
    left, right = left.resolve(), right.resolve()
    return left == right or left in right.parents or right in left.parents


def _safe_output_root(output_root: Path, source_root: Path, queue_root: Path) -> None:
    output = Path(output_root)
    for path in (Path(source_root), Path(queue_root), HERE, HERE.parents[1]):
        if _overlaps(output, path): raise ValueError("output root must be disjoint from source, queue, and repository paths")
    parent = output.parent
    while True:
        _plain(parent, directory=True)
        if parent == parent.parent: break
        parent = parent.parent


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink(): raise ValueError(f"refuses overwrite: {path.name}")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle: handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _load_v3() -> ModuleType:
    raw = stable(V3_EXECUTOR)
    if sha(raw) != V3_EXECUTOR_SHA256: raise ValueError("pinned v3 Sol executor drifted")
    module = ModuleType("_hanna_v5_sol_validation_v3"); module.__file__ = str(V3_EXECUTOR); sys.modules[module.__name__] = module
    try: exec(compile(raw, str(V3_EXECUTOR), "exec"), module.__dict__)
    finally: sys.modules.pop(module.__name__, None)
    if stable(V3_EXECUTOR) != raw: raise ValueError("pinned v3 Sol executor changed during load")
    return module


def _source_row(row: Mapping[str, Any], source_root: Path) -> tuple[bytes, bytes]:
    prepared = _json(Path(source_root) / row["source_cell_id"] / "prepared.json", "published source preparation")
    payload = stable(Path(source_root) / row["source_cell_id"] / "outbound-payload.json")
    schema = stable(Path(source_root) / row["source_cell_id"] / "response-schema.json")
    if (sha(payload) != row["payload_sha256"] or sha(schema) != SCHEMA_SHA256 or prepared.get("outbound_payload_sha256") != sha(payload)
            or prepared.get("response_schema_sha256") != sha(schema) or prepared.get("cell", {}).get("candidate_id") != row["candidate_id"]
            or prepared.get("cell", {}).get("prompt_group_id") != row["prompt_group_id"] or prepared.get("cell", {}).get("item_id") != row["item_id"]):
        raise ValueError("published payload/source lineage drifted")
    return payload, schema


def _route(queue_root: Path, broker_factory: Callable[[Path], Any] | None) -> tuple[dict[str, Any], dict[str, Any], ModuleType]:
    v3 = _load_v3(); route, evidence = v3.validate_live_sol_route(Path(queue_root), broker_factory=broker_factory)
    if (route.get("name") != "codex-chatgpt-gpt-5.6-sol" or route.get("model") != "gpt-5.6-sol" or route.get("reasoning_effort") != "high"
            or route.get("zero_charge") is not True or route.get("health") != "healthy" or not isinstance(route.get("codex_command"), list) or len(route["codex_command"]) != 1):
        raise ValueError("current governed Sol/high route is invalid")
    return dict(route), dict(evidence), v3


def _inventory(root: Path, *, callback: bool = False, completed: bool = False) -> None:
    _plain(root, directory=True); children = {p.name: p for p in root.iterdir()}
    expected = set(PREPARED)
    if callback: expected.add("responses")
    if completed: expected |= {"responses", "launch-intent.json", "raw-codex-events.bin", "raw-codex-final-response.bin", "raw-codex-stderr.bin", "codex-record.json", "effective-settings.json", "execution-receipt.json"}
    if set(children) != expected: raise ValueError("root inventory has missing, extra, or unsafe artifacts")
    for name, path in children.items(): _plain(path, directory=name == "responses")
    if callback and any((root / "responses").iterdir()): raise ValueError("callback-time responses residue is not empty")
    if completed:
        responses = root / "responses"; expected_response = {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"}
        if {p.name for p in responses.iterdir()} != expected_response: raise ValueError("completed response inventory drifted")
        for child in responses.iterdir(): _plain(child, directory=False)


def _prepared(row: Mapping[str, Any], payload: bytes, schema: bytes, target: Mapping[str, float], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9a-f]{64}", acknowledgement): raise ValueError("acknowledgement must be lowercase SHA-256")
    disclosure = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell": dict(row), "destination": route["destination"], "route_name": route["name"], "task_payload_sha256": sha(payload), "response_schema_sha256": sha(schema), "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    authorization = {"format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": acknowledgement, "disclosure_sha256": sha(disclosure)}
    proof = {"format_version": 1, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "cell_id": row["cell_id"], "route": dict(route), "route_evidence": dict(evidence), "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}
    target_file = {"format_version": 1, "study_id": STUDY_ID, "cell_id": row["cell_id"], "item_id": row["item_id"], "story_id": row["story_id"], "hanna_csv_sha256": TARGET_CSV_SHA256, "target": dict(target)}
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "descriptive_sol_validation_preparation", "cell": dict(row), "source": {"public_result_commit": PUBLIC_RESULT_COMMIT, "source_result_file_sha256": SOURCE_RESULT_FILE_SHA256, "source_executor_commit": SOURCE_EXECUTOR_COMMIT, "source_executor_sha256": SOURCE_EXECUTOR_SHA256, "schedule_sha256": SCHEDULE_SHA256, "collector_sha256": COLLECTOR_SHA256, "alias_manifest_sha256": ALIAS_MANIFEST_SHA256, "result_internal_sha256": RESULT_INTERNAL_SHA256}, "route_evidence": dict(evidence), "route_command": route["codex_command"][0], "task_payload_sha256": sha(payload), "response_schema_sha256": sha(schema), "target_vector_sha256": sha(target_file), "disclosure_sha256": sha(disclosure), "authorization_sha256": sha(authorization), "route_proof_sha256": sha(proof), "tools_enabled": False, "provider_calls_made": 0, "process_launches": 0}
    return {"outbound-payload.json": payload, "response-schema.json": schema, "target-vector.json": canonical(target_file), "disclosure.json": canonical(disclosure), "authorization-acknowledgement.json": canonical(authorization), "zero-charge-route-proof.json": canonical(proof), "prepared.json": canonical(prepared)}


def prepare_all(*, output_root: Path, source_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, hanna_csv_path: Path = TARGET_CSV, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    _safe_output_root(Path(output_root), Path(source_root), Path(queue_root))
    public_raw = _git_blob(PUBLIC_RESULT_COMMIT, "evaluation-results/hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-result-v1/result.json")
    if stable(PUBLIC_RESULT) != public_raw: raise ValueError("checked-out public result differs from pinned commit")
    executor_raw = _git_blob(SOURCE_EXECUTOR_COMMIT, "evaluation-results/hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-live-exec-v1/executor.py")
    if sha(executor_raw) != SOURCE_EXECUTOR_SHA256: raise ValueError("pinned source executor commitment drifted")
    public = json.loads(public_raw.decode("utf-8"))
    source = public.get("source_artifacts", {})
    if (public.get("result_sha256") != RESULT_INTERNAL_SHA256 or source.get("executor_commit") != SOURCE_EXECUTOR_COMMIT
            or source.get("executor_sha256") != SOURCE_EXECUTOR_SHA256 or source.get("schedule_sha256") != SCHEDULE_SHA256
            or source.get("collector_file_sha256") != COLLECTOR_SHA256 or source.get("alias_manifest_sha256") != ALIAS_MANIFEST_SHA256
            or source.get("result_file_sha256") != SOURCE_RESULT_FILE_SHA256):
        raise ValueError("published source commitment drifted")
    if Path(output_root).exists(): raise ValueError("fresh output root required")
    route, evidence, _v3 = _route(queue_root, broker_factory); Path(output_root).mkdir(parents=True)
    _plain(Path(output_root), directory=True)
    for row in ROWS:
        payload, schema = _source_row(row, Path(source_root)); target = _validate_target(row, Path(hanna_csv_path)); root = Path(output_root) / row["cell_id"]; root.mkdir(); _plain(root, directory=True)
        for name, raw in _prepared(row, payload, schema, target, route, evidence, authorization_acknowledgement_sha256).items(): _write_new(root / name, raw)
    return {"cells": 4, "state": "prepared_no_contact", "provider_calls_made": 0, "process_launches": 0, "authority": "descriptive_validation_only"}


def _row(cell_id: str) -> dict[str, Any]:
    matches = [dict(row) for row in ROWS if row["cell_id"] == cell_id]
    if len(matches) != 1: raise ValueError("unknown validation cell")
    return matches[0]


def _verify_prepared(root: Path, row: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], acknowledgement: str, *, callback: bool = False, hanna_csv_path: Path = TARGET_CSV) -> tuple[dict[str, Any], bytes, bytes]:
    _inventory(root, callback=callback); prepared = _json(root / "prepared.json", "preparation")
    payload, schema = stable(root / "outbound-payload.json"), stable(root / "response-schema.json")
    expected = _prepared(row, payload, schema, _validate_target(row, Path(hanna_csv_path)), route, evidence, acknowledgement)
    if any(stable(root / name) != raw for name, raw in expected.items()): raise ValueError("prepared bindings drifted")
    return prepared, payload, schema


def _finalize(*, root: Path, row: Mapping[str, Any], prepared: Mapping[str, Any], route: Mapping[str, Any], evidence: Mapping[str, Any], payload: bytes, schema: bytes, content: str, record: Mapping[str, Any], v3: ModuleType) -> dict[str, Any]:
    artifacts = record.get("provider_artifacts", {})
    events_ref, stderr_ref = artifacts.get("codex_events"), artifacts.get("codex_stderr")
    if list(record.get("command", [])) != v3._expected_codex_command(route["codex_command"][0], root): raise ValueError("command binding drifted")
    def artifact(ref: Mapping[str, Any]) -> bytes:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("path"), str): raise ValueError("artifact reference invalid")
        path = root / ref["path"]; raw = stable(path)
        if ref.get("bytes") != len(raw) or ref.get("sha256") != sha(raw): raise ValueError("artifact commitment drifted")
        return raw
    events, stderr = artifact(events_ref), artifact(stderr_ref); projection = v3._codex_event_projection(events, v3._load_parse_codex_events()); final = stable(root / "responses" / "batch-0001.attempt-0001.message.json")
    if content.encode("utf-8") != final or projection.get("completed_agent_message_text", "").encode("utf-8") != final: raise ValueError("raw final-message projection drifted")
    answer = _validate_answer(_json(root / "responses" / "batch-0001.attempt-0001.message.json", "final Sol message"))
    settings = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_attested": False, "event_projection": projection, "route_name": route["name"], "codex_command_identity": route["codex_command_identity"]}
    thread_id = projection.get("thread_id")
    if not isinstance(thread_id, str) or not thread_id: raise ValueError("Sol lifecycle thread identity is absent")
    identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3", "native_endpoint_contact_cardinality": "unproven", "thread_id": thread_id, "session_id": f"local-codex-thread-session:{thread_id}", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{thread_id}"}
    receipt = {"format_version": 1, "study_id": STUDY_ID, "kind": "local_codex_lifecycle_receipt", "cell": dict(row), "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": sha(payload), "response_schema_sha256": sha(schema), "raw_events_sha256": sha(events), "raw_stderr_sha256": sha(stderr), "final_response_sha256": sha(final), "route_evidence": dict(evidence), "effective_settings_sha256": sha(settings), "launch_intent_sha256": sha(stable(root / "launch-intent.json")), "identity": identity, "human_score_projection": answer}
    for name, raw in (("raw-codex-events.bin", events), ("raw-codex-final-response.bin", final), ("codex-record.json", canonical(dict(record))), ("effective-settings.json", canonical(settings)), ("execution-receipt.json", canonical(receipt))): _write_new(root / name, raw)
    _inventory(root, completed=True); return receipt


def execute_one(*, output_root: Path, cell_id: str, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, hanna_csv_path: Path = TARGET_CSV, broker_factory: Callable[[Path], Any] | None = None, call_codex: Callable[..., tuple[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    if allow_remote is not True: raise ValueError("execution requires explicit allow_remote=True")
    row, root = _row(cell_id), Path(output_root) / cell_id
    if any((root / name).exists() for name in ("launch-intent.json", "execution-receipt.json", "result.json", "precontact-failure.json")): raise ValueError("no resend: use a fresh output root")
    route, evidence, v3 = _route(queue_root, broker_factory); prepared, payload, schema = _verify_prepared(root, row, route, evidence, authorization_acknowledgement_sha256, hanna_csv_path=hanna_csv_path); launches = 0
    def before_provider_attempt() -> None:
        nonlocal launches
        if launches: raise ValueError("launch callback repeated")
        fresh_route, fresh_evidence, _ = _route(queue_root, broker_factory)
        if fresh_route != route or fresh_evidence != evidence: raise ValueError("route drifted adjacent to launch")
        _verify_prepared(root, row, route, evidence, authorization_acknowledgement_sha256, callback=True, hanna_csv_path=hanna_csv_path)
        _write_new(root / "launch-intent.json", canonical({"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": cell_id, "prepared_sha256": sha(prepared)})); launches = 1
    invoke = call_codex or v3._load_call_codex()
    try:
        content, record = invoke(executable=route["codex_command"][0], model="gpt-5.6-sol", reasoning="high", prompt=payload.decode("utf-8"), output_dir=root, response_schema=root / "response-schema.json", batch_number=1, timeout=float(route["timeout_seconds"]), attempt_number=1, before_provider_attempt=before_provider_attempt, capture_jsonl_events=True)
        if launches != 1: raise ValueError("launch callback was not called exactly once")
        receipt = _finalize(root=root, row=row, prepared=prepared, route=route, evidence=evidence, payload=payload, schema=schema, content=content, record=record, v3=v3)
    except BaseException as error:
        if launches:
            _write_new(root / "result.json", canonical({"format_version": 1, "study_id": STUDY_ID, "kind": "reconcile_required_after_process_launch", "cell_id": cell_id, "process_launches": 1, "provider_calls_made": None, "error_type": type(error).__name__})); return {"cell_id": cell_id, "state": "reconcile_required_after_process_launch", "process_launches": 1, "provider_calls_made": None}
        raise
    return {"cell_id": cell_id, "state": "local_codex_lifecycle_received_native_contact_unproven", "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": receipt["native_endpoint_contact_cardinality"]}


def project_descriptive(*, output_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, hanna_csv_path: Path = TARGET_CSV, broker_factory: Callable[[Path], Any] | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{64}", authorization_acknowledgement_sha256): raise ValueError("exact authorization acknowledgement is required")
    output_root = Path(output_root); _plain(output_root, directory=True)
    entries = list(output_root.iterdir())
    if {entry.name for entry in entries} != {row["cell_id"] for row in ROWS}:
        raise ValueError("output-root inventory has missing, extra, or unsafe artifacts")
    for entry in entries: _plain(entry, directory=True)
    route, live_evidence, live_v3 = _route(Path(queue_root), broker_factory)
    values: dict[str, list[float]] = {"candidate-102cc7f06c9a99a7": [], "candidate-69720ac6257db007": []}
    identities: set[tuple[str, str, str]] = set()
    for row in ROWS:
        root = Path(output_root) / row["cell_id"]; _inventory(root, completed=True)
        prepared = _canonical_json(root / "prepared.json", "preparation"); disclosure = _canonical_json(root / "disclosure.json", "disclosure"); authorization = _canonical_json(root / "authorization-acknowledgement.json", "authorization"); proof = _canonical_json(root / "zero-charge-route-proof.json", "route proof"); target_file = _canonical_json(root / "target-vector.json", "target vector")
        receipt = _canonical_json(root / "execution-receipt.json", "receipt"); settings = _canonical_json(root / "effective-settings.json", "effective settings"); record = _canonical_json(root / "codex-record.json", "Codex record")
        payload, schema, final, events, stderr = stable(root / "outbound-payload.json"), stable(root / "response-schema.json"), stable(root / "raw-codex-final-response.bin"), stable(root / "raw-codex-events.bin"), stable(root / "raw-codex-stderr.bin")
        expected_source = {"public_result_commit": PUBLIC_RESULT_COMMIT, "source_result_file_sha256": SOURCE_RESULT_FILE_SHA256, "source_executor_commit": SOURCE_EXECUTOR_COMMIT, "source_executor_sha256": SOURCE_EXECUTOR_SHA256, "schedule_sha256": SCHEDULE_SHA256, "collector_sha256": COLLECTOR_SHA256, "alias_manifest_sha256": ALIAS_MANIFEST_SHA256, "result_internal_sha256": RESULT_INTERNAL_SHA256}
        if (payload != stable(root / "outbound-payload.json") or sha(payload) != row["payload_sha256"] or sha(schema) != SCHEMA_SHA256
                or target_file != {"format_version": 1, "study_id": STUDY_ID, "cell_id": row["cell_id"], "item_id": row["item_id"], "story_id": row["story_id"], "hanna_csv_sha256": TARGET_CSV_SHA256, "target": _validate_target(row, Path(hanna_csv_path))}
                or prepared.get("format_version") != 1 or prepared.get("study_id") != STUDY_ID or prepared.get("kind") != "descriptive_sol_validation_preparation" or prepared.get("cell") != row or prepared.get("source") != expected_source
                or prepared.get("route_command") != route["codex_command"][0] or prepared.get("route_evidence") != live_evidence or prepared.get("task_payload_sha256") != sha(payload) or prepared.get("response_schema_sha256") != sha(schema)
                or prepared.get("target_vector_sha256") != sha(target_file) or prepared.get("disclosure_sha256") != sha(disclosure) or prepared.get("authorization_sha256") != sha(authorization) or prepared.get("route_proof_sha256") != sha(proof)
                or prepared.get("tools_enabled") is not False or prepared.get("provider_calls_made") != 0 or prepared.get("process_launches") != 0
                or disclosure != {"format_version": 1, "study_id": STUDY_ID, "kind": "local_first_exact_outbound_disclosure", "cell": row, "destination": "openai_codex_chatgpt_subscription", "route_name": "codex-chatgpt-gpt-5.6-sol", "task_payload_sha256": sha(payload), "response_schema_sha256": sha(schema), "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_calls_made": 0, "process_launches": 0}
                or authorization != {"format_version": 1, "study_id": STUDY_ID, "kind": "authorization_acknowledgement_reference", "cell_id": row["cell_id"], "acknowledgement_sha256": authorization_acknowledgement_sha256, "disclosure_sha256": sha(disclosure)}
                or proof != {"format_version": 1, "study_id": STUDY_ID, "kind": "current_zero_charge_route_proof", "cell_id": row["cell_id"], "route": route, "route_evidence": live_evidence, "zero_charge_only": True, "paid_fallback_forbidden": True, "provider_calls_made": 0, "process_launches": 0}):
            raise ValueError("prepared source artifact binding drifted")
        v3 = live_v3; projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        answer = _validate_answer(_json(root / "raw-codex-final-response.bin", "raw final Sol message"))
        intent = _canonical_json(root / "launch-intent.json", "launch intent")
        if (intent != {"format_version": 1, "study_id": STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha(prepared)}
                or receipt.get("native_endpoint_contact_cardinality") != "unproven" or receipt.get("cell") != row
                or receipt.get("request_sha256") != sha(payload) or receipt.get("response_schema_sha256") != sha(schema)
                or receipt.get("raw_events_sha256") != sha(events) or receipt.get("raw_stderr_sha256") != sha(stderr)
                or receipt.get("final_response_sha256") != sha(final) or receipt.get("effective_settings_sha256") != sha(settings)
                or receipt.get("launch_intent_sha256") != sha(stable(root / "launch-intent.json")) or receipt.get("human_score_projection") != answer
                or receipt.get("format_version") != 1 or receipt.get("study_id") != STUDY_ID or receipt.get("kind") != "local_codex_lifecycle_receipt"
                or receipt.get("process_launches") != 1 or receipt.get("provider_calls_made") is not None or receipt.get("internal_retry_cardinality") != "unproven"
                or receipt.get("route_evidence") != prepared.get("route_evidence")
                or final != stable(root / "responses" / "batch-0001.attempt-0001.message.json")
                or projection.get("completed_agent_message_text", "").encode("utf-8") != final):
            raise ValueError("receipt evidence ceiling/binding drifted")
        if (settings.get("requested_model") != "gpt-5.6-sol" or settings.get("local_effective_model") != "gpt-5.6-sol"
                or settings.get("requested_reasoning_effort") != "high" or settings.get("local_effective_reasoning_effort") != "high"
                or any(settings.get(flag) is not False for flag in ("tools_enabled", "web_search_enabled", "subagents_enabled"))
                or settings.get("provider_attested") is not False or settings.get("event_projection") != projection or settings.get("route_name") != route["name"] or settings.get("codex_command_identity") != route["codex_command_identity"]):
            raise ValueError("effective settings binding drifted")
        artifacts = record.get("provider_artifacts", {})
        if (not isinstance(artifacts, dict) or list(record.get("command", [])) != v3._expected_codex_command(prepared["route_command"], root)
                or artifacts.get("codex_events") != {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha(events)}
                or artifacts.get("codex_stderr") != {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha(stderr)}):
            raise ValueError("Codex record artifact binding drifted")
        identity = receipt.get("identity", {})
        key = (identity.get("thread_id"), identity.get("session_id"), identity.get("contact_id"))
        expected_identity = (projection.get("thread_id"), f"local-codex-thread-session:{projection.get('thread_id')}", f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}")
        if (identity.get("provider") != "openai_codex" or identity.get("route_name") != "codex-chatgpt-gpt-5.6-sol" or identity.get("requested_model") != "gpt-5.6-sol"
                or identity.get("requested_reasoning_effort") != "high" or identity.get("effective_model") != "gpt-5.6-sol" or identity.get("provider_reported_model") is not None
                or identity.get("reasoning_attested") is not False or identity.get("transport_identity") != "codex_chatgpt_subscription_exec_tool_free_v3" or identity.get("native_endpoint_contact_cardinality") != "unproven"
                or key != expected_identity or not all(isinstance(value, str) and value for value in key) or key in identities):
            raise ValueError("duplicate or absent Sol lifecycle identity")
        identities.add(key)
        scores, target = answer["scores"], target_file["target"]
        values[row["candidate_id"]].append(sum(abs(scores[dimension] - target[dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS))
    if any(len(value) != 2 for value in values.values()): raise ValueError("two-group geometry is incomplete")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "two_group_equal_group_sol_mae_descriptive_only", "metrics": {key: sum(value) / 2 for key, value in values.items()}, "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "confirmation": "unopened", "general_hanna": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-root", type=Path, required=True); parser.add_argument("--source-root", type=Path); parser.add_argument("--queue-root", type=Path); parser.add_argument("--hanna-csv-path", type=Path, default=TARGET_CSV); parser.add_argument("--authorization-acknowledgement-sha256"); parser.add_argument("--prepare", action="store_true"); parser.add_argument("--execute-one"); parser.add_argument("--project", action="store_true"); parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    if args.prepare: result = prepare_all(output_root=args.output_root, source_root=args.source_root, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, hanna_csv_path=args.hanna_csv_path)
    elif args.execute_one: result = execute_one(output_root=args.output_root, cell_id=args.execute_one, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, allow_remote=args.allow_remote, hanna_csv_path=args.hanna_csv_path)
    elif args.project: result = project_descriptive(output_root=args.output_root, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, hanna_csv_path=args.hanna_csv_path)
    else: parser.error("select --prepare, --execute-one, or --project")
    print(canonical(result).decode(), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
