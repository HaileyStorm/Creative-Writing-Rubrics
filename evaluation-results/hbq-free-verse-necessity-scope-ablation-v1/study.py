"""Provider-free planner for the free-verse necessity / scope-form ablation."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from hbqrs import runner as production_runner


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-free-verse-necessity-scope-ablation-v1"
PINNED_COMMIT = "4ce1204d8dd97feff2c7bd88237e265fac742adb"
FINDING_ID = "338b510127809018cc8f14b2674e5960ac6bb70d8692e7af300d74a3eab0ed80"
LEAVES = ("form.poetry.free_verse.necessity", "scope.poetry_poem.form")
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
MODULE_PATHS = {
    "form.poetry.free_verse.necessity": "registry/modules/form.poetry.free_verse.yaml",
    "scope.poetry_poem.form": "registry/modules/scope.poetry_poem.yaml",
}
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    *MODULE_PATHS.values(),
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "src/hbqrs/runner.py",
)
EXPECTED = {
    "complete-necessary": ("YES", "YES"),
    "complete-arbitrary": ("NO", "YES"),
    "stanza-excerpt": ("YES", "NOT_APPLICABLE"),
    "line-excerpt": ("CANNOT_ASSESS", "NOT_APPLICABLE"),
    "missing-poem-coverage": ("CANNOT_ASSESS", "CANNOT_ASSESS"),
    "inactive-metadata-control": ("NOT_APPLICABLE", "NOT_APPLICABLE"),
}
DIRECT_PROJECTION = {
    "form.poetry.free_verse.necessity": {"domain_id": "form", "role": "direct_only_form_leaf"},
    "scope.poetry_poem.form": {"domain_id": "scope.poetry_poem", "role": "direct_only_scope_overlay"},
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


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


@lru_cache(maxsize=None)
def git_show_bytes(relative_path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{PINNED_COMMIT}:{relative_path}"], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"Pinned Git object is unavailable: {relative_path}")
    return result.stdout


def verify_bound_paths_unchanged(relative_paths: tuple[str, ...]) -> None:
    result = subprocess.run(["git", "diff", "--quiet", PINNED_COMMIT, "--", *relative_paths], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError("Pinned bound paths drifted from the exact Git parent")


@lru_cache(maxsize=1)
def source_leaf_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in LEAVES:
            records[row["id"]] = {key: row[key] for key in ("module_id", "id", "type", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy", "tags")}
    if tuple(records) != LEAVES:
        raise ValueError("Canonical source leaves are unavailable")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in source_leaf_records().items()}


@lru_cache(maxsize=1)
def predecessor_fixtures() -> dict[str, dict[str, Any]]:
    contract = load_contract()
    binding = contract["bindings"]["source_fixture"]
    frozen_bytes = git_show_bytes(binding["path"])
    source_path = REPOSITORY / binding["path"]
    verify_bound_paths_unchanged((binding["path"],))
    if not source_path.is_file() or hashlib.sha256(frozen_bytes).hexdigest() != binding["git_object_sha256"]:
        raise ValueError("Original public fixture bytes drifted")
    source = json.loads(frozen_bytes.decode("utf-8"))
    block = next((item for item in source.get("blocks", []) if item.get("block_id") == "free_verse_form_scope"), None)
    if block is None or block.get("finding_id") != FINDING_ID:
        raise ValueError("Original free-verse fixture block is unavailable")
    return {item["artifact_name"]: item for item in block["conditions"]}


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    required_case = {"case_id", "fixture_origin", "source_fixture_id", "lineage_expected", "artifact_name", "artifact_type", "declared_scope", "completion_status", "text", "expected"}
    if set(corpus) != {"format_version", "study_id", "privacy", "leaves", "cases"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only" or tuple(corpus["leaves"]) != LEAVES:
        raise ValueError("Corpus identity or pairing drifted")
    cases = corpus["cases"]
    if not isinstance(cases, list) or len(cases) != len(EXPECTED):
        raise ValueError("Exactly six public synthetic conditions are required")
    observed: dict[str, tuple[str, str]] = {}
    for index, case in enumerate(cases, start=1):
        if set(case) != required_case or case.get("case_id") in observed or case.get("case_id") not in EXPECTED:
            raise ValueError("Case identity drifted")
        if case["artifact_name"] != f"fixture-{index:02d}.txt" or not isinstance(case["text"], str) or not isinstance(case["source_fixture_id"], str):
            raise ValueError("Public fixture surface drifted")
        expected = tuple(case["expected"])
        if expected != EXPECTED[case["case_id"]] or len(expected) != len(LEAVES) or not set(expected) <= VERDICTS:
            raise ValueError("Four-state expected ledger drifted")
        observed[case["case_id"]] = expected
    if observed != EXPECTED or {state for pair in observed.values() for state in pair} != VERDICTS:
        raise ValueError("Expected state coverage drifted")
    fields = {case["case_id"]: (case["artifact_type"], case["declared_scope"], case["completion_status"]) for case in cases}
    if fields != {
        "complete-necessary": ("poetry", "poem", "complete"),
        "complete-arbitrary": ("poetry", "poem", "complete"),
        "stanza-excerpt": ("poetry", "stanza", "excerpt"),
        "line-excerpt": ("poetry", "line", "excerpt"),
        "missing-poem-coverage": ("poetry", "poem", "unknown"),
        "inactive-metadata-control": ("metadata", "metadata", "complete"),
    }:
        raise ValueError("Scope or coverage ablation geometry drifted")
    predecessor = predecessor_fixtures()
    complete = cases[0]
    if complete["fixture_origin"] != "new_public_synthetic" or complete["source_fixture_id"] != "new-v1-complete-necessary" or complete["lineage_expected"] is not None or "\nin the\nblue light—" not in complete["text"] or "\n\nWhen doors close," not in complete["text"]:
        raise ValueError("Necessary reflow-dependent carrier drifted")
    arbitrary = next(case for case in cases if case["case_id"] == "complete-arbitrary")
    if arbitrary["fixture_origin"] != "predecessor_exact" or arbitrary["source_fixture_id"] != "artifact-03.txt" or arbitrary["text"] != predecessor["artifact-03.txt"]["text"] or arbitrary["lineage_expected"] != predecessor["artifact-03.txt"]["expected"] or tuple(arbitrary["expected"]) != ("NO", "YES"):
        raise ValueError("Arbitrary-lineation predecessor correction drifted")
    stanza = next(case for case in cases if case["case_id"] == "stanza-excerpt")
    if stanza["fixture_origin"] != "same_package_extract" or stanza["source_fixture_id"] != "new-v1-complete-necessary#lines-1-5" or stanza["text"] != "\n".join(complete["text"].splitlines()[:5]) or tuple(stanza["expected"]) != ("YES", "NOT_APPLICABLE"):
        raise ValueError("Stanza extraction or scope control drifted")
    line = next(case for case in cases if case["case_id"] == "line-excerpt")
    if line["fixture_origin"] != "predecessor_extract" or line["source_fixture_id"] != "artifact-01.txt#line-3" or line["text"] != predecessor["artifact-01.txt"]["text"].splitlines()[2]:
        raise ValueError("Predecessor line extraction drifted")
    for case_id, artifact_name in (("missing-poem-coverage", "artifact-05.txt"), ("inactive-metadata-control", "artifact-06.txt")):
        case = next(item for item in cases if item["case_id"] == case_id)
        if case["fixture_origin"] != "predecessor_exact" or case["source_fixture_id"] != artifact_name or case["text"] != predecessor[artifact_name]["text"] or case["lineage_expected"] != predecessor[artifact_name]["expected"]:
            raise ValueError("Predecessor exact fixture lineage drifted")


def verify_bindings(contract: Mapping[str, Any]) -> None:
    bindings = contract["bindings"]
    if bindings["pinned_commit"] != PINNED_COMMIT:
        raise ValueError("Pinned CWR parent drifted")
    pinned = subprocess.run(["git", "rev-parse", f"{PINNED_COMMIT}^{{commit}}"], cwd=REPOSITORY, text=True, capture_output=True, check=False)
    if pinned.returncode != 0 or pinned.stdout.strip() != PINNED_COMMIT:
        raise ValueError("Pinned CWR parent is unavailable")
    if bindings["corpus"] != {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")}:
        raise ValueError("Public synthetic corpus binding drifted")
    bound_paths = (*RUNTIME_PATHS, bindings["source_fixture"]["path"])
    verify_bound_paths_unchanged(bound_paths)
    source_path = REPOSITORY / bindings["source_fixture"]["path"]
    frozen_source = git_show_bytes(bindings["source_fixture"]["path"])
    if not source_path.is_file() or hashlib.sha256(frozen_source).hexdigest() != bindings["source_fixture"]["git_object_sha256"] or bindings["source_fixture"]["finding_id"] != FINDING_ID:
        raise ValueError("Original public fixture provenance drifted")
    for path, expected_hash in bindings["runtime"].items():
        frozen_bytes = git_show_bytes(path)
        current_path = REPOSITORY / path
        if path not in RUNTIME_PATHS or not current_path.is_file() or hashlib.sha256(frozen_bytes).hexdigest() != expected_hash:
            raise ValueError("Pinned current runtime binding drifted")
    if set(bindings["runtime"]) != set(RUNTIME_PATHS):
        raise ValueError("Pinned runtime surface drifted")
    if bindings["source_leaves"] != source_leaf_hashes():
        raise ValueError("Pinned canonical leaf binding drifted")
    ownership = load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    records = source_leaf_records()
    expected = {leaf: {"module_id": records[leaf]["module_id"], "question_id": leaf} for leaf in LEAVES}
    if {leaf: ownership.get(leaf) for leaf in LEAVES} != expected:
        raise ValueError("Criterion ownership invariant drifted")
    portfolio = contract["portfolio_binding"]
    manifest_path = REPOSITORY / portfolio["manifest_path"]
    if sha256_file(manifest_path) != portfolio["manifest_sha256"]:
        raise ValueError("Frozen first-remedy portfolio binding drifted")
    package = next((item for item in load_json(manifest_path)["packages"] if item["package_id"] == portfolio["package_id"]), None)
    if package is None or FINDING_ID not in package["finding_ids"] or package["initial_calls_exact"] != portfolio["frozen_initial_slots_exact"] or portfolio["additive_to_portfolio"] is not False:
        raise ValueError("First-remedy portfolio membership or non-additivity drifted")


def materialize_artifacts(corpus: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    corpus = load_corpus() if corpus is None else corpus
    return {case["case_id"]: deepcopy(case) for case in corpus["cases"]}


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for case in load_corpus()["cases"]:
        for leaf_id, verdict in zip(LEAVES, case["expected"], strict=True):
            for repeat in range(1, 4):
                slots.append({"slot_id": f"necessity-scope-v1-{len(slots) + 1:03d}", "case_id": case["case_id"], "leaf_id": leaf_id, "repeat": repeat, "expected_verdict": verdict})
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "portfolio_binding", "geometry", "labels", "screen", "scope_rule", "scoring", "promotion", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_provider_free_paired_scope_evidence_ablation" or contract["development_only"] is not True:
        raise ValueError("Contract identity or status drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "paid_route": "forbidden", "one_leaf_per_request": True} or contract["geometry"] != {"conditions_exact": 6, "leaves_per_condition_exact": 2, "repeats_exact": 3, "slots_exact": 36, "complete_poem_applicable_distinctions_minimum": 1} or contract["labels"] != ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]:
        raise ValueError("Provider, geometry, or label contract drifted")
    if contract["screen"] != {"name": "current_wording", "prompt_policy": "unchanged_production_prompt", "prompt_paths": ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md"], "schema_path": "schema/hbq_judge_response.schema.json", "renderer": "src/hbqrs/runner.py:_render_prompt", "expected_labels_provider_facing": False}:
        raise ValueError("Production prompt/schema/renderer contract drifted")
    if contract["scope_rule"] != {"study_mode": "direct_paired_leaf_overlay", "ordinary_bundle_activation_claimed": False, "compiled_pair_claimed": False, "projection": "question_index_direct_projection_with_explicit_module_domain_role_and_applies_when", "scope_overlay_control": "stanza_and_line_are_expected_not_applicable_for_scope.poetry_poem.form", "coverage_control": "declared_poem_with_missing_text_is_expected_cannot_assess_for_both_leaves"}:
        raise ValueError("Scope ablation contract drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "merge", "weight")}:
        raise ValueError("Promotion boundary drifted")
    verify_corpus(load_corpus())
    verify_bindings(contract)
    slots = plan_slots()
    expected_schedule = {(case_id, leaf_id, repeat) for case_id in EXPECTED for leaf_id in LEAVES for repeat in range(1, 4)}
    actual_schedule = {(slot["case_id"], slot["leaf_id"], slot["repeat"]) for slot in slots}
    complete_distinctions = sum(1 for case in load_corpus()["cases"] if case["declared_scope"] == "poem" and case["completion_status"] == "complete" and case["expected"][0] != case["expected"][1])
    if len(slots) != 36 or len({slot["slot_id"] for slot in slots}) != 36 or any(slot["leaf_id"] not in LEAVES for slot in slots) or {slot["expected_verdict"] for slot in slots} != VERDICTS or actual_schedule != expected_schedule or complete_distinctions < contract["geometry"]["complete_poem_applicable_distinctions_minimum"]:
        raise ValueError("One-leaf slot ledger drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "conditions": 6, "slots": 36}


def production_question(leaf_id: str) -> dict[str, Any]:
    record = source_leaf_records()[leaf_id]
    projection = DIRECT_PROJECTION[leaf_id]
    return {"question": deepcopy(record), "module_id": record["module_id"], "domain_id": projection["domain_id"], "role": projection["role"]}


def task_context_for(artifact: Mapping[str, Any]) -> dict[str, Any]:
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": artifact["artifact_type"], "declared_scope": artifact["declared_scope"], "completion_status": artifact["completion_status"], "background": "Public synthetic scope-and-evidence ablation.", "constraints": [{"id": "carrier", "statement": "Use only the supplied artifact at its declared scope."}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def provider_request(slot_id: str) -> dict[str, Any]:
    slot = next((item for item in plan_slots() if item["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown slot")
    artifact = materialize_artifacts()[slot["case_id"]]
    binary_prompt = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    prompt = production_runner._render_prompt(binary_prompt=binary_prompt, artifact={"name": artifact["artifact_name"], "text": artifact["text"]}, contexts=[], bundle_id="poetry.free_verse", artifact_id="public-synthetic-artifact", questions=[production_question(slot["leaf_id"])], task_contract_context=task_context_for(artifact))
    for forbidden in (slot_id, FINDING_ID, "expected_verdict", "source_fixture_id", "oracle"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local ledger metadata")
    return {"prompt": prompt, "leaf_id": slot["leaf_id"]}


def render_all_provider_inputs() -> dict[str, dict[str, Any]]:
    inputs = {slot["slot_id"]: provider_request(slot["slot_id"]) for slot in plan_slots()}
    if len(inputs) != 36:
        raise ValueError("All singleton inputs were not rendered")
    return inputs
