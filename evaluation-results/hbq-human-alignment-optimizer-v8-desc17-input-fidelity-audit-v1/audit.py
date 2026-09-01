"""Withdraw desc17 semantic use after replaying its immutable input evidence."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v8-desc17-input-fidelity-audit-v1"
COLLECTOR_SHA256 = "7b35b5fd1970158e74d59cabc12bf09156bf7cd7b99ac623bacc13d90617bdd3"
ORIGINAL_COMMIT = "7a768f09c34a226740fdd38f4efed0150d3580e0"
ORIGINAL_PATH = "evaluation-results/hbq-human-alignment-optimizer-v8-desc17-generalization-grok-result-v1/result.json"
ORIGINAL_SHA256 = "efe6d5a9a505784e0e5281014a212546fc68cacb786cc548d2b287138eff9260"
ORIGINAL_MANIFEST_PATH = "evaluation-results/hbq-human-alignment-optimizer-v8-desc17-generalization-grok-result-v1/publication-manifest.json"
ORIGINAL_MANIFEST_SHA256 = "8f9a0043aa479209079ce802fb4fea91e5be0ee7618354b23a610ace6058f81f"
ORIGINAL_STUDY_ID = "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-result-v1"
DIMENSIONS = ("Coherence", "Complexity", "Empathy", "Engagement", "Relevance", "Surprise")
PUBLIC_FILES = {"README.md", "audit.py", "public-result.json", "study-contract.json"}
EXPECTED = {"all_zero_score_cells": 10, "evidence_x_cells": 2, "opaque_prompt_writing_payload_cells": 52, "placeholder_or_searching_response_cells": 4, "response_fidelity_signal_union_cells": 12}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(raw: bytes | Any) -> str:
    return hashlib.sha256(raw if isinstance(raw, bytes) else canonical(raw)).hexdigest()


def ancestry(path: Path, *, directory: bool) -> tuple[tuple[int, int, int, int, int], ...]:
    target = Path(os.path.abspath(path))
    values = []
    for index, current in enumerate((target, *target.parents)):
        info = os.lstat(current)
        expected_directory = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed audit input")
        if stat.S_ISDIR(info.st_mode) != expected_directory:
            raise ValueError("audit input type drifted")
        values.append((info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns))
    return tuple(values)


def stable(path: Path, *, directory: bool = False) -> bytes:
    target = Path(os.path.abspath(path))
    before = ancestry(target, directory=directory)
    if directory:
        return b""
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after_open = os.fstat(handle.fileno())
    after = ancestry(target, directory=False)
    identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != after or before[0][:4] != identity or identity != (after_open.st_dev, after_open.st_ino, stat.S_IFMT(after_open.st_mode), after_open.st_size):
        raise ValueError("audit input changed during stable read")
    return raw


def mapping(raw: bytes, label: str, *, canonical_required: bool) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical_required and canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _response(cell: Mapping[str, Any]) -> dict[str, Any]:
    encoded = cell.get("native_response_base64")
    if not isinstance(encoded, str):
        raise TypeError("collector response is absent")
    try:
        outer = mapping(base64.b64decode(encoded, validate=True), "native response", canonical_required=False)
        text = outer["text"]
    except (KeyError, ValueError) as error:
        raise ValueError("collector response is malformed") from error
    if not isinstance(text, str):
        raise TypeError("native response text is malformed")
    return mapping(text.encode("utf-8"), "response payload", canonical_required=False)


def _payload(cell: Mapping[str, Any]) -> dict[str, Any]:
    encoded = cell.get("payload_base64")
    if not isinstance(encoded, str):
        raise TypeError("collector payload is absent")
    try:
        return mapping(base64.b64decode(encoded, validate=True), "payload", canonical_required=True)
    except ValueError as error:
        raise ValueError("collector payload is malformed") from error


def inspect_collector(collector: Mapping[str, Any]) -> dict[str, int]:
    cells = collector.get("cells")
    if collector.get("format_version") != 1 or collector.get("study_id") != "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-exec-v1" or not isinstance(cells, list) or len(cells) != 52:
        raise ValueError("collector geometry or identity drifted")
    seen, all_zero, evidence_x, opaque, placeholder, signals = set(), 0, 0, 0, 0, 0
    for cell in cells:
        if not isinstance(cell, Mapping) or not isinstance(cell.get("cell_id"), str) or cell["cell_id"] in seen:
            raise ValueError("collector cell identity drifted")
        seen.add(cell["cell_id"])
        payload = _payload(cell)
        item_id, prompt_group_id = payload.get("item_id"), payload.get("prompt_group_id")
        prompt, writing = payload.get("prompt"), payload.get("writing")
        if not isinstance(item_id, str) or not isinstance(prompt_group_id, str) or prompt != f"prompt:{prompt_group_id}" or writing != f"writing:{item_id}":
            raise ValueError("desc17 payload is not the pinned opaque-id form")
        opaque += 1
        response = _response(cell)
        scores, evidence = response.get("scores"), response.get("evidence")
        if not isinstance(scores, Mapping) or not isinstance(evidence, Mapping) or set(scores) != set(DIMENSIONS) or set(evidence) != set(DIMENSIONS) or any(type(value) not in {int, float} for value in scores.values()) or any(not isinstance(value, str) for value in evidence.values()):
            raise ValueError("response schema drifted")
        zero = all(value == 0 for value in scores.values())
        x = any(value == "x" for value in evidence.values())
        placeholder_value = any("placeholder" in value or "Searching workspace" in value for value in evidence.values())
        all_zero += int(zero)
        evidence_x += int(x)
        placeholder += int(placeholder_value)
        signals += int(zero or x or placeholder_value)
    return {"opaque_prompt_writing_payload_cells": opaque, "all_zero_score_cells": all_zero, "evidence_x_cells": evidence_x, "placeholder_or_searching_response_cells": placeholder, "response_fidelity_signal_union_cells": signals}


def _original_result() -> None:
    admitted: dict[str, bytes] = {}
    for relative, digest in ((ORIGINAL_PATH, ORIGINAL_SHA256), (ORIGINAL_MANIFEST_PATH, ORIGINAL_MANIFEST_SHA256)):
        raw = stable(REPO / relative)
        blob = subprocess.run(["git", "-C", str(REPO), "show", f"{ORIGINAL_COMMIT}:{relative}"], capture_output=True, check=False)
        if sha256(raw) != digest or blob.returncode or blob.stdout != raw:
            raise ValueError("original desc17 result binding drifted")
        admitted[relative] = raw
    if mapping(admitted[ORIGINAL_PATH], "original desc17 result", canonical_required=True).get("study_id") != ORIGINAL_STUDY_ID:
        raise ValueError("original desc17 result identity drifted")


def result(counts: Mapping[str, int]) -> dict[str, Any]:
    if dict(counts) != EXPECTED:
        raise ValueError("input-fidelity defect counts drifted")
    return {
        "authority": {"desc17_generalization": "withdrawn", "desc17_semantic_conclusion": "withdrawn", "promotion": "none", "runtime": "none"},
        "claim": "Desc17 semantic and generalization conclusions are withdrawn: all 52 payloads carried only opaque prompt/writing identifiers, and the pinned responses include material fidelity defects. The original result remains immutable history, not usable semantic evidence.",
        "defect_counts": dict(EXPECTED),
        "format_version": 1,
        "kind": "desc17_input_fidelity_audit_withdrawal",
        "original_result": {"commit": ORIGINAL_COMMIT, "file_sha256": ORIGINAL_SHA256, "path": ORIGINAL_PATH, "publication_manifest_file_sha256": ORIGINAL_MANIFEST_SHA256, "study_id": ORIGINAL_STUDY_ID},
        "scope": {"affected": ["desc17"], "outside_audit_scope": ["desc15", "desc16", "Fresh88"]},
        "source": {"collector_sha256": COLLECTOR_SHA256, "collector_study_id": "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-exec-v1"},
        "study_id": STUDY_ID,
    }


def contract() -> dict[str, Any]:
    return {"authority": {"desc17_generalization": "withdrawn", "desc17_semantic_conclusion": "withdrawn", "promotion": "none", "runtime": "none"}, "format_version": 1, "kind": "provider_free_desc17_input_fidelity_audit", "original_result": {"commit": ORIGINAL_COMMIT, "file_sha256": ORIGINAL_SHA256, "path": ORIGINAL_PATH, "publication_manifest_file_sha256": ORIGINAL_MANIFEST_SHA256, "study_id": ORIGINAL_STUDY_ID}, "pinned_collector_sha256": COLLECTOR_SHA256, "prohibitions": ["no provider calls", "no reinterpretation of desc15, desc16, or Fresh88", "no replacement or mutation of the original desc17 result"], "study_id": STUDY_ID}


def audit(collector_path: Path) -> dict[str, Any]:
    raw = stable(Path(collector_path))
    if sha256(raw) != COLLECTOR_SHA256:
        raise ValueError("collector bytes drifted")
    _original_result()
    return result(inspect_collector(mapping(raw, "collector", canonical_required=True)))


def validate_package() -> dict[str, Any]:
    stable(HERE, directory=True)
    if {item.name for item in HERE.iterdir() if item.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("audit package inventory drifted")
    if mapping(stable(HERE / "study-contract.json"), "study contract", canonical_required=True) != contract():
        raise ValueError("audit contract drifted")
    public = mapping(stable(HERE / "public-result.json"), "public result", canonical_required=True)
    if public != result(EXPECTED):
        raise ValueError("public audit result drifted")
    return public


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collector-path", type=Path, required=True)
    args = parser.parse_args(argv)
    validate_package()
    print(canonical(audit(args.collector_path)).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
