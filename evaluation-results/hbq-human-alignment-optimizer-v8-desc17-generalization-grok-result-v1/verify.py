"""Replay the completed desc17 Grok result from immutable local evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v8-desc17-generalization-grok-result-v1"
ANALYZER_ID = "hbq-human-alignment-optimizer-v8-desc17-generalization-development-optimizer-v1"
ANALYZER_COMMIT = "71abad0429bb860c4a013611c3f74f21aa9c9fae"
ANALYZER_ROOT = HERE.parent / ANALYZER_ID
ANALYZER_FILES = {
    "README.md": "3bc80949280b328bc7b864af446767b77551e41578ed31feb42286c70b3a39c1",
    "analyzer.py": "9ca948eb093e0c51d3e66989d878a22cb2353877b138ab5bb4c22b92591e12e1",
    "study-contract.json": "fa50492d686ec5dd473628fd98895d3ed05e8a5050acaf273d690778a7e38cd8",
}
ANALYZER_TEST_SHA256 = "5bbd053e99cf59c48ff09352f028820f2d12576f2a72c18f962d76c99f9dfadd"
COLLECTOR_SHA256 = "7b35b5fd1970158e74d59cabc12bf09156bf7cd7b99ac623bacc13d90617bdd3"
EXTERNAL_RESULT_FILE_SHA256 = "68168bb6988e0b6997321760a8b6cf3f763b90955d751d1362e859f6789c1847"
EXTERNAL_RESULT_INTERNAL_SHA256 = "a904d23639d4f17c625b50be2f1502e8bb91e5f8c0f7ec971e52db3bda994d53"
PERSISTED_RESULT_SHA256 = "efe6d5a9a505784e0e5281014a212546fc68cacb786cc548d2b287138eff9260"
PARENT = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CHILDREN = (
    "broader-nextwave-25-human-reference-six-slot-evidence-ledger",
    "broader-nextwave-26-construct-framing-human-reader-clean-room",
    "broader-nextwave-27-human-reference-full-scale-realization",
)
AUTHORITY = {
    "confirmation": "unopened",
    "generalization": "none",
    "promotion": "none",
    "runtime": "none",
    "selection": "retain_parent_zero_sol_calls",
    "sol": "not_required_zero_calls",
}
PUBLIC_FILES = {"README.md", "publication-manifest.json", "result.json", "study-contract.json", "verify.py"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def ancestry(path: Path, *, directory: bool) -> tuple[tuple[int, int, int, int, int], ...]:
    target = Path(os.path.abspath(path))
    values = []
    for index, current in enumerate((target, *target.parents)):
        info = os.lstat(current)
        expected_directory = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed result input")
        if stat.S_ISDIR(info.st_mode) != expected_directory:
            raise ValueError("result input type drifted")
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
        raise ValueError("result input changed during stable read")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if type(value) is not dict or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def load_analyzer() -> ModuleType:
    admitted: dict[str, bytes] = {}
    for name, digest in ANALYZER_FILES.items():
        path = ANALYZER_ROOT / name
        raw = stable(path)
        blob = subprocess.run(["git", "-C", str(REPO), "show", f"{ANALYZER_COMMIT}:{path.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
        if sha256(raw) != digest or blob.returncode or blob.stdout != raw:
            raise ValueError("pinned optimizer package drifted")
        admitted[name] = raw
    test_path = REPO / "tests" / "test_hbq_human_alignment_optimizer_v8_desc17_generalization_development_optimizer_v1.py"
    test_raw = stable(test_path)
    blob = subprocess.run(["git", "-C", str(REPO), "show", f"{ANALYZER_COMMIT}:{test_path.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if sha256(test_raw) != ANALYZER_TEST_SHA256 or blob.returncode or blob.stdout != test_raw:
        raise ValueError("pinned optimizer test drifted")
    module = ModuleType("_desc17_generalization_result_analyzer")
    module.__file__ = str(ANALYZER_ROOT / "analyzer.py")
    sys.modules[module.__name__] = module
    try:
        exec(compile(admitted["analyzer.py"], module.__file__, "exec"), module.__dict__)  # noqa: S102 -- exact committed optimizer bytes
    finally:
        sys.modules.pop(module.__name__, None)
    module.validate_package()
    if any(stable(ANALYZER_ROOT / name) != raw for name, raw in admitted.items()):
        raise ValueError("pinned optimizer package changed during load")
    return module


def public_result(source: Mapping[str, Any]) -> dict[str, Any]:
    metrics = source.get("metrics")
    qualification = source.get("qualification")
    optimizer = source.get("optimizer")
    dspy = source.get("dspy_evidence")
    source_evidence = source.get("source")
    if not all(isinstance(value, Mapping) for value in (qualification, optimizer, dspy, source_evidence)) or not isinstance(metrics, list):
        raise ValueError("optimizer result shape drifted")
    rows = {row.get("candidate_id"): row for row in metrics if isinstance(row, Mapping)}
    if set(rows) != {PARENT, *CHILDREN} or any(rows[candidate].get("cells") != 13 for candidate in rows):
        raise ValueError("optimizer metric geometry drifted")
    parent = rows[PARENT].get("equal_group_mae")
    if not isinstance(parent, (int, float)):
        raise TypeError("parent metric drifted")
    assessments = {row.get("candidate_id"): row for row in qualification.get("assessments", []) if isinstance(row, Mapping)}
    if qualification.get("parent_candidate_id") != PARENT or qualification.get("qualifiers") != [] or qualification.get("development_decision") != "retain_parent_zero_sol_calls" or qualification.get("frozen_before_sol") is not True or set(assessments) != set(CHILDREN):
        raise ValueError("zero-qualifier decision drifted")
    if any(assessments[candidate].get(key) is not False for candidate in CHILDREN for key in ("raw_equal_group_mae_strictly_below_parent", "no_worse_than_parent_all_six_robustness_settings", "qualifies_for_sol_veto")):
        raise ValueError("qualification drifted")
    if qualification.get("sol_veto") != {"calls_made": 0, "eligible_candidates": [], "role": "veto_only_no_sol_favored_substitution", "status": "not_required_no_qualifiers"}:
        raise ValueError("Sol boundary drifted")
    if optimizer.get("completed_trials") != 24 or len(optimizer.get("settings", [])) != 6 or dspy.get("evidence_examples") != 4 or dspy.get("lm_calls") != 0 or dspy.get("predict_calls") != 0 or source_evidence.get("collector_sha256") != COLLECTOR_SHA256:
        raise ValueError("development evidence drifted")
    return {
        "authority": AUTHORITY,
        "claim": "This development-only replay found no child satisfying the parent-relative raw-MAE and six-setting robustness rule. The desc16 child-20 parent is retained; Sol made zero calls. No confirmation, promotion, runtime, pooled-endpoint, or generalization claim follows.",
        "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 52, "provider_calls_made": None},
        "format_version": 1,
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_trials": 24, "robustness_settings": 6, "sol_cells_executed": 0},
        "kind": "desc17_generalization_grok_development_result_no_qualifiers",
        "metrics": [{"candidate_id": candidate, "cells": 13, "equal_group_mae": rows[candidate]["equal_group_mae"], "coverage_false_count": len(rows[candidate].get("coverage_false", [])), "absolute_reduction_from_parent": 0.0 if candidate == PARENT else parent - rows[candidate]["equal_group_mae"], "relative_reduction_from_parent": 0.0 if candidate == PARENT else (parent - rows[candidate]["equal_group_mae"]) / parent} for candidate in (PARENT, *CHILDREN)],
        "optimizer_evidence": {"library": optimizer.get("library"), "sampler": optimizer.get("sampler"), "seed": optimizer.get("seed"), "completed_trials": 24, "robustness_settings": 6, "trial_records_sha256": optimizer.get("trial_records_sha256")},
        "qualification": {"parent_candidate_id": PARENT, "assessments": [{"candidate_id": candidate, "raw_equal_group_mae_strictly_below_parent": False, "no_worse_than_parent_all_six_robustness_settings": False, "qualifies_for_sol_veto": False} for candidate in CHILDREN], "qualifiers": [], "rejected_candidates": list(CHILDREN), "frozen_before_sol": True, "all_children_fail_raw_equal_group_mae": True, "all_children_fail_six_setting_robustness": True, "sol_calls_made": 0, "sol_role": "veto_only_no_sol_favored_substitution", "sol_status": "not_required"},
        "source": {"analyzer_commit": ANALYZER_COMMIT, "analyzer_sha256": ANALYZER_FILES["analyzer.py"], "collector_sha256": COLLECTOR_SHA256, "external_optimizer_result_file_sha256": EXTERNAL_RESULT_FILE_SHA256, "optimizer_internal_result_sha256": EXTERNAL_RESULT_INTERNAL_SHA256, "projection_sha256": source_evidence.get("projection_sha256")},
        "study_id": STUDY_ID,
    }


def replay(*, freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path, optimizer_result_path: Path) -> dict[str, Any]:
    analyzer = load_analyzer()
    collector_raw, external_raw = stable(Path(collector_path)), stable(Path(optimizer_result_path))
    if sha256(collector_raw) != COLLECTOR_SHA256 or sha256(external_raw) != EXTERNAL_RESULT_FILE_SHA256:
        raise ValueError("collector or external optimizer result bytes drifted")
    external = strict(external_raw, "external optimizer result")
    replayed = analyzer.analyze(freeze_root=Path(freeze_root), development_freeze_root=Path(development_freeze_root), normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), collector_path=Path(collector_path))
    internal = {key: value for key, value in external.items() if key != "result_sha256"}
    if analyzer.canonical(replayed) != external_raw or external.get("result_sha256") != EXTERNAL_RESULT_INTERNAL_SHA256 or analyzer.sha256(internal) != EXTERNAL_RESULT_INTERNAL_SHA256:
        raise ValueError("independent optimizer replay differs from immutable result")
    return public_result(external)


def contract() -> dict[str, Any]:
    return {"authority": AUTHORITY, "format_version": 1, "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_trials": 24, "robustness_settings": 6, "sol_cells_executed": 0}, "kind": "provider_free_desc17_generalization_grok_development_result_replay", "pins": {"analyzer_commit": ANALYZER_COMMIT, "analyzer_files": dict(sorted(ANALYZER_FILES.items())), "analyzer_test_sha256": ANALYZER_TEST_SHA256, "collector_sha256": COLLECTOR_SHA256, "external_optimizer_result_file_sha256": EXTERNAL_RESULT_FILE_SHA256, "optimizer_internal_result_sha256": EXTERNAL_RESULT_INTERNAL_SHA256}, "prohibitions": ["no caller aggregates", "no imputation", "no endpoint pooling", "no confirmation, promotion, runtime, or generalization claim", "no runtime optimizer dependency"], "study_id": STUDY_ID}


def validate_package() -> dict[str, Any]:
    stable(HERE, directory=True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("public result package inventory drifted")
    result = strict(stable(HERE / "result.json"), "public result")
    manifest = strict(stable(HERE / "publication-manifest.json"), "publication manifest")
    expected_manifest = {"files": {name: sha256(stable(HERE / name)) for name in ("README.md", "result.json", "study-contract.json", "verify.py")}, "format_version": 1, "kind": "desc17_generalization_grok_result_publication_manifest", "study_id": STUDY_ID}
    if strict(stable(HERE / "study-contract.json"), "study contract") != contract() or manifest != expected_manifest or sha256(stable(HERE / "result.json")) != PERSISTED_RESULT_SHA256 or result.get("study_id") != STUDY_ID:
        raise ValueError("public result package drifted")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor-path", "hanna-csv-path", "output-root", "collector-path", "optimizer-result-path"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    validate_package()
    names = ("freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "output_root", "collector_path", "optimizer_result_path")
    print(canonical(replay(**{name: getattr(args, name) for name in names})).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
