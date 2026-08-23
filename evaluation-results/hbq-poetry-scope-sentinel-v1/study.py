"""Provider-free freeze verifier for the first staged S1 poetry scope sentinel."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as production_runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-scope-sentinel-v1"
LEAVES = (
    "form.poetry.general_poetry.ending",
    "form.poetry.elegy.movement",
    "form.poetry.free_verse.repetition",
    "form.poetry.haiku_in_english.sequence_scope",
    "form.poetry.pantoum.recontext",
)
STATES = ("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch")
STATE_VERDICTS = {
    "localized_issue": "YES",
    "material_failure": "NO",
    "missing_required_evidence": "CANNOT_ASSESS",
    "activation_mismatch": "NOT_APPLICABLE",
}
STATE_INVARIANT = {
    "localized_issue": {"verdict": "YES", "rule": "localized issue is a revision note, not a material failure"},
    "material_failure": {"verdict": "NO", "rule": "NO is a material failure at declared scope"},
    "missing_required_evidence": {"verdict": "CANNOT_ASSESS", "rule": "missing required evidence is coverage uncertainty"},
    "activation_mismatch": {"verdict": "NOT_APPLICABLE", "rule": "inactive criterion is completed but unscored"},
}
MODULE_PATHS = {
    "form.poetry.general_poetry.ending": "registry/modules/form.poetry.general_poetry.yaml",
    "form.poetry.elegy.movement": "registry/modules/form.poetry.elegy.yaml",
    "form.poetry.free_verse.repetition": "registry/modules/form.poetry.free_verse.yaml",
    "form.poetry.haiku_in_english.sequence_scope": "registry/modules/form.poetry.haiku_in_english.yaml",
    "form.poetry.pantoum.recontext": "registry/modules/form.poetry.pantoum.yaml",
}
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", *MODULE_PATHS.values(),
    "registry/question_index.jsonl", "registry/criterion_ownership.json", "src/hbqrs/runner.py",
)
SCREEN = {
    "name": "current_wording", "prompt_policy": "unchanged_production_prompt",
    "prompt_paths": ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md"],
    "renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False,
}
FINDING_IDS = {
    "form.poetry.general_poetry.ending": "b6916f20a925a6a9229375fef8d6f8b75513f8f8c76e4cf68a9fb5d24f389aa0",
    "form.poetry.elegy.movement": "799fb9f3f2b4b298c9b185fb46119fa96396943c8c8f14c9be9831d4e739aa57",
    "form.poetry.free_verse.repetition": "0bd6d60cc6d3fc8cc68812761f59acfcab4c2de7b1ae6e5c711d6cbb42edce37",
    "form.poetry.haiku_in_english.sequence_scope": "00c63848fca1ca52f1bdf45aa19dc02bee30c5439fb1e10d2f40614c8af4f016",
    "form.poetry.pantoum.recontext": "adeaee9cc0c305024ef7a8efe20902c9070c7b53074a4c82004cd6e2da2f8e6c",
}
REJECTED_HAIKU_POLARITY_FINDING = "f69aee26f88757d6d364c34b4d921d764cf7944ed0e896f3e18a9189ffe7e8aa"
FIXTURE_CONTRACTS = {
    ("form.poetry.general_poetry.ending", "localized_issue"): {"fixture_id": "pss-ending-local", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "YES"},
    ("form.poetry.general_poetry.ending", "material_failure"): {"fixture_id": "pss-ending-material", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "NO"},
    ("form.poetry.general_poetry.ending", "missing_required_evidence"): {"fixture_id": "pss-ending-unknown", "completion_status": "excerpt", "evaluation_scope": "stanza", "parent_status": "unknown", "oracle_verdict": "CANNOT_ASSESS"},
    ("form.poetry.general_poetry.ending", "activation_mismatch"): {"fixture_id": "pss-ending-inactive", "completion_status": "complete", "evaluation_scope": "non_poetry", "parent_status": "complete", "oracle_verdict": "NOT_APPLICABLE"},
    ("form.poetry.elegy.movement", "localized_issue"): {"fixture_id": "pss-elegy-local", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "YES"},
    ("form.poetry.elegy.movement", "material_failure"): {"fixture_id": "pss-elegy-material", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "NO"},
    ("form.poetry.elegy.movement", "missing_required_evidence"): {"fixture_id": "pss-elegy-unknown", "completion_status": "excerpt", "evaluation_scope": "stanza", "parent_status": "unknown", "oracle_verdict": "CANNOT_ASSESS"},
    ("form.poetry.elegy.movement", "activation_mismatch"): {"fixture_id": "pss-elegy-inactive", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "NOT_APPLICABLE"},
    ("form.poetry.free_verse.repetition", "localized_issue"): {"fixture_id": "pss-free-local", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "YES"},
    ("form.poetry.free_verse.repetition", "material_failure"): {"fixture_id": "pss-free-material", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "NO"},
    ("form.poetry.free_verse.repetition", "missing_required_evidence"): {"fixture_id": "pss-free-unknown", "completion_status": "excerpt", "evaluation_scope": "stanza", "parent_status": "unknown", "oracle_verdict": "CANNOT_ASSESS"},
    ("form.poetry.free_verse.repetition", "activation_mismatch"): {"fixture_id": "pss-free-inactive", "completion_status": "complete", "evaluation_scope": "non_poetry", "parent_status": "complete", "oracle_verdict": "NOT_APPLICABLE"},
    ("form.poetry.haiku_in_english.sequence_scope", "localized_issue"): {"fixture_id": "pss-haiku-local", "completion_status": "complete", "evaluation_scope": "sequence", "parent_status": "complete", "oracle_verdict": "YES"},
    ("form.poetry.haiku_in_english.sequence_scope", "material_failure"): {"fixture_id": "pss-haiku-material", "completion_status": "complete", "evaluation_scope": "sequence", "parent_status": "complete", "oracle_verdict": "NO"},
    ("form.poetry.haiku_in_english.sequence_scope", "missing_required_evidence"): {"fixture_id": "pss-haiku-unknown", "completion_status": "excerpt", "evaluation_scope": "stanza", "parent_status": "unknown", "oracle_verdict": "CANNOT_ASSESS"},
    ("form.poetry.haiku_in_english.sequence_scope", "activation_mismatch"): {"fixture_id": "pss-haiku-inactive", "completion_status": "complete", "evaluation_scope": "stanza", "parent_status": "complete", "oracle_verdict": "NOT_APPLICABLE"},
    ("form.poetry.pantoum.recontext", "localized_issue"): {"fixture_id": "pss-pantoum-local", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "YES"},
    ("form.poetry.pantoum.recontext", "material_failure"): {"fixture_id": "pss-pantoum-material", "completion_status": "complete", "evaluation_scope": "poem", "parent_status": "complete", "oracle_verdict": "NO"},
    ("form.poetry.pantoum.recontext", "missing_required_evidence"): {"fixture_id": "pss-pantoum-unknown", "completion_status": "excerpt", "evaluation_scope": "stanza", "parent_status": "unknown", "oracle_verdict": "CANNOT_ASSESS"},
    ("form.poetry.pantoum.recontext", "activation_mismatch"): {"fixture_id": "pss-pantoum-inactive", "completion_status": "complete", "evaluation_scope": "non_poetry", "parent_status": "complete", "oracle_verdict": "NOT_APPLICABLE"},
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def source_leaf_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry/question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in LEAVES:
            records[row["id"]] = {key: row[key] for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")}
    if set(records) != set(LEAVES):
        raise ValueError("Canonical source leaves are unavailable")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in source_leaf_records().items()}


def artifact_sha256(artifact: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(artifact)).hexdigest()


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "states", "artifacts"}:
        raise ValueError("Corpus surface drifted")
    if corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only" or corpus["states"] != list(STATES):
        raise ValueError("Corpus identity drifted")
    artifacts = corpus["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 20:
        raise ValueError("Corpus must contain exactly twenty artifacts")
    seen: set[tuple[str, str]] = set()
    for artifact in artifacts:
        if set(artifact) != {"leaf_id", "state", "artifact_kind", "declared_scope", "text", "contexts"}:
            raise ValueError("Artifact surface drifted")
        leaf, state = artifact["leaf_id"], artifact["state"]
        if leaf not in LEAVES or state not in STATES or (leaf, state) in seen:
            raise ValueError("Artifact matrix drifted")
        seen.add((leaf, state))
        fixture = FIXTURE_CONTRACTS[(leaf, state)]
        if fixture["oracle_verdict"] != STATE_VERDICTS[state] or not artifact["declared_scope"].strip() or not artifact["text"].strip() or not artifact["contexts"]:
            raise ValueError("Fixture contract drifted")
        if state == "localized_issue" and "revision note" not in " ".join(artifact["contexts"]).lower():
            raise ValueError("Localized issue must remain a revision note")
        if state == "missing_required_evidence" and (fixture["completion_status"], fixture["parent_status"]) != ("excerpt", "unknown"):
            raise ValueError("Coverage control must preserve excerpt and unknown parent")
        if state == "activation_mismatch" and not any(token in " ".join(artifact["contexts"]).lower() for token in ("inactive", "not a", "no ")):
            raise ValueError("Activation mismatch is not explicit")
    if seen != {(leaf, state) for leaf in LEAVES for state in STATES}:
        raise ValueError("Four-state leaf matrix is incomplete")


def verify_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    if bindings["runtime"] != {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}:
        raise ValueError("Current production runtime binding drifted")
    if bindings["source_leaves"] != source_leaf_hashes():
        raise ValueError("Exact current leaf bytes drifted")
    if bindings["corpus"] != {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}:
        raise ValueError("Public synthetic corpus binding drifted")
    ownership = load_json(REPOSITORY / "registry/criterion_ownership.json")
    expected = {leaf: {"module_id": source_leaf_records()[leaf]["module_id"], "question_id": leaf} for leaf in LEAVES}
    if {leaf: ownership.get(leaf) for leaf in LEAVES} != expected:
        raise ValueError("Criterion ownership invariant drifted")
    portfolio = contract["portfolio_binding"]
    if sha256_file(REPOSITORY / portfolio["manifest_path"]) != portfolio["manifest_sha256"] or sha256_file(REPOSITORY / portfolio["findings_path"]) != portfolio["findings_sha256"]:
        raise ValueError("Frozen portfolio binding drifted")
    selected = next((item for item in load_json(REPOSITORY / portfolio["manifest_path"])["packages"] if item["package_id"] == "S1"), None)
    if portfolio["package"] != "S1" or portfolio["frozen_initial_slots_exact"] != 420 or portfolio["this_first_staged_subset_slots_exact"] != 60 or portfolio["additive_to_portfolio"] is not False or not isinstance(selected, Mapping) or selected["initial_calls_exact"] != 420 or list(portfolio["leaf_findings"]) != list(LEAVES) or portfolio["leaf_findings"] != FINDING_IDS or not set(FINDING_IDS.values()).issubset(selected["finding_ids"]):
        raise ValueError("S1 portfolio boundary drifted")
    rows = {row["finding_id"]: row for row in load_jsonl(REPOSITORY / portfolio["findings_path"])}
    for leaf, finding_id in FINDING_IDS.items():
        if rows.get(finding_id, {}).get("kind") != "scope_binding_review" or rows[finding_id].get("subjects") != [leaf]:
            raise ValueError("Leaf-to-finding source mapping drifted")
    rejected = rows.get(REJECTED_HAIKU_POLARITY_FINDING, {})
    if rejected.get("kind") != "polarity_change" or rejected.get("subjects") != ["form.poetry.haiku_in_english.sequence_scope"] or rejected.get("first_remedy", {}).get("selected") is not None:
        raise ValueError("Rejected haiku polarity context drifted")


def plan_slots(expected_labels: Mapping[str, str] = STATE_VERDICTS) -> list[dict[str, Any]]:
    if set(expected_labels) != set(STATES):
        raise ValueError("Expected-label mutation surface drifted")
    slots: list[dict[str, Any]] = []
    for artifact_index, artifact in enumerate(load_corpus()["artifacts"], start=1):
        for repeat in range(1, 4):
            slots.append({"slot_id": f"pss-v1-{artifact_index:02d}-r{repeat}", "artifact_index": artifact_index - 1, "leaf_id": artifact["leaf_id"], "state": artifact["state"], "repeat": repeat, "fixture_id": FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]["fixture_id"], "expected_verdict": expected_labels[artifact["state"]], "artifact_sha256": artifact_sha256(artifact)})
    return slots


def production_question(leaf_id: str) -> dict[str, Any]:
    record = source_leaf_records()[leaf_id]
    return {"question": {"id": leaf_id, **record}, "module_id": record["module_id"], "domain_id": None, "role": "core"}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    carrier = FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_kind"], "declared_scope": artifact["declared_scope"], "completion_status": carrier["completion_status"], "background": "Public synthetic development screen for the declared poetic scope only.", "constraints": [{"id": "scope", "statement": "Use only the supplied poem and contexts."}, {"id": "evaluation_scope", "statement": carrier["evaluation_scope"]}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def render_provider_prompt(slot_id: str, expected_labels: Mapping[str, str] = STATE_VERDICTS) -> str:
    slot = next((value for value in plan_slots(expected_labels) if value["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = load_corpus()["artifacts"][slot["artifact_index"]]
    binary_prompt = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt, artifact={"name": "synthetic-poetry-artifact.txt", "text": artifact["text"]}, contexts=[{"name": f"context-{index + 1}.txt", "text": text} for index, text in enumerate(artifact["contexts"])], bundle_id="poetry-scope-sentinel", artifact_id="public-synthetic-artifact", questions=[production_question(slot["leaf_id"])], task_contract_context=task_context_for(artifact))
    for forbidden in (slot["slot_id"], slot["state"], slot["fixture_id"], "oracle", "artifact_index"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local ledger metadata")
    return prompt


def render_all_provider_prompts(expected_labels: Mapping[str, str] = STATE_VERDICTS) -> dict[str, str]:
    prompts = {slot["slot_id"]: render_provider_prompt(slot["slot_id"], expected_labels) for slot in plan_slots(expected_labels)}
    if len(prompts) != 60:
        raise ValueError("All singleton prompts were not rendered")
    return prompts


def pantoum_repeated_line_pairs() -> list[tuple[str, int, int]]:
    artifact = next(item for item in load_corpus()["artifacts"] if item["leaf_id"] == "form.poetry.pantoum.recontext" and item["state"] == "localized_issue")
    lines = [line for stanza in artifact["text"].split("\n\n") for line in stanza.splitlines()]
    pairs: list[tuple[str, int, int]] = []
    for later, line in enumerate(lines):
        earlier = next((index for index, candidate in enumerate(lines[:later]) if candidate.rstrip(".—,;").casefold() == line.rstrip(".—,;").casefold()), None)
        if earlier is not None:
            pairs.append((line, earlier, later))
    return pairs


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "portfolio_binding", "geometry", "labels", "state_invariant", "carrier_axes", "screen", "promotion", "rejected_context", "sealed_successor_gate", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_development_only_poetry_scope_sentinel" or contract["development_only"] is not True:
        raise ValueError("Contract identity or surface drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}:
        raise ValueError("Provider-free boundary drifted")
    if contract["geometry"] != {"leaves_exact": 5, "states_exact": 4, "artifacts_exact": 20, "repeats_exact": 3, "slots_exact": 60} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"] or contract["state_invariant"] != STATE_INVARIANT or contract["screen"] != SCREEN:
        raise ValueError("Study geometry or screen drifted")
    if contract["carrier_axes"] != {"completion_status": ["complete", "excerpt"], "parent_status": ["complete", "unknown"], "evaluation_scope": ["stanza", "poem", "sequence", "non_poetry"], "independent_carrier_metadata": True}:
        raise ValueError("Carrier-axis binding drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight", "influence")}:
        raise ValueError("Promotion boundary drifted")
    if contract["rejected_context"] != {"finding_id": REJECTED_HAIKU_POLARITY_FINDING, "controlling": False, "reason": "positive YES orientation remains correct"}:
        raise ValueError("Rejected context boundary drifted")
    if contract["sealed_successor_gate"] != {"affected_leaf_only": True, "private_quartet_current_and_candidate_calls_exact": 24, "candidate_required": "12/12", "no_regression_required": True, "baseline_differential_required": True, "sol_smallest_repair_review_required": True, "unchanged": ["id", "owner", "polarity", "weight", "influence"], "synthetic_success_authorizes_only": "real_or_archived_holdout"}:
        raise ValueError("Sealed successor gate drifted")
    verify_corpus(load_corpus())
    verify_bindings(contract)
    slots = plan_slots()
    if len(slots) != 60 or len({slot["slot_id"] for slot in slots}) != 60 or {slot["expected_verdict"] for slot in slots} != set(STATE_VERDICTS.values()):
        raise ValueError("Slot plan drifted")
    if len(pantoum_repeated_line_pairs()) != 8:
        raise ValueError("Pantoum recontext fixture drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "artifacts": 20, "slots": 60, "staged_subset_of_s1": 420}
