"""Sealed, offline verifier for the HANNA batch/polarity development pilot.

This module intentionally has no provider client. A future executor must produce
the committed evidence shape; this verifier is the only path to an analysis.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
from typing import Any
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
ROOT = RESULTS.parent
CONTRACT_PATH = HERE / "study-contract.json"
PAIRS_PATH = HERE / "polarity-pairs.json"
V2_STUDY = RESULTS / "hbq-human-alignment-v2" / "study.py"
PARENT_RUNTIME_RELATIVES = (
    "evaluation-results/hbq-human-alignment-v3-successor-v1/study.py",
    "evaluation-results/hbq-human-alignment-v3-successor-v1/prepare_fresh.py",
    "evaluation-results/hbq-human-alignment-v3-successor-v1/run_fresh.py",
    "evaluation-results/hbq-human-alignment-v3-successor-v1/successor_gate.py",
    "evaluation-results/hbq-human-alignment-v3-successor-v1/study-contract.json",
    "src/hbqrs/__init__.py", "src/hbqrs/paths.py", "src/hbqrs/run_verify.py", "src/hbqrs/runner.py",
    "src/hbqrs/runner_v2.py", "src/hbqrs/core.py", "src/hbqrs/scoring_v2.py", "src/hbqrs/weights.py",
)
STATES = frozenset({"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"})
REVERSE = {"YES": "NO", "NO": "YES", "NOT_APPLICABLE": "NOT_APPLICABLE", "CANNOT_ASSESS": "CANNOT_ASSESS"}
CONDITION_IDS = ("global_positive_batch32", "global_negative_batch32", "single_positive_batch1", "single_negative_batch1")
EXPECTED_CONDITIONS = [
    {"id": "global_positive_batch32", "scope": "global", "polarity": "positive", "negative_question_scope": "none", "batch_size": 32, "leaf_set": "full_short_story"},
    {"id": "global_negative_batch32", "scope": "global", "polarity": "negative_failure_condition", "negative_question_scope": "mapped_leaves_only", "batch_size": 32, "leaf_set": "full_short_story"},
    {"id": "single_positive_batch1", "scope": "focal", "polarity": "positive", "negative_question_scope": "none", "batch_size": 1, "leaf_set": "hanna_mapped"},
    {"id": "single_negative_batch1", "scope": "focal", "polarity": "negative_failure_condition", "negative_question_scope": "mapped_leaves_only", "batch_size": 1, "leaf_set": "hanna_mapped"},
]
EXPECTED_ORDER = [
    ["global_positive_batch32", "global_negative_batch32", "single_positive_batch1", "single_negative_batch1"],
    ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1", "global_positive_batch32"],
    ["single_positive_batch1", "single_negative_batch1", "global_positive_batch32", "global_negative_batch32"],
]


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fingerprint(path: Path) -> dict[str, Any]:
    actual = path.resolve()
    if not actual.is_file():
        raise ValueError(f"Missing bound file: {path}")
    return {"path": str(actual), "bytes": actual.stat().st_size, "sha256": sha256_path(actual)}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def atomic_immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise ValueError(f"Immutable artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(rendered)
            output.flush()
            os.fsync(output.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ValueError(f"Cannot load bound module: {path.name}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def load_contract() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    expected = {
        "format_version", "study_id", "status", "frozen_before_execution", "parent", "conditions",
        "stages", "condition_order", "metrics", "decision_policy", "human_ratings_policy",
    }
    if set(contract) != expected or contract["format_version"] != 1 or contract["study_id"] != "hbq-hanna-batch-polarity-pilot-v1":
        raise ValueError("Pilot contract identity drifted")
    if contract["status"] != "preregistered_development_only_no_empirical_results" or contract["frozen_before_execution"] is not True:
        raise ValueError("Pilot must remain a frozen development-only preregistration")
    parent = contract["parent"]
    if parent != {"study_id": "hbq-human-alignment-v3-successor-v1", "required_phase": "semantic_development_gate", "reused_item_id": "hanna-225", "reused_condition": "global_positive_batch32", "reused_repetition": 1}:
        raise ValueError("Pilot parent binding drifted")
    conditions = contract["conditions"]
    if conditions != EXPECTED_CONDITIONS:
        raise ValueError("Pilot conditions are not frozen")
    expected_stages = [(1, 1, 60), (2, 2, 66), (3, 3, 66)]
    if [(item.get("stage"), item.get("repetition"), item.get("new_calls")) for item in contract["stages"] if isinstance(item, Mapping)] != expected_stages:
        raise ValueError("Pilot staged call geometry drifted")
    order = contract["condition_order"]
    if order != EXPECTED_ORDER:
        raise ValueError("Pilot Latin condition order drifted")
    if contract["decision_policy"].get("recommendation") is not None or contract["decision_policy"].get("promotion") != "forbidden":
        raise ValueError("Pilot cannot contain a recommendation or promotion route")
    adaptive = contract["decision_policy"].get("confidence_adaptive_repeats")
    if contract["decision_policy"].get("later_prefixes") != [1, 4, 12, 24, 40, 80] or adaptive != {
        "status": "future_hypothesis_not_active",
        "requires": ["independent_confidence_calibration", "frozen_threshold_before_outcomes", "equal_call_budget_random_repeat_control", "equal_call_budget_uniform_repeat_control"],
        "evidence": "Every repeat has a separate sealed response and session commitment.",
        "aggregation": "Canonicalize polarity first; use a deterministic predeclared reducer and retain every probe.",
        "production": "No canonical score or coverage change without separate validation.",
        "future_evaluation": "Require equal-budget improvement over random and uniform repeat controls on repeatability and held-out HANNA overlap-dimension alignment.",
        "custom_model_calibration": "Optimize uncertainty calibration and stability/correctness; never directly imitate global HANNA ratings, and keep overlap evaluation on untouched holdouts.",
    }:
        raise ValueError("Pilot later-stage policy drifted")
    return contract


@lru_cache(maxsize=1)
def mapping_sets() -> dict[str, list[str]]:
    return _module(V2_STUDY, "hbq_hanna_batch_polarity_v2_mapping").mapping_sets()


@lru_cache(maxsize=1)
def _focal_question_ids() -> tuple[str, ...]:
    result: list[str] = []
    for values in mapping_sets().values():
        for question_id in values:
            if question_id not in result:
                result.append(question_id)
    if len(result) != 27 or sum(len(values) for values in mapping_sets().values()) != 28:
        raise ValueError("HANNA mapped-leaf geometry drifted")
    return tuple(result)


def focal_question_ids() -> list[str]:
    return list(_focal_question_ids())


def reviewed_pairs() -> list[dict[str, str]]:
    try:
        pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Polarity-pair file is invalid JSON") from error
    if not isinstance(pairs, list) or any(not isinstance(item, dict) or set(item) != {"question_id", "failure_question"} for item in pairs):
        raise ValueError("Polarity-pair schema drifted")
    ids = [item["question_id"] for item in pairs]
    if ids != focal_question_ids() or len(set(ids)) != 27 or any(not isinstance(item["failure_question"], str) or not item["failure_question"].strip() for item in pairs):
        raise ValueError("Reviewed polarity pairs no longer own the exact mapped leaf sequence")
    return pairs


def condition_map() -> dict[str, dict[str, Any]]:
    contract = load_contract()
    result = {str(item["id"]): dict(item) for item in contract["conditions"]}
    if tuple(result) != CONDITION_IDS:
        raise ValueError("Condition order drifted")
    return result


@lru_cache(maxsize=1)
def _full_question_ids() -> tuple[str, ...]:
    identifiers = _module(V2_STUDY, "hbq_hanna_batch_polarity_v2_full_questions").compiled_question_ids()
    if len(identifiers) != 179 or len(set(identifiers)) != 179:
        raise ValueError("Fresh88 full question geometry drifted")
    if set(focal_question_ids()) - set(identifiers):
        raise ValueError("Mapped leaves are absent from the full short-story stack")
    return tuple(identifiers)


def condition_question_ids(condition_id: str) -> list[str]:
    condition = condition_map().get(condition_id)
    if condition is None:
        raise ValueError("Unknown pilot condition")
    return list(_full_question_ids()) if condition["leaf_set"] == "full_short_story" else focal_question_ids()


def physical_call_count(condition_id: str) -> int:
    condition = condition_map()[condition_id]
    return math.ceil(len(condition_question_ids(condition_id)) / int(condition["batch_size"]))


def planned_cells() -> list[dict[str, Any]]:
    contract = load_contract()
    cells: list[dict[str, Any]] = []
    for repetition, order in enumerate(contract["condition_order"], 1):
        for within_repetition, condition_id in enumerate(order, 1):
            reused = condition_id == contract["parent"]["reused_condition"] and repetition == contract["parent"]["reused_repetition"]
            cells.append({
                "stage": repetition,
                "repetition": repetition,
                "within_repetition": within_repetition,
                "condition_id": condition_id,
                "source": "verified_parent_repetition" if reused else "new_provider_evidence",
                "new_calls": 0 if reused else physical_call_count(condition_id),
                "question_ids": condition_question_ids(condition_id),
            })
    expected = [60, 66, 66]
    for repetition, value in enumerate(expected, 1):
        if sum(cell["new_calls"] for cell in cells if cell["repetition"] == repetition) != value:
            raise ValueError("Pilot physical-call geometry drifted")
    return cells


def _runtime_files() -> dict[str, dict[str, Any]]:
    files = [HERE / "study.py", CONTRACT_PATH, PAIRS_PATH, V2_STUDY]
    return {path.relative_to(ROOT).as_posix(): fingerprint(path) for path in files}


def _binding_matches(binding: Mapping[str, Any]) -> bool:
    if set(binding) != {"path", "bytes", "sha256"}:
        return False
    path = Path(str(binding["path"])).resolve()
    return path.is_file() and type(binding["bytes"]) is int and binding["bytes"] == path.stat().st_size and isinstance(binding["sha256"], str) and binding["sha256"] == sha256_path(path)


def _parent_runtime_binding(runtime_root: Path) -> dict[str, Any]:
    root = runtime_root.resolve()
    files = {relative: fingerprint(root / relative) for relative in PARENT_RUNTIME_RELATIVES}
    return {"root": str(root), "files": files, "sha256": sha256_bytes(canonical(files))}


def _valid_parent_runtime(binding: Mapping[str, Any]) -> bool:
    if set(binding) != {"root", "files", "sha256"} or not isinstance(binding.get("root"), str) or not isinstance(binding.get("files"), Mapping):
        return False
    try:
        return binding == _parent_runtime_binding(Path(binding["root"]))
    except ValueError:
        return False


def _route_parent_bound_inputs(parent: Any, parent_work: Path) -> Path:
    """Route frozen verifier code only to the raw plan's already-hashed inputs."""
    raw = read_json(parent_work / "fresh88-execution-contract.json")
    base = raw.get("base_frozen")
    required = {"registry", "bundles", "prompts", "response_schema", "score_v1_schema", "score_v2_schema", "verdict_schema", "task_contract_schema"}
    if not isinstance(base, Mapping) or not required <= set(base) or not isinstance(base.get("prompts"), list) or len(base["prompts"]) != 1:
        raise ValueError("Parent raw plan lacks its canonical input bindings")
    bound = {key: base[key] for key in required - {"prompts"}}
    bound["prompts"] = base["prompts"][0]
    if any(not isinstance(value, Mapping) or not _binding_matches(value) for value in bound.values()):
        raise ValueError("Parent raw plan canonical input binding drifted")
    parent._CANONICAL_BINDING_PATHS = {key: Path(str(value["path"])).resolve() for key, value in bound.items()}
    return Path(str(bound["registry"]["path"])).resolve().parent.parent


