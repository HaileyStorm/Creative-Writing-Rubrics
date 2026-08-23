from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-poetry-scope-sentinel-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("s1_execution_test", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    assert s.validate_package()["slots"] == 60
    slots = s.build_schedule()
    assert len(slots) == len({row["slot_id"] for row in slots}) == 60
    assert {row["leaf_id"] for row in slots} == set(s.LEAVES)
    bundle = s._bundle()[0]
    assert bundle["module_ids"] == list(s.MODULES.values())
    assert [component["include_question_ids"][0] for component in bundle["domains"][0]["components"]] == list(s.LEAVES)


def test_provider_command_is_singleton_strict_and_poetry_scope_bound(tmp_path: Path, monkeypatch):
    s = study(); monkeypatch.setattr(s, "_external_root", lambda value: Path(value).resolve())
    s.prepare(tmp_path); slot = s.build_schedule()[0]; command = s.command_for(slot, tmp_path)
    assert command[command.index("--provider") + 1] == "codex"
    assert command[command.index("--model") + 1] == "gpt-5.6-sol"
    assert command[command.index("--reasoning") + 1] == "high" and "--strict-ai" in command
    assert command[command.index("--batch-size") + 1] == "1" and command[command.index("--batch-attempts") + 1] == "3"
    assert "--task-contract" in command and "--scope-compatibility-override" in command
    assert "expected_verdict" in (tmp_path / "private-schedule.json").read_text(encoding="utf-8")


def test_full_60_slot_dry_run_is_provider_free_and_prompt_committed(tmp_path: Path, monkeypatch):
    s = study(); monkeypatch.setattr(s, "_external_root", lambda value: Path(value).resolve())
    result = s.dry_run(tmp_path, runner_call=fake_cwr)
    assert result["provider_calls"] == 0 and len(result["rendered_prompt_sha256s"]) == 60
    assert len(list((tmp_path / "rendered-prompts").glob("*.txt"))) == 60
    runtime = json.loads((tmp_path / "runtime-schedule.json").read_text(encoding="utf-8"))
    assert runtime["rendered_prompt_aggregate_sha256"] == result["rendered_prompt_aggregate_sha256"]


def test_dry_run_freezes_lf_only_and_execute_requires_both_flags(tmp_path: Path, monkeypatch):
    s = study(); monkeypatch.setattr(s, "_external_root", lambda value: Path(value).resolve())
    def crlf_renderer(command, **_kwargs):
        if "render-judge" in command:
            return SimpleNamespace(returncode=0, stdout=b"frozen\r\nprompt\r\n", stderr=b"")
        if "--dry-run" in command:
            output = Path(command[command.index("--output-dir") + 1]); output.mkdir(parents=True, exist_ok=True)
            (output / "run.json").write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    s.dry_run(tmp_path, runner_call=crlf_renderer)
    assert b"\r" not in (tmp_path / "rendered-prompts" / "pssexec-v1-01-r1.txt").read_bytes()
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(tmp_path, runner_call=fake_cwr)


def test_settlement_preserves_four_state_diagnostics_without_promotion(tmp_path: Path, monkeypatch):
    s = study(); monkeypatch.setattr(s, "_external_root", lambda value: Path(value).resolve())
    s.dry_run(tmp_path, runner_call=fake_cwr)
    result = s.settle(tmp_path, verifier=lambda _root, slot: record(slot))
    assert result["decision"] == "PASS_NO_CHANGE"
    public = json.loads((tmp_path / "public-aggregate.json").read_text(encoding="utf-8"))
    assert public["scored_cells"] == {"passed": 15, "total": 15}
    assert public["not_applicable_diagnostic_cells"] == {"matched": 5, "total": 5}
    assert public["promotion"] == "none"


def test_prompt_comparison_allows_only_checkpoint_crlf_to_rendered_lf(tmp_path: Path):
    s = study(); prompt = tmp_path / "prompt.txt"; prompt.write_bytes(b"one\ntwo\n")
    run = tmp_path / "run" / "responses"; run.mkdir(parents=True)
    checkpoint = run / "batch-0001.prompt.txt.gz"; checkpoint.write_bytes(gzip.compress(b"one\r\ntwo\r\n"))
    assert s._verify_checkpoint_prompt(run.parent, prompt)["canonical_prompt_sha256"] == s.sha256_bytes(b"one\ntwo\n")
    checkpoint.write_bytes(gzip.compress(b"one\rtwo\n"))
    with pytest.raises(ValueError, match="lone"):
        s._verify_checkpoint_prompt(run.parent, prompt)


def test_private_path_and_predecessor_tampering_fail_closed(tmp_path: Path, monkeypatch):
    s = study()
    with pytest.raises(ValueError, match="outside"):
        s.prepare(book_root() / ".artifacts-temp" / "s1-private")
    mutated = s.contract(); mutated["geometry"]["slots"] = 61
    monkeypatch.setattr(s, "contract", lambda: mutated)
    with pytest.raises(ValueError, match="geometry"):
        s.validate_package()
