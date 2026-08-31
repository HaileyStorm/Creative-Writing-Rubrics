#!/usr/bin/env python3
"""Bounded Grok execution for the frozen descendant-13 lower-step study."""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import importlib.util
import json
import os
import stat
import sys
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STUDY_ID = "hbq-human-alignment-optimizer-v6-desc13-lower-step-grok-exec-v1"
SOURCE_COMMIT = "02bdbf5c1adc4fa44a0b39b46e5bb9895f4d95d4"
CANDIDATES = HERE.parent / "hbq-human-alignment-optimizer-v6-desc13-lower-step-candidates-v1"
BROADER_FREEZE = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-broader-development-freeze-v1"
V3 = HERE.parent / "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load"
CANDIDATE_HASHES = {
    CANDIDATES / "study.py": "511066c8b8723b1df04a07eae4eb0daa7fb375169ba2a23c442fc848b2ef8dae",
    CANDIDATES / "study-contract.json": "74aa271918c4e9d15cd48f797f4b94814f7cf41344ace7a2c65a56a9fa06acfa",
    CANDIDATES / "README.md": "a62ffb01d9ac453470a886270251689d6d472080b4cce58090227e8add95bc67",
}
BROADER_HASHES = {
    BROADER_FREEZE / "study.py": "507e3c0bec1af6d0acef6e806cf6874a2633e892c9bbf567728f436af30f84bf",
    BROADER_FREEZE / "study-contract.json": "3b31c9b0d5ec4c71d6b562045dcd52b2646380cb318d72b83d2119e760543a77",
    BROADER_FREEZE / "README.md": "5f8956e96df28ddfe37533e631c163f1cdbf711e820e05e2607618975bf0e75f",
}
V3_HASHES = {
    V3 / "executor.py": "24d38e0de28d20bcb1f87bb4af5737d4dc2a588bdf79e04e7c1a52f5de3ec3da",
    V3 / "study-contract.json": "d85610ccf354dc8d5aa639cbc0a5ece89bcf0720495445cd252c651dd59590c5",
    V3 / "README.md": "49846137b273758c20bb57109dfbb09dc76aa2c2fd7442f471f85430a583a7a6",
}
PARENT_CANDIDATE_ID = "broader-nextwave-13-missing_evidence_not_no"
PARENT_CANDIDATE_SHA256 = "d8e55620d3a91ac17762d9ac40f7be3bb8aa87a478d6593f6ebda906d28b4684"
PARENT_DOCUMENT_SHA256 = "0b9b7b7417c37534689ef3c159e7de1d7cc7a6eb0fb593e4f671a5e2686e9f28"
CANDIDATE_MANIFEST_SHA256 = "0487398345b28388fb6e35d879e5ea6f771f65802488e3fc33cf0426b530cecd"
MAX_CONCURRENCY = 10


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def sha256(value: bytes | Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _plain(path: Path, *, directory: bool | None = None) -> None:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("unsafe/reparsed path")
    if directory is not None and stat.S_ISDIR(info.st_mode) != directory:
        raise ValueError("unexpected path type")


def _safe(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.exists():
            _plain(current, directory=True if current != absolute else None)
    return absolute


def _full_identity(path: Path, *, directory: bool) -> tuple[tuple[str, int, int, int, int | None], ...]:
    absolute = _safe(path)
    values: list[tuple[str, int, int, int, int | None]] = []
    for index, current in enumerate((absolute, *absolute.parents)):
        info = os.lstat(current)
        expected_directory = directory if index == 0 else True
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise ValueError("unsafe/reparsed prepared artifact ancestry")
        if stat.S_ISDIR(info.st_mode) != expected_directory:
            raise ValueError("prepared artifact type drifted")
        values.append((str(current), info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), None if expected_directory else info.st_size))
    return tuple(values)


def stable(path: Path) -> bytes:
    path = _safe(Path(path))
    _plain(path, directory=False)
    before = os.lstat(path)
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    identity = (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode), before.st_size)
    if identity != (opened.st_dev, opened.st_ino, stat.S_IFMT(opened.st_mode), opened.st_size) or identity != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode), after.st_size):
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


