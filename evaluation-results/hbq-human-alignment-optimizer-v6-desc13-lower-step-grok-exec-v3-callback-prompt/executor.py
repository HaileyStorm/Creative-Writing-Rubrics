#!/usr/bin/env python3
"""Callback-prompt successor for the lower-step Grok execution."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v3-callback-prompt"
V2_COMMIT = "95b59d086aec71895385c214ac528a2ff5473aaf"
V2 = HERE.parent / "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v2-slot-visibility"
V2_TEST = REPO / "tests" / "test_hbq_human_alignment_optimizer_v6_desc13_lower_step_grok_exec_v2_slot_visibility.py"
V2_HASHES = {
    V2 / "executor.py": "536d30656b85d9c3b5547677118b91caf086e35eba63ef1f10f1e239ec79f3ef",
    V2 / "study-contract.json": "d9bdfae4ea8f1149833944f98f94bb455641dcfe33730e675ab8eb68a64d0ca6",
    V2 / "README.md": "cdeb14e974aeff8d26a431768664ae538a526165b5c39a62cfc9184d8c9fb10d",
    V2_TEST: "1c5e3ca05b8f7361abec12d0f7d07fcf850e6bcb1a72c4475428f69c4992ee0c",
}
PACKAGE_FILES = frozenset({"README.md", "executor.py", "study-contract.json"})
ATTEMPT_PROMPT = "batch-0001.attempt-0001.prompt.txt"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def stable(path: Path) -> bytes:
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode), before.st_size)
    if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size) or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
        raise ValueError("stable read drift")
    return raw


def _blob(path: Path) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{V2_COMMIT}:{path.relative_to(REPO).as_posix()}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned V2 Git blob is absent")
    return result.stdout


def _validate_v2_lineage() -> None:
    for path, digest in V2_HASHES.items():
        raw = stable(path)
        if sha256(raw) != digest or _blob(path) != raw:
            raise ValueError("pinned V2 dependency drifted")


def _load_v2() -> ModuleType:
    _validate_v2_lineage()
    path = V2 / "executor.py"
    raw = stable(path)
    spec = importlib.util.spec_from_file_location("_desc13_lower_step_v3_v2", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned V2")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    if stable(path) != raw:
        raise ValueError("pinned V2 changed during load")
    return module


def _expected_contract() -> dict[str, Any]:
    return {
        "format_version": 1,
        "kind": "callback_prompt_successor",
        "study_id": STUDY_ID,
        "pinned_v2": {
            "commit": V2_COMMIT,
            "executor_sha256": V2_HASHES[V2 / "executor.py"],
            "study_contract_sha256": V2_HASHES[V2 / "study-contract.json"],
            "readme_sha256": V2_HASHES[V2 / "README.md"],
            "test_sha256": V2_HASHES[V2_TEST],
        },
        "geometry": {"candidates": 5, "development_groups": 7, "grok_cells": 35},
        "callback_prompt": {"name": ATTEMPT_PROMPT, "source": "prompt-request.bin"},
        "prohibitions": ["fresh output root only", "no fallback or resend", "no response output before callback", "no provider contact in preparation"],
    }


def contract() -> dict[str, Any]:
    raw = stable(HERE / "study-contract.json")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid study contract") from error
    if not isinstance(value, dict) or canonical(value) != raw or value != _expected_contract():
        raise ValueError("study contract drifted")
    return value


def _package_source_inventory() -> None:
    _plain(HERE, directory=True)
    entries = {path.name: path for path in HERE.iterdir()}
    if set(entries) - {"__pycache__"} != PACKAGE_FILES:
        raise ValueError("V3 package inventory drifted")
    for name in PACKAGE_FILES:
        _plain(entries[name], directory=False)
    cache = entries.get("__pycache__")
    if cache is not None:
        _plain(cache, directory=True)
        for path in cache.iterdir():
            _plain(path, directory=False)
            if path.suffix != ".pyc":
                raise ValueError("unsafe V3 package cache artifact")


def validate_package() -> None:
    _package_source_inventory()
    contract()
    _validate_v2_lineage()


def _verify_callback_prepared(module: ModuleType, lifecycle: ModuleType, schedule: Mapping[str, Any], root: Path, captured: Mapping[str, tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]]) -> None:
    root = module._safe(root)
    expected = set(lifecycle.PREPARED) | {"responses"}
    if {path.name for path in root.iterdir()} != expected:
        raise ValueError("prepared root inventory drifted before launch")
    responses = root / "responses"
    module._full_identity(responses, directory=True)
    if {path.name for path in responses.iterdir()} != {ATTEMPT_PROMPT}:
        raise ValueError("callback response inventory drifted before launch")
    staged_prompt = responses / ATTEMPT_PROMPT
    module._full_identity(staged_prompt, directory=False)
    prompt = stable(staged_prompt)
    admitted, admitted_identity = captured["prompt-request.bin"]
    if prompt != admitted or sha256(prompt) != sha256(admitted):
        raise ValueError("staged callback prompt differs from admitted prompt request")
    if module._full_identity(root / "prompt-request.bin", directory=False) != admitted_identity:
        raise ValueError("admitted prompt request identity drifted before launch")
    matching = [row for row in schedule["cells"] if row["cell_id"] == root.name]
    if len(matching) != 1 or matching[0].get("payload_sha256") != sha256(admitted):
        raise ValueError("staged callback prompt identity does not bind its scheduled cell")
    for name in lifecycle.PREPARED:
        raw, identity = captured[name]
        path = root / name
        if module.stable(path) != raw or module._full_identity(path, directory=False) != identity:
            raise ValueError("prepared artifact drifted before launch")
    schedule_raw, schedule_identity = captured["schedule.json"]
    schedule_path = root.parent / "schedule.json"
    if module.stable(schedule_path) != schedule_raw or module._full_identity(schedule_path, directory=False) != schedule_identity or schedule_raw != module.canonical(schedule):
        raise ValueError("schedule drifted before launch")


def _guard_runner(module: ModuleType, runner: Callable[..., Mapping[str, Any]], lifecycle: ModuleType, schedule: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    def guarded(**kwargs: Any) -> Mapping[str, Any]:
        root = Path(kwargs["output_dir"])
        captured = module._capture_prepared(lifecycle, schedule, root)
        before_contact = kwargs["before_contact"]

        def guarded_before_contact() -> None:
            _verify_callback_prepared(module, lifecycle, schedule, root, captured)
            before_contact()

        copied = dict(kwargs)
        copied["before_contact"] = guarded_before_contact
        return runner(**copied)

    return guarded


def _runtime() -> ModuleType:
    validate_package()
    module = _load_v2()._runtime()
    module.STUDY_ID = STUDY_ID
    expected_contract = module._expected_contract()
    module.contract = lambda: expected_contract
    module._guard_runner = lambda runner, lifecycle, schedule: _guard_runner(module, runner, lifecycle, schedule)
    return module


def prepare_all(**kwargs: Any):
    return _runtime().prepare_all(**kwargs)


def execute_one(**kwargs: Any):
    return _runtime().execute_one(**kwargs)


async def execute_wave(**kwargs: Any):
    return await _runtime().execute_wave(**kwargs)


def finalize_collector(**kwargs: Any):
    return _runtime().finalize_collector(**kwargs)


def replay_collector(**kwargs: Any):
    return _runtime().replay_collector(**kwargs)


def main(argv: list[str] | None = None) -> int:
    return _runtime().main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
