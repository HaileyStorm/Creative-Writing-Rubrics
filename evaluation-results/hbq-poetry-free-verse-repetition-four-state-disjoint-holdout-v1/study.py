"""Provider-free freeze for the disjoint S1 four-state holdout."""
from __future__ import annotations

import hashlib
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
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-disjoint-holdout-v1"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
LEAF_ID = "form.poetry.free_verse.repetition"
MODULE_ID = "form.poetry.free_verse"
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_disjoint_holdout_v1"
REPEATS = (1, 2, 3)
V10_CONTRACT = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10" / "study-contract.json"
V10_CONTRACT_SHA256 = "157cb3197988dae26b5ab7799b86896fcacbcfd6c17ddd4258fd91c95ed5edc3"
V10_SETTLED_AGGREGATE_SHA256 = "3440c2855761a832345b5d9504f27cb40cc37045de9af0f5e4c49eabc421a632"
CANDIDATE_TEXT = (
    "Answer NOT_APPLICABLE when no recurrence is supplied or indicated, and CANNOT_ASSESS "
    "when recurrence is indicated but too few instances are supplied to judge its effect. "
    "Presence of recurrence alone does not satisfy this criterion. Answer YES only when "
    "sufficient supplied instances show that recurring words, phrases, or structures change "
    "pressure or meaning; when sufficient supplied instances recur without doing so, answer NO."
)
V10_SOURCE_LEAF_SHA256 = "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a"
V10_CANDIDATE_LEAF_SHA256 = "b8b874772e62965042bc75c8171a933bc3d85e3d785da911019d52cbfd268219"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SHA256 = "a72bf60e40f809e2acd89035c76ac3b000032d3d01fa7d8e7235f78a8a73b4fc"
RUNTIME_BINDINGS = {
    "registry/question_index.jsonl": "d89706f0d32b4b8f5393a81d2d2382d58890452a55e0549c5bac77dd2497892a",
    "registry/all_modules.json": "b8c453f7eb86889f2e76b593eb44a6660f9f7cd695dbd6ac3d13b23d3635102b",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "src/hbqrs/runner.py": "81c1dea4bb4146707f48f86c2d6b7eeab2c1bf1f37bbfea81fea61173c2d6fe2",
}
SEALED_OUTCOMES_NAME = "sealed-expected-outcomes.v1.json"
SEALED_OUTCOMES_SHA256 = "7147c80b6f505643d002705cfae6fe4414bc856c6a4da627df1a91677ddccf18"
WORK_ROOT: Path | None = None


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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


def contract() -> dict[str, Any]:
    return load_json(ROOT / "study-contract.json")


def corpus() -> list[dict[str, Any]]:
    value = load_json(ROOT / "public-synthetic-corpus.json").get("cases")
    if not isinstance(value, list):
        raise ValueError("Public synthetic corpus is invalid")
    return value


def sealed_outcomes() -> dict[str, str]:
    if not SEALED_OUTCOMES_SHA256:
        raise ValueError("Sealed-outcomes commitment is not frozen")
    path = execution_root().parent / SEALED_OUTCOMES_NAME
    if not path.is_file() or sha256_file(path) != SEALED_OUTCOMES_SHA256:
        raise ValueError("Sealed expected-outcomes record is unavailable or drifted")
    value = load_json(path).get("expected_states")
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(state, str) for key, state in value.items()):
        raise ValueError("Expected-outcomes geometry is invalid")
    return value


def source_leaf() -> dict[str, Any]:
    for line in (REPOSITORY / "registry" / "question_index.jsonl").read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if value.get("id") == LEAF_ID:
            fields = ("id", "module_id", "criterion_key", "text", "pass_answer", "weight", "question_type", "severity", "applies_when", "evidence_policy")
            return {key: value[key] for key in fields}
    raise ValueError("Canonical S1 leaf is unavailable")


