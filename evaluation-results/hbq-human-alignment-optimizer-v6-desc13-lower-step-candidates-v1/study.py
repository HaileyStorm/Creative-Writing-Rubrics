"""Provider-free four-way lower-step candidate freeze from descendant 13."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-candidates-v1"
PARENT_PATH = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-recommended-development-profile-v1" / "profile.json"
PARENT_DOCUMENT_SHA256 = "0b9b7b7417c37534689ef3c159e7de1d7cc7a6eb0fb593e4f671a5e2686e9f28"
PARENT_CANDIDATE_ID = "broader-nextwave-13-missing_evidence_not_no"
PARENT_CANDIDATE_SHA256 = "d8e55620d3a91ac17762d9ac40f7be3bb8aa87a478d6593f6ebda906d28b4684"

CHILDREN = (
    ("broader-nextwave-15-construct_framing-speaker-attribution", "construct_framing", "Step-05 speaker attribution: for Coherence, resolve from the local passage who is speaking, feeling, or acting before evaluating its connective surface; do not assign a character's viewpoint to narration or narration to a character. This is a Coherence-only check."),
    ("broader-nextwave-16-scope_materiality-temporal-causality", "scope_materiality", "Step-05 relation scope: for Coherence, keep chronological sequence distinct from causal linkage on the supplied local surface; succession is not itself causation, and causation is not itself time order. This is a Coherence-only check."),
    ("broader-nextwave-17-scope_materiality-sustained-stakes", "scope_materiality", "Step-05 engagement scope: for Engagement, weigh stakes or curiosity sustained across the supplied passage rather than isolated hooks or one-line attention cues. This is an Engagement-only check."),
    ("broader-nextwave-18-construct_framing-referent-resolution", "construct_framing", "Step-05 referent resolution: for Coherence, resolve ambiguous pronouns and referents from the local passage before judging continuity; unresolved reference is distinct from a missing causal link. This is a Coherence-only check."),
)

REJECTED_GROK_LINEAGE = {
    "adaptation": "Locally repaired one-factor descendants; rejected Grok profiles are never promoted or reused as profiles.",
    "recovery_manifest_sha256": "69a4528aa81185bf0dea6e39481aadbd249c69efcf71bf267b605d67a0f53c68",
    "recovery_package": {
        "commit": "ece991d3b1e34524f6eeab8c12e97495ea23d442",
        "recover_py_sha256": "29549f86ff2f31809d713472fd5fc1f1db4298be50cfede6c88b9ea149c8d74e",
        "study_contract_sha256": "64fd45fc812f577fcbc7ef644fe291e8b71a89a394a17d09bb08b4fc23f43c9d",
        "study_id": "hbq-human-alignment-optimizer-v5-f20-descendant13-nextwave-grok-reconcile-v2-existing-output",
    },
    "source_variants": [
        {"candidate_id": CHILDREN[0][0], "envelope_sha256": "5a16ab7b99497f4912680afbaad6974d7949bee25db593f95bd915fdf9e017b8", "source_cell_id": "descendant13-nextwave-02-speaker-attribution", "source_variant_id": "speaker-attribution"},
        {"candidate_id": CHILDREN[1][0], "envelope_sha256": "73defa4de26a4fc9d53fd1b522dfb91339139e26b59314112c505685bec5ec10", "source_cell_id": "descendant13-nextwave-03-temporal-causality-separation", "source_variant_id": "temporal-causality-separation"},
        {"candidate_id": CHILDREN[2][0], "envelope_sha256": "0f1861e49ae99f42c969ada1e8e7d6b62f4760a7c86e08c8828cc9f29a3dd96d", "source_cell_id": "descendant13-nextwave-08-engagement-stakes-distinction", "source_variant_id": "engagement-stakes-distinction"},
        {"candidate_id": CHILDREN[3][0], "envelope_sha256": "0bae24c86c9f67635c775c699df7c35e305cd7a2f4fc6a4acf2f8a6539d06d58", "source_cell_id": "descendant13-nextwave-09-coherence-reference-resolution", "source_variant_id": "coherence-reference-resolution"},
    ],
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _ancestry(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int | None], ...]:
    lexical = Path(os.path.abspath(path))
    values: list[tuple[str, int, int, int, int | None]] = []
    for index, current in enumerate((lexical, *lexical.parents)):
        try:
            info = os.lstat(current)
        except OSError as error:
            raise ValueError("artifact ancestry cannot be inspected") from error
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe reparse artifact ancestry")
        expected_directory = directory if index == 0 else True
        if bool(stat.S_ISDIR(info.st_mode)) != expected_directory:
            raise ValueError("unexpected artifact ancestry type")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), None if expected_directory else info.st_size))
    return tuple(values)


def _plain(path: Path, *, directory: bool) -> None:
    _ancestry(path, directory=directory)


def _stable_read(path: Path) -> tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]:
    target = Path(path)
    before = _ancestry(target, directory=False)
    try:
        with target.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            raw = handle.read()
            after_open = os.fstat(handle.fileno())
    except OSError as error:
        raise ValueError("artifact cannot be stably read") from error
    after = _ancestry(target, directory=False)
    opened_identity = (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size)
    if before != after or before[0][1:] != opened_identity or opened_identity != (after_open.st_dev, after_open.st_ino, stat.S_IFMT(after_open.st_mode), after_open.st_size):
        raise ValueError("stable full-ancestry read drift")
    return raw, before


def _stable(path: Path) -> bytes:
    return _stable_read(path)[0]


def strict_json(path: Path, label: str) -> dict[str, Any]:
    return _strict_raw(_stable(path), label)


def _strict_raw(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    if not isinstance(value, dict) or raw != canonical(value):
        raise ValueError(f"{label} must be canonical JSON")
    return value


def _parent(parent_path: Path = PARENT_PATH) -> tuple[dict[str, Any], bytes, dict[str, Any], bytes, tuple[tuple[str, int, int, int, int | None], ...]]:
    path = Path(parent_path)
    raw, ancestry = _stable_read(path)
    if sha256(raw) != PARENT_DOCUMENT_SHA256:
        raise ValueError("immutable recommended descendant13 document drifted")
    value = _strict_raw(raw, "recommended descendant13 document")
    candidate = value.get("candidate")
    instruction = value.get("instruction")
    profile = value.get("profile")
    normalized = value.get("parent_normalized")
    if (not isinstance(candidate, Mapping) or candidate.get("candidate_id") != PARENT_CANDIDATE_ID
            or candidate.get("candidate_sha256") != PARENT_CANDIDATE_SHA256
            or not isinstance(instruction, str) or not isinstance(profile, dict)
            or not isinstance(normalized, Mapping) or normalized.get("instruction") != instruction
            or not isinstance(normalized.get("profile"), Mapping)):
        raise ValueError("immutable recommended descendant13 shape drifted")
    instruction_bytes = instruction.encode("utf-8")
    profile_bytes = json_bytes(profile)
    if value.get("instruction_sha256") != sha256(instruction_bytes) or value.get("profile_sha256") != sha256(profile_bytes):
        raise ValueError("immutable recommended descendant13 bindings drifted")
    return value, instruction_bytes, profile, profile_bytes, ancestry


def _candidate(*, candidate_id: str, factor: str, addendum: str, instruction: bytes, parent_profile: Mapping[str, Any]) -> dict[str, Any]:
    factors = parent_profile.get("factors")
    if not isinstance(factors, dict):
        raise TypeError("parent factor surface drifted")
    if factor not in factors or not isinstance(factors[factor], str):
        raise ValueError("parent factor surface drifted")
    if any(not isinstance(key, str) or not isinstance(item, str) for key, item in factors.items()):
        raise ValueError("parent factor values drifted")
    profile = deepcopy(parent_profile)
    child_factors = profile["factors"]
    child_factors[factor] = factors[factor] + "\n" + addendum
    changed = [key for key in factors if child_factors.get(key) != factors[key]]
    if set(child_factors) != set(factors) or changed != [factor] or child_factors[factor].count(addendum) != 1:
        raise ValueError("candidate must append one unique addendum to one existing factor")
    profile_bytes = json_bytes(profile)
    identity = {
        "study_id": STUDY_ID,
        "parent_document_sha256": PARENT_DOCUMENT_SHA256,
        "parent_candidate_sha256": PARENT_CANDIDATE_SHA256,
        "candidate_id": candidate_id,
        "factor": factor,
        "addendum": addendum,
        "instruction_sha256": sha256(instruction),
        "profile_sha256": sha256(profile_bytes),
    }
    return {
        "addendum": addendum,
        "candidate_id": candidate_id,
        "candidate_sha256": sha256(identity),
        "factor": factor,
        "instruction_base64": base64.b64encode(instruction).decode("ascii"),
        "instruction_sha256": sha256(instruction),
        "kind": "one_factor_one_clause_descendant",
        "parent_candidate_id": PARENT_CANDIDATE_ID,
        "parent_candidate_sha256": PARENT_CANDIDATE_SHA256,
        "parent_document_sha256": PARENT_DOCUMENT_SHA256,
        "profile_base64": base64.b64encode(profile_bytes).decode("ascii"),
        "profile_sha256": sha256(profile_bytes),
    }


def _materialize(*, parent_path: Path = PARENT_PATH) -> tuple[dict[str, Any], tuple[tuple[str, int, int, int, int | None], ...]]:
    _parent_document, instruction, profile, _profile_bytes, ancestry = _parent(parent_path)
    if len(CHILDREN) != 4 or len({row[0] for row in CHILDREN}) != 4 or len({row[2] for row in CHILDREN}) != 4:
        raise ValueError("four-candidate geometry or addendum uniqueness drifted")
    candidates = [_candidate(candidate_id=candidate_id, factor=factor, addendum=addendum, instruction=instruction, parent_profile=profile) for candidate_id, factor, addendum in CHILDREN]
    if len(candidates) != 4 or len({row["candidate_id"] for row in candidates}) != 4:
        raise ValueError("four-candidate geometry drifted")
    value = {
        "authority": {"dspy_optuna_runtime": "forbidden", "process_launches": 0, "provider_calls_made": 0, "selection": "none"},
        "candidate_count": 4,
        "candidates": candidates,
        "format_version": 1,
        "kind": "provider_free_descendant13_lower_step_candidate_freeze",
        "parent": {"candidate_id": PARENT_CANDIDATE_ID, "candidate_sha256": PARENT_CANDIDATE_SHA256, "document_sha256": PARENT_DOCUMENT_SHA256},
        "study_id": STUDY_ID,
    }
    value["manifest_sha256"] = sha256(value)
    _validate_contract(value)
    assert_no_fresh96_leakage(value)
    return value, ancestry


def materialize(*, parent_path: Path = PARENT_PATH) -> dict[str, Any]:
    return _materialize(parent_path=parent_path)[0]


def contract() -> dict[str, Any]:
    return strict_json(HERE / "study-contract.json", "study contract")


def _validate_contract(manifest: Mapping[str, Any]) -> None:
    expected = contract()
    fixed = expected.get("frozen_commitments")
    if (set(expected) != {"format_version", "frozen_commitments", "kind", "lineage", "study_id"}
            or expected.get("format_version") != 1 or expected.get("study_id") != STUDY_ID or expected.get("kind") != "provider_free_descendant13_lower_step_candidate_freeze"
            or expected.get("lineage") != REJECTED_GROK_LINEAGE
            or not isinstance(fixed, Mapping) or fixed.get("manifest_sha256") != manifest.get("manifest_sha256")
            or fixed.get("candidate_sha256s") != [row["candidate_sha256"] for row in manifest.get("candidates", [])]):
        raise ValueError("frozen candidate commitments drifted")


def assert_no_fresh96_leakage(value: Mapping[str, Any], *, forbidden: tuple[str, ...] = ()) -> None:
    rendered = canonical(value).decode("utf-8")
    if isinstance(value.get("candidates"), list):
        for candidate in value["candidates"]:
            if isinstance(candidate, Mapping):
                for key in ("instruction_base64", "profile_base64"):
                    encoded = candidate.get(key)
                    if isinstance(encoded, str):
                        try:
                            rendered += base64.b64decode(encoded, validate=True).decode("utf-8")
                        except (UnicodeDecodeError, ValueError):
                            raise ValueError("candidate byte encoding drifted") from None
    rendered = rendered.lower()
    blocked = ("hanna96", "private-freeze", "future_confirmation", "prompt-", "item-", "\"target\":", "\\\\users\\\\", "c:/users/") + tuple(item.lower() for item in forbidden)
    normalized = re.sub(r"[-_\s]+", "", rendered)
    normalized_blocked = ("hanna96", "fresh96", "futureconfirmation", "privatefreeze")
    if any(item and item in rendered for item in blocked) or any(item in normalized for item in normalized_blocked):
        raise ValueError("Fresh96 identifier, path, or score leakage")


def freeze(*, output_root: Path, parent_path: Path = PARENT_PATH) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists():
        raise ValueError("candidate-freeze output root must be fresh")
    _plain(root.parent, directory=True)
    manifest, parent_ancestry = _materialize(parent_path=parent_path)
    repeat, repeat_ancestry = _materialize(parent_path=parent_path)
    if repeat != manifest or repeat_ancestry != parent_ancestry:
        raise ValueError("parent changed between materialization phases")
    root.mkdir(parents=True)
    for candidate in manifest["candidates"]:
        (root / f"{candidate['candidate_id']}.json").write_bytes(canonical(candidate))
    (root / "manifest.json").write_bytes(canonical(manifest))
    validate_frozen_root(root, parent_path=parent_path, expected_parent_ancestry=parent_ancestry)
    return manifest


def validate_frozen_root(
    root: Path,
    *,
    parent_path: Path = PARENT_PATH,
    expected_parent_ancestry: tuple[tuple[str, int, int, int, int | None], ...] | None = None,
) -> dict[str, Any]:
    root = Path(root)
    _plain(root, directory=True)
    actual = {path.name for path in root.iterdir()}
    expected = {"manifest.json", *(f"{candidate_id}.json" for candidate_id, _factor, _addendum in CHILDREN)}
    if actual != expected:
        raise ValueError("candidate-freeze inventory drifted")
    manifest = strict_json(root / "manifest.json", "persisted manifest")
    rebuilt, observed_parent_ancestry = _materialize(parent_path=parent_path)
    if expected_parent_ancestry is not None and observed_parent_ancestry != expected_parent_ancestry:
        raise ValueError("parent changed before final frozen-root validation")
    if manifest != rebuilt:
        raise ValueError("persisted manifest or immutable parent drifted")
    for candidate in manifest["candidates"]:
        persisted = strict_json(root / f"{candidate['candidate_id']}.json", "persisted candidate")
        if persisted != candidate:
            raise ValueError("persisted candidate bytes drifted")
    return manifest
