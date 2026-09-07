"""Adapt the established Sol CLI lifecycle to current Dryad batch paths."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parents[1]
BASE = ROOT.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v3/executor.py"
BASE_SHA256 = "cea177b5185a84b682bd5271ae7384cd7742add872d31b45227433d72c7f7e90"
RUNNER = REPOSITORY / "src/hbqrs/runner.py"
RUNNER_SHA256 = "3af6dd86088fddb91c2979ed6ddef00efb3da767e959972f8ee1ee0c1ab034f6"


def _verify() -> None:
    for path, expected in ((BASE, BASE_SHA256), (RUNNER, RUNNER_SHA256)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Sol existing-runtime source differs")


def _base() -> Any:
    _verify()
    name = f"_dryad_existing_sol_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, BASE)
    if spec is None or spec.loader is None:
        raise ValueError("Sol existing lifecycle cannot load")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    # This prospective composition uses the current, explicitly pinned runner.
    # Historical modules and their persisted receipts retain their original pins.
    module.RUNNER_SHA256 = RUNNER_SHA256
    return module


def call_codex(**kwargs: Any) -> tuple[str, dict[str, Any]]:
    """Reuse v3's single launch and raw evidence capture, without provider attestation."""
    if kwargs.get("attempt_number", 1) != 1:
        raise ValueError("Dryad Sol permits one cumulative attempt per batch")
    gate = kwargs.get("before_provider_attempt")
    if not callable(gate):
        raise TypeError("Dryad Sol requires its caller's precontact gate")
    root = Path(kwargs["output_dir"]).resolve()
    batch = kwargs["batch_number"]
    if type(batch) is not int or batch < 1:
        raise ValueError("Dryad Sol batch number differs")
    schema = Path(kwargs["response_schema"]).resolve()
    schema.relative_to(root)
    module = _base()
    original_command = module._expected_codex_command

    def command(executable: str, output_root: Path) -> list[str]:
        value = original_command(executable, output_root)
        value[value.index("--output-schema") + 1] = str(schema)
        value[value.index("--output-last-message") + 1] = str(
            root / "responses" / f"batch-{batch:04d}.attempt-0001.message.json")
        value[-1:-1] = ["--disable", "code_mode"]
        return value

    def stderr_artifact(output_root: Path, raw: bytes) -> dict[str, Any]:
        path = output_root / "responses" / f"batch-{batch:04d}.attempt-0001.stderr.bin"
        with path.open("xb") as output:
            output.write(raw)
        return {"path": path.relative_to(output_root).as_posix(), "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}

    def before_contact() -> None:
        _verify()
        gate()

    module._expected_codex_command = command
    module._stderr_artifact = stderr_artifact
    invoke = module._load_call_codex()
    result = invoke(**{**kwargs, "capture_jsonl_events": True, "before_provider_attempt": before_contact})
    _verify()
    return result
