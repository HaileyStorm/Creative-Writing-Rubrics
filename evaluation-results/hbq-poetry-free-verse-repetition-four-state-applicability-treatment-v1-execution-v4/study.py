"""Fresh v4 executor: v3 exact-quote design with honest v2 lineage."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v4"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V3_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v3" / "study.py"
V3_SHA256 = "3726c3426473d623fc556625fea568625e2ea2f1bc3e0245e2b5097c33f52477"
V2_RESULT_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2-public-result-v1" / "public-result.json"
V2_RESULT_SHA256 = "93c8eb06fdbd8e55b69efcdfd7c803ff4137710bb5104b310380cb91400de7fc"
PROMPT_SOURCE = ROOT / "exact-quote-binary-prompt.md"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SOURCE = ROOT / "exact-quote-response.schema.json"
SCHEMA_SHA256 = "25b7563672c08d76f9a978108fc334def213a81211c00520c9cad25fa5a4451e"
CONTROLLER_SHA256 = "d77a9e7ba69c699e8be590490ee93c24fa9a6dadf22d9dab448190836888f858"
LEDGER_SHA256 = "47fb0e95c29e5b17e80531b218dd61460d7b298aab7316ff9fbeb2ea8a924762"
VERIFIER_SHA256 = "9834fa06a83639467867411ac6e36ec1026961a91f98238e08714e30705f18cf"
FIXTURE_SHA256 = {
    "949a5ade63baff0a18ad4d9365f79375575671a464cd6f3cf89eb950f2760d83",
    "262c3dbfd3c584462e5b4078e324cf8a3516be5ee9d4ecefb2ce20616d715fa7",
    "5277854c7cfa6d324c4fd977b43926d5c74fd79a35094c5212a4e0ffc5c4e675",
    "1fa7859c544799a182a81f374693274dd94e48eb3b264c99f5559467b4e0185c",
}
PRIVATE_EXECUTION_DIRECTORY = "execution-v4-preexecution-freeze-v1"
SLOTS = 12
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v4"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json", "exact-quote-binary-prompt.md", "exact-quote-response.schema.json")
_CONFIGURED = False
_V3_PROTOCOL_SCAN: Callable[[Sequence[Mapping[str, Any]], Mapping[str, bytes]], dict[str, Any]] | None = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _v3():
    if not V3_PATH.is_file() or sha256_file(V3_PATH) != V3_SHA256:
        raise ValueError("Frozen v3 exact-quote design drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v4_adapter", V3_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v3 exact-quote design is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _configure() -> Any:
    global _CONFIGURED
    value = _v3()
    if _CONFIGURED:
        return value
    base = value._base()
    v2, v1, clean = value._v2(), value._v2()._v1(), value._v2()._v1()._adapter()
    for module in (value, v2, v1, clean, base):
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
    value._private_freeze = _private_freeze
    value.validate_package = validate_package
    global _V3_PROTOCOL_SCAN
    _V3_PROTOCOL_SCAN = value._protocol_prompt_scan
    value._protocol_prompt_scan = _protocol_prompt_scan
    value._write_protocol_receipt = _write_protocol_receipt
    value._require_protocol_receipt = _require_protocol_receipt
    value._configure(v2, base)
    _CONFIGURED = True
    return value


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    value = _v3()
    base = value._base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = ((controller_path, CONTROLLER_SHA256), (ledger_path, LEDGER_SHA256), (verifier_path, VERIFIER_SHA256))
    if any(not path.is_file() or sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private v4 controller, ledger, or verifier drifted")
    controller, ledger = base._load_json(controller_path), base._load_json(ledger_path)
    fixtures, mappings = controller.get("fixture_matrix"), ledger.get("slot_mapping")
    if (controller.get("study_id") != STUDY_ID or controller.get("format_version") != 4 or
            controller.get("visibility") != "private_controller_only" or ledger.get("study_id") != STUDY_ID or
            ledger.get("format_version") != 4 or ledger.get("visibility") != "private_controller_only" or
            not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(mappings, list) or len(mappings) != SLOTS):
        raise ValueError("Private v4 freeze geometry drifted")
    fixture_ids = {str(item.get("fixture_id")) for item in fixtures}
    fixture_hashes = {base.sha256_bytes(str(item.get("text")).encode("utf-8")) for item in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256:
        raise ValueError("Private v4 fixture commitments drifted")
    opaque_by_fixture: dict[str, str] = {}
    geometry: set[tuple[str, int]] = set()
    slot_ids: set[str] = set()
    for mapping in mappings:
        fixture_id, artifact_id, slot_id, repeat = (str(mapping.get("fixture_id")), str(mapping.get("opaque_artifact_id")), str(mapping.get("opaque_slot_id")), int(mapping.get("repeat")))
        if (fixture_id not in fixture_ids or mapping.get("arm") != "candidate" or not value._v2().OPAQUE_ARTIFACT.fullmatch(artifact_id) or
                not value._v2().OPAQUE_SLOT.fullmatch(slot_id) or repeat not in REPEATS):
            raise ValueError("Private v4 opaque mapping boundary drifted")
        if opaque_by_fixture.setdefault(fixture_id, artifact_id) != artifact_id:
            raise ValueError("A v4 semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat)); slot_ids.add(slot_id)
    if len(set(opaque_by_fixture.values())) != 4 or geometry != {(item, repeat) for item in fixture_ids for repeat in REPEATS} or len(slot_ids) != SLOTS:
        raise ValueError("Private v4 opaque schedule is not one-to-one and complete")
    return controller, ledger


def _protocol_prompt_scan(schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> dict[str, Any]:
    if _V3_PROTOCOL_SCAN is None:
        raise ValueError("V3 protocol scanner is unavailable")
    value = _V3_PROTOCOL_SCAN(schedule, prompts)
    return {**value, "format_version": 4}


def _write_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    value = _configure()
    receipt = value._protocol_receipt(root, schedule)
    value._base()._write_or_verify(root / "receipts" / "evidence-protocol-scan.v4.json", value._base().canonical_json(receipt))
    return receipt


def _require_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    value = _configure()
    path = root / "receipts" / "evidence-protocol-scan.v4.json"
    if not path.is_file() or value._base()._load_json(path) != value._protocol_receipt(root, schedule):
        raise ValueError("Exact v4 evidence-protocol receipt is required before claim")


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def _expected_contract() -> dict[str, Any]:
    v3 = _v3()
    return {
        "format_version": 4, "study_id": STUDY_ID, "status": "frozen_unexecuted_exact_quote_protocol_successor",
        "source_checkout": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "exact_head_required_before_claim": True},
        "v2_historical_preexecution_snapshot": {
            "package_path": "evaluation-results/hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v2",
            "snapshot_completed_at_utc": "2026-08-24T18:25:43.6706198Z", "study_manifest_sha256": "8d12ecfeb06fbd2424790f0a847074ceb15f4efdfbec00d1b99db6998a66367a",
            "dry_run_receipt_sha256": "ad6b93cad86b3cbc0818411165b098d63a232b7fdb97081da91465852abc8ee5", "prompt_privacy_receipt_sha256": "e31fec72dd10554a5413c1a8d8e0077c8ead9d8aced07ea2001ceab578b0088a",
            "provider_calls_at_snapshot": 0, "execution_claim_at_snapshot": "none", "disposition": "historical_preexecution_snapshot_not_current_execution_outcome"},
        "v2_current_outcome_binding": {
            "public_result_path": V2_RESULT_PATH.relative_to(REPOSITORY).as_posix(), "public_result_sha256": V2_RESULT_SHA256,
            "execution_claim_sha256": "af6032f1a84398f23216ae7b16c78c8fe5c60a95dedc61d677b3a0ad9a552141",
            "contacts": {"planned": 12, "accepted": 12, "unique": 12, "first_attempt": 12, "retries": 0, "rejections": 0, "normalization_events": 0},
            "semantic_oracle_agreement": {"matched": 12, "total": 12}, "strict_evidence_gate": {"matched": 10, "total": 12, "summary_items": 2},
            "formal_result": "NO_RESULT", "postexecution_artifacts": {"settlement": "not_written", "aggregate": "not_written", "terminal_result": "not_written"},
            "promotion": "none", "holdout": "not_authorized", "dspy": "not_authorized"},
        "candidate": {"leaf_id": "form.poetry.free_verse.repetition", "text": v3._v2().CANDIDATE_TEXT,
                      "source_leaf_sha256": "34f195cb415bdca5725be3bcc524ab826aac09c43245f4bcddb6961f13dce24a",
                      "candidate_leaf_sha256": v3._v2()._v1().CANDIDATE_SHA256, "prompt_delta": "repetition_leaf_text_only"},
        "private_commitments": {"controller_sha256": CONTROLLER_SHA256, "ledger_sha256": LEDGER_SHA256, "verifier_sha256": VERIFIER_SHA256, "fixture_text_sha256": sorted(FIXTURE_SHA256)},
        "evidence_protocol": {"composition": "replace_generic_binary_evidence_instructions", "binary_prompt_source": PROMPT_SOURCE.name, "binary_prompt_sha256": PROMPT_SHA256,
                              "response_schema_source": SCHEMA_SOURCE.name, "response_schema_sha256": SCHEMA_SHA256, "kind": "exact_quote_only", "exact_quote": "nonempty_verbatim_supplied_substring",
                              "summary": "required_null_unavailable", "normalization_events_required": 0, "protocol_receipt": "required_before_claim"},
        "identifier_boundary": {"semantic_fixture_keys": "private_controller_and_ledger_only", "expected_labels_and_roles": "private_controller_and_verifier_only",
                                "provider_artifact_ids": "opaque_private_ledger_tokens_only", "provider_slot_ids": "opaque_private_ledger_tokens_not_rendered", "prompt_privacy_receipt": "required_before_claim"},
        "geometry": {"cells": 4, "states": ["NOT_APPLICABLE", "NO", "YES", "CANNOT_ASSESS"], "arms": ["candidate"], "repeats": 3, "slots": 12, "one_leaf_per_call": True, "fresh_private_prose": True},
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "sequence": "strict", "batch_size": 1, "batch_attempts": 1, "maximum_provider_sends": 12,
                      "one_physical_attempt_per_slot": True, "semantic_retry_or_resume": "forbidden", "paid_api_or_fallback_route": "forbidden"},
        "gating": {"each_cell_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "all_slots_required": "12/12", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY",
                   "invalid_or_incomplete": "no_result", "success_authorizes_only": "fresh_disjoint_holdout"}, "promotion": "none", "dspy": "not_implemented_runtime"}


def validate_package() -> dict[str, Any]:
    value = _configure()
    if contract() != _expected_contract():
        raise ValueError("V4 contract or lineage binding drifted")
    if not V2_RESULT_PATH.is_file() or sha256_file(V2_RESULT_PATH) != V2_RESULT_SHA256:
        raise ValueError("Current v2 public outcome binding drifted")
    if value._v2()._git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in value._v2()._v1()._adapter().RUNTIME_SHA256.items():
        if sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    if sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or sha256_file(SCHEMA_SOURCE) != SCHEMA_SHA256:
        raise ValueError("Exact-quote protocol source drifted")
    _private_freeze()
    schedule = value.build_schedule()
    if len(schedule) != SLOTS or any(not value._v2().OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule):
        raise ValueError("V4 provider identifiers are not opaque and complete")
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "provider_artifacts": 4,
            "summary_evidence_available": False, "normalization_events_required": 0, "success_authorizes_only": "fresh_disjoint_holdout"}


def prepare() -> dict[str, Any]:
    return _configure().prepare()


def set_private_root(value: str | Path) -> Path:
    return _configure().set_private_root(value)


def build_schedule() -> list[dict[str, Any]]:
    return _configure().build_schedule()


def dry_run(private_root: str | Path, *, runner_call: Callable[..., Any] = None) -> dict[str, Any]:
    value = _configure()
    if runner_call is None:
        return value.dry_run(private_root)
    return value.dry_run(private_root, runner_call=runner_call)


def execute(private_root: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] = None) -> dict[str, Any]:
    value = _configure()
    kwargs: dict[str, Any] = {"allow_remote": allow_remote, "acknowledged_zero_incremental_charge": acknowledged_zero_incremental_charge}
    if runner_call is not None:
        kwargs["runner_call"] = runner_call
    return value.execute(private_root, **kwargs)


def settle(private_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    return _configure().settle(private_root, verifier=verifier)


def command_for(slot: Mapping[str, Any], private_root: str | Path, *, render: bool = False) -> list[str]:
    return _configure().command_for(slot, private_root, render=render)
