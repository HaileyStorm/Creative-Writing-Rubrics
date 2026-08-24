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
    if command[-1] == "--version":
        return SimpleNamespace(returncode=0, stdout="codex-cli test-version\n", stderr="")
    if command[-2:] == ["login", "status"]:
        return SimpleNamespace(returncode=0, stdout="Logged in using ChatGPT\n", stderr="")
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
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    callbacks = []

    def inspect_frozen_runtime(command, **kwargs):
        if "--dry-run" in command:
            assert (root / "study-manifest.v1.json").is_file()
        if "render-judge" in command:
            assert kwargs["env"]["NO_COLOR"] == "1"
        callbacks.append(command)
        return fake_cwr(command, **kwargs)

    report = s.dry_run(external_private, runner_call=inspect_frozen_runtime, auth_call=fake_cwr)
    assert report["provider_calls"] == 0 and report["rendered_prompts"] == 72
    schedule = json.loads((root / "runtime-schedule.v1.json").read_text(encoding="utf-8"))["slots"]
    disclosure = json.loads((root / "receipts" / "preexecution-disclosure.v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "study-manifest.v1.json").read_text(encoding="utf-8"))
    assert len(schedule) == len(disclosure["slots"]) == 72
    assert disclosure["attempt_lifecycle_policy"] == "terminal_sidecar_v1"
    assert disclosure["retry_or_resume"] == "forbidden"
    assert disclosure["remote_destination"] == "Codex CLI -> authenticated OpenAI service"
    assert disclosure["dispatch_authentication"]["authentication"] == "chatgpt_subscription"
    assert disclosure["dispatch_authentication"]["codex_executable_path"].endswith(".exe")
    assert (root / "catalog" / "registry.json").is_file()
    assert manifest["runtime_bindings"]["cwr_head"] == s._git("rev-parse", "HEAD")
    prompt = next((root / "rendered-prompts").glob("*.txt")).read_bytes()
    assert prompt.endswith(b"\n") and prompt.strip()
    assert len(callbacks) == 144


def test_dry_run_rejects_runtime_drift_after_freezing_manifest(external_private, monkeypatch):
    s = study()
    original = s._runtime_bindings
    calls = 0

    def drifting_bindings():
        nonlocal calls
        calls += 1
        value = original()
        if calls > 1:
            value["cwr_head"] = "drifted-after-freeze"
        return value

    monkeypatch.setattr(s, "_runtime_bindings", drifting_bindings)
    with pytest.raises(ValueError, match="drifted during dry-run"):
        s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)


def test_production_command_is_singleton_gated_and_has_required_bindings(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
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
    binary = s._load_json(external_private / s.PRIVATE_EXECUTION_DIRECTORY / "receipts" / "subscription-authentication.v1.json")["codex_executable_path"]
    dispatched = s.command_for(slot, external_private, allow_remote=True, codex_binary=binary)
    assert dispatched[dispatched.index("--codex-bin") + 1] == binary


def test_execute_requires_dual_gate_and_has_no_resume_or_retry_path(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    with pytest.raises(ValueError, match="allow-remote"):
        s.execute(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    assert s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr, auth_call=fake_cwr)["executed_slots"] == 72
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    assert json.loads((root / "receipts" / "zero-charge-acknowledgement.v1.json").read_text(encoding="utf-8"))["paid_fallback"] == "forbidden"
    another = external_private.parent / (external_private.name + "-existing")
    try:
        s.dry_run(another, runner_call=fake_cwr, auth_call=fake_cwr)
        (another / s.PRIVATE_EXECUTION_DIRECTORY / "runs" / "already").mkdir(parents=True)
        with pytest.raises(ValueError, match="pre-existing"):
            s.execute(another, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr, auth_call=fake_cwr)
    finally:
        shutil.rmtree(another, ignore_errors=True)
    assert "resume" not in inspect.signature(s.execute).parameters


def test_settlement_accepts_no_caller_records_and_prompt_receipt_is_exact(external_private):
    s = study()
    assert set(inspect.signature(s.settle).parameters) == {"private_root"}
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    incomplete = s.settle(external_private)
    assert incomplete["decision"] == "INCOMPLETE" and incomplete["phase_b_enabled"] is False
    assert "execution claim" in incomplete["failures"][0]["reason"]
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
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    assert s.settle(external_private)["decision"] == "INCOMPLETE"
    with pytest.raises(ValueError, match="terminal settlement"):
        s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr, auth_call=fake_cwr)


def test_authentication_drift_fails_before_any_dispatch(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)

    def drifted_auth(command, **kwargs):
        if command[-1] == "--version":
            return SimpleNamespace(returncode=0, stdout="codex-cli changed-version\n", stderr="")
        return fake_cwr(command, **kwargs)

    with pytest.raises(ValueError, match="authentication evidence drifted"):
        s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=fake_cwr, auth_call=drifted_auth)
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    assert (root / "execution-claim.v1.json").is_file()
    assert not (root / "receipts" / "zero-charge-acknowledgement.v1.json").exists()
    assert not (root / "runs").exists()


def test_atomic_execution_claim_blocks_contention_before_the_second_callback(external_private):
    s = study()
    s.dry_run(external_private, runner_call=fake_cwr, auth_call=fake_cwr)
    callbacks = []

    def dispatch(command, **kwargs):
        callbacks.append((command, kwargs))
        return fake_cwr(command, **kwargs)

    assert s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=dispatch, auth_call=fake_cwr)["executed_slots"] == 72
    first_count = len(callbacks)
    with pytest.raises(ValueError, match="durable claim"):
        s.execute(external_private, allow_remote=True, acknowledged_zero_incremental_charge=True, runner_call=dispatch, auth_call=fake_cwr)
    assert first_count == 72 and len(callbacks) == first_count
    claim = json.loads((external_private / s.PRIVATE_EXECUTION_DIRECTORY / "execution-claim.v1.json").read_text(encoding="utf-8"))
    assert claim["state"] == "claimed_no_retry_or_resume" and claim["provider_capable_dispatches"] == 72
    assert claim["frozen_inputs"]["study_manifest_sha256"] == s.sha256_file(external_private / s.PRIVATE_EXECUTION_DIRECTORY / "study-manifest.v1.json")


