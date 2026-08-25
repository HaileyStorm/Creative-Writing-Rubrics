"""Fresh v6 successor: a minimal one-independent-clause absence control."""
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

ROOT = Path(__file__).resolve().parent; REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v6"
SOURCE_COMMIT = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"; SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
V5_PATH = ROOT.parent / "hbq-poetry-free-verse-repetition-four-state-applicability-treatment-v1-execution-v5" / "study.py"
V5_SHA256 = "4567858d53a479caf9a20dacd9e1c522dd16734d5a942b874a795a9a83362348"; V5_CONTRACT_SHA256 = "99237085400335aa42ea6213d61201b08aab6ac5b30b59244b5d0993b37dbb36"
PROMPT_SOURCE = ROOT / "exact-quote-binary-prompt.md"; PROMPT_SHA256 = "70db54001cdf585717f6151a5eb277c1eae698102f7fd3ed7429fc7ff8071094"
SCHEMA_SOURCE = ROOT / "exact-quote-response.schema.json"; SCHEMA_SHA256 = "25b7563672c08d76f9a978108fc334def213a81211c00520c9cad25fa5a4451e"
CONTROLLER_SHA256 = "fe5897898327877537e9ed0a93884b39daf9ffc56f29bc8d4710ad358ef62f61"; LEDGER_SHA256 = "541fc2f06193fc9266905ea29cf2c30a61655a293c82e47d6cb3e576329a50bf"; VERIFIER_SHA256 = "e8f176bcfac9fc74644cbba8872e4cf1106c2e224913931e1ebc49a34054a9d0"; FIXTURE_SHA256 = {"7eee7bbe1e394a506b88001566786dbf970004bf86d28e7370d517d6f5684c3d", "262c3dbfd3c584462e5b4078e324cf8a3516be5ee9d4ecefb2ce20616d715fa7", "5277854c7cfa6d324c4fd977b43926d5c74fd79a35094c5212a4e0ffc5c4e675", "1fa7859c544799a182a81f374693274dd94e48eb3b264c99f5559467b4e0185c"}
PRIVATE_EXECUTION_DIRECTORY = "execution-v6-preexecution-freeze-v1"; SLOTS, ARMS, REPEATS = 12, ("candidate",), (1, 2, 3)
BUNDLE_ID = "diagnostic.poetry_free_verse_repetition_four_state_applicability_v6"; SUCCESSOR_FILES = ("study.py", "run.py", "study-contract.json", "exact-quote-binary-prompt.md", "exact-quote-response.schema.json")
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?"); COORDINATOR = re.compile(r"\b(?:and|but|or|nor|for|yet|so)\b", re.I)
_CONFIGURED = False; _PROTOCOL_BASE: Callable[[Sequence[Mapping[str, Any]], Mapping[str, bytes]], dict[str, Any]] | None = None

def sha256_file(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

@lru_cache(maxsize=1)
def _v5():
    if not V5_PATH.is_file() or sha256_file(V5_PATH) != V5_SHA256: raise ValueError("Frozen v5 successor drifted")
    contract = V5_PATH.parent / "study-contract.json"
    if not contract.is_file() or sha256_file(contract) != V5_CONTRACT_SHA256: raise ValueError("Frozen v5 lineage contract drifted")
    spec = importlib.util.spec_from_file_location("_s1_four_state_v6_adapter", V5_PATH)
    if spec is None or spec.loader is None: raise ValueError("Frozen v5 successor is unavailable")
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name] = module; spec.loader.exec_module(module)
    return module

def _configure() -> Any:
    global _CONFIGURED, _PROTOCOL_BASE
    value = _v5()
    if _CONFIGURED: return value
    v4 = value._configure(); v3 = v4._v3(); base, v2, v1, clean = v3._base(), v3._v2(), v3._v2()._v1(), v3._v2()._v1()._adapter()
    for module in (value, v4, v3, v2, v1, clean, base):
        module.ROOT = ROOT; module.REPOSITORY = REPOSITORY; module.STUDY_ID = STUDY_ID; module.SOURCE_COMMIT = SOURCE_COMMIT; module.SOURCE_TREE = SOURCE_TREE
        module.CONTROLLER_SHA256 = CONTROLLER_SHA256; module.LEDGER_SHA256 = LEDGER_SHA256; module.VERIFIER_SHA256 = VERIFIER_SHA256
        module.PRIVATE_EXECUTION_DIRECTORY = PRIVATE_EXECUTION_DIRECTORY; module.SLOTS = SLOTS; module.ARMS = ARMS; module.REPEATS = REPEATS; module.BUNDLE_ID = BUNDLE_ID; module.SUCCESSOR_FILES = SUCCESSOR_FILES
        module._private_freeze = _private_freeze; module.validate_package = validate_package
    _PROTOCOL_BASE = v3._protocol_prompt_scan; v3._protocol_prompt_scan = _protocol_prompt_scan; v3._write_protocol_receipt = _write_protocol_receipt; v3._require_protocol_receipt = _require_protocol_receipt
    _CONFIGURED = True
    return value

