#!/usr/bin/env python3
"""Provider-free V9 replay using the exact historical V6 input bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import types
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STUDY_ID = "cwr-guided-revision-gain-v2-live-exec-v9-historical-input-replay-result-v1"
PINNED_V7_COMMIT = "1affc2c6d3b2ebaf28adecf14b489e3bd9e0baf2"
V7_PATH = ROOT / "evaluation-results" / "cwr-guided-revision-gain-v2-live-exec-v7-endpoint-continuation" / "executor.py"
V7_SHA256 = "f2e35ea8380fb50e5c657ecc4d9ecc47128d044a56d6e2ce5ca4ef0e58aa5865"
HISTORICAL_V6_COMMIT = "c24a9eccaa5faea820f7a2b392e53293240792b1"
HISTORICAL_V6_REPOSITORY_PATH = "evaluation-results/cwr-guided-revision-gain-v2-live-exec-v6-single-replacement/executor.py"
HISTORICAL_V6_GIT_BLOB_OID = "100c9e70ebe4d550249c47e5f775b30d4515361a"
HISTORICAL_V6_SHA256 = "e0f4181e4daed637b6c8e438e71b90129505bd2191202dd2ef43e0f7e406d172"
HISTORICAL_V6_COMPILE_PATH = ROOT / HISTORICAL_V6_REPOSITORY_PATH
V8_PROJECTION_SHA256 = "e3ebd206b71ce20fa16e791af80221ce82237e7013ff413c3c425ecd7d9d88ce"
EXPECTED_MEANS = {
    ("gpt-5.6-sol-high", "holistic"): 2.25,
    ("gpt-5.6-sol-high", "compact"): 2.25,
    ("grok-4.6-high", "holistic"): 1.75,
    ("grok-4.6-high", "compact"): 1.5,
}
_GIT_RUN = subprocess.run


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: Path, *, label: str = "artifact") -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(f"V9 {label} is reparsed")
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError(f"V9 {label} is unsafe")
    before = (info.st_dev, info.st_ino, info.st_size)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if before != (opened.st_dev, opened.st_ino, opened.st_size) or (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"V9 {label} changed during read")
    return raw


def contract() -> dict[str, Any]:
    expected = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "mode": "provider_free_completed_v7_replay_with_historical_v6_input",
        "pinned_v7_commit": PINNED_V7_COMMIT,
        "pinned_v7_executor_sha256": V7_SHA256,
        "historical_v6": {"commit": HISTORICAL_V6_COMMIT, "repository_path": HISTORICAL_V6_REPOSITORY_PATH, "git_blob_oid": HISTORICAL_V6_GIT_BLOB_OID, "sha256": HISTORICAL_V6_SHA256},
        "pinned_v8_projection_sha256": V8_PROJECTION_SHA256,
        "source_root_input": "required_explicit_absolute_path",
        "accepted_adapter_stdout_suffixes": ["LF", "CRLF"],
        "rejected_adapter_stdout_suffixes": ["none", "CR", "multiple_or_mixed"],
        "geometry": {"endpoint_receipts": 40, "primary_guided_control_rows": 16, "arm_baseline_rows": 32},
        "disclosure": {"provider_calls_made": 0, "no_remote_execution": True, "historical_development_evidence_only": True, "no_source_root_in_public_result": True},
    }
    if canonical(expected) + b"\n" != read(HERE / "study-contract.json", label="contract"):
        raise ValueError("V9 contract drifted")
    return expected


def _git_blob() -> bytes:
    spec = f"{HISTORICAL_V6_COMMIT}:{HISTORICAL_V6_REPOSITORY_PATH}"
    oid = _GIT_RUN(["git", "-C", str(ROOT), "rev-parse", spec], capture_output=True, check=False)
    if oid.returncode != 0 or oid.stdout.decode("ascii", "strict").strip() != HISTORICAL_V6_GIT_BLOB_OID:
        raise ValueError("V9 historical V6 Git blob binding drifted")
    blob = _GIT_RUN(["git", "-C", str(ROOT), "cat-file", "blob", HISTORICAL_V6_GIT_BLOB_OID], capture_output=True, check=False)
    if blob.returncode != 0 or sha(blob.stdout) != HISTORICAL_V6_SHA256:
        raise ValueError("V9 historical V6 Git blob content drifted")
    return blob.stdout


def _load_historical_v6():
    raw = _git_blob()
    if sha(raw) != HISTORICAL_V6_SHA256:
        raise ValueError("V9 historical V6 Git blob content drifted")
    module = types.ModuleType("v9_historical_v6")
    module.__file__ = str(HISTORICAL_V6_COMPILE_PATH)
    exec(compile(raw, str(HISTORICAL_V6_COMPILE_PATH), "exec"), module.__dict__)  # noqa: S102
    if module._sha(raw) != HISTORICAL_V6_SHA256 or module.STUDY_ID != "cwr-guided-revision-gain-v2-live-exec-v6-single-replacement":
        raise ValueError("V9 historical V6 module drifted")
    return module


def _patched_v7_source(raw: bytes) -> bytes:
    old = b'expected_stdout=json.dumps(envelope,sort_keys=True).encode("ascii")+b"\\n"'
    new = b'expected_stdout=json.dumps(envelope,sort_keys=True).encode("ascii"); allowed_stdout=(expected_stdout+b"\\n",expected_stdout+b"\\r\\n")'
    if raw.count(old) != 1 or raw.count(b"stdout!=expected_stdout") != 1:
        raise ValueError("V9 pinned V7 replay seam drifted")
    return raw.replace(old, new).replace(b"stdout!=expected_stdout", b"stdout not in allowed_stdout")


def _load_v7_adapter():
    raw = read(V7_PATH, label="pinned V7 executor")
    if sha(raw) != V7_SHA256:
        raise ValueError("V9 pinned V7 executor drifted")
    module = types.ModuleType("v9_pinned_v7_replay")
    module.__file__ = str(V7_PATH)
    exec(compile(_patched_v7_source(raw), str(V7_PATH), "exec"), module.__dict__)  # noqa: S102
    historical_v6 = _load_historical_v6()
    module.v6 = lambda: historical_v6
    return module


def _source_root(value: Path) -> Path:
    root = Path(value)
    if not root.is_absolute():
        raise ValueError("V9 source root must be an explicit absolute path")
    root = Path(os.path.abspath(root))
    if not root.is_dir():
        raise ValueError("V9 source root is unavailable")
    info = os.lstat(root)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
        raise ValueError("V9 source root is reparsed")
    return root


def _receipt_paths(source_root: Path) -> list[Path]:
    paths = sorted((source_root / "cells").glob("*/verified-receipt.json"))
    if len(paths) != 40 or len({path.parent.name for path in paths}) != 40:
        raise ValueError("V9 requires exactly forty V7 receipt authorities")
    if any(path.parent.parent != source_root / "cells" for path in paths):
        raise ValueError("V9 receipt layout drifted")
    return paths


def _commitment(root: Path, path: Path) -> dict[str, Any]:
    raw = read(path)
    return {"path": path.relative_to(root).as_posix(), "bytes": len(raw), "sha256": sha(raw)}


def _public(value: Any) -> None:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True)
    if "\\\\" in encoded or ":\\\\" in encoded or "C:/" in encoded:
        raise ValueError("V9 public result leaks an absolute path")


def _projection(result: dict[str, Any]) -> dict[str, Any]:
    return {name: result[name] for name in ("endpoint_results_are_not_pooled", "endpoint_evidence", "primary_guided_minus_control", "arm_minus_baseline", "summaries")}


def replay_completed_v7(*, source_root: Path) -> dict[str, Any]:
    contract()
    source_root = _source_root(source_root)
    adapter = _load_v7_adapter()
    receipts = _receipt_paths(source_root)
    projection = adapter.project_independent_metrics(receipt_paths=receipts)
    replay_context = adapter._context()
    summaries = {(row["judge_route_id"], row["measure_id"]): row for row in projection["summaries"]}
    if {key: summaries[key]["mean_guided_minus_control"] for key in EXPECTED_MEANS} != EXPECTED_MEANS:
        raise ValueError("V9 independently recomputed means differ from the completed V7 evidence")
    rows = []
    for path in receipts:
        receipt, event = adapter._replay_receipt(source_root, path, context=replay_context)
        root = path.parent
        rows.append({"endpoint_event_id": event["endpoint_event_id"], "judge_route_id": event["judge_route_id"], "measure_id": event["measure_id"], "overall": receipt["response"]["overall"], "receipt": _commitment(source_root, path), "adapter_stdout": _commitment(source_root, root / "adapter-stdout.raw"), "adapter_control": _commitment(source_root, root / "adapter-control.json")})
    result = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "independently_recomputed_v9_historical_v6_input_v7_endpoint_projection",
        "evidence_status": "historical_development_evidence_only",
        "pinned_v7_commit": PINNED_V7_COMMIT,
        "pinned_v7_executor_sha256": V7_SHA256,
        "historical_v6": contract()["historical_v6"],
        "provider_calls_made": 0,
        "source_artifacts": [_commitment(source_root, source_root / name) for name in ("immutable-inputs.json", "prepared-index.json")],
        "endpoint_results_are_not_pooled": projection["endpoint_results_are_not_pooled"],
        "endpoint_evidence": projection["endpoint_evidence"],
        "primary_guided_minus_control": projection["primary_guided_minus_control"],
        "arm_minus_baseline": projection["arm_minus_baseline"],
        "summaries": projection["summaries"],
        "underlying_endpoint_rows": rows,
        "ceilings": ["Historical development evidence only; this replay does not make a promotion, provider-ranking, or generalization claim.", "Sol native endpoint-contact cardinality is unproven.", "Launch intent inherits the pilot study_id bound by the V7 hash and is not independently reminted.", "Grok command_identity_hash includes nonvisual_max_turns semantics and is not cross-compared to the route proof."],
    }
    if len(result["primary_guided_minus_control"]) != 16 or len(result["arm_minus_baseline"]) != 32:
        raise ValueError("V9 independent endpoint geometry drifted")
    actual_projection_sha256 = sha(canonical(_projection(result)))
    result["v8_projection_parity"] = {"expected_sha256": V8_PROJECTION_SHA256, "actual_sha256": actual_projection_sha256, "status": "exact_parity" if actual_projection_sha256 == V8_PROJECTION_SHA256 else "discrepancy"}
    _public(result)
    return result


def write_result(*, source_root: Path, output: Path) -> dict[str, Any]:
    output = Path(output)
    if output.exists():
        raise ValueError("V9 output already exists")
    result = replay_completed_v7(source_root=source_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as handle:
        handle.write(canonical(result) + b"\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider-free V9 historical-input replay verifier")
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = write_result(source_root=args.source_root, output=args.output) if args.output else replay_completed_v7(source_root=args.source_root)
    print(json.dumps({"study_id": result["study_id"], "provider_calls_made": 0, "endpoint_rows": len(result["underlying_endpoint_rows"]), "primary_rows": len(result["primary_guided_minus_control"]), "arm_rows": len(result["arm_minus_baseline"]), "summaries": result["summaries"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
