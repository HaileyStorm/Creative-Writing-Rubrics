from __future__ import annotations

import importlib.util
import json
import sys
import gzip
import hashlib
import shutil
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root

ROOT = book_root() / "evaluation-results" / "hbq-grok-sol-current-matched-v1"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


study = load("study")
analyze = load("analyze_study")


def test_contract_has_a_small_public_synthetic_matched_screen():
    assert study.validate() == {"study_id": "hbq-grok-sol-current-matched-v1", "cases": 12, "conditions": 2, "provider_calls": 0}
    contract = study.contract()
    assert contract["conditions"] == study.EXPECTED_CONDITIONS
    assert contract["candidate_condition"]["enabled_by_default"] is False
    assert contract["dispatch_prerequisites"]["execution_enabled"] is False
    assert contract["runtime_input_policy"] == "exact_content_hashes_independent_of_porcelain"
    assert "schema/hbq_verdict.schema.json" in contract["runtime_files"]
    assert contract["evidence_policy"]["promotion_class"] == "NON_PROMOTABLE"
    assert contract["batch_attempts"] == 1
    assert "75.19" not in contract["historical_context"]
    assert "score" not in " ".join(contract["metrics"])


def make_manifest(case: dict, condition: dict, commitment: dict, run_id: str = "fixture-run") -> dict:
    runtime = {item["relative_path"]: item for item in SNAPSHOT["runtime"]}
    config = {
        "artifact": {"path": "unused", **commitment["artifact"]},
        "contexts": [{"path": "unused", **commitment["context"]}],
        "task_contract": None, "task_contract_judge_context": None, "scope_compatibility": None, "weight_profile": None,
        "bundle_id": case["bundle_id"], "bundle_version": analyze._bundle_version(case["bundle_id"]), "question_ids": [case["question_id"]],
        "provider": condition["provider"], "model": condition["model"], "endpoint": None, "api_key_env": None, "temperature": None,
        "allow_model_mismatch": None, "reasoning": condition["reasoning"], "batch_size": 1, "retry_policy": {"batch_attempts": 1},
        "retry_semantics": "cumulative_batch_attempts_v1", "evidence_normalization_policy": analyze.runner.EVIDENCE_NORMALIZATION_POLICY,
        "validation_feedback_policy": analyze.runner.VALIDATION_FEEDBACK_POLICY, "artifact_id": case["case_id"],
        "judge_id": f"{condition['provider']}:{condition['model']}", "strict_ai": False,
        "prompt_rendering_version": analyze.runner.PROMPT_RENDERING_VERSION,
        "prompts": [{"path": "unused", "name": runtime["prompts/judge/BINARY_EVALUATION_PROMPT.md"]["relative_path"].split("/")[-1], "bytes": runtime["prompts/judge/BINARY_EVALUATION_PROMPT.md"]["bytes"], "sha256": runtime["prompts/judge/BINARY_EVALUATION_PROMPT.md"]["sha256"]}],
        "response_schema": {"path": "unused", "name": "hbq_judge_response.schema.json", "bytes": runtime["schema/hbq_judge_response.schema.json"]["bytes"], "sha256": runtime["schema/hbq_judge_response.schema.json"]["sha256"]},
    }
    if condition["condition_id"] == "sol":
        config["codex_bin"] = "codex"
    else:
        config["grok_bin"] = "grok"
        config["allow_unattested_reasoning"] = True
    config["compiled_bundle_sha256"], config["questions_sha256"] = analyze._package_hashes(case["bundle_id"], case["question_id"])
    return {
        "format_version": 4, "run_id": run_id, "created_at": "2026-08-27T00:00:00+00:00", "remote": True,
        "config_sha256": __import__("hashlib").sha256(analyze.runner._json_bytes(config)).hexdigest(), "configuration": config,
    }


@pytest.fixture(scope="module", autouse=True)
def snapshot(tmp_path_factory):
    global SNAPSHOT, FROZEN_PATH
    FROZEN_PATH = tmp_path_factory.mktemp("grok-sol-frozen") / "frozen" / "frozen-inputs.json"
    SNAPSHOT = study.freeze(FROZEN_PATH.parent)
    return SNAPSHOT


