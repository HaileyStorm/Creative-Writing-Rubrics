"""Provider-free freeze for an inter-part whole-poem architecture treatment."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-whole-poem-architecture-treatment-v2"
PINNED_COMMIT = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
SOURCE_LEAF_ID = "scope.poetry_poem.form"
ARMS = ("current_wording", "candidate_architecture_wording")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
CANDIDATE_TEXT = (
    "If the declared evaluation scope is not a whole poem, answer NOT_APPLICABLE. If whole-poem scope is declared but the supplied text is not confirmed complete enough for whole-poem judgment, answer CANNOT_ASSESS. Only after completeness is established, answer NOT_APPLICABLE when the poem has fewer than two major parts at whole-poem scale. Otherwise, does a specific structural relationship among those major parts—their ordering, framing, recurrence, juxtaposition, or relative proportion—depend on their placement or scale strongly enough that materially rearranging or resizing them would weaken the poem-wide architecture? YES requires evidence of that inter-part relationship. A merely final or contrasting part, or a plausible thematic or narrative progression by itself, is insufficient. Do not judge local formal mechanics, stanza-boundary effects, turns, ending quality, or movement quality here."
)
REJECTED_WORDING = (
    "Answer NOT_APPLICABLE when the declared evaluation scope is not a whole poem, or when the supplied whole poem has no distinct major units to compare. "
    "Answer CANNOT_ASSESS when whole-poem evaluation is declared but insufficient poem text is supplied. "
    "Considering only the poem-wide ordering and proportion of its major supplied units—not local formal mechanics, stanza-boundary effects, turns, ending, or whether movement succeeds—would materially rearranging those units weaken the poem's whole-poem architecture?"
)
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "registry/modules/scope.poetry_poem.yaml",
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "src/hbqrs/runner.py",
)
SOURCE_FIELDS = ("module_id", "id", "type", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy", "tags")
EXPECTED = {
    "inter_part_positive": "YES",
    "permutation_neutral": "NO",
    "ending_only_coda": "NO",
    "semantic_progression_without_inter_part_relation": "NO",
    "declared_whole_poem_incomplete": "CANNOT_ASSESS",
    "complete_single_part": "NOT_APPLICABLE",
    "declared_excerpt": "NOT_APPLICABLE",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


@lru_cache(maxsize=None)
def git_show_bytes(relative_path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{PINNED_COMMIT}:{relative_path}"], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"Pinned Git object is unavailable: {relative_path}")
    return result.stdout


def verify_bound_paths_unchanged(paths: tuple[str, ...]) -> None:
    result = subprocess.run(["git", "diff", "--quiet", PINNED_COMMIT, "--", *paths], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError("Pinned bound paths drifted from the exact Git parent")


@lru_cache(maxsize=1)
def source_leaf() -> dict[str, Any]:
    records = [json.loads(line) for line in git_show_bytes("registry/question_index.jsonl").decode("utf-8").splitlines()]
    record = next((row for row in records if row.get("id") == SOURCE_LEAF_ID), None)
    if not isinstance(record, dict):
        raise ValueError("Pinned scope source leaf is unavailable")
    return record


@lru_cache(maxsize=1)
def candidate_leaf() -> dict[str, Any]:
    record = deepcopy(source_leaf())
    record["text"] = CANDIDATE_TEXT
    return record


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def _projection(record: Mapping[str, Any], arm: str) -> dict[str, Any]:
    if any(field not in record for field in SOURCE_FIELDS):
        raise ValueError("Source leaf fields are unavailable")
    return {
        **{field: deepcopy(record[field]) for field in SOURCE_FIELDS},
        "domain_id": "scope.poetry_poem",
        "role": "direct_only_candidate_overlay" if arm == "candidate_architecture_wording" else "direct_only_current_leaf_overlay",
    }


def _leaf_projection_hash(record: Mapping[str, Any], arm: str) -> str:
    return hashlib.sha256(canonical_bytes(_projection(record, arm))).hexdigest()


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    cases = corpus["cases"]
    required = {"case_id", "artifact_name", "artifact_type", "declared_scope", "completion_status", "fixture_origin", "source_fixture_id", "text", "candidate_expected"}
    if not isinstance(cases, list) or len(cases) != 7:
        raise ValueError("Exactly seven lineage-declared public synthetic fixtures are required")
    observed: dict[str, str] = {}
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or set(case) != required or case.get("case_id") in observed:
            raise ValueError("Fixture shape drifted")
        expected_lineage = (
            ("new_public_synthetic", f"scope-treatment-v2-{index:02d}")
            if index <= 5 else {
                6: ("inherited_stable_public_synthetic_scope_control", "scope-treatment-v1-03"),
                7: ("inherited_stable_public_synthetic_scope_control", "scope-treatment-v1-04"),
            }[index]
        )
        if case["artifact_name"] != f"scope-fixture-v2-{index:02d}.txt" or (case["fixture_origin"], case["source_fixture_id"]) != expected_lineage or not isinstance(case["text"], str) or not case["text"]:
            raise ValueError("Fresh fixture identity drifted")
        if case["candidate_expected"] not in VERDICTS:
            raise ValueError("Four-state candidate ledger drifted")
        observed[case["case_id"]] = case["candidate_expected"]
    if observed != EXPECTED or set(observed.values()) != VERDICTS:
        raise ValueError("Candidate expected ledger drifted")
    if [case["fixture_origin"] for case in cases].count("new_public_synthetic") != 5 or [case["fixture_origin"] for case in cases].count("inherited_stable_public_synthetic_scope_control") != 2:
        raise ValueError("Fixture lineage count drifted")
    surface = {case["case_id"]: (case["artifact_type"], case["declared_scope"], case["completion_status"]) for case in cases}
    if surface != {
        "inter_part_positive": ("poetry", "poem", "complete"),
        "permutation_neutral": ("poetry", "poem", "complete"),
        "ending_only_coda": ("poetry", "poem", "complete"),
        "semantic_progression_without_inter_part_relation": ("poetry", "poem", "complete"),
        "declared_whole_poem_incomplete": ("poetry", "poem", "unknown"),
        "complete_single_part": ("poetry", "poem", "complete"),
        "declared_excerpt": ("poetry", "stanza", "excerpt"),
    }:
        raise ValueError("Scope and coverage treatment geometry drifted")


def verify_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    if bindings["pinned_commit"] != PINNED_COMMIT:
        raise ValueError("Pinned parent drifted")
    verify_bound_paths_unchanged(RUNTIME_PATHS)
    if bindings["corpus"] != {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}:
        raise ValueError("Corpus binding drifted")
    if bindings["runtime"] != {path: hashlib.sha256(git_show_bytes(path)).hexdigest() for path in RUNTIME_PATHS}:
        raise ValueError("Runtime binding drifted")
    source = source_leaf()
    candidate = candidate_leaf()
    if {key: value for key, value in candidate.items() if key != "text"} != {key: value for key, value in source.items() if key != "text"}:
        raise ValueError("Candidate overlay changed more than source wording")
    if bindings["source_leaf"] != {"id": SOURCE_LEAF_ID, "sha256": _leaf_projection_hash(source, "current_wording")}:
        raise ValueError("Current source-leaf binding drifted")
    if bindings["candidate_leaf"] != {"id": SOURCE_LEAF_ID, "sha256": _leaf_projection_hash(candidate, "candidate_architecture_wording")}:
        raise ValueError("Candidate leaf binding drifted")
    ownership = load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    if ownership.get(SOURCE_LEAF_ID) != {"module_id": source["module_id"], "question_id": SOURCE_LEAF_ID}:
        raise ValueError("Current source ownership binding drifted")
    predecessor = bindings["predecessor"]
    result_path = REPOSITORY / predecessor["public_result_path"]
    if predecessor["public_result_path"] != "evaluation-results/hbq-free-verse-necessity-scope-ablation-v1-public-result-v1/aggregate.v1.json" or not result_path.is_file() or sha256_file(result_path) != predecessor["public_result_sha256"] or predecessor["classification"] != "VALID_EXECUTION_NEGATIVE_DISCRIMINATION_NO_PROMOTION":
        raise ValueError("Negative-result provenance binding drifted")


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for case in load_corpus()["cases"]:
        for arm in ARMS:
            for repeat in range(1, 4):
                slots.append({
                    "slot_id": f"whole-poem-architecture-v2-{len(slots) + 1:03d}",
                    "case_id": case["case_id"],
                    "arm": arm,
                    "repeat": repeat,
                    "candidate_expected": case["candidate_expected"] if arm == "candidate_architecture_wording" else "UNOPENED",
                    "question_projection_sha256": _leaf_projection_hash(candidate_leaf() if arm == "candidate_architecture_wording" else source_leaf(), arm),
                    "fixture_sha256": hashlib.sha256(case["text"].encode("utf-8")).hexdigest(),
                })
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "labels", "fixture_lineage", "treatment", "overlap_review", "promotion", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_provider_free_scope_wording_treatment" or contract["development_only"] is not True:
        raise ValueError("Treatment contract identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}:
        raise ValueError("Provider boundary drifted")
    if contract["geometry"] != {"fixtures_exact": 7, "arms_exact": 2, "repeats_exact": 3, "slots_exact": 42} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]:
        raise ValueError("Treatment geometry drifted")
    if contract["fixture_lineage"] != {"fresh_public_synthetic_discriminatory_cases_exact": 5, "inherited_stable_public_synthetic_scope_controls_exact": 2, "reused_discriminatory_oracle_cases_exact": 0}:
        raise ValueError("Fixture lineage contract drifted")
    if contract["treatment"] != {"source_leaf_id": SOURCE_LEAF_ID, "study_mode": "direct_only_overlay", "current_wording": source_leaf()["text"], "candidate_wording": CANDIDATE_TEXT, "rejected_original_candidate": REJECTED_WORDING, "ordinary_bundle_activation_claimed": False, "compiled_module_claimed": False, "expected_labels_provider_facing": False}:
        raise ValueError("Wording treatment drifted")
    if contract["overlap_review"] != {"status": "revised_after_v1_no_go", "candidate_owner": "whole_poem_architecture_under_inter_part_relationship", "excluded_owners": ["form_specific_mechanics", "stanza_boundary_effects", "turns", "ending_quality", "movement_quality"], "review_required_before_execution": True}:
        raise ValueError("Ownership boundary drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "merge", "weight", "execution")}:
        raise ValueError("Promotion boundary drifted")
    verify_corpus(load_corpus())
    verify_bindings(contract)
    slots = plan_slots()
    expected = {(case_id, arm, repeat) for case_id in EXPECTED for arm in ARMS for repeat in range(1, 4)}
    actual = {(slot["case_id"], slot["arm"], slot["repeat"]) for slot in slots}
    if len(slots) != 42 or len({slot["slot_id"] for slot in slots}) != 42 or actual != expected or sum(slot["candidate_expected"] != "UNOPENED" for slot in slots) != 21:
        raise ValueError("Singleton no-call schedule drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "fixtures": 7, "slots": 42}
