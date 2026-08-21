#!/usr/bin/env python3
"""Fail-closed offline verification and prose-free analysis for the Ox Alpha pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hbqrs.core import load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, NOUS_TRANSPORT_POLICY, _json_bytes, _load_checkpoints, _validate_provider_artifacts

from study import CONTRACT, canonical, fingerprint, immutable_json, input_folder, load_frozen, read_json, sha, strict_json


def _compact(value: Any) -> dict[str, Any] | None:
    return {key: value.get(key) for key in ("name", "bytes", "sha256")} if isinstance(value, Mapping) else None


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _receipt(run: Path, record: Mapping[str, Any]) -> str:
    provider = record.get("provider")
    if not isinstance(provider, Mapping):
        raise ValueError("Accepted checkpoint lacks a Nous provider receipt")
    expected = CONTRACT["provider"]
    if provider.get("requested") != {"model": expected["model"], "reasoning_effort": "max"} or provider.get("reported") != {"provider": "nous", "model": expected["model"]}:
        raise ValueError("Ox Alpha provider/model receipt drifted")
    if provider.get("provider_canonical_model") != expected["provider_canonical_model"] or provider.get("reasoning_attested") is not False or provider.get("reasoning_attestation") != "provider_did_not_report_reasoning_effort":
        raise ValueError("Ox Alpha provisional max-attestation blocker is malformed")
    required = {"judge_request", "judge_result", "serialization_proof", "evidence_tree"}
    artifacts = provider.get("provider_artifacts")
    if (
        not isinstance(artifacts, Mapping) or set(artifacts) != required or provider.get("tool_free") is not True
        or provider.get("exact_gate_eligible") is not False or provider.get("transport_policy") != NOUS_TRANSPORT_POLICY
        or NOUS_TRANSPORT_POLICY["max_physical_attempts_per_logical_request"] != CONTRACT["runtime"]["maximum_physical_http_attempts_per_logical_request"]
        or provider.get("logical_provider_request_count") != 1 or not isinstance(provider.get("physical_http_attempt_count"), int)
        or not 1 <= provider["physical_http_attempt_count"] <= CONTRACT["runtime"]["maximum_physical_http_attempts_per_logical_request"]
        or provider.get("recovered_request_count") != 0 or not _is_hash(provider.get("evidence_sha256"))
        or not _is_hash(provider.get("serialization_proof_sha256"))
    ):
        raise ValueError("Ox Alpha transport is not a one-request provisional receipt")
    evidence = artifacts["evidence_tree"].get("path") if isinstance(artifacts["evidence_tree"], Mapping) else None
    proof = artifacts["serialization_proof"].get("path") if isinstance(artifacts["serialization_proof"], Mapping) else None
    if not isinstance(evidence, str) or not isinstance(proof, str) or not proof.startswith(evidence.rstrip("/") + "/"):
        raise ValueError("Serialization proof does not share the request EvidenceRoot")
    try:
        _validate_provider_artifacts(run, record)
    except Exception as exc:
        raise ValueError("Ox Alpha provider artifacts are invalid") from exc
    events_path = run / evidence / "events.jsonl"
    if not events_path.is_file():
        raise ValueError("Ox Alpha EvidenceRoot lacks the sealed HTTP event log")
    events = [strict_json(line, label=f"{events_path}:{number}") for number, line in enumerate(events_path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    attempts = [event.get("data") for event in events if isinstance(event, Mapping) and event.get("event_type") == "http_attempt"]
    statuses = [attempt.get("status") for attempt in attempts if isinstance(attempt, Mapping)]
    if len(statuses) != provider["physical_http_attempt_count"] or any(not isinstance(status, int) or isinstance(status, bool) or not 200 <= status < 300 for status in statuses):
        raise ValueError("Ox Alpha evidence records a non-2xx or unbound physical HTTP attempt")
    response = record.get("response_artifact")
    response_path = response.get("path") if isinstance(response, Mapping) else None
    if not isinstance(response_path, str):
        raise ValueError("Ox Alpha checkpoint lacks a bound accepted provider response")
    accepted_path = (run / response_path).resolve()
    try:
        accepted_path.relative_to(run.resolve())
    except ValueError as exc:
        raise ValueError("Ox Alpha accepted provider response escapes its private run") from exc
    accepted = strict_json(accepted_path.read_text(encoding="utf-8"), label=str(accepted_path))
    raw_payloads: list[Any] = []
    for attempt in attempts:
        body = attempt.get("response_body") if isinstance(attempt, Mapping) else None
        choices = body.get("choices") if isinstance(body, Mapping) else None
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
            raise ValueError("Ox Alpha EvidenceRoot lacks one raw provider message per HTTP attempt")
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise ValueError("Ox Alpha EvidenceRoot raw provider content is malformed")
        raw_payloads.append(strict_json(content, label=f"{events_path}:raw-provider"))
    if not any(canonical(payload) == canonical(accepted) for payload in raw_payloads):
        raise ValueError("Ox Alpha accepted response is not bound to the raw sealed provider message")
    return f"nous:{provider['evidence_sha256']}:{provider['serialization_proof_sha256']}"


def verify_run(work: Path, frozen: Mapping[str, Any], cell: Mapping[str, Any]) -> dict[str, Any]:
    folder = input_folder(frozen, cell)
    run = work / "runs" / str(cell["cell_id"])
    manifest = read_json(run / "run.json")
    score = read_json(run / "score.json")
    config = manifest.get("configuration")
    if not isinstance(config, Mapping) or manifest.get("format_version") != 3 or manifest.get("config_sha256") != hashlib.sha256(_json_bytes(config)).hexdigest():
        raise ValueError("Ox Alpha run manifest is malformed")
    expected = {
        "bundle_id": CONTRACT["runtime"]["bundle_id"], "question_ids": cell["question_ids"], "provider": "nous",
        "model": CONTRACT["provider"]["model"], "reasoning": "max", "batch_size": 32,
        "retry_policy": {"batch_attempts": 1}, "artifact_id": cell["item_id"], "strict_ai": False,
        "allow_unattested_reasoning": True, "nous_transport_policy": NOUS_TRANSPORT_POLICY,
        "nous_model_policy": {"requested_model": "stealth/ox-alpha", "provider_canonical_model": "stealth/ox-alpha", "required_reasoning_effort": "max"},
    }
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("Ox Alpha run configuration drifted")
    if _compact(config.get("artifact")) != cell["inputs"]["source.md"] or [_compact(item) for item in config.get("contexts", [])] != [cell["inputs"]["prompt.md"]] or _compact(config.get("task_contract")) != cell["inputs"]["task-contract.json"]:
        raise ValueError("Ox Alpha run inputs do not match the frozen primary cell")
    paths = sorted((run / "responses").glob("batch-[0-9][0-9][0-9][0-9].json"))
    if len(cell["question_ids"]) != 178 or len(set(cell["question_ids"])) != 178:
        raise ValueError("Ox Alpha cell does not bind all 178 unique HBQ questions")
    if len(paths) != CONTRACT["runtime"]["expected_batches_per_item"] or list((run / "responses" / "rejected").rglob("*.json")):
        raise ValueError("Ox Alpha run has missing batches or forbidden retry evidence")
    sessions: list[str] = []
    previous = None
    for number, path in enumerate(paths, 1):
        record = read_json(path)
        expected_ids = cell["question_ids"][(number - 1) * 32:number * 32]
        if record.get("format_version") != 4 or record.get("batch") != number or record.get("question_ids") != expected_ids or record.get("previous_checkpoint_sha256") != previous or record.get("retry_policy") != {"batch_attempts": 1} or record.get("accepted_attempt") != 1 or record.get("recovered_from_rejected") is not None or record.get("rejected_chain") != {"count": 0, "head_sha256": None}:
            raise ValueError("Ox Alpha checkpoint violates its one-attempt serial schedule")
        sessions.append(_receipt(run, record))
        response = record.get("response_artifact")
        raw_path = response.get("path") if isinstance(response, Mapping) else None
        if not isinstance(raw_path, str):
            raise ValueError("Ox Alpha checkpoint lacks a bound raw provider response")
        raw = (run / raw_path).resolve()
        try:
            raw.relative_to(run.resolve())
        except ValueError as exc:
            raise ValueError("Ox Alpha raw provider response escapes its private run") from exc
        strict_json(raw.read_text(encoding="utf-8"), label=str(raw))
        previous = sha(path)
    source = (folder / "source.md").read_text(encoding="utf-8")
    prompt = (folder / "prompt.md").read_text(encoding="utf-8")
    try:
        verdicts, count, _ = _load_checkpoints(run, artifact_text=source, context_texts=[prompt], batch_attempts=1, normalization_policy=EVIDENCE_NORMALIZATION_POLICY)
    except Exception as exc:
        raise ValueError("Ox Alpha checkpoint/schema replay failed") from exc
    stored = [strict_json(line, label=f"{run / 'verdicts.jsonl'}:{number}") for number, line in enumerate((run / "verdicts.jsonl").read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    if count != 6 or verdicts != stored or [item.get("question_id") for item in stored] != cell["question_ids"] or len(set(sessions)) != 6:
        raise ValueError("Ox Alpha verdict or provider-session proof is incomplete")
    bundle = resolve_bundle(load_bundles(bundles_path()), CONTRACT["runtime"]["bundle_id"])
    recomputed = score_bundle(load_modules(registry_path()), bundle, stored, artifact_id=str(cell["item_id"]), task_contract=read_json(folder / "task-contract.json"))
    if {key: value for key, value in score.items() if key != "weight_profile"} != recomputed:
        raise ValueError("Ox Alpha score does not deterministically reconstruct")
    return {"run": fingerprint(run / "run.json"), "receipt_count": 6, "receipt_commitments": sessions, "physical_http_attempt_count": sum(read_json(path)["provider"]["physical_http_attempt_count"] for path in paths), "provisional": True}


def verify_evidence(work: Path, frozen: Mapping[str, Any]) -> list[dict[str, Any]]:
    journal = sorted((work / "pilot-journal").glob("[0-9][0-9][0-9][0-9]-*.json"))
    if len(journal) != 3:
        raise ValueError("Ox Alpha pilot does not have exactly three terminal journal records")
    proofs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, cell in enumerate(frozen["cells"], 1):
        record = read_json(journal[number - 1])
        if record.get("sequence") != number or record.get("cell_id") != cell["cell_id"] or record.get("item_id") != cell["item_id"] or record.get("status") != "completed":
            raise ValueError("Ox Alpha journal is incomplete, reordered, or failed")
        proof = verify_run(work, frozen, cell)
        if record.get("run") != proof["run"] or record.get("proof") != proof:
            raise ValueError("Ox Alpha journal does not bind its verified run")
        overlap = seen & set(proof["receipt_commitments"])
        if overlap:
            raise ValueError("Ox Alpha provider session/evidence proof is reused")
        seen.update(proof["receipt_commitments"])
        proofs.append({"cell_id": cell["cell_id"], "item_id": cell["item_id"], **proof})
    if len(seen) != CONTRACT["runtime"]["maximum_logical_requests"]:
        raise ValueError("Ox Alpha pilot did not establish eighteen unique logical provider requests")
    if sum(item["physical_http_attempt_count"] for item in proofs) > CONTRACT["runtime"]["maximum_physical_http_attempts"]:
        raise ValueError("Ox Alpha pilot exceeded its frozen physical HTTP-attempt ceiling")
    return proofs


def _gpt_pairs(frozen: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    path = Path(str(frozen["gpt_reference"]["output"])) / "items.jsonl"
    rows = [strict_json(line, label=f"{path}:{number}") for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1) if line.strip()]
    pairs = {str(row.get("item_id")): row for row in rows if isinstance(row, Mapping)}
    wanted = {cell["item_id"] for cell in frozen["cells"]}
    if not wanted <= set(pairs):
        raise ValueError("Frozen GPT reference output no longer covers the selected Ox Alpha cells")
    return pairs


def _domain_diagnostics(score: Mapping[str, Any]) -> list[dict[str, Any]]:
    domains = score.get("domains")
    if not isinstance(domains, list):
        return []
    result: list[dict[str, Any]] = []
    for domain in domains:
        if not isinstance(domain, Mapping) or not isinstance(domain.get("domain_id"), str):
            raise ValueError("Ox Alpha score has malformed domain diagnostics")
        result.append({key: domain.get(key) for key in ("domain_id", "active", "coverage", "confidence", "score")})
    return result


def analyze(work: Path, output: Path) -> None:
    if output.exists():
        raise ValueError("Refusing to merge into or overwrite public Ox Alpha analysis")
    frozen = load_frozen(work)
    proofs = verify_evidence(work, frozen)
    gpt = _gpt_pairs(frozen)
    rows: list[dict[str, Any]] = []
    for cell, proof in zip(frozen["cells"], proofs):
        score = read_json(work / "runs" / cell["cell_id"] / "score.json")
        ox = score.get("final_score", {}).get("observed")
        gpt_row = gpt[cell["item_id"]]
        gpt_score = gpt_row.get("hbq_full_observed_score")
        rows.append({
            "item_id": cell["item_id"], "source_model": cell["source_model"], "story_sha256": cell["story_sha256"], "prompt_sha256": cell["prompt_sha256"],
            "ox_hbq_observed_score": ox, "gpt_hbq_observed_score": gpt_score,
            "ox_minus_gpt": float(ox) - float(gpt_score) if isinstance(ox, (int, float)) and isinstance(gpt_score, (int, float)) else None,
            "dimension_diagnostics": {"ox_domains": _domain_diagnostics(score)},
            "receipt_count": proof["receipt_count"], "evidence_status": "provisional_only",
        })
    summary = {
        "format_version": 1, "study_id": CONTRACT["study_id"], "provider_id": CONTRACT["provider"]["provider_id"],
        "item_count": 3, "logical_request_count": 18, "physical_http_attempt_count": sum(proof["physical_http_attempt_count"] for proof in proofs), "physical_http_attempt_ceiling": CONTRACT["runtime"]["maximum_physical_http_attempts"], "evidence_status": "provisional_only", "exact_gate_eligible": False,
        "provisional_blockers": ["provider_did_not_report_reasoning_effort", "protocol_forbids_exact_gate_use"],
        "interpretation_limits": CONTRACT["interpretation_limits"], "remote_disclosure": CONTRACT["remote_disclosure"], "zero_cost": CONTRACT["zero_cost"],
    }
    output.mkdir(parents=True)
    immutable_json(output / "summary.json", summary)
    (output / "items.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    immutable_json(output / "manifest.json", {"format_version": 1, "study_id": CONTRACT["study_id"], "contract_sha256": sha(Path(__file__).resolve().parent / "study-contract.json"), "files": {path.name: fingerprint(path) for path in output.iterdir() if path.is_file() and path.name != "manifest.json"}})
    forbidden = [str(work), str(frozen["primary_work_dir"]), str(frozen["gpt_reference"]["output"]), "source.md", "prompt.md", "task-contract.json"]
    rendered = "\n".join(path.read_text(encoding="utf-8") for path in output.iterdir() if path.is_file())
    if any(item and item in rendered for item in forbidden):
        raise ValueError("Public Ox Alpha output leaks private paths or prose-bearing filenames")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    analyze(args.work_dir.resolve(), args.output_dir.resolve())
