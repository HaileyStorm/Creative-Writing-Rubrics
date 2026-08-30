#!/usr/bin/env python3
"""Provider-free freezer, preparation, receipt validator, and endpoint projection for revision-gain v2."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(_SOURCE_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(_SOURCE_ROOT))

from hbqrs.core import compile_bundle, compiled_questions, load_bundles, load_modules, resolve_bundle
from hbqrs.runner import _question_payload

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
CONTRACT_PATH = HERE / "study-contract.json"
STUDY_ID = "cwr-guided-revision-gain-v2-lean-pilot"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _stable_bytes(path: Path, *, label: str) -> bytes:
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except FileNotFoundError as error:
            raise ValueError(f"Revision-gain v2 {label} is missing: {current}") from error
        if stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400):
            raise ValueError(f"Revision-gain v2 {label} path is reparsed: {current}")
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"Revision-gain v2 {label} is not a regular file: {path}")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (opened.st_dev, opened.st_ino, opened.st_size):
            raise ValueError(f"Revision-gain v2 {label} identity drifted before read")
        value = handle.read()
        after = os.fstat(handle.fileno())
    if (opened.st_dev, opened.st_ino, opened.st_size) != (after.st_dev, after.st_ino, after.st_size):
        raise ValueError(f"Revision-gain v2 {label} changed during read")
    return value


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _hex(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"Revision-gain v2 {label} must be a lowercase SHA-256 hex string")
    return value


def _commitment(path: Path, *, root: Path, label: str) -> dict[str, Any]:
    payload = _stable_bytes(path, label=label)
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as error:
        raise ValueError(f"Revision-gain v2 {label} escapes its approved root") from error
    return {"path": relative, "bytes": len(payload), "sha256": _sha256(payload)}


def _verify_binding(path: Path, expected: Mapping[str, Any], *, label: str) -> bytes:
    payload = _stable_bytes(path, label=label)
    if expected != {"path": expected.get("path"), "bytes": len(payload), "sha256": _sha256(payload)}:
        raise ValueError(f"Revision-gain v2 {label} binding drifted")
    return payload


def _asset(name: str, expected: Mapping[str, Any]) -> bytes:
    if set(expected) != {"path", "bytes", "sha256"} or expected["path"] != name:
        raise ValueError(f"Revision-gain v2 {name} contract shape drifted")
    return _verify_binding(HERE / name, expected, label=name)


def _cwr_question_payload(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Invoke the pinned runner composition; a hash alone is not CWR-feedback evidence."""
    runtime = value["cwr_runtime"]
    _verify_binding(REPOSITORY / "src" / "hbqrs" / "runner.py", runtime["runner"], label="pinned CWR runner")
    modules = load_modules(REPOSITORY / "registry" / "all_modules.json")
    bundles = load_bundles(REPOSITORY / "bundles" / "all_bundles.json")
    bundle = resolve_bundle(bundles, runtime["bundle_id"])
    questions = _question_payload(compiled_questions(compile_bundle(modules, bundle)))
    if not isinstance(questions, list) or not questions:
        raise ValueError("Revision-gain v2 CWR runner returned no question payload")
    return questions


