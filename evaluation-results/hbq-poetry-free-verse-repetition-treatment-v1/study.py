"""Provider-free commitment for a private S1 free-verse repetition A/B screen."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-treatment-v1"
LEAF_ID = "form.poetry.free_verse.repetition"
CANDIDATE_TEXT = (
    "Presence of recurrence alone does not satisfy this criterion. Answer YES only "
    "when the supplied instances show that recurrence changes pressure or meaning; "
    "when recurrence is present but does not do so, answer NO."
)
PRESERVED_FIELDS = (
    "id", "module_id", "criterion_key", "pass_answer", "weight", "question_type",
    "severity", "applies_when", "evidence_policy",
)
OPAQUE_SLOT_IDS = tuple(f"s1fvrt-v1-r3-slot-{index:02d}" for index in range(1, 25))
FIXTURE_COMMITMENTS = (
    "013ae6adb5c637fb84d846de669d7f04cf7df86c2f4da8e919828c2fd22e6a13",
    "2a64856565475a762b2fcc5a7d9af589d8ec0b5636aa9a17e3806f2a5ba17d61",
    "42fb20ef361058ef3f4a6e8085c9c5a14925166a19fb4c97aed4c0960a0506a4",
    "bd0a8e0f5d64f45d4f2f31de9d1b8ef5ff6130e6ab54c52209d113a1e1b1474b",
)
PRIVATE_CONTROLLER_COMMITMENT = "7a75a6dd30e028bcfa398b7104bed34d32ea71efb491310eb87d3a50700dd5b9"
PRIVATE_LEDGER_COMMITMENT = "9a3455fee1466d4cdc7461ab33c6b4014a4ad112b0e9f8293d3cf63615f52fbc"
PRIVATE_VALUE_SHA256 = (
    "0d5e666eba82de28ca27b1ac5267c4e6ea4e4de6988c7db86050cc4e9428e4f2",
    "0d6f2ab575bb680b5380faa7359df66648e3b5a6cb787831dcaca6f9e96f54a1",
    "0fcd568a5cb9bdb4677b69354b11ee415af8f784519cff3da49a26f84eaee7f2",
    "23794d91c53ae875c8e247d72561e35d9d06ee07c70c9e0dbcc977a6d161504a",
    "34a04005bcaf206eec990bd9637d9fdb6725e0a0c0d4aebf003f17f4c956eb5c",
    "394c7fdbe7f448f438f0d4add59257f9cfab71f6f5b212c1da84ab2a2211b477",
    "425be7879d71031e655dbd973a0c81402b341ed48f3c8a1f08d34e2acdf6443c",
    "4939983c27aa96148083a912be834edd28d8661042b0d2e319a2f686a6e5cbaf",
    "51d98c2e782d22aec95abbb7dad5cf3fb2aa0da4fb1ebaca59f29aa493c3b50e",
    "55e7302b62d935af50843067da3d903be4fa2c5a67510db5bd8f1704bd727c4c",
    "7d0586912cf823d83c88390b92ed66708a8956b4cc5d51d26cb461262f27235e",
    "88d69a3a1c14f61144ff45ffe116ffa2420490a7384dfd151c6891b320087de6",
    "8f1130444defef7f131ed4d1983f0e31b3a2cfbf3faff268a71e8ec7e1290382",
    "b7b9356f39da5055f2be84b07bad19fc8c6a3716da5fb25f722535b172fd78bb",
    "bb4d27ddba04b0ed1b71024b2f596880fbd5656bd917cfbef43c77a08e4182b0",
    "c4663a6d2b61cf6fb9ebdc4c86c444ec2e94ed05ef657f32fc49378f7a9c5812",
    "dc2d91edff633a2bd96b9bc8f7d571bedb6196aaf66e433da36477d8796ab279",
    "df50f680326679347d5591b14f5f18b409e3f08948ad0641ed3e6d75612efce0",
    "e3f111161169204407e64bccdf0c65760e177f506f3300dbae79013c61310cc2",
    "eebbf6457e46a7f63acdf9b97390f790ba443d60cfa44b607da7e5c40aa1cc1d",
    "f8e0837f7c5d01587f45e504a889de435c521b82fa63a4a7a3889a40c4c7df97",
    "f9171164593756e56fb197327b529a4955590566560dbe62d586bff41be9d297",
)
RUNTIME_PATHS = (
    "prompts/judge/JUDGE_PREFIX.md",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md",
    "schema/hbq_judge_response.schema.json",
    "registry/modules/form.poetry.free_verse.yaml",
    "registry/question_index.jsonl",
    "registry/criterion_ownership.json",
    "src/hbqrs/runner.py",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Study contract must be an object")
    return value


def source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == LEAF_ID:
            return {key: row[key] for key in PRESERVED_FIELDS + ("text",)}
    raise ValueError("Canonical free-verse repetition leaf is unavailable")


def source_owner() -> dict[str, Any]:
    owner = json.loads((REPOSITORY / "registry" / "criterion_ownership.json").read_text(encoding="utf-8")).get(LEAF_ID)
    if owner != {"module_id": "form.poetry.free_verse", "question_id": LEAF_ID}:
        raise ValueError("Canonical free-verse repetition owner drifted")
    return owner


def candidate_leaf() -> dict[str, Any]:
    candidate = source_leaf()
    candidate["text"] = CANDIDATE_TEXT
    return candidate


def opaque_schedule() -> list[dict[str, str]]:
    return [{"opaque_slot_id": slot_id} for slot_id in OPAQUE_SLOT_IDS]


def _expected_contract() -> dict[str, Any]:
    source = source_leaf()
    candidate = candidate_leaf()
    return {
        "format_version": 3,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_private_same_fixture_ab_treatment_r3",
        "development_only": True,
        "provider_execution": {
            "permitted_now": False,
            "provider_calls_made_now_exact": 0,
            "planned_new_provider_calls_exact": 24,
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "reasoning": "high",
            "zero_paid_route_required": True,
            "semantic_retries_permitted": False,
            "one_leaf_per_request": True,
        },
        "candidate": {
            "leaf_id": LEAF_ID,
            "text": CANDIDATE_TEXT,
            "source_leaf_sha256": sha256_bytes(canonical_json(source)),
            "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)),
            "owner": source_owner(),
            "preserved_fields": {key: source[key] for key in PRESERVED_FIELDS},
        },
        "geometry": {
            "private_fixture_commitments_exact": 4,
            "arms_exact": 2,
            "repeats_exact": 3,
            "opaque_slots_exact": 24,
            "same_fixture_ab": True,
        },
        "privacy": {
            "fixture_text": "private_controller_only",
            "expected_labels": "private_controller_only",
            "arm_mapping": "private_controller_only",
            "repeat_mapping": "private_controller_only",
            "provider_facing_metadata": "opaque_slot_id_never_rendered",
            "public_package_contains": "commitments_and_opaque_schedule_only",
            "predecessor_private_freezes": "r1_and_r2_retained_unexecuted_provenance_only",
        },
        "private_commitments": {
            "controller_sha256": PRIVATE_CONTROLLER_COMMITMENT,
            "ledger_sha256": PRIVATE_LEDGER_COMMITMENT,
            "fixture_sha256": list(FIXTURE_COMMITMENTS),
            "value_sha256": list(PRIVATE_VALUE_SHA256),
        },
        "development_gate": {
            "candidate_required": "12/12",
            "candidate_target_required": "3/3",
            "candidate_controls_required": "9/9",
            "current_target_maximum": "2/3",
            "pass_authorizes_only": "disjoint_holdout",
            "failure_action": "NO_GO_DSPY_ELIGIBLE_ONLY",
            "derivation": "private_verified_terminal_slot_records_only",
            "summary_boolean_attestation_accepted": False,
        },
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "owner", "weight", "influence", "split")},
        "bindings": {path: sha256_file(REPOSITORY / path) for path in RUNTIME_PATHS},
    }


def validate_package() -> dict[str, Any]:
    if load_contract() != _expected_contract():
        raise ValueError("Treatment contract or live source binding drifted")
    schedule = opaque_schedule()
    if len(schedule) != 24 or len(set(OPAQUE_SLOT_IDS)) != 24:
        raise ValueError("Opaque same-fixture A/B geometry drifted")
    if any(set(row) != {"opaque_slot_id"} for row in schedule):
        raise ValueError("Public schedule leaked private controller metadata")
    if source_owner() != {"module_id": "form.poetry.free_verse", "question_id": LEAF_ID}:
        raise ValueError("Leaf ownership drifted")
    return {"study_id": STUDY_ID, "provider_calls": 0, "opaque_slots": 24, "private_fixture_commitments": 4, "holdout_eligible_on_verified_success": True}
