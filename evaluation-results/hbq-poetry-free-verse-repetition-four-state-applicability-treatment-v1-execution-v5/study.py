"""Fresh v5 successor: recurrence-free absence control with v4 lineage intact."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v5"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V4_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v4" / "study.py"
V4_SHA256 = "5501083164ae38ecad598c0b53341091f15d902bc45167e7eb3ec7db06c65da7"
V4_CONTRACT_SHA256 = "46d542889e8a12b60875afa8cd65a2d09c434ed4fe6c71d46138dc0dcdafc941"
PROMPT_SOURCE = ROOT / "exact-quote-binary-prompt.md"
PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SOURCE = ROOT / "exact-quote-response.schema.json"
SCHEMA_SHA256 = "25b7563672c08d76f9a978108fc334def213a81211c00520c9cad25fa5a4451e"
CONTROLLER_SHA256 = "2b5385aaa8a388191ca1901b84e45b3e550430b3b602921ebe6c42f082ecc4b9"
LEDGER_SHA256 = "35fc0f0e00b87d243d367271f702920cca62075684adbe7174a9da5cc4e0967d"
VERIFIER_SHA256 = "a08d6897943c49222d1b4a53a7167b3ce40421aa08ae1223f36c6553f30a8673"
FIXTURE_SHA256 = {"c48c61280df3bf1f9fb0889fa6794d96f4d1199cfdc8c934e5f05769222d7cea", "262c3dbfd3c584462e5b4078e324cf8a3516be5ee9d4ecefb2ce20616d715fa7", "5277854c7cfa6d324c4fd977b43926d5c74fd79a35094c5212a4e0ffc5c4e675", "1fa7859c544799a182a81f374693274dd94e48eb3b264c99f5559467b4e0185c"}
PRIVATE_EXECUTION_DIRECTORY = "execution-v5-preexecution-freeze-v1"
SLOTS, ARMS, REPEATS = 12, ("candidate",), (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v5"
SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json", "exact-quote-binary-prompt.md", "exact-quote-response.schema.json")
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_CONFIGURED = False
_PROTOCOL_BASE: Callable[[Sequence[Mapping[str, Any]], Mapping[str, bytes]], dict[str, Any]] | None = None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def _v4():
    if not V4_PATH.is_file() or sha256_file(V4_PATH) != V4_SHA256:
        raise ValueError("Frozen v4 successor drifted")
    contract = V4_PATH.parent / "study-contract.json"
    if not contract.is_file() or sha256_file(contract) != V4_CONTRACT_SHA256:
        raise ValueError("Frozen v4 lineage contract drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v5_adapter", V4_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("Frozen v4 successor is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _configure() -> Any:
    global _CONFIGURED, _PROTOCOL_BASE
    value = _v4()
    if _CONFIGURED:
        return value
    v3 = value._configure()
    base, v2, v1, clean = v3._base(), v3._v2(), v3._v2()._v1(), v3._v2()._v1()._adapter()
    for module in (value, v3, v2, v1, clean, base):
        module.ROOT = ROOT; module.REPOSITORY = REPOSITORY; module.STUDY_ID = STUDY_ID
        module.SOURCE_COMMIT = SOURCE_COMMIT; module.SOURCE_TREE = SOURCE_TREE
        module.CONTROLLER_SHA256 = CONTROLLER_SHA256; module.LEDGER_SHA256 = LEDGER_SHA256; module.VERIFIER_SHA256 = VERIFIER_SHA256
        module.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY; module.SLOTS = SLOTS; module.ARMS = ARMS; module.REPEATS = REPEATS
        module.BUNDLE_ID = BUNDLE_ID; module.SUCCESSOR_FILES = SUCCESSOR_FILES
    _PROTOCOL_BASE = v3._protocol_prompt_scan
    for module in (value, v3, v2, v1, clean, base):
        module._private_freeze = _private_freeze
        module.validate_package = validate_package
    v3._protocol_prompt_scan = _protocol_prompt_scan
    v3._write_protocol_receipt = _write_protocol_receipt
    v3._require_protocol_receipt = _require_protocol_receipt
    _CONFIGURED = True
    return value


def recurrence_free_absence_text(text: str) -> None:
    tokens = [token.casefold() for token in TOKEN.findall(text)]
    if len(tokens) < 4 or len(tokens) != len(set(tokens)):
        raise ValueError("Absence fixture repeats a lexical token")
    bigrams = list(zip(tokens, tokens[1:]))
    if len(bigrams) != len(set(bigrams)):
        raise ValueError("Absence fixture repeats a lexical phrase")
    if text.count("\n") or len(re.findall(r"[.!?]", text)) != 1:
        raise ValueError("Absence fixture must remain a single-sentence, single-line control")


def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    v3, base = _v4()._v3(), _v4()._v3()._base()
    controller_path, ledger_path, verifier_path = base._private_paths()
    expected = ((controller_path, CONTROLLER_SHA256), (ledger_path, LEDGER_SHA256), (verifier_path, VERIFIER_SHA256))
    if any(not path.is_file() or sha256_file(path) != digest for path, digest in expected):
        raise ValueError("Private v5 controller, ledger, or verifier drifted")
    controller, ledger = base._load_json(controller_path), base._load_json(ledger_path)
    fixtures, mappings = controller.get("fixture_matrix"), ledger.get("slot_mapping")
    if (controller.get("study_id") != STUDY_ID or controller.get("format_version") != 5 or controller.get("visibility") != "private_controller_only" or
            ledger.get("study_id") != STUDY_ID or ledger.get("format_version") != 5 or ledger.get("visibility") != "private_controller_only" or
            not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(mappings, list) or len(mappings) != SLOTS):
        raise ValueError("Private v5 freeze geometry drifted")
    fixture_ids = {str(item.get("fixture_id")) for item in fixtures}
    fixture_hashes = {base.sha256_bytes(str(item.get("text")).encode("utf-8")) for item in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256:
        raise ValueError("Private v5 fixture commitments drifted")
    absence = [str(item.get("text")) for item in fixtures if item.get("state") == "absence"]
    if len(absence) != 1:
        raise ValueError("Private v5 requires exactly one absence fixture")
    recurrence_free_absence_text(absence[0])
    opaque_by_fixture: dict[str, str] = {}; geometry: set[tuple[str, int]] = set(); slot_ids: set[str] = set()
    for mapping in mappings:
        fixture_id, artifact_id, slot_id, repeat = str(mapping.get("fixture_id")), str(mapping.get("opaque_artifact_id")), str(mapping.get("opaque_slot_id")), int(mapping.get("repeat"))
        if (fixture_id not in fixture_ids or mapping.get("arm") != "candidate" or not v3._v2().OPAQUE_ARTIFACT.fullmatch(artifact_id) or not v3._v2().OPAQUE_SLOT.fullmatch(slot_id) or repeat not in REPEATS):
            raise ValueError("Private v5 opaque mapping boundary drifted")
        if opaque_by_fixture.setdefault(fixture_id, artifact_id) != artifact_id:
            raise ValueError("A v5 semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat)); slot_ids.add(slot_id)
    if len(set(opaque_by_fixture.values())) != 4 or geometry != {(item, repeat) for item in fixture_ids for repeat in REPEATS} or len(slot_ids) != SLOTS:
        raise ValueError("Private v5 opaque schedule is not one-to-one and complete")
    return controller, ledger


def _protocol_prompt_scan(schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> dict[str, Any]:
    if _PROTOCOL_BASE is None:
        raise ValueError("Protocol scanner is unavailable")
    return {**_PROTOCOL_BASE(schedule, prompts), "format_version": 5}


def _write_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    v3 = _v4()._v3(); receipt = v3._protocol_receipt(root, schedule)
    v3._base()._write_or_verify(root / "receipts" / "evidence-protocol-scan.v5.json", v3._base().canonical_json(receipt))
    return receipt


def _require_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    v3 = _v4()._v3(); path = root / "receipts" / "evidence-protocol-scan.v5.json"
    if not path.is_file() or v3._base()._load_json(path) != v3._protocol_receipt(root, schedule):
        raise ValueError("Exact v5 evidence-protocol receipt is required before claim")


def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise TypeError("Study contract must be an object")
    return value


def _expected_contract() -> dict[str, Any]:
    v4_contract = json.loads((V4_PATH.parent / "study-contract.json").read_text(encoding="utf-8"))
    return {
        "format_version": 5, "study_id": STUDY_ID, "status": "frozen_unexecuted_recurrence_free_absence_successor",
        "source_checkout": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "exact_head_required_before_claim": True},
        "v4_provider_free_predecessor": {"package_path": V4_PATH.parent.relative_to(REPOSITORY).as_posix(), "executor_sha256": V4_SHA256, "contract_sha256": V4_CONTRACT_SHA256,
            "study_manifest_sha256": "ab25af16fe1f41a52df6e118360acc6c2a7adf70d96ca94b480ca3ff2cf6c130", "dry_run_receipt_sha256": "cc2d6aa854ab7f6ad9a3a40564abfdda7fa0a4abf4920dc7e19961a6c891d99a",
            "prompt_privacy_receipt_sha256": "3362e3dcfaefffa8e1bb69265cbdf8a806c289aa7d611dce11a69a9854416813", "protocol_receipt_sha256": "af8038cd6c55134358a8561fc1b6324d281b43c4f4190678746c9f5b6d21fcd8",
            "provider_calls": 0, "execution_claim": "none", "disposition": "immutable_zero_call_construct_purity_predecessor"},
        "v2_historical_preexecution_snapshot": v4_contract["v2_historical_preexecution_snapshot"], "v2_current_outcome_binding": v4_contract["v2_current_outcome_binding"], "candidate": v4_contract["candidate"],
        "private_commitments": {"controller_sha256": CONTROLLER_SHA256, "ledger_sha256": LEDGER_SHA256, "verifier_sha256": VERIFIER_SHA256, "fixture_text_sha256": sorted(FIXTURE_SHA256)},
        "absence_construct_gate": {"artifact_text_only": True, "casefolded_lexical_tokens_unique": True, "contiguous_two_token_phrases_unique": True, "single_sentence_single_line": True, "failure": "NO_RESULT_REFREEZE_REQUIRED"},
        "evidence_protocol": v4_contract["evidence_protocol"], "identifier_boundary": v4_contract["identifier_boundary"], "geometry": v4_contract["geometry"], "execution": v4_contract["execution"], "gating": v4_contract["gating"], "promotion": "none", "dspy": "not_implemented_runtime"}


def validate_package() -> dict[str, Any]:
    value = _configure(); v3 = value._v3()
    if contract() != _expected_contract(): raise ValueError("V5 contract or lineage binding drifted")
    if v3._v2()._git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE: raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in v3._v2()._v1()._adapter().RUNTIME_SHA256.items():
        if sha256_file(REPOSITORY / path) != digest: raise ValueError(f"Frozen runtime drifted: {path}")
    if sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or sha256_file(SCHEMA_SOURCE) != SCHEMA_SHA256: raise ValueError("Exact-quote protocol source drifted")
    _private_freeze(); schedule = v3.build_schedule()
    if len(schedule) != SLOTS or any(not v3._v2().OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule): raise ValueError("V5 provider identifiers are not opaque and complete")
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "provider_artifacts": 4, "summary_evidence_available": False, "normalization_events_required": 0, "success_authorizes_only": "fresh_disjoint_holdout"}


def set_private_root(path: str | Path) -> Path: return _configure().set_private_root(path)
def build_schedule() -> list[dict[str, Any]]: return _configure()._v3().build_schedule()
def dry_run(path: str | Path, *, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    value = _configure(); return value.dry_run(path) if runner_call is None else value.dry_run(path, runner_call=runner_call)
def execute(path: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    value = _configure(); kwargs: dict[str, Any] = {"allow_remote": allow_remote, "acknowledged_zero_incremental_charge": acknowledged_zero_incremental_charge}
    if runner_call is not None: kwargs["runner_call"] = runner_call
    return value.execute(path, **kwargs)
def settle(path: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]: return _configure().settle(path, verifier=verifier)
def command_for(slot: Mapping[str, Any], path: str | Path, *, render: bool = False) -> list[str]: return _configure().command_for(slot, path, render=render)
