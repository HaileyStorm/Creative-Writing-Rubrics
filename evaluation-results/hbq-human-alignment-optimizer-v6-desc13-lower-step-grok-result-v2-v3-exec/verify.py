"""Replay the completed descendant-13 lower-step Grok V3 collector without contact."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v2-v3-exec"
V1_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-result-v1"
V1 = HERE.parent / V1_ID / "verify.py"
V1_FILES = {"verify.py": "cf6d0a6bb2526191b5897275ae903ca8569f61d733cb0bfe136a41856447b587", "study-contract.json": "e097186128657b32251a5aad0e3d281e059111f15001508aa51ca6804b636681", "README.md": "adc79f8cc5190dc4f8e70f93e26423aaf01dc7198099dba315a10be3a1ad68ab", "test": "687015e5c6f310c398151010e1cced9e521b7910c37d9f61a313ec100a1615ad"}
EXECUTOR_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v3-callback-prompt"
EXECUTOR_COMMIT = "cd67452ceb018e18f5d2d3315c544af0d47f23ef"
EXECUTOR = HERE.parent / EXECUTOR_ID / "executor.py"
EXECUTOR_FILES = {"executor.py": "00c1df7da792c36e4d1532765977299c5001c0119097985a089a8935fd014b14", "study-contract.json": "9df0214e83e7d0a7c3ee599bd3a5e6fa8c416eaaff1d5234ab16c487fab296a0", "README.md": "b9b4dff4f64527c2753bd642d0a6868f9369ddbe5535cf459bc2a3429047643c"}
COLLECTOR_SHA256 = "6ca1fc13244f93719d672a127ddf10cc492ea2207e5649fab1058bdbea923ae6"
PUBLIC = {"README.md", "study-contract.json", "verify.py"}


def _identity(path: Path, directory: bool) -> tuple[tuple[str, int, int, int, int, int | None], ...]:
    target = Path(os.path.abspath(path)); values: list[tuple[str, int, int, int, int, int | None]] = []
    for index, current in enumerate((target, *target.parents)):
        info = os.lstat(current); expected = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)) or stat.S_ISDIR(info.st_mode) != expected:
            raise ValueError("unsafe package path")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_mtime_ns, None if expected else info.st_size))
    return tuple(values)


def _plain(path: Path, directory: bool) -> None:
    _identity(path, directory)


def _raw(path: Path) -> bytes:
    before = _identity(path, False)
    with path.open("rb") as handle:
        raw = handle.read(); opened = os.fstat(handle.fileno())
    after = _identity(path, False)
    opened_identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != after or before[0][1:4] + (before[0][-1],) != opened_identity:
        raise ValueError("stable full-ancestry read drift")
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _blob(relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{EXECUTOR_COMMIT}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned V3 Git blob is absent")
    return result.stdout


def _load(path: Path, name: str, expected_raw: bytes) -> ModuleType:
    if _raw(path) != expected_raw:
        raise ValueError("pinned source changed after admission")
    module = ModuleType(name); module.__file__ = str(path); module.__package__ = ""
    sys.modules[name] = module
    try:
        exec(compile(expected_raw, str(path), "exec"), module.__dict__)  # noqa: S102 -- exact admitted immutable bytes
    finally:
        sys.modules.pop(name, None)
    if _raw(path) != expected_raw:
        raise ValueError("pinned module changed during load")
    return module


def _base() -> ModuleType:
    root = HERE.parent / V1_ID
    admitted: dict[str, bytes] = {}
    for name, digest in V1_FILES.items():
        path = REPO / "tests/test_hbq_human_alignment_optimizer_v6_desc13_lower_step_grok_result_v1.py" if name == "test" else root / name
        raw = _raw(path)
        if _sha(raw) != digest:
            raise ValueError("pinned V1 analyzer drifted")
        admitted[name] = raw
    value = _load(V1, "_desc13_lower_result_v2_base", admitted["verify.py"])
    value.STUDY_ID = STUDY_ID; value.EXECUTOR_ID = EXECUTOR_ID
    return value


def _executor() -> ModuleType:
    root = HERE.parent / EXECUTOR_ID
    admitted: dict[str, bytes] = {}
    for name, digest in EXECUTOR_FILES.items():
        relative = f"evaluation-results/{EXECUTOR_ID}/{name}"; raw = _raw(root / name)
        if _sha(raw) != digest or _blob(relative) != raw:
            raise ValueError("pinned V3 executor drifted")
        admitted[name] = raw
    return _load(EXECUTOR, "_desc13_lower_result_v2_exec", admitted["executor.py"])


def _contract() -> dict[str, Any]:
    return {"format_version": 1, "kind": "provider_free_descendant13_lower_step_grok_result_v3_analyzer", "study_id": STUDY_ID, "authority": {"selection": "grok_development_only", "confirmation": "unopened", "generalization": "none", "promotion": "none", "runtime": "none", "endpoint_pooling": "forbidden"}, "pinned_v1_analyzer": {"study_id": V1_ID, "verify_sha256": V1_FILES["verify.py"], "study_contract_sha256": V1_FILES["study-contract.json"], "readme_sha256": V1_FILES["README.md"], "test_sha256": V1_FILES["test"], "role": "hardened_replay_code_and_provenance_only_not_retired_root_authority"}, "pinned_executor": {"commit": EXECUTOR_COMMIT, "study_id": EXECUTOR_ID, "executor_sha256": EXECUTOR_FILES["executor.py"], "study_contract_sha256": EXECUTOR_FILES["study-contract.json"], "readme_sha256": EXECUTOR_FILES["README.md"]}, "pinned_collector_sha256": COLLECTOR_SHA256}


def validate_package() -> None:
    _plain(HERE, True)
    if {path.name for path in HERE.iterdir() if path.name != "__pycache__"} != PUBLIC:
        raise ValueError("result V2 package inventory drifted")
    raw = _raw(HERE / "study-contract.json")
    if raw != (json.dumps(_contract(), sort_keys=True, separators=(",", ":")) + "\n").encode() or _sha(_raw(HERE / "verify.py")) == "":
        raise ValueError("result V2 contract drifted")


def replay(*, candidate_freeze_root: Path, development_freeze_root: Path, normalized_root: Path, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path, output_root: Path, collector_path: Path) -> dict[str, Any]:
    base = _base(); executor = _executor()
    collector_raw, ancestry = base._stable_read(Path(collector_path))
    if base.sha256(collector_raw) != COLLECTOR_SHA256:
        raise ValueError("wrong immutable V3 collector")
    replayed = executor.replay_collector(output_root=Path(output_root), candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root), collector_path=Path(collector_path))
    base._require_collector_binding(collector_raw, ancestry, replayed, Path(collector_path))
    schedule = base.strict(base.stable(Path(output_root) / "schedule.json"), "persisted V3 schedule")
    if schedule.get("study_id") != EXECUTOR_ID or schedule.get("schedule_sha256") != base.strict(collector_raw, "collector").get("schedule_sha256"):
        raise ValueError("V3 schedule/collector binding drifted")
    collector = base.strict(collector_raw, "collector")
    freeze = base._load_freeze(REPO)
    targets = base._targets(freeze, frozen_root=Path(development_freeze_root), normalized_root=Path(normalized_root), materialization_root=Path(materialization_root), frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    result = base._project(schedule, collector, targets, freeze._v3().v2_module()._extract_native)
    result["source_execution"] = {"executor_commit": EXECUTOR_COMMIT, "executor_sha256": EXECUTOR_FILES["executor.py"], "collector_sha256": COLLECTOR_SHA256, "development_schedule_sha256": schedule.get("development_schedule_sha256"), "candidate_manifest_sha256": schedule.get("candidate_freeze_manifest_sha256")}
    result["result_internal_sha256"] = base.sha256(result)
    return result


def write_result(path: Path, result: dict[str, Any]) -> None:
    target = Path(path)
    if target.exists() or target.is_symlink():
        raise ValueError("result output must be fresh")
    _plain(target.parent, True)
    with target.open("xb") as handle:
        handle.write((json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--candidate-freeze-root", type=Path); parser.add_argument("--development-freeze-root", type=Path); parser.add_argument("--normalized-root", type=Path); parser.add_argument("--materialization-root", type=Path); parser.add_argument("--frozen-successor", type=Path); parser.add_argument("--hanna-csv", type=Path); parser.add_argument("--output-root", type=Path); parser.add_argument("--collector-path", type=Path); parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv); validate_package()
    values = vars(args)
    if not all(values.values()):
        raise ValueError("every replay input is required")
    result = replay(candidate_freeze_root=args.candidate_freeze_root, development_freeze_root=args.development_freeze_root, normalized_root=args.normalized_root, materialization_root=args.materialization_root, frozen_successor_path=args.frozen_successor, hanna_csv_path=args.hanna_csv, output_root=args.output_root, collector_path=args.collector_path)
    if args.result_output:
        write_result(args.result_output, result)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), end="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
