#!/usr/bin/env python3
"""Provider-free normalization of the immutable 544af81 Grok next-wave terminal evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-normalize-v1"
SOURCE_STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-exec-v1"
SOURCE_COMMIT = "544af81c20b24545aca9d12e9ab3c4ced2a183f2"
SOURCE_EXECUTOR = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-exec-v1" / "executor.py"
SOURCE_EXECUTOR_SHA256 = "6c34f0a42db0e06ff717d28a1f80d5c943d4d19d6deb6d6a912ff4e1fbe588e1"
SOURCE_CATALOG_SHA256 = "6f0805518381a16b98d4dc87aad7acefc7d259f0ae098202b87b1a32aea4006b"
SOURCE_TREE_SHA256 = "ee64d219d23de840ba0b24b04aa5801a1ed64b5a54b86bd42472f91ef56eca1f"
SOURCE_CATALOG_MANIFEST_SHA256 = "5ce4d2baeaa0bf6a296446e82e3e45b03a3a51ae7478121ffeab189579d8eb3d"
NORMALIZED_VERSION = "f20-nextwave-local-normalized-v1"
EXPECTED_FACTORS = ("construct_framing", "human_reference_variant", "missing_evidence_not_no", "scope_materiality")
EXPECTED_RESPONSES = frozenset({"batch-0001.attempt-0001.prompt.txt", "batch-0001.attempt-0001.grok.envelope.json"})


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError(f"unsafe/reparsed path: {path}")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError(f"unexpected path type: {path}")


def _safe_ancestry(path: Path) -> Path:
    absolute = Path(os.path.abspath(path)); current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists(): _plain(current, directory=True)
    return absolute


def _under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _disjoint(output: Path, source: Path) -> None:
    repo = _safe_ancestry(HERE.parents[1])
    if any(_under(left, right) or _under(right, left) for left, right in ((output, source), (output, repo), (source, repo))):
        raise ValueError("source, output, and repository must be pairwise disjoint")


def stable(path: Path) -> bytes:
    path = Path(os.path.abspath(path)); current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part; _plain(current, directory=current != path)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno()); raw = handle.read(); after = os.fstat(handle.fileno())
    key = (before.st_dev, before.st_ino, before.st_size)
    if key != (opened.st_dev, opened.st_ino, opened.st_size) or key != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError("file changed during stable read")
    return raw


def _json(raw: bytes, label: str) -> dict[str, Any]:
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict): raise ValueError(f"{label} must be an object")
    return value


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink(): raise ValueError(f"refuses overwrite: {path}")
    _plain(path.parent, directory=True)
    with path.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def _load_source() -> ModuleType:
    raw = stable(SOURCE_EXECUTOR)
    if sha256(raw) != SOURCE_EXECUTOR_SHA256: raise ValueError("pinned 544af81 source executor drifted")
    module = ModuleType("_hanna_nextwave_source_544af81"); module.__file__ = str(SOURCE_EXECUTOR); sys.modules[module.__name__] = module
    try: exec(compile(raw, str(SOURCE_EXECUTOR), "exec"), module.__dict__)
    finally: sys.modules.pop(module.__name__, None)
    if stable(SOURCE_EXECUTOR) != raw: raise ValueError("pinned source executor changed during load")
    return module


def _tree(root: Path) -> tuple[str, list[dict[str, Any]]]:
    rows = []
    for path in sorted(root.rglob("*")):
        _plain(path, directory=path.is_dir())
        if path.is_file():
            raw = stable(path); rows.append({"path": path.relative_to(root).as_posix(), "sha256": sha256(raw), "bytes": len(raw)})
    return sha256(canonical(rows)), rows


def _source_inventory(root: Path, source: ModuleType, rows: list[Mapping[str, Any]]) -> None:
    _plain(root, directory=True)
    expected = {"catalog.json", *(str(row["cell_id"]) for row in rows)}
    entries = {item.name: item for item in root.iterdir()}
    if set(entries) != expected: raise ValueError("terminal source top-level inventory drifted")
    for name, item in entries.items(): _plain(item, directory=name != "catalog.json")
    for row in rows:
        cell = root / row["cell_id"]
        _plain(cell, directory=True)
        expected_cell = set(source.PREPARED) | {"launch-intent.json", "result.json", "responses"}
        cell_entries = {item.name: item for item in cell.iterdir()}
        if set(cell_entries) != expected_cell: raise ValueError("terminal source cell inventory drifted")
        for name, item in cell_entries.items(): _plain(item, directory=name == "responses")
        responses = cell / "responses"
        response_entries = {item.name: item for item in responses.iterdir()}
        if set(response_entries) != EXPECTED_RESPONSES: raise ValueError("terminal source response inventory drifted")
        for item in response_entries.values(): _plain(item, directory=False)


def _parent_profile(raw: bytes, source: ModuleType) -> dict[str, Any]:
    profile = source._profile(_json(raw, "frozen parent profile"))
    if tuple(profile["factors"]) != EXPECTED_FACTORS:
        raise ValueError("frozen parent factor geometry drifted")
    return profile


def _raw_suggestion(envelope_raw: bytes) -> tuple[dict[str, Any], dict[str, Any]]:
    envelope = _json(envelope_raw, "native Grok envelope")
    text = envelope.get("text")
    if not isinstance(text, str) or not text: raise ValueError("native envelope has no generated text")
    suggestion = _json(text.encode("utf-8"), "parsed native envelope text")
    if envelope.get("structuredOutput") != suggestion: raise ValueError("structuredOutput differs from parsed envelope text")
    if set(suggestion) != {"instruction", "profile", "change_summary"} or not isinstance(suggestion["instruction"], str) or not suggestion["instruction"] or not isinstance(suggestion["profile"], Mapping) or not isinstance(suggestion["change_summary"], str) or not suggestion["change_summary"]:
        raise ValueError("raw suggestion semantics drifted")
    if not all(isinstance(envelope.get(key), str) and envelope[key] for key in ("requestId", "sessionId")):
        raise ValueError("native request/session identity is absent")
    return envelope, suggestion


def _normalize(parent_instruction: bytes, parent_profile_raw: bytes, suggestion: Mapping[str, Any], source: ModuleType) -> tuple[dict[str, Any], list[str]]:
    parent = _parent_profile(parent_profile_raw, source)
    proposed = suggestion["profile"]
    factors = proposed.get("factors") if isinstance(proposed, Mapping) else None
    if not isinstance(factors, Mapping): raise ValueError("raw suggestion lacks factors")
    if any(not isinstance(factors.get(key), str) or not factors[key] for key in EXPECTED_FACTORS):
        raise ValueError("raw suggestion has missing or invalid existing factor")
    instruction = suggestion["instruction"].encode("utf-8")
    if instruction == parent_instruction and all(factors[key] == parent["factors"][key] for key in EXPECTED_FACTORS):
        raise ValueError("parent-identical output is rejected")
    normalized = json.loads(parent_profile_raw.decode("utf-8"))
    normalized["factors"] = {key: factors[key] for key in EXPECTED_FACTORS}
    normalized["instruction_sha256"] = sha256(instruction)
    normalized["version"] = NORMALIZED_VERSION
    source._profile(normalized)
    immutable = ("demonstrations", "dimension_weights", "fixed_mapping", "immutable_cwr_commitments", "same_bytes_for_models", "sampler", "study_id", "format_version")
    if any(normalized[key] != parent[key] for key in immutable): raise ValueError("normalization changed immutable frozen parent field")
    extras = sorted(set(factors) - set(EXPECTED_FACTORS))
    return normalized, extras


def _terminal_cell(root: Path, row: Mapping[str, Any], parent: Mapping[str, Any], source: ModuleType) -> dict[str, Any]:
    expected = source._files(row, parent, _json(stable(root / "prepared.json"), "prepared")["route"], _json(stable(root / "prepared.json"), "prepared")["route_evidence"], _json(stable(root / "authorization-acknowledgement.json"), "acknowledgement")["acknowledgement_sha256"])
    if any(stable(root / name) != raw for name, raw in expected.items()): raise ValueError("prepared source binding drifted")
    prompt = stable(root / "prompt-request.bin")
    if stable(root / "responses" / "batch-0001.attempt-0001.prompt.txt") != prompt: raise ValueError("terminal runner prompt differs from frozen prompt")
    prepared = _json(expected["prepared.json"], "prepared")
    intent = {"format_version": 1, "study_id": SOURCE_STUDY_ID, "kind": "intent_before_grok_candidate_generation", "cell_id": row["cell_id"], "prepared_sha256": source.sha256(prepared), "prompt_sha256": source.sha256(prompt), "native_contact_proven": False}
    result = _json(stable(root / "result.json"), "terminal result")
    expected_result = {"format_version": 1, "study_id": SOURCE_STUDY_ID, "kind": "reconcile_required_after_process_launch", "cell_id": row["cell_id"], "detail": "ValueError", "provider_calls_made": None, "process_launches": 1, "native_endpoint_contact_cardinality": "unknown", "intent_sha256": source.sha256(intent), "retry_policy": "fresh_output_root_required_no_in_place_resend"}
    if result != expected_result or stable(root / "launch-intent.json") != source.canonical(intent): raise ValueError("terminal launch/result binding drifted")
    envelope_raw = stable(root / "responses" / "batch-0001.attempt-0001.grok.envelope.json")
    envelope, suggestion = _raw_suggestion(envelope_raw)
    parent_instruction, parent_profile = stable(root / "parent-instruction.bin"), stable(root / "parent-profile.json")
    normalized, extras = _normalize(parent_instruction, parent_profile, suggestion, source)
    return {"cell": dict(row), "prepared_sha256": sha256(expected["prepared.json"]), "prompt_sha256": sha256(prompt), "route_proof_sha256": sha256(expected["zero-charge-route-proof.json"]), "parent_instruction_sha256": sha256(parent_instruction), "parent_profile_sha256": sha256(parent_profile), "native_envelope_sha256": sha256(envelope_raw), "request_id": envelope["requestId"], "session_id": envelope["sessionId"], "raw": suggestion, "normalized_profile": normalized, "ignored_extra_factor_keys": extras}


def _unique(records: list[Mapping[str, Any]]) -> None:
    if len({record["request_id"] for record in records}) != 10 or len({record["session_id"] for record in records}) != 10 or len({record["raw"]["instruction"] for record in records}) != 10:
        raise ValueError("terminal wave has duplicate identity or instruction")


def _records(source_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = _safe_ancestry(source_root); source = _load_source()
    catalog = _json(stable(root / "catalog.json"), "source catalog")
    if sha256(stable(root / "catalog.json")) != SOURCE_CATALOG_SHA256 or catalog.get("manifest_sha256") != SOURCE_CATALOG_MANIFEST_SHA256 or catalog.get("study_id") != SOURCE_STUDY_ID:
        raise ValueError("pinned terminal catalog drifted")
    source_parent_root = catalog.get("source_root")
    if not isinstance(source_parent_root, str) or not source_parent_root: raise ValueError("terminal catalog source root is absent")
    rows, parents = source._catalog(Path(source_parent_root)); _source_inventory(root, source, rows)
    tree_sha, tree_rows = _tree(root)
    if tree_sha != SOURCE_TREE_SHA256: raise ValueError("pinned terminal source evidence drifted")
    records = [_terminal_cell(root / row["cell_id"], row, parents[row["parent"]], source) for row in rows]
    _unique(records)
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "immutable_terminal_grok_wave_normalization_source", "source_commit": SOURCE_COMMIT, "source_executor_sha256": SOURCE_EXECUTOR_SHA256, "source_catalog_sha256": SOURCE_CATALOG_SHA256, "source_catalog_manifest_sha256": SOURCE_CATALOG_MANIFEST_SHA256, "source_tree_sha256": tree_sha, "source_tree": tree_rows, "provider_calls_made": 0, "process_launches": 0, "authority": "none"}
    return manifest, records


def _record(cell: Mapping[str, Any]) -> dict[str, Any]:
    raw = cell["raw"]; profile = cell["normalized_profile"]
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "locally_normalized_provisional_grok_descendant", "source_cell": cell["cell"], "source": {key: cell[key] for key in ("prepared_sha256", "prompt_sha256", "route_proof_sha256", "parent_instruction_sha256", "parent_profile_sha256", "native_envelope_sha256", "request_id", "session_id")}, "raw_generated": {"instruction": raw["instruction"], "instruction_sha256": sha256(raw["instruction"].encode("utf-8")), "change_summary": raw["change_summary"], "profile_sha256": sha256(compact(raw["profile"]))}, "normalization": {"copied_parent_profile": True, "applied_factor_keys": list(EXPECTED_FACTORS), "ignored_extra_factor_keys": cell["ignored_extra_factor_keys"], "normalized_version": NORMALIZED_VERSION}, "normalized": {"instruction": raw["instruction"], "instruction_sha256": sha256(raw["instruction"].encode("utf-8")), "profile": profile, "profile_sha256": sha256(compact(profile))}, "provider_calls_made": 0, "process_launches": 0, "authority": {"judging": "none", "selection": "none", "promotion": "none", "runtime": "none", "confirmation": "unopened"}}


def normalize_all(*, source_root: Path, output_root: Path) -> dict[str, Any]:
    source, output = _safe_ancestry(source_root), _safe_ancestry(output_root); _disjoint(output, source)
    if output.exists(): raise ValueError("normalization output root must be fresh")
    manifest, cells = _records(source); records = [_record(cell) for cell in cells]
    output.mkdir(parents=True, exist_ok=False); _plain(output, directory=True)
    _write_new(output / "source-manifest.json", canonical(manifest))
    for record in records: _write_new(output / f"{record['source_cell']['cell_id']}.json", canonical(record))
    return verify_all(source_root=source, output_root=output)


def verify_all(*, source_root: Path, output_root: Path) -> dict[str, Any]:
    source, output = _safe_ancestry(source_root), _safe_ancestry(output_root); _disjoint(output, source)
    manifest, cells = _records(source); expected = {"source-manifest.json": canonical(manifest), **{f"{cell['cell']['cell_id']}.json": canonical(_record(cell)) for cell in cells}}
    _plain(output, directory=True)
    if {item.name for item in output.iterdir()} != set(expected): raise ValueError("normalization output inventory drifted")
    if any(stable(output / name) != raw for name, raw in expected.items()): raise ValueError("normalization output reparse drifted")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "reconciled_ten_locally_normalized_provisional_grok_descendants", "normalized_candidates": 10, "provider_calls_made": 0, "process_launches": 0, "authority": "none"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); mode = parser.add_mutually_exclusive_group(required=True); mode.add_argument("--normalize-all", action="store_true"); mode.add_argument("--verify-all", action="store_true")
    parser.add_argument("--source-root", type=Path, required=True); parser.add_argument("--output-root", type=Path, required=True); args = parser.parse_args(argv)
    result = normalize_all(source_root=args.source_root, output_root=args.output_root) if args.normalize_all else verify_all(source_root=args.source_root, output_root=args.output_root)
    print(canonical(result).decode("utf-8"), end=""); return 0


if __name__ == "__main__": raise SystemExit(main())
