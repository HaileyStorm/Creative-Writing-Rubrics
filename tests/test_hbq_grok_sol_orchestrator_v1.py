from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from hbqrs import runner
from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-grok-sol-current-matched-v1"


def load(name: str):
    spec = importlib.util.spec_from_file_location(f"strict_orchestrator_{name}", ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


study, analyze, orchestrator = load("study"), load("analyze_study"), load("orchestrator")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def prepared(tmp_path: Path):
    frozen_dir = tmp_path / "frozen"
    snapshot = study.freeze(frozen_dir)
    disclosure = study.dispatch_disclosure(snapshot)
    ack = {"format_version": 1, "acknowledged_by": "external owner", "acknowledgement": "Exact public synthetic payload reviewed.",
           "disclosure_sha256": digest(study.canonical(disclosure)), "conditions_sha256": digest(study.canonical(snapshot["protocol"]["conditions"]))}
    proofs = {"format_version": 1, "proofs": {row["condition_id"]: {"provider": row["provider"], "model": row["model"], "checked_at": "2026-08-28T00:00:00Z", "proof_kind": "live_account_zero_charge_inspection", "evidence_reference": "external fixture", "paid_api": False, "no_payment_method": True, "no_paid_fallback": True, "no_hold_or_deposit": True, "no_billable_dispatch": True} for row in snapshot["protocol"]["conditions"]}}
    ack_path, proofs_path = tmp_path / "ack.json", tmp_path / "proofs.json"
    ack_path.write_bytes(study.canonical(ack)); proofs_path.write_bytes(study.canonical(proofs))
    dispatch = tmp_path / "prepared"
    study.prepare(frozen_dir / "frozen-inputs.json", ack_path, proofs_path, dispatch)
    receipt = tmp_path / "untrusted-local-receipt.json"
    receipt.write_bytes(study.canonical({"study_id": study.EXPECTED_STUDY_ID}))
    return snapshot, frozen_dir / "frozen-inputs.json", dispatch / "dispatch-binding.json", receipt


def write_v4_run(work: Path, snapshot: dict, *, condition_id: str = "sol") -> tuple[dict, Path]:
    case = study.cases()[0]
    condition = next(row for row in study.contract()["conditions"] if row["condition_id"] == condition_id)
    run = work / "runs" / condition_id / case["case_id"] / "run-01"
    responses = run / "responses"; responses.mkdir(parents=True)
    runtime = {row["relative_path"]: row for row in snapshot["runtime"]}
    commitment = snapshot["case_commitments"][case["case_id"]]
    config = {
        "artifact": {"path": "fixture/source.md", **commitment["artifact"]}, "contexts": [{"path": "fixture/context.md", **commitment["context"]}],
        "task_contract": None, "task_contract_judge_context": None, "scope_compatibility": None, "weight_profile": None,
        "bundle_id": case["bundle_id"], "bundle_version": analyze._bundle_version(case["bundle_id"]), "question_ids": [case["question_id"]],
        "provider": condition["provider"], "model": condition["model"], "endpoint": None, "api_key_env": None, "temperature": None, "allow_model_mismatch": None,
        "reasoning": condition["reasoning"], "batch_size": 1, "retry_policy": {"batch_attempts": 1}, "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY,
        "artifact_id": case["case_id"], "judge_id": f"{condition['provider']}:{condition['model']}", "strict_ai": False, "prompt_rendering_version": runner.PROMPT_RENDERING_VERSION,
        "prompts": [{"path": "fixture/prompt", "name": "BINARY_EVALUATION_PROMPT.md", "bytes": runtime["prompts/judge/BINARY_EVALUATION_PROMPT.md"]["bytes"], "sha256": runtime["prompts/judge/BINARY_EVALUATION_PROMPT.md"]["sha256"]}],
        "response_schema": {"path": "fixture/schema", "name": "hbq_judge_response.schema.json", "bytes": runtime["schema/hbq_judge_response.schema.json"]["bytes"], "sha256": runtime["schema/hbq_judge_response.schema.json"]["sha256"]},
    }
    config["compiled_bundle_sha256"], config["questions_sha256"] = analyze._package_hashes(case["bundle_id"], case["question_id"])
    if condition_id == "sol": config["codex_bin"] = "codex"
    else: config.update({"grok_bin": "grok", "allow_unattested_reasoning": True})
    run_id = f"fixture-{condition_id}"
    (run / "run.json").write_bytes(runner._json_bytes({"format_version": 4, "run_id": run_id, "created_at": "2026-08-28T00:00:00+00:00", "config_sha256": digest(runner._json_bytes(config)), "remote": True, "configuration": config}))
    prompt = study.rendered_prompt(case, condition).encode("utf-8")
    (responses / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt, mtime=0))
    raw = json.dumps({"verdicts": [{"question_id": case["question_id"], "verdict": "YES", "confidence": 0.9, "evidence": [{"kind": "exact_quote", "reference": "source.md", "exact_quote": case["artifact"], "summary": None}], "note": "fixture"}]}).encode("utf-8")
    raw_path = responses / "batch-0001.accepted-0001.message.txt"; raw_path.write_bytes(raw)
    verdict = runner._normalize_batch(json.loads(raw), expected_ids=[case["question_id"]], artifact_id=case["case_id"], bundle_id=case["bundle_id"], judge_id=config["judge_id"], run_id=run_id, artifact_text=case["artifact"], context_texts=[case["context"]], normalization_policy=runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[])[0]
    provider = {"command": ["codex", "exec", "fixture"], "reported": {"model": condition["model"], "provider": "openai", "reasoning_effort": condition["reasoning"]}}
    checkpoint = {"format_version": 4, "batch": 1, "retry_policy": {"batch_attempts": 1}, "accepted_attempt": 1, "question_ids": [case["question_id"]], "prompt_sha256": digest(prompt), "base_prompt_sha256": digest(prompt), "effective_prompt_sha256": digest(prompt), "validation_feedback_policy": runner.VALIDATION_FEEDBACK_POLICY, "validation_feedback": None, "normalization_policy": runner.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": [], "response_sha256": digest(raw), "response_artifact": {"path": raw_path.relative_to(run).as_posix(), "bytes": len(raw), "sha256": digest(raw)}, "rejected_chain": {"count": 0, "head_sha256": None}, "previous_checkpoint_sha256": None, "verdicts_sha256": digest(runner._verdicts_bytes([verdict])), "provider": provider, "normalized_verdicts": [verdict]}
    (responses / "batch-0001.json").write_bytes(runner._json_bytes(checkpoint)); (run / "verdicts.jsonl").write_bytes(runner._verdicts_bytes([verdict]))
    return case, run


def test_all_36_tasks_are_identical_and_inspection_is_local_only(tmp_path: Path):
    snapshot, frozen, binding, receipt = prepared(tmp_path)
    sol, grok = study.contract()["conditions"]
    assert all(study.rendered_prompt(case, sol).encode() == study.rendered_prompt(case, grok).encode() for case in study.cases() for _ in range(3))
    result = orchestrator.inspect_cell(frozen_path=frozen, prepared_binding_path=binding, trusted_receipt_path=receipt, condition_id="sol", case_id=study.cases()[0]["case_id"], repetition=1)
    assert result["status"] == "preflight_only_no_dispatch" and result["provider_calls"] == 0
    assert result["launcher_identity"]["status"] == "no_local_trust_anchor"


def test_local_receipt_cannot_dispatch_or_create_provider_intent(tmp_path: Path):
    _, frozen, binding, receipt = prepared(tmp_path)
    work = tmp_path / "work"
    with pytest.raises(RuntimeError, match="trusted launch authority"):
        orchestrator.execute_cell(frozen_path=frozen, prepared_binding_path=binding, trusted_receipt_path=receipt, work_root=work, condition_id="sol", case_id=study.cases()[0]["case_id"], repetition=1, allow_remote=True)
    assert not work.exists()


def test_strict_v4_native_evidence_validation_and_fake_missing_evidence_rejection(tmp_path: Path):
    snapshot, frozen, binding, _ = prepared(tmp_path)
    work = tmp_path / "work"; case, run = write_v4_run(work, snapshot)
    result = orchestrator.validate_completed_cell(frozen_path=frozen, prepared_binding_path=binding, work_root=work, condition_id="sol", case_id=case["case_id"], repetition=1)
    assert result["status"] == "native_v4_evidence_validated_nonpromotable"
    (run / "responses" / "batch-0001.accepted-0001.message.txt").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="accepted-response receipt"):
        orchestrator.validate_completed_cell(frozen_path=frozen, prepared_binding_path=binding, work_root=work, condition_id="sol", case_id=case["case_id"], repetition=1)


