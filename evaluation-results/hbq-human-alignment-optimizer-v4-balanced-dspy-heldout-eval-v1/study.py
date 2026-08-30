"""Provider-free reconstruction of the reconciled HANNA held-out schedule."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
STUDY_ID = "hbq-human-alignment-optimizer-v4-balanced-dspy-heldout-eval-v1"
V3_PATH = HERE.parent / "hbq-human-alignment-optimizer-v3" / "study.py"
V3_SHA256 = "8928b9af075486483f5d117daf34d10ed71b98407b897c8948181b66d1cb99c3"
RECONCILER_PATH = HERE.parent / "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v1" / "reconciler.py"
RECONCILER_CONTRACT_PATH = RECONCILER_PATH.with_name("study-contract.json")
RECONCILER_SHA256 = "52dc21570860c23a2380c18e072f3eb8c1eb6f6208fb88f10e522534b8e3b161"
RECONCILER_CONTRACT_SHA256 = "540d402683f5280e8e9c734756aa01e96e65964e077d724d38dfcb05db479b3d"
RECONCILIATION_MANIFEST_FILE_SHA256 = "26b91ea23f04b55909db775b75c1bf7ae2d4819d2acc8346244548296e229bf3"
RECONCILIATION_MANIFEST_SHA256 = "8184c85e3be49669b8d3c1c28702b531e7a7bc501297252e4c8b8f87fb08f2ac"
FROZEN_SUCCESSOR_SHA256 = "b0f6dd24415c388a3104f8c9304ce301193cf0a48631a86c4886bc8ce48468e7"
BASELINE_ID = "candidate-52d1be4bc34e0018"


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def adapter_canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _hex(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"HANNA held-out {label} must be lowercase SHA-256")
    return value


def _pinned(path: Path, digest: str, *, label: str) -> bytes:
    raw = Path(path).read_bytes()
    if sha256(raw) != digest: raise ValueError(f"HANNA held-out pinned {label} drifted")
    return raw


def _canonical(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    try: value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError(f"HANNA held-out {label} is invalid JSON") from error
    if not isinstance(value, dict) or canonical(value) != raw: raise ValueError(f"HANNA held-out {label} must be canonical JSON")
    return value, raw


def _v3() -> ModuleType:
    raw = _pinned(V3_PATH, V3_SHA256, label="v3 source")
    spec = importlib.util.spec_from_file_location("_hanna_heldout_v3", V3_PATH)
    if spec is None or spec.loader is None: raise ValueError("HANNA held-out cannot load pinned v3")
    module = importlib.util.module_from_spec(spec); exec(compile(raw, str(V3_PATH), "exec"), module.__dict__)
    return module


def _baseline(v3: ModuleType) -> dict[str, Any]:
    rows = [row for row in v3.candidate_pack() if row["candidate_id"] == BASELINE_ID]
    if len(rows) != 1: raise ValueError("HANNA held-out pinned baseline is absent")
    row = rows[0]
    if (sha256(row["instruction_bytes"]) != row["instruction_sha256"] or sha256(row["profile_bytes"]) != row["profile_sha256"]):
        raise ValueError("HANNA held-out pinned baseline descriptor drifted")
    return {key: row[key] for key in ("candidate_id", "candidate_sha256", "instruction_bytes", "profile_bytes", "instruction_sha256", "profile_sha256")}


def _reconciliation_manifest(path: Path, *, baseline: Mapping[str, Any]) -> dict[str, Any]:
    reconciler_raw = _pinned(RECONCILER_PATH, RECONCILER_SHA256, label="reconciler source")
    contract, contract_raw = _canonical(RECONCILER_CONTRACT_PATH, label="reconciler contract")
    if sha256(contract_raw) != RECONCILER_CONTRACT_SHA256:
        raise ValueError("HANNA held-out pinned reconciler contract drifted")
    if contract.get("study_id") != "hbq-human-alignment-optimizer-v4-balanced-dspy-grok-reconcile-v1":
        raise ValueError("HANNA held-out reconciler contract identity drifted")
    value, raw = _canonical(Path(path), label="reconciliation manifest")
    if sha256(raw) != RECONCILIATION_MANIFEST_FILE_SHA256:
        raise ValueError("HANNA held-out reconciliation manifest file hash drifted")
    required = {"format_version", "study_id", "kind", "source", "samples", "authority", "reconciliation_provider_calls_made", "reconciliation_process_launches", "manifest_sha256"}
    body = dict(value); digest = body.pop("manifest_sha256", None)
    if (set(value) != required or value.get("format_version") != 1 or value.get("study_id") != contract["study_id"]
            or value.get("kind") != "balanced_dspy_grok_v2_reconciled_all_ten_descendants" or digest != RECONCILIATION_MANIFEST_SHA256 or digest != sha256(canonical(body))
            or value.get("authority") != contract["authority"] or value.get("reconciliation_provider_calls_made") != 0 or value.get("reconciliation_process_launches") != 0):
        raise ValueError("HANNA held-out reconciliation manifest identity/counters drifted")
    source = value["source"]
    source_keys = {"study_id", "executor_sha256", "adapter_sha256", "source_root", "preparation_file_sha256", "shared_prompt_sha256", "shared_response_schema_sha256", "terminal_roots", "completed_native_identities", "source_process_launches"}
    if (not isinstance(source, Mapping) or set(source) != source_keys or source.get("study_id") != contract["source"]["study_id"]
            or source.get("executor_sha256") != contract["source"]["executor_sha256"] or source.get("adapter_sha256") != contract["source"]["adapter_sha256"]
            or source.get("preparation_file_sha256") != contract["source"]["preparation_file_sha256"] or source.get("terminal_roots") != 10
            or source.get("completed_native_identities") != 10 or source.get("source_process_launches") != 10 or not isinstance(source.get("source_root"), str) or not source["source_root"]):
        raise ValueError("HANNA held-out reconciliation source lineage/counters drifted")
    for key in ("executor_sha256", "adapter_sha256", "preparation_file_sha256", "shared_prompt_sha256", "shared_response_schema_sha256"): _hex(source[key], label=f"reconciliation source {key}")
    source_root = Path(source["source_root"])
    if not source_root.is_dir(): raise ValueError("HANNA held-out reconciliation source root is unavailable")
    replay = ModuleType("_hanna_heldout_reconciler"); replay.__file__ = str(RECONCILER_PATH); exec(compile(reconciler_raw, str(RECONCILER_PATH), "exec"), replay.__dict__)
    with tempfile.TemporaryDirectory(prefix="hanna-heldout-reconcile-replay-") as temporary:
        replay_target = Path(temporary) / "replayed"
        replayed = replay.reconcile_all(source_root=source_root, target_root=replay_target)
        replay_raw = (replay_target / "reconciliation-manifest.json").read_bytes()
    if canonical(replayed) != replay_raw or replay_raw != raw:
        raise ValueError("HANNA held-out reconciliation replay does not byte-match frozen manifest")
    rows = value["samples"]
    if not isinstance(rows, list) or len(rows) != 10: raise ValueError("HANNA held-out reconciliation requires exactly ten samples")
    normalized_hashes, request_ids, session_ids = set(), set(), set()
    expected_sample_keys = {"sample_id", "source_root", "source_inventory_sha256", "source_artifacts", "source_terminal_kind", "source_adapter_control_sha256", "source_control", "raw_output", "raw_output_sha256", "runtime", "normalized_output", "derivation", "lineage", "source_native_contact_proven", "source_native_endpoint_contact_cardinality", "reconciliation_provider_calls_made", "reconciliation_process_launches"}
    for ordinal, row in enumerate(rows, 1):
        if not isinstance(row, Mapping) or set(row) != expected_sample_keys or row.get("sample_id") != f"sample-{ordinal:02d}": raise ValueError("HANNA held-out reconciliation sample order drifted")
        if (row.get("source_terminal_kind") != "reconcile_required_after_process_launch" or row.get("source_native_contact_proven") is not True or row.get("source_native_endpoint_contact_cardinality") != "proven_exactly_one_from_completed_adapter_control" or row.get("reconciliation_provider_calls_made") != 0 or row.get("reconciliation_process_launches") != 0 or not isinstance(row.get("source_root"), str) or not row["source_root"]):
            raise ValueError("HANNA held-out terminal lineage must remain explicitly reconciled")
        for key in ("source_inventory_sha256", "source_adapter_control_sha256", "raw_output_sha256"): _hex(row[key], label=f"reconciliation {key}")
        if not isinstance(row["source_artifacts"], Mapping) or not row["source_artifacts"]: raise ValueError("HANNA held-out source artifact bindings are absent")
        for value_hash in row["source_artifacts"].values(): _hex(value_hash, label="reconciliation source artifact")
        output, normalized, derivation, lineage, runtime = row["raw_output"], row["normalized_output"], row["derivation"], row["lineage"], row["runtime"]
        if (not isinstance(output, Mapping) or set(output) != {"descendant_instruction_base64", "descendant_profile_base64"} or sha256(adapter_canonical(dict(output))) != row["raw_output_sha256"]
                or not isinstance(normalized, Mapping) or set(normalized) != set(output) or not isinstance(derivation, Mapping) or not isinstance(lineage, Mapping)
                or lineage.get("parent_candidate_id") != baseline["candidate_id"] or lineage.get("parent_instruction_sha256") != baseline["instruction_sha256"] or lineage.get("parent_profile_sha256") != baseline["profile_sha256"]):
            raise ValueError("HANNA held-out reconciliation descriptor/parent binding drifted")
        try:
            instruction = base64.b64decode(normalized["descendant_instruction_base64"].encode("ascii"), validate=True)
            profile = base64.b64decode(normalized["descendant_profile_base64"].encode("ascii"), validate=True)
            profile_value = json.loads(profile.decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error: raise ValueError("HANNA held-out normalized descriptor is invalid") from error
        if (not instruction or not isinstance(profile_value, dict) or canonical(profile_value) != profile or profile_value.get("instruction_sha256") != sha256(instruction)
                or lineage.get("descendant_instruction_sha256") != sha256(instruction) or lineage.get("derived_descendant_profile_sha256") != sha256(profile)
                or derivation.get("derived_profile_sha256") != sha256(profile) or derivation.get("derived_profile_base64") != normalized["descendant_profile_base64"]):
            raise ValueError("HANNA held-out derived profile instruction binding drifted")
        if not isinstance(runtime, Mapping) or not isinstance(runtime.get("request_id_hash"), str) or not isinstance(runtime.get("session_id_hash"), str): raise ValueError("HANNA held-out reconciliation runtime identity is absent")
        _hex(runtime["request_id_hash"], label="reconciliation request identity"); _hex(runtime["session_id_hash"], label="reconciliation session identity")
        normalized_hashes.add(sha256(canonical(dict(normalized)))); request_ids.add(runtime["request_id_hash"]); session_ids.add(runtime["session_id_hash"])
    if {len(normalized_hashes), len(request_ids), len(session_ids)} != {10}: raise ValueError("HANNA held-out reconciliation has duplicate descriptor/contact identity")
    return {**value, "manifest_file_sha256": sha256(raw)}


def _groups(split: Mapping[str, Any]) -> list[dict[str, str]]:
    grouped: dict[str, list[str]] = {}
    for row in split["items"]:
        if row["partition"] == "development": grouped.setdefault(row["prompt_group_id"], []).append(row["item_id"])
    result = [{"prompt_group_id": key, "item_id": min(items)} for key, items in sorted(grouped.items())]
    if len(result) != 7: raise ValueError("HANNA held-out frozen development partition drifted")
    return result[:4]


def build_schedule(*, reconciliation_manifest_path: Path, frozen_successor_path: Path, hanna_csv_path: Path) -> dict[str, Any]:
    if sha256(Path(frozen_successor_path).read_bytes()) != FROZEN_SUCCESSOR_SHA256: raise ValueError("HANNA held-out frozen successor contract drifted")
    v3 = _v3(); baseline = _baseline(v3); manifest = _reconciliation_manifest(Path(reconciliation_manifest_path), baseline=baseline)
    _study, _harness, _freeze, split, _parents = v3._material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path))
    descendants = []
    for row in manifest["samples"]:
        normalized = row["normalized_output"]; instruction = base64.b64decode(normalized["descendant_instruction_base64"]); profile = base64.b64decode(normalized["descendant_profile_base64"])
        instruction_sha, profile_sha = sha256(instruction), sha256(profile); candidate_sha = sha256({"instruction_sha256": instruction_sha, "profile_sha256": profile_sha})
        descendants.append({"sample_id": row["sample_id"], "candidate_id": "candidate-" + candidate_sha[:16], "candidate_sha256": candidate_sha, "instruction_bytes": instruction, "profile_bytes": profile, "instruction_sha256": instruction_sha, "profile_sha256": profile_sha})
    candidates = [{"sample_id": "fresh-baseline", **baseline}, *descendants]; groups = _groups(split); freeze = v3.v2_module().parent_modules()[2]; sources = freeze._source_material(frozen_successor_path=Path(frozen_successor_path), hanna_csv_path=Path(hanna_csv_path)); cells = []
    for route_name, group_count in (("grok_primary", 4), ("sol_validation", 2)):
        for group in groups[:group_count]:
            for candidate in candidates:
                payload = freeze._payload_bytes(item=sources[group["item_id"]], candidate=candidate); key = {"study_id": STUDY_ID, "route_name": route_name, "item_id": group["item_id"], "candidate_id": candidate["candidate_id"]}
                cells.append({"ordinal": len(cells) + 1, "cell_id": "heldout-cell-" + sha256(key)[:16], "route_name": route_name, **group, "sample_id": candidate["sample_id"], "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload)})
    if len(cells) != 66 or len({row["cell_id"] for row in cells}) != 66: raise ValueError("HANNA held-out exact 66-cell schedule drifted")
    for group in groups[:2]:
        for candidate in candidates:
            pair = [row for row in cells if row["item_id"] == group["item_id"] and row["candidate_id"] == candidate["candidate_id"]]
            if len(pair) != 2 or pair[0]["payload_base64"] != pair[1]["payload_base64"]: raise ValueError("HANNA held-out cross-model payload bytes drifted")
    reconciliation = {"study_id": manifest["study_id"], "source_sha256": RECONCILER_SHA256, "contract_sha256": RECONCILER_CONTRACT_SHA256, "manifest_file_sha256": manifest["manifest_file_sha256"], "manifest_sha256": manifest["manifest_sha256"], "source_terminal_roots": manifest["source"]["terminal_roots"], "source_completed_native_identities": manifest["source"]["completed_native_identities"], "source_process_launches": manifest["source"]["source_process_launches"], "reconciliation_provider_calls_made": manifest["reconciliation_provider_calls_made"], "reconciliation_process_launches": manifest["reconciliation_process_launches"]}
    result = {"format_version": 3, "study_id": STUDY_ID, "kind": "frozen_provider_free_reconciled_paired_descendant_heldout_schedule", "frozen_successor_sha256": FROZEN_SUCCESSOR_SHA256, "v3_source_sha256": V3_SHA256, "reconciliation": reconciliation, "baseline": {key: baseline[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256")}, "candidate_order": [{key: row[key] for key in ("sample_id", "candidate_id", "candidate_sha256")} for row in candidates], "groups": groups, "sol_sprinkled_group_count": 2, "cells": cells, "geometry": {"candidates": 11, "grok_cells": 44, "sol_cells": 22, "total_cells": 66}, "missing_terminal_policy": "missing_or_terminal_blocks_candidate_route_no_replacement_or_resend", "tie_break": ["grok_mean_absolute_error:ascending", "candidate_id:lexicographic"], "confirmation": {"status": "unopened", "cells": 0}}
    result["schedule_sha256"] = sha256({key: result[key] for key in ("reconciliation", "baseline", "candidate_order", "groups", "sol_sprinkled_group_count", "cells", "geometry", "missing_terminal_policy", "tie_break", "confirmation")})
    return result


def payload_bytes(cell: Mapping[str, Any]) -> bytes:
    try: raw = base64.b64decode(cell["payload_base64"].encode("ascii"), validate=True)
    except (AttributeError, UnicodeEncodeError, ValueError) as error: raise ValueError("HANNA held-out payload is invalid") from error
    if sha256(raw) != cell.get("payload_sha256"): raise ValueError("HANNA held-out payload binding drifted")
    return raw
