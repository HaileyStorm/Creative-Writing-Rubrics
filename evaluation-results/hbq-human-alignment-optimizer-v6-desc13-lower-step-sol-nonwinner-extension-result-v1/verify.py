from __future__ import annotations

import argparse
import hashlib
import json
import math
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
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-nonwinner-extension-result-v1"
SOURCE_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-sol-nonwinner-extension-exec-v1"
SOURCE_COMMIT = "5f4fbe1f3fe9e52a2c2082495a2d2e9ff973d9d4"
SOURCE = HERE.parent / SOURCE_ID
SOURCE_FILES = {
    "executor.py": "da7b95115265d6c7a7eda1d1893357d871c08e353b53caccbbae516ac40df8e4",
    "study-contract.json": "d999e4cdf877020a04396cde167c27864ed03c14584d4701a0e7314b1f6a8408",
    "README.md": "a66cf8f6435245f81aa04d67390c091e67aa52a72bf6ef38b6fd16fa5c8754f0",
}
ACK = "2fb371ff82b37fe22d238a223fc030ad7a7bb9a10b672719da081470d25dbe78"
CHILDREN = (
    "broader-nextwave-15-construct_framing-speaker-attribution",
    "broader-nextwave-16-scope_materiality-temporal-causality",
    "broader-nextwave-17-scope_materiality-sustained-stakes",
)
BASELINE = "candidate-52d1be4bc34e0018"
PARENT = "broader-nextwave-13-missing_evidence_not_no"
DIMS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
AUTHORITY = {
    "selection": "none",
    "sol": "descriptive_extension_only",
    "confirmation": "unopened",
    "generalization": "none",
    "promotion": "none",
    "runtime": "none",
    "endpoint_pooling": "forbidden",
}
CEILING = {
    "native_endpoint_contact_cardinality": "unproven",
    "process_lifecycle_receipts": 21,
    "provider_calls_made": None,
}
PERSISTED_RESULT_SHA256 = "15da35133fa66b1a0b862338508267fc7c1e76d9f41e021687dcb4b3365cdadc"


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
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def native_json(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode(), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict:
        raise ValueError(f"invalid {label}")
    return value


def _tree(path: Path) -> str:
    root = _safe(path)
    if root.is_file():
        return sha256({"file": root.name, "sha256": sha256(stable(root))})
    records = []
    for child in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        directory = stat.S_ISDIR(os.lstat(child).st_mode); _plain(child, directory)
        records.append({"path": child.relative_to(root).as_posix(), "directory": directory, **({} if directory else {"sha256": sha256(stable(child))})})
    return sha256(records)


def _blob(relative: str) -> bytes:
    run = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{relative}"], capture_output=True, check=False)
    if run.returncode:
        raise ValueError("pinned source blob is absent")
    return run.stdout


def _source() -> ModuleType:
    admitted: dict[str, bytes] = {}
    for name, digest in SOURCE_FILES.items():
        raw = stable(SOURCE / name)
        if sha256(raw) != digest or _blob(f"evaluation-results/{SOURCE_ID}/{name}") != raw:
            raise ValueError("pinned Sol extension executor drifted")
        admitted[name] = raw
    module = ModuleType("_desc15_sol_extension_source"); module.__file__ = str(SOURCE / "executor.py")
    sys.modules[module.__name__] = module
    try:
        exec(compile(admitted["executor.py"], str(SOURCE / "executor.py"), "exec"), module.__dict__)  # noqa: S102
    finally:
        sys.modules.pop(module.__name__, None)
    if stable(SOURCE / "executor.py") != admitted["executor.py"]:
        raise ValueError("pinned Sol extension executor changed during load")
    module.validate_package()
    return module


def _prior_metrics(source: ModuleType) -> dict[str, float]:
    source._checkpoint_result()
    prior = strict(stable(source.CWR_SOL_RESULT), "pinned prior Sol result")
    rows = prior.get("metrics")
    if not isinstance(rows, list):
        raise TypeError("prior Sol metrics are absent")
    values = {row.get("candidate_id"): row.get("equal_group_mae") for row in rows if isinstance(row, Mapping)}
    if set(values) < {BASELINE, PARENT} or any(not isinstance(values[key], (int, float)) or values[key] <= 0 for key in (BASELINE, PARENT)):
        raise ValueError("prior Sol comparator metrics drifted")
    return {key: float(values[key]) for key in (BASELINE, PARENT)}


def _metrics(values: dict[str, dict[str, float]], prior: dict[str, float]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if set(values) != set(CHILDREN) or any(len(groups) != 7 for groups in values.values()):
        raise ValueError("incomplete equal-group geometry")
    group_sets = {tuple(sorted(groups)) for groups in values.values()}
    if len(group_sets) != 1:
        raise ValueError("incompatible equal-group geometry")
    rows = [
        {"candidate_id": candidate, "cells": 7, "equal_group_mae": sum(groups.values()) / 7, "group_mae": dict(sorted(groups.items()))}
        for candidate, groups in values.items()
    ]
    rows.sort(key=lambda row: (row["equal_group_mae"], row["candidate_id"]))
    comparisons: dict[str, Any] = {}
    for row in rows:
        value = row["equal_group_mae"]
        comparisons[row["candidate_id"]] = {
            "against_desc13_parent": _compare(PARENT, prior[PARENT], row["candidate_id"], value),
            "against_original_baseline": _compare(BASELINE, prior[BASELINE], row["candidate_id"], value),
        }
    return rows, comparisons


def _compare(left: str, start: float, right: str, end: float) -> dict[str, Any]:
    delta = end - start
    return {
        "from_candidate_id": left,
        "from_equal_group_mae": start,
        "to_candidate_id": right,
        "to_equal_group_mae": end,
        "absolute_delta": delta,
        "relative_reduction": -delta / start,
    }


def replay(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, grok_execution_root: Path, grok_collector_path: Path, grok_result_path: Path) -> dict[str, Any]:
    validate_package()
    source = _source()
    inputs = {
        "candidate_freeze_root": Path(candidate_freeze_root), "development_freeze_root": Path(development_freeze_root),
        "normalized_root": Path(normalized_root), "materialization_root": Path(materialization_root),
        "frozen_successor_path": Path(frozen_successor_path), "hanna_csv_path": Path(hanna_csv_path),
        "grok_execution_root": Path(grok_execution_root), "grok_collector_path": Path(grok_collector_path),
        "grok_result_path": Path(grok_result_path), "output_root": Path(output_root),
    }
    committed = {name: _tree(path) for name, path in sorted(inputs.items())}
    resolution = source._resolve(**{name: inputs[name] for name in inputs if name != "output_root"})
    base = source._configured_base(resolution); rows = {row["cell_id"]: row for row in resolution["rows"]}
    root = _safe(Path(output_root), True)
    if len(rows) != 21 or {path.name for path in root.iterdir()} != set(rows):
        raise ValueError("completed extension root inventory drifted")
    values: dict[str, dict[str, float]] = {candidate: {} for candidate in CHILDREN}
    identities: set[tuple[str, str, str]] = set(); commitments = []; coverage_false = []; route_value = evidence_value = None
    v3 = base._load_v3(); v4 = source.sol_v4()
    for cell_id, row in rows.items():
        cell = root / cell_id; base._inventory(cell, completed=True)
        prepared = strict(stable(cell / "prepared.json"), "prepared"); disclosure = strict(stable(cell / "disclosure.json"), "disclosure")
        acknowledgement = strict(stable(cell / "authorization-acknowledgement.json"), "acknowledgement")
        proof = strict(stable(cell / "zero-charge-route-proof.json"), "route proof"); receipt = strict(stable(cell / "execution-receipt.json"), "receipt")
        intent = strict(stable(cell / "launch-intent.json"), "launch intent"); settings = strict(stable(cell / "effective-settings.json"), "effective settings")
        record = strict(stable(cell / "codex-record.json"), "Codex record"); target_file = strict(stable(cell / "target-vector.json"), "target vector")
        payload, schema = stable(cell / "outbound-payload.json"), stable(cell / "response-schema.json")
        final, events, stderr = stable(cell / "raw-codex-final-response.bin"), stable(cell / "raw-codex-events.bin"), stable(cell / "raw-codex-stderr.bin")
        if final != stable(cell / "responses" / "batch-0001.attempt-0001.message.json") or events != stable(cell / "responses" / "batch-0001.attempt-0001.events.jsonl"):
            raise ValueError("persisted final/message event binding drifted")
        projection = v3._codex_event_projection(events, v3._load_parse_codex_events())
        answer = base._validate_answer(native_json(final, "native final message"))
        route, evidence = v4._frozen_route(proof.get("route"), prepared.get("route_evidence"), v3, require_unexpired=False)
        expected = base._prepared(row, payload, schema, row["target"], route, evidence, ACK)
        expected_settings = {"requested_model":"gpt-5.6-sol","local_effective_model":"gpt-5.6-sol","requested_reasoning_effort":"high","local_effective_reasoning_effort":"high","tools_enabled":False,"web_search_enabled":False,"subagents_enabled":False,"provider_attested":False,"event_projection":projection,"route_name":route["name"],"codex_command_identity":route["codex_command_identity"]}
        identity = {"provider":"openai_codex","route_name":route["name"],"requested_model":"gpt-5.6-sol","requested_reasoning_effort":"high","effective_model":"gpt-5.6-sol","provider_reported_model":None,"reasoning_attested":False,"transport_identity":"codex_chatgpt_subscription_exec_tool_free_v3","native_endpoint_contact_cardinality":"unproven","thread_id":projection.get("thread_id"),"session_id":f"local-codex-thread-session:{projection.get('thread_id')}","contact_id":f"unproven-native-endpoint-contact-for-local-thread:{projection.get('thread_id')}"}
        expected_intent = {"format_version":1,"study_id":SOURCE_ID,"kind":"process_launch_intent_not_native_contact","cell_id":cell_id,"prepared_sha256":sha256(prepared)}
        expected_receipt = {"format_version":1,"study_id":SOURCE_ID,"kind":"local_codex_lifecycle_receipt","cell":dict(row),"process_launches":1,"provider_calls_made":None,"native_endpoint_contact_cardinality":"unproven","internal_retry_cardinality":"unproven","request_sha256":sha256(payload),"response_schema_sha256":sha256(schema),"raw_events_sha256":sha256(events),"raw_stderr_sha256":sha256(stderr),"final_response_sha256":sha256(final),"route_evidence":evidence,"effective_settings_sha256":sha256(settings),"launch_intent_sha256":sha256(stable(cell / "launch-intent.json")),"identity":identity,"human_score_projection":answer}
        expected_record = {"command":v3._expected_codex_command(route["codex_command"][0],cell),"provider_artifacts":{"codex_events":{"path":"responses/batch-0001.attempt-0001.events.jsonl","bytes":len(events),"sha256":sha256(events)},"codex_stderr":{"path":"raw-codex-stderr.bin","bytes":len(stderr),"sha256":sha256(stderr)}},"reported":{"model":None,"provider":None,"reasoning_effort":None,"session_id":None}}
        key = (identity["thread_id"], identity["session_id"], identity["contact_id"])
        if route_value is None:
            route_value, evidence_value = route, evidence
        if (route != route_value or evidence != evidence_value or any(stable(cell / name) != raw for name, raw in expected.items()) or disclosure.get("study_id") != SOURCE_ID or acknowledgement.get("acknowledgement_sha256") != ACK or proof.get("route") != route or proof.get("route_evidence") != evidence or target_file.get("target") != row["target"] or intent != expected_intent or sha256(payload) != row["payload_sha256"] or prepared.get("cell") != row or settings != expected_settings or record != expected_record or receipt != expected_receipt or projection.get("completed_agent_message_text", "").encode() != final or any(not isinstance(item, str) or not item for item in key) or key in identities):
            raise ValueError("lifecycle/native-score/identity binding drifted")
        identities.add(key); commitments.append({"cell_id": cell_id, "prepared_sha256": sha256(prepared), "receipt_sha256": sha256(receipt), "final_response_sha256": sha256(final), "events_sha256": sha256(events)})
        scores = answer.get("scores")
        if not isinstance(scores, Mapping) or set(scores) != set(DIMS):
            raise ValueError("native score dimensions drifted")
        if any(type(scores[dimension]) not in (int, float) or not math.isfinite(float(scores[dimension])) or not 0 <= float(scores[dimension]) <= 5 for dimension in DIMS):
            raise ValueError("native score range drifted")
        evidence = answer.get("evidence")
        if not isinstance(evidence, Mapping) or set(evidence) != set(DIMS) or any(not isinstance(evidence[dimension], str) or not evidence[dimension] for dimension in DIMS):
            raise ValueError("native score evidence drifted")
        coverage = answer.get("coverage")
        if not isinstance(coverage, Mapping) or set(coverage) != set(DIMS) or any(type(coverage[dimension]) is not bool for dimension in DIMS):
            raise ValueError("native score coverage drifted")
        coverage_false.extend({"cell_id": cell_id, "candidate_id": row["candidate_id"], "prompt_group_id": row["prompt_group_id"], "dimension": dimension} for dimension in DIMS if not coverage[dimension])
        values[row["candidate_id"]][row["prompt_group_id"]] = sum(abs(float(scores[dimension]) - float(row["target"][dimension])) for dimension in DIMS) / len(DIMS)
    if {name: _tree(path) for name, path in sorted(inputs.items())} != committed:
        raise ValueError("replay input changed during result reconstruction")
    if len(identities) != 21:
        raise ValueError("duplicate/missing lifecycle identity")
    prior = _prior_metrics(source); metrics, comparison = _metrics(values, prior)
    return {"format_version":1,"study_id":STUDY_ID,"kind":"twenty_one_cell_desc13_lower_step_sol_nonwinner_extension_result","authority":AUTHORITY,"claim":"DESCRIPTIVE_SOL_EXTENSION_ONLY; no pooling, selection, generalization, confirmation, promotion, or runtime claim","evidence_ceiling":CEILING,"coverage":{"complete":not coverage_false,"false_dimensions":sorted(coverage_false, key=lambda item: (item["cell_id"], item["dimension"]))},"metrics":metrics,"comparisons":comparison,"source_execution":{"sol_extension_executor_commit":SOURCE_COMMIT,"sol_extension_executor_sha256":SOURCE_FILES["executor.py"],"grok_result_sha256":resolution["bindings"]["grok_result_sha256"],"grok_result_internal_sha256":resolution["bindings"]["grok_result_internal_sha256"],"grok_collector_sha256":resolution["bindings"]["grok_collector_sha256"],"sol_schedule_sha256":resolution["schedule"]["schedule_sha256"],"prior_sol_result_sha256":source.CWR_SOL_RESULT_SHA256,"receipt_chain_sha256":sha256(sorted(commitments, key=lambda item: item["cell_id"])),"input_commitments":committed}}


def write_result(path: Path, result: dict[str, Any], prohibited_roots: tuple[Path, ...] = ()) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("result path must be fresh")
    _safe(target.parent, True)
    absolute = Path(os.path.abspath(target))
    if any(absolute.is_relative_to(Path(os.path.abspath(root))) for root in (HERE, REPO, *prohibited_roots)):
        raise ValueError("result path must be external and disjoint")
    raw = canonical(result)
    with target.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())
    if stable(target) != raw:
        raise ValueError("result write verification failed")


def validate_package() -> None:
    _plain(HERE, True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != {"README.md", "result.json", "study-contract.json", "verify.py"}:
        raise ValueError("package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    expected = {"format_version":1,"study_id":STUDY_ID,"kind":"provider_free_desc13_lower_step_sol_nonwinner_extension_result_replay","geometry":{"candidates":3,"cells":21,"groups":7},"authority":AUTHORITY,"pins":{"sol_extension_executor_commit":SOURCE_COMMIT,"sol_extension_executor_sha256":SOURCE_FILES["executor.py"],"prior_sol_result_sha256":"da575fc017c461ecfd0756a50265387b8a5b4145cdfaf3b21d32020410371047"},"prohibitions":["no caller aggregate","no imputation","no pooling or promotion claim","no runtime optimizer dependency"]}
    result = strict(stable(HERE / "result.json"), "result")
    if contract != expected or sha256(stable(HERE / "result.json")) != PERSISTED_RESULT_SHA256 or result.get("study_id") != STUDY_ID:
        raise ValueError("package contract/result drifted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provider-free replay of the completed 21-cell Sol nonwinner extension.")
    for name in ("output-root", "candidate-freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor", "hanna-csv", "grok-execution-root", "grok-collector", "grok-result", "result-output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv); result = replay(output_root=args.output_root, candidate_freeze_root=args.candidate_freeze_root, development_freeze_root=args.development_freeze_root, normalized_root=args.normalized_root, materialization_root=args.materialization_root, frozen_successor_path=args.frozen_successor, hanna_csv_path=args.hanna_csv, grok_execution_root=args.grok_execution_root, grok_collector_path=args.grok_collector, grok_result_path=args.grok_result)
    write_result(args.result_output, result, tuple(inputs for inputs in (args.output_root, args.candidate_freeze_root, args.development_freeze_root, args.normalized_root, args.materialization_root, args.frozen_successor, args.hanna_csv, args.grok_execution_root, args.grok_collector, args.grok_result)))
    print(canonical({"cells":21,"provider_calls_made":0,"result_sha256":sha256(result)}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
