from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-polarity-change-current-wording-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("p1_execution_v1", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"ordinary P1 prompt\r\nwith Windows transport\r\n")
    elif "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text("{}", encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _prepared(s, root: Path):
    s.dry_run(root, runner_call=_fake_cwr)
    return json.loads((root / "runtime-schedule.json").read_text(encoding="utf-8"))["slots"]


def _record(s, slot: dict[str, object]) -> dict[str, object]:
    return {
        "slot_id": slot["slot_id"], "verdict": slot["expected_verdict"], "expected": slot["expected_verdict"],
        "correct": True, "evidence": [{"reference": "artifact", "exact_quote": str(slot["artifact_text"])[:20]}],
        "run_id": f"run-{slot['slot_id']}", "session_id_sha256": hashlib.sha256(str(slot["slot_id"]).encode()).hexdigest(),
        "checkpoint_chain_head_sha256": hashlib.sha256(("chain-" + str(slot["slot_id"])).encode()).hexdigest(),
    }


def test_package_binds_pushed_p1_predecessor_and_exact_132_slot_geometry():
    s = study()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "slots": 132, "provider_calls": 0, "predecessor": "5665e2f"}
    slots = s.build_schedule()
    assert len(slots) == len({slot["slot_id"] for slot in slots}) == 132
    assert len({slot["leaf_id"] for slot in slots}) == 11
    assert {slot["expected_verdict"] for slot in slots} == s.VERDICTS
    assert s.contract()["execution"]["maximum_provider_sends"] == 396


def test_dry_run_has_zero_provider_calls_and_freezes_canonical_prompt_bytes(tmp_path: Path):
    s = study()
    report = s.dry_run(tmp_path, runner_call=_fake_cwr)
    stored = json.loads((tmp_path / "runtime-schedule.json").read_text(encoding="utf-8"))
    assert report["provider_calls"] == 0 and len(report["rendered_prompt_sha256s"]) == 132
    assert stored["rendered_prompt_aggregate_sha256"] == report["rendered_prompt_aggregate_sha256"]
    prompt = (tmp_path / "rendered-prompts" / "p1-v1-audio-exposition-yes-r1.txt").read_bytes()
    assert prompt == b"ordinary P1 prompt\nwith Windows transport\n"
    assert s.canonical_prompt_bytes(b"x\r\ny\n") == b"x\ny\n"
    with pytest.raises(ValueError, match="lone CR"):
        s.canonical_prompt_bytes(b"x\ry\n")
    assert (tmp_path / "runtime-p1-bundle.json").is_file()


def test_provider_command_is_singleton_strict_and_does_not_expose_oracle_metadata(tmp_path: Path):
    s = study()
    slot = _prepared(s, tmp_path)[0]
    command = s.command_for(slot, tmp_path)
    joined = " ".join(command)
    assert "--provider" in command and command[command.index("--provider") + 1] == "codex"
    assert "--strict-ai" in command and command[command.index("--batch-size") + 1] == "1"
    assert "--allow-remote" not in command and "expected_verdict" not in joined
    assert "--resume" in s.command_for(slot, tmp_path, resume=True)


