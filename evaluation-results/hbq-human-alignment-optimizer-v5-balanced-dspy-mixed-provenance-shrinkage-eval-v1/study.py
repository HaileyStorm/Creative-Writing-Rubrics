"""Provider-free schedule for the exploratory mixed-provenance HANNA set."""
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
STUDY_ID = "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-shrinkage-eval-v1"
V4_HELDOUT = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1" / "study.py"
V4_HELDOUT_SHA256 = "770b8c496df3c86dbc6ae3c7673d462428f81bcbddf84e493ea7c6710bd1b346"
MATERIALIZER_COMMIT = "9447b33"
MATERIALIZER_SOURCE = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1" / "materialize.py"
MATERIALIZER_SOURCE_SHA256 = "aec112f15c7371191ecac70c3772063a40c842846fc52de6f6dc6c1dac9b0bd8"
MATERIALIZER_CONTRACT = HERE.parent / "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1" / "study-contract.json"
MATERIALIZER_CONTRACT_SHA256 = "0976e6925fbe1ae69b0817fc26747c28dbf94f013bfd585d6ae888cfc841fe97"
MATERIALIZATION_FILE_SHA256 = "9a6db38703b0e34b96e856a956436e4bba76c9770f899943d75ecc436aca1a84"
MIXED_COMPOSITION_FILE_SHA256 = "9fdc76472031719eff0b83042121f0f6f860eed5a0915f5159161d33939916a9"
MATERIALIZER_ID = "hbq-human-alignment-optimizer-v5-balanced-dspy-mixed-provenance-materializer-v1"
SOURCE_TENTH_ID = "candidate-625dac0d1e79f79c"
UNUSED_DEVELOPMENT_GROUPS = (("prompt-7c393c4bcb3a7484", "item-2377fcf24510aac5"), ("prompt-8997770ce6efe4d5", "item-0cb9c7afe8527434"), ("prompt-8d3d397a4f6ba0ea", "item-1b27b9076eef2bc5"))
_TOKEN = object()

def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()

def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()

def _json(path: Path, expected: str, label: str) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if sha256(raw) != expected: raise ValueError(f"mixed evaluator {label} hash drifted")
    try: value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"mixed evaluator {label} invalid JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw: raise ValueError(f"mixed evaluator {label} must be canonical")
    return value, raw

def _module() -> ModuleType:
    raw = V4_HELDOUT.read_bytes()
    if sha256(raw) != V4_HELDOUT_SHA256: raise ValueError("mixed evaluator held-out source drifted")
    spec = importlib.util.spec_from_file_location("_mixed_v4_heldout", V4_HELDOUT)
    if spec is None or spec.loader is None: raise ValueError("mixed evaluator cannot load pinned held-out source")
    module = importlib.util.module_from_spec(spec); exec(compile(raw, str(V4_HELDOUT), "exec"), module.__dict__)
    return module

def _b64(value: Any, label: str) -> bytes:
    if not isinstance(value, str): raise ValueError(f"mixed evaluator {label} missing base64")
    try: raw = base64.b64decode(value, validate=True)
    except ValueError as error: raise ValueError(f"mixed evaluator {label} bad base64") from error
    if base64.b64encode(raw).decode() != value: raise ValueError(f"mixed evaluator {label} noncanonical base64")
    return raw

def _local_identity(source_id: str, instruction: bytes, profile: bytes) -> tuple[str, str]:
    identity = {"study_id": STUDY_ID, "source_candidate_id": source_id, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile)}
    digest = sha256(identity)
    return "candidate-" + digest[:16], digest

