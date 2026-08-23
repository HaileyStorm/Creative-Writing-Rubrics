from __future__ import annotations

import gzip
import importlib.util
import inspect
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from hbqrs.paths import book_root


ROOT = book_root() / "evaluation-results" / "hbq-figurative-metaphor-checklist-successor-v1-execution-v1"


def study():
    spec = importlib.util.spec_from_file_location("fmcs_phase_a_execution", ROOT / "study.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def external_private():
    root = Path(tempfile.mkdtemp(prefix="hbq-fmcs-phase-a-executor-"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def fake_cwr(command, **_kwargs):
    if "render-judge" in command:
        leaf = command[command.index("--question-id") + 1]
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"current production prompt for {leaf}\r\n".encode("utf-8"))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    if "--dry-run" in command:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text(json.dumps({"format_version": 5, "configuration": {"compiled_bundle_sha256": "f" * 64}}), encoding="utf-8")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_exact_predecessor_runtime_privacy_and_phase_stops_are_frozen(monkeypatch):
    s = study()
    assert s.validate_package() == {"study_id": s.STUDY_ID, "slots": 72, "provider_calls": 0, "phase_b_enabled": False, "real_holdout_opened": False}
    baseline = s.contract()
    for section, key in (("privacy", "real_holdout"), ("phase_a_stops", "controls"), ("execution", "batch_attempts"), ("runtime_bindings", "prompt")):
        mutated = json.loads(json.dumps(baseline))
        mutated[section][key] = "mutated"
        monkeypatch.setattr(s, "contract", lambda value=mutated: value)
        with pytest.raises(ValueError, match="contract drifted"):
            s.validate_package()
    assert baseline["predecessor"]["commit"] == "a02418f"
    assert baseline["execution"]["run_manifest_format_version"] == 5


def test_dry_run_uses_real_cwr_command_shape_and_freezes_disclosure(external_private):
    s = study()
    report = s.dry_run(external_private, runner_call=fake_cwr)
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    assert report["provider_calls"] == 0 and report["rendered_prompts"] == 72
    schedule = json.loads((root / "runtime-schedule.v1.json").read_text(encoding="utf-8"))["slots"]
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "study-manifest.v1.json").read_text(encoding="utf-8"))
    assert len(schedule) == len(disclosure["slots"]) == 72
    assert disclosure["attempt_lifecycle_policy"] == "terminal_sidecar_v1"
    assert disclosure["retry_or_resume"] == "forbidden"
    assert (root / "catalog" / "registry.json").is_file()
    assert manifest["runtime_bindings"]["cwr_head"] == s._git("rev-parse", "HEAD")
    prompt = next((root / "rendered-prompts").glob("*.txt")).read_bytes()
    assert prompt.endswith(b"\n") and prompt.strip()


def test_production_command_is_singleton_gated_and_has_required_bindings(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr)
    slot = s._validated_runtime_schedule(external_private)[0]
    command = s.command_for(slot, external_private)
    joined = " ".join(command)
    for flag in ("--registry", "--bundles", "--bundle", "--artifact-id", "--task-contract", "--scope-compatibility-override", "--question-id", "--attempt-lifecycle-policy"):
        assert flag in command
    assert command[command.index("--batch-size") + 1] == "1"
    assert command[command.index("--batch-attempts") + 1] == "1"
    assert command[command.index("--attempt-lifecycle-policy") + 1] == "terminal_sidecar_v1"
    assert "--resume" not in command and "expected_verdict" not in joined and "case_id" not in joined
    assert "--allow-remote" not in command and s.command_for(slot, external_private, allow_remote=True)[-1] == "--allow-remote"


def test_execute_requires_dual_gate_and_has_no_resume_or_retry_path(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(external_private, runner_call=fake_cwr)
    assert s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr)["executed_slots"] == 72
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    assert json.loads((root / "receipts" / "zero-charge-acknowledgement.v1.json").read_text(encoding="utf-8"))["paid_fallback"] == "forbidden"
    another = external_private.parent / (external_private.name + "-existing")
    try:
        s.dry_run(another, runner_call=fake_cwr)
        (another / s.PRIVATE_EXECUTION_DIRECTORY / "runs" / "already").mkdir(parents=True)
        with pytest.raises(ValueError, match="pre-existing"):
            s.execute(another, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr)
    finally:
        shutil.rmtree(another, ignore_errors=True)
    assert "resume" not in inspect.signature(s.execute).parameters


def test_settlement_accepts_no_caller_records_and_prompt_receipt_is_exact(external_private):
    s = study()
    assert set(inspect.signature(s.settle).parameters) == {"private_root"}
    s.dry_run(external_private, runner_call=fake_cwr)
    incomplete = s.settle(external_private)
    assert incomplete["decision"] == "INCOMPLETE" and incomplete["phase_b_enabled"] is False
    run = external_private / "checkpoint"
    (run / "responses").mkdir(parents=True)
    prompt = external_private / "prompt.txt"
    prompt.write_bytes(b"alpha\nbeta\n")
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"alpha\r\nbeta\r\n", mtime=0))
    assert s._verify_checkpoint_prompt(run, prompt)["canonical_prompt_sha256"] == s.sha256_file(prompt)
    (run / "responses" / "batch-0001.prompt.txt.gz").write_bytes(gzip.compress(b"alpha\ngamma\n", mtime=0))
    with pytest.raises(ValueError, match="exact rendered"):
        s._verify_checkpoint_prompt(run, prompt)


def test_terminal_incomplete_result_blocks_any_later_execution(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr)
    assert s.settle(external_private)["decision"] == "INCOMPLETE"
    with pytest.raises(ValueError, match="terminal settlement"):
        s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr)


def test_real_format5_dry_manifest_and_output_prompt_shape(external_private):
    s = study()
    s.prepare(external_private)
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    slot = s.build_schedule()[0]
    dry = subprocess.run([*s.command_for(slot, external_private, output_root="dry-runs"), "--dry-run"], text=True, capture_output=True, check=False)
    assert dry.returncode == 0, dry.stderr
    manifest = json.loads((root / "dry-runs" / slot["slot_id"] / "run.json").read_text(encoding="utf-8"))
    config = manifest["configuration"]
    assert manifest["format_version"] == 5
    assert isinstance(config["compiled_bundle_sha256"], str) and len(config["compiled_bundle_sha256"]) == 64
    assert "registry" not in config
    prompt = root / "single-real-render.txt"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    rendered = subprocess.run(s._render_command(slot, root, prompt), text=True, capture_output=True, check=False)
    assert rendered.returncode == 0, rendered.stderr
    raw = prompt.read_bytes()
    canonical = s.canonical_prompt_bytes(raw)
    assert len(raw) > 1000 and canonical.endswith(b"\n") and len(canonical) >= 1000