def test_execute_requires_dual_acknowledgement_and_empty_fresh_attempts(tmp_path: Path):
    s = study()
    slots = _prepared(s, tmp_path)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(tmp_path, runner_call=_fake_cwr)
    assert s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)["mode"] == "execute"
    response = tmp_path / "runs" / slots[0]["slot_id"] / "responses"
    response.mkdir(parents=True, exist_ok=True)
    (response / "batch-0001.attempt-01.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="prior provider attempts"):
        s.execute(tmp_path, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)
    assert s.execute(tmp_path, resume=True, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=_fake_cwr)["mode"] == "resume"


def test_settlement_four_state_marks_na_unscored_and_rejects_missing_slot(tmp_path: Path):
    s = study()
    _prepared(s, tmp_path)
    settled = s.settle(tmp_path, verifier=lambda _root, slot: _record(s, slot))
    assert settled["decision"] == "PASS_NO_CHANGE" and len(settled["per_cell_three_of_three"]) == 44
    public = json.loads((tmp_path / "public-aggregate.json").read_text(encoding="utf-8"))
    assert public["scored_cells"] == {"passed": 33, "total": 33}
    assert public["not_applicable_diagnostic_cells"] == {"matched": 11, "total": 11}
    other = tmp_path.parent / "missing"
    _prepared(s, other)
    incomplete = s.settle(other, verifier=lambda _root, slot: (_ for _ in ()).throw(ValueError("missing run")) if slot["slot_id"] == "p1-v1-audio-exposition-yes-r1" else _record(s, slot))
    assert incomplete["decision"] == "INCOMPLETE" and incomplete["completed_slots"] == 131


def test_runtime_bindings_have_no_head_dependency_and_public_package_has_no_private_result():
    s = study()
    assert "runtime_head" not in s._runtime_bindings()
    files = {path.name for path in ROOT.iterdir() if path.is_file()}
    assert files == {"README.md", "run.py", "study-contract.json", "study.py"}
    for path in (ROOT / name for name in files):
        text = path.read_text(encoding="utf-8")
        assert "C:\\Users\\" not in text and "Gray Blood" not in text and "raw_response" not in text


def test_checkpoint_prompt_rule_is_one_way_and_rejects_lone_cr_or_other_mutation(tmp_path: Path):
    s = study()
    run = tmp_path / "run"
    (run / "responses").mkdir(parents=True)
    rendered = tmp_path / "rendered.txt"
    rendered.write_bytes(b"alpha\nbeta\n")
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(__import__("gzip").compress(b"alpha\r\nbeta\r\n", mtime=0))
    assert s._verify_checkpoint_prompt(run, rendered)["canonical_prompt_sha256"] == hashlib.sha256(rendered.read_bytes()).hexdigest()
    rendered.write_bytes(b"alpha\r\nbeta\r\n")
    with pytest.raises(ValueError, match="canonical UTF-8 LF"):
        s._verify_checkpoint_prompt(run, rendered)
    rendered.write_bytes(b"alpha\nbeta\n")
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(__import__("gzip").compress(b"alpha\rbeta\n", mtime=0))
    with pytest.raises(ValueError, match="lone CR"):
        s._verify_checkpoint_prompt(run, rendered)
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(__import__("gzip").compress(b"alpha\ngamma\n", mtime=0))
    with pytest.raises(ValueError, match="beyond line endings"):
        s._verify_checkpoint_prompt(run, rendered)


def test_identical_prompt_and_config_checkpoint_from_another_run_is_rejected(tmp_path: Path, monkeypatch):
    s = study()
    slot = _prepared(s, tmp_path)[0]
    run = tmp_path / "runs" / slot["slot_id"]
    responses = run / "responses"
    responses.mkdir(parents=True, exist_ok=True)
    artifact = tmp_path / "inputs" / f"{slot['artifact_id']}.txt"
    config = {
        "provider": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "strict_ai": True,
        "batch_size": 1, "retry_policy": {"batch_attempts": 3}, "retry_semantics": "cumulative_batch_attempts_v1",
        "artifact_id": slot["artifact_id"], "bundle_id": s.BUNDLE_ID, "question_ids": [slot["leaf_id"]],
        "artifact": s._input_record(artifact), "contexts": [],
        "prompts": [{"sha256": s.sha256_file(s.REPOSITORY / "prompts" / "judge" / name)} for name in ("JUDGE_PREFIX.md", "BINARY_EVALUATION_PROMPT.md")],
        "response_schema": {"sha256": s.sha256_file(s.REPOSITORY / "schema" / "hbq_judge_response.schema.json")},
    }
    (run / "run.json").write_text(json.dumps({"format_version": 4, "run_id": "canonical-run", "configuration": config, "config_sha256": s.runner._sha256_bytes(s.runner._json_bytes(config))}), encoding="utf-8")
    prompt = tmp_path / "rendered-prompts" / f"{slot['slot_id']}.txt"
    (responses / "batch-0001.prompt.txt.gz").write_bytes(__import__("gzip").compress(prompt.read_bytes(), mtime=0))
    (responses / "batch-0001.json").write_text(json.dumps({"accepted_attempt": 1, "provider": {"reported": {"provider": "openai", "model": "gpt-5.6-sol", "reasoning_effort": "high", "session_id": "session-from-other-run"}}}), encoding="utf-8")
    transplanted = {
        "question_id": slot["leaf_id"], "run_id": "other-run", "verdict": slot["expected_verdict"],
        "evidence": [{"reference": "artifact", "exact_quote": str(slot["artifact_text"])[:20]}],
    }
    monkeypatch.setattr(s.runner, "_load_checkpoints", lambda *_args, **_kwargs: ([transplanted], 1, "a" * 64))
    monkeypatch.setattr(s.runner, "_rejected_records", lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match="run identity"):
        s._verify_slot(tmp_path, slot)
