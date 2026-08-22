"""Offline plan and evidence verifier for the sealed HANNA four-story expansion.

This module has no provider client.  The separate executor accepts an injected,
reviewed callback; no command in this package can contact a provider by itself.
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


HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
ROOT = RESULTS.parent
CONTRACT_PATH = HERE / "study-contract.json"
RESPONSE_SCHEMA_PATH = HERE / "response.schema.json"
PILOT_PATH = RESULTS / "hbq-hanna-batch-polarity-pilot-v1" / "study.py"
REPEATABILITY_AUTHORITY_PATH = HERE / "freeze_repeatability_authority.py"
PLAN_NAME = "expansion-contract.json"
REUSED_MATRIX_NAME = "hanna-225-reused-verified.json"
STORIES = ("hanna-225", "hanna-178", "hanna-817", "hanna-382")
NEW_STORIES = STORIES[1:]
CONDITIONS = (
    "global_positive_batch32", "global_negative_batch32",
    "single_positive_batch1", "single_negative_batch1",
)
LATIN_ROWS = {
    "L0": list(CONDITIONS),
    "L1": ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1", "global_positive_batch32"],
    "L2": ["single_positive_batch1", "single_negative_batch1", "global_positive_batch32", "global_negative_batch32"],
    "L3": ["single_negative_batch1", "global_positive_batch32", "global_negative_batch32", "single_positive_batch1"],
}
STORY_ROWS = {
    "hanna-225": ["L0", "L1", "L2"], "hanna-178": ["L1", "L2", "L3"],
    "hanna-817": ["L2", "L3", "L0"], "hanna-382": ["L3", "L0", "L1"],
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    actual = path.resolve()
    if not actual.is_file():
        raise ValueError(f"Missing bound file: {path}")
    return {"path": str(actual), "bytes": actual.stat().st_size, "sha256": sha256_bytes(actual.read_bytes())}


def _matches(binding: Any) -> bool:
    if not isinstance(binding, Mapping) or set(binding) != {"path", "bytes", "sha256"}:
        return False
    path = Path(str(binding["path"])).resolve()
    return path.is_file() and type(binding["bytes"]) is int and binding["bytes"] == path.stat().st_size and binding["sha256"] == sha256_bytes(path.read_bytes())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate object key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON constant: {value}")


def _reject_non_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON number")
    if isinstance(value, Mapping):
        for item in value.values():
            _reject_non_finite(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite(item)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        _reject_non_finite(value)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Immutable artifact drifted: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text); out.flush(); os.fsync(out.fileno())
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _paths_disjoint(*paths: Path) -> bool:
    resolved = [path.resolve() for path in paths]
    return len(resolved) == len(set(resolved)) and all(
        left not in right.parents and right not in left.parents
        for index, left in enumerate(resolved)
        for right in resolved[index + 1:]
    )


def _module(path: Path, name: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ValueError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def pilot() -> Any:
    return _module(PILOT_PATH, "hbq_hanna_batch_polarity_expansion_pilot")


@lru_cache(maxsize=1)
def repeatability_authority() -> Any:
    return _module(REPEATABILITY_AUTHORITY_PATH, "hbq_hanna_batch_polarity_expansion_authority")


def load_contract() -> dict[str, Any]:
    contract = read_json(CONTRACT_PATH)
    required = {
        "format_version", "study_id", "status", "frozen_before_execution", "parent_study", "stories", "reused_story",
        "new_stories", "conditions", "latin_rows", "story_rows", "geometry", "twelfth_story_rule", "metrics",
        "human_ratings_policy", "decision_policy",
    }
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != "hbq-hanna-batch-polarity-expansion-v1":
        raise ValueError("Expansion contract identity drifted")
    if contract["status"] != "preregistered_development_only_no_empirical_results" or contract["frozen_before_execution"] is not True:
        raise ValueError("Expansion must remain preregistered and development-only")
    if tuple(contract["stories"]) != STORIES or tuple(contract["new_stories"]) != NEW_STORIES or contract["reused_story"] != STORIES[0]:
        raise ValueError("Frozen story universe drifted")
    if contract["conditions"] != list(CONDITIONS) or contract["latin_rows"] != LATIN_ROWS or contract["story_rows"] != STORY_ROWS:
        raise ValueError("Frozen Latin geometry drifted")
    if contract["geometry"] != {"calls_per_story": 198, "reused_calls": 198, "new_provider_calls": 594, "combined_session_commitments": 792}:
        raise ValueError("Expansion call geometry drifted")
    rule = contract["twelfth_story_rule"]
    if not isinstance(rule, Mapping) or rule.get("status") != "frozen_before_expansion_execution" or rule.get("existing_prefix_size") != 11 or rule.get("result_is_not_used_by_this_four_story_package") is not True:
        raise ValueError("Twelfth-story freeze rule drifted")
    decision = contract["decision_policy"]
    if decision != {"recommendation": None, "promotion": "forbidden", "automatic_follow_on": "forbidden", "outcome_dependent_selection": "forbidden"}:
        raise ValueError("Expansion cannot contain a promotion path")
    return contract


def _condition(condition_id: str) -> dict[str, Any]:
    values = pilot().condition_map()
    if condition_id not in values:
        raise ValueError("Unknown frozen condition")
    return values[condition_id]


def _question_ids(condition_id: str) -> list[str]:
    return pilot().condition_question_ids(condition_id)


def _call_count(condition_id: str) -> int:
    value = _condition(condition_id)
    return math.ceil(len(_question_ids(condition_id)) / int(value["batch_size"]))


def planned_cells() -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for story_id in STORIES:
        for repetition, row_name in enumerate(STORY_ROWS[story_id], 1):
            for within_repetition, condition_id in enumerate(LATIN_ROWS[row_name], 1):
                reused = story_id == STORIES[0]
                cells.append({
                    "story_id": story_id, "repetition": repetition, "latin_row": row_name,
                    "within_repetition": within_repetition, "condition_id": condition_id,
                    "source": "reused_complete_pilot_matrix" if reused else "new_provider_evidence",
                    "new_calls": 0 if reused else _call_count(condition_id),
                    "question_ids": _question_ids(condition_id),
                })
    if len(cells) != 48 or sum(cell["new_calls"] for cell in cells) != 594:
        raise ValueError("Expansion physical-call geometry drifted")
    for story_id in STORIES:
        if sum(cell["new_calls"] for cell in cells if cell["story_id"] == story_id) != (0 if story_id == STORIES[0] else 198):
            raise ValueError("Per-story call geometry drifted")
    return cells


def _runtime_files() -> dict[str, dict[str, Any]]:
    files = [
        HERE / "study.py", CONTRACT_PATH, HERE / "response.schema.json",
        REPEATABILITY_AUTHORITY_PATH, HERE / "repeatability-authority-contract.json",
        HERE / "run_expansion.py", HERE / "run_expansion_live.py",
        ROOT / "src" / "hbqrs" / "runner.py", PILOT_PATH,
    ]
    return {path.relative_to(ROOT).as_posix(): fingerprint(path) for path in files}


def _frozen_twelfth(authority_path: Path) -> dict[str, Any]:
    """Select the twelfth ID only from a frozen ordered, pre-outcome authority."""
    authority = repeatability_authority().verify_authority(authority_path)
    ordered, first_eleven = authority["ordered_story_ids"], authority["first_eleven_story_ids"]
    return {"authority": fingerprint(authority_path), "first_eleven_story_ids": first_eleven, "twelfth_story_id": ordered[11]}


def _fresh_parent_inputs(parent_work: Path, parent_artifacts: Path, parent_authority: Path, parent_runtime_root: Path, story_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Replay the frozen Fresh88 verifier before reusing only its bound inputs."""
    p = pilot()
    runtime = p._parent_runtime_binding(parent_runtime_root)
    with p._frozen_parent_runtime(parent_runtime_root) as parent:
        book_root = p._route_parent_bound_inputs(parent, parent_work)
        p._route_parent_runtime_manifest(parent, parent_work, parent_runtime_root)
        prior = os.environ.get("HBQRS_ROOT"); os.environ["HBQRS_ROOT"] = str(book_root)
        try:
            matrix = parent.verify_matrix(parent_work, parent_authority, parent_artifacts)
            gate = read_json(parent_work / "semantic-development-gate.json")
            if gate.get("matrix_sha256") != matrix.get("matrix_sha256"):
                raise ValueError("Fresh88 parent gate is not bound to its matrix")
            execution = parent.load_execution_contract(parent_work, parent_authority)
            cells = {str(cell.get("item_id")): cell for cell in execution["cells"]}
            result: dict[str, dict[str, Any]] = {}
            for story_id in story_ids:
                cell = cells.get(story_id)
                if cell is None:
                    raise ValueError(f"Frozen Fresh88 parent lacks {story_id}")
                verified = parent._verify_cell(cell, execution["base_frozen"], parent_artifacts)
                result[story_id] = {"cell": deepcopy(cell), "verified_run": verified}
        finally:
            if prior is None: os.environ.pop("HBQRS_ROOT", None)
            else: os.environ["HBQRS_ROOT"] = prior
    return {
        "runtime": runtime,
        "parent_work": fingerprint(parent_work / "fresh88-execution-contract.json"),
        "parent_matrix": fingerprint(parent_work / "fresh88-verifier-matrix.json"),
        "parent_gate": fingerprint(parent_work / "semantic-development-gate.json"),
        "stories": result,
    }