def one_independent_clause_recurrence_free(text: str) -> None:
    tokens = [token.casefold() for token in TOKEN.findall(text)]
    if len(tokens) < 4 or len(tokens) != len(set(tokens)): raise ValueError("Absence fixture repeats a lexical token")
    if text.count("\n") or len(re.findall(r"[.!?]", text)) != 1: raise ValueError("Absence fixture must be exactly one sentence and one line")
    if any(mark in text for mark in (",", ";", ":", "—")) or COORDINATOR.search(text): raise ValueError("Absence fixture must contain exactly one independent clause")
    if len(list(zip(tokens, tokens[1:]))) != len(set(zip(tokens, tokens[1:]))): raise ValueError("Absence fixture repeats a lexical phrase")

def _private_freeze() -> tuple[dict[str, Any], dict[str, Any]]:
    v3, base = _v5()._v4()._v3(), _v5()._v4()._v3()._base(); controller_path, ledger_path, verifier_path = base._private_paths()
    if any(not path.is_file() or sha256_file(path) != digest for path, digest in ((controller_path, CONTROLLER_SHA256), (ledger_path, LEDGER_SHA256), (verifier_path, VERIFIER_SHA256))): raise ValueError("Private v6 controller, ledger, or verifier drifted")
    controller, ledger = base._load_json(controller_path), base._load_json(ledger_path); fixtures, mappings = controller.get("fixture_matrix"), ledger.get("slot_mapping")
    if (controller.get("study_id") != STUDY_ID or controller.get("format_version") != 6 or controller.get("visibility") != "private_controller_only" or ledger.get("study_id") != STUDY_ID or ledger.get("format_version") != 6 or ledger.get("visibility") != "private_controller_only" or not isinstance(fixtures, list) or len(fixtures) != 4 or not isinstance(mappings, list) or len(mappings) != SLOTS): raise ValueError("Private v6 freeze geometry drifted")
    fixture_ids = {str(item.get("fixture_id")) for item in fixtures}; fixture_hashes = {base.sha256_bytes(str(item.get("text")).encode("utf-8")) for item in fixtures}
    if len(fixture_ids) != 4 or fixture_hashes != FIXTURE_SHA256: raise ValueError("Private v6 fixture commitments drifted")
    absence = [str(item.get("text")) for item in fixtures if item.get("state") == "absence"]
    if len(absence) != 1: raise ValueError("Private v6 requires exactly one absence fixture")
    one_independent_clause_recurrence_free(absence[0])
    opaque_by_fixture: dict[str, str] = {}; geometry: set[tuple[str, int]] = set(); slot_ids: set[str] = set()
    for mapping in mappings:
        fixture_id, artifact_id, slot_id, repeat = str(mapping.get("fixture_id")), str(mapping.get("opaque_artifact_id")), str(mapping.get("opaque_slot_id")), int(mapping.get("repeat"))
        if fixture_id not in fixture_ids or mapping.get("arm") != "candidate" or not v3._v2().OPAQUE_ARTIFACT.fullmatch(artifact_id) or not v3._v2().OPAQUE_SLOT.fullmatch(slot_id) or repeat not in REPEATS: raise ValueError("Private v6 opaque mapping boundary drifted")
        if opaque_by_fixture.setdefault(fixture_id, artifact_id) != artifact_id: raise ValueError("A v6 semantic fixture maps to more than one opaque artifact")
        geometry.add((fixture_id, repeat)); slot_ids.add(slot_id)
    if len(set(opaque_by_fixture.values())) != 4 or geometry != {(item, repeat) for item in fixture_ids for repeat in REPEATS} or len(slot_ids) != SLOTS: raise ValueError("Private v6 opaque schedule is not one-to-one and complete")
    return controller, ledger

def _protocol_prompt_scan(schedule: Sequence[Mapping[str, Any]], prompts: Mapping[str, bytes]) -> dict[str, Any]:
    if _PROTOCOL_BASE is None: raise ValueError("Protocol scanner is unavailable")
    return {**_PROTOCOL_BASE(schedule, prompts), "format_version": 6}
def _write_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    v3 = _v5()._v4()._v3(); receipt = v3._protocol_receipt(root, schedule); v3._base()._write_or_verify(root / "receipts" / "evidence-protocol-scan.v6.json", v3._base().canonical_json(receipt)); return receipt
def _require_protocol_receipt(root: Path, schedule: Sequence[Mapping[str, Any]]) -> None:
    v3 = _v5()._v4()._v3(); path = root / "receipts" / "evidence-protocol-scan.v6.json"
    if not path.is_file() or v3._base()._load_json(path) != v3._protocol_receipt(root, schedule): raise ValueError("Exact v6 evidence-protocol receipt is required before claim")

