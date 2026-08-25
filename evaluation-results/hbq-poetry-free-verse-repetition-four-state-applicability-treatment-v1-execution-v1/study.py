"""Four-state S1 applicability treatment over the proven one-shot lifecycle."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v1"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
ADAPTER_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-clean-na-successor-v1-execution-v1" / "study.py"
ADAPTER_SHA256 = "b06aab5c7f55196118c43c3b9e8ed8a8a3d63c5c1627d86aae268af31b35cd54"
RESULT_PATH = "evaluation-results/hbq-poetry-free-verse-repetition-treatment-v1-execution-v1-public-result-v1"
RESULT_TREE = "b0c41c99632ef63a1df55546703ceb3fb1d116f9"
RESULT_FILES = {
    "README.md": "7b9c889586a0994fba61aa438c422c29cff65cdd",
    "public-result.json": "326968f0e93ca0edc5d21e1846d772b0cb4557d1",
}
CANDIDATE_TEXT = (
    "Answer NOT_APPLICABLE when no recurrence is supplied or indicated, and "
    "CANNOT_ASSESS when recurrence is indicated but too few instances are supplied "
    "to judge its effect. Presence of recurrence alone does not satisfy this criterion. "
    "Answer YES only when sufficient supplied instances show that recurring words, "
    "phrases, or structures change pressure or meaning; when sufficient supplied "
    "instances recur without doing so, answer NO."
)
CANDIDATE_SHA256 = "b8b874772e62965042bc75c8171a933bc3d85e3d785da911019d52cbfd268219"
CONTROLLER_SHA256 = "5bf97d0c69e24b4cba457b89041a91a86b9f28ad06864eebd352cc633c90eb0f"
LEDGER_SHA256 = "5822c683e7f56e6d84d99f34003061512ba5e785d38fcfc77da7761d8f7b7e0a"
VERIFIER_SHA256 = "70236fc9cd5415d9fb2e71390c009ae47de2a187a7a529e77deca5ee1ef1d9ae"
FIXTURE_SHA256 = {
    "absence": "5c1811f83571359374c22b096f4398ace0a52a1a596a829869cbe206f69293b6",
    "accidental_inert_duplicate": "44a108e95424d315de9a3436b783ecf6f62f7781c2265b0bff1b11028edfe6aa",
    "functional_recurrence": "1fbac6de7c697341ad7cfd42b3c43d7098afec7858d188f707bdca0d99ee1000",
    "incomplete_indicated_recurrence": "34c026dff516cf7a4ad792db5335730b331bd5c1e954ffd5797289f230d424f2",
}
PRIVATE_EXECUTION_DIRECTORY = "execution-v1-terminal-sidecar-v1"
SLOTS = 12
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8",
        capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Git binding lookup failed")
    return result.stdout.strip()


@lru_cache(maxsize=1)
def _adapter():
    if not ADAPTER_PATH.is_file() or sha256_file(ADAPTER_PATH) != ADAPTER_SHA256:
        raise ValueError("Frozen S1 lifecycle adapter drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_lifecycle_adapter", ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen S1 lifecycle adapter is unavailable")
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _base():
    adapter = _adapter()
    base = adapter._base()
    _configure(adapter, base)
    return base


def _configure(adapter, base) -> None:
    adapter.ROOT = ROOT
    adapter.REPOSITORY = REPOSITORY
    adapter.STUDY_ID = STUDY_ID
    adapter.SOURCE_COMMIT = SOURCE_COMMIT
    adapter.SOURCE_TREE = SOURCE_TREE
    adapter.CONTROLLER_SHA256 = CONTROLLER_SHA256
    adapter.LEDGER_SHA256 = LEDGER_SHA256
    adapter.VERIFIER_SHA256 = VERIFIER_SHA256
    adapter.FIXTURE_SHA256 = FIXTURE_SHA256
    adapter.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY
    adapter.SLOTS = SLOTS
    adapter.ARMS = ARMS
    adapter.REPEATS = REPEATS
    adapter.BUNDLE_ID = BUNDLE_ID
    adapter.SUCCESSOR_FILES = SUCCESSOR_FILES
    adapter._private_freeze = _private_freeze
    adapter._questions = _questions
    adapter.validate_package = validate_package
    adapter.prepare = prepare
    adapter._verify_prompt_pairs = _verify_prompt_pairs
    adapter._derive_gate = _derive_gate
    adapter._settle = _settle
    adapter._configure(base)
    if not hasattr(base, "_four_state_original_verify_slot"):
        base._four_state_original_verify_slot = base._verify_slot
    if not hasattr(base, "_four_state_original_claim_execution"):
        base._four_state_original_claim_execution = base._claim_execution
    base._private_freeze = _private_freeze
    base._questions = _questions
    base.validate_package = validate_package
    base.prepare = prepare
    base._verify_prompt_pairs = _verify_prompt_pairs
    base._derive_gate = _derive_gate
    base._verify_slot = _verify_slot
    base._claim_execution = _claim_execution
    base.settle = _settle


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    base = _base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = (
        (controller_path, CONTROLLER_SHA256),
        (ledger_path, LEDGER_SHA256),
        (verifier_path, VERIFIER_SHA256),
    )
    if any(not path.is_file() or base.sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private four-state controller, ledger, or verifier drifted")
    controller = base._load_json(controller_path)
    ledger = base._load_json(ledger_path)
    fixtures = controller.get("fixture_matrix")
    mappings = ledger.get("slot_mapping")
    if (
        controller.get("study_id") != STUDY_ID
        or controller.get("format_version") != 1
        or controller.get("visibility") != "private_controller_only"
        or not isinstance(fixtures, list)
        or len(fixtures) != 4
        or not isinstance(mappings, list)
        or len(mappings) != SLOTS
    ):
        raise ValueError("Private four-state geometry drifted")
    expected_states = {
        "absence": "NOT_APPLICABLE",
        "accidental_inert_duplicate": "NO",
        "functional_recurrence": "YES",
        "incomplete_indicated_recurrence": "CANNOT_ASSESS",
    }
    fixture_ids: set[str] = set()
    for fixture in fixtures:
        state = str(fixture.get("state"))
        if (
            expected_states.get(state) != fixture.get("expected_verdict")
            or fixture.get("role") not in {"target", "control"}
            or base.sha256_bytes(str(fixture.get("text")).encode("utf-8")) != FIXTURE_SHA256.get(state)
        ):
            raise ValueError("Private four-state fixture boundary drifted")
        fixture_ids.add(str(fixture.get("fixture_id")))
    expected_geometry = {(fixture_id, "candidate", repeat) for fixture_id in fixture_ids for repeat in REPEATS}
    actual_geometry = {
        (str(item.get("fixture_id")), str(item.get("arm")), int(item.get("repeat")))
        for item in mappings
        if isinstance(item, Mapping)
    }
    if len(fixture_ids) != 4 or actual_geometry != expected_geometry:
        raise ValueError("Private four-state slot mapping drifted")
    if len({item.get("opaque_slot_id") for item in mappings}) != SLOTS:
        raise ValueError("Private four-state opaque identities drifted")
    return controller, ledger


def _questions() -> dict[str, dict[str, Any]]:
    base = _base()
    source = base._source_leaf()
    predecessor = base._predecessor_contract().get("candidate")
    preserved = predecessor.get("preserved_fields") if isinstance(predecessor, Mapping) else None
    if not isinstance(preserved, Mapping):
        raise TypeError("Frozen predecessor leaf fields are unavailable")
    if any(source.get(key) != value for key, value in preserved.items()):
        raise ValueError("Canonical repetition leaf fields drifted")
    source_leaf = {key: source[key] for key in (*preserved, "text")}
    treatment = dict(source_leaf)
    treatment["text"] = CANDIDATE_TEXT
    if base.sha256_bytes(base.canonical_json(source_leaf)) != "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a":
        raise ValueError("Canonical repetition source digest drifted")
    if base.sha256_bytes(base.canonical_json(treatment)) != CANDIDATE_SHA256:
        raise ValueError("Four-state candidate digest drifted")
    return {"candidate": treatment}


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def validate_package() -> dict[str, Any]:
    adapter, base = _adapter(), _base()
    value = contract()
    if (
        value.get("study_id") != STUDY_ID
        or value.get("format_version") != 1
        or value.get("status") != "frozen_unexecuted_candidate_only_four_state_manual_repair"
    ):
        raise ValueError("Four-state contract identity drifted")
    if value.get("source_checkout") != {
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "exact_head_required_before_claim": True,
    }:
        raise ValueError("Four-state source binding drifted")
    if value.get("lifecycle_adapter") != {
        "path": ADAPTER_PATH.relative_to(REPOSITORY).as_posix(),
        "sha256": ADAPTER_SHA256,
    }:
        raise ValueError("Four-state lifecycle adapter binding drifted")
    if value.get("template_executor") != {
        "commit": SOURCE_COMMIT,
        "path": _adapter().TEMPLATE_PATH,
        "blob": _adapter().TEMPLATE_BLOB,
    }:
        raise ValueError("Four-state executor template binding drifted")
    if value.get("predecessor_result") != {
        "commit": SOURCE_COMMIT,
        "tree": RESULT_TREE,
        "path": RESULT_PATH,
        "files": RESULT_FILES,
        "disposition": "immutable_formal_no_go_manual_applicability_successor",
    }:
        raise ValueError("Four-state predecessor lineage drifted")
    if value.get("geometry") != {
        "cells": 4,
        "states": ["NOT_APPLICABLE", "NO", "YES", "CANNOT_ASSESS"],
        "arms": ["candidate"],
        "repeats": 3,
        "slots": 12,
        "one_leaf_per_call": True,
    }:
        raise ValueError("Four-state geometry drifted")
    if value.get("private_commitments") != {
        "controller_sha256": CONTROLLER_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "verifier_sha256": VERIFIER_SHA256,
        "fixture_text_sha256": FIXTURE_SHA256,
    }:
        raise ValueError("Four-state private commitments drifted")
    if value.get("execution") != {
        "route": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "sequence": "strict",
        "batch_size": 1,
        "batch_attempts": 1,
        "maximum_provider_sends": 12,
        "one_physical_attempt_per_slot": True,
        "semantic_retry_or_resume": "forbidden",
        "paid_api_or_fallback_route": "forbidden",
    }:
        raise ValueError("Four-state execution boundary drifted")
    if value.get("evidence_gate") != {
        "grounding": "nonempty_exact_quotes_verbatim_in_supplied_artifact_or_context_only",
        "summary_evidence": "forbidden",
        "normalization_events_required": 0,
    }:
        raise ValueError("Four-state evidence gate drifted")
    if value.get("gating") != {
        "each_cell_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS",
        "all_slots_required": "12/12",
        "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY",
        "invalid_or_incomplete": "no_result",
        "success_authorizes_only": "fresh_disjoint_holdout",
    }:
        raise ValueError("Four-state outcome gate drifted")
    if value.get("promotion") != "none" or value.get("dspy") != "not_implemented_runtime":
        raise ValueError("Four-state promotion or runtime-DSPy boundary drifted")
    candidate = value.get("candidate")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("leaf_id") != base.LEAF_ID
        or candidate.get("text") != CANDIDATE_TEXT
        or candidate.get("source_leaf_sha256") != "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a"
        or candidate.get("candidate_leaf_sha256") != CANDIDATE_SHA256
        or candidate.get("prompt_delta") != "repetition_leaf_text_only"
    ):
        raise ValueError("Four-state candidate binding drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen exact source tree is unavailable")
    if _git("rev-parse", f"{SOURCE_COMMIT}:{RESULT_PATH}") != RESULT_TREE:
        raise ValueError("Frozen predecessor result tree is unavailable")
    for name, blob in RESULT_FILES.items():
        if _git("rev-parse", f"{SOURCE_COMMIT}:{RESULT_PATH}/{name}") != blob:
            raise ValueError("Frozen predecessor result file drifted")
    for path, digest in adapter.RUNTIME_SHA256.items():
        if base.sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    _questions()
    _private_freeze()
    schedule = base.build_schedule()
    if len(schedule) != SLOTS or {slot["arm"] for slot in schedule} != {"candidate"}:
        raise ValueError("Four-state candidate-only schedule drifted")
    return {
        "study_id": STUDY_ID,
        "source_commit": SOURCE_COMMIT,
        "slots": SLOTS,
        "provider_calls": 0,
        "normalization_events_required": 0,
        "success_authorizes_only": "fresh_disjoint_holdout",
    }


def prepare() -> dict[str, Any]:
    base = _base()
    validate_package()
    root, schedule = base._execution_root(), base.build_schedule()
    if base._claim_path(root).exists():
        raise ValueError("Preparation cannot rewrite a claimed root")
    base._write_or_verify(root / "catalog" / "bundles.json", base.canonical_json(base._bundle()))
    base._write_or_verify(base._registry_path(root, "candidate"), base.canonical_json(base._registry("candidate")))
    controller, _ledger = _private_freeze()
    fixtures = {str(item["fixture_id"]): item for item in controller["fixture_matrix"]}
    for fixture_id, fixture in fixtures.items():
        slot = next(item for item in schedule if item["fixture_id"] == fixture_id)
        base._write_or_verify(base._artifact_path(root, slot), str(fixture["text"]).encode("utf-8"))
        task = base._task_contract(fixture)
        base._write_or_verify(base._task_path(root, slot), base.canonical_json(task))
        base._write_or_verify(base._override_path(root, slot), base.canonical_json(base._scope_override(fixture, task)))
        for index, context in enumerate(fixture["contexts"], start=1):
            path = root / "contexts" / base._fixture_token(fixture_id) / f"context-{index:02d}.txt"
            base._write_or_verify(path, str(context).encode("utf-8"))
    base._write_or_verify(root / "private-schedule.json", base.canonical_json({"format_version": 1, "slots": schedule}))
    base._write_prepared_manifest(root / "study-manifest.json", base.canonical_json(base._manifest(schedule)))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _verify_prompt_pairs(
    root: Path,
    schedule: Sequence[Mapping[str, Any]],
    prompts: Mapping[str, bytes],
) -> None:
    del root
    base = _base()
    candidate = CANDIDATE_TEXT.encode("utf-8")
    source = base._source_leaf()["text"].encode("utf-8")
    if len(schedule) != SLOTS or set(prompts) != {str(slot["opaque_slot_id"]) for slot in schedule}:
        raise ValueError("Four-state rendered prompt geometry drifted")
    if any(candidate not in prompts[str(slot["opaque_slot_id"])] for slot in schedule):
        raise ValueError("Four-state candidate wording is absent from a frozen prompt")
    if any(source in prompts[str(slot["opaque_slot_id"])] for slot in schedule):
        raise ValueError("Canonical source wording leaked into a treatment prompt")


def _validate_raw_grounding(
    slot: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    raw: Mapping[str, Any],
) -> int:
    if checkpoint.get("normalization_audit") != []:
        raise ValueError("Normalized evidence cannot settle the four-state screen")
    verdicts = raw.get("verdicts")
    if not isinstance(verdicts, list) or len(verdicts) != 1 or not isinstance(verdicts[0], Mapping):
        raise ValueError("Raw singleton verdict is unavailable")
    verdict = verdicts[0]
    if verdict.get("question_id") != _base().LEAF_ID:
        raise ValueError("Raw singleton question identity drifted")
    evidence = verdict.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("Strict quote evidence is required")
    supplied = [str(slot["artifact_text"]), *(str(value) for value in slot["contexts"])]
    for item in evidence:
        if (
            not isinstance(item, Mapping)
            or item.get("kind") != "exact_quote"
            or not isinstance(item.get("exact_quote"), str)
            or not item["exact_quote"]
            or item.get("summary") is not None
            or not isinstance(item.get("reference"), str)
            or not item["reference"].strip()
            or not any(item["exact_quote"] in source for source in supplied)
        ):
            raise ValueError("Evidence is not a strict verbatim supplied quote")
    return len(evidence)


def _verify_slot(root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    base = _base()
    record = base._four_state_original_verify_slot(root, slot)
    run = root / "runs" / str(slot["opaque_slot_id"])
    checkpoint = base._load_json(run / "responses" / "batch-0001.json")
    raw = base._load_json(run / "responses" / "batch-0001.attempt-0001.message.json")
    quote_count = _validate_raw_grounding(slot, checkpoint, raw)
    raw_verdict = raw["verdicts"][0]["verdict"]
    if raw_verdict != record["verdict"]:
        raise ValueError("Raw and terminal singleton verdicts differ")
    return {**record, "normalization_events": 0, "grounded_exact_quotes": quote_count}


def _claim_execution(root: Path, schedule: Sequence[Mapping[str, Any]]) -> Path:
    if _git("rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("Exact source HEAD is required immediately before execution claim")
    validate_package()
    return _base()._four_state_original_claim_execution(root, schedule)


def _derive_gate(root: Path, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = _base()
    record_path = root / "terminal-slot-records.v1.json"
    base._write_or_verify(record_path, base.canonical_json(list(records)))
    verifier = base._private_paths()[2]
    result = subprocess.run(
        [sys.executable, str(verifier), "--assess-records", str(record_path)],
        cwd=base._controller_root(), text=True, encoding="utf-8",
        capture_output=True, check=False,
    )
    if result.returncode:
        raise ValueError("Private four-state verifier rejected settlement evidence")
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get("decision") not in {
        "HOLDOUT_ELIGIBLE_ON_SUCCESS",
        "NO_GO_DSPY_ELIGIBLE_ONLY",
    }:
        raise ValueError("Private four-state verifier returned an invalid gate")
    return value


def _settle(
    *,
    verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base = _base()
    validate_package()
    root, schedule = base._execution_root(), base._runtime_schedule()
    if base._load_json(root / "receipts" / "zero-charge-acknowledgement.v1.json") != base._zero_charge_receipt():
        raise ValueError("Zero-charge acknowledgement is unavailable or drifted")
    prompts = {
        str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes()
        for slot in schedule
    }
    if base._load_json(root / "receipts" / "preexecution-disclosure.v1.json") != base._disclosure(schedule, prompts):
        raise ValueError("Preexecution disclosure is unavailable or drifted")
    claim = base._require_execution_claim(root, schedule)
    if (root / "settlement.v1.json").exists() or (root / "public-aggregate.v1.json").exists():
        raise ValueError("Original settlement is write-once")
    verify = verifier or _verify_slot
    records = [verify(root, slot) for slot in schedule]
    gate = _derive_gate(root, records)
    settlement = {
        "study_id": STUDY_ID,
        "decision": gate["decision"],
        "completed_slots": SLOTS,
        "planned_slots": SLOTS,
        "matches": gate["matches"],
        "total_matches": gate["total_matches"],
        "normalization_events": 0,
        "promotion": "none",
        "success_authorizes_only": "fresh_disjoint_holdout",
        "records": records,
        "execution_claim_sha256": base.sha256_file(claim),
    }
    public = {
        "study_id": STUDY_ID,
        "decision": gate["decision"],
        "completed_slots": SLOTS,
        "planned_slots": SLOTS,
        "aggregate": {"matches": gate["matches"], "total_matches": gate["total_matches"], "required": 12},
        "normalization_events": 0,
        "promotion": "none",
        "success_authorizes_only": "fresh_disjoint_holdout",
    }
    base._write_terminal(root, settlement, public)
    return settlement


def set_private_root(value: str | Path) -> Path:
    return _base().set_private_root(value)


def build_schedule() -> list[dict[str, Any]]:
    return _base().build_schedule()


def dry_run(
    private_root: str | Path,
    *,
    runner_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    set_private_root(private_root)
    return _base().dry_run(runner_call=runner_call)


def execute(
    private_root: str | Path,
    *,
    allow_remote: bool = False,
    acknowledged_zero_incremental_charge: bool = False,
    runner_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    if not allow_remote:
        raise ValueError("Execution requires explicit allow-remote authority")
    if not acknowledged_zero_incremental_charge:
        raise ValueError("Execution requires explicit zero-incremental-charge acknowledgement")
    set_private_root(private_root)
    return _base().execute(
        acknowledged_zero_incremental_charge=True,
        runner_call=runner_call,
    )


def settle(
    private_root: str | Path,
    *,
    verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    set_private_root(private_root)
    return _settle(verifier=verifier)


def command_for(
    slot: Mapping[str, Any],
    private_root: str | Path,
    *,
    render: bool = False,
) -> list[str]:
    set_private_root(private_root)
    return _base()._command(slot, render=render)
