"""Fail-closed deployment seam for the matched Grok/Sol screen.

There is no locally trustable account/receipt authority.  This module therefore
only identifies the exact launcher/backend bytes and reports that dispatch is
unavailable.  A deployment environment must replace this whole reviewed module
with an independently attested successor; callers cannot inject a verifier or
backend through the public orchestrator API.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
BOOK = HERE.parents[1]
sys.path.insert(0, str(BOOK / "src"))
from hbqrs import runner  # noqa: E402


def _binding(path: Path) -> dict[str, Any]:
    value = path.read_bytes()
    return {"name": path.name, "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}


def identity() -> dict[str, Any]:
    commands = {}
    for name in ("codex", "grok"):
        resolved = shutil.which(name)
        commands[name] = _binding(Path(resolved).resolve()) if resolved else {"status": "not_found"}
    return {
        "format_version": 1,
        "launcher": _binding(HERE / "trusted_launcher.py"),
        "orchestrator": _binding(HERE / "orchestrator.py"),
        "backend": _binding(Path(runner.__file__).resolve()),
        "backend_symbol": "hbqrs.runner.run_judge",
        "python": _binding(Path(sys.executable).resolve()),
        "commands": commands,
        "status": "no_local_trust_anchor",
    }


def verify_external_launch(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("No independently trusted launch authority is installed on this host; remote dispatch is disabled")