def contract() -> dict[str, Any]:
    value = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise TypeError("Study contract must be an object")
    return value
def _expected_contract() -> dict[str, Any]:
    prior = json.loads((V5_PATH.parent / "study-contract.json").read_text(encoding="utf-8"))
    return {"format_version": 6, "study_id": STUDY_ID, "status": "frozen_unexecuted_one_independent_clause_successor", "source_checkout": {"commit": SOURCE_COMMIT, "tree": SOURCE_TREE, "exact_head_required_before_claim": True},
        "v5_provider_free_predecessor": {"package_path": V5_PATH.parent.relative_to(REPOSITORY).as_posix(), "executor_sha256": V5_SHA256, "contract_sha256": V5_CONTRACT_SHA256, "study_manifest_sha256": "a517fe20f566d859f1806c743b83f7f3c9085e158af5c2ce59508ea98df410fa", "dry_run_receipt_sha256": "062d02d6f20d4112df8bc522906a048169bd2b4e44c2349fa511280e22b52abd", "prompt_privacy_receipt_sha256": "4f89971cd98c50a94bf7377eba1fbf10d767f801b27fc2a1043597c651b27003", "protocol_receipt_sha256": "6ac778b9cf0ac8354a3124ff848f4b9a3d4457cb325f1876ae47eada0bd6a4a2", "provider_calls": 0, "execution_claim": "none", "disposition": "immutable_zero_call_syntactic_construct_predecessor"},
        "inherited_v4_and_v2_lineage_contract_sha256": V5_CONTRACT_SHA256, "candidate": prior["candidate"], "private_commitments": {"controller_sha256": CONTROLLER_SHA256, "ledger_sha256": LEDGER_SHA256, "verifier_sha256": VERIFIER_SHA256, "fixture_text_sha256": sorted(FIXTURE_SHA256)},
        "absence_construct_gate": {"artifact_text_only": True, "casefolded_lexical_tokens_unique": True, "contiguous_two_token_phrases_unique": True, "single_sentence_single_line": True, "exactly_one_independent_clause": True, "coordinated_or_serial_clause_markers_forbidden": True, "failure": "NO_RESULT_REFREEZE_REQUIRED"}, "evidence_protocol": prior["evidence_protocol"], "identifier_boundary": prior["identifier_boundary"], "geometry": prior["geometry"], "execution": prior["execution"], "gating": prior["gating"], "promotion": "none", "dspy": "not_implemented_runtime"}
def validate_package() -> dict[str, Any]:
    value = _configure(); v3 = value._v4()._v3()
    if contract() != _expected_contract(): raise ValueError("V6 contract or lineage binding drifted")
    if v3._v2()._git("rev-parse", f"{SOURCE_COMMIT}^{{tree}}") != SOURCE_TREE: raise ValueError("Frozen exact source tree is unavailable")
    for path, digest in v3._v2()._v1()._adapter().RUNTIME_SHA256.items():
        if sha256_file(REPOSITORY / path) != digest: raise ValueError(f"Frozen runtime drifted: {path}")
    if sha256_file(PROMPT_SOURCE) != PROMPT_SHA256 or sha256_file(SCHEMA_SOURCE) != SCHEMA_SHA256: raise ValueError("Exact-quote protocol source drifted")
    _private_freeze(); schedule = v3.build_schedule()
    if len(schedule) != SLOTS or any(not v3._v2().OPAQUE_ARTIFACT.fullmatch(slot["fixture_id"]) for slot in schedule): raise ValueError("V6 provider identifiers are not opaque and complete")
    return {"study_id": STUDY_ID, "source_commit": SOURCE_COMMIT, "slots": SLOTS, "provider_calls": 0, "provider_artifacts": 4, "summary_evidence_available": False, "normalization_events_required": 0, "success_authorizes_only": "fresh_disjoint_holdout"}
def set_private_root(path: str | Path) -> Path: return _configure().set_private_root(path)
def build_schedule() -> list[dict[str, Any]]: return _configure()._v4()._v3().build_schedule()
def dry_run(path: str | Path, *, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    value = _configure(); return value.dry_run(path) if runner_call is None else value.dry_run(path, runner_call=runner_call)
def execute(path: str | Path, *, allow_remote: bool = False, acknowledged_zero_incremental_charge: bool = False, runner_call: Callable[..., Any] | None = None) -> dict[str, Any]:
    value = _configure(); kwargs: dict[str, Any] = {"allow_remote": allow_remote, "acknowledged_zero_incremental_charge": acknowledged_zero_incremental_charge}
    if runner_call is not None: kwargs["runner_call"] = runner_call
    return value.execute(path, **kwargs)
def settle(path: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]: return _configure().settle(path, verifier=verifier)
def command_for(slot: Mapping[str, Any], path: str | Path, *, render: bool = False) -> list[str]: return _configure().command_for(slot, path, render=render)
