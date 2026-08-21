from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import shutil
import sys
import csv
from pathlib import Path

import pytest

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle, score_bundle
from hbqrs.paths import bundles_path, registry_path
from hbqrs.runner import EVIDENCE_NORMALIZATION_POLICY, VALIDATION_FEEDBACK_POLICY, _feedback_for_rejection, _json_bytes, _normalize_batch, _question_payload, _render_prompt
from hbqrs.weights import materialize_weight_profile

ROOT = Path(__file__).resolve().parents[1] / "evaluation-results" / "hbq-human-alignment-v3"
SUPPLEMENTAL_ROOT = ROOT.parent / "hbq-human-alignment-supplemental-providers-v1"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def module(name: str, filename: str):
    return _load_module(name, ROOT / filename)


study = module("hanna_v3_study", "study.py")
sys.modules["study"] = study
analysis = module("hanna_v3_analysis", "analyze_study.py")
sys.modules["analyze_study"] = analysis
run_study = module("hanna_v3_run", "run_study.py")
gate_module = module("hanna_v3_gate", "confirmation_gate.py")


@pytest.fixture(autouse=True)
def _bind_v3_module_aliases(monkeypatch):
    monkeypatch.setitem(sys.modules, "study", study)
    monkeypatch.setitem(sys.modules, "analyze_study", analysis)


def _load_supplemental_analyzer() -> object:
    previous_study = sys.modules.get("study")
    previous_analysis = sys.modules.get("analyze_study")
    supplemental_study = _load_module("hanna_v3_mixed_order_supplemental_study", SUPPLEMENTAL_ROOT / "study.py")
    sys.modules["study"] = supplemental_study
    try:
        return _load_module("hanna_v3_mixed_order_supplemental_analysis", SUPPLEMENTAL_ROOT / "analyze_study.py")
    finally:
        if previous_study is None:
            sys.modules.pop("study", None)
        else:
            sys.modules["study"] = previous_study
        if previous_analysis is None:
            sys.modules.pop("analyze_study", None)
        else:
            sys.modules["analyze_study"] = previous_analysis