def contract() -> dict[str, Any]:
    raw = _stable_bytes(CONTRACT_PATH, label="contract")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain v2 contract is invalid JSON") from error
    if not isinstance(value, dict) or value.get("format_version") != 1 or value.get("study_id") != STUDY_ID:
        raise ValueError("Revision-gain v2 contract identity drifted")
    source = value.get("sources")
    routes = value.get("routes")
    if not isinstance(source, Mapping) or set(source) != {"parent_contract_sha256", "items", "source_root_layout"}:
        raise ValueError("Revision-gain v2 source contract drifted")
    if source["parent_contract_sha256"] != "5fb06e5a4775ecfe1cee10132e52100733c7e765e8eae9865374bb23f1addddd" or source["source_root_layout"] != "inputs/<item-id>/{source.md,prompt.md}":
        raise ValueError("Revision-gain v2 source parent binding drifted")
    if not isinstance(source["items"], Mapping) or sorted(source["items"]) != ["hanna-1035", "hanna-178"]:
        raise ValueError("Revision-gain v2 source selection drifted")
    for item in source["items"].values():
        if not isinstance(item, Mapping) or set(item) != {"source.md", "prompt.md"}:
            raise ValueError("Revision-gain v2 source commitment shape drifted")
        for commitment in item.values():
            if not isinstance(commitment, Mapping) or set(commitment) != {"bytes", "sha256"}:
                raise ValueError("Revision-gain v2 source commitment drifted")
    if routes != {
        "generator": {"destination": "xai_grok_build_subscription", "model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "paid_api": False},
        "cwr_feedback": {"destination": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "tools_enabled": False, "paid_api": False},
        "judges": {
            "gpt-5.6-sol-high": {"destination": "codex", "model": "gpt-5.6-sol", "reasoning": "high", "tools_enabled": False, "paid_api": False},
            "grok-4.6-high": {"destination": "xai_grok_build_subscription", "model": "grok-4.6", "reasoning": "high", "tools_enabled": False, "paid_api": False},
        },
    }:
        raise ValueError("Revision-gain v2 provider identity, tools, or zero-charge contract drifted")
    runtime = value.get("cwr_runtime")
    if not isinstance(runtime, Mapping) or set(runtime) != {"bundle_id", "runner"} or runtime["bundle_id"] != "prose.short_story":
        raise ValueError("Revision-gain v2 CWR runtime contract drifted")
    _verify_binding(REPOSITORY / "src" / "hbqrs" / "runner.py", runtime["runner"], label="pinned CWR runner")
    assets = value.get("assets")
    expected_assets = {"revision-instruction.md", "cwr-feedback.prompt.md", "cwr-feedback.schema.json", "holistic.prompt.md", "compact.prompt.md", "score.schema.json"}
    if not isinstance(assets, Mapping) or set(assets) != expected_assets:
        raise ValueError("Revision-gain v2 asset inventory drifted")
    for name, binding in assets.items():
        _asset(name, binding)
    geometry = value.get("geometry")
    if geometry != {"sources": 2, "cycles": 2, "arms": 2, "revision_cells": 8, "cwr_feedback_cells": 4, "blind_targets": 10, "endpoint_cells": 40, "remote_contacts": 52}:
        raise ValueError("Revision-gain v2 geometry drifted")
    if value.get("execution_policy") != {"precontact": "terminal_fresh_root_required", "postlaunch": "terminal_reconcile_required_no_resend", "source": "immutable_versioned_descendants_only", "endpoint": "blind_identical_target_prompt_schema_per_measure_across_judges"}:
        raise ValueError("Revision-gain v2 terminality or blindness policy drifted")
    return value


def _revision_id(cycle: int, item_id: str, arm: str) -> str:
    return f"revision-v2-c{cycle}-{item_id}-grok-4.6-{arm}"


def revision_schedule(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else value
    rows: list[dict[str, Any]] = []
    for cycle in (1, 2):
        for item_id in sorted(value["sources"]["items"]):
            for arm in ("cwr_guided", "generic_no_feedback"):
                event_id = _revision_id(cycle, item_id, arm)
                rows.append({"event_id": event_id, "cycle": cycle, "source_item_id": item_id, "generator_id": "grok-4.6", "guidance_arm": arm, "parent_event_id": None if cycle == 1 else _revision_id(1, item_id, arm), "cwr_feedback_event_id": None if arm == "generic_no_feedback" else f"feedback-v2-{event_id}"})
    return rows


def targets(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else value
    rows = [{"blind_target_id": f"target-v2-baseline-{item_id}", "kind": "source_baseline", "target_event_id": None, "source_item_id": item_id} for item_id in sorted(value["sources"]["items"])]
    rows.extend({"blind_target_id": f"target-v2-{event['event_id']}", "kind": "revision_descendant", "target_event_id": event["event_id"], "source_item_id": event["source_item_id"]} for event in revision_schedule(value))
    return rows


def endpoint_schedule(value: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    value = contract() if value is None else value
    rows: list[dict[str, Any]] = []
    for target in targets(value):
        for measure_id in ("holistic", "compact"):
            for judge_route_id in ("gpt-5.6-sol-high", "grok-4.6-high"):
                rows.append({"endpoint_event_id": f"endpoint-v2-{target['blind_target_id']}-{measure_id}-{judge_route_id}", "blind_target_id": target["blind_target_id"], "measure_id": measure_id, "judge_route_id": judge_route_id})
    return rows


def _write_once(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(canonical(value) + b"\n")


def _write_bytes_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def freeze_inputs(*, source_root: Path, work_root: Path) -> dict[str, Any]:
    value = contract()
    source_root, work_root = Path(source_root), Path(work_root)
    rows: list[dict[str, Any]] = []
    for item_id, bindings in sorted(value["sources"]["items"].items()):
        row = {"item_id": item_id}
        for filename in ("source.md", "prompt.md"):
            path = source_root / "inputs" / item_id / filename
            payload = _stable_bytes(path, label=f"external {filename}")
            expected = bindings[filename]
            if {"bytes": len(payload), "sha256": _sha256(payload)} != dict(expected):
                raise ValueError(f"Revision-gain v2 frozen {item_id} {filename} binding drifted")
            row[filename] = {"path": f"inputs/{item_id}/{filename}", **dict(expected)}
        rows.append(row)
    question_payload = _cwr_question_payload(value)
    question_path = work_root / "frozen-cwr-question-payload.json"
    _write_once(question_path, question_payload)
    frozen = {"format_version": 1, "study_id": STUDY_ID, "kind": "frozen_external_inputs", "contract_sha256": _sha256(_stable_bytes(CONTRACT_PATH, label="contract")), "source_material_copied": False, "source_root_not_persisted": True, "items": rows, "cwr_question_payload": _commitment(question_path, root=work_root, label="frozen CWR question payload"), "revision_schedule_sha256": _sha256(canonical(revision_schedule(value))), "endpoint_schedule_sha256": _sha256(canonical(endpoint_schedule(value)))}
    _write_once(work_root / "frozen-inputs.json", frozen)
    return frozen


def _read_frozen(work_root: Path, *, verify_cwr_output: bool = False, study_value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    path = Path(work_root) / "frozen-inputs.json"
    raw = _stable_bytes(path, label="frozen inputs")
    value = json.loads(raw.decode("utf-8"))
    contract_sha256 = _sha256(_stable_bytes(CONTRACT_PATH, label="contract"))
    if canonical(value) + b"\n" != raw or value.get("study_id") != STUDY_ID or value.get("source_material_copied") is not False or value.get("contract_sha256") != contract_sha256:
        raise ValueError("Revision-gain v2 frozen input manifest drifted")
    expected_items = []
    study_value = contract() if study_value is None else study_value
    for item_id, bindings in sorted(study_value["sources"]["items"].items()):
        expected_items.append({"item_id": item_id, "source.md": {"path": f"inputs/{item_id}/source.md", **bindings["source.md"]}, "prompt.md": {"path": f"inputs/{item_id}/prompt.md", **bindings["prompt.md"]}})
    if value.get("items") != expected_items:
        raise ValueError("Revision-gain v2 frozen source commitments drifted")
    question = _verified_work_commitment(Path(work_root), value.get("cwr_question_payload"), label="frozen CWR question payload")
    payload = json.loads(_stable_bytes(Path(work_root) / question["path"], label="frozen CWR question payload").decode("utf-8"))
    if verify_cwr_output and payload != _cwr_question_payload(study_value):
        raise ValueError("Revision-gain v2 frozen CWR runner output drifted")
    return value


def _prepared_payload(value: Mapping[str, Any], *, phase: str, event_id: str, target_commitment: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if phase == "cwr_feedback":
        event = next((row for row in revision_schedule(value) if row["cwr_feedback_event_id"] == event_id), None)
        route = value["routes"]["cwr_feedback"]
        assets = ["cwr-feedback.prompt.md", "cwr-feedback.schema.json"]
    elif phase == "revision_generation":
        event = next((row for row in revision_schedule(value) if row["event_id"] == event_id), None)
        route = value["routes"]["generator"]
        assets = ["revision-instruction.md"]
    elif phase == "blind_endpoint_judgment":
        event = next((row for row in endpoint_schedule(value) if row["endpoint_event_id"] == event_id), None)
        if event is None:
            raise ValueError("Revision-gain v2 endpoint event is not scheduled")
        route = value["routes"]["judges"][event["judge_route_id"]]
        assets = [f"{event['measure_id']}.prompt.md", "score.schema.json"]
    else:
        raise ValueError("Revision-gain v2 preparation phase is unsupported")
    if event is None:
        raise ValueError("Revision-gain v2 prepared event is not scheduled")
    return {"study_id": STUDY_ID, "phase": phase, "event_id": event_id, "schedule_event": event, "destination": route["destination"], "provider_model": route["model"], "reasoning": route["reasoning"], "tools_enabled": False, "paid_api": False, "assets": [dict(value["assets"][name]) for name in assets], "blind_target": dict(target_commitment) if target_commitment is not None else None}


def _source_material(*, source_root: Path, frozen: Mapping[str, Any], item_id: str) -> tuple[str, str]:
    item = next(row for row in frozen["items"] if row["item_id"] == item_id)
    source_path = Path(source_root) / item["source.md"]["path"]
    prompt_path = Path(source_root) / item["prompt.md"]["path"]
    if _commitment(source_path, root=Path(source_root), label="prepared source") != item["source.md"] or _commitment(prompt_path, root=Path(source_root), label="prepared prompt") != item["prompt.md"]:
        raise ValueError("Revision-gain v2 source bytes drifted after freeze")
    return (_stable_bytes(source_path, label="prepared source").decode("utf-8"), _stable_bytes(prompt_path, label="prepared prompt").decode("utf-8"))


def _read_verified_receipt(path: Path, *, expected_event_id: str, expected_phase: str) -> dict[str, Any]:
    raw = _stable_bytes(path, label="verified native receipt")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain v2 verified native receipt is invalid") from error
    if canonical(value) + b"\n" != raw or value.get("study_id") != STUDY_ID or value.get("event_id") != expected_event_id or value.get("phase") != expected_phase or value.get("kind") != "verified_native_receipt":
        raise ValueError("Revision-gain v2 verified native receipt binding drifted")
    if not isinstance(value.get("prepared_root"), str) or not isinstance(value.get("native_receipt"), Mapping):
        raise ValueError("Revision-gain v2 verified native receipt lacks replayable native evidence")
    reopened = validate_receipt(prepared_root=Path(value["prepared_root"]), receipt=value["native_receipt"], output_path=None)
    if reopened != value:
        raise ValueError("Revision-gain v2 verified native receipt failed replay authentication")
    return value


def prepare_targets(*, work_root: Path, target_root: Path, source_root: Path, revision_records: list[Mapping[str, Any]]) -> dict[str, Any]:
    value = contract()
    frozen = _read_frozen(Path(work_root))
    target_root = Path(target_root)
    if target_root.exists():
        raise ValueError("Revision-gain v2 target root is immutable; use a fresh root")
    lineage_validation = validate_revision_lineage(work_root=Path(work_root), records=revision_records)
    lineage_path = target_root / "validated-revision-lineage.json"
    _write_once(lineage_path, revision_records)
    lineage = {record["event_id"]: record["descendant"] for record in revision_records}
    rows = []
    for target in targets(value):
        if target["kind"] == "source_baseline":
            source_text, _ = _source_material(source_root=Path(source_root), frozen=frozen, item_id=target["source_item_id"])
            payload = source_text.encode("utf-8")
        else:
            payload = _stable_bytes(Path(work_root) / lineage[target["target_event_id"]]["path"], label="lineage descendant")
        artifact = target_root / "targets" / f"{target['blind_target_id']}.md"
        _write_bytes_once(artifact, payload)
        origin = ({"kind": "source_baseline", "source_item_id": target["source_item_id"], "source": value["sources"]["items"][target["source_item_id"]]["source.md"]} if target["kind"] == "source_baseline" else {"kind": "revision_descendant", "event_id": target["target_event_id"], "descendant": lineage[target["target_event_id"]]})
        rows.append({"blind_target_id": target["blind_target_id"], "target": _commitment(artifact, root=target_root, label="blind target"), "origin": origin})
    manifest = {"format_version": 1, "study_id": STUDY_ID, "kind": "frozen_blind_targets", "work_root": str(Path(work_root).resolve()), "frozen_manifest_sha256": _sha256(_stable_bytes(Path(work_root) / "frozen-inputs.json", label="frozen inputs")), "revision_lineage": _commitment(lineage_path, root=target_root, label="validated revision lineage"), "revision_lineage_sha256": lineage_validation["revision_lineage_sha256"], "targets": rows}
    _write_once(target_root / "target-manifest.json", manifest)
    return manifest


def _target_from_manifest(target_root: Path, manifest_path: Path, blind_target_id: str, frozen_sha256: str, *, study_value: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    raw = _stable_bytes(manifest_path, label="target manifest")
    value = json.loads(raw.decode("utf-8"))
    if canonical(value) + b"\n" != raw or value.get("study_id") != STUDY_ID or value.get("kind") != "frozen_blind_targets" or value.get("frozen_manifest_sha256") != frozen_sha256 or not isinstance(value.get("revision_lineage_sha256"), str) or not isinstance(value.get("work_root"), str):
        raise ValueError("Revision-gain v2 target manifest binding drifted")
    lineage_commitment = _verified_work_commitment(Path(target_root), value.get("revision_lineage"), label="validated revision lineage")
    lineage_raw = _stable_bytes(Path(target_root) / lineage_commitment["path"], label="validated revision lineage")
    try:
        lineage_records = json.loads(lineage_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain v2 validated revision lineage is invalid") from error
    if not isinstance(lineage_records, list) or canonical(lineage_records) + b"\n" != lineage_raw:
        raise ValueError("Revision-gain v2 validated revision lineage is not canonical")
    validation = validate_revision_lineage(work_root=Path(value["work_root"]), records=lineage_records)
    if value["revision_lineage_sha256"] != validation["revision_lineage_sha256"]:
        raise ValueError("Revision-gain v2 target manifest lineage hash drifted")
    descendants = {record["event_id"]: record["descendant"] for record in lineage_records}
    study_value = contract() if study_value is None else study_value
    expected_targets = {row["blind_target_id"]: row for row in targets(study_value)}
    manifest_targets = value.get("targets")
    if not isinstance(manifest_targets, list) or len(manifest_targets) != 10 or {row.get("blind_target_id") for row in manifest_targets if isinstance(row, Mapping)} != set(expected_targets):
        raise ValueError("Revision-gain v2 target manifest inventory is incomplete")
    for row in manifest_targets:
        target = expected_targets[row["blind_target_id"]]
        commitment = _verified_work_commitment(Path(target_root), row.get("target"), label="blind target")
        origin = row.get("origin")
        if target["kind"] == "source_baseline":
            expected_origin = {"kind": "source_baseline", "source_item_id": target["source_item_id"], "source": study_value["sources"]["items"][target["source_item_id"]]["source.md"]}
            if origin != expected_origin or {"bytes": commitment["bytes"], "sha256": commitment["sha256"]} != expected_origin["source"]:
                raise ValueError("Revision-gain v2 baseline target origin drifted")
        elif origin != {"kind": "revision_descendant", "event_id": target["target_event_id"], "descendant": descendants.get(target["target_event_id"])} or origin.get("descendant", {}).get("bytes") != commitment["bytes"] or origin.get("descendant", {}).get("sha256") != commitment["sha256"]:
            raise ValueError("Revision-gain v2 descendant target origin drifted")
    rows = [row for row in manifest_targets if isinstance(row, Mapping) and row.get("blind_target_id") == blind_target_id]
    if len(rows) != 1:
        raise ValueError("Revision-gain v2 blind target is not frozen")
    commitment = _verified_work_commitment(Path(target_root), rows[0].get("target"), label="blind target")
    return commitment, _stable_bytes(Path(target_root) / commitment["path"], label="blind target").decode("utf-8")


def prepare_cell(*, work_root: Path, prepared_root: Path, phase: str, event_id: str, acknowledgement_sha256: str, source_root: Path | None = None, revision_records: list[Mapping[str, Any]] | None = None, feedback_receipt_path: Path | None = None, target_root: Path | None = None, target_manifest_path: Path | None = None) -> dict[str, Any]:
    value = contract()
    work_root = Path(work_root)
    frozen = _read_frozen(work_root, verify_cwr_output=phase == "cwr_feedback")
    _hex(acknowledgement_sha256, label="zero-charge acknowledgement hash")
    prepared_root = Path(prepared_root)
    if prepared_root.exists():
        raise ValueError("Revision-gain v2 prepared root is terminal; use a fresh root")
    frozen_sha256 = _sha256(_stable_bytes(work_root / "frozen-inputs.json", label="frozen inputs"))
    generic = _prepared_payload(value, phase=phase, event_id=event_id)
    event = generic["schedule_event"]
    source_text = prompt_text = None
    parent_commitment = None
    if phase in {"cwr_feedback", "revision_generation"}:
        if source_root is None:
            raise ValueError("Revision-gain v2 source-root is required for feedback and revision preparation")
        if event.get("parent_event_id") is None:
            source_text, prompt_text = _source_material(source_root=Path(source_root), frozen=frozen, item_id=event["source_item_id"])
        else:
            if revision_records is None:
                raise ValueError("Revision-gain v2 cycle-two preparation requires a cycle-one lineage parent")
            parents = [record for record in revision_records if isinstance(record, Mapping) and record.get("event_id") == event["parent_event_id"]]
            if len(parents) != 1:
                raise ValueError("Revision-gain v2 cycle-two preparation cannot select an arbitrary parent")
            parent = parents[0]
            if set(parent) != {"event_id", "source", "parent", "descendant", "generator", "generator_receipt", "cwr_feedback"}:
                raise ValueError("Revision-gain v2 cycle-two parent record is not authenticated")
            if parent.get("source") != {"item_id": event["source_item_id"], "source.md": value["sources"]["items"][event["source_item_id"]]["source.md"], "prompt.md": value["sources"]["items"][event["source_item_id"]]["prompt.md"]}:
                raise ValueError("Revision-gain v2 cycle-two source parent binding drifted")
            parent_commitment = dict(parent["descendant"])
            _verified_work_commitment(work_root, parent_commitment, label="cycle-one descendant")
            parent_receipt_commitment = _verified_work_commitment(work_root, parent["generator_receipt"], label="cycle-one Grok receipt")
            parent_receipt = _read_verified_receipt(work_root / parent_receipt_commitment["path"], expected_event_id=event["parent_event_id"], expected_phase="revision_generation")
            parent_bytes = _stable_bytes(work_root / parent_commitment["path"], label="cycle-one descendant")
            parent_story = parent_receipt["response"].get("story") if isinstance(parent_receipt.get("response"), Mapping) else None
            if parent_story != parent_bytes.decode("utf-8"):
                raise ValueError("Revision-gain v2 cycle-two parent bytes are not its authenticated Grok response")
            source_text = _stable_bytes(work_root / parent_commitment["path"], label="cycle-one descendant").decode("utf-8")
            _, prompt_text = _source_material(source_root=Path(source_root), frozen=frozen, item_id=event["source_item_id"])
    if phase == "cwr_feedback":
        question_commitment = _verified_work_commitment(work_root, frozen["cwr_question_payload"], label="frozen CWR question payload")
        questions = json.loads(_stable_bytes(work_root / question_commitment["path"], label="frozen CWR question payload").decode("utf-8"))
        payload = {"event_id": event_id, "role": phase, "source_text": source_text, "originating_prompt": prompt_text, "question_payload": questions, "feedback_prompt": _asset("cwr-feedback.prompt.md", value["assets"]["cwr-feedback.prompt.md"]).decode("utf-8"), "response_schema": json.loads(_asset("cwr-feedback.schema.json", value["assets"]["cwr-feedback.schema.json"]).decode("utf-8")), "parent_descendant": parent_commitment}
    elif phase == "revision_generation":
        feedback = None
        if event["guidance_arm"] == "cwr_guided":
            if feedback_receipt_path is None:
                raise ValueError("Revision-gain v2 guided revision requires its verified Sol feedback receipt")
            feedback = _read_verified_receipt(Path(feedback_receipt_path), expected_event_id=event["cwr_feedback_event_id"], expected_phase="cwr_feedback")
        payload = {"event_id": event_id, "role": phase, "source_text": source_text, "originating_prompt": prompt_text, "revision_instruction": _asset("revision-instruction.md", value["assets"]["revision-instruction.md"]).decode("utf-8"), "cwr_feedback": feedback["response"] if feedback is not None else None, "cwr_feedback_receipt_sha256": _sha256(_stable_bytes(Path(feedback_receipt_path), label="verified Sol feedback receipt")) if feedback_receipt_path else None, "parent_descendant": parent_commitment}
    else:
        if target_root is None or target_manifest_path is None:
            raise ValueError("Revision-gain v2 endpoint preparation requires a frozen target manifest")
        target_commitment, target_text = _target_from_manifest(Path(target_root), Path(target_manifest_path), event["blind_target_id"], frozen_sha256)
        measure = event["measure_id"]
        payload = {"blind_target_text": target_text, "endpoint_prompt": _asset(f"{measure}.prompt.md", value["assets"][f"{measure}.prompt.md"]).decode("utf-8"), "response_schema": json.loads(_asset("score.schema.json", value["assets"]["score.schema.json"]).decode("utf-8"))}
    _write_once(prepared_root / "payload.json", payload)
    payload_commitment = _commitment(prepared_root / "payload.json", root=prepared_root, label="prepared outbound payload")
    prepared = {"format_version": 1, "study_id": STUDY_ID, "kind": "prepared_cell", "work_root": str(work_root.resolve()), "frozen_manifest_sha256": frozen_sha256, "acknowledgement_sha256": acknowledgement_sha256, "provider_calls_made": 0, "process_launches": 0, "payload": payload_commitment, "phase": phase, "event_id": event_id, "provider_model": generic["provider_model"], "reasoning": generic["reasoning"], "tools_enabled": False, "endpoint_target": ({"target_root": str(Path(target_root).resolve()), "target_manifest": _commitment(Path(target_manifest_path), root=Path(target_root), label="target manifest"), "blind_target_id": event["blind_target_id"], "target": target_commitment} if phase == "blind_endpoint_judgment" else None), "no_resend": True, "precontact_failure": "terminal_fresh_root_required", "postlaunch_failure": "terminal_reconcile_required_no_resend"}
    _write_once(prepared_root / "prepared-cell.json", prepared)
    return prepared


def terminal_outcome(*, process_launches: int, settled: bool) -> dict[str, Any]:
    """Classify a failed execution without offering an in-place resend path."""
    if isinstance(process_launches, bool) or not isinstance(process_launches, int) or process_launches < 0:
        raise ValueError("Revision-gain v2 process launch count is invalid")
    if settled:
        if process_launches != 1:
            raise ValueError("Revision-gain v2 settled execution must have one launch")
        return {"state": "settled", "no_resend": True}
    if process_launches == 0:
        return {"state": "terminal_precontact", "fresh_output_root_required": True, "no_resend": True}
    return {"state": "terminal_postlaunch_reconcile_required", "fresh_output_root_required": False, "no_resend": True}


def begin_one_launch(*, prepared_root: Path) -> dict[str, Any]:
    """Persist the only launch intent; native dispatch remains outside this provider-free module."""
    prepared_root = Path(prepared_root)
    raw = _stable_bytes(prepared_root / "prepared-cell.json", label="prepared cell")
    try:
        prepared = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain v2 prepared cell is invalid") from error
    if canonical(prepared) + b"\n" != raw:
        raise ValueError("Revision-gain v2 prepared cell is not canonical")
    _validate_current_prepared(prepared_root=prepared_root, prepared=prepared)
    if (prepared_root / "terminal-outcome.json").exists() or (prepared_root / "verified-receipt.json").exists():
        raise ValueError("Revision-gain v2 cell is terminal and cannot launch again")
    intent = {"format_version": 1, "study_id": STUDY_ID, "kind": "one_launch_intent", "prepared_record_sha256": _sha256(raw), "process_launches": 1, "no_resend": True}
    _write_once(prepared_root / "launch-intent.json", intent)
    return intent


def record_terminal_outcome(*, prepared_root: Path, process_launches: int, settled: bool) -> dict[str, Any]:
    prepared_root = Path(prepared_root)
    if process_launches == 0 and (prepared_root / "launch-intent.json").exists():
        raise ValueError("Revision-gain v2 launched cells cannot become precontact outcomes")
    if process_launches == 1:
        intent = json.loads(_stable_bytes(prepared_root / "launch-intent.json", label="launch intent").decode("utf-8"))
        if intent.get("process_launches") != 1:
            raise ValueError("Revision-gain v2 launch intent drifted")
    elif process_launches != 0:
        raise ValueError("Revision-gain v2 supports at most one process launch")
    outcome = terminal_outcome(process_launches=process_launches, settled=settled)
    _write_once(prepared_root / "terminal-outcome.json", outcome)
    return outcome


def reconcile_postlaunch(*, prepared_root: Path, acknowledgement_sha256: str) -> dict[str, Any]:
    """Explicitly authorize acceptance review after a launched cell reached a terminal ambiguous state."""
    prepared_root = Path(prepared_root)
    _hex(acknowledgement_sha256, label="reconciliation acknowledgement hash")
    prepared_raw = _stable_bytes(prepared_root / "prepared-cell.json", label="prepared cell")
    intent_raw = _stable_bytes(prepared_root / "launch-intent.json", label="launch intent")
    outcome_raw = _stable_bytes(prepared_root / "terminal-outcome.json", label="terminal outcome")
    outcome = json.loads(outcome_raw.decode("utf-8"))
    if canonical(outcome) + b"\n" != outcome_raw or outcome != {"state": "terminal_postlaunch_reconcile_required", "fresh_output_root_required": False, "no_resend": True}:
        raise ValueError("Revision-gain v2 reconciliation requires a postlaunch terminal outcome")
    reconciliation = {"format_version": 1, "study_id": STUDY_ID, "kind": "postlaunch_receipt_reconciliation", "prepared_record_sha256": _sha256(prepared_raw), "launch_intent_sha256": _sha256(intent_raw), "terminal_outcome_sha256": _sha256(outcome_raw), "acknowledgement_sha256": acknowledgement_sha256, "action": "accept_settled_native_receipt_without_resend"}
    _write_once(prepared_root / "reconciliation.json", reconciliation)
    return reconciliation


def _verified_work_commitment(work_root: Path, value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "bytes", "sha256"}:
        raise ValueError(f"Revision-gain v2 {label} commitment shape drifted")
    relative = value["path"]
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise ValueError(f"Revision-gain v2 {label} path is unsafe")
    actual = _commitment(Path(work_root) / Path(relative), root=Path(work_root), label=label)
    if actual != dict(value):
        raise ValueError(f"Revision-gain v2 {label} commitment drifted")
    return actual


def validate_revision_lineage(*, work_root: Path, records: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate exact source/parent/descendant lineage without creating or dispatching anything."""
    value = contract()
    schedule = {row["event_id"]: row for row in revision_schedule(value)}
    if len(records) != len(schedule):
        raise ValueError("Revision-gain v2 revision lineage is incomplete")
    descendants: dict[str, dict[str, Any]] = {}
    seen_paths: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"event_id", "source", "parent", "descendant", "generator", "generator_receipt", "cwr_feedback"}:
            raise ValueError("Revision-gain v2 revision lineage record shape drifted")
        event = schedule.get(record["event_id"])
        if event is None or event["event_id"] in descendants:
            raise ValueError("Revision-gain v2 revision lineage event drifted")
        source = record["source"]
        expected_source = value["sources"]["items"][event["source_item_id"]]
        if source != {"item_id": event["source_item_id"], "source.md": expected_source["source.md"], "prompt.md": expected_source["prompt.md"]}:
            raise ValueError("Revision-gain v2 source lineage binding drifted")
        if event["parent_event_id"] is None:
            if record["parent"] is not None:
                raise ValueError("Revision-gain v2 cycle-one parent drifted")
        else:
            expected_parent = descendants.get(event["parent_event_id"])
            if record["parent"] != {"event_id": event["parent_event_id"], "descendant": expected_parent}:
                raise ValueError("Revision-gain v2 cycle-two parent lineage drifted")
        descendant = _verified_work_commitment(Path(work_root), record["descendant"], label="revision descendant")
        if Path(descendant["path"]).parts[:1] == ("inputs",):
            raise ValueError("Revision-gain v2 descendant cannot reuse an immutable source path")
        if descendant["path"] in seen_paths:
            raise ValueError("Revision-gain v2 descendants must have separate immutable paths")
        seen_paths.add(descendant["path"])
        if record["generator"] != {"model": "grok-4.6", "reasoning": "high", "tools_enabled": False}:
            raise ValueError("Revision-gain v2 generator identity drifted")
        generator_commitment = _verified_work_commitment(Path(work_root), record["generator_receipt"], label="Grok revision receipt")
        generator_receipt = _read_verified_receipt(Path(work_root) / generator_commitment["path"], expected_event_id=event["event_id"], expected_phase="revision_generation")
        if generator_receipt.get("provider_model") != "grok-4.6" or generator_receipt.get("reasoning") != "high" or generator_receipt.get("tools_enabled") is not False:
            raise ValueError("Revision-gain v2 Grok generator native identity drifted")
        returned_story = generator_receipt.get("response", {}).get("story") if isinstance(generator_receipt.get("response"), Mapping) else None
        descendant_bytes = _stable_bytes(Path(work_root) / descendant["path"], label="revision descendant")
        if not isinstance(returned_story, str) or descendant_bytes != returned_story.encode("utf-8") or _sha256(descendant_bytes) != descendant["sha256"]:
            raise ValueError("Revision-gain v2 descendant bytes are not the verified Grok response")
        if event["guidance_arm"] == "generic_no_feedback":
            if record["cwr_feedback"] is not None:
                raise ValueError("Revision-gain v2 control arm must not carry CWR feedback")
        else:
            feedback = record["cwr_feedback"]
            if not isinstance(feedback, Mapping) or set(feedback) != {"event_id", "verified_receipt"} or feedback["event_id"] != event["cwr_feedback_event_id"]:
                raise ValueError("Revision-gain v2 feedback lineage binding drifted")
            receipt_commitment = _verified_work_commitment(Path(work_root), feedback["verified_receipt"], label="Sol feedback receipt")
            receipt = _read_verified_receipt(Path(work_root) / receipt_commitment["path"], expected_event_id=event["cwr_feedback_event_id"], expected_phase="cwr_feedback")
            if receipt.get("provider_model") != "gpt-5.6-sol" or receipt.get("reasoning") != "high" or receipt.get("tools_enabled") is not False:
                raise ValueError("Revision-gain v2 Sol feedback native identity drifted")
        descendants[event["event_id"]] = descendant
    if set(descendants) != set(schedule):
        raise ValueError("Revision-gain v2 revision lineage lacks scheduled descendants")
    return {"study_id": STUDY_ID, "kind": "validated_revision_lineage", "record_count": len(descendants), "revision_lineage_sha256": _sha256(canonical(records))}


def _validate_current_prepared(*, prepared_root: Path, prepared: Mapping[str, Any], study_value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(prepared.get("work_root"), str):
        raise ValueError("Revision-gain v2 prepared work-root binding is missing")
    work_root = Path(prepared["work_root"])
    value = contract() if study_value is None else study_value
    frozen = _read_frozen(work_root, verify_cwr_output=prepared["phase"] == "cwr_feedback", study_value=value)
    frozen_raw = _stable_bytes(work_root / "frozen-inputs.json", label="frozen inputs")
    if prepared["frozen_manifest_sha256"] != _sha256(frozen_raw):
        raise ValueError("Revision-gain v2 prepared frozen manifest drifted")
    payload = _verified_work_commitment(prepared_root, prepared.get("payload"), label="prepared outbound payload")
    payload_raw = _stable_bytes(prepared_root / payload["path"], label="prepared outbound payload")
    try:
        content = json.loads(payload_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain v2 prepared payload is invalid") from error
    if canonical(content) + b"\n" != payload_raw:
        raise ValueError("Revision-gain v2 prepared payload is not canonical")
    if prepared["phase"] == "cwr_feedback":
        if content.get("question_payload") != _cwr_question_payload(value) or content.get("feedback_prompt") != _asset("cwr-feedback.prompt.md", value["assets"]["cwr-feedback.prompt.md"]).decode("utf-8") or content.get("response_schema") != json.loads(_asset("cwr-feedback.schema.json", value["assets"]["cwr-feedback.schema.json"]).decode("utf-8")):
            raise ValueError("Revision-gain v2 current CWR feedback payload/schema drifted")
    elif prepared["phase"] == "revision_generation":
        if content.get("revision_instruction") != _asset("revision-instruction.md", value["assets"]["revision-instruction.md"]).decode("utf-8"):
            raise ValueError("Revision-gain v2 current revision instruction drifted")
    elif prepared["phase"] == "blind_endpoint_judgment":
        target_info = prepared.get("endpoint_target")
        event = next((row for row in endpoint_schedule(value) if row["endpoint_event_id"] == prepared["event_id"]), None)
        if not isinstance(target_info, Mapping) or event is None:
            raise ValueError("Revision-gain v2 endpoint target binding is missing")
        actual_manifest = _commitment(Path(target_info["target_root"]) / target_info["target_manifest"]["path"], root=Path(target_info["target_root"]), label="target manifest")
        if actual_manifest != target_info.get("target_manifest"):
            raise ValueError("Revision-gain v2 prepared target manifest commitment drifted")
        target, text = _target_from_manifest(Path(target_info["target_root"]), Path(target_info["target_root"]) / target_info["target_manifest"]["path"], event["blind_target_id"], prepared["frozen_manifest_sha256"], study_value=value)
        expected = {"blind_target_text": text, "endpoint_prompt": _asset(f"{event['measure_id']}.prompt.md", value["assets"][f"{event['measure_id']}.prompt.md"]).decode("utf-8"), "response_schema": json.loads(_asset("score.schema.json", value["assets"]["score.schema.json"]).decode("utf-8"))}
        if target != target_info.get("target") or content != expected:
            raise ValueError("Revision-gain v2 endpoint payload/schema/target drifted")
    else:
        raise ValueError("Revision-gain v2 prepared phase is unsupported")
    return {"payload": payload, "content": content, "frozen": frozen}


def _validate_response_schema(prepared: Mapping[str, Any], response: Mapping[str, Any]) -> None:
    phase = prepared["phase"]
    if phase == "cwr_feedback":
        findings = response.get("findings") if isinstance(response, Mapping) else None
        if set(response) != {"findings"} or not isinstance(findings, list) or len(findings) > 3:
            raise ValueError("Revision-gain v2 Sol feedback response schema drifted")
        for finding in findings:
            if not isinstance(finding, Mapping) or set(finding) != {"location", "observation", "repair_target"} or any(not isinstance(finding[name], str) or not finding[name] for name in finding):
                raise ValueError("Revision-gain v2 Sol feedback finding schema drifted")
    elif phase == "revision_generation":
        if set(response) != {"story"} or not isinstance(response.get("story"), str) or not response["story"]:
            raise ValueError("Revision-gain v2 Grok revision response schema drifted")
    elif phase == "blind_endpoint_judgment":
        event = next((row for row in endpoint_schedule(contract()) if row["endpoint_event_id"] == prepared["event_id"]), None)
        limits = (1, 7) if event and event["measure_id"] == "holistic" else (1, 5)
        score = response.get("overall") if isinstance(response, Mapping) else None
        if set(response) != {"overall", "rationale"} or not isinstance(score, int) or isinstance(score, bool) or not limits[0] <= score <= limits[1] or not isinstance(response.get("rationale"), str) or not response["rationale"]:
            raise ValueError("Revision-gain v2 endpoint response schema drifted")
    else:
        raise ValueError("Revision-gain v2 response phase is unsupported")


def validate_receipt(*, prepared_root: Path, receipt: Mapping[str, Any], output_path: Path | None = None, study_value: Mapping[str, Any] | None = None) -> dict[str, Any]:
    raw = _stable_bytes(Path(prepared_root) / "prepared-cell.json", label="prepared cell")
    prepared = json.loads(raw.decode("utf-8"))
    if canonical(prepared) + b"\n" != raw:
        raise ValueError("Revision-gain v2 prepared cell is not canonical")
    current = _validate_current_prepared(prepared_root=Path(prepared_root), prepared=prepared, study_value=study_value)
    intent_raw = _stable_bytes(Path(prepared_root) / "launch-intent.json", label="launch intent")
    try:
        intent = json.loads(intent_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Revision-gain v2 launch intent is invalid") from error
    if canonical(intent) + b"\n" != intent_raw or intent != {"format_version": 1, "study_id": STUDY_ID, "kind": "one_launch_intent", "prepared_record_sha256": _sha256(raw), "process_launches": 1, "no_resend": True}:
        raise ValueError("Revision-gain v2 launch intent is not authenticated")
    terminal_path = Path(prepared_root) / "terminal-outcome.json"
    if terminal_path.exists():
        terminal_raw = _stable_bytes(terminal_path, label="terminal outcome")
        reconciliation_raw = _stable_bytes(Path(prepared_root) / "reconciliation.json", label="postlaunch reconciliation")
        try:
            reconciliation = json.loads(reconciliation_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Revision-gain v2 postlaunch reconciliation is invalid") from error
        expected_reconciliation = {"format_version": 1, "study_id": STUDY_ID, "kind": "postlaunch_receipt_reconciliation", "prepared_record_sha256": _sha256(raw), "launch_intent_sha256": _sha256(intent_raw), "terminal_outcome_sha256": _sha256(terminal_raw), "acknowledgement_sha256": reconciliation.get("acknowledgement_sha256"), "action": "accept_settled_native_receipt_without_resend"}
        if canonical(reconciliation) + b"\n" != reconciliation_raw or reconciliation != expected_reconciliation:
            raise ValueError("Revision-gain v2 postlaunch receipt requires authenticated reconciliation")
        _hex(reconciliation["acknowledgement_sha256"], label="reconciliation acknowledgement hash")
    required = {"prepared_record_sha256", "launch_intent_sha256", "frozen_manifest_sha256", "provider_request_id", "session_id", "status", "provider_model", "reasoning", "tools_enabled", "transmitted_payload_sha256", "returned_response_sha256", "response"}
    if set(receipt) != required or receipt["status"] != 200 or receipt["tools_enabled"] is not False:
        raise ValueError("Revision-gain v2 receipt is not a settled tools-disabled native success")
    for field in ("provider_request_id", "session_id"):
        if not isinstance(receipt[field], str) or not receipt[field]:
            raise ValueError("Revision-gain v2 native receipt identity is missing")
    if receipt["prepared_record_sha256"] != _sha256(raw) or receipt["launch_intent_sha256"] != _sha256(intent_raw) or receipt["frozen_manifest_sha256"] != prepared["frozen_manifest_sha256"]:
        raise ValueError("Revision-gain v2 receipt is not bound to its exact prepared/frozen record")
    payload = current["payload"]
    if receipt["provider_model"] != prepared["provider_model"] or receipt["reasoning"] != prepared["reasoning"] or receipt["transmitted_payload_sha256"] != payload["sha256"]:
        raise ValueError("Revision-gain v2 receipt identity or payload binding drifted")
    response = receipt["response"]
    if not isinstance(response, Mapping) or receipt["returned_response_sha256"] != _sha256(canonical(response)):
        raise ValueError("Revision-gain v2 receipt response binding drifted")
    _validate_response_schema(prepared, response)
    verified = {"format_version": 1, "study_id": STUDY_ID, "kind": "verified_native_receipt", "prepared_root": str(Path(prepared_root).resolve()), "event_id": prepared["event_id"], "phase": prepared["phase"], "prepared_record_sha256": _sha256(raw), "launch_intent_sha256": _sha256(intent_raw), "frozen_manifest_sha256": prepared["frozen_manifest_sha256"], "provider_request_id": receipt["provider_request_id"], "session_id": receipt["session_id"], "provider_model": receipt["provider_model"], "reasoning": receipt["reasoning"], "tools_enabled": False, "payload_sha256": payload["sha256"], "response_sha256": receipt["returned_response_sha256"], "native_receipt": dict(receipt), "response": dict(response)}
    if output_path is not None:
        _write_once(Path(output_path), verified)
    return verified


def project_independent_metrics(*, endpoint_receipt_paths: list[Path]) -> dict[str, Any]:
    value = contract()
    schedule = {row["endpoint_event_id"]: row for row in endpoint_schedule(value)}
    if len(endpoint_receipt_paths) != len(schedule):
        raise ValueError("Revision-gain v2 endpoint evidence is incomplete")
    observed: dict[str, int] = {}
    for path in endpoint_receipt_paths:
        raw = _stable_bytes(Path(path), label="persisted endpoint receipt")
        try:
            receipt = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Revision-gain v2 persisted endpoint receipt is invalid") from error
        if canonical(receipt) + b"\n" != raw or receipt.get("kind") != "verified_native_receipt" or receipt.get("phase") != "blind_endpoint_judgment":
            raise ValueError("Revision-gain v2 endpoint projection requires persisted verified receipts")
        if not isinstance(receipt.get("prepared_root"), str) or not isinstance(receipt.get("native_receipt"), Mapping):
            raise ValueError("Revision-gain v2 endpoint projection rejects handcrafted receipt summaries")
        reopened = validate_receipt(prepared_root=Path(receipt["prepared_root"]), receipt=receipt["native_receipt"], output_path=None, study_value=value)
        if reopened != receipt:
            raise ValueError("Revision-gain v2 persisted endpoint receipt failed independent revalidation")
        event = schedule.get(receipt.get("event_id"))
        if event is None or event["endpoint_event_id"] in observed:
            raise ValueError("Revision-gain v2 endpoint evidence is unscheduled or duplicated")
        expected = value["routes"]["judges"][event["judge_route_id"]]
        response = receipt.get("response")
        score = response.get("overall") if isinstance(response, Mapping) else None
        limits = (1, 7) if event["measure_id"] == "holistic" else (1, 5)
        if receipt.get("provider_model") != expected["model"] or receipt.get("reasoning") != expected["reasoning"] or receipt.get("tools_enabled") is not False or not isinstance(score, int) or isinstance(score, bool) or not limits[0] <= score <= limits[1]:
            raise ValueError("Revision-gain v2 endpoint receipt identity or score drifted")
        observed[event["endpoint_event_id"]] = score
    target_by_event = {row["target_event_id"]: row["blind_target_id"] for row in targets(value) if row["target_event_id"]}
    rows: list[dict[str, Any]] = []
    for revision in revision_schedule(value):
        if revision["guidance_arm"] != "cwr_guided":
            continue
        control = _revision_id(revision["cycle"], revision["source_item_id"], "generic_no_feedback")
        for judge in value["routes"]["judges"]:
            for measure in ("holistic", "compact"):
                guided_id = f"endpoint-v2-{target_by_event[revision['event_id']]}-{measure}-{judge}"
                control_id = f"endpoint-v2-{target_by_event[control]}-{measure}-{judge}"
                rows.append({"source_item_id": revision["source_item_id"], "cycle": revision["cycle"], "generator_id": "grok-4.6", "judge_route_id": judge, "measure_id": measure, "guided_event_id": revision["event_id"], "control_event_id": control, "guided_minus_control": observed[guided_id] - observed[control_id]})
    summaries = []
    for judge in value["routes"]["judges"]:
        for measure in ("holistic", "compact"):
            scores = [row["guided_minus_control"] for row in rows if row["judge_route_id"] == judge and row["measure_id"] == measure]
            summaries.append({"judge_route_id": judge, "measure_id": measure, "sample_count": len(scores), "mean_guided_minus_control": sum(scores) / len(scores), "positive": sum(score > 0 for score in scores), "zero": sum(score == 0 for score in scores), "negative": sum(score < 0 for score in scores)})
    baselines = {row["source_item_id"]: row["blind_target_id"] for row in targets(value) if row["kind"] == "source_baseline"}
    versus_baseline = []
    for revision in revision_schedule(value):
        target = target_by_event[revision["event_id"]]
        for judge in value["routes"]["judges"]:
            for measure in ("holistic", "compact"):
                endpoint_id = f"endpoint-v2-{target}-{measure}-{judge}"
                baseline_id = f"endpoint-v2-{baselines[revision['source_item_id']]}-{measure}-{judge}"
                versus_baseline.append({"source_item_id": revision["source_item_id"], "cycle": revision["cycle"], "guidance_arm": revision["guidance_arm"], "judge_route_id": judge, "measure_id": measure, "event_id": revision["event_id"], "baseline_target_id": baselines[revision["source_item_id"]], "arm_minus_baseline": observed[endpoint_id] - observed[baseline_id]})
    return {"study_id": STUDY_ID, "kind": "independently_recomputed_endpoint_projection", "primary_guided_minus_control": rows, "arm_minus_baseline": versus_baseline, "summaries": summaries}