def _blob(relative: Path) -> bytes:
    import subprocess
    result = subprocess.run(["git", "-C", str(REPO), "show", f"{SOURCE_COMMIT}:{relative.as_posix()}"], capture_output=True, check=False)
    if result.returncode:
        raise ValueError("pinned source Git blob is absent")
    return result.stdout


def _load_pinned(path: Path, hashes: Mapping[Path, str], name: str) -> ModuleType:
    for candidate, digest in hashes.items():
        raw = stable(candidate)
        if sha256(raw) != digest or _blob(candidate.relative_to(REPO)) != raw:
            raise ValueError("pinned execution dependency drifted")
    raw = stable(path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load pinned execution dependency")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    if stable(path) != raw:
        raise ValueError("pinned execution dependency changed during load")
    return module


def candidate_study() -> ModuleType:
    return _load_pinned(CANDIDATES / "study.py", CANDIDATE_HASHES, "_desc13_lower_step_candidates")


def broader_study() -> ModuleType:
    return _load_pinned(BROADER_FREEZE / "study.py", BROADER_HASHES, "_desc13_lower_step_broader")


def v3_runtime() -> ModuleType:
    module = _load_pinned(V3 / "executor.py", V3_HASHES, "_desc13_lower_step_grok_v3")
    return module


def contract() -> dict[str, Any]:
    return strict(stable(HERE / "study-contract.json"), "study contract")


def _expected_contract() -> dict[str, Any]:
    return {
        "authority": {"confirmation": {"cells": 0, "status": "unopened"}, "promotion": "none", "runtime": "none", "selection": "none", "sol": "out_of_scope"},
        "format_version": 1,
        "geometry": {"candidates": 5, "confirmation_cells": 0, "development_groups": 7, "grok_cells": 35, "sol_cells": 0},
        "kind": "descendant13_lower_step_grok_development_execution",
        "pinned_candidate_freeze": {
            "commit": SOURCE_COMMIT,
            "manifest_sha256": CANDIDATE_MANIFEST_SHA256,
            "readme_sha256": CANDIDATE_HASHES[CANDIDATES / "README.md"],
            "study_contract_sha256": CANDIDATE_HASHES[CANDIDATES / "study-contract.json"],
            "study_sha256": CANDIDATE_HASHES[CANDIDATES / "study.py"],
        },
        "pinned_route_stack": {
            "executor_sha256": V3_HASHES[V3 / "executor.py"],
            "readme_sha256": V3_HASHES[V3 / "README.md"],
            "study_contract_sha256": V3_HASHES[V3 / "study-contract.json"],
            "study_id": "hbq-human-alignment-optimizer-v5-f20-broader-development-grok-exec-v3-threadsafe-route-load",
        },
        "prohibitions": ["no runtime optimizer dependency", "no fallback or resend", "no confirmation, private path, target, selection, promotion, runtime, or general claim"],
        "study_id": STUDY_ID,
    }


def _validate_contract(schedule: Mapping[str, Any]) -> None:
    value = contract()
    expected = _expected_contract()
    if (value != expected or schedule.get("geometry") != expected["geometry"]
            or schedule.get("candidate_freeze_manifest_sha256") != CANDIDATE_MANIFEST_SHA256):
        raise ValueError("execution contract drifted")


def _candidate_records(root: Path) -> tuple[ModuleType, list[dict[str, Any]], str]:
    study = candidate_study()
    manifest = study.validate_frozen_root(Path(root))
    rebuilt = study.materialize()
    if manifest != rebuilt or manifest.get("manifest_sha256") != CANDIDATE_MANIFEST_SHA256:
        raise ValueError("candidate freeze manifest drifted")
    _outer, parent_instruction, parent_profile, parent_profile_bytes, _ancestry = study._parent()
    parent = {
        "candidate_id": PARENT_CANDIDATE_ID,
        "candidate_sha256": PARENT_CANDIDATE_SHA256,
        "instruction": parent_instruction.decode("utf-8"),
        "instruction_sha256": sha256(parent_instruction),
        "profile": parent_profile,
        "profile_sha256": sha256(parent_profile_bytes),
        "parent_document_sha256": PARENT_DOCUMENT_SHA256,
        "kind": "admitted_parent",
    }
    children: list[dict[str, Any]] = []
    for row in manifest.get("candidates", []):
        if not isinstance(row, Mapping):
            raise TypeError("candidate freeze row drifted")
        try:
            instruction = base64.b64decode(row["instruction_base64"], validate=True)
            profile_raw = base64.b64decode(row["profile_base64"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("candidate freeze byte encoding drifted") from error
        profile = strict(profile_raw + b"\n", "candidate profile")
        if (not isinstance(row.get("candidate_id"), str) or not isinstance(row.get("candidate_sha256"), str)
                or row.get("instruction_sha256") != sha256(instruction) or row.get("profile_sha256") != sha256(profile_raw)):
            raise ValueError("candidate freeze identity drifted")
        children.append({
            "candidate_id": row["candidate_id"],
            "candidate_sha256": row["candidate_sha256"],
            "instruction": instruction.decode("utf-8"),
            "instruction_sha256": sha256(instruction),
            "profile": profile,
            "profile_sha256": sha256(profile_raw),
            "parent_document_sha256": PARENT_DOCUMENT_SHA256,
            "kind": "one_factor_one_clause_descendant",
            "factor": row.get("factor"),
            "addendum": row.get("addendum"),
        })
    records = [parent, *children]
    if len(records) != 5 or len({row["candidate_id"] for row in records}) != 5 or records[0]["candidate_id"] != PARENT_CANDIDATE_ID:
        raise ValueError("five-candidate lower-step geometry drifted")
    return study, records, manifest["manifest_sha256"]


def _development_templates(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    study = broader_study()
    schedule = study.validate_frozen_root(Path(root))
    if schedule.get("geometry") != {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0}:
        raise ValueError("frozen development geometry drifted")
    if schedule.get("authority", {}).get("confirmation") != {"status": "unopened", "cells": 0}:
        raise ValueError("confirmation surface is forbidden")
    groups = schedule.get("groups")
    cells = schedule.get("cells")
    if not isinstance(groups, list) or not isinstance(cells, list) or len(groups) != 7:
        raise ValueError("frozen development groups drifted")
    templates = [row for row in cells if isinstance(row, Mapping) and row.get("candidate_id") == PARENT_CANDIDATE_ID]
    if len(templates) != 7:
        raise ValueError("descendant13 development templates drifted")
    by_group = {row.get("prompt_group_id"): row for row in templates}
    if len(by_group) != 7 or {row.get("prompt_group_id") for row in groups} != set(by_group):
        raise ValueError("frozen development group/template binding drifted")
    ordered = [dict(by_group[row["prompt_group_id"]]) for row in groups if isinstance(row, Mapping) and isinstance(row.get("prompt_group_id"), str)]
    if len(ordered) != 7:
        raise ValueError("frozen development group type drifted")
    return schedule, ordered


def _candidate_manifest(row: Mapping[str, Any]) -> dict[str, Any]:
    value = {key: row[key] for key in ("candidate_id", "candidate_sha256", "instruction_sha256", "profile_sha256", "parent_document_sha256", "kind")}
    if row["kind"] != "admitted_parent":
        value |= {key: row[key] for key in ("factor", "addendum")}
    value["manifest_sha256"] = sha256(value)
    return value


def build_schedule(*, candidate_freeze_root: Path, development_freeze_root: Path) -> dict[str, Any]:
    _candidate_study, candidates, candidate_manifest_sha256 = _candidate_records(candidate_freeze_root)
    development, templates = _development_templates(development_freeze_root)
    groups = development["groups"]
    cells: list[dict[str, Any]] = []
    for group, template in zip(groups, templates, strict=True):
        if not isinstance(group, Mapping):
            raise TypeError("frozen development group drifted")
        payload_raw = base64.b64decode(template["payload_base64"], validate=True)
        template_payload = strict(payload_raw, "development template payload")
        if sha256(payload_raw) != template.get("payload_sha256"):
            raise ValueError("development template payload binding drifted")
        for candidate in candidates:
            payload = dict(template_payload)
            payload["study_id"] = STUDY_ID
            payload["instruction"] = candidate["instruction"]
            payload["profile"] = candidate["profile"]
            raw = canonical(payload)
            key = {"study_id": STUDY_ID, "candidate_id": candidate["candidate_id"], "prompt_group_id": group["prompt_group_id"], "item_id": group["item_id"]}
            cells.append({
                "ordinal": len(cells) + 1,
                "cell_id": "desc13-lower-grok-" + sha256(key)[:16],
                "route_name": "grok_primary",
                "partition": "development",
                "prompt_group_id": group["prompt_group_id"],
                "item_id": group["item_id"],
                "candidate_id": candidate["candidate_id"],
                "candidate_sha256": candidate["candidate_sha256"],
                "candidate_instruction_sha256": candidate["instruction_sha256"],
                "candidate_profile_sha256": candidate["profile_sha256"],
                "payload_base64": base64.b64encode(raw).decode("ascii"),
                "payload_sha256": sha256(raw),
                "response_schema_sha256": sha256(canonical(payload["response_schema"])),
            })
    if len(cells) != 35 or len({row["cell_id"] for row in cells}) != 35 or len({row["payload_sha256"] for row in cells}) != 35:
        raise ValueError("35-cell lower-step payload geometry drifted")
    value = {
        "format_version": 1,
        "study_id": STUDY_ID,
        "kind": "frozen_descendant13_lower_step_grok_development_schedule",
        "source_commit": SOURCE_COMMIT,
        "candidate_freeze_manifest_sha256": candidate_manifest_sha256,
        "development_schedule_sha256": development.get("schedule_sha256"),
        "candidates": [_candidate_manifest(row) for row in candidates],
        "groups": groups,
        "cells": cells,
        "geometry": {"candidates": 5, "development_groups": 7, "grok_cells": 35, "sol_cells": 0, "confirmation_cells": 0},
        "authority": {"provider_calls_made": 0, "process_launches": 0, "selection": "none", "promotion": "none", "runtime": "none", "sol": "out_of_scope", "confirmation": {"status": "unopened", "cells": 0}},
    }
    value["schedule_sha256"] = sha256(value)
    _validate_contract(value)
    return value


def _capture_prepared(lifecycle: ModuleType, schedule: Mapping[str, Any], root: Path) -> dict[str, tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]]:
    root = _safe(root)
    if lifecycle.inventory(root) != set(lifecycle.PREPARED):
        raise ValueError("prepared root is not pristine at runner entry")
    schedule_path = root.parent / "schedule.json"
    if stable(schedule_path) != canonical(schedule):
        raise ValueError("persisted schedule drifted before runner entry")
    captured = {name: (stable(root / name), _full_identity(root / name, directory=False)) for name in lifecycle.PREPARED}
    captured["schedule.json"] = (stable(schedule_path), _full_identity(schedule_path, directory=False))
    return captured


def _verify_callback_prepared(lifecycle: ModuleType, root: Path, captured: Mapping[str, tuple[bytes, tuple[tuple[str, int, int, int, int | None], ...]]]) -> None:
    root = _safe(root)
    expected = set(lifecycle.PREPARED) | {"responses"}
    if {path.name for path in root.iterdir()} != expected:
        raise ValueError("prepared root inventory drifted before launch")
    responses = root / "responses"
    _full_identity(responses, directory=True)
    if {path.name for path in responses.iterdir()}:
        raise ValueError("responses must be empty before launch intent")
    for name in lifecycle.PREPARED:
        raw, identity = captured[name]
        path = root / name
        if stable(path) != raw or _full_identity(path, directory=False) != identity:
            raise ValueError("prepared artifact drifted before launch")
    schedule_raw, schedule_identity = captured["schedule.json"]
    schedule_path = root.parent / "schedule.json"
    if stable(schedule_path) != schedule_raw or _full_identity(schedule_path, directory=False) != schedule_identity:
        raise ValueError("persisted schedule drifted before launch")


def _guard_runner(runner: Callable[..., Mapping[str, Any]], lifecycle: ModuleType, schedule: Mapping[str, Any]) -> Callable[..., Mapping[str, Any]]:
    def guarded(**kwargs: Any) -> Mapping[str, Any]:
        root = Path(kwargs["output_dir"])
        captured = _capture_prepared(lifecycle, schedule, root)
        before_contact = kwargs["before_contact"]

        def guarded_before_contact() -> None:
            _verify_callback_prepared(lifecycle, root, captured)
            before_contact()

        copied = dict(kwargs)
        copied["before_contact"] = guarded_before_contact
        return runner(**copied)

    return guarded


@contextmanager
def _bound_runtime(*, candidate_freeze_root: Path, development_freeze_root: Path) -> Iterator[tuple[ModuleType, dict[str, Any], ModuleType, ModuleType, ModuleType]]:
    schedule = build_schedule(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root))
    v3 = v3_runtime()
    runtime = v3._runtime()
    runtime.STUDY_ID = STUDY_ID
    original_admit = runtime.admit_frozen_root
    original_bound = runtime.bound_lifecycle
    lifecycle = runtime.lifecycle()
    source = lifecycle.live()
    original_schedule, original_study_id = lifecycle.schedule, lifecycle.STUDY_ID

    def admit(_ignored: Path) -> dict[str, Any]:
        return schedule

    lifecycle.schedule = lambda **_kwargs: (source, schedule)
    lifecycle.STUDY_ID = STUDY_ID

    @contextmanager
    def bound(_ignored: Path) -> Iterator[tuple[ModuleType, ModuleType, dict[str, Any]]]:
        yield lifecycle, source, schedule

    runtime.admit_frozen_root = admit
    runtime.bound_lifecycle = bound
    try:
        yield runtime, schedule, v3, lifecycle, source
    finally:
        runtime.admit_frozen_root, runtime.bound_lifecycle = original_admit, original_bound
        lifecycle.schedule, lifecycle.STUDY_ID = original_schedule, original_study_id


def _validated_route(v3: ModuleType, runtime: ModuleType, queue_root: Path, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None) -> Callable[[Path], tuple[dict[str, Any], dict[str, Any]]]:
    return v3._validated_route(runtime, Path(queue_root), route_provider)


def prepare_all(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None) -> dict[str, Any]:
    with _bound_runtime(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root)) as (runtime, schedule, v3, _lifecycle, _source):
        frozen_route = _validated_route(v3, runtime, Path(queue_root), route_provider)
        result = runtime.prepare_all(output_root=Path(output_root), frozen_root=Path(candidate_freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, route_provider=frozen_route)
    if (result.get("provider_calls_made") != 0 or result.get("process_launches") != 0
            or result.get("logical_cells") != 35 or result.get("effective_candidates") != 5
            or len(result.get("prepared_cells", [])) != 35):
        raise ValueError("lower-step preparation lifecycle drifted")
    root = Path(output_root)
    if stable(root / "schedule.json") != canonical(schedule):
        raise ValueError("persisted schedule differs from prepared schedule")
    return {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_35_descendant13_lower_step_grok_cells", "prepared_cells": result["prepared_cells"], "logical_cells": 35, "effective_candidates": 5, "provider_calls_made": 0, "process_launches": 0}


def execute_one(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, cell_id: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> dict[str, Any]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    with _bound_runtime(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root)) as (runtime, schedule, v3, lifecycle, source):
        if cell_id not in {row["cell_id"] for row in schedule["cells"]}:
            raise ValueError("unknown cell")
        frozen_route = _validated_route(v3, runtime, Path(queue_root), route_provider)
        selected_runner = runner or source._default_runner
        return runtime.execute_one(output_root=Path(output_root), frozen_root=Path(candidate_freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, cell_id=cell_id, allow_remote=True, route_provider=frozen_route, runner=_guard_runner(selected_runner, lifecycle, schedule))


async def execute_wave(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, queue_root: Path, authorization_acknowledgement_sha256: str, allow_remote: bool, route_provider: Callable[[Path], tuple[dict[str, Any], dict[str, Any]]] | None = None, runner: Callable[..., Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    if allow_remote is not True:
        raise ValueError("explicit allow_remote required")
    with _bound_runtime(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root)) as (runtime, schedule, v3, lifecycle, source):
        frozen_route = _validated_route(v3, runtime, Path(queue_root), route_provider)
        selected_runner = runner or source._default_runner
        result = await runtime.execute_wave(output_root=Path(output_root), frozen_root=Path(candidate_freeze_root), queue_root=Path(queue_root), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256, allow_remote=True, route_provider=frozen_route, runner=_guard_runner(selected_runner, lifecycle, schedule))
    if len(result) != len(schedule["cells"]):
        raise ValueError("lower-step execution wave cardinality drifted")
    return result


def finalize_collector(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, collector_output: Path, authorization_acknowledgement_sha256: str) -> dict[str, Any]:
    with _bound_runtime(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root)) as (runtime, _schedule, _v3, _lifecycle, _source):
        return runtime.finalize_collector(output_root=Path(output_root), frozen_root=Path(candidate_freeze_root), collector_output=Path(collector_output), authorization_acknowledgement_sha256=authorization_acknowledgement_sha256)


def replay_collector(*, output_root: Path, candidate_freeze_root: Path, development_freeze_root: Path, collector_path: Path) -> dict[str, Any]:
    with _bound_runtime(candidate_freeze_root=Path(candidate_freeze_root), development_freeze_root=Path(development_freeze_root)) as (runtime, _schedule, _v3, _lifecycle, _source):
        return runtime.replay_collector(output_root=Path(output_root), frozen_root=Path(candidate_freeze_root), collector_path=Path(collector_path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ("prepare-all", "execute-one", "execute-wave", "finalize-collector", "replay-collector"):
        modes.add_argument("--" + name, action="store_true")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--candidate-freeze-root", type=Path, required=True)
    parser.add_argument("--development-freeze-root", type=Path, required=True)
    parser.add_argument("--queue-root", type=Path)
    parser.add_argument("--collector-output", type=Path)
    parser.add_argument("--collector-path", type=Path)
    parser.add_argument("--authorization-acknowledgement-sha256")
    parser.add_argument("--cell-id")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)
    shared = {"output_root": args.output_root, "candidate_freeze_root": args.candidate_freeze_root, "development_freeze_root": args.development_freeze_root}
    if args.prepare_all:
        if args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256:
            parser.error("prepare requires queue/acknowledgement and forbids remote execution")
        result = prepare_all(**shared, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    elif args.execute_one:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256 or not args.cell_id:
            parser.error("execute-one requires queue/acknowledgement/cell and explicit remote execution")
        result = execute_one(**shared, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, cell_id=args.cell_id, allow_remote=True)
    elif args.execute_wave:
        if not args.allow_remote or not args.queue_root or not args.authorization_acknowledgement_sha256:
            parser.error("execute-wave requires queue/acknowledgement and explicit remote execution")
        result = asyncio.run(execute_wave(**shared, queue_root=args.queue_root, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256, allow_remote=True))
    elif args.finalize_collector:
        if args.allow_remote or not args.collector_output or not args.authorization_acknowledgement_sha256:
            parser.error("finalize requires collector output/acknowledgement and forbids remote execution")
        result = finalize_collector(**shared, collector_output=args.collector_output, authorization_acknowledgement_sha256=args.authorization_acknowledgement_sha256)
    else:
        if args.allow_remote or not args.collector_path:
            parser.error("replay requires collector path and forbids remote execution")
        result = replay_collector(**shared, collector_path=args.collector_path)
    print(canonical(result).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