def write_run_evidence(work, case, condition, repetition, *, valid_manifest=True):
    run = work / "runs" / condition["condition_id"] / case["case_id"] / f"run-{repetition:02d}"
    run.mkdir(parents=True)
    manifest = make_manifest(case, condition, SNAPSHOT["case_commitments"][case["case_id"]]) if valid_manifest else {"fixture": True}
    (run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    (run / "checkpoint.jsonl").write_text('{"accepted":true}\n', encoding="utf-8")
    (run / "verdicts.jsonl").write_text('{"accepted":true}\n', encoding="utf-8")
    (run / "rejected.jsonl").write_text('', encoding="utf-8")
    return run


def write_full_run_tree(work):
    for condition in study.contract()["conditions"]:
        for case in study.cases():
            for repetition in range(1, 4):
                write_run_evidence(work, case, condition, repetition, valid_manifest=False)


def write_complete_runner_run(work, case, condition, repetition):
    run = work / "runs" / condition["condition_id"] / case["case_id"] / f"run-{repetition:02d}"
    responses = run / "responses"
    responses.mkdir(parents=True)
    run_id = f"fixture-{condition['condition_id']}-{case['case_id']}-{repetition}"
    manifest = make_manifest(case, condition, SNAPSHOT["case_commitments"][case["case_id"]], run_id)
    (run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    prompt = study.rendered_prompt(case, condition).encode("utf-8")
    (responses / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt, mtime=0))
    raw_response = {
        "verdicts": [{
            "question_id": case["question_id"], "verdict": study.contract()["design_intent_verdicts"][case["design_intent"]], "confidence": 0.9,
            "evidence": [{"kind": "exact_quote", "reference": "source.md", "exact_quote": case["artifact"], "summary": None}], "note": "provider-free fixture",
        }]
    }
    response = json.dumps(raw_response, ensure_ascii=False).encode("utf-8")
    response_path = responses / "batch-0001.accepted-0001.message.txt"
    response_path.write_bytes(response)
    verdict = analyze.runner._normalize_batch(
        raw_response, expected_ids=[case["question_id"]], artifact_id=case["case_id"], bundle_id=case["bundle_id"],
        judge_id=f"{condition['provider']}:{condition['model']}", run_id=run_id, artifact_text=case["artifact"], context_texts=[case["context"]],
        normalization_policy=analyze.runner.EVIDENCE_NORMALIZATION_POLICY, repair_audit=[],
    )[0]
    prompt_sha = hashlib.sha256(prompt).hexdigest()
    if condition["condition_id"] == "sol":
        provider = {"command": ["codex", "exec", "<fixture>"], "reported": {"model": condition["model"], "provider": "openai", "reasoning_effort": condition["reasoning"]}}
    else:
        envelope_path = responses / "batch-0001.attempt-0001.grok.envelope.json"
        session_id, request_id = f"fixture-session-{run_id}", f"fixture-request-{run_id}"
        envelope_path.write_text(json.dumps({"sessionId": session_id, "requestId": request_id, "modelUsage": {"grok-4.6-build": {}}}), encoding="utf-8")
        provider = {
            "cli_version": "fixture", "requested": {"model": condition["model"], "reasoning_effort": condition["reasoning"]},
            "reported": {"provider": "grok", "model": "grok-4.6-build"}, "session_id_sha256": hashlib.sha256(session_id.encode("utf-8")).hexdigest(), "request_id_sha256": hashlib.sha256(request_id.encode("utf-8")).hexdigest(),
            "reasoning_attested": False, "reasoning_attestation": "not_reported_by_grok_build_cli",
            "provider_artifacts": {"grok_envelope": analyze.runner._provider_artifact(run, envelope_path)},
        }
    checkpoint = {
        "format_version": 4, "batch": 1, "previous_checkpoint_sha256": None, "question_ids": [case["question_id"]],
        "normalized_verdicts": [verdict], "retry_policy": {"batch_attempts": 1}, "accepted_attempt": 1,
        "response_artifact": {"path": response_path.relative_to(run).as_posix(), "bytes": len(response), "sha256": hashlib.sha256(response).hexdigest()},
        "response_sha256": hashlib.sha256(response).hexdigest(), "rejected_chain": {"count": 0, "head_sha256": None},
        "prompt_sha256": prompt_sha, "base_prompt_sha256": prompt_sha, "effective_prompt_sha256": prompt_sha,
        "validation_feedback_policy": analyze.runner.VALIDATION_FEEDBACK_POLICY, "validation_feedback": None,
        "normalization_policy": analyze.runner.EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": [], "provider": provider,
    }
    checkpoint["verdicts_sha256"] = hashlib.sha256(analyze.runner._verdicts_bytes([verdict])).hexdigest()
    (responses / "batch-0001.json").write_bytes(analyze.runner._json_bytes(checkpoint))
    (run / "verdicts.jsonl").write_bytes(analyze.runner._verdicts_bytes([verdict]))
    return run


def write_complete_runner_tree(work):
    for condition in study.contract()["conditions"]:
        for case in study.cases():
            for repetition in range(1, 4):
                write_complete_runner_run(work, case, condition, repetition)


def prepare_dispatch(tmp_path, snapshot):
    disclosure = study.dispatch_disclosure(snapshot)
    acknowledgement = {
        "format_version": 1, "acknowledged_by": "fixture owner", "acknowledgement": "Fixture acknowledgement of exact public-synthetic disclosure.",
        "disclosure_sha256": hashlib.sha256(study.canonical(disclosure)).hexdigest(),
        "conditions_sha256": hashlib.sha256(study.canonical(snapshot["protocol"]["conditions"])).hexdigest(),
    }
    proofs = {
        "format_version": 1,
        "proofs": {
            condition["condition_id"]: {
                "provider": condition["provider"], "model": condition["model"], "checked_at": "2026-08-27T18:00:00Z",
                "proof_kind": "live_account_zero_charge_inspection", "evidence_reference": "fixture-only account shape",
                "paid_api": False, "no_payment_method": True, "no_paid_fallback": True, "no_hold_or_deposit": True, "no_billable_dispatch": True,
            }
            for condition in snapshot["protocol"]["conditions"]
        },
    }
    acknowledgement_path, proof_path = tmp_path / "fixture-ack.json", tmp_path / "fixture-proof.json"
    acknowledgement_path.write_text(json.dumps(acknowledgement), encoding="utf-8")
    proof_path.write_text(json.dumps(proofs), encoding="utf-8")
    prepared = tmp_path / "prepared"
    study.prepare(FROZEN_PATH, acknowledgement_path, proof_path, prepared)
    return prepared / "dispatch-binding.json"


def test_run_revalidates_real_runner_contract_and_rejects_mutation(monkeypatch, tmp_path, snapshot):
    case = study.cases()[0]; condition = study.contract()["conditions"][0]
    run = write_complete_runner_run(tmp_path / "work", case, condition, 1)
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    verdict = json.loads((run / "responses" / "batch-0001.json").read_text(encoding="utf-8"))["normalized_verdicts"][0]
    monkeypatch.setattr(analyze.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([verdict], 1, None))
    monkeypatch.setattr(analyze.runner, "_load_completed", lambda *_args, **_kwargs: [verdict])
    monkeypatch.setattr(analyze.runner, "_rejected_records", lambda *_args, **_kwargs: [])
    result = analyze._run(tmp_path / "work", snapshot, case, "sol", 1)
    assert result["verdict"] == "YES"
    assert result["exact_quote_count"] == 1
    assert result["evidence_localizations"] == [{"reference": "source.md", "start_offset": 0, "end_offset": len(case["artifact"]), "exact_quote": case["artifact"]}]
    assert {"run.json", "verdicts.jsonl", "batch-0001.json", "batch-0001.prompt.txt.gz", "batch-0001.accepted-0001.message.txt"}.issubset({item["relative_path"].split("/")[-1] for item in result["input_evidence"]})
    manifest["configuration"]["question_ids"] = ["wrong"]
    manifest["config_sha256"] = __import__("hashlib").sha256(analyze.runner._json_bytes(manifest["configuration"])).hexdigest()
    (run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="configuration"):
        analyze._run(tmp_path / "work", snapshot, case, "sol", 1)
    manifest = json.loads((run / "run.json").read_text(encoding="utf-8"))
    manifest.pop("created_at")
    (run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="exact current V4 shape"):
        analyze._run(tmp_path / "work", snapshot, case, "sol", 1)


def test_analyzer_reports_cross_model_and_per_model_repeatability(monkeypatch, tmp_path, snapshot):
    write_full_run_tree(tmp_path / "work")

    def fake_run(_work, _snapshot, case, condition_id, repetition):
        expected = study.contract()["design_intent_verdicts"][case["design_intent"]]
        verdict = "NO" if case["case_id"] == study.cases()[0]["case_id"] else expected
        return {
            "verdict": verdict,
            "exact_quote_count": 1,
            "evidence": [{"reference": "source.md", "exact_quote": case["artifact"], "summary": None}],
            "evidence_localizations": [{"reference": "source.md", "start_offset": 0, "end_offset": len(case["artifact"]), "exact_quote": case["artifact"]}],
            "configuration": {"fixture": case["case_id"]},
            "run_id": f"{condition_id}:{case['case_id']}:{repetition}",
            "provider_receipt": {"session_id_sha256": hashlib.sha256(f"session:{case['case_id']}:{repetition}".encode("utf-8")).hexdigest(), "request_id_sha256": hashlib.sha256(f"request:{case['case_id']}:{repetition}".encode("utf-8")).hexdigest()} if condition_id == "grok" else {},
        }

    monkeypatch.setattr(analyze, "_run", fake_run)
    summary = analyze.analyze(FROZEN_PATH, tmp_path / "work", prepare_dispatch(tmp_path, snapshot), tmp_path / "analysis")
    assert summary["pair_count"] == 36
    assert summary["evidence_class"] == "DEVELOPMENT_SCREENING_FIXTURE"
    assert summary["promotion"]["eligible"] is False
    assert summary["four_state"]["exact_agreement"]["rate"] == 1.0
    assert summary["per_judge_design_intent"]["sol"]["exact_agreement"]["rate"] < 1.0
    assert {row["sol_verdict"] for row in summary["case_disagreement_ledger"]} == {"YES", "NO", "NOT_APPLICABLE", "CANNOT_ASSESS"}
    assert any(row["common_mode_wrong"] for row in summary["case_disagreement_ledger"])
    assert summary["repeatability"]["sol"]["all_three_rate"]["rate"] == 1.0
    assert summary["repeatability"]["grok"]["mean_pairwise_agreement"] == 1.0
    assert summary["directional_deltas"]["joint_no_same_declared_leaf"]["joint_no_pair_count"] > 0
    assert summary["directional_deltas"]["materiality"]["status"].startswith("unavailable_runner")
    assert summary["latency"]["status"].startswith("unavailable_runner")
    inputs = json.loads((tmp_path / "analysis" / "analysis-input-manifest.json").read_text(encoding="utf-8"))
    assert len(inputs["accepted_runs"]) == 72
    assert all(len(row["files"]) == 4 for row in inputs["accepted_runs"])


def test_contract_and_case_files_are_plain_json():
    assert json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))["study_id"] == study.contract()["study_id"]
    assert len(json.loads((ROOT / "public-synthetic-cases.json").read_text(encoding="utf-8"))["cases"]) == 12


