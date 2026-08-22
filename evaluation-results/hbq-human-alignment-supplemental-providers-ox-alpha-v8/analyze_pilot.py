#!/usr/bin/env python3
"""Fail-closed verifier and prose-free publisher for the Ox Alpha v8 successor."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, NOUS_TRANSPORT_POLICY, _json_bytes, _load_checkpoints
from hbqrs.scoring_v2 import score_bundle as score_bundle_v2
from study import CONTRACT, FROZEN_NAME, assert_fresh_at, fingerprint, input_paths, load_frozen, parent_v2, read_json, sha, strict_json, v7_verifier


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None


def _finite(value: Any, label: str) -> float:
    if isinstance(value, Mapping):
        value = value.get("final_score", {}).get("observed") if isinstance(value.get("final_score"), Mapping) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be finite")
    return float(value)


def _atomic_text(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(text)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _checkpoint_paths(root: Path) -> list[Path]:
    # Provider request/result sidecars intentionally share the batch prefix.
    return v7_verifier().checkpoint_paths(root)


def _expected_prompt(frozen: Mapping[str, Any], artifact_root: Path, cell: Mapping[str, Any], ids: list[str]) -> bytes:
    shim = {"item_id": cell["item_id"], "question_ids": ids}
    return v7_verifier()._expected_prompt(frozen, artifact_root, shim)


def _raw_transport(run: Path, checkpoint: Mapping[str, Any], prompt: bytes, frozen: Mapping[str, Any]) -> dict[str, Any]:
    """Reuse v7's exact request-v2/cap-1 raw transport verifier per batch."""
    return v7_verifier()._raw_transport(run, checkpoint, prompt, frozen)


