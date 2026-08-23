"""Provider-free freeze verifier for the first staged S2 scope sentinel."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as production_runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-nonpoetry-scope-sentinel-v1"
LEAVES = (
    "craft.narrative.character_arc.end_state",
    "data.eval.evaluation_determinism.rerun",
    "modifier.genre.hybrid_or_genre_blend.tone",
    "op.critique.single_unit_critique.no_whole_claims",
    "scope.passage.status",
)
STATES = ("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
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
SCREEN = {
    "name": "current_wording", "prompt_policy": "unchanged_production_prompt",
    "prompt_paths": ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md"],
    "renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False,
}
FIXTURE_CONTRACTS = {
    ("craft.narrative.character_arc.end_state", "localized_issue"): {"fixture_id": "npss-character-local", "oracle_verdict": "YES", "completion_status": "complete", "scope_declaration": "complete novella"},
    ("craft.narrative.character_arc.end_state", "material_failure"): {"fixture_id": "npss-character-material", "oracle_verdict": "NO", "completion_status": "complete", "scope_declaration": "complete novella"},
    ("craft.narrative.character_arc.end_state", "missing_required_evidence"): {"fixture_id": "npss-character-unknown", "oracle_verdict": "CANNOT_ASSESS", "completion_status": "unknown", "scope_declaration": "complete novella"},
    ("craft.narrative.character_arc.end_state", "activation_mismatch"): {"fixture_id": "npss-character-inactive", "oracle_verdict": "NOT_APPLICABLE", "completion_status": "complete", "scope_declaration": "metadata record"},
    ("data.eval.evaluation_determinism.rerun", "localized_issue"): {"fixture_id": "npss-rerun-local", "oracle_verdict": "YES", "completion_status": "complete", "scope_declaration": "complete evaluation run"},
    ("data.eval.evaluation_determinism.rerun", "material_failure"): {"fixture_id": "npss-rerun-material", "oracle_verdict": "NO", "completion_status": "complete", "scope_declaration": "complete evaluation run"},
    ("data.eval.evaluation_determinism.rerun", "missing_required_evidence"): {"fixture_id": "npss-rerun-unknown", "oracle_verdict": "CANNOT_ASSESS", "completion_status": "unknown", "scope_declaration": "complete evaluation run"},
    ("data.eval.evaluation_determinism.rerun", "activation_mismatch"): {"fixture_id": "npss-rerun-inactive", "oracle_verdict": "NOT_APPLICABLE", "completion_status": "complete", "scope_declaration": "dataset card"},
    ("modifier.genre.hybrid_or_genre_blend.tone", "localized_issue"): {"fixture_id": "npss-tone-local", "oracle_verdict": "YES", "completion_status": "complete", "scope_declaration": "complete short story"},
    ("modifier.genre.hybrid_or_genre_blend.tone", "material_failure"): {"fixture_id": "npss-tone-material", "oracle_verdict": "NO", "completion_status": "complete", "scope_declaration": "complete short story"},
    ("modifier.genre.hybrid_or_genre_blend.tone", "missing_required_evidence"): {"fixture_id": "npss-tone-unknown", "oracle_verdict": "CANNOT_ASSESS", "completion_status": "unknown", "scope_declaration": "complete short story"},
    ("modifier.genre.hybrid_or_genre_blend.tone", "activation_mismatch"): {"fixture_id": "npss-tone-inactive", "oracle_verdict": "NOT_APPLICABLE", "completion_status": "complete", "scope_declaration": "complete short story"},
    ("op.critique.single_unit_critique.no_whole_claims", "localized_issue"): {"fixture_id": "npss-critique-local", "oracle_verdict": "YES", "completion_status": "complete", "scope_declaration": "single scene critique"},
    ("op.critique.single_unit_critique.no_whole_claims", "material_failure"): {"fixture_id": "npss-critique-material", "oracle_verdict": "NO", "completion_status": "complete", "scope_declaration": "single scene critique"},
    ("op.critique.single_unit_critique.no_whole_claims", "missing_required_evidence"): {"fixture_id": "npss-critique-unknown", "oracle_verdict": "CANNOT_ASSESS", "completion_status": "unknown", "scope_declaration": "single scene critique"},
    ("op.critique.single_unit_critique.no_whole_claims", "activation_mismatch"): {"fixture_id": "npss-critique-inactive", "oracle_verdict": "NOT_APPLICABLE", "completion_status": "complete", "scope_declaration": "marketing copy"},
    ("scope.passage.status", "localized_issue"): {"fixture_id": "npss-passage-local", "oracle_verdict": "YES", "completion_status": "excerpt", "scope_declaration": "excerpt from a novel"},
    ("scope.passage.status", "material_failure"): {"fixture_id": "npss-passage-material", "oracle_verdict": "NO", "completion_status": "excerpt", "scope_declaration": "excerpt from a novel"},
    ("scope.passage.status", "missing_required_evidence"): {"fixture_id": "npss-passage-unknown", "oracle_verdict": "CANNOT_ASSESS", "completion_status": "unknown", "scope_declaration": "unspecified"},
    ("scope.passage.status", "activation_mismatch"): {"fixture_id": "npss-passage-inactive", "oracle_verdict": "NOT_APPLICABLE", "completion_status": "complete", "scope_declaration": "catalog record"},
}
LEAF_ARTIFACT_KINDS = {
    "craft.narrative.character_arc.end_state": "prose_fiction",
    "data.eval.evaluation_determinism.rerun": "evaluation_pipeline",
    "modifier.genre.hybrid_or_genre_blend.tone": "prose_fiction",
    "op.critique.single_unit_critique.no_whole_claims": "critique_report",
    "scope.passage.status": "scope_evaluation_record",
}
MODULE_PATHS = {
    "craft.narrative.character_arc.end_state": "registry/modules/craft.narrative.character_arc.yaml",
    "data.eval.evaluation_determinism.rerun": "registry/modules/data.eval.evaluation_determinism.yaml",
    "modifier.genre.hybrid_or_genre_blend.tone": "registry/modules/modifier.genre.hybrid_or_genre_blend.yaml",
    "op.critique.single_unit_critique.no_whole_claims": "registry/modules/op.critique.single_unit_critique.yaml",
    "scope.passage.status": "registry/modules/scope.passage.yaml",
}
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", *MODULE_PATHS.values(),
    "registry/question_index.jsonl", "registry/criterion_ownership.json", "src/hbqrs/runner.py",
)


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
            records[row["id"]] = {key: row[key] for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity")}
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
        fixture = FIXTURE_CONTRACTS.get((leaf, state))
        if not isinstance(fixture, Mapping) or fixture["oracle_verdict"] != STATE_VERDICTS[state] or fixture["scope_declaration"] != artifact["declared_scope"]:
            raise ValueError("Exact fixture oracle or task-context contract drifted")
        expected_completion = "unknown" if state == "missing_required_evidence" else "excerpt" if leaf == "scope.passage.status" and state in {"localized_issue", "material_failure"} else "complete"
        if fixture["completion_status"] != expected_completion:
            raise ValueError("Fixture completion-status regime drifted")
        if (state != "activation_mismatch" and artifact["artifact_kind"] != LEAF_ARTIFACT_KINDS[leaf]) or not isinstance(artifact["declared_scope"], str) or not artifact["declared_scope"].strip():
            raise ValueError("Leaf-to-artifact applicability drifted")
        if not isinstance(artifact["text"], str) or not artifact["text"].strip() or not isinstance(artifact["contexts"], list) or not artifact["contexts"] or not all(isinstance(item, str) and item.strip() for item in artifact["contexts"]):
            raise ValueError("Synthetic evidence is malformed")
        visible = " ".join((artifact["text"], *artifact["contexts"])).lower()
        if state == "localized_issue" and "revision note" not in visible:
            raise ValueError("Localized issue must remain a revision note")
        if state == "material_failure" and artifact["declared_scope"] == "unspecified":
            raise ValueError("Material failure must bind a declared scope")
        if state == "missing_required_evidence" and not any(token in visible for token in ("omits", "no repeated", "does not establish", "no supplied", "does not state", "unknown")):
            raise ValueError("Coverage control does not disclose missing evidence")
        if state == "activation_mismatch" and "no " not in visible:
            raise ValueError("Activation mismatch is not explicit")
    if seen != {(leaf, state) for leaf in LEAVES for state in STATES}:
        raise ValueError("Four-state leaf matrix is incomplete")
    if set(FIXTURE_CONTRACTS) != seen or len({value["fixture_id"] for value in FIXTURE_CONTRACTS.values()}) != 20:
        raise ValueError("Fixture identity table drifted")


def verify_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    expected_runtime = {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}
    if bindings["runtime"] != expected_runtime:
        raise ValueError("Current production runtime binding drifted")
    if bindings["corpus"] != {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}:
        raise ValueError("Public synthetic corpus binding drifted")
    if bindings["source_leaves"] != source_leaf_hashes():
        raise ValueError("Exact current leaf bytes drifted")
    ownership = load_json(REPOSITORY / "registry/criterion_ownership.json")
    expected_ownership = {leaf: {"module_id": source_leaf_records()[leaf]["module_id"], "question_id": leaf} for leaf in LEAVES}
    if {leaf: ownership.get(leaf) for leaf in LEAVES} != expected_ownership:
        raise ValueError("Criterion ownership invariant drifted")
    portfolio = contract["portfolio_binding"]
    manifest_path = REPOSITORY / portfolio["manifest_path"]
    if sha256_file(manifest_path) != portfolio["manifest_sha256"]:
        raise ValueError("Frozen S2 portfolio manifest binding drifted")
    manifest = load_json(manifest_path)
    selected = next((item for item in manifest["packages"] if item.get("package_id") == "S2"), None)
    if set(portfolio["leaf_findings"]) != set(LEAVES) or list(portfolio["leaf_findings"].values()) != portfolio["finding_ids"]:
        raise ValueError("Leaf-to-finding binding drifted")
    if not isinstance(selected, Mapping) or selected.get("initial_calls_exact") != portfolio["frozen_initial_slots_exact"] or not set(portfolio["finding_ids"]).issubset(selected.get("finding_ids", [])):
        raise ValueError("Exact S2 finding-ID binding drifted")
    findings_path = REPOSITORY / portfolio["findings_path"]
    if sha256_file(findings_path) != portfolio["findings_sha256"]:
        raise ValueError("Frozen finding-record binding drifted")
    finding_rows = {row.get("finding_id"): row for row in load_jsonl(findings_path)}
    for leaf, finding_id in portfolio["leaf_findings"].items():
        row = finding_rows.get(finding_id)
        if not isinstance(row, Mapping) or row.get("kind") != "scope_binding_review" or row.get("subjects") != [leaf]:
            raise ValueError("Leaf-to-finding source mapping drifted")


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for artifact in load_corpus()["artifacts"]:
        for repeat in range(1, 4):
            slots.append({
                "slot_id": f"npss-v1-{len(slots) // 3 + 1:02d}-r{repeat}",
                "leaf_id": artifact["leaf_id"], "repeat": repeat, "state": artifact["state"],
                "fixture_id": FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]["fixture_id"],
                "expected_verdict": STATE_VERDICTS[artifact["state"]], "artifact_sha256": artifact_sha256(artifact),
            })
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "portfolio_binding", "geometry", "labels", "state_invariant", "screen", "promotion", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID:
        raise ValueError("Contract identity or surface drifted")
    if contract["status"] != "frozen_development_only_nonpoetry_scope_sentinel" or contract["development_only"] is not True:
        raise ValueError("Study status drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}:
        raise ValueError("Provider-free boundary drifted")
    if contract["portfolio_binding"] != {"package": "S2", "manifest_path": "evaluation-results/hbq-first-remedy-portfolio-v1/manifest.json", "manifest_sha256": "eebe2ac7a7b592459e5b084d8f6806a56ccd7a8c077e6508b34e0a0818111d32", "findings_path": "evaluation-results/hbq-full-leaf-structural-audit-v1/findings.jsonl", "findings_sha256": "06c08ef035a09288fa6710db51786ec1a73b71116ac9b23e4c2a09ece8fa14a1", "frozen_initial_slots_exact": 300, "this_first_staged_subset_slots_exact": 60, "additive_to_portfolio": False, "leaf_findings": {"craft.narrative.character_arc.end_state": "68d285cbf064d7d2dfedf708163087baf5573c51f2dd6e8e38cc1a5a470b7911", "data.eval.evaluation_determinism.rerun": "0354e235f1a9d2cd76c8867ff027e94c392c345a097a61bf09143e186b2f2e6f", "modifier.genre.hybrid_or_genre_blend.tone": "a4df027d1648482ceaa1f775b18266359c253b347f4456056d82b416e396d7f8", "op.critique.single_unit_critique.no_whole_claims": "815666a33000670ae350d9e2a7471b27a820e9e91ea18f190c5573a5305202a5", "scope.passage.status": "eb17cc18285de2bf8614389623255d9b5df9d5e0f85fac16fde6a79a2c8023d6"}, "finding_ids": ["68d285cbf064d7d2dfedf708163087baf5573c51f2dd6e8e38cc1a5a470b7911", "0354e235f1a9d2cd76c8867ff027e94c392c345a097a61bf09143e186b2f2e6f", "a4df027d1648482ceaa1f775b18266359c253b347f4456056d82b416e396d7f8", "815666a33000670ae350d9e2a7471b27a820e9e91ea18f190c5573a5305202a5", "eb17cc18285de2bf8614389623255d9b5df9d5e0f85fac16fde6a79a2c8023d6"]}:
        raise ValueError("S2 portfolio boundary drifted")
    if contract["geometry"] != {"leaves_exact": 5, "states_exact": 4, "artifacts_exact": 20, "repeats_exact": 3, "slots_exact": 60} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]:
        raise ValueError("Study geometry drifted")
    if contract["state_invariant"] != STATE_INVARIANT:
        raise ValueError("Scope invariant drifted")
    if contract["screen"] != SCREEN:
        raise ValueError("Production screen binding drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Promotion boundary drifted")
    verify_corpus(load_corpus())
    verify_bindings(contract)
    slots = plan_slots()
    if len(slots) != 60 or len({slot["slot_id"] for slot in slots}) != 60 or {slot["expected_verdict"] for slot in slots} != VERDICTS:
        raise ValueError("Slot plan drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "artifacts": 20, "slots": 60, "staged_subset_of_s2": 300}


def production_question(leaf_id: str) -> dict[str, Any]:
    record = source_leaf_records()[leaf_id]
    return {"question": {"id": leaf_id, **record, "evidence_policy": {"required": True, "minimum_references": 1, "reference_style": "artifact span, unit ID, timestamp, or source ID"}}, "module_id": record["module_id"], "domain_id": None, "role": "core"}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    fixture = FIXTURE_CONTRACTS[(artifact["leaf_id"], artifact["state"])]
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_kind"], "declared_scope": fixture["scope_declaration"], "completion_status": fixture["completion_status"], "background": "Public synthetic development screen for declared scope only.", "constraints": [{"id": "scope", "statement": "Use only supplied artifact and contexts."}, {"id": "scope_declaration", "statement": fixture["scope_declaration"]}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def render_provider_prompt(slot_id: str) -> str:
    slots = {slot["slot_id"]: slot for slot in plan_slots()}
    slot = slots.get(slot_id)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = load_corpus()["artifacts"][(int(slot_id.split("-")[-2]) - 1)]
    binary_prompt = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt, artifact={"name": "synthetic-scope-artifact.txt", "text": artifact["text"]}, contexts=[{"name": f"context-{index + 1}.txt", "text": text} for index, text in enumerate(artifact["contexts"])], bundle_id="scope-sentinel", artifact_id="public-synthetic-artifact", questions=[production_question(slot["leaf_id"])], task_contract_context=task_context_for(artifact))
    for forbidden in (slot_id, slot["state"], "expected_verdict", "oracle"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local ledger metadata")
    return prompt


def render_all_provider_prompts() -> dict[str, str]:
    prompts = {slot["slot_id"]: render_provider_prompt(slot["slot_id"]) for slot in plan_slots()}
    if len(prompts) != 60:
        raise ValueError("All singleton prompts were not rendered")
    return prompts