def test_external_root_guard_rejects_overlap_before_any_read(tmp_path):
    with pytest.raises(ValueError, match="roots overlap"):
        study.guard_external_roots({"parent": tmp_path, "child": tmp_path / "child"})


def test_snapshot_rejects_protocol_or_analyzer_binding_drift(snapshot):
    altered = deepcopy(snapshot)
    altered["protocol"]["repetitions"] = 4
    with pytest.raises(ValueError, match="program or protocol"):
        analyze._check_snapshot(altered)
    altered = deepcopy(snapshot)
    altered["executable_identity"]["python"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="executable/version"):
        analyze._check_snapshot(altered)
    altered = deepcopy(snapshot)
    altered["analysis_program"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="program or protocol"):
        analyze._check_snapshot(altered)


def test_contract_rejects_extra_or_relabelled_condition(monkeypatch):
    altered = deepcopy(study.contract())
    altered["conditions"].append(deepcopy(altered["conditions"][0]))
    monkeypatch.setattr(study, "contract", lambda: altered)
    with pytest.raises(ValueError, match="exact Sol/Grok"):
        study.validate()


def test_contract_rejects_schema_candidate_or_case_outcome_drift(monkeypatch):
    real_contract = study.contract
    altered = deepcopy(real_contract())
    altered["candidate_condition"]["rule"] = "different"
    monkeypatch.setattr(study, "contract", lambda: altered)
    with pytest.raises(ValueError, match="Candidate-condition"):
        study.validate()
    altered_cases = deepcopy(study.cases())
    altered_cases[0]["design_intent"] = "visible_defect"
    monkeypatch.setattr(study, "contract", real_contract)
    monkeypatch.setattr(study, "cases", lambda: altered_cases)
    with pytest.raises(ValueError, match="case identities or schema"):
        study.validate()


