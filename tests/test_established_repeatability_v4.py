from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import _historical_runtime_compat as historical_runtime
from hbqrs.paths import book_root, bundles_path, registry_path
from hbqrs import longform_runner, runner as binary_runner


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v4"


def _raw_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(name: str):
    module = _raw_module(name)
    if name == "run_study":
        historical_runtime.allow_asset_manifest_runner_drift(module)
    elif name == "analyze_study":
        runner = _module("run_study")
        module._runner = lambda: runner
    return module


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _make_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, repaired_quote: bool = False, rejected_first: bool = False) -> tuple[object, Path]:
    analysis = _module("analyze_study")
    calls = 0

    def fake_codex(*, prompt: str, **kwargs):
        nonlocal calls
        calls += 1
        if rejected_first and calls == 1:
            return '{"not_verdicts":[]}', {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "rejected"}}
        ids = re.findall(r'"question_id"\s*:\s*"([^"]+)"', prompt)
        assert ids
        repair_call = 2 if rejected_first else 1
        evidence = {"kind": "exact_quote", "reference": "story", "exact_quote": "Mica always arrived frist." if repaired_quote and calls == repair_call else "Mica always arrived first.", "summary": None}
        content = json.dumps({"verdicts": [{"question_id": item, "verdict": "NO", "confidence": 0.9, "evidence": [evidence], "note": "fixture"} for item in ids]})
        return content, {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"accepted-{calls}"}}

    monkeypatch.setattr(binary_runner, "_call_codex", fake_codex)
    source = ROOT.parent / "source.md"
    output = tmp_path / "work" / "hbq_short_story_batch32" / "run-01"
    binary_runner.run_judge(artifact_path=source, bundle_id="prose.short_story", provider="codex", model="gpt-5.6-sol", output_dir=output, registry=registry_path(), bundles=bundles_path(), batch_size=32, batch_attempts=3, reasoning="high", allow_remote=True, artifact_id="the-part-that-arrives-first", strict_ai=True)
    return analysis, output


def test_preflight_hashes_schedule_and_exact_predecessor() -> None:
    with pytest.raises(ValueError, match="Frozen asset changed: runner"):
        _raw_module("run_study").preflight()
    runner = _module("run_study")
    contract, source = runner.preflight()
    assert source.name == "source.md"
    assert contract["format_version"] == 4
    assert contract["supersedes"]["study_id"].endswith("v3-replayable-batch32")
    assert len(contract["supersedes"]["contract_git_blob_sha1"]) == 40
    assert len(contract["supersedes"]["contract_file_sha256"]) == 64
    assert all(arm.get("official_url") for arm in contract["arms"] if arm["kind"] == "native_rubric")
    assert contract["hbq_runtime"]["question_count"] == 178
    assert contract["hbq_runtime"]["checkpoint_format_version"] == 4
    assert len(runner._schedule_events(contract)) == 20
    assert runner._asset_manifest(contract)["assets"]["study_runner"]["sha256"]


def test_preflight_rejects_a_declared_policy_that_differs_from_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")
    contract = _json(ROOT / "study-contract.json")
    contract["hbq_runtime"]["evidence_normalization_policy"] = "wrong_policy"
    frozen = tmp_path / "study-contract.json"
    _write(frozen, contract)
    monkeypatch.setattr(runner, "CONTRACT_PATH", frozen)
    with pytest.raises(ValueError, match="runtime policy"):
        runner.preflight()


def test_journal_requires_ordered_plans_then_ordered_completions(tmp_path: Path) -> None:
    runner = _module("run_study")
    contract, _ = runner.preflight()
    journal, count = runner._prepare_journal(tmp_path, contract)
    assert count == 0
    plans = runner._schedule_events(contract)
    runner._append_journal(journal, {**plans[1], "event": "completed", "run_binding_sha256": "a" * 64})
    with pytest.raises(ValueError, match="missing, duplicated, or reordered"):
        runner._prepare_journal(tmp_path, contract)


def test_journal_recovers_a_contiguous_planning_prefix_only(tmp_path: Path) -> None:
    runner = _module("run_study")
    contract, _ = runner.preflight()
    plans = runner._schedule_events(contract)
    journal = tmp_path / runner.JOURNAL_NAME
    runner._append_journal(journal, plans[0])
    _, count = runner._prepare_journal(tmp_path, contract)
    assert count == 0
    assert runner._read_journal(journal) == plans
    mismatch = tmp_path / "mismatch" / runner.JOURNAL_NAME
    runner._append_journal(mismatch, {**plans[0], "arm_id": "wrong"})
    with pytest.raises(ValueError, match="planned events"):
        runner._prepare_journal(mismatch.parent, contract)


