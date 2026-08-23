"""Provider-free freeze verifier and planner for the P1 manual treatment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as production_runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-polarity-change-manual-treatment-v1"
PREDECESSOR_ROOT = REPOSITORY / "evaluation-results" / "hbq-polarity-change-current-wording-v1"
LEAVES = (
    "form.audio.audio_drama_production.no_as_you_know",
    "form.multimodal.text_audio_alignment.no_narrow",
    "form.poetry.general_poetry.oral_test",
    "form.poetry.haiku_in_english.kigo_legible",
    "form.poetry.lyric_song_lyric.no_filler",
    "form.poetry.spoken_word_performance_poetry.page_independence",
    "form.visual.visual_prompt_and_canon_fidelity.subjects",
    "op.critique.rubric_directed_critique.criteria",
    "op.ingest.source_ingestion_fidelity.no_invention",
    "op.ingest.source_ingestion_fidelity.no_omission",
    "sampler.freshness_gain.no_ornate_proxy",
)
TREATED_LEAVES = (
    "form.poetry.general_poetry.oral_test",
    "form.visual.visual_prompt_and_canon_fidelity.subjects",
    "op.critique.rubric_directed_critique.criteria",
    "op.ingest.source_ingestion_fidelity.no_invention",
)
VERDICTS = ("YES", "NO", "NOT_APPLICABLE")
TREATMENT_APPENDIX = """**Applicability and evidence-sufficiency rules**
Decide applicability before evidence sufficiency. Return `NOT_APPLICABLE` when the selected criterion does not govern the declared artifact, scope, or operation. This remains `NOT_APPLICABLE` even if evidence for a hypothetical in-scope artifact is absent. Return `CANNOT_ASSESS` only when the criterion does govern the declared artifact, scope, and operation but the evidence required to decide `YES` or `NO` is not supplied.