def _route_parent_runtime_manifest(parent: Any, parent_work: Path, runtime_root: Path) -> None:
    raw = read_json(parent_work / "fresh88-execution-contract.json")
    manifest = raw.get("base_frozen", {}).get("runtime_manifest")
    files = manifest.get("files") if isinstance(manifest, Mapping) else None
    if not isinstance(files, Mapping) or not isinstance(manifest.get("sha256"), str):
        raise ValueError("Parent raw plan lacks its runtime manifest")
    root = runtime_root.resolve()
    for frozen_path in parent._RUNTIME_FILES:
        relative = Path(frozen_path).resolve().relative_to(root).as_posix()
        matches = [value for key, value in files.items() if Path(str(key)).as_posix().endswith(relative)]
        if len(matches) != 1 or not isinstance(matches[0], Mapping) or matches[0].get("bytes") != Path(frozen_path).stat().st_size or matches[0].get("sha256") != sha256_path(Path(frozen_path)):
            raise ValueError("Frozen parent runtime does not byte-match the raw-plan runtime projection")
    if sha256_bytes(parent.canonical(files)) != manifest["sha256"]:
        raise ValueError("Parent raw runtime manifest commitment drifted")
    parent.runtime_manifest = lambda: dict(manifest)


@contextmanager
def _frozen_parent_runtime(runtime_root: Path):
    root = runtime_root.resolve()
    _parent_runtime_binding(root)
    prefix = str((root / "src").resolve())
    displaced = {name: value for name, value in sys.modules.items() if name == "hbqrs" or name.startswith("hbqrs.")}
    for name in displaced: sys.modules.pop(name, None)
    sys.path.insert(0, prefix)
    try:
        yield _module(root / "evaluation-results" / "hbq-human-alignment-v3-successor-v1" / "study.py", "hbq_hanna_batch_polarity_frozen_parent")
    finally:
        for name in [name for name in sys.modules if name == "hbqrs" or name.startswith("hbqrs.") or name == "hbq_hanna_batch_polarity_frozen_parent"]: sys.modules.pop(name, None)
        sys.path.remove(prefix)
        sys.modules.update(displaced)