def test_real_format5_dry_manifest_and_output_prompt_shape(external_private, monkeypatch):
    s = study()
    s.prepare(external_private)
    root = external_private / s.PRIVATE_EXECUTION_DIRECTORY
    slot = s.build_schedule()[0]
    monkeypatch.setenv("PYTHONPATH", "arbitrary-parent-pythonpath")
    environment = s._minimal_environment()
    assert environment["PYTHONPATH"] == str((s.REPOSITORY / "src").resolve())
    assert not any(name in environment for name in s.BILLING_CREDENTIAL_ENVIRONMENT_NAMES)
    imported = subprocess.run([sys.executable, "-c", "import hbqrs; print(hbqrs.__file__)"], text=True, capture_output=True, check=False, env=environment)
    assert imported.returncode == 0, imported.stderr
    assert Path(imported.stdout.strip()).resolve().is_relative_to((s.REPOSITORY / "src").resolve())
    dry = subprocess.run([*s.command_for(slot, external_private, output_root="dry-runs"), "--dry-run"], text=True, capture_output=True, check=False, env=environment)
    assert dry.returncode == 0, dry.stderr
    manifest = json.loads((root / "dry-runs" / slot["slot_id"] / "run.json").read_text(encoding="utf-8"))
    config = manifest["configuration"]
    assert manifest["format_version"] == 5
    assert isinstance(config["compiled_bundle_sha256"], str) and len(config["compiled_bundle_sha256"]) == 64
    assert "registry" not in config
    prompt = root / "single-real-render.txt"
    prompt.parent.mkdir(parents=True, exist_ok=True)
    rendered = subprocess.run(s._render_command(slot, root, prompt), text=True, capture_output=True, check=False, env=environment)
    assert rendered.returncode == 0, rendered.stderr
    raw = prompt.read_bytes()
    canonical = s.canonical_prompt_bytes(raw)
    assert len(raw) > 1000 and canonical.endswith(b"\n") and len(canonical) >= 1000
