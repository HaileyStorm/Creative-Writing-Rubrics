#!/usr/bin/env python3
"""Replay desc16 Grok receipts, then freeze Grok-primary qualifiers for Sol veto."""
from __future__ import annotations

import argparse
import os
import stat
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-development-optimizer-v1"
EXECUTOR_ID = "hbq-human-alignment-optimizer-v7-desc16-referent-evidence-grok-exec-v1"
EXECUTOR_ROOT = HERE.parent / EXECUTOR_ID
FREEZE_COMMIT = "2fb8b1e1dd9acc0d0869c3ebf51c384653ac3ee5"
FREEZE_SCHEDULE_SHA256 = "bffed26aec631bda163909fcdc66d5a91eef35ce9082d75bb05cce5c58fb6d45"
FREEZE_SCHEDULE_FILE_SHA256 = "00cf5cd9d95767cec44fb296197eec1760aab18327d753b816d84462aca712f3"
FREEZE_MANIFEST_SHA256 = "5aa8f797d833e387432d956b7d7e326ab71fa3a5642a368967842b26aa82909f"
EXECUTOR_FILES = {
    "README.md": "0dc792f306cf8d3e1c9b92772828bcdba78b08c80792a2935a80e00b14d79d6b",
    "executor.py": "33ecfb6806364a121df9f383be343985d0f667411cfdba553e1a290091312f88",
    "study-contract.json": "66e8190eab879971d948ffa46d1d549d6d2ab368c637d3a386f8ee8b27fd9e6f",
}
EXECUTOR_COMMIT = "989f1d6d438812d369d1344a706ee42cca105848"
PARENT = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CHILDREN = (
    "broader-nextwave-22-missing_evidence_not_no-referent-contradiction-threshold",
    "broader-nextwave-23-missing_evidence_not_no-local-antecedent-only",
    "broader-nextwave-24-missing_evidence_not_no-referent-dimension-isolation",
)
PREDECESSOR = HERE.parent / "hbq-human-alignment-optimizer-v6-desc15-referent-development-optimizer-v1" / "analyzer.py"
PREDECESSOR_SHA256 = "16f3945477b72a607f46065f93d533b5d1e9efc91627df723630b31bf32f8937"
PUBLIC_FILES = {"README.md", "analyzer.py", "study-contract.json"}


def _plain(path: Path, *, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed desc16 optimizer input")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("desc16 optimizer input type drifted")


def _stable(path: Path, *, directory: bool = False) -> bytes:
    target = Path(os.path.abspath(path))
    for current in (target, *target.parents):
        _plain(current, directory=current != target or directory)
    before = os.lstat(target)
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode), before.st_size)
    if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size) or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("desc16 optimizer input changed during stable read")
    return raw


def _engine() -> ModuleType:
    raw = _stable(PREDECESSOR)
    import hashlib
    if hashlib.sha256(raw).hexdigest() != PREDECESSOR_SHA256:
        raise ValueError("pinned desc15 optimizer predecessor drifted")
    source = raw.decode("utf-8")
    replacements = {
        "hbq-human-alignment-optimizer-v6-desc15-referent-development-optimizer-v1": STUDY_ID,
        "hbq-human-alignment-optimizer-v6-desc15-referent-grok-exec-v1": EXECUTOR_ID,
        "frozen_desc15_referent_grok_development_execution_schedule": "frozen_desc16_referent_evidence_grok_development_execution_schedule",
        "complete_52_desc15_referent_grok_receipts_cardinality_unproven": "complete_52_desc16_referent_evidence_grok_receipts_cardinality_unproven",
        "desc15_referent_grok_development_equal_group_projection": "desc16_referent_evidence_grok_development_equal_group_projection",
        "desc15_referent_grok_development_optimizer_and_sol_veto_freeze": "desc16_referent_evidence_grok_development_optimizer_and_sol_veto_freeze",
        "Desc15": "Desc16",
        "desc15": "desc16",
        "d2935d770079a4bacee654ef36c165fc27bb6f700d48647cf1f867dee5c276b4": FREEZE_SCHEDULE_SHA256,
        "broader-nextwave-13-missing_evidence_not_no": PARENT,
        "broader-nextwave-19-construct_framing-referent-boundary": CHILDREN[0],
        "broader-nextwave-20-missing_evidence_not_no-referent-evidence": CHILDREN[1],
        "broader-nextwave-21-scope_materiality-referent-materiality": CHILDREN[2],
    }
    for old, new in replacements.items():
        source = source.replace(old, new)
    module = ModuleType("_desc16_referent_optimizer_engine")
    module.__file__ = str(HERE / "analyzer.py")
    module.__package__ = ""
    sys.modules[module.__name__] = module
    try:
        exec(compile(source, str(PREDECESSOR), "exec"), module.__dict__)  # noqa: S102 -- exact pinned predecessor with explicit identifiers only
    finally:
        sys.modules.pop(module.__name__, None)
    module.HERE = HERE
    module.REPO = REPO
    module.STUDY_ID = STUDY_ID
    module.EXECUTOR_ID = EXECUTOR_ID
    module.EXECUTOR_ROOT = EXECUTOR_ROOT
    module.EXECUTOR_COMMIT = "runtime_admitted_desc16_executor"
    module.EXECUTOR_HASHES = {"executor.py": ""}
    module.FREEZE_SCHEDULE_SHA256 = FREEZE_SCHEDULE_SHA256
    module.PARENT = PARENT
    module.CHILDREN = CHILDREN
    module.CANDIDATES = (PARENT, *CHILDREN)
    return module


