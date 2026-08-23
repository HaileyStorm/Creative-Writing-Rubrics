"""Provider-free verifier and slot planner for the premise-scale ownership screen."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from hbqrs import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs import runner as production_runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-premise-scale-ownership-v1"
LEAVES = (
    "artifact.support.premise_story_seed.extensibility",
    "op.ideation.premise_stress_test.scale",
)
VERDICTS = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})
SCORING = {
    "applicable_and_control_cells": "must_be_3_of_3_expected_with_grounded_typed_evidence",
    "not_applicable": "completed_unscored",
    "cannot_assess": "coverage_uncertainty",
    "missing_or_ambiguous_slot": "INCOMPLETE",
}
CLARIFICATION_SUCCESSOR = {
    "maximum_exact": 1,
    "requires_all_72_slots_settled": True,
    "requires_independent_pair_types_minimum": 2,
    "requires_same_scope_or_control_error_repeats_minimum": 2,
    "requires_independent_sol_attribution": "one_missing_rendering_rule",
    "forbidden_if": "same_verdict_and_same_premise_evidence_indicates_rubric_or_route_duplication",
}
HOLDOUT_CONTRACT_BINDING = {
    "file": "external-real-text-holdout-commitment.json",
    "file_sha256": "43a6523013758cf0f8753b583370a588743e7e0db203d8783707fa5e52d3a5d2",
    "package_id": "cwr-premise-scale-real-holdout-20260823",
    "status": "sealed_from_evaluation",
    "payload_canonical_sha256": "c3e4ca0ed76bfd872304656bea57861c7e4b72c0c7056213935b7b652c1e1665",
    "payload_file_sha256": "d58ac420d51e2e4ddf092fa8641cf1189ce9129c12e02480d30cd653fdb62bfd",
    "freeze_manifest_sha256": "c9b6c249ebbe39ce02fd075d1c7e4b4504efc40b969ab066bbb41fe553c1fe56",
    "current_wording_diagnostic_access": "forbidden",
    "role": "external_positive_realism_control_not_sole_discriminating_holdout",
    "later_execution_gate": "no_treatment_optimizer_or_confirmation_before_separately_frozen_execution_successor_and_explicit_holdout_opening_gate",
}
HOLDOUT_PUBLIC = {
    "format_version": 1,
    "package_id": "cwr-premise-scale-real-holdout-20260823",
    "status": "sealed_from_evaluation",
    "artifact_count": 2,
    "selection": "license_and_form_before_evaluation",
    "expected_verdicts_present": False,
    "sources": [
        {"title": "Tears of Steel", "source_url": "https://mango.blender.org/about/", "license_url": "https://creativecommons.org/licenses/by/3.0/", "attribution": "Tears of Steel — writer/director Ian Hubert; Blender Foundation"},
        {"title": "Spring", "source_url": "https://studio.blender.org/projects/spring/pages/about/", "license_url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "Spring — written/directed by Andy Goralczyk; Blender Foundation"},
    ],
    "payload_canonical_sha256": "c3e4ca0ed76bfd872304656bea57861c7e4b72c0c7056213935b7b652c1e1665",
    "payload_file_sha256": "d58ac420d51e2e4ddf092fa8641cf1189ce9129c12e02480d30cd653fdb62bfd",
    "freeze_manifest_sha256": "c9b6c249ebbe39ce02fd075d1c7e4b4504efc40b969ab066bbb41fe553c1fe56",
    "role": "external_positive_realism_control_not_sole_discriminating_holdout",
    "current_wording_diagnostic_access": "forbidden",
    "later_execution_gate": "no_treatment_optimizer_or_confirmation_before_separately_frozen_execution_successor_and_explicit_holdout_opening_gate",
}
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "registry/modules/artifact.support.premise_story_seed.yaml",
    "registry/modules/op.ideation.premise_stress_test.yaml",
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "registry/all_modules.json",
    "bundles/all_bundles.json",
    "src/hbqrs/runner.py",
)
CANONICAL_LEAVES = {
    "artifact.support.premise_story_seed.extensibility": {
        "module_id": "artifact.support.premise_story_seed",
        "text": "Can it sustain the intended length and medium?",
        "pass_answer": "YES",
        "weight": 1.5,
        "question_type": "scored",
        "severity": "material",
    },
    "op.ideation.premise_stress_test.scale": {
        "module_id": "op.ideation.premise_stress_test",
        "text": "Can the premise sustain the intended length and form without padding or premature exhaustion?",
        "pass_answer": "YES",
        "weight": 2.0,
        "question_type": "scored",
        "severity": "material",
    },
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def source_leaf_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry/question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in LEAVES:
            records[row["id"]] = {
                key: row[key]
                for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity")
            }
    if set(records) != set(LEAVES):
        raise ValueError("Canonical source leaves are unavailable")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in source_leaf_records().items()}


def artifact_sha256(artifact: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(artifact)).hexdigest()


def verify_scope_activation_targets(artifact: Mapping[str, Any]) -> None:
    artifact_leaf, operation_leaf = LEAVES
    artifact_verdict = artifact["expected_verdicts"][artifact_leaf]
    operation_verdict = artifact["expected_verdicts"][operation_leaf]
    scope = artifact["declared_scope"]
    artifact_target = artifact["artifact_target"]
    operation_target = artifact["operation_target"]
    active = artifact["operation_active"]
    if scope not in {"artifact_only", "operation_only", "artifact_and_operation"}:
        raise ValueError("Declared scope is malformed")
    if scope == "artifact_only":
        if active or operation_target is not None or operation_verdict != "NOT_APPLICABLE" or artifact_target is None:
            raise ValueError("Artifact-only control is inconsistent")
    elif scope == "operation_only":
        if not active or artifact["artifact_type"] != "reference_artifact" or artifact_target is not None or artifact_verdict != "NOT_APPLICABLE" or operation_target is None:
            raise ValueError("Operation-only reference control is inconsistent")
    else:
        if not active:
            raise ValueError("Joint scope must activate the operation")
        if artifact_verdict == "CANNOT_ASSESS" or operation_verdict == "CANNOT_ASSESS":
            if artifact_target is not None or operation_target is not None or artifact_verdict != operation_verdict:
                raise ValueError("Coverage-uncertainty control is inconsistent")
        elif artifact_target is None or operation_target is None:
            raise ValueError("Active scoped leaves require observable targets")
    if artifact_verdict in {"YES", "NO"} and artifact_target is None:
        raise ValueError("Artifact verdict lacks an artifact target")
    if operation_verdict in {"YES", "NO"} and (not active or operation_target is None):
        raise ValueError("Operation verdict lacks an active operation target")
    if artifact["pair_id"] == "mismatched-form":
        if artifact_target == operation_target or (artifact_verdict, operation_verdict) != ("YES", "NO"):
            raise ValueError("Mismatched-form ownership case is not opposed and observable")


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for artifact in load_corpus()["artifacts"]:
        for leaf_id in LEAVES:
            for repeat in range(1, 4):
                slots.append({
                    "slot_id": f"pso-v1-{artifact['case_id']}-{leaf_id.rsplit('.', 1)[-1]}-r{repeat}",
                    "case_id": artifact["case_id"],
                    "pair_id": artifact["pair_id"],
                    "carrier": artifact["carrier"],
                    "leaf_id": leaf_id,
                    "repeat": repeat,
                    "expected_verdict": artifact["expected_verdicts"][leaf_id],
                    "artifact_sha256": artifact_sha256(artifact),
                    "permitted_evidence_sections": artifact["available_evidence_sections"],
                })
    return slots


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "pairing", "artifacts"}:
        raise ValueError("Corpus surface drifted")
    if corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    artifacts = corpus["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 12:
        raise ValueError("Corpus must contain exactly twelve artifacts")
    required = {
        "case_id", "pair_id", "carrier", "artifact_type", "declared_scope", "operation_active",
        "artifact_target", "operation_target", "available_evidence_sections", "sections", "expected_verdicts",
    }
    ids, pairs, labels = set(), {}, set()
    for artifact in artifacts:
        if set(artifact) != required or not isinstance(artifact["case_id"], str) or artifact["case_id"] in ids:
            raise ValueError("Artifact identity drifted")
        ids.add(artifact["case_id"])
        if artifact["carrier"] not in {"isolated", "composite"} or not isinstance(artifact["operation_active"], bool):
            raise ValueError("Carrier or operation activation drifted")
        if set(artifact["expected_verdicts"]) != set(LEAVES) or not set(artifact["expected_verdicts"].values()) <= VERDICTS:
            raise ValueError("Expected verdicts drifted")
        if not isinstance(artifact["available_evidence_sections"], list) or not artifact["available_evidence_sections"]:
            raise ValueError("Evidence sections are unavailable")
        if set(artifact["available_evidence_sections"]) != set(artifact["sections"]):
            raise ValueError("Evidence section binding drifted")
        if any(not isinstance(value, str) or not value.strip() for value in artifact["sections"].values()):
            raise ValueError("Artifact source text is malformed")
        for target in (artifact["artifact_target"], artifact["operation_target"]):
            if target is not None and (set(target) != {"length", "form"} or not all(isinstance(value, str) and value for value in target.values())):
                raise ValueError("Target length/form binding drifted")
        verify_scope_activation_targets(artifact)
        pairs.setdefault(artifact["pair_id"], []).append(artifact)
        labels.update(artifact["expected_verdicts"].values())
    if len(pairs) != 6 or any(len(pair) != 2 or {item["carrier"] for item in pair} != {"isolated", "composite"} for pair in pairs.values()):
        raise ValueError("Six semantic pairs with both carriers are required")
    for pair in pairs.values():
        by_carrier = {item["carrier"]: item for item in pair}
        isolated, composite = by_carrier["isolated"], by_carrier["composite"]
        for key in ("artifact_type", "declared_scope", "operation_active", "artifact_target", "operation_target", "expected_verdicts"):
            if isolated[key] != composite[key]:
                raise ValueError("Pair treatment drifted")
        for key in ("premise", "artifact_brief", "operation_brief"):
            if key in isolated["sections"] and isolated["sections"][key] != composite["sections"].get(key):
                raise ValueError("Pair semantic content drifted")
    if labels != VERDICTS:
        raise ValueError("All four verdict states are required")


def verify_runtime_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    expected_runtime = {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}
    if bindings["runtime"] != expected_runtime:
        raise ValueError("Current production runtime binding drifted")
    expected_local = {"corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}}
    if {key: bindings[key] for key in expected_local} != expected_local:
        raise ValueError("Local frozen binding drifted")
    if source_leaf_records() != CANONICAL_LEAVES or bindings["source_leaves"] != source_leaf_hashes():
        raise ValueError("Canonical leaf invariant drifted")
    ownership = load_json(REPOSITORY / "registry/criterion_ownership.json")
    if {leaf: ownership.get(leaf) for leaf in LEAVES} != {leaf: {"module_id": CANONICAL_LEAVES[leaf]["module_id"], "question_id": leaf} for leaf in LEAVES}:
        raise ValueError("Criterion ownership invariant drifted")


def verify_real_text_holdout(contract: Mapping[str, Any]) -> None:
    if contract["real_text_holdout_commitment"] != HOLDOUT_CONTRACT_BINDING:
        raise ValueError("Real-text holdout contract binding drifted")
    path = ROOT / HOLDOUT_CONTRACT_BINDING["file"]
    if sha256_file(path) != HOLDOUT_CONTRACT_BINDING["file_sha256"] or load_json(path) != HOLDOUT_PUBLIC:
        raise ValueError("Public real-text holdout commitment drifted")


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected_keys = {
        "format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "labels", "screen",
        "scoring", "clarification_successor", "promotion", "real_text_holdout_commitment", "bindings",
    }
    if set(contract) != expected_keys or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID:
        raise ValueError("Contract identity or surface drifted")
    if contract["status"] != "frozen_development_only_current_wording_screen" or contract["development_only"] is not True:
        raise ValueError("Study status drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}:
        raise ValueError("Provider-free boundary drifted")
    if contract["geometry"] != {"artifacts_exact": 12, "semantic_pairs_exact": 6, "leaves_exact": 2, "repeats_exact": 3, "slots_exact": 72, "carriers": ["isolated", "composite"]}:
        raise ValueError("Study geometry drifted")
    if contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]:
        raise ValueError("Four-state semantics drifted")
    if contract["screen"] != {"name": "current_wording", "prompt_policy": "unchanged_production_prompt", "prompt_paths": ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md"], "evidence_separation_required": False, "cross_leaf_section_span_overlap": "record_as_outcome"}:
        raise ValueError("Current wording screen drifted")
    if contract["scoring"] != SCORING:
        raise ValueError("Scoring gate drifted")
    if contract["clarification_successor"] != CLARIFICATION_SUCCESSOR:
        raise ValueError("Clarification successor boundary drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Promotion boundary drifted")
    verify_corpus(load_corpus())
    verify_runtime_bindings(contract)
    verify_real_text_holdout(contract)
    slots = plan_slots()
    if len(slots) != 72 or len({slot["slot_id"] for slot in slots}) != 72:
        raise ValueError("Slot plan drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "artifacts": 12, "slots": 72, "current_wording_bound": True}


def validate_typed_evidence(evidence: Sequence[Mapping[str, Any]], artifact: Mapping[str, Any]) -> None:
    if not isinstance(evidence, Sequence) or isinstance(evidence, (str, bytes)) or not evidence:
        raise ValueError("Evidence must be a nonempty typed sequence")
    sections = artifact["sections"]
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {"kind", "reference", "exact_quote", "summary"}:
            raise ValueError("Evidence item shape is malformed")
        kind, quote, summary = item["kind"], item["exact_quote"], item["summary"]
        if not isinstance(item["reference"], str) or not item["reference"].strip():
            raise ValueError("Evidence reference is malformed")
        if kind == "exact_quote":
            if not isinstance(quote, str) or not quote.strip() or summary is not None or not any(quote in text for text in sections.values()):
                raise ValueError("Exact evidence is malformed or ungrounded")
        elif kind == "summary":
            if quote is not None or not isinstance(summary, str) or not summary.strip():
                raise ValueError("Summary evidence is malformed")
        else:
            raise ValueError("Evidence kind is malformed")


def production_question(leaf_id: str) -> dict[str, Any]:
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundles = load_bundles(REPOSITORY / "bundles" / "all_bundles.json")
    compiled = compile_bundle(modules, resolve_bundle(bundles, "default.ideation"))
    matches = [item for item in compiled_questions(compiled) if item["question"].get("id") == leaf_id]
    if len(matches) != 1:
        raise ValueError("Current bundle does not expose the requested singleton leaf")
    return matches[0]


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION,
        "untrusted_evaluation_data": True,
        "artifact_kind": artifact["artifact_type"],
        "declared_scope": artifact["declared_scope"],
        "completion_status": "complete",
        "background": "Public synthetic development screen for the supplied premise only.",
        "constraints": [
            {"id": "operation_activation", "statement": f"operation_active={artifact['operation_active']}"},
            {"id": "artifact_target", "statement": f"artifact_target={json.dumps(artifact['artifact_target'], sort_keys=True)}"},
            {"id": "operation_target", "statement": f"operation_target={json.dumps(artifact['operation_target'], sort_keys=True)}"},
        ],
        "audience": "development-only rubric validation",
        "preferences": [],
        "priorities": [],
    }


def render_provider_prompt(slot_id: str) -> str:
    slots = {slot["slot_id"]: slot for slot in plan_slots()}
    slot = slots.get(slot_id)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = next(item for item in load_corpus()["artifacts"] if item["case_id"] == slot["case_id"])
    contexts = [
        {"name": f"{name}.txt", "text": text}
        for name, text in artifact["sections"].items()
        if name != "premise"
    ]
    binary_prompt = "\n\n".join(
        (REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip()
        for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")
    )
    prompt = production_runner._render_prompt(
        binary_prompt=binary_prompt,
        artifact={"name": "synthetic-premise.txt", "text": artifact["sections"]["premise"]},
        contexts=contexts,
        bundle_id="default.ideation",
        artifact_id="synthetic-development-artifact",
        questions=[production_question(slot["leaf_id"])],
        task_contract_context=task_context_for(artifact),
    )
    for forbidden in (slot_id, slot["case_id"], "expected_verdict", "oracle"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked ledger or oracle metadata")
    return prompt


def render_all_provider_prompts() -> dict[str, str]:
    rendered = {slot["slot_id"]: render_provider_prompt(slot["slot_id"]) for slot in plan_slots()}
    if len(rendered) != 72:
        raise ValueError("All singleton prompts were not rendered")
    return rendered


def project_production_verdict(slot_id: str, verdict: Mapping[str, Any]) -> dict[str, Any]:
    slots = {slot["slot_id"]: slot for slot in plan_slots()}
    slot = slots.get(slot_id)
    if slot is None:
        raise ValueError("Unknown ledger slot")
    required = {"question_id", "verdict", "confidence", "evidence", "note"}
    if set(verdict) != required or verdict["question_id"] != slot["leaf_id"]:
        raise ValueError("Production verdict surface or leaf is malformed")
    if verdict["verdict"] not in VERDICTS or not isinstance(verdict["confidence"], (int, float)) or not 0 <= verdict["confidence"] <= 1 or not isinstance(verdict["note"], str):
        raise ValueError("Production verdict values are malformed")
    artifact = next(item for item in load_corpus()["artifacts"] if item["case_id"] == slot["case_id"])
    validate_typed_evidence(verdict["evidence"], artifact)
    return {
        "slot_id": slot_id,
        "provider_question_id": verdict["question_id"],
        "expected_verdict": slot["expected_verdict"],
        "observed_verdict": verdict["verdict"],
        "matches_expected": verdict["verdict"] == slot["expected_verdict"],
    }
