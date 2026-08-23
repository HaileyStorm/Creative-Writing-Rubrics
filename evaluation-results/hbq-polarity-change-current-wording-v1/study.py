"""Provider-free verifier and singleton prompt planner for the P1 wording screen."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner as production_runner

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-polarity-change-current-wording-v1"
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
VERDICTS = ("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS")
FINDINGS = (
    "cd890d802fe78388cbbe684615894473dffda2b5b1eab8b3ae6ca6acfa806e26",
    "8e14f58a8faf4f80734ef6b10fa18bbdfce3c8e58cdf1823f54314c70638db65",
    "c7ee0bdfcaf98db40d37f38f4de67d66dd709f56db748df0a83ffba39f979cf2",
    "8a6326c8c665cccf14c2f931a4acde9ebc1117211e6cec1454829dc4dd507afe",
    "82d1e80a0970c07c6c4b8a6340aed3744a5182fddf8793863e93ca315875c14d",
    "11d98b6de654dd40e64af4e784061fb6ef59d57e9bd0f866407efa9ae52964db",
    "e6e5ad3862be84811980db705f4dd6e5ac29533f3d049c78db47df4d51e82b28",
    "dd6f1489415df0938adf2d8388d07bfe95363f45d9500850d086651493ef9b6d",
    "bb38fcb28b25e66341d4e56065fbb6f5476bf07c4afb5990002fe20bde0472ae",
    "3f93b906a04f9c76134f1f91dbf1c895023afa548035dfe1afea8cbb21017d34",
    "d0e5d4aa61643ec9b73e240f9fa93ce47711fca5473becb2f4f8788695fab354",
)
SCORING = {
    "yes_no": "requires_3_of_3_grounded_typed_evidence_matches",
    "not_applicable": "completed_unscored",
    "cannot_assess": "coverage_uncertainty",
    "missing_or_ambiguous_slot": "INCOMPLETE",
}
FINDING_SUBJECTS = dict(zip(FINDINGS, LEAVES, strict=True))
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


def load_findings_ledger() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FINDINGS_PATH.read_text(encoding="utf-8").splitlines() if line]


def source_leaf_records() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry/question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") in LEAVES:
            records[row["id"]] = {
                key: row[key]
                for key in ("module_id", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")
            }
    if set(records) != set(LEAVES):
        raise ValueError("Canonical P1 leaf order or records drifted")
    records = {leaf: records[leaf] for leaf in LEAVES}
    if any(row["pass_answer"] != "YES" for row in records.values()):
        raise ValueError("P1 pass-answer orientation drifted")
    return records


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(record)).hexdigest() for leaf, record in source_leaf_records().items()}


def runtime_hashes() -> dict[str, str]:
    paths = [
        "prompts/judge/JUDGE_PREFIX.md",
        "prompts/judge/BINARY_EVALUATION_PROMPT.md",
        "schema/hbq_judge_response.schema.json",
        "registry/question_index.jsonl",
        "src/hbqrs/runner.py",
    ]
    paths.extend(f"registry/modules/{row['module_id']}.yaml" for row in source_leaf_records().values())
    return {path: sha256_file(REPOSITORY / path) for path in paths}


def verify_audit_membership() -> None:
    portfolio = load_json(PORTFOLIO_PATH)
    p1 = [package for package in portfolio.get("packages", []) if package.get("package_id") == "P1"]
    if len(p1) != 1 or p1[0].get("finding_ids") != list(FINDINGS) or p1[0].get("finding_count_exact") != 11 or p1[0].get("initial_calls_exact") != 132:
        raise ValueError("P1 portfolio membership drifted")
    records = {record.get("finding_id"): record for record in load_findings_ledger()}
    if len(records) != len(load_findings_ledger()):
        raise ValueError("Findings ledger identity drifted")
    observed = {finding: tuple(records.get(finding, {}).get("subjects", ())) for finding in FINDINGS}
    if observed != {finding: (leaf,) for finding, leaf in FINDING_SUBJECTS.items()}:
        raise ValueError("P1 audit finding-to-subject mapping drifted")
    if any(records[finding].get("kind") != "polarity_change" for finding in FINDINGS):
        raise ValueError("P1 audit finding kind drifted")


def verify_criterion_ownership() -> None:
    ownership = load_json(OWNERSHIP_PATH)
    expected = {
        leaf: {"module_id": source_leaf_records()[leaf]["module_id"], "question_id": leaf}
        for leaf in LEAVES
    }
    if {leaf: ownership.get(leaf) for leaf in LEAVES} != expected:
        raise ValueError("P1 criterion ownership drifted")


def plan_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    for fixture in load_corpus()["fixtures"]:
        for repeat in range(1, 4):
            slots.append({
                "slot_id": f"p1-v1-{fixture['case_id']}-r{repeat}",
                "case_id": fixture["case_id"],
                "leaf_id": fixture["leaf_id"],
                "repeat": repeat,
                "expected_verdict": fixture["state"],
                "fixture_sha256": hashlib.sha256(canonical_bytes(fixture)).hexdigest(),
            })
    return slots


def verify_corpus(corpus: Mapping[str, Any]) -> None:
    if set(corpus) != {"format_version", "study_id", "privacy", "fixtures"} or corpus["format_version"] != 1 or corpus["study_id"] != STUDY_ID or corpus["privacy"] != "public_synthetic_only":
        raise ValueError("Corpus identity drifted")
    fixtures = corpus["fixtures"]
    required = {"case_id", "leaf_id", "state", "artifact_kind", "text"}
    if not isinstance(fixtures, list) or len(fixtures) != 44:
        raise ValueError("P1 fixture count drifted")
    seen: set[str] = set()
    by_leaf: dict[str, list[Mapping[str, Any]]] = {leaf: [] for leaf in LEAVES}
    for fixture in fixtures:
        if set(fixture) != required or not isinstance(fixture["case_id"], str) or fixture["case_id"] in seen:
            raise ValueError("Fixture identity drifted")
        if fixture["leaf_id"] not in by_leaf or fixture["state"] not in VERDICTS or not isinstance(fixture["artifact_kind"], str) or not isinstance(fixture["text"], str) or not fixture["text"].strip():
            raise ValueError("Fixture content drifted")
        seen.add(fixture["case_id"])
        by_leaf[fixture["leaf_id"]].append(fixture)
    for leaf, cases in by_leaf.items():
        if {case["state"] for case in cases} != set(VERDICTS) or len(cases) != 4:
            raise ValueError(f"Four-state fixture coverage drifted for {leaf}")
        if any(leaf not in case["case_id"] and case["case_id"].count("-") < 1 for case in cases):
            raise ValueError("Fixture case identity is malformed")


def verify_package() -> dict[str, Any]:
    contract = load_contract()
    expected = {
        "format_version", "study_id", "status", "development_only", "provider_execution", "geometry", "screen", "scoring", "promotion", "bindings",
    }
    if set(contract) != expected or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_development_only_current_wording_screen" or contract["development_only"] is not True:
        raise ValueError("Contract identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}:
        raise ValueError("Provider-free boundary drifted")
    if contract["geometry"] != {"leaves_exact": 11, "fixture_states": list(VERDICTS), "fixtures_exact": 44, "repeats_exact": 3, "slots_exact": 132}:
        raise ValueError("P1 geometry drifted")
    if contract["screen"] != {"name": "current_wording", "prompt_policy": "unchanged_production_prompt", "treatment_arm": "absent", "expected_label_visibility": "ledger_only"} or contract["scoring"] != SCORING or contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Current-wording boundary drifted")
    verify_corpus(load_corpus())
    expected_bindings = {
        "corpus": {"path": "public-synthetic-corpus.json", "sha256": sha256_file(ROOT / "public-synthetic-corpus.json")},
        "runtime": runtime_hashes(),
        "source_leaves": source_leaf_hashes(),
        "portfolio_manifest": {"path": "evaluation-results/hbq-first-remedy-portfolio-v1/manifest.json", "sha256": sha256_file(PORTFOLIO_PATH)},
        "findings_ledger": {"path": "evaluation-results/hbq-full-leaf-structural-audit-v1/findings.jsonl", "sha256": sha256_file(FINDINGS_PATH)},
        "criterion_ownership": {"path": "registry/criterion_ownership.json", "sha256": sha256_file(OWNERSHIP_PATH)},
    }
    if contract["bindings"] != expected_bindings:
        raise ValueError("Frozen package bindings drifted")
    verify_audit_membership()
    verify_criterion_ownership()
    slots = plan_slots()
    if len(slots) != 132 or len({slot["slot_id"] for slot in slots}) != 132:
        raise ValueError("P1 slot plan drifted")
    return {"study_id": STUDY_ID, "status": contract["status"], "provider_calls": 0, "leaves": 11, "fixtures": 44, "slots": 132, "current_wording_bound": True}


def production_question(leaf_id: str) -> dict[str, Any]:
    row = source_leaf_records().get(leaf_id)
    if row is None:
        raise ValueError("Unknown P1 leaf")
    return {
        "module_id": row["module_id"],
        "domain_id": row["module_id"],
        "role": "primary",
        "question": {
            "id": leaf_id,
            "text": row["text"],
            "question_type": row["question_type"],
            "applies_when": row["applies_when"],
            "evidence_policy": row["evidence_policy"],
        },
    }


def task_context_for(fixture: Mapping[str, Any]) -> dict[str, Any]:
    scope = "out_of_scope" if fixture["state"] == "NOT_APPLICABLE" else "current_artifact"
    availability = "unavailable" if fixture["state"] == "CANNOT_ASSESS" else "supplied"
    return {
        "context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION,
        "untrusted_evaluation_data": True,
        "artifact_kind": fixture["artifact_kind"],
        "declared_scope": scope,
        "completion_status": "complete",
        "background": "Public synthetic development screen for current rubric wording.",
        "constraints": [{"id": "evidence_availability", "statement": f"relevant_evidence={availability}"}],
        "audience": "development-only rubric validation",
        "preferences": [],
        "priorities": [],
    }


def render_provider_prompt(slot_id: str) -> str:
    slot = next((item for item in plan_slots() if item["slot_id"] == slot_id), None)
    if slot is None:
        raise ValueError("Unknown P1 slot")
    fixture = next(item for item in load_corpus()["fixtures"] if item["case_id"] == slot["case_id"])
    binary_prompt = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    prompt = production_runner._render_prompt(
        binary_prompt=binary_prompt,
        artifact={"name": "public-synthetic-fixture.txt", "text": fixture["text"]},
        contexts=[],
        bundle_id="p1-current-wording-development",
        artifact_id="public-synthetic-fixture",
        questions=[production_question(slot["leaf_id"])],
        task_contract_context=task_context_for(fixture),
    )
    for forbidden in (slot_id, slot["case_id"], "expected_verdict", "oracle"):
        if forbidden in prompt:
            raise ValueError("Provider-facing prompt leaked ledger metadata")
    return prompt


def render_all_provider_prompts() -> dict[str, str]:
    rendered = {slot["slot_id"]: render_provider_prompt(slot["slot_id"]) for slot in plan_slots()}
    if len(rendered) != 132:
        raise ValueError("All singleton P1 prompts were not rendered")
    return rendered