def _pilot_binding(pilot_work: Path, pilot_private_root: Path) -> dict[str, Any]:
    p = pilot(); plan = p.load_plan(pilot_work)
    raw = read_json(pilot_private_root / "stage3-raw-evidence.json")
    rows = raw.get("rows")
    if not isinstance(rows, list) or len(rows) != 11:
        raise ValueError("Completed pilot lacks its full three-repetition raw evidence")
    verified = p.verify_evidence(plan, rows)
    parent_sessions = plan["parent"]["parent_verifier"].get("sessions")
    if not isinstance(parent_sessions, list):
        raise ValueError("Completed pilot lacks parent session commitments")
    sessions = [item.get("session_id_sha256") for item in parent_sessions if isinstance(item, Mapping)]
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("calls"), list):
            raise ValueError("Completed pilot raw evidence has malformed calls")
        sessions.extend(call.get("session_id_sha256") for call in row["calls"] if isinstance(call, Mapping))
    verdict_count = sum(len(value) for value in verified.values())
    if len(verified) != 12 or len(sessions) != 198 or len(set(sessions)) != 198 or any(not isinstance(value, str) or len(value) != 64 for value in sessions):
        raise ValueError("Pilot matrix is not the complete 198-call commitment")
    return {
        "pilot_plan": fingerprint(pilot_work / "pilot-contract.json"),
        "pilot_stage3_raw_evidence": fingerprint(pilot_private_root / "stage3-raw-evidence.json"),
        "verified_cell_count": len(verified), "verdict_count": verdict_count, "reused_calls": 198,
        "session_commitments": sessions, "verified": verified,
        "source_cell": deepcopy(plan["parent"]["parent_cell"]),
    }