ENGINE = _engine()


def load_executor() -> ModuleType:
    raw = _stable(EXECUTOR_ROOT / "executor.py")
    if any(ENGINE.sha256(_stable(EXECUTOR_ROOT / name)) != digest for name, digest in EXECUTOR_FILES.items()):
        raise ValueError("desc16 executor public-file binding drifted")
    import subprocess
    for name, digest in EXECUTOR_FILES.items():
        relative = (EXECUTOR_ROOT / name).relative_to(REPO).as_posix()
        blob = subprocess.run(["git", "-C", str(REPO), "show", f"{EXECUTOR_COMMIT}:{relative}"], capture_output=True, check=False)
        if blob.returncode or ENGINE.sha256(blob.stdout) != digest or blob.stdout != _stable(EXECUTOR_ROOT / name):
            raise ValueError("desc16 executor Git commitment drifted")
    module = ModuleType("_desc16_referent_evidence_executor")
    module.__file__ = str(EXECUTOR_ROOT / "executor.py")
    module.__package__ = ""
    sys.modules[module.__name__] = module
    try:
        exec(compile(raw, module.__file__, "exec"), module.__dict__)  # noqa: S102 -- admitted local executor bytes are replayed immediately
    finally:
        sys.modules.pop(module.__name__, None)
    if (
        module.STUDY_ID != EXECUTOR_ID
        or module.SOURCE_COMMIT != FREEZE_COMMIT
        or module.FREEZE_SCHEDULE_SHA256 != FREEZE_SCHEDULE_SHA256
        or module.FREEZE_SCHEDULE_FILE_SHA256 != FREEZE_SCHEDULE_FILE_SHA256
        or module.FREEZE_MANIFEST_SHA256 != FREEZE_MANIFEST_SHA256
        or _stable(EXECUTOR_ROOT / "executor.py") != raw
    ):
        raise ValueError("desc16 executor identity or frozen evidence binding drifted")
    ENGINE.EXECUTOR_HASHES = {"executor.py": ENGINE.sha256(raw)}
    return module


ENGINE.load_executor = load_executor


def _contract() -> dict[str, Any]:
    return {
        "authority": {"confirmation": "unopened", "promotion": "none", "runtime": "none", "selection": "grok_development_qualification_only", "sol": "veto_only"},
        "format_version": 1,
        "geometry": {"candidates": 4, "development_groups": 7, "development_items": 13, "grok_cells": 52, "optuna_grid_settings": 6},
        "kind": "provider_free_desc16_result_replay_and_development_optimizer",
        "pinned_executor": {"commit": EXECUTOR_COMMIT, "files": dict(sorted(EXECUTOR_FILES.items())), "study_id": EXECUTOR_ID},
        "pinned_freeze": {"commit": FREEZE_COMMIT, "manifest_file_sha256": FREEZE_MANIFEST_SHA256, "schedule_file_sha256": FREEZE_SCHEDULE_FILE_SHA256, "schedule_sha256": FREEZE_SCHEDULE_SHA256},
        "pinned_predecessor": {"analyzer_sha256": PREDECESSOR_SHA256, "study_id": "hbq-human-alignment-optimizer-v6-desc15-referent-development-optimizer-v1"},
        "qualification_rule": {"raw_equal_group_mae": "strictly_below_desc15_child20_parent", "robustness": "no_worse_than_desc15_child20_parent_in_all_six_settings", "sol": "freeze_qualifiers_before_sol_then_veto_only", "zero_qualifiers": "retain_desc15_child20_parent_and_make_zero_sol_calls"},
        "runtime_dependencies": {"dspy": "development_only_zero_lm_calls", "optuna": "development_only_grid_sampler", "production": "none"},
        "study_id": STUDY_ID,
    }


def validate_package() -> dict[str, Any]:
    _plain(HERE, directory=True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC_FILES:
        raise ValueError("desc16 development optimizer package inventory drifted")
    contract = ENGINE._strict(_stable(HERE / "study-contract.json"), "desc16 study contract")
    if contract != _contract():
        raise ValueError("desc16 development optimizer contract drifted")
    return contract


def replay_projection(**paths: Path) -> dict[str, Any]:
    return ENGINE.replay_projection(**paths)


def analyze(**paths: Path) -> dict[str, Any]:
    return ENGINE.analyze(**paths)


def write_result(path: Path, result: Mapping[str, Any]) -> None:
    ENGINE.write_result(path, result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("freeze-root", "development-freeze-root", "normalized-root", "materialization-root", "frozen-successor-path", "hanna-csv-path", "output-root", "collector-path"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv)
    validate_package()
    names = ("freeze_root", "development_freeze_root", "normalized_root", "materialization_root", "frozen_successor_path", "hanna_csv_path", "output_root", "collector_path")
    result = analyze(**{name: getattr(args, name) for name in names})
    if args.result_output is not None:
        write_result(args.result_output, result)
    print(ENGINE.canonical(result).decode("utf-8"), end="")
    return 0


for _name in ("canonical", "sha256", "DIMENSIONS", "WORST_GROUP_WEIGHTS", "STABILITY_WEIGHTS", "SEED", "_project", "_validated_metrics", "run_optuna", "qualify", "build_dspy_evidence", "objective"):
    globals()[_name] = getattr(ENGINE, _name)


if __name__ == "__main__":
    raise SystemExit(main())
