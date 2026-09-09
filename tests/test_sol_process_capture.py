from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "hbqrs" / "sol_process_capture.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("sol_process_capture_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(root: Path) -> list[str]:
    return [
        "codex",
        "--output-last-message",
        str(root / "responses" / "batch-0001.attempt-0001.message.json"),
    ]


def receipt(root: Path) -> dict[str, Any]:
    return json.loads((root / "sol-process-completion-receipt.json").read_bytes())


@pytest.mark.parametrize("returncode", [0, 1])
def test_completed_receipt_retains_exit_code_and_final_message_hash(tmp_path: Path, returncode: int) -> None:
    value = load()
    root = tmp_path / "run"
    message = root / "responses" / "batch-0001.attempt-0001.message.json"
    message.parent.mkdir(parents=True)
    message.write_bytes(b'{"scores":{}}')

    class FakeSubprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        def run(self, *_args: Any, **_kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(returncode=returncode, stdout=b"events", stderr=b"stderr")

    completed = value.facade(FakeSubprocess()).run(command(root))

    actual = receipt(root)
    assert completed.returncode == returncode
    assert actual["state"] == "completed"
    assert actual["exit_code"] == returncode
    assert actual["stdout"] == {
        "bytes": len(b"events"),
        "sha256": hashlib.sha256(b"events").hexdigest(),
    }
    assert actual["final_message"] == {
        "exists": True,
        "bytes": len(message.read_bytes()),
        "sha256": hashlib.sha256(message.read_bytes()).hexdigest(),
    }


@pytest.mark.parametrize(
    "error",
    [
        subprocess.TimeoutExpired("codex", 1, output=b"partial events", stderr=b"timeout"),
        OSError("fixture process launch failure"),
    ],
)
def test_timeout_and_os_error_record_unknown_exit_code(tmp_path: Path, error: BaseException) -> None:
    value = load()
    root = tmp_path / "run"
    (root / "responses").mkdir(parents=True)

    class FakeSubprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        def run(self, *_args: Any, **_kwargs: Any) -> Any:
            raise error

    with pytest.raises(type(error)):
        value.facade(FakeSubprocess()).run(command(root))

    actual = receipt(root)
    assert actual["state"] == "exception"
    assert actual["exit_code"] is None
    assert actual["final_message"] == {"exists": False, "bytes": None, "sha256": None}


def test_existing_receipt_prevents_another_underlying_run(tmp_path: Path) -> None:
    value = load()
    root = tmp_path / "run"
    (root / "responses").mkdir(parents=True)
    (root / "sol-process-completion-receipt.json").write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    class FakeSubprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        def run(self, actual: list[str], **_kwargs: Any) -> Any:
            calls.append(actual)
            raise AssertionError("the prospective receipt must stop a resend")

    with pytest.raises(FileExistsError, match="receipt already exists"):
        value.facade(FakeSubprocess()).run(command(root))

    assert calls == []


def test_facade_uses_only_its_injected_subprocess_module(tmp_path: Path) -> None:
    value = load()
    root = tmp_path / "run"
    message = root / "responses" / "batch-0001.attempt-0001.message.json"
    message.parent.mkdir(parents=True)
    message.write_text("{}", encoding="utf-8")
    original_run = subprocess.run
    calls: list[list[str]] = []

    class FakeSubprocess:
        TimeoutExpired = subprocess.TimeoutExpired

        def run(self, actual: list[str], **_kwargs: Any) -> SimpleNamespace:
            calls.append(actual)
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    wrapper = value.facade(FakeSubprocess())
    assert wrapper.TimeoutExpired is subprocess.TimeoutExpired
    assert subprocess.run is original_run
    wrapper.run(command(root))

    assert calls == [command(root)]
    assert subprocess.run is original_run
