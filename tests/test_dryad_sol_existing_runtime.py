from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "evaluation-results/hbq-human-alignment-dryad-full-hbq-analysis-v1/sol_existing_runtime.py"


def load():
    spec = importlib.util.spec_from_file_location("dryad_existing_sol_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_existing_launcher_loads_with_explicit_current_runner_pin():
    module = load()
    base = module._base()
    assert base.RUNNER_SHA256 == module.RUNNER_SHA256
    assert callable(base._load_call_codex())
    assert all(value is None for value in base._strict_stderr_labels(b"").values())
    with pytest.raises(ValueError, match="conflicts"):
        base._strict_stderr_labels(b"model: different-model\n")


def test_reuses_launcher_with_exact_batch_paths_and_one_gate(tmp_path, monkeypatch):
    module = load()
    (tmp_path / "responses").mkdir()
    schema = tmp_path / "schema.json"
    schema.write_bytes(b'{"type":"object"}')
    calls = []
    gates = []
    def base():
        value = SimpleNamespace(_expected_codex_command=lambda executable, root: [
            executable, "exec", "--output-schema", "old-schema", "--output-last-message", "old-message", "<prompt-via-stdin>"])
        def invoke(**kwargs):
            kwargs["before_provider_attempt"]()
            command = value._expected_codex_command(kwargs["executable"], kwargs["output_dir"])
            stderr = value._stderr_artifact(kwargs["output_dir"], b"synthetic stderr")
            calls.append((kwargs, command, stderr))
            return "{}", {"command": command}
        value._load_call_codex = lambda: invoke
        return value
    monkeypatch.setattr(module, "_base", base)
    for batch in (1, 2):
        module.call_codex(executable="codex", model="gpt-5.6-sol", reasoning="high", prompt="exact café\n",
            output_dir=tmp_path, response_schema=schema, batch_number=batch, timeout=30,
            before_provider_attempt=lambda: gates.append(1))
    assert len(gates) == len(calls) == 2
    for batch, (kwargs, command, descriptor) in enumerate(calls, 1):
        assert kwargs["prompt"] == "exact café\n" and kwargs["capture_jsonl_events"] is True
        assert command[command.index("--output-schema") + 1] == str(schema)
        assert command[command.index("--output-last-message") + 1].endswith(f"batch-{batch:04d}.attempt-0001.message.json")
        assert command[-3:] == ["--disable", "code_mode", "<prompt-via-stdin>"]
        assert descriptor["path"] == f"responses/batch-{batch:04d}.attempt-0001.stderr.bin"
    with pytest.raises(FileExistsError):
        module.call_codex(executable="codex", model="gpt-5.6-sol", reasoning="high", prompt="exact café\n",
            output_dir=tmp_path, response_schema=schema, batch_number=2, timeout=30,
            before_provider_attempt=lambda: None)


def test_retry_or_missing_gate_rejected_before_loading(monkeypatch):
    module = load()
    monkeypatch.setattr(module, "_base", lambda: pytest.fail("must not load"))
    with pytest.raises(ValueError, match="one cumulative"):
        module.call_codex(attempt_number=2)
    with pytest.raises(TypeError, match="precontact gate"):
        module.call_codex()