def test_run_rejects_normalized_verdict_identity_drift(monkeypatch, tmp_path, snapshot):
    case, condition = study.cases()[0], study.contract()["conditions"][0]
    run = write_complete_runner_run(tmp_path / "work", case, condition, 1)
    verdict = json.loads((run / "responses" / "batch-0001.json").read_text(encoding="utf-8"))["normalized_verdicts"][0]
    verdict["run_id"] = "wrong-run"
    monkeypatch.setattr(analyze.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([verdict], 1, None))
    monkeypatch.setattr(analyze.runner, "_load_completed", lambda *_args, **_kwargs: [verdict])
    with pytest.raises(ValueError, match="Normalized verdict identity"):
        analyze._run(tmp_path / "work", snapshot, case, "sol", 1)


def test_run_rejects_exact_quote_with_the_wrong_source_reference(monkeypatch, tmp_path, snapshot):
    case = study.cases()[0]
    condition = study.contract()["conditions"][0]
    run = write_complete_runner_run(tmp_path / "work", case, condition, 1)
    verdict = json.loads((run / "responses" / "batch-0001.json").read_text(encoding="utf-8"))["normalized_verdicts"][0]
    verdict["evidence"] = [{"reference": "context.md", "exact_quote": case["artifact"]}]
    monkeypatch.setattr(analyze.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([verdict], 1, None))
    monkeypatch.setattr(analyze.runner, "_load_completed", lambda *_args, **_kwargs: [verdict])
    monkeypatch.setattr(analyze.runner, "_rejected_records", lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match="source-specific frozen offset"):
        analyze._run(tmp_path / "work", snapshot, case, "sol", 1)


