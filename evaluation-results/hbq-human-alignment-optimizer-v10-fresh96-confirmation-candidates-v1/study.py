"""Freeze the Fresh96 future-confirmation panel before private identities open."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v10-fresh96-confirmation-candidates-v1"
FRESH96 = HERE.parent / "hbq-human-alignment-hanna96-fresh-split-v1" / "study.py"
FRESH96_SHA256 = "3573e33847b7ce3d1bb98b54d89af1c381c69f29438b9d8289e8f84de67475c2"
MANIFEST = HERE.parent / "hbq-human-alignment-hanna96-fresh-split-v1" / "manifest.json"
MANIFEST_SHA256 = "ca5adea2288d9c01ddf3aeb0c6239ac2c550d26095a2c66a928d90511f4afb16"
PRIVATE_FREEZE_SHA256 = "442c564da1933b5e5b444046748db88dfce6725b23a87bba099e524167102410"
VALIDATION = HERE.parent / "hbq-human-alignment-hanna96-validation-freeze-v1" / "study.py"
VALIDATION_SHA256 = "d8b99c651cfbc0c04207101a6ad15373168a5ffad3711f7d17fb589e8a13542e"
V9 = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-candidates-v1" / "study.py"
V9_SHA256 = "99387d9626ae13f20ef58f0a7f6624ebe850d8477ba17934c4f35735ca9eda16"
V9_SOL_VETO = HERE.parent / "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-result-v1" / "result.json"
V9_SOL_VETO_SHA256 = "f74cd54bbe88bd549a86e42ed46dcca4a68252ea168c4cf116225c0a69e06a0f"
BASELINE = "candidate-102cc7f06c9a99a7"
BASELINE_CANDIDATE_SHA256 = "d82391798ef8a661f2a3d15f37377e09a33d0d632f6fd1c05412e9bd0ea0f61c"
BASELINE_INSTRUCTION_SHA256 = "f318da394124d72dea4e9fb896d0345c6c5136d4839feae2cff1e389ea642de1"
BASELINE_PROFILE_SHA256 = "3d90b5bdd1b1cd1673cc45b834485754eb0ee01f89e2c3c7ddf5d31e7d24c74f"
CHILD = "broader-nextwave-20-missing_evidence_not_no-referent-evidence"
CHILD_CANDIDATE_SHA256 = "572d5e6b96251eacf19951a10574aaefb811beb9d7890e9f702b524d3c5465bb"
CHILD_INSTRUCTION_SHA256 = "e172abcab5284fe415d82cff30e1851f08c6ba8d4baccc764eeccf788a6e036d"
CHILD_PROFILE_SHA256 = "07cd3652f4792aef082a0e2d9d615229013663b14599abd011637daf8f185a20"
DIMENSIONS = ("Relevance", "Coherence", "Empathy", "Surprise", "Engagement", "Complexity")


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("reparsed filesystem artifact")
    if stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected filesystem artifact type")


def _safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=current != absolute or current.is_dir())
    return absolute


def stable(path: Path) -> bytes:
    path = _safe(Path(path)); _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened, raw, after = os.fstat(handle.fileno()), handle.read(), os.fstat(handle.fileno())
    identity = lambda value: (value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode), value.st_size)
    if identity(before) != identity(opened) or identity(opened) != identity(after):
        raise ValueError("stable read drift")
    return raw


def strict(raw: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate key in {label}")
            value[key] = item
        return value
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid {label}") from error
    if not isinstance(value, dict) or canonical(value) != raw:
        raise ValueError(f"noncanonical {label}")
    return value


def _module(path: Path, expected_sha256: str, name: str):
    if sha256(stable(path)) != expected_sha256:
        raise ValueError(f"{name} bytes drifted")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"{name} cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract() -> dict[str, Any]:
    value = strict(stable(HERE / "study-contract.json"), "study contract")
    expected = {
        "analysis_rule": {"aggregation": "mean_of_16_prompt_group_maes", "comparison": "child20_minus_baseline", "direction": "negative_favors_child20", "endpoints": {"grok_primary": {"complete_cells": 64, "endpoint_pooling": "forbidden"}, "sol_later": {"complete_cells": 64, "endpoint_pooling": "forbidden"}}, "missing_or_ambiguous_cell": "terminal_reconcile_only_no_projection_without_all_64_cells", "pairing": "same_item_each_candidate_exact_payload_unchanged_across_endpoints", "selection": "forbidden", "target_use": "local_projection_only"},
        "authority": {"confirmation": "opened_by_this_frozen_schedule", "dspy_optuna_runtime": "forbidden", "promotion": "none", "runtime": "none", "selection": "none", "sol": "not_implemented"},
        "format_version": 1,
        "geometry": {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0},
        "kind": "frozen_fresh96_future_confirmation_candidate_panel",
        "panel": {"baseline_candidate_id": BASELINE, "child_candidate_id": CHILD},
        "prohibitions": ["no provider calls or process launches during freeze", "no targets outbound", "no candidate or analysis-rule changes after private-root admission", "no endpoint pooling", "no runtime DSPy or Optuna dependency"],
        "study_id": STUDY_ID,
    }
    if value != expected:
        raise ValueError("study contract drifted")
    return value


def _inputs(private_root: Path, hanna_csv_path: Path) -> tuple[Any, Any, dict[str, Any], list[dict[str, Any]]]:
    contract()
    fresh = _module(FRESH96, FRESH96_SHA256, "_v10_fresh96")
    manifest = strict(stable(MANIFEST), "Fresh96 manifest")
    if sha256(canonical(manifest)) != MANIFEST_SHA256 or manifest.get("commitments", {}).get("private_freeze_sha256") != PRIVATE_FREEZE_SHA256:
        raise ValueError("Fresh96 private-freeze commitment drifted")
    rows = fresh.read_source(Path(hanna_csv_path))
    private, private_sha = fresh._private_freeze(Path(private_root) / fresh.PRIVATE_FILENAME, rows)
    if private_sha != PRIVATE_FREEZE_SHA256:
        raise ValueError("private freeze commitment drifted")
    items = [dict(row) for row in private.get("selected_items", []) if row.get("partition") == "future_confirmation"]
    groups = [row for row in private.get("groups", []) if row.get("partition") == "future_confirmation"]
    if len(items) != 32 or len(groups) != 16 or len({row.get("item_id") for row in items}) != 32 or len({row.get("prompt_group_id") for row in items}) != 16:
        raise ValueError("future-confirmation geometry drifted")
    validation = _module(VALIDATION, VALIDATION_SHA256, "_v10_validation_payload")
    return fresh, validation, manifest, sorted(items, key=lambda row: (str(row["prompt_group_id"]), str(row["item_id"])))


def _panel(validation: Any) -> list[dict[str, Any]]:
    instruction, profile_raw, baseline = validation._baseline()
    if baseline != {"candidate_id": BASELINE, "instruction_sha256": BASELINE_INSTRUCTION_SHA256, "profile_sha256": BASELINE_PROFILE_SHA256, "candidate_sha256": BASELINE_CANDIDATE_SHA256}:
        raise ValueError("baseline panel binding drifted")
    v9 = _module(V9, V9_SHA256, "_v10_child20")
    source, schedule = v9._source_schedule()
    child = next(row for row in v9._candidates(source, schedule) if row["candidate_id"] == CHILD)
    if (child.get("candidate_sha256"), child.get("instruction_sha256"), child.get("profile_sha256")) != (CHILD_CANDIDATE_SHA256, CHILD_INSTRUCTION_SHA256, CHILD_PROFILE_SHA256):
        raise ValueError("child20 panel binding drifted")
    return [
        {"candidate_id": BASELINE, "candidate_sha256": BASELINE_CANDIDATE_SHA256, "instruction": instruction, "instruction_sha256": BASELINE_INSTRUCTION_SHA256, "profile_raw": profile_raw, "profile_sha256": BASELINE_PROFILE_SHA256, "kind": "immutable_baseline"},
        {"candidate_id": CHILD, "candidate_sha256": CHILD_CANDIDATE_SHA256, "instruction": base64.b64decode(child["instruction_base64"], validate=True), "instruction_sha256": CHILD_INSTRUCTION_SHA256, "profile_raw": base64.b64decode(child["profile_base64"], validate=True), "profile_sha256": CHILD_PROFILE_SHA256, "kind": "retained_child20"},
    ]


def _qualification() -> dict[str, Any]:
    value = strict(stable(V9_SOL_VETO), "pinned V9 Grok qualification and Sol veto")
    sol = value.get("sol_validation")
    if (sha256(canonical(value)) != V9_SOL_VETO_SHA256
            or value.get("study_id") != "hbq-human-alignment-optimizer-v9-desc18-broad-replication-sol-veto-result-v1"
            or value.get("authority", {}).get("selection") != "grok_qualification_then_sol_veto_only"
            or not isinstance(sol, Mapping) or sol.get("retained_candidate_id") != CHILD
            or sol.get("survivors") != [CHILD] or sol.get("vetoed") != []
            or value.get("source", {}).get("grok_optimizer_result_file_sha256") != "da6f567763f4b4f0bece074a47bcf34a247e2c337dbaaee09f3ee9f69cd5aaa9"):
        raise ValueError("pinned V9 Grok qualification or Sol veto drifted")
    return {"result_sha256": V9_SOL_VETO_SHA256, "study_id": value["study_id"], "selection": "grok_qualification_then_sol_veto_only", "retained_candidate_id": CHILD}


def _payload(validation: Any, item: Mapping[str, Any], candidate: Mapping[str, Any]) -> bytes:
    value = {"format_version": 1, "study_id": validation.STUDY_ID, "instruction": candidate["instruction"].decode("utf-8"), "profile": json.loads(candidate["profile_raw"]), "writing": {"prompt": item["prompt"], "story": item["story"]}, "response_schema": validation._schema()}
    if "target" in value or "target" in value["writing"]:
        raise ValueError("target leakage into outbound payload")
    return validation.canonical(value)


def materialize(*, private_root: Path, hanna_csv_path: Path) -> dict[str, Any]:
    qualification = _qualification()
    fresh, validation, _manifest, items = _inputs(Path(private_root), Path(hanna_csv_path))
    panel = _panel(validation)
    candidates = [{key: candidate[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "kind")} for candidate in panel]
    cells: list[dict[str, Any]] = []
    for item in items:
        target = {dimension: float(item["target"][dimension]) for dimension in DIMENSIONS}
        for candidate in panel:
            payload = _payload(validation, item, candidate)
            cell_id = "v10-future-" + sha256({"candidate": candidate["candidate_id"], "item": item["item_id"]})[:20]
            cells.append({"cell_id": cell_id, "ordinal": len(cells) + 1, "candidate_id": candidate["candidate_id"], "candidate_sha256": candidate["candidate_sha256"], "candidate_instruction_sha256": candidate["instruction_sha256"], "candidate_profile_sha256": candidate["profile_sha256"], "partition": "future_confirmation", "prompt_group_id": item["prompt_group_id"], "item_id": item["item_id"], "source_binding_sha256": item["source_binding_sha256"], "target": target, "target_sha256": sha256(target), "payload_base64": base64.b64encode(payload).decode("ascii"), "payload_sha256": sha256(payload), "endpoint_payload_sha256s": {"grok_primary": sha256(payload), "sol_later": sha256(payload)}})
    value = {"format_version": 1, "study_id": STUDY_ID, "kind": "frozen_fresh96_future_confirmation_candidate_panel", "private_source": {"fresh96_manifest_sha256": MANIFEST_SHA256, "private_freeze_sha256": PRIVATE_FREEZE_SHA256, "hanna_csv_sha256": fresh.CONTRACT["dataset"]["csv_sha256"]}, "qualification": qualification, "analysis_rule": contract()["analysis_rule"], "candidates": candidates, "cells": cells, "geometry": {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}, "authority": contract()["authority"]}
    value["schedule_sha256"] = sha256(value)
    validate(value)
    return value


def validate(value: Mapping[str, Any]) -> None:
    body = dict(value); declared = body.pop("schedule_sha256", None)
    if declared != sha256(body) or value.get("study_id") != STUDY_ID or value.get("analysis_rule") != contract()["analysis_rule"]:
        raise ValueError("schedule commitment or analysis rule drifted")
    if value.get("geometry") != {"candidates": 2, "future_confirmation_groups": 16, "future_confirmation_items": 32, "grok_cells": 64, "sol_cells": 0}:
        raise ValueError("future-confirmation geometry drifted")
    expected_candidates = [
        {"candidate_id": BASELINE, "candidate_sha256": BASELINE_CANDIDATE_SHA256, "instruction_sha256": BASELINE_INSTRUCTION_SHA256, "profile_sha256": BASELINE_PROFILE_SHA256, "kind": "immutable_baseline"},
        {"candidate_id": CHILD, "candidate_sha256": CHILD_CANDIDATE_SHA256, "instruction_sha256": CHILD_INSTRUCTION_SHA256, "profile_sha256": CHILD_PROFILE_SHA256, "kind": "retained_child20"},
    ]
    if value.get("candidates") != expected_candidates or value.get("qualification") != _qualification() or value.get("private_source") != {"fresh96_manifest_sha256": MANIFEST_SHA256, "private_freeze_sha256": PRIVATE_FREEZE_SHA256, "hanna_csv_sha256": "ef59054d27fa32def06cfdc57243b1dd09c7e71f40b6d9d43fecfbf60e59026b"}:
        raise ValueError("panel or private-source binding drifted")
    cells = value.get("cells")
    if not isinstance(cells, list) or len(cells) != 64 or len({row.get("cell_id") for row in cells if isinstance(row, Mapping)}) != 64:
        raise ValueError("cell inventory drifted")
    if {row.get("candidate_id") for row in cells} != {BASELINE, CHILD} or len({row.get("item_id") for row in cells}) != 32 or len({row.get("prompt_group_id") for row in cells}) != 16 or {row.get("partition") for row in cells} != {"future_confirmation"}:
        raise ValueError("candidate or private partition drifted")
    for row in cells:
        payload = base64.b64decode(row.get("payload_base64", ""), validate=True)
        decoded = strict(payload, "outbound payload")
        expected = next((candidate for candidate in expected_candidates if candidate["candidate_id"] == row.get("candidate_id")), None)
        expected_hashes = None if expected is None else (expected["candidate_sha256"], expected["instruction_sha256"], expected["profile_sha256"])
        if expected_hashes is None or tuple(row.get(key) for key in ("candidate_sha256", "candidate_instruction_sha256", "candidate_profile_sha256")) != expected_hashes:
            raise ValueError("cell candidate binding drifted")
        instruction, profile = decoded.get("instruction"), decoded.get("profile")
        profile_raw = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") if isinstance(profile, Mapping) else b""
        if not isinstance(instruction, str) or sha256(instruction.encode("utf-8")) != row["candidate_instruction_sha256"] or sha256(profile_raw) != row["candidate_profile_sha256"]:
            raise ValueError("payload candidate bytes drifted")
        if sha256(payload) != row.get("payload_sha256") or row.get("endpoint_payload_sha256s") != {"grok_primary": sha256(payload), "sol_later": sha256(payload)} or set(decoded) != {"format_version", "study_id", "instruction", "profile", "writing", "response_schema"} or "target" in json.dumps(decoded, sort_keys=True).casefold():
            raise ValueError("outbound payload drifted or leaked target")
        if not isinstance(row.get("target"), Mapping) or sha256(row["target"]) != row.get("target_sha256"):
            raise ValueError("local target binding drifted")


def _write_new(path: Path, raw: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("refuses overwrite")
    with path.open("xb") as handle:
        handle.write(raw); handle.flush(); os.fsync(handle.fileno())


def freeze(*, output_root: Path, private_root: Path, hanna_csv_path: Path) -> dict[str, Any]:
    root, private, csv = _safe(Path(output_root)), _safe(Path(private_root)), _safe(Path(hanna_csv_path))
    if root.exists() or REPO == root or REPO in root.parents or private == root or private in root.parents or root in private.parents or csv in root.parents:
        raise ValueError("freeze output root must be fresh and external")
    schedule = materialize(private_root=private, hanna_csv_path=csv)
    root.mkdir(parents=True)
    _plain(root, directory=True)
    _write_new(root / "schedule.json", canonical(schedule))
    _write_new(root / "manifest.json", canonical({"study_id": STUDY_ID, "schedule_sha256": schedule["schedule_sha256"], "candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]], "analysis_rule_sha256": sha256(schedule["analysis_rule"])}))
    return validate_frozen_root(root)


def validate_frozen_root(root: Path) -> dict[str, Any]:
    root = _safe(Path(root)); _plain(root, directory=True)
    if {path.name for path in root.iterdir()} != {"manifest.json", "schedule.json"}:
        raise ValueError("frozen root inventory drifted")
    schedule = strict(stable(root / "schedule.json"), "persisted schedule"); validate(schedule)
    manifest = strict(stable(root / "manifest.json"), "persisted manifest")
    expected = {"study_id": STUDY_ID, "schedule_sha256": schedule["schedule_sha256"], "candidate_sha256s": [row["candidate_sha256"] for row in schedule["candidates"]], "analysis_rule_sha256": sha256(schedule["analysis_rule"])}
    if manifest != expected:
        raise ValueError("frozen manifest drifted")
    return schedule


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output-root", type=Path); parser.add_argument("--private-root", type=Path); parser.add_argument("--hanna-csv", type=Path)
    args = parser.parse_args()
    if args.output_root:
        if not args.private_root or not args.hanna_csv:
            parser.error("freeze requires private root and HANNA CSV")
        value = freeze(output_root=args.output_root, private_root=args.private_root, hanna_csv_path=args.hanna_csv)
    else:
        parser.error("materialization is intentionally unavailable without an explicit external freeze root")
    print(canonical(value).decode("utf-8"), end="")
