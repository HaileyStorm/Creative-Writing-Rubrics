"""Verify the literal HANNA development profile and its evidence pins."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1"
FREEZE_ID = "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
FREEZE_COMMIT = "436da1ef3f8cf239203ac6a80afe8f72708c0415"
FREEZE_RELATIVE = f"evaluation-results/{FREEZE_ID}/study.py"
FREEZE_SHA256 = "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf"
FREEZE_SCHEDULE_SHA256 = "bdb40b0f24f07ea938d57951768101a93ff62575919075abcd7bb9534e12c52c"
PROFILE_FILE_SHA256 = "0b9b7b7417c37534689ef3c159e7de1d7cc7a6eb0fb593e4f671a5e2686e9f28"
PUBLIC_FILES = {"README.md", "profile.json", "study-contract.json", "verify.py"}
AUTHORITY = {"status": "development_recommendation_only", "runtime": "none", "selection": "none", "promotion": "none", "generalization": "none"}
RESULT_PINS = {
    "broader_development_grok": {"commit": "5f50fbc2c345a55203cd2891d80037a797c6a1b4", "relative_path": "evaluation-results/hbq-human-alignment-optimizer-v5-f20-broader-development-grok-result-v2-v3-exec/result.json", "sha256": "89d18aa68e8285dd9cbe8f996413672aec3c19b740c869b2bbca66c54ccd3a32"},
    "grok_confirmation": {"commit": "aff71f0fc19e7f68e1f2c1e3c9377ca131b542d2", "relative_path": "evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-grok-replay-v2-native-json-normalization/result.json", "sha256": "ecb09a02d5caeb4130e91ff35b00cca48119d04c3d9b9b46dc0c1102c5ee2de4"},
    "sol_confirmation_v3": {"commit": "66859894b8081d83bd54ff4e9c40c0dd3050d0c5", "relative_path": "evaluation-results/hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v3-final-message/result.json", "sha256": "52933a37cd2cff49e8f494e540e485a9d6edbe936e09d7793442792472ffd368"},
}
CANDIDATE_ID = "broader-nextwave-13-missing_evidence_not_no"
CANDIDATE_SHA256 = "d8e55620d3a91ac17762d9ac40f7be3bb8aa87a478d6593f6ebda906d28b4684"
PARENT_ARTIFACT_SHA256 = "48055e2ab5d7c2b347aecf0895b46b8e468c2de2af06b25db3215fd3a0af158c"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _pairs(label: str):
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key in {label}")
            result[key] = value
        return result
    return pairs


def strict_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = Path(path).read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs(label), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    if not isinstance(value, dict) or raw != canonical(value):
        raise ValueError(f"{label} is not canonical JSON")
    return raw, value


def _blob(commit: str, relative: str) -> bytes:
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{relative}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned Git blob is absent")
    return result.stdout


def _load_freeze() -> ModuleType:
    path = REPO / FREEZE_RELATIVE
    raw = path.read_bytes()
    if sha256(raw) != FREEZE_SHA256 or _blob(FREEZE_COMMIT, FREEZE_RELATIVE) != raw:
        raise ValueError("pinned broader-freeze constructor drifted")
    spec = importlib.util.spec_from_file_location("_recommended_profile_freeze", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned broader-freeze constructor")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _reconstruct(profile: Mapping[str, Any], freeze: ModuleType) -> Mapping[str, Any]:
    parent = profile.get("parent_normalized")
    if not isinstance(parent, Mapping) or set(parent) != {"instruction", "instruction_sha256", "profile", "profile_sha256"}:
        raise ValueError("literal parent surface drifted")
    admitted = {"study_id": "hbq-human-alignment-optimizer-v5-f20-nextwave-grok-normalize-v1", "kind": "locally_normalized_provisional_grok_descendant", "normalized": parent}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / freeze.PARENT_FILE).write_bytes(canonical(admitted))
        original = freeze.PARENT_ARTIFACT_SHA256
        freeze.PARENT_ARTIFACT_SHA256 = sha256(canonical(admitted))
        try:
            children = freeze.descendants(root)
        finally:
            freeze.PARENT_ARTIFACT_SHA256 = original
    row = next((child for child in children if child.get("candidate_id") == CANDIDATE_ID), None)
    if not isinstance(row, Mapping):
        raise ValueError("canonical constructor omitted descendant13")
    return row


def _verify_profile(profile: Mapping[str, Any]) -> None:
    if set(profile) != {"candidate", "format_version", "instruction", "instruction_sha256", "parent_normalized", "profile", "profile_sha256", "study_id"}:
        raise ValueError("literal profile surface drifted")
    candidate = profile.get("candidate")
    if profile.get("study_id") != STUDY_ID or profile.get("format_version") != 1 or not isinstance(candidate, Mapping):
        raise ValueError("profile identity drifted")
    expected_candidate = {"candidate_id": CANDIDATE_ID, "candidate_sha256": CANDIDATE_SHA256, "parent_artifact_sha256": PARENT_ARTIFACT_SHA256, "factor": "missing_evidence_not_no", "addendum": "Step-05 evidence balance: evaluate positive and negative local evidence with the same standard; missing evidence is neutral, never NO or an automatic midpoint.", "requested_step_fraction": 0.05, "step_semantics": "planning_prior_not_numeric_or_semantic_distance"}
    if dict(candidate) != expected_candidate:
        raise ValueError("candidate manifest drifted")
    if not isinstance(profile.get("instruction"), str) or not isinstance(profile.get("profile"), dict):
        raise ValueError("literal prompt/profile bytes are absent")
    if profile.get("instruction_sha256") != sha256(profile["instruction"].encode("utf-8")):
        raise ValueError("literal instruction hash drifted")
    if profile.get("profile_sha256") != sha256(json.dumps(profile["profile"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")):
        raise ValueError("literal profile hash drifted")
    freeze = _load_freeze()
    row = _reconstruct(profile, freeze)
    if row["instruction_bytes"] != profile["instruction"].encode("utf-8") or row["profile_bytes"] != json.dumps(profile["profile"], ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"):
        raise ValueError("literal bytes differ from the canonical descendant constructor")
    if row["instruction_sha256"] != profile["instruction_sha256"] or row["profile_sha256"] != profile["profile_sha256"]:
        raise ValueError("canonical descendant hash drifted")
    identity = {"study_id": freeze.STUDY_ID, "parent_artifact_sha256": PARENT_ARTIFACT_SHA256, "ordinal": "13", "factor": candidate["factor"], "instruction_sha256": profile["instruction_sha256"], "profile_sha256": profile["profile_sha256"]}
    if freeze.sha256(identity) != CANDIDATE_SHA256:
        raise ValueError("published descendant identity drifted")


def _verify_result_pins() -> None:
    for name, pin in RESULT_PINS.items():
        raw, result = strict_json(REPO / pin["relative_path"], f"{name} result")
        if sha256(raw) != pin["sha256"]:
            raise ValueError(f"{name} result pin drifted")
        commit = pin["commit"]
        if commit is not None and _blob(commit, pin["relative_path"]) != raw:
            raise ValueError(f"{name} committed result pin drifted")
        if name == "broader_development_grok" and result.get("selection", {}).get("candidate_id") != CANDIDATE_ID:
            raise ValueError("broader development result no longer selects descendant13")
        if name == "broader_development_grok" and result.get("source_execution", {}).get("freeze_schedule_sha256") != FREEZE_SCHEDULE_SHA256:
            raise ValueError("broader frozen schedule commitment drifted")
        if name == "grok_confirmation" and result.get("comparison", {}).get("descendant_candidate_id") != CANDIDATE_ID:
            raise ValueError("Grok confirmation result no longer measures descendant13")
        if name == "sol_confirmation_v3" and result.get("study_id") != "hbq-human-alignment-optimizer-v5-f20-confirmation-sol-reconcile-v3-final-message":
            raise ValueError("Sol confirmation result identity drifted")


def validate_package(root: Path = HERE) -> dict[str, Any]:
    root = Path(root)
    if {path.name for path in root.iterdir()} != PUBLIC_FILES:
        raise ValueError("public package inventory drifted")
    profile_raw, profile = strict_json(root / "profile.json", "literal profile")
    if sha256(profile_raw) != PROFILE_FILE_SHA256:
        raise ValueError("literal profile file drifted")
    _verify_profile(profile)
    _contract_raw, contract = strict_json(root / "study-contract.json", "study contract")
    expected_freeze = {"commit": FREEZE_COMMIT, "relative_path": FREEZE_RELATIVE, "sha256": FREEZE_SHA256, "schedule_sha256": FREEZE_SCHEDULE_SHA256}
    if (contract.get("study_id") != STUDY_ID or contract.get("authority") != AUTHORITY
            or contract.get("profile_file_sha256") != PROFILE_FILE_SHA256
            or contract.get("pins") != {"broader_freeze": expected_freeze, **RESULT_PINS}):
        raise ValueError("study contract authority or pin drifted")
    _verify_result_pins()
    return {"study_id": STUDY_ID, "candidate_id": CANDIDATE_ID, "authority": AUTHORITY["status"], "profile_sha256": profile["profile_sha256"]}


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(json.dumps(validate_package(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