def _fingerprint(path: Path) -> dict:
    return {"name": path.name, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _fixture(tmp_path: Path, *, repaired: bool = False, retry: bool = False, recovered: bool = False, session: str = "session-a"):
    item = study.HannaItem("hanna-x", "999", "Generated", "prompt text", "story text", {key: (3, 3, 3) for key in study.RATING_DIMENSIONS})
    inputs = tmp_path / "inputs" / "development" / item.item_id
    inputs.mkdir(parents=True)
    (inputs / "source.md").write_text(item.story, encoding="utf-8")
    (inputs / "prompt.md").write_text(item.prompt, encoding="utf-8")
    study.write_json(inputs / "task-contract.json", study.make_task_contract(item))
    task_contract = json.loads((inputs / "task-contract.json").read_text(encoding="utf-8"))
    modules, bundle, weight_profile = materialize_weight_profile(load_modules(registry_path()), resolve_bundle(load_bundles(bundles_path()), "prose.short_story"), None)
    compiled = compile_bundle(modules, bundle, task_contract=task_contract)
    records = sorted(compiled_questions(compiled), key=lambda value: {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}.get(value.get("role"), 99))
    ids = [row["question"]["id"] for row in records]
    runtime_files = study._runtime_files()
    prompt_fingerprint = next(value for key, value in runtime_files.items() if key.endswith("prompts/judge/BINARY_EVALUATION_PROMPT.md"))
    schema_fingerprint = next(value for key, value in runtime_files.items() if key.endswith("schema/hbq_judge_response.schema.json"))
    source, prompt, contract = _fingerprint(inputs / "source.md"), _fingerprint(inputs / "prompt.md"), _fingerprint(inputs / "task-contract.json")
    configuration = {
        "artifact": {**source, "path": str(inputs / "source.md")}, "contexts": [{**prompt, "path": str(inputs / "prompt.md")}],
        "task_contract": {**contract, "path": str(inputs / "task-contract.json"), "contract_id": "hanna"},
        "weight_profile": weight_profile, "bundle_id": "prose.short_story", "bundle_version": bundle["version"], "question_ids": ids,
        "provider": "codex", "model": "gpt-5.6-sol", "endpoint": None, "api_key_env": None, "temperature": None,
        "allow_model_mismatch": None, "reasoning": "high", "codex_bin": "codex", "batch_size": 32,
        "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1",
        "evidence_normalization_policy": EVIDENCE_NORMALIZATION_POLICY, "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY,
        "artifact_id": item.item_id, "judge_id": "codex:gpt-5.6-sol", "strict_ai": False,
        "prompts": [{**prompt_fingerprint, "path": "binary"}], "response_schema": {**schema_fingerprint, "path": "schema"},
        "questions_sha256": hashlib.sha256(_json_bytes(_question_payload(records))).hexdigest(), "compiled_bundle_sha256": hashlib.sha256(_json_bytes(compiled)).hexdigest(),
    }
    folder = tmp_path / "runs" / "development" / item.item_id / "run-01"
    (folder / "responses").mkdir(parents=True)
    run_id = "run-synthetic"
    study.write_json(folder / "run.json", {"format_version": 3, "run_id": run_id, "created_at": "x", "config_sha256": hashlib.sha256(_json_bytes(configuration)).hexdigest(), "remote": True, "configuration": configuration})
    previous, completed = None, []
    for batch, offset in enumerate(range(0, len(ids), 32), 1):
        chunk = ids[offset:offset + 32]
        quote = "not in source" if repaired and batch == 1 else item.story
        payload = {"verdicts": [{"question_id": question_id, "verdict": "YES", "confidence": 1.0, "evidence": [{"kind": "exact_quote", "reference": "story", "exact_quote": quote, "summary": None}], "note": ""} for question_id in chunk]}
        raw = json.dumps(payload, ensure_ascii=False)
        audit = []
        normalized = _normalize_batch(json.loads(raw), expected_ids=chunk, artifact_id=item.item_id, bundle_id="prose.short_story", judge_id="codex:gpt-5.6-sol", run_id=run_id, artifact_text=item.story, context_texts=[item.prompt], normalization_policy=EVIDENCE_NORMALIZATION_POLICY, repair_audit=audit)
        base_prompt = _render_prompt(
            binary_prompt=(Path(__file__).resolve().parents[1] / "prompts" / "judge" / "BINARY_EVALUATION_PROMPT.md").read_text(encoding="utf-8"),
            artifact={"name": source["name"], "text": item.story}, contexts=[{"name": prompt["name"], "text": item.prompt}],
            bundle_id="prose.short_story", artifact_id=item.item_id, questions=records[offset:offset + 32],
        )
        base_bytes = base_prompt.encode("utf-8")
        checkpoint_prompt = folder / "responses" / f"batch-{batch:04d}.prompt.txt.gz"
        checkpoint_prompt.write_bytes(gzip.compress(base_bytes, mtime=0))
        rejected_chain = {"count": 0, "head_sha256": None}
        accepted_attempt = 1
        feedback = None
        effective = base_prompt
        recovered_from = None
        if retry and batch == 1:
            rejected_dir = folder / "responses" / "rejected" / f"batch-{batch:04d}"
            rejected_dir.mkdir(parents=True)
            rejection = {"format_version": 4, "batch": batch, "attempt": 1, "sequence": 1, "previous_rejected_sha256": None, "stage": "model_output", "retry_policy": {"batch_attempts": 3}, "prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "base_prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "effective_prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY, "validation_feedback": None, "raw_content": {"encoding": "utf-8", "text": "{}", "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}, "provider": None, "error": {"class": "HBQError", "message": "fixture rejection"}}
            rejection_path = rejected_dir / "attempt-0001.json"
            study.write_json(rejection_path, rejection)
            rejected_chain = {"count": 1, "head_sha256": hashlib.sha256(rejection_path.read_bytes()).hexdigest()}
            effective, feedback = _feedback_for_rejection(base_prompt=base_prompt, base_prompt_sha256=hashlib.sha256(base_bytes).hexdigest(), previous_rejection=(rejection_path, rejection))
            accepted_attempt = 2
        if recovered and batch == 1:
            rejected_dir = folder / "responses" / "rejected" / f"batch-{batch:04d}"
            rejected_dir.mkdir(parents=True, exist_ok=True)
            first = {"format_version": 4, "batch": batch, "attempt": 1, "sequence": 1, "previous_rejected_sha256": None, "stage": "model_output", "retry_policy": {"batch_attempts": 3}, "prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "base_prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "effective_prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY, "validation_feedback": None, "raw_content": {"encoding": "utf-8", "text": "{}", "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}, "provider": None, "error": {"class": "HBQError", "message": "first fixture rejection"}}
            first_path = rejected_dir / "attempt-0001.json"
            study.write_json(first_path, first)
            effective, feedback = _feedback_for_rejection(base_prompt=base_prompt, base_prompt_sha256=hashlib.sha256(base_bytes).hexdigest(), previous_rejection=(first_path, first))
            rejection = {"format_version": 4, "batch": batch, "attempt": 2, "sequence": 2, "previous_rejected_sha256": hashlib.sha256(first_path.read_bytes()).hexdigest(), "stage": "model_output", "retry_policy": {"batch_attempts": 3}, "prompt_sha256": hashlib.sha256(effective.encode()).hexdigest(), "base_prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "effective_prompt_sha256": hashlib.sha256(effective.encode()).hexdigest(), "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY, "validation_feedback": feedback, "raw_content": {"encoding": "utf-8", "text": raw, "bytes": len(raw.encode()), "sha256": hashlib.sha256(raw.encode()).hexdigest()}, "provider": None, "error": {"class": "HBQError", "message": "strict fixture rejection"}}
            rejection_path = rejected_dir / "attempt-0002.json"
            study.write_json(rejection_path, rejection)
            rejected_chain = {"count": 2, "head_sha256": hashlib.sha256(rejection_path.read_bytes()).hexdigest()}
            accepted_attempt = 2
            recovered_from = {"path": rejection_path.relative_to(folder).as_posix(), "attempt": 2, "sha256": hashlib.sha256(rejection_path.read_bytes()).hexdigest()}
        accepted = folder / "responses" / f"batch-{batch:04d}.accepted-0001.message.txt"
        accepted.write_text(raw, encoding="utf-8")
        provider_artifact = folder / "responses" / f"batch-{batch:04d}.provider.txt"
        provider_artifact.write_text("provider-artifact", encoding="utf-8")
        completed.extend(normalized)
        record = {"format_version": 4, "batch": batch, "retry_policy": {"batch_attempts": 3}, "accepted_attempt": accepted_attempt, "question_ids": chunk, "prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "base_prompt_sha256": hashlib.sha256(base_bytes).hexdigest(), "effective_prompt_sha256": hashlib.sha256(effective.encode()).hexdigest(), "validation_feedback_policy": VALIDATION_FEEDBACK_POLICY, "validation_feedback": feedback, "normalization_policy": EVIDENCE_NORMALIZATION_POLICY, "normalization_audit": audit, "response_sha256": hashlib.sha256(raw.encode()).hexdigest(), "response_artifact": {"path": accepted.relative_to(folder).as_posix(), "bytes": len(raw.encode()), "sha256": hashlib.sha256(raw.encode()).hexdigest()}, "rejected_chain": rejected_chain, "previous_checkpoint_sha256": previous, "verdicts_sha256": hashlib.sha256(analysis.verdict_bytes(completed)).hexdigest(), "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"{session}-{batch}"}, "provider_artifacts": {"metadata": {"path": provider_artifact.relative_to(folder).as_posix(), "bytes": provider_artifact.stat().st_size, "sha256": hashlib.sha256(provider_artifact.read_bytes()).hexdigest()}}}, "normalized_verdicts": normalized}
        if recovered_from is not None:
            record["recovered_from_rejected"] = recovered_from
        checkpoint = folder / "responses" / f"batch-{batch:04d}.json"
        study.write_json(checkpoint, record)
        previous = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    (folder / "verdicts.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in completed), encoding="utf-8")
    score = score_bundle(modules, bundle, completed, artifact_id=item.item_id, task_contract=task_contract)
    score["weight_profile"] = weight_profile
    study.write_json(folder / "score.json", score)
    row = {"item_id": item.item_id, "model": "Generated", "quartile": 1, "prompt_group_id": "prompt-x", "story_sha256": item.story_sha256, "prompt_sha256": item.prompt_sha256, "external_input": {"source.md": source, "prompt.md": prompt, "task-contract.json": contract}}
    frozen = {"study_id": "fixture", "provider": {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "fresh_session": True}, "runner": {"bundle_id": "prose.short_story", "batch_size": 32, "batch_attempts": 3, "weight_profile": study.load_contract()["runner"]["weight_profile"]}, "question_ids": ids, "runtime_files": runtime_files, "runtime_sha256": study._runtime_sha256(runtime_files), "partitions": {"development": [row]}, "repeatability": {"repetitions": 5, "items": [{"item_id": item.item_id, "model": "Generated", "partition": "development"}]}}
    return frozen, row, folder


def _rewrite_manifest(folder: Path, mutate) -> None:
    manifest = json.loads((folder / "run.json").read_text(encoding="utf-8"))
    mutate(manifest["configuration"])
    manifest["config_sha256"] = hashlib.sha256(_json_bytes(manifest["configuration"])).hexdigest()
    study.write_json(folder / "run.json", manifest)


def _semantic_development_output(tmp_path: Path, frozen: dict) -> Path:
    output = tmp_path / "development-analysis"
    output.mkdir()
    rows = frozen["partitions"]["development"]
    items = [{"item_id": row["item_id"], "story_id": row["story_id"]} for row in rows]
    (output / "items.jsonl").write_text("".join(json.dumps(item) + "\n" for item in items), encoding="utf-8")
    dimensions = {key: {} for key in study.RATING_DIMENSIONS}
    ordinal = {key: {} for key in study.RATING_DIMENSIONS}
    summary = {"format_version": 3, "study_id": frozen["study_id"], "phase": "development", "study_contract_sha256": frozen["study_contract_sha256"], "runtime_sha256": frozen["runtime_sha256"], "mapping_sets": frozen["mapping_sets"], "dataset": frozen["dataset"], "item_count": 88, "primary_generated_only": {"item_count": 80, "dimensions": dimensions, "macro_spearman": {}, "ordinal_human_agreement": ordinal}, "secondary_all_11": {"item_count": 88, "dimensions": dimensions, "ordinal_human_agreement": ordinal}, "source_model_strata": {f"M{number}": {"dimensions": dimensions} for number in range(11)}, "published_human_agreement_context": frozen["protocol"]["published_human_agreement_context"]}
    study.write_json(output / "summary.json", summary)
    files = {path.relative_to(output).as_posix(): {"bytes": path.stat().st_size, "sha256": study.sha256_path(path)} for path in sorted(output.rglob("*")) if path.is_file()}
    study.write_json(output / "manifest.json", {"format_version": 3, "study_id": frozen["study_id"], "phase": "development", "study_contract_sha256": frozen["study_contract_sha256"], "runtime_sha256": frozen["runtime_sha256"], "package_commit": frozen["package_commit"], "files": files})
    return output


def _synthetic_hanna_data(path: Path) -> None:
    fields = ["Story ID", "Prompt", "Human", "Story", "Model", *study.RATING_DIMENSIONS, "Worker ID", "Assignment ID"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for prompt_group in range(96):
            for model in range(11):
                for rater in range(3):
                    writer.writerow({"Story ID": str(prompt_group * 100 + model), "Prompt": f"prompt-{prompt_group}", "Human": "same", "Story": f"story-{prompt_group}-{model}", "Model": f"M{model}", **{key: str(prompt_group % 5 + 1) for key in study.RATING_DIMENSIONS}, "Worker ID": str(rater), "Assignment ID": f"assignment-{prompt_group}-{model}-{rater}"})


def _selection_fixture() -> tuple[dict, dict]:
    groups = {partition: [f"{index + offset:064x}" for index in range(48)] for partition, offset in (("development", 0), ("confirmatory", 48))}
    partitions = {}
    for partition in ("development", "confirmatory"):
        rows = []
        for model in range(11):
            for quartile in range(1, 5):
                for rank in range(1, 3):
                    index = len(rows) % 48
                    prompt_sha = groups[partition][index]
                    rows.append({"item_id": f"{partition}-{model}-{quartile}-{rank}", "story_id": str(len(rows)), "model": f"M{model}", "quartile": quartile, "selected_rank": rank, "prompt_sha256": prompt_sha, "prompt_group_id": f"prompt-{prompt_sha[:16]}"})
        partitions[partition] = rows
    return partitions, groups


def test_v3_contract_and_prompt_disjoint_selection():
    contract = study.load_contract()
    assert contract["supersedes"]["study_id"] == "hbq-human-alignment-v2"
    assert contract["human_ratings_policy"].startswith("Use only already-published")
    assert contract["selection"]["prompt_groups"] == 96 and contract["runner"]["batch_attempts"] == 3


def test_v4_repaired_evidence_and_provider_artifact_are_replayable(tmp_path):
    frozen, row, _ = _fixture(tmp_path, repaired=True)
    verdicts, score = analysis.verify_run(tmp_path, frozen, "development", row, 1)
    assert len(verdicts) == 179 and score["provenance"]["checkpoint_version"] == 4
    assert verdicts[0]["evidence"][0] == {"reference": "story", "summary": "not in source"}


def test_v4_retry_feedback_and_recovery_are_bound(tmp_path):
    frozen, row, _ = _fixture(tmp_path, retry=True)
    analysis.verify_run(tmp_path, frozen, "development", row, 1)
    frozen, row, _ = _fixture(tmp_path / "recovered", recovered=True, repaired=True)
    analysis.verify_run(tmp_path / "recovered", frozen, "development", row, 1)


def test_v4_tamper_rejections(tmp_path):
    frozen, row, folder = _fixture(tmp_path, retry=True)
    rejected = folder / "responses" / "rejected" / "batch-0001" / "attempt-0001.json"
    value = json.loads(rejected.read_text(encoding="utf-8"))
    value["validation_feedback"] = {"bad": True}
    study.write_json(rejected, value)
    with pytest.raises(ValueError, match="provenance"):
        analysis.verify_run(tmp_path, frozen, "development", row, 1)


def test_v4_rejects_provider_artifact_and_score_tampering(tmp_path):
    frozen, row, folder = _fixture(tmp_path)
    analysis.verify_run(tmp_path, frozen, "development", row, 1)
    provider_artifact = folder / "responses" / "batch-0001.provider.txt"
    provider_artifact.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        analysis.verify_run(tmp_path, frozen, "development", row, 1)
    provider_artifact.write_text("provider-artifact", encoding="utf-8")
    score = json.loads((folder / "score.json").read_text(encoding="utf-8"))
    score["status"] = "TAMPERED"
    study.write_json(folder / "score.json", score)
    with pytest.raises(ValueError, match="Deterministic score"):
        analysis.verify_run(tmp_path, frozen, "development", row, 1)


def test_v4_rejects_forged_identity_weight_prompt_and_extra_context(tmp_path):
    frozen, row, folder = _fixture(tmp_path)
    _rewrite_manifest(folder, lambda config: config.update({"artifact_id": "forged"}))
    with pytest.raises(ValueError, match="identity"):
        analysis.verify_run(tmp_path, frozen, "development", row, 1)
    frozen, row, folder = _fixture(tmp_path / "bundle")
    _rewrite_manifest(folder, lambda config: config.update({"bundle_version": "forged", "judge_id": "forged"}))
    with pytest.raises(ValueError, match="identity"):
        analysis.verify_run(tmp_path / "bundle", frozen, "development", row, 1)
    frozen, row, folder = _fixture(tmp_path / "weight")
    _rewrite_manifest(folder, lambda config: config["weight_profile"].update({"identity": False}))
    with pytest.raises(ValueError, match="weight profile"):
        analysis.verify_run(tmp_path / "weight", frozen, "development", row, 1)
    frozen, row, folder = _fixture(tmp_path / "effective-weight")
    _rewrite_manifest(folder, lambda config: config["weight_profile"]["effective"].update({"domain_weights": [{"domain_id": "forged", "effective_points": 100.0}]}))
    with pytest.raises(ValueError, match="weight profile"):
        analysis.verify_run(tmp_path / "effective-weight", frozen, "development", row, 1)
    frozen, row, folder = _fixture(tmp_path / "prompt")
    prompt = folder / "responses" / "batch-0001.prompt.txt.gz"
    prompt.write_bytes(gzip.compress(b"forged prompt", mtime=0))
    with pytest.raises(ValueError, match="exact frozen batch"):
        analysis.verify_run(tmp_path / "prompt", frozen, "development", row, 1)
    frozen, row, folder = _fixture(tmp_path / "context")
    _rewrite_manifest(folder, lambda config: config["contexts"].append(dict(config["contexts"][0])))
    with pytest.raises(ValueError, match="exactly one"):
        analysis.verify_run(tmp_path / "context", frozen, "development", row, 1)


def test_fresh_session_rejects_reuse_inside_one_run(tmp_path):
    frozen, row, folder = _fixture(tmp_path)
    final = folder / "responses" / "batch-0006.json"
    record = json.loads(final.read_text(encoding="utf-8"))
    record["provider"]["reported"]["session_id"] = "session-a-5"
    study.write_json(final, record)
    with pytest.raises(ValueError, match="unique provider sessions"):
        analysis.verify_phase_runs(tmp_path, frozen, "development")


def test_frozen_protocol_projection_rejects_contract_governed_tampering(tmp_path, monkeypatch):
    contract = study.load_contract()
    runtime = study._runtime_files()
    partitions, groups = _selection_fixture()
    metadata = {study.CSV_NAME: {"sha256": contract["dataset"]["csv_sha256"], "bytes": 13219167}, study.LICENSE_NAME: {"sha256": contract["dataset"]["license_sha256"], "bytes": 1065}}
    frozen = {"format_version": 3, "study_id": contract["study_id"], "frozen_before_execution": True, "study_contract_sha256": study.sha256_path(ROOT / "study-contract.json"), "v2_contract_sha256": study.sha256_path(ROOT.parent / "hbq-human-alignment-v2" / "study-contract.json"), "protocol": study.protocol_projection(contract), "protocol_sha256": study.protocol_sha256(contract), "dataset": {**contract["dataset"], "verified_files": metadata}, "selection": contract["selection"], "provider": contract["provider"], "runner": contract["runner"], "repeatability": {**contract["repeatability"], "items": study.derived_repeatability_items(partitions, contract)}, "mapping_sets": study.mapping_sets(), "mapping_sets_sha256": study.sha256_bytes(study.canonical_json(study.mapping_sets())), "package_commit": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT.parents[1], text=True).strip(), "runtime_files": runtime, "runtime_sha256": study._runtime_sha256(runtime), "question_ids": study.compiled_question_ids(), "partitions": partitions, "prompt_partitions": groups, "selection_sha256": study.validate_selection(partitions, groups, contract)}
    monkeypatch.setattr(study, "validate_external_inputs", lambda work, value: None)
    study.write_json(tmp_path / "frozen-run-contract.json", frozen)
    assert study.validate_frozen_contract(tmp_path)["protocol_sha256"] == frozen["protocol_sha256"]
    for path, mutate in (("provider", lambda value: value.update({"model": "forged"})), ("runner", lambda value: value.update({"batch_attempts": 9, "maximum_workers": 9})), ("selection", lambda value: value.update({"seed": 1})), ("repeatability", lambda value: value.update({"repetitions": 9}))):
        changed = json.loads(json.dumps(frozen))
        mutate(changed[path])
        study.write_json(tmp_path / "frozen-run-contract.json", changed)
        with pytest.raises(ValueError, match="canonical v3 protocol|projection"):
            study.validate_frozen_contract(tmp_path)
    changed = json.loads(json.dumps(frozen))
    changed["dataset"]["verified_files"][study.CSV_NAME]["sha256"] = "0" * 64
    study.write_json(tmp_path / "frozen-run-contract.json", changed)
    with pytest.raises(ValueError, match="dataset provenance"):
        study.validate_frozen_contract(tmp_path)


def test_prepare_then_validate_preserves_derived_repeatability_items(tmp_path, monkeypatch):
    _synthetic_hanna_data(tmp_path / study.CSV_NAME)
    contract = study.load_contract()
    metadata = {study.CSV_NAME: {"sha256": contract["dataset"]["csv_sha256"], "bytes": 13219167}, study.LICENSE_NAME: {"sha256": contract["dataset"]["license_sha256"], "bytes": 1065}}
    monkeypatch.setattr(study, "fetch_or_verify_dataset", lambda data, fetch=False: metadata)
    frozen = study.freeze_external_work(tmp_path, tmp_path / "work")
    assert len(frozen["repeatability"]["items"]) == 11
    assert study.validate_frozen_contract(tmp_path / "work")["repeatability"]["items"] == frozen["repeatability"]["items"]
    changed = json.loads(json.dumps(frozen))
    changed["dataset"]["verified_files"][study.CSV_NAME]["bytes"] += 1
    study.write_json(tmp_path / "work" / "frozen-run-contract.json", changed)
    with pytest.raises(ValueError, match="frozen verified metadata"):
        study.validate_dataset_binding(tmp_path, changed)


def test_repeatability_rejects_session_reuse_and_confirmation_gate_binds_v3_hashes(tmp_path, monkeypatch):
    frozen, row, folder = _fixture(tmp_path)
    for number in range(1, 6):
        destination = tmp_path / "runs" / "repeatability" / row["item_id"] / f"run-{number:02d}"
        shutil.copytree(folder, destination)
    with pytest.raises(ValueError, match="Fresh-session"):
        analysis.verify_phase_runs(tmp_path, frozen, "repeatability")
    contract = study.load_contract()
    rows = [{"item_id": f"hanna-{number}", "story_id": str(number), "model": f"M{number % 11}"} for number in range(88)]
    frozen.update({"study_id": contract["study_id"], "study_contract_sha256": study.sha256_path(ROOT / "study-contract.json"), "package_commit": "commit", "mapping_sets": study.mapping_sets(), "mapping_sets_sha256": study.sha256_bytes(study.canonical_json(study.mapping_sets())), "protocol": study.protocol_projection(contract), "runtime_sha256": "runtime", "dataset": {**contract["dataset"], "verified_files": {}}, "partitions": {"development": rows}, "selection": contract["selection"]})
    study.write_json(tmp_path / "frozen-run-contract.json", frozen)
    development = _semantic_development_output(tmp_path, frozen)
    monkeypatch.setattr(gate_module, "validate_frozen_contract", lambda work: frozen)
    monkeypatch.setattr(analysis, "verify_phase_runs", lambda work, contract, phase: None)
    gate_module.create_gate(tmp_path, development)
    supplemental_analysis = _load_supplemental_analyzer()
    assert supplemental_analysis is not analysis
    assert sys.modules["analyze_study"] is analysis
    run_study.gate(tmp_path, frozen)
    (development / "summary.json").write_text("tamper", encoding="utf-8")
    with pytest.raises(ValueError, match="hashes"):
        run_study.gate(tmp_path, frozen)