def test_v4_checkpoint_replays_repaired_quote_and_cumulative_feedback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis, base = _make_run(tmp_path, monkeypatch, repaired_quote=True, rejected_first=True)
    checkpoint = _json(base / "responses" / "batch-0001.json")
    assert checkpoint["format_version"] == 4
    assert checkpoint["normalization_audit"]
    assert checkpoint["validation_feedback_policy"] == "validation_feedback_retry_v1"
    _, score, sessions = analysis._validate_hbq_run(tmp_path / "work", 1)
    assert score["artifact_id"] == "the-part-that-arrives-first"
    assert len(sessions) == 6


def test_v4_replay_rejects_tampered_repair_audit_and_rejected_chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis, base = _make_run(tmp_path / "audit", monkeypatch, repaired_quote=True)
    checkpoint_path = base / "responses" / "batch-0001.json"
    checkpoint = _json(checkpoint_path)
    checkpoint["normalization_audit"] = []
    _write(checkpoint_path, checkpoint)
    with pytest.raises(ValueError, match="checkpoint/retry/normalization replay"):
        analysis._validate_hbq_run(tmp_path / "audit" / "work", 1)
    analysis, base = _make_run(tmp_path / "chain", monkeypatch)
    checkpoint_path = base / "responses" / "batch-0001.json"
    checkpoint = _json(checkpoint_path)
    checkpoint["rejected_chain"] = {"count": 1, "head_sha256": "0" * 64}
    _write(checkpoint_path, checkpoint)
    with pytest.raises(ValueError, match="checkpoint/retry/normalization replay"):
        analysis._validate_hbq_run(tmp_path / "chain" / "work", 1)


def test_score_recomputation_and_global_session_uniqueness_are_mandatory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis, base = _make_run(tmp_path, monkeypatch)
    score_path = base / "score.json"
    score = _json(score_path)
    score["final_score"]["observed"] = 99.0
    _write(score_path, score)
    with pytest.raises(ValueError, match="deterministic recomputation"):
        analysis._validate_hbq_run(tmp_path / "work", 1)
    with pytest.raises(ValueError, match="globally unique"):
        analysis._require_unique_sessions(["same"] * 45, 45)


def test_analysis_never_overwrites_existing_public_output(tmp_path: Path) -> None:
    analysis = _module("analyze_study")
    output = tmp_path / "published"
    output.mkdir()
    with pytest.raises(ValueError, match="overwrite"):
        analysis.analyze(tmp_path / "work", output)


def test_complete_twenty_slot_analysis_fixture_proves_all_45_sessions_and_public_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _module("analyze_study")
    monkeypatch.setattr(analysis, "_validate_journal", lambda work: [])
    monkeypatch.setattr(analysis, "_validate_hbq_run", lambda work, number: ([], {}, [f"hbq-{number}-{batch}" for batch in range(1, 7)]))
    monkeypatch.setattr(analysis, "_validate_native_run", lambda work, arm, number: ({}, f"{arm['arm_id']}-{number}"))
    monkeypatch.setattr(analysis, "_retry_provenance", lambda work: {"accepted_run_count": 5, "rejected_attempt_count": 0, "recovered_acceptance_count": 0, "normalization_repair_count": 0})
    monkeypatch.setattr(analysis, "_native_retry_provenance", lambda work, arm: ({"attempt_count": 5}, []))

    def prove(work: Path, output: Path, arm: dict) -> list[dict]:
        target = output / arm["arm_id"] / "proof.json"
        _write(target, {"arm_id": arm["arm_id"]})
        return [{"run_id": "run-01", "proof": target.name}]

    monkeypatch.setattr(analysis, "_copy_and_prove", prove)
    helper = SimpleNamespace(
        _hbq_metrics=lambda work: ({"observed_score": {"values": [50] * 5}, "exact_all_run_agreement_rate": 1.0}, []),
        _native_metrics=lambda work, arm: ({"total_score": {"values": [1] * 5}, "criterion_exact_all_run_agreement_rate": 1.0}, []),
        _charts=lambda summary, output: (output / "score-distributions.svg").write_text("<svg/>", encoding="utf-8"),
    )
    monkeypatch.setattr(analysis, "_v2_helper", lambda: helper)
    output = tmp_path / "published"
    analysis.analyze(tmp_path / "work", output)
    provenance = _json(output / "provenance.json")
    assert provenance["fresh_session_commitment"]["session_count"] == 45
    assert provenance["fresh_session_commitment"]["unique_session_count"] == 45
    assert (output / "summary.json").is_file() and (output / "manifest.json").is_file()
    assert (output / "hbq_short_story_batch32" / "proof.json").is_file()


