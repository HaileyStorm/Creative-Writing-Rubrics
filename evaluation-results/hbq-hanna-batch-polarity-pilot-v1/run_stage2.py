"""One-attempt executor for Stage 2 of the sealed HANNA mechanics pilot.

Stage 2 is deliberately a separate executable surface.  It verifies the
complete Stage 1 prefix before binding or sending its 66 new requests; every
raw prompt, response, and receipt remains in a separately selected private
root.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
STAGE1_PATH = HERE / "run_stage1.py"
STUDY_PATH = HERE / "study.py"
SCHEMA_PATH = HERE / "stage1-response.schema.json"
RUNNER_PATH = REPOSITORY / "src" / "hbqrs" / "runner.py"
EXECUTION_NAME = "stage2-execution-contract.json"
DISCLOSURE_NAME = "stage2-disclosure.json"
EVIDENCE_NAME = "stage2-evidence.json"
RAW_EVIDENCE_NAME = "stage2-raw-evidence.json"
GATE_NAME = "stage2-gate.json"
FREEZE_NAME = "stage2-freeze.json"
ATTEMPTS = "stage2-attempts"
MODEL = "gpt-5.6-sol"
REASONING = "high"
TIMEOUT_SECONDS = 600.0
PREDECESSOR_ARTIFACTS = {
    "attempt_start": {"path_sha256": "461bcb6a941ce239ed05a127b1d83b477183e08b8be9e78cda79a9560d8d3861", "bytes": 13721, "sha256": "5e940109e14e6355853d3179463f01563559576e58f265f44be9122a9c547358"},
    "disclosure": {"path_sha256": "a4c7299535bd5c34a130e2a96fe4ba38c8fedf96cecbafcc6d38d95c01cef666", "bytes": 28945, "sha256": "6d4295f411944f8af15996824f68e3f18be12fdff3a183a713480df85b5d8cce"},
    "execution_contract": {"path_sha256": "89e4a4ae231b436467da554f4e5445f6e87cd9364fdfe5b83a7464dd6711362a", "bytes": 4251, "sha256": "783fbbbaf60f9f2b25a80783c97f2ad51f0893da29c4d722ef8d39f1ba55e1e9"},
    "failed_terminal": {"path_sha256": "7abf8b75d655c8e2b682c38398cf9ea0ae7f311f6ef7405a2f2ca10baa666bee", "bytes": 468, "sha256": "704835df9c7fbb3f292f4bd726cfa90c2aabaa8432d52fb866aabc7cff497ddf"},
    "freeze": {"path_sha256": "da077e68673cd8d1256e68c13a1dde07f27ff79728900dee7e21edb38670f8a5", "bytes": 534, "sha256": "d48256f3b9276a4ae704bc4c477bfe11a70315264e0955fc8281832863e35999"},
}
PREDECESSOR_ARTIFACTS_SHA256 = "7ee95bc5eaff7eeedd27dda8b5a072f5b2c488d9c5bd46591fe5f8f08bd910c5"


def _load_module(name: str, path: Path) -> Any:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"Cannot load required runtime: {path.name}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


stage1 = _load_module("hbq_hanna_batch_polarity_stage2_parent", STAGE1_PATH)
study = stage1.study
_call_codex = stage1._call_codex


def _read_json(path: Path) -> dict[str, Any]:
    return stage1._read_json(path)


def _immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    stage1._immutable_json(path, value)


def _sha256(value: bytes | str) -> str:
    return stage1._sha256(value)


def _canonical(value: Any) -> bytes:
    return stage1._canonical(value)


def _fingerprint(path: Path) -> dict[str, Any]:
    return stage1._fingerprint(path)


def _safe_path_fingerprint(path: Path) -> dict[str, Any]:
    return stage1._safe_path_fingerprint(path)


def _paths_disjoint(*paths: Path) -> bool:
    resolved = [path.resolve() for path in paths]
    return len(set(resolved)) == len(resolved) and all(
        left not in right.parents and right not in left.parents
        for index, left in enumerate(resolved)
        for right in resolved[index + 1 :]
    )


def _stage2_cells(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells = [dict(cell) for cell in plan["cells"] if cell["repetition"] == 2 and cell["source"] == "new_provider_evidence"]
    expected = ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1", "global_positive_batch32"]
    if [cell["condition_id"] for cell in cells] != expected or sum(int(cell["new_calls"]) for cell in cells) != 66:
        raise RuntimeError("Prepared plan is not the exact Stage 2 66-call geometry")
    return cells


def _schedule(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cell in _stage2_cells(plan):
        condition = study.condition_map()[cell["condition_id"]]
        for call_in_cell, question_ids in enumerate(study._chunks(cell["question_ids"], int(condition["batch_size"])), 1):
            prompt = study.rendered_prompt(plan, cell, question_ids)
            result.append({
                "sequence": len(result) + 1,
                "condition_id": cell["condition_id"],
                "repetition": 2,
                "call_in_cell": call_in_cell,
                "question_ids": question_ids,
                "prompt": prompt,
                "prompt_sha256": _sha256(prompt),
            })
    if len(result) != 66 or len({item["sequence"] for item in result}) != 66:
        raise RuntimeError("Stage 2 physical-call schedule drifted")
    return result


def _stage1_binding(stage1_work: Path, stage1_private_root: Path) -> dict[str, Any]:
    """Replay all accepted Stage 1 evidence without projecting private content."""
    work, private = stage1_work.resolve(), stage1_private_root.resolve()
    if not work.is_dir() or not private.is_dir() or (work / stage1.FREEZE_NAME).exists():
        raise RuntimeError("Stage 2 requires a completed unfrozen Stage 1 public and private root")
    names = {
        "plan": work / "pilot-contract.json",
        "execution_contract": work / stage1.EXECUTION_NAME,
        "disclosure": work / stage1.DISCLOSURE_NAME,
        "evidence": work / stage1.EVIDENCE_NAME,
        "gate": work / stage1.GATE_NAME,
        "raw_evidence": private / stage1.RAW_EVIDENCE_NAME,
    }
    try:
        artifacts = {name: _safe_path_fingerprint(path) for name, path in names.items()}
    except RuntimeError as error:
        raise RuntimeError("Stage 1 public or private artifacts are incomplete") from error
    plan = study.load_plan(work)
    schedule = stage1._schedule(plan)
    if len(schedule) != 60:
        raise RuntimeError("Stage 1 schedule geometry drifted")
    disclosure = _read_json(names["disclosure"])
    if disclosure != stage1._public_disclosure(plan, schedule, private):
        raise RuntimeError("Stage 1 disclosure does not replay its exact outbound commitments")
    contract = _read_json(names["execution_contract"])
    required_provider = {"provider": "codex", "model": MODEL, "reasoning": REASONING, "fresh_ephemeral_sessions": True, "attempts_per_call": 1, "timeout_seconds": TIMEOUT_SECONDS}
    bound = [STUDY_PATH, SCHEMA_PATH, STAGE1_PATH, HERE / "study-contract.json", HERE / "polarity-pairs.json", RUNNER_PATH]
    expected_runtime = {path.name: _fingerprint(path) for path in bound if path not in {STAGE1_PATH, SCHEMA_PATH}}
    required_contract = {"format_version", "study_id", "stage", "pilot_plan", "executor", "response_schema", "study_runtime", "pushed_git", "disclosure", "private_raw_root_sha256", "schedule_sha256", "provider", "transport", "predecessor", "outcome_policy"}
    expected_schedule_sha256 = _sha256(_canonical([{key: item[key] for key in ("sequence", "condition_id", "repetition", "call_in_cell", "question_ids", "prompt_sha256")} for item in schedule]))
    expected_transport = {"generation": stage1.TRANSPORT_GENERATION, "schema": _fingerprint(SCHEMA_PATH), "projection_rule": stage1.TRANSPORT_PROJECTION_RULE, "projection_rule_sha256": _sha256(_canonical(stage1.TRANSPORT_PROJECTION_RULE)), "predecessor_failure": stage1.PREDECESSOR_FAILURE}
    expected_outcome = {"stage_gate": "stage_1_complete", "next_stage": 2, "recommendation": None, "promotion": "forbidden", "automatic_stage_2": "forbidden"}
    if set(contract) != required_contract or contract.get("format_version") != 2 or contract.get("study_id") != plan["study_id"] or contract.get("stage") != 1 or contract.get("pilot_plan") != _fingerprint(work / "pilot-contract.json") or contract.get("executor") != _fingerprint(STAGE1_PATH) or contract.get("response_schema") != _fingerprint(SCHEMA_PATH) or contract.get("study_runtime") != expected_runtime or contract.get("provider") != required_provider or contract.get("transport") != expected_transport or contract.get("outcome_policy") != expected_outcome or contract.get("schedule_sha256") != expected_schedule_sha256:
        raise RuntimeError("Stage 1 execution contract identity or call geometry drifted")
    pushed = contract.get("pushed_git")
    if not isinstance(pushed, Mapping) or set(pushed) != {"revision", "remote_ref", "complete_tracked_worktree_clean", "files", "sha256"} or pushed.get("remote_ref") != "origin/main" or pushed.get("complete_tracked_worktree_clean") is not True or not isinstance(pushed.get("revision"), str) or len(pushed["revision"]) != 40 or not isinstance(pushed.get("files"), Mapping):
        raise RuntimeError("Stage 1 execution contract lacks its pushed-runtime binding")
    expected_files: dict[str, dict[str, Any]] = {}
    for path in bound:
        relative = path.resolve().relative_to(REPOSITORY).as_posix()
        completed = subprocess.run(["git", "-C", str(REPOSITORY), "show", f"{pushed['revision']}:{relative}"], capture_output=True, check=False)
        if completed.returncode:
            raise RuntimeError("Stage 1 pushed runtime cannot replay a bound file")
        expected_files[relative] = {"bytes": len(completed.stdout), "sha256": _sha256(completed.stdout)}
    if pushed["files"] != expected_files or pushed.get("sha256") != _sha256(_canonical(expected_files)):
        raise RuntimeError("Stage 1 pushed runtime file binding drifted")
    disclosure_binding = contract.get("disclosure")
    if not isinstance(disclosure_binding, Mapping) or disclosure_binding.get("bytes") != names["disclosure"].stat().st_size or disclosure_binding.get("sha256") != _sha256(names["disclosure"].read_bytes()) or contract.get("private_raw_root_sha256") != _sha256(str(private)):
        raise RuntimeError("Stage 1 execution contract cross-binding drifted")
    predecessor = contract.get("predecessor")
    if not isinstance(predecessor, Mapping) or set(predecessor) != {"revision", "work_root_path_sha256", "private_root_path_sha256", "artifacts", "artifacts_sha256", "failure", "persisted_outcome"} or predecessor.get("revision") != stage1.PREDECESSOR_REVISION or predecessor.get("work_root_path_sha256") != stage1.PREDECESSOR_WORK_PATH_SHA256 or predecessor.get("private_root_path_sha256") != stage1.PREDECESSOR_PRIVATE_PATH_SHA256 or predecessor.get("failure") != stage1.PREDECESSOR_FAILURE or predecessor.get("persisted_outcome") != {"failed_terminal": True, "accepted_result": False, "retry": False} or predecessor.get("artifacts") != PREDECESSOR_ARTIFACTS or predecessor.get("artifacts_sha256") != PREDECESSOR_ARTIFACTS_SHA256:
        raise RuntimeError("Stage 1 predecessor binding drifted")
    if _sha256(_canonical(PREDECESSOR_ARTIFACTS)) != PREDECESSOR_ARTIFACTS_SHA256 or any(set(value) != {"path_sha256", "bytes", "sha256"} or type(value.get("bytes")) is not int for value in predecessor["artifacts"].values() if isinstance(value, Mapping)) or any(not isinstance(value, Mapping) for value in predecessor["artifacts"].values()):
        raise RuntimeError("Stage 1 predecessor artifact commitments are malformed")
    parent_sessions = {item["session_id_sha256"] for item in plan["parent"]["parent_verifier"]["sessions"]}
    terminals: dict[int, dict[str, Any]] = {}
    expected_dirs = {f"{item['sequence']:04d}" for item in schedule}
    attempts = private / stage1.ATTEMPTS
    actual_entries = list(attempts.iterdir()) if attempts.is_dir() else []
    actual_dirs = {path.name for path in actual_entries if path.is_dir()}
    if actual_dirs != expected_dirs or any(not path.is_dir() for path in actual_entries):
        raise RuntimeError("Stage 1 private attempts are partial or contain unexpected calls")
    attempt_artifacts: list[dict[str, Any]] = []
    for item in schedule:
        root, started_path, terminal_path = stage1._attempt_paths(private, int(item["sequence"]))
        if not started_path.is_file() or not terminal_path.is_file():
            raise RuntimeError("Stage 1 private attempt is incomplete")
        expected_start = {"format_version": 1, "status": "started", "sequence": item["sequence"], "condition_id": item["condition_id"], "repetition": 1, "call_in_cell": item["call_in_cell"], "question_ids": item["question_ids"], "prompt": item["prompt"], "prompt_sha256": item["prompt_sha256"], "response_schema": _fingerprint(SCHEMA_PATH), "transport": {"generation": stage1.TRANSPORT_GENERATION, "projection_rule_sha256": _sha256(_canonical(stage1.TRANSPORT_PROJECTION_RULE))}, "provider": {"provider": "codex", "model": MODEL, "reasoning": REASONING, "ephemeral": True, "attempt_number": 1}}
        if _read_json(started_path) != expected_start:
            raise RuntimeError("Stage 1 attempt-start no longer binds its request")
        try:
            terminals[int(item["sequence"])] = stage1._validate_terminal(_read_json(terminal_path), item, parent_sessions)
        except RuntimeError as error:
            raise RuntimeError("Stage 1 terminal replay failed") from error
        files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(root).as_posix())
        if not files:
            raise RuntimeError("Stage 1 private attempt contains no bindable files")
        attempt_artifacts.append({"sequence": item["sequence"], "attempt_start": _safe_path_fingerprint(started_path), "terminal": _safe_path_fingerprint(terminal_path), "files": [{"relative_path": path.relative_to(root).as_posix(), "fingerprint": _safe_path_fingerprint(path)} for path in files]})
    rows = stage1._evidence_rows(schedule, terminals)
    try:
        study.verify_evidence(plan, rows)
    except ValueError as error:
        raise RuntimeError("Stage 1 reconstructed rows fail the pilot verifier") from error
    expected_raw = {"format_version": 1, "study_id": plan["study_id"], "stage": 1, "transport": {"generation": stage1.TRANSPORT_GENERATION, "projection_rule": stage1.TRANSPORT_PROJECTION_RULE, "projection_rule_sha256": _sha256(_canonical(stage1.TRANSPORT_PROJECTION_RULE))}, "rows": rows, "row_count": 3, "call_count": 60, "recommendation": None, "promotion": "forbidden"}
    if _read_json(names["raw_evidence"]) != expected_raw:
        raise RuntimeError("Stage 1 private raw evidence does not replay its terminals")
    expected_public = {"format_version": 1, "study_id": plan["study_id"], "stage": 1, "transport": {"generation": stage1.TRANSPORT_GENERATION, "projection_rule_sha256": _sha256(_canonical(stage1.TRANSPORT_PROJECTION_RULE))}, "rows": stage1._public_evidence_rows(schedule, terminals), "row_count": 3, "call_count": 60, "private_raw_evidence": {"bytes": names["raw_evidence"].stat().st_size, "sha256": _sha256(names["raw_evidence"].read_bytes())}, "recommendation": None, "promotion": "forbidden"}
    if _read_json(names["evidence"]) != expected_public:
        raise RuntimeError("Stage 1 public evidence does not replay its terminals")
    expected_gate = {"study_id": plan["study_id"], "completed_stage": 1, "status": "stage_1_complete", "next_stage": 2, "recommendation": None, "promotion": "forbidden"}
    if _read_json(names["gate"]) != expected_gate:
        raise RuntimeError("Stage 1 gate is not the exact complete predecessor gate")
    artifacts["attempts"] = attempt_artifacts
    return {"plan": plan, "rows": rows, "sessions": parent_sessions, "artifacts": artifacts, "artifacts_sha256": _sha256(_canonical(artifacts))}


def _public_disclosure(plan: Mapping[str, Any], schedule: Sequence[Mapping[str, Any]], private_root: Path) -> dict[str, Any]:
    parent_cell = plan["parent"]["parent_cell"]
    artifact, contexts = parent_cell.get("artifact"), parent_cell.get("contexts")
    if not isinstance(artifact, Mapping) or not isinstance(contexts, list) or any(not isinstance(value, Mapping) for value in contexts):
        raise RuntimeError("Prepared plan lacks safe source/context bindings")
    return {
        "format_version": 1, "study_id": plan["study_id"], "stage": 2,
        "remote_destination": {"provider": "codex", "model": MODEL, "reasoning": REASONING},
        "private_raw_root": {"path_sha256": _sha256(str(private_root.resolve()))},
        "outbound_artifacts": {"source": stage1._safe_fingerprint(artifact), "contexts": [stage1._safe_fingerprint(value) for value in contexts]},
        "outbound_requests": [{key: item[key] for key in ("sequence", "condition_id", "repetition", "call_in_cell", "question_ids", "prompt_sha256")} for item in schedule],
        "outbound_content": "Each private attempt preserves the exact rendered prompt. This public projection contains only commitments and source/context fingerprints.",
        "no_human_judging": True, "no_adaptive_confidence_repeats": True, "automatic_stage_3": "forbidden", "recommendation": None, "promotion": "forbidden",
    }


def _execution_contract(plan: Mapping[str, Any], work: Path, private_root: Path, repo: Path, schedule: Sequence[Mapping[str, Any],], disclosure: Path, stage1_parent: Mapping[str, Any]) -> dict[str, Any]:
    bound = [STUDY_PATH, SCHEMA_PATH, STAGE1_PATH, HERE / "run_stage2.py", HERE / "study-contract.json", HERE / "polarity-pairs.json", RUNNER_PATH]
    pushed = stage1._pushed_git_binding(repo, bound)
    return {
        "format_version": 1, "study_id": plan["study_id"], "stage": 2,
        "pilot_plan": _safe_path_fingerprint(work / "pilot-contract.json"), "executor": _safe_path_fingerprint(HERE / "run_stage2.py"),
        "response_schema": _safe_path_fingerprint(SCHEMA_PATH),
        "study_runtime": {path.name: _safe_path_fingerprint(path) for path in bound if path not in {HERE / "run_stage2.py", SCHEMA_PATH}},
        "pushed_git": pushed, "disclosure": _safe_path_fingerprint(disclosure), "private_raw_root_sha256": _sha256(str(private_root.resolve())),
        "schedule_sha256": _sha256(_canonical([{key: item[key] for key in ("sequence", "condition_id", "repetition", "call_in_cell", "question_ids", "prompt_sha256")} for item in schedule])),
        "provider": {"provider": "codex", "model": MODEL, "reasoning": REASONING, "fresh_ephemeral_sessions": True, "attempts_per_call": 1, "timeout_seconds": TIMEOUT_SECONDS},
        "transport": {"generation": stage1.TRANSPORT_GENERATION, "schema": _safe_path_fingerprint(SCHEMA_PATH), "projection_rule": stage1.TRANSPORT_PROJECTION_RULE, "projection_rule_sha256": _sha256(_canonical(stage1.TRANSPORT_PROJECTION_RULE))},
        "stage1_parent": {"artifacts": stage1_parent["artifacts"], "artifacts_sha256": stage1_parent["artifacts_sha256"], "replayed_rows": 3, "replayed_calls": 60, "session_commitments": 66},
        "outcome_policy": {"stage_gate": ["stage_2_stop_no_reproduced_signal", "stage_3_required_signal"], "next_stage": "gate_only", "recommendation": None, "promotion": "forbidden", "automatic_stage_3": "forbidden"},
    }


def _attempt_paths(private_root: Path, sequence: int) -> tuple[Path, Path, Path]:
    root = private_root / ATTEMPTS / f"{sequence:04d}"
    return root, root / "attempt-start.json", root / "terminal.json"


def _safe_freeze(work: Path, private_root: Path, *, reason: str, item: Mapping[str, Any] | None, detail: str | None = None, raw_object_response: str | None = None) -> None:
    _immutable_json(work / FREEZE_NAME, {"format_version": 1, "study_id": study.load_contract()["study_id"], "stage": 2, "status": "frozen_failure", "reason": reason, "detail_sha256": _sha256(detail) if detail is not None else None, "raw_object_response_sha256": _sha256(raw_object_response) if raw_object_response is not None else None, "sequence": item["sequence"] if item else None, "prompt_sha256": item["prompt_sha256"] if item else None, "private_raw_root_sha256": _sha256(str(private_root.resolve())), "recommendation": None, "promotion": "forbidden"})


def _freeze_and_raise(work: Path, private_root: Path, reason: str, item: Mapping[str, Any] | None = None, detail: str | None = None, raw_object_response: str | None = None) -> None:
    _safe_freeze(work, private_root, reason=reason, item=item, detail=detail, raw_object_response=raw_object_response)
    raise RuntimeError(f"Stage 2 is frozen: {reason}")


def _rows(schedule: Sequence[Mapping[str, Any]], terminals: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in schedule:
        grouped[str(item["condition_id"])].append(item)
    return [{"condition_id": condition_id, "repetition": 2, "calls": [{"question_ids": item["question_ids"], "session_id_sha256": terminals[int(item["sequence"])]["session_id_sha256"], "prompt": item["prompt"], "prompt_sha256": item["prompt_sha256"], "response": terminals[int(item["sequence"])]["transport_projection"], "response_sha256": terminals[int(item["sequence"])]["transport_projection_sha256"], "verdicts": terminals[int(item["sequence"])]["verdicts"]} for item in grouped[condition_id]]} for condition_id in ("global_negative_batch32", "single_positive_batch1", "single_negative_batch1", "global_positive_batch32")]


def _public_rows(schedule: Sequence[Mapping[str, Any]], terminals: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in schedule:
        grouped[str(item["condition_id"])].append(item)
    return [{"condition_id": condition_id, "repetition": 2, "call_count": len(grouped[condition_id]), "calls": [{"sequence": item["sequence"], "question_ids_sha256": _sha256(_canonical(item["question_ids"])), "prompt_sha256": item["prompt_sha256"], "raw_object_response_sha256": terminals[int(item["sequence"])]["raw_object_response_sha256"], "transport_projection_sha256": terminals[int(item["sequence"])]["transport_projection_sha256"], "transport_projection_rule_sha256": terminals[int(item["sequence"])]["transport_projection_rule_sha256"], "session_id_sha256": terminals[int(item["sequence"])]["session_id_sha256"], "verdicts_sha256": _sha256(_canonical(terminals[int(item["sequence"])]["verdicts"]))} for item in grouped[condition_id]]} for condition_id in ("global_negative_batch32", "single_positive_batch1", "single_negative_batch1", "global_positive_batch32")]


def _validate_completed(work: Path, private_root: Path, plan: Mapping[str, Any], schedule: Sequence[Mapping[str, Any]], terminals: Mapping[int, Mapping[str, Any]], stage1_parent: Mapping[str, Any]) -> dict[str, Any]:
    stage2_rows = _rows(schedule, terminals)
    merged_rows = [*stage1_parent["rows"], *stage2_rows]
    try:
        study.verify_evidence(plan, merged_rows)
    except ValueError as error:
        raise RuntimeError("Merged Stage 1 and Stage 2 raw rows fail the pilot verifier") from error
    gate = study.stage_gate(plan, merged_rows)
    expected_gates = [{"study_id": plan["study_id"], "completed_stage": 2, "status": status, "next_stage": next_stage, "recommendation": None, "promotion": "forbidden"} for status, next_stage in (("stage_2_stop_no_reproduced_signal", None), ("stage_3_required_signal", 3))]
    if gate not in expected_gates:
        raise RuntimeError("Stage 2 gate is outside the frozen outcome policy")
    raw_evidence = {"format_version": 1, "study_id": plan["study_id"], "stage": 2, "rows": merged_rows, "row_count": 7, "stage2_call_count": 66, "stage1_parent_artifacts_sha256": stage1_parent["artifacts_sha256"], "recommendation": None, "promotion": "forbidden"}
    private_evidence = private_root / RAW_EVIDENCE_NAME
    _immutable_json(private_evidence, raw_evidence)
    raw_bytes = private_evidence.read_bytes()
    evidence = {"format_version": 1, "study_id": plan["study_id"], "stage": 2, "rows": _public_rows(schedule, terminals), "row_count": 4, "merged_row_count": 7, "call_count": 66, "stage1_parent_artifacts_sha256": stage1_parent["artifacts_sha256"], "private_raw_evidence": {"bytes": len(raw_bytes), "sha256": _sha256(raw_bytes)}, "recommendation": None, "promotion": "forbidden"}
    _immutable_json(work / EVIDENCE_NAME, evidence)
    _immutable_json(work / GATE_NAME, gate)
    return {"status": gate["status"], "next_stage": gate["next_stage"], "calls": 66, "rows": 7}


def _bootstrap(work: Path, private_root: Path, stage1_work: Path, stage1_private_root: Path, repo: Path, *, dry_run: bool) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    if not _paths_disjoint(work, private_root, stage1_work, stage1_private_root):
        raise RuntimeError("Stage 2 public/private roots and Stage 1 roots must be pairwise disjoint")
    if repo.resolve() == private_root.resolve() or repo.resolve() in private_root.resolve().parents:
        raise RuntimeError("Stage 2 private raw root must not be inside the repository")
    parent = _stage1_binding(stage1_work, stage1_private_root)
    plan = study.load_plan(work)
    if plan != parent["plan"]:
        raise RuntimeError("Stage 2 must use the exact Stage 1 pilot plan")
    schedule = _schedule(plan)
    if dry_run:
        return plan, schedule, None, parent
    disclosure = work / DISCLOSURE_NAME
    _immutable_json(disclosure, _public_disclosure(plan, schedule, private_root))
    contract = _execution_contract(plan, work, private_root, repo, schedule, disclosure, parent)
    _immutable_json(work / EXECUTION_NAME, contract)
    if _read_json(work / EXECUTION_NAME) != contract:
        raise RuntimeError("Stage 2 execution contract drifted")
    return plan, schedule, contract, parent


def dry_run(work: Path, private_root: Path, *, stage1_work: Path, stage1_private_root: Path, repo: Path = REPOSITORY) -> dict[str, Any]:
    plan, schedule, _, _ = _bootstrap(work, private_root, stage1_work, stage1_private_root, repo, dry_run=True)
    return {"study_id": plan["study_id"], "stage": 2, "provider_calls": 0, "scheduled_calls": len(schedule), "conditions": [cell["condition_id"] for cell in _stage2_cells(plan)]}


def prepare(work: Path, private_root: Path, *, stage1_work: Path, stage1_private_root: Path, repo: Path = REPOSITORY) -> dict[str, Any]:
    plan, schedule, contract, _ = _bootstrap(work, private_root, stage1_work, stage1_private_root, repo, dry_run=False)
    if contract is None:
        raise RuntimeError("Stage 2 preparation did not create its execution contract")
    return {"study_id": plan["study_id"], "stage": 2, "provider_calls": 0, "scheduled_calls": len(schedule), "stage1_artifacts_sha256": contract["stage1_parent"]["artifacts_sha256"]}


def execute_stage2(work: Path, private_root: Path, *, stage1_work: Path, stage1_private_root: Path, executable: str = "codex", timeout: float = TIMEOUT_SECONDS, repo: Path = REPOSITORY, dry_run_only: bool = False) -> dict[str, Any]:
    if timeout != TIMEOUT_SECONDS:
        raise RuntimeError("Stage 2 timeout is frozen at 600 seconds")
    if dry_run_only:
        return dry_run(work, private_root, stage1_work=stage1_work, stage1_private_root=stage1_private_root, repo=repo)
    plan, schedule, _, parent = _bootstrap(work, private_root, stage1_work, stage1_private_root, repo, dry_run=False)
    if (work / FREEZE_NAME).exists():
        raise RuntimeError("Stage 2 root is frozen and cannot be resumed")
    sessions = set(parent["sessions"])
    terminals: dict[int, dict[str, Any]] = {}
    for item in schedule:
        root, started_path, terminal_path = _attempt_paths(private_root, int(item["sequence"]))
        if started_path.exists() and not terminal_path.exists():
            _freeze_and_raise(work, private_root, "started_without_terminal", item)
        if terminal_path.exists():
            try:
                terminals[int(item["sequence"])] = stage1._validate_terminal(_read_json(terminal_path), item, sessions)
            except RuntimeError as error:
                _freeze_and_raise(work, private_root, "invalid_existing_terminal", item, str(error))
            continue
        if root.exists() and any(root.iterdir()):
            _freeze_and_raise(work, private_root, "unknown_partial_attempt_state", item)
        start = {"format_version": 1, "status": "started", "stage": 2, "sequence": item["sequence"], "condition_id": item["condition_id"], "repetition": 2, "call_in_cell": item["call_in_cell"], "question_ids": item["question_ids"], "prompt": item["prompt"], "prompt_sha256": item["prompt_sha256"], "response_schema": _fingerprint(SCHEMA_PATH), "transport": {"generation": stage1.TRANSPORT_GENERATION, "projection_rule_sha256": _sha256(_canonical(stage1.TRANSPORT_PROJECTION_RULE))}, "provider": {"provider": "codex", "model": MODEL, "reasoning": REASONING, "ephemeral": True, "attempt_number": 1}}
        _immutable_json(started_path, start)
        try:
            raw_object_response, provider_record = _call_codex(executable=executable, model=MODEL, reasoning=REASONING, prompt=item["prompt"], output_dir=root, response_schema=SCHEMA_PATH, batch_number=int(item["sequence"]), attempt_number=1, timeout=TIMEOUT_SECONDS)
            terminal = stage1._terminal_success(item, raw_object_response, provider_record)
            terminals[int(item["sequence"])] = stage1._validate_terminal(terminal, item, sessions)
            _immutable_json(terminal_path, terminal)
        except BaseException as error:
            raw_object_response = getattr(error, "content", None)
            provider_record = getattr(error, "provider_record", None)
            _immutable_json(terminal_path, {"format_version": 1, "status": "failed", "stage": 2, "sequence": item["sequence"], "prompt_sha256": item["prompt_sha256"], "error_sha256": _sha256(str(error)), "raw_object_response_sha256": _sha256(raw_object_response) if isinstance(raw_object_response, str) else None, "provider_record": provider_record if isinstance(provider_record, Mapping) else None})
            _freeze_and_raise(work, private_root, "provider_or_response_failure", item, str(error), raw_object_response if isinstance(raw_object_response, str) else None)
    try:
        return _validate_completed(work, private_root, plan, schedule, terminals, parent)
    except RuntimeError as error:
        _freeze_and_raise(work, private_root, "completion_validation_failure", detail=str(error))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--stage1-work", required=True, type=Path)
    parser.add_argument("--stage1-private-root", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=REPOSITORY)
    parser.add_argument("--executable", default="codex")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--prepare", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.prepare:
        result = prepare(arguments.work, arguments.private_root, stage1_work=arguments.stage1_work, stage1_private_root=arguments.stage1_private_root, repo=arguments.repo)
    else:
        result = execute_stage2(arguments.work, arguments.private_root, stage1_work=arguments.stage1_work, stage1_private_root=arguments.stage1_private_root, executable=arguments.executable, repo=arguments.repo, dry_run_only=arguments.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
