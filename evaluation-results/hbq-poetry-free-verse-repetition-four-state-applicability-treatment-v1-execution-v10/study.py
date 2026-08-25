"""Fresh S1 v10 full-rendered-prompt freeze successor."""
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
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v10"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V9_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v9" / "study.py"
V9_SHA256 = "a471e80aaca58d06b70515390ea82953897870070a419ae543c4a95fe45be048"
V9_CONTRACT_SHA256 = "114759ff2edd76f5cf441b887e427e26fd60baecc162f12250bfaf12da5c2bf1"
PROMPT_SOURCE = ROOT / "exact-quote-binary-prompt.md"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SOURCE = ROOT / "exact-quote-response.schema.json"
PRIVATE_EXECUTION_DIRECTORY = "execution-v10-full-rendered-prompt-freeze-v3"
SLOTS = 12
ARMS = ("candidate",)
REPEATS = (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v9"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json", "README.md", "exact-quote-binary-prompt.md", "exact-quote-response.schema.json")
CONTROLLER_SHA256 = "2cae9df8911904252f662155a4089832de9f7e798b8473e0bbb490199732b720"
LEDGER_SHA256 = "8aaa5dd0d9ded854572275bebc40d74c27a7c7e80774db247a0e95dacb841d77"
VERIFIER_SHA256 = "5e7fb0c8c70f13d5016b145b338cda1a6dbe48505ff41b15e4107694a1fa0cbd"
FIXTURE_SHA256 = {"1fa7859c544799a182a81f374693274dd94e48eb3b264c99f5559467b4e0185c", "262c3dbfd3c584462e5b4078e324cf8a3516be5ee9d4ecefb2ce20616d715fa7", "5277854c7cfa6d324c4fd977b43926d5c74fd79a35094c5212a4e0ffc5c4e675", "7eee7bbe1e394a506b88001566786dbf970004bf86d28e7370d517d6f5684c3d"}
EXPECTED_RENDERED_PROMPT_LENGTHS = (4803, 4803, 4803, 4916, 4916, 4916, 4985, 4985, 4985, 5124, 5124, 5124)
_CONFIGURED = False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _v9() -> Any:
    if not V9_PATH.is_file() or sha256_file(V9_PATH) != V9_SHA256:
        raise ValueError("Frozen v9 successor drifted")
    contract = V9_PATH.parent / "study-contract.json"
    if not contract.is_file() or sha256_file(contract) != V9_CONTRACT_SHA256:
        raise ValueError("Frozen v9 lineage contract drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v10_adapter", V9_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v9 successor is unavailable")
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


def _v3() -> Any:
    return _v9()._v8()._v7()._v6()._v5()._v4()._v3()


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    v3 = _v3(); base = v3._base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = ((controller_path, CONTROLLER_SHA256), (ledger_path, LEDGER_SHA256), (verifier_path, VERIFIER_SHA256))
    if any(not path.is_file() or sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private v10 controller, ledger, or verifier drifted")
    controller, ledger = base._load_json(controller_path), base._load_json(ledger_path)
    fixtures, mappings = controller.get("fixture_matrix"), ledger.get("slot_mapping")
    if controller.get("study_id") != STUDY_ID or controller.get("format_version") != 10 or ledger.get("study_id") != STUDY_ID or ledger.get("format_version") != 10 or not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(mappings, list) or len(mappings) != SLOTS:
        raise ValueError("Private v10 freeze geometry drifted")
    fixture_ids = {str(item.get("fixture_id")) for item in fixtures}
    fixture_hashes = {base.sha256_bytes(str(item.get("text")).encode("utf-8")) for item in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256:
        raise ValueError("Private v10 fixture commitments drifted")
    opaque_by_fixture: dict[str, str] = {}; geometry: set[tuple[str, int]] = set(); slot_ids: set[str] = set()
    for mapping in mappings:
        fixture_id, artifact_id, slot_id, repeat = str(mapping.get("fixture_id")), str(mapping.get("opaque_artifact_id")), str(mapping.get("opaque_slot_id")), int(mapping.get("repeat"))
        if fixture_id not in fixture_ids or mapping.get("arm") != "candidate" or not v3._v2().OPAQUE_ARTIFACT.fullmatch(artifact_id) or not v3._v2().OPAQUE_SLOT.fullmatch(slot_id) or repeat not in REPEATS:
            raise ValueError("Private v10 opaque mapping boundary drifted")
        if opaque_by_fixture.setdefault(fixture_id, artifact_id) != artifact_id:
            raise ValueError("A v10 semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat)); slot_ids.add(slot_id)
    if len(set(opaque_by_fixture.values())) != 4 or geometry != {(fixture_id, repeat) for fixture_id in fixture_ids for repeat in REPEATS} or len(slot_ids) != SLOTS:
        raise ValueError("Private v10 schedule is not one-to-one and complete")
    return controller, ledger


def _protocol_prompt_scan(schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> dict[str, Any]:
    receipt = _v9()._protocol_prompt_scan(schedule, prompts)
    return {**receipt, "format_version": 10, "schema_sha256": _schema_sha256(), "prompt_sha256": _prompt_sha256()}


def _write_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    v3 = _v3(); receipt = v3._protocol_receipt(root, schedule)
    v3._base()._write_or_verify(root / "receipts" / "evidence-protocol-scan.v10.json", v3._base().canonical_json(receipt))
    return receipt


def _assert_schema_parity_at_root(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    v3 = _v3()
    digest = _schema_sha256()
    runtime = root / "runtime-book-v3" / "schema" / "hbq_judge_response.schema.json"
    manifest = v3._base()._load_json(root / "study-manifest.json")
    receipt = v3._protocol_receipt(root, schedule)
    if (
        not runtime.is_file() or sha256_file(runtime) != digest
        or manifest.get("generated_input_bindings", {}).get("runtime-book-v3/schema/hbq_judge_response.schema.json") != digest
        or receipt.get("schema_sha256") != digest
    ):
        raise ValueError("V10 public, runtime, manifest, and protocol schema bindings must agree before claim")
    prompt = root / "runtime-book-v3" / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md"
    if (
        sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or not prompt.is_file() or sha256_file(prompt) != PROMPT_SHA256
        or manifest.get("generated_input_bindings", {}).get("runtime-book-v3/prompts/judge/BINARY_EVALUATION_PROMPT.md") != PROMPT_SHA256
        or receipt.get("prompt_sha256") != PROMPT_SHA256 or receipt.get("binary_prompt_sha256") != PROMPT_SHA256
    ):
        raise ValueError("V10 public, runtime, manifest, and protocol prompt bindings must agree before claim")


def _require_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    v3 = _v3(); path = root / "receipts" / "evidence-protocol-scan.v10.json"
    if not path.is_file() or v3._base()._load_json(path) != v3._protocol_receipt(root, schedule):
        raise ValueError("Exact v10 evidence-protocol receipt is required before claim")
    _assert_schema_parity_at_root(root, schedule)


def _overlay_runner(runner_call: Callable[..., Any]) -> Callable[..., Any]:
    def call(command: Sequence[str], **kwargs: Any) -> Any:
        environment = os.environ.copy()
        supplied = kwargs.pop("env", None)
        if isinstance(supplied, Mapping):
            environment.update({str(key): str(value) for key, value in supplied.items()})
        environment["HBQRS_ROOT"] = str(_v3()._base()._execution_root() / "runtime-book-v3")
        return runner_call(command, env=environment, **kwargs)
    return call


def _assert_full_rendered_prompt_geometry(
    schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes],
) -> None:
    expected_slots = tuple(str(slot["opaque_slot_id"]) for slot in schedule)
    if tuple(prompts) != expected_slots:
        raise ValueError("Full rendered prompt freeze must cover every private slot in schedule order")
    lengths = tuple(len(prompts[slot_id]) for slot_id in expected_slots)
    if tuple(sorted(lengths)) != EXPECTED_RENDERED_PROMPT_LENGTHS:
        raise ValueError(
            "Full rendered provider prompt byte geometry drifted; surrogate renderer output is forbidden"
        )
    if any(length <= 1726 for length in lengths):
        raise ValueError("Provider prompt surrogate was supplied instead of the inherited execution renderer")


def _render_full_provider_prompts(
    root: Path, schedule: Sequence[Mapping[str, Any]], runner_call: Callable[..., Any],
) -> dict[str, bytes]:
    base = _v3()._base()
    render = _overlay_runner(runner_call)
    prompts = {
        str(slot["opaque_slot_id"]): base._run_render(slot, render)
        for slot in schedule
    }
    _assert_full_rendered_prompt_geometry(schedule, prompts)
    for slot_id, prompt in prompts.items():
        base._write_or_verify(root / "rendered-prompts" / f"{slot_id}.txt", prompt)
    return prompts


def _assert_full_rendered_prompt_parity_at_root(
    root: Path, schedule: Sequence[Mapping[str, Any]],
) -> None:
    base = _v3()._base()
    frozen = {
        str(slot["opaque_slot_id"]): (root / "rendered-prompts" / f"{slot['opaque_slot_id']}.txt").read_bytes()
        for slot in schedule
    }
    _assert_full_rendered_prompt_geometry(schedule, frozen)
    rendered = _render_full_provider_prompts(root, schedule, subprocess.run)
    if rendered != frozen:
        raise ValueError("Claim-time/pre-dispatch full provider prompt parity drifted")
    disclosure_path = root / "receipts" / "preexecution-disclosure.v1.json"
    if not disclosure_path.is_file() or base._load_json(disclosure_path) != base._disclosure(schedule, frozen):
        raise ValueError("Claim-time/pre-dispatch disclosure does not bind the full frozen provider prompts")


def _claim_execution(root: Path, schedule: Sequence[Mapping[str, Any]]) -> Path:
    v3 = _v3()
    if v3._v2()._git("rev-parse", "HEAD") != SOURCE_COMMIT:
        raise ValueError("Exact source HEAD is required immediately before execution claim")
    validate_package()
    v3._v2()._require_privacy_receipt(root, schedule)
    _require_protocol_receipt(root, schedule)
    _assert_full_rendered_prompt_parity_at_root(root, schedule)
    return v3._base()._four_state_original_claim_execution(root, schedule)


def _configure() -> Any:
    global _CONFIGURED
    v9 = _v9()
    if _CONFIGURED:
        return v9
    v9._configure()
    v8 = v9._v8(); v7 = v8._v7(); v6 = v7._v6(); v5 = v6._v5(); v4 = v5._v4(); v3 = v4._v3(); v2 = v3._v2(); v1 = v2._v1(); clean = v1._adapter(); base = v3._base()
    for module in (v9, v8, v7, v6, v5, v4, v3, v2, v1, clean, base):
        module.ROOT = ROOT; module.REPOSITORY = REPOSITORY; module.STUDY_ID = STUDY_ID; module.SOURCE_COMMIT = SOURCE_COMMIT; module.SOURCE_TREE = SOURCE_TREE
        module.PROMPT_SOURCE = PROMPT_SOURCE; module.PROMPT_SHA256 = PROMPT_SHA256; module.SCHEMA_SOURCE = SCHEMA_SOURCE; module.SCHEMA_SHA256 = _schema_sha256()
        module.CONTROLLER_SHA256 = CONTROLLER_SHA256; module.LEDGER_SHA256 = LEDGER_SHA256; module.VERIFIER_SHA256 = VERIFIER_SHA256
        module.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY; module.SLOTS = SLOTS; module.ARMS = ARMS; module.REPEATS = REPEATS; module.BUNDLE_ID = BUNDLE_ID; module.SUCCESSOR_FILES = SUCCESSOR_FILES
        module._private_freeze = _private_freeze; module.validate_package = validate_package
    v3._validate_protocol_sources = _validate_protocol_sources; v3._protocol_prompt_scan = _protocol_prompt_scan; v3._write_protocol_receipt = _write_protocol_receipt; v3._require_protocol_receipt = _require_protocol_receipt
    v3._claim_execution = _claim_execution
    base._claim_execution = _claim_execution
    _CONFIGURED = True
    return v9


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Study contract must be an object")
    return value


def _expected_contract() -> dict[str, Any]:
    return {
        "format_version": 10,
        "study_id": STUDY_ID,
        "status": "frozen_unexecuted_full_rendered_prompt_parity_successor",
        "source_checkout": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "exact_head_required_before_claim": True},
        "v9_formal_no_result_predecessor": {
            "package_path": V9_PATH.parent.relative_to(REPOSITORY).as_posix(),
            "executor_sha256": V9_SHA256,
            "contract_sha256": V9_CONTRACT_SHA256,
            "execution_claim_sha256": "166d881ace0a095c7f1b142308697b7e9ae7bfa677e2a4301d6774adb1e7b8a2",
            "zero_charge_acknowledgement_sha256": "37ac50d2ae5c3a2314b425109ac3fcb354b0b77ff76e1cd654a7ba64aaed53b4",
            "claim": 1,
            "acknowledgement": 1,
            "dispatches": 0,
            "runs": 0,
            "provider_contacts": 0,
            "untouched_slots": 12,
            "formal_result": "NO_RESULT",
            "wording_inference": "forbidden",
        },
        "schema_parity": {"public_schema_sha256": _schema_sha256(), "runtime_book_schema_sha256": _schema_sha256(), "protocol_receipt_schema_sha256": _schema_sha256(), "manifest_runtime_schema_sha256": _schema_sha256(), "provider_subset_checked_before_claim": True},
        "prompt_parity": {
            "public_prompt_sha256": PROMPT_SHA256,
            "runtime_book_prompt_sha256": PROMPT_SHA256,
            "protocol_receipt_prompt_sha256": PROMPT_SHA256,
            "manifest_runtime_prompt_sha256": PROMPT_SHA256,
            "full_execution_renderer_bytes": list(EXPECTED_RENDERED_PROMPT_LENGTHS),
            "dry_freeze_and_claim_time_pre_dispatch_checked": True,
            "surrogate_renderer_forbidden": True,
        },
        "candidate": json.loads((V9_PATH.parent / "study-contract.json").read_text(encoding="utf-8"))["candidate"],
        "private_commitments": {"controller_sha256": CONTROLLER_SHA256, "ledger_sha256": LEDGER_SHA256, "verifier_sha256": VERIFIER_SHA256, "fixture_text_sha256": sorted(FIXTURE_SHA256), "verifier_contract": "assess_records_private_oracle"},
        "geometry": {"cells": 4, "states": ["NOT_APPLICABLE", "NO", "YES", "CANNOT_ASSESS"], "arms": ["candidate"], "repeats": 3, "slots": 12, "one_leaf_per_call": True, "fresh_private_prose": True},
        "execution": {"route": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "sequence": "strict", "batch_size": 1, "batch_attempts": 1, "maximum_provider_sends": 12, "one_physical_attempt_per_slot": True, "semantic_retry_or_resume": "forbidden", "paid_api_or_fallback_route": "forbidden"},
        "gating": {"each_cell_three_of_three": "HOLDOUT_ELIGIBLE_ON_SUCCESS", "all_slots_required": "12/12", "any_complete_valid_miss": "NO_GO_DSPY_ELIGIBLE_ONLY", "invalid_or_incomplete": "no_result", "success_authorizes_only": "fresh_disjoint_holdout"},
        "promotion": "none",
        "dspy": "not_implemented_runtime",
    }


def validate_package() -> dict[str, Any]:
    _configure(); v3 = _v3()
    if contract() != _expected_contract():
        raise ValueError("V10 contract or lineage binding drifted")
    if v3._v2()._git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE:
        raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in v3._v2()._v1()._adapter().RUNTIME_SHA256.items():
        if sha256_file(REPOSITORY / path) != digest:
            raise ValueError(f"Frozen runtime drifted: {path}")
    _validate_protocol_sources(); _private_freeze()
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "provider_artifacts": 4, "schema_sha256": _schema_sha256(), "success_authorizes_only": "fresh_disjoint_holdout"}


def set_private_root(path: str | Path) -> Path: return _configure().set_private_root(path)
def build_schedule() -> list[dict[str, Any]]: _configure(); return _v3().build_schedule()
def dry_run(path: str | Path, *, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    _configure()
    set_private_root(path)
    v3, base = _v3(), _v3()._base()
    prepared = v3.prepare()
    root, schedule = base._execution_root(), v3.build_schedule()
    prompts = _render_full_provider_prompts(root, schedule, subprocess.run if runner_call is None else runner_call)
    v3._verify_prompt_pairs(root, schedule, prompts)
    privacy = v3._v2()._write_privacy_receipt(root, schedule)
    protocol = _write_protocol_receipt(root, schedule)
    disclosure = base._disclosure(schedule, prompts)
    base._write_or_verify(root / "receipts" / "preexecution-disclosure.v1.json", base.canonical_json(disclosure))
    base._write_or_verify(root / "receipts" / "provider-free-dry-run.v1.json", base.canonical_json({
        "format_version": 1,
        "study_id": STUDY_ID,
        "provider_calls": 0,
        "full_execution_renderer_prompt_checks": SLOTS,
        "rendered_prompt_lengths": list(EXPECTED_RENDERED_PROMPT_LENGTHS),
        "disclosure_sha256": base.sha256_bytes(base.canonical_json(disclosure)),
    }))
    return {**prepared, "rendered_prompts": SLOTS, "provider_calls": 0, "prompt_privacy": privacy, "evidence_protocol": protocol}
def execute(path: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"allow_remote": allow_remote, "acknowledged_zero_incremental_charge": acknowledged_zero_incremental_charge}
    if runner_call is not None: kwargs["runner_call"] = runner_call
    return _configure().execute(path, **kwargs)
def settle(path: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]: return _configure().settle(path, verifier=verifier)
def command_for(slot: Mapping[str, Any], path: str | Path, *, render: bool = False) -> list[str]: return _configure().command_for(slot, path, render=render)