Apply the same evidence threshold to `YES` and `NO`. When a criterion compares an output with a requirement, source, active criterion list, baseline, or other reference, return `YES` or `NO` only when both the output and the comparison evidence are supplied. If either side is missing, return `CANNOT_ASSESS`. Do not infer an unstated requirement, and do not treat the absence of a shown violation as proof of `YES`."""
SCORING = {
    "development_success": "all_19_cells_3_of_3_grounded_typed_evidence_matches",
    "not_applicable_controls": "completed_diagnostic_only",
    "missing_or_ambiguous_slot": "INCOMPLETE",
    "development_pass_decision": "MANUAL_TREATMENT_PASS",
    "prompt_promotion": "holdout_and_independent_review_required",
}
MATCHED_PAIR_CARRIERS = {
    "poem-oral": {
        "reference": "DECLARED PERFORMANCE AIM: a calm, easily articulated lullaby cadence.",
        "output_prefix": "POEM: ",
    },
    "visual-subjects": {
        "reference": "SUBJECT SPECIFICATION: Required subjects: a red fox and a brass compass. Forbidden subject: a crown.",
        "output_prefix": "DEPICTED IMAGE RECORD: ",
    },
    "critique-criteria": {
        "reference": "ACTIVE CRITERIA: clarity; evidence.",
        "output_prefix": "CRITIQUE OUTPUT: ",
    },
    "ingest-invention": {
        "reference": "SOURCE RECORD: Nell waits at dawn.",
        "output_prefix": "INGESTED OUTPUT: ",
    },
}
PORTFOLIO_PATH = REPOSITORY / "evaluation-results" / "hbq-first-remedy-portfolio-v1" / "manifest.json"
FINDINGS_PATH = REPOSITORY / "evaluation-results" / "hbq-full-leaf-structural-audit-v1" / "findings.jsonl"
OWNERSHIP_PATH = REPOSITORY / "registry" / "criterion_ownership.json"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def load_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def load_predecessor_corpus() -> dict[str, Any]:
    return load_json(PREDECESSOR_ROOT / "public-synthetic-corpus.json")


def load_carriers() -> dict[str, Any]:
    return load_json(ROOT / "fixture-carriers.json")


def source_leaf_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry/question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in LEAVES:
            records[row["id"]] = {key: row[key] for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")}
    if set(records) != set(LEAVES) or any(record["pass_answer"] != "YES" for record in records.values()):
        raise ValueError("Canonical P1 leaf records drifted")
    return {leaf: records[leaf] for leaf in LEAVES}


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in source_leaf_records().items()}


def runtime_hashes() -> dict[str, str]:
    paths = ["prompts/judge/JUDGE_PREFIX.md", "prompts/judge/BINARY_EVALUATION_PROMPT.md", "schema/hbq_judge_response.schema.json", "registry/question_index.jsonl", "registry/criterion_ownership.json", "src/hbqrs/runner.py"]
    paths.extend(f"registry/modules/{row['module_id']}.yaml" for row in source_leaf_records().values())
    return {path: sha256_file(REPOSITORY / path) for path in paths}


def _fixtures_by_case(corpus: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    fixtures = corpus.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("Fixture list drifted")
    return {fixture.get("case_id"): fixture for fixture in fixtures if isinstance(fixture, Mapping)}


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "fixtures"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    fixtures = corpus["fixtures"]
    required = {"case_id", "leaf_id", "state", "artifact_kind", "text"}
    if not isinstance(fixtures, list) or len(fixtures) != 19:
        raise ValueError("Manual-treatment fixture count drifted")
    cases = _fixtures_by_case(corpus)
    if len(cases) != 19 or any(set(fixture) != required for fixture in fixtures):
        raise ValueError("Manual-treatment fixture shape drifted")
    by_leaf: dict[str, list[Mapping[str, Any]]] = {leaf: [] for leaf in LEAVES}
    for fixture in fixtures:
        if fixture["leaf_id"] not in by_leaf or fixture["state"] not in VERDICTS or not isinstance(fixture["artifact_kind"], str) or not isinstance(fixture["text"], str) or not fixture["text"].strip():
            raise ValueError("Manual-treatment fixture content drifted")
        by_leaf[fixture["leaf_id"]].append(fixture)
    predecessor_cases = _fixtures_by_case(load_predecessor_corpus())
    expected_na_cases = {case_id for case_id, fixture in predecessor_cases.items() if fixture.get("state") == "NOT_APPLICABLE"}
    observed_na_cases = {fixture["case_id"] for fixture in fixtures if fixture["state"] == "NOT_APPLICABLE"}
    if observed_na_cases != expected_na_cases or len(observed_na_cases) != 11:
        raise ValueError("Unchanged NOT_APPLICABLE control set drifted")
    for case_id in expected_na_cases:
        if cases[case_id] != predecessor_cases[case_id]:
            raise ValueError("NOT_APPLICABLE fixture bytes drifted from predecessor")
    for leaf in LEAVES:
        leaf_cases = by_leaf[leaf]
        states = {fixture["state"] for fixture in leaf_cases}
        if leaf in TREATED_LEAVES:
            if states != {"YES", "NO", "NOT_APPLICABLE"} or len(leaf_cases) != 3:
                raise ValueError("Treated leaf fixture matrix drifted")
        elif states != {"NOT_APPLICABLE"} or len(leaf_cases) != 1:
            raise ValueError("Untreated leaf control matrix drifted")
    for prefix, leaf in (("poem-oral", TREATED_LEAVES[0]), ("visual-subjects", TREATED_LEAVES[1]), ("critique-criteria", TREATED_LEAVES[2]), ("ingest-invention", TREATED_LEAVES[3])):
        yes, no = cases[f"{prefix}-yes"], cases[f"{prefix}-no"]
        if yes["leaf_id"] != leaf or no["leaf_id"] != leaf or yes["artifact_kind"] != no["artifact_kind"]:
            raise ValueError("Matched treatment pair identity drifted")
        carrier = MATCHED_PAIR_CARRIERS[prefix]
        expected_prefix = f"{carrier['reference']}\n{carrier['output_prefix']}"
        if not yes["text"].startswith(expected_prefix) or not no["text"].startswith(expected_prefix):
            raise ValueError("Matched comparison carrier drifted")
        yes_reference, yes_output = yes["text"].split("\n", maxsplit=1)
        no_reference, no_output = no["text"].split("\n", maxsplit=1)
        if yes_reference != carrier["reference"] or no_reference != carrier["reference"] or not yes_output.startswith(carrier["output_prefix"]) or not no_output.startswith(carrier["output_prefix"]) or yes_output == no_output:
            raise ValueError("Matched comparison carrier is not isolated from decisive output")


def verify_carriers(corpus: Mapping[str, Any]) -> None:
    carrier_document = load_carriers()
    expected_fields = ["declared_scope", "completion_status", "relevant_evidence"]
    if set(carrier_document) != {"format_version", "study_id", "carrier_fields", "carriers"} or carrier_document["format_version"] != 1 or carrier_document["study_id"] != STUDY_ID or carrier_document["carrier_fields"] != expected_fields:
        raise ValueError("Fixture carrier document drifted")
    cases = _fixtures_by_case(corpus)
    carriers = carrier_document["carriers"]
    if set(carriers) != set(cases) or any(set(carrier) != set(expected_fields) for carrier in carriers.values()):
        raise ValueError("Fixture carrier identity drifted")
    for case_id, fixture in cases.items():
        carrier = carriers[case_id]
        if not all(isinstance(carrier[field], str) and carrier[field] for field in expected_fields):
            raise ValueError("Fixture carrier content drifted")
        if fixture["state"] == "NOT_APPLICABLE" and carrier != {"declared_scope": "out_of_scope", "completion_status": "complete", "relevant_evidence": "supplied"}:
            raise ValueError("NOT_APPLICABLE carrier drifted")


def verify_holdout_contract(contract: Mapping[str, Any]) -> None:
    expected = {
        "format_version": 1, "study_id": STUDY_ID,
        "status": "sealed_private_holdout_contract_frozen_preexecution",
        "fixture_material": "sealed_private_not_in_public_package",
        "required_coverage": {"matched_not_applicable_cannot_assess_pairs": True, "symmetric_yes_no_comparison_carriers": ["visual", "critique", "ingest"], "unaffected_polarity_controls": True},
        "reveal_gate": "after_development_settlement_only",
        "promotion_gate": ["holdout_3_of_3_per_cell", "zero_regression", "deterministic_validation", "independent_sol_high_go", "zero_paid_gpt_5_6_execution"],
        "promotion": "none",
    }
    if dict(contract) != expected:
        raise ValueError("Sealed holdout contract drifted")


def verify_audit_membership() -> None:
    portfolio = load_json(PORTFOLIO_PATH)
    p1 = [package for package in portfolio.get("packages", []) if package.get("package_id") == "P1"]
    findings = [json.loads(line) for line in FINDINGS_PATH.read_text(encoding="utf-8").splitlines() if line]
    if len(p1) != 1 or p1[0].get("finding_count_exact") != 11 or p1[0].get("initial_calls_exact") != 132 or any(row.get("kind") != "polarity_change" for row in findings if row.get("finding_id") in p1[0].get("finding_ids", [])):
        raise ValueError("P1 audit binding drifted")


def verify_bindings(contract: Mapping[str, Any]) -> None:
    expected = {
        "corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")},
        "fixture_carriers": {"path": "fixture-carriers.json", "sha256": sha256_file(ROOT / "fixture-carriers.json")},
        "sealed_holdout_contract": {"path": "sealed-holdout-contract.json", "sha256": sha256_file(ROOT / "sealed-holdout-contract.json")},
        "treatment_appendix_sha256": hashlib.sha256(TREATMENT_APPENDIX.encode("utf-8")).hexdigest(),
        "runtime": runtime_hashes(), "source_leaves": source_leaf_hashes(),
        "portfolio_manifest": {"path": "evaluation-results/hbq-first-remedy-portfolio-v1/manifest.json", "sha256": sha256_file(PORTFOLIO_PATH)},
        "findings_ledger": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/findings.jsonl", "sha256": sha256_file(FINDINGS_PATH)},
        "criterion_ownership": {"path": "registry/criterion_ownership.json", "sha256": sha256_file(OWNERSHIP_PATH)},
    }
    if contract["bindings"] != expected:
        raise ValueError("Frozen package bindings drifted")
    ownership = load_json(OWNERSHIP_PATH)
    expected_ownership = {leaf: {"module_id": source_leaf_records()[leaf]["module_id"], "question_id": leaf} for leaf in LEAVES}
    if {leaf: ownership.get(leaf) for leaf in LEAVES} != expected_ownership:
        raise ValueError("Criterion ownership drifted")
    verify_audit_membership()


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for fixture in load_corpus()["fixtures"]:
        for repeat in range(1, 4):
            slots.append({"slot_id": f"p1mt-v1-{fixture['case_id']}-r{repeat}", "case_id": fixture["case_id"], "leaf_id": fixture["leaf_id"], "repeat": repeat, "expected_verdict": fixture["state"], "fixture_sha256": hashlib.sha256(canonical_bytes(fixture)).hexdigest()})
    return slots


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "screen", "scoring", "promotion", "bindings"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_development_only_manual_treatment" or contract["development_only"] is not True:
        raise ValueError("Contract identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}:
        raise ValueError("Provider-free boundary drifted")
    if contract["geometry"] != {"leaves_exact": 11, "treated_leaves_exact": 4, "unchanged_not_applicable_controls_exact": 11, "corrected_yes_no_pairs_exact": 4, "fixtures_exact": 19, "repeats_exact": 3, "slots_exact": 57}:
        raise ValueError("Manual-treatment geometry drifted")
    if contract["screen"] != {"name": "manual_treatment", "prompt_policy": "append_exact_applicability_and_evidence_sufficiency_rules", "treatment_arm": "only", "expected_label_visibility": "ledger_only", "semantic_fixture_evidence_may_determine_truth_state": True, "ledger_expected_label_drives_or_renders_prompt": False, "sealed_holdout_required_before_execution": True} or contract["scoring"] != SCORING or contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Manual-treatment screen boundary drifted")
    corpus = load_corpus()
    verify_corpus(corpus)
    verify_carriers(corpus)
    verify_holdout_contract(load_json(ROOT / "sealed-holdout-contract.json"))
    verify_bindings(contract)
    slots = plan_slots()
    if len(slots) != 57 or len({slot["slot_id"] for slot in slots}) != 57 or {slot["repeat"] for slot in slots} != {1, 2, 3}:
        raise ValueError("Manual-treatment slot plan drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "fixtures": 19, "slots": 57, "sealed_holdout_contract": True}


def production_question(leaf_id: str) -> dict[str, Any]:
    row = source_leaf_records().get(leaf_id)
    if row is None:
        raise ValueError("Unknown P1 leaf")
    return {"module_id": row["module_id"], "domain_id": row["module_id"], "role": "primary", "question": {"id": leaf_id, "text": row["text"], "question_type": row["question_type"], "applies_when": row["applies_when"], "evidence_policy": row["evidence_policy"]}}


def task_context_for(fixture: Mapping[str, Any]) -> dict[str, Any]:
    case_id = fixture.get("case_id")
    carrier = load_carriers()["carriers"].get(case_id)
    if not isinstance(carrier, Mapping):
        raise ValueError("Fixture carrier is unavailable")
    return {"context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION, "untrusted_evaluation_data": True, "artifact_kind": fixture["artifact_kind"], "declared_scope": carrier["declared_scope"], "completion_status": carrier["completion_status"], "background": "Public synthetic development screen for manual prompt treatment.", "constraints": [{"id": "evidence_availability", "statement": f"relevant_evidence={carrier['relevant_evidence']}"}], "audience": "development-only rubric validation", "preferences": [], "priorities": []}


def render_provider_prompt(slot_id: str) -> str:
    slot = next((item for item in plan_slots() if item["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown P1 manual-treatment slot")
    fixture = next(item for item in load_corpus()["fixtures"] if item["case_id"] == slot["case_id"])
    base = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    prompt = production_runner._render_prompt(binary_prompt=f"{base}\n\n{TREATMENT_APPENDIX}", artifact={"name": "public-synthetic-fixture.txt", "text": fixture["text"]}, contexts=[], bundle_id="p1-manual-treatment-development", artifact_id="public-synthetic-fixture", questions=[production_question(slot["leaf_id"])], task_contract_context=task_context_for(fixture))
    for forbidden in (slot_id, slot["case_id"], "expected_verdict", "oracle", "sealed-holdout"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked local metadata")
    return prompt


def render_all_provider_prompts() -> dict[str, str]:
    prompts = {slot["slot_id"]: render_provider_prompt(slot["slot_id"]) for slot in plan_slots()}
    if len(prompts) != 57:
        raise ValueError("All singleton manual-treatment prompts were not rendered")
    return prompts
