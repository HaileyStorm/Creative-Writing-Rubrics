#!/usr/bin/env python3
"""Verify the public, provider-free QPC24 two-pass confirmation contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
if str(REPOSITORY / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY / "src"))

from hbqrs.core import compile_bundle, compiled_questions, load_data, resolve_bundle  # noqa: E402


STUDY_ID = "hbq-qpc24-two-pass-product-confirmation-v1"
HEAD = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
CONTRACT_PATH = HERE / "study-contract.json"
ROLE_ORDER = ("author_original", "gpt_5_6_pro_rewrite", "public_control_story")
RUNTIME_BINDINGS = {
    "registry/all_modules.json": "12149c9ee556113b1c2865fa8a09a9cb6d60b554a8685219300e48dc1bf52de6",
    "bundles/all_bundles.json": "ca20defa2e3350f949dc9da5e69bb9061d5a0c2d6ddcd71bb9399262dad10f86",
    "bundles/prose.novel.yaml": "96e2b27d4324a368eb3c6cc76bf51ec1b82f02c3a92e8dd6a6e68efad00b9f38",
    "registry/question_index.jsonl": "683f32cffbe4d5f57de288a7c6fab8b79ffa02a6b99635349d2945ed0af1fde0",
    "registry/criterion_ownership.json": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
    "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
}
QUESTION_SEQUENCE_SHA256 = "22c7c011189072b746eef4cd6aaf0b4da8cb21fd4786e9920593a4e9828602ce"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_contract() -> dict[str, Any]:
    try:
        value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid public QPC24 contract") from error
    if not isinstance(value, dict):
        raise ValueError("Public QPC24 contract must be an object")
    return value


def contract() -> dict[str, Any]:
    value = read_contract()
    if value.get("format_version") != 1 or value.get("study_id") != STUDY_ID or value.get("source_head") != HEAD:
        raise ValueError("QPC24 two-pass public identity drift")
    execution = value.get("execution")
    if not isinstance(execution, dict) or execution != {
        "provider_free_now": True,
        "remote_provider_call_count_now": 0,
        "dispatch_surface": "absent",
        "future_provider": "codex",
        "future_model": "gpt-5.6-sol",
        "future_reasoning": "high",
        "zero_paid_route": "owner_acknowledged_zero_incremental_charge_only",
        "paid_fallback": "forbidden",
        "api_fallback": "forbidden",
        "retry": "forbidden_per_slot",
        "resume": "never_claimed_slots_only",
        "future_execution": "requires_independent_review",
    }:
        raise ValueError("QPC24 two-pass provider boundary drift")
    geometry = value.get("geometry")
    if not isinstance(geometry, dict) or {key: geometry.get(key) for key in (
        "artifact_roles", "complete_eligible_question_count", "questions_per_provider_call", "full_batches_per_pass",
        "final_remainder_questions", "calls_per_pass", "target_voting_calls", "target_voting_positions",
        "maximum_unique_contacts",
    )} != {
        "artifact_roles": list(ROLE_ORDER), "complete_eligible_question_count": 221, "questions_per_provider_call": 24,
        "full_batches_per_pass": 9, "final_remainder_questions": 5, "calls_per_pass": 10,
        "target_voting_calls": 60, "target_voting_positions": 1326, "maximum_unique_contacts": 90,
    }:
        raise ValueError("QPC24 two-pass geometry drift")
    if value.get("reserve_policy") != {
        "unit": "whole_pass_only", "activation": "local_transport_ambiguity_only",
        "forbidden_activation": ["substantive_miss", "unfavorable_result", "schema_or_model_failure", "additional_sampling"],
        "maximum_replacements_per_role": 1,
    }:
        raise ValueError("QPC24 two-pass reserve policy drift")
    if value.get("runtime_bindings") != RUNTIME_BINDINGS:
        raise ValueError("QPC24 two-pass runtime bindings drift")
    if value.get("eligible_question_set") != {"bundle_id": "prose.novel", "question_sequence_sha256": QUESTION_SEQUENCE_SHA256}:
        raise ValueError("QPC24 two-pass question sequence binding drift")
    if value.get("fidelity") != {
        "per_selected_pass": "full_prose.novel_221_leaves_in_9x24_plus_5",
        "two_pass_effect": "reduces_repeatability_evidence_only",
        "runtime_or_default_change": "none",
        "historical_five_repeat_plan": "retained_as_extended_validation_path_not_replaced",
    } or value.get("non_claims") != {
        "runtime_default": "none", "new_evaluation_mode": "none", "replacement_of_five_repeat_validation": "none",
    }:
        raise ValueError("QPC24 two-pass fidelity boundary drift")
    private_only = value.get("disjointness", {}).get("private_only")
    if private_only != ["source_paths", "repetition_selection", "reserve_selection", "contact_ledger", "rendered_prompt_hashes"]:
        raise ValueError("QPC24 two-pass privacy boundary drift")
    return value


def verify_exact_head_and_bindings() -> dict[str, str]:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode or result.stdout.strip() != HEAD:
        raise ValueError("QPC24 two-pass freeze requires exact source HEAD 4ce1204")
    observed: dict[str, str] = {}
    for relative, digest in RUNTIME_BINDINGS.items():
        actual = sha256_bytes((REPOSITORY / relative).read_bytes())
        if actual != digest:
            raise ValueError(f"QPC24 two-pass runtime binding drift: {relative}")
        observed[relative] = actual
    return observed


def verify_question_geometry() -> int:
    modules = load_data(REPOSITORY / "registry" / "all_modules.json")
    bundles = load_data(REPOSITORY / "bundles" / "all_bundles.json")
    rows = compiled_questions(compile_bundle(modules, resolve_bundle(bundles, "prose.novel")))
    count = len(rows)
    if count != 221 or sha256_bytes(canonical([str(row["question"]["id"]) for row in rows])) != QUESTION_SEQUENCE_SHA256:
        raise ValueError("QPC24 two-pass eligible-question geometry drift")
    return count


def validate() -> dict[str, Any]:
    contract()
    bindings = verify_exact_head_and_bindings()
    question_count = verify_question_geometry()
    return {
        "study_id": STUDY_ID,
        "source_head": HEAD,
        "provider_calls": 0,
        "logical_work_evaluations": 6,
        "planned_voting_calls": 60,
        "maximum_unique_contacts": 90,
        "verdict_positions": question_count * 6,
        "status": "FROZEN_PROVIDER_FREE_PREEXECUTION",
        "runtime_bindings": bindings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("verify",))
    args = parser.parse_args(argv)
    print(json.dumps(validate(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