def candidate_leaf() -> dict[str, Any]:
    value = dict(source_leaf())
    value["text"] = CANDIDATE_TEXT
    return value


def _replace_leaf(node: Any) -> bool:
    if isinstance(node, dict):
        if node.get("id") == LEAF_ID:
            node["text"] = CANDIDATE_TEXT
            return True
        return any(_replace_leaf(value) for value in node.values())
    if isinstance(node, list):
        return any(_replace_leaf(value) for value in node)
    return False


def candidate_registry() -> list[dict[str, Any]]:
    modules = json.loads((REPOSITORY / "registry" / "all_modules.json").read_text(encoding="utf-8"))
    copied = json.loads(json.dumps(modules, ensure_ascii=False))
    module = next((row for row in copied if row.get("module_id") == MODULE_ID), None)
    if module is None or not _replace_leaf(module):
        raise ValueError("Candidate leaf was not substituted")
    return [module]


def bundle() -> list[dict[str, Any]]:
    return [{
        "standard": {"id": "HBQ-RS", "version": "1.2.0"},
        "bundle_id": BUNDLE_ID,
        "version": 1,
        "title": "S1 four-state disjoint holdout",
        "module_ids": [MODULE_ID],
        "task_contract_domain_id": "s1-four-state-disjoint-holdout-v1",
        "domains": [{
            "domain_id": "s1-four-state-disjoint-holdout-v1",
            "title": "Free-verse recurrence four-state holdout",
            "points": 1.0,
            "components": [{"module_id": MODULE_ID, "weight": 1.0, "include_question_ids": [LEAF_ID]}],
            "score_mode": "weighted_binary_mean",
        }],
        "penalty_modules": [],
        "hard_gate_policy": {"no_is_invalid": True, "cannot_assess_is_unresolved": True, "not_applicable_requires_condition_or_reason": True, "hard_gates_are_reported_separately": True},
        "coverage_policy": {"minimum_weighted_coverage": 0.0, "below_threshold_status": "PROVISIONAL", "score_interval_required_when_unassessed": True, "whole_work_claims_require_whole_work_evidence": True},
    }]


def slots() -> list[dict[str, Any]]:
    question_hash = sha256_bytes(canonical_json(candidate_leaf()))
    rubric_hash = sha256_bytes(canonical_json(candidate_registry()))
    by_case = {str(row["case_id"]): row for row in corpus()}
    plan = (
        ("q-8f31c2", "s1h-cinder", 2), ("q-1ad7e4", "s1h-amber", 1), ("q-c4b98d", "s1h-drift", 3),
        ("q-72d1fa", "s1h-birch", 2), ("q-95ae36", "s1h-cinder", 1), ("q-3c6fd9", "s1h-amber", 3),
        ("q-e18b54", "s1h-drift", 1), ("q-4f2ca7", "s1h-birch", 3), ("q-b76e10", "s1h-cinder", 3),
        ("q-0d94bc", "s1h-amber", 2), ("q-a53f68", "s1h-drift", 2), ("q-6e29d1", "s1h-birch", 1),
    )
    result = []
    for opaque_slot_id, case_id, repeat in plan:
        row = by_case[case_id]
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID, "question_sha256": question_hash, "prompt_sha256": "0" * 64, "rubric_sha256": rubric_hash}
        result.append({
            "slot_id": opaque_slot_id,
            "case_id": case_id,
            "repeat": repeat,
            "condition": condition,
            "logical_sample_id": logical_sample_id(study_id=STUDY_ID, artifact_id=case_id, artifact_sha256=sha256_bytes(str(row["text"]).encode("utf-8")), condition=condition, repetition=repeat, rubric_revision="1.2.0"),
        })
    if len(result) != 12 or len({row["slot_id"] for row in result}) != 12 or {(str(row["case_id"]), int(row["repeat"])) for row in result} != {(case_id, repeat) for case_id in by_case for repeat in REPEATS}:
        raise ValueError("Opaque shuffled schedule geometry drifted")
    return result