def _parent_binding(parent_work: Path, parent_artifacts: Path, parent_authority: Path, parent_runtime_root: Path) -> dict[str, Any]:
    runtime = _parent_runtime_binding(parent_runtime_root)
    with _frozen_parent_runtime(parent_runtime_root) as parent:
        book_root = _route_parent_bound_inputs(parent, parent_work)
        _route_parent_runtime_manifest(parent, parent_work, parent_runtime_root)
        previous_root = os.environ.get("HBQRS_ROOT")
        os.environ["HBQRS_ROOT"] = str(book_root)
        try:
            matrix = parent.verify_matrix(parent_work, parent_authority, parent_artifacts)
            gate = read_json(parent_work / "semantic-development-gate.json")
            if gate.get("phase") != "semantic_development_gate" or gate.get("matrix_sha256") != matrix.get("matrix_sha256"):
                raise ValueError("Parent semantic-development gate is not bound to its verifier matrix")
            plan = parent.load_execution_contract(parent_work, parent_authority)
            parent_cell = next((item for item in plan["cells"] if item["item_id"] == load_contract()["parent"]["reused_item_id"]), None)
            if parent_cell is None:
                raise ValueError("Pinned parent item is missing")
            result = parent._verify_cell(parent_cell, plan["base_frozen"], parent_artifacts)
            run = parent_artifacts / parent_cell["run_dir"] / "run.json"
            score = parent_artifacts / parent_cell["run_dir"] / "score.v2.json"
            verdicts = parent_artifacts / parent_cell["run_dir"] / "verdicts.jsonl"
            sessions = result["result"].get("sessions")
            if not isinstance(sessions, list) or len(sessions) != 6 or any(not isinstance(item, Mapping) or not isinstance(item.get("session_id_sha256"), str) for item in sessions):
                raise ValueError("Parent global batch32 evidence lacks six verified session commitments")
        finally:
            if previous_root is None: os.environ.pop("HBQRS_ROOT", None)
            else: os.environ["HBQRS_ROOT"] = previous_root
    return {
        "parent_runtime": runtime,
        "parent_work": fingerprint(parent_work / "fresh88-execution-contract.json"),
        "parent_matrix": fingerprint(parent_work / "fresh88-verifier-matrix.json"),
        "parent_gate": fingerprint(parent_work / "semantic-development-gate.json"),
        "parent_run": fingerprint(run),
        "parent_score": fingerprint(score),
        "parent_verdicts": fingerprint(verdicts),
        "parent_cell": deepcopy(parent_cell),
        "parent_verifier": result["result"],
    }


