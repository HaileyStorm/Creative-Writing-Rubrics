"""Read-only settlement for the L2 CRLF-to-LF compatibility repair."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from hbqrs import runner


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
EXECUTION_PACKAGE = REPOSITORY / "evaluation-results" / "hbq-other-lexical-overlap-ownership-v1-execution-v1"
STUDY_ID = "hbq-other-lexical-overlap-ownership-v1-settlement-crlf-lf-repair-v1"
EXECUTION_STUDY_ID = "hbq-other-lexical-overlap-ownership-v1-execution-v1"
EXECUTION_COMMIT = "bd7f4f90031c451ae27a74ff3f07bab08d619d9c"
EXECUTION_TREE = "1c3eea1903d8858cae67ce92c24c779aa548bea2"
EXECUTION_FILES = {
    "README.md": "bc13f234b9342f9b37082d6517914a0b642aa718",
    "run.py": "f1d5d3445468e8616e5acbe35cbb957970aa487d",
    "study-contract.json": "d7008bd55b31651e16febf286ee367956b1b38a2",
    "study.py": "f96217ae9bea64733eead031ccf161e301b67afa",
}
EXECUTION_SLOTS, CELLS, VISUAL_SLOTS = 216, 72, 72
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate immutable settlement artifact: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if done.returncode:
        raise ValueError(done.stderr.strip() or "git binding lookup failed")
    return done.stdout.strip()


def _external_root(value: str | Path, *, label: str) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        return root
    raise ValueError(f"{label} must be outside the CWR checkout")


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _execution() -> Any:
    spec = importlib.util.spec_from_file_location("l2_execution_for_crlf_lf_settlement", EXECUTION_PACKAGE / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Frozen L2 execution package is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_package() -> dict[str, Any]:
    value = contract()
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "settlement_only_compatibility_repair",
        "execution_predecessor": {"commit": EXECUTION_COMMIT, "tree": EXECUTION_TREE, "study_id": EXECUTION_STUDY_ID},
        "compatibility": {"accepted_raw_to_canonical_transform": "crlf_to_lf_only_v1", "lone_cr": "rejected", "other_prompt_mutation": "rejected", "retain_raw_and_canonical_sha256": True},
        "geometry": {"execution_slots": EXECUTION_SLOTS, "three_repeat_cells": CELLS, "visual_attachment_slots": VISUAL_SLOTS},
        "provider_calls": "forbidden",
        "public_result_policy": "aggregate_only_verified_diagnostic_fail_or_incomplete_no_promotion",
        "promotion": "none",
    }
    if value != expected:
        raise ValueError("Settlement contract drifted")
    if _git("rev-parse", f"{EXECUTION_COMMIT}:evaluation-results/hbq-other-lexical-overlap-ownership-v1-execution-v1") != EXECUTION_TREE:
        raise ValueError("Pinned L2 execution tree is unavailable")
    for name, blob in EXECUTION_FILES.items():
        source = EXECUTION_PACKAGE / name
        if _git("rev-parse", f"{EXECUTION_COMMIT}:evaluation-results/hbq-other-lexical-overlap-ownership-v1-execution-v1/{name}") != blob or _git("hash-object", str(source)) != blob:
            raise ValueError("Imported execution package differs from the pinned historical tree")
    execution = _execution()
    report = execution.validate_package()
    if report != {"study_id": EXECUTION_STUDY_ID, "slots": EXECUTION_SLOTS, "provider_calls": 0, "predecessor": execution.PREDECESSOR_COMMIT, "visual_image_slots": VISUAL_SLOTS}:
        raise ValueError("Execution-package verification drifted")
    return {"study_id": STUDY_ID, "execution_slots": EXECUTION_SLOTS, "three_repeat_cells": CELLS, "provider_calls": 0}


def canonical_lf(raw: bytes) -> bytes:
    if b"\r" in raw.replace(b"\r\n", b""):
        raise ValueError("Prompt contains a lone CR byte")
    return raw.replace(b"\r\n", b"\n")


def _prompt_commitment(raw: bytes, expected_canonical: bytes) -> dict[str, Any]:
    canonical = canonical_lf(raw)
    if canonical != expected_canonical:
        raise ValueError("Rendered prompt differs beyond CRLF-to-LF compatibility")
    return {
        "raw_sha256": sha256_bytes(raw),
        "canonical_sha256": sha256_bytes(canonical),
        "canonical_matches_frozen": True,
        "line_ending_transform": "identity" if raw == canonical else "crlf_to_lf",
    }


def _schedule(execution: Any) -> list[dict[str, Any]]:
    schedule = execution.build_schedule()
    if len(schedule) != EXECUTION_SLOTS or len({slot["slot_id"] for slot in schedule}) != EXECUTION_SLOTS:
        raise ValueError("Frozen execution slot geometry drifted")
    if len({(slot["case_id"], slot["leaf_id"]) for slot in schedule}) != CELLS:
        raise ValueError("Frozen execution cell geometry drifted")
    if sum(slot["image_input"] is not None for slot in schedule) != VISUAL_SLOTS:
        raise ValueError("Frozen execution visual-slot geometry drifted")
    return schedule


def _validate_execution_root(execution_root: Path, execution: Any, schedule: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    manifest = _load_json(execution_root / "study-manifest.json")
    runtime_schedule = _load_json(execution_root / "runtime-schedule.json")
    private_schedule = _load_json(execution_root / "private-schedule.json")
    expected_public = [execution._public_slot(slot) for slot in schedule]
    expected_private = schedule
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["prompt_sha256"] for slot in expected_public}))
    if manifest.get("study_id") != EXECUTION_STUDY_ID or manifest.get("contract_sha256") != sha256_file(EXECUTION_PACKAGE / "study-contract.json") or manifest.get("runtime_bindings") != execution._runtime_bindings() or manifest.get("planned_slots") != EXECUTION_SLOTS or manifest.get("slots") != expected_public:
        raise ValueError("Execution manifest does not bind the frozen 216-slot schedule")
    if runtime_schedule != {"format_version": 1, "slots": expected_public, "rendered_prompt_aggregate_sha256": aggregate}:
        raise ValueError("Execution runtime schedule drifted")
    if private_schedule != {"format_version": 1, "slots": expected_private}:
        raise ValueError("Execution private schedule drifted")
    commitments: dict[str, dict[str, Any]] = {}
    for slot in schedule:
        prompt_path = execution_root / "rendered-prompts" / f"{slot['slot_id']}.txt"
        commitment = _prompt_commitment(prompt_path.read_bytes(), str(slot["prompt"]).encode("utf-8"))
        if commitment["canonical_sha256"] != slot["prompt_sha256"]:
            raise ValueError("Canonical prompt SHA-256 does not match frozen slot commitment")
        commitments[str(slot["slot_id"])] = commitment
    if len(commitments) != EXECUTION_SLOTS:
        raise ValueError("Rendered prompt commitments are incomplete")
    return commitments


def _verify_attempt(execution_root: Path, execution: Any, slot: Mapping[str, Any], attempt: int, commitment: Mapping[str, Any]) -> dict[str, Any]:
    intent = execution._load_json(execution._intent_path(execution_root, slot, attempt))
    receipt = execution._load_json(execution._receipt_path(execution_root, slot, attempt))
    response = execution._response_path(execution_root, slot, attempt)
    attempt_id = f"{slot['run_id']}-attempt-{attempt:02d}"
    if intent.get("state") != "contact_started" or intent.get("run_id") != slot["run_id"] or intent.get("attempt") != attempt or intent.get("attempt_id") != attempt_id:
        raise ValueError("Attempt intent is incomplete")
    if receipt.get("returncode") != 0 or receipt.get("attempt_id") != attempt_id or not response.is_file():
        raise ValueError("Attempt receipt or output is incomplete")
    if receipt.get("reported") != {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high"}:
        raise ValueError("Codex provider/model/reasoning report is absent or drifted")
    command = execution.command_for(slot, execution_root, attempt=attempt)
    if intent.get("command") != command or receipt.get("command_sha256") != sha256_bytes(canonical_json(command)):
        raise ValueError("Codex command binding drifted")
    if intent.get("prompt_sha256") != slot["prompt_sha256"] or commitment.get("canonical_sha256") != slot["prompt_sha256"]:
        raise ValueError("Frozen canonical prompt binding drifted")
    if slot["image_input"]:
        attachment = execution._attachment_record(execution._input_path(execution_root, slot))
        if receipt.get("attachment") != attachment or intent.get("attachment") != attachment or attachment["sha256"] != slot["image_input"]["sha256"]:
            raise ValueError("Exact PNG attachment binding drifted")
    elif intent.get("attachment") is not None or receipt.get("attachment") is not None:
        raise ValueError("Text slot unexpectedly carries an attachment")
    try:
        payload = json.loads(response.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Structured Codex response is malformed") from exc
    try:
        validated = execution._validate_response(slot, payload)
    except (ValueError, runner.HBQError) as exc:
        raise ValueError("Structured Codex response is invalid") from exc
    verdict = validated["verdict"]
    return {
        "slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": verdict["verdict"],
        "expected": slot["expected_verdict"], "correct": verdict["verdict"] == slot["expected_verdict"], "run_id": slot["run_id"],
        "attempt": attempt, "attempt_id": attempt_id, "response_sha256": sha256_file(response), "command_sha256": receipt["command_sha256"],
        "attachment_sha256": receipt["attachment"]["sha256"] if receipt.get("attachment") else None,
        "prompt_commitment": dict(commitment), "evidence": verdict["evidence"], "normalization_audit": validated["normalization_audit"],
    }


def _accepted_slot(execution_root: Path, execution: Any, slot: Mapping[str, Any], commitment: Mapping[str, Any]) -> dict[str, Any] | None:
    outcomes: list[tuple[int, str]] = []
    for attempt in range(1, 4):
        outcome = execution._outcome_path(execution_root, slot, attempt)
        if not outcome.exists():
            continue
        value = execution._load_json(outcome)
        state = value.get("state")
        if state not in {"accepted", "rejected"}:
            raise ValueError("Attempt outcome is malformed")
        outcomes.append((attempt, state))
    accepted = [attempt for attempt, state in outcomes if state == "accepted"]
    if not accepted:
        return None
    if [attempt for attempt, _ in outcomes] != list(range(1, len(outcomes) + 1)) or len(accepted) != 1 or accepted[0] != outcomes[-1][0] or any(state != "rejected" for _, state in outcomes[:-1]):
        raise ValueError("Accepted logical slot has invalid attempt history")
    record = _verify_attempt(execution_root, execution, slot, accepted[0], commitment)
    record.update({"accepted_provider_call_count": 1, "rejected_retry_count": sum(state == "rejected" for _, state in outcomes), "batch_attempt_count": len(outcomes)})
    return record


def _public_aggregate(*, completed_slots: int, integrity: str, scored_cells: dict[str, int], controls: dict[str, int], counts: Mapping[str, Mapping[str, int]], prompt_commitments: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    verified = integrity == "VERIFIED"
    return {
        "study_id": STUDY_ID,
        "execution_predecessor": EXECUTION_STUDY_ID,
        "decision": "DIAGNOSTIC_FAIL" if verified else "INCOMPLETE",
        "integrity": integrity,
        "publicable": verified,
        "completed_execution_slots": completed_slots,
        "required_execution_slots": EXECUTION_SLOTS,
        "three_repeat_cells": CELLS,
        "scored_cells": scored_cells,
        "not_applicable_diagnostic_cells": controls,
        "canonical_four_state_counts": counts,
        "visual_attachment_slots": VISUAL_SLOTS,
        "prompt_commitments": {
            "slots": len(prompt_commitments),
            "raw_aggregate_sha256": sha256_bytes(canonical_json({slot: value["raw_sha256"] for slot, value in prompt_commitments.items()})),
            "canonical_aggregate_sha256": sha256_bytes(canonical_json({slot: value["canonical_sha256"] for slot, value in prompt_commitments.items()})),
            "accepted_transform": "crlf_to_lf_only_v1",
        },
        "promotion": "none",
        "provider_calls": 0,
    }


def _write_result(settlement_root: Path, settlement: Mapping[str, Any], public: Mapping[str, Any]) -> None:
    _write_or_verify(settlement_root / "settlement.json", canonical_json(settlement))
    _write_or_verify(settlement_root / "public-aggregate.json", canonical_json(public))


def settle(execution_root: str | Path, settlement_root: str | Path) -> dict[str, Any]:
    source = _external_root(execution_root, label="execution_root")
    destination = _external_root(settlement_root, label="settlement_root")
    if source == destination:
        raise ValueError("Settlement root must be distinct from immutable execution evidence")
    execution = _execution()
    try:
        validate_package()
        schedule = _schedule(execution)
        commitments = _validate_execution_root(source, execution, schedule)
    except (OSError, ValueError) as exc:
        settlement = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_execution_slots": 0, "required_execution_slots": EXECUTION_SLOTS, "failures": [{"slot_id": "schedule", "reason": str(exc)}], "promotion": "none", "provider_calls": 0}
        public = _public_aggregate(completed_slots=0, integrity="FAILED", scored_cells={"passed": 0, "total": 0}, controls={"matched": 0, "total": 0}, counts={}, prompt_commitments={})
        _write_result(destination, settlement, public)
        return settlement
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for slot in schedule:
        try:
            record = _accepted_slot(source, execution, slot, commitments[str(slot["slot_id"])])
            if record is None or record.get("slot_id") != slot["slot_id"] or record.get("verdict") not in VERDICTS or record.get("run_id") != slot["run_id"]:
                raise ValueError("Verifier returned malformed singleton identity")
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != EXECUTION_SLOTS or len({row["slot_id"] for row in records}) != EXECUTION_SLOTS or len({row["logical_sample_id"] for row in records}) != EXECUTION_SLOTS or len({row["run_id"] for row in records}) != EXECUTION_SLOTS:
        settlement = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_execution_slots": len(records), "required_execution_slots": EXECUTION_SLOTS, "failures": failures or [{"slot_id": "identity", "reason": "duplicate logical or run identity"}], "promotion": "none", "provider_calls": 0}
        public = _public_aggregate(completed_slots=len(records), integrity="FAILED", scored_cells={"passed": 0, "total": 0}, controls={"matched": 0, "total": 0}, counts={}, prompt_commitments=commitments)
        _write_result(destination, settlement, public)
        return settlement
    visual = [row for row in records if next(slot for slot in schedule if slot["slot_id"] == row["slot_id"])["image_input"]]
    if len(visual) != VISUAL_SLOTS or len({row["attachment_sha256"] for row in visual}) != 6 or any(row["attachment_sha256"] is None for row in visual):
        settlement = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "completed_execution_slots": len(records), "required_execution_slots": EXECUTION_SLOTS, "failures": [{"slot_id": "images", "reason": "visual attachment receipts are incomplete"}], "promotion": "none", "provider_calls": 0}
        public = _public_aggregate(completed_slots=len(records), integrity="FAILED", scored_cells={"passed": 0, "total": 0}, controls={"matched": 0, "total": 0}, counts={}, prompt_commitments=commitments)
        _write_result(destination, settlement, public)
        return settlement
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    counts: dict[str, Counter[str]] = {leaf: Counter() for block in execution._predecessor().BLOCK_LEAVES.values() for leaf in block}
    by_slot = {str(slot["slot_id"]): slot for slot in schedule}
    for row in records:
        slot = by_slot[str(row["slot_id"])]
        cells[(str(slot["case_id"]), str(slot["leaf_id"]))].append(bool(row["correct"]))
        counts[str(slot["leaf_id"])][str(row["verdict"])] += 1
    states = {(str(slot["case_id"]), str(slot["leaf_id"])): str(slot["expected_verdict"]) for slot in schedule}
    per_cell = {f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": states[key]} for index, (key, values) in enumerate(cells.items(), start=1)}
    if len(per_cell) != CELLS:
        raise ValueError("Execution does not bind all required three-repeat cells")
    scored = [value for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE"]
    controls = [value for value in per_cell.values() if value["expected_state"] == "NOT_APPLICABLE"]
    four_state = {leaf: {state: counts[leaf][state] for state in sorted(VERDICTS)} for leaf in sorted(counts)}
    settlement = {"study_id": STUDY_ID, "execution_predecessor": EXECUTION_STUDY_ID, "decision": "DIAGNOSTIC_FAIL", "completed_execution_slots": EXECUTION_SLOTS, "required_execution_slots": EXECUTION_SLOTS, "three_repeat_cells": CELLS, "per_cell_three_of_three": per_cell, "canonical_four_state_counts": four_state, "visual_attachment_slots": VISUAL_SLOTS, "prompt_commitments": commitments, "promotion": "none", "provider_calls": 0, "records": records}
    public = _public_aggregate(completed_slots=EXECUTION_SLOTS, integrity="VERIFIED", scored_cells={"passed": sum(value["passed"] for value in scored), "total": len(scored)}, controls={"matched": sum(value["passed"] for value in controls), "total": len(controls)}, counts=four_state, prompt_commitments=commitments)
    _write_result(destination, settlement, public)
    return settlement