def test_run_tree_rejects_extra_condition_role(tmp_path, snapshot):
    write_full_run_tree(tmp_path / "work")
    extra = tmp_path / "work" / "runs" / "candidate" / study.cases()[0]["case_id"] / "run-01"
    extra.mkdir(parents=True)
    with pytest.raises(ValueError, match="exactly match"):
        analyze._validate_run_tree(tmp_path / "work", {case["case_id"]: case for case in study.cases()})


def test_complete_persisted_evidence_tree_is_accepted_end_to_end(tmp_path, snapshot):
    write_complete_runner_tree(tmp_path / "work")
    summary = analyze.analyze(FROZEN_PATH, tmp_path / "work", prepare_dispatch(tmp_path, snapshot), tmp_path / "analysis")
    assert summary["pair_count"] == 36
    assert summary["promotion"] == {"eligible": False, "evidence_class": "NON_PROMOTABLE", "reason": "trusted_external_runner_launch_receipt_required"}
    inputs = json.loads((tmp_path / "analysis" / "analysis-input-manifest.json").read_text(encoding="utf-8"))
    assert len(inputs["accepted_runs"]) == 72
    assert inputs["evidence_class"] == "DEVELOPMENT_SCREENING_FIXTURE"
    assert inputs["promotion"]["eligible"] is False
    assert all({"run.json", "verdicts.jsonl", "batch-0001.json", "batch-0001.prompt.txt.gz", "batch-0001.accepted-0001.message.txt"}.issubset({entry["relative_path"].split("/")[-1] for entry in row["files"]}) for row in inputs["accepted_runs"])


