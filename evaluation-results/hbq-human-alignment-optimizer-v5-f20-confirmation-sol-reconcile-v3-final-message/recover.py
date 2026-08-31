#!/usr/bin/env python3
"""Provider-free final-message recovery for the single terminal Sol cell."""
from __future__ import annotations

import argparse
import importlib.util
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v3-final-message"
CONTRACT = HERE / "study-contract.json"
V2 = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v2-existing-output" / "verify.py"
V2_SHA256 = "2e1baa6fcee12b9ae6037945841fc860125cb0c9ea3cc2257f6e3fbbf9a125a4"
V2_COMMIT = "b9fa014c06c884c9f27beecf318028bea4aa6192"
V2_FILES = {
    "evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v2-existing-output/verify.py": V2_SHA256,
    "evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v2-existing-output/study-contract.json": "c2a72414c29a8f523127f8f3dcb50e79ffb6c5bf1d052aab563328fc87ec641d",
    "evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v2-existing-output/README.md": "405a4d8f562b51b31853b7b5d64ade98b13483bef8bab23e91b0310593080faa",
    "tests/test_hbq_human_alignment_optimizer_v5_f20_confirmation_sol_reconcile_v2_existing_output.py": "a052287dc2febd186754bc597232685e87d11efd29b5d18b0cac403342a16e8e",
}
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
EXPECTED_GROUP_MAE = {
    "candidate-102cc7f06c9a99a7": {
        "prompt-224828d8a6b2b338": 1.225, "prompt-3286f1e85780066d": 1.1180555555555556,
        "prompt-577e90eb9a834995": 2.0, "prompt-6f4bd6b8f36ecdba": 0.9930555555555556,
        "prompt-7c9df668d681b1fc": 1.4944444444444445, "prompt-8355ff141c67473d": 1.5416666666666667,
        "prompt-9e29d5b528d4bd23": 1.8416666666666668, "prompt-dd2a0062e1557ba7": 1.2,
    },
    "broader-nextwave-13-missing_evidence_not_no": {
        "prompt-224828d8a6b2b338": 1.0277777777777777, "prompt-3286f1e85780066d": 0.9625000000000001,
        "prompt-577e90eb9a834995": 1.6916666666666667, "prompt-6f4bd6b8f36ecdba": 1.011111111111111,
        "prompt-7c9df668d681b1fc": 1.1777777777777778, "prompt-8355ff141c67473d": 1.1972222222222222,
        "prompt-9e29d5b528d4bd23": 1.6666666666666665, "prompt-dd2a0062e1557ba7": 1.2166666666666668,
    },
}
EXPECTED_METRICS = {"candidate-102cc7f06c9a99a7": 1.4267361111111112, "broader-nextwave-13-missing_evidence_not_no": 1.2439236111111112}
EXPECTED_COMPARISON = {"descendant_minus_baseline": -0.18281250000000004, "relative_reduction_percent": 12.813336578242884}
EXPECTED_AUTHORITY = {"selection": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden", "confirmation": "Sol_only"}
PUBLIC_RESULT_SHA256 = "52933a37cd2cff49e8f494e540e485a9d6edbe936e09d7793442792472ffd368"


def _load_v2():
    raw = V2.read_bytes()
    if hashlib.sha256(raw).hexdigest() != V2_SHA256:
        raise ValueError("pinned V2 reconciliation drifted")
    repo = HERE.parents[1]
    for relative, digest in V2_FILES.items():
        local = (repo / relative).read_bytes()
        blob = subprocess.run(["git", "-C", str(repo), "show", f"{V2_COMMIT}:{relative}"], capture_output=True, check=False)
        if hashlib.sha256(local).hexdigest() != digest or blob.returncode or blob.stdout != local:
            raise ValueError("pinned V2 predecessor drifted")
    spec = importlib.util.spec_from_file_location("_confirmation_sol_reconcile_v2", V2)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict:
        raise ValueError(f"invalid {label}")
    return value


def _exact(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return set(actual) == set(expected) and all(_exact(actual[key], expected[key]) for key in expected)
    if type(expected) is list:
        return len(actual) == len(expected) and all(_exact(left, right) for left, right in zip(actual, expected))
    return actual == expected


def _expected_result() -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "full_38_cell_sol_confirmation_group_weighted_mae",
        "source": {"v2_commit": V2_COMMIT, "v2_verify_sha256": V2_SHA256},
        "metrics": EXPECTED_METRICS,
        "group_mae": EXPECTED_GROUP_MAE,
        "comparison": EXPECTED_COMPARISON,
        "native_endpoint_contact_cardinality": "unproven",
        "authority": EXPECTED_AUTHORITY,
        "recovery": {"terminal_cell_count": 1, "accepted_only_after_final_message_sequence_validation": True},
    }


def _answer(raw: bytes, base: Any) -> dict[str, Any]:
    value = base._validate_answer(_json(raw, "agent message"))
    if any(value["coverage"][dimension] is not True for dimension in DIMENSIONS):
        raise ValueError("final agent message is not fully covered")
    if json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8") != raw:
        raise ValueError("final agent message does not exactly equal message.json")
    return value


def _terminal_final(root: Path, base: Any) -> dict[str, Any]:
    events = (root / "responses" / "batch-0001.attempt-0001.events.jsonl").read_bytes().splitlines()
    records = [_json(raw, "event") for raw in events]
    if len(records) < 4 or [records[0].get("type"), records[1].get("type"), records[-1].get("type")] != ["thread.started", "turn.started", "turn.completed"]:
        raise ValueError("terminal turn sequence drifted")
    messages = [record.get("item", {}).get("text") for record in records[2:-1] if record.get("type") == "item.completed" and record.get("item", {}).get("type") == "agent_message"]
    if not messages or any(record.get("type") != "item.completed" for record in records[2:-1]):
        raise ValueError("terminal event sequence drifted")
    final_raw = (root / "responses" / "batch-0001.attempt-0001.message.json").read_bytes()
    final_item = records[-2].get("item", {})
    if final_item.get("type") != "agent_message" or not isinstance(final_item.get("text"), str) or final_item["text"].encode("utf-8") != final_raw:
        raise ValueError("terminal final event/message binding drifted")
    for text in messages[:-1]:
        interim = _json(text.encode("utf-8"), "interim agent message")
        if (set(interim) != {"scores", "evidence", "coverage"} or set(interim["scores"]) != set(DIMENSIONS)
                or set(interim["coverage"]) != set(DIMENSIONS) or any(interim["coverage"][key] is not False for key in DIMENSIONS)
                or any(interim["scores"][key] != 0 for key in DIMENSIONS)):
            raise ValueError("earlier agent message is not a non-authoritative zero-coverage interim")
    return _answer(final_raw, base)


def recover_and_project(*, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    v2 = _load_v2()
    baseline = v2.reconcile_existing_output(output_root=Path(output_root), frozen_root=Path(frozen_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)
    if baseline["completion"] != {"logical_cells": 38, "reconciled_complete_cells": 37, "terminal_unprojectable_cells": 1}:
        raise ValueError("V2 reconciliation baseline drifted")
    source = v2._load_v1(); resolution = source._resolve(frozen_root=Path(frozen_root)); base = source._configured_base(resolution)
    rows = {row["cell_id"]: row for row in resolution["rows"]}
    root = Path(output_root)
    values: dict[str, dict[str, list[float]]] = {}
    terminal = set(item["cell_id"] for item in baseline["terminal_exclusions"])
    for cell_id, row in rows.items():
        cell = root / cell_id
        if cell_id in terminal:
            answer = _terminal_final(cell, base)
        else:
            answer = _json((cell / "execution-receipt.json").read_bytes(), "receipt")["human_score_projection"]
        score = sum(abs(float(answer["scores"][dimension]) - float(row["target"][dimension])) for dimension in DIMENSIONS) / len(DIMENSIONS)
        values.setdefault(row["candidate_id"], {}).setdefault(row["prompt_group_id"], []).append(score)
    group_mae = {candidate: {group: sum(items) / len(items) for group, items in groups.items()} for candidate, groups in values.items()}
    if {candidate: len(groups) for candidate, groups in group_mae.items()} != {"candidate-102cc7f06c9a99a7": 8, "broader-nextwave-13-missing_evidence_not_no": 8}:
        raise ValueError("full confirmation group geometry drifted")
    metrics = {candidate: sum(groups.values()) / len(groups) for candidate, groups in group_mae.items()}
    delta = metrics["broader-nextwave-13-missing_evidence_not_no"] - metrics["candidate-102cc7f06c9a99a7"]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "full_38_cell_sol_confirmation_group_weighted_mae", "source": {"v2_commit": V2_COMMIT, "v2_verify_sha256": V2_SHA256}, "metrics": metrics, "group_mae": group_mae, "comparison": {"descendant_minus_baseline": delta, "relative_reduction_percent": (-delta / metrics["candidate-102cc7f06c9a99a7"]) * 100}, "native_endpoint_contact_cardinality": "unproven", "authority": {"selection": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden", "confirmation": "Sol_only"}, "recovery": {"terminal_cell_count": 1, "accepted_only_after_final_message_sequence_validation": True}}


def validate_public(result_path: Path) -> dict[str, Any]:
    raw = Path(result_path).read_bytes()
    result = _json(raw, "public result")
    if canonical(result) != raw or not _exact(result, _expected_result()):
        raise ValueError("public result binding drifted")
    return result


def validate_study_contract(contract_path: Path = CONTRACT, result_path: Path = HERE / "result.json") -> dict[str, Any]:
    raw = Path(contract_path).read_bytes()
    contract = _json(raw, "study contract")
    expected = {
        "authority": EXPECTED_AUTHORITY,
        "format_version": 1,
        "kind": "provider_free_final_message_recovery_and_sol_confirmation_projection",
        "metrics": {"baseline_mae": 1.4267361111111112, "descendant13_mae": 1.2439236111111112, "descendant_minus_baseline": -0.18281250000000004},
        "pins": {"v2": {"commit": V2_COMMIT, "verify_sha256": V2_SHA256}},
        "prohibitions": ["no provider, launch, retry, queue, or output-root mutation", "no endpoint pooling, promotion, runtime, or generalization claim"],
        "public_result_sha256": PUBLIC_RESULT_SHA256,
        "study_id": STUDY_ID,
    }
    if canonical(contract) != raw or not _exact(contract, expected) or hashlib.sha256(Path(result_path).read_bytes()).hexdigest() != PUBLIC_RESULT_SHA256:
        raise ValueError("study contract binding drifted")
    return contract


def replay_public(*, output_root: Path, frozen_root: Path, authorization_acknowledgement_sha256: str, result_path: Path) -> dict[str, Any]:
    raw = Path(result_path).read_bytes()
    validate_public(result_path)
    validate_study_contract(result_path=Path(result_path))
    actual = recover_and_project(
        output_root=Path(output_root),
        frozen_root=Path(frozen_root),
        authorization_acknowledgement_sha256=authorization_acknowledgement_sha256,
    )
    if canonical(actual) != raw:
        raise ValueError("actual-root replay does not exactly equal public result")
    return actual


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path); parser.add_argument("--frozen-root", type=Path); parser.add_argument("--authorization-acknowledgement-sha256"); parser.add_argument("--result-path", type=Path); parser.add_argument("--validate-public", type=Path)
    args = parser.parse_args(argv)
    if args.validate_public:
        if args.output_root or args.frozen_root or args.authorization_acknowledgement_sha256 or args.result_path: parser.error("public validation accepts only --validate-public")
        result = validate_public(args.validate_public)
        validate_study_contract(result_path=args.validate_public)
    else:
        if not (args.output_root and args.frozen_root and args.authorization_acknowledgement_sha256 and args.result_path): parser.error("replay requires output root, frozen root, acknowledgement, and result path")
        result = replay_public(output_root=args.output_root, frozen_root=args.frozen_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, result_path=args.result_path)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
