from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hbqrs.paths import book_root
from tests import _hbq_s2_historical_runtime as historical_runtime

ROOT = book_root() / "evaluation-results" / "hbq-nonpoetry-scope-sentinel-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("s2_execution_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        return historical_runtime.install(module, source_commit="3a529c071997b26bfe4d15acd0b100be5300b2a1")
    except historical_runtime.HistoricalRuntimeUnbound as exc:
        pytest.skip(f"historical runtime unbound: {exc}")


def fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        return SimpleNamespace(returncode=0, stdout="frozen LF prompt\n", stderr="")
    if "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1]); output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def record(slot):
    ordinal = 10 * int(slot["slot_id"].split("-")[-2]) + int(slot["slot_id"].split("-")[-1].removeprefix("r"))
    return {"slot_id": slot["slot_id"], "logical_sample_id": slot["logical_sample_id"], "verdict": slot["expected_verdict"], "expected": slot["expected_verdict"], "correct": True, "run_id": "run", "session_id_sha256": f"{ordinal:064x}", "checkpoint_chain_head_sha256": f"{1000 + ordinal:064x}", "evidence": [], "accepted_provider_call_count": 1, "rejected_retry_count": 0, "batch_attempt_count": 1}


def test_exact_predecessor_geometry_and_private_minimal_bundle():
    s = study()
    assert s.REPOSITORY != book_root()
    assert s.validate_package()["slots"] == 60
    slots = s.build_schedule()
    assert len(slots) == len({row["slot_id"] for row in slots}) == 60
    assert {row["leaf_id"] for row in slots} == set(s.LEAVES)
    bundle = s._bundle()[0]
    assert bundle["module_ids"] == list(s.MODULES.values())
    assert [component["include_question_ids"][0] for component in bundle["domains"][0]["components"]] == list(s.LEAVES)


def test_provider_command_is_singleton_strict_and_has_scope_context(tmp_path: Path):
    s = study(); s.prepare(tmp_path); slot = s.build_schedule()[0]; command = s.command_for(slot, tmp_path)
    assert command[command.index("--provider") + 1] == "codex"
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert command[command.index("--reasoning") + 1] == "high" and "--strict-ai" in command
    assert command[command.index("--batch-size") + 1] == "1" and command[command.index("--batch-attempts") + 1] == "3"
    assert "--task-contract" in command and "--scope-compatibility-override" in command
    assert "expected_verdict" in (tmp_path / "private-schedule.json").read_text(encoding="utf-8")


def test_full_60_slot_dry_run_is_provider_free_and_prompt_committed(tmp_path: Path):
    s = study(); result = s.dry_run(tmp_path, runner_call=fake_cwr)
    assert result["provider_calls"] == 0 and len(result["rendered_prompt_sha256s"]) == 60
    assert len(list((tmp_path / "rendered-prompts").glob("*.txt"))) == 60
    assert json.loads((tmp_path / "runtime-schedule.json").read_text(encoding="utf-8"))["rendered_prompt_aggregate_sha256"] == result["rendered_prompt_aggregate_sha256"]


def test_dry_run_freezes_lf_only_even_if_renderer_returns_crlf(tmp_path: Path):
    s = study()
    def crlf_renderer(command, **_kwargs):
        if "render-judge" in command:
            return SimpleNamespace(returncode=0, stdout=b"frozen\r\nprompt\r\n", stderr=b"")
        if "--dry-run" in command:
            output = Path(command[command.index("--output-dir") + 1]); output.mkdir(parents=True, exist_ok=True)
            (output / "run.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    s.dry_run(tmp_path, runner_call=crlf_renderer)
    assert b"\r" not in (tmp_path / "rendered-prompts" / "npssexec-v1-01-r1.txt").read_bytes()


def test_execution_acknowledgement_and_settlement_four_state_handling(tmp_path: Path):
    s = study(); s.dry_run(tmp_path, runner_call=fake_cwr)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(tmp_path, runner_call=fake_cwr)
    assert s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr)["mode"] == "execute"
    result = s.settle(tmp_path, verifier=lambda _root, slot: record(slot))
    assert result["decision"] == "PASS_NO_CHANGE"
    public = json.loads((tmp_path / "public-aggregate.json").read_text(encoding="utf-8"))
    assert public["scored_cells"] == {"passed": 15, "total": 15}
    assert public["not_applicable_diagnostic_cells"] == {"matched": 5, "total": 5}