def test_v4_code_has_explicit_native_schema_artifact_and_replay_gates() -> None:
    text = (ROOT / "analyze_study.py").read_text(encoding="utf-8")
    assert "_load_checkpoints" in text and "EVIDENCE_NORMALIZATION_POLICY" in text
    assert "_validate_provider_artifacts" in text and "score_bundle" in text
    assert "Draft202012Validator" in text and "unique accepted provider sessions" in text


def test_native_schemas_are_flat_and_strict_after_provider_projection() -> None:
    runner = _module("run_study")
    contract = _json(ROOT / "study-contract.json")
    for arm in contract["arms"]:
        if arm["kind"] != "native_rubric":
            continue
        schema = _json(ROOT / arm["schema"])
        runner._validate_strict_response_schema(schema, label=arm["arm_id"])
        assert "allOf" not in json.dumps(schema)


def test_schema_preflight_rejects_allof_and_optional_object_fields() -> None:
    runner = _module("run_study")
    with pytest.raises(ValueError, match="allOf"):
        runner._validate_strict_response_schema({"type": "object", "properties": {}, "required": [], "additionalProperties": False, "allOf": [{}]}, label="bad")
    with pytest.raises(ValueError, match="require every"):
        runner._validate_strict_response_schema({"type": "object", "properties": {"value": {"type": "string"}}, "required": [], "additionalProperties": False}, label="bad")
    with pytest.raises(ValueError, match="root must be an object"):
        runner._validate_strict_response_schema({"type": "array", "items": {"type": "string"}}, label="bad")


def test_execute_runs_real_preflight_and_prepares_full_journal_without_provider_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")

    def fake_hbq(arm: dict, number: int, source: Path, work: Path, timeout: float, contract: dict) -> None:
        _write(work / arm["arm_id"] / f"run-{number:02d}" / "run.json", {"fixture": True})

    def fake_native(arm: dict, number: int, source: Path, work: Path, timeout: float) -> None:
        _write(work / arm["arm_id"] / f"run-{number:02d}" / "pass.json", {"fixture": True})

    monkeypatch.setattr(runner, "_run_hbq", fake_hbq)
    monkeypatch.setattr(runner, "_run_native", fake_native)
    work = tmp_path / "study-work"
    runner.execute(work, timeout=1.0)
    records = runner._read_journal(work / runner.JOURNAL_NAME)
    assert len(records) == 40
    assert [record["event"] for record in records[:20]] == ["planned"] * 20
    assert [record["event"] for record in records[20:]] == ["completed"] * 20


def test_analyzer_enforces_native_identifiers_ranges_and_totals() -> None:
    analysis = _module("analyze_study")
    maxima = {"audience": 6, "text_structure": 4, "ideas": 5, "character_and_setting": 4, "vocabulary": 5, "cohesion": 4, "paragraphing": 2, "sentence_structure": 6, "punctuation": 5, "spelling": 6}
    result = {
        "criteria": [{"criterion_id": key, "score": value, "exact_quote": "Mica always arrived first."} for key, value in maxima.items()],
        "total_score": sum(maxima.values()),
    }
    analysis._validate_native_semantics(result, "naplan_narrative_2022")
    result["criteria"][1]["score"] = 5
    result["total_score"] += 1
    with pytest.raises(ValueError, match="native range"):
        analysis._validate_native_semantics(result, "naplan_narrative_2022")
    result["criteria"][1]["score"] = 4
    with pytest.raises(ValueError, match="deterministic sum"):
        analysis._validate_native_semantics(result, "naplan_narrative_2022")
    result["total_score"] -= 1
    result["criteria"][-1]["criterion_id"] = "audience"
    with pytest.raises(ValueError, match="duplicated"):
        analysis._validate_native_semantics(result, "naplan_narrative_2022")


