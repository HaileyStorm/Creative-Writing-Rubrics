"""Fresh S1 v9 prompt-and-schema-parity successor."""
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
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v9"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V8_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v8" / "study.py"
V8_SHA256 = "c54de16377633facb674cb632a3ad6d5890c2aad9ecea11bc41618cca31e8d67"
V8_CONTRACT_SHA256 = "a0ef3261bfb3f14c88e3308f9ddf3e71d3d1aa28e022f328958304b2ba97a96c"
PROMPT_SOURCE = ROOT / "exact-quote-binary-prompt.md"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SOURCE = ROOT / "exact-quote-response.schema.json"
PRIVATE_EXECUTION_DIRECTORY = "execution-v9-preexecution-freeze-v1"
SLOTS = 12
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v9"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json", "README.md", "exact-quote-binary-prompt.md", "exact-quote-response.schema.json")
CONTROLLER_SHA256 = "271165f1a1c420174bfe205728a9596c27cfadba9b9f069c58041c20ecffb1e7"
LEDGER_SHA256 = "5348169733b68ad9214ba4488fa2ddb2dcb3e4617b14bfbf08bd55114f749fa8"
VERIFIER_SHA256 = "5e7fb0c8c70f13d5016b145b338cda1a6dbe48505ff41b15e4107694a1fa0cbd"
FIXTURE_SHA256 = {"1fa7859c544799a182a81f374693274dd94e48eb3b264c99f5559467b4e0185c", "262c3dbfd3c584462e5b4078e324cf8a3516be5ee9d4ecefb2ce20616d715fa7", "5277854c7cfa6d324c4fd977b43926d5c74fd79a35094c5212a4e0ffc5c4e675", "7eee7bbe1e394a506b88001566786dbf970004bf86d28e7370d517d6f5684c3d"}
_CONFIGURED = False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _v8() -> Any:
    if not V8_PATH.is_file() or sha256_file(V8_PATH) != V8_SHA256:
        raise ValueError("Frozen v8 successor drifted")
    contract = V8_PATH.parent / "study-contract.json"
    if not contract.is_file() or sha256_file(contract) != V8_CONTRACT_SHA256:
        raise ValueError("Frozen v8 lineage contract drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v9_adapter", V8_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v8 successor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _prompt_sha256() -> str:
    return sha256_file(PROMPT_SOURCE)


def _schema_sha256() -> str:
    return sha256_file(SCHEMA_SOURCE)


def provider_schema_subset(schema: Mapping[str, Any]) -> None:
    def walk(node: Any, path: str) -> None:
        if isinstance(node, Mapping):
            if "const" in node and isinstance(node["const"], str) and node.get("type") != "string":
                raise ValueError(f"provider schema subset requires type:string for const at {path}")
            enum = node.get("enum")
            if isinstance(enum, list) and enum and all(isinstance(value, str) for value in enum) and node.get("type") != "string":
                raise ValueError(f"provider schema subset requires type:string for enum at {path}")
            for key, value in node.items():
                walk(value, f"{path}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}/{index}")
    walk(schema, "$")


def _validate_protocol_sources() -> None:
    if sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or sha256_file(SCHEMA_SOURCE) != _schema_sha256():
        raise ValueError("Exact-quote protocol source drifted")
    prompt = PROMPT_SOURCE.read_text(encoding="utf-8")
    required = ("`kind` set exactly to `exact_quote`", "a nonblank `exact_quote`", "`summary` set to JSON `null`")
    if any(value not in prompt for value in required):
        raise ValueError("Exact-quote replacement instruction is incomplete")
    schema = json.loads(SCHEMA_SOURCE.read_text(encoding="utf-8"))
    provider_schema_subset(schema)
    item = schema["properties"]["verdicts"]["items"]["properties"]
    evidence = item["evidence"]
    if item["verdict"] != {"type": "string", "enum": ["YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"]} or evidence.get("minItems") != 1 or evidence["items"]["properties"].get("kind") != {"type": "string", "const": "exact_quote"} or evidence["items"]["properties"].get("summary") != {"type": "null"}:
        raise ValueError("Provider-compatible exact-quote response schema drifted")


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    v8 = _v8(); v3 = v8._v7()._v6()._v5()._v4()._v3(); base = v3._base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = ((controller_path, CONTROLLER_SHA256), (ledger_path, LEDGER_SHA256), (verifier_path, VERIFIER_SHA256))
    if any(not path.is_file() or sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private v9 controller, ledger, or verifier drifted")
    controller, ledger = base._load_json(controller_path), base._load_json(ledger_path)
    fixtures, mappings = controller.get("fixture_matrix"), ledger.get("slot_mapping")
    if controller.get("study_id") != STUDY_ID or controller.get("format_version") != 9 or ledger.get("study_id") != STUDY_ID or ledger.get("format_version") != 9 or not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(mappings, list) or len(mappings) != SLOTS:
        raise ValueError("Private v9 freeze geometry drifted")
    fixture_ids = {str(item.get("fixture_id")) for item in fixtures}
    fixture_hashes = {base.sha256_bytes(str(item.get("text")).encode("utf-8")) for item in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256:
        raise ValueError("Private v9 fixture commitments drifted")
    opaque_by_fixture: dict[str, str] = {}; geometry: set[tuple[str, int]] = set(); slot_ids: set[str] = set()
    for mapping in mappings:
        fixture_id, artifact_id, slot_id, repeat = str(mapping.get("fixture_id")), str(mapping.get("opaque_artifact_id")), str(mapping.get("opaque_slot_id")), int(mapping.get("repeat"))
        if fixture_id not in fixture_ids or mapping.get("arm") != "candidate" or not v3._v2().OPAQUE_ARTIFACT.fullmatch(artifact_id) or not v3._v2().OPAQUE_SLOT.fullmatch(slot_id) or repeat not in REPEATS:
            raise ValueError("Private v9 opaque mapping boundary drifted")
        if opaque_by_fixture.setdefault(fixture_id, artifact_id) != artifact_id:
            raise ValueError("A v9 semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat)); slot_ids.add(slot_id)
    if len(set(opaque_by_fixture.values())) != 4 or geometry != {(fixture_id, repeat) for fixture_id in fixture_ids for repeat in REPEATS} or len(slot_ids) != SLOTS:
        raise ValueError("Private v9 schedule is not one-to-one and complete")
    return controller, ledger


def _protocol_prompt_scan(schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> dict[str, Any]:
    receipt = _v8()._protocol_prompt_scan(schedule, prompts)
    return {**receipt, "format_version": 9, "schema_sha256": _schema_sha256(), "prompt_sha256": _prompt_sha256()}


def _write_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    v3 = _v8()._v7()._v6()._v5()._v4()._v3(); receipt = v3._protocol_receipt(root, schedule)
    v3._base()._write_or_verify(root / "receipts" / "evidence-protocol-scan.v9.json", v3._base().canonical_json(receipt))
    return receipt


def _assert_schema_parity_at_root(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    v3 = _v8()._v7()._v6()._v5()._v4()._v3()
    digest = _schema_sha256()
    runtime = root / "runtime-book-v3" / "schema" / "hbq_judge_response.schema.json"
    manifest = v3._base()._load_json(root / "study-manifest.json")
    receipt = v3._protocol_receipt(root, schedule)
    if (
        not runtime.is_file() or sha256_file(runtime) != digest
        or manifest.get("generated_input_bindings", {}).get("runtime-book-v3/schema/hbq_judge_response.schema.json") != digest
        or receipt.get("schema_sha256") != digest
    ):
        raise ValueError("V9 public, runtime, manifest, and protocol schema bindings must agree before claim")
    prompt = root / "runtime-book-v3" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md"
    if (
        sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or not prompt.is_file() or sha256_file(prompt) != PROMPT_SHA256
        or manifest.get("generated_input_bindings", {}).get("runtime-book-v3/prompts/judge/BINARY_EVALUATION_PROMPT.md") != PROMPT_SHA256
        or receipt.get("prompt_sha256") != PROMPT_SHA256 or receipt.get("binary_prompt_sha256") != PROMPT_SHA256
    ):
        raise ValueError("V9 public, runtime, manifest, and protocol prompt bindings must agree before claim")


def _require_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    v3 = _v8()._v7()._v6()._v5()._v4()._v3(); path = root / "receipts" / "evidence-protocol-scan.v9.json"
    if not path.is_file() or v3._base()._load_json(path) != v3._protocol_receipt(root, schedule):
        raise ValueError("Exact v9 evidence-protocol receipt is required before claim")
    _assert_schema_parity_at_root(root, schedule)


def _configure() -> Any:
    global _CONFIGURED
    v8 = _v8()
    if _CONFIGURED:
        return v8
    v8._configure()
    v7 = v8._v7(); v6 = v7._v6(); v5 = v6._v5(); v4 = v5._v4(); v3 = v4._v3(); v2 = v3._v2(); v1 = v2._v1(); clean = v1._adapter(); base = v3._base()
    for module in (v8, v7, v6, v5, v4, v3, v2, v1, clean, base):
        module.ROOT = ROOT; module.REPOSITORY = REPOSITORY; module.STUDY_ID = STUDY_ID; module.SOURCE_COMMIT = SOURCE_COMMIT; module.SOURCE_TREE = SOURCE_TREE
        module.PROMPT_SOURCE = PROMPT_SOURCE; module.PROMPT_SHA256 = PROMPT_SHA256; module.SCHEMA_SOURCE = SCHEMA_SOURCE; module.SCHEMA_SHA256 = _schema_sha256()
        module.CONTROLLER_SHA256 = CONTROLLER_SHA256; module.LEDGER_SHA256 = LEDGER_SHA256; module.VERIFIER_SHA256 = VERIFIER_SHA256
        module.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY; module.SLOTS = SLOTS; module.ARMS = ARMS; module.REPEATS = REPEATS; module.BUNDLE_ID = BUNDLE_ID; module.SUCCESSOR_FILES = SUCCESSOR_FILES
        module._private_freeze = _private_freeze; module.validate_package = validate_package
    v3._validate_protocol_sources = _validate_protocol_sources; v3._protocol_prompt_scan = _protocol_prompt_scan; v3._write_protocol_receipt = _write_protocol_receipt; v3._require_protocol_receipt = _require_protocol_receipt
    _CONFIGURED = True
    return v8


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def _expected_contract() -> dict[str, Any]:
    return {"format_version": 9, "study_id": STUDY_ID, "status": "frozen_unexecuted_prompt_and_schema_parity_successor", "source_checkout": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "exact_head_required_before_claim": True}, "v8_provider_free_predecessor": {"package_path": V8_PATH.parent.relative_to(REPOSITORY).as_posix(), "executor_sha256": V8_SHA256, "contract_sha256": V8_CONTRACT_SHA256, "provider_calls": 0, "execution_claim": "none", "disposition": "frozen_prompt_parity_predecessor"}, "v6_consumed_outcome": {"physical_attempts": 1, "provider_attempt_settlements": 1, "outer_dispatch_settlements": 0, "accepted": 0, "untouched_slots": 11, "formal_result": "NO_RESULT", "wording_inference": "forbidden"}, "schema_parity": {"public_schema_sha256": _schema_sha256(), "runtime_book_schema_sha256": _schema_sha256(), "protocol_receipt_schema_sha256": _schema_sha256(), "manifest_runtime_schema_sha256": _schema_sha256(), "provider_subset_checked_before_claim": True}, "prompt_parity": {"public_prompt_sha256": PROMPT_SHA256, "runtime_book_prompt_sha256": PROMPT_SHA256, "protocol_receipt_prompt_sha256": PROMPT_SHA256, "manifest_runtime_prompt_sha256": PROMPT_SHA256, "exact_v7_prompt_bytes": True, "checked_before_claim": True}, "candidate": json.loads((V8_PATH.parent / "study-contract.json").read_text(encoding="utf-8"))["candidate"], "private_commitments": {"controller_sha256": CONTROLLER_SHA256, "ledger_sha256": LEDGER_SHA256, "verifier_sha256": VERIFIER_SHA256, "fixture_text_sha256": sorted(FIXTURE_SHA256), "verifier_contract": "assess_records_private_oracle"}, "geometry": {"cells": 4, "states": ["NOT_APPLICABLE", "NO", "YES", "CANNOT_ASSESS"], "arms": ["candidate"], "repeats": 3, "slots": 12, "one_leaf_per_call": True, "fresh_private_prose": True}, "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "sequence": "strict", "batch_size": 1, "batch_attempts": 1, "maximum_provider_sends": 12, "one_physical_attempt_per_slot": True, "semantic_retry_or_resume": "forbidden", "paid_api_or_fallback_route": "forbidden"}, "gating": {"each_cell_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "all_slots_required": "12/12", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY", "invalid_or_incomplete": "no_result", "success_authorizes_only": "fresh_disjoint_holdout"}, "promotion": "none", "dspy": "not_implemented_runtime"}


def validate_package() -> dict[str, Any]:
    v8 = _configure(); v3 = v8._v7()._v6()._v5()._v4()._v3()
    if contract() != _expected_contract():
        raise ValueError("V9 contract or lineage binding drifted")
    if v3._v2()._git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in v3._v2()._v1()._adapter().RUNTIME_SHA256.items():
        if sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    _validate_protocol_sources(); _private_freeze()
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "provider_artifacts": 4, "schema_sha256": _schema_sha256(), "success_authorizes_only": "fresh_disjoint_holdout"}


def set_private_root(path: str | Path) -> Path: return _configure().set_private_root(path)
def build_schedule() -> list[dict[str, Any]]: return _configure().build_schedule()
def dry_run(path: str | Path, *, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {} if runner_call is None else {"runner_call": runner_call}; return _configure().dry_run(path, **kwargs)
def execute(path: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"allow_remote": allow_remote, "acknowledged_zero_incremental_charge": acknowledged_zero_incremental_charge}
    if runner_call is not None: kwargs["runner_call"] = runner_call
    return _configure().execute(path, **kwargs)
def settle(path: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]: return _configure().settle(path, verifier=verifier)
def command_for(slot: Mapping[str, Any], path: str | Path, *, render: bool = False) -> list[str]: return _configure().command_for(slot, path, render=render)
