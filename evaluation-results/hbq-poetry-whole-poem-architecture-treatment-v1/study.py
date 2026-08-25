"""Provider-free freeze for a direct-only whole-poem architecture wording treatment."""
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
STUDY_ID = "hbq-poetry-whole-poem-architecture-treatment-v1"
PINNED_COMMIT = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
SOURCE_LEAF_ID = "scope.poetry_poem.form"
ARMS = ("current_wording", "candidate_architecture_wording")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
CANDIDATE_TEXT = (
    "Answer NOT_APPLICABLE when the declared evaluation scope is not a whole poem, or when the supplied whole poem has no distinct major units to compare. "
    "Answer CANNOT_ASSESS when whole-poem evaluation is declared but insufficient poem text is supplied. "
    "Considering only the poem-wide ordering and proportion of its major supplied units—not local formal mechanics, stanza-boundary effects, turns, ending, or whether movement succeeds—would materially rearranging those units weaken the poem's whole-poem architecture?"
)
REJECTED_WORDING = (
    "Answer NOT_APPLICABLE when the declared evaluation scope is not a whole poem. "
    "Answer CANNOT_ASSESS when whole-poem evaluation is declared but insufficient poem text is supplied. "
    "Considering the arrangement of the poem’s major supplied units and total movement—not local lineation, rhythm, meter, or other mechanics owned by form-specific modules—does the whole-poem organization feel necessary to that movement?"
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
    "ordered_architecture": "YES",
    "interchangeable_architecture": "NO",
    "single_unit_poem": "NOT_APPLICABLE",
    "stanza_excerpt": "NOT_APPLICABLE",
    "line_excerpt": "NOT_APPLICABLE",
    "missing_poem_coverage": "CANNOT_ASSESS",
    "owner_positive_architecture_negative": "NO",
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
        raise ValueError("Exactly seven fresh public synthetic fixtures are required")
    observed: dict[str, str] = {}
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or set(case) != required or case.get("case_id") in observed:
            raise ValueError("Fixture shape drifted")
        if case["artifact_name"] != f"scope-fixture-{index:02d}.txt" or case["fixture_origin"] != "new_public_synthetic" or case["source_fixture_id"] != f"scope-treatment-v1-{index:02d}" or not isinstance(case["text"], str) or not case["text"]:
            raise ValueError("Fresh fixture identity drifted")
        if case["candidate_expected"] not in VERDICTS:
            raise ValueError("Four-state candidate ledger drifted")
        observed[case["case_id"]] = case["candidate_expected"]
    if observed != EXPECTED or set(observed.values()) != VERDICTS:
        raise ValueError("Candidate expected ledger drifted")
    surface = {case["case_id"]: (case["artifact_type"], case["declared_scope"], case["completion_status"]) for case in cases}
    if surface != {
        "ordered_architecture": ("poetry", "poem", "complete"),
        "interchangeable_architecture": ("poetry", "poem", "complete"),
        "single_unit_poem": ("poetry", "poem", "complete"),
        "stanza_excerpt": ("poetry", "stanza", "excerpt"),
        "line_excerpt": ("poetry", "line", "excerpt"),
        "missing_poem_coverage": ("poetry", "poem", "unknown"),
        "owner_positive_architecture_negative": ("poetry", "poem", "complete"),
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
                    "slot_id": f"whole-poem-architecture-v1-{len(slots) + 1:03d}",
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
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "labels", "treatment", "overlap_review", "promotion", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_provider_free_scope_wording_treatment" or contract["development_only"] is not True:
        raise ValueError("Treatment contract identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True}:
        raise ValueError("Provider boundary drifted")
    if contract["geometry"] != {"fixtures_exact": 7, "arms_exact": 2, "repeats_exact": 3, "slots_exact": 42} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]:
        raise ValueError("Treatment geometry drifted")
    if contract["treatment"] != {"source_leaf_id": SOURCE_LEAF_ID, "study_mode": "direct_only_overlay", "current_wording": source_leaf()["text"], "candidate_wording": CANDIDATE_TEXT, "rejected_original_candidate": REJECTED_WORDING, "ordinary_bundle_activation_claimed": False, "compiled_module_claimed": False, "expected_labels_provider_facing": False}:
        raise ValueError("Wording treatment drifted")
    if contract["overlap_review"] != {"status": "revised_after_no_go", "candidate_owner": "whole_poem_architecture_under_material_rearrangement", "excluded_owners": ["form_specific_mechanics", "stanza_boundary_effects", "turns", "ending", "movement_success"], "review_required_before_execution": True}:
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
