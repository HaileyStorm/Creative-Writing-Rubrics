"""Build sealed repeatability confidence metadata only from a complete frozen HBQ arm."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from prepare_fresh88_input import fingerprint, ordered_questions
from study import binding, canonical


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write(output: Path, payload: dict[str, Any]) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite a sealed confidence input")
    output.mkdir(parents=True)
    source = output / "confidence-input.json"
    source.write_bytes(canonical(payload) + b"\n")
    (output / "manifest.json").write_bytes(canonical({"format_version": 1, "kind": payload["kind"], "files": {"confidence-input.json": binding(source)}}) + b"\n")


def role(question_id: str) -> str:
    if question_id.startswith("penalty."):
        return "penalty"
    if question_id.startswith("core.task_and_brief_fidelity."):
        return "hard_gate"
    return "domain"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract complete, sealed HBQ repeats without exposing prose or responses.")
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    frozen_path = work / "frozen-run-contract.json"
    frozen = read(frozen_path)
    contract = frozen.get("contract")
    samples = frozen.get("samples")
    if frozen.get("study_id") != "hbq-multisample-repeatability-v1" or not isinstance(contract, Mapping) or contract.get("repetitions") != 5 or not isinstance(samples, list) or len(samples) != 11:
        raise ValueError("Repeat extractor requires the authoritative complete 11-story, five-repeat frozen contract")
    arm = next((item for item in contract.get("arms", []) if isinstance(item, Mapping) and item.get("arm_id") == "hbq_short_story_batch32" and item.get("kind") == "hbq"), None)
    if arm is None:
        raise ValueError("Frozen repeat contract lacks the HBQ arm")
    item_ids = [item.get("item_id") for item in samples]
    if any(not isinstance(item, str) or not item for item in item_ids) or len(set(item_ids)) != 11:
        raise ValueError("Frozen repeat item selection is malformed")
    runs_root = work / "runs"
    if not runs_root.is_dir():
        raise ValueError("Repeat work has no completed run root")
    records: list[dict[str, Any]] = []
    first_fingerprint = None
    for item_id in item_ids:
        columns: dict[str, list[dict[str, Any]]] = {}
        for repetition in range(1, 6):
            folder = runs_root / item_id / "hbq_short_story_batch32" / f"run-{repetition:02d}"
            run_path, score_path = folder / "run.json", folder / "score.json"
            if not run_path.is_file() or not score_path.is_file() or folder.is_symlink():
                raise ValueError("Repeat extractor refuses an incomplete or aliased frozen run")
            run, score = read(run_path), read(score_path)
            configuration = run.get("configuration")
            if not isinstance(configuration, Mapping) or configuration.get("artifact_id") != item_id:
                raise ValueError("Repeat run configuration does not bind its frozen item")
            current = fingerprint(configuration, runtime_sha256=str(frozen.get("runtime_sha256", "")), corpus_sha256=str(frozen.get("schedule_sha256", "")), selection_sha256=str(frozen.get("schedule_sha256", "")), reasoning_attestation="provider_attested")
            if first_fingerprint is None:
                first_fingerprint = current
            elif current != first_fingerprint:
                raise ValueError("Repeat extractor refuses to pool different model fingerprints")
            leaves = ordered_questions(score, configuration.get("question_ids"))
            for leaf in leaves:
                columns.setdefault(leaf["question_id"], []).append({"verdict": leaf["verdict"], "confidence": leaf["confidence"], "effective_weight": leaf["effective_weight"], "role": role(leaf["question_id"])})
        if len(columns) != arm.get("question_count") or any(len(values) != 5 for values in columns.values()):
            raise ValueError("Repeat extractor requires a complete rectangular leaf matrix")
        for question_id, values in sorted(columns.items()):
            if len({value["effective_weight"] for value in values}) != 1 or len({value["role"] for value in values}) != 1:
                raise ValueError("Repeat leaf metadata drifted across repetitions")
            records.append({"item_id": item_id, "question_id": question_id, "role": values[0]["role"], "effective_weight": values[0]["effective_weight"], "responses": [{"verdict": value["verdict"], "confidence": value["confidence"]} for value in values]})
    if first_fingerprint is None:
        raise ValueError("Repeat extractor found no verified model configuration")
    authority = {"frozen_run_contract": binding(frozen_path)}
    configuration = read(runs_root / item_ids[0] / "hbq_short_story_batch32" / "run-01" / "run.json")["configuration"]
    condition = {"phase": "repeatability", "arm_id": "hbq_short_story_batch32", "bundle_id": str(configuration["bundle_id"]), "batch_size": int(configuration["batch_size"]), "polarity": "as_frozen", "task_contract_sha256": str(configuration["task_contract"]["sha256"]), "weight_profile_sha256": hashlib.sha256(canonical(configuration["weight_profile"])).hexdigest()}
    payload = {"format_version": 1, "kind": "repeatability_confidence_evidence", "models": [{"model_fingerprint": first_fingerprint, "condition": condition, "authority": authority, "records": records}]}
    write(args.output_dir.resolve(), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