def test_semantic_rejection_is_not_journaled_and_corrected_resume_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")
    contract = _json(ROOT / "study-contract.json")
    arm = next(item for item in contract["arms"] if item["arm_id"] == "naplan_narrative_2022")
    event = {"format_version": 4, "event": "planned", "sequence": 1, "block": 1, "position": 1, "arm_id": arm["arm_id"], "run_id": "run-01", "protocol_contract_sha256": runner._sha256(runner.CONTRACT_PATH), "schedule_sha256": runner.schedule_sha256(contract)}
    monkeypatch.setattr(runner, "_schedule_events", lambda frozen: [event])
    identifiers = ["audience", "text_structure", "ideas", "character_and_setting", "vocabulary", "cohesion", "paragraphing", "sentence_structure", "punctuation", "spelling"]
    calls = 0

    def fake_codex(**kwargs):
        nonlocal calls
        calls += 1
        current = ["audience"] * 10 if calls == 1 else identifiers
        result = {
            "method": "naplan_narrative_2022_research_implementation",
            "criteria": [{"criterion_id": identifier, "score": 0, "exact_quote": "Mica always arrived first.", "observation": "fixture"} for identifier in current],
            "total_score": 0,
            "overall_note": "fixture",
        }
        return json.dumps(result), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"native-{calls}"}}

    monkeypatch.setattr(longform_runner, "_call_codex", fake_codex)
    work = tmp_path / "work"
    with pytest.raises(ValueError, match="duplicated"):
        runner.execute(work, timeout=1.0)
    records = runner._read_journal(work / runner.JOURNAL_NAME)
    assert records == [event]
    pass_dir = work / arm["arm_id"] / "run-01"
    assert not (pass_dir / "response.json").exists() and not (pass_dir / "result.json").exists()
    rejected = list((pass_dir / "attempts").glob("rejected-*.json"))
    assert len(rejected) == 1 and "duplicated" in _json(rejected[0])["reason"]
    runner.execute(work, timeout=1.0)
    records = runner._read_journal(work / runner.JOURNAL_NAME)
    assert [record["event"] for record in records] == ["planned", "completed"]
    assert calls == 2 and (pass_dir / "result.json").is_file()


def test_cached_third_attempt_is_validated_without_a_fourth_provider_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")
    contract, source = runner.preflight()
    arm = next(item for item in contract["arms"] if item["arm_id"] == "naplan_narrative_2022")
    identifiers = ["audience", "text_structure", "ideas", "character_and_setting", "vocabulary", "cohesion", "paragraphing", "sentence_structure", "punctuation", "spelling"]
    calls = 0

    def fake_codex(**kwargs):
        nonlocal calls
        calls += 1
        current = ["audience"] * 10 if calls < 3 else identifiers
        result = {"method": "naplan_narrative_2022_research_implementation", "criteria": [{"criterion_id": item, "score": 0, "exact_quote": "Mica always arrived first.", "observation": "fixture"} for item in current], "total_score": 0, "overall_note": "fixture"}
        return json.dumps(result), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"third-{calls}"}}

    monkeypatch.setattr(longform_runner, "_call_codex", fake_codex)
    output = tmp_path / "work"
    for _ in range(2):
        with pytest.raises(ValueError, match="duplicated"):
            runner._run_native(arm, 1, source, output, 1.0)
    original = runner._validate_native_result
    crashed = False

    def crash_once(result, arm_id, source_text):
        nonlocal crashed
        original(result, arm_id, source_text)
        if not crashed:
            crashed = True
            raise RuntimeError("simulated post-provider crash")

    monkeypatch.setattr(runner, "_validate_native_result", crash_once)
    with pytest.raises(RuntimeError, match="simulated"):
        runner._run_native(arm, 1, source, output, 1.0)
    pass_dir = output / arm["arm_id"] / "run-01"
    assert runner._native_next_attempt(pass_dir) == 4 and (pass_dir / "response.json").is_file()
    runner._run_native(arm, 1, source, output, 1.0)
    assert calls == 3 and (pass_dir / "result.json").is_file()