def prepare(parent_work: Path, parent_artifacts: Path, parent_authority: Path, parent_runtime_root: Path, work: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Create the immutable study plan. This function never contacts a provider."""
    if not dry_run and work.exists() and any(work.iterdir()):
        raise ValueError("Pilot preparation requires an empty work directory")
    contract = load_contract()
    parent = _parent_binding(parent_work, parent_artifacts, parent_authority, parent_runtime_root)
    runtime = _runtime_files()
    plan = {
        "format_version": 1,
        "study_id": contract["study_id"],
        "study_contract": fingerprint(CONTRACT_PATH),
        "pair_file": fingerprint(PAIRS_PATH),
        "runtime_files": runtime,
        "runtime_sha256": sha256_bytes(canonical(runtime)),
        "parent": parent,
        "parent_sha256": sha256_bytes(canonical(parent)),
        "mapping_sets": mapping_sets(),
        "mapping_sets_sha256": sha256_bytes(canonical(mapping_sets())),
        "pairs_sha256": sha256_bytes(canonical(reviewed_pairs())),
        "cells": planned_cells(),
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "fresh_sessions": True},
        "execution": {"status": "not_implemented_by_this_package", "remote_calls": "forbidden_until_a_distinct_executor_is_reviewed"},
    }
    if dry_run:
        return {"new_calls": sum(cell["new_calls"] for cell in plan["cells"]), "plan": plan}
    atomic_immutable_json(work / "pilot-contract.json", plan)
    return plan


def load_plan(work: Path) -> dict[str, Any]:
    plan = read_json(work / "pilot-contract.json")
    required = {"format_version", "study_id", "study_contract", "pair_file", "runtime_files", "runtime_sha256", "parent", "parent_sha256", "mapping_sets", "mapping_sets_sha256", "pairs_sha256", "cells", "provider", "execution"}
    if set(plan) != required or plan["format_version"] != 1 or plan["study_id"] != load_contract()["study_id"]:
        raise ValueError("Pilot plan schema or identity drifted")
    if not _binding_matches(plan["study_contract"]) or plan["study_contract"] != fingerprint(CONTRACT_PATH) or not _binding_matches(plan["pair_file"]) or plan["pair_file"] != fingerprint(PAIRS_PATH):
        raise ValueError("Pilot contract or reviewed pair binding drifted")
    runtime = _runtime_files()
    if plan["runtime_files"] != runtime or plan["runtime_sha256"] != sha256_bytes(canonical(runtime)):
        raise ValueError("Pilot runtime binding drifted")
    if plan["mapping_sets"] != mapping_sets() or plan["mapping_sets_sha256"] != sha256_bytes(canonical(mapping_sets())) or plan["pairs_sha256"] != sha256_bytes(canonical(reviewed_pairs())):
        raise ValueError("Pilot mapping or polarity-pair binding drifted")
    if plan["cells"] != planned_cells() or plan["provider"] != {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "fresh_sessions": True} or plan["execution"] != {"status": "not_implemented_by_this_package", "remote_calls": "forbidden_until_a_distinct_executor_is_reviewed"}:
        raise ValueError("Pilot execution geometry drifted")
    parent = plan["parent"]
    if not isinstance(parent, Mapping) or set(parent) != {"parent_runtime", "parent_work", "parent_matrix", "parent_gate", "parent_run", "parent_score", "parent_verdicts", "parent_cell", "parent_verifier"} or not _valid_parent_runtime(parent["parent_runtime"]) or any(not _binding_matches(parent[key]) for key in ("parent_work", "parent_matrix", "parent_gate", "parent_run", "parent_score", "parent_verdicts")):
        raise ValueError("Pilot parent evidence binding drifted")
    if plan["parent_sha256"] != sha256_bytes(canonical(parent)):
        raise ValueError("Pilot parent commitment drifted")
    if parent["parent_cell"].get("item_id") != "hanna-225":
        raise ValueError("Pilot parent cell drifted")
    sessions = parent["parent_verifier"].get("sessions") if isinstance(parent["parent_verifier"], Mapping) else None
    if not isinstance(sessions, list) or len(sessions) != 6 or len({item.get("session_id_sha256") for item in sessions if isinstance(item, Mapping)}) != 6:
        raise ValueError("Pilot parent session commitments drifted")
    return plan


def canonicalize_verdict(record: Mapping[str, Any], polarity: str) -> dict[str, Any]:
    if record.get("verdict") not in STATES:
        raise ValueError("Pilot verdict has an invalid state")
    result = deepcopy(dict(record))
    if polarity == "negative_failure_condition":
        result["verdict"] = REVERSE[result["verdict"]]
    elif polarity != "positive":
        raise ValueError("Unknown pilot polarity")
    return result


def question_polarity(condition_id: str, question_id: str) -> str:
    condition = condition_map().get(condition_id)
    if condition is None or question_id not in condition_question_ids(condition_id):
        raise ValueError("Question is not owned by the requested pilot condition")
    if condition["polarity"] == "negative_failure_condition" and question_id in _focal_question_ids():
        return "negative_failure_condition"
    return "positive"


def _chunks(ids: Sequence[str], batch_size: int) -> list[list[str]]:
    return [list(ids[index:index + batch_size]) for index in range(0, len(ids), batch_size)]


@lru_cache(maxsize=1)
def _question_texts() -> dict[str, str]:
    from hbqrs import compile_bundle, load_bundles, load_modules
    from hbqrs.paths import bundles_path, registry_path
    v2 = _module(V2_STUDY, "hbq_hanna_batch_polarity_v2_question_texts")
    sample = v2.HannaItem("hanna-225", "225", "CTRL", "prompt", "story", {key: (3, 3, 3) for key in v2.RATING_DIMENSIONS})
    bundle = next(item for item in load_bundles(bundles_path()) if item["bundle_id"] == "prose.short_story")
    compiled = compile_bundle(load_modules(registry_path()), bundle, task_contract=v2.make_task_contract(sample))
    output = {item["question"]["id"]: item["question"]["text"] for section in ("domain_questions", "hard_gates", "supplemental_questions") for item in compiled[section]}
    output.update({item["question"]["id"]: item["question"]["text"] for group in compiled["penalty_groups"] for item in group["questions"]})
    if set(output) != set(_full_question_ids()):
        raise ValueError("Rendered prompt question sequence drifted")
    return output


def rendered_prompt(plan: Mapping[str, Any], cell: Mapping[str, Any], question_ids: Sequence[str]) -> str:
    """Exact outbound request bytes for a future, separately reviewed executor."""
    condition_id = str(cell["condition_id"])
    parent_cell = plan["parent"]["parent_cell"]
    artifact = parent_cell.get("artifact")
    contexts = parent_cell.get("contexts")
    if not isinstance(artifact, Mapping) or not _binding_matches(artifact) or not isinstance(contexts, list) or not all(isinstance(item, Mapping) and _binding_matches(item) for item in contexts):
        raise ValueError("Rendered prompt source/context binding drifted")
    failures = {item["question_id"]: item["failure_question"] for item in reviewed_pairs()}
    texts = _question_texts()
    questions = []
    for question_id in question_ids:
        polarity = question_polarity(condition_id, question_id)
        questions.append({"question_id": question_id, "canonical_question": texts[question_id], "asked_question": failures[question_id] if polarity == "negative_failure_condition" else texts[question_id], "polarity": polarity})
    return canonical({"study_id": load_contract()["study_id"], "condition_id": condition_id, "repetition": cell["repetition"], "source": Path(str(artifact["path"])).read_text(encoding="utf-8"), "contexts": [Path(str(item["path"])).read_text(encoding="utf-8") for item in contexts], "questions": questions, "response_contract": "JSON array in exact question order; question_id, verdict, confidence only"}).decode("utf-8")


def _validate_cell_evidence(plan: Mapping[str, Any], cell: Mapping[str, Any], evidence: Mapping[str, Any]) -> list[dict[str, Any]]:
    condition = condition_map()[str(cell["condition_id"])]
    required = {"condition_id", "repetition", "calls"}
    if set(evidence) != required or evidence["condition_id"] != cell["condition_id"] or evidence["repetition"] != cell["repetition"] or not isinstance(evidence["calls"], list):
        raise ValueError("Cell evidence does not bind its frozen condition and repetition")
    expected_chunks = _chunks(cell["question_ids"], int(condition["batch_size"]))
    if len(evidence["calls"]) != len(expected_chunks):
        raise ValueError("Cell evidence physical-call count drifted")
    output: list[dict[str, Any]] = []
    seen_sessions: set[str] = set()
    for call, expected_ids in zip(evidence["calls"], expected_chunks, strict=True):
        if not isinstance(call, Mapping) or set(call) != {"question_ids", "session_id_sha256", "prompt", "prompt_sha256", "response", "response_sha256", "verdicts"} or call.get("question_ids") != expected_ids:
            raise ValueError("Call evidence no longer binds the frozen exact question batch")
        if any(not isinstance(call.get(key), str) or len(call[key]) != 64 or any(character not in "0123456789abcdef" for character in call[key]) for key in ("session_id_sha256", "prompt_sha256", "response_sha256")):
            raise ValueError("Call evidence lacks hashed session/prompt/response commitments")
        prompt = rendered_prompt(plan, cell, expected_ids)
        if call.get("prompt") != prompt or call["prompt_sha256"] != sha256_bytes(prompt.encode("utf-8")) or not isinstance(call.get("response"), str) or call["response_sha256"] != sha256_bytes(call["response"].encode("utf-8")):
            raise ValueError("Call evidence prompt or response commitment drifted")
        try:
            parsed = json.loads(call["response"])
        except json.JSONDecodeError as error:
            raise ValueError("Call evidence response is not JSON") from error
        if parsed != call["verdicts"]:
            raise ValueError("Call evidence verdicts are not the parsed response")
        if call["session_id_sha256"] in seen_sessions:
            raise ValueError("Cell evidence reuses a session")
        seen_sessions.add(call["session_id_sha256"])
        verdicts = call.get("verdicts")
        if not isinstance(verdicts, list) or len(verdicts) != len(expected_ids):
            raise ValueError("Call evidence verdict geometry drifted")
        for verdict, question_id in zip(verdicts, expected_ids, strict=True):
            if not isinstance(verdict, Mapping) or set(verdict) != {"question_id", "verdict", "confidence"} or verdict.get("question_id") != question_id or type(verdict.get("confidence")) not in {int, float} or isinstance(verdict.get("confidence"), bool) or not 0 <= float(verdict["confidence"]) <= 1:
                raise ValueError("Call evidence verdict schema drifted")
            output.append(canonicalize_verdict(verdict, question_polarity(str(cell["condition_id"]), question_id)))
    return output


def _parent_verdicts(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(str(plan["parent"]["parent_verdicts"]["path"]))
    if not _binding_matches(plan["parent"]["parent_verdicts"]):
        raise ValueError("Reused parent verdict evidence drifted")
    try:
        raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except json.JSONDecodeError as error:
        raise ValueError("Reused parent verdict evidence is malformed") from error
    ids = condition_question_ids("global_positive_batch32")
    if len(raw) != len(ids):
        raise ValueError("Reused parent verdict count drifted")
    output = []
    for row, question_id in zip(raw, ids, strict=True):
        if not isinstance(row, Mapping) or row.get("question_id") != question_id:
            raise ValueError("Reused parent verdict order drifted")
        output.append(canonicalize_verdict(row, "positive"))
    return output


def verify_evidence(plan: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Verify evidence supplied by a future reviewed executor; no I/O beyond caller data."""
    if plan.get("study_id") != load_contract()["study_id"]:
        raise ValueError("Evidence does not bind this pilot")
    cells = [cell for cell in plan["cells"] if cell["source"] == "new_provider_evidence"]
    by_key = {(str(row.get("condition_id")), row.get("repetition")): row for row in evidence_rows}
    if len(by_key) != len(evidence_rows):
        raise ValueError("Evidence contains duplicate cell keys")
    expected_keys = [(cell["condition_id"], cell["repetition"]) for cell in cells]
    actual_keys = list(by_key)
    if actual_keys != expected_keys[:len(actual_keys)] or len(actual_keys) not in {3, 7, 11}:
        raise ValueError("Evidence must be an ordered complete prefix of the frozen staged plan")
    result: dict[str, list[dict[str, Any]]] = {"global_positive_batch32:1": _parent_verdicts(plan)}
    sessions: set[str] = {item["session_id_sha256"] for item in plan["parent"]["parent_verifier"]["sessions"]}
    for cell in cells:
        key = (cell["condition_id"], cell["repetition"])
        if key in by_key:
            for call in by_key[key]["calls"]:
                session = call.get("session_id_sha256") if isinstance(call, Mapping) else None
                if not isinstance(session, str) or session in sessions:
                    raise ValueError("Pilot evidence reuses a session across cells")
                sessions.add(session)
            result[f"{key[0]}:{key[1]}"] = _validate_cell_evidence(plan, cell, by_key[key])
    if set(by_key) - {(cell["condition_id"], cell["repetition"]) for cell in cells}:
        raise ValueError("Evidence contains an unplanned or parent-reused cell")
    return result


def _rank(values: Sequence[float]) -> list[float]:
    positions = sorted(enumerate(values), key=lambda item: item[1]); result = [0.0] * len(values); start = 0
    while start < len(positions):
        end = start + 1
        while end < len(positions) and positions[end][1] == positions[start][1]: end += 1
        for index, _ in positions[start:end]: result[index] = (start + 1 + end) / 2
        start = end
    return result


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    a, b = statistics.fmean(left), statistics.fmean(right)
    denominator = math.sqrt(sum((x - a) ** 2 for x in left) * sum((y - b) ** 2 for y in right))
    return None if not denominator else sum((x - a) * (y - b) for x, y in zip(left, right)) / denominator


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return _pearson(_rank(left), _rank(right))


def kendall_tau_b(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    concordant = discordant = left_ties = right_ties = 0
    for first in range(len(left)):
        for second in range(first + 1, len(left)):
            a, b = (left[first] > left[second]) - (left[first] < left[second]), (right[first] > right[second]) - (right[first] < right[second])
            if not a and not b: continue
            if not a: left_ties += 1
            elif not b: right_ties += 1
            elif a == b: concordant += 1
            else: discordant += 1
    denominator = math.sqrt((concordant + discordant + left_ties) * (concordant + discordant + right_ties))
    return None if not denominator else (concordant - discordant) / denominator


def correlation_bridge(model_scores: Sequence[float], human_scores: Sequence[float]) -> dict[str, float | None]:
    """Tie-corrected, signed diagnostics; absolute tau is display-only."""
    signed = kendall_tau_b(model_scores, human_scores)
    return {
        "signed_kendall_tau_b": signed,
        "absolute_kendall_tau_b": abs(signed) if signed is not None else None,
        "spearman": spearman(model_scores, human_scores),
    }


def _cell_metrics(verified: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    mappings = mapping_sets()
    for key, rows in verified.items():
        by_id = {str(row["question_id"]): row for row in rows}
        assessed = [row for row in rows if row["verdict"] in {"YES", "NO"}]
        dimensions = {}
        for dimension, ids in mappings.items():
            values = [by_id[item] for item in ids if item in by_id and by_id[item]["verdict"] in {"YES", "NO"}]
            dimensions[dimension] = None if not values else sum(row["verdict"] == "YES" for row in values) / len(values)
        result[key] = {"coverage": len(assessed) / len(rows), "dimensions": dimensions, "verdicts": by_id}
    return result


def _mechanical_changes(cells: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = defaultdict(list)
    for key, value in cells.items():
        condition, repetition = key.rsplit(":", 1); grouped[condition].append((int(repetition), value))
    changes = []
    for condition, rows in grouped.items():
        for (previous_rep, previous), (current_rep, current) in zip(sorted(rows), sorted(rows)[1:], strict=False):
            ids = sorted(set(previous["verdicts"]) & set(current["verdicts"]))
            if not ids: continue
            flips = sum(previous["verdicts"][item]["verdict"] != current["verdicts"][item]["verdict"] for item in ids)
            assessed = sum((previous["verdicts"][item]["verdict"] in {"YES", "NO"}) != (current["verdicts"][item]["verdict"] in {"YES", "NO"}) for item in ids)
            previous_confidence = statistics.fmean(float(previous["verdicts"][item]["confidence"]) for item in ids)
            current_confidence = statistics.fmean(float(current["verdicts"][item]["confidence"]) for item in ids)
            changes.append({"condition_id": condition, "from_repetition": previous_rep, "to_repetition": current_rep, "canonical_leaf_flip_rate": flips / len(ids), "assessed_state_change_rate": assessed / len(ids), "coverage_change": current["coverage"] - previous["coverage"], "confidence_change": current_confidence - previous_confidence, "dimension_score_change": {dimension: None if previous["dimensions"][dimension] is None or current["dimensions"][dimension] is None else current["dimensions"][dimension] - previous["dimensions"][dimension] for dimension in mapping_sets()}})
    return changes


def _factor_contrasts(cells: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    definitions = (("polarity_global", "global_positive_batch32", "global_negative_batch32"), ("polarity_single", "single_positive_batch1", "single_negative_batch1"), ("batch_positive", "global_positive_batch32", "single_positive_batch1"), ("batch_negative", "global_negative_batch32", "single_negative_batch1"))
    result = []
    for repetition in (1, 2, 3):
        for factor, left_name, right_name in definitions:
            left, right = cells.get(f"{left_name}:{repetition}"), cells.get(f"{right_name}:{repetition}")
            if left is None or right is None: continue
            ids = sorted(set(left["verdicts"]) & set(right["verdicts"]))
            if ids:
                result.append({"factor": factor, "repetition": repetition, "common_leaf_count": len(ids), "canonical_leaf_difference_rate": sum(left["verdicts"][item]["verdict"] != right["verdicts"][item]["verdict"] for item in ids) / len(ids), "coverage_change": left["coverage"] - right["coverage"]})
    return result


def metrics(plan: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    verified = verify_evidence(plan, evidence_rows)
    leaves: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, verdicts in verified.items():
        condition, repetition = key.rsplit(":", 1)
        for verdict in verdicts:
            leaves[verdict["question_id"]].append({"condition": condition, "repetition": int(repetition), **verdict})
    stability: dict[str, Any] = {}
    stable_confidence: list[float] = []; flipped_confidence: list[float] = []
    for question_id, rows in sorted(leaves.items()):
        by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows: by_condition[row["condition"]].append(row)
        states = [row["verdict"] for row in rows]
        stable = all(len({row["verdict"] for row in values}) == 1 for values in by_condition.values())
        (stable_confidence if stable else flipped_confidence).extend(float(row["confidence"]) for row in rows)
        stability[question_id] = {"observations": len(rows), "stable_within_condition": stable, "condition_states": {name: [row["verdict"] for row in values] for name, values in sorted(by_condition.items())}, "between_condition_difference": len({row["verdict"] for row in rows}) > 1}
    cell_metrics = _cell_metrics(verified)
    changes = _mechanical_changes(cell_metrics)
    contrasts = _factor_contrasts(cell_metrics)
    return {
        "study_id": plan["study_id"],
        "evidence_cell_count": len(verified),
        "recommendation": None,
        "promotion": "forbidden",
        "correlation_bridge": {**correlation_bridge([], []), "status": "unavailable_one_story"},
        "stability": stability,
        "confidence_by_stability": {"stable_mean": statistics.fmean(stable_confidence) if stable_confidence else None, "flipped_mean": statistics.fmean(flipped_confidence) if flipped_confidence else None, "interpretation": "repeat-consensus diagnostic, not calibrated human truth"},
        "mechanics": {"canonicalization": "negative YES/NO reversed; NOT_APPLICABLE/CANNOT_ASSESS unchanged", "cell_metrics": {key: {"coverage": value["coverage"], "dimensions": value["dimensions"]} for key, value in cell_metrics.items()}, "between_repetition_changes": changes, "factor_contrasts": contrasts},
    }


def stage_gate(plan: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result = metrics(plan, evidence_rows)
    completed = max(int(key.rsplit(":", 1)[1]) for key in result["mechanics"]["cell_metrics"])
    changes = result["mechanics"]["between_repetition_changes"]
    contrasts = result["mechanics"]["factor_contrasts"]
    reproduced_factor_effect = any(sum(item["canonical_leaf_difference_rate"] > 0 or item["coverage_change"] != 0 for item in contrasts if item["factor"] == factor) >= 2 for factor in {item["factor"] for item in contrasts})
    signal = reproduced_factor_effect or any(change["canonical_leaf_flip_rate"] > 0 or change["assessed_state_change_rate"] > 0 or change["coverage_change"] != 0 or abs(change["confidence_change"]) >= 0.10 or any(value not in {None, 0} for value in change["dimension_score_change"].values()) for change in changes)
    if completed == 1:
        status, next_stage = "stage_1_complete", 2
    elif completed == 2:
        status, next_stage = ("stage_3_required_signal", 3) if signal else ("stage_2_stop_no_reproduced_signal", None)
    else:
        status, next_stage = "stage_3_complete_development_only", None
    return {"study_id": plan["study_id"], "completed_stage": completed, "status": status, "next_stage": next_stage, "recommendation": None, "promotion": "forbidden"}


def execute(*_: Any, **__: Any) -> None:
    raise RuntimeError("This protocol package deliberately cannot make provider calls; use a separately reviewed executor.")