def test_prompt_comparison_allows_only_checkpoint_crlf_to_rendered_lf(tmp_path: Path):
    s = study(); prompt = tmp_path / "prompt.txt"; prompt.write_bytes(b"one\ntwo\n")
    run = tmp_path / "run" / "responses"; run.mkdir(parents=True)
    checkpoint = run / "batch-0001.prompt.txt.gz"; checkpoint.write_bytes(gzip.compress(b"one\r\ntwo\r\n"))
    assert s._verify_checkpoint_prompt(run.parent, prompt)["canonical_prompt_sha256"] == s.sha256_bytes(b"one\ntwo\n")
    checkpoint.write_bytes(gzip.compress(b"one\rtwo\n"))
    with pytest.raises(ValueError, match="lone"):
        s._verify_checkpoint_prompt(run.parent, prompt)


def test_renderer_recovers_windows_cp1252_prompt_bytes_without_silently_replacing_text():
    s = study()
    assert s._rendered_prompt_bytes("scope — prompt") == "scope — prompt".encode("utf-8")
    assert s._rendered_prompt_bytes("scope — prompt".encode("cp1252")) == "scope — prompt".encode("utf-8")


def test_verify_slot_rejects_config_hash_or_transplanted_run_identity(monkeypatch, tmp_path: Path):
    s = study(); s.prepare(tmp_path); slot = s.build_schedule()[0]
    prompt = tmp_path / "rendered-prompts" / f"{slot['slot_id']}.txt"; prompt.parent.mkdir(); prompt.write_bytes(b"prompt\n")
    slot = s._runtime_schedule(tmp_path, [slot])[0]
    artifact, task, override = s._paths(tmp_path, slot); contexts = s._context_paths(tmp_path, slot)
    run = tmp_path / "runs" / slot["slot_id"]; response = run / "responses"; response.mkdir(parents=True)
    (response / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"prompt\n"))
    config = {"provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True, "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1", "artifact_id": slot["artifact_id"], "bundle_id": s.BUNDLE_ID, "question_ids": [slot["leaf_id"]], "artifact": s._input_record(artifact), "contexts": [s._input_record(path) for path in contexts], "task_contract": {"sha256": s.sha256_file(task)}, "scope_compatibility": {"sha256": s.sha256_file(override)}, "prompts": [{"sha256": s.sha256_file(s.REPOSITORY / "prompts" / "judge" / name)} for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")], "response_schema": {"sha256": s.sha256_file(s.REPOSITORY / "schema" / "hbq_judge_response.schema.json")}}
    manifest = {"format_version": 4, "configuration": config, "config_sha256": s.runner._sha256_bytes(s.runner._json_bytes(config)), "run_id": "manifest-run"}
    checkpoint = {"provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "session"}}}
    diagnostic = {"status": "DIAGNOSTIC_SUBSET", "selected_question_ids": [slot["leaf_id"]]}
    def loader(path):
        if path.name == "run.json": return manifest
        if path.name == "batch-0001.json": return checkpoint
        if path.name == "diagnostic.json": return diagnostic
        raise AssertionError(path)
    monkeypatch.setattr(s, "_load_json", loader)
    monkeypatch.setattr(s.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([{"question_id": slot["leaf_id"], "verdict": slot["expected_verdict"], "run_id": "manifest-run", "evidence": []}], 1, "chain"))
    monkeypatch.setattr(s.runner, "_validate_typed_checkpoint_evidence", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s.runner, "_validate_exact_quotes", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(s.runner, "_rejected_records", lambda *_args, **_kwargs: [])
    assert s._verify_slot(tmp_path, slot)["run_id"] == "manifest-run"
    manifest["config_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="configuration hash"):
        s._verify_slot(tmp_path, slot)
    manifest["config_sha256"] = s.runner._sha256_bytes(s.runner._json_bytes(config))
    monkeypatch.setattr(s.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([{"question_id": slot["leaf_id"], "verdict": slot["expected_verdict"], "run_id": "transplanted-run", "evidence": []}], 1, "chain"))
    with pytest.raises(ValueError, match="run identity"):
        s._verify_slot(tmp_path, slot)
