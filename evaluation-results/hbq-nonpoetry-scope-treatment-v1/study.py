"""Provider-free plan and verifier for the S2 wording/evidence-scope treatment."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-nonpoetry-scope-treatment-v1"
PREDECESSOR_ID = "hbq-nonpoetry-scope-sentinel-v1-execution-v1"
LEAVES = (
    "craft.narrative.character_arc.end_state",
    "data.eval.evaluation_determinism.rerun",
    "modifier.genre.hybrid_or_genre_blend.tone",
    "op.critique.single_unit_critique.no_whole_claims",
    "scope.passage.status",
)
STATES = ("localized_issue", "material_failure", "missing_required_evidence", "activation_mismatch")
STATUS_CANDIDATE = "When a passage is explicitly an excerpt or fragment, does the evaluation exempt it from whole-work completeness requirements?"
REUSE_ORDINALS = {"material_failure": 18, "activation_mismatch": 20}
CORRECTED_FIXTURE_IDS = ("npsst-tone-local", "npsst-tone-unknown", "npsst-critique-unknown", "npsst-passage-local", "npsst-passage-unknown")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(name: str) -> dict[str, Any]:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def predecessor_corpus() -> dict[str, Any]:
    return json.loads((REPOSITORY / "evaluation-results" / "hbq-nonpoetry-scope-sentinel-v1" / "public-synthetic-corpus.json").read_text(encoding="utf-8"))


def source_leaf(leaf_id: str) -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("id") == leaf_id:
            return {key: row[key] for key in ("id", "module_id", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity")}
    raise ValueError(f"Canonical {leaf_id} leaf is unavailable")


def source_status_leaf() -> dict[str, Any]:
    return source_leaf("scope.passage.status")


def artifacts_by_key() -> dict[tuple[str, str], dict[str, Any]]:
    artifacts = predecessor_corpus()["artifacts"]
    rows = {(item["leaf_id"], item["state"]): dict(item) for item in artifacts}
    if len(rows) != 20:
        raise ValueError("Predecessor corpus geometry drifted")
    return rows


def corrected_fixtures() -> dict[str, dict[str, Any]]:
    originals = artifacts_by_key()
    tone_local = dict(originals[("modifier.genre.hybrid_or_genre_blend.tone", "localized_issue")])
    tone_local.update({
        "fixture_id": "npsst-tone-local",
        "text": "The comic detective narrator follows the keeper into the lighthouse. When the bell stops, the jokes shorten into watchful dread; the keeper's earlier warning makes that performed shift legible. Revision note: tighten one transition sentence.",
        "contexts": ["The complete synthetic story explicitly activates detective-comedy and gothic modes, and supplies the performed transition between them."],
    })
    tone_unknown = dict(originals[("modifier.genre.hybrid_or_genre_blend.tone", "missing_required_evidence")])
    tone_unknown.update({
        "fixture_id": "npsst-tone-unknown",
        "text": "The comic detective enters the gothic lighthouse after the bell stops. The supplied record gives no performed transition, bridge, or relation between the two activated modes.",
        "contexts": ["Detective-comedy and gothic modes are explicitly active, but the supplied material withholds transition evidence."],
    })
    critique_unknown = dict(originals[("op.critique.single_unit_critique.no_whole_claims", "missing_required_evidence")])
    critique_unknown.update({
        "fixture_id": "npsst-critique-unknown",
        "text": "The scene's delayed reveal may need a clearer local cue. The report also says the entire manuscript may be repetitive, but it does not disclose whether supporting manuscript-wide evidence was available to the critic.",
        "contexts": ["Supplied unit: one scene only. The availability and content of any wider manuscript evidence are unknown."],
    })
    passage_local = dict(originals[("scope.passage.status", "localized_issue")])
    passage_local.update({
        "fixture_id": "npsst-passage-local",
        "text": "EXCERPT — Chapter 7. Lio enters the archive after the prior chase. The evaluator explicitly exempts this declared fragment from whole-work completeness requirements. Revision note: clarify the chapter heading.",
        "contexts": ["This supplied synthetic passage is explicitly a fragment from a larger novel, not a complete work. The supplied evaluation disposition exempts it from whole-work completeness requirements."],
    })
    passage_unknown = dict(originals[("scope.passage.status", "missing_required_evidence")])
    passage_unknown.update({
        "fixture_id": "npsst-passage-unknown",
        "declared_scope": "excerpt from a novel",
        "text": "EXCERPT — Chapter 7. Lio opens a door in the archive after the prior chase. The record does not state whether the evaluation exempts this declared excerpt from whole-work completeness requirements.",
        "contexts": ["This supplied synthetic passage is explicitly an excerpt from a larger novel. The evaluation disposition about whole-work completeness is unknown."],
    })
    return {item["fixture_id"]: item for item in (tone_local, tone_unknown, critique_unknown, passage_local, passage_unknown)}


def _artifact(leaf: str, state: str) -> tuple[dict[str, Any], str]:
    corrected = corrected_fixtures()
    fixture_for = {
        ("modifier.genre.hybrid_or_genre_blend.tone", "localized_issue"): "npsst-tone-local",
        ("modifier.genre.hybrid_or_genre_blend.tone", "missing_required_evidence"): "npsst-tone-unknown",
        ("op.critique.single_unit_critique.no_whole_claims", "missing_required_evidence"): "npsst-critique-unknown",
        ("scope.passage.status", "localized_issue"): "npsst-passage-local",
        ("scope.passage.status", "missing_required_evidence"): "npsst-passage-unknown",
    }.get((leaf, state))
    if fixture_for:
        return corrected[fixture_for], fixture_for
    return artifacts_by_key()[(leaf, state)], "predecessor-public-fixture"


def _slot(slot_id: str, leaf: str, state: str, arm: str, repeat: int, *, reused: bool) -> dict[str, Any]:
    artifact, fixture_id = _artifact(leaf, state)
    question = source_leaf(leaf)
    rendered_question = dict(question)
    if arm == "candidate_wording":
        rendered_question["text"] = STATUS_CANDIDATE
    item = {
        "slot_id": slot_id,
        "leaf_id": leaf,
        "state": state,
        "arm": arm,
        "repeat": repeat,
        "fixture_id": fixture_id,
        "artifact_sha256": sha256_bytes(canonical_json(artifact)),
        "expected_verdict": {"localized_issue": "YES", "material_failure": "NO", "missing_required_evidence": "CANNOT_ASSESS", "activation_mismatch": "NOT_APPLICABLE"}[state],
        "question": rendered_question,
    }
    if reused:
        ordinal = REUSE_ORDINALS[state]
        item["reuse"] = {
            "predecessor_study_id": PREDECESSOR_ID,
            "predecessor_slot_id": f"npssexec-v1-{ordinal:02d}-r{repeat}",
            "immutable_condition": "same public fixture bytes, current production wording, source leaf, and singleton route; only those six accepted calls may be reused",
        }
    return item


def build_plan() -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for state in REUSE_ORDINALS:
        for repeat in range(1, 4):
            plan.append(_slot(f"npsst-v1-reuse-{state}-r{repeat}", "scope.passage.status", state, "current_wording", repeat, reused=True))
    for state, name in (("localized_issue", "local"), ("missing_required_evidence", "unknown")):
        for repeat in range(1, 4):
            plan.append(_slot(f"npsst-v1-current-passage-{name}-r{repeat}", "scope.passage.status", state, "current_wording", repeat, reused=False))
    for state in STATES:
        for repeat in range(1, 4):
            plan.append(_slot(f"npsst-v1-candidate-passage-{state}-r{repeat}", "scope.passage.status", state, "candidate_wording", repeat, reused=False))
    for leaf, state, name in (
        ("modifier.genre.hybrid_or_genre_blend.tone", "localized_issue", "tone-local"),
        ("modifier.genre.hybrid_or_genre_blend.tone", "missing_required_evidence", "tone-unknown"),
        ("op.critique.single_unit_critique.no_whole_claims", "missing_required_evidence", "critique-unknown"),
    ):
        for repeat in range(1, 4):
            plan.append(_slot(f"npsst-v1-current-{name}-r{repeat}", leaf, state, "current_wording", repeat, reused=False))
    return plan


def validate_holdout(contract: Mapping[str, Any]) -> None:
    expected = {
        "format_version": 1,
        "holdout_id": "hbq-nonpoetry-scope-treatment-v1-private-four-state-holdout",
        "status": "sealed_before_execution",
        "visibility": "private_external_only",
        "states": list(STATES),
        "repeats": 3,
        "content_policy": "No holdout prose, private path, model output, or receipt is stored in this public package.",
        "release_gate": "A separate execution successor may reveal the external holdout only after this development treatment is settled and an independent review approves the candidate wording.",
    }
    if dict(contract) != expected:
        raise ValueError("Private holdout contract drifted")


def validate_package() -> dict[str, Any]:
    contract = load_json("study-contract.json")
    holdout = load_json("private-four-state-holdout-contract.json")
    required = {"format_version", "study_id", "status", "development_only", "provider_execution", "candidate", "geometry", "reuse", "corrections", "promotion", "bindings", "holdout_contract"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != STUDY_ID:
        raise ValueError("Treatment contract identity drifted")
    if contract["status"] != "frozen_provider_free_manual_wording_and_evidence_scope_treatment" or contract["development_only"] is not True:
        raise ValueError("Treatment status drifted")
    if contract["provider_execution"] != {"permitted": False, "new_provider_calls_exact": 27, "reused_accepted_calls_exact": 6, "one_leaf_per_request": True}:
        raise ValueError("Provider boundary or call geometry drifted")
    source = source_status_leaf()
    candidate = dict(source); candidate["text"] = STATUS_CANDIDATE
    if contract["candidate"] != {"leaf_id": "scope.passage.status", "source_leaf_sha256": sha256_bytes(canonical_json(source)), "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)), "preserved_fields": {key: source[key] for key in ("id", "module_id", "criterion_key", "pass_answer", "weight", "question_type", "severity")}}:
        raise ValueError("Candidate wording must preserve the source leaf identity and influence")
    if contract["geometry"] != {"planned_slots_exact": 33, "new_slots_exact": 27, "reused_slots_exact": 6, "status_comparison_new_slots_exact": 18, "corrected_nonpassage_diagnostic_slots_exact": 9, "repeats": 3}:
        raise ValueError("Treatment geometry drifted")
    if contract["reuse"] != {"permitted_states": ["material_failure", "activation_mismatch"], "forbidden_states": ["localized_issue", "missing_required_evidence"], "predecessor_study_id": PREDECESSOR_ID, "binding_rule": "Reuse only the six accepted predecessor calls whose public fixture and current-wording prompt inputs are byte-identical."}:
        raise ValueError("Immutable reuse boundary drifted")
    if contract["corrections"] != list(CORRECTED_FIXTURE_IDS):
        raise ValueError("Exact corrected fixture set drifted")
    if contract["promotion"] != {key: "none" for key in ("prompt", "rubric", "leaf", "ownership", "split", "weight")}:
        raise ValueError("Promotion boundary drifted")
    if contract["bindings"] != {"predecessor_corpus_sha256": sha256_file(REPOSITORY / "evaluation-results" / "hbq-nonpoetry-scope-sentinel-v1" / "public-synthetic-corpus.json"), "source_question_index_sha256": sha256_file(REPOSITORY / "registry" / "question_index.jsonl"), "holdout_contract_sha256": sha256_file(ROOT / "private-four-state-holdout-contract.json")}:
        raise ValueError("Source binding drifted")
    if contract["holdout_contract"] != "private-four-state-holdout-contract.json":
        raise ValueError("Holdout binding drifted")
    validate_holdout(holdout)
    fixtures = corrected_fixtures()
    if tuple(fixtures) != CORRECTED_FIXTURE_IDS:
        raise ValueError("Corrected fixtures drifted")
    plan = build_plan()
    if len(plan) != 33 or len({item["slot_id"] for item in plan}) != 33:
        raise ValueError("Plan identity drifted")
    reuse = [item for item in plan if "reuse" in item]
    new = [item for item in plan if "reuse" not in item]
    if len(reuse) != 6 or len(new) != 27 or {item["state"] for item in reuse} != set(REUSE_ORDINALS):
        raise ValueError("Reuse plan drifted")
    if any(item["reuse"]["immutable_condition"] != "same public fixture bytes, current production wording, source leaf, and singleton route; only those six accepted calls may be reused" for item in reuse):
        raise ValueError("Immutable reuse condition drifted")
    if sum(item["leaf_id"] == "scope.passage.status" for item in new) != 18 or sum(item["leaf_id"] != "scope.passage.status" for item in new) != 9:
        raise ValueError("New-call treatment partition drifted")
    if any(item["question"]["id"] != item["leaf_id"] for item in plan):
        raise ValueError("Question identity drifted")
    return {"study_id": STUDY_ID, "provider_calls": 0, "new_provider_calls_planned": 27, "reused_accepted_calls": 6, "sealed_private_holdout": True}


def render_plan() -> dict[str, str]:
    validate_package()
    return {item["slot_id"]: "\n".join((f"Question ID: {item['question']['id']}", f"Question: {item['question']['text']}", f"State: {item['state']}", f"Expected verdict: {item['expected_verdict']}")) for item in build_plan()}
