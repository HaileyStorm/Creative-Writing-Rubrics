#!/usr/bin/env python3
"""Pinned HANNA v4 native execution successor with corrected Codex startup flags."""
from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path


HERE = Path(__file__).resolve().parent
EXEC_V1_DIR = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1"
EXEC_V1_PATH = EXEC_V1_DIR / "executor.py"
EXEC_V1_CONTRACT_PATH = EXEC_V1_DIR / "study-contract.json"
EXEC_V1_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
EXEC_V1_CONTRACT_SHA256 = "b132f0d29273a4896c2308f684c7df6547408195ef36c6d4f5f54ed263f86562"

_SOURCE_PATCHES = (
    (
        'STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1"',
        'STUDY_ID = "hbq-human-alignment-optimizer-v4-native-subscription-exec-v2"',
    ),
    (
        '    "shell_tool", "unified_exec", "code_mode_host", "hooks", "auth_elicitation", "memories",',
        '    "shell_tool", "unified_exec", "code_mode", "hooks", "auth_elicitation", "memories",',
    ),
    (
        '"transport_identity": "codex_chatgpt_subscription_exec_tool_free_v1"',
        '"transport_identity": "codex_chatgpt_subscription_exec_tool_free_v2"',
    ),
)


def _bootstrap_sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bootstrap_stable_file_bytes(path: Path) -> bytes:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
        ):
            raise ValueError(f"HANNA native exec-v2 pinned path is reparsed: {current}")
    before = os.lstat(absolute)
    with absolute.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
        ):
            raise ValueError(f"HANNA native exec-v2 pinned file identity drifted: {absolute}")
        raw = handle.read()
        after = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ):
            raise ValueError(f"HANNA native exec-v2 pinned file changed during read: {absolute}")
    return raw


def _bootstrap_successor_source() -> bytes:
    raw = _bootstrap_stable_file_bytes(EXEC_V1_PATH)
    contract_raw = _bootstrap_stable_file_bytes(EXEC_V1_CONTRACT_PATH)
    if _bootstrap_sha(raw) != EXEC_V1_SHA256 or _bootstrap_sha(contract_raw) != EXEC_V1_CONTRACT_SHA256:
        raise ValueError("HANNA native exec-v2 predecessor bytes drifted")
    source = raw.decode("utf-8")
    for old, new in _SOURCE_PATCHES:
        if source.count(old) != 1 or new in source:
            raise ValueError("HANNA native exec-v2 exact source patch precondition drifted")
        source = source.replace(old, new, 1)
    if _bootstrap_sha(_bootstrap_stable_file_bytes(EXEC_V1_PATH)) != EXEC_V1_SHA256:
        raise ValueError("HANNA native exec-v2 predecessor changed during exact-byte load")
    return source.encode("utf-8")


_bootstrap_module_name = __name__
__name__ = "_hanna_v4_native_subscription_exec_v2_runtime"
exec(compile(_bootstrap_successor_source(), str(Path(__file__).resolve()), "exec"), globals())
__name__ = _bootstrap_module_name


_LOCALIZED_RUNNER_PATCH = (
    '        "code_mode_host",',
    '        "code_mode",',
)


def _load_call_codex() -> Callable[..., tuple[str, dict[str, Any]]]:
    """Load the pinned runner with exec-v2's single localized Codex startup correction."""

    raw = _stable_file_bytes(RUNNER_PATH)
    if _sha(raw) != RUNNER_SHA256:
        raise ValueError("HANNA native exec-v2 pinned runner bytes drifted")
    source_text = raw.decode("utf-8")
    old, new = _LOCALIZED_RUNNER_PATCH
    if source_text.count(old) != 1 or new in source_text:
        raise ValueError("HANNA native exec-v2 localized runner patch precondition drifted")
    source_text = source_text.replace(old, new, 1)
    source_root = str(REPOSITORY / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        importlib.import_module("hbqrs")
        module = ModuleType("hbqrs._hanna_native_exec_v2_localized_runner")
        module.__file__ = str(RUNNER_PATH)
        module.__package__ = "hbqrs"
        exec(compile(source_text, str(RUNNER_PATH), "exec"), module.__dict__)
    finally:
        if inserted:
            sys.path.remove(source_root)
    if _sha(_stable_file_bytes(RUNNER_PATH)) != RUNNER_SHA256:
        raise ValueError("HANNA native exec-v2 runner changed during localized exact-byte load")
    function = getattr(module, "_call_codex", None)
    if not callable(function):
        raise ValueError("HANNA native exec-v2 localized runner omitted its Codex call seam")
    return function


# Re-expose the successor's own predecessor commitment after the pinned source initializes its
# distinct native-subscription predecessor constants.
EXEC_V1_DIR = HERE.parent / "hbq-human-alignment-optimizer-v4-native-subscription-exec-v1"
EXEC_V1_PATH = EXEC_V1_DIR / "executor.py"
EXEC_V1_CONTRACT_PATH = EXEC_V1_DIR / "study-contract.json"
EXEC_V1_SHA256 = "5d2bd6871fe2013b8af5e166d89eeb020ff98889ce30494dd8889f7bee2d942f"
EXEC_V1_CONTRACT_SHA256 = "b132f0d29273a4896c2308f684c7df6547408195ef36c6d4f5f54ed263f86562"

if _bootstrap_module_name == "__main__":
    raise SystemExit(main())