def test_analyzer_rejects_copied_run_bytes_with_duplicate_run_identity(tmp_path, snapshot):
    work = tmp_path / "work"
    write_complete_runner_tree(work)
    case_id = study.cases()[0]["case_id"]
    source = work / "runs" / "sol" / case_id / "run-01"
    copied = work / "runs" / "sol" / case_id / "run-02"
    shutil.rmtree(copied)
    shutil.copytree(source, copied)
    with pytest.raises(ValueError, match="duplicate or missing run_id"):
        analyze.analyze(FROZEN_PATH, work, prepare_dispatch(tmp_path, snapshot), tmp_path / "analysis")


def test_analyzer_rejects_replayed_grok_envelope_with_forged_unique_hashes(tmp_path, snapshot):
    work = tmp_path / "work"
    write_complete_runner_tree(work)
    case_id = study.cases()[0]["case_id"]
    source = work / "runs" / "grok" / case_id / "run-01"
    target = work / "runs" / "grok" / case_id / "run-02"
    source_envelope = next((source / "responses").glob("*.grok.envelope.json"))
    target_envelope = next((target / "responses").glob("*.grok.envelope.json"))
    target_envelope.write_bytes(source_envelope.read_bytes())
    checkpoint_path = target / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    provider = checkpoint["provider"]
    provider["session_id_sha256"] = hashlib.sha256(b"forged-session").hexdigest()
    provider["request_id_sha256"] = hashlib.sha256(b"forged-request").hexdigest()
    provider["provider_artifacts"]["grok_envelope"] = analyze.runner._provider_artifact(target, target_envelope)
    checkpoint_path.write_bytes(analyze.runner._json_bytes(checkpoint))
    with pytest.raises(ValueError, match="not derived from its bound envelope"):
        analyze.analyze(FROZEN_PATH, work, prepare_dispatch(tmp_path, snapshot), tmp_path / "analysis")


def test_run_rejects_config_shape_format_and_asymmetric_judges(monkeypatch, tmp_path, snapshot):
    case = study.cases()[0]
    sol, grok = study.contract()["conditions"]
    sol_run = write_complete_runner_run(tmp_path / "work", case, sol, 1)
    manifest = json.loads((sol_run / "run.json").read_text(encoding="utf-8"))
    manifest["configuration"]["unexpected_execution_switch"] = True
    manifest["config_sha256"] = hashlib.sha256(analyze.runner._json_bytes(manifest["configuration"])).hexdigest()
    (sol_run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    verdict = {"question_id": case["question_id"], "verdict": "YES", "evidence": [{"reference": "source.md", "exact_quote": case["artifact"]}]}
    monkeypatch.setattr(analyze.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([verdict], 1, None))
    monkeypatch.setattr(analyze.runner, "_load_completed", lambda *_args, **_kwargs: [verdict])
    monkeypatch.setattr(analyze.runner, "_rejected_records", lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match="unexpected or missing execution-affecting key"):
        analyze._run(tmp_path / "work", snapshot, case, "sol", 1)
    manifest["configuration"].pop("unexpected_execution_switch")
    manifest["format_version"] = 5
    manifest["config_sha256"] = hashlib.sha256(analyze.runner._json_bytes(manifest["configuration"])).hexdigest()
    (sol_run / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        analyze._run(tmp_path / "work", snapshot, case, "sol", 1)
    sol_configuration = make_manifest(case, sol, snapshot["case_commitments"][case["case_id"]])["configuration"]
    grok_configuration = make_manifest(case, grok, snapshot["case_commitments"][case["case_id"]])["configuration"]
    grok_configuration["batch_size"] = 2
    with pytest.raises(ValueError, match="asymmetric"):
        analyze._assert_matched_configuration({"configuration": sol_configuration}, {"configuration": grok_configuration})


def test_snapshot_rejects_runtime_omission_duplicate_or_extra(snapshot):
    for runtime in (
        snapshot["runtime"][1:],
        [*snapshot["runtime"], snapshot["runtime"][0]],
        [*snapshot["runtime"], {"relative_path": "extra.py", "bytes": 0, "sha256": "0" * 64}],
    ):
        altered = deepcopy(snapshot)
        altered["runtime"] = runtime
        with pytest.raises(ValueError, match="runtime binding"):
            analyze._check_snapshot(altered)


def test_checkpoint_rejects_rendered_prompt_v3_and_missing_provider(monkeypatch, tmp_path, snapshot):
    case = study.cases()[0]
    condition = study.contract()["conditions"][0]
    run = write_complete_runner_run(tmp_path / "work", case, condition, 1)
    checkpoint_path = run / "responses" / "batch-0001.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["format_version"] = 3
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="exact current V4"):
        analyze._checkpoint_record(run, case, "sol")
    checkpoint["format_version"] = 4
    checkpoint.pop("provider")
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="exact current V4"):
        analyze._checkpoint_record(run, case, "sol")
    checkpoint = json.loads((run / "responses" / "batch-0001.json").read_text(encoding="utf-8"))
    checkpoint["provider"] = {"command": ["codex"], "reported": {"model": condition["model"], "provider": "openai", "reasoning_effort": condition["reasoning"]}}
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"tampered", mtime=0))
    with pytest.raises(ValueError, match="prompt bytes or hash"):
        analyze._checkpoint_record(run, case, "sol")
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(study.rendered_prompt(case, condition).encode("utf-8"), mtime=0))
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["accepted_attempt"] = 2
    checkpoint["rejected_chain"] = {"count": 1, "head_sha256": "0" * 64}
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(ValueError, match="schedule binding"):
        analyze._checkpoint_record(run, case, "sol")


