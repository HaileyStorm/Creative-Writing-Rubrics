"""Sealed one-attempt executor shell for the HANNA four-story expansion.

The CLI can only prepare or dry-run.  Live transport is intentionally absent;
an independently reviewed owner must pass an explicit callback to execute().
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
STUDY_PATH = HERE / "study.py"
SCHEMA_PATH = HERE / "response.schema.json"
LIVE_CALLER_PATH = HERE / "run_expansion_live.py"
RUNNER_PATH = REPOSITORY / "src" / "hbqrs" / "runner.py"
EXECUTION_NAME = "expansion-execution-contract.json"
DISCLOSURE_NAME = "expansion-disclosure.json"
EVIDENCE_NAME = "expansion-evidence.json"
ANALYSIS_NAME = "expansion-analysis.json"
FREEZE_NAME = "expansion-freeze.json"
RAW_EVIDENCE_NAME = "expansion-raw-evidence.json"
ATTEMPTS = "attempts"
MODEL = "gpt-5.6-sol"
REASONING = "high"


def _module() -> Any:
    specification = importlib.util.spec_from_file_location("hbq_hanna_batch_polarity_expansion_study", STUDY_PATH)
    if specification is None or specification.loader is None: raise RuntimeError("Cannot load study runtime")
    module = importlib.util.module_from_spec(specification); sys.modules[specification.name] = module
    specification.loader.exec_module(module); return module


study = _module()


def _sha(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _safe_fingerprint(path: Path) -> dict[str, Any]:
    value = study.fingerprint(path)
    return {"path_sha256": _sha(value["path"]), "bytes": value["bytes"], "sha256": value["sha256"]}


def _immutable(path: Path, value: Mapping[str, Any]) -> None:
    study.immutable_json(path, value)


def _paths_disjoint(*paths: Path) -> bool:
    resolved = [path.resolve() for path in paths]
    return len(resolved) == len(set(resolved)) and all(left not in right.parents and right not in left.parents for index, left in enumerate(resolved) for right in resolved[index + 1:])


def schedule(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for cell in plan["cells"]:
        if cell["source"] != "new_provider_evidence": continue
        batch = int(study._condition(cell["condition_id"])["batch_size"])
        for call_in_cell, question_ids in enumerate(study._chunks(cell["question_ids"], batch), 1):
            prompt = study.rendered_prompt(plan, cell, question_ids)
            output.append({"sequence": len(output) + 1, "story_id": cell["story_id"], "condition_id": cell["condition_id"], "repetition": cell["repetition"], "latin_row": cell["latin_row"], "call_in_cell": call_in_cell, "question_ids": question_ids, "prompt": prompt, "prompt_sha256": _sha(prompt)})
    if len(output) != 594 or len({item["sequence"] for item in output}) != 594:
        raise RuntimeError("Expansion schedule geometry drifted")
    if [item["story_id"] for item in output[:198]] != ["hanna-178"] * 198 or [item["story_id"] for item in output[198:396]] != ["hanna-817"] * 198 or [item["story_id"] for item in output[396:]] != ["hanna-382"] * 198:
        raise RuntimeError("Expansion story order drifted")
    return output


def _pushed_runtime(repo: Path) -> dict[str, Any]:
    """Bind only a clean, pushed tracked runtime before any attempt can start."""
    def git(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
        if result.returncode: raise RuntimeError(f"Git binding failed: {' '.join(args)}")
        return result.stdout.strip()
    revision, remote = git("rev-parse", "HEAD"), git("rev-parse", "origin/main")
    if revision != remote: raise RuntimeError("Executor must be at the exact pushed origin/main revision")
    tracked_dirty = git("status", "--porcelain", "--untracked-files=no")
    if tracked_dirty: raise RuntimeError("Executor requires a clean tracked worktree")
    files: dict[str, dict[str, Any]] = {}
    for path in (STUDY_PATH, SCHEMA_PATH, HERE / "run_expansion.py", LIVE_CALLER_PATH, RUNNER_PATH, HERE / "study-contract.json"):
        relative = path.resolve().relative_to(repo.resolve()).as_posix()
        raw = subprocess.run(["git", "-C", str(repo), "show", f"{revision}:{relative}"], capture_output=True, check=False)
        if raw.returncode: raise RuntimeError("Pushed revision lacks a bound executor file")
        files[relative] = {"bytes": len(raw.stdout), "sha256": _sha(raw.stdout)}
    return {"revision": revision, "remote_ref": "origin/main", "complete_tracked_worktree_clean": True, "files": files, "sha256": _sha(study.canonical(files))}


def _disclosure(plan: Mapping[str, Any], items: Sequence[Mapping[str, Any]], private_root: Path) -> dict[str, Any]:
    source = plan["sources"]
    return {"format_version": 1, "study_id": plan["study_id"], "remote_destination": {"provider": "codex", "model": MODEL, "reasoning": REASONING}, "private_raw_root": {"path_sha256": _sha(str(private_root.resolve()))}, "outbound_artifacts": {story: {"artifact": _safe_fingerprint(Path(value["artifact"]["path"])), "contexts": [_safe_fingerprint(Path(context["path"])) for context in value["contexts"]]} for story, value in source.items()}, "outbound_requests": [{key: item[key] for key in ("sequence", "story_id", "condition_id", "repetition", "latin_row", "call_in_cell", "question_ids", "prompt_sha256")} for item in items], "outbound_content": "Exact prompts are retained only in the private attempt root; public artifacts carry commitments.", "no_human_judging": True, "recommendation": None, "promotion": "forbidden"}


def prepare_execution(work: Path, private_root: Path, *, repo: Path = REPOSITORY) -> dict[str, Any]:
    if not _paths_disjoint(work, private_root): raise RuntimeError("Public work and private raw roots must be disjoint")
    plan = study.load_plan(work); items = schedule(plan)
    if study.bound_private_root(plan) != private_root.resolve():
        raise RuntimeError("Execution private root does not match the prepared reused-matrix root")
    if (work / FREEZE_NAME).exists(): raise RuntimeError("Frozen expansion cannot be prepared or restarted")
    disclosure = _disclosure(plan, items, private_root); _immutable(work / DISCLOSURE_NAME, disclosure)
    contract = {"format_version": 1, "study_id": plan["study_id"], "plan": _safe_fingerprint(work / study.PLAN_NAME), "executor": _safe_fingerprint(HERE / "run_expansion.py"), "live_caller": _safe_fingerprint(LIVE_CALLER_PATH), "provider_primitive": _safe_fingerprint(RUNNER_PATH), "response_schema": _safe_fingerprint(SCHEMA_PATH), "pushed_runtime": _pushed_runtime(repo), "disclosure": _safe_fingerprint(work / DISCLOSURE_NAME), "private_raw_root_sha256": _sha(str(private_root.resolve())), "schedule_sha256": _sha(study.canonical([{key: item[key] for key in ("sequence", "story_id", "condition_id", "repetition", "latin_row", "call_in_cell", "question_ids", "prompt_sha256")} for item in items])), "provider": {"provider": "codex", "cli_executable": "codex", "model": MODEL, "reasoning": REASONING, "fresh_ephemeral_sessions": True, "attempts_per_call": 1, "parallelism": 1}, "restart": "existing valid terminals replay; any partial, invalid, or failed attempt freezes", "recommendation": None, "promotion": "forbidden"}
    _immutable(work / EXECUTION_NAME, contract)
    return {"status": "prepared_no_provider_contact", "scheduled_calls": 594, "provider_calls": 0, "schedule_sha256": contract["schedule_sha256"]}


def dry_run(work: Path, private_root: Path, *, repo: Path = REPOSITORY) -> dict[str, Any]:
    result = prepare_execution(work, private_root, repo=repo)
    return {**result, "status": "dry_run_complete_no_provider_contact"}


def _attempt_paths(private_root: Path, sequence: int) -> tuple[Path, Path, Path]:
    root = private_root / ATTEMPTS / f"{sequence:04d}"
    return root, root / "attempt-start.json", root / "terminal.json"


def _start(item: Mapping[str, Any]) -> dict[str, Any]:
    return {"format_version": 1, "status": "started", "sequence": item["sequence"], "story_id": item["story_id"], "condition_id": item["condition_id"], "repetition": item["repetition"], "latin_row": item["latin_row"], "call_in_cell": item["call_in_cell"], "question_ids": item["question_ids"], "prompt": item["prompt"], "prompt_sha256": item["prompt_sha256"], "response_schema": study.fingerprint(SCHEMA_PATH), "provider": {"provider": "codex", "model": MODEL, "reasoning": REASONING, "ephemeral": True, "attempt_number": 1}}


def _freeze(work: Path, private_root: Path, reason: str, item: Mapping[str, Any] | None = None, detail: str | None = None) -> None:
    _immutable(work / FREEZE_NAME, {"format_version": 1, "study_id": study.load_contract()["study_id"], "status": "frozen_failure", "reason": reason, "detail_sha256": _sha(detail) if detail else None, "sequence": item["sequence"] if item else None, "prompt_sha256": item["prompt_sha256"] if item else None, "private_raw_root_sha256": _sha(str(private_root.resolve())), "recommendation": None, "promotion": "forbidden"})
    raise RuntimeError(f"Expansion is frozen: {reason}")


def _terminal(item: Mapping[str, Any], returned: Mapping[str, Any], sessions: set[str]) -> dict[str, Any]:
    if set(returned) != {"receipt", "response"} or not isinstance(returned.get("response"), str) or not isinstance(returned.get("receipt"), Mapping):
        raise RuntimeError("Callback response violates the one-attempt transport contract")
    receipt = returned["receipt"]
    if set(receipt) != {"provider", "model", "reasoning_effort", "session_id"} or receipt.get("provider") != "openai" or receipt.get("model") != MODEL or receipt.get("reasoning_effort") != REASONING or not isinstance(receipt.get("session_id"), str) or not receipt["session_id"]:
        raise RuntimeError("Callback receipt does not attest the required Codex route")
    session = _sha(receipt["session_id"])
    if session in sessions: raise RuntimeError("Callback receipt reuses a session")
    try: verdicts = study.validate_response(item["question_ids"], returned["response"])
    except ValueError as error: raise RuntimeError("Callback response violates the bound schema") from error
    sessions.add(session)
    return {"format_version": 1, "status": "succeeded", "sequence": item["sequence"], "session_id_sha256": session, "receipt": dict(receipt), "response": returned["response"], "response_sha256": _sha(returned["response"]), "verdicts": verdicts}


def _validate_existing(item: Mapping[str, Any], start: Path, terminal: Path, sessions: set[str]) -> dict[str, Any]:
    if not start.is_file() or not terminal.is_file() or study.read_json(start) != _start(item): raise RuntimeError("existing attempt no longer binds its request")
    record = study.read_json(terminal)
    required = {"format_version", "status", "sequence", "session_id_sha256", "receipt", "response", "response_sha256", "verdicts"}
    if set(record) != required or record.get("format_version") != 1 or record.get("status") != "succeeded" or record.get("sequence") != item["sequence"] or record.get("response_sha256") != _sha(str(record.get("response"))): raise RuntimeError("existing terminal is invalid")
    replayed = _terminal(item, {"receipt": record["receipt"], "response": record["response"]}, sessions)
    if replayed["session_id_sha256"] != record["session_id_sha256"] or replayed["verdicts"] != record["verdicts"]:
        raise RuntimeError("existing terminal cannot replay its receipt or verdict projection")
    return replayed


def execute(work: Path, private_root: Path, callback: Callable[[Mapping[str, Any]], Mapping[str, Any]], *, repo: Path = REPOSITORY) -> dict[str, Any]:
    """Invoke the supplied one-attempt callback sequentially; failure permanently freezes."""
    prepare_execution(work, private_root, repo=repo)
    plan, items, sessions = study.load_plan(work), schedule(study.load_plan(work)), set()
    terminals: dict[int, dict[str, Any]] = {}
    for item in items:
        root, started, terminal = _attempt_paths(private_root, int(item["sequence"]))
        if started.exists() and not terminal.exists(): _freeze(work, private_root, "started_without_terminal", item)
        if terminal.exists():
            try: terminals[item["sequence"]] = _validate_existing(item, started, terminal, sessions)
            except RuntimeError as error: _freeze(work, private_root, "invalid_existing_attempt", item, str(error))
            continue
        if root.exists() and any(root.iterdir()): _freeze(work, private_root, "unknown_partial_attempt_state", item)
        _immutable(started, _start(item))
        try: terminals[item["sequence"]] = _terminal(item, callback(item), sessions); _immutable(terminal, terminals[item["sequence"]])
        except BaseException as error:
            _immutable(terminal, {"format_version": 1, "status": "failed", "sequence": item["sequence"], "prompt_sha256": item["prompt_sha256"], "error_sha256": _sha(str(error))})
            _freeze(work, private_root, "provider_or_response_failure", item, str(error))
    rows: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for item in items: grouped[(item["story_id"], item["condition_id"], item["repetition"])].append(item)
    for story_id, condition_id, repetition in [(cell["story_id"], cell["condition_id"], cell["repetition"]) for cell in plan["cells"] if cell["source"] == "new_provider_evidence"]:
        calls = grouped[(story_id, condition_id, repetition)]
        rows.append({"story_id": story_id, "condition_id": condition_id, "repetition": repetition, "calls": [{"question_ids": item["question_ids"], "session_id_sha256": terminals[item["sequence"]]["session_id_sha256"], "prompt": item["prompt"], "prompt_sha256": item["prompt_sha256"], "response": terminals[item["sequence"]]["response"], "response_sha256": terminals[item["sequence"]]["response_sha256"], "verdicts": terminals[item["sequence"]]["verdicts"]} for item in calls]})
    try:
        study.verify_evidence(plan, rows)
        analysis = study.metrics(plan, rows)
    except BaseException as error:
        _freeze(work, private_root, "completion_validation_failure", detail=str(error))
    raw = {"format_version": 1, "study_id": plan["study_id"], "new_call_count": 594, "rows": rows, "recommendation": None, "promotion": "forbidden"}; _immutable(private_root / RAW_EVIDENCE_NAME, raw)
    public = {"format_version": 1, "study_id": plan["study_id"], "new_call_count": 594, "row_count": 36, "private_raw_evidence": _safe_fingerprint(private_root / RAW_EVIDENCE_NAME), "recommendation": None, "promotion": "forbidden"}; _immutable(work / EVIDENCE_NAME, public)
    _immutable(work / ANALYSIS_NAME, analysis)
    return {"status": "completed_development_only", "calls": 594, "rows": 36, "recommendation": None, "promotion": "forbidden"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--work", type=Path, required=True); parser.add_argument("--private-root", type=Path, required=True); parser.add_argument("--repo", type=Path, default=REPOSITORY)
    mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--prepare", action="store_true"); mode.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv); result = dry_run(arguments.work, arguments.private_root, repo=arguments.repo) if arguments.dry_run else prepare_execution(arguments.work, arguments.private_root, repo=arguments.repo)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
