"""Replay the desc16 Grok development result from immutable local evidence."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-grok-result-v1"
ANALYZER_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-development-optimizer-v1"
ANALYZER_COMMIT = "bdf96b88a89d8daebcf4aaec75d43229a7ca2698"
ANALYZER_ROOT = HERE.parent / ANALYZER_ID
ANALYZER_FILES = {
    "README.md": "8ed73240b3e1655667d01c848c6579e1d2c8864d70a85465be1723b1027a1a9c",
    "analyzer.py": "6f219737c0979087c7ed3302dd391b4ed0228ddf33ec110586c390d4175c30be",
    "study-contract.json": "8a0dc402deb0ede247dde73654cbe65dc79d6466d85a2c4b5ed5e9dfc2001fb6",
}
ANALYZER_TEST_SHA256 = "98e60cf7606cdfa83742e8165edbd708effee9064df34f1a685ebdee7c874470"
COLLECTOR_SHA256 = "83cdb82482a6b1b2a23a6146ddb1fd8ec4f7387d4feb232eda0a1119136246b9"
EXTERNAL_RESULT_FILE_SHA256 = "53dd32cc52c2f7975f2562e172f735576ae755bf702f3ee687f8e0418c2bdd54"
EXTERNAL_RESULT_INTERNAL_SHA256 = "e0c00248520c18676d5ea760c8464195b9b2ea0863f16e2c6cb840ac027f2f9a"
PERSISTED_RESULT_SHA256 = "424a90956d8b68e04bd79b57d3c893dc558b776a087c036057b0dd24a7cbb0fc"
PARENT = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CHILDREN = (
    "broader-nextwave-22-missing_evidence_not_no-referent-contradiction-threshold",
    "broader-nextwave-23-missing_evidence_not_no-local-antecedent-only",
    "broader-nextwave-24-missing_evidence_not_no-referent-dimension-isolation",
)
QUALIFIERS = (CHILDREN[0], CHILDREN[2])
PUBLIC_FILES = {"README.md", "publication-manifest.json", "result.json", "study-contract.json", "verify.py"}
AUTHORITY = {"confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "selection": "grok_development_qualifiers_frozen_pending_sol_veto", "sol": "veto_only_pending"}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _ancestry(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int, int | None], ...]:
    target = Path(os.path.abspath(path))
    values = []
    for index, current in enumerate((target, *target.parents)):
        info = os.lstat(current)
        expected_directory = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe or reparsed result input")
        if stat.S_ISDIR(info.st_mode) != expected_directory:
            raise ValueError("result input type drifted")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_mtime_ns, None if expected_directory else info.st_size))
    return tuple(values)


def stable(path: Path) -> bytes:
    target = Path(os.path.abspath(path))
    before = _ancestry(target, directory=False)
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after_open = os.fstat(handle.fileno())
    after = _ancestry(target, directory=False)
    identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != after or identity != (after_open.st_dev, after_open.st_ino, stat.S_IFMT(after_open.st_mode), after_open.st_size) or before[0][1:4] + (before[0][-1],) != identity:
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


def _blob(relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{ANALYZER_COMMIT}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned optimizer Git blob is absent")
    return result.stdout


def load_analyzer() -> ModuleType:
    admitted: dict[str, bytes] = {}
    for name, digest in ANALYZER_FILES.items():
        path = ANALYZER_ROOT / name
        raw = stable(path)
        if sha256(raw) != digest or _blob(path.relative_to(REPO).as_posix()) != raw:
            raise ValueError("pinned optimizer package drifted")
        admitted[name] = raw
    test_path = REPO / "tests" / "test_hbq_human_alignment_optimizer_v7_desc16_referent_evidence_development_optimizer_v1.py"
    test_raw = stable(test_path)
    if sha256(test_raw) != ANALYZER_TEST_SHA256 or _blob(test_path.relative_to(REPO).as_posix()) != test_raw:
        raise ValueError("pinned optimizer test drifted")
    module = ModuleType("_desc16_referent_public_result_analyzer")
    module.__file__ = str(ANALYZER_ROOT / "analyzer.py")
    module.__package__ = ""
    sys.modules[module.__name__] = module
    try:
        exec(compile(admitted["analyzer.py"], module.__file__, "exec"), module.__dict__)  # noqa: S102 -- exact committed bytes
    finally:
        sys.modules.pop(module.__name__, None)
    if stable(ANALYZER_ROOT / "analyzer.py") != admitted["analyzer.py"]:
        raise ValueError("pinned optimizer changed during load")
    module.validate_package()
    return module


def _public_result(source: Mapping[str, Any]) -> dict[str, Any]:
    metrics = source.get("metrics")
    if not isinstance(metrics, list) or len(metrics) != 4:
        raise ValueError("optimizer metrics geometry drifted")
    rows = {row.get("candidate_id"): row for row in metrics if isinstance(row, Mapping)}
    if set(rows) != {PARENT, *CHILDREN}:
        raise ValueError("optimizer candidates drifted")
    parent = rows[PARENT].get("equal_group_mae")
    if not isinstance(parent, (int, float)):
        raise TypeError("parent metric drifted")
    public_metrics = []
    for candidate in (PARENT, *CHILDREN):
        row = rows[candidate]
        value = row.get("equal_group_mae")
        if not isinstance(value, (int, float)) or row.get("cells") != 13 or row.get("coverage_false") != []:
            raise ValueError("optimizer metric or coverage drifted")
        public_metrics.append({"candidate_id": candidate, "cells": 13, "equal_group_mae": value, "absolute_reduction_from_parent": 0.0 if candidate == PARENT else parent - value, "relative_reduction_from_parent": 0.0 if candidate == PARENT else (parent - value) / parent})
    qualification = source.get("qualification")
    optimizer = source.get("optimizer")
    dspy = source.get("dspy_evidence")
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("parent_candidate_id") != PARENT
        or qualification.get("qualifiers") != list(QUALIFIERS)
        or qualification.get("frozen_before_sol") is not True
        or qualification.get("development_decision") != "freeze_qualifiers_pending_sol_veto"
    ):
        raise ValueError("frozen qualifier set drifted")
    assessments = qualification.get("assessments")
    if not isinstance(assessments, list) or len(assessments) != 3:
        raise ValueError("six-setting robustness qualification drifted")
    assessment_rows = {item.get("candidate_id"): item for item in assessments if isinstance(item, Mapping)}
    if set(assessment_rows) != set(CHILDREN) or any(
        assessment_rows[candidate].get("qualifies_for_sol_veto") is not (candidate in QUALIFIERS)
        or assessment_rows[candidate].get("no_worse_than_parent_all_six_robustness_settings") is not (candidate in QUALIFIERS)
        or assessment_rows[candidate].get("raw_equal_group_mae_strictly_below_parent") is not (candidate in QUALIFIERS)
        for candidate in CHILDREN
    ):
        raise ValueError("qualification assessment drifted")
    sol_veto = qualification.get("sol_veto")
    if not isinstance(sol_veto, Mapping) or sol_veto != {
        "calls_made": 0,
        "eligible_candidates": list(QUALIFIERS),
        "role": "veto_only_no_sol_favored_substitution",
        "status": "pending_for_frozen_qualifiers",
    }:
        raise ValueError("Sol veto boundary drifted")
    if not isinstance(optimizer, Mapping) or optimizer.get("completed_trials") != 24 or len(optimizer.get("settings", [])) != 6:
        raise ValueError("Optuna grid evidence drifted")
    if not isinstance(dspy, Mapping) or dspy.get("evidence_examples") != 4 or dspy.get("lm_calls") != 0 or dspy.get("predict_calls") != 0:
        raise ValueError("DSPy evidence drifted")
    source_evidence = source.get("source")
    if not isinstance(source_evidence, Mapping) or source_evidence.get("collector_sha256") != COLLECTOR_SHA256:
        raise ValueError("collector binding drifted")
    public_assessments = [
        {"candidate_id": candidate, "raw_equal_group_mae_strictly_below_parent": assessment_rows[candidate]["raw_equal_group_mae_strictly_below_parent"], "no_worse_than_parent_all_six_robustness_settings": assessment_rows[candidate]["no_worse_than_parent_all_six_robustness_settings"], "qualifies_for_sol_veto": assessment_rows[candidate]["qualifies_for_sol_veto"]}
        for candidate in CHILDREN
    ]
    return {
        "authority": AUTHORITY,
        "claim": "Against the freshly re-evaluated desc15 child-20 parent in this same 52-cell Grok development wave, two desc16 referent-evidence children qualified and were frozen before Sol. Sol may only veto; no confirmation, promotion, runtime, pooled-endpoint, or generalization claim follows.",
        "evidence_ceiling": {"native_endpoint_contact_cardinality": "unproven", "process_lifecycle_receipts": 52, "provider_calls_made": None},
        "format_version": 1,
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_trials": 24, "robustness_settings": 6, "sol_cells_executed": 0},
        "kind": "desc16_referent_evidence_grok_development_result_pending_sol_veto",
        "metrics": public_metrics,
        "optimizer_evidence": {"library": optimizer.get("library"), "sampler": optimizer.get("sampler"), "seed": optimizer.get("seed"), "completed_trials": 24, "robustness_settings": 6, "trial_records_sha256": optimizer.get("trial_records_sha256")},
        "qualification": {"parent_candidate_id": PARENT, "assessments": public_assessments, "qualifiers": list(QUALIFIERS), "rejected_candidates": [CHILDREN[1]], "frozen_before_sol": True, "all_qualifiers_raw_equal_group_mae_strictly_below_parent": True, "all_qualifiers_no_worse_than_parent_all_six_robustness_settings": True, "sol_role": "veto_only_no_sol_favored_substitution", "sol_status": "pending"},
        "source": {"analyzer_commit": ANALYZER_COMMIT, "analyzer_sha256": ANALYZER_FILES["analyzer.py"], "collector_sha256": COLLECTOR_SHA256, "external_optimizer_result_file_sha256": EXTERNAL_RESULT_FILE_SHA256, "optimizer_internal_result_sha256": EXTERNAL_RESULT_INTERNAL_SHA256, "projection_sha256": source_evidence.get("projection_sha256")},
        "study_id": STUDY_ID,
    }


def replay(*, freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path, optimizer_result_path: Path) -> dict[str, Any]:
    analyzer = load_analyzer()
    collector_raw = stable(Path(collector_path))
    external_raw = stable(Path(optimizer_result_path))
    if sha256(collector_raw) != COLLECTOR_SHA256 or sha256(external_raw) != EXTERNAL_RESULT_FILE_SHA256:
        raise ValueError("collector or external optimizer result bytes drifted")
    external = strict(external_raw, "external optimizer result")
    replayed = analyzer.analyze(freeze_root=Path(freeze_root), development_freeze_root=Path(development_freeze_root), normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path), output_root=Path(output_root), collector_path=Path(collector_path))
    internal = {key: value for key, value in external.items() if key != "result_sha256"}
    if analyzer.canonical(replayed) != external_raw or external.get("result_sha256") != EXTERNAL_RESULT_INTERNAL_SHA256 or analyzer.sha256(internal) != EXTERNAL_RESULT_INTERNAL_SHA256:
        raise ValueError("independent optimizer replay differs from immutable result")
    return _public_result(external)


def _contract() -> dict[str, Any]:
    return {"authority": AUTHORITY, "format_version": 1, "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_trials": 24, "robustness_settings": 6}, "kind": "provider_free_desc16_referent_evidence_grok_development_result_replay", "pins": {"analyzer_commit": ANALYZER_COMMIT, "analyzer_files": dict(sorted(ANALYZER_FILES.items())), "analyzer_test_sha256": ANALYZER_TEST_SHA256, "collector_sha256": COLLECTOR_SHA256, "external_optimizer_result_file_sha256": EXTERNAL_RESULT_FILE_SHA256, "optimizer_internal_result_sha256": EXTERNAL_RESULT_INTERNAL_SHA256}, "prohibitions": ["no caller aggregates", "no imputation", "no endpoint pooling", "no confirmation or promotion claim", "no runtime optimizer dependency"], "study_id": STUDY_ID}


def validate_package() -> dict[str, Any]:
    _ancestry(HERE, directory=True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("public result package inventory drifted")
    contract = strict(stable(HERE / "study-contract.json"), "study contract")
    result = strict(stable(HERE / "result.json"), "public result")
    manifest = strict(stable(HERE / "publication-manifest.json"), "publication manifest")
    bound_files = ("README.md", "result.json", "study-contract.json", "verify.py")
    expected_manifest = {"files": {name: sha256(stable(HERE / name)) for name in bound_files}, "format_version": 1, "kind": "desc16_referent_evidence_grok_result_publication_manifest", "study_id": STUDY_ID}
    if contract != _contract() or manifest != expected_manifest or sha256(stable(HERE / "result.json")) != PERSISTED_RESULT_SHA256 or result.get("study_id") != STUDY_ID:
        raise ValueError("public result package drifted")
    return contract


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("result output must be fresh")
    _ancestry(target.parent, directory=True)
    with target.open("xb") as handle:
        raw = canonical(dict(result))
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    if stable(target) != raw:
        raise ValueError("result output changed during write")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor-path", "hanna-csv-path", "output-root", "collector-path", "optimizer-result-path"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv)
    validate_package()
    names = ("freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "output_root", "collector_path", "optimizer_result_path")
    result = replay(**{name: getattr(args, name) for name in names})
    if args.result_output is not None:
        write_result(args.result_output, result)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
