"""Provider-free v2 freeze; it preserves v1 inputs and replaces only evidence comparison."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
STUDY_ID = "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v2-execution-v2"
SOURCE_HEAD = "6ae9ee0db17dda61bb9adc00a60bcd8072969d5d"
SOURCE_TREE = "16f49b15706852ce64f5688f952b4f968707dc04"
LEAF_ID = "form.poetry.free_verse.repetition"
V1_ROOT = ROOT.parent / "hbq-poetry-free-verse-repetition-incidental-determiner-holdout-v1"
V1_STUDY_SHA256 = "afa5fa98faec2a88999d10af88ab5c0dde72967c51eefeeb625e492c2bb89d53"
V1_TERMINAL_SHA256 = "b711e9557d7e4a763d0600626a7089de332e2760af12f513ab68db37af5eeecc"
V1_CANDIDATE_SHA256 = "6bd8ec3bc0ec8901869a987e9bf0cecfc1160aade2b4984fe4c3de8ad659ae11"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path.name}")
    return value


def _v1() -> Any:
    path = V1_ROOT / "study.py"
    if not path.is_file() or sha(path) != V1_STUDY_SHA256:
        raise ValueError("V1 public study binding drifted")
    spec = importlib.util.spec_from_file_location("s1_incidental_v1_bound", path)
    if spec is None or spec.loader is None:
        raise ValueError("V1 public study is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    return load(ROOT / "study-contract.json")


def inherited_candidate_contract() -> dict[str, str]:
    value = load(V1_ROOT / "study-contract.json")
    candidate = value.get("candidate")
    if not isinstance(candidate, Mapping) or set(candidate) != {"leaf_id", "text"}:
        raise ValueError("V1 candidate contract is malformed")
    normalized = {"leaf_id": str(candidate["leaf_id"]), "text": str(candidate["text"])}
    if normalized["leaf_id"] != LEAF_ID or value.get("candidate_sha256") != V1_CANDIDATE_SHA256:
        raise ValueError("V1 candidate contract commitment drifted")
    if hashlib.sha256(canonical(normalized)).hexdigest() != V1_CANDIDATE_SHA256:
        raise ValueError("V1 candidate contract text drifted")
    return normalized


def candidate_leaf() -> dict[str, Any]:
    candidate = dict(_v1()._base().candidate_leaf())
    inherited = inherited_candidate_contract()
    if candidate.get("id") != LEAF_ID or candidate.get("text") != inherited["text"]:
        raise ValueError("V2 inherited candidate differs from its V1 contract")
    return candidate


def artifact() -> dict[str, str]:
    value = load(ROOT / "public-synthetic-corpus.json").get("artifact")
    if not isinstance(value, Mapping) or set(value) != {"case_id", "text"}:
        raise ValueError("Public artifact is invalid")
    return {"case_id": str(value["case_id"]), "text": str(value["text"])}


def slots() -> list[dict[str, Any]]:
    candidate = candidate_leaf()
    condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 1, "leaf_id": LEAF_ID, "question_sha256": hashlib.sha256(canonical(candidate)).hexdigest()}
    result = [{"slot_id": slot_id, "case_id": artifact()["case_id"], "repeat": repeat, "condition": condition} for slot_id, repeat in (("v2-3d1a", 3), ("v2-7fe4", 1), ("v2-c928", 2))]
    if len({row["slot_id"] for row in result}) != 3 or {row["repeat"] for row in result} != {1, 2, 3}:
        raise ValueError("Fresh v2 opaque schedule drifted")
    return result


def _task(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {"contract_version": 1, "contract_id": f"incidental-determiner-v2-{slot['slot_id']}", "artifact_id": slot["slot_id"], "context": {"artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied poem", "completion_status": "complete", "background": ["Evaluate the recurrence of the determiner ‘the’ across the supplied poem."], "constraints": ["Use only the supplied poem as verdict evidence."], "audience": []}, "preferences": [], "priorities": [], "weighted_goals": [], "binding_requirements": []}


def _override(slot: Mapping[str, Any], task: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "artifact_id": slot["slot_id"], "bundle_id": "poetry_free_verse_repetition_singleton_v2", "task_contract_sha256": hashlib.sha256(canonical(task)).hexdigest(), "contract_id": task["contract_id"], "artifact_kind": "poetry.free_verse", "declared_scope": "complete supplied poem", "compatibility_mode": "reviewed_override", "decision_id": "incidental-determiner-v2-singleton", "reviewer": "hbqrs-reviewed-v1", "reason": "Reviewed compatibility for a supplied poem."}


def _head() -> tuple[str, str]:
    values = []
    for value in ("HEAD", f"{SOURCE_HEAD}^{{tree}}"):
        result = subprocess.run(["git", "rev-parse", value], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
        if result.returncode:
            raise ValueError("CWR source binding is unavailable")
        values.append(result.stdout.strip())
    return values[0], values[1]


def validate_package() -> dict[str, Any]:
    value = contract()
    if value.get("study_id") != STUDY_ID or value.get("status") != "provider_free_frozen_unexecuted" or value.get("source_checkout") != {"commit": SOURCE_HEAD, "tree": SOURCE_TREE} or _head() != (SOURCE_HEAD, SOURCE_TREE):
        raise ValueError("V2 source identity drifted")
    if value.get("predecessor") != {"terminal_sha256": V1_TERMINAL_SHA256, "v1_disposition": "one_accepted_contact_evidence_projection_terminal_no_result"}:
        raise ValueError("V1 terminal lineage drifted")
    candidate = candidate_leaf()
    if artifact() != _v1().artifact() or value.get("candidate") != inherited_candidate_contract() or value.get("candidate_sha256") != V1_CANDIDATE_SHA256:
        raise ValueError("V2 changed an inherited carrier or candidate")
    if hashlib.sha256(canonical(value["candidate"])).hexdigest() != value["candidate_sha256"] or candidate["text"] != value["candidate"]["text"]:
        raise ValueError("V2 candidate text/hash binding drifted")
    if {row["slot_id"] for row in slots()} & {row["slot_id"] for row in _v1().slots()}:
        raise ValueError("V2 reused a v1 opaque slot")
    return {"study_id": STUDY_ID, "provider_calls": 0, "slots": 3, "promotion": "none"}


def _configured_v1() -> Any:
    module = _v1()
    module.ROOT = ROOT
    module.STUDY_ID = STUDY_ID
    module.SOURCE_HEAD = SOURCE_HEAD
    module.SOURCE_TREE = SOURCE_TREE
    module.PREDECESSOR_TERMINAL_SHA256 = V1_TERMINAL_SHA256
    module.contract = contract
    module.artifact = artifact
    module.slots = slots
    module._task = _task
    module._override = _override
    module.validate_package = validate_package
    module.dry_root = lambda: module.WORK_ROOT / "execution-dry-v2" if module.WORK_ROOT is not None else (_ for _ in ()).throw(ValueError("An explicit external private work root is required"))
    return module


def dry_freeze(private_root: str | Path) -> dict[str, Any]:
    return _configured_v1().dry_freeze(private_root)


def _render(slot: Mapping[str, Any], root: Path) -> str:
    return _configured_v1()._render(slot, root)


def validate_checkpoint_prompt(slot_id: str, gzip_path: str | Path) -> dict[str, Any]:
    return _configured_v1().validate_checkpoint_prompt(slot_id, gzip_path)
