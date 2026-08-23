"""Compose a strictly verified, partial repeatability-confidence input offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from prepare_fresh88_input import ordered_questions
from study import binding, canonical


PARTIAL_KIND = "repeatability_confidence_evidence_partial_v1"
OBSERVED_SCORE_LEAF_COUNT = 162


def read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing {label}")
    return value


def _configuration(run: Mapping[str, Any], item_id: str) -> Mapping[str, Any]:
    configuration = run.get("configuration")
    if not isinstance(configuration, Mapping) or configuration.get("artifact_id") != item_id:
        raise ValueError("Run configuration does not bind its expected story")
    return configuration


def _signature(configuration: Mapping[str, Any], *, runtime_sha256: str) -> tuple[dict[str, str], dict[str, str | int]]:
    prompts = configuration.get("prompts")
    schema = configuration.get("response_schema")
    task = configuration.get("task_contract")
    if not isinstance(prompts, list) or not prompts or not all(isinstance(prompt, Mapping) for prompt in prompts):
        raise ValueError("Run configuration lacks a prompt binding")
    if not isinstance(schema, Mapping) or not isinstance(task, Mapping):
        raise ValueError("Run configuration lacks schema or task bindings")
    prompt_rows = [{"name": _string(prompt.get("name"), "prompt name"), "sha256": _string(prompt.get("sha256"), "prompt hash")} for prompt in prompts]
    model = {
        "provider": _string(configuration.get("provider"), "provider"),
        "model": _string(configuration.get("model"), "model"),
        "requested_reasoning_effort": _string(configuration.get("reasoning"), "reasoning"),
        "reasoning_attestation": "provider_attested",
        "prompt_sha256": sha(prompt_rows),
        "schema_sha256": _string(schema.get("sha256"), "schema hash"),
        "compiled_bundle_sha256": _string(configuration.get("compiled_bundle_sha256"), "compiled bundle hash"),
        "questions_sha256": _string(configuration.get("questions_sha256"), "questions hash"),
        "runtime_sha256": _string(runtime_sha256, "frozen runtime hash"),
        "corpus_sha256": sha({"bundle_id": configuration.get("bundle_id"), "bundle_version": configuration.get("bundle_version")}),
        "selection_sha256": sha({"task_contract_sha256": _string(task.get("sha256"), "task contract hash"), "artifact_sha256": _string((configuration.get("artifact") or {}).get("sha256"), "artifact hash")}),
    }
    condition: dict[str, str | int] = {
        "phase": "repeatability_partial_exploratory",
        "arm_id": "hbq_short_story_batch32",
        "bundle_id": _string(configuration.get("bundle_id"), "bundle id"),
        "batch_size": configuration.get("batch_size"),
        "polarity": "as_frozen",
        "task_contract_sha256": _string(task.get("sha256"), "task contract hash"),
        "weight_profile_sha256": sha(configuration.get("weight_profile")),
    }
    if isinstance(condition["batch_size"], bool) or not isinstance(condition["batch_size"], int) or condition["batch_size"] < 1:
        raise ValueError("Invalid batch size")
    return model, condition


def _run_folder(root: Path, item_id: str, repetition: int) -> Path:
    folder = root / "runs" / item_id / "hbq_short_story_batch32" / f"run-{repetition:02d}"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Repeat run is missing or aliased")
    return folder


def _available_folder(root: Path, item_id: str, repetition: int) -> Path | None:
    folder = root / "runs" / item_id / "hbq_short_story_batch32" / f"run-{repetition:02d}"
    if folder.is_symlink():
        raise ValueError("Candidate repeat run is aliased")
    if not folder.is_dir() or not (folder / "run.json").is_file() or not (folder / "score.json").is_file():
        return None
    return folder


def _scheduled_items(frozen: Mapping[str, Any]) -> list[str]:
    samples = frozen.get("samples")
    if not isinstance(samples, list) or len(samples) != 11:
        raise ValueError("Frozen authority does not contain its exact 11-story schedule")
    items = [sample.get("item_id") if isinstance(sample, Mapping) else None for sample in samples]
    if any(not isinstance(item, str) or not item for item in items) or len(set(items)) != len(items):
        raise ValueError("Frozen authority has malformed item identities")
    return items


def _candidate_sources(item_id: str, roots: Mapping[str, Path]) -> tuple[tuple[str, int], ...]:
    selected: list[tuple[str, int]] = []
    for repetition in range(1, 6):
        candidates = [source for source in ("original", "successor") if _available_folder(roots[source], item_id, repetition) is not None]
        if item_id == "hanna-52" and repetition == 5 and _available_folder(roots["recovery"], item_id, repetition) is not None:
            candidates.append("recovery")
        if not candidates:
            raise ValueError("missing_repetition")
        if len(candidates) != 1:
            raise ValueError("duplicate_repetition")
        selected.append((candidates[0], repetition))
    return tuple(selected)


def _shared_condition_key(model: Mapping[str, Any]) -> str:
    fingerprint = model["model_fingerprint"]
    condition = model["condition"]
    if not isinstance(fingerprint, Mapping) or not isinstance(condition, Mapping):
        raise ValueError("Candidate record lacks a model condition")
    return sha({
        "model_fingerprint": {key: value for key, value in fingerprint.items() if key != "selection_sha256"},
        "condition": {key: value for key, value in condition.items() if key != "task_contract_sha256"},
    })


def _scan_scheduled_stories(frozen: Mapping[str, Any], roots: Mapping[str, Path], authority: Mapping[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]], str]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    exclusions: list[dict[str, str]] = []
    for position, item_id in enumerate(_scheduled_items(frozen)):
        try:
            candidates.append((position, _story_records(item_id, _candidate_sources(item_id, roots), roots, authority, runtime_sha256=_string(frozen.get("runtime_sha256"), "frozen runtime hash"))))
        except ValueError as exc:
            message = str(exc)
            reason = message if message in {"missing_repetition", "duplicate_repetition"} else "condition_or_score_drift"
            exclusions.append({"item_id": item_id, "reason": reason})
    groups: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for position, model in candidates:
        groups.setdefault(_shared_condition_key(model), []).append((position, model))
    qualifying = [(key, rows) for key, rows in groups.items() if len(rows) >= 3]
    if not qualifying:
        raise ValueError("Partial repeatability evidence requires at least three stories sharing one full model/prompt/schema/runtime condition")
    winner, selected = sorted(qualifying, key=lambda pair: (-len(pair[1]), tuple(position for position, _ in pair[1]), pair[0]))[0]
    selected_positions = {position for position, _ in selected}
    for position, model in candidates:
        if position not in selected_positions:
            item_ids = {record["item_id"] for record in model["records"]}
            if len(item_ids) != 1:
                raise ValueError("Candidate story group identity is malformed")
            exclusions.append({"item_id": next(iter(item_ids)), "reason": "different_shared_condition"})
    return [model for _, model in selected], sorted(exclusions, key=lambda row: row["item_id"]), winner


def _story_records(item_id: str, run_sources: tuple[tuple[str, int], ...], roots: Mapping[str, Path], shared_authority: Mapping[str, dict[str, Any]], *, runtime_sha256: str) -> dict[str, Any]:
    columns: dict[str, list[dict[str, Any]]] = {}
    first_model: dict[str, str] | None = None
    first_condition: dict[str, str | int] | None = None
    accepted: list[dict[str, Any]] = []
    for source, repetition in run_sources:
        folder = _run_folder(roots[source], item_id, repetition)
        run_path, score_path = folder / "run.json", folder / "score.json"
        if not run_path.is_file() or not score_path.is_file():
            raise ValueError("Repeat run lacks accepted run or score bytes")
        run, score = read(run_path), read(score_path)
        configuration = _configuration(run, item_id)
        model, condition = _signature(configuration, runtime_sha256=runtime_sha256)
        if first_model is None:
            first_model, first_condition = model, condition
        elif model != first_model or condition != first_condition:
            raise ValueError(f"Repeat condition drifted within included story {item_id} at repetition {repetition}")
        leaves = ordered_questions(score, configuration.get("question_ids"))
        if len(leaves) != OBSERVED_SCORE_LEAF_COUNT:
            raise ValueError("Included repeat run lacks the frozen observed 162-leaf score shape")
        accepted.extend(({"repetition": repetition, "run": binding(run_path), "score": binding(score_path)} ,))
        for leaf in leaves:
            columns.setdefault(leaf["question_id"], []).append({"verdict": leaf["verdict"], "confidence": leaf["confidence"], "effective_weight": leaf["effective_weight"], "role": leaf["role"]})
    if first_model is None or first_condition is None or len(columns) != OBSERVED_SCORE_LEAF_COUNT or any(len(values) != 5 for values in columns.values()):
        raise ValueError("Included story must have exactly five rectangular observed-score repetitions")
    records = []
    for question_id, values in sorted(columns.items()):
        if len({value["effective_weight"] for value in values}) != 1 or len({value["role"] for value in values}) != 1:
            raise ValueError("Question metadata drifted across repetitions")
        records.append({"item_id": item_id, "question_id": question_id, "role": values[0]["role"], "effective_weight": values[0]["effective_weight"], "responses": [{"verdict": value["verdict"], "confidence": value["confidence"]} for value in values]})
    authority = dict(shared_authority)
    authority["accepted_artifacts"] = {"item_count": len(accepted) * 2, "sha256": sha(accepted)}
    return {"model_fingerprint": first_model, "condition": first_condition, "authority": authority, "records": records}


def _verify_lineage(original: Path, successor: Path, recovery: Path, settlement: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    frozen_path = original / "frozen-run-contract.json"
    predecessor_path, successor_contract_path = successor / "predecessor-binding.json", successor / "successor-execution-contract.json"
    frozen, predecessor, successor_contract = read(frozen_path), read(predecessor_path), read(successor_contract_path)
    if frozen.get("study_id") != "hbq-multisample-repeatability-v1" or frozen.get("contract", {}).get("repetitions") != 5 or not isinstance(frozen.get("samples"), list) or len(frozen["samples"]) != 11:
        raise ValueError("Original root is not the frozen 11-story, five-repeat authority")
    if predecessor.get("frozen_contract_sha256") != binding(frozen_path)["sha256"] or successor_contract.get("predecessor_binding_sha256") != sha(predecessor):
        raise ValueError("Successor lineage does not bind the original frozen authority")
    recovery_run = recovery / "runs" / "hanna-52" / "hbq_short_story_batch32" / "run-05" / "run.json"
    recovery_settlement = read(settlement)
    failed = recovery_settlement.get("failed_v4")
    if not isinstance(failed, Mapping) or recovery_settlement.get("completion_sha256") != binding(recovery_run)["sha256"] or failed.get("run_sha256") != binding(recovery_run)["sha256"]:
        raise ValueError("Recovery settlement does not bind its recovered run")
    successor_config = _configuration(read(_run_folder(successor, "hanna-52", 1) / "run.json"), "hanna-52")
    recovery_config = _configuration(read(recovery_run), "hanna-52")
    runtime_sha256 = _string(frozen.get("runtime_sha256"), "frozen runtime hash")
    successor_model, successor_condition = _signature(successor_config, runtime_sha256=runtime_sha256)
    recovery_model, recovery_condition = _signature(recovery_config, runtime_sha256=runtime_sha256)
    if successor_condition != recovery_condition or successor_model["prompt_sha256"] == recovery_model["prompt_sha256"]:
        raise ValueError("Expected hanna-52 prompt-condition drift is absent or malformed")
    return frozen, {
        "frozen_run_contract": binding(frozen_path),
        "successor_predecessor_binding": binding(predecessor_path),
        "successor_execution_contract": binding(successor_contract_path),
        "excluded_condition_drift_settlement": binding(settlement),
    }


def compose(original: Path, successor: Path, recovery: Path, settlement: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise ValueError("Refusing to overwrite a sealed partial repeatability input")
    roots = {"original": original.resolve(), "successor": successor.resolve(), "recovery": recovery.resolve()}
    frozen, authority = _verify_lineage(roots["original"], roots["successor"], roots["recovery"], settlement.resolve())
    models, exclusions, shared_condition = _scan_scheduled_stories(frozen, roots, authority)
    payload = {"format_version": 1, "kind": PARTIAL_KIND, "models": models, "partial_exclusions": exclusions, "partial_shared_condition_sha256": shared_condition}
    output.mkdir(parents=True)
    input_path = output / "confidence-input.json"
    input_path.write_bytes(canonical(payload) + b"\n")
    manifest = {"format_version": 1, "kind": PARTIAL_KIND, "files": {"confidence-input.json": binding(input_path)}}
    (output / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose a sealed, exploratory 3x5 repeatability confidence input without provider contact.")
    parser.add_argument("--original-work-dir", required=True, type=Path)
    parser.add_argument("--successor-work-dir", required=True, type=Path)
    parser.add_argument("--recovery-work-dir", required=True, type=Path)
    parser.add_argument("--recovery-settlement", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    compose(args.original_work_dir, args.successor_work_dir, args.recovery_work_dir, args.recovery_settlement, args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
