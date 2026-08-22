#!/usr/bin/env python3
"""Fail-closed offline verifier and prose-free publisher for Ox Alpha v2."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, NOUS_TRANSPORT_POLICY, _json_bytes, _load_checkpoints
from hbqrs.scoring_v2 import score_bundle as score_bundle_v2
from study import CONTRACT, _assert_fresh_at, canonical, fingerprint, immutable_json, input_paths, load_frozen, read_json, sha, static_ablation, strict_json


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _atomic_text(path: Path, text: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(text); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True); raise


def _legacy_receipt_validator() -> Any:
    root = Path(__file__).resolve().parent.parent / "hbq-human-alignment-supplemental-providers-ox-alpha-v1"
    study_spec = importlib.util.spec_from_file_location("ox_alpha_v2_legacy_study", root / "study.py")
    analyzer_spec = importlib.util.spec_from_file_location("ox_alpha_v2_legacy_analyzer", root / "analyze_pilot.py")
    if study_spec is None or study_spec.loader is None or analyzer_spec is None or analyzer_spec.loader is None:
        raise ValueError("Preserved v1 receipt validator is unavailable")
    legacy_study = importlib.util.module_from_spec(study_spec); study_spec.loader.exec_module(legacy_study)
    legacy_analyzer = importlib.util.module_from_spec(analyzer_spec)
    prior = sys.modules.get("study"); sys.modules["study"] = legacy_study
    try: analyzer_spec.loader.exec_module(legacy_analyzer)
    finally:
        if prior is None: sys.modules.pop("study", None)
        else: sys.modules["study"] = prior
    return legacy_analyzer


def _receipt(run: Path, checkpoint: Mapping[str, Any]) -> str:
    return _legacy_receipt_validator()._receipt(run, checkpoint)


def verify_run(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    run = work / "runs" / str(cell["cell_id"])
    manifest, score, score_v2 = read_json(run / "run.json"), read_json(run / "score.json"), read_json(run / "score.v2.json")
    config = manifest.get("configuration")
    if not isinstance(config, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(config)).hexdigest():
        raise ValueError("Ox v2 run manifest is malformed")
    artifact, prompt, task_path = input_paths(cell)
    expected = {"bundle_id": CONTRACT["questions"]["bundle_id"], "question_ids": cell["primary_question_ids"], "provider": "nous", "model": CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 32, "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "strict_ai": False, "allow_unattested_reasoning": True, "nous_transport_policy": NOUS_TRANSPORT_POLICY, "nous_model_policy": {"requested_model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "required_reasoning_effort": "max"}}
    if any(config.get(key) != value for key, value in expected.items()): raise ValueError("Ox v2 run configuration drifted")
    if _compact(config.get("artifact")) != cell["inputs"]["source.md"] or [_compact(item) for item in config.get("contexts", [])] != [cell["inputs"]["prompt.md"]] or _compact(config.get("task_contract")) != cell["inputs"]["task-contract.json"]: raise ValueError("Ox v2 run input commitments drifted")
    paths = sorted((run / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
    if len(paths) != 6 or [len(batch) for batch in cell.get("primary_batches", [])] != [32, 32, 32, 32, 32, 19] or list((run / "responses" / "rejected").rglob("*.json")): raise ValueError("Ox v2 requires six exact one-attempt batches")
    previous, receipts = None, []
    for number, path in enumerate(paths, 1):
        checkpoint = read_json(path)
        if (checkpoint.get("format_version") != 4 or checkpoint.get("batch") != number or checkpoint.get("question_ids") != cell["primary_batches"][number - 1] or checkpoint.get("previous_checkpoint_sha256") != previous or checkpoint.get("retry_policy") != {"batch_attempts": 1} or checkpoint.get("accepted_attempt") != 1 or checkpoint.get("recovered_from_rejected") is not None or checkpoint.get("rejected_chain") != {"count": 0, "head_sha256": None}): raise ValueError("Ox v2 checkpoint chain/retry policy drifted")
        receipts.append(_receipt(run, checkpoint))
        response = checkpoint.get("response_artifact"); raw_path = response.get("path") if isinstance(response, Mapping) else None
        if not isinstance(raw_path, str): raise ValueError("Ox v2 checkpoint lacks a bound accepted response")
        raw = (run / raw_path).resolve()
        if run.resolve() not in raw.parents: raise ValueError("Ox v2 checkpoint accepted response escapes its run")
        strict_json(raw.read_text(encoding="utf-8"), label=str(raw)); previous = sha(path)
    source, prompt_text = artifact.read_text(encoding="utf-8"), prompt.read_text(encoding="utf-8")
    try: replayed, count, _ = _load_checkpoints(run, artifact_text=source, context_texts=[prompt_text], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc: raise ValueError("Ox v2 checkpoint/schema replay failed") from exc
    verdict_path = run / "verdicts.jsonl"
    stored = [strict_json(line, label=f"{verdict_path}:{number}") for number, line in enumerate(verdict_path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    if count != 6 or replayed != stored or [row.get("question_id") for row in stored] != cell["primary_question_ids"] or len(set(receipts)) != 6: raise ValueError("Ox v2 verdict/receipt reconstruction is incomplete")
    modules, bundle, task = load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), CONTRACT["questions"]["bundle_id"]), read_json(task_path)
    primary, primary_v2 = score_bundle(modules, bundle, stored, artifact_id=str(cell["item_id"]), task_contract=task), score_bundle_v2(modules, bundle, stored, artifact_id=str(cell["item_id"]), task_contract=task)
    if {key: value for key, value in score.items() if key != "weight_profile"} != primary or score_v2 != primary_v2: raise ValueError("Ox v2 primary score descendants do not deterministically reconstruct")
    ablation = static_ablation(stored, task, str(cell["item_id"]))
    return {"run": fingerprint(run / "run.json"), "score": fingerprint(run / "score.json"), "score_v2": fingerprint(run / "score.v2.json"), "verdicts": fingerprint(verdict_path), "receipt_count": 6, "receipt_commitments": receipts, "physical_http_attempt_count": sum(read_json(path)["provider"]["physical_http_attempt_count"] for path in paths), "primary_score": _finite(primary_v2["final_score"]["observed"], "Ox primary score"), "static_ablation_score": _finite(ablation["final_score"]["observed"], "Ox static ablation"), "provisional": True}


def verify_evidence(work: Path, frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    invocation_path, claim_path = work / "pilot-invocation.json", work / "pilot-execution-claim.json"
    invocation = read_json(invocation_path); invocation_binding = fingerprint(invocation_path)
    expected_invocation = {"format_version": 2, "study_id": CONTRACT["study_id"], "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract_sha256": sha(work / "frozen-ox-alpha-v2-contract.json"), "provider": CONTRACT["provider"], "runtime": CONTRACT["runtime"], "remote_disclosure": CONTRACT["remote_disclosure"], "zero_cost": CONTRACT["zero_cost"]}
    if any(invocation.get(key) != value for key, value in expected_invocation.items()) or not isinstance(invocation.get("zero_cost_fresh_at_invocation"), str):
        raise ValueError("Ox v2 invocation does not bind the frozen execution protocol")
    _assert_fresh_at(frozen["zero_cost_proof"], invocation["zero_cost_fresh_at_invocation"])
    claim = read_json(claim_path)
    if claim.get("format_version") != 2 or claim.get("study_id") != CONTRACT["study_id"] or claim.get("kind") != "exclusive_serial_ox_alpha_execution" or claim.get("invocation") != invocation_binding or not isinstance(claim.get("pid"), int):
        raise ValueError("Ox v2 execution claim does not bind its invocation")
    journal = sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json"))
    if len(journal) != 3: raise ValueError("Ox v2 requires exactly three terminal journal records")
    proofs, receipts = [], set()
    for sequence, (cell, path) in enumerate(zip(frozen["cells"], journal), 1):
        record = read_json(path)
        if record.get("sequence") != sequence or record.get("cell_id") != cell["cell_id"] or record.get("item_id") != cell["item_id"] or record.get("status") != "completed" or record.get("invocation") != invocation_binding: raise ValueError("Ox v2 journal is incomplete, reordered, or failed")
        proof = verify_run(work, frozen, cell)
        if record.get("run") != proof["run"] or record.get("proof") != proof or receipts & set(proof["receipt_commitments"]): raise ValueError("Ox v2 journal/receipt binding drifted")
        receipts.update(proof["receipt_commitments"]); proofs.append(proof)
    if len(receipts) != 18 or sum(item["physical_http_attempt_count"] for item in proofs) > 36: raise ValueError("Ox v2 provider request ceiling or uniqueness drifted")
    return proofs


def analyze(work: Path, output: Path) -> None:
    if output.exists(): raise ValueError("Refusing to merge into or overwrite public Ox v2 analysis")
    frozen = load_frozen(work)
    fresh_sources = frozen["fresh88"]["sources"]
    roots = [work, Path(str(frozen["zero_cost_proof"]["path"])), Path(str(frozen["zero_cost_proof"]["catalog"]["root"])), Path(str(frozen["zero_cost_proof"]["usage"]["root"])), Path(str(fresh_sources["work"])), Path(str(fresh_sources["authority"])), Path(str(fresh_sources["repair1_artifacts"]))]
    roots.extend(path for cell in frozen["cells"] for path in (Path(str(cell["paths"]["artifact"])).parent, Path(str(cell["paths"]["prompt"])).parent, Path(str(cell["paths"]["task_contract"])).parent))
    if any(output.resolve() == root.resolve() or output.resolve() in root.resolve().parents or root.resolve() in output.resolve().parents for root in roots): raise ValueError("Public Ox v2 output must be disjoint from private work and evidence roots")
    proofs, rows = verify_evidence(work, frozen), []
    for cell, proof in zip(frozen["cells"], proofs):
        gpt = cell["gpt_reference"]; primary, static = _finite(gpt.get("primary_score"), "GPT primary score"), _finite(gpt.get("static_ablation_score"), "GPT static ablation")
        rows.append({"item_id": cell["item_id"], "primary": {"ox": proof["primary_score"], "gpt": primary, "ox_minus_gpt": proof["primary_score"] - primary}, "static_178_ablation": {"ox": proof["static_ablation_score"], "gpt": static, "ox_minus_gpt": proof["static_ablation_score"] - static, "noncanonical": True, "relevance_interpretation": "two_leaf_ablation_only"}, "receipt_count": proof["receipt_count"], "evidence_status": "provisional_only"})
    summary = {"format_version": 2, "study_id": CONTRACT["study_id"], "item_count": 3, "primary_question_count": 179, "secondary_static_ablation_question_count": 178, "logical_request_count": 18, "physical_http_attempt_count": sum(proof["physical_http_attempt_count"] for proof in proofs), "physical_http_attempt_ceiling": 36, "evidence_status": "provisional_only", "exact_gate_eligible": False, "provisional_blockers": ["provider_did_not_report_reasoning_effort", "protocol_forbids_exact_gate_use"], "interpretation_limits": CONTRACT["interpretation_limits"]}
    rendered_rows = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    proposed = {"summary.json": json.dumps(summary, sort_keys=True, indent=2) + "\n", "items.jsonl": rendered_rows}
    forbidden = [str(root.resolve()) for root in roots] + ["source.md", "prompt.md", "task-contract.json"]
    if any(token and token in "\n".join(proposed.values()) for token in forbidden): raise ValueError("Public Ox v2 output would leak a private path or prose-bearing filename")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        immutable_json(staging / "summary.json", summary); _atomic_text(staging / "items.jsonl", rendered_rows)
        immutable_json(staging / "manifest.json", {"format_version": 2, "study_id": CONTRACT["study_id"], "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "files": {path.name: fingerprint(path) for path in staging.iterdir() if path.is_file() and path.name != "manifest.json"}})
        final_text = "\n".join(path.read_text(encoding="utf-8") for path in staging.iterdir() if path.is_file())
        if any(token and token in final_text for token in forbidden): raise ValueError("Public Ox v2 output leaks private content")
        os.replace(staging, output)
    except BaseException:
        for path in staging.glob("*"):
            if path.is_file(): path.unlink()
        staging.rmdir(); raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--work-dir", required=True, type=Path); parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(); analyze(args.work_dir.resolve(), args.output_dir.resolve())
