"""CLI-free helper for replaying the successor's one-way development decision."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from study import create_development_gate, permit_phase, read_json


def create_gate(work: Path, artifact_root: Path, authority_root: Path) -> dict[str, Any]:
    return create_development_gate(work, artifact_root, authority_root)


def validate_gate(work: Path, artifact_root: Path, authority_root: Path) -> dict[str, Any]:
    gate = read_json(work / "semantic-development-gate.json")
    if gate.get("study_id") != "hbq-human-alignment-v3-successor-v1" or gate.get("phase") != "semantic_development_gate":
        raise ValueError("Successor development gate does not bind the frozen work")
    if gate.get("development_mode") != "fresh_88":
        raise ValueError("Successor development gate has an unsupported development mode")
    permit_phase(work, "repeatability", artifact_root, authority_root)
    return gate