def current_head() -> str:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "CWR HEAD is unavailable")
    return completed.stdout.strip()


def assert_exact_head() -> None:
    if current_head() != SOURCE_HEAD:
        raise ValueError("CWR live HEAD differs from the frozen holdout source head")


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
    return WORK_ROOT / "execution-v1-6ae9ee0"


def expected_contract() -> dict[str, Any]:
    source = source_leaf()
    candidate = candidate_leaf()
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_disjoint_holdout",
        "source_checkout": {"commit": SOURCE_HEAD, "tree": SOURCE_TREE, "exact_head_required_before_claim": True},
        "predecessor_v10": {"study_id": "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10", "contract_sha256": V10_CONTRACT_SHA256, "settled_aggregate_sha256": V10_SETTLED_AGGREGATE_SHA256, "decision": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "result": {"matched": 12, "required": 12}},
        "candidate": {"leaf_id": LEAF_ID, "text": CANDIDATE_TEXT, "source_leaf_sha256": sha256_bytes(canonical_json(source)), "candidate_leaf_sha256": sha256_bytes(canonical_json(candidate)), "unchanged_fields": {key: value for key, value in source.items() if key != "text"}},
        "public_synthetic_geometry": {"cases": 4, "case_ids": [str(row["case_id"]) for row in corpus()], "distinct_expected_states": 4, "repeats_per_case": 3, "slots": 12, "one_leaf_per_call": True, "all_carriers_fresh_public_synthetic": True, "shuffled_opaque_slots": True},
        "sealed_outcomes": {"filename": SEALED_OUTCOMES_NAME, "sha256": SEALED_OUTCOMES_SHA256, "provider_visible": False},
        "production_render": {"prompt_sha256": PROMPT_SHA256, "schema_sha256": SCHEMA_SHA256, "renderer": "hbqrs render-judge with external runtime overlay", "dry_freeze_checks_all_slots": True},
        "execution": {"freeze_provider_calls": 0, "future_model": "gpt-5.6-sol", "future_reasoning": "high", "batch_size": 1, "batch_attempts": 1, "semantic_retry_or_resume": "forbidden", "normalization": "forbidden", "maximum_provider_sends": 12, "paid_or_fallback_route": "forbidden", "unique_sessions_required": True},
        "gate": {"required": "twelve_of_twelve_exact_first_attempt_raw_verdicts", "success_authorizes_only": "INDEPENDENT_PROMOTION_REVIEW", "automatic_promotion": False},
        "promotion": {key: "none" for key in ("prompt", "rubric", "leaf", "owner", "split", "weight", "applicability", "evidence_policy")},
        "dspy": "forbidden_for_this_holdout",
    }


def validate_package() -> dict[str, Any]:
    assert_exact_head()
    if not V10_CONTRACT.is_file() or sha256_file(V10_CONTRACT) != V10_CONTRACT_SHA256:
        raise ValueError("V10 lineage contract drifted")
    for relative, expected in RUNTIME_BINDINGS.items():
        if sha256_file(REPOSITORY / relative) != expected:
            raise ValueError(f"Frozen runtime drifted: {relative}")
    if sha256_file(ROOT / "exact-quote-prompt.md") != PROMPT_SHA256 or sha256_file(ROOT / "exact-quote-response.schema.json") != SCHEMA_SHA256:
        raise ValueError("V10 exact-quote protocol drifted")
    if sha256_bytes(canonical_json(source_leaf())) != V10_SOURCE_LEAF_SHA256 or sha256_bytes(canonical_json(candidate_leaf())) != V10_CANDIDATE_LEAF_SHA256:
        raise ValueError("V10 candidate wording or source leaf drifted")
    if contract() != expected_contract():
        raise ValueError("Holdout contract drifted")
    rows = corpus()
    if len(rows) != 4 or len({str(row.get("case_id")) for row in rows}) != 4 or len(slots()) != 12:
        raise ValueError("Four-state holdout geometry drifted")
    tokens = [token.casefold() for row in rows for token in row.get("carrier_ids", [])]
    prior = ""
    for path in ROOT.parent.glob("hbq-poetry-free-verse-repetition*/public-synthetic-corpus.json"):
        if path.resolve() != (ROOT / "public-synthetic-corpus.json").resolve():
            prior += path.read_text(encoding="utf-8").casefold()
    if len(tokens) != len(set(tokens)) or any(re.search(rf"\b{re.escape(token)}\b", prior) for token in tokens):
        raise ValueError("Public carrier freshness drifted")
    return {"study_id": STUDY_ID, "slots": 12, "provider_calls": 0, "promotion": "none"}


