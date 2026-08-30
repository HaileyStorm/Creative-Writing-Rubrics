"""Held-out analysis remains intentionally unavailable until a pinned native verifier lands."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
STUDY_PATH = HERE / "study.py"


def _study() -> Any:
    spec = importlib.util.spec_from_file_location("_hanna_heldout_study", STUDY_PATH)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA held-out analyzer cannot load its schedule module")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def analyze(*, schedule: Mapping[str, Any], reconciliation_manifest_path: Path,
            frozen_successor_path: Path,
            hanna_csv_path: Path, projection_path: Path | None = None,
            verifier: Any | None = None) -> dict[str, Any]:
    """Reject execution until an exact pinned native held-out executor/verifier exists.

    The independently regenerated schedule check is deliberately retained before the
    NO-GO result so a future executor cannot accept a self-rehashed caller schedule.
    """
    if verifier is not None or projection_path is not None:
        raise ValueError("HANNA held-out analysis has no native executor/verifier pin; synthetic callbacks and projections are NO-GO")
    study = _study()
    expected = study.build_schedule(reconciliation_manifest_path=Path(reconciliation_manifest_path), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    if study.canonical(dict(schedule)) != study.canonical(expected):
        raise ValueError("HANNA held-out supplied schedule does not byte-match the independently reconstructed frozen schedule")
    raise ValueError("HANNA held-out analysis is NO-GO until a pinned native executor/verifier binds all 66 cells, payloads, endpoint identities, contacts, and projection bytes")
