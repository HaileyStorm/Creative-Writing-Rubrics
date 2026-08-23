from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


def test_artifact_receipt_families_3_4_verify() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/verify_artifact_receipt_families_3_4_v1.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "artifact receipt families 3 and 4: PASS\n"


def test_artifact_receipt_verifier_rejects_local_path_leaks() -> None:
    root = Path(__file__).resolve().parents[1]
    path = root / "scripts" / "verify_artifact_receipt_families_3_4_v1.py"
    specification = importlib.util.spec_from_file_location("artifact_receipt_verifier", path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)

    with pytest.raises(ValueError, match="leaks a local or private path"):
        module._check_public_safety({"path": r"C:\\Users\\example\\private.json"})
