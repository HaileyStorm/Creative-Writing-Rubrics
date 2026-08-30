"""Provider-free, independently replayed schedule for HANNA shrinkage evaluation."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-shrinkage-eval-v1"
HELDOUT_STUDY_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1" / "study.py"
HELDOUT_STUDY_SHA256 = "770b8c496df3c86dbc6ae3c7673d462428f81bcbddf84e493ea7c6710bd1b346"
PUBLIC_RESULT_ROOT = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-exec-v1-public-result-v1"
PUBLIC_ARTIFACT_SHA256 = {
    "grok-selection.json": "1cc2d24ae3e6793683d1e3ec1118b0358ef3861099e5dc00f3588bac3ac38eb3",
    "endpoint-result.json": "2c9e6716e2419e420ee03a6d0bb64b1a2863df00bc44f666320b17732207d227",
    "public-result.json": "4bc51804857841b59d6ed5150993460f0dbb9767b22591526e37d14b88ea97b7",
    "provenance.v1.json": "f3ec4adc9b07dac635b034a8ecbc3cdf81021d03f860d936c9fc1d30d9dbfd85",
    "feedback-selection.json": "5b49688f85a530a7ab22cee382514bfd659eec4ef2d8bb68a9b223554aefb816",
    "feedback-result.json": "2ecaf697c8ff729e3545e7004113b0ac186428623d4116fa4e505df950bd1a25",
    "study-contract.json": "8022c4387718cd6491b7a6a83d6a64da7a42c85d7d640f18d42ee5d9eb70e4df",
}
PUBLIC_PRODUCER_SOURCE_SHA256 = "f64809efdb248ea87408e6cdb49e8d9727dc13614cbfa823cc3d4d90fbde4919"
ADMISSION_PATH = HERE / "declared-mechanism-admission.json"
ADMISSION_FILE_SHA256 = "c459a929a47f9d890f1ec2bb46fd9c939b2ea72999635ed0aaf01eaf24a1ca14"
BASELINE_ID = "candidate-52d1be4bc34e0018"
UNUSED_DEVELOPMENT_GROUPS = (
    ("prompt-7c393c4bcb3a7484", "item-2377fcf24510aac5"),
    ("prompt-8997770ce6efe4d5", "item-0cb9c7afe8527434"),
    ("prompt-8d3d397a4f6ba0ea", "item-1b27b9076eef2bc5"),
)
_SCHEDULE_TOKEN = object()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _canonical_file(path: Path, *, label: str, expected_sha256: str | None = None) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    if expected_sha256 is not None and sha256(raw) != expected_sha256:
        raise ValueError(f"HANNA shrinkage {label} hash drifted")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"HANNA shrinkage {label} is invalid JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"HANNA shrinkage {label} must be canonical JSON")
    return value, raw


def _module(path: Path, digest: str, name: str) -> ModuleType:
    raw = path.read_bytes()
    if sha256(raw) != digest:
        raise ValueError("HANNA shrinkage pinned held-out study drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("HANNA shrinkage cannot load pinned held-out study")
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102 - exact pinned source replay
    return module


def _heldout() -> ModuleType:
    return _module(HELDOUT_STUDY_PATH, HELDOUT_STUDY_SHA256, "_hanna_shrinkage_heldout")


def _feedback(root: Path) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {}; raws: dict[str, bytes] = {}
    for name, digest in PUBLIC_ARTIFACT_SHA256.items():
        values[name], raws[name] = _canonical_file(Path(root) / name, label=f"r4 feedback {name}", expected_sha256=digest)
    selection, endpoint = values["grok-selection.json"], values["endpoint-result.json"]
    public, provenance = values["public-result.json"], values["provenance.v1.json"]
    feedback_selection, feedback_result, contract = values["feedback-selection.json"], values["feedback-result.json"], values["study-contract.json"]
    if (public.get("claim") != "no_independently_observed_heldout_gain" or public.get("gain_observed") is not False
            or public.get("confirmation") != {"cells": 0, "status": "unopened"}
            or public.get("selected_candidate_id") != selection.get("selected_candidate_id")
            or public.get("artifacts", {}).get("grok_selection", {}).get("sha256") != sha256(raws["grok-selection.json"])
            or public.get("artifacts", {}).get("endpoint_result", {}).get("sha256") != sha256(raws["endpoint-result.json"])
            or endpoint.get("grok_selection") != selection
            or provenance.get("derived_commitments", {}).get("grok_selection_artifact_sha256") != sha256(raws["grok-selection.json"])
            or provenance.get("derived_commitments", {}).get("endpoint_result_artifact_sha256") != sha256(raws["endpoint-result.json"])
            or provenance.get("derived_commitments", {}).get("public_result_artifact_sha256") != sha256(raws["public-result.json"])
            or provenance.get("source_commitments", {}).get("reconciliation_manifest_sha256") != "26b91ea23f04b55909db775b75c1bf7ae2d4819d2acc8346244548296e229bf3"
            or feedback_selection.get("grok_selection") != selection or feedback_result.get("endpoint_result") != endpoint
            or feedback_result.get("public_result") != public or contract.get("producer_source", {}).get("sha256") != PUBLIC_PRODUCER_SOURCE_SHA256
            or sha256((Path(root) / "materialize.py").read_bytes()) != PUBLIC_PRODUCER_SOURCE_SHA256):
        raise ValueError("HANNA shrinkage r4 feedback artifact chain drifted")
    return {"artifact_sha256": dict(PUBLIC_ARTIFACT_SHA256), "selected_candidate_id": selection["selected_candidate_id"], "claim": public["claim"]}


def _groups(split: Mapping[str, Any]) -> list[dict[str, str]]:
    grouped: dict[str, list[str]] = {}
    for row in split["items"]:
        if row["partition"] == "development": grouped.setdefault(row["prompt_group_id"], []).append(row["item_id"])
    all_development = [{"partition": "development", "prompt_group_id": key, "item_id": min(items)} for key, items in sorted(grouped.items())]
    expected = [{"partition": "development", "prompt_group_id": prompt, "item_id": item} for prompt, item in UNUSED_DEVELOPMENT_GROUPS]
    if len(all_development) != 7 or all_development[4:] != expected:
        raise ValueError("HANNA shrinkage unused development group map drifted")
    if {row["prompt_group_id"] for row in all_development[:4]} & {row["prompt_group_id"] for row in expected}:
        raise ValueError("HANNA shrinkage development groups overlap predecessor groups")
    return expected


def _edit_mass(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> float:
    instruction_change = 1.0 - SequenceMatcher(None, baseline["instruction_bytes"], candidate["instruction_bytes"], autojunk=False).ratio()
    try:
        baseline_profile = json.loads(baseline["profile_bytes"]); candidate_profile = json.loads(candidate["profile_bytes"])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("HANNA shrinkage candidate profile is invalid JSON") from error
    keys = set(baseline_profile) | set(candidate_profile)
    profile_changed_keys = sum(baseline_profile.get(key) != candidate_profile.get(key) for key in keys) / max(1, len(keys))
    return (instruction_change + profile_changed_keys) / 2.0


def _candidate_material(*, heldout: ModuleType, reconciliation_manifest_path: Path, admission_path: Path) -> list[dict[str, Any]]:
    v3 = heldout._v3(); baseline = heldout._baseline(v3)
    manifest = heldout._reconciliation_manifest(Path(reconciliation_manifest_path), baseline=baseline)
    admission, _raw = _canonical_file(Path(admission_path), label="declared-mechanism admission", expected_sha256=ADMISSION_FILE_SHA256)
    body = dict(admission); digest = body.pop("admission_sha256", None)
    expected_source = {"reconciliation_manifest_file_sha256": manifest["manifest_file_sha256"], "reconciliation_manifest_sha256": manifest["manifest_sha256"], "sample_count": 10, "study_id": manifest["study_id"]}
    expected_authority = {"declared_mechanism_count_per_candidate": 1, "process_launches": 0, "provider_calls_made": 0, "selection_authority": "none", "semantic_single_mechanism_verified": False}
    if digest != sha256(body) or admission.get("kind") != "declared_mechanism_admission_for_governed_reconciled_descendants" or admission.get("source") != expected_source or admission.get("authority") != expected_authority:
        raise ValueError("HANNA shrinkage declared-mechanism admission authority drifted")
    admitted = admission.get("candidates")
    if not isinstance(admitted, list) or len(admitted) != 10 or len({row.get("declared_mechanism") for row in admitted}) != 10:
        raise ValueError("HANNA shrinkage requires ten unique declared mechanisms")
    admission_index = {row.get("sample_id"): row for row in admitted}; descendants = []
    for source in manifest["samples"]:
        row = admission_index.get(source["sample_id"]); normalized = source["normalized_output"]
        if (not isinstance(row, Mapping) or set(row) != {"sample_id", "declared_mechanism", "normalized_descriptor_sha256", "instruction_sha256", "profile_sha256"}
                or row["normalized_descriptor_sha256"] != sha256(normalized)
                or row["instruction_sha256"] != source["lineage"]["descendant_instruction_sha256"]
                or row["profile_sha256"] != source["lineage"]["derived_descendant_profile_sha256"]):
            raise ValueError("HANNA shrinkage admission does not bind governed reconciled candidate")
        instruction = base64.b64decode(normalized["descendant_instruction_base64"], validate=True)
        profile = base64.b64decode(normalized["descendant_profile_base64"], validate=True)
        candidate_sha = sha256({"instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile)})
        descendants.append({"sample_id": source["sample_id"], "declared_mechanism": row["declared_mechanism"], "candidate_id": "candidate-" + candidate_sha[:16], "candidate_sha256": candidate_sha, "instruction_bytes": instruction, "profile_bytes": profile, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile)})
    return [{"sample_id": "fresh-baseline", "declared_mechanism": "baseline-none-declared", **baseline}, *descendants]


@dataclass(frozen=True)
class _ReplayInputs:
    reconciliation_manifest_path: Path
    admission_path: Path
    feedback_root: Path
    frozen_successor_path: Path
    hanna_csv_path: Path


@dataclass(frozen=True)
class ValidatedSchedule:
    value: Mapping[str, Any]
    _bytes: bytes
    _candidate_bytes: bytes
    _inputs: _ReplayInputs
    _token: object


def _schedule_value(inputs: _ReplayInputs) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    heldout = _heldout(); v3 = heldout._v3(); feedback = _feedback(inputs.feedback_root)
    _study, _harness, _freeze, split, _parents = v3._material(frozen_successor_path=inputs.frozen_successor_path, hanna_csv_path=inputs.hanna_csv_path)
    candidates = _candidate_material(heldout=heldout, reconciliation_manifest_path=inputs.reconciliation_manifest_path, admission_path=inputs.admission_path)
    groups = _groups(split); freeze = v3.v2_module().parent_modules()[2]
    sources = freeze._source_material(frozen_successor_path=inputs.frozen_successor_path, hanna_csv_path=inputs.hanna_csv_path); cells = []
    for group in groups:
        for candidate in candidates:
            payload = freeze._payload_bytes(item=sources[group["item_id"]], candidate=candidate)
            key = {"study_id": STUDY_ID, "route_name": "grok_primary", "item_id": group["item_id"], "candidate_id": candidate["candidate_id"]}
            cells.append({"ordinal": len(cells) + 1, "cell_id": "shrinkage-cell-" + sha256(key)[:16], "route_name": "grok_primary", **group, "sample_id": candidate["sample_id"], "declared_mechanism": candidate["declared_mechanism"], "semantic_single_mechanism_verified": False, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload)})
    candidate_rows = [{"sample_id": row["sample_id"], "declared_mechanism": row["declared_mechanism"], "semantic_single_mechanism_verified": False, "candidate_id": row["candidate_id"], "candidate_sha256": row["candidate_sha256"], "instruction_sha256": row["instruction_sha256"], "profile_sha256": row["profile_sha256"], "edit_mass": 0.0 if row["candidate_id"] == BASELINE_ID else _edit_mass(candidates[0], row)} for row in candidates]
    result = {"format_version": 2, "study_id": STUDY_ID, "kind": "replayed_governed_three_unused_development_group_grok_schedule", "heldout_study_sha256": HELDOUT_STUDY_SHA256, "feedback": feedback, "reconciliation_manifest_file_sha256": sha256(inputs.reconciliation_manifest_path.read_bytes()), "declared_mechanism_admission_file_sha256": sha256(inputs.admission_path.read_bytes()), "frozen_successor_file_sha256": sha256(inputs.frozen_successor_path.read_bytes()), "hanna_csv_file_sha256": sha256(inputs.hanna_csv_path.read_bytes()), "candidates": candidate_rows, "groups": groups, "cells": cells, "geometry": {"candidates": 11, "groups": 3, "grok_cells": 33, "sol_cells": 0}, "objective": {"formula": "0.5*mean(group_delta)+0.25*population_stdev(group_delta)+0.02*edit_mass", "baseline_j": 0.0, "optuna": "4.9.0 GridSampler development-only"}, "confirmation": {"status": "unopened", "cells": 0}, "provider_calls_made": 0, "process_launches": 0, "runtime_authority": "none", "claim": "NO-GO until independently replayed native evidence"}
    result["schedule_sha256"] = sha256(result)
    if len(cells) != 33 or len({row["cell_id"] for row in cells}) != 33:
        raise ValueError("HANNA shrinkage 33-cell Grok geometry drifted")
    return result, candidates


def prepare_grok_schedule(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path,
                          admission_path: Path = ADMISSION_PATH, feedback_root: Path = PUBLIC_RESULT_ROOT) -> ValidatedSchedule:
    inputs = _ReplayInputs(Path(reconciliation_manifest_path), Path(admission_path), Path(feedback_root), Path(frozen_successor_path), Path(hanna_csv_path))
    value, candidates = _schedule_value(inputs); raw = canonical(value)
    return ValidatedSchedule(value=json.loads(raw), _bytes=raw, _candidate_bytes=_candidate_projection(candidates), _inputs=inputs, _token=_SCHEDULE_TOKEN)


def _candidate_projection(candidates: list[dict[str, Any]]) -> bytes:
    material = [{key: row[key] for key in ("sample_id", "declared_mechanism", "candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256")} | {"instruction_base64": base64.b64encode(row["instruction_bytes"]).decode("ascii"), "profile_base64": base64.b64encode(row["profile_bytes"]).decode("ascii")} for row in candidates]
    return canonical(material)


def _validated_schedule(value: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(value, ValidatedSchedule) or value._token is not _SCHEDULE_TOKEN or canonical(dict(value.value)) != value._bytes:
        raise ValueError("HANNA shrinkage requires an immutable replay-validated schedule")
    replayed, candidates = _schedule_value(value._inputs)
    if canonical(replayed) != value._bytes or _candidate_projection(candidates) != value._candidate_bytes:
        raise ValueError("HANNA shrinkage full schedule/candidate/cell replay drifted")
    return replayed, candidates


def payload_bytes(cell: Mapping[str, Any]) -> bytes:
    try:
        raw = base64.b64decode(cell["payload_base64"].encode("ascii"), validate=True)
    except (KeyError, AttributeError, UnicodeEncodeError, ValueError) as error:
        raise ValueError("HANNA shrinkage payload is invalid") from error
    if sha256(raw) != cell.get("payload_sha256"):
        raise ValueError("HANNA shrinkage payload binding drifted")
    return raw
