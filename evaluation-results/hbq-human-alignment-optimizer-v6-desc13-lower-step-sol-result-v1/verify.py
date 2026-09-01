from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-result-v1"
SOURCE_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-validation-exec-v1"
SOURCE_COMMIT = "f1a06c7a83aaf85e90030735360da33fd9fc2219"
SOURCE = HERE.parent / SOURCE_ID / "executor.py"
SOURCE_FILES = {
    "executor.py": "383ca581bf57af3a907541bb0cbc6f57e4bc2cdbecbcda0de37641a72c29af3d",
    "study-contract.json": "2f35d843baaa283e3a27eb12edf5d24649d746d7620956da7eda5bd1754ab7ef",
    "README.md": "edd2c55bb7ed64e20dba816b932be8adf94820ebeae5f5090db1074b4b6e4423",
}
GROK_ANALYZER_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v2-v3-exec"
GROK_ANALYZER_COMMIT = "7bf7923f36edee85c82000104b46a6f7f0f5f96d"
GROK_ANALYZER_SHA256 = "a080cfe32f44e9cca4536445fddaca9c0c79cad724d6a6365dadbeeecdc39b86"
GROK_RESULT_SHA256 = "7b31b817a324bb874f24e270b1446b03e142dc1ea0f71edf45da14504ce7d5a2"
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
BASELINE = "candidate-52d1be4bc34e0018"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
WINNER = "broader-nextwave-18-construct_framing-referent-resolution"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
AUTHORITY = {"selection": "grok_development_only", "sol": "descriptive_validation_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}
CEILING = {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 21, "provider_calls_made": None}
README_SHA256 = "87f11f34e259cf72c7ff6bc14b66a0d4591a007e2781dc304bf1e122c98a7fe5"
PERSISTED_RESULT_SHA256 = "da575fc017c461ecfd0756a50265387b8a5b4145cdfaf3b21d32020410371047"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode()


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe(path: Path, directory: bool | None = None) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if not current.exists():
            raise ValueError("required path is absent")
        _plain(current, current != absolute or directory)
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(path, False); before = os.lstat(path)
    with path.open("rb") as handle:
        raw = handle.read(); opened = os.fstat(handle.fileno())
    after = os.lstat(path)
    identity = lambda item: (item.st_dev, item.st_ino, stat.S_IFMT(item.st_mode), item.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        answer: dict[str, Any] = {}
        for key, value in items:
            if key in answer: raise ValueError(f"duplicate key in {label}")
            answer[key] = value
        return answer
    try: value = json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error: raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw: raise ValueError(f"noncanonical {label}")
    return value


def _tree(path: Path) -> str:
    root = _safe(path)
    if root.is_file(): return sha256({"file": root.name, "sha256": sha256(stable(root))})
    records = []
    for child in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        info = os.lstat(child); directory = stat.S_ISDIR(info.st_mode); _plain(child, directory)
        records.append({"path": child.relative_to(root).as_posix(), "directory": directory, **({} if directory else {"sha256": sha256(stable(child))})})
    return sha256(records)


def _blob(relative: str) -> bytes:
    run = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{relative}"], capture_output=True, check=False)
    if run.returncode: raise ValueError("pinned source blob is absent")
    return run.stdout


def _source() -> ModuleType:
    admitted: dict[str, bytes] = {}
    for name, digest in SOURCE_FILES.items():
        raw = stable(SOURCE.parent / name)
        if sha256(raw) != digest or _blob(f"evaluation-results/{SOURCE_ID}/{name}") != raw: raise ValueError("pinned Sol executor drifted")
        admitted[name] = raw
    analyzer = HERE.parent / GROK_ANALYZER_ID / "verify.py"
    run = subprocess.run(["git", "-C", str(REPO), "show", f"{GROK_ANALYZER_COMMIT}:evaluation-results/{GROK_ANALYZER_ID}/verify.py"], capture_output=True, check=False)
    if run.returncode or sha256(stable(analyzer)) != GROK_ANALYZER_SHA256 or run.stdout != stable(analyzer): raise ValueError("pinned Grok analyzer drifted")
    module = ModuleType("_desc13_sol_result_source"); module.__file__ = str(SOURCE); sys.modules[module.__name__] = module
    try: exec(compile(admitted["executor.py"], str(SOURCE), "exec"), module.__dict__)  # noqa: S102
    finally: sys.modules.pop(module.__name__, None)
    if stable(SOURCE) != admitted["executor.py"]: raise ValueError("pinned Sol executor changed during load")
    return module


def _metrics(values: dict[str, dict[str, float]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if set(values) != {BASELINE, PARENT, WINNER} or any(len(groups) != 7 for groups in values.values()): raise ValueError("incomplete equal-group geometry")
    rows = [{"candidate_id": candidate, "cells": 7, "equal_group_mae": sum(groups.values()) / 7, "group_mae": dict(sorted(groups.items()))} for candidate, groups in values.items()]
    rows.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"])); index = {row["candidate_id"]: row for row in rows}
    if index[BASELINE]["equal_group_mae"] <= 0 or index[PARENT]["equal_group_mae"] <= 0: raise ValueError("invalid comparison baseline")
    def compare(left: str, right: str) -> dict[str, Any]:
        delta = index[right]["equal_group_mae"] - index[left]["equal_group_mae"]
        return {"from_candidate_id": left, "from_equal_group_mae": index[left]["equal_group_mae"], "to_candidate_id": right, "to_equal_group_mae": index[right]["equal_group_mae"], "absolute_delta": delta, "relative_reduction": -delta / index[left]["equal_group_mae"]}
    return rows, {"baseline_to_parent": compare(BASELINE, PARENT), "parent_to_winner": compare(PARENT, WINNER), "baseline_to_winner": compare(BASELINE, WINNER)}


def replay(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    validate_package()
    source = _source()
    inputs = {"candidate_freeze_root": Path(candidate_freeze_root), "development_freeze_root": Path(development_freeze_root), "normalized_root": Path(normalized_root), "materialization_root": Path(materialization_root), "frozen_successor_path": Path(frozen_successor_path), "hanna_csv_path": Path(hanna_csv_path), "grok_execution_root": Path(grok_execution_root), "grok_collector_path": Path(grok_collector_path), "grok_result_path": Path(grok_result_path), "output_root": Path(output_root)}
    committed = {name: _tree(path) for name, path in sorted(inputs.items())}
    if sha256(stable(Path(grok_result_path))) != GROK_RESULT_SHA256: raise ValueError("wrong immutable Grok result")
    resolution = source._resolve(**{name: inputs[name] for name in inputs if name != "output_root"})
    if resolution["selection"]["selection"]["candidate_id"] != WINNER or resolution["bindings"]["grok_result_sha256"] != GROK_RESULT_SHA256: raise ValueError("Grok winner/result replay drifted")
    base = source._configured_base(resolution); root = _safe(Path(output_root), True); rows = {row["cell_id"]: row for row in resolution["rows"]}
    if len(rows) != 21 or {path.name for path in root.iterdir()} != set(rows): raise ValueError("completed Sol root inventory drifted")
    values: dict[str, dict[str, float]] = {BASELINE: {}, PARENT: {}, WINNER: {}}; identities: set[tuple[str, str, str]] = set(); commitments = []
    v3 = base._load_v3(); v4 = source.sol_v4(); route_value = evidence_value = None
    for cell_id, row in rows.items():
        cell = root / cell_id; base._inventory(cell, completed=True)
        prepared = strict(stable(cell / "prepared.json"), "prepared"); disclosure = strict(stable(cell / "disclosure.json"), "disclosure"); acknowledgement = strict(stable(cell / "authorization-acknowledgement.json"), "acknowledgement")
        proof = strict(stable(cell / "zero-charge-route-proof.json"), "route proof"); receipt = strict(stable(cell / "execution-receipt.json"), "receipt")
        intent = strict(stable(cell / "launch-intent.json"), "launch intent"); settings = strict(stable(cell / "effective-settings.json"), "effective settings")
        record = strict(stable(cell / "codex-record.json"), "Codex record"); target_file = strict(stable(cell / "target-vector.json"), "target vector")
        payload, schema = stable(cell / "outbound-payload.json"), stable(cell / "response-schema.json")
        final, events, stderr = stable(cell / "raw-codex-final-response.bin"), stable(cell / "raw-codex-events.bin"), stable(cell / "raw-codex-stderr.bin")
        if final != stable(cell / "responses" / "batch-0001.attempt-0001.message.json") or events != stable(cell / "responses" / "batch-0001.attempt-0001.events.jsonl"): raise ValueError("persisted final/message event binding drifted")
        projection = v3._codex_event_projection(events, v3._load_parse_codex_events()); answer = base._validate_answer(base._json(cell / "raw-codex-final-response.bin", "native final message"))
        route, evidence = v4._frozen_route(proof.get("route"), prepared.get("route_evidence"), v3, require_unexpired=False)
        expected = base._prepared(row, payload, schema, row["target"], route, evidence, ACK)
        expected_settings = {"requested_model":"gpt-5.6-sol","local_effective_model":"gpt-5.6-sol","requested_reasoning_effort":"high","local_effective_reasoning_effort":"high","tools_enabled":False,"web_search_enabled":False,"subagents_enabled":False,"provider_attested":False,"event_projection":projection,"route_name":route["name"],"codex_command_identity":route["codex_command_identity"]}
        identity = {"provider":"openai_codex","route_name":route["name"],"requested_model":"gpt-5.6-sol","requested_reasoning_effort":"high","effective_model":"gpt-5.6-sol","provider_reported_model":None,"reasoning_attested":False,"transport_identity":"codex_chatgpt_subscription_exec_tool_free_v3","native_endpoint_contact_cardinality":"unproven","thread_id":projection.get("thread_id"),"session_id":f"local-codex-thread-session:{projection.get('thread_id')}","contact_id":f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}"}
        expected_intent = {"format_version":1,"study_id":SOURCE_ID,"kind":"process_launch_intent_not_native_contact","cell_id":cell_id,"prepared_sha256":sha256(prepared)}
        expected_receipt = {"format_version":1,"study_id":SOURCE_ID,"kind":"local_codex_lifecycle_receipt","cell":dict(row),"process_launches":1,"provider_calls_made":None,"native_endpoint_contact_cardinality":"unproven","internal_retry_cardinality":"unproven","request_sha256":sha256(payload),"response_schema_sha256":sha256(schema),"raw_events_sha256":sha256(events),"raw_stderr_sha256":sha256(stderr),"final_response_sha256":sha256(final),"route_evidence":evidence,"effective_settings_sha256":sha256(settings),"launch_intent_sha256":sha256(stable(cell / "launch-intent.json")),"identity":identity,"human_score_projection":answer}
        expected_record = {"command":v3._expected_codex_command(route["codex_command"][0],cell),"provider_artifacts":{"codex_events":{"path":"responses/batch-0001.attempt-0001.events.jsonl","bytes":len(events),"sha256":sha256(events)},"codex_stderr":{"path":"raw-codex-stderr.bin","bytes":len(stderr),"sha256":sha256(stderr)}},"reported":{"model":None,"provider":None,"reasoning_effort":None,"session_id":None}}
        key = (identity["thread_id"], identity["session_id"], identity["contact_id"])
        if route_value is None: route_value, evidence_value = route, evidence
        if (route != route_value or evidence != evidence_value or any(stable(cell / name) != raw for name, raw in expected.items()) or disclosure.get("study_id") != SOURCE_ID or acknowledgement.get("acknowledgement_sha256") != ACK or proof.get("route") != route or proof.get("route_evidence") != evidence or target_file.get("target") != row["target"] or intent != expected_intent or sha256(payload) != row["payload_sha256"] or prepared.get("cell") != row or settings != expected_settings or record != expected_record or receipt != expected_receipt or projection.get("completed_agent_message_text", "").encode() != final or len(key) != 3 or not all(isinstance(item, str) and item for item in key) or key in identities):
            raise ValueError("lifecycle/native-score/identity binding drifted")
        identities.add(key); commitments.append({"cell_id": cell_id, "prepared_sha256": sha256(prepared), "receipt_sha256": sha256(receipt), "final_response_sha256": sha256(final), "events_sha256": sha256(events)})
        scores = answer.get("scores")
        if not isinstance(scores, Mapping) or set(scores) != set(DIMS): raise ValueError("native score dimensions drifted")
        values[row["candidate_id"]][row["prompt_group_id"]] = sum(abs(float(scores[key]) - float(row["target"][key])) for key in DIMS) / len(DIMS)
    if {name: _tree(path) for name, path in sorted(inputs.items())} != committed: raise ValueError("replay input changed during result reconstruction")
    if len(identities) != 21: raise ValueError("duplicate/missing lifecycle identity")
    metrics, comparison = _metrics(values)
    source_execution = {"sol_executor_commit": SOURCE_COMMIT, "sol_executor_sha256": SOURCE_FILES["executor.py"], "grok_analyzer_commit": GROK_ANALYZER_COMMIT, "grok_analyzer_sha256": GROK_ANALYZER_SHA256, "grok_result_sha256": GROK_RESULT_SHA256, "grok_result_internal_sha256": resolution["bindings"]["grok_result_internal_sha256"], "grok_collector_sha256": resolution["bindings"]["grok_collector_sha256"], "sol_schedule_sha256": resolution["schedule"]["schedule_sha256"], "receipt_chain_sha256": sha256(sorted(commitments, key=lambda item: item["cell_id"])), "input_commitments": committed}
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "twenty_one_cell_desc13_lower_step_sol_result", "authority": AUTHORITY, "claim": "DESCRIPTIVE_SOL_VALIDATION_ONLY; no pooling, selection, generalization, confirmation, promotion, or runtime claim", "evidence_ceiling": CEILING, "metrics": metrics, "comparison": comparison, "source_execution": source_execution}


def write_result(path: Path, result: dict[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink(): raise ValueError("result path must be fresh")
    _safe(target.parent, True)
    with target.open("xb") as handle: handle.write(canonical(result))


def validate_package() -> None:
    _plain(HERE, True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != {"README.md", "result.json", "study-contract.json", "verify.py"}: raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract"); result = strict(stable(HERE / "result.json"), "result")
    expected_contract = {"authority":AUTHORITY,"format_version":1,"geometry":{"candidates":3,"cells":21,"groups":7},"kind":"provider_free_desc13_lower_step_sol_result_replay","pins":{"grok_analyzer_commit":GROK_ANALYZER_COMMIT,"grok_analyzer_sha256":GROK_ANALYZER_SHA256,"grok_result_sha256":GROK_RESULT_SHA256,"sol_executor_commit":SOURCE_COMMIT,"sol_executor_sha256":SOURCE_FILES["executor.py"]},"prohibitions":["no caller aggregate","no imputation","no pooling or promotion claim","no runtime optimizer dependency"],"study_id":STUDY_ID}
    if contract != expected_contract or sha256(stable(HERE / "result.json")) != PERSISTED_RESULT_SHA256 or sha256(stable(HERE / "README.md")) != README_SHA256 or result.get("study_id") != STUDY_ID: raise ValueError("package contract/result drifted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-free replay of the completed 21-cell Sol lower-step validation.")
    for name in ("output-root", "candidate-freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "result-output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    validate_package()
    result = replay(output_root=args.output_root, candidate_freeze_root=args.candidate_freeze_root, development_freeze_root=args.development_freeze_root, normalized_root=args.normalized_root, materialization_root=args.materialization_root, frozen_successor_path=args.frozen_successor, hanna_csv_path=args.hanna_csv, grok_execution_root=args.grok_execution_root, grok_collector_path=args.grok_collector, grok_result_path=args.grok_result)
    write_result(args.result_output, result); print(canonical({"cells": 21, "provider_calls_made": 0, "result_sha256": sha256(result)}).decode(), end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