def _persist_reused_matrix(private_root: Path, reuse: Mapping[str, Any]) -> dict[str, Any]:
    matrix = {
        "format_version": 1, "study_id": load_contract()["study_id"], "story_id": STORIES[0],
        "pilot_plan": reuse["pilot_plan"], "pilot_stage3_raw_evidence": reuse["pilot_stage3_raw_evidence"],
        "cells": reuse["verified"], "session_commitments": reuse["session_commitments"],
        "session_count": 198, "verdict_count": reuse["verdict_count"],
    }
    path = private_root / REUSED_MATRIX_NAME
    immutable_json(path, matrix)
    return fingerprint(path)


def load_reused_matrix(plan: Mapping[str, Any]) -> dict[str, Any]:
    reuse = plan.get("pilot_reuse")
    if not isinstance(reuse, Mapping) or not _matches(reuse.get("matrix")):
        raise ValueError("Expansion plan lacks its persisted reused-matrix binding")
    matrix = read_json(Path(str(reuse["matrix"]["path"])))
    required = {"format_version", "study_id", "story_id", "pilot_plan", "pilot_stage3_raw_evidence", "cells", "session_commitments", "session_count", "verdict_count"}
    if set(matrix) != required or matrix["format_version"] != 1 or matrix["study_id"] != load_contract()["study_id"] or matrix["story_id"] != STORIES[0]:
        raise ValueError("Persisted reused matrix identity drifted")
    if matrix["pilot_plan"] != reuse.get("pilot_plan") or matrix["pilot_stage3_raw_evidence"] != reuse.get("pilot_stage3_raw_evidence"):
        raise ValueError("Persisted reused matrix parent binding drifted")
    expected_keys = {f"{condition}:{repetition}" for condition in CONDITIONS for repetition in (1, 2, 3)}
    sessions = matrix["session_commitments"]
    if (not isinstance(matrix["cells"], Mapping) or set(matrix["cells"]) != expected_keys or not isinstance(sessions, list)
            or matrix["session_count"] != 198 or len(sessions) != 198 or len(set(sessions)) != 198
            or any(not isinstance(value, str) or len(value) != 64 for value in sessions)):
        raise ValueError("Persisted reused matrix is incomplete")
    verdict_count = sum(len(value) for value in matrix["cells"].values() if isinstance(value, list))
    if matrix["verdict_count"] != verdict_count or any(not isinstance(value, list) for value in matrix["cells"].values()):
        raise ValueError("Persisted reused matrix verdict geometry drifted")
    return matrix


