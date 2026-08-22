"""Immutable bindings and safe output helpers for Fresh88 primary analysis."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
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
    contract = read_json(CONTRACT_PATH)
    required = {"format_version", "study_id", "kind", "analysis_only", "predecessor", "dataset", "analysis", "analysis_sources", "outputs", "interpretation_limits"}
    if set(contract) != required or contract["format_version"] != 1 or contract["study_id"] != "hbq-human-alignment-v3-fresh88-analysis-v1" or contract["kind"] != "offline_primary_development_analysis" or contract["analysis_only"] is not True or contract["outputs"] != ["summary.json", "items.jsonl", "manifest.json"]:
        raise ValueError("Fresh88 analysis contract identity drifted")
    predecessor = contract["predecessor"]
    if not isinstance(predecessor, Mapping) or predecessor.get("study_id") != "hbq-human-alignment-v3-successor-v1" or any(not isinstance(predecessor.get(key), str) or len(str(predecessor[key])) != 64 for key in predecessor if key.endswith("sha256")):
        raise ValueError("Fresh88 analysis predecessor pins are invalid")
    dataset = contract["dataset"]
    if not isinstance(dataset, Mapping) or dataset.get("license") != "MIT" or dataset.get("csv_name") != "hanna_stories_annotations.csv" or dataset.get("license_name") != "LICENSE" or any(not isinstance(dataset.get(key), str) or len(dataset[key]) != 64 for key in ("csv_sha256", "license_sha256")):
        raise ValueError("Fresh88 analysis dataset pins are invalid")
    analysis = contract["analysis"]
    if not isinstance(analysis, Mapping) or tuple(analysis.get("dimensions", ())) != ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity") or not isinstance(analysis.get("mapping_sets_sha256"), str) or len(analysis["mapping_sets_sha256"]) != 64 or analysis.get("primary_generated_only") != {"exclude_source_model": "Human", "item_count": 80} or analysis.get("secondary_all_11") != {"item_count": 88} or analysis.get("bootstrap") != {"cluster": "prompt_group_id", "draws": 1000, "primary_base_seed": 560820, "secondary_base_seed": 560920, "macro_seed": 560820} or analysis.get("output_order") != {"canonical_selection": "authority.fresh_complement.item_ids", "execution": "authority.fresh_complement.scheduled_item_ids"}:
        raise ValueError("Fresh88 analysis methodology pins are invalid")
    sources = contract["analysis_sources"]
    prefix = "evaluation-results/hbq-human-alignment-v3-fresh88-analysis-v1/"
    if not isinstance(sources, Mapping) or set(sources) != {"analyze.py", "study.py"} or any(not isinstance(value, Mapping) or value.get("path") != prefix + name or not isinstance(value.get("bytes"), int) or isinstance(value["bytes"], bool) or value["bytes"] < 1 or not isinstance(value.get("sha256"), str) or len(value["sha256"]) != 64 for name, value in sources.items()):
        raise ValueError("Fresh88 analysis source pins are invalid")
    return contract


CONTRACT = load_contract()


def _same_or_below(left: Path, right: Path) -> bool:
    try:
        left.resolve().relative_to(right.resolve())
        return True
    except ValueError:
        return False


def ensure_output_disjoint(output: Path, roots: Iterable[Path]) -> None:
    target = output.resolve()
    for root in roots:
        candidate = root.resolve()
        if _same_or_below(target, candidate) or _same_or_below(candidate, target):
            raise ValueError("Public output must be disjoint from every private evidence root")


def atomic_output_directory(output: Path, files: Mapping[str, str]) -> None:
    if output.exists():
        raise ValueError("Refusing to overwrite or merge an existing analysis output")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        for name, contents in files.items():
            path = staging / name
            path.write_text(contents, encoding="utf-8", newline="\n")
        os.rename(staging, output)
    except BaseException:
        if staging.exists():
            for path in staging.iterdir():
                if path.is_file():
                    path.unlink()
            staging.rmdir()
        raise
