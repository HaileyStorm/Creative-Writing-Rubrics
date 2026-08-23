from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "artifact-receipts"
CUSTODY_SHA256 = "bbd2ddf6dc8d251c369019a6c259e6d1502497073537547263e7ce703abe9319"
SOURCE_SHA = "e363d645b443b865fcab137af5882460961959e0"
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
HEX_GIT_BLOB = re.compile(r"^[0-9a-f]{40}$")
NORMALIZED_MATERIALIZATION = "git archive --format=tar <source-commit> | tar.exe -xf - -C <isolated-source>"
PRIVATE_PATH_MARKERS = ("haile", "documents")
ABSOLUTE_PATH = re.compile(r"(?:[a-zA-Z]:[\\/]|(?:^|[\\/])(?:users|home)[\\/]|\\\\)")


def _receipt(name: str) -> dict[str, object]:
    return json.loads((RECEIPTS / name).read_text(encoding="utf-8"))


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    return []


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _assert_public_paths_only(receipt: dict[str, object]) -> None:
    for value in _strings(receipt):
        assert not ABSOLUTE_PATH.search(value), value
        assert not any(marker in value.casefold() for marker in PRIVATE_PATH_MARKERS), value


def _assert_common_receipt_fields(receipt: dict[str, object], family: str) -> None:
    assert receipt["schema"] == "cwr-artifact-replacement-receipt/v1"
    assert receipt["logical_root_id"] == "cwr-historical-artifacts-20260820-v1"
    assert receipt["family"] == family
    custody = receipt["custody_manifest"]
    assert isinstance(custody, dict)
    assert custody["sha256"] == CUSTODY_SHA256
    source = receipt["source"]
    assert isinstance(source, dict)
    assert source["git_commit"] == SOURCE_SHA
    assert source["materialization"] == NORMALIZED_MATERIALIZATION
    assert _git("cat-file", "-e", f"{SOURCE_SHA}^{{commit}}") == ""
    blobs = source["input_blobs"]
    assert isinstance(blobs, dict)
    for path, expected_blob in blobs.items():
        assert isinstance(path, str)
        assert isinstance(expected_blob, str) and HEX_GIT_BLOB.fullmatch(expected_blob)
        assert _git("rev-parse", f"{SOURCE_SHA}:{path}") == expected_blob
    _assert_public_paths_only(receipt)


def test_distribution_receipt_is_explicitly_blocked_without_replacement_hashes() -> None:
    receipt = _receipt("distribution-regenerable-output.v1.json")
    _assert_common_receipt_fields(receipt, "distribution-regenerable-output")
    assert receipt["status"] == "BLOCKED"
    assert [member["relative_path"] for member in receipt["manifest_members"]] == [
        "dist",
        "dist-fixed",
        "dist-final",
        "public-final",
        "public-score-final",
        "public-surface-final-20260820",
        "public-448c461-installed-dry-run",
    ]
    historical = receipt["historical_1_1_0_evidence"]
    assert isinstance(historical, dict)
    assert historical["comparison"].startswith("NOT_PERFORMED")
    assert all(HEX_SHA256.fullmatch(item["sha256"]) for item in historical["artifacts"])
    attempts = receipt["build_attempts"]
    assert [attempt["result"] for attempt in attempts] == ["BLOCKED_TIMEOUT", "BLOCKED_TIMEOUT"]
    assert receipt["replacement_artifact_hashes"] == []
    cleanup = receipt["cleanup"]
    assert isinstance(cleanup, dict)
    assert cleanup["eligible"] is False
    assert cleanup["members"] == []


def test_cli_validation_receipt_maps_every_member_to_a_successful_pinned_source_result() -> None:
    receipt = _receipt("cli-validation-regenerable-output.v1.json")
    _assert_common_receipt_fields(receipt, "cli-validation-regenerable-output")
    assert receipt["status"] == "GO"
    members = receipt["manifest_members"]
    results = receipt["replacement_results"]
    assert [member["relative_path"] for member in members] == [result["member"] for result in results]
    assert all(HEX_SHA256.fullmatch(member["sha256"]) for member in members)
    assert all(result["exit_code"] == 0 and HEX_SHA256.fullmatch(result["sha256"]) for result in results)
    validation = receipt["validation"]
    assert validation["result"] == {
        "exit_code": 0,
        "module_count": 278,
        "bundle_count": 85,
        "question_count": 2145,
    }
    cleanup = receipt["cleanup"]
    assert isinstance(cleanup, dict)
    assert cleanup["eligible"] is True
    assert cleanup["execution_authorized"] is False
    assert cleanup["members"] == [member["relative_path"] for member in members]
