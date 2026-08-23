"""Provider-free S2 disjoint passage-status holdout freeze."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-nonpoetry-scope-disjoint-holdout-v1"
EARNED_BY_COMMIT = "271e30a6adf08e6fc8f9da40cf48638d60b412eb"
LEAF_ID = "scope.passage.status"
CANDIDATE_TEXT = "For a passage explicitly declared to be an excerpt or fragment, does the supplied evaluation avoid penalizing it for not being a complete work?"
ARMS = ("baseline", "candidate")
REPEATS = (1, 2, 3)
SCHEDULE_SEED = "s2-disjoint-holdout-v1-20260823"
FIXTURE_IDS = tuple(f"s2dh-f{index:02d}" for index in range(1, 9))
FIXTURE_COMMITMENTS = (
    "757a26958f7015a25a4ab13dd95234078d2fd1fe4108ce333311e6376eb07366",
    "220377d5ea669abcd6840c339930f95c7427bb06df2fd2f9a437199d8d0e9313",
    "6dee70f65fbbaac44626caa26f40ea0fd5087f55511d091b1259e11edda75254",
    "aa11addd56372de2abe3ddf564cc34d568ada11e59bcfac268020506566af58d",
    "30fe0e80fe0cdca980dc64e125060781fbbe49b8d3316fe80121175fab891f0c",
    "6f239b65f24d1a5ad3c66c66a1f1acad9e05085275742cd7a85ea3a488d42eff",
    "aaa202da0e9a3005c2c2c32934586480027106393beccf6c5041b63f3a831f80",
    "97ec005e2583a69cf4cb6d7779eeaf9de186a197c3ba730b9ca9576ffd10b435",
)
PRIVATE_CONTROLLER_COMMITMENT = "d09ac27f48282bfd4fb13322a7d5987f3029fb68d8de8d209bd083ff1f704474"
PRIVATE_FIXTURES_SHA256 = "b22bb9ced4666c82af9fde182ce2e1a27dc53b69453149024321b4d09b2e3375"
PRIVATE_EXPECTED_LEDGER_SHA256 = "ce956bb6d28fa82d5289375f9092a8c9e0883a590d3a78be0392eb5564d143f5"
PRIVATE_SOURCE_MANIFEST_SHA256 = "d700f89352d587a0dbe2463388eb620cde7904877aa7ec6cfee6f1ad5ea8bb2c"
PRIVATE_SCHEDULE_SHA256 = "e0488ea3c7a82791b6ef14ea8fdbf20f91b880efb09b68677dbdbb712dd054d4"
PRESERVED_FIELDS = (
    "id", "module_id", "criterion_key", "pass_answer", "weight",
    "question_type", "severity", "applies_when", "evidence_policy",
)
UNAVOIDABLE_TOKENS = frozenset({
    "a", "an", "and", "artifact", "assessment", "book", "complete",
    "completeness", "declared", "does", "evaluation", "excerpt", "fragment",
    "from", "in", "is", "it", "no", "not", "of", "or", "passage",
    "record", "scope", "supplied", "the", "this", "to", "whole", "work",
})


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == LEAF_ID:
            return {key: row[key] for key in PRESERVED_FIELDS + ("text",)}
    raise ValueError("Canonical S2 leaf is unavailable")


def source_owner() -> dict[str, Any]:
    ownership = load_json(REPOSITORY / "registry" / "criterion_ownership.json")
    owner = ownership.get(LEAF_ID)
    if owner != {"module_id": "scope.passage", "question_id": LEAF_ID}:
        raise ValueError("Canonical S2 criterion ownership drifted")
    return owner


def candidate_leaf() -> dict[str, Any]:
    candidate = source_leaf()
    candidate["text"] = CANDIDATE_TEXT
    return candidate


def _ordered_slot_ids() -> list[str]:
    slots = [
        f"{fixture_id}-{arm}-r{repeat}"
        for fixture_id in FIXTURE_IDS
        for arm in ARMS
        for repeat in REPEATS
    ]
    return sorted(slots, key=lambda slot_id: sha256_bytes(f"{SCHEDULE_SEED}|{slot_id}".encode("utf-8")))


def build_public_plan() -> list[dict[str, Any]]:
    commitments = dict(zip(FIXTURE_IDS, FIXTURE_COMMITMENTS, strict=True))
    plan: list[dict[str, Any]] = []
    pattern = re.compile(r"^(s2dh-f\d{2})-(baseline|candidate)-r([123])$")
    for slot_id in _ordered_slot_ids():
        match = pattern.fullmatch(slot_id)
        if match is None:
            raise ValueError("Opaque schedule slot drifted")
        fixture_id, arm, repeat_text = match.groups()
        question = candidate_leaf() if arm == "candidate" else source_leaf()
        plan.append({
            "slot_id": slot_id,
            "fixture_commitment_sha256": commitments[fixture_id],
            "p0_p3_commitment_sha256": commitments[fixture_id],
            "leaf_id": LEAF_ID,
            "arm": arm,
            "repeat": int(repeat_text),
            "p4_question": question,
        })
    if len(plan) != 48 or len({row["slot_id"] for row in plan}) != 48:
        raise ValueError("Disjoint holdout geometry drifted")
    return plan


def _expected_contract() -> dict[str, Any]:
    source = source_leaf()
    candidate = candidate_leaf()
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_disjoint_holdout",
        "earned_by_public_commit": EARNED_BY_COMMIT,
        "development_only": True,
        "provider_execution": {
            "permitted_now": False,
            "provider_calls_made_exact": 0,
            "planned_future_calls_exact": 48,
            "route": "codex",
            "model": "gpt-5.6-sol",
            "reasoning": "high",
            "one_leaf_per_request": True,
            "post_response_retries_permitted": False,
            "paid_or_fallback_route": "forbidden",
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
            "fixtures_exact": 8,
            "public_domain_carriers_exact": 6,
            "activation_controls_exact": 2,
            "states_exact": 4,
            "fixtures_per_state_exact": 2,
            "arms": list(ARMS),
            "repeats": 3,
            "slots_exact": 48,
        },
        "private_controller": {
            "controller_contract_commitment_sha256": PRIVATE_CONTROLLER_COMMITMENT,
            "fixtures_commitment_sha256": PRIVATE_FIXTURES_SHA256,
            "expected_ledger_commitment_sha256": PRIVATE_EXPECTED_LEDGER_SHA256,
            "source_manifest_commitment_sha256": PRIVATE_SOURCE_MANIFEST_SHA256,
            "schedule_commitment_sha256": PRIVATE_SCHEDULE_SHA256,
            "fixture_commitments_sha256": list(FIXTURE_COMMITMENTS),
            "fixture_content": "private_controller_only",
            "expected_states": "separate_private_ledger_only",
            "source_details": "private_controller_only",
            "responses_and_receipts": "future_private_controller_only",
        },
        "source_policy": {
            "provider": "Project Gutenberg authoritative HTML and landing pages",
            "copyright_status_required": "Public domain in the USA.",
            "original_publication_before_year": 1929,
            "remote_archives_or_bulk_downloads": "forbidden",
            "exact_excerpt_offsets_and_hashes": "private_source_manifest",
        },
        "contamination_policy": {
            "fixture_sha_overlap": "forbidden",
            "source_title_author_or_id_reuse": "forbidden",
            "subject_and_structure_reuse": "forbidden",
            "normalized_eight_token_predecessor_overlap_after_fixed_vocabulary_removal": "forbidden",
        },
        "arm_parity": "byte_identical_fixture_context_and_evidence_p0_p3_p4_question_text_only",
        "decision_gate": {
            "pass": "PROMOTION_REVIEW_ELIGIBLE",
            "pass_requires": [
                "candidate_24_of_24_raw_and_8_of_8_cells_3_of_3",
                "both_control_states_correct_in_both_arms",
                "candidate_improves_at_least_one_fixture_cell_in_each_target_state",
            ],
            "no_effect": "candidate_perfect_all_controls_correct_in_both_arms_but_two_target_state_improvement_floor_not_met",
            "no_go": "any_candidate_mismatch_any_control_mismatch_in_either_arm_invalid_route_or_post_response_retry",
        },
        "public_result_policy": "aggregate_only_after_execution",
        "promotion": "none_until_pass_and_independent_sol_review",
        "bindings": {
            "question_index_sha256": sha256_file(REPOSITORY / "registry" / "question_index.jsonl"),
            "criterion_ownership_sha256": sha256_file(REPOSITORY / "registry" / "criterion_ownership.json"),
        },
    }


def validate_public_package() -> dict[str, Any]:
    contract = load_json(ROOT / "study-contract.json")
    if contract != _expected_contract():
        raise ValueError("Public disjoint-holdout contract or live binding drifted")
    plan = build_public_plan()
    forbidden = {"fixture_text", "source_excerpt", "expected_verdict", "state", "rationale"}
    if any(forbidden.intersection(row) for row in plan):
        raise ValueError("Private holdout data leaked into the public plan")
    for fixture_id in FIXTURE_IDS:
        for repeat in REPEATS:
            pair = [row for row in plan if row["slot_id"].startswith(f"{fixture_id}-") and row["repeat"] == repeat]
            if len(pair) != 2 or {row["arm"] for row in pair} != set(ARMS):
                raise ValueError("A/B pair geometry drifted")
            if len({row["p0_p3_commitment_sha256"] for row in pair}) != 1:
                raise ValueError("A/B arms differ before P4")
            if len({sha256_bytes(canonical_json(row["p4_question"])) for row in pair}) != 2:
                raise ValueError("A/B P4 questions are not distinct")
    return {
        "study_id": STUDY_ID,
        "provider_calls": 0,
        "planned_future_calls": 48,
        "fixtures": 8,
        "opaque_slot_ids": [row["slot_id"] for row in plan],
        "promotion": "none",
    }


def classify_gate(attestation: dict[str, Any]) -> str:
    """Exhaustively classify a future aggregate without inspecting private rows."""
    required = {
        "candidate_all_eight_cells_3_of_3",
        "baseline_controls_all_correct",
        "candidate_controls_all_correct",
        "improved_material_failure_cell",
        "improved_missing_evidence_cell",
        "route_and_receipts_valid",
        "post_response_retries",
    }
    if set(attestation) != required:
        raise ValueError("Aggregate gate attestation surface drifted")
    boolean_fields = required - {"post_response_retries"}
    if any(not isinstance(attestation[field], bool) for field in boolean_fields):
        raise ValueError("Aggregate gate boolean type drifted")
    retries = attestation["post_response_retries"]
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise ValueError("Aggregate gate retry count drifted")
    if (
        not attestation["route_and_receipts_valid"]
        or retries != 0
        or not attestation["candidate_all_eight_cells_3_of_3"]
        or not attestation["baseline_controls_all_correct"]
        or not attestation["candidate_controls_all_correct"]
    ):
        return "NO_GO"
    if attestation["improved_material_failure_cell"] and attestation["improved_missing_evidence_cell"]:
        return "PROMOTION_REVIEW_ELIGIBLE"
    return "NO_EFFECT"


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        token for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in UNAVOIDABLE_TOKENS
    )


def _ngrams(text: str, size: int = 8) -> set[tuple[str, ...]]:
    tokens = _tokens(text)
    return {tokens[index:index + size] for index in range(max(0, len(tokens) - size + 1))}


def _fixture_text(fixture: dict[str, Any]) -> str:
    values = [fixture.get("source_excerpt") or "", fixture["evaluation_record"], *fixture["contexts"]]
    return "\n".join(values)


def _predecessor_texts(predecessor_private_root: Path) -> list[str]:
    corpus = load_json(REPOSITORY / "evaluation-results" / "hbq-nonpoetry-scope-sentinel-v1" / "public-synthetic-corpus.json")
    texts = [
        "\n".join([row["text"], *row.get("contexts", [])])
        for row in corpus["artifacts"]
        if row.get("leaf_id") == LEAF_ID
    ]
    predecessor = load_json(predecessor_private_root / "controller-contract.v1.json")
    for fixture in predecessor.get("fixtures", []):
        texts.append("\n".join([fixture.get("text", ""), *fixture.get("contexts", [])]))
    if len(texts) < 8:
        raise ValueError("Predecessor fixture corpus is incomplete")
    return texts


def validate_private_root(private_root: Path, predecessor_private_root: Path) -> dict[str, Any]:
    private_root = private_root.resolve()
    predecessor_private_root = predecessor_private_root.resolve()
    expected_files = {
        "fixtures.v1.json": PRIVATE_FIXTURES_SHA256,
        "expected-ledger.v1.json": PRIVATE_EXPECTED_LEDGER_SHA256,
        "source-manifest.v1.json": PRIVATE_SOURCE_MANIFEST_SHA256,
        "private-schedule.v1.json": PRIVATE_SCHEDULE_SHA256,
    }
    controller_path = private_root / "controller-contract.v1.json"
    if sha256_file(controller_path) != PRIVATE_CONTROLLER_COMMITMENT:
        raise ValueError("Private controller commitment drifted")
    controller = load_json(controller_path)
    if controller.get("study_id") != STUDY_ID or controller.get("provider_execution", {}).get("provider_calls_made_exact") != 0:
        raise ValueError("Private controller identity or zero-call state drifted")
    if controller.get("file_bindings") != expected_files:
        raise ValueError("Private controller file binding surface drifted")
    if controller.get("decision_gate") != _expected_contract()["decision_gate"]:
        raise ValueError("Private/public decision gate parity drifted")
    for name, expected_hash in expected_files.items():
        if sha256_file(private_root / name) != expected_hash:
            raise ValueError(f"Private file commitment drifted: {name}")

    fixture_doc = load_json(private_root / "fixtures.v1.json")
    ledger_doc = load_json(private_root / "expected-ledger.v1.json")
    source_doc = load_json(private_root / "source-manifest.v1.json")
    schedule_doc = load_json(private_root / "private-schedule.v1.json")
    fixtures = fixture_doc.get("fixtures")
    ledger = ledger_doc.get("rows")
    sources = source_doc.get("sources")
    if not isinstance(fixtures, list) or len(fixtures) != 8 or not isinstance(ledger, list) or len(ledger) != 8:
        raise ValueError("Private fixture or ledger geometry drifted")
    if not isinstance(sources, list) or len(sources) != 6:
        raise ValueError("Private source geometry drifted")
    fixture_ids = [row.get("fixture_id") for row in fixtures]
    if tuple(fixture_ids) != FIXTURE_IDS or {row.get("fixture_id") for row in ledger} != set(FIXTURE_IDS):
        raise ValueError("Private fixture or ledger identity drifted")
    forbidden_fixture_fields = {"state", "expected_verdict", "gate_role", "rationale"}
    if any(forbidden_fixture_fields.intersection(row) for row in fixtures):
        raise ValueError("Expected labels leaked into fixture records")
    verdict_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    for row in ledger:
        verdict_counts[row["expected_verdict"]] = verdict_counts.get(row["expected_verdict"], 0) + 1
        state_counts[row["state"]] = state_counts.get(row["state"], 0) + 1
    if verdict_counts != {"YES": 2, "NO": 2, "CANNOT_ASSESS": 2, "NOT_APPLICABLE": 2}:
        raise ValueError("Expected-verdict balance drifted")
    if state_counts != {"localized_issue": 2, "material_failure": 2, "missing_required_evidence": 2, "activation_mismatch": 2}:
        raise ValueError("State balance drifted")

    if len({row["structure_id"] for row in fixtures}) != 8 or len({row["subject_key"] for row in fixtures}) != 8:
        raise ValueError("Fixture structure or subject disjointness drifted")
    source_by_id = {row["source_id"]: row for row in sources}
    if len(source_by_id) != 6 or len({row["title"] for row in sources}) != 6 or len({row["author"] for row in sources}) != 6:
        raise ValueError("Source title, author, or identifier reuse detected")
    if any(row["original_publication_year"] >= 1929 for row in sources):
        raise ValueError("A source is outside the frozen pre-1929 public-domain set")
    if any(row["copyright_status"] != "Public domain in the USA." for row in sources):
        raise ValueError("Source copyright status drifted")
    if any(not row["landing_url"].startswith("https://www.gutenberg.org/ebooks/") or not row["content_url"].startswith("https://www.gutenberg.org/cache/epub/") for row in sources):
        raise ValueError("Non-authoritative source URL detected")
    if any(sha256_bytes(row["excerpt"].encode("utf-8")) != row["excerpt_sha256"] for row in sources):
        raise ValueError("Source excerpt hash drifted")
    sourced = [row for row in fixtures if row.get("source_id") is not None]
    controls = [row for row in fixtures if row.get("source_id") is None]
    if len(sourced) != 6 or len(controls) != 2 or any(row.get("source_excerpt") is not None for row in controls):
        raise ValueError("Source-carrier or activation-control geometry drifted")
    if any(row["source_excerpt"] != source_by_id[row["source_id"]]["excerpt"] for row in sourced):
        raise ValueError("Fixture excerpt is not byte-identical to its source record")

    fixture_commitments = [sha256_bytes(canonical_json(row)) for row in fixtures]
    if fixture_commitments != list(FIXTURE_COMMITMENTS) or controller.get("fixture_commitments_sha256") != fixture_commitments:
        raise ValueError("Fixture commitment order or content drifted")
    source_commitments = [sha256_bytes(canonical_json(row)) for row in sources]
    if controller.get("source_record_commitments_sha256") != source_commitments:
        raise ValueError("Source record commitments drifted")
    if schedule_doc != {
        "format_version": 1,
        "study_id": STUDY_ID,
        "ordering": "sha256_sort_v1",
        "ordering_seed": SCHEDULE_SEED,
        "fixture_ids": list(FIXTURE_IDS),
        "arms": list(ARMS),
        "repeats": list(REPEATS),
        "slots_exact": 48,
        "one_leaf_per_request": True,
        "provider_calls_made_exact": 0,
    }:
        raise ValueError("Private schedule freeze drifted")

    predecessor_texts = _predecessor_texts(predecessor_private_root)
    predecessor_hashes = {sha256_bytes(text.casefold().encode("utf-8")) for text in predecessor_texts}
    predecessor_ngrams = set().union(*(_ngrams(text) for text in predecessor_texts))
    for fixture in fixtures:
        text = _fixture_text(fixture)
        if sha256_bytes(text.casefold().encode("utf-8")) in predecessor_hashes:
            raise ValueError("Exact predecessor fixture overlap detected")
        overlap = _ngrams(text).intersection(predecessor_ngrams)
        if overlap:
            raise ValueError(f"Normalized predecessor eight-token overlap detected: {sorted(overlap)[0]}")
    banned = {"lio", "archive", "chapter 7"}
    joined = "\n".join(_fixture_text(row).casefold() for row in fixtures)
    if any(term in joined for term in banned):
        raise ValueError("Prior S2 subject wording leaked into the holdout")

    plan = build_public_plan()
    if [row["slot_id"] for row in plan] != _ordered_slot_ids():
        raise ValueError("Public/private schedule ordering drifted")
    validate_public_package()
    return {
        "study_id": STUDY_ID,
        "provider_calls": 0,
        "fixtures": 8,
        "sources": 6,
        "activation_controls": 2,
        "slots": 48,
        "labels_sealed_separately": True,
        "p4_only_arm_delta": True,
        "contamination_checks": "passed",
        "promotion": "none",
    }
