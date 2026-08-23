"""Provider-free freeze verifier for figurative domain compatibility v1."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as production_runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-figurative-domain-compatibility-v1"
P1_APPENDIX = """**Applicability and evidence-sufficiency rules**
Decide applicability before evidence sufficiency. Return `NOT_APPLICABLE` when the selected criterion does not govern the declared artifact, scope, or operation. This remains `NOT_APPLICABLE` even if evidence for a hypothetical in-scope artifact is absent. Return `CANNOT_ASSESS` only when the criterion does govern the declared artifact, scope, and operation but the evidence required to decide `YES` or `NO` is not supplied.

Apply the same evidence threshold to `YES` and `NO`. When a criterion compares an output with a requirement, source, active criterion list, baseline, or other reference, return `YES` or `NO` only when both the output and the comparison evidence are supplied. If either side is missing, return `CANNOT_ASSESS`. Do not infer an unstated requirement, and do not treat the absence of a shown violation as proof of `YES`."""
LEAF_AID = """For this leaf only, check the material metaphors and images and the source-domain implications each applies to its target. Ignore familiarity, sheer quantity, lyrical intensity, and ornament. Return YES when those implications can coexist and jointly clarify the subject; return NO when incompatible source-domain commitments make the intended perception unstable or make the figures compete. Judge only the declared evaluated scope."""
TARGET = "penalty.purple_prose.metaphor"
CONTROLS = ("core.freshness_and_non_genericness.no_default_metaphors", "penalty.purple_prose.proportion")
LEAVES = (TARGET, *CONTROLS)
ARMS = ("p1_appendix_only", "p1_appendix_plus_leaf_aid")
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json", "registry/question_index.jsonl",
    "registry/criterion_ownership.json", "registry/modules/penalty.purple_prose.yaml",
    "registry/modules/core.freshness_and_non_genericness.yaml", "src/hbqrs/runner.py",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def load_labels() -> dict[str, Any]:
    return load_json(ROOT / "expected-verdict-ledger.json")


def source_leaf_records() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry/question_index.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("id") in LEAVES:
            rows[record["id"]] = {key: record[key] for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")}
    if set(rows) != set(LEAVES) or any(row["pass_answer"] != "YES" for row in rows.values()):
        raise ValueError("Canonical figurative leaf records drifted")
    return rows


def runtime_hashes() -> dict[str, str]:
    return {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(row)).hexdigest() for leaf, row in source_leaf_records().items()}


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "fixtures"} or corpus.get("format_version") != 1 or corpus.get("study_id") != STUDY_ID or corpus.get("privacy") != "public_synthetic_only":
        raise ValueError("Public corpus identity drifted")
    fixtures = corpus.get("fixtures")
    required = {"case_id", "domain_relation", "stockness", "material_load", "figure_count", "text"}
    if not isinstance(fixtures, list) or len(fixtures) != 8 or any(set(row) != required for row in fixtures):
        raise ValueError("Public corpus geometry drifted")
    coordinates: set[tuple[str, str, str]] = set()
    for row in fixtures:
        coordinate = (row["domain_relation"], row["stockness"], row["material_load"])
        if coordinate in coordinates or coordinate[0] not in {"cooperate", "compete"} or coordinate[1] not in {"default", "specific"} or coordinate[2] not in {"routine", "charged"}:
            raise ValueError("Public corpus factor grid drifted")
        coordinates.add(coordinate)
        if not isinstance(row["case_id"], str) or not row["case_id"].startswith("dev-") or not isinstance(row["text"], str) or not row["text"].strip() or row["figure_count"] != 2:
            raise ValueError("Public fixture content drifted")
        expected = load_labels()["expected_verdicts"].get(row["case_id"])
        if set(expected) != set(LEAVES) or set(expected.values()) - {"YES", "NO"}:
            raise ValueError("Public expected verdict surface drifted")
        if expected[TARGET] != ("YES" if row["domain_relation"] == "cooperate" else "NO") or expected[CONTROLS[0]] != ("YES" if row["stockness"] == "specific" else "NO") or expected[CONTROLS[1]] != ("YES" if row["material_load"] == "routine" else "NO"):
            raise ValueError("Orthogonal construction oracle drifted")
    labels = load_labels()
    if set(labels) != {"format_version", "study_id", "visibility", "expected_verdicts"} or labels.get("format_version") != 1 or labels.get("study_id") != STUDY_ID or labels.get("visibility") != "local_ledger_only_not_provider_input" or set(labels["expected_verdicts"]) != {row["case_id"] for row in fixtures}:
        raise ValueError("Expected-label ledger drifted")
    if len(coordinates) != 8:
        raise ValueError("Public corpus is not a complete 2x2x2 grid")


def holdout_commitment(private_holdout_root: Path | None) -> str:
    if private_holdout_root is None:
        raise ValueError("A sealed private holdout root is required for verification")
    path = private_holdout_root / "holdout-commitment.json"
    if not path.is_file():
        raise ValueError("Sealed private holdout commitment is unavailable")
    return sha256_file(path)


def expected_public_bindings() -> dict[str, Any]:
    return {
        "public_corpus_sha256": sha256_file(ROOT / "public-synthetic-corpus.json"),
        "expected_label_ledger_sha256": sha256_file(ROOT / "expected-verdict-ledger.json"),
        "p1_appendix_sha256": sha256_text(P1_APPENDIX),
        "leaf_specific_aid_sha256": sha256_text(LEAF_AID),
        "runtime": runtime_hashes(),
        "source_leaves": source_leaf_hashes(),
    }


def expected_bindings(private_holdout_root: Path | None) -> dict[str, Any]:
    return {**expected_public_bindings(), "sealed_holdout_commitment_sha256": holdout_commitment(private_holdout_root)}


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for arm in ARMS:
        for fixture in load_corpus()["fixtures"]:
            for leaf in LEAVES:
                for repeat in range(1, 4):
                    slots.append({"slot_id": f"fdc-v1-{arm}-{fixture['case_id']}-{leaf.rsplit('.', 1)[-1]}-r{repeat}", "arm": arm, "case_id": fixture["case_id"], "leaf_id": leaf, "repeat": repeat, "expected_verdict": load_labels()["expected_verdicts"][fixture["case_id"]][leaf], "fixture_sha256": hashlib.sha256(canonical_bytes(fixture)).hexdigest()})
    return slots


def production_question(leaf_id: str) -> dict[str, Any]:
    row = source_leaf_records().get(leaf_id)
    if row is None:
        raise ValueError("Unknown frozen leaf")
    return {"module_id": row["module_id"], "domain_id": row["module_id"], "role": "primary", "question": {"id": leaf_id, "text": row["text"], "question_type": row["question_type"], "applies_when": row["applies_when"], "evidence_policy": row["evidence_policy"]}}


def render_provider_prompt(slot_id: str) -> str:
    slot = next((row for row in plan_slots() if row["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown frozen slot")
    fixture = next(row for row in load_corpus()["fixtures"] if row["case_id"] == slot["case_id"])
    base = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    appendix = P1_APPENDIX + ("\n\n" + LEAF_AID if slot["arm"] == "p1_appendix_plus_leaf_aid" and slot["leaf_id"] == TARGET else "")
    prompt = production_runner._render_prompt(binary_prompt=f"{base}\n\n{appendix}", artifact={"name": "public-synthetic-fixture.txt", "text": fixture["text"]}, contexts=[], bundle_id="figurative-domain-compatibility-development", artifact_id="public-synthetic-fixture", questions=[production_question(slot["leaf_id"])], task_contract_context={"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": "prose.short_story", "declared_scope": "complete supplied passage", "completion_status": "complete", "background": "Public synthetic development screen for prompt-only figurative validation.", "constraints": [], "audience": "development-only rubric validation", "preferences": [], "priorities": []})
    for forbidden in (slot_id, slot["case_id"], "expected_verdicts", "local_ledger_only_not_provider_input", "oracle", "holdout", "domain_relation", "stockness", "material_load"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local metadata")
    if slot["leaf_id"] != TARGET and LEAF_AID in prompt:
        raise ValueError("Leaf-specific aid leaked into a control prompt")
    return prompt


def render_all_provider_prompts() -> dict[str, str]:
    prompts = {slot["slot_id"]: render_provider_prompt(slot["slot_id"]) for slot in plan_slots()}
    if len(prompts) != 144:
        raise ValueError("Frozen slot plan drifted")
    return prompts


def verify_contract_structure() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "leaves", "screen", "stop_gate", "promotion", "bindings"}
    if set(contract) != required or contract.get("format_version") != 1 or contract.get("study_id") != STUDY_ID or contract.get("status") != "frozen_development_and_sealed_holdout_preexecution" or contract.get("development_only") is not True:
        raise ValueError("Frozen package identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True} or contract["geometry"] != {"public_fixtures_exact": 8, "dimensions": ["domain_relation", "stockness", "material_load"], "material_figures_per_fixture_exact": 2, "arms": list(ARMS), "leaves_exact": 3, "repeats_exact": 3, "slots_exact": 144} or contract["leaves"] != {"target": TARGET, "controls": list(CONTROLS)}:
        raise ValueError("Frozen package geometry drifted")
    if contract["screen"] != {"expected_label_visibility": "ledger_only", "ledger_expected_label_drives_or_renders_prompt": False, "semantic_fixture_evidence_may_determine_truth_state": True, "holdout_execution_gate": "p1_same_fixture_ab_holdout_passed", "development_settlement_precondition": "private_holdout_frozen_before_execution"}:
        raise ValueError("Frozen package screen boundary drifted")
    if contract["stop_gate"] != {"treatment_target": "24_of_24", "treatment_controls": "48_of_48", "improvement": "at_least_two_differently_worded_competing_domain_cells_across_strata", "compatible_regression": "zero", "both_arms_perfect": "NO_GO", "target_miss": "NO_GO", "wrong_factor_control_dependence": "NO_GO", "single_fixture_gain": "NO_GO"} or contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Frozen package gate drifted")
    return contract


def verify_package(private_holdout_root: Path | None = None) -> dict[str, Any]:
    contract = verify_contract_structure()
    verify_corpus(load_corpus())
    if contract["bindings"] != expected_bindings(private_holdout_root):
        raise ValueError("Frozen package binding drifted")
    slots = plan_slots()
    if len(slots) != 144 or len({slot["slot_id"] for slot in slots}) != 144:
        raise ValueError("Frozen slot plan drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "public_fixtures": 8, "slots": 144, "sealed_holdout_frozen": True}


def verify_public_package() -> dict[str, Any]:
    """Validate public structure without opening a sealed private holdout."""
    contract = verify_contract_structure()
    verify_corpus(load_corpus())
    bindings = dict(contract.get("bindings", {}))
    sealed_commitment = bindings.pop("sealed_holdout_commitment_sha256", None)
    expected = expected_public_bindings()
    if bindings != expected or not isinstance(sealed_commitment, str) or len(sealed_commitment) != 64 or set(sealed_commitment) - set("0123456789abcdef"):
        raise ValueError("Public package binding drifted")
    return {"study_id": STUDY_ID, "provider_calls": 0, "public_fixtures": 8, "slots": 144, "sealed_holdout_content_opened": False}
