from __future__ import annotations

import importlib.util
import hashlib
import json
import gzip
from pathlib import Path

import pytest

from jsonschema import Draft202012Validator

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v2"


def _module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_contract_preflight_freezes_source_assets_and_runtime() -> None:
    runner = _module("run_study")
    analysis = _module("analyze_study")
    contract, source = runner.preflight()
    assert source.name == "source.md"
    assert contract["repetitions"] == 5
    assert contract["provider"]["model"] == "gpt-5.6-sol"
    assert contract["provider"]["reasoning"] == "high"
    assert contract["hbq_runtime"]["batch_size"] == 256
    assert set(contract["asset_hashes"]) >= {"binary_prompt", "response_schema", "verdict_schema", "score_report_schema", "runner", "structured_runner", "scoring_core", "paths", "study_runner", "study_analyzer"}
    positions = {arm["arm_id"]: [] for arm in contract["arms"]}
    for block in contract["schedule"]["blocks"]:
        assert set(block) == set(positions)
        for position, arm_id in enumerate(block):
            positions[arm_id].append(position)
    assert max(max(values.count(position) for position in range(4)) - min(values.count(position) for position in range(4)) for values in positions.values()) == 1
    schedule_hash = runner.schedule_sha256(contract)
    assert analysis._schedule_sha256() == schedule_hash
    assert {event["schedule_sha256"] for event in runner._schedule_events(contract)} == {schedule_hash}


def test_native_schemas_are_strict_and_reject_wrong_criterion_range() -> None:
    schemas = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in (ROOT / "arms").glob("*.schema.json")}
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["additionalProperties"] is False
    naplan = schemas["naplan-narrative-2022.schema.json"]
    criteria = []
    maximums = {"audience": 6, "text_structure": 4, "ideas": 5, "character_and_setting": 4, "vocabulary": 5, "cohesion": 4, "paragraphing": 2, "sentence_structure": 6, "punctuation": 5, "spelling": 6}
    for key in maximums:
        criteria.append({"criterion_id": key, "score": 0, "exact_quote": "A", "observation": "Observed."})
    valid = {"method": "naplan_narrative_2022_research_implementation", "criteria": criteria, "total_score": 0, "overall_note": "A note."}
    assert not list(Draft202012Validator(naplan).iter_errors(valid))
    invalid = json.loads(json.dumps(valid))
    invalid["criteria"][6]["score"] = 3
    assert list(Draft202012Validator(naplan).iter_errors(invalid))