def _material(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sha256(MATERIALIZER_SOURCE.read_bytes()) != MATERIALIZER_SOURCE_SHA256 or sha256(MATERIALIZER_CONTRACT.read_bytes()) != MATERIALIZER_CONTRACT_SHA256:
        raise ValueError("mixed evaluator pushed materializer source/contract drifted")
    manifest, _ = _json(root / "materialization.json", MATERIALIZATION_FILE_SHA256, "materialization")
    composition, raw = _json(root / "mixed-composition.json", MIXED_COMPOSITION_FILE_SHA256, "composition")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(path.name for path in root.iterdir()) != set(artifacts) | {"materialization.json"}:
        raise ValueError("mixed evaluator materialization artifact inventory drifted")
    if any(not isinstance(name, str) or not isinstance(digest, str) or sha256((root / name).read_bytes()) != digest for name, digest in artifacts.items()):
        raise ValueError("mixed evaluator materialization artifact bytes drifted")
    if (manifest.get("study_id") != MATERIALIZER_ID or manifest.get("kind") != "completed_provider_free_materialization"
            or manifest.get("candidate_id") != SOURCE_TENTH_ID or manifest.get("candidate_sha256") != "625dac0d1e79f79c544c4e6ec66af442499cae553e0179ea934906eee3533113"
            or manifest.get("provider_calls_made") != 0 or manifest.get("process_launches") != 0
            or artifacts.get("mixed-composition.json") != sha256(raw)):
        raise ValueError("mixed evaluator materialization manifest binding drifted")
    if composition.get("study_id") != MATERIALIZER_ID or composition.get("manifest_sha256") != sha256(canonical({key: value for key, value in composition.items() if key != "manifest_sha256"})):
        raise ValueError("mixed evaluator composition commitment drifted")
    authority = composition.get("authority")
    if authority != manifest.get("authority") or authority.get("evaluation") is not False or authority.get("selection") is not False or authority.get("promotion") is not False or authority.get("runtime") is not False:
        raise ValueError("mixed evaluator materialization authority drifted")
    rows = composition.get("candidates")
    if not isinstance(rows, list) or len(rows) != 10 or len({row.get("candidate_id") for row in rows if isinstance(row, dict)}) != 10:
        raise ValueError("mixed evaluator requires ten unique materialized candidates")
    candidates: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows):
        if not isinstance(row, dict): raise ValueError("mixed evaluator candidate shape drifted")
        source_id = row.get("candidate_id"); instruction = _b64(row.get("instruction_base64"), "candidate instruction"); profile = _b64(row.get("profile_base64"), "candidate profile")
        if not isinstance(source_id, str) or row.get("instruction_sha256") != sha256(instruction) or row.get("profile_sha256") != sha256(profile): raise ValueError("mixed evaluator candidate byte binding drifted")
        provenance = row.get("provenance")
        expected_kind = "EXPLORATORY_POST_HOC_MATERIALIZATION" if ordinal == 9 else "reconciled_v3_terminal_descendant_under_unknown_native_contact"
        if not isinstance(provenance, dict) or provenance.get("kind") != expected_kind: raise ValueError("mixed evaluator provenance kind drifted")
        if ordinal == 9:
            descriptor, _ = _json(root / "descendant.json", artifacts["descendant.json"], "descendant descriptor")
            if (source_id != SOURCE_TENTH_ID or instruction != (root / "descendant-instruction.bin").read_bytes() or profile != (root / "descendant-profile.json").read_bytes()
                    or descriptor.get("candidate_id") != source_id or descriptor.get("candidate_sha256") != row.get("candidate_sha256")
                    or provenance.get("source_provider_attempts") != 1 or provenance.get("reasoning_attested") is not False or provenance.get("native_contact_proven") is not False
                    or provenance.get("provider_output_unchanged") is not False or provenance.get("not_a_recovered_replacement_or_native_descendant") is not True):
                raise ValueError("mixed evaluator exploratory tenth provenance drifted")
        else:
            terminal = provenance.get("source_terminal")
            if not isinstance(terminal, dict) or terminal.get("kind") != "reconcile_required_after_process_launch" or terminal.get("native_contact_proven") is not False or terminal.get("native_endpoint_contact_cardinality") != "unknown": raise ValueError("mixed evaluator reconciled provenance drifted")
        candidate_id, candidate_sha = _local_identity(source_id, instruction, profile)
        candidates.append({"sample_id": row.get("sample_id"), "source_candidate_id": source_id, "candidate_id": candidate_id, "candidate_sha256": candidate_sha, "instruction_bytes": instruction, "profile_bytes": profile, "instruction_sha256": sha256(instruction), "profile_sha256": sha256(profile), "provenance_kind": expected_kind})
    return candidates, {"materialization_file_sha256": MATERIALIZATION_FILE_SHA256, "mixed_composition_file_sha256": MIXED_COMPOSITION_FILE_SHA256, "mixed_composition_sha256": composition["manifest_sha256"], "materializer_commit": MATERIALIZER_COMMIT}

