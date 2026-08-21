"""One-attempt executor for Stage 1 of the sealed HANNA mechanics pilot.

The protocol verifier deliberately has no provider path.  This adjacent runner
binds a reviewed prepared plan, records each outbound request before it is
sent, and stops permanently on the first uncertain call state.  Raw prompts,
responses, and provider records stay under the separately selected private
root; the public work directory receives commitments and a safe projection.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
STUDY_PATH = HERE / "study.py"
SCHEMA_PATH = HERE / "stage1-response.schema.json"
RUNNER_PATH = REPOSITORY / "src" / "hbqrs" / "runner.py"
EXECUTION_NAME = "stage1-execution-contract.json"
DISCLOSURE_NAME = "stage1-disclosure.json"
EVIDENCE_NAME = "stage1-evidence.json"
RAW_EVIDENCE_NAME = "stage1-raw-evidence.json"
GATE_NAME = "stage1-gate.json"
FREEZE_NAME = "stage1-freeze.json"
ATTEMPTS = "attempts"
MODEL = "gpt-5.6-sol"
REASONING = "high"
TIMEOUT_SECONDS = 600.0


def _module() -> Any:
    specification = importlib.util.spec_from_file_location("hbq_hanna_batch_polarity_stage1_study", STUDY_PATH)
    if specification is None or specification.loader is None:
        raise RuntimeError("Cannot load the frozen pilot study")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


study = _module()
from hbqrs.runner import _call_codex  # noqa: E402  # The approved provider primitive.
if Path(inspect.getsourcefile(_call_codex) or "").resolve() != RUNNER_PATH.resolve():
    raise RuntimeError("Stage 1 must import the repository-bound Codex provider primitive")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def _immutable_json(path: Path, value: Mapping[str, Any]) -> None:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != rendered:
            raise RuntimeError(f"Immutable artifact drifted: {path}")
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


def _fingerprint(path: Path) -> dict[str, Any]:
    actual = path.resolve()
    if not actual.is_file():
        raise RuntimeError(f"Missing bound file: {actual}")
    contents = actual.read_bytes()
    return {"path": str(actual), "bytes": len(contents), "sha256": _sha256(contents)}


def _safe_fingerprint(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Expose an immutable artifact identity without disclosing its local path."""
    if set(binding) != {"path", "bytes", "sha256"} or not isinstance(binding.get("path"), str) or type(binding.get("bytes")) is not int or not isinstance(binding.get("sha256"), str):
        raise RuntimeError("Source or context binding is malformed")
    return {"path_sha256": _sha256(binding["path"]), "bytes": binding["bytes"], "sha256": binding["sha256"]}


def _paths_disjoint(left: Path, right: Path) -> bool:
    first, second = left.resolve(), right.resolve()
    return first != second and first not in second.parents and second not in first.parents


def _git_output(repo: Path, arguments: Sequence[str]) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *arguments], text=True, encoding="utf-8", capture_output=True, check=False)
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no diagnostic"
        raise RuntimeError(f"Git binding failed: {detail}")
    return completed.stdout.strip()


