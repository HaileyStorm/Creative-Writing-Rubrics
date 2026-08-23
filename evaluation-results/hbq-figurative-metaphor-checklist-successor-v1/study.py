"""Provider-free two-phase freeze for the figurative-metaphor checklist successor."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from hbqrs import runner as production_runner


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-figurative-domain-compatibility-v1"
STUDY_ID = "hbq-figurative-metaphor-checklist-successor-v1"
SOURCE_STUDY_ID = "hbq-figurative-domain-compatibility-v1"
TARGET = "penalty.purple_prose.metaphor"
CONTROLS = (
    "core.freshness_and_non_genericness.no_default_metaphors",
    "penalty.purple_prose.proportion",
)
LEAVES = (TARGET, *CONTROLS)
REPEATS = (1, 2, 3)
CANDIDATE_CHECKLIST = (
    "Inspect every material metaphor or image in the declared scope and compare what each implies "
    "about its subject. Return YES when the implications can coexist and jointly clarify the "
    "perception; return NO when stacking, mixing, or competing implications materially destabilize "
    "it at that scope. Do not judge familiarity/defaultness or sheer figurative load relative to "
    "content; cite the cooperating or conflicting spans."
)
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "registry/modules/penalty.purple_prose.yaml",
    "registry/modules/core.freshness_and_non_genericness.yaml",
    "src/hbqrs/runner.py",
)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def load_contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def source_corpus() -> dict[str, Any]:
    return load_json(ROOT / "public-synthetic-corpus.json")


def source_labels() -> dict[str, Any]:
    return load_json(ROOT / "expected-verdict-ledger.json")


def source_leaf_records() -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record.get("id") in LEAVES:
            rows[record["id"]] = {
                key: record[key]
                for key in (
                    "module_id", "text", "pass_answer", "weight", "question_type", "severity",
                    "applies_when", "evidence_policy",
                )
            }
    if set(rows) != set(LEAVES) or any(row["pass_answer"] != "YES" for row in rows.values()):
        raise ValueError("Canonical figurative leaf records drifted")
    return rows


def runtime_hashes() -> dict[str, str]:
    return {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS}


def source_leaf_hashes() -> dict[str, str]:
    return {leaf: hashlib.sha256(canonical_bytes(row)).hexdigest() for leaf, row in source_leaf_records().items()}


def expected_bindings() -> dict[str, Any]:
    return {
        "public_synthetic_corpus_sha256": sha256_file(ROOT / "public-synthetic-corpus.json"),
        "expected_label_ledger_sha256": sha256_file(ROOT / "expected-verdict-ledger.json"),
        "predecessor_public_corpus_sha256": sha256_file(PREDECESSOR_ROOT / "public-synthetic-corpus.json"),
        "real_holdout_commitment_sha256": sha256_file(ROOT / "real-holdout-commitment.json"),
        "candidate_checklist_sha256": sha256_text(CANDIDATE_CHECKLIST),
        "runtime": runtime_hashes(),
        "source_leaves": source_leaf_hashes(),
    }


def verify_source_corpus() -> None:
    corpus, labels = source_corpus(), source_labels()
    if corpus.get("format_version") != 2 or corpus.get("study_id") != STUDY_ID or corpus.get("privacy") != "public_synthetic_only" or corpus.get("fixture_design") != "v2_semantic_construction_actual_figurative_load":
        raise ValueError("Source synthetic corpus identity drifted")
    fixtures = corpus.get("fixtures")
    required = {"case_id", "text", "semantic_construction"}
    if not isinstance(fixtures, list) or len(fixtures) != 8 or any(set(row) != required for row in fixtures):
        raise ValueError("Source synthetic corpus geometry drifted")
    expected = labels.get("expected_verdicts")
    if labels.get("format_version") != 2 or labels.get("study_id") != STUDY_ID or labels.get("visibility") != "local_ledger_only_not_provider_input" or not isinstance(expected, Mapping):
        raise ValueError("Source expected-ledger identity drifted")
    semantic_cells: set[tuple[str, str, str]] = set()
    for fixture in fixtures:
        construction = fixture["semantic_construction"]
        if not isinstance(fixture["text"], str) or not isinstance(construction, Mapping) or set(construction) != {"target_subject", "figures", "reviewer_rationale"}:
            raise ValueError("Source fixture content drifted")
        figures = construction["figures"]
        if construction["target_subject"] != "the argument" or not isinstance(construction["reviewer_rationale"], str) or not construction["reviewer_rationale"].strip() or not isinstance(figures, list) or len(figures) not in {3, 7}:
            raise ValueError("Source semantic construction drifted")
        if any(set(figure) != {"role", "subject", "span", "source_domain", "relational_implication"} or not isinstance(figure["span"], str) or figure["span"] not in fixture["text"] for figure in figures):
            raise ValueError("Source figure span drifted")
        targets = [figure for figure in figures if figure["role"] == "target_pair"]
        probes = [figure for figure in figures if figure["role"] == "separate_probe"]
        extras = [figure for figure in figures if figure["role"] == "unrelated_extra"]
        if len(targets) != 2 or len(probes) != 1 or len(extras) != len(figures) - 3 or any(figure["subject"] != construction["target_subject"] for figure in targets) or any(figure["subject"] == construction["target_subject"] for figure in [*probes, *extras]) or len({figure["subject"] for figure in extras}) != len(extras):
            raise ValueError("Source figure subjects drifted")
        implications = tuple(figure["relational_implication"] for figure in targets)
        if implications == ("connects", "supports_connection") and all(figure["source_domain"] == "bridge construction" for figure in targets):
            target_expected = "YES"
        elif implications == ("connects", "isolates") and targets[0]["source_domain"] == "bridge construction" and targets[1]["source_domain"] == "sealed vault":
            target_expected = "NO"
        else:
            raise ValueError("Target relational implications drifted")
        probe_expected = {"beacon": "NO", "postage stamp": "YES"}.get(str(probes[0]["source_domain"]))
        if probe_expected is None:
            raise ValueError("Separate stockness probe drifted")
        proportion_expected = "YES" if len(figures) == 3 else "NO"
        row = expected.get(fixture["case_id"])
        if not isinstance(row, Mapping) or set(row) != set(LEAVES):
            raise ValueError("Source expected-ledger geometry drifted")
        if row[TARGET] != target_expected or row[CONTROLS[0]] != probe_expected or row[CONTROLS[1]] != proportion_expected:
            raise ValueError("Semantic construction oracle drifted")
        semantic_cells.add((target_expected, probe_expected, proportion_expected))
    if len(semantic_cells) != 8 or set(expected) != {row["case_id"] for row in fixtures}:
        raise ValueError("Source corpus no longer provides the full orthogonal grid")


def verify_holdout_commitment() -> None:
    value = load_json(ROOT / "real-holdout-commitment.json")
    expected = {
        "format_version", "study_id", "visibility", "carrier_status", "excerpt_slots",
        "disjointness", "prohibitions", "execution_gate",
    }
    if set(value) != expected or value["format_version"] != 1 or value["study_id"] != STUDY_ID:
        raise ValueError("Real-holdout commitment identity drifted")
    if value["visibility"] != "public_commitment_only_no_excerpt_text" or value["carrier_status"] != "not_authored_or_sourced":
        raise ValueError("Real-holdout commitment must not carry text or a source")
    slots = value["excerpt_slots"]
    if not isinstance(slots, list) or len(slots) != 8 or len(set(slots)) != 8 or any(not isinstance(slot, str) or not slot.startswith("real-holdout-") for slot in slots):
        raise ValueError("Real-holdout commitment requires eight opaque slots")
    if value["prohibitions"] != ["Gray Blood", "public excerpt text", "holdout tuning", "provider submission before Phase B pass and separate private carrier freeze"]:
        raise ValueError("Real-holdout exclusions drifted")
    if value["execution_gate"] != "Phase_B_pass_and_separate_private_carrier_freeze_with_eight_disjoint_excerpt_hashes_before_any_provider_call":
        raise ValueError("Real-holdout execution gate drifted")
    required_disjointness = {
        "development_corpus": "no shared text, phrase, actor, setting, or figurative construction",
        "between_holdout_slots": "no shared source passage or overlapping excerpt",
        "selection": "one use only; selection cannot use this package's model outcomes",
    }
    if value["disjointness"] != required_disjointness:
        raise ValueError("Real-holdout disjointness contract drifted")


def phase_a_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    labels = source_labels()["expected_verdicts"]
    for fixture in source_corpus()["fixtures"]:
        fixture_hash = hashlib.sha256(canonical_bytes(fixture)).hexdigest()
        for leaf_id in LEAVES:
            for repeat in REPEATS:
                slots.append({
                    "slot_id": f"fmcs-v1-a-{fixture['case_id']}-{leaf_id.rsplit('.', 1)[-1]}-r{repeat}",
                    "phase": "A", "case_id": fixture["case_id"], "leaf_id": leaf_id, "repeat": repeat,
                    "expected_verdict": labels[fixture["case_id"]][leaf_id], "fixture_sha256": fixture_hash,
                })
    if len(slots) != 72 or len({slot["slot_id"] for slot in slots}) != 72:
        raise ValueError("Phase A schedule drifted")
    return slots


def phase_b_slots() -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    labels = source_labels()["expected_verdicts"]
    for fixture in source_corpus()["fixtures"]:
        fixture_hash = hashlib.sha256(canonical_bytes(fixture)).hexdigest()
        for repeat in REPEATS:
            slots.append({
                "slot_id": f"fmcs-v1-b-{fixture['case_id']}-metaphor-r{repeat}",
                "phase": "B", "case_id": fixture["case_id"], "leaf_id": TARGET, "repeat": repeat,
                "expected_verdict": labels[fixture["case_id"]][TARGET], "fixture_sha256": fixture_hash,
            })
    if len(slots) != 24 or len({slot["slot_id"] for slot in slots}) != 24:
        raise ValueError("Phase B schedule drifted")
    return slots


def fixture_stratum(fixture: Mapping[str, Any]) -> tuple[str, int]:
    construction = fixture["semantic_construction"]
    probe = next(figure for figure in construction["figures"] if figure["role"] == "separate_probe")
    return str(probe["source_domain"]), len(construction["figures"])


def production_question(leaf_id: str) -> dict[str, Any]:
    row = source_leaf_records().get(leaf_id)
    if row is None:
        raise ValueError("Unknown frozen leaf")
    return {
        "module_id": row["module_id"], "domain_id": row["module_id"], "role": "primary",
        "question": {
            "id": leaf_id, "text": row["text"], "question_type": row["question_type"],
            "applies_when": row["applies_when"], "evidence_policy": row["evidence_policy"],
        },
    }


def render_provider_prompt(slot_id: str) -> str:
    slots = {slot["slot_id"]: slot for slot in [*phase_a_slots(), *phase_b_slots()]}
    slot = slots.get(slot_id)
    if slot is None:
        raise ValueError("Unknown frozen slot")
    fixture = next(row for row in source_corpus()["fixtures"] if row["case_id"] == slot["case_id"])
    base = "\n\n".join((REPOSITORY / "prompts" / "judge" / name).read_text(encoding="utf-8").strip() for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md"))
    checklist = "" if slot["phase"] == "A" else "\n\n" + CANDIDATE_CHECKLIST
    prompt = production_runner._render_prompt(
        binary_prompt=base + checklist,
        artifact={"name": "public-synthetic-fixture.txt", "text": fixture["text"]}, contexts=[],
        bundle_id="figurative-metaphor-checklist-successor-development",
        artifact_id="public-synthetic-fixture", questions=[production_question(slot["leaf_id"])],
        task_contract_context={
            "context_version": production_runner.TASK_CONTRACT_JUDGE_CONTEXT_VERSION,
            "untrusted_evaluation_data": True, "artifact_kind": "prose.short_story",
            "declared_scope": "complete supplied passage", "completion_status": "complete",
            "background": "Public synthetic development screen for a figurative-metaphor checklist.",
            "constraints": [], "audience": "development-only rubric validation", "preferences": [], "priorities": [],
        },
    )
    forbidden = (slot_id, slot["case_id"], "expected_verdicts", "local_ledger_only_not_provider_input", "semantic_construction", "reviewer_rationale", "relational_implication", "P1_APPENDIX")
    if any(value in prompt for value in forbidden):
        raise ValueError("Provider-facing prompt leaked local metadata")
    if slot["phase"] == "A" and CANDIDATE_CHECKLIST in prompt:
        raise ValueError("Candidate checklist leaked into current-production phase")
    if slot["phase"] == "B" and CANDIDATE_CHECKLIST not in prompt:
        raise ValueError("Candidate checklist is absent from treatment phase")
    return prompt


def render_all_provider_prompts() -> dict[str, str]:
    prompts = {slot["slot_id"]: render_provider_prompt(slot["slot_id"]) for slot in [*phase_a_slots(), *phase_b_slots()]}
    if len(prompts) != 96:
        raise ValueError("Total two-phase prompt plan drifted")
    return prompts


def verify_contract_structure() -> dict[str, Any]:
    contract = load_contract()
    required = {
        "format_version", "study_id", "status", "development_only", "provider_execution", "eventual_executor", "fixture_provenance",
        "geometry", "leaves", "candidate_checklist", "phase_a", "phase_b", "real_holdout", "promotion", "bindings",
    }
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID or contract["status"] != "frozen_two_phase_development_preexecution" or contract["development_only"] is not True:
        raise ValueError("Frozen successor contract identity drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 0, "one_leaf_per_request": True}:
        raise ValueError("Provider-free execution boundary drifted")
    if contract["eventual_executor"] != {"enabled": False, "route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "one_leaf_per_request": True, "batch_size": 1, "repeats_per_slot": 3, "physical_attempts_per_slot": 1, "retry_or_resume": "forbidden", "attempt_lifecycle_policy": "terminal_sidecar_v1", "zero_incremental_charge_only": True, "paid_fallback": "forbidden"}:
        raise ValueError("Eventual executor boundary drifted")
    if contract["fixture_provenance"] != {"predecessor_study_id": SOURCE_STUDY_ID, "predecessor_modified": False, "predecessor_public_corpus_reused": False, "replacement": "eight_new_public_synthetic_v2_semantic_construction_cases"}:
        raise ValueError("Fixture provenance boundary drifted")
    if contract["geometry"] != {"phase_a": {"fixtures": 8, "leaves": 3, "repeats": 3, "slots": 72}, "phase_b": {"fixtures": 8, "leaves": 1, "repeats": 3, "slots": 24}, "maximum_slots_after_phase_a_gate": 96}:
        raise ValueError("Two-phase geometry drifted")
    if contract["leaves"] != {"target": TARGET, "controls": list(CONTROLS)}:
        raise ValueError("Leaf ownership boundary drifted")
    if contract["candidate_checklist"] != {"exact_text": CANDIDATE_CHECKLIST, "applies_to": TARGET, "excludes": ["familiarity/defaultness", "sheer figurative load relative to content"], "no_runtime_promotion": True}:
        raise ValueError("Candidate checklist boundary drifted")
    if contract["phase_a"] != {"prompt": "current_production_prompt_only", "current_target_sufficient": "24_of_24", "controls_required": "24_of_24_each", "stable_miss": "same_wrong_target_verdict_all_3_repeats", "phase_b_gate": "at_least_2_stable_misses_from_differently_worded_cases_across_at_least_2_stockness_load_strata_and_both_controls_24_of_24", "otherwise_stop": ["CURRENT_TARGET_SUFFICIENT_NO_CHANGE", "CURRENT_TARGET_UNSTABLE_NO_CHANGE", "STABLE_MISS_EVIDENCE_INSUFFICIENT_NO_CHANGE", "FIXTURE_OR_OWNERSHIP_INVALID"]}:
        raise ValueError("Phase A stop gates drifted")
    if contract["phase_b"] != {"prompt": "candidate_checklist_target_only", "pass": {"target": "24_of_24", "stable_misses_repaired": "at_least_2_across_at_least_2_stockness_load_strata"}, "failure": "NO_PROMOTION"}:
        raise ValueError("Phase B gate drifted")
    if contract["real_holdout"] != {"excerpt_count": 8, "Gray_Blood": "forbidden", "status": "commitment_only_no_authoring_or_sourcing", "execution": "separate_private_carrier_freeze_required"}:
        raise ValueError("Real-holdout boundary drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight", "qpc24")}:
        raise ValueError("Promotion boundary drifted")
    return contract


def verify_public_package() -> dict[str, Any]:
    contract = verify_contract_structure()
    verify_source_corpus()
    verify_holdout_commitment()
    if contract["bindings"] != expected_bindings():
        raise ValueError("Frozen successor bindings drifted")
    if len(phase_a_slots()) != 72 or len(phase_b_slots()) != 24:
        raise ValueError("Frozen successor schedule drifted")
    return {
        "study_id": STUDY_ID, "provider_calls": 0, "phase_a_slots": 72,
        "phase_b_slots": 24, "real_holdout_excerpt_text_opened": False,
    }


def _validate_records(records: Sequence[Mapping[str, Any]], slots: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_id = {str(record.get("slot_id")): record for record in records}
    expected_ids = {str(slot["slot_id"]) for slot in slots}
    if len(by_id) != len(records) or set(by_id) != expected_ids:
        raise ValueError("Settlement records do not match the frozen schedule")
    for slot in slots:
        record = by_id[slot["slot_id"]]
        if record.get("verdict") not in {"YES", "NO"}:
            raise ValueError("Settlement record contains an invalid binary verdict")
    return by_id


def phase_a_decision(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_id = _validate_records(records, phase_a_slots())
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for slot in phase_a_slots():
        cells[(slot["case_id"], slot["leaf_id"])].append(by_id[slot["slot_id"]]["verdict"] == slot["expected_verdict"])
    if len(cells) != 24 or any(len(values) != 3 for values in cells.values()):
        raise ValueError("Phase A settlement-cell geometry drifted")
    controls_perfect = {leaf: all(all(cells[(fixture["case_id"], leaf)]) for fixture in source_corpus()["fixtures"]) for leaf in CONTROLS}
    target_perfect = all(all(cells[(fixture["case_id"], TARGET)]) for fixture in source_corpus()["fixtures"])
    target_unstable = any(any(cells[(fixture["case_id"], TARGET)]) and not all(cells[(fixture["case_id"], TARGET)]) for fixture in source_corpus()["fixtures"])
    stable_miss_cases = [
        fixture for fixture in source_corpus()["fixtures"]
        if not any(cells[(fixture["case_id"], TARGET)])
    ]
    strata = {fixture_stratum(fixture) for fixture in stable_miss_cases}
    wording = {sha256_text(str(fixture["text"])) for fixture in stable_miss_cases}
    if not all(controls_perfect.values()):
        decision = "FIXTURE_OR_OWNERSHIP_INVALID"
    elif target_perfect:
        decision = "CURRENT_TARGET_SUFFICIENT_NO_CHANGE"
    elif target_unstable:
        decision = "CURRENT_TARGET_UNSTABLE_NO_CHANGE"
    elif len(stable_miss_cases) < 2 or len(wording) < 2 or len(strata) < 2:
        decision = "STABLE_MISS_EVIDENCE_INSUFFICIENT_NO_CHANGE"
    else:
        decision = "PHASE_B_ELIGIBLE"
    return {
        "decision": decision, "target_correct": sum(sum(cells[(fixture["case_id"], TARGET)]) for fixture in source_corpus()["fixtures"]),
        "target_total": 24, "controls": {leaf: {"correct": sum(sum(cells[(fixture["case_id"], leaf)]) for fixture in source_corpus()["fixtures"]), "total": 24, "perfect": controls_perfect[leaf]} for leaf in CONTROLS},
        "stable_miss_case_count": len(stable_miss_cases), "stable_miss_strata_count": len(strata),
        "stable_miss_distinct_wording_count": len(wording),
        "target_unstable_cell_count": sum(1 for fixture in source_corpus()["fixtures"] if any(cells[(fixture["case_id"], TARGET)]) and not all(cells[(fixture["case_id"], TARGET)])),
        "phase_b_permitted": decision == "PHASE_B_ELIGIBLE",
    }


def phase_b_decision(phase_a_records: Sequence[Mapping[str, Any]], phase_b_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    phase_a = phase_a_decision(phase_a_records)
    if phase_a["decision"] != "PHASE_B_ELIGIBLE":
        raise ValueError("Phase B is forbidden unless Phase A is eligible")
    phase_a_by_id = _validate_records(phase_a_records, phase_a_slots())
    by_id = _validate_records(phase_b_records, phase_b_slots())
    correct = sum(by_id[slot["slot_id"]]["verdict"] == slot["expected_verdict"] for slot in phase_b_slots())
    stable_miss_cases = {
        fixture["case_id"]
        for fixture in source_corpus()["fixtures"]
        if all(
            phase_a_by_id[slot["slot_id"]]["verdict"] != slot["expected_verdict"]
            for slot in phase_a_slots()
            if slot["case_id"] == fixture["case_id"] and slot["leaf_id"] == TARGET
        )
    }
    repaired_cases = {
        case_id for case_id in stable_miss_cases
        if all(
            by_id[slot["slot_id"]]["verdict"] == slot["expected_verdict"]
            for slot in phase_b_slots() if slot["case_id"] == case_id
        )
    }
    repaired_strata = {
        fixture_stratum(fixture)
        for fixture in source_corpus()["fixtures"] if fixture["case_id"] in repaired_cases
    }
    phase_a_controls_perfect = all(value["perfect"] for value in phase_a["controls"].values())
    passed = correct == 24 and len(repaired_cases) >= 2 and len(repaired_strata) >= 2 and phase_a_controls_perfect
    return {
        "decision": "PHASE_B_PASS_HOLDOUT_ELIGIBLE" if passed else "NO_PROMOTION",
        "candidate_target_correct": correct, "candidate_target_total": 24,
        "repaired_stable_miss_cases": len(repaired_cases),
        "repaired_stable_miss_strata": len(repaired_strata),
        "phase_a_controls_perfect": phase_a_controls_perfect, "promotion": "none",
    }
