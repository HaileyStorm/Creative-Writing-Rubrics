"""Contract and immutable-output helpers for the Fresh88 overlap analysis."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve().parent
CONTRACT_PATH = HERE / "study-contract.json"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": sha(path)}


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_contract() -> dict[str, Any]:
    value = read_json(CONTRACT_PATH)
    expected = {"format_version", "study_id", "kind", "analysis_only", "source_study", "outputs", "views", "interpretation_limits"}
    if set(value) != expected or value["format_version"] != 1 or value["study_id"] != "hbq-human-alignment-v3-fresh88-overlap-analysis-v1" or value["kind"] != "offline_frozen_descriptive_overlap_analysis" or value["analysis_only"] is not True:
        raise ValueError("Fresh88 overlap-analysis contract identity drifted")
    if value["source_study"] != "hbq-human-alignment-v3-fresh88-analysis-v1" or value["outputs"] != ["summary.json", "leaf-diagnostics.jsonl", "manifest.json"]:
        raise ValueError("Fresh88 overlap-analysis contract output binding drifted")
    if value["views"] != ["six_dimension_macro", "unique_27_leaf_overlap", "occurrence_weighted_28_mapping", "hierarchical_dimension_to_macro", "native_hbq_domains_and_final"]:
        raise ValueError("Fresh88 overlap-analysis view contract drifted")
    return value


CONTRACT = load_contract()


def _same_or_below(left: Path, right: Path) -> bool:
    try:
        left.resolve().relative_to(right.resolve())
        return True
    except ValueError:
        return False


def ensure_output_disjoint(output: Path, roots: Iterable[Path]) -> None:
    for root in roots:
        if _same_or_below(output, root) or _same_or_below(root, output):
            raise ValueError("Public output must be disjoint from every private evidence root")


def atomic_output_directory(output: Path, files: Mapping[str, str]) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite or merge an existing analysis output")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for name, text in files.items():
            (staging / name).write_text(text, encoding="utf-8", newline="\n")
        os.rename(staging, output)
    except BaseException:
        if staging.exists():
            for path in staging.iterdir():
                if path.is_file():
                    path.unlink()
            staging.rmdir()
        raise