def test_binding_reparse_and_intent_recovery_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _, frozen, binding, receipt = prepared(tmp_path)
    data = json.loads(binding.read_text(encoding="utf-8")); ack_path = binding.parent / data["owner_acknowledgement"]["relative_path"]
    ack = json.loads(ack_path.read_text(encoding="utf-8")); ack["acknowledged_by"] = "placeholder"; ack_path.write_bytes(study.canonical(ack))
    data["owner_acknowledgement"] = {"relative_path": ack_path.name, "bytes": ack_path.stat().st_size, "sha256": digest(ack_path.read_bytes())}
    binding.write_bytes(study.canonical(data))
    with pytest.raises(RuntimeError, match="not admissible"):
        orchestrator.inspect_cell(frozen_path=frozen, prepared_binding_path=binding, trusted_receipt_path=receipt, condition_id="sol", case_id=study.cases()[0]["case_id"], repetition=1)
    work = tmp_path / "recovery"; intent = work / "runs" / "sol" / study.cases()[0]["case_id"] / "run-01" / "attempt-intent.json"; intent.parent.mkdir(parents=True); intent.write_text("{}", encoding="utf-8")
    assert orchestrator.recover_cell(work_root=work, condition_id="sol", case_id=study.cases()[0]["case_id"], repetition=1)["status"] == "precontact_or_unresolved_no_resend"
    monkeypatch.setattr(orchestrator, "_is_reparse", lambda path: path == frozen)
    with pytest.raises(RuntimeError, match="Reparse"):
        orchestrator.inspect_cell(frozen_path=frozen, prepared_binding_path=binding, trusted_receipt_path=receipt, condition_id="sol", case_id=study.cases()[0]["case_id"], repetition=1)
