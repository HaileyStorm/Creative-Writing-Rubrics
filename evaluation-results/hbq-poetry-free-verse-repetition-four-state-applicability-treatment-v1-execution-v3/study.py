"""Fresh exact-quote-only v3 successor for the S1 four-state treatment."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v3"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V2_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2" / "study.py"
V2_SHA256 = "743dc5e832e98d05256e6d5c16a5d296301614eed47c2a893b566ba71ea3f961"
PROMPT_SOURCE = ROOT / "exact-quote-binary-prompt.md"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SOURCE = ROOT / "exact-quote-response.schema.json"
SCHEMA_SHA256 = "25b7563672c08d76f9a978108fc334def213a81211c00520c9cad25fa5a4451e"
CONTROLLER_SHA256 = "efce9ac20c1e936d3ee4bc610c3eb7a36cc0b33bdcf3d6f47c52df8ebe42d45d"
LEDGER_SHA256 = "baa937bea43cecf1fd00be9dc4991626985753ea802e9b711b0f25bf29bd8a0d"
VERIFIER_SHA256 = "0107aadfd702273b138ae542ee492e23b26a8fd02da62e6d63e2112205d9f24a"
FIXTURE_SHA256 = {
    "06c64278607a5882420dec0ff899d239a5e0f2e8ceb2a520f107088adfeb7029",
    "5334a8c6a91c887399264118aa83377e0b24766be6759be86080f266abe116c3",
    "5e726f4167d2575f6027181f70996d45af7f3a21642b7042d56b8e5a6e9b6519",
    "9982ca5eac4f14215a7529b79762999c54714f1e7a8aa6e40c8edf041395bc81",
}
PRIVATE_EXECUTION_DIRECTORY = "execution-v3-terminal-sidecar-v1"
SLOTS = 12
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v3"
SUCCESSOR_FILES = (
    "study.py",
    "run.py",
    "study-contract.json",
    "exact-quote-binary-prompt.md",
    "exact-quote-response.schema.json",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _v2():
    if not V2_PATH.is_file() or sha256_file(V2_PATH) != V2_SHA256:
        raise ValueError("Frozen v2 lifecycle adapter drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v3_adapter", V2_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v2 lifecycle adapter is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def _base():
    v2 = _v2()
    base = v2._base()
    _configure(v2, base)
    return base


def _configure(v2, base) -> None:
    v1, clean = v2._v1(), v2._v1()._adapter()
    for module in (v2, v1, clean):
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
    if not hasattr(base, "_v3_original_generated_input_bindings"):
        base._v3_original_generated_input_bindings = base._generated_input_bindings
    v2._private_freeze = _private_freeze
    v2.validate_package = validate_package
    v2.prepare = prepare
    v2._generated_input_bindings = _generated_input_bindings
    v2._verify_prompt_pairs = _verify_prompt_pairs
    v2._claim_execution = _claim_execution
    v1._private_freeze = _private_freeze
    clean._private_freeze = _private_freeze
    clean.validate_package = validate_package
    clean.prepare = prepare
    clean._generated_input_bindings = _generated_input_bindings
    clean._verify_prompt_pairs = _verify_prompt_pairs
    base._private_freeze = _private_freeze
    base.validate_package = validate_package
    base.prepare = prepare
    base._generated_input_bindings = _generated_input_bindings
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
        raise ValueError("Private v3 controller, ledger, or verifier drifted")
    controller = base._load_json(controller_path)
    ledger = base._load_json(ledger_path)
    fixtures = controller.get("fixture_matrix")
    mappings = ledger.get("slot_mapping")
    if (
        controller.get("study_id") != STUDY_ID
        or controller.get("format_version") != 3
        or controller.get("visibility") != "private_controller_only"
        or ledger.get("study_id") != STUDY_ID
        or ledger.get("format_version") != 3
        or ledger.get("visibility") != "private_controller_only"
        or not isinstance(fixtures, list)
        or len(fixtures) != 4
        or not isinstance(mappings, list)
        or len(mappings) != SLOTS
    ):
        raise ValueError("Private v3 freeze geometry drifted")
    fixture_ids = {str(fixture.get("fixture_id")) for fixture in fixtures}
    fixture_hashes = {base.sha256_bytes(str(fixture.get("text")).encode("utf-8")) for fixture in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256:
        raise ValueError("Private v3 fixture commitments drifted")
    opaque_by_fixture: dict[str, str] = {}
    geometry: set[tuple[str, int]] = set()
    slot_ids: set[str] = set()
    for mapping in mappings:
        if not isinstance(mapping, Mapping):
            raise TypeError("Private v3 mapping is malformed")
        fixture_id = str(mapping.get("fixture_id"))
        artifact_id = str(mapping.get("opaque_artifact_id"))
        slot_id = str(mapping.get("opaque_slot_id"))
        repeat = int(mapping.get("repeat"))
        if (
            fixture_id not in fixture_ids
            or mapping.get("arm") != "candidate"
            or not _v2().OPAQUE_ARTIFACT.fullmatch(artifact_id)
            or not _v2().OPAQUE_SLOT.fullmatch(slot_id)
            or repeat not in REPEATS
        ):
            raise ValueError("Private v3 opaque mapping boundary drifted")
        prior = opaque_by_fixture.setdefault(fixture_id, artifact_id)
        if prior != artifact_id:
            raise ValueError("A v3 semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat))
        slot_ids.add(slot_id)
    if (
        len(set(opaque_by_fixture.values())) != 4
        or geometry != {(fixture_id, repeat) for fixture_id in fixture_ids for repeat in REPEATS}
        or len(slot_ids) != SLOTS
    ):
        raise ValueError("Private v3 opaque schedule is not one-to-one and complete")
    return controller, ledger


def build_schedule() -> list[dict[str, Any]]:
    return _v2().build_schedule()


def _runtime_book() -> Path:
    return _base()._execution_root() / "runtime-book-v3"


def _validate_protocol_sources() -> None:
    if sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or sha256_file(SCHEMA_SOURCE) != SCHEMA_SHA256:
        raise ValueError("Exact-quote protocol source drifted")
    prompt = PROMPT_SOURCE.read_text(encoding="utf-8")
    forbidden = (
        "set `kind` to `exact_quote` or `summary`",
        "use `summary` for an evidence description",
        "never place a summary in `exact_quote`",
    )
    if any(value in prompt for value in forbidden):
        raise ValueError("Generic summary evidence instruction remains in the replacement prompt")
    required = (
        "`kind` set exactly to `exact_quote`",
        "a nonblank `exact_quote`",
        "`summary` set to JSON `null`",
    )
    if any(value not in prompt for value in required):
        raise ValueError("Exact-quote replacement instruction is incomplete")
    schema = json.loads(SCHEMA_SOURCE.read_text(encoding="utf-8"))
    evidence = schema["properties"]["verdicts"]["items"]["properties"]["evidence"]
    item = evidence["items"]["properties"]
    if (
        evidence.get("minItems") != 1
        or item.get("kind") != {"const": "exact_quote"}
        or item.get("reference") != {"type": "string", "minLength": 1}
        or item.get("exact_quote") != {"type": "string", "minLength": 1, "maxLength": 500}
        or item.get("summary") != {"type": "null"}
    ):
        raise ValueError("Exact-quote response schema admits summary or empty quote evidence")


def _write_runtime_book() -> None:
    base = _base()
    root = _runtime_book()
    files = {
        root / "registry" / "all_modules.json": (REPOSITORY / "registry" / "all_modules.json").read_bytes(),
        root / "prompts" / "judge" / "JUDGE_PREFIX.md": (REPOSITORY / "prompts" / "judge" / "JUDGE_PREFIX.md").read_bytes(),
        root / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md": PROMPT_SOURCE.read_bytes(),
    }
    files.update({root / "schema" / path.name: path.read_bytes() for path in (REPOSITORY / "schema").glob("*.json")})
    files[root / "schema" / "hbq_judge_response.schema.json"] = SCHEMA_SOURCE.read_bytes()
    for path, content in files.items():
        base._write_or_verify(path, content)


def _generated_input_bindings(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    base = _base()
    bindings = base._v3_original_generated_input_bindings(root, schedule)
    runtime = _runtime_book()
    files = {
        "runtime-book-v3/registry/all_modules.json": runtime / "registry" / "all_modules.json",
        "runtime-book-v3/prompts/judge/JUDGE_PREFIX.md": runtime / "prompts" / "judge" / "JUDGE_PREFIX.md",
        "runtime-book-v3/prompts/judge/BINARY_EVALUATION_PROMPT.md": runtime / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md",
    }
    files.update({f"runtime-book-v3/schema/{path.name}": path for path in (runtime / "schema").glob("*.json")})
    if any(not path.is_file() for path in files.values()):
        raise ValueError("Frozen v3 runtime-book input is unavailable")
    return {**bindings, **{name: base.sha256_file(path) for name, path in files.items()}}


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def validate_package() -> dict[str, Any]:
    v2, base = _v2(), _base()
    value = contract()
    if (
        value.get("study_id") != STUDY_ID
        or value.get("format_version") != 3
        or value.get("status") != "frozen_unexecuted_exact_quote_protocol_successor"
    ):
        raise ValueError("V3 contract identity drifted")
    if value.get("source_checkout") != {
        "commit": SOURCE_COMMIT,
        "tree": SOURCE_TREE,
        "exact_head_required_before_claim": True,
    }:
        raise ValueError("V3 source binding drifted")
    if value.get("v2_provider_free_predecessor") != {
        "package_path": V2_PATH.parent.relative_to(REPOSITORY).as_posix(),
        "executor_sha256": V2_SHA256,
        "manifest_sha256": "8d12ecfeb06fbd2424790f0a847074ceb15f4efdfbec00d1b99db6998a66367a",
        "privacy_receipt_sha256": "e31fec72dd10554a5413c1a8d8e0077c8ead9d8aced07ea2001ceab578b0088a",
        "provider_calls": 0,
        "execution_claim": "none",
        "disposition": "immutable_provider_free_evidence_protocol_successor",
    }:
        raise ValueError("V3 predecessor freeze lineage drifted")
    candidate = value.get("candidate")
    if (
        not isinstance(candidate, Mapping)
        or candidate.get("leaf_id") != base.LEAF_ID
        or candidate.get("text") != v2.CANDIDATE_TEXT
        or candidate.get("source_leaf_sha256") != "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a"
        or candidate.get("candidate_leaf_sha256") != v2._v1().CANDIDATE_SHA256
        or candidate.get("prompt_delta") != "repetition_leaf_text_only"
    ):
        raise ValueError("V3 candidate binding drifted")
    if value.get("private_commitments") != {
        "controller_sha256": CONTROLLER_SHA256,
        "ledger_sha256": LEDGER_SHA256,
        "verifier_sha256": VERIFIER_SHA256,
        "fixture_text_sha256": sorted(FIXTURE_SHA256),
    }:
        raise ValueError("V3 private commitments drifted")
    if value.get("evidence_protocol") != {
        "composition": "replace_generic_binary_evidence_instructions",
        "binary_prompt_source": PROMPT_SOURCE.name,
        "binary_prompt_sha256": PROMPT_SHA256,
        "response_schema_source": SCHEMA_SOURCE.name,
        "response_schema_sha256": SCHEMA_SHA256,
        "kind": "exact_quote_only",
        "exact_quote": "nonempty_verbatim_supplied_substring",
        "summary": "required_null_unavailable",
        "normalization_events_required": 0,
        "protocol_receipt": "required_before_claim",
    }:
        raise ValueError("V3 evidence protocol drifted")
    if value.get("identifier_boundary") != {
        "semantic_fixture_keys": "private_controller_and_ledger_only",
        "expected_labels_and_roles": "private_controller_and_verifier_only",
        "provider_artifact_ids": "opaque_private_ledger_tokens_only",
        "provider_slot_ids": "opaque_private_ledger_tokens_not_rendered",
        "prompt_privacy_receipt": "required_before_claim",
    }:
        raise ValueError("V3 identifier boundary drifted")
    if value.get("geometry") != {
        "cells": 4,
        "states": ["NOT_APPLICABLE", "NO", "YES", "CANNOT_ASSESS"],
        "arms": ["candidate"],
        "repeats": 3,
        "slots": 12,
        "one_leaf_per_call": True,
        "fresh_private_prose": True,
    }:
        raise ValueError("V3 geometry drifted")
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
        raise ValueError("V3 execution boundary drifted")
    if value.get("gating") != {
        "each_cell_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS",
        "all_slots_required": "12/12",
        "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY",
        "invalid_or_incomplete": "no_result",
        "success_authorizes_only": "fresh_disjoint_holdout",
    }:
        raise ValueError("V3 outcome gate drifted")
    if value.get("promotion") != "none" or value.get("dspy") != "not_implemented_runtime":
        raise ValueError("V3 promotion or runtime-DSPy boundary drifted")
    if v2._git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in v2._v1()._adapter().RUNTIME_SHA256.items():
        if base.sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    _validate_protocol_sources()
    _private_freeze()
    schedule = build_schedule()
    if any(not v2.OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule):
        raise ValueError("A v3 provider artifact identifier is not opaque")
    return {
        "study_id": STUDY_ID,
        "source_commit": SOURCE_COMMIT,
        "slots": SLOTS,
        "provider_calls": 0,
        "provider_artifacts": 4,
        "summary_evidence_available": False,
        "normalization_events_required": 0,
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
    base._write_or_verify(root / "private-schedule.json", base.canonical_json({"format_version": 3, "slots": schedule}))
    _write_runtime_book()
    base._write_prepared_manifest(root / "study-manifest.json", base.canonical_json(base._manifest(schedule)))
    return {"private_root": str(root), "planned_slots": SLOTS, "provider_calls": 0}


def _protocol_prompt_scan(
    schedule: Sequence[Mapping[str, Any]],
    prompts: Mapping[str, bytes],
) -> dict[str, Any]:
    required = (
        b"`kind` set exactly to `exact_quote`",
        b"a nonblank `exact_quote`",
        b"`summary` set to JSON `null`",
    )
    forbidden = (
        b"set `kind` to `exact_quote` or `summary`",
        b"use `summary` for an evidence description",
        b"never place a summary in `exact_quote`",
    )
    if len(schedule) != SLOTS or set(prompts) != {str(slot["opaque_slot_id"]) for slot in schedule}:
        raise ValueError("V3 protocol prompt geometry drifted")
    for prompt in prompts.values():
        if any(value not in prompt for value in required) or any(value in prompt for value in forbidden):
            raise ValueError("V3 rendered prompt did not replace the generic evidence instruction")
    return {
        "format_version": 3,
        "study_id": STUDY_ID,
        "prompts_scanned": SLOTS,
        "exact_quote_instruction_matches": SLOTS,
        "generic_summary_instruction_hits": 0,
        "schema_sha256": sha256_file(_runtime_book() / "schema" / "hbq_judge_response.schema.json"),
        "binary_prompt_sha256": sha256_file(_runtime_book() / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md"),
        "summary_evidence_available": False,
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
    v2, base = _v2(), _base()
    candidate = v2.CANDIDATE_TEXT.encode("utf-8")
    source = base._source_leaf()["text"].encode("utf-8")
    if any(candidate not in prompts[str(slot["opaque_slot_id"])] for slot in schedule):
        raise ValueError("V3 candidate wording is absent from a frozen prompt")
    if any(source in prompts[str(slot["opaque_slot_id"])] for slot in schedule):
        raise ValueError("Canonical source wording leaked into a treatment prompt")
    v2._prompt_scan(schedule, prompts)
    _protocol_prompt_scan(schedule, prompts)


def _overlay_runner(runner_call: Callable[..., Any]) -> Callable[..., Any]:
    def call(command, **kwargs):
        environment = os.environ.copy()
        supplied = kwargs.pop("env", None)
        if isinstance(supplied, Mapping):
            environment.update({str(key): str(value) for key, value in supplied.items()})
        environment["HBQRS_ROOT"] = str(_runtime_book())
        return runner_call(command, env=environment, **kwargs)

    return call


def _protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    prompts = {
        str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes()
        for slot in schedule
    }
    return _protocol_prompt_scan(schedule, prompts)


def _write_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    base = _base()
    receipt = _protocol_receipt(root, schedule)
    base._write_or_verify(
        root / "receipts" / "evidence-protocol-scan.v3.json",
        base.canonical_json(receipt),
    )
    return receipt


def _require_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    path = root / "receipts" / "evidence-protocol-scan.v3.json"
    if not path.is_file() or _base()._load_json(path) != _protocol_receipt(root, schedule):
        raise ValueError("Exact v3 evidence-protocol receipt is required before claim")


def _claim_execution(root: Path, schedule: Sequence[Mapping[str, Any]]) -> Path:
    v2 = _v2()
    if v2._v1()._git("rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("Exact source HEAD is required immediately before execution claim")
    validate_package()
    v2._require_privacy_receipt(root, schedule)
    _require_protocol_receipt(root, schedule)
    return _base()._four_state_original_claim_execution(root, schedule)


def set_private_root(value: str | Path) -> Path:
    return _base().set_private_root(value)


def dry_run(
    private_root: str | Path,
    *,
    runner_call: Callable[..., Any] = subprocess.run,
) -> dict[str, Any]:
    set_private_root(private_root)
    report = _base().dry_run(runner_call=_overlay_runner(runner_call))
    root, schedule = _base()._execution_root(), build_schedule()
    privacy = _v2()._write_privacy_receipt(root, schedule)
    protocol = _write_protocol_receipt(root, schedule)
    return {**report, "prompt_privacy": privacy, "evidence_protocol": protocol}


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
        runner_call=_overlay_runner(runner_call),
    )


def settle(
    private_root: str | Path,
    *,
    verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    set_private_root(private_root)
    return _v2()._v1()._settle(verifier=verifier)


def command_for(
    slot: Mapping[str, Any],
    private_root: str | Path,
    *,
    render: bool = False,
) -> list[str]:
    set_private_root(private_root)
    return _base()._command(slot, render=render)
