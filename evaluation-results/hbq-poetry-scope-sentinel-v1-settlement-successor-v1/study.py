"""Provider-free read-only settlement for the completed frozen S1 evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping

from hbqrs import runner


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
EXECUTION_PACKAGE = REPOSITORY / "evaluation-results" / "hbq-poetry-scope-sentinel-v1-execution-v1"
STUDY_ID = "hbq-poetry-scope-sentinel-v1-settlement-successor-v1"
EXECUTION_STUDY_ID = "hbq-poetry-scope-sentinel-v1-execution-v1"
HISTORICAL_RUNTIME_HEAD = "9e22d715b0c05a8a411c48c6cf8471053c26a731"
EXECUTION_TREE = "0cea72a77fc91dac22e651357716522f485d0155"
RUNTIME_BLOBS = {
    "prompts/judge/JUDGE_PREFIX.md": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "d2662edfccc115c6d0c4d97af82a10c9e926b853",
    "schema/hbq_judge_response.schema.json": "1034a35dcd6c30a75101f369627d60e155d65c2c",
    "registry/all_modules.json": "d94af34c80cf32b4d5a380167e66e2af39f29ad7",
    "registry/question_index.jsonl": "4ab3b7e11fe2e150cc0defafc22a29929cf5799c",
    "registry/criterion_ownership.json": "685846945ddd562992b313b17e8efa72692b8036",
    "bundles/all_bundles.json": "3d4f8c0d2dcc7020111dbdaf0e40a9fe483bc2a4",
    "src/hbqrs/runner.py": "9fe6cedd4dc63ba7eb618e906093dff98436a835",
    "src/hbqrs/cli.py": "b4bece11db82a81d517d52f8ad21ef7ef824be0f",
}
SUCCESSOR_BLOBS = {
    "study.py": "170edd19770b41e5eda8db706935422991b65542",
    "run.py": "a111535d578bc4f1421d01684842d2a0aad904e3",
    "study-contract.json": "60b6816847d5fe0c2eea84a1f1496cd8bcccc888",
}
RUNTIME_SHA256 = {
    "bundles/all_bundles.json": "ca20defa2e3350f949dc9da5e69bb9061d5a0c2d6ddcd71bb9399262dad10f86",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
    "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
    "registry/all_modules.json": "4da342cc24881c70be11e5e2cd92a7beccbeb024e5808a5c779935f29989a4ed",
    "registry/criterion_ownership.json": "79d636c7c692926d15ff8ebd47c3592e6bb0e6640473c0948ae9dead4fdd6876",
    "registry/question_index.jsonl": "0de8eec70a5a4de74770570253af96f6483c07fcf00ebad198fe951cf2af1fb6",
    "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
    "src/hbqrs/cli.py": "3e7eb62d0dbcd92b3eaeba69a24177a3c34cc1048d4d34a2d077ab4d2cb44f45",
    "src/hbqrs/runner.py": "af97b27de7cf8aba63435489e83eb09307c45a0de3b6ce47ebdd847898b1a9f8",
}
SUCCESSOR_SHA256 = {
    "run.py": "5ea88c21c4d146fe98b10e683a2ea33d155325805f0930bca884e4fa9e6f5b40",
    "study-contract.json": "1394b64f29b96132baf19640a2ae469211059fda27b438992b4bcac7f3b915c4",
    "study.py": "20d9c6677bf6874d25071b18ed7a26241833d6405a51a4c9cee3daf4e2da1f50",
}
SOURCE_SETTLEMENT_SHA256 = "65bd1952e60bbf39845469a52ed8822a27435611d7c4137e43d7b5ddf040265e"
SOURCE_PUBLIC_SHA256 = "94b16551c218e92c4c4b036d408903452b2611e4aa159aa879eb78c6186d06fb"
SOURCE_FILES = (
    "study-manifest.json", "private-schedule.json", "runtime-schedule.json", "dry-run.json",
    "settlement.json", "public-aggregate.json",
)
VERDICTS = frozenset(("YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"))
PRIVATE_RESULT = "settlement.json"
PUBLIC_RESULT = "public-aggregate.json"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path.name}")
    return value


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", "--no-optional-locks", *args], cwd=REPOSITORY, text=True,
        encoding="utf-8", capture_output=True, check=False,
    )
    if completed.returncode:
        raise ValueError(completed.stderr.strip() or "git binding lookup failed")
    return completed.stdout.strip()


def _git_lines(*args: str) -> list[str]:
    result = _git(*args)
    return result.splitlines() if result else []


def _external_root(value: str | Path, *, label: str) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        return root
    raise ValueError(f"{label} must be outside the CWR checkout")


def _require_separate_roots(source: Path, destination: Path) -> None:
    if source == destination or source.is_relative_to(destination) or destination.is_relative_to(source):
        raise ValueError("Settlement and immutable source roots must be disjoint")


def _write_or_verify(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise ValueError(f"Refusing to mutate immutable successor artifact: {path.name}")
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _write_results(root: Path, settlement: Mapping[str, Any], public: Mapping[str, Any]) -> None:
    _write_or_verify(root / PRIVATE_RESULT, canonical_json(settlement))
    _write_or_verify(root / PUBLIC_RESULT, canonical_json(public))


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _execution() -> Any:
    spec = importlib.util.spec_from_file_location("s1_execution_for_settlement_successor", EXECUTION_PACKAGE / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Frozen S1 execution package is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _expected_contract() -> dict[str, Any]:
    return {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "provider_free_read_only_settlement_successor",
        "execution_predecessor": {
            "study_id": EXECUTION_STUDY_ID,
            "runtime_head": HISTORICAL_RUNTIME_HEAD,
            "tree": EXECUTION_TREE,
            "runtime_paths": sorted(RUNTIME_BLOBS),
            "successor_paths": sorted(SUCCESSOR_BLOBS),
        },
        "source_artifacts": {
            "settlement_sha256": SOURCE_SETTLEMENT_SHA256,
            "public_aggregate_sha256": SOURCE_PUBLIC_SHA256,
            "required_completed_slots": 60,
        },
        "provider_calls": "forbidden",
        "source_policy": "read_only_external_execution_evidence",
        "public_result_policy": "aggregate_only_verified_result_or_incomplete_nonpublicable",
        "promotion": "none",
    }


def validate_package() -> dict[str, Any]:
    if contract() != _expected_contract():
        raise ValueError("Settlement successor contract drifted")
    if _git("rev-parse", f"{HISTORICAL_RUNTIME_HEAD}^{{commit}}") != HISTORICAL_RUNTIME_HEAD:
        raise ValueError("Historical S1 runtime commit is unavailable")
    package_path = "evaluation-results/hbq-poetry-scope-sentinel-v1-execution-v1"
    if _git("rev-parse", f"{HISTORICAL_RUNTIME_HEAD}:{package_path}") != EXECUTION_TREE:
        raise ValueError("Historical S1 execution tree is unavailable")
    historical_paths = [*RUNTIME_BLOBS, *(f"{package_path}/{name}" for name in SUCCESSOR_BLOBS)]
    historical_lines = _git_lines("ls-tree", "-r", HISTORICAL_RUNTIME_HEAD, "--", *historical_paths)
    historical = {line.rsplit("\t", 1)[1]: line.split()[2] for line in historical_lines}
    expected_historical = {**RUNTIME_BLOBS, **{f"{package_path}/{name}": blob for name, blob in SUCCESSOR_BLOBS.items()}}
    if historical != expected_historical:
        raise ValueError("Historical runtime or execution blob bindings drifted")
    if {path: sha256_file(REPOSITORY / path) for path in RUNTIME_BLOBS} != RUNTIME_SHA256:
        raise ValueError("Current runtime bytes differ from the source runtime commitments")
    if {name: sha256_file(EXECUTION_PACKAGE / name) for name in SUCCESSOR_BLOBS} != SUCCESSOR_SHA256:
        raise ValueError("Current execution bytes differ from the source successor commitments")
    return {"study_id": STUDY_ID, "execution_slots": 60, "provider_calls": 0, "historical_runtime_head": HISTORICAL_RUNTIME_HEAD}


def _source_input_commitments(source: Path) -> dict[str, Any]:
    files = {name: sha256_file(source / name) for name in SOURCE_FILES}
    return {"files": files, "aggregate_sha256": sha256_bytes(canonical_json(files))}


def _validate_source(source: Path, execution: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    validate_package()
    manifest = _load_json(source / "study-manifest.json")
    runtime = _load_json(source / "runtime-schedule.json")
    private_schedule = _load_json(source / "private-schedule.json")
    source_settlement = _load_json(source / "settlement.json")
    source_public = _load_json(source / "public-aggregate.json")
    if sha256_file(source / "settlement.json") != SOURCE_SETTLEMENT_SHA256 or sha256_file(source / "public-aggregate.json") != SOURCE_PUBLIC_SHA256:
        raise ValueError("Original incomplete source summaries differ from their immutable hashes")
    if source_settlement != {"study_id": EXECUTION_STUDY_ID, "decision": "INCOMPLETE", "completed_slots": 0, "planned_slots": 60, "failures": [{"slot_id": "runtime", "reason": "CWR runtime/schema/runner binding drifted; dry-run again"}]}:
        raise ValueError("Original settlement no longer records the expected incomplete runtime binding")
    if source_public != {"study_id": EXECUTION_STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": 0, "planned_slots": 60}:
        raise ValueError("Original public aggregate no longer records the expected incomplete state")
    source_bindings = manifest.get("runtime_bindings")
    expected_bindings = {"runtime_head": HISTORICAL_RUNTIME_HEAD, "cwr_files": RUNTIME_SHA256, "successor_files": SUCCESSOR_SHA256}
    if source_bindings != expected_bindings:
        raise ValueError("Source manifest runtime bindings differ from the frozen historical inputs")
    execution_report = execution.validate_package()
    if execution_report != {"study_id": EXECUTION_STUDY_ID, "slots": 60, "provider_calls": 0, "predecessor": execution.PREDECESSOR_COMMIT}:
        raise ValueError("Execution package validation report drifted")
    schedule = execution.build_schedule()
    expected_public = [execution._public_slot(slot) for slot in schedule]
    expected_runtime = execution._runtime_schedule(source, schedule)
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in expected_runtime}))
    if manifest != {"format_version": 1, "study_id": EXECUTION_STUDY_ID, "contract_sha256": sha256_file(EXECUTION_PACKAGE / "study-contract.json"), "runtime_bindings": expected_bindings, "planned_slots": 60, "slots": expected_public}:
        raise ValueError("Source manifest does not bind the frozen 60-slot schedule")
    if private_schedule != {"format_version": 1, "slots": schedule}:
        raise ValueError("Source private schedule differs from the frozen schedule")
    if runtime != {"format_version": 1, "slots": expected_runtime, "rendered_prompt_aggregate_sha256": aggregate}:
        raise ValueError("Source runtime schedule differs from frozen rendered-prompt commitments")
    return expected_runtime, _source_input_commitments(source)


def _incomplete(completed: int, failures: list[dict[str, str]], commitments: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    settlement = {"study_id": STUDY_ID, "execution_predecessor": EXECUTION_STUDY_ID, "decision": "INCOMPLETE", "completed_execution_slots": completed, "required_execution_slots": 60, "failures": failures, "source_input_commitments": dict(commitments), "promotion": "none", "provider_calls": 0}
    public = {"study_id": STUDY_ID, "decision": "INCOMPLETE", "integrity": "FAILED", "publicable": False, "completed_execution_slots": completed, "required_execution_slots": 60, "scored_cells": {"passed": 0, "total": 0}, "not_applicable_diagnostic_cells": {"matched": 0, "total": 0}, "canonical_four_state_counts": {}, "source_input_commitments": _public_commitments(commitments), "promotion": "none", "provider_calls": 0}
    return settlement, public


def _public_commitments(commitments: Mapping[str, Any]) -> dict[str, str]:
    files = commitments.get("files")
    if not isinstance(files, Mapping):
        return {"aggregate_sha256": "0" * 64}
    selected = ("study-manifest.json", "private-schedule.json", "runtime-schedule.json", "settlement.json", "public-aggregate.json")
    return {"source_input_aggregate_sha256": str(commitments.get("aggregate_sha256")), **{f"{name.removesuffix('.json').replace('-', '_')}_sha256": str(files.get(name)) for name in selected}}


def _privacy_failures(public: Mapping[str, Any]) -> list[str]:
    allowed = {"study_id", "decision", "integrity", "publicable", "completed_execution_slots", "required_execution_slots", "scored_cells", "not_applicable_diagnostic_cells", "canonical_four_state_counts", "source_input_commitments", "promotion", "provider_calls"}
    failures: list[str] = []
    if set(public) != allowed:
        failures.append("aggregate top-level allowlist mismatch")
    text = canonical_json(public).decode("utf-8")
    for label, pattern in (("path", r"[A-Za-z]:[\\/]"), ("prompt", r"prompt"), ("evidence", r"evidence"), ("session identifier", r"session[_-]?id"), ("run identifier", r"run[_-]?id")):
        if re.search(pattern, text, flags=re.IGNORECASE):
            failures.append(f"forbidden public metadata: {label}")
    return failures


def _complete(records: list[dict[str, Any]], schedule: list[dict[str, Any]], commitments: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(records) != 60 or len({row["slot_id"] for row in records}) != 60 or len({row["logical_sample_id"] for row in records}) != 60 or len({row["session_id_sha256"] for row in records}) != 60 or len({row["checkpoint_chain_head_sha256"] for row in records}) != 60:
        return _incomplete(len(records), [{"slot_id": "identity", "reason": "duplicate logical, session, or checkpoint identity"}], commitments)
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    counts = {str(slot["leaf_id"]): Counter() for slot in schedule}
    by_slot = {str(slot["slot_id"]): slot for slot in schedule}
    for row in records:
        slot = by_slot[str(row["slot_id"])]
        cells[(str(slot["artifact_id"]), str(slot["leaf_id"]))].append(bool(row["correct"]))
        counts[str(slot["leaf_id"])][str(row["verdict"])] += 1
    expected = {(str(slot["artifact_id"]), str(slot["leaf_id"])): str(slot["expected_verdict"]) for slot in schedule}
    per_cell = {f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": expected[key]} for index, (key, values) in enumerate(cells.items(), start=1)}
    if len(per_cell) != 20 or any(len(values) != 3 for values in cells.values()):
        return _incomplete(len(records), [{"slot_id": "cells", "reason": "incomplete three-repeat cell geometry"}], commitments)
    scored = [value for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE"]
    controls = [value for value in per_cell.values() if value["expected_state"] == "NOT_APPLICABLE"]
    four_state = {leaf: {state: counts[leaf][state] for state in sorted(VERDICTS)} for leaf in counts}
    decision = "PASS_NO_CHANGE" if all(value["passed"] for value in scored) else "DIAGNOSTIC_FAIL"
    settlement = {"study_id": STUDY_ID, "execution_predecessor": EXECUTION_STUDY_ID, "decision": decision, "completed_execution_slots": 60, "required_execution_slots": 60, "per_cell_three_of_three": per_cell, "canonical_four_state_counts": four_state, "source_input_commitments": dict(commitments), "promotion": "none", "provider_calls": 0, "records": records}
    public = {"study_id": STUDY_ID, "decision": decision, "integrity": "VERIFIED", "publicable": True, "completed_execution_slots": 60, "required_execution_slots": 60, "scored_cells": {"passed": sum(value["passed"] for value in scored), "total": len(scored)}, "not_applicable_diagnostic_cells": {"matched": sum(value["passed"] for value in controls), "total": len(controls)}, "canonical_four_state_counts": four_state, "source_input_commitments": _public_commitments(commitments), "promotion": "none", "provider_calls": 0}
    privacy = _privacy_failures(public)
    if privacy:
        return _incomplete(60, [{"slot_id": "public", "reason": "; ".join(privacy)}], commitments)
    return settlement, public


def settle(source_root: str | Path, settlement_root: str | Path, *, verifier: Callable[[Path, Mapping[str, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    source = _external_root(source_root, label="source_root")
    destination = _external_root(settlement_root, label="settlement_root")
    _require_separate_roots(source, destination)
    commitments = {"files": {}, "aggregate_sha256": "0" * 64}
    try:
        commitments = _source_input_commitments(source)
        schedule, commitments = _validate_source(source, _execution())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        settlement, public = _incomplete(0, [{"slot_id": "source", "reason": str(exc)}], commitments)
        _write_results(destination, settlement, public)
        return settlement
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    execution = _execution()
    for slot in schedule:
        try:
            record = verifier(source, slot) if verifier is not None else execution._verify_slot(source, slot)
            if record.get("slot_id") != slot["slot_id"] or record.get("verdict") not in VERDICTS:
                raise ValueError("Full per-slot verifier returned malformed singleton record")
            records.append(record)
        except (OSError, ValueError, runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    settlement, public = _incomplete(len(records), failures, commitments) if failures else _complete(records, schedule, commitments)
    _write_results(destination, settlement, public)
    return settlement