def test_prepare_binds_exact_disclosure_acknowledgement_and_live_zero_charge_proofs(tmp_path, snapshot):
    disclosure = study.dispatch_disclosure(snapshot)
    acknowledgement = {
        "format_version": 1,
        "acknowledged_by": "release owner",
        "acknowledgement": "I reviewed the exact destinations and transmitted public-synthetic artifacts.",
        "disclosure_sha256": hashlib.sha256(study.canonical(disclosure)).hexdigest(),
        "conditions_sha256": hashlib.sha256(study.canonical(snapshot["protocol"]["conditions"])).hexdigest(),
    }
    proofs = {
        "format_version": 1,
        "proofs": {
            condition["condition_id"]: {
                "provider": condition["provider"], "model": condition["model"], "checked_at": "2026-08-27T18:00:00Z",
                "proof_kind": "live_account_zero_charge_inspection", "evidence_reference": "owner-reviewed live account state", "paid_api": False,
                "no_payment_method": True, "no_paid_fallback": True, "no_hold_or_deposit": True, "no_billable_dispatch": True,
            }
            for condition in snapshot["protocol"]["conditions"]
        },
    }
    frozen_path = FROZEN_PATH
    ack_path, proof_path = tmp_path / "owner-ack.json", tmp_path / "zero-charge.json"
    ack_path.write_text(json.dumps(acknowledgement), encoding="utf-8")
    proof_path.write_text(json.dumps(proofs), encoding="utf-8")
    prepared = study.prepare(frozen_path, ack_path, proof_path, tmp_path / "prepared")
    assert prepared["provider_calls"] == 0
    assert prepared["status"] == "prepared_provisional_dispatch_disabled"
    assert prepared["evidence_class"] == "DEVELOPMENT_SCREENING_FIXTURE"
    assert prepared["promotion"]["eligible"] is False
    persisted_disclosure = json.loads((tmp_path / "prepared" / "dispatch-disclosure.json").read_text(encoding="utf-8"))
    assert persisted_disclosure["entries"][0]["artifact"]["utf8"]
    assert persisted_disclosure["entries"][0]["context"]["utf8"]
    assert persisted_disclosure["entries"][0]["rendered_prompt"]["utf8"]
    assert persisted_disclosure["entries"][0]["response_schema"]["utf8"]
    assert persisted_disclosure["route_response_schemas"]["sol"]["utf8"] == analyze.runner._json_bytes(analyze.runner._response_schema()).decode("utf-8")
    assert persisted_disclosure["route_response_schemas"]["grok"]["utf8"] == analyze.runner._json_bytes(analyze.runner._response_schema()).decode("utf-8")
    assert persisted_disclosure["grok_system_prompt_override"]["utf8"] == study.GROK_SYSTEM_PROMPT_OVERRIDE
    assert persisted_disclosure["entries"][0]["batch_attempts"] == 1
    assert persisted_disclosure["entries"][0]["retry_semantics"] == "single_attempt_no_validation_feedback"
    acknowledgement["acknowledged_by"] = "placeholder"
    ack_path.write_text(json.dumps(acknowledgement), encoding="utf-8")
    with pytest.raises(ValueError, match="non-placeholder"):
        study._validate_owner_acknowledgement(acknowledgement, disclosure, snapshot)


