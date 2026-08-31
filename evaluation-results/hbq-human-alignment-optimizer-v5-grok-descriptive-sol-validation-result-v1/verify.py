#!/usr/bin/env python3
"""Recompute the public descriptive Sol readout from a completed local root."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


HERE = Path(__file__).resolve().parent
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")
CELLS = (
    "sol-v5-descriptive-baseline-g1",
    "sol-v5-descriptive-baseline-g2",
    "sol-v5-descriptive-low-g1",
    "sol-v5-descriptive-low-g2",
)
SOURCE_EXECUTION = {
    "executor_commit": "b3b2f4495bc187b5a5cdca41edc075b4f0f74cc4",
    "executor_sha256": "7f8a9934bb8fea18ab4cba315f97ebe46e3b6e1bc04a1f4bfb6f2816f76daebd",
    "executor_study_contract_sha256": "90e44ff10d345c3cd8d5172cb981219a06a8c26a7d4d7c2c18a36f16d6160835",
    "test_sha256": "aaf9686454fd2fa3f4f61d1b40e7c2aa0758319111a9e74321b1e706e6afdff7",
}
SOURCE_EXECUTION_KEYS = frozenset((*SOURCE_EXECUTION, "live_root_tree_sha256"))
METRIC_KEYS = frozenset({"candidate_id", "equal_group_mae", "group_mae"})
GROUP_IDS = frozenset({"prompt-7c393c4bcb3a7484", "prompt-8997770ce6efe4d5"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _raw(path: Path) -> bytes:
    return path.read_bytes()


def _json(path: Path) -> dict[str, Any]:
    raw = _raw(path)
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical object: {path.name}")
    return value


def _tree(root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        raise ValueError("live root is absent")
    tree: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_dir():
            if path.is_symlink():
                raise ValueError("live root contains a symlink")
            continue
        relative = path.relative_to(root).as_posix()
        raw = _raw(path)
        tree[relative] = {"bytes": len(raw), "sha256": sha(raw)}
    return tree


def _message_from_events(raw: bytes) -> tuple[str, str]:
    answer: str | None = None
    thread_id: str | None = None
    for line in raw.decode("utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        item = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item, dict) and item.get("type") == "agent_message":
            answer = item.get("text")
    if not isinstance(answer, str) or not isinstance(thread_id, str) or not thread_id:
        raise ValueError("raw lifecycle projection is incomplete")
    return answer, thread_id


def _answer(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or set(value) != {"scores", "evidence", "coverage"}:
        raise ValueError("final message schema drifted")
    scores, evidence, coverage = value["scores"], value["evidence"], value["coverage"]
    if not all(isinstance(part, dict) and set(part) == set(DIMENSIONS) for part in (scores, evidence, coverage)):
        raise ValueError("final message dimensions drifted")
    for dimension in DIMENSIONS:
        score = scores[dimension]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 5:
            raise ValueError("final score drifted")
        if not isinstance(evidence[dimension], str) or not evidence[dimension] or not isinstance(coverage[dimension], bool):
            raise ValueError("final evidence drifted")
    return value


def _publication() -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    result_raw, contract_raw = _raw(HERE / "result.json"), _raw(HERE / "study-contract.json")
    result, contract = json.loads(result_raw.decode("utf-8")), json.loads(contract_raw.decode("utf-8"))
    if not isinstance(result, dict) or not isinstance(contract, dict):
        raise ValueError("publication files must be objects")
    return result, contract, result_raw, contract_raw


def _reject_sensitive(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("public object key is not a string")
            _reject_sensitive(child)
        return
    if isinstance(value, list):
        for child in value:
            _reject_sensitive(child)
        return
    if not isinstance(value, str):
        return
    if ("PRIVATE_STORY_SENTINEL" in value or re.search(r"[A-Za-z]:[\\/]", value)
            or re.search(r"(?:^|[=\"'\s(,:;])\\\\[^\\/\s]+\\[^\\/\s]+", value)
            or re.search(r"(?:^|[\"'\s])/(?:Users|home|tmp|var|private|mnt|etc)(?:/|$)", value)
            or re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", value, flags=re.IGNORECASE)):
        raise ValueError("public artifact contains sensitive material or a local path")


def verify(live_root: Path) -> dict[str, Any]:
    result, contract, result_raw, _contract_raw = _publication()
    _reject_sensitive(result); _reject_sensitive(contract); _reject_sensitive((HERE / "README.md").read_text(encoding="utf-8"))
    if set(result) != {"authority", "cell_commitments", "claim", "comparison", "evidence_ceiling", "format_version", "kind", "metrics", "publication_geometry", "result_internal_sha256", "source_execution", "study_id"}:
        raise ValueError("public result field surface drifted")
    internal = dict(result); recorded = internal.pop("result_internal_sha256")
    if not isinstance(recorded, str) or recorded != sha(internal):
        raise ValueError("public result commitment drifted")
    source_execution = result["source_execution"]
    if (not isinstance(source_execution, dict) or set(source_execution) != SOURCE_EXECUTION_KEYS
            or contract.get("result_file_sha256") != sha(result_raw) or contract.get("result_internal_sha256") != recorded or contract.get("study_id") != result["study_id"]
            or contract.get("source_execution") != source_execution or {key: source_execution.get(key) for key in SOURCE_EXECUTION} != SOURCE_EXECUTION
            or not isinstance(source_execution.get("live_root_tree_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", source_execution["live_root_tree_sha256"])):
        raise ValueError("contract/result commitment drifted")
    if (set(contract) != {"authority", "comparison", "evidence_ceiling", "format_version", "kind", "result_file_sha256", "result_internal_sha256", "source_execution", "study_id"}
            or contract.get("format_version") != 1 or contract.get("kind") != "immutable_descriptive_sol_public_result_publication"
            or contract.get("authority") != result["authority"] or contract.get("evidence_ceiling") != result["evidence_ceiling"]):
        raise ValueError("contract field surface drifted")
    if result["authority"] != {"selection": "none", "confirmation": "unopened", "general_hanna": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}:
        raise ValueError("authority drifted")
    if result["evidence_ceiling"] != "local Codex lifecycle only; native endpoint contact cardinality is unproven":
        raise ValueError("evidence ceiling drifted")
    if result["publication_geometry"] != {"cells": 4, "prompt_groups": 2, "candidate_observations": 2, "dimensions": 6}:
        raise ValueError("publication geometry drifted")
    expected_tree = source_execution["live_root_tree_sha256"]
    if not isinstance(expected_tree, str) or sha(_tree(Path(live_root))) != expected_tree:
        raise ValueError("live root tree commitment drifted")
    rows = result["cell_commitments"]
    if not isinstance(rows, list) or [row.get("cell_id") for row in rows] != list(CELLS):
        raise ValueError("cell geometry drifted")
    observed: dict[str, dict[str, float]] = {}
    identities: set[str] = set()
    for row in rows:
        if set(row) != {"candidate_id", "cell_id", "final_response_sha256", "lifecycle_identity_sha256", "payload_sha256", "prompt_group_id", "raw_events_sha256", "receipt_sha256", "target_vector_sha256", "tree_sha256"}:
            raise ValueError("public cell field surface drifted")
        root = Path(live_root) / row["cell_id"]
        tree = _tree(root)
        if row["tree_sha256"] != sha(tree):
            raise ValueError("cell tree commitment drifted")
        receipt = _json(root / "execution-receipt.json")
        final, events, payload, target = (_raw(root / "raw-codex-final-response.bin"), _raw(root / "raw-codex-events.bin"), _raw(root / "outbound-payload.json"), _json(root / "target-vector.json"))
        if (row["receipt_sha256"] != sha(_raw(root / "execution-receipt.json")) or row["final_response_sha256"] != sha(final) or row["raw_events_sha256"] != sha(events)
                or row["payload_sha256"] != sha(payload) or row["target_vector_sha256"] != sha(target)):
            raise ValueError("cell artifact commitment drifted")
        projected, thread_id = _message_from_events(events)
        if projected.encode("utf-8") != final or _raw(root / "responses" / "batch-0001.attempt-0001.message.json") != final or _raw(root / "responses" / "batch-0001.attempt-0001.events.jsonl") != events:
            raise ValueError("raw final-message lifecycle binding drifted")
        answer = _answer(final)
        identity = receipt.get("identity")
        if (not isinstance(identity, dict) or row["lifecycle_identity_sha256"] != sha(identity) or row["lifecycle_identity_sha256"] in identities
                or identity.get("thread_id") != thread_id or identity.get("session_id") != f"local-codex-thread-session:{thread_id}"
                or identity.get("contact_id") != f"unproven-native-endpoint-contact-for-local-thread:{thread_id}"
                or receipt.get("native_endpoint_contact_cardinality") != "unproven" or receipt.get("provider_calls_made") is not None
                or receipt.get("process_launches") != 1 or receipt.get("human_score_projection") != answer):
            raise ValueError("receipt lifecycle identity/binding drifted")
        identities.add(row["lifecycle_identity_sha256"])
        target_scores = target.get("target")
        if not isinstance(target_scores, dict) or set(target_scores) != set(DIMENSIONS):
            raise ValueError("target geometry drifted")
        mae = sum(abs(answer["scores"][dimension] - target_scores[dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS)
        observed.setdefault(row["candidate_id"], {})[row["prompt_group_id"]] = mae
    if len(identities) != 4 or any(len(groups) != 2 for groups in observed.values()) or set(observed) != {"candidate-102cc7f06c9a99a7", "candidate-69720ac6257db007"}:
        raise ValueError("unique two-group observation geometry drifted")
    metrics = result["metrics"]
    if not isinstance(metrics, list) or len(metrics) != 2:
        raise ValueError("metrics geometry drifted")
    published = {row.get("candidate_id"): row for row in metrics}
    for candidate_id, groups in observed.items():
        item = published.get(candidate_id)
        if (not isinstance(item, dict) or set(item) != METRIC_KEYS or item.get("group_mae") != groups or item.get("equal_group_mae") != sum(groups.values()) / 2
                or not isinstance(item["group_mae"], dict) or set(item["group_mae"]) != GROUP_IDS
                or any(isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) for score in item["group_mae"].values())):
            raise ValueError("independent equal-group MAE projection drifted")
    baseline, candidate = published["candidate-102cc7f06c9a99a7"]["equal_group_mae"], published["candidate-69720ac6257db007"]["equal_group_mae"]
    expected_comparison = {"baseline_candidate_id": "candidate-102cc7f06c9a99a7", "candidate_id": "candidate-69720ac6257db007", "absolute_delta": candidate - baseline, "relative_reduction": (baseline - candidate) / baseline}
    if result["comparison"] != expected_comparison or contract.get("comparison") != expected_comparison:
        raise ValueError("published comparison drifted")
    return {"baseline_mae": baseline, "candidate_mae": candidate, "absolute_delta": candidate - baseline, "relative_reduction": (baseline - candidate) / baseline, "cells": 4, "native_endpoint_contact_cardinality": "unproven"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--live-root", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().live_root), sort_keys=True))
