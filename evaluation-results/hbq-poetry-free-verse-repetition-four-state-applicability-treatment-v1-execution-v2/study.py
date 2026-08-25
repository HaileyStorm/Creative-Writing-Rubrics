"""Opaque-identifier v2 successor for the S1 four-state treatment."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V1_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v1" / "study.py"
V1_SHA256 = "851054aa510614c3c66a6b0bdaab0e978edea3bb049a8dad9b852ff55b3d9c9a"
CANDIDATE_TEXT = (
    "Answer NOT_APPLICABLE when no recurrence is supplied or indicated, and "
    "CANNOT_ASSESS when recurrence is indicated but too few instances are supplied "
    "to judge its effect. Presence of recurrence alone does not satisfy this criterion. "
    "Answer YES only when sufficient supplied instances show that recurring words, "
    "phrases, or structures change pressure or meaning; when sufficient supplied "
    "instances recur without doing so, answer NO."
)
CONTROLLER_SHA256 = "0eb61a86301e767adcd86dab0cc486e5723a6d76dd6f75a1289d1bab6e7f1871"
LEDGER_SHA256 = "ae51563f8caf9728b3fb7baac6a1330697384c0db7150756373330859bca6332"
VERIFIER_SHA256 = "812c37ab144ce442b2cd9d541e58969d30de91657467694d21af24b450f15a53"
FIXTURE_SHA256 = {
    "1fbac6de7c697341ad7cfd42b3c43d7098afec7858d188f707bdca0d99ee1000",
    "34c026dff516cf7a4ad792db5335730b331bd5c1e954ffd5797289f230d424f2",
    "44a108e95424d315de9a3436b783ecf6f62f7781c2265b0bff1b11028edfe6aa",
    "5c1811f83571359374c22b096f4398ace0a52a1a596a829869cbe206f69293b6",
}
PRIVATE_EXECUTION_DIRECTORY = "execution-v2-terminal-sidecar-v1"
SLOTS = 12
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v2"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json")
OPAQUE_ARTIFACT = re.compile(r"^a-[0-9a-f]{12}$")
OPAQUE_SLOT = re.compile(r"^q-[0-9a-f]{12}$")
ORACLE_MARKERS = (
    "expected_verdict",
    "expected verdict",
    "expected label",
    "correct verdict",
    "correct answer",
    "oracle label",
    "rationale:",
    "opaque_artifact_id",
)


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
def _v1():
    if not V1_PATH.is_file() or sha256_file(V1_PATH) != V1_SHA256:
        raise ValueError("Frozen v1 lifecycle adapter drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v2_adapter", V1_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v1 lifecycle adapter is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _base():
    v1 = _v1()
    base = v1._base()
    _configure(v1, base)
    return base


def _configure(v1, base) -> None:
    clean = v1._adapter()
    for module in (v1, clean):
        module.ROOT = ROOT
        module.REPOSITORY = REPOSITORY
        module.STUDY_ID = STUDY_ID
        module.SOURCE_COMMIT = SOURCE_COMMIT
        module.SOURCE_TREE = SOURCE_TREE
        module.CONTROLLER_SHA256 = CONTROLLER_SHA256
        module.LEDGER_SHA256 = LEDGER_SHA256
        module.VERIFIER_SHA256 = VERIFIER_SHA256
        module.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY
        module.SLOTS = SLOTS
        module.ARMS = ARMS
        module.REPEATS = REPEATS
        module.BUNDLE_ID = BUNDLE_ID
        module.SUCCESSOR_FILES = SUCCESSOR_FILES
    base.ROOT = ROOT
    base.REPOSITORY = REPOSITORY
    base.STUDY_ID = STUDY_ID
    base.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY
    base.SLOTS = SLOTS
    base.ARMS = ARMS
    base.REPEATS = REPEATS
    base.BUNDLE_ID = BUNDLE_ID
    base.SUCCESSOR_FILES = SUCCESSOR_FILES
    base.CONTROLLER_SHA256 = CONTROLLER_SHA256
    base.LEDGER_SHA256 = LEDGER_SHA256
    base.VERIFIER_SHA256 = VERIFIER_SHA256
    v1._private_freeze = _private_freeze
    v1.build_schedule = build_schedule
    v1.validate_package = validate_package
    v1.prepare = prepare
    v1._verify_prompt_pairs = _verify_prompt_pairs
    v1._claim_execution = _claim_execution
    clean._private_freeze = _private_freeze
    clean.validate_package = validate_package
    clean.prepare = prepare
    clean._verify_prompt_pairs = _verify_prompt_pairs
    base._private_freeze = _private_freeze
    base.build_schedule = build_schedule
    base.validate_package = validate_package
    base.prepare = prepare
    base._verify_prompt_pairs = _verify_prompt_pairs
    base._claim_execution = _claim_execution


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    base = _base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = (
        (controller_path, CONTROLLER_SHA256),
        (ledger_path, LEDGER_SHA256),
        (verifier_path, VERIFIER_SHA256),
    )
    if any(not path.is_file() or base.sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private v2 controller, ledger, or verifier drifted")
    controller = base._load_json(controller_path)
    ledger = base._load_json(ledger_path)
    fixtures = controller.get("fixture_matrix")
    mappings = ledger.get("slot_mapping")
    if (
        controller.get("study_id") != STUDY_ID
        or controller.get("format_version") != 2
        or controller.get("visibility") != "private_controller_only"
        or ledger.get("study_id") != STUDY_ID
        or ledger.get("format_version") != 2
        or ledger.get("visibility") != "private_controller_only"
        or not isinstance(fixtures, list)
        or len(fixtures) != 4
        or not isinstance(mappings, list)
        or len(mappings) != SLOTS
    ):
        raise ValueError("Private v2 freeze geometry drifted")
    fixture_ids = {str(fixture.get("fixture_id")) for fixture in fixtures}
    fixture_hashes = {base.sha256_bytes(str(fixture.get("text")).encode("utf-8")) for fixture in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256:
        raise ValueError("Private v2 fixture commitments drifted")
    opaque_by_fixture: dict[str, str] = {}
    geometry: set[tuple[str, int]] = set()
    slot_ids: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise TypeError("Private v2 mapping is malformed")
        fixture_id = str(mapping.get("fixture_id"))
        artifact_id = str(mapping.get("opaque_artifact_id"))
        slot_id = str(mapping.get("opaque_slot_id"))
        repeat = int(mapping.get("repeat"))
        if (
            fixture_id not in fixture_ids
            or mapping.get("arm") != "candidate"
            or not OPAQUE_ARTIFACT.fullmatch(artifact_id)
            or not OPAQUE_SLOT.fullmatch(slot_id)
            or repeat not in REPEATS
        ):
            raise ValueError("Private v2 opaque mapping boundary drifted")
        prior = opaque_by_fixture.setdefault(fixture_id, artifact_id)
        if prior != artifact_id:
            raise ValueError("A semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat))
        slot_ids.add(slot_id)
    if (
        len(set(opaque_by_fixture.values())) != 4
        or geometry != {(fixture_id, repeat) for fixture_id in fixture_ids for repeat in REPEATS}
        or len(slot_ids) != SLOTS
    ):
        raise ValueError("Private v2 opaque schedule is not one-to-one and complete")
    return controller, ledger


def build_schedule() -> list[dict[str, Any]]:
    base = _base()
    controller, ledger = _private_freeze()
    fixtures = {str(item["fixture_id"]): item for item in controller["fixture_matrix"]}
    question = v1_question = _v1()._questions()["candidate"]
    if question["text"] != CANDIDATE_TEXT or v1_question != question:
        raise ValueError("V2 candidate wording drifted")
    rubric_sha256 = base.sha256_file(REPOSITORY / "registry" / "all_modules.json")
    schedule: list[dict[str, Any]] = []
    for mapping in sorted(ledger["slot_mapping"], key=lambda item: str(item["opaque_slot_id"])):
        private_fixture_id = str(mapping["fixture_id"])
        artifact_id = str(mapping["opaque_artifact_id"])
        repeat = int(mapping["repeat"])
        fixture = fixtures[private_fixture_id]
        condition = {
            "provider": "codex",
            "model": "gpt-5.6-sol",
            "reasoning": "high",
            "strict_ai": True,
            "batch_size": 1,
            "batch_attempts": 1,
            "leaf_id": base.LEAF_ID,
            "question_sha256": base.sha256_bytes(base.canonical_json(question)),
            "prompt_sha256": "0" * 64,
            "rubric_sha256": rubric_sha256,
        }
        schedule.append({
            "opaque_slot_id": str(mapping["opaque_slot_id"]),
            "private_fixture_id": private_fixture_id,
            "fixture_id": artifact_id,
            "arm": "candidate",
            "repeat": repeat,
            "artifact_text": str(fixture["text"]),
            "contexts": list(fixture["contexts"]),
            "expected_verdict": str(fixture["expected_verdict"]),
            "role": str(fixture["role"]),
            "condition": condition,
            "logical_sample_id": base.logical_sample_id(
                study_id=STUDY_ID,
                artifact_id=artifact_id,
                artifact_sha256=base.sha256_bytes(str(fixture["text"]).encode("utf-8")),
                condition=condition,
                repetition=repeat,
                rubric_revision="1.2.0",
            ),
        })
    if len(schedule) != SLOTS or len({slot["opaque_slot_id"] for slot in schedule}) != SLOTS:
        raise ValueError("V2 execution schedule geometry drifted")
    if len({slot["fixture_id"] for slot in schedule}) != 4:
        raise ValueError("V2 provider artifact identifiers are not one-to-one")
    return schedule


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def validate_package() -> dict[str, Any]:
    v1, base = _v1(), _base()
    value = contract()
    if (
        value.get("study_id") != STUDY_ID
        or value.get("format_version") != 2
        or value.get("status") != "frozen_unexecuted_opaque_identifier_successor"
    ):
        raise ValueError("V2 contract identity drifted")
    if value.get("source_checkout") != {
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "exact_head_required_before_claim": True,
    }:
        raise ValueError("V2 source binding drifted")
    if value.get("v1_provider_free_predecessor") != {
        "package_path": V1_PATH.parent.relative_to(REPOSITORY).as_posix(),
        "executor_sha256": V1_SHA256,
        "manifest_sha256": "d0d66ec5e289ee96dc39389ecfa372a8fafa6c6d52f877b547a9a10cf82d4aa8",
        "disclosure_sha256": "3829192370d9cf6e4dd0985f920d7332c2a09094b75ffbd4040033c49adc5c54",
        "dry_run_receipt_sha256": "c1a558878a2d0076bf8995a58b1a925925d34a269aa7809ebce5759d3c1b8598",
        "provider_calls": 0,
        "execution_claim": "none",
        "disposition": "stale_semantic_identifier_leak_not_reusable",
    }:
        raise ValueError("V2 predecessor freeze lineage drifted")
    candidate = value.get("candidate")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("leaf_id") != base.LEAF_ID
        or candidate.get("text") != CANDIDATE_TEXT
        or candidate.get("source_leaf_sha256") != "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a"
        or candidate.get("candidate_leaf_sha256") != v1.CANDIDATE_SHA256
        or candidate.get("prompt_delta") != "repetition_leaf_text_only"
    ):
        raise ValueError("V2 candidate binding drifted")
    if value.get("private_commitments") != {
        "controller_sha256": CONTROLLER_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "verifier_sha256": VERIFIER_SHA256,
        "fixture_text_sha256": sorted(FIXTURE_SHA256),
    }:
        raise ValueError("V2 private commitments drifted")
    if value.get("identifier_boundary") != {
        "semantic_fixture_keys": "private_controller_and_ledger_only",
        "expected_labels_and_roles": "private_controller_and_verifier_only",
        "provider_artifact_ids": "opaque_private_ledger_tokens_only",
        "provider_slot_ids": "opaque_private_ledger_tokens_not_rendered",
        "prompt_privacy_receipt": "required_before_claim",
    }:
        raise ValueError("V2 identifier boundary drifted")
    if value.get("geometry") != {
        "cells": 4,
        "states": ["NOT_APPLICABLE", "NO", "YES", "CANNOT_ASSESS"],
        "arms": ["candidate"],
        "repeats": 3,
        "slots": 12,
        "one_leaf_per_call": True,
    }:
        raise ValueError("V2 geometry drifted")
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
        raise ValueError("V2 execution boundary drifted")
    if value.get("evidence_gate") != {
        "grounding": "nonempty_exact_quotes_verbatim_in_supplied_artifact_or_context_only",
        "summary_evidence": "forbidden",
        "normalization_events_required": 0,
    }:
        raise ValueError("V2 evidence gate drifted")
    if value.get("gating") != {
        "each_cell_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS",
        "all_slots_required": "12/12",
        "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY",
        "invalid_or_incomplete": "no_result",
        "success_authorizes_only": "fresh_disjoint_holdout",
    }:
        raise ValueError("V2 outcome gate drifted")
    if value.get("promotion") != "none" or value.get("dspy") != "not_implemented_runtime":
        raise ValueError("V2 promotion or runtime-DSPy boundary drifted")
    if _git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in v1._adapter().RUNTIME_SHA256.items():
        if base.sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    _private_freeze()
    schedule = build_schedule()
    if any(not OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule):
        raise ValueError("A provider artifact identifier is not opaque")
    if any(not OPAQUE_SLOT.fullmatch(slot["opaque_slot_id"]) for slot in schedule):
        raise ValueError("A private slot identifier is not opaque")
    return {
        "study_id": STUDY_ID,
        "source_commit": SOURCE_COMMIT,
        "slots": SLOTS,
        "provider_calls": 0,
        "provider_artifacts": 4,
        "semantic_identifier_hits_allowed": 0,
        "success_authorizes_only": "fresh_disjoint_holdout",
    }


def prepare() -> dict[str, Any]:
    base = _base()
    validate_package()
    root, schedule = base._execution_root(), build_schedule()
    if base._claim_path(root).exists():
        raise ValueError("Preparation cannot rewrite a claimed root")
    base._write_or_verify(root / "catalog" / "bundles.json", base.canonical_json(base._bundle()))
    base._write_or_verify(base._registry_path(root, "candidate"), base.canonical_json(base._registry("candidate")))
    controller, _ledger = _private_freeze()
    fixtures = {str(item["fixture_id"]): item for item in controller["fixture_matrix"]}
    for private_fixture_id, fixture in fixtures.items():
        slot = next(item for item in schedule if item["private_fixture_id"] == private_fixture_id)
        provider_fixture = {
            "fixture_id": slot["fixture_id"],
            "declared_scope": fixture["declared_scope"],
            "completion_status": fixture["completion_status"],
            "contexts": list(fixture["contexts"]),
            "text": fixture["text"],
        }
        base._write_or_verify(base._artifact_path(root, slot), str(fixture["text"]).encode("utf-8"))
        task = base._task_contract(provider_fixture)
        base._write_or_verify(base._task_path(root, slot), base.canonical_json(task))
        base._write_or_verify(base._override_path(root, slot), base.canonical_json(base._scope_override(provider_fixture, task)))
        for index, context in enumerate(fixture["contexts"], start=1):
            path = root / "contexts" / base._fixture_token(slot["fixture_id"]) / f"context-{index:02d}.txt"
            base._write_or_verify(path, str(context).encode("utf-8"))
    base._write_or_verify(root / "private-schedule.json", base.canonical_json({"format_version": 2, "slots": schedule}))
    base._write_prepared_manifest(root / "study-manifest.json", base.canonical_json(base._manifest(schedule)))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _prompt_scan(
    schedule: Sequence[Mapping[str, Any]],
    prompts: Mapping[str, bytes],
) -> dict[str, Any]:
    controller, ledger = _private_freeze()
    private_tokens = {
        str(value)
        for fixture in controller["fixture_matrix"]
        for value in (fixture.get("fixture_id"), fixture.get("state"))
    }
    private_slots = {str(item["opaque_slot_id"]) for item in ledger["slot_mapping"]}
    provider_artifacts = {str(item["opaque_artifact_id"]) for item in ledger["slot_mapping"]}
    semantic_hits: list[str] = []
    oracle_hits: list[str] = []
    slot_hits: list[str] = []
    artifact_mismatches: list[str] = []
    identifier_pattern = re.compile(
        r"(?:artifact|fixture|private|s1)[-_.:][^\s\"']*(?:absence|functional|inert|incomplete)",
        re.IGNORECASE,
    )
    for slot in schedule:
        slot_id = str(slot["opaque_slot_id"])
        prompt = prompts[slot_id].decode("utf-8")
        folded = prompt.casefold()
        semantic_hits.extend(token for token in private_tokens if token and token.casefold() in folded)
        semantic_hits.extend(identifier_pattern.findall(prompt))
        oracle_hits.extend(marker for marker in ORACLE_MARKERS if marker in folded)
        slot_hits.extend(token for token in private_slots if token in prompt)
        own_artifact = str(slot["fixture_id"])
        present_artifacts = {token for token in provider_artifacts if token in prompt}
        if present_artifacts != {own_artifact}:
            artifact_mismatches.append(slot_id)
    if semantic_hits or oracle_hits or slot_hits or artifact_mismatches:
        raise ValueError("Provider prompt privacy scan found semantic or oracle identifier leakage")
    return {
        "format_version": 2,
        "study_id": STUDY_ID,
        "prompts_scanned": SLOTS,
        "provider_artifacts": len(provider_artifacts),
        "semantic_identifier_hits": 0,
        "oracle_binding_hits": 0,
        "private_slot_identifier_hits": 0,
        "provider_artifact_mismatches": 0,
        "prompt_sha256": {
            str(slot["opaque_slot_id"]): _base().sha256_bytes(prompts[str(slot["opaque_slot_id"])])
            for slot in schedule
        },
    }


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
        raise ValueError("V2 rendered prompt geometry drifted")
    if any(candidate not in prompts[str(slot["opaque_slot_id"])] for slot in schedule):
        raise ValueError("V2 candidate wording is absent from a frozen prompt")
    if any(source in prompts[str(slot["opaque_slot_id"])] for slot in schedule):
        raise ValueError("Canonical source wording leaked into a treatment prompt")
    _prompt_scan(schedule, prompts)


def _privacy_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    prompts = {
        str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes()
        for slot in schedule
    }
    return _prompt_scan(schedule, prompts)


def _write_privacy_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = _base()
    receipt = _privacy_receipt(root, schedule)
    base._write_or_verify(
        root / "receipts" / "provider-prompt-privacy-scan.v2.json",
        base.canonical_json(receipt),
    )
    return receipt


def _require_privacy_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    path = root / "receipts" / "provider-prompt-privacy-scan.v2.json"
    if not path.is_file() or _base()._load_json(path) != _privacy_receipt(root, schedule):
        raise ValueError("Exact provider-prompt privacy receipt is required before claim")


def _claim_execution(root: Path, schedule: Sequence[Mapping[str, Any]]) -> Path:
    if _v1()._git("rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("Exact source HEAD is required immediately before execution claim")
    validate_package()
    _require_privacy_receipt(root, schedule)
    return _base()._four_state_original_claim_execution(root, schedule)


def set_private_root(value: str | Path) -> Path:
    return _base().set_private_root(value)


def dry_run(
    private_root: str | Path,
    *,
    runner_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    set_private_root(private_root)
    report = _base().dry_run(runner_call=runner_call)
    receipt = _write_privacy_receipt(_base()._execution_root(), build_schedule())
    return {**report, "prompt_privacy": receipt}


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
    return _v1()._settle(verifier=verifier)


def command_for(
    slot: Mapping[str, Any],
    private_root: str | Path,
    *,
    render: bool = False,
) -> list[str]:
    set_private_root(private_root)
    return _base()._command(slot, render=render)
