"""Prospective metadata-only capture for one native Sol child process."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bytes(value: Any) -> bytes:
    return value if isinstance(value, bytes) else (value or "").encode("utf-8")


def _receipt_path(command: list[str]) -> tuple[Path, Path]:
    index = command.index("--output-last-message") + 1
    message = Path(command[index])
    return message, message.parent.parent / "sol-process-completion-receipt.json"


def _write(path: Path, value: dict[str, Any]) -> None:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)


def _record(receipt: Path, message: Path, *, state: str, exit_code: int | None,
            stdout: Any, stderr: Any) -> None:
    def stream(value: Any) -> dict[str, Any]:
        raw = _bytes(value)
        return {"bytes": len(raw), "sha256": _sha(raw)}

    try:
        final = message.read_bytes()
    except FileNotFoundError:
        final_message = {"exists": False, "bytes": None, "sha256": None}
    except OSError:
        # A diagnostic-file read must not discard the child's observed status.
        final_message = {"exists": None, "bytes": None, "sha256": None, "read_error": True}
    else:
        final_message = {"exists": True, "bytes": len(final), "sha256": _sha(final)}
    _write(receipt, {"format_version": 1, "state": state, "exit_code": exit_code,
                     "stdout": stream(stdout), "stderr": stream(stderr), "final_message": final_message})


class Facade:
    def __init__(self, subprocess_module: Any, *, receipt_root: Path | None = None):
        self._module = subprocess_module
        self.TimeoutExpired = subprocess_module.TimeoutExpired
        self._receipt_root = receipt_root

    def run(self, command: list[str], *args: Any, **kwargs: Any) -> Any:
        message, receipt = _receipt_path(command)
        if self._receipt_root is not None:
            receipt = self._receipt_root / f"{message.parent.parent.name}.json"
        if receipt.exists():
            raise FileExistsError("Sol process completion receipt already exists")
        try:
            completed = self._module.run(command, *args, **kwargs)
        except (OSError, self.TimeoutExpired) as error:
            _record(receipt, message, state="exception", exit_code=None,
                    stdout=getattr(error, "stdout", None), stderr=getattr(error, "stderr", None))
            raise
        _record(receipt, message, state="completed", exit_code=completed.returncode,
                stdout=completed.stdout, stderr=completed.stderr)
        return completed


def facade(subprocess_module: Any, *, receipt_root: Path | None = None) -> Facade:
    return Facade(subprocess_module, receipt_root=receipt_root)
