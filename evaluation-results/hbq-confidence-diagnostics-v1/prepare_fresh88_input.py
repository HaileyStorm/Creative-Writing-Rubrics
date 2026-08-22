"""Build a sealed, prose-free Fresh88/Grok confidence input from verified private artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from study import FRESH_DIMENSIONS, binding, canonical


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def rows(path: Path) -> list[dict[str, Any]]:
    value = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("Fresh88 public rows must be JSON objects")
    return value


def verify_primary(output: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    summary_path, items_path, manifest_path = (output / name for name in ("summary.json", "items.jsonl", "manifest.json"))
    summary, items, manifest = read(summary_path), rows(items_path), read(manifest_path)
    if manifest.get("format_version") != 1 or manifest.get("study_id") != "hbq-human-alignment-v3-fresh88-analysis-v1" or manifest.get("files") != {"summary.json": binding(summary_path), "items.jsonl": binding(items_path)}:
        raise ValueError("Fresh88 primary manifest does not bind its public summary and rows")
    if summary.get("study_id") != manifest["study_id"] or summary.get("item_count") != 88 or summary.get("primary_generated_only", {}).get("item_count") != 80 or not isinstance(summary.get("mapping_sets"), Mapping) or set(summary["mapping_sets"]) != set(FRESH_DIMENSIONS):
        raise ValueError("Fresh88 primary output lacks the frozen 80/88 selection or dimension mapping")
    if len(items) != 88 or len({item.get("item_id") for item in items}) != 88 or sum(item.get("source_model") != "Human" for item in items) != 80:
        raise ValueError("Fresh88 public rows do not preserve the exact frozen item set")
    return summary, items, manifest


def questions(score: Mapping[str, Any]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    def visit(value: Any, section: str | None = None) -> None:
        if isinstance(value, Mapping):
            if {"question_id", "verdict", "weight", "confidence"} <= set(value):
                item_id, verdict = value["question_id"], value["verdict"]
                if not isinstance(item_id, str) or verdict not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} or item_id in found:
                    raise ValueError("Private score question identity is malformed")
                weight, confidence = value["weight"], value["confidence"]
                if isinstance(weight, bool) or not isinstance(weight, (int, float)) or isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
                    raise ValueError("Private score question metadata is malformed")
                if section not in {"hard_gate", "domain", "penalty", "supplemental"}:
                    raise ValueError("Private score question has no authoritative score-section ownership")
                found[item_id] = {"question_id": item_id, "verdict": verdict, "confidence": float(confidence), "effective_weight": float(weight), "role": section}
            for key, child in value.items():
                visit(child, {"hard_gates": "hard_gate", "domains": "domain", "penalties": "penalty", "supplemental": "supplemental"}.get(key, section))
        elif isinstance(value, list):
            for child in value:
                visit(child, section)
    visit(score)
    return list(found.values())


def ordered_questions(score: Mapping[str, Any], configured_ids: Any) -> list[dict[str, Any]]:
    found = {row["question_id"]: row for row in questions(score)}
    if not isinstance(configured_ids, list) or any(not isinstance(item, str) for item in configured_ids):
        raise ValueError("Private run configuration lacks ordered question IDs")
    ordered = [item for item in configured_ids if item in found]
    if len(ordered) != len(found) or set(ordered) != set(found):
        raise ValueError("Private score questions are not an ordered subset of its sealed run configuration")
    return [found[item] for item in ordered]


def mapping(rows: list[dict[str, Any]], mappings: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    labels = {row["question_id"]: row for row in rows}
    scores, confidences = {}, {}
    for dimension, ids in mappings.items():
        selected = [labels[item] for item in ids if item in labels]
        assessed = [item for item in selected if item["verdict"] in {"YES", "NO"}]
        if not assessed:
            scores[dimension] = None
            confidences[dimension] = None
            continue
        scores[dimension] = sum(item["verdict"] == "YES" for item in assessed) / len(assessed)
        total = sum(item["effective_weight"] for item in assessed)
        confidences[dimension] = sum(item["confidence"] * item["effective_weight"] for item in assessed) / total if total else 0.0
    return scores, confidences


def fingerprint(configuration: Mapping[str, Any], *, runtime_sha256: str, corpus_sha256: str, selection_sha256: str, reasoning_attestation: str) -> dict[str, str]:
    schema = configuration.get("response_schema")
    prompts = configuration.get("prompts")
    if not isinstance(schema, Mapping) or not isinstance(prompts, list) or len(prompts) != 1 or not isinstance(prompts[0], Mapping):
        raise ValueError("Private run configuration lacks exact prompt/schema bindings")
    values = {"provider": configuration.get("provider"), "model": configuration.get("model"), "requested_reasoning_effort": configuration.get("reasoning") or "unattested", "reasoning_attestation": reasoning_attestation, "prompt_sha256": prompts[0].get("sha256"), "schema_sha256": schema.get("sha256"), "compiled_bundle_sha256": configuration.get("compiled_bundle_sha256"), "questions_sha256": configuration.get("questions_sha256"), "runtime_sha256": runtime_sha256, "corpus_sha256": corpus_sha256, "selection_sha256": selection_sha256}
    if any(not isinstance(value, str) or not value for value in values.values()):
        raise ValueError("Private run configuration lacks a complete model fingerprint")
    return values


def private_model(root: Path, items: list[dict[str, Any]], mappings: Mapping[str, Any], *, score_name: str, run_path: str, runtime_sha256: str, corpus_sha256: str, selection_sha256: str, authority: dict[str, dict[str, Any]], reasoning_attestation: str, parent_mapping: bool, ordered_item_ids: list[str]) -> dict[str, Any]:
    records, first, task_contracts, accepted_artifacts = [], None, [], []
    expected = {str(item["item_id"]) for item in items}
    actual = {path.name for path in root.iterdir() if path.is_dir()}
    if actual != expected:
        raise ValueError("Private run root does not contain the exact Fresh88 item set")
    public_by_id = {str(item["item_id"]): item for item in items}
    if len(ordered_item_ids) != 88 or len(set(ordered_item_ids)) != 88 or set(ordered_item_ids) != set(public_by_id):
        raise ValueError("Verifier receipt does not preserve the exact ordered 88-item projection")
    for item_id in ordered_item_ids:
        public = public_by_id[item_id]
        folder = root / item_id / run_path
        run_path_json, score_path = folder / "run.json", folder / score_name
        verdict_path = folder / "verdicts.jsonl"
        if not run_path_json.is_file() or not score_path.is_file() or folder.is_symlink():
            raise ValueError("Private Fresh88 run is incomplete or aliased")
        run, score = read(run_path_json), read(score_path)
        if not verdict_path.is_file():
            raise ValueError("Private run lacks accepted verdict bytes")
        accepted_artifacts.append({"item_id": item_id, "run": binding(run_path_json), "score": binding(score_path), "verdicts": binding(verdict_path)})
        configuration = run.get("configuration")
        if not isinstance(configuration, Mapping) or configuration.get("artifact_id") != item_id:
            raise ValueError("Private run configuration does not bind its item")
        task = configuration.get("task_contract")
        if not isinstance(task, Mapping) or not isinstance(task.get("sha256"), str):
            raise ValueError("Private run configuration lacks a task-contract binding")
        task_contracts.append({"item_id": item_id, "task_contract_sha256": task["sha256"]})
        leaf_rows = ordered_questions(score, configuration.get("question_ids"))
        raw_rows = [json.loads(line) for line in verdict_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        raw_by_id = {row.get("question_id"): row for row in raw_rows if isinstance(row, Mapping)}
        if len(raw_by_id) != len(raw_rows) or any(not isinstance(item_id, str) or not isinstance(row.get("confidence"), (int, float)) or row.get("verdict") not in {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"} for item_id, row in raw_by_id.items()):
            raise ValueError("Private verdict metadata is malformed or duplicated")
        known = {row["question_id"] for row in leaf_rows}
        mapping_rows = [*leaf_rows, *({"question_id": item_id, "verdict": row["verdict"], "confidence": float(row["confidence"]), "effective_weight": 1.0, "role": "unweighted_mapping_only"} for item_id, row in raw_by_id.items() if item_id not in known)]
        current = fingerprint(configuration, runtime_sha256=runtime_sha256, corpus_sha256=corpus_sha256, selection_sha256=selection_sha256, reasoning_attestation=reasoning_attestation)
        if first is None:
            first = current
        elif current != first:
            raise ValueError("A confidence input may not pool different model fingerprints")
        derived_scores, mapped_confidences = mapping(mapping_rows, mappings)
        mapped_scores = {name: public["hbq_mapping"][name]["score"] for name in FRESH_DIMENSIONS} if parent_mapping else derived_scores
        if parent_mapping:
            for name in FRESH_DIMENSIONS:
                if mapped_scores[name] is None:
                    mapped_confidences[name] = None
        final = score.get("final_score")
        observed = final.get("observed") if isinstance(final, Mapping) else None
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            raise ValueError("Private score lacks observed HBQ result")
        records.append({"item_id": item_id, "source_model": public["source_model"], "score": float(observed), "hanna_overall": float(public["human_overall"]), "hanna_dimensions": {name: float(public["human_means"][name]) for name in FRESH_DIMENSIONS}, "mapped_scores": mapped_scores, "mapped_confidences": mapped_confidences, "verdicts": [{key: row[key] for key in ("verdict", "confidence", "effective_weight", "role")} for row in leaf_rows]})
    if first is None:
        raise ValueError("No private runs found")
    selection_digest = hashlib.sha256(canonical([{"item_id": item["item_id"], "source_model": item["source_model"], "hanna_overall": item["hanna_overall"], "hanna_dimensions": item["hanna_dimensions"]} for item in records])).hexdigest()
    configuration = read(root / records[0]["item_id"] / run_path / "run.json")["configuration"]
    accepted_digest = hashlib.sha256(canonical(accepted_artifacts)).hexdigest()
    first["accepted_artifacts_sha256"] = accepted_digest
    condition = {"phase": "development", "arm_id": "hbq_short_story_batch32", "bundle_id": str(configuration["bundle_id"]), "batch_size": int(configuration["batch_size"]), "polarity": "as_frozen", "task_contract_sha256": hashlib.sha256(canonical(task_contracts)).hexdigest(), "weight_profile_sha256": hashlib.sha256(canonical(configuration["weight_profile"])).hexdigest(), "accepted_artifacts_sha256": accepted_digest}
    return {"model_fingerprint": first, "condition": condition, "authority": {**authority, "accepted_artifacts": {"item_count": len(accepted_artifacts), "sha256": accepted_digest}}, "selection_digest": selection_digest, "records": records}


def write(output: Path, payload: dict[str, Any]) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite a sealed confidence input")
    output.mkdir(parents=True)
    input_path = output / "confidence-input.json"
    input_path.write_bytes(canonical(payload) + b"\n")
    manifest = {"format_version": 1, "kind": payload["kind"], "files": {"confidence-input.json": binding(input_path)}}
    (output / "manifest.json").write_bytes(canonical(manifest) + b"\n")


def require_projection_digest(model: Mapping[str, Any], projection: Mapping[str, Any]) -> None:
    digest = model.get("condition", {}).get("accepted_artifacts_sha256") if isinstance(model.get("condition"), Mapping) else None
    if projection.get("item_count") != 88 or digest != projection.get("sha256"):
        raise ValueError("Consumed accepted artifacts do not match the verifier replay projection")


def replay_receipt(directory: Path, kind: str) -> dict[str, Any]:
    receipt_path, manifest_path = directory / "receipt.json", directory / "manifest.json"
    receipt, manifest = read(receipt_path), read(manifest_path)
    if receipt.get("format_version") != 1 or receipt.get("kind") != kind or manifest != {"format_version": 1, "kind": kind, "files": {"receipt.json": binding(receipt_path)}}:
        raise ValueError("Verifier replay receipt is not independently sealed")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a sealed private-to-aggregate Fresh88/Grok confidence input.")
    parser.add_argument("--fresh88-primary-output", required=True, type=Path)
    parser.add_argument("--fresh88-artifact-root", required=True, type=Path)
    parser.add_argument("--fresh88-verifier-replay-dir", required=True, type=Path)
    parser.add_argument("--grok-work-root", required=True, type=Path)
    parser.add_argument("--grok-verifier-manifest", required=True, type=Path)
    parser.add_argument("--grok-verifier-replay-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    summary, items, primary_manifest = verify_primary(args.fresh88_primary_output.resolve())
    grok_manifest = read(args.grok_verifier_manifest.resolve())
    corpus = grok_manifest.get("corpus")
    if grok_manifest.get("verifier_id") != "hbq-human-alignment-supplemental-providers-verifier-v2" or not isinstance(corpus, Mapping) or corpus.get("provider_id") != "grok_4_6_high" or corpus.get("phase") != "development" or corpus.get("run_count") != 88 or corpus.get("checkpoint_count") != 528:
        raise ValueError("Grok verifier manifest does not bind the completed 88-story corpus")
    selection_sha256 = primary_manifest["files"]["items.jsonl"]["sha256"]
    fresh_runtime = summary["evidence_binding"]["historical_runtime_source_manifest_sha256"]
    fresh_corpus = summary["evidence_binding"]["verifier_matrix_sha256"]
    fresh_replay_dir = args.fresh88_verifier_replay_dir.resolve()
    fresh_replay = replay_receipt(fresh_replay_dir, "fresh88_historical_verifier_replay")
    if fresh_replay.get("result", {}).get("matrix_sha256") != fresh_corpus or fresh_replay.get("result", {}).get("record_count") != 88:
        raise ValueError("Fresh88 verifier replay does not bind the primary analysis matrix")
    parent_contract = read(Path(__file__).resolve().parent.parent / "hbq-human-alignment-v3-fresh88-analysis-v1" / "study-contract.json")
    expected_runtime = parent_contract.get("analysis_sources", {}).get("analyze.py")
    if fresh_replay.get("result", {}).get("analysis_runtime") != {"bytes": expected_runtime.get("bytes"), "sha256": expected_runtime.get("sha256")}:
        raise ValueError("Fresh88 verifier replay runtime does not match the parent analysis-source contract")
    if fresh_replay.get("inputs", {}).get("artifact_root_marker") != binding(args.fresh88_artifact_root.resolve() / "runs" / "hanna-10" / "run.json"):
        raise ValueError("Fresh88 verifier replay was sealed against a different consumed artifact root")
    fresh_projection = fresh_replay.get("result", {}).get("accepted_projection")
    if not isinstance(fresh_projection, Mapping) or fresh_projection.get("item_count") != 88 or not isinstance(fresh_projection.get("sha256"), str) or not isinstance(fresh_projection.get("item_ids"), list):
        raise ValueError("Fresh88 verifier replay lacks its canonical accepted-artifact projection")
    fresh_authority = {"fresh88_primary_summary": binding(args.fresh88_primary_output.resolve() / "summary.json"), "fresh88_primary_items": binding(args.fresh88_primary_output.resolve() / "items.jsonl"), "fresh88_primary_manifest": binding(args.fresh88_primary_output.resolve() / "manifest.json"), "fresh88_verifier_replay_receipt": binding(fresh_replay_dir / "receipt.json")}
    grok_runtime = grok_manifest["verifier_runtime"]["analyzer"]["sha256"]
    grok_corpus = corpus["root_commitment"]["sha256"]
    grok_replay_dir = args.grok_verifier_replay_dir.resolve()
    grok_replay = replay_receipt(grok_replay_dir, "grok_verifier_v2_replay")
    if grok_replay.get("result", {}).get("root_sha256") != grok_corpus or grok_replay.get("result", {}).get("run_count") != 88 or grok_replay.get("result", {}).get("checkpoint_count") != 528:
        raise ValueError("Grok verifier-v2 replay does not bind the completed corpus")
    if grok_replay.get("inputs", {}).get("raw_frozen_contract") != binding(args.grok_work_root.resolve() / "frozen-provider-contract.json"):
        raise ValueError("Grok verifier replay was sealed against a different consumed raw root")
    grok_projection = grok_replay.get("result", {}).get("accepted_projection")
    if not isinstance(grok_projection, Mapping) or grok_projection.get("item_count") != 88 or not isinstance(grok_projection.get("sha256"), str) or not isinstance(grok_projection.get("item_ids"), list):
        raise ValueError("Grok verifier replay lacks its canonical accepted-artifact projection")
    grok_authority = {**fresh_authority, "grok_verifier_manifest": binding(args.grok_verifier_manifest.resolve()), "grok_verifier_replay_receipt": binding(grok_replay_dir / "receipt.json")}
    fresh_root = args.fresh88_artifact_root.resolve() / "runs"
    grok_root = args.grok_work_root.resolve() / "runs" / "grok_4_6_high" / "development"
    fresh = private_model(fresh_root, items, summary["mapping_sets"], score_name="score.v2.json", run_path=".", runtime_sha256=fresh_runtime, corpus_sha256=fresh_corpus, selection_sha256=selection_sha256, authority=fresh_authority, reasoning_attestation="provider_attested", parent_mapping=True, ordered_item_ids=fresh_projection["item_ids"])
    grok = private_model(grok_root, items, summary["mapping_sets"], score_name="score.json", run_path="run-01", runtime_sha256=grok_runtime, corpus_sha256=grok_corpus, selection_sha256=selection_sha256, authority=grok_authority, reasoning_attestation="not_reported_by_grok_build_cli", parent_mapping=False, ordered_item_ids=grok_projection["item_ids"])
    require_projection_digest(fresh, fresh_projection)
    require_projection_digest(grok, grok_projection)
    payload = {"format_version": 1, "kind": "fresh88_confidence_evidence", "models": [fresh, grok]}
    write(args.output_dir.resolve(), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