def _pushed_git_binding(repo: Path, bound_paths: Sequence[Path]) -> dict[str, Any]:
    """Require the complete tracked prompt runtime to equal the pushed revision."""
    root = repo.resolve()
    head = _git_output(root, ["rev-parse", "HEAD"])
    remote = _git_output(root, ["rev-parse", "origin/main"])
    if head != remote:
        raise RuntimeError("Stage 1 requires HEAD to equal origin/main before provider contact")
    for arguments in (["diff", "--quiet"], ["diff", "--cached", "--quiet"]):
        clean = subprocess.run(["git", "-C", str(root), *arguments], capture_output=True, check=False)
        if clean.returncode not in {0, 1}:
            raise RuntimeError("Unable to establish the tracked-runtime Git binding")
        if clean.returncode:
            raise RuntimeError("Stage 1 requires every tracked prompt-producing byte to match pushed HEAD")
    files: dict[str, dict[str, Any]] = {}
    for path in bound_paths:
        actual = path.resolve()
        try:
            relative = actual.relative_to(root).as_posix()
        except ValueError as error:
            raise RuntimeError(f"Bound path lies outside repository: {actual}") from error
        contents = actual.read_bytes()
        recorded = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{relative}"], capture_output=True, check=False)
        if recorded.returncode or recorded.stdout != contents:
            raise RuntimeError(f"Pushed revision does not contain the executed bytes: {relative}")
        files[relative] = {"bytes": len(contents), "sha256": _sha256(contents)}
    return {"revision": head, "remote_ref": "origin/main", "complete_tracked_worktree_clean": True, "files": files, "sha256": _sha256(_canonical(files))}