def test_semantic_rejection_transaction_is_idempotent_after_unlink_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")
    contract, source = runner.preflight()
    arm = next(item for item in contract["arms"] if item["arm_id"] == "naplan_narrative_2022")
    identifiers = ["audience", "text_structure", "ideas", "character_and_setting", "vocabulary", "cohesion", "paragraphing", "sentence_structure", "punctuation", "spelling"]
    calls = 0

    def fake_codex(**kwargs):
        nonlocal calls
        calls += 1
        current = ["audience"] * 10 if calls == 1 else identifiers
        result = {"method": "naplan_narrative_2022_research_implementation", "criteria": [{"criterion_id": item, "score": 0, "exact_quote": "Mica always arrived first.", "observation": "fixture"} for item in current], "total_score": 0, "overall_note": "fixture"}
        return json.dumps(result), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"dedupe-{calls}"}}

    def crash_before_unlink(output: Path, *, reason: str) -> None:
        _write(output / "attempts" / "rejected-0001.json", {"format_version": 1, "reason": reason, "response": _json(output / "response.json"), "result": _json(output / "result.json")})

    monkeypatch.setattr(longform_runner, "_call_codex", fake_codex)
    monkeypatch.setattr(runner, "_reject_structured_checkpoint", crash_before_unlink)
    output = tmp_path / "work"
    with pytest.raises(ValueError, match="duplicated"):
        runner._run_native(arm, 1, source, output, 1.0)
    pass_dir = output / arm["arm_id"] / "run-01"
    assert (pass_dir / "response.json").is_file()
    with pytest.raises(ValueError, match="duplicated"):
        runner._run_native(arm, 1, source, output, 1.0)
    assert len(list((pass_dir / "attempts").glob("rejected-*.json"))) == 1
    assert runner._native_next_attempt(pass_dir) == 2
    runner._run_native(arm, 1, source, output, 1.0)
    assert calls == 2


def test_native_retry_provenance_rejects_coherent_binding_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _module("run_study")
    analysis = _module("analyze_study")
    contract, source = runner.preflight()
    arm = next(item for item in contract["arms"] if item["arm_id"] == "naplan_narrative_2022")
    identifiers = ["audience", "text_structure", "ideas", "character_and_setting", "vocabulary", "cohesion", "paragraphing", "sentence_structure", "punctuation", "spelling"]
    calls = 0

    def fake_codex(**kwargs):
        nonlocal calls
        calls += 1
        invalid = calls == 1
        current = ["audience"] * 10 if invalid else identifiers
        result = {"method": "naplan_narrative_2022_research_implementation", "criteria": [{"criterion_id": item, "score": 0, "exact_quote": "Mica always arrived first.", "observation": "fixture"} for item in current], "total_score": 0, "overall_note": "fixture"}
        response_dir = Path(kwargs["output_dir"]) / "responses"
        _write(response_dir / f"batch-0001.attempt-{kwargs['attempt_number']:04d}.message.json", {"fixture": calls})
        return json.dumps(result), {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": f"audit-{calls}"}}

    monkeypatch.setattr(longform_runner, "_call_codex", fake_codex)
    work = tmp_path / "work"
    with pytest.raises(ValueError, match="duplicated"):
        runner._run_native(arm, 1, source, work, 1.0)
    runner._run_native(arm, 1, source, work, 1.0)
    for number in range(2, 6):
        runner._run_native(arm, number, source, work, 1.0)
    provenance, sessions = analysis._native_retry_provenance(work, arm)
    assert provenance["attempt_count"] == 6 and provenance["semantic_rejection_count"] == 1
    assert sessions == ["audit-1"]
    rejected = work / arm["arm_id"] / "run-01" / "attempts" / "rejected-0001.json"
    record = _json(rejected)
    accepted_session = _json(work / arm["arm_id"] / "run-01" / "response.json")["provider"]["reported"]["session_id"]
    provider_failure = {"format_version": 1, "config_sha256": _json(work / arm["arm_id"] / "run-01" / "pass.json")["config_sha256"], "content": None, "provider": json.loads(json.dumps(record["response"]["provider"])), "retryable": True, "error": {"class": "fixture", "message": "fixture"}}
    provider_failure["provider"]["reported"]["session_id"] = accepted_session
    _write(rejected, provider_failure)
    _, rejected_sessions = analysis._native_retry_provenance(work, arm)
    assert rejected_sessions == [accepted_session]
    with pytest.raises(ValueError, match="globally unique"):
        analysis._require_disjoint_attempt_sessions([accepted_session], rejected_sessions)
    _write(rejected, record)
    record = _json(rejected)
    record["response"]["config_sha256"] = "0" * 64
    _write(rejected, record)
    with pytest.raises(ValueError, match="semantic rejection response binding"):
        analysis._native_retry_provenance(work, arm)


def test_analysis_validation_failure_does_not_consume_final_output_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = _module("analyze_study")
    monkeypatch.setattr(analysis, "_validate_journal", lambda work: (_ for _ in ()).throw(ValueError("fixture validation failure")))
    output = tmp_path / "published"
    with pytest.raises(ValueError, match="fixture validation failure"):
        analysis.analyze(tmp_path / "work", output)
    assert not output.exists()