def test_analyzer_rejects_one_leaf_hbq_fixture_before_publish(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    work = tmp_path / "work"
    contract = json.loads((ROOT / "study-contract.json").read_text(encoding="utf-8"))
    configuration = {
        "artifact": {"sha256": contract["source"]["sha256"], "bytes": contract["source"]["bytes"]},
        "bundle_id": "prose.short_story",
        "question_ids": ["only.one.leaf"],
        "artifact_id": "the-part-that-arrives-first",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "reasoning": "high",
        "batch_size": 256,
        "strict_ai": True,
        "prompts": [{"sha256": contract["asset_hashes"]["binary_prompt"]}, {"sha256": contract["asset_hashes"]["judge_prefix"]}],
        "response_schema": {"sha256": contract["asset_hashes"]["response_schema"]},
    }
    _write_json(work / "hbq_short_story_one_batch" / "run-01" / "run.json", {"format_version": 1, "run_id": "fake", "config_sha256": hashlib.sha256(analysis._runner_json_bytes(configuration)).hexdigest(), "configuration": configuration})
    with pytest.raises(ValueError, match="exact frozen 178-question order"):
        analysis._validate_hbq_run(work, 1)


def test_analyzer_rejects_native_result_outside_frozen_range(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    arm = next(item for item in analysis.CONTRACT["arms"] if item["arm_id"] == "naplan_narrative_2022")
    criteria = [{"criterion_id": key, "score": 0, "exact_quote": "Mica always arrived first.", "observation": "x"} for key in ["audience", "text_structure", "ideas", "character_and_setting", "vocabulary", "cohesion", "paragraphing", "sentence_structure", "punctuation", "spelling"]]
    criteria[6]["score"] = 3
    _write_json(tmp_path / "work" / arm["arm_id"] / "run-01" / "result.json", {"method": "naplan_narrative_2022_research_implementation", "criteria": criteria, "total_score": 3, "overall_note": "x"})
    with pytest.raises(ValueError, match="violates frozen schema"):
        analysis._validate_native_run(tmp_path / "work", arm, 1)


def test_analyzer_refuses_existing_output_directory(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    output = tmp_path / "already-there"
    output.mkdir()
    with pytest.raises(ValueError, match="existing analysis output"):
        analysis.analyze(tmp_path / "work", output)


def test_schedule_journal_rejects_missing_reordered_and_duplicate_completions(tmp_path: Path) -> None:
    runner = _module("run_study")
    contract, _ = runner.preflight()
    journal, count = runner._prepare_journal(tmp_path, contract)
    assert count == 0
    plans = runner._schedule_events(contract)
    records = runner._read_journal(journal)
    assert records == plans
    with pytest.raises(ValueError, match="missing planned events"):
        _module("analyze_study")._validate_journal(tmp_path)
    runner._append_journal(journal, {**plans[1], "event": "completed", "run_binding_sha256": "a" * 64})
    with pytest.raises(ValueError, match="missing, duplicated, or reordered"):
        runner._prepare_journal(tmp_path, contract)
    duplicate_root = tmp_path / "duplicate"
    duplicate_journal, _ = runner._prepare_journal(duplicate_root, contract)
    completion = {**plans[0], "event": "completed", "run_binding_sha256": "b" * 64}
    runner._append_journal(duplicate_journal, completion)
    runner._append_journal(duplicate_journal, completion)
    with pytest.raises(ValueError, match="missing, duplicated, or reordered"):
        runner._prepare_journal(duplicate_root, contract)


def test_native_response_content_tampering_is_rejected(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    runner = _module("run_study")
    arm = next(item for item in analysis.CONTRACT["arms"] if item["arm_id"] == "oregon_narrative_2017")
    result = {"method": "oregon_narrative_2017_research_implementation", "traits": [{"trait_id": key, "score": 3, "exact_quote": "Mica always arrived first.", "observation": "x"} for key in ["ideas_and_content", "organization", "voice", "word_choice", "sentence_fluency", "conventions"]], "total_score": 18, "overall_note": "x"}
    schema = json.loads((ROOT / arm["schema"]).read_text(encoding="utf-8"))
    source = (ROOT / analysis.CONTRACT["source"]["path"]).read_text(encoding="utf-8")
    prompt = runner._prompt((ROOT / arm["prompt"]).read_text(encoding="utf-8"), source)
    configuration = {"format_version": 1, "name": "oregon_narrative_2017-run-01", "provider": "codex", "model": "gpt-5.6-sol", "endpoint": None, "api_key_env": None, "temperature": None, "allow_model_mismatch": None, "reasoning": "high", "codex_bin": "codex", "openai_structured_outputs": None, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "schema_sha256": hashlib.sha256(analysis._structured_json_bytes(schema)).hexdigest()}
    base = tmp_path / "work" / arm["arm_id"] / "run-01"
    _write_json(base / "pass.json", {"format_version": 1, "config_sha256": hashlib.sha256(analysis._structured_json_bytes(configuration)).hexdigest(), "configuration": configuration})
    _write_json(base / "response.schema.json", analysis._provider_response_schema(schema))
    _write_json(base / "result.json", result)
    content = json.dumps({**result, "overall_note": "tampered"})
    response = {"format_version": 1, "config_sha256": hashlib.sha256(analysis._structured_json_bytes(configuration)).hexdigest(), "prompt_sha256": configuration["prompt_sha256"], "schema_sha256": configuration["schema_sha256"], "content": content, "content_sha256": "0" * 64, "result_sha256": hashlib.sha256(analysis._structured_json_bytes(result)).hexdigest(), "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "session-1"}}}
    _write_json(base / "response.json", response)
    with pytest.raises(ValueError, match="content hash"):
        analysis._validate_native_run(tmp_path / "work", arm, 1)
    response["content_sha256"] = hashlib.sha256(content.encode()).hexdigest()
    _write_json(base / "response.json", response)
    with pytest.raises(ValueError, match="does not exactly match"):
        analysis._validate_native_run(tmp_path / "work", arm, 1)


def test_hbq_rejects_legacy_checkpoint_even_with_full_question_set(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    runner = _module("run_study")
    contract = analysis.CONTRACT
    bundle = __import__("hbqrs.core", fromlist=["compile_bundle"]).compile_bundle(__import__("hbqrs.core", fromlist=["load_modules"]).load_modules(__import__("hbqrs.paths", fromlist=["registry_path"]).registry_path()), __import__("hbqrs.core", fromlist=["resolve_bundle"]).resolve_bundle(__import__("hbqrs.core", fromlist=["load_bundles"]).load_bundles(__import__("hbqrs.paths", fromlist=["bundles_path"]).bundles_path()), "prose.short_story"))
    roles = {"hard_gate": 0, "domain": 1, "penalty": 2, "supplemental": 3}
    ids = [item["question"]["id"] for item in sorted(__import__("hbqrs.core", fromlist=["compiled_questions"]).compiled_questions(bundle), key=lambda item: roles.get(item["role"], 99))]
    configuration = {"artifact": {"sha256": contract["source"]["sha256"], "bytes": contract["source"]["bytes"]}, "bundle_id": "prose.short_story", "question_ids": ids, "artifact_id": "the-part-that-arrives-first", "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "batch_size": 256, "strict_ai": True, "prompts": [{"sha256": contract["asset_hashes"]["binary_prompt"]}, {"sha256": contract["asset_hashes"]["judge_prefix"]}], "response_schema": {"sha256": contract["asset_hashes"]["response_schema"]}}
    base = tmp_path / "work" / "hbq_short_story_one_batch" / "run-01"
    _write_json(base / "run.json", {"format_version": 1, "run_id": "run", "config_sha256": hashlib.sha256(analysis._runner_json_bytes(configuration)).hexdigest(), "configuration": configuration})
    verdicts = [{"artifact_id": "the-part-that-arrives-first", "bundle_id": "prose.short_story", "question_id": question_id, "verdict": "NO", "confidence": 0.9, "evidence": [{"reference": "story", "quote": "legacy"}], "judge_id": "codex:gpt-5.6-sol", "run_id": "run"} for question_id in ids]
    (base / "verdicts.jsonl").parent.mkdir(parents=True, exist_ok=True)
    (base / "verdicts.jsonl").write_bytes(analysis._verdicts_bytes(verdicts))
    prompt = b"legacy checkpoint"
    (base / "responses").mkdir(parents=True, exist_ok=True)
    (base / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(prompt, mtime=0))
    checkpoint = {"format_version": 1, "batch": 1, "question_ids": ids, "prompt_sha256": hashlib.sha256(prompt).hexdigest(), "response_sha256": "0" * 64, "previous_checkpoint_sha256": None, "verdicts_sha256": hashlib.sha256(analysis._verdicts_bytes(verdicts)).hexdigest(), "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "session-legacy"}}, "normalized_verdicts": verdicts}
    _write_json(base / "responses" / "batch-0001.json", checkpoint)
    with pytest.raises(ValueError, match="format-version-2"):
        analysis._validate_hbq_run(tmp_path / "work", 1)