def test_grok_disclosure_override_matches_captured_runtime_argv(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **_kwargs):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stderr="",
            stdout=json.dumps({
                "modelUsage": {"grok-4.6-build": {}}, "sessionId": "fixture-session", "requestId": "fixture-request",
                "stopReason": "end_turn", "num_turns": 1, "structuredOutput": {"verdicts": []},
            }),
        )

    monkeypatch.setattr(analyze.runner, "_grok_cli_version", lambda **_kwargs: "fixture-cli")
    monkeypatch.setattr(analyze.runner.uuid, "uuid4", lambda: "fixture-session")
    monkeypatch.setattr(analyze.runner.subprocess, "run", fake_run)
    analyze.runner._call_grok(
        executable="grok", model="grok-4.6", reasoning="high", prompt="fixture prompt", output_dir=tmp_path,
        response_schema=ROOT.parents[1] / "schema" / "hbq_judge_response.schema.json", batch_number=1, timeout=1,
        allow_unattested_reasoning=True,
    )
    arguments = captured["command"]
    override_index = arguments.index("--system-prompt-override")
    assert arguments[override_index + 1] == study.GROK_SYSTEM_PROMPT_OVERRIDE


def test_runner_dispatch_path_uses_disclosed_canonical_schema_for_sol_and_grok(monkeypatch, tmp_path):
    case = study.cases()[0]
    artifact = tmp_path / "source.md"
    artifact.write_text(case["artifact"], encoding="utf-8")
    raw_response = json.dumps({"verdicts": [{"question_id": case["question_id"], "verdict": "YES", "confidence": 0.9, "evidence": [{"kind": "exact_quote", "reference": "source.md", "exact_quote": case["artifact"], "summary": None}], "note": "fixture"}]})
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if "--output-last-message" in command:
            output = Path(command[command.index("--output-last-message") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(raw_response, encoding="utf-8")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({"modelUsage": {"grok-4.6-build": {}}, "sessionId": "dispatch-session", "requestId": "dispatch-request", "stopReason": "end_turn", "num_turns": 1, "structuredOutput": json.loads(raw_response)}))

    monkeypatch.setattr(analyze.runner.subprocess, "run", fake_run)
    monkeypatch.setattr(analyze.runner, "_codex_reported_settings", lambda _stderr: {"model": "gpt-5.6-sol", "provider": "openai", "reasoning_effort": "high"})
    monkeypatch.setattr(analyze.runner, "_grok_cli_version", lambda **_kwargs: "fixture-cli")
    monkeypatch.setattr(analyze.runner.uuid, "uuid4", lambda: "dispatch-session")
    for condition in study.contract()["conditions"]:
        analyze.runner.run_judge(
            artifact_path=artifact, bundle_id=case["bundle_id"], provider=condition["provider"], model=condition["model"],
            output_dir=tmp_path / condition["condition_id"], registry=ROOT.parents[1] / "registry" / "all_modules.json",
            bundles=ROOT.parents[1] / "bundles" / "all_bundles.json", question_ids=[case["question_id"]], batch_size=1,
            batch_attempts=1, reasoning=condition["reasoning"], artifact_id=case["case_id"],
            judge_id=f"{condition['provider']}:{condition['model']}", allow_remote=True,
            allow_unattested_reasoning=condition.get("allow_unattested_reasoning", False),
        )
    canonical_schema = analyze.runner._json_bytes(analyze.runner._response_schema()).decode("utf-8")
    codex_command = next(command for command in commands if "--output-schema" in command)
    assert Path(codex_command[codex_command.index("--output-schema") + 1]).read_text(encoding="utf-8") == canonical_schema
    grok_command = next(command for command in commands if "--json-schema" in command)
    assert grok_command[grok_command.index("--json-schema") + 1] == canonical_schema
