from __future__ import annotations

import json
import importlib.util
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from _established_repeatability_historical_runtime import (
    HistoricalRuntimeUnavailable,
    HistoricalStudyRuntime,
)
from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "the-part-that-arrives-first-repeatability" / "established-v3"
REPOSITORY = book_root().resolve()
_HISTORICAL = HistoricalStudyRuntime(
    root=ROOT,
    repository=REPOSITORY,
    runtime_commit="6a2a2bf1452576d01a56e83bbca98763f5697e7c",
    control_commit="6a2a2bf1452576d01a56e83bbca98763f5697e7c",
    package_name="established_v3_historical_hbqrs",
    label="v3",
    seals_path=Path(__file__).with_name("fixtures") / "established_repeatability_historical_successor_seals.json",
)


def _historical_runtime():
    try:
        return _HISTORICAL.runtime()
    except HistoricalRuntimeUnavailable as exc:
        pytest.skip(str(exc))


def _raw_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _module(name: str):
    return _HISTORICAL.module(name)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _make_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, repaired_quote: bool = False, rejected_first: bool = False) -> tuple[object, Path]:
    analysis = _module("analyze_study")
    historical = _historical_runtime()
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

    monkeypatch.setattr(historical.runner, "_call_codex", fake_codex)
    source = historical.root / ROOT.relative_to(REPOSITORY).parent / "source.md"
    output = tmp_path / "work" / "hbq_short_story_batch32" / "run-01"
    historical.runner.run_judge(artifact_path=source, bundle_id="prose.short_story", provider="codex", model="gpt-5.6-sol", output_dir=output, registry=historical.paths.registry_path(), bundles=historical.paths.bundles_path(), batch_size=32, batch_attempts=3, reasoning="high", allow_remote=True, artifact_id="the-part-that-arrives-first", strict_ai=True)
    return analysis, output


def test_preflight_hashes_schedule_and_exact_predecessor() -> None:
    with pytest.raises(ValueError, match="Frozen asset changed: registry"):
        _raw_module("run_study").preflight()
    runner = _module("run_study")
    contract, source = runner.preflight()
    assert source.name == "source.md"
    assert contract["format_version"] == 3
    assert contract["supersedes"]["study_id"].endswith("v2-batch32")
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


def test_v3_code_has_explicit_native_schema_artifact_and_replay_gates() -> None:
    text = (ROOT / "analyze_study.py").read_text(encoding="utf-8")
    assert "_load_checkpoints" in text and "EVIDENCE_NORMALIZATION_POLICY" in text
    assert "_validate_provider_artifacts" in text and "score_bundle" in text
    assert "Draft202012Validator" in text and "unique accepted provider sessions" in text


def test_historical_runtime_ignores_hostile_hbqrs_root_and_uses_snapshot_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HBQRS_ROOT", str(tmp_path / "hostile-root"))
    historical = _historical_runtime()
    source = historical.root / ROOT.relative_to(REPOSITORY).parent / "source.md"
    assert historical.paths.book_root() == historical.root
    assert source.is_file() and source.read_bytes() != b""


def test_v2_helper_is_fully_bound_to_the_historical_runtime() -> None:
    analysis = _module("analyze_study")
    historical = _historical_runtime()
    helper = analysis._v2_helper()
    assert helper._verdicts_bytes is historical.runner._verdicts_bytes
    assert helper.schema_dir().is_relative_to(historical.root)


def test_canonical_successor_seals_retain_raw_lineage_without_claiming_raw_reconstruction() -> None:
    historical = _historical_runtime()
    assets = historical.manifest["assets"]
    for name in ("score_report_schema", "scoring_core"):
        record = assets[name]
        seal = historical.seals[record["sha256"]]
        payload = (historical.root / (ROOT / record["path"]).resolve().relative_to(REPOSITORY)).read_bytes()
        assert seal["raw_bytes"] == record["bytes"]
        assert hashlib.sha256(payload).hexdigest() == seal["canonical_lf_sha256"]
        assert hashlib.sha256(payload).hexdigest() != record["sha256"]
