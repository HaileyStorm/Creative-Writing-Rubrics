import json
import os
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_SHA256 = "bbd2ddf6dc8d251c369019a6c259e6d1502497073537547263e7ce703abe9319"
SOURCE_REVISION = "e363d645b443b865fcab137af5882460961959e0"
SOURCE_TREE = "82344e75272f7223beda8f5f008b4e9b9de11769"
PRIVATE_MANIFEST_ENV = "CWR_ARTIFACT_CUSTODY_MANIFEST"
ABSOLUTE_PATH = re.compile(r"(?i)(?:^|\s)(?:[a-z]:[\\/]|/|\\\\)")

FAMILIES = {
    "pytest-regenerable-output": {
        "receipt": "pytest-regenerable-output.v1.json",
        "members": [
            "pytest",
            "pytest-124310bf94f14f9fa3f5f9dbf54cdd49",
            "pytest-63668eaa342e4563bdf61a8c541408cb",
            "pytest-aliases",
            "pytest-checkpoint-tool",
            "pytest-checkpoint-v2",
            "pytest-full-after-fixes",
            "pytest-full-baseline-final",
            "pytest-packaging-final",
            "pytest-public-eval-final",
            "pytest-review-fixes",
            "pytest-review-fixes-v2",
            "pytest-review-fixes-v3",
            "pytest-runner-final-post-version",
            "pytest-runner-first",
            "pytest-runner-full-final",
            "pytest-runner-release-final",
            "pytest-runner-second",
            "pytest-runner-third",
            "pytest-runner-v4",
            "pytest-schema",
            "pytest-targeted-2",
        ],
    },
    "large-final-regenerable-output": {
        "receipt": "large-final-regenerable-output.v1.json",
        "members": [
            "full-af033eca873e49f0b62cbfd547a91868",
            "full-exact-final",
            "full-final",
            "full-final-20260820",
        ],
    },
}


@pytest.mark.parametrize("family, expected", FAMILIES.items())
def test_public_receipt_is_structurally_complete_and_path_safe(
    family: str, expected: dict[str, object]
) -> None:
    receipt_path = ROOT / "artifact-receipts" / str(expected["receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    strings = []

    def collect_strings(value: object) -> None:
        if isinstance(value, str):
            strings.append(value)
        elif isinstance(value, dict):
            for nested in value.values():
                collect_strings(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_strings(nested)

    collect_strings(receipt)
    assert not any(ABSOLUTE_PATH.search(value) for value in strings)
    assert receipt["schema"] == "cwr-artifact-regeneration-receipt/v1"
    assert receipt["logical_root_id"] == "cwr-historical-artifacts-20260820-v1"
    assert receipt["custody_manifest_sha256"] == MANIFEST_SHA256
    assert receipt["source_revision"] == SOURCE_REVISION
    assert receipt["source_materialization"] == {
        "commit": SOURCE_REVISION,
        "tree": SOURCE_TREE,
        "clean_worktree_execution_claimed": False,
    }
    assert receipt["family"] == family
    assert receipt["historical_identity"] == "not_claimed"
    assert receipt["direct_members"] == expected["members"]

    verification = receipt["verification"]
    assert verification["status"] == "BLOCKED"
    assert verification["commands"]
    assert len(verification["private_attempt_sha256"]) == 64
    assert verification["replacement_output_sha256"] is None
    assert verification["private_replacement_receipt_sha256"] is None
    assert verification["blocker"]

    portable_verifier = receipt["portable_verifier"]
    assert portable_verifier == {
        "command": ".\\.venv\\Scripts\\python.exe -m pytest -q tests/test_artifact_receipts_pytest_large_v1.py",
        "tests": 5,
        "passed": 3,
        "failures": 0,
        "errors": 0,
        "skipped_private_integrations": 2,
    }
    private_integration = receipt["private_custody_integration"]
    assert private_integration["environment_variable"] == PRIVATE_MANIFEST_ENV
    assert private_integration["tests"] == 2
    assert private_integration["passed"] == 2
    assert private_integration["failures"] == 0
    assert private_integration["errors"] == 0
    assert len(private_integration["private_output_sha256"]) == 64
    assert receipt["cleanup_status"] == "BLOCKED"
    assert receipt["safe_cleanup_members"] == []
    assert receipt["physical_cleanup_executed"] is False


def test_claimed_source_revision_is_materialized_locally() -> None:
    commit = subprocess.run(
        ["git", "rev-parse", f"{SOURCE_REVISION}^{{commit}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", f"{SOURCE_REVISION}^{{tree}}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert commit == SOURCE_REVISION
    assert tree == SOURCE_TREE


@pytest.mark.parametrize("family, expected", FAMILIES.items())
def test_private_custody_members_match_only_when_explicitly_configured(
    family: str, expected: dict[str, object]
) -> None:
    configured = os.environ.get(PRIVATE_MANIFEST_ENV)
    if not configured:
        pytest.skip(f"set {PRIVATE_MANIFEST_ENV} for private custody integration")

    manifest_path = Path(configured)
    assert manifest_path.is_file()
    receipt = json.loads(
        (ROOT / "artifact-receipts" / str(expected["receipt"])).read_text(encoding="utf-8")
    )
    manifest_members = sorted(
        record["relative_path"]
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if (record := json.loads(line)).get("record_type") == "custody_entry"
        and record["root_family"] == family
        and record["entry_type"] == "directory"
        and "/" not in record["relative_path"]
    )
    assert receipt["direct_members"] == manifest_members