def verify_run(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    run = work / "runs" / str(cell["cell_id"])
    manifest, score, score_v2 = read_json(run / "run.json"), read_json(run / "score.json"), read_json(run / "score.v2.json")
    config = manifest.get("configuration")
    policy = {**NOUS_TRANSPORT_POLICY, "max_physical_attempts_per_logical_request": 1}
    expected = {
        "bundle_id": CONTRACT["questions"]["bundle_id"], "question_ids": cell["primary_question_ids"], "provider": "nous", "model": CONTRACT["provider"]["model"],
        "reasoning": "max", "batch_size": 4, "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "strict_ai": False,
        "allow_unattested_reasoning": True, "nous_transport_policy": policy,
        "nous_model_policy": {"requested_model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "required_reasoning_effort": "max"},
    }
    if not isinstance(config, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(config)).hexdigest() or any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Ox v8 run configuration drifted")
    artifact, prompt, task_path = input_paths(cell)
    if _compact(config.get("artifact")) != cell["inputs"]["source.md"] or [_compact(item) for item in config.get("contexts", [])] != [cell["inputs"]["prompt.md"]] or _compact(config.get("task_contract")) != cell["inputs"]["task-contract.json"]:
        raise ValueError("Ox v8 run input commitments drifted")
    paths, batches = _checkpoint_paths(run / "responses"), cell["primary_batches"]
    if len(paths) != 45 or [len(batch) for batch in batches] != [4] * 44 + [3] or list((run / "responses" / "rejected").rglob("*.json")):
        raise ValueError("Ox v8 requires exactly forty-five unrecovered cap-1 batches")
    previous, receipts, sessions, logical_ids = None, [], [], []
    for number, (path, ids) in enumerate(zip(paths, batches), 1):
        checkpoint = read_json(path)
        if checkpoint.get("format_version") != 4 or checkpoint.get("batch") != number or checkpoint.get("question_ids") != ids or checkpoint.get("previous_checkpoint_sha256") != previous or checkpoint.get("retry_policy") != {"batch_attempts": 1} or checkpoint.get("accepted_attempt") != 1 or checkpoint.get("recovered_from_rejected") is not None or checkpoint.get("rejected_chain") != {"count": 0, "head_sha256": None}:
            raise ValueError("Ox v8 checkpoint chain or retry policy drifted")
        prompt_path = path.with_suffix(".prompt.txt.gz")
        prompt_bytes = gzip.decompress(prompt_path.read_bytes())
        if prompt_bytes != _expected_prompt(frozen, artifact.parent, cell, ids) or checkpoint.get("base_prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest() or checkpoint.get("prompt_sha256") != hashlib.sha256(prompt_bytes).hexdigest():
            raise ValueError("Ox v8 batch prompt is unbound")
        raw = _raw_transport(run, checkpoint, prompt_bytes, frozen)
        receipts.append(raw["receipt_id"])
        sessions.append(raw["session_id"])
        logical_ids.append(raw["logical_request_id"])
        previous = sha(path)
    if any(len(set(values)) != 45 for values in (receipts, sessions, logical_ids)):
        raise ValueError("Ox v8 reuses a batch receipt, session, or logical request")
    try:
        replayed, count, _ = _load_checkpoints(run, artifact_text=artifact.read_bytes().decode("utf-8"), context_texts=[prompt.read_bytes().decode("utf-8")], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("Ox v8 checkpoint/schema replay failed") from exc
    verdict_path = run / "verdicts.jsonl"
    stored = [strict_json(line, label=f"{verdict_path}:{number}") for number, line in enumerate(verdict_path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    if count != 45 or replayed != stored or [row.get("question_id") for row in stored] != cell["primary_question_ids"]:
        raise ValueError("Ox v8 verdict reconstruction is incomplete")
    modules, bundle, task = load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), CONTRACT["questions"]["bundle_id"]), read_json(task_path)
    primary = score_bundle(modules, bundle, stored, artifact_id=str(cell["item_id"]), task_contract=task)
    primary_v2 = score_bundle_v2(modules, bundle, stored, artifact_id=str(cell["item_id"]), task_contract=task)
    if {key: value for key, value in score.items() if key != "weight_profile"} != primary or score_v2 != primary_v2:
        raise ValueError("Ox v8 primary score descendants do not deterministically reconstruct")
    ablation = parent_v2().static_ablation(stored, task, str(cell["item_id"]))
    return {
        "run": fingerprint(run / "run.json"), "score": fingerprint(run / "score.json"), "score_v2": fingerprint(run / "score.v2.json"), "verdicts": fingerprint(verdict_path),
        "receipt_count": 45, "receipt_commitments": receipts, "session_ids": sessions, "logical_request_ids": logical_ids,
        "physical_http_attempt_count": 45, "primary_score": _finite(primary_v2, "Ox primary score"), "static_ablation_score": _finite(ablation, "Ox static ablation"), "provisional": True,
    }


def _invocation(work: Path, frozen: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    path = work / "pilot-invocation.json"
    record = read_json(path)
    required = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "outcome_blind_serial_cap1_full_scoring", "contract": fingerprint(Path(__file__).resolve().parent / "study-contract.json"), "frozen_contract": fingerprint(work / FROZEN_NAME), "provider": CONTRACT["provider"], "runtime": CONTRACT["runtime"], "remote_disclosure": CONTRACT["remote_disclosure"], "zero_cost": CONTRACT["zero_cost"]}
    if any(record.get(key) != value for key, value in required.items()) or record.get("runtime_bindings") != frozen["runtime"] or record.get("runner", {}).get("sha256") != frozen["runtime"]["runner"]["sha256"] or record.get("executor") != fingerprint(Path(__file__).resolve().parent / "run_pilot.py") or record.get("verifier") != fingerprint(Path(__file__)) or not isinstance(record.get("zero_cost_fresh_at_invocation"), str):
        raise ValueError("Ox v8 invocation does not bind the frozen execution protocol")
    assert_fresh_at(frozen["zero_cost_proof"], record["zero_cost_fresh_at_invocation"])
    return record, fingerprint(path)


def verify_evidence(work: Path, frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    if (work / "pilot-uncertain.json").exists():
        raise ValueError("Ox v8 contains an immutable uncertain outcome")
    _, invocation = _invocation(work, frozen)
    claim = read_json(work / "pilot-execution-claim.json")
    if claim != {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "exclusive_serial_cap1_full_scoring_execution", "invocation": invocation, "pid": claim.get("pid")} or type(claim.get("pid")) is not int:
        raise ValueError("Ox v8 execution claim does not bind its invocation")
    paths = sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json"))
    if len(paths) != 3 or len(paths) != len(list((work / "pilot-journal").iterdir())):
        raise ValueError("Ox v8 requires exactly three terminal journal records")
    proofs = []
    for sequence, (cell, path) in enumerate(zip(frozen["cells"], paths), 1):
        record, proof = read_json(path), verify_run(work, frozen, cell)
        receipt_path = work / "pilot-receipts" / f"{cell['cell_id']}.json"
        receipt = {"format_version": 1, "study_id": CONTRACT["study_id"], "kind": "cap1_full_scoring_completion", "cell_id": cell["cell_id"], "item_id": cell["item_id"], "question_count": len(cell["primary_question_ids"]), "v7_transport_tree": frozen["v7_transport_success"]["tree"], "excluded_v7_global_ids": frozen["v7_transport_success"]["global_ids"], "proof": proof}
        if read_json(receipt_path) != receipt:
            raise ValueError("Ox v8 semantic receipt drifted")
        expected = {"sequence": sequence, "cell_id": cell["cell_id"], "item_id": cell["item_id"], "status": "completed", "invocation": invocation, "receipt": fingerprint(receipt_path), "proof": proof}
        if record != expected:
            raise ValueError("Ox v8 journal is incomplete, reordered, or failed")
        proofs.append(proof)
    expected_receipts = sorted(f"{cell['cell_id']}.json" for cell in frozen["cells"])
    receipt_root = work / "pilot-receipts"
    if not receipt_root.is_dir() or sorted(path.name for path in receipt_root.iterdir()) != expected_receipts:
        raise ValueError("Ox v8 semantic receipt set is malformed")
    all_receipts = [value for proof in proofs for value in proof["receipt_commitments"]]
    all_sessions = [value for proof in proofs for value in proof["session_ids"]]
    all_logical = [value for proof in proofs for value in proof["logical_request_ids"]]
    if any(len(set(values)) != 135 for values in (all_receipts, all_sessions, all_logical)):
        raise ValueError("Ox v8 reuses identities across full-scoring cells")
    predecessor = frozen["v7_transport_success"]["global_ids"]
    if any(set(values) & set(predecessor[key]) for key, values in (("receipt_id", all_receipts), ("session_id", all_sessions), ("logical_request_id", all_logical))):
        raise ValueError("Ox v8 reuses a successful v7 provider identity")
    return proofs


def analyze(work: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Refusing to merge into or overwrite public Ox v8 analysis")
    frozen = load_frozen(work)
    sources = frozen["fresh88"]["sources"]
    roots = [work, Path(str(frozen["zero_cost_proof"]["path"])), Path(str(frozen["zero_cost_proof"]["catalog"]["root"])), Path(str(frozen["zero_cost_proof"]["usage"]["root"])), Path(str(frozen["v7_transport_success"]["root"])), *(Path(str(sources[key])) for key in ("work", "authority", "repair1_artifacts"))]
    roots.extend(Path(str(cell["paths"]["artifact"])).parent for cell in frozen["cells"])
    if any(output.resolve() == root.resolve() or output.resolve() in root.resolve().parents or root.resolve() in output.resolve().parents for root in roots):
        raise ValueError("Public Ox v8 output must be disjoint from private work and evidence roots")
    proofs, rows = verify_evidence(work, frozen), []
    for cell, proof in zip(frozen["cells"], proofs):
        reference = cell["gpt_reference"]
        primary, static = _finite(reference.get("primary_score"), "GPT primary score"), _finite(reference.get("static_ablation_score"), "GPT static ablation")
        rows.append({"item_id": cell["item_id"], "primary": {"ox": proof["primary_score"], "gpt": primary, "ox_minus_gpt": proof["primary_score"] - primary}, "static_178_ablation": {"ox": proof["static_ablation_score"], "gpt": static, "ox_minus_gpt": proof["static_ablation_score"] - static, "noncanonical": True, "relevance_interpretation": "two_leaf_ablation_only"}, "receipt_count": proof["receipt_count"], "evidence_status": "provisional_only"})
    summary = {"format_version": 1, "study_id": CONTRACT["study_id"], "item_count": 3, "primary_question_count": 179, "secondary_static_ablation_question_count": 178, "logical_request_count": 135, "physical_http_attempt_count": sum(proof["physical_http_attempt_count"] for proof in proofs), "physical_http_attempt_ceiling": 135, "evidence_status": "provisional_only", "exact_gate_eligible": False, "provisional_blockers": ["provider_did_not_report_reasoning_effort", "protocol_forbids_exact_gate_use"], "interpretation_limits": CONTRACT["interpretation_limits"]}
    rendered_rows = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    forbidden = [str(root.resolve()) for root in roots] + ["source.md", "prompt.md", "task-contract.json"]
    if any(token and token in "\n".join((json.dumps(summary), rendered_rows)) for token in forbidden):
        raise ValueError("Public Ox v8 output would leak private paths or prose-bearing filenames")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        _atomic_text(staging / "summary.json", json.dumps(summary, sort_keys=True, indent=2) + "\n")
        _atomic_text(staging / "items.jsonl", rendered_rows)
        manifest = {"format_version": 1, "study_id": CONTRACT["study_id"], "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "files": {path.name: fingerprint(path) for path in staging.iterdir() if path.is_file()}}
        _atomic_text(staging / "manifest.json", json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        final = "\n".join(path.read_text(encoding="utf-8") for path in staging.iterdir() if path.is_file())
        if any(token and token in final for token in forbidden):
            raise ValueError("Public Ox v8 output leaks private content")
        os.replace(staging, output)
    except BaseException:
        for path in staging.glob("*"):
            if path.is_file():
                path.unlink()
        staging.rmdir()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.work_dir.resolve(), args.output_dir.resolve())
