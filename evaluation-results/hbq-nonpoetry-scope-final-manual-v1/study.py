"""Provider-free public commitment for the final S2 manual A/B comparison."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-nonpoetry-scope-final-manual-v1"
PREDECESSOR_ID = "hbq-nonpoetry-scope-treatment-v1-execution-v1"
LEAF_ID = "scope.passage.status"
CANDIDATE_TEXT = "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?"
ARMS = ("baseline", "candidate")
REPEATS = (1, 2, 3)
FIXTURE_COMMITMENTS = (
    "b6aa8c4d711469560f3c8239a761730478de57333ff7a02f3654930fe92fabc4",
    "9f5adad37b9799c66ebe12fcb001c213df6d3a27f0105bbef4abd8b39a40801a",
    "05b5ebfb1459f98ba9898a6ef476b62bd8ce82d33f96099eabe5a215993d4b63",
    "d9fdc9a2267c0e66a7b8327fda5e1a7e2e91148e215fd3edf633078d3f01ef14",
)
PRIVATE_CONTROLLER_COMMITMENT = "b6f12ade4ee05e4507080d4fc9e6d93b5ff99b2295bfa8d599d613b4e05b75eb"
PRESERVED_FIELDS = (
    "id", "module_id", "criterion_key", "pass_answer", "weight", "question_type",
    "severity", "applies_when", "evidence_policy",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(name: str) -> dict[str, Any]:
    value = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {name}")
    return value


def source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == LEAF_ID:
            return {key: row[key] for key in PRESERVED_FIELDS + ("text",)}
    raise ValueError("Canonical S2 leaf is unavailable")


def source_owner() -> dict[str, Any]:
    ownership = json.loads((REPOSITORY / "registry" / "criterion_ownership.json").read_text(encoding="utf-8"))
    owner = ownership.get(LEAF_ID)
    if owner != {"module_id": "scope.passage", "question_id": LEAF_ID}:
        raise ValueError("Canonical S2 leaf owner drifted")
    return owner


def candidate_leaf() -> dict[str, Any]:
    candidate = source_leaf()
    candidate["text"] = CANDIDATE_TEXT
    return candidate


def build_plan() -> list[dict[str, Any]]:
    """Return an opaque controller schedule without fixture or oracle content."""
    plan: list[dict[str, Any]] = []
    for fixture_index, fixture_commitment in enumerate(FIXTURE_COMMITMENTS, start=1):
        for arm in ARMS:
            question = candidate_leaf() if arm == "candidate" else source_leaf()
            for repeat in REPEATS:
                plan.append({
                    "slot_id": f"s2fm-v1-f{fixture_index}-{arm}-r{repeat}",
                    "fixture_commitment_sha256": fixture_commitment,
                    "leaf_id": LEAF_ID,
                    "arm": arm,
                    "repeat": repeat,
                    "question": question,
                })
    if len(plan) != 24 or len({row["slot_id"] for row in plan}) != 24:
        raise ValueError("Final-manual A/B geometry drifted")
    return plan


def _expected_contract() -> dict[str, Any]:
    source = source_leaf()
    candidate = candidate_leaf()
    return {
        "format_version": 2,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_final_manual_question_level_successor",
        "development_only": True,
        "provider_execution": {"permitted_now": False, "provider_calls_made_now_exact": 0, "one_leaf_per_request": True, "planned_contingency": "fresh_24_call_ab_only", "planned_new_provider_calls_exact": 24},
        "candidate": {"leaf_id": LEAF_ID, "text": CANDIDATE_TEXT, "source_leaf_sha256": sha256_bytes(canonical_json(source)), "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)), "owner": source_owner(), "preserved_fields": {key: source[key] for key in PRESERVED_FIELDS}},
        "geometry": {"fixtures_exact": 4, "arms": list(ARMS), "repeats": 3, "slots_exact": 24},
        "reuse": {"predecessor_study_id": PREDECESSOR_ID, "preferred_only_if": "independent controller verifies exactly twelve candidate and twelve baseline accepted v1 calls for the same four fixture bytes and byte-identical question inputs", "selected_mode": "fresh_24_call_ab", "reused_accepted_calls_exact": 0, "ineligible_reason": "The available v1 execution successor is frozen unexecuted and its candidate wording is not byte-identical to this corrected candidate."},
        "private_controller": {"controller_contract_commitment_sha256": PRIVATE_CONTROLLER_COMMITMENT, "fixture_commitments_sha256": list(FIXTURE_COMMITMENTS), "fixture_content": "private_controller_only", "expected_states": "private_controller_only", "responses_and_receipts": "private_controller_only", "public_package_contains": "commitments_and_opaque_schedule_only"},
        "development_gate": {"private_controller_applies_frozen_four_cell_gate": True, "failure_action": "NO_GO_DSPY_ELIGIBLE_ONLY", "success_action": "HOLDOUT_ELIGIBLE_ON_SUCCESS"},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "owner", "weight", "applicability", "evidence_policy")},
        "bindings": {"question_index_sha256": sha256_file(REPOSITORY / "registry" / "question_index.jsonl"), "criterion_ownership_sha256": sha256_file(REPOSITORY / "registry" / "criterion_ownership.json")},
    }


def validate_package() -> dict[str, Any]:
    if load_json("study-contract.json") != _expected_contract():
        raise ValueError("Final-manual contract or live source binding drifted")
    plan = build_plan()
    if any(row["question"]["id"] != LEAF_ID for row in plan):
        raise ValueError("A/B plan must remain one leaf per request")
    if any("expected_verdict" in row or "fixture_text" in row or "state" in row for row in plan):
        raise ValueError("Private controller data leaked into the public plan")
    return {"study_id": STUDY_ID, "provider_calls": 0, "planned_new_calls": 24, "reused_calls": 0, "holdout_eligible_on_success": True}


def assess_private_controller_attestation(attestation: Mapping[str, Any]) -> dict[str, Any]:
    """Accept only a commitment-bound controller summary, never raw private results."""
    required = {"visibility", "controller_contract_commitment_sha256", "completed_calls", "candidate_all_four_cells_3_of_3", "no_localized_or_inactive_regression"}
    if set(attestation) != required or attestation["visibility"] != "private_controller_only":
        raise ValueError("Controller attestation visibility or surface drifted")
    if attestation["controller_contract_commitment_sha256"] != PRIVATE_CONTROLLER_COMMITMENT or attestation["completed_calls"] != 24:
        raise ValueError("Controller attestation binding or geometry drifted")
    if not isinstance(attestation["candidate_all_four_cells_3_of_3"], bool) or not isinstance(attestation["no_localized_or_inactive_regression"], bool):
        raise ValueError("Controller attestation gate values drifted")
    passed = attestation["candidate_all_four_cells_3_of_3"] and attestation["no_localized_or_inactive_regression"]
    return {"decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS" if passed else "NO_GO_DSPY_ELIGIBLE_ONLY", "provider_calls": 0}