def bound_private_root(plan: Mapping[str, Any]) -> Path:
    """The persisted hanna-225 matrix is the expansion's private-root binding."""
    reuse = plan.get("pilot_reuse")
    if not isinstance(reuse, Mapping) or not _matches(reuse.get("matrix")):
        raise ValueError("Expansion plan lacks its persisted reused-matrix binding")
    return Path(str(reuse["matrix"]["path"])).resolve().parent


def prepare(pilot_work: Path, pilot_private_root: Path, parent_work: Path, parent_artifacts: Path, parent_authority: Path, parent_runtime_root: Path, repeatability_authority: Path, work: Path, private_root: Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Bind every source and the twelfth selector without contacting a provider."""
    if not _paths_disjoint(work, private_root):
        raise ValueError("Expansion public work and private roots must be disjoint")
    if not dry_run and work.exists() and any(work.iterdir()):
        raise ValueError("Expansion preparation requires an empty work directory")
    if not dry_run and private_root.exists() and any(private_root.iterdir()):
        raise ValueError("Expansion preparation requires an empty private root")
    reuse = _pilot_binding(pilot_work, pilot_private_root)
    parent = _fresh_parent_inputs(parent_work, parent_artifacts, parent_authority, parent_runtime_root, NEW_STORIES)
    sources = {STORIES[0]: reuse["source_cell"]}
    sources.update({story_id: parent["stories"][story_id]["cell"] for story_id in NEW_STORIES})
    matrix_binding = _persist_reused_matrix(private_root, reuse) if not dry_run else None
    pilot_reuse = {key: value for key, value in reuse.items() if key not in {"verified", "session_commitments", "verdict_count"}}
    if matrix_binding is not None:
        pilot_reuse["matrix"] = matrix_binding
    plan = {
        "format_version": 1, "study_id": load_contract()["study_id"], "study_contract": fingerprint(CONTRACT_PATH),
        "runtime_files": _runtime_files(), "runtime_sha256": sha256_bytes(canonical(_runtime_files())),
        "pilot_reuse": pilot_reuse,
        "pilot_reuse_sha256": sha256_bytes(canonical(pilot_reuse)),
        "fresh_parent": parent, "fresh_parent_sha256": sha256_bytes(canonical(parent)),
        "sources": sources, "twelfth_story": _frozen_twelfth(repeatability_authority),
        "cells": planned_cells(),
        "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "fresh_sessions": True},
        "execution": {"remote_calls": "forbidden_until_separate_executor_review", "attempts_per_new_call": 1, "restart": "replay_only_or_freeze"},
    }
    if dry_run:
        return {"new_provider_calls": 594, "combined_session_commitments": 792, "plan": plan}
    immutable_json(work / PLAN_NAME, plan)
    return plan


def load_plan(work: Path) -> dict[str, Any]:
    plan = read_json(work / PLAN_NAME)
    required = {"format_version", "study_id", "study_contract", "runtime_files", "runtime_sha256", "pilot_reuse", "pilot_reuse_sha256", "fresh_parent", "fresh_parent_sha256", "sources", "twelfth_story", "cells", "provider", "execution"}
    if set(plan) != required or plan["format_version"] != 1 or plan["study_id"] != load_contract()["study_id"]:
        raise ValueError("Expansion plan schema or identity drifted")
    if plan["study_contract"] != fingerprint(CONTRACT_PATH) or plan["runtime_files"] != _runtime_files() or plan["runtime_sha256"] != sha256_bytes(canonical(_runtime_files())):
        raise ValueError("Expansion runtime binding drifted")
    if plan["cells"] != planned_cells() or plan["provider"] != {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "fresh_sessions": True} or plan["execution"] != {"remote_calls": "forbidden_until_separate_executor_review", "attempts_per_new_call": 1, "restart": "replay_only_or_freeze"}:
        raise ValueError("Expansion plan geometry drifted")
    if not all(_matches(item) for item in (plan["study_contract"], *plan["runtime_files"].values())):
        raise ValueError("Expansion plan has invalid file commitments")
    if plan["pilot_reuse_sha256"] != sha256_bytes(canonical(plan["pilot_reuse"])) or plan["fresh_parent_sha256"] != sha256_bytes(canonical(plan["fresh_parent"])):
        raise ValueError("Expansion parent commitment drifted")
    if set(plan["sources"]) != set(STORIES) or any(not isinstance(value, Mapping) or value.get("item_id") != story for story, value in plan["sources"].items()):
        raise ValueError("Expansion source bindings drifted")
    expected_sources = {STORIES[0]: plan["pilot_reuse"].get("source_cell")}
    expected_sources.update({story: plan["fresh_parent"].get("stories", {}).get(story, {}).get("cell") for story in NEW_STORIES})
    if plan["sources"] != expected_sources:
        raise ValueError("Expansion sources are not the exact replayed parent cells")
    for source in plan["sources"].values():
        if not _matches(source.get("artifact")) or not isinstance(source.get("contexts"), list) or not all(_matches(value) for value in source["contexts"]):
            raise ValueError("Expansion source file commitments drifted")
    if not _matches(plan["twelfth_story"].get("authority")):
        raise ValueError("Frozen twelfth-story binding drifted")
    if plan["twelfth_story"] != _frozen_twelfth(Path(str(plan["twelfth_story"]["authority"]["path"]))):
        raise ValueError("Frozen twelfth-story selection drifted")
    load_reused_matrix(plan)
    return plan


def _chunks(question_ids: Sequence[str], batch_size: int) -> list[list[str]]:
    return [list(question_ids[index:index + batch_size]) for index in range(0, len(question_ids), batch_size)]


def rendered_prompt(plan: Mapping[str, Any], cell: Mapping[str, Any], question_ids: Sequence[str]) -> str:
    source = plan["sources"][str(cell["story_id"])]
    artifact, contexts = source.get("artifact"), source.get("contexts")
    if not _matches(artifact) or not isinstance(contexts, list) or not all(_matches(value) for value in contexts):
        raise ValueError("Source/context commitment drifted")
    p = pilot(); failures = {row["question_id"]: row["failure_question"] for row in p.reviewed_pairs()}; texts = p._question_texts()
    questions = []
    for question_id in question_ids:
        polarity = p.question_polarity(str(cell["condition_id"]), question_id)
        questions.append({"question_id": question_id, "canonical_question": texts[question_id], "asked_question": failures[question_id] if polarity == "negative_failure_condition" else texts[question_id], "polarity": polarity})
    return canonical({"study_id": load_contract()["study_id"], "story_id": cell["story_id"], "condition_id": cell["condition_id"], "repetition": cell["repetition"], "source": Path(str(artifact["path"])).read_text(encoding="utf-8"), "contexts": [Path(str(value["path"])).read_text(encoding="utf-8") for value in contexts], "questions": questions, "response_contract": "JSON array in exact question order; question_id, verdict, confidence only"}).decode("utf-8")


def _validate_new_cell(plan: Mapping[str, Any], cell: Mapping[str, Any], row: Mapping[str, Any], sessions: set[str]) -> list[dict[str, Any]]:
    if set(row) != {"story_id", "condition_id", "repetition", "calls"} or any(row[key] != cell[key] for key in ("story_id", "condition_id", "repetition")) or not isinstance(row["calls"], list):
        raise ValueError("Evidence cell does not bind its frozen story, condition, and repetition")
    condition = _condition(str(cell["condition_id"])); chunks = _chunks(cell["question_ids"], int(condition["batch_size"]))
    if len(row["calls"]) != len(chunks):
        raise ValueError("Evidence physical-call count drifted")
    output: list[dict[str, Any]] = []
    for call, question_ids in zip(row["calls"], chunks, strict=True):
        required = {"question_ids", "session_id_sha256", "prompt", "prompt_sha256", "response", "response_sha256", "verdicts"}
        if not isinstance(call, Mapping) or set(call) != required or call.get("question_ids") != question_ids or not isinstance(call.get("session_id_sha256"), str) or len(call["session_id_sha256"]) != 64:
            raise ValueError("Evidence call does not bind the exact frozen batch")
        if call["session_id_sha256"] in sessions:
            raise ValueError("Expansion evidence reuses a session commitment")
        sessions.add(call["session_id_sha256"])
        prompt = rendered_prompt(plan, cell, question_ids)
        if call.get("prompt") != prompt or call.get("prompt_sha256") != sha256_bytes(prompt) or not isinstance(call.get("response"), str) or call.get("response_sha256") != sha256_bytes(call["response"]):
            raise ValueError("Evidence prompt/response commitment drifted")
        parsed = validate_response(question_ids, call["response"])
        if parsed != call.get("verdicts"):
            raise ValueError("Evidence response does not reproduce the parsed verdicts")
        for verdict, question_id in zip(parsed, question_ids, strict=True):
            output.append(pilot().canonicalize_verdict(verdict, pilot().question_polarity(str(cell["condition_id"]), question_id)))
    return output


def p_states() -> set[str]:
    return {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}


def validate_response(question_ids: Sequence[str], response: str) -> list[dict[str, Any]]:
    """Validate the response-schema payload and preserve its exact ordered projection."""
    schema = read_json(RESPONSE_SCHEMA_PATH)
    if schema.get("type") != "array" or schema.get("items", {}).get("required") != ["question_id", "verdict", "confidence"]:
        raise ValueError("Bound response schema drifted")
    def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result
    try:
        values = json.loads(response, object_pairs_hook=no_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ValueError("Response is not JSON") from error
    except ValueError as error:
        raise ValueError("Response JSON contains duplicate object keys") from error
    if not isinstance(values, list) or len(values) != len(question_ids):
        raise ValueError("Response does not contain the exact requested verdict count")
    validated: list[dict[str, Any]] = []
    for record, question_id in zip(values, question_ids, strict=True):
        if (not isinstance(record, Mapping) or set(record) != {"question_id", "verdict", "confidence"}
                or record.get("question_id") != question_id or record.get("verdict") not in p_states()
                or type(record.get("confidence")) not in {int, float} or isinstance(record.get("confidence"), bool)
                or not 0 <= float(record["confidence"]) <= 1):
            raise ValueError("Response violates the exact bound response schema")
        validated.append(dict(record))
    return validated


def verify_evidence(plan: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Validate all 594 new calls; the 225 matrix must be separately replayed first."""
    if plan.get("study_id") != load_contract()["study_id"]:
        raise ValueError("Evidence does not bind this expansion")
    reused_matrix = load_reused_matrix(plan)
    reused_verified = reused_matrix["cells"]
    cells = [cell for cell in plan["cells"] if cell["source"] == "new_provider_evidence"]
    expected_keys = [(cell["story_id"], cell["condition_id"], cell["repetition"]) for cell in cells]
    actual_keys = [(row.get("story_id"), row.get("condition_id"), row.get("repetition")) for row in evidence_rows]
    if actual_keys != expected_keys:
        raise ValueError("Evidence must be the complete exact ordered new-story plan")
    sessions: set[str] = set(reused_matrix["session_commitments"])
    result: dict[str, dict[str, list[dict[str, Any]]]] = {STORIES[0]: {key: list(value) for key, value in reused_verified.items()}}
    for cell, row in zip(cells, evidence_rows, strict=True):
        result.setdefault(str(cell["story_id"]), {})[f"{cell['condition_id']}:{cell['repetition']}"] = _validate_new_cell(plan, cell, row, sessions)
    if len(sessions) != 792:
        raise ValueError("Combined evidence lacks exactly 792 unique session commitments")
    return result


def _cell_metrics(verified: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    return pilot()._cell_metrics(verified)


def _confidence_stability(verified: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    leaves: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key, records in verified.items():
        condition, repetition = key.rsplit(":", 1)
        for record in records: leaves[str(record["question_id"])].append({"condition": condition, "repetition": int(repetition), **record})
    stable, varying = [], []
    for records in leaves.values():
        by_condition: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for record in records: by_condition[str(record["condition"])].append(record)
        bucket = stable if all(len({item["verdict"] for item in values}) == 1 for values in by_condition.values()) else varying
        bucket.extend(float(item["confidence"]) for item in records)
    return {"stable_mean": statistics.fmean(stable) if stable else None, "varying_mean": statistics.fmean(varying) if varying else None, "interpretation": "repeat-consensus diagnostic, not calibrated human truth"}


def _story_score(cells: Mapping[str, Mapping[str, Any]], condition_id: str) -> float | None:
    values = []
    for repetition in (1, 2, 3):
        dimensions = cells[f"{condition_id}:{repetition}"]["dimensions"].values()
        values.extend(float(value) for value in dimensions if value is not None)
    return statistics.fmean(values) if values else None


def metrics(plan: Mapping[str, Any], evidence_rows: Sequence[Mapping[str, Any]], *, published_hanna_labels: Path | None = None) -> dict[str, Any]:
    verified = verify_evidence(plan, evidence_rows)
    per_story = {story: _cell_metrics(cells) for story, cells in verified.items()}
    summaries = {condition: {story: _story_score(cells, condition) for story, cells in per_story.items()} for condition in CONDITIONS}
    alignment: dict[str, Any] = {"status": "unavailable_without_offline_published_labels"}
    if published_hanna_labels is not None:
        label_record = read_json(published_hanna_labels)
        required = {"format_version", "status", "source", "source_fingerprint", "labels"}
        if set(label_record) != required or label_record["format_version"] != 1 or label_record["status"] != "offline_published_hanna_only" or not isinstance(label_record["source"], str) or not _matches(label_record["source_fingerprint"]):
            raise ValueError("Published HANNA labels lack a bound offline provenance source")
        label_map = label_record["labels"]
        if set(label_map) != set(STORIES) or any(type(value) not in {int, float} or isinstance(value, bool) or not math.isfinite(float(value)) for value in label_map.values()):
            raise ValueError("Published HANNA label record must exactly cover frozen stories")
        labels = [float(label_map[story]) for story in STORIES]
        alignment = {}
        for condition in CONDITIONS:
            scores = [summaries[condition][story] for story in STORIES]
            alignment[condition] = (
                {**pilot().correlation_bridge(scores, labels), "status": "exploratory_four_story_offline_published_labels"}
                if all(value is not None for value in scores)
                else {"signed_kendall_tau_b": None, "absolute_kendall_tau_b": None, "spearman": None, "status": "unavailable_incomplete_condition_score"}
            )
    return {
        "study_id": plan["study_id"], "recommendation": None, "promotion": "forbidden",
        "cross_story": {"condition_summary": summaries, "exploratory_alignment": alignment, "published_label_provenance": fingerprint(published_hanna_labels) if published_hanna_labels is not None else None},
        "repeatability": {story: {"between_repetition_changes": pilot()._mechanical_changes(per_story[story]), "factor_contrasts": pilot()._factor_contrasts(per_story[story]), "confidence_by_stability": _confidence_stability(verified[story])} for story in STORIES},
    }


def execute(*_: Any, **__: Any) -> None:
    raise RuntimeError("This study module deliberately cannot make provider calls; use the separately reviewed callback executor.")