def _task(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"{STUDY_ID}-{slot['slot_id']}", "artifact_id": slot["slot_id"], "context": {"artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied text", "completion_status": "complete", "background": ["Public synthetic S1 four-state disjoint holdout."], "constraints": ["Use only the supplied text as verdict evidence."], "audience": ["development-only rubric validation"]}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["slot_id"], "bundle_id": BUNDLE_ID, "task_contract_sha256": sha256_bytes(canonical_json(task)), "contract_id": task["contract_id"], "artifact_kind": task["context"]["artifact_kind"], "declared_scope": task["context"]["declared_scope"], "compatibility_mode": "reviewed_override", "decision_id": "s1h-v1-scope", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for a public synthetic singleton holdout."}


def _overlay(root: Path) -> Path:
    runtime = root / "runtime-book"
    write_once(runtime / "registry" / "all_modules.json", (REPOSITORY / "registry" / "all_modules.json").read_bytes())
    for source in (REPOSITORY / "schema").glob("*.json"):
        if source.name != "hbq_judge_response.schema.json":
            write_once(runtime / "schema" / source.name, source.read_bytes())
    write_once(runtime / "prompts" / "judge" / "JUDGE_PREFIX.md", (REPOSITORY / "prompts" / "judge" / "JUDGE_PREFIX.md").read_bytes())
    write_once(runtime / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md", (ROOT / "exact-quote-prompt.md").read_bytes())
    write_once(runtime / "schema" / "hbq_judge_response.schema.json", (ROOT / "exact-quote-response.schema.json").read_bytes())
    return runtime


def _command(slot: Mapping[str, Any], root: Path, *, render: bool) -> list[str]:
    catalog = root / "catalog"
    artifact = root / "inputs" / f"{slot['slot_id']}.txt"
    value = [sys.executable, "-m", "hbqrs", "--registry", str(catalog / "candidate-registry.json"), "--bundles", str(catalog / "bundles.json"), "render-judge" if render else "judge"]
    if render:
        value.extend(["--artifact", str(artifact)])
    else:
        value.append(str(artifact))
    value.extend(["--bundle", BUNDLE_ID, "--provider", "codex", "--model", "gpt-5.6-sol", "--strict-ai", "--artifact-id", str(slot["slot_id"]), "--question-id", LEAF_ID, "--task-contract", str(root / "contracts" / f"{slot['slot_id']}.json"), "--scope-compatibility-override", str(root / "overrides" / f"{slot['slot_id']}.json")])
    if render:
        return [*value, "--output", str(root / "rendered-prompts" / f"{slot['slot_id']}.txt")]
    return [*value, "--reasoning", "high", "--batch-size", "1", "--batch-attempts", "1", "--attempt-lifecycle-policy", "terminal_sidecar_v1", "--output-dir", str(root / "runs" / str(slot["slot_id"]))]


def execution_command(slot: Mapping[str, Any]) -> list[str]:
    return _command(slot, execution_root(), render=False)


def assert_rendered_prompt_privacy(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if any(str(row["case_id"]) in text for row in corpus()) or "sealed-expected-outcomes" in text or "expected_states" in text:
        raise ValueError("Rendered prompt contains holdout state or role cues")


def prepare() -> dict[str, Any]:
    validate_package()
    root = execution_root()
    write_once(root / "catalog" / "candidate-registry.json", canonical_json(candidate_registry()))
    write_once(root / "catalog" / "bundles.json", canonical_json(bundle()))
    by_case = {str(row["case_id"]): row for row in corpus()}
    for slot in slots():
        task = _task(slot)
        write_once(root / "inputs" / f"{slot['slot_id']}.txt", str(by_case[str(slot["case_id"])]["text"]).encode("utf-8"))
        write_once(root / "contracts" / f"{slot['slot_id']}.json", canonical_json(task))
        write_once(root / "overrides" / f"{slot['slot_id']}.json", canonical_json(_override(slot, task)))
    _overlay(root)
    return {"execution_root": str(root), "planned_slots": 12, "provider_calls": 0}


def dry_run(runner_call: Any = subprocess.run) -> dict[str, Any]:
    prepared = prepare()
    root = execution_root()
    environment = os.environ.copy()
    environment["HBQRS_ROOT"] = str(root / "runtime-book")
    (root / "rendered-prompts").mkdir(parents=True, exist_ok=True)
    prompt_hashes: dict[str, str] = {}
    for slot in slots():
        completed = runner_call(_command(slot, root, render=True), text=True, encoding="utf-8", capture_output=True, check=False, env=environment)
        if getattr(completed, "returncode", 1):
            raise RuntimeError(f"Provider-free production render failed for {slot['slot_id']}: {getattr(completed, 'stderr', '')}")
        prompt = root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        if not prompt.is_file() or b"exact_quote" not in prompt.read_bytes():
            raise ValueError("Production-rendered exact-quote prompt is unavailable")
        assert_rendered_prompt_privacy(prompt)
        prompt_hashes[str(slot["slot_id"])] = sha256_file(prompt)
    manifest = {"format_version": 1, "study_id": STUDY_ID, "source_head": SOURCE_HEAD, "provider_calls": 0, "planned_slots": 12, "rendered_slots": 12, "rendered_prompt_sha256": prompt_hashes, "production_prompt_sha256": PROMPT_SHA256, "production_schema_sha256": SCHEMA_SHA256, "future_execution": contract()["execution"], "promotion": "none"}
    write_once(root / "dry-manifest.v1.json", canonical_json(manifest))
    return {**prepared, "provider_calls": 0, "rendered_slots": 12, "dry_manifest_sha256": sha256_file(root / "dry-manifest.v1.json")}


def verify_settlement_records(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    schedule = {str(slot["slot_id"]): slot for slot in slots()}
    if len(records) != 12 or {str(row.get("slot_id")) for row in records} != set(schedule):
        raise ValueError("Settlement record geometry drifted")
    sessions: set[str] = set()
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in records:
        slot = schedule[str(row["slot_id"])]
        session = str(row.get("session_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", session) or session in sessions:
            raise ValueError("Provider session must be unique and committed")
        sessions.add(session)
        if row.get("accepted_attempt") != 1 or row.get("rejected_retries") != 0 or row.get("normalization_events") != 0 or row.get("exact_quote_valid") is not True:
            raise ValueError("Holdout requires one accepted exact-quote-valid first attempt per slot")
        grouped[str(slot["case_id"])].append(str(row.get("raw_verdict")))
    expected = sealed_outcomes()
    if set(grouped) != set(expected) or any(len(values) != 3 for values in grouped.values()):
        raise ValueError("Four-state settlement cell geometry drifted")
    matched = all(values == [expected[case_id]] * 3 for case_id, values in grouped.items())
    return {"study_id": STUDY_ID, "decision": "INDEPENDENT_PROMOTION_REVIEW_ELIGIBLE" if matched else "NO_GO", "completed_slots": 12, "promotion": "none", "automatic_promotion": False}