def _edit_mass(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> float:
    instruction = 1.0 - SequenceMatcher(None, baseline["instruction_bytes"], candidate["instruction_bytes"], autojunk=False).ratio()
    try: left, right = json.loads(baseline["profile_bytes"]), json.loads(candidate["profile_bytes"])
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("mixed evaluator profile is invalid") from error
    keys = set(left) | set(right)
    return (instruction + sum(left.get(key) != right.get(key) for key in keys) / max(1, len(keys))) / 2

def _groups(split: Mapping[str, Any]) -> list[dict[str, str]]:
    grouped: dict[str, list[str]] = {}
    for row in split["items"]:
        if row["partition"] == "development": grouped.setdefault(row["prompt_group_id"], []).append(row["item_id"])
    all_groups = [{"partition": "development", "prompt_group_id": group, "item_id": min(items)} for group, items in sorted(grouped.items())]
    expected = [{"partition": "development", "prompt_group_id": prompt, "item_id": item} for prompt, item in UNUSED_DEVELOPMENT_GROUPS]
    if len(all_groups) != 7 or all_groups[4:] != expected: raise ValueError("mixed evaluator development groups drifted")
    return expected

@dataclass(frozen=True)
class ValidatedSchedule:
    value: Mapping[str, Any]; _bytes: bytes; _candidate_bytes: bytes; _inputs: tuple[Path, Path, Path]; _token: object

def _schedule(inputs: tuple[Path, Path, Path]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    material_root, frozen, csv = inputs; heldout = _module(); v3 = heldout._v3(); baseline_source = heldout._baseline(v3)
    baseline_id, baseline_sha = _local_identity(baseline_source["candidate_id"], baseline_source["instruction_bytes"], baseline_source["profile_bytes"])
    baseline = {**baseline_source, "source_candidate_id": baseline_source["candidate_id"], "candidate_id": baseline_id, "candidate_sha256": baseline_sha, "provenance_kind": "baseline"}
    descendants, pins = _material(material_root); candidates = [baseline, *descendants]
    _study, _harness, _freeze, split, _parents = v3._material(frozen_successor_path=frozen, hanna_csv_path=csv); groups = _groups(split); freeze = v3.v2_module().parent_modules()[2]; sources = freeze._source_material(frozen_successor_path=frozen, hanna_csv_path=csv)
    cells = []
    for group in groups:
        for candidate in candidates:
            payload = freeze._payload_bytes(item=sources[group["item_id"]], candidate=candidate); key = {"study_id": STUDY_ID, "route_name": "grok_primary", "item_id": group["item_id"], "candidate_id": candidate["candidate_id"]}
            cells.append({"ordinal": len(cells)+1, "cell_id": "mixed-shrinkage-cell-"+sha256(key)[:16], "route_name": "grok_primary", **group, "sample_id": candidate.get("sample_id", "fresh-baseline"), "source_candidate_id": candidate["source_candidate_id"], "provenance_kind": candidate["provenance_kind"], "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "payload_base64": base64.b64encode(payload).decode(), "payload_sha256": sha256(payload)})
    row_candidates = [{"sample_id": candidate.get("sample_id", "fresh-baseline")} | {key: candidate[key] for key in ("source_candidate_id", "candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "provenance_kind")} | {"edit_mass": 0.0 if candidate is baseline else _edit_mass(baseline, candidate)} for candidate in candidates]
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "exploratory_post_hoc_mixed_provenance_three_group_grok_schedule", "materialization": pins, "frozen_successor_file_sha256": sha256(frozen.read_bytes()), "hanna_csv_file_sha256": sha256(csv.read_bytes()), "candidates": row_candidates, "groups": groups, "cells": cells, "geometry": {"candidates": 11, "groups": 3, "grok_cells": 33, "sol_cells": 0}, "objective": {"formula": "0.5*mean(group_delta)+0.25*population_stdev(group_delta)+0.02*edit_mass", "baseline_j": 0.0, "optuna": "4.9.0 GridSampler development-only"}, "authority": {"provider_calls_made": 0, "process_launches": 0, "runtime_authority": "none", "confirmation": {"status": "unopened", "cells": 0}}, "claim": "EXPLORATORY_POST_HOC_DEVELOPMENT_ONLY; no general HANNA claim; NO-GO until independently replayed native evidence"}
    value["schedule_sha256"] = sha256(value)
    if len(cells) != 33 or len({row["cell_id"] for row in cells}) != 33: raise ValueError("mixed evaluator geometry drifted")
    return value, candidates

def prepare_grok_schedule(*, materialization_root: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> ValidatedSchedule:
    inputs = (Path(materialization_root), Path(frozen_successor_path), Path(hanna_csv_path)); value, candidates = _schedule(inputs); raw = canonical(value)
    projection = canonical([{key: row[key] for key in ("source_candidate_id", "candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "provenance_kind")} | {"instruction_base64": base64.b64encode(row["instruction_bytes"]).decode(), "profile_base64": base64.b64encode(row["profile_bytes"]).decode()} for row in candidates])
    return ValidatedSchedule(json.loads(raw), raw, projection, inputs, _TOKEN)

def _validated_schedule(value: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(value, ValidatedSchedule) or value._token is not _TOKEN or canonical(dict(value.value)) != value._bytes: raise ValueError("mixed evaluator requires a replay-validated schedule")
    replayed, candidates = _schedule(value._inputs)
    projection = canonical([{key: row[key] for key in ("source_candidate_id", "candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "provenance_kind")} | {"instruction_base64": base64.b64encode(row["instruction_bytes"]).decode(), "profile_base64": base64.b64encode(row["profile_bytes"]).decode()} for row in candidates])
    if canonical(replayed) != value._bytes or projection != value._candidate_bytes: raise ValueError("mixed evaluator full source/candidate/cell replay drifted")
    return replayed, candidates

def payload_bytes(cell: Mapping[str, Any]) -> bytes:
    raw = _b64(cell.get("payload_base64"), "payload")
    if sha256(raw) != cell.get("payload_sha256"): raise ValueError("mixed evaluator payload binding drifted")
    return raw
