"""Provider-free v2 successor for the S1 four-state disjoint holdout."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from hbqrs.study_identity import logical_sample_id


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v2"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
LEAF_ID = "form.poetry.free_verse.repetition"
MODULE_ID = "form.poetry.free_verse"
BUNDLE_ID = "poetry_free_verse_repetition_singleton_v2"
REPEATS = (1, 2, 3)
V1_ROOT = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1"
V1_STUDY_SHA256 = "58ec8a7646a653f9fcfa1e21b2e7c203b20d49764271964da9053167dcdd2e87"
V1_CONTRACT_SHA256 = "463e297dc0c9707a0d3503f6afb14e44ad44a1b8982da258b6295be2ba74bf8f"
CANDIDATE_TEXT = (
    "Answer NOT_APPLICABLE when no recurrence is supplied or indicated, and CANNOT_ASSESS "
    "when recurrence is indicated but too few instances are supplied to judge its effect. "
    "Presence of recurrence alone does not satisfy this criterion. Answer YES only when "
    "sufficient supplied instances show that recurring words, phrases, or structures change "
    "pressure or meaning; when sufficient supplied instances recur without doing so, answer NO."
)
SOURCE_LEAF_SHA256 = "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a"
CANDIDATE_LEAF_SHA256 = "b8b874772e62965042bc75c8171a933bc3d85e3d785da911019d52cbfd268219"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SHA256 = "a72bf60e40f809e2acd89035c76ac3b000032d3d01fa7d8e7235f78a8a73b4fc"
RUNTIME_BINDINGS = {
    "registry/question_index.jsonl": "d89706f0d32b4b8f5393a81d2d2382d58890452a55e0549c5bac77dd2497892a",
    "registry/all_modules.json": "b8c453f7eb86889f2e76b593eb44a6660f9f7cd695dbd6ac3d13b23d3635102b",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
}
SEALED_OUTCOMES_NAME = "sealed-outcomes.v2.json"
SEALED_OUTCOMES_SHA256 = "fead2cb67c5a346a4f65663d056c045f0591743744642689b23b573e81d79867"
WORK_ROOT: Path | None = None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def write_once(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Frozen artifact drifted: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _v1() -> Any:
    study = V1_ROOT / "study.py"
    contract = V1_ROOT / "study-contract.json"
    if not study.is_file() or sha256_file(study) != V1_STUDY_SHA256 or not contract.is_file() or sha256_file(contract) != V1_CONTRACT_SHA256:
        raise ValueError("V1 freeze lineage drifted")
    spec = importlib.util.spec_from_file_location("s1_holdout_v1_bound", study)
    if spec is None or spec.loader is None:
        raise ValueError("V1 freeze is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def corpus() -> list[dict[str, Any]]:
    source = load_json(ROOT / "public-synthetic-corpus.json")
    retained = source.get("retained_predecessor_case_ids")
    replacement = source.get("replacement_case")
    if not isinstance(retained, list) or not isinstance(replacement, dict):
        raise ValueError("Public corpus is invalid")
    inherited = {str(row["case_id"]): row for row in _v1().corpus()}
    if set(map(str, retained)) != {"s1h-amber", "s1h-cinder", "s1h-drift"} or any(case_id not in inherited for case_id in retained):
        raise ValueError("Retained predecessor carrier binding drifted")
    return [inherited[str(case_id)] for case_id in retained] + [replacement]


def source_leaf() -> dict[str, Any]:
    return _v1().source_leaf()


def candidate_leaf() -> dict[str, Any]:
    value = dict(source_leaf())
    value["text"] = CANDIDATE_TEXT
    return value


def candidate_registry() -> list[dict[str, Any]]:
    return _v1().candidate_registry()


def bundle() -> list[dict[str, Any]]:
    return [{
        "standard": {"id": "HBQ-RS", "version": "1.2.0"}, "bundle_id": BUNDLE_ID, "version": 2,
        "title": "Free verse recurrence", "module_ids": [MODULE_ID], "task_contract_domain_id": "recurrence-v2",
        "domains": [{"domain_id": "recurrence-v2", "title": "Free verse recurrence", "points": 1.0, "components": [{"module_id": MODULE_ID, "weight": 1.0, "include_question_ids": [LEAF_ID]}], "score_mode": "weighted_binary_mean"}],
        "penalty_modules": [],
        "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
    }]


def slots() -> list[dict[str, Any]]:
    by_case = {str(row["case_id"]): row for row in corpus()}
    plan = (
        ("q-46ac81", "s1h-cinder", 2), ("q-19d5ef", "s1h-amber", 1), ("q-b72f04", "s1h-drift", 3),
        ("q-6e93ba", "s1h-garnet", 2), ("q-c18d75", "s1h-cinder", 1), ("q-3af260", "s1h-amber", 3),
        ("q-9bd41e", "s1h-drift", 1), ("q-52e8c7", "s1h-garnet", 3), ("q-f06a39", "s1h-cinder", 3),
        ("q-7c15db", "s1h-amber", 2), ("q-a84e62", "s1h-drift", 2), ("q-2f79c4", "s1h-garnet", 1),
    )
    question_hash = sha256_bytes(canonical_json(candidate_leaf()))
    rubric_hash = sha256_bytes(canonical_json(candidate_registry()))
    result = []
    for slot_id, case_id, repeat in plan:
        row = by_case[case_id]
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID, "question_sha256": question_hash, "prompt_sha256": "0" * 64, "rubric_sha256": rubric_hash}
        result.append({"slot_id": slot_id, "case_id": case_id, "repeat": repeat, "condition": condition, "logical_sample_id": logical_sample_id(study_id=STUDY_ID, artifact_id=case_id, artifact_sha256=sha256_bytes(str(row["text"]).encode("utf-8")), condition=condition, repetition=repeat, rubric_revision="1.2.0")})
    if len(result) != 12 or len({row["slot_id"] for row in result}) != 12 or {(str(row["case_id"]), int(row["repeat"])) for row in result} != {(case_id, repeat) for case_id in by_case for repeat in REPEATS}:
        raise ValueError("Shuffled opaque schedule drifted")
    return result


def current_head() -> str:
    value = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if value.returncode:
        raise ValueError(value.stderr.strip() or "CWR HEAD is unavailable")
    return value.stdout.strip()


def assert_exact_head() -> None:
    if current_head() != SOURCE_HEAD:
        raise ValueError("CWR live HEAD differs from the frozen v2 source head")


def set_work_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("External work root must be outside the CWR checkout")
    global WORK_ROOT
    WORK_ROOT = root
    return root


def execution_root() -> Path:
    if WORK_ROOT is None:
        raise ValueError("An explicit external work root is required")
    return WORK_ROOT / "execution-v2-6ae9ee0"


def sealed_outcomes() -> dict[str, str]:
    path = execution_root().parent / SEALED_OUTCOMES_NAME
    if not SEALED_OUTCOMES_SHA256 or not path.is_file() or sha256_file(path) != SEALED_OUTCOMES_SHA256:
        raise ValueError("Sealed v2 outcomes are unavailable or drifted")
    value = load_json(path).get("outcomes")
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(state, str) for key, state in value.items()):
        raise ValueError("Sealed v2 outcomes are invalid")
    return value


def expected_contract() -> dict[str, Any]:
    source, candidate = source_leaf(), candidate_leaf()
    return {
        "format_version": 2, "study_id": STUDY_ID, "status": "frozen_provider_free_carrier_repair_successor",
        "source_checkout": {"commit": SOURCE_HEAD, "tree": SOURCE_TREE, "exact_head_required_before_claim": True},
        "predecessor_v1": {"study_id": "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1", "study_sha256": V1_STUDY_SHA256, "contract_sha256": V1_CONTRACT_SHA256, "repair_scope": "one_public_carrier_replacement", "replaced_case_id": "s1h-birch", "replacement_case_id": "s1h-garnet", "external_evidence_immutable": True},
        "candidate": {"leaf_id": LEAF_ID, "text": CANDIDATE_TEXT, "source_leaf_sha256": sha256_bytes(canonical_json(source)), "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)), "unchanged_fields": {key: value for key, value in source.items() if key != "text"}},
        "public_synthetic_geometry": {"cases": 4, "retained_v1_carriers": 3, "replaced_v1_carriers": 1, "repeats_per_case": 3, "slots": 12, "one_leaf_per_call": True, "shuffled_opaque_slots": True},
        "sealed_outcomes": {"filename": SEALED_OUTCOMES_NAME, "sha256": SEALED_OUTCOMES_SHA256, "provider_visible": False},
        "production_render": {"prompt_sha256": PROMPT_SHA256, "schema_sha256": SCHEMA_SHA256, "renderer": "hbqrs render-judge with external runtime overlay", "rendered_prompt_role_cues_forbidden": True},
        "execution": {"freeze_provider_calls": 0, "future_model": "gpt-5.6-sol", "future_reasoning": "high", "batch_size": 1, "batch_attempts": 1, "semantic_retry_or_resume": "forbidden", "normalization": "forbidden", "maximum_provider_sends": 12, "paid_or_fallback_route": "forbidden", "unique_sessions_required": True, "execution_entrypoint": "unavailable_until_independent_review"},
        "gate": {"required": "twelve_of_twelve_exact_first_attempt_raw_verdicts", "success_authorizes_only": "INDEPENDENT_PROMOTION_REVIEW", "automatic_promotion": False},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "owner", "split", "weight", "applicability", "evidence_policy")}, "dspy": "forbidden_for_this_holdout",
    }


def validate_package() -> dict[str, Any]:
    assert_exact_head(); _v1()
    for relative, expected in RUNTIME_BINDINGS.items():
        if sha256_file(REPOSITORY / relative) != expected:
            raise ValueError(f"Frozen runtime drifted: {relative}")
    if sha256_file(ROOT / "exact-quote-prompt.md") != PROMPT_SHA256 or sha256_file(ROOT / "exact-quote-response.schema.json") != SCHEMA_SHA256:
        raise ValueError("Exact-quote protocol drifted")
    if sha256_bytes(canonical_json(source_leaf())) != SOURCE_LEAF_SHA256 or sha256_bytes(canonical_json(candidate_leaf())) != CANDIDATE_LEAF_SHA256:
        raise ValueError("Candidate wording drifted")
    if contract() != expected_contract():
        raise ValueError("V2 contract drifted")
    rows = corpus()
    v1_rows = {str(row["case_id"]): row for row in _v1().corpus()}
    by_case = {str(row["case_id"]): row for row in rows}
    if len(rows) != 4 or set(by_case) != {"s1h-amber", "s1h-garnet", "s1h-cinder", "s1h-drift"} or len(slots()) != 12:
        raise ValueError("V2 carrier geometry drifted")
    if any(by_case[case_id] != v1_rows[case_id] for case_id in ("s1h-amber", "s1h-cinder", "s1h-drift")):
        raise ValueError("V2 changed more than its one permitted carrier")
    new_tokens = [str(token).casefold() for token in by_case["s1h-garnet"].get("carrier_ids", [])]
    prior = "\n".join(path.read_text(encoding="utf-8").casefold() for path in ROOT.parent.glob("hbq-poetry-free-verse-repetition*/public-synthetic-corpus.json") if path.resolve() != (ROOT / "public-synthetic-corpus.json").resolve())
    if len(new_tokens) != len(set(new_tokens)) or any(re.search(rf"\b{re.escape(token)}\b", prior) for token in new_tokens):
        raise ValueError("Replacement carrier freshness drifted")
    return {"study_id": STUDY_ID, "slots": 12, "provider_calls": 0, "promotion": "none"}


def task(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"record-{slot['slot_id']}", "artifact_id": slot["slot_id"], "context": {"artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied text", "completion_status": "complete", "background": [], "constraints": ["Use only the supplied text as verdict evidence."], "audience": []}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def override(slot: Mapping[str, Any], task_value: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["slot_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task_value)), "contract_id": task_value["contract_id"], "artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied text", "compatibility_mode": "reviewed_override", "decision_id": "singleton-compatibility-v2", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for a supplied text."}


def overlay(root: Path) -> None:
    runtime = root / "runtime-book"
    write_once(runtime / "registry" / "all_modules.json", (REPOSITORY / "registry" / "all_modules.json").read_bytes())
    for source in (REPOSITORY / "schema").glob("*.json"):
        if source.name != "hbq_judge_response.schema.json":
            write_once(runtime / "schema" / source.name, source.read_bytes())
    write_once(runtime / "schema" / "hbq_judge_response.schema.json", (ROOT / "exact-quote-response.schema.json").read_bytes())
    write_once(runtime / "prompts" / "judge" / "JUDGE_PREFIX.md", (REPOSITORY / "prompts" / "judge" / "JUDGE_PREFIX.md").read_bytes())
    write_once(runtime / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md", (ROOT / "exact-quote-prompt.md").read_bytes())


def render_command(slot: Mapping[str, Any], root: Path) -> list[str]:
    return [sys.executable, "-m", "hbqrs", "--registry", str(root / "catalog" / "candidate-registry.json"), "--bundles", str(root / "catalog" / "bundles.json"), "render-judge", "--artifact", str(root / "inputs" / f"{slot['slot_id']}.txt"), "--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["slot_id"]), "--question-id", LEAF_ID, "--task-contract", str(root / "contracts" / f"{slot['slot_id']}.json"), "--scope-compatibility-override", str(root / "overrides" / f"{slot['slot_id']}.json"), "--output", str(root / "rendered-prompts" / f"{slot['slot_id']}.txt")]


def assert_prompt_privacy(path: Path) -> None:
    text = path.read_text(encoding="utf-8").casefold()
    banned = ("holdout", "four-state", "four state", "development", "validation", "expected_states", "oracle", STUDY_ID.casefold(), *(str(row["case_id"]).casefold() for row in corpus()))
    if any(token in text for token in banned):
        raise ValueError("Rendered prompt contains a provider-facing study-role cue")


def prepare() -> dict[str, Any]:
    validate_package()
    root = execution_root(); by_case = {str(row["case_id"]): row for row in corpus()}
    write_once(root / "catalog" / "candidate-registry.json", canonical_json(candidate_registry()))
    write_once(root / "catalog" / "bundles.json", canonical_json(bundle()))
    for slot in slots():
        value = task(slot)
        write_once(root / "inputs" / f"{slot['slot_id']}.txt", str(by_case[str(slot["case_id"])]["text"]).encode("utf-8"))
        write_once(root / "contracts" / f"{slot['slot_id']}.json", canonical_json(value))
        write_once(root / "overrides" / f"{slot['slot_id']}.json", canonical_json(override(slot, value)))
    overlay(root)
    return {"execution_root": str(root), "planned_slots": 12, "provider_calls": 0}


def dry_run(runner_call: Any = subprocess.run) -> dict[str, Any]:
    prepared = prepare(); root = execution_root(); (root / "rendered-prompts").mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy(); environment["HBQRS_ROOT"] = str(root / "runtime-book")
    hashes: dict[str, str] = {}
    for slot in slots():
        completed = runner_call(render_command(slot, root), text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(completed, "returncode", 1):
            raise RuntimeError(f"Provider-free production render failed for {slot['slot_id']}: {getattr(completed, 'stderr', '')}")
        path = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if not path.is_file() or b"exact_quote" not in path.read_bytes():
            raise ValueError("Exact-quote prompt is unavailable")
        assert_prompt_privacy(path); hashes[str(slot["slot_id"])] = sha256_file(path)
    manifest = {"format_version": 2, "study_id": STUDY_ID, "source_head": SOURCE_HEAD, "provider_calls": 0, "planned_slots": 12, "rendered_slots": 12, "rendered_prompt_sha256": hashes, "production_prompt_sha256": PROMPT_SHA256, "production_schema_sha256": SCHEMA_SHA256, "execution_entrypoint": "unavailable_until_independent_review", "promotion": "none"}
    write_once(root / "dry-manifest.v2.json", canonical_json(manifest))
    return {**prepared, "provider_calls": 0, "rendered_slots": 12, "dry_manifest_sha256": sha256_file(root / "dry-manifest.v2.json")}


def verify_settlement_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    schedule = {str(slot["slot_id"]): slot for slot in slots()}
    if len(records) != 12 or {str(row.get("slot_id")) for row in records} != set(schedule):
        raise ValueError("Settlement record geometry drifted")
    sessions: set[str] = set(); grouped: dict[str, list[str]] = defaultdict(list)
    for row in records:
        session = str(row.get("session_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", session) or session in sessions:
            raise ValueError("Provider session must be unique and committed")
        sessions.add(session)
        if row.get("accepted_attempt") != 1 or row.get("rejected_retries") != 0 or row.get("normalization_events") != 0 or row.get("exact_quote_valid") is not True:
            raise ValueError("Holdout requires one accepted exact-quote-valid first attempt per slot")
        grouped[str(schedule[str(row["slot_id"])]["case_id"])].append(str(row.get("raw_verdict")))
    outcomes = sealed_outcomes()
    if set(grouped) != set(outcomes) or any(len(values) != 3 for values in grouped.values()):
        raise ValueError("Four-state settlement cell geometry drifted")
    matched = all(values == [outcomes[case_id]] * 3 for case_id, values in grouped.items())
    return {"study_id": STUDY_ID, "decision": "INDEPENDENT_PROMOTION_REVIEW_ELIGIBLE" if matched else "NO_GO", "completed_slots": 12, "promotion": "none", "automatic_promotion": False}