def _stage1_cells(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    cells = [dict(cell) for cell in plan["cells"] if cell["repetition"] == 1 and cell["source"] == "new_provider_evidence"]
    expected = ["global_negative_batch32", "single_positive_batch1", "single_negative_batch1"]
    if [cell["condition_id"] for cell in cells] != expected or sum(int(cell["new_calls"]) for cell in cells) != 60:
        raise RuntimeError("Prepared plan is not the exact Stage 1 60-call geometry")
    if any(cell["condition_id"] == "global_positive_batch32" for cell in cells):
        raise RuntimeError("The parent-reused global-positive cell may never be called")
    return cells


def _schedule(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cell in _stage1_cells(plan):
        condition = study.condition_map()[cell["condition_id"]]
        for call_in_cell, question_ids in enumerate(study._chunks(cell["question_ids"], int(condition["batch_size"])), 1):
            prompt = study.rendered_prompt(plan, cell, question_ids)
            result.append({
                "sequence": len(result) + 1,
                "condition_id": cell["condition_id"],
                "repetition": 1,
                "call_in_cell": call_in_cell,
                "question_ids": question_ids,
                "prompt": prompt,
                "prompt_sha256": _sha256(prompt),
            })
    if len(result) != 60 or len({item["sequence"] for item in result}) != 60:
        raise RuntimeError("Stage 1 physical-call schedule drifted")
    return result


def _public_disclosure(plan: Mapping[str, Any], schedule: Sequence[Mapping[str, Any]], private_root: Path) -> dict[str, Any]:
    parent_cell = plan["parent"]["parent_cell"]
    artifact = parent_cell.get("artifact") if isinstance(parent_cell, Mapping) else None
    contexts = parent_cell.get("contexts") if isinstance(parent_cell, Mapping) else None
    if not isinstance(artifact, Mapping) or not isinstance(contexts, list) or any(not isinstance(value, Mapping) for value in contexts):
        raise RuntimeError("Prepared plan lacks safe source/context bindings")
    return {
        "format_version": 1,
        "study_id": study.load_contract()["study_id"],
        "stage": 1,
        "remote_destination": {"provider": "codex", "model": MODEL, "reasoning": REASONING},
        "private_raw_root": {"path_sha256": _sha256(str(private_root.resolve()))},
        "outbound_artifacts": {"source": _safe_fingerprint(artifact), "contexts": [_safe_fingerprint(value) for value in contexts]},
        "outbound_requests": [
            {key: item[key] for key in ("sequence", "condition_id", "repetition", "call_in_cell", "question_ids", "prompt_sha256")}
            for item in schedule
        ],
        "outbound_content": "Each private attempt preserves the exact rendered prompt. This public projection contains only commitments and source/context fingerprints.",
        "no_human_judging": True,
        "no_adaptive_confidence_repeats": True,
        "automatic_stage_2": "forbidden",
        "recommendation": None,
        "promotion": "forbidden",
    }


def _execution_contract(plan: Mapping[str, Any], work: Path, private_root: Path, repo: Path, schedule: Sequence[Mapping[str, Any]], disclosure: Path) -> dict[str, Any]:
    bound = [STUDY_PATH, SCHEMA_PATH, HERE / "run_stage1.py", HERE / "study-contract.json", HERE / "polarity-pairs.json", RUNNER_PATH]
    git = _pushed_git_binding(repo, bound)
    return {
        "format_version": 1,
        "study_id": plan["study_id"],
        "stage": 1,
        "pilot_plan": _fingerprint(work / "pilot-contract.json"),
        "executor": _fingerprint(HERE / "run_stage1.py"),
        "response_schema": _fingerprint(SCHEMA_PATH),
        "study_runtime": {path.name: _fingerprint(path) for path in bound if path != HERE / "run_stage1.py" and path != SCHEMA_PATH},
        "pushed_git": git,
        "disclosure": _fingerprint(disclosure),
        "private_raw_root_sha256": _sha256(str(private_root.resolve())),
        "schedule_sha256": _sha256(_canonical([{key: item[key] for key in ("sequence", "condition_id", "repetition", "call_in_cell", "question_ids", "prompt_sha256")} for item in schedule])),
        "provider": {"provider": "codex", "model": MODEL, "reasoning": REASONING, "fresh_ephemeral_sessions": True, "attempts_per_call": 1, "timeout_seconds": TIMEOUT_SECONDS},
        "outcome_policy": {"stage_gate": "stage_1_complete", "next_stage": 2, "recommendation": None, "promotion": "forbidden", "automatic_stage_2": "forbidden"},
    }


def _parse_response(response: str, expected_ids: Sequence[str]) -> list[dict[str, Any]]:
    try:
        verdicts = json.loads(response)
    except json.JSONDecodeError as error:
        raise RuntimeError("Provider response is not JSON") from error
    if not isinstance(verdicts, list) or len(verdicts) != len(expected_ids):
        raise RuntimeError("Provider response verdict geometry drifted")
    output: list[dict[str, Any]] = []
    for verdict, question_id in zip(verdicts, expected_ids, strict=True):
        if not isinstance(verdict, dict) or set(verdict) != {"question_id", "verdict", "confidence"}:
            raise RuntimeError("Provider response does not use the executor-owned schema")
        confidence = verdict.get("confidence")
        if verdict.get("question_id") != question_id or verdict.get("verdict") not in study.STATES or type(confidence) not in {int, float} or isinstance(confidence, bool) or not 0 <= float(confidence) <= 1:
            raise RuntimeError("Provider response violates ordered verdict constraints")
        output.append({"question_id": question_id, "verdict": verdict["verdict"], "confidence": confidence})
    return output


def _attempt_paths(private_root: Path, sequence: int) -> tuple[Path, Path, Path]:
    root = private_root / ATTEMPTS / f"{sequence:04d}"
    return root, root / "attempt-start.json", root / "terminal.json"


def _safe_freeze(work: Path, private_root: Path, *, reason: str, schedule_item: Mapping[str, Any] | None, detail: str | None = None, response: str | None = None) -> None:
    value: dict[str, Any] = {
        "format_version": 1,
        "study_id": study.load_contract()["study_id"],
        "stage": 1,
        "status": "frozen_failure",
        "reason": reason,
        "detail_sha256": _sha256(detail) if detail is not None else None,
        "response_sha256": _sha256(response) if response is not None else None,
        "sequence": schedule_item["sequence"] if schedule_item is not None else None,
        "prompt_sha256": schedule_item["prompt_sha256"] if schedule_item is not None else None,
        "private_raw_root_sha256": _sha256(str(private_root.resolve())),
        "recommendation": None,
        "promotion": "forbidden",
    }
    _immutable_json(work / FREEZE_NAME, value)


def _freeze_and_raise(work: Path, private_root: Path, reason: str, item: Mapping[str, Any] | None = None, detail: str | None = None, response: str | None = None) -> None:
    _safe_freeze(work, private_root, reason=reason, schedule_item=item, detail=detail, response=response)
    raise RuntimeError(f"Stage 1 is frozen: {reason}")


def _provider_receipt(provider_record: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if set(provider_record) != {"command", "reported"}:
        raise RuntimeError("Provider receipt schema drifted")
    command, reported = provider_record.get("command"), provider_record.get("reported")
    if not isinstance(command, list) or not command or any(not isinstance(value, str) for value in command):
        raise RuntimeError("Provider receipt command is malformed")
    if not isinstance(reported, Mapping) or set(reported) != {"model", "provider", "reasoning_effort", "session_id"}:
        raise RuntimeError("Provider receipt reported settings are incomplete")
    if reported["provider"] != "openai" or reported["model"] != MODEL or reported["reasoning_effort"] != REASONING or not isinstance(reported["session_id"], str) or not reported["session_id"]:
        raise RuntimeError("Provider receipt does not attest the frozen Codex session settings")
    return {"command": list(command), "reported": dict(reported)}, reported["session_id"]


def _terminal_success(item: Mapping[str, Any], response: str, provider_record: Mapping[str, Any]) -> dict[str, Any]:
    receipt, session_id = _provider_receipt(provider_record)
    verdicts = _parse_response(response, item["question_ids"])
    return {
        "format_version": 1,
        "status": "accepted",
        "sequence": item["sequence"],
        "condition_id": item["condition_id"],
        "repetition": item["repetition"],
        "call_in_cell": item["call_in_cell"],
        "prompt_sha256": item["prompt_sha256"],
        "response": response,
        "response_sha256": _sha256(response),
        "session_id_sha256": _sha256(session_id),
        "provider_record": receipt,
        "verdicts": verdicts,
    }


def _validate_terminal(terminal: Mapping[str, Any], item: Mapping[str, Any], sessions: set[str]) -> dict[str, Any]:
    required = {"format_version", "status", "sequence", "condition_id", "repetition", "call_in_cell", "prompt_sha256", "response", "response_sha256", "session_id_sha256", "provider_record", "verdicts"}
    if set(terminal) != required or terminal.get("format_version") != 1 or terminal.get("status") != "accepted":
        raise RuntimeError("Private terminal record schema drifted")
    for key in ("sequence", "condition_id", "repetition", "call_in_cell", "prompt_sha256"):
        if terminal.get(key) != item[key]:
            raise RuntimeError("Private terminal record no longer binds its scheduled call")
    if not isinstance(terminal.get("response"), str) or terminal.get("response_sha256") != _sha256(terminal["response"]):
        raise RuntimeError("Private terminal response commitment drifted")
    provider_record = terminal.get("provider_record")
    if not isinstance(provider_record, Mapping):
        raise RuntimeError("Private terminal lacks a provider receipt")
    _, session_id = _provider_receipt(provider_record)
    if terminal.get("session_id_sha256") != _sha256(session_id) or terminal["session_id_sha256"] in sessions:
        raise RuntimeError("Private terminal session is absent or duplicate")
    if _parse_response(terminal["response"], item["question_ids"]) != terminal.get("verdicts"):
        raise RuntimeError("Private terminal verdicts are not response-derived")
    sessions.add(terminal["session_id_sha256"])
    return dict(terminal)


def _evidence_rows(schedule: Sequence[Mapping[str, Any]], terminals: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in schedule:
        grouped[str(item["condition_id"])].append(item)
    rows: list[dict[str, Any]] = []
    for condition_id in ("global_negative_batch32", "single_positive_batch1", "single_negative_batch1"):
        calls = grouped[condition_id]
        rows.append({
            "condition_id": condition_id,
            "repetition": 1,
            "calls": [{
                "question_ids": item["question_ids"],
                "session_id_sha256": terminals[int(item["sequence"])]["session_id_sha256"],
                "prompt": item["prompt"],
                "prompt_sha256": item["prompt_sha256"],
                "response": terminals[int(item["sequence"])]["response"],
                "response_sha256": terminals[int(item["sequence"])]["response_sha256"],
                "verdicts": terminals[int(item["sequence"])]["verdicts"],
            } for item in calls],
        })
    return rows


def _public_evidence_rows(schedule: Sequence[Mapping[str, Any]], terminals: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in schedule:
        grouped[str(item["condition_id"])].append(item)
    rows: list[dict[str, Any]] = []
    for condition_id in ("global_negative_batch32", "single_positive_batch1", "single_negative_batch1"):
        calls = grouped[condition_id]
        rows.append({
            "condition_id": condition_id,
            "repetition": 1,
            "call_count": len(calls),
            "calls": [{
                "sequence": item["sequence"],
                "question_ids_sha256": _sha256(_canonical(item["question_ids"])),
                "prompt_sha256": item["prompt_sha256"],
                "response_sha256": terminals[int(item["sequence"])]["response_sha256"],
                "session_id_sha256": terminals[int(item["sequence"])]["session_id_sha256"],
                "verdicts_sha256": _sha256(_canonical(terminals[int(item["sequence"])]["verdicts"])),
            } for item in calls],
        })
    return rows


def _validate_completed(work: Path, private_root: Path, plan: Mapping[str, Any], schedule: Sequence[Mapping[str, Any]], terminals: Mapping[int, Mapping[str, Any]]) -> dict[str, Any]:
    rows = _evidence_rows(schedule, terminals)
    study.verify_evidence(plan, rows)
    gate = study.stage_gate(plan, rows)
    if gate != {"study_id": plan["study_id"], "completed_stage": 1, "status": "stage_1_complete", "next_stage": 2, "recommendation": None, "promotion": "forbidden"}:
        raise RuntimeError("Stage 1 gate did not preserve the frozen no-promotion outcome")
    raw_evidence = {"format_version": 1, "study_id": plan["study_id"], "stage": 1, "rows": rows, "row_count": 3, "call_count": 60, "recommendation": None, "promotion": "forbidden"}
    private_evidence = private_root / RAW_EVIDENCE_NAME
    _immutable_json(private_evidence, raw_evidence)
    raw_bytes = private_evidence.read_bytes()
    evidence = {"format_version": 1, "study_id": plan["study_id"], "stage": 1, "rows": _public_evidence_rows(schedule, terminals), "row_count": 3, "call_count": 60, "private_raw_evidence": {"bytes": len(raw_bytes), "sha256": _sha256(raw_bytes)}, "recommendation": None, "promotion": "forbidden"}
    _immutable_json(work / EVIDENCE_NAME, evidence)
    _immutable_json(work / GATE_NAME, gate)
    return {"status": gate["status"], "next_stage": gate["next_stage"], "calls": 60, "rows": 3}


def _bootstrap(work: Path, private_root: Path, repo: Path, *, dry_run: bool) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
    if not _paths_disjoint(work, private_root):
        raise RuntimeError("Public work and private raw roots must be disjoint")
    if repo.resolve() == private_root.resolve() or repo.resolve() in private_root.resolve().parents:
        raise RuntimeError("Private raw root must not be inside the repository")
    plan = study.load_plan(work)
    schedule = _schedule(plan)
    disclosure_value = _public_disclosure(plan, schedule, private_root)
    if dry_run:
        return plan, schedule, None
    disclosure = work / DISCLOSURE_NAME
    _immutable_json(disclosure, disclosure_value)
    contract = _execution_contract(plan, work, private_root, repo, schedule, disclosure)
    _immutable_json(work / EXECUTION_NAME, contract)
    loaded = _read_json(work / EXECUTION_NAME)
    if loaded != contract:
        raise RuntimeError("Stage 1 execution contract drifted")
    return plan, schedule, contract


def dry_run(work: Path, private_root: Path, *, repo: Path = REPOSITORY) -> dict[str, Any]:
    plan, schedule, _ = _bootstrap(work, private_root, repo, dry_run=True)
    return {"study_id": plan["study_id"], "stage": 1, "provider_calls": 0, "scheduled_calls": len(schedule), "conditions": [cell["condition_id"] for cell in _stage1_cells(plan)]}


def execute_stage1(work: Path, private_root: Path, *, executable: str = "codex", timeout: float = TIMEOUT_SECONDS, repo: Path = REPOSITORY, dry_run_only: bool = False) -> dict[str, Any]:
    """Execute only the 60 physical Stage 1 calls, each at most once."""
    if timeout != TIMEOUT_SECONDS:
        raise RuntimeError("Stage 1 timeout is frozen at 600 seconds")
    if dry_run_only:
        return dry_run(work, private_root, repo=repo)
    plan, schedule, _ = _bootstrap(work, private_root, repo, dry_run=False)
    if (work / FREEZE_NAME).exists():
        raise RuntimeError("Stage 1 root is frozen and cannot be resumed")
    parent_sessions = {item["session_id_sha256"] for item in plan["parent"]["parent_verifier"]["sessions"]}
    terminals: dict[int, dict[str, Any]] = {}
    for item in schedule:
        root, started_path, terminal_path = _attempt_paths(private_root, int(item["sequence"]))
        if started_path.exists() and not terminal_path.exists():
            _freeze_and_raise(work, private_root, "started_without_terminal", item)
        if terminal_path.exists():
            try:
                terminals[int(item["sequence"])] = _validate_terminal(_read_json(terminal_path), item, parent_sessions)
            except RuntimeError as error:
                _freeze_and_raise(work, private_root, "invalid_existing_terminal", item, str(error))
            continue
        if root.exists() and any(root.iterdir()):
            _freeze_and_raise(work, private_root, "unknown_partial_attempt_state", item)
        start = {"format_version": 1, "status": "started", "sequence": item["sequence"], "condition_id": item["condition_id"], "repetition": 1, "call_in_cell": item["call_in_cell"], "question_ids": item["question_ids"], "prompt": item["prompt"], "prompt_sha256": item["prompt_sha256"], "response_schema": _fingerprint(SCHEMA_PATH), "provider": {"provider": "codex", "model": MODEL, "reasoning": REASONING, "ephemeral": True, "attempt_number": 1}}
        _immutable_json(started_path, start)
        try:
            response, provider_record = _call_codex(executable=executable, model=MODEL, reasoning=REASONING, prompt=item["prompt"], output_dir=root, response_schema=SCHEMA_PATH, batch_number=int(item["sequence"]), attempt_number=1, timeout=TIMEOUT_SECONDS)
            terminal = _terminal_success(item, response, provider_record)
            terminals[int(item["sequence"])] = _validate_terminal(terminal, item, parent_sessions)
            _immutable_json(terminal_path, terminal)
        except BaseException as error:
            response = getattr(error, "content", None)
            provider_record = getattr(error, "provider_record", None)
            failure = {"format_version": 1, "status": "failed", "sequence": item["sequence"], "prompt_sha256": item["prompt_sha256"], "error_sha256": _sha256(str(error)), "response_sha256": _sha256(response) if isinstance(response, str) else None, "provider_record": provider_record if isinstance(provider_record, Mapping) else None}
            _immutable_json(terminal_path, failure)
            _freeze_and_raise(work, private_root, "provider_or_response_failure", item, str(error), response if isinstance(response, str) else None)
    return _validate_completed(work, private_root, plan, schedule, terminals)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=REPOSITORY)
    parser.add_argument("--executable", default="codex")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args(argv)
    result = execute_stage1(arguments.work, arguments.private_root, executable=arguments.executable, repo=arguments.repo, dry_run_only=arguments.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
