"""Provider-free CRLF/LF settlement repair for the frozen premise-scale run."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
PREDECESSOR_ROOT = ROOT.parent / "hbq-premise-scale-ownership-v1-execution-v1"
STUDY_ID = "hbq-premise-scale-ownership-v1-settlement-repair-v1"
PREDECESSOR_COMMIT = "3258e6f44bb728ce17ebcd85b4964d472aaf87c2"
PREDECESSOR_TREE = "2c4dc6fee8332eaf52e04288e107c0f0c7fe317c"
SLOTS = 72
REPAIR_SETTLEMENT = "settlement-repair-v1.json"
REPAIR_PUBLIC = "public-aggregate-repair-v1.json"
HISTORICAL_RUNTIME_BINDINGS = {
    "runtime_head": PREDECESSOR_COMMIT,
    "cwr_files": {
        "bundles/all_bundles.json": "ca20defa2e3350f949dc9da5e69bb9061d5a0c2d6ddcd71bb9399262dad10f86",
        "prompts/judge/BINARY_EVALUATION_PROMPT.md": "6c1cac901d820c1ab866e19f9191896e8c97a6aadf35bdae4eac640fd199a3a2",
        "prompts/judge/JUDGE_PREFIX.md": "5e3a0990efca93e2cbc3894e635f9fd1b97b6e61ea2981940319cb54994ebb74",
        "registry/all_modules.json": "4da342cc24881c70be11e5e2cd92a7beccbeb024e5808a5c779935f29989a4ed",
        "registry/question_index.jsonl": "0de8eec70a5a4de74770570253af96f6483c07fcf00ebad198fe951cf2af1fb6",
        "schema/hbq_judge_response.schema.json": "49c7d824ba5dd957e67968ba3ae6ceb8a7ed9434dfb0dfc654836a76613c7854",
        "src/hbqrs/cli.py": "3e7eb62d0dbcd92b3eaeba69a24177a3c34cc1048d4d34a2d077ab4d2cb44f45",
        "src/hbqrs/runner.py": "af97b27de7cf8aba63435489e83eb09307c45a0de3b6ce47ebdd847898b1a9f8",
    },
    "successor_files": {
        "run.py": "73f74b717e2db6da9cf60d65fd58ec9923b2decc9a2a63935e5d9360dac14bf5",
        "study-contract.json": "235ef070ed0689d44843bd39a093324046448e3ce58910e67522a61680f909dc",
        "study.py": "960ee843f9fbde0b32756872409665fbc65a930f3699c51f07c24782ee084b43",
    },
}
HISTORICAL_RUNTIME_BLOBS = {
    "prompts/judge/JUDGE_PREFIX.md": "7f07f76fb339a8f6b86cbeb4ce8ba9220e2e2a5e",
    "prompts/judge/BINARY_EVALUATION_PROMPT.md": "d2662edfccc115c6d0c4d97af82a10c9e926b853",
    "schema/hbq_judge_response.schema.json": "1034a35dcd6c30a75101f369627d60e155d65c2c",
    "registry/all_modules.json": "d94af34c80cf32b4d5a380167e66e2af39f29ad7",
    "registry/question_index.jsonl": "4ab3b7e11fe2e150cc0defafc22a29929cf5799c",
    "bundles/all_bundles.json": "3d4f8c0d2dcc7020111dbdaf0e40a9fe483bc2a4",
    "src/hbqrs/runner.py": "9fe6cedd4dc63ba7eb618e906093dff98436a835",
    "src/hbqrs/cli.py": "b4bece11db82a81d517d52f8ad21ef7ef824be0f",
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=REPOSITORY, text=True, encoding="utf-8", capture_output=True, check=False)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "git binding lookup failed")
    return result.stdout.strip()


def _predecessor() -> Any:
    spec = importlib.util.spec_from_file_location("premise_scale_execution_predecessor", PREDECESSOR_ROOT / "study.py")
    if spec is None or spec.loader is None:
        raise ValueError("Cannot load frozen execution predecessor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _external_root(value: str | Path) -> Path:
    root = Path(value).resolve()
    try:
        root.relative_to(REPOSITORY.resolve())
    except ValueError:
        return root
    raise ValueError("private_root must be outside the CWR checkout")


def _write_summary(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical_json(value)
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"Refusing to overwrite prior repair output: {path.name}")
    if not path.exists():
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)


def contract() -> dict[str, Any]:
    return _load_json(ROOT / "study-contract.json")


def _predecessor_bindings() -> dict[str, str]:
    return {
        "README.md": "2d7b9a277300d47b7d8811ca10613e5edc18a808",
        "run.py": "8b5523455e2d59ce38fe38d68532c97efab6943c",
        "study-contract.json": "7207b6bd82227a9c34060989112fb06a0af2f549",
        "study.py": "a0d11a35908d6db2cf1ac0f19f441f9df310b951",
    }


def _historical_runtime_bindings() -> dict[str, Any]:
    for path, blob in HISTORICAL_RUNTIME_BLOBS.items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:{path}") != blob:
            raise ValueError("Historical execution runtime blob drifted")
    return HISTORICAL_RUNTIME_BINDINGS


def validate_package() -> dict[str, Any]:
    value = contract()
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "status": "frozen_provider_free_settlement_repair",
        "predecessor": {"commit": PREDECESSOR_COMMIT, "tree": PREDECESSOR_TREE, "files": _predecessor_bindings()},
        "provider_execution": "forbidden",
        "public_result_policy": "aggregate_only",
        "promotion": "none",
    }
    if any(value.get(key) != item for key, item in expected.items()):
        raise ValueError("Settlement-repair contract identity drifted")
    if value.get("prompt_reconciliation") != {"rule": "checkpoint CRLF may be canonicalized to LF only; lone CR and every other byte difference fail", "slots": SLOTS, "required_newline_only_slots": SLOTS}:
        raise ValueError("Settlement-repair comparator contract drifted")
    if value.get("historical_runtime_git_blobs") != HISTORICAL_RUNTIME_BLOBS:
        raise ValueError("Settlement-repair historical runtime blob contract drifted")
    if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-premise-scale-ownership-v1-execution-v1") != PREDECESSOR_TREE:
        raise ValueError("Execution predecessor tree is unavailable")
    for path, blob in _predecessor_bindings().items():
        if _git("rev-parse", f"{PREDECESSOR_COMMIT}:evaluation-results/hbq-premise-scale-ownership-v1-execution-v1/{path}") != blob:
            raise ValueError("Execution predecessor file binding drifted")
        if _git("hash-object", str(PREDECESSOR_ROOT / path)) != blob:
            raise ValueError("Current execution predecessor bytes differ from pinned source")
    predecessor = _predecessor()
    predecessor.validate_package()
    return {"study_id": STUDY_ID, "slots": SLOTS, "provider_calls": 0, "repair": "crlf_to_lf_only"}


def _canonicalize_checkpoint_crlf(value: bytes) -> bytes:
    output = bytearray()
    position = 0
    while position < len(value):
        current = value[position]
        if current == 13:
            if position + 1 >= len(value) or value[position + 1] != 10:
                raise ValueError("Prompt contains lone CR")
            output.append(10)
            position += 2
            continue
        output.append(current)
        position += 1
    return bytes(output)


def _verify_checkpoint_prompt(run_dir: Path, prompt_path: Path) -> dict[str, str]:
    checkpoint = run_dir / "responses" / "batch-0001.prompt.txt.gz"
    try:
        checkpoint_bytes = gzip.decompress(checkpoint.read_bytes())
    except (OSError, EOFError) as exc:
        raise ValueError("Checkpoint prompt is unavailable or malformed") from exc
    rendered = prompt_path.read_bytes()
    if b"\r" in rendered:
        raise ValueError("Rendered prompt must contain LF only")
    canonical_checkpoint = _canonicalize_checkpoint_crlf(checkpoint_bytes)
    if checkpoint_bytes == rendered:
        raise ValueError("Expected newline-only checkpoint difference is absent")
    if canonical_checkpoint != rendered:
        raise ValueError("Checkpoint prompt differs beyond CRLF-to-LF normalization")
    checkpoint_record = _load_json(run_dir / "responses" / "batch-0001.json")
    raw_sha256 = sha256_bytes(checkpoint_bytes)
    if any(checkpoint_record.get(key) != raw_sha256 for key in ("prompt_sha256", "base_prompt_sha256", "effective_prompt_sha256")):
        raise ValueError("Checkpoint prompt metadata does not bind the raw prompt")
    return {
        "rendered_prompt_sha256": sha256_bytes(rendered),
        "checkpoint_prompt_sha256": raw_sha256,
        "canonical_rendered_prompt_sha256": sha256_bytes(rendered),
        "canonical_checkpoint_prompt_sha256": sha256_bytes(canonical_checkpoint),
        "comparison": "newline_only_crlf_to_lf",
    }


def _private_bindings(root: Path) -> dict[str, str]:
    return {
        "runtime_schedule_sha256": sha256_file(root / "runtime-schedule.json"),
        "study_manifest_sha256": sha256_file(root / "study-manifest.json"),
        "dry_run_sha256": sha256_file(root / "dry-run.json"),
        "original_settlement_sha256": sha256_file(root / "settlement.json"),
        "original_public_aggregate_sha256": sha256_file(root / "public-aggregate.json"),
        "rendered_prompt_aggregate_sha256": _load_json(root / "runtime-schedule.json").get("rendered_prompt_aggregate_sha256"),
    }


def _historical_runtime_schedule(root: Path, predecessor: Any) -> list[dict[str, Any]]:
    manifest = _load_json(root / "study-manifest.json")
    if manifest.get("runtime_bindings") != _historical_runtime_bindings():
        raise ValueError("Historical execution runtime binding drifted")
    stored = _load_json(root / "runtime-schedule.json")
    expected_base = predecessor.build_schedule()
    slots = stored.get("slots")
    if not isinstance(slots, list) or len(slots) != SLOTS or len(expected_base) != SLOTS:
        raise ValueError("Historical execution schedule count drifted")
    runtime_slots: list[dict[str, Any]] = []
    rubric_sha256 = _historical_runtime_bindings()["cwr_files"]["registry/all_modules.json"]
    for base, stored_slot in zip(expected_base, slots):
        if not isinstance(stored_slot, Mapping) or {key: stored_slot.get(key) for key in base} != base:
            raise ValueError("Historical execution slot identity drifted")
        prompt = root / "rendered-prompts" / f"{base['slot_id']}.txt"
        prompt_sha256 = sha256_file(prompt)
        condition = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "batch_attempts": 3, "leaf_id": base["leaf_id"], "prompt_sha256": prompt_sha256, "rubric_sha256": rubric_sha256}
        expected = dict(base)
        expected["rendered_prompt_sha256"] = prompt_sha256
        expected["condition"] = condition
        expected["logical_sample_id"] = predecessor.logical_sample_id(study_id=predecessor.STUDY_ID, artifact_id=expected["artifact_id"], artifact_sha256=expected["artifact_sha256"], condition=condition, repetition=expected["repeat"], rubric_revision="1.2.0")
        if dict(stored_slot) != expected:
            raise ValueError("Historical execution runtime schedule drifted")
        runtime_slots.append(expected)
    aggregate = sha256_bytes(canonical_json({slot["slot_id"]: slot["rendered_prompt_sha256"] for slot in runtime_slots}))
    if stored.get("rendered_prompt_aggregate_sha256") != aggregate:
        raise ValueError("Historical execution prompt aggregate drifted")
    return runtime_slots


def _validate_private_root(root: Path, predecessor: Any) -> list[dict[str, Any]]:
    expected_bindings = contract().get("private_root_bindings")
    if _private_bindings(root) != expected_bindings:
        raise ValueError("Frozen private root binding drifted")
    original = _load_json(root / "settlement.json")
    expected_failure = "Checkpoint prompt content differs from frozen rendered prompt"
    failures = original.get("failures")
    if original.get("study_id") != predecessor.STUDY_ID or original.get("decision") != "INCOMPLETE" or original.get("completed_slots") != 0 or original.get("planned_slots") != SLOTS or not isinstance(failures, list) or len(failures) != SLOTS or any(item != {"slot_id": f"psoexec-v1-{index:03d}", "reason": expected_failure} for index, item in enumerate(failures, start=1)):
        raise ValueError("Original failed settlement is not the bounded comparator failure")
    schedule = _historical_runtime_schedule(root, predecessor)
    if len(schedule) != SLOTS:
        raise ValueError("Execution schedule count drifted")
    return schedule


def _verify_slot(predecessor: Any, root: Path, slot: Mapping[str, Any]) -> dict[str, Any]:
    original_comparator = predecessor._verify_checkpoint_prompt
    predecessor._verify_checkpoint_prompt = _verify_checkpoint_prompt
    try:
        return predecessor._verify_slot(root, slot)
    finally:
        predecessor._verify_checkpoint_prompt = original_comparator


def _incomplete(root: Path, completed: int, failures: list[dict[str, str]], bindings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = {
        "study_id": STUDY_ID,
        "decision": "INCOMPLETE",
        "completed_slots": completed,
        "planned_slots": SLOTS,
        "repair": "crlf_to_lf_only",
        "private_root_bindings": dict(bindings or {}),
        "failures": failures,
        "promotion": "none",
    }
    _write_summary(root / REPAIR_SETTLEMENT, value)
    _write_summary(root / REPAIR_PUBLIC, {"study_id": STUDY_ID, "decision": "INCOMPLETE", "publicable": False, "completed_slots": completed, "planned_slots": SLOTS, "promotion": "none"})
    return value


def _settlement(predecessor: Any, records: Sequence[Mapping[str, Any]], schedule: Sequence[Mapping[str, Any]], bindings: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cells: dict[tuple[str, str], list[bool]] = defaultdict(list)
    states: dict[str, Counter[str]] = {leaf: Counter() for leaf in predecessor.LEAVES}
    slot_map = {slot["slot_id"]: slot for slot in schedule}
    for row in records:
        slot = slot_map[row["slot_id"]]
        cells[(slot["case_id"], slot["leaf_id"])].append(bool(row["correct"]))
        states[slot["leaf_id"]][str(row["verdict"])] += 1
    cell_states = {(slot["case_id"], slot["leaf_id"]): slot["expected_verdict"] for slot in schedule}
    per_cell = {
        f"cell-{index:02d}": {"match": sum(values), "denominator": 3, "passed": sum(values) == 3, "expected_state": cell_states[key]}
        for index, (key, values) in enumerate(cells.items(), start=1)
    }
    overlap = predecessor._overlap(records, schedule)
    def accuracy(expected: set[str]) -> dict[str, int]:
        selected = [row for row in records if row["expected"] in expected]
        return {"correct": sum(bool(row["correct"]) for row in selected), "denominator": len(selected)}
    metrics = {"applicable_yes_no": accuracy({"YES", "NO"}), "cannot_assess": accuracy({"CANNOT_ASSESS"}), "not_applicable_unscored": accuracy({"NOT_APPLICABLE"}), "all_cell_diagnostic": accuracy(set(predecessor.VERDICTS))}
    opposed = [row for row in records if slot_map[row["slot_id"]]["pair_id"] == "mismatched-form" and slot_map[row["slot_id"]]["operation_active"] and row["expected"] in {"YES", "NO"}]
    canonical_counts = {leaf: {state: states[leaf][state] for state in sorted(predecessor.VERDICTS)} for leaf in predecessor.LEAVES}
    scored = [value for value in per_cell.values() if value["expected_state"] != "NOT_APPLICABLE"]
    controls = [value for value in per_cell.values() if value["expected_state"] == "NOT_APPLICABLE"]
    decision = "PASS_NO_CHANGE" if all(value["passed"] for value in scored) else "DIAGNOSTIC_FAIL"
    reconciliation = [row["prompt_commitment"] for row in records]
    if len(reconciliation) != SLOTS or any(row.get("comparison") != "newline_only_crlf_to_lf" for row in reconciliation):
        raise ValueError("Not every slot has the required newline-only reconciliation")
    settlement = {
        "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS,
        "repair": "crlf_to_lf_only", "private_root_bindings": dict(bindings), "prompt_reconciliation": reconciliation,
        "per_cell_three_of_three": per_cell, "canonical_four_state_counts": canonical_counts, "accuracy": metrics,
        "jointly_active_opposed_target_accuracy": {"correct": sum(bool(row["correct"]) for row in opposed), "denominator": len(opposed)},
        "cross_leaf_evidence_section_span_overlap": overlap,
        "clarification": predecessor._clarification_eligibility(records, schedule, overlap), "promotion": "none", "records": list(records),
    }
    public = {
        "study_id": STUDY_ID, "decision": decision, "completed_slots": SLOTS, "planned_slots": SLOTS,
        "scored_cells": {"passed": sum(value["passed"] for value in scored), "total": len(scored)},
        "not_applicable_diagnostic_cells": {"matched": sum(value["passed"] for value in controls), "total": len(controls)},
        "canonical_four_state_counts": canonical_counts, "accuracy": metrics, "promotion": "none",
    }
    return settlement, public


def settle(private_root: str | Path) -> dict[str, Any]:
    validate_package()
    root = _external_root(private_root)
    predecessor = _predecessor()
    try:
        bindings = _private_bindings(root)
        schedule = _validate_private_root(root, predecessor)
    except (OSError, ValueError) as exc:
        return _incomplete(root, 0, [{"slot_id": "schedule", "reason": str(exc)}])
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for slot in schedule:
        try:
            record = _verify_slot(predecessor, root, slot)
            if record.get("slot_id") != slot["slot_id"] or record.get("verdict") not in predecessor.VERDICTS:
                raise ValueError("Verifier slot identity or four-state verdict malformed")
            records.append(record)
        except (OSError, ValueError, predecessor.runner.HBQError) as exc:
            failures.append({"slot_id": str(slot["slot_id"]), "reason": str(exc)})
    if failures or len(records) != SLOTS or len({row["slot_id"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), failures or [{"slot_id": "identity", "reason": "Duplicate logical slot"}], bindings)
    if len({row["session_id_sha256"] for row in records}) != SLOTS or len({row["checkpoint_chain_head_sha256"] for row in records}) != SLOTS:
        return _incomplete(root, len(records), [{"slot_id": "identity", "reason": "Session or checkpoint identity repeated"}], bindings)
    settlement, public = _settlement(predecessor, records, schedule, bindings)
    _write_summary(root / REPAIR_SETTLEMENT, settlement)
    _write_summary(root / REPAIR_PUBLIC, public)
    return settlement


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify")
    settle_parser = commands.add_parser("settle")
    settle_parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    result = validate_package() if args.command == "verify" else settle(args.private_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
