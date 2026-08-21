#!/usr/bin/env python3
"""Verify the public established-v4 analysis package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "publication-manifest.json"
PRIVATE_TEXT = re.compile(r"(?:^|[^A-Za-z])[A-Za-z]:[\\/]|/home/|\\Users\\|session_id|api[_-]?key|OPENAI_API_KEY|NOUS_API_KEY|provider_artifacts|raw_(?:content|response)", re.IGNORECASE)


def verify(root: Path = HERE) -> dict:
    manifest_path = root / MANIFEST.name
    manifest_text = manifest_path.read_text(encoding="utf-8")
    if PRIVATE_TEXT.search(manifest_text):
        raise ValueError("Publication manifest contains a private runtime field")
    manifest = json.loads(manifest_text)
    if manifest.get("format_version") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Publication manifest is malformed")
    expected_files = set(manifest["files"]) | {MANIFEST.name, Path(__file__).name}
    expected_entries = set(expected_files)
    for relative in expected_files:
        parent = Path(relative).parent
        while parent != Path("."):
            expected_entries.add(parent.as_posix())
            parent = parent.parent
    python_sources = {Path(relative) for relative in expected_files if Path(relative).suffix == ".py"}

    def regenerable_cache_entry(path: Path) -> bool:
        relative = path.relative_to(root)
        if path.is_dir():
            return relative.name == "__pycache__" and any(source.parent == relative.parent for source in python_sources)
        if not path.is_file() or relative.parent.name != "__pycache__" or relative.suffix != ".pyc":
            return False
        source_parent = relative.parent.parent
        return any(source.parent == source_parent and relative.name.startswith(f"{source.stem}.") for source in python_sources)

    actual_entries = {path.relative_to(root).as_posix() for path in root.rglob("*") if not regenerable_cache_entry(path)}
    if actual_entries != expected_entries:
        raise ValueError(f"Results directory contains unexpected or missing entries: {sorted(actual_entries ^ expected_entries)}")
    for relative, expected in manifest["files"].items():
        path = root / relative
        content = path.read_bytes()
        if not path.is_file() or len(content) != expected.get("bytes") or hashlib.sha256(content).hexdigest() != expected.get("sha256"):
            raise ValueError(f"Published artifact does not match its manifest: {relative}")
        if PRIVATE_TEXT.search(content.decode("utf-8")):
            raise ValueError(f"Published artifact contains a private runtime field: {relative}")
    study_root = root.parent
    contract_path = study_root / "study-contract.json"
    contract_bytes = contract_path.read_bytes()
    if hashlib.sha256(contract_bytes).hexdigest() != manifest.get("protocol_contract_sha256"):
        raise ValueError("Parent study contract does not match the publication manifest")
    contract = json.loads(contract_bytes)
    source_spec = contract.get("source")
    if contract.get("study_id") != manifest.get("study_id") or not isinstance(source_spec, dict) or source_spec.get("publication_authorized") is not True:
        raise ValueError("Parent study contract does not authorize this publication")
    relative_source = Path(str(source_spec.get("path", "")))
    if relative_source.is_absolute():
        raise ValueError("Published source path must be repository-relative")
    source = (study_root / relative_source).resolve()
    repository = study_root.parents[2].resolve()
    try:
        source.relative_to(repository)
    except ValueError as exc:
        raise ValueError("Published source path escapes the repository") from exc
    source_content = source.read_bytes()
    if len(source_content) != source_spec.get("bytes") or hashlib.sha256(source_content).hexdigest() != source_spec.get("sha256"):
        raise ValueError("Authorized published source does not match the frozen contract")
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
    if summary.get("study_id") != manifest.get("study_id") or summary.get("protocol_contract_sha256") != manifest.get("protocol_contract_sha256"):
        raise ValueError("Summary does not bind to the publication manifest")
    if provenance.get("study_id") != manifest.get("study_id") or provenance.get("protocol_contract_sha256") != manifest.get("protocol_contract_sha256"):
        raise ValueError("Provenance does not bind to the publication manifest")
    return manifest


if __name__ == "__main__":
    verified = verify()
    print(f"Verified {len(verified['files'])} public established-v4 artifacts.")
