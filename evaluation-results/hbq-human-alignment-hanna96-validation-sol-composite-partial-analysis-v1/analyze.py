#!/usr/bin/env python3
"""Provider-free composite analysis of two immutable partial Fresh96 Sol roots."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-hanna96-validation-sol-composite-partial-analysis-v1"
EXECUTOR = HERE.parent / "hbq-human-alignment-hanna96-validation-sol-exec-v1" / "executor.py"
FREEZE = HERE.parent / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
PUBLIC_RESULT = HERE / "result.json"
EXECUTOR_SHA256 = "3bcc05b3f201b234419f4288a5bd183cd4de53b138b9ee6841356dffc58ac7f0"
FREEZE_SHA256 = "d8b99c651cfbc0c04207101a6ad15373168a5ffad3711f7d17fb589e8a13542e"
PUBLIC_RESULT_SHA256 = "967d3f8c372d95b3eec61e9bf7fdf4b3680a29dfdcc8c8e446553fcefcff786a"
PUBLIC_RESULT_SELF_SHA256 = "cf0da171a1d26fed20f26e562791ea60a1de7ce8c22995dce7514852d6a83715"
SOURCE_COMMIT = "c280729bd2382fadd442b023845239b1056348e5"
SCHEDULE_SHA256 = "639c34bb1d07266759280249b6b74a51c05d51f60ed27eb3aed0b2ea6c3bfee2"
BASELINE = "candidate-102cc7f06c9a99a7"
DESCENDANT = "broader-nextwave-13-missing_evidence_not_no"
UNCOVERED = "h96-sol-h96-dd7a8fa6fd9e44a66497"
ACKNOWLEDGEMENT = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
PREPARED = {"authorization-acknowledgement.json", "disclosure.json", "outbound-payload.json", "prepared.json", "response-schema.json", "target-vector.json", "zero-charge-route-proof.json"}
SUCCESS = PREPARED | {"responses", "codex-record.json", "effective-settings.json", "execution-receipt.json", "launch-intent.json", "raw-codex-events.bin", "raw-codex-final-response.bin", "raw-codex-stderr.bin"}
AMBIGUOUS = PREPARED | {"responses", "launch-intent.json", "raw-codex-stderr.bin", "result.json"}
REPORTED_COMPATIBILITY = {"model": None, "provider": None, "reasoning_effort": None, "session_id": None}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed artifact")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected artifact type")


def _safe(path: Path, directory: bool | None = None) -> Path:
    value = Path(os.path.abspath(path))
    current = Path(value.anchor)
    for part in value.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("required artifact is absent")
        _plain(current, current != value or directory)
    return value


def stable(path: Path) -> bytes:
    path = _safe(Path(path), False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def strict(path: Path, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result
    try:
        value = json.loads(stable(path).decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != stable(path):
        raise ValueError(f"noncanonical {label}")
    return value


def _inventory(path: Path, expected: set[str], label: str) -> None:
    _plain(path, True)
    if {entry.name for entry in path.iterdir()} != expected:
        raise ValueError(f"{label} inventory drifted")


def _pin(path: Path, expected: str, relative: str) -> None:
    raw = stable(path)
    shown = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{relative}"], capture_output=True, check=False)
    if sha256(raw) != expected or shown.returncode or shown.stdout != raw:
        raise ValueError("pinned dependency drifted")


def validate_package() -> dict[str, Any]:
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != {"README.md", "analyze.py", "result.json", "study-contract.json"}:
        raise ValueError("package inventory drifted")
    contract = strict(HERE / "study-contract.json", "study contract")
    expected = {"authority": {"confirmation": "none", "generalization": "none", "imputation": "forbidden", "pooling": "forbidden", "runtime": "none", "selection": "none"}, "compatibility": {"codex_record_reported": "exact_all_null_in_memory_projection_only"}, "format_version": 1, "geometry": {"A_success": 57, "A_unstarted": 7, "B_success": 60, "B_terminal_ambiguous": 4, "fully_complete_groups": 15, "logical_receipt_backed_cells": 63, "paired_groups": 16, "paired_items": 31, "repeat_success_overlap": 54, "scheduled_cells": 64, "uncovered_cells": 1}, "kind": "strict_sol_fresh96_composite_partial_analysis_contract", "pins": {"execution_wrapper": {"commit": SOURCE_COMMIT, "path": "hbq-human-alignment-hanna96-validation-sol-exec-v1/executor.py", "sha256": EXECUTOR_SHA256}, "freeze": {"path": "hbq-human-alignment-hanna96-validation-freeze-v1/study.py", "sha256": FREEZE_SHA256}, "public_result": {"result_sha256": PUBLIC_RESULT_SELF_SHA256, "sha256": PUBLIC_RESULT_SHA256}, "schedule_sha256": SCHEDULE_SHA256}, "study_id": STUDY_ID}
    if contract != expected:
        raise ValueError("study contract drifted")
    raw = stable(PUBLIC_RESULT)
    result = strict(PUBLIC_RESULT, "public result")
    if sha256(raw) != PUBLIC_RESULT_SHA256 or result.get("result_sha256") != PUBLIC_RESULT_SELF_SHA256:
        raise ValueError("public result byte or self-commitment drifted")
    recomputed = dict(result)
    recomputed.pop("result_sha256", None)
    if sha256(recomputed) != PUBLIC_RESULT_SELF_SHA256:
        raise ValueError("public result self-commitment recomputation drifted")
    return contract


def _disjoint(output: Path, *sources: Path) -> None:
    output = Path(os.path.abspath(output))
    _safe(output.parent, True)
    for source in (*sources, REPO):
        source = _safe(Path(source), True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("result output must be disjoint from source roots and repository")


def _executor_context(frozen_root: Path) -> tuple[ModuleType, ModuleType, dict[str, dict[str, Any]]]:
    _pin(EXECUTOR, EXECUTOR_SHA256, "evaluation-results/hbq-human-alignment-hanna96-validation-sol-exec-v1/executor.py")
    _pin(FREEZE, FREEZE_SHA256, "evaluation-results/hbq-human-alignment-hanna96-validation-freeze-v1/study.py")
    raw = stable(EXECUTOR)
    executor = ModuleType("_pinned_fresh96_sol_executor")
    executor.__file__ = str(EXECUTOR)
    sys.modules[executor.__name__] = executor
    try:
        exec(compile(raw, str(EXECUTOR), "exec"), executor.__dict__)  # noqa: S102 -- exact SHA and Git blob are bound.
        resolution = executor._resolve(frozen_root=_safe(Path(frozen_root), True))
        base = executor._configured_base(resolution)
    finally:
        sys.modules.pop(executor.__name__, None)
    if stable(EXECUTOR) != raw or resolution["schedule_sha256"] != SCHEDULE_SHA256:
        raise ValueError("pinned Sol executor or Fresh96 schedule drifted")
    rows = {row["cell_id"]: dict(row) for row in resolution["rows"]}
    if len(rows) != 64 or {row["candidate_id"] for row in rows.values()} != {BASELINE, DESCENDANT}:
        raise ValueError("pinned Fresh96 row geometry drifted")
    return executor, base, rows


def _success(base: ModuleType, root: Path, row: Mapping[str, Any], identities: set[tuple[str, str, str]]) -> float:
    base._inventory(root, completed=True)
    prepared = base._canonical_json(root / "prepared.json", "prepared")
    proof = base._canonical_json(root / "zero-charge-route-proof.json", "route proof")
    payload, schema = base.stable(root / "outbound-payload.json"), base.stable(root / "response-schema.json")
    route, evidence = proof.get("route"), prepared.get("route_evidence")
    if not isinstance(route, Mapping) or not isinstance(evidence, Mapping):
        raise TypeError("prepared route binding drifted")
    expected = base._prepared(row, payload, schema, row["target"], route, evidence, ACKNOWLEDGEMENT)
    final, events, stderr = (base.stable(root / name) for name in ("raw-codex-final-response.bin", "raw-codex-events.bin", "raw-codex-stderr.bin"))
    receipt = base._canonical_json(root / "execution-receipt.json", "receipt")
    settings = base._canonical_json(root / "effective-settings.json", "effective settings")
    record = base._canonical_json(root / "codex-record.json", "Codex record")
    intent = base._canonical_json(root / "launch-intent.json", "launch intent")
    v3 = base._load_v3()
    projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
    answer = base._validate_answer(base._json(root / "raw-codex-final-response.bin", "final response"))
    identity = receipt.get("identity", {})
    key = (identity.get("thread_id"), identity.get("session_id"), identity.get("contact_id"))
    expected_settings = {"requested_model": "gpt-5.6-sol", "local_effective_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "local_effective_reasoning_effort": "high", "tools_enabled": False, "web_search_enabled": False, "subagents_enabled": False, "provider_attested": False, "event_projection": projection, "route_name": route["name"], "codex_command_identity": route["codex_command_identity"]}
    expected_record = {"command": v3._expected_codex_command(route["codex_command"][0], root), "provider_artifacts": {"codex_events": {"path": "responses/batch-0001.attempt-0001.events.jsonl", "bytes": len(events), "sha256": sha256(events)}, "codex_stderr": {"path": "raw-codex-stderr.bin", "bytes": len(stderr), "sha256": sha256(stderr)}}}
    expected_identity = {"provider": "openai_codex", "route_name": route["name"], "requested_model": "gpt-5.6-sol", "requested_reasoning_effort": "high", "effective_model": "gpt-5.6-sol", "provider_reported_model": None, "reasoning_attested": False, "transport_identity": "codex_chatgpt_subscription_exec_tool_free_v3", "native_endpoint_contact_cardinality": "unproven", "thread_id": projection.get("thread_id"), "session_id": f"local-codex-thread-session:{projection.get('thread_id')}", "contact_id": f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}"}
    expected_intent = {"format_version": 1, "study_id": base.STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared)}
    expected_receipt = {"format_version": 1, "study_id": base.STUDY_ID, "kind": "local_codex_lifecycle_receipt", "cell": dict(row), "process_launches": 1, "provider_calls_made": None, "native_endpoint_contact_cardinality": "unproven", "internal_retry_cardinality": "unproven", "request_sha256": sha256(payload), "response_schema_sha256": sha256(schema), "raw_events_sha256": sha256(events), "raw_stderr_sha256": sha256(stderr), "final_response_sha256": sha256(final), "route_evidence": evidence, "effective_settings_sha256": sha256(settings), "launch_intent_sha256": sha256(base.stable(root / "launch-intent.json")), "identity": expected_identity, "human_score_projection": answer}
    if set(record) != {"command", "provider_artifacts", "reported"} or record["reported"] != REPORTED_COMPATIBILITY:
        raise ValueError("codex record compatibility ceiling drifted")
    projected_record = {key: record[key] for key in expected_record}
    if (any(base.stable(root / name) != raw for name, raw in expected.items()) or sha256(payload) != row["payload_sha256"] or prepared.get("cell") != row
            or intent != expected_intent or settings != expected_settings or projected_record != expected_record or receipt != expected_receipt
            or final != base.stable(root / "responses" / "batch-0001.attempt-0001.message.json") or events != base.stable(root / "responses" / "batch-0001.attempt-0001.events.jsonl")
            or projection.get("completed_agent_message_text", "").encode() != final or not all(isinstance(value, str) and value for value in key) or key in identities):
        raise ValueError("pinned Sol admission/projection binding drifted")
    identities.add(key)
    return sum(abs(answer["scores"][dimension] - row["target"][dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS)


def _state(base: ModuleType, root: Path, row: Mapping[str, Any], identities: set[tuple[str, str, str]]) -> tuple[str, float | None]:
    names = {entry.name for entry in root.iterdir()}
    if names == SUCCESS:
        return "success", _success(base, root, row, identities)
    if names == set(base.PREPARED):
        payload, schema = base.stable(root / "outbound-payload.json"), base.stable(root / "response-schema.json")
        prepared, proof = (base._canonical_json(root / name, name) for name in ("prepared.json", "zero-charge-route-proof.json"))
        expected = base._prepared(row, payload, schema, row["target"], proof["route"], prepared["route_evidence"], ACKNOWLEDGEMENT)
        if any(base.stable(root / name) != raw for name, raw in expected.items()):
            raise ValueError("pristine prepared binding drifted")
        return "unstarted", None
    if names == AMBIGUOUS:
        payload, schema = base.stable(root / "outbound-payload.json"), base.stable(root / "response-schema.json")
        prepared, proof = (base._canonical_json(root / name, name) for name in ("prepared.json", "zero-charge-route-proof.json"))
        expected = base._prepared(row, payload, schema, row["target"], proof["route"], prepared["route_evidence"], ACKNOWLEDGEMENT)
        if any(base.stable(root / name) != raw for name, raw in expected.items()):
            raise ValueError("terminal prepared binding drifted")
        _inventory(root / "responses", {"batch-0001.attempt-0001.events.jsonl", "batch-0001.attempt-0001.message.json"}, "ambiguous response")
        intent, result = (base._canonical_json(root / name, name) for name in ("launch-intent.json", "result.json"))
        expected_intent = {"format_version": 1, "study_id": base.STUDY_ID, "kind": "process_launch_intent_not_native_contact", "cell_id": row["cell_id"], "prepared_sha256": sha256(prepared)}
        expected_result = {"cell_id": row["cell_id"], "error_type": "ValueError", "format_version": 1, "kind": "reconcile_required_after_process_launch", "process_launches": 1, "provider_calls_made": None, "study_id": base.STUDY_ID}
        if intent != expected_intent or result != expected_result:
            raise ValueError("ambiguous terminal drifted")
        return "ambiguous", None
    raise ValueError("cell inventory is neither prepared, successful, nor terminal ambiguous")


def _metric(observations: list[tuple[str, str, str, float]], groups: set[str], label: str) -> dict[str, Any]:
    values: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for candidate, item, group, mae in observations:
        if group in groups:
            values[candidate][group].append(mae)
    if set(values) != {BASELINE, DESCENDANT} or any(set(candidate) != groups for candidate in values.values()):
        raise ValueError("paired coverage drifted")
    means = {candidate: sum(sum(values[candidate][group]) / len(values[candidate][group]) for group in groups) / len(groups) for candidate in values}
    return {"subset": label, "groups": len(groups), "paired_items": len({item for _candidate, item, group, _mae in observations if group in groups}), "baseline_equal_group_mae": means[BASELINE], "descendant13_equal_group_mae": means[DESCENDANT], "percent_reduction": (means[BASELINE] - means[DESCENDANT]) * 100 / means[BASELINE]}


def analyze(root_a: Path, root_b: Path, frozen_root: Path) -> dict[str, Any]:
    validate_package()
    _executor, base, rows = _executor_context(Path(frozen_root))
    sources = (("B", _safe(Path(root_b), True)), ("A", _safe(Path(root_a), True)))
    identities: set[tuple[str, str, str]] = set()
    states: dict[str, dict[str, tuple[str, float | None]]] = {}
    for name, root in sources:
        _inventory(root, set(rows), f"source {name}")
        states[name] = {cell: _state(base, root / cell, row, identities) for cell, row in rows.items()}
    selected: list[tuple[str, str, str, float]] = []
    source_counts = {"A": defaultdict(int), "B": defaultdict(int)}
    repeats = 0
    uncovered: list[str] = []
    for cell, row in rows.items():
        b, a = states["B"][cell], states["A"][cell]
        if a[0] == b[0] == "success":
            repeats += 1
        pick = b if b[0] == "success" else a if a[0] == "success" else None
        if pick is None:
            uncovered.append(cell)
        else:
            source = "B" if b[0] == "success" else "A"
            source_counts[source]["selected"] += 1
            selected.append((str(row["candidate_id"]), str(row["item_id"]), str(row["prompt_group_id"]), float(pick[1])))
    state_counts = {name: {state: sum(value[0] == state for value in values.values()) for state in ("success", "unstarted", "ambiguous")} for name, values in states.items()}
    if len(selected) != 63 or uncovered != [UNCOVERED] or repeats != 54 or state_counts != {"B": {"success": 60, "unstarted": 0, "ambiguous": 4}, "A": {"success": 57, "unstarted": 7, "ambiguous": 0}}:
        raise ValueError("expected composite coverage drifted")
    per_item: dict[str, list[tuple[str, str, str, float]]] = defaultdict(list)
    for observation in selected:
        per_item[observation[1]].append(observation)
    paired = [row for pairs in per_item.values() if len(pairs) == 2 for row in pairs]
    if len(paired) != 62 or len(per_item) != 32:
        raise ValueError("composite item pairing drifted")
    groups = {row[2] for row in paired}
    complete = {group for group in groups if sum(row[2] == group for row in paired) == 4}
    if len(groups) != 16 or len(complete) != 15:
        raise ValueError("composite group geometry drifted")
    result = {"format_version": 1, "study_id": STUDY_ID, "kind": "strict_sol_fresh96_composite_partial_validation_analysis", "source": {"source_commit": SOURCE_COMMIT, "schedule_sha256": SCHEDULE_SHA256, "execution_wrapper_sha256": EXECUTOR_SHA256, "freeze_sha256": FREEZE_SHA256, "precedence": "B_then_A"}, "coverage": {"scheduled_cells": 64, "receipt_backed_logical_cells": 63, "uncovered_logical_cells": 1, "A": {"success": 57, "unstarted": 7}, "B": {"success": 60, "terminal_ambiguous": 4}, "repeat_success_overlap": 54, "selected_from_A": source_counts["A"]["selected"], "selected_from_B": source_counts["B"]["selected"], "paired_items": 31, "paired_groups": 16, "fully_complete_groups": 15, "native_endpoint_contact_cardinality": "unproven"}, "metrics": [_metric(paired, groups, "all_31_paired_items",), _metric([row for row in paired if row[2] in complete], complete, "15_fully_complete_groups")], "authority": {"endpoint": "gpt-5.6-sol", "imputation": "forbidden", "pooling": "forbidden", "selection": "none", "confirmation": "none", "generalization": "none", "runtime": "none"}, "interpretation": "Fresh endpoint-specific partial composite only: B takes precedence, A fills only B non-successes, one logical cell remains uncovered, and repeats are never pooled."}
    result["result_sha256"] = sha256(result)
    return result


def write_result(root_a: Path, root_b: Path, frozen_root: Path, output: Path) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise ValueError("result output must be fresh")
    _disjoint(output, Path(root_a), Path(root_b), Path(frozen_root))
    value = analyze(root_a, root_b, frozen_root)
    with output.open("xb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root-a", type=Path, required=True)
    parser.add_argument("--root-b", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--result-output", type=Path, required=True)
    args = parser.parse_args()
    write_result(args.root_a, args.root_b, args.frozen_root, args.result_output)
