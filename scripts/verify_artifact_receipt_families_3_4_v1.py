"""Validate public-safe regeneration receipts for artifact families 3 and 4."""

from __future__ import annotations

import json
import re
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RECEIPT_DIRECTORY = ROOT / "artifact-receipts"
MANIFEST_SHA256 = "bbd2ddf6dc8d251c369019a6c259e6d1502497073537547263e7ce703abe9319"
LOGICAL_ROOT_ID = "cwr-historical-artifacts-20260820-v1"
WORKSPACE_MEMBERS = (
    "exact-final-a4bf165804b8444ca417b38f865191b1",
    "final-523109f6cf164d2b82fd218a99fe2669",
    "focused-v3",
    "longform-v5",
    "targeted-release-20260820",
    "cli-final",
    "temp-verify",
)
ISOLATED_INSTALL_MEMBER = "isolated-install-final"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GIT_SHA1 = re.compile(r"[0-9a-f]{40}\Z")
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|(?:^|[\"'\s])/(?:home|private|tmp|users|var)(?:/|$))", re.IGNORECASE)
PRIVATE_PATH_TOKENS = ("appdata", "cwr-artifact-custody-20260823", "\\users\\", "/users/")


def _read_receipt(name: str) -> dict[str, Any]:
    value = json.loads((RECEIPT_DIRECTORY / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain an object")
    return value


def _expect_hash(value: object, field: str) -> None:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _check_public_safety(value: object, context: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _check_public_safety(item, f"{context}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_public_safety(item, f"{context}[{index}]")
    elif isinstance(value, str):
        normalized = value.lower()
        if ABSOLUTE_PATH.search(value) or any(token in normalized for token in PRIVATE_PATH_TOKENS):
            raise ValueError(f"{context} leaks a local or private path")


def _git_blob(commit: str, path: str) -> bytes:
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot read pinned source blob {path}")
    return result.stdout


def _materialize_mixed_eol(blob: bytes, lf_line_numbers: list[int]) -> bytes:
    lines = blob.splitlines(keepends=True)
    expected_lines = set(lf_line_numbers)
    if len(expected_lines) != len(lf_line_numbers) or any(line < 1 or line > len(lines) for line in expected_lines):
        raise ValueError("invalid LF line map")
    rendered: list[bytes] = []
    for index, line in enumerate(lines, start=1):
        if line.endswith(b"\n"):
            ending = b"\n" if index in expected_lines else b"\r\n"
            rendered.append(line[:-1] + ending)
        else:
            rendered.append(line)
    return b"".join(rendered)


def _check_source_materialization(source: dict[str, Any]) -> None:
    materialization = source.get("materialization")
    if not isinstance(materialization, dict) or materialization.get("rule") != "mixed_eol_line_map_v1":
        raise ValueError("source materialization rule must be mixed_eol_line_map_v1")
    line_map = materialization.get("lf_line_numbers")
    if not isinstance(line_map, dict):
        raise ValueError("source materialization requires an LF line map")
    files = source.get("files")
    if not isinstance(files, dict) or set(files) != {"pyproject.toml", "manifest.json"}:
        raise ValueError("source must bind exactly the package and manifest files")
    if set(line_map) != set(files):
        raise ValueError("LF line map must bind exactly the source files")
    commit = source["git_commit_sha1"]
    for path, binding in files.items():
        if not isinstance(binding, dict):
            raise ValueError(f"missing binding for {path}")
        blob_sha1 = binding.get("git_blob_sha1")
        if not isinstance(blob_sha1, str) or not GIT_SHA1.fullmatch(blob_sha1):
            raise ValueError(f"{path} git blob must be a full lowercase SHA-1")
        _expect_hash(binding.get("git_blob_sha256"), f"{path} git blob hash")
        _expect_hash(binding.get("materialized_sha256"), f"{path} materialized hash")
        blob = _git_blob(commit, path)
        header = b"blob " + str(len(blob)).encode() + b"\x00"
        if hashlib.sha1(header + blob).hexdigest() != blob_sha1:
            raise ValueError(f"{path} git blob identifier mismatch")
        if hashlib.sha256(blob).hexdigest() != binding["git_blob_sha256"]:
            raise ValueError(f"{path} git blob digest mismatch")
        if b"\r" in blob:
            raise ValueError(f"{path} cannot use a line-ending map with carriage returns in its blob")
        lf_line_numbers = line_map[path]
        if not isinstance(lf_line_numbers, list) or not all(isinstance(line, int) for line in lf_line_numbers):
            raise ValueError(f"{path} LF line map must contain integers")
        materialized = _materialize_mixed_eol(blob, lf_line_numbers)
        if hashlib.sha256(materialized).hexdigest() != binding["materialized_sha256"]:
            raise ValueError(f"{path} materialized digest mismatch")


def _check_common(receipt: dict[str, Any], expected_family: str) -> None:
    if receipt.get("schema") != "cwr-artifact-regeneration-receipt/v1":
        raise ValueError("unexpected receipt schema")
    if receipt.get("family") != expected_family:
        raise ValueError("unexpected receipt family")
    if receipt.get("logical_root_id") != LOGICAL_ROOT_ID:
        raise ValueError("unexpected logical root")
    custody = receipt.get("custody_manifest")
    if not isinstance(custody, dict):
        raise ValueError("missing custody manifest binding")
    if custody.get("sha256") != MANIFEST_SHA256:
        raise ValueError("custody manifest digest mismatch")
    source = receipt.get("source")
    if not isinstance(source, dict):
        raise ValueError("missing source binding")
    revision = source.get("git_commit_sha1")
    if not isinstance(revision, str) or not GIT_SHA1.fullmatch(revision):
        raise ValueError("source git commit must be a full lowercase SHA-1")
    _check_source_materialization(source)
    _check_public_safety(receipt)
    cleanup = receipt.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("status") != "NOT_EXECUTED":
        raise ValueError("receipt must not claim physical cleanup")
    if cleanup.get("historical_paths_deleted") != []:
        raise ValueError("receipt must record no historical deletion")


def _check_replacement(record: object) -> None:
    if not isinstance(record, dict):
        raise ValueError("replacement record must be an object")
    if not isinstance(record.get("command"), str) or not record["command"]:
        raise ValueError("replacement command is required")
    if record.get("exit_code") != 0 or record.get("result") != "PASS":
        raise ValueError("replacement must have passed")
    _expect_hash(record.get("stdout_sha256"), "replacement stdout hash")
    _expect_hash(record.get("output_tree_sha256"), "replacement output tree hash")


def _check_workspace() -> None:
    receipt = _read_receipt("workspace-regenerable-output.v1.json")
    _check_common(receipt, "workspace-regenerable-output")
    if tuple(receipt.get("historical_members", ())) != WORKSPACE_MEMBERS:
        raise ValueError("workspace members differ from the approved exact family")
    replacements = receipt.get("replacements")
    if not isinstance(replacements, list) or len(replacements) != len(WORKSPACE_MEMBERS):
        raise ValueError("workspace receipt must have one replacement per member")
    if tuple(item.get("historical_member") for item in replacements if isinstance(item, dict)) != WORKSPACE_MEMBERS:
        raise ValueError("workspace replacements must preserve member order")
    for record in replacements:
        _check_replacement(record)
    if receipt.get("temporary_outputs_retained") is not True:
        raise ValueError("receipt must disclose retained temporary outputs")
    if receipt.get("temporary_cleanup_status") != "BLOCKED_BY_EXECUTOR_DELETION_POLICY":
        raise ValueError("receipt must disclose the temporary cleanup blocker")


def _check_isolated_install() -> None:
    receipt = _read_receipt("isolated-install-regenerable-output.v1.json")
    _check_common(receipt, "isolated-install-regenerable-output")
    if receipt.get("historical_members") != [ISOLATED_INSTALL_MEMBER]:
        raise ValueError("isolated-install receipt has an unexpected member")
    steps = receipt.get("replacement_steps")
    if not isinstance(steps, list) or len(steps) < 3:
        raise ValueError("isolated-install receipt must record build, install, and smoke steps")
    for step in steps:
        _check_replacement(step)
    artifacts = receipt.get("replacement_artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("isolated-install receipt must bind replacement artifacts")
    _expect_hash(artifacts.get("wheel_sha256"), "wheel hash")
    _expect_hash(artifacts.get("smoke_output_sha256"), "smoke output hash")
    if receipt.get("temporary_install_retained") is not True:
        raise ValueError("receipt must disclose the retained temporary environment")
    if receipt.get("temporary_cleanup_status") != "BLOCKED_BY_EXECUTOR_DELETION_POLICY":
        raise ValueError("receipt must disclose the temporary cleanup blocker")


def main() -> int:
    _check_workspace()
    _check_isolated_install()
    print("artifact receipt families 3 and 4: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
