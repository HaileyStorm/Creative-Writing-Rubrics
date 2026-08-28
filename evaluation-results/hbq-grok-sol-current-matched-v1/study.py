#!/usr/bin/env python3
"""Freeze public-synthetic `run_judge` inputs for a matched Grok/Sol screen."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs import runner

HERE = Path(__file__).resolve().parent
BOOK = HERE.parents[1]
EXPECTED_CONDITIONS = [
    {
        "condition_id": "sol",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "role": "canonical",
        "canonical": True,
        "screen_only": False,
    },
    {
        "condition_id": "grok",
        "provider": "grok",
        "model": "grok-4.6",
        "reasoning": "high",
        "allow_unattested_reasoning": True,
        "role": "screen_only",
        "canonical": False,
        "screen_only": True,
    },
]
EXPECTED_RUNTIME_FILES = (
    "src/hbqrs/runner.py",
    "src/hbqrs/core.py",
    "src/hbqrs/paths.py",
    "src/hbqrs/weights.py",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "schema/hbq_verdict.schema.json",
    "registry/all_modules.json",
    "bundles/all_bundles.json",
)
GROK_SYSTEM_PROMPT_OVERRIDE = "Act as an isolated structured-output evaluator. Do not use memory, tools, web, plans, or subagents."
EXPECTED_STUDY_ID = "hbq-grok-sol-current-matched-v1"
EXPECTED_CONTRACT_SHA256 = "7e5871ed3fb8551024ddbfd6c9f1370ba831f1642287f2103b7d5c469068f0fc"
EXPECTED_CASE_FILE_SHA256 = "40dc1b2d947ea403aac45d982bd5a6c0c1009ca68b03b670a3a43bdc6178ec80"
EXPECTED_CONTRACT_KEYS = {
    "format_version", "study_id", "status", "frozen_before_execution", "purpose", "privacy", "conditions", "candidate_condition",
    "repetitions", "batch_attempts", "case_file", "same_input_invariant", "runtime_files", "runtime_input_policy", "evidence_policy",
    "required_areas", "design_intent_verdicts", "dispatch_prerequisites", "metrics", "historical_context", "interpretation_limits",
}
EXPECTED_CASE_IDS_AND_INTENTS = (
    ("task-affirmative", "affirmative_check"), ("task-pov-defect", "visible_defect"), ("task-source-absent", "activation_absent"),
    ("form-line-break-positive", "affirmative_check"), ("form-line-break-absent", "visible_defect"), ("form-line-break-unavailable", "evidence_unavailable"),
    ("core-meaning-positive", "affirmative_check"), ("core-referent-ambiguous", "visible_defect"),
    ("craft-dialogue-purpose", "affirmative_check"), ("craft-dialogue-dump", "visible_defect"),
    ("penalty-repetition-absent", "affirmative_check"), ("penalty-purple-clarity", "visible_defect"),
)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict[str, Any]:
    return {"relative_path": path.relative_to(BOOK).as_posix(), "bytes": path.stat().st_size, "sha256": sha(path)}


def external_binding(path: Path) -> dict[str, Any]:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.stat().st_file_attributes
    except (AttributeError, OSError):
        attributes = 0
    return path.is_symlink() or bool(attributes & 0x400)


def guard_external_roots(roots: dict[str, Path], *, require_exists: set[str] = frozenset()) -> dict[str, Path]:
    guarded: dict[str, Path] = {}
    for label, original in roots.items():
        absolute = original.absolute()
        current = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            current /= part
            if current.exists() and _is_reparse_point(current):
                raise ValueError(f"External {label} crosses a reparse point")
        if label in require_exists and not absolute.exists():
            raise ValueError(f"External {label} is missing")
        guarded[label] = absolute.resolve(strict=False)
    labels = list(guarded)
    for index, left_label in enumerate(labels):
        left = guarded[left_label]
        for right_label in labels[index + 1:]:
            right = guarded[right_label]
            if left == right or left.is_relative_to(right) or right.is_relative_to(left):
                raise ValueError(f"External roots overlap: {left_label} and {right_label}")
    return guarded


def text_binding(name: str, text: str) -> dict[str, Any]:
    raw = text.encode("utf-8")
    return {"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def analysis_program_bindings() -> list[dict[str, Any]]:
    return [binding(HERE / name) for name in ("study.py", "analyze_study.py")]


def contract() -> dict[str, Any]:
    value = json.loads((HERE / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Study contract must be an object")
    return value


def cases() -> list[dict[str, Any]]:
    value = json.loads((HERE / "public-synthetic-cases.json").read_text(encoding="utf-8"))
    rows = value.get("cases") if isinstance(value, dict) else None
    if not isinstance(value, dict) or set(value) != {"format_version", "privacy", "cases"} or value.get("format_version") != 2 or value.get("privacy") != "public_synthetic_only" or not isinstance(rows, list) or not all(isinstance(row, dict) and set(row) == {"case_id", "area", "bundle_id", "question_id", "design_intent", "artifact", "context"} for row in rows):
        raise ValueError("Synthetic cases are malformed")
    if tuple((row["case_id"], row["design_intent"]) for row in rows) != EXPECTED_CASE_IDS_AND_INTENTS:
        raise ValueError("Frozen synthetic case identities or design-intent outcomes drifted")
    return rows


@lru_cache(maxsize=None)
def _question_membership(bundle_id: str, question_id: str) -> bool:
    modules = load_modules(registry_path())
    bundle = resolve_bundle(load_bundles(bundles_path()), bundle_id)
    questions = {str(row["question"]["id"]) for row in compiled_questions(compile_bundle(modules, bundle))}
    return question_id in questions


def executable_identity() -> dict[str, Any]:
    executable = Path(sys.executable).resolve()
    return {
        "python": {"name": executable.name, "bytes": executable.stat().st_size, "sha256": sha(executable), "version": sys.version},
        "judge_commands": [
            {"condition_id": "sol", "command": "codex", "version_identity": "trusted_external_launch_receipt_required"},
            {"condition_id": "grok", "command": "grok", "version_identity": "trusted_external_launch_receipt_required"},
        ],
    }


def frozen_protocol(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "conditions": spec["conditions"],
        "repetitions": spec["repetitions"],
        "batch_attempts": spec["batch_attempts"],
        "same_input_invariant": spec["same_input_invariant"],
    }


@lru_cache(maxsize=None)
def _selected_question_by_id(bundle_id: str, question_id: str) -> dict[str, Any]:
    modules = load_modules(registry_path())
    bundle = resolve_bundle(load_bundles(bundles_path()), bundle_id)
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    compiled = compile_bundle(modules, bundle)
    selected = [
        row for row in sorted(compiled_questions(compiled), key=lambda row: roles.get(str(row.get("role")), 99))
        if row["question"]["id"] == question_id
    ]
    if len(selected) != 1:
        raise ValueError("Frozen case does not resolve one compiled question")
    return selected[0]


def _selected_question(case: dict[str, Any]) -> dict[str, Any]:
    return _selected_question_by_id(str(case["bundle_id"]), str(case["question_id"]))


def rendered_prompt(case: dict[str, Any], condition: dict[str, Any]) -> str:
    binary_prompt = (BOOK / "prompts/judge/BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8")
    return runner._render_prompt(
        binary_prompt=binary_prompt,
        artifact={"name": "source.md", "text": case["artifact"]},
        contexts=[{"name": "context.md", "text": case["context"]}],
        bundle_id=str(case["bundle_id"]),
        artifact_id=str(case["case_id"]),
        questions=[_selected_question(case)],
        provider=str(condition["provider"]),
        model=str(condition["model"]),
    )


def rendered_prompt_binding(case: dict[str, Any], condition: dict[str, Any]) -> dict[str, Any]:
    return text_binding("rendered-prompt.txt", rendered_prompt(case, condition))


def reviewable_text(name: str, text: str) -> dict[str, Any]:
    return {**text_binding(name, text), "utf8": text}


def route_response_schema(condition: dict[str, Any]) -> dict[str, Any]:
    if condition["condition_id"] not in {"sol", "grok"}:
        raise ValueError("Condition is absent from the frozen protocol")
    return reviewable_text("response.schema.json", runner._json_bytes(runner._response_schema()).decode("utf-8"))


def dispatch_disclosure(snapshot: dict[str, Any]) -> dict[str, Any]:
    entries = []
    cases_by_id = {row["case_id"]: row for row in cases()}
    for condition in snapshot["protocol"]["conditions"]:
        destination = (
            "Codex CLI -> authenticated OpenAI service"
            if condition["provider"] == "codex"
            else "Grok Build CLI -> authenticated xAI service"
        )
        for case_id, case in cases_by_id.items():
            for repetition in range(1, snapshot["protocol"]["repetitions"] + 1):
                prompt = rendered_prompt(case, condition)
                entries.append({
                    "condition_id": condition["condition_id"],
                    "case_id": case_id,
                    "repetition": repetition,
                    "batch_attempts": snapshot["protocol"]["batch_attempts"],
                    "retry_semantics": "single_attempt_no_validation_feedback",
                    "destination": destination,
                    "artifact": reviewable_text("source.md", case["artifact"]),
                    "context": reviewable_text("context.md", case["context"]),
                    "rendered_prompt": reviewable_text("rendered-prompt.txt", prompt),
                    "response_schema": route_response_schema(condition),
                })
    return {
        "format_version": 1,
        "study_id": snapshot["study_id"],
        "conditions": snapshot["protocol"]["conditions"],
        "same_input_invariant": snapshot["protocol"]["same_input_invariant"],
        "route_response_schemas": {condition["condition_id"]: route_response_schema(condition) for condition in snapshot["protocol"]["conditions"]},
        "grok_system_prompt_override": reviewable_text("grok-system-prompt-override.txt", GROK_SYSTEM_PROMPT_OVERRIDE),
        "entries": entries,
    }


def _non_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() not in {"placeholder", "todo", "tbd", "owner", "unknown"}


def _validate_owner_acknowledgement(value: Any, disclosure: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"format_version", "acknowledged_by", "acknowledgement", "disclosure_sha256", "conditions_sha256"}:
        raise ValueError("Owner acknowledgement has an invalid shape")
    if value.get("format_version") != 1 or not _non_placeholder(value.get("acknowledged_by")) or not _non_placeholder(value.get("acknowledgement")):
        raise ValueError("Owner acknowledgement must be non-placeholder")
    if value.get("disclosure_sha256") != hashlib.sha256(canonical(disclosure)).hexdigest() or value.get("conditions_sha256") != hashlib.sha256(canonical(snapshot["protocol"]["conditions"])).hexdigest():
        raise ValueError("Owner acknowledgement is not bound to this disclosure and conditions")
    return value


def _validate_zero_charge_proofs(value: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"format_version", "proofs"} or value.get("format_version") != 1 or not isinstance(value.get("proofs"), dict):
        raise ValueError("Live zero-charge proof bundle has an invalid shape")
    expected = {row["condition_id"]: row for row in snapshot["protocol"]["conditions"]}
    if set(value["proofs"]) != set(expected):
        raise ValueError("Live zero-charge proofs must cover exactly the frozen conditions")
    keys = {"provider", "model", "checked_at", "proof_kind", "evidence_reference", "paid_api", "no_payment_method", "no_paid_fallback", "no_hold_or_deposit", "no_billable_dispatch"}
    for condition_id, proof in value["proofs"].items():
        condition = expected[condition_id]
        if not isinstance(proof, dict) or set(proof) != keys:
            raise ValueError("Live zero-charge proof has an invalid shape")
        if proof.get("provider") != condition["provider"] or proof.get("model") != condition["model"] or proof.get("proof_kind") != "live_account_zero_charge_inspection":
            raise ValueError("Live zero-charge proof identity drifted")
        if proof.get("paid_api") is not False or not _non_placeholder(proof.get("checked_at")) or not _non_placeholder(proof.get("evidence_reference")) or not all(proof.get(key) is True for key in ("no_payment_method", "no_paid_fallback", "no_hold_or_deposit", "no_billable_dispatch")):
            raise ValueError("Live zero-charge proof is incomplete")
    return value


def validate() -> dict[str, Any]:
    spec, rows = contract(), cases()
    if sha(HERE / "study-contract.json") != EXPECTED_CONTRACT_SHA256 or sha(HERE / "public-synthetic-cases.json") != EXPECTED_CASE_FILE_SHA256:
        raise ValueError("Frozen contract or case-file bytes drifted")
    if set(spec) != EXPECTED_CONTRACT_KEYS or spec.get("format_version") != 2 or spec.get("study_id") != EXPECTED_STUDY_ID:
        raise ValueError("Frozen contract identity or schema drifted")
    if tuple((row.get("case_id"), row.get("design_intent")) for row in rows) != EXPECTED_CASE_IDS_AND_INTENTS or any(set(row) != {"case_id", "area", "bundle_id", "question_id", "design_intent", "artifact", "context"} for row in rows):
        raise ValueError("Frozen synthetic case identities or schema drifted")
    intents = spec["design_intent_verdicts"]
    if spec.get("status") != "provider_free_scaffold" or spec.get("privacy") != "public_synthetic_only":
        raise ValueError("The calibration screen must remain a public-synthetic provider-free scaffold")
    if len(rows) != 12 or len({row.get("case_id") for row in rows}) != 12:
        raise ValueError("The calibration screen requires exactly twelve uniquely named cases")
    if {row.get("area") for row in rows} != set(spec["required_areas"]) or set(intents) - {row.get("design_intent") for row in rows}:
        raise ValueError("Synthetic cases do not cover every required area and design intent")
    for row in rows:
        if not all(isinstance(row.get(key), str) and row[key] for key in ("case_id", "bundle_id", "question_id", "design_intent", "artifact", "context")):
            raise ValueError("Synthetic case lacks a required bound input")
        if row["design_intent"] not in intents or not _question_membership(row["bundle_id"], row["question_id"]):
            raise ValueError("Synthetic case label or bundle/leaf membership drifted")
    if spec.get("conditions") != EXPECTED_CONDITIONS:
        raise ValueError("The exact Sol/Grok condition identities, roles, or screen/canonical flags drifted")
    if spec.get("runtime_files") != list(EXPECTED_RUNTIME_FILES):
        raise ValueError("The exact ordered runtime-file set drifted")
    if spec.get("runtime_input_policy") != "exact_content_hashes_independent_of_porcelain":
        raise ValueError("Runtime inputs must use exact content hashes independent of worktree shape")
    if spec.get("evidence_policy") != {
        "local_fixture_class": "DEVELOPMENT_SCREENING_FIXTURE",
        "promotion_class": "NON_PROMOTABLE",
        "trusted_external_launch_receipt_required": True,
    }:
        raise ValueError("Calibration evidence-class policy drifted")
    candidate = spec.get("candidate_condition")
    if candidate != {"enabled_by_default": False, "rule": "Any added judge condition is reported separately and does not alter the Sol-versus-Grok screen."}:
        raise ValueError("Candidate-condition isolation drifted")
    dispatch = spec.get("dispatch_prerequisites")
    if not isinstance(dispatch, dict) or dispatch.get("execution_enabled") is not False:
        raise ValueError("This provider-free scaffold must keep execution disabled")
    disclosure, zero_charge = dispatch.get("remote_disclosure"), dispatch.get("zero_charge")
    if not isinstance(disclosure, dict) or disclosure != {
        "required": True,
        "provider_neutral": True,
        "must_name_destination_and_transmitted_artifacts": True,
    }:
        raise ValueError("Provider-neutral remote disclosure prerequisite drifted")
    if not isinstance(zero_charge, dict) or zero_charge != {
        "required": True,
        "must_prove_no_payment_method_paid_fallback_hold_or_billable_dispatch": True,
    }:
        raise ValueError("Zero-charge dispatch prerequisite drifted")
    if spec.get("design_intent_verdicts") != {"affirmative_check": "YES", "visible_defect": "NO", "activation_absent": "NOT_APPLICABLE", "evidence_unavailable": "CANNOT_ASSESS"}:
        raise ValueError("Frozen design-intent verdict semantics drifted")
    if spec.get("repetitions") != 3 or spec.get("batch_attempts") != 1 or not isinstance(spec.get("same_input_invariant"), str) or not spec["same_input_invariant"].strip():
        raise ValueError("Frozen repetitions, single-attempt policy, or same-input invariant drifted")
    return {"study_id": spec["study_id"], "cases": len(rows), "conditions": len(EXPECTED_CONDITIONS), "provider_calls": 0}


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    validate()
    spec = contract()
    if snapshot.get("format_version") != 4 or snapshot.get("study_id") != spec["study_id"]:
        raise ValueError("Frozen snapshot identity drifted")
    if snapshot.get("contract") != binding(HERE / "study-contract.json") or snapshot.get("case_file") != binding(HERE / "public-synthetic-cases.json"):
        raise ValueError("Frozen contract or case binding drifted")
    if snapshot.get("runtime") != [binding(BOOK / path) for path in EXPECTED_RUNTIME_FILES]:
        raise ValueError("Frozen current runtime binding drifted")
    if snapshot.get("analysis_program") != analysis_program_bindings() or snapshot.get("protocol") != frozen_protocol(spec):
        raise ValueError("Frozen program or protocol binding drifted")
    if snapshot.get("executable_identity") != executable_identity():
        raise ValueError("Frozen executable/version identity drifted")
    expected_cases = {row["case_id"]: row for row in cases()}
    commitments = snapshot.get("case_commitments")
    if not isinstance(commitments, dict) or set(commitments) != set(expected_cases):
        raise ValueError("Frozen case commitments drifted")
    for case_id, case in expected_cases.items():
        expected = {
            "case_sha256": hashlib.sha256(canonical(case)).hexdigest(),
            "artifact": text_binding("source.md", case["artifact"]),
            "context": text_binding("context.md", case["context"]),
            "bundle_id": case["bundle_id"],
            "question_id": case["question_id"],
        }
        if commitments.get(case_id) != expected:
            raise ValueError("Frozen synthetic case content drifted")


def freeze(output: Path) -> dict[str, Any]:
    output = guard_external_roots({"output": output})["output"]
    validate()
    if output.exists():
        raise ValueError("Refusing to overwrite a frozen calibration snapshot")
    spec = contract()
    runtime = [BOOK / relative for relative in spec["runtime_files"]]
    if not all(path.is_file() for path in runtime):
        raise ValueError("A declared calibration runtime file is missing")
    commitments = {}
    for row in cases():
        artifact, context = text_binding("source.md", row["artifact"]), text_binding("context.md", row["context"])
        commitments[row["case_id"]] = {
            "case_sha256": hashlib.sha256(canonical(row)).hexdigest(),
            "artifact": artifact,
            "context": context,
            "bundle_id": row["bundle_id"],
            "question_id": row["question_id"],
        }
    snapshot = {
        "format_version": 4,
        "study_id": spec["study_id"],
        "contract": binding(HERE / "study-contract.json"),
        "case_file": binding(HERE / "public-synthetic-cases.json"),
        "runtime": [binding(path) for path in runtime],
        "executable_identity": executable_identity(),
        "analysis_program": analysis_program_bindings(),
        "protocol": frozen_protocol(spec),
        "case_commitments": commitments,
    }
    output.mkdir(parents=True)
    (output / "frozen-inputs.json").write_bytes(canonical(snapshot))
    return snapshot


def prepare(frozen_path: Path, owner_ack_path: Path, zero_charge_proof_path: Path, output: Path) -> dict[str, Any]:
    guarded = guard_external_roots(
        {"frozen": frozen_path, "owner_acknowledgement": owner_ack_path, "zero_charge_proof": zero_charge_proof_path, "output": output},
        require_exists={"frozen", "owner_acknowledgement", "zero_charge_proof"},
    )
    frozen_path, owner_ack_path, zero_charge_proof_path, output = (guarded["frozen"], guarded["owner_acknowledgement"], guarded["zero_charge_proof"], guarded["output"])
    if output.exists():
        raise ValueError("Refusing to overwrite a prepared dispatch binding")
    snapshot = json.loads(frozen_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError("Frozen snapshot must be an object")
    validate_snapshot(snapshot)
    disclosure = dispatch_disclosure(snapshot)
    owner_ack = json.loads(owner_ack_path.read_text(encoding="utf-8"))
    zero_charge_proofs = json.loads(zero_charge_proof_path.read_text(encoding="utf-8"))
    _validate_owner_acknowledgement(owner_ack, disclosure, snapshot)
    _validate_zero_charge_proofs(zero_charge_proofs, snapshot)
    output.mkdir(parents=True)
    disclosure_path = output / "dispatch-disclosure.json"
    disclosure_path.write_bytes(canonical(disclosure))
    acknowledgement_path = output / "owner-acknowledgement.json"
    acknowledgement_path.write_bytes(canonical(owner_ack))
    zero_charge_path = output / "zero-charge-proofs.json"
    zero_charge_path.write_bytes(canonical(zero_charge_proofs))
    dispatch_binding = {
        "format_version": 1,
        "study_id": snapshot["study_id"],
        "status": "prepared_provisional_dispatch_disabled",
        "provider_calls": 0,
        "frozen_inputs": {"bytes": frozen_path.stat().st_size, "sha256": sha(frozen_path)},
        "disclosure": {"relative_path": disclosure_path.name, "bytes": disclosure_path.stat().st_size, "sha256": sha(disclosure_path)},
        "owner_acknowledgement": {"relative_path": acknowledgement_path.name, "bytes": acknowledgement_path.stat().st_size, "sha256": sha(acknowledgement_path)},
        "zero_charge_proofs": {"relative_path": zero_charge_path.name, "bytes": zero_charge_path.stat().st_size, "sha256": sha(zero_charge_path)},
        "conditions_sha256": hashlib.sha256(canonical(snapshot["protocol"]["conditions"])).hexdigest(),
        "evidence_class": "DEVELOPMENT_SCREENING_FIXTURE",
        "promotion": {"eligible": False, "evidence_class": "NON_PROMOTABLE", "reason": "trusted_external_runner_launch_receipt_required"},
        "trusted_launch_receipt": {"status": "absent_nonpromotable", "receipt": None},
    }
    (output / "dispatch-binding.json").write_bytes(canonical(dispatch_binding))
    return dispatch_binding


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "freeze", "prepare"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--owner-ack", type=Path)
    parser.add_argument("--zero-charge-proof", type=Path)
    args = parser.parse_args()
    if args.command == "validate":
        print(json.dumps(validate(), sort_keys=True))
        return 0
    if args.output is None:
        parser.error("freeze requires --output")
    if args.command == "prepare":
        if args.frozen is None or args.owner_ack is None or args.zero_charge_proof is None:
            parser.error("prepare requires --frozen, --owner-ack, and --zero-charge-proof")
        prepared = prepare(args.frozen.resolve(), args.owner_ack.resolve(), args.zero_charge_proof.resolve(), args.output.resolve())
        print(json.dumps({"study_id": prepared["study_id"], "output": str(args.output), "provider_calls": 0}, sort_keys=True))
        return 0
    snapshot = freeze(args.output.resolve())
    print(json.dumps({"study_id": snapshot["study_id"], "output": str(args.output), "provider_calls": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
